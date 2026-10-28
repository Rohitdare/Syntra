"""Unit tests for the Collector agent (Phase 2.4)."""

from __future__ import annotations

import uuid
from typing import Any, Sequence

import pytest

from research_desk.agents.collector import (
    AgentDeps,
    CollectorInput,
    CollectorRepos,
)
from research_desk.agents.collector import (
    run as run_collector,
)
from research_desk.core.config import get_settings
from research_desk.core.errors import AppError
from research_desk.core.ids import source_id
from research_desk.providers.llm import CallContext
from research_desk.stores.models import Source, SourceText
from research_desk.stores.vector import (
    ChunkPoint,
    ClaimNeighbors,
    ClaimPoint,
    ClaimVector,
    Hit,
)


class FakeProjectRepo:
    """In-memory ProjectRepo simulation."""

    def __init__(self, source_repo: FakeSourceRepo | None = None) -> None:
        self.tags: dict[str, int] = {}
        self.source_repo = source_repo

    async def allocate_source_tag(self, project_id: str, content_hash: str | None = None) -> str:
        if content_hash is not None and self.source_repo is not None:
            for s in self.source_repo.sources.values():
                if s.project_id == project_id and s.content_hash == content_hash:
                    return str(s.tag)
        curr = self.tags.get(project_id, 1)
        self.tags[project_id] = curr + 1
        return f"S{curr}"


class FakeSourceRepo:
    """In-memory SourceRepo simulation."""

    def __init__(self) -> None:
        self.sources: dict[tuple[str, str], Source] = {}
        self.texts: dict[tuple[str, str], SourceText] = {}

    async def upsert_source(
        self,
        project_id: str,
        source_id: str,
        tag: str,
        kind: str,
        title: str,
        origin: str,
        content_hash: str,
        char_count: int,
        page_count: int | None = None,
        text_content: str | None = None,
        page_offsets: list[int] | None = None,
    ) -> Source:
        key = (project_id, source_id)
        if key in self.sources:
            s = self.sources[key]
            s.title = title
            s.origin = origin
            s.content_hash = content_hash
            s.char_count = char_count
            s.page_count = page_count
        else:
            s = Source(
                project_id=project_id,
                id=source_id,
                tag=tag,
                kind=kind,
                title=title,
                origin=origin,
                content_hash=content_hash,
                char_count=char_count,
                page_count=page_count,
                stage_collected=False,
            )
            self.sources[key] = s

        if text_content is not None:
            self.texts[key] = SourceText(
                project_id=project_id,
                source_id=source_id,
                text=text_content,
                page_offsets=page_offsets or [],
                chunker_version=1,
            )
        return s

    async def get_by_content_hash(self, project_id: str, content_hash: str) -> Source | None:
        for s in self.sources.values():
            if s.project_id == project_id and s.content_hash == content_hash:
                return s
        return None

    async def list_by_project(self, project_id: str) -> list[Source]:
        return [s for s in self.sources.values() if s.project_id == project_id]

    async def update_stage_flags(
        self,
        project_id: str,
        source_id: str,
        *,
        stage_collected: bool | None = None,
        chunk_count: int | None = None,
        fail_update: bool = False,
        **kwargs: object,
    ) -> None:
        if getattr(self, "fail_update", False) or fail_update:
            raise RuntimeError("Simulated PostgreSQL error during update_stage_flags")
        key = (project_id, source_id)
        if key in self.sources:
            s = self.sources[key]
            if stage_collected is not None:
                s.stage_collected = stage_collected
            if chunk_count is not None:
                s.chunk_count = chunk_count


class FakeVectorStore:
    """In-memory VectorStore simulation."""

    def __init__(self) -> None:
        self.chunks: list[ChunkPoint] = []
        self.pruned_calls: list[tuple[str, str, int]] = []
        self.fail_upsert: bool = False
        self.fail_prune: bool = False

    async def upsert_chunks(self, rows: Sequence[ChunkPoint]) -> None:
        if self.fail_upsert:
            raise RuntimeError("Simulated Qdrant failure during upsert_chunks")
        # Idempotent upsert by key
        existing_keys = {c.key for c in rows}
        self.chunks = [c for c in self.chunks if c.key not in existing_keys]
        self.chunks.extend(rows)

    async def upsert_claims(self, rows: Sequence[ClaimPoint]) -> None:
        pass

    async def prune(
        self,
        project_id: str,
        source_id: str,
        type_: str,
        keep_count: int,
    ) -> None:
        if self.fail_prune:
            raise RuntimeError("Simulated Qdrant failure during prune")
        self.pruned_calls.append((project_id, source_id, keep_count))
        # Keep only up to keep_count chunks for this source
        filtered = [
            c
            for c in self.chunks
            if not (
                c.project_id == project_id
                and c.source_id == source_id
                and c.chunk_index >= keep_count
            )
        ]
        self.chunks = filtered

    async def get_claim_vectors(self, project_id: str, source_id: str) -> list[ClaimVector]:
        return []

    async def find_similar_claims_from_other_sources(
        self, *args: object, **kwargs: object
    ) -> list[ClaimNeighbors]:
        return []

    async def search_chunks(
        self, project_id: str, embedding: Sequence[float], top_k: int
    ) -> list[Hit]:
        return []

    async def search_claims(
        self, project_id: str, embedding: Sequence[float], top_k: int
    ) -> list[Hit]:
        return []

    async def delete_source(self, project_id: str, source_id: str) -> None:
        self.chunks = [
            c for c in self.chunks if not (c.project_id == project_id and c.source_id == source_id)
        ]

    async def delete_project(self, project_id: str) -> None:
        self.chunks = [c for c in self.chunks if c.project_id != project_id]

    async def count(
        self,
        project_id: str,
        type_: str,
        source_id: str | None = None,
    ) -> int:
        return len(
            [
                c
                for c in self.chunks
                if c.project_id == project_id and (source_id is None or c.source_id == source_id)
            ]
        )

    async def ping(self) -> bool:
        return True


class FakeEmbeddingProvider:
    """In-memory fake embedding provider generating 768-dim vectors."""

    def __init__(self, dim: int = 768) -> None:
        self.dim = dim
        self.called_with: list[list[str]] = []
        self.fail_embed: bool = False

    async def embed_texts(
        self,
        texts: Sequence[str],
        kind: str = "document",
        *,
        ctx: CallContext | None = None,
    ) -> list[list[float]]:
        if self.fail_embed:
            raise RuntimeError("Simulated embedding provider failure")
        self.called_with.append(list(texts))
        return [[0.01 * (i + 1)] * self.dim for i in range(len(texts))]


def _build_test_deps() -> tuple[AgentDeps, FakeSourceRepo, FakeVectorStore, FakeEmbeddingProvider]:
    fake_src = FakeSourceRepo()
    fake_proj = FakeProjectRepo(source_repo=fake_src)
    fake_vec = FakeVectorStore()
    fake_emb = FakeEmbeddingProvider(dim=768)

    repos = CollectorRepos(projects=fake_proj, sources=fake_src)  # type: ignore[arg-type]
    deps = AgentDeps(
        repos=repos,
        vectors=fake_vec,
        embeddings=fake_emb,
        cfg=get_settings(),
    )
    return deps, fake_src, fake_vec, fake_emb


@pytest.mark.asyncio
async def test_collector_new_source_success() -> None:
    deps, fake_src, fake_vec, fake_emb = _build_test_deps()
    events: list[tuple[str, dict[str, Any] | None, str | None]] = []

    async def mock_emit(evt_type: str, data: dict[str, Any] | None, msg: str | None) -> None:
        events.append((evt_type, data, msg))

    ctx = CallContext(user_id=uuid.uuid4(), project_id="prj_test001", job_id=uuid.uuid4())
    inp = CollectorInput(
        project_id="prj_test001",
        kind="text",
        text="Long text content about modern software architecture.\n\n"
        + ("Explaining distributed services and agents.\n" * 25),
        title="Architecture Guide",
    )

    out = await run_collector(inp, deps, mock_emit, ctx)

    assert out.tag == "S1"
    assert out.already_existed is False
    assert out.chunk_count > 0
    assert out.char_count >= 500
    assert out.title == "Architecture Guide"

    # Verify PostgreSQL store state
    key = ("prj_test001", out.source_id)
    assert key in fake_src.sources
    assert fake_src.sources[key].stage_collected is True
    assert fake_src.sources[key].chunk_count == out.chunk_count
    assert key in fake_src.texts

    # Verify Qdrant points
    assert len(fake_vec.chunks) == out.chunk_count
    for chk in fake_vec.chunks:
        assert chk.project_id == "prj_test001"
        assert chk.source_id == out.source_id
        assert len(chk.embedding) == 768

    # Verify event stream
    event_types = [e[0] for e in events]
    assert event_types == ["start", "status", "status", "status", "result", "complete"]


@pytest.mark.asyncio
async def test_collector_idempotent_duplicate_content() -> None:
    deps, fake_src, fake_vec, fake_emb = _build_test_deps()
    events: list[tuple[str, dict[str, Any] | None, str | None]] = []

    async def mock_emit(evt_type: str, data: dict[str, Any] | None, msg: str | None) -> None:
        events.append((evt_type, data, msg))

    ctx = CallContext(user_id=uuid.uuid4(), project_id="prj_test001")
    inp = CollectorInput(
        project_id="prj_test001",
        kind="text",
        text="Unique idempotent content for testing duplicated additions.\n\n"
        + ("Repeating detailed observations.\n" * 25),
        title="Duplicate Test",
    )

    # First run
    out1 = await run_collector(inp, deps, mock_emit, ctx)
    assert out1.already_existed is False
    assert out1.tag == "S1"

    # Second run with same text
    events.clear()
    out2 = await run_collector(inp, deps, mock_emit, ctx)
    assert out2.already_existed is True
    assert out2.source_id == out1.source_id
    assert out2.tag == "S1"
    assert out2.chunk_count == out1.chunk_count

    # Verify events
    event_types = [e[0] for e in events]
    assert "result" in event_types
    assert "complete" in event_types


@pytest.mark.asyncio
async def test_collector_max_sources_limit_reached() -> None:
    deps, fake_src, fake_vec, fake_emb = _build_test_deps()

    async def mock_emit(evt_type: str, data: dict[str, Any] | None, msg: str | None) -> None:
        pass

    ctx = CallContext(user_id=uuid.uuid4(), project_id="prj_test001")

    # Pre-populate 8 sources
    for i in range(8):
        fake_src.sources[("prj_test001", f"src_{i}")] = Source(
            project_id="prj_test001",
            id=f"src_{i}",
            tag=f"S{i + 1}",
            kind="text",
            title=f"Source {i}",
            origin="test",
            content_hash=f"hash_{i}",
            stage_collected=True,
        )

    # Adding a 9th distinct source should raise LIMIT_REACHED
    inp = CollectorInput(
        project_id="prj_test001",
        kind="text",
        text="A new 9th distinct source that should be rejected by the limit.\n\n"
        + ("Extensive content text to easily exceed the minimum char count.\n" * 30),
    )

    with pytest.raises(AppError) as exc_info:
        await run_collector(inp, deps, mock_emit, ctx)
    assert exc_info.value.code == "LIMIT_REACHED"


@pytest.mark.asyncio
async def test_collector_embedding_dimension_mismatch() -> None:
    deps, fake_src, fake_vec, fake_emb = _build_test_deps()
    # Force wrong embedding dimension (e.g. 512 instead of 768)
    fake_emb.dim = 512

    async def mock_emit(evt_type: str, data: dict[str, Any] | None, msg: str | None) -> None:
        pass

    ctx = CallContext(user_id=uuid.uuid4(), project_id="prj_test001")
    inp = CollectorInput(
        project_id="prj_test001",
        kind="text",
        text="Testing dimension validation.\n\n" + ("Paragraphs of text.\n" * 25),
    )

    with pytest.raises(AppError) as exc_info:
        await run_collector(inp, deps, mock_emit, ctx)
    assert exc_info.value.code == "INTERNAL"
    assert "dimension mismatch" in str(exc_info.value.message)


@pytest.mark.asyncio
async def test_collector_recovery_on_uncollected_source() -> None:
    deps, fake_src, fake_vec, fake_emb = _build_test_deps()

    async def mock_emit(evt_type: str, data: dict[str, Any] | None, msg: str | None) -> None:
        pass

    text = "Recovering interrupted collection run.\n\n" + ("Substantial text to process.\n" * 25)
    ctx = CallContext(user_id=uuid.uuid4(), project_id="prj_test001")
    inp = CollectorInput(project_id="prj_test001", kind="text", text=text)

    # Compute hash and pre-insert a source with stage_collected=False
    import hashlib

    from research_desk.ingest.clean import clean_text

    cleaned = clean_text(text)
    content_hash = hashlib.sha256(cleaned.encode("utf-8")).hexdigest()
    src_id = source_id("prj_test001", content_hash)
    fake_src.sources[("prj_test001", src_id)] = Source(
        project_id="prj_test001",
        id=src_id,
        tag="S1",
        kind="text",
        title="Interrupted",
        origin="pasted_text",
        content_hash=content_hash,
        stage_collected=False,
    )

    # Running collector should pick up the uncollected source and finish it
    out = await run_collector(inp, deps, mock_emit, ctx)
    assert out.source_id == src_id
    assert out.already_existed is False
    assert fake_src.sources[("prj_test001", src_id)].stage_collected is True


@pytest.mark.asyncio
async def test_collector_concurrent_duplicate_reuses_tag() -> None:
    """Verify that concurrent requests with identical content hash reuse tag
    and do not burn counter.
    """
    deps, fake_src, fake_vec, fake_emb = _build_test_deps()
    events: list[tuple[str, dict[str, Any] | None, str | None]] = []

    async def mock_emit(evt_type: str, data: dict[str, Any] | None, msg: str | None) -> None:
        events.append((evt_type, data, msg))

    text = "Concurrent race condition test text.\n\n" + ("Analyzing lock semantics.\n" * 25)
    ctx = CallContext(user_id=uuid.uuid4(), project_id="prj_test001")
    inp = CollectorInput(project_id="prj_test001", kind="text", text=text)

    # First request runs and completes
    out1 = await run_collector(inp, deps, mock_emit, ctx)
    assert out1.tag == "S1"

    # Second request comes in with identical content
    out2 = await run_collector(inp, deps, mock_emit, ctx)
    assert out2.tag == "S1"
    assert out2.already_existed is True

    # Next different source should get S2, proving S2 was NOT burned
    inp_diff = CollectorInput(
        project_id="prj_test001",
        kind="text",
        text="A completely different source content text.\n\n"
        + ("Exploring alternative architecture designs.\n" * 25),
    )
    out3 = await run_collector(inp_diff, deps, mock_emit, ctx)
    assert out3.tag == "S2"


@pytest.mark.asyncio
async def test_collector_embedding_failure_recovery() -> None:
    """Trace failure when embedding fails before vector writes."""
    deps, fake_src, fake_vec, fake_emb = _build_test_deps()
    events: list[tuple[str, dict[str, Any] | None, str | None]] = []

    async def mock_emit(evt_type: str, data: dict[str, Any] | None, msg: str | None) -> None:
        events.append((evt_type, data, msg))

    text = "Embedding failure simulation text.\n\n" + ("Validating robust recovery.\n" * 25)
    ctx = CallContext(user_id=uuid.uuid4(), project_id="prj_test001")
    inp = CollectorInput(project_id="prj_test001", kind="text", text=text)

    # 1. First run: embedding fails
    fake_emb.fail_embed = True
    with pytest.raises(RuntimeError, match="Simulated embedding provider failure"):
        await run_collector(inp, deps, mock_emit, ctx)

    # Verify state: PostgreSQL has uncollected source, Qdrant is empty, complete not emitted
    event_types = [e[0] for e in events]
    assert "complete" not in event_types
    assert "result" not in event_types

    # Find the uncollected source in PostgreSQL
    all_sources = await fake_src.list_by_project("prj_test001")
    assert len(all_sources) == 1
    uncollected = all_sources[0]
    assert uncollected.stage_collected is False
    assert uncollected.tag == "S1"
    assert len(fake_vec.chunks) == 0

    # 2. Retry run: embedding succeeds
    fake_emb.fail_embed = False
    events.clear()
    out = await run_collector(inp, deps, mock_emit, ctx)

    assert out.tag == "S1"
    assert out.already_existed is False
    assert uncollected.stage_collected is True
    assert len(fake_vec.chunks) == out.chunk_count
    event_types = [e[0] for e in events]
    assert "complete" in event_types


@pytest.mark.asyncio
async def test_collector_vector_upsert_failure_recovery() -> None:
    """Trace failure when Qdrant upsert fails partway."""
    deps, fake_src, fake_vec, fake_emb = _build_test_deps()
    events: list[tuple[str, dict[str, Any] | None, str | None]] = []

    async def mock_emit(evt_type: str, data: dict[str, Any] | None, msg: str | None) -> None:
        events.append((evt_type, data, msg))

    text = "Vector upsert failure simulation text.\n\n" + ("Validating Qdrant retry.\n" * 25)
    ctx = CallContext(user_id=uuid.uuid4(), project_id="prj_test001")
    inp = CollectorInput(project_id="prj_test001", kind="text", text=text)

    # 1. First run: upsert fails
    fake_vec.fail_upsert = True
    with pytest.raises(RuntimeError, match="Simulated Qdrant failure during upsert_chunks"):
        await run_collector(inp, deps, mock_emit, ctx)

    event_types = [e[0] for e in events]
    assert "complete" not in event_types

    all_sources = await fake_src.list_by_project("prj_test001")
    assert len(all_sources) == 1
    assert all_sources[0].stage_collected is False

    # 2. Retry run: upsert succeeds
    fake_vec.fail_upsert = False
    events.clear()
    out = await run_collector(inp, deps, mock_emit, ctx)

    assert out.tag == "S1"
    assert all_sources[0].stage_collected is True
    assert len(fake_vec.chunks) == out.chunk_count
    assert "complete" in [e[0] for e in events]


@pytest.mark.asyncio
async def test_collector_pruning_failure_recovery() -> None:
    """Trace failure when pruning stale points fails."""
    deps, fake_src, fake_vec, fake_emb = _build_test_deps()
    events: list[tuple[str, dict[str, Any] | None, str | None]] = []

    async def mock_emit(evt_type: str, data: dict[str, Any] | None, msg: str | None) -> None:
        events.append((evt_type, data, msg))

    text = "Pruning failure simulation text.\n\n" + ("Validating pruning recovery.\n" * 25)
    ctx = CallContext(user_id=uuid.uuid4(), project_id="prj_test001")
    inp = CollectorInput(project_id="prj_test001", kind="text", text=text)

    # 1. First run: pruning fails
    fake_vec.fail_prune = True
    with pytest.raises(RuntimeError, match="Simulated Qdrant failure during prune"):
        await run_collector(inp, deps, mock_emit, ctx)

    all_sources = await fake_src.list_by_project("prj_test001")
    assert len(all_sources) == 1
    # Even though chunks were upserted, source is not marked collected
    assert all_sources[0].stage_collected is False

    # 2. Retry run: pruning succeeds
    fake_vec.fail_prune = False
    events.clear()
    out = await run_collector(inp, deps, mock_emit, ctx)

    assert out.tag == "S1"
    assert all_sources[0].stage_collected is True
    assert len(fake_vec.chunks) == out.chunk_count
    assert "complete" in [e[0] for e in events]


@pytest.mark.asyncio
async def test_collector_final_db_update_failure_recovery() -> None:
    """Trace failure when final update_stage_flags fails."""
    deps, fake_src, fake_vec, fake_emb = _build_test_deps()
    events: list[tuple[str, dict[str, Any] | None, str | None]] = []

    async def mock_emit(evt_type: str, data: dict[str, Any] | None, msg: str | None) -> None:
        events.append((evt_type, data, msg))

    text = "Final DB update failure simulation text.\n\n" + ("Validating final commit.\n" * 25)
    ctx = CallContext(user_id=uuid.uuid4(), project_id="prj_test001")
    inp = CollectorInput(project_id="prj_test001", kind="text", text=text)

    # 1. First run: update_stage_flags fails
    fake_src.fail_update = True  # type: ignore[attr-defined]
    with pytest.raises(RuntimeError, match="Simulated PostgreSQL error"):
        await run_collector(inp, deps, mock_emit, ctx)

    all_sources = await fake_src.list_by_project("prj_test001")
    assert len(all_sources) == 1
    assert all_sources[0].stage_collected is False
    # Chunks are in vector store but source is NOT marked collected
    assert len(fake_vec.chunks) > 0
    assert "complete" not in [e[0] for e in events]

    # 2. Retry run: update_stage_flags succeeds
    fake_src.fail_update = False  # type: ignore[attr-defined]
    events.clear()
    out = await run_collector(inp, deps, mock_emit, ctx)

    assert out.tag == "S1"
    assert all_sources[0].stage_collected is True
    # Upserting again does not produce duplicate chunks in vector store
    assert len(fake_vec.chunks) == out.chunk_count
    assert "complete" in [e[0] for e in events]


@pytest.mark.asyncio
async def test_collector_deterministic_chunk_keys_and_point_ids() -> None:
    """Verify deterministic chunk keys and Qdrant point IDs across multiple invocations."""
    import hashlib

    from research_desk.core.ids import chunk_id, key_to_point_id
    from research_desk.ingest.clean import clean_text

    text = "Deterministic ID verification test.\n\n" + ("Checking UUIDv5 stability.\n" * 25)
    cleaned = clean_text(text)
    content_hash = hashlib.sha256(cleaned.encode("utf-8")).hexdigest()
    src_id = source_id("prj_test001", content_hash)

    # Generate chunk key and point ID
    chk_k = chunk_id(src_id, 0)
    assert chk_k.startswith("chk_")
    pt_id_1 = key_to_point_id("prj_test001", chk_k)
    pt_id_2 = key_to_point_id("prj_test001", chk_k)
    assert pt_id_1 == pt_id_2
    assert str(pt_id_1) == str(pt_id_2)
