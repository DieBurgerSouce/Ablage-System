# -*- coding: utf-8 -*-
"""
Barcode/QR Detection database models for Ablage-System.

Speichert erkannte Barcodes und QR-Codes pro Dokument:
- SEPA-QR Codes (EPC-Standard)
- EAN-13/EAN-8 Produktcodes
- Code-128, Code-39 Logistik-Codes
- DataMatrix, PDF-417

Feinpoliert und durchdacht - Enterprise-grade Barcode Detection.
"""

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from sqlalchemy import (
    Column,
    String,
    Integer,
    DateTime,
    Float,
    ForeignKey,
    Index,
    CheckConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.models import Base, CrossDBJSON


class BarcodeCodeType(str, Enum):
    """Typen von erkannten Codes."""

    QR_CODE = "qr_code"
    SEPA_QR = "sepa_qr"
    EAN_13 = "ean_13"
    EAN_8 = "ean_8"
    CODE_128 = "code_128"
    CODE_39 = "code_39"
    DATA_MATRIX = "data_matrix"
    PDF_417 = "pdf_417"
    UNKNOWN = "unknown"


class BarcodeCategory(str, Enum):
    """Kategorien von erkannten Codes."""

    PAYMENT = "payment"
    PRODUCT = "product"
    LOGISTICS = "logistics"
    DOCUMENT = "document"
    URL = "url"
    OTHER = "other"


class BarcodeDetection(Base):
    """
    Einzelne Barcode/QR-Code-Erkennung fuer ein Dokument.

    Speichert den erkannten Code mit Position, Typ, Konfidenz
    und geparsten Daten (z.B. SEPA-Zahlungsinformationen).
    """

    __tablename__ = "barcode_detections"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Dokument-Referenz
    document_id = Column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Code-Typ und Kategorie
    code_type = Column(
        String(30),
        nullable=False,
        index=True,
    )
    category = Column(
        String(20),
        nullable=False,
        index=True,
    )

    # Rohdaten des erkannten Codes
    raw_value = Column(String(4096), nullable=False)

    # Geparste/strukturierte Daten (z.B. SEPA-Payment, EAN-Validierung)
    parsed_data = Column(CrossDBJSON, default=dict)

    # Position im Bild (Bounding Box)
    position_x = Column(Integer, nullable=False, default=0)
    position_y = Column(Integer, nullable=False, default=0)
    position_width = Column(Integer, nullable=False, default=0)
    position_height = Column(Integer, nullable=False, default=0)

    # Seite im Dokument (1-basiert)
    page_number = Column(Integer, nullable=False, default=1)

    # Erkennungs-Konfidenz (0.0 - 1.0)
    confidence = Column(Float, nullable=False, default=0.0)

    # Multi-Tenant Support
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Zeitstempel
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        index=True,
    )

    # Relationships
    document = relationship("Document", backref="barcode_detections")
    company = relationship("Company", backref="barcode_detections")

    # Table constraints and indexes
    __table_args__ = (
        Index(
            "ix_barcode_detections_document_page",
            "document_id",
            "page_number",
        ),
        Index(
            "ix_barcode_detections_category_company",
            "category",
            "company_id",
        ),
        CheckConstraint(
            "confidence >= 0.0 AND confidence <= 1.0",
            name="ck_barcode_confidence_range",
        ),
        CheckConstraint(
            "page_number >= 1",
            name="ck_barcode_page_positive",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<BarcodeDetection(id={self.id}, "
            f"document_id={self.document_id}, "
            f"code_type={self.code_type}, "
            f"category={self.category})>"
        )
