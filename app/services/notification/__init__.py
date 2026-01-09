"""Notification Services Modul.

Beinhaltet:
- NotificationRuleEngine: Event-basierte Regel-Auswertung
"""

from app.services.notification.rule_engine import (
    NotificationRuleEngine,
    get_notification_rule_engine,
    RuleConditionMatcher,
    NotificationAction,
    RuleEvaluationResult,
)

__all__ = [
    "NotificationRuleEngine",
    "get_notification_rule_engine",
    "RuleConditionMatcher",
    "NotificationAction",
    "RuleEvaluationResult",
]
