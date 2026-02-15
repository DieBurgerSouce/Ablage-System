# -*- coding: utf-8 -*-
"""
KI-Pipeline Satellite Models fuer Ablage-System.

Intelligente Extraktion mit Confidence-Scoring, Lern-Profilen,
Cross-Dokument-Matching und automatischer Zusammenfassung.

Modelle:
- ExtractionConfidence: Confidence-Score pro extrahiertem Feld
- LearningProfile: Per-Lieferant / Per-Dokumenttyp Lernprofile
- CrossDocumentMatch: Verknuepfung und Abweichungen zwischen Dokumenten
- DocumentSummary: Deutsche Zusammenfassungen

Feinpoliert und durchdacht - KI-gestuetzte Dokumentenverarbeitung.
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
    Boolean,
    Float,
    Text,
    ForeignKey,
    Index,
    CheckConstraint,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.models import Base, CrossDBJSON


# =============================================================================
# ENUMS
# =============================================================================


class ConfidenceLevel(str, Enum):
    """Confidence-Stufen fuer extrahierte Felder.

    HIGH (>90%): Auto-Akzeptieren (gruen)
    MEDIUM (60-90%): Gelb markiert, manuell pruefen
    LOW (<60%): Rot markiert, manuell eingeben
    """
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class MatchStatus(str, Enum):
    """Status des Cross-Document-Matchings."""
    AUTO_MATCHED = "auto_matched"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"
    REVIEW_NEEDED = "review_needed"


# =============================================================================
# MODELS
# =============================================================================


class ExtractionConfidence(Base):
    """
    Confidence-Score fuer ein einzelnes extrahiertes Feld.

    Speichert den extrahierten Wert, Confidence-Score, die verwendete
    Extraktionsmethode und ggf. die manuelle Korrektur.

    Farbcodierung im Frontend:
    - Score > 0.9: Gruen (auto-akzeptiert)
    - Score 0.6-0.9: Gelb (manuell pruefen)
    - Score < 0.6: Rot (manuell eingeben)
    """
    __tablename__ = "extraction_confidences"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

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

    # Extrahiertes Feld
    field_name = Column(String(200), nullable=False)
    extracted_value = Column(Text, nullable=False)
    confidence_score = Column(Float, nullable=False, default=0.0)
    confidence_level = Column(
        String(20),
        nullable=False,
        default=ConfidenceLevel.LOW.value,
    )

    # Korrektur-Tracking
    was_corrected = Column(Boolean, default=False)
    corrected_value = Column(Text, nullable=True)
    corrected_by = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    corrected_at = Column(DateTime(timezone=True), nullable=True)

    # Extraktionsmethode
    extraction_method = Column(String(50), nullable=False)

    # Zusaetzliche Metadaten (Model-Name, Verarbeitungszeit etc.)
    extraction_metadata = Column(CrossDBJSON, default=dict)

    # Zeitstempel
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    document = relationship("Document", backref="extraction_confidences")
    company = relationship("Company", backref="extraction_confidences")
    corrected_by_user = relationship(
        "User",
        foreign_keys=[corrected_by],
    )

    __table_args__ = (
        Index("ix_extraction_conf_doc_field", "document_id", "field_name"),
        Index("ix_extraction_conf_company_level", "company_id", "confidence_level"),
        Index("ix_extraction_conf_created", "created_at"),
        CheckConstraint(
            "confidence_score >= 0.0 AND confidence_score <= 1.0",
            name="ck_extraction_conf_score_range",
        ),
        CheckConstraint(
            "confidence_level IN ('high', 'medium', 'low')",
            name="ck_extraction_conf_level",
        ),
        CheckConstraint(
            "extraction_method IN ('ocr', 'llm', 'regex', 'template')",
            name="ck_extraction_conf_method",
        ),
    )

    def to_dict(self) -> dict:
        """Konvertiert zu Dictionary fuer API-Responses."""
        return {
            "id": str(self.id),
            "document_id": str(self.document_id),
            "company_id": str(self.company_id),
            "field_name": self.field_name,
            "extracted_value": self.extracted_value,
            "confidence_score": self.confidence_score,
            "confidence_level": self.confidence_level,
            "was_corrected": self.was_corrected,
            "corrected_value": self.corrected_value,
            "corrected_by": str(self.corrected_by) if self.corrected_by else None,
            "corrected_at": self.corrected_at.isoformat() if self.corrected_at else None,
            "extraction_method": self.extraction_method,
            "extraction_metadata": self.extraction_metadata or {},
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class LearningProfile(Base):
    """
    Lernprofil fuer Lieferanten oder Dokumenttypen.

    Speichert Korrekturhistorie und gelernte Feld-Ueberschreibungen.
    Ab 3 identischen Korrekturen wird eine automatische Regel erstellt.

    'Wenn ich 3x den gleichen Lieferanten korrigiere, merke es dir.'
    """
    __tablename__ = "learning_profiles"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Multi-Tenant
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Profil-Identifikation
    profile_type = Column(String(50), nullable=False)  # "supplier", "document_type"
    profile_key = Column(String(200), nullable=False)   # Lieferantenname oder Dokumenttyp

    # Lern-Statistiken
    correction_count = Column(Integer, default=0)

    # Korrektur-Patterns: {field_name: {original: [...], corrected: [...]}}
    correction_patterns = Column(CrossDBJSON, default=dict)

    # Gelernte Feld-Regeln: {field_name: {rule: ..., value: ...}}
    field_overrides = Column(CrossDBJSON, default=dict)

    # Confidence-Boost basierend auf Lernhistorie
    confidence_boost = Column(Float, default=0.0)

    # Zeitstempel
    last_correction_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    # Relationships
    company = relationship("Company", backref="learning_profiles")

    __table_args__ = (
        Index("ix_learning_prof_company_type_key", "company_id", "profile_type", "profile_key"),
        UniqueConstraint("company_id", "profile_type", "profile_key", name="uq_learning_profile"),
        CheckConstraint(
            "profile_type IN ('supplier', 'document_type')",
            name="ck_learning_prof_type",
        ),
        CheckConstraint(
            "confidence_boost >= 0.0 AND confidence_boost <= 0.5",
            name="ck_learning_prof_boost_range",
        ),
    )

    def to_dict(self) -> dict:
        """Konvertiert zu Dictionary fuer API-Responses."""
        return {
            "id": str(self.id),
            "company_id": str(self.company_id),
            "profile_type": self.profile_type,
            "profile_key": self.profile_key,
            "correction_count": self.correction_count,
            "correction_patterns": self.correction_patterns or {},
            "field_overrides": self.field_overrides or {},
            "confidence_boost": self.confidence_boost,
            "last_correction_at": (
                self.last_correction_at.isoformat() if self.last_correction_at else None
            ),
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class CrossDocumentMatch(Base):
    """
    Cross-Dokument-Verknuepfung mit Abweichungsanalyse.

    Speichert Vergleichsergebnisse zwischen zwei Dokumenten:
    Bestellung <-> Lieferschein <-> Rechnung

    'Diese Rechnung passt nicht zum Lieferschein'
    """
    __tablename__ = "cross_document_matches"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Multi-Tenant
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Dokument-Paar
    document_a_id = Column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    document_b_id = Column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Match-Details
    match_type = Column(String(50), nullable=False)
    match_score = Column(Float, nullable=False, default=0.0)

    # Feld-Vergleiche: [{field, value_a, value_b, match: bool}]
    field_comparisons = Column(CrossDBJSON, default=list)

    # Abweichungen: [{field, expected, actual, severity, description}]
    discrepancies = Column(CrossDBJSON, default=list)

    # Status
    status = Column(
        String(30),
        nullable=False,
        default=MatchStatus.AUTO_MATCHED.value,
    )
    reviewed_by = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Zeitstempel
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    company = relationship("Company", backref="cross_document_matches")
    document_a = relationship(
        "Document",
        foreign_keys=[document_a_id],
        backref="matches_as_a",
    )
    document_b = relationship(
        "Document",
        foreign_keys=[document_b_id],
        backref="matches_as_b",
    )
    reviewed_by_user = relationship(
        "User",
        foreign_keys=[reviewed_by],
    )

    __table_args__ = (
        Index("ix_cross_doc_match_company", "company_id"),
        Index("ix_cross_doc_match_doc_a", "document_a_id"),
        Index("ix_cross_doc_match_doc_b", "document_b_id"),
        Index("ix_cross_doc_match_status", "company_id", "status"),
        CheckConstraint(
            "match_score >= 0.0 AND match_score <= 1.0",
            name="ck_cross_doc_match_score_range",
        ),
        CheckConstraint(
            "match_type IN ('order_invoice', 'delivery_invoice', 'duplicate', 'amendment', 'order_delivery')",
            name="ck_cross_doc_match_type",
        ),
        CheckConstraint(
            "status IN ('auto_matched', 'confirmed', 'rejected', 'review_needed')",
            name="ck_cross_doc_match_status",
        ),
    )

    def to_dict(self) -> dict:
        """Konvertiert zu Dictionary fuer API-Responses."""
        return {
            "id": str(self.id),
            "company_id": str(self.company_id),
            "document_a_id": str(self.document_a_id),
            "document_b_id": str(self.document_b_id),
            "match_type": self.match_type,
            "match_score": self.match_score,
            "field_comparisons": self.field_comparisons or [],
            "discrepancies": self.discrepancies or [],
            "status": self.status,
            "reviewed_by": str(self.reviewed_by) if self.reviewed_by else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class DocumentSummary(Base):
    """
    Deutsche Zusammenfassung fuer ein Dokument.

    Format-Beispiel: 'Rechnung #4711 von Mueller GmbH, 3.450 EUR netto,
    Zahlungsziel 30 Tage, 2% Skonto bei 10 Tagen'
    """
    __tablename__ = "document_summaries"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Dokument-Referenz (1:1)
    document_id = Column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )

    # Multi-Tenant
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Zusammenfassung
    summary_text = Column(Text, nullable=False)
    summary_template = Column(String(100), nullable=False, default="default")

    # Strukturierte Fakten: {type, number, supplier, amount, due_date, skonto...}
    key_facts = Column(CrossDBJSON, default=dict)

    # Generierungsinformationen
    generated_at = Column(DateTime(timezone=True), nullable=False)
    model_used = Column(String(100), nullable=False, default="template")

    # Relationships
    document = relationship("Document", backref="summary")
    company = relationship("Company", backref="document_summaries")

    __table_args__ = (
        Index("ix_doc_summary_company", "company_id"),
        Index("ix_doc_summary_generated", "generated_at"),
    )

    def to_dict(self) -> dict:
        """Konvertiert zu Dictionary fuer API-Responses."""
        return {
            "id": str(self.id),
            "document_id": str(self.document_id),
            "company_id": str(self.company_id),
            "summary_text": self.summary_text,
            "summary_template": self.summary_template,
            "key_facts": self.key_facts or {},
            "generated_at": self.generated_at.isoformat() if self.generated_at else None,
            "model_used": self.model_used,
        }
