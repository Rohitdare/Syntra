"""Tests for GET /api/health endpoint."""

import pytest
from httpx import ASGITransport, AsyncClient

from research_desk.core.config import Settings
from research_desk.main import create_app


@pytest.mark.asyncio
async def test_health_endpoint_success() -> None:
    settings = Settings(
        GEMINI_API_KEY="test_key",  # type: ignore[arg-type]
        DATABASE_URL="postgresql://user:pass@localhost:5432/db",  # type: ignore[arg-type]
        QDRANT_URL="http://localhost:6333",
    )
    app = create_app(settings)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert data["configured"] == {
            "gemini": True,
            "postgres": True,
            "qdrant": True,
        }
        # Verify no secret values were exposed
        raw_text = response.text
        assert "test_key" not in raw_text
        assert "pass" not in raw_text
        # Verify X-Request-Id header is present
        assert "X-Request-Id" in response.headers


@pytest.mark.asyncio
async def test_health_endpoint_db_option_implemented() -> None:
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/health?db=1")
        # In test environment without running services, returns 503 with db status
        assert response.status_code in (200, 503)
        data = response.json()
        assert "db" in data
        assert "postgres" in data["db"]
        assert "qdrant" in data["db"]
