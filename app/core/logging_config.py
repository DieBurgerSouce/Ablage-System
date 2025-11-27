"""
Structured logging configuration for Ablage-System.

Provides JSON-formatted logs with correlation IDs and context.
"""
import sys
import logging
from typing import Any, Dict, Optional
import structlog
from structlog.processors import JSONRenderer, CallsiteParameter
from structlog.stdlib import LoggerFactory, add_logger_name, BoundLogger
import uuid
from datetime import datetime
import json

# German log level names
GERMAN_LOG_LEVELS = {
    "DEBUG": "FEHLERSUCHE",
    "INFO": "INFORMATION",
    "WARNING": "WARNUNG",
    "ERROR": "FEHLER",
    "CRITICAL": "KRITISCH"
}

class GermanLogLevelProcessor:
    """Convert log levels to German."""

    def __call__(self, logger: Any, method_name: str, event_dict: Dict[str, Any]) -> Dict[str, Any]:
        """Add German log level."""
        if "level" in event_dict:
            event_dict["stufe"] = GERMAN_LOG_LEVELS.get(event_dict["level"], event_dict["level"])
        return event_dict


class CorrelationIdProcessor:
    """Add correlation ID to logs for request tracing."""

    def __call__(self, logger: Any, method_name: str, event_dict: Dict[str, Any]) -> Dict[str, Any]:
        """Add correlation ID if available."""
        from contextvars import ContextVar
        correlation_id: ContextVar[Optional[str]] = ContextVar('correlation_id', default=None)

        if cid := correlation_id.get():
            event_dict["korrelations_id"] = cid
        return event_dict


class SensitiveDataFilter:
    """Filter sensitive data from logs (GDPR compliance)."""

    SENSITIVE_FIELDS = {
        "password", "passwort", "token", "access_token", "refresh_token",
        "api_key", "secret", "email", "iban", "credit_card", "ssn",
        "hashed_password", "authorization"
    }

    def __call__(self, logger: Any, method_name: str, event_dict: Dict[str, Any]) -> Dict[str, Any]:
        """Redact sensitive fields."""
        for key in list(event_dict.keys()):
            if any(sensitive in key.lower() for sensitive in self.SENSITIVE_FIELDS):
                event_dict[key] = "***ZENSIERT***"
        return event_dict


class PerformanceProcessor:
    """Add performance metrics to logs."""

    def __call__(self, logger: Any, method_name: str, event_dict: Dict[str, Any]) -> Dict[str, Any]:
        """Add timing information."""
        import time
        import psutil

        # Add timestamp
        event_dict["zeitstempel"] = datetime.utcnow().isoformat()

        # Add system metrics
        event_dict["system"] = {
            "cpu_prozent": psutil.cpu_percent(interval=0),
            "speicher_prozent": psutil.virtual_memory().percent,
            "festplatte_prozent": psutil.disk_usage('/').percent
        }

        # Add GPU metrics if available
        try:
            import torch
            if torch.cuda.is_available():
                event_dict["gpu"] = {
                    "verfuegbar": True,
                    "speicher_verwendet": torch.cuda.memory_allocated() / 1024**3,
                    "speicher_gesamt": torch.cuda.get_device_properties(0).total_memory / 1024**3
                }
        except ImportError:
            pass

        return event_dict


class RequestContextProcessor:
    """Add HTTP request context to logs."""

    def __call__(self, logger: Any, method_name: str, event_dict: Dict[str, Any]) -> Dict[str, Any]:
        """Add request context if available."""
        from starlette.requests import Request
        from contextvars import ContextVar

        request_var: ContextVar[Optional[Request]] = ContextVar('request', default=None)

        if request := request_var.get():
            event_dict["anfrage"] = {
                "methode": request.method,
                "pfad": request.url.path,
                "ip": request.client.host if request.client else None,
                "user_agent": request.headers.get("User-Agent", "Unbekannt")
            }

        return event_dict


def configure_logging(
    log_level: str = "INFO",
    log_format: str = "json",
    log_file: Optional[str] = None,
    enable_performance: bool = True,
    enable_sensitive_filter: bool = True
) -> None:
    """
    Configure structured logging for the application.

    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_format: Output format ('json' or 'console')
        log_file: Optional file path for log output
        enable_performance: Include performance metrics
        enable_sensitive_filter: Filter sensitive data
    """

    # Configure processors
    processors = [
        # Add log level
        structlog.stdlib.add_log_level,
        # Add logger name
        add_logger_name,
        # Add timestamp
        structlog.processors.TimeStamper(fmt="iso"),
        # Add German log level
        GermanLogLevelProcessor(),
        # Add correlation ID
        CorrelationIdProcessor(),
        # Add request context
        RequestContextProcessor(),
    ]

    # Optional processors
    if enable_sensitive_filter:
        processors.append(SensitiveDataFilter())

    if enable_performance:
        processors.append(PerformanceProcessor())

    # Add call site information (file, function, line)
    processors.append(
        structlog.processors.CallsiteParameterAdder(
            parameters=[
                CallsiteParameter.FILENAME,
                CallsiteParameter.FUNC_NAME,
                CallsiteParameter.LINENO,
            ]
        )
    )

    # Stack info for errors
    processors.append(structlog.processors.StackInfoRenderer())

    # Format exceptions
    processors.append(structlog.processors.format_exc_info)

    # Choose renderer based on format
    if log_format == "json":
        processors.append(JSONRenderer())
    else:
        processors.append(structlog.dev.ConsoleRenderer())

    # Configure structlog
    structlog.configure(
        processors=processors,
        context_class=dict,
        logger_factory=LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Configure standard logging
    handlers = []

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(getattr(logging, log_level))
    handlers.append(console_handler)

    # File handler if specified
    if log_file:
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setLevel(getattr(logging, log_level))
        handlers.append(file_handler)

    # Configure root logger
    logging.basicConfig(
        level=getattr(logging, log_level),
        handlers=handlers,
        format="%(message)s"
    )

    # Suppress noisy libraries
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("watchfiles").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)


def get_logger(name: str = __name__) -> BoundLogger:
    """
    Get a structured logger instance.

    Args:
        name: Logger name (usually __name__)

    Returns:
        Configured structlog logger
    """
    return structlog.get_logger(name)


# Convenience functions for German logging
def log_erfolg(logger: BoundLogger, nachricht: str, **kwargs: Any) -> None:
    """Log success message in German."""
    logger.info(nachricht, typ="erfolg", **kwargs)


def log_warnung(logger: BoundLogger, nachricht: str, **kwargs: Any) -> None:
    """Log warning message in German."""
    logger.warning(nachricht, typ="warnung", **kwargs)


def log_fehler(logger: BoundLogger, nachricht: str, **kwargs: Any) -> None:
    """Log error message in German."""
    logger.error(nachricht, typ="fehler", **kwargs)


def log_ocr_verarbeitung(
    logger: BoundLogger,
    dokument_id: str,
    backend: str,
    status: str,
    dauer_ms: Optional[int] = None,
    **kwargs: Any
) -> None:
    """Log OCR processing event."""
    logger.info(
        "OCR Verarbeitung",
        dokument_id=dokument_id,
        backend=backend,
        status=status,
        dauer_ms=dauer_ms,
        kategorie="ocr",
        **kwargs
    )


def log_authentifizierung(
    logger: BoundLogger,
    benutzer: str,
    aktion: str,
    erfolgreich: bool,
    ip_adresse: Optional[str] = None,
    **kwargs: Any
) -> None:
    """Log authentication event."""
    level = "info" if erfolgreich else "warning"
    getattr(logger, level)(
        "Authentifizierung",
        benutzer=benutzer,
        aktion=aktion,
        erfolgreich=erfolgreich,
        ip_adresse=ip_adresse,
        kategorie="sicherheit",
        **kwargs
    )


def log_api_anfrage(
    logger: BoundLogger,
    methode: str,
    pfad: str,
    status_code: int,
    dauer_ms: int,
    benutzer_id: Optional[str] = None,
    **kwargs: Any
) -> None:
    """Log API request."""
    logger.info(
        "API Anfrage",
        methode=methode,
        pfad=pfad,
        status_code=status_code,
        dauer_ms=dauer_ms,
        benutzer_id=benutzer_id,
        kategorie="api",
        **kwargs
    )


def log_datenbank_operation(
    logger: BoundLogger,
    operation: str,
    tabelle: str,
    dauer_ms: int,
    zeilen_betroffen: Optional[int] = None,
    **kwargs: Any
) -> None:
    """Log database operation."""
    logger.debug(
        "Datenbank Operation",
        operation=operation,
        tabelle=tabelle,
        dauer_ms=dauer_ms,
        zeilen_betroffen=zeilen_betroffen,
        kategorie="datenbank",
        **kwargs
    )


# Export main components
__all__ = [
    'configure_logging',
    'get_logger',
    'log_erfolg',
    'log_warnung',
    'log_fehler',
    'log_ocr_verarbeitung',
    'log_authentifizierung',
    'log_api_anfrage',
    'log_datenbank_operation',
    'GermanLogLevelProcessor',
    'CorrelationIdProcessor',
    'SensitiveDataFilter',
    'PerformanceProcessor',
    'RequestContextProcessor'
]