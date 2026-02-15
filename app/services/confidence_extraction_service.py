# -*- coding: utf-8 -*-
"""
Confidence Extraction Service - Orchestrierung fuer KI-Pipeline Feature #4.

Orchestriert die Confidence-basierte Extraktion fuer ein Dokument:
- Extrahiert Daten mit Confidence-Scoring pro Feld
- Klassifiziert Felder in AUTO_ACCEPT / REVIEW_NEEDED / MANUAL_REQUIRED
- Generiert Confidence-Reports
- Verarbeitet Benutzer-Korrekturen und triggert Lernen

Baut auf dem existierenden ExtractionConfidenceService auf und ergaenzt
ihn um Orchestrierungs- und Reporting-Funktionen.

Feinpoliert und durchdacht - Vertrauenswuerdige Extraktion.
"""

import structlog
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from uuid import UUID

from sqlalchemy import select, and_, func, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.datetime_utils import utc_now
from app.core.safe_errors import safe_error_log
from app.db.models import Document, BusinessEntity, OCRResult
from app.db.models_ki_pipeline import (
    ExtractionConfidence,
    ConfidenceLevel,
    LearningProfile,
)
from app.services.extraction_confidence_service import (
    ExtractionConfidenceService,
    get_extraction_confidence_service,
    _determine_confidence_level,
)

logger = structlog.get_logger(__name__)


# =============================================================================
# DATA CLASSES
# =============================================================================


@dataclass
class FieldConfidenceReport:
    """Confidence-Report fuer ein einzelnes Feld."""
    field_name: str
    extracted_value: str
    confidence_score: float
    confidence_level: str
    is_corrected: bool
    corrected_value: Optional[str]
    extraction_method: str

    def to_dict(self) -> Dict[str, str]:
        """Konvertiert zu Dictionary."""
        return {
            "field_name": self.field_name,
            "extracted_value": self.extracted_value,
            "confidence_score": str(self.confidence_score),
            "confidence_level": self.confidence_level,
            "is_corrected": str(self.is_corrected),
            "corrected_value": self.corrected_value or "",
            "extraction_method": self.extraction_method,
        }


@dataclass
class DocumentConfidenceReport:
    """Gesamter Confidence-Report fuer ein Dokument."""
    document_id: str
    total_fields: int
    auto_accepted: int
    review_needed: int
    manual_required: int
    average_confidence: float
    fields: List[FieldConfidenceReport]

    def to_dict(self) -> Dict[str, object]:
        """Konvertiert zu Dictionary."""
        return {
            "document_id": self.document_id,
            "total_fields": self.total_fields,
            "auto_accepted": self.auto_accepted,
            "review_needed": self.review_needed,
            "manual_required": self.manual_required,
            "average_confidence": round(self.average_confidence, 4),
            "fields": [f.to_dict() for f in self.fields],
        }


# =============================================================================
# FIELD EXTRACTION MAPPING
# =============================================================================

# Mapping von extracted_data JSONB Feldern auf Feld-Namen
INVOICE_FIELD_PATHS: Dict[str, str] = {
    "invoice_number": "invoice.invoice_number",
    "invoice_date": "invoice.invoice_date",
    "due_date": "invoice.due_date",
    "total_gross": "invoice.total_gross",
    "total_net": "invoice.total_net",
    "vat_amount": "invoice.vat_amount",
    "vat_rate": "invoice.vat_rate",
    "supplier_name": "invoice.supplier_name",
    "customer_name": "invoice.customer_name",
    "currency": "invoice.currency",
    "payment_terms": "invoice.payment_terms",
    "iban": "invoice.iban",
    "bic": "invoice.bic",
    "vat_id": "invoice.vat_id",
    "order_number": "invoice.order_number",
    "delivery_note_number": "invoice.delivery_note_number",
}

ORDER_FIELD_PATHS: Dict[str, str] = {
    "order_number": "order.order_number",
    "order_date": "order.order_date",
    "supplier_name": "order.supplier_name",
    "total_amount": "order.total_amount",
}

COMMON_FIELD_PATHS: Dict[str, str] = {
    "vat_ids": "vat_ids",
    "ibans": "ibans",
}


# =============================================================================
# SERVICE
# =============================================================================


class ConfidenceExtractionService:
    """Orchestriert die Confidence-basierte Extraktion fuer KI-Pipeline.

    Nutzt den existierenden ExtractionConfidenceService fuer die
    Einzelfeld-Berechnung und ergaenzt Orchestrierungs-Logik.
    """

    def __init__(self) -> None:
        self._confidence_svc = get_extraction_confidence_service()

    async def extract_with_confidence(
        self,
        db: AsyncSession,
        document_id: UUID,
    ) -> List[ExtractionConfidence]:
        """Extrahiert Daten mit Confidence-Scoring pro Feld.

        Laedt das Dokument, extrahiert Felder aus extracted_data JSONB
        und berechnet fuer jedes Feld einen individuellen Score.

        Args:
            db: Datenbank-Session
            document_id: Dokument-ID

        Returns:
            Liste von ExtractionConfidence-Eintraegen

        Raises:
            ValueError: Wenn das Dokument nicht gefunden wurde
        """
        # Dokument laden
        result = await db.execute(
            select(Document).where(
                and_(
                    Document.id == document_id,
                    Document.deleted_at.is_(None),
                )
            )
        )
        doc = result.scalar_one_or_none()
        if not doc:
            raise ValueError(f"Dokument {document_id} nicht gefunden")

        # Bereits vorhandene Confidence-Records pruefen
        existing = await db.execute(
            select(func.count())
            .select_from(ExtractionConfidence)
            .where(ExtractionConfidence.document_id == document_id)
        )
        if existing.scalar_one() > 0:
            logger.info(
                "confidence_already_exists",
                document_id=str(document_id),
            )
            return await self._confidence_svc.get_document_confidence(db, document_id)

        # Felder aus extracted_data extrahieren
        extracted_data = doc.extracted_data or {}
        fields = self._extract_fields_from_data(extracted_data)

        if not fields:
            logger.warning(
                "no_extracted_fields",
                document_id=str(document_id),
            )
            return []

        # Lieferantenname und Dokumenttyp fuer Lernprofil
        supplier_name = self._get_supplier_name(extracted_data)
        document_type = doc.document_type

        # OCR-Backend als Extraktionsmethode
        extraction_method = self._determine_extraction_method(doc.ocr_backend_used)

        # Confidence-Scores berechnen
        records = await self._confidence_svc.process_document_extraction(
            db=db,
            document_id=document_id,
            company_id=doc.company_id,
            extracted_fields=fields,
            extraction_method=extraction_method,
            supplier_name=supplier_name,
            document_type=document_type,
        )

        await db.commit()

        logger.info(
            "confidence_extraction_completed",
            document_id=str(document_id),
            field_count=len(records),
        )

        return records

    async def score_field_confidence(
        self,
        field_name: str,
        value: str,
        extraction_metadata: Optional[Dict[str, str]] = None,
    ) -> float:
        """Berechnet Confidence-Score fuer ein einzelnes Feld.

        Stateless Berechnung ohne DB-Zugriff.

        Args:
            field_name: Name des Feldes
            value: Extrahierter Wert
            extraction_metadata: Optionale Extraktions-Metadaten

        Returns:
            Confidence-Score zwischen 0.0 und 1.0
        """
        from app.services.extraction_confidence_service import (
            METHOD_BASE_CONFIDENCE,
            FIELD_CONFIDENCE_ADJUSTMENTS,
            FIELD_VALIDATION_PATTERNS,
        )
        import re

        method = "ocr"
        if extraction_metadata:
            method = extraction_metadata.get("method", "ocr")

        base_score = METHOD_BASE_CONFIDENCE.get(method, 0.7)
        field_adj = FIELD_CONFIDENCE_ADJUSTMENTS.get(field_name, 0.0)
        score = base_score + field_adj

        # Plausibilitaetspruefung
        pattern = FIELD_VALIDATION_PATTERNS.get(field_name)
        if pattern and value:
            normalized = value.replace(" ", "").strip()
            if pattern.match(normalized):
                score += 0.05
            else:
                score -= 0.10

        # Wert-Laenge-Check
        if not value or len(value.strip()) < 2:
            score -= 0.30

        return max(0.0, min(1.0, round(score, 4)))

    def classify_confidence_level(self, score: float) -> str:
        """Klassifiziert einen Confidence-Score in eine Stufe.

        Args:
            score: Confidence-Score (0.0 - 1.0)

        Returns:
            ConfidenceLevel-Wert (high/medium/low)
        """
        return _determine_confidence_level(score)

    async def get_document_confidence_report(
        self,
        db: AsyncSession,
        document_id: UUID,
    ) -> DocumentConfidenceReport:
        """Generiert einen Confidence-Report fuer ein Dokument.

        Args:
            db: Datenbank-Session
            document_id: Dokument-ID

        Returns:
            DocumentConfidenceReport mit allen Feldern
        """
        records = await self._confidence_svc.get_document_confidence(
            db, document_id
        )

        field_reports: List[FieldConfidenceReport] = []
        for rec in records:
            field_reports.append(FieldConfidenceReport(
                field_name=rec.field_name,
                extracted_value=rec.extracted_value or "",
                confidence_score=rec.confidence_score,
                confidence_level=rec.confidence_level,
                is_corrected=rec.was_corrected,
                corrected_value=rec.corrected_value,
                extraction_method=rec.extraction_method,
            ))

        auto_accepted = sum(
            1 for r in records if r.confidence_level == ConfidenceLevel.HIGH.value
        )
        review_needed = sum(
            1 for r in records if r.confidence_level == ConfidenceLevel.MEDIUM.value
        )
        manual_required = sum(
            1 for r in records if r.confidence_level == ConfidenceLevel.LOW.value
        )

        total = len(records)
        avg_confidence = (
            sum(r.confidence_score for r in records) / total if total > 0 else 0.0
        )

        return DocumentConfidenceReport(
            document_id=str(document_id),
            total_fields=total,
            auto_accepted=auto_accepted,
            review_needed=review_needed,
            manual_required=manual_required,
            average_confidence=avg_confidence,
            fields=field_reports,
        )

    async def get_low_confidence_fields(
        self,
        db: AsyncSession,
        document_id: UUID,
    ) -> List[ExtractionConfidence]:
        """Gibt Felder zurueck die manuelle Pruefung benoetigen.

        Args:
            db: Datenbank-Session
            document_id: Dokument-ID

        Returns:
            Liste der Felder mit Score < 0.9
        """
        return await self._confidence_svc.get_fields_needing_review(
            db, document_id
        )

    async def auto_accept_high_confidence(
        self,
        db: AsyncSession,
        document_id: UUID,
    ) -> int:
        """Akzeptiert automatisch alle Felder mit Score >= 0.9.

        Markiert die Felder als korrigiert (mit dem extrahierten Wert),
        sodass sie nicht mehr im Review-Queue erscheinen.

        Args:
            db: Datenbank-Session
            document_id: Dokument-ID

        Returns:
            Anzahl der automatisch akzeptierten Felder
        """
        result = await db.execute(
            select(ExtractionConfidence).where(
                and_(
                    ExtractionConfidence.document_id == document_id,
                    ExtractionConfidence.confidence_level == ConfidenceLevel.HIGH.value,
                    ExtractionConfidence.was_corrected == False,  # noqa: E712
                )
            )
        )
        high_confidence_records = list(result.scalars().all())

        now = utc_now()
        count = 0
        for rec in high_confidence_records:
            rec.was_corrected = True
            rec.corrected_value = rec.extracted_value
            rec.corrected_at = now
            count += 1

        if count > 0:
            await db.flush()
            logger.info(
                "auto_accepted_high_confidence",
                document_id=str(document_id),
                accepted_count=count,
            )

        return count

    async def apply_user_correction(
        self,
        db: AsyncSession,
        document_id: UUID,
        field_name: str,
        corrected_value: str,
        user_id: UUID,
    ) -> ExtractionConfidence:
        """Verarbeitet eine Benutzer-Korrektur und triggert Lernen.

        Args:
            db: Datenbank-Session
            document_id: Dokument-ID
            field_name: Name des Feldes
            corrected_value: Korrigierter Wert
            user_id: ID des Benutzers

        Returns:
            Aktualisierter ExtractionConfidence-Record

        Raises:
            ValueError: Wenn das Feld nicht gefunden wurde
        """
        result = await db.execute(
            select(ExtractionConfidence).where(
                and_(
                    ExtractionConfidence.document_id == document_id,
                    ExtractionConfidence.field_name == field_name,
                )
            )
        )
        record = result.scalar_one_or_none()
        if not record:
            raise ValueError(
                f"Feld '{field_name}' fuer Dokument {document_id} nicht gefunden"
            )

        # Korrektur anwenden
        old_value = record.extracted_value
        now = utc_now()
        record.was_corrected = True
        record.corrected_value = corrected_value
        record.corrected_by = user_id
        record.corrected_at = now
        await db.flush()

        # Lernen triggern
        try:
            from app.services.extraction_learning_service import (
                get_extraction_learning_service,
            )
            learning_svc = get_extraction_learning_service()

            # Dokument-Infos fuer Lernprofil laden
            doc_result = await db.execute(
                select(
                    Document.company_id,
                    Document.document_type,
                    Document.extracted_data,
                ).where(Document.id == document_id)
            )
            doc_row = doc_result.one_or_none()
            if doc_row:
                # Lieferantenname aus extracted_data extrahieren
                supplier_name = self._get_supplier_name(
                    doc_row.extracted_data or {}
                )
                await learning_svc.record_correction(
                    db=db,
                    company_id=doc_row.company_id,
                    document_id=document_id,
                    field_name=field_name,
                    original_value=old_value or "",
                    corrected_value=corrected_value,
                    supplier_name=supplier_name,
                    document_type=doc_row.document_type,
                )
        except Exception as exc:
            safe_error_log(exc, context="learning_from_correction")

        logger.info(
            "user_correction_applied",
            document_id=str(document_id),
            field_name=field_name,
            user_id=str(user_id),
        )

        return record

    # =========================================================================
    # PRIVATE HELPERS
    # =========================================================================

    def _extract_fields_from_data(
        self,
        extracted_data: Dict[str, object],
    ) -> Dict[str, str]:
        """Extrahiert flache Felder aus dem extracted_data JSONB.

        Args:
            extracted_data: Das extracted_data JSONB-Feld des Dokuments

        Returns:
            Dict {field_name: extracted_value_as_string}
        """
        fields: Dict[str, str] = {}

        # Invoice-Felder
        invoice = extracted_data.get("invoice")
        if isinstance(invoice, dict):
            for key in [
                "invoice_number", "supplier_name", "customer_name",
                "total_gross", "total_net", "vat_amount", "vat_rate",
                "currency", "iban", "bic", "vat_id", "order_number",
                "delivery_note_number",
            ]:
                val = invoice.get(key)
                if val is not None:
                    fields[key] = str(val)
            # Datum-Felder
            for key in ["invoice_date", "due_date"]:
                val = invoice.get(key)
                if val is not None:
                    fields[key] = str(val)

        # Order-Felder
        order = extracted_data.get("order")
        if isinstance(order, dict):
            for key in ["order_number", "supplier_name", "total_amount"]:
                val = order.get(key)
                if val is not None and key not in fields:
                    fields[f"order_{key}"] = str(val)

        # Allgemeine Identifiers
        classification = extracted_data.get("classification")
        if isinstance(classification, dict):
            doc_type = classification.get("document_type")
            if doc_type:
                fields["document_type"] = str(doc_type)

        # VAT-IDs und IBANs aus Top-Level
        vat_ids = extracted_data.get("vat_ids")
        if isinstance(vat_ids, list) and vat_ids:
            fields["vat_id"] = str(vat_ids[0])
        ibans = extracted_data.get("ibans")
        if isinstance(ibans, list) and ibans:
            fields["iban"] = str(ibans[0])

        return fields

    def _get_supplier_name(self, extracted_data: Dict[str, object]) -> Optional[str]:
        """Extrahiert den Lieferantennamen aus extracted_data."""
        invoice = extracted_data.get("invoice")
        if isinstance(invoice, dict):
            name = invoice.get("supplier_name")
            if name:
                return str(name)
        order = extracted_data.get("order")
        if isinstance(order, dict):
            name = order.get("supplier_name")
            if name:
                return str(name)
        return None

    def _determine_extraction_method(
        self,
        ocr_backend: Optional[str],
    ) -> str:
        """Bestimmt die Extraktionsmethode basierend auf dem OCR-Backend."""
        if not ocr_backend:
            return "ocr"
        backend_lower = ocr_backend.lower()
        if "deepseek" in backend_lower:
            return "llm"
        if "got" in backend_lower:
            return "llm"
        return "ocr"


# =============================================================================
# SINGLETON
# =============================================================================

_service_instance: Optional[ConfidenceExtractionService] = None


def get_confidence_extraction_service() -> ConfidenceExtractionService:
    """Gibt die Singleton-Instanz des ConfidenceExtractionService zurueck."""
    global _service_instance
    if _service_instance is None:
        _service_instance = ConfidenceExtractionService()
    return _service_instance
