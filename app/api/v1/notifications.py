"""
Notifications API Endpoints.

Enterprise-level Benachrichtigungssystem:
- Benachrichtigungen abrufen (gefiltert/paginiert)
- Als gelesen markieren (einzeln/alle)
- Benachrichtigungen loeschen
- Unread-Count fuer Badge

Feinpoliert und durchdacht - Real-time Benachrichtigungen auf Enterprise-Niveau.
"""

import structlog
from typing import Optional
from uuid import UUID
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, update
from sqlalchemy.orm import selectinload

from app.db.models import (
    User,
    Document,
    UserNotification,
)
from app.api.dependencies import get_current_user, get_db
from app.db.schemas import (
    NotificationResponse,
    NotificationsListResponse,
)

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/notifications", tags=["notifications"])


def _build_notification_response(
    notification: UserNotification,
    from_user: Optional[User],
    document: Optional[Document],
) -> NotificationResponse:
    """Erstellt NotificationResponse aus DB-Modell."""
    return NotificationResponse(
        id=str(notification.id),
        type=notification.notification_type,
        title=notification.title,
        message=notification.message,
        documentId=str(notification.document_id) if notification.document_id else None,
        documentName=document.original_filename or document.filename if document else None,
        fromUserId=str(notification.from_user_id) if notification.from_user_id else "",
        fromUserName=from_user.full_name or from_user.username or from_user.email if from_user else "System",
        fromUserAvatar=None,
        isRead=notification.is_read,
        createdAt=notification.created_at.isoformat() if notification.created_at else "",
        actionUrl=notification.action_url,
    )


@router.get(
    "/",
    response_model=NotificationsListResponse,
    summary="Benachrichtigungen auflisten",
    description="Gibt alle Benachrichtigungen des aktuellen Benutzers zurueck."
)
async def list_notifications(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    unread_only: bool = Query(False, description="Nur ungelesene Benachrichtigungen"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> NotificationsListResponse:
    """Liste aller Benachrichtigungen des Benutzers."""
    # Base filter
    base_filter = UserNotification.user_id == current_user.id
    if unread_only:
        base_filter = and_(base_filter, UserNotification.is_read == False)

    # Unread count (immer alle ungelesenen)
    unread_result = await db.execute(
        select(func.count(UserNotification.id)).where(
            and_(
                UserNotification.user_id == current_user.id,
                UserNotification.is_read == False,
            )
        )
    )
    unread_count = unread_result.scalar() or 0

    # Total count
    count_result = await db.execute(
        select(func.count(UserNotification.id)).where(base_filter)
    )
    total = count_result.scalar() or 0

    # Query Notifications mit Eager Loading (N+1 Fix)
    query = (
        select(UserNotification)
        .options(selectinload(UserNotification.from_user))
        .options(selectinload(UserNotification.document))
        .where(base_filter)
        .order_by(UserNotification.created_at.desc())
        .limit(limit)
        .offset(offset)
    )

    result = await db.execute(query)
    notifications_db = result.scalars().all()

    # Baue Responses mit bereits geladenen Relations
    notifications = [
        _build_notification_response(notif, notif.from_user, notif.document)
        for notif in notifications_db
    ]

    return NotificationsListResponse(
        notifications=notifications,
        unreadCount=unread_count,
        total=total,
    )


@router.get(
    "/unread-count",
    summary="Ungelesene Anzahl",
    description="Gibt die Anzahl ungelesener Benachrichtigungen zurueck."
)
async def get_unread_count(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Anzahl ungelesener Benachrichtigungen."""
    result = await db.execute(
        select(func.count(UserNotification.id)).where(
            and_(
                UserNotification.user_id == current_user.id,
                UserNotification.is_read == False,
            )
        )
    )
    count = result.scalar() or 0

    return {"unreadCount": count}


@router.patch(
    "/{notification_id}/read",
    response_model=NotificationResponse,
    summary="Als gelesen markieren",
    description="Markiert eine Benachrichtigung als gelesen."
)
async def mark_as_read(
    notification_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> NotificationResponse:
    """Benachrichtigung als gelesen markieren."""
    result = await db.execute(
        select(UserNotification)
        .options(selectinload(UserNotification.from_user))
        .options(selectinload(UserNotification.document))
        .where(
            and_(
                UserNotification.id == notification_id,
                UserNotification.user_id == current_user.id,
            )
        )
    )
    notification = result.scalar_one_or_none()

    if not notification:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Benachrichtigung nicht gefunden"
        )

    notification.is_read = True
    notification.read_at = datetime.utcnow()
    await db.commit()
    await db.refresh(notification)

    logger.info(
        "notification_marked_read",
        notification_id=str(notification_id),
        user_id=str(current_user.id),
    )

    return _build_notification_response(notification, notification.from_user, notification.document)


@router.post(
    "/mark-all-read",
    summary="Alle als gelesen markieren",
    description="Markiert alle Benachrichtigungen als gelesen."
)
async def mark_all_as_read(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Alle Benachrichtigungen als gelesen markieren."""
    now = datetime.utcnow()

    await db.execute(
        update(UserNotification)
        .where(
            and_(
                UserNotification.user_id == current_user.id,
                UserNotification.is_read == False,
            )
        )
        .values(is_read=True, read_at=now)
    )
    await db.commit()

    logger.info(
        "notifications_all_marked_read",
        user_id=str(current_user.id),
    )

    return {"message": "Alle Benachrichtigungen als gelesen markiert", "success": True}


@router.delete(
    "/{notification_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Benachrichtigung loeschen",
    description="Loescht eine Benachrichtigung."
)
async def delete_notification(
    notification_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Benachrichtigung loeschen."""
    result = await db.execute(
        select(UserNotification).where(
            and_(
                UserNotification.id == notification_id,
                UserNotification.user_id == current_user.id,
            )
        )
    )
    notification = result.scalar_one_or_none()

    if not notification:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Benachrichtigung nicht gefunden"
        )

    await db.delete(notification)
    await db.commit()

    logger.info(
        "notification_deleted",
        notification_id=str(notification_id),
        user_id=str(current_user.id),
    )


@router.delete(
    "/",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Alle Benachrichtigungen loeschen",
    description="Loescht alle Benachrichtigungen des Benutzers."
)
async def delete_all_notifications(
    read_only: bool = Query(False, description="Nur gelesene Benachrichtigungen loeschen"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Alle Benachrichtigungen loeschen."""
    from sqlalchemy import delete as sql_delete

    filter_cond = UserNotification.user_id == current_user.id
    if read_only:
        filter_cond = and_(filter_cond, UserNotification.is_read == True)

    await db.execute(
        sql_delete(UserNotification).where(filter_cond)
    )
    await db.commit()

    logger.info(
        "notifications_all_deleted",
        user_id=str(current_user.id),
        read_only=read_only,
    )
