"""
Logging utilities for Ablage-System.

Provides convenient logging functions and decorators.
"""
import time
import functools
from typing import Callable, Generator, Optional, TypeVar, ParamSpec, Concatenate
import structlog
from contextlib import contextmanager
import asyncio

# Type variables for decorated functions (PEP 612)
P = ParamSpec('P')
R = TypeVar('R')

# Get logger
logger = structlog.get_logger(__name__)


def log_execution_time(
    operation_name: Optional[str] = None,
    log_level: str = "info",
    include_args: bool = False,
    german: bool = True
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """
    Decorator to log execution time of functions.

    Args:
        operation_name: Custom name for the operation
        log_level: Log level to use
        include_args: Whether to include function arguments in log
        german: Use German language for logging

    Returns:
        Decorated function with preserved signature
    """
    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        name = operation_name or func.__name__

        @functools.wraps(func)
        async def async_wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            start_time = time.time()
            log_data: dict[str, object] = {
                "operation": name,
                "typ": "ausführungszeit"
            }

            if include_args:
                log_data["argumente"] = {
                    "args": str(args)[:200],
                    "kwargs": str(kwargs)[:200]
                }

            try:
                result = await func(*args, **kwargs)  # type: ignore[misc]
                duration_ms = int((time.time() - start_time) * 1000)

                log_data.update({
                    "dauer_ms": duration_ms,
                    "status": "erfolgreich" if german else "success"
                })

                message = f"Operation '{name}' abgeschlossen" if german else f"Operation '{name}' completed"
                getattr(logger, log_level)(message, **log_data)

                return result
            except Exception as e:
                duration_ms = int((time.time() - start_time) * 1000)

                log_data.update({
                    "dauer_ms": duration_ms,
                    "status": "fehlgeschlagen" if german else "failed",
                    "fehler": str(e)
                })

                message = f"Operation '{name}' fehlgeschlagen" if german else f"Operation '{name}' failed"
                logger.error(message, **log_data, exc_info=True)
                raise

        @functools.wraps(func)
        def sync_wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            start_time = time.time()
            log_data: dict[str, object] = {
                "operation": name,
                "typ": "ausführungszeit"
            }

            if include_args:
                log_data["argumente"] = {
                    "args": str(args)[:200],
                    "kwargs": str(kwargs)[:200]
                }

            try:
                result = func(*args, **kwargs)
                duration_ms = int((time.time() - start_time) * 1000)

                log_data.update({
                    "dauer_ms": duration_ms,
                    "status": "erfolgreich" if german else "success"
                })

                message = f"Operation '{name}' abgeschlossen" if german else f"Operation '{name}' completed"
                getattr(logger, log_level)(message, **log_data)

                return result
            except Exception as e:
                duration_ms = int((time.time() - start_time) * 1000)

                log_data.update({
                    "dauer_ms": duration_ms,
                    "status": "fehlgeschlagen" if german else "failed",
                    "fehler": str(e)
                })

                message = f"Operation '{name}' fehlgeschlagen" if german else f"Operation '{name}' failed"
                logger.error(message, **log_data, exc_info=True)
                raise

        # Return appropriate wrapper based on function type
        if asyncio.iscoroutinefunction(func):
            return async_wrapper  # type: ignore[return-value]
        else:
            return sync_wrapper  # type: ignore[return-value]

    return decorator


def log_retry(
    max_retries: int = 3,
    backoff_seconds: float = 1.0,
    german: bool = True
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """
    Decorator to add retry logic with logging.

    Args:
        max_retries: Maximum number of retry attempts
        backoff_seconds: Initial backoff time in seconds
        german: Use German language for logging

    Returns:
        Decorated function with preserved signature
    """
    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        @functools.wraps(func)
        async def async_wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            last_exception: Optional[Exception] = None

            for attempt in range(max_retries):
                try:
                    if attempt > 0:
                        wait_time = backoff_seconds * (2 ** (attempt - 1))
                        message = f"Wiederhole nach {wait_time}s (Versuch {attempt + 1}/{max_retries})" if german else f"Retrying after {wait_time}s (attempt {attempt + 1}/{max_retries})"
                        logger.info(
                            message,
                            operation=func.__name__,
                            versuch=attempt + 1,
                            max_versuche=max_retries,
                            wartezeit_s=wait_time
                        )
                        await asyncio.sleep(wait_time)

                    return await func(*args, **kwargs)  # type: ignore[misc]

                except Exception as e:
                    last_exception = e
                    message = f"Versuch {attempt + 1} fehlgeschlagen" if german else f"Attempt {attempt + 1} failed"
                    logger.warning(
                        message,
                        operation=func.__name__,
                        versuch=attempt + 1,
                        max_versuche=max_retries,
                        fehler=str(e)
                    )

            # All retries exhausted
            message = f"Alle Versuche fehlgeschlagen für '{func.__name__}'" if german else f"All retries exhausted for '{func.__name__}'"
            logger.error(
                message,
                operation=func.__name__,
                max_versuche=max_retries,
                exc_info=True
            )
            if last_exception is not None:
                raise last_exception
            raise RuntimeError("Unerwarteter Fehler: last_exception ist None")

        @functools.wraps(func)
        def sync_wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            last_exception: Optional[Exception] = None

            for attempt in range(max_retries):
                try:
                    if attempt > 0:
                        wait_time = backoff_seconds * (2 ** (attempt - 1))
                        message = f"Wiederhole nach {wait_time}s (Versuch {attempt + 1}/{max_retries})" if german else f"Retrying after {wait_time}s (attempt {attempt + 1}/{max_retries})"
                        logger.info(
                            message,
                            operation=func.__name__,
                            versuch=attempt + 1,
                            max_versuche=max_retries,
                            wartezeit_s=wait_time
                        )
                        time.sleep(wait_time)

                    return func(*args, **kwargs)

                except Exception as e:
                    last_exception = e
                    message = f"Versuch {attempt + 1} fehlgeschlagen" if german else f"Attempt {attempt + 1} failed"
                    logger.warning(
                        message,
                        operation=func.__name__,
                        versuch=attempt + 1,
                        max_versuche=max_retries,
                        fehler=str(e)
                    )

            # All retries exhausted
            message = f"Alle Versuche fehlgeschlagen für '{func.__name__}'" if german else f"All retries exhausted for '{func.__name__}'"
            logger.error(
                message,
                operation=func.__name__,
                max_versuche=max_retries,
                exc_info=True
            )
            if last_exception is not None:
                raise last_exception
            raise RuntimeError("Unerwarteter Fehler: last_exception ist None")

        if asyncio.iscoroutinefunction(func):
            return async_wrapper  # type: ignore[return-value]
        else:
            return sync_wrapper  # type: ignore[return-value]

    return decorator


@contextmanager
def log_context(**kwargs: object) -> Generator[None, None, None]:
    """
    Context manager to add contextual information to logs.

    Usage:
        with log_context(dokument_id="123", benutzer="max"):
            logger.info("Processing document")
    """
    try:
        structlog.contextvars.bind_contextvars(**kwargs)
        yield
    finally:
        structlog.contextvars.clear_contextvars()


class OCRLogger:
    """Specialized logger for OCR operations."""

    def __init__(self, bound_logger: Optional[structlog.BoundLogger] = None):
        """Initialize OCR logger."""
        self._logger = bound_logger or structlog.get_logger("ocr")

    def log_start(self, dokument_id: str, backend: str, **kwargs: object) -> None:
        """Log OCR processing start."""
        self._logger.info(
            "OCR Verarbeitung gestartet",
            dokument_id=dokument_id,
            backend=backend,
            ereignis="ocr_start",
            **kwargs
        )

    def log_progress(
        self,
        dokument_id: str,
        fortschritt: int,
        nachricht: str,
        **kwargs: object
    ) -> None:
        """Log OCR processing progress."""
        self._logger.info(
            f"OCR Fortschritt: {nachricht}",
            dokument_id=dokument_id,
            fortschritt_prozent=fortschritt,
            ereignis="ocr_fortschritt",
            **kwargs
        )

    def log_complete(
        self,
        dokument_id: str,
        backend: str,
        dauer_ms: int,
        zeichen_extrahiert: int,
        **kwargs: object
    ) -> None:
        """Log OCR processing completion."""
        self._logger.info(
            "OCR Verarbeitung abgeschlossen",
            dokument_id=dokument_id,
            backend=backend,
            dauer_ms=dauer_ms,
            zeichen_extrahiert=zeichen_extrahiert,
            ereignis="ocr_abgeschlossen",
            **kwargs
        )

    def log_error(
        self,
        dokument_id: str,
        backend: str,
        fehler: str,
        **kwargs: object
    ) -> None:
        """Log OCR processing error."""
        self._logger.error(
            "OCR Verarbeitung fehlgeschlagen",
            dokument_id=dokument_id,
            backend=backend,
            fehler=fehler,
            ereignis="ocr_fehler",
            exc_info=True,
            **kwargs
        )


class DatabaseLogger:
    """Specialized logger for database operations."""

    def __init__(self, logger: Optional[structlog.BoundLogger] = None):
        """Initialize database logger."""
        self.logger = logger or structlog.get_logger("database")

    def log_query(
        self,
        query: str,
        dauer_ms: int,
        zeilen: Optional[int] = None,
        **kwargs: object
    ) -> None:
        """Log database query."""
        self.logger.debug(
            "Datenbank Abfrage",
            query=query[:200],  # Truncate long queries
            dauer_ms=dauer_ms,
            zeilen_betroffen=zeilen,
            ereignis="db_query",
            **kwargs
        )

    def log_transaction_start(self, transaction_id: str, **kwargs: object) -> None:
        """Log transaction start."""
        self.logger.debug(
            "Transaktion gestartet",
            transaction_id=transaction_id,
            ereignis="db_transaction_start",
            **kwargs
        )

    def log_transaction_commit(
        self,
        transaction_id: str,
        dauer_ms: int,
        **kwargs: object
    ) -> None:
        """Log transaction commit."""
        self.logger.debug(
            "Transaktion abgeschlossen",
            transaction_id=transaction_id,
            dauer_ms=dauer_ms,
            ereignis="db_transaction_commit",
            **kwargs
        )

    def log_transaction_rollback(
        self,
        transaction_id: str,
        grund: str,
        **kwargs: object
    ) -> None:
        """Log transaction rollback."""
        self.logger.warning(
            "Transaktion zurückgerollt",
            transaction_id=transaction_id,
            grund=grund,
            ereignis="db_transaction_rollback",
            **kwargs
        )


class SecurityLogger:
    """Specialized logger for security events."""

    def __init__(self, logger: Optional[structlog.BoundLogger] = None):
        """Initialize security logger."""
        self.logger = logger or structlog.get_logger("security")

    def log_login_attempt(
        self,
        benutzer: str,
        erfolgreich: bool,
        ip_adresse: str,
        **kwargs: object
    ) -> None:
        """Log login attempt."""
        level = "info" if erfolgreich else "warning"
        getattr(self.logger, level)(
            "Anmeldeversuch",
            benutzer=benutzer,
            erfolgreich=erfolgreich,
            ip_adresse=ip_adresse,
            ereignis="login_versuch",
            **kwargs
        )

    def log_access_denied(
        self,
        benutzer: str,
        ressource: str,
        grund: str,
        **kwargs: object
    ) -> None:
        """Log access denied event."""
        self.logger.warning(
            "Zugriff verweigert",
            benutzer=benutzer,
            ressource=ressource,
            grund=grund,
            ereignis="zugriff_verweigert",
            **kwargs
        )

    def log_rate_limit_exceeded(
        self,
        ip_adresse: str,
        endpoint: str,
        limit: int,
        **kwargs: object
    ) -> None:
        """Log rate limit exceeded."""
        self.logger.warning(
            "Ratenlimit überschritten",
            ip_adresse=ip_adresse,
            endpoint=endpoint,
            limit=limit,
            ereignis="ratenlimit_überschritten",
            **kwargs
        )

    def log_suspicious_activity(
        self,
        beschreibung: str,
        ip_adresse: str,
        **kwargs: object
    ) -> None:
        """Log suspicious activity."""
        self.logger.warning(
            "Verdächtige Aktivität erkannt",
            beschreibung=beschreibung,
            ip_adresse=ip_adresse,
            ereignis="verdächtige_aktivität",
            **kwargs
        )


# Export convenience instances
ocr_logger = OCRLogger()
db_logger = DatabaseLogger()
security_logger = SecurityLogger()

# Export all components
__all__ = [
    'log_execution_time',
    'log_retry',
    'log_context',
    'OCRLogger',
    'DatabaseLogger',
    'SecurityLogger',
    'ocr_logger',
    'db_logger',
    'security_logger'
]