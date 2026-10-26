"""Health check route with liveness and database readiness probe."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Response, status
from fastapi.responses import JSONResponse

from research_desk.core.config import Settings, get_settings
from research_desk.core.schemas import HealthConfigured, HealthResponse
from research_desk.stores.db import check_db_readiness
from research_desk.stores.vector import get_vector_store

router = APIRouter(prefix="/api", tags=["health"])


@router.get(
    "/health",
    response_model=HealthResponse,
    status_code=status.HTTP_200_OK,
    summary="Application liveness and readiness check",
)
async def get_health(
    response: Response,
    db: int | None = Query(
        None, description="Set to 1 to check database and vector store readiness"
    ),
    settings: Settings = Depends(get_settings),
) -> HealthResponse | JSONResponse:
    """Returns application status and service readiness without exposing secrets."""
    if db == 1:
        # Check PostgreSQL
        pg_ok = await check_db_readiness(settings)
        pg_status = "up" if pg_ok else "down"

        # Check Qdrant
        qdrant_status = "down"
        try:
            store = get_vector_store(settings)
            qdrant_ok = await store.ping()
            qdrant_status = "up" if qdrant_ok else "down"
        except Exception:
            qdrant_status = "down"

        is_healthy = pg_status == "up" and qdrant_status == "up"
        status_code = status.HTTP_200_OK if is_healthy else status.HTTP_503_SERVICE_UNAVAILABLE

        return JSONResponse(
            status_code=status_code,
            content={
                "ok": is_healthy,
                "db": {
                    "postgres": pg_status,
                    "qdrant": qdrant_status,
                },
            },
        )

    return HealthResponse(
        ok=True,
        configured=HealthConfigured(
            gemini=bool(settings.GEMINI_API_KEY.get_secret_value()),
            postgres=bool(settings.DATABASE_URL.get_secret_value()),
            qdrant=bool(settings.QDRANT_URL),
        ),
    )
