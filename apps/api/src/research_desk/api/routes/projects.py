"""Project management API routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, status

from research_desk.api.auth import get_current_user, get_owned_project
from research_desk.api.dependencies import get_vector_store
from research_desk.core.errors import AppError
from research_desk.core.schemas import (
    ActiveJobItem,
    CreateProjectRequest,
    CreateProjectResponse,
    DeleteProjectResponse,
    ListProjectsResponse,
    ProjectDetailResponse,
    ProjectHeader,
    ProjectListItem,
    ProjectSourceItem,
    SourceStages,
)
from research_desk.stores.db import DbSession, get_db
from research_desk.stores.models import Project, User
from research_desk.stores.repos.jobs import JobRepo
from research_desk.stores.repos.projects import ProjectRepo
from research_desk.stores.repos.sources import SourceRepo
from research_desk.stores.vector import VectorStore

router = APIRouter(prefix="/api/projects", tags=["projects"])


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

    return ProjectDetailResponse(
        project=ProjectHeader(
            id=project.id,
            name=project.name,
            description=project.description,
        ),
        sources=sources,
        conflicts=[],
        briefs=[],
        active_jobs=active_jobs,
    )


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

    # 1. Tombstone in PostgreSQL
    project_repo = ProjectRepo(session)
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
