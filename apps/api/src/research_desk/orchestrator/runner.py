"""In-process job runner executing detached async stage pipelines.

Per docs/02-DESIGN-DOC.md Section 14 and docs/05-API-SPEC.md Section 5.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import Callable, Coroutine
from typing import Any, Protocol

from research_desk.core.errors import AppError
from research_desk.orchestrator.events import EventSink
from research_desk.stores.db import DbSessionFactory
from research_desk.stores.repos.jobs import JobRepo

logger = logging.getLogger(__name__)

StageCallable = Callable[[EventSink], Coroutine[Any, Any, dict[str, Any]]]


class JobRunner(Protocol):
    """Protocol for launching and executing background jobs."""

    async def submit(self, job_id: uuid.UUID, stage_coro: StageCallable) -> None: ...


class InProcessRunner(JobRunner):
    """Level-0 (v1) in-process job runner with active caps and lease heartbeats."""

    def __init__(
        self,
        sessionmaker: DbSessionFactory,
        event_sink: EventSink,
        *,
        active_cap: int = 3,
        stage_timeout_s: float = 180.0,
        lease_seconds: int = 30,
    ) -> None:
        self.sessionmaker = sessionmaker
        self.event_sink = event_sink
        self.active_cap = active_cap
        self.stage_timeout_s = stage_timeout_s
        self.lease_seconds = lease_seconds

        self._active_tasks: dict[uuid.UUID, asyncio.Task[None]] = {}
        self._lock = asyncio.Lock()

    async def submit(self, job_id: uuid.UUID, stage_coro: StageCallable) -> None:
        """Submit a job to be executed in a detached background task."""
        async with self._lock:
            if len(self._active_tasks) >= self.active_cap:
                raise AppError(
                    code="OVERLOADED",
                    message="Server active job capacity reached; please retry shortly",
                    http_status=503,
                    retryable=True,
                    retry_after_seconds=10,
                )

            task = asyncio.create_task(
                self._run_job(job_id, stage_coro),
                name=f"job-{job_id}",
            )
            self._active_tasks[job_id] = task

        def _cleanup(t: asyncio.Task[None]) -> None:
            self._active_tasks.pop(job_id, None)

        task.add_done_callback(_cleanup)

    async def _heartbeat_loop(self, job_id: uuid.UUID) -> None:
        """Periodically extend the job lease in the background while running."""
        interval = max(5.0, self.lease_seconds / 2.0)
        while True:
            await asyncio.sleep(interval)
            try:
                async with self.sessionmaker() as session:
                    async with session.begin():
                        repo = JobRepo(session)
                        await repo.heartbeat(job_id, lease_seconds=self.lease_seconds)
                # Emit heartbeat event to tailing streams
                await self.event_sink.emit(
                    job_id=job_id,
                    stage="system",
                    agent="runner",
                    type_="heartbeat",
                )
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.warning("Heartbeat failed for job %s: %s", job_id, exc)

    async def _run_job(self, job_id: uuid.UUID, stage_coro: StageCallable) -> None:
        """Execute the job pipeline with status updates, heartbeat, and error recovery."""
        hb_task = asyncio.create_task(self._heartbeat_loop(job_id))

        # Transition job to running
        async with self.sessionmaker() as session:
            async with session.begin():
                repo = JobRepo(session)
                await repo.update_status(job_id, status="running")

        try:
            result = await asyncio.wait_for(
                stage_coro(self.event_sink),
                timeout=self.stage_timeout_s,
            )

            # Succeeded
            async with self.sessionmaker() as session:
                async with session.begin():
                    repo = JobRepo(session)
                    await repo.update_status(
                        job_id,
                        status="succeeded",
                        result=result,
                    )

            await self.event_sink.emit(
                job_id=job_id,
                stage="system",
                agent="runner",
                type_="stage_end",
                data={"status": "succeeded", "result": result},
            )

        except asyncio.TimeoutError:
            logger.error("Job %s timed out after %s seconds", job_id, self.stage_timeout_s)
            async with self.sessionmaker() as session:
                async with session.begin():
                    repo = JobRepo(session)
                    await repo.update_status(
                        job_id,
                        status="failed",
                        error_code="TIMEOUT",
                        error_message="Stage exceeded maximum execution time",
                    )

            await self.event_sink.emit(
                job_id=job_id,
                stage="system",
                agent="runner",
                type_="error",
                message="Stage exceeded maximum execution time",
                data={"code": "TIMEOUT", "retryable": True},
            )
            await self.event_sink.emit(
                job_id=job_id,
                stage="system",
                agent="runner",
                type_="stage_end",
                data={"status": "failed", "code": "TIMEOUT"},
            )

        except Exception as exc:
            err_code = getattr(exc, "code", "INTERNAL")
            err_msg = str(getattr(exc, "message", str(exc)))
            retryable = bool(getattr(exc, "retryable", False))

            logger.exception("Job %s failed: %s", job_id, exc)

            async with self.sessionmaker() as session:
                async with session.begin():
                    repo = JobRepo(session)
                    await repo.update_status(
                        job_id,
                        status="failed",
                        error_code=err_code,
                        error_message=err_msg,
                    )

            await self.event_sink.emit(
                job_id=job_id,
                stage="system",
                agent="runner",
                type_="error",
                message=err_msg,
                data={"code": err_code, "retryable": retryable},
            )
            await self.event_sink.emit(
                job_id=job_id,
                stage="system",
                agent="runner",
                type_="stage_end",
                data={"status": "failed", "code": err_code},
            )

        finally:
            hb_task.cancel()
            try:
                await hb_task
            except asyncio.CancelledError:
                pass

    async def shutdown(self, grace_period_s: float = 5.0) -> None:
        """Gracefully wait for or cancel active in-process job tasks."""
        async with self._lock:
            tasks = list(self._active_tasks.values())
        if not tasks:
            return

        logger.info("Graceful shutdown: waiting for %d active job tasks...", len(tasks))
        done, pending = await asyncio.wait(tasks, timeout=grace_period_s)
        for t in pending:
            t.cancel()
