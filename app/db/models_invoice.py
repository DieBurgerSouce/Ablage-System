"""
Invoice satellite model.

Separates Invoice-Modell als Satellit (nicht in models.py).

Drift-Historie (siehe ``docs/drift/invoice-model-drift.md``):
- 2026-05-19 (Task B): ``company_id`` Model-seitig nachgezogen
  (existiert in DB seit Migration 022).
- 2026-05-19 (F1): ``business_contact_id`` Phantom-Column + zugehoerige
  ``business_contact``-Beziehung + Index ``ix_invoices_contact_date``
  entfernt - DB-Tabelle invoices hatte diese Spalte nie, dead code in der
  Codebase.
"""

import uuid
from decimal import Decimal
from datetime import date
from enum import Enum

from sqlalchemy import (
    Column,
    String,
    Text,
    Date,
    DateTime,
    Numeric,
    Index,
    ForeignKey,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.models import Base

# Invoice Status Enum
class InvoiceStatus(str, Enum):
    """Invoice payment status."""
    PENDING = "pending"
    PAID = "paid"
    OVERDUE = "overdue"
    CANCELLED = "cancelled"


# Invoice Model
class Invoice(Base):
    """Rechnungsverwaltung fuer Finanzen.

    Verknuepft Dokumente mit Geschaeftskontakten und verfolgt Zahlungsstatus.
    Multi-Tenant-Isolation ueber ``company_id`` (Defense-in-Depth, RLS aktiv
    seit Migrationen 110/210/211).
    """
    __tablename__ = "invoices"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, unique=True)

    # Multi-Tenant-Isolation. Nullable=True wegen historischer Rows ohne
    # Backfill; neue Eintraege sollten company_id immer setzen.
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=True
    )

    # Invoice details
    invoice_number = Column(String(100), unique=True, nullable=False)
    invoice_date = Column(Date, nullable=False)
    due_date = Column(Date, nullable=False)

    # Amounts
    subtotal = Column(Numeric(12, 2), nullable=False)
    tax_amount = Column(Numeric(12, 2), default=Decimal(0))
    total_amount = Column(Numeric(12, 2), nullable=False)
    currency = Column(String(3), default="EUR", nullable=False)

    # Payment status
    status = Column(String(20), default=InvoiceStatus.PENDING, nullable=False)
    payment_date = Column(Date, nullable=True)

    # Metadata
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), nullable=True)

    # Relationships
    document = relationship("Document", backref="invoice", uselist=False)

    __table_args__ = (
        Index("ix_invoices_invoice_number", "invoice_number"),
        Index("ix_invoices_status", "status"),
        Index("ix_invoices_due_date", "due_date"),
        # Multi-Tenant-Lookups (DB-Index existiert bereits als ix_invoices_company_date
        # aus Migration 022, leading column company_id deckt Standard-Filter ab).
        Index("ix_invoices_company_id", "company_id"),
    )
