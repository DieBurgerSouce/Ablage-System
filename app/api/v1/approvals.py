"""
Approval API Endpoints.

Enterprise Approval Workflow Engine:
- ApprovalRule CRUD (GET/POST/PUT/DELETE)
- ApprovalRequest Lifecycle (GET, approve, reject, escalate)
- ApprovalStep Decision (PATCH)
- Rule Preview/Simulation

Feinpoliert und durchdacht - Enterprise Genehmigungsworkflows.
"""

import structlog
from decimal import Decimal
from typing import Dict, List, Optional
from uuid import UUID

from app.core.types import JSONDict
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, ConfigDict, field_validator
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.db.models import (
    ApprovalPriority,
    ApprovalRequest,
    ApprovalRule,
    ApprovalRuleType,
    ApprovalStatus,
    ApprovalStep,
    User,
)
from app.api.dependencies import get_current_user, get_db
from app.services.approval.approval_service import ApprovalService
from app.services.approval.approval_rule_service import ApprovalRuleService
from app.services.approval.auto_approval_service import (
    AutoApprovalService,
    AutoApprovalConfig,
    AutoApprovalDecision,
    get_auto_approval_service,
)
from app.core.validators.jsonb_validators import (
    validate_approval_chain,
    validate_approval_conditions,
    JSONBValidationError,
)

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/approvals", tags=["approvals"])


# =============================================================================
# SCHEMAS - ApprovalRule
# =============================================================================

class ApprovalChainStepSchema(BaseModel):
    """Schema fuer einen Schritt in der Genehmiger-Kette."""
    step: int = Field(..., ge=1, description="Schritt-Nummer (1-basiert)")
    type: str = Field(..., description="Typ: user, role, group, department, any, all")
    value: str = Field(..., min_length=1, description="Wert: User-ID, Rollenname, etc.")
    required: bool = Field(True, description="Ob der Schritt erforderlich ist")
    threshold: Optional[Decimal] = Field(None, description="Optionale Betragsschwelle")
    timeout_hours: Optional[int] = Field(None, ge=1, description="Timeout in Stunden")


class ApprovalRuleCreateRequest(BaseModel):
    """Request zum Erstellen einer Approval-Regel."""
    name: str = Field(..., min_length=1, max_length=200, description="Name der Regel")
    description: Optional[str] = Field(None, description="Optionale Beschreibung")
    rule_type: ApprovalRuleType = Field(..., description="Typ der Regel")
    entity_types: List[str] = Field(
        ...,
        min_length=1,
        description="Entitaetstypen (z.B. invoice, expense, document)"
    )
    conditions: JSONDict = Field(
        default_factory=dict,
        description="Bedingungen (JSON)"
    )
    approval_chain: List[ApprovalChainStepSchema] = Field(
        ...,
        min_length=1,
        description="Genehmiger-Kette"
    )
    escalation_after_hours: Optional[int] = Field(None, ge=1, description="Eskalation nach X Stunden")
    escalation_to_role: Optional[str] = Field(None, description="Eskalation an Rolle")
    sla_hours: int = Field(48, ge=1, description="Max. Bearbeitungszeit")
    priority: int = Field(100, ge=1, le=999, description="Prioritaet (niedriger = hoeher)")
    is_active: bool = Field(True, description="Ob die Regel aktiv ist")

    @field_validator("conditions")
    @classmethod
    def validate_conditions(cls, v: JSONDict) -> JSONDict:
        """Validiert conditions gegen Whitelist."""
        if v:
            try:
                validate_approval_conditions(v, strict=True)
            except JSONBValidationError as e:
                raise ValueError(str(e))
        return v

    @field_validator("approval_chain")
    @classmethod
    def validate_chain(cls, v: List[ApprovalChainStepSchema]) -> List[ApprovalChainStepSchema]:
        """Validiert approval_chain gegen Schema."""
        chain_dicts = [step.model_dump() for step in v]
        try:
            validate_approval_chain(chain_dicts, strict=True)
        except JSONBValidationError as e:
            raise ValueError(str(e))
        return v


class ApprovalRuleUpdateRequest(BaseModel):
    """Request zum Aktualisieren einer Approval-Regel."""
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = None
    rule_type: Optional[ApprovalRuleType] = None
    entity_types: Optional[List[str]] = Field(None, min_length=1)
    conditions: Optional[JSONDict] = None
    approval_chain: Optional[List[ApprovalChainStepSchema]] = Field(None, min_length=1)
    escalation_after_hours: Optional[int] = Field(None, ge=1)
    escalation_to_role: Optional[str] = None
    sla_hours: Optional[int] = Field(None, ge=1)
    priority: Optional[int] = Field(None, ge=1, le=999)
    is_active: Optional[bool] = None

    @field_validator("conditions")
    @classmethod
    def validate_conditions(cls, v: Optional[JSONDict]) -> Optional[JSONDict]:
        """Validiert conditions gegen Whitelist."""
        if v is not None:
            try:
                validate_approval_conditions(v, strict=True)
            except JSONBValidationError as e:
                raise ValueError(str(e))
        return v


class ApprovalRuleResponse(BaseModel):
    """Response fuer eine Approval-Regel."""
    model_config = ConfigDict(from_attributes=True)

    id: str
    company_id: str
    name: str
    description: Optional[str]
    rule_type: str
    entity_types: List[str]
    conditions: JSONDict
    approval_chain: List[JSONDict]
    escalation_after_hours: Optional[int]
    escalation_to_role: Optional[str]
    sla_hours: Optional[int]
    priority: int
    is_active: bool
    created_at: str
    updated_at: str
    created_by_id: Optional[str]


class ApprovalRulesListResponse(BaseModel):
    """Response fuer Regelliste."""
    rules: List[ApprovalRuleResponse]
    total: int


# =============================================================================
# SCHEMAS - ApprovalRequest
# =============================================================================

class ApprovalRequestCreateRequest(BaseModel):
    """Request zum manuellen Erstellen einer Genehmigungsanfrage."""
    entity_type: str = Field(..., description="Entitaetstyp")
    entity_id: str = Field(..., description="Entitaets-ID (UUID)")
    title: str = Field(..., min_length=1, max_length=255, description="Titel")
    description: Optional[str] = Field(None, description="Beschreibung")
    amount: Optional[Decimal] = Field(None, description="Betrag")
    currency: str = Field("EUR", max_length=3, description="Waehrung")
    priority: ApprovalPriority = Field(ApprovalPriority.NORMAL, description="Prioritaet")
    approval_chain: List[ApprovalChainStepSchema] = Field(
        ...,
        min_length=1,
        description="Genehmiger-Kette"
    )
    sla_hours: int = Field(48, ge=1, description="Max. Bearbeitungszeit")
    metadata: Optional[JSONDict] = Field(None, description="Zusaetzliche Daten")


class ApprovalRequestResponse(BaseModel):
    """Response fuer eine Genehmigungsanfrage."""
    model_config = ConfigDict(from_attributes=True)

    id: str
    company_id: str
    entity_type: str
    entity_id: str
    title: str
    description: Optional[str]
    amount: Optional[str]  # Decimal als String
    currency: str
    status: str
    priority: str
    current_step: int
    total_steps: int
    approval_chain: List[JSONDict]
    due_date: Optional[str]
    is_escalated: bool
    resolved_at: Optional[str]
    resolved_by_id: Optional[str]
    requested_by_id: Optional[str]
    created_at: str
    updated_at: str
    steps: List["ApprovalStepResponse"] = Field(default_factory=list)


class ApprovalRequestsListResponse(BaseModel):
    """Response fuer Anfragenliste."""
    requests: List[ApprovalRequestResponse]
    total: int


class ApprovalDecisionRequest(BaseModel):
    """Request fuer Genehmigungsentscheidung."""
    decision: str = Field(..., pattern="^(approved|rejected)$", description="Entscheidung: approved oder rejected")
    notes: Optional[str] = Field(None, description="Optionale Notizen")


class ApprovalEscalationRequest(BaseModel):
    """Request fuer Eskalation."""
    escalation_reason: str = Field(..., min_length=1, description="Grund fuer Eskalation")
    escalate_to_role: Optional[str] = Field(None, description="An Rolle eskalieren")


# =============================================================================
# SCHEMAS - ApprovalStep
# =============================================================================

class ApprovalStepResponse(BaseModel):
    """Response fuer einen Genehmigungsschritt."""
    model_config = ConfigDict(from_attributes=True)

    id: str
    approval_request_id: str
    step_number: int
    approver_type: str
    approver_value: str
    assigned_user_id: Optional[str]
    status: str
    is_required: bool
    decision: Optional[str]
    decision_date: Optional[str]
    decision_by_id: Optional[str]
    decision_notes: Optional[str]
    delegated_to_id: Optional[str]
    reminder_sent_count: int


class ApprovalStepUpdateRequest(BaseModel):
    """Request zum Aktualisieren eines Schritts (nur Delegation)."""
    delegate_to_user_id: Optional[str] = Field(None, description="An User delegieren")
    delegation_reason: Optional[str] = Field(None, description="Grund fuer Delegation")


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def _build_rule_response(rule: ApprovalRule) -> ApprovalRuleResponse:
    """Erstellt Response aus DB-Modell."""
    return ApprovalRuleResponse(
        id=str(rule.id),
        company_id=str(rule.company_id),
        name=rule.name,
        description=rule.description,
        rule_type=rule.rule_type.value if rule.rule_type else "custom",
        entity_types=rule.entity_types or [],
        conditions=rule.conditions or {},
        approval_chain=rule.approval_chain or [],
        escalation_after_hours=rule.escalation_after_hours,
        escalation_to_role=rule.escalation_to_role,
        sla_hours=rule.sla_hours,
        priority=rule.priority,
        is_active=rule.is_active,
        created_at=rule.created_at.isoformat() if rule.created_at else "",
        updated_at=rule.updated_at.isoformat() if rule.updated_at else "",
        created_by_id=str(rule.created_by_id) if rule.created_by_id else None,
    )


def _build_request_response(request: ApprovalRequest) -> ApprovalRequestResponse:
    """Erstellt Response aus DB-Modell."""
    steps = []
    if hasattr(request, "approval_steps") and request.approval_steps:
        steps = [_build_step_response(s) for s in request.approval_steps]

    return ApprovalRequestResponse(
        id=str(request.id),
        company_id=str(request.company_id),
        entity_type=request.entity_type,
        entity_id=str(request.entity_id),
        title=request.title,
        description=request.description,
        amount=str(request.amount) if request.amount else None,
        currency=request.currency,
        status=request.status.value if request.status else "pending",
        priority=request.priority.value if request.priority else "normal",
        current_step=request.current_step,
        total_steps=request.total_steps,
        approval_chain=request.approval_chain or [],
        due_date=request.due_date.isoformat() if request.due_date else None,
        is_escalated=request.is_escalated,
        resolved_at=request.resolved_at.isoformat() if request.resolved_at else None,
        resolved_by_id=str(request.resolved_by_id) if request.resolved_by_id else None,
        requested_by_id=str(request.requested_by_id) if request.requested_by_id else None,
        created_at=request.created_at.isoformat() if request.created_at else "",
        updated_at=request.updated_at.isoformat() if request.updated_at else "",
        steps=steps,
    )


def _build_step_response(step: ApprovalStep) -> ApprovalStepResponse:
    """Erstellt Response aus DB-Modell."""
    return ApprovalStepResponse(
        id=str(step.id),
        approval_request_id=str(step.approval_request_id),
        step_number=step.step_number,
        approver_type=step.approver_type,
        approver_value=step.approver_value,
        assigned_user_id=str(step.assigned_user_id) if step.assigned_user_id else None,
        status=step.status.value if step.status else "pending",
        is_required=step.is_required,
        decision=step.decision,
        decision_date=step.decision_date.isoformat() if step.decision_date else None,
        decision_by_id=str(step.decision_by_id) if step.decision_by_id else None,
        decision_notes=step.decision_notes,
        delegated_to_id=str(step.delegated_to_id) if step.delegated_to_id else None,
        reminder_sent_count=step.reminder_sent_count or 0,
    )


# =============================================================================
# APPROVAL RULES ENDPOINTS
# =============================================================================

@router.get("/rules", response_model=ApprovalRulesListResponse)
async def list_approval_rules(
    active_only: bool = Query(True, description="Nur aktive Regeln"),
    rule_type: Optional[ApprovalRuleType] = Query(None, description="Nach Typ filtern"),
    entity_type: Optional[str] = Query(None, description="Nach Entitaetstyp filtern"),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ApprovalRulesListResponse:
    """Listet alle Approval-Regeln fuer die aktuelle Firma."""
    service = ApprovalRuleService(db)

    # Basis-Query
    rules = await service.get_rules_for_company(
        company_id=current_user.company_id,
        active_only=active_only,
    )

    # Filter anwenden
    filtered_rules = list(rules)
    if rule_type:
        filtered_rules = [r for r in filtered_rules if r.rule_type == rule_type]
    if entity_type:
        filtered_rules = [r for r in filtered_rules if entity_type in (r.entity_types or [])]

    total = len(filtered_rules)
    paginated = filtered_rules[offset:offset + limit]

    logger.info(
        "approval_rules_listed",
        company_id=str(current_user.company_id),
        total=total,
        user_id=str(current_user.id),
    )

    return ApprovalRulesListResponse(
        rules=[_build_rule_response(r) for r in paginated],
        total=total,
    )


@router.post("/rules", response_model=ApprovalRuleResponse, status_code=status.HTTP_201_CREATED)
async def create_approval_rule(
    request: ApprovalRuleCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ApprovalRuleResponse:
    """Erstellt eine neue Approval-Regel."""
    service = ApprovalRuleService(db)

    rule = await service.create_rule(
        company_id=current_user.company_id,
        name=request.name,
        rule_type=request.rule_type,
        entity_types=request.entity_types,
        conditions=request.conditions,
        approval_chain=[step.model_dump() for step in request.approval_chain],
        created_by_id=current_user.id,
        description=request.description,
        escalation_after_hours=request.escalation_after_hours,
        escalation_to_role=request.escalation_to_role,
        sla_hours=request.sla_hours,
        priority=request.priority,
    )

    logger.info(
        "approval_rule_created",
        rule_id=str(rule.id),
        rule_name=rule.name,
        company_id=str(current_user.company_id),
        user_id=str(current_user.id),
    )

    return _build_rule_response(rule)


@router.get("/rules/{rule_id}", response_model=ApprovalRuleResponse)
async def get_approval_rule(
    rule_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ApprovalRuleResponse:
    """Holt eine einzelne Approval-Regel."""
    service = ApprovalRuleService(db)

    # SECURITY: company_id fuer Multi-Tenant Isolation (IDOR-Prevention)
    rule = await service.get_rule(rule_id, company_id=current_user.company_id)
    if not rule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Regel nicht gefunden",
        )

    return _build_rule_response(rule)


@router.put("/rules/{rule_id}", response_model=ApprovalRuleResponse)
async def update_approval_rule(
    rule_id: UUID,
    request: ApprovalRuleUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ApprovalRuleResponse:
    """Aktualisiert eine Approval-Regel."""
    service = ApprovalRuleService(db)

    # Update-Daten
    update_data = request.model_dump(exclude_unset=True)
    if "approval_chain" in update_data:
        update_data["approval_chain"] = [
            step.model_dump() for step in request.approval_chain
        ]

    # SECURITY: company_id fuer Multi-Tenant Isolation (IDOR-Prevention)
    rule = await service.update_rule(
        rule_id,
        company_id=current_user.company_id,
        **update_data,
    )
    if not rule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Regel nicht gefunden",
        )

    logger.info(
        "approval_rule_updated",
        rule_id=str(rule_id),
        company_id=str(current_user.company_id),
        user_id=str(current_user.id),
    )

    return _build_rule_response(rule)


@router.delete("/rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_approval_rule(
    rule_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    """Loescht eine Approval-Regel (Soft-Delete via is_active=False)."""
    service = ApprovalRuleService(db)

    # SECURITY: company_id fuer Multi-Tenant Isolation (IDOR-Prevention)
    deleted = await service.delete_rule(rule_id, company_id=current_user.company_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Regel nicht gefunden",
        )

    logger.info(
        "approval_rule_deleted",
        rule_id=str(rule_id),
        company_id=str(current_user.company_id),
        user_id=str(current_user.id),
    )


@router.post("/rules/{rule_id}/preview")
async def preview_approval_rule(
    rule_id: UUID,
    test_data: JSONDict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> JSONDict:
    """Simuliert eine Regel gegen Testdaten (Preview/Dry-Run)."""
    service = ApprovalRuleService(db)

    # SECURITY: company_id fuer Multi-Tenant Isolation (IDOR-Prevention)
    rule = await service.get_rule(rule_id, company_id=current_user.company_id)
    if not rule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Regel nicht gefunden",
        )

    # Evaluate Rule against test_data
    matched = await service.evaluate_rule_conditions(rule, test_data)

    return {
        "rule_id": str(rule_id),
        "rule_name": rule.name,
        "would_match": matched,
        "approval_chain": rule.approval_chain,
        "test_data": test_data,
    }


# =============================================================================
# APPROVAL REQUESTS ENDPOINTS
# =============================================================================

@router.get("/requests", response_model=ApprovalRequestsListResponse)
async def list_approval_requests(
    status_filter: Optional[ApprovalStatus] = Query(None, description="Nach Status filtern"),
    entity_type: Optional[str] = Query(None, description="Nach Entitaetstyp filtern"),
    my_pending: bool = Query(False, description="Nur meine ausstehenden Genehmigungen"),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ApprovalRequestsListResponse:
    """Listet Genehmigungsanfragen."""
    service = ApprovalService(db)

    requests = await service.get_requests_for_company(
        company_id=current_user.company_id,
        status_filter=status_filter,
        entity_type=entity_type,
        for_user_id=current_user.id if my_pending else None,
        offset=offset,
        limit=limit,
    )

    total = await service.count_requests_for_company(
        company_id=current_user.company_id,
        status_filter=status_filter,
        entity_type=entity_type,
        for_user_id=current_user.id if my_pending else None,
    )

    return ApprovalRequestsListResponse(
        requests=[_build_request_response(r) for r in requests],
        total=total,
    )


@router.get("/requests/{request_id}", response_model=ApprovalRequestResponse)
async def get_approval_request(
    request_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ApprovalRequestResponse:
    """Holt eine einzelne Genehmigungsanfrage mit Steps."""
    service = ApprovalService(db)

    # SECURITY: Multi-Tenant Isolation via company_id
    request = await service.get_request(
        request_id,
        company_id=current_user.company_id,
        include_steps=True,
    )
    if not request:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Anfrage nicht gefunden",
        )

    return _build_request_response(request)


@router.post("/requests/{request_id}/approve", response_model=ApprovalRequestResponse)
async def approve_request(
    request_id: UUID,
    decision: ApprovalDecisionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ApprovalRequestResponse:
    """Genehmigt eine Anfrage (fuer den aktuellen Schritt)."""
    if decision.decision != "approved":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Diese Aktion erwartet 'approved' als Entscheidung",
        )

    service = ApprovalService(db)

    # SECURITY: Multi-Tenant Isolation via company_id
    request = await service.get_request(
        request_id,
        company_id=current_user.company_id,
        include_steps=True,
    )
    if not request:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Anfrage nicht gefunden",
        )

    # Check if user can approve current step
    can_approve = await service.can_user_approve_step(
        request=request,
        user=current_user,
        step_number=request.current_step,
    )
    if not can_approve:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Sie sind nicht berechtigt, diesen Schritt zu genehmigen",
        )

    # SECURITY: company_id an Service weitergeben
    result = await service.process_approval_decision(
        request_id=request_id,
        user_id=current_user.id,
        decision="approved",
        company_id=current_user.company_id,
        notes=decision.notes,
    )

    if not result.success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result.message,
        )

    # Refetch with updated data
    updated_request = await service.get_request(
        request_id,
        company_id=current_user.company_id,
        include_steps=True,
    )

    logger.info(
        "approval_request_approved",
        request_id=str(request_id),
        step=request.current_step,
        user_id=str(current_user.id),
    )

    return _build_request_response(updated_request)


@router.post("/requests/{request_id}/reject", response_model=ApprovalRequestResponse)
async def reject_request(
    request_id: UUID,
    decision: ApprovalDecisionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ApprovalRequestResponse:
    """Lehnt eine Anfrage ab."""
    if decision.decision != "rejected":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Diese Aktion erwartet 'rejected' als Entscheidung",
        )

    service = ApprovalService(db)

    # SECURITY: Multi-Tenant Isolation via company_id
    request = await service.get_request(
        request_id,
        company_id=current_user.company_id,
        include_steps=True,
    )
    if not request:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Anfrage nicht gefunden",
        )

    can_approve = await service.can_user_approve_step(
        request=request,
        user=current_user,
        step_number=request.current_step,
    )
    if not can_approve:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Sie sind nicht berechtigt, diesen Schritt zu bearbeiten",
        )

    # SECURITY: company_id an Service weitergeben
    result = await service.process_approval_decision(
        request_id=request_id,
        user_id=current_user.id,
        decision="rejected",
        company_id=current_user.company_id,
        notes=decision.notes,
    )

    if not result.success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result.message,
        )

    updated_request = await service.get_request(
        request_id,
        company_id=current_user.company_id,
        include_steps=True,
    )

    logger.info(
        "approval_request_rejected",
        request_id=str(request_id),
        step=request.current_step,
        user_id=str(current_user.id),
    )

    return _build_request_response(updated_request)


@router.post("/requests/{request_id}/escalate", response_model=ApprovalRequestResponse)
async def escalate_request(
    request_id: UUID,
    escalation: ApprovalEscalationRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ApprovalRequestResponse:
    """Eskaliert eine Anfrage manuell."""
    service = ApprovalService(db)

    # SECURITY: Multi-Tenant Isolation via company_id
    request = await service.get_request(
        request_id,
        company_id=current_user.company_id,
        include_steps=True,
    )
    if not request:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Anfrage nicht gefunden",
        )

    if request.status != ApprovalStatus.PENDING:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Nur ausstehende Anfragen koennen eskaliert werden",
        )

    # SECURITY: company_id an Service weitergeben
    result = await service.escalate_request(
        request_id=request_id,
        reason=escalation.escalation_reason,
        company_id=current_user.company_id,
        escalate_to_role=escalation.escalate_to_role,
        escalated_by_id=current_user.id,
    )

    if not result:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Eskalation fehlgeschlagen",
        )

    updated_request = await service.get_request(
        request_id,
        company_id=current_user.company_id,
        include_steps=True,
    )

    logger.info(
        "approval_request_escalated",
        request_id=str(request_id),
        reason=escalation.escalation_reason,
        user_id=str(current_user.id),
    )

    return _build_request_response(updated_request)


# =============================================================================
# APPROVAL STEPS ENDPOINTS
# =============================================================================

@router.patch("/steps/{step_id}", response_model=ApprovalStepResponse)
async def update_approval_step(
    step_id: UUID,
    update: ApprovalStepUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ApprovalStepResponse:
    """Aktualisiert einen Schritt (Delegation)."""
    service = ApprovalService(db)

    # SECURITY: Multi-Tenant Isolation via company_id
    step = await service.get_step(step_id, company_id=current_user.company_id)
    if not step:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Schritt nicht gefunden",
        )

    if update.delegate_to_user_id:
        delegate_to_uuid = UUID(update.delegate_to_user_id)
        # SECURITY: company_id an Service weitergeben
        await service.delegate_step(
            step_id=step_id,
            delegate_to_id=delegate_to_uuid,
            delegated_by_id=current_user.id,
            company_id=current_user.company_id,
            reason=update.delegation_reason,
        )

    updated_step = await service.get_step(step_id, company_id=current_user.company_id)

    logger.info(
        "approval_step_delegated",
        step_id=str(step_id),
        delegate_to=update.delegate_to_user_id,
        user_id=str(current_user.id),
    )

    return _build_step_response(updated_step)


# =============================================================================
# DASHBOARD / SUMMARY ENDPOINTS
# =============================================================================

@router.get("/summary")
async def get_approval_summary(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> JSONDict:
    """Holt Zusammenfassung fuer Dashboard."""
    service = ApprovalService(db)

    summary = await service.get_approval_summary(
        company_id=current_user.company_id,
        user_id=current_user.id,
    )

    return {
        "total_pending": summary.total_pending,
        "total_approved": summary.total_approved,
        "total_rejected": summary.total_rejected,
        "total_escalated": summary.total_escalated,
        "avg_resolution_hours": round(summary.avg_resolution_hours, 1),
        "overdue_count": summary.overdue_count,
        "my_pending": summary.my_pending,
    }


@router.get("/rule-types")
async def list_rule_types(
    current_user: User = Depends(get_current_user),
) -> Dict[str, List[Dict[str, str]]]:
    """Listet verfuegbare Regeltypen."""
    return {
        "rule_types": [
            {"value": rt.value, "label": _get_rule_type_label(rt)}
            for rt in ApprovalRuleType
        ]
    }


def _get_rule_type_label(rt: ApprovalRuleType) -> str:
    """Gibt deutsches Label fuer Regeltyp zurueck."""
    labels = {
        ApprovalRuleType.AMOUNT_THRESHOLD: "Betragsschwelle",
        ApprovalRuleType.CATEGORY: "Nach Kategorie",
        ApprovalRuleType.SUPPLIER: "Nach Lieferant",
        ApprovalRuleType.COST_CENTER: "Nach Kostenstelle",
        ApprovalRuleType.DOCUMENT_TYPE: "Nach Dokumenttyp",
        ApprovalRuleType.RISK_LEVEL: "Nach Risikostufe",
        ApprovalRuleType.CUSTOM: "Benutzerdefiniert",
    }
    return labels.get(rt, rt.value)


# =============================================================================
# AUTO-APPROVAL SCHEMAS
# =============================================================================


class AutoApprovalCheckRequest(BaseModel):
    """Request fuer Auto-Approval Pruefung."""
    document_id: Optional[str] = Field(None, description="Dokument-ID (UUID)")
    invoice_id: Optional[str] = Field(None, description="Rechnungs-ID (UUID)")
    entity_id: Optional[str] = Field(None, description="Entity-ID (UUID)")
    amount: Optional[Decimal] = Field(None, description="Betrag")
    document_type: Optional[str] = Field(None, description="Dokumenttyp")
    category: Optional[str] = Field(None, description="Kategorie")


class AutoApprovalRuleSchema(BaseModel):
    """Schema fuer eine Auto-Approval-Regel."""
    id: str
    name: str
    description: str
    enabled: bool
    priority: int
    max_amount: Optional[str] = None
    min_entity_relationship_months: Optional[int] = None
    max_risk_score: Optional[int] = None
    document_types: Optional[List[str]] = None
    categories: Optional[List[str]] = None


class AutoApprovalRuleUpdateRequest(BaseModel):
    """Request zum Aktualisieren einer Auto-Approval-Regel."""
    enabled: Optional[bool] = Field(None, description="Regel aktivieren/deaktivieren")
    max_amount: Optional[Decimal] = Field(None, description="Maximalbetrag")
    min_entity_relationship_months: Optional[int] = Field(None, ge=0, description="Min. Beziehungsdauer")
    max_risk_score: Optional[int] = Field(None, ge=0, le=100, description="Max. Risiko-Score")


class AutoApprovalResultResponse(BaseModel):
    """Response fuer Auto-Approval Pruefung."""
    decision: str
    reasons: List[str]
    matched_rules: List[str]
    confidence: float
    explanation: str
    auto_approved: bool
    approval_id: Optional[str] = None
    approved_at: Optional[str] = None
    approved_by_rule: Optional[str] = None


class EntityTrustScoreResponse(BaseModel):
    """Response fuer Entity Trust Score."""
    entity_id: str
    trust_score: float
    relationship_months: int
    total_documents: int
    total_invoices: int
    avg_payment_delay_days: float
    risk_score: int
    is_trusted: bool
    trust_factors: Dict[str, float]


class AutoApprovalConfigResponse(BaseModel):
    """Response fuer Auto-Approval Konfiguration."""
    default_max_amount: str
    default_max_risk_score: int
    default_min_relationship_months: int
    max_auto_approvals_per_day: int
    max_auto_approvals_per_hour: int
    enable_amount_based_approval: bool
    enable_trusted_supplier_approval: bool
    enable_risk_based_approval: bool


class AutoApprovalOptOutRequest(BaseModel):
    """Request fuer User Opt-Out."""
    opt_out: bool = Field(..., description="True fuer Opt-Out, False fuer Opt-In")
    document_types: Optional[List[str]] = Field(None, description="Spezifische Dokumenttypen")


# =============================================================================
# AUTO-APPROVAL ENDPOINTS
# =============================================================================


@router.post("/auto-approval/check", response_model=AutoApprovalResultResponse)
async def check_auto_approval(
    request: AutoApprovalCheckRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AutoApprovalResultResponse:
    """Prueft ob ein Dokument/Rechnung automatisch genehmigt werden kann.

    Diese Pruefung fuehrt keine Genehmigung durch, sondern zeigt nur das Ergebnis.
    """
    service = get_auto_approval_service(db)

    result = await service.check_auto_approval(
        document_id=UUID(request.document_id) if request.document_id else None,
        invoice_id=UUID(request.invoice_id) if request.invoice_id else None,
        entity_id=UUID(request.entity_id) if request.entity_id else None,
        amount=request.amount,
        document_type=request.document_type,
        category=request.category,
        company_id=current_user.company_id,
        user_id=current_user.id,
    )

    return AutoApprovalResultResponse(
        decision=result.decision.value,
        reasons=[r.value for r in result.reasons],
        matched_rules=result.matched_rules,
        confidence=result.confidence,
        explanation=result.explanation,
        auto_approved=result.decision == AutoApprovalDecision.AUTO_APPROVED,
        approval_id=str(result.approval_id) if result.approval_id else None,
        approved_at=result.approved_at.isoformat() if result.approved_at else None,
        approved_by_rule=result.approved_by_rule,
    )


@router.post("/auto-approval/apply", response_model=AutoApprovalResultResponse)
async def apply_auto_approval(
    request: AutoApprovalCheckRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AutoApprovalResultResponse:
    """Prueft und wendet Auto-Approval an wenn moeglich.

    Erstellt einen ApprovalRequest im Status APPROVED wenn alle Bedingungen erfuellt sind.
    """
    service = get_auto_approval_service(db)

    # Erst pruefen
    result = await service.check_auto_approval(
        document_id=UUID(request.document_id) if request.document_id else None,
        invoice_id=UUID(request.invoice_id) if request.invoice_id else None,
        entity_id=UUID(request.entity_id) if request.entity_id else None,
        amount=request.amount,
        document_type=request.document_type,
        category=request.category,
        company_id=current_user.company_id,
        user_id=current_user.id,
    )

    approval_request = None

    # Wenn auto-approved, dann ApprovalRequest erstellen
    if result.decision == AutoApprovalDecision.AUTO_APPROVED:
        entity_type = request.document_type or "document"
        entity_id = UUID(request.document_id or request.invoice_id or "")

        if request.document_id or request.invoice_id:
            approval_request = await service.apply_auto_approval(
                entity_type=entity_type,
                entity_id=entity_id,
                company_id=current_user.company_id,
                amount=request.amount,
                title=f"Auto-Approval: {entity_type}",
            )

    logger.info(
        "auto_approval_applied",
        decision=result.decision.value,
        document_id=request.document_id,
        invoice_id=request.invoice_id,
        approval_id=str(approval_request.id) if approval_request else None,
        user_id=str(current_user.id),
    )

    return AutoApprovalResultResponse(
        decision=result.decision.value,
        reasons=[r.value for r in result.reasons],
        matched_rules=result.matched_rules,
        confidence=result.confidence,
        explanation=result.explanation,
        auto_approved=approval_request is not None,
        approval_id=str(approval_request.id) if approval_request else None,
        approved_at=result.approved_at.isoformat() if result.approved_at else None,
        approved_by_rule=result.approved_by_rule,
    )


@router.get("/auto-approval/rules", response_model=List[AutoApprovalRuleSchema])
async def list_auto_approval_rules(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> List[AutoApprovalRuleSchema]:
    """Listet alle konfigurierten Auto-Approval-Regeln."""
    service = get_auto_approval_service(db)
    rules = service.get_rules()

    return [
        AutoApprovalRuleSchema(
            id=rule.id,
            name=rule.name,
            description=rule.description,
            enabled=rule.enabled,
            priority=rule.priority,
            max_amount=str(rule.max_amount) if rule.max_amount else None,
            min_entity_relationship_months=rule.min_entity_relationship_months,
            max_risk_score=rule.max_risk_score,
            document_types=rule.document_types,
            categories=rule.categories,
        )
        for rule in rules
    ]


@router.patch("/auto-approval/rules/{rule_id}")
async def update_auto_approval_rule(
    rule_id: str,
    update: AutoApprovalRuleUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> JSONDict:
    """Aktualisiert eine Auto-Approval-Regel."""
    service = get_auto_approval_service(db)

    # Regel finden
    rules = service.get_rules()
    rule = next((r for r in rules if r.id == rule_id), None)

    if not rule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Regel nicht gefunden",
        )

    # Updates anwenden
    if update.enabled is not None:
        service.enable_rule(rule_id, update.enabled)

    if update.max_amount is not None:
        rule.max_amount = update.max_amount

    if update.min_entity_relationship_months is not None:
        rule.min_entity_relationship_months = update.min_entity_relationship_months

    if update.max_risk_score is not None:
        rule.max_risk_score = update.max_risk_score

    logger.info(
        "auto_approval_rule_updated",
        rule_id=rule_id,
        user_id=str(current_user.id),
    )

    return {"success": True, "rule_id": rule_id}


@router.get("/auto-approval/entity-trust/{entity_id}", response_model=EntityTrustScoreResponse)
async def get_entity_trust_score(
    entity_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> EntityTrustScoreResponse:
    """Berechnet den Trust-Score fuer eine Entity (Kunde/Lieferant)."""
    service = get_auto_approval_service(db)
    trust_score = await service.calculate_entity_trust_score(entity_id)

    return EntityTrustScoreResponse(
        entity_id=str(trust_score.entity_id),
        trust_score=trust_score.trust_score,
        relationship_months=trust_score.relationship_months,
        total_documents=trust_score.total_documents,
        total_invoices=trust_score.total_invoices,
        avg_payment_delay_days=trust_score.avg_payment_delay_days,
        risk_score=trust_score.risk_score,
        is_trusted=trust_score.is_trusted,
        trust_factors=trust_score.trust_factors,
    )


@router.get("/auto-approval/config", response_model=AutoApprovalConfigResponse)
async def get_auto_approval_config(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AutoApprovalConfigResponse:
    """Holt die aktuelle Auto-Approval-Konfiguration."""
    service = get_auto_approval_service(db)
    config = service.config

    return AutoApprovalConfigResponse(
        default_max_amount=str(config.default_max_amount),
        default_max_risk_score=config.default_max_risk_score,
        default_min_relationship_months=config.default_min_relationship_months,
        max_auto_approvals_per_day=config.max_auto_approvals_per_day,
        max_auto_approvals_per_hour=config.max_auto_approvals_per_hour,
        enable_amount_based_approval=config.enable_amount_based_approval,
        enable_trusted_supplier_approval=config.enable_trusted_supplier_approval,
        enable_risk_based_approval=config.enable_risk_based_approval,
    )


@router.post("/auto-approval/opt-out")
async def set_user_opt_out(
    request: AutoApprovalOptOutRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> JSONDict:
    """Setzt Opt-Out fuer den aktuellen User.

    Wenn opt_out=True, werden Dokumente des Users nicht automatisch genehmigt.
    Optional koennen spezifische Dokumenttypen angegeben werden.
    """
    service = get_auto_approval_service(db)

    await service.set_user_opt_out(
        user_id=current_user.id,
        opt_out=request.opt_out,
        document_types=request.document_types,
    )

    logger.info(
        "auto_approval_opt_out_set",
        user_id=str(current_user.id),
        opt_out=request.opt_out,
        document_types=request.document_types,
    )

    return {
        "success": True,
        "opt_out": request.opt_out,
        "document_types": request.document_types,
    }


@router.get("/auto-approval/stats")
async def get_auto_approval_stats(
    days: int = Query(30, ge=1, le=365, description="Zeitraum in Tagen"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> JSONDict:
    """Holt Statistiken zu Auto-Approvals."""
    from datetime import timedelta
    from app.core.datetime_utils import utc_now

    # Statistiken aus ApprovalRequests berechnen
    cutoff = utc_now() - timedelta(days=days)

    # Auto-Approved Anfragen
    auto_approved_stmt = select(func.count(ApprovalRequest.id)).where(
        and_(
            ApprovalRequest.company_id == current_user.company_id,
            ApprovalRequest.metadata["auto_approved"].astext == "true",
            ApprovalRequest.created_at >= cutoff,
        )
    )
    auto_approved_result = await db.execute(auto_approved_stmt)
    auto_approved_count = auto_approved_result.scalar() or 0

    # Manuelle Approvals
    manual_stmt = select(func.count(ApprovalRequest.id)).where(
        and_(
            ApprovalRequest.company_id == current_user.company_id,
            or_(
                ApprovalRequest.metadata["auto_approved"].is_(None),
                ApprovalRequest.metadata["auto_approved"].astext != "true",
            ),
            ApprovalRequest.created_at >= cutoff,
        )
    )
    manual_result = await db.execute(manual_stmt)
    manual_count = manual_result.scalar() or 0

    total = auto_approved_count + manual_count
    auto_rate = (auto_approved_count / total * 100) if total > 0 else 0

    return {
        "period_days": days,
        "total_approvals": total,
        "auto_approved": auto_approved_count,
        "manual_approved": manual_count,
        "auto_approval_rate": round(auto_rate, 1),
        "rules_active": len(get_auto_approval_service(db).get_rules()),
    }
