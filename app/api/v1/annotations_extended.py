"""Erweiterte Annotationen & Kommentar-Aufgaben API.

Endpoints für:
- Bounding-Box-Annotationen (PDF-Markierungen)
- Verschachtelte Kommentar-Antworten mit @Mentions
- Aufgaben aus Kommentar-Threads
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from app.core.safe_errors import safe_error_detail
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user
from app.db.models import User
from app.db.models_annotations_extended import (
    BoundingBoxAnnotation,
    CommentReply,
    CommentTask,
)
from app.db.session import get_async_session
from app.services.annotations.extended_annotation_service import (
    ExtendedAnnotationService,
)

router = APIRouter(
    prefix="/annotations",
    tags=["Annotationen & Kommentare"],
)


# ============================================================================
# Pydantic Schemas
# ============================================================================


class BoundingBoxCreate(BaseModel):
    """Schema für neue Bounding-Box-Annotation."""

    document_id: UUID
    page_number: int = Field(..., ge=1, description="Seitennummer (1-basiert)")
    x: float = Field(..., ge=0.0, le=1.0, description="X-Position (0.0 - 1.0)")
    y: float = Field(..., ge=0.0, le=1.0, description="Y-Position (0.0 - 1.0)")
    width: float = Field(
        ..., ge=0.0, le=1.0, description="Breite (0.0 - 1.0)"
    )
    height: float = Field(
        ..., ge=0.0, le=1.0, description="Höhe (0.0 - 1.0)"
    )
    annotation_type: str = Field(
        default="bounding_box",
        pattern="^(comment|highlight|bounding_box|pin|task)$",
    )
    label: Optional[str] = Field(None, max_length=500)
    color: str = Field(default="#FFD700", max_length=20)
    thread_id: Optional[UUID] = None


class BoundingBoxResponse(BaseModel):
    """Schema für Bounding-Box-Antwort."""

    id: UUID
    document_id: UUID
    page_number: int
    x: float
    y: float
    width: float
    height: float
    annotation_type: str
    label: Optional[str] = None
    color: str
    author_id: UUID
    thread_id: Optional[UUID] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    model_config = {"from_attributes": True}


class ReplyCreate(BaseModel):
    """Schema für neue Kommentar-Antwort."""

    content: str = Field(..., min_length=1, max_length=5000)
    mentions: Optional[List[str]] = Field(
        default=None,
        description="Liste von erwaehnten User-UUIDs",
    )
    parent_reply_id: Optional[UUID] = Field(
        default=None,
        description="Eltern-Antwort für verschachtelte Antworten",
    )


class ReplyResponse(BaseModel):
    """Schema für Kommentar-Antwort."""

    id: UUID
    thread_id: UUID
    parent_reply_id: Optional[UUID] = None
    author_id: UUID
    content: str
    mentions: List[str]
    is_edited: bool
    edited_at: Optional[str] = None
    created_at: Optional[str] = None

    model_config = {"from_attributes": True}


class TaskCreate(BaseModel):
    """Schema für neue Kommentar-Aufgabe."""

    assigned_to_user_id: UUID
    title: str = Field(..., min_length=1, max_length=500)
    description: Optional[str] = Field(None, max_length=5000)
    due_date: Optional[datetime] = None


class TaskResponse(BaseModel):
    """Schema für Kommentar-Aufgabe."""

    id: UUID
    thread_id: UUID
    assigned_to_user_id: UUID
    title: str
    description: Optional[str] = None
    status: str
    due_date: Optional[str] = None
    completed_at: Optional[str] = None
    created_by_user_id: Optional[UUID] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    model_config = {"from_attributes": True}


class TaskStatusUpdate(BaseModel):
    """Schema für Statusänderung einer Aufgabe."""

    status: str = Field(
        ...,
        pattern="^(offen|in_bearbeitung|erledigt)$",
        description="Neuer Status: offen, in_bearbeitung, erledigt",
    )


# ============================================================================
# Helper Functions
# ============================================================================


def _bbox_to_response(annotation: BoundingBoxAnnotation) -> BoundingBoxResponse:
    """Konvertiert BoundingBoxAnnotation zu Response-Schema."""
    return BoundingBoxResponse(
        id=annotation.id,
        document_id=annotation.document_id,
        page_number=annotation.page_number,
        x=annotation.x,
        y=annotation.y,
        width=annotation.width,
        height=annotation.height,
        annotation_type=annotation.annotation_type,
        label=annotation.label,
        color=annotation.color,
        author_id=annotation.author_id,
        thread_id=annotation.thread_id,
        created_at=(
            annotation.created_at.isoformat()
            if annotation.created_at
            else None
        ),
        updated_at=(
            annotation.updated_at.isoformat()
            if annotation.updated_at
            else None
        ),
    )


def _reply_to_response(reply: CommentReply) -> ReplyResponse:
    """Konvertiert CommentReply zu Response-Schema."""
    return ReplyResponse(
        id=reply.id,
        thread_id=reply.thread_id,
        parent_reply_id=reply.parent_reply_id,
        author_id=reply.author_id,
        content=reply.content,
        mentions=reply.mentions or [],
        is_edited=reply.is_edited,
        edited_at=(
            reply.edited_at.isoformat()
            if reply.edited_at
            else None
        ),
        created_at=(
            reply.created_at.isoformat()
            if reply.created_at
            else None
        ),
    )


def _task_to_response(task: CommentTask) -> TaskResponse:
    """Konvertiert CommentTask zu Response-Schema."""
    return TaskResponse(
        id=task.id,
        thread_id=task.thread_id,
        assigned_to_user_id=task.assigned_to_user_id,
        title=task.title,
        description=task.description,
        status=task.status,
        due_date=(
            task.due_date.isoformat()
            if task.due_date
            else None
        ),
        completed_at=(
            task.completed_at.isoformat()
            if task.completed_at
            else None
        ),
        created_by_user_id=task.created_by_user_id,
        created_at=(
            task.created_at.isoformat()
            if task.created_at
            else None
        ),
        updated_at=(
            task.updated_at.isoformat()
            if task.updated_at
            else None
        ),
    )


# ============================================================================
# Bounding Box Endpoints
# ============================================================================


@router.post(
    "/bounding-box",
    response_model=BoundingBoxResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Bounding-Box-Annotation erstellen",
)
async def create_bounding_box(
    data: BoundingBoxCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
) -> BoundingBoxResponse:
    """Erstellt eine neue Bounding-Box-Annotation auf einer PDF-Seite."""
    service = ExtendedAnnotationService(db)

    try:
        annotation = await service.create_bounding_box(
            document_id=data.document_id,
            page_number=data.page_number,
            x=data.x,
            y=data.y,
            width=data.width,
            height=data.height,
            author_id=current_user.id,
            label=data.label,
            color=data.color,
            annotation_type=data.annotation_type,
            thread_id=data.thread_id,
        )
        await db.commit()
        return _bbox_to_response(annotation)

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=safe_error_detail(e, "Annotation"),
        )


@router.get(
    "/document/{document_id}/page/{page_number}",
    response_model=List[BoundingBoxResponse],
    summary="Annotationen für Seite abrufen",
)
async def get_page_annotations(
    document_id: UUID,
    page_number: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
) -> List[BoundingBoxResponse]:
    """Holt alle Bounding-Box-Annotationen für eine Dokumentseite."""
    service = ExtendedAnnotationService(db)

    annotations = await service.get_page_annotations(
        document_id=document_id,
        page_number=page_number,
    )

    return [_bbox_to_response(a) for a in annotations]


# ============================================================================
# Comment Reply Endpoints
# ============================================================================


@router.post(
    "/threads/{thread_id}/replies",
    response_model=ReplyResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Kommentar-Antwort erstellen",
    # Eindeutige operation_id: kollidierte mit annotations_enhanced.py
    operation_id="extended_create_reply",
)
async def create_reply(
    thread_id: UUID,
    data: ReplyCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
) -> ReplyResponse:
    """Erstellt eine verschachtelte Antwort auf einen Kommentar-Thread.

    Unterstützt @Mentions - erwaehnte Benutzer erhalten Benachrichtigungen.
    """
    service = ExtendedAnnotationService(db)

    try:
        reply = await service.create_reply(
            thread_id=thread_id,
            author_id=current_user.id,
            content=data.content,
            mentions=data.mentions,
            parent_reply_id=data.parent_reply_id,
        )
        await db.commit()
        return _reply_to_response(reply)

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=safe_error_detail(e, "Annotation"),
        )


@router.get(
    "/threads/{thread_id}/tree",
    summary="Thread mit verschachtelten Antworten abrufen",
)
async def get_thread_tree(
    thread_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
) -> dict:
    """Holt einen Kommentar-Thread mit allen verschachtelten Antworten als Baumstruktur."""
    service = ExtendedAnnotationService(db)

    try:
        tree = await service.get_thread_with_replies(thread_id=thread_id)
        return tree

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=safe_error_detail(e, "Annotation"),
        )


# ============================================================================
# Comment Task Endpoints
# ============================================================================


@router.post(
    "/threads/{thread_id}/tasks",
    response_model=TaskResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Aufgabe aus Kommentar-Thread erstellen",
)
async def create_comment_task(
    thread_id: UUID,
    data: TaskCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
) -> TaskResponse:
    """Erstellt eine Aufgabe aus einem Kommentar-Thread."""
    service = ExtendedAnnotationService(db)

    try:
        task = await service.create_comment_task(
            thread_id=thread_id,
            assigned_to_user_id=data.assigned_to_user_id,
            title=data.title,
            created_by_user_id=current_user.id,
            description=data.description,
            due_date=data.due_date,
        )
        await db.commit()
        return _task_to_response(task)

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=safe_error_detail(e, "Annotation"),
        )


@router.get(
    "/tasks/my",
    response_model=List[TaskResponse],
    summary="Meine zugewiesenen Aufgaben",
)
async def get_my_tasks(
    task_status: Optional[str] = Query(
        default=None,
        alias="status",
        pattern="^(offen|in_bearbeitung|erledigt)$",
        description="Status-Filter",
    ),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
) -> List[TaskResponse]:
    """Holt alle Aufgaben die dem aktuellen Benutzer zugewiesen sind."""
    service = ExtendedAnnotationService(db)

    tasks = await service.get_user_tasks(
        user_id=current_user.id,
        status=task_status,
    )

    return [_task_to_response(t) for t in tasks]


@router.patch(
    "/tasks/{task_id}/status",
    response_model=TaskResponse,
    summary="Aufgaben-Status ändern",
)
async def update_task_status(
    task_id: UUID,
    data: TaskStatusUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
) -> TaskResponse:
    """Aktualisiert den Status einer Kommentar-Aufgabe.

    Erlaubte Status: offen, in_bearbeitung, erledigt
    """
    service = ExtendedAnnotationService(db)

    try:
        task = await service.update_task_status(
            task_id=task_id,
            status=data.status,
            user_id=current_user.id,
        )

        if not task:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Aufgabe nicht gefunden",
            )

        await db.commit()
        return _task_to_response(task)

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=safe_error_detail(e, "Annotation"),
        )


# ============================================================================
# Delete Annotation
# ============================================================================


@router.delete(
    "/{annotation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    summary="Annotation löschen",
    # Eindeutige operation_id: kollidierte mit annotations.py/_enhanced.py
    operation_id="extended_delete_annotation",
)
async def delete_annotation(
    annotation_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
) -> None:
    """Löscht eine Bounding-Box-Annotation (nur eigene, Soft-Delete)."""
    service = ExtendedAnnotationService(db)

    deleted = await service.delete_annotation(
        annotation_id=annotation_id,
        user_id=current_user.id,
    )

    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Annotation nicht gefunden oder keine Berechtigung",
        )

    await db.commit()
