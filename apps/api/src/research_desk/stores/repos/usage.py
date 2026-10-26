"""Usage ledger repository for PostgreSQL."""

from __future__ import annotations

import datetime
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from research_desk.stores.models import UsageLedger


class UsageRepo:
    """Repository managing UsageLedger entries in PostgreSQL."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def record(
        self,
        *,
        user_id: uuid.UUID,
        project_id: str | None,
        job_id: uuid.UUID | None,
        provider: str,
        model: str,
        kind: str,
        tokens_in: int = 0,
        tokens_out: int = 0,
        texts: int = 0,
    ) -> UsageLedger:
        """Record an LLM or embedding call in the usage ledger."""
        entry = UsageLedger(
            user_id=user_id,
            project_id=project_id,
            job_id=job_id,
            provider=provider,
            model=model,
            kind=kind,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            texts=texts,
        )
        self.session.add(entry)
        await self.session.flush()
        return entry

    async def get_daily_usage(
        self, user_id: uuid.UUID, since: datetime.datetime
    ) -> tuple[int, int]:
        """Return (llm_calls, embedded_texts) for user_id since timestamp."""
        llm_stmt = select(func.count(UsageLedger.id)).where(
            UsageLedger.user_id == user_id,
            UsageLedger.kind == "llm",
            UsageLedger.created_at >= since,
        )
        llm_calls = (await self.session.execute(llm_stmt)).scalar_one()

        embed_stmt = select(func.coalesce(func.sum(UsageLedger.texts), 0)).where(
            UsageLedger.user_id == user_id,
            UsageLedger.kind == "embed",
            UsageLedger.created_at >= since,
        )
        embedded_texts = (await self.session.execute(embed_stmt)).scalar_one()

        return int(llm_calls), int(embedded_texts)
