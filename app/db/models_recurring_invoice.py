# -*- coding: utf-8 -*-
"""
Wiederkehrende Rechnungen (Abo-Verwaltung) Models für Ablage-System.

Abo-Erkennung & Verwaltung mit:
- Automatische Erkennung wiederkehrender Rechnungsmuster
- Soll/Ist-Vergleich für erwartete vs. tatsaechliche Rechnungen
- Preisänderungs-Tracking und Alerts
- Kündigungsfristen-Management
- Fehlende-Rechnungen-Erkennung

Phase 2.2 der Feature-Roadmap (Februar 2026).
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


class RecurringInvoiceStatus(str, Enum):
    """Status einer wiederkehrenden Rechnung."""
    ACTIVE = "active"           # Aktiv
    PAUSED = "paused"           # Pausiert
    CANCELLED = "cancelled"     # Gekündigt
    EXPIRED = "expired"         # Ausgelaufen


class RecurringIntervalType(str, Enum):
    """Intervall-Typ für wiederkehrende Rechnungen."""
    MONTHLY = "monthly"         # Monatlich
    QUARTERLY = "quarterly"     # Vierteljährlich
    HALF_YEARLY = "half_yearly" # Halbjährlich
    YEARLY = "yearly"           # Jährlich


class DetectionMethod(str, Enum):
    """Methode der Erkennung."""
    AUTO = "auto"               # Automatisch erkannt
    MANUAL = "manual"           # Manuell angelegt


class OccurrenceStatus(str, Enum):
    """Status einer einzelnen Abo-Instanz."""
    EXPECTED = "expected"       # Erwartet (noch nicht eingetroffen)
    MATCHED = "matched"         # Zugeordnet
    MISSING = "missing"         # Fehlend / überfällig
    LATE = "late"               # Verspätet eingetroffen
    OVERPAID = "overpaid"       # Überzahlt
    UNDERPAID = "underpaid"     # Unterzahlt


class OccurrenceMatchMethod(str, Enum):
    """Methode der Zuordnung."""
    AUTO = "auto"               # Automatisch zugeordnet
    MANUAL = "manual"           # Manuell zugeordnet


# ============================================================================
# RecurringInvoice Model
# ============================================================================


class RecurringInvoice(Base):
    """Wiederkehrende Rechnung / Abo-Erkennung.

    Repraesentiert ein erkanntes oder manuell angelegtes Abo-Muster
    mit erwarteten Betraegen, Intervallen und Kündigungsinformationen.
    """
    __tablename__ = "recurring_invoices"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Multi-Tenant
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Lieferant-Verknüpfung
    vendor_entity_id = Column(
        UUID(as_uuid=True),
        ForeignKey("business_entities.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    vendor_name = Column(String(255), nullable=False)

    # Intervall-Muster
    interval_type = Column(
        SQLAlchemyEnum(RecurringIntervalType, name="recurring_interval_type", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        default=RecurringIntervalType.MONTHLY,
    )
    interval_months = Column(Integer, nullable=False, default=1)

    # Erwarteter Betrag
    expected_amount = Column(Numeric(15, 2), nullable=False)
    currency = Column(String(3), default="EUR")
    tolerance_percent = Column(Float, default=5.0)

    # Zeitraum-Tracking
    first_seen_date = Column(Date, nullable=True)
    last_seen_date = Column(Date, nullable=True)
    next_expected_date = Column(Date, nullable=True)

    # Kündigungs-Management
    cancellation_deadline = Column(Date, nullable=True)
    notice_period_days = Column(Integer, nullable=True)
    auto_renewal = Column(Boolean, default=True)

    # Erkennungs-Metriken
    detection_confidence = Column(Float, default=0.0)
    detection_method = Column(
        SQLAlchemyEnum(DetectionMethod, name="detection_method", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        default=DetectionMethod.MANUAL,
    )
    match_count = Column(Integer, default=0)

    # Preis-Tracking
    price_history = Column(CrossDBJSON, default=list)
    # Format: [{"date": "2026-01-15", "amount": 29.99, "change_percent": 5.0}]
    last_price_change_date = Column(Date, nullable=True)
    price_change_percent = Column(Float, nullable=True)

    # Status
    status = Column(
        SQLAlchemyEnum(RecurringInvoiceStatus, name="recurring_invoice_status", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        default=RecurringInvoiceStatus.ACTIVE,
    )

    # Alert-Flags
    price_increase_alerted = Column(Boolean, default=False)
    missing_invoice_alerted = Column(Boolean, default=False)

    # Beschreibung und Kategorisierung
    category = Column(String(100), nullable=True)
    description = Column(Text, nullable=True)
    document_type = Column(String(100), nullable=True)
    reference_pattern = Column(String(255), nullable=True)  # Regex für Rechnungsnummern

    # Metadata
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    company = relationship("Company", backref="recurring_invoices")
    vendor_entity = relationship("BusinessEntity", backref="recurring_invoices")
    occurrences = relationship(
        "RecurringInvoiceOccurrence",
        back_populates="recurring_invoice",
        cascade="all, delete-orphan",
        order_by="RecurringInvoiceOccurrence.expected_date.desc()",
    )

    __table_args__ = (
        Index("ix_recurring_invoice_company_status", "company_id", "status"),
        Index("ix_recurring_invoice_company_vendor", "company_id", "vendor_name"),
        Index("ix_recurring_invoice_next_expected", "company_id", "next_expected_date"),
        CheckConstraint("interval_months > 0", name="ck_recurring_invoice_interval_positive"),
        CheckConstraint("tolerance_percent >= 0", name="ck_recurring_invoice_tolerance_positive"),
    )

    @property
    def is_overdue(self) -> bool:
        """Prüft ob die nächste erwartete Rechnung überfällig ist."""
        if self.next_expected_date and self.status == RecurringInvoiceStatus.ACTIVE:
            return date.today() > self.next_expected_date
        return False


# ============================================================================
# RecurringInvoiceOccurrence Model
# ============================================================================


class RecurringInvoiceOccurrence(Base):
    """Einzelne Instanz einer wiederkehrenden Rechnung.

    Trackt jede erwartete und tatsaechliche Rechnung eines Abos
    mit Soll/Ist-Vergleich und Zuordnungsinformationen.
    """
    __tablename__ = "recurring_invoice_occurrences"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Abo-Verknüpfung
    recurring_invoice_id = Column(
        UUID(as_uuid=True),
        ForeignKey("recurring_invoices.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Dokument-Verknüpfung
    document_id = Column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    invoice_tracking_id = Column(
        UUID(as_uuid=True),
        ForeignKey("invoice_tracking.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Erwartete vs. tatsaechliche Daten
    expected_date = Column(Date, nullable=False)
    actual_date = Column(Date, nullable=True)
    expected_amount = Column(Numeric(15, 2), nullable=False)
    actual_amount = Column(Numeric(15, 2), nullable=True)
    amount_deviation = Column(Numeric(15, 2), nullable=True)

    # Status
    status = Column(
        SQLAlchemyEnum(OccurrenceStatus, name="occurrence_status", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        default=OccurrenceStatus.EXPECTED,
    )

    # Zuordnungs-Details
    match_confidence = Column(Float, nullable=True)
    matched_at = Column(DateTime(timezone=True), nullable=True)
    matched_by = Column(
        SQLAlchemyEnum(OccurrenceMatchMethod, name="occurrence_match_method", values_callable=lambda e: [m.value for m in e]),
        nullable=True,
    )

    # Abrechnungszeitraum
    period_start = Column(Date, nullable=True)
    period_end = Column(Date, nullable=True)

    # Notizen
    notes = Column(Text, nullable=True)

    # Metadata
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    recurring_invoice = relationship("RecurringInvoice", back_populates="occurrences")
    document = relationship("Document", backref="recurring_invoice_occurrences")
    invoice_tracking = relationship("InvoiceTracking", backref="recurring_invoice_occurrences")

    __table_args__ = (
        Index("ix_occurrence_recurring_date", "recurring_invoice_id", "expected_date"),
        Index("ix_occurrence_status", "recurring_invoice_id", "status"),
        Index("ix_occurrence_document", "document_id"),
    )
