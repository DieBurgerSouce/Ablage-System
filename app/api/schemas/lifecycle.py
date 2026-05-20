# -*- coding: utf-8 -*-
"""Pydantic Schemas fuer Document Lifecycle Engine API.

GoBD-konforme Schemas fuer:
- Lifecycle-Dashboard
- Ablaufende Dokumente
- Fristverlängerung
- Vernichtungsprotokolle
"""

from datetime import date, datetime
from typing import Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


# =============================================================================
# Dashboard Schemas
# =============================================================================


class LifecycleDashboardCounts(BaseModel):
    """Zaehler fuer das Lifecycle-Dashboard."""

    active: int = Field(description="Aktive, nicht archivierte Dokumente")
    archived: int = Field(description="Archivierte Dokumente insgesamt")
    expiring_30_days: int = Field(description="In 30 Tagen ablaufend")
    expiring_90_days: int = Field(description="In 90 Tagen ablaufend")
    expired: int = Field(description="Frist bereits abgelaufen")
    verification_failed: int = Field(description="Verifikation fehlgeschlagen")


class LifecycleDashboardResponse(BaseModel):
    """Antwort fuer das Lifecycle-Dashboard."""

    company_id: str = Field(description="Firmen-ID")
    generated_at: str = Field(description="Zeitpunkt der Generierung")
    counts: LifecycleDashboardCounts = Field(description="Zaehler-Uebersicht")
    by_category: Dict[str, int] = Field(
        default_factory=dict,
        description="Aufschluesselung nach Aufbewahrungskategorie"
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "company_id": "550e8400-e29b-41d4-a716-446655440000",
                "generated_at": "2026-02-16T10:30:00+00:00",
                "counts": {
                    "active": 1250,
                    "archived": 340,
                    "expiring_30_days": 12,
                    "expiring_90_days": 45,
                    "expired": 3,
                    "verification_failed": 0,
                },
                "by_category": {
                    "invoice": 150,
                    "contract": 80,
                    "correspondence": 110,
                },
            }
        }
    )


# =============================================================================
# Expiring Documents Schemas
# =============================================================================


class ExpiringDocumentResponse(BaseModel):
    """Antwort fuer ein ablaufendes Dokument."""

    archive_id: str = Field(description="Archiv-ID")
    document_id: str = Field(description="Dokument-ID")
    filename: Optional[str] = Field(None, description="Dateiname")
    retention_category: str = Field(description="Aufbewahrungskategorie")
    retention_years: int = Field(description="Aufbewahrungsfrist in Jahren")
    retention_expires_at: date = Field(description="Ablaufdatum")
    days_until_expiry: int = Field(description="Tage bis zum Ablauf")
    is_verified: bool = Field(description="Integritaet verifiziert")
    archived_at: Optional[str] = Field(None, description="Archivierungszeitpunkt")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "archive_id": "660e8400-e29b-41d4-a716-446655440001",
                "document_id": "770e8400-e29b-41d4-a716-446655440002",
                "filename": "Rechnung_2020_001.pdf",
                "retention_category": "invoice",
                "retention_years": 10,
                "retention_expires_at": "2030-06-15",
                "days_until_expiry": 25,
                "is_verified": True,
                "archived_at": "2020-06-15T14:30:00+00:00",
            }
        }
    )


# =============================================================================
# Retention Extension Schemas
# =============================================================================


class RetentionExtensionRequest(BaseModel):
    """Anfrage fuer eine Fristverlaengerung."""

    new_years: int = Field(
        ...,
        ge=1,
        le=30,
        description="Neue Aufbewahrungsdauer in Jahren (ab heute)"
    )
    reason: str = Field(
        ...,
        min_length=5,
        max_length=500,
        description="Begruendung der Verlaengerung"
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "new_years": 15,
                "reason": "Laufende Betriebspruefung durch das Finanzamt",
            }
        }
    )


class RetentionExtensionResponse(BaseModel):
    """Antwort nach erfolgreicher Fristverlaengerung."""

    archive_id: str = Field(description="Archiv-ID")
    document_id: str = Field(description="Dokument-ID")
    old_years: int = Field(description="Bisherige Aufbewahrungsdauer")
    new_years: int = Field(description="Neue Aufbewahrungsdauer")
    old_expires_at: date = Field(description="Bisheriges Ablaufdatum")
    new_expires_at: date = Field(description="Neues Ablaufdatum")
    reason: str = Field(description="Begruendung")
    extended_at: str = Field(description="Zeitpunkt der Verlaengerung")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "archive_id": "660e8400-e29b-41d4-a716-446655440001",
                "document_id": "770e8400-e29b-41d4-a716-446655440002",
                "old_years": 10,
                "new_years": 15,
                "old_expires_at": "2030-06-15",
                "new_expires_at": "2041-02-16",
                "reason": "Laufende Betriebspruefung",
                "extended_at": "2026-02-16T10:30:00+00:00",
            }
        }
    )


# =============================================================================
# Destruction Protocol Schemas
# =============================================================================


class DestructionProtocolRequest(BaseModel):
    """Anfrage fuer ein Vernichtungsprotokoll."""

    document_ids: List[UUID] = Field(
        ...,
        min_length=1,
        description="IDs der zu vernichtenden Dokumente"
    )
    reason: str = Field(
        default="Aufbewahrungsfrist abgelaufen",
        min_length=5,
        max_length=500,
        description="Begruendung der Vernichtung"
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "document_ids": [
                    "770e8400-e29b-41d4-a716-446655440002",
                    "880e8400-e29b-41d4-a716-446655440003",
                ],
                "reason": "Aufbewahrungsfrist abgelaufen gemaess §147 AO",
            }
        }
    )


class DestructionProtocolItem(BaseModel):
    """Einzelnes Dokument im Vernichtungsprotokoll."""

    document_id: str = Field(description="Dokument-ID")
    filename: str = Field(description="Dateiname")
    original_filename: str = Field(description="Originaler Dateiname")
    retention_category: str = Field(description="Aufbewahrungskategorie")
    retention_years: int = Field(description="Aufbewahrungsdauer")
    archived_at: Optional[str] = Field(None, description="Archivierungszeitpunkt")
    retention_expired_at: str = Field(description="Ablaufdatum der Frist")
    content_hash: str = Field(description="SHA-256 Hash des Dokuments")
    hash_algorithm: str = Field(description="Verwendeter Hash-Algorithmus")
    is_verified: bool = Field(description="Integritaet verifiziert")


class DestructionProtocolError(BaseModel):
    """Fehler bei der Vernichtungsprotokoll-Erstellung."""

    document_id: str = Field(description="Dokument-ID")
    error: str = Field(description="Fehlerbeschreibung")


class DestructionProtocolResponse(BaseModel):
    """Antwort mit Vernichtungsprotokoll."""

    protocol_id: str = Field(description="Protokoll-ID")
    generated_at: str = Field(description="Zeitpunkt der Generierung")
    generated_by: str = Field(description="Erstellt von (User-ID)")
    reason: str = Field(description="Begruendung")
    legal_basis: str = Field(description="Gesetzliche Grundlage")
    total_documents: int = Field(description="Anzahl angefragter Dokumente")
    approved_for_destruction: int = Field(description="Zur Vernichtung freigegeben")
    rejected: int = Field(description="Abgelehnt")
    items: List[DestructionProtocolItem] = Field(
        default_factory=list,
        description="Freigegebene Dokumente"
    )
    errors: List[DestructionProtocolError] = Field(
        default_factory=list,
        description="Fehlgeschlagene Dokumente"
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "protocol_id": "990e8400-e29b-41d4-a716-446655440004",
                "generated_at": "2026-02-16T10:30:00+00:00",
                "generated_by": "550e8400-e29b-41d4-a716-446655440000",
                "reason": "Aufbewahrungsfrist abgelaufen",
                "legal_basis": "§147 AO, §257 HGB",
                "total_documents": 2,
                "approved_for_destruction": 1,
                "rejected": 1,
                "items": [],
                "errors": [],
            }
        }
    )


# =============================================================================
# Retention Summary Schemas
# =============================================================================


class RetentionCategorySummary(BaseModel):
    """Zusammenfassung einer Aufbewahrungskategorie."""

    category: str = Field(description="Kategorie-Name")
    total: int = Field(description="Gesamt-Anzahl")
    active: int = Field(description="Aktive (Frist noch nicht abgelaufen)")
    expiring_soon_90_days: int = Field(description="In 90 Tagen ablaufend")
    expired: int = Field(description="Frist abgelaufen")


class RetentionSettingInfo(BaseModel):
    """Information zu einer Aufbewahrungsfrist-Einstellung."""

    category: str = Field(description="Kategorie-Name")
    display_name: str = Field(description="Anzeigename auf Deutsch")
    retention_years: int = Field(description="Aufbewahrungsdauer in Jahren")
    legal_basis: Optional[str] = Field(None, description="Gesetzliche Grundlage")


class RetentionSummaryResponse(BaseModel):
    """Antwort mit Aufbewahrungsfristen-Zusammenfassung."""

    generated_at: str = Field(description="Zeitpunkt der Generierung")
    company_id: str = Field(description="Firmen-ID oder 'all'")
    categories: List[RetentionCategorySummary] = Field(
        default_factory=list,
        description="Aufschluesselung nach Kategorie"
    )
    retention_settings: List[RetentionSettingInfo] = Field(
        default_factory=list,
        description="Konfigurierte Aufbewahrungsfristen"
    )
