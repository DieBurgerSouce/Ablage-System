# -*- coding: utf-8 -*-
"""
Document Tasks API Endpoints.

Enterprise-level Aufgabenverwaltung fuer Dokumente:
- Aufgaben erstellen/bearbeiten/loeschen
- Zuweisung an Benutzer
- Status-Uebergaenge (Start, Abschluss, Abbruch, Blockierung)
- Deadline-Ueberwachung
- Eskalations-Support

Feinpoliert und durchdacht - Aufgabenmanagement auf Enterprise-Niveau.

Security:
- Firmenzugehoerigkeit wird bei jeder Operation validiert
- Dokumentzugriff wird vor Erstellung geprueft
- Benutzer-Existenz wird vor Zuweisung validiert
"""

import structlog
from typing import Optional
from uuid import UUID
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, exists, func

from app.db.models import (
    User,
    Document,
    DocumentTask,
    TaskStatus,
    TaskPriority,
    DocumentAccess,
    AccessLevel,
)
from app.api.dependencies import get_current_user, get_db
from app.db.schemas import (
    TaskCreate,
    TaskUpdate,
    TaskResponse,
    TasksListResponse,
    TaskStatistics,
    TaskCompleteRequest,
    TaskAssignRequest,
    TaskStatusEnum,
    TaskPriorityEnum,
)
from app.services.collaboration.document_task_service import (
    DocumentTaskService,
    get_document_task_service,
)
from app.core.datetime_utils import utc_now
from app.core.safe_errors import safe_error_detail

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/document-tasks", tags=["document-tasks"])


# =============================================================================
# Helper Functions
# =============================================================================


async def _verify_document_access(
    db: AsyncSession,
    document_id: UUID,
    user_id: UUID,
) -> Document:
    """Prueft ob User Zugriff auf das Dokument hat.

    Zugriff erlaubt wenn:
    - User ist Owner des Dokuments
    - User hat expliziten Zugriff via document_access Tabelle

    Args:
        db: Datenbank-Session
        document_id: ID des Dokuments
        user_id: ID des anfragenden Users

    Returns:
        Document wenn Zugriff erlaubt

    Raises:
        HTTPException 404: Dokument nicht gefunden
        HTTPException 403: Zugriff verweigert
    """
    # Dokument abrufen
    doc_result = await db.execute(
        select(Document).where(Document.id == document_id)
    )
    document = doc_result.scalar_one_or_none()

    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dokument nicht gefunden"
        )

    # Owner hat immer Zugriff
    if document.owner_id == user_id:
        return document

    # Pruefe shared access
    access_result = await db.execute(
        select(exists().where(
            and_(
                DocumentAccess.document_id == document_id,
                DocumentAccess.user_id == user_id,
                or_(
                    DocumentAccess.expires_at.is_(None),
                    DocumentAccess.expires_at > func.now()
                )
            )
        ))
    )
    has_access = access_result.scalar()

    if not has_access:
        logger.warning(
            "task_document_access_denied",
            document_id=str(document_id),
            user_id=str(user_id),
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Keine Berechtigung fuer dieses Dokument"
        )

    return document


def _build_task_response(task: DocumentTask) -> TaskResponse:
    """Erstellt TaskResponse aus DB-Modell.

    Args:
        task: DocumentTask Instanz mit geladenen Beziehungen

    Returns:
        TaskResponse Pydantic Schema
    """
    return TaskResponse(
        id=str(task.id),
        documentId=str(task.document_id),
        documentName=(
            task.document.original_filename or task.document.filename
            if task.document else None
        ),
        companyId=str(task.company_id),
        title=task.title,
        description=task.description,
        taskType=task.task_type,
        createdById=str(task.created_by_id) if task.created_by_id else None,
        createdByName=(
            task.created_by.full_name or task.created_by.username
            if task.created_by else None
        ),
        assignedToId=str(task.assigned_to_id) if task.assigned_to_id else None,
        assignedToName=(
            task.assigned_to.full_name or task.assigned_to.username
            if task.assigned_to else None
        ),
        status=task.status,
        priority=task.priority,
        dueDate=task.due_date.isoformat() if task.due_date else None,
        reminderSent=task.reminder_sent,
        escalated=task.escalated,
        escalatedAt=task.escalated_at.isoformat() if task.escalated_at else None,
        completedAt=task.completed_at.isoformat() if task.completed_at else None,
        completedById=str(task.completed_by_id) if task.completed_by_id else None,
        completionNotes=task.completion_notes,
        metadata=task.task_metadata or {},
        createdAt=task.created_at.isoformat() if task.created_at else "",
        updatedAt=task.updated_at.isoformat() if task.updated_at else "",
    )


# =============================================================================
# CRUD Endpoints
# =============================================================================


@router.post(
    "/",
    response_model=TaskResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Aufgabe erstellen",
    description="Erstellt eine neue Aufgabe fuer ein Dokument."
)
async def create_task(
    task_data: TaskCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TaskResponse:
    """Erstellt eine neue Aufgabe fuer ein Dokument."""
    # Pruefe Dokumentzugriff
    document = await _verify_document_access(db, task_data.documentId, current_user.id)

    # Service initialisieren
    task_service = get_document_task_service(db)

    try:
        task = await task_service.create_task(
            document_id=task_data.documentId,
            company_id=document.company_id,
            created_by_id=current_user.id,
            title=task_data.title,
            description=task_data.description,
            task_type=task_data.taskType.value,
            assigned_to_id=task_data.assignedToId,
            priority=task_data.priority.value,
            due_date=task_data.dueDate,
            metadata=task_data.metadata,
            notify_assignee=True,
        )

        # Lade Beziehungen fuer Response
        # SECURITY: company_id muss IMMER uebergeben werden fuer Multi-Tenant Isolation
        task = await task_service.get_task(task.id, company_id=document.company_id)

        logger.info(
            "document_task_created_via_api",
            task_id=str(task.id),
            document_id=str(task_data.documentId),
            created_by=str(current_user.id),
        )

        return _build_task_response(task)

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=safe_error_detail(e, "Dokument-Aufgabe")
        )


@router.get(
    "/",
    response_model=TasksListResponse,
    summary="Aufgaben auflisten",
    description="Listet alle Aufgaben mit Filtern auf."
)
async def list_tasks(
    document_id: Optional[UUID] = Query(None, description="Filter nach Dokument"),
    assigned_to_me: bool = Query(False, description="Nur mir zugewiesene Aufgaben"),
    created_by_me: bool = Query(False, description="Nur von mir erstellte Aufgaben"),
    status_filter: Optional[TaskStatusEnum] = Query(None, alias="status", description="Filter nach Status"),
    priority_filter: Optional[TaskPriorityEnum] = Query(None, alias="priority", description="Filter nach Prioritaet"),
    overdue_only: bool = Query(False, description="Nur ueberfaellige Aufgaben"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TasksListResponse:
    """Listet Aufgaben mit optionalen Filtern auf."""
    task_service = get_document_task_service(db)

    # Filter aufbauen
    assigned_to_id = current_user.id if assigned_to_me else None
    created_by_id = current_user.id if created_by_me else None
    status_value = status_filter.value if status_filter else None
    priority_value = priority_filter.value if priority_filter else None

    tasks, total = await task_service.list_tasks(
        company_id=current_user.company_id,
        document_id=document_id,
        assigned_to_id=assigned_to_id,
        created_by_id=created_by_id,
        status=status_value,
        priority=priority_value,
        overdue_only=overdue_only,
        limit=limit,
        offset=offset,
    )

    task_responses = [_build_task_response(task) for task in tasks]

    return TasksListResponse(
        tasks=task_responses,
        total=total,
        hasMore=(offset + len(tasks)) < total,
    )


@router.get(
    "/my",
    response_model=TasksListResponse,
    summary="Meine Aufgaben",
    description="Holt alle mir zugewiesenen Aufgaben."
)
async def get_my_tasks(
    status_filter: Optional[TaskStatusEnum] = Query(None, alias="status"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TasksListResponse:
    """Holt alle dem aktuellen Benutzer zugewiesenen Aufgaben."""
    task_service = get_document_task_service(db)

    status_value = status_filter.value if status_filter else None

    tasks, total = await task_service.get_my_tasks(
        user_id=current_user.id,
        company_id=current_user.company_id,
        status=status_value,
        limit=limit,
        offset=offset,
    )

    task_responses = [_build_task_response(task) for task in tasks]

    return TasksListResponse(
        tasks=task_responses,
        total=total,
        hasMore=(offset + len(tasks)) < total,
    )


@router.get(
    "/overdue",
    response_model=TasksListResponse,
    summary="Ueberfaellige Aufgaben",
    description="Holt alle ueberfaelligen Aufgaben."
)
async def get_overdue_tasks(
    limit: int = Query(50, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TasksListResponse:
    """Holt alle ueberfaelligen Aufgaben."""
    task_service = get_document_task_service(db)

    tasks = await task_service.get_overdue_tasks(
        company_id=current_user.company_id,
        limit=limit,
    )

    task_responses = [_build_task_response(task) for task in tasks]

    return TasksListResponse(
        tasks=task_responses,
        total=len(tasks),
        hasMore=False,
    )


@router.get(
    "/statistics",
    response_model=TaskStatistics,
    summary="Aufgaben-Statistiken",
    description="Berechnet Aufgaben-Statistiken."
)
async def get_task_statistics(
    my_stats_only: bool = Query(False, description="Nur eigene Statistiken"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TaskStatistics:
    """Berechnet Aufgaben-Statistiken."""
    task_service = get_document_task_service(db)

    user_id = current_user.id if my_stats_only else None

    stats = await task_service.get_task_statistics(
        company_id=current_user.company_id,
        user_id=user_id,
    )

    return TaskStatistics(**stats)


@router.get(
    "/{task_id}",
    response_model=TaskResponse,
    summary="Aufgabe abrufen",
    description="Ruft eine einzelne Aufgabe ab."
)
async def get_task(
    task_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TaskResponse:
    """Ruft eine einzelne Aufgabe ab."""
    task_service = get_document_task_service(db)

    task = await task_service.get_task(
        task_id=task_id,
        company_id=current_user.company_id,
    )

    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Aufgabe nicht gefunden"
        )

    return _build_task_response(task)


@router.patch(
    "/{task_id}",
    response_model=TaskResponse,
    summary="Aufgabe aktualisieren",
    description="Aktualisiert eine Aufgabe."
)
async def update_task(
    task_id: UUID,
    task_data: TaskUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TaskResponse:
    """Aktualisiert eine Aufgabe."""
    task_service = get_document_task_service(db)

    try:
        task = await task_service.update_task(
            task_id=task_id,
            company_id=current_user.company_id,
            updated_by_id=current_user.id,
            title=task_data.title,
            description=task_data.description,
            priority=task_data.priority.value if task_data.priority else None,
            due_date=task_data.dueDate,
            metadata=task_data.metadata,
        )

        if not task:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Aufgabe nicht gefunden"
            )

        logger.info(
            "document_task_updated_via_api",
            task_id=str(task_id),
            updated_by=str(current_user.id),
        )

        return _build_task_response(task)

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=safe_error_detail(e, "Dokument-Aufgabe")
        )


@router.delete(
    "/{task_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    summary="Aufgabe loeschen",
    description="Loescht eine Aufgabe."
)
async def delete_task(
    task_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Loescht eine Aufgabe."""
    task_service = get_document_task_service(db)

    deleted = await task_service.delete_task(
        task_id=task_id,
        company_id=current_user.company_id,
        deleted_by_id=current_user.id,
    )

    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Aufgabe nicht gefunden"
        )

    logger.info(
        "document_task_deleted_via_api",
        task_id=str(task_id),
        deleted_by=str(current_user.id),
    )

    return Response(status_code=status.HTTP_204_NO_CONTENT)


# =============================================================================
# Status Transition Endpoints
# =============================================================================


@router.post(
    "/{task_id}/start",
    response_model=TaskResponse,
    summary="Aufgabe starten",
    description="Startet die Bearbeitung einer Aufgabe."
)
async def start_task(
    task_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TaskResponse:
    """Startet die Bearbeitung einer Aufgabe."""
    task_service = get_document_task_service(db)

    try:
        task = await task_service.start_task(
            task_id=task_id,
            company_id=current_user.company_id,
            user_id=current_user.id,
        )

        if not task:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Aufgabe nicht gefunden"
            )

        logger.info(
            "document_task_started_via_api",
            task_id=str(task_id),
            started_by=str(current_user.id),
        )

        return _build_task_response(task)

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=safe_error_detail(e, "Dokument-Aufgabe")
        )


@router.post(
    "/{task_id}/complete",
    response_model=TaskResponse,
    summary="Aufgabe abschliessen",
    description="Schliesst eine Aufgabe ab."
)
async def complete_task(
    task_id: UUID,
    request_body: Optional[TaskCompleteRequest] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TaskResponse:
    """Schliesst eine Aufgabe ab."""
    task_service = get_document_task_service(db)

    completion_notes = request_body.completionNotes if request_body else None

    try:
        task = await task_service.complete_task(
            task_id=task_id,
            company_id=current_user.company_id,
            completed_by_id=current_user.id,
            completion_notes=completion_notes,
        )

        if not task:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Aufgabe nicht gefunden"
            )

        logger.info(
            "document_task_completed_via_api",
            task_id=str(task_id),
            completed_by=str(current_user.id),
        )

        return _build_task_response(task)

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=safe_error_detail(e, "Dokument-Aufgabe")
        )


@router.post(
    "/{task_id}/cancel",
    response_model=TaskResponse,
    summary="Aufgabe abbrechen",
    description="Bricht eine Aufgabe ab."
)
async def cancel_task(
    task_id: UUID,
    reason: Optional[str] = Query(None, description="Grund fuer Abbruch"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TaskResponse:
    """Bricht eine Aufgabe ab."""
    task_service = get_document_task_service(db)

    try:
        task = await task_service.cancel_task(
            task_id=task_id,
            company_id=current_user.company_id,
            cancelled_by_id=current_user.id,
            reason=reason,
        )

        if not task:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Aufgabe nicht gefunden"
            )

        logger.info(
            "document_task_cancelled_via_api",
            task_id=str(task_id),
            cancelled_by=str(current_user.id),
        )

        return _build_task_response(task)

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=safe_error_detail(e, "Dokument-Aufgabe")
        )


@router.post(
    "/{task_id}/block",
    response_model=TaskResponse,
    summary="Aufgabe blockieren",
    description="Markiert eine Aufgabe als blockiert."
)
async def block_task(
    task_id: UUID,
    reason: str = Query(..., description="Grund fuer Blockierung"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TaskResponse:
    """Markiert eine Aufgabe als blockiert."""
    task_service = get_document_task_service(db)

    try:
        task = await task_service.block_task(
            task_id=task_id,
            company_id=current_user.company_id,
            blocked_by_id=current_user.id,
            reason=reason,
        )

        if not task:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Aufgabe nicht gefunden"
            )

        logger.info(
            "document_task_blocked_via_api",
            task_id=str(task_id),
            blocked_by=str(current_user.id),
        )

        return _build_task_response(task)

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=safe_error_detail(e, "Dokument-Aufgabe")
        )


@router.post(
    "/{task_id}/unblock",
    response_model=TaskResponse,
    summary="Aufgabe entblocken",
    description="Hebt die Blockierung einer Aufgabe auf."
)
async def unblock_task(
    task_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TaskResponse:
    """Hebt die Blockierung einer Aufgabe auf."""
    task_service = get_document_task_service(db)

    try:
        task = await task_service.unblock_task(
            task_id=task_id,
            company_id=current_user.company_id,
            unblocked_by_id=current_user.id,
        )

        if not task:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Aufgabe nicht gefunden"
            )

        logger.info(
            "document_task_unblocked_via_api",
            task_id=str(task_id),
            unblocked_by=str(current_user.id),
        )

        return _build_task_response(task)

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=safe_error_detail(e, "Dokument-Aufgabe")
        )


# =============================================================================
# Assignment Endpoints
# =============================================================================


@router.post(
    "/{task_id}/assign",
    response_model=TaskResponse,
    summary="Aufgabe zuweisen",
    description="Weist eine Aufgabe einem Benutzer zu."
)
async def assign_task(
    task_id: UUID,
    request_body: TaskAssignRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TaskResponse:
    """Weist eine Aufgabe einem Benutzer zu."""
    task_service = get_document_task_service(db)

    try:
        task = await task_service.assign_task(
            task_id=task_id,
            company_id=current_user.company_id,
            assigned_to_id=request_body.assignedToId,
            assigned_by_id=current_user.id,
            notify_assignee=request_body.notifyAssignee,
        )

        if not task:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Aufgabe nicht gefunden"
            )

        logger.info(
            "document_task_assigned_via_api",
            task_id=str(task_id),
            assigned_to=str(request_body.assignedToId),
            assigned_by=str(current_user.id),
        )

        return _build_task_response(task)

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=safe_error_detail(e, "Dokument-Aufgabe")
        )


@router.post(
    "/{task_id}/unassign",
    response_model=TaskResponse,
    summary="Zuweisung aufheben",
    description="Entfernt die Zuweisung einer Aufgabe."
)
async def unassign_task(
    task_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TaskResponse:
    """Entfernt die Zuweisung einer Aufgabe."""
    task_service = get_document_task_service(db)

    task = await task_service.unassign_task(
        task_id=task_id,
        company_id=current_user.company_id,
        unassigned_by_id=current_user.id,
    )

    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Aufgabe nicht gefunden"
        )

    logger.info(
        "document_task_unassigned_via_api",
        task_id=str(task_id),
        unassigned_by=str(current_user.id),
    )

    return _build_task_response(task)


# =============================================================================
# Document-Specific Endpoints
# =============================================================================


@router.get(
    "/document/{document_id}",
    response_model=TasksListResponse,
    summary="Dokument-Aufgaben",
    description="Holt alle Aufgaben fuer ein Dokument."
)
async def get_document_tasks(
    document_id: UUID,
    include_completed: bool = Query(False, description="Auch abgeschlossene einbeziehen"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TasksListResponse:
    """Holt alle Aufgaben fuer ein bestimmtes Dokument."""
    # Pruefe Dokumentzugriff
    await _verify_document_access(db, document_id, current_user.id)

    task_service = get_document_task_service(db)

    tasks = await task_service.get_document_tasks(
        document_id=document_id,
        company_id=current_user.company_id,
        include_completed=include_completed,
    )

    task_responses = [_build_task_response(task) for task in tasks]

    return TasksListResponse(
        tasks=task_responses,
        total=len(tasks),
        hasMore=False,
    )
