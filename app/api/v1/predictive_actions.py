# -*- coding: utf-8 -*-
"""
API Endpoints fuer PredictiveActionService.

Proaktive Handlungsvorschlaege fuer Benutzer:
- Aktionsvorschlaege abrufen
- Aktionen akzeptieren/ablehnen/verschieben
- Statistiken und Feedback

Phase 2.2 der Feature-Roadmap (Januar 2026)
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional

from app.core.types import JSONDict
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_active_user, get_db
from app.middleware.company_context import require_company
from app.core.datetime_utils import utc_now
from app.db.models import User, Company
from app.services.ai.predictive_action_service import (
    ActionPriority,
    ActionStatus,
    ActionType,
    PredictiveAction,
    TriggerType,
    get_predictive_action_service,
)

import structlog

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/predictive-actions", tags=["Predictive Actions"])


# ============================================================================
# Schemas
# ============================================================================


class ActionMetadata(BaseModel):
    """Zusaetzliche Metadaten einer Aktion."""

    invoice_number: Optional[str] = None
    amount: Optional[float] = None
    days_overdue: Optional[int] = None
    days_remaining: Optional[int] = None
    skonto_percentage: Optional[float] = None
    skonto_amount: Optional[float] = None
    skonto_deadline: Optional[str] = None
    contract_name: Optional[str] = None
    budget_name: Optional[str] = None
    utilization_percent: Optional[float] = None

    class Config:
        extra = "allow"


class PredictiveActionResponse(BaseModel):
    """Antwort-Schema fuer eine einzelne Aktion."""

    id: str
    action_type: str
    trigger_type: str
    priority: str

    title: str
    description: str
    benefit_text: str

    target_id: str
    target_type: str

    confidence: float
    deadline: Optional[datetime] = None
    suggested_action_time: Optional[datetime] = None

    status: str
    created_at: datetime

    metadata: JSONDict = Field(default_factory=dict)

    class Config:
        from_attributes = True

    @classmethod
    def from_domain(cls, action: PredictiveAction) -> "PredictiveActionResponse":
        """Konvertiere Domain-Objekt zu Response."""
        return cls(
            id=str(action.id),
            action_type=action.action_type.value,
            trigger_type=action.trigger_type.value,
            priority=action.priority.value,
            title=action.title,
            description=action.description,
            benefit_text=action.benefit_text,
            target_id=str(action.target_id),
            target_type=action.target_type,
            confidence=action.confidence,
            deadline=action.deadline,
            suggested_action_time=action.suggested_action_time,
            status=action.status.value,
            created_at=action.created_at,
            metadata=action.metadata,
        )


class PredictiveActionsListResponse(BaseModel):
    """Liste von Aktionsvorschlaegen."""

    actions: List[PredictiveActionResponse]
    total: int
    summary: Dict[str, int] = Field(default_factory=dict)


class AcceptActionRequest(BaseModel):
    """Request zum Akzeptieren einer Aktion."""

    execute_immediately: bool = Field(
        default=False,
        description="Aktion direkt ausfuehren wenn moeglich",
    )


class RejectActionRequest(BaseModel):
    """Request zum Ablehnen einer Aktion."""

    reason: Optional[str] = Field(
        default=None,
        description="Optionaler Ablehnungsgrund",
        max_length=500,
    )


class SnoozeActionRequest(BaseModel):
    """Request zum Verschieben einer Aktion."""

    snooze_hours: int = Field(
        default=24,
        ge=1,
        le=168,  # Max 1 Woche
        description="Stunden bis zur erneuten Anzeige",
    )


class ActionResultResponse(BaseModel):
    """Ergebnis einer Aktions-Operation."""

    success: bool
    message: str
    action_id: str
    new_status: str
    snooze_until: Optional[datetime] = None


class ActionStatisticsResponse(BaseModel):
    """Statistiken zu Aktionsvorschlaegen."""

    period_start: datetime
    period_end: datetime

    total_suggested: int
    total_accepted: int
    total_rejected: int
    total_snoozed: int

    acceptance_rate: float
    effectiveness_rate: float

    estimated_savings: float
    realized_savings: float

    by_action_type: Dict[str, int]
    by_priority: Dict[str, int]


class UserPreferencesRequest(BaseModel):
    """Benutzer-Praeferenzen fuer Aktionsvorschlaege."""

    enabled_triggers: Optional[List[str]] = None
    notification_channels: Optional[List[str]] = None
    min_confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    min_savings_threshold: Optional[float] = Field(default=None, ge=0.0)
    default_snooze_hours: Optional[int] = Field(default=None, ge=1, le=168)


# ============================================================================
# Endpoints
# ============================================================================


@router.get(
    "",
    response_model=PredictiveActionsListResponse,
    summary="Aktionsvorschlaege abrufen",
    description="Ruft alle relevanten Aktionsvorschlaege fuer die aktuelle Firma ab.",
)
async def get_predictive_actions(
    limit: int = Query(default=20, ge=1, le=100, description="Maximale Anzahl"),
    action_types: Optional[str] = Query(
        default=None,
        description="Komma-separierte Liste von Aktionstypen",
    ),
    min_priority: Optional[str] = Query(
        default=None,
        description="Minimale Prioritaet (critical, high, medium, low)",
    ),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company: Company = Depends(require_company),
) -> PredictiveActionsListResponse:
    """Hole alle relevanten Aktionsvorschlaege."""
    service = get_predictive_action_service()

    # Parse Filter
    action_type_list: Optional[List[ActionType]] = None
    if action_types:
        try:
            action_type_list = [ActionType(t.strip()) for t in action_types.split(",")]
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Ungueltiger Aktionstyp: {e}",
            )

    priority_filter: Optional[ActionPriority] = None
    if min_priority:
        try:
            priority_filter = ActionPriority(min_priority)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Ungueltige Prioritaet: {min_priority}",
            )

    # Aktionen generieren
    actions = await service.get_pending_actions(
        db=db,
        company_id=company.id,
        user_id=current_user.id,
        limit=limit,
        action_types=action_type_list,
        min_priority=priority_filter,
    )

    # Zusammenfassung erstellen
    summary = {
        "critical": sum(1 for a in actions if a.priority == ActionPriority.CRITICAL),
        "high": sum(1 for a in actions if a.priority == ActionPriority.HIGH),
        "medium": sum(1 for a in actions if a.priority == ActionPriority.MEDIUM),
        "low": sum(1 for a in actions if a.priority == ActionPriority.LOW),
    }

    return PredictiveActionsListResponse(
        actions=[PredictiveActionResponse.from_domain(a) for a in actions],
        total=len(actions),
        summary=summary,
    )


@router.get(
    "/critical",
    response_model=PredictiveActionsListResponse,
    summary="Kritische Aktionen abrufen",
    description="Ruft nur kritische und hochpriorisierte Aktionen ab.",
)
async def get_critical_actions(
    limit: int = Query(default=10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company: Company = Depends(require_company),
) -> PredictiveActionsListResponse:
    """Hole kritische Aktionen fuer Dashboard-Widget."""
    service = get_predictive_action_service()

    actions = await service.get_pending_actions(
        db=db,
        company_id=company.id,
        user_id=current_user.id,
        limit=limit,
        min_priority=ActionPriority.HIGH,
    )

    summary = {
        "critical": sum(1 for a in actions if a.priority == ActionPriority.CRITICAL),
        "high": sum(1 for a in actions if a.priority == ActionPriority.HIGH),
    }

    return PredictiveActionsListResponse(
        actions=[PredictiveActionResponse.from_domain(a) for a in actions],
        total=len(actions),
        summary=summary,
    )


@router.get(
    "/skonto",
    response_model=PredictiveActionsListResponse,
    summary="Skonto-Vorschlaege abrufen",
    description="Ruft nur Skonto-relevante Aktionsvorschlaege ab.",
)
async def get_skonto_actions(
    limit: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company: Company = Depends(require_company),
) -> PredictiveActionsListResponse:
    """Hole Skonto-spezifische Vorschlaege."""
    service = get_predictive_action_service()

    actions = await service.get_pending_actions(
        db=db,
        company_id=company.id,
        user_id=current_user.id,
        limit=limit,
        action_types=[ActionType.USE_SKONTO],
    )

    # Berechne Gesamtersparnis
    total_savings = sum(
        a.metadata.get("skonto_amount", 0)
        for a in actions
    )

    summary = {
        "total_potential_savings": total_savings,
        "expiring_today": sum(1 for a in actions if a.metadata.get("days_remaining", 99) <= 1),
        "expiring_this_week": sum(1 for a in actions if a.metadata.get("days_remaining", 99) <= 7),
    }

    return PredictiveActionsListResponse(
        actions=[PredictiveActionResponse.from_domain(a) for a in actions],
        total=len(actions),
        summary=summary,
    )


@router.get(
    "/dunning",
    response_model=PredictiveActionsListResponse,
    summary="Mahnungs-Vorschlaege abrufen",
    description="Ruft nur Mahnungs-relevante Aktionsvorschlaege ab.",
)
async def get_dunning_actions(
    limit: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company: Company = Depends(require_company),
) -> PredictiveActionsListResponse:
    """Hole Mahnungs-spezifische Vorschlaege."""
    service = get_predictive_action_service()

    actions = await service.get_pending_actions(
        db=db,
        company_id=company.id,
        user_id=current_user.id,
        limit=limit,
        action_types=[ActionType.SEND_DUNNING, ActionType.CALL_CUSTOMER],
    )

    # Berechne Gesamtbetrag offener Forderungen
    total_outstanding = sum(
        a.metadata.get("amount", 0)
        for a in actions
    )

    summary = {
        "total_outstanding": total_outstanding,
        "critical_count": sum(1 for a in actions if a.priority == ActionPriority.CRITICAL),
        "needs_call": sum(1 for a in actions if a.action_type == ActionType.CALL_CUSTOMER),
    }

    return PredictiveActionsListResponse(
        actions=[PredictiveActionResponse.from_domain(a) for a in actions],
        total=len(actions),
        summary=summary,
    )


@router.post(
    "/{action_id}/accept",
    response_model=ActionResultResponse,
    summary="Aktion akzeptieren",
    description="Akzeptiert einen Aktionsvorschlag. Optional kann die Aktion direkt ausgefuehrt werden.",
)
async def accept_action(
    action_id: str,
    request: AcceptActionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company: Company = Depends(require_company),
) -> ActionResultResponse:
    """Akzeptiere eine vorgeschlagene Aktion."""
    service = get_predictive_action_service()

    # Regeneriere Aktionen um die richtige zu finden
    # In Produktion: Aus Datenbank laden
    actions = await service.generate_actions_for_company(db, company.id, current_user.id)

    action = next((a for a in actions if str(a.id) == action_id), None)

    if not action:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Aktion nicht gefunden oder nicht mehr aktuell",
        )

    success, message = await service.accept_action(
        db=db,
        action=action,
        user_id=current_user.id,
        execute_action=request.execute_immediately,
    )

    await db.commit()

    logger.info(
        "predictive_action_accepted_via_api",
        action_id=action_id,
        user_id=str(current_user.id),
        executed=request.execute_immediately,
    )

    return ActionResultResponse(
        success=success,
        message=message,
        action_id=action_id,
        new_status=action.status.value,
    )


@router.post(
    "/{action_id}/reject",
    response_model=ActionResultResponse,
    summary="Aktion ablehnen",
    description="Lehnt einen Aktionsvorschlag ab. Optional mit Begruendung.",
)
async def reject_action(
    action_id: str,
    request: RejectActionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company: Company = Depends(require_company),
) -> ActionResultResponse:
    """Lehne eine vorgeschlagene Aktion ab."""
    service = get_predictive_action_service()

    actions = await service.generate_actions_for_company(db, company.id, current_user.id)
    action = next((a for a in actions if str(a.id) == action_id), None)

    if not action:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Aktion nicht gefunden oder nicht mehr aktuell",
        )

    success = await service.reject_action(
        db=db,
        action=action,
        user_id=current_user.id,
        reason=request.reason,
    )

    await db.commit()

    logger.info(
        "predictive_action_rejected_via_api",
        action_id=action_id,
        user_id=str(current_user.id),
        reason=request.reason,
    )

    return ActionResultResponse(
        success=success,
        message="Aktion abgelehnt",
        action_id=action_id,
        new_status=ActionStatus.REJECTED.value,
    )


@router.post(
    "/{action_id}/snooze",
    response_model=ActionResultResponse,
    summary="Aktion verschieben",
    description="Verschiebt einen Aktionsvorschlag auf spaeter.",
)
async def snooze_action(
    action_id: str,
    request: SnoozeActionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company: Company = Depends(require_company),
) -> ActionResultResponse:
    """Verschiebe eine Aktion auf spaeter."""
    service = get_predictive_action_service()

    actions = await service.generate_actions_for_company(db, company.id, current_user.id)
    action = next((a for a in actions if str(a.id) == action_id), None)

    if not action:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Aktion nicht gefunden oder nicht mehr aktuell",
        )

    snooze_until = await service.snooze_action(
        db=db,
        action=action,
        user_id=current_user.id,
        snooze_hours=request.snooze_hours,
    )

    await db.commit()

    logger.info(
        "predictive_action_snoozed_via_api",
        action_id=action_id,
        user_id=str(current_user.id),
        snooze_until=snooze_until.isoformat(),
    )

    return ActionResultResponse(
        success=True,
        message=f"Aktion verschoben bis {snooze_until.strftime('%d.%m.%Y %H:%M')}",
        action_id=action_id,
        new_status=ActionStatus.SNOOZED.value,
        snooze_until=snooze_until,
    )


@router.get(
    "/statistics",
    response_model=ActionStatisticsResponse,
    summary="Aktions-Statistiken abrufen",
    description="Ruft Statistiken zu Aktionsvorschlaegen ab.",
)
async def get_action_statistics(
    days: int = Query(default=30, ge=1, le=365, description="Anzahl Tage zurueck"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company: Company = Depends(require_company),
) -> ActionStatisticsResponse:
    """Hole Statistiken zu Aktionsvorschlaegen."""
    service = get_predictive_action_service()

    end_date = utc_now()
    start_date = end_date - timedelta(days=days)

    stats = await service.get_action_statistics(
        db=db,
        company_id=company.id,
        start_date=start_date,
        end_date=end_date,
    )

    return ActionStatisticsResponse(
        period_start=stats.period_start,
        period_end=stats.period_end,
        total_suggested=stats.total_suggested,
        total_accepted=stats.total_accepted,
        total_rejected=stats.total_rejected,
        total_snoozed=stats.total_snoozed,
        acceptance_rate=stats.acceptance_rate,
        effectiveness_rate=stats.effectiveness_rate,
        estimated_savings=float(stats.estimated_savings),
        realized_savings=float(stats.realized_savings),
        by_action_type={},
        by_priority={},
    )


@router.get(
    "/types",
    response_model=Dict[str, List[str]],
    summary="Verfuegbare Typen abrufen",
    description="Listet alle verfuegbaren Aktions- und Trigger-Typen auf.",
)
async def get_action_types(
    current_user: User = Depends(get_current_active_user),
) -> Dict[str, List[str]]:
    """Hole verfuegbare Typen fuer Filter."""
    return {
        "action_types": [t.value for t in ActionType],
        "trigger_types": [t.value for t in TriggerType],
        "priorities": [p.value for p in ActionPriority],
        "statuses": [s.value for s in ActionStatus],
    }
