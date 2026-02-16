# -*- coding: utf-8 -*-
"""Push Notification Service für PWA Web Push.

Dieser Service verwaltet:
- Push Subscriptions (registrieren, aktualisieren, entfernen)
- Notification Templates (erstellen, anwenden)
- Push Nachrichtenversand (einzeln, batch, broadcast)
- Delivery Tracking (status, analytics)

Nutzt pywebpush für VAPID-signierte Web Push Nachrichten.
"""

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID
import json
import re
from app.core.safe_errors import safe_error_detail, safe_error_log

from sqlalchemy import select, update, delete, func
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

try:
    from pywebpush import webpush, WebPushException
    PYWEBPUSH_AVAILABLE = True
except ImportError:
    PYWEBPUSH_AVAILABLE = False
    webpush = None
    WebPushException = Exception

from app.core.config import settings
from app.db.models import PushSubscription, NotificationTemplate, NotificationHistory, User

logger = structlog.get_logger(__name__)


class PushNotificationService:
    """Service für Push Notifications."""

    def __init__(self, db: AsyncSession):
        """Initialisiert den Service.

        Args:
            db: Async Database Session
        """
        self.db = db
        self._vapid_private_key = settings.VAPID_PRIVATE_KEY
        self._vapid_public_key = settings.VAPID_PUBLIC_KEY
        self._vapid_claims = {
            "sub": f"mailto:{settings.VAPID_CONTACT_EMAIL}",
        }

    # ==================================================
    # Subscription Management
    # ==================================================

    async def register_subscription(
        self,
        user_id: UUID,
        endpoint: str,
        p256dh_key: str,
        auth_key: str,
        expiration_time: Optional[int] = None,
        device_name: Optional[str] = None,
        device_type: Optional[str] = None,
        browser: Optional[str] = None,
        os: Optional[str] = None,
        user_agent: Optional[str] = None,
        preferences: Optional[dict[str, bool]] = None,
    ) -> PushSubscription:
        """Registriert eine neue Push Subscription.

        Args:
            user_id: ID des Benutzers
            endpoint: Push Service Endpoint URL
            p256dh_key: Public Key für Verschlüsselung
            auth_key: Auth Secret
            expiration_time: Optional expiration timestamp
            device_name: Optionaler Gerätename
            device_type: mobile, tablet, desktop
            browser: Browser Name
            os: Betriebssystem
            user_agent: Full User Agent String
            preferences: Notification Preferences

        Returns:
            Erstellte PushSubscription
        """
        # Prüfe ob Subscription bereits existiert
        existing = await self.db.execute(
            select(PushSubscription).where(PushSubscription.endpoint == endpoint)
        )
        subscription = existing.scalar_one_or_none()

        if subscription:
            # Update existing subscription
            subscription.user_id = user_id
            subscription.p256dh_key = p256dh_key
            subscription.auth_key = auth_key
            subscription.expiration_time = expiration_time
            subscription.device_name = device_name
            subscription.device_type = device_type
            subscription.browser = browser
            subscription.os = os
            subscription.user_agent = user_agent
            subscription.is_active = True
            subscription.error_count = 0
            subscription.last_error = None
            subscription.updated_at = datetime.now(timezone.utc)

            if preferences:
                subscription.preferences = preferences

            logger.info(
                "push_subscription_updated",
                subscription_id=str(subscription.id),
                user_id=str(user_id),
            )
        else:
            # Create new subscription
            subscription = PushSubscription(
                user_id=user_id,
                endpoint=endpoint,
                p256dh_key=p256dh_key,
                auth_key=auth_key,
                expiration_time=expiration_time,
                device_name=device_name,
                device_type=device_type,
                browser=browser,
                os=os,
                user_agent=user_agent,
                preferences=preferences or {},
                is_active=True,
                error_count=0,
            )
            self.db.add(subscription)
            logger.info(
                "push_subscription_created",
                user_id=str(user_id),
                device_type=device_type,
            )

        await self.db.flush()
        return subscription

    async def unregister_subscription(self, endpoint: str) -> bool:
        """Entfernt eine Push Subscription.

        Args:
            endpoint: Push Service Endpoint URL

        Returns:
            True wenn erfolgreich entfernt
        """
        result = await self.db.execute(
            delete(PushSubscription).where(PushSubscription.endpoint == endpoint)
        )
        deleted = result.rowcount > 0

        if deleted:
            logger.info("push_subscription_removed", endpoint=endpoint[:50])

        return deleted

    async def get_user_subscriptions(
        self,
        user_id: UUID,
        active_only: bool = True,
    ) -> list[PushSubscription]:
        """Holt alle Subscriptions eines Benutzers.

        Args:
            user_id: Benutzer ID
            active_only: Nur aktive Subscriptions

        Returns:
            Liste der Subscriptions
        """
        query = select(PushSubscription).where(PushSubscription.user_id == user_id)

        if active_only:
            query = query.where(PushSubscription.is_active == True)

        result = await self.db.execute(query.order_by(PushSubscription.created_at.desc()))
        return list(result.scalars().all())

    async def get_subscription(
        self,
        subscription_id: UUID,
    ) -> Optional[PushSubscription]:
        """Ruft eine einzelne Subscription ab.

        Args:
            subscription_id: Subscription ID

        Returns:
            PushSubscription oder None wenn nicht gefunden
        """
        result = await self.db.execute(
            select(PushSubscription).where(PushSubscription.id == subscription_id)
        )
        return result.scalar_one_or_none()

    async def update_preferences(
        self,
        subscription_id: UUID,
        preferences: dict[str, bool],
    ) -> Optional[PushSubscription]:
        """Aktualisiert die Notification Preferences einer Subscription.

        Args:
            subscription_id: Subscription ID
            preferences: Neue Preferences

        Returns:
            Aktualisierte Subscription oder None
        """
        result = await self.db.execute(
            select(PushSubscription).where(PushSubscription.id == subscription_id)
        )
        subscription = result.scalar_one_or_none()

        if subscription:
            subscription.preferences = {**subscription.preferences, **preferences}
            subscription.updated_at = datetime.now(timezone.utc)

        return subscription

    # ==================================================
    # Notification Sending
    # ==================================================

    async def send_notification(
        self,
        subscription: PushSubscription,
        title: str,
        body: str,
        icon: Optional[str] = None,
        badge: Optional[str] = None,
        image: Optional[str] = None,
        tag: Optional[str] = None,
        data: Optional[dict] = None,
        actions: Optional[list[dict]] = None,
        require_interaction: bool = False,
        silent: bool = False,
        template_id: Optional[UUID] = None,
    ) -> bool:
        """Sendet eine Push Notification an eine Subscription.

        Args:
            subscription: Ziel-Subscription
            title: Notification Titel
            body: Notification Body
            icon: Icon URL
            badge: Badge URL
            image: Image URL
            tag: Tag für Replacement
            data: Custom Data Payload
            actions: Action Buttons
            require_interaction: Muss interagiert werden
            silent: Stille Notification
            template_id: Optional Template ID für History

        Returns:
            True wenn erfolgreich gesendet
        """
        payload = {
            "title": title,
            "body": body,
            "icon": icon or "/icons/icon-192x192.png",
            "badge": badge or "/icons/icon-72x72.png",
            "tag": tag,
            "data": data or {},
            "requireInteraction": require_interaction,
            "silent": silent,
        }

        if image:
            payload["image"] = image
        if actions:
            payload["actions"] = actions

        # Create history entry
        history = NotificationHistory(
            subscription_id=subscription.id,
            template_id=template_id,
            title=title,
            body=body,
            data=data,
            status="pending",
        )
        self.db.add(history)
        await self.db.flush()

        try:
            webpush(
                subscription_info={
                    "endpoint": subscription.endpoint,
                    "keys": {
                        "p256dh": subscription.p256dh_key,
                        "auth": subscription.auth_key,
                    },
                },
                data=json.dumps(payload),
                vapid_private_key=self._vapid_private_key,
                vapid_claims=self._vapid_claims,
            )

            # Update subscription and history
            subscription.last_used_at = datetime.now(timezone.utc)
            subscription.error_count = 0
            subscription.last_error = None

            history.status = "sent"
            history.sent_at = datetime.now(timezone.utc)

            logger.info(
                "push_notification_sent",
                subscription_id=str(subscription.id),
                title=title,
            )
            return True

        except WebPushException as e:
            error_msg = safe_error_detail(e, "Push")
            subscription.error_count += 1
            subscription.last_error = error_msg

            # Deactivate subscription after too many errors or if expired/unsubscribed
            if subscription.error_count >= 5 or e.response.status_code in (404, 410):
                subscription.is_active = False
                logger.warning(
                    "push_subscription_deactivated",
                    subscription_id=str(subscription.id),
                    error=error_msg,
                )

            history.status = "failed"
            history.error_message = error_msg

            logger.error(
                "push_notification_failed",
                subscription_id=str(subscription.id),
                error=error_msg,
            )
            return False

    async def send_to_user(
        self,
        user_id: UUID,
        title: str,
        body: str,
        category: Optional[str] = None,
        **kwargs,
    ) -> tuple[int, int]:
        """Sendet Notification an alle Geräte eines Benutzers.

        Args:
            user_id: Benutzer ID
            title: Notification Titel
            body: Notification Body
            category: Optional category für preference filtering
            **kwargs: Weitere Parameter für send_notification

        Returns:
            Tuple (erfolgreich, fehlgeschlagen)
        """
        subscriptions = await self.get_user_subscriptions(user_id)

        success_count = 0
        fail_count = 0

        for sub in subscriptions:
            # Check category preferences
            if category and not sub.preferences.get(category, True):
                continue

            if await self.send_notification(sub, title, body, **kwargs):
                success_count += 1
            else:
                fail_count += 1

        return success_count, fail_count

    async def broadcast(
        self,
        title: str,
        body: str,
        category: Optional[str] = None,
        user_filter: Optional[list[UUID]] = None,
        **kwargs,
    ) -> tuple[int, int]:
        """Sendet Notification an alle (gefilterten) Benutzer.

        Args:
            title: Notification Titel
            body: Notification Body
            category: Optional category für preference filtering
            user_filter: Optional liste von User IDs
            **kwargs: Weitere Parameter für send_notification

        Returns:
            Tuple (erfolgreich, fehlgeschlagen)
        """
        query = select(PushSubscription).where(PushSubscription.is_active == True)

        if user_filter:
            query = query.where(PushSubscription.user_id.in_(user_filter))

        result = await self.db.execute(query)
        subscriptions = list(result.scalars().all())

        success_count = 0
        fail_count = 0

        for sub in subscriptions:
            if category and not sub.preferences.get(category, True):
                continue

            if await self.send_notification(sub, title, body, **kwargs):
                success_count += 1
            else:
                fail_count += 1

        logger.info(
            "push_broadcast_completed",
            total=len(subscriptions),
            success=success_count,
            failed=fail_count,
        )

        return success_count, fail_count

    # ==================================================
    # Template Management
    # ==================================================

    async def get_template(self, name: str) -> Optional[NotificationTemplate]:
        """Holt ein Notification Template nach Name.

        Args:
            name: Template Name

        Returns:
            Template oder None
        """
        result = await self.db.execute(
            select(NotificationTemplate).where(
                NotificationTemplate.name == name,
                NotificationTemplate.is_active == True,
            )
        )
        return result.scalar_one_or_none()

    async def send_from_template(
        self,
        user_id: UUID,
        template_name: str,
        variables: dict[str, str],
        extra_data: Optional[dict] = None,
    ) -> tuple[int, int]:
        """Sendet Notification basierend auf Template.

        Args:
            user_id: Benutzer ID
            template_name: Template Name
            variables: Template Variablen (z.B. {"document_name": "Rechnung.pdf"})
            extra_data: Zusätzliche Data Payload

        Returns:
            Tuple (erfolgreich, fehlgeschlagen)
        """
        template = await self.get_template(template_name)
        if not template:
            logger.warning("notification_template_not_found", template_name=template_name)
            return 0, 0

        # Apply template variables
        title = self._apply_variables(template.title_template, variables)
        body = self._apply_variables(template.body_template, variables)
        tag = self._apply_variables(template.tag, variables) if template.tag else None

        return await self.send_to_user(
            user_id=user_id,
            title=title,
            body=body,
            category=template.category,
            icon=template.icon,
            badge=template.badge,
            image=template.image,
            tag=tag,
            actions=template.actions,
            require_interaction=template.require_interaction,
            silent=template.silent,
            data=extra_data,
            template_id=template.id,
        )

    def _apply_variables(self, template: str, variables: dict[str, str]) -> str:
        """Ersetzt Template Variablen.

        Args:
            template: Template String mit {{variable}} Platzhaltern
            variables: Dictionary mit Werten

        Returns:
            Ersetzter String
        """
        result = template
        for key, value in variables.items():
            result = result.replace(f"{{{{{key}}}}}", str(value))
        return result

    # ==================================================
    # Analytics
    # ==================================================

    async def get_subscription_stats(
        self,
        user_id: Optional[UUID] = None,
    ) -> dict:
        """Holt Subscription Statistiken.

        Args:
            user_id: Optional User ID für Filterung

        Returns:
            Statistik Dictionary
        """
        base_query = select(PushSubscription)

        if user_id:
            base_query = base_query.where(PushSubscription.user_id == user_id)

        # Total count
        total_result = await self.db.execute(
            select(func.count(PushSubscription.id)).select_from(base_query.subquery())
        )
        total = total_result.scalar() or 0

        # Active count
        active_query = base_query.where(PushSubscription.is_active == True)
        active_result = await self.db.execute(
            select(func.count(PushSubscription.id)).select_from(active_query.subquery())
        )
        active = active_result.scalar() or 0

        # Device type breakdown
        device_query = (
            select(PushSubscription.device_type, func.count(PushSubscription.id))
            .where(PushSubscription.is_active == True)
            .group_by(PushSubscription.device_type)
        )
        if user_id:
            device_query = device_query.where(PushSubscription.user_id == user_id)

        device_result = await self.db.execute(device_query)
        devices = {row[0] or "unknown": row[1] for row in device_result.fetchall()}

        return {
            "total": total,
            "active": active,
            "inactive": total - active,
            "by_device_type": devices,
        }

    async def mark_notification_clicked(
        self,
        subscription_id: UUID,
        notification_tag: str,
    ) -> bool:
        """Markiert eine Notification als geklickt.

        Args:
            subscription_id: Subscription ID
            notification_tag: Notification Tag

        Returns:
            True wenn erfolgreich
        """
        # Find the most recent matching notification
        result = await self.db.execute(
            select(NotificationHistory)
            .where(
                NotificationHistory.subscription_id == subscription_id,
                NotificationHistory.status.in_(["sent", "delivered"]),
            )
            .order_by(NotificationHistory.created_at.desc())
            .limit(1)
        )
        history = result.scalar_one_or_none()

        if history:
            history.status = "clicked"
            history.clicked_at = datetime.now(timezone.utc)
            return True

        return False
