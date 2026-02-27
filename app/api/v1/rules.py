# -*- coding: utf-8 -*-
"""
Business Rules API für Ablage-System.

REST API für Geschäftsregeln:
- CRUD für Regeln
- Regel-Testing (Dry-Run)
- Regel-Auswertung für Dokumente
- RuleSets verwalten

Phase 4 der Strategischen Roadmap (Januar 2026).
"""

import structlog
from datetime import datetime
from typing import Optional, List, Dict, Union

from app.core.types import JSONDict, RuleConditionDict, RuleActionDict, RuleContextDict
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status, Body
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user, get_db
from app.core.safe_errors import safe_error_detail
from app.core.jsonb_validators import validate_jsonb_payload
from app.db.models import User

logger = structlog.get_logger(__name__)
from app.db.models_rules import BusinessRuleModel, RuleExecutionLog, RuleSet
from app.services.rules import (
    BusinessRulesEngine,
    RuleCondition,
    RuleAction,
    BusinessRule,
    RuleEvaluationResult,
    ConditionOperator,
    ActionType,
    RuleCategory,
    RulePriority,
    CompositeCondition,
    RuleSetEvaluationResult,
)

router = APIRouter(prefix="/rules", tags=["Business Rules"])


# =============================================================================
# Pydantic Schemas
# =============================================================================


class ConditionSchema(BaseModel):
    """Schema für eine Regel-Bedingung."""
    field: str = Field(..., description="Feld-Pfad (z.B. 'amount', 'supplier.is_new')")
    op: ConditionOperator = Field(..., description="Operator")
    value: Union[str, int, float, bool, List[str], None] = Field(default=None, description="Vergleichswert")
    case_sensitive: bool = Field(default=False)
    negate: bool = Field(default=False)


class CompositeConditionSchema(BaseModel):
    """Schema für zusammengesetzte Bedingung."""
    and_: Optional[List["ConditionOrComposite"]] = Field(default=None, alias="and")
    or_: Optional[List["ConditionOrComposite"]] = Field(default=None, alias="or")
    not_: Optional["ConditionOrComposite"] = Field(default=None, alias="not")

    class Config:
        populate_by_name = True


# Union type für verschachtelte Bedingungen
ConditionOrComposite = ConditionSchema | CompositeConditionSchema


class ActionSchema(BaseModel):
    """Schema für eine Regel-Aktion."""
    type: ActionType = Field(..., description="Aktions-Typ")
    params: JSONDict = Field(default_factory=dict, description="Parameter")


class RuleCreateRequest(BaseModel):
    """Request zum Erstellen einer Regel."""
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = Field(default=None, max_length=2000)
    code: Optional[str] = Field(default=None, max_length=50, description="Kurzer Code")

    # Bedingung (einfach oder komplex als JSON)
    condition: RuleConditionDict = Field(..., description="Regel-Bedingung")

    # Aktionen
    actions: List[ActionSchema] = Field(..., min_length=1)
    else_actions: Optional[List[ActionSchema]] = Field(default=None)

    # Konfiguration
    priority: int = Field(default=50, ge=1, le=100)
    category: str = Field(default="custom")
    is_active: bool = Field(default=True)
    stop_on_match: bool = Field(default=False)

    # Anwendungsbereich
    applies_to_document_types: Optional[List[str]] = Field(default=None)
    applies_to_sources: Optional[List[str]] = Field(default=None)

    # Zeitliche Einschränkung
    valid_from: Optional[datetime] = None
    valid_until: Optional[datetime] = None

    @model_validator(mode="after")
    def validate_jsonb_payloads(self) -> "RuleCreateRequest":
        """Validate JSONB payloads for size, depth, and injection patterns."""
        if self.condition:
            validate_jsonb_payload(self.condition, max_depth=5)
        for action in self.actions:
            if action.params:
                validate_jsonb_payload(action.params, max_depth=3)
        if self.else_actions:
            for action in self.else_actions:
                if action.params:
                    validate_jsonb_payload(action.params, max_depth=3)
        return self


class RuleUpdateRequest(BaseModel):
    """Request zum Aktualisieren einer Regel."""
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    description: Optional[str] = Field(default=None, max_length=2000)
    code: Optional[str] = Field(default=None, max_length=50)
    condition: Optional[RuleConditionDict] = None
    actions: Optional[List[ActionSchema]] = None
    else_actions: Optional[List[ActionSchema]] = None
    priority: Optional[int] = Field(default=None, ge=1, le=100)
    category: Optional[str] = None
    is_active: Optional[bool] = None
    stop_on_match: Optional[bool] = None
    applies_to_document_types: Optional[List[str]] = None
    applies_to_sources: Optional[List[str]] = None
    valid_from: Optional[datetime] = None
    valid_until: Optional[datetime] = None

    @model_validator(mode="after")
    def validate_jsonb_payloads(self) -> "RuleUpdateRequest":
        """Validate JSONB payloads for size, depth, and injection patterns."""
        if self.condition:
            validate_jsonb_payload(self.condition, max_depth=5)
        if self.actions:
            for action in self.actions:
                if action.params:
                    validate_jsonb_payload(action.params, max_depth=3)
        if self.else_actions:
            for action in self.else_actions:
                if action.params:
                    validate_jsonb_payload(action.params, max_depth=3)
        return self


class RuleResponse(BaseModel):
    """Response für eine Regel."""
    id: UUID
    name: str
    description: Optional[str] = None
    code: Optional[str] = None
    condition: RuleConditionDict
    actions: List[RuleActionDict]
    else_actions: Optional[List[RuleActionDict]] = None
    priority: int
    category: str
    is_active: bool
    stop_on_match: bool
    applies_to_document_types: Optional[List[str]] = None
    applies_to_sources: Optional[List[str]] = None
    valid_from: Optional[datetime] = None
    valid_until: Optional[datetime] = None
    execution_count: int
    match_count: int
    last_executed_at: Optional[datetime] = None
    last_matched_at: Optional[datetime] = None
    created_by_id: Optional[UUID] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class RuleListResponse(BaseModel):
    """Response für Regel-Liste."""
    items: List[RuleResponse]
    total: int
    page: int
    per_page: int


class RuleTestRequest(BaseModel):
    """Request zum Testen einer Regel."""
    condition: RuleConditionDict = Field(..., description="Regel-Bedingung")
    actions: List[ActionSchema] = Field(..., min_length=1)
    else_actions: Optional[List[ActionSchema]] = None
    context: RuleContextDict = Field(..., description="Test-Kontext")


class RuleTestResponse(BaseModel):
    """Response für Regel-Test."""
    matched: bool
    condition_details: JSONDict
    would_trigger_actions: List[RuleActionDict]
    context_used: RuleContextDict


class DocumentEvaluationRequest(BaseModel):
    """Request für Dokument-Auswertung."""
    document_id: UUID
    rule_ids: Optional[List[UUID]] = Field(
        default=None, description="Spezifische Regeln (oder alle)"
    )
    additional_context: Optional[RuleContextDict] = Field(default=None)
    dry_run: bool = Field(default=True, description="Aktionen nicht ausführen")


class EvaluationResultResponse(BaseModel):
    """Response für Auswertungs-Ergebnis."""
    rule_id: UUID
    rule_name: str
    matched: bool
    condition_details: JSONDict
    triggered_actions: List[RuleActionDict]
    execution_errors: List[str]


class DocumentEvaluationResponse(BaseModel):
    """Response für Dokument-Auswertung."""
    document_id: UUID
    total_rules_evaluated: int
    rules_matched: int
    results: List[EvaluationResultResponse]
    all_triggered_actions: List[RuleActionDict]
    evaluated_at: datetime


class RuleSetCreateRequest(BaseModel):
    """Request zum Erstellen eines RuleSets."""
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = Field(default=None, max_length=2000)
    rule_ids: List[UUID] = Field(..., min_length=1)
    is_active: bool = Field(default=True)
    is_default: bool = Field(default=False)


class RuleSetResponse(BaseModel):
    """Response für RuleSet."""
    id: UUID
    name: str
    description: Optional[str] = None
    version: str
    rule_ids: List[UUID]
    is_active: bool
    is_default: bool
    created_by_id: Optional[UUID] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ExecutionLogResponse(BaseModel):
    """Response für Execution-Log."""
    id: UUID
    rule_id: UUID
    document_id: Optional[UUID] = None
    matched: bool
    condition_details: JSONDict
    triggered_actions: List[RuleActionDict]
    execution_errors: List[str]
    dry_run: bool
    executed_at: datetime
    execution_time_ms: Optional[int] = None

    class Config:
        from_attributes = True


class OperatorsResponse(BaseModel):
    """Response mit verfügbaren Operatoren."""
    operators: List[Dict[str, str]]
    action_types: List[Dict[str, str]]
    categories: List[str]


class GenerateRuleRequest(BaseModel):
    """Request zur KI-Regelgenerierung."""
    prompt: str = Field(..., min_length=5, max_length=1000, description="Natürlichsprachliche Beschreibung der Regel")


class GenerateRuleResponse(BaseModel):
    """Response der KI-Regelgenerierung."""
    name: str
    description: str
    code: Optional[str] = None
    category: str
    priority: int
    condition: RuleConditionDict
    actions: List[RuleActionDict]
    else_actions: Optional[List[RuleActionDict]] = None
    confidence: float = Field(ge=0.0, le=1.0)
    explanation: str


# =============================================================================
# Helper Functions
# =============================================================================


def _model_to_response(model: BusinessRuleModel) -> RuleResponse:
    """Konvertiert DB-Model zu Response."""
    return RuleResponse(
        id=model.id,
        name=model.name,
        description=model.description,
        code=model.code,
        condition=model.condition,
        actions=model.actions,
        else_actions=model.else_actions,
        priority=model.priority,
        category=model.category,
        is_active=model.is_active,
        stop_on_match=model.stop_on_match,
        applies_to_document_types=model.applies_to_document_types,
        applies_to_sources=model.applies_to_sources,
        valid_from=model.valid_from,
        valid_until=model.valid_until,
        execution_count=model.execution_count,
        match_count=model.match_count,
        last_executed_at=model.last_executed_at,
        last_matched_at=model.last_matched_at,
        created_by_id=model.created_by_id,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


def _db_rule_to_business_rule(model: BusinessRuleModel) -> BusinessRule:
    """Konvertiert DB-Model zu BusinessRule für Engine."""
    return BusinessRule(
        id=model.id,
        name=model.name,
        description=model.description,
        condition=model.condition,
        actions=[RuleAction(**a) for a in model.actions],
        else_actions=[RuleAction(**a) for a in model.else_actions] if model.else_actions else None,
        priority=RulePriority(model.priority) if model.priority in [10, 25, 50, 75, 100] else RulePriority.NORMAL,
        category=RuleCategory(model.category) if model.category in [c.value for c in RuleCategory] else RuleCategory.CUSTOM,
        is_active=model.is_active,
        stop_on_match=model.stop_on_match,
        applies_to_document_types=model.applies_to_document_types,
        applies_to_sources=model.applies_to_sources,
        valid_from=model.valid_from,
        valid_until=model.valid_until,
        company_id=model.company_id,
    )


# =============================================================================
# CRUD Endpoints
# =============================================================================


@router.get("", response_model=RuleListResponse)
async def list_rules(
    page: int = Query(1, ge=1, description="Seitennummer (1-basiert)"),
    per_page: int = Query(50, ge=1, le=100, description="Eintraege pro Seite"),
    category: Optional[str] = Query(None, description="Nach Kategorie filtern"),
    is_active: Optional[bool] = Query(None, description="Nach Status filtern"),
    search: Optional[str] = Query(None, max_length=100, description="Suche in Name"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> RuleListResponse:
    """Listet alle Regeln der Company."""
    # Basis-Query
    query = select(BusinessRuleModel).where(
        BusinessRuleModel.company_id == current_user.company_id
    )

    # Filter
    if category:
        query = query.where(BusinessRuleModel.category == category)
    if is_active is not None:
        query = query.where(BusinessRuleModel.is_active == is_active)
    if search:
        query = query.where(BusinessRuleModel.name.ilike(f"%{search}%"))

    # Count
    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar() or 0

    # Sortierung und Pagination
    query = query.order_by(
        BusinessRuleModel.priority.desc(),
        BusinessRuleModel.name,
    ).offset((page - 1) * per_page).limit(per_page)

    result = await db.execute(query)
    rules = result.scalars().all()

    return RuleListResponse(
        items=[_model_to_response(r) for r in rules],
        total=total,
        page=page,
        per_page=per_page,
    )


@router.post("", response_model=RuleResponse, status_code=status.HTTP_201_CREATED)
async def create_rule(
    request: RuleCreateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> RuleResponse:
    """Erstellt eine neue Regel."""
    # Code-Eindeutigkeit prüfen
    if request.code:
        existing = await db.execute(
            select(BusinessRuleModel).where(
                and_(
                    BusinessRuleModel.company_id == current_user.company_id,
                    BusinessRuleModel.code == request.code,
                )
            )
        )
        if existing.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Regel mit Code '{request.code}' existiert bereits",
            )

    # Aktionen zu JSON serialisieren
    actions_json = [{"type": a.type.value, "params": a.params} for a in request.actions]
    else_actions_json = None
    if request.else_actions:
        else_actions_json = [{"type": a.type.value, "params": a.params} for a in request.else_actions]

    rule = BusinessRuleModel(
        name=request.name,
        description=request.description,
        code=request.code,
        company_id=current_user.company_id,
        condition=request.condition,
        actions=actions_json,
        else_actions=else_actions_json,
        priority=request.priority,
        category=request.category,
        is_active=request.is_active,
        stop_on_match=request.stop_on_match,
        applies_to_document_types=request.applies_to_document_types,
        applies_to_sources=request.applies_to_sources,
        valid_from=request.valid_from,
        valid_until=request.valid_until,
        created_by_id=current_user.id,
    )

    db.add(rule)
    await db.commit()
    await db.refresh(rule)

    return _model_to_response(rule)


@router.get("/{rule_id}", response_model=RuleResponse)
async def get_rule(
    rule_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> RuleResponse:
    """Holt eine einzelne Regel."""
    result = await db.execute(
        select(BusinessRuleModel).where(
            and_(
                BusinessRuleModel.id == rule_id,
                BusinessRuleModel.company_id == current_user.company_id,
            )
        )
    )
    rule = result.scalar_one_or_none()

    if not rule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Regel nicht gefunden",
        )

    return _model_to_response(rule)


@router.patch("/{rule_id}", response_model=RuleResponse)
async def update_rule(
    rule_id: UUID,
    request: RuleUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> RuleResponse:
    """Aktualisiert eine Regel."""
    result = await db.execute(
        select(BusinessRuleModel).where(
            and_(
                BusinessRuleModel.id == rule_id,
                BusinessRuleModel.company_id == current_user.company_id,
            )
        )
    )
    rule = result.scalar_one_or_none()

    if not rule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Regel nicht gefunden",
        )

    # Code-Eindeutigkeit prüfen
    if request.code and request.code != rule.code:
        existing = await db.execute(
            select(BusinessRuleModel).where(
                and_(
                    BusinessRuleModel.company_id == current_user.company_id,
                    BusinessRuleModel.code == request.code,
                    BusinessRuleModel.id != rule_id,
                )
            )
        )
        if existing.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Regel mit Code '{request.code}' existiert bereits",
            )

    # Felder aktualisieren
    update_data = request.model_dump(exclude_unset=True)

    # Aktionen zu JSON konvertieren
    if "actions" in update_data and update_data["actions"]:
        update_data["actions"] = [
            {"type": a["type"].value if hasattr(a["type"], "value") else a["type"], "params": a["params"]}
            for a in update_data["actions"]
        ]
    if "else_actions" in update_data and update_data["else_actions"]:
        update_data["else_actions"] = [
            {"type": a["type"].value if hasattr(a["type"], "value") else a["type"], "params": a["params"]}
            for a in update_data["else_actions"]
        ]

    for key, value in update_data.items():
        setattr(rule, key, value)

    rule.updated_by_id = current_user.id

    await db.commit()
    await db.refresh(rule)

    return _model_to_response(rule)


@router.delete("/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_rule(
    rule_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Löscht eine Regel."""
    result = await db.execute(
        select(BusinessRuleModel).where(
            and_(
                BusinessRuleModel.id == rule_id,
                BusinessRuleModel.company_id == current_user.company_id,
            )
        )
    )
    rule = result.scalar_one_or_none()

    if not rule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Regel nicht gefunden",
        )

    await db.delete(rule)
    await db.commit()


# =============================================================================
# Testing & Evaluation Endpoints
# =============================================================================


@router.post("/test", response_model=RuleTestResponse)
async def test_rule(
    request: RuleTestRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> RuleTestResponse:
    """Testet eine Regel gegen einen Kontext (ohne zu speichern).

    Erlaubt das Testen von Regeln vor dem Erstellen.
    """
    engine = BusinessRulesEngine(db)

    # Temporaere Regel erstellen
    temp_rule = BusinessRule(
        name="Test-Regel",
        condition=request.condition,
        actions=[RuleAction(**a.model_dump()) for a in request.actions],
        else_actions=[RuleAction(**a.model_dump()) for a in request.else_actions] if request.else_actions else None,
    )

    # Auswerten (immer dry_run)
    result = await engine.evaluate_single_rule(
        context=request.context,
        rule=temp_rule,
        dry_run=True,
    )

    return RuleTestResponse(
        matched=result.matched,
        condition_details=result.condition_details,
        would_trigger_actions=[
            {"type": a.type.value, "params": a.params}
            for a in result.triggered_actions
        ],
        context_used=request.context,
    )


@router.post("/evaluate/{document_id}", response_model=DocumentEvaluationResponse)
async def evaluate_document(
    document_id: UUID,
    rule_ids: Optional[List[UUID]] = Body(default=None, description="Spezifische Regeln"),
    additional_context: Optional[RuleContextDict] = Body(default=None),
    dry_run: bool = Body(default=True),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DocumentEvaluationResponse:
    """Wertet Regeln für ein Dokument aus.

    Ladet automatisch Dokument-Daten als Kontext und wendet
    alle (oder spezifische) Regeln an.
    """
    import time

    # Regeln laden
    query = select(BusinessRuleModel).where(
        and_(
            BusinessRuleModel.company_id == current_user.company_id,
            BusinessRuleModel.is_active == True,
        )
    )

    if rule_ids:
        query = query.where(BusinessRuleModel.id.in_(rule_ids))

    result = await db.execute(query.order_by(BusinessRuleModel.priority.desc()))
    db_rules = result.scalars().all()

    if not db_rules:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Keine aktiven Regeln gefunden",
        )

    # Zu BusinessRule-Objekten konvertieren
    business_rules = [_db_rule_to_business_rule(r) for r in db_rules]

    # Engine ausführen
    engine = BusinessRulesEngine(db)

    start_time = time.time()
    eval_result = await engine.evaluate_for_document(
        document_id=document_id,
        rules=business_rules,
        additional_context=additional_context,
        dry_run=dry_run,
    )
    execution_time_ms = int((time.time() - start_time) * 1000)

    # Statistiken aktualisieren
    now = datetime.utcnow()
    for rule_result in eval_result.rule_results:
        # DB-Regel finden
        db_rule = next((r for r in db_rules if r.id == rule_result.rule_id), None)
        if db_rule:
            db_rule.execution_count += 1
            db_rule.last_executed_at = now
            if rule_result.matched:
                db_rule.match_count += 1
                db_rule.last_matched_at = now

            # Execution Log erstellen
            log = RuleExecutionLog(
                rule_id=db_rule.id,
                document_id=document_id,
                matched=rule_result.matched,
                condition_details=rule_result.condition_details,
                triggered_actions=[
                    {"type": a.type.value, "params": a.params}
                    for a in rule_result.triggered_actions
                ],
                execution_errors=rule_result.execution_errors,
                context_snapshot=eval_result.context_snapshot,
                dry_run=dry_run,
                execution_time_ms=execution_time_ms // len(db_rules) if db_rules else 0,
            )
            db.add(log)

    await db.commit()

    return DocumentEvaluationResponse(
        document_id=document_id,
        total_rules_evaluated=eval_result.total_rules_evaluated,
        rules_matched=eval_result.rules_matched,
        results=[
            EvaluationResultResponse(
                rule_id=r.rule_id,
                rule_name=r.rule_name,
                matched=r.matched,
                condition_details=r.condition_details,
                triggered_actions=[
                    {"type": a.type.value, "params": a.params}
                    for a in r.triggered_actions
                ],
                execution_errors=r.execution_errors,
            )
            for r in eval_result.rule_results
        ],
        all_triggered_actions=[
            {"type": a.type.value, "params": a.params}
            for a in eval_result.all_triggered_actions
        ],
        evaluated_at=eval_result.evaluated_at,
    )


@router.get("/evaluate/{document_id}/preview", response_model=DocumentEvaluationResponse)
async def preview_document_evaluation(
    document_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DocumentEvaluationResponse:
    """Preview: Zeigt welche Regeln für ein Dokument greifen wuerden.

    Immer dry_run - keine Aktionen werden ausgeführt.
    """
    return await evaluate_document(
        document_id=document_id,
        rule_ids=None,
        additional_context=None,
        dry_run=True,
        current_user=current_user,
        db=db,
    )


# =============================================================================
# RuleSet Endpoints
# =============================================================================


@router.get("/sets", response_model=List[RuleSetResponse])
async def list_rule_sets(
    is_active: Optional[bool] = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> List[RuleSetResponse]:
    """Listet alle RuleSets."""
    query = select(RuleSet).where(
        RuleSet.company_id == current_user.company_id
    )

    if is_active is not None:
        query = query.where(RuleSet.is_active == is_active)

    query = query.order_by(RuleSet.name)

    result = await db.execute(query)
    sets = result.scalars().all()

    return [
        RuleSetResponse(
            id=s.id,
            name=s.name,
            description=s.description,
            version=s.version,
            rule_ids=[UUID(r) if isinstance(r, str) else r for r in s.rule_ids],
            is_active=s.is_active,
            is_default=s.is_default,
            created_by_id=s.created_by_id,
            created_at=s.created_at,
            updated_at=s.updated_at,
        )
        for s in sets
    ]


@router.post("/sets", response_model=RuleSetResponse, status_code=status.HTTP_201_CREATED)
async def create_rule_set(
    request: RuleSetCreateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> RuleSetResponse:
    """Erstellt ein neues RuleSet."""
    # Wenn default, andere defaults deaktivieren
    if request.is_default:
        await db.execute(
            select(RuleSet).where(
                and_(
                    RuleSet.company_id == current_user.company_id,
                    RuleSet.is_default == True,
                )
            )
        )
        # Update alle is_default auf False
        from sqlalchemy import update
        await db.execute(
            update(RuleSet).where(
                and_(
                    RuleSet.company_id == current_user.company_id,
                    RuleSet.is_default == True,
                )
            ).values(is_default=False)
        )

    rule_set = RuleSet(
        name=request.name,
        description=request.description,
        company_id=current_user.company_id,
        rule_ids=[str(r) for r in request.rule_ids],
        is_active=request.is_active,
        is_default=request.is_default,
        created_by_id=current_user.id,
    )

    db.add(rule_set)
    await db.commit()
    await db.refresh(rule_set)

    return RuleSetResponse(
        id=rule_set.id,
        name=rule_set.name,
        description=rule_set.description,
        version=rule_set.version,
        rule_ids=[UUID(r) if isinstance(r, str) else r for r in rule_set.rule_ids],
        is_active=rule_set.is_active,
        is_default=rule_set.is_default,
        created_by_id=rule_set.created_by_id,
        created_at=rule_set.created_at,
        updated_at=rule_set.updated_at,
    )


@router.delete("/sets/{set_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_rule_set(
    set_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Löscht ein RuleSet."""
    result = await db.execute(
        select(RuleSet).where(
            and_(
                RuleSet.id == set_id,
                RuleSet.company_id == current_user.company_id,
            )
        )
    )
    rule_set = result.scalar_one_or_none()

    if not rule_set:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="RuleSet nicht gefunden",
        )

    await db.delete(rule_set)
    await db.commit()


# =============================================================================
# Execution Logs
# =============================================================================


@router.get("/logs", response_model=List[ExecutionLogResponse])
async def list_execution_logs(
    rule_id: Optional[UUID] = Query(None, description="Nach Regel filtern"),
    document_id: Optional[UUID] = Query(None, description="Nach Dokument filtern"),
    matched_only: bool = Query(False, description="Nur Matches"),
    per_page: int = Query(50, ge=1, le=100, description="Eintraege pro Seite"),
    page: int = Query(1, ge=1, description="Seitennummer (1-basiert)"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> List[ExecutionLogResponse]:
    """Listet Ausführungs-Logs."""
    # Subquery für Company-Filter
    company_rules = select(BusinessRuleModel.id).where(
        BusinessRuleModel.company_id == current_user.company_id
    )

    query = select(RuleExecutionLog).where(
        RuleExecutionLog.rule_id.in_(company_rules)
    )

    if rule_id:
        query = query.where(RuleExecutionLog.rule_id == rule_id)
    if document_id:
        query = query.where(RuleExecutionLog.document_id == document_id)
    if matched_only:
        query = query.where(RuleExecutionLog.matched == True)

    query = query.order_by(RuleExecutionLog.executed_at.desc()).offset((page - 1) * per_page).limit(per_page)

    result = await db.execute(query)
    logs = result.scalars().all()

    return [
        ExecutionLogResponse(
            id=log.id,
            rule_id=log.rule_id,
            document_id=log.document_id,
            matched=log.matched,
            condition_details=log.condition_details,
            triggered_actions=log.triggered_actions,
            execution_errors=log.execution_errors,
            dry_run=log.dry_run,
            executed_at=log.executed_at,
            execution_time_ms=log.execution_time_ms,
        )
        for log in logs
    ]


# =============================================================================
# Schema/Info Endpoints
# =============================================================================


@router.get("/schema/operators", response_model=OperatorsResponse)
async def get_operators(
    current_user: User = Depends(get_current_user),
) -> OperatorsResponse:
    """Gibt verfügbare Operatoren und Aktionstypen zurück."""
    return OperatorsResponse(
        operators=[
            {"value": op.value, "name": op.name, "description": _get_operator_description(op)}
            for op in ConditionOperator
        ],
        action_types=[
            {"value": at.value, "name": at.name, "description": _get_action_description(at)}
            for at in ActionType
        ],
        categories=[c.value for c in RuleCategory],
    )


def _get_operator_description(op: ConditionOperator) -> str:
    """Gibt Beschreibung für Operator zurück."""
    descriptions = {
        ConditionOperator.EQUALS: "Exakte Gleichheit",
        ConditionOperator.NOT_EQUALS: "Ungleichheit",
        ConditionOperator.GREATER_THAN: "Größer als",
        ConditionOperator.GREATER_EQUALS: "Größer oder gleich",
        ConditionOperator.LESS_THAN: "Kleiner als",
        ConditionOperator.LESS_EQUALS: "Kleiner oder gleich",
        ConditionOperator.CONTAINS: "Enthält Teilstring",
        ConditionOperator.NOT_CONTAINS: "Enthält nicht",
        ConditionOperator.STARTS_WITH: "Beginnt mit",
        ConditionOperator.ENDS_WITH: "Endet mit",
        ConditionOperator.MATCHES: "Regex-Pattern Match",
        ConditionOperator.IN: "In Liste enthalten",
        ConditionOperator.NOT_IN: "Nicht in Liste",
        ConditionOperator.IS_EMPTY: "Liste/String ist leer",
        ConditionOperator.IS_NOT_EMPTY: "Liste/String nicht leer",
        ConditionOperator.IS_NULL: "Wert ist null/None",
        ConditionOperator.IS_NOT_NULL: "Wert existiert",
        ConditionOperator.IN_PERIOD: "Datum in Periode (month_end, quarter_end)",
        ConditionOperator.BEFORE: "Datum vor Vergleichsdatum",
        ConditionOperator.AFTER: "Datum nach Vergleichsdatum",
        ConditionOperator.BETWEEN: "Wert zwischen zwei Grenzen",
        ConditionOperator.HAS_TAG: "Hat bestimmten Tag",
        ConditionOperator.HAS_ANY_TAG: "Hat mindestens einen der Tags",
        ConditionOperator.HAS_ALL_TAGS: "Hat alle angegebenen Tags",
    }
    return descriptions.get(op, "")


def _get_action_description(at: ActionType) -> str:
    """Gibt Beschreibung für Aktionstyp zurück."""
    descriptions = {
        ActionType.REQUIRE_APPROVAL: "Genehmigung erforderlich",
        ActionType.REQUIRE_CFO_APPROVAL: "CFO-Genehmigung erforderlich",
        ActionType.REQUIRE_MANAGER_APPROVAL: "Manager-Genehmigung erforderlich",
        ActionType.SET_FLAG: "Flag setzen",
        ActionType.REMOVE_FLAG: "Flag entfernen",
        ActionType.SET_STATUS: "Status setzen",
        ActionType.SET_PRIORITY: "Prioritaet setzen",
        ActionType.NOTIFY_USER: "Benutzer benachrichtigen",
        ActionType.NOTIFY_TEAM: "Team benachrichtigen",
        ActionType.NOTIFY_ADMIN: "Admin benachrichtigen",
        ActionType.SEND_EMAIL: "E-Mail senden",
        ActionType.SEND_SLACK: "Slack-Nachricht senden",
        ActionType.START_WORKFLOW: "Workflow starten",
        ActionType.ASSIGN_TO_USER: "Benutzer zuweisen",
        ActionType.ASSIGN_TO_TEAM: "Team zuweisen",
        ActionType.SET_FIELD: "Feld setzen",
        ActionType.ADD_TAG: "Tag hinzufuegen",
        ActionType.REMOVE_TAG: "Tag entfernen",
        ActionType.ADD_COMMENT: "Kommentar hinzufuegen",
        ActionType.TRIGGER_OCR: "OCR ausloesen",
        ActionType.FLAG_FOR_REVIEW: "Zur Prüfung markieren",
        ActionType.MANUAL_REVIEW_REQUIRED: "Manuelle Prüfung erforderlich",
        ActionType.BLOCK_PROCESSING: "Verarbeitung blockieren",
        ActionType.FLAG_FOR_ARCHIVE: "Zur Archivierung markieren",
        ActionType.FLAG_FOR_PERIOD_CLOSE: "Für Periodenabschluss markieren",
    }
    return descriptions.get(at, "")


# =============================================================================
# AI Rule Generation
# =============================================================================


@router.post("/generate", response_model=GenerateRuleResponse)
async def generate_rule_from_prompt(
    request: GenerateRuleRequest,
    current_user: User = Depends(get_current_user),
) -> GenerateRuleResponse:
    """Generiert eine Regel aus natürlichsprachlicher Beschreibung.

    Nutzt lokalen LLM (Ollama) zur Generierung strukturierter Regeln
    aus natürlichsprachlichen Prompts wie:
    - "Erstelle Regel für Skonto-Überwachung"
    - "Rechnungen über 10000 EUR müssen vom CFO genehmigt werden"
    - "Neue Lieferanten zur Prüfung markieren"

    Die generierte Regel wird NICHT gespeichert - nur zur Vorschau.
    Der Nutzer kann sie danach bearbeiten und manuell speichern.

    Returns:
        GenerateRuleResponse mit strukturierter Regel inkl. Confidence
    """
    from app.services.rules.ai_rule_generator_service import get_ai_rule_generator_service

    try:
        service = await get_ai_rule_generator_service()
        generated = await service.generate_rule(request.prompt)

        return GenerateRuleResponse(
            name=generated.name,
            description=generated.description,
            code=generated.code,
            category=generated.category,
            priority=generated.priority,
            condition=generated.condition,
            actions=generated.actions,
            else_actions=generated.else_actions,
            confidence=generated.confidence,
            explanation=generated.explanation,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=safe_error_detail(e, "Vorgang")
        )
    except Exception as e:
        logger.exception("Fehler bei Regelgenerierung", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=safe_error_detail(e, "Vorgang")
        )
