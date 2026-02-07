# -*- coding: utf-8 -*-
"""
Database models for GL-Posting System (General Ledger).

Feature 2.1: GL-Posting Service
- Journal Entries (Buchungssaetze)
- Journal Entry Lines (Buchungszeilen)
- Tax Periods (Steuerperioden/USt-VA)
- GL Accounts (Sachkonten SKR03/SKR04)

GoBD-konform: Keine Loeschungen, nur Stornierungen.

SECURITY NOTES:
- NEVER log journal entry details in production (GoBD confidential)
- All GL posting operations are audit-logged
- Reversals create opposite entries (no deletion)
"""

from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Optional, List
import uuid

from sqlalchemy import (
    Column, String, Integer, Date, DateTime, Boolean, Numeric,
    ForeignKey, Index, UniqueConstraint, CheckConstraint
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.models import Base, CrossDBJSON


# =============================================================================
# Enums
# =============================================================================

class JournalEntryStatus(str, Enum):
    """Journal entry status."""
    DRAFT = "draft"               # Entwurf (editierbar)
    POSTED = "posted"             # Gebucht (nicht mehr editierbar)
    REVERSED = "reversed"         # Storniert
    LOCKED = "locked"             # Gesperrt (z.B. nach Jahresabschluss)


class JournalEntrySource(str, Enum):
    """Source of journal entry."""
    MANUAL = "manual"             # Manuelle Erfassung
    AUTO_BOOKING = "auto_booking" # Automatische Buchung aus OCR
    IMPORT = "import"             # Import (DATEV, CSV)
    PIPELINE = "pipeline"         # Document Pipeline


class TaxPeriodStatus(str, Enum):
    """Tax period status."""
    OPEN = "open"                 # Offen fuer Buchungen
    FILED = "filed"               # USt-VA eingereicht
    ACCEPTED = "accepted"         # Vom Finanzamt akzeptiert
    CORRECTED = "corrected"       # Korrigiert


class TaxPeriodType(str, Enum):
    """Tax period type."""
    MONTHLY = "monthly"           # Monatlich
    QUARTERLY = "quarterly"       # Quartalsweise


# =============================================================================
# GL Account Model
# =============================================================================

class GLAccount(Base):
    """
    General Ledger Account (Sachkonto).

    Unterstuetzt SKR03 und SKR04.
    Standard-Konten werden vorgeladen, Custom-Konten per Company.
    """
    __tablename__ = "gl_accounts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Account Definition
    account_number = Column(String(5), nullable=False, comment="Kontonummer (z.B. 1200)")
    account_name = Column(String(100), nullable=False, comment="Kontobezeichnung")
    account_class = Column(
        Integer,
        nullable=False,
        comment="Kontenklasse 0-9"
    )

    # Flags
    is_custom = Column(
        Boolean,
        default=False,
        comment="True = Custom Account, False = Standard SKR03/04"
    )
    is_active = Column(Boolean, default=True)

    # Default Tax Settings
    default_tax_code = Column(
        String(10),
        nullable=True,
        comment="Standard BU-Schluessel (DATEV)"
    )

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    company = relationship("Company", backref="gl_accounts")

    __table_args__ = (
        UniqueConstraint("company_id", "account_number", name="uq_gl_account_company_number"),
        Index("ix_gl_accounts_company_active", "company_id", "is_active"),
        Index("ix_gl_accounts_account_class", "account_class"),
        CheckConstraint(
            "account_class >= 0 AND account_class <= 9",
            name="ck_gl_account_class_range"
        ),
    )


# =============================================================================
# Journal Entry Models
# =============================================================================

class JournalEntry(Base):
    """
    Journal Entry (Buchungssatz).

    Ein Buchungssatz besteht aus mindestens 2 Zeilen (Soll/Haben).
    Die Summe der Soll-Betraege muss gleich der Summe der Haben-Betraege sein.

    GoBD-konform: Keine Loeschung, nur Stornierung via reversed_by_entry_id.
    """
    __tablename__ = "journal_entries"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    document_id = Column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="SET NULL"),
        nullable=True,
        comment="Verknuepftes Dokument (optional)"
    )

    # Period Assignment
    posting_date = Column(Date, nullable=False, comment="Buchungsdatum")
    fiscal_year = Column(Integer, nullable=False, comment="Geschaeftsjahr")
    fiscal_period = Column(
        Integer,
        nullable=False,
        comment="Periode 1-12 (Monat)"
    )

    # Entry Identification
    entry_number = Column(
        String(20),
        nullable=False,
        comment="Buchungsnummer (z.B. JE-2024-00001)"
    )
    description = Column(
        String(60),
        nullable=True,
        comment="Buchungsbeschreibung"
    )

    # Totals (for quick reference)
    total_amount = Column(
        Numeric(15, 2),
        nullable=True,
        comment="Gesamtbetrag (Soll = Haben)"
    )
    currency = Column(String(3), default="EUR")
    exchange_rate = Column(
        Numeric(18, 8),
        nullable=True,
        comment="Wechselkurs (wenn Fremdwaehrung)"
    )

    # Status
    status = Column(
        String(20),
        default=JournalEntryStatus.DRAFT.value,
        nullable=False
    )

    # Source Tracking
    source = Column(
        String(20),
        nullable=True,
        comment="Quelle: manual, auto_booking, import, pipeline"
    )
    confidence = Column(
        Numeric(3, 2),
        nullable=True,
        comment="Confidence fuer Auto-Bookings (0.00-1.00)"
    )

    # Posting Audit
    created_by_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )
    posted_by_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )
    posted_at = Column(DateTime(timezone=True), nullable=True)

    # Reversal (GoBD: No deletion, only reversal)
    reversed_by_entry_id = Column(
        UUID(as_uuid=True),
        ForeignKey("journal_entries.id", ondelete="SET NULL"),
        nullable=True,
        comment="ID des Storno-Buchungssatzes"
    )

    # Metadata
    metadata_json = Column(
        CrossDBJSON,
        nullable=True,
        comment="Zusaetzliche Metadaten (flexible Erweiterung)"
    )

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    company = relationship("Company", backref="journal_entries")
    document = relationship("Document", foreign_keys=[document_id])
    created_by = relationship("User", foreign_keys=[created_by_id])
    posted_by = relationship("User", foreign_keys=[posted_by_id])
    reversed_by_entry = relationship("JournalEntry", remote_side=[id], foreign_keys=[reversed_by_entry_id])
    lines = relationship(
        "JournalEntryLine",
        back_populates="entry",
        cascade="all, delete-orphan",
        order_by="JournalEntryLine.line_number"
    )

    __table_args__ = (
        UniqueConstraint("company_id", "entry_number", name="uq_journal_entry_number"),
        Index("ix_journal_entries_company_period", "company_id", "fiscal_year", "fiscal_period"),
        Index("ix_journal_entries_posting_date", "posting_date"),
        Index("ix_journal_entries_status", "status"),
        Index("ix_journal_entries_document", "document_id"),
        CheckConstraint(
            "fiscal_period >= 1 AND fiscal_period <= 12",
            name="ck_journal_entry_period_range"
        ),
    )


class JournalEntryLine(Base):
    """
    Journal Entry Line (Buchungszeile).

    Jeder Buchungssatz hat mindestens 2 Zeilen:
    - Soll-Buchung (debit_amount > 0)
    - Haben-Buchung (credit_amount > 0)

    Eine Zeile darf NICHT gleichzeitig Soll UND Haben haben.
    """
    __tablename__ = "journal_entry_lines"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    entry_id = Column(
        UUID(as_uuid=True),
        ForeignKey("journal_entries.id", ondelete="CASCADE"),
        nullable=False
    )

    # Line Position
    line_number = Column(
        Integer,
        nullable=False,
        comment="Zeilennummer innerhalb des Buchungssatzes"
    )

    # Account Assignment
    account_number = Column(
        String(5),
        nullable=False,
        comment="Kontonummer (SKR03/04)"
    )
    account_name = Column(
        String(100),
        nullable=True,
        comment="Kontobezeichnung (redundant fuer Performance)"
    )

    # Amounts (one must be > 0, not both)
    debit_amount = Column(
        Numeric(15, 2),
        default=0,
        nullable=False,
        comment="Soll-Betrag"
    )
    credit_amount = Column(
        Numeric(15, 2),
        default=0,
        nullable=False,
        comment="Haben-Betrag"
    )

    # Tax Assignment
    tax_code = Column(
        String(10),
        nullable=True,
        comment="DATEV BU-Schluessel (z.B. 40 fuer 19% Vorsteuer)"
    )
    tax_rate = Column(
        Numeric(5, 2),
        nullable=True,
        comment="Steuersatz in Prozent (z.B. 19.00)"
    )
    tax_amount = Column(
        Numeric(15, 2),
        nullable=True,
        comment="Steuerbetrag"
    )

    # Cost Accounting (optional)
    cost_center = Column(
        String(20),
        nullable=True,
        comment="Kostenstelle"
    )
    cost_object = Column(
        String(20),
        nullable=True,
        comment="Kostentraeger"
    )

    # Line Text
    text = Column(
        String(60),
        nullable=True,
        comment="Buchungstext (max 60 Zeichen wie DATEV)"
    )

    # Relationship
    entry = relationship("JournalEntry", back_populates="lines")

    __table_args__ = (
        Index("ix_journal_entry_lines_entry", "entry_id", "line_number"),
        Index("ix_journal_entry_lines_account", "account_number"),
        Index("ix_journal_entry_lines_tax_code", "tax_code"),
        CheckConstraint(
            "NOT (debit_amount > 0 AND credit_amount > 0)",
            name="ck_journal_line_not_both_debit_credit"
        ),
    )


# =============================================================================
# Tax Period Model
# =============================================================================

class TaxPeriod(Base):
    """
    Tax Period (Steuerperiode) for USt-VA.

    Tracks VAT reporting periods (monthly/quarterly).
    """
    __tablename__ = "tax_periods"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Period Definition
    fiscal_year = Column(Integer, nullable=False)
    period_type = Column(
        String(20),
        nullable=False,
        comment="monthly oder quarterly"
    )
    period_number = Column(
        Integer,
        nullable=False,
        comment="Monat 1-12 oder Quartal 1-4"
    )
    period_start = Column(Date, nullable=False)
    period_end = Column(Date, nullable=False)

    # Status
    status = Column(
        String(20),
        default=TaxPeriodStatus.OPEN.value,
        nullable=False
    )

    # VAT Summary (calculated from JournalEntryLines)
    total_output_vat = Column(
        Numeric(15, 2),
        default=0,
        nullable=False,
        comment="Umsatzsteuer (Output VAT)"
    )
    total_input_vat = Column(
        Numeric(15, 2),
        default=0,
        nullable=False,
        comment="Vorsteuer (Input VAT)"
    )
    vat_payable = Column(
        Numeric(15, 2),
        default=0,
        nullable=False,
        comment="Zahllast (Output - Input), positiv = Zahlung, negativ = Erstattung"
    )

    # Filing Tracking
    filed_at = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="Zeitpunkt der Einreichung bei ELSTER"
    )
    elster_transfer_ticket = Column(
        String(100),
        nullable=True,
        comment="ELSTER Transfer-Ticket"
    )

    # Report Data
    report_data = Column(
        CrossDBJSON,
        nullable=True,
        comment="Kompletter USt-VA Report als JSON"
    )

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    company = relationship("Company", backref="tax_periods")

    __table_args__ = (
        UniqueConstraint(
            "company_id", "fiscal_year", "period_type", "period_number",
            name="uq_tax_period_company_period"
        ),
        Index("ix_tax_periods_company_year", "company_id", "fiscal_year"),
        Index("ix_tax_periods_status", "status"),
        Index("ix_tax_periods_period_end", "period_end"),
    )
