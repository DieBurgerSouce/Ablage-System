# -*- coding: utf-8 -*-
"""
Alert database models for Ablage-System.

Zentrales Alert-Management fuer:
- Fraud Detection Alerts
- Risk Intelligence Alerts
- Compliance Violations
- Deadline Warnings
- System Alerts

Feinpoliert und durchdacht - Enterprise-grade Alert Management.
"""

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from sqlalchemy import (
    Column,
    String,
    Integer,
    DateTime,
    Boolean,
    Text,
    ForeignKey,
    Index,
    CheckConstraint,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.models import Base, CrossDBJSON


class AlertCategory(str, Enum):
    """Alert category classification."""
    FRAUD = "fraud"              # Betrugsverdacht
    RISK = "risk"                # Risikowarnung
    COMPLIANCE = "compliance"    # Compliance-Verletzung
    DEADLINE = "deadline"        # Fristwarnung
    SYSTEM = "system"            # Systemwarnung
    SECURITY = "security"        # Sicherheitswarnung
    QUALITY = "quality"          # Qualitaetswarnung (OCR, Daten)
    WORKFLOW = "workflow"        # Workflow-bezogene Alerts


class AlertSeverity(str, Enum):
    """Alert severity levels."""
    INFO = "info"          # Informativ - keine Aktion erforderlich
    LOW = "low"            # Niedrig - bei Gelegenheit pruefen
    MEDIUM = "medium"      # Mittel - zeitnah pruefen
    HIGH = "high"          # Hoch - dringend pruefen
    CRITICAL = "critical"  # Kritisch - sofortige Aktion erforderlich


class AlertStatus(str, Enum):
    """Alert processing status."""
    NEW = "new"                    # Neu, ungelesen
    ACKNOWLEDGED = "acknowledged"  # Zur Kenntnis genommen
    IN_PROGRESS = "in_progress"    # In Bearbeitung
    RESOLVED = "resolved"          # Geloest
    DISMISSED = "dismissed"        # Verworfen/Ignoriert
    ESCALATED = "escalated"        # Eskaliert


class Alert(Base):
    """
    Central alert model for all system alerts.

    Stores alerts from various sources with categorization,
    severity levels, and tracking of acknowledgment/resolution.
    """
    __tablename__ = "alerts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Alert identification
    alert_code = Column(String(50), nullable=False, index=True)
    title = Column(String(255), nullable=False)
    message = Column(Text, nullable=False)

    # Categorization
    category = Column(
        String(30),
        nullable=False,
        default=AlertCategory.SYSTEM.value,
        index=True,
    )
    severity = Column(
        String(20),
        nullable=False,
        default=AlertSeverity.MEDIUM.value,
        index=True,
    )
    status = Column(
        String(20),
        nullable=False,
        default=AlertStatus.NEW.value,
        index=True,
    )

    # Source tracking
    source_type = Column(String(50), nullable=True)  # z.B. "fraud_detection", "ocr_pipeline"
    source_id = Column(String(100), nullable=True)   # z.B. Document ID, Entity ID

    # Related entities (optional references)
    document_id = Column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    entity_id = Column(
        UUID(as_uuid=True),
        ForeignKey("business_entities.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Multi-tenant support
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # User assignment
    assigned_to_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Extended data (flexible JSON for category-specific data)
    # Note: 'metadata' is reserved in SQLAlchemy, so we use 'alert_metadata'
    alert_metadata = Column(CrossDBJSON, default=dict)
    context = Column(CrossDBJSON, default=dict)  # Additional context for UI

    # Actions available for this alert
    available_actions = Column(CrossDBJSON, default=list)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    acknowledged_at = Column(DateTime(timezone=True), nullable=True)
    acknowledged_by_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    resolved_by_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Resolution details
    resolution_note = Column(Text, nullable=True)
    resolution_action = Column(String(100), nullable=True)

    # Auto-dismiss settings
    auto_dismiss_at = Column(DateTime(timezone=True), nullable=True)
    is_recurring = Column(Boolean, default=False)
    recurrence_key = Column(String(255), nullable=True, index=True)

    # Email notification tracking
    email_sent = Column(Boolean, default=False)
    email_sent_at = Column(DateTime(timezone=True), nullable=True)

    # Escalation tracking
    escalation_level = Column(Integer, default=0)
    escalated_at = Column(DateTime(timezone=True), nullable=True)
    escalated_to_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Relationships
    company = relationship("Company", backref="alerts")
    document = relationship("Document", backref="alerts")
    assigned_to = relationship(
        "User",
        foreign_keys=[assigned_to_id],
        backref="assigned_alerts",
    )
    acknowledged_by = relationship(
        "User",
        foreign_keys=[acknowledged_by_id],
    )
    resolved_by = relationship(
        "User",
        foreign_keys=[resolved_by_id],
    )
    escalated_to = relationship(
        "User",
        foreign_keys=[escalated_to_id],
    )

    # Indexes for common queries
    __table_args__ = (
        Index("ix_alerts_company_status", "company_id", "status"),
        Index("ix_alerts_company_category", "company_id", "category"),
        Index("ix_alerts_company_severity", "company_id", "severity"),
        Index("ix_alerts_created_at", "created_at"),
        Index("ix_alerts_recurrence_key", "recurrence_key"),
        CheckConstraint(
            "severity IN ('info', 'low', 'medium', 'high', 'critical')",
            name="ck_alerts_severity",
        ),
        CheckConstraint(
            "status IN ('new', 'acknowledged', 'in_progress', 'resolved', 'dismissed', 'escalated')",
            name="ck_alerts_status",
        ),
        CheckConstraint(
            "category IN ('fraud', 'risk', 'compliance', 'deadline', 'system', 'security', 'quality', 'workflow')",
            name="ck_alerts_category",
        ),
    )

    def to_dict(self) -> dict:
        """Convert alert to dictionary for API responses."""
        return {
            "id": str(self.id),
            "alert_code": self.alert_code,
            "title": self.title,
            "message": self.message,
            "category": self.category,
            "severity": self.severity,
            "status": self.status,
            "source_type": self.source_type,
            "source_id": self.source_id,
            "document_id": str(self.document_id) if self.document_id else None,
            "entity_id": str(self.entity_id) if self.entity_id else None,
            "company_id": str(self.company_id),
            "assigned_to_id": str(self.assigned_to_id) if self.assigned_to_id else None,
            "metadata": self.alert_metadata or {},
            "context": self.context or {},
            "available_actions": self.available_actions or [],
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "acknowledged_at": self.acknowledged_at.isoformat() if self.acknowledged_at else None,
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
            "resolution_note": self.resolution_note,
            "escalation_level": self.escalation_level,
            "email_sent": self.email_sent,
        }


class AlertRule(Base):
    """
    Alert rules for automatic alert generation.

    Defines conditions that trigger alerts and their configuration.
    """
    __tablename__ = "alert_rules"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Rule identification
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)

    # Rule configuration
    category = Column(String(30), nullable=False)
    severity = Column(String(20), nullable=False)
    alert_code = Column(String(50), nullable=False)

    # Conditions (JSON-based for flexibility)
    conditions = Column(CrossDBJSON, nullable=False, default=dict)

    # Actions when triggered
    actions = Column(CrossDBJSON, default=list)

    # Throttling
    cooldown_minutes = Column(Integer, default=60)  # Min. Zeit zwischen Alerts
    max_alerts_per_day = Column(Integer, nullable=True)

    # Multi-tenant
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Status
    is_active = Column(Boolean, default=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    created_by_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Relationships
    company = relationship("Company", backref="alert_rules")
    created_by = relationship("User")

    __table_args__ = (
        Index("ix_alert_rules_company_active", "company_id", "is_active"),
    )


class AlertDigestSubscription(Base):
    """
    User subscriptions for alert email digests.

    Allows users to configure daily/weekly digest emails.
    """
    __tablename__ = "alert_digest_subscriptions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Digest configuration
    frequency = Column(String(20), default="daily")  # daily, weekly, immediate
    categories = Column(CrossDBJSON, default=list)   # Which categories to include
    min_severity = Column(String(20), default="medium")  # Minimum severity

    # Schedule
    digest_hour = Column(Integer, default=8)  # Hour of day for digest (0-23)
    digest_day = Column(Integer, nullable=True)  # Day of week for weekly (0=Mon, 6=Sun)

    # Status
    is_active = Column(Boolean, default=True)
    last_sent_at = Column(DateTime(timezone=True), nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    user = relationship("User", backref="alert_digest_subscriptions")

    __table_args__ = (
        Index("ix_alert_digest_user_active", "user_id", "is_active"),
    )
