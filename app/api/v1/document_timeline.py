# -*- coding: utf-8 -*-
"""
Document Timeline API Endpoints.

Phasenbasierte Lebensweg-Visualisierung fuer Dokumente:
  GET /documents/{id}/timeline         - Vollstaendige Timeline mit Phasengruppen
  GET /documents/{id}/timeline/summary - Schnell-Zusammenfassung mit Meilensteinen

Alle Texte in Deutsch. Multi-Tenant-sicher (company_id-Isolation).
GDPR Art. 30 compliant (vollstaendiger Audit-Trail).
"""

from dataclasses import asdict
from typing import Dict, List, Optional
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import (
    get_current_active_user,
    get_db,
    get_company_id,
    verify_document_ownership,
)
from app.core.safe_errors import safe_error_log
from app.db.models import User
from app.services.document_timeline_service import (
    DocumentTimelineSummary,
    DocumentTimelineResult,
    KeyMilestone,
    TimelineEventDetail,
    TimelinePhase,
    get_document_timeline_service,
)

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/documents", tags=["Dokument-Lebensweg"])


# =============================================================================
# PYDANTIC RESPONSE SCHEMAS
# =============================================================================


class TimelineEventResponse(BaseModel):
    """Einzelnes aufbereitetes Timeline-Ereignis."""

    id: str = Field(..., description="Eindeutige Ereignis-ID")
    event_type: str = Field(..., description="Technischer Ereignis-Typ (z.B. ocr_complete)")
    phase: str = Field(..., description="Zugehoerige Phase (z.B. VERARBEITUNG)")
    timestamp: Optional[str] = Field(None, description="ISO-8601 Zeitstempel")
    description: str = Field(..., description="Deutsche Beschreibung des Ereignisses")
    icon_hint: str = Field(..., description="Lucide-Icon-Name fuer das Frontend")
    user_id: Optional[str] = Field(None, description="ID des ausloesenden Benutzers")
    user_name: Optional[str] = Field(None, description="Anzeigename des Benutzers")
    details: Dict[str, object] = Field(
        default_factory=dict,
        description="Zusaetzliche Ereignis-Details (PII-bereinigt)",
    )
    duration_ms: Optional[int] = Field(None, description="Verarbeitungsdauer in Millisekunden")
    confidence: Optional[float] = Field(
        None,
        ge=0.0,
        le=1.0,
        description="Konfidenz (0.0 - 1.0) fuer OCR/Klassifikation",
    )
    source_service: Optional[str] = Field(None, description="Quell-Service")

    model_config = {"from_attributes": True}


class TimelinePhaseResponse(BaseModel):
    """Eine Phase im Dokumenten-Lebenszyklus mit ihren Ereignissen."""

    phase: str = Field(..., description="Phasenkennung (z.B. VERARBEITUNG)")
    phase_label: str = Field(..., description="Deutsches Label (z.B. OCR-Verarbeitung)")
    completed: bool = Field(..., description="Ob die Phase abgeschlossen ist")
    first_event_at: Optional[str] = Field(None, description="Erster Ereignis-Zeitstempel")
    last_event_at: Optional[str] = Field(None, description="Letzter Ereignis-Zeitstempel")
    event_count: int = Field(..., description="Anzahl der Ereignisse in dieser Phase")
    events: List[TimelineEventResponse] = Field(
        default_factory=list,
        description="Ereignisse dieser Phase (chronologisch)",
    )

    model_config = {"from_attributes": True}


class DocumentTimelineResponse(BaseModel):
    """Vollstaendige phasenbezogene Timeline eines Dokuments."""

    document_id: str = Field(..., description="Dokument-ID")
    total_events: int = Field(..., description="Gesamtanzahl aller Ereignisse")
    phases: List[TimelinePhaseResponse] = Field(
        ...,
        description="Phasen in definierter Reihenfolge (alle 7 Phasen immer vorhanden)",
    )
    all_events: List[TimelineEventResponse] = Field(
        ...,
        description="Alle Ereignisse chronologisch sortiert (ungefiltert/ungegruppiert)",
    )

    model_config = {"from_attributes": True}


class KeyMilestoneResponse(BaseModel):
    """Wichtiger Meilenstein im Dokumenten-Lebenszyklus."""

    phase: str = Field(..., description="Phasenkennung")
    phase_label: str = Field(..., description="Deutsches Label")
    completed_at: Optional[str] = Field(
        None, description="Abschluss-Zeitstempel (None = noch nicht erreicht)"
    )
    event_count: int = Field(..., description="Anzahl der Ereignisse in dieser Phase")

    model_config = {"from_attributes": True}


class DocumentTimelineSummaryResponse(BaseModel):
    """Schnell-Zusammenfassung des Dokumenten-Lebenszyklus."""

    document_id: str = Field(..., description="Dokument-ID")
    total_events: int = Field(..., description="Gesamtanzahl aller gespeicherten Ereignisse")
    current_phase: Optional[str] = Field(
        None, description="Aktuelle (letzte abgeschlossene) Phase"
    )
    current_phase_label: Optional[str] = Field(
        None, description="Deutsches Label der aktuellen Phase"
    )
    time_since_upload: Optional[str] = Field(
        None, description="Zeit seit dem Upload (z.B. 'vor 3 Stunde(n)')"
    )
    upload_at: Optional[str] = Field(None, description="ISO-8601 Upload-Zeitstempel")
    key_milestones: List[KeyMilestoneResponse] = Field(
        ...,
        description="Liste aller 7 Phasen-Meilensteine mit Abschluss-Zeitstempel",
    )
    completion_percentage: float = Field(
        ...,
        ge=0.0,
        le=100.0,
        description="Anteil abgeschlossener Phasen in Prozent (0-100)",
    )

    model_config = {"from_attributes": True}


# =============================================================================
# KONVERTER-HILFSFUNKTIONEN
# =============================================================================


def _event_to_response(event: TimelineEventDetail) -> TimelineEventResponse:
    """Konvertiert ein internes TimelineEventDetail in ein API-Response-Schema."""
    return TimelineEventResponse(
        id=event.id,
        event_type=event.event_type,
        phase=event.phase,
        timestamp=event.timestamp,
        description=event.description,
        icon_hint=event.icon_hint,
        user_id=event.user_id,
        user_name=event.user_name,
        details=event.details,
        duration_ms=event.duration_ms,
        confidence=event.confidence,
        source_service=event.source_service,
    )


def _phase_to_response(phase: TimelinePhase) -> TimelinePhaseResponse:
    """Konvertiert eine interne TimelinePhase in ein API-Response-Schema."""
    return TimelinePhaseResponse(
        phase=phase.phase,
        phase_label=phase.phase_label,
        completed=phase.completed,
        first_event_at=phase.first_event_at,
        last_event_at=phase.last_event_at,
        event_count=phase.event_count,
        events=[_event_to_response(e) for e in phase.events],
    )


def _milestone_to_response(milestone: KeyMilestone) -> KeyMilestoneResponse:
    """Konvertiert einen internen KeyMilestone in ein API-Response-Schema."""
    return KeyMilestoneResponse(
        phase=milestone.phase,
        phase_label=milestone.phase_label,
        completed_at=milestone.completed_at,
        event_count=milestone.event_count,
    )


# =============================================================================
# ENDPOINTS
# =============================================================================


@router.get(
    "/{document_id}/timeline",
    response_model=DocumentTimelineResponse,
    summary="Vollstaendige Dokumenten-Timeline",
    description=(
        "Liefert alle Lebensweg-Ereignisse eines Dokuments, geordnet nach Phasen "
        "und chronologisch sortiert. Aggregiert Lineage-Events, OCR-Jobs, "
        "Audit-Logs, Korrekturen und Versionen."
    ),
    responses={
        200: {"description": "Timeline erfolgreich abgerufen"},
        403: {"description": "Kein Zugriff auf dieses Dokument"},
        404: {"description": "Dokument nicht gefunden"},
    },
)
async def get_document_timeline(
    document_id: UUID,
    limit: int = Query(
        100,
        ge=1,
        le=500,
        description="Maximale Anzahl der Ereignisse (Standard: 100)",
    ),
    event_types: Optional[str] = Query(
        None,
        description=(
            "Komma-getrennte Event-Typen zum Filtern "
            "(z.B. ocr_complete,export,approval)"
        ),
    ),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_company_id),
    db: AsyncSession = Depends(get_db),
    _ownership: bool = Depends(verify_document_ownership),
) -> DocumentTimelineResponse:
    """
    Vollstaendige phasenbezogene Dokumenten-Timeline.

    Aggregiert Ereignisse aus allen Quellen:
    - **Lineage-Events**: Alle in der Lineage-Tabelle gespeicherten Ereignisse
    - **Processing-Jobs**: OCR-Start und -Abschluss aus der Jobs-Tabelle
    - **Audit-Logs**: Genehmigungen, Exporte, Freigaben
    - **OCR-Korrekturen**: Manuelle Benutzer-Korrekturen
    - **Versionen**: Erstellte Dokumentversionen
    - **Dokumentzustand**: Upload-, Kategorisierungs-, Archivierungsfelder

    **Phasenstruktur** (immer alle 7 Phasen vorhanden):
    1. UPLOAD - Hochladen
    2. VERARBEITUNG - OCR-Verarbeitung
    3. KLASSIFIKATION - Dokumenttyp-Erkennung
    4. ZUORDNUNG - Geschaeftspartner-Verknuepfung
    5. KORREKTUR - Manuelle Korrekturen und Anmerkungen
    6. EXPORT - Exporte, Genehmigungen, Workflow
    7. ARCHIVIERUNG - GoBD-Archivierung, DSGVO-Loeschung

    **Zugriffsschutz**: Nur Dokumente der eigenen Firma sichtbar.
    """
    # Event-Typ-Filter parsen
    parsed_event_types: Optional[List[str]] = None
    if event_types:
        parsed_event_types = [t.strip() for t in event_types.split(",") if t.strip()]

    service = get_document_timeline_service(db)

    try:
        result: DocumentTimelineResult = await service.get_timeline(
            document_id=document_id,
            company_id=company_id,
            limit=limit,
            event_types=parsed_event_types,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dokument nicht gefunden",
        ) from exc
    except Exception as exc:
        logger.error(
            "document_timeline_fetch_failed",
            document_id=str(document_id),
            **safe_error_log(exc),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Timeline konnte nicht abgerufen werden",
        ) from exc

    return DocumentTimelineResponse(
        document_id=result.document_id,
        total_events=result.total_events,
        phases=[_phase_to_response(p) for p in result.phases],
        all_events=[_event_to_response(e) for e in result.all_events],
    )


@router.get(
    "/{document_id}/timeline/summary",
    response_model=DocumentTimelineSummaryResponse,
    summary="Dokumenten-Lebensweg Zusammenfassung",
    description=(
        "Liefert eine schnelle Zusammenfassung des Dokumenten-Lebenszyklus: "
        "Gesamtereigniszahl, aktuelle Phase, Zeit seit Upload und "
        "Meilensteine aller 7 Phasen."
    ),
    responses={
        200: {"description": "Zusammenfassung erfolgreich abgerufen"},
        403: {"description": "Kein Zugriff auf dieses Dokument"},
        404: {"description": "Dokument nicht gefunden"},
    },
)
async def get_document_timeline_summary(
    document_id: UUID,
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_company_id),
    db: AsyncSession = Depends(get_db),
    _ownership: bool = Depends(verify_document_ownership),
) -> DocumentTimelineSummaryResponse:
    """
    Schnell-Zusammenfassung des Dokumenten-Lebenszyklus.

    Nutzt die Lineage-Summary-Cache-Tabelle fuer hohe Performance.
    Gibt immer alle 7 Phasen-Meilensteine zurueck, auch wenn sie noch
    nicht abgeschlossen sind (completed_at ist dann None).

    **Anwendungsfaelle**:
    - Fortschrittsbalken im Frontend
    - Schnellansicht des aktuellen Status
    - Badge-Anzeige (z.B. "Phase 3 von 7")
    - Benachrichtigungen bei Phasenwechseln

    **Meilensteine** (immer alle 7):
    - UPLOAD: Dokument hochgeladen
    - VERARBEITUNG: OCR-Erkennung abgeschlossen
    - KLASSIFIKATION: Dokumenttyp erkannt
    - ZUORDNUNG: Geschaeftspartner verknuepft
    - KORREKTUR: Letzte manuelle Korrektur
    - EXPORT: Letzter Export oder Genehmigung
    - ARCHIVIERUNG: GoBD-Archivierung

    **completion_percentage**: Anteil abgeschlossener Phasen (0 - 100 %).
    """
    service = get_document_timeline_service(db)

    try:
        summary: DocumentTimelineSummary = await service.get_summary(
            document_id=document_id,
            company_id=company_id,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dokument nicht gefunden",
        ) from exc
    except Exception as exc:
        logger.error(
            "document_timeline_summary_failed",
            document_id=str(document_id),
            **safe_error_log(exc),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Zusammenfassung konnte nicht abgerufen werden",
        ) from exc

    return DocumentTimelineSummaryResponse(
        document_id=summary.document_id,
        total_events=summary.total_events,
        current_phase=summary.current_phase,
        current_phase_label=summary.current_phase_label,
        time_since_upload=summary.time_since_upload,
        upload_at=summary.upload_at,
        key_milestones=[_milestone_to_response(m) for m in summary.key_milestones],
        completion_percentage=summary.completion_percentage,
    )
