# -*- coding: utf-8 -*-
"""
Digest Service for Ablage-System.

Enterprise-grade Email-Zusammenfassungen:
- Tägliche/wöchentliche Digest-Emails
- Benutzer-Präferenzen für Frequenz
- Benachrichtigungs-Queue-Management
- HTML-Email-Templates

Feinpoliert und durchdacht - Digest-System auf Enterprise-Niveau.
"""

import structlog
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy import and_, delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.datetime_utils import utc_now
from app.db.models import (
    DigestFrequency,
    NotificationDigestQueue,
    NotificationPreference,
    User,
    UserNotification,
)

logger = structlog.get_logger(__name__)


class DigestService:
    """Service fuer Benachrichtigungs-Digests."""

    def __init__(self, db: AsyncSession):
        """Initialisiert den DigestService.

        Args:
            db: AsyncSession fuer Datenbankoperationen
        """
        self.db = db

    # =========================================================================
    # Preference Management
    # =========================================================================

    async def get_user_preferences(
        self,
        user_id: UUID,
    ) -> List[NotificationPreference]:
        """Holt alle Benachrichtigungs-Präferenzen eines Benutzers.

        Args:
            user_id: ID des Benutzers

        Returns:
            Liste von NotificationPreference
        """
        result = await self.db.execute(
            select(NotificationPreference)
            .where(NotificationPreference.user_id == user_id)
        )
        return list(result.scalars().all())

    async def get_preference(
        self,
        user_id: UUID,
        notification_type: str,
    ) -> Optional[NotificationPreference]:
        """Holt eine spezifische Präferenz.

        Args:
            user_id: ID des Benutzers
            notification_type: Typ der Benachrichtigung

        Returns:
            NotificationPreference oder None
        """
        result = await self.db.execute(
            select(NotificationPreference)
            .where(
                and_(
                    NotificationPreference.user_id == user_id,
                    NotificationPreference.notification_type == notification_type,
                )
            )
        )
        return result.scalar_one_or_none()

    async def set_preference(
        self,
        user_id: UUID,
        notification_type: str,
        email_enabled: bool = True,
        in_app_enabled: bool = True,
        websocket_enabled: bool = True,
        slack_enabled: bool = False,
        sms_enabled: bool = False,
        digest_frequency: str = DigestFrequency.IMMEDIATE.value,
    ) -> NotificationPreference:
        """Setzt oder aktualisiert eine Benachrichtigungs-Präferenz.

        Args:
            user_id: ID des Benutzers
            notification_type: Typ der Benachrichtigung
            email_enabled: Email-Benachrichtigungen aktiviert
            in_app_enabled: In-App-Benachrichtigungen aktiviert
            websocket_enabled: WebSocket-Benachrichtigungen aktiviert
            slack_enabled: Slack-Benachrichtigungen aktiviert
            sms_enabled: SMS-Benachrichtigungen aktiviert
            digest_frequency: Digest-Frequenz

        Returns:
            Aktualisierte oder neue NotificationPreference
        """
        pref = await self.get_preference(user_id, notification_type)

        # Build enabled_channels JSONB
        enabled_channels = {
            "in_app": in_app_enabled,
            "email": email_enabled,
            "websocket": websocket_enabled,
            "slack": slack_enabled,
            "sms": sms_enabled,
        }

        if pref:
            pref.enabled_channels = enabled_channels
            pref.digest_frequency = digest_frequency
            pref.updated_at = utc_now()
        else:
            pref = NotificationPreference(
                user_id=user_id,
                notification_type=notification_type,
                enabled_channels=enabled_channels,
                digest_frequency=digest_frequency,
            )
            self.db.add(pref)

        await self.db.commit()
        await self.db.refresh(pref)

        logger.info(
            "notification_preference_set",
            user_id=str(user_id),
            notification_type=notification_type,
            digest_frequency=digest_frequency,
        )

        return pref

    async def delete_preference(
        self,
        user_id: UUID,
        notification_type: str,
    ) -> bool:
        """Löscht eine Benachrichtigungs-Präferenz.

        Args:
            user_id: ID des Benutzers
            notification_type: Typ der Benachrichtigung

        Returns:
            True bei Erfolg, False wenn nicht gefunden
        """
        pref = await self.get_preference(user_id, notification_type)
        if not pref:
            return False

        await self.db.delete(pref)
        await self.db.commit()

        logger.info(
            "notification_preference_deleted",
            user_id=str(user_id),
            notification_type=notification_type,
        )

        return True

    # =========================================================================
    # Digest Queue Management
    # =========================================================================

    async def queue_for_digest(
        self,
        notification: UserNotification,
        digest_frequency: str,
    ) -> NotificationDigestQueue:
        """Fügt eine Benachrichtigung zur Digest-Queue hinzu.

        Args:
            notification: Die zu queuende Benachrichtigung
            digest_frequency: Gewünschte Digest-Frequenz

        Returns:
            NotificationDigestQueue Eintrag
        """
        # Berechne geplante Versandzeit
        scheduled_for = self._calculate_scheduled_time(digest_frequency)

        # NotificationDigestQueue speichert Daten direkt (nicht als FK)
        queue_entry = NotificationDigestQueue(
            user_id=notification.user_id,
            notification_type=notification.notification_type,
            title=notification.title,
            message=notification.message,
            action_url=notification.action_url,
            document_id=getattr(notification, "document_id", None),
            from_user_id=getattr(notification, "from_user_id", None),
            digest_frequency=digest_frequency,
            scheduled_for=scheduled_for,
        )

        self.db.add(queue_entry)
        await self.db.commit()
        await self.db.refresh(queue_entry)

        logger.debug(
            "notification_queued_for_digest",
            notification_type=notification.notification_type,
            user_id=str(notification.user_id),
            digest_frequency=digest_frequency,
            scheduled_for=scheduled_for.isoformat(),
        )

        return queue_entry

    def _calculate_scheduled_time(self, digest_frequency: str) -> datetime:
        """Berechnet die geplante Versandzeit basierend auf Frequenz.

        Args:
            digest_frequency: Digest-Frequenz

        Returns:
            Geplante Versandzeit
        """
        now = utc_now()

        if digest_frequency == DigestFrequency.HOURLY.value:
            # Nächste volle Stunde
            return now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)

        elif digest_frequency == DigestFrequency.DAILY.value:
            # Morgen um 8:00 Uhr
            tomorrow = now + timedelta(days=1)
            return tomorrow.replace(hour=8, minute=0, second=0, microsecond=0)

        elif digest_frequency == DigestFrequency.WEEKLY.value:
            # Nächster Montag um 8:00 Uhr
            days_until_monday = (7 - now.weekday()) % 7
            if days_until_monday == 0:
                days_until_monday = 7
            next_monday = now + timedelta(days=days_until_monday)
            return next_monday.replace(hour=8, minute=0, second=0, microsecond=0)

        else:
            # Immediate - sofort
            return now

    async def get_pending_digests(
        self,
        frequency: str,
        limit: int = 1000,
    ) -> Dict[UUID, List[NotificationDigestQueue]]:
        """Holt ausstehende Digests gruppiert nach Benutzer.

        Args:
            frequency: Digest-Frequenz
            limit: Max. Anzahl Einträge

        Returns:
            Dict von user_id -> Liste von Queue-Einträgen
        """
        now = utc_now()

        # NotificationDigestQueue speichert Daten direkt - kein selectinload noetig
        result = await self.db.execute(
            select(NotificationDigestQueue)
            .where(
                and_(
                    NotificationDigestQueue.digest_frequency == frequency,
                    NotificationDigestQueue.scheduled_for <= now,
                    NotificationDigestQueue.is_sent == False,  # noqa: E712
                )
            )
            .order_by(NotificationDigestQueue.created_at.asc())
            .limit(limit)
        )

        entries = result.scalars().all()

        # Gruppiere nach User
        by_user: Dict[UUID, List[NotificationDigestQueue]] = {}
        for entry in entries:
            if entry.user_id not in by_user:
                by_user[entry.user_id] = []
            by_user[entry.user_id].append(entry)

        return by_user

    async def mark_digests_sent(
        self,
        queue_ids: List[UUID],
    ) -> int:
        """Markiert Queue-Einträge als gesendet.

        Args:
            queue_ids: Liste von Queue-Eintrag-IDs

        Returns:
            Anzahl aktualisierter Einträge
        """
        if not queue_ids:
            return 0

        now = utc_now()

        result = await self.db.execute(
            update(NotificationDigestQueue)
            .where(NotificationDigestQueue.id.in_(queue_ids))
            .values(is_sent=True, sent_at=now)
        )
        await self.db.commit()

        count = result.rowcount
        logger.info(
            "digests_marked_sent",
            count=count,
        )

        return count

    async def cleanup_old_digests(
        self,
        days_old: int = 7,
    ) -> int:
        """Löscht alte gesendete Digest-Einträge.

        Args:
            days_old: Einträge älter als X Tage löschen

        Returns:
            Anzahl gelöschter Einträge
        """
        cutoff = utc_now() - timedelta(days=days_old)

        result = await self.db.execute(
            delete(NotificationDigestQueue)
            .where(
                and_(
                    NotificationDigestQueue.sent_at.isnot(None),
                    NotificationDigestQueue.sent_at < cutoff,
                )
            )
        )
        await self.db.commit()

        count = result.rowcount
        logger.info(
            "old_digests_cleaned_up",
            count=count,
            days_old=days_old,
        )

        return count

    # =========================================================================
    # Digest Compilation
    # =========================================================================

    async def compile_digest(
        self,
        user_id: UUID,
        queue_entries: List[NotificationDigestQueue],
    ) -> Dict[str, Any]:
        """Kompiliert einen Digest aus Queue-Einträgen.

        Args:
            user_id: ID des Benutzers
            queue_entries: Liste von Queue-Einträgen

        Returns:
            Kompilierter Digest als Dict
        """
        # Hole User-Info
        user_result = await self.db.execute(
            select(User).where(User.id == user_id)
        )
        user = user_result.scalar_one_or_none()

        if not user:
            logger.warning("digest_user_not_found", user_id=str(user_id))
            return {}

        # Gruppiere nach Notification-Typ
        # NotificationDigestQueue speichert Daten direkt (nicht als Relationship)
        by_type: Dict[str, List[Dict[str, Any]]] = {}

        for entry in queue_entries:
            notif_type = entry.notification_type
            if notif_type not in by_type:
                by_type[notif_type] = []

            by_type[notif_type].append({
                "id": str(entry.id),
                "title": entry.title,
                "message": entry.message,
                "action_url": entry.action_url,
                "created_at": entry.created_at.isoformat() if entry.created_at else "",
            })

        return {
            "user_id": str(user_id),
            "user_name": user.full_name or user.username or user.email,
            "user_email": user.email,
            "notification_count": len(queue_entries),
            "notifications_by_type": by_type,
            "compiled_at": utc_now().isoformat(),
        }

    def render_digest_html(
        self,
        digest_data: Dict[str, Any],
        frequency: str,
    ) -> str:
        """Rendert einen Digest als HTML-Email.

        Args:
            digest_data: Kompilierter Digest
            frequency: Digest-Frequenz (für Titel)

        Returns:
            HTML-String
        """
        frequency_titles = {
            DigestFrequency.HOURLY.value: "Stündliche",
            DigestFrequency.DAILY.value: "Tägliche",
            DigestFrequency.WEEKLY.value: "Wöchentliche",
        }
        title = frequency_titles.get(frequency, "")

        user_name = digest_data.get("user_name", "Benutzer")
        notification_count = digest_data.get("notification_count", 0)
        by_type = digest_data.get("notifications_by_type", {})

        # Build HTML
        html_parts = [
            "<!DOCTYPE html>",
            "<html lang='de'>",
            "<head>",
            "<meta charset='UTF-8'>",
            "<meta name='viewport' content='width=device-width, initial-scale=1.0'>",
            f"<title>{title} Zusammenfassung - Ablage-System</title>",
            "<style>",
            "body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px; }",
            "h1 { color: #1a73e8; font-size: 24px; }",
            "h2 { color: #5f6368; font-size: 18px; margin-top: 24px; }",
            ".notification { background: #f8f9fa; border-radius: 8px; padding: 16px; margin-bottom: 12px; }",
            ".notification-title { font-weight: 600; margin-bottom: 4px; }",
            ".notification-message { color: #5f6368; }",
            ".notification-time { font-size: 12px; color: #9aa0a6; margin-top: 8px; }",
            ".footer { margin-top: 32px; padding-top: 16px; border-top: 1px solid #e0e0e0; font-size: 12px; color: #9aa0a6; }",
            "</style>",
            "</head>",
            "<body>",
            f"<h1>{title} Zusammenfassung</h1>",
            f"<p>Hallo {user_name},</p>",
            f"<p>Sie haben {notification_count} neue Benachrichtigungen:</p>",
        ]

        # Notification type mappings
        type_labels = {
            "task_assigned": "Zugewiesene Aufgaben",
            "task_completed": "Abgeschlossene Aufgaben",
            "task_escalated": "Eskalierte Aufgaben",
            "task_reminder": "Aufgaben-Erinnerungen",
            "mention": "Erwähnungen",
            "comment_reply": "Antworten auf Kommentare",
            "document_shared": "Geteilte Dokumente",
            "document_approved": "Genehmigte Dokumente",
            "document_rejected": "Abgelehnte Dokumente",
        }

        for notif_type, notifications in by_type.items():
            label = type_labels.get(notif_type, notif_type)
            html_parts.append(f"<h2>{label} ({len(notifications)})</h2>")

            for notif in notifications:
                html_parts.extend([
                    "<div class='notification'>",
                    f"<div class='notification-title'>{notif['title']}</div>",
                    f"<div class='notification-message'>{notif['message']}</div>",
                    f"<div class='notification-time'>{notif['created_at']}</div>",
                    "</div>",
                ])

        html_parts.extend([
            "<div class='footer'>",
            "<p>Diese E-Mail wurde automatisch vom Ablage-System generiert.</p>",
            "<p>Um Ihre Benachrichtigungseinstellungen zu ändern, besuchen Sie die Einstellungen in der App.</p>",
            "</div>",
            "</body>",
            "</html>",
        ])

        return "\n".join(html_parts)

    def render_digest_subject(
        self,
        digest_data: Dict[str, Any],
        frequency: str,
    ) -> str:
        """Generiert den Email-Betreff für einen Digest.

        Args:
            digest_data: Kompilierter Digest
            frequency: Digest-Frequenz

        Returns:
            Email-Betreff
        """
        count = digest_data.get("notification_count", 0)

        frequency_labels = {
            DigestFrequency.HOURLY.value: "Stündliche",
            DigestFrequency.DAILY.value: "Tägliche",
            DigestFrequency.WEEKLY.value: "Wöchentliche",
        }
        freq_label = frequency_labels.get(frequency, "")

        return f"{freq_label} Zusammenfassung: {count} neue Benachrichtigungen"


# =============================================================================
# Factory Function
# =============================================================================


def get_digest_service(db: AsyncSession) -> DigestService:
    """Factory-Funktion für DigestService.

    Args:
        db: AsyncSession für Datenbankoperationen

    Returns:
        DigestService Instanz
    """
    return DigestService(db)
