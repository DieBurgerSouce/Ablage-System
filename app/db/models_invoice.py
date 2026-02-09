"""
Invoice satellite model.

Separates Invoice-Modell als Satellit (nicht in models.py).
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
    """
    __tablename__ = "invoices"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, unique=True)
    business_contact_id = Column(UUID(as_uuid=True), ForeignKey("business_contacts.id"), nullable=False)

    # Invoice details
    invoice_number = Column(String(100), unique=True, nullable=False, index=True)
    invoice_date = Column(Date, nullable=False)
    due_date = Column(Date, nullable=False)

    # Amounts
    subtotal = Column(Numeric(12, 2), nullable=False)
    tax_amount = Column(Numeric(12, 2), default=Decimal(0))
    total_amount = Column(Numeric(12, 2), nullable=False)
    currency = Column(String(3), default="EUR", nullable=False)

    # Payment status
    status = Column(String(20), default=InvoiceStatus.PENDING, nullable=False, index=True)
    payment_date = Column(Date, nullable=True)

    # Metadata
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), nullable=True)

    # Relationships
    document = relationship("Document", backref="invoice", uselist=False)
    business_contact = relationship("BusinessContact", backref="invoices")

    __table_args__ = (
        Index("ix_invoices_invoice_number", "invoice_number"),
        Index("ix_invoices_status", "status"),
        Index("ix_invoices_due_date", "due_date"),
        Index("ix_invoices_contact_date", "business_contact_id", "invoice_date"),
    )
