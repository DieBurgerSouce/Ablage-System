# -*- coding: utf-8 -*-
"""Database session utilities for Celery tasks.

Provides async session context manager for use in Celery workers.
IMPORTANT: Engine is created inside async context to avoid event loop binding issues.
"""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from app.core.config import settings


@asynccontextmanager
async def get_async_session_context() -> AsyncGenerator[AsyncSession, None]:
    """Async context manager for database sessions in Celery tasks.

    Creates a fresh engine and session inside the current event loop to avoid
    'Future attached to a different loop' errors when using asyncio.run().

    Usage:
        async with get_async_session_context() as session:
            # Use session here
            result = await session.execute(query)

    Yields:
        AsyncSession: Database session that auto-commits on success
                      and rolls back on exception.
    """
    # Create engine inside async context to bind to current event loop
    engine = create_async_engine(
        settings.DATABASE_URL,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10,
        pool_recycle=3600,
        echo=False,
    )

    async_session_maker = sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False
    )

    session = async_session_maker()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()
        await engine.dispose()
