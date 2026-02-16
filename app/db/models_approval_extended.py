# -*- coding: utf-8 -*-
"""
Erweiterte Approval-Modelle für Features #3 und #7.

Feature #3: Approval Workflow Depth
- ConditionalApprovalRule: Bedingte Genehmigungsregeln
- EscalationRule: Konfigurierbare Eskalationsregeln
- SubstitutionRule: Stellvertretungsregeln (Urlaub, Krankheit)
- ApprovalSLAMetric: SLA-Metriken pro Schritt

Feature #7: Automation 2.0
- AutoFilingRule: ML-basierte Ablageregeln
- AutoMatchResult: Automatisches Dokumenten-Matching
"""

from datetime import datetime
from typing import Optional
import uuid

from sqlalchemy import (
    Column,
    String,
    Integer,
    Float,
    Boolean,
    Text,
    DateTime,
    ForeignKey,
    Index,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.models import Base, CrossDBJSON


# ============================================================================
# Feature #3: Approval Workflow Depth
# ============================================================================


class ConditionalApprovalRule(Base):
    """Bedingte Genehmigungsregel.

    Fuegt zusätzliche Genehmiger hinzu wenn bestimmte Bedingungen
    erfuellt sind (z.B. Betrag > 5000 EUR oder Lieferanten-Risiko > 70).

    conditions-Format:
        [
            {"field": "amount", "operator": "gt", "value": 5000, "currency": "EUR"},
            {"field": "supplier_risk_score", "operator": "gt", "value": 70}
        ]
    """
    __tablename__ = "conditional_approval_rules"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False, index=True)

    # Bedingungen als JSON-Array
    conditions = Column(CrossDBJSON, nullable=False, default=list)

    # Zusätzliche Genehmiger (User-IDs oder Rollen-Referenzen)
    additional_approvers = Column(CrossDBJSON, nullable=False, default=list)
    # Format: [{"type": "user", "value": "uuid..."}, {"type": "role", "value": "cfo"}]

    # Optionale Prioritäts-Überschreibung
    priority_override = Column(String(50), nullable=True)

    # Audit
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    company = relationship("Company", backref="conditional_approval_rules")

    __table_args__ = (
        Index(
            "ix_cond_approval_rules_company_active",
            "company_id",
            "is_active",
        ),
        {"comment": "Bedingte Genehmigungsregeln mit zusätzlichen Genehmigern"},
    )


class EscalationRule(Base):
    """Konfigurierbare Eskalationsregel.

    Definiert was passiert wenn eine Genehmigung nicht innerhalb
    des Timeout-Zeitraums bearbeitet wird.
    """
    __tablename__ = "escalation_rules"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name = Column(String(200), nullable=False)
    timeout_hours = Column(Integer, default=48, nullable=False)

    # Eskalationsziel
    escalation_target_user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    escalation_target_role = Column(String(100), nullable=True)

    # Benachrichtigungen
    send_email = Column(Boolean, default=True, nullable=False)
    send_notification = Column(Boolean, default=True, nullable=False)

    is_active = Column(Boolean, default=True, nullable=False, index=True)

    # Audit
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    company = relationship("Company", backref="escalation_rules")
    escalation_target_user = relationship(
        "User", foreign_keys=[escalation_target_user_id]
    )

    __table_args__ = (
        Index("ix_escalation_rules_company_active", "company_id", "is_active"),
        {"comment": "Eskalationsregeln für überfällige Genehmigungen"},
    )


class SubstitutionRule(Base):
    """Stellvertretungsregel.

    Ermöglicht automatische Weiterleitung von Genehmigungen
    an einen Stellvertreter bei Abwesenheit (Urlaub, Krankheit).
    """
    __tablename__ = "substitution_rules"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Abwesender User
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Stellvertreter
    substitute_user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Zeitraum
    valid_from = Column(DateTime(timezone=True), nullable=False)
    valid_until = Column(DateTime(timezone=True), nullable=False)

    # Grund
    reason = Column(String(200), nullable=True)
    # Typische Werte: "Urlaub", "Krankheit", "Dienstreise", "Fortbildung"

    is_active = Column(Boolean, default=True, nullable=False, index=True)
    auto_activated = Column(Boolean, default=False, nullable=False)

    # Audit
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    company = relationship("Company", backref="substitution_rules")
    user = relationship("User", foreign_keys=[user_id], backref="substitution_absences")
    substitute_user = relationship(
        "User", foreign_keys=[substitute_user_id], backref="substitution_duties"
    )

    __table_args__ = (
        Index("ix_substitution_rules_user", "user_id", "is_active"),
        Index("ix_substitution_rules_substitute", "substitute_user_id", "is_active"),
        Index("ix_substitution_rules_period", "valid_from", "valid_until"),
        {
            "comment": "Stellvertretungsregeln für abwesende Genehmiger "
            "(Urlaub, Krankheit)"
        },
    )


class ApprovalSLAMetric(Base):
    """SLA-Metrik für einen einzelnen Genehmigungsschritt.

    Trackt die Zeit von Zuweisung bis Bearbeitung pro Schritt
    und erkennt SLA-Verletzungen.
    """
    __tablename__ = "approval_sla_metrics"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    approval_request_id = Column(
        UUID(as_uuid=True),
        ForeignKey("approval_requests.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    step_number = Column(Integer, nullable=False)

    # Timing
    assigned_at = Column(DateTime(timezone=True), nullable=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    # SLA
    sla_target_hours = Column(Float, nullable=False)
    is_breached = Column(Boolean, default=False, nullable=False, index=True)
    breached_at = Column(DateTime(timezone=True), nullable=True)

    # Audit
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    company = relationship("Company", backref="approval_sla_metrics")
    approval_request = relationship("ApprovalRequest", backref="sla_metrics")

    __table_args__ = (
        Index(
            "ix_sla_metrics_request_step",
            "approval_request_id",
            "step_number",
        ),
        Index("ix_sla_metrics_breached", "company_id", "is_breached"),
        {"comment": "SLA-Metriken pro Genehmigungsschritt"},
    )


# ============================================================================
# Feature #7: Automation 2.0
# ============================================================================


class AutoFilingRule(Base):
    """Automatische Ablageregel (ML- oder regelbasiert).

    Lernt aus historischen Ablage-Entscheidungen und schlaegt
    automatisch Ordner/Kategorie für neue Dokumente vor.
    """
    __tablename__ = "auto_filing_rules"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)

    # Modelltyp: "ml" (Machine Learning) oder "rule" (Regelbasiert)
    model_type = Column(String(50), nullable=False, default="rule")

    # Confidence-Schwelle für automatische Ablage
    confidence_threshold = Column(Float, default=0.95, nullable=False)

    # Ziel
    target_folder_id = Column(UUID(as_uuid=True), nullable=True)
    target_category = Column(String(100), nullable=True)

    # Trainings-Statistiken
    training_sample_count = Column(Integer, default=0, nullable=False)
    accuracy = Column(Float, nullable=True)

    is_active = Column(Boolean, default=True, nullable=False, index=True)

    # Konfiguration (regelspezifisch oder ML-Parameter)
    config = Column(CrossDBJSON, nullable=True, default=dict)

    # Audit
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    company = relationship("Company", backref="auto_filing_rules")

    __table_args__ = (
        Index("ix_auto_filing_rules_company_active", "company_id", "is_active"),
        {"comment": "Automatische Ablageregeln (ML/Regel-basiert)"},
    )


class AutoMatchResult(Base):
    """Ergebnis eines automatischen Dokumenten-Matchings.

    Verknüpft automatisch zusammengehoerige Dokumente:
    Bestellung <-> Lieferschein <-> Rechnung
    """
    __tablename__ = "auto_match_results"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Quell-Dokument
    document_id = Column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Gefundenes Match-Dokument
    matched_document_id = Column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Match-Typ
    match_type = Column(String(50), nullable=False, index=True)
    # Werte: "bestellung_lieferschein", "lieferschein_rechnung", "bestellung_rechnung"

    # Konfidenz des Matchings (0.0 - 1.0)
    confidence = Column(Float, nullable=False)

    # Details: welche Felder gematcht haben
    match_details = Column(CrossDBJSON, nullable=True, default=dict)
    # Format: {"po_number": true, "amount": 0.95, "supplier": true, "date": 0.8}

    # Bestätigung
    is_confirmed = Column(Boolean, default=False, nullable=False)
    confirmed_by_user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Audit
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    company = relationship("Company", backref="auto_match_results")
    document = relationship(
        "Document", foreign_keys=[document_id], backref="auto_matches_as_source"
    )
    matched_document = relationship(
        "Document", foreign_keys=[matched_document_id], backref="auto_matches_as_target"
    )
    confirmed_by = relationship("User", foreign_keys=[confirmed_by_user_id])

    __table_args__ = (
        Index("ix_auto_match_document", "document_id", "match_type"),
        Index("ix_auto_match_matched", "matched_document_id"),
        Index("ix_auto_match_company_confirmed", "company_id", "is_confirmed"),
        {"comment": "Automatische Dokumenten-Matching-Ergebnisse"},
    )
