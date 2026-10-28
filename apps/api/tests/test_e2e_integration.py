"""Live end-to-end integration tests against real PostgreSQL and Qdrant.

Per Stage 2.7 specification:
- Real FastAPI application and HTTP client (httpx.AsyncClient with ASGITransport).
- Real PostgreSQL database and real Qdrant vector index.
- Strict data safety: Unique test IDs, strict targeted cleanup, zero table drops/truncations.
- Isolated embeddings for deterministic CI/CD, plus opt-in live Gemini test.
"""

from __future__ import annotations

import json
import os
import uuid
from collections.abc import Sequence
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from research_desk.api.dependencies import get_embedding_provider, reset_dependencies
from research_desk.core.config import Settings, get_settings
from research_desk.main import create_app
from research_desk.providers.embeddings import EmbedKind
from research_desk.providers.llm import CallContext
from research_desk.stores.db import check_db_readiness, get_sessionmaker, reset_engine
from research_desk.stores.repos.jobs import JobRepo
from research_desk.stores.repos.projects import ProjectRepo
from research_desk.stores.repos.sources import SourceRepo
from research_desk.stores.vector import get_vector_store


class DeterministicFakeEmbeddingProvider:
    """Deterministic embedding provider generating 768-dim normalized vectors without LLM calls.

    Used strictly for testing database, vector store, and API lifecycle isolation.
    Persists real chunks and real points in Qdrant.
    """

    def __init__(self, dim: int = 768) -> None:
        self.dim = dim

    async def embed_texts(
        self,
        texts: Sequence[str],
        kind: EmbedKind,
        *,
        ctx: CallContext,
    ) -> list[list[float]]:
        res: list[list[float]] = []
        for text in texts:
            # Deterministic non-zero values between 0.01 and 0.1
            val = round(0.01 + ((abs(hash(text)) % 900) / 10000.0), 6)
            res.append([val] * self.dim)
        return res


async def check_live_services() -> tuple[bool, bool]:
    settings = get_settings()
    db_ok = await check_db_readiness(settings)
    vector_store = get_vector_store(settings)
    qdrant_ok = await vector_store.ping()
    return db_ok, qdrant_ok


@pytest.fixture(autouse=True)
async def clean_deps():
    reset_dependencies()
    await reset_engine()
    yield
    reset_dependencies()
    await reset_engine()


def get_e2e_test_app(override_embeddings: bool = True):
    base_settings = get_settings()
    # Use AUTH_MODE='jwt' so Bearer tokens map cleanly to distinct users in PostgreSQL
    test_settings = Settings(
        GEMINI_API_KEY=base_settings.GEMINI_API_KEY,
        DATABASE_URL=base_settings.DATABASE_URL,
        QDRANT_URL=base_settings.QDRANT_URL,
        QDRANT_API_KEY=base_settings.QDRANT_API_KEY,
        QDRANT_COLLECTION=base_settings.QDRANT_COLLECTION,
        APP_ENV="local",
        AUTH_MODE="jwt",
        LOG_LEVEL="WARNING",
    )
    app = create_app(test_settings)
    if override_embeddings:
        app.dependency_overrides[get_embedding_provider] = lambda: (
            DeterministicFakeEmbeddingProvider()
        )
    return app, test_settings


@pytest.mark.asyncio
async def test_live_project_lifecycle() -> None:
    """Scenario A: Project creation, retrieval, DB verification, and deletion."""
    db_ok, qdrant_ok = await check_live_services()
    if not db_ok:
        pytest.skip("PostgreSQL not reachable on configured port")
    if not qdrant_ok:
        pytest.skip("Qdrant not reachable on configured port")

    app, settings = get_e2e_test_app()
    user_token = f"e2e-user-{uuid.uuid4().hex[:8]}"
    headers = {"Authorization": f"Bearer {user_token}"}
    created_prj_id: str | None = None

    sm = get_sessionmaker(settings)
    vector_store = get_vector_store(settings)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        try:
            # 1. Create project via HTTP POST
            res = await client.post(
                "/api/projects",
                headers=headers,
                json={
                    "name": "E2E Test Lifecycle Project",
                    "description": "Live integration lifecycle",
                },
            )
            assert res.status_code == 201, res.text
            data = res.json()
            assert "projectId" in data
            created_prj_id = data["projectId"]
            assert created_prj_id.startswith("prj_")

            # 2. Retrieve project via HTTP GET
            get_res = await client.get(f"/api/projects/{created_prj_id}", headers=headers)
            assert get_res.status_code == 200, get_res.text
            proj_data = get_res.json()
            assert proj_data["project"]["id"] == created_prj_id
            assert proj_data["project"]["name"] == "E2E Test Lifecycle Project"
            assert proj_data["project"]["description"] == "Live integration lifecycle"
            assert proj_data["sources"] == []
            assert proj_data["activeJobs"] == []

            # 3. Confirm database record exists directly in PostgreSQL
            async with sm() as session:
                repo = ProjectRepo(session)
                db_proj = await repo.get(created_prj_id)
                assert db_proj is not None
                assert db_proj.name == "E2E Test Lifecycle Project"
                assert db_proj.status == "active"

            # 4. Delete project via HTTP DELETE
            del_res = await client.delete(f"/api/projects/{created_prj_id}", headers=headers)
            assert del_res.status_code == 200, del_res.text
            del_data = del_res.json()
            assert del_data["deleted"] >= 1

            # 5. Confirm deletion in PostgreSQL and Qdrant
            async with sm() as session:
                repo = ProjectRepo(session)
                db_proj_after = await repo.get(created_prj_id)
                assert db_proj_after is None

            pts_count = await vector_store.count(created_prj_id, "chunk")
            assert pts_count == 0
            created_prj_id = None

        finally:
            # Safe targeted cleanup if assertion failed
            if created_prj_id:
                await vector_store.delete_project(created_prj_id)
                async with sm() as session:
                    async with session.begin():
                        repo = ProjectRepo(session)
                        p = await repo.get(created_prj_id)
                        if p:
                            await repo.delete(created_prj_id)


@pytest.mark.asyncio
async def test_live_ingest_pasted_text_and_source_deletion() -> None:
    """Scenario B & C: Ingest text, stream NDJSON, verify DB + Qdrant vectors, delete source."""
    db_ok, qdrant_ok = await check_live_services()
    if not db_ok:
        pytest.skip("PostgreSQL not reachable on configured port")
    if not qdrant_ok:
        pytest.skip("Qdrant not reachable on configured port")

    app, settings = get_e2e_test_app(override_embeddings=True)
    user_token = f"e2e-user-{uuid.uuid4().hex[:8]}"
    headers = {"Authorization": f"Bearer {user_token}"}
    created_prj_id: str | None = None
    created_src_id: str | None = None

    sm = get_sessionmaker(settings)
    vector_store = get_vector_store(settings)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        try:
            # 1. Create a dedicated project
            p_res = await client.post(
                "/api/projects",
                headers=headers,
                json={"name": "E2E Ingestion Test Project"},
            )
            assert p_res.status_code == 201, p_res.text
            created_prj_id = p_res.json()["projectId"]

            # 2. Text payload: > 500 chars to satisfy MIN_SOURCE_CHARS
            sample_paragraphs = [
                (
                    "Artificial intelligence research desks aggregate multi-agent workflows into "
                    "synchronized systems."
                ),
                (
                    "The Collector agent ingests source text, computes deterministic hashes, "
                    "and chunks content."
                ),
                (
                    "PostgreSQL acts as the authoritative system of record storing metadata, "
                    "jobs, and events."
                ),
                (
                    "Qdrant serves as the rebuildable vector index ensuring fast semantic search "
                    "across source chunks."
                ),
                (
                    "Cross-agent coordination occurs via durable transactional states rather than "
                    "unmonitored point-to-point calls."
                ),
                (
                    "Strict boundaries guarantee that unauthorized access returns generic 404 "
                    "responses to eliminate enumeration."
                ),
                (
                    "Every chunk embedded by the pipeline retains project and source IDs in "
                    "its index payload."
                ),
            ]
            valid_text = "\n\n".join(sample_paragraphs)
            assert len(valid_text) >= 500

            # 3. Submit pasted text to ingestion endpoint with streaming response
            stream_res = await client.post(
                f"/api/projects/{created_prj_id}/sources",
                headers=headers,
                json={"title": "E2E Architecture Overview", "text": valid_text},
            )
            assert stream_res.status_code == 200, stream_res.text
            assert "application/x-ndjson" in stream_res.headers.get("content-type", "")

            job_id_str = stream_res.headers.get("X-Job-Id")
            assert job_id_str is not None
            job_uuid = uuid.UUID(job_id_str)

            # 4. Consume NDJSON streaming events
            events: list[dict[str, Any]] = []
            for line in stream_res.text.strip().split("\n"):
                if line.strip():
                    events.append(json.loads(line.strip()))

            assert len(events) >= 2, f"Expected multiple events, got: {events}"
            types = [e.get("type") for e in events]
            assert "stage_end" in types, f"Stream did not terminate with stage_end: {types}"

            # Verify terminal state
            stage_end_event = next(e for e in events if e.get("type") == "stage_end")
            assert stage_end_event.get("data", {}).get("status") == "succeeded"

            # Find result event to extract source ID
            result_event = next((e for e in events if e.get("type") == "result"), None)
            assert result_event is not None
            res_data = result_event.get("data", {})
            created_src_id = res_data.get("sourceId")
            assert created_src_id is not None
            assert created_src_id.startswith("src_")
            chunk_count = res_data.get("chunkCount", 0)
            assert chunk_count > 0

            # 5. Verify PostgreSQL persistence
            async with sm() as session:
                s_repo = SourceRepo(session)
                db_src = await s_repo.get(created_prj_id, created_src_id)
                assert db_src is not None
                assert db_src.stage_collected is True
                assert db_src.chunk_count == chunk_count
                assert db_src.tag == "S1"

                db_text = await s_repo.get_text(created_prj_id, created_src_id)
                assert db_text is not None
                assert db_text.text == valid_text

                j_repo = JobRepo(session)
                db_job = await j_repo.get(job_uuid)
                assert db_job is not None
                assert db_job.status == "succeeded"

            # 5b. Exercise job status and event streaming HTTP routes
            job_status_res = await client.get(f"/api/jobs/{job_uuid}", headers=headers)
            assert job_status_res.status_code == 200, job_status_res.text
            job_status_data = job_status_res.json()
            assert job_status_data["status"] == "succeeded"
            assert job_status_data["stage"] == "collect"

            events_res = await client.get(f"/api/jobs/{job_uuid}/events?after=0", headers=headers)
            assert events_res.status_code == 200, events_res.text
            replayed_events = [
                json.loads(line) for line in events_res.text.strip().split("\n") if line.strip()
            ]
            assert len(replayed_events) >= 2
            assert any(e.get("type") == "stage_end" for e in replayed_events)

            # 6. Verify Qdrant points and payload
            qdrant_count = await vector_store.count(created_prj_id, "chunk")
            assert qdrant_count == chunk_count

            # Search in Qdrant to inspect payload structure
            hits = await vector_store.search_chunks(
                project_id=created_prj_id,
                embedding=[0.01] * 768,
                top_k=5,
            )
            assert len(hits) > 0
            for hit in hits:
                assert hit.key.startswith("chk_")

            # 7. Scenario C: Delete Source via HTTP DELETE
            del_src_res = await client.delete(
                f"/api/projects/{created_prj_id}/sources/{created_src_id}",
                headers=headers,
            )
            assert del_src_res.status_code == 200, del_src_res.text
            assert del_src_res.json() == {"deleted": True}

            # 8. Confirm PostgreSQL records deleted
            async with sm() as session:
                s_repo = SourceRepo(session)
                assert await s_repo.get(created_prj_id, created_src_id) is None
                assert await s_repo.get_text(created_prj_id, created_src_id) is None

            # 9. Confirm Qdrant points purged
            count_after_del = await vector_store.count(created_prj_id, "chunk")
            assert count_after_del == 0
            created_src_id = None

        finally:
            if created_prj_id:
                await vector_store.delete_project(created_prj_id)
                async with sm() as session:
                    async with session.begin():
                        repo = ProjectRepo(session)
                        p = await repo.get(created_prj_id)
                        if p:
                            await repo.delete(created_prj_id)


@pytest.mark.asyncio
async def test_live_contract_and_security_checks() -> None:
    """Scenario D: Cross-user 404 isolation, active job 409 conflict, and input error envelopes."""
    db_ok, qdrant_ok = await check_live_services()
    if not db_ok:
        pytest.skip("PostgreSQL not reachable on configured port")
    if not qdrant_ok:
        pytest.skip("Qdrant not reachable on configured port")

    app, settings = get_e2e_test_app()
    user_a_token = f"user-a-{uuid.uuid4().hex[:8]}"
    user_b_token = f"user-b-{uuid.uuid4().hex[:8]}"
    headers_a = {"Authorization": f"Bearer {user_a_token}"}
    headers_b = {"Authorization": f"Bearer {user_b_token}"}

    created_prj_id: str | None = None
    sm = get_sessionmaker(settings)
    vector_store = get_vector_store(settings)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        try:
            # 1. User A creates a project
            res_a = await client.post(
                "/api/projects",
                headers=headers_a,
                json={"name": "User A Private Research Desk"},
            )
            assert res_a.status_code == 201
            created_prj_id = res_a.json()["projectId"]

            # 2. Cross-user isolation: User B accessing User A's project MUST return 404 NOT_FOUND
            cross_get = await client.get(f"/api/projects/{created_prj_id}", headers=headers_b)
            assert cross_get.status_code == 404, cross_get.text
            err = cross_get.json()["error"]
            assert err["code"] == "NOT_FOUND"

            # 3. Active job conflict test (409 JOB_ACTIVE)
            active_job_id: uuid.UUID | None = None
            async with sm() as session:
                async with session.begin():
                    # Insert an active running job directly in the database
                    p_repo = ProjectRepo(session)
                    p = await p_repo.get(created_prj_id)
                    assert p is not None
                    j_repo = JobRepo(session)
                    job = await j_repo.create_job(
                        project_id=created_prj_id,
                        user_id=p.owner_id,
                        stage="collect",
                        input_hash="hash_dummy",
                    )
                    active_job_id = job.id
                    await j_repo.update_status(active_job_id, status="running")

            # Attempting to delete project while job is active returns 409
            conflict_res = await client.delete(f"/api/projects/{created_prj_id}", headers=headers_a)
            assert conflict_res.status_code == 409, conflict_res.text
            err_data = conflict_res.json()["error"]
            assert err_data["code"] == "JOB_ACTIVE"
            assert err_data["retryable"] is True

            # Mark job succeeded so project can be deleted cleanly
            if active_job_id:
                async with sm() as session:
                    async with session.begin():
                        j_repo = JobRepo(session)
                        await j_repo.update_status(active_job_id, status="succeeded")

            # 4. Input validation and error shapes
            # Missing text and url
            bad_input_res = await client.post(
                f"/api/projects/{created_prj_id}/sources",
                headers=headers_a,
                json={"title": "Missing content"},
            )
            assert bad_input_res.status_code == 400
            assert bad_input_res.json()["error"]["code"] == "BAD_REQUEST"

            # Unauthenticated request without Bearer token
            unauth_res = await client.get(f"/api/projects/{created_prj_id}")
            assert unauth_res.status_code == 401
            assert unauth_res.json()["error"]["code"] == "UNAUTHENTICATED"

            # Non-existent project
            not_found_res = await client.get("/api/projects/prj_nonexistent", headers=headers_a)
            assert not_found_res.status_code == 404
            assert not_found_res.json()["error"]["code"] == "NOT_FOUND"

        finally:
            if created_prj_id:
                await vector_store.delete_project(created_prj_id)
                async with sm() as session:
                    async with session.begin():
                        repo = ProjectRepo(session)
                        p = await repo.get(created_prj_id)
                        if p:
                            await repo.delete(created_prj_id)


@pytest.mark.asyncio
async def test_live_ingest_pasted_text_real_gemini_opt_in() -> None:
    """Opt-in live ingestion test using real Gemini provider (costs quota).

    Explicitly gated behind RUN_LIVE_GEMINI_TESTS=1 and valid GEMINI_API_KEY.
    """
    if os.getenv("RUN_LIVE_GEMINI_TESTS") != "1":
        pytest.skip("RUN_LIVE_GEMINI_TESTS!=1: Skipping billable/quota-consuming live Gemini call")

    db_ok, qdrant_ok = await check_live_services()
    if not db_ok or not qdrant_ok:
        pytest.skip("Local PostgreSQL or Qdrant unavailable")

    app, settings = get_e2e_test_app(override_embeddings=False)
    if not settings.GEMINI_API_KEY or not settings.GEMINI_API_KEY.get_secret_value():
        pytest.skip("GEMINI_API_KEY is missing")

    user_token = f"e2e-gemini-{uuid.uuid4().hex[:8]}"
    headers = {"Authorization": f"Bearer {user_token}"}
    created_prj_id: str | None = None
    sm = get_sessionmaker(settings)
    vector_store = get_vector_store(settings)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        try:
            p_res = await client.post(
                "/api/projects", headers=headers, json={"name": "E2E Live Gemini Project"}
            )
            assert p_res.status_code == 201
            created_prj_id = p_res.json()["projectId"]

            sample_text = (
                "Artificial intelligence research desks aggregate multi-agent workflows into "
                "synchronized systems. "
                "The Collector agent ingests source text, computes deterministic SHA-256 hashes, "
                "and chunks content. "
                "PostgreSQL acts as the authoritative system of record storing source metadata, "
                "jobs, and events. "
                "Qdrant serves as the rebuildable vector index ensuring fast semantic search "
                "across source chunks. "
                "Cross-agent coordination occurs via durable transactional states rather than "
                "unmonitored calls. "
                "Each chunk is stored with its associated project identifier and source identifier "
                "for multi-tenant safety."
            )
            res = await client.post(
                f"/api/projects/{created_prj_id}/sources",
                headers=headers,
                json={"title": "Gemini Ingest", "text": sample_text},
            )
            assert res.status_code == 200
            events = [json.loads(line) for line in res.text.strip().split("\n") if line.strip()]
            stage_end = next(e for e in events if e.get("type") == "stage_end")
            assert stage_end.get("data", {}).get("status") == "succeeded"
        finally:
            if created_prj_id:
                await vector_store.delete_project(created_prj_id)
                async with sm() as session:
                    async with session.begin():
                        repo = ProjectRepo(session)
                        p = await repo.get(created_prj_id)
                        if p:
                            await repo.delete(created_prj_id)
