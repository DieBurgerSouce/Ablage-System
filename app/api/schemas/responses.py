"""
Standardisierte API Response Schemas für OpenAPI-Dokumentation.

Alle API-Antworten folgen diesen Schemas für konsistente Client-Integration.

Created: 2025-11-30
"""

from datetime import datetime
from typing import Optional, Dict, Any, List

from pydantic import BaseModel, Field


class ErrorResponse(BaseModel):
    """
    Standardisiertes Fehler-Response-Schema.

    Alle Fehlerantworten der API folgen diesem Format.

    Beispiel:
        {
            "fehler": "Nicht gefunden",
            "nachricht": "Das angeforderte Dokument wurde nicht gefunden",
            "status_code": 404,
            "fehler_code": "E007",
            "zeitstempel": "2025-01-01T12:00:00Z",
            "pfad": "/api/v1/documents/123"
        }
    """

    fehler: str = Field(
        ...,
        description="Kurze Fehlerbezeichnung",
        examples=["Validierungsfehler", "Nicht gefunden", "Nicht autorisiert"]
    )
    nachricht: str = Field(
        ...,
        description="Detaillierte, benutzerfreundliche Fehlerbeschreibung auf Deutsch",
        examples=["Das angeforderte Dokument wurde nicht gefunden"]
    )
    status_code: int = Field(
        ...,
        description="HTTP-Statuscode",
        ge=400,
        le=599,
        examples=[400, 401, 404, 500]
    )
    fehler_code: Optional[str] = Field(
        None,
        description="Interner Fehlercode für Debugging (E001-E099)",
        pattern=r"^E\d{3}$",
        examples=["E001", "E007", "E010"]
    )
    zeitstempel: str = Field(
        ...,
        description="ISO 8601 Zeitstempel (UTC)",
        examples=["2025-01-01T12:00:00+00:00"]
    )
    pfad: Optional[str] = Field(
        None,
        description="Request-Pfad, der den Fehler ausgelöst hat",
        examples=["/api/v1/documents/123"]
    )
    details: Optional[Dict[str, Any]] = Field(
        None,
        description="Zusätzliche technische Details (nur in DEBUG-Modus)"
    )
    retry_after: Optional[int] = Field(
        None,
        description="Sekunden bis zum nächsten Versuch (bei 429/503)",
        ge=1,
        examples=[60, 300]
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "fehler": "Validierungsfehler",
                    "nachricht": "Das Feld 'email' ist ungültig",
                    "status_code": 400,
                    "fehler_code": "E007",
                    "zeitstempel": "2025-01-01T12:00:00+00:00",
                    "pfad": "/api/v1/auth/register"
                },
                {
                    "fehler": "Nicht autorisiert",
                    "nachricht": "Bitte melden Sie sich an",
                    "status_code": 401,
                    "zeitstempel": "2025-01-01T12:00:00+00:00",
                    "pfad": "/api/v1/documents"
                },
                {
                    "fehler": "Service nicht verfügbar",
                    "nachricht": "Der Service ist vorübergehend nicht verfügbar. Bitte in 60 Sekunden erneut versuchen.",
                    "status_code": 503,
                    "zeitstempel": "2025-01-01T12:00:00+00:00",
                    "pfad": "/api/v1/ocr/process",
                    "retry_after": 60
                }
            ]
        }
    }


class ValidationErrorDetail(BaseModel):
    """Detail eines Validierungsfehlers."""

    loc: List[str] = Field(
        ...,
        description="Pfad zum fehlerhaften Feld",
        examples=[["body", "email"], ["query", "page"]]
    )
    msg: str = Field(
        ...,
        description="Fehlermeldung",
        examples=["Pflichtfeld fehlt"]
    )
    type: str = Field(
        ...,
        description="Fehlertyp",
        examples=["value_error.missing", "type_error.string"]
    )


class ValidationErrorResponse(ErrorResponse):
    """
    Response-Schema für Validierungsfehler (HTTP 422).

    Enthält detaillierte Informationen zu jedem ungültigen Feld.
    """

    fehler: str = Field(
        default="Validierungsfehler",
        description="Immer 'Validierungsfehler' für 422 Responses"
    )
    status_code: int = Field(
        default=422,
        description="Immer 422 für Validierungsfehler"
    )
    details: Optional[Dict[str, List[str]]] = Field(
        None,
        description="Liste der Validierungsfehler pro Feld"
    )


class SuccessResponse(BaseModel):
    """
    Basis-Schema für Erfolgsantworten.

    Kann erweitert werden für spezifische Endpoints.
    """

    status: str = Field(
        default="erfolg",
        description="Status der Operation",
        examples=["erfolg", "teilweise_erfolg"]
    )
    nachricht: str = Field(
        ...,
        description="Erfolgsmeldung auf Deutsch",
        examples=["Dokument erfolgreich hochgeladen"]
    )
    zeitstempel: Optional[str] = Field(
        None,
        description="ISO 8601 Zeitstempel (UTC)"
    )


class PaginatedResponse(BaseModel):
    """
    Basis-Schema für paginierte Listen.

    Beispiel:
        {
            "items": [...],
            "gesamt": 100,
            "seite": 1,
            "seiten_größe": 20,
            "seiten_gesamt": 5
        }
    """

    gesamt: int = Field(
        ...,
        description="Gesamtanzahl der Einträge",
        ge=0,
        examples=[100]
    )
    seite: int = Field(
        ...,
        description="Aktuelle Seitennummer (1-basiert)",
        ge=1,
        examples=[1]
    )
    seiten_größe: int = Field(
        ...,
        description="Anzahl der Einträge pro Seite",
        ge=1,
        le=100,
        examples=[20]
    )
    seiten_gesamt: int = Field(
        ...,
        description="Gesamtanzahl der Seiten",
        ge=0,
        examples=[5]
    )


class HealthResponse(BaseModel):
    """
    Schema für Health-Check-Responses.

    Beispiel:
        {
            "status": "healthy",
            "zeitstempel": "2025-01-01T12:00:00+00:00",
            "komponenten": {
                "datenbank": "ok",
                "redis": "ok",
                "gpu": "ok"
            }
        }
    """

    status: str = Field(
        ...,
        description="Gesamtstatus des Systems",
        examples=["healthy", "degraded", "unhealthy"]
    )
    zeitstempel: str = Field(
        ...,
        description="ISO 8601 Zeitstempel (UTC)"
    )
    komponenten: Dict[str, str] = Field(
        ...,
        description="Status einzelner Komponenten",
        examples=[{"datenbank": "ok", "redis": "ok", "gpu": "ok"}]
    )
    nachricht: Optional[str] = Field(
        None,
        description="Zusätzliche Statusnachricht"
    )


class OCRResultResponse(BaseModel):
    """
    Schema für OCR-Verarbeitungsergebnisse.

    Beispiel:
        {
            "erfolg": true,
            "text": "Extrahierter Text...",
            "backend": "deepseek",
            "verarbeitungszeit_ms": 1234,
            "seiten": 1,
            "sprache": "de"
        }
    """

    erfolg: bool = Field(
        ...,
        description="Ob die OCR-Verarbeitung erfolgreich war"
    )
    text: Optional[str] = Field(
        None,
        description="Extrahierter Text"
    )
    backend: str = Field(
        ...,
        description="Verwendetes OCR-Backend",
        examples=["deepseek", "got_ocr", "surya"]
    )
    verarbeitungszeit_ms: int = Field(
        ...,
        description="Verarbeitungszeit in Millisekunden",
        ge=0
    )
    seiten: int = Field(
        ...,
        description="Anzahl der verarbeiteten Seiten",
        ge=1
    )
    sprache: str = Field(
        ...,
        description="Erkannte Sprache",
        examples=["de", "en"]
    )
    konfidenz: Optional[float] = Field(
        None,
        description="Konfidenzwert der Extraktion (0-1)",
        ge=0,
        le=1
    )
    fehler: Optional[str] = Field(
        None,
        description="Fehlermeldung bei erfolg=false"
    )


# Common response examples for OpenAPI
COMMON_RESPONSES = {
    400: {
        "description": "Ungültige Anfrage - Die gesendeten Daten sind fehlerhaft",
        "model": ErrorResponse,
    },
    401: {
        "description": "Nicht autorisiert - Authentifizierung erforderlich",
        "model": ErrorResponse,
    },
    403: {
        "description": "Zugriff verweigert - Keine Berechtigung für diese Aktion",
        "model": ErrorResponse,
    },
    404: {
        "description": "Nicht gefunden - Die angeforderte Ressource existiert nicht",
        "model": ErrorResponse,
    },
    413: {
        "description": "Anfrage zu groß - Die hochgeladene Datei überschreitet das Limit",
        "model": ErrorResponse,
    },
    422: {
        "description": "Validierungsfehler - Die Eingabedaten sind ungültig",
        "model": ValidationErrorResponse,
    },
    429: {
        "description": "Zu viele Anfragen - Rate Limit überschritten",
        "model": ErrorResponse,
    },
    500: {
        "description": "Interner Serverfehler - Ein unerwarteter Fehler ist aufgetreten",
        "model": ErrorResponse,
    },
    503: {
        "description": "Service nicht verfügbar - Bitte später erneut versuchen",
        "model": ErrorResponse,
    },
}


# Error code reference
ERROR_CODES = {
    "E001": "GPU-Speicher nicht ausreichend",
    "E002": "GPU nicht verfügbar",
    "E003": "Ungültige Textcodierung (Umlaute)",
    "E004": "OCR-Backend Timeout",
    "E005": "Datenbankverbindung fehlgeschlagen",
    "E006": "Redis-Verbindung fehlgeschlagen",
    "E007": "Ungültiges Dokumentformat",
    "E008": "Dateigröße überschritten",
    "E009": "DSGVO-Verstoß erkannt",
    "E010": "Backend-Auswahl fehlgeschlagen",
    "E011": "DSGVO-Operation fehlgeschlagen",
    "E012": "Benutzer nicht gefunden",
    "E013": "Datenexport fehlgeschlagen",
    "E014": "E-Mail-Verifizierung fehlgeschlagen",
}
