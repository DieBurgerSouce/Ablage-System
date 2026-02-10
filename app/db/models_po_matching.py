# -*- coding: utf-8 -*-
"""
PO-Matching Models fuer Ablage-System.

3-Way Purchase Order Matching:
- Bestellung (Purchase Order) <-> Lieferschein (Delivery Note) <-> Rechnung (Invoice)
- Automatisches Matching nach Bestellnummer, Lieferant und Betraegen
- Abweichungserkennung mit konfigurierbaren Toleranzen
- Freigabe-Workflow fuer Abweichungen

Phase 2.2 der Feature-Roadmap (Februar 2026).
"""

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Optional
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
    ForeignKey,
    Index,
    Enum as SQLAlchemyEnum,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.models import Base, CrossDBJSON


# ============================================================================
# Enums
# ============================================================================


class MatchStatus(str, Enum):
    """Status eines 3-Way Matches."""
    PENDING = "pending"          # Noch nicht gematcht
    PARTIAL = "partial"          # Teilweise gematcht (z.B. nur 2 von 3)
    FULL = "full"                # Vollstaendig gematcht (3-Way)
    DISCREPANCY = "discrepancy"  # Abweichungen gefunden
    REJECTED = "rejected"        # Manuell abgelehnt
    APPROVED = "approved"        # Trotz Abweichung freigegeben


class DiscrepancyCategory(str, Enum):
    """Kategorie einer Abweichung."""
    AMOUNT = "amount"            # Betragabweichung
    QUANTITY = "quantity"        # Mengenabweichung
    ITEM = "item"                # Fehlende/zusaetzliche Position
    DATE = "date"                # Datumsabweichung
    PRICE = "price"              # Preisabweichung pro Einheit


class DiscrepancySeverity(str, Enum):
    """Schweregrad einer Abweichung."""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


# ============================================================================
# PurchaseOrderMatch Model
# ============================================================================


class PurchaseOrderMatch(Base):
    """3-Way Match: Bestellung <-> Lieferschein <-> Rechnung.

    Ein Match baut sich schrittweise auf, wenn Dokumente eintreffen:
    1. Bestellung wird erfasst -> Match mit Status PENDING
    2. Lieferschein trifft ein -> Match wird PARTIAL
    3. Rechnung trifft ein -> Match wird FULL oder DISCREPANCY
    """
    __tablename__ = "purchase_order_matches"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Company (Multi-Tenant)
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Dokument-Referenzen (alle nullable - Match baut sich auf)
    purchase_order_id = Column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="SET NULL"),
        nullable=True,
        index=True
    )
    delivery_note_id = Column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="SET NULL"),
        nullable=True,
        index=True
    )
    invoice_id = Column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="SET NULL"),
        nullable=True,
        index=True
    )

    # Dokumentenkette (Referenz auf chain_id String, nicht FK)
    document_chain_id = Column(
        String(100),
        nullable=True,
        index=True,
        comment="Auftragsketten-ID (z.B. CHAIN-2026-00001)"
    )

    # Lieferant
    vendor_entity_id = Column(
        UUID(as_uuid=True),
        ForeignKey("business_entities.id", ondelete="SET NULL"),
        nullable=True,
        index=True
    )
    vendor_name = Column(String(255), nullable=True)

    # Bestellreferenz
    order_number = Column(String(100), nullable=True, index=True)
    order_date = Column(DateTime(timezone=True), nullable=True)

    # Betraege (Numeric 15,2 - nullable bis Dokument vorliegt)
    po_amount = Column(Numeric(15, 2), nullable=True)
    dn_amount = Column(Numeric(15, 2), nullable=True)
    invoice_amount = Column(Numeric(15, 2), nullable=True)

    # Match-Status
    match_status = Column(
        SQLAlchemyEnum(MatchStatus, name="match_status"),
        nullable=False,
        default=MatchStatus.PENDING
    )

    # Match-Qualitaet
    match_score = Column(Float, default=0.0)  # 0-100
    auto_matched = Column(Boolean, default=False)

    # Toleranzen
    amount_tolerance_percent = Column(Float, default=2.0)
    quantity_tolerance_percent = Column(Float, default=1.0)

    # Positionsvergleich (detaillierter Zeile-fuer-Zeile Vergleich)
    line_items_comparison = Column(CrossDBJSON, default=list)

    # Freigabe
    approved_by_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )
    approved_at = Column(DateTime(timezone=True), nullable=True)
    approval_notes = Column(Text, nullable=True)

    # Zeitstempel
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    matched_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    company = relationship("Company", backref="po_matches")
    purchase_order = relationship(
        "Document",
        foreign_keys=[purchase_order_id],
        backref="po_match_as_order"
    )
    delivery_note = relationship(
        "Document",
        foreign_keys=[delivery_note_id],
        backref="po_match_as_delivery"
    )
    invoice = relationship(
        "Document",
        foreign_keys=[invoice_id],
        backref="po_match_as_invoice"
    )
    vendor_entity = relationship("BusinessEntity", backref="po_matches")
    approved_by = relationship("User", backref="approved_po_matches")
    discrepancies = relationship(
        "MatchDiscrepancy",
        back_populates="match",
        cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_po_match_company_status", "company_id", "match_status"),
        Index("ix_po_match_vendor", "company_id", "vendor_entity_id"),
        Index("ix_po_match_order_number", "company_id", "order_number"),
        Index("ix_po_match_created", "company_id", "created_at"),
    )

    @property
    def document_count(self) -> int:
        """Anzahl verknuepfter Dokumente."""
        count = 0
        if self.purchase_order_id:
            count += 1
        if self.delivery_note_id:
            count += 1
        if self.invoice_id:
            count += 1
        return count

    @property
    def is_complete(self) -> bool:
        """Prueft ob alle 3 Dokumente vorhanden sind."""
        return self.document_count == 3


# ============================================================================
# MatchDiscrepancy Model
# ============================================================================


class MatchDiscrepancy(Base):
    """Abweichung in einem 3-Way Match.

    Dokumentiert Unterschiede zwischen Bestellung, Lieferschein
    und Rechnung mit Schweregrad und Loesungsstatus.
    """
    __tablename__ = "match_discrepancies"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Zuordnung zum Match
    match_id = Column(
        UUID(as_uuid=True),
        ForeignKey("purchase_order_matches.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Kategorie der Abweichung
    category = Column(
        SQLAlchemyEnum(DiscrepancyCategory, name="discrepancy_category"),
        nullable=False
    )

    # Beschreibung (Deutsch)
    description = Column(Text, nullable=False)

    # Betroffenes Feld
    field_name = Column(String(100), nullable=False)

    # Werte (als String fuer Anzeige)
    expected_value = Column(String(500), nullable=True)
    actual_value = Column(String(500), nullable=True)

    # Betraege (fuer Betrags-Abweichungen)
    expected_amount = Column(Numeric(15, 2), nullable=True)
    actual_amount = Column(Numeric(15, 2), nullable=True)

    # Abweichung in Prozent
    deviation_percent = Column(Float, nullable=True)

    # Schweregrad
    severity = Column(
        SQLAlchemyEnum(DiscrepancySeverity, name="discrepancy_severity"),
        nullable=False,
        default=DiscrepancySeverity.WARNING
    )

    # Loesungsstatus
    resolved = Column(Boolean, default=False)
    resolved_by_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    resolution_notes = Column(Text, nullable=True)

    # Zeitstempel
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    match = relationship("PurchaseOrderMatch", back_populates="discrepancies")
    resolved_by = relationship("User", backref="resolved_discrepancies")

    __table_args__ = (
        Index("ix_discrepancy_match_category", "match_id", "category"),
        Index("ix_discrepancy_unresolved", "match_id", "resolved"),
    )
