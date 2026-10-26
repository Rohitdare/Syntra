"""Source repository for PostgreSQL."""

from __future__ import annotations

from typing import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from research_desk.stores.models import Source, SourceText


class SourceRepo:
    """Repository managing Source and SourceText entities in PostgreSQL."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

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
        """Upsert source record and optional associated source text."""
        stmt = select(Source).where(
            Source.project_id == project_id,
            Source.id == source_id,
        )
        res = await self.session.execute(stmt)
        source = res.scalar_one_or_none()

        if source is None:
            source = Source(
                project_id=project_id,
                id=source_id,
                tag=tag,
                kind=kind,
                title=title,
                origin=origin,
                content_hash=content_hash,
                char_count=char_count,
                page_count=page_count,
                chunk_count=0,
                claim_count=0,
                stage_collected=False,
                stage_analyzed=False,
                stage_critiqued=False,
            )
            self.session.add(source)
        else:
            source.title = title
            source.origin = origin
            source.content_hash = content_hash
            source.char_count = char_count
            source.page_count = page_count

        await self.session.flush()

        if text_content is not None:
            t_stmt = select(SourceText).where(
                SourceText.project_id == project_id,
                SourceText.source_id == source_id,
            )
            t_res = await self.session.execute(t_stmt)
            st = t_res.scalar_one_or_none()
            if st is None:
                st = SourceText(
                    project_id=project_id,
                    source_id=source_id,
                    text=text_content,
                    page_offsets=page_offsets or [],
                    chunker_version=1,
                )
                self.session.add(st)
            else:
                st.text = text_content
                st.page_offsets = page_offsets or []
            await self.session.flush()

        return source

    async def get(self, project_id: str, source_id: str) -> Source | None:
        """Fetch source by project_id and source_id."""
        stmt = select(Source).where(
            Source.project_id == project_id,
            Source.id == source_id,
        )
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def get_by_content_hash(self, project_id: str, content_hash: str) -> Source | None:
        """Fetch existing source in the project with matching content hash."""
        stmt = select(Source).where(
            Source.project_id == project_id,
            Source.content_hash == content_hash,
        )
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def list_by_project(self, project_id: str) -> Sequence[Source]:
        """List all sources in project, ordered by tag."""
        stmt = (
            select(Source).where(Source.project_id == project_id).order_by(Source.created_at.asc())
        )
        res = await self.session.execute(stmt)
        return res.scalars().all()

    async def get_text(self, project_id: str, source_id: str) -> SourceText | None:
        """Fetch cleaned text for a source."""
        stmt = select(SourceText).where(
            SourceText.project_id == project_id,
            SourceText.source_id == source_id,
        )
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def update_stage_flags(
        self,
        project_id: str,
        source_id: str,
        *,
        stage_collected: bool | None = None,
        stage_analyzed: bool | None = None,
        stage_critiqued: bool | None = None,
        chunk_count: int | None = None,
        claim_count: int | None = None,
        summary: str | None = None,
        topics: list[str] | None = None,
        last_error: str | None = None,
    ) -> None:
        """Update stage completion booleans and derived counts."""
        stmt = select(Source).where(
            Source.project_id == project_id,
            Source.id == source_id,
        )
        res = await self.session.execute(stmt)
        source = res.scalar_one_or_none()
        if source:
            if stage_collected is not None:
                source.stage_collected = stage_collected
            if stage_analyzed is not None:
                source.stage_analyzed = stage_analyzed
            if stage_critiqued is not None:
                source.stage_critiqued = stage_critiqued
            if chunk_count is not None:
                source.chunk_count = chunk_count
            if claim_count is not None:
                source.claim_count = claim_count
            if summary is not None:
                source.summary = summary
            if topics is not None:
                source.topics = topics
            if last_error is not None:
                source.last_error = last_error
            await self.session.flush()

    async def delete(self, project_id: str, source_id: str) -> None:
        """Delete source by project_id and source_id (cascades claims, texts, verdicts)."""
        stmt = select(Source).where(
            Source.project_id == project_id,
            Source.id == source_id,
        )
        res = await self.session.execute(stmt)
        source = res.scalar_one_or_none()
        if source:
            await self.session.delete(source)
            await self.session.flush()
