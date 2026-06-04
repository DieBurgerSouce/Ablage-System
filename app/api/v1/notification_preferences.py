"""Notification Preferences API.

Verwaltung von Benutzer-Benachrichtigungspraeferenzen.
"""


from typing import Dict, List
from uuid import UUID
from datetime import time

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.api.dependencies import get_current_active_user, get_db
from app.db.models import User, NotificationPreference, UserNotification
from app.core.safe_errors import safe_error_log
from app.core.rate_limiting import limiter, get_user_identifier

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/notification-preferences", tags=["notification-preferences"])


# =============================================================================
# Pydantic Schemas
# =============================================================================

class NotificationChannelStatus(BaseModel):
    """Status eines Benachrichtigungskanals."""
    channel: str = Field(..., description="Kanalname (in_app, email, push, slack)")
    available: bool = Field(..., description="Ob der Kanal verfügbar ist")
    configured: bool = Field(..., description="Ob der Kanal konfiguriert ist")
    description: str = Field(..., description="Beschreibung des Kanals")


class NotificationPreferenceUpdate(BaseModel):
    """Update für eine Benachrichtigungspraeferenz."""
    notification_type: str = Field(..., description="Typ der Benachrichtigung")
    enabled_channels: Dict[str, bool] = Field(
        default_factory=dict,
        description="Aktivierte Kanaele (in_app, email, websocket, slack, sms)"
    )
    digest_frequency: str = Field(
        default="immediate",
        description="Digest-Frequenz (immediate, daily, weekly, disabled)"
    )


class NotificationPreferenceResponse(BaseModel):
    """Antwort mit Benachrichtigungspraeferenz."""
    id: UUID
    user_id: UUID
    notification_type: str
    enabled_channels: Dict[str, bool]
    digest_frequency: str
    created_at: str
    updated_at: str

    model_config = ConfigDict(from_attributes=True)


class NotificationPreferencesUpdateRequest(BaseModel):
    """Batch-Update für Benachrichtigungspraeferenzen."""
    preferences: List[NotificationPreferenceUpdate] = Field(
        ...,
        description="Liste von Praeferenz-Updates"
    )


class PreferencesUpdateResponse(BaseModel):
    """Antwort nach Aktualisierung der Benachrichtigungspraeferenzen."""
    status: str
    updated: int
    created: int
    message: str


class TestNotificationResponse(BaseModel):
    """Antwort nach Senden einer Test-Benachrichtigung."""
    status: str
    channel: str
    notification_id: str
    message: str


class TestNotificationRequest(BaseModel):
    """Request für Test-Benachrichtigung."""
    channel: str = Field(
        default="in_app",
        description="Kanal für Test-Benachrichtigung"
    )


# =============================================================================
# API Endpoints
# =============================================================================

@router.get(
    "",
    response_model=List[NotificationPreferenceResponse],
    summary="Benachrichtigungspraeferenzen abrufen",
    description="Ruft alle Benachrichtigungspraeferenzen des aktuellen Benutzers ab"
)
@limiter.limit("60/minute", key_func=get_user_identifier)
async def get_notification_preferences(
    request: Request,  # Required for rate limiter
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
) -> List[NotificationPreferenceResponse]:
    """Ruft alle Benachrichtigungspraeferenzen des aktuellen Benutzers ab."""
    try:
        query = select(NotificationPreference).where(
            NotificationPreference.user_id == current_user.id
        ).order_by(NotificationPreference.notification_type)

        result = await db.execute(query)
        preferences = result.scalars().all()

        return [
            NotificationPreferenceResponse(
                id=pref.id,
                user_id=pref.user_id,
                notification_type=pref.notification_type,
                enabled_channels=pref.enabled_channels or {},
                digest_frequency=pref.digest_frequency or "immediate",
                created_at=pref.created_at.isoformat() if pref.created_at else "",
                updated_at=pref.updated_at.isoformat() if pref.updated_at else "",
            )
            for pref in preferences
        ]

    except Exception as e:
        logger.error(
            "get_notification_preferences_error",
            user_id=str(current_user.id),
            **safe_error_log(e)
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Fehler beim Abrufen der Benachrichtigungspraeferenzen"
        )


@router.put(
    "",
    response_model=PreferencesUpdateResponse,
    summary="Benachrichtigungspraeferenzen aktualisieren",
    description="Aktualisiert die Benachrichtigungspraeferenzen des aktuellen Benutzers"
)
@limiter.limit("20/minute", key_func=get_user_identifier)
async def update_notification_preferences(
    request: Request,  # Required for rate limiter
    body: NotificationPreferencesUpdateRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
) -> PreferencesUpdateResponse:
    """Aktualisiert die Benachrichtigungspraeferenzen des aktuellen Benutzers."""
    try:
        updated_count = 0
        created_count = 0

        for pref_update in body.preferences:
            # Prüfen ob Praeferenz bereits existiert
            query = select(NotificationPreference).where(
                NotificationPreference.user_id == current_user.id,
                NotificationPreference.notification_type == pref_update.notification_type
            )
            result = await db.execute(query)
            existing_pref = result.scalar_one_or_none()

            if existing_pref:
                # Update existierende Praeferenz
                if pref_update.enabled_channels:
                    existing_pref.enabled_channels = pref_update.enabled_channels
                existing_pref.digest_frequency = pref_update.digest_frequency
                updated_count += 1
            else:
                # Erstelle neue Praeferenz
                new_pref = NotificationPreference(
                    user_id=current_user.id,
                    notification_type=pref_update.notification_type,
                    enabled_channels=pref_update.enabled_channels or {
                        "in_app": True,
                        "email": True,
                        "websocket": True,
                        "slack": False,
                        "sms": False
                    },
                    digest_frequency=pref_update.digest_frequency
                )
                db.add(new_pref)
                created_count += 1

        await db.commit()

        logger.info(
            "notification_preferences_updated",
            user_id=str(current_user.id),
            updated_count=updated_count,
            created_count=created_count
        )

        return PreferencesUpdateResponse(
            status="success",
            updated=updated_count,
            created=created_count,
            message=f"{updated_count} Praeferenzen aktualisiert, {created_count} neu erstellt",
        )

    except Exception as e:
        await db.rollback()
        logger.error(
            "update_notification_preferences_error",
            user_id=str(current_user.id),
            **safe_error_log(e)
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Fehler beim Aktualisieren der Benachrichtigungspraeferenzen"
        )


@router.get(
    "/channels",
    response_model=List[NotificationChannelStatus],
    summary="Verfügbare Kanaele auflisten",
    description="Listet alle verfügbaren Benachrichtigungskanaele mit ihrem Status"
)
@limiter.limit("60/minute", key_func=get_user_identifier)
async def get_available_channels(
    request: Request,  # Required for rate limiter
    current_user: User = Depends(get_current_active_user),
) -> List[NotificationChannelStatus]:
    """Listet alle verfügbaren Benachrichtigungskanaele mit ihrem Status."""
    # Statische Liste der verfügbaren Kanaele
    channels = [
        NotificationChannelStatus(
            channel="in_app",
            available=True,
            configured=True,
            description="In-App Benachrichtigungen (immer verfügbar)"
        ),
        NotificationChannelStatus(
            channel="email",
            available=True,
            configured=bool(current_user.email),
            description="E-Mail Benachrichtigungen"
        ),
        NotificationChannelStatus(
            channel="websocket",
            available=True,
            configured=True,
            description="Echtzeit-Benachrichtigungen über WebSocket"
        ),
        NotificationChannelStatus(
            channel="push",
            available=True,
            configured=bool(getattr(current_user, "push_subscriptions", None)),
            description="Push-Benachrichtigungen (Browser/PWA)"
        ),
        NotificationChannelStatus(
            channel="slack",
            available=True,
            configured=True,
            description="Slack-Benachrichtigungen"
        ),
    ]

    return channels


@router.post(
    "/test",
    response_model=TestNotificationResponse,
    summary="Test-Benachrichtigung senden",
    description="Sendet eine Test-Benachrichtigung an den aktuellen Benutzer"
)
@limiter.limit("20/minute", key_func=get_user_identifier)
async def send_test_notification(
    request: Request,  # Required for rate limiter
    body: TestNotificationRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
) -> TestNotificationResponse:
    """Sendet eine Test-Benachrichtigung an den aktuellen Benutzer."""
    try:
        valid_channels = {"in_app", "email", "websocket", "push", "slack"}
        if body.channel not in valid_channels:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Kanal '{body.channel}' wird nicht unterstützt. "
                       f"Verfügbar: {', '.join(sorted(valid_channels))}"
            )

        notification_id_str = ""

        if body.channel == "push":
            # Push-Benachrichtigung via PushNotificationService
            from app.services.push_notification_service import PushNotificationService
            push_service = PushNotificationService(db)
            success, failed = await push_service.send_to_user(
                user_id=current_user.id,
                title="Test-Benachrichtigung",
                body="Dies ist eine Test-Push-Benachrichtigung vom Ablage-System.",
                tag="test-notification",
                data={"type": "test"},
            )
            await db.commit()
            notification_id_str = f"push-{success}-sent-{failed}-failed"

        elif body.channel == "slack":
            # Slack-Benachrichtigung via SlackService
            from app.services.slack_service import send_slack_notification
            slack_success = await send_slack_notification(
                notification_type="custom",
                title="Test-Benachrichtigung",
                message=f"Dies ist eine Test-Slack-Benachrichtigung von Benutzer {current_user.email or current_user.id}.",
                priority="normal",
            )
            notification_id_str = "slack-test" if slack_success else "slack-failed"

        else:
            # In-App / Email / WebSocket via NotificationService
            test_notification = UserNotification(
                user_id=current_user.id,
                notification_type="system.test",
                title="Test-Benachrichtigung",
                message=f"Dies ist eine Test-Benachrichtigung für den Kanal '{body.channel}'.",
                action_url=None,
                is_read=False,
            )
            db.add(test_notification)
            await db.commit()
            await db.refresh(test_notification)
            notification_id_str = str(test_notification.id)

        logger.info(
            "test_notification_sent",
            user_id=str(current_user.id),
            channel=body.channel,
            notification_id=notification_id_str,
        )

        return TestNotificationResponse(
            status="success",
            channel=body.channel,
            notification_id=notification_id_str,
            message="Test-Benachrichtigung erfolgreich gesendet",
        )

    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(
            "send_test_notification_error",
            user_id=str(current_user.id),
            channel=body.channel,
            **safe_error_log(e)
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Fehler beim Senden der Test-Benachrichtigung"
        )
