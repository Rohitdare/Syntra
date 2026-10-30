import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from pydantic.alias_generators import to_camel


class CamelModel(BaseModel):
    """Base model that automatically aliases snake_case fields to camelCase."""

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        extra="ignore",
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


class VerdictClaimSide(CamelModel):
    """Claim details for one side of a comparative verdict."""

    claim_id: str
    source_id: str | None = None
    source_tag: str
    text: str


class ConflictItem(CamelModel):
    """Comparative verdict representing agreement, disagreement, or nuance between two claims."""

    id: str
    label: Literal["supports", "contradicts", "nuances", "unrelated"]
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str
    similarity: float | None = None
    a: VerdictClaimSide
    b: VerdictClaimSide


class ProjectDetailResponse(CamelModel):
    """Full detail view of a project, its sources, conflicts, briefs, and active jobs."""

    project: ProjectHeader
    sources: list[ProjectSourceItem]
    conflicts: list[ConflictItem] = Field(default_factory=list)
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
    topics: list[str] = Field(default_factory=list)
    claims: list[ClaimItem] = Field(default_factory=list)
    verdicts: list[ConflictItem] = Field(default_factory=list)


class AnalystClaim(CamelModel):
    """Atomic claim extracted by the LLM from source text."""

    text: str = Field(min_length=20, max_length=400, description="Atomic, self-contained assertion")
    importance: int = Field(
        ge=1, le=5, description="Significance of finding: 5=central, 1=minor detail"
    )
    page_hint: int | None = Field(
        default=None, ge=1, description="Approximate source page if available"
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


class CriticCandidatePair(CamelModel):
    """Candidate pair of claims prepared for Critic LLM evaluation."""

    pair_id: str = Field(min_length=1, description="Deterministic pair key, e.g. vrd_<8hex>")
    source_tag_a: str = Field(min_length=1, description="Source tag of claim A, e.g. S1")
    claim_text_a: str = Field(min_length=1, description="Text of claim A")
    source_tag_b: str = Field(min_length=1, description="Source tag of claim B, e.g. S2")
    claim_text_b: str = Field(min_length=1, description="Text of claim B")


class CriticVerdict(CamelModel):
    """Verdict for an individual claim pair returned by the LLM."""

    pair_id: str = Field(
        description="Deterministic pair identifier matching requested candidate pair"
    )
    label: Literal["supports", "contradicts", "nuances", "unrelated"] = Field(
        description="Relationship stance between the two claims"
    )
    confidence: float = Field(ge=0.0, le=1.0, description="Heuristic linguistic certainty score")
    rationale: str = Field(
        min_length=10,
        max_length=300,
        description="One-sentence explanation of agreement or difference",
    )


class CriticOutputSchema(CamelModel):
    """Structured LLM output schema for Gemini provider validation."""

    verdicts: list[CriticVerdict] = Field(description="Verdicts for all evaluated candidate pairs")


class CriticInput(CamelModel):
    """Input payload to run the Critic agent on a source."""

    project_id: str
    source_id: str


class CriticOutput(CamelModel):
    """Result payload emitted at the conclusion of critique."""

    pairs_judged: int = Field(ge=0, description="Number of candidate pairs evaluated in this run")
    supports: int = Field(ge=0, description="Count of supporting pairs")
    contradicts: int = Field(ge=0, description="Count of contradicting pairs")
    nuances: int = Field(ge=0, description="Count of nuanced pairs")
    unrelated: int = Field(ge=0, description="Count of unrelated pairs")
    skipped_existing: int = Field(
        ge=0,
        description="Count of candidate pairs skipped because already judged",
    )


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
