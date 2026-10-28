"""Integration tests for PostgreSQL repositories and QdrantVectorStore against live services.

Runs when live PostgreSQL and Qdrant are available (e.g. local Docker containers).
Skips gracefully if local Docker services are not running.
"""

from __future__ import annotations

import uuid

import pytest

from research_desk.core.config import get_settings
from research_desk.core.ids import chunk_id, make_project_id, make_source_id, qdrant_point_id
from research_desk.stores.db import check_db_readiness, get_sessionmaker, reset_engine
from research_desk.stores.models import User
from research_desk.stores.repos.projects import ProjectRepo
from research_desk.stores.repos.sources import SourceRepo
from research_desk.stores.vector import ChunkPoint, get_vector_store


@pytest.fixture(autouse=True)
async def clean_deps():
    await reset_engine()
    yield
    await reset_engine()


async def is_integration_available() -> tuple[bool, bool]:
    settings = get_settings()
    db_ok = await check_db_readiness(settings)
    vector_store = get_vector_store(settings)
    qdrant_ok = await vector_store.ping()
    return db_ok, qdrant_ok


@pytest.mark.asyncio
async def test_postgres_tag_allocation_and_cascade() -> None:
    """Test project tag allocation locking and cascade deletion in PostgreSQL."""
    settings = get_settings()
    db_ok = await check_db_readiness(settings)
    if not db_ok:
        pytest.skip("PostgreSQL not reachable on configured port")

    sm = get_sessionmaker(settings)
    owner_id = uuid.uuid4()

    # 1. Create user and project
    async with sm() as session:
        async with session.begin():
            session.add(User(id=owner_id, auth_subject=f"test-owner-{owner_id}"))
            await session.flush()
            repo = ProjectRepo(session)
            project = await repo.create(owner_id=owner_id, name="Integration Prj")
            prj_id = project.id

    try:
        # 2. Allocate tags sequentially under row lock
        async with sm() as session:
            async with session.begin():
                repo = ProjectRepo(session)
                tag1 = await repo.allocate_source_tag(prj_id)
                tag2 = await repo.allocate_source_tag(prj_id)
                assert tag1 == "S1"
                assert tag2 == "S2"

        # 3. Add source and verify
        src_id = make_source_id(prj_id, "test_hash_1")
        async with sm() as session:
            async with session.begin():
                s_repo = SourceRepo(session)
                src = await s_repo.upsert_source(
                    project_id=prj_id,
                    source_id=src_id,
                    tag=tag1,
                    kind="text",
                    title="Source 1",
                    origin="test.txt",
                    content_hash="test_hash_1",
                    char_count=100,
                    text_content="Sample text for integration test.",
                )
                assert src.tag == "S1"
                assert src.content_hash == "test_hash_1"

        # 4. Soft delete -> status becomes 'deleting'
        async with sm() as session:
            async with session.begin():
                repo = ProjectRepo(session)
                await repo.mark_deleting(prj_id)
                p = await repo.get(prj_id)
                assert p is not None and p.status == "deleting"

        # 5. Hard delete -> cascades and removes project, source, and text
        async with sm() as session:
            async with session.begin():
                repo = ProjectRepo(session)
                await repo.delete(prj_id)
                p_deleted = await repo.get(prj_id)
                assert p_deleted is None

                s_repo = SourceRepo(session)
                s_deleted = await s_repo.get(prj_id, src_id)
                assert s_deleted is None
    finally:
        # Cleanup in case of assertion failure
        async with sm() as session:
            async with session.begin():
                repo = ProjectRepo(session)
                p = await repo.get(prj_id)
                if p:
                    await repo.delete(prj_id)


@pytest.mark.asyncio
async def test_qdrant_vector_store_idempotency_and_filter() -> None:
    """Test Qdrant upsert idempotency and cross-project/source filtering."""
    settings = get_settings()
    vector_store = get_vector_store(settings)
    qdrant_ok = await vector_store.ping()
    if not qdrant_ok:
        pytest.skip("Qdrant not reachable on configured port")

    prj_a = make_project_id()
    prj_b = make_project_id()
    src_1 = make_source_id(prj_a, "content_hash_1")
    chk_key = chunk_id(src_1, 0)

    pt_id_a = qdrant_point_id(prj_a, chk_key)
    pt_id_b = qdrant_point_id(prj_b, chk_key)

    # Note: pt_id_a != pt_id_b because UUIDv5 includes project_id
    assert pt_id_a != pt_id_b

    vec = [0.1] * 768

    chunk_point = ChunkPoint(
        key=chk_key,
        project_id=prj_a,
        source_id=src_1,
        chunk_index=0,
        text="Sample chunk for vector integration testing.",
        embedding=vec,
        embedding_model=settings.GEMINI_EMBEDDING_MODEL,
    )

    try:
        # 1. Upsert chunk to prj_a
        await vector_store.upsert_chunks([chunk_point])

        # 2. Count verification
        count_a = await vector_store.count(prj_a, "chunk")
        assert count_a == 1

        # 3. Re-upsert identical chunk (idempotency test)
        await vector_store.upsert_chunks([chunk_point])
        count_a_after = await vector_store.count(prj_a, "chunk")
        assert count_a_after == 1

        # 4. Querying from prj_b must NEVER return points from prj_a
        hits_b = await vector_store.search_chunks(
            project_id=prj_b,
            embedding=vec,
            top_k=5,
        )
        assert len(hits_b) == 0

        # 5. Querying from prj_a must return point
        hits_a = await vector_store.search_chunks(
            project_id=prj_a,
            embedding=vec,
            top_k=5,
        )
        assert len(hits_a) == 1
        assert hits_a[0].key == chk_key

        # 6. Delete source vectors
        await vector_store.delete_source(prj_a, src_1)
        count_after_source_delete = await vector_store.count(prj_a, "chunk")
        assert count_after_source_delete == 0
    finally:
        # Clean up both test projects
        await vector_store.delete_project(prj_a)
        await vector_store.delete_project(prj_b)
