"""
Safe Error Handling Utilities for Ablage-System OCR

This module provides utilities to prevent PII (Personally Identifiable Information)
leakage through exception messages in API responses and logs.

Security Context (CWE-532):
- Exception messages can contain database passwords, API keys, customer data
- str(e) in HTTPException detail exposes internal system state
- Log messages with str(e) can leak sensitive information to log aggregators

Usage:
    from app.core.safe_errors import safe_error_detail, safe_error_log

    try:
        await some_operation()
    except Exception as e:
        logger.error("Operation failed", **safe_error_log(e))
        raise HTTPException(status_code=500, detail=safe_error_detail(e, "Export"))

Created: 2026-01-29
"""

from typing import Any, Dict, Optional
from uuid import uuid4
import re


# Known exception types that are safe to expose (non-sensitive)
SAFE_EXCEPTION_TYPES = frozenset({
    "ValueError",
    "TypeError",
    "KeyError",
    "IndexError",
    "AttributeError",
    "FileNotFoundError",
    "PermissionError",
    "TimeoutError",
    "ConnectionError",
    "NotImplementedError",
    # Custom Ablage-System exceptions (already sanitized)
    "AblageSystemException",
    "NotFoundError",
    "ForbiddenError",
    "ValidationError",
    "GPUOutOfMemoryError",
    "OCRProcessingError",
    "DocumentNotFoundError",
    "InvalidDocumentFormatError",
    "FileSizeExceededError",
    "GDPRViolationError",
    "RateLimitError",
    "AuthenticationError",
    "BusinessLogicError",
    "WorkflowError",
})

# Patterns that indicate PII in exception messages
PII_PATTERNS = [
    re.compile(r"password[=:\s]", re.IGNORECASE),
    re.compile(r"api[_-]?key[=:\s]", re.IGNORECASE),
    re.compile(r"secret[=:\s]", re.IGNORECASE),
    re.compile(r"token[=:\s]", re.IGNORECASE),
    re.compile(r"bearer\s+\w+", re.IGNORECASE),
    re.compile(r"authorization[=:\s]", re.IGNORECASE),
    re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),  # Email
    re.compile(r"\b(?:DE)?\d{2}\s?\d{4}\s?\d{4}\s?\d{4}\s?\d{4}\s?\d{2}\b"),  # IBAN
    re.compile(r"\b\d{3}[-.\s]?\d{3}[-.\s]?\d{4}\b"),  # Phone
    re.compile(r"(?:kunden?|customer)[_-]?(?:nummer|number|nr|id)[=:\s]*\d+", re.IGNORECASE),
    re.compile(r"(?:vat|ust|mwst)[_-]?id[=:\s]", re.IGNORECASE),
    re.compile(r"connection[_-]?string[=:\s]", re.IGNORECASE),
    re.compile(r"postgres(?:ql)?://", re.IGNORECASE),
    re.compile(r"redis://", re.IGNORECASE),
    re.compile(r"mysql://", re.IGNORECASE),
    re.compile(r"mongodb://", re.IGNORECASE),
]


def _contains_pii(message: str) -> bool:
    """Check if message potentially contains PII."""
    if not message:
        return False
    for pattern in PII_PATTERNS:
        if pattern.search(message):
            return True
    return False


def _get_exception_type_name(e: Exception) -> str:
    """Get the type name of an exception safely."""
    try:
        return type(e).__name__
    except Exception:
        return "UnknownException"


def safe_error_detail(
    e: Exception,
    context: str = "Vorgang",
    include_type: bool = True,
    fallback_message: Optional[str] = None
) -> str:
    """
    Generate a safe error message for API responses without PII leakage.

    Args:
        e: The exception that occurred
        context: German context description (e.g., "Export", "Upload", "Verarbeitung")
        include_type: Whether to include the exception type name
        fallback_message: Custom fallback message if exception type is not safe

    Returns:
        Safe, German error message suitable for API responses

    Example:
        >>> safe_error_detail(ValueError("invalid input"), "Validierung")
        "Validierung fehlgeschlagen: ValueError"

        >>> safe_error_detail(Exception("DB password: secret123"), "Export")
        "Export fehlgeschlagen: Interner Fehler"
    """
    error_type = _get_exception_type_name(e)

    # For known safe exception types, we can be more specific
    if error_type in SAFE_EXCEPTION_TYPES:
        # Still check the message for PII
        error_message = str(e) if e.args else ""
        if not _contains_pii(error_message) and len(error_message) < 200:
            # For AblageSystem exceptions, use their user_message_de
            if hasattr(e, "user_message_de"):
                return str(e.user_message_de)
            # For other safe types, include type name
            if include_type:
                return f"{context} fehlgeschlagen: {error_type}"
            return f"{context} fehlgeschlagen"

    # For unknown/unsafe exception types, use generic message
    if fallback_message:
        return fallback_message

    if include_type:
        return f"{context} fehlgeschlagen: {error_type}"
    return f"{context} fehlgeschlagen: Interner Fehler"


def safe_error_log(
    e: Exception,
    context: Optional[str] = None,
    extra: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Generate safe logging data for an exception without PII leakage.

    Returns a dict suitable for structured logging with **safe_error_log(e).
    Includes a unique error_id for correlation with support tickets.

    Args:
        e: The exception that occurred
        context: Optional context string for the log
        extra: Additional safe data to include

    Returns:
        Dict with safe error information for logging

    Example:
        >>> logger.error("Export failed", **safe_error_log(e, context="PDF export"))
        # Logs: {"error_type": "ValueError", "error_id": "a1b2c3d4", "context": "PDF export"}
    """
    error_type = _get_exception_type_name(e)
    error_id = uuid4().hex[:8]  # Short ID for support tickets

    result: Dict[str, Any] = {
        "error_type": error_type,
        "error_id": error_id,
    }

    if context:
        result["context"] = context

    # Only include message for safe exception types
    if error_type in SAFE_EXCEPTION_TYPES:
        error_message = str(e) if e.args else ""
        if not _contains_pii(error_message) and len(error_message) < 500:
            result["error_message"] = error_message[:500]

    # Include AblageSystem exception details safely
    if hasattr(e, "error_code"):
        result["error_code"] = str(e.error_code)
    if hasattr(e, "details") and isinstance(e.details, dict):
        # Only include non-sensitive detail keys
        safe_keys = {"document_id", "backend", "retry_after_seconds", "operation"}
        result["error_details"] = {
            k: v for k, v in e.details.items()
            if k in safe_keys and not _contains_pii(str(v))
        }

    if extra:
        # Filter extra data for PII
        for key, value in extra.items():
            if not _contains_pii(str(value)):
                result[key] = value

    return result


def create_error_response(
    e: Exception,
    context: str = "Vorgang",
    status_code: int = 500,
    error_code: Optional[str] = None
) -> Dict[str, Any]:
    """
    Create a standardized error response dict for API endpoints.

    Args:
        e: The exception that occurred
        context: German context description
        status_code: HTTP status code
        error_code: Optional custom error code

    Returns:
        Standardized error response dict

    Example:
        >>> create_error_response(e, "Export", 500, "EXPORT_001")
        {
            "detail": "Export fehlgeschlagen: ValueError",
            "error_code": "EXPORT_001",
            "error_id": "a1b2c3d4"
        }
    """
    error_id = uuid4().hex[:8]

    result = {
        "detail": safe_error_detail(e, context),
        "error_id": error_id,
    }

    if error_code:
        result["error_code"] = error_code
    elif hasattr(e, "error_code"):
        result["error_code"] = str(e.error_code)

    return result


# German error messages for common contexts
ERROR_CONTEXTS = {
    "export": "Export",
    "import": "Import",
    "upload": "Upload",
    "download": "Download",
    "processing": "Verarbeitung",
    "validation": "Validierung",
    "authentication": "Authentifizierung",
    "authorization": "Autorisierung",
    "database": "Datenbankoperation",
    "ocr": "OCR-Verarbeitung",
    "search": "Suche",
    "calculation": "Berechnung",
    "notification": "Benachrichtigung",
    "sync": "Synchronisierung",
    "backup": "Backup",
    "restore": "Wiederherstellung",
}


def get_german_context(context_key: str) -> str:
    """
    Get German context string for error messages.

    Args:
        context_key: English context key

    Returns:
        German context string, or the input if not found
    """
    return ERROR_CONTEXTS.get(context_key.lower(), context_key)
