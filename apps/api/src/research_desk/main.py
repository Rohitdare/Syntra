"""FastAPI application factory and entry point."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from research_desk.api.middleware import setup_middleware
from research_desk.api.routes.health import router as health_router
from research_desk.api.routes.jobs import router as jobs_router
from research_desk.api.routes.projects import router as projects_router
from research_desk.api.routes.sources import router as sources_router
from research_desk.core.config import Settings, get_settings
from research_desk.core.errors import register_error_handlers
from research_desk.core.logging import setup_logging
from research_desk.stores.db import get_sessionmaker
from research_desk.stores.repos.jobs import JobRepo
from research_desk.stores.repos.sources import SourceRepo


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create and configure the FastAPI application instance."""
    app_settings = settings or get_settings()

    setup_logging(level=app_settings.LOG_LEVEL)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        """Close persisted jobs left behind by a previous in-process API instance."""
        sessionmaker = get_sessionmaker(app_settings)
        async with sessionmaker() as session:
            async with session.begin():
                jobs = await JobRepo(session).interrupt_active_on_startup()
                sources = SourceRepo(session)
                for job in jobs:
                    if job.source_id and job.project_id:
                        await sources.update_stage_flags(
                            job.project_id,
                            job.source_id,
                            last_error="INTERRUPTED",
                        )
        yield

    app = FastAPI(
        title="Research Desk API",
        version="0.1.0",
        docs_url="/docs" if app_settings.APP_ENV != "production" else None,
        redoc_url=None,
        lifespan=lifespan,
    )

    if settings is not None:
        app.dependency_overrides[get_settings] = lambda: app_settings

    allowed_origins = (
        app_settings.CORS_ALLOWED_ORIGINS
        if isinstance(app_settings.CORS_ALLOWED_ORIGINS, list)
        else [app_settings.CORS_ALLOWED_ORIGINS]
    )
    setup_middleware(app, allowed_origins=allowed_origins)
    register_error_handlers(app)

    app.include_router(health_router)
    app.include_router(projects_router)
    app.include_router(sources_router)
    app.include_router(jobs_router)

    return app


app = create_app()
