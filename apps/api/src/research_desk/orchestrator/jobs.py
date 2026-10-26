"""Job service coordinating single-flight execution, idempotency, and recovery sweep.

Per docs/02-DESIGN-DOC.md Section 13.8 and docs/05-API-SPEC.md Section 6.
"""

from __future__ import annotations

import datetime
import uuid

from research_desk.core.errors import AppError
from research_desk.stores.db import DbSessionFactory
from research_desk.stores.models import Job
from research_desk.stores.repos.jobs import JobRepo


class JobService:
    """Service managing the lifecycle, idempotency, and recovery of jobs."""

    def __init__(self, sessionmaker: DbSessionFactory) -> None:
        self.sessionmaker = sessionmaker

    async def create_or_join_job(
        self,
        *,
        project_id: str,
        user_id: uuid.UUID,
        stage: str,
        input_hash: str,
        source_id: str | None = None,
        idempotency_key: str | None = None,
        lease_seconds: int = 30,
    ) -> tuple[Job, bool]:
        """Create a new job or join an existing active/idempotent one.

        Returns (job, is_new).
        Raises AppError("IDEMPOTENCY_CONFLICT") if an idempotency key is reused with
        different input.
        """
        async with self.sessionmaker() as session:
            async with session.begin():
                repo = JobRepo(session)

                # 1. Check client idempotency key if provided
                if idempotency_key is not None:
                    existing_idemp = await repo.get_by_idempotency(user_id, idempotency_key)
                    if existing_idemp is not None:
                        if existing_idemp.input_hash != input_hash:
                            raise AppError(
                                code="IDEMPOTENCY_CONFLICT",
                                message="Idempotency key reused with different request payload",
                                http_status=409,
                                retryable=False,
                            )
                        return existing_idemp, False

                # 2. Check server-side single flight
                existing_active = await repo.get_active_single_flight(
                    project_id=project_id,
                    stage=stage,
                    source_id=source_id,
                    input_hash=input_hash,
                )
                if existing_active is not None:
                    return existing_active, False

                # 3. Create fresh queued job
                job = await repo.create_job(
                    project_id=project_id,
                    user_id=user_id,
                    stage=stage,
                    input_hash=input_hash,
                    source_id=source_id,
                    idempotency_key=idempotency_key,
                    lease_seconds=lease_seconds,
                )
                return job, True

    async def get_job(self, job_id: uuid.UUID) -> Job | None:
        """Fetch job by ID."""
        async with self.sessionmaker() as session:
            repo = JobRepo(session)
            return await repo.get(job_id)

    async def heartbeat(self, job_id: uuid.UUID, lease_seconds: int = 30) -> None:
        """Extend lease timestamp for a running job."""
        async with self.sessionmaker() as session:
            async with session.begin():
                repo = JobRepo(session)
                await repo.heartbeat(job_id, lease_seconds=lease_seconds)

    async def sweep_interrupted(self) -> int:
        """Sweep running jobs whose leases expired, marking them INTERRUPTED."""
        now = datetime.datetime.now(datetime.timezone.utc)
        async with self.sessionmaker() as session:
            async with session.begin():
                repo = JobRepo(session)
                return await repo.sweep_interrupted(lease_cutoff=now)
