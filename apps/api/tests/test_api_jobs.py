"""Unit tests for Job status and event streaming routes (/api/jobs)."""

from __future__ import annotations

import datetime
import json
import uuid
from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient

from research_desk.api.auth import get_current_user
from research_desk.api.dependencies import get_event_sink
from research_desk.core.config import Settings
from research_desk.main import create_app
from research_desk.orchestrator.events import EventMessage, EventSink
from research_desk.stores.db import get_db
from research_desk.stores.models import Job, User


def get_test_settings() -> Settings:
    return Settings(
        GEMINI_API_KEY="test-key",
        DATABASE_URL="postgresql://user:pass@localhost:5432/testdb",
        QDRANT_URL="http://localhost:6333",
        APP_ENV="local",
        AUTH_MODE="dev",
    )


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
async def test_get_job_status_owned_success(test_user: User) -> None:
    """GET /api/jobs/{job_id} returns JobStatusResponse with operational status and lastSeq."""
    app = create_app(get_test_settings())
    mock_session = AsyncMock()

    job_id = uuid.uuid4()
    now = datetime.datetime.now(datetime.timezone.utc)
    job = Job(
        id=job_id,
        project_id="prj_001",
        source_id="src_001",
        user_id=test_user.id,
        stage="analyze",
        status="running",
        input_hash="hash123",
        started_at=now,
        finished_at=None,
    )

    app.dependency_overrides[get_current_user] = lambda: test_user
    app.dependency_overrides[get_db] = lambda: mock_session

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            "research_desk.api.routes.jobs.JobRepo.get",
            AsyncMock(return_value=job),
        )
        mp.setattr(
            "research_desk.api.routes.jobs.JobRepo.get_last_seq",
            AsyncMock(return_value=7),
        )

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get(f"/api/jobs/{job_id}")

    assert resp.status_code == 200
    data = resp.json()
    assert data["jobId"] == str(job_id)
    assert data["projectId"] == "prj_001"
    assert data["sourceId"] == "src_001"
    assert data["stage"] == "analyze"
    assert data["status"] == "running"
    assert data["lastSeq"] == 7
    assert data["startedAt"] is not None
    assert data["finishedAt"] is None


@pytest.mark.asyncio
async def test_get_job_status_foreign_404(foreign_user: User) -> None:
    """GET /api/jobs/{job_id} returns 404 NOT_FOUND if job belongs to another user."""
    app = create_app(get_test_settings())
    mock_session = AsyncMock()

    job_id = uuid.uuid4()
    job = Job(
        id=job_id,
        project_id="prj_001",
        source_id="src_001",
        user_id=uuid.UUID("00000000-0000-0000-0000-000000000001"),  # Different user
        stage="analyze",
        status="running",
        input_hash="hash123",
    )

    app.dependency_overrides[get_current_user] = lambda: foreign_user
    app.dependency_overrides[get_db] = lambda: mock_session

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            "research_desk.api.routes.jobs.JobRepo.get",
            AsyncMock(return_value=job),
        )

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get(f"/api/jobs/{job_id}")

    assert resp.status_code == 404
    data = resp.json()
    assert data["error"]["code"] == "NOT_FOUND"


@pytest.mark.asyncio
async def test_stream_job_events_replay_and_terminate(test_user: User) -> None:
    """GET /api/jobs/{job_id}/events streams NDJSON events and finishes cleanly."""
    app = create_app(get_test_settings())
    mock_session = AsyncMock()

    job_id = uuid.uuid4()
    job = Job(
        id=job_id,
        project_id="prj_001",
        source_id="src_001",
        user_id=test_user.id,
        stage="collect",
        status="succeeded",
        input_hash="hash123",
    )

    now = datetime.datetime.now(datetime.timezone.utc)
    events = [
        EventMessage(
            job_id=job_id,
            seq=1,
            ts=now,
            stage="collect",
            agent="collector",
            type="stage_start",
            message="Starting collection",
        ),
        EventMessage(
            job_id=job_id,
            seq=2,
            ts=now,
            stage="collect",
            agent="collector",
            type="doc_write",
            message="Saved chunks",
            data={"count": 5},
        ),
        EventMessage(
            job_id=job_id,
            seq=3,
            ts=now,
            stage="collect",
            agent="system",
            type="stage_end",
            message="Finished",
            data={"status": "succeeded"},
        ),
    ]

    async def fake_subscribe(
        jid: uuid.UUID, since_seq: int = 0
    ) -> AsyncGenerator[EventMessage, None]:
        for e in events:
            if e.seq > since_seq:
                yield e

    mock_event_sink = AsyncMock(spec=EventSink)
    mock_event_sink.subscribe = fake_subscribe

    app.dependency_overrides[get_current_user] = lambda: test_user
    app.dependency_overrides[get_db] = lambda: mock_session
    app.dependency_overrides[get_event_sink] = lambda: mock_event_sink

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            "research_desk.api.routes.jobs.JobRepo.get",
            AsyncMock(return_value=job),
        )

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get(f"/api/jobs/{job_id}/events?after=0")

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/x-ndjson")
    assert resp.headers["X-Job-Id"] == str(job_id)

    lines = [json.loads(line) for line in resp.text.strip().split("\n") if line]
    assert len(lines) == 3
    assert lines[0]["seq"] == 1
    assert lines[0]["type"] == "stage_start"
    assert lines[1]["seq"] == 2
    assert lines[2]["seq"] == 3
    assert lines[2]["type"] == "stage_end"


@pytest.mark.asyncio
async def test_stream_job_events_with_after_cursor(test_user: User) -> None:
    """GET /api/jobs/{job_id}/events?after=2 replays only events with seq > 2."""
    app = create_app(get_test_settings())
    mock_session = AsyncMock()

    job_id = uuid.uuid4()
    job = Job(
        id=job_id,
        project_id="prj_001",
        user_id=test_user.id,
        stage="analyze",
        status="succeeded",
        input_hash="hash123",
    )

    now = datetime.datetime.now(datetime.timezone.utc)
    ev3 = EventMessage(
        job_id=job_id,
        seq=3,
        ts=now,
        stage="analyze",
        agent="analyst",
        type="step",
        message="Analyzing chunk 3",
    )
    ev4 = EventMessage(
        job_id=job_id,
        seq=4,
        ts=now,
        stage="analyze",
        agent="system",
        type="stage_end",
        message="Done",
        data={"status": "succeeded"},
    )

    async def fake_subscribe(
        jid: uuid.UUID, since_seq: int = 0
    ) -> AsyncGenerator[EventMessage, None]:
        assert since_seq == 2
        yield ev3
        yield ev4

    mock_event_sink = AsyncMock(spec=EventSink)
    mock_event_sink.subscribe = fake_subscribe

    app.dependency_overrides[get_current_user] = lambda: test_user
    app.dependency_overrides[get_db] = lambda: mock_session
    app.dependency_overrides[get_event_sink] = lambda: mock_event_sink

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            "research_desk.api.routes.jobs.JobRepo.get",
            AsyncMock(return_value=job),
        )

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get(f"/api/jobs/{job_id}/events?after=2")

    assert resp.status_code == 200
    lines = [json.loads(line) for line in resp.text.strip().split("\n") if line]
    assert len(lines) == 2
    assert lines[0]["seq"] == 3
    assert lines[1]["seq"] == 4


@pytest.mark.asyncio
async def test_stream_job_events_foreign_404(foreign_user: User) -> None:
    """GET /api/jobs/{job_id}/events returns 404 NOT_FOUND for foreign job."""
    app = create_app(get_test_settings())
    mock_session = AsyncMock()

    job_id = uuid.uuid4()
    job = Job(
        id=job_id,
        project_id="prj_001",
        user_id=uuid.UUID("00000000-0000-0000-0000-000000000001"),  # Other user
        stage="collect",
        status="running",
        input_hash="hash123",
    )

    app.dependency_overrides[get_current_user] = lambda: foreign_user
    app.dependency_overrides[get_db] = lambda: mock_session

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            "research_desk.api.routes.jobs.JobRepo.get",
            AsyncMock(return_value=job),
        )

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get(f"/api/jobs/{job_id}/events")

    assert resp.status_code == 404
    data = resp.json()
    assert data["error"]["code"] == "NOT_FOUND"
