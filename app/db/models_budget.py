# -*- coding: utf-8 -*-
"""
Budget & Kostenstellen Models fuer Ablage-System.

Budgetierung & Controlling mit:
- Budget-Perioden (Monat, Quartal, Jahr)
- Kostenstellen-Support
- Automatische Kategorisierung aus OCR-extrahierten Daten
- Abweichungsberichte mit Drill-Down
- Alert-System bei Budget-Ueberschreitung

Phase 2.1 der Feature-Roadmap (Januar 2026).
"""

from datetime import datetime, date
from decimal import Decimal
from enum import Enum
from typing import Optional, List
import uuid

from sqlalchemy import (
    Column,
    String,
    Integer,
    Float,
    Numeric,
    Boolean,
    Text,
    DateTime,
    Date,
    ForeignKey,
    Index,
    UniqueConstraint,
    CheckConstraint,
    Enum as SQLAlchemyEnum,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.models import Base, CrossDBJSON


# ============================================================================
# Enums
# ============================================================================


class BudgetPeriodType(str, Enum):
    """Budget-Perioden-Typ."""
    MONTHLY = "monthly"       # Monat
    QUARTERLY = "quarterly"   # Quartal
    YEARLY = "yearly"         # Jahr
    CUSTOM = "custom"         # Benutzerdefiniert


class BudgetStatus(str, Enum):
    """Budget-Status."""
    DRAFT = "draft"           # Entwurf
    ACTIVE = "active"         # Aktiv
    CLOSED = "closed"         # Abgeschlossen
    ARCHIVED = "archived"     # Archiviert


class BudgetLineStatus(str, Enum):
    """Status einer Budget-Position."""
    UNDER_BUDGET = "under_budget"     # Unter Budget
    ON_TRACK = "on_track"             # Im Plan
    WARNING = "warning"               # Warnung (>80%)
    OVER_BUDGET = "over_budget"       # Ueber Budget


class AllocationSource(str, Enum):
    """Quelle der Budget-Zuordnung."""
    MANUAL = "manual"             # Manuelle Zuordnung
    OCR_AUTO = "ocr_auto"         # Automatisch aus OCR
    RULE_BASED = "rule_based"     # Regelbasiert
    IMPORT = "import"             # Import (z.B. DATEV)


class AlertSeverity(str, Enum):
    """Schweregrad von Budget-Alerts."""
    INFO = "info"           # Information
    WARNING = "warning"     # Warnung (>80%)
    CRITICAL = "critical"   # Kritisch (>95%)
    EXCEEDED = "exceeded"   # Ueberschritten (>100%)


# ============================================================================
# Kostenstelle Model
# ============================================================================


class Kostenstelle(Base):
    """Kostenstelle fuer Budget-Zuordnung.

    Hierarchische Kostenstellenstruktur mit Parent-Child Beziehungen.
    Beispiel: Vertrieb (parent) -> Vertrieb Nord (child)
    """
    __tablename__ = "kostenstellen"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Identifikation
    code = Column(String(50), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)

    # Hierarchie
    parent_id = Column(
        UUID(as_uuid=True),
        ForeignKey("kostenstellen.id", ondelete="SET NULL"),
        nullable=True,
        index=True
    )
    level = Column(Integer, default=0)  # Hierarchie-Ebene (0 = Root)
    path = Column(String(500), nullable=True)  # Materialized Path: "1/5/12"

    # Company (Multi-Tenant)
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Verantwortung
    responsible_user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )

    # Status
    is_active = Column(Boolean, default=True)
    valid_from = Column(Date, nullable=True)
    valid_until = Column(Date, nullable=True)

    # Kategorisierung
    category = Column(String(100), nullable=True)  # z.B. "Produktion", "Verwaltung"
    tags = Column(CrossDBJSON, default=list)

    # Metadata
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    parent = relationship(
        "Kostenstelle",
        remote_side="Kostenstelle.id",
        backref="children"
    )
    company = relationship("Company", backref="kostenstellen")
    responsible_user = relationship("User", backref="managed_kostenstellen")
    budget_lines = relationship("BudgetLine", back_populates="kostenstelle")
    allocations = relationship("BudgetAllocation", back_populates="kostenstelle")

    __table_args__ = (
        UniqueConstraint("company_id", "code", name="uq_kostenstelle_company_code"),
        Index("ix_kostenstelle_company_active", "company_id", "is_active"),
        Index("ix_kostenstelle_path", "path"),
    )


# ============================================================================
# Budget Model
# ============================================================================


class Budget(Base):
    """Hauptbudget fuer eine Periode.

    Ein Budget kann fuer verschiedene Zeitraeume angelegt werden:
    - Jahresbudget
    - Quartalsbudget
    - Monatsbudget
    - Benutzerdefinierte Perioden
    """
    __tablename__ = "budgets"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Identifikation
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)

    # Periode
    period_type = Column(
        SQLAlchemyEnum(BudgetPeriodType, name="budget_period_type"),
        nullable=False,
        default=BudgetPeriodType.YEARLY
    )
    year = Column(Integer, nullable=False)
    quarter = Column(Integer, nullable=True)  # 1-4 bei Quartalsbudget
    month = Column(Integer, nullable=True)    # 1-12 bei Monatsbudget
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)

    # Status
    status = Column(
        SQLAlchemyEnum(BudgetStatus, name="budget_status"),
        nullable=False,
        default=BudgetStatus.DRAFT
    )

    # Company (Multi-Tenant)
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Verantwortung
    owner_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )

    # Gesamt-Budget
    total_planned = Column(Numeric(15, 2), default=Decimal("0.00"))
    total_actual = Column(Numeric(15, 2), default=Decimal("0.00"))
    total_committed = Column(Numeric(15, 2), default=Decimal("0.00"))  # Gebundene Mittel
    total_remaining = Column(Numeric(15, 2), default=Decimal("0.00"))

    # Waehrung
    currency = Column(String(3), default="EUR")

    # Schwellenwerte fuer Alerts
    warning_threshold = Column(Float, default=80.0)   # Alert bei 80%
    critical_threshold = Column(Float, default=95.0)  # Kritisch bei 95%

    # Einstellungen
    allow_overspend = Column(Boolean, default=False)
    auto_close_on_period_end = Column(Boolean, default=True)
    notify_on_allocation = Column(Boolean, default=True)

    # Vorgaenger-Budget (fuer Vergleiche)
    previous_budget_id = Column(
        UUID(as_uuid=True),
        ForeignKey("budgets.id", ondelete="SET NULL"),
        nullable=True
    )

    # Metadata
    metadata_json = Column(CrossDBJSON, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    approved_at = Column(DateTime(timezone=True), nullable=True)
    approved_by_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )

    # Relationships
    company = relationship("Company", backref="budgets")
    owner = relationship("User", foreign_keys=[owner_id], backref="owned_budgets")
    approved_by = relationship("User", foreign_keys=[approved_by_id])
    previous_budget = relationship("Budget", remote_side="Budget.id")
    lines = relationship("BudgetLine", back_populates="budget", cascade="all, delete-orphan")
    allocations = relationship("BudgetAllocation", back_populates="budget", cascade="all, delete-orphan")
    alerts = relationship("BudgetAlert", back_populates="budget", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_budget_company_year", "company_id", "year"),
        Index("ix_budget_company_status", "company_id", "status"),
        Index("ix_budget_period", "year", "quarter", "month"),
        CheckConstraint("end_date > start_date", name="ck_budget_date_range"),
        CheckConstraint("quarter IS NULL OR (quarter >= 1 AND quarter <= 4)", name="ck_budget_quarter"),
        CheckConstraint("month IS NULL OR (month >= 1 AND month <= 12)", name="ck_budget_month"),
    )

    @property
    def utilization_percent(self) -> float:
        """Berechnet die Budget-Auslastung in Prozent."""
        if self.total_planned and self.total_planned > 0:
            return float((self.total_actual / self.total_planned) * 100)
        return 0.0

    @property
    def is_over_budget(self) -> bool:
        """Prueft ob Budget ueberschritten."""
        return self.total_actual > self.total_planned


# ============================================================================
# BudgetLine Model
# ============================================================================


class BudgetLine(Base):
    """Budget-Position fuer eine Kategorie/Kostenstelle.

    Granulare Budget-Planung pro:
    - Kostenstelle
    - Kategorie (z.B. "Reisekosten", "Material")
    - Konto (SKR03/04 Kontonummer)
    """
    __tablename__ = "budget_lines"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Zuordnung
    budget_id = Column(
        UUID(as_uuid=True),
        ForeignKey("budgets.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    kostenstelle_id = Column(
        UUID(as_uuid=True),
        ForeignKey("kostenstellen.id", ondelete="SET NULL"),
        nullable=True,
        index=True
    )

    # Kategorisierung
    category = Column(String(100), nullable=False)  # z.B. "Reisekosten"
    subcategory = Column(String(100), nullable=True)  # z.B. "Flug"
    account_number = Column(String(20), nullable=True)  # SKR03/04 Konto

    # Beschreibung
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)

    # Betraege
    planned_amount = Column(Numeric(15, 2), nullable=False, default=Decimal("0.00"))
    actual_amount = Column(Numeric(15, 2), default=Decimal("0.00"))
    committed_amount = Column(Numeric(15, 2), default=Decimal("0.00"))

    # Status (berechnet)
    status = Column(
        SQLAlchemyEnum(BudgetLineStatus, name="budget_line_status"),
        nullable=False,
        default=BudgetLineStatus.UNDER_BUDGET
    )

    # Monatliche Verteilung (fuer Jahresbudgets)
    monthly_distribution = Column(CrossDBJSON, default=dict)
    # Format: {"1": 1000.00, "2": 1200.00, ...}

    # Vorjahresvergleich
    previous_year_actual = Column(Numeric(15, 2), nullable=True)
    variance_to_previous = Column(Numeric(15, 2), nullable=True)

    # Regeln fuer automatische Zuordnung
    auto_assign_rules = Column(CrossDBJSON, default=list)
    # Format: [{"field": "vendor_name", "operator": "contains", "value": "Amazon"}]

    # Notizen
    notes = Column(Text, nullable=True)

    # Metadata
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    budget = relationship("Budget", back_populates="lines")
    kostenstelle = relationship("Kostenstelle", back_populates="budget_lines")
    allocations = relationship("BudgetAllocation", back_populates="budget_line", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_budget_line_budget_category", "budget_id", "category"),
        Index("ix_budget_line_kostenstelle", "kostenstelle_id"),
        Index("ix_budget_line_account", "account_number"),
    )

    @property
    def remaining_amount(self) -> Decimal:
        """Verbleibendes Budget."""
        return self.planned_amount - self.actual_amount - self.committed_amount

    @property
    def utilization_percent(self) -> float:
        """Auslastung in Prozent."""
        if self.planned_amount and self.planned_amount > 0:
            return float((self.actual_amount / self.planned_amount) * 100)
        return 0.0


# ============================================================================
# BudgetAllocation Model
# ============================================================================


class BudgetAllocation(Base):
    """Einzelne Budget-Zuordnung zu einem Dokument/Transaktion.

    Verknuepft Dokumente mit Budget-Positionen und trackt:
    - Quelle (OCR, manuell, Import)
    - Betrag und Aufteilung
    - Verarbeitungsstatus
    """
    __tablename__ = "budget_allocations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Budget-Zuordnung
    budget_id = Column(
        UUID(as_uuid=True),
        ForeignKey("budgets.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    budget_line_id = Column(
        UUID(as_uuid=True),
        ForeignKey("budget_lines.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    kostenstelle_id = Column(
        UUID(as_uuid=True),
        ForeignKey("kostenstellen.id", ondelete="SET NULL"),
        nullable=True,
        index=True
    )

    # Dokument-Verknuepfung
    document_id = Column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="SET NULL"),
        nullable=True,
        index=True
    )
    invoice_tracking_id = Column(
        UUID(as_uuid=True),
        ForeignKey("invoice_tracking.id", ondelete="SET NULL"),
        nullable=True
    )
    bank_transaction_id = Column(
        UUID(as_uuid=True),
        ForeignKey("bank_transactions.id", ondelete="SET NULL"),
        nullable=True
    )

    # Betraege
    amount = Column(Numeric(15, 2), nullable=False)
    tax_amount = Column(Numeric(15, 2), default=Decimal("0.00"))
    net_amount = Column(Numeric(15, 2), default=Decimal("0.00"))

    # Datum der Buchung
    booking_date = Column(Date, nullable=False)
    value_date = Column(Date, nullable=True)  # Wertstellung

    # Quelle
    source = Column(
        SQLAlchemyEnum(AllocationSource, name="allocation_source"),
        nullable=False,
        default=AllocationSource.MANUAL
    )

    # Beschreibung
    description = Column(String(500), nullable=True)
    reference = Column(String(100), nullable=True)  # Rechnungsnr, etc.
    vendor_name = Column(String(255), nullable=True)

    # OCR-Erkennung Details
    ocr_confidence = Column(Float, nullable=True)
    ocr_extracted_category = Column(String(100), nullable=True)
    ocr_matched_rule = Column(String(100), nullable=True)

    # Status
    is_committed = Column(Boolean, default=False)  # Gebunden aber noch nicht bezahlt
    is_processed = Column(Boolean, default=True)   # Verarbeitet/Gebucht
    is_reversed = Column(Boolean, default=False)   # Storniert

    # Aufteilung (wenn ein Dokument auf mehrere Positionen verteilt wird)
    split_allocation = Column(Boolean, default=False)
    split_parent_id = Column(
        UUID(as_uuid=True),
        ForeignKey("budget_allocations.id", ondelete="SET NULL"),
        nullable=True
    )
    split_percentage = Column(Float, nullable=True)  # Anteil in %

    # User
    created_by_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )
    approved_by_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )

    # Metadata
    metadata_json = Column(CrossDBJSON, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    budget = relationship("Budget", back_populates="allocations")
    budget_line = relationship("BudgetLine", back_populates="allocations")
    kostenstelle = relationship("Kostenstelle", back_populates="allocations")
    document = relationship("Document", backref="budget_allocations")
    invoice_tracking = relationship("InvoiceTracking", backref="budget_allocations")
    bank_transaction = relationship("BankTransaction", backref="budget_allocations")
    created_by = relationship("User", foreign_keys=[created_by_id])
    approved_by = relationship("User", foreign_keys=[approved_by_id])
    split_parent = relationship("BudgetAllocation", remote_side="BudgetAllocation.id")

    __table_args__ = (
        Index("ix_allocation_budget_date", "budget_id", "booking_date"),
        Index("ix_allocation_document", "document_id"),
        Index("ix_allocation_line_date", "budget_line_id", "booking_date"),
    )


# ============================================================================
# BudgetAlert Model
# ============================================================================


class BudgetAlert(Base):
    """Alert bei Budget-Ueberschreitung oder Warnung.

    Automatisch generiert bei:
    - Ueberschreitung der Warnschwelle (z.B. 80%)
    - Kritischer Schwelle (z.B. 95%)
    - Budget-Ueberschreitung (>100%)
    """
    __tablename__ = "budget_alerts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Zuordnung
    budget_id = Column(
        UUID(as_uuid=True),
        ForeignKey("budgets.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    budget_line_id = Column(
        UUID(as_uuid=True),
        ForeignKey("budget_lines.id", ondelete="CASCADE"),
        nullable=True,
        index=True
    )
    kostenstelle_id = Column(
        UUID(as_uuid=True),
        ForeignKey("kostenstellen.id", ondelete="SET NULL"),
        nullable=True
    )

    # Alert Details
    severity = Column(
        SQLAlchemyEnum(AlertSeverity, name="alert_severity"),
        nullable=False
    )
    title = Column(String(255), nullable=False)
    message = Column(Text, nullable=False)

    # Schwellenwert-Details
    threshold_percent = Column(Float, nullable=False)
    actual_percent = Column(Float, nullable=False)
    amount_exceeded = Column(Numeric(15, 2), nullable=True)

    # Status
    is_acknowledged = Column(Boolean, default=False)
    acknowledged_at = Column(DateTime(timezone=True), nullable=True)
    acknowledged_by_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )

    # Notifikation
    notification_sent = Column(Boolean, default=False)
    notification_sent_at = Column(DateTime(timezone=True), nullable=True)
    notification_channels = Column(CrossDBJSON, default=list)  # ["email", "slack"]

    # Metadata
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    budget = relationship("Budget", back_populates="alerts")
    budget_line = relationship("BudgetLine", backref="alerts")
    kostenstelle = relationship("Kostenstelle", backref="alerts")
    acknowledged_by = relationship("User", backref="acknowledged_alerts")

    __table_args__ = (
        Index("ix_alert_budget_severity", "budget_id", "severity"),
        Index("ix_alert_unacknowledged", "is_acknowledged", "created_at"),
    )


# ============================================================================
# BudgetCategory Model (Vordefinierte Kategorien)
# ============================================================================


class BudgetCategory(Base):
    """Vordefinierte Budget-Kategorien mit OCR-Mapping.

    Ermoeglicht automatische Kategorisierung aus OCR-Daten
    basierend auf Schluesselwoertern und Mustern.
    """
    __tablename__ = "budget_categories"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Identifikation
    code = Column(String(50), nullable=False, unique=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)

    # Hierarchie
    parent_code = Column(String(50), nullable=True)
    level = Column(Integer, default=0)

    # DATEV/SKR03/04 Mapping
    skr03_accounts = Column(CrossDBJSON, default=list)  # ["4200", "4210", ...]
    skr04_accounts = Column(CrossDBJSON, default=list)

    # OCR Auto-Detection
    keywords = Column(CrossDBJSON, default=list)  # ["Reise", "Flug", "Hotel"]
    vendor_patterns = Column(CrossDBJSON, default=list)  # ["Lufthansa", "Deutsche Bahn"]
    regex_patterns = Column(CrossDBJSON, default=list)  # Erweiterte Muster

    # Default Kostenstelle
    default_kostenstelle_code = Column(String(50), nullable=True)

    # Tax Information
    tax_rate = Column(Float, nullable=True)  # Default MwSt-Satz
    is_tax_deductible = Column(Boolean, default=True)

    # Status
    is_active = Column(Boolean, default=True)
    is_system = Column(Boolean, default=False)  # System-Kategorie (nicht loeschbar)

    # Metadata
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("ix_budget_category_code", "code"),
        Index("ix_budget_category_parent", "parent_code"),
    )


# ============================================================================
# BudgetReport Model (Gespeicherte Berichte)
# ============================================================================


class BudgetReport(Base):
    """Gespeicherter Budget-Bericht.

    Ermoeglicht:
    - Periodische Berichte (Monatsabschluss)
    - Drill-Down Analysen
    - Export-Vorlagen
    """
    __tablename__ = "budget_reports"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Zuordnung
    budget_id = Column(
        UUID(as_uuid=True),
        ForeignKey("budgets.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False
    )

    # Report Details
    name = Column(String(255), nullable=False)
    report_type = Column(String(50), nullable=False)  # "variance", "summary", "drill_down"

    # Zeitraum
    period_start = Column(Date, nullable=False)
    period_end = Column(Date, nullable=False)

    # Daten (Snapshot)
    report_data = Column(CrossDBJSON, nullable=False, default=dict)

    # Export
    export_format = Column(String(20), nullable=True)  # "pdf", "xlsx", "csv"
    export_path = Column(String(500), nullable=True)

    # User
    created_by_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )

    # Metadata
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    budget = relationship("Budget", backref="reports")
    company = relationship("Company", backref="budget_reports")
    created_by = relationship("User", backref="budget_reports")

    __table_args__ = (
        Index("ix_report_budget_type", "budget_id", "report_type"),
        Index("ix_report_company_period", "company_id", "period_start", "period_end"),
    )
