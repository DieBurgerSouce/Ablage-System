# -*- coding: utf-8 -*-
"""Database session utilities for Celery tasks and standalone async contexts.

Provides async and sync session context managers for use in Celery workers and other
contexts where FastAPI's dependency injection is not available.

IMPORTANT: Engine is created inside async context to avoid event loop binding issues.
For FastAPI endpoints, use AsyncSessionLocal from app.api.dependencies instead.

RLS Support:
- get_sync_session_with_rls() - Sets company context for RLS
- enable_rls_bypass_sync() - Enables bypass for service operations
- rls_bypass_context_sync() - Context manager for bypass
"""

from contextlib import asynccontextmanager, contextmanager
from threading import RLock
from typing import AsyncGenerator, Generator, Optional
from uuid import UUID

import structlog
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, Session

from app.core.config import settings
from app.core.safe_errors import safe_error_log, safe_error_detail

logger = structlog.get_logger(__name__)

# Cached sync engine for Celery tasks - Thread-safe singleton
_sync_engine: Optional[Engine] = None
_sync_session_maker: Optional[sessionmaker] = None
# RLock (reentrant) statt Lock: _get_sync_session_maker() haelt diesen Lock und
# ruft darin _get_sync_engine() auf, das denselben Lock erneut acquiren will.
# Mit nicht-reentrantem Lock() deadlockt der Thread beim Cold-Start mit sich
# selbst (Stack: _get_sync_session_maker -> _get_sync_engine -> with _sync_engine_lock).
# Das blockierte den Solo-GPU-Worker beim ersten sync-Task -> OCR lief nie.
_sync_engine_lock = RLock()


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

    WICHTIG: Diese Funktion ist für Celery Tasks gedacht, die in separaten
    Prozessen laufen. Für FastAPI Endpoints sollte AsyncSessionLocal aus
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


@asynccontextmanager
async def get_worker_session_context(
    company_id: Optional[UUID] = None,
) -> AsyncGenerator[AsyncSession, None]:
    """Worker-Session mit gesetztem RLS-Kontext (F-16).

    Für Celery-Tasks und Skripte, die RLS-geschützte Tabellen (``documents``,
    ...) berühren. Hintergrund-Prozesse gehen nicht durch die HTTP-Middleware,
    die sonst den RLS-Company-Kontext setzt — ohne diesen Helfer würden ihre
    Reads/Inserts an den ``documents``-Policies scheitern (bzw. hingen an den
    permissiven Escapes, die F-15 entfernt).

    Zwei Modi:
    - **Ersteller** (Mirror, Import) kennen die Company → ``company_id`` setzen
      → Session läuft company-gescoped (INSERT-``WITH CHECK`` passt).
    - **systemische Prozessoren** (Verarbeitung per Objekt-ID, Company erst nach
      dem Read bekannt) → ohne ``company_id`` → RLS-Bypass.

    WICHTIG: Bewusst ein eigener Helfer statt einer pauschalen Änderung von
    ``get_async_session_context`` — diese Factory wird auch von einigen
    API-Endpunkten genutzt, die NICHT bypassen dürfen. Der GUC wird
    **session-level** (``is_local=false``) gesetzt, damit er Per-Move-/Batch-
    Commits innerhalb der Task überlebt; leak-frei, weil die Factory Engine +
    Verbindung pro Aufruf disposed (kein Cross-Task-Reuse, direkte
    Postgres-Verbindung ohne Transaction-Pooler).

    Args:
        company_id: Company der Ersteller-Operation; ``None`` = systemischer
            Bypass für Prozessoren.
    """
    async with get_async_session_context() as session:
        if company_id is not None:
            # UUID-Validierung gegen Injection (analog set_rls_company_context_sync)
            cid = str(UUID(str(company_id)))
            await session.execute(
                text("SELECT set_config('app.current_company_id', :cid, false)"),
                {"cid": cid},
            )
            # Mig-210-Policies nutzen app.current_tenant_id -> konsistent mitsetzen
            await session.execute(
                text("SELECT set_config('app.current_tenant_id', :cid, false)"),
                {"cid": cid},
            )
        else:
            await session.execute(
                text("SELECT set_config('app.rls_bypass', 'true', false)")
            )
        yield session


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


async def arm_rls_bypass(session: AsyncSession) -> None:
    """Setzt den session-level RLS-Bypass auf einer BESTEHENDEN Session.

    Fuer Task-Module mit eigenem Engine/Pool (task_callbacks, thumbnail_,
    export_, extraction_, customer_detection_tasks), die nicht durch
    ``get_worker_session_context`` gehen koennen, ohne ihren dedizierten
    Pool zu verlieren. ``is_local=false`` — ueberlebt Commits; der GUC
    haftet an den gepoolten Verbindungen des MODUL-EIGENEN Pools, was
    gewollt ist (alle Tasks dieser Module sind systemische Prozessoren).
    """
    await session.execute(
        text("SELECT set_config('app.rls_bypass', 'true', false)")
    )


# Aliases for backwards compatibility with Celery tasks
# Many tasks use `async with async_session_factory() as db:` or
# `async with async_session_maker() as db:` pattern.
#
# SEIT 2026-07-11 (RLS-Restrunde 272-274): Die Aliase zeigen auf den
# WORKER-Kontext (Bypass) — sie werden ausschliesslich von Celery-Tasks/
# Task-Handlern genutzt (Inventar: 0 Treffer in app/api; Design-Doc
# 2026-07_rls_274_design.md §4). Kontextlose Task-Sessions waren nach den
# Migrationen still kaputt (Reads = 0 Zeilen, documents-INSERT abgelehnt) —
# Muster active_learning_tasks. Die API-Dependency ``get_async_session``
# bleibt bewusst OHNE Bypass.
async_session_factory = get_worker_session_context
async_session_maker = get_worker_session_context


@contextmanager
def get_sync_session() -> Generator[Session, None, None]:
    """Synchronous context manager for database sessions in Celery tasks.

    Erstellt eine synchrone DB-Session für Celery-Tasks, die keine
    async/await-Syntax verwenden können oder wollen.

    WICHTIG: Diese Funktion ist für Celery Tasks gedacht, die synchron
    arbeiten müssen. Die async-URL wird automatisch zu sync konvertiert.

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


# =============================================================================
# RLS (Row Level Security) Support for Celery Tasks
# =============================================================================


def set_rls_company_context_sync(session: Session, company_id: UUID) -> None:
    """Setzt die PostgreSQL Session-Variable für RLS (synchron).

    WICHTIG: Muss vor allen DB-Operationen in Celery Tasks aufgerufen werden,
    wenn diese Company-spezifische Daten bearbeiten sollen.

    Args:
        session: Sync DB-Session
        company_id: Company-ID für RLS-Filter
    """
    try:
        # Strenge UUID-Validierung gegen SQL-Injection
        company_id_str = str(company_id)
        validated_uuid = UUID(company_id_str)

        session.execute(
            text("SELECT set_config('app.current_company_id', :cid, true)"),
            {"cid": str(validated_uuid)}
        )
        # RLS-Reconciliation (siehe set_rls_company_context): Migration-210-Policies
        # nutzen 'app.current_tenant_id' -> konsistent mitsetzen.
        session.execute(
            text("SELECT set_config('app.current_tenant_id', :cid, true)"),
            {"cid": str(validated_uuid)}
        )
        logger.debug(
            "rls_context_set_sync",
            company_id=str(validated_uuid)
        )
    except ValueError:
        logger.warning(
            "rls_context_invalid_uuid_sync",
            attempted_value=str(company_id)[:50]
        )
    except Exception as e:
        logger.debug(
            "rls_context_skip_sync",
            reason=safe_error_detail(e, "DB-Session")
        )


def enable_rls_bypass_sync(session: Session) -> None:
    """Aktiviert RLS-Bypass für Service-Account Operationen (synchron).

    WARNUNG: Nur für Migrations, Admin-Operationen und Cross-Tenant Tasks!

    Args:
        session: Sync DB-Session
    """
    try:
        session.execute(
            text("SELECT set_config('app.rls_bypass', 'true', true)")
        )
        logger.debug("rls_bypass_enabled_sync")
    except Exception as e:
        logger.warning("rls_bypass_enable_failed_sync", **safe_error_log(e))


def disable_rls_bypass_sync(session: Session) -> None:
    """Deaktiviert RLS-Bypass (synchron).

    Args:
        session: Sync DB-Session
    """
    try:
        session.execute(
            text("SELECT set_config('app.rls_bypass', 'false', true)")
        )
        logger.debug("rls_bypass_disabled_sync")
    except Exception as e:
        logger.warning("rls_bypass_disable_failed_sync", **safe_error_log(e))


@contextmanager
def rls_bypass_context_sync(session: Session) -> Generator[None, None, None]:
    """Context Manager für RLS-Bypass in Celery Tasks (synchron).

    Usage:
        with get_sync_session() as session:
            with rls_bypass_context_sync(session):
                # Cross-tenant Operationen möglich
                ...
            # RLS wieder aktiv

    Args:
        session: Sync DB-Session
    """
    try:
        enable_rls_bypass_sync(session)
        yield
    finally:
        disable_rls_bypass_sync(session)


@contextmanager
def get_sync_session_with_rls(company_id: UUID) -> Generator[Session, None, None]:
    """Synchrone Session mit automatischem RLS-Context.

    Convenience-Funktion für Celery Tasks, die nur für eine bestimmte
    Company Daten verarbeiten.

    Usage:
        with get_sync_session_with_rls(company_id) as session:
            # RLS ist automatisch aktiv für diese Company
            docs = session.query(Document).all()  # Nur company_id's Docs

    Args:
        company_id: Company-ID für RLS-Filter

    Yields:
        Session: DB-Session mit aktivem RLS-Context
    """
    session = _get_sync_session_maker()()
    try:
        set_rls_company_context_sync(session, company_id)
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
