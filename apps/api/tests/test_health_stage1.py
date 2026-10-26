"""Tests for GET /api/health and GET /api/health?db=1 readiness probing."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from research_desk.main import app


@pytest.mark.asyncio
async def test_health_check_basic() -> None:
    """GET /api/health returns 200 and configured flags."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        assert "configured" in body
        assert isinstance(body["configured"]["gemini"], bool)
        assert isinstance(body["configured"]["postgres"], bool)
        assert isinstance(body["configured"]["qdrant"], bool)


@pytest.mark.asyncio
async def test_health_check_db_healthy() -> None:
    """GET /api/health?db=1 returns 200 when both postgres and qdrant are healthy."""
    transport = ASGITransport(app=app)
    with (
        patch(
            "research_desk.api.routes.health.check_db_readiness", new=AsyncMock(return_value=True)
        ),
        patch(
            "research_desk.stores.vector.QdrantVectorStore.ping", new=AsyncMock(return_value=True)
        ),
    ):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/health?db=1")
            assert resp.status_code == 200
            body = resp.json()
            assert body["ok"] is True
            assert body["db"]["postgres"] == "up"
            assert body["db"]["qdrant"] == "up"


@pytest.mark.asyncio
async def test_health_check_db_unhealthy() -> None:
    """GET /api/health?db=1 returns 503 when postgres or qdrant is unhealthy."""
    transport = ASGITransport(app=app)
    with (
        patch(
            "research_desk.api.routes.health.check_db_readiness", new=AsyncMock(return_value=True)
        ),
        patch(
            "research_desk.stores.vector.QdrantVectorStore.ping", new=AsyncMock(return_value=False)
        ),
    ):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/health?db=1")
            assert resp.status_code == 503
            body = resp.json()
            assert body["ok"] is False
            assert body["db"]["postgres"] == "up"
            assert body["db"]["qdrant"] == "down"
