"""User repository handling user lookup and upsert.

Per docs/02-DESIGN-DOC.md Section 13.1 and docs/03-DATABASE-SCHEMA.md Section 1.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from research_desk.stores.models import User


class UserRepo:
    """Repository managing User records in PostgreSQL."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_auth_subject(self, auth_subject: str) -> User | None:
        """Find user by auth provider subject identifier."""
        stmt = select(User).where(User.auth_subject == auth_subject)
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def get_or_create(
        self,
        auth_subject: str,
        email: str | None = None,
        default_id: uuid.UUID | None = None,
    ) -> User:
        """Upsert a user based on auth_subject."""
        user = await self.get_by_auth_subject(auth_subject)
        if user is None:
            user = User(
                id=default_id or uuid.uuid4(),
                auth_subject=auth_subject,
                email=email,
            )
            self.session.add(user)
            await self.session.flush()
        return user
