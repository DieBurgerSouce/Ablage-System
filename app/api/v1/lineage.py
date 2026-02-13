# -*- coding: utf-8 -*-
"""
Document Lineage API endpoints for Ablage-System.

API fuer Datenherkunfts-Tracking:
- Timeline aller Ereignisse
- Statistiken zur Verarbeitung
- Export der Lineage-Daten

Feinpoliert und durchdacht - Enterprise-grade Document Lineage.
"""

import json
from datetime import datetime
from typing import Dict, List, Optional

from app.core.types import JSONDict
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.reports.pdf_export_service import PdfExportService
from app.services.reports.report_templates import ReportColumn

from app.api.dependencies import (
    get_current_user,
    get_db,
    get_company_id,
    verify_document_ownership,
)
from app.db.models import User
from app.db.models_lineage import LineageEventType, ImportSourceType
from app.services.lineage.document_lineage_service import (
    DocumentLineageService,
    get_lineage_service,
    LineageStats,
)

router = APIRouter(prefix="/documents", tags=["Document Lineage"])


# =============================================================================
# Pydantic Schemas
# =============================================================================


class TimelineEntryResponse(BaseModel):
    """Response-Schema fuer einen Timeline-Eintrag."""

    id: str
    event_type: str
    event_data: JSONDict
    timestamp: str
    duration_ms: Optional[int] = None
    confidence: Optional[float] = None
    user_id: Optional[str] = None
    source_service: Optional[str] = None

    model_config = {"from_attributes": True}


class TimelineResponse(BaseModel):
    """Response-Schema fuer die Timeline."""

    document_id: str
    events: List[TimelineEntryResponse]
    total: int
    limit: int
    offset: int


class LineageStatsResponse(BaseModel):
    """Response-Schema fuer Lineage-Statistiken."""

    document_id: str
    total_events: int
    total_processing_duration_ms: int
    ocr: JSONDict
    classification: JSONDict
    entity_linking: JSONDict
    modifications: JSONDict
    exports: JSONDict
    workflow: JSONDict
    import_info: JSONDict


class LineageSummaryResponse(BaseModel):
    """Response-Schema fuer die Lineage-Zusammenfassung."""

    id: str
    document_id: str
    import_info: JSONDict
    ocr: JSONDict
    classification: JSONDict
    entity_linking: JSONDict
    modifications: JSONDict
    statistics: JSONDict
    last_exported_at: Optional[str] = None
    company_id: str
    created_at: str
    updated_at: str


# =============================================================================
# Event Type Mapping (German)
# =============================================================================


EVENT_TYPE_LABELS = {
    "import": "Import",
    "ocr_start": "OCR gestartet",
    "ocr_complete": "OCR abgeschlossen",
    "ocr_failed": "OCR fehlgeschlagen",
    "classification": "Klassifizierung",
    "extraction": "Datenextraktion",
    "entity_link": "Geschaeftspartner verknuepft",
    "entity_unlink": "Verknuepfung entfernt",
    "modification": "Bearbeitung",
    "metadata_update": "Metadaten aktualisiert",
    "tag_change": "Tags geaendert",
    "approval": "Genehmigt",
    "rejection": "Abgelehnt",
    "escalation": "Eskaliert",
    "export": "Exportiert",
    "archive": "Archiviert",
    "restore": "Wiederhergestellt",
    "soft_delete": "Geloescht (DSGVO)",
    "hard_delete": "Endgueltig geloescht",
}


# =============================================================================
# API Endpoints
# =============================================================================


@router.get("/{document_id}/lineage", response_model=TimelineResponse)
async def get_document_lineage(
    document_id: UUID,
    limit: int = Query(50, ge=1, le=500, description="Maximale Anzahl Ereignisse"),
    offset: int = Query(0, ge=0, description="Offset fuer Pagination"),
    event_types: Optional[str] = Query(
        None,
        description="Komma-getrennte Event-Typen zum Filtern",
    ),
    current_user: User = Depends(get_current_user),
    company_id: UUID = Depends(get_company_id),
    session: AsyncSession = Depends(get_db),
    _ownership: bool = Depends(verify_document_ownership),
) -> TimelineResponse:
    """
    Ruft die vollstaendige Lineage-Timeline eines Dokuments ab.

    Zeigt alle Ereignisse in der Verarbeitungskette:
    - Import (Quelle, Zeitpunkt)
    - OCR-Verarbeitung (Backend, Dauer, Konfidenz)
    - Klassifikation
    - Entity-Linking
    - Bearbeitungen
    - Exports
    """
    # Event-Typ-Filter parsen
    filter_types: Optional[List[LineageEventType]] = None
    if event_types:
        try:
            type_names = [t.strip() for t in event_types.split(",")]
            filter_types = [LineageEventType(t) for t in type_names if t]
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Ungueltiger Event-Typ: {e}",
            )

    service = get_lineage_service(session)

    events, total = await service.get_timeline(
        document_id=document_id,
        company_id=company_id,
        limit=limit,
        offset=offset,
        event_types=filter_types,
    )

    return TimelineResponse(
        document_id=str(document_id),
        events=[
            TimelineEntryResponse(
                id=e.id,
                event_type=e.event_type,
                event_data=e.event_data,
                timestamp=e.timestamp.isoformat() if e.timestamp else "",
                duration_ms=e.duration_ms,
                confidence=e.confidence,
                user_id=e.user_id,
                source_service=e.source_service,
            )
            for e in events
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{document_id}/lineage/stats", response_model=LineageStatsResponse)
async def get_document_lineage_stats(
    document_id: UUID,
    current_user: User = Depends(get_current_user),
    company_id: UUID = Depends(get_company_id),
    session: AsyncSession = Depends(get_db),
    _ownership: bool = Depends(verify_document_ownership),
) -> LineageStatsResponse:
    """
    Ruft aggregierte Statistiken zur Dokumenten-Lineage ab.

    Liefert:
    - Gesamte Verarbeitungsdauer
    - OCR-Konfidenz und Backend
    - Anzahl Bearbeitungen
    - Anzahl Exports
    - Workflow-Status (Genehmigungen/Ablehnungen)
    """
    service = get_lineage_service(session)

    stats = await service.get_lineage_stats(
        document_id=document_id,
        company_id=company_id,
    )

    if not stats:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Keine Lineage-Daten fuer dieses Dokument gefunden",
        )

    return LineageStatsResponse(
        document_id=str(document_id),
        total_events=stats.total_events,
        total_processing_duration_ms=stats.total_processing_duration_ms,
        ocr={
            "duration_ms": stats.ocr_duration_ms,
            "confidence": stats.ocr_confidence,
        },
        classification={
            "confidence": stats.classification_confidence,
        },
        entity_linking={
            "confidence": stats.entity_link_confidence,
        },
        modifications={
            "count": stats.modification_count,
            "last_modified_at": (
                stats.last_modified_at.isoformat()
                if stats.last_modified_at
                else None
            ),
        },
        exports={
            "count": stats.export_count,
        },
        workflow={
            "approval_count": stats.approval_count,
            "rejection_count": stats.rejection_count,
        },
        import_info={
            "source_type": stats.import_source_type,
            "imported_at": (
                stats.imported_at.isoformat()
                if stats.imported_at
                else None
            ),
        },
    )


@router.get("/{document_id}/lineage/summary", response_model=LineageSummaryResponse)
async def get_document_lineage_summary(
    document_id: UUID,
    current_user: User = Depends(get_current_user),
    company_id: UUID = Depends(get_company_id),
    session: AsyncSession = Depends(get_db),
    _ownership: bool = Depends(verify_document_ownership),
) -> LineageSummaryResponse:
    """
    Ruft die vollstaendige Lineage-Zusammenfassung ab.

    Enthaelt alle aggregierten Informationen zur Dokumenten-Historie.
    """
    service = get_lineage_service(session)

    summary = await service.get_summary(
        document_id=document_id,
        company_id=company_id,
    )

    if not summary:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Keine Lineage-Zusammenfassung fuer dieses Dokument gefunden",
        )

    return LineageSummaryResponse(
        id=str(summary.id),
        document_id=str(summary.document_id),
        import_info={
            "source_type": summary.import_source_type,
            "source_details": summary.import_source_details or {},
            "imported_at": (
                summary.imported_at.isoformat()
                if summary.imported_at
                else None
            ),
            "imported_by_id": (
                str(summary.imported_by_id)
                if summary.imported_by_id
                else None
            ),
        },
        ocr={
            "backend": summary.ocr_backend,
            "duration_ms": summary.ocr_duration_ms,
            "confidence": summary.ocr_confidence,
            "completed_at": (
                summary.ocr_completed_at.isoformat()
                if summary.ocr_completed_at
                else None
            ),
        },
        classification={
            "confidence": summary.classification_confidence,
            "classified_at": (
                summary.classified_at.isoformat()
                if summary.classified_at
                else None
            ),
        },
        entity_linking={
            "current_entity_id": (
                str(summary.current_entity_id)
                if summary.current_entity_id
                else None
            ),
            "confidence": summary.entity_link_confidence,
            "linked_at": (
                summary.entity_linked_at.isoformat()
                if summary.entity_linked_at
                else None
            ),
            "link_count": summary.entity_link_count,
        },
        modifications={
            "count": summary.modification_count,
            "last_modified_at": (
                summary.last_modified_at.isoformat()
                if summary.last_modified_at
                else None
            ),
            "last_modified_by_id": (
                str(summary.last_modified_by_id)
                if summary.last_modified_by_id
                else None
            ),
        },
        statistics={
            "total_processing_duration_ms": summary.total_processing_duration_ms,
            "total_event_count": summary.total_event_count,
            "approval_count": summary.approval_count,
            "rejection_count": summary.rejection_count,
            "export_count": summary.export_count,
        },
        last_exported_at=(
            summary.last_exported_at.isoformat()
            if summary.last_exported_at
            else None
        ),
        company_id=str(summary.company_id),
        created_at=(
            summary.created_at.isoformat()
            if summary.created_at
            else ""
        ),
        updated_at=(
            summary.updated_at.isoformat()
            if summary.updated_at
            else ""
        ),
    )


@router.get("/{document_id}/lineage/export")
async def export_document_lineage(
    document_id: UUID,
    format: str = Query("json", regex="^(json|pdf)$", description="Export-Format"),
    current_user: User = Depends(get_current_user),
    company_id: UUID = Depends(get_company_id),
    session: AsyncSession = Depends(get_db),
    _ownership: bool = Depends(verify_document_ownership),
) -> Response:
    """
    Exportiert die Lineage-Daten eines Dokuments.

    Unterstuetzte Formate:
    - json: Vollstaendige Lineage als JSON
    - pdf: Formatierter PDF-Report
    """
    service = get_lineage_service(session)

    # Timeline und Statistiken abrufen
    events, total = await service.get_timeline(
        document_id=document_id,
        company_id=company_id,
        limit=1000,  # Maximale Events fuer Export
    )

    stats = await service.get_lineage_stats(
        document_id=document_id,
        company_id=company_id,
    )

    summary = await service.get_summary(
        document_id=document_id,
        company_id=company_id,
    )

    if format == "json":
        export_data = {
            "document_id": str(document_id),
            "exported_at": datetime.utcnow().isoformat(),
            "exported_by": str(current_user.id),
            "statistics": {
                "total_events": stats.total_events if stats else 0,
                "total_processing_duration_ms": (
                    stats.total_processing_duration_ms if stats else 0
                ),
                "ocr_confidence": stats.ocr_confidence if stats else None,
                "classification_confidence": (
                    stats.classification_confidence if stats else None
                ),
                "modification_count": stats.modification_count if stats else 0,
                "export_count": stats.export_count if stats else 0,
            },
            "summary": summary.to_dict() if summary else None,
            "timeline": [e.to_dict() for e in events],
            "event_type_labels": EVENT_TYPE_LABELS,
        }

        json_content = json.dumps(export_data, ensure_ascii=False, indent=2)

        return Response(
            content=json_content.encode("utf-8"),
            media_type="application/json",
            headers={
                "Content-Disposition": (
                    f'attachment; filename="lineage_{document_id}.json"'
                ),
            },
        )

    elif format == "pdf":
        # Statistik-Kopfzeile als Subtitle
        stats_parts: List[str] = []
        if stats:
            stats_parts.append(f"{stats.total_events} Ereignisse")
            if stats.ocr_confidence is not None:
                stats_parts.append(f"OCR-Konfidenz: {stats.ocr_confidence:.0%}")
            if stats.modification_count:
                stats_parts.append(f"{stats.modification_count} Bearbeitungen")
        subtitle = " | ".join(stats_parts) if stats_parts else ""

        # Spalten-Definition
        columns_def = [
            ReportColumn(key="timestamp", label="Zeitpunkt", width=120, format_type="text"),
            ReportColumn(key="event_type", label="Ereignis", width=150, format_type="text"),
            ReportColumn(key="confidence", label="Konfidenz", width=70, format_type="text"),
            ReportColumn(key="duration", label="Dauer", width=60, format_type="text"),
            ReportColumn(key="source", label="Quelle", width=100, format_type="text"),
        ]

        # Events in Tabellenzeilen umwandeln
        table_data: List[Dict[str, object]] = []
        for event in events:
            ts = event.timestamp.strftime("%d.%m.%Y %H:%M") if event.timestamp else "-"
            label = EVENT_TYPE_LABELS.get(event.event_type, event.event_type)
            conf = f"{event.confidence:.0%}" if event.confidence is not None else "-"
            dur = f"{event.duration_ms} ms" if event.duration_ms is not None else "-"
            src = event.source_service or "-"
            table_data.append({
                "timestamp": ts,
                "event_type": label,
                "confidence": conf,
                "duration": dur,
                "source": src,
            })

        pdf_service = PdfExportService()
        pdf_bytes = await pdf_service.generate_report_pdf(
            title="Dokument-Lineage",
            subtitle=subtitle,
            columns=columns_def,
            data=table_data,
        )

        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={
                "Content-Disposition": (
                    f'attachment; filename="lineage_{document_id}.pdf"'
                ),
            },
        )

    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ungueltiges Export-Format",
        )


@router.get("/lineage/event-types")
async def get_lineage_event_types(
    current_user: User = Depends(get_current_user),
) -> Dict[str, str]:
    """
    Gibt alle verfuegbaren Event-Typen mit deutschen Labels zurueck.

    Nuetzlich fuer Frontend-Filterung und Anzeige.
    """
    return EVENT_TYPE_LABELS


@router.get("/lineage/import-source-types")
async def get_import_source_types(
    current_user: User = Depends(get_current_user),
) -> Dict[str, str]:
    """
    Gibt alle verfuegbaren Import-Quelltypen mit deutschen Labels zurueck.
    """
    return {
        "manual_upload": "Manueller Upload",
        "email": "E-Mail Import",
        "folder": "Ordner-Import",
        "api": "API Upload",
        "scan": "Scanner",
        "integration": "Integration",
    }
