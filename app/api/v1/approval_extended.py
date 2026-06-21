# -*- coding: utf-8 -*-
"""
Erweiterte Approval API Endpoints.

Feature #3: Approval Workflow Depth
- Bedingte Genehmigungsregeln (CRUD + Evaluation)
- Eskalationsregeln (CRUD)
- Stellvertretungen (CRUD + Aktivierung)
- SLA-Dashboard und Bottleneck-Analyse
"""

import structlog
from datetime import datetime
from typing import Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, ConfigDict, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user, get_db, get_user_company_id_dep
from app.db.models import User
from app.db.models_approval_extended import (
    ConditionalApprovalRule,
    EscalationRule,
    SubstitutionRule,
)
from app.services.approval.conditional_logic_service import (
    ConditionalLogicService,
)
from app.services.approval.escalation_service import EscalationService
from app.services.approval.sla_monitoring_service import SLAMonitoringService

logger = structlog.get_logger(__name__)

router = APIRouter(
    prefix="/approvals/extended",
    tags=["approvals-extended"],
)


# =============================================================================
# SCHEMAS - Bedingte Regeln
# =============================================================================


class ConditionSchema(BaseModel):
    """Schema für eine einzelne Bedingung."""

    field: str = Field(
        ...,
        min_length=1,
        description="Feldname (z.B. amount, supplier_risk_score)",
    )
    operator: str = Field(
        ...,
        description="Operator: gt, gte, lt, lte, eq, neq, in, not_in",
    )
    value: object = Field(
        ...,
        description="Vergleichswert",
    )

    @field_validator("operator")
    @classmethod
    def validate_operator(cls, v: str) -> str:
        allowed = {"gt", "gte", "lt", "lte", "eq", "neq", "in", "not_in"}
        if v not in allowed:
            raise ValueError(
                f"Ungültiger Operator: {v}. "
                f"Erlaubt: {', '.join(sorted(allowed))}"
            )
        return v


class ApproverSchema(BaseModel):
    """Schema für einen zusätzlichen Genehmiger."""

    type: str = Field(
        ...,
        description="Typ: user oder role",
    )
    value: str = Field(
        ...,
        min_length=1,
        description="User-ID oder Rollenname",
    )


class ConditionalRuleCreateRequest(BaseModel):
    """Request zum Erstellen einer bedingten Genehmigungsregel."""

    name: str = Field(
        ...,
        min_length=1,
        max_length=200,
        description="Name der Regel",
    )
    description: Optional[str] = Field(
        None,
        description="Optionale Beschreibung",
    )
    conditions: List[ConditionSchema] = Field(
        ...,
        min_length=1,
        description="Liste der Bedingungen",
    )
    additional_approvers: List[ApproverSchema] = Field(
        ...,
        min_length=1,
        description="Zusätzliche Genehmiger",
    )
    priority_override: Optional[str] = Field(
        None,
        description="Optionale Prioritaets-Überschreibung",
    )
    is_active: bool = Field(
        True,
        description="Ob die Regel aktiv ist",
    )


class ConditionalRuleResponse(BaseModel):
    """Response für eine bedingte Genehmigungsregel."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    company_id: UUID
    name: str
    description: Optional[str]
    is_active: bool
    conditions: List[Dict[str, object]]
    additional_approvers: List[Dict[str, str]]
    priority_override: Optional[str]
    created_at: Optional[datetime]
    updated_at: Optional[datetime]


# =============================================================================
# SCHEMAS - Eskalationsregeln
# =============================================================================


class EscalationRuleCreateRequest(BaseModel):
    """Request zum Erstellen einer Eskalationsregel."""

    name: str = Field(
        ...,
        min_length=1,
        max_length=200,
        description="Name der Regel",
    )
    timeout_hours: int = Field(
        48,
        ge=1,
        description="Timeout in Stunden bis Eskalation",
    )
    escalation_target_user_id: Optional[UUID] = Field(
        None,
        description="Eskalationsziel: User-ID",
    )
    escalation_target_role: Optional[str] = Field(
        None,
        description="Eskalationsziel: Rollenname",
    )
    send_email: bool = Field(
        True,
        description="E-Mail-Benachrichtigung senden",
    )
    send_notification: bool = Field(
        True,
        description="In-App-Benachrichtigung senden",
    )
    is_active: bool = Field(
        True,
        description="Ob die Regel aktiv ist",
    )


class EscalationRuleResponse(BaseModel):
    """Response für eine Eskalationsregel."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    company_id: UUID
    name: str
    timeout_hours: int
    escalation_target_user_id: Optional[UUID]
    escalation_target_role: Optional[str]
    send_email: bool
    send_notification: bool
    is_active: bool
    created_at: Optional[datetime]
    updated_at: Optional[datetime]


# =============================================================================
# SCHEMAS - Stellvertretung
# =============================================================================


class SubstitutionCreateRequest(BaseModel):
    """Request zum Erstellen einer Stellvertretung."""

    user_id: UUID = Field(
        ...,
        description="ID des abwesenden Users",
    )
    substitute_user_id: UUID = Field(
        ...,
        description="ID des Stellvertreters",
    )
    valid_from: datetime = Field(
        ...,
        description="Beginn der Vertretung",
    )
    valid_until: datetime = Field(
        ...,
        description="Ende der Vertretung",
    )
    reason: Optional[str] = Field(
        None,
        max_length=200,
        description="Grund (z.B. Urlaub, Krankheit)",
    )


class SubstitutionResponse(BaseModel):
    """Response für eine Stellvertretung."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    company_id: UUID
    user_id: UUID
    substitute_user_id: UUID
    valid_from: datetime
    valid_until: datetime
    reason: Optional[str]
    is_active: bool
    auto_activated: bool
    created_at: Optional[datetime]
    updated_at: Optional[datetime]


# =============================================================================
# SCHEMAS - SLA
# =============================================================================


class SLADashboardResponse(BaseModel):
    """Response für SLA-Dashboard."""

    avg_approval_hours: float
    median_approval_hours: float
    total_requests_period: int
    total_completed_period: int
    sla_compliance_rate: float
    sla_breaches: int
    overdue_count: int
    bottleneck_users: List[Dict[str, object]]


class SLABreachResponse(BaseModel):
    """Response für eine SLA-Verletzung."""

    request_id: str
    title: Optional[str]
    entity_type: Optional[str]
    current_step: Optional[int]
    total_steps: Optional[int]
    created_at: Optional[str]
    due_date: Optional[str]
    wait_hours: float
    overdue_hours: float
    priority: str
    is_escalated: bool


# =============================================================================
# ENDPOINTS - Bedingte Regeln
# =============================================================================


@router.get(
    "/conditional-rules",
    response_model=List[ConditionalRuleResponse],
    summary="Bedingte Regeln auflisten",
)
async def list_conditional_rules(
    active_only: bool = Query(True, description="Nur aktive Regeln"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    company_id: UUID = Depends(get_user_company_id_dep),
) -> List[ConditionalRuleResponse]:
    """Listet alle bedingten Genehmigungsregeln der Firma auf."""
    service = ConditionalLogicService(db)
    rules = await service._get_active_rules(company_id)

    if not active_only:
        from sqlalchemy import select

        stmt = select(ConditionalApprovalRule).where(
            ConditionalApprovalRule.company_id == company_id
        )
        result = await db.execute(stmt)
        rules = result.scalars().all()

    return [ConditionalRuleResponse.model_validate(r) for r in rules]


@router.post(
    "/conditional-rules",
    response_model=ConditionalRuleResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Bedingte Regel erstellen",
)
async def create_conditional_rule(
    request: ConditionalRuleCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    company_id: UUID = Depends(get_user_company_id_dep),
) -> ConditionalRuleResponse:
    """Erstellt eine neue bedingte Genehmigungsregel."""
    rule = ConditionalApprovalRule(
        company_id=company_id,
        name=request.name,
        description=request.description,
        is_active=request.is_active,
        conditions=[c.model_dump() for c in request.conditions],
        additional_approvers=[
            a.model_dump() for a in request.additional_approvers
        ],
        priority_override=request.priority_override,
    )

    db.add(rule)
    await db.commit()
    await db.refresh(rule)

    logger.info(
        "conditional_rule_created",
        rule_id=str(rule.id),
        name=rule.name,
        user_id=str(current_user.id),
    )

    return ConditionalRuleResponse.model_validate(rule)


@router.delete(
    "/conditional-rules/{rule_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Bedingte Regel löschen",
)
async def delete_conditional_rule(
    rule_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    company_id: UUID = Depends(get_user_company_id_dep),
) -> None:
    """Löscht eine bedingte Genehmigungsregel."""
    from sqlalchemy import and_, select

    stmt = select(ConditionalApprovalRule).where(
        and_(
            ConditionalApprovalRule.id == rule_id,
            ConditionalApprovalRule.company_id == company_id,
        )
    )
    result = await db.execute(stmt)
    rule = result.scalar_one_or_none()

    if not rule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Bedingte Regel nicht gefunden",
        )

    await db.delete(rule)
    await db.commit()

    logger.info(
        "conditional_rule_deleted",
        rule_id=str(rule_id),
        user_id=str(current_user.id),
    )


# =============================================================================
# ENDPOINTS - Eskalationsregeln
# =============================================================================


@router.get(
    "/escalation-rules",
    response_model=List[EscalationRuleResponse],
    summary="Eskalationsregeln auflisten",
)
async def list_escalation_rules(
    active_only: bool = Query(True, description="Nur aktive Regeln"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    company_id: UUID = Depends(get_user_company_id_dep),
) -> List[EscalationRuleResponse]:
    """Listet alle Eskalationsregeln der Firma auf."""
    service = EscalationService(db)
    rules = await service.get_escalation_rules(
        company_id, active_only=active_only
    )
    return [EscalationRuleResponse.model_validate(r) for r in rules]


@router.post(
    "/escalation-rules",
    response_model=EscalationRuleResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Eskalationsregel erstellen",
)
async def create_escalation_rule(
    request: EscalationRuleCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    company_id: UUID = Depends(get_user_company_id_dep),
) -> EscalationRuleResponse:
    """Erstellt eine neue Eskalationsregel."""
    if (
        not request.escalation_target_user_id
        and not request.escalation_target_role
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "Mindestens ein Eskalationsziel muss angegeben werden "
                "(User-ID oder Rolle)"
            ),
        )

    # Validierung: Ziel-User muss existieren (verhindert FK-Violation -> 500).
    if request.escalation_target_user_id is not None:
        from sqlalchemy import select as _select

        target_exists = await db.execute(
            _select(User.id).where(User.id == request.escalation_target_user_id)
        )
        if target_exists.scalar_one_or_none() is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Ungueltige escalation_target_user_id: Benutzer nicht gefunden",
            )

    rule = EscalationRule(
        company_id=company_id,
        name=request.name,
        timeout_hours=request.timeout_hours,
        escalation_target_user_id=request.escalation_target_user_id,
        escalation_target_role=request.escalation_target_role,
        send_email=request.send_email,
        send_notification=request.send_notification,
        is_active=request.is_active,
    )

    db.add(rule)
    await db.commit()
    await db.refresh(rule)

    logger.info(
        "escalation_rule_created",
        rule_id=str(rule.id),
        name=rule.name,
        timeout_hours=rule.timeout_hours,
        user_id=str(current_user.id),
    )

    return EscalationRuleResponse.model_validate(rule)


@router.delete(
    "/escalation-rules/{rule_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Eskalationsregel löschen",
)
async def delete_escalation_rule(
    rule_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    company_id: UUID = Depends(get_user_company_id_dep),
) -> None:
    """Löscht eine Eskalationsregel."""
    from sqlalchemy import and_, select

    stmt = select(EscalationRule).where(
        and_(
            EscalationRule.id == rule_id,
            EscalationRule.company_id == company_id,
        )
    )
    result = await db.execute(stmt)
    rule = result.scalar_one_or_none()

    if not rule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Eskalationsregel nicht gefunden",
        )

    await db.delete(rule)
    await db.commit()

    logger.info(
        "escalation_rule_deleted",
        rule_id=str(rule_id),
        user_id=str(current_user.id),
    )


# =============================================================================
# ENDPOINTS - Stellvertretung
# =============================================================================


@router.get(
    "/substitutions",
    response_model=List[SubstitutionResponse],
    summary="Stellvertretungen auflisten",
)
async def list_substitutions(
    active_only: bool = Query(True, description="Nur aktive Vertretungen"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    company_id: UUID = Depends(get_user_company_id_dep),
) -> List[SubstitutionResponse]:
    """Listet alle Stellvertretungen der Firma auf."""
    service = EscalationService(db)
    rules = await service.get_substitution_rules(
        company_id, active_only=active_only
    )
    return [SubstitutionResponse.model_validate(r) for r in rules]


@router.post(
    "/substitutions",
    response_model=SubstitutionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Stellvertretung erstellen",
)
async def create_substitution(
    request: SubstitutionCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    company_id: UUID = Depends(get_user_company_id_dep),
) -> SubstitutionResponse:
    """Erstellt eine neue Stellvertretung."""
    service = EscalationService(db)

    try:
        rule = await service.create_substitution(
            company_id=company_id,
            user_id=request.user_id,
            substitute_user_id=request.substitute_user_id,
            valid_from=request.valid_from,
            valid_until=request.valid_until,
            reason=request.reason,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        )

    return SubstitutionResponse.model_validate(rule)


@router.delete(
    "/substitutions/{rule_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Stellvertretung löschen",
)
async def delete_substitution(
    rule_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    company_id: UUID = Depends(get_user_company_id_dep),
) -> None:
    """Löscht eine Stellvertretung."""
    service = EscalationService(db)
    deleted = await service.delete_substitution(
        rule_id, company_id
    )

    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Stellvertretung nicht gefunden",
        )


@router.get(
    "/substitutions/active/{user_id}",
    summary="Aktive Stellvertretung für User",
)
async def get_active_substitution(
    user_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    company_id: UUID = Depends(get_user_company_id_dep),
) -> Dict[str, object]:
    """Findet die aktive Stellvertretung für einen User."""
    service = EscalationService(db)
    sub = await service.find_substitute(
        db, user_id, company_id
    )

    if not sub:
        return {"has_substitute": False}

    return {
        "has_substitute": True,
        "original_user_id": str(sub.original_user_id),
        "substitute_user_id": str(sub.substitute_user_id),
        "reason": sub.reason,
        "valid_from": (
            sub.valid_from.isoformat() if sub.valid_from else None
        ),
        "valid_until": (
            sub.valid_until.isoformat() if sub.valid_until else None
        ),
    }


# =============================================================================
# ENDPOINTS - SLA Dashboard & Bottlenecks
# =============================================================================


@router.get(
    "/sla/dashboard",
    response_model=SLADashboardResponse,
    summary="SLA-Dashboard",
)
async def get_sla_dashboard(
    period_days: int = Query(30, ge=1, le=365, description="Zeitraum in Tagen"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    company_id: UUID = Depends(get_user_company_id_dep),
) -> SLADashboardResponse:
    """Liefert SLA-Dashboard-Daten mit Metriken und Compliance-Rate."""
    service = SLAMonitoringService(db)
    dashboard = await service.get_sla_dashboard(
        db, company_id, period_days
    )

    return SLADashboardResponse(
        avg_approval_hours=dashboard.avg_approval_hours,
        median_approval_hours=dashboard.median_approval_hours,
        total_requests_period=dashboard.total_requests_period,
        total_completed_period=dashboard.total_completed_period,
        sla_compliance_rate=dashboard.sla_compliance_rate,
        sla_breaches=dashboard.sla_breaches,
        overdue_count=dashboard.overdue_count,
        bottleneck_users=dashboard.bottleneck_users,
    )


@router.get(
    "/sla/breaches",
    response_model=List[SLABreachResponse],
    summary="Aktuelle SLA-Verletzungen",
)
async def get_sla_breaches(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    company_id: UUID = Depends(get_user_company_id_dep),
) -> List[SLABreachResponse]:
    """Listet alle aktuellen SLA-Verletzungen auf."""
    service = SLAMonitoringService(db)
    breaches = await service.check_sla_breaches(
        db, company_id
    )

    return [
        SLABreachResponse(**breach)
        for breach in breaches
    ]


@router.get(
    "/sla/bottlenecks",
    summary="Bottleneck-Analyse",
)
async def get_sla_bottlenecks(
    period_days: int = Query(30, ge=1, le=365, description="Zeitraum in Tagen"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    company_id: UUID = Depends(get_user_company_id_dep),
) -> List[Dict[str, object]]:
    """Detaillierte Bottleneck-Analyse: Langsamste Genehmiger."""
    service = SLAMonitoringService(db)
    return await service.get_bottleneck_analysis(
        db, company_id, period_days
    )
