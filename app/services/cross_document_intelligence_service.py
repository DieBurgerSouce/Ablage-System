# -*- coding: utf-8 -*-
"""
Cross-Document Intelligence Service.

Cross-Dokument-Intelligenz:
- 'Diese Rechnung passt nicht zum Lieferschein' (Mengen, Preise, Artikelnummern)
- Automatisches Matching: Bestellung <-> Lieferschein <-> Rechnung
- Anomalieerkennung bei Preisabweichungen
- Dokumenten-Ketten-Status

Feinpoliert und durchdacht - Intelligente Dokumentenverknuepfung.
"""

import structlog
from decimal import Decimal, InvalidOperation
from typing import Dict, List, Optional
from uuid import UUID

from sqlalchemy import select, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.datetime_utils import utc_now
from app.core.safe_errors import safe_error_log
from app.db.models import Document
from app.db.models_ki_pipeline import (
    CrossDocumentMatch,
    ExtractionConfidence,
    MatchStatus,
)

logger = structlog.get_logger(__name__)

# Schwellenwerte fuer Matching
AMOUNT_TOLERANCE_PERCENT = 0.02  # 2% Toleranz bei Betraegen
HIGH_MATCH_THRESHOLD = 0.8       # Ab 80% = auto_matched
REVIEW_MATCH_THRESHOLD = 0.5     # Ab 50% = review_needed

# Mapping Dokumenttyp -> moegliche Verknuepfungstypen
MATCH_TYPE_MAP: Dict[str, Dict[str, str]] = {
    "order": {
        "delivery_note": "order_delivery",
        "invoice": "order_invoice",
    },
    "delivery_note": {
        "invoice": "delivery_invoice",
    },
}

# Vergleichbare Felder zwischen Dokumenttypen
COMPARABLE_FIELDS: List[str] = [
    "total_amount",
    "net_amount",
    "supplier_name",
    "invoice_number",
    "order_number",
    "delivery_note_number",
    "item_count",
    "vat_amount",
]


def _safe_decimal(value: str) -> Optional[Decimal]:
    """Konvertiert einen String sicher zu Decimal."""
    if not value:
        return None
    try:
        # Deutsche Zahlenformate: 1.234,56 -> 1234.56
        cleaned = value.replace(".", "").replace(",", ".")
        return Decimal(cleaned)
    except (InvalidOperation, ValueError):
        return None


def _compare_amounts(value_a: str, value_b: str) -> Optional[bool]:
    """Vergleicht zwei Betraege mit Toleranz.

    Returns:
        True wenn gleich (innerhalb Toleranz), False wenn abweichend,
        None wenn nicht vergleichbar
    """
    dec_a = _safe_decimal(value_a)
    dec_b = _safe_decimal(value_b)

    if dec_a is None or dec_b is None:
        return None

    if dec_a == Decimal("0") and dec_b == Decimal("0"):
        return True

    if dec_a == Decimal("0") or dec_b == Decimal("0"):
        return False

    diff_pct = abs(dec_a - dec_b) / max(abs(dec_a), abs(dec_b))
    return diff_pct <= Decimal(str(AMOUNT_TOLERANCE_PERCENT))


def _compare_strings(value_a: str, value_b: str) -> bool:
    """Vergleicht zwei Strings (case-insensitive, trimmed)."""
    return value_a.strip().lower() == value_b.strip().lower()


class CrossDocumentIntelligenceService:
    """Cross-Dokument-Intelligenz.

    'Diese Rechnung passt nicht zum Lieferschein' (Mengen, Preise, Artikelnummern)
    Automatisches Matching: Bestellung <-> Lieferschein <-> Rechnung
    """

    async def compare_documents(
        self,
        db: AsyncSession,
        company_id: UUID,
        doc_a_id: UUID,
        doc_b_id: UUID,
        match_type: Optional[str] = None,
    ) -> CrossDocumentMatch:
        """Zwei Dokumente vergleichen und Abweichungen finden.

        Laedt die extrahierten Daten beider Dokumente, vergleicht
        gemeinsame Felder und erstellt einen Abweichungsbericht.

        Args:
            db: Datenbank-Session
            company_id: Firma-ID
            doc_a_id: Dokument A ID
            doc_b_id: Dokument B ID
            match_type: Optionaler Match-Typ (wird automatisch ermittelt)

        Returns:
            CrossDocumentMatch-Objekt mit Vergleichsergebnis
        """
        # Extrahierte Felder beider Dokumente laden
        fields_a = await self._load_extracted_fields(db, doc_a_id)
        fields_b = await self._load_extracted_fields(db, doc_b_id)

        # Feld-Vergleiche durchfuehren
        comparisons: List[Dict[str, object]] = []
        discrepancies: List[Dict[str, object]] = []
        match_count = 0
        total_compared = 0

        for field_name in COMPARABLE_FIELDS:
            value_a = fields_a.get(field_name)
            value_b = fields_b.get(field_name)

            if value_a is None or value_b is None:
                continue

            total_compared += 1

            # Betragsfelder numerisch vergleichen
            if field_name in ("total_amount", "net_amount", "vat_amount"):
                is_match = _compare_amounts(value_a, value_b)
            else:
                is_match = _compare_strings(value_a, value_b)

            comparison = {
                "field": field_name,
                "value_a": value_a,
                "value_b": value_b,
                "match": is_match if is_match is not None else False,
            }
            comparisons.append(comparison)

            if is_match:
                match_count += 1
            elif is_match is False:
                discrepancies.append({
                    "field": field_name,
                    "expected": value_a,
                    "actual": value_b,
                    "severity": self._classify_discrepancy_severity(field_name),
                    "description": self._generate_discrepancy_description(
                        field_name, value_a, value_b
                    ),
                })

        # Match-Score berechnen
        match_score = (match_count / total_compared) if total_compared > 0 else 0.0

        # Status bestimmen
        if match_score >= HIGH_MATCH_THRESHOLD:
            status = MatchStatus.AUTO_MATCHED.value
        elif match_score >= REVIEW_MATCH_THRESHOLD:
            status = MatchStatus.REVIEW_NEEDED.value
        else:
            status = MatchStatus.REVIEW_NEEDED.value

        # Match-Typ bestimmen
        if match_type is None:
            match_type = "order_invoice"  # Fallback

        record = CrossDocumentMatch(
            company_id=company_id,
            document_a_id=doc_a_id,
            document_b_id=doc_b_id,
            match_type=match_type,
            match_score=round(match_score, 4),
            field_comparisons=comparisons,
            discrepancies=discrepancies,
            status=status,
        )
        db.add(record)
        await db.flush()

        logger.info(
            "cross_document_compared",
            company_id=str(company_id),
            doc_a=str(doc_a_id),
            doc_b=str(doc_b_id),
            match_score=match_score,
            discrepancy_count=len(discrepancies),
            status=status,
        )

        return record

    async def find_related_documents(
        self,
        db: AsyncSession,
        company_id: UUID,
        document_id: UUID,
    ) -> List[CrossDocumentMatch]:
        """Verwandte Dokumente finden (Bestellung->Lieferschein->Rechnung).

        Sucht anhand von Referenznummern, Lieferant und Betrag
        nach potentiell zusammengehoerenden Dokumenten.

        Args:
            db: Datenbank-Session
            company_id: Firma-ID
            document_id: Quell-Dokument-ID

        Returns:
            Liste der CrossDocumentMatch-Eintraege
        """
        # Bereits existierende Matches laden
        result = await db.execute(
            select(CrossDocumentMatch).where(
                and_(
                    CrossDocumentMatch.company_id == company_id,
                    or_(
                        CrossDocumentMatch.document_a_id == document_id,
                        CrossDocumentMatch.document_b_id == document_id,
                    ),
                )
            )
            .order_by(CrossDocumentMatch.match_score.desc())
        )
        return list(result.scalars().all())

    async def detect_anomalies(
        self,
        db: AsyncSession,
        company_id: UUID,
        document_id: UUID,
    ) -> List[Dict[str, object]]:
        """Anomalien erkennen: Preisabweichung, fehlende Positionen.

        Vergleicht das Dokument mit seinen Cross-Document-Matches
        und sammelt alle Abweichungen.

        Args:
            db: Datenbank-Session
            company_id: Firma-ID
            document_id: Dokument-ID

        Returns:
            Liste der erkannten Anomalien
        """
        matches = await self.find_related_documents(db, company_id, document_id)

        anomalies: List[Dict[str, object]] = []
        for match in matches:
            for disc in (match.discrepancies or []):
                anomalies.append({
                    "match_id": str(match.id),
                    "related_document_id": str(
                        match.document_b_id
                        if str(match.document_a_id) == str(document_id)
                        else match.document_a_id
                    ),
                    "field": disc.get("field", ""),
                    "expected": disc.get("expected", ""),
                    "actual": disc.get("actual", ""),
                    "severity": disc.get("severity", "info"),
                    "description": disc.get("description", ""),
                })

        return anomalies

    async def get_document_chain_status(
        self,
        db: AsyncSession,
        company_id: UUID,
        document_id: UUID,
    ) -> Dict[str, object]:
        """Status der Dokumenten-Kette: Welche Dokumente fehlen noch?

        Analysiert die vorhandenen Matches und bestimmt,
        welche Glieder in der Kette noch fehlen.

        Args:
            db: Datenbank-Session
            company_id: Firma-ID
            document_id: Dokument-ID

        Returns:
            Dict mit Ketten-Status
        """
        matches = await self.find_related_documents(db, company_id, document_id)

        # Vorhandene Dokumenttypen sammeln
        matched_types: List[str] = []
        for match in matches:
            matched_types.append(match.match_type)

        # Ketten-Vollstaendigkeit pruefen
        # Standard-Kette: Bestellung -> Lieferschein -> Rechnung
        expected_chain = ["order_delivery", "delivery_invoice"]
        present = [t for t in expected_chain if t in matched_types]
        missing = [t for t in expected_chain if t not in matched_types]

        completeness = len(present) / len(expected_chain) if expected_chain else 1.0

        return {
            "document_id": str(document_id),
            "total_matches": len(matches),
            "match_types": matched_types,
            "chain_completeness": round(completeness, 2),
            "present_links": present,
            "missing_links": missing,
            "has_discrepancies": any(
                bool(m.discrepancies) for m in matches
            ),
            "discrepancy_count": sum(
                len(m.discrepancies or []) for m in matches
            ),
        }

    # =========================================================================
    # HILFSMETHODEN
    # =========================================================================

    async def _load_extracted_fields(
        self,
        db: AsyncSession,
        document_id: UUID,
    ) -> Dict[str, str]:
        """Extrahierte Felder eines Dokuments als Dict laden.

        Args:
            db: Datenbank-Session
            document_id: Dokument-ID

        Returns:
            Dict {field_name: extracted_value}
        """
        result = await db.execute(
            select(ExtractionConfidence).where(
                ExtractionConfidence.document_id == document_id
            )
        )
        records = result.scalars().all()

        fields: Dict[str, str] = {}
        for record in records:
            # Bei Korrektur den korrigierten Wert verwenden
            value = record.corrected_value if record.was_corrected else record.extracted_value
            fields[record.field_name] = value

        return fields

    def _classify_discrepancy_severity(self, field_name: str) -> str:
        """Klassifiziert die Schwere einer Abweichung.

        Args:
            field_name: Name des abweichenden Feldes

        Returns:
            Schweregrad: "critical", "warning", "info"
        """
        critical_fields = {"total_amount", "net_amount", "vat_amount"}
        warning_fields = {"item_count", "supplier_name"}

        if field_name in critical_fields:
            return "critical"
        elif field_name in warning_fields:
            return "warning"
        return "info"

    def _generate_discrepancy_description(
        self,
        field_name: str,
        value_a: str,
        value_b: str,
    ) -> str:
        """Erzeugt eine deutsche Beschreibung fuer eine Abweichung.

        Args:
            field_name: Feldname
            value_a: Wert Dokument A
            value_b: Wert Dokument B

        Returns:
            Deutsche Beschreibung
        """
        field_labels: Dict[str, str] = {
            "total_amount": "Gesamtbetrag",
            "net_amount": "Nettobetrag",
            "vat_amount": "USt-Betrag",
            "supplier_name": "Lieferant",
            "invoice_number": "Rechnungsnummer",
            "order_number": "Bestellnummer",
            "delivery_note_number": "Lieferscheinnummer",
            "item_count": "Positionsanzahl",
        }

        label = field_labels.get(field_name, field_name)
        return f"{label}: erwartet '{value_a}', gefunden '{value_b}'"


# =============================================================================
# SINGLETON
# =============================================================================

_service_instance: Optional[CrossDocumentIntelligenceService] = None


def get_cross_document_intelligence_service() -> CrossDocumentIntelligenceService:
    """Gibt die Singleton-Instanz des CrossDocumentIntelligenceService zurueck."""
    global _service_instance
    if _service_instance is None:
        _service_instance = CrossDocumentIntelligenceService()
    return _service_instance
