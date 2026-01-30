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
