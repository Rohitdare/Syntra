"""Unit tests for Sources API routes (/api/projects/{project_id}/sources)."""

from __future__ import annotations

import datetime
import io
import json
import uuid
from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient

from research_desk.api.auth import get_current_user, get_owned_project
from research_desk.api.dependencies import (
    get_event_sink,
    get_pipeline_orchestrator,
    get_vector_store,
    reset_dependencies,
)
from research_desk.core.config import Settings
from research_desk.main import create_app
from research_desk.orchestrator.events import EventMessage, EventSink
from research_desk.orchestrator.pipeline import PipelineOrchestrator
from research_desk.stores.db import get_db
from research_desk.stores.models import Job, Project, Source, User
from research_desk.stores.vector import VectorStore


def get_test_settings() -> Settings:
    return Settings(
        GEMINI_API_KEY="test-key",
        DATABASE_URL="postgresql://user:pass@localhost:5432/testdb",
        QDRANT_URL="http://localhost:6333",
        APP_ENV="local",
        AUTH_MODE="dev",
        MAX_SOURCES_PER_PROJECT=2,
        MAX_UPLOAD_MB=1,
        MAX_PASTE_CHARS=5000,
    )


@pytest.fixture(autouse=True)
def clean_dependencies():
    reset_dependencies()
    yield
    reset_dependencies()


@pytest.fixture
def test_user() -> User:
    return User(
        id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
        auth_subject="test-user",
        email="test@example.com",
    )


@pytest.fixture
def test_project(test_user: User) -> Project:
    return Project(
        id="prj_src_test01",
        owner_id=test_user.id,
        name="Sources Test Project",
        status="active",
    )


@pytest.mark.asyncio
async def test_ingest_source_pdf_success(test_user: User, test_project: Project) -> None:
    """POST /sources with valid multipart PDF streams NDJSON events and finishes with stage_end."""
    app = create_app(get_test_settings())
    mock_session = AsyncMock()

    job_id = uuid.uuid4()
    job = Job(
        id=job_id,
        project_id=test_project.id,
        user_id=test_user.id,
        stage="collect",
        status="running",
        input_hash="hash123",
    )

    now = datetime.datetime.now(datetime.timezone.utc)
    ev1 = EventMessage(
        job_id=job_id,
        seq=1,
        ts=now,
        stage="collect",
        agent="collector",
        type="stage_start",
        message="Parsing PDF",
    )
    ev2 = EventMessage(
        job_id=job_id,
        seq=2,
        ts=now,
        stage="collect",
        agent="collector",
        type="stage_end",
        message="Finished",
    )

    async def fake_subscribe(*args: object, **kwargs: object) -> AsyncGenerator[EventMessage, None]:
        yield ev1
        yield ev2

    mock_event_sink = AsyncMock(spec=EventSink)
    mock_event_sink.subscribe = fake_subscribe

    mock_orchestrator = AsyncMock(spec=PipelineOrchestrator)
    mock_orchestrator.run_job.return_value = (job, True)

    app.dependency_overrides[get_current_user] = lambda: test_user
    app.dependency_overrides[get_db] = lambda: mock_session
    app.dependency_overrides[get_owned_project] = lambda: test_project
    app.dependency_overrides[get_pipeline_orchestrator] = lambda: mock_orchestrator
    app.dependency_overrides[get_event_sink] = lambda: mock_event_sink

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            "research_desk.api.routes.sources.SourceRepo.count_by_project",
            AsyncMock(return_value=0),
        )

        pdf_bytes = b"%PDF-1.4 sample content for unit testing ingestion pipeline"
        files = {"file": ("sample.pdf", io.BytesIO(pdf_bytes), "application/pdf")}
        data = {"title": "Sample Research Paper"}

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                f"/api/projects/{test_project.id}/sources",
                files=files,
                data=data,
            )

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/x-ndjson")
    assert resp.headers["X-Job-Id"] == str(job_id)

    lines = [json.loads(line) for line in resp.text.strip().split("\n") if line]
    assert len(lines) == 2
    assert lines[0]["type"] == "stage_start"
    assert lines[1]["type"] == "stage_end"


@pytest.mark.asyncio
async def test_ingest_source_url_success(test_user: User, test_project: Project) -> None:
    """POST /sources with application/json URL runs collector job and streams events."""
    app = create_app(get_test_settings())
    mock_session = AsyncMock()

    job_id = uuid.uuid4()
    job = Job(
        id=job_id,
        project_id=test_project.id,
        user_id=test_user.id,
        stage="collect",
        status="running",
        input_hash="hash_url",
    )

    ev = EventMessage(
        job_id=job_id,
        seq=1,
        ts=datetime.datetime.now(datetime.timezone.utc),
        stage="collect",
        agent="collector",
        type="stage_end",
        message="Done",
    )

    async def fake_subscribe(*args: object, **kwargs: object) -> AsyncGenerator[EventMessage, None]:
        yield ev

    mock_event_sink = AsyncMock(spec=EventSink)
    mock_event_sink.subscribe = fake_subscribe

    mock_orchestrator = AsyncMock(spec=PipelineOrchestrator)
    mock_orchestrator.run_job.return_value = (job, True)

    app.dependency_overrides[get_current_user] = lambda: test_user
    app.dependency_overrides[get_db] = lambda: mock_session
    app.dependency_overrides[get_owned_project] = lambda: test_project
    app.dependency_overrides[get_pipeline_orchestrator] = lambda: mock_orchestrator
    app.dependency_overrides[get_event_sink] = lambda: mock_event_sink

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            "research_desk.api.routes.sources.SourceRepo.count_by_project",
            AsyncMock(return_value=0),
        )

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                f"/api/projects/{test_project.id}/sources",
                json={"url": "https://example.com/article", "title": "Online Article"},
            )

    assert resp.status_code == 200
    mock_orchestrator.run_job.assert_awaited_once()


@pytest.mark.asyncio
async def test_ingest_source_text_success(test_user: User, test_project: Project) -> None:
    """POST /sources with application/json pasted text runs collector job."""
    app = create_app(get_test_settings())
    mock_session = AsyncMock()

    job_id = uuid.uuid4()
    job = Job(
        id=job_id,
        project_id=test_project.id,
        user_id=test_user.id,
        stage="collect",
        status="running",
        input_hash="hash_text",
    )

    ev = EventMessage(
        job_id=job_id,
        seq=1,
        ts=datetime.datetime.now(datetime.timezone.utc),
        stage="collect",
        agent="collector",
        type="stage_end",
        message="Done",
    )

    async def fake_subscribe(*args: object, **kwargs: object) -> AsyncGenerator[EventMessage, None]:
        yield ev

    mock_event_sink = AsyncMock(spec=EventSink)
    mock_event_sink.subscribe = fake_subscribe

    mock_orchestrator = AsyncMock(spec=PipelineOrchestrator)
    mock_orchestrator.run_job.return_value = (job, True)

    app.dependency_overrides[get_current_user] = lambda: test_user
    app.dependency_overrides[get_db] = lambda: mock_session
    app.dependency_overrides[get_owned_project] = lambda: test_project
    app.dependency_overrides[get_pipeline_orchestrator] = lambda: mock_orchestrator
    app.dependency_overrides[get_event_sink] = lambda: mock_event_sink

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            "research_desk.api.routes.sources.SourceRepo.count_by_project",
            AsyncMock(return_value=0),
        )

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                f"/api/projects/{test_project.id}/sources",
                json={"text": "A" * 600, "title": "Raw Notes"},
            )

    assert resp.status_code == 200
    mock_orchestrator.run_job.assert_awaited_once()


@pytest.mark.asyncio
async def test_ingest_source_invalid_pdf_magic_bytes(
    test_user: User, test_project: Project
) -> None:
    """Uploading non-PDF content (wrong magic bytes) returns 415 UNSUPPORTED_MEDIA_TYPE."""
    app = create_app(get_test_settings())
    mock_session = AsyncMock()

    app.dependency_overrides[get_current_user] = lambda: test_user
    app.dependency_overrides[get_db] = lambda: mock_session
    app.dependency_overrides[get_owned_project] = lambda: test_project

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            "research_desk.api.routes.sources.SourceRepo.count_by_project",
            AsyncMock(return_value=0),
        )

        # Plain text disguised as a PDF
        fake_pdf = b"NOT_A_PDF plain text content"
        files = {"file": ("fake.pdf", io.BytesIO(fake_pdf), "application/pdf")}

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                f"/api/projects/{test_project.id}/sources",
                files=files,
            )

    assert resp.status_code == 415
    assert resp.json()["error"]["code"] == "UNSUPPORTED_MEDIA_TYPE"


@pytest.mark.asyncio
async def test_ingest_source_payload_too_large(test_user: User, test_project: Project) -> None:
    """Uploading bytes exceeding MAX_UPLOAD_MB returns 413 PAYLOAD_TOO_LARGE."""
    app = create_app(get_test_settings())
    mock_session = AsyncMock()

    app.dependency_overrides[get_current_user] = lambda: test_user
    app.dependency_overrides[get_db] = lambda: mock_session
    app.dependency_overrides[get_owned_project] = lambda: test_project

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            "research_desk.api.routes.sources.SourceRepo.count_by_project",
            AsyncMock(return_value=0),
        )

        # 1MB limit in test settings; send 1.2MB
        oversize_pdf = b"%PDF" + (b"X" * (1024 * 1024 + 200 * 1024))
        files = {"file": ("big.pdf", io.BytesIO(oversize_pdf), "application/pdf")}

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                f"/api/projects/{test_project.id}/sources",
                files=files,
            )

    assert resp.status_code == 413
    assert resp.json()["error"]["code"] == "PAYLOAD_TOO_LARGE"


@pytest.mark.asyncio
async def test_ingest_source_max_sources_limit_reached(
    test_user: User, test_project: Project
) -> None:
    """Attempting ingest when project reaches MAX_SOURCES_PER_PROJECT returns 409."""
    app = create_app(get_test_settings())
    mock_session = AsyncMock()

    app.dependency_overrides[get_current_user] = lambda: test_user
    app.dependency_overrides[get_db] = lambda: mock_session
    app.dependency_overrides[get_owned_project] = lambda: test_project

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            "research_desk.api.routes.sources.SourceRepo.count_by_project",
            AsyncMock(return_value=2),  # Limit is 2
        )

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                f"/api/projects/{test_project.id}/sources",
                json={"url": "https://example.com/blocked"},
            )

    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "LIMIT_REACHED"


@pytest.mark.asyncio
async def test_ingest_source_invalid_idempotency_key(
    test_user: User, test_project: Project
) -> None:
    """Invalid Idempotency-Key header returns 400 BAD_REQUEST."""
    app = create_app(get_test_settings())
    mock_session = AsyncMock()

    app.dependency_overrides[get_current_user] = lambda: test_user
    app.dependency_overrides[get_db] = lambda: mock_session
    app.dependency_overrides[get_owned_project] = lambda: test_project

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            "research_desk.api.routes.sources.SourceRepo.count_by_project",
            AsyncMock(return_value=0),
        )

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                f"/api/projects/{test_project.id}/sources",
                json={"url": "https://example.com/ok"},
                headers={"Idempotency-Key": "key with spaces \n"},
            )

    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "BAD_REQUEST"


@pytest.mark.asyncio
async def test_get_source_detail_success(test_user: User, test_project: Project) -> None:
    """GET /sources/{source_id} returns source metadata, summary, and stage booleans."""
    app = create_app(get_test_settings())
    mock_session = AsyncMock()

    source = Source(
        project_id=test_project.id,
        id="src_detail01",
        tag="S1",
        kind="pdf",
        title="Foundational AI",
        origin="ai.pdf",
        content_hash="hash_ai",
        char_count=12000,
        chunk_count=10,
        claim_count=5,
        summary="Overview of deep learning architectures",
        stage_collected=True,
        stage_analyzed=True,
        stage_critiqued=True,
        last_error=None,
    )

    app.dependency_overrides[get_current_user] = lambda: test_user
    app.dependency_overrides[get_db] = lambda: mock_session
    app.dependency_overrides[get_owned_project] = lambda: test_project

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            "research_desk.api.routes.sources.SourceRepo.get",
            AsyncMock(return_value=source),
        )

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get(f"/api/projects/{test_project.id}/sources/src_detail01")

    assert resp.status_code == 200
    data = resp.json()
    assert data["source"]["id"] == "src_detail01"
    assert data["source"]["tag"] == "S1"
    assert data["summary"] == "Overview of deep learning architectures"
    assert data["source"]["stages"]["critiqued"] is True


@pytest.mark.asyncio
async def test_get_source_not_found(test_user: User, test_project: Project) -> None:
    """GET /sources/{source_id} for non-existent source returns 404 NOT_FOUND."""
    app = create_app(get_test_settings())
    mock_session = AsyncMock()

    app.dependency_overrides[get_current_user] = lambda: test_user
    app.dependency_overrides[get_db] = lambda: mock_session
    app.dependency_overrides[get_owned_project] = lambda: test_project

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            "research_desk.api.routes.sources.SourceRepo.get",
            AsyncMock(return_value=None),
        )

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get(f"/api/projects/{test_project.id}/sources/src_nonexistent")

    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "NOT_FOUND"


@pytest.mark.asyncio
async def test_delete_source_active_job_conflict(test_user: User, test_project: Project) -> None:
    """DELETE /sources/{source_id} rejects with 409 JOB_ACTIVE if job is running."""
    app = create_app(get_test_settings())
    mock_session = AsyncMock()

    source = Source(
        project_id=test_project.id,
        id="src_busy01",
        tag="S1",
        kind="pdf",
        title="Busy Source",
        origin="busy.pdf",
        content_hash="hash_busy",
    )

    app.dependency_overrides[get_current_user] = lambda: test_user
    app.dependency_overrides[get_db] = lambda: mock_session
    app.dependency_overrides[get_owned_project] = lambda: test_project

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            "research_desk.api.routes.sources.SourceRepo.get",
            AsyncMock(return_value=source),
        )
        mp.setattr(
            "research_desk.api.routes.sources.JobRepo.has_active_for_source",
            AsyncMock(return_value=True),
        )

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.delete(f"/api/projects/{test_project.id}/sources/src_busy01")

    assert resp.status_code == 409
    data = resp.json()
    assert data["error"]["code"] == "JOB_ACTIVE"
    assert "A stage is still running for this source." in data["error"]["message"]


@pytest.mark.asyncio
async def test_delete_source_success(test_user: User, test_project: Project) -> None:
    """DELETE /sources/{source_id} purges Qdrant vectors and deletes DB record."""
    app = create_app(get_test_settings())
    mock_session = AsyncMock()
    mock_vectors = AsyncMock(spec=VectorStore)

    source = Source(
        project_id=test_project.id,
        id="src_del01",
        tag="S1",
        kind="pdf",
        title="Delete Me",
        origin="del.pdf",
        content_hash="hash_del",
    )

    app.dependency_overrides[get_current_user] = lambda: test_user
    app.dependency_overrides[get_db] = lambda: mock_session
    app.dependency_overrides[get_owned_project] = lambda: test_project
    app.dependency_overrides[get_vector_store] = lambda: mock_vectors

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            "research_desk.api.routes.sources.SourceRepo.get",
            AsyncMock(return_value=source),
        )
        mp.setattr(
            "research_desk.api.routes.sources.JobRepo.has_active_for_source",
            AsyncMock(return_value=False),
        )
        mp.setattr(
            "research_desk.api.routes.sources.SourceRepo.delete",
            AsyncMock(),
        )

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.delete(f"/api/projects/{test_project.id}/sources/src_del01")

    assert resp.status_code == 200
    assert resp.json() == {"deleted": True}
    mock_vectors.delete_source.assert_awaited_once_with(test_project.id, "src_del01")


@pytest.mark.asyncio
async def test_ingest_source_idempotency_conflict(test_user: User, test_project: Project) -> None:
    """Reusing idempotency key with different payload returns 409 IDEMPOTENCY_CONFLICT."""
    from research_desk.core.errors import AppError

    app = create_app(get_test_settings())
    mock_session = AsyncMock()

    mock_orchestrator = AsyncMock(spec=PipelineOrchestrator)
    mock_orchestrator.run_job.side_effect = AppError(
        code="IDEMPOTENCY_CONFLICT",
        message="Idempotency key reused with different request payload",
        http_status=409,
    )

    app.dependency_overrides[get_current_user] = lambda: test_user
    app.dependency_overrides[get_db] = lambda: mock_session
    app.dependency_overrides[get_owned_project] = lambda: test_project
    app.dependency_overrides[get_pipeline_orchestrator] = lambda: mock_orchestrator

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            "research_desk.api.routes.sources.SourceRepo.count_by_project",
            AsyncMock(return_value=0),
        )

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                f"/api/projects/{test_project.id}/sources",
                json={"url": "https://example.com/different"},
                headers={"Idempotency-Key": "reused_key_123"},
            )

    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"


@pytest.mark.asyncio
async def test_ingest_source_duplicate_joins_existing_job(
    test_user: User, test_project: Project
) -> None:
    """Duplicate submit attaches to active job (is_new=False) and cleans up temp file."""
    import os

    app = create_app(get_test_settings())
    mock_session = AsyncMock()

    job_id = uuid.uuid4()
    job = Job(
        id=job_id,
        project_id=test_project.id,
        user_id=test_user.id,
        stage="collect",
        status="running",
        input_hash="hash_dup",
    )

    ev = EventMessage(
        job_id=job_id,
        seq=1,
        ts=datetime.datetime.now(datetime.timezone.utc),
        stage="collect",
        agent="collector",
        type="stage_end",
        message="Joined stream",
    )

    async def fake_subscribe(*args: object, **kwargs: object) -> AsyncGenerator[EventMessage, None]:
        yield ev

    mock_event_sink = AsyncMock(spec=EventSink)
    mock_event_sink.subscribe = fake_subscribe

    created_temp_path: list[str] = []

    async def mock_run_job(*args: object, **kwargs: object) -> tuple[Job, bool]:
        inp = kwargs.get("inp")
        if inp and getattr(inp, "pdf_path", None):
            created_temp_path.append(inp.pdf_path)
        return job, False  # is_new = False

    mock_orchestrator = AsyncMock(spec=PipelineOrchestrator)
    mock_orchestrator.run_job.side_effect = mock_run_job

    app.dependency_overrides[get_current_user] = lambda: test_user
    app.dependency_overrides[get_db] = lambda: mock_session
    app.dependency_overrides[get_owned_project] = lambda: test_project
    app.dependency_overrides[get_pipeline_orchestrator] = lambda: mock_orchestrator
    app.dependency_overrides[get_event_sink] = lambda: mock_event_sink

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            "research_desk.api.routes.sources.SourceRepo.count_by_project",
            AsyncMock(return_value=0),
        )

        pdf_bytes = b"%PDF-1.4 duplicate test content"
        files = {"file": ("dup.pdf", io.BytesIO(pdf_bytes), "application/pdf")}

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                f"/api/projects/{test_project.id}/sources",
                files=files,
            )

    assert resp.status_code == 200
    assert resp.headers["X-Job-Id"] == str(job_id)
    # The temporary file created during this request should be deleted because is_new=False
    assert len(created_temp_path) == 1
    assert not os.path.exists(created_temp_path[0])
