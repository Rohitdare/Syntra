"""Verdict repository for PostgreSQL."""

from __future__ import annotations

from typing import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from research_desk.stores.models import Verdict


class VerdictRepo:
    """Repository managing Verdict entities in PostgreSQL."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def upsert_verdicts(self, project_id: str, verdicts: Sequence[Verdict]) -> None:
        """Upsert a sequence of verdicts for the project."""
        for v in verdicts:
            stmt = select(Verdict).where(
                Verdict.project_id == project_id,
                Verdict.id == v.id,
            )
            res = await self.session.execute(stmt)
            existing = res.scalar_one_or_none()
            if existing is None:
                self.session.add(v)
            else:
                existing.label = v.label
                existing.confidence = v.confidence
                existing.rationale = v.rationale
                existing.similarity = v.similarity
        await self.session.flush()

    async def get_judged_pair_keys(
        self, project_id: str, candidate_keys: Sequence[str]
    ) -> set[str]:
        """Find verdict keys that have already been judged (Query Q3)."""
        if not candidate_keys:
            return set()
        stmt = select(Verdict.id).where(
            Verdict.project_id == project_id,
            Verdict.id.in_(candidate_keys),
        )
        res = await self.session.execute(stmt)
        return set(res.scalars().all())

    async def list_by_project(self, project_id: str, label: str | None = None) -> Sequence[Verdict]:
        """List verdicts for a project, optionally filtered by label, ordered by confidence."""
        stmt = select(Verdict).where(Verdict.project_id == project_id)
        if label is not None:
            stmt = stmt.where(Verdict.label == label)
        stmt = stmt.order_by(Verdict.confidence.desc())
        res = await self.session.execute(stmt)
        return res.scalars().all()
