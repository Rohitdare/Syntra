"""Brief repository for PostgreSQL."""

from __future__ import annotations

from typing import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from research_desk.stores.models import Brief


class BriefRepo:
    """Repository managing Brief entities in PostgreSQL."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def upsert(self, project_id: str, brief: Brief) -> Brief:
        """Upsert a research brief (keyed by project_id and brf_<8hex>)."""
        stmt = select(Brief).where(
            Brief.project_id == project_id,
            Brief.id == brief.id,
        )
        res = await self.session.execute(stmt)
        existing = res.scalar_one_or_none()
        if existing is None:
            self.session.add(brief)
            await self.session.flush()
            return brief
        else:
            existing.question = brief.question
            existing.answer_markdown = brief.answer_markdown
            existing.json_data = brief.json_data
            existing.source_ids = brief.source_ids
            await self.session.flush()
            return existing

    async def get(self, project_id: str, brief_id: str) -> Brief | None:
        """Fetch single brief by project_id and id."""
        stmt = select(Brief).where(
            Brief.project_id == project_id,
            Brief.id == brief_id,
        )
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def list_by_project(self, project_id: str) -> Sequence[Brief]:
        """List all briefs for a project, sorted newest first."""
        stmt = select(Brief).where(Brief.project_id == project_id).order_by(Brief.created_at.desc())
        res = await self.session.execute(stmt)
        return res.scalars().all()
