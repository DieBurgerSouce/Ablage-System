# -*- coding: utf-8 -*-
"""
Audit Trail Visualisierung API.

Vision 2026+ Feature: Visuelle Timeline aller Dokumenten-Aktionen
- Wer hat zugegriffen
- Wer hat geändert
- Wer hat genehmigt
- Filter nach Aktionstyp
- Export für Audits (PDF/CSV)

Nutzt bestehende AuditLog-Infrastruktur und ergänzt sie um
Dokument-spezifische und Entity-spezifische Audit Trails.
"""

from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Literal
from uuid import UUID

from app.core.types import JSONDict
import csv
import io

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, func, and_, or_, literal_column
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db, get_current_user
from app.core.security_auth import build_content_disposition
from app.db.models import (
    Document,
    User,
    AuditLog,
    BusinessEntity,
    DocumentActivity,
    Company,
)
from app.middleware.company_context import require_company

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/audit-trail", tags=["Audit Trail"])


# =============================================================================
# Pydantic Schemas
# =============================================================================

class AuditTrailEventSchema(BaseModel):
    """Schema für ein einzelnes Audit-Trail-Event."""
    id: UUID
    event_type: str = Field(..., description="Typ des Events (view, edit, approve, download, etc.)")
    title: str = Field(..., description="Deutscher Titel des Events")
    description: Optional[str] = Field(None, description="Detailbeschreibung")

    # Actor (wer hat die Aktion ausgeführt)
    actor_id: Optional[UUID] = None
    actor_name: Optional[str] = None
    actor_email: Optional[str] = None

    # Target (worauf wurde die Aktion ausgeführt)
    target_type: str = Field(..., description="document, entity, comment, etc.")
    target_id: UUID
    target_name: Optional[str] = None

    # Zeitstempel
    timestamp: datetime

    # Zusätzliche Metadaten
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    metadata: JSONDict = Field(default_factory=dict)
    changes: Optional[JSONDict] = Field(None, description="Delta bei Änderungen")

    # Visualisierung
    icon: str = Field(default="Activity", description="Lucide Icon")
    color: str = Field(default="gray", description="Tailwind Farbe")
    is_important: bool = Field(default=False, description="Wichtiges Event")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": "550e8400-e29b-41d4-a716-446655440000",
                "event_type": "document_edit",
                "title": "Dokument bearbeitet",
                "description": "Metadaten aktualisiert",
                "actor_id": "550e8400-e29b-41d4-a716-446655440001",
                "actor_name": "Max Mustermann",
                "actor_email": "max@example.com",
                "target_type": "document",
                "target_id": "550e8400-e29b-41d4-a716-446655440002",
                "target_name": "Rechnung_2026_001.pdf",
                "timestamp": "2026-01-28T10:30:00Z",
                "icon": "Edit",
                "color": "blue",
                "is_important": False,
            }
        },
    )


class AuditTrailResponse(BaseModel):
    """Response für Audit Trail Abfragen."""
    events: List[AuditTrailEventSchema]
    total: int
    limit: int
    offset: int
    has_more: bool
    summary: Dict[str, int] = Field(default_factory=dict, description="Zusammenfassung nach Event-Typ")


class AuditTrailStatsSchema(BaseModel):
    """Statistiken für Audit Trail."""
    total_events: int
    unique_actors: int
    events_by_type: Dict[str, int]
    events_by_day: List[JSONDict]
    most_active_users: List[JSONDict]
    date_range: Dict[str, str]


# =============================================================================
# Event Type Mapping
# =============================================================================

EVENT_TYPE_CONFIG: Dict[str, JSONDict] = {
    # Document Events
    "document_created": {"title": "Dokument erstellt", "icon": "FilePlus", "color": "green", "important": True},
    "document_uploaded": {"title": "Dokument hochgeladen", "icon": "Upload", "color": "green", "important": True},
    "document_viewed": {"title": "Dokument angesehen", "icon": "Eye", "color": "gray", "important": False},
    "document_downloaded": {"title": "Dokument heruntergeladen", "icon": "Download", "color": "blue", "important": False},
    "document_updated": {"title": "Dokument aktualisiert", "icon": "Edit", "color": "blue", "important": True},
    "document_deleted": {"title": "Dokument gelöscht", "icon": "Trash", "color": "red", "important": True},
    "document_restored": {"title": "Dokument wiederhergestellt", "icon": "RotateCcw", "color": "green", "important": True},
    "document_shared": {"title": "Dokument geteilt", "icon": "Share2", "color": "purple", "important": True},
    "document_exported": {"title": "Dokument exportiert", "icon": "FileOutput", "color": "blue", "important": False},

    # OCR Events
    "ocr_started": {"title": "OCR gestartet", "icon": "Scan", "color": "yellow", "important": False},
    "ocr_completed": {"title": "OCR abgeschlossen", "icon": "CheckCircle", "color": "green", "important": True},
    "ocr_failed": {"title": "OCR fehlgeschlagen", "icon": "XCircle", "color": "red", "important": True},
    "ocr_corrected": {"title": "OCR korrigiert", "icon": "Edit3", "color": "orange", "important": True},

    # Approval Events
    "approval_requested": {"title": "Genehmigung angefragt", "icon": "Clock", "color": "yellow", "important": True},
    "approval_approved": {"title": "Genehmigt", "icon": "Check", "color": "green", "important": True},
    "approval_rejected": {"title": "Abgelehnt", "icon": "X", "color": "red", "important": True},
    "approval_escalated": {"title": "Eskaliert", "icon": "ArrowUp", "color": "orange", "important": True},

    # Comment Events
    "comment_added": {"title": "Kommentar hinzugefuegt", "icon": "MessageSquare", "color": "blue", "important": False},
    "comment_replied": {"title": "Auf Kommentar geantwortet", "icon": "CornerDownRight", "color": "blue", "important": False},

    # Tag Events
    "tags_changed": {"title": "Tags geändert", "icon": "Tag", "color": "purple", "important": False},

    # Entity Events
    "entity_linked": {"title": "Geschäftspartner verknüpft", "icon": "Link", "color": "green", "important": True},
    "entity_unlinked": {"title": "Verknüpfung entfernt", "icon": "Unlink", "color": "red", "important": False},

    # Metadata Events
    "metadata_updated": {"title": "Metadaten aktualisiert", "icon": "FileText", "color": "gray", "important": False},
    "status_changed": {"title": "Status geändert", "icon": "RefreshCw", "color": "blue", "important": True},

    # Access Events
    "access_granted": {"title": "Zugriff gewährt", "icon": "UserPlus", "color": "green", "important": True},
    "access_revoked": {"title": "Zugriff entzogen", "icon": "UserMinus", "color": "red", "important": True},

    # Generic
    "unknown": {"title": "Aktion", "icon": "Activity", "color": "gray", "important": False},
}


def get_event_config(event_type: str) -> JSONDict:
    """Gibt Konfiguration für einen Event-Typ zurück."""
    return EVENT_TYPE_CONFIG.get(event_type, EVENT_TYPE_CONFIG["unknown"])


# =============================================================================
# Helper Functions
# =============================================================================

def _map_audit_log_action(action: str) -> str:
    """Mappt AuditLog.action zu Event-Typ."""
    action_lower = action.lower() if action else ""

    mappings = {
        "create": "document_created",
        "upload": "document_uploaded",
        "view": "document_viewed",
        "read": "document_viewed",
        "download": "document_downloaded",
        "update": "document_updated",
        "edit": "document_updated",
        "delete": "document_deleted",
        "restore": "document_restored",
        "share": "document_shared",
        "export": "document_exported",
        "ocr_start": "ocr_started",
        "ocr_complete": "ocr_completed",
        "ocr_fail": "ocr_failed",
        "ocr_correct": "ocr_corrected",
        "approve": "approval_approved",
        "reject": "approval_rejected",
        "escalate": "approval_escalated",
        "comment": "comment_added",
        "tag": "tags_changed",
        "link_entity": "entity_linked",
        "unlink_entity": "entity_unlinked",
        "status": "status_changed",
    }

    for key, value in mappings.items():
        if key in action_lower:
            return value

    return "unknown"


def _map_activity_type(activity_type: str) -> str:
    """Mappt DocumentActivity.activity_type zu Event-Typ."""
    # DocumentActivity hat bereits gute Typ-Namen
    return activity_type if activity_type in EVENT_TYPE_CONFIG else "unknown"


# =============================================================================
# Document Audit Trail Endpoint
# =============================================================================

@router.get(
    "/document/{document_id}",
    response_model=AuditTrailResponse,
    summary="Gibt Audit Trail für ein einzelnes Dokument zurück",
    description="""
    Zeigt alle Aktivitaeten die ein Dokument betreffen:
    - Wer hat angesehen (Views, Downloads)
    - Wer hat bearbeitet (Metadaten, Tags)
    - OCR-Verarbeitung
    - Kommentare
    - Genehmigungen
    - Verknüpfungen zu Geschäftspartnern
    """,
)
async def get_document_audit_trail(
    document_id: UUID,
    page: int = Query(1, ge=1, description="Seitennummer (1-basiert)"),
    per_page: int = Query(50, ge=1, le=200, description="Eintraege pro Seite"),
    event_types: Optional[List[str]] = Query(None, description="Filter nach Event-Typen"),
    actor_id: Optional[UUID] = Query(None, description="Filter nach Benutzer"),
    date_from: Optional[datetime] = Query(None, description="Von Datum"),
    date_until: Optional[datetime] = Query(None, description="Bis Datum"),
    important_only: bool = Query(False, description="Nur wichtige Events"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    company: Company = Depends(require_company),
) -> AuditTrailResponse:
    """Gibt Audit Trail für ein Dokument zurück."""

    # Paginierung: page/per_page -> offset/limit (Response-Contract erwartet limit/offset)
    company_id = company.id
    offset = (page - 1) * per_page
    limit = per_page
    # Prüfe ob Dokument existiert und Berechtigung
    doc_result = await db.execute(
        select(Document).where(
            Document.id == document_id,
            Document.company_id == company_id,
        )
    )
    document = doc_result.scalar_one_or_none()

    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dokument nicht gefunden",
        )

    events: List[AuditTrailEventSchema] = []
    summary: Dict[str, int] = {}

    # 1. Lade DocumentActivity Einträge
    activity_query = select(DocumentActivity).where(
        DocumentActivity.document_id == document_id
    )

    if actor_id:
        activity_query = activity_query.where(DocumentActivity.user_id == actor_id)
    if date_from:
        activity_query = activity_query.where(DocumentActivity.created_at >= date_from)
    if date_until:
        activity_query = activity_query.where(DocumentActivity.created_at <= date_until)

    activity_query = activity_query.order_by(DocumentActivity.created_at.desc())

    activity_result = await db.execute(activity_query.limit(per_page * 2))  # Holen mehr für Merge
    activities = activity_result.scalars().all()

    # 2. Lade AuditLog Einträge für dieses Dokument
    audit_query = select(AuditLog).where(
        and_(
            AuditLog.resource_type == "document",
            AuditLog.resource_id == str(document_id),
        )
    )

    if actor_id:
        audit_query = audit_query.where(AuditLog.user_id == actor_id)
    if date_from:
        audit_query = audit_query.where(AuditLog.created_at >= date_from)
    if date_until:
        audit_query = audit_query.where(AuditLog.created_at <= date_until)

    audit_query = audit_query.order_by(AuditLog.created_at.desc())

    audit_result = await db.execute(audit_query.limit(limit * 2))
    audit_logs = audit_result.scalars().all()

    # 3. Sammle User-IDs für Batch-Laden
    user_ids = set()
    for activity in activities:
        if activity.user_id:
            user_ids.add(activity.user_id)
    for log in audit_logs:
        if log.user_id:
            user_ids.add(log.user_id)

    # Lade User-Informationen
    users_map: Dict[UUID, User] = {}
    if user_ids:
        users_result = await db.execute(
            select(User).where(User.id.in_(user_ids))
        )
        for user in users_result.scalars().all():
            users_map[user.id] = user

    # 4. Konvertiere DocumentActivity zu Events
    for activity in activities:
        event_type = _map_activity_type(activity.activity_type)
        config = get_event_config(event_type)

        if important_only and not config["important"]:
            continue

        if event_types and event_type not in event_types:
            continue

        user = users_map.get(activity.user_id) if activity.user_id else None

        events.append(AuditTrailEventSchema(
            id=activity.id,
            event_type=event_type,
            title=config["title"],
            description=activity.description,
            actor_id=activity.user_id,
            actor_name=user.full_name if user else None,
            actor_email=user.email if user else None,
            target_type="document",
            target_id=document_id,
            target_name=document.original_filename or document.filename,
            timestamp=activity.created_at,
            metadata=activity.metadata or {},
            icon=config["icon"],
            color=config["color"],
            is_important=config["important"],
        ))

        summary[event_type] = summary.get(event_type, 0) + 1

    # 5. Konvertiere AuditLog zu Events (merge, vermeiden von Duplikaten)
    existing_timestamps = {e.timestamp for e in events}

    for log in audit_logs:
        # Skip wenn sehr ähnlicher Timestamp existiert (innerhalb 1 Sekunde)
        skip = False
        for ts in existing_timestamps:
            if abs((log.created_at - ts).total_seconds()) < 1:
                skip = True
                break
        if skip:
            continue

        event_type = _map_audit_log_action(log.action)
        config = get_event_config(event_type)

        if important_only and not config["important"]:
            continue

        if event_types and event_type not in event_types:
            continue

        user = users_map.get(log.user_id) if log.user_id else None

        events.append(AuditTrailEventSchema(
            id=log.id,
            event_type=event_type,
            title=config["title"],
            description=log.action,
            actor_id=log.user_id,
            actor_name=user.full_name if user else None,
            actor_email=user.email if user else None,
            target_type="document",
            target_id=document_id,
            target_name=document.original_filename or document.filename,
            timestamp=log.created_at,
            ip_address=log.ip_address,
            user_agent=log.user_agent,
            metadata=log.audit_metadata or {},
            changes=log.audit_metadata.get("changes") if log.audit_metadata else None,
            icon=config["icon"],
            color=config["color"],
            is_important=config["important"],
        ))

        summary[event_type] = summary.get(event_type, 0) + 1

    # Sortiere nach Timestamp absteigend
    events.sort(key=lambda e: e.timestamp, reverse=True)

    # Paginierung
    total = len(events)
    paginated_events = events[offset:offset + limit]
    has_more = (offset + limit) < total

    logger.info(
        "document_audit_trail_retrieved",
        document_id=str(document_id),
        user_id=str(current_user.id),
        total_events=total,
    )

    return AuditTrailResponse(
        events=paginated_events,
        total=total,
        limit=limit,
        offset=offset,
        has_more=has_more,
        summary=summary,
    )


# =============================================================================
# Entity Audit Trail Endpoint
# =============================================================================

@router.get(
    "/entity/{entity_id}",
    response_model=AuditTrailResponse,
    summary="Gibt Audit Trail für einen Geschäftspartner zurück",
)
async def get_entity_audit_trail(
    entity_id: UUID,
    page: int = Query(1, ge=1, description="Seitennummer (1-basiert)"),
    per_page: int = Query(50, ge=1, le=200, description="Eintraege pro Seite"),
    event_types: Optional[List[str]] = Query(None),
    date_from: Optional[datetime] = Query(None),
    date_until: Optional[datetime] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    company: Company = Depends(require_company),
) -> AuditTrailResponse:
    """Gibt Audit Trail für einen Geschäftspartner zurück."""

    # Paginierung: page/per_page -> offset/limit (Response-Contract erwartet limit/offset)
    company_id = company.id
    offset = (page - 1) * per_page
    limit = per_page
    # Prüfe ob Entity existiert und Berechtigung
    entity_result = await db.execute(
        select(BusinessEntity).where(
            BusinessEntity.id == entity_id,
            BusinessEntity.company_id == company_id,
        )
    )
    entity = entity_result.scalar_one_or_none()

    if not entity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Geschäftspartner nicht gefunden",
        )

    events: List[AuditTrailEventSchema] = []
    summary: Dict[str, int] = {}

    # Lade AuditLog Einträge für diese Entity
    audit_query = select(AuditLog).where(
        and_(
            AuditLog.resource_type == "entity",
            AuditLog.resource_id == str(entity_id),
        )
    )

    if date_from:
        audit_query = audit_query.where(AuditLog.created_at >= date_from)
    if date_until:
        audit_query = audit_query.where(AuditLog.created_at <= date_until)

    audit_query = audit_query.order_by(AuditLog.created_at.desc())

    audit_result = await db.execute(audit_query.limit(limit + offset))
    audit_logs = audit_result.scalars().all()

    # Lade User-Informationen
    user_ids = {log.user_id for log in audit_logs if log.user_id}
    users_map: Dict[UUID, User] = {}
    if user_ids:
        users_result = await db.execute(
            select(User).where(User.id.in_(user_ids))
        )
        for user in users_result.scalars().all():
            users_map[user.id] = user

    # Konvertiere zu Events
    for log in audit_logs:
        event_type = _map_audit_log_action(log.action)
        config = get_event_config(event_type)

        if event_types and event_type not in event_types:
            continue

        user = users_map.get(log.user_id) if log.user_id else None

        events.append(AuditTrailEventSchema(
            id=log.id,
            event_type=event_type,
            title=config["title"],
            description=log.action,
            actor_id=log.user_id,
            actor_name=user.full_name if user else None,
            actor_email=user.email if user else None,
            target_type="entity",
            target_id=entity_id,
            target_name=entity.display_name or entity.name,
            timestamp=log.created_at,
            ip_address=log.ip_address,
            user_agent=log.user_agent,
            metadata=log.audit_metadata or {},
            icon=config["icon"],
            color=config["color"],
            is_important=config["important"],
        ))

        summary[event_type] = summary.get(event_type, 0) + 1

    # Paginierung
    total = len(events)
    paginated_events = events[offset:offset + limit]
    has_more = (offset + limit) < total

    return AuditTrailResponse(
        events=paginated_events,
        total=total,
        limit=limit,
        offset=offset,
        has_more=has_more,
        summary=summary,
    )


# =============================================================================
# Export Endpoints
# =============================================================================

@router.get(
    "/document/{document_id}/export",
    summary="Exportiert Audit Trail als CSV oder PDF",
)
async def export_document_audit_trail(
    document_id: UUID,
    format: Literal["csv", "json"] = Query("csv"),
    date_from: Optional[datetime] = Query(None),
    date_until: Optional[datetime] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    company: Company = Depends(require_company),
) -> Response:
    """Exportiert Audit Trail für ein Dokument."""
    # Hole alle Events (ohne Paginierung)
    company_id = company.id
    result = await get_document_audit_trail(
        document_id=document_id,
        limit=10000,
        offset=0,
        date_from=date_from,
        date_until=date_until,
        db=db,
        current_user=current_user,
        company_id=company_id,
    )

    if format == "csv":
        return _export_to_csv(result.events, document_id)
    else:
        return _export_to_json(result.events, document_id)


def _export_to_csv(events: List[AuditTrailEventSchema], document_id: UUID) -> Response:
    """Exportiert Events als CSV."""
    output = io.StringIO()
    writer = csv.writer(output, quoting=csv.QUOTE_ALL)

    # Header (Deutsch)
    writer.writerow([
        "Zeitstempel",
        "Ereignistyp",
        "Titel",
        "Beschreibung",
        "Benutzer",
        "Email",
        "IP-Adresse",
        "Wichtig",
    ])

    # Daten
    for event in events:
        writer.writerow([
            event.timestamp.strftime("%d.%m.%Y %H:%M:%S") if event.timestamp else "",
            event.event_type,
            event.title,
            event.description or "",
            event.actor_name or "",
            event.actor_email or "",
            event.ip_address or "",
            "Ja" if event.is_important else "Nein",
        ])

    content = output.getvalue().encode('utf-8-sig')  # BOM für Excel

    return Response(
        content=content,
        media_type="text/csv",
        headers={
            "Content-Disposition": build_content_disposition(f"audit_trail_{document_id}.csv", "attachment"),
        },
    )


def _export_to_json(events: List[AuditTrailEventSchema], document_id: UUID) -> Response:
    """Exportiert Events als JSON."""
    import json

    data = {
        "document_id": str(document_id),
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "total_events": len(events),
        "events": [
            {
                "id": str(e.id),
                "timestamp": e.timestamp.isoformat() if e.timestamp else None,
                "event_type": e.event_type,
                "title": e.title,
                "description": e.description,
                "actor": {
                    "id": str(e.actor_id) if e.actor_id else None,
                    "name": e.actor_name,
                    "email": e.actor_email,
                },
                "ip_address": e.ip_address,
                "is_important": e.is_important,
                "metadata": e.metadata,
            }
            for e in events
        ],
    }

    content = json.dumps(data, ensure_ascii=False, indent=2).encode('utf-8')

    return Response(
        content=content,
        media_type="application/json",
        headers={
            "Content-Disposition": build_content_disposition(f"audit_trail_{document_id}.json", "attachment"),
        },
    )


# =============================================================================
# Statistics Endpoint
# =============================================================================

@router.get(
    "/stats",
    response_model=AuditTrailStatsSchema,
    summary="Gibt Audit Trail Statistiken zurück",
)
async def get_audit_trail_stats(
    document_id: Optional[UUID] = Query(None, description="Optional: Nur für dieses Dokument"),
    entity_id: Optional[UUID] = Query(None, description="Optional: Nur für diesen Geschäftspartner"),
    days: int = Query(30, ge=1, le=365, description="Zeitraum in Tagen"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    company: Company = Depends(require_company),
) -> AuditTrailStatsSchema:
    """Gibt Statistiken über Audit Trail Events zurück."""
    company_id = company.id
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    # Base Query
    base_conditions = [AuditLog.created_at >= cutoff]

    if document_id:
        base_conditions.extend([
            AuditLog.resource_type == "document",
            AuditLog.resource_id == str(document_id),
        ])
    elif entity_id:
        base_conditions.extend([
            AuditLog.resource_type == "entity",
            AuditLog.resource_id == str(entity_id),
        ])

    # Total Events
    total_result = await db.execute(
        select(func.count()).select_from(AuditLog).where(and_(*base_conditions))
    )
    total_events = total_result.scalar() or 0

    # Unique Actors
    actors_result = await db.execute(
        select(func.count(func.distinct(AuditLog.user_id)))
        .where(and_(*base_conditions, AuditLog.user_id.isnot(None)))
    )
    unique_actors = actors_result.scalar() or 0

    # Events by Type (Action)
    type_result = await db.execute(
        select(AuditLog.action, func.count())
        .where(and_(*base_conditions))
        .group_by(AuditLog.action)
        .order_by(func.count().desc())
        .limit(15)
    )
    events_by_type = {
        _map_audit_log_action(row[0]): row[1]
        for row in type_result.all()
    }

    # Events by Day
    day_result = await db.execute(
        select(
            func.date_trunc(literal_column("'day'"), AuditLog.created_at).label('day'),
            func.count()
        )
        .where(and_(*base_conditions))
        .group_by('day')
        .order_by('day')
    )
    events_by_day = [
        {"date": row[0].strftime("%Y-%m-%d"), "count": row[1]}
        for row in day_result.all()
    ]

    # Most Active Users
    user_result = await db.execute(
        select(AuditLog.user_id, func.count())
        .where(and_(*base_conditions, AuditLog.user_id.isnot(None)))
        .group_by(AuditLog.user_id)
        .order_by(func.count().desc())
        .limit(10)
    )
    top_user_data = user_result.all()

    most_active_users = []
    if top_user_data:
        user_ids = [row[0] for row in top_user_data]
        users_result = await db.execute(
            select(User).where(User.id.in_(user_ids))
        )
        users_map = {u.id: u for u in users_result.scalars().all()}

        most_active_users = [
            {
                "user_id": str(row[0]),
                "name": users_map.get(row[0]).full_name if users_map.get(row[0]) else None,
                "email": users_map.get(row[0]).email if users_map.get(row[0]) else None,
                "count": row[1],
            }
            for row in top_user_data
        ]

    return AuditTrailStatsSchema(
        total_events=total_events,
        unique_actors=unique_actors,
        events_by_type=events_by_type,
        events_by_day=events_by_day,
        most_active_users=most_active_users,
        date_range={
            "from": cutoff.strftime("%Y-%m-%d"),
            "to": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        },
    )


# =============================================================================
# Event Types Endpoint
# =============================================================================

@router.get(
    "/event-types",
    response_model=Dict[str, JSONDict],
    summary="Gibt alle verfügbaren Event-Typen zurück",
)
async def get_event_types() -> Dict[str, JSONDict]:
    """Gibt alle verfügbaren Event-Typen mit Konfiguration zurück."""
    return EVENT_TYPE_CONFIG
