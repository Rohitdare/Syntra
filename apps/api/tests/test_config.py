"""Tests for application settings and security constraints."""

import pytest
from pydantic import ValidationError

from research_desk.core.config import Settings


def test_auth_dev_mode_allowed_in_local() -> None:
    settings = Settings(APP_ENV="local", AUTH_MODE="dev")
    assert settings.AUTH_MODE == "dev"
    assert settings.APP_ENV == "local"


def test_auth_dev_mode_refused_outside_local() -> None:
    with pytest.raises(ValidationError) as exc_info:
        Settings(APP_ENV="production", AUTH_MODE="dev")
    assert "AUTH_MODE=dev is only permitted when APP_ENV=local" in str(exc_info.value)

    with pytest.raises(ValidationError) as exc_info_staging:
        Settings(APP_ENV="staging", AUTH_MODE="dev")
    assert "AUTH_MODE=dev is only permitted when APP_ENV=local" in str(exc_info_staging.value)


def test_secrets_redacted_in_repr() -> None:
    settings = Settings(
        GEMINI_API_KEY="super_secret_gemini_key",  # type: ignore[arg-type]
        DATABASE_URL="postgresql://usr:secret_pass@localhost/db",  # type: ignore[arg-type]
        QDRANT_API_KEY="super_secret_qdrant_key",  # type: ignore[arg-type]
    )
    repr_str = repr(settings)
    assert "super_secret_gemini_key" not in repr_str
    assert "secret_pass" not in repr_str
    assert "super_secret_qdrant_key" not in repr_str
    assert "**********" in repr_str


def test_cors_origins_parsing() -> None:
    settings = Settings(CORS_ALLOWED_ORIGINS="http://localhost:3000, https://app.example.com")  # type: ignore[arg-type]
    assert settings.CORS_ALLOWED_ORIGINS == ["http://localhost:3000", "https://app.example.com"]
