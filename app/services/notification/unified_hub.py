# -*- coding: utf-8 -*-
"""
Unified Notification Hub fuer Ablage-System.

Zentraler Orchestrator fuer alle Benachrichtigungskanaele:
- Email (SMTP)
- Slack (Webhook/Bot)
- Microsoft Teams (Webhook/Adaptive Cards)
- Push Notifications (PWA Web Push)
- SMS (Twilio)
- WhatsApp (Twilio)
- In-App (Redis)
- WebSocket (Real-time)

Features:
- Severity-basiertes Routing
- Benutzer-Praeferenzen
- Deduplizierung (kein doppeltes Senden)
- Delivery Tracking mit Retry
- Eskalationsketten
- Audit-Logging

Feinpoliert und durchdacht - Ein Hub fuer alle Benachrichtigungen.
"""

import asyncio
import hashlib
import json
import time
from collections import deque
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from enum import Enum
from typing import Dict, Optional, TypedDict
from uuid import UUID, uuid4

import structlog
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings as app_settings
from app.core.safe_errors import safe_error_log, safe_error_detail

logger = structlog.get_logger(__name__)


# =============================================================================
# Enums und Konstanten
# =============================================================================

class NotificationChannel(str, Enum):
    """Verfuegbare Benachrichtigungskanaele."""
    EMAIL = "email"
    SLACK = "slack"
    TEAMS = "teams"
    PUSH = "push"
    SMS = "sms"
    WHATSAPP = "whatsapp"
    IN_APP = "in_app"
    WEBSOCKET = "websocket"


class NotificationSeverity(str, Enum):
    """Schweregrad einer Benachrichtigung."""
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class NotificationCategory(str, Enum):
    """Kategorien von Benachrichtigungen."""
    DOCUMENT = "document"
    ALERT = "alert"
    WORKFLOW = "workflow"
    SYSTEM = "system"
    SECURITY = "security"
    FINANCE = "finance"
    COMPLIANCE = "compliance"
    REMINDER = "reminder"


class DeliveryStatus(str, Enum):
    """Lieferstatus einer Benachrichtigung."""
    PENDING = "pending"
    SENT = "sent"
    DELIVERED = "delivered"
    FAILED = "failed"
    SKIPPED = "skipped"
    DEDUPED = "deduped"


class EscalationLevel(int, Enum):
    """Eskalationsstufen."""
    NONE = 0
    LEVEL_1 = 1  # Email + Slack
    LEVEL_2 = 2  # + Teams
    LEVEL_3 = 3  # + Push
    LEVEL_4 = 4  # + SMS
    LEVEL_5 = 5  # + WhatsApp + Anruf


# Kanal-Prioritaet fuer Routing (hoeherer Wert = hoehere Prioritaet)
CHANNEL_PRIORITY = {
    NotificationChannel.EMAIL: 1,
    NotificationChannel.SLACK: 2,
    NotificationChannel.TEAMS: 2,
    NotificationChannel.IN_APP: 3,
    NotificationChannel.WEBSOCKET: 3,
    NotificationChannel.PUSH: 4,
    NotificationChannel.SMS: 5,
    NotificationChannel.WHATSAPP: 5,
}

# Standard-Kanaele pro Schweregrad
DEFAULT_CHANNELS_BY_SEVERITY = {
    NotificationSeverity.INFO: [
        NotificationChannel.IN_APP,
    ],
    NotificationSeverity.LOW: [
        NotificationChannel.IN_APP,
        NotificationChannel.WEBSOCKET,
    ],
    NotificationSeverity.MEDIUM: [
        NotificationChannel.EMAIL,
        NotificationChannel.SLACK,
        NotificationChannel.IN_APP,
    ],
    NotificationSeverity.HIGH: [
        NotificationChannel.EMAIL,
        NotificationChannel.SLACK,
        NotificationChannel.TEAMS,
        NotificationChannel.PUSH,
        NotificationChannel.IN_APP,
    ],
    NotificationSeverity.CRITICAL: [
        NotificationChannel.EMAIL,
        NotificationChannel.SLACK,
        NotificationChannel.TEAMS,
        NotificationChannel.PUSH,
        NotificationChannel.SMS,
        NotificationChannel.IN_APP,
    ],
}

# Deduplizierungs-TTL (in Sekunden)
DEDUP_TTL_BY_SEVERITY = {
    NotificationSeverity.INFO: 3600,      # 1 Stunde
    NotificationSeverity.LOW: 1800,       # 30 Minuten
    NotificationSeverity.MEDIUM: 900,     # 15 Minuten
    NotificationSeverity.HIGH: 300,       # 5 Minuten
    NotificationSeverity.CRITICAL: 60,    # 1 Minute
}


# =============================================================================
# Pydantic Models
# =============================================================================

class NotificationAction(BaseModel):
    """Aktions-Button fuer Benachrichtigungen."""

    action_id: str = Field(..., description="Eindeutige Aktion-ID")
    title: str = Field(..., max_length=50, description="Button-Text")
    url: Optional[str] = Field(default=None, description="URL bei Klick")
    style: str = Field(default="default", description="primary, danger, default")


class NotificationRecipient(BaseModel):
    """Empfaenger einer Benachrichtigung."""

    user_id: UUID = Field(..., description="Benutzer-ID")
    email: Optional[str] = Field(default=None, description="E-Mail-Adresse")
    phone_number: Optional[str] = Field(default=None, description="Telefonnummer (E.164)")
    slack_user_id: Optional[str] = Field(default=None, description="Slack User ID")
    teams_user_id: Optional[str] = Field(default=None, description="Teams User ID")


class NotificationPayload(BaseModel):
    """Payload fuer eine Benachrichtigung."""

    # Identifikation
    notification_id: UUID = Field(
        default_factory=uuid4,
        description="Eindeutige Benachrichtigungs-ID"
    )
    notification_type: str = Field(
        ...,
        max_length=100,
        description="Typ der Benachrichtigung"
    )

    # Inhalt
    title: str = Field(..., max_length=200, description="Titel")
    message: str = Field(..., max_length=2000, description="Hauptnachricht")
    short_message: Optional[str] = Field(
        default=None,
        max_length=160,
        description="Kurznachricht fuer SMS"
    )

    # Klassifikation
    category: NotificationCategory = Field(
        default=NotificationCategory.SYSTEM,
        description="Kategorie"
    )
    severity: NotificationSeverity = Field(
        default=NotificationSeverity.MEDIUM,
        description="Schweregrad"
    )

    # Kontext
    company_id: Optional[UUID] = Field(default=None, description="Mandanten-ID")
    reference_type: Optional[str] = Field(default=None, description="Referenz-Typ (document, alert, etc.)")
    reference_id: Optional[str] = Field(default=None, description="Referenz-ID")
    metadata: dict[str, object] = Field(default_factory=dict, description="Zusaetzliche Metadaten")

    # UI
    icon: Optional[str] = Field(default=None, description="Icon-Name oder URL")
    color: Optional[str] = Field(default=None, description="Farbcode")
    url: Optional[str] = Field(default=None, description="Link bei Klick")
    actions: list[NotificationAction] = Field(default_factory=list, description="Aktions-Buttons")

    # Optionen
    dedupe_key: Optional[str] = Field(
        default=None,
        description="Key fuer Deduplizierung (generiert wenn leer)"
    )
    ttl_seconds: Optional[int] = Field(
        default=None,
        description="Time-To-Live fuer Deduplizierung"
    )
    persist: bool = Field(
        default=True,
        description="In Datenbank speichern"
    )

    def generate_dedupe_key(self) -> str:
        """Generiert einen Deduplizierungs-Key."""
        if self.dedupe_key:
            return self.dedupe_key

        # Hash aus Typ, Referenz und Titel
        key_data = f"{self.notification_type}:{self.reference_type}:{self.reference_id}:{self.title}"
        return hashlib.md5(key_data.encode()).hexdigest()


class UserNotificationPreferences(BaseModel):
    """Benutzer-Praeferenzen fuer Benachrichtigungen."""

    # Globale Einstellungen
    enabled: bool = Field(default=True, description="Benachrichtigungen aktiviert")

    # Kanal-Praeferenzen
    email_enabled: bool = Field(default=True)
    slack_enabled: bool = Field(default=True)
    teams_enabled: bool = Field(default=True)
    push_enabled: bool = Field(default=True)
    sms_enabled: bool = Field(default=False)  # Explizites Opt-in
    whatsapp_enabled: bool = Field(default=False)  # Explizites Opt-in
    in_app_enabled: bool = Field(default=True)

    # Kategorie-Praeferenzen (welche Kategorien pro Kanal)
    email_categories: list[str] = Field(
        default_factory=lambda: [
            NotificationCategory.DOCUMENT.value,
            NotificationCategory.ALERT.value,
            NotificationCategory.WORKFLOW.value,
            NotificationCategory.SECURITY.value,
        ]
    )
    push_categories: list[str] = Field(
        default_factory=lambda: [
            NotificationCategory.ALERT.value,
            NotificationCategory.WORKFLOW.value,
            NotificationCategory.SECURITY.value,
        ]
    )
    sms_categories: list[str] = Field(
        default_factory=lambda: [
            NotificationCategory.SECURITY.value,
            NotificationCategory.ALERT.value,
        ]
    )

    # Minimum-Schweregrad pro Kanal
    email_min_severity: str = Field(default=NotificationSeverity.LOW.value)
    push_min_severity: str = Field(default=NotificationSeverity.MEDIUM.value)
    sms_min_severity: str = Field(default=NotificationSeverity.HIGH.value)

    # Ruhezeiten
    quiet_hours_enabled: bool = Field(default=False)
    quiet_hours_start: int = Field(default=22, ge=0, le=23)
    quiet_hours_end: int = Field(default=7, ge=0, le=23)
    quiet_hours_timezone: str = Field(default="Europe/Berlin")

    # Eskalations-Praeferenzen
    escalation_enabled: bool = Field(default=True)
    escalation_phone: Optional[str] = Field(default=None)

    @classmethod
    def from_user_preferences(cls, prefs: Optional[dict]) -> "UserNotificationPreferences":
        """Erstellt Praeferenzen aus User.preferences JSONB."""
        if not prefs:
            return cls()

        notification_prefs = prefs.get("notifications", {})
        return cls(**notification_prefs)


class ChannelDeliveryResult(BaseModel):
    """Ergebnis der Zustellung ueber einen Kanal."""

    channel: NotificationChannel
    status: DeliveryStatus
    message_id: Optional[str] = None
    error_message: Optional[str] = None
    retry_count: int = 0
    delivered_at: Optional[datetime] = None


class NotificationDeliveryResult(BaseModel):
    """Gesamtergebnis einer Benachrichtigung."""

    notification_id: UUID
    success: bool
    total_channels: int
    successful_channels: int
    failed_channels: int
    skipped_channels: int
    channel_results: list[ChannelDeliveryResult]
    deduplicated: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# =============================================================================
# Unified Notification Hub
# =============================================================================

class UnifiedNotificationHub:
    """
    Zentraler Notification Hub fuer alle Kanaele.

    Orchestriert:
    - Routing basierend auf Schweregrad und Praeferenzen
    - Deduplizierung von Benachrichtigungen
    - Delivery Tracking mit Retry
    - Eskalationsketten
    - Audit-Logging

    Verwendung:
        hub = UnifiedNotificationHub(session)
        result = await hub.send(
            recipients=[recipient],
            payload=NotificationPayload(
                notification_type="document_processed",
                title="Dokument verarbeitet",
                message="Ihre Rechnung wurde erfolgreich verarbeitet.",
                category=NotificationCategory.DOCUMENT,
                severity=NotificationSeverity.LOW,
            ),
        )
    """

    def __init__(
        self,
        session: Optional[AsyncSession] = None,
    ) -> None:
        """
        Initialisiert den Notification Hub.

        Args:
            session: SQLAlchemy AsyncSession (fuer DB-Operationen)
        """
        self.session = session

        # Lazy-loaded Service-Instanzen
        self._email_service: Optional[object] = None
        self._slack_service: Optional[object] = None
        self._teams_service: Optional[object] = None
        self._push_service: Optional[object] = None
        self._twilio_service: Optional[object] = None
        self._in_app_service: Optional[object] = None
        self._websocket_service: Optional[object] = None

        # Deduplizierungs-Cache (In-Memory, TTL-basiert)
        self._dedup_cache: dict[str, float] = {}
        self._dedup_lock = asyncio.Lock()

        # Delivery Tracking
        self._delivery_queue: deque = deque(maxlen=1000)

        logger.info("unified_notification_hub_initialized")

    # =========================================================================
    # Service Properties (Lazy Loading)
    # =========================================================================

    @property
    def email_service(self) -> object:
        """Lazy-Load Email Service."""
        if self._email_service is None:
            from app.services.notification_service import get_notification_service
            self._email_service = get_notification_service().email
        return self._email_service

    @property
    def slack_service(self) -> object:
        """Lazy-Load Slack Service."""
        if self._slack_service is None:
            from app.services.slack_service import get_slack_service
            self._slack_service = get_slack_service()
        return self._slack_service

    @property
    def teams_service(self) -> object:
        """Lazy-Load Teams Service."""
        if self._teams_service is None:
            from app.services.ms_teams_service import get_teams_service
            self._teams_service = get_teams_service()
        return self._teams_service

    @property
    def push_service(self) -> object:
        """Lazy-Load Push Service."""
        if self._push_service is None:
            from app.services.push_notification_service import PushNotificationService
            self._push_service = PushNotificationService(self.session)
        return self._push_service

    @property
    def twilio_service(self) -> object:
        """Lazy-Load Twilio Service."""
        if self._twilio_service is None:
            from app.services.twilio_service import get_twilio_service
            self._twilio_service = get_twilio_service()
        return self._twilio_service

    @property
    def in_app_service(self) -> object:
        """Lazy-Load In-App Notification Store."""
        if self._in_app_service is None:
            from app.services.notification_service import get_notification_service
            self._in_app_service = get_notification_service().in_app
        return self._in_app_service

    @property
    def websocket_service(self) -> object:
        """Lazy-Load WebSocket Manager."""
        if self._websocket_service is None:
            from app.services.notification_service import get_notification_ws_manager
            self._websocket_service = get_notification_ws_manager()
        return self._websocket_service

    # =========================================================================
    # User-Praeferenzen aus DB
    # =========================================================================

    async def _load_user_preferences(
        self,
        user_id: UUID,
    ) -> UserNotificationPreferences:
        """
        Laedt Benachrichtigungs-Praeferenzen aus der Datenbank.

        Konsolidiert NotificationPreference-Eintraege pro Typ in ein
        UserNotificationPreferences-Objekt. Faellt auf Defaults zurueck
        wenn keine Session vorhanden oder keine Eintraege existieren.
        """
        if self.session is None:
            return UserNotificationPreferences()

        try:
            from app.db.models import NotificationPreference

            stmt = select(NotificationPreference).where(
                NotificationPreference.user_id == user_id
            )
            result = await self.session.execute(stmt)
            rows = result.scalars().all()

            if not rows:
                return UserNotificationPreferences()

            # Kanal-Flags aus allen Typ-Eintraegen aggregieren
            # Ein Kanal gilt als aktiviert, wenn mindestens ein Typ ihn aktiviert hat
            channel_flags: Dict[str, bool] = {
                "email": False,
                "slack": False,
                "in_app": False,
                "sms": False,
                "websocket": False,
            }
            for row in rows:
                channels = row.enabled_channels or {}
                for channel, enabled in channels.items():
                    if enabled:
                        channel_flags[channel] = True

            return UserNotificationPreferences(
                email_enabled=channel_flags.get("email", True),
                slack_enabled=channel_flags.get("slack", False),
                in_app_enabled=channel_flags.get("in_app", True),
                sms_enabled=channel_flags.get("sms", False),
            )
        except Exception:
            logger.warning(
                "notification_preferences_load_failed",
                user_id=str(user_id),
                exc_info=True,
            )
            return UserNotificationPreferences()

    # =========================================================================
    # Deduplizierung
    # =========================================================================

    async def _is_duplicate(
        self,
        dedupe_key: str,
        ttl_seconds: int,
    ) -> bool:
        """
        Prueft ob Benachrichtigung ein Duplikat ist.

        Args:
            dedupe_key: Deduplizierungs-Schluessel
            ttl_seconds: Time-To-Live in Sekunden

        Returns:
            True wenn Duplikat
        """
        async with self._dedup_lock:
            now = time.time()

            # Alte Eintraege bereinigen
            expired_keys = [
                k for k, v in self._dedup_cache.items()
                if now > v
            ]
            for k in expired_keys:
                del self._dedup_cache[k]

            # Pruefen ob Key existiert
            if dedupe_key in self._dedup_cache:
                return True

            # Key hinzufuegen
            self._dedup_cache[dedupe_key] = now + ttl_seconds
            return False

    # =========================================================================
    # Kanal-Routing
    # =========================================================================

    def _determine_channels(
        self,
        payload: NotificationPayload,
        preferences: Optional[UserNotificationPreferences],
    ) -> list[NotificationChannel]:
        """
        Bestimmt Kanaele basierend auf Schweregrad und Praeferenzen.

        Args:
            payload: Benachrichtigungs-Payload
            preferences: Benutzer-Praeferenzen

        Returns:
            Liste der zu verwendenden Kanaele
        """
        # Standard-Kanaele fuer Schweregrad
        default_channels = DEFAULT_CHANNELS_BY_SEVERITY.get(
            payload.severity,
            [NotificationChannel.EMAIL, NotificationChannel.IN_APP]
        )

        if preferences is None:
            return default_channels

        if not preferences.enabled:
            return []

        # Nach Praeferenzen filtern
        filtered = []

        for channel in default_channels:
            # Kanal aktiviert?
            enabled_attr = f"{channel.value}_enabled"
            if hasattr(preferences, enabled_attr):
                if not getattr(preferences, enabled_attr):
                    continue

            # Kategorie erlaubt?
            categories_attr = f"{channel.value}_categories"
            if hasattr(preferences, categories_attr):
                allowed_categories = getattr(preferences, categories_attr)
                if payload.category.value not in allowed_categories:
                    continue

            # Minimum-Schweregrad erreicht?
            min_severity_attr = f"{channel.value}_min_severity"
            if hasattr(preferences, min_severity_attr):
                min_severity = getattr(preferences, min_severity_attr)
                severity_order = [s.value for s in NotificationSeverity]
                if severity_order.index(payload.severity.value) < severity_order.index(min_severity):
                    continue

            filtered.append(channel)

        return filtered

    def _is_quiet_hours(
        self,
        preferences: UserNotificationPreferences,
    ) -> bool:
        """Prueft ob aktuelle Zeit in Ruhezeiten faellt."""
        if not preferences.quiet_hours_enabled:
            return False

        try:
            import zoneinfo
            user_tz = zoneinfo.ZoneInfo(preferences.quiet_hours_timezone)
            user_now = datetime.now(user_tz)
            current_hour = user_now.hour

            start = preferences.quiet_hours_start
            end = preferences.quiet_hours_end

            if start <= end:
                return start <= current_hour < end
            else:
                return current_hour >= start or current_hour < end

        except Exception as e:
            logger.warning(
                "quiet_hours_check_failed",
                **safe_error_log(e),
            )
            return False

    # =========================================================================
    # Kanal-Versand
    # =========================================================================

    async def _send_email(
        self,
        recipient: NotificationRecipient,
        payload: NotificationPayload,
    ) -> ChannelDeliveryResult:
        """Sendet Email-Benachrichtigung."""
        if not recipient.email:
            return ChannelDeliveryResult(
                channel=NotificationChannel.EMAIL,
                status=DeliveryStatus.SKIPPED,
                error_message="Keine E-Mail-Adresse"
            )

        try:
            success = await self.email_service.send(
                to_email=recipient.email,
                subject=payload.title,
                body=payload.message,
            )

            return ChannelDeliveryResult(
                channel=NotificationChannel.EMAIL,
                status=DeliveryStatus.SENT if success else DeliveryStatus.FAILED,
                delivered_at=datetime.now(timezone.utc) if success else None,
            )

        except Exception as e:
            logger.error(
                "email_send_failed",
                user_id=str(recipient.user_id),
                **safe_error_log(e),
            )
            return ChannelDeliveryResult(
                channel=NotificationChannel.EMAIL,
                status=DeliveryStatus.FAILED,
                error_message=safe_error_detail(e, "Email")
            )

    async def _send_slack(
        self,
        recipient: NotificationRecipient,
        payload: NotificationPayload,
    ) -> ChannelDeliveryResult:
        """Sendet Slack-Benachrichtigung."""
        try:
            if not self.slack_service.is_enabled:
                return ChannelDeliveryResult(
                    channel=NotificationChannel.SLACK,
                    status=DeliveryStatus.SKIPPED,
                    error_message="Slack nicht konfiguriert"
                )

            success = await self.slack_service.send_notification(
                notification_type=payload.notification_type,
                title=payload.title,
                message=payload.message,
                context=payload.metadata,
                priority="high" if payload.severity in (
                    NotificationSeverity.HIGH,
                    NotificationSeverity.CRITICAL
                ) else "normal",
            )

            return ChannelDeliveryResult(
                channel=NotificationChannel.SLACK,
                status=DeliveryStatus.SENT if success else DeliveryStatus.FAILED,
                delivered_at=datetime.now(timezone.utc) if success else None,
            )

        except Exception as e:
            logger.error(
                "slack_send_failed",
                **safe_error_log(e),
            )
            return ChannelDeliveryResult(
                channel=NotificationChannel.SLACK,
                status=DeliveryStatus.FAILED,
                error_message=safe_error_detail(e, "Slack")
            )

    async def _send_teams(
        self,
        recipient: NotificationRecipient,
        payload: NotificationPayload,
    ) -> ChannelDeliveryResult:
        """Sendet Teams-Benachrichtigung."""
        try:
            if not self.teams_service.is_enabled:
                return ChannelDeliveryResult(
                    channel=NotificationChannel.TEAMS,
                    status=DeliveryStatus.SKIPPED,
                    error_message="Teams nicht konfiguriert"
                )

            success = await self.teams_service.send_notification(
                notification_type=payload.notification_type,
                title=payload.title,
                message=payload.message,
                context=payload.metadata,
                priority="high" if payload.severity in (
                    NotificationSeverity.HIGH,
                    NotificationSeverity.CRITICAL
                ) else "normal",
            )

            return ChannelDeliveryResult(
                channel=NotificationChannel.TEAMS,
                status=DeliveryStatus.SENT if success else DeliveryStatus.FAILED,
                delivered_at=datetime.now(timezone.utc) if success else None,
            )

        except Exception as e:
            logger.error(
                "teams_send_failed",
                **safe_error_log(e),
            )
            return ChannelDeliveryResult(
                channel=NotificationChannel.TEAMS,
                status=DeliveryStatus.FAILED,
                error_message=safe_error_detail(e, "Teams")
            )

    async def _send_push(
        self,
        recipient: NotificationRecipient,
        payload: NotificationPayload,
    ) -> ChannelDeliveryResult:
        """Sendet Push-Benachrichtigung."""
        try:
            from app.services.push_notification_service import (
                PushNotificationPayload,
                PushNotificationCategory,
                PushNotificationPriority,
            )

            # Kategorie mappen
            category_map = {
                NotificationCategory.DOCUMENT: PushNotificationCategory.DOCUMENT,
                NotificationCategory.ALERT: PushNotificationCategory.ALERT,
                NotificationCategory.WORKFLOW: PushNotificationCategory.WORKFLOW,
                NotificationCategory.SYSTEM: PushNotificationCategory.SYSTEM,
            }

            push_payload = PushNotificationPayload(
                title=payload.title,
                body=payload.message,
                category=category_map.get(
                    payload.category,
                    PushNotificationCategory.SYSTEM
                ),
                priority=PushNotificationPriority.HIGH if payload.severity in (
                    NotificationSeverity.HIGH,
                    NotificationSeverity.CRITICAL
                ) else PushNotificationPriority.NORMAL,
                url=payload.url,
                tag=f"{payload.notification_type}-{payload.reference_id or payload.notification_id}",
                data={
                    "notification_id": str(payload.notification_id),
                    "notification_type": payload.notification_type,
                    "reference_type": payload.reference_type,
                    "reference_id": payload.reference_id,
                    **payload.metadata,
                },
            )

            result = await self.push_service.send_to_user(
                user_id=recipient.user_id,
                payload=push_payload,
            )

            return ChannelDeliveryResult(
                channel=NotificationChannel.PUSH,
                status=DeliveryStatus.SENT if result.successful > 0 else DeliveryStatus.FAILED,
                delivered_at=datetime.now(timezone.utc) if result.successful > 0 else None,
                error_message=str(result.errors) if result.errors else None,
            )

        except Exception as e:
            logger.error(
                "push_send_failed",
                user_id=str(recipient.user_id),
                **safe_error_log(e),
            )
            return ChannelDeliveryResult(
                channel=NotificationChannel.PUSH,
                status=DeliveryStatus.FAILED,
                error_message=safe_error_detail(e, "Push")
            )

    async def _send_sms(
        self,
        recipient: NotificationRecipient,
        payload: NotificationPayload,
    ) -> ChannelDeliveryResult:
        """Sendet SMS-Benachrichtigung."""
        if not recipient.phone_number:
            return ChannelDeliveryResult(
                channel=NotificationChannel.SMS,
                status=DeliveryStatus.SKIPPED,
                error_message="Keine Telefonnummer"
            )

        try:
            if not self.twilio_service.is_enabled:
                return ChannelDeliveryResult(
                    channel=NotificationChannel.SMS,
                    status=DeliveryStatus.SKIPPED,
                    error_message="Twilio nicht konfiguriert"
                )

            # Kurznachricht verwenden wenn vorhanden
            message = payload.short_message or payload.message[:160]

            result = await self.twilio_service.send_critical_alert(
                phone_number=recipient.phone_number,
                title=payload.title,
                message=message,
                alert_code=payload.metadata.get("alert_code"),
                company_id=payload.company_id,
                user_id=recipient.user_id,
            )

            return ChannelDeliveryResult(
                channel=NotificationChannel.SMS,
                status=DeliveryStatus.SENT if result.success else DeliveryStatus.FAILED,
                message_id=result.message_sid,
                delivered_at=datetime.now(timezone.utc) if result.success else None,
                error_message=result.error_message,
            )

        except Exception as e:
            logger.error(
                "sms_send_failed",
                user_id=str(recipient.user_id),
                **safe_error_log(e),
            )
            return ChannelDeliveryResult(
                channel=NotificationChannel.SMS,
                status=DeliveryStatus.FAILED,
                error_message=safe_error_detail(e, "SMS")
            )

    async def _send_whatsapp(
        self,
        recipient: NotificationRecipient,
        payload: NotificationPayload,
    ) -> ChannelDeliveryResult:
        """Sendet WhatsApp-Benachrichtigung."""
        if not recipient.phone_number:
            return ChannelDeliveryResult(
                channel=NotificationChannel.WHATSAPP,
                status=DeliveryStatus.SKIPPED,
                error_message="Keine Telefonnummer"
            )

        try:
            if not self.twilio_service.is_enabled:
                return ChannelDeliveryResult(
                    channel=NotificationChannel.WHATSAPP,
                    status=DeliveryStatus.SKIPPED,
                    error_message="Twilio nicht konfiguriert"
                )

            result = await self.twilio_service.send_critical_alert(
                phone_number=recipient.phone_number,
                title=payload.title,
                message=payload.message,
                alert_code=payload.metadata.get("alert_code"),
                company_id=payload.company_id,
                user_id=recipient.user_id,
                use_whatsapp=True,
            )

            return ChannelDeliveryResult(
                channel=NotificationChannel.WHATSAPP,
                status=DeliveryStatus.SENT if result.success else DeliveryStatus.FAILED,
                message_id=result.message_sid,
                delivered_at=datetime.now(timezone.utc) if result.success else None,
                error_message=result.error_message,
            )

        except Exception as e:
            logger.error(
                "whatsapp_send_failed",
                user_id=str(recipient.user_id),
                **safe_error_log(e),
            )
            return ChannelDeliveryResult(
                channel=NotificationChannel.WHATSAPP,
                status=DeliveryStatus.FAILED,
                error_message=safe_error_detail(e, "WhatsApp")
            )

    async def _send_in_app(
        self,
        recipient: NotificationRecipient,
        payload: NotificationPayload,
    ) -> ChannelDeliveryResult:
        """Speichert In-App-Benachrichtigung."""
        try:
            notification_id = await self.in_app_service.store(
                user_id=str(recipient.user_id),
                notification={
                    "type": payload.notification_type,
                    "title": payload.title,
                    "message": payload.message,
                    "category": payload.category.value,
                    "severity": payload.severity.value,
                    "icon": payload.icon,
                    "color": payload.color,
                    "url": payload.url,
                    "reference_type": payload.reference_type,
                    "reference_id": payload.reference_id,
                    "metadata": payload.metadata,
                },
            )

            return ChannelDeliveryResult(
                channel=NotificationChannel.IN_APP,
                status=DeliveryStatus.SENT,
                message_id=notification_id,
                delivered_at=datetime.now(timezone.utc),
            )

        except Exception as e:
            logger.error(
                "in_app_store_failed",
                user_id=str(recipient.user_id),
                **safe_error_log(e),
            )
            return ChannelDeliveryResult(
                channel=NotificationChannel.IN_APP,
                status=DeliveryStatus.FAILED,
                error_message=safe_error_detail(e, "In-App")
            )

    async def _send_websocket(
        self,
        recipient: NotificationRecipient,
        payload: NotificationPayload,
    ) -> ChannelDeliveryResult:
        """Sendet WebSocket-Benachrichtigung."""
        try:
            if not self.websocket_service.is_user_connected(str(recipient.user_id)):
                return ChannelDeliveryResult(
                    channel=NotificationChannel.WEBSOCKET,
                    status=DeliveryStatus.SKIPPED,
                    error_message="Benutzer nicht verbunden"
                )

            message = {
                "type": "notification",
                "notification_id": str(payload.notification_id),
                "notification_type": payload.notification_type,
                "title": payload.title,
                "message": payload.message,
                "category": payload.category.value,
                "severity": payload.severity.value,
                "icon": payload.icon,
                "color": payload.color,
                "url": payload.url,
                "actions": [a.model_dump() for a in payload.actions],
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

            sent_count = await self.websocket_service.send_to_user(
                user_id=str(recipient.user_id),
                message=message,
            )

            return ChannelDeliveryResult(
                channel=NotificationChannel.WEBSOCKET,
                status=DeliveryStatus.SENT if sent_count > 0 else DeliveryStatus.FAILED,
                delivered_at=datetime.now(timezone.utc) if sent_count > 0 else None,
            )

        except Exception as e:
            logger.error(
                "websocket_send_failed",
                user_id=str(recipient.user_id),
                **safe_error_log(e),
            )
            return ChannelDeliveryResult(
                channel=NotificationChannel.WEBSOCKET,
                status=DeliveryStatus.FAILED,
                error_message=safe_error_detail(e, "WebSocket")
            )

    # =========================================================================
    # Haupt-Sendemethode
    # =========================================================================

    async def send(
        self,
        recipients: list[NotificationRecipient],
        payload: NotificationPayload,
        channels: Optional[list[NotificationChannel]] = None,
        preferences_override: Optional[UserNotificationPreferences] = None,
        skip_dedup: bool = False,
        skip_quiet_hours: bool = False,
    ) -> list[NotificationDeliveryResult]:
        """
        Sendet Benachrichtigung an mehrere Empfaenger.

        Args:
            recipients: Liste der Empfaenger
            payload: Benachrichtigungs-Payload
            channels: Optionale Kanal-Liste (ueberschreibt Routing)
            preferences_override: Praeferenzen-Override
            skip_dedup: Deduplizierung ueberspringen
            skip_quiet_hours: Ruhezeiten ignorieren

        Returns:
            Liste von Delivery-Ergebnissen pro Empfaenger
        """
        results = []

        for recipient in recipients:
            result = await self._send_to_recipient(
                recipient=recipient,
                payload=payload,
                channels=channels,
                preferences_override=preferences_override,
                skip_dedup=skip_dedup,
                skip_quiet_hours=skip_quiet_hours,
            )
            results.append(result)

        return results

    async def _send_to_recipient(
        self,
        recipient: NotificationRecipient,
        payload: NotificationPayload,
        channels: Optional[list[NotificationChannel]],
        preferences_override: Optional[UserNotificationPreferences],
        skip_dedup: bool,
        skip_quiet_hours: bool,
    ) -> NotificationDeliveryResult:
        """Sendet Benachrichtigung an einen einzelnen Empfaenger."""

        # Deduplizierung pruefen
        if not skip_dedup:
            dedupe_key = f"{recipient.user_id}:{payload.generate_dedupe_key()}"
            ttl = payload.ttl_seconds or DEDUP_TTL_BY_SEVERITY.get(
                payload.severity, 900
            )

            if await self._is_duplicate(dedupe_key, ttl):
                logger.debug(
                    "notification_deduplicated",
                    notification_id=str(payload.notification_id),
                    user_id=str(recipient.user_id),
                )
                return NotificationDeliveryResult(
                    notification_id=payload.notification_id,
                    success=True,
                    total_channels=0,
                    successful_channels=0,
                    failed_channels=0,
                    skipped_channels=0,
                    channel_results=[],
                    deduplicated=True,
                )

        # Praeferenzen laden oder Override verwenden
        preferences = preferences_override
        if preferences is None:
            preferences = await self._load_user_preferences(recipient.user_id)

        # Ruhezeiten pruefen
        if not skip_quiet_hours and self._is_quiet_hours(preferences):
            # Bei kritischen Alerts trotzdem senden
            if payload.severity != NotificationSeverity.CRITICAL:
                logger.debug(
                    "notification_skipped_quiet_hours",
                    notification_id=str(payload.notification_id),
                    user_id=str(recipient.user_id),
                )
                return NotificationDeliveryResult(
                    notification_id=payload.notification_id,
                    success=False,
                    total_channels=0,
                    successful_channels=0,
                    failed_channels=0,
                    skipped_channels=1,
                    channel_results=[
                        ChannelDeliveryResult(
                            channel=NotificationChannel.EMAIL,
                            status=DeliveryStatus.SKIPPED,
                            error_message="Ruhezeiten aktiv",
                        )
                    ],
                )

        # Kanaele bestimmen
        target_channels = channels or self._determine_channels(payload, preferences)

        if not target_channels:
            return NotificationDeliveryResult(
                notification_id=payload.notification_id,
                success=False,
                total_channels=0,
                successful_channels=0,
                failed_channels=0,
                skipped_channels=0,
                channel_results=[],
            )

        # An alle Kanaele senden (parallel)
        channel_tasks = []
        for channel in target_channels:
            task = self._send_to_channel(channel, recipient, payload)
            channel_tasks.append(task)

        channel_results = await asyncio.gather(*channel_tasks)

        # Ergebnis zusammenstellen
        successful = sum(
            1 for r in channel_results
            if r.status == DeliveryStatus.SENT
        )
        failed = sum(
            1 for r in channel_results
            if r.status == DeliveryStatus.FAILED
        )
        skipped = sum(
            1 for r in channel_results
            if r.status == DeliveryStatus.SKIPPED
        )

        result = NotificationDeliveryResult(
            notification_id=payload.notification_id,
            success=successful > 0,
            total_channels=len(target_channels),
            successful_channels=successful,
            failed_channels=failed,
            skipped_channels=skipped,
            channel_results=list(channel_results),
        )

        # Audit-Log
        logger.info(
            "notification_sent",
            notification_id=str(payload.notification_id),
            user_id=str(recipient.user_id),
            notification_type=payload.notification_type,
            severity=payload.severity.value,
            channels=[c.value for c in target_channels],
            successful=successful,
            failed=failed,
        )

        return result

    async def _send_to_channel(
        self,
        channel: NotificationChannel,
        recipient: NotificationRecipient,
        payload: NotificationPayload,
    ) -> ChannelDeliveryResult:
        """Sendet an einen spezifischen Kanal."""
        sender_map = {
            NotificationChannel.EMAIL: self._send_email,
            NotificationChannel.SLACK: self._send_slack,
            NotificationChannel.TEAMS: self._send_teams,
            NotificationChannel.PUSH: self._send_push,
            NotificationChannel.SMS: self._send_sms,
            NotificationChannel.WHATSAPP: self._send_whatsapp,
            NotificationChannel.IN_APP: self._send_in_app,
            NotificationChannel.WEBSOCKET: self._send_websocket,
        }

        sender = sender_map.get(channel)
        if sender is None:
            return ChannelDeliveryResult(
                channel=channel,
                status=DeliveryStatus.SKIPPED,
                error_message=f"Kanal '{channel}' nicht unterstuetzt"
            )

        return await sender(recipient, payload)

    # =========================================================================
    # Eskalation
    # =========================================================================

    async def escalate(
        self,
        original_notification_id: UUID,
        recipient: NotificationRecipient,
        payload: NotificationPayload,
        escalation_level: EscalationLevel,
        reason: str = "Keine Reaktion",
    ) -> NotificationDeliveryResult:
        """
        Eskaliert eine Benachrichtigung.

        Args:
            original_notification_id: Urspruengliche Benachrichtigungs-ID
            recipient: Empfaenger
            payload: Benachrichtigungs-Payload
            escalation_level: Eskalationsstufe
            reason: Grund der Eskalation

        Returns:
            Delivery-Ergebnis
        """
        # Eskalations-Kanaele basierend auf Level
        escalation_channels = {
            EscalationLevel.LEVEL_1: [
                NotificationChannel.EMAIL,
                NotificationChannel.SLACK,
            ],
            EscalationLevel.LEVEL_2: [
                NotificationChannel.EMAIL,
                NotificationChannel.SLACK,
                NotificationChannel.TEAMS,
            ],
            EscalationLevel.LEVEL_3: [
                NotificationChannel.EMAIL,
                NotificationChannel.SLACK,
                NotificationChannel.TEAMS,
                NotificationChannel.PUSH,
            ],
            EscalationLevel.LEVEL_4: [
                NotificationChannel.EMAIL,
                NotificationChannel.SLACK,
                NotificationChannel.TEAMS,
                NotificationChannel.PUSH,
                NotificationChannel.SMS,
            ],
            EscalationLevel.LEVEL_5: [
                NotificationChannel.EMAIL,
                NotificationChannel.SLACK,
                NotificationChannel.TEAMS,
                NotificationChannel.PUSH,
                NotificationChannel.SMS,
                NotificationChannel.WHATSAPP,
            ],
        }

        channels = escalation_channels.get(
            escalation_level,
            [NotificationChannel.EMAIL]
        )

        # Payload anpassen
        escalated_payload = payload.model_copy()
        escalated_payload.title = f"[ESKALATION {escalation_level.value}] {payload.title}"
        escalated_payload.metadata["escalation_level"] = escalation_level.value
        escalated_payload.metadata["escalation_reason"] = reason
        escalated_payload.metadata["original_notification_id"] = str(original_notification_id)
        escalated_payload.severity = NotificationSeverity.CRITICAL

        logger.warning(
            "notification_escalated",
            original_notification_id=str(original_notification_id),
            escalation_level=escalation_level.value,
            reason=reason,
            user_id=str(recipient.user_id),
        )

        return await self._send_to_recipient(
            recipient=recipient,
            payload=escalated_payload,
            channels=channels,
            preferences_override=None,
            skip_dedup=True,  # Eskalation nicht deduplizieren
            skip_quiet_hours=True,  # Ruhezeiten ignorieren
        )

    # =========================================================================
    # Convenience-Methoden
    # =========================================================================

    async def send_document_notification(
        self,
        user_id: UUID,
        user_email: str,
        document_id: UUID,
        title: str,
        message: str,
        company_id: Optional[UUID] = None,
    ) -> NotificationDeliveryResult:
        """Sendet Dokument-bezogene Benachrichtigung."""
        recipient = NotificationRecipient(
            user_id=user_id,
            email=user_email,
        )

        payload = NotificationPayload(
            notification_type="document_processed",
            title=title,
            message=message,
            category=NotificationCategory.DOCUMENT,
            severity=NotificationSeverity.LOW,
            company_id=company_id,
            reference_type="document",
            reference_id=str(document_id),
            url=f"/documents/{document_id}",
        )

        results = await self.send([recipient], payload)
        return results[0] if results else NotificationDeliveryResult(
            notification_id=payload.notification_id,
            success=False,
            total_channels=0,
            successful_channels=0,
            failed_channels=0,
            skipped_channels=0,
            channel_results=[],
        )

    async def send_alert_notification(
        self,
        user_id: UUID,
        user_email: str,
        alert_id: UUID,
        alert_code: str,
        title: str,
        message: str,
        severity: NotificationSeverity,
        company_id: Optional[UUID] = None,
        phone_number: Optional[str] = None,
    ) -> NotificationDeliveryResult:
        """Sendet Alert-Benachrichtigung."""
        recipient = NotificationRecipient(
            user_id=user_id,
            email=user_email,
            phone_number=phone_number,
        )

        payload = NotificationPayload(
            notification_type="alert",
            title=title,
            message=message,
            short_message=f"{title}: {message[:100]}...",
            category=NotificationCategory.ALERT,
            severity=severity,
            company_id=company_id,
            reference_type="alert",
            reference_id=str(alert_id),
            url=f"/alerts/{alert_id}",
            metadata={"alert_code": alert_code},
        )

        results = await self.send([recipient], payload)
        return results[0] if results else NotificationDeliveryResult(
            notification_id=payload.notification_id,
            success=False,
            total_channels=0,
            successful_channels=0,
            failed_channels=0,
            skipped_channels=0,
            channel_results=[],
        )

    async def send_workflow_notification(
        self,
        user_id: UUID,
        user_email: str,
        workflow_id: UUID,
        title: str,
        message: str,
        actions: Optional[list[NotificationAction]] = None,
        company_id: Optional[UUID] = None,
    ) -> NotificationDeliveryResult:
        """Sendet Workflow-Benachrichtigung."""
        recipient = NotificationRecipient(
            user_id=user_id,
            email=user_email,
        )

        payload = NotificationPayload(
            notification_type="workflow_action_required",
            title=title,
            message=message,
            category=NotificationCategory.WORKFLOW,
            severity=NotificationSeverity.MEDIUM,
            company_id=company_id,
            reference_type="workflow",
            reference_id=str(workflow_id),
            url=f"/workflows/{workflow_id}",
            actions=actions or [
                NotificationAction(
                    action_id="approve",
                    title="Genehmigen",
                    style="primary"
                ),
                NotificationAction(
                    action_id="reject",
                    title="Ablehnen",
                    style="danger"
                ),
            ],
        )

        results = await self.send([recipient], payload)
        return results[0] if results else NotificationDeliveryResult(
            notification_id=payload.notification_id,
            success=False,
            total_channels=0,
            successful_channels=0,
            failed_channels=0,
            skipped_channels=0,
            channel_results=[],
        )


# =============================================================================
# Factory Functions
# =============================================================================

_unified_hub: Optional[UnifiedNotificationHub] = None


def get_unified_notification_hub(
    session: Optional[AsyncSession] = None,
) -> UnifiedNotificationHub:
    """
    Factory-Funktion fuer Unified Notification Hub.

    Args:
        session: SQLAlchemy AsyncSession

    Returns:
        UnifiedNotificationHub Instanz
    """
    global _unified_hub
    if _unified_hub is None:
        _unified_hub = UnifiedNotificationHub(session)
    elif session is not None:
        _unified_hub.session = session
    return _unified_hub


async def send_notification(
    recipient_user_id: UUID,
    recipient_email: str,
    notification_type: str,
    title: str,
    message: str,
    category: NotificationCategory = NotificationCategory.SYSTEM,
    severity: NotificationSeverity = NotificationSeverity.MEDIUM,
    company_id: Optional[UUID] = None,
    reference_type: Optional[str] = None,
    reference_id: Optional[str] = None,
    url: Optional[str] = None,
    phone_number: Optional[str] = None,
    session: Optional[AsyncSession] = None,
) -> NotificationDeliveryResult:
    """
    Convenience-Funktion fuer einfaches Senden von Benachrichtigungen.

    Args:
        recipient_user_id: Benutzer-ID
        recipient_email: E-Mail-Adresse
        notification_type: Typ der Benachrichtigung
        title: Titel
        message: Nachricht
        category: Kategorie
        severity: Schweregrad
        company_id: Mandanten-ID
        reference_type: Referenz-Typ
        reference_id: Referenz-ID
        url: URL bei Klick
        phone_number: Telefonnummer fuer SMS
        session: Datenbank-Session

    Returns:
        Delivery-Ergebnis
    """
    hub = get_unified_notification_hub(session)

    recipient = NotificationRecipient(
        user_id=recipient_user_id,
        email=recipient_email,
        phone_number=phone_number,
    )

    payload = NotificationPayload(
        notification_type=notification_type,
        title=title,
        message=message,
        category=category,
        severity=severity,
        company_id=company_id,
        reference_type=reference_type,
        reference_id=reference_id,
        url=url,
    )

    results = await hub.send([recipient], payload)
    return results[0] if results else NotificationDeliveryResult(
        notification_id=payload.notification_id,
        success=False,
        total_channels=0,
        successful_channels=0,
        failed_channels=0,
        skipped_channels=0,
        channel_results=[],
    )
