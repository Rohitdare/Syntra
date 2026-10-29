"""Unit tests for InProcessRunner active cap, timeouts, and detached execution."""

from __future__ import annotations

import asyncio
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from research_desk.core.errors import AppError
from research_desk.orchestrator.events import EventSink
from research_desk.orchestrator.runner import InProcessRunner
from research_desk.stores.models import Job


@pytest.fixture(autouse=True)
def mock_job_repo_ops():
    """Mock JobRepo update and heartbeat operations so runner logic is isolated."""
    with (
        patch("research_desk.orchestrator.runner.JobRepo.update_status", new=AsyncMock()),
        patch("research_desk.orchestrator.runner.JobRepo.heartbeat", new=AsyncMock()),
        patch("research_desk.orchestrator.runner.JobRepo.get", new=AsyncMock(return_value=None)),
    ):
        yield


@pytest.fixture
def mock_sessionmaker() -> MagicMock:
    """Mock sessionmaker providing an async context manager session."""
    session = AsyncMock()
    session.begin = MagicMock(return_value=AsyncMock())
    sm = MagicMock()
    sm.return_value.__aenter__.return_value = session
    sm.return_value.__aexit__.return_value = None
    return sm


@pytest.mark.asyncio
async def test_runner_active_cap_enforcement(mock_sessionmaker: MagicMock) -> None:
    """Submitting more jobs than active_cap raises 503 OVERLOADED."""
    event_sink = MagicMock(spec=EventSink)
    event_sink.emit = AsyncMock()

    runner = InProcessRunner(
        sessionmaker=mock_sessionmaker,
        event_sink=event_sink,
        active_cap=2,
        stage_timeout_s=10.0,
    )

    async def blocking_stage(sink: EventSink) -> dict[str, str]:
        await asyncio.sleep(5.0)
        return {"status": "ok"}

    job_1 = uuid.uuid4()
    job_2 = uuid.uuid4()
    job_3 = uuid.uuid4()

    # Submit 2 jobs to fill the cap
    await runner.submit(job_1, blocking_stage)
    await runner.submit(job_2, blocking_stage)

    # 3rd job must fail with 503 OVERLOADED
    with pytest.raises(AppError) as exc_info:
        await runner.submit(job_3, blocking_stage)

    assert exc_info.value.code == "OVERLOADED"
    assert exc_info.value.http_status == 503
    assert exc_info.value.retryable is True

    await runner.shutdown()


@pytest.mark.asyncio
async def test_runner_stage_timeout(mock_sessionmaker: MagicMock) -> None:
    """A stage exceeding stage_timeout_s is marked TIMEOUT."""
    event_sink = MagicMock(spec=EventSink)
    event_sink.emit = AsyncMock()

    runner = InProcessRunner(
        sessionmaker=mock_sessionmaker,
        event_sink=event_sink,
        active_cap=2,
        stage_timeout_s=0.1,  # Fast timeout for test
        lease_seconds=5,
    )

    async def slow_stage(sink: EventSink) -> dict[str, str]:
        await asyncio.sleep(2.0)
        return {"status": "ok"}

    job_id = uuid.uuid4()
    await runner.submit(job_id, slow_stage)

    # Wait for the job task to complete and handle timeout
    await asyncio.sleep(0.3)

    # Verify event_sink emitted TIMEOUT error
    emitted_types = [call.kwargs.get("type_") for call in event_sink.emit.call_args_list]
    assert "error" in emitted_types
    assert "stage_end" in emitted_types

    await runner.shutdown()


@pytest.mark.asyncio
async def test_runner_updates_source_last_error_on_failure(mock_sessionmaker: MagicMock) -> None:
    """When a job fails, the runner updates source.last_error with the error code."""
    event_sink = MagicMock(spec=EventSink)
    event_sink.emit = AsyncMock()

    runner = InProcessRunner(
        sessionmaker=mock_sessionmaker,
        event_sink=event_sink,
        active_cap=2,
        stage_timeout_s=5.0,
    )

    job_id = uuid.uuid4()
    mock_job = Job(
        id=job_id,
        project_id="prj_test001",
        source_id="src_test001",
        user_id=uuid.uuid4(),
        stage="analyze",
        status="running",
        input_hash="hash_1",
    )

    async def failing_stage(sink: EventSink) -> dict[str, str]:
        raise AppError("LLM_QUOTA", "Quota exceeded", http_status=503, retryable=True)

    with (
        patch("research_desk.orchestrator.runner.JobRepo.get", AsyncMock(return_value=mock_job)),
        patch(
            "research_desk.stores.repos.sources.SourceRepo.update_stage_flags",
            AsyncMock(),
        ) as mock_update_flags,
    ):
        await runner.submit(job_id, failing_stage)
        await asyncio.sleep(0.1)

    mock_update_flags.assert_awaited_once_with(
        project_id="prj_test001",
        source_id="src_test001",
        last_error="LLM_QUOTA",
    )
    await runner.shutdown()


@pytest.mark.asyncio
async def test_runner_clears_source_last_error_on_success(mock_sessionmaker: MagicMock) -> None:
    """When a job succeeds, the runner clears source.last_error to None."""
    event_sink = MagicMock(spec=EventSink)
    event_sink.emit = AsyncMock()

    runner = InProcessRunner(
        sessionmaker=mock_sessionmaker,
        event_sink=event_sink,
        active_cap=2,
        stage_timeout_s=5.0,
    )

    job_id = uuid.uuid4()
    mock_job = Job(
        id=job_id,
        project_id="prj_test001",
        source_id="src_test001",
        user_id=uuid.uuid4(),
        stage="analyze",
        status="running",
        input_hash="hash_1",
    )

    async def successful_stage(sink: EventSink) -> dict[str, str]:
        return {"claimCount": "3"}

    with (
        patch("research_desk.orchestrator.runner.JobRepo.get", AsyncMock(return_value=mock_job)),
        patch(
            "research_desk.stores.repos.sources.SourceRepo.update_stage_flags",
            AsyncMock(),
        ) as mock_update_flags,
    ):
        await runner.submit(job_id, successful_stage)
        await asyncio.sleep(0.1)

    mock_update_flags.assert_awaited_once_with(
        project_id="prj_test001",
        source_id="src_test001",
        last_error=None,
    )
    await runner.shutdown()
