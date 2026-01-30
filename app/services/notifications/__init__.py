# -*- coding: utf-8 -*-
"""
Notification Services - Intelligentes Benachrichtigungssystem.

Vision 2026 Q3: Smart Notification Engine.
"""

from app.services.notifications.smart_notification_engine import (
    SmartNotificationEngine,
    get_smart_notification_engine,
    NotificationEvent,
    NotificationDecision,
    DeliveredNotification,
    UserNotificationPreferences,
    UserContext,
    NotificationChannel,
    NotificationPriority,
    EventCategory,
    FilterReason,
)

__all__ = [
    # Smart Notification Engine
    "SmartNotificationEngine",
    "get_smart_notification_engine",
    "NotificationEvent",
    "NotificationDecision",
    "DeliveredNotification",
    "UserNotificationPreferences",
    "UserContext",
    # Enums
    "NotificationChannel",
    "NotificationPriority",
    "EventCategory",
    "FilterReason",
]
