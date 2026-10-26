"""Project repository for PostgreSQL."""

from __future__ import annotations

import uuid
from typing import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from research_desk.core.ids import project_id as generate_project_id
from research_desk.stores.models import Project


class ProjectRepo:
    """Repository managing Project entities in PostgreSQL."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self, owner_id: uuid.UUID, name: str, description: str | None = None
    ) -> Project:
        """Create a new project with a unique prj_<8hex> key."""
        for _ in range(5):
            pid = generate_project_id()
            project = Project(
                id=pid,
                owner_id=owner_id,
                name=name,
                description=description,
                status="active",
                next_source_tag=1,
            )
            self.session.add(project)
            try:
                await self.session.flush()
                return project
            except Exception:
                await self.session.rollback()
        raise RuntimeError("Failed to generate unique project ID after 5 attempts")

    async def get_owned(self, owner_id: uuid.UUID, project_id: str) -> Project | None:
        """Fetch project only if owned by owner_id and not deleting."""
        stmt = select(Project).where(
            Project.id == project_id,
            Project.owner_id == owner_id,
            Project.status != "deleting",
        )
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def list_for_owner(self, owner_id: uuid.UUID) -> Sequence[Project]:
        """List active projects owned by user, sorted newest first."""
        stmt = (
            select(Project)
            .where(Project.owner_id == owner_id, Project.status != "deleting")
            .order_by(Project.created_at.desc())
        )
        res = await self.session.execute(stmt)
        return res.scalars().all()

    async def mark_deleting(self, project_id: str) -> None:
        """Tombstone project to deleting status."""
        stmt = select(Project).where(Project.id == project_id)
        res = await self.session.execute(stmt)
        project = res.scalar_one_or_none()
        if project:
            project.status = "deleting"
            await self.session.flush()

    async def delete(self, project_id: str) -> None:
        """Hard delete project after Qdrant vectors are purged."""
        stmt = select(Project).where(Project.id == project_id)
        res = await self.session.execute(stmt)
        project = res.scalar_one_or_none()
        if project:
            await self.session.delete(project)
            await self.session.flush()

    async def allocate_source_tag(self, project_id: str) -> str:
        """Allocate next source tag (e.g. S1, S2) under a row lock."""
        # Row lock project for update
        stmt = select(Project).where(Project.id == project_id).with_for_update()
        res = await self.session.execute(stmt)
        project = res.scalar_one_or_none()
        if not project:
            raise ValueError(f"Project '{project_id}' not found")

        tag_num = project.next_source_tag
        project.next_source_tag += 1
        await self.session.flush()
        return f"S{tag_num}"
