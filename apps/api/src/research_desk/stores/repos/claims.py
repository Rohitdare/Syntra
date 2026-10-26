"""Claim repository for PostgreSQL."""

from __future__ import annotations

from typing import Sequence

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from research_desk.stores.models import Claim


class ClaimRepo:
    """Repository managing Claim entities in PostgreSQL."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def replace_claims(
        self,
        project_id: str,
        source_id: str,
        new_claims: Sequence[Claim],
    ) -> None:
        """Replace all claims for a source in one transaction.

        Cascades in PostgreSQL remove dependent verdicts automatically.
        """
        # Delete existing claims for this source
        del_stmt = delete(Claim).where(
            Claim.project_id == project_id,
            Claim.source_id == source_id,
        )
        await self.session.execute(del_stmt)

        for clm in new_claims:
            self.session.add(clm)
        await self.session.flush()

    async def list_by_source(self, project_id: str, source_id: str) -> Sequence[Claim]:
        """Fetch all claims for a given source, ordered by claim_index."""
        stmt = (
            select(Claim)
            .where(Claim.project_id == project_id, Claim.source_id == source_id)
            .order_by(Claim.claim_index.asc())
        )
        res = await self.session.execute(stmt)
        return res.scalars().all()

    async def list_by_project(self, project_id: str) -> Sequence[Claim]:
        """Fetch all claims in a project."""
        stmt = select(Claim).where(Claim.project_id == project_id).order_by(Claim.created_at.asc())
        res = await self.session.execute(stmt)
        return res.scalars().all()

    async def get(self, project_id: str, claim_id: str) -> Claim | None:
        """Fetch single claim by project_id and id."""
        stmt = select(Claim).where(
            Claim.project_id == project_id,
            Claim.id == claim_id,
        )
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()
