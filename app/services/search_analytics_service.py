"""Search Analytics Service - Tracking und Auswertung von Suchanfragen.

Dieses Modul bietet Funktionen zur:
- Protokollierung von Suchanfragen
- Analyse von Suchmustern
- Generierung von Nutzungsstatistiken
- Verbesserung der Suchqualität
"""

import structlog
import math
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict, Any, Tuple
from uuid import UUID
import hashlib
import ipaddress

from sqlalchemy import select, func, text, and_, Integer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert

from app.db.models import SearchAnalytics, User
from app.db.schemas import SearchFilters, SearchType
from app.core.safe_errors import safe_error_log, safe_error_detail

logger = structlog.get_logger(__name__)


# =============================================================================
# Position-Weighted Click Analytics Functions
# =============================================================================

def calculate_position_weight(position: int, decay_rate: float = 0.15) -> float:
    """Berechnet das Gewicht eines Klicks basierend auf der Position.

    Verwendet exponentiellen Decay:
    - Position 1: 1.0 (volle Relevanz)
    - Position 5: ~0.55 (mittlere Relevanz)
    - Position 10: ~0.26 (niedrige Relevanz)
    - Position 20: ~0.07 (sehr niedrige Relevanz)

    Die Idee: Ein Klick auf Position 1 zeigt starke Relevanz an,
    während ein Klick auf Position 10 weniger aussagekraeftig ist
    (User musste weit scrollen).

    Args:
        position: 1-basierte Klick-Position (1 = erstes Ergebnis)
        decay_rate: Abklingrate (Standard: 0.15, höher = schnellerer Abfall)

    Returns:
        Gewicht zwischen 0 und 1
    """
    if position < 1:
        return 0.0
    # Formel: exp(-decay_rate * (position - 1))
    return math.exp(-decay_rate * (position - 1))


def calculate_weighted_ctr(
    total_searches: int,
    weighted_score_sum: float,
    max_possible_score: Optional[float] = None
) -> float:
    """Berechnet die gewichtete Click-Through-Rate.

    Im Gegensatz zur einfachen CTR (Klicks / Suchen) berücksichtigt
    die gewichtete CTR die Position der Klicks.

    Args:
        total_searches: Anzahl der Suchanfragen
        weighted_score_sum: Summe der gewichteten Klick-Scores
        max_possible_score: Maximaler Score (default: total_searches * 1.0)

    Returns:
        Gewichtete CTR zwischen 0 und 1 (oder höher bei Mehrfachklicks)
    """
    if total_searches == 0:
        return 0.0

    if max_possible_score is None:
        # Maximaler Score wenn jede Suche einen Klick auf Position 1 haette
        max_possible_score = float(total_searches)

    return weighted_score_sum / max_possible_score


class SearchAnalyticsService:
    """Service für Such-Analytics und Reporting.

    Bietet Funktionen zur:
    - Protokollierung von Suchanfragen mit Metadaten
    - Klick-Tracking auf Suchergebnisse
    - Aggregierte Statistiken (tägliche, woechentliche Auswertungen)
    - Analyse von Suchmustern und Filter-Nutzung
    - Identifikation von Suchanfragen ohne Ergebnisse

    Der Service anonymisiert IP-Adressen (DSGVO-konform) und
    verwendet eine materialisierte View für performante Abfragen.

    Hinweis: Alle zeitbasierten Abfragen verwenden UTC.
    """

    def _anonymize_ip(self, ip_address: Optional[str]) -> Optional[str]:
        """Anonymisiert eine IP-Adresse für DSGVO-Konformität.

        IPv4: Behält erste zwei Oktetts (x.x.0.0)
        IPv6: Behält erste 48 Bits / 3 Segmente (xxxx:xxxx:xxxx::)

        Args:
            ip_address: Zu anonymisierende IP-Adresse

        Returns:
            Anonymisierte IP-Adresse oder None bei ungültigem Format
        """
        if not ip_address:
            return None

        try:
            ip = ipaddress.ip_address(ip_address)
            if isinstance(ip, ipaddress.IPv4Address):
                # Behalte erste zwei Oktetts: x.x.0.0
                parts = ip_address.split(".")
                return f"{parts[0]}.{parts[1]}.0.0"
            elif isinstance(ip, ipaddress.IPv6Address):
                # Behalte erste 48 Bits (3 Segmente): xxxx:xxxx:xxxx::
                # Expandiere zuerst zu vollem Format für konsistente Verarbeitung
                expanded = ip.exploded.split(":")
                return f"{expanded[0]}:{expanded[1]}:{expanded[2]}::"
        except ValueError:
            logger.warning(
                "invalid_ip_address_format",
                ip_address=ip_address[:20] if ip_address else None
            )
            return None

        return None

    async def log_search(
        self,
        db: AsyncSession,
        query: str,
        search_type: SearchType,
        total_results: int,
        execution_time_ms: int,
        user_id: Optional[UUID] = None,
        filters: Optional[SearchFilters] = None,
        page: int = 1,
        per_page: int = 20,
        fts_time_ms: Optional[int] = None,
        semantic_time_ms: Optional[int] = None,
        session_id: Optional[str] = None,
        previous_query_id: Optional[UUID] = None,
        user_agent: Optional[str] = None,
        ip_address: Optional[str] = None,
    ) -> UUID:
        """Protokolliert eine Suchanfrage.

        Args:
            db: Datenbank-Session
            query: Suchbegriff
            search_type: Art der Suche (fts, semantic, hybrid)
            total_results: Anzahl der Treffer
            execution_time_ms: Gesamtausführungszeit
            user_id: Benutzer-ID (optional)
            filters: Angewendete Filter (optional)
            page: Aktuelle Seite
            per_page: Ergebnisse pro Seite
            fts_time_ms: FTS-Ausführungszeit (optional)
            semantic_time_ms: Semantic-Ausführungszeit (optional)
            session_id: Session-ID für Gruppierung (optional)
            previous_query_id: Vorherige Anfrage bei Verfeinerung (optional)
            user_agent: Browser User-Agent (optional)
            ip_address: IP-Adresse für Aggregation (optional)

        Returns:
            UUID der erstellten Analytics-Eintrag
        """
        # Anonymisiere IP-Adresse (DSGVO-konform)
        anonymized_ip = self._anonymize_ip(ip_address)

        # Analysiere Filter
        filters_dict: Dict[str, Any] = {}
        has_type_filter = False
        has_date_filter = False
        has_tag_filter = False
        has_status_filter = False

        if filters:
            if filters.document_type:
                filters_dict["document_type"] = filters.document_type.value if hasattr(filters.document_type, 'value') else str(filters.document_type)
                has_type_filter = True
            if filters.date_from or filters.date_to:
                filters_dict["date_from"] = filters.date_from.isoformat() if filters.date_from else None
                filters_dict["date_to"] = filters.date_to.isoformat() if filters.date_to else None
                has_date_filter = True
            if filters.tags:
                filters_dict["tags"] = filters.tags
                has_tag_filter = True
            if filters.status:
                filters_dict["status"] = filters.status.value if hasattr(filters.status, 'value') else str(filters.status)
                has_status_filter = True
            if filters.confidence_min is not None:
                filters_dict["confidence_min"] = filters.confidence_min
            if filters.language:
                filters_dict["language"] = filters.language
            if filters.has_embedding is not None:
                filters_dict["has_embedding"] = filters.has_embedding

        # Erstelle Analytics-Eintrag
        analytics = SearchAnalytics(
            user_id=user_id,
            search_query=query[:500],  # Limitiere auf 500 Zeichen
            search_type=search_type.value if hasattr(search_type, 'value') else str(search_type),
            query_length=len(query),
            filters_used=filters_dict,
            has_document_type_filter=has_type_filter,
            has_date_filter=has_date_filter,
            has_tag_filter=has_tag_filter,
            has_status_filter=has_status_filter,
            total_results=total_results,
            results_returned=min(per_page, total_results),
            page_number=page,
            execution_time_ms=execution_time_ms,
            fts_time_ms=fts_time_ms,
            semantic_time_ms=semantic_time_ms,
            session_id=session_id,
            is_refinement=previous_query_id is not None,
            previous_query_id=previous_query_id,
            user_agent=user_agent[:255] if user_agent else None,
            ip_address=anonymized_ip,
        )

        db.add(analytics)
        await db.commit()
        await db.refresh(analytics)

        logger.info(
            "search_logged",
            analytics_id=str(analytics.id),
            query_length=len(query),
            search_type=search_type,
            total_results=total_results,
            execution_time_ms=execution_time_ms,
        )

        return analytics.id

    async def log_click(
        self,
        db: AsyncSession,
        analytics_id: UUID,
        result_position: int,
        is_download: bool = False,
    ) -> None:
        """Protokolliert einen Klick auf ein Suchergebnis mit Position-Weighted Score.

        Args:
            db: Datenbank-Session
            analytics_id: ID des Analytics-Eintrags
            result_position: Position des geklickten Ergebnisses (1-basiert)
            is_download: Ob das Dokument heruntergeladen wurde

        Position-Weighted Scoring:
            - Position 1: +1.0 zum weighted_click_score
            - Position 5: +0.55 zum weighted_click_score
            - Position 10: +0.26 zum weighted_click_score
            - Formel: exp(-0.15 * (position - 1))
        """
        result = await db.execute(
            select(SearchAnalytics).where(SearchAnalytics.id == analytics_id)
        )
        analytics = result.scalar_one_or_none()

        if not analytics:
            logger.warning("analytics_not_found", analytics_id=str(analytics_id))
            return

        # Klick-Zähler aktualisieren
        analytics.clicked_results = (analytics.clicked_results or 0) + 1

        # Erste Klick-Position merken
        if analytics.first_click_position is None:
            analytics.first_click_position = result_position

        # Download-Zähler
        if is_download:
            analytics.downloaded_count = (analytics.downloaded_count or 0) + 1

        # Position-Weighted Click Analytics
        # Gewicht basierend auf Position berechnen
        position_weight = calculate_position_weight(result_position)

        # Gewichteten Score kumulieren
        current_score = analytics.weighted_click_score or 0.0
        analytics.weighted_click_score = current_score + position_weight

        # Klick-Position zur Liste hinzufuegen
        current_positions = analytics.click_positions or []
        if isinstance(current_positions, list):
            current_positions.append(result_position)
            analytics.click_positions = current_positions
        else:
            # Falls JSON nicht korrekt initialisiert war
            analytics.click_positions = [result_position]

        await db.commit()

        logger.debug(
            "search_click_logged",
            analytics_id=str(analytics_id),
            position=result_position,
            position_weight=round(position_weight, 4),
            total_weighted_score=round(analytics.weighted_click_score, 4),
            is_download=is_download,
        )

    async def get_search_statistics(
        self,
        db: AsyncSession,
        days: int = 30,
        user_id: Optional[UUID] = None,
    ) -> Dict[str, Any]:
        """Liefert aggregierte Suchstatistiken.

        Args:
            db: Datenbank-Session
            days: Anzahl der Tage für die Statistik
            user_id: Optional - nur Statistiken für diesen Benutzer

        Returns:
            Dictionary mit Statistiken
        """
        since = datetime.now(timezone.utc) - timedelta(days=days)

        # Basis-Query
        base_filter = [SearchAnalytics.created_at >= since]
        if user_id:
            base_filter.append(SearchAnalytics.user_id == user_id)

        # Gesamtstatistiken
        total_query = select(
            func.count(SearchAnalytics.id).label("total_searches"),
            func.count(func.distinct(SearchAnalytics.user_id)).label("unique_users"),
            func.avg(SearchAnalytics.total_results).label("avg_results"),
            func.avg(SearchAnalytics.execution_time_ms).label("avg_execution_time"),
            func.sum(SearchAnalytics.clicked_results).label("total_clicks"),
        ).where(and_(*base_filter))

        result = await db.execute(total_query)
        totals = result.one()

        # Suchen ohne Ergebnisse
        zero_results_query = select(
            func.count(SearchAnalytics.id)
        ).where(
            and_(*base_filter, SearchAnalytics.total_results == 0)
        )
        zero_results = await db.execute(zero_results_query)
        zero_result_count = zero_results.scalar() or 0

        # Aufschluesselung nach Suchtyp
        type_breakdown_query = select(
            SearchAnalytics.search_type,
            func.count(SearchAnalytics.id).label("count"),
            func.avg(SearchAnalytics.execution_time_ms).label("avg_time"),
        ).where(
            and_(*base_filter)
        ).group_by(SearchAnalytics.search_type)

        type_results = await db.execute(type_breakdown_query)
        type_breakdown = {
            row.search_type: {
                "count": row.count,
                "avg_time_ms": round(row.avg_time) if row.avg_time else 0,
            }
            for row in type_results
        }

        # Top-Suchbegriffe
        top_queries_query = select(
            SearchAnalytics.search_query,
            func.count(SearchAnalytics.id).label("count"),
        ).where(
            and_(*base_filter)
        ).group_by(
            SearchAnalytics.search_query
        ).order_by(
            func.count(SearchAnalytics.id).desc()
        ).limit(10)

        top_results = await db.execute(top_queries_query)
        top_queries = [{"query": row.search_query, "count": row.count} for row in top_results]

        # Filter-Nutzung
        filter_usage_query = select(
            func.sum(func.cast(SearchAnalytics.has_document_type_filter, Integer)).label("type_filter"),
            func.sum(func.cast(SearchAnalytics.has_date_filter, Integer)).label("date_filter"),
            func.sum(func.cast(SearchAnalytics.has_tag_filter, Integer)).label("tag_filter"),
            func.sum(func.cast(SearchAnalytics.has_status_filter, Integer)).label("status_filter"),
        ).where(and_(*base_filter))

        # Verwende raw SQL für Boolean-Summe
        filter_usage_sql = text("""
            SELECT
                SUM(CASE WHEN has_document_type_filter THEN 1 ELSE 0 END) as type_filter,
                SUM(CASE WHEN has_date_filter THEN 1 ELSE 0 END) as date_filter,
                SUM(CASE WHEN has_tag_filter THEN 1 ELSE 0 END) as tag_filter,
                SUM(CASE WHEN has_status_filter THEN 1 ELSE 0 END) as status_filter
            FROM search_analytics
            WHERE created_at >= :since
        """)
        params = {"since": since}
        if user_id:
            filter_usage_sql = text("""
                SELECT
                    SUM(CASE WHEN has_document_type_filter THEN 1 ELSE 0 END) as type_filter,
                    SUM(CASE WHEN has_date_filter THEN 1 ELSE 0 END) as date_filter,
                    SUM(CASE WHEN has_tag_filter THEN 1 ELSE 0 END) as tag_filter,
                    SUM(CASE WHEN has_status_filter THEN 1 ELSE 0 END) as status_filter
                FROM search_analytics
                WHERE created_at >= :since AND user_id = :user_id
            """)
            params["user_id"] = user_id

        filter_results = await db.execute(filter_usage_sql, params)
        filter_row = filter_results.one()

        total_searches = totals.total_searches or 0

        return {
            "period_days": days,
            "total_searches": total_searches,
            "unique_users": totals.unique_users or 0,
            "avg_results_per_search": round(totals.avg_results, 1) if totals.avg_results else 0,
            "avg_execution_time_ms": round(totals.avg_execution_time) if totals.avg_execution_time else 0,
            "total_result_clicks": totals.total_clicks or 0,
            "click_through_rate": round(
                (totals.total_clicks or 0) / total_searches * 100, 1
            ) if total_searches > 0 else 0,
            "zero_result_searches": zero_result_count,
            "zero_result_rate": round(
                zero_result_count / total_searches * 100, 1
            ) if total_searches > 0 else 0,
            "search_type_breakdown": type_breakdown,
            "top_queries": top_queries,
            "filter_usage": {
                "document_type": filter_row.type_filter or 0,
                "date_range": filter_row.date_filter or 0,
                "tags": filter_row.tag_filter or 0,
                "status": filter_row.status_filter or 0,
            },
        }

    async def get_daily_statistics(
        self,
        db: AsyncSession,
        days: int = 30,
    ) -> List[Dict[str, Any]]:
        """Liefert tägliche Suchstatistiken.

        Verwendet die materialisierte View für Performance.

        Args:
            db: Datenbank-Session
            days: Anzahl der Tage

        Returns:
            Liste mit täglichen Statistiken
        """
        since = datetime.now(timezone.utc) - timedelta(days=days)

        # Versuche materialisierte View zu nutzen
        try:
            query = text("""
                SELECT
                    date,
                    search_type,
                    total_searches,
                    unique_users,
                    avg_results,
                    avg_execution_time_ms,
                    avg_clicks_per_search,
                    zero_result_searches
                FROM search_analytics_daily
                WHERE date >= :since
                ORDER BY date DESC, search_type
            """)
            result = await db.execute(query, {"since": since})
            rows = result.fetchall()

            return [
                {
                    "date": row.date.isoformat() if row.date else None,
                    "search_type": row.search_type,
                    "total_searches": row.total_searches,
                    "unique_users": row.unique_users,
                    "avg_results": row.avg_results,
                    "avg_execution_time_ms": row.avg_execution_time_ms,
                    "avg_clicks": round(row.avg_clicks_per_search, 2) if row.avg_clicks_per_search else 0,
                    "zero_result_searches": row.zero_result_searches,
                }
                for row in rows
            ]
        except Exception as e:
            logger.warning(
                "materialized_view_error",
                **safe_error_log(e),
                fallback="direct_query",
            )

            # Fallback auf direkte Abfrage
            query = text("""
                SELECT
                    DATE_TRUNC('day', created_at) as date,
                    search_type,
                    COUNT(*) as total_searches,
                    COUNT(DISTINCT user_id) as unique_users,
                    AVG(total_results)::INTEGER as avg_results,
                    AVG(execution_time_ms)::INTEGER as avg_execution_time_ms,
                    AVG(clicked_results)::FLOAT as avg_clicks,
                    SUM(CASE WHEN total_results = 0 THEN 1 ELSE 0 END) as zero_result_searches
                FROM search_analytics
                WHERE created_at >= :since
                GROUP BY DATE_TRUNC('day', created_at), search_type
                ORDER BY date DESC, search_type
            """)
            result = await db.execute(query, {"since": since})
            rows = result.fetchall()

            return [
                {
                    "date": row.date.isoformat() if row.date else None,
                    "search_type": row.search_type,
                    "total_searches": row.total_searches,
                    "unique_users": row.unique_users,
                    "avg_results": row.avg_results,
                    "avg_execution_time_ms": row.avg_execution_time_ms,
                    "avg_clicks": round(row.avg_clicks, 2) if row.avg_clicks else 0,
                    "zero_result_searches": row.zero_result_searches,
                }
                for row in rows
            ]

    async def get_popular_search_terms(
        self,
        db: AsyncSession,
        days: int = 7,
        limit: int = 20,
        min_count: int = 2,
    ) -> List[Dict[str, Any]]:
        """Liefert die beliebtesten Suchbegriffe.

        Args:
            db: Datenbank-Session
            days: Zeitraum in Tagen
            limit: Maximale Anzahl der Ergebnisse
            min_count: Mindestanzahl der Suchen

        Returns:
            Liste der beliebtesten Suchbegriffe
        """
        since = datetime.now(timezone.utc) - timedelta(days=days)

        query = text("""
            SELECT
                search_query,
                COUNT(*) as search_count,
                AVG(total_results)::INTEGER as avg_results,
                AVG(clicked_results)::FLOAT as avg_clicks,
                COUNT(DISTINCT user_id) as unique_searchers
            FROM search_analytics
            WHERE created_at >= :since
            GROUP BY search_query
            HAVING COUNT(*) >= :min_count
            ORDER BY search_count DESC
            LIMIT :limit
        """)

        result = await db.execute(
            query,
            {"since": since, "min_count": min_count, "limit": limit}
        )
        rows = result.fetchall()

        return [
            {
                "query": row.search_query,
                "search_count": row.search_count,
                "avg_results": row.avg_results or 0,
                "avg_clicks": round(row.avg_clicks, 2) if row.avg_clicks else 0,
                "unique_searchers": row.unique_searchers,
            }
            for row in rows
        ]

    async def get_zero_result_queries(
        self,
        db: AsyncSession,
        days: int = 7,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """Liefert Suchanfragen ohne Ergebnisse.

        Nützlich für die Verbesserung der Suchqualität.

        Args:
            db: Datenbank-Session
            days: Zeitraum in Tagen
            limit: Maximale Anzahl der Ergebnisse

        Returns:
            Liste der Suchanfragen ohne Ergebnisse
        """
        since = datetime.now(timezone.utc) - timedelta(days=days)

        query = text("""
            SELECT
                search_query,
                COUNT(*) as search_count,
                search_type,
                MAX(created_at) as last_searched
            FROM search_analytics
            WHERE created_at >= :since AND total_results = 0
            GROUP BY search_query, search_type
            ORDER BY search_count DESC
            LIMIT :limit
        """)

        result = await db.execute(query, {"since": since, "limit": limit})
        rows = result.fetchall()

        return [
            {
                "query": row.search_query,
                "search_count": row.search_count,
                "search_type": row.search_type,
                "last_searched": row.last_searched.isoformat() if row.last_searched else None,
            }
            for row in rows
        ]

    async def refresh_daily_statistics(self, db: AsyncSession) -> bool:
        """Aktualisiert die materialisierte View für tägliche Statistiken.

        Sollte periodisch aufgerufen werden (z.B. via Celery Beat).

        Args:
            db: Datenbank-Session

        Returns:
            True bei Erfolg
        """
        try:
            await db.execute(text("SELECT refresh_search_analytics_daily()"))
            await db.commit()
            logger.info("search_analytics_daily_refreshed")
            return True
        except Exception as e:
            logger.error("refresh_daily_statistics_error", **safe_error_log(e))
            return False

    # =========================================================================
    # Position-Weighted Click Analytics
    # =========================================================================

    async def get_weighted_ctr_statistics(
        self,
        db: AsyncSession,
        days: int = 30,
        min_searches: int = 5,
        limit: int = 20,
    ) -> Dict[str, Any]:
        """Liefert Position-Weighted CTR Statistiken.

        Die gewichtete CTR berücksichtigt die Position der Klicks:
        - Ein Klick auf Position 1 ist wertvoller als auf Position 10
        - Ermöglicht bessere Bewertung der Suchqualität

        Args:
            db: Datenbank-Session
            days: Analysezeitraum in Tagen
            min_searches: Mindestanzahl Suchen für Einbeziehung
            limit: Maximale Anzahl Ergebnisse

        Returns:
            Dictionary mit:
            - overall: Gesamtstatistiken (CTR, weighted CTR, etc.)
            - by_search_type: Aufschluesselung nach Suchtyp
            - top_queries_by_weighted_ctr: Queries mit hoechster gewichteter CTR
            - low_performing_queries: Queries mit niedriger gewichteter CTR
            - position_distribution: Verteilung der Klicks nach Position
        """
        since = datetime.now(timezone.utc) - timedelta(days=days)

        result: Dict[str, Any] = {
            "period_days": days,
            "analysis_timestamp": datetime.now(timezone.utc).isoformat(),
            "overall": {},
            "by_search_type": {},
            "top_queries_by_weighted_ctr": [],
            "low_performing_queries": [],
            "position_distribution": {},
        }

        try:
            # 1. Gesamtstatistiken
            overall_query = text("""
                SELECT
                    COUNT(*) as total_searches,
                    SUM(clicked_results) as total_clicks,
                    SUM(weighted_click_score) as total_weighted_score,
                    AVG(weighted_click_score) as avg_weighted_score,
                    COUNT(CASE WHEN clicked_results > 0 THEN 1 END) as searches_with_clicks,
                    AVG(first_click_position) as avg_first_click_position
                FROM search_analytics
                WHERE created_at >= :since
                  AND total_results > 0
            """)
            overall_result = await db.execute(overall_query, {"since": since})
            overall_row = overall_result.one()

            total_searches = overall_row.total_searches or 0
            total_clicks = overall_row.total_clicks or 0
            total_weighted = overall_row.total_weighted_score or 0.0
            searches_with_clicks = overall_row.searches_with_clicks or 0

            # Einfache CTR
            simple_ctr = (searches_with_clicks / total_searches * 100) if total_searches > 0 else 0

            # Gewichtete CTR (normalisiert auf Searches mit Ergebnissen)
            weighted_ctr = calculate_weighted_ctr(total_searches, total_weighted)

            result["overall"] = {
                "total_searches": total_searches,
                "total_clicks": total_clicks,
                "searches_with_clicks": searches_with_clicks,
                "simple_ctr_percent": round(simple_ctr, 2),
                "weighted_ctr": round(weighted_ctr, 4),
                "total_weighted_score": round(total_weighted, 2),
                "avg_weighted_score_per_search": round(overall_row.avg_weighted_score or 0, 4),
                "avg_first_click_position": round(overall_row.avg_first_click_position or 0, 2),
            }

            # 2. Aufschluesselung nach Suchtyp
            type_query = text("""
                SELECT
                    search_type,
                    COUNT(*) as searches,
                    SUM(clicked_results) as clicks,
                    SUM(weighted_click_score) as weighted_score,
                    AVG(first_click_position) as avg_first_position
                FROM search_analytics
                WHERE created_at >= :since
                  AND total_results > 0
                GROUP BY search_type
            """)
            type_result = await db.execute(type_query, {"since": since})

            for row in type_result:
                type_searches = row.searches or 0
                type_weighted = row.weighted_score or 0.0
                type_ctr = calculate_weighted_ctr(type_searches, type_weighted)

                result["by_search_type"][row.search_type] = {
                    "searches": type_searches,
                    "clicks": row.clicks or 0,
                    "weighted_ctr": round(type_ctr, 4),
                    "weighted_score": round(type_weighted, 2),
                    "avg_first_click_position": round(row.avg_first_position or 0, 2),
                }

            # 3. Top Queries nach gewichteter CTR
            top_queries_query = text("""
                SELECT
                    search_query,
                    COUNT(*) as search_count,
                    SUM(clicked_results) as total_clicks,
                    SUM(weighted_click_score) as weighted_score,
                    AVG(first_click_position) as avg_first_position
                FROM search_analytics
                WHERE created_at >= :since
                  AND total_results > 0
                GROUP BY search_query
                HAVING COUNT(*) >= :min_searches
                   AND SUM(weighted_click_score) > 0
                ORDER BY SUM(weighted_click_score) / COUNT(*) DESC
                LIMIT :limit
            """)
            top_result = await db.execute(
                top_queries_query,
                {"since": since, "min_searches": min_searches, "limit": limit}
            )

            for row in top_result:
                q_searches = row.search_count or 1
                q_weighted = row.weighted_score or 0.0
                q_ctr = calculate_weighted_ctr(q_searches, q_weighted)

                result["top_queries_by_weighted_ctr"].append({
                    "query": row.search_query,
                    "search_count": q_searches,
                    "total_clicks": row.total_clicks or 0,
                    "weighted_ctr": round(q_ctr, 4),
                    "weighted_score": round(q_weighted, 2),
                    "avg_first_click_position": round(row.avg_first_position or 0, 2),
                })

            # 4. Low-Performing Queries (Suchen mit Ergebnissen aber wenig/keine Klicks)
            low_perf_query = text("""
                SELECT
                    search_query,
                    COUNT(*) as search_count,
                    AVG(total_results) as avg_results,
                    SUM(clicked_results) as total_clicks,
                    SUM(weighted_click_score) as weighted_score
                FROM search_analytics
                WHERE created_at >= :since
                  AND total_results > 0
                GROUP BY search_query
                HAVING COUNT(*) >= :min_searches
                ORDER BY COALESCE(SUM(weighted_click_score), 0) / COUNT(*) ASC
                LIMIT :limit
            """)
            low_result = await db.execute(
                low_perf_query,
                {"since": since, "min_searches": min_searches, "limit": limit}
            )

            for row in low_result:
                q_searches = row.search_count or 1
                q_weighted = row.weighted_score or 0.0
                q_ctr = calculate_weighted_ctr(q_searches, q_weighted)

                result["low_performing_queries"].append({
                    "query": row.search_query,
                    "search_count": q_searches,
                    "avg_results": round(row.avg_results or 0, 1),
                    "total_clicks": row.total_clicks or 0,
                    "weighted_ctr": round(q_ctr, 4),
                    "improvement_potential": "hoch" if q_ctr < 0.1 else "mittel",
                })

            # 5. Position Distribution (aus click_positions aggregiert)
            # Fallback auf first_click_position wenn click_positions leer
            pos_query = text("""
                SELECT
                    first_click_position as position,
                    COUNT(*) as click_count
                FROM search_analytics
                WHERE created_at >= :since
                  AND first_click_position IS NOT NULL
                GROUP BY first_click_position
                ORDER BY first_click_position
            """)
            pos_result = await db.execute(pos_query, {"since": since})

            total_position_clicks = 0
            position_data = {}
            for row in pos_result:
                pos = row.position
                count = row.click_count or 0
                total_position_clicks += count
                position_data[pos] = count

            # Prozentsatz und Gewicht berechnen
            for pos, count in position_data.items():
                percentage = (count / total_position_clicks * 100) if total_position_clicks > 0 else 0
                result["position_distribution"][str(pos)] = {
                    "clicks": count,
                    "percentage": round(percentage, 2),
                    "position_weight": round(calculate_position_weight(pos), 4),
                }

            logger.info(
                "weighted_ctr_statistics_generated",
                period_days=days,
                total_searches=total_searches,
                weighted_ctr=round(weighted_ctr, 4),
            )

        except Exception as e:
            logger.error("weighted_ctr_statistics_error", **safe_error_log(e), exc_info=True)
            result["error"] = safe_error_detail(e, "Analytics")

        return result


# Singleton-Instanz
_search_analytics_service: Optional[SearchAnalyticsService] = None


def get_search_analytics_service() -> SearchAnalyticsService:
    """Liefert die Singleton-Instanz des SearchAnalyticsService."""
    global _search_analytics_service
    if _search_analytics_service is None:
        _search_analytics_service = SearchAnalyticsService()
    return _search_analytics_service
