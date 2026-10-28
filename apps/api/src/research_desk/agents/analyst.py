"""Analyst agent implementation.

Per docs/04-AGENT-SPECS.md Section 2 and docs/08-STAGE-4-ANALYST-IMPLEMENTATION-PLAN.md:
- Reads cleaned source text from PostgreSQL.
- Enforces MAX_ANALYST_CHARS (80,000) input truncation (50k head + 30k tail with omission notice).
- Makes exactly one fast-tier Gemini LLM call to extract title, summary, topics, and claims.
- Defends against prompt injection and ensures strict evidence provenance.
- Embeds all claims in one batch using the configured 768-dim embedding model.
- Strictly adheres to Rule 13 two-store safe write sequence:
    Step A: PostgreSQL replaces claims, stores summary/topics, keeps stage_analyzed=False.
    Step B: Upserts deterministic claim points into Qdrant and prunes stale points.
    Step C: Sets stage_analyzed=True and claim_count in PostgreSQL.
"""

from __future__ import annotations

import hashlib
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from research_desk.agents.prompts import (
    build_analyst_system_prompt,
    build_analyst_user_prompt,
)
from research_desk.core.config import Settings, get_settings
from research_desk.core.errors import AppError
from research_desk.core.ids import claim_id
from research_desk.core.schemas import (
    AnalystClaim,
    AnalystInput,
    AnalystOutput,
    AnalystOutputSchema,
)
from research_desk.providers.embeddings import EmbeddingProvider
from research_desk.providers.llm import CallContext, LLMProvider
from research_desk.stores.models import Claim
from research_desk.stores.repos.claims import ClaimRepo
from research_desk.stores.repos.sources import SourceRepo
from research_desk.stores.vector import ClaimPoint, VectorStore

MAX_ANALYST_CHARS: int = 80_000
TRUNCATION_HEAD_CHARS: int = 50_000
TRUNCATION_TAIL_CHARS: int = 30_000
OMISSION_NOTICE: str = "\n\n[... content omitted for length: middle portion truncated ...]\n\n"

KNOWN_DOCUMENT_EXTENSIONS: tuple[str, ...] = (
    ".pdf",
    ".txt",
    ".docx",
    ".doc",
    ".html",
    ".htm",
    ".md",
)


def truncate_text(text: str, max_chars: int = MAX_ANALYST_CHARS) -> str:
    """Truncate text exceeding max_chars, retaining first 50k and last 30k chars."""
    if len(text) <= max_chars:
        return text
    head = text[:TRUNCATION_HEAD_CHARS]
    tail = text[-TRUNCATION_TAIL_CHARS:]
    return f"{head}{OMISSION_NOTICE}{tail}"


def should_refine_title(current_title: str) -> bool:
    """Determine whether the current title is an auto-generated placeholder or filename.

    Returns True if current_title is 'Pasted Text' or appears to be a filename or URL.
    Preserves custom user-entered titles.
    """
    clean = current_title.strip()
    if not clean:
        return True
    lower = clean.lower()
    if lower == "pasted text":
        return True
    if lower.startswith("http://") or lower.startswith("https://"):
        return True
    for ext in KNOWN_DOCUMENT_EXTENSIONS:
        if lower.endswith(ext):
            return True
    return False


def sanitize_page_hint(
    page_hint: int | None,
    source_kind: str,
    page_count: int | None,
) -> int | None:
    """Ensure page_hint is only populated for paginated sources and within valid ranges."""
    if page_hint is None:
        return None
    if source_kind != "pdf":
        return None
    if page_hint < 1:
        return None
    if page_count is not None and page_hint > page_count:
        return None
    return page_hint


@dataclass(frozen=True)
class AnalystRepos:
    """Repositories required by the Analyst agent."""

    sources: SourceRepo
    claims: ClaimRepo


@dataclass(frozen=True)
class AnalystDeps:
    """Injected dependencies for the Analyst agent."""

    repos: Any  # Supports AnalystRepos or any object with .sources and .claims
    vectors: VectorStore
    embeddings: EmbeddingProvider
    llm: LLMProvider
    cfg: Settings | None = None


Emit = Callable[[str, dict[str, Any] | None, str | None], Awaitable[None]]


async def run(
    inp: AnalystInput,
    deps: AnalystDeps,
    emit: Emit,
    ctx: CallContext,
) -> AnalystOutput:
    """Execute the Analyst agent workflow."""
    cfg = deps.cfg or get_settings()

    await emit("start", None, "Starting source analysis...")

    # 1. Verify source existence and collection status
    source = await deps.repos.sources.get(inp.project_id, inp.source_id)
    if source is None:
        raise AppError(
            "NOT_FOUND",
            f"Source '{inp.source_id}' not found in project '{inp.project_id}'.",
        )
    if not source.stage_collected:
        raise AppError(
            "BAD_REQUEST",
            f"Source '{inp.source_id}' must be collected before analysis.",
        )

    # 2. Retrieve cleaned text from PostgreSQL
    source_text_row = await deps.repos.sources.get_text(inp.project_id, inp.source_id)
    if source_text_row is None or not source_text_row.text:
        raise AppError("NO_TEXT", f"No cleaned text found for source '{inp.source_id}'.")

    raw_text = source_text_row.text
    if len(raw_text.strip()) < cfg.MIN_SOURCE_CHARS:
        raise AppError(
            "NO_TEXT",
            (
                f"Source text is too short to analyze ({len(raw_text)} chars, "
                f"minimum {cfg.MIN_SOURCE_CHARS})."
            ),
        )

    # 3. Truncate text if needed (head 50k + tail 30k with notice)
    text_to_analyze = truncate_text(raw_text, max_chars=cfg.MAX_ANALYST_CHARS)
    await emit(
        "doc_read",
        {"count": len(text_to_analyze), "docType": "source_text"},
        "Reading cleaned source text...",
    )

    # 4. Single structured fast-tier LLM call
    await emit("llm_call", {"tier": "fast"}, "Extracting claims and summary...")

    system_prompt = build_analyst_system_prompt(max_claims=cfg.MAX_CLAIMS_PER_SOURCE)
    user_prompt = build_analyst_user_prompt(
        title=source.title,
        kind=source.kind,
        text=text_to_analyze,
    )

    llm_result = await deps.llm.call(
        tier="fast",
        system=system_prompt,
        user=user_prompt,
        schema=AnalystOutputSchema,
        temperature=0.2,
        ctx=ctx,
    )
    llm_data: AnalystOutputSchema = llm_result.data

    # Cap claims at MAX_CLAIMS_PER_SOURCE
    raw_claims = llm_data.claims[: cfg.MAX_CLAIMS_PER_SOURCE]

    # Sanitize page_hints and build validated claims
    sanitized_claims: list[AnalystClaim] = []
    for c in raw_claims:
        sanitized_page_hint = sanitize_page_hint(
            page_hint=c.page_hint,
            source_kind=source.kind,
            page_count=source.page_count,
        )
        sanitized_claims.append(
            AnalystClaim(
                text=c.text,
                importance=c.importance,
                page_hint=sanitized_page_hint,
            )
        )

    # 5. Batched embedding generation
    embeddings: list[list[float]] = []
    if sanitized_claims:
        await emit("status", None, f"Generating embeddings for {len(sanitized_claims)} claims...")
        claim_texts = [c.text for c in sanitized_claims]
        embeddings = await deps.embeddings.embed_texts(claim_texts, kind="document", ctx=ctx)

        if len(embeddings) != len(sanitized_claims):
            raise AppError(
                "INTERNAL",
                (
                    f"Embedding count ({len(embeddings)}) does not match "
                    f"claim count ({len(sanitized_claims)})."
                ),
            )
        for emb in embeddings:
            if len(emb) != cfg.EMBEDDING_DIM:
                raise AppError(
                    "INTERNAL",
                    f"Vector dimension mismatch: expected {cfg.EMBEDDING_DIM}, got {len(emb)}.",
                )

    # 6. Step A: PostgreSQL transaction - persist claims and summary, keeping stage_analyzed=False
    db_claims: list[Claim] = []
    for idx, c in enumerate(sanitized_claims):
        cid = claim_id(inp.source_id, idx)
        text_hash = hashlib.sha256(c.text.encode("utf-8")).hexdigest()
        db_claims.append(
            Claim(
                project_id=inp.project_id,
                id=cid,
                source_id=inp.source_id,
                claim_index=idx,
                text=c.text,
                text_hash=text_hash,
                importance=c.importance,
                page_hint=c.page_hint,
                embedding_model=cfg.GEMINI_EMBEDDING_MODEL,
            )
        )

    new_title = (
        llm_data.title.strip()[:200]
        if should_refine_title(source.title) and llm_data.title.strip()
        else None
    )

    await deps.repos.claims.replace_claims(inp.project_id, inp.source_id, db_claims)
    await deps.repos.sources.update_stage_flags(
        project_id=inp.project_id,
        source_id=inp.source_id,
        summary=llm_data.summary,
        topics=list(llm_data.topics),
        title=new_title,
        stage_analyzed=False,
        stage_critiqued=False,
    )
    if hasattr(deps.repos.sources, "session"):
        await deps.repos.sources.session.commit()

    # 7. Step B: Qdrant vector indexing
    claim_points = [
        ClaimPoint(
            key=c.id,
            project_id=inp.project_id,
            source_id=inp.source_id,
            source_tag=source.tag,
            claim_index=c.claim_index,
            text=c.text,
            embedding=embeddings[c.claim_index],
            importance=c.importance,
            page_hint=c.page_hint,
            embedding_model=cfg.GEMINI_EMBEDDING_MODEL,
        )
        for c in db_claims
    ]

    if claim_points:
        await deps.vectors.upsert_claims(claim_points)

    # Prune any stale claims from previous runs
    await deps.vectors.prune(
        project_id=inp.project_id,
        source_id=inp.source_id,
        type_="claim",
        keep_count=len(claim_points),
    )

    # 8. Step C: Mark stage_analyzed = True in PostgreSQL
    await deps.repos.sources.update_stage_flags(
        project_id=inp.project_id,
        source_id=inp.source_id,
        stage_analyzed=True,
        claim_count=len(db_claims),
    )
    if hasattr(deps.repos.sources, "session"):
        await deps.repos.sources.session.commit()

    # 9. Emit results
    await emit(
        "doc_write",
        {"count": len(db_claims), "docType": "claim"},
        f"Stored {len(db_claims)} claims.",
    )

    output = AnalystOutput(
        claim_count=len(db_claims),
        topics=list(llm_data.topics),
    )

    await emit("result", output.model_dump(by_alias=True), "Analysis complete.")
    await emit("complete", None, "Analysis stage completed.")
    return output
