"""Job status and event streaming API routes."""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator

from fastapi import APIRouter, Depends, Query, Request, status
from fastapi.responses import StreamingResponse

from research_desk.api.auth import get_current_user
from research_desk.api.dependencies import get_event_sink
from research_desk.core.errors import AppError
from research_desk.core.schemas import JobStatusResponse
from research_desk.orchestrator.events import EventSink
from research_desk.stores.db import DbSession, get_db
from research_desk.stores.models import User
from research_desk.stores.repos.jobs import JobRepo

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


@router.get("/{job_id}", status_code=status.HTTP_200_OK, response_model=JobStatusResponse)
async def get_job_status(
    job_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    session: DbSession = Depends(get_db),
) -> JobStatusResponse:
    """Fetch status and outcome of an execution job."""
    job_repo = JobRepo(session)
    job = await job_repo.get(job_id)

    # Prevent existence leakage for foreign or missing jobs
    if job is None or job.user_id != current_user.id:
        raise AppError(
            code="NOT_FOUND",
            message="Job not found",
            http_status=404,
            retryable=False,
        )

    last_seq = await job_repo.get_last_seq(job_id)

    return JobStatusResponse(
        job_id=str(job.id),
        project_id=job.project_id,
        source_id=job.source_id,
        stage=job.stage,
        status=job.status,
        error_code=job.error_code,
        result=job.result,
        last_seq=last_seq,
        started_at=job.started_at,
        finished_at=job.finished_at,
    )


@router.get("/{job_id}/events", status_code=status.HTTP_200_OK)
async def stream_job_events(
    job_id: uuid.UUID,
    request: Request,
    after: int = Query(default=0, ge=0),
    current_user: User = Depends(get_current_user),
    session: DbSession = Depends(get_db),
    event_sink: EventSink = Depends(get_event_sink),
) -> StreamingResponse:
    """Stream NDJSON events for a job, replaying from cursor then streaming live."""
    job_repo = JobRepo(session)
    job = await job_repo.get(job_id)

    # Prevent existence leakage for foreign or missing jobs
    if job is None or job.user_id != current_user.id:
        raise AppError(
            code="NOT_FOUND",
            message="Job not found",
            http_status=404,
            retryable=False,
        )

    async def event_generator() -> AsyncGenerator[str, None]:
        async for msg in event_sink.subscribe(job_id, since_seq=after):
            yield msg.to_ndjson() + "\n"

    req_id = getattr(request.state, "request_id", None) or f"req_{uuid.uuid4().hex[:24]}"
    headers = {
        "X-Request-Id": req_id,
        "X-Job-Id": str(job_id),
    }

    return StreamingResponse(
        event_generator(),
        media_type="application/x-ndjson",
        headers=headers,
    )
