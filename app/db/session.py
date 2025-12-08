# -*- coding: utf-8 -*-
"""Database session utilities for Celery tasks.

Provides async session context manager for use in Celery workers.
"""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from app.core.config import settings


# Create engine for Celery workers
# Uses separate pool settings optimized for worker tasks
_engine = create_async_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
    pool_recycle=3600,
    echo=False,
)

_async_session_maker = sessionmaker(
    _engine,
    class_=AsyncSession,
    expire_on_commit=False
)


@asynccontextmanager
async def get_async_session_context() -> AsyncGenerator[AsyncSession, None]:
    """Async context manager for database sessions in Celery tasks.

    Usage:
        async with get_async_session_context() as session:
            # Use session here
            result = await session.execute(query)

    Yields:
        AsyncSession: Database session that auto-commits on success
                      and rolls back on exception.
    """
    session = _async_session_maker()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()
