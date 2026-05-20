# -*- coding: utf-8 -*-
"""
Anomalie-Erkennung database models for Ablage-System.

Models fuer:
- AnomalyRule: Konfigurierbare Regeln fuer Anomalie-Erkennung
- Anomaly: Erkannte Anomalien mit Score und Status-Tracking

Hybrid-Ansatz: Regelbasiert + Statistisch.

Phase 2.3 der Feature-Roadmap (Februar 2026).
Feinpoliert und durchdacht - Enterprise Anomaly Detection.
"""

import uuid
from enum import Enum

from sqlalchemy import (
    Column,
    String,
    DateTime,
    Boolean,
    Float,
    Text,
    ForeignKey,
    Index,
    CheckConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.models import Base, CrossDBJSON


class AnomalyRuleType(str, Enum):
    """Typen von Anomalie-Regeln."""
    DUPLICATE_INVOICE = "duplicate_invoice"
    AMOUNT_OUTLIER = "amount_outlier"
    SUPPLIER_CHANGE = "supplier_change"
    MISSING_CHAIN_DOC = "missing_chain_doc"
    UNUSUAL_FREQUENCY = "unusual_frequency"
    AMOUNT_THRESHOLD = "amount_threshold"


class AnomalySeverity(str, Enum):
    """Schweregrad einer Anomalie."""
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class AnomalyStatus(str, Enum):
    """Bearbeitungsstatus einer Anomalie."""
    OPEN = "open"
    INVESTIGATING = "investigating"
    RESOLVED = "resolved"
    FALSE_POSITIVE = "false_positive"


class AnomalyRule(Base):
    """
    Konfigurierbare Regeln fuer die Anomalie-Erkennung.

    Jede Regel definiert einen Prueftyp mit spezifischen Parametern.
    Regeln koennen pro Mandant aktiviert/deaktiviert werden.
    """
    __tablename__ = "anomaly_rules"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Regel-Identifikation
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)

    # Regel-Konfiguration
    rule_type = Column(String(50), nullable=False, index=True)
    config = Column(CrossDBJSON, nullable=False, default=dict)
    severity = Column(
        String(20),
        nullable=False,
        default=AnomalySeverity.WARNING.value,
    )

    # Status
    is_active = Column(Boolean, default=True, nullable=False)

    # Multi-Tenant
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Zeitstempel
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    # Relationships
    company = relationship("Company", backref="anomaly_rules")
    anomalies = relationship(
        "Anomaly",
        back_populates="rule",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("ix_anomaly_rules_company_active", "company_id", "is_active"),
        CheckConstraint(
            "rule_type IN ('duplicate_invoice', 'amount_outlier', 'supplier_change', "
            "'missing_chain_doc', 'unusual_frequency', 'amount_threshold')",
            name="ck_anomaly_rules_rule_type",
        ),
        CheckConstraint(
            "severity IN ('info', 'warning', 'critical')",
            name="ck_anomaly_rules_severity",
        ),
    )

    def to_dict(self) -> dict:
        """Konvertiere zu Dictionary fuer API-Antworten."""
        return {
            "id": str(self.id),
            "name": self.name,
            "description": self.description,
            "rule_type": self.rule_type,
            "config": self.config or {},
            "severity": self.severity,
            "is_active": self.is_active,
            "company_id": str(self.company_id),
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class Anomaly(Base):
    """
    Erkannte Anomalien mit Bewertung und Status-Tracking.

    Speichert alle erkannten Auffaelligkeiten aus regelbasierten
    und statistischen Pruefungen mit Konfidenz-Score und
    Bearbeitungs-Workflow.
    """
    __tablename__ = "anomalies"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Regel-Referenz (nullable fuer ML-erkannte Anomalien)
    rule_id = Column(
        UUID(as_uuid=True),
        ForeignKey("anomaly_rules.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Anomalie-Klassifikation
    anomaly_type = Column(String(50), nullable=False, index=True)
    severity = Column(String(20), nullable=False)

    # Beschreibung (Deutsch)
    title = Column(String(500), nullable=False)
    description = Column(Text, nullable=True)

    # Quell-Referenz
    source_table = Column(String(100), nullable=False)
    source_id = Column(UUID(as_uuid=True), nullable=False)

    # Verknuepfte Entitaeten
    related_ids = Column(CrossDBJSON, default=list)

    # Bewertung
    score = Column(Float, default=0.0)
    details = Column(CrossDBJSON, default=dict)

    # Status-Tracking
    status = Column(
        String(20),
        nullable=False,
        default=AnomalyStatus.OPEN.value,
    )
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    resolved_by_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    resolution_note = Column(Text, nullable=True)

    # Multi-Tenant
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Zeitstempel
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    rule = relationship("AnomalyRule", back_populates="anomalies")
    resolved_by = relationship("User", foreign_keys=[resolved_by_id])
    company = relationship("Company", backref="anomalies")

    __table_args__ = (
        Index(
            "ix_anomalies_company_status_created",
            "company_id",
            "status",
            "created_at",
        ),
        Index("ix_anomalies_type_status", "anomaly_type", "status"),
        CheckConstraint(
            "score >= 0 AND score <= 1",
            name="ck_anomalies_score_range",
        ),
        CheckConstraint(
            "severity IN ('info', 'warning', 'critical')",
            name="ck_anomalies_severity",
        ),
        CheckConstraint(
            "status IN ('open', 'investigating', 'resolved', 'false_positive')",
            name="ck_anomalies_status",
        ),
    )

    def to_dict(self) -> dict:
        """Konvertiere zu Dictionary fuer API-Antworten."""
        return {
            "id": str(self.id),
            "rule_id": str(self.rule_id) if self.rule_id else None,
            "anomaly_type": self.anomaly_type,
            "severity": self.severity,
            "title": self.title,
            "description": self.description,
            "source_table": self.source_table,
            "source_id": str(self.source_id),
            "related_ids": self.related_ids or [],
            "score": self.score,
            "details": self.details or {},
            "status": self.status,
            "resolved_at": (
                self.resolved_at.isoformat() if self.resolved_at else None
            ),
            "resolution_note": self.resolution_note,
            "company_id": str(self.company_id),
            "created_at": (
                self.created_at.isoformat() if self.created_at else None
            ),
        }
