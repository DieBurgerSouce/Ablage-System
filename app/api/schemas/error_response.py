"""Standardisiertes Fehler-Response-Schema fuer die API.

Alle API-Fehlerantworten folgen diesem einheitlichen Format mit:
- Fehlercode (ERR-DOC-001 bis ERR-API-999)
- Deutsche Benutzer-Nachricht
- Englische technische Nachricht
- Korrelations-ID fuer Tracing
- Zeitstempel

Feinpoliert und durchdacht.
"""

from typing import Dict, Optional

from pydantic import BaseModel, ConfigDict, Field


class StandardErrorResponse(BaseModel):
    """Einheitliches Fehler-Response-Format fuer alle API-Endpunkte."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "error_code": "ERR-DOC-001",
                "message": "Document not found",
                "message_de": "Dokument nicht gefunden",
                "correlation_id": "550e8400-e29b-41d4-a716-446655440000",
                "details": {},
                "timestamp": "2026-02-17T12:00:00+00:00",
                "path": "/api/v1/documents/123",
            }
        }
    )

    error_code: str = Field(
        ...,
        description="Standardisierter Fehlercode (z.B. ERR-DOC-001)",
        examples=["ERR-DOC-001"],
    )
    message: str = Field(
        ...,
        description="Technische Fehlerbeschreibung (Englisch)",
        examples=["Document not found"],
    )
    message_de: str = Field(
        ...,
        description="Benutzerfreundliche Fehlerbeschreibung (Deutsch)",
        examples=["Dokument nicht gefunden"],
    )
    correlation_id: str = Field(
        ...,
        description="Eindeutige Korrelations-ID fuer Request-Tracing",
        examples=["550e8400-e29b-41d4-a716-446655440000"],
    )
    details: Optional[Dict[str, str]] = Field(
        default=None,
        description="Zusaetzliche technische Details",
    )
    timestamp: str = Field(
        ...,
        description="ISO 8601 Zeitstempel",
        examples=["2026-02-17T12:00:00+00:00"],
    )
    path: Optional[str] = Field(
        default=None,
        description="Request-Pfad",
        examples=["/api/v1/documents/123"],
    )
