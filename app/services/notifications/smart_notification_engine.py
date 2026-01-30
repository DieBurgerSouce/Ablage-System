# -*- coding: utf-8 -*-
"""
Smart Notification Engine.

Vision 2026 Q3: Intelligentes Benachrichtigungssystem mit KI-Filterung.

Features:
- Noise-Filterung (aehnliche Events zusammenfassen)
- Prioritaets-basierte Benachrichtigung
- Kontext-Beruecksichtigung (Arbeitszeit, letzte Aktivitaet)
- Multi-Channel Delivery (In-App, Email, Push, Slack)
- User-Praeferenzen

Feinpoliert und durchdacht - Deutsche Qualitaet.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Set

import structlog
from prometheus_client import Counter, Histogram

logger = structlog.get_logger(__name__)


# =============================================================================
# Prometheus Metriken
# =============================================================================

NOTIFICATION_DECISIONS = Counter(
    "smart_notification_decisions_total",
    "Benachrichtigungs-Entscheidungen",
    ["decision", "reason"]
)

NOTIFICATION_DELIVERED = Counter(
    "smart_notifications_delivered_total",
    "Zugestellte Benachrichtigungen",
    ["channel", "priority"]
)

NOTIFICATION_FILTERED = Counter(
    "smart_notifications_filtered_total",
    "Gefilterte Benachrichtigungen",
    ["filter_reason"]
)


# =============================================================================
# Enums
# =============================================================================

class NotificationChannel(str, Enum):
    """Verfuegbare Benachrichtigungskanaele."""
    IN_APP = "in_app"
    EMAIL = "email"
    PUSH = "push"
    SLACK = "slack"


class NotificationPriority(str, Enum):
    """Prioritaet einer Benachrichtigung."""
    CRITICAL = "critical"  # Sofort, alle Kanaele
    HIGH = "high"          # Sofort, In-App + Email
    MEDIUM = "medium"      # Normal, In-App
    LOW = "low"            # Gebuendelt, In-App
    INFO = "info"          # Optional, nur wenn gewuenscht


class EventCategory(str, Enum):
    """Kategorien von Events."""
    DOCUMENT = "document"          # Dokument-Events
    INVOICE = "invoice"            # Rechnungs-Events
    PAYMENT = "payment"            # Zahlungs-Events
    APPROVAL = "approval"          # Genehmigungen
    ANOMALY = "anomaly"            # Anomalie-Warnungen
    SYSTEM = "system"              # System-Events
    DEADLINE = "deadline"          # Fristen
    WORKFLOW = "workflow"          # Workflow-Events


class FilterReason(str, Enum):
    """Grund fuer das Filtern einer Benachrichtigung."""
    NOISE = "noise"                    # Aehnliches Event kuerzlich
    LOW_IMPORTANCE = "low_importance"  # Unter User-Schwelle
    QUIET_HOURS = "quiet_hours"        # Ruhezeit
    DISABLED_CHANNEL = "disabled"      # Kanal deaktiviert
    RATE_LIMITED = "rate_limited"      # Zu viele Benachrichtigungen


# =============================================================================
# Datenstrukturen
# =============================================================================

@dataclass
class NotificationEvent:
    """Ein zu benachrichtigendes Event."""
    event_id: str
    event_type: str
    category: EventCategory
    title: str
    message: str
    priority: NotificationPriority
    user_id: uuid.UUID
    company_id: uuid.UUID
    document_id: Optional[uuid.UUID] = None
    entity_id: Optional[uuid.UUID] = None
    data: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class UserNotificationPreferences:
    """Benachrichtigungs-Praeferenzen eines Users."""
    user_id: uuid.UUID
    enabled_channels: Set[NotificationChannel]
    min_priority: NotificationPriority
    quiet_hours_start: Optional[time]
    quiet_hours_end: Optional[time]
    email_digest: bool  # Emails zusammenfassen
    email_digest_frequency: str  # "daily", "weekly"
    disabled_categories: Set[EventCategory]
    slack_channel: Optional[str]


@dataclass
class UserContext:
    """Kontext eines Users fuer intelligente Filterung."""
    user_id: uuid.UUID
    is_online: bool
    last_activity: Optional[datetime]
    current_page: Optional[str]
    recent_notifications_count: int  # Letzten 15 Minuten
    unread_notifications_count: int


@dataclass
class NotificationDecision:
    """Entscheidung ob und wie benachrichtigt werden soll."""
    should_notify: bool
    channels: List[NotificationChannel]
    priority: NotificationPriority
    reason: str
    explanation: str
    delay_until: Optional[datetime] = None
    bundle_with: Optional[str] = None  # ID fuer Buendelung


@dataclass
class DeliveredNotification:
    """Eine zugestellte Benachrichtigung."""
    notification_id: str
    event_id: str
    user_id: uuid.UUID
    channels: List[NotificationChannel]
    priority: NotificationPriority
    delivered_at: datetime
    read_at: Optional[datetime] = None


# =============================================================================
# Importance Calculation
# =============================================================================

# Basis-Wichtigkeit pro Event-Typ (1-10)
EVENT_TYPE_IMPORTANCE: Dict[str, int] = {
    # Kritisch
    "fraud_detected": 10,
    "system_down": 10,
    "security_breach": 10,

    # Hoch
    "approval_required": 8,
    "payment_overdue": 8,
    "anomaly_critical": 8,
    "deadline_tomorrow": 8,

    # Mittel
    "document_processed": 5,
    "invoice_received": 5,
    "payment_received": 6,
    "workflow_step": 5,
    "skonto_deadline": 6,

    # Niedrig
    "document_uploaded": 3,
    "ocr_completed": 3,
    "entity_updated": 3,
    "comment_added": 4,

    # Info
    "report_generated": 2,
    "backup_completed": 2,
    "maintenance_scheduled": 2,
}

# Kontext-Modifikatoren
CONTEXT_MODIFIERS: Dict[str, float] = {
    "user_online": 0.8,           # Weniger dringend wenn online
    "user_offline_1h": 1.2,       # Dringender wenn laenger offline
    "user_offline_24h": 1.5,      # Noch dringender
    "on_related_page": 0.7,       # Weniger wichtig wenn schon dort
    "many_unread": 0.9,           # Leicht weniger wenn viele ungelesen
    "recent_similar": 0.5,        # Stark reduziert wenn aehnliches kuerzlich
}

# Priority-Schwellenwerte
PRIORITY_THRESHOLDS = {
    NotificationPriority.CRITICAL: 9,
    NotificationPriority.HIGH: 7,
    NotificationPriority.MEDIUM: 5,
    NotificationPriority.LOW: 3,
    NotificationPriority.INFO: 0,
}


class SmartNotificationEngine:
    """
    Intelligentes Benachrichtigungssystem.

    Entscheidet basierend auf:
    - Event-Wichtigkeit
    - User-Praeferenzen
    - Aktuellem Kontext
    - Noise-Filterung
    """

    def __init__(self) -> None:
        """Initialisiert die Engine."""
        # Caches
        self._preferences_cache: Dict[uuid.UUID, UserNotificationPreferences] = {}
        self._recent_events: Dict[uuid.UUID, List[NotificationEvent]] = {}
        self._delivered: Dict[str, DeliveredNotification] = {}

        # Konfiguration
        self._noise_window_minutes = 15
        self._rate_limit_per_15min = 10
        self._digest_events: Dict[uuid.UUID, List[NotificationEvent]] = {}

    async def should_notify(
        self,
        event: NotificationEvent,
        preferences: Optional[UserNotificationPreferences] = None,
        context: Optional[UserContext] = None,
    ) -> NotificationDecision:
        """
        Entscheidet ob und wie eine Benachrichtigung gesendet werden soll.

        Args:
            event: Das Event
            preferences: User-Praeferenzen (oder aus Cache)
            context: User-Kontext (oder Default)

        Returns:
            NotificationDecision
        """
        # Praeferenzen laden
        if preferences is None:
            preferences = self._get_default_preferences(event.user_id)

        # Kontext laden
        if context is None:
            context = self._get_default_context(event.user_id)

        # 1. Basis-Wichtigkeit berechnen
        base_importance = self._calculate_base_importance(event)

        # 2. Kontext-Modifikatoren anwenden
        modified_importance = self._apply_context_modifiers(
            base_importance, event, context
        )

        # 3. Noise-Check
        is_noise, noise_reason = self._check_noise(event, context)
        if is_noise:
            NOTIFICATION_FILTERED.labels(filter_reason=FilterReason.NOISE.value).inc()
            return NotificationDecision(
                should_notify=False,
                channels=[],
                priority=event.priority,
                reason=FilterReason.NOISE.value,
                explanation=noise_reason,
            )

        # 4. Kategorie-Check
        if event.category in preferences.disabled_categories:
            NOTIFICATION_FILTERED.labels(filter_reason=FilterReason.DISABLED_CHANNEL.value).inc()
            return NotificationDecision(
                should_notify=False,
                channels=[],
                priority=event.priority,
                reason=FilterReason.DISABLED_CHANNEL.value,
                explanation=f"Kategorie '{event.category.value}' ist deaktiviert",
            )

        # 5. Prioritaet bestimmen
        effective_priority = self._determine_priority(modified_importance)

        # 6. Priority-Schwelle pruefen
        priority_order = [p for p in NotificationPriority]
        if priority_order.index(effective_priority) > priority_order.index(preferences.min_priority):
            NOTIFICATION_FILTERED.labels(filter_reason=FilterReason.LOW_IMPORTANCE.value).inc()
            return NotificationDecision(
                should_notify=False,
                channels=[],
                priority=effective_priority,
                reason=FilterReason.LOW_IMPORTANCE.value,
                explanation=f"Wichtigkeit {modified_importance:.1f} unter Schwelle",
            )

        # 7. Ruhezeit-Check
        if self._is_quiet_hours(preferences):
            if effective_priority not in (NotificationPriority.CRITICAL, NotificationPriority.HIGH):
                NOTIFICATION_FILTERED.labels(filter_reason=FilterReason.QUIET_HOURS.value).inc()

                # Berechne Ende der Ruhezeit
                delay_until = self._calculate_quiet_hours_end(preferences)

                return NotificationDecision(
                    should_notify=True,  # Spaeter senden
                    channels=[NotificationChannel.IN_APP],  # Nur In-App
                    priority=effective_priority,
                    reason=FilterReason.QUIET_HOURS.value,
                    explanation="Ruhezeit - Benachrichtigung wird verzoegert",
                    delay_until=delay_until,
                )

        # 8. Rate-Limit-Check
        if context.recent_notifications_count >= self._rate_limit_per_15min:
            if effective_priority not in (NotificationPriority.CRITICAL,):
                NOTIFICATION_FILTERED.labels(filter_reason=FilterReason.RATE_LIMITED.value).inc()
                return NotificationDecision(
                    should_notify=False,
                    channels=[],
                    priority=effective_priority,
                    reason=FilterReason.RATE_LIMITED.value,
                    explanation=f"Rate-Limit erreicht ({self._rate_limit_per_15min}/15min)",
                )

        # 9. Kanaele bestimmen
        channels = self._select_channels(
            effective_priority, preferences, context
        )

        # 10. Event in Recent-Liste speichern
        self._add_to_recent_events(event)

        NOTIFICATION_DECISIONS.labels(
            decision="notify",
            reason="passed_all_checks",
        ).inc()

        return NotificationDecision(
            should_notify=True,
            channels=channels,
            priority=effective_priority,
            reason="passed_all_checks",
            explanation=self._generate_explanation(
                event, modified_importance, effective_priority, channels
            ),
        )

    async def deliver_notification(
        self,
        event: NotificationEvent,
        decision: NotificationDecision,
    ) -> DeliveredNotification:
        """
        Stellt eine Benachrichtigung zu.

        Args:
            event: Das Event
            decision: Die Entscheidung

        Returns:
            DeliveredNotification
        """
        notification_id = str(uuid.uuid4())

        # Zustellung simulieren (in Produktion: echte Delivery)
        for channel in decision.channels:
            NOTIFICATION_DELIVERED.labels(
                channel=channel.value,
                priority=decision.priority.value,
            ).inc()

            logger.info(
                "notification_delivered",
                notification_id=notification_id,
                event_type=event.event_type,
                user_id=str(event.user_id),
                channel=channel.value,
                priority=decision.priority.value,
            )

        delivered = DeliveredNotification(
            notification_id=notification_id,
            event_id=event.event_id,
            user_id=event.user_id,
            channels=decision.channels,
            priority=decision.priority,
            delivered_at=datetime.now(timezone.utc),
        )

        self._delivered[notification_id] = delivered

        return delivered

    async def add_to_digest(
        self,
        event: NotificationEvent,
    ) -> None:
        """
        Fuegt ein Event zum Digest hinzu (fuer gebuendelte Zustellung).

        Args:
            event: Das Event
        """
        if event.user_id not in self._digest_events:
            self._digest_events[event.user_id] = []

        self._digest_events[event.user_id].append(event)

        logger.debug(
            "event_added_to_digest",
            event_type=event.event_type,
            user_id=str(event.user_id),
            digest_count=len(self._digest_events[event.user_id]),
        )

    async def get_digest(
        self,
        user_id: uuid.UUID,
        clear: bool = True,
    ) -> List[NotificationEvent]:
        """
        Gibt den gesammelten Digest zurueck.

        Args:
            user_id: User-ID
            clear: Digest nach Abruf leeren

        Returns:
            Liste der Events im Digest
        """
        events = self._digest_events.get(user_id, [])

        if clear and user_id in self._digest_events:
            del self._digest_events[user_id]

        return events

    # =========================================================================
    # PRIVATE METHODS
    # =========================================================================

    def _calculate_base_importance(self, event: NotificationEvent) -> float:
        """Berechnet die Basis-Wichtigkeit."""
        # Event-Typ Wichtigkeit
        base = EVENT_TYPE_IMPORTANCE.get(event.event_type, 5)

        # Priority-Boost
        priority_boost = {
            NotificationPriority.CRITICAL: 2,
            NotificationPriority.HIGH: 1,
            NotificationPriority.MEDIUM: 0,
            NotificationPriority.LOW: -1,
            NotificationPriority.INFO: -2,
        }
        base += priority_boost.get(event.priority, 0)

        return float(min(10, max(1, base)))

    def _apply_context_modifiers(
        self,
        base_importance: float,
        event: NotificationEvent,
        context: UserContext,
    ) -> float:
        """Wendet Kontext-Modifikatoren an."""
        modified = base_importance

        # Online-Status
        if context.is_online:
            modified *= CONTEXT_MODIFIERS["user_online"]
        elif context.last_activity:
            hours_offline = (datetime.now(timezone.utc) - context.last_activity).total_seconds() / 3600
            if hours_offline > 24:
                modified *= CONTEXT_MODIFIERS["user_offline_24h"]
            elif hours_offline > 1:
                modified *= CONTEXT_MODIFIERS["user_offline_1h"]

        # Auf verwandter Seite
        if context.current_page and event.document_id:
            if str(event.document_id) in (context.current_page or ""):
                modified *= CONTEXT_MODIFIERS["on_related_page"]

        # Viele ungelesene
        if context.unread_notifications_count > 10:
            modified *= CONTEXT_MODIFIERS["many_unread"]

        # Aehnliches Event kuerzlich
        recent = self._recent_events.get(event.user_id, [])
        similar = [
            e for e in recent
            if e.event_type == event.event_type
            and (datetime.now(timezone.utc) - e.created_at).total_seconds() < self._noise_window_minutes * 60
        ]
        if similar:
            modified *= CONTEXT_MODIFIERS["recent_similar"]

        return modified

    def _check_noise(
        self,
        event: NotificationEvent,
        context: UserContext,
    ) -> tuple[bool, str]:
        """Prueft ob das Event Noise ist."""
        recent = self._recent_events.get(event.user_id, [])
        window = datetime.now(timezone.utc) - timedelta(minutes=self._noise_window_minutes)

        # Exakt gleiches Event (gleicher Typ + gleiches Dokument)
        for recent_event in recent:
            if recent_event.created_at < window:
                continue

            if (
                recent_event.event_type == event.event_type
                and recent_event.document_id == event.document_id
            ):
                return True, f"Gleiches Event '{event.event_type}' fuer gleiches Dokument in letzten {self._noise_window_minutes} Minuten"

        # Zu viele Events gleichen Typs
        same_type_count = len([
            e for e in recent
            if e.event_type == event.event_type and e.created_at >= window
        ])
        if same_type_count >= 5:
            return True, f"Mehr als 5 Events vom Typ '{event.event_type}' in letzten {self._noise_window_minutes} Minuten"

        return False, ""

    def _determine_priority(self, importance: float) -> NotificationPriority:
        """Bestimmt die Prioritaet basierend auf Wichtigkeit."""
        for priority, threshold in PRIORITY_THRESHOLDS.items():
            if importance >= threshold:
                return priority
        return NotificationPriority.INFO

    def _is_quiet_hours(self, preferences: UserNotificationPreferences) -> bool:
        """Prueft ob Ruhezeit ist."""
        if not preferences.quiet_hours_start or not preferences.quiet_hours_end:
            return False

        now = datetime.now(timezone.utc).time()
        start = preferences.quiet_hours_start
        end = preferences.quiet_hours_end

        if start <= end:
            return start <= now <= end
        else:
            # Ueber Mitternacht
            return now >= start or now <= end

    def _calculate_quiet_hours_end(
        self,
        preferences: UserNotificationPreferences,
    ) -> datetime:
        """Berechnet das Ende der Ruhezeit."""
        now = datetime.now(timezone.utc)
        end_time = preferences.quiet_hours_end or time(8, 0)

        end_dt = datetime.combine(now.date(), end_time, tzinfo=timezone.utc)

        if end_dt <= now:
            end_dt += timedelta(days=1)

        return end_dt

    def _select_channels(
        self,
        priority: NotificationPriority,
        preferences: UserNotificationPreferences,
        context: UserContext,
    ) -> List[NotificationChannel]:
        """Waehlt die Zustellungskanaele."""
        channels: List[NotificationChannel] = []

        # In-App immer (wenn aktiviert)
        if NotificationChannel.IN_APP in preferences.enabled_channels:
            channels.append(NotificationChannel.IN_APP)

        # Email bei hoher Prioritaet oder offline
        if (
            NotificationChannel.EMAIL in preferences.enabled_channels
            and (
                priority in (NotificationPriority.CRITICAL, NotificationPriority.HIGH)
                or not context.is_online
            )
        ):
            if not preferences.email_digest:
                channels.append(NotificationChannel.EMAIL)

        # Push bei kritisch oder hoch
        if (
            NotificationChannel.PUSH in preferences.enabled_channels
            and priority in (NotificationPriority.CRITICAL, NotificationPriority.HIGH)
        ):
            channels.append(NotificationChannel.PUSH)

        # Slack bei kritisch
        if (
            NotificationChannel.SLACK in preferences.enabled_channels
            and preferences.slack_channel
            and priority == NotificationPriority.CRITICAL
        ):
            channels.append(NotificationChannel.SLACK)

        return channels

    def _add_to_recent_events(self, event: NotificationEvent) -> None:
        """Fuegt Event zur Recent-Liste hinzu."""
        if event.user_id not in self._recent_events:
            self._recent_events[event.user_id] = []

        self._recent_events[event.user_id].append(event)

        # Alte Events entfernen
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=self._noise_window_minutes * 2)
        self._recent_events[event.user_id] = [
            e for e in self._recent_events[event.user_id]
            if e.created_at >= cutoff
        ]

    def _generate_explanation(
        self,
        event: NotificationEvent,
        importance: float,
        priority: NotificationPriority,
        channels: List[NotificationChannel],
    ) -> str:
        """Generiert eine Erklaerung fuer die Entscheidung."""
        channel_names = [c.value for c in channels]

        return (
            f"Event '{event.event_type}' mit Wichtigkeit {importance:.1f} "
            f"wird mit Prioritaet '{priority.value}' "
            f"ueber {', '.join(channel_names)} zugestellt."
        )

    def _get_default_preferences(
        self,
        user_id: uuid.UUID,
    ) -> UserNotificationPreferences:
        """Gibt Default-Praeferenzen zurueck."""
        if user_id in self._preferences_cache:
            return self._preferences_cache[user_id]

        return UserNotificationPreferences(
            user_id=user_id,
            enabled_channels={NotificationChannel.IN_APP, NotificationChannel.EMAIL},
            min_priority=NotificationPriority.LOW,
            quiet_hours_start=time(22, 0),
            quiet_hours_end=time(7, 0),
            email_digest=True,
            email_digest_frequency="daily",
            disabled_categories=set(),
            slack_channel=None,
        )

    def _get_default_context(
        self,
        user_id: uuid.UUID,
    ) -> UserContext:
        """Gibt Default-Kontext zurueck."""
        return UserContext(
            user_id=user_id,
            is_online=False,
            last_activity=None,
            current_page=None,
            recent_notifications_count=0,
            unread_notifications_count=0,
        )


# =============================================================================
# Factory
# =============================================================================

_smart_notification_engine: Optional[SmartNotificationEngine] = None


def get_smart_notification_engine() -> SmartNotificationEngine:
    """Factory fuer SmartNotificationEngine Singleton."""
    global _smart_notification_engine
    if _smart_notification_engine is None:
        _smart_notification_engine = SmartNotificationEngine()
    return _smart_notification_engine
