"""LLM Provider protocol, call context, and provider errors.

Per docs/02-DESIGN-DOC.md Section 5.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Generic, Literal, Protocol, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)
Tier = Literal["fast", "strong"]


@dataclass(frozen=True)
class CallContext:
    """Invocation context for rate limiting, usage tracking, and audit logging."""

    user_id: uuid.UUID
    project_id: str | None = None
    job_id: uuid.UUID | None = None


@dataclass(frozen=True)
class LLMResult(Generic[T]):
    """Validated structured output and token usage."""

    data: T
    usage: dict[str, int] = field(default_factory=dict)


class ProviderError(Exception):
    """Base error for LLM/Embedding provider failures with user-safe message."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        retryable: bool = False,
        retry_after_seconds: float | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable
        self.retry_after_seconds = retry_after_seconds


class LLMProvider(Protocol):
    """Protocol for calling large language models with structured JSON output."""

    async def call(
        self,
        *,
        tier: Tier,
        system: str,
        user: str,
        schema: type[T],
        temperature: float = 0.2,
        ctx: CallContext,
    ) -> LLMResult[T]: ...
