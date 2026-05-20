# -*- coding: utf-8 -*-
"""
Intelligent Document Matcher - Automatisches Dokumenten-Matching.

Verknüpft zusammengehörige Dokumente automatisch:
- Rechnung ↔ Lieferschein ↔ Bestellung
- Angebot ↔ Auftrag ↔ Rechnung

Mehrere Matching-Strategien mit Confidence-Scores und Erklärungen.

Vision 2026 Q2 - Intelligent Document Matching
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID, uuid4

import structlog
from prometheus_client import Counter, Histogram
from sqlalchemy import select, and_, or_, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Document, BusinessEntity, InvoiceTracking
from app.core.security.sensitive_data_filter import get_pii_safe_logger
from app.core.safe_errors import safe_error_log

logger = get_pii_safe_logger(__name__)


# =============================================================================
# Prometheus Metriken
# =============================================================================

MATCH_ATTEMPTS = Counter(
    "document_match_attempts_total",
    "Anzahl Match-Versuche",
    ["strategy", "result"]
)

MATCH_CONFIDENCE = Histogram(
    "document_match_confidence",
    "Verteilung der Match-Confidence",
    ["strategy"],
    buckets=[0.5, 0.6, 0.7, 0.75, 0.8, 0.85, 0.9, 0.95, 1.0]
)


# =============================================================================
# Enums
# =============================================================================

class MatchStrategy(str, Enum):
    """Matching-Strategien nach Priorität."""
    REFERENCE_NUMBER = "reference_number"          # Referenznummer identisch (95%)
    PO_NUMBER = "po_number"                        # Bestellnummer identisch (90%)
    CUSTOMER_AMOUNT = "customer_amount"            # Kunde + Betrag (+/-5%) (85%)
    CUSTOMER_DATE_RANGE = "customer_date_range"    # Kunde + Datum im Bereich (80%)
    LINE_ITEMS = "line_items"                      # Artikelpositionen überlappend (75%)


class DocumentRelationType(str, Enum):
    """Typen von Dokumenten-Beziehungen."""
    QUOTE_TO_ORDER = "quote_to_order"              # Angebot → Auftrag
    ORDER_TO_DELIVERY = "order_to_delivery"        # Auftrag → Lieferschein
    DELIVERY_TO_INVOICE = "delivery_to_invoice"    # Lieferschein → Rechnung
    QUOTE_TO_INVOICE = "quote_to_invoice"          # Direkt: Angebot → Rechnung
    RELATED = "related"                            # Sonstige Beziehung


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class MatchResult:
    """Ergebnis eines Document-Matches."""
    id: UUID = field(default_factory=uuid4)

    # Matched Document
    document_id: UUID = field(default_factory=uuid4)
    document_type: str = ""
    document_date: Optional[datetime] = None

    # Match-Details
    strategy: MatchStrategy = MatchStrategy.REFERENCE_NUMBER
    confidence: float = 0.0
    relation_type: DocumentRelationType = DocumentRelationType.RELATED

    # Erklärung
    explanation: str = ""
    match_details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Konvertiert zu Dictionary."""
        return {
            "id": str(self.id),
            "document_id": str(self.document_id),
            "document_type": self.document_type,
            "document_date": self.document_date.isoformat() if self.document_date else None,
            "strategy": self.strategy.value,
            "confidence": self.confidence,
            "relation_type": self.relation_type.value,
            "explanation": self.explanation,
            "match_details": self.match_details,
        }


@dataclass
class MatchingConfig:
    """Konfiguration für Document Matching."""
    # Confidence-Schwellen pro Strategie
    strategy_confidences: Dict[MatchStrategy, float] = field(default_factory=lambda: {
        MatchStrategy.REFERENCE_NUMBER: 0.95,
        MatchStrategy.PO_NUMBER: 0.90,
        MatchStrategy.CUSTOMER_AMOUNT: 0.85,
        MatchStrategy.CUSTOMER_DATE_RANGE: 0.80,
        MatchStrategy.LINE_ITEMS: 0.75,
    })

    # Toleranzen
    amount_tolerance_percent: float = 5.0          # Betrags-Toleranz ±5%
    date_range_days: int = 30                      # Datum-Toleranz ±30 Tage

    # Limits
    max_matches: int = 10                          # Maximale Anzahl Matches
    min_confidence: float = 0.70                   # Mindest-Confidence


# =============================================================================
# Intelligent Document Matcher
# =============================================================================

class IntelligentDocumentMatcher:
    """
    Automatisches Matching zusammengehöriger Dokumente.

    Matching-Strategien (nach Priorität):
    1. Referenznummer identisch (95% Confidence)
    2. Bestellnummer identisch (90% Confidence)
    3. Kunde + Betrag (+/-5%) übereinstimmend (85% Confidence)
    4. Kunde + Datum im Bereich (80% Confidence)
    5. Artikelpositionen überlappend (75% Confidence)
    """

    def __init__(self, db: AsyncSession, config: Optional[MatchingConfig] = None) -> None:
        """Initialisiert den Matcher."""
        self.db = db
        self.config = config or MatchingConfig()

    async def find_matches(
        self,
        document_id: UUID,
        company_id: UUID,
    ) -> List[MatchResult]:
        """
        Findet alle passenden Dokumente für ein gegebenes Dokument.

        Args:
            document_id: ID des Quell-Dokuments
            company_id: Mandant-ID

        Returns:
            Liste von MatchResult, sortiert nach Confidence
        """
        # Dokument laden
        document = await self._get_document(document_id)
        if not document:
            logger.warning("document_not_found", document_id=str(document_id))
            return []

        # Extrahierte Daten aus OCR
        ocr_text = document.ocr_text or ""
        extracted_data = document.extracted_data or {}

        results: List[MatchResult] = []

        # Strategien sequentiell anwenden (nach Priorität)
        strategies = [
            (MatchStrategy.REFERENCE_NUMBER, self._match_by_reference_number),
            (MatchStrategy.PO_NUMBER, self._match_by_po_number),
            (MatchStrategy.CUSTOMER_AMOUNT, self._match_by_customer_amount),
            (MatchStrategy.CUSTOMER_DATE_RANGE, self._match_by_customer_date),
            (MatchStrategy.LINE_ITEMS, self._match_by_line_items),
        ]

        for strategy, match_func in strategies:
            try:
                matches = await match_func(
                    document=document,
                    ocr_text=ocr_text,
                    extracted_data=extracted_data,
                    company_id=company_id,
                )

                for match in matches:
                    match.strategy = strategy
                    results.append(match)

                    MATCH_ATTEMPTS.labels(
                        strategy=strategy.value,
                        result="found"
                    ).inc()

                    MATCH_CONFIDENCE.labels(
                        strategy=strategy.value
                    ).observe(match.confidence)

            except Exception as e:
                logger.error(
                    "matching_strategy_error",
                    strategy=strategy.value,
                    **safe_error_log(e),
                )
                MATCH_ATTEMPTS.labels(
                    strategy=strategy.value,
                    result="error"
                ).inc()

        # Deduplizieren und sortieren
        results = self._deduplicate_and_sort(results)

        # Auf max_matches begrenzen
        results = results[:self.config.max_matches]

        logger.info(
            "document_matching_completed",
            document_id=str(document_id),
            matches_found=len(results),
        )

        return results

    # =========================================================================
    # Strategy 1: Reference Number Matching
    # =========================================================================

    async def _match_by_reference_number(
        self,
        document: Document,
        ocr_text: str,
        extracted_data: Dict[str, Any],
        company_id: UUID,
    ) -> List[MatchResult]:
        """Matching über identische Referenznummer."""
        matches: List[MatchResult] = []

        # Referenznummern aus OCR extrahieren
        reference_numbers = self._extract_reference_numbers(ocr_text)
        if not reference_numbers:
            return matches

        # Suche nach Dokumenten mit gleicher Referenz
        for ref_num in reference_numbers:
            stmt = select(Document).where(
                and_(
                    Document.company_id == company_id,
                    Document.id != document.id,
                    # Suche in extracted_data oder extracted_text
                    or_(
                        Document.extracted_text.ilike(f"%{ref_num}%"),
                        func.cast(Document.extracted_data, String).ilike(f"%{ref_num}%"),
                    )
                )
            ).limit(5)

            result = await self.db.execute(stmt)
            found_docs = result.scalars().all()

            for found_doc in found_docs:
                # Relation-Typ bestimmen
                relation = self._determine_relation_type(
                    document.document_type,
                    found_doc.document_type
                )

                matches.append(MatchResult(
                    document_id=found_doc.id,
                    document_type=found_doc.document_type or "",
                    document_date=found_doc.upload_date,
                    confidence=self.config.strategy_confidences[MatchStrategy.REFERENCE_NUMBER],
                    relation_type=relation,
                    explanation=f"Referenznummer '{ref_num}' identisch",
                    match_details={
                        "reference_number": ref_num,
                        "match_type": "exact",
                    },
                ))

        return matches

    def _extract_reference_numbers(self, text: str) -> List[str]:
        """Extrahiert Referenznummern aus Text."""
        patterns = [
            r'(?:Ref(?:erenz)?\.?|Referenznummer|Ihre\s+Referenz)[\s:\-]*([A-Z0-9\-]{5,20})',
            r'(?:Angebots?|Auftrags?|Bestell)(?:nummer|nr\.?)[\s:\-]*([A-Z0-9\-]{5,20})',
            r'(?:Re|RG|LS|AB|AN)[\s\-]?(\d{4,12})',
        ]

        numbers = set()
        for pattern in patterns:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                numbers.add(match.group(1).strip())

        return list(numbers)

    # =========================================================================
    # Strategy 2: PO Number Matching
    # =========================================================================

    async def _match_by_po_number(
        self,
        document: Document,
        ocr_text: str,
        extracted_data: Dict[str, Any],
        company_id: UUID,
    ) -> List[MatchResult]:
        """Matching über Bestellnummer (PO Number)."""
        matches: List[MatchResult] = []

        # Bestellnummern extrahieren
        po_numbers = self._extract_po_numbers(ocr_text)
        if not po_numbers:
            return matches

        for po_num in po_numbers:
            stmt = select(Document).where(
                and_(
                    Document.company_id == company_id,
                    Document.id != document.id,
                    Document.extracted_text.ilike(f"%{po_num}%"),
                )
            ).limit(5)

            result = await self.db.execute(stmt)
            found_docs = result.scalars().all()

            for found_doc in found_docs:
                relation = self._determine_relation_type(
                    document.document_type,
                    found_doc.document_type
                )

                matches.append(MatchResult(
                    document_id=found_doc.id,
                    document_type=found_doc.document_type or "",
                    document_date=found_doc.upload_date,
                    confidence=self.config.strategy_confidences[MatchStrategy.PO_NUMBER],
                    relation_type=relation,
                    explanation=f"Bestellnummer '{po_num}' übereinstimmend",
                    match_details={
                        "po_number": po_num,
                        "match_type": "exact",
                    },
                ))

        return matches

    def _extract_po_numbers(self, text: str) -> List[str]:
        """Extrahiert Bestellnummern aus Text."""
        patterns = [
            r'(?:Bestell(?:ung)?|PO|Purchase\s*Order)[\s\-\.:]?(?:Nr\.?|Nummer)?[\s:\-]*([A-Z0-9\-]{4,15})',
            r'(?:Ihre\s+Bestellung|Order)[\s:\-]*([A-Z0-9\-]{4,15})',
        ]

        numbers = set()
        for pattern in patterns:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                numbers.add(match.group(1).strip())

        return list(numbers)

    # =========================================================================
    # Strategy 3: Customer + Amount Matching
    # =========================================================================

    async def _match_by_customer_amount(
        self,
        document: Document,
        ocr_text: str,
        extracted_data: Dict[str, Any],
        company_id: UUID,
    ) -> List[MatchResult]:
        """Matching über Kunde + Betrag (±5% Toleranz)."""
        matches: List[MatchResult] = []

        # Entity-ID und Betrag aus Dokument
        entity_id = document.business_entity_id
        if not entity_id:
            return matches

        # Betrag aus extracted_data oder OCR
        amount = self._extract_amount(ocr_text, extracted_data)
        if not amount:
            return matches

        # Toleranz berechnen
        tolerance = amount * Decimal(str(self.config.amount_tolerance_percent / 100))
        amount_min = amount - tolerance
        amount_max = amount + tolerance

        # Suche nach Dokumenten mit gleichem Kunden und ähnlichem Betrag
        stmt = select(Document).where(
            and_(
                Document.company_id == company_id,
                Document.id != document.id,
                Document.business_entity_id == entity_id,
            )
        ).limit(20)

        result = await self.db.execute(stmt)
        found_docs = result.scalars().all()

        for found_doc in found_docs:
            # Betrag des gefundenen Dokuments extrahieren
            found_amount = self._extract_amount(
                found_doc.ocr_text or "",
                found_doc.extracted_data or {}
            )

            if found_amount and amount_min <= found_amount <= amount_max:
                # Confidence basierend auf Betragsabweichung
                deviation = abs(float(found_amount - amount) / float(amount))
                confidence_adjustment = 1.0 - (deviation * 2)  # Mehr Abweichung = weniger Confidence
                adjusted_confidence = self.config.strategy_confidences[MatchStrategy.CUSTOMER_AMOUNT] * confidence_adjustment

                relation = self._determine_relation_type(
                    document.document_type,
                    found_doc.document_type
                )

                matches.append(MatchResult(
                    document_id=found_doc.id,
                    document_type=found_doc.document_type or "",
                    document_date=found_doc.document_date,
                    confidence=min(adjusted_confidence, 0.85),
                    relation_type=relation,
                    explanation=(
                        f"Gleicher Kunde, Betrag {found_amount:.2f} EUR "
                        f"(Abweichung: {deviation*100:.1f}%)"
                    ),
                    match_details={
                        "entity_id": str(entity_id),
                        "source_amount": float(amount),
                        "matched_amount": float(found_amount),
                        "deviation_percent": deviation * 100,
                    },
                ))

        return matches

    def _extract_amount(
        self,
        ocr_text: str,
        extracted_data: Dict[str, Any],
    ) -> Optional[Decimal]:
        """Extrahiert den Gesamtbetrag aus Dokument."""
        # Erst aus extracted_data versuchen
        if extracted_data:
            for key in ["gross_amount", "total_amount", "amount", "gesamtbetrag"]:
                if key in extracted_data and extracted_data[key]:
                    try:
                        return Decimal(str(extracted_data[key]))
                    except (ValueError, TypeError, ArithmeticError):
                        pass

        # Fallback: Aus OCR-Text extrahieren
        patterns = [
            r'(?:Gesamt|Summe|Total|Brutto|Endbetrag)[:\s]*(\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{2}))\s*(?:€|EUR)?',
            r'(\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{2}))\s*(?:€|EUR)?\s*(?:brutto|inkl\.?\s*MwSt)',
        ]

        for pattern in patterns:
            match = re.search(pattern, ocr_text, re.IGNORECASE)
            if match:
                try:
                    amount_str = match.group(1).replace('.', '').replace(',', '.')
                    return Decimal(amount_str)
                except (ValueError, TypeError, ArithmeticError):
                    pass

        return None

    # =========================================================================
    # Strategy 4: Customer + Date Range Matching
    # =========================================================================

    async def _match_by_customer_date(
        self,
        document: Document,
        ocr_text: str,
        extracted_data: Dict[str, Any],
        company_id: UUID,
    ) -> List[MatchResult]:
        """Matching über Kunde + Datum im Bereich."""
        matches: List[MatchResult] = []

        entity_id = document.business_entity_id
        doc_date = document.document_date

        if not entity_id or not doc_date:
            return matches

        # Datum-Bereich
        date_range = timedelta(days=self.config.date_range_days)
        date_min = doc_date - date_range
        date_max = doc_date + date_range

        stmt = select(Document).where(
            and_(
                Document.company_id == company_id,
                Document.id != document.id,
                Document.business_entity_id == entity_id,
                Document.upload_date.between(date_min, date_max),
            )
        ).limit(10)

        result = await self.db.execute(stmt)
        found_docs = result.scalars().all()

        for found_doc in found_docs:
            if found_doc.upload_date:
                days_diff = abs((found_doc.upload_date - doc_date).days)
                # Confidence sinkt mit größerem Datumsabstand
                confidence_factor = 1.0 - (days_diff / (self.config.date_range_days * 2))

                relation = self._determine_relation_type(
                    document.document_type,
                    found_doc.document_type
                )

                matches.append(MatchResult(
                    document_id=found_doc.id,
                    document_type=found_doc.document_type or "",
                    document_date=found_doc.upload_date,
                    confidence=self.config.strategy_confidences[MatchStrategy.CUSTOMER_DATE_RANGE] * confidence_factor,
                    relation_type=relation,
                    explanation=f"Gleicher Kunde, {days_diff} Tage Differenz",
                    match_details={
                        "entity_id": str(entity_id),
                        "days_difference": days_diff,
                    },
                ))

        return matches

    # =========================================================================
    # Strategy 5: Line Items Matching
    # =========================================================================

    async def _match_by_line_items(
        self,
        document: Document,
        ocr_text: str,
        extracted_data: Dict[str, Any],
        company_id: UUID,
    ) -> List[MatchResult]:
        """Matching über überlappende Artikelpositionen."""
        matches: List[MatchResult] = []

        # Line Items aus extracted_data
        line_items = extracted_data.get("line_items", [])
        if not line_items:
            # Versuche Artikelnummern aus Text zu extrahieren
            article_numbers = self._extract_article_numbers(ocr_text)
            if not article_numbers:
                return matches
        else:
            article_numbers = [
                item.get("article_number") or item.get("sku")
                for item in line_items
                if item.get("article_number") or item.get("sku")
            ]

        if not article_numbers:
            return matches

        # Suche nach Dokumenten mit überlappenden Artikeln
        for article_num in article_numbers[:5]:  # Nur erste 5 prüfen
            stmt = select(Document).where(
                and_(
                    Document.company_id == company_id,
                    Document.id != document.id,
                    Document.extracted_text.ilike(f"%{article_num}%"),
                )
            ).limit(5)

            result = await self.db.execute(stmt)
            found_docs = result.scalars().all()

            for found_doc in found_docs:
                # Overlap-Berechnung
                found_articles = self._extract_article_numbers(found_doc.extracted_text or "")
                overlap = set(article_numbers) & set(found_articles)

                if overlap:
                    overlap_ratio = len(overlap) / max(len(article_numbers), len(found_articles))

                    relation = self._determine_relation_type(
                        document.document_type,
                        found_doc.document_type
                    )

                    matches.append(MatchResult(
                        document_id=found_doc.id,
                        document_type=found_doc.document_type or "",
                        document_date=found_doc.document_date,
                        confidence=self.config.strategy_confidences[MatchStrategy.LINE_ITEMS] * overlap_ratio,
                        relation_type=relation,
                        explanation=f"{len(overlap)} gemeinsame Artikel ({overlap_ratio*100:.0f}% Überlappung)",
                        match_details={
                            "overlapping_articles": list(overlap),
                            "overlap_ratio": overlap_ratio,
                        },
                    ))

        return matches

    def _extract_article_numbers(self, text: str) -> List[str]:
        """Extrahiert Artikelnummern aus Text."""
        patterns = [
            r'(?:Art\.?(?:ikel)?|SKU|Pos\.?)[\s\-\.:]?(?:Nr\.?)?[\s:\-]*([A-Z0-9\-]{4,15})',
            r'^\s*([A-Z]{2,3}\d{4,8})\s+',  # Am Zeilenanfang
        ]

        numbers = set()
        for pattern in patterns:
            for match in re.finditer(pattern, text, re.IGNORECASE | re.MULTILINE):
                numbers.add(match.group(1).strip())

        return list(numbers)

    # =========================================================================
    # Helpers
    # =========================================================================

    async def _get_document(self, document_id: UUID) -> Optional[Document]:
        """Lädt ein Dokument aus der Datenbank."""
        stmt = select(Document).where(Document.id == document_id)
        result = await self.db.execute(stmt)
        return result.scalars().first()

    def _determine_relation_type(
        self,
        source_type: Optional[str],
        target_type: Optional[str],
    ) -> DocumentRelationType:
        """Bestimmt den Beziehungstyp zwischen zwei Dokumenttypen."""
        if not source_type or not target_type:
            return DocumentRelationType.RELATED

        source = source_type.lower()
        target = target_type.lower()

        relations = {
            ("quote", "order"): DocumentRelationType.QUOTE_TO_ORDER,
            ("order", "quote"): DocumentRelationType.QUOTE_TO_ORDER,
            ("order", "delivery_note"): DocumentRelationType.ORDER_TO_DELIVERY,
            ("delivery_note", "order"): DocumentRelationType.ORDER_TO_DELIVERY,
            ("delivery_note", "invoice"): DocumentRelationType.DELIVERY_TO_INVOICE,
            ("invoice", "delivery_note"): DocumentRelationType.DELIVERY_TO_INVOICE,
            ("quote", "invoice"): DocumentRelationType.QUOTE_TO_INVOICE,
            ("invoice", "quote"): DocumentRelationType.QUOTE_TO_INVOICE,
        }

        return relations.get((source, target), DocumentRelationType.RELATED)

    def _deduplicate_and_sort(self, matches: List[MatchResult]) -> List[MatchResult]:
        """Dedupliziert und sortiert Matches nach Confidence."""
        # Deduplizieren nach document_id (höchste Confidence behalten)
        seen: Dict[UUID, MatchResult] = {}
        for match in matches:
            if match.document_id not in seen or match.confidence > seen[match.document_id].confidence:
                seen[match.document_id] = match

        # Nach Confidence sortieren
        return sorted(seen.values(), key=lambda m: m.confidence, reverse=True)


# =============================================================================
# Factory
# =============================================================================

def get_intelligent_document_matcher(
    db: AsyncSession,
    config: Optional[MatchingConfig] = None,
) -> IntelligentDocumentMatcher:
    """Factory-Funktion für IntelligentDocumentMatcher."""
    return IntelligentDocumentMatcher(db, config)


# String import für SQLAlchemy (fix)
from sqlalchemy import String
