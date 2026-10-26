"""Unit tests for authentication dependency and project ownership isolation."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from research_desk.api.auth import DEV_USER_ID, get_current_user, get_owned_project
from research_desk.core.config import Settings
from research_desk.core.errors import AppError
from research_desk.stores.models import User


def get_dev_settings() -> Settings:
    return Settings(
        GEMINI_API_KEY="test-key",
        DATABASE_URL="postgresql://user:pass@localhost:5432/testdb",
        QDRANT_URL="http://localhost:6333",
        APP_ENV="local",
        AUTH_MODE="dev",
    )


def get_jwt_settings() -> Settings:
    return Settings(
        GEMINI_API_KEY="test-key",
        DATABASE_URL="postgresql://user:pass@localhost:5432/testdb",
        QDRANT_URL="http://localhost:6333",
        APP_ENV="production",
        AUTH_MODE="jwt",
    )


@pytest.mark.asyncio
async def test_get_current_user_dev_mode() -> None:
    """Dev mode yields the fixed local development user."""
    mock_session = AsyncMock()
    mock_request = MagicMock()

    # Mock UserRepo.get_by_auth_subject returning None, creating user with DEV_USER_ID
    with pytest.MonkeyPatch.context() as mp:
        mock_user = User(
            id=DEV_USER_ID,
            auth_subject="dev-user-local",
            email="dev@local.test",
        )
        mp.setattr(
            "research_desk.api.auth.get_or_create_user",
            AsyncMock(return_value=mock_user),
        )

        user = await get_current_user(
            request=mock_request,
            authorization=None,
            session=mock_session,
            settings=get_dev_settings(),
        )
        assert user.id == DEV_USER_ID
        assert user.auth_subject == "dev-user-local"


@pytest.mark.asyncio
async def test_get_current_user_jwt_missing_token() -> None:
    """JWT mode raises 401 UNAUTHENTICATED when Authorization header is absent."""
    mock_session = AsyncMock()
    mock_request = MagicMock()

    with pytest.raises(AppError) as exc_info:
        await get_current_user(
            request=mock_request,
            authorization=None,
            session=mock_session,
            settings=get_jwt_settings(),
        )
    assert exc_info.value.code == "UNAUTHENTICATED"
    assert exc_info.value.http_status == 401


@pytest.mark.asyncio
async def test_get_owned_project_404_on_foreign_project() -> None:
    """Accessing another user's project raises 404 NOT_FOUND to prevent leaking existence."""
    mock_session = AsyncMock()
    user_a = User(id=uuid.uuid4(), auth_subject="user-a")

    # ProjectRepo returns None when owner_id does not match
    with pytest.MonkeyPatch.context() as mp:
        mock_repo = MagicMock()
        mock_repo.get_owned = AsyncMock(return_value=None)
        mp.setattr("research_desk.api.auth.ProjectRepo", MagicMock(return_value=mock_repo))

        with pytest.raises(AppError) as exc_info:
            await get_owned_project(
                project_id="prj_other_user",
                current_user=user_a,
                session=mock_session,
            )
        assert exc_info.value.code == "NOT_FOUND"
        assert exc_info.value.http_status == 404
