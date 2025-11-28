"""Search Analytics Service - Tracking und Auswertung von Suchanfragen.

Dieses Modul bietet Funktionen zur:
- Protokollierung von Suchanfragen
- Analyse von Suchmustern
- Generierung von Nutzungsstatistiken
- Verbesserung der Suchqualitaet
"""

import structlog
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict, Any
from uuid import UUID
import hashlib
import ipaddress

from sqlalchemy import select, func, text, and_, Integer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert

from app.db.models import SearchAnalytics, User
from app.db.schemas import SearchFilters, SearchType

logger = structlog.get_logger(__name__)


class SearchAnalyticsService:
    """Service fuer Such-Analytics und Reporting.

    Bietet Funktionen zur:
    - Protokollierung von Suchanfragen mit Metadaten
    - Klick-Tracking auf Suchergebnisse
    - Aggregierte Statistiken (taegliche, woechentliche Auswertungen)
    - Analyse von Suchmustern und Filter-Nutzung
    - Identifikation von Suchanfragen ohne Ergebnisse

    Der Service anonymisiert IP-Adressen (DSGVO-konform) und
    verwendet eine materialisierte View fuer performante Abfragen.

    Hinweis: Alle zeitbasierten Abfragen verwenden UTC.
    """

    def _anonymize_ip(self, ip_address: Optional[str]) -> Optional[str]:
        """Anonymisiert eine IP-Adresse fuer DSGVO-Konformitaet.

        IPv4: Behaelt erste zwei Oktetts (x.x.0.0)
        IPv6: Behaelt erste 48 Bits / 3 Segmente (xxxx:xxxx:xxxx::)

        Args:
            ip_address: Zu anonymisierende IP-Adresse

        Returns:
            Anonymisierte IP-Adresse oder None bei ungueltigem Format
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
                # Expandiere zuerst zu vollem Format fuer konsistente Verarbeitung
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
            execution_time_ms: Gesamtausfuehrungszeit
            user_id: Benutzer-ID (optional)
            filters: Angewendete Filter (optional)
            page: Aktuelle Seite
            per_page: Ergebnisse pro Seite
            fts_time_ms: FTS-Ausfuehrungszeit (optional)
            semantic_time_ms: Semantic-Ausfuehrungszeit (optional)
            session_id: Session-ID fuer Gruppierung (optional)
            previous_query_id: Vorherige Anfrage bei Verfeinerung (optional)
            user_agent: Browser User-Agent (optional)
            ip_address: IP-Adresse fuer Aggregation (optional)

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
            query=query[:500],  # Limitiere auf 500 Zeichen
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
        """Protokolliert einen Klick auf ein Suchergebnis.

        Args:
            db: Datenbank-Session
            analytics_id: ID des Analytics-Eintrags
            result_position: Position des geklickten Ergebnisses (1-basiert)
            is_download: Ob das Dokument heruntergeladen wurde
        """
        result = await db.execute(
            select(SearchAnalytics).where(SearchAnalytics.id == analytics_id)
        )
        analytics = result.scalar_one_or_none()

        if not analytics:
            logger.warning("analytics_not_found", analytics_id=str(analytics_id))
            return

        analytics.clicked_results = (analytics.clicked_results or 0) + 1

        if analytics.first_click_position is None:
            analytics.first_click_position = result_position

        if is_download:
            analytics.downloaded_count = (analytics.downloaded_count or 0) + 1

        await db.commit()

        logger.debug(
            "search_click_logged",
            analytics_id=str(analytics_id),
            position=result_position,
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
            days: Anzahl der Tage fuer die Statistik
            user_id: Optional - nur Statistiken fuer diesen Benutzer

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
            SearchAnalytics.query,
            func.count(SearchAnalytics.id).label("count"),
        ).where(
            and_(*base_filter)
        ).group_by(
            SearchAnalytics.query
        ).order_by(
            func.count(SearchAnalytics.id).desc()
        ).limit(10)

        top_results = await db.execute(top_queries_query)
        top_queries = [{"query": row.query, "count": row.count} for row in top_results]

        # Filter-Nutzung
        filter_usage_query = select(
            func.sum(func.cast(SearchAnalytics.has_document_type_filter, Integer)).label("type_filter"),
            func.sum(func.cast(SearchAnalytics.has_date_filter, Integer)).label("date_filter"),
            func.sum(func.cast(SearchAnalytics.has_tag_filter, Integer)).label("tag_filter"),
            func.sum(func.cast(SearchAnalytics.has_status_filter, Integer)).label("status_filter"),
        ).where(and_(*base_filter))

        # Verwende raw SQL fuer Boolean-Summe
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
        """Liefert taegliche Suchstatistiken.

        Verwendet die materialisierte View fuer Performance.

        Args:
            db: Datenbank-Session
            days: Anzahl der Tage

        Returns:
            Liste mit taeglichen Statistiken
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
                error=str(e),
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
                query,
                COUNT(*) as search_count,
                AVG(total_results)::INTEGER as avg_results,
                AVG(clicked_results)::FLOAT as avg_clicks,
                COUNT(DISTINCT user_id) as unique_searchers
            FROM search_analytics
            WHERE created_at >= :since
            GROUP BY query
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
                "query": row.query,
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

        Nuetzlich fuer die Verbesserung der Suchqualitaet.

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
                query,
                COUNT(*) as search_count,
                search_type,
                MAX(created_at) as last_searched
            FROM search_analytics
            WHERE created_at >= :since AND total_results = 0
            GROUP BY query, search_type
            ORDER BY search_count DESC
            LIMIT :limit
        """)

        result = await db.execute(query, {"since": since, "limit": limit})
        rows = result.fetchall()

        return [
            {
                "query": row.query,
                "search_count": row.search_count,
                "search_type": row.search_type,
                "last_searched": row.last_searched.isoformat() if row.last_searched else None,
            }
            for row in rows
        ]

    async def refresh_daily_statistics(self, db: AsyncSession) -> bool:
        """Aktualisiert die materialisierte View fuer taegliche Statistiken.

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
            logger.error("refresh_daily_statistics_error", error=str(e))
            return False


# Singleton-Instanz
_search_analytics_service: Optional[SearchAnalyticsService] = None


def get_search_analytics_service() -> SearchAnalyticsService:
    """Liefert die Singleton-Instanz des SearchAnalyticsService."""
    global _search_analytics_service
    if _search_analytics_service is None:
        _search_analytics_service = SearchAnalyticsService()
    return _search_analytics_service
