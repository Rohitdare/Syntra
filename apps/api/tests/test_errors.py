"""Tests for error envelope handling and exception formatters."""

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from research_desk.api.middleware import setup_middleware
from research_desk.core.errors import AppError, register_error_handlers


@pytest.mark.asyncio
async def test_app_error_handled_with_envelope() -> None:
    app = FastAPI()
    setup_middleware(app, allowed_origins=["*"])
    register_error_handlers(app)

    @app.get("/trigger-app-error")
    async def trigger_app_error() -> None:
        raise AppError(code="NO_TEXT", retryable=False)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/trigger-app-error")
        assert response.status_code == 422
        data = response.json()
        assert "error" in data
        assert data["error"]["code"] == "NO_TEXT"
        assert "No readable text found" in data["error"]["message"]
        assert data["error"]["retryable"] is False
        assert "X-Request-Id" in response.headers


@pytest.mark.asyncio
async def test_unhandled_exception_does_not_leak_stack_trace() -> None:
    app = FastAPI()
    setup_middleware(app, allowed_origins=["*"])
    register_error_handlers(app)

    @app.get("/trigger-crash")
    async def trigger_crash() -> None:
        raise RuntimeError("Sensitive internal database connection failed at /app/secret.py:42")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/trigger-crash")
        assert response.status_code == 500
        data = response.json()
        assert data["error"]["code"] == "INTERNAL"
        # Must not leak the stack trace or error message to the client
        assert "Sensitive internal database connection" not in response.text
        assert "secret.py" not in response.text
        assert "X-Request-Id" in response.headers
