"""Database engine, session management, and transaction helper.

Uses SQLAlchemy 2 async with AsyncSession and asyncpg driver.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from research_desk.core.config import Settings, get_settings

_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None

# Type aliases for external callers to preserve module boundary rules
DbSession = AsyncSession
DbSessionFactory = async_sessionmaker[AsyncSession]


def get_engine(settings: Settings | None = None) -> AsyncEngine:
    """Return or initialize the singleton AsyncEngine."""
    global _engine, _sessionmaker
    if _engine is None:
        cfg = settings or get_settings()
        db_url = cfg.DATABASE_URL.get_secret_value()
        if not db_url:
            db_url = "postgresql+asyncpg://postgres:postgres@localhost:5432/research_desk"
        elif db_url.startswith("postgresql://"):
            db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)

        connect_args: dict[str, Any] = {}
        if db_url.startswith("sqlite"):
            connect_args["check_same_thread"] = False

        _engine = create_async_engine(
            db_url,
            echo=False,
            pool_pre_ping=True,
            connect_args=connect_args,
        )
        _sessionmaker = async_sessionmaker(
            bind=_engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
        )
    return _engine


def get_sessionmaker(settings: Settings | None = None) -> async_sessionmaker[AsyncSession]:
    """Return the singleton sessionmaker."""
    global _sessionmaker
    if _sessionmaker is None:
        get_engine(settings)
    assert _sessionmaker is not None
    return _sessionmaker


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency yielding an AsyncSession."""
    sm = get_sessionmaker()
    async with sm() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


@asynccontextmanager
async def transaction(session: AsyncSession) -> AsyncGenerator[AsyncSession, None]:
    """Transaction context manager ensuring commit or rollback."""
    if session.in_transaction():
        yield session
    else:
        async with session.begin():
            yield session


async def ping_db(session: AsyncSession) -> bool:
    """Perform a fast readiness check (SELECT 1)."""
    try:
        res = await session.execute(text("SELECT 1"))
        return res.scalar() == 1
    except Exception:
        return False


async def check_db_readiness(settings: Settings | None = None) -> bool:
    """Directly connect and perform SELECT 1 using the engine."""
    try:
        engine = get_engine(settings)
        async with engine.connect() as conn:
            res = await conn.execute(text("SELECT 1"))
            return res.scalar() == 1
    except Exception:
        return False


async def reset_engine() -> None:
    """Dispose engine for testing or shutdown."""
    global _engine, _sessionmaker
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _sessionmaker = None
