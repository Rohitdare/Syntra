"""Idempotent migration script for Qdrant and app_meta pinning.

Creates collection, keyword payload indexes, and collection alias.
Pins embedding model, dimension, collection name, and schema version into PostgreSQL app_meta.
"""

import asyncio
import sys

from qdrant_client import AsyncQdrantClient
from sqlalchemy import select

from research_desk.core.config import get_settings
from research_desk.stores.db import get_engine, get_sessionmaker
from research_desk.stores.models import AppMeta
from research_desk.stores.vector import init_qdrant_collection


async def migrate() -> None:
    settings = get_settings()
    print(f"Connecting to Qdrant at {settings.QDRANT_URL}...")

    qdrant_client = AsyncQdrantClient(
        url=settings.QDRANT_URL,
        api_key=settings.QDRANT_API_KEY.get_secret_value() if settings.QDRANT_API_KEY else None,
    )

    collection_name = f"{settings.QDRANT_COLLECTION}_v1"
    alias_name = settings.QDRANT_COLLECTION

    try:
        await init_qdrant_collection(
            client=qdrant_client,
            collection_name=collection_name,
            embedding_dim=settings.EMBEDDING_DIM,
            alias_name=alias_name,
        )
        print(f"Qdrant collection '{collection_name}' with alias '{alias_name}' is ready.")
    except Exception as exc:
        print(f"Warning: Failed to connect to or migrate Qdrant: {exc}", file=sys.stderr)
        print("Continuing with database app_meta check if database is available.")
    finally:
        await qdrant_client.close()

    # PostgreSQL app_meta pinning
    print("Connecting to database to pin app_meta...")
    engine = get_engine(settings)
    sessionmaker = get_sessionmaker(settings)

    meta_entries = {
        "embedding_model": settings.GEMINI_EMBEDDING_MODEL,
        "embedding_dim": str(settings.EMBEDDING_DIM),
        "qdrant_collection": settings.QDRANT_COLLECTION,
        "qdrant_schema_version": "1",
    }

    try:
        async with sessionmaker() as session:
            async with session.begin():
                for key, val in meta_entries.items():
                    existing = await session.scalar(select(AppMeta.value).where(AppMeta.key == key))
                    if existing is None:
                        session.add(AppMeta(key=key, value=val))
                        print(f"Pinned app_meta '{key}' = '{val}'")
                    elif existing != val:
                        raise ValueError(
                            f"Configuration conflict in app_meta for '{key}': "
                            f"database has '{existing}' but settings have '{val}'. "
                            "Startup/migration refused."
                        )
                    else:
                        print(f"Verified app_meta '{key}' = '{val}'")
        print("Database app_meta successfully verified.")
    except Exception as exc:
        print(f"Database error during app_meta migration: {exc}", file=sys.stderr)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(migrate())
