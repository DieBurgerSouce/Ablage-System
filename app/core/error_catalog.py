"""Fehlercode-Katalog fuer standardisierte API-Fehler.

Kodierung: ERR-{DOMAIN}-{NUMBER}
- ERR-DOC-001 bis ERR-DOC-099: Dokument-Fehler
- ERR-OCR-001 bis ERR-OCR-099: OCR-Fehler
- ERR-AUTH-001 bis ERR-AUTH-099: Authentifizierung
- ERR-API-001 bis ERR-API-099: Allgemeine API-Fehler
- ERR-PAY-001 bis ERR-PAY-099: Zahlungs-Fehler
- ERR-IMP-001 bis ERR-IMP-099: Import-Fehler
- ERR-VAL-001 bis ERR-VAL-099: Validierungs-Fehler
- ERR-GPU-001 bis ERR-GPU-099: GPU-Fehler
- ERR-DB-001 bis ERR-DB-099: Datenbank-Fehler
- ERR-SYS-001 bis ERR-SYS-099: System-Fehler

Feinpoliert und durchdacht.
"""

from dataclasses import dataclass
from typing import Dict, Optional


@dataclass(frozen=True)
class ErrorDefinition:
    """Definition eines standardisierten Fehlercodes."""

    code: str
    message_de: str
    message_en: str
    http_status: int


# Document Errors
ERR_DOC_001 = ErrorDefinition("ERR-DOC-001", "Dokument nicht gefunden", "Document not found", 404)
ERR_DOC_002 = ErrorDefinition("ERR-DOC-002", "Ungueltiges Dateiformat", "Invalid document format", 400)
ERR_DOC_003 = ErrorDefinition("ERR-DOC-003", "Datei zu gross", "File size exceeded", 413)
ERR_DOC_004 = ErrorDefinition("ERR-DOC-004", "Dokument-Verarbeitung fehlgeschlagen", "Document processing failed", 500)
ERR_DOC_005 = ErrorDefinition(
    "ERR-DOC-005",
    "Dokument ist archiviert und kann nicht geaendert werden",
    "Document is archived and immutable",
    409,
)
ERR_DOC_006 = ErrorDefinition("ERR-DOC-006", "Duplikat erkannt", "Duplicate detected", 409)
ERR_DOC_007 = ErrorDefinition("ERR-DOC-007", "Dokument-Export fehlgeschlagen", "Document export failed", 500)

# OCR Errors
ERR_OCR_001 = ErrorDefinition("ERR-OCR-001", "OCR-Verarbeitung fehlgeschlagen", "OCR processing failed", 500)
ERR_OCR_002 = ErrorDefinition("ERR-OCR-002", "OCR-Backend nicht verfuegbar", "OCR backend unavailable", 503)
ERR_OCR_003 = ErrorDefinition("ERR-OCR-003", "OCR-Timeout ueberschritten", "OCR processing timeout", 504)
ERR_OCR_004 = ErrorDefinition("ERR-OCR-004", "Textcodierung fehlerhaft", "Invalid text encoding", 422)

# Auth Errors
ERR_AUTH_001 = ErrorDefinition("ERR-AUTH-001", "Authentifizierung fehlgeschlagen", "Authentication failed", 401)
ERR_AUTH_002 = ErrorDefinition("ERR-AUTH-002", "Zugriff verweigert", "Access forbidden", 403)
ERR_AUTH_003 = ErrorDefinition("ERR-AUTH-003", "Sitzung abgelaufen", "Session expired", 401)
ERR_AUTH_004 = ErrorDefinition("ERR-AUTH-004", "Fehlende Berechtigung", "Insufficient permissions", 403)
ERR_AUTH_005 = ErrorDefinition("ERR-AUTH-005", "Ratenlimit erreicht", "Rate limit exceeded", 429)

# API Errors
ERR_API_001 = ErrorDefinition("ERR-API-001", "Ungueltiger Request", "Invalid request", 400)
ERR_API_002 = ErrorDefinition("ERR-API-002", "Interner Serverfehler", "Internal server error", 500)
ERR_API_003 = ErrorDefinition("ERR-API-003", "Service nicht verfuegbar", "Service unavailable", 503)
ERR_API_004 = ErrorDefinition("ERR-API-004", "Request-Timeout", "Request timeout", 504)
ERR_API_005 = ErrorDefinition("ERR-API-005", "Methode nicht erlaubt", "Method not allowed", 405)

# Payment Errors
ERR_PAY_001 = ErrorDefinition("ERR-PAY-001", "Zahlung fehlgeschlagen", "Payment failed", 402)
ERR_PAY_002 = ErrorDefinition("ERR-PAY-002", "SEPA-Ueberweisung ungueltig", "Invalid SEPA transfer", 400)
ERR_PAY_003 = ErrorDefinition("ERR-PAY-003", "Bankverbindung nicht gefunden", "Bank connection not found", 404)

# Import Errors
ERR_IMP_001 = ErrorDefinition("ERR-IMP-001", "Import fehlgeschlagen", "Import failed", 500)
ERR_IMP_002 = ErrorDefinition(
    "ERR-IMP-002", "Import-Konfiguration nicht gefunden", "Import config not found", 404
)
ERR_IMP_003 = ErrorDefinition("ERR-IMP-003", "Ordnerpfad nicht erreichbar", "Folder path not accessible", 400)
ERR_IMP_004 = ErrorDefinition("ERR-IMP-004", "Ungueltige Import-Regel", "Invalid import rule", 400)

# Validation Errors
ERR_VAL_001 = ErrorDefinition("ERR-VAL-001", "Validierungsfehler", "Validation error", 422)
ERR_VAL_002 = ErrorDefinition("ERR-VAL-002", "Pflichtfeld fehlt", "Required field missing", 422)
ERR_VAL_003 = ErrorDefinition("ERR-VAL-003", "Ungueltiger Datentyp", "Invalid data type", 422)

# GPU Errors
ERR_GPU_001 = ErrorDefinition("ERR-GPU-001", "GPU-Speicher nicht ausreichend", "GPU out of memory", 503)
ERR_GPU_002 = ErrorDefinition("ERR-GPU-002", "GPU nicht verfuegbar", "GPU not available", 503)

# Database Errors
ERR_DB_001 = ErrorDefinition("ERR-DB-001", "Datenbankverbindung fehlgeschlagen", "Database connection failed", 503)
ERR_DB_002 = ErrorDefinition("ERR-DB-002", "Datenbankabfrage fehlgeschlagen", "Database query failed", 500)

# System Errors
ERR_SYS_001 = ErrorDefinition("ERR-SYS-001", "Interner Systemfehler", "Internal system error", 500)
ERR_SYS_002 = ErrorDefinition("ERR-SYS-002", "Konfigurationsfehler", "Configuration error", 500)

# Finance Errors
ERR_FIN_001 = ErrorDefinition("ERR-FIN-001", "Rechnung nicht gefunden", "Invoice not found", 404)
ERR_FIN_002 = ErrorDefinition("ERR-FIN-002", "Zahlungszuordnung fehlgeschlagen", "Payment matching failed", 400)
ERR_FIN_003 = ErrorDefinition("ERR-FIN-003", "Skonto-Frist abgelaufen", "Discount deadline expired", 409)
ERR_FIN_004 = ErrorDefinition("ERR-FIN-004", "Offener Posten nicht gefunden", "Open item not found", 404)
ERR_FIN_005 = ErrorDefinition("ERR-FIN-005", "Finanzdaten nicht verfuegbar", "Financial data unavailable", 503)

# Integration Errors
ERR_INT_001 = ErrorDefinition("ERR-INT-001", "DATEV-Verbindung fehlgeschlagen", "DATEV connection failed", 502)
ERR_INT_002 = ErrorDefinition("ERR-INT-002", "Lexware-Import fehlgeschlagen", "Lexware import failed", 500)
ERR_INT_003 = ErrorDefinition("ERR-INT-003", "Slack-Benachrichtigung fehlgeschlagen", "Slack notification failed", 502)
ERR_INT_004 = ErrorDefinition("ERR-INT-004", "E-Mail-Verbindung fehlgeschlagen", "Email connection failed", 502)
ERR_INT_005 = ErrorDefinition("ERR-INT-005", "Externe API nicht erreichbar", "External API unreachable", 502)


# Registry: code -> ErrorDefinition
ERROR_CATALOG: Dict[str, ErrorDefinition] = {}


def _register_all() -> None:
    """Registriert alle ErrorDefinitions im Katalog."""
    import sys

    module = sys.modules[__name__]
    for name in dir(module):
        obj = getattr(module, name)
        if isinstance(obj, ErrorDefinition):
            ERROR_CATALOG[obj.code] = obj


_register_all()


def get_error_definition(code: str) -> Optional[ErrorDefinition]:
    """Gibt die ErrorDefinition fuer einen Fehlercode zurueck."""
    return ERROR_CATALOG.get(code)


# Mapping: Exception class name -> error code
EXCEPTION_TO_ERROR_CODE: Dict[str, str] = {
    "NotFoundError": "ERR-DOC-001",
    "DocumentNotFoundError": "ERR-DOC-001",
    "InvalidDocumentFormatError": "ERR-DOC-002",
    "FileSizeExceededError": "ERR-DOC-003",
    "OCRProcessingError": "ERR-OCR-001",
    "BackendSelectionError": "ERR-OCR-002",
    "OCRBackendTimeoutError": "ERR-OCR-003",
    "InferenceTimeoutError": "ERR-OCR-003",
    "InvalidGermanEncodingError": "ERR-OCR-004",
    "InvalidCredentialsError": "ERR-AUTH-001",
    "ForbiddenError": "ERR-AUTH-002",
    "TokenExpiredError": "ERR-AUTH-003",
    "InsufficientPermissionsError": "ERR-AUTH-004",
    "RateLimitError": "ERR-AUTH-005",
    "ValidationError": "ERR-VAL-001",
    "GPUOutOfMemoryError": "ERR-GPU-001",
    "GPUNotAvailableError": "ERR-GPU-002",
    "OCRGPUOutOfMemoryError": "ERR-GPU-001",
    "DatabaseConnectionError": "ERR-DB-001",
    "ImmutabilityViolationError": "ERR-DOC-005",
    "ExportError": "ERR-DOC-007",
    "StorageError": "ERR-SYS-001",
    "BusinessLogicError": "ERR-API-001",
    "InvoiceNotFoundError": "ERR-FIN-001",
    "PaymentMatchingError": "ERR-FIN-002",
    "SkontoExpiredError": "ERR-FIN-003",
    "DATEVConnectionError": "ERR-INT-001",
    "LexwareImportError": "ERR-INT-002",
    "SlackNotificationError": "ERR-INT-003",
}
