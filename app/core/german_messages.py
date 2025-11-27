# -*- coding: utf-8 -*-
"""
German Language Messages for Ablage-System.

All user-facing messages MUST be in German per project requirements.
This module centralizes all German text for consistency and maintainability.

CRITICAL: 100% German compliance required for production.
"""

from typing import Dict


# =============================================================================
# HTTP ERROR MESSAGES (for HTTPException details)
# =============================================================================

class HTTPErrors:
    """German HTTP error messages."""

    # 400 Bad Request
    INVALID_FILE_TYPE = "Ungültiger Dateityp. Erlaubt: {allowed}"
    INVALID_REQUEST = "Ungültige Anfrage"
    MISSING_REQUIRED_FIELD = "Pflichtfeld fehlt: {field}"
    INVALID_FORMAT = "Ungültiges Format: {details}"

    # 401 Unauthorized
    INVALID_CREDENTIALS = "Ungültige Anmeldedaten"
    TOKEN_EXPIRED = "Sitzung abgelaufen. Bitte erneut anmelden"
    TOKEN_INVALID = "Ungültiger Authentifizierungstoken"
    NOT_AUTHENTICATED = "Authentifizierung erforderlich"

    # 403 Forbidden
    PERMISSION_DENIED = "Zugriff verweigert"
    INSUFFICIENT_PERMISSIONS = "Unzureichende Berechtigungen"
    ACCOUNT_DISABLED = "Konto deaktiviert"

    # 404 Not Found
    DOCUMENT_NOT_FOUND = "Dokument nicht gefunden"
    USER_NOT_FOUND = "Benutzer nicht gefunden"
    TASK_NOT_FOUND = "Aufgabe nicht gefunden"
    AGENT_NOT_FOUND = "Agent nicht gefunden: {agent_id}"
    RESOURCE_NOT_FOUND = "Ressource nicht gefunden"

    # 409 Conflict
    EMAIL_EXISTS = "E-Mail-Adresse bereits registriert"
    USERNAME_EXISTS = "Benutzername bereits vergeben"
    RESOURCE_CONFLICT = "Ressourcenkonflikt"

    # 413 Payload Too Large
    FILE_TOO_LARGE = "Datei zu groß: {size_mb:.1f}MB (max: {max_mb:.1f}MB)"

    # 415 Unsupported Media Type
    UNSUPPORTED_FILE_TYPE = "Dateityp nicht unterstützt: {file_type}"

    # 422 Unprocessable Entity
    VALIDATION_ERROR = "Validierungsfehler: {details}"
    INVALID_PASSWORD = "Passwort entspricht nicht den Anforderungen"

    # 429 Too Many Requests
    RATE_LIMIT_EXCEEDED = "Zu viele Anfragen. Bitte warten Sie {retry_after} Sekunden"

    # 500 Internal Server Error
    INTERNAL_ERROR = "Interner Serverfehler"
    PROCESSING_FAILED = "Verarbeitung fehlgeschlagen: {details}"

    # 502 Bad Gateway
    BACKEND_ERROR = "Backend-Dienst nicht erreichbar"

    # 503 Service Unavailable
    SERVICE_UNAVAILABLE = "Dienst vorübergehend nicht verfügbar"
    GPU_NOT_AVAILABLE = "GPU nicht verfügbar"
    OCR_SERVICE_NOT_INITIALIZED = "OCR-Dienst nicht initialisiert"
    GPU_MANAGER_NOT_INITIALIZED = "GPU-Manager nicht initialisiert"
    GERMAN_VALIDATOR_NOT_INITIALIZED = "Deutscher Validator nicht initialisiert"
    DATABASE_UNAVAILABLE = "Datenbankverbindung fehlgeschlagen"

    # 504 Gateway Timeout
    PROCESSING_TIMEOUT = "Zeitüberschreitung bei der Verarbeitung"


# =============================================================================
# SUCCESS MESSAGES
# =============================================================================

class SuccessMessages:
    """German success messages."""

    # Document operations
    DOCUMENT_UPLOADED = "Dokument erfolgreich hochgeladen"
    DOCUMENT_PROCESSED = "Dokument erfolgreich verarbeitet"
    DOCUMENT_DELETED = "Dokument erfolgreich gelöscht"

    # User operations
    USER_CREATED = "Benutzer erfolgreich erstellt"
    USER_UPDATED = "Benutzer erfolgreich aktualisiert"
    PASSWORD_CHANGED = "Passwort erfolgreich geändert"
    LOGGED_OUT = "Erfolgreich abgemeldet"

    # Task operations
    TASK_STARTED = "Aufgabe gestartet"
    TASK_COMPLETED = "Aufgabe abgeschlossen"
    TASK_CANCELLED = "Aufgabe abgebrochen"

    # Batch operations
    BATCH_STARTED = "Stapelverarbeitung gestartet"
    BATCH_COMPLETED = "Stapelverarbeitung abgeschlossen"


# =============================================================================
# STATUS MESSAGES
# =============================================================================

class StatusMessages:
    """German status messages for progress updates."""

    # Processing states
    PENDING = "Ausstehend"
    QUEUED = "In Warteschlange"
    PROCESSING = "Verarbeitung läuft..."
    COMPLETED = "Abgeschlossen"
    FAILED = "Fehlgeschlagen"
    CANCELLED = "Abgebrochen"
    RETRYING = "Wiederholung..."

    # OCR stages
    UPLOADING = "Hochladen..."
    PREPROCESSING = "Vorverarbeitung..."
    OCR_RUNNING = "OCR-Erkennung läuft..."
    POSTPROCESSING = "Nachbearbeitung..."
    VALIDATING = "Validierung..."
    SAVING = "Speichern..."

    # System states
    HEALTHY = "Gesund"
    DEGRADED = "Eingeschränkt"
    UNHEALTHY = "Nicht verfügbar"
    OPERATIONAL = "Betriebsbereit"


# =============================================================================
# VALIDATION MESSAGES
# =============================================================================

class ValidationMessages:
    """German validation messages."""

    # Field validation
    FIELD_REQUIRED = "Dieses Feld ist erforderlich"
    FIELD_TOO_SHORT = "Eingabe zu kurz (min. {min} Zeichen)"
    FIELD_TOO_LONG = "Eingabe zu lang (max. {max} Zeichen)"
    INVALID_EMAIL = "Ungültige E-Mail-Adresse"
    INVALID_DATE = "Ungültiges Datumsformat (erwartet: TT.MM.JJJJ)"
    INVALID_AMOUNT = "Ungültiger Betrag"

    # Password validation
    PASSWORD_TOO_SHORT = "Passwort muss mindestens {min} Zeichen haben"
    PASSWORD_NEEDS_UPPERCASE = "Passwort muss Großbuchstaben enthalten"
    PASSWORD_NEEDS_LOWERCASE = "Passwort muss Kleinbuchstaben enthalten"
    PASSWORD_NEEDS_NUMBER = "Passwort muss Zahlen enthalten"
    PASSWORD_NEEDS_SPECIAL = "Passwort muss Sonderzeichen enthalten"
    PASSWORDS_DONT_MATCH = "Passwörter stimmen nicht überein"

    # Document validation
    INVALID_IBAN = "Ungültige IBAN"
    INVALID_VAT_ID = "Ungültige USt-IdNr."
    INVALID_TAX_NUMBER = "Ungültige Steuernummer"

    # German text validation
    UMLAUT_ERROR_DETECTED = "Möglicher Umlaut-Fehler erkannt: '{pattern}' sollte '{correct}' sein"
    ENCODING_ERROR = "Textcodierung fehlerhaft (Umlaute nicht korrekt)"


# =============================================================================
# OCR-SPECIFIC MESSAGES
# =============================================================================

class OCRMessages:
    """German OCR-related messages."""

    # Backend messages
    BACKEND_SELECTED = "Backend ausgewählt: {backend}"
    BACKEND_NOT_AVAILABLE = "Backend nicht verfügbar: {backend}"
    BACKEND_FALLBACK = "Wechsel zu Fallback-Backend: {backend}"

    # Processing messages
    PROCESSING_STARTED = "Dokumentverarbeitung gestartet"
    PROCESSING_PAGE = "Verarbeite Seite {current} von {total}"
    EXTRACTION_COMPLETE = "Textextraktion abgeschlossen"

    # Quality messages
    HIGH_CONFIDENCE = "Hohe Erkennungsqualität"
    MEDIUM_CONFIDENCE = "Mittlere Erkennungsqualität"
    LOW_CONFIDENCE = "Niedrige Erkennungsqualität - Überprüfung empfohlen"

    # German-specific
    GERMAN_TEXT_DETECTED = "Deutscher Text erkannt"
    UMLAUTS_PRESERVED = "Umlaute korrekt erkannt"
    FRAKTUR_DETECTED = "Frakturschrift erkannt"


# =============================================================================
# SYSTEM MESSAGES
# =============================================================================

class SystemMessages:
    """German system messages."""

    # Startup/Shutdown
    STARTING = "System wird gestartet..."
    STARTED = "System erfolgreich gestartet"
    SHUTTING_DOWN = "System wird heruntergefahren..."
    SHUTDOWN_COMPLETE = "System heruntergefahren"

    # GPU messages
    GPU_DETECTED = "GPU erkannt: {gpu_name}"
    GPU_NOT_DETECTED = "Keine GPU erkannt - CPU-Modus aktiv"
    GPU_MEMORY_LOW = "GPU-Speicher niedrig: {available_gb:.1f}GB frei"
    GPU_MEMORY_CLEARED = "GPU-Speicher freigegeben"

    # Maintenance
    CLEANUP_STARTED = "Bereinigung gestartet"
    CLEANUP_COMPLETE = "Bereinigung abgeschlossen: {count} Elemente entfernt"


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def get_error_message(error_key: str, **kwargs) -> str:
    """
    Get German error message with optional formatting.

    Args:
        error_key: Key from HTTPErrors class
        **kwargs: Format arguments

    Returns:
        Formatted German error message
    """
    message = getattr(HTTPErrors, error_key, HTTPErrors.INTERNAL_ERROR)
    if kwargs:
        try:
            return message.format(**kwargs)
        except KeyError:
            return message
    return message


def get_status_message(status: str) -> str:
    """
    Get German status message.

    Args:
        status: Status key (e.g., 'pending', 'processing')

    Returns:
        German status message
    """
    status_map = {
        "pending": StatusMessages.PENDING,
        "queued": StatusMessages.QUEUED,
        "processing": StatusMessages.PROCESSING,
        "completed": StatusMessages.COMPLETED,
        "failed": StatusMessages.FAILED,
        "cancelled": StatusMessages.CANCELLED,
        "retrying": StatusMessages.RETRYING,
    }
    return status_map.get(status.lower(), status)
