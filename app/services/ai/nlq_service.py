# -*- coding: utf-8 -*-
"""
NLQService - Natural Language Query Service.

Ermoeglicht natuerlichsprachliche Abfragen auf Dokumenten und Geschaeftsdaten:
- "Zeige alle Rechnungen von Mueller GmbH ueber 1000 EUR"
- "Wie viel haben wir letzten Monat fuer Bueroartikel ausgegeben?"
- "Welche Rechnungen sind seit mehr als 30 Tagen offen?"
- "Finde alle Dokumente mit dem Stichwort 'Wartung'"

Features:
- Intent-Erkennung (Query, Aggregation, Comparison)
- Entity-Extraction (Firmenname, Betrag, Datum, Dokumenttyp)
- SQL-Generierung aus natuerlicher Sprache
- RAG-Integration fuer Dokumenten-Chat
- Confidence-basierte Antworten

Phase 2.2 der Feature-Roadmap (Januar 2026)
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, date, timedelta
from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple, Union

import structlog
from sqlalchemy import select, and_, or_, func, case, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.datetime_utils import utc_now
from app.services.extraction.patterns.date_patterns import parse_german_date
from app.db.models import Document, BusinessEntity, InvoiceTracking
from app.core.safe_errors import safe_error_detail,  safe_error_log

# NOTE: Folder model does not exist - folder-based queries disabled
Folder = None

logger = structlog.get_logger(__name__)


# ============================================================================
# Enums and Constants
# ============================================================================


class QueryIntent(str, Enum):
    """Erkannter Intent der Abfrage."""

    SEARCH = "search"  # Dokumente suchen
    AGGREGATE = "aggregate"  # Summe, Durchschnitt, Anzahl
    COMPARE = "compare"  # Vergleich zwischen Zeitraeumen/Entities
    TREND = "trend"  # Trend-Analyse
    CHAT = "chat"  # Freie Frage ueber Dokumente (RAG)
    LIST = "list"  # Auflistung
    UNKNOWN = "unknown"


class EntityType(str, Enum):
    """Erkannte Entity-Typen in der Abfrage."""

    COMPANY = "company"  # Firmenname
    AMOUNT = "amount"  # Geldbetrag
    DATE = "date"  # Datum
    DATE_RANGE = "date_range"  # Zeitraum
    DOCUMENT_TYPE = "document_type"  # Dokumenttyp
    STATUS = "status"  # Status (offen, bezahlt, etc.)
    KEYWORD = "keyword"  # Freitext-Stichwort


@dataclass
class ExtractedEntity:
    """Aus der Abfrage extrahierte Entity."""

    entity_type: EntityType
    value: Union[str, int, float, bool, datetime, date]
    original_text: str
    confidence: float = 0.9


@dataclass
class NLQResult:
    """Ergebnis einer NLQ-Abfrage."""

    success: bool
    intent: QueryIntent
    extracted_entities: List[ExtractedEntity]
    generated_sql: Optional[str] = None
    results: Optional[List[Dict[str, Any]]] = None
    result_count: int = 0
    aggregation_value: Optional[Union[Decimal, int, float]] = None
    natural_response: str = ""
    confidence: float = 0.0
    processing_time_ms: int = 0
    error_message: Optional[str] = None


# ============================================================================
# German Language Patterns
# ============================================================================


# Deutsche Zahlwoerter
GERMAN_NUMBER_WORDS = {
    "null": 0, "eins": 1, "zwei": 2, "drei": 3, "vier": 4,
    "fuenf": 5, "sechs": 6, "sieben": 7, "acht": 8, "neun": 9,
    "zehn": 10, "elf": 11, "zwoelf": 12, "dreizehn": 13,
    "vierzehn": 14, "fuenfzehn": 15, "zwanzig": 20, "dreissig": 30,
    "vierzig": 40, "fuenfzig": 50, "sechzig": 60, "siebzig": 70,
    "achtzig": 80, "neunzig": 90, "hundert": 100, "tausend": 1000,
}

# Zeitraum-Keywords
TIME_KEYWORDS = {
    "heute": lambda: (date.today(), date.today()),
    "gestern": lambda: (date.today() - timedelta(days=1), date.today() - timedelta(days=1)),
    "diese woche": lambda: (date.today() - timedelta(days=date.today().weekday()), date.today()),
    "letzte woche": lambda: (
        date.today() - timedelta(days=date.today().weekday() + 7),
        date.today() - timedelta(days=date.today().weekday() + 1)
    ),
    "dieser monat": lambda: (date.today().replace(day=1), date.today()),
    "letzter monat": lambda: (
        (date.today().replace(day=1) - timedelta(days=1)).replace(day=1),
        date.today().replace(day=1) - timedelta(days=1)
    ),
    "dieses jahr": lambda: (date.today().replace(month=1, day=1), date.today()),
    "letztes jahr": lambda: (
        date.today().replace(year=date.today().year - 1, month=1, day=1),
        date.today().replace(year=date.today().year - 1, month=12, day=31)
    ),
    "letzte 7 tage": lambda: (date.today() - timedelta(days=7), date.today()),
    "letzte 30 tage": lambda: (date.today() - timedelta(days=30), date.today()),
    "letzte 90 tage": lambda: (date.today() - timedelta(days=90), date.today()),
}

# Dokumenttyp-Keywords
DOCUMENT_TYPE_KEYWORDS = {
    "rechnung": ["invoice", "rechnung"],
    "rechnungen": ["invoice", "rechnung"],
    "angebot": ["offer", "angebot", "quote"],
    "angebote": ["offer", "angebot", "quote"],
    "lieferschein": ["delivery_note", "lieferschein"],
    "lieferscheine": ["delivery_note", "lieferschein"],
    "vertrag": ["contract", "vertrag"],
    "vertraege": ["contract", "vertrag"],
    "mahnung": ["dunning", "mahnung", "reminder"],
    "mahnungen": ["dunning", "mahnung", "reminder"],
    "gutschrift": ["credit_note", "gutschrift"],
    "gutschriften": ["credit_note", "gutschrift"],
}

# Status-Keywords
STATUS_KEYWORDS = {
    "offen": ["pending", "open", "unpaid"],
    "offene": ["pending", "open", "unpaid"],
    "bezahlt": ["paid", "completed"],
    "bezahlte": ["paid", "completed"],
    "ueberfaellig": ["overdue"],
    "ueberfaellige": ["overdue"],
    "teil": ["partial"],
    "storniert": ["cancelled", "canceled"],
}

# Aggregations-Keywords
AGGREGATION_KEYWORDS = {
    "summe": "sum",
    "gesamt": "sum",
    "insgesamt": "sum",
    "total": "sum",
    "durchschnitt": "avg",
    "mittel": "avg",
    "anzahl": "count",
    "wie viele": "count",
    "wieviele": "count",
    "maximum": "max",
    "hoechste": "max",
    "minimum": "min",
    "niedrigste": "min",
}


# ============================================================================
# NLQ Service
# ============================================================================


class NLQService:
    """Service fuer Natural Language Queries.

    Verarbeitet natuerlichsprachliche Abfragen und generiert
    entsprechende Datenbankabfragen.

    Settings werden aus app.core.config.settings geladen.
    """

    def __init__(self, db: AsyncSession):
        """Initialisiert den Service.

        Args:
            db: Async Database Session
        """
        self.db = db
        self._load_config()

    def _load_config(self) -> None:
        """Laedt Konfiguration aus Settings."""
        try:
            from app.core.config import settings

            self.enabled = settings.AUTONOMY_NLQ_ENABLED
            self.max_results = settings.AUTONOMY_NLQ_MAX_RESULTS
        except Exception as e:
            logger.debug(
                "nlq_settings_load_failed",
                error_type=type(e).__name__,
            )
            # Fallback-Defaults
            self.enabled = True
            self.max_results = 100

    async def process_query(
        self,
        query: str,
        company_id: Optional[uuid.UUID] = None,
        user_id: Optional[uuid.UUID] = None,
        limit: int = 50,
    ) -> NLQResult:
        """Verarbeitet eine natuerlichsprachliche Abfrage.

        Args:
            query: Die Abfrage in natuerlicher Sprache
            company_id: Optional Company-ID fuer Multi-Tenant
            user_id: Optional User-ID fuer Berechtigungspruefung
            limit: Maximale Anzahl Ergebnisse

        Returns:
            NLQResult mit Ergebnissen
        """
        import time
        start_time = time.time()

        # Check ob NLQ aktiviert ist
        if not self.enabled:
            return NLQResult(
                success=False,
                intent=QueryIntent.UNKNOWN,
                extracted_entities=[],
                natural_response="Natural Language Queries sind derzeit deaktiviert.",
                confidence=0.0,
                processing_time_ms=0,
            )

        # Limit auf konfiguriertes Maximum begrenzen
        effective_limit = min(limit, self.max_results)

        try:
            # 1. Query normalisieren
            normalized_query = self._normalize_query(query)

            # 2. Intent erkennen
            intent = self._detect_intent(normalized_query)

            # 3. Entities extrahieren
            entities = await self._extract_entities(normalized_query, company_id)

            # 4. Je nach Intent verarbeiten
            if intent == QueryIntent.SEARCH or intent == QueryIntent.LIST:
                result = await self._process_search_query(
                    normalized_query, entities, company_id, effective_limit
                )
            elif intent == QueryIntent.AGGREGATE:
                result = await self._process_aggregate_query(
                    normalized_query, entities, company_id
                )
            elif intent == QueryIntent.COMPARE:
                result = await self._process_compare_query(
                    normalized_query, entities, company_id
                )
            elif intent == QueryIntent.CHAT:
                result = await self._process_chat_query(
                    normalized_query, entities, company_id
                )
            else:
                result = NLQResult(
                    success=False,
                    intent=intent,
                    extracted_entities=entities,
                    natural_response="Entschuldigung, ich konnte Ihre Anfrage nicht verstehen. "
                                   "Bitte formulieren Sie Ihre Frage anders.",
                    confidence=0.3,
                )

            # Verarbeitungszeit hinzufuegen
            result.processing_time_ms = int((time.time() - start_time) * 1000)

            logger.info(
                "nlq_query_processed",
                query_length=len(query),
                intent=intent.value,
                entity_count=len(entities),
                result_count=result.result_count,
                processing_time_ms=result.processing_time_ms,
            )

            return result

        except Exception as e:
            logger.error(
                "nlq_query_error",
                query=query[:100],
                **safe_error_log(e),
            )
            return NLQResult(
                success=False,
                intent=QueryIntent.UNKNOWN,
                extracted_entities=[],
                natural_response=safe_error_detail(e, "NLQ"),
                confidence=0.0,
                processing_time_ms=int((time.time() - start_time) * 1000),
                error_message=safe_error_detail(e, "NLQ"),
            )

    # ========================================================================
    # Query Normalization
    # ========================================================================

    def _normalize_query(self, query: str) -> str:
        """Normalisiert die Abfrage fuer bessere Verarbeitung."""
        # Kleinschreibung
        normalized = query.lower().strip()

        # Umlaute normalisieren (fuer Matching)
        umlaut_map = {
            "ae": "ae", "ä": "ae",
            "oe": "oe", "ö": "oe",
            "ue": "ue", "ü": "ue",
            "ss": "ss", "ß": "ss",
        }
        for search, replace in umlaut_map.items():
            normalized = normalized.replace(search, replace)

        # Mehrfache Leerzeichen entfernen
        normalized = re.sub(r'\s+', ' ', normalized)

        return normalized

    # ========================================================================
    # Intent Detection
    # ========================================================================

    def _detect_intent(self, query: str) -> QueryIntent:
        """Erkennt den Intent der Abfrage."""

        # Aggregation-Keywords
        for keyword in AGGREGATION_KEYWORDS:
            if keyword in query:
                return QueryIntent.AGGREGATE

        # Vergleichs-Keywords
        compare_keywords = ["vergleich", "unterschied", "mehr als", "weniger als", "gegenueber"]
        for keyword in compare_keywords:
            if keyword in query:
                return QueryIntent.COMPARE

        # Such-Keywords
        search_keywords = ["zeige", "finde", "suche", "liste", "welche", "wo ist", "wo sind"]
        for keyword in search_keywords:
            if keyword in query:
                return QueryIntent.SEARCH

        # Frage-Keywords (Chat/RAG)
        question_keywords = ["warum", "wie", "erklaere", "was bedeutet", "wer"]
        for keyword in question_keywords:
            if keyword in query:
                return QueryIntent.CHAT

        # Liste-Keywords
        list_keywords = ["alle", "auflistung", "uebersicht"]
        for keyword in list_keywords:
            if keyword in query:
                return QueryIntent.LIST

        # Default: Suche
        return QueryIntent.SEARCH

    # ========================================================================
    # Entity Extraction
    # ========================================================================

    async def _extract_entities(
        self,
        query: str,
        company_id: Optional[uuid.UUID],
    ) -> List[ExtractedEntity]:
        """Extrahiert Entities aus der Abfrage."""
        entities: List[ExtractedEntity] = []

        # 1. Betraege extrahieren
        amount_entities = self._extract_amounts(query)
        entities.extend(amount_entities)

        # 2. Zeitraeume extrahieren
        time_entities = self._extract_time_ranges(query)
        entities.extend(time_entities)

        # 3. Dokumenttypen extrahieren
        doc_type_entities = self._extract_document_types(query)
        entities.extend(doc_type_entities)

        # 4. Status extrahieren
        status_entities = self._extract_status(query)
        entities.extend(status_entities)

        # 5. Firmennamen extrahieren (mit DB-Lookup)
        company_entities = await self._extract_company_names(query, company_id)
        entities.extend(company_entities)

        return entities

    def _extract_amounts(self, query: str) -> List[ExtractedEntity]:
        """Extrahiert Geldbetraege aus der Abfrage."""
        entities = []

        # Pattern: "1000 EUR", "1.000,50 EUR", "1000€"
        amount_pattern = r'(\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{2})?)\s*(?:eur|euro|€)'
        matches = re.findall(amount_pattern, query, re.IGNORECASE)

        for match in matches:
            # Deutsches Format zu Decimal konvertieren
            amount_str = match.replace('.', '').replace(',', '.')
            try:
                amount = Decimal(amount_str)
                entities.append(ExtractedEntity(
                    entity_type=EntityType.AMOUNT,
                    value=amount,
                    original_text=match,
                    confidence=0.95,
                ))
            except (ValueError, InvalidOperation) as e:
                logger.debug(
                    "nlq_amount_parsing_skipped",
                    amount_str=amount_str[:20],
                    error_type=type(e).__name__,
                )

        # Pattern: "ueber X", "mehr als X", "unter X"
        comparison_pattern = r'(ueber|mehr als|mindestens|unter|weniger als|maximal|bis)\s+(\d+)'
        comp_matches = re.findall(comparison_pattern, query, re.IGNORECASE)

        for operator, value in comp_matches:
            try:
                amount = Decimal(value)
                op = "gte" if operator in ["ueber", "mehr als", "mindestens"] else "lte"
                entities.append(ExtractedEntity(
                    entity_type=EntityType.AMOUNT,
                    value={"amount": amount, "operator": op},
                    original_text=f"{operator} {value}",
                    confidence=0.90,
                ))
            except (ValueError, InvalidOperation) as e:
                logger.debug(
                    "nlq_comparison_amount_skipped",
                    operator=operator,
                    value=value,
                    error_type=type(e).__name__,
                )

        return entities

    def _extract_time_ranges(self, query: str) -> List[ExtractedEntity]:
        """Extrahiert Zeitraeume aus der Abfrage."""
        entities = []

        # Vordefinierte Zeitraeume
        for keyword, date_func in TIME_KEYWORDS.items():
            if keyword in query:
                start_date, end_date = date_func()
                entities.append(ExtractedEntity(
                    entity_type=EntityType.DATE_RANGE,
                    value={"start": start_date, "end": end_date},
                    original_text=keyword,
                    confidence=0.95,
                ))
                break  # Nur ersten Match nehmen

        # Explizite Daten: "seit 01.01.2025"
        date_pattern = r'(?:seit|ab|vom|bis|am)\s+(\d{1,2})[./](\d{1,2})[./](\d{2,4})'
        date_matches = re.findall(date_pattern, query)

        for day, month, year in date_matches:
            try:
                year_int = int(year)
                if year_int < 100:
                    year_int += 2000
                parsed_date = date(year_int, int(month), int(day))
                entities.append(ExtractedEntity(
                    entity_type=EntityType.DATE,
                    value=parsed_date,
                    original_text=f"{day}.{month}.{year}",
                    confidence=0.90,
                ))
            except (ValueError, TypeError) as e:
                logger.debug(
                    "nlq_date_parsing_skipped",
                    date_str=f"{day}.{month}.{year}",
                    error_type=type(e).__name__,
                )

        # "Letzten X Tage/Wochen/Monate"
        period_pattern = r'letzte[n]?\s+(\d+)\s+(tag|tage|woche|wochen|monat|monate)'
        period_matches = re.findall(period_pattern, query)

        for count, unit in period_matches:
            count_int = int(count)
            if "tag" in unit:
                delta = timedelta(days=count_int)
            elif "woche" in unit:
                delta = timedelta(weeks=count_int)
            elif "monat" in unit:
                delta = timedelta(days=count_int * 30)  # Approximation
            else:
                continue

            entities.append(ExtractedEntity(
                entity_type=EntityType.DATE_RANGE,
                value={"start": date.today() - delta, "end": date.today()},
                original_text=f"letzte {count} {unit}",
                confidence=0.90,
            ))

        return entities

    def _extract_document_types(self, query: str) -> List[ExtractedEntity]:
        """Extrahiert Dokumenttypen aus der Abfrage."""
        entities = []

        for keyword, types in DOCUMENT_TYPE_KEYWORDS.items():
            if keyword in query:
                entities.append(ExtractedEntity(
                    entity_type=EntityType.DOCUMENT_TYPE,
                    value=types,
                    original_text=keyword,
                    confidence=0.95,
                ))

        return entities

    def _extract_status(self, query: str) -> List[ExtractedEntity]:
        """Extrahiert Status-Keywords aus der Abfrage."""
        entities = []

        for keyword, statuses in STATUS_KEYWORDS.items():
            if keyword in query:
                entities.append(ExtractedEntity(
                    entity_type=EntityType.STATUS,
                    value=statuses,
                    original_text=keyword,
                    confidence=0.90,
                ))

        return entities

    async def _extract_company_names(
        self,
        query: str,
        company_id: Optional[uuid.UUID],
    ) -> List[ExtractedEntity]:
        """Extrahiert und validiert Firmennamen gegen die DB."""
        entities = []

        # Haeufige Firmenbezeichnungen
        company_suffixes = ["gmbh", "ag", "kg", "ohg", "e.k.", "ug", "mbh", "co kg"]

        # Finde potentielle Firmennamen
        for suffix in company_suffixes:
            # Pattern: "Wort(e) GmbH" etc.
            pattern = rf'([A-Za-z\u00c0-\u00ff]+(?:\s+[A-Za-z\u00c0-\u00ff]+)*)\s+{suffix}'
            matches = re.findall(pattern, query, re.IGNORECASE)

            for match in matches:
                full_name = f"{match} {suffix}"

                # DB-Lookup
                stmt = select(BusinessEntity).where(
                    BusinessEntity.name.ilike(f"%{match}%")
                )
                if company_id:
                    stmt = stmt.where(BusinessEntity.company_id == company_id)
                stmt = stmt.limit(1)

                result = await self.db.execute(stmt)
                entity = result.scalar_one_or_none()

                if entity:
                    entities.append(ExtractedEntity(
                        entity_type=EntityType.COMPANY,
                        value={"id": entity.id, "name": entity.name},
                        original_text=full_name,
                        confidence=0.90,
                    ))
                else:
                    # Auch ohne DB-Match hinzufuegen (fuer Fuzzy-Suche)
                    entities.append(ExtractedEntity(
                        entity_type=EntityType.COMPANY,
                        value={"name": full_name},
                        original_text=full_name,
                        confidence=0.70,
                    ))

        # Keyword "von Firma X"
        von_pattern = r'von\s+([A-Za-z\u00c0-\u00ff]+(?:\s+[A-Za-z\u00c0-\u00ff]+){0,3})'
        von_matches = re.findall(von_pattern, query, re.IGNORECASE)

        for match in von_matches:
            if match.lower() not in ["der", "die", "das", "dem", "den"]:
                # DB-Lookup
                stmt = select(BusinessEntity).where(
                    BusinessEntity.name.ilike(f"%{match}%")
                )
                if company_id:
                    stmt = stmt.where(BusinessEntity.company_id == company_id)
                stmt = stmt.limit(1)

                result = await self.db.execute(stmt)
                entity = result.scalar_one_or_none()

                if entity:
                    entities.append(ExtractedEntity(
                        entity_type=EntityType.COMPANY,
                        value={"id": entity.id, "name": entity.name},
                        original_text=match,
                        confidence=0.85,
                    ))

        return entities

    # ========================================================================
    # Query Processing
    # ========================================================================

    async def _process_search_query(
        self,
        query: str,
        entities: List[ExtractedEntity],
        company_id: Optional[uuid.UUID],
        limit: int,
    ) -> NLQResult:
        """Verarbeitet eine Such-Abfrage."""

        # Base-Query mit optional Entity Join
        stmt = (
            select(Document, BusinessEntity.name.label("entity_name"))
            .outerjoin(BusinessEntity, Document.business_entity_id == BusinessEntity.id)
            .where(Document.deleted_at.is_(None))
        )

        if company_id:
            stmt = stmt.where(Document.company_id == company_id)

        # Filter anwenden basierend auf Entities
        for entity in entities:
            if entity.entity_type == EntityType.DOCUMENT_TYPE:
                stmt = stmt.where(Document.document_type.in_(entity.value))

            elif entity.entity_type == EntityType.COMPANY:
                if "id" in entity.value:
                    stmt = stmt.where(Document.business_entity_id == entity.value["id"])

            elif entity.entity_type == EntityType.DATE_RANGE:
                stmt = stmt.where(
                    and_(
                        Document.created_at >= entity.value["start"],
                        Document.created_at <= entity.value["end"],
                    )
                )

            elif entity.entity_type == EntityType.AMOUNT:
                if isinstance(entity.value, dict):
                    # Operator-basiert
                    if entity.value.get("operator") == "gte":
                        stmt = stmt.where(
                            Document.extracted_data["total_gross"].astext.cast(Decimal) >= entity.value["amount"]
                        )
                    elif entity.value.get("operator") == "lte":
                        stmt = stmt.where(
                            Document.extracted_data["total_gross"].astext.cast(Decimal) <= entity.value["amount"]
                        )
                else:
                    # Exakter Betrag (mit Toleranz)
                    tolerance = entity.value * Decimal("0.01")
                    stmt = stmt.where(
                        and_(
                            Document.extracted_data["total_gross"].astext.cast(Decimal) >= entity.value - tolerance,
                            Document.extracted_data["total_gross"].astext.cast(Decimal) <= entity.value + tolerance,
                        )
                    )

        stmt = stmt.order_by(Document.created_at.desc()).limit(limit)

        # Ausfuehren (Tupel: Document, entity_name)
        result = await self.db.execute(stmt)
        rows = result.all()

        # Ergebnis aufbereiten
        results = []
        documents = []
        for row in rows:
            doc = row[0]  # Document
            entity_name = row[1]  # BusinessEntity.name (kann None sein)
            documents.append(doc)
            results.append({
                "id": str(doc.id),
                "filename": doc.filename,
                "document_type": doc.document_type,
                "created_at": doc.created_at.isoformat() if doc.created_at else None,
                "amount": doc.extracted_data.get("total_gross") if doc.extracted_data else None,
                "entity_name": entity_name,
            })

        # Natuerliche Antwort generieren
        if len(documents) == 0:
            natural_response = "Keine Dokumente gefunden, die Ihren Kriterien entsprechen."
        elif len(documents) == 1:
            natural_response = f"Ich habe 1 Dokument gefunden: {documents[0].filename}"
        else:
            natural_response = f"Ich habe {len(documents)} Dokumente gefunden."
            if len(documents) >= limit:
                natural_response += f" (Limit: {limit})"

        return NLQResult(
            success=True,
            intent=QueryIntent.SEARCH,
            extracted_entities=entities,
            results=results,
            result_count=len(results),
            natural_response=natural_response,
            confidence=0.85,
        )

    async def _process_aggregate_query(
        self,
        query: str,
        entities: List[ExtractedEntity],
        company_id: Optional[uuid.UUID],
    ) -> NLQResult:
        """Verarbeitet eine Aggregations-Abfrage."""

        # Erkenne Aggregations-Typ
        agg_type = "sum"  # Default
        for keyword, agg in AGGREGATION_KEYWORDS.items():
            if keyword in query:
                agg_type = agg
                break

        # Base-Query auf InvoiceTracking (fuer Betraege)
        if agg_type in ["sum", "avg", "max", "min"]:
            if agg_type == "sum":
                agg_func = func.sum(InvoiceTracking.total_amount)
            elif agg_type == "avg":
                agg_func = func.avg(InvoiceTracking.total_amount)
            elif agg_type == "max":
                agg_func = func.max(InvoiceTracking.total_amount)
            else:
                agg_func = func.min(InvoiceTracking.total_amount)

            stmt = select(agg_func)

            if company_id:
                stmt = stmt.where(InvoiceTracking.company_id == company_id)

        else:  # count
            stmt = select(func.count(Document.id))
            if company_id:
                stmt = stmt.where(Document.company_id == company_id)

        # Filter anwenden
        for entity in entities:
            if entity.entity_type == EntityType.DATE_RANGE:
                stmt = stmt.where(
                    and_(
                        InvoiceTracking.created_at >= entity.value["start"],
                        InvoiceTracking.created_at <= entity.value["end"],
                    )
                )

            elif entity.entity_type == EntityType.STATUS:
                stmt = stmt.where(InvoiceTracking.status.in_(entity.value))

        result = await self.db.execute(stmt)
        agg_value = result.scalar()

        # Natuerliche Antwort
        if agg_type == "sum":
            if agg_value:
                natural_response = f"Die Gesamtsumme betraegt {float(agg_value):,.2f} EUR."
            else:
                natural_response = "Keine Daten fuer die Summenberechnung gefunden."
        elif agg_type == "avg":
            if agg_value:
                natural_response = f"Der Durchschnitt betraegt {float(agg_value):,.2f} EUR."
            else:
                natural_response = "Keine Daten fuer die Durchschnittsberechnung gefunden."
        elif agg_type == "count":
            natural_response = f"Anzahl: {agg_value or 0}"
        elif agg_type == "max":
            if agg_value:
                natural_response = f"Der hoechste Betrag ist {float(agg_value):,.2f} EUR."
            else:
                natural_response = "Keine Daten gefunden."
        else:  # min
            if agg_value:
                natural_response = f"Der niedrigste Betrag ist {float(agg_value):,.2f} EUR."
            else:
                natural_response = "Keine Daten gefunden."

        return NLQResult(
            success=True,
            intent=QueryIntent.AGGREGATE,
            extracted_entities=entities,
            aggregation_value=agg_value,
            result_count=1 if agg_value else 0,
            natural_response=natural_response,
            confidence=0.85,
        )

    async def _process_compare_query(
        self,
        query: str,
        entities: List[ExtractedEntity],
        company_id: Optional[uuid.UUID],
    ) -> NLQResult:
        """Verarbeitet eine Vergleichs-Abfrage."""

        # Vereinfacht: Vergleiche zwei Zeitraeume
        date_ranges = [e for e in entities if e.entity_type == EntityType.DATE_RANGE]

        if len(date_ranges) < 2:
            return NLQResult(
                success=False,
                intent=QueryIntent.COMPARE,
                extracted_entities=entities,
                natural_response="Fuer einen Vergleich benoetigen Sie zwei Zeitraeume. "
                               "Beispiel: 'Vergleiche Januar mit Februar'",
                confidence=0.5,
            )

        results = []
        for i, dr in enumerate(date_ranges[:2]):
            stmt = select(func.sum(InvoiceTracking.total_amount)).where(
                and_(
                    InvoiceTracking.created_at >= dr.value["start"],
                    InvoiceTracking.created_at <= dr.value["end"],
                )
            )
            if company_id:
                stmt = stmt.where(InvoiceTracking.company_id == company_id)

            result = await self.db.execute(stmt)
            total = result.scalar() or Decimal("0")
            results.append({
                "period": dr.original_text,
                "total": float(total),
            })

        # Vergleich
        diff = results[0]["total"] - results[1]["total"]
        pct_change = (diff / results[1]["total"] * 100) if results[1]["total"] else 0

        natural_response = (
            f"Vergleich: {results[0]['period']} = {results[0]['total']:,.2f} EUR, "
            f"{results[1]['period']} = {results[1]['total']:,.2f} EUR. "
            f"Differenz: {diff:+,.2f} EUR ({pct_change:+.1f}%)"
        )

        return NLQResult(
            success=True,
            intent=QueryIntent.COMPARE,
            extracted_entities=entities,
            results=results,
            result_count=2,
            natural_response=natural_response,
            confidence=0.80,
        )

    async def _process_chat_query(
        self,
        query: str,
        entities: List[ExtractedEntity],
        company_id: Optional[uuid.UUID],
    ) -> NLQResult:
        """Verarbeitet eine Chat/RAG-Abfrage mit vollstaendiger RAG-Integration.

        Phase 9.3: Enhanced NLQ with RAG

        Workflow:
        1. Semantische Suche nach relevanten Dokumenten-Chunks
        2. Kontext aus Chunks zusammenstellen
        3. LLM mit Kontext und Frage aufrufen
        4. Antwort mit Quellenangaben zurueckgeben
        """
        try:
            # RAG-Services importieren (lazy import um Circular Imports zu vermeiden)
            from app.services.rag.search_service import RAGSearchService
            from app.services.rag.llm_service import LLMService, LLMMessage, LLMContextType


            # 1. Semantische Suche nach relevanten Chunks
            search_service = RAGSearchService()
            search_result = await search_service.semantic_search(
                db=self.db,
                query=query,
                limit=5,  # Top 5 relevante Chunks
                threshold=0.6,
                rerank=True
            )

            # Pruefen ob Chunks gefunden wurden
            if not search_result.results:
                return NLQResult(
                    success=True,
                    intent=QueryIntent.CHAT,
                    extracted_entities=entities,
                    natural_response=(
                        "Ich konnte keine relevanten Dokumente zu Ihrer Frage finden. "
                        "Bitte stellen Sie sicher, dass die entsprechenden Dokumente "
                        "bereits verarbeitet wurden."
                    ),
                    confidence=0.40,
                    results=[],
                    result_count=0,
                )

            # 2. Kontext aus Chunks zusammenstellen
            context_parts: List[str] = []
            source_documents: List[Dict[str, Any]] = []

            for i, chunk in enumerate(search_result.results, 1):
                context_parts.append(
                    f"[Quelle {i}] (Relevanz: {chunk.similarity:.0%}):\n{chunk.chunk_text}"
                )
                source_documents.append({
                    "chunk_id": str(chunk.chunk_id),
                    "document_id": str(chunk.document_id),
                    "similarity": round(chunk.similarity, 3),
                    "page_number": chunk.page_number,
                    "section_type": chunk.section_type,
                })

            context = "\n\n---\n\n".join(context_parts)

            # 3. System-Prompt fuer RAG erstellen
            system_prompt = """Du bist ein hilfreicher Assistent fuer ein Dokumentenmanagementsystem.
Beantworte die Frage basierend auf den bereitgestellten Dokumenten-Auszuegen.

WICHTIGE REGELN:
- Antworte NUR basierend auf den bereitgestellten Informationen
- Wenn die Information nicht in den Dokumenten enthalten ist, sage das ehrlich
- Nenne die Quellen (Quelle 1, Quelle 2, etc.) wenn du Informationen verwendest
- Antworte auf Deutsch
- Halte dich kurz und praezise

KONTEXT AUS DOKUMENTEN:
{context}"""

            # 4. LLM aufrufen
            llm_service = LLMService()
            try:
                messages = [
                    LLMMessage(role="system", content=system_prompt.format(context=context)),
                    LLMMessage(role="user", content=query)
                ]

                llm_response = await llm_service.generate(
                    messages=messages,
                    context_type=LLMContextType.GENERAL,
                    max_tokens=1024,
                    temperature=0.3  # Niedrigere Temperatur fuer faktische Antworten
                )

                natural_response = llm_response.content

                # Quellenangaben hinzufuegen
                if source_documents:
                    natural_response += "\n\n📚 Verwendete Quellen: "
                    natural_response += ", ".join(
                        f"Dokument {i+1}" for i in range(len(source_documents))
                    )

                return NLQResult(
                    success=True,
                    intent=QueryIntent.CHAT,
                    extracted_entities=entities,
                    natural_response=natural_response,
                    confidence=0.85,
                    results=source_documents,
                    result_count=len(source_documents),
                )

            except Exception as llm_error:
                logger.warning(
                    "nlq_llm_fallback",
                    error=str(llm_error),
                    query=query[:50]
                )
                # Fallback: Chunks ohne LLM-Verarbeitung zurueckgeben
                return NLQResult(
                    success=True,
                    intent=QueryIntent.CHAT,
                    extracted_entities=entities,
                    natural_response=(
                        f"Ich habe {len(search_result.results)} relevante Dokumente gefunden. "
                        "Die LLM-Verarbeitung ist derzeit nicht verfuegbar. "
                        "Hier sind die relevanten Textausschnitte:\n\n" +
                        "\n---\n".join(
                            f"• {r.chunk_text[:200]}..." for r in search_result.results[:3]
                        )
                    ),
                    confidence=0.65,
                    results=source_documents,
                    result_count=len(source_documents),
                )

            finally:
                await llm_service.close()

        except ImportError as e:
            logger.warning("nlq_rag_import_error", **safe_error_log(e))
            return NLQResult(
                success=True,
                intent=QueryIntent.CHAT,
                extracted_entities=entities,
                natural_response=(
                    "Die RAG-Funktionalitaet ist derzeit nicht verfuegbar. "
                    "Bitte versuchen Sie es spaeter erneut."
                ),
                confidence=0.30,
            )
        except Exception as e:
            logger.error("nlq_chat_error", **safe_error_log(e), query=query[:50])
            return NLQResult(
                success=False,
                intent=QueryIntent.CHAT,
                extracted_entities=entities,
                natural_response=safe_error_detail(e, "NLQ"),
                confidence=0.0,
                error_message=safe_error_detail(e, "NLQ"),
            )


# ============================================================================
# Factory Function
# ============================================================================


async def get_nlq_service(db: AsyncSession) -> NLQService:
    """Factory-Funktion fuer NLQService.

    Args:
        db: Async Database Session

    Returns:
        Konfigurierter NLQService
    """
    return NLQService(db=db)
