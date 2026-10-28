"""API router definitions."""

from research_desk.api.routes.health import router as health_router
from research_desk.api.routes.jobs import router as jobs_router
from research_desk.api.routes.projects import router as projects_router
from research_desk.api.routes.sources import router as sources_router

__all__ = ["health_router", "jobs_router", "projects_router", "sources_router"]
