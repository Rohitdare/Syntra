"""Embedding provider protocol and types.

Per docs/02-DESIGN-DOC.md Section 5.
"""

from __future__ import annotations

from typing import Literal, Protocol, Sequence

from research_desk.providers.llm import CallContext

EmbedKind = Literal["document", "query"]


class EmbeddingProvider(Protocol):
    """Protocol for embedding batches of text."""

    async def embed_texts(
        self,
        texts: Sequence[str],
        kind: EmbedKind,
        *,
        ctx: CallContext,
    ) -> list[list[float]]:
        """Embed a sequence of texts.

        Guarantees:
        - Output list length exactly matches input texts length.
        - Every vector length matches EMBEDDING_DIM.
        """
        ...
