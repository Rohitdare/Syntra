"""Job and JobEvent repository for PostgreSQL."""

from __future__ import annotations

import datetime
import uuid
from typing import Any, Sequence

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from research_desk.stores.models import Job, JobEvent


class JobRepo:
    """Repository managing Job and JobEvent entities in PostgreSQL."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_job(
        self,
        *,
        project_id: str,
        user_id: uuid.UUID,
        stage: str,
        input_hash: str,
        source_id: str | None = None,
        idempotency_key: str | None = None,
        lease_seconds: int = 30,
    ) -> Job:
        """Create a new queued job."""
        now = datetime.datetime.now(datetime.timezone.utc)
        lease_expires = now + datetime.timedelta(seconds=lease_seconds)

        job = Job(
            id=uuid.uuid4(),
            project_id=project_id,
            source_id=source_id,
            user_id=user_id,
            stage=stage,
            status="queued",
            idempotency_key=idempotency_key,
            input_hash=input_hash,
            attempt=1,
            lease_expires_at=lease_expires,
            created_at=now,
        )
        self.session.add(job)
        await self.session.flush()
        return job

    async def get(self, job_id: uuid.UUID) -> Job | None:
        """Fetch job by ID."""
        stmt = select(Job).where(Job.id == job_id)
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def get_active_single_flight(
        self,
        project_id: str,
        stage: str,
        source_id: str | None,
        input_hash: str,
    ) -> Job | None:
        """Find an existing queued or running job matching the single-flight parameters."""
        src_check = Job.source_id.is_(None) if source_id is None else Job.source_id == source_id
        stmt = select(Job).where(
            Job.project_id == project_id,
            Job.stage == stage,
            src_check,
            Job.input_hash == input_hash,
            Job.status.in_(["queued", "running"]),
        )
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def get_by_idempotency(self, user_id: uuid.UUID, idempotency_key: str) -> Job | None:
        """Fetch job by user_id and idempotency_key."""
        stmt = select(Job).where(
            Job.user_id == user_id,
            Job.idempotency_key == idempotency_key,
        )
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def update_status(
        self,
        job_id: uuid.UUID,
        status: str,
        *,
        error_code: str | None = None,
        error_message: str | None = None,
        result: dict[str, Any] | None = None,
        worker_id: str | None = None,
    ) -> None:
        """Transition job status."""
        stmt = select(Job).where(Job.id == job_id)
        res = await self.session.execute(stmt)
        job = res.scalar_one_or_none()
        if not job:
            return

        now = datetime.datetime.now(datetime.timezone.utc)
        job.status = status
        if status == "running" and job.started_at is None:
            job.started_at = now
        elif status in ("succeeded", "failed", "interrupted"):
            job.finished_at = now

        if error_code is not None:
            job.error_code = error_code
        if error_message is not None:
            job.error_message = error_message
        if result is not None:
            job.result = result
        if worker_id is not None:
            job.worker_id = worker_id

        await self.session.flush()

    async def heartbeat(self, job_id: uuid.UUID, lease_seconds: int = 30) -> None:
        """Extend the lease expiration timestamp for a running job."""
        now = datetime.datetime.now(datetime.timezone.utc)
        new_lease = now + datetime.timedelta(seconds=lease_seconds)
        stmt = (
            update(Job)
            .where(Job.id == job_id, Job.status == "running")
            .values(lease_expires_at=new_lease)
        )
        await self.session.execute(stmt)
        await self.session.flush()

    async def add_event(
        self,
        job_id: uuid.UUID,
        stage: str,
        agent: str,
        type_: str,
        message: str | None = None,
        data: dict[str, Any] | None = None,
    ) -> JobEvent:
        """Append an event to the job event log with monotonically increasing seq."""
        # Find next seq for this job
        max_seq_stmt = select(func.coalesce(func.max(JobEvent.seq), 0)).where(
            JobEvent.job_id == job_id
        )
        max_seq = (await self.session.execute(max_seq_stmt)).scalar_one()
        next_seq = max_seq + 1

        event = JobEvent(
            job_id=job_id,
            seq=next_seq,
            stage=stage,
            agent=agent,
            type=type_,
            message=message,
            data=data,
        )
        self.session.add(event)
        await self.session.flush()
        return event

    async def get_events(self, job_id: uuid.UUID, since_seq: int = 0) -> Sequence[JobEvent]:
        """Fetch all events for a job with seq > since_seq."""
        stmt = (
            select(JobEvent)
            .where(JobEvent.job_id == job_id, JobEvent.seq > since_seq)
            .order_by(JobEvent.seq.asc())
        )
        res = await self.session.execute(stmt)
        return res.scalars().all()

    async def sweep_interrupted(self, lease_cutoff: datetime.datetime) -> int:
        """Mark expired running jobs as failed with error_code='INTERRUPTED'."""
        stmt = (
            update(Job)
            .where(
                Job.status == "running",
                Job.lease_expires_at < lease_cutoff,
            )
            .values(
                status="failed",
                error_code="INTERRUPTED",
                error_message="Job interrupted by server restart or lost lease",
                finished_at=datetime.datetime.now(datetime.timezone.utc),
            )
        )
        res = await self.session.execute(stmt)
        await self.session.flush()
        rowcount = getattr(res, "rowcount", 0)
        return int(rowcount or 0)

    async def list_active_for_project(self, project_id: str) -> Sequence[Job]:
        """Find all active (queued or running) jobs in a project."""
        stmt = (
            select(Job)
            .where(
                Job.project_id == project_id,
                Job.status.in_(["queued", "running"]),
            )
            .order_by(Job.created_at.asc())
        )
        res = await self.session.execute(stmt)
        return res.scalars().all()

    async def has_active_for_source(self, project_id: str, source_id: str) -> bool:
        """Check if any active job exists for this source."""
        stmt = select(func.count(Job.id)).where(
            Job.project_id == project_id,
            Job.source_id == source_id,
            Job.status.in_(["queued", "running"]),
        )
        res = await self.session.execute(stmt)
        return bool(res.scalar_one() > 0)

    async def has_active_for_project(self, project_id: str) -> bool:
        """Check if any active job exists for this project."""
        stmt = select(func.count(Job.id)).where(
            Job.project_id == project_id,
            Job.status.in_(["queued", "running"]),
        )
        res = await self.session.execute(stmt)
        return bool(res.scalar_one() > 0)

    async def get_last_seq(self, job_id: uuid.UUID) -> int:
        """Get the maximum sequence number emitted for a job."""
        stmt = select(func.coalesce(func.max(JobEvent.seq), 0)).where(JobEvent.job_id == job_id)
        res = await self.session.execute(stmt)
        return int(res.scalar_one() or 0)
