"""Notification Services Modul.

Beinhaltet:
- NotificationRuleEngine: Event-basierte Regel-Auswertung
- SkontoNotificationService: Multi-Channel Skonto-Deadline-Alerts
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
]
