"""Spike script for NDJSON event streaming and disconnected job survival (S9).

Checks:
- S9: InProcessRunner launches detached async job task.
- EventSink records heartbeats and stage events in DB and live subscribers.
- Client cancellation/disconnect does not cancel the background running task.
"""

from __future__ import annotations

import asyncio
import uuid

from research_desk.core.config import get_settings
from research_desk.orchestrator.events import EventSink
from research_desk.orchestrator.runner import InProcessRunner
from research_desk.stores.db import check_db_readiness, get_sessionmaker
from research_desk.stores.models import Project, User
from research_desk.stores.repos.jobs import JobRepo


async def dummy_slow_stage(event_sink: EventSink, job_id: uuid.UUID) -> dict[str, str]:
    """Simulates a detached 6-second job stage emitting progress and heartbeats."""
    for i in range(1, 4):
        await asyncio.sleep(1.0)
        await event_sink.emit(
            job_id=job_id,
            stage="test_stage",
            agent="spike_agent",
            type_="progress",
            message=f"Step {i} completed",
            data={"step": i},
        )
    return {"status": "complete", "details": "Detached execution successful"}


async def run_spikes() -> dict[str, str]:
    results: dict[str, str] = {}
    settings = get_settings()

    print("=" * 60)
    print("Stage 1 Spike: NDJSON Streaming & Detached Job Survival (S9)")
    print("=" * 60)

    db_ok = await check_db_readiness(settings)
    if not db_ok:
        msg = "PostgreSQL is DOWN. Start Docker Compose services to run streaming spike."
        print(f"  {msg}")
        results["S9"] = f"BLOCKED: {msg}"
        return results

    sm = get_sessionmaker(settings)
    event_sink = EventSink(sm)
    runner = InProcessRunner(
        sessionmaker=sm,
        event_sink=event_sink,
        active_cap=3,
        stage_timeout_s=30.0,
        lease_seconds=10,
    )

    test_user_id = uuid.uuid4()
    test_prj_id = f"prj_{uuid.uuid4().hex[:8]}"

    async with sm() as session:
        async with session.begin():
            session.add(User(id=test_user_id, auth_subject=f"stream-user-{test_user_id}"))
            session.add(Project(id=test_prj_id, owner_id=test_user_id, name="Stream Spike Prj"))
            job_repo = JobRepo(session)
            job = await job_repo.create_job(
                project_id=test_prj_id,
                user_id=test_user_id,
                stage="collect",
                input_hash="hash_stream",
            )
            job_id = job.id

    print(f"  Created test job {job_id}. Submitting to runner...")

    async def stage_wrapper(sink: EventSink) -> dict[str, str]:
        return await dummy_slow_stage(sink, job_id)

    await runner.submit(job_id, stage_wrapper)

    # Simulate client listening to stream for 1.5 seconds, then disconnecting
    print("  Simulating client connecting to stream...")
    received_events: list[str] = []

    async def client_listener() -> None:
        async for evt in event_sink.subscribe(job_id):
            received_events.append(evt.type)
            print(f"    [Client Received] Event type={evt.type}, message={evt.message}")

    listener_task = asyncio.create_task(client_listener())
    await asyncio.sleep(1.5)
    print("  Simulating client DISCONNECT (cancelling subscriber)...")
    listener_task.cancel()
    try:
        await listener_task
    except asyncio.CancelledError:
        pass

    # Wait for the background job to finish on the server
    print("  Waiting for server job to finish detached execution...")
    await asyncio.sleep(3.5)

    # Verify final job status in database
    async with sm() as session:
        job_repo = JobRepo(session)
        final_job = await job_repo.get(job_id)
        assert final_job is not None

        all_events = await job_repo.get_events(job_id)
        event_types = [e.type for e in all_events]

    print(f"  Job final status: {final_job.status}")
    print(f"  Persisted event types in DB: {event_types}")

    if final_job.status == "succeeded" and "stage_end" in event_types:
        results["S9"] = (
            "PASSED: Detached job survived client disconnection, continued executing, "
            "and finished with status='succeeded'. "
            f"Recorded {len(all_events)} events in PostgreSQL."
        )
        print("  S9 Result: PASSED")
    else:
        results["S9"] = f"FAILED: Job ended with status={final_job.status}, events={event_types}"
        print("  S9 Result: FAILED")

    await runner.shutdown()
    return results


async def main() -> None:
    results = await run_spikes()
    print("\n" + "=" * 60)
    print("SPIKE SUMMARY RESULTS:")
    print("=" * 60)
    for k, v in results.items():
        print(f"[{k}]: {v}")


if __name__ == "__main__":
    asyncio.run(main())
