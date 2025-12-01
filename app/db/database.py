"""
Database Connection Manager
Async PostgreSQL with connection pooling
Priority: P0 - CRITICAL
Created: 2024-11-22
"""
from typing import AsyncGenerator, Optional
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import NullPool, QueuePool
from sqlalchemy import text
from contextlib import asynccontextmanager
import structlog
import os

from app.core.config import settings

logger = structlog.get_logger(__name__)


# ============================================================================
# CONFIGURATION
# ============================================================================

class DatabaseConfig:
    """Database configuration from central settings"""

    def __init__(self):
        # Verwende zentrale settings statt eigener Defaults
        self.DB_HOST = settings.DB_HOST
        self.DB_PORT = settings.DB_PORT
        self.DB_NAME = settings.DB_NAME
        self.DB_USER = settings.DB_USER
        self.DB_PASSWORD = settings.DB_PASSWORD.get_secret_value() if settings.DB_PASSWORD else ""

        # Connection pool settings - aus Umgebungsvariablen mit sicheren Defaults
        self.POOL_SIZE = self._safe_int(os.getenv("DB_POOL_SIZE"), 20)
        self.MAX_OVERFLOW = self._safe_int(os.getenv("DB_MAX_OVERFLOW"), 40)
        self.POOL_TIMEOUT = self._safe_int(os.getenv("DB_POOL_TIMEOUT"), 30)
        self.POOL_RECYCLE = self._safe_int(os.getenv("DB_POOL_RECYCLE"), 3600)  # 1 hour

        # Query settings
        self.ECHO_SQL = settings.DEBUG

    @staticmethod
    def _safe_int(value: Optional[str], default: int) -> int:
        """Safely convert string to int with fallback."""
        if value is None:
            return default
        try:
            return int(value)
        except (ValueError, TypeError):
            logger.warning("invalid_integer_config", value=value, default=default)
            return default

    @property
    def DATABASE_URL(self) -> str:
        """Build async PostgreSQL connection string"""
        return (
            f"postgresql+asyncpg://{self.DB_USER}:{self.DB_PASSWORD}"
            f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
        )

    @property
    def SYNC_DATABASE_URL(self) -> str:
        """Build sync PostgreSQL connection string (for Alembic)"""
        return (
            f"postgresql+psycopg2://{self.DB_USER}:{self.DB_PASSWORD}"
            f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
        )


# ============================================================================
# ENGINE & SESSION
# ============================================================================

class DatabaseManager:
    """Singleton database manager"""

    _instance: Optional['DatabaseManager'] = None
    _engine = None
    _session_maker = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if self._engine is None:
            self.config = DatabaseConfig()
            self._initialize_engine()

    def _initialize_engine(self):
        """Initialize async SQLAlchemy engine with connection pooling"""
        try:
            self._engine = create_async_engine(
                self.config.DATABASE_URL,
                echo=self.config.ECHO_SQL,
                poolclass=QueuePool,
                pool_size=self.config.POOL_SIZE,
                max_overflow=self.config.MAX_OVERFLOW,
                pool_timeout=self.config.POOL_TIMEOUT,
                pool_recycle=self.config.POOL_RECYCLE,
                pool_pre_ping=True,  # Verify connections before using
            )

            self._session_maker = async_sessionmaker(
                self._engine,
                class_=AsyncSession,
                expire_on_commit=False,
                autocommit=False,
                autoflush=False,
            )

            logger.info(
                "database_initialized",
                host=self.config.DB_HOST,
                database=self.config.DB_NAME,
                pool_size=self.config.POOL_SIZE
            )

        except Exception as e:
            logger.error("database_initialization_failed", error=str(e), exc_info=True)
            raise

    @property
    def engine(self):
        """Get async engine"""
        if self._engine is None:
            self._initialize_engine()
        return self._engine

    @property
    def session_maker(self):
        """Get async session maker"""
        if self._session_maker is None:
            self._initialize_engine()
        return self._session_maker

    async def dispose(self):
        """Dispose engine and close all connections"""
        if self._engine:
            await self._engine.dispose()
            logger.info("database_disposed")

    async def health_check(self) -> dict:
        """Check database connectivity"""
        try:
            async with self.get_session() as session:
                await session.execute(text("SELECT 1"))

            # Get pool stats
            pool = self._engine.pool

            return {
                "status": "healthy",
                "host": self.config.DB_HOST,
                "database": self.config.DB_NAME,
                "pool_size": pool.size(),
                "checked_out": pool.checkedout(),
                "overflow": pool.overflow(),
                "total_connections": pool.size() + pool.overflow()
            }

        except Exception as e:
            logger.error("database_health_check_failed", error=str(e), exc_info=True)
            return {
                "status": "unhealthy",
                "error": str(e)
            }

    @asynccontextmanager
    async def get_session(self) -> AsyncGenerator[AsyncSession, None]:
        """Get async database session with automatic cleanup"""
        session = self.session_maker()
        try:
            yield session
            await session.commit()
        except Exception as e:
            await session.rollback()
            logger.error("database_session_error", error=str(e), exc_info=True)
            raise
        finally:
            await session.close()


# ============================================================================
# DEPENDENCY INJECTION (for FastAPI)
# ============================================================================

async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency for database sessions"""
    db_manager = DatabaseManager()
    async with db_manager.get_session() as session:
        yield session


# Alias für Abwärtskompatibilität
get_db = get_db_session


# ============================================================================
# UTILITIES
# ============================================================================

async def check_database_connection() -> bool:
    """Simple connection check"""
    try:
        db_manager = DatabaseManager()
        health = await db_manager.health_check()
        return health["status"] == "healthy"
    except Exception:
        return False


async def get_pool_status() -> dict:
    """Get detailed connection pool status"""
    try:
        db_manager = DatabaseManager()
        return await db_manager.health_check()
    except Exception as e:
        return {
            "status": "error",
            "error": str(e)
        }


# ============================================================================
# INITIALIZATION
# ============================================================================

def get_database_manager() -> DatabaseManager:
    """Get singleton database manager instance"""
    return DatabaseManager()
