# -*- coding: utf-8 -*-
"""API Endpoints fuer Push Notifications.

Stellt Endpoints bereit fuer:
- Subscription Management (registrieren, entfernen, auflisten)
- Preference Management
- VAPID Public Key Abruf
- Notification Tracking
"""

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db, get_current_user
from app.db.models import User
from app.services.push_notification_service import PushNotificationService
from app.core.config import settings

router = APIRouter(prefix="/push", tags=["Push Notifications"])


# ==================================================
# Schemas
# ==================================================

class PushSubscriptionKeys(BaseModel):
    """Web Push Subscription Keys."""

    p256dh: str = Field(..., description="P-256 Public Key")
    auth: str = Field(..., description="Auth Secret")


class PushSubscriptionCreate(BaseModel):
    """Request fuer Subscription Registrierung."""

    endpoint: str = Field(..., description="Push Service Endpoint URL")
    keys: PushSubscriptionKeys = Field(..., description="Subscription Keys")
    expiration_time: Optional[int] = Field(None, description="Expiration Timestamp")
    device_name: Optional[str] = Field(None, max_length=255, description="Geraetename")
    device_type: Optional[str] = Field(None, pattern="^(mobile|tablet|desktop)$", description="Geraetetyp")
    browser: Optional[str] = Field(None, max_length=100, description="Browser Name")
    os: Optional[str] = Field(None, max_length=100, description="Betriebssystem")


class PushSubscriptionResponse(BaseModel):
    """Response fuer Subscription."""

    id: UUID
    endpoint: str
    device_name: Optional[str]
    device_type: Optional[str]
    browser: Optional[str]
    os: Optional[str]
    preferences: dict[str, bool]
    is_active: bool
    created_at: datetime
    last_used_at: Optional[datetime]


class PreferencesUpdate(BaseModel):
    """Request fuer Preference Update."""

    preferences: dict[str, bool] = Field(
        ...,
        description="Notification Preferences (z.B. {'documents': true, 'system': false})",
    )


class VAPIDPublicKeyResponse(BaseModel):
    """Response mit VAPID Public Key."""

    public_key: str = Field(..., description="VAPID Public Key fuer Subscription")


class SubscriptionStatsResponse(BaseModel):
    """Response mit Subscription Statistiken."""

    total: int
    active: int
    inactive: int
    by_device_type: dict[str, int]


class NotificationClickRequest(BaseModel):
    """Request fuer Notification Click Tracking."""

    tag: str = Field(..., description="Notification Tag")


# ==================================================
# VAPID Key Endpoint
# ==================================================

@router.get(
    "/vapid-public-key",
    response_model=VAPIDPublicKeyResponse,
    summary="VAPID Public Key abrufen",
    description="Gibt den VAPID Public Key zurueck, der fuer die Push Subscription benoetigt wird.",
)
async def get_vapid_public_key() -> VAPIDPublicKeyResponse:
    """Gibt den VAPID Public Key zurueck."""
    return VAPIDPublicKeyResponse(public_key=settings.VAPID_PUBLIC_KEY)


# ==================================================
# Subscription Endpoints
# ==================================================

@router.post(
    "/subscriptions",
    response_model=PushSubscriptionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Push Subscription registrieren",
    description="Registriert eine neue Push Subscription fuer den aktuellen Benutzer.",
)
async def register_subscription(
    data: PushSubscriptionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PushSubscriptionResponse:
    """Registriert eine neue Push Subscription."""
    service = PushNotificationService(db)

    subscription = await service.register_subscription(
        user_id=current_user.id,
        endpoint=data.endpoint,
        p256dh_key=data.keys.p256dh,
        auth_key=data.keys.auth,
        expiration_time=data.expiration_time,
        device_name=data.device_name,
        device_type=data.device_type,
        browser=data.browser,
        os=data.os,
    )

    await db.commit()

    return PushSubscriptionResponse(
        id=subscription.id,
        endpoint=subscription.endpoint,
        device_name=subscription.device_name,
        device_type=subscription.device_type,
        browser=subscription.browser,
        os=subscription.os,
        preferences=subscription.preferences,
        is_active=subscription.is_active,
        created_at=subscription.created_at,
        last_used_at=subscription.last_used_at,
    )


@router.delete(
    "/subscriptions",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    summary="Push Subscription entfernen",
    description="Entfernt eine Push Subscription anhand des Endpoints.",
)
async def unregister_subscription(
    endpoint: str = Query(..., description="Push Service Endpoint URL"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Response:
    """Entfernt eine Push Subscription."""
    service = PushNotificationService(db)

    success = await service.unregister_subscription(endpoint)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Subscription nicht gefunden",
        )

    await db.commit()

    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/subscriptions",
    response_model=list[PushSubscriptionResponse],
    summary="Eigene Subscriptions auflisten",
    description="Listet alle Push Subscriptions des aktuellen Benutzers auf.",
)
async def list_subscriptions(
    include_inactive: bool = Query(False, description="Auch inaktive Subscriptions anzeigen"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[PushSubscriptionResponse]:
    """Listet alle eigenen Push Subscriptions auf."""
    service = PushNotificationService(db)

    subscriptions = await service.get_user_subscriptions(
        user_id=current_user.id,
        active_only=not include_inactive,
    )

    return [
        PushSubscriptionResponse(
            id=sub.id,
            endpoint=sub.endpoint,
            device_name=sub.device_name,
            device_type=sub.device_type,
            browser=sub.browser,
            os=sub.os,
            preferences=sub.preferences,
            is_active=sub.is_active,
            created_at=sub.created_at,
            last_used_at=sub.last_used_at,
        )
        for sub in subscriptions
    ]


@router.patch(
    "/subscriptions/{subscription_id}/preferences",
    response_model=PushSubscriptionResponse,
    summary="Notification Preferences aktualisieren",
    description="Aktualisiert die Notification Preferences einer Subscription.",
)
async def update_subscription_preferences(
    subscription_id: UUID,
    data: PreferencesUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PushSubscriptionResponse:
    """Aktualisiert die Notification Preferences."""
    service = PushNotificationService(db)

    # SECURITY FIX: Ownership Check MUSS VOR der Modifikation erfolgen!
    # Vorher wurde update_preferences() vor dem Check aufgerufen, was
    # einem Angreifer erlaubte, fremde Subscriptions zu modifizieren.
    subscription = await service.get_subscription(subscription_id)

    if not subscription:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Subscription nicht gefunden",
        )

    # Verify ownership BEFORE any modification
    if subscription.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Keine Berechtigung fuer diese Subscription",
        )

    # Now safe to update
    subscription = await service.update_preferences(subscription_id, data.preferences)
    await db.commit()

    return PushSubscriptionResponse(
        id=subscription.id,
        endpoint=subscription.endpoint,
        device_name=subscription.device_name,
        device_type=subscription.device_type,
        browser=subscription.browser,
        os=subscription.os,
        preferences=subscription.preferences,
        is_active=subscription.is_active,
        created_at=subscription.created_at,
        last_used_at=subscription.last_used_at,
    )


# ==================================================
# Stats & Tracking Endpoints
# ==================================================

@router.get(
    "/stats",
    response_model=SubscriptionStatsResponse,
    summary="Subscription Statistiken",
    description="Gibt Statistiken ueber die eigenen Push Subscriptions zurueck.",
)
async def get_subscription_stats(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SubscriptionStatsResponse:
    """Gibt Subscription Statistiken zurueck."""
    service = PushNotificationService(db)

    stats = await service.get_subscription_stats(user_id=current_user.id)

    return SubscriptionStatsResponse(**stats)


@router.post(
    "/track-click",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    summary="Notification Click tracken",
    description="Markiert eine Notification als geklickt (fuer Analytics).",
)
async def track_notification_click(
    data: NotificationClickRequest,
    subscription_id: UUID = Query(..., description="Subscription ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Response:
    """Trackt einen Notification Click."""
    service = PushNotificationService(db)

    await service.mark_notification_clicked(subscription_id, data.tag)
    await db.commit()

    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ==================================================
# Test Endpoint (Development Only)
# ==================================================

@router.post(
    "/test",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    summary="Test Notification senden",
    description="Sendet eine Test-Notification an alle Geraete des aktuellen Benutzers. Nur in Entwicklung verfuegbar.",
)
async def send_test_notification(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Response:
    """Sendet eine Test-Notification."""
    if not settings.DEBUG:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Test-Notifications nur in Entwicklung verfuegbar",
        )

    service = PushNotificationService(db)

    success, failed = await service.send_to_user(
        user_id=current_user.id,
        title="Test Notification",
        body="Dies ist eine Test-Nachricht vom Ablage-System.",
        tag="test-notification",
        data={"type": "test", "timestamp": datetime.now(timezone.utc).isoformat()},
    )

    await db.commit()

    if success == 0 and failed == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Keine aktiven Subscriptions gefunden",
        )

    return Response(status_code=status.HTTP_204_NO_CONTENT)
