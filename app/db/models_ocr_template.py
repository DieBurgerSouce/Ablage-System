# -*- coding: utf-8 -*-
"""
Supplier OCR Template Models.

Vision 2026+ Feature #2: Dokumenten-Template-System (Lieferanten-spezifisch)
OCR-Genauigkeit von 95% auf 99%+ für wiederkehrende Lieferanten.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.models import Base, CrossDBJSON


class FieldExtractionType(str, Enum):
    """Typ der Feld-Extraktion."""
    BOUNDING_BOX = "bounding_box"  # Feste Position (Koordinaten)
    REGEX = "regex"  # Regulaerer Ausdruck
    ANCHOR_RELATIVE = "anchor_relative"  # Relativ zu Anker-Text
    TABLE_CELL = "table_cell"  # Tabellenzelle (Zeile/Spalte)
    SEMANTIC = "semantic"  # KI-basierte semantische Erkennung


class TemplateMatchingStrategy(str, Enum):
    """Strategie zur Template-Erkennung."""
    LOGO_MATCH = "logo_match"  # Logo-Erkennung via Bildvergleich
    LAYOUT_HASH = "layout_hash"  # Layout-Fingerprint
    TEXT_ANCHOR = "text_anchor"  # Feste Textanker (z.B. "Rechnungsnummer:")
    HEADER_PATTERN = "header_pattern"  # Header-Muster
    COMBINED = "combined"  # Mehrere Strategien kombiniert


class SupplierOCRTemplate(Base):
    """
    OCR-Template für einen spezifischen Lieferanten.

    Definiert Feldpositionen und Extraktionsregeln für
    wiederkehrende Dokumente eines Lieferanten.
    """
    __tablename__ = "supplier_ocr_templates"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Lieferanten-Referenz
    entity_id = Column(
        UUID(as_uuid=True),
        ForeignKey("business_entities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Multi-Tenant
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Identifikation
    name = Column(String(255), nullable=False)  # z.B. "Amazon Rechnung Standard"
    description = Column(Text, nullable=True)
    document_type = Column(String(50), nullable=False, default="invoice_incoming")
    version = Column(Integer, nullable=False, default=1)

    # Matching-Strategie
    matching_strategy = Column(
        String(30),
        nullable=False,
        default=TemplateMatchingStrategy.COMBINED.value,
    )

    # Template-Erkennung
    logo_fingerprint = Column(String(500), nullable=True)  # Hash des Logos
    layout_fingerprint = Column(String(500), nullable=True)  # Layout-Hash
    text_anchors = Column(CrossDBJSON, default=list)  # ["Rechnungsnummer", "Amazon.de"]
    header_patterns = Column(CrossDBJSON, default=list)  # Regex-Patterns für Header

    # Thumbnail des Templates (Base64 encoded, optional)
    thumbnail_base64 = Column(Text, nullable=True)

    # Feld-Definitionen
    field_definitions = Column(
        CrossDBJSON,
        nullable=False,
        default=list,
        comment="Liste der zu extrahierenden Felder mit Positionen",
    )
    # Format: [
    #   {
    #     "name": "invoice_number",
    #     "label": "Rechnungsnummer",
    #     "type": "bounding_box",
    #     "coordinates": {"x": 400, "y": 150, "width": 150, "height": 30},
    #     "page": 1,
    #     "preprocessing": ["trim", "remove_prefix:Re-Nr."],
    #     "validation_regex": "^\\d{6,12}$",
    #     "confidence_boost": 0.15
    #   },
    #   {
    #     "name": "total_amount",
    #     "label": "Gesamtbetrag",
    #     "type": "anchor_relative",
    #     "anchor_text": "Gesamtbetrag:",
    #     "offset": {"x": 100, "y": 0, "width": 80, "height": 20},
    #     "preprocessing": ["extract_number"],
    #     "confidence_boost": 0.10
    #   }
    # ]

    # Qualitaetsmetriken
    training_document_count = Column(Integer, nullable=False, default=0)
    accuracy_score = Column(Float, nullable=True)  # 0.0 - 1.0 aus Tests
    last_accuracy_test_at = Column(DateTime(timezone=True), nullable=True)

    # Statistiken
    usage_count = Column(Integer, nullable=False, default=0)
    successful_extractions = Column(Integer, nullable=False, default=0)
    failed_extractions = Column(Integer, nullable=False, default=0)
    average_confidence = Column(Float, nullable=True)  # Durchschnittliche Confidence
    last_used_at = Column(DateTime(timezone=True), nullable=True)

    # Status
    is_active = Column(Boolean, nullable=False, default=True)
    is_verified = Column(Boolean, nullable=False, default=False)  # Manuell geprüft
    auto_apply = Column(Boolean, nullable=False, default=True)  # Automatisch anwenden

    # Auto-Generation
    is_auto_generated = Column(Boolean, nullable=True, default=False)
    source_document_ids = Column(CrossDBJSON, nullable=True)  # List of document UUIDs used for generation
    auto_confidence = Column(Float, nullable=True)  # Confidence score of auto-generated template

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # User References
    created_by_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    verified_by_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Relationships
    entity = relationship("BusinessEntity", backref="ocr_templates")
    company = relationship("Company", backref="supplier_ocr_templates")
    created_by = relationship("User", foreign_keys=[created_by_id])
    verified_by = relationship("User", foreign_keys=[verified_by_id])
    training_samples = relationship(
        "OCRTemplateSample",
        back_populates="template",
        cascade="all, delete-orphan",
    )

    # Indexes
    __table_args__ = (
        Index("ix_ocr_template_entity_company", "entity_id", "company_id"),
        Index("ix_ocr_template_document_type", "document_type"),
        Index("ix_ocr_template_active", "is_active", "auto_apply"),
    )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses."""
        return {
            "id": str(self.id),
            "entity_id": str(self.entity_id),
            "company_id": str(self.company_id),
            "name": self.name,
            "description": self.description,
            "document_type": self.document_type,
            "version": self.version,
            "matching_strategy": self.matching_strategy,
            "text_anchors": self.text_anchors or [],
            "field_definitions": self.field_definitions or [],
            "training_document_count": self.training_document_count,
            "accuracy_score": self.accuracy_score,
            "usage_count": self.usage_count,
            "successful_extractions": self.successful_extractions,
            "failed_extractions": self.failed_extractions,
            "average_confidence": self.average_confidence,
            "is_active": self.is_active,
            "is_verified": self.is_verified,
            "auto_apply": self.auto_apply,
            "is_auto_generated": self.is_auto_generated,
            "source_document_ids": self.source_document_ids or [],
            "auto_confidence": self.auto_confidence,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class OCRTemplateSample(Base):
    """
    Trainings-Dokument für ein OCR-Template.

    Speichert korrigierte Extraktionen als Trainings-Daten.
    """
    __tablename__ = "ocr_template_samples"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Template-Referenz
    template_id = Column(
        UUID(as_uuid=True),
        ForeignKey("supplier_ocr_templates.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Dokument-Referenz
    document_id = Column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Multi-Tenant
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Extrahierte Werte (vor Korrektur)
    original_extraction = Column(CrossDBJSON, nullable=True)

    # Korrigierte Werte (Ground Truth)
    corrected_extraction = Column(CrossDBJSON, nullable=True)

    # Welche Felder wurden korrigiert
    corrected_fields = Column(CrossDBJSON, default=list)  # ["invoice_number", "total_amount"]

    # Qualitaet
    original_confidence = Column(Float, nullable=True)
    improvement_achieved = Column(Float, nullable=True)  # Wie viel besser nach Training

    # Status
    is_verified = Column(Boolean, nullable=False, default=False)
    is_used_for_training = Column(Boolean, nullable=False, default=False)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # User Reference
    corrected_by_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Relationships
    template = relationship("SupplierOCRTemplate", back_populates="training_samples")
    document = relationship("Document")
    company = relationship("Company")
    corrected_by = relationship("User")

    # Indexes
    __table_args__ = (
        Index("ix_ocr_sample_template_doc", "template_id", "document_id"),
    )


class OCRTemplateMatchLog(Base):
    """
    Log für Template-Matching-Versuche.

    Hilft bei der Analyse welche Templates wann matched wurden.
    """
    __tablename__ = "ocr_template_match_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Dokument
    document_id = Column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Multi-Tenant
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Matched Template (optional - kann leer sein wenn kein Match)
    matched_template_id = Column(
        UUID(as_uuid=True),
        ForeignKey("supplier_ocr_templates.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Match-Ergebnis
    match_confidence = Column(Float, nullable=True)
    match_strategy_used = Column(String(30), nullable=True)
    match_details = Column(CrossDBJSON, default=dict)  # Details zum Matching

    # Kandidaten (andere Templates die geprüft wurden)
    candidates_checked = Column(CrossDBJSON, default=list)
    # Format: [{"template_id": "...", "score": 0.75, "reason": "logo mismatch"}]

    # Extraktions-Ergebnis
    extraction_applied = Column(Boolean, nullable=False, default=False)
    extraction_confidence = Column(Float, nullable=True)
    fields_extracted = Column(Integer, nullable=True)

    # Timing
    match_duration_ms = Column(Integer, nullable=True)
    extraction_duration_ms = Column(Integer, nullable=True)

    # Timestamp
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    document = relationship("Document")
    matched_template = relationship("SupplierOCRTemplate")

    # Indexes
    __table_args__ = (
        Index("ix_ocr_match_log_created", "created_at"),
    )
