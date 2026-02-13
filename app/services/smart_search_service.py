# -*- coding: utf-8 -*-
"""
Smart Search Service.

Intelligente Suche mit automatischer Erkennung von NLQ vs. Keyword-Suche.
Kombiniert:
- NLQ Service fuer natuerlichsprachliche Fragen
- Unified Search Service fuer Keyword/Hybrid/Semantic-Suche
- Entity Search Service fuer Kunden/Lieferanten-Suche
- Query Expansion Service fuer deutsche Synonyme

Feature #1 der Feature-Roadmap (Phase 2026 Q1)
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple
from uuid import UUID

import structlog
from prometheus_client import Counter, Histogram
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.safe_errors import safe_error_detail, safe_error_log
from app.db.schemas import SearchFilters, SearchType, SortField, SortOrder
from app.services.ai.nlq_service import NLQService, QueryIntent, get_nlq_service
from app.services.entity_search_service import (
    EntitySearchService,
    get_entity_search_service,
)
from app.services.unified_search_service import (
    UnifiedDocumentResult,
    UnifiedSearchMode,
    UnifiedSearchService,
    get_unified_search_service,
)

logger = structlog.get_logger(__name__)

# ============================================================================
# Prometheus Metrics
# ============================================================================

SMART_SEARCH_REQUESTS = Counter(
    "smart_search_requests_total",
    "Anzahl Smart Search Anfragen",
    ["search_mode", "detected_type"]
)

SMART_SEARCH_DURATION = Histogram(
    "smart_search_duration_seconds",
    "Dauer der Smart Search Anfragen",
    ["search_mode"]
)

SMART_SEARCH_AUTO_DETECTION = Counter(
    "smart_search_auto_detection_total",
    "Auto-Detection NLQ vs Keyword",
    ["detected_type"]
)


# ============================================================================
# Enums and Constants
# ============================================================================


class DetectedQueryType(str, Enum):
    """Auto-erkannter Query-Typ."""
    NLQ = "nlq"  # Natuerlichsprachliche Frage
    KEYWORD = "keyword"  # Keyword-Suche
    MIXED = "mixed"  # Gemischter Typ


# NLQ-Erkennungs-Patterns
NLQ_QUESTION_WORDS = [
    "zeig", "zeige", "finde", "suche", "liste",
    "wie viel", "wie viele", "wieviel", "wieviele",
    "welche", "welcher", "welches",
    "wer", "was", "warum", "wie", "wann", "wo",
    "gibt es", "habe ich", "haben wir",
]

NLQ_AGGREGATION_WORDS = [
    "summe", "gesamt", "insgesamt", "total",
    "durchschnitt", "mittel",
    "anzahl", "zahl",
    "maximum", "minimum", "hoechste", "niedrigste",
]

# Verbs-Pattern fuer natuerliche Satzstruktur
VERB_PATTERN = re.compile(
    r'\b(sind|ist|haben|hat|war|waren|wurde|wurden|'
    r'kosten|kostet|betraegt|betragen|zeig|zeige|finde|suche)\b',
    re.IGNORECASE
)


# ============================================================================
# Data Classes
# ============================================================================


@dataclass
class SmartSearchEntity:
    """Gefundene Business Entity (Kunde/Lieferant)."""
    entity_id: str
    entity_type: str  # "CUSTOMER" oder "SUPPLIER"
    name: str
    display_name: Optional[str]
    match_type: str  # "customer_number", "supplier_number", "matchcode", "iban", "vat_id"
    confidence: float


@dataclass
class SmartSearchInterpretation:
    """Interpretation der Suchanfrage."""
    detected_type: DetectedQueryType
    confidence: float
    reasoning: str  # Warum wurde dieser Typ erkannt?
    nlq_intent: Optional[str] = None  # Bei NLQ: erkannter Intent
    entities_found: List[str] = field(default_factory=list)


@dataclass
class SmartSearchFacets:
    """Verfuegbare Facetten/Filter."""
    document_types: Dict[str, int]  # {"invoice": 5, "contract": 2}
    statuses: Dict[str, int]  # {"pending": 3, "completed": 2}
    date_ranges: Dict[str, int]  # {"last_7_days": 5, "last_30_days": 10}
    entities: Dict[str, int]  # {"entity_id": count}
    total_count: int


@dataclass
class SmartSearchResponse:
    """Antwort der Smart Search."""
    query: str
    detected_type: DetectedQueryType
    interpretation: SmartSearchInterpretation

    # Dokument-Ergebnisse
    documents: List[UnifiedDocumentResult]
    total_documents: int

    # Entity-Ergebnisse
    entities: List[SmartSearchEntity]
    total_entities: int

    # NLQ-spezifisch (optional)
    natural_response: Optional[str] = None
    nlq_confidence: Optional[float] = None

    # Suggestions & Facets
    suggestions: List[str] = field(default_factory=list)
    facets: Optional[SmartSearchFacets] = None

    # Metriken
    search_time_ms: float = 0.0
    document_search_time_ms: Optional[float] = None
    entity_search_time_ms: Optional[float] = None
    nlq_processing_time_ms: Optional[float] = None


# ============================================================================
# Smart Search Service
# ============================================================================


class SmartSearchService:
    """
    Intelligenter Such-Service mit Auto-Detection.

    Erkennt automatisch ob Anfrage eine natuerlichsprachliche Frage
    oder eine Keyword-Suche ist und routet entsprechend.
    """

    def __init__(self) -> None:
        """Initialisiert den Service."""
        self._nlq_service: Optional[NLQService] = None
        self._unified_search: Optional[UnifiedSearchService] = None
        self._entity_search: Optional[EntitySearchService] = None

        # Auto-Detection Thresholds
        self.nlq_confidence_threshold = 0.7
        self.min_query_length_for_nlq = 5

    async def search(
        self,
        db: AsyncSession,
        query: str,
        user_id: UUID,
        company_id: Optional[UUID] = None,
        filters: Optional[SearchFilters] = None,
        limit: int = 20,
        include_suggestions: bool = True,
        include_facets: bool = True,
        force_mode: Optional[DetectedQueryType] = None,
    ) -> SmartSearchResponse:
        """
        Fuehrt eine intelligente Suche durch.

        Args:
            db: Datenbank-Session
            query: Suchanfrage
            user_id: Benutzer-ID
            company_id: Optional Company-ID fuer Multi-Tenant
            filters: Optional Filter (Dokumenttyp, Datum, etc.)
            limit: Maximale Anzahl Ergebnisse
            include_suggestions: Query-Suggestions generieren
            include_facets: Facetten/Aggregationen berechnen
            force_mode: Optional erzwungener Modus (NLQ/KEYWORD)

        Returns:
            SmartSearchResponse mit kombinierten Ergebnissen
        """
        start_time = time.perf_counter()

        # 1. Query-Typ erkennen
        if force_mode:
            detected_type = force_mode
            confidence = 1.0
            reasoning = "Manuell erzwungener Modus"
        else:
            detected_type, confidence, reasoning = self._detect_query_type(query)

        SMART_SEARCH_AUTO_DETECTION.labels(detected_type=detected_type.value).inc()

        interpretation = SmartSearchInterpretation(
            detected_type=detected_type,
            confidence=confidence,
            reasoning=reasoning,
        )

        # Metriken initialisieren
        documents: List[UnifiedDocumentResult] = []
        total_documents = 0
        entities: List[SmartSearchEntity] = []
        total_entities = 0
        natural_response: Optional[str] = None
        nlq_confidence: Optional[float] = None
        suggestions: List[str] = []
        facets: Optional[SmartSearchFacets] = None

        doc_search_time: Optional[float] = None
        entity_search_time: Optional[float] = None
        nlq_time: Optional[float] = None

        try:
            # 2. Parallel: Entity-Suche (immer durchfuehren)
            entity_start = time.perf_counter()
            entities_result = await self._search_entities(
                db=db,
                query=query,
                company_id=company_id,
                limit=min(limit, 10),
            )
            entities = entities_result[0]
            total_entities = entities_result[1]
            entity_search_time = (time.perf_counter() - entity_start) * 1000

            # 3. Haupt-Suche basierend auf erkanntem Typ
            if detected_type == DetectedQueryType.NLQ:
                # NLQ-Modus: Natuerlichsprachliche Verarbeitung
                nlq_start = time.perf_counter()
                nlq_result = await self._execute_nlq_search(
                    db=db,
                    query=query,
                    company_id=company_id,
                    user_id=user_id,
                    limit=limit,
                )
                nlq_time = (time.perf_counter() - nlq_start) * 1000

                # Interpretation erweitern
                interpretation.nlq_intent = nlq_result.intent.value if nlq_result.intent else None
                interpretation.entities_found = [
                    e.original_text for e in nlq_result.extracted_entities
                ]

                # Ergebnisse extrahieren
                if nlq_result.results:
                    documents = self._convert_nlq_to_documents(nlq_result.results)
                    total_documents = nlq_result.result_count

                natural_response = nlq_result.natural_response
                nlq_confidence = nlq_result.confidence

            else:
                # KEYWORD-Modus: Unified Search (Hybrid/FTS/Semantic)
                doc_start = time.perf_counter()
                search_result = await self._execute_keyword_search(
                    db=db,
                    query=query,
                    user_id=user_id,
                    filters=filters,
                    limit=limit,
                )
                doc_search_time = (time.perf_counter() - doc_start) * 1000

                documents = search_result.documents
                total_documents = search_result.total_documents

            # 4. Suggestions generieren (optional)
            if include_suggestions:
                suggestions = self._generate_suggestions(
                    query=query,
                    detected_type=detected_type,
                    has_results=(total_documents > 0),
                )

            # 5. Facets berechnen (optional)
            if include_facets and documents:
                facets = self._calculate_facets(documents, entities)

            # Gesamtzeit
            total_time = (time.perf_counter() - start_time) * 1000

            # Metriken
            SMART_SEARCH_REQUESTS.labels(
                search_mode=detected_type.value,
                detected_type=detected_type.value
            ).inc()
            SMART_SEARCH_DURATION.labels(search_mode=detected_type.value).observe(
                total_time / 1000
            )

            logger.info(
                "smart_search_completed",
                query_length=len(query),
                detected_type=detected_type.value,
                confidence=confidence,
                document_count=len(documents),
                entity_count=len(entities),
                total_time_ms=total_time,
            )

            return SmartSearchResponse(
                query=query,
                detected_type=detected_type,
                interpretation=interpretation,
                documents=documents,
                total_documents=total_documents,
                entities=entities,
                total_entities=total_entities,
                natural_response=natural_response,
                nlq_confidence=nlq_confidence,
                suggestions=suggestions,
                facets=facets,
                search_time_ms=total_time,
                document_search_time_ms=doc_search_time,
                entity_search_time_ms=entity_search_time,
                nlq_processing_time_ms=nlq_time,
            )

        except Exception as e:
            logger.error(
                "smart_search_error",
                query=query[:100],
                detected_type=detected_type.value,
                **safe_error_log(e),
            )
            # Fallback: Leere Ergebnisse mit Fehler
            return SmartSearchResponse(
                query=query,
                detected_type=detected_type,
                interpretation=interpretation,
                documents=[],
                total_documents=0,
                entities=[],
                total_entities=0,
                natural_response=safe_error_detail(e, "Suche"),
                search_time_ms=(time.perf_counter() - start_time) * 1000,
            )

    # ========================================================================
    # Query Type Detection
    # ========================================================================

    def _detect_query_type(self, query: str) -> Tuple[DetectedQueryType, float, str]:
        """
        Erkennt automatisch ob Query NLQ oder Keyword-Suche ist.

        Returns:
            (detected_type, confidence, reasoning)
        """
        query_lower = query.lower().strip()
        query_len = len(query.split())

        # Heuristik 1: Sehr kurze Queries (1-2 Woerter) = Keyword
        if query_len <= 2:
            return (
                DetectedQueryType.KEYWORD,
                0.9,
                "Kurze Query (1-2 Woerter) - Keyword-Suche"
            )

        # Heuristik 2: Fragewoerter am Anfang = NLQ
        for question_word in NLQ_QUESTION_WORDS:
            if query_lower.startswith(question_word):
                return (
                    DetectedQueryType.NLQ,
                    0.95,
                    f"Fragewort erkannt: '{question_word}'"
                )

        # Heuristik 3: Aggregations-Woerter = NLQ
        for agg_word in NLQ_AGGREGATION_WORDS:
            if agg_word in query_lower:
                return (
                    DetectedQueryType.NLQ,
                    0.9,
                    f"Aggregation erkannt: '{agg_word}'"
                )

        # Heuristik 4: Verben in der Query = NLQ (natuerliche Satzstruktur)
        if VERB_PATTERN.search(query_lower):
            if query_len >= 5:  # Mindestens 5 Woerter mit Verb = Satz
                return (
                    DetectedQueryType.NLQ,
                    0.85,
                    "Natuerliche Satzstruktur erkannt (Verb + mehrere Woerter)"
                )

        # Heuristik 5: Lange Queries (6+ Woerter) ohne Operatoren = NLQ
        if query_len >= 6:
            # Check ob Boolean-Operatoren vorhanden (dann eher Keyword)
            has_operators = any(
                op in query_lower for op in ["AND", "OR", "NOT", "+", "-", '"']
            )
            if not has_operators:
                return (
                    DetectedQueryType.NLQ,
                    0.75,
                    "Lange Query ohne Boolean-Operatoren - natuerliche Sprache"
                )

        # Default: Keyword-Suche
        return (
            DetectedQueryType.KEYWORD,
            0.8,
            "Standard Keyword-Suche (keine NLQ-Muster erkannt)"
        )

    # ========================================================================
    # NLQ Search Execution
    # ========================================================================

    async def _execute_nlq_search(
        self,
        db: AsyncSession,
        query: str,
        company_id: Optional[UUID],
        user_id: UUID,
        limit: int,
    ) -> "NLQResult":
        """Fuehrt NLQ-Suche durch."""
        nlq_service = await self._get_nlq_service(db)
        result = await nlq_service.process_query(
            query=query,
            company_id=company_id,
            user_id=user_id,
            limit=limit,
        )
        return result

    async def _get_nlq_service(self, db: AsyncSession) -> NLQService:
        """Lazy-load NLQ Service."""
        if self._nlq_service is None:
            self._nlq_service = await get_nlq_service(db)
        return self._nlq_service

    def _convert_nlq_to_documents(
        self, nlq_results: List[Dict]
    ) -> List[UnifiedDocumentResult]:
        """Konvertiert NLQ-Ergebnisse zu UnifiedDocumentResult."""
        documents = []
        for result in nlq_results:
            doc = UnifiedDocumentResult(
                document_id=result.get("id", ""),
                filename=result.get("filename", ""),
                original_filename=result.get("filename"),
                score=1.0,  # NLQ hat keine Score-Metrik
                document_type=result.get("document_type"),
                status=None,
                created_at=result.get("created_at"),
                mime_type=None,
                page_count=None,
                extracted_text_preview=None,
            )
            documents.append(doc)
        return documents

    # ========================================================================
    # Keyword Search Execution
    # ========================================================================

    async def _execute_keyword_search(
        self,
        db: AsyncSession,
        query: str,
        user_id: UUID,
        filters: Optional[SearchFilters],
        limit: int,
    ) -> "UnifiedSearchResponse":
        """Fuehrt Unified Search durch (Keyword/Hybrid)."""
        unified_search = self._get_unified_search()
        result = await unified_search.search(
            db=db,
            query=query,
            user_id=user_id,
            mode=UnifiedSearchMode.COMBINED,
            search_type=SearchType.HYBRID,  # Best results
            filters=filters,
            page=1,
            per_page=limit,
            sort_by=SortField.RELEVANCE,
            sort_order=SortOrder.DESC,
            expand_synonyms=True,
        )
        return result

    def _get_unified_search(self) -> UnifiedSearchService:
        """Lazy-load Unified Search Service."""
        if self._unified_search is None:
            self._unified_search = get_unified_search_service()
        return self._unified_search

    # ========================================================================
    # Entity Search
    # ========================================================================

    async def _search_entities(
        self,
        db: AsyncSession,
        query: str,
        company_id: Optional[UUID],
        limit: int,
    ) -> Tuple[List[SmartSearchEntity], int]:
        """Sucht Business Entities (Kunden/Lieferanten)."""
        entity_search = self._get_entity_search(db)

        # Smart-Suche ueber alle Felder
        results = await entity_search.smart_search(
            query=query,
            entity_type=None,  # Beide Typen durchsuchen
            company=None,  # Alle Companies (wird intern gefiltert)
            limit=limit,
        )

        entities = []
        for entity, confidence, match_type in results:
            entities.append(SmartSearchEntity(
                entity_id=str(entity.id),
                entity_type=entity.entity_type,
                name=entity.name,
                display_name=entity.display_name,
                match_type=match_type,
                confidence=confidence,
            ))

        return entities, len(entities)

    def _get_entity_search(self, db: AsyncSession) -> EntitySearchService:
        """Lazy-load Entity Search Service."""
        if self._entity_search is None:
            self._entity_search = get_entity_search_service(db)
        return self._entity_search

    # ========================================================================
    # Suggestions & Facets
    # ========================================================================

    def _generate_suggestions(
        self,
        query: str,
        detected_type: DetectedQueryType,
        has_results: bool,
    ) -> List[str]:
        """Generiert Query-Vorschlaege."""
        suggestions = []

        if not has_results:
            # Keine Ergebnisse: Alternative Vorschlaege
            if detected_type == DetectedQueryType.NLQ:
                suggestions.append("Versuchen Sie eine einfachere Formulierung")
                suggestions.append("Nutzen Sie Schlagwoerter statt ganzer Saetze")
            else:
                suggestions.append("Verwenden Sie weniger spezifische Suchbegriffe")
                suggestions.append("Probieren Sie verwandte Begriffe")
        else:
            # Ergebnisse vorhanden: Verfeinerungs-Vorschlaege
            if detected_type == DetectedQueryType.KEYWORD:
                suggestions.append("Verfeinern Sie mit Dokumenttyp-Filter")
                suggestions.append("Filtern Sie nach Datum oder Status")
            else:
                suggestions.append("Fragen Sie nach zusaetzlichen Details")
                suggestions.append("Kombinieren Sie mit Zeitangaben")

        return suggestions[:3]  # Max 3 Vorschlaege

    def _calculate_facets(
        self,
        documents: List[UnifiedDocumentResult],
        entities: List[SmartSearchEntity],
    ) -> SmartSearchFacets:
        """Berechnet Facetten/Aggregationen."""
        doc_types: Dict[str, int] = {}
        statuses: Dict[str, int] = {}
        entities_map: Dict[str, int] = {}

        for doc in documents:
            # Dokumenttypen
            if doc.document_type:
                doc_types[doc.document_type] = doc_types.get(doc.document_type, 0) + 1
            # Status
            if doc.status:
                statuses[doc.status] = statuses.get(doc.status, 0) + 1

        # Entities
        for entity in entities:
            entities_map[entity.entity_id] = entities_map.get(entity.entity_id, 0) + 1

        # Dummy date_ranges (koennte aus created_at berechnet werden)
        date_ranges = {
            "last_7_days": len([d for d in documents if d.created_at]),
            "last_30_days": len(documents),
        }

        return SmartSearchFacets(
            document_types=doc_types,
            statuses=statuses,
            date_ranges=date_ranges,
            entities=entities_map,
            total_count=len(documents),
        )

    # ========================================================================
    # Autocomplete
    # ========================================================================

    async def autocomplete(
        self,
        db: AsyncSession,
        query: str,
        limit: int = 10,
    ) -> List[str]:
        """
        Generiert Autocomplete-Vorschlaege.

        Args:
            db: Datenbank-Session
            query: Teilweise eingegebene Query
            limit: Maximale Anzahl Vorschlaege

        Returns:
            Liste von Autocomplete-Vorschlaegen
        """
        suggestions = []

        # Haeufige NLQ-Patterns
        nlq_templates = [
            "Zeige alle Rechnungen von",
            "Wie viel haben wir ausgegeben fuer",
            "Finde Dokumente vom",
            "Liste alle offenen Rechnungen",
            "Welche Lieferanten haben wir",
        ]

        query_lower = query.lower()

        # Pattern-Matching fuer Autocomplete
        for template in nlq_templates:
            if template.lower().startswith(query_lower) and len(query) >= 3:
                suggestions.append(template)

        # Koennte erweitert werden mit:
        # - Haeufige Queries aus History
        # - Entity-Namen Autocomplete
        # - Dokumenttyp-Namen

        return suggestions[:limit]


# ============================================================================
# Factory Function
# ============================================================================


_smart_search_service: Optional[SmartSearchService] = None


def get_smart_search_service() -> SmartSearchService:
    """Factory-Funktion fuer Dependency Injection."""
    global _smart_search_service
    if _smart_search_service is None:
        _smart_search_service = SmartSearchService()
    return _smart_search_service
