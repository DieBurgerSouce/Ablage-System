"""BPMN Process Engine API Endpoints.

Endpunkte für:
- Process Definitions: Deploy, List, Export
- Process Instances: Start, List, Terminate
- Process Tasks: Claim, Complete, Delegate
- Process History: Audit Trail

Alle Endpunkte erfordern Authentifizierung und Multi-Tenant Isolation.
"""

from datetime import datetime
from typing import Optional, List, Dict

from app.core.types import JSONDict, JSONValue
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status, Body
from pydantic import BaseModel, Field, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db, get_current_active_user, get_user_company_id_dep
from app.core.safe_errors import safe_error_detail, safe_error_log
from app.db.models import (
    User,
    ProcessStatus,
    BpmnTaskStatus as TaskStatus,
    TaskType,
)
from app.services.bpmn import (
    get_process_definition_service,
    get_process_execution_service,
    get_task_service,
    get_timer_service,
)

router = APIRouter(prefix="/bpmn", tags=["BPMN Workflow Engine"])


# =============================================================================
# Pydantic Schemas
# =============================================================================

class ProcessDefinitionCreate(BaseModel):
    """Schema für Prozess-Definition Erstellung."""
    key: str = Field(..., min_length=1, max_length=255,
                     description="Eindeutiger Prozess-Key")
    name: str = Field(..., min_length=1, max_length=255,
                      description="Anzeigename")
    description: Optional[str] = None
    category: Optional[str] = Field(None, max_length=100)
    tags: Optional[List[str]] = None
    bpmn_xml: Optional[str] = Field(None, description="BPMN 2.0 XML")
    process_json: Optional[JSONDict] = Field(
        None, description="Frontend JSON (React Flow Format)"
    )


class ProcessDefinitionResponse(BaseModel):
    """Response für Prozess-Definition."""
    id: UUID
    key: str
    name: str
    description: Optional[str]
    version: int
    is_active: bool
    category: Optional[str]
    tags: List[str]
    deployed_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ProcessInstanceStart(BaseModel):
    """Schema zum Starten einer Prozess-Instanz."""
    definition_key: str = Field(..., description="Key der Prozess-Definition")
    variables: Optional[JSONDict] = Field(
        default_factory=dict, description="Initiale Prozess-Variablen"
    )
    business_key: Optional[str] = Field(
        None, max_length=255, description="Externer Schluessel (z.B. Rechnungsnummer)"
    )
    document_id: Optional[UUID] = Field(
        None, description="Verknüpftes Dokument"
    )


class ProcessInstanceResponse(BaseModel):
    """Response für Prozess-Instanz."""
    id: UUID
    definition_id: UUID
    definition_key: Optional[str] = None
    definition_name: Optional[str] = None
    business_key: Optional[str]
    status: str
    variables: JSONDict
    current_elements: List[str]
    document_id: Optional[UUID]
    started_at: Optional[datetime]
    ended_at: Optional[datetime]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ProcessTaskResponse(BaseModel):
    """Response für Process Task."""
    id: UUID
    instance_id: UUID
    element_id: str
    element_name: Optional[str]
    task_type: str
    status: str
    assignee_id: Optional[UUID]
    assignee_group: Optional[str]
    priority: int
    due_date: Optional[datetime]
    form_key: Optional[str]
    task_variables: JSONDict
    created_at: datetime
    claimed_at: Optional[datetime]
    completed_at: Optional[datetime]

    # Optionale Instanz-Info
    business_key: Optional[str] = None
    process_name: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class TaskCompleteRequest(BaseModel):
    """Request zum Abschließen eines Tasks."""
    variables: Optional[JSONDict] = Field(
        default_factory=dict, description="Output-Variablen"
    )


class TaskDelegateRequest(BaseModel):
    """Request zum Delegieren eines Tasks."""
    to_user_id: UUID = Field(..., description="Empfänger-User ID")
    comment: Optional[str] = None


class ProcessHistoryResponse(BaseModel):
    """Response für History-Eintrag."""
    id: UUID
    event_type: str
    element_id: Optional[str]
    element_type: Optional[str]
    message: Optional[str]
    actor_id: Optional[UUID]
    actor_type: str
    old_value: Optional[JSONDict]
    new_value: Optional[JSONDict]
    timestamp: datetime

    model_config = ConfigDict(from_attributes=True)


class PaginatedResponse(BaseModel):
    """Generische paginierte Response."""
    items: List[JSONValue]
    total: int
    page: int
    per_page: int
    pages: int


# =============================================================================
# Process Definition Endpoints
# =============================================================================

@router.post(
    "/definitions",
    response_model=ProcessDefinitionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Prozess-Definition deployen"
)
async def deploy_process_definition(
    request: ProcessDefinitionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_user_company_id_dep),
):
    """Deployt eine neue Prozess-Definition.

    Unterstützt sowohl BPMN 2.0 XML als auch Frontend JSON (React Flow).
    Bei existierendem Key wird automatisch eine neue Version erstellt.
    """
    service = get_process_definition_service(db)

    try:
        if request.bpmn_xml:
            definition = await service.deploy(
                key=request.key,
                name=request.name,
                company_id=company_id,
                bpmn_xml=request.bpmn_xml,
                description=request.description,
                category=request.category,
                tags=request.tags,
                deployed_by_id=current_user.id,
            )
        elif request.process_json:
            definition = await service.deploy_from_json(
                key=request.key,
                name=request.name,
                company_id=company_id,
                process_json=request.process_json,
                description=request.description,
                category=request.category,
                tags=request.tags,
                deployed_by_id=current_user.id,
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Entweder bpmn_xml oder process_json erforderlich"
            )

        return definition

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=safe_error_detail(e, "Prozess-Definition")
        )


@router.get(
    "/definitions",
    response_model=PaginatedResponse,
    summary="Prozess-Definitionen auflisten"
)
async def list_process_definitions(
    category: Optional[str] = Query(None, description="Filter nach Kategorie"),
    only_active: bool = Query(False, description="Nur aktive Versionen"),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_user_company_id_dep),
):
    """Listet alle Prozess-Definitionen auf."""
    service = get_process_definition_service(db)

    definitions, total = await service.list_definitions(
        company_id=company_id,
        category=category,
        only_active=only_active,
        page=page,
        per_page=per_page,
    )

    return PaginatedResponse(
        items=[ProcessDefinitionResponse.model_validate(d) for d in definitions],
        total=total,
        page=page,
        per_page=per_page,
        pages=(total + per_page - 1) // per_page,
    )


@router.get(
    "/definitions/{definition_id}",
    response_model=ProcessDefinitionResponse,
    summary="Prozess-Definition abrufen"
)
async def get_process_definition(
    definition_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_user_company_id_dep),
):
    """Gibt eine einzelne Prozess-Definition zurück."""
    service = get_process_definition_service(db)

    definition = await service.get_by_id(definition_id, company_id)
    if not definition:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Prozess-Definition nicht gefunden"
        )

    return definition


@router.get(
    "/definitions/{definition_id}/export",
    response_model=dict,
    summary="BPMN XML exportieren"
)
async def export_process_definition(
    definition_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_user_company_id_dep),
):
    """Exportiert Prozess-Definition als BPMN 2.0 XML."""
    service = get_process_definition_service(db)

    try:
        bpmn_xml = await service.export_bpmn(definition_id, company_id)
        return {"bpmn_xml": bpmn_xml}
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=safe_error_detail(e, "BPMN-Export")
        )


@router.post(
    "/definitions/{definition_id}/activate",
    response_model=ProcessDefinitionResponse,
    summary="Prozess-Definition aktivieren"
)
async def activate_process_definition(
    definition_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_user_company_id_dep),
):
    """Aktiviert eine Prozess-Definition.

    Deaktiviert automatisch andere Versionen desselben Keys.
    """
    service = get_process_definition_service(db)

    try:
        definition = await service.activate(
            definition_id=definition_id,
            company_id=company_id,
            user_id=current_user.id
        )
        return definition
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=safe_error_detail(e, "Prozess-Aktivierung")
        )


@router.post(
    "/definitions/{definition_id}/deactivate",
    response_model=ProcessDefinitionResponse,
    summary="Prozess-Definition deaktivieren"
)
async def deactivate_process_definition(
    definition_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_user_company_id_dep),
):
    """Deaktiviert eine Prozess-Definition."""
    service = get_process_definition_service(db)

    try:
        definition = await service.deactivate(
            definition_id=definition_id,
            company_id=company_id
        )
        return definition
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=safe_error_detail(e, "Prozess-Deaktivierung")
        )


@router.get(
    "/definitions/statistics",
    summary="Prozess-Statistiken"
)
async def get_process_statistics(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_user_company_id_dep),
):
    """Gibt Statistiken zu Prozess-Definitionen zurück."""
    service = get_process_definition_service(db)
    return await service.get_statistics(company_id)


# =============================================================================
# Process Instance Endpoints
# =============================================================================

@router.post(
    "/instances",
    response_model=ProcessInstanceResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Prozess starten"
)
async def start_process_instance(
    request: ProcessInstanceStart,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_user_company_id_dep),
):
    """Startet eine neue Prozess-Instanz.

    Erfordert eine aktive Prozess-Definition mit dem angegebenen Key.
    """
    service = get_process_execution_service(db)

    try:
        instance = await service.start(
            definition_key=request.definition_key,
            company_id=company_id,
            variables=request.variables,
            business_key=request.business_key,
            started_by_id=current_user.id,
            document_id=request.document_id,
        )
        return instance
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=safe_error_detail(e, "Prozess-Start")
        )


@router.get(
    "/instances",
    response_model=PaginatedResponse,
    summary="Prozess-Instanzen auflisten"
)
async def list_process_instances(
    definition_key: Optional[str] = Query(None, description="Filter nach Prozess-Key"),
    status: Optional[ProcessStatus] = Query(None, description="Filter nach Status"),
    document_id: Optional[UUID] = Query(None, description="Filter nach Dokument"),
    my_processes: bool = Query(False, description="Nur eigene Prozesse"),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_user_company_id_dep),
):
    """Listet Prozess-Instanzen auf."""
    service = get_process_execution_service(db)

    instances, total = await service.list_instances(
        company_id=company_id,
        definition_key=definition_key,
        status=status,
        started_by_id=current_user.id if my_processes else None,
        document_id=document_id,
        page=page,
        per_page=per_page,
    )

    return PaginatedResponse(
        items=[ProcessInstanceResponse.model_validate(i) for i in instances],
        total=total,
        page=page,
        per_page=per_page,
        pages=(total + per_page - 1) // per_page,
    )


@router.get(
    "/instances/{instance_id}",
    response_model=ProcessInstanceResponse,
    summary="Prozess-Instanz abrufen"
)
async def get_process_instance(
    instance_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_user_company_id_dep),
):
    """Gibt eine einzelne Prozess-Instanz zurück."""
    service = get_process_execution_service(db)

    instance = await service.get_instance(instance_id, company_id)
    if not instance:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Prozess-Instanz nicht gefunden"
        )

    return instance


@router.post(
    "/instances/{instance_id}/terminate",
    response_model=ProcessInstanceResponse,
    summary="Prozess terminieren"
)
async def terminate_process_instance(
    instance_id: UUID,
    reason: Optional[str] = Body(None, embed=True),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_user_company_id_dep),
):
    """Terminiert eine laufende Prozess-Instanz.

    Bricht alle offenen Tasks ab und markiert den Prozess als terminiert.
    """
    service = get_process_execution_service(db)

    try:
        instance = await service.terminate(
            instance_id=instance_id,
            company_id=company_id,
            reason=reason,
            user_id=current_user.id,
        )
        return instance
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=safe_error_detail(e, "Prozess-Terminierung")
        )


@router.post(
    "/instances/{instance_id}/signal",
    response_model=ProcessInstanceResponse,
    summary="Signal senden"
)
async def send_signal_to_instance(
    instance_id: UUID,
    signal_name: str = Body(..., embed=True),
    variables: Optional[JSONDict] = Body(None, embed=True),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_user_company_id_dep),
):
    """Sendet ein Signal an eine Prozess-Instanz."""
    service = get_process_execution_service(db)

    try:
        instance = await service.signal(
            instance_id=instance_id,
            company_id=company_id,
            signal_name=signal_name,
            variables=variables,
            user_id=current_user.id,
        )
        return instance
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=safe_error_detail(e, "Signal-Verarbeitung")
        )


@router.get(
    "/instances/{instance_id}/history",
    response_model=List[ProcessHistoryResponse],
    summary="Prozess-Historie"
)
async def get_process_history(
    instance_id: UUID,
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_user_company_id_dep),
):
    """Gibt die Historie einer Prozess-Instanz zurück."""
    service = get_process_execution_service(db)

    history = await service.get_history(
        instance_id=instance_id,
        company_id=company_id,
        limit=limit
    )

    return history


# =============================================================================
# Task Endpoints
# =============================================================================

@router.get(
    "/tasks",
    response_model=PaginatedResponse,
    summary="Meine Tasks"
)
async def get_my_tasks(
    status: Optional[TaskStatus] = Query(None, description="Filter nach Status"),
    include_group_tasks: bool = Query(True, description="Gruppen-Tasks einbeziehen"),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_user_company_id_dep),
):
    """Gibt Tasks für den aktuellen Benutzer zurück.

    Beinhaltet direkt zugewiesene Tasks sowie optionale Gruppen-Tasks.
    """
    service = get_task_service(db)

    # User-Gruppen aus User-Rollen ableiten
    user_groups: list[str] = []
    if current_user.roles:
        user_groups = [role.name for role in current_user.roles]

    tasks, total = await service.get_user_tasks(
        user_id=current_user.id,
        company_id=company_id,
        status=status,
        include_group_tasks=include_group_tasks,
        user_groups=user_groups,
        page=page,
        per_page=per_page,
    )

    # Tasks mit Instanz-Info anreichern
    task_responses = []
    for task in tasks:
        task_dict = ProcessTaskResponse.model_validate(task).model_dump()
        if task.instance:
            task_dict["business_key"] = task.instance.business_key
        task_responses.append(task_dict)

    return PaginatedResponse(
        items=task_responses,
        total=total,
        page=page,
        per_page=per_page,
        pages=(total + per_page - 1) // per_page,
    )


@router.get(
    "/tasks/group/{group_name}",
    response_model=PaginatedResponse,
    summary="Gruppen-Tasks"
)
async def get_group_tasks(
    group_name: str,
    status: Optional[TaskStatus] = None,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_user_company_id_dep),
):
    """Gibt unzugewiesene Tasks für eine Gruppe zurück."""
    service = get_task_service(db)

    tasks, total = await service.get_group_tasks(
        group_name=group_name,
        company_id=company_id,
        status=status,
        page=page,
        per_page=per_page,
    )

    return PaginatedResponse(
        items=[ProcessTaskResponse.model_validate(t) for t in tasks],
        total=total,
        page=page,
        per_page=per_page,
        pages=(total + per_page - 1) // per_page,
    )


@router.get(
    "/tasks/{task_id}",
    response_model=ProcessTaskResponse,
    summary="Task abrufen"
)
async def get_task(
    task_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_user_company_id_dep),
):
    """Gibt einen einzelnen Task zurück."""
    service = get_task_service(db)

    task = await service.get_task(task_id, company_id)
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task nicht gefunden"
        )

    return task


@router.post(
    "/tasks/{task_id}/claim",
    response_model=ProcessTaskResponse,
    summary="Task übernehmen"
)
async def claim_task(
    task_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_user_company_id_dep),
):
    """Übernimmt einen Task."""
    service = get_task_service(db)

    try:
        task = await service.claim(
            task_id=task_id,
            user_id=current_user.id,
            company_id=company_id
        )
        return task
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=safe_error_detail(e, "Aufgabe-Übernehmen")
        )


@router.post(
    "/tasks/{task_id}/unclaim",
    response_model=ProcessTaskResponse,
    summary="Task freigeben"
)
async def unclaim_task(
    task_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_user_company_id_dep),
):
    """Gibt einen Task wieder frei."""
    service = get_task_service(db)

    try:
        task = await service.unclaim(
            task_id=task_id,
            user_id=current_user.id,
            company_id=company_id
        )
        return task
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=safe_error_detail(e, "Aufgabe-Freigeben")
        )


@router.post(
    "/tasks/{task_id}/complete",
    response_model=ProcessTaskResponse,
    summary="Task abschließen"
)
async def complete_task(
    task_id: UUID,
    request: TaskCompleteRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_user_company_id_dep),
):
    """Schließt einen Task ab.

    Output-Variablen werden als Prozess-Variablen übernommen.
    Der Prozess wird automatisch fortgesetzt.
    """
    service = get_task_service(db)

    try:
        task = await service.complete(
            task_id=task_id,
            user_id=current_user.id,
            company_id=company_id,
            variables=request.variables
        )
        return task
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=safe_error_detail(e, "Aufgabe-Abschließen")
        )


@router.post(
    "/tasks/{task_id}/delegate",
    response_model=ProcessTaskResponse,
    summary="Task delegieren"
)
async def delegate_task(
    task_id: UUID,
    request: TaskDelegateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_user_company_id_dep),
):
    """Delegiert einen Task an einen anderen Benutzer."""
    service = get_task_service(db)

    try:
        task = await service.delegate(
            task_id=task_id,
            from_user_id=current_user.id,
            to_user_id=request.to_user_id,
            company_id=company_id,
            comment=request.comment
        )
        return task
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=safe_error_detail(e, "Aufgabe-Delegieren")
        )


@router.get(
    "/tasks/overdue",
    response_model=List[ProcessTaskResponse],
    summary="Überfällige Tasks"
)
async def get_overdue_tasks(
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_user_company_id_dep),
):
    """Gibt alle überfälligen Tasks zurück."""
    service = get_task_service(db)

    tasks = await service.get_overdue_tasks(
        company_id=company_id,
        limit=limit
    )

    return tasks


@router.get(
    "/tasks/statistics",
    summary="Task-Statistiken"
)
async def get_task_statistics(
    user_id: Optional[UUID] = Query(None, description="Filter nach User"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_user_company_id_dep),
):
    """Gibt Task-Statistiken zurück."""
    service = get_task_service(db)

    return await service.get_task_statistics(
        company_id=company_id,
        user_id=user_id
    )


# =============================================================================
# Timer Endpoints (Admin)
# =============================================================================

@router.get(
    "/timers/statistics",
    summary="Timer-Statistiken"
)
async def get_timer_statistics(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_user_company_id_dep),
):
    """Gibt Timer-Statistiken zurück."""
    service = get_timer_service(db)
    return await service.get_timer_statistics(company_id)


# =============================================================================
# Workflow Templates
# =============================================================================

class WorkflowTemplateResponse(BaseModel):
    """Response für Workflow-Template."""
    key: str
    name: str
    description: str
    category: str
    tags: List[str]
    nodes_count: int
    edges_count: int


class WorkflowTemplateDeployRequest(BaseModel):
    """Request zum Deployen eines Workflow-Templates."""
    template_key: str = Field(..., description="Key des Templates")
    custom_name: Optional[str] = Field(None, description="Optionaler benutzerdefinierter Name")


@router.get(
    "/templates",
    response_model=List[WorkflowTemplateResponse],
    summary="Workflow-Templates auflisten"
)
async def list_templates(
    category: Optional[str] = Query(None, description="Filter nach Kategorie"),
    current_user: User = Depends(get_current_active_user)
):
    """Listet alle verfügbaren Workflow-Templates auf."""
    from app.services.bpmn.workflow_templates import list_workflow_templates

    templates = list_workflow_templates()

    # Optional nach Kategorie filtern
    if category:
        templates = [t for t in templates if t.get("category") == category]

    result = []
    for template in templates:
        process_json = template.get("process_json", {})
        result.append(WorkflowTemplateResponse(
            key=template["key"],
            name=template["name"],
            description=template.get("description", ""),
            category=template.get("category", ""),
            tags=template.get("tags", []),
            nodes_count=len(process_json.get("nodes", [])),
            edges_count=len(process_json.get("edges", [])),
        ))

    return result


@router.get(
    "/templates/{template_key}",
    summary="Workflow-Template Details"
)
async def get_template(
    template_key: str,
    current_user: User = Depends(get_current_active_user)
):
    """Gibt die Details eines Workflow-Templates zurück (inkl. vollständigem JSON)."""
    from app.services.bpmn.workflow_templates import get_workflow_template

    template = get_workflow_template(template_key)
    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Template '{template_key}' nicht gefunden"
        )

    return template


@router.post(
    "/templates/deploy",
    response_model=ProcessDefinitionResponse,
    summary="Workflow-Template deployen"
)
async def deploy_template(
    request: WorkflowTemplateDeployRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_user_company_id_dep),
):
    """Deployed ein Workflow-Template als neue Prozess-Definition."""
    from app.services.bpmn.workflow_templates import get_workflow_template

    template = get_workflow_template(request.template_key)
    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Template '{request.template_key}' nicht gefunden"
        )

    service = get_process_definition_service(db)

    try:
        definition = await service.deploy_from_json(
            key=template["key"],
            name=request.custom_name or template["name"],
            description=template.get("description"),
            category=template.get("category"),
            tags=template.get("tags", []),
            process_json=template["process_json"],
            company_id=company_id,
            deployed_by_id=current_user.id
        )
        return definition
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=safe_error_detail(e, "Template-Deployment")
        )
