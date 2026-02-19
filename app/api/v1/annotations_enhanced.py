# -*- coding: utf-8 -*-
"""Erweiterte Annotationen & Kommentare API Router.

Endpoints für:
- Erweiterte Annotationen (Bounding Box, Pfeile, Stempel)
- Verschachtelte Kommentar-Antworten mit @mentions
- Aufgaben aus Kommentaren
- Mention-Benachrichtigungen
"""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from app.core.safe_errors import safe_error_detail
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user
from app.db.session import get_async_session
from app.db.models_annotations_extended import AnnotationType, CommentTaskStatus

router = APIRouter(prefix="/annotations", tags=["Annotationen & Kommentare"])


# ============================================================================
# Pydantic Schemas
# ============================================================================


class AnnotationCreateRequest(BaseModel):
    """Schema für neue erweiterte Annotation."""
    annotation_type: str = Field(
        ...,
        description="Typ: comment, highlight, bounding_box, arrow, stamp",
    )
    page_number: int = Field(..., ge=1)
    x: float = Field(..., ge=0.0, le=1.0, description="X-Position normalisiert")
    y: float = Field(..., ge=0.0, le=1.0, description="Y-Position normalisiert")
    width: Optional[float] = Field(None, ge=0.0, le=1.0)
    height: Optional[float] = Field(None, ge=0.0, le=1.0)
    text: Optional[str] = Field(None, max_length=5000)
    color: str = Field(default="#FFD700", pattern=r"^#[0-9A-Fa-f]{6}$")


class AnnotationUpdateRequest(BaseModel):
    """Schema für Annotation-Update."""
    content: Optional[str] = Field(None, max_length=5000)
    color: Optional[str] = Field(None, pattern=r"^#[0-9A-Fa-f]{6}$")


class ReplyCreateRequest(BaseModel):
    """Schema für neue Kommentar-Antwort."""
    content: str = Field(..., min_length=1, max_length=5000)
    parent_reply_id: Optional[UUID] = None
    mentions: Optional[List[UUID]] = None


class ReplyEditRequest(BaseModel):
    """Schema für Antwort-Bearbeitung."""
    content: str = Field(..., min_length=1, max_length=5000)


class TaskCreateRequest(BaseModel):
    """Schema für Aufgabe aus Kommentar."""
    title: str = Field(..., min_length=1, max_length=300)
    description: Optional[str] = Field(None, max_length=2000)
    thread_id: Optional[UUID] = None
    reply_id: Optional[UUID] = None
    assigned_to: Optional[UUID] = None
    due_date: Optional[datetime] = None


class TaskStatusUpdateRequest(BaseModel):
    """Schema für Aufgaben-Status-Update."""
    status: str = Field(
        ...,
        description="offen, in_bearbeitung, erledigt",
    )


# ============================================================================
# Annotation Endpoints
# ============================================================================


@router.post(
    "/{document_id}",
    status_code=status.HTTP_201_CREATED,
    summary="Annotation erstellen",
)
async def create_annotation(
    document_id: UUID,
    data: AnnotationCreateRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
) -> dict:
    """Erstellt eine neue erweiterte Annotation auf einem Dokument."""
    from app.services.annotation_service import get_enhanced_annotation_service

    service = get_enhanced_annotation_service()

    try:
        annotation_type = AnnotationType(data.annotation_type)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Ungültiger Annotationstyp: {data.annotation_type}",
        )

    annotation = await service.create_annotation(
        db=db,
        company_id=current_user["company_id"],
        document_id=document_id,
        author_id=current_user["id"],
        annotation_type=annotation_type,
        page_number=data.page_number,
        x=data.x,
        y=data.y,
        width=data.width,
        height=data.height,
        text=data.text,
        color=data.color,
    )
    await db.commit()

    return {
        "id": str(annotation.id),
        "document_id": str(annotation.document_id),
        "annotation_type": annotation.annotation_type,
        "page": annotation.page,
        "position": annotation.position,
        "content": annotation.content,
        "color": annotation.color,
        "created_at": annotation.created_at.isoformat() if annotation.created_at else None,
    }


@router.get(
    "/{document_id}",
    summary="Annotationen abrufen",
)
async def get_annotations(
    document_id: UUID,
    page_number: Optional[int] = None,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
) -> List[dict]:
    """Alle Annotationen für ein Dokument abrufen (optional nach Seite filtern)."""
    from app.services.annotation_service import get_enhanced_annotation_service

    service = get_enhanced_annotation_service()
    annotations = await service.get_annotations(
        db=db,
        document_id=document_id,
        page_number=page_number,
    )

    return [
        {
            "id": str(a.id),
            "document_id": str(a.document_id),
            "user_id": str(a.user_id),
            "annotation_type": a.annotation_type,
            "page": a.page,
            "position": a.position,
            "content": a.content,
            "color": a.color,
            "is_resolved": a.is_resolved,
            "created_at": a.created_at.isoformat() if a.created_at else None,
        }
        for a in annotations
    ]


@router.put(
    "/{annotation_id}",
    summary="Annotation aktualisieren",
)
async def update_annotation(
    annotation_id: UUID,
    data: AnnotationUpdateRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
) -> dict:
    """Annotation aktualisieren."""
    from app.services.annotation_service import get_enhanced_annotation_service

    service = get_enhanced_annotation_service()
    try:
        updates = {}
        if data.content is not None:
            updates["content"] = data.content
        if data.color is not None:
            updates["color"] = data.color

        annotation = await service.update_annotation(
            db=db,
            annotation_id=annotation_id,
            user_id=current_user["id"],
            **updates,
        )
        await db.commit()
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=safe_error_detail(e, "Annotation"),
        )

    return {
        "id": str(annotation.id),
        "content": annotation.content,
        "color": annotation.color,
        "updated_at": annotation.updated_at.isoformat() if annotation.updated_at else None,
    }


@router.post(
    "/{annotation_id}/resolve",
    summary="Annotation als erledigt markieren",
)
async def resolve_annotation(
    annotation_id: UUID,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
) -> dict:
    """Annotation als erledigt markieren."""
    from app.services.annotation_service import get_enhanced_annotation_service

    service = get_enhanced_annotation_service()
    try:
        annotation = await service.resolve_annotation(
            db=db,
            annotation_id=annotation_id,
            user_id=current_user["id"],
        )
        await db.commit()
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=safe_error_detail(e, "Annotation"),
        )

    return {
        "id": str(annotation.id),
        "is_resolved": annotation.is_resolved,
        "resolved_at": annotation.resolved_at.isoformat() if annotation.resolved_at else None,
    }


@router.delete(
    "/{annotation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Annotation löschen",
)
async def delete_annotation(
    annotation_id: UUID,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
) -> None:
    """Annotation löschen (nur Autor)."""
    from app.services.annotation_service import get_enhanced_annotation_service

    service = get_enhanced_annotation_service()
    deleted = await service.delete_annotation(
        db=db,
        annotation_id=annotation_id,
        user_id=current_user["id"],
    )
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Annotation nicht gefunden oder keine Berechtigung",
        )
    await db.commit()


# ============================================================================
# Comment Reply Endpoints
# ============================================================================


@router.post(
    "/threads/{thread_id}/replies",
    status_code=status.HTTP_201_CREATED,
    summary="Antwort erstellen",
)
async def create_reply(
    thread_id: UUID,
    data: ReplyCreateRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
) -> dict:
    """Antwort auf einen Kommentar-Thread erstellen mit optionalen @mentions."""
    from app.services.comment_reply_service import get_comment_reply_service

    service = get_comment_reply_service()
    reply = await service.create_reply(
        db=db,
        company_id=current_user["company_id"],
        thread_id=thread_id,
        author_id=current_user["id"],
        content=data.content,
        parent_reply_id=data.parent_reply_id,
        mentions=data.mentions,
    )
    await db.commit()

    return {
        "id": str(reply.id),
        "thread_id": str(reply.thread_id),
        "author_id": str(reply.author_id),
        "content": reply.content,
        "parent_reply_id": str(reply.parent_reply_id) if reply.parent_reply_id else None,
        "mentions": reply.mentions,
        "created_at": reply.created_at.isoformat() if reply.created_at else None,
    }


@router.get(
    "/threads/{thread_id}/replies",
    summary="Thread-Antworten abrufen",
)
async def get_thread_replies(
    thread_id: UUID,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
) -> List[dict]:
    """Alle Antworten eines Kommentar-Threads abrufen."""
    from app.services.comment_reply_service import get_comment_reply_service

    service = get_comment_reply_service()
    replies = await service.get_thread_replies(db=db, thread_id=thread_id)

    return [
        {
            "id": str(r.id),
            "thread_id": str(r.thread_id),
            "author_id": str(r.author_id),
            "content": r.content,
            "parent_reply_id": str(r.parent_reply_id) if r.parent_reply_id else None,
            "mentions": r.mentions,
            "is_edited": r.is_edited,
            "edited_at": r.edited_at.isoformat() if r.edited_at else None,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in replies
    ]


@router.put(
    "/replies/{reply_id}",
    summary="Antwort bearbeiten",
)
async def edit_reply(
    reply_id: UUID,
    data: ReplyEditRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
) -> dict:
    """Antwort bearbeiten (nur Autor)."""
    from app.services.comment_reply_service import get_comment_reply_service

    service = get_comment_reply_service()
    try:
        reply = await service.edit_reply(
            db=db,
            reply_id=reply_id,
            author_id=current_user["id"],
            new_content=data.content,
        )
        await db.commit()
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=safe_error_detail(e, "Annotation"),
        )

    return {
        "id": str(reply.id),
        "content": reply.content,
        "is_edited": reply.is_edited,
        "edited_at": reply.edited_at.isoformat() if reply.edited_at else None,
    }


# ============================================================================
# Comment Task Endpoints
# ============================================================================


@router.post(
    "/tasks",
    status_code=status.HTTP_201_CREATED,
    summary="Aufgabe aus Kommentar erstellen",
)
async def create_task(
    data: TaskCreateRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
) -> dict:
    """Aufgabe aus einem Kommentar oder einer Antwort erstellen."""
    from app.services.comment_reply_service import get_comment_reply_service

    service = get_comment_reply_service()
    task = await service.create_task_from_comment(
        db=db,
        company_id=current_user["company_id"],
        created_by=current_user["id"],
        title=data.title,
        thread_id=data.thread_id,
        reply_id=data.reply_id,
        assigned_to=data.assigned_to,
        description=data.description,
        due_date=data.due_date,
    )
    await db.commit()

    return {
        "id": str(task.id),
        "title": task.title,
        "description": task.description,
        "status": task.status,
        "assigned_to": str(task.assigned_to_user_id) if task.assigned_to_user_id else None,
        "due_date": task.due_date.isoformat() if task.due_date else None,
        "created_at": task.created_at.isoformat() if task.created_at else None,
    }


@router.get(
    "/tasks",
    summary="Kommentar-Aufgaben abrufen",
)
async def get_tasks(
    assigned_to: Optional[UUID] = None,
    task_status: Optional[str] = None,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
) -> List[dict]:
    """Kommentar-Aufgaben abrufen (optional filtern)."""
    from app.services.comment_reply_service import get_comment_reply_service

    service = get_comment_reply_service()
    tasks = await service.get_tasks(
        db=db,
        company_id=current_user["company_id"],
        assigned_to=assigned_to,
        status=task_status,
    )

    return [
        {
            "id": str(t.id),
            "title": t.title,
            "description": t.description,
            "status": t.status,
            "assigned_to": str(t.assigned_to_user_id) if t.assigned_to_user_id else None,
            "due_date": t.due_date.isoformat() if t.due_date else None,
            "completed_at": t.completed_at.isoformat() if t.completed_at else None,
            "created_at": t.created_at.isoformat() if t.created_at else None,
        }
        for t in tasks
    ]


@router.patch(
    "/tasks/{task_id}",
    summary="Aufgaben-Status aktualisieren",
)
async def update_task_status(
    task_id: UUID,
    data: TaskStatusUpdateRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
) -> dict:
    """Aufgaben-Status aktualisieren."""
    from app.services.comment_reply_service import get_comment_reply_service

    # Status validieren
    valid_statuses = [s.value for s in CommentTaskStatus]
    if data.status not in valid_statuses:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Ungültiger Status. Erlaubt: {', '.join(valid_statuses)}",
        )

    service = get_comment_reply_service()
    try:
        task = await service.update_task_status(
            db=db,
            task_id=task_id,
            company_id=current_user["company_id"],
            new_status=data.status,
        )
        await db.commit()
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=safe_error_detail(e, "Annotation"),
        )

    return {
        "id": str(task.id),
        "status": task.status,
        "completed_at": task.completed_at.isoformat() if task.completed_at else None,
    }


# ============================================================================
# Mention Endpoints
# ============================================================================


@router.get(
    "/mentions",
    summary="Meine @mention-Benachrichtigungen",
)
async def get_mentions(
    unread_only: bool = True,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
) -> List[dict]:
    """@mention-Benachrichtigungen für den aktuellen Benutzer abrufen."""
    from app.services.comment_reply_service import get_comment_reply_service

    service = get_comment_reply_service()
    notifications = await service.get_mention_notifications(
        db=db,
        user_id=current_user["id"],
        unread_only=unread_only,
    )

    return [
        {
            "id": str(n.id),
            "mentioning_user_id": str(n.mentioning_user_id),
            "document_id": str(n.document_id),
            "source_type": n.source_type,
            "source_id": str(n.source_id),
            "is_read": n.is_read,
            "created_at": n.created_at.isoformat() if n.created_at else None,
        }
        for n in notifications
    ]


@router.post(
    "/mentions/{notification_id}/read",
    summary="Mention als gelesen markieren",
)
async def mark_mention_read(
    notification_id: UUID,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
) -> dict:
    """@mention-Benachrichtigung als gelesen markieren."""
    from app.services.comment_reply_service import get_comment_reply_service

    service = get_comment_reply_service()
    try:
        notification = await service.mark_mention_read(
            db=db,
            notification_id=notification_id,
            user_id=current_user["id"],
        )
        await db.commit()
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=safe_error_detail(e, "Annotation"),
        )

    return {
        "id": str(notification.id),
        "is_read": notification.is_read,
        "read_at": notification.read_at.isoformat() if notification.read_at else None,
    }
