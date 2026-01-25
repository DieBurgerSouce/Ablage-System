# -*- coding: utf-8 -*-
"""
Business Rules Models fuer Ablage-System.

Persistierung von Geschaeftsregeln in der Datenbank.

Phase 4 der Strategischen Roadmap (Januar 2026).
"""

from datetime import datetime
from typing import Optional, List
import uuid

from sqlalchemy import (
    Column,
    String,
    Integer,
    Boolean,
    Text,
    DateTime,
    ForeignKey,
    Index,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.models import Base, CrossDBJSON


class BusinessRuleModel(Base):
    """Persistierte Geschaeftsregel.

    Speichert Regeln mit Bedingungen und Aktionen.
    """
    __tablename__ = "business_rules"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Identifikation
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    code = Column(String(50), nullable=True, index=True,
                  comment="Kurzer eindeutiger Code (z.B. RULE_HIGH_AMOUNT)")

    # Multi-Tenant
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Regel-Definition (JSON)
    condition = Column(
        CrossDBJSON,
        nullable=False,
        comment="Bedingung als JSON-Struktur"
    )
    # Format: {"field": "amount", "op": ">", "value": 10000}
    # Oder: {"and": [{"field": "...", ...}, {"field": "...", ...}]}

    actions = Column(
        CrossDBJSON,
        nullable=False,
        default=list,
        comment="Aktionen als JSON-Array"
    )
    # Format: [{"type": "require_approval", "params": {...}}]

    else_actions = Column(
        CrossDBJSON,
        nullable=True,
        default=list,
        comment="Aktionen wenn Regel NICHT matcht"
    )

    # Konfiguration
    priority = Column(Integer, nullable=False, default=50,
                      comment="Ausfuehrungsprioritaet (hoeher = frueher)")
    category = Column(String(50), nullable=False, default="custom",
                      comment="approval, compliance, fraud, workflow, etc.")

    is_active = Column(Boolean, nullable=False, default=True)
    stop_on_match = Column(Boolean, nullable=False, default=False,
                          comment="Weitere Regeln nach Match stoppen")

    # Anwendungsbereich
    applies_to_document_types = Column(
        CrossDBJSON,
        nullable=True,
        default=list,
        comment="Nur fuer bestimmte Dokumenttypen"
    )
    applies_to_sources = Column(
        CrossDBJSON,
        nullable=True,
        default=list,
        comment="Nur fuer bestimmte Quellen"
    )

    # Zeitliche Einschraenkung
    valid_from = Column(DateTime(timezone=True), nullable=True)
    valid_until = Column(DateTime(timezone=True), nullable=True)

    # Statistiken
    execution_count = Column(Integer, nullable=False, default=0,
                             comment="Wie oft ausgefuehrt")
    match_count = Column(Integer, nullable=False, default=0,
                         comment="Wie oft gematcht")
    last_executed_at = Column(DateTime(timezone=True), nullable=True)
    last_matched_at = Column(DateTime(timezone=True), nullable=True)

    # Audit
    created_by_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )
    updated_by_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(),
                        onupdate=func.now())

    # Metadata
    metadata_json = Column(CrossDBJSON, default=dict)

    # Relationships
    company = relationship("Company", backref="business_rules")
    created_by = relationship("User", foreign_keys=[created_by_id])
    updated_by = relationship("User", foreign_keys=[updated_by_id])
    execution_logs = relationship(
        "RuleExecutionLog",
        back_populates="rule",
        cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_rule_company_active", "company_id", "is_active"),
        Index("ix_rule_company_category", "company_id", "category"),
        Index("ix_rule_priority", "priority"),
        UniqueConstraint("company_id", "code", name="uq_rule_company_code"),
    )


class RuleExecutionLog(Base):
    """Log fuer Regel-Ausfuehrungen.

    Protokolliert jede Ausfuehrung einer Regel fuer Audit und Debugging.
    """
    __tablename__ = "rule_execution_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Regel
    rule_id = Column(
        UUID(as_uuid=True),
        ForeignKey("business_rules.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Kontext
    document_id = Column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="SET NULL"),
        nullable=True,
        index=True
    )

    # Ergebnis
    matched = Column(Boolean, nullable=False)
    condition_details = Column(CrossDBJSON, default=dict)
    triggered_actions = Column(CrossDBJSON, default=list)
    execution_errors = Column(CrossDBJSON, default=list)

    # Kontext-Snapshot (fuer Debugging)
    context_snapshot = Column(CrossDBJSON, default=dict)

    # Ausfuehrung
    dry_run = Column(Boolean, nullable=False, default=False)
    executed_at = Column(DateTime(timezone=True), server_default=func.now(),
                         nullable=False, index=True)
    execution_time_ms = Column(Integer, nullable=True,
                               comment="Ausfuehrungszeit in Millisekunden")

    # Relationships
    rule = relationship("BusinessRuleModel", back_populates="execution_logs")
    document = relationship("Document", backref="rule_execution_logs")

    __table_args__ = (
        Index("ix_rule_log_rule_date", "rule_id", "executed_at"),
        Index("ix_rule_log_document", "document_id", "executed_at"),
    )


class RuleSet(Base):
    """Gruppierung von Regeln zu Sets.

    Ermoeglicht logische Gruppierung und Versionierung.
    """
    __tablename__ = "rule_sets"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Identifikation
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    version = Column(String(20), nullable=False, default="1.0.0")

    # Multi-Tenant
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Konfiguration
    is_active = Column(Boolean, nullable=False, default=True)
    is_default = Column(Boolean, nullable=False, default=False,
                        comment="Standard-Set fuer Company")

    # Regeln (IDs)
    rule_ids = Column(CrossDBJSON, nullable=False, default=list,
                      comment="Geordnete Liste der Regel-IDs")

    # Audit
    created_by_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(),
                        onupdate=func.now())

    # Relationships
    company = relationship("Company", backref="rule_sets")
    created_by = relationship("User", foreign_keys=[created_by_id])

    __table_args__ = (
        Index("ix_ruleset_company_active", "company_id", "is_active"),
        UniqueConstraint("company_id", "name", "version",
                         name="uq_ruleset_company_name_version"),
    )
