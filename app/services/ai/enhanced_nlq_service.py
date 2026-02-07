# -*- coding: utf-8 -*-
"""
Enhanced Natural Language Query Service.

Vision 2026 Q3: Erweiterte NLQ mit Power-User Features.

Erweitert den bestehenden NLQService um:
- SQL-Preview fuer Power-User
- Query-Suggestions basierend auf Kontext
- Interpretation-Erklaerung ("Ich verstehe Ihre Anfrage als...")
- Query-History fuer Verbesserungsvorschlaege
- Fuzzy-Matching fuer Entity-Namen
- Auto-Completion Vorschlaege

Feinpoliert und durchdacht - Deutsche Qualitaet.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from enum import Enum
from typing import Dict, List, Optional, Tuple, Union

import structlog

# Type aliases for JSON data
JSONValue = Union[str, int, float, bool, None, Dict[str, "JSONValue"], List["JSONValue"]]
JSONDict = Dict[str, JSONValue]
from prometheus_client import Counter, Histogram
from sqlalchemy import and_, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Document, BusinessEntity, InvoiceTracking
from app.services.ai.nlq_service import (
    NLQService,
    NLQResult,
    QueryIntent,
    EntityType,
    ExtractedEntity,
    get_nlq_service,
)

logger = structlog.get_logger(__name__)


# =============================================================================
# Prometheus Metriken
# =============================================================================

ENHANCED_NLQ_REQUESTS = Counter(
    "enhanced_nlq_requests_total",
    "Anzahl erweiterter NLQ-Anfragen",
    ["intent", "has_sql_preview"]
)

NLQ_SUGGESTION_USAGE = Counter(
    "nlq_suggestion_usage_total",
    "Nutzung von Query-Vorschlaegen",
    ["suggestion_type"]
)


# =============================================================================
# Datenstrukturen
# =============================================================================

@dataclass
class QueryInterpretation:
    """Erklaerung wie die Query interpretiert wurde."""
    original_query: str
    interpreted_as: str
    entities_found: List[JSONDict]
    filters_applied: List[str]
    confidence: float
    ambiguities: List[str] = field(default_factory=list)


@dataclass
class SQLPreview:
    """SQL-Vorschau fuer Power-User."""
    sql_query: str
    parameters: JSONDict
    estimated_rows: Optional[int]
    tables_used: List[str]
    warning: Optional[str] = None


@dataclass
class QuerySuggestion:
    """Vorgeschlagene Abfrage."""
    suggestion_text: str
    description: str
    category: str  # "refine", "related", "common"
    confidence: float


@dataclass
class EnhancedNLQResult:
    """Erweitertes NLQ-Ergebnis mit Power-User Features."""
    base_result: NLQResult
    interpretation: QueryInterpretation
    sql_preview: Optional[SQLPreview]
    suggestions: List[QuerySuggestion]
    related_queries: List[str]
    metadata: JSONDict = field(default_factory=dict)


# =============================================================================
# Query Templates und Beispiele
# =============================================================================

EXAMPLE_QUERIES: Dict[str, List[str]] = {
    "documents": [
        "Zeige alle Rechnungen von letztem Monat",
        "Finde Dokumente mit Betrag ueber 1000 EUR",
        "Liste offene Rechnungen von Mueller GmbH",
    ],
    "aggregation": [
        "Wie hoch ist die Summe aller offenen Rechnungen?",
        "Was ist der Durchschnittsbetrag pro Rechnung?",
        "Wie viele Dokumente wurden diese Woche verarbeitet?",
    ],
    "comparison": [
        "Vergleiche Umsaetze Januar mit Februar",
        "Zeige Unterschied letzte 30 Tage vs. vorherige 30 Tage",
    ],
    "trend": [
        "Wie entwickeln sich die monatlichen Ausgaben?",
        "Zeige Trend offener Posten ueber 6 Monate",
    ],
}

COMMON_QUERY_PATTERNS: List[Tuple[str, str, str]] = [
    # (Pattern, Beschreibung, Kategorie)
    ("offene rechnungen", "Zeigt alle unbezahlten Rechnungen", "finance"),
    ("rechnungen von {firma}", "Rechnungen eines bestimmten Lieferanten", "documents"),
    ("umsatz {zeitraum}", "Umsatzuebersicht fuer einen Zeitraum", "aggregation"),
    ("dokumente heute", "Heute verarbeitete Dokumente", "documents"),
    ("hoechste rechnung", "Rechnung mit dem hoechsten Betrag", "aggregation"),
    ("ueberfaellige rechnungen", "Alle ueberfaelligen Rechnungen", "finance"),
    ("anzahl {dokumenttyp}", "Anzahl eines bestimmten Dokumenttyps", "aggregation"),
]


class EnhancedNLQService:
    """
    Erweiterter NLQ-Service mit Power-User Features.

    Nutzt den bestehenden NLQService und reichert
    die Ergebnisse mit zusaetzlichen Informationen an.
    """

    def __init__(self, db: AsyncSession) -> None:
        """Initialisiert den Service."""
        self.db = db
        self._base_service: Optional[NLQService] = None
        self._query_history: List[JSONDict] = []
        self._max_history = 100

    async def _get_base_service(self) -> NLQService:
        """Lazy-Loading des Basis-Services."""
        if self._base_service is None:
            self._base_service = await get_nlq_service(self.db)
        return self._base_service

    async def process_query(
        self,
        query: str,
        company_id: Optional[uuid.UUID] = None,
        user_id: Optional[uuid.UUID] = None,
        include_sql_preview: bool = False,
        include_suggestions: bool = True,
        limit: int = 50,
    ) -> EnhancedNLQResult:
        """
        Verarbeitet eine Abfrage mit erweiterten Features.

        Args:
            query: Die Abfrage in natuerlicher Sprache
            company_id: Optional Company-ID
            user_id: Optional User-ID
            include_sql_preview: SQL-Preview generieren
            include_suggestions: Vorschlaege generieren
            limit: Maximale Anzahl Ergebnisse

        Returns:
            EnhancedNLQResult mit erweiterten Informationen
        """
        import time
        start_time = time.perf_counter()

        # Basis-Query verarbeiten
        base_service = await self._get_base_service()
        base_result = await base_service.process_query(
            query=query,
            company_id=company_id,
            user_id=user_id,
            limit=limit,
        )

        # Interpretation erstellen
        interpretation = self._create_interpretation(
            query, base_result
        )

        # SQL-Preview wenn gewuenscht
        sql_preview: Optional[SQLPreview] = None
        if include_sql_preview:
            sql_preview = await self._generate_sql_preview(
                query, base_result, company_id
            )

        # Suggestions generieren
        suggestions: List[QuerySuggestion] = []
        if include_suggestions:
            suggestions = await self._generate_suggestions(
                query, base_result, company_id
            )

        # Related Queries
        related = self._get_related_queries(query, base_result.intent)

        # Query in History speichern
        self._add_to_history(query, base_result, company_id, user_id)

        # Metriken
        ENHANCED_NLQ_REQUESTS.labels(
            intent=base_result.intent.value,
            has_sql_preview=str(include_sql_preview).lower(),
        ).inc()

        processing_time = int((time.perf_counter() - start_time) * 1000)

        return EnhancedNLQResult(
            base_result=base_result,
            interpretation=interpretation,
            sql_preview=sql_preview,
            suggestions=suggestions,
            related_queries=related,
            metadata={
                "processing_time_ms": processing_time,
                "include_sql_preview": include_sql_preview,
                "include_suggestions": include_suggestions,
            },
        )

    async def get_autocomplete_suggestions(
        self,
        partial_query: str,
        company_id: Optional[uuid.UUID] = None,
        limit: int = 10,
    ) -> List[QuerySuggestion]:
        """
        Gibt Auto-Complete Vorschlaege fuer eine teilweise Eingabe.

        Args:
            partial_query: Teilweise eingegebene Abfrage
            company_id: Optional Company-ID
            limit: Maximale Anzahl Vorschlaege

        Returns:
            Liste von QuerySuggestion
        """
        suggestions: List[QuerySuggestion] = []
        partial_lower = partial_query.lower().strip()

        if len(partial_lower) < 2:
            return suggestions

        # 1. Aus History matchen
        for history_entry in self._query_history[-50:]:
            if partial_lower in history_entry["query"].lower():
                suggestions.append(QuerySuggestion(
                    suggestion_text=history_entry["query"],
                    description="Basierend auf frueherer Suche",
                    category="history",
                    confidence=0.8,
                ))

        # 2. Common Patterns matchen
        for pattern, desc, cat in COMMON_QUERY_PATTERNS:
            if partial_lower in pattern:
                suggestions.append(QuerySuggestion(
                    suggestion_text=pattern.replace("{firma}", "Musterfirma")
                                         .replace("{zeitraum}", "diesen Monat")
                                         .replace("{dokumenttyp}", "Rechnungen"),
                    description=desc,
                    category=cat,
                    confidence=0.7,
                ))

        # 3. Entity-Namen matchen (Firmennamen)
        if company_id:
            entity_matches = await self._match_entity_names(partial_query, company_id)
            for name in entity_matches[:5]:
                suggestions.append(QuerySuggestion(
                    suggestion_text=f"Rechnungen von {name}",
                    description=f"Dokumente von {name}",
                    category="entity",
                    confidence=0.9,
                ))

        # Deduplizieren und limitieren
        seen = set()
        unique_suggestions = []
        for s in suggestions:
            if s.suggestion_text not in seen:
                seen.add(s.suggestion_text)
                unique_suggestions.append(s)

        return sorted(
            unique_suggestions,
            key=lambda x: x.confidence,
            reverse=True,
        )[:limit]

    async def get_query_examples(
        self,
        category: Optional[str] = None,
    ) -> Dict[str, List[str]]:
        """
        Gibt Beispiel-Abfragen zurueck.

        Args:
            category: Optional Kategorie-Filter

        Returns:
            Dict mit Kategorien und Beispielen
        """
        if category and category in EXAMPLE_QUERIES:
            return {category: EXAMPLE_QUERIES[category]}
        return EXAMPLE_QUERIES

    # =========================================================================
    # PRIVATE METHODS
    # =========================================================================

    def _create_interpretation(
        self,
        query: str,
        result: NLQResult,
    ) -> QueryInterpretation:
        """Erstellt eine Interpretation der Abfrage."""
        # Interpretation zusammenbauen
        parts: List[str] = []

        # Intent beschreiben
        intent_descriptions = {
            QueryIntent.SEARCH: "Suche nach Dokumenten",
            QueryIntent.AGGREGATE: "Berechnung eines Aggregats",
            QueryIntent.COMPARE: "Vergleich zwischen Zeitraeumen",
            QueryIntent.TREND: "Trend-Analyse",
            QueryIntent.CHAT: "Frage zu Dokumenteninhalten",
            QueryIntent.LIST: "Auflistung von Dokumenten",
            QueryIntent.UNKNOWN: "Unklare Anfrage",
        }
        parts.append(intent_descriptions.get(result.intent, "Verarbeitung"))

        # Entities beschreiben
        entity_details: List[Dict[str, Any]] = []
        filters: List[str] = []

        for entity in result.extracted_entities:
            entity_info = {
                "type": entity.entity_type.value,
                "value": str(entity.value),
                "confidence": entity.confidence,
            }
            entity_details.append(entity_info)

            # Filter-Beschreibung
            if entity.entity_type == EntityType.DATE_RANGE:
                value = entity.value
                if isinstance(value, dict):
                    filters.append(
                        f"Zeitraum: {value.get('start')} bis {value.get('end')}"
                    )
            elif entity.entity_type == EntityType.AMOUNT:
                if isinstance(entity.value, dict):
                    op = "mindestens" if entity.value.get("operator") == "gte" else "maximal"
                    filters.append(f"Betrag: {op} {entity.value.get('amount')} EUR")
                else:
                    filters.append(f"Betrag: {entity.value} EUR")
            elif entity.entity_type == EntityType.COMPANY:
                if isinstance(entity.value, dict):
                    filters.append(f"Firma: {entity.value.get('name', 'Unbekannt')}")
            elif entity.entity_type == EntityType.DOCUMENT_TYPE:
                filters.append(f"Dokumenttyp: {entity.original_text}")
            elif entity.entity_type == EntityType.STATUS:
                filters.append(f"Status: {entity.original_text}")

        # Interpreted As generieren
        if filters:
            interpreted_as = f"{parts[0]} mit Filtern: {', '.join(filters)}"
        else:
            interpreted_as = parts[0]

        # Ambiguitaeten erkennen
        ambiguities: List[str] = []

        # Niedrige Confidence bei Entities
        low_conf_entities = [
            e for e in result.extracted_entities
            if e.confidence < 0.7
        ]
        if low_conf_entities:
            ambiguities.append(
                f"{len(low_conf_entities)} Elemente mit niedriger Erkennungssicherheit"
            )

        # Keine Zeitangabe bei Aggregation
        if result.intent == QueryIntent.AGGREGATE:
            has_date = any(
                e.entity_type in (EntityType.DATE, EntityType.DATE_RANGE)
                for e in result.extracted_entities
            )
            if not has_date:
                ambiguities.append("Kein Zeitraum angegeben - alle Daten werden beruecksichtigt")

        return QueryInterpretation(
            original_query=query,
            interpreted_as=interpreted_as,
            entities_found=entity_details,
            filters_applied=filters,
            confidence=result.confidence,
            ambiguities=ambiguities,
        )

    async def _generate_sql_preview(
        self,
        query: str,
        result: NLQResult,
        company_id: Optional[uuid.UUID],
    ) -> SQLPreview:
        """Generiert eine SQL-Vorschau fuer Power-User."""
        # Basis-SQL je nach Intent
        tables: List[str] = []
        params: Dict[str, Any] = {}
        where_clauses: List[str] = []

        if result.intent in (QueryIntent.SEARCH, QueryIntent.LIST):
            base_sql = "SELECT d.* FROM documents d"
            tables.append("documents")

            # Entity-Join wenn noetig
            has_company = any(
                e.entity_type == EntityType.COMPANY
                for e in result.extracted_entities
            )
            if has_company:
                base_sql += " LEFT JOIN business_entities be ON d.business_entity_id = be.id"
                tables.append("business_entities")

        elif result.intent == QueryIntent.AGGREGATE:
            base_sql = "SELECT COUNT(*), SUM(total_amount) FROM invoice_tracking"
            tables.append("invoice_tracking")

        else:
            base_sql = "SELECT * FROM documents"
            tables.append("documents")

        # Filter-Clauses bauen
        for i, entity in enumerate(result.extracted_entities):
            param_name = f"param_{i}"

            if entity.entity_type == EntityType.DATE_RANGE:
                value = entity.value
                if isinstance(value, dict):
                    where_clauses.append(f"created_at BETWEEN :start_{i} AND :end_{i}")
                    params[f"start_{i}"] = value.get("start")
                    params[f"end_{i}"] = value.get("end")

            elif entity.entity_type == EntityType.DOCUMENT_TYPE:
                where_clauses.append(f"document_type IN :{param_name}")
                params[param_name] = entity.value

            elif entity.entity_type == EntityType.COMPANY:
                if isinstance(entity.value, dict) and "id" in entity.value:
                    where_clauses.append(f"business_entity_id = :{param_name}")
                    params[param_name] = entity.value["id"]

            elif entity.entity_type == EntityType.AMOUNT:
                if isinstance(entity.value, dict):
                    op = ">=" if entity.value.get("operator") == "gte" else "<="
                    where_clauses.append(f"(extracted_data->>'total_gross')::numeric {op} :{param_name}")
                    params[param_name] = entity.value.get("amount")

        # SQL zusammenbauen
        if company_id:
            where_clauses.append("company_id = :company_id")
            params["company_id"] = company_id

        if where_clauses:
            sql = f"{base_sql} WHERE {' AND '.join(where_clauses)}"
        else:
            sql = base_sql

        # Row-Estimate (vereinfacht)
        estimated_rows = result.result_count if result.result_count else None

        # Warning wenn keine Filter
        warning = None
        if not where_clauses:
            warning = "Keine Filter angewendet - Abfrage kann viele Ergebnisse liefern"

        return SQLPreview(
            sql_query=sql,
            parameters=params,
            estimated_rows=estimated_rows,
            tables_used=tables,
            warning=warning,
        )

    async def _generate_suggestions(
        self,
        query: str,
        result: NLQResult,
        company_id: Optional[uuid.UUID],
    ) -> List[QuerySuggestion]:
        """Generiert Vorschlaege zur Verfeinerung der Abfrage."""
        suggestions: List[QuerySuggestion] = []

        # 1. Zeitraum-Verfeinerung wenn kein Zeitraum
        has_date = any(
            e.entity_type in (EntityType.DATE, EntityType.DATE_RANGE)
            for e in result.extracted_entities
        )
        if not has_date:
            suggestions.append(QuerySuggestion(
                suggestion_text=f"{query} letzte 30 Tage",
                description="Auf letzte 30 Tage beschraenken",
                category="refine",
                confidence=0.8,
            ))
            suggestions.append(QuerySuggestion(
                suggestion_text=f"{query} diesen Monat",
                description="Auf aktuellen Monat beschraenken",
                category="refine",
                confidence=0.75,
            ))

        # 2. Sortierung hinzufuegen
        if result.intent == QueryIntent.SEARCH and result.result_count and result.result_count > 5:
            suggestions.append(QuerySuggestion(
                suggestion_text=f"{query} sortiert nach Betrag",
                description="Nach Betrag sortieren",
                category="refine",
                confidence=0.7,
            ))

        # 3. Verwandte Dokumenttypen
        doc_types = [
            e for e in result.extracted_entities
            if e.entity_type == EntityType.DOCUMENT_TYPE
        ]
        if doc_types:
            # Andere Dokumenttypen vorschlagen
            current_type = doc_types[0].original_text
            related_types = {
                "rechnungen": ["Lieferscheine", "Angebote"],
                "lieferscheine": ["Rechnungen", "Auftraege"],
                "angebote": ["Auftraege", "Rechnungen"],
            }
            for related in related_types.get(current_type, []):
                suggestions.append(QuerySuggestion(
                    suggestion_text=query.replace(current_type, related.lower()),
                    description=f"Stattdessen {related} suchen",
                    category="related",
                    confidence=0.6,
                ))

        # 4. Aggregation vorschlagen bei Suche
        if result.intent == QueryIntent.SEARCH and result.result_count and result.result_count > 10:
            suggestions.append(QuerySuggestion(
                suggestion_text=f"Summe der {query}",
                description="Gesamtsumme berechnen",
                category="related",
                confidence=0.65,
            ))
            suggestions.append(QuerySuggestion(
                suggestion_text=f"Anzahl {query}",
                description="Anzahl zaehlen",
                category="related",
                confidence=0.65,
            ))

        return suggestions[:5]  # Maximal 5 Vorschlaege

    def _get_related_queries(
        self,
        query: str,
        intent: QueryIntent,
    ) -> List[str]:
        """Gibt verwandte haeufige Abfragen zurueck."""
        related: List[str] = []

        # Basierend auf Intent
        category_map = {
            QueryIntent.SEARCH: "documents",
            QueryIntent.LIST: "documents",
            QueryIntent.AGGREGATE: "aggregation",
            QueryIntent.COMPARE: "comparison",
            QueryIntent.TREND: "trend",
        }

        category = category_map.get(intent)
        if category and category in EXAMPLE_QUERIES:
            # Beispiele aus der Kategorie
            related.extend(EXAMPLE_QUERIES[category][:3])

        return related

    async def _match_entity_names(
        self,
        partial: str,
        company_id: uuid.UUID,
    ) -> List[str]:
        """Findet Entity-Namen die zum Partial matchen."""
        stmt = select(BusinessEntity.name).where(
            and_(
                BusinessEntity.company_id == company_id,
                BusinessEntity.name.ilike(f"%{partial}%"),
            )
        ).limit(10)

        result = await self.db.execute(stmt)
        return [row[0] for row in result.all()]

    def _add_to_history(
        self,
        query: str,
        result: NLQResult,
        company_id: Optional[uuid.UUID],
        user_id: Optional[uuid.UUID],
    ) -> None:
        """Fuegt eine Abfrage zur History hinzu."""
        self._query_history.append({
            "query": query,
            "intent": result.intent.value,
            "success": result.success,
            "result_count": result.result_count,
            "company_id": str(company_id) if company_id else None,
            "user_id": str(user_id) if user_id else None,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

        # History begrenzen
        if len(self._query_history) > self._max_history:
            self._query_history = self._query_history[-self._max_history:]


# =============================================================================
# Factory
# =============================================================================

async def get_enhanced_nlq_service(db: AsyncSession) -> EnhancedNLQService:
    """Factory fuer EnhancedNLQService."""
    return EnhancedNLQService(db)
