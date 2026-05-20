# -*- coding: utf-8 -*-
"""
Proaktiver Assistent - Datenbank-Modelle.

Hint-System für vorausschauende Warnungen und Optimierungsvorschläge:
- Fristen & Deadlines (Skonto, Verträge, Mahnungen)
- Anomalien & Warnungen (Preisabweichungen, Duplikate, Bankverbindungsänderungen)
- Optimierungs-Vorschläge (verpasste Skonti, Buendelungsrabatte, Dauerauftraege)

Feinpoliert und durchdacht - Enterprise-grade Proactive Intelligence.
"""

import uuid
from enum import Enum

from sqlalchemy import (
    Column,
    String,
    Integer,
    Float,
    DateTime,
    Boolean,
    Text,
    ForeignKey,
    Index,
    CheckConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.models import Base, CrossDBJSON


class HintCategory(str, Enum):
    """Hinweis-Kategorie."""
    DEADLINE = "deadline"          # Fristen & Deadlines
    ANOMALY = "anomaly"            # Anomalien & Warnungen
    OPTIMIZATION = "optimization"  # Optimierungs-Vorschläge


class HintPriority(str, Enum):
    """Hinweis-Priorität."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class HintStatus(str, Enum):
    """Hinweis-Bearbeitungsstatus."""
    NEW = "new"                    # Neu, ungesehen
    SEEN = "seen"                  # Gesehen aber nicht bestätigt
    ACKNOWLEDGED = "acknowledged"  # Zur Kenntnis genommen
    DISMISSED = "dismissed"        # Verworfen/Irrelevant
    ACTED_ON = "acted_on"          # Massnahme ergriffen


class ProactiveHint(Base):
    """
    Proaktiver Hinweis - Denkt mit und warnt vorausschauend.

    Speichert generierte Hinweise aus den drei Kategorien:
    Fristen, Anomalien, Optimierungen.
    """
    __tablename__ = "proactive_hints"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Multi-Tenant
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Optionaler User-Bezug (None = alle Benutzer)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Kategorisierung
    category = Column(
        String(30),
        nullable=False,
        default=HintCategory.DEADLINE.value,
    )
    priority = Column(
        String(20),
        nullable=False,
        default=HintPriority.MEDIUM.value,
    )
    status = Column(
        String(20),
        nullable=False,
        default=HintStatus.NEW.value,
    )

    # Inhalt
    title = Column(String(500), nullable=False)
    message = Column(Text, nullable=False)

    # Scoring (0.0 - 1.0)
    urgency_score = Column(Float, default=0.5)
    value_score = Column(Float, default=0.5)
    combined_score = Column(Float, default=0.25)

    # Quelle
    source_type = Column(String(100), nullable=False)
    source_id = Column(UUID(as_uuid=True), nullable=True)
    source_metadata = Column(CrossDBJSON, default=dict)

    # Aktionen
    action_url = Column(String(500), nullable=True)
    action_label = Column(String(200), nullable=True)

    # Ablauf
    expires_at = Column(DateTime(timezone=True), nullable=True)

    # Status-Zeitstempel
    seen_at = Column(DateTime(timezone=True), nullable=True)
    acknowledged_at = Column(DateTime(timezone=True), nullable=True)
    dismissed_at = Column(DateTime(timezone=True), nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    company = relationship("Company", backref="proactive_hints")
    user = relationship("User", backref="proactive_hints")

    __table_args__ = (
        Index("ix_proactive_hints_company_status", "company_id", "status"),
        Index("ix_proactive_hints_company_category_created", "company_id", "category", "created_at"),
        Index("ix_proactive_hints_expires_at", "expires_at"),
        Index("ix_proactive_hints_combined_score", "combined_score"),
        Index("ix_proactive_hints_source", "source_type", "source_id"),
        CheckConstraint(
            "category IN ('deadline', 'anomaly', 'optimization')",
            name="ck_proactive_hints_category",
        ),
        CheckConstraint(
            "priority IN ('low', 'medium', 'high', 'critical')",
            name="ck_proactive_hints_priority",
        ),
        CheckConstraint(
            "status IN ('new', 'seen', 'acknowledged', 'dismissed', 'acted_on')",
            name="ck_proactive_hints_status",
        ),
        CheckConstraint(
            "urgency_score >= 0.0 AND urgency_score <= 1.0",
            name="ck_proactive_hints_urgency_range",
        ),
        CheckConstraint(
            "value_score >= 0.0 AND value_score <= 1.0",
            name="ck_proactive_hints_value_range",
        ),
    )

    def to_dict(self) -> dict:
        """Convert hint to dictionary for API responses."""
        return {
            "id": str(self.id),
            "company_id": str(self.company_id),
            "user_id": str(self.user_id) if self.user_id else None,
            "category": self.category,
            "priority": self.priority,
            "status": self.status,
            "title": self.title,
            "message": self.message,
            "urgency_score": self.urgency_score,
            "value_score": self.value_score,
            "combined_score": self.combined_score,
            "source_type": self.source_type,
            "source_id": str(self.source_id) if self.source_id else None,
            "source_metadata": self.source_metadata or {},
            "action_url": self.action_url,
            "action_label": self.action_label,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "seen_at": self.seen_at.isoformat() if self.seen_at else None,
            "acknowledged_at": self.acknowledged_at.isoformat() if self.acknowledged_at else None,
            "dismissed_at": self.dismissed_at.isoformat() if self.dismissed_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class HintRule(Base):
    """
    Konfigurierbare Regeln für die Hinweis-Generierung.

    Ermöglicht pro Firma die Anpassung von Schwellwerten und
    Aktivierung/Deaktivierung einzelner Hint-Typen.
    """
    __tablename__ = "hint_rules"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Multi-Tenant
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Regel-Identifikation
    name = Column(String(200), nullable=False)
    category = Column(String(30), nullable=False)
    source_type = Column(String(100), nullable=False)

    # Konfiguration
    is_active = Column(Boolean, default=True)
    threshold_config = Column(CrossDBJSON, default=dict)
    schedule = Column(String(50), nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    company = relationship("Company", backref="hint_rules")

    __table_args__ = (
        Index("ix_hint_rules_company_active", "company_id", "is_active"),
    )


class HintStatistics(Base):
    """
    Aggregierte Statistiken über Hinweise pro Zeitraum.

    Wird täglich berechnet für Reporting und Dashboard.
    """
    __tablename__ = "hint_statistics"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Multi-Tenant
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Zeitraum
    period_start = Column(DateTime(timezone=True), nullable=False)
    period_end = Column(DateTime(timezone=True), nullable=False)

    # Statistiken
    total_hints = Column(Integer, default=0)
    hints_by_category = Column(CrossDBJSON, default=dict)
    action_rate = Column(Float, default=0.0)
    avg_response_time_hours = Column(Float, default=0.0)
    estimated_savings = Column(Float, default=0.0)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    company = relationship("Company", backref="hint_statistics")

    __table_args__ = (
        Index("ix_hint_statistics_company_period", "company_id", "period_start", "period_end"),
    )
