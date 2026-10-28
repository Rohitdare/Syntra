"""Unit tests for EventSink streaming, reconnection, and replay (Phase 2.5)."""

from __future__ import annotations

import asyncio
import datetime
import uuid
from typing import Any

import pytest

from research_desk.orchestrator.events import EventMessage, EventSink
from research_desk.stores.models import Job, JobEvent


class FakeJobRepo:
    """In-memory JobRepo simulation for EventSink tests."""

    def __init__(self) -> None:
        self.events: list[JobEvent] = []
        self.jobs: dict[uuid.UUID, Job] = {}

    async def add_event(
        self,
        job_id: uuid.UUID,
        stage: str,
        agent: str,
        type_: str,
        message: str | None = None,
        data: dict | None = None,
    ) -> JobEvent:
        next_seq = len(self.events) + 1
        ev = JobEvent(
            job_id=job_id,
            seq=next_seq,
            ts=datetime.datetime.now(datetime.timezone.utc),
            stage=stage,
            agent=agent,
            type=type_,
            message=message,
            data=data,
        )
        self.events.append(ev)
        return ev

    async def get_events(self, job_id: uuid.UUID, since_seq: int = 0) -> list[JobEvent]:
        return [e for e in self.events if e.job_id == job_id and e.seq > since_seq]

    async def get(self, job_id: uuid.UUID) -> Job | None:
        return self.jobs.get(job_id)


class MockAsyncContextManager:
    def __init__(self, target: Any = None) -> None:
        self.target = target

    async def __aenter__(self) -> Any:
        return self.target

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        return None


class FakeSession:
    def begin(self) -> MockAsyncContextManager:
        return MockAsyncContextManager()


@pytest.fixture
def fake_event_setup() -> tuple[EventSink, FakeJobRepo]:
    fake_repo = FakeJobRepo()

    def fake_sessionmaker() -> MockAsyncContextManager:
        return MockAsyncContextManager(FakeSession())

    from unittest.mock import patch

    # Mock JobRepo instantiated inside EventSink to use fake_repo
    patcher = patch("research_desk.orchestrator.events.JobRepo", return_value=fake_repo)
    patcher.start()

    sink = EventSink(sessionmaker=fake_sessionmaker)  # type: ignore[arg-type]
    return sink, fake_repo


@pytest.mark.asyncio
async def test_event_message_to_dict_contract() -> None:
    """EventMessage wire dict contains jobId and matches docs/05-API-SPEC.md Section 3."""
    job_id = uuid.uuid4()
    now = datetime.datetime.now(datetime.timezone.utc)
    msg = EventMessage(
        job_id=job_id,
        seq=3,
        ts=now,
        stage="collect",
        agent="collector",
        type="step",
        message="Reading chunks",
        data={"count": 5},
    )

    d = msg.to_dict()
    assert d["jobId"] == str(job_id)
    assert d["seq"] == 3
    assert d["ts"] == now.isoformat()
    assert d["stage"] == "collect"
    assert d["agent"] == "collector"
    assert d["type"] == "step"
    assert d["message"] == "Reading chunks"
    assert d["data"] == {"count": 5}


@pytest.mark.asyncio
async def test_event_sink_heartbeat_does_not_consume_seq(
    fake_event_setup: tuple[EventSink, FakeJobRepo],
) -> None:
    """Heartbeat events do not insert rows in the database and carry the last real seq."""
    sink, fake_repo = fake_event_setup
    job_id = uuid.uuid4()

    # Emit 2 real events
    ev1 = await sink.emit(job_id, "collect", "collector", "stage_start")
    assert ev1.seq == 1

    ev2 = await sink.emit(job_id, "collect", "collector", "step", message="Parsing")
    assert ev2.seq == 2
    assert len(fake_repo.events) == 2

    # Emit a heartbeat
    hb = await sink.emit(job_id, "system", "runner", "heartbeat")
    assert hb.type == "heartbeat"
    assert hb.seq == 2  # Carries last real seq
    # No row added to database events table
    assert len(fake_repo.events) == 2

    # Next real event gets seq 3
    ev3 = await sink.emit(job_id, "collect", "collector", "result")
    assert ev3.seq == 3
    assert len(fake_repo.events) == 3


@pytest.mark.asyncio
async def test_event_sink_live_streaming_and_fan_out(
    fake_event_setup: tuple[EventSink, FakeJobRepo],
) -> None:
    """EventSink streams live events to multiple concurrent subscribers."""
    sink, _ = fake_event_setup
    job_id = uuid.uuid4()

    events_sub1: list[EventMessage] = []
    events_sub2: list[EventMessage] = []

    async def subscriber1() -> None:
        async for msg in sink.subscribe(job_id):
            events_sub1.append(msg)

    async def subscriber2() -> None:
        async for msg in sink.subscribe(job_id):
            events_sub2.append(msg)

    t1 = asyncio.create_task(subscriber1())
    t2 = asyncio.create_task(subscriber2())

    # Wait for subscribers to register
    await asyncio.sleep(0.05)

    await sink.emit(job_id, "collect", "collector", "stage_start")
    await sink.emit(job_id, "collect", "collector", "step", message="Ingesting")
    await sink.emit(job_id, "system", "runner", "stage_end")

    await asyncio.gather(t1, t2)

    assert len(events_sub1) == 3
    assert len(events_sub2) == 3
    assert [e.type for e in events_sub1] == ["stage_start", "step", "stage_end"]
    assert [e.type for e in events_sub2] == ["stage_start", "step", "stage_end"]


@pytest.mark.asyncio
async def test_event_sink_resumable_replay_with_since_seq(
    fake_event_setup: tuple[EventSink, FakeJobRepo],
) -> None:
    """Subscriber replaying with since_seq receives only events after that sequence number."""
    sink, fake_repo = fake_event_setup
    job_id = uuid.uuid4()

    # Pre-emit events into database
    await sink.emit(job_id, "collect", "collector", "stage_start")  # seq 1
    await sink.emit(job_id, "collect", "collector", "step")  # seq 2
    await sink.emit(job_id, "collect", "collector", "step")  # seq 3

    # Start subscriber requesting since_seq=2
    received: list[EventMessage] = []

    async def sub() -> None:
        async for msg in sink.subscribe(job_id, since_seq=2):
            received.append(msg)

    sub_task = asyncio.create_task(sub())
    await asyncio.sleep(0.05)

    # Emit final stage_end to complete the stream
    await sink.emit(job_id, "system", "runner", "stage_end")  # seq 4
    await sub_task

    # Should only receive seq 3 and seq 4
    seqs = [m.seq for m in received]
    assert seqs == [3, 4]


@pytest.mark.asyncio
async def test_event_sink_finished_job_replays_and_terminates(
    fake_event_setup: tuple[EventSink, FakeJobRepo],
) -> None:
    """Subscribing to a finished job replays historical events
    and immediately finishes without hanging.
    """
    sink, fake_repo = fake_event_setup
    job_id = uuid.uuid4()

    # Mark job as succeeded in repository
    fake_repo.jobs[job_id] = Job(
        id=job_id,
        project_id="prj_test001",
        user_id=uuid.uuid4(),
        stage="collect",
        status="succeeded",
        input_hash="hash_done",
    )

    await sink.emit(job_id, "collect", "collector", "stage_start")
    await sink.emit(job_id, "collect", "collector", "result")

    # Subscriber connects to already finished job
    received: list[EventMessage] = []
    # This should finish promptly and not block indefinitely
    async for msg in sink.subscribe(job_id, since_seq=0):
        received.append(msg)

    assert len(received) == 2
    assert [m.type for m in received] == ["stage_start", "result"]
