"""
Unified Exception Handlers für Ablage-System OCR.

Zentrale Fehlerbehandlung mit konsistenten deutschen Antworten.
Alle API-Fehler folgen dem gleichen Format für bessere Client-Integration.

Art. 32 DSGVO - Sicherheit der Verarbeitung:
Fehler werden protokolliert ohne sensible Daten preiszugeben.

Created: 2025-11-30
"""

from datetime import datetime, timezone
from typing import Dict, Any, Optional, Type

from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
import structlog

from app.core.exceptions import (
    AblageSystemException,
    GPUException,
    GPUOutOfMemoryError,
    GPUNotAvailableError,
    OCRException,
    OCRProcessingError,
    OCRBackendTimeoutError,
    BackendSelectionError,
    GermanTextException,
    InvalidGermanEncodingError,
    DocumentException,
    DocumentNotFoundError,
    InvalidDocumentFormatError,
    FileSizeExceededError,
    DatabaseException,
    DatabaseConnectionError,
    ComplianceException,
    GDPRViolationError,
    GDPRError,
    UserNotFoundError,
    ExportError,
    EmailVerificationError,
)
from app.core.file_validation import (
    FileValidationError,
    DecompressionBombError,
    ImageBombError,
    TooManyPagesError,
)
from app.core.rate_limiting import RateLimitStorageError
from app.core.encryption import EncryptionError, KeyNotConfiguredError, DecryptionError
from app.core.totp import (
    TOTPError,
    TOTPNotAvailableError,
    TOTPInvalidCodeError,
    TOTPAlreadyEnabledError,
    TOTPNotEnabledError,
    TOTPSecretEncryptionError,
)
from app.core.session_manager import SessionError, SessionLimitReachedError
from app.core.account_lockout import AccountLockoutStorageError
from app.core.circuit_breaker import CircuitOpenError
from app.core.gpu_recovery import GPURecoveryError
from app.core.retry_strategy import RetryExhaustedError
from app.services.api_key_service import APIKeyError, APIKeyLimitError, APIKeyNotFoundError
from app.middleware.csrf import CSRFError
from app.services.error_tracking_service import (
    get_error_tracking_service,
    ErrorCategory,
    ErrorSeverity,
)

logger = structlog.get_logger(__name__)


# HTTP Status Code Mapping für Exception-Typen
EXCEPTION_STATUS_CODES: Dict[Type[Exception], int] = {
    # 400 Bad Request - Client-Fehler
    InvalidDocumentFormatError: 400,
    InvalidGermanEncodingError: 400,
    FileValidationError: 400,
    DecompressionBombError: 400,
    ImageBombError: 400,
    TooManyPagesError: 400,
    TOTPInvalidCodeError: 400,
    TOTPAlreadyEnabledError: 400,
    TOTPNotEnabledError: 400,
    CSRFError: 400,

    # 401 Unauthorized
    # (Handled by FastAPI's security dependencies)

    # 403 Forbidden
    GDPRViolationError: 403,
    APIKeyError: 403,
    APIKeyLimitError: 403,

    # 404 Not Found
    DocumentNotFoundError: 404,
    UserNotFoundError: 404,
    APIKeyNotFoundError: 404,

    # 408 Request Timeout
    OCRBackendTimeoutError: 408,

    # 409 Conflict
    SessionLimitReachedError: 409,

    # 413 Payload Too Large
    FileSizeExceededError: 413,

    # 429 Too Many Requests - Handled by rate limiter

    # 500 Internal Server Error
    OCRProcessingError: 500,
    BackendSelectionError: 500,
    DatabaseConnectionError: 500,
    EncryptionError: 500,
    KeyNotConfiguredError: 500,
    DecryptionError: 500,
    TOTPSecretEncryptionError: 500,
    ExportError: 500,
    EmailVerificationError: 500,
    RetryExhaustedError: 500,

    # 502 Bad Gateway
    GPURecoveryError: 502,

    # 503 Service Unavailable
    GPUOutOfMemoryError: 503,
    GPUNotAvailableError: 503,
    RateLimitStorageError: 503,
    TOTPNotAvailableError: 503,
    AccountLockoutStorageError: 503,
    CircuitOpenError: 503,
    SessionError: 503,
}


def create_error_response(
    fehler: str,
    nachricht: str,
    status_code: int,
    fehler_code: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
    pfad: Optional[str] = None,
    retry_after: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Erstellt ein standardisiertes Fehler-Response-Dict.

    Alle Fehlerantworten folgen diesem Format für konsistente Client-Integration.

    Args:
        fehler: Kurze Fehlerbezeichnung (z.B. "Validierungsfehler")
        nachricht: Detaillierte Fehlerbeschreibung für den Benutzer
        status_code: HTTP Status Code
        fehler_code: Interner Fehlercode (z.B. "E001")
        details: Zusätzliche technische Details (nur in DEBUG)
        pfad: Request-Pfad
        retry_after: Sekunden bis zum nächsten Versuch (für 503/429)

    Returns:
        Standardisiertes Fehler-Dict
    """
    response: Dict[str, Any] = {
        "fehler": fehler,
        "nachricht": nachricht,
        "status_code": status_code,
        "zeitstempel": datetime.now(timezone.utc).isoformat(),
    }

    if fehler_code:
        response["fehler_code"] = fehler_code

    if pfad:
        response["pfad"] = pfad

    if details:
        # Filter sensible Daten aus Details
        safe_details = _sanitize_details(details)
        if safe_details:
            response["details"] = safe_details

    if retry_after:
        response["retry_after"] = retry_after

    return response


def _sanitize_details(details: Dict[str, Any]) -> Dict[str, Any]:
    """
    Entfernt sensible Daten aus Details für Logging/Response.

    GDPR-konform: Keine PII in Fehlerresponses.
    """
    sensitive_keys = {
        "password", "token", "secret", "key", "auth",
        "credential", "api_key", "access_token", "refresh_token",
        "ssn", "iban", "tax_id", "email", "phone",
    }

    safe = {}
    for key, value in details.items():
        key_lower = key.lower()
        if any(sensitive in key_lower for sensitive in sensitive_keys):
            safe[key] = "[REDACTED]"
        elif isinstance(value, dict):
            safe[key] = _sanitize_details(value)
        elif isinstance(value, str) and len(value) > 200:
            # Truncate long strings
            safe[key] = value[:200] + "..."
        else:
            safe[key] = value

    return safe


async def ablage_system_exception_handler(
    request: Request,
    exc: AblageSystemException,
) -> JSONResponse:
    """
    Handler für alle AblageSystemException und Unterklassen.

    Nutzt user_message_de für benutzerfreundliche deutsche Meldungen.
    """
    status_code = EXCEPTION_STATUS_CODES.get(type(exc), 500)

    # Log mit strukturierten Daten (ohne sensible Informationen)
    logger.error(
        "ablage_system_error",
        error_code=exc.error_code,
        error_type=type(exc).__name__,
        path=request.url.path,
        method=request.method,
        client_ip=request.client.host if request.client else None,
        # Keine exc.message - könnte PII enthalten
    )

    # Track error for analytics
    _track_exception(exc, request, status_code)

    response = create_error_response(
        fehler=_get_error_category(exc),
        nachricht=exc.user_message_de,
        status_code=status_code,
        fehler_code=exc.error_code,
        details=exc.details if _should_include_details() else None,
        pfad=request.url.path,
    )

    headers = {}
    if status_code == 503:
        headers["Retry-After"] = "60"

    return JSONResponse(
        status_code=status_code,
        content=response,
        headers=headers,
    )


async def file_validation_error_handler(
    request: Request,
    exc: FileValidationError,
) -> JSONResponse:
    """Handler für Datei-Validierungsfehler."""
    status_code = EXCEPTION_STATUS_CODES.get(type(exc), 400)

    logger.warning(
        "file_validation_error",
        error_type=type(exc).__name__,
        path=request.url.path,
    )

    return JSONResponse(
        status_code=status_code,
        content=create_error_response(
            fehler="Validierungsfehler",
            nachricht=exc.user_message_de,
            status_code=status_code,
            pfad=request.url.path,
        ),
    )


async def totp_error_handler(
    request: Request,
    exc: TOTPError,
) -> JSONResponse:
    """Handler für TOTP/2FA-Fehler."""
    status_code = EXCEPTION_STATUS_CODES.get(type(exc), 400)

    # Spezifische Meldungen für TOTP-Fehler
    messages = {
        TOTPNotAvailableError: "Zwei-Faktor-Authentifizierung ist nicht verfügbar",
        TOTPInvalidCodeError: "Ungültiger Authentifizierungscode",
        TOTPAlreadyEnabledError: "Zwei-Faktor-Authentifizierung ist bereits aktiviert",
        TOTPNotEnabledError: "Zwei-Faktor-Authentifizierung ist nicht aktiviert",
        TOTPSecretEncryptionError: "Interner Fehler bei der Authentifizierung",
    }

    nachricht = messages.get(type(exc), str(exc))

    logger.warning(
        "totp_error",
        error_type=type(exc).__name__,
        path=request.url.path,
    )

    return JSONResponse(
        status_code=status_code,
        content=create_error_response(
            fehler="Authentifizierungsfehler",
            nachricht=nachricht,
            status_code=status_code,
            pfad=request.url.path,
        ),
    )


async def session_error_handler(
    request: Request,
    exc: SessionError,
) -> JSONResponse:
    """Handler für Session-Fehler."""
    status_code = EXCEPTION_STATUS_CODES.get(type(exc), 503)

    if isinstance(exc, SessionLimitReachedError):
        nachricht = "Maximale Anzahl aktiver Sitzungen erreicht. Bitte melden Sie sich von anderen Geräten ab."
    else:
        nachricht = "Sitzungsfehler aufgetreten. Bitte erneut anmelden."

    logger.warning(
        "session_error",
        error_type=type(exc).__name__,
        path=request.url.path,
    )

    return JSONResponse(
        status_code=status_code,
        content=create_error_response(
            fehler="Sitzungsfehler",
            nachricht=nachricht,
            status_code=status_code,
            pfad=request.url.path,
        ),
    )


async def api_key_error_handler(
    request: Request,
    exc: APIKeyError,
) -> JSONResponse:
    """Handler für API-Key-Fehler."""
    status_code = EXCEPTION_STATUS_CODES.get(type(exc), 403)

    messages = {
        APIKeyLimitError: "API-Key-Limit erreicht. Bitte später erneut versuchen.",
        APIKeyNotFoundError: "API-Key nicht gefunden oder ungültig.",
    }

    nachricht = messages.get(type(exc), "API-Key-Fehler")

    logger.warning(
        "api_key_error",
        error_type=type(exc).__name__,
        path=request.url.path,
    )

    return JSONResponse(
        status_code=status_code,
        content=create_error_response(
            fehler="API-Key-Fehler",
            nachricht=nachricht,
            status_code=status_code,
            pfad=request.url.path,
        ),
    )


async def csrf_error_handler(
    request: Request,
    exc: CSRFError,
) -> JSONResponse:
    """Handler für CSRF-Fehler."""
    logger.warning(
        "csrf_error",
        path=request.url.path,
        client_ip=request.client.host if request.client else None,
    )

    return JSONResponse(
        status_code=400,
        content=create_error_response(
            fehler="CSRF-Fehler",
            nachricht="Ungültiger oder fehlender CSRF-Token. Bitte Seite neu laden.",
            status_code=400,
            pfad=request.url.path,
        ),
    )


async def circuit_breaker_error_handler(
    request: Request,
    exc: CircuitOpenError,
) -> JSONResponse:
    """Handler für Circuit-Breaker-Fehler."""
    logger.warning(
        "circuit_breaker_open",
        path=request.url.path,
    )

    return JSONResponse(
        status_code=503,
        content=create_error_response(
            fehler="Service vorübergehend nicht verfügbar",
            nachricht="Der angeforderte Dienst ist vorübergehend überlastet. Bitte in 60 Sekunden erneut versuchen.",
            status_code=503,
            pfad=request.url.path,
            retry_after=60,
        ),
        headers={"Retry-After": "60"},
    )


async def encryption_error_handler(
    request: Request,
    exc: EncryptionError,
) -> JSONResponse:
    """Handler für Verschlüsselungsfehler."""
    logger.error(
        "encryption_error",
        error_type=type(exc).__name__,
        path=request.url.path,
    )

    if isinstance(exc, KeyNotConfiguredError):
        nachricht = "Verschlüsselungskonfiguration nicht verfügbar"
    elif isinstance(exc, DecryptionError):
        nachricht = "Daten konnten nicht entschlüsselt werden"
    else:
        nachricht = "Verschlüsselungsfehler aufgetreten"

    return JSONResponse(
        status_code=500,
        content=create_error_response(
            fehler="Verschlüsselungsfehler",
            nachricht=nachricht,
            status_code=500,
            pfad=request.url.path,
        ),
    )


async def http_exception_handler(
    request: Request,
    exc: HTTPException,
) -> JSONResponse:
    """
    Handler für FastAPI HTTPExceptions.

    Überschreibt den Standard-Handler für konsistentes deutsches Format.
    """
    # Übersetze häufige HTTP-Fehler
    error_translations = {
        400: ("Ungültige Anfrage", "Die Anfrage konnte nicht verarbeitet werden"),
        401: ("Nicht autorisiert", "Bitte melden Sie sich an"),
        403: ("Zugriff verweigert", "Sie haben keine Berechtigung für diese Aktion"),
        404: ("Nicht gefunden", "Die angeforderte Ressource wurde nicht gefunden"),
        405: ("Methode nicht erlaubt", "Diese HTTP-Methode ist nicht erlaubt"),
        409: ("Konflikt", "Die Anfrage steht in Konflikt mit dem aktuellen Zustand"),
        413: ("Anfrage zu groß", "Die hochgeladene Datei ist zu groß"),
        422: ("Validierungsfehler", "Die Eingabedaten sind ungültig"),
        429: ("Zu viele Anfragen", "Bitte warten Sie einen Moment und versuchen Sie es erneut"),
        500: ("Interner Serverfehler", "Ein unerwarteter Fehler ist aufgetreten"),
        502: ("Bad Gateway", "Der Backend-Service ist nicht erreichbar"),
        503: ("Service nicht verfügbar", "Der Service ist vorübergehend nicht verfügbar"),
    }

    fehler, default_nachricht = error_translations.get(
        exc.status_code,
        ("Fehler", "Ein Fehler ist aufgetreten")
    )

    # Verwende exc.detail wenn vorhanden, sonst Standard
    nachricht = exc.detail if exc.detail else default_nachricht

    # Log nur bei Server-Fehlern (5xx)
    if exc.status_code >= 500:
        logger.error(
            "http_exception",
            status_code=exc.status_code,
            path=request.url.path,
            detail=nachricht if len(str(nachricht)) < 200 else str(nachricht)[:200],
        )

    # Track error for analytics (nur bei Fehlern >= 400)
    if exc.status_code >= 400:
        _track_exception(exc, request, exc.status_code)

    headers = dict(exc.headers) if exc.headers else {}
    if exc.status_code == 503:
        headers.setdefault("Retry-After", "60")

    return JSONResponse(
        status_code=exc.status_code,
        content=create_error_response(
            fehler=fehler,
            nachricht=nachricht,
            status_code=exc.status_code,
            pfad=request.url.path,
        ),
        headers=headers,
    )


async def validation_exception_handler(
    request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    """
    Handler für Pydantic-Validierungsfehler.

    Übersetzt Validierungsfehler in benutzerfreundliches Deutsch.
    """
    # Sammle Validierungsfehler
    errors = []
    for error in exc.errors():
        loc = " -> ".join(str(l) for l in error.get("loc", []))
        msg = _translate_validation_error(error.get("type", ""), error.get("msg", ""))
        errors.append(f"{loc}: {msg}")

    nachricht = "Validierungsfehler: " + "; ".join(errors[:5])  # Max 5 Fehler anzeigen
    if len(errors) > 5:
        nachricht += f" (und {len(errors) - 5} weitere)"

    logger.warning(
        "validation_error",
        path=request.url.path,
        error_count=len(errors),
    )

    # Track error for analytics
    _track_exception(exc, request, 422, ErrorCategory.VALIDATION)

    return JSONResponse(
        status_code=422,
        content=create_error_response(
            fehler="Validierungsfehler",
            nachricht=nachricht,
            status_code=422,
            pfad=request.url.path,
            details={"fehler": errors} if _should_include_details() else None,
        ),
    )


async def generic_exception_handler(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    """
    Fallback-Handler für alle nicht behandelten Exceptions.

    WICHTIG: Gibt keine internen Details preis (Sicherheit).
    """
    logger.exception(
        "unhandled_exception",
        error_type=type(exc).__name__,
        path=request.url.path,
        method=request.method,
    )

    # Track critical error for analytics
    _track_exception(exc, request, 500, ErrorCategory.SYSTEM)

    return JSONResponse(
        status_code=500,
        content=create_error_response(
            fehler="Interner Serverfehler",
            nachricht="Ein unerwarteter Fehler ist aufgetreten. Bitte versuchen Sie es später erneut.",
            status_code=500,
            pfad=request.url.path,
        ),
    )


def _get_error_category(exc: AblageSystemException) -> str:
    """Bestimmt die Fehlerkategorie basierend auf Exception-Typ."""
    if isinstance(exc, GPUException):
        return "GPU-Fehler"
    elif isinstance(exc, OCRException):
        return "OCR-Fehler"
    elif isinstance(exc, DocumentException):
        return "Dokumentfehler"
    elif isinstance(exc, DatabaseException):
        return "Datenbankfehler"
    elif isinstance(exc, ComplianceException):
        return "Compliance-Fehler"
    elif isinstance(exc, GermanTextException):
        return "Textverarbeitungsfehler"
    else:
        return "Systemfehler"


def _get_tracking_category(exc: Exception) -> ErrorCategory:
    """Bestimmt die Error-Tracking-Kategorie basierend auf Exception-Typ."""
    if isinstance(exc, GPUException):
        return ErrorCategory.GPU
    elif isinstance(exc, OCRException):
        return ErrorCategory.OCR
    elif isinstance(exc, DatabaseException):
        return ErrorCategory.DATABASE
    elif isinstance(exc, ComplianceException):
        return ErrorCategory.COMPLIANCE
    elif isinstance(exc, (TOTPError, SessionError, APIKeyError)):
        return ErrorCategory.AUTH
    elif isinstance(exc, (FileValidationError, DocumentException)):
        return ErrorCategory.FILE
    elif isinstance(exc, CSRFError):
        return ErrorCategory.AUTH
    elif isinstance(exc, RequestValidationError):
        return ErrorCategory.VALIDATION
    else:
        return ErrorCategory.SYSTEM


def _get_tracking_severity(status_code: int) -> ErrorSeverity:
    """Bestimmt den Schweregrad basierend auf HTTP-Status-Code."""
    if status_code < 400:
        return ErrorSeverity.DEBUG
    elif status_code < 500:
        return ErrorSeverity.WARNING
    elif status_code < 503:
        return ErrorSeverity.ERROR
    else:
        return ErrorSeverity.CRITICAL


def _track_exception(
    exc: Exception,
    request: Request,
    status_code: int,
    category: Optional[ErrorCategory] = None,
) -> None:
    """Zentrale Funktion zum Tracking von Exceptions."""
    try:
        service = get_error_tracking_service()

        # Kategorie bestimmen
        if category is None:
            category = _get_tracking_category(exc)

        # Severity basierend auf Status-Code
        severity = _get_tracking_severity(status_code)

        # Error tracken
        service.track_error(
            category=category,
            error_type=type(exc).__name__,
            severity=severity,
            message=str(exc)[:500],  # Truncate
            path=request.url.path,
            request_id=getattr(request.state, "request_id", None),
            details={
                "method": request.method,
                "status_code": status_code,
            }
        )
    except Exception as e:
        # Error tracking darf nicht den Request-Flow stoeren
        logger.debug("error_tracking_failed", error=str(e))


def _translate_validation_error(error_type: str, msg: str) -> str:
    """Übersetzt Pydantic-Validierungsfehler ins Deutsche."""
    translations = {
        "missing": "Pflichtfeld fehlt",
        "string_type": "Muss ein Text sein",
        "int_type": "Muss eine Ganzzahl sein",
        "float_type": "Muss eine Zahl sein",
        "bool_type": "Muss ein Wahrheitswert sein",
        "value_error": "Ungültiger Wert",
        "type_error": "Falscher Datentyp",
        "string_too_short": "Text zu kurz",
        "string_too_long": "Text zu lang",
        "greater_than": "Wert zu klein",
        "less_than": "Wert zu groß",
        "json_invalid": "Ungültiges JSON",
        "url_parsing": "Ungültige URL",
        "email": "Ungültige E-Mail-Adresse",
        "uuid_parsing": "Ungültige UUID",
    }

    for key, translation in translations.items():
        if key in error_type.lower():
            return translation

    return msg


def _should_include_details() -> bool:
    """Prüft ob Details in der Response enthalten sein sollen (nur DEBUG)."""
    from app.core.config import settings
    return settings.DEBUG


def register_exception_handlers(app) -> None:
    """
    Registriert alle Exception-Handler bei der FastAPI-App.

    Sollte nach der App-Erstellung aufgerufen werden.

    Args:
        app: FastAPI-Anwendung
    """
    from fastapi import FastAPI
    from fastapi.exceptions import RequestValidationError
    from starlette.exceptions import HTTPException as StarletteHTTPException

    # AblageSystemException und alle Unterklassen
    app.add_exception_handler(AblageSystemException, ablage_system_exception_handler)

    # Spezifische Handler für Exceptions außerhalb der Hierarchie
    app.add_exception_handler(FileValidationError, file_validation_error_handler)
    app.add_exception_handler(TOTPError, totp_error_handler)
    app.add_exception_handler(SessionError, session_error_handler)
    app.add_exception_handler(APIKeyError, api_key_error_handler)
    app.add_exception_handler(CSRFError, csrf_error_handler)
    app.add_exception_handler(CircuitOpenError, circuit_breaker_error_handler)
    app.add_exception_handler(EncryptionError, encryption_error_handler)

    # Standard FastAPI/Starlette Exceptions
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)

    # Fallback für alle anderen Exceptions
    app.add_exception_handler(Exception, generic_exception_handler)

    logger.info("exception_handlers_registered")
