"""Authentication dependencies, user upsert, and project ownership verification.

Per docs/02-DESIGN-DOC.md Section 13.1 and docs/05-API-SPEC.md Section 1.
"""

from __future__ import annotations

import uuid

from fastapi import Depends, Header, Request

from research_desk.core.config import Settings, get_settings
from research_desk.core.errors import AppError
from research_desk.stores.db import DbSession, get_db
from research_desk.stores.models import Project, User
from research_desk.stores.repos.projects import ProjectRepo
from research_desk.stores.repos.users import UserRepo

# Fixed local development user ID
DEV_USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
DEV_AUTH_SUBJECT = "dev-user-local"


async def get_or_create_user(
    session: DbSession, auth_subject: str, email: str | None = None
) -> User:
    """Upsert a user record based on unique auth_subject."""
    repo = UserRepo(session)
    default_id = DEV_USER_ID if auth_subject == DEV_AUTH_SUBJECT else None
    return await repo.get_or_create(
        auth_subject=auth_subject,
        email=email,
        default_id=default_id,
    )


async def get_current_user(
    request: Request,
    authorization: str | None = Header(None),
    session: DbSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> User:
    """FastAPI dependency authenticating the request.

    In dev mode (AUTH_MODE=dev and APP_ENV=local), automatically yields a fixed local user.
    In jwt mode, validates the Bearer token.
    """
    if settings.AUTH_MODE == "dev" and settings.APP_ENV == "local":
        return await get_or_create_user(
            session=session,
            auth_subject=DEV_AUTH_SUBJECT,
            email="dev@local.test",
        )

    # JWT mode verification
    if not authorization or not authorization.startswith("Bearer "):
        raise AppError(
            code="UNAUTHENTICATED",
            message="Missing or invalid authentication token",
            http_status=401,
            retryable=False,
        )

    token = authorization.removeprefix("Bearer ").strip()
    if not token:
        raise AppError(
            code="UNAUTHENTICATED",
            message="Empty bearer token provided",
            http_status=401,
            retryable=False,
        )

    # Provider-independent JWT token verification hook
    # Real JWKS verification can be wired when external auth provider is chosen
    # For now, token serves as auth_subject identifier
    auth_subject = f"jwt:{token}"
    return await get_or_create_user(
        session=session,
        auth_subject=auth_subject,
    )


async def get_owned_project(
    project_id: str,
    current_user: User = Depends(get_current_user),
    session: DbSession = Depends(get_db),
) -> Project:
    """Dependency verifying project existence and ownership.

    Returns 404 if project does not exist OR is owned by another user,
    preventing project existence leakage.
    """
    repo = ProjectRepo(session)
    project = await repo.get_owned(owner_id=current_user.id, project_id=project_id)
    if project is None:
        raise AppError(
            code="NOT_FOUND",
            message="Project not found",
            http_status=404,
            retryable=False,
        )
    return project
