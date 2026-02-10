"""
Datenqualitaets-Ampel Service.

Berechnet einen Composite Quality Score fuer Dokumente basierend auf:
- OCR Confidence (40% Gewichtung)
- Feld-Vollstaendigkeit (35% Gewichtung)
- Verarbeitungs-Status (25% Gewichtung)

Score -> Ampel:
- GRUEN (>=0.80): Vollstaendig und vertrauenswuerdig
- GELB (0.50-0.79): Pruefung empfohlen
- ROT (<0.50): Manuelle Korrektur erforderlich
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple
from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.safe_errors import safe_error_log

logger = structlog.get_logger(__name__)


class AmpelColor(str, Enum):
    """Ampel-Farben fuer Qualitaetsbewertung."""
    GRUEN = "gruen"
    GELB = "gelb"
    ROT = "rot"


@dataclass
class QualityDimension:
    """Einzelne Qualitaetsdimension."""
    name: str
    score: float  # 0.0 - 1.0
    weight: float  # Gewichtung
    details: str
    sub_scores: Dict[str, float] = field(default_factory=dict)


@dataclass
class DocumentQualityScore:
    """Vollstaendiges Qualitaetsergebnis fuer ein Dokument."""
    document_id: str
    score: float  # Composite 0.0 - 1.0
    ampel_color: AmpelColor
    ampel_label: str
    dimensions: List[QualityDimension]
    recommendations: List[str]

    def to_dict(self) -> Dict[str, object]:
        return {
            "document_id": self.document_id,
            "score": round(self.score, 4),
            "ampel_color": self.ampel_color.value,
            "ampel_label": self.ampel_label,
            "dimensions": [
                {
                    "name": d.name,
                    "score": round(d.score, 4),
                    "weight": d.weight,
                    "details": d.details,
                    "sub_scores": {k: round(v, 4) for k, v in d.sub_scores.items()},
                }
                for d in self.dimensions
            ],
            "recommendations": self.recommendations,
        }


@dataclass
class CompanyQualityOverview:
    """Unternehmensweite Qualitaetsuebersicht."""
    total_documents: int
    average_score: float
    gruen_count: int
    gelb_count: int
    rot_count: int
    gruen_percent: float
    gelb_percent: float
    rot_percent: float

    def to_dict(self) -> Dict[str, object]:
        return {
            "total_documents": self.total_documents,
            "average_score": round(self.average_score, 4),
            "verteilung": {
                "gruen": {"anzahl": self.gruen_count, "prozent": round(self.gruen_percent, 1)},
                "gelb": {"anzahl": self.gelb_count, "prozent": round(self.gelb_percent, 1)},
                "rot": {"anzahl": self.rot_count, "prozent": round(self.rot_percent, 1)},
            },
        }


# Required fields per document type
REQUIRED_FIELDS: Dict[str, List[str]] = {
    "invoice": [
        "invoice_number", "invoice_date", "net_amount", "gross_amount",
        "vat_amount", "sender_company", "recipient_company",
    ],
    "order": [
        "order_number", "order_date", "total_amount", "sender_company",
    ],
    "contract": [
        "contract_date", "party_a", "party_b", "subject",
    ],
    "default": [
        "document_date", "sender",
    ],
}


def _score_to_ampel(score: float) -> Tuple[AmpelColor, str]:
    """Konvertiere Score zu Ampel-Farbe und Label."""
    if score >= 0.80:
        return AmpelColor.GRUEN, "Vollstaendig und vertrauenswuerdig"
    elif score >= 0.50:
        return AmpelColor.GELB, "Pruefung empfohlen"
    else:
        return AmpelColor.ROT, "Manuelle Korrektur erforderlich"


class DocumentQualityScoreService:
    """Service fuer Dokumenten-Qualitaetsbewertung."""

    # Dimension weights
    WEIGHT_OCR_CONFIDENCE = 0.40
    WEIGHT_FIELD_COMPLETENESS = 0.35
    WEIGHT_PROCESSING_STATUS = 0.25

    async def calculate_quality_score(
        self,
        document_id: str,
        session: AsyncSession,
    ) -> DocumentQualityScore:
        """
        Berechne Composite Quality Score fuer ein Dokument.

        Args:
            document_id: Dokument-ID
            session: DB Session

        Returns:
            DocumentQualityScore mit Ampel-Bewertung
        """
        from app.db.models import Document

        # Load document
        result = await session.execute(
            select(Document).where(Document.id == document_id)
        )
        document = result.scalar_one_or_none()

        if not document:
            raise ValueError(f"Dokument nicht gefunden: {document_id}")

        dimensions: List[QualityDimension] = []
        recommendations: List[str] = []

        # Dimension 1: OCR Confidence (40%)
        ocr_confidence = float(document.ocr_confidence or 0.0)
        ocr_dim = QualityDimension(
            name="OCR-Konfidenz",
            score=ocr_confidence,
            weight=self.WEIGHT_OCR_CONFIDENCE,
            details=self._ocr_confidence_detail(ocr_confidence),
            sub_scores={"raw_confidence": ocr_confidence},
        )
        dimensions.append(ocr_dim)

        if ocr_confidence < 0.70:
            recommendations.append("OCR-Ergebnis manuell pruefen - niedrige Konfidenz")
        elif ocr_confidence < 0.85:
            recommendations.append("Stichprobenartige Pruefung des OCR-Textes empfohlen")

        # Dimension 2: Field Completeness (35%)
        doc_type = getattr(document, "document_type", None) or "default"
        extracted_data = getattr(document, "extracted_data", None) or {}
        field_score, field_sub_scores = self._calculate_field_completeness(
            doc_type, extracted_data
        )
        field_dim = QualityDimension(
            name="Feld-Vollstaendigkeit",
            score=field_score,
            weight=self.WEIGHT_FIELD_COMPLETENESS,
            details=self._field_completeness_detail(field_score, field_sub_scores),
            sub_scores=field_sub_scores,
        )
        dimensions.append(field_dim)

        if field_score < 0.50:
            recommendations.append("Wichtige Felder fehlen - Daten manuell ergaenzen")
        elif field_score < 0.80:
            recommendations.append("Einige Felder unvollstaendig - Datensatz pruefen")

        # Dimension 3: Processing Status (25%)
        status_score, status_sub = self._calculate_processing_status(document)
        status_dim = QualityDimension(
            name="Verarbeitungs-Status",
            score=status_score,
            weight=self.WEIGHT_PROCESSING_STATUS,
            details=self._processing_status_detail(status_score),
            sub_scores=status_sub,
        )
        dimensions.append(status_dim)

        if status_score < 0.50:
            recommendations.append("Dokument noch nicht vollstaendig verarbeitet")

        # Calculate composite score
        composite_score = sum(d.score * d.weight for d in dimensions)
        ampel_color, ampel_label = _score_to_ampel(composite_score)

        if not recommendations:
            recommendations.append("Keine Massnahmen erforderlich")

        quality_score = DocumentQualityScore(
            document_id=document_id,
            score=composite_score,
            ampel_color=ampel_color,
            ampel_label=ampel_label,
            dimensions=dimensions,
            recommendations=recommendations,
        )

        logger.info(
            "document_quality_calculated",
            document_id=document_id,
            score=round(composite_score, 4),
            ampel=ampel_color.value,
        )

        return quality_score

    async def get_company_quality_overview(
        self,
        company_id: str,
        session: AsyncSession,
    ) -> CompanyQualityOverview:
        """
        Unternehmensweite Qualitaetsuebersicht berechnen.

        Args:
            company_id: Unternehmens-ID
            session: DB Session

        Returns:
            CompanyQualityOverview mit Ampel-Verteilung
        """
        from app.db.models import Document
        from sqlalchemy import func

        result = await session.execute(
            select(
                func.count(Document.id).label("total"),
                func.avg(Document.ocr_confidence).label("avg_confidence"),
            ).where(Document.company_id == company_id)
        )
        row = result.one()
        total = int(row.total or 0)
        avg_conf = float(row.avg_confidence or 0.0)

        if total == 0:
            return CompanyQualityOverview(
                total_documents=0,
                average_score=0.0,
                gruen_count=0, gelb_count=0, rot_count=0,
                gruen_percent=0.0, gelb_percent=0.0, rot_percent=0.0,
            )

        # Count by confidence ranges (simplified using OCR confidence as proxy)
        gruen_result = await session.execute(
            select(func.count(Document.id)).where(
                Document.company_id == company_id,
                Document.ocr_confidence >= 0.80,
            )
        )
        gruen_count = int(gruen_result.scalar() or 0)

        gelb_result = await session.execute(
            select(func.count(Document.id)).where(
                Document.company_id == company_id,
                Document.ocr_confidence >= 0.50,
                Document.ocr_confidence < 0.80,
            )
        )
        gelb_count = int(gelb_result.scalar() or 0)

        rot_count = total - gruen_count - gelb_count

        overview = CompanyQualityOverview(
            total_documents=total,
            average_score=avg_conf,
            gruen_count=gruen_count,
            gelb_count=gelb_count,
            rot_count=rot_count,
            gruen_percent=(gruen_count / total * 100) if total > 0 else 0.0,
            gelb_percent=(gelb_count / total * 100) if total > 0 else 0.0,
            rot_percent=(rot_count / total * 100) if total > 0 else 0.0,
        )

        logger.info(
            "company_quality_overview",
            company_id=company_id,
            total=total,
            average=round(avg_conf, 4),
        )

        return overview

    async def recalculate_quality_score(
        self,
        document_id: str,
        session: AsyncSession,
    ) -> DocumentQualityScore:
        """Force-Recalculate Quality Score."""
        logger.info("quality_score_recalculation", document_id=document_id)
        return await self.calculate_quality_score(document_id, session)

    def _calculate_field_completeness(
        self,
        doc_type: str,
        extracted_data: Optional[Dict[str, object]],
    ) -> Tuple[float, Dict[str, float]]:
        """Calculate field completeness score."""
        required = REQUIRED_FIELDS.get(doc_type, REQUIRED_FIELDS["default"])
        if not required:
            return 1.0, {}

        sub_scores: Dict[str, float] = {}
        filled = 0

        if isinstance(extracted_data, dict):
            # Check invoice sub-object
            invoice_data = extracted_data.get("invoice", {})
            flat_data = {**extracted_data, **(invoice_data if isinstance(invoice_data, dict) else {})}

            for req_field in required:
                value = flat_data.get(req_field)
                has_value = value is not None and str(value).strip() != ""
                sub_scores[req_field] = 1.0 if has_value else 0.0
                if has_value:
                    filled += 1
        else:
            for req_field in required:
                sub_scores[req_field] = 0.0

        score = filled / len(required) if required else 1.0
        return score, sub_scores

    def _calculate_processing_status(self, document: object) -> Tuple[float, Dict[str, float]]:
        """Calculate processing status score."""
        sub_scores: Dict[str, float] = {}

        # OCR completed?
        status = getattr(document, "status", None)
        sub_scores["ocr_completed"] = 1.0 if status == "completed" else 0.0

        # Has category? (via tags or extracted data)
        extracted_data = getattr(document, "extracted_data", None) or {}
        category = None
        if isinstance(extracted_data, dict):
            category = extracted_data.get("category")
        sub_scores["categorized"] = 1.0 if category else 0.0

        # Has document_type classification?
        doc_type = getattr(document, "document_type", None)
        sub_scores["classified"] = 1.0 if doc_type and doc_type != "other" else 0.0

        score = sum(sub_scores.values()) / len(sub_scores) if sub_scores else 0.0
        return score, sub_scores

    def _ocr_confidence_detail(self, confidence: float) -> str:
        if confidence >= 0.95:
            return "Sehr hohe OCR-Qualitaet"
        elif confidence >= 0.85:
            return "Gute OCR-Qualitaet"
        elif confidence >= 0.70:
            return "Akzeptable OCR-Qualitaet"
        else:
            return "Niedrige OCR-Qualitaet - Pruefung erforderlich"

    def _field_completeness_detail(self, score: float, sub_scores: Dict[str, float]) -> str:
        missing = [k for k, v in sub_scores.items() if v < 1.0]
        if not missing:
            return "Alle Pflichtfelder vorhanden"
        return f"{len(missing)} Pflichtfeld(er) fehlen: {', '.join(missing[:3])}"

    def _processing_status_detail(self, score: float) -> str:
        if score >= 1.0:
            return "Vollstaendig verarbeitet"
        elif score >= 0.5:
            return "Teilweise verarbeitet"
        else:
            return "Verarbeitung unvollstaendig"


# Singleton
_quality_service: Optional[DocumentQualityScoreService] = None


def get_document_quality_service() -> DocumentQualityScoreService:
    """Get singleton instance."""
    global _quality_service
    if _quality_service is None:
        _quality_service = DocumentQualityScoreService()
    return _quality_service
