# -*- coding: utf-8 -*-
"""
Proaktiver Assistent API Endpoints fuer Ablage-System.

API fuer das proaktive Hint-System:
- Dashboard-Widget Daten
- Hint-Liste mit Filterung
- Status-Updates (gesehen, bestaetigt, abgelehnt, bearbeitet)
- Kontext-Hints fuer Dokument/Entity Sidebar
- Statistiken und Regelkonfiguration

Feinpoliert und durchdacht - Enterprise-grade Proactive Intelligence.
"""

from datetime import datetime
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
from app.db.models_proactive_assistant import (
    HintCategory,
    HintPriority,
    HintStatus,
)
from app.services.proactive_assistant_service import (
    ProactiveAssistantService,
    get_proactive_assistant_service,
)

router = APIRouter(prefix="/proactive-assistant", tags=["Proaktiver Assistent"])


# =============================================================================
# Pydantic Schemas
# =============================================================================


class HintResponse(BaseModel):
    """Einzelner Hint in API-Response."""
    id: UUID
    company_id: UUID
    user_id: Optional[UUID]
    category: str
    priority: str
    status: str
    title: str
    message: str
    urgency_score: float
    value_score: float
    combined_score: float
    source_type: str
    source_id: Optional[UUID]
    source_metadata: JSONDict
    action_url: Optional[str]
    action_label: Optional[str]
    expires_at: Optional[str]
    seen_at: Optional[str]
    acknowledged_at: Optional[str]
    dismissed_at: Optional[str]
    created_at: str
    updated_at: Optional[str]

    model_config = {"from_attributes": True}


class HintListResponse(BaseModel):
    """Paginierte Hint-Liste."""
    hints: List[HintResponse]
    total: int
    limit: int
    offset: int


class DashboardSummaryResponse(BaseModel):
    """Dashboard-Widget Zusammenfassung."""
    total_active: int
    by_category: Dict[str, int]
    top_hints: List[JSONDict]
    potential_savings_eur: float
    generated_at: str


class HintStatusUpdateRequest(BaseModel):
    """Request fuer Hint-Status Update."""
    status: HintStatus


class HintRuleResponse(BaseModel):
    """Hint-Regel Response."""
    id: UUID
    company_id: UUID
    name: str
    category: str
    source_type: str
    is_active: bool
    threshold_config: JSONDict
    schedule: Optional[str]
    created_at: str
    updated_at: Optional[str]

    model_config = {"from_attributes": True}


class HintRuleUpdateRequest(BaseModel):
    """Request fuer Hint-Regel Update."""
    is_active: Optional[bool] = None
    threshold_config: Optional[JSONDict] = None
    schedule: Optional[str] = None


class HintStatisticsResponse(BaseModel):
    """Hint-Statistiken Response."""
    id: UUID
    company_id: UUID
    period_start: str
    period_end: str
    total_hints: int
    hints_by_category: Dict[str, int]
    action_rate: float
    avg_response_time_hours: float
    estimated_savings: float
    created_at: str

    model_config = {"from_attributes": True}


class GenerateHintsResponse(BaseModel):
    """Response fuer manuelle Hint-Generierung."""
    hints_created: int
    message: str


# =============================================================================
# Helper: Hint -> Response
# =============================================================================


def _hint_to_response(hint: object) -> HintResponse:
    """Konvertiert ProactiveHint ORM-Objekt zu Response."""
    return HintResponse(
        id=hint.id,
        company_id=hint.company_id,
        user_id=hint.user_id,
        category=hint.category,
        priority=hint.priority,
        status=hint.status,
        title=hint.title,
        message=hint.message,
        urgency_score=hint.urgency_score or 0.0,
        value_score=hint.value_score or 0.0,
        combined_score=hint.combined_score or 0.0,
        source_type=hint.source_type,
        source_id=hint.source_id,
        source_metadata=hint.source_metadata or {},
        action_url=hint.action_url,
        action_label=hint.action_label,
        expires_at=hint.expires_at.isoformat() if hint.expires_at else None,
        seen_at=hint.seen_at.isoformat() if hint.seen_at else None,
        acknowledged_at=hint.acknowledged_at.isoformat() if hint.acknowledged_at else None,
        dismissed_at=hint.dismissed_at.isoformat() if hint.dismissed_at else None,
        created_at=hint.created_at.isoformat() if hint.created_at else "",
        updated_at=hint.updated_at.isoformat() if hint.updated_at else None,
    )


# =============================================================================
# API Endpoints
# =============================================================================


@router.get("/dashboard", response_model=DashboardSummaryResponse)
async def get_dashboard_summary(
    current_user: User = Depends(get_current_user),
    company_id: UUID = Depends(get_company_id),
    session: AsyncSession = Depends(get_db),
) -> DashboardSummaryResponse:
    """
    Dashboard-Widget: Tagesuebersicht der proaktiven Hinweise.

    Liefert Zaehler pro Kategorie, Top-5 dringendste Hints
    und potenzielle Ersparnisse.
    """
    service = get_proactive_assistant_service()
    summary = await service.get_dashboard_summary(session, company_id, current_user.id)
    return DashboardSummaryResponse(**summary)


@router.get("/hints", response_model=HintListResponse)
async def list_hints(
    category: Optional[HintCategory] = Query(None, description="Filter nach Kategorie"),
    hint_status: Optional[HintStatus] = Query(None, alias="status", description="Filter nach Status"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
    company_id: UUID = Depends(get_company_id),
    session: AsyncSession = Depends(get_db),
) -> HintListResponse:
    """
    Hinweise abrufen mit Filterung und Paginierung.

    Sortiert nach combined_score (dringendste zuerst).
    """
    service = get_proactive_assistant_service()

    hints, total = await service.get_hints(
        db=session,
        company_id=company_id,
        user_id=current_user.id,
        category=category,
        status=hint_status,
        limit=limit,
        offset=offset,
    )

    return HintListResponse(
        hints=[_hint_to_response(h) for h in hints],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.patch("/hints/{hint_id}/status", response_model=HintResponse)
async def update_hint_status(
    hint_id: UUID,
    request: HintStatusUpdateRequest,
    current_user: User = Depends(get_current_user),
    company_id: UUID = Depends(get_company_id),
    session: AsyncSession = Depends(get_db),
) -> HintResponse:
    """
    Hint-Status aktualisieren.

    Moegliche Status-Uebergaenge:
    - new -> seen, acknowledged, dismissed, acted_on
    - seen -> acknowledged, dismissed, acted_on
    - acknowledged -> acted_on, dismissed
    """
    service = get_proactive_assistant_service()

    hint = await service.update_hint_status(
        db=session,
        hint_id=hint_id,
        user_id=current_user.id,
        new_status=request.status,
    )

    if not hint:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Hinweis nicht gefunden",
        )

    await session.commit()
    return _hint_to_response(hint)


@router.get("/hints/context", response_model=List[HintResponse])
async def get_context_hints(
    document_id: Optional[UUID] = Query(None, description="Dokument-ID fuer Kontext"),
    entity_id: Optional[UUID] = Query(None, description="Entity-ID fuer Kontext"),
    current_user: User = Depends(get_current_user),
    company_id: UUID = Depends(get_company_id),
    session: AsyncSession = Depends(get_db),
) -> List[HintResponse]:
    """
    Kontext-Sidebar: Hints zum aktuellen Dokument oder Entity.

    Mindestens einer der Parameter document_id oder entity_id muss angegeben werden.
    """
    if not document_id and not entity_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Mindestens document_id oder entity_id muss angegeben werden",
        )

    service = get_proactive_assistant_service()
    hints = await service.get_context_hints(
        db=session,
        company_id=company_id,
        document_id=document_id,
        entity_id=entity_id,
    )
    return [_hint_to_response(h) for h in hints]


@router.get("/statistics", response_model=HintStatisticsResponse)
async def get_statistics(
    period_start: datetime = Query(..., description="Beginn des Zeitraums"),
    period_end: datetime = Query(..., description="Ende des Zeitraums"),
    current_user: User = Depends(get_current_user),
    company_id: UUID = Depends(get_company_id),
    session: AsyncSession = Depends(get_db),
) -> HintStatisticsResponse:
    """
    Hint-Statistiken fuer einen Zeitraum.

    Berechnet Zaehler, Action-Rate, Reaktionszeit und geschaetzte Ersparnisse.
    """
    service = get_proactive_assistant_service()
    stats = await service.calculate_statistics(
        db=session,
        company_id=company_id,
        period_start=period_start,
        period_end=period_end,
    )
    await session.commit()

    return HintStatisticsResponse(
        id=stats.id,
        company_id=stats.company_id,
        period_start=stats.period_start.isoformat() if stats.period_start else "",
        period_end=stats.period_end.isoformat() if stats.period_end else "",
        total_hints=stats.total_hints or 0,
        hints_by_category=stats.hints_by_category or {},
        action_rate=stats.action_rate or 0.0,
        avg_response_time_hours=stats.avg_response_time_hours or 0.0,
        estimated_savings=stats.estimated_savings or 0.0,
        created_at=stats.created_at.isoformat() if stats.created_at else "",
    )


@router.post("/generate", response_model=GenerateHintsResponse, status_code=status.HTTP_201_CREATED)
async def trigger_hint_generation(
    current_user: User = Depends(get_current_user),
    company_id: UUID = Depends(get_company_id),
    session: AsyncSession = Depends(get_db),
) -> GenerateHintsResponse:
    """
    Manuelle Hint-Generierung ausloesen (Admin).

    Fuehrt sofort eine vollstaendige Analyse fuer die aktuelle Firma durch.
    """
    service = get_proactive_assistant_service()
    hints = await service.generate_daily_hints(session, company_id)
    await session.commit()

    return GenerateHintsResponse(
        hints_created=len(hints),
        message=f"{len(hints)} neue Hinweise generiert",
    )


@router.get("/rules", response_model=List[HintRuleResponse])
async def list_rules(
    current_user: User = Depends(get_current_user),
    company_id: UUID = Depends(get_company_id),
    session: AsyncSession = Depends(get_db),
) -> List[HintRuleResponse]:
    """
    Hint-Regeln der aktuellen Firma auflisten.

    Zeigt alle konfigurierbaren Regeln mit Schwellwerten und Zeitplaenen.
    """
    service = get_proactive_assistant_service()
    rules = await service.get_rules(session, company_id)

    return [
        HintRuleResponse(
            id=r.id,
            company_id=r.company_id,
            name=r.name,
            category=r.category,
            source_type=r.source_type,
            is_active=r.is_active,
            threshold_config=r.threshold_config or {},
            schedule=r.schedule,
            created_at=r.created_at.isoformat() if r.created_at else "",
            updated_at=r.updated_at.isoformat() if r.updated_at else None,
        )
        for r in rules
    ]


@router.put("/rules/{rule_id}", response_model=HintRuleResponse)
async def update_rule(
    rule_id: UUID,
    request: HintRuleUpdateRequest,
    current_user: User = Depends(get_current_user),
    company_id: UUID = Depends(get_company_id),
    session: AsyncSession = Depends(get_db),
) -> HintRuleResponse:
    """
    Hint-Regel konfigurieren.

    Ermoeglicht das Aktivieren/Deaktivieren von Regeln und
    die Anpassung von Schwellwerten.
    """
    service = get_proactive_assistant_service()
    rule = await service.update_rule(
        db=session,
        rule_id=rule_id,
        company_id=company_id,
        is_active=request.is_active,
        threshold_config=request.threshold_config,
        schedule=request.schedule,
    )

    if not rule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Regel nicht gefunden",
        )

    await session.commit()

    return HintRuleResponse(
        id=rule.id,
        company_id=rule.company_id,
        name=rule.name,
        category=rule.category,
        source_type=rule.source_type,
        is_active=rule.is_active,
        threshold_config=rule.threshold_config or {},
        schedule=rule.schedule,
        created_at=rule.created_at.isoformat() if rule.created_at else "",
        updated_at=rule.updated_at.isoformat() if rule.updated_at else None,
    )
