# -*- coding: utf-8 -*-
"""
OCR Correction Feedback Models fuer ML-Persistenz.

Phase 1.3: Self-Learning speichert Korrekturen persistent in DB statt Redis.

Diese Models ermöglichen:
- Langfristige Speicherung von OCR-Korrekturen (statt 30d Redis TTL)
- Training von ML-Modellen auf historischen Korrekturen
- Analyse von Fehlermustern pro Backend/Dokumenttyp
- A/B Test Evaluierung über Zeit

Feinpoliert und durchdacht - Deutsche Dokumente mit höchster Genauigkeit.
"""

import uuid
from datetime import datetime
from enum import Enum
from typing import Optional

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Boolean,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship

from app.db.models import Base


# =============================================================================
# ENUMS
# =============================================================================

class CorrectionType(str, Enum):
    """Typ der OCR-Korrektur."""
    TEXT = "text"              # Allgemeiner Text
    AMOUNT = "amount"          # Geldbeträge (10,50 vs 10.50)
    DATE = "date"              # Datumsangaben (01.02.2026 vs 2026-02-01)
    ENTITY = "entity"          # Firmen-/Personennamen
    IBAN = "iban"              # Bankdaten
    VAT_ID = "vat_id"          # Steuernummern
    REFERENCE = "reference"    # Referenznummern (Rechnungs-Nr, etc.)


class FeedbackStatus(str, Enum):
    """Status des Feedbacks."""
    PENDING = "pending"        # Neu, noch nicht verarbeitet
    PROCESSED = "processed"    # In Confidence-Adjustments eingeflossen
    REJECTED = "rejected"      # Abgelehnt (z.B. offensichtlicher Fehler)
    VERIFIED = "verified"      # Manuell verifiziert


# =============================================================================
# MODELS
# =============================================================================

class OCRCorrectionFeedback(Base):
    """
    Speichert OCR-Korrekturen für Self-Learning.

    Jede Korrektur, die ein User an OCR-Ergebnissen vornimmt, wird hier
    gespeichert und kann für Training und Confidence-Kalibrierung genutzt werden.
    """
    __tablename__ = "ocr_correction_feedbacks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Beziehungen
    document_id = Column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Dokument zu dem die Korrektur gehört"
    )
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Company für RLS und Tenant-Isolation"
    )
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="User der die Korrektur vorgenommen hat"
    )

    # OCR-Backend Info
    backend = Column(
        String(50),
        nullable=False,
        index=True,
        comment="OCR-Backend (deepseek, got_ocr, surya, etc.)"
    )
    backend_version = Column(
        String(50),
        nullable=True,
        comment="Version des Backends (für Tracking nach Updates)"
    )

    # Korrektur-Details
    field_name = Column(
        String(100),
        nullable=False,
        index=True,
        comment="Name des korrigierten Feldes (invoice_number, amount, etc.)"
    )
    original_value = Column(
        Text,
        nullable=False,
        comment="Ursprünglicher OCR-Wert"
    )
    corrected_value = Column(
        Text,
        nullable=False,
        comment="Korrigierter Wert vom User"
    )
    correction_type = Column(
        String(20),
        nullable=False,
        default=CorrectionType.TEXT,
        comment="Art der Korrektur (text, amount, date, entity, etc.)"
    )

    # Confidence-Tracking
    confidence_before = Column(
        Float,
        nullable=True,
        comment="OCR-Confidence vor Korrektur (0.0-1.0)"
    )
    confidence_after = Column(
        Float,
        nullable=True,
        comment="Kalibrierte Confidence nach Korrektur"
    )

    # Analyse-Daten
    document_type = Column(
        String(50),
        nullable=True,
        index=True,
        comment="Dokumenttyp für typ-spezifische Analyse"
    )
    error_category = Column(
        String(50),
        nullable=True,
        comment="Fehlerkategorie (umlaut, digit_swap, ocr_noise, etc.)"
    )
    edit_distance = Column(
        Integer,
        nullable=True,
        comment="Levenshtein-Distanz zwischen Original und Korrektur"
    )

    # Status und Verarbeitung
    status = Column(
        String(20),
        nullable=False,
        default=FeedbackStatus.PENDING,
        comment="Verarbeitungsstatus"
    )
    processed_at = Column(
        DateTime,
        nullable=True,
        comment="Wann wurde das Feedback verarbeitet"
    )
    verification_source = Column(
        String(50),
        nullable=True,
        comment="Wie wurde verifiziert (manual, auto, ab_test)"
    )

    # Metadaten
    extra_data = Column(
        JSONB,
        nullable=True,
        default=dict,
        comment="Zusätzliche Metadaten (A/B Test ID, etc.)"
    )
    created_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        index=True
    )
    updated_at = Column(
        DateTime,
        nullable=True,
        onupdate=datetime.utcnow
    )

    # Relationships
    document = relationship("Document", back_populates="ocr_feedbacks")
    company = relationship("Company")
    user = relationship("User")

    # Indexes für Performance
    __table_args__ = (
        # Für Confidence-Kalibrierung pro Backend/Feld
        Index(
            "ix_ocr_feedback_backend_field",
            "backend",
            "field_name",
            "status"
        ),
        # Für Company-spezifische Analysen
        Index(
            "ix_ocr_feedback_company_backend",
            "company_id",
            "backend",
            "created_at"
        ),
        # Für Dokumenttyp-Analysen
        Index(
            "ix_ocr_feedback_doctype_field",
            "document_type",
            "field_name",
            "status"
        ),
        # Constraint: Ein Feedback pro Dokument/Feld/User
        UniqueConstraint(
            "document_id",
            "field_name",
            "user_id",
            name="uq_ocr_feedback_doc_field_user"
        ),
        {"comment": "OCR-Korrekturen für Self-Learning und Confidence-Kalibrierung"}
    )

    def __repr__(self) -> str:
        return (
            f"<OCRCorrectionFeedback("
            f"id={self.id}, "
            f"backend={self.backend}, "
            f"field={self.field_name}, "
            f"status={self.status}"
            f")>"
        )

    @property
    def is_significant_correction(self) -> bool:
        """Prüft ob die Korrektur signifikant ist (nicht nur Whitespace)."""
        if not self.original_value or not self.corrected_value:
            return False
        return self.original_value.strip() != self.corrected_value.strip()

    @property
    def is_umlaut_correction(self) -> bool:
        """Prüft ob es sich um eine Umlaut-Korrektur handelt."""
        umlauts = {"ä", "ö", "ü", "Ä", "Ö", "Ü", "ß"}
        original_umlauts = set(c for c in (self.original_value or "") if c in umlauts)
        corrected_umlauts = set(c for c in (self.corrected_value or "") if c in umlauts)
        return original_umlauts != corrected_umlauts


class OCRBackendPerformance(Base):
    """
    Aggregierte Performance-Metriken pro OCR-Backend.

    Wird täglich aus OCRCorrectionFeedback berechnet und gecached
    für schnelle Confidence-Adjustments.
    """
    __tablename__ = "ocr_backend_performance"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Identifikation
    backend = Column(
        String(50),
        nullable=False,
        index=True
    )
    field_name = Column(
        String(100),
        nullable=False,
        index=True
    )
    document_type = Column(
        String(50),
        nullable=True,
        index=True,
        comment="Optional: Typ-spezifische Metriken"
    )
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
        comment="Optional: Company-spezifische Metriken"
    )

    # Metriken
    total_corrections = Column(
        Integer,
        nullable=False,
        default=0,
        comment="Anzahl Korrekturen im Zeitraum"
    )
    total_documents = Column(
        Integer,
        nullable=False,
        default=0,
        comment="Anzahl verarbeiteter Dokumente"
    )
    correction_rate = Column(
        Float,
        nullable=False,
        default=0.0,
        comment="Korrekturrate (0.0-1.0)"
    )
    avg_confidence_before = Column(
        Float,
        nullable=True,
        comment="Durchschnittliche Original-Confidence"
    )
    avg_confidence_adjustment = Column(
        Float,
        nullable=True,
        comment="Empfohlene Confidence-Anpassung"
    )

    # Fehleranalyse
    umlaut_error_rate = Column(
        Float,
        nullable=True,
        comment="Rate der Umlaut-Fehler"
    )
    digit_error_rate = Column(
        Float,
        nullable=True,
        comment="Rate der Ziffern-Fehler"
    )

    # Zeitraum
    period_start = Column(DateTime, nullable=False)
    period_end = Column(DateTime, nullable=False)

    # Timestamps
    calculated_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow
    )

    __table_args__ = (
        # Unique pro Backend/Feld/Typ/Company/Zeitraum
        UniqueConstraint(
            "backend",
            "field_name",
            "document_type",
            "company_id",
            "period_start",
            name="uq_backend_performance_period"
        ),
        Index(
            "ix_backend_perf_lookup",
            "backend",
            "field_name",
            "calculated_at"
        ),
        {"comment": "Aggregierte OCR-Backend Performance für Confidence-Tuning"}
    )

    def __repr__(self) -> str:
        return (
            f"<OCRBackendPerformance("
            f"backend={self.backend}, "
            f"field={self.field_name}, "
            f"correction_rate={self.correction_rate:.2%}"
            f")>"
        )
