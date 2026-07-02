# -*- coding: utf-8 -*-
"""
Celery Task Error Handling Decorator for Ablage-System.

Provides a structured, type-classified error handling decorator for Celery tasks.
Replaces bare ``except Exception as e: pass`` blocks with explicit retry logic
and safe, PII-protected structured logging.

Error classification and retry behaviour
-----------------------------------------
1. **Netzwerk-Fehler** (``ConnectionError``, ``TimeoutError``, ``OSError``):
   Transient. Task is retried up to *max_retries* times with a delay of
   *retry_countdown* seconds between attempts.

2. **Datenbankfehler** (SQLAlchemy ``OperationalError``, ``InterfaceError``):
   Transient. Retried up to *max_retries* times with a delay of
   *db_retry_countdown* seconds.

3. **Validierungsfehler** (``app.core.exceptions.ValidationError``,
   ``pydantic.ValidationError``, built-in ``ValueError``):
   Permanent. Task fails immediately without retry.  A structured ERROR
   log entry is written.

4. **Unbekannte Fehler** (all other ``Exception`` subclasses):
   Full traceback is captured via ``logger.exception`` and the exception is
   **re-raised without modification**.  Exceptions are *never* swallowed.

All log entries include:
    - ``task_name``           – Celery task name
    - ``task_id``             – Celery task request ID
    - ``error_category``      – machine-readable category string
    - ``fehler_klassifizierung`` – German human-readable classification label
    - All fields returned by ``safe_error_log()`` (PII-safe, CWE-532)

Usage::

    from app.workers.error_handling import celery_error_handler

    # Basic usage with default limits
    @celery_app.task(bind=True)
    @celery_error_handler()
    def process_banking_transaction(self, transaction_id: str) -> dict:
        ...

    # Custom retry parameters
    @celery_app.task(bind=True)
    @celery_error_handler(max_retries=5, retry_countdown=30, db_retry_countdown=90)
    def heavy_import_task(self, batch_id: str) -> dict:
        ...

    # Async tasks are handled automatically
    @celery_app.task(bind=True)
    @celery_error_handler()
    async def async_ocr_task(self, document_id: str) -> dict:
        ...

    # classify_exception is also importable for ad-hoc use
    from app.workers.error_handling import classify_exception
    category = classify_exception(some_exc)  # "transient" | "permanent" | "unknown"

Security note:
    All log entries pass through ``safe_error_log`` and ``safe_error_detail``
    to prevent PII leakage into log aggregators (CWE-532).

Created: 2026-02-26
"""

from __future__ import annotations

import asyncio
import functools
from typing import Callable, TypeVar

import structlog
from sqlalchemy.exc import InterfaceError, OperationalError

from app.core.safe_errors import safe_error_detail, safe_error_log

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Sentinel TypeVar – keeps the wrapper return type identical to the wrapped fn
# ---------------------------------------------------------------------------
_RT = TypeVar("_RT")

# ---------------------------------------------------------------------------
# Error category constants used in structured log entries
# ---------------------------------------------------------------------------
_CATEGORY_NETWORK: str = "transient_network"
_CATEGORY_DATABASE: str = "transient_database"
_CATEGORY_VALIDATION: str = "permanent_validation"
_CATEGORY_UNKNOWN: str = "unknown"

# ---------------------------------------------------------------------------
# Default retry configuration (can be overridden per task via the decorator)
# ---------------------------------------------------------------------------
_DEFAULT_MAX_RETRIES: int = 3
_DEFAULT_NETWORK_COUNTDOWN: int = 60   # seconds
_DEFAULT_DB_COUNTDOWN: int = 120       # seconds

# ---------------------------------------------------------------------------
# Exception type groups – built lazily to avoid import-time circular imports
# ---------------------------------------------------------------------------

# Transient network / OS layer errors
_NETWORK_EXCEPTION_TYPES: tuple[type[Exception], ...] = (
    ConnectionError,
    ConnectionRefusedError,
    ConnectionResetError,
    TimeoutError,
    OSError,
)

# Transient database errors (SQLAlchemy)
_DATABASE_EXCEPTION_TYPES: tuple[type[Exception], ...] = (
    OperationalError,
    InterfaceError,
)

# Permanent validation / value errors – extended at module load time
_VALIDATION_EXCEPTION_TYPES: tuple[type[Exception], ...] = (
    ValueError,
)

# Optional: project-level ValidationError
try:
    from app.core.exceptions import ValidationError as _AblageValidationError
    _VALIDATION_EXCEPTION_TYPES = _VALIDATION_EXCEPTION_TYPES + (_AblageValidationError,)
except ImportError:
    pass  # Projekt-ValidationError optional: bleibt aus der Klassifizierung

# Optional: pydantic ValidationError
try:
    from pydantic import ValidationError as _PydanticValidationError
    _VALIDATION_EXCEPTION_TYPES = _VALIDATION_EXCEPTION_TYPES + (_PydanticValidationError,)
except ImportError:
    pass  # pydantic-ValidationError optional: bleibt aus der Klassifizierung


# ---------------------------------------------------------------------------
# Public classification helper
# ---------------------------------------------------------------------------

def classify_exception(exc: Exception) -> str:
    """Classify an exception as 'transient', 'permanent', or 'unknown'.

    This function is exported for ad-hoc use outside the decorator, e.g. in
    ``except`` blocks that cannot use the decorator pattern.

    Classification rules (in priority order):

    1. ``ConnectionError``, ``TimeoutError``, ``OSError`` → ``"transient"``
    2. SQLAlchemy ``OperationalError``, ``InterfaceError`` → ``"transient"``
    3. ``ValueError``, project/pydantic ``ValidationError`` → ``"permanent"``
    4. Any other ``Exception`` subclass → ``"unknown"``

    Args:
        exc: The exception instance to classify.

    Returns:
        One of ``"transient"``, ``"permanent"``, or ``"unknown"``.

    Example::

        from app.workers.error_handling import classify_exception

        try:
            risky_call()
        except Exception as e:
            category = classify_exception(e)
            if category == "transient":
                raise self.retry(exc=e)
            raise
    """
    if isinstance(exc, _NETWORK_EXCEPTION_TYPES):
        return "transient"
    if isinstance(exc, _DATABASE_EXCEPTION_TYPES):
        return "transient"
    if isinstance(exc, _VALIDATION_EXCEPTION_TYPES):
        return "permanent"
    return "unknown"


# ---------------------------------------------------------------------------
# Decorator factory
# ---------------------------------------------------------------------------

def celery_error_handler(
    *,
    max_retries: int = _DEFAULT_MAX_RETRIES,
    retry_countdown: int = _DEFAULT_NETWORK_COUNTDOWN,
    db_retry_countdown: int = _DEFAULT_DB_COUNTDOWN,
) -> Callable[[Callable[..., _RT]], Callable[..., _RT]]:
    """Decorator factory for structured Celery task error handling.

    The decorated function MUST be a bound Celery task (``bind=True``).
    Both synchronous and async task functions are supported.

    Args:
        max_retries: Maximum number of retry attempts for transient errors.
            Passed directly to ``self.retry(max_retries=...)``.  The Celery
            task-level ``max_retries`` is overridden per invocation.
            Default: 3.
        retry_countdown: Seconds to wait before retrying after a network /
            OS error.  Default: 60.
        db_retry_countdown: Seconds to wait before retrying after a database
            connectivity error.  Default: 120.

    Returns:
        A decorator applicable to a bound Celery task function.

    Raises:
        ``celery.exceptions.Retry`` – propagated from ``self.retry()`` for
            transient errors (network and database categories).
        ``ValueError`` | project ``ValidationError`` | pydantic
            ``ValidationError`` – re-raised immediately for permanent errors.
        ``Exception`` – re-raised for unknown errors; never swallowed.

    Example::

        from app.workers.error_handling import celery_error_handler

        @celery_app.task(bind=True)
        @celery_error_handler(max_retries=3, retry_countdown=60)
        def process_banking_transaction(self, transaction_id: str) -> dict:
            ...
    """

    def decorator(func: Callable[..., _RT]) -> Callable[..., _RT]:

        @functools.wraps(func)
        def wrapper(task_self: object, *args: object, **kwargs: object) -> _RT:
            # Resolve task metadata for log correlation
            task_name: str = getattr(task_self, "name", None) or func.__qualname__
            task_request: object = getattr(task_self, "request", None)
            task_id: str = getattr(task_request, "id", None) or "unknown"

            try:
                if asyncio.iscoroutinefunction(func):
                    # asyncio.run() is safe here: Celery workers are not
                    # running inside an existing event loop.
                    return asyncio.run(func(task_self, *args, **kwargs))  # type: ignore[return-value]
                return func(task_self, *args, **kwargs)

            # ------------------------------------------------------------------
            # Netzwerk-Fehler (transient)
            # ------------------------------------------------------------------
            except _NETWORK_EXCEPTION_TYPES as exc:
                _log_transient(
                    exc,
                    category=_CATEGORY_NETWORK,
                    task_name=task_name,
                    task_id=task_id,
                )
                raise task_self.retry(  # type: ignore[attr-defined]
                    exc=exc,
                    countdown=retry_countdown,
                    max_retries=max_retries,
                )

            # ------------------------------------------------------------------
            # Datenbankfehler (transient)
            # ------------------------------------------------------------------
            except _DATABASE_EXCEPTION_TYPES as exc:
                _log_transient(
                    exc,
                    category=_CATEGORY_DATABASE,
                    task_name=task_name,
                    task_id=task_id,
                )
                raise task_self.retry(  # type: ignore[attr-defined]
                    exc=exc,
                    countdown=db_retry_countdown,
                    max_retries=max_retries,
                )

            # ------------------------------------------------------------------
            # Validierungsfehler (permanent)
            # ------------------------------------------------------------------
            except _VALIDATION_EXCEPTION_TYPES as exc:
                _log_permanent(
                    exc,
                    category=_CATEGORY_VALIDATION,
                    task_name=task_name,
                    task_id=task_id,
                )
                raise

            # ------------------------------------------------------------------
            # Unbekannte Fehler (catch-all – never swallow)
            # ------------------------------------------------------------------
            except Exception as exc:  # noqa: BLE001
                _log_unknown(
                    exc,
                    task_name=task_name,
                    task_id=task_id,
                )
                raise

        return wrapper  # type: ignore[return-value]

    return decorator


# ---------------------------------------------------------------------------
# Internal structured-log helpers
# ---------------------------------------------------------------------------

def _log_transient(
    exc: Exception,
    *,
    category: str,
    task_name: str,
    task_id: str,
) -> None:
    """Emit a WARNING log entry for a transient (retryable) exception.

    Uses ``safe_error_log`` to prevent PII leakage into log aggregators.

    Args:
        exc: The caught exception.
        category: One of the ``_CATEGORY_*`` module constants.
        task_name: Celery task name for log correlation.
        task_id: Celery request ID for log correlation.
    """
    logger.warning(
        "celery_task_transient_error",
        task_name=task_name,
        task_id=task_id,
        error_category=category,
        fehler_klassifizierung="Voruebergehender Fehler – Wiederholung geplant",
        **safe_error_log(exc, context=task_name),
    )


def _log_permanent(
    exc: Exception,
    *,
    category: str,
    task_name: str,
    task_id: str,
) -> None:
    """Emit an ERROR log entry for a permanent (non-retryable) exception.

    Uses both ``safe_error_log`` (structured fields) and ``safe_error_detail``
    (German human-readable description) to prevent PII leakage.

    Args:
        exc: The caught exception.
        category: One of the ``_CATEGORY_*`` module constants.
        task_name: Celery task name for log correlation.
        task_id: Celery request ID for log correlation.
    """
    logger.error(
        "celery_task_permanent_error",
        task_name=task_name,
        task_id=task_id,
        error_category=category,
        fehler_klassifizierung="Permanenter Fehler – keine Wiederholung",
        fehler_detail=safe_error_detail(exc, context="Aufgabenverarbeitung"),
        **safe_error_log(exc, context=task_name),
    )


def _log_unknown(
    exc: Exception,
    *,
    task_name: str,
    task_id: str,
) -> None:
    """Emit an ERROR log entry with full traceback for an unclassified exception.

    ``logger.exception`` is used so that structlog captures the full traceback.
    The exception is *never* swallowed; callers must re-raise after this call.

    Args:
        exc: The caught exception.
        task_name: Celery task name for log correlation.
        task_id: Celery request ID for log correlation.
    """
    logger.exception(
        "celery_task_unknown_error",
        task_name=task_name,
        task_id=task_id,
        error_category=_CATEGORY_UNKNOWN,
        fehler_klassifizierung="Unbekannter Fehler – Ausnahme wird weitergeleitet",
        fehler_detail=safe_error_detail(exc, context="Aufgabenverarbeitung"),
        **safe_error_log(exc, context=task_name),
    )


# ---------------------------------------------------------------------------
# Optional: convenience alias for the common no-arg usage pattern
# ---------------------------------------------------------------------------

#: ``celery_error_handler`` with all defaults applied.  Equivalent to calling
#: ``celery_error_handler()`` without arguments.  Provided as a convenience
#: for tasks that do not need to customise retry parameters.
#:
#: Example::
#:
#:     @celery_app.task(bind=True)
#:     @default_celery_error_handler
#:     def simple_task(self, doc_id: str) -> dict:
#:         ...
default_celery_error_handler: Callable[[Callable[..., _RT]], Callable[..., _RT]] = (
    celery_error_handler()
)
