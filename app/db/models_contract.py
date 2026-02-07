# -*- coding: utf-8 -*-
"""
Contract database models for Ablage-System.

Vision 2.0 Feature: Contract AI - Intelligente Vertragsanalyse
Unterstuetzt alle Vertragstypen:
- Lieferantenvertraege (Rahmenvertraege, Einkaufskonditionen)
- Kundenvertraege (SLAs, Gewaehrleistungen)
- Miet-/Leasingvertraege (Immobilien, Fahrzeuge, Equipment)
- Arbeitsvertraege (Befristungen, Kuendigungsfristen)

Feinpoliert und durchdacht - Enterprise-grade Contract Management.
"""

import uuid
from datetime import datetime, date
from decimal import Decimal
from enum import Enum
from typing import Optional, List

from sqlalchemy import (
    Column,
    String,
    Integer,
    DateTime,
    Date,
    Boolean,
    Text,
    Numeric,
    ForeignKey,
    Index,
    CheckConstraint,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.models import Base, CrossDBJSON


class ContractType(str, Enum):
    """Vertragstyp-Klassifikation."""
    # Lieferantenvertraege
    SUPPLIER_FRAMEWORK = "supplier_framework"  # Rahmenvertrag
    SUPPLIER_PURCHASE = "supplier_purchase"    # Einkaufskonditionen

    # Kundenvertraege
    CUSTOMER_SLA = "customer_sla"              # Service Level Agreement
    CUSTOMER_WARRANTY = "customer_warranty"    # Gewaehrleistungsvertrag
    CUSTOMER_SALES = "customer_sales"          # Verkaufsvertrag

    # Miet-/Leasingvertraege
    LEASE_PROPERTY = "lease_property"          # Immobilienmiete
    LEASE_VEHICLE = "lease_vehicle"            # Fahrzeugleasing
    LEASE_EQUIPMENT = "lease_equipment"        # Equipment-Leasing

    # Arbeitsvertraege
    EMPLOYMENT_PERMANENT = "employment_permanent"  # Unbefristet
    EMPLOYMENT_FIXED = "employment_fixed"          # Befristet
    EMPLOYMENT_FREELANCE = "employment_freelance"  # Freiberufler

    # Sonstige
    NDA = "nda"                                # Geheimhaltungsvereinbarung
    PARTNERSHIP = "partnership"                # Partnerschaftsvertrag
    LICENSE = "license"                        # Lizenzvertrag
    MAINTENANCE = "maintenance"                # Wartungsvertrag
    OTHER = "other"                            # Sonstiger Vertrag


class ContractStatus(str, Enum):
    """Vertragsstatus."""
    DRAFT = "draft"                  # Entwurf
    PENDING_APPROVAL = "pending"     # Warten auf Genehmigung
    ACTIVE = "active"                # Aktiv/Laufend
    EXPIRED = "expired"              # Abgelaufen
    TERMINATED = "terminated"        # Gekuendigt
    SUSPENDED = "suspended"          # Ausgesetzt
    RENEWED = "renewed"              # Verlaengert


class ObligationType(str, Enum):
    """Pflichttyp."""
    PAYMENT = "payment"              # Zahlung
    DELIVERY = "delivery"            # Lieferung
    REPORT = "report"                # Bericht/Report
    MAINTENANCE = "maintenance"      # Wartung
    AUDIT = "audit"                  # Pruefung
    NOTIFICATION = "notification"    # Benachrichtigung
    COMPLIANCE = "compliance"        # Compliance-Pflicht
    RENEWAL = "renewal"              # Verlaengerung
    OTHER = "other"                  # Sonstige


class ObligationStatus(str, Enum):
    """Status einer Vertragspflicht."""
    PENDING = "pending"              # Ausstehend
    IN_PROGRESS = "in_progress"      # In Bearbeitung
    FULFILLED = "fulfilled"          # Erfuellt
    OVERDUE = "overdue"              # Ueberfaellig
    WAIVED = "waived"                # Verzichtet
    CANCELLED = "cancelled"          # Storniert


class RecurrencePattern(str, Enum):
    """Wiederholungsmuster."""
    ONCE = "once"                    # Einmalig
    DAILY = "daily"                  # Taeglich
    WEEKLY = "weekly"                # Woechentlich
    BIWEEKLY = "biweekly"            # Alle 2 Wochen
    MONTHLY = "monthly"              # Monatlich
    QUARTERLY = "quarterly"          # Vierteljährlich
    SEMIANNUAL = "semiannual"        # Halbjaehrlich
    ANNUAL = "annual"                # Jaehrlich


class Contract(Base):
    """
    Haupttabelle fuer Vertraege.

    Speichert alle Vertragsmetadaten inkl. automatisch extrahierter
    Klauseln, Fristen und Risiko-Scores.
    """
    __tablename__ = "contracts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Verknuepfung zum Quelldokument
    document_id = Column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Vertragsidentifikation
    contract_number = Column(String(100), nullable=True, index=True)
    title = Column(String(500), nullable=False)
    description = Column(Text, nullable=True)

    # Klassifikation
    contract_type = Column(
        String(50),
        nullable=False,
        default=ContractType.OTHER.value,
        index=True,
    )
    status = Column(
        String(30),
        nullable=False,
        default=ContractStatus.DRAFT.value,
        index=True,
    )

    # Vertragsparteien
    parties = Column(CrossDBJSON, default=list)
    # Format: [{"role": "buyer/seller/lessor/lessee", "name": "...", "entity_id": "uuid or null"}]

    our_role = Column(String(50), nullable=True)  # buyer, seller, lessor, lessee, employer, employee
    counterparty_entity_id = Column(
        UUID(as_uuid=True),
        ForeignKey("business_entities.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Laufzeiten
    effective_date = Column(Date, nullable=True, index=True)
    expiration_date = Column(Date, nullable=True, index=True)
    signed_date = Column(Date, nullable=True)

    # Automatische Verlaengerung
    auto_renewal = Column(Boolean, default=False)
    renewal_period_months = Column(Integer, nullable=True)
    renewal_notice_days = Column(Integer, nullable=True)  # Kuendigungsfrist vor Verlaengerung

    # Kuendigung
    notice_period_days = Column(Integer, nullable=True)
    termination_date = Column(Date, nullable=True)
    termination_reason = Column(Text, nullable=True)

    # Finanzen
    total_value = Column(Numeric(15, 2), nullable=True)
    currency = Column(String(3), default="EUR")
    payment_terms = Column(CrossDBJSON, default=dict)
    # Format: {"due_days": 30, "skonto_percent": 2, "skonto_days": 14}

    # Extrahierte Klauseln (NLP-basiert)
    clauses = Column(CrossDBJSON, default=dict)
    # Format: {
    #   "liability": {"text": "...", "limit": 100000, "exclusions": [...]},
    #   "warranty": {"period_months": 24, "conditions": "..."},
    #   "confidentiality": {"duration_years": 5, "scope": "..."},
    #   "price_adjustment": {"type": "index", "index_name": "CPI", "interval": "annual"},
    #   "jurisdiction": {"court": "Hamburg", "law": "German"},
    #   "incoterms": "DAP",
    #   ...
    # }

    # Unterschriften
    signatures = Column(CrossDBJSON, default=list)
    # Format: [{"party": "...", "signatory": "Name", "date": "2026-01-15", "valid": true}]

    # Risiko-Bewertung
    risk_score = Column(Integer, nullable=True)  # 0-100, hoeher = mehr Risiko
    risk_factors = Column(CrossDBJSON, default=list)
    # Format: [{"factor": "short_notice_period", "impact": 15, "description": "..."}]

    # OCR/NLP Verarbeitungsinfos
    extraction_confidence = Column(Numeric(5, 4), nullable=True)
    extraction_backend = Column(String(50), nullable=True)
    last_analyzed_at = Column(DateTime(timezone=True), nullable=True)
    analysis_version = Column(String(20), nullable=True)  # Version des Analyse-Algorithmus

    # Versionen (fuer Vertragsaenderungen)
    version_number = Column(Integer, default=1)
    parent_contract_id = Column(
        UUID(as_uuid=True),
        ForeignKey("contracts.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Multi-Tenant
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Benutzer-Tracking
    created_by_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    updated_by_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Zeitstempel
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Tags fuer Kategorisierung
    tags = Column(CrossDBJSON, default=list)

    # Freitext-Notizen
    notes = Column(Text, nullable=True)

    # Relationships
    document = relationship("Document", backref="contracts")
    counterparty = relationship("BusinessEntity", backref="contracts_as_counterparty")
    company = relationship("Company", backref="contracts")
    created_by = relationship("User", foreign_keys=[created_by_id])
    updated_by = relationship("User", foreign_keys=[updated_by_id])
    parent_contract = relationship("Contract", remote_side=[id], backref="child_contracts")
    obligations = relationship("ContractObligation", back_populates="contract", cascade="all, delete-orphan")
    deadlines = relationship("ContractDeadline", back_populates="contract", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_contracts_company_status", "company_id", "status"),
        Index("ix_contracts_company_type", "company_id", "contract_type"),
        Index("ix_contracts_expiration", "expiration_date"),
        Index("ix_contracts_effective", "effective_date"),
        CheckConstraint(
            "risk_score IS NULL OR (risk_score >= 0 AND risk_score <= 100)",
            name="ck_contracts_risk_score",
        ),
    )

    def to_dict(self) -> dict:
        """Convert contract to dictionary for API responses."""
        return {
            "id": str(self.id),
            "document_id": str(self.document_id) if self.document_id else None,
            "contract_number": self.contract_number,
            "title": self.title,
            "description": self.description,
            "contract_type": self.contract_type,
            "status": self.status,
            "parties": self.parties or [],
            "our_role": self.our_role,
            "counterparty_entity_id": str(self.counterparty_entity_id) if self.counterparty_entity_id else None,
            "effective_date": self.effective_date.isoformat() if self.effective_date else None,
            "expiration_date": self.expiration_date.isoformat() if self.expiration_date else None,
            "signed_date": self.signed_date.isoformat() if self.signed_date else None,
            "auto_renewal": self.auto_renewal,
            "renewal_period_months": self.renewal_period_months,
            "renewal_notice_days": self.renewal_notice_days,
            "notice_period_days": self.notice_period_days,
            "total_value": float(self.total_value) if self.total_value else None,
            "currency": self.currency,
            "payment_terms": self.payment_terms or {},
            "clauses": self.clauses or {},
            "signatures": self.signatures or [],
            "risk_score": self.risk_score,
            "risk_factors": self.risk_factors or [],
            "extraction_confidence": float(self.extraction_confidence) if self.extraction_confidence else None,
            "version_number": self.version_number,
            "company_id": str(self.company_id),
            "tags": self.tags or [],
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class ContractObligation(Base):
    """
    Vertragspflichten und -verpflichtungen.

    Trackt wiederkehrende und einmalige Pflichten aus Vertraegen
    inkl. Erinnerungen und Status-Tracking.
    """
    __tablename__ = "contract_obligations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Verknuepfung zum Vertrag
    contract_id = Column(
        UUID(as_uuid=True),
        ForeignKey("contracts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Pflicht-Details
    obligation_type = Column(
        String(30),
        nullable=False,
        default=ObligationType.OTHER.value,
    )
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)

    # Zustaendigkeit
    responsible_party = Column(String(50), nullable=True)  # "us", "them", "both"
    assignee_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Faelligkeit
    due_date = Column(Date, nullable=True, index=True)

    # Wiederholung
    recurring = Column(Boolean, default=False)
    recurrence_pattern = Column(String(20), nullable=True)  # RecurrencePattern value
    recurrence_end_date = Column(Date, nullable=True)
    next_occurrence_date = Column(Date, nullable=True, index=True)

    # Status
    status = Column(
        String(20),
        nullable=False,
        default=ObligationStatus.PENDING.value,
        index=True,
    )
    completed_at = Column(DateTime(timezone=True), nullable=True)
    completed_by_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Erinnerungen
    reminder_days = Column(Integer, default=7)  # Tage vor Faelligkeit
    reminder_sent = Column(Boolean, default=False)
    reminder_sent_at = Column(DateTime(timezone=True), nullable=True)

    # Finanzieller Wert (falls relevant)
    amount = Column(Numeric(15, 2), nullable=True)
    currency = Column(String(3), default="EUR")

    # Zusaetzliche Metadaten
    metadata = Column(CrossDBJSON, default=dict)

    # Multi-Tenant
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Zeitstempel
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    contract = relationship("Contract", back_populates="obligations")
    assignee = relationship("User", foreign_keys=[assignee_id])
    completed_by = relationship("User", foreign_keys=[completed_by_id])
    company = relationship("Company", backref="contract_obligations")

    __table_args__ = (
        Index("ix_obligations_contract_status", "contract_id", "status"),
        Index("ix_obligations_due_date", "due_date"),
        Index("ix_obligations_next_occurrence", "next_occurrence_date"),
        Index("ix_obligations_company_status", "company_id", "status"),
    )

    def to_dict(self) -> dict:
        """Convert obligation to dictionary for API responses."""
        return {
            "id": str(self.id),
            "contract_id": str(self.contract_id),
            "obligation_type": self.obligation_type,
            "title": self.title,
            "description": self.description,
            "responsible_party": self.responsible_party,
            "assignee_id": str(self.assignee_id) if self.assignee_id else None,
            "due_date": self.due_date.isoformat() if self.due_date else None,
            "recurring": self.recurring,
            "recurrence_pattern": self.recurrence_pattern,
            "next_occurrence_date": self.next_occurrence_date.isoformat() if self.next_occurrence_date else None,
            "status": self.status,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "reminder_days": self.reminder_days,
            "amount": float(self.amount) if self.amount else None,
            "currency": self.currency,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class ContractDeadline(Base):
    """
    Vertragsfristen und wichtige Termine.

    Trackt alle wichtigen Termine wie Kuendigungsfristen,
    Verlaengerungen, Preisanpassungen etc.
    """
    __tablename__ = "contract_deadlines"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Verknuepfung zum Vertrag
    contract_id = Column(
        UUID(as_uuid=True),
        ForeignKey("contracts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Frist-Details
    deadline_type = Column(String(50), nullable=False)
    # Typen: termination_notice, renewal_decision, price_adjustment,
    #        contract_expiry, warranty_expiry, audit_due, etc.

    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)

    # Datum
    deadline_date = Column(Date, nullable=False, index=True)

    # Prioritaet
    priority = Column(String(20), default="medium")  # low, medium, high, critical

    # Status
    is_completed = Column(Boolean, default=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    completed_by_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    action_taken = Column(Text, nullable=True)

    # Erinnerungen
    reminder_days_before = Column(CrossDBJSON, default=lambda: [30, 14, 7, 1])
    # Liste der Tage vor Frist fuer Erinnerungen
    last_reminder_sent = Column(DateTime(timezone=True), nullable=True)

    # Zustaendigkeit
    assignee_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Multi-Tenant
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Zeitstempel
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    contract = relationship("Contract", back_populates="deadlines")
    assignee = relationship("User", foreign_keys=[assignee_id])
    completed_by = relationship("User", foreign_keys=[completed_by_id])
    company = relationship("Company", backref="contract_deadlines")

    __table_args__ = (
        Index("ix_deadlines_contract", "contract_id"),
        Index("ix_deadlines_date", "deadline_date"),
        Index("ix_deadlines_company_pending", "company_id", "is_completed"),
    )

    def to_dict(self) -> dict:
        """Convert deadline to dictionary for API responses."""
        return {
            "id": str(self.id),
            "contract_id": str(self.contract_id),
            "deadline_type": self.deadline_type,
            "title": self.title,
            "description": self.description,
            "deadline_date": self.deadline_date.isoformat() if self.deadline_date else None,
            "priority": self.priority,
            "is_completed": self.is_completed,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "action_taken": self.action_taken,
            "reminder_days_before": self.reminder_days_before or [30, 14, 7, 1],
            "assignee_id": str(self.assignee_id) if self.assignee_id else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class ContractComparison(Base):
    """
    Vertragsvergleiche zwischen Versionen.

    Speichert Vergleichsergebnisse fuer Audit-Trail
    und Nachvollziehbarkeit.
    """
    __tablename__ = "contract_comparisons"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Verglichene Vertraege
    contract_a_id = Column(
        UUID(as_uuid=True),
        ForeignKey("contracts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    contract_b_id = Column(
        UUID(as_uuid=True),
        ForeignKey("contracts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Vergleichsergebnis
    differences = Column(CrossDBJSON, nullable=False, default=list)
    # Format: [{"field": "total_value", "old": 10000, "new": 12000, "change_type": "modified"}]

    similarity_score = Column(Numeric(5, 4), nullable=True)  # 0.0 - 1.0

    # Kategorisierte Aenderungen
    added_clauses = Column(CrossDBJSON, default=list)
    removed_clauses = Column(CrossDBJSON, default=list)
    modified_clauses = Column(CrossDBJSON, default=list)

    # Risiko-Bewertung der Aenderungen
    risk_impact = Column(Integer, nullable=True)  # -100 bis +100
    risk_summary = Column(Text, nullable=True)

    # Multi-Tenant
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Erstellt von
    created_by_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Zeitstempel
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    contract_a = relationship("Contract", foreign_keys=[contract_a_id])
    contract_b = relationship("Contract", foreign_keys=[contract_b_id])
    company = relationship("Company", backref="contract_comparisons")
    created_by = relationship("User", foreign_keys=[created_by_id])

    __table_args__ = (
        Index("ix_comparisons_contracts", "contract_a_id", "contract_b_id"),
    )


# =============================================================================
# Contract Clause Model (V2 Enhancement)
# =============================================================================


class ClauseType(str, Enum):
    """Typen von Vertragsklauseln."""
    PRICE_ADJUSTMENT = "price_adjustment"      # Preisanpassungsklausel
    MINIMUM_TERM = "minimum_term"              # Mindestlaufzeit
    AUTO_RENEWAL = "auto_renewal"              # Automatische Verlaengerung
    PENALTY = "penalty"                        # Vertragsstrafe
    TERMINATION_CONDITION = "termination"      # Kuendigungsbedingungen
    LIABILITY = "liability"                    # Haftungsbegrenzung
    CONFIDENTIALITY = "confidentiality"        # Geheimhaltung
    WARRANTY = "warranty"                      # Gewaehrleistung
    JURISDICTION = "jurisdiction"              # Gerichtsstand
    PAYMENT_TERMS = "payment_terms"            # Zahlungsbedingungen
    FORCE_MAJEURE = "force_majeure"            # Hoehere Gewalt
    INTELLECTUAL_PROPERTY = "ip"               # Geistiges Eigentum
    DATA_PROTECTION = "data_protection"        # Datenschutz
    COMPLIANCE = "compliance"                  # Compliance-Anforderungen
    ESCALATION = "escalation"                  # Eskalationsklausel
    SERVICE_LEVEL = "service_level"            # SLA-Klausel
    OTHER = "other"                            # Sonstige


class ContractClause(Base):
    """
    Extrahierte Vertragsklauseln.

    Speichert aus Vertraegen extrahierte Klauseln mit
    strukturierten Werten und Risikoeinschaetzung.
    """
    __tablename__ = "contract_clauses"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Verknuepfungen
    contract_id = Column(
        UUID(as_uuid=True),
        ForeignKey("contracts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Klausel-Identifikation
    clause_type = Column(
        String(50),
        nullable=False,
        index=True,
    )
    clause_text = Column(Text, nullable=False)
    clause_text_hash = Column(String(64), nullable=True)

    # Extraktion
    confidence = Column(Numeric(5, 4), nullable=False, default=0.0)
    extraction_method = Column(String(50), nullable=True)  # nlp, regex, manual
    source_page = Column(Integer, nullable=True)
    source_position = Column(CrossDBJSON, nullable=True)

    # Strukturierte extrahierte Werte
    extracted_value = Column(CrossDBJSON, nullable=True)

    # Status
    is_active = Column(Boolean, default=True, nullable=False)
    is_verified = Column(Boolean, default=False, nullable=False)
    verified_by_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    verified_at = Column(DateTime(timezone=True), nullable=True)

    # Risikobewertung
    risk_level = Column(String(20), nullable=True)  # low, medium, high, critical
    risk_notes = Column(Text, nullable=True)

    # Zeitstempel
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    contract = relationship("Contract", backref="extracted_clauses")
    company = relationship("Company", backref="contract_clauses")
    verified_by = relationship("User", foreign_keys=[verified_by_id])

    __table_args__ = (
        Index("ix_contract_clauses_contract_type", "contract_id", "clause_type"),
        Index("ix_contract_clauses_company_type", "company_id", "clause_type"),
        Index("ix_contract_clauses_text_hash", "clause_text_hash"),
    )

    def to_dict(self) -> dict:
        """Convert clause to dictionary for API responses."""
        return {
            "id": str(self.id),
            "contract_id": str(self.contract_id),
            "clause_type": self.clause_type,
            "clause_text": self.clause_text[:500] + "..." if len(self.clause_text) > 500 else self.clause_text,
            "confidence": float(self.confidence) if self.confidence else 0.0,
            "extraction_method": self.extraction_method,
            "source_page": self.source_page,
            "extracted_value": self.extracted_value or {},
            "is_verified": self.is_verified,
            "risk_level": self.risk_level,
            "risk_notes": self.risk_notes,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


# =============================================================================
# Contract Benchmark Model (V2 Enhancement)
# =============================================================================


class ContractBenchmark(Base):
    """
    Markt-Benchmark-Daten fuer Vertragsvergleiche.

    Speichert Durchschnittswerte und Statistiken
    fuer verschiedene Vertragskategorien.
    """
    __tablename__ = "contract_benchmarks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Kategorie und Metrik
    category = Column(String(100), nullable=False, index=True)
    metric = Column(String(100), nullable=False, index=True)

    # Werte und Statistiken
    value = Column(Numeric(15, 4), nullable=False)
    min_value = Column(Numeric(15, 4), nullable=True)
    max_value = Column(Numeric(15, 4), nullable=True)
    percentile_25 = Column(Numeric(15, 4), nullable=True)
    percentile_50 = Column(Numeric(15, 4), nullable=True)
    percentile_75 = Column(Numeric(15, 4), nullable=True)
    std_deviation = Column(Numeric(15, 4), nullable=True)

    # Sample und Gueltigkeit
    sample_size = Column(Integer, nullable=False, default=0)
    region = Column(String(50), default="DACH", nullable=False)
    industry = Column(String(100), nullable=True)
    valid_from = Column(Date, nullable=False)
    valid_until = Column(Date, nullable=True)

    # Quelle
    source = Column(String(255), nullable=True)
    source_url = Column(String(500), nullable=True)

    # Metadaten
    notes = Column(Text, nullable=True)
    metadata = Column(CrossDBJSON, nullable=True)

    # Zeitstempel
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("ix_benchmarks_category_metric", "category", "metric"),
        Index("ix_benchmarks_region_industry", "region", "industry"),
        Index("ix_benchmarks_valid_from", "valid_from"),
    )

    def to_dict(self) -> dict:
        """Convert benchmark to dictionary."""
        return {
            "id": str(self.id),
            "category": self.category,
            "metric": self.metric,
            "value": float(self.value) if self.value else None,
            "min_value": float(self.min_value) if self.min_value else None,
            "max_value": float(self.max_value) if self.max_value else None,
            "percentile_25": float(self.percentile_25) if self.percentile_25 else None,
            "percentile_50": float(self.percentile_50) if self.percentile_50 else None,
            "percentile_75": float(self.percentile_75) if self.percentile_75 else None,
            "sample_size": self.sample_size,
            "region": self.region,
            "industry": self.industry,
            "valid_from": self.valid_from.isoformat() if self.valid_from else None,
            "source": self.source,
        }


# =============================================================================
# Contract Cancellation Model (V2 Enhancement)
# =============================================================================


class CancellationStatus(str, Enum):
    """Status der Kuendigung."""
    DRAFT = "draft"                    # Entwurf
    PENDING = "pending"                # Warten auf Genehmigung
    SCHEDULED = "scheduled"            # Geplant fuer Versand
    SENT = "sent"                      # Gesendet
    ACKNOWLEDGED = "acknowledged"      # Bestaetigt
    REJECTED = "rejected"              # Abgelehnt
    COMPLETED = "completed"            # Abgeschlossen
    CANCELLED = "cancelled"            # Abgebrochen


class CancellationType(str, Enum):
    """Art der Kuendigung."""
    ORDINARY = "ordinary"              # Ordentliche Kuendigung
    EXTRAORDINARY = "extraordinary"    # Ausserordentliche Kuendigung
    MUTUAL = "mutual"                  # Einvernehmliche Aufhebung


class ContractCancellation(Base):
    """
    Kuendigungsanfragen und -verfolgung.

    Verwaltet den gesamten Kuendigungsprozess
    von der Anfrage bis zur Bestaetigung.
    """
    __tablename__ = "contract_cancellations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Verknuepfungen
    contract_id = Column(
        UUID(as_uuid=True),
        ForeignKey("contracts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Kuendigungsdetails
    cancellation_type = Column(String(50), nullable=False)
    reason = Column(Text, nullable=True)
    reason_code = Column(String(50), nullable=True)

    # Termine
    requested_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    effective_date = Column(Date, nullable=False)
    latest_send_date = Column(Date, nullable=False)
    scheduled_send_date = Column(Date, nullable=True)

    # Kuendigungsschreiben
    letter_template = Column(String(100), nullable=True)
    letter_content = Column(Text, nullable=True)
    letter_language = Column(String(10), default="de", nullable=False)
    recipient_name = Column(String(255), nullable=True)
    recipient_address = Column(Text, nullable=True)
    recipient_email = Column(String(255), nullable=True)

    # Versand
    send_method = Column(String(50), nullable=True)
    sent_at = Column(DateTime(timezone=True), nullable=True)
    sent_by_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    sent_reference = Column(String(255), nullable=True)

    # Bestaetigung
    acknowledgment_received = Column(Boolean, default=False, nullable=False)
    acknowledgment_date = Column(DateTime(timezone=True), nullable=True)
    acknowledgment_reference = Column(String(255), nullable=True)
    acknowledgment_document_id = Column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Status
    status = Column(String(30), nullable=False, default=CancellationStatus.DRAFT.value)

    # Workflow
    requested_by_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    approved_by_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    approved_at = Column(DateTime(timezone=True), nullable=True)

    # Metadaten
    metadata = Column(CrossDBJSON, nullable=True)
    notes = Column(Text, nullable=True)

    # Zeitstempel
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    contract = relationship("Contract", backref="cancellations")
    company = relationship("Company", backref="contract_cancellations")
    sent_by = relationship("User", foreign_keys=[sent_by_id])
    requested_by = relationship("User", foreign_keys=[requested_by_id])
    approved_by = relationship("User", foreign_keys=[approved_by_id])
    acknowledgment_document = relationship("Document", backref="cancellation_acknowledgments")

    __table_args__ = (
        Index("ix_cancellations_contract", "contract_id"),
        Index("ix_cancellations_company_status", "company_id", "status"),
        Index("ix_cancellations_effective_date", "effective_date"),
        Index("ix_cancellations_scheduled_send", "scheduled_send_date", "status"),
    )

    def to_dict(self) -> dict:
        """Convert cancellation to dictionary for API responses."""
        return {
            "id": str(self.id),
            "contract_id": str(self.contract_id),
            "cancellation_type": self.cancellation_type,
            "reason": self.reason,
            "reason_code": self.reason_code,
            "effective_date": self.effective_date.isoformat() if self.effective_date else None,
            "latest_send_date": self.latest_send_date.isoformat() if self.latest_send_date else None,
            "scheduled_send_date": self.scheduled_send_date.isoformat() if self.scheduled_send_date else None,
            "status": self.status,
            "send_method": self.send_method,
            "sent_at": self.sent_at.isoformat() if self.sent_at else None,
            "acknowledgment_received": self.acknowledgment_received,
            "acknowledgment_date": self.acknowledgment_date.isoformat() if self.acknowledgment_date else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


# =============================================================================
# Contract Cost Analysis Model (V2 Enhancement)
# =============================================================================


class ContractCostAnalysis(Base):
    """
    Kostenanalyse fuer Vertraege.

    Cached berechnete Kostenmetriken und
    Optimierungsvorschlaege.
    """
    __tablename__ = "contract_cost_analyses"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Verknuepfungen
    contract_id = Column(
        UUID(as_uuid=True),
        ForeignKey("contracts.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Kostenprojektionen
    monthly_cost = Column(Numeric(15, 2), nullable=True)
    annual_cost = Column(Numeric(15, 2), nullable=True)
    total_contract_cost = Column(Numeric(15, 2), nullable=True)
    remaining_cost = Column(Numeric(15, 2), nullable=True)
    currency = Column(String(3), default="EUR", nullable=False)

    # Kostenaufschluesselung
    cost_breakdown = Column(CrossDBJSON, nullable=True)

    # Trendanalyse
    cost_trend = Column(String(20), nullable=True)  # increasing, stable, decreasing
    trend_percent = Column(Numeric(5, 2), nullable=True)
    cost_history = Column(CrossDBJSON, nullable=True)

    # Optimierung
    optimization_potential = Column(Numeric(15, 2), nullable=True)
    optimization_suggestions = Column(CrossDBJSON, nullable=True)

    # Benchmark-Vergleich
    benchmark_comparison = Column(CrossDBJSON, nullable=True)

    # Analyse-Metadaten
    analyzed_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    analysis_version = Column(String(20), nullable=True)

    # Zeitstempel
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    contract = relationship("Contract", backref="cost_analysis", uselist=False)
    company = relationship("Company", backref="contract_cost_analyses")

    __table_args__ = (
        Index("ix_cost_analyses_company", "company_id"),
        Index("ix_cost_analyses_trend", "cost_trend"),
    )

    def to_dict(self) -> dict:
        """Convert cost analysis to dictionary for API responses."""
        return {
            "id": str(self.id),
            "contract_id": str(self.contract_id),
            "monthly_cost": float(self.monthly_cost) if self.monthly_cost else None,
            "annual_cost": float(self.annual_cost) if self.annual_cost else None,
            "total_contract_cost": float(self.total_contract_cost) if self.total_contract_cost else None,
            "remaining_cost": float(self.remaining_cost) if self.remaining_cost else None,
            "currency": self.currency,
            "cost_breakdown": self.cost_breakdown or {},
            "cost_trend": self.cost_trend,
            "trend_percent": float(self.trend_percent) if self.trend_percent else None,
            "cost_history": self.cost_history or [],
            "optimization_potential": float(self.optimization_potential) if self.optimization_potential else None,
            "optimization_suggestions": self.optimization_suggestions or [],
            "benchmark_comparison": self.benchmark_comparison or {},
            "analyzed_at": self.analyzed_at.isoformat() if self.analyzed_at else None,
        }
