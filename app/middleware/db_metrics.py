# -*- coding: utf-8 -*-
"""
Database Query Performance Metrics Middleware.

Tracks database query execution times using SQLAlchemy events.
Records metrics to Prometheus for monitoring and alerting.

Feinpoliert und durchdacht - Production-ready DB Monitoring.
"""

import re
import time
from contextlib import contextmanager
from typing import Callable, Optional, Dict, Generator

from starlette.requests import Request
from starlette.responses import Response

import structlog
from sqlalchemy import event
from sqlalchemy.engine import Engine, Connection, ExceptionContext
from sqlalchemy.orm import Session

logger = structlog.get_logger(__name__)

# Global tracking state
_query_start_times: Dict[int, float] = {}

# Table name extraction patterns
TABLE_PATTERNS = [
    re.compile(r'\bFROM\s+["`]?(\w+)["`]?', re.IGNORECASE),
    re.compile(r'\bINTO\s+["`]?(\w+)["`]?', re.IGNORECASE),
    re.compile(r'\bUPDATE\s+["`]?(\w+)["`]?', re.IGNORECASE),
    re.compile(r'\bDELETE\s+FROM\s+["`]?(\w+)["`]?', re.IGNORECASE),
]

# Operation detection
OPERATION_PATTERNS = {
    'select': re.compile(r'^\s*SELECT', re.IGNORECASE),
    'insert': re.compile(r'^\s*INSERT', re.IGNORECASE),
    'update': re.compile(r'^\s*UPDATE', re.IGNORECASE),
    'delete': re.compile(r'^\s*DELETE', re.IGNORECASE),
}


def extract_table_name(statement: str) -> str:
    """Extract table name from SQL statement."""
    for pattern in TABLE_PATTERNS:
        match = pattern.search(statement)
        if match:
            return match.group(1).lower()
    return "unknown"


def extract_operation(statement: str) -> str:
    """Extract operation type from SQL statement."""
    for op_name, pattern in OPERATION_PATTERNS.items():
        if pattern.match(statement):
            return op_name
    return "other"


def setup_db_metrics(engine: Engine) -> None:
    """
    Setup database query metrics collection.

    Registers SQLAlchemy event listeners to track query execution times.

    Args:
        engine: SQLAlchemy engine instance
    """
    @event.listens_for(engine, "before_cursor_execute")
    def before_cursor_execute(
        conn: Connection,
        cursor: object,
        statement: str,
        parameters: object,
        context: object,
        executemany: bool
    ) -> None:
        """Record query start time."""
        conn_id = id(conn)
        _query_start_times[conn_id] = time.perf_counter()

    @event.listens_for(engine, "after_cursor_execute")
    def after_cursor_execute(
        conn: Connection,
        cursor: object,
        statement: str,
        parameters: object,
        context: object,
        executemany: bool
    ) -> None:
        """Record query execution time and metrics."""
        conn_id = id(conn)
        start_time = _query_start_times.pop(conn_id, None)

        if start_time is None:
            return

        duration = time.perf_counter() - start_time
        table = extract_table_name(statement)
        operation = extract_operation(statement)

        # Record metrics
        try:
            from app.core.business_metrics import record_db_query
            record_db_query(
                operation=operation,
                table=table,
                duration_seconds=duration,
                status="success"
            )
        except Exception as e:
            logger.debug(
                "db_metrics_recording_failed",
                operation=operation,
                table=table,
                error_type=type(e).__name__,
            )

        # Log slow queries (>100ms)
        if duration > 0.1:
            logger.warning(
                "slow_db_query",
                duration_ms=round(duration * 1000, 2),
                operation=operation,
                table=table,
                statement=statement[:200]  # Truncate for logging
            )

    @event.listens_for(engine, "handle_error")
    def handle_error(exception_context: ExceptionContext) -> None:
        """Record query errors."""
        conn = exception_context.connection
        if conn is None:
            return

        conn_id = id(conn)
        start_time = _query_start_times.pop(conn_id, None)

        if start_time is not None:
            duration = time.perf_counter() - start_time
            statement = str(exception_context.statement or "")
            table = extract_table_name(statement)
            operation = extract_operation(statement)

            try:
                from app.core.business_metrics import record_db_query
                record_db_query(
                    operation=operation,
                    table=table,
                    duration_seconds=duration,
                    status="error"
                )
            except Exception as e:
                logger.debug(
                    "db_metrics_recording_failed",
                    operation=operation,
                    table=table,
                    status="error",
                    error_type=type(e).__name__,
                )

            logger.error(
                "db_query_error",
                duration_ms=round(duration * 1000, 2),
                operation=operation,
                table=table,
                error=str(exception_context.original_exception)
            )

    logger.info("db_metrics_initialized")


def update_pool_metrics(engine: Engine) -> None:
    """
    Update connection pool metrics.

    Should be called periodically (e.g., every minute) to track pool status.

    Args:
        engine: SQLAlchemy engine instance
    """
    try:
        pool = engine.pool
        if pool is None:
            return

        from app.core.business_metrics import update_db_pool_metrics

        # Get pool stats
        pool_size = pool.size()
        checked_out = pool.checkedout()
        overflow = pool.overflow()

        update_db_pool_metrics(
            pool_size=pool_size,
            checked_out=checked_out,
            overflow=overflow
        )

        logger.debug(
            "db_pool_metrics_updated",
            pool_size=pool_size,
            checked_out=checked_out,
            overflow=overflow
        )
    except Exception as e:
        logger.warning("db_pool_metrics_error", **safe_error_log(e))


@contextmanager
def track_db_operation(operation: str, table: str) -> Generator[None, None, None]:
    """
    Context manager for tracking database operations.

    Usage:
        with track_db_operation("select", "documents"):
            result = await session.execute(query)

    Args:
        operation: Operation type (select, insert, update, delete)
        table: Table name
    """
    start_time = time.perf_counter()
    status = "success"

    try:
        yield
    except Exception:
        status = "error"
        raise
    finally:
        duration = time.perf_counter() - start_time

        try:
            from app.core.business_metrics import record_db_query

            record_db_query(
                operation=operation,
                table=table,
                duration_seconds=duration,
                status=status
            )
        except Exception as e:
            logger.debug(
                "db_metrics_context_recording_failed",
                operation=operation,
                table=table,
                status=status,
                error_type=type(e).__name__,
            )


class DBMetricsMiddleware:
    """
    Middleware for tracking database metrics in FastAPI.

    Tracks connection pool status on each request.
    """

    def __init__(self, engine: Engine):
        """Initialize with engine reference."""
        self._engine = engine
        self._last_pool_update = 0
        self._pool_update_interval = 60  # Update pool metrics every 60s

    async def __call__(self, request: Request, call_next: Callable[[Request], object]) -> Response:
        """Process request and update metrics."""
        import time

        # Update pool metrics periodically
        current_time = time.time()
        if current_time - self._last_pool_update > self._pool_update_interval:
            update_pool_metrics(self._engine)
            self._last_pool_update = current_time

        return await call_next(request)
