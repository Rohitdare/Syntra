"""Pydantic models and base schemas with camelCase serialization."""

from pydantic import BaseModel, ConfigDict
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
