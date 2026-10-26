"""Google Gemini provider implementation for LLM and Embeddings.

Per Non-negotiable Rule 2:
This is the ONLY module in the entire application that imports google.genai.
Structured output requested as JSON and validated with Pydantic.
Enforces concurrency semaphores, rate intervals, bounded retries, and timeouts.
"""

from __future__ import annotations

import asyncio
import json
import random
import time
import uuid
from typing import Any, Callable, Coroutine, Sequence, TypeVar

from google import genai
from google.genai import types
from pydantic import BaseModel, ValidationError

from research_desk.core.config import Settings
from research_desk.providers.embeddings import EmbeddingProvider, EmbedKind
from research_desk.providers.llm import (
    CallContext,
    LLMProvider,
    LLMResult,
    ProviderError,
    Tier,
)

T = TypeVar("T", bound=BaseModel)

UsageRecorder = Callable[
    [uuid.UUID, str | None, uuid.UUID | None, str, str, str, int, int, int],
    Coroutine[Any, Any, None],
]


class GeminiProvider(LLMProvider, EmbeddingProvider):
    """Unified Gemini adapter handling LLM completions and embeddings."""

    def __init__(
        self,
        settings: Settings,
        usage_recorder: UsageRecorder | None = None,
    ) -> None:
        self.settings = settings
        self.usage_recorder = usage_recorder

        api_key = settings.GEMINI_API_KEY.get_secret_value() if settings.GEMINI_API_KEY else ""
        self.client = genai.Client(api_key=api_key)

        self._concurrency_sem = asyncio.Semaphore(settings.GEMINI_MAX_CONCURRENCY)
        self._llm_last_call_time = 0.0
        self._embed_last_call_time = 0.0
        self._pace_lock = asyncio.Lock()

    async def _pace(self, min_interval_ms: int, is_llm: bool) -> None:
        """Pace requests to respect minimum interval between calls."""
        async with self._pace_lock:
            now = time.monotonic()
            last = self._llm_last_call_time if is_llm else self._embed_last_call_time
            elapsed_ms = (now - last) * 1000.0
            wait_ms = min_interval_ms - elapsed_ms
            if wait_ms > 0:
                await asyncio.sleep(wait_ms / 1000.0)
            if is_llm:
                self._llm_last_call_time = time.monotonic()
            else:
                self._embed_last_call_time = time.monotonic()

    async def call(
        self,
        *,
        tier: Tier,
        system: str,
        user: str,
        schema: type[T],
        temperature: float = 0.2,
        ctx: CallContext,
    ) -> LLMResult[T]:
        """Call Gemini model with structured output validated against schema."""
        if not self.settings.LLM_ENABLED:
            raise ProviderError(
                code="QUOTA_EXCEEDED",
                message="AI provider is globally disabled by kill switch",
                retryable=False,
            )

        model_name = (
            self.settings.GEMINI_MODEL_FAST if tier == "fast" else self.settings.GEMINI_MODEL_STRONG
        )

        prompt_user = user
        last_error_msg = ""

        for attempt in range(self.settings.LLM_MAX_RETRIES + 1):
            await self._pace(self.settings.LLM_MIN_INTERVAL_MS, is_llm=True)

            async with self._concurrency_sem:
                try:
                    config = types.GenerateContentConfig(
                        system_instruction=system,
                        temperature=temperature,
                        response_mime_type="application/json",
                        response_schema=schema,
                    )

                    response = await asyncio.wait_for(
                        self.client.aio.models.generate_content(
                            model=model_name,
                            contents=prompt_user,
                            config=config,
                        ),
                        timeout=self.settings.LLM_TIMEOUT_S,
                    )

                    text_content = response.text or ""
                    tokens_in = (
                        response.usage_metadata.prompt_token_count if response.usage_metadata else 0
                    )
                    tokens_out = (
                        response.usage_metadata.candidates_token_count
                        if response.usage_metadata
                        else 0
                    )

                    # Validate with Pydantic
                    parsed_dict = json.loads(text_content)
                    validated_data = schema.model_validate(parsed_dict)

                    if self.usage_recorder:
                        await self.usage_recorder(
                            ctx.user_id,
                            ctx.project_id,
                            ctx.job_id,
                            "gemini",
                            model_name,
                            "llm",
                            tokens_in or 0,
                            tokens_out or 0,
                            0,
                        )

                    return LLMResult(
                        data=validated_data,
                        usage={"tokens_in": tokens_in or 0, "tokens_out": tokens_out or 0},
                    )

                except asyncio.TimeoutError:
                    if attempt == self.settings.LLM_MAX_RETRIES:
                        raise ProviderError(
                            code="TIMEOUT",
                            message="Model request timed out",
                            retryable=True,
                        )
                    await asyncio.sleep(0.5 + random.uniform(0.1, 0.4))

                except (ValidationError, json.JSONDecodeError) as val_err:
                    last_error_msg = str(val_err)
                    if attempt == self.settings.LLM_MAX_RETRIES:
                        raise ProviderError(
                            code="LLM_INVALID",
                            message="Model response failed schema validation after retries",
                            retryable=True,
                        )
                    # Retry appending error hint to user prompt
                    prompt_user = (
                        f"{user}\n\nNote: Your previous response was invalid: "
                        f"{last_error_msg}. Please return valid JSON matching the schema."
                    )
                    await asyncio.sleep(0.5 * (attempt + 1) + random.uniform(0.1, 0.3))

                except Exception as exc:
                    err_str = str(exc).lower()
                    if "429" in err_str or "quota" in err_str or "resource_exhausted" in err_str:
                        if attempt == self.settings.LLM_MAX_RETRIES:
                            raise ProviderError(
                                code="LLM_QUOTA",
                                message=(
                                    "Provider quota or rate limit exceeded; please try again later"
                                ),
                                retryable=True,
                                retry_after_seconds=30.0,
                            )
                        wait_backoff = (2.0**attempt) + random.uniform(0.5, 1.5)
                        await asyncio.sleep(wait_backoff)
                    elif "500" in err_str or "503" in err_str or "unavailable" in err_str:
                        if attempt == self.settings.LLM_MAX_RETRIES:
                            raise ProviderError(
                                code="INTERNAL",
                                message="Model provider unavailable after retries",
                                retryable=True,
                            )
                        await asyncio.sleep(1.0 + random.uniform(0.1, 0.5))
                    else:
                        raise ProviderError(
                            code="INTERNAL",
                            message="Model request failed",
                            retryable=False,
                        )

        raise ProviderError(
            code="LLM_INVALID",
            message=f"Model failed: {last_error_msg}",
            retryable=True,
        )

    async def embed_texts(
        self,
        texts: Sequence[str],
        kind: EmbedKind,
        *,
        ctx: CallContext,
    ) -> list[list[float]]:
        """Embed a sequence of texts using Gemini embedding model."""
        if not texts:
            return []

        task_type = "RETRIEVAL_DOCUMENT" if kind == "document" else "RETRIEVAL_QUERY"
        model_name = self.settings.GEMINI_EMBEDDING_MODEL

        batch_size = max(1, self.settings.EMBED_BATCH_SIZE)
        all_embeddings: list[list[float]] = []

        for i in range(0, len(texts), batch_size):
            batch = list(texts[i : i + batch_size])
            await self._pace(self.settings.EMBED_MIN_INTERVAL_MS, is_llm=False)

            async with self._concurrency_sem:
                try:
                    config = types.EmbedContentConfig(
                        task_type=task_type,
                        output_dimensionality=self.settings.EMBEDDING_DIM,
                    )

                    response = await asyncio.wait_for(
                        self.client.aio.models.embed_content(
                            model=model_name,
                            contents=batch,
                            config=config,
                        ),
                        timeout=self.settings.EMBED_TIMEOUT_S,
                    )

                    batch_embeddings: list[list[float]] = []
                    if response.embeddings:
                        for emb in response.embeddings:
                            vals = emb.values or []
                            if len(vals) != self.settings.EMBEDDING_DIM:
                                raise ProviderError(
                                    code="INTERNAL",
                                    message=(
                                        f"Embedding dimension mismatch: expected "
                                        f"{self.settings.EMBEDDING_DIM}, got {len(vals)}"
                                    ),
                                    retryable=False,
                                )
                            batch_embeddings.append(list(vals))

                    if len(batch_embeddings) != len(batch):
                        raise ProviderError(
                            code="INTERNAL",
                            message=(
                                f"Expected {len(batch)} embeddings, "
                                f"received {len(batch_embeddings)}"
                            ),
                            retryable=True,
                        )

                    all_embeddings.extend(batch_embeddings)

                except asyncio.TimeoutError:
                    raise ProviderError(
                        code="TIMEOUT",
                        message="Embedding request timed out",
                        retryable=True,
                    )
                except ProviderError:
                    raise
                except Exception as exc:
                    err_str = str(exc).lower()
                    if "429" in err_str or "quota" in err_str or "resource_exhausted" in err_str:
                        raise ProviderError(
                            code="LLM_QUOTA",
                            message="Embedding quota or rate limit reached",
                            retryable=True,
                            retry_after_seconds=30.0,
                        )
                    raise ProviderError(
                        code="INTERNAL",
                        message="Embedding call failed",
                        retryable=True,
                    )

        if self.usage_recorder:
            await self.usage_recorder(
                ctx.user_id,
                ctx.project_id,
                ctx.job_id,
                "gemini",
                model_name,
                "embed",
                0,
                0,
                len(texts),
            )

        return all_embeddings
