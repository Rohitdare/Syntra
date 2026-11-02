"""Project management API routes."""

from __future__ import annotations

import hashlib
import uuid
from collections.abc import AsyncGenerator
from typing import Any, Literal, cast

from fastapi import APIRouter, Depends, Header, Request, status
from fastapi.responses import StreamingResponse

from research_desk.api.auth import get_current_user, get_owned_project
from research_desk.api.dependencies import (
    get_event_sink,
    get_pipeline_orchestrator,
    get_vector_store,
)
from research_desk.core.errors import AppError
from research_desk.core.ids import normalize_question
from research_desk.core.schemas import (
    ActiveJobItem,
    AskInput,
    AskRequest,
    ConflictItem,
    CreateProjectRequest,
    CreateProjectResponse,
    DeleteProjectResponse,
    ListProjectsResponse,
    ProjectDetailResponse,
    ProjectHeader,
    ProjectListItem,
    ProjectSourceItem,
    SourceStages,
    VerdictClaimSide,
)
from research_desk.orchestrator.events import EventSink
from research_desk.orchestrator.pipeline import PipelineOrchestrator
from research_desk.stores.db import DbSession, get_db
from research_desk.stores.models import Project, User, Verdict
from research_desk.stores.repos.briefs import BriefRepo
from research_desk.stores.repos.jobs import JobRepo
from research_desk.stores.repos.projects import ProjectRepo
from research_desk.stores.repos.sources import SourceRepo
from research_desk.stores.repos.verdicts import VerdictRepo
from research_desk.stores.vector import VectorStore

router = APIRouter(prefix="/api/projects", tags=["projects"])


def _validate_idempotency_key(key: str | None) -> str | None:
    if key is None:
        return None
    clean = key.strip()
    if not 1 <= len(clean) <= 100 or not all(33 <= ord(char) <= 126 for char in clean):
        raise AppError(
            "BAD_REQUEST",
            "Idempotency-Key must contain 1-100 visible ASCII characters",
            http_status=400,
            retryable=False,
        )
    return clean


@router.post("", status_code=status.HTTP_201_CREATED, response_model=CreateProjectResponse)
async def create_project(
    payload: CreateProjectRequest,
    current_user: User = Depends(get_current_user),
    session: DbSession = Depends(get_db),
) -> CreateProjectResponse:
    """Create a new research project."""
    repo = ProjectRepo(session)
    project = await repo.create(
        owner_id=current_user.id,
        name=payload.name,
        description=payload.description,
    )
    await session.commit()
    return CreateProjectResponse(project_id=project.id)


@router.get("", status_code=status.HTTP_200_OK, response_model=ListProjectsResponse)
async def list_projects(
    current_user: User = Depends(get_current_user),
    session: DbSession = Depends(get_db),
) -> ListProjectsResponse:
    """List active projects owned by user, sorted newest first."""
    repo = ProjectRepo(session)
    rows = await repo.list_for_owner_with_source_counts(owner_id=current_user.id)
    items = [
        ProjectListItem(
            id=p.id,
            name=p.name,
            description=p.description,
            source_count=count,
            updated_at=p.updated_at,
        )
        for p, count in rows
    ]
    return ListProjectsResponse(projects=items)


@router.get("/{project_id}", status_code=status.HTTP_200_OK, response_model=ProjectDetailResponse)
async def get_project(
    project: Project = Depends(get_owned_project),
    session: DbSession = Depends(get_db),
) -> ProjectDetailResponse:
    """Fetch project detail view with sources and active jobs."""
    source_repo = SourceRepo(session)
    job_repo = JobRepo(session)

    sources_db = await source_repo.list_by_project(project.id)
    sources = [
        ProjectSourceItem(
            id=s.id,
            tag=s.tag,
            kind=s.kind,
            title=s.title,
            origin=s.origin,
            chunk_count=s.chunk_count,
            claim_count=s.claim_count,
            stages=SourceStages(
                collected=s.stage_collected,
                analyzed=s.stage_analyzed,
                critiqued=s.stage_critiqued,
            ),
            last_error=s.last_error,
        )
        for s in sources_db
    ]

    active_db = await job_repo.list_active_for_project(project.id)
    active_jobs = [
        ActiveJobItem(
            job_id=str(j.id),
            stage=j.stage,
            source_id=j.source_id,
            status=j.status,
            last_seq=await job_repo.get_last_seq(j.id),
        )
        for j in active_db
    ]

    verdict_rows = await VerdictRepo(session).list_by_project(project.id)
    brief_rows = await BriefRepo(session).list_by_project(project.id)
    return ProjectDetailResponse(
        project=ProjectHeader(
            id=project.id,
            name=project.name,
            description=project.description,
        ),
        sources=sources,
        conflicts=[_conflict_item(row) for row in verdict_rows],
        briefs=[
            {"id": b.id, "question": b.question, "createdAt": b.created_at} for b in brief_rows
        ],
        active_jobs=active_jobs,
    )


def _conflict_item(row: Verdict) -> ConflictItem:
    return ConflictItem(
        id=row.id,
        label=cast(Literal["supports", "contradicts", "nuances", "unrelated"], row.label),
        confidence=row.confidence,
        rationale=row.rationale,
        similarity=row.similarity,
        a=VerdictClaimSide(
            claim_id=row.claim_key_a,
            source_id=row.source_id_a,
            source_tag=row.source_tag_a,
            text=row.claim_text_a,
        ),
        b=VerdictClaimSide(
            claim_id=row.claim_key_b,
            source_id=row.source_id_b,
            source_tag=row.source_tag_b,
            text=row.claim_text_b,
        ),
    )


@router.post("/{project_id}/ask", status_code=status.HTTP_200_OK)
async def ask_project(
    project_id: str,
    payload: AskRequest,
    request: Request,
    project: Project = Depends(get_owned_project),
    current_user: User = Depends(get_current_user),
    orchestrator: PipelineOrchestrator = Depends(get_pipeline_orchestrator),
    event_sink: EventSink = Depends(get_event_sink),
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
) -> StreamingResponse:
    """Run Writer and stream persisted stage events."""
    question = payload.question
    if not 5 <= len(question.strip()) <= 500:
        raise AppError("BAD_REQUEST", "Question must be 5-500 characters", http_status=400)
    question = normalize_question(question)
    idempotency_key = _validate_idempotency_key(idempotency_key)
    input_hash = hashlib.sha256(f"{project.id}:{question}".encode()).hexdigest()
    job, _ = await orchestrator.run_job(
        stage="ask",
        project_id=project.id,
        user_id=current_user.id,
        inp=AskInput(project_id=project.id, question=question),
        input_hash=input_hash,
        idempotency_key=idempotency_key,
    )

    async def event_generator() -> AsyncGenerator[str, None]:
        async for msg in event_sink.subscribe(job.id, since_seq=0):
            yield msg.to_ndjson() + "\n"

    req_id = getattr(request.state, "request_id", None) or f"req_{uuid.uuid4().hex[:24]}"
    return StreamingResponse(
        event_generator(),
        media_type="application/x-ndjson",
        headers={"X-Request-Id": req_id, "X-Job-Id": str(job.id)},
    )


@router.get("/{project_id}/briefs/{brief_id}", status_code=status.HTTP_200_OK)
async def get_brief(
    brief_id: str,
    project: Project = Depends(get_owned_project),
    session: DbSession = Depends(get_db),
) -> dict[str, Any]:
    brief = await BriefRepo(session).get(project.id, brief_id)
    if brief is None:
        raise AppError("NOT_FOUND", "Brief not found", http_status=404, retryable=False)
    data = dict(brief.json_data)
    data.pop("_researchContext", None)
    data.update({"briefId": brief.id, "question": brief.question})
    return data


@router.delete(
    "/{project_id}", status_code=status.HTTP_200_OK, response_model=DeleteProjectResponse
)
async def delete_project(
    project: Project = Depends(get_owned_project),
    session: DbSession = Depends(get_db),
    vectors: VectorStore = Depends(get_vector_store),
) -> DeleteProjectResponse:
    """Delete a project, safely purging its vectors and cascading database records."""
    job_repo = JobRepo(session)
    has_active = await job_repo.has_active_for_project(project.id)
    if has_active:
        raise AppError(
            code="JOB_ACTIVE",
            message="A stage is still running for this target.",
            http_status=409,
            retryable=True,
        )

    source_repo = SourceRepo(session)
    source_count = await source_repo.count_by_project(project.id)

    # 1. Hide the project before touching Qdrant. DELETE retries are allowed to
    # resolve an existing tombstone after a transient vector or DB failure.
    project_repo = ProjectRepo(session)
    if project.status != "deleting":
        await project_repo.mark_deleting(project.id)
    await session.commit()

    # 2. Purge Qdrant points
    try:
        await vectors.delete_project(project.id)
    except Exception as exc:
        raise AppError(
            code="VECTOR_DB_ERROR",
            message=f"Vector database failed to delete project index: {exc}",
            http_status=503,
            retryable=True,
        ) from exc

    # 3. Hard delete from PostgreSQL
    await project_repo.delete(project.id)
    await session.commit()

    deleted_count = 1 + source_count
    return DeleteProjectResponse(deleted=deleted_count)
