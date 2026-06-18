# -*- coding: utf-8 -*-
"""Workflow API Endpoints.

32 Endpoints für Workflow-Automation:
- Workflow CRUD (8)
- Workflow Steps (6)
- Execution (8)
- Templates (4)
- Webhook Triggers (3)
- Statistics (3)
"""


from datetime import datetime
from typing import Dict, List, Optional
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status, Response
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user, get_db, require_admin
from app.api.dependencies import get_user_company_id  # F-31
from app.core.jsonb_validators import validate_jsonb_payload
from app.core.rate_limiting import limiter, get_user_identifier
from app.core.safe_errors import safe_error_detail, safe_error_log
from app.db.models import User, UserCompany, Company
from app.services.workflow import (
    ConditionEvaluator,
    WorkflowExecutionService,
    WorkflowService,
    WorkflowStepExecutor,
    WorkflowTriggerService,
)
from sqlalchemy import Integer, select

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/workflows", tags=["workflows"])


# =============================================================================
# Helper Functions - Multi-Tenant Security
# =============================================================================

async def get_user_company_id(db: AsyncSession, user: User) -> Optional[UUID]:
    """
    Ermittelt die Company-ID des Users via UserCompany-Tabelle.

    SECURITY FIX: Ersetzt das ungültige `hasattr(user, 'company_id')` Pattern.
    User-Model hat kein company_id Feld - muss über UserCompany geholt werden.

    Returns:
        Company-ID oder None wenn keine Zuordnung existiert
    """
    from sqlalchemy import select

    # 1. Hole aktuelle Firma (is_current=True)
    result = await db.execute(
        select(UserCompany.company_id)
        .join(Company, Company.id == UserCompany.company_id)
        .where(UserCompany.user_id == user.id)
        .where(UserCompany.is_current == True)
        .where(Company.is_active == True)
        .where(Company.deleted_at.is_(None))
    )
    current_company_id = result.scalar_one_or_none()

    if current_company_id:
        return current_company_id

    # 2. Fallback: Erste verfügbare Firma
    result = await db.execute(
        select(UserCompany.company_id)
        .join(Company, Company.id == UserCompany.company_id)
        .where(UserCompany.user_id == user.id)
        .where(Company.is_active == True)
        .where(Company.deleted_at.is_(None))
        .order_by(UserCompany.created_at)
        .limit(1)
    )
    return result.scalar_one_or_none()


# =============================================================================
# Pydantic Schemas
# =============================================================================


class WorkflowCreate(BaseModel):
    """Schema für Workflow-Erstellung."""

    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    trigger_type: str = Field(..., pattern="^(document_event|schedule|condition|manual|webhook)$")
    trigger_config: Dict[str, object] = Field(default_factory=dict)
    nodes: Optional[List[Dict[str, object]]] = None
    edges: Optional[List[Dict[str, object]]] = None
    variables: Optional[Dict[str, object]] = None
    max_concurrent_executions: int = Field(default=10, ge=1, le=100)
    timeout_seconds: int = Field(default=3600, ge=60, le=86400)
    retry_config: Optional[Dict[str, object]] = None

    @model_validator(mode="after")
    def validate_jsonb_payloads(self) -> "WorkflowCreate":
        """Validate JSONB payloads for size, depth, and injection patterns."""
        if self.trigger_config:
            validate_jsonb_payload(self.trigger_config, max_depth=3)
        if self.nodes:
            validate_jsonb_payload(self.nodes, max_depth=5)
        if self.edges:
            validate_jsonb_payload(self.edges, max_depth=3)
        if self.variables:
            validate_jsonb_payload(self.variables, max_depth=3)
        if self.retry_config:
            validate_jsonb_payload(self.retry_config, max_depth=3)
        return self


class WorkflowUpdate(BaseModel):
    """Schema für Workflow-Update."""

    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    trigger_type: Optional[str] = Field(None, pattern="^(document_event|schedule|condition|manual|webhook)$")
    trigger_config: Optional[Dict[str, object]] = None
    nodes: Optional[List[Dict[str, object]]] = None
    edges: Optional[List[Dict[str, object]]] = None
    variables: Optional[Dict[str, object]] = None
    is_active: Optional[bool] = None
    max_concurrent_executions: Optional[int] = Field(None, ge=1, le=100)
    timeout_seconds: Optional[int] = Field(None, ge=60, le=86400)
    retry_config: Optional[Dict[str, object]] = None

    @model_validator(mode="after")
    def validate_jsonb_payloads(self) -> "WorkflowUpdate":
        """Validate JSONB payloads for size, depth, and injection patterns."""
        if self.trigger_config:
            validate_jsonb_payload(self.trigger_config, max_depth=3)
        if self.nodes:
            validate_jsonb_payload(self.nodes, max_depth=5)
        if self.edges:
            validate_jsonb_payload(self.edges, max_depth=3)
        if self.variables:
            validate_jsonb_payload(self.variables, max_depth=3)
        if self.retry_config:
            validate_jsonb_payload(self.retry_config, max_depth=3)
        return self


class WorkflowResponse(BaseModel):
    """Schema für Workflow-Antwort."""

    id: UUID
    user_id: UUID
    company_id: Optional[UUID] = None
    name: str
    description: Optional[str] = None
    trigger_type: str
    trigger_config: Dict[str, object]
    nodes: List[Dict[str, object]]
    edges: List[Dict[str, object]]
    variables: Dict[str, object]
    is_active: bool
    is_template: bool
    max_concurrent_executions: int
    timeout_seconds: int
    retry_config: Dict[str, object]
    execution_count: int
    last_executed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class WorkflowListResponse(BaseModel):
    """Schema für Workflow-Liste."""

    items: List[WorkflowResponse]
    total: int
    page: int
    per_page: int


class StepCreate(BaseModel):
    """Schema für Step-Erstellung."""

    step_order: int = Field(..., ge=0)
    step_type: str = Field(..., pattern="^(condition|action|branch|delay|parallel|loop)$")
    step_name: Optional[str] = None
    config: Dict[str, object] = Field(default_factory=dict)
    retry_on_failure: bool = True
    max_retries: int = Field(default=3, ge=0, le=10)
    position_x: float = 0.0
    position_y: float = 0.0


class StepUpdate(BaseModel):
    """Schema für Step-Update."""

    step_order: Optional[int] = Field(None, ge=0)
    step_type: Optional[str] = Field(None, pattern="^(condition|action|branch|delay|parallel|loop)$")
    step_name: Optional[str] = None
    config: Optional[Dict[str, object]] = None
    retry_on_failure: Optional[bool] = None
    max_retries: Optional[int] = Field(None, ge=0, le=10)
    position_x: Optional[float] = None
    position_y: Optional[float] = None


class StepResponse(BaseModel):
    """Schema für Step-Antwort."""

    id: UUID
    workflow_id: UUID
    step_order: int
    step_type: str
    step_name: Optional[str] = None
    config: Dict[str, object]
    retry_on_failure: bool
    max_retries: int
    position_x: float
    position_y: float
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class StepReorderItem(BaseModel):
    """Schema für Step-Neuordnung."""

    step_id: UUID
    step_order: int


class ExecutionStart(BaseModel):
    """Schema für Execution-Start."""

    document_id: Optional[UUID] = None
    variables: Optional[Dict[str, object]] = None


class ExecutionResponse(BaseModel):
    """Schema für Execution-Antwort."""

    id: UUID
    workflow_id: UUID
    user_id: UUID
    document_id: Optional[UUID] = None
    status: str
    trigger_data: Dict[str, object]
    variables: Dict[str, object]
    current_step_id: Optional[UUID] = None
    progress_percent: int
    started_at: datetime
    completed_at: Optional[datetime] = None
    result: Optional[Dict[str, object]] = None
    error_message: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class ExecutionListResponse(BaseModel):
    """Schema für Execution-Liste."""

    items: List[ExecutionResponse]
    total: int
    page: int
    per_page: int


class StepExecutionResponse(BaseModel):
    """Schema für Step-Execution-Antwort."""

    id: UUID
    execution_id: UUID
    step_id: UUID
    status: str
    started_at: datetime
    completed_at: Optional[datetime] = None
    input_data: Optional[Dict[str, object]] = None
    output_data: Optional[Dict[str, object]] = None
    error_message: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class TemplateInstantiate(BaseModel):
    """Schema für Template-Instanziierung."""

    name: Optional[str] = None
    company_id: Optional[UUID] = None


class WebhookPayload(BaseModel):
    """Schema für Webhook-Payload."""

    data: Dict[str, object] = Field(default_factory=dict)


class ValidationResult(BaseModel):
    """Schema für Validierungsergebnis."""

    valid: bool
    errors: List[str]
    warnings: List[str]


class WorkflowStats(BaseModel):
    """Schema für Workflow-Statistiken."""

    workflow_id: UUID
    name: str
    is_active: bool
    execution_count: int
    last_executed_at: Optional[datetime] = None
    statistics: Dict[str, object]


class OverviewStats(BaseModel):
    """Schema für Gesamt-Statistiken."""

    total_workflows: int
    active_workflows: int
    total_executions: int
    executions_today: int
    success_rate: float


# =============================================================================
# Workflow CRUD Endpoints (8)
# =============================================================================


@router.post(
    "",
    response_model=WorkflowResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Workflow erstellen",
)
async def create_workflow(
    data: WorkflowCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> WorkflowResponse:
    """Erstellt einen neuen Workflow."""
    service = WorkflowService(db)

    # SECURITY FIX: company_id via UserCompany-Tabelle (User-Modell hat keine Firmen-Spalte)
    company_id = await get_user_company_id(db, current_user)

    workflow = await service.create_workflow(
        user_id=current_user.id,
        name=data.name,
        trigger_type=data.trigger_type,
        trigger_config=data.trigger_config,
        nodes=data.nodes,
        edges=data.edges,
        description=data.description,
        company_id=company_id,
        variables=data.variables,
        max_concurrent_executions=data.max_concurrent_executions,
        timeout_seconds=data.timeout_seconds,
        retry_config=data.retry_config,
    )

    return WorkflowResponse.model_validate(workflow)


@router.get(
    "",
    response_model=WorkflowListResponse,
    summary="Workflows auflisten",
)
async def list_workflows(
    trigger_type: Optional[str] = Query(None, description="Filter nach Trigger-Typ"),
    is_active: Optional[bool] = Query(None, description="Filter nach Aktiv-Status"),
    is_template: Optional[bool] = Query(None, description="Filter nach Template-Status"),
    search: Optional[str] = Query(None, description="Suchbegriff"),
    page: int = Query(1, ge=1, description="Seitennummer (1-basiert)"),
    per_page: int = Query(50, ge=1, le=100, description="Eintraege pro Seite"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> WorkflowListResponse:
    """Listet Workflows mit optionalen Filtern."""
    service = WorkflowService(db)

    # SECURITY FIX: company_id via UserCompany-Tabelle (User-Modell hat keine Firmen-Spalte)
    company_id = await get_user_company_id(db, current_user)

    workflows, total = await service.list_workflows(
        user_id=current_user.id,
        company_id=company_id,
        trigger_type=trigger_type,
        is_active=is_active,
        is_template=is_template,
        search=search,
        offset=(page - 1) * per_page,
        limit=per_page,
    )

    return WorkflowListResponse(
        items=[WorkflowResponse.model_validate(w) for w in workflows],
        total=total,
        page=page,
        per_page=per_page,
    )


@router.get(
    "/{workflow_id}",
    response_model=WorkflowResponse,
    summary="Workflow abrufen",
)
async def get_workflow(
    workflow_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> WorkflowResponse:
    """Ruft einen Workflow nach ID ab."""
    # SECURITY FIX: company_id für Multi-Tenant Isolation
    company_id = await get_user_company_id(db, current_user)

    service = WorkflowService(db)

    workflow = await service.get_workflow(
        workflow_id=workflow_id,
        user_id=current_user.id,
        company_id=company_id,
    )

    if not workflow:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workflow nicht gefunden",
        )

    return WorkflowResponse.model_validate(workflow)


@router.put(
    "/{workflow_id}",
    response_model=WorkflowResponse,
    summary="Workflow aktualisieren",
)
async def update_workflow(
    workflow_id: UUID,
    data: WorkflowUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> WorkflowResponse:
    """Aktualisiert einen Workflow."""
    # SECURITY FIX: company_id für Multi-Tenant Isolation
    company_id = await get_user_company_id(db, current_user)

    service = WorkflowService(db)

    workflow = await service.update_workflow(
        workflow_id=workflow_id,
        user_id=current_user.id,
        company_id=company_id,
        **data.model_dump(exclude_unset=True),
    )

    if not workflow:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workflow nicht gefunden oder keine Berechtigung",
        )

    return WorkflowResponse.model_validate(workflow)


@router.delete(
    "/{workflow_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    summary="Workflow löschen",
)
async def delete_workflow(
    workflow_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Response:
    """Löscht einen Workflow."""
    # SECURITY FIX: company_id für Multi-Tenant Isolation
    company_id = await get_user_company_id(db, current_user)

    service = WorkflowService(db)

    success = await service.delete_workflow(
        workflow_id=workflow_id,
        user_id=current_user.id,
        company_id=company_id,
    )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workflow nicht gefunden oder keine Berechtigung",
        )

    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{workflow_id}/duplicate",
    response_model=WorkflowResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Workflow duplizieren",
)
async def duplicate_workflow(
    workflow_id: UUID,
    new_name: Optional[str] = Query(None, description="Name für Kopie"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> WorkflowResponse:
    """Dupliziert einen Workflow."""
    # SECURITY FIX: company_id für Multi-Tenant Isolation
    company_id = await get_user_company_id(db, current_user)

    service = WorkflowService(db)

    duplicate = await service.duplicate_workflow(
        workflow_id=workflow_id,
        user_id=current_user.id,
        company_id=company_id,
        new_name=new_name,
    )

    if not duplicate:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workflow nicht gefunden",
        )

    return WorkflowResponse.model_validate(duplicate)


@router.patch(
    "/{workflow_id}/toggle",
    response_model=WorkflowResponse,
    summary="Workflow aktivieren/deaktivieren",
)
async def toggle_workflow(
    workflow_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> WorkflowResponse:
    """Aktiviert oder deaktiviert einen Workflow."""
    # SECURITY FIX: company_id für Multi-Tenant Isolation
    company_id = await get_user_company_id(db, current_user)

    service = WorkflowService(db)

    workflow = await service.toggle_workflow(
        workflow_id=workflow_id,
        user_id=current_user.id,
        company_id=company_id,
    )

    if not workflow:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workflow nicht gefunden oder keine Berechtigung",
        )

    return WorkflowResponse.model_validate(workflow)


@router.post(
    "/{workflow_id}/validate",
    response_model=ValidationResult,
    summary="Workflow validieren",
)
async def validate_workflow(
    workflow_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ValidationResult:
    """Validiert einen Workflow."""
    # SECURITY FIX: company_id für Multi-Tenant Isolation
    company_id = await get_user_company_id(db, current_user)

    service = WorkflowService(db)

    result = await service.validate_workflow(
        workflow_id=workflow_id,
        user_id=current_user.id,
        company_id=company_id,
    )

    return ValidationResult(**result)


# =============================================================================
# Workflow Steps Endpoints (6)
# =============================================================================


@router.get(
    "/{workflow_id}/steps",
    response_model=List[StepResponse],
    summary="Steps abrufen",
)
async def get_workflow_steps(
    workflow_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> List[StepResponse]:
    """Ruft alle Steps eines Workflows ab."""
    # SECURITY FIX: company_id für Multi-Tenant Isolation
    company_id = await get_user_company_id(db, current_user)

    service = WorkflowService(db)

    # Workflow-Zugriff prüfen (mit company_id)
    workflow = await service.get_workflow(
        workflow_id, current_user.id, company_id=company_id, include_steps=False
    )
    if not workflow:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workflow nicht gefunden",
        )

    steps = await service.get_steps(workflow_id, user_id=current_user.id, company_id=company_id)

    return [StepResponse.model_validate(s) for s in steps]


@router.post(
    "/{workflow_id}/steps",
    response_model=StepResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Step erstellen",
)
async def create_step(
    workflow_id: UUID,
    data: StepCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> StepResponse:
    """Erstellt einen neuen Step."""
    # SECURITY FIX: company_id für Multi-Tenant Isolation
    company_id = await get_user_company_id(db, current_user)

    service = WorkflowService(db)

    # Workflow-Zugriff prüfen (mit company_id)
    workflow = await service.get_workflow(
        workflow_id, current_user.id, company_id=company_id, include_steps=False
    )
    if not workflow or workflow.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workflow nicht gefunden oder keine Berechtigung",
        )

    step = await service.create_step(
        workflow_id=workflow_id,
        step_order=data.step_order,
        step_type=data.step_type,
        user_id=current_user.id,
        company_id=company_id,
        step_name=data.step_name,
        config=data.config,
        retry_on_failure=data.retry_on_failure,
        max_retries=data.max_retries,
        position_x=data.position_x,
        position_y=data.position_y,
    )

    return StepResponse.model_validate(step)


@router.put(
    "/{workflow_id}/steps/{step_id}",
    response_model=StepResponse,
    summary="Step aktualisieren",
)
async def update_step(
    workflow_id: UUID,
    step_id: UUID,
    data: StepUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> StepResponse:
    """Aktualisiert einen Step."""
    # SECURITY FIX: company_id für Multi-Tenant Isolation
    company_id = await get_user_company_id(db, current_user)

    service = WorkflowService(db)

    # Workflow-Zugriff prüfen (mit company_id)
    workflow = await service.get_workflow(
        workflow_id, current_user.id, company_id=company_id, include_steps=False
    )
    if not workflow or workflow.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workflow nicht gefunden oder keine Berechtigung",
        )

    step = await service.update_step(
        step_id=step_id,
        user_id=current_user.id,
        company_id=company_id,
        **data.model_dump(exclude_unset=True),
    )

    if not step:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Step nicht gefunden",
        )

    return StepResponse.model_validate(step)


@router.delete(
    "/{workflow_id}/steps/{step_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    summary="Step löschen",
)
async def delete_step(
    workflow_id: UUID,
    step_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Response:
    """Löscht einen Step."""
    # SECURITY FIX: company_id für Multi-Tenant Isolation
    company_id = await get_user_company_id(db, current_user)

    service = WorkflowService(db)

    # Workflow-Zugriff prüfen (mit company_id)
    workflow = await service.get_workflow(
        workflow_id, current_user.id, company_id=company_id, include_steps=False
    )
    if not workflow or workflow.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workflow nicht gefunden oder keine Berechtigung",
        )

    success = await service.delete_step(step_id, user_id=current_user.id, company_id=company_id)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Step nicht gefunden",
        )

    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{workflow_id}/steps/reorder",
    response_model=List[StepResponse],
    summary="Steps neu ordnen",
)
async def reorder_steps(
    workflow_id: UUID,
    step_orders: List[StepReorderItem],
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> List[StepResponse]:
    """Ordnet Steps neu an."""
    # SECURITY FIX: company_id für Multi-Tenant Isolation
    company_id = await get_user_company_id(db, current_user)

    service = WorkflowService(db)

    # Workflow-Zugriff prüfen (mit company_id)
    workflow = await service.get_workflow(
        workflow_id, current_user.id, company_id=company_id, include_steps=False
    )
    if not workflow or workflow.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workflow nicht gefunden oder keine Berechtigung",
        )

    await service.reorder_steps(
        workflow_id=workflow_id,
        step_orders=[{"step_id": str(s.step_id), "step_order": s.step_order} for s in step_orders],
        user_id=current_user.id,
        company_id=company_id,
    )

    steps = await service.get_steps(workflow_id, user_id=current_user.id, company_id=company_id)

    return [StepResponse.model_validate(s) for s in steps]


@router.post(
    "/{workflow_id}/steps/batch",
    response_model=List[StepResponse],
    summary="Steps batch-aktualisieren",
)
async def batch_update_steps(
    workflow_id: UUID,
    steps_data: List[Dict[str, object]],
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> List[StepResponse]:
    """Aktualisiert mehrere Steps (ReactFlow Bulk-Update)."""
    # SECURITY FIX: company_id für Multi-Tenant Isolation
    company_id = await get_user_company_id(db, current_user)

    service = WorkflowService(db)

    # Workflow-Zugriff prüfen (mit company_id)
    workflow = await service.get_workflow(
        workflow_id, current_user.id, company_id=company_id, include_steps=False
    )
    if not workflow or workflow.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workflow nicht gefunden oder keine Berechtigung",
        )

    updated_steps = await service.batch_update_steps(
        workflow_id=workflow_id,
        steps_data=steps_data,
        user_id=current_user.id,
        company_id=company_id,
    )

    return [StepResponse.model_validate(s) for s in updated_steps]


# =============================================================================
# Execution Endpoints (8)
# =============================================================================


@router.post(
    "/{workflow_id}/execute",
    response_model=ExecutionResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Workflow ausführen",
)
async def execute_workflow(
    workflow_id: UUID,
    data: ExecutionStart,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ExecutionResponse:
    """Startet eine Workflow-Ausführung."""
    # SECURITY FIX: company_id für Multi-Tenant Isolation
    company_id = await get_user_company_id(db, current_user)

    step_executor = WorkflowStepExecutor(db)
    execution_service = WorkflowExecutionService(db, step_executor)

    try:
        execution = await execution_service.start_execution(
            workflow_id=workflow_id,
            user_id=current_user.id,
            company_id=company_id,
            document_id=data.document_id,
            initial_variables=data.variables,
        )

        return ExecutionResponse.model_validate(execution)

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=safe_error_detail(e, "Workflow-Ausführung"),
        )


@router.get(
    "/{workflow_id}/executions",
    response_model=ExecutionListResponse,
    summary="Ausführungen abrufen",
)
async def get_workflow_executions(
    workflow_id: UUID,
    status_filter: Optional[str] = Query(None, alias="status", description="Filter nach Status"),
    page: int = Query(1, ge=1, description="Seitennummer (1-basiert)"),
    per_page: int = Query(50, ge=1, le=100, description="Eintraege pro Seite"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ExecutionListResponse:
    """Ruft Ausführungen eines Workflows ab."""
    # SECURITY: company_id für Multi-Tenant Isolation
    company_id = await get_user_company_id(db, current_user)
    execution_service = WorkflowExecutionService(db)

    executions, total = await execution_service.list_executions(
        company_id=company_id,  # SECURITY: Multi-Tenant Filter
        workflow_id=workflow_id,
        user_id=current_user.id,
        status=status_filter,
        offset=(page - 1) * per_page,
        limit=per_page,
    )

    return ExecutionListResponse(
        items=[ExecutionResponse.model_validate(e) for e in executions],
        total=total,
        page=page,
        per_page=per_page,
    )


@router.get(
    "/executions/{execution_id}",
    response_model=ExecutionResponse,
    summary="Ausführung abrufen",
)
async def get_execution(
    execution_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ExecutionResponse:
    """Ruft eine Ausführung nach ID ab."""
    # SECURITY: company_id für Multi-Tenant Isolation
    company_id = await get_user_company_id(db, current_user)
    execution_service = WorkflowExecutionService(db)

    execution = await execution_service.get_execution(
        execution_id=execution_id,
        user_id=current_user.id,
        company_id=company_id,  # SECURITY: Multi-Tenant Validation
    )

    if not execution:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ausführung nicht gefunden",
        )

    return ExecutionResponse.model_validate(execution)


@router.get(
    "/executions/{execution_id}/steps",
    response_model=List[StepExecutionResponse],
    summary="Step-Ausführungen abrufen",
)
async def get_step_executions(
    execution_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> List[StepExecutionResponse]:
    """Ruft Step-Ausführungen ab."""
    # SECURITY: company_id für Multi-Tenant Isolation
    company_id = await get_user_company_id(db, current_user)
    execution_service = WorkflowExecutionService(db)

    # Execution-Zugriff prüfen (mit company_id Validierung)
    execution = await execution_service.get_execution(
        execution_id, current_user.id, company_id=company_id
    )
    if not execution:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ausführung nicht gefunden",
        )

    step_executions = await execution_service.get_step_executions(
        execution_id, user_id=current_user.id, company_id=company_id
    )

    return [StepExecutionResponse.model_validate(se) for se in step_executions]


@router.post(
    "/executions/{execution_id}/pause",
    response_model=Dict[str, bool],
    summary="Ausführung pausieren",
)
async def pause_execution(
    execution_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, bool]:
    """Pausiert eine laufende Ausführung."""
    # SECURITY: company_id für Multi-Tenant Isolation
    company_id = await get_user_company_id(db, current_user)
    execution_service = WorkflowExecutionService(db)

    success = await execution_service.pause_execution(
        execution_id=execution_id,
        user_id=current_user.id,
        company_id=company_id,  # SECURITY: Multi-Tenant Validation
    )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ausführung kann nicht pausiert werden",
        )

    return {"paused": True}


@router.post(
    "/executions/{execution_id}/resume",
    response_model=Dict[str, bool],
    summary="Ausführung fortsetzen",
)
async def resume_execution(
    execution_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, bool]:
    """Setzt eine pausierte Ausführung fort."""
    # SECURITY: company_id für Multi-Tenant Isolation
    company_id = await get_user_company_id(db, current_user)
    step_executor = WorkflowStepExecutor(db)
    execution_service = WorkflowExecutionService(db, step_executor)

    success = await execution_service.resume_execution(
        execution_id=execution_id,
        user_id=current_user.id,
        company_id=company_id,  # SECURITY: Multi-Tenant Validation
    )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ausführung kann nicht fortgesetzt werden",
        )

    return {"resumed": True}


@router.post(
    "/executions/{execution_id}/cancel",
    response_model=Dict[str, bool],
    summary="Ausführung abbrechen",
)
async def cancel_execution(
    execution_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, bool]:
    """Bricht eine Ausführung ab."""
    # SECURITY: company_id für Multi-Tenant Isolation
    company_id = await get_user_company_id(db, current_user)
    execution_service = WorkflowExecutionService(db)

    success = await execution_service.cancel_execution(
        execution_id=execution_id,
        user_id=current_user.id,
        company_id=company_id,  # SECURITY: Multi-Tenant Validation
    )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ausführung kann nicht abgebrochen werden",
        )

    return {"cancelled": True}


@router.post(
    "/executions/{execution_id}/retry",
    response_model=ExecutionResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Ausführung wiederholen",
)
async def retry_execution(
    execution_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ExecutionResponse:
    """Wiederholt eine fehlgeschlagene Ausführung."""
    # SECURITY: company_id für Multi-Tenant Isolation
    company_id = await get_user_company_id(db, current_user)
    step_executor = WorkflowStepExecutor(db)
    execution_service = WorkflowExecutionService(db, step_executor)

    new_execution = await execution_service.retry_execution(
        execution_id=execution_id,
        user_id=current_user.id,
        company_id=company_id,  # SECURITY: Multi-Tenant Validation
    )

    if not new_execution:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ausführung kann nicht wiederholt werden",
        )

    return ExecutionResponse.model_validate(new_execution)


# =============================================================================
# Template Endpoints (4)
# =============================================================================


@router.get(
    "/templates",
    response_model=List[WorkflowResponse],
    summary="Templates auflisten",
)
async def list_templates(
    category: Optional[str] = Query(None, description="Filter nach Kategorie"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> List[WorkflowResponse]:
    """Listet verfügbare Workflow-Templates."""
    # SECURITY FIX: company_id für Multi-Tenant Isolation
    company_id = await get_user_company_id(db, current_user)

    service = WorkflowService(db)

    templates = await service.list_templates(company_id=company_id, category=category)

    return [WorkflowResponse.model_validate(t) for t in templates]


@router.get(
    "/templates/{template_id}",
    response_model=WorkflowResponse,
    summary="Template abrufen",
)
async def get_template(
    template_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> WorkflowResponse:
    """Ruft ein Template nach ID ab."""
    # SECURITY FIX: company_id für Multi-Tenant Isolation
    # Templates können company-spezifisch oder global (NULL) sein
    company_id = await get_user_company_id(db, current_user)

    service = WorkflowService(db)

    # Template laden - entweder Company-spezifisch oder global
    from sqlalchemy import select, and_, or_
    from app.db.models import Workflow
    from sqlalchemy.orm import selectinload

    query = (
        select(Workflow)
        .where(
            and_(
                Workflow.id == template_id,
                Workflow.is_template == True,  # noqa: E712
                or_(
                    Workflow.company_id == company_id,
                    Workflow.company_id.is_(None),  # Globale Templates
                ),
            )
        )
        .options(selectinload(Workflow.steps))
    )
    result = await db.execute(query)
    template = result.scalar_one_or_none()

    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Template nicht gefunden",
        )

    return WorkflowResponse.model_validate(template)


@router.post(
    "/templates/{template_id}/instantiate",
    response_model=WorkflowResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Template instanziieren",
)
async def instantiate_template(
    template_id: UUID,
    data: TemplateInstantiate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> WorkflowResponse:
    """Erstellt einen Workflow aus einem Template."""
    # SECURITY FIX: company_id aus User-Context, NICHT aus Request-Body (IDOR Prevention)
    company_id = await get_user_company_id(db, current_user)
    if not company_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Benutzer muss einer Firma zugeordnet sein",
        )

    service = WorkflowService(db)

    workflow = await service.instantiate_template(
        template_id=template_id,
        user_id=current_user.id,
        name=data.name,
        company_id=company_id,  # SECURITY: Aus User-Context, nicht Request
    )

    if not workflow:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Template nicht gefunden",
        )

    return WorkflowResponse.model_validate(workflow)


@router.post(
    "/templates",
    response_model=WorkflowResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Template erstellen (Admin)",
)
async def create_template(
    data: WorkflowCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> WorkflowResponse:
    """Erstellt ein neues Workflow-Template (nur Admins)."""
    # Admin-Check durch require_admin Dependency sichergestellt

    service = WorkflowService(db)

    workflow = await service.create_workflow(
        user_id=current_user.id,
        name=data.name,
        trigger_type=data.trigger_type,
        trigger_config=data.trigger_config,
        nodes=data.nodes,
        edges=data.edges,
        description=data.description,
        variables=data.variables,
        max_concurrent_executions=data.max_concurrent_executions,
        timeout_seconds=data.timeout_seconds,
        retry_config=data.retry_config,
    )

    # Als Template markieren
    workflow.is_template = True
    await db.commit()
    await db.refresh(workflow)

    return WorkflowResponse.model_validate(workflow)


# =============================================================================
# Webhook Trigger Endpoints (3)
# =============================================================================


@router.post(
    "/trigger/{webhook_path:path}",
    response_model=Dict[str, object],
    summary="Webhook Trigger",
)
async def webhook_trigger(
    webhook_path: str,
    payload: WebhookPayload,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> Dict[str, object]:
    """Empfängt Webhook-Trigger von externen Systemen."""
    step_executor = WorkflowStepExecutor(db)
    execution_service = WorkflowExecutionService(db, step_executor)
    trigger_service = WorkflowTriggerService(db, execution_service)

    # Headers extrahieren
    headers = dict(request.headers)

    execution_id = await trigger_service.handle_webhook(
        webhook_path=webhook_path,
        payload=payload.data,
        headers=headers,
    )

    if not execution_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Kein Workflow für diesen Webhook gefunden",
        )

    return {
        "success": True,
        "execution_id": str(execution_id),
    }


@router.get(
    "/{workflow_id}/webhook-config",
    response_model=Dict[str, object],
    summary="Webhook-Konfiguration abrufen",
)
async def get_webhook_config(
    workflow_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, object]:
    """Ruft die Webhook-Konfiguration eines Workflows ab."""
    # SECURITY FIX: company_id für Multi-Tenant Isolation
    company_id = await get_user_company_id(db, current_user)

    trigger_service = WorkflowTriggerService(db)

    config = await trigger_service.get_webhook_config(
        workflow_id=workflow_id,
        user_id=current_user.id,
        company_id=company_id,
    )

    if not config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workflow nicht gefunden oder kein Webhook-Trigger",
        )

    return config


@router.post(
    "/{workflow_id}/regenerate-webhook-secret",
    response_model=Dict[str, str],
    summary="Webhook-Secret regenerieren",
)
async def regenerate_webhook_secret(
    workflow_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, str]:
    """Generiert ein neues Webhook-Secret."""
    # SECURITY FIX: company_id für Multi-Tenant Isolation
    company_id = await get_user_company_id(db, current_user)

    trigger_service = WorkflowTriggerService(db)

    new_secret = await trigger_service.regenerate_webhook_secret(
        workflow_id=workflow_id,
        user_id=current_user.id,
        company_id=company_id,
    )

    if not new_secret:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workflow nicht gefunden oder keine Berechtigung",
        )

    return {"secret": new_secret}


# =============================================================================
# Statistics Endpoints (3)
# =============================================================================


@router.get(
    "/{workflow_id}/stats",
    response_model=WorkflowStats,
    summary="Workflow-Statistiken",
)
async def get_workflow_stats(
    workflow_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> WorkflowStats:
    """Ruft Statistiken für einen Workflow ab."""
    # SECURITY FIX: company_id für Multi-Tenant Isolation
    company_id = await get_user_company_id(db, current_user)

    service = WorkflowService(db)

    stats = await service.get_workflow_stats(
        workflow_id=workflow_id,
        user_id=current_user.id,
        company_id=company_id,
    )

    if not stats:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workflow nicht gefunden",
        )

    return WorkflowStats(**stats)


@router.get(
    "/stats/overview",
    response_model=OverviewStats,
    summary="Gesamt-Statistiken",
)
async def get_overview_stats(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> OverviewStats:
    """Ruft Gesamt-Statistiken ab."""
    from sqlalchemy import func, and_, or_
    from app.db.models import Workflow, WorkflowExecution

    # SECURITY: company_id für Multi-Tenant Isolation
    company_id = await get_user_company_id(db, current_user)

    # Workflows zaehlen - filtert nach user_id UND company_id
    workflow_conditions = [Workflow.user_id == current_user.id]
    if company_id:
        workflow_conditions.append(Workflow.company_id == company_id)

    # BUGFIX (2026-06-12): Ein lokaler sqlalchemy-Integer-Reimport NACH der
    # Nutzung shadowte den Modulimport (Z.35) -> UnboundLocalError -> 500.
    workflow_query = select(
        func.count(Workflow.id).label("total"),
        func.sum(func.cast(Workflow.is_active == True, Integer)).label("active"),  # noqa: E712
    ).where(and_(*workflow_conditions))

    result = await db.execute(workflow_query)
    workflow_row = result.one()

    # SECURITY: Subquery für Workflow-IDs mit company_id Filter
    workflow_ids_subquery = select(Workflow.id).where(and_(*workflow_conditions)).scalar_subquery()

    # BUGFIX (2026-06-12): WorkflowExecution hat KEIN user_id-Feld (nur
    # triggered_by_id, das bei Auto-Triggern NULL ist) -> AttributeError -> 500.
    # User-Scope laeuft korrekt ueber die Workflow-Ownership-Subquery
    # (Workflow.user_id + optional company_id), die ALLE Executions der
    # eigenen Workflows erfasst (auch automatisch getriggerte).
    exec_conditions = [WorkflowExecution.workflow_id.in_(workflow_ids_subquery)]

    exec_query = select(
        func.count(WorkflowExecution.id).label("total"),
    ).where(and_(*exec_conditions))

    exec_result = await db.execute(exec_query)
    exec_row = exec_result.one()

    # Executions heute
    from datetime import date

    today_conditions = exec_conditions + [func.date(WorkflowExecution.started_at) == date.today()]
    today_query = select(
        func.count(WorkflowExecution.id).label("today"),
    ).where(and_(*today_conditions))

    today_result = await db.execute(today_query)
    today_row = today_result.one()

    # Success Rate
    success_conditions = exec_conditions + [WorkflowExecution.status == "completed"]
    success_query = select(
        func.count(WorkflowExecution.id).label("completed"),
    ).where(and_(*success_conditions))

    success_result = await db.execute(success_query)
    success_row = success_result.one()

    total_execs = exec_row.total or 0
    completed = success_row.completed or 0

    return OverviewStats(
        total_workflows=workflow_row.total or 0,
        active_workflows=workflow_row.active or 0,
        total_executions=total_execs,
        executions_today=today_row.today or 0,
        success_rate=(completed / total_execs * 100) if total_execs > 0 else 0,
    )


@router.get(
    "/stats/execution-history",
    response_model=List[Dict[str, object]],
    summary="Ausführungs-Historie",
)
async def get_execution_history(
    days: int = Query(30, ge=1, le=365, description="Anzahl Tage"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> List[Dict[str, object]]:
    """Ruft Ausführungs-Historie ab."""
    from sqlalchemy import func, and_, Integer
    from datetime import datetime, timedelta, timezone
    from app.db.models import Workflow, WorkflowExecution

    # SECURITY: company_id für Multi-Tenant Isolation
    company_id = await get_user_company_id(db, current_user)

    start_date = datetime.now(timezone.utc) - timedelta(days=days)

    # BUGFIX (2026-06-12): WorkflowExecution hat KEIN user_id-Feld (nur
    # triggered_by_id, bei Auto-Triggern NULL) -> AttributeError -> 500.
    # User-Scope ueber Workflow-Ownership-Subquery (Workflow.user_id +
    # optional company_id) - erfasst auch automatisch getriggerte Executions.
    workflow_conditions = [Workflow.user_id == current_user.id]
    if company_id:
        workflow_conditions.append(Workflow.company_id == company_id)

    workflow_ids_subquery = (
        select(Workflow.id).where(and_(*workflow_conditions)).scalar_subquery()
    )

    conditions = [
        WorkflowExecution.workflow_id.in_(workflow_ids_subquery),
        WorkflowExecution.started_at >= start_date,
    ]

    query = (
        select(
            func.date(WorkflowExecution.started_at).label("date"),
            func.count(WorkflowExecution.id).label("total"),
            func.sum(
                func.cast(WorkflowExecution.status == "completed", Integer)
            ).label("completed"),
            func.sum(
                func.cast(WorkflowExecution.status == "failed", Integer)
            ).label("failed"),
        )
        .where(and_(*conditions))
        .group_by(func.date(WorkflowExecution.started_at))
        .order_by(func.date(WorkflowExecution.started_at))
    )

    result = await db.execute(query)
    rows = result.all()

    return [
        {
            "date": str(row.date),
            "total": row.total or 0,
            "completed": row.completed or 0,
            "failed": row.failed or 0,
        }
        for row in rows
    ]


# =============================================================================
# Utility Endpoints
# =============================================================================


@router.get(
    "/operators",
    response_model=List[Dict[str, str]],
    summary="Verfügbare Operatoren",
)
async def get_available_operators(
    current_user: User = Depends(get_current_user),
) -> List[Dict[str, str]]:
    """Gibt verfügbare Bedingungs-Operatoren zurück."""
    evaluator = ConditionEvaluator()
    return evaluator.get_available_operators()


@router.get(
    "/fields",
    response_model=Dict[str, str],
    summary="Verfügbare Felder",
)
async def get_available_fields(
    current_user: User = Depends(get_current_user),
) -> Dict[str, str]:
    """Gibt verfügbare Bedingungs-Felder zurück."""
    evaluator = ConditionEvaluator()
    return evaluator.get_available_fields()


# =============================================================================
# Workflow Execution Visualization (Phase B)
# =============================================================================


class NodeState(BaseModel):
    """Status eines einzelnen Workflow-Knotens."""

    node_id: str
    node_type: str  # action, condition, branch, delay, parallel, loop
    node_name: str
    status: str  # pending, active, completed, failed, skipped, warning
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_ms: Optional[int] = None
    error_message: Optional[str] = None
    sla_deadline: Optional[datetime] = None
    sla_status: Optional[str] = None  # ok, warning, breached


class ExecutionStateResponse(BaseModel):
    """Aktueller Ausführungsstatus eines Workflows."""

    instance_id: UUID
    workflow_id: UUID
    workflow_name: str
    status: str  # pending, running, completed, failed, cancelled
    progress_percent: int
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    nodes: List[NodeState]  # Alle Knoten mit ihrem Ausführungsstatus
    active_step_ids: List[str]  # Aktuell ausgeführte Schritte


class TimelineEntry(BaseModel):
    """Einzelner Eintrag in der Ausführungs-Zeitleiste."""

    step_id: str
    step_name: str
    step_type: str
    status: str
    started_at: datetime
    completed_at: Optional[datetime] = None
    duration_ms: Optional[int] = None
    input_summary: Optional[str] = None  # Kurze Beschreibung des Inputs
    output_summary: Optional[str] = None  # Kurze Beschreibung des Outputs
    error_message: Optional[str] = None


class ExecutionMetrics(BaseModel):
    """Performance-Metriken einer Workflow-Ausführung."""

    instance_id: UUID
    total_duration_ms: Optional[int] = None
    steps_completed: int
    steps_failed: int
    steps_pending: int
    avg_step_duration_ms: Optional[float] = None
    slowest_step: Optional[str] = None
    slowest_step_duration_ms: Optional[int] = None
    bottleneck_step: Optional[str] = None  # Step mit längster Wartezeit


# Ab diesem Anteil der SLA-Zeit gilt ein laufender Schritt als "warning"
_SLA_WARNING_RATIO = 0.8


def _compute_step_sla(
    step: object,
    started_at: Optional[datetime],
    completed_at: Optional[datetime],
) -> "tuple[Optional[datetime], Optional[str]]":
    """Berechnet SLA-Deadline und -Status fuer einen Workflow-Schritt.

    SLA-Quelle ist die Step-Config: "sla_minutes" (bevorzugt) oder
    "timeout_seconds". Ist keine Step-SLA konfiguriert oder hat der
    Schritt noch nicht gestartet, wird ehrlich (None, None) geliefert.

    Status:
    - "breached": Abschluss (bzw. jetzt) liegt hinter der Deadline
    - "warning":  >= 80% der SLA-Zeit verbraucht
    - "ok":       innerhalb der SLA
    """
    from datetime import timedelta, timezone as _tz

    config = getattr(step, "config", None) or {}

    sla_seconds: Optional[float] = None
    sla_minutes = config.get("sla_minutes")
    if isinstance(sla_minutes, (int, float)) and sla_minutes > 0:
        sla_seconds = float(sla_minutes) * 60.0
    else:
        timeout_seconds = config.get("timeout_seconds")
        if isinstance(timeout_seconds, (int, float)) and timeout_seconds > 0:
            sla_seconds = float(timeout_seconds)

    if sla_seconds is None or started_at is None:
        return None, None

    # Naive Zeitstempel defensiv als UTC interpretieren
    start = started_at if started_at.tzinfo else started_at.replace(tzinfo=_tz.utc)
    reference_time = completed_at or datetime.now(_tz.utc)
    if reference_time.tzinfo is None:
        reference_time = reference_time.replace(tzinfo=_tz.utc)

    deadline = start + timedelta(seconds=sla_seconds)

    if reference_time > deadline:
        sla_status = "breached"
    elif (reference_time - start).total_seconds() >= _SLA_WARNING_RATIO * sla_seconds:
        sla_status = "warning"
    else:
        sla_status = "ok"

    return deadline, sla_status


@router.get(
    "/executions/{instance_id}/state",
    response_model=ExecutionStateResponse,
    summary="Aktuellen Ausführungsstatus abrufen",
)
@limiter.limit("30/minute", key_func=get_user_identifier)
async def get_execution_state(
    request: Request,
    instance_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ExecutionStateResponse:
    """
    Ruft den aktuellen Ausführungsstatus ab.

    Gibt detaillierte Informationen über alle Knoten/Schritte zurück,
    inklusive Status, Timing und Fehler.
    """
    from sqlalchemy import select, and_
    from sqlalchemy.orm import selectinload
    from app.db.models import WorkflowExecution, WorkflowStepExecution, Workflow, WorkflowStep

    # SECURITY: company_id für Multi-Tenant Isolation
    company_id = await get_user_company_id(db, current_user)

    # Lade Execution mit allen Beziehungen
    query = (
        select(WorkflowExecution)
        .where(WorkflowExecution.id == instance_id)
        .options(
            selectinload(WorkflowExecution.workflow).selectinload(Workflow.steps),
            selectinload(WorkflowExecution.step_executions),
        )
    )
    result = await db.execute(query)
    execution = result.scalar_one_or_none()

    if not execution:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ausführung nicht gefunden",
        )

    # SECURITY: Verify ownership
    if execution.triggered_by_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Keine Berechtigung für diese Ausführung",
        )

    # SECURITY: Verify company_id if set
    if company_id and execution.workflow.company_id != company_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Keine Berechtigung für diese Ausführung",
        )

    # Build node states from step executions
    nodes: List[NodeState] = []
    active_step_ids: List[str] = []

    # Create map of step_id -> step_execution
    step_exec_map = {str(se.workflow_step_id): se for se in execution.step_executions}

    for step in execution.workflow.steps:
        step_exec = step_exec_map.get(str(step.id))

        # Determine node status
        if step_exec:
            node_status = step_exec.status
            started_at = step_exec.started_at
            completed_at = step_exec.completed_at
            duration_ms = step_exec.duration_ms
            error_message = step_exec.error_message
        else:
            node_status = "pending"
            started_at = None
            completed_at = None
            duration_ms = None
            error_message = None

        # Track active steps
        if node_status == "running":
            active_step_ids.append(str(step.id))

        # SLA pro Knoten (2026-06-12): abgeleitet aus der Step-Config
        # ("sla_minutes" bevorzugt, sonst "timeout_seconds"). Das
        # Workflow-weite Workflow.timeout_seconds gilt fuer die GESAMTE
        # Ausfuehrung und wird bewusst NICHT pro Knoten interpretiert.
        # Ohne Step-SLA und ohne Startzeit bleibt der Wert ehrlich None
        # (kein erfundener Status).
        sla_deadline, sla_status = _compute_step_sla(
            step, started_at, completed_at
        )

        nodes.append(
            NodeState(
                node_id=str(step.id),
                node_type=step.step_type,
                node_name=step.name,
                status=node_status,
                started_at=started_at,
                completed_at=completed_at,
                duration_ms=duration_ms,
                error_message=error_message,
                sla_deadline=sla_deadline,
                sla_status=sla_status,
            )
        )

    return ExecutionStateResponse(
        instance_id=execution.id,
        workflow_id=execution.workflow_id,
        workflow_name=execution.workflow.name,
        status=execution.status,
        progress_percent=execution.progress_percent,
        started_at=execution.started_at,
        completed_at=execution.completed_at,
        nodes=nodes,
        active_step_ids=active_step_ids,
    )


@router.get(
    "/executions/{instance_id}/timeline",
    response_model=List[TimelineEntry],
    summary="Ausführungs-Zeitleiste abrufen",
)
@limiter.limit("30/minute", key_func=get_user_identifier)
async def get_execution_timeline(
    request: Request,
    instance_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> List[TimelineEntry]:
    """
    Ruft die geordnete Ausführungs-Zeitleiste ab.

    Gibt alle Schritte in chronologischer Reihenfolge zurück.
    """
    from sqlalchemy import select, and_
    from sqlalchemy.orm import selectinload
    from app.db.models import WorkflowExecution, WorkflowStepExecution, WorkflowStep

    # SECURITY: company_id für Multi-Tenant Isolation
    company_id = await get_user_company_id(db, current_user)

    # Lade Execution mit Step-Executions
    query = (
        select(WorkflowExecution)
        .where(WorkflowExecution.id == instance_id)
        .options(
            selectinload(WorkflowExecution.step_executions).selectinload(
                WorkflowStepExecution.workflow_step
            )
        )
    )
    result = await db.execute(query)
    execution = result.scalar_one_or_none()

    if not execution:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ausführung nicht gefunden",
        )

    # SECURITY: Verify ownership
    if execution.triggered_by_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Keine Berechtigung für diese Ausführung",
        )

    # Build timeline entries
    timeline: List[TimelineEntry] = []

    for step_exec in sorted(execution.step_executions, key=lambda x: x.execution_order):
        if not step_exec.started_at:
            continue  # Skip steps that haven't started yet

        # Generate summaries from input/output data (simplified)
        input_summary = None
        output_summary = None

        if step_exec.input_data:
            input_summary = f"{len(step_exec.input_data)} Felder"

        if step_exec.output_data:
            output_summary = f"{len(step_exec.output_data)} Felder"

        timeline.append(
            TimelineEntry(
                step_id=str(step_exec.workflow_step_id),
                step_name=step_exec.workflow_step.name,
                step_type=step_exec.workflow_step.step_type,
                status=step_exec.status,
                started_at=step_exec.started_at,
                completed_at=step_exec.completed_at,
                duration_ms=step_exec.duration_ms,
                input_summary=input_summary,
                output_summary=output_summary,
                error_message=step_exec.error_message,
            )
        )

    return timeline


@router.get(
    "/executions/{instance_id}/metrics",
    response_model=ExecutionMetrics,
    summary="Performance-Metriken abrufen",
)
@limiter.limit("30/minute", key_func=get_user_identifier)
async def get_execution_metrics(
    request: Request,
    instance_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ExecutionMetrics:
    """
    Ruft Performance-Metriken der Ausführung ab.

    Gibt Timing-Informationen, Engpaesse und Statistiken zurück.
    """
    from sqlalchemy import select, func
    from sqlalchemy.orm import selectinload
    from app.db.models import WorkflowExecution, WorkflowStepExecution

    # SECURITY: company_id für Multi-Tenant Isolation
    company_id = await get_user_company_id(db, current_user)

    # Lade Execution mit Step-Executions
    query = (
        select(WorkflowExecution)
        .where(WorkflowExecution.id == instance_id)
        .options(selectinload(WorkflowExecution.step_executions).selectinload(WorkflowStepExecution.workflow_step))
    )
    result = await db.execute(query)
    execution = result.scalar_one_or_none()

    if not execution:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ausführung nicht gefunden",
        )

    # SECURITY: Verify ownership
    if execution.triggered_by_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Keine Berechtigung für diese Ausführung",
        )

    # Calculate metrics
    steps_completed = sum(1 for se in execution.step_executions if se.status == "completed")
    steps_failed = sum(1 for se in execution.step_executions if se.status == "failed")
    steps_pending = sum(
        1 for se in execution.step_executions if se.status in ("pending", "running")
    )

    # Calculate average step duration (only completed steps)
    completed_steps = [se for se in execution.step_executions if se.status == "completed" and se.duration_ms]
    avg_step_duration_ms = None
    if completed_steps:
        avg_step_duration_ms = sum(se.duration_ms for se in completed_steps) / len(completed_steps)

    # Find slowest step
    slowest_step = None
    slowest_step_duration_ms = None
    if completed_steps:
        slowest = max(completed_steps, key=lambda x: x.duration_ms or 0)
        slowest_step = slowest.workflow_step.name
        slowest_step_duration_ms = slowest.duration_ms

    # Find bottleneck (step with longest wait time before starting)
    bottleneck_step = None
    max_wait_time = 0

    sorted_steps = sorted(execution.step_executions, key=lambda x: x.execution_order)
    for i, step_exec in enumerate(sorted_steps):
        if i == 0 or not step_exec.started_at:
            continue

        prev_step = sorted_steps[i - 1]
        if prev_step.completed_at and step_exec.started_at:
            wait_time = (step_exec.started_at - prev_step.completed_at).total_seconds()
            if wait_time > max_wait_time:
                max_wait_time = wait_time
                bottleneck_step = step_exec.workflow_step.name

    return ExecutionMetrics(
        instance_id=execution.id,
        total_duration_ms=execution.duration_ms,
        steps_completed=steps_completed,
        steps_failed=steps_failed,
        steps_pending=steps_pending,
        avg_step_duration_ms=avg_step_duration_ms,
        slowest_step=slowest_step,
        slowest_step_duration_ms=slowest_step_duration_ms,
        bottleneck_step=bottleneck_step,
    )
