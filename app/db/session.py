# -*- coding: utf-8 -*-
"""Database session utilities for Celery tasks and standalone async contexts.

Provides async session context manager for use in Celery workers and other
contexts where FastAPI's dependency injection is not available.

IMPORTANT: Engine is created inside async context to avoid event loop binding issues.
For FastAPI endpoints, use AsyncSessionLocal from app.api.dependencies instead.
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

    WICHTIG: Diese Funktion ist fuer Celery Tasks gedacht, die in separaten
    Prozessen laufen. Fuer FastAPI Endpoints sollte AsyncSessionLocal aus
    app.api.dependencies verwendet werden.

    Usage:
        async with get_async_session_context() as session:
            # Use session here
            result = await session.execute(query)

    Yields:
        AsyncSession: Database session that auto-commits on success
                      and rolls back on exception.
    """
    # Create engine inside async context to bind to current event loop
    # Use settings for pool configuration to match FastAPI's engine
    engine = create_async_engine(
        settings.DATABASE_URL,
        pool_pre_ping=True,
        pool_size=settings.DB_POOL_SIZE,
        max_overflow=settings.DB_MAX_OVERFLOW,
        pool_recycle=settings.DB_POOL_RECYCLE,
        pool_timeout=settings.DB_POOL_TIMEOUT,
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


async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency for async database sessions.

    Creates a fresh session for each request using the context manager.
    This is the function imported by RAG endpoints.

    Usage:
        @router.get("/")
        async def endpoint(db: AsyncSession = Depends(get_async_session)):
            ...

    Yields:
        AsyncSession: Database session that auto-commits on success
                      and rolls back on exception.
    """
    async with get_async_session_context() as session:
        yield session
