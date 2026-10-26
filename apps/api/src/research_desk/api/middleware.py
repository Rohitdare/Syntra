"""Middleware for request ID generation, extraction, and CORS configuration."""

import uuid
from typing import Awaitable, Callable

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Ensures every incoming request has an X-Request-Id, generating one if absent."""

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        incoming_id = request.headers.get("X-Request-Id")
        if incoming_id and len(incoming_id.strip()) > 0:
            request_id = incoming_id.strip()
        else:
            request_id = f"req_{uuid.uuid4().hex[:24]}"

        # Store on request.state for exception handlers and route loggers
        request.state.request_id = request_id

        try:
            response = await call_next(request)
        except Exception:
            from research_desk.core.errors import ERROR_MESSAGES, create_error_response

            return create_error_response(
                status_code=500,
                code="INTERNAL",
                message=ERROR_MESSAGES["INTERNAL"],
                request_id=request_id,
                retryable=True,
            )

        response.headers["X-Request-Id"] = request_id
        return response


def setup_middleware(app: FastAPI, allowed_origins: list[str]) -> None:
    """Register request ID and CORS middleware onto the FastAPI app."""
    app.add_middleware(RequestIdMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "Idempotency-Key", "X-Request-Id"],
        expose_headers=["X-Request-Id", "X-Job-Id", "Retry-After"],
    )
