# -*- coding: utf-8 -*-
"""
Enhanced Approval + Automation 2.0 API Endpoints.

Feature #3: Approval Workflow Depth
- Bedingte Genehmigungsregeln (ConditionalApprovalRule CRUD)
- Eskalationsregeln (EscalationRule CRUD)
- Stellvertretungen (SubstitutionRule CRUD)
- SLA-Dashboard und Bottleneck-Analyse

Feature #7: Automation 2.0
- Auto-Filing (Regeln + Ausfuehrung)
- Auto-Matching (Ausfuehrung + Bestaetigung)

Feinpoliert und durchdacht - Enterprise Workflow Automation.
"""

import structlog
from datetime import datetime
from typing import Dict, List, Optional
from uuid import UUID

from app.core.types import JSONDict
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, ConfigDict, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user, get_db
from app.db.models import User
from app.core.safe_errors import safe_error_detail, safe_error_log

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/approval-enhanced", tags=["approval-enhanced"])


# =============================================================================
# SCHEMAS - Conditional Approval Rules
# =============================================================================


class ConditionSchema(BaseModel):
    """Schema fuer eine einzelne Bedingung."""
    field: str = Field(..., min_length=1, description="Feldname (z.B. amount, supplier_risk_score)")
    operator: str = Field(..., description="Operator: gt, lt, gte, lte, eq, neq, in, not_in, between, contains")
    value: object = Field(..., description="Schwellenwert")


class ApproverSchema(BaseModel):
    """Schema fuer einen zusaetzlichen Genehmiger."""
    type: str = Field(..., description="Typ: user oder role")
    value: str = Field(..., min_length=1, description="User-ID oder Rollenname")


class ConditionalRuleCreateRequest(BaseModel):
    """Request zum Erstellen einer bedingten Genehmigungsregel."""
    name: str = Field(..., min_length=1, max_length=200, description="Name der Regel")
    description: Optional[str] = Field(None, description="Beschreibung")
    conditions: List[ConditionSchema] = Field(
        ..., min_length=1, description="Liste der Bedingungen (alle muessen erfuellt sein)"
    )
    additional_approvers: List[ApproverSchema] = Field(
        ..., min_length=1, description="Zusaetzliche Genehmiger bei Match"
    )
    priority_override: Optional[str] = Field(
        None, description="Prioritaets-Ueberschreibung (low, normal, high, urgent)"
    )
    is_active: bool = Field(True, description="Ob die Regel aktiv ist")


class ConditionalRuleUpdateRequest(BaseModel):
    """Request zum Aktualisieren einer bedingten Genehmigungsregel."""
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = None
    conditions: Optional[List[ConditionSchema]] = Field(None, min_length=1)
    additional_approvers: Optional[List[ApproverSchema]] = Field(None, min_length=1)
    priority_override: Optional[str] = None
    is_active: Optional[bool] = None


class ConditionalRuleResponse(BaseModel):
    """Response fuer eine bedingte Genehmigungsregel."""
    model_config = ConfigDict(from_attributes=True)

    id: str
    company_id: str
    name: str
    description: Optional[str]
    conditions: List[Dict[str, object]]
    additional_approvers: List[Dict[str, object]]
    priority_override: Optional[str]
    is_active: bool
    created_at: str
    updated_at: str


# =============================================================================
# SCHEMAS - Escalation Rules
# =============================================================================


class EscalationRuleCreateRequest(BaseModel):
    """Request zum Erstellen einer Eskalationsregel."""
    name: str = Field(..., min_length=1, max_length=200, description="Name der Regel")
    timeout_hours: int = Field(48, ge=1, description="Timeout in Stunden bis zur Eskalation")
    escalation_target_user_id: Optional[str] = Field(
        None, description="Eskalationsziel: User-ID"
    )
    escalation_target_role: Optional[str] = Field(
        None, description="Eskalationsziel: Rollenname"
    )
    send_email: bool = Field(True, description="E-Mail senden")
    send_notification: bool = Field(True, description="Benachrichtigung senden")
    is_active: bool = Field(True, description="Ob die Regel aktiv ist")


class EscalationRuleResponse(BaseModel):
    """Response fuer eine Eskalationsregel."""
    model_config = ConfigDict(from_attributes=True)

    id: str
    company_id: str
    name: str
    timeout_hours: int
    escalation_target_user_id: Optional[str]
    escalation_target_role: Optional[str]
    send_email: bool
    send_notification: bool
    is_active: bool
    created_at: str
    updated_at: str


# =============================================================================
# SCHEMAS - Substitution Rules
# =============================================================================


class SubstitutionCreateRequest(BaseModel):
    """Request zum Erstellen einer Stellvertretungsregel."""
    user_id: str = Field(..., description="ID des abwesenden Users")
    substitute_user_id: str = Field(..., description="ID des Stellvertreters")
    valid_from: datetime = Field(..., description="Beginn der Vertretung")
    valid_until: datetime = Field(..., description="Ende der Vertretung")
    reason: Optional[str] = Field(
        None, max_length=200, description="Grund (z.B. Urlaub, Krankheit)"
    )


class SubstitutionResponse(BaseModel):
    """Response fuer eine Stellvertretungsregel."""
    model_config = ConfigDict(from_attributes=True)

    id: str
    company_id: str
    user_id: str
    substitute_user_id: str
    valid_from: str
    valid_until: str
    reason: Optional[str]
    is_active: bool
    auto_activated: bool
    created_at: str
    updated_at: str


# =============================================================================
# SCHEMAS - SLA
# =============================================================================


class SLADashboardResponse(BaseModel):
    """Response fuer SLA-Dashboard."""
    avg_approval_hours: float
    median_approval_hours: float
    total_requests_period: int
    total_completed_period: int
    sla_compliance_rate: float
    sla_breaches: int
    overdue_count: int
    bottleneck_users: List[Dict[str, object]]


# =============================================================================
# SCHEMAS - Auto-Filing
# =============================================================================


class AutoFilingRuleCreateRequest(BaseModel):
    """Request zum Erstellen einer Auto-Filing-Regel."""
    name: str = Field(..., min_length=1, max_length=200, description="Name der Regel")
    description: Optional[str] = Field(None, description="Beschreibung")
    model_type: str = Field("rule", description="Modelltyp: ml oder rule")
    confidence_threshold: float = Field(0.95, ge=0.0, le=1.0, description="Schwelle fuer Auto-Filing")
    target_folder_id: Optional[str] = Field(None, description="Zielordner-ID")
    target_category: Optional[str] = Field(None, max_length=100, description="Zielkategorie")
    config: Optional[JSONDict] = Field(None, description="Regelkonfiguration")
    is_active: bool = Field(True, description="Ob die Regel aktiv ist")

    @field_validator("model_type")
    @classmethod
    def validate_model_type(cls, v: str) -> str:
        if v not in ("ml", "rule"):
            raise ValueError("model_type muss 'ml' oder 'rule' sein")
        return v


class AutoFilingRuleResponse(BaseModel):
    """Response fuer eine Auto-Filing-Regel."""
    model_config = ConfigDict(from_attributes=True)

    id: str
    company_id: str
    name: str
    description: Optional[str]
    model_type: str
    confidence_threshold: float
    target_folder_id: Optional[str]
    target_category: Optional[str]
    training_sample_count: int
    accuracy: Optional[float]
    is_active: bool
    config: Optional[JSONDict]
    created_at: str
    updated_at: str


# =============================================================================
# SCHEMAS - Auto-Matching
# =============================================================================


class AutoMatchResponse(BaseModel):
    """Response fuer ein Auto-Match-Ergebnis."""
    model_config = ConfigDict(from_attributes=True)

    id: str
    company_id: str
    document_id: str
    matched_document_id: str
    match_type: str
    confidence: float
    match_details: Optional[JSONDict]
    is_confirmed: bool
    confirmed_by_user_id: Optional[str]
    created_at: str


class AutoMatchConfirmRequest(BaseModel):
    """Request zum Bestaetigen eines Matches."""
    match_id: str = Field(..., description="Match-ID")


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================


def _build_conditional_rule_response(rule: object) -> ConditionalRuleResponse:
    """Baut Response aus ConditionalApprovalRule."""
    return ConditionalRuleResponse(
        id=str(rule.id),
        company_id=str(rule.company_id),
        name=rule.name,
        description=rule.description,
        conditions=rule.conditions or [],
        additional_approvers=rule.additional_approvers or [],
        priority_override=rule.priority_override,
        is_active=rule.is_active,
        created_at=rule.created_at.isoformat() if rule.created_at else "",
        updated_at=rule.updated_at.isoformat() if rule.updated_at else "",
    )


def _build_escalation_rule_response(rule: object) -> EscalationRuleResponse:
    """Baut Response aus EscalationRule."""
    return EscalationRuleResponse(
        id=str(rule.id),
        company_id=str(rule.company_id),
        name=rule.name,
        timeout_hours=rule.timeout_hours,
        escalation_target_user_id=(
            str(rule.escalation_target_user_id)
            if rule.escalation_target_user_id
            else None
        ),
        escalation_target_role=rule.escalation_target_role,
        send_email=rule.send_email,
        send_notification=rule.send_notification,
        is_active=rule.is_active,
        created_at=rule.created_at.isoformat() if rule.created_at else "",
        updated_at=rule.updated_at.isoformat() if rule.updated_at else "",
    )


def _build_substitution_response(rule: object) -> SubstitutionResponse:
    """Baut Response aus SubstitutionRule."""
    return SubstitutionResponse(
        id=str(rule.id),
        company_id=str(rule.company_id),
        user_id=str(rule.user_id),
        substitute_user_id=str(rule.substitute_user_id),
        valid_from=rule.valid_from.isoformat() if rule.valid_from else "",
        valid_until=rule.valid_until.isoformat() if rule.valid_until else "",
        reason=rule.reason,
        is_active=rule.is_active,
        auto_activated=rule.auto_activated,
        created_at=rule.created_at.isoformat() if rule.created_at else "",
        updated_at=rule.updated_at.isoformat() if rule.updated_at else "",
    )


def _build_auto_filing_rule_response(rule: object) -> AutoFilingRuleResponse:
    """Baut Response aus AutoFilingRule."""
    return AutoFilingRuleResponse(
        id=str(rule.id),
        company_id=str(rule.company_id),
        name=rule.name,
        description=rule.description,
        model_type=rule.model_type,
        confidence_threshold=rule.confidence_threshold,
        target_folder_id=str(rule.target_folder_id) if rule.target_folder_id else None,
        target_category=rule.target_category,
        training_sample_count=rule.training_sample_count or 0,
        accuracy=rule.accuracy,
        is_active=rule.is_active,
        config=rule.config,
        created_at=rule.created_at.isoformat() if rule.created_at else "",
        updated_at=rule.updated_at.isoformat() if rule.updated_at else "",
    )


def _build_auto_match_response(match: object) -> AutoMatchResponse:
    """Baut Response aus AutoMatchResult."""
    return AutoMatchResponse(
        id=str(match.id),
        company_id=str(match.company_id),
        document_id=str(match.document_id),
        matched_document_id=str(match.matched_document_id),
        match_type=match.match_type,
        confidence=match.confidence,
        match_details=match.match_details,
        is_confirmed=match.is_confirmed,
        confirmed_by_user_id=(
            str(match.confirmed_by_user_id) if match.confirmed_by_user_id else None
        ),
        created_at=match.created_at.isoformat() if match.created_at else "",
    )


# =============================================================================
# ENDPOINTS - Conditional Approval Rules
# =============================================================================


@router.get(
    "/conditions",
    response_model=List[ConditionalRuleResponse],
    summary="Bedingte Genehmigungsregeln auflisten",
)
async def list_conditional_rules(
    active_only: bool = Query(True, description="Nur aktive Regeln"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> List[ConditionalRuleResponse]:
    """Listet alle bedingten Genehmigungsregeln der Firma auf."""
    from app.db.models_approval_extended import ConditionalApprovalRule
    from sqlalchemy import select, and_

    stmt = select(ConditionalApprovalRule).where(
        ConditionalApprovalRule.company_id == current_user.company_id
    )
    if active_only:
        stmt = stmt.where(ConditionalApprovalRule.is_active.is_(True))
    stmt = stmt.order_by(ConditionalApprovalRule.created_at.desc())

    result = await db.execute(stmt)
    rules = result.scalars().all()

    return [_build_conditional_rule_response(r) for r in rules]


@router.post(
    "/conditions",
    response_model=ConditionalRuleResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Bedingte Genehmigungsregel erstellen",
)
async def create_conditional_rule(
    request: ConditionalRuleCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ConditionalRuleResponse:
    """Erstellt eine neue bedingte Genehmigungsregel."""
    from app.db.models_approval_extended import ConditionalApprovalRule

    rule = ConditionalApprovalRule(
        company_id=current_user.company_id,
        name=request.name,
        description=request.description,
        conditions=[c.model_dump() for c in request.conditions],
        additional_approvers=[a.model_dump() for a in request.additional_approvers],
        priority_override=request.priority_override,
        is_active=request.is_active,
    )
    db.add(rule)
    await db.commit()
    await db.refresh(rule)

    logger.info(
        "conditional_rule_created",
        rule_id=str(rule.id),
        name=rule.name,
    )

    return _build_conditional_rule_response(rule)


@router.put(
    "/conditions/{rule_id}",
    response_model=ConditionalRuleResponse,
    summary="Bedingte Genehmigungsregel aktualisieren",
)
async def update_conditional_rule(
    rule_id: UUID,
    request: ConditionalRuleUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ConditionalRuleResponse:
    """Aktualisiert eine bedingte Genehmigungsregel."""
    from app.db.models_approval_extended import ConditionalApprovalRule
    from sqlalchemy import select, and_

    stmt = select(ConditionalApprovalRule).where(
        and_(
            ConditionalApprovalRule.id == rule_id,
            ConditionalApprovalRule.company_id == current_user.company_id,
        )
    )
    result = await db.execute(stmt)
    rule = result.scalar_one_or_none()

    if not rule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Bedingte Regel nicht gefunden",
        )

    if request.name is not None:
        rule.name = request.name
    if request.description is not None:
        rule.description = request.description
    if request.conditions is not None:
        rule.conditions = [c.model_dump() for c in request.conditions]
    if request.additional_approvers is not None:
        rule.additional_approvers = [a.model_dump() for a in request.additional_approvers]
    if request.priority_override is not None:
        rule.priority_override = request.priority_override
    if request.is_active is not None:
        rule.is_active = request.is_active

    await db.commit()
    await db.refresh(rule)

    return _build_conditional_rule_response(rule)


@router.delete(
    "/conditions/{rule_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Bedingte Genehmigungsregel loeschen",
)
async def delete_conditional_rule(
    rule_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    """Loescht eine bedingte Genehmigungsregel."""
    from app.db.models_approval_extended import ConditionalApprovalRule
    from sqlalchemy import select, and_

    stmt = select(ConditionalApprovalRule).where(
        and_(
            ConditionalApprovalRule.id == rule_id,
            ConditionalApprovalRule.company_id == current_user.company_id,
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


@router.post(
    "/conditions/evaluate",
    response_model=List[ConditionalRuleResponse],
    summary="Bedingungen gegen Dokumentdaten evaluieren",
)
async def evaluate_conditions(
    document_data: JSONDict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> List[ConditionalRuleResponse]:
    """Evaluiert alle aktiven bedingten Regeln gegen uebergebene Dokumentdaten."""
    from app.services.approval.conditional_logic_engine import ConditionalLogicEngine

    engine = ConditionalLogicEngine(db)
    matching_rules = await engine.evaluate_conditions(
        db, current_user.company_id, document_data
    )

    return [_build_conditional_rule_response(r) for r in matching_rules]


# =============================================================================
# ENDPOINTS - Escalation Rules
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
) -> List[EscalationRuleResponse]:
    """Listet alle Eskalationsregeln der Firma auf."""
    from app.services.approval.escalation_service import EscalationService

    service = EscalationService(db)
    rules = await service.get_escalation_rules(
        current_user.company_id, active_only=active_only
    )

    return [_build_escalation_rule_response(r) for r in rules]


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
) -> EscalationRuleResponse:
    """Erstellt eine neue Eskalationsregel."""
    from app.db.models_approval_extended import EscalationRule

    rule = EscalationRule(
        company_id=current_user.company_id,
        name=request.name,
        timeout_hours=request.timeout_hours,
        escalation_target_user_id=(
            UUID(request.escalation_target_user_id)
            if request.escalation_target_user_id
            else None
        ),
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
    )

    return _build_escalation_rule_response(rule)


@router.delete(
    "/escalation-rules/{rule_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Eskalationsregel loeschen",
)
async def delete_escalation_rule(
    rule_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    """Loescht eine Eskalationsregel."""
    from app.db.models_approval_extended import EscalationRule
    from sqlalchemy import select, and_

    stmt = select(EscalationRule).where(
        and_(
            EscalationRule.id == rule_id,
            EscalationRule.company_id == current_user.company_id,
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


# =============================================================================
# ENDPOINTS - Substitution Rules (Stellvertretung)
# =============================================================================


@router.get(
    "/substitutions",
    response_model=List[SubstitutionResponse],
    summary="Stellvertretungsregeln auflisten",
)
async def list_substitutions(
    active_only: bool = Query(True, description="Nur aktive Stellvertretungen"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> List[SubstitutionResponse]:
    """Listet alle Stellvertretungsregeln der Firma auf."""
    from app.services.approval.escalation_service import EscalationService

    service = EscalationService(db)
    rules = await service.get_substitution_rules(
        current_user.company_id, active_only=active_only
    )

    return [_build_substitution_response(r) for r in rules]


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
) -> SubstitutionResponse:
    """Erstellt eine neue Stellvertretungsregel."""
    from app.services.approval.escalation_service import EscalationService

    service = EscalationService(db)

    try:
        rule = await service.create_substitution(
            company_id=current_user.company_id,
            user_id=UUID(request.user_id),
            substitute_user_id=UUID(request.substitute_user_id),
            valid_from=request.valid_from,
            valid_until=request.valid_until,
            reason=request.reason,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )

    return _build_substitution_response(rule)


@router.delete(
    "/substitutions/{rule_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Stellvertretung loeschen",
)
async def delete_substitution(
    rule_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    """Loescht eine Stellvertretungsregel."""
    from app.services.approval.escalation_service import EscalationService

    service = EscalationService(db)
    deleted = await service.delete_substitution(rule_id, current_user.company_id)

    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Stellvertretung nicht gefunden",
        )


# =============================================================================
# ENDPOINTS - SLA Dashboard
# =============================================================================


@router.get(
    "/sla/dashboard",
    response_model=SLADashboardResponse,
    summary="SLA-Dashboard abrufen",
)
async def get_sla_dashboard(
    period_days: int = Query(30, ge=1, le=365, description="Zeitraum in Tagen"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SLADashboardResponse:
    """Liefert das SLA-Dashboard mit Metriken und Bottleneck-Analyse."""
    from app.services.approval.sla_monitoring_service import SLAMonitoringService

    service = SLAMonitoringService(db)
    dashboard = await service.get_sla_dashboard(
        db, current_user.company_id, period_days=period_days
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
    response_model=List[Dict[str, object]],
    summary="Aktuelle SLA-Verletzungen abrufen",
)
async def get_sla_breaches(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> List[Dict[str, object]]:
    """Liefert alle aktuell verletzten SLAs (offene Genehmigungen ueber Limit)."""
    from app.services.approval.sla_monitoring_service import SLAMonitoringService

    service = SLAMonitoringService(db)
    return await service.check_sla_breaches(db, current_user.company_id)


@router.get(
    "/sla/bottlenecks",
    response_model=List[Dict[str, object]],
    summary="Bottleneck-Analyse abrufen",
)
async def get_bottleneck_analysis(
    period_days: int = Query(30, ge=1, le=365, description="Zeitraum in Tagen"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> List[Dict[str, object]]:
    """Detaillierte Bottleneck-Analyse: Wer ist der langsamste Genehmiger?"""
    from app.services.approval.sla_monitoring_service import SLAMonitoringService

    service = SLAMonitoringService(db)
    return await service.get_bottleneck_analysis(
        db, current_user.company_id, period_days=period_days
    )


# =============================================================================
# ENDPOINTS - Auto-Filing
# =============================================================================


@router.get(
    "/auto-filing/rules",
    response_model=List[AutoFilingRuleResponse],
    summary="Auto-Filing-Regeln auflisten",
)
async def list_auto_filing_rules(
    active_only: bool = Query(True, description="Nur aktive Regeln"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> List[AutoFilingRuleResponse]:
    """Listet alle Auto-Filing-Regeln der Firma auf."""
    from app.db.models_approval_extended import AutoFilingRule
    from sqlalchemy import select, and_

    stmt = select(AutoFilingRule).where(
        AutoFilingRule.company_id == current_user.company_id
    )
    if active_only:
        stmt = stmt.where(AutoFilingRule.is_active.is_(True))
    stmt = stmt.order_by(AutoFilingRule.created_at.desc())

    result = await db.execute(stmt)
    rules = result.scalars().all()

    return [_build_auto_filing_rule_response(r) for r in rules]


@router.post(
    "/auto-filing/rules",
    response_model=AutoFilingRuleResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Auto-Filing-Regel erstellen",
)
async def create_auto_filing_rule(
    request: AutoFilingRuleCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AutoFilingRuleResponse:
    """Erstellt eine neue Auto-Filing-Regel."""
    from app.db.models_approval_extended import AutoFilingRule

    rule = AutoFilingRule(
        company_id=current_user.company_id,
        name=request.name,
        description=request.description,
        model_type=request.model_type,
        confidence_threshold=request.confidence_threshold,
        target_folder_id=(
            UUID(request.target_folder_id) if request.target_folder_id else None
        ),
        target_category=request.target_category,
        config=request.config or {},
        is_active=request.is_active,
    )
    db.add(rule)
    await db.commit()
    await db.refresh(rule)

    logger.info(
        "auto_filing_rule_created",
        rule_id=str(rule.id),
        name=rule.name,
        model_type=rule.model_type,
    )

    return _build_auto_filing_rule_response(rule)


@router.delete(
    "/auto-filing/rules/{rule_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Auto-Filing-Regel loeschen",
)
async def delete_auto_filing_rule(
    rule_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    """Loescht eine Auto-Filing-Regel."""
    from app.db.models_approval_extended import AutoFilingRule
    from sqlalchemy import select, and_

    stmt = select(AutoFilingRule).where(
        and_(
            AutoFilingRule.id == rule_id,
            AutoFilingRule.company_id == current_user.company_id,
        )
    )
    result = await db.execute(stmt)
    rule = result.scalar_one_or_none()

    if not rule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Auto-Filing-Regel nicht gefunden",
        )

    await db.delete(rule)
    await db.commit()


@router.post(
    "/auto-filing/classify/{document_id}",
    response_model=Dict[str, object],
    summary="Dokument automatisch klassifizieren und einordnen",
)
async def auto_file_document(
    document_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, object]:
    """Klassifiziert ein Dokument und ordnet es automatisch ein."""
    from app.services.auto_filing_service import AutoFilingService

    service = AutoFilingService(db)

    try:
        result = await service.auto_file_document(
            db, current_user.company_id, document_id
        )
        await db.commit()
        return result
    except Exception as exc:
        logger.error(
            "auto_filing_api_error",
            document_id=str(document_id),
            **safe_error_log(exc),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=safe_error_detail(exc, "Auto-Filing"),
        )


# =============================================================================
# ENDPOINTS - Auto-Matching
# =============================================================================


@router.get(
    "/auto-matching/results",
    response_model=List[AutoMatchResponse],
    summary="Auto-Match-Ergebnisse auflisten",
)
async def list_auto_match_results(
    document_id: Optional[UUID] = Query(None, description="Filter nach Dokument-ID"),
    confirmed_only: Optional[bool] = Query(None, description="Nur bestaetigte Matches"),
    limit: int = Query(50, ge=1, le=200, description="Maximale Anzahl"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> List[AutoMatchResponse]:
    """Listet Auto-Match-Ergebnisse auf."""
    from app.db.models_approval_extended import AutoMatchResult
    from sqlalchemy import select, and_

    stmt = select(AutoMatchResult).where(
        AutoMatchResult.company_id == current_user.company_id
    )

    if document_id:
        stmt = stmt.where(
            (AutoMatchResult.document_id == document_id)
            | (AutoMatchResult.matched_document_id == document_id)
        )

    if confirmed_only is not None:
        stmt = stmt.where(AutoMatchResult.is_confirmed == confirmed_only)

    stmt = stmt.order_by(AutoMatchResult.created_at.desc()).limit(limit)

    result = await db.execute(stmt)
    matches = result.scalars().all()

    return [_build_auto_match_response(m) for m in matches]


@router.post(
    "/auto-matching/run/{document_id}",
    response_model=List[AutoMatchResponse],
    summary="Auto-Matching fuer ein Dokument ausfuehren",
)
async def run_auto_matching(
    document_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> List[AutoMatchResponse]:
    """Fuehrt Auto-Matching fuer ein spezifisches Dokument aus."""
    from app.services.auto_matching_service import AutoMatchingService

    service = AutoMatchingService(db)

    try:
        matches = await service.find_matches(
            db, current_user.company_id, document_id
        )
        await db.commit()
        return [_build_auto_match_response(m) for m in matches]
    except Exception as exc:
        logger.error(
            "auto_matching_api_error",
            document_id=str(document_id),
            **safe_error_log(exc),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=safe_error_detail(exc, "Auto-Matching"),
        )


@router.post(
    "/auto-matching/confirm/{match_id}",
    response_model=AutoMatchResponse,
    summary="Auto-Match bestaetigen",
)
async def confirm_auto_match(
    match_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AutoMatchResponse:
    """Bestaetigt ein Auto-Match-Ergebnis manuell."""
    from app.services.auto_matching_service import AutoMatchingService

    service = AutoMatchingService(db)
    match = await service.confirm_match(
        db, match_id, current_user.id, current_user.company_id
    )

    if not match:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Match nicht gefunden",
        )

    await db.commit()
    return _build_auto_match_response(match)


@router.get(
    "/auto-matching/unmatched",
    response_model=List[Dict[str, object]],
    summary="Ungematchte Dokumente auflisten",
)
async def list_unmatched_documents(
    limit: int = Query(100, ge=1, le=500, description="Maximale Anzahl"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> List[Dict[str, object]]:
    """Listet Dokumente auf die noch kein Match haben."""
    from app.services.auto_matching_service import AutoMatchingService

    service = AutoMatchingService(db)
    return await service.get_unmatched_documents(
        db, current_user.company_id, limit=limit
    )
