"""
Inventory Models - Warenbestand und Lagerverwaltung

Modelle für:
- Lager (Warehouse)
- Artikel (InventoryItem)
- Bestandsführung (StockLevel)
- Warenbewegungen (InventoryMovement)
- Wareneingang aus Lieferscheinen
"""

import uuid
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Optional

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum as SQLEnum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.models import Base


class MovementType(str, Enum):
    """Bewegungsarten für Inventar"""
    GOODS_RECEIPT = "goods_receipt"          # Wareneingang
    GOODS_ISSUE = "goods_issue"              # Warenausgang
    TRANSFER = "transfer"                     # Umlagerung
    ADJUSTMENT_PLUS = "adjustment_plus"       # Inventurkorrektur +
    ADJUSTMENT_MINUS = "adjustment_minus"     # Inventurkorrektur -
    RETURN_INBOUND = "return_inbound"         # Retoure Eingang
    RETURN_OUTBOUND = "return_outbound"       # Retoure Ausgang
    SCRAPPING = "scrapping"                   # Verschrottung


class MovementStatus(str, Enum):
    """Status einer Warenbewegung"""
    PENDING = "pending"       # Ausstehend
    CONFIRMED = "confirmed"   # Bestätigt
    CANCELLED = "cancelled"   # Storniert


class Warehouse(Base):
    """
    Lager - Physische oder logische Lagerorte
    """
    __tablename__ = "warehouses"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False
    )

    # Stammdaten
    code: Mapped[str] = mapped_column(String(20), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Adresse
    address_line1: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    address_line2: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    postal_code: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    city: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    country: Mapped[str] = mapped_column(String(2), default="DE")

    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    stock_levels: Mapped[list["StockLevel"]] = relationship(
        "StockLevel", back_populates="warehouse", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("company_id", "code", name="uq_warehouse_company_code"),
        Index("ix_warehouse_company_active", "company_id", "is_active"),
    )


class InventoryItem(Base):
    """
    Artikel - Stammdaten für Lagerartikel
    """
    __tablename__ = "inventory_items"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False
    )

    # Identifikation
    item_number: Mapped[str] = mapped_column(String(50), nullable=False)
    ean: Mapped[Optional[str]] = mapped_column(String(13), nullable=True)
    manufacturer_part_number: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    # Beschreibung
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    category: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # Einheiten
    unit: Mapped[str] = mapped_column(String(20), default="Stück")  # Stück, kg, m, etc.

    # Preise (optional, hauptsaechlich aus Rechnungen)
    purchase_price: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(precision=12, scale=2), nullable=True
    )
    sales_price: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(precision=12, scale=2), nullable=True
    )
    currency: Mapped[str] = mapped_column(String(3), default="EUR")

    # Bestellwesen
    min_stock_level: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(precision=12, scale=3), nullable=True
    )
    reorder_point: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(precision=12, scale=3), nullable=True
    )
    reorder_quantity: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(precision=12, scale=3), nullable=True
    )

    # Lieferant (kann mit BusinessEntity verknüpft werden)
    default_supplier_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("business_entities.id"), nullable=True
    )

    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Zusätzliche Attribute
    attributes: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    stock_levels: Mapped[list["StockLevel"]] = relationship(
        "StockLevel", back_populates="item", cascade="all, delete-orphan"
    )
    movements: Mapped[list["InventoryMovement"]] = relationship(
        "InventoryMovement", back_populates="item", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("company_id", "item_number", name="uq_item_company_number"),
        Index("ix_item_company_active", "company_id", "is_active"),
        Index("ix_item_ean", "ean"),
        Index("ix_item_category", "company_id", "category"),
    )


class StockLevel(Base):
    """
    Bestandsführung - Aktueller Bestand pro Artikel und Lager
    """
    __tablename__ = "stock_levels"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False
    )

    item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("inventory_items.id", ondelete="CASCADE"), nullable=False
    )
    warehouse_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("warehouses.id", ondelete="CASCADE"), nullable=False
    )

    # Bestände
    quantity_on_hand: Mapped[Decimal] = mapped_column(
        Numeric(precision=12, scale=3), default=0
    )
    quantity_reserved: Mapped[Decimal] = mapped_column(
        Numeric(precision=12, scale=3), default=0
    )
    quantity_on_order: Mapped[Decimal] = mapped_column(
        Numeric(precision=12, scale=3), default=0
    )

    # Letzte Inventur
    last_count_date: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_count_quantity: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(precision=12, scale=3), nullable=True
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    item: Mapped["InventoryItem"] = relationship("InventoryItem", back_populates="stock_levels")
    warehouse: Mapped["Warehouse"] = relationship("Warehouse", back_populates="stock_levels")

    __table_args__ = (
        UniqueConstraint("item_id", "warehouse_id", name="uq_stock_item_warehouse"),
        Index("ix_stock_company", "company_id"),
        Index("ix_stock_warehouse", "warehouse_id"),
        CheckConstraint("quantity_on_hand >= 0", name="ck_stock_quantity_positive"),
    )

    @property
    def quantity_available(self) -> Decimal:
        """Verfügbare Menge = Bestand - Reserviert"""
        return self.quantity_on_hand - self.quantity_reserved


class InventoryMovement(Base):
    """
    Warenbewegungen - Historische Buchungen
    """
    __tablename__ = "inventory_movements"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False
    )

    item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("inventory_items.id", ondelete="CASCADE"), nullable=False
    )
    warehouse_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("warehouses.id", ondelete="CASCADE"), nullable=False
    )

    # Bei Umlagerungen: Ziellager
    target_warehouse_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("warehouses.id"), nullable=True
    )

    # Bewegungstyp und Status
    movement_type: Mapped[MovementType] = mapped_column(
        SQLEnum(MovementType, values_callable=lambda e: [m.value for m in e]), nullable=False
    )
    status: Mapped[MovementStatus] = mapped_column(
        SQLEnum(MovementStatus, values_callable=lambda e: [m.value for m in e]), default=MovementStatus.CONFIRMED
    )

    # Mengen
    quantity: Mapped[Decimal] = mapped_column(
        Numeric(precision=12, scale=3), nullable=False
    )
    unit_price: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(precision=12, scale=2), nullable=True
    )
    total_value: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(precision=12, scale=2), nullable=True
    )
    currency: Mapped[str] = mapped_column(String(3), default="EUR")

    # Referenzen
    document_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id"), nullable=True
    )
    reference_number: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # Geschäftspartner
    entity_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("business_entities.id"), nullable=True
    )

    # Zusätzliche Infos
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Audit
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    movement_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    item: Mapped["InventoryItem"] = relationship("InventoryItem", back_populates="movements")
    warehouse: Mapped["Warehouse"] = relationship(
        "Warehouse", foreign_keys=[warehouse_id]
    )
    target_warehouse: Mapped[Optional["Warehouse"]] = relationship(
        "Warehouse", foreign_keys=[target_warehouse_id]
    )

    __table_args__ = (
        Index("ix_movement_company_date", "company_id", "movement_date"),
        Index("ix_movement_item", "item_id"),
        Index("ix_movement_document", "document_id"),
        Index("ix_movement_type", "movement_type"),
    )


class GoodsReceipt(Base):
    """
    Wareneingang - Verknüpfung Lieferschein mit Bestandsbuchung
    """
    __tablename__ = "goods_receipts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False
    )

    # Verknüpfung mit Lieferschein-Dokument
    delivery_note_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )

    # Ziellager
    warehouse_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("warehouses.id"), nullable=False
    )

    # Lieferant
    supplier_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("business_entities.id"), nullable=True
    )

    # Referenzen
    delivery_note_number: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    purchase_order_number: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # Datum
    receipt_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Status
    is_processed: Mapped[bool] = mapped_column(Boolean, default=False)
    processed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Notizen
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Audit
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    lines: Mapped[list["GoodsReceiptLine"]] = relationship(
        "GoodsReceiptLine", back_populates="goods_receipt", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("delivery_note_id", name="uq_goods_receipt_delivery_note"),
        Index("ix_goods_receipt_company", "company_id"),
        Index("ix_goods_receipt_supplier", "supplier_id"),
        Index("ix_goods_receipt_date", "receipt_date"),
    )


class GoodsReceiptLine(Base):
    """
    Wareneingangszeile - Einzelne Position im Wareneingang
    """
    __tablename__ = "goods_receipt_lines"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    goods_receipt_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("goods_receipts.id", ondelete="CASCADE"), nullable=False
    )

    # Artikel (kann null sein wenn noch nicht zugeordnet)
    item_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("inventory_items.id"), nullable=True
    )

    # Position aus Lieferschein
    line_number: Mapped[int] = mapped_column(Integer, nullable=False)

    # Artikeldaten (aus OCR oder manuell)
    item_number_extracted: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    # Mengen
    quantity_expected: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(precision=12, scale=3), nullable=True
    )
    quantity_received: Mapped[Decimal] = mapped_column(
        Numeric(precision=12, scale=3), nullable=False
    )
    unit: Mapped[str] = mapped_column(String(20), default="Stück")

    # Warenbewegung (erstellt nach Verarbeitung)
    movement_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("inventory_movements.id"), nullable=True
    )

    # Status
    is_matched: Mapped[bool] = mapped_column(Boolean, default=False)
    match_confidence: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(precision=5, scale=2), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    goods_receipt: Mapped["GoodsReceipt"] = relationship(
        "GoodsReceipt", back_populates="lines"
    )
    item: Mapped[Optional["InventoryItem"]] = relationship("InventoryItem")

    __table_args__ = (
        Index("ix_goods_receipt_line_item", "item_id"),
        UniqueConstraint("goods_receipt_id", "line_number", name="uq_receipt_line_number"),
    )
