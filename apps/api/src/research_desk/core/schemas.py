import datetime
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from pydantic.alias_generators import to_camel


class CamelModel(BaseModel):
    """Base model that automatically aliases snake_case fields to camelCase."""

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        extra="forbid",
    )


class HealthConfigured(CamelModel):
    """Configured status for dependent services."""

    gemini: bool
    postgres: bool
    qdrant: bool


class HealthDbStatus(CamelModel):
    """Database connectivity status for readiness probe."""

    postgres: str
    qdrant: str


class HealthResponse(CamelModel):
    """Health check endpoint response envelope."""

    ok: bool
    configured: HealthConfigured | None = None
    db: HealthDbStatus | None = None


class ErrorDetail(CamelModel):
    """Standardized error detail body."""

    code: str
    message: str
    request_id: str
    retryable: bool = False
    retry_after_seconds: int | None = None


class ErrorEnvelope(CamelModel):
    """Standardized error envelope for all non-stream responses."""

    error: ErrorDetail


class CreateProjectRequest(CamelModel):
    """Payload to create a new project."""

    name: str = Field(min_length=1, max_length=80)
    description: str | None = None


class CreateProjectResponse(CamelModel):
    """Response returned upon project creation."""

    project_id: str


class ProjectListItem(CamelModel):
    """Summary of a project in list view."""

    id: str
    name: str
    description: str | None = None
    source_count: int
    updated_at: datetime.datetime


class ListProjectsResponse(CamelModel):
    """Response returning all active projects for the current user."""

    projects: list[ProjectListItem]


class SourceStages(CamelModel):
    """Stage status booleans for a source."""

    collected: bool
    analyzed: bool
    critiqued: bool


class ProjectSourceItem(CamelModel):
    """Source item in project detail or list view."""

    id: str
    tag: str
    kind: str
    title: str
    origin: str
    chunk_count: int
    claim_count: int
    stages: SourceStages
    last_error: str | None = None


class ActiveJobItem(CamelModel):
    """Summary of an active background stage running in a project."""

    job_id: str
    stage: str
    source_id: str | None = None
    status: str
    last_seq: int


class ProjectHeader(CamelModel):
    """Project metadata header."""

    id: str
    name: str
    description: str | None = None


class ProjectDetailResponse(CamelModel):
    """Full detail view of a project, its sources, conflicts, briefs, and active jobs."""

    project: ProjectHeader
    sources: list[ProjectSourceItem]
    conflicts: list[dict[str, Any]] = Field(default_factory=list)
    briefs: list[dict[str, Any]] = Field(default_factory=list)
    active_jobs: list[ActiveJobItem] = Field(default_factory=list)


class DeleteProjectResponse(CamelModel):
    """Response confirming project deletion."""

    deleted: int


class DeleteSourceResponse(CamelModel):
    """Response confirming source deletion."""

    deleted: bool


class SourceIngestJsonRequest(CamelModel):
    """JSON payload for adding a URL or pasted text source."""

    url: str | None = None
    title: str | None = None
    text: str | None = None


class ClaimItem(CamelModel):
    """Public API representation of an extracted claim."""

    id: str
    source_id: str
    claim_index: int
    text: str
    importance: int
    page_hint: int | None = None
    created_at: datetime.datetime | str | None = None


class SourceDetailResponse(CamelModel):
    """Detail view of a source with summary, claims, and verdicts."""

    source: ProjectSourceItem
    summary: str | None = None
    claims: list[ClaimItem] = Field(default_factory=list)
    verdicts: list[dict[str, Any]] = Field(default_factory=list)


class AnalystClaim(CamelModel):
    """Atomic claim extracted by the LLM from source text."""

    text: str = Field(min_length=20, max_length=400, description="Atomic, self-contained assertion")
    importance: int = Field(
        ge=1, le=5, description="Significance of finding: 5=central, 1=minor detail"
    )
    page_hint: int | None = Field(
        default=None, gt=0, description="Approximate source page if available"
    )


class AnalystOutputSchema(CamelModel):
    """Structured LLM output schema for Gemini provider validation."""

    title: str = Field(min_length=1, max_length=200, description="Faithful, concise document title")
    summary: str = Field(
        min_length=40, max_length=1200, description="3-5 sentence faithful summary"
    )
    topics: list[Annotated[str, StringConstraints(max_length=40)]] = Field(
        min_length=1, max_length=5, description="1-5 high-level research topics"
    )
    claims: list[AnalystClaim] = Field(max_length=8, description="At most 8 ranked claims")


class AnalystInput(CamelModel):
    """Input payload to run the Analyst agent."""

    project_id: str
    source_id: str


class AnalystOutput(CamelModel):
    """Result payload emitted at the conclusion of analysis."""

    claim_count: int
    topics: list[str]


class JobStatusResponse(CamelModel):
    """Operational status and outcome of an execution job."""

    job_id: str
    project_id: str
    source_id: str | None = None
    stage: str
    status: str
    error_code: str | None = None
    result: dict[str, Any] | None = None
    last_seq: int
    started_at: datetime.datetime | None = None
    finished_at: datetime.datetime | None = None
