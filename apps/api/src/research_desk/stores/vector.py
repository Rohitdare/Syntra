"""VectorStore protocol and Qdrant adapter implementation.

Per Non-negotiable Rule 2:
This is the ONLY module that imports qdrant_client.
All filters are built strictly from validated IDs and enums.
Every search strictly filters on 'type' and 'projectId'.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Protocol, Sequence

from qdrant_client import AsyncQdrantClient, models

from research_desk.core.config import Settings, get_settings
from research_desk.core.ids import key_to_point_id


@dataclass(frozen=True)
class ChunkPoint:
    """Document chunk to store in Qdrant."""

    key: str
    project_id: str
    source_id: str
    chunk_index: int
    text: str
    embedding: list[float]
    page_start: int | None = None
    page_end: int | None = None
    chunker_version: int = 1
    embedding_model: str = ""


@dataclass(frozen=True)
class ClaimPoint:
    """Extracted claim point to store in Qdrant."""

    key: str
    project_id: str
    source_id: str
    source_tag: str
    claim_index: int
    text: str
    embedding: list[float]
    importance: int = 3
    page_hint: int | None = None
    embedding_model: str = ""


@dataclass(frozen=True)
class ClaimVector:
    """Claim vector representation for similarity search."""

    key: str
    text: str
    source_id: str
    source_tag: str
    embedding: list[float]


@dataclass(frozen=True)
class Hit:
    """Search hit returned from Qdrant."""

    key: str
    score: float
    payload: dict[str, Any]


@dataclass(frozen=True)
class ClaimNeighbors:
    """Neighbors found for a single claim vector in batch similarity search."""

    claim_key: str
    neighbors: list[Hit]


class VectorStore(Protocol):
    """Protocol for semantic vector storage and similarity retrieval."""

    async def upsert_chunks(self, rows: Sequence[ChunkPoint]) -> None: ...

    async def upsert_claims(self, rows: Sequence[ClaimPoint]) -> None: ...

    async def prune(
        self,
        project_id: str,
        source_id: str,
        type_: Literal["chunk", "claim"],
        keep_count: int,
    ) -> None: ...

    async def get_claim_vectors(self, project_id: str, source_id: str) -> list[ClaimVector]: ...

    async def find_similar_claims_from_other_sources(
        self,
        project_id: str,
        source_id: str,
        claims: Sequence[ClaimVector],
        top_k: int,
        min_similarity: float,
    ) -> list[ClaimNeighbors]: ...

    async def search_chunks(
        self, project_id: str, embedding: Sequence[float], top_k: int
    ) -> list[Hit]: ...

    async def search_claims(
        self, project_id: str, embedding: Sequence[float], top_k: int
    ) -> list[Hit]: ...

    async def delete_source(self, project_id: str, source_id: str) -> None: ...

    async def delete_project(self, project_id: str) -> None: ...

    async def count(
        self,
        project_id: str,
        type_: Literal["chunk", "claim"],
        source_id: str | None = None,
    ) -> int: ...

    async def ping(self) -> bool: ...


class QdrantVectorStore(VectorStore):
    """Qdrant implementation of VectorStore."""

    def __init__(
        self,
        client: AsyncQdrantClient | None = None,
        collection: str | None = None,
    ) -> None:
        if client is not None:
            self.client = client
            self.collection = collection or "knowledge"
        else:
            cfg = get_settings()
            api_key = cfg.QDRANT_API_KEY.get_secret_value() if cfg.QDRANT_API_KEY else None
            self.client = AsyncQdrantClient(url=cfg.QDRANT_URL, api_key=api_key)
            self.collection = collection or cfg.QDRANT_COLLECTION

    async def upsert_chunks(self, rows: Sequence[ChunkPoint]) -> None:
        if not rows:
            return
        points: list[models.PointStruct] = []
        for r in rows:
            pt_id = key_to_point_id(r.project_id, r.key)
            payload = {
                "key": r.key,
                "type": "chunk",
                "projectId": r.project_id,
                "sourceId": r.source_id,
                "chunkIndex": r.chunk_index,
                "pageStart": r.page_start,
                "pageEnd": r.page_end,
                "text": r.text,
                "chunkerVersion": r.chunker_version,
                "embeddingModel": r.embedding_model,
                "schemaVersion": 1,
            }
            points.append(
                models.PointStruct(
                    id=str(pt_id),
                    vector=r.embedding,
                    payload=payload,
                )
            )
        await self.client.upsert(collection_name=self.collection, points=points, wait=True)

    async def upsert_claims(self, rows: Sequence[ClaimPoint]) -> None:
        if not rows:
            return
        points: list[models.PointStruct] = []
        for r in rows:
            pt_id = key_to_point_id(r.project_id, r.key)
            payload = {
                "key": r.key,
                "type": "claim",
                "projectId": r.project_id,
                "sourceId": r.source_id,
                "sourceTag": r.source_tag,
                "claimIndex": r.claim_index,
                "text": r.text,
                "importance": r.importance,
                "pageHint": r.page_hint,
                "embeddingModel": r.embedding_model,
                "schemaVersion": 1,
            }
            points.append(
                models.PointStruct(
                    id=str(pt_id),
                    vector=r.embedding,
                    payload=payload,
                )
            )
        await self.client.upsert(collection_name=self.collection, points=points, wait=True)

    async def prune(
        self,
        project_id: str,
        source_id: str,
        type_: Literal["chunk", "claim"],
        keep_count: int,
    ) -> None:
        # Delete stale indexes >= keep_count for this source
        idx_field = "chunkIndex" if type_ == "chunk" else "claimIndex"
        flt = models.Filter(
            must=[
                models.FieldCondition(key="type", match=models.MatchValue(value=type_)),
                models.FieldCondition(key="projectId", match=models.MatchValue(value=project_id)),
                models.FieldCondition(key="sourceId", match=models.MatchValue(value=source_id)),
                models.FieldCondition(key=idx_field, range=models.Range(gte=keep_count)),
            ]
        )
        await self.client.delete(
            collection_name=self.collection,
            points_selector=models.FilterSelector(filter=flt),
            wait=True,
        )

    async def get_claim_vectors(self, project_id: str, source_id: str) -> list[ClaimVector]:
        flt = models.Filter(
            must=[
                models.FieldCondition(key="type", match=models.MatchValue(value="claim")),
                models.FieldCondition(key="projectId", match=models.MatchValue(value=project_id)),
                models.FieldCondition(key="sourceId", match=models.MatchValue(value=source_id)),
            ]
        )
        points, _ = await self.client.scroll(
            collection_name=self.collection,
            scroll_filter=flt,
            with_payload=True,
            with_vectors=True,
            limit=100,
        )
        result: list[ClaimVector] = []
        for p in points:
            if not p.payload or p.vector is None:
                continue
            if not isinstance(p.vector, list):
                continue
            embedding = [float(v) for v in p.vector if isinstance(v, (int, float))]
            result.append(
                ClaimVector(
                    key=str(p.payload.get("key", "")),
                    text=str(p.payload.get("text", "")),
                    source_id=str(p.payload.get("sourceId", "")),
                    source_tag=str(p.payload.get("sourceTag", "")),
                    embedding=embedding,
                )
            )
        return result

    async def find_similar_claims_from_other_sources(
        self,
        project_id: str,
        source_id: str,
        claims: Sequence[ClaimVector],
        top_k: int,
        min_similarity: float,
    ) -> list[ClaimNeighbors]:
        if not claims:
            return []

        # Batch query in ONE request
        requests: list[models.QueryRequest] = []
        for claim in claims:
            flt = models.Filter(
                must=[
                    models.FieldCondition(key="type", match=models.MatchValue(value="claim")),
                    models.FieldCondition(
                        key="projectId", match=models.MatchValue(value=project_id)
                    ),
                ],
                must_not=[
                    models.FieldCondition(key="sourceId", match=models.MatchValue(value=source_id)),
                ],
            )
            requests.append(
                models.QueryRequest(
                    query=claim.embedding,
                    filter=flt,
                    limit=top_k,
                    score_threshold=min_similarity,
                    with_payload=True,
                )
            )

        batch_results = await self.client.query_batch_points(
            collection_name=self.collection,
            requests=requests,
        )

        all_neighbors: list[ClaimNeighbors] = []
        for claim, batch_res in zip(claims, batch_results):
            hits: list[Hit] = []
            for scored_point in batch_res.points:
                payload = scored_point.payload or {}
                key = str(payload.get("key", scored_point.id))
                hits.append(
                    Hit(
                        key=key,
                        score=float(scored_point.score),
                        payload=payload,
                    )
                )
            all_neighbors.append(ClaimNeighbors(claim_key=claim.key, neighbors=hits))

        return all_neighbors

    async def search_chunks(
        self, project_id: str, embedding: Sequence[float], top_k: int
    ) -> list[Hit]:
        flt = models.Filter(
            must=[
                models.FieldCondition(key="type", match=models.MatchValue(value="chunk")),
                models.FieldCondition(key="projectId", match=models.MatchValue(value=project_id)),
            ]
        )
        res = await self.client.query_points(
            collection_name=self.collection,
            query=list(embedding),
            query_filter=flt,
            limit=top_k,
            with_payload=True,
        )
        return [
            Hit(
                key=str(p.payload.get("key", p.id) if p.payload else p.id),
                score=float(p.score),
                payload=p.payload or {},
            )
            for p in res.points
        ]

    async def search_claims(
        self, project_id: str, embedding: Sequence[float], top_k: int
    ) -> list[Hit]:
        flt = models.Filter(
            must=[
                models.FieldCondition(key="type", match=models.MatchValue(value="claim")),
                models.FieldCondition(key="projectId", match=models.MatchValue(value=project_id)),
            ]
        )
        res = await self.client.query_points(
            collection_name=self.collection,
            query=list(embedding),
            query_filter=flt,
            limit=top_k,
            with_payload=True,
        )
        return [
            Hit(
                key=str(p.payload.get("key", p.id) if p.payload else p.id),
                score=float(p.score),
                payload=p.payload or {},
            )
            for p in res.points
        ]

    async def delete_source(self, project_id: str, source_id: str) -> None:
        flt = models.Filter(
            must=[
                models.FieldCondition(key="projectId", match=models.MatchValue(value=project_id)),
                models.FieldCondition(key="sourceId", match=models.MatchValue(value=source_id)),
            ]
        )
        await self.client.delete(
            collection_name=self.collection,
            points_selector=models.FilterSelector(filter=flt),
            wait=True,
        )

    async def delete_project(self, project_id: str) -> None:
        flt = models.Filter(
            must=[
                models.FieldCondition(key="projectId", match=models.MatchValue(value=project_id)),
            ]
        )
        await self.client.delete(
            collection_name=self.collection,
            points_selector=models.FilterSelector(filter=flt),
            wait=True,
        )

    async def count(
        self,
        project_id: str,
        type_: Literal["chunk", "claim"],
        source_id: str | None = None,
    ) -> int:
        conditions: list[models.Condition] = [
            models.FieldCondition(key="type", match=models.MatchValue(value=type_)),
            models.FieldCondition(key="projectId", match=models.MatchValue(value=project_id)),
        ]
        if source_id is not None:
            conditions.append(
                models.FieldCondition(key="sourceId", match=models.MatchValue(value=source_id))
            )
        flt = models.Filter(must=conditions)
        res = await self.client.count(collection_name=self.collection, count_filter=flt)
        return int(res.count)

    async def ping(self) -> bool:
        """Check readiness by getting collection info."""
        try:
            await self.client.get_collection(collection_name=self.collection)
            return True
        except Exception:
            return False


async def init_qdrant_collection(
    client: AsyncQdrantClient,
    collection_name: str,
    embedding_dim: int,
    alias_name: str | None = None,
) -> None:
    """Create collection, payload indexes and optional alias idempotently."""
    exists = await client.collection_exists(collection_name=collection_name)
    if not exists:
        await client.create_collection(
            collection_name=collection_name,
            vectors_config=models.VectorParams(
                size=embedding_dim,
                distance=models.Distance.COSINE,
            ),
        )

    # Create payload indexes on type, projectId, sourceId
    for field in ("type", "projectId", "sourceId"):
        try:
            await client.create_payload_index(
                collection_name=collection_name,
                field_name=field,
                field_schema=models.PayloadSchemaType.KEYWORD,
            )
        except Exception:
            # Idempotent: already exists
            pass

    # Address through alias if provided
    if alias_name and alias_name != collection_name:
        aliases_resp = await client.get_collection_aliases(collection_name=collection_name)
        existing_aliases = [a.alias_name for a in aliases_resp.aliases]
        if alias_name not in existing_aliases:
            await client.update_collection_aliases(
                change_aliases_operations=[
                    models.CreateAliasOperation(
                        create_alias=models.CreateAlias(
                            collection_name=collection_name,
                            alias_name=alias_name,
                        )
                    )
                ]
            )


def get_vector_store(settings: Settings | None = None) -> VectorStore:
    """Initialize and return a QdrantVectorStore using app configuration."""
    cfg = settings or get_settings()
    client = AsyncQdrantClient(
        url=cfg.QDRANT_URL,
        api_key=cfg.QDRANT_API_KEY.get_secret_value() if cfg.QDRANT_API_KEY else None,
    )
    return QdrantVectorStore(client=client, collection=cfg.QDRANT_COLLECTION)
