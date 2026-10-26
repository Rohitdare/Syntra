"""Standardized error codes, exception types, user messages, and FastAPI handlers."""

import logging

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from research_desk.core.schemas import ErrorDetail, ErrorEnvelope

logger = logging.getLogger("research_desk.errors")

ERROR_MESSAGES: dict[str, str] = {
    "BAD_REQUEST": "Invalid request parameter or payload.",
    "UNAUTHENTICATED": "Authentication required. Please sign in.",
    "NOT_FOUND": "Requested resource was not found.",
    "PAYLOAD_TOO_LARGE": "File size exceeds the allowed limit.",
    "UNSUPPORTED_MEDIA_TYPE": "Unsupported file format. Please upload a valid PDF.",
    "LIMIT_REACHED": "A project limit or capacity cap has been reached.",
    "IDEMPOTENCY_CONFLICT": "An idempotency key was reused with different request payload.",
    "JOB_ACTIVE": "A stage is still running for this source.",
    "NO_TEXT": "No readable text found. If this is a scanned PDF, paste the text instead.",
    "FETCH_BLOCKED": "URL fetch was blocked for security reasons.",
    "FETCH_FAILED": "Failed to fetch or extract content from the URL.",
    "RATE_LIMITED": "Too many requests. Please try again later.",
    "QUOTA_EXCEEDED": "Daily usage limit reached. Please try again tomorrow.",
    "LLM_QUOTA": "AI provider quota reached. Please try again later.",
    "LLM_INVALID": "AI model output was invalid after retries.",
    "TIMEOUT": "Operation timed out.",
    "INTERRUPTED": "Job was interrupted by a server restart. Please retry.",
    "OVERLOADED": "Server is temporarily at full capacity. Please try again shortly.",
    "DB_ERROR": "Database is unavailable. Please try again shortly.",
    "VECTOR_DB_ERROR": (
        "Search index is unavailable. Please check the cluster or try again shortly."
    ),
    "INTERNAL": "An unexpected error occurred. Please quote the requestId if contacting support.",
}

HTTP_STATUS_MAP: dict[str, int] = {
    "BAD_REQUEST": status.HTTP_400_BAD_REQUEST,
    "UNAUTHENTICATED": status.HTTP_401_UNAUTHORIZED,
    "NOT_FOUND": status.HTTP_404_NOT_FOUND,
    "PAYLOAD_TOO_LARGE": status.HTTP_413_CONTENT_TOO_LARGE,
    "UNSUPPORTED_MEDIA_TYPE": status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
    "LIMIT_REACHED": status.HTTP_409_CONFLICT,
    "IDEMPOTENCY_CONFLICT": status.HTTP_409_CONFLICT,
    "JOB_ACTIVE": status.HTTP_409_CONFLICT,
    "NO_TEXT": status.HTTP_422_UNPROCESSABLE_CONTENT,
    "FETCH_BLOCKED": status.HTTP_422_UNPROCESSABLE_CONTENT,
    "FETCH_FAILED": status.HTTP_422_UNPROCESSABLE_CONTENT,
    "RATE_LIMITED": status.HTTP_429_TOO_MANY_REQUESTS,
    "QUOTA_EXCEEDED": status.HTTP_429_TOO_MANY_REQUESTS,
    "LLM_QUOTA": status.HTTP_503_SERVICE_UNAVAILABLE,
    "LLM_INVALID": status.HTTP_502_BAD_GATEWAY,
    "TIMEOUT": status.HTTP_504_GATEWAY_TIMEOUT,
    "INTERRUPTED": status.HTTP_503_SERVICE_UNAVAILABLE,
    "OVERLOADED": status.HTTP_503_SERVICE_UNAVAILABLE,
    "DB_ERROR": status.HTTP_503_SERVICE_UNAVAILABLE,
    "VECTOR_DB_ERROR": status.HTTP_503_SERVICE_UNAVAILABLE,
    "INTERNAL": status.HTTP_500_INTERNAL_SERVER_ERROR,
}


class AppError(Exception):
    """Base application domain exception mapped to standard error envelope."""

    def __init__(
        self,
        code: str,
        message: str | None = None,
        status_code: int | None = None,
        retryable: bool = False,
        retry_after_seconds: int | None = None,
    ) -> None:
        self.code = code
        self.message = message or ERROR_MESSAGES.get(code, "An error occurred.")
        self.status_code = status_code or HTTP_STATUS_MAP.get(code, status.HTTP_400_BAD_REQUEST)
        self.retryable = retryable
        self.retry_after_seconds = retry_after_seconds
        super().__init__(self.message)


def create_error_response(
    status_code: int,
    code: str,
    message: str,
    request_id: str,
    retryable: bool = False,
    retry_after_seconds: int | None = None,
) -> JSONResponse:
    """Format and return a standardized JSON error response."""
    envelope = ErrorEnvelope(
        error=ErrorDetail(
            code=code,
            message=message,
            request_id=request_id,
            retryable=retryable,
            retry_after_seconds=retry_after_seconds,
        )
    )
    headers = {"X-Request-Id": request_id}
    if retry_after_seconds is not None:
        headers["Retry-After"] = str(retry_after_seconds)
    return JSONResponse(
        status_code=status_code,
        content=envelope.model_dump(by_alias=True),
        headers=headers,
    )


def register_error_handlers(app: FastAPI) -> None:
    """Register custom exception handlers on the FastAPI application."""

    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
        request_id = getattr(request.state, "request_id", "req_unknown")
        return create_error_response(
            status_code=exc.status_code,
            code=exc.code,
            message=exc.message,
            request_id=request_id,
            retryable=exc.retryable,
            retry_after_seconds=exc.retry_after_seconds,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        request_id = getattr(request.state, "request_id", "req_unknown")
        # Replace FastAPI's default 422 with a clean 400 BAD_REQUEST error envelope
        first_error = exc.errors()[0] if exc.errors() else {}
        loc = " -> ".join(str(item) for item in first_error.get("loc", []))
        msg = first_error.get("msg", "Invalid input")
        detail_msg = f"Validation failed: {loc}: {msg}" if loc else f"Validation failed: {msg}"
        return create_error_response(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="BAD_REQUEST",
            message=detail_msg,
            request_id=request_id,
            retryable=False,
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        request_id = getattr(request.state, "request_id", "req_unknown")
        code = "NOT_FOUND" if exc.status_code == 404 else "BAD_REQUEST"
        message = str(exc.detail) if exc.detail else ERROR_MESSAGES.get(code, "HTTP error")
        return create_error_response(
            status_code=exc.status_code,
            code=code,
            message=message,
            request_id=request_id,
            retryable=False,
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        request_id = getattr(request.state, "request_id", "req_unknown")
        # Log stack trace server-side only; never send to client
        logger.exception("Unhandled server exception: %s (request_id=%s)", exc, request_id)
        return create_error_response(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="INTERNAL",
            message=ERROR_MESSAGES["INTERNAL"],
            request_id=request_id,
            retryable=True,
        )
