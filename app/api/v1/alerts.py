# -*- coding: utf-8 -*-
"""
Alert Center API endpoints for Ablage-System.

Zentrale API für Alert-Management:
- Alert-Liste mit Filterung
- Acknowledge/Dismiss/Resolve/Escalate Actions
- Dashboard-Statistiken
- Bulk-Aktionen

Feinpoliert und durchdacht - Enterprise-grade Alert Management.
"""

from typing import Dict, List, Optional
from uuid import UUID

from app.core.types import JSONDict
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import (
    get_current_user,
    get_db,
    get_company_id,
)
from app.db.models import User
from app.db.models_alert import (
    AlertCategory,
    AlertSeverity,
    AlertStatus,
)
from app.services.alert_center_service import (
    AlertCenterService,
    get_alert_center_service,
)

router = APIRouter(prefix="/alerts", tags=["Alerts"])


# =============================================================================
# Pydantic Schemas
# =============================================================================

class AlertCreateRequest(BaseModel):
    """Request schema for creating an alert."""
    alert_code: str = Field(..., min_length=1, max_length=50)
    category: AlertCategory
    severity: AlertSeverity
    title: str = Field(..., min_length=1, max_length=255)
    message: str = Field(..., min_length=1)
    source_type: Optional[str] = None
    source_id: Optional[str] = None
    document_id: Optional[UUID] = None
    entity_id: Optional[UUID] = None
    metadata: Optional[JSONDict] = None
    context: Optional[JSONDict] = None
    available_actions: Optional[List[str]] = None
    assigned_to_id: Optional[UUID] = None
    auto_dismiss_hours: Optional[int] = Field(None, ge=1, le=720)
    recurrence_key: Optional[str] = None
    send_email: bool = False
    email_recipient: Optional[str] = None


class AlertResponse(BaseModel):
    """Response schema for a single alert."""
    id: UUID
    alert_code: str
    title: str
    message: str
    category: str
    severity: str
    status: str
    source_type: Optional[str]
    source_id: Optional[str]
    document_id: Optional[UUID]
    entity_id: Optional[UUID]
    company_id: UUID
    assigned_to_id: Optional[UUID]
    metadata: JSONDict
    context: JSONDict
    available_actions: List[str]
    created_at: str
    acknowledged_at: Optional[str]
    resolved_at: Optional[str]
    resolution_note: Optional[str]
    escalation_level: int
    email_sent: bool

    model_config = {"from_attributes": True}


class AlertListResponse(BaseModel):
    """Response schema for alert list."""
    alerts: List[AlertResponse]
    total: int
    page: int
    per_page: int


class AlertStatsResponse(BaseModel):
    """Response schema for alert statistics."""
    total_active: int
    new_count: int
    acknowledged_count: int
    in_progress_count: int
    resolved_count: int
    critical_count: int
    recent_24h_count: int
    by_category: Dict[str, int]
    by_severity: Dict[str, int]
    by_status: Dict[str, int]


class AlertActionRequest(BaseModel):
    """Request schema for alert actions."""
    resolution_note: Optional[str] = None
    resolution_action: Optional[str] = None
    reason: Optional[str] = None


class AlertEscalateRequest(BaseModel):
    """Request schema for alert escalation."""
    escalate_to_id: UUID
    reason: Optional[str] = None


class AlertAssignRequest(BaseModel):
    """Request schema for alert assignment."""
    assigned_to_id: UUID


class BulkActionRequest(BaseModel):
    """Request schema for bulk alert actions."""
    alert_ids: List[UUID] = Field(..., min_length=1, max_length=100)
    action: str = Field(..., pattern="^(acknowledge|dismiss|resolve)$")
    resolution_note: Optional[str] = None
    reason: Optional[str] = None


class BulkActionResponse(BaseModel):
    """Response schema for bulk actions."""
    success_count: int
    error_count: int
    total: int


# =============================================================================
# API Endpoints
# =============================================================================

@router.get("", response_model=AlertListResponse)
async def list_alerts(
    category: Optional[AlertCategory] = Query(None, description="Filter nach Kategorie"),
    severity: Optional[AlertSeverity] = Query(None, description="Filter nach Schweregrad"),
    status: Optional[AlertStatus] = Query(None, description="Filter nach Status"),
    assigned_to_id: Optional[UUID] = Query(None, description="Filter nach zugewiesenem Benutzer"),
    source_type: Optional[str] = Query(None, description="Filter nach Quellsystem"),
    unread_only: bool = Query(False, description="Nur ungelesene Alerts"),
    page: int = Query(1, ge=1, description="Seitennummer (1-basiert)"),
    per_page: int = Query(50, ge=1, le=200, description="Eintraege pro Seite"),
    order_by: str = Query("created_at", description="Sortierfeld"),
    order_desc: bool = Query(True, description="Absteigend sortieren"),
    current_user: User = Depends(get_current_user),
    company_id: UUID = Depends(get_company_id),
    session: AsyncSession = Depends(get_db),
) -> AlertListResponse:
    """
    Liste aller Alerts mit Filterung und Paginierung.

    Filtert nach Kategorie, Schweregrad, Status und weiteren Kriterien.
    """
    service = get_alert_center_service(session)

    alerts, total = await service.list_alerts(
        company_id=company_id,
        category=category,
        severity=severity,
        status=status,
        assigned_to_id=assigned_to_id,
        source_type=source_type,
        unread_only=unread_only,
        limit=per_page,
        offset=(page - 1) * per_page,
        order_by=order_by,
        order_desc=order_desc,
    )

    return AlertListResponse(
        alerts=[
            AlertResponse(
                id=a.id,
                alert_code=a.alert_code,
                title=a.title,
                message=a.message,
                category=a.category,
                severity=a.severity,
                status=a.status,
                source_type=a.source_type,
                source_id=a.source_id,
                document_id=a.document_id,
                entity_id=a.entity_id,
                company_id=a.company_id,
                assigned_to_id=a.assigned_to_id,
                metadata=a.metadata or {},
                context=a.context or {},
                available_actions=a.available_actions or [],
                created_at=a.created_at.isoformat() if a.created_at else "",
                acknowledged_at=a.acknowledged_at.isoformat() if a.acknowledged_at else None,
                resolved_at=a.resolved_at.isoformat() if a.resolved_at else None,
                resolution_note=a.resolution_note,
                escalation_level=a.escalation_level or 0,
                email_sent=a.email_sent or False,
            )
            for a in alerts
        ],
        total=total,
        page=page,
        per_page=per_page,
    )


@router.get("/stats", response_model=AlertStatsResponse)
async def get_alert_stats(
    current_user: User = Depends(get_current_user),
    company_id: UUID = Depends(get_company_id),
    session: AsyncSession = Depends(get_db),
) -> AlertStatsResponse:
    """
    Alert-Statistiken für Dashboard.

    Liefert Zaehler nach Kategorie, Schweregrad und Status.
    """
    service = get_alert_center_service(session)
    stats = await service.get_dashboard_stats(company_id)
    return AlertStatsResponse(**stats)


@router.get("/counts", response_model=Dict[str, int])
async def get_alert_counts(
    group_by: str = Query("category", pattern="^(category|severity|status)$"),
    current_user: User = Depends(get_current_user),
    company_id: UUID = Depends(get_company_id),
    session: AsyncSession = Depends(get_db),
) -> Dict[str, int]:
    """
    Alert-Zaehler gruppiert nach Kategorie, Schweregrad oder Status.
    """
    service = get_alert_center_service(session)
    return await service.get_alert_counts(company_id, group_by)


@router.get("/{alert_id}", response_model=AlertResponse)
async def get_alert(
    alert_id: UUID,
    current_user: User = Depends(get_current_user),
    company_id: UUID = Depends(get_company_id),
    session: AsyncSession = Depends(get_db),
) -> AlertResponse:
    """
    Einzelnen Alert abrufen.
    """
    service = get_alert_center_service(session)
    alert = await service.get_alert(alert_id, company_id)

    if not alert:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Alert nicht gefunden",
        )

    return AlertResponse(
        id=alert.id,
        alert_code=alert.alert_code,
        title=alert.title,
        message=alert.message,
        category=alert.category,
        severity=alert.severity,
        status=alert.status,
        source_type=alert.source_type,
        source_id=alert.source_id,
        document_id=alert.document_id,
        entity_id=alert.entity_id,
        company_id=alert.company_id,
        assigned_to_id=alert.assigned_to_id,
        metadata=alert.alert_metadata or {},
        context=alert.context or {},
        available_actions=alert.available_actions or [],
        created_at=alert.created_at.isoformat() if alert.created_at else "",
        acknowledged_at=alert.acknowledged_at.isoformat() if alert.acknowledged_at else None,
        resolved_at=alert.resolved_at.isoformat() if alert.resolved_at else None,
        resolution_note=alert.resolution_note,
        escalation_level=alert.escalation_level or 0,
        email_sent=alert.email_sent or False,
    )


@router.post("", response_model=AlertResponse, status_code=status.HTTP_201_CREATED)
async def create_alert(
    request: AlertCreateRequest,
    current_user: User = Depends(get_current_user),
    company_id: UUID = Depends(get_company_id),
    session: AsyncSession = Depends(get_db),
) -> AlertResponse:
    """
    Neuen Alert erstellen.

    Normalerweise werden Alerts automatisch vom System erstellt,
    aber manuelle Erstellung ist für spezielle Faelle möglich.
    """
    service = get_alert_center_service(session)

    alert = await service.create_alert(
        company_id=company_id,
        alert_code=request.alert_code,
        category=request.category,
        severity=request.severity,
        title=request.title,
        message=request.message,
        source_type=request.source_type,
        source_id=request.source_id,
        document_id=request.document_id,
        entity_id=request.entity_id,
        metadata=request.metadata,
        context=request.context,
        available_actions=request.available_actions,
        assigned_to_id=request.assigned_to_id,
        auto_dismiss_hours=request.auto_dismiss_hours,
        recurrence_key=request.recurrence_key,
        send_email=request.send_email,
        email_recipient=request.email_recipient,
    )

    await session.commit()

    return AlertResponse(
        id=alert.id,
        alert_code=alert.alert_code,
        title=alert.title,
        message=alert.message,
        category=alert.category,
        severity=alert.severity,
        status=alert.status,
        source_type=alert.source_type,
        source_id=alert.source_id,
        document_id=alert.document_id,
        entity_id=alert.entity_id,
        company_id=alert.company_id,
        assigned_to_id=alert.assigned_to_id,
        metadata=alert.alert_metadata or {},
        context=alert.context or {},
        available_actions=alert.available_actions or [],
        created_at=alert.created_at.isoformat() if alert.created_at else "",
        acknowledged_at=None,
        resolved_at=None,
        resolution_note=None,
        escalation_level=0,
        email_sent=alert.email_sent or False,
    )


@router.post("/{alert_id}/acknowledge", response_model=AlertResponse)
async def acknowledge_alert(
    alert_id: UUID,
    current_user: User = Depends(get_current_user),
    company_id: UUID = Depends(get_company_id),
    session: AsyncSession = Depends(get_db),
) -> AlertResponse:
    """
    Alert als gelesen/zur Kenntnis genommen markieren.
    """
    service = get_alert_center_service(session)
    alert = await service.acknowledge_alert(alert_id, current_user.id, company_id)

    if not alert:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Alert nicht gefunden",
        )

    await session.commit()

    return AlertResponse(
        id=alert.id,
        alert_code=alert.alert_code,
        title=alert.title,
        message=alert.message,
        category=alert.category,
        severity=alert.severity,
        status=alert.status,
        source_type=alert.source_type,
        source_id=alert.source_id,
        document_id=alert.document_id,
        entity_id=alert.entity_id,
        company_id=alert.company_id,
        assigned_to_id=alert.assigned_to_id,
        metadata=alert.alert_metadata or {},
        context=alert.context or {},
        available_actions=alert.available_actions or [],
        created_at=alert.created_at.isoformat() if alert.created_at else "",
        acknowledged_at=alert.acknowledged_at.isoformat() if alert.acknowledged_at else None,
        resolved_at=alert.resolved_at.isoformat() if alert.resolved_at else None,
        resolution_note=alert.resolution_note,
        escalation_level=alert.escalation_level or 0,
        email_sent=alert.email_sent or False,
    )


@router.post("/{alert_id}/dismiss", response_model=AlertResponse)
async def dismiss_alert(
    alert_id: UUID,
    request: Optional[AlertActionRequest] = None,
    current_user: User = Depends(get_current_user),
    company_id: UUID = Depends(get_company_id),
    session: AsyncSession = Depends(get_db),
) -> AlertResponse:
    """
    Alert verwerfen (als nicht relevant markieren).
    """
    service = get_alert_center_service(session)
    reason = request.reason if request else None
    alert = await service.dismiss_alert(alert_id, current_user.id, reason, company_id)

    if not alert:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Alert nicht gefunden",
        )

    await session.commit()

    return AlertResponse(
        id=alert.id,
        alert_code=alert.alert_code,
        title=alert.title,
        message=alert.message,
        category=alert.category,
        severity=alert.severity,
        status=alert.status,
        source_type=alert.source_type,
        source_id=alert.source_id,
        document_id=alert.document_id,
        entity_id=alert.entity_id,
        company_id=alert.company_id,
        assigned_to_id=alert.assigned_to_id,
        metadata=alert.alert_metadata or {},
        context=alert.context or {},
        available_actions=alert.available_actions or [],
        created_at=alert.created_at.isoformat() if alert.created_at else "",
        acknowledged_at=alert.acknowledged_at.isoformat() if alert.acknowledged_at else None,
        resolved_at=alert.resolved_at.isoformat() if alert.resolved_at else None,
        resolution_note=alert.resolution_note,
        escalation_level=alert.escalation_level or 0,
        email_sent=alert.email_sent or False,
    )


@router.post("/{alert_id}/resolve", response_model=AlertResponse)
async def resolve_alert(
    alert_id: UUID,
    request: Optional[AlertActionRequest] = None,
    current_user: User = Depends(get_current_user),
    company_id: UUID = Depends(get_company_id),
    session: AsyncSession = Depends(get_db),
) -> AlertResponse:
    """
    Alert als geloest markieren.
    """
    service = get_alert_center_service(session)

    resolution_note = request.resolution_note if request else None
    resolution_action = request.resolution_action if request else None

    alert = await service.resolve_alert(
        alert_id, current_user.id, resolution_note, resolution_action, company_id
    )

    if not alert:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Alert nicht gefunden",
        )

    await session.commit()

    return AlertResponse(
        id=alert.id,
        alert_code=alert.alert_code,
        title=alert.title,
        message=alert.message,
        category=alert.category,
        severity=alert.severity,
        status=alert.status,
        source_type=alert.source_type,
        source_id=alert.source_id,
        document_id=alert.document_id,
        entity_id=alert.entity_id,
        company_id=alert.company_id,
        assigned_to_id=alert.assigned_to_id,
        metadata=alert.alert_metadata or {},
        context=alert.context or {},
        available_actions=alert.available_actions or [],
        created_at=alert.created_at.isoformat() if alert.created_at else "",
        acknowledged_at=alert.acknowledged_at.isoformat() if alert.acknowledged_at else None,
        resolved_at=alert.resolved_at.isoformat() if alert.resolved_at else None,
        resolution_note=alert.resolution_note,
        escalation_level=alert.escalation_level or 0,
        email_sent=alert.email_sent or False,
    )


@router.post("/{alert_id}/escalate", response_model=AlertResponse)
async def escalate_alert(
    alert_id: UUID,
    request: AlertEscalateRequest,
    current_user: User = Depends(get_current_user),
    company_id: UUID = Depends(get_company_id),
    session: AsyncSession = Depends(get_db),
) -> AlertResponse:
    """
    Alert an einen anderen Benutzer eskalieren.
    """
    service = get_alert_center_service(session)

    alert = await service.escalate_alert(
        alert_id,
        request.escalate_to_id,
        current_user.id,
        request.reason,
        company_id,
    )

    if not alert:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Alert nicht gefunden",
        )

    await session.commit()

    return AlertResponse(
        id=alert.id,
        alert_code=alert.alert_code,
        title=alert.title,
        message=alert.message,
        category=alert.category,
        severity=alert.severity,
        status=alert.status,
        source_type=alert.source_type,
        source_id=alert.source_id,
        document_id=alert.document_id,
        entity_id=alert.entity_id,
        company_id=alert.company_id,
        assigned_to_id=alert.assigned_to_id,
        metadata=alert.alert_metadata or {},
        context=alert.context or {},
        available_actions=alert.available_actions or [],
        created_at=alert.created_at.isoformat() if alert.created_at else "",
        acknowledged_at=alert.acknowledged_at.isoformat() if alert.acknowledged_at else None,
        resolved_at=alert.resolved_at.isoformat() if alert.resolved_at else None,
        resolution_note=alert.resolution_note,
        escalation_level=alert.escalation_level or 0,
        email_sent=alert.email_sent or False,
    )


@router.post("/{alert_id}/assign", response_model=AlertResponse)
async def assign_alert(
    alert_id: UUID,
    request: AlertAssignRequest,
    current_user: User = Depends(get_current_user),
    company_id: UUID = Depends(get_company_id),
    session: AsyncSession = Depends(get_db),
) -> AlertResponse:
    """
    Alert einem Benutzer zuweisen.
    """
    service = get_alert_center_service(session)

    alert = await service.assign_alert(alert_id, request.assigned_to_id, company_id)

    if not alert:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Alert nicht gefunden",
        )

    await session.commit()

    return AlertResponse(
        id=alert.id,
        alert_code=alert.alert_code,
        title=alert.title,
        message=alert.message,
        category=alert.category,
        severity=alert.severity,
        status=alert.status,
        source_type=alert.source_type,
        source_id=alert.source_id,
        document_id=alert.document_id,
        entity_id=alert.entity_id,
        company_id=alert.company_id,
        assigned_to_id=alert.assigned_to_id,
        metadata=alert.alert_metadata or {},
        context=alert.context or {},
        available_actions=alert.available_actions or [],
        created_at=alert.created_at.isoformat() if alert.created_at else "",
        acknowledged_at=alert.acknowledged_at.isoformat() if alert.acknowledged_at else None,
        resolved_at=alert.resolved_at.isoformat() if alert.resolved_at else None,
        resolution_note=alert.resolution_note,
        escalation_level=alert.escalation_level or 0,
        email_sent=alert.email_sent or False,
    )


@router.post("/bulk", response_model=BulkActionResponse)
async def bulk_action(
    request: BulkActionRequest,
    current_user: User = Depends(get_current_user),
    company_id: UUID = Depends(get_company_id),
    session: AsyncSession = Depends(get_db),
) -> BulkActionResponse:
    """
    Massenaktion auf mehrere Alerts ausführen.

    Unterstützte Aktionen:
    - acknowledge: Als gelesen markieren
    - dismiss: Verwerfen
    - resolve: Als geloest markieren
    """
    service = get_alert_center_service(session)

    result = await service.bulk_action(
        alert_ids=request.alert_ids,
        action=request.action,
        user_id=current_user.id,
        company_id=company_id,
        resolution_note=request.resolution_note,
        reason=request.reason,
    )

    await session.commit()

    return BulkActionResponse(**result)
