# -*- coding: utf-8 -*-
"""
Extraction Confidence Service.

Confidence-basierte Extraktion mit Farbcodierung:
- Score > 90%: Auto-Akzeptieren (gruen)
- Score 60-90%: Gelb markiert, manuell prüfen
- Score < 60%: Rot markiert, manuell eingeben

Berechnet Confidence-Scores basierend auf Extraktionsmethode,
Lernprofil-Boost und Plausibilitaetsprüfungen.

Feinpoliert und durchdacht - Vertrauenswuerdige Extraktion.
"""

import re
import structlog
from typing import Dict, List, Optional
from uuid import UUID

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.datetime_utils import utc_now
from app.core.safe_errors import safe_error_log
from app.db.models_ki_pipeline import (
    ExtractionConfidence,
    ConfidenceLevel,
)

logger = structlog.get_logger(__name__)


# =============================================================================
# BASE CONFIDENCE SCORES PER EXTRACTION METHOD
# =============================================================================

METHOD_BASE_CONFIDENCE: Dict[str, float] = {
    "regex": 0.95,      # Regulaere Ausdrücke: hoechste Praezision
    "template": 0.90,   # Template-basiert: sehr zuverlaessig
    "llm": 0.85,        # LLM-Extraktion: gut, aber variabel
    "ocr": 0.75,        # OCR-direkt: abhängig von Qualität
}

# Feldspezifische Adjustierungen
FIELD_CONFIDENCE_ADJUSTMENTS: Dict[str, float] = {
    "invoice_number": 0.05,    # Rechnungsnummern sind gut strukturiert
    "total_amount": 0.0,       # Betraege sind durchschnittlich
    "supplier_name": -0.05,    # Namen können variieren
    "iban": 0.05,              # IBANs haben Prüfsummen
    "vat_id": 0.05,            # USt-IdNr sind validierbar
    "date": 0.0,               # Datumsangaben sind neutral
    "address": -0.10,          # Adressen sind komplex
    "line_items": -0.15,       # Einzelpositionen sind schwierig
}

# Validierungs-Patterns für Plausibilitaetsprüfung
FIELD_VALIDATION_PATTERNS: Dict[str, re.Pattern[str]] = {
    "invoice_number": re.compile(r"^[A-Za-z0-9\-/\.]{2,50}$"),
    "iban": re.compile(r"^[A-Z]{2}\d{2}[A-Z0-9]{11,30}$"),
    "vat_id": re.compile(r"^[A-Z]{2}\d{9,12}$"),
    "total_amount": re.compile(r"^\d{1,10}([,.]\d{1,2})?$"),
}


def _determine_confidence_level(score: float) -> str:
    """Bestimmt die Confidence-Stufe basierend auf dem Score."""
    if score >= 0.9:
        return ConfidenceLevel.HIGH.value
    elif score >= 0.6:
        return ConfidenceLevel.MEDIUM.value
    return ConfidenceLevel.LOW.value


# =============================================================================
# SERVICE
# =============================================================================


class ExtractionConfidenceService:
    """Confidence-basierte Extraktion mit Farbcodierung.

    Score > 90%: Auto-Akzeptieren (gruen)
    Score 60-90%: Gelb markiert, manuell prüfen
    Score < 60%: Rot markiert, manuell eingeben
    """

    async def calculate_field_confidence(
        self,
        db: AsyncSession,
        document_id: UUID,
        company_id: UUID,
        field_name: str,
        extracted_value: str,
        extraction_method: str,
        learning_boost: float = 0.0,
        metadata: Optional[Dict[str, str]] = None,
    ) -> ExtractionConfidence:
        """Berechnet Confidence-Score für ein extrahiertes Feld.

        Berechnung:
        1. Base-Confidence aus Extraktionsmethode
        2. Feld-spezifische Adjustierung
        3. Plausibilitaetsprüfung (Validierung)
        4. Learning-Boost aus Korrekturhistorie
        5. Clamp auf [0.0, 1.0]

        Args:
            db: Datenbank-Session
            document_id: Dokument-ID
            company_id: Firma-ID
            field_name: Name des extrahierten Feldes
            extracted_value: Extrahierter Wert
            extraction_method: Extraktionsmethode (ocr, llm, regex, template)
            learning_boost: Zusätzlicher Boost aus Lernprofil
            metadata: Optionale Metadaten

        Returns:
            ExtractionConfidence-Objekt
        """
        # 1. Base Confidence
        base_score = METHOD_BASE_CONFIDENCE.get(extraction_method, 0.7)

        # 2. Feld-spezifische Adjustierung
        field_adj = FIELD_CONFIDENCE_ADJUSTMENTS.get(field_name, 0.0)
        score = base_score + field_adj

        # 3. Plausibilitaetsprüfung
        pattern = FIELD_VALIDATION_PATTERNS.get(field_name)
        if pattern:
            # Normalisiere für Pattern-Check (Leerzeichen entfernen)
            normalized = extracted_value.replace(" ", "").strip()
            if pattern.match(normalized):
                score += 0.05  # Bonus für valides Format
            else:
                score -= 0.10  # Penalty für invalides Format

        # 4. Wert-Länge-Check (leere/zu kurze Werte sind verdaechtig)
        if not extracted_value or len(extracted_value.strip()) < 2:
            score -= 0.30

        # 5. Learning-Boost
        score += learning_boost

        # 6. Clamp
        score = max(0.0, min(1.0, round(score, 4)))

        # Confidence-Level bestimmen
        level = _determine_confidence_level(score)

        # Erstelle Record
        record = ExtractionConfidence(
            document_id=document_id,
            company_id=company_id,
            field_name=field_name,
            extracted_value=extracted_value,
            confidence_score=score,
            confidence_level=level,
            extraction_method=extraction_method,
            extraction_metadata=metadata or {},
        )
        db.add(record)

        logger.info(
            "extraction_confidence_calculated",
            document_id=str(document_id),
            field_name=field_name,
            score=score,
            level=level,
            method=extraction_method,
        )

        return record

    async def process_document_extraction(
        self,
        db: AsyncSession,
        document_id: UUID,
        company_id: UUID,
        extracted_fields: Dict[str, str],
        extraction_method: str = "ocr",
        supplier_name: Optional[str] = None,
        document_type: Optional[str] = None,
    ) -> List[ExtractionConfidence]:
        """Alle Felder eines Dokuments mit Confidence-Scores versehen.

        Laedt ggf. ein Lernprofil für den Lieferanten/Dokumenttyp
        und berechnet pro Feld einen individuellen Confidence-Score.

        Args:
            db: Datenbank-Session
            document_id: Dokument-ID
            company_id: Firma-ID
            extracted_fields: Dict {field_name: extracted_value}
            extraction_method: Standard-Extraktionsmethode
            supplier_name: Optionaler Lieferantenname für Lernprofil
            document_type: Optionaler Dokumenttyp für Lernprofil

        Returns:
            Liste von ExtractionConfidence-Objekten
        """
        # Lernprofil-Boost laden
        learning_boost = 0.0
        if supplier_name or document_type:
            from app.services.extraction_learning_service import (
                ExtractionLearningService,
            )
            learning_svc = ExtractionLearningService()
            learning_boost = await learning_svc.get_confidence_boost(
                db=db,
                company_id=company_id,
                supplier_name=supplier_name,
                document_type=document_type,
            )

        results: List[ExtractionConfidence] = []
        for field_name, value in extracted_fields.items():
            record = await self.calculate_field_confidence(
                db=db,
                document_id=document_id,
                company_id=company_id,
                field_name=field_name,
                extracted_value=value,
                extraction_method=extraction_method,
                learning_boost=learning_boost,
            )
            results.append(record)

        await db.flush()

        logger.info(
            "document_extraction_processed",
            document_id=str(document_id),
            field_count=len(results),
            high_count=sum(1 for r in results if r.confidence_level == ConfidenceLevel.HIGH.value),
            medium_count=sum(1 for r in results if r.confidence_level == ConfidenceLevel.MEDIUM.value),
            low_count=sum(1 for r in results if r.confidence_level == ConfidenceLevel.LOW.value),
        )

        return results

    async def get_document_confidence(
        self,
        db: AsyncSession,
        document_id: UUID,
    ) -> List[ExtractionConfidence]:
        """Alle Confidence-Scores für ein Dokument abrufen.

        Args:
            db: Datenbank-Session
            document_id: Dokument-ID

        Returns:
            Liste aller ExtractionConfidence-Einträge
        """
        result = await db.execute(
            select(ExtractionConfidence)
            .where(ExtractionConfidence.document_id == document_id)
            .order_by(ExtractionConfidence.field_name)
        )
        return list(result.scalars().all())

    async def get_fields_needing_review(
        self,
        db: AsyncSession,
        document_id: UUID,
    ) -> List[ExtractionConfidence]:
        """Felder die manuelle Prüfung benötigen (Score < 0.9).

        Args:
            db: Datenbank-Session
            document_id: Dokument-ID

        Returns:
            Liste der zu prüfenden Felder (sortiert nach Score aufsteigend)
        """
        result = await db.execute(
            select(ExtractionConfidence)
            .where(
                and_(
                    ExtractionConfidence.document_id == document_id,
                    ExtractionConfidence.confidence_score < 0.9,
                    ExtractionConfidence.was_corrected == False,
                )
            )
            .order_by(ExtractionConfidence.confidence_score.asc())
        )
        return list(result.scalars().all())

    async def submit_correction(
        self,
        db: AsyncSession,
        confidence_id: UUID,
        corrected_value: str,
        user_id: UUID,
    ) -> ExtractionConfidence:
        """Korrektur für ein extrahiertes Feld einreichen.

        Aktualisiert den ExtractionConfidence-Record und stellt
        Daten für das Lernsystem bereit.

        Args:
            db: Datenbank-Session
            confidence_id: ID des ExtractionConfidence-Records
            corrected_value: Korrigierter Wert
            user_id: ID des korrigierenden Benutzers

        Returns:
            Aktualisierter ExtractionConfidence-Record

        Raises:
            ValueError: Wenn der Record nicht gefunden wurde
        """
        result = await db.execute(
            select(ExtractionConfidence)
            .where(ExtractionConfidence.id == confidence_id)
        )
        record = result.scalar_one_or_none()

        if not record:
            raise ValueError(f"ExtractionConfidence {confidence_id} nicht gefunden")

        now = utc_now()
        record.was_corrected = True
        record.corrected_value = corrected_value
        record.corrected_by = user_id
        record.corrected_at = now

        await db.flush()

        logger.info(
            "extraction_correction_submitted",
            confidence_id=str(confidence_id),
            document_id=str(record.document_id),
            field_name=record.field_name,
            original_score=record.confidence_score,
            user_id=str(user_id),
        )

        return record


# =============================================================================
# SINGLETON
# =============================================================================

_service_instance: Optional[ExtractionConfidenceService] = None


def get_extraction_confidence_service() -> ExtractionConfidenceService:
    """Gibt die Singleton-Instanz des ExtractionConfidenceService zurück."""
    global _service_instance
    if _service_instance is None:
        _service_instance = ExtractionConfidenceService()
    return _service_instance
