# -*- coding: utf-8 -*-
"""
Spotlight-Schnellsuche Service.

Kombiniert Autocomplete, Dokumentsuche und Entity-Matching
fuer die Cmd+K Spotlight-Suche im Frontend.
Ziel: <200ms Antwortzeit fuer schnelle Interaktion.
"""

from __future__ import annotations

import asyncio
import time
from datetime import datetime
from typing import List, Optional, Tuple
from uuid import UUID

import structlog
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.safe_errors import safe_error_log
from app.services.entity_search_service import (
    EntitySearchService,
    get_entity_search_service,
)
from app.services.smart_search_service import (
    SmartSearchService,
    get_smart_search_service,
)

logger = structlog.get_logger(__name__)


# ============================================================================
# Pydantic Response Schemas
# ============================================================================


class SpotlightSuggestion(BaseModel):
    """Autocomplete-/Navigations-Vorschlag."""
    text: str
    suggestion_type: str  # "entity", "document_type", "recent", "suggestion"
    confidence: Optional[float] = None
    entity_type: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class SpotlightDocument(BaseModel):
    """Dokument-Ergebnis fuer Spotlight."""
    document_id: str
    filename: str
    document_type: str
    status: str
    created_at: Optional[datetime] = None
    ocr_confidence: Optional[float] = None
    relevance_score: float
    highlight: Optional[str] = None
    text_preview: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class SpotlightEntity(BaseModel):
    """Gefundene Business Entity (Kunde/Lieferant)."""
    entity_id: str
    entity_name: str
    entity_type: str  # "customer" oder "supplier"
    customer_number: Optional[str] = None
    supplier_number: Optional[str] = None
    match_confidence: float

    model_config = ConfigDict(from_attributes=True)


class SpotlightInterpretation(BaseModel):
    """Interpretation der Suchanfrage."""
    original_query: str
    interpreted_as: str
    search_mode: str  # "nlq" oder "keyword"
    confidence: float

    model_config = ConfigDict(from_attributes=True)


class SpotlightResponse(BaseModel):
    """Vollstaendige Spotlight-Antwort."""
    suggestions: List[SpotlightSuggestion] = Field(default_factory=list)
    documents: List[SpotlightDocument] = Field(default_factory=list)
    entities: List[SpotlightEntity] = Field(default_factory=list)
    interpretation: Optional[SpotlightInterpretation] = None
    search_time_ms: float = 0.0
    total_documents: int = 0

    model_config = ConfigDict(from_attributes=True)


# ============================================================================
# Navigation Items (statisch, kein DB-Zugriff)
# ============================================================================

NAVIGATION_ITEMS: List[SpotlightSuggestion] = [
    SpotlightSuggestion(
        text="Dashboard",
        suggestion_type="navigation",
    ),
    SpotlightSuggestion(
        text="Dokumente",
        suggestion_type="navigation",
    ),
    SpotlightSuggestion(
        text="Rechnungen",
        suggestion_type="navigation",
    ),
    SpotlightSuggestion(
        text="Kunden & Lieferanten",
        suggestion_type="navigation",
    ),
    SpotlightSuggestion(
        text="OCR-Verarbeitung",
        suggestion_type="navigation",
    ),
    SpotlightSuggestion(
        text="Einstellungen",
        suggestion_type="navigation",
    ),
]


# ============================================================================
# Spotlight Service
# ============================================================================


class SpotlightService:
    """
    Schnellsuche fuer die Cmd+K Spotlight-Funktion.

    Kombiniert parallel:
    - Autocomplete-Vorschlaege
    - Dokumentsuche (via SmartSearch)
    - Entity-Matching (Kunden/Lieferanten)

    Ziel: <200ms Antwortzeit.
    """

    def __init__(self) -> None:
        """Initialisiert den Service."""
        self._smart_search: Optional[SmartSearchService] = None

    async def search(
        self,
        db: AsyncSession,
        query: str,
        user_id: UUID,
        company_id: Optional[UUID] = None,
        limit: int = 8,
    ) -> SpotlightResponse:
        """
        Fuehrt Spotlight-Schnellsuche durch.

        Bei kurzen Queries (<2 Zeichen) werden nur Navigations-Items
        zurueckgegeben. Bei laengeren Queries werden parallel
        Autocomplete, Dokument- und Entity-Suche durchgefuehrt.

        Args:
            db: Datenbank-Session
            query: Suchanfrage
            user_id: Benutzer-ID
            company_id: Optional Company-ID fuer Multi-Tenant
            limit: Maximale Anzahl Ergebnisse pro Kategorie

        Returns:
            SpotlightResponse mit kombinierten Ergebnissen
        """
        start_time = time.perf_counter()
        query_stripped = query.strip()

        # Kurze Queries: nur Navigation
        if len(query_stripped) < 2:
            nav_items = self._filter_navigation(query_stripped)
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            return SpotlightResponse(
                suggestions=nav_items,
                search_time_ms=elapsed_ms,
            )

        # Parallele Suche: Suggestions + Dokumente + Entities
        suggestions_task = self._get_suggestions(db, query_stripped, limit)
        documents_task = self._search_documents(
            db, query_stripped, user_id, company_id, limit,
        )
        entities_task = self._search_entities(
            db, query_stripped, company_id, min(limit, 5),
        )

        suggestions, doc_result, entities = await asyncio.gather(
            suggestions_task,
            documents_task,
            entities_task,
            return_exceptions=True,
        )

        # Fehlerbehandlung: partielle Ergebnisse bei Einzelfehlern
        if isinstance(suggestions, BaseException):
            logger.warning("spotlight_suggestions_failed", **safe_error_log(suggestions))
            suggestions = []

        if isinstance(doc_result, BaseException):
            logger.warning("spotlight_documents_failed", **safe_error_log(doc_result))
            doc_result = ([], 0, None)

        if isinstance(entities, BaseException):
            logger.warning("spotlight_entities_failed", **safe_error_log(entities))
            entities = []

        documents, total_documents, interpretation = doc_result

        elapsed_ms = (time.perf_counter() - start_time) * 1000

        logger.info(
            "spotlight_search_completed",
            query_length=len(query_stripped),
            suggestion_count=len(suggestions),
            document_count=len(documents),
            entity_count=len(entities),
            total_time_ms=round(elapsed_ms, 1),
        )

        return SpotlightResponse(
            suggestions=suggestions,
            documents=documents,
            entities=entities,
            interpretation=interpretation,
            search_time_ms=round(elapsed_ms, 1),
            total_documents=total_documents,
        )

    # ========================================================================
    # Navigation Filter
    # ========================================================================

    def _filter_navigation(self, query: str) -> List[SpotlightSuggestion]:
        """Filtert Navigations-Items nach Query."""
        if not query:
            return list(NAVIGATION_ITEMS)
        query_lower = query.lower()
        return [
            item for item in NAVIGATION_ITEMS
            if query_lower in item.text.lower()
        ]

    # ========================================================================
    # Autocomplete Suggestions
    # ========================================================================

    async def _get_suggestions(
        self,
        db: AsyncSession,
        query: str,
        limit: int,
    ) -> List[SpotlightSuggestion]:
        """Generiert Autocomplete-Vorschlaege."""
        smart_search = self._get_smart_search()

        # Autocomplete vom SmartSearchService
        raw_suggestions = await smart_search.autocomplete(
            db=db,
            query=query,
            limit=limit,
        )

        suggestions: List[SpotlightSuggestion] = []

        # Navigation filtern
        nav_matches = self._filter_navigation(query)
        for nav in nav_matches[:3]:
            suggestions.append(nav)

        # Autocomplete-Vorschlaege
        for text in raw_suggestions:
            suggestions.append(SpotlightSuggestion(
                text=text,
                suggestion_type="suggestion",
            ))

        return suggestions[:limit]

    # ========================================================================
    # Document Search
    # ========================================================================

    async def _search_documents(
        self,
        db: AsyncSession,
        query: str,
        user_id: UUID,
        company_id: Optional[UUID],
        limit: int,
    ) -> Tuple[List[SpotlightDocument], int, Optional[SpotlightInterpretation]]:
        """Sucht Dokumente via SmartSearch."""
        smart_search = self._get_smart_search()

        result = await smart_search.search(
            db=db,
            query=query,
            user_id=user_id,
            company_id=company_id,
            limit=limit,
            include_suggestions=False,
            include_facets=False,
        )

        documents: List[SpotlightDocument] = []
        for doc in result.documents[:limit]:
            documents.append(SpotlightDocument(
                document_id=doc.document_id,
                filename=doc.filename,
                document_type=doc.document_type or "unbekannt",
                status=doc.status or "unbekannt",
                created_at=None,  # created_at ist str im SmartSearch
                relevance_score=doc.score,
                text_preview=doc.extracted_text_preview,
            ))

        interpretation = SpotlightInterpretation(
            original_query=result.query,
            interpreted_as=result.interpretation.reasoning,
            search_mode=result.detected_type.value,
            confidence=result.interpretation.confidence,
        )

        return documents, result.total_documents, interpretation

    # ========================================================================
    # Entity Search
    # ========================================================================

    async def _search_entities(
        self,
        db: AsyncSession,
        query: str,
        company_id: Optional[UUID],
        limit: int,
    ) -> List[SpotlightEntity]:
        """Sucht Business Entities (Kunden/Lieferanten)."""
        entity_search = get_entity_search_service(db)

        results = await entity_search.smart_search(
            query=query,
            entity_type=None,
            company=None,
            limit=limit,
        )

        entities: List[SpotlightEntity] = []
        for entity, confidence, match_type in results:
            entities.append(SpotlightEntity(
                entity_id=str(entity.id),
                entity_name=entity.display_name or entity.name,
                entity_type=entity.entity_type.lower() if entity.entity_type else "unbekannt",
                customer_number=entity.primary_customer_number,
                supplier_number=entity.primary_supplier_number,
                match_confidence=confidence,
            ))

        return entities

    # ========================================================================
    # Lazy Loading
    # ========================================================================

    def _get_smart_search(self) -> SmartSearchService:
        """Lazy-load SmartSearchService."""
        if self._smart_search is None:
            self._smart_search = get_smart_search_service()
        return self._smart_search


# ============================================================================
# Factory Function
# ============================================================================

_spotlight_service: Optional[SpotlightService] = None


def get_spotlight_service() -> SpotlightService:
    """Factory-Funktion fuer Dependency Injection."""
    global _spotlight_service
    if _spotlight_service is None:
        _spotlight_service = SpotlightService()
    return _spotlight_service
