# -*- coding: utf-8 -*-
"""
SmartMatchingService - Intelligentes Dokument-Matching.

Findet automatisch zusammengehoerige Dokumente:
- Rechnung <-> Lieferschein
- Rechnung <-> Bestellung
- Angebot <-> Bestellung <-> Rechnung

Ziel-Konfidenz: 95%+ für Auto-Link.

Feinpoliert und durchdacht - Enterprise Document Linking.
"""

from __future__ import annotations

import re
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

import structlog
from prometheus_client import Counter, Histogram
from sqlalchemy import select, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Document, DocumentMatch
from app.services.ai.extracted_data_wrapper import ExtractedData, get_extracted_data
from app.services.ai.decision_service import (
    AIDecisionService,
    AIDecisionResult,
    DecisionType,
    get_ai_decision_service,
)

logger = structlog.get_logger(__name__)


# =============================================================================
# Prometheus Metriken
# =============================================================================

MATCHING_REQUESTS = Counter(
    "smart_matching_requests_total",
    "Anzahl der Smart Matching Anfragen",
    ["match_type", "auto_linked"]
)

MATCHING_DURATION = Histogram(
    "smart_matching_duration_seconds",
    "Dauer des Smart Matchings in Sekunden",
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0]
)

MATCHING_CANDIDATES = Histogram(
    "smart_matching_candidates_count",
    "Anzahl der Match-Kandidaten",
    buckets=[0, 1, 2, 5, 10, 20, 50, 100]
)


# =============================================================================
# Match-Typen und Konfiguration
# =============================================================================

class MatchType:
    """Typen von Dokument-Matches."""
    INVOICE_DELIVERY = "invoice_delivery"  # Rechnung <-> Lieferschein
    INVOICE_ORDER = "invoice_order"  # Rechnung <-> Bestellung
    DELIVERY_ORDER = "delivery_order"  # Lieferschein <-> Bestellung
    INVOICE_CONTRACT = "invoice_contract"  # Rechnung <-> Vertrag
    OFFER_ORDER = "offer_order"  # Angebot <-> Bestellung
    CREDIT_INVOICE = "credit_invoice"  # Gutschrift <-> Rechnung


@dataclass
class MatchFeatureWeights:
    """Gewichtung der Match-Features."""
    document_number: float = 0.35
    customer_supplier: float = 0.25
    amount: float = 0.20
    date_proximity: float = 0.10
    positions_overlap: float = 0.10


@dataclass
class MatchCandidate:
    """Ein potentieller Match-Kandidat."""
    target_document_id: uuid.UUID
    match_type: str
    confidence: float
    feature_scores: Dict[str, float] = field(default_factory=dict)
    matched_values: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SmartMatchResult:
    """Ergebnis des Smart Matchings."""
    matches: List[MatchCandidate] = field(default_factory=list)
    total_candidates_checked: int = 0
    processing_time_ms: int = 0


class SmartMatchingService:
    """
    Intelligentes Matching von zusammengehoerigen Dokumenten.

    Nutzt extrahierte Daten (Nummern, Betraege, Entitäten) um
    Dokumente automatisch zu verknüpfen.
    """

    # Konfiguration
    MIN_MATCH_CONFIDENCE = 0.70
    MAX_DATE_DIFF_DAYS = 90  # Max Tage zwischen Dokumenten
    AMOUNT_TOLERANCE_PERCENT = 0.02  # 2% Toleranz bei Betraegen

    def __init__(self) -> None:
        """Initialisiert den Service."""
        self._decision_service = get_ai_decision_service()
        self._weights = MatchFeatureWeights()

    def _normalize_number(self, number: Optional[str]) -> Optional[str]:
        """Normalisiert eine Dokumentnummer."""
        if not number:
            return None
        # Entferne Leerzeichen, Bindestriche, führende Nullen
        normalized = re.sub(r'[\s\-/]', '', str(number).strip())
        normalized = normalized.lstrip('0') or '0'
        return normalized.lower()

    def _calculate_number_similarity(
        self,
        num1: Optional[str],
        num2: Optional[str],
    ) -> float:
        """Berechnet Ähnlichkeit zwischen zwei Nummern."""
        if not num1 or not num2:
            return 0.0

        n1 = self._normalize_number(num1)
        n2 = self._normalize_number(num2)

        if n1 == n2:
            return 1.0

        # Teilstring-Match (z.B. "12345" in "RG-12345")
        if n1 and n2:
            if n1 in n2 or n2 in n1:
                return 0.8

        # Levenshtein-Ähnlichkeit (simplifiziert)
        if n1 and n2 and len(n1) > 3 and len(n2) > 3:
            # Gemeinsame Ziffern am Ende
            common_suffix = 0
            for c1, c2 in zip(reversed(n1), reversed(n2)):
                if c1 == c2:
                    common_suffix += 1
                else:
                    break
            if common_suffix >= 4:
                return 0.6 + (common_suffix / max(len(n1), len(n2))) * 0.3

        return 0.0

    def _calculate_amount_similarity(
        self,
        amount1: Optional[Decimal],
        amount2: Optional[Decimal],
        tolerance: float = 0.02,
    ) -> float:
        """Berechnet Ähnlichkeit zwischen zwei Betraegen."""
        if amount1 is None or amount2 is None:
            return 0.0

        try:
            a1 = float(amount1)
            a2 = float(amount2)
        except (ValueError, TypeError):
            return 0.0

        if a1 == 0 or a2 == 0:
            return 1.0 if a1 == a2 else 0.0

        # Exakter Match
        if a1 == a2:
            return 1.0

        # Innerhalb Toleranz
        diff_percent = abs(a1 - a2) / max(a1, a2)
        if diff_percent <= tolerance:
            return 0.95 - (diff_percent / tolerance) * 0.1

        # Nahes Match (bis 5%)
        if diff_percent <= 0.05:
            return 0.7

        return 0.0

    def _calculate_date_proximity(
        self,
        date1: Optional[datetime],
        date2: Optional[datetime],
        max_days: int = 90,
    ) -> float:
        """Berechnet Naehe zwischen zwei Daten."""
        if date1 is None or date2 is None:
            return 0.5  # Neutral wenn Datum fehlt

        diff_days = abs((date1 - date2).days)

        if diff_days == 0:
            return 1.0
        elif diff_days <= 7:
            return 0.95
        elif diff_days <= 30:
            return 0.85 - (diff_days - 7) / 23 * 0.2
        elif diff_days <= max_days:
            return 0.65 - (diff_days - 30) / (max_days - 30) * 0.35
        else:
            return 0.0

    def _calculate_entity_similarity(
        self,
        entity1_id: Optional[uuid.UUID],
        entity1_name: Optional[str],
        entity2_id: Optional[uuid.UUID],
        entity2_name: Optional[str],
    ) -> float:
        """Berechnet Ähnlichkeit zwischen zwei Entitäten."""
        # ID-Match
        if entity1_id and entity2_id and entity1_id == entity2_id:
            return 1.0

        # Namen-Match (vereinfacht)
        if entity1_name and entity2_name:
            n1 = entity1_name.lower().strip()
            n2 = entity2_name.lower().strip()
            if n1 == n2:
                return 0.95
            # Teilstring
            if len(n1) > 5 and len(n2) > 5:
                if n1 in n2 or n2 in n1:
                    return 0.7

        return 0.0

    def _determine_match_type(
        self,
        source_category: Optional[str],
        target_category: Optional[str],
    ) -> Optional[str]:
        """Bestimmt den Match-Typ basierend auf Kategorien."""
        if not source_category or not target_category:
            return None

        mapping = {
            ("invoice_incoming", "delivery_note"): MatchType.INVOICE_DELIVERY,
            ("delivery_note", "invoice_incoming"): MatchType.INVOICE_DELIVERY,
            ("invoice_incoming", "order"): MatchType.INVOICE_ORDER,
            ("order", "invoice_incoming"): MatchType.INVOICE_ORDER,
            ("delivery_note", "order"): MatchType.DELIVERY_ORDER,
            ("order", "delivery_note"): MatchType.DELIVERY_ORDER,
            ("invoice_incoming", "contract"): MatchType.INVOICE_CONTRACT,
            ("contract", "invoice_incoming"): MatchType.INVOICE_CONTRACT,
            ("offer", "order"): MatchType.OFFER_ORDER,
            ("order", "offer"): MatchType.OFFER_ORDER,
            ("credit_note", "invoice_incoming"): MatchType.CREDIT_INVOICE,
            ("invoice_incoming", "credit_note"): MatchType.CREDIT_INVOICE,
        }

        return mapping.get((source_category, target_category))

    async def _find_candidates(
        self,
        db: AsyncSession,
        source_doc: Document,
        source_data: Optional[ExtractedData],
        company_id: Optional[uuid.UUID],
        max_candidates: int = 100,
    ) -> List[Tuple[Document, Optional[ExtractedData]]]:
        """
        Findet potentielle Match-Kandidaten.

        Filtert nach:
        - Gleiches Company
        - Passender Dokument-Typ
        - Datum innerhalb Range
        """
        # Basis-Query
        query = select(Document).where(
            and_(
                Document.id != source_doc.id,
                Document.deleted_at.is_(None),
            )
        )

        if company_id:
            query = query.where(Document.company_id == company_id)

        # Datum-Filter
        if source_doc.created_at:
            min_date = source_doc.created_at - timedelta(days=self.MAX_DATE_DIFF_DAYS)
            max_date = source_doc.created_at + timedelta(days=self.MAX_DATE_DIFF_DAYS)
            query = query.where(
                and_(
                    Document.created_at >= min_date,
                    Document.created_at <= max_date,
                )
            )

        query = query.limit(max_candidates)
        result = await db.execute(query)
        candidates = result.scalars().all()

        # Erstelle ExtractedData Wrapper für Kandidaten
        candidates_with_data: List[Tuple[Document, Optional[ExtractedData]]] = []
        for doc in candidates:
            data = get_extracted_data(doc)
            candidates_with_data.append((doc, data))

        return candidates_with_data

    def _calculate_match_score(
        self,
        source_doc: Document,
        source_data: Optional[ExtractedData],
        target_doc: Document,
        target_data: Optional[ExtractedData],
    ) -> Optional[MatchCandidate]:
        """Berechnet Match-Score zwischen zwei Dokumenten."""
        # Match-Typ bestimmen
        match_type = self._determine_match_type(
            source_doc.document_category,
            target_doc.document_category,
        )
        if not match_type:
            return None

        feature_scores: Dict[str, float] = {}
        matched_values: Dict[str, Any] = {}

        # 1. Dokumentnummer-Matching
        if source_data and target_data:
            # Rechnungsnummer <-> Bestellnummer/Lieferscheinnummer
            source_ref = source_data.order_number or source_data.invoice_number
            target_ref = target_data.order_number or target_data.invoice_number

            num_score = self._calculate_number_similarity(source_ref, target_ref)
            feature_scores["document_number"] = num_score
            if num_score > 0.5:
                matched_values["document_number"] = {
                    "source": source_ref,
                    "target": target_ref,
                }

        # 2. Kunde/Lieferant-Matching
        entity_score = 0.0
        if source_data and target_data:
            entity_score = self._calculate_entity_similarity(
                source_data.supplier_id,
                source_data.supplier_name,
                target_data.supplier_id,
                target_data.supplier_name,
            )
            if entity_score < 0.5:
                # Auch Customer prüfen
                entity_score = max(
                    entity_score,
                    self._calculate_entity_similarity(
                        source_data.customer_id,
                        source_data.customer_name,
                        target_data.customer_id,
                        target_data.customer_name,
                    )
                )
            if entity_score > 0.5:
                matched_values["entity"] = {
                    "source": source_data.supplier_name or source_data.customer_name,
                    "target": target_data.supplier_name or target_data.customer_name,
                }
        feature_scores["customer_supplier"] = entity_score

        # 3. Betrags-Matching
        amount_score = 0.0
        if source_data and target_data:
            source_amount = source_data.total_gross or source_data.total_net
            target_amount = target_data.total_gross or target_data.total_net
            amount_score = self._calculate_amount_similarity(
                source_amount,
                target_amount,
                self.AMOUNT_TOLERANCE_PERCENT,
            )
            if amount_score > 0.5:
                matched_values["amount"] = {
                    "source": float(source_amount) if source_amount else None,
                    "target": float(target_amount) if target_amount else None,
                }
        feature_scores["amount"] = amount_score

        # 4. Datum-Naehe
        date_score = self._calculate_date_proximity(
            source_doc.created_at,
            target_doc.created_at,
            self.MAX_DATE_DIFF_DAYS,
        )
        feature_scores["date_proximity"] = date_score

        # Gesamt-Confidence berechnen (gewichteter Durchschnitt)
        total_confidence = (
            feature_scores.get("document_number", 0) * self._weights.document_number +
            feature_scores.get("customer_supplier", 0) * self._weights.customer_supplier +
            feature_scores.get("amount", 0) * self._weights.amount +
            feature_scores.get("date_proximity", 0) * self._weights.date_proximity
        )

        if total_confidence < self.MIN_MATCH_CONFIDENCE:
            return None

        return MatchCandidate(
            target_document_id=target_doc.id,
            match_type=match_type,
            confidence=total_confidence,
            feature_scores=feature_scores,
            matched_values=matched_values,
        )

    async def find_matches(
        self,
        db: AsyncSession,
        document_id: uuid.UUID,
        company_id: Optional[uuid.UUID] = None,
        max_results: int = 10,
    ) -> SmartMatchResult:
        """
        Findet Matches für ein Dokument.

        Args:
            db: Database Session
            document_id: Quell-Dokument-ID
            company_id: Optional Company-Filter
            max_results: Max Anzahl Ergebnisse

        Returns:
            SmartMatchResult
        """
        start_time = time.perf_counter()

        # Lade Source-Dokument
        doc_result = await db.execute(
            select(Document).where(Document.id == document_id)
        )
        source_doc = doc_result.scalar_one_or_none()
        if not source_doc:
            return SmartMatchResult()

        # Erstelle ExtractedData Wrapper
        source_data = get_extracted_data(source_doc)

        # Finde Kandidaten
        candidates = await self._find_candidates(
            db, source_doc, source_data, company_id
        )
        MATCHING_CANDIDATES.observe(len(candidates))

        # Berechne Scores
        matches: List[MatchCandidate] = []
        for target_doc, target_data in candidates:
            candidate = self._calculate_match_score(
                source_doc, source_data, target_doc, target_data
            )
            if candidate:
                matches.append(candidate)

        # Sortiere nach Confidence
        matches.sort(key=lambda x: x.confidence, reverse=True)
        matches = matches[:max_results]

        processing_time_ms = int((time.perf_counter() - start_time) * 1000)
        MATCHING_DURATION.observe(processing_time_ms / 1000)

        return SmartMatchResult(
            matches=matches,
            total_candidates_checked=len(candidates),
            processing_time_ms=processing_time_ms,
        )

    async def create_match(
        self,
        db: AsyncSession,
        source_document_id: uuid.UUID,
        target_document_id: uuid.UUID,
        match_type: str,
        confidence: float,
        feature_scores: Dict[str, float],
        company_id: Optional[uuid.UUID] = None,
        user_id: Optional[uuid.UUID] = None,
        auto_link: bool = False,
    ) -> AIDecisionResult:
        """
        Erstellt einen Dokument-Match mit AI-Autonomie.

        Args:
            db: Database Session
            source_document_id: Quell-Dokument
            target_document_id: Ziel-Dokument
            match_type: Match-Typ
            confidence: Konfidenz
            feature_scores: Feature-Scores
            company_id: Optional Company-ID
            user_id: Optional User-ID
            auto_link: Ob automatisch verlinkt werden soll

        Returns:
            AIDecisionResult
        """
        # Decision Value
        decision_value = {
            "source_document_id": str(source_document_id),
            "target_document_id": str(target_document_id),
            "match_type": match_type,
        }

        # Explanation
        explanation = {
            "feature_scores": {k: round(v, 3) for k, v in feature_scores.items()},
            "reasons": [],
        }
        if feature_scores.get("document_number", 0) > 0.7:
            explanation["reasons"].append("Dokumentnummer stimmt überein")
        if feature_scores.get("customer_supplier", 0) > 0.7:
            explanation["reasons"].append("Gleicher Kunde/Lieferant")
        if feature_scores.get("amount", 0) > 0.7:
            explanation["reasons"].append("Betrag stimmt überein")

        # Callback für Auto-Link
        async def apply_match(value: Dict[str, Any]) -> None:
            """Erstellt den Match-Eintrag."""
            match = DocumentMatch(
                id=uuid.uuid4(),
                company_id=company_id,
                source_document_id=source_document_id,
                target_document_id=target_document_id,
                match_type=match_type,
                match_confidence=confidence,
                match_features=feature_scores,
                auto_linked=True,
                linked_by_id=user_id,
                linked_at=datetime.now(timezone.utc),
            )
            db.add(match)
            await db.commit()

            logger.info(
                "document_match_auto_linked",
                source_id=str(source_document_id),
                target_id=str(target_document_id),
                match_type=match_type,
            )

        # Entscheidung erstellen
        ai_result = await self._decision_service.make_decision(
            db=db,
            decision_type=DecisionType.MATCHING,
            decision_value=decision_value,
            confidence=confidence,
            document_id=source_document_id,
            company_id=company_id,
            explanation=explanation,
            features_used=feature_scores,
            apply_callback=apply_match if auto_link else None,
        )

        # Metriken
        MATCHING_REQUESTS.labels(
            match_type=match_type,
            auto_linked=str(ai_result.auto_applied).lower(),
        ).inc()

        return ai_result


# Singleton-Instanz mit Thread-Safety
_smart_matching_service: Optional[SmartMatchingService] = None
_service_lock = threading.Lock()


def get_smart_matching_service() -> SmartMatchingService:
    """Factory für SmartMatchingService Singleton (Thread-safe)."""
    global _smart_matching_service
    if _smart_matching_service is None:
        with _service_lock:
            # Double-check locking pattern
            if _smart_matching_service is None:
                _smart_matching_service = SmartMatchingService()
    return _smart_matching_service
