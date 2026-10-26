"""Unit tests for GeminiProvider with fake client verifying batching, retries, and errors."""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import BaseModel

from research_desk.core.config import Settings
from research_desk.providers.gemini import GeminiProvider
from research_desk.providers.llm import CallContext, ProviderError


class SampleSchema(BaseModel):
    title: str
    score: int


def get_test_settings() -> Settings:
    return Settings(
        GEMINI_API_KEY="test-key-1234",
        DATABASE_URL="postgresql://user:pass@localhost:5432/testdb",
        QDRANT_URL="http://localhost:6333",
        APP_ENV="local",
        AUTH_MODE="dev",
        EMBEDDING_DIM=768,
        EMBED_BATCH_SIZE=2,
        LLM_MAX_RETRIES=2,
        LLM_TIMEOUT_S=5.0,
        LLM_MIN_INTERVAL_MS=0,
        EMBED_MIN_INTERVAL_MS=0,
    )


def make_test_context() -> CallContext:
    return CallContext(
        user_id=uuid.uuid4(),
        project_id="prj_12345678",
        job_id=uuid.uuid4(),
    )


@pytest.mark.asyncio
async def test_embed_documents_batching() -> None:
    """Ensure texts are sliced into batches of EMBED_BATCH_SIZE."""
    settings = get_test_settings()
    provider = GeminiProvider(settings)

    async def mock_embed_call(*, model: str, contents: list[str], config: Any) -> MagicMock:
        mock_res = MagicMock()
        mock_embed = MagicMock()
        mock_embed.values = [0.1] * 768
        mock_res.embeddings = [mock_embed] * len(contents)
        return mock_res

    with patch.object(
        provider.client.aio.models,
        "embed_content",
        new=AsyncMock(side_effect=mock_embed_call),
    ) as mock_call:
        texts = ["text1", "text2", "text3", "text4", "text5"]
        ctx = make_test_context()
        vectors = await provider.embed_texts(texts, kind="document", ctx=ctx)

        assert len(vectors) == 5
        assert all(len(v) == 768 for v in vectors)
        # With batch_size=2 and 5 texts, should call 3 times (2, 2, 1)
        assert mock_call.call_count == 3


@pytest.mark.asyncio
async def test_embed_documents_dimension_mismatch() -> None:
    """Ensure ProviderError is raised if returned embedding dimension differs from EMBEDDING_DIM."""
    settings = get_test_settings()
    provider = GeminiProvider(settings)

    # Return vector of 512 dims instead of 768
    mock_embed = MagicMock()
    mock_embed.values = [0.1] * 512
    mock_batch_res = MagicMock()
    mock_batch_res.embeddings = [mock_embed]

    with patch.object(
        provider.client.aio.models,
        "embed_content",
        new=AsyncMock(return_value=mock_batch_res),
    ):
        ctx = make_test_context()
        with pytest.raises(ProviderError) as exc_info:
            await provider.embed_texts(["text1"], kind="document", ctx=ctx)
        assert "dimension mismatch" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_call_structured_success() -> None:
    """Ensure call parses JSON conforming to Pydantic model."""
    settings = get_test_settings()
    provider = GeminiProvider(settings)

    mock_usage = MagicMock()
    mock_usage.prompt_token_count = 15
    mock_usage.candidates_token_count = 25

    mock_resp = MagicMock()
    mock_resp.text = '{"title": "Test Title", "score": 95}'
    mock_resp.usage_metadata = mock_usage

    with patch.object(
        provider.client.aio.models,
        "generate_content",
        new=AsyncMock(return_value=mock_resp),
    ):
        ctx = make_test_context()
        res = await provider.call(
            tier="fast",
            system="System prompt",
            user="Generate title",
            schema=SampleSchema,
            ctx=ctx,
        )

        assert isinstance(res.data, SampleSchema)
        assert res.data.title == "Test Title"
        assert res.data.score == 95
        assert res.usage.get("tokens_in") == 15
        assert res.usage.get("tokens_out") == 25


@pytest.mark.asyncio
async def test_call_retries_on_invalid_schema() -> None:
    """Ensure invalid JSON output is retried up to LLM_MAX_RETRIES with error context."""
    settings = get_test_settings()
    provider = GeminiProvider(settings)

    mock_bad_resp = MagicMock()
    mock_bad_resp.text = '{"title": "Missing Score"}'
    mock_bad_resp.usage_metadata = None

    mock_good_resp = MagicMock()
    mock_good_resp.text = '{"title": "Fixed", "score": 100}'
    mock_good_resp.usage_metadata = None

    with patch.object(
        provider.client.aio.models,
        "generate_content",
        new=AsyncMock(side_effect=[mock_bad_resp, mock_good_resp]),
    ) as mock_call:
        ctx = make_test_context()
        res = await provider.call(
            tier="fast",
            system="System prompt",
            user="Generate title",
            schema=SampleSchema,
            ctx=ctx,
        )

        assert res.data.score == 100
        assert mock_call.call_count == 2
