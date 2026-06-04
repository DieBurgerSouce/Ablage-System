"""
Skonto Deadline Notification Service.

Spezialisierter Service für Skonto-Frist-Benachrichtigungen.
Unterstützt Email, Slack und In-App Channels.

Feinpoliert und durchdacht - Multi-Channel Skonto Alerts.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Optional
from uuid import UUID

import structlog
from app.core.safe_errors import safe_error_log

logger = structlog.get_logger(__name__)


class SkontoUrgencyLevel(str, Enum):
    """Dringlichkeitsstufen für Skonto-Benachrichtigungen."""
    INFO = "info"           # 7+ Tage voraus
    WARNING = "warning"     # 3-7 Tage voraus
    URGENT = "urgent"       # 1-3 Tage voraus
    CRITICAL = "critical"   # Weniger als 1 Tag


@dataclass
class SkontoOpportunity:
    """Skonto-Gelegenheit für Benachrichtigungen."""
    invoice_id: UUID
    invoice_number: str
    amount: float
    skonto_percentage: float
    skonto_amount: float
    deadline: datetime
    days_remaining: int
    entity_name: Optional[str] = None

    @property
    def urgency(self) -> SkontoUrgencyLevel:
        """Berechnet die Dringlichkeitsstufe."""
        if self.days_remaining <= 0:
            return SkontoUrgencyLevel.CRITICAL
        elif self.days_remaining <= 1:
            return SkontoUrgencyLevel.CRITICAL
        elif self.days_remaining <= 3:
            return SkontoUrgencyLevel.URGENT
        elif self.days_remaining <= 7:
            return SkontoUrgencyLevel.WARNING
        return SkontoUrgencyLevel.INFO


class SkontoNotificationService:
    """
    Service für Multi-Channel Skonto-Benachrichtigungen.

    Channels:
    - Email: Detaillierte Zusammenfassung
    - Slack: Schnelle Benachrichtigungen (nur für dringende Fristen)
    - In-App: Immer, wenn Opportunities existieren

    Usage:
        service = SkontoNotificationService()
        await service.notify_user(
            user_id=user_id,
            email=user_email,
            opportunities=opportunities,
        )
    """

    def __init__(self) -> None:
        """Initialisiert den Service."""
        self._notification_service = None
        self._slack_service = None

    @property
    def notification_service(self):
        """Lazy-Load NotificationService."""
        if self._notification_service is None:
            from app.services.notification_service import NotificationService
            self._notification_service = NotificationService()
        return self._notification_service

    @property
    def slack_service(self):
        """Lazy-Load SlackService."""
        if self._slack_service is None:
            from app.services.slack_service import SlackService
            self._slack_service = SlackService()
        return self._slack_service

    async def notify_user(
        self,
        user_id: str,
        email: Optional[str],
        opportunities: list[SkontoOpportunity],
        include_slack: bool = True,
        include_email: bool = True,
        include_in_app: bool = True,
    ) -> dict[str, bool]:
        """
        Sendet Skonto-Benachrichtigungen an einen User.

        Args:
            user_id: User-ID
            email: Email-Adresse (optional)
            opportunities: Liste der Skonto-Gelegenheiten
            include_slack: Slack-Benachrichtigung senden
            include_email: Email-Benachrichtigung senden
            include_in_app: In-App-Benachrichtigung senden

        Returns:
            Dict mit Erfolgs-Status pro Channel
        """
        if not opportunities:
            return {"email": False, "slack": False, "in_app": False}

        result = {"email": False, "slack": False, "in_app": False}

        # Gruppiere nach Dringlichkeit
        critical = [o for o in opportunities if o.urgency == SkontoUrgencyLevel.CRITICAL]
        urgent = [o for o in opportunities if o.urgency == SkontoUrgencyLevel.URGENT]
        warning = [o for o in opportunities if o.urgency == SkontoUrgencyLevel.WARNING]
        info = [o for o in opportunities if o.urgency == SkontoUrgencyLevel.INFO]

        # Berechne Gesamt-Ersparnis
        total_savings = sum(o.skonto_amount for o in opportunities)

        # Email-Benachrichtigung
        if include_email and email:
            result["email"] = await self._send_email_notification(
                user_id=user_id,
                email=email,
                opportunities=opportunities,
                total_savings=total_savings,
            )

        # Slack nur für kritische/dringende Faelle
        if include_slack and (critical or urgent):
            result["slack"] = await self._send_slack_notification(
                critical=critical,
                urgent=urgent,
                total_savings=total_savings,
            )

        # In-App immer
        if include_in_app:
            result["in_app"] = await self._send_in_app_notification(
                user_id=user_id,
                opportunities=opportunities,
                total_savings=total_savings,
            )

        logger.info(
            "skonto_notifications_sent",
            user_id=user_id,
            opportunities_count=len(opportunities),
            critical_count=len(critical),
            urgent_count=len(urgent),
            total_savings=total_savings,
            results=result,
        )

        return result

    async def _send_email_notification(
        self,
        user_id: str,
        email: str,
        opportunities: list[SkontoOpportunity],
        total_savings: float,
    ) -> bool:
        """Sendet Email-Benachrichtigung."""
        try:
            from app.services.notification_service import (
                NotificationType,
                NotificationPriority,
            )

            # Formatiere Opportunities-Liste
            opportunities_list = "\n".join([
                f"- {o.invoice_number}: {o.amount:.2f} EUR "
                f"(Skonto: {o.skonto_amount:.2f} EUR, "
                f"Frist: {o.deadline.strftime('%d.%m.%Y')}, "
                f"{o.days_remaining} Tag(e))"
                for o in sorted(opportunities, key=lambda x: x.days_remaining)[:15]
            ])
            if len(opportunities) > 15:
                opportunities_list += f"\n... und {len(opportunities) - 15} weitere"

            # Priorität basierend auf dringendster Frist
            min_days = min(o.days_remaining for o in opportunities)
            priority = (
                NotificationPriority.URGENT if min_days <= 1
                else NotificationPriority.HIGH if min_days <= 3
                else NotificationPriority.NORMAL
            )

            await self.notification_service.notify(
                notification_type=NotificationType.SKONTO_EXPIRING,
                context={
                    "opportunities_list": opportunities_list,
                    "total_savings": f"{total_savings:.2f}",
                },
                user_id=user_id,
                email=email,
                priority=priority,
            )
            return True

        except Exception as e:
            logger.warning(
                "skonto_email_notification_failed",
                user_id=user_id,
                **safe_error_log(e),
            )
            return False

    async def _send_slack_notification(
        self,
        critical: list[SkontoOpportunity],
        urgent: list[SkontoOpportunity],
        total_savings: float,
    ) -> bool:
        """Sendet Slack-Benachrichtigung für dringende Faelle."""
        try:
            from app.services.slack_service import (

                SlackNotificationType,
                SlackMessagePriority,
            )

            if not self.slack_service.is_enabled:
                return False

            # Bestimme Dringlichkeit
            if critical:
                urgency_text = "KRITISCH"
                priority = SlackMessagePriority.URGENT
                count = len(critical)
                example = critical[0]
            else:
                urgency_text = "DRINGEND"
                priority = SlackMessagePriority.HIGH
                count = len(urgent)
                example = urgent[0]

            # Formatiere Nachricht
            message = (
                f"*{count} Rechnung(en)* mit ablaufenden Skonto-Fristen!\n\n"
                f"Beispiel: {example.invoice_number} - "
                f"{example.amount:.2f} EUR (Skonto: {example.skonto_amount:.2f} EUR)\n"
                f"Frist: {example.deadline.strftime('%d.%m.%Y')} ({example.days_remaining} Tag(e))\n\n"
                f"Potenzielle Gesamtersparnis: *{total_savings:.2f} EUR*"
            )

            await self.slack_service.send_notification(
                notification_type=SlackNotificationType.SKONTO_EXPIRING,
                title=f"{urgency_text}: Skonto-Fristen",
                message=message,
                context={
                    "kritische_rechnungen": len(critical),
                    "dringende_rechnungen": len(urgent),
                    "ersparnis_eur": total_savings,
                },
                priority=priority,
            )
            return True

        except Exception as e:
            logger.debug(
                "skonto_slack_notification_failed",
                **safe_error_log(e),
            )
            return False

    async def _send_in_app_notification(
        self,
        user_id: str,
        opportunities: list[SkontoOpportunity],
        total_savings: float,
    ) -> bool:
        """Sendet In-App-Benachrichtigung."""
        try:
            # Bestimme dringendste Frist
            min_days = min(o.days_remaining for o in opportunities)

            if min_days <= 1:
                title = "Skonto-Fristen laufen HEUTE ab!"
            elif min_days <= 3:
                title = f"Skonto-Fristen in {min_days} Tagen"
            else:
                title = "Skonto-Gelegenheiten verfügbar"

            message = (
                f"{len(opportunities)} Rechnung(en) mit Skonto-Fristen. "
                f"Potenzielle Ersparnis: {total_savings:.2f} EUR"
            )

            await self.notification_service.in_app.store_notification(
                user_id=user_id,
                notification_type="skonto_expiring",
                title=title,
                message=message,
                data={
                    "count": len(opportunities),
                    "total_savings": total_savings,
                    "min_days": min_days,
                },
            )
            return True

        except Exception as e:
            logger.debug(
                "skonto_in_app_notification_failed",
                user_id=user_id,
                **safe_error_log(e),
            )
            return False


# Singleton-Instanz
_skonto_notification_service: Optional[SkontoNotificationService] = None


def get_skonto_notification_service() -> SkontoNotificationService:
    """Gibt die Singleton-Instanz zurück."""
    global _skonto_notification_service
    if _skonto_notification_service is None:
        _skonto_notification_service = SkontoNotificationService()
    return _skonto_notification_service


async def send_skonto_alerts(
    user_id: str,
    email: Optional[str],
    opportunities: list[dict[str, Any]],
) -> dict[str, bool]:
    """
    Convenience-Funktion für Skonto-Alerts.

    Args:
        user_id: User-ID
        email: Email-Adresse
        opportunities: Liste der Opportunities als Dicts

    Returns:
        Ergebnis-Dict
    """
    service = get_skonto_notification_service()

    # Konvertiere Dicts zu SkontoOpportunity
    opps = []
    now = datetime.now(timezone.utc)

    for o in opportunities:
        deadline = o.get("deadline")
        if isinstance(deadline, str):
            try:
                deadline = datetime.fromisoformat(deadline.replace("Z", "+00:00"))
            except ValueError:
                deadline = now + timedelta(days=7)

        days_remaining = (deadline - now).days if deadline else 7

        opps.append(SkontoOpportunity(
            invoice_id=UUID(str(o.get("invoice_id", "00000000-0000-0000-0000-000000000000"))),
            invoice_number=o.get("invoice_number", "N/A"),
            amount=float(o.get("amount", 0)),
            skonto_percentage=float(o.get("skonto_percentage", 0)),
            skonto_amount=float(o.get("savings", o.get("skonto_amount", 0))),
            deadline=deadline,
            days_remaining=days_remaining,
            entity_name=o.get("entity_name"),
        ))

    return await service.notify_user(
        user_id=user_id,
        email=email,
        opportunities=opps,
    )
