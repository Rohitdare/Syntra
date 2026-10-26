"""Health check route."""

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import JSONResponse

from research_desk.core.config import Settings, get_settings
from research_desk.core.errors import AppError
from research_desk.core.schemas import HealthConfigured, HealthResponse

router = APIRouter(prefix="/api", tags=["health"])


@router.get(
    "/health",
    response_model=HealthResponse,
    status_code=status.HTTP_200_OK,
    summary="Application liveness and readiness check",
)
async def get_health(
    db: int | None = Query(None, description="Set to 1 to check database readiness (Stage 1)"),
    settings: Settings = Depends(get_settings),
) -> HealthResponse | JSONResponse:
    """Returns application status and boolean configuration states without exposing secrets."""
    if db == 1:
        # Per Stage 0 specification, ?db=1 is implemented in Stage 1 and returns 501
        raise AppError(
            code="NOT_IMPLEMENTED",
            message="Database readiness check (?db=1) is implemented in Stage 1.",
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
        )

    return HealthResponse(
        ok=True,
        configured=HealthConfigured(
            gemini=bool(settings.GEMINI_API_KEY.get_secret_value()),
            postgres=bool(settings.DATABASE_URL.get_secret_value()),
            qdrant=bool(settings.QDRANT_URL),
        ),
    )
