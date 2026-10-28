"""Collector agent implementation.

Per docs/04-AGENT-SPECS.md Section 1:
- Turn raw input (PDF, URL, or pasted text) into a stored source with embedded chunks.
- Computes deterministic SHA-256 content_hash and source_id.
- Persists source and source_text in PostgreSQL (initial stage flags False).
- Chunks text and generates vector embeddings.
- Upserts vector points into Qdrant and prunes stale points.
- Sets stage_collected = True in PostgreSQL only after writes are durable.
"""

from __future__ import annotations

import hashlib
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from pydantic import Field

from research_desk.core.config import Settings, get_settings
from research_desk.core.errors import AppError
from research_desk.core.ids import chunk_id, source_id
from research_desk.core.schemas import CamelModel
from research_desk.ingest.chunk import chunk_text
from research_desk.ingest.pdf import parse_pdf
from research_desk.ingest.text import parse_pasted_text
from research_desk.ingest.url import ingest_url
from research_desk.providers.embeddings import EmbeddingProvider
from research_desk.providers.llm import CallContext, LLMProvider
from research_desk.stores.repos.projects import ProjectRepo
from research_desk.stores.repos.sources import SourceRepo
from research_desk.stores.vector import ChunkPoint, VectorStore


class CollectorInput(CamelModel):
    """Input payload to the Collector agent."""

    project_id: str = Field(description="Target project ID")
    kind: Literal["pdf", "url", "text"] = Field(description="Source type")
    pdf_path: str | None = Field(default=None, description="Local path to uploaded PDF")
    url: str | None = Field(default=None, description="Public web address")
    text: str | None = Field(default=None, description="Raw pasted text")
    title: str | None = Field(default=None, description="Optional custom source title")


class CollectorOutput(CamelModel):
    """Output result produced by the Collector agent."""

    source_id: str
    tag: str
    title: str
    kind: str
    chunk_count: int
    char_count: int
    already_existed: bool


@dataclass(frozen=True)
class CollectorRepos:
    """Repositories needed by the Collector agent."""

    projects: ProjectRepo
    sources: SourceRepo


@dataclass(frozen=True)
class AgentDeps:
    """Injected dependencies for agents."""

    repos: CollectorRepos
    vectors: VectorStore
    embeddings: EmbeddingProvider
    llm: LLMProvider | None = None
    cfg: Settings | None = None


# Emit callable signature: (event_type, data_dict, message) -> Awaitable[None]
Emit = Callable[[str, dict[str, Any] | None, str | None], Awaitable[None]]


async def run(
    inp: CollectorInput,
    deps: AgentDeps,
    emit: Emit,
    ctx: CallContext,
) -> CollectorOutput:
    """Execute the Collector agent workflow."""
    cfg = deps.cfg or get_settings()

    await emit("start", None, "Starting source collection...")

    # 1. Ingest and extract text based on kind
    await emit("status", None, "Extracting and validating source content...")

    cleaned_text: str = ""
    page_offsets: list[int] = [0]
    page_count: int | None = None
    title: str = ""
    origin: str = ""

    if inp.kind == "pdf":
        if not inp.pdf_path:
            raise AppError("BAD_REQUEST", "PDF file path is required for PDF collection.")
        parsed_pdf = await parse_pdf(
            pdf_path=inp.pdf_path,
            max_pages=cfg.MAX_PDF_PAGES,
            max_chars=cfg.MAX_EXTRACTED_CHARS,
            min_chars=cfg.MIN_SOURCE_CHARS,
            timeout_s=cfg.PDF_PARSE_TIMEOUT_S,
        )
        cleaned_text = parsed_pdf.text
        page_offsets = parsed_pdf.page_offsets
        page_count = parsed_pdf.page_count
        origin = Path(inp.pdf_path).name
        title = (inp.title or "").strip() or Path(inp.pdf_path).stem or "PDF Document"

    elif inp.kind == "text":
        if not inp.text:
            raise AppError("BAD_REQUEST", "Pasted text is required for text collection.")
        parsed_text = parse_pasted_text(
            text=inp.text,
            title=inp.title,
            max_chars=cfg.MAX_PASTE_CHARS,
            min_chars=cfg.MIN_SOURCE_CHARS,
        )
        cleaned_text = parsed_text.text
        page_offsets = parsed_text.page_offsets
        page_count = 1
        origin = "pasted_text"
        title = parsed_text.title

    elif inp.kind == "url":
        if not inp.url:
            raise AppError("BAD_REQUEST", "URL is required for URL collection.")
        parsed_url = await ingest_url(
            target_url=inp.url,
            max_redirects=cfg.URL_MAX_REDIRECTS,
            max_bytes=cfg.URL_MAX_BYTES,
            timeout_s=cfg.URL_TIMEOUT_S,
            max_chars=cfg.MAX_EXTRACTED_CHARS,
            min_chars=cfg.MIN_SOURCE_CHARS,
        )
        cleaned_text = parsed_url.text
        page_offsets = parsed_url.page_offsets
        page_count = 1
        origin = parsed_url.url
        title = (inp.title or "").strip() or parsed_url.title

    else:
        raise AppError("BAD_REQUEST", f"Unsupported source kind '{inp.kind}'.")

    # 2. Content hash and deterministic source ID
    content_hash = hashlib.sha256(cleaned_text.encode("utf-8")).hexdigest()
    src_id = source_id(inp.project_id, content_hash)

    # 3. Idempotency and duplicate check
    existing_source = await deps.repos.sources.get_by_content_hash(inp.project_id, content_hash)

    if existing_source is not None:
        tag = existing_source.tag
        if existing_source.stage_collected:
            # Source already fully collected
            output = CollectorOutput(
                source_id=existing_source.id,
                tag=tag,
                title=existing_source.title,
                kind=existing_source.kind,
                chunk_count=existing_source.chunk_count,
                char_count=existing_source.char_count,
                already_existed=True,
            )
            await emit("result", output.model_dump(by_alias=True), "Source already collected.")
            await emit("complete", None, "Collection complete.")
            return output
    else:
        # Check source limit before allocating a new tag
        existing_sources = await deps.repos.sources.list_by_project(inp.project_id)
        if len(existing_sources) >= cfg.MAX_SOURCES_PER_PROJECT:
            raise AppError(
                "LIMIT_REACHED",
                f"Project has reached the maximum limit of {cfg.MAX_SOURCES_PER_PROJECT} sources.",
            )
        # Allocate new tag (e.g. S1, S2) under project row lock, reusing tag if created concurrently
        tag = await deps.repos.projects.allocate_source_tag(
            inp.project_id, content_hash=content_hash
        )

        # Re-check if source was completed while waiting for the lock
        existing_source = await deps.repos.sources.get_by_content_hash(inp.project_id, content_hash)
        if existing_source is not None and existing_source.stage_collected:
            output = CollectorOutput(
                source_id=existing_source.id,
                tag=existing_source.tag,
                title=existing_source.title,
                kind=existing_source.kind,
                chunk_count=existing_source.chunk_count,
                char_count=existing_source.char_count,
                already_existed=True,
            )
            await emit("result", output.model_dump(by_alias=True), "Source already collected.")
            await emit("complete", None, "Collection complete.")
            return output

    # 4. Initial PostgreSQL persistence (with stage_collected=False)
    # This transaction commits before any embedding or vector network calls
    await deps.repos.sources.upsert_source(
        project_id=inp.project_id,
        source_id=src_id,
        tag=tag,
        kind=inp.kind,
        title=title,
        origin=origin,
        content_hash=content_hash,
        char_count=len(cleaned_text),
        page_count=page_count,
        text_content=cleaned_text,
        page_offsets=page_offsets,
    )

    # 5. Chunk the text
    chunks = chunk_text(
        text=cleaned_text,
        page_offsets=page_offsets,
        target_chars=cfg.CHUNK_TARGET_CHARS,
        overlap_chars=cfg.CHUNK_OVERLAP_CHARS,
    )
    if not chunks:
        raise AppError("NO_TEXT", "No chunks could be produced from source text.")

    # 6. Generate vector embeddings in bounded batches
    await emit("status", None, f"Generating embeddings for {len(chunks)} chunks...")
    chunk_texts = [c.text for c in chunks]
    embeddings = await deps.embeddings.embed_texts(chunk_texts, "document", ctx=ctx)

    if len(embeddings) != len(chunks):
        raise AppError(
            "INTERNAL",
            f"Embedding count ({len(embeddings)}) does not match chunk count ({len(chunks)}).",
        )

    # Validate embedding dimension
    for emb in embeddings:
        if len(emb) != cfg.EMBEDDING_DIM:
            raise AppError(
                "INTERNAL",
                f"Vector dimension mismatch: expected {cfg.EMBEDDING_DIM}, got {len(emb)}.",
            )

    # 7. Upsert vector points to Qdrant
    await emit("status", None, "Storing vector index...")
    chunk_points = [
        ChunkPoint(
            key=chunk_id(src_id, c.index),
            project_id=inp.project_id,
            source_id=src_id,
            chunk_index=c.index,
            text=c.text,
            embedding=embeddings[c.index],
            page_start=c.page_start,
            page_end=c.page_end,
            chunker_version=1,
            embedding_model=cfg.GEMINI_EMBEDDING_MODEL,
        )
        for c in chunks
    ]

    await deps.vectors.upsert_chunks(chunk_points)

    # Prune any stale chunks from previous runs
    await deps.vectors.prune(
        project_id=inp.project_id,
        source_id=src_id,
        type_="chunk",
        keep_count=len(chunks),
    )

    # 8. Mark source stage_collected = True in PostgreSQL
    await deps.repos.sources.update_stage_flags(
        project_id=inp.project_id,
        source_id=src_id,
        stage_collected=True,
        chunk_count=len(chunks),
    )

    output = CollectorOutput(
        source_id=src_id,
        tag=tag,
        title=title,
        kind=inp.kind,
        chunk_count=len(chunks),
        char_count=len(cleaned_text),
        already_existed=False,
    )

    await emit("result", output.model_dump(by_alias=True), "Source collection complete.")
    await emit("complete", None, "Collection complete.")
    return output
