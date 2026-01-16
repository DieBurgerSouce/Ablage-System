# -*- coding: utf-8 -*-
"""Database session utilities for Celery tasks and standalone async contexts.

Provides async and sync session context managers for use in Celery workers and other
contexts where FastAPI's dependency injection is not available.

IMPORTANT: Engine is created inside async context to avoid event loop binding issues.
For FastAPI endpoints, use AsyncSessionLocal from app.api.dependencies instead.
"""

from contextlib import asynccontextmanager, contextmanager
from threading import Lock
from typing import AsyncGenerator, Generator, Optional

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, Session

from app.core.config import settings

# Cached sync engine for Celery tasks - Thread-safe singleton
_sync_engine: Optional[Engine] = None
_sync_session_maker: Optional[sessionmaker] = None
_sync_engine_lock = Lock()


def _get_sync_engine() -> Engine:
    """Lazy-initialized sync engine singleton.

    Thread-safe: Uses double-checked locking pattern to ensure
    only one engine is created even in multi-threaded environments.
    SQLAlchemy engines are designed to be shared across threads.

    Returns:
        Engine: Cached sync database engine
    """
    global _sync_engine
    if _sync_engine is None:
        with _sync_engine_lock:
            # Double-check after acquiring lock
            if _sync_engine is None:
                # Convert async URL to sync URL
                # postgresql+asyncpg:// -> postgresql://
                sync_url = settings.DATABASE_URL.replace("+asyncpg", "")
                _sync_engine = create_engine(
                    sync_url,
                    pool_pre_ping=True,
                    pool_size=settings.DB_POOL_SIZE,
                    max_overflow=settings.DB_MAX_OVERFLOW,
                    pool_recycle=settings.DB_POOL_RECYCLE,
                    pool_timeout=settings.DB_POOL_TIMEOUT,
                    echo=False,
                )
    return _sync_engine


def _get_sync_session_maker() -> sessionmaker:
    """Lazy-initialized sync session maker singleton.

    Thread-safe: Uses the same lock as engine initialization.

    Returns:
        sessionmaker: Configured session factory
    """
    global _sync_session_maker
    if _sync_session_maker is None:
        with _sync_engine_lock:
            # Double-check after acquiring lock
            if _sync_session_maker is None:
                _sync_session_maker = sessionmaker(
                    _get_sync_engine(),
                    class_=Session,
                    expire_on_commit=False
                )
    return _sync_session_maker


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


# Alias for backwards compatibility with Celery tasks
# Many tasks use `async with async_session_factory() as db:` pattern
async_session_factory = get_async_session_context


@contextmanager
def get_sync_session() -> Generator[Session, None, None]:
    """Synchronous context manager for database sessions in Celery tasks.

    Erstellt eine synchrone DB-Session fuer Celery-Tasks, die keine
    async/await-Syntax verwenden koennen oder wollen.

    WICHTIG: Diese Funktion ist fuer Celery Tasks gedacht, die synchron
    arbeiten muessen. Die async-URL wird automatisch zu sync konvertiert.

    Performance: Nutzt gecachte Engine/SessionMaker Singletons statt
    bei jedem Aufruf neue Engines zu erstellen.

    Usage:
        with get_sync_session() as session:
            # Use session here
            result = session.execute(query)

    Yields:
        Session: Database session that auto-commits on success
                 and rolls back on exception.
    """
    session = _get_sync_session_maker()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
