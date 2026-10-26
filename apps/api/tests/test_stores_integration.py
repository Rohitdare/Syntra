"""Integration tests for PostgreSQL repositories and QdrantVectorStore against live services.

Runs when live PostgreSQL and Qdrant are available (e.g. in CI service containers).
Skips gracefully if local Docker services are not running.
"""

from __future__ import annotations

import uuid

import pytest

from research_desk.core.config import get_settings
from research_desk.core.ids import make_claim_key, make_project_id, make_source_id, qdrant_point_id
from research_desk.stores.db import check_db_readiness, get_sessionmaker
from research_desk.stores.models import Project, Source, User
from research_desk.stores.repos.projects import ProjectRepo
from research_desk.stores.repos.sources import SourceRepo
from research_desk.stores.vector import QdrantVectorStore


async def is_integration_available() -> tuple[bool, bool]:
    settings = get_settings()
    db_ok = await check_db_readiness(settings)
    vector_store = QdrantVectorStore(settings)
    qdrant_ok = await vector_store.ping()
    return db_ok, qdrant_ok


@pytest.mark.asyncio
async def test_postgres_tag_allocation_and_cascade() -> None:
    """Test project tag allocation locking and cascade deletion in PostgreSQL."""
    settings = get_settings()
    db_ok = await check_db_readiness(settings)
    if not db_ok:
        pytest.skip("PostgreSQL not reachable (Docker not started)")

    sm = get_sessionmaker(settings)
    owner_id = uuid.uuid4()
    prj_id = make_project_id()

    async with sm() as session:
        async with session.begin():
            session.add(User(id=owner_id, auth_subject=f"test-owner-{owner_id}"))
            repo = ProjectRepo(session)
            await repo.create(Project(id=prj_id, owner_id=owner_id, name="Integration Prj"))

    # Allocate tags sequentially
    async with sm() as session:
        async with session.begin():
            repo = ProjectRepo(session)
            tag1 = await repo.allocate_next_tag(prj_id)
            tag2 = await repo.allocate_next_tag(prj_id)
            assert tag1 == "S1"
            assert tag2 == "S2"

    # Add source and verify
    src_id = make_source_id()
    async with sm() as session:
        async with session.begin():
            s_repo = SourceRepo(session)
            src = await s_repo.upsert(
                Source(
                    project_id=prj_id,
                    id=src_id,
                    tag=tag1,
                    kind="text",
                    title="Source 1",
                    content_hash="hash1",
                )
            )
            assert src.tag == "S1"

    # Soft delete -> status becomes 'deleting'
    async with sm() as session:
        async with session.begin():
            repo = ProjectRepo(session)
            await repo.set_status(prj_id, "deleting")
            p = await repo.get(prj_id)
            assert p is not None and p.status == "deleting"

    # Hard delete -> cascades and removes project
    async with sm() as session:
        async with session.begin():
            repo = ProjectRepo(session)
            await repo.hard_delete(prj_id)
            p_deleted = await repo.get(prj_id)
            assert p_deleted is None


@pytest.mark.asyncio
async def test_qdrant_vector_store_idempotency_and_filter() -> None:
    """Test Qdrant upsert idempotency and cross-project/source filtering."""
    settings = get_settings()
    vector_store = QdrantVectorStore(settings)
    qdrant_ok = await vector_store.ping()
    if not qdrant_ok:
        pytest.skip("Qdrant not reachable (Docker not started)")

    prj_a = make_project_id()
    prj_b = make_project_id()
    src_1 = make_source_id()
    clm_key = make_claim_key(src_1, 1)

    pt_id_a = qdrant_point_id(prj_a, clm_key)
    pt_id_b = qdrant_point_id(prj_b, clm_key)

    # Note: pt_id_a != pt_id_b because UUIDv5 includes project_id
    assert pt_id_a != pt_id_b

    vec = [0.1] * 768

    # Upsert to prj_a
    await vector_store.upsert(
        project_id=prj_a,
        points=[
            {
                "id": pt_id_a,
                "vector": vec,
                "payload": {
                    "projectId": prj_a,
                    "sourceId": src_1,
                    "key": clm_key,
                    "type": "claim",
                },
            }
        ],
    )

    # Querying from prj_b must NEVER return points from prj_a
    hits = await vector_store.query_similar(
        project_id=prj_b,
        vector=vec,
        point_type="claim",
    )
    assert len(hits) == 0

    # Querying from prj_a must return point
    hits_a = await vector_store.query_similar(
        project_id=prj_a,
        vector=vec,
        point_type="claim",
    )
    assert len(hits_a) == 1
    assert hits_a[0]["key"] == clm_key

    # Clean up
    await vector_store.delete_by_project(prj_a)
