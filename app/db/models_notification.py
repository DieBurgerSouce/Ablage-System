"""Notification, Activity und Task Modelle - extrahiert aus models.py (Modularisierung Phase 1.1)."""
import uuid
from datetime import datetime
from enum import Enum

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    Time,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import relationship

from app.db.models_base import Base, CrossDBJSON, SoftDeleteMixin


class DocumentComment(SoftDeleteMixin, Base):
    """Kommentare zu Dokumenten für Collaboration.

    Multi-Tenant Support:
    - company_id: Firmenzugehoerigkeit (Migration 103)

    Feld-Referenz (Inline-Kommentare):
    - field_reference: Optionaler Feldname für Inline-Kommentare auf Extraktionsfeldern
      (z.B. "invoice_number", "total_amount", "vendor_name")

    Soft Delete mit Timestamp:
    - deleted_at: Zeitpunkt des Löschens (NULL = nicht gelöscht)
    - deleted_by_id: User der den Kommentar gelöscht hat
    - is_deleted: Legacy-Flag (wird parallel gepflegt)
    """
    __tablename__ = "document_comments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    parent_id = Column(UUID(as_uuid=True), ForeignKey("document_comments.id", ondelete="CASCADE"), nullable=True)

    # Multi-Tenant Support (Migration 103)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)

    # Feld-Referenz für Inline-Kommentare (Migration 103)
    field_reference = Column(String(100), nullable=True)

    content = Column(Text, nullable=False)
    mentions = Column(CrossDBJSON, default=list)  # [{"userId": "...", "userName": "...", "startIndex": 0, "endIndex": 10}]
    reactions = Column(CrossDBJSON, default=list)  # [{"emoji": "👍", "count": 2, "userIds": ["..."]}]

    is_edited = Column(Boolean, default=False)
    is_deleted = Column(Boolean, default=False)  # Legacy-Flag

    # Soft Delete mit Timestamp (Migration 103)
    deleted_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    document = relationship("Document", backref="comments")
    user = relationship("User", backref="document_comments", foreign_keys=[user_id])
    parent = relationship("DocumentComment", remote_side=[id], backref="replies")
    company = relationship("Company", backref="document_comments")
    deleted_by = relationship("User", foreign_keys=[deleted_by_id])

    __table_args__ = (
        Index("ix_doc_comment_document", "document_id"),
        Index("ix_doc_comment_user", "user_id"),
        Index("ix_doc_comment_parent", "parent_id"),
        Index("ix_doc_comment_created", "created_at"),
        Index("ix_doc_comment_company", "company_id"),
        Index("ix_doc_comment_company_document", "company_id", "document_id"),
    )

    def __repr__(self) -> str:
        return f"<DocumentComment {self.id} on {self.document_id}>"


class ActivityType(str, Enum):
    """Aktivitaetstypen für Document Activity Log."""
    DOCUMENT_CREATED = "document_created"
    DOCUMENT_UPDATED = "document_updated"
    DOCUMENT_VIEWED = "document_viewed"
    DOCUMENT_DOWNLOADED = "document_downloaded"
    COMMENT_ADDED = "comment_added"
    COMMENT_REPLIED = "comment_replied"
    STATUS_CHANGED = "status_changed"
    TAGS_CHANGED = "tags_changed"
    METADATA_UPDATED = "metadata_updated"
    DOCUMENT_SHARED = "document_shared"


class DocumentActivity(Base):
    """Aktivitaetslog für Dokumente."""
    __tablename__ = "document_activities"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    activity_type = Column(String(50), nullable=False)
    description = Column(String(500), nullable=False)
    activity_metadata = Column("metadata", CrossDBJSON, default=dict)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    document = relationship("Document", backref="activities")
    user = relationship("User", backref="document_activities")

    __table_args__ = (
        Index("ix_doc_activity_document", "document_id"),
        Index("ix_doc_activity_user", "user_id"),
        Index("ix_doc_activity_type", "activity_type"),
        Index("ix_doc_activity_created", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<DocumentActivity {self.activity_type} on {self.document_id}>"


class ActivityNotificationType(str, Enum):
    """Benachrichtigungstypen."""
    MENTION = "mention"
    COMMENT_REPLY = "comment_reply"
    DOCUMENT_SHARED = "document_shared"
    TASK_ASSIGNED = "task_assigned"
    TASK_COMPLETED = "task_completed"
    TASK_ESCALATED = "task_escalated"
    TASK_REMINDER = "task_reminder"
    DOCUMENT_APPROVED = "document_approved"
    DOCUMENT_REJECTED = "document_rejected"


# Backward-compatible alias
NotificationType = ActivityNotificationType


class UserNotification(Base):
    """Benutzer-Benachrichtigungen."""
    __tablename__ = "user_notifications"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    from_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=True)

    notification_type = Column(String(50), nullable=False)
    title = Column(String(200), nullable=False)
    message = Column(Text, nullable=False)
    action_url = Column(String(500), nullable=True)

    is_read = Column(Boolean, default=False)
    read_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    user = relationship("User", foreign_keys=[user_id], backref="notifications")
    from_user = relationship("User", foreign_keys=[from_user_id])
    document = relationship("Document", backref="notifications")

    __table_args__ = (
        Index("ix_notification_user", "user_id"),
        Index("ix_notification_unread", "user_id", "is_read"),
        Index("ix_notification_created", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<UserNotification {self.notification_type} for {self.user_id}>"


class TaskStatus(str, Enum):
    """Status einer zugewiesenen Aufgabe."""
    OPEN = "open"                  # Neu erstellt, noch nicht begonnen
    IN_PROGRESS = "in_progress"    # In Bearbeitung
    COMPLETED = "completed"        # Erledigt
    CANCELLED = "cancelled"        # Abgebrochen
    BLOCKED = "blocked"            # Blockiert (wartet auf etwas)


class TaskPriority(str, Enum):
    """Priorität einer Aufgabe."""
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


class DocumentTask(Base):
    """Aufgaben-Zuweisung für Dokumente.

    Ermöglicht Team-Collaboration durch:
    - Zuweisung von Aufgaben an Benutzer ("Bitte prüfen")
    - Deadlines mit automatischer Eskalation
    - Status-Tracking
    - Benachrichtigungen bei Änderungen
    """
    __tablename__ = "document_tasks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Referenzen
    document_id = Column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Aufgaben-Details
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    task_type = Column(String(50), nullable=False, default="review")  # review, approve, process, other

    # Zuweisung
    created_by_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )
    assigned_to_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True
    )

    # Status und Priorität
    status = Column(String(20), nullable=False, default=TaskStatus.OPEN.value)
    priority = Column(String(20), nullable=False, default=TaskPriority.NORMAL.value)

    # Deadlines
    due_date = Column(DateTime(timezone=True), nullable=True, index=True)
    reminder_sent = Column(Boolean, default=False)  # "Bald fällig" Erinnerung gesendet
    last_reminder_at = Column(DateTime(timezone=True), nullable=True)  # Letzte Überfällig-Erinnerung
    escalated = Column(Boolean, default=False)
    escalated_at = Column(DateTime(timezone=True), nullable=True)
    escalated_to_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )

    # Completion-Details
    completed_at = Column(DateTime(timezone=True), nullable=True)
    completed_by_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )
    completion_notes = Column(Text, nullable=True)

    # Metadaten
    task_metadata = Column(CrossDBJSON, default=dict)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    document = relationship("Document", backref="tasks")
    company = relationship("Company", backref="document_tasks")
    created_by = relationship("User", foreign_keys=[created_by_id], backref="created_tasks")
    assigned_to = relationship("User", foreign_keys=[assigned_to_id], backref="assigned_tasks")
    completed_by = relationship("User", foreign_keys=[completed_by_id])
    escalated_to = relationship("User", foreign_keys=[escalated_to_id])

    __table_args__ = (
        Index("ix_task_document", "document_id"),
        Index("ix_task_assigned", "assigned_to_id"),
        Index("ix_task_status", "status"),
        Index("ix_task_due_date", "due_date"),
        Index("ix_task_company_status", "company_id", "status"),
        Index("ix_task_assigned_status", "assigned_to_id", "status"),
    )

    def __repr__(self) -> str:
        return f"<DocumentTask {self.id} '{self.title}' -> {self.assigned_to_id}>"


class NotificationChannel(str, Enum):
    """Verfügbare Benachrichtigungskanaele."""
    IN_APP = "in_app"        # In-App Benachrichtigung (Glocke)
    EMAIL = "email"          # Email
    WEBSOCKET = "websocket"  # Real-time WebSocket
    SLACK = "slack"          # Slack Integration
    SMS = "sms"              # SMS (future)


class DigestFrequency(str, Enum):
    """Häufigkeit für Email-Digest."""
    IMMEDIATE = "immediate"  # Sofort senden
    HOURLY = "hourly"        # Stuendlich
    DAILY = "daily"          # Täglich
    WEEKLY = "weekly"        # Woechentlich
    DISABLED = "disabled"    # Deaktiviert


class NotificationPreference(Base):
    """Benutzer-Praeferenzen für Benachrichtigungen.

    Ermöglicht granulare Kontrolle über:
    - Welche Benachrichtigungstypen empfangen werden
    - Über welche Kanaele (In-App, Email, Slack, etc.)
    - Digest-Einstellungen (sofort, täglich, woechentlich)
    """
    __tablename__ = "notification_preferences"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Notification Type (z.B. "mention", "task_assigned", "document_shared")
    notification_type = Column(String(50), nullable=False)

    # Kanal-Einstellungen (JSON: {"in_app": true, "email": false, "slack": true})
    enabled_channels = Column(CrossDBJSON, default=lambda: {
        "in_app": True,
        "email": True,
        "websocket": True,
        "slack": False,
        "sms": False
    })

    # Digest-Einstellung für diesen Typ
    digest_frequency = Column(String(20), default=DigestFrequency.IMMEDIATE.value)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    user = relationship("User", backref="notification_preferences")

    __table_args__ = (
        UniqueConstraint("user_id", "notification_type", name="uq_user_notification_type"),
        Index("ix_notif_pref_user", "user_id"),
        Index("ix_notif_pref_type", "notification_type"),
    )

    def __repr__(self) -> str:
        return f"<NotificationPreference {self.user_id} - {self.notification_type}>"


class NotificationDigestQueue(Base):
    """Queue für Digest-Benachrichtigungen.

    Sammelt Benachrichtigungen für spätere Zustellung als Digest.
    Wird von einem Celery Task periodisch verarbeitet.
    """
    __tablename__ = "notification_digest_queue"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Originale Notification-Daten
    notification_type = Column(String(50), nullable=False)
    title = Column(String(200), nullable=False)
    message = Column(Text, nullable=False)
    action_url = Column(String(500), nullable=True)
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=True)
    from_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # Digest-Metadaten
    digest_frequency = Column(String(20), nullable=False)  # daily, weekly
    scheduled_for = Column(DateTime(timezone=True), nullable=False, index=True)  # Wann soll Digest gesendet werden

    # Status
    is_sent = Column(Boolean, default=False)
    sent_at = Column(DateTime(timezone=True), nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    user = relationship("User", foreign_keys=[user_id])
    document = relationship("Document")
    from_user = relationship("User", foreign_keys=[from_user_id])

    __table_args__ = (
        Index("ix_digest_queue_user_unsent", "user_id", "is_sent"),
        Index("ix_digest_queue_scheduled", "scheduled_for", "is_sent"),
    )

    def __repr__(self) -> str:
        return f"<NotificationDigestQueue {self.id} for {self.user_id}>"


class PushSubscription(Base):
    """Push Subscription für Web Push Notifications.

    Speichert Web Push Subscription Daten pro Geraet/Browser.
    Ermöglicht Benachrichtigungen auch wenn App nicht geöffnet ist.
    """

    __tablename__ = "push_subscriptions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    # Web Push Subscription data
    endpoint = Column(Text, nullable=False, unique=True, index=True)
    p256dh_key = Column(Text, nullable=False)
    auth_key = Column(Text, nullable=False)
    expiration_time = Column(BigInteger, nullable=True)

    # Device information
    device_name = Column(String(255), nullable=True)
    device_type = Column(String(50), nullable=True, index=True)  # mobile, tablet, desktop
    browser = Column(String(100), nullable=True)
    os = Column(String(100), nullable=True)
    user_agent = Column(Text, nullable=True)

    # Subscription preferences
    preferences = Column(CrossDBJSON, nullable=False, default=dict)

    # Status
    is_active = Column(Boolean, nullable=False, default=True, index=True)
    last_used_at = Column(DateTime(timezone=True), nullable=True)
    error_count = Column(Integer, nullable=False, default=0)
    last_error = Column(Text, nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    user = relationship("User", backref="push_subscriptions")
    notification_history = relationship("NotificationHistory", back_populates="subscription", cascade="all, delete-orphan")

    __table_args__ = (
        {"comment": "Web Push Subscriptions für PWA Notifications"}
    )


class NotificationTemplate(Base):
    """Notification Template für vordefinierte Benachrichtigungen.

    Ermöglicht wiederverwendbare Notification-Vorlagen mit Variablen.
    """

    __tablename__ = "notification_templates"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Template identification
    name = Column(String(100), nullable=False, unique=True, index=True)
    category = Column(String(50), nullable=False, index=True)
    description = Column(Text, nullable=True)

    # Notification content
    title_template = Column(String(255), nullable=False)
    body_template = Column(Text, nullable=False)
    icon = Column(String(255), nullable=True)
    badge = Column(String(255), nullable=True)
    image = Column(String(255), nullable=True)

    # Actions
    actions = Column(CrossDBJSON, nullable=True)

    # Behavior
    tag = Column(String(100), nullable=True)
    require_interaction = Column(Boolean, nullable=False, default=False)
    silent = Column(Boolean, nullable=False, default=False)
    vibrate_pattern = Column(CrossDBJSON, nullable=True)

    # Default preferences
    default_enabled = Column(Boolean, nullable=False, default=True)
    priority = Column(String(20), nullable=False, default="normal")

    # Status
    is_active = Column(Boolean, nullable=False, default=True, index=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    notification_history = relationship("NotificationHistory", back_populates="template")

    __table_args__ = (
        {"comment": "Vordefinierte Notification Templates"}
    )


class NotificationHistory(Base):
    """History für gesendete Push Notifications.

    Ermöglicht Tracking von Delivery und Click-Through.
    """

    __tablename__ = "notification_history"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    subscription_id = Column(UUID(as_uuid=True), ForeignKey("push_subscriptions.id", ondelete="CASCADE"), nullable=False, index=True)
    template_id = Column(UUID(as_uuid=True), ForeignKey("notification_templates.id", ondelete="SET NULL"), nullable=True, index=True)

    # Notification content (snapshot)
    title = Column(String(255), nullable=False)
    body = Column(Text, nullable=False)
    data = Column(CrossDBJSON, nullable=True)

    # Delivery status
    status = Column(String(20), nullable=False, default="pending", index=True)  # pending, sent, delivered, clicked, failed
    sent_at = Column(DateTime(timezone=True), nullable=True)
    delivered_at = Column(DateTime(timezone=True), nullable=True)
    clicked_at = Column(DateTime(timezone=True), nullable=True)
    error_message = Column(Text, nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)

    # Relationships
    subscription = relationship("PushSubscription", back_populates="notification_history")
    template = relationship("NotificationTemplate", back_populates="notification_history")

    __table_args__ = (
        {"comment": "Tracking für gesendete Push Notifications"}
    )


class NotificationRulePriority(str, Enum):
    """Priorität einer Notification Rule."""
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


class NotificationRuleActionType(str, Enum):
    """Aktionstyp für Notification Rules."""
    IN_APP = "in_app"
    PUSH = "push"
    EMAIL = "email"
    WEBHOOK = "webhook"


class NotificationRule(Base):
    """Notification Rules für Event-basierte Benachrichtigungen.

    Ermöglicht benutzerdefinierte Regeln, wann und wie Benachrichtigungen
    ausgeloest werden sollen. Teil des Enterprise Notification Rule Engine.

    Beispiel-Conditions:
    {
        "operator": "AND",
        "conditions": [
            {"field": "amount", "op": "gt", "value": 1000},
            {"field": "category", "op": "eq", "value": "insurance"}
        ]
    }

    Beispiel-Actions:
    {
        "actions": [
            {"type": "in_app", "template_id": "...", "priority": "high"},
            {"type": "push", "title": "...", "body": "..."},
            {"type": "email", "template": "payment_alert"}
        ]
    }
    """

    __tablename__ = "notification_rules"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    # Rule identification
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    enabled = Column(Boolean, nullable=False, default=True)

    # Event matching
    event_type = Column(String(100), nullable=False, index=True,
                        comment="Event-Typ z.B. document.ocr_completed, insurance.deadline_approaching")
    event_source = Column(String(50), nullable=True,
                          comment="Optional: Quelle filtern (z.B. privat, business)")

    # Conditions (JSONB für komplexe Filter)
    conditions = Column(CrossDBJSON, nullable=False, default=dict,
                        comment="JSON-Bedingungen mit Operatoren (AND, OR, NOT)")

    # Actions (JSONB für mehrere Aktionen)
    actions = Column(CrossDBJSON, nullable=False, default=list,
                     comment="Liste von auszuführenden Aktionen")

    # Scheduling
    quiet_hours_start = Column(Time, nullable=True,
                               comment="Start der Ruhezeit (z.B. 22:00)")
    quiet_hours_end = Column(Time, nullable=True,
                             comment="Ende der Ruhezeit (z.B. 08:00)")
    timezone = Column(String(50), nullable=False, default="Europe/Berlin")

    # Rate limiting
    cooldown_minutes = Column(Integer, nullable=True, default=0,
                              comment="Mindestabstand zwischen Benachrichtigungen")
    max_per_day = Column(Integer, nullable=True,
                         comment="Maximale Anzahl pro Tag (NULL = unbegrenzt)")

    # Priority
    priority = Column(String(20), nullable=False, default=NotificationRulePriority.NORMAL.value)

    # Statistics
    trigger_count = Column(Integer, nullable=False, default=0)
    last_triggered_at = Column(DateTime(timezone=True), nullable=True)
    last_matched_event_id = Column(UUID(as_uuid=True), nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    user = relationship("User", backref="notification_rules")

    __table_args__ = (
        Index("ix_notification_rules_user_enabled", "user_id", "enabled"),
        Index("ix_notification_rules_event_type", "event_type"),
        {"comment": "Benutzerdefinierte Notification-Regeln für Events"}
    )

    def __repr__(self) -> str:
        return f"<NotificationRule {self.name} ({self.event_type})>"
