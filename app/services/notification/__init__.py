"""Notification Services Modul.

Beinhaltet:
- NotificationRuleEngine: Event-basierte Regel-Auswertung
- SkontoNotificationService: Multi-Channel Skonto-Deadline-Alerts
- UnifiedNotificationHub: Zentraler Orchestrator fuer alle Kanaele
- NotificationEscalationService: Zeitbasierte Eskalationsketten
- NotificationDeduplicationService: Duplikat-Praevention
"""

from app.services.notification.rule_engine import (
    NotificationRuleEngine,
    get_notification_rule_engine,
    RuleConditionMatcher,
    NotificationAction,
    RuleEvaluationResult,
)
from app.services.notification.skonto_notifications import (
    SkontoNotificationService,
    SkontoOpportunity,
    SkontoUrgencyLevel,
    get_skonto_notification_service,
    send_skonto_alerts,
)
from app.services.notification.unified_hub import (
    UnifiedNotificationHub,
    get_unified_notification_hub,
    send_notification,
    NotificationChannel,
    NotificationSeverity,
    NotificationCategory,
    NotificationPayload,
    NotificationRecipient,
    NotificationDeliveryResult,
    UserNotificationPreferences,
    EscalationLevel,
)
from app.services.notification.escalation_chain_service import (
    NotificationEscalationService,
    get_escalation_service,
    EscalationChain,
    EscalationLevel as EscalationLevelDataclass,
    EscalationState,
    EscalationStatus,
    EscalationChannel,
    PRESET_CHAINS,
)
from app.services.notification.dedup_service import (
    NotificationDeduplicationService,
    get_dedup_service,
)
from app.services.notification.template_engine import (
    NotificationTemplateEngine,
    get_template_engine,
)

__all__ = [
    # Rule Engine
    "NotificationRuleEngine",
    "get_notification_rule_engine",
    "RuleConditionMatcher",
    "NotificationAction",
    "RuleEvaluationResult",
    # Skonto Notifications
    "SkontoNotificationService",
    "SkontoOpportunity",
    "SkontoUrgencyLevel",
    "get_skonto_notification_service",
    "send_skonto_alerts",
    # Unified Notification Hub
    "UnifiedNotificationHub",
    "get_unified_notification_hub",
    "send_notification",
    "NotificationChannel",
    "NotificationSeverity",
    "NotificationCategory",
    "NotificationPayload",
    "NotificationRecipient",
    "NotificationDeliveryResult",
    "UserNotificationPreferences",
    "EscalationLevel",
    # Escalation Chain Service
    "NotificationEscalationService",
    "get_escalation_service",
    "EscalationChain",
    "EscalationLevelDataclass",
    "EscalationState",
    "EscalationStatus",
    "EscalationChannel",
    "PRESET_CHAINS",
    # Deduplication Service
    "NotificationDeduplicationService",
    "get_dedup_service",
    # Template Engine
    "NotificationTemplateEngine",
    "get_template_engine",
]
