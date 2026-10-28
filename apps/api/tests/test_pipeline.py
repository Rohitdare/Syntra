"""Unit tests for PipelineOrchestrator and run_stage (Phase 2.5)."""

from __future__ import annotations

import tempfile
import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from research_desk.agents.collector import CollectorInput
from research_desk.core.errors import AppError
from research_desk.orchestrator.events import EventSink
from research_desk.orchestrator.jobs import JobService
from research_desk.orchestrator.pipeline import (
    PipelineOrchestrator,
    create_stage_callable,
    run_stage,
)
from research_desk.orchestrator.runner import JobRunner
from research_desk.providers.llm import CallContext
from research_desk.stores.models import Job, Source


@pytest.fixture
def mock_sessionmaker() -> MagicMock:
    session = AsyncMock()
    session.begin = MagicMock()
    session.begin.return_value.__aenter__.return_value = AsyncMock()
    session.begin.return_value.__aexit__.return_value = None
    sm = MagicMock()
    sm.return_value.__aenter__.return_value = session
    sm.return_value.__aexit__.return_value = None
    return sm


@pytest.mark.asyncio
async def test_run_stage_collect_success() -> None:
    """run_stage('collect') invokes collector and cleans up temp files."""
    # Create a real temp file simulating a PDF
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tf:
        tf.write(b"%PDF-1.4 minimal test content")
        pdf_path = tf.name

    events: list[tuple[str, dict[str, Any] | None, str | None]] = []

    async def mock_emit(evt_type: str, data: dict[str, Any] | None, msg: str | None) -> None:
        events.append((evt_type, data, msg))

    # Mock collector run
    mock_output = MagicMock()
    mock_output.model_dump.return_value = {
        "sourceId": "src_test1234",
        "tag": "S1",
        "title": "Test PDF",
        "kind": "pdf",
        "chunkCount": 5,
        "charCount": 1200,
        "alreadyExisted": False,
    }

    mock_deps = MagicMock()
    ctx = CallContext(user_id=uuid.uuid4(), project_id="prj_test001", job_id=uuid.uuid4())
    inp = CollectorInput(project_id="prj_test001", kind="pdf", pdf_path=pdf_path)

    import os
    from unittest.mock import patch

    with patch(
        "research_desk.orchestrator.pipeline.collector.run",
        AsyncMock(return_value=mock_output),
    ):
        result = await run_stage("collect", inp, mock_deps, mock_emit, ctx)

    assert result["sourceId"] == "src_test1234"
    assert result["tag"] == "S1"
    # Temp file should be removed
    assert not os.path.exists(pdf_path)


@pytest.mark.asyncio
async def test_run_stage_collect_cleans_temp_file_on_failure() -> None:
    """Temporary PDF file is cleaned up even when collector raises an error."""
    import os

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tf:
        tf.write(b"%PDF-1.4 fail content")
        pdf_path = tf.name

    async def mock_emit(evt_type: str, data: dict[str, Any] | None, msg: str | None) -> None:
        pass

    mock_deps = MagicMock()
    ctx = CallContext(user_id=uuid.uuid4(), project_id="prj_test001")
    inp = CollectorInput(project_id="prj_test001", kind="pdf", pdf_path=pdf_path)

    from unittest.mock import patch

    with patch(
        "research_desk.orchestrator.pipeline.collector.run",
        AsyncMock(side_effect=AppError("BAD_REQUEST", "Extraction failed")),
    ):
        with pytest.raises(AppError):
            await run_stage("collect", inp, mock_deps, mock_emit, ctx)

    assert not os.path.exists(pdf_path)


@pytest.mark.asyncio
async def test_run_stage_prerequisite_validations() -> None:
    """Analyze and critique stages validate prerequisite state before execution."""
    mock_deps = MagicMock()
    mock_deps.repos.sources.get = AsyncMock()
    ctx = CallContext(user_id=uuid.uuid4(), project_id="prj_test001")

    async def mock_emit(t: str, d: dict[str, Any] | None, m: str | None) -> None:
        pass

    # 1. Analyze fails if source is not collected
    uncollected = Source(
        project_id="prj_test001",
        id="src_001",
        tag="S1",
        kind="text",
        title="Test",
        origin="test",
        content_hash="h1",
        stage_collected=False,
    )
    mock_deps.repos.sources.get.return_value = uncollected

    with pytest.raises(AppError) as exc_info:
        await run_stage("analyze", {"source_id": "src_001"}, mock_deps, mock_emit, ctx)
    assert exc_info.value.code == "BAD_REQUEST"
    assert "must be collected" in str(exc_info.value.message)

    # 2. Critique fails if source is not analyzed
    collected_not_analyzed = Source(
        project_id="prj_test001",
        id="src_001",
        tag="S1",
        kind="text",
        title="Test",
        origin="test",
        content_hash="h1",
        stage_collected=True,
        stage_analyzed=False,
    )
    mock_deps.repos.sources.get.return_value = collected_not_analyzed

    with pytest.raises(AppError) as exc_info:
        await run_stage("critique", {"source_id": "src_001"}, mock_deps, mock_emit, ctx)
    assert exc_info.value.code == "BAD_REQUEST"
    assert "must be analyzed" in str(exc_info.value.message)

    # 3. Unknown stage raises BAD_REQUEST
    with pytest.raises(AppError) as exc_info:
        await run_stage("invalid_stage", {}, mock_deps, mock_emit, ctx)
    assert exc_info.value.code == "BAD_REQUEST"
    assert "Unknown pipeline stage" in str(exc_info.value.message)


@pytest.mark.asyncio
async def test_pipeline_orchestrator_run_job_new_submission(mock_sessionmaker: MagicMock) -> None:
    """PipelineOrchestrator creates a new job and submits it to the runner."""
    mock_job_service = MagicMock(spec=JobService)
    job_id = uuid.uuid4()
    new_job = Job(
        id=job_id,
        project_id="prj_test001",
        user_id=uuid.uuid4(),
        stage="collect",
        status="queued",
        input_hash="hash123",
    )
    mock_job_service.create_or_join_job = AsyncMock(return_value=(new_job, True))

    mock_runner = MagicMock(spec=JobRunner)
    mock_runner.submit = AsyncMock()

    mock_event_sink = MagicMock(spec=EventSink)
    mock_vectors = MagicMock()
    mock_embeddings = MagicMock()

    orchestrator = PipelineOrchestrator(
        sessionmaker=mock_sessionmaker,
        vectors=mock_vectors,
        embeddings=mock_embeddings,
        job_service=mock_job_service,
        runner=mock_runner,
        event_sink=mock_event_sink,
    )

    job, is_new = await orchestrator.run_job(
        stage="collect",
        project_id="prj_test001",
        user_id=new_job.user_id,
        inp=CollectorInput(project_id="prj_test001", kind="text", text="sample text"),
        input_hash="hash123",
    )

    assert is_new is True
    assert job.id == job_id
    mock_runner.submit.assert_awaited_once()


@pytest.mark.asyncio
async def test_pipeline_orchestrator_single_flight_join(mock_sessionmaker: MagicMock) -> None:
    """Second concurrent call joins existing active job and does not submit to runner."""
    mock_job_service = MagicMock(spec=JobService)
    job_id = uuid.uuid4()
    existing_job = Job(
        id=job_id,
        project_id="prj_test001",
        user_id=uuid.uuid4(),
        stage="collect",
        status="running",
        input_hash="hash123",
    )
    # create_or_join_job returns is_new = False
    mock_job_service.create_or_join_job = AsyncMock(return_value=(existing_job, False))

    mock_runner = MagicMock(spec=JobRunner)
    mock_runner.submit = AsyncMock()

    mock_event_sink = MagicMock(spec=EventSink)

    orchestrator = PipelineOrchestrator(
        sessionmaker=mock_sessionmaker,
        vectors=MagicMock(),
        embeddings=MagicMock(),
        job_service=mock_job_service,
        runner=mock_runner,
        event_sink=mock_event_sink,
    )

    job, is_new = await orchestrator.run_job(
        stage="collect",
        project_id="prj_test001",
        user_id=existing_job.user_id,
        inp=CollectorInput(project_id="prj_test001", kind="text", text="sample text"),
        input_hash="hash123",
    )

    assert is_new is False
    assert job.id == job_id
    # Runner submit should NOT be called for joined job
    mock_runner.submit.assert_not_awaited()


@pytest.mark.asyncio
async def test_create_stage_callable_emits_mapped_wire_events(mock_sessionmaker: MagicMock) -> None:
    """create_stage_callable maps agent internal events to wire event types."""
    job_id = uuid.uuid4()
    ctx = CallContext(user_id=uuid.uuid4(), project_id="prj_test001", job_id=job_id)
    mock_event_sink = MagicMock(spec=EventSink)
    mock_event_sink.emit = AsyncMock()

    stage_coro = create_stage_callable(
        stage="collect",
        inp=CollectorInput(
            project_id="prj_test001",
            kind="text",
            text="Deterministic testing text.\n\n" + ("Lots of paragraphs.\n" * 25),
        ),
        ctx=ctx,
        sessionmaker=mock_sessionmaker,
        vectors=MagicMock(),
        embeddings=MagicMock(),
    )

    # Run the stage coro with mock collector run
    from unittest.mock import patch

    mock_out = MagicMock()
    mock_out.model_dump.return_value = {"sourceId": "src_1", "tag": "S1"}

    async def fake_collector_run(inp: Any, deps: Any, emit: Any, ctx: Any) -> Any:
        await emit("start", None, "Starting")
        await emit("status", None, "Working")
        await emit("result", {"data": 1}, "Done")
        await emit("complete", None, "Finish")
        return mock_out

    with patch("research_desk.orchestrator.pipeline.collector.run", side_effect=fake_collector_run):
        res = await stage_coro(mock_event_sink)

    assert res == {"sourceId": "src_1", "tag": "S1"}

    # Verify event types sent to event_sink
    emitted_types = [call.kwargs.get("type_") for call in mock_event_sink.emit.call_args_list]
    # start -> stage_start, status -> step, result -> result, complete -> ignored
    assert emitted_types == ["stage_start", "step", "result"]
