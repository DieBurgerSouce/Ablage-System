"""
Slack Integration API Endpoints.

Ermöglicht:
- Slack-Kanal-Konfiguration (CRUD)
- Verbindungstest
- Nachrichten-Verlauf einsehen
- User-Mapping verwalten
- Test-Nachrichten senden

Feinpoliert und durchdacht - Enterprise Slack-Integration.
"""

import structlog
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, update, delete
from pydantic import BaseModel, Field, field_validator
import re

from app.core.rate_limiting import limiter, get_user_identifier
from app.db.models import (
    User,
    SlackChannel,
    SlackMessageLog,
    SlackUserMapping,
    SlackChannelType,
    SlackMessageStatus,
)
from app.api.dependencies import get_current_user, get_db, require_admin
from app.core.safe_errors import safe_error_log
from app.services.slack_service import (

    get_slack_service,
    SlackService,
    SlackNotificationType,
    SlackMessagePriority,
)

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/slack", tags=["slack"])


# =============================================================================
# SCHEMAS
# =============================================================================


class SlackChannelCreate(BaseModel):
    """Schema für Kanal-Erstellung."""
    channel_id: str = Field(..., min_length=1, max_length=50, description="Slack Channel ID")
    channel_name: str = Field(..., min_length=1, max_length=100, description="Kanal-Name ohne #")
    channel_type: str = Field(default="public", description="public, private, dm")
    company_id: Optional[UUID] = Field(default=None, description="Firmen-ID für Multi-Tenant")
    notification_types: list[str] = Field(default_factory=list, description="Notification-Typen")
    min_priority: str = Field(default="normal", description="Mindest-Prioritaet")
    is_default: bool = Field(default=False, description="Standard-Kanal")
    include_context: bool = Field(default=True, description="Kontext einschließen")
    mention_users: list[str] = Field(default_factory=list, description="Slack User-IDs")
    custom_icon: Optional[str] = Field(default=None, description="Custom Emoji")

    @field_validator("channel_id")
    @classmethod
    def validate_channel_id(cls, v: str) -> str:
        """Validiert Slack Channel ID Format."""
        if not re.match(r"^[A-Z0-9]{9,11}$", v):
            raise ValueError("Ungültige Slack Channel ID (Format: C01234567)")
        return v

    @field_validator("channel_type")
    @classmethod
    def validate_channel_type(cls, v: str) -> str:
        """Validiert Kanal-Typ."""
        valid = ["public", "private", "dm"]
        if v not in valid:
            raise ValueError(f"Kanal-Typ muss einer von {valid} sein")
        return v

    @field_validator("min_priority")
    @classmethod
    def validate_priority(cls, v: str) -> str:
        """Validiert Prioritaet."""
        valid = ["low", "normal", "high", "urgent"]
        if v not in valid:
            raise ValueError(f"Prioritaet muss eine von {valid} sein")
        return v


class SlackChannelUpdate(BaseModel):
    """Schema für Kanal-Update."""
    channel_name: Optional[str] = Field(default=None, max_length=100)
    notification_types: Optional[list[str]] = None
    min_priority: Optional[str] = None
    is_default: Optional[bool] = None
    is_active: Optional[bool] = None
    include_context: Optional[bool] = None
    mention_users: Optional[list[str]] = None
    custom_icon: Optional[str] = None

    @field_validator("min_priority")
    @classmethod
    def validate_priority(cls, v: Optional[str]) -> Optional[str]:
        """Validiert Prioritaet."""
        if v is None:
            return v
        valid = ["low", "normal", "high", "urgent"]
        if v not in valid:
            raise ValueError(f"Prioritaet muss eine von {valid} sein")
        return v


class SlackChannelResponse(BaseModel):
    """Schema für Kanal-Response."""
    id: UUID
    channel_id: str
    channel_name: str
    channel_type: str
    company_id: Optional[UUID]
    notification_types: list[str]
    min_priority: str
    is_default: bool
    is_active: bool
    include_context: bool
    mention_users: list[str]
    custom_icon: Optional[str]
    message_count: int
    last_message_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class SlackChannelListResponse(BaseModel):
    """Liste von Slack-Kanaelen."""
    items: list[SlackChannelResponse]
    total: int


class SlackMessageLogResponse(BaseModel):
    """Schema für Nachrichten-Log Response."""
    id: UUID
    slack_channel_id: str
    message_ts: Optional[str]
    notification_type: str
    title: str
    message_preview: Optional[str]
    priority: str
    status: str
    error_message: Optional[str]
    retry_count: int
    reference_type: Optional[str]
    reference_id: Optional[UUID]
    created_at: datetime
    sent_at: Optional[datetime]

    model_config = {"from_attributes": True}


class SlackMessageListResponse(BaseModel):
    """Liste von Slack-Nachrichten."""
    items: list[SlackMessageLogResponse]
    total: int


class SlackUserMappingCreate(BaseModel):
    """Schema für User-Mapping Erstellung."""
    slack_user_id: str = Field(..., min_length=1, max_length=50)
    slack_username: Optional[str] = Field(default=None, max_length=100)
    dm_enabled: bool = Field(default=False)
    dm_notification_types: list[str] = Field(default_factory=list)
    mention_on_approval: bool = Field(default=True)
    quiet_hours_start: Optional[str] = Field(default=None, description="HH:MM")
    quiet_hours_end: Optional[str] = Field(default=None, description="HH:MM")

    @field_validator("slack_user_id")
    @classmethod
    def validate_slack_user_id(cls, v: str) -> str:
        """Validiert Slack User ID Format."""
        if not re.match(r"^[A-Z0-9]{9,11}$", v):
            raise ValueError("Ungültige Slack User ID (Format: U01234567)")
        return v

    @field_validator("quiet_hours_start", "quiet_hours_end")
    @classmethod
    def validate_time(cls, v: Optional[str]) -> Optional[str]:
        """Validiert Zeit-Format."""
        if v is None:
            return v
        if not re.match(r"^([01]\d|2[0-3]):[0-5]\d$", v):
            raise ValueError("Zeit muss im Format HH:MM sein")
        return v


class SlackUserMappingResponse(BaseModel):
    """Schema für User-Mapping Response."""
    id: UUID
    user_id: UUID
    slack_user_id: str
    slack_username: Optional[str]
    dm_enabled: bool
    dm_notification_types: list[str]
    mention_on_approval: bool
    quiet_hours_start: Optional[str]
    quiet_hours_end: Optional[str]
    is_verified: bool
    verified_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class SlackTestMessageRequest(BaseModel):
    """Schema für Test-Nachricht."""
    channel_id: Optional[UUID] = Field(default=None, description="Kanal-ID (optional)")
    message: str = Field(default="Dies ist eine Test-Nachricht vom Ablage-System.")
    notification_type: str = Field(default="system_alert")
    priority: str = Field(default="normal")


class SlackTestMessageResponse(BaseModel):
    """Schema für Test-Nachricht Response."""
    success: bool
    message_ts: Optional[str] = None
    error: Optional[str] = None


class SlackConnectionStatus(BaseModel):
    """Schema für Verbindungs-Status."""
    enabled: bool
    webhook_configured: bool
    bot_token_configured: bool
    default_channel: str
    webhook_test: Optional[str] = None
    bot_test: Optional[dict] = None


class SlackStatistics(BaseModel):
    """Schema für Slack-Statistiken."""
    total_channels: int
    active_channels: int
    total_messages_sent: int
    messages_last_24h: int
    messages_last_7d: int
    failed_messages: int
    user_mappings: int


# =============================================================================
# ENDPOINTS: Connection & Status
# =============================================================================


@router.get(
    "/status",
    response_model=SlackConnectionStatus,
    summary="Verbindungs-Status prüfen",
    description="Prüft den Status der Slack-Integration.",
)
async def get_slack_status(
    current_user: User = Depends(require_admin),
) -> SlackConnectionStatus:
    """Gibt den aktuellen Slack-Verbindungsstatus zurück."""
    service = get_slack_service()
    status_data = await service.test_connection()
    return SlackConnectionStatus(**status_data)


@router.get(
    "/statistics",
    response_model=SlackStatistics,
    summary="Slack-Statistiken abrufen",
    description="Liefert Statistiken zur Slack-Integration.",
)
async def get_slack_statistics(
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> SlackStatistics:
    """Berechnet und liefert Slack-Statistiken."""
    from datetime import timedelta

    now = datetime.now(timezone.utc)
    day_ago = now - timedelta(days=1)
    week_ago = now - timedelta(days=7)

    # Kanal-Statistiken
    total_channels = await db.scalar(select(func.count(SlackChannel.id)))
    active_channels = await db.scalar(
        select(func.count(SlackChannel.id)).where(SlackChannel.is_active == True)
    )

    # Nachrichten-Statistiken
    total_messages = await db.scalar(select(func.count(SlackMessageLog.id)))
    messages_24h = await db.scalar(
        select(func.count(SlackMessageLog.id)).where(
            SlackMessageLog.created_at >= day_ago,
            SlackMessageLog.status == SlackMessageStatus.SENT.value,
        )
    )
    messages_7d = await db.scalar(
        select(func.count(SlackMessageLog.id)).where(
            SlackMessageLog.created_at >= week_ago,
            SlackMessageLog.status == SlackMessageStatus.SENT.value,
        )
    )
    failed_messages = await db.scalar(
        select(func.count(SlackMessageLog.id)).where(
            SlackMessageLog.status == SlackMessageStatus.FAILED.value
        )
    )

    # User-Mappings
    user_mappings = await db.scalar(select(func.count(SlackUserMapping.id)))

    return SlackStatistics(
        total_channels=total_channels or 0,
        active_channels=active_channels or 0,
        total_messages_sent=total_messages or 0,
        messages_last_24h=messages_24h or 0,
        messages_last_7d=messages_7d or 0,
        failed_messages=failed_messages or 0,
        user_mappings=user_mappings or 0,
    )


# =============================================================================
# ENDPOINTS: Channels
# =============================================================================


@limiter.limit("30/minute", key_func=get_user_identifier)
@router.post(
    "/channels",
    response_model=SlackChannelResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Slack-Kanal hinzufuegen",
    description="Fuegt einen neuen Slack-Kanal zur Konfiguration hinzu.",
)
async def create_slack_channel(
    request: Request,
    channel_data: SlackChannelCreate,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> SlackChannelResponse:
    """Erstellt eine neue Slack-Kanal-Konfiguration."""
    # Prüfen ob Kanal bereits existiert
    existing = await db.execute(
        select(SlackChannel).where(
            SlackChannel.channel_id == channel_data.channel_id,
            SlackChannel.company_id == channel_data.company_id,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Kanal existiert bereits für diese Firma",
        )

    channel = SlackChannel(
        channel_id=channel_data.channel_id,
        channel_name=channel_data.channel_name,
        channel_type=channel_data.channel_type,
        company_id=channel_data.company_id,
        notification_types=channel_data.notification_types,
        min_priority=channel_data.min_priority,
        is_default=channel_data.is_default,
        include_context=channel_data.include_context,
        mention_users=channel_data.mention_users,
        custom_icon=channel_data.custom_icon,
        created_by_id=current_user.id,
    )

    db.add(channel)
    await db.commit()
    await db.refresh(channel)

    logger.info(
        "slack_channel_created",
        channel_id=str(channel.id),
        slack_channel_id=channel.channel_id,
        user_id=str(current_user.id),
    )

    return SlackChannelResponse.model_validate(channel)


@router.get(
    "/channels",
    response_model=SlackChannelListResponse,
    summary="Slack-Kanaele auflisten",
    description="Listet alle konfigurierten Slack-Kanaele auf.",
)
async def list_slack_channels(
    company_id: Optional[UUID] = Query(default=None, description="Filter nach Firma"),
    active_only: bool = Query(default=False, description="Nur aktive Kanaele"),
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> SlackChannelListResponse:
    """Listet alle Slack-Kanaele auf."""
    query = select(SlackChannel).order_by(SlackChannel.channel_name)

    if company_id:
        query = query.where(SlackChannel.company_id == company_id)

    if active_only:
        query = query.where(SlackChannel.is_active == True)

    result = await db.execute(query)
    channels = result.scalars().all()

    return SlackChannelListResponse(
        items=[SlackChannelResponse.model_validate(c) for c in channels],
        total=len(channels),
    )


@router.get(
    "/channels/{channel_id}",
    response_model=SlackChannelResponse,
    summary="Slack-Kanal abrufen",
    description="Ruft Details eines Slack-Kanals ab.",
)
async def get_slack_channel(
    channel_id: UUID,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> SlackChannelResponse:
    """Ruft einen einzelnen Slack-Kanal ab."""
    result = await db.execute(
        select(SlackChannel).where(SlackChannel.id == channel_id)
    )
    channel = result.scalar_one_or_none()

    if not channel:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Kanal nicht gefunden",
        )

    return SlackChannelResponse.model_validate(channel)


@limiter.limit("30/minute", key_func=get_user_identifier)
@router.patch(
    "/channels/{channel_id}",
    response_model=SlackChannelResponse,
    summary="Slack-Kanal aktualisieren",
    description="Aktualisiert die Konfiguration eines Slack-Kanals.",
)
async def update_slack_channel(
    request: Request,
    channel_id: UUID,
    update_data: SlackChannelUpdate,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> SlackChannelResponse:
    """Aktualisiert einen Slack-Kanal."""
    result = await db.execute(
        select(SlackChannel).where(SlackChannel.id == channel_id)
    )
    channel = result.scalar_one_or_none()

    if not channel:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Kanal nicht gefunden",
        )

    # Update-Daten anwenden
    update_dict = update_data.model_dump(exclude_unset=True)
    for key, value in update_dict.items():
        setattr(channel, key, value)

    await db.commit()
    await db.refresh(channel)

    logger.info(
        "slack_channel_updated",
        channel_id=str(channel.id),
        user_id=str(current_user.id),
    )

    return SlackChannelResponse.model_validate(channel)


@router.delete(
    "/channels/{channel_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Slack-Kanal entfernen",
    description="Entfernt einen Slack-Kanal aus der Konfiguration.",
)
async def delete_slack_channel(
    channel_id: UUID,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Löscht einen Slack-Kanal."""
    result = await db.execute(
        select(SlackChannel).where(SlackChannel.id == channel_id)
    )
    channel = result.scalar_one_or_none()

    if not channel:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Kanal nicht gefunden",
        )

    await db.delete(channel)
    await db.commit()

    logger.info(
        "slack_channel_deleted",
        channel_id=str(channel_id),
        user_id=str(current_user.id),
    )


# =============================================================================
# ENDPOINTS: Messages
# =============================================================================


@router.get(
    "/messages",
    response_model=SlackMessageListResponse,
    summary="Nachrichten-Verlauf",
    description="Zeigt den Verlauf gesendeter Slack-Nachrichten.",
)
async def list_slack_messages(
    channel_id: Optional[UUID] = Query(default=None, description="Filter nach Kanal"),
    notification_type: Optional[str] = Query(default=None, description="Filter nach Typ"),
    status_filter: Optional[str] = Query(default=None, alias="status", description="Filter nach Status"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> SlackMessageListResponse:
    """Listet Slack-Nachrichten-Logs auf."""
    query = select(SlackMessageLog).order_by(SlackMessageLog.created_at.desc())

    if channel_id:
        query = query.where(SlackMessageLog.channel_id == channel_id)

    if notification_type:
        query = query.where(SlackMessageLog.notification_type == notification_type)

    if status_filter:
        query = query.where(SlackMessageLog.status == status_filter)

    # Total zaehlen
    count_query = select(func.count()).select_from(query.subquery())
    total = await db.scalar(count_query)

    # Pagination
    query = query.offset(offset).limit(limit)

    result = await db.execute(query)
    messages = result.scalars().all()

    return SlackMessageListResponse(
        items=[SlackMessageLogResponse.model_validate(m) for m in messages],
        total=total or 0,
    )


@limiter.limit("10/minute", key_func=get_user_identifier)
@router.post(
    "/test",
    response_model=SlackTestMessageResponse,
    summary="Test-Nachricht senden",
    description="Sendet eine Test-Nachricht an Slack.",
)
async def send_test_message(
    request: Request,
    test_data: SlackTestMessageRequest,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> SlackTestMessageResponse:
    """Sendet eine Test-Nachricht an Slack."""
    service = get_slack_service()

    if not service.is_enabled:
        return SlackTestMessageResponse(
            success=False,
            error="Slack-Integration ist nicht aktiviert",
        )

    # Kanal ermitteln
    channel_name = None
    if test_data.channel_id:
        result = await db.execute(
            select(SlackChannel).where(SlackChannel.id == test_data.channel_id)
        )
        channel = result.scalar_one_or_none()
        if channel:
            channel_name = channel.channel_name

    try:
        success = await service.send_notification(
            notification_type=test_data.notification_type,
            title="Test-Benachrichtigung",
            message=test_data.message,
            context={
                "gesendet_von": current_user.username,
                "zeitpunkt": datetime.now(timezone.utc).isoformat(),
            },
            priority=SlackMessagePriority(test_data.priority),
            channel=channel_name,
        )

        if success:
            logger.info(
                "slack_test_message_sent",
                user_id=str(current_user.id),
                channel=channel_name,
            )
            return SlackTestMessageResponse(success=True)
        else:
            return SlackTestMessageResponse(
                success=False,
                error="Nachricht konnte nicht gesendet werden",
            )

    except Exception as e:
        logger.error(
            "slack_test_message_failed",
            **safe_error_log(e),
            user_id=str(current_user.id),
        )
        return SlackTestMessageResponse(
            success=False,
            **safe_error_log(e),
        )


# =============================================================================
# ENDPOINTS: User Mappings
# =============================================================================


@router.get(
    "/user-mapping",
    response_model=Optional[SlackUserMappingResponse],
    summary="Eigenes User-Mapping abrufen",
    description="Ruft das Slack-Mapping des aktuellen Benutzers ab.",
)
async def get_my_slack_mapping(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Optional[SlackUserMappingResponse]:
    """Ruft das Slack-Mapping des aktuellen Benutzers ab."""
    result = await db.execute(
        select(SlackUserMapping).where(SlackUserMapping.user_id == current_user.id)
    )
    mapping = result.scalar_one_or_none()

    if not mapping:
        return None

    return SlackUserMappingResponse.model_validate(mapping)


@limiter.limit("10/minute", key_func=get_user_identifier)
@router.post(
    "/user-mapping",
    response_model=SlackUserMappingResponse,
    status_code=status.HTTP_201_CREATED,
    summary="User-Mapping erstellen",
    description="Verbindet den aktuellen Benutzer mit einem Slack-Account.",
)
async def create_my_slack_mapping(
    request: Request,
    mapping_data: SlackUserMappingCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SlackUserMappingResponse:
    """Erstellt ein Slack-Mapping für den aktuellen Benutzer."""
    # Prüfen ob bereits Mapping existiert
    existing = await db.execute(
        select(SlackUserMapping).where(SlackUserMapping.user_id == current_user.id)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Slack-Verknüpfung existiert bereits",
        )

    # Prüfen ob Slack-User bereits verwendet
    existing_slack = await db.execute(
        select(SlackUserMapping).where(
            SlackUserMapping.slack_user_id == mapping_data.slack_user_id
        )
    )
    if existing_slack.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Diese Slack-ID ist bereits mit einem anderen Benutzer verknüpft",
        )

    mapping = SlackUserMapping(
        user_id=current_user.id,
        slack_user_id=mapping_data.slack_user_id,
        slack_username=mapping_data.slack_username,
        dm_enabled=mapping_data.dm_enabled,
        dm_notification_types=mapping_data.dm_notification_types,
        mention_on_approval=mapping_data.mention_on_approval,
        quiet_hours_start=mapping_data.quiet_hours_start,
        quiet_hours_end=mapping_data.quiet_hours_end,
    )

    db.add(mapping)
    await db.commit()
    await db.refresh(mapping)

    logger.info(
        "slack_user_mapping_created",
        user_id=str(current_user.id),
        slack_user_id=mapping.slack_user_id,
    )

    return SlackUserMappingResponse.model_validate(mapping)


@router.delete(
    "/user-mapping",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="User-Mapping entfernen",
    description="Entfernt die Slack-Verknüpfung des aktuellen Benutzers.",
)
async def delete_my_slack_mapping(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Löscht das Slack-Mapping des aktuellen Benutzers."""
    result = await db.execute(
        select(SlackUserMapping).where(SlackUserMapping.user_id == current_user.id)
    )
    mapping = result.scalar_one_or_none()

    if not mapping:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Keine Slack-Verknüpfung gefunden",
        )

    await db.delete(mapping)
    await db.commit()

    logger.info(
        "slack_user_mapping_deleted",
        user_id=str(current_user.id),
    )


# Admin-Endpoint für alle User-Mappings
@router.get(
    "/user-mappings",
    response_model=list[SlackUserMappingResponse],
    summary="Alle User-Mappings (Admin)",
    description="Listet alle Slack-User-Mappings auf (nur für Admins).",
)
async def list_all_user_mappings(
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> list[SlackUserMappingResponse]:
    """Listet alle Slack-User-Mappings auf."""
    result = await db.execute(
        select(SlackUserMapping).order_by(SlackUserMapping.created_at.desc())
    )
    mappings = result.scalars().all()

    return [SlackUserMappingResponse.model_validate(m) for m in mappings]


# =============================================================================
# ENDPOINTS: Notification Types
# =============================================================================


@router.get(
    "/notification-types",
    response_model=list[dict],
    summary="Verfügbare Notification-Typen",
    description="Listet alle verfügbaren Slack-Notification-Typen auf.",
)
async def get_notification_types(
    current_user: User = Depends(get_current_user),
) -> list[dict]:
    """Gibt alle verfügbaren Notification-Typen zurück."""
    types = [
        {
            "type": "document_processed",
            "name": "Dokument verarbeitet",
            "description": "Wenn ein Dokument erfolgreich verarbeitet wurde",
            "icon": ":white_check_mark:",
        },
        {
            "type": "document_error",
            "name": "Dokumentfehler",
            "description": "Wenn bei der Dokumentverarbeitung ein Fehler auftritt",
            "icon": ":x:",
        },
        {
            "type": "approval_required",
            "name": "Freigabe erforderlich",
            "description": "Wenn eine Freigabe angefordert wird",
            "icon": ":hourglass_flowing_sand:",
        },
        {
            "type": "approval_completed",
            "name": "Freigabe erteilt",
            "description": "Wenn eine Freigabe erteilt oder abgelehnt wird",
            "icon": ":heavy_check_mark:",
        },
        {
            "type": "workflow_completed",
            "name": "Workflow abgeschlossen",
            "description": "Wenn ein Workflow-Durchlauf abgeschlossen ist",
            "icon": ":checkered_flag:",
        },
        {
            "type": "high_risk_entity",
            "name": "Hochrisiko-Partner",
            "description": "Wenn ein Geschäftspartner hohen Risikowert erreicht",
            "icon": ":warning:",
        },
        {
            "type": "dunning_escalation",
            "name": "Mahneskalation",
            "description": "Wenn eine Mahnstufe erhöht wird",
            "icon": ":warning:",
        },
        {
            "type": "report_generated",
            "name": "Bericht erstellt",
            "description": "Wenn ein geplanter Bericht generiert wurde",
            "icon": ":bar_chart:",
        },
        {
            "type": "system_alert",
            "name": "System-Warnung",
            "description": "Wichtige System-Benachrichtigungen",
            "icon": ":rotating_light:",
        },
    ]
    return types
