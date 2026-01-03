# -*- coding: utf-8 -*-
"""Workflow API Endpoints.

32 Endpoints fuer Workflow-Automation:
- Workflow CRUD (8)
- Workflow Steps (6)
- Execution (8)
- Templates (4)
- Webhook Triggers (3)
- Statistics (3)
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user, get_db, require_admin
from app.db.models import User
from app.services.workflow import (
    ConditionEvaluator,
    WorkflowExecutionService,
    WorkflowService,
    WorkflowStepExecutor,
    WorkflowTriggerService,
)

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/workflows", tags=["workflows"])


# =============================================================================
# Pydantic Schemas
# =============================================================================


class WorkflowCreate(BaseModel):
    """Schema fuer Workflow-Erstellung."""

    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    trigger_type: str = Field(..., pattern="^(document_event|schedule|condition|manual|webhook)$")
    trigger_config: Dict[str, Any] = Field(default_factory=dict)
    nodes: Optional[List[Dict[str, Any]]] = None
    edges: Optional[List[Dict[str, Any]]] = None
    variables: Optional[Dict[str, Any]] = None
    max_concurrent_executions: int = Field(default=10, ge=1, le=100)
    timeout_seconds: int = Field(default=3600, ge=60, le=86400)
    retry_config: Optional[Dict[str, Any]] = None


class WorkflowUpdate(BaseModel):
    """Schema fuer Workflow-Update."""

    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    trigger_type: Optional[str] = Field(None, pattern="^(document_event|schedule|condition|manual|webhook)$")
    trigger_config: Optional[Dict[str, Any]] = None
    nodes: Optional[List[Dict[str, Any]]] = None
    edges: Optional[List[Dict[str, Any]]] = None
    variables: Optional[Dict[str, Any]] = None
    is_active: Optional[bool] = None
    max_concurrent_executions: Optional[int] = Field(None, ge=1, le=100)
    timeout_seconds: Optional[int] = Field(None, ge=60, le=86400)
    retry_config: Optional[Dict[str, Any]] = None


class WorkflowResponse(BaseModel):
    """Schema fuer Workflow-Antwort."""

    id: UUID
    user_id: UUID
    company_id: Optional[UUID] = None
    name: str
    description: Optional[str] = None
    trigger_type: str
    trigger_config: Dict[str, Any]
    nodes: List[Dict[str, Any]]
    edges: List[Dict[str, Any]]
    variables: Dict[str, Any]
    is_active: bool
    is_template: bool
    max_concurrent_executions: int
    timeout_seconds: int
    retry_config: Dict[str, Any]
    execution_count: int
    last_executed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class WorkflowListResponse(BaseModel):
    """Schema fuer Workflow-Liste."""

    items: List[WorkflowResponse]
    total: int
    offset: int
    limit: int


class StepCreate(BaseModel):
    """Schema fuer Step-Erstellung."""

    step_order: int = Field(..., ge=0)
    step_type: str = Field(..., pattern="^(condition|action|branch|delay|parallel|loop)$")
    step_name: Optional[str] = None
    config: Dict[str, Any] = Field(default_factory=dict)
    retry_on_failure: bool = True
    max_retries: int = Field(default=3, ge=0, le=10)
    position_x: float = 0.0
    position_y: float = 0.0


class StepUpdate(BaseModel):
    """Schema fuer Step-Update."""

    step_order: Optional[int] = Field(None, ge=0)
    step_type: Optional[str] = Field(None, pattern="^(condition|action|branch|delay|parallel|loop)$")
    step_name: Optional[str] = None
    config: Optional[Dict[str, Any]] = None
    retry_on_failure: Optional[bool] = None
    max_retries: Optional[int] = Field(None, ge=0, le=10)
    position_x: Optional[float] = None
    position_y: Optional[float] = None


class StepResponse(BaseModel):
    """Schema fuer Step-Antwort."""

    id: UUID
    workflow_id: UUID
    step_order: int
    step_type: str
    step_name: Optional[str] = None
    config: Dict[str, Any]
    retry_on_failure: bool
    max_retries: int
    position_x: float
    position_y: float
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class StepReorderItem(BaseModel):
    """Schema fuer Step-Neuordnung."""

    step_id: UUID
    step_order: int


class ExecutionStart(BaseModel):
    """Schema fuer Execution-Start."""

    document_id: Optional[UUID] = None
    variables: Optional[Dict[str, Any]] = None


class ExecutionResponse(BaseModel):
    """Schema fuer Execution-Antwort."""

    id: UUID
    workflow_id: UUID
    user_id: UUID
    document_id: Optional[UUID] = None
    status: str
    trigger_data: Dict[str, Any]
    variables: Dict[str, Any]
    current_step_id: Optional[UUID] = None
    progress_percent: int
    started_at: datetime
    completed_at: Optional[datetime] = None
    result: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None

    class Config:
        from_attributes = True


class ExecutionListResponse(BaseModel):
    """Schema fuer Execution-Liste."""

    items: List[ExecutionResponse]
    total: int
    offset: int
    limit: int


class StepExecutionResponse(BaseModel):
    """Schema fuer Step-Execution-Antwort."""

    id: UUID
    execution_id: UUID
    step_id: UUID
    status: str
    started_at: datetime
    completed_at: Optional[datetime] = None
    input_data: Optional[Dict[str, Any]] = None
    output_data: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None

    class Config:
        from_attributes = True


class TemplateInstantiate(BaseModel):
    """Schema fuer Template-Instanziierung."""

    name: Optional[str] = None
    company_id: Optional[UUID] = None


class WebhookPayload(BaseModel):
    """Schema fuer Webhook-Payload."""

    data: Dict[str, Any] = Field(default_factory=dict)


class ValidationResult(BaseModel):
    """Schema fuer Validierungsergebnis."""

    valid: bool
    errors: List[str]
    warnings: List[str]


class WorkflowStats(BaseModel):
    """Schema fuer Workflow-Statistiken."""

    workflow_id: UUID
    name: str
    is_active: bool
    execution_count: int
    last_executed_at: Optional[datetime] = None
    statistics: Dict[str, Any]


class OverviewStats(BaseModel):
    """Schema fuer Gesamt-Statistiken."""

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

    workflow = await service.create_workflow(
        user_id=current_user.id,
        name=data.name,
        trigger_type=data.trigger_type,
        trigger_config=data.trigger_config,
        nodes=data.nodes,
        edges=data.edges,
        description=data.description,
        company_id=current_user.company_id if hasattr(current_user, "company_id") else None,
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
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> WorkflowListResponse:
    """Listet Workflows mit optionalen Filtern."""
    service = WorkflowService(db)

    workflows, total = await service.list_workflows(
        user_id=current_user.id,
        company_id=current_user.company_id if hasattr(current_user, "company_id") else None,
        trigger_type=trigger_type,
        is_active=is_active,
        is_template=is_template,
        search=search,
        offset=offset,
        limit=limit,
    )

    return WorkflowListResponse(
        items=[WorkflowResponse.model_validate(w) for w in workflows],
        total=total,
        offset=offset,
        limit=limit,
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
    service = WorkflowService(db)

    workflow = await service.get_workflow(
        workflow_id=workflow_id,
        user_id=current_user.id,
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
    service = WorkflowService(db)

    workflow = await service.update_workflow(
        workflow_id=workflow_id,
        user_id=current_user.id,
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
    summary="Workflow loeschen",
)
async def delete_workflow(
    workflow_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    """Loescht einen Workflow."""
    service = WorkflowService(db)

    success = await service.delete_workflow(
        workflow_id=workflow_id,
        user_id=current_user.id,
    )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workflow nicht gefunden oder keine Berechtigung",
        )


@router.post(
    "/{workflow_id}/duplicate",
    response_model=WorkflowResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Workflow duplizieren",
)
async def duplicate_workflow(
    workflow_id: UUID,
    new_name: Optional[str] = Query(None, description="Name fuer Kopie"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> WorkflowResponse:
    """Dupliziert einen Workflow."""
    service = WorkflowService(db)

    duplicate = await service.duplicate_workflow(
        workflow_id=workflow_id,
        user_id=current_user.id,
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
    service = WorkflowService(db)

    workflow = await service.toggle_workflow(
        workflow_id=workflow_id,
        user_id=current_user.id,
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
    service = WorkflowService(db)

    result = await service.validate_workflow(workflow_id)

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
    service = WorkflowService(db)

    # Workflow-Zugriff pruefen
    workflow = await service.get_workflow(workflow_id, current_user.id, include_steps=False)
    if not workflow:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workflow nicht gefunden",
        )

    steps = await service.get_steps(workflow_id)

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
    service = WorkflowService(db)

    # Workflow-Zugriff pruefen
    workflow = await service.get_workflow(workflow_id, current_user.id, include_steps=False)
    if not workflow or workflow.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workflow nicht gefunden oder keine Berechtigung",
        )

    step = await service.create_step(
        workflow_id=workflow_id,
        step_order=data.step_order,
        step_type=data.step_type,
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
    service = WorkflowService(db)

    # Workflow-Zugriff pruefen
    workflow = await service.get_workflow(workflow_id, current_user.id, include_steps=False)
    if not workflow or workflow.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workflow nicht gefunden oder keine Berechtigung",
        )

    step = await service.update_step(
        step_id=step_id,
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
    summary="Step loeschen",
)
async def delete_step(
    workflow_id: UUID,
    step_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    """Loescht einen Step."""
    service = WorkflowService(db)

    # Workflow-Zugriff pruefen
    workflow = await service.get_workflow(workflow_id, current_user.id, include_steps=False)
    if not workflow or workflow.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workflow nicht gefunden oder keine Berechtigung",
        )

    success = await service.delete_step(step_id)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Step nicht gefunden",
        )


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
    service = WorkflowService(db)

    # Workflow-Zugriff pruefen
    workflow = await service.get_workflow(workflow_id, current_user.id, include_steps=False)
    if not workflow or workflow.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workflow nicht gefunden oder keine Berechtigung",
        )

    await service.reorder_steps(
        workflow_id=workflow_id,
        step_orders=[{"step_id": str(s.step_id), "step_order": s.step_order} for s in step_orders],
    )

    steps = await service.get_steps(workflow_id)

    return [StepResponse.model_validate(s) for s in steps]


@router.post(
    "/{workflow_id}/steps/batch",
    response_model=List[StepResponse],
    summary="Steps batch-aktualisieren",
)
async def batch_update_steps(
    workflow_id: UUID,
    steps_data: List[Dict[str, Any]],
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> List[StepResponse]:
    """Aktualisiert mehrere Steps (ReactFlow Bulk-Update)."""
    service = WorkflowService(db)

    # Workflow-Zugriff pruefen
    workflow = await service.get_workflow(workflow_id, current_user.id, include_steps=False)
    if not workflow or workflow.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workflow nicht gefunden oder keine Berechtigung",
        )

    updated_steps = await service.batch_update_steps(
        workflow_id=workflow_id,
        steps_data=steps_data,
    )

    return [StepResponse.model_validate(s) for s in updated_steps]


# =============================================================================
# Execution Endpoints (8)
# =============================================================================


@router.post(
    "/{workflow_id}/execute",
    response_model=ExecutionResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Workflow ausfuehren",
)
async def execute_workflow(
    workflow_id: UUID,
    data: ExecutionStart,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ExecutionResponse:
    """Startet eine Workflow-Ausfuehrung."""
    step_executor = WorkflowStepExecutor(db)
    execution_service = WorkflowExecutionService(db, step_executor)

    try:
        execution = await execution_service.start_execution(
            workflow_id=workflow_id,
            user_id=current_user.id,
            document_id=data.document_id,
            initial_variables=data.variables,
        )

        return ExecutionResponse.model_validate(execution)

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.get(
    "/{workflow_id}/executions",
    response_model=ExecutionListResponse,
    summary="Ausfuehrungen abrufen",
)
async def get_workflow_executions(
    workflow_id: UUID,
    status_filter: Optional[str] = Query(None, alias="status", description="Filter nach Status"),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ExecutionListResponse:
    """Ruft Ausfuehrungen eines Workflows ab."""
    execution_service = WorkflowExecutionService(db)

    executions, total = await execution_service.list_executions(
        workflow_id=workflow_id,
        user_id=current_user.id,
        status=status_filter,
        offset=offset,
        limit=limit,
    )

    return ExecutionListResponse(
        items=[ExecutionResponse.model_validate(e) for e in executions],
        total=total,
        offset=offset,
        limit=limit,
    )


@router.get(
    "/executions/{execution_id}",
    response_model=ExecutionResponse,
    summary="Ausfuehrung abrufen",
)
async def get_execution(
    execution_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ExecutionResponse:
    """Ruft eine Ausfuehrung nach ID ab."""
    execution_service = WorkflowExecutionService(db)

    execution = await execution_service.get_execution(
        execution_id=execution_id,
        user_id=current_user.id,
    )

    if not execution:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ausfuehrung nicht gefunden",
        )

    return ExecutionResponse.model_validate(execution)


@router.get(
    "/executions/{execution_id}/steps",
    response_model=List[StepExecutionResponse],
    summary="Step-Ausfuehrungen abrufen",
)
async def get_step_executions(
    execution_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> List[StepExecutionResponse]:
    """Ruft Step-Ausfuehrungen ab."""
    execution_service = WorkflowExecutionService(db)

    # Execution-Zugriff pruefen
    execution = await execution_service.get_execution(execution_id, current_user.id)
    if not execution:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ausfuehrung nicht gefunden",
        )

    step_executions = await execution_service.get_step_executions(execution_id)

    return [StepExecutionResponse.model_validate(se) for se in step_executions]


@router.post(
    "/executions/{execution_id}/pause",
    response_model=Dict[str, bool],
    summary="Ausfuehrung pausieren",
)
async def pause_execution(
    execution_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, bool]:
    """Pausiert eine laufende Ausfuehrung."""
    execution_service = WorkflowExecutionService(db)

    success = await execution_service.pause_execution(
        execution_id=execution_id,
        user_id=current_user.id,
    )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ausfuehrung kann nicht pausiert werden",
        )

    return {"paused": True}


@router.post(
    "/executions/{execution_id}/resume",
    response_model=Dict[str, bool],
    summary="Ausfuehrung fortsetzen",
)
async def resume_execution(
    execution_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, bool]:
    """Setzt eine pausierte Ausfuehrung fort."""
    step_executor = WorkflowStepExecutor(db)
    execution_service = WorkflowExecutionService(db, step_executor)

    success = await execution_service.resume_execution(
        execution_id=execution_id,
        user_id=current_user.id,
    )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ausfuehrung kann nicht fortgesetzt werden",
        )

    return {"resumed": True}


@router.post(
    "/executions/{execution_id}/cancel",
    response_model=Dict[str, bool],
    summary="Ausfuehrung abbrechen",
)
async def cancel_execution(
    execution_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, bool]:
    """Bricht eine Ausfuehrung ab."""
    execution_service = WorkflowExecutionService(db)

    success = await execution_service.cancel_execution(
        execution_id=execution_id,
        user_id=current_user.id,
    )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ausfuehrung kann nicht abgebrochen werden",
        )

    return {"cancelled": True}


@router.post(
    "/executions/{execution_id}/retry",
    response_model=ExecutionResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Ausfuehrung wiederholen",
)
async def retry_execution(
    execution_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ExecutionResponse:
    """Wiederholt eine fehlgeschlagene Ausfuehrung."""
    step_executor = WorkflowStepExecutor(db)
    execution_service = WorkflowExecutionService(db, step_executor)

    new_execution = await execution_service.retry_execution(
        execution_id=execution_id,
        user_id=current_user.id,
    )

    if not new_execution:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ausfuehrung kann nicht wiederholt werden",
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
    """Listet verfuegbare Workflow-Templates."""
    service = WorkflowService(db)

    templates = await service.list_templates(category=category)

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
    service = WorkflowService(db)

    template = await service.get_workflow(template_id, include_steps=True)

    if not template or not template.is_template:
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
    service = WorkflowService(db)

    workflow = await service.instantiate_template(
        template_id=template_id,
        user_id=current_user.id,
        name=data.name,
        company_id=data.company_id,
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
    response_model=Dict[str, Any],
    summary="Webhook Trigger",
)
async def webhook_trigger(
    webhook_path: str,
    payload: WebhookPayload,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Empfaengt Webhook-Trigger von externen Systemen."""
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
            detail="Kein Workflow fuer diesen Webhook gefunden",
        )

    return {
        "success": True,
        "execution_id": str(execution_id),
    }


@router.get(
    "/{workflow_id}/webhook-config",
    response_model=Dict[str, Any],
    summary="Webhook-Konfiguration abrufen",
)
async def get_webhook_config(
    workflow_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """Ruft die Webhook-Konfiguration eines Workflows ab."""
    trigger_service = WorkflowTriggerService(db)

    config = await trigger_service.get_webhook_config(
        workflow_id=workflow_id,
        user_id=current_user.id,
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
    trigger_service = WorkflowTriggerService(db)

    new_secret = await trigger_service.regenerate_webhook_secret(
        workflow_id=workflow_id,
        user_id=current_user.id,
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
    """Ruft Statistiken fuer einen Workflow ab."""
    service = WorkflowService(db)

    stats = await service.get_workflow_stats(workflow_id)

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
    from sqlalchemy import func, and_
    from app.db.models import Workflow, WorkflowExecution

    # Workflows zaehlen
    workflow_query = select(
        func.count(Workflow.id).label("total"),
        func.sum(func.cast(Workflow.is_active == True, Integer)).label("active"),  # noqa: E712
    ).where(Workflow.user_id == current_user.id)

    from sqlalchemy import Integer

    result = await db.execute(workflow_query)
    workflow_row = result.one()

    # Executions zaehlen
    exec_query = select(
        func.count(WorkflowExecution.id).label("total"),
    ).where(WorkflowExecution.user_id == current_user.id)

    exec_result = await db.execute(exec_query)
    exec_row = exec_result.one()

    # Executions heute
    from datetime import date

    today_query = select(
        func.count(WorkflowExecution.id).label("today"),
    ).where(
        and_(
            WorkflowExecution.user_id == current_user.id,
            func.date(WorkflowExecution.started_at) == date.today(),
        )
    )

    today_result = await db.execute(today_query)
    today_row = today_result.one()

    # Success Rate
    success_query = select(
        func.count(WorkflowExecution.id).label("completed"),
    ).where(
        and_(
            WorkflowExecution.user_id == current_user.id,
            WorkflowExecution.status == "completed",
        )
    )

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
    response_model=List[Dict[str, Any]],
    summary="Ausfuehrungs-Historie",
)
async def get_execution_history(
    days: int = Query(30, ge=1, le=365, description="Anzahl Tage"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> List[Dict[str, Any]]:
    """Ruft Ausfuehrungs-Historie ab."""
    from sqlalchemy import func, and_
    from datetime import datetime, timedelta, timezone
    from app.db.models import WorkflowExecution

    start_date = datetime.now(timezone.utc) - timedelta(days=days)

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
        .where(
            and_(
                WorkflowExecution.user_id == current_user.id,
                WorkflowExecution.started_at >= start_date,
            )
        )
        .group_by(func.date(WorkflowExecution.started_at))
        .order_by(func.date(WorkflowExecution.started_at))
    )

    from sqlalchemy import Integer

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
    summary="Verfuegbare Operatoren",
)
async def get_available_operators(
    current_user: User = Depends(get_current_user),
) -> List[Dict[str, str]]:
    """Gibt verfuegbare Bedingungs-Operatoren zurueck."""
    evaluator = ConditionEvaluator()
    return evaluator.get_available_operators()


@router.get(
    "/fields",
    response_model=Dict[str, str],
    summary="Verfuegbare Felder",
)
async def get_available_fields(
    current_user: User = Depends(get_current_user),
) -> Dict[str, str]:
    """Gibt verfuegbare Bedingungs-Felder zurueck."""
    evaluator = ConditionEvaluator()
    return evaluator.get_available_fields()
