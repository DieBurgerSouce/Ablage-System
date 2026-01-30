# -*- coding: utf-8 -*-
"""
Notifications API Endpoints - Enterprise Notification Center.

Vollstaendiges Benachrichtigungssystem:
- CRUD fuer Benachrichtigungen (GET, DELETE, mark as read)
- Prioritaeten: critical, warning, info
- Read/Unread Status Tracking
- Bulk Actions (mark all as read, dismiss multiple)
- Filterung nach Typ, Prioritaet, Zeitraum
- WebSocket-Support fuer Echtzeit-Updates
- Per-User Notification Settings

Feinpoliert und durchdacht - Real-time Benachrichtigungen auf Enterprise-Niveau.
"""

import structlog
from typing import Optional, List
from uuid import UUID
from datetime import datetime, timedelta
from app.core.datetime_utils import utc_now

from fastapi import APIRouter, Depends, HTTPException, Query, status, Response, Body
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, update, delete as sql_delete, or_
from sqlalchemy.orm import selectinload
from pydantic import BaseModel, Field, ConfigDict, field_validator

from app.db.models import (
    User,
    Document,
    UserNotification,
    Notification,
    NotificationType,
    NotificationPreference,
    DigestFrequency,
)
from app.api.dependencies import get_current_user, get_db
from app.db.schemas import (
    NotificationResponse,
    NotificationsListResponse,
)

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/notifications", tags=["notifications"])


# =============================================================================
# Pydantic Schemas fuer Notification Center
# =============================================================================


class NotificationPriority(str):
    """Notification priority levels."""
    CRITICAL = "critical"
    WARNING = "warning"
    INFO = "info"


class NotificationFilter(BaseModel):
    """Filter fuer Benachrichtigungen."""
    notification_type: Optional[str] = Field(None, description="Filter nach Typ")
    priority: Optional[str] = Field(None, description="Filter nach Prioritaet (critical/warning/info)")
    read: Optional[bool] = Field(None, description="Filter nach Gelesen-Status")
    from_date: Optional[datetime] = Field(None, description="Datum Von")
    to_date: Optional[datetime] = Field(None, description="Datum Bis")


class NotificationDetailResponse(BaseModel):
    """Detaillierte Notification-Antwort."""
    model_config = ConfigDict(from_attributes=True)

    id: str
    type: str
    title: str
    message: str
    priority: str = "info"
    reference_type: Optional[str] = None
    reference_id: Optional[str] = None
    read: bool = False
    read_at: Optional[datetime] = None
    email_sent: bool = False
    email_sent_at: Optional[datetime] = None
    data: dict = Field(default_factory=dict)
    created_at: datetime
    expires_at: Optional[datetime] = None


class NotificationsListResponseExtended(BaseModel):
    """Erweiterte Liste von Notifications."""
    notifications: List[NotificationDetailResponse]
    unread_count: int
    total: int
    has_critical: bool = False


class BulkDismissRequest(BaseModel):
    """Bulk Dismiss Request."""
    notification_ids: List[str] = Field(..., min_length=1, max_length=100)


class NotificationSettingsResponse(BaseModel):
    """User Notification Settings Response."""
    user_id: str
    preferences: dict = Field(default_factory=dict)
    digest_frequency: str = "immediate"
    quiet_hours_enabled: bool = False
    quiet_hours_start: Optional[str] = None
    quiet_hours_end: Optional[str] = None


class NotificationSettingsUpdate(BaseModel):
    """Update Notification Settings."""
    notification_type: str = Field(..., max_length=50)
    enabled_channels: dict = Field(
        default_factory=lambda: {
            "in_app": True,
            "email": True,
            "websocket": True,
            "slack": False,
            "sms": False
        }
    )
    digest_frequency: str = Field(default="immediate", pattern="^(immediate|daily|weekly)$")


# =============================================================================
# Helper Functions
# =============================================================================


def _build_system_notification_response(notification: Notification) -> NotificationDetailResponse:
    """Erstellt NotificationDetailResponse aus DB-Modell."""
    return NotificationDetailResponse(
        id=str(notification.id),
        type=notification.notification_type,
        title=notification.title,
        message=notification.message,
        priority=_map_notification_type_to_priority(notification.notification_type),
        reference_type=notification.reference_type,
        reference_id=str(notification.reference_id) if notification.reference_id else None,
        read=notification.read,
        read_at=notification.read_at,
        email_sent=notification.email_sent,
        email_sent_at=notification.email_sent_at,
        data=notification.data or {},
        created_at=notification.created_at,
        expires_at=notification.expires_at,
    )


def _map_notification_type_to_priority(notification_type: str) -> str:
    """Mappt NotificationType zu Priority."""
    if notification_type in [NotificationType.ERROR.value, NotificationType.SYSTEM.value]:
        return NotificationPriority.CRITICAL
    elif notification_type in [NotificationType.WARNING.value]:
        return NotificationPriority.WARNING
    else:
        return NotificationPriority.INFO


def _build_notification_response(
    notification: UserNotification,
    from_user: Optional[User],
    document: Optional[Document],
) -> NotificationResponse:
    """Erstellt NotificationResponse aus DB-Modell (Legacy)."""
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


# =============================================================================
# System Notifications Endpoints (Notification Model)
# =============================================================================


@router.get(
    "/system",
    response_model=NotificationsListResponseExtended,
    summary="System-Benachrichtigungen auflisten",
    description="Gibt System-Benachrichtigungen mit erweiterten Filtern zurueck."
)
async def list_system_notifications(
    limit: int = Query(50, ge=1, le=100, description="Anzahl Benachrichtigungen"),
    offset: int = Query(0, ge=0, description="Offset fuer Pagination"),
    unread_only: bool = Query(False, description="Nur ungelesene Benachrichtigungen"),
    notification_type: Optional[str] = Query(None, description="Filter nach Typ"),
    priority: Optional[str] = Query(None, description="Filter nach Prioritaet (critical/warning/info)"),
    from_date: Optional[datetime] = Query(None, description="Datum Von"),
    to_date: Optional[datetime] = Query(None, description="Datum Bis"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> NotificationsListResponseExtended:
    """Liste System-Benachrichtigungen mit erweiterten Filtern."""
    # Base filter
    filters = [Notification.user_id == current_user.id]

    if unread_only:
        filters.append(Notification.read == False)

    if notification_type:
        filters.append(Notification.notification_type == notification_type)

    if priority:
        # Map priority to notification types
        if priority == NotificationPriority.CRITICAL:
            filters.append(Notification.notification_type.in_([
                NotificationType.ERROR.value,
                NotificationType.SYSTEM.value
            ]))
        elif priority == NotificationPriority.WARNING:
            filters.append(Notification.notification_type == NotificationType.WARNING.value)
        elif priority == NotificationPriority.INFO:
            filters.append(Notification.notification_type.in_([
                NotificationType.INFO.value,
                NotificationType.SUCCESS.value,
                NotificationType.OCR_COMPLETE.value,
                NotificationType.BATCH_COMPLETE.value,
                NotificationType.EXPORT_READY.value,
                NotificationType.SHARE_RECEIVED.value,
            ]))

    if from_date:
        filters.append(Notification.created_at >= from_date)

    if to_date:
        filters.append(Notification.created_at <= to_date)

    # Unread count
    unread_result = await db.execute(
        select(func.count(Notification.id)).where(
            and_(
                Notification.user_id == current_user.id,
                Notification.read == False,
            )
        )
    )
    unread_count = unread_result.scalar() or 0

    # Critical unread check
    critical_result = await db.execute(
        select(func.count(Notification.id)).where(
            and_(
                Notification.user_id == current_user.id,
                Notification.read == False,
                Notification.notification_type.in_([
                    NotificationType.ERROR.value,
                    NotificationType.SYSTEM.value
                ])
            )
        )
    )
    has_critical = (critical_result.scalar() or 0) > 0

    # Total count with filters
    count_result = await db.execute(
        select(func.count(Notification.id)).where(and_(*filters))
    )
    total = count_result.scalar() or 0

    # Query Notifications
    query = (
        select(Notification)
        .where(and_(*filters))
        .order_by(Notification.created_at.desc())
        .limit(limit)
        .offset(offset)
    )

    result = await db.execute(query)
    notifications_db = result.scalars().all()

    # Build responses
    notifications = [
        _build_system_notification_response(notif)
        for notif in notifications_db
    ]

    return NotificationsListResponseExtended(
        notifications=notifications,
        unread_count=unread_count,
        total=total,
        has_critical=has_critical,
    )


@router.get(
    "/system/{notification_id}",
    response_model=NotificationDetailResponse,
    summary="System-Benachrichtigung abrufen",
    description="Ruft eine einzelne System-Benachrichtigung ab."
)
async def get_system_notification(
    notification_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> NotificationDetailResponse:
    """Einzelne System-Benachrichtigung abrufen."""
    result = await db.execute(
        select(Notification).where(
            and_(
                Notification.id == notification_id,
                Notification.user_id == current_user.id,
            )
        )
    )
    notification = result.scalar_one_or_none()

    if not notification:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Benachrichtigung nicht gefunden"
        )

    return _build_system_notification_response(notification)


@router.delete(
    "/system/{notification_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    summary="System-Benachrichtigung loeschen",
    description="Loescht eine System-Benachrichtigung."
)
async def delete_system_notification(
    notification_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """System-Benachrichtigung loeschen."""
    result = await db.execute(
        select(Notification).where(
            and_(
                Notification.id == notification_id,
                Notification.user_id == current_user.id,
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
        "system_notification_deleted",
        notification_id=str(notification_id),
        user_id=str(current_user.id),
    )

    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.patch(
    "/system/{notification_id}/read",
    response_model=NotificationDetailResponse,
    summary="System-Benachrichtigung als gelesen markieren",
    description="Markiert eine System-Benachrichtigung als gelesen."
)
async def mark_system_notification_as_read(
    notification_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> NotificationDetailResponse:
    """System-Benachrichtigung als gelesen markieren."""
    result = await db.execute(
        select(Notification).where(
            and_(
                Notification.id == notification_id,
                Notification.user_id == current_user.id,
            )
        )
    )
    notification = result.scalar_one_or_none()

    if not notification:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Benachrichtigung nicht gefunden"
        )

    notification.read = True
    notification.read_at = utc_now()
    await db.commit()
    await db.refresh(notification)

    logger.info(
        "system_notification_marked_read",
        notification_id=str(notification_id),
        user_id=str(current_user.id),
    )

    return _build_system_notification_response(notification)


@router.post(
    "/system/mark-all-read",
    summary="Alle System-Benachrichtigungen als gelesen markieren",
    description="Markiert alle System-Benachrichtigungen als gelesen."
)
async def mark_all_system_notifications_read(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Alle System-Benachrichtigungen als gelesen markieren."""
    now = utc_now()

    result = await db.execute(
        update(Notification)
        .where(
            and_(
                Notification.user_id == current_user.id,
                Notification.read == False,
            )
        )
        .values(read=True, read_at=now)
    )
    await db.commit()

    updated_count = result.rowcount

    logger.info(
        "system_notifications_all_marked_read",
        user_id=str(current_user.id),
        count=updated_count,
    )

    return {
        "message": "Alle Benachrichtigungen als gelesen markiert",
        "success": True,
        "count": updated_count
    }


@router.post(
    "/system/bulk-dismiss",
    status_code=status.HTTP_200_OK,
    summary="Mehrere System-Benachrichtigungen loeschen",
    description="Loescht mehrere System-Benachrichtigungen auf einmal."
)
async def bulk_dismiss_system_notifications(
    request: BulkDismissRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Mehrere System-Benachrichtigungen loeschen."""
    # Convert to UUIDs
    notification_uuids = [UUID(nid) for nid in request.notification_ids]

    result = await db.execute(
        sql_delete(Notification).where(
            and_(
                Notification.id.in_(notification_uuids),
                Notification.user_id == current_user.id,
            )
        )
    )
    await db.commit()

    deleted_count = result.rowcount

    logger.info(
        "system_notifications_bulk_dismissed",
        user_id=str(current_user.id),
        count=deleted_count,
    )

    return {
        "message": f"{deleted_count} Benachrichtigungen geloescht",
        "success": True,
        "count": deleted_count
    }


@router.get(
    "/unread-count",
    summary="Anzahl ungelesener Benachrichtigungen",
    description="Gibt die Anzahl ungelesener System- und User-Benachrichtigungen zurueck."
)
async def get_unread_count(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Anzahl ungelesener Benachrichtigungen (System + User)."""
    # System notifications
    system_result = await db.execute(
        select(func.count(Notification.id)).where(
            and_(
                Notification.user_id == current_user.id,
                Notification.read == False,
            )
        )
    )
    system_count = system_result.scalar() or 0

    # User notifications
    user_result = await db.execute(
        select(func.count(UserNotification.id)).where(
            and_(
                UserNotification.user_id == current_user.id,
                UserNotification.is_read == False,
            )
        )
    )
    user_count = user_result.scalar() or 0

    return {
        "unreadCount": system_count + user_count,
        "systemCount": system_count,
        "userCount": user_count
    }


# =============================================================================
# Notification Settings Endpoints
# =============================================================================


@router.get(
    "/settings",
    response_model=NotificationSettingsResponse,
    summary="Benachrichtigungs-Einstellungen abrufen",
    description="Ruft die Benachrichtigungs-Einstellungen des Benutzers ab."
)
async def get_notification_settings(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> NotificationSettingsResponse:
    """Benachrichtigungs-Einstellungen abrufen."""
    # Query all preferences
    result = await db.execute(
        select(NotificationPreference).where(
            NotificationPreference.user_id == current_user.id
        )
    )
    preferences_list = result.scalars().all()

    # Build preferences dict
    preferences = {}
    for pref in preferences_list:
        preferences[pref.notification_type] = {
            "enabled_channels": pref.enabled_channels or {
                "in_app": True,
                "email": True,
                "websocket": True,
                "slack": False,
                "sms": False
            },
            "digest_frequency": pref.digest_frequency,
        }

    return NotificationSettingsResponse(
        user_id=str(current_user.id),
        preferences=preferences,
        digest_frequency="immediate",  # Default
        quiet_hours_enabled=False,
        quiet_hours_start=None,
        quiet_hours_end=None,
    )


@router.patch(
    "/settings",
    response_model=NotificationSettingsResponse,
    summary="Benachrichtigungs-Einstellungen aktualisieren",
    description="Aktualisiert die Benachrichtigungs-Einstellungen fuer einen Typ."
)
async def update_notification_settings(
    settings: NotificationSettingsUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> NotificationSettingsResponse:
    """Benachrichtigungs-Einstellungen aktualisieren."""
    # Check if preference exists
    result = await db.execute(
        select(NotificationPreference).where(
            and_(
                NotificationPreference.user_id == current_user.id,
                NotificationPreference.notification_type == settings.notification_type,
            )
        )
    )
    preference = result.scalar_one_or_none()

    if preference:
        # Update existing
        preference.enabled_channels = settings.enabled_channels
        preference.digest_frequency = settings.digest_frequency
    else:
        # Create new
        preference = NotificationPreference(
            user_id=current_user.id,
            notification_type=settings.notification_type,
            enabled_channels=settings.enabled_channels,
            digest_frequency=settings.digest_frequency,
        )
        db.add(preference)

    await db.commit()

    logger.info(
        "notification_settings_updated",
        user_id=str(current_user.id),
        notification_type=settings.notification_type,
    )

    # Return updated settings
    return await get_notification_settings(current_user, db)


# =============================================================================
# User Notifications Endpoints (Legacy - UserNotification Model)
# =============================================================================


@router.get(
    "/",
    response_model=NotificationsListResponse,
    summary="User-Benachrichtigungen auflisten",
    description="Gibt User-zu-User Benachrichtigungen zurueck."
)
async def list_notifications(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    unread_only: bool = Query(False, description="Nur ungelesene Benachrichtigungen"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> NotificationsListResponse:
    """Liste aller User-Benachrichtigungen."""
    # Base filter
    base_filter = UserNotification.user_id == current_user.id
    if unread_only:
        base_filter = and_(base_filter, UserNotification.is_read == False)

    # Unread count
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

    # Build responses
    notifications = [
        _build_notification_response(notif, notif.from_user, notif.document)
        for notif in notifications_db
    ]

    return NotificationsListResponse(
        notifications=notifications,
        unreadCount=unread_count,
        total=total,
    )


@router.patch(
    "/{notification_id}/read",
    response_model=NotificationResponse,
    summary="User-Benachrichtigung als gelesen markieren",
    description="Markiert eine User-Benachrichtigung als gelesen."
)
async def mark_as_read(
    notification_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> NotificationResponse:
    """User-Benachrichtigung als gelesen markieren."""
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
    notification.read_at = utc_now()
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
    summary="Alle User-Benachrichtigungen als gelesen markieren",
    description="Markiert alle User-Benachrichtigungen als gelesen."
)
async def mark_all_as_read(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Alle User-Benachrichtigungen als gelesen markieren."""
    now = utc_now()

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
    response_class=Response,
    summary="User-Benachrichtigung loeschen",
    description="Loescht eine User-Benachrichtigung."
)
async def delete_notification(
    notification_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """User-Benachrichtigung loeschen."""
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

    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete(
    "/",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    summary="Alle User-Benachrichtigungen loeschen",
    description="Loescht alle User-Benachrichtigungen des Benutzers."
)
async def delete_all_notifications(
    read_only: bool = Query(False, description="Nur gelesene Benachrichtigungen loeschen"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Alle User-Benachrichtigungen loeschen."""
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

    return Response(status_code=status.HTTP_204_NO_CONTENT)


# =============================================================================
# WebSocket Endpoint fuer Real-time Benachrichtigungen
# =============================================================================


from fastapi import WebSocket, WebSocketDisconnect
from app.core.security import extract_user_id_from_token
from app.services.notification_service import get_notification_ws_manager
from app.core.safe_errors import safe_error_log, safe_error_detail


@router.websocket("/ws")
async def notification_websocket(
    websocket: WebSocket,
    token: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
) -> None:
    """
    WebSocket-Endpoint fuer Real-time Benachrichtigungen.

    WICHTIG: Auth VOR accept() - Token muss als Query-Parameter uebergeben werden!

    Verbindungsaufbau:
    1. Client verbindet sich zu /api/v1/notifications/ws?token=jwt_token
    2. Server validiert Token VOR accept() (Security Best Practice)
    3. Nach erfolgreicher Auth werden Benachrichtigungen in Echtzeit gesendet

    Alternativ (Legacy, wird unterstuetzt):
    1. Client verbindet sich zu /api/v1/notifications/ws
    2. Client sendet {type: "auth", token: "jwt_token"} zur Authentifizierung
    3. Nach erfolgreicher Auth werden Benachrichtigungen in Echtzeit gesendet

    Nachrichtenformat (Server -> Client):
    {
        "type": "notification",
        "notification_type": "processing_completed",
        "title": "Dokument verarbeitet",
        "message": "Dokument X wurde erfolgreich verarbeitet",
        "priority": "normal",
        "timestamp": "2026-01-02T06:00:00Z"
    }
    """
    ws_manager = get_notification_ws_manager()
    user_id: Optional[str] = None

    try:
        # =========================================================================
        # SECURITY FIX: Auth VOR accept() wenn Token als Query-Parameter vorhanden
        # =========================================================================
        if token:
            try:
                user_id = await extract_user_id_from_token(token)

                # Verify user exists
                user_result = await db.execute(
                    select(User).where(User.id == UUID(user_id))
                )
                user = user_result.scalar_one_or_none()
                if not user or not user.is_active:
                    logger.warning("notification_ws_auth_failed", reason="user_not_found_or_inactive")
                    await websocket.close(code=4001)
                    return

            except Exception as e:
                logger.warning("notification_ws_auth_failed", **safe_error_log(e))
                await websocket.close(code=4001)
                return

            # Auth erfolgreich - jetzt accept()
            await websocket.accept()
            logger.info("notification_ws_connected", user_id=user_id, auth_method="query_token")

            # Register connection and keep alive for query-token auth
            async with ws_manager._lock:
                if user_id not in ws_manager._connections:
                    ws_manager._connections[user_id] = []
                ws_manager._connections[user_id].append(websocket)

            # Send welcome message
            await websocket.send_json({
                "type": "connected",
                "message": "Verbindung erfolgreich hergestellt",
                "user_id": user_id,
            })

            # Keep connection alive and handle incoming messages
            while True:
                try:
                    message = await websocket.receive_json()
                    if message.get("type") == "ping":
                        await websocket.send_json({"type": "pong"})
                except WebSocketDisconnect:
                    break
                except Exception as e:
                    logger.warning("notification_ws_message_error", user_id=user_id, **safe_error_log(e))
                    break

        else:
            # =========================================================================
            # LEGACY: Accept first, then auth via message (fuer Rueckwaertskompatibilitaet)
            # =========================================================================
            try:
                await websocket.accept()

                # Wait for auth message
                try:
                    auth_message = await websocket.receive_json()

                    if auth_message.get("type") != "auth" or not auth_message.get("token"):
                        await websocket.send_json({
                            "type": "error",
                            "message": "Authentifizierung erforderlich. Senden Sie {type: 'auth', token: 'jwt_token'} oder nutzen Sie ?token=... im Query-Parameter",
                        })
                        await websocket.close(code=4001)
                        return

                    # Validate token
                    msg_token = auth_message.get("token")
                    try:
                        user_id = await extract_user_id_from_token(msg_token)

                        # Verify user exists
                        user_result = await db.execute(
                            select(User).where(User.id == UUID(user_id))
                        )
                        user = user_result.scalar_one_or_none()
                        if not user or not user.is_active:
                            raise Exception("Benutzer nicht gefunden oder deaktiviert")

                        logger.info("notification_ws_connected", user_id=user_id, auth_method="message")

                    except Exception as e:
                        await websocket.send_json({
                            "type": "error",
                            "message": safe_error_detail(e, "Authentifizierung"),
                        })
                        await websocket.close(code=4001)
                        return

                except Exception as e:
                    logger.warning("notification_ws_auth_failed", **safe_error_log(e))
                    await websocket.close(code=4001)
                    return

            except Exception as e:
                logger.warning("notification_ws_accept_failed", **safe_error_log(e))
                return

            # Register connection (without calling accept again)
            async with ws_manager._lock:
                if user_id not in ws_manager._connections:
                    ws_manager._connections[user_id] = []
                ws_manager._connections[user_id].append(websocket)

            logger.info(
                "notification_ws_authenticated",
                user_id=user_id,
            )

            # Send welcome message
            await websocket.send_json({
                "type": "connected",
                "message": "Verbindung erfolgreich hergestellt",
                "user_id": user_id,
            })

            # Keep connection alive and handle incoming messages
            while True:
                try:
                    message = await websocket.receive_json()

                    # Handle ping/pong for keepalive
                    if message.get("type") == "ping":
                        await websocket.send_json({"type": "pong"})

                except WebSocketDisconnect:
                    break
                except Exception as e:
                    logger.warning(
                        "notification_ws_message_error",
                        user_id=user_id,
                        **safe_error_log(e),
                    )
                    break

    finally:
        # Clean up connection
        if user_id:
            await ws_manager.disconnect(websocket, user_id)
            logger.info(
                "notification_ws_cleanup",
                user_id=user_id,
            )
