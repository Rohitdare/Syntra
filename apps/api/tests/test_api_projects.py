"""Unit tests for Project API routes (/api/projects)."""

from __future__ import annotations

import datetime
import uuid
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient

from research_desk.api.auth import get_current_user, get_owned_project
from research_desk.api.dependencies import get_vector_store, reset_dependencies
from research_desk.core.config import Settings
from research_desk.main import create_app
from research_desk.stores.db import get_db
from research_desk.stores.models import Project, Source, User
from research_desk.stores.vector import VectorStore


def get_test_settings() -> Settings:
    return Settings(
        GEMINI_API_KEY="test-key",
        DATABASE_URL="postgresql://user:pass@localhost:5432/testdb",
        QDRANT_URL="http://localhost:6333",
        APP_ENV="local",
        AUTH_MODE="dev",
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
def foreign_user() -> User:
    return User(
        id=uuid.UUID("00000000-0000-0000-0000-000000000002"),
        auth_subject="foreign-user",
        email="foreign@example.com",
    )


@pytest.mark.asyncio
async def test_create_project_success(test_user: User) -> None:
    """POST /api/projects creates a project and returns 201 with projectId."""
    app = create_app(get_test_settings())
    mock_session = AsyncMock()

    app.dependency_overrides[get_current_user] = lambda: test_user
    app.dependency_overrides[get_db] = lambda: mock_session

    created_project = Project(
        id="prj_11223344",
        owner_id=test_user.id,
        name="Quantum Computing",
        description="Literature review",
        status="active",
        next_source_tag=1,
    )

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            "research_desk.api.routes.projects.ProjectRepo.create",
            AsyncMock(return_value=created_project),
        )

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/api/projects",
                json={"name": "Quantum Computing", "description": "Literature review"},
            )

    assert resp.status_code == 201
    data = resp.json()
    assert data["projectId"] == "prj_11223344"
    assert "X-Request-Id" in resp.headers


@pytest.mark.asyncio
async def test_create_project_validation_error(test_user: User) -> None:
    """POST /api/projects with invalid name (empty or too long) returns 400 BAD_REQUEST."""
    app = create_app(get_test_settings())
    mock_session = AsyncMock()
    app.dependency_overrides[get_current_user] = lambda: test_user
    app.dependency_overrides[get_db] = lambda: mock_session

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Empty name
        resp = await client.post("/api/projects", json={"name": ""})
        assert resp.status_code == 400
        assert resp.json()["error"]["code"] == "BAD_REQUEST"

        # Over 80 chars
        resp_long = await client.post("/api/projects", json={"name": "A" * 81})
        assert resp_long.status_code == 400
        assert resp_long.json()["error"]["code"] == "BAD_REQUEST"


@pytest.mark.asyncio
async def test_list_projects(test_user: User) -> None:
    """GET /api/projects lists active projects for owner with source counts."""
    app = create_app(get_test_settings())
    mock_session = AsyncMock()

    app.dependency_overrides[get_current_user] = lambda: test_user
    app.dependency_overrides[get_db] = lambda: mock_session

    now = datetime.datetime.now(datetime.timezone.utc)
    proj1 = Project(
        id="prj_001",
        owner_id=test_user.id,
        name="Project One",
        description="First project",
        status="active",
        created_at=now,
        updated_at=now,
    )
    proj2 = Project(
        id="prj_002",
        owner_id=test_user.id,
        name="Project Two",
        description=None,
        status="active",
        created_at=now,
        updated_at=now,
    )

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            "research_desk.api.routes.projects.ProjectRepo.list_for_owner_with_source_counts",
            AsyncMock(return_value=[(proj1, 3), (proj2, 0)]),
        )

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/projects")

    assert resp.status_code == 200
    data = resp.json()
    assert "projects" in data
    assert len(data["projects"]) == 2
    assert data["projects"][0]["id"] == "prj_001"
    assert data["projects"][0]["sourceCount"] == 3
    assert data["projects"][1]["id"] == "prj_002"
    assert data["projects"][1]["sourceCount"] == 0


@pytest.mark.asyncio
async def test_get_project_detail(test_user: User) -> None:
    """GET /api/projects/{project_id} returns detail view with sources and active jobs."""
    app = create_app(get_test_settings())
    mock_session = AsyncMock()

    now = datetime.datetime.now(datetime.timezone.utc)
    project = Project(
        id="prj_detail01",
        owner_id=test_user.id,
        name="Detailed Study",
        description="Deep dive",
        status="active",
        created_at=now,
        updated_at=now,
    )
    source = Source(
        project_id="prj_detail01",
        id="src_001",
        tag="S1",
        kind="pdf",
        title="Sample Paper",
        origin="sample.pdf",
        content_hash="hash123",
        char_count=5000,
        chunk_count=4,
        claim_count=2,
        stage_collected=True,
        stage_analyzed=True,
        stage_critiqued=False,
        last_error=None,
    )

    app.dependency_overrides[get_current_user] = lambda: test_user
    app.dependency_overrides[get_db] = lambda: mock_session
    app.dependency_overrides[get_owned_project] = lambda: project

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            "research_desk.api.routes.projects.SourceRepo.list_by_project",
            AsyncMock(return_value=[source]),
        )
        mp.setattr(
            "research_desk.api.routes.projects.JobRepo.list_active_for_project",
            AsyncMock(return_value=[]),
        )

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/projects/prj_detail01")

    assert resp.status_code == 200
    data = resp.json()
    assert data["project"]["id"] == "prj_detail01"
    assert data["project"]["name"] == "Detailed Study"
    assert len(data["sources"]) == 1
    assert data["sources"][0]["id"] == "src_001"
    assert data["sources"][0]["stages"]["collected"] is True
    assert data["sources"][0]["stages"]["critiqued"] is False
    assert data["activeJobs"] == []


@pytest.mark.asyncio
async def test_get_project_foreign_404(foreign_user: User) -> None:
    """GET /api/projects/{project_id} returns 404 for project not owned by user."""
    app = create_app(get_test_settings())
    mock_session = AsyncMock()

    app.dependency_overrides[get_current_user] = lambda: foreign_user
    app.dependency_overrides[get_db] = lambda: mock_session

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            "research_desk.api.auth.ProjectRepo.get_owned",
            AsyncMock(return_value=None),
        )

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/projects/prj_other_user")

    assert resp.status_code == 404
    data = resp.json()
    assert data["error"]["code"] == "NOT_FOUND"


@pytest.mark.asyncio
async def test_delete_project_active_job_conflict(test_user: User) -> None:
    """DELETE /api/projects/{project_id} rejects with 409 JOB_ACTIVE if a job is running."""
    app = create_app(get_test_settings())
    mock_session = AsyncMock()

    project = Project(
        id="prj_active_run",
        owner_id=test_user.id,
        name="Active Job Project",
        status="active",
    )

    app.dependency_overrides[get_current_user] = lambda: test_user
    app.dependency_overrides[get_db] = lambda: mock_session
    app.dependency_overrides[get_owned_project] = lambda: project

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            "research_desk.api.routes.projects.JobRepo.has_active_for_project",
            AsyncMock(return_value=True),
        )

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.delete("/api/projects/prj_active_run")

    assert resp.status_code == 409
    data = resp.json()
    assert data["error"]["code"] == "JOB_ACTIVE"


@pytest.mark.asyncio
async def test_delete_project_vector_error(test_user: User) -> None:
    """DELETE /api/projects/{project_id} returns 503 VECTOR_DB_ERROR if vector deletion fails."""
    app = create_app(get_test_settings())
    mock_session = AsyncMock()
    mock_vectors = AsyncMock(spec=VectorStore)
    mock_vectors.delete_project.side_effect = RuntimeError("Qdrant node connection lost")

    project = Project(
        id="prj_qdrant_fail",
        owner_id=test_user.id,
        name="Qdrant Failure",
        status="active",
    )

    app.dependency_overrides[get_current_user] = lambda: test_user
    app.dependency_overrides[get_db] = lambda: mock_session
    app.dependency_overrides[get_owned_project] = lambda: project
    app.dependency_overrides[get_vector_store] = lambda: mock_vectors

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            "research_desk.api.routes.projects.JobRepo.has_active_for_project",
            AsyncMock(return_value=False),
        )
        mp.setattr(
            "research_desk.api.routes.projects.SourceRepo.count_by_project",
            AsyncMock(return_value=2),
        )
        mp.setattr(
            "research_desk.api.routes.projects.ProjectRepo.mark_deleting",
            AsyncMock(),
        )

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.delete("/api/projects/prj_qdrant_fail")

    assert resp.status_code == 503
    data = resp.json()
    assert data["error"]["code"] == "VECTOR_DB_ERROR"


@pytest.mark.asyncio
async def test_delete_project_success(test_user: User) -> None:
    """DELETE /api/projects/{project_id} succeeds, purges Qdrant and deletes PostgreSQL rows."""
    app = create_app(get_test_settings())
    mock_session = AsyncMock()
    mock_vectors = AsyncMock(spec=VectorStore)

    project = Project(
        id="prj_to_delete",
        owner_id=test_user.id,
        name="Clean Delete",
        status="active",
    )

    app.dependency_overrides[get_current_user] = lambda: test_user
    app.dependency_overrides[get_db] = lambda: mock_session
    app.dependency_overrides[get_owned_project] = lambda: project
    app.dependency_overrides[get_vector_store] = lambda: mock_vectors

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            "research_desk.api.routes.projects.JobRepo.has_active_for_project",
            AsyncMock(return_value=False),
        )
        mp.setattr(
            "research_desk.api.routes.projects.SourceRepo.count_by_project",
            AsyncMock(return_value=3),
        )
        mp.setattr(
            "research_desk.api.routes.projects.ProjectRepo.mark_deleting",
            AsyncMock(),
        )
        mp.setattr(
            "research_desk.api.routes.projects.ProjectRepo.delete",
            AsyncMock(),
        )

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.delete("/api/projects/prj_to_delete")

    assert resp.status_code == 200
    data = resp.json()
    assert data["deleted"] == 4  # 1 project + 3 sources
    mock_vectors.delete_project.assert_awaited_once_with("prj_to_delete")
