"""Cash/Company domain models - extracted from models.py (Modularisierung Phase 1.1).

Enthält:
- CashEntryType, ExpenseReportStatus, ExpenseType (Enums)
- Company, UserCompany, CashRegister, CashEntry, CashCategory,
  CashCount, ExpenseReport, ExpenseItem (SQLAlchemy Models)
"""

import uuid
from datetime import date
from enum import Enum
from typing import List

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    Time,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, relationship
from sqlalchemy.sql import func

from app.db.models_base import Base, CrossDBJSON, SoftDeleteMixin

# =============================================================================
# KASSE-MODUL: ENUMS
# =============================================================================


class CashEntryType(str, Enum):
    """Typ der Kassenbuchung - GoBD-konform."""

    # Einnahmen
    INCOME = "income"                    # Allgemeine Einnahme
    DEPOSIT = "deposit"                  # Kasseneinlage von Bank
    REFUND_RECEIVED = "refund_received"  # Erstattung erhalten

    # Ausgaben
    EXPENSE = "expense"                  # Allgemeine Ausgabe
    WITHDRAWAL = "withdrawal"            # Kassenentnahme zur Bank
    ENTERTAINMENT = "entertainment"      # Bewirtungskosten (70% abzugsfaehig)
    TRAVEL = "travel"                    # Reisekosten
    OFFICE = "office"                    # Buerobedarf
    FUEL = "fuel"                        # Tankkosten
    PARKING = "parking"                  # Parkgebühren
    POSTAGE = "postage"                  # Porto
    TIPS = "tips"                        # Trinkgeld
    GIFTS = "gifts"                      # Geschenke

    # Sonder
    DIFFERENCE_PLUS = "difference_plus"   # Kassenmehrbestand
    DIFFERENCE_MINUS = "difference_minus" # Kassenfehlbestand
    CANCELLATION = "cancellation"         # Stornobuchung (Gegenbuchung)
    OPENING = "opening"                   # Eröffnungsbuchung


class ExpenseReportStatus(str, Enum):
    """Status einer Spesenabrechnung - Workflow."""

    DRAFT = "draft"           # Entwurf
    SUBMITTED = "submitted"   # Eingereicht
    IN_REVIEW = "in_review"   # In Prüfung
    APPROVED = "approved"     # Genehmigt
    REJECTED = "rejected"     # Abgelehnt
    PAID = "paid"             # Ausgezahlt


class ExpenseType(str, Enum):
    """Typ einer Spesenposition."""

    RECEIPT = "receipt"       # Belegausgabe
    MILEAGE = "mileage"       # Kilometergeld (0,30 EUR/km)
    PER_DIEM = "per_diem"     # Verpflegungspauschale (14/28 EUR)
    FLAT_RATE = "flat_rate"   # Sonstige Pauschale


# =============================================================================
# KASSE-MODUL: MULTI-COMPANY
# =============================================================================


class Company(SoftDeleteMixin, Base):
    """Firma/Mandant für Multi-Company Support.

    Ersetzt das bisherige CompanySettings-Singleton und ermöglicht
    die Verwaltung mehrerer Firmen pro Installation.

    Jede Firma hat eigene Kassen, Spesenfreigaben und Einstellungen.
    Row-Level Security (RLS) isoliert Mandanten-Daten.
    """

    __tablename__ = "companies"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Identifikation
    name = Column(String(255), nullable=False)
    short_name = Column(String(50), nullable=True)
    display_name = Column(String(255), nullable=True)

    # Rechtsform & Register
    legal_form = Column(String(50), nullable=True)  # GmbH, UG, AG, etc.
    commercial_register = Column(String(100), nullable=True)
    court = Column(String(100), nullable=True)

    # Steuer
    vat_id = Column(String(20), unique=True, nullable=True)  # DE123456789
    tax_number = Column(String(50), nullable=True)

    # Adresse
    street = Column(String(255), nullable=True)
    street_number = Column(String(20), nullable=True)
    postal_code = Column(String(10), nullable=True)
    city = Column(String(100), nullable=True)
    country = Column(String(2), default="DE")

    # Kontakt
    email = Column(String(255), nullable=True)
    phone = Column(String(50), nullable=True)
    website = Column(String(255), nullable=True)

    # Banking (Hauptkonto)
    iban = Column(String(34), nullable=True)
    bic = Column(String(11), nullable=True)
    bank_name = Column(String(100), nullable=True)

    # Alternative Namen für OCR-Erkennung
    alternative_names = Column(CrossDBJSON, default=list)

    # Einstellungen
    default_currency = Column(String(3), default="EUR")
    fiscal_year_start = Column(Integer, default=1)  # Monat (1=Januar)
    kontenrahmen = Column(String(10), default="SKR03")  # SKR03 oder SKR04

    # Status
    is_active = Column(Boolean, default=True)
    is_default = Column(Boolean, default=False)

    # ==================== Subscription/Multi-Tenant ====================
    # Abonnement-Stufe: free, basic, professional, enterprise
    subscription_tier = Column(String(50), nullable=False, default="free")
    subscription_started_at = Column(DateTime(timezone=True), nullable=True)
    subscription_expires_at = Column(DateTime(timezone=True), nullable=True)

    # Billing-Informationen
    billing_email = Column(String(255), nullable=True)
    billing_address = Column(CrossDBJSON, default=dict)
    payment_method = Column(String(50), nullable=True)  # invoice, sepa, card

    # Tenant-Limits (überschreibbar pro Tier)
    max_users = Column(Integer, nullable=False, default=5)
    max_documents_per_month = Column(Integer, nullable=False, default=100)
    max_storage_gb = Column(Integer, nullable=False, default=5)

    # Aktivierte Features als JSON-Array
    features_enabled = Column(CrossDBJSON, default=lambda: ["ocr", "search", "export"])

    # Auto-Filing Rules (Phase 11.2)
    filing_rules = Column(
        CrossDBJSON,
        default=dict,
        comment="Custom auto-filing rules: {'invoice': {'folder_id': 'uuid', 'folder_name': '...'}, ...}",
    )

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    created_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # Relationships
    user_associations = relationship("UserCompany", back_populates="company", cascade="all, delete-orphan")
    documents = relationship("Document", back_populates="company", cascade="all, delete-orphan")
    cash_registers = relationship("CashRegister", back_populates="company", cascade="all, delete-orphan")
    expense_reports = relationship("ExpenseReport", back_populates="company", cascade="all, delete-orphan")
    # Document Template relationships - imported from app.db.models.document_template
    document_templates = relationship("DocumentTemplate", back_populates="company", cascade="all, delete-orphan")
    # Tenant Rate Limit relationships
    rate_limits = relationship("TenantRateLimit", back_populates="company", cascade="all, delete-orphan")
    usage_metrics = relationship("TenantUsageMetrics", back_populates="company", cascade="all, delete-orphan")
    rate_limit_violations = relationship("RateLimitViolation", back_populates="company", cascade="all, delete-orphan")
    # BPMN Process Engine relationships (models in bpmn_models/bpmn.py, same Base)
    bpmn_process_definitions = relationship("ProcessDefinition", back_populates="company", cascade="all, delete-orphan")
    bpmn_process_instances = relationship("ProcessInstance", back_populates="company", cascade="all, delete-orphan")
    # Banking relationships (Migration 232)
    bank_accounts: Mapped[List["BankAccount"]] = relationship(
        "BankAccount",
        back_populates="company",
        cascade="all, delete-orphan",
    )
    bank_imports: Mapped[List["BankImport"]] = relationship(
        "BankImport",
        back_populates="company",
        cascade="all, delete-orphan",
    )
    payment_batches: Mapped[List["PaymentBatch"]] = relationship(
        "PaymentBatch",
        back_populates="company",
        cascade="all, delete-orphan",
    )
    payment_orders: Mapped[List["PaymentOrder"]] = relationship(
        "PaymentOrder",
        back_populates="company",
        cascade="all, delete-orphan",
    )
    dunning_records: Mapped[List["DunningRecord"]] = relationship(
        "DunningRecord",
        back_populates="company",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("ix_companies_vat_id", "vat_id"),
        Index("ix_companies_is_active", "is_active"),
        Index("ix_companies_is_default", "is_default"),
        Index("ix_companies_deleted_at", "deleted_at"),
        Index("ix_companies_name", "name"),
    )

    def __repr__(self) -> str:
        return f"<Company {self.name} ({self.id})>"


class UserCompany(Base):
    """Zuordnung User <-> Company mit granularen Berechtigungen.

    Ermöglicht Multi-Mandanten-Fähigkeit: Ein User kann
    Zugriff auf mehrere Firmen haben, mit unterschiedlichen Rechten.
    """

    __tablename__ = "user_companies"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)

    # Rolle
    role = Column(String(50), default="member")  # owner, admin, member, viewer

    # Granulare Berechtigungen für Kasse-Modul
    can_manage_cash = Column(Boolean, default=False)      # Kassenbuchungen erstellen
    can_approve_expenses = Column(Boolean, default=False) # Spesen genehmigen
    can_export_datev = Column(Boolean, default=False)     # DATEV-Export
    can_manage_settings = Column(Boolean, default=False)  # Firmeneinstellungen

    # Aktive Firma für Session
    is_current = Column(Boolean, default=False)

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    user = relationship("User", backref="company_associations")
    company = relationship("Company", back_populates="user_associations")

    __table_args__ = (
        Index("ix_user_companies_user_id", "user_id"),
        Index("ix_user_companies_company_id", "company_id"),
        Index("ix_user_companies_is_current", "is_current"),
        Index("ix_user_companies_role", "role"),
        # Migration 268: hoechstens EINE aktuelle Firma pro User. Verhindert
        # die is_current-Korruption, die MultipleResultsFound-500er in
        # get_user_current_company/get_user_company_id ausloeste.
        Index(
            "uq_user_companies_one_current",
            "user_id",
            unique=True,
            postgresql_where=is_current.is_(True),
        ),
        # UniqueConstraint wird in Migration erstellt
    )

    def __repr__(self) -> str:
        return f"<UserCompany user={self.user_id} company={self.company_id} role={self.role}>"


# =============================================================================
# KASSE-MODUL: KASSENBUCH (GoBD-KONFORM!)
# =============================================================================


class CashRegister(SoftDeleteMixin, Base):
    """Kasse/Bargeldbestand.

    Eine Firma kann mehrere Kassen haben (Hauptkasse, Portokasse, Nebenkasse).
    Jede Kasse führt ein eigenes Kassenbuch mit fortlaufender Nummerierung.
    """

    __tablename__ = "cash_registers"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)

    # Identifikation
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    register_number = Column(String(50), nullable=True)  # Interne Kassennummer

    # Währung & Limits
    currency = Column(String(3), default="EUR")
    max_balance = Column(Numeric(15, 2), nullable=True)  # Maximaler Kassenbestand
    warning_threshold = Column(Numeric(15, 2), nullable=True)  # Warnschwelle

    # Aktueller Stand (denormalisiert für Performance)
    current_balance = Column(Numeric(15, 2), default=0)
    balance_date = Column(DateTime(timezone=True), nullable=True)
    last_reconciliation_date = Column(DateTime(timezone=True), nullable=True)

    # Banking-Verknüpfung (für Entnahmen/Einlagen)
    linked_bank_account_id = Column(
        UUID(as_uuid=True),
        ForeignKey("bank_accounts.id", ondelete="SET NULL"),
        nullable=True
    )

    # Status
    is_active = Column(Boolean, default=True)
    is_default = Column(Boolean, default=False)

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    created_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # Relationships
    company = relationship("Company", back_populates="cash_registers")
    entries = relationship("CashEntry", back_populates="cash_register", order_by="CashEntry.entry_number")
    linked_bank_account = relationship("BankAccount")
    counts = relationship("CashCount", back_populates="cash_register")

    __table_args__ = (
        Index("ix_cash_registers_company_id", "company_id"),
        Index("ix_cash_registers_is_active", "is_active"),
        Index("ix_cash_registers_deleted_at", "deleted_at"),
        # Name muss pro Firma eindeutig sein
        Index("ix_cash_registers_company_name", "company_id", "name", unique=True),
    )

    def __repr__(self) -> str:
        return f"<CashRegister {self.name} ({self.current_balance} {self.currency})>"


class CashEntry(Base):
    """Kassenbucheintrag - APPEND-ONLY für GoBD-Compliance!

    WICHTIG: Diese Tabelle erlaubt KEINE Updates oder Deletes!
    Nach GoBD müssen Kassenbuchungen unveränderbar sein.
    Stornierungen erfolgen durch Gegenbuchung mit Verweis auf Original.

    Constraints:
    - entry_date darf NICHT in der Zukunft liegen
    - amount darf NICHT 0 sein
    - entry_number ist fortlaufend pro Kasse/Jahr - KEINE Lücken!
    - balance_after muss bei JEDER Buchung korrekt berechnet werden
    """

    __tablename__ = "cash_entries"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="RESTRICT"),  # RESTRICT - nicht CASCADE!
        nullable=False
    )
    cash_register_id = Column(
        UUID(as_uuid=True),
        ForeignKey("cash_registers.id", ondelete="RESTRICT"),  # RESTRICT!
        nullable=False
    )

    # Fortlaufende Nummer (pro Kasse/Jahr) - KEINE LUECKEN!
    entry_number = Column(Integer, nullable=False)
    fiscal_year = Column(Integer, nullable=False)

    # Buchungsdaten
    entry_date = Column(Date, nullable=False)  # Buchungsdatum
    value_date = Column(Date, nullable=False)  # Wertstellungsdatum

    # Betrag (positiv = Einnahme, negativ = Ausgabe)
    amount = Column(Numeric(15, 2), nullable=False)
    currency = Column(String(3), default="EUR")

    # Saldo NACH dieser Buchung (für Kassensturz)
    balance_after = Column(Numeric(15, 2), nullable=False)

    # Kategorisierung
    entry_type = Column(String(50), nullable=False)  # CashEntryType
    category_id = Column(UUID(as_uuid=True), ForeignKey("cash_categories.id", ondelete="SET NULL"), nullable=True)

    # Steuer
    tax_rate = Column(Numeric(5, 2), nullable=True)      # 0, 7, 19
    tax_amount = Column(Numeric(15, 2), nullable=True)   # MwSt-Betrag
    net_amount = Column(Numeric(15, 2), nullable=True)   # Netto-Betrag
    is_tax_deductible = Column(Boolean, default=True)
    deductible_percentage = Column(Integer, default=100)  # z.B. 70 bei Bewirtung

    # Beschreibung
    description = Column(Text, nullable=False)
    reference_number = Column(String(100), nullable=True)  # Belegnummer

    # Geschäftspartner
    counterparty_name = Column(String(255), nullable=True)
    counterparty_id = Column(UUID(as_uuid=True), ForeignKey("business_entities.id", ondelete="SET NULL"), nullable=True)

    # Verknüpfungen
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="SET NULL"), nullable=True)
    bank_transaction_id = Column(UUID(as_uuid=True), ForeignKey("bank_transactions.id", ondelete="SET NULL"), nullable=True)
    expense_report_id = Column(UUID(as_uuid=True), ForeignKey("expense_reports.id", ondelete="SET NULL"), nullable=True)

    # Storno-Handling (Gegenbuchung statt Löschung!)
    is_cancelled = Column(Boolean, default=False)
    cancelled_by_entry_id = Column(UUID(as_uuid=True), ForeignKey("cash_entries.id", ondelete="SET NULL"), nullable=True)
    cancellation_reason = Column(Text, nullable=True)

    # GoBD Audit Trail für Stornierungen
    cancelled_by_user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        comment="User der die Stornierung durchgeführt hat"
    )
    cancelled_at = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="Zeitpunkt der Stornierung (GoBD Audit Trail)"
    )

    # Bewirtungskosten-Spezifika (JSON)
    entertainment_data = Column(CrossDBJSON, nullable=True)
    # Schema: {"participants": ["Name1", "Name2"], "occasion": "Projektbesprechung", "location": "Restaurant XY"}

    # DATEV-Export
    datev_exported_at = Column(DateTime(timezone=True), nullable=True)
    datev_export_batch_id = Column(UUID(as_uuid=True), nullable=True)

    # Buchungskonten (SKR03/SKR04)
    debit_account = Column(String(10), nullable=True)   # Soll-Konto
    credit_account = Column(String(10), nullable=True)  # Haben-Konto
    cost_center = Column(String(50), nullable=True)     # Kostenstelle

    # Audit (UNVERAENDERBAR!)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    created_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)

    # Relationships
    cash_register = relationship("CashRegister", back_populates="entries")
    category = relationship("CashCategory")
    document = relationship("Document")
    bank_transaction = relationship("BankTransaction")
    counterparty = relationship("BusinessEntity")
    cancellation_entry = relationship("CashEntry", remote_side=[id])

    __table_args__ = (
        # Eindeutige Nummerierung pro Kasse/Jahr
        Index("ix_cash_entries_unique_number", "cash_register_id", "fiscal_year", "entry_number", unique=True),
        Index("ix_cash_entries_company_id", "company_id"),
        Index("ix_cash_entries_register_id", "cash_register_id"),
        Index("ix_cash_entries_date", "entry_date"),
        Index("ix_cash_entries_type", "entry_type"),
        Index("ix_cash_entries_document_id", "document_id"),
        Index("ix_cash_entries_cancelled", "is_cancelled"),
        Index("ix_cash_entries_datev", "datev_exported_at"),
        # Constraint: Betrag darf nicht 0 sein
        CheckConstraint("amount != 0", name="ck_cash_entries_amount_not_zero"),
        # Constraint: Kein Buchungsdatum in der Zukunft
        CheckConstraint("entry_date <= CURRENT_DATE", name="ck_cash_entries_no_future_date"),
    )

    def __repr__(self) -> str:
        return f"<CashEntry #{self.entry_number}/{self.fiscal_year} {self.amount} {self.currency}>"


class CashCategory(Base):
    """Kategorie für Kassenausgaben mit SKR-Kontenzuordnung.

    Vordefinierte Kategorien mit Mapping zu SKR03/SKR04 Konten.
    Unterstützt hierarchische Kategorien für detaillierte Auswertungen.
    """

    __tablename__ = "cash_categories"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=True  # NULL = System-Default Kategorien
    )

    # Identifikation
    name = Column(String(100), nullable=False)
    name_en = Column(String(100), nullable=True)  # Englischer Name
    description = Column(Text, nullable=True)
    icon = Column(String(50), nullable=True)   # Icon-Name
    color = Column(String(7), nullable=True)   # Hex-Farbe

    # Hierarchie
    parent_id = Column(UUID(as_uuid=True), ForeignKey("cash_categories.id", ondelete="SET NULL"), nullable=True)
    level = Column(Integer, default=0)
    path = Column(String(500), nullable=True)  # Materialisierter Pfad

    # Buchhaltung (SKR03/SKR04)
    skr03_account = Column(String(10), nullable=True)
    skr04_account = Column(String(10), nullable=True)
    default_tax_rate = Column(Numeric(5, 2), default=19)

    # Spezielle Typen
    category_type = Column(String(50), nullable=True)  # entertainment, travel, office, etc.
    is_entertainment = Column(Boolean, default=False)   # Bewirtungskosten?
    is_travel_expense = Column(Boolean, default=False)  # Reisekosten?
    deductible_percentage = Column(Integer, default=100)  # z.B. 70 bei Bewirtung

    # Vorsteuer
    allows_vat_deduction = Column(Boolean, default=True)

    # Status
    is_active = Column(Boolean, default=True)
    is_system = Column(Boolean, default=False)  # System-Kategorie (nicht löschbar)
    sort_order = Column(Integer, default=0)

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    parent = relationship("CashCategory", remote_side=[id])

    __table_args__ = (
        Index("ix_cash_categories_company_id", "company_id"),
        Index("ix_cash_categories_parent_id", "parent_id"),
        Index("ix_cash_categories_is_active", "is_active"),
        Index("ix_cash_categories_type", "category_type"),
        Index("ix_cash_categories_sort", "sort_order"),
    )

    def __repr__(self) -> str:
        return f"<CashCategory {self.name} (SKR03: {self.skr03_account})>"


class CashCount(Base):
    """Zaehlprotokoll für Kassensturz.

    Dokumentiert den physischen Bargeldbestand bei Kassensturz.
    Berechnet Differenz zu Soll-Bestand aus Kassenbuch.
    Bei Differenz wird automatisch eine Ausgleichsbuchung erstellt.
    """

    __tablename__ = "cash_counts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False
    )
    cash_register_id = Column(
        UUID(as_uuid=True),
        ForeignKey("cash_registers.id", ondelete="CASCADE"),
        nullable=False
    )

    # Zeitpunkt
    count_date = Column(Date, nullable=False)
    count_time = Column(Time, nullable=False)

    # Muenzen (Stückzahl)
    coins_1_cent = Column(Integer, default=0)
    coins_2_cent = Column(Integer, default=0)
    coins_5_cent = Column(Integer, default=0)
    coins_10_cent = Column(Integer, default=0)
    coins_20_cent = Column(Integer, default=0)
    coins_50_cent = Column(Integer, default=0)
    coins_1_euro = Column(Integer, default=0)
    coins_2_euro = Column(Integer, default=0)

    # Scheine (Stückzahl)
    notes_5_euro = Column(Integer, default=0)
    notes_10_euro = Column(Integer, default=0)
    notes_20_euro = Column(Integer, default=0)
    notes_50_euro = Column(Integer, default=0)
    notes_100_euro = Column(Integer, default=0)
    notes_200_euro = Column(Integer, default=0)
    notes_500_euro = Column(Integer, default=0)

    # Soll-Bestand (aus Kassenbuch)
    expected_total = Column(Numeric(15, 2), nullable=False)

    # Bei Differenz automatisch erstellte Buchung
    difference_entry_id = Column(UUID(as_uuid=True), ForeignKey("cash_entries.id", ondelete="SET NULL"), nullable=True)
    difference_explanation = Column(Text, nullable=True)

    # Signatur
    counted_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    verified_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    verified_at = Column(DateTime(timezone=True), nullable=True)

    notes = Column(Text, nullable=True)

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    cash_register = relationship("CashRegister", back_populates="counts")
    difference_entry = relationship("CashEntry")
    counted_by = relationship("User", foreign_keys=[counted_by_id])
    verified_by = relationship("User", foreign_keys=[verified_by_id])

    __table_args__ = (
        Index("ix_cash_counts_company_id", "company_id"),
        Index("ix_cash_counts_register_id", "cash_register_id"),
        Index("ix_cash_counts_date", "count_date"),
    )

    @property
    def total_coins(self) -> float:
        """Berechnet Summe aller Muenzen."""
        return (
            self.coins_1_cent * 0.01 +
            self.coins_2_cent * 0.02 +
            self.coins_5_cent * 0.05 +
            self.coins_10_cent * 0.10 +
            self.coins_20_cent * 0.20 +
            self.coins_50_cent * 0.50 +
            self.coins_1_euro * 1.00 +
            self.coins_2_euro * 2.00
        )

    @property
    def total_notes(self) -> float:
        """Berechnet Summe aller Scheine."""
        return (
            self.notes_5_euro * 5 +
            self.notes_10_euro * 10 +
            self.notes_20_euro * 20 +
            self.notes_50_euro * 50 +
            self.notes_100_euro * 100 +
            self.notes_200_euro * 200 +
            self.notes_500_euro * 500
        )

    @property
    def counted_total(self) -> float:
        """Berechnet Gesamtsumme (Ist-Bestand)."""
        return self.total_coins + self.total_notes

    @property
    def difference(self) -> float:
        """Berechnet Differenz (Ist - Soll)."""
        return self.counted_total - float(self.expected_total)

    def __repr__(self) -> str:
        return f"<CashCount {self.count_date} Ist={self.counted_total} Soll={self.expected_total}>"


# =============================================================================
# KASSE-MODUL: SPESENABRECHNUNG
# =============================================================================


class ExpenseReport(SoftDeleteMixin, Base):
    """Spesenabrechnung eines Mitarbeiters.

    Sammelt alle Spesenpositionen eines Zeitraums mit Workflow:
    Entwurf -> Eingereicht -> In Prüfung -> Genehmigt/Abgelehnt -> Ausgezahlt
    """

    __tablename__ = "expense_reports"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False
    )

    # Identifikation
    report_number = Column(String(50), nullable=False)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)

    # Zeitraum
    period_start = Column(Date, nullable=False)
    period_end = Column(Date, nullable=False)

    # Mitarbeiter
    employee_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    employee_name = Column(String(255), nullable=True)  # Denormalisiert

    # Betraege (berechnet aus Positionen)
    total_amount = Column(Numeric(15, 2), default=0)
    total_vat = Column(Numeric(15, 2), default=0)
    total_deductible = Column(Numeric(15, 2), default=0)

    # Reisekosten-Pauschalen
    travel_days = Column(Integer, default=0)
    travel_allowance_total = Column(Numeric(15, 2), default=0)

    # Kilometergeld
    total_kilometers = Column(Numeric(10, 2), default=0)
    mileage_allowance_total = Column(Numeric(15, 2), default=0)

    # Status-Workflow
    status = Column(String(50), default="draft")

    # Workflow-Timestamps
    submitted_at = Column(DateTime(timezone=True), nullable=True)
    submitted_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    reviewed_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    review_notes = Column(Text, nullable=True)

    approved_at = Column(DateTime(timezone=True), nullable=True)
    approved_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    rejected_at = Column(DateTime(timezone=True), nullable=True)
    rejected_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    rejection_reason = Column(Text, nullable=True)

    paid_at = Column(DateTime(timezone=True), nullable=True)
    paid_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    payment_method = Column(String(50), nullable=True)
    payment_reference = Column(String(100), nullable=True)

    # Verknüpfung zu Kassenbuch
    cash_entry_id = Column(UUID(as_uuid=True), ForeignKey("cash_entries.id", ondelete="SET NULL"), nullable=True)

    # DATEV
    datev_exported_at = Column(DateTime(timezone=True), nullable=True)

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    created_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # Soft-Delete
    deleted_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # Relationships
    company = relationship("Company", back_populates="expense_reports")
    employee = relationship("User", foreign_keys=[employee_id])
    items = relationship(
        "ExpenseItem",
        back_populates="expense_report",
        cascade="all, delete-orphan",
        order_by="ExpenseItem.expense_date"
    )
    cash_entry = relationship("CashEntry", foreign_keys=[cash_entry_id])

    __table_args__ = (
        Index("ix_expense_reports_company_id", "company_id"),
        Index("ix_expense_reports_employee_id", "employee_id"),
        Index("ix_expense_reports_status", "status"),
        Index("ix_expense_reports_period", "period_start", "period_end"),
        Index("ix_expense_reports_created_at", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<ExpenseReport {self.report_number} ({self.status})>"


class ExpenseItem(Base):
    """Einzelposition einer Spesenabrechnung.

    Unterstützt verschiedene Typen:
    - RECEIPT: Belegausgabe (mit gescanntem Beleg)
    - MILEAGE: Kilometergeld (0,30 EUR/km)
    - PER_DIEM: Verpflegungspauschale (14/28 EUR)
    - FLAT_RATE: Sonstige Pauschale
    """

    __tablename__ = "expense_items"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    expense_report_id = Column(
        UUID(as_uuid=True),
        ForeignKey("expense_reports.id", ondelete="CASCADE"),
        nullable=False
    )

    # Kategorisierung
    category_id = Column(UUID(as_uuid=True), ForeignKey("cash_categories.id", ondelete="SET NULL"), nullable=True)
    expense_type = Column(String(50), nullable=False)  # ExpenseType

    # Datum
    expense_date = Column(Date, nullable=False)

    # Betrag
    amount = Column(Numeric(15, 2), nullable=False)
    currency = Column(String(3), default="EUR")

    # Steuer
    tax_rate = Column(Numeric(5, 2), nullable=True)
    tax_amount = Column(Numeric(15, 2), nullable=True)
    net_amount = Column(Numeric(15, 2), nullable=True)

    # Abzugsfähigkeit
    is_deductible = Column(Boolean, default=True)
    deductible_percentage = Column(Integer, default=100)
    deductible_amount = Column(Numeric(15, 2), nullable=True)

    # Beschreibung
    description = Column(Text, nullable=False)

    # Beleg
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="SET NULL"), nullable=True)
    receipt_number = Column(String(100), nullable=True)

    # Geschäftspartner
    vendor_name = Column(String(255), nullable=True)
    vendor_id = Column(UUID(as_uuid=True), ForeignKey("business_entities.id", ondelete="SET NULL"), nullable=True)

    # Bewirtung (wenn expense_type = receipt & category = entertainment)
    entertainment_participants = Column(CrossDBJSON, nullable=True)  # ["Name1", "Name2"]
    entertainment_occasion = Column(Text, nullable=True)
    entertainment_location = Column(String(255), nullable=True)

    # Kilometergeld (wenn expense_type = mileage)
    mileage_from = Column(String(255), nullable=True)
    mileage_to = Column(String(255), nullable=True)
    mileage_kilometers = Column(Numeric(10, 2), nullable=True)
    mileage_rate = Column(Numeric(5, 2), default=0.30)  # EUR/km
    mileage_vehicle_type = Column(String(50), nullable=True)  # pkw, motorrad
    mileage_license_plate = Column(String(20), nullable=True)

    # Verpflegungspauschale (wenn expense_type = per_diem)
    per_diem_hours = Column(Numeric(4, 1), nullable=True)
    per_diem_rate = Column(Numeric(5, 2), nullable=True)  # 14 oder 28
    per_diem_breakfast_provided = Column(Boolean, default=False)
    per_diem_lunch_provided = Column(Boolean, default=False)
    per_diem_dinner_provided = Column(Boolean, default=False)

    # Buchhaltung
    skr_account = Column(String(10), nullable=True)
    cost_center = Column(String(50), nullable=True)

    # Sortierung
    sort_order = Column(Integer, default=0)

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    expense_report = relationship("ExpenseReport", back_populates="items")
    category = relationship("CashCategory")
    document = relationship("Document")
    vendor = relationship("BusinessEntity")

    __table_args__ = (
        Index("ix_expense_items_report_id", "expense_report_id"),
        Index("ix_expense_items_date", "expense_date"),
        Index("ix_expense_items_document_id", "document_id"),
        Index("ix_expense_items_type", "expense_type"),
    )

    def __repr__(self) -> str:
        return f"<ExpenseItem {self.expense_date} {self.amount} {self.currency}>"
