"""
Advanced Search API Endpoints.

Erweiterte Suchfunktionen:
- Faceted Search (Filterung nach Kategorien)
- Autocomplete/Suggestions
- Search with Facets kombiniert

Feinpoliert und durchdacht - Intelligente Dokumentensuche.
"""

import structlog
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import SQLAlchemyError, OperationalError, IntegrityError
from redis.exceptions import RedisError, ConnectionError as RedisConnectionError

from app.db.models import User
from app.api.dependencies import get_current_user, get_db
from app.services.search_service import get_search_service, SearchService
from app.services.search_analytics_service import get_search_analytics_service
from app.core.safe_errors import safe_error_log
from app.db.schemas import (
    SearchFilters,
    SearchFacetsResponse,
    SuggestResponse,
    FacetGroup,
)

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/search", tags=["search"])


def get_search_service_dep() -> SearchService:
    """Dependency für SearchService."""
    return get_search_service()


@router.get(
    "/facets",
    response_model=SearchFacetsResponse,
    summary="Facetten abrufen",
    description="Gibt Facetten (Kategorien mit Anzahlen) für die Suchseite zurück."
)
async def get_search_facets(
    facet_fields: Optional[str] = Query(
        "document_type,status,tags,ocr_backend_used",
        description="Komma-separierte Liste der Facet-Felder"
    ),
    document_type: Optional[str] = Query(None, description="Filter: Dokumenttyp"),
    status_filter: Optional[str] = Query(None, alias="status", description="Filter: Status"),
    date_from: Optional[str] = Query(None, description="Filter: Datum von (ISO 8601)"),
    date_to: Optional[str] = Query(None, description="Filter: Datum bis (ISO 8601)"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    search_service: SearchService = Depends(get_search_service_dep)
) -> SearchFacetsResponse:
    """
    Facetten für Suchseiten-Filter.

    Gibt die Anzahl der Dokumente pro Kategorie zurück,
    z.B. wie viele Rechnungen, Verträge etc. vorhanden sind.

    Unterstützte Facet-Felder:
    - document_type: Dokumenttyp (Rechnung, Vertrag, etc.)
    - status: Verarbeitungsstatus
    - tags: Tags
    - ocr_backend_used: Verwendetes OCR-Backend
    - mime_type: MIME-Typ
    """
    from datetime import datetime, timezone

    # Parse facet fields
    fields = [f.strip() for f in facet_fields.split(",") if f.strip()]

    if not fields:
        fields = ["document_type", "status", "tags"]

    # Validate fields
    valid_fields = {"document_type", "status", "tags", "ocr_backend_used", "mime_type", "language"}
    for field in fields:
        if field not in valid_fields:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Ungültiges Facet-Feld: {field}. Gültige Felder: {valid_fields}"
            )

    # Build filters
    filters = None
    if any([document_type, status_filter, date_from, date_to]):
        from app.db.schemas import DocumentType, ProcessingStatus

        filters = SearchFilters(
            document_type=DocumentType(document_type) if document_type else None,
            status=ProcessingStatus(status_filter) if status_filter else None,
            date_from=datetime.fromisoformat(date_from) if date_from else None,
            date_to=datetime.fromisoformat(date_to) if date_to else None,
        )

    try:
        result = await search_service.get_facets(
            db=db,
            user_id=current_user.id,
            facet_fields=fields,
            filters=filters
        )

        logger.info(
            "facets_retrieved",
            user_id=str(current_user.id),
            fields=fields,
            total_documents=result["total_documents"]
        )

        return SearchFacetsResponse(
            facets=result["facets"],
            total_documents=result["total_documents"]
        )

    except OperationalError as e:
        logger.error("facets_db_connection_error", error_type="OperationalError", **safe_error_log(e))
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Datenbankverbindung nicht verfuegbar"
        )
    except SQLAlchemyError as e:
        logger.error("facets_db_error", error_type=type(e).__name__, **safe_error_log(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Datenbankfehler beim Abrufen der Facetten"
        )
    except ValueError as e:
        # SECURITY FIX 29: Generic error message - no internal details
        logger.warning("facets_validation_error", error_type="ValueError", **safe_error_log(e))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ungueltige Filterparameter. Bitte Eingaben pruefen."
        )
    except Exception as e:
        logger.error("facets_error", error_type=type(e).__name__, **safe_error_log(e), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Fehler beim Abrufen der Facetten"
        )


@router.get(
    "/suggest",
    response_model=SuggestResponse,
    summary="Suchvorschläge",
    description="Autovervollständigung für die Suchleiste."
)
async def get_search_suggestions(
    q: str = Query(..., min_length=2, max_length=100, description="Suchbegriff"),
    limit: int = Query(10, ge=1, le=20, description="Maximale Anzahl Vorschläge"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    search_service: SearchService = Depends(get_search_service_dep)
) -> SuggestResponse:
    """
    Autovervollständigung für Suchanfragen.

    Gibt Vorschläge basierend auf:
    - Dokumentnamen
    - Tags
    - Häufige Begriffe aus dem extrahierten Text

    Der `type` der Vorschläge kann sein:
    - "document": Ein Dokumentname
    - "tag": Ein Tag
    - "term": Ein häufiger Begriff

    Das `highlight`-Feld enthält HTML mit <mark>-Tags für die Hervorhebung.
    """
    # P3: Input Sanitization - Query sanitieren gegen XSS/ReDoS
    from app.core.input_sanitization import sanitize_search_query
    sanitized_q, warnings = sanitize_search_query(q, max_length=100, strict_mode=False)
    if warnings:
        logger.debug("search_query_sanitized", original=q[:50], warnings=warnings)
    q = sanitized_q if sanitized_q else q

    try:
        result = await search_service.get_suggestions(
            db=db,
            user_id=current_user.id,
            query=q,
            limit=limit
        )

        logger.debug(
            "suggestions_retrieved",
            user_id=str(current_user.id),
            query=q,
            count=result["total"]
        )

        return SuggestResponse(
            query=result["query"],
            suggestions=result["suggestions"],
            total=result["total"]
        )

    except OperationalError as e:
        logger.error("suggest_db_connection_error", error_type="OperationalError", **safe_error_log(e))
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Datenbankverbindung nicht verfuegbar"
        )
    except SQLAlchemyError as e:
        logger.error("suggest_db_error", error_type=type(e).__name__, **safe_error_log(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Datenbankfehler bei der Autovervollstaendigung"
        )
    except Exception as e:
        logger.error("suggest_error", error_type=type(e).__name__, **safe_error_log(e), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Fehler bei der Autovervollständigung"
        )


@router.get(
    "/popular-tags",
    summary="Beliebte Tags",
    description="Gibt die beliebtesten Tags des Benutzers zurück."
)
async def get_popular_tags(
    limit: int = Query(20, ge=1, le=50, description="Maximale Anzahl Tags"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    search_service: SearchService = Depends(get_search_service_dep)
) -> dict:
    """
    Beliebte Tags des Benutzers.

    Gibt Tags sortiert nach Verwendungshäufigkeit zurück.
    Nützlich für Tag-Clouds oder Filter-Vorschläge.
    """
    try:
        from sqlalchemy import select, func, desc
        from app.db.models import Document, Tag, document_tags

        result = await db.execute(
            select(Tag.name, func.count(document_tags.c.document_id).label("count"))
            .select_from(Tag)
            .join(document_tags, Tag.id == document_tags.c.tag_id)
            .join(Document, Document.id == document_tags.c.document_id)
            .where(Document.owner_id == current_user.id)
            .group_by(Tag.name)
            .order_by(desc("count"))
            .limit(limit)
        )
        rows = result.all()

        tags = [{"name": row[0], "count": row[1]} for row in rows]

        logger.debug(
            "popular_tags_retrieved",
            user_id=str(current_user.id),
            count=len(tags)
        )

        return {
            "tags": tags,
            "total": len(tags)
        }

    except OperationalError as e:
        logger.error("popular_tags_db_connection_error", error_type="OperationalError", **safe_error_log(e))
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Datenbankverbindung nicht verfuegbar"
        )
    except SQLAlchemyError as e:
        logger.error("popular_tags_db_error", error_type=type(e).__name__, **safe_error_log(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Datenbankfehler beim Abrufen der Tags"
        )
    except Exception as e:
        logger.error("popular_tags_error", error_type=type(e).__name__, **safe_error_log(e), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Fehler beim Abrufen der Tags"
        )


@router.get(
    "/recent",
    summary="Letzte Suchen",
    description="Gibt die letzten Suchanfragen des Benutzers zurück (aus Redis)."
)
async def get_recent_searches(
    limit: int = Query(10, ge=1, le=20),
    current_user: User = Depends(get_current_user),
    search_service: SearchService = Depends(get_search_service_dep)
) -> dict:
    """
    Letzte Suchanfragen des Benutzers.

    Wird aus dem Redis-Cache abgerufen.
    Jede Suche enthält:
    - query: Der Suchbegriff
    - timestamp: Zeitstempel der Suche (ISO 8601)
    - results_count: Anzahl der Ergebnisse
    - filters: Verwendete Filter (optional)
    """
    import json
    from app.core.redis_state import RedisStateManager

    try:
        redis_manager = RedisStateManager.get_instance()
        await redis_manager._ensure_connection()

        # Key fuer Search History: search_history:{user_id}
        key = f"search_history:{current_user.id}"

        # Letzte N Suchen abrufen (LRANGE gibt Liste zurueck)
        raw_searches = await redis_manager._redis.lrange(key, 0, limit - 1)

        # JSON-Strings zu Dicts parsen
        searches = []
        for raw in raw_searches:
            try:
                search_data = json.loads(raw)
                searches.append(search_data)
            except json.JSONDecodeError:
                logger.warning("invalid_search_history_entry", raw=raw[:50])
                continue

        # Gesamtzahl der Suchen (LLEN gibt Laenge der Liste)
        total = await redis_manager._redis.llen(key)

        logger.debug(
            "recent_searches_retrieved",
            user_id=str(current_user.id),
            count=len(searches),
            total=total
        )

        return {
            "searches": searches,
            "total": total,
            "limit": limit
        }

    except Exception as e:
        logger.warning("recent_searches_redis_error", **safe_error_log(e))
        # Graceful degradation: Leere Liste zurueckgeben wenn Redis nicht verfuegbar
        return {
            "searches": [],
            "total": 0,
            "info": "Suchhistorie temporaer nicht verfuegbar"
        }


@router.delete(
    "/recent",
    summary="Suchhistorie loeschen",
    description="Loescht die gesamte Suchhistorie des Benutzers."
)
async def clear_search_history(
    current_user: User = Depends(get_current_user),
) -> dict:
    """
    Loescht alle gespeicherten Suchen des Benutzers.

    Nuetzlich fuer Datenschutz oder zum Zuruecksetzen der Historie.
    """
    from app.core.redis_state import RedisStateManager

    try:
        redis_manager = RedisStateManager.get_instance()
        await redis_manager._ensure_connection()

        key = f"search_history:{current_user.id}"

        # Anzahl der geloeschten Eintraege
        deleted_count = await redis_manager._redis.llen(key)

        # Liste loeschen
        await redis_manager._redis.delete(key)

        logger.info(
            "search_history_cleared",
            user_id=str(current_user.id),
            deleted_count=deleted_count
        )

        return {
            "erfolg": True,
            "geloeschte_eintraege": deleted_count,
            "nachricht": f"Suchhistorie erfolgreich geloescht ({deleted_count} Eintraege)"
        }

    except (RedisError, RedisConnectionError) as e:
        logger.error("clear_search_history_redis_error", error_type=type(e).__name__, **safe_error_log(e))
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Redis nicht verfuegbar - Suchhistorie konnte nicht geloescht werden"
        )
    except Exception as e:
        logger.error("clear_search_history_error", error_type=type(e).__name__, **safe_error_log(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Fehler beim Loeschen der Suchhistorie"
        )


# ==================== Search History Helper ====================

async def save_search_to_history(
    user_id: str,
    query: str,
    results_count: int,
    filters: Optional[dict] = None,
    max_history_size: int = 100
) -> bool:
    """
    Speichert eine Suche in der Redis-History des Benutzers.

    Args:
        user_id: Benutzer-ID
        query: Suchbegriff
        results_count: Anzahl der Ergebnisse
        filters: Verwendete Filter (optional)
        max_history_size: Maximale Anzahl der gespeicherten Suchen

    Returns:
        True wenn erfolgreich, False bei Fehler
    """
    import json
    from datetime import datetime, timezone
    from app.core.redis_state import RedisStateManager

    # Leere Suchen nicht speichern
    if not query or not query.strip():
        return False

    try:
        redis_manager = RedisStateManager.get_instance()
        await redis_manager._ensure_connection()

        key = f"search_history:{user_id}"

        # Sucheintrag erstellen
        search_entry = {
            "query": query.strip(),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "results_count": results_count,
        }

        # Filter hinzufuegen wenn vorhanden
        if filters:
            # Nur serialisierbare Filter behalten
            safe_filters = {}
            for k, v in filters.items():
                if v is not None:
                    if hasattr(v, 'value'):  # Enum
                        safe_filters[k] = v.value
                    elif hasattr(v, 'isoformat'):  # datetime
                        safe_filters[k] = v.isoformat()
                    elif isinstance(v, (str, int, float, bool, list)):
                        safe_filters[k] = v
            if safe_filters:
                search_entry["filters"] = safe_filters

        # Am Anfang der Liste einfuegen (LPUSH)
        await redis_manager._redis.lpush(key, json.dumps(search_entry))

        # Liste auf max_history_size begrenzen (LTRIM)
        await redis_manager._redis.ltrim(key, 0, max_history_size - 1)

        # TTL setzen (30 Tage)
        await redis_manager._redis.expire(key, 30 * 24 * 60 * 60)

        logger.debug(
            "search_saved_to_history",
            user_id=user_id,
            query=query[:50],
            results_count=results_count
        )

        return True

    except Exception as e:
        logger.warning("save_search_history_error", **safe_error_log(e))
        return False


@router.get(
    "/trending",
    summary="Trending Suchbegriffe und Tags",
    description="Gibt die beliebtesten Suchbegriffe und Tags der letzten Tage zurueck."
)
async def get_trending_searches(
    days: int = Query(7, ge=1, le=30, description="Analysezeitraum in Tagen"),
    limit: int = Query(10, ge=1, le=50, description="Maximale Anzahl pro Kategorie"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    search_service: SearchService = Depends(get_search_service_dep)
) -> dict:
    """
    Trending Suchbegriffe und Tags.

    Kombiniert:
    - Haeufigste Suchbegriffe (aus Search Analytics)
    - Beliebteste Tags (aus Dokumenten)
    - Neue Dokumente (letzten 7 Tage)

    Nuetzlich fuer:
    - Dashboard-Widgets
    - Suchvorschlaege
    - Content Discovery
    """
    from datetime import datetime, timedelta, timezone
    from sqlalchemy import select, func, desc
    from app.db.models import Document, Tag, document_tags

    result = {
        "period_days": days,
        "trending_queries": [],
        "trending_tags": [],
        "recent_activity": {}
    }

    try:
        # 1. Trending Suchbegriffe aus Redis (letzte Suchen aggregieren)
        from app.core.redis_state import RedisStateManager
        redis_manager = RedisStateManager.get_instance()
        await redis_manager._ensure_connection()

        # Alle User-Histories aggregieren (nur eigene fuer Privacy)
        key = f"search_history:{current_user.id}"
        raw_searches = await redis_manager._redis.lrange(key, 0, 100)

        import json
        from collections import Counter
        query_counter = Counter()
        cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=days)

        for raw in raw_searches:
            try:
                search_data = json.loads(raw)
                timestamp = datetime.fromisoformat(search_data.get("timestamp", ""))
                if timestamp >= cutoff:
                    query = search_data.get("query", "").lower().strip()
                    if query and len(query) >= 2:
                        query_counter[query] += 1
            except (json.JSONDecodeError, ValueError):
                continue

        result["trending_queries"] = [
            {"query": q, "count": c}
            for q, c in query_counter.most_common(limit)
        ]

    except Exception as e:
        logger.warning("trending_queries_error", **safe_error_log(e))
        result["trending_queries"] = []

    try:
        # 2. Trending Tags (meist verwendete Tags in den letzten N Tagen)
        cutoff_date = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=days)

        tag_query = (
            select(Tag.name, func.count(document_tags.c.document_id).label("count"))
            .select_from(Tag)
            .join(document_tags, Tag.id == document_tags.c.tag_id)
            .join(Document, Document.id == document_tags.c.document_id)
            .where(
                Document.owner_id == current_user.id,
                Document.created_at >= cutoff_date
            )
            .group_by(Tag.name)
            .order_by(desc("count"))
            .limit(limit)
        )
        tag_result = await db.execute(tag_query)
        tag_rows = tag_result.all()

        result["trending_tags"] = [
            {"tag": row[0], "count": row[1]}
            for row in tag_rows
        ]

    except Exception as e:
        logger.warning("trending_tags_error", **safe_error_log(e))
        result["trending_tags"] = []

    try:
        # 3. Recent Activity Stats
        cutoff_date = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=days)

        # Neue Dokumente
        new_docs_result = await db.execute(
            select(func.count(Document.id))
            .where(
                Document.owner_id == current_user.id,
                Document.created_at >= cutoff_date
            )
        )
        new_docs_count = new_docs_result.scalar() or 0

        # Verarbeitete Dokumente (mit OCR-Text)
        processed_result = await db.execute(
            select(func.count(Document.id))
            .where(
                Document.owner_id == current_user.id,
                Document.created_at >= cutoff_date,
                Document.extracted_text.isnot(None)
            )
        )
        processed_count = processed_result.scalar() or 0

        result["recent_activity"] = {
            "new_documents": new_docs_count,
            "processed_documents": processed_count,
            "period_start": cutoff_date.isoformat(),
            "period_end": datetime.now(timezone.utc).isoformat()
        }

    except Exception as e:
        logger.warning("recent_activity_error", **safe_error_log(e))
        result["recent_activity"] = {}

    logger.debug(
        "trending_retrieved",
        user_id=str(current_user.id),
        queries=len(result["trending_queries"]),
        tags=len(result["trending_tags"])
    )

    return result


@router.get(
    "/stats",
    summary="Suchstatistiken",
    description="Gibt Statistiken über die Dokumentensammlung zurück."
)
async def get_search_stats(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> dict:
    """
    Statistiken über die Dokumentensammlung.

    Enthält:
    - Gesamtanzahl Dokumente
    - Dokumente nach Status
    - Dokumente nach Typ
    - Durchschnittliche OCR-Konfidenz
    """
    try:
        from sqlalchemy import select, func
        from app.db.models import Document


        # Gesamtanzahl
        total_result = await db.execute(
            select(func.count(Document.id)).where(Document.owner_id == current_user.id)
        )
        total = total_result.scalar() or 0

        # Nach Status
        status_result = await db.execute(
            select(Document.status, func.count(Document.id))
            .where(Document.owner_id == current_user.id)
            .group_by(Document.status)
        )
        by_status = {row[0]: row[1] for row in status_result.all()}

        # Durchschnittliche Konfidenz
        confidence_result = await db.execute(
            select(func.avg(Document.ocr_confidence))
            .where(
                Document.owner_id == current_user.id,
                Document.ocr_confidence.isnot(None)
            )
        )
        avg_confidence = confidence_result.scalar()

        # Dokumente mit Text
        text_result = await db.execute(
            select(func.count(Document.id))
            .where(
                Document.owner_id == current_user.id,
                Document.extracted_text.isnot(None),
                func.length(Document.extracted_text) > 0
            )
        )
        with_text = text_result.scalar() or 0

        return {
            "total_documents": total,
            "by_status": by_status,
            "average_confidence": round(avg_confidence, 4) if avg_confidence else None,
            "documents_with_text": with_text,
            "documents_without_text": total - with_text
        }

    except OperationalError as e:
        logger.error("search_stats_db_connection_error", error_type="OperationalError", **safe_error_log(e))
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Datenbankverbindung nicht verfuegbar"
        )
    except SQLAlchemyError as e:
        logger.error("search_stats_db_error", error_type=type(e).__name__, **safe_error_log(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Datenbankfehler beim Abrufen der Statistiken"
        )
    except Exception as e:
        logger.error("search_stats_error", error_type=type(e).__name__, **safe_error_log(e), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Fehler beim Abrufen der Statistiken"
        )


# =============================================================================
# Position-Weighted Click Analytics
# =============================================================================

@router.get(
    "/analytics/weighted-ctr",
    summary="Gewichtete CTR-Statistiken",
    description="Gibt Position-Weighted Click-Through-Rate Statistiken zurueck."
)
async def get_weighted_ctr_analytics(
    days: int = Query(30, ge=1, le=365, description="Analysezeitraum in Tagen"),
    min_searches: int = Query(5, ge=1, le=100, description="Mindestanzahl Suchen pro Query"),
    limit: int = Query(20, ge=1, le=100, description="Maximale Anzahl Ergebnisse pro Kategorie"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> dict:
    """
    Position-Weighted CTR Statistiken.

    Diese Metrik bewertet die Suchqualitaet basierend auf Klick-Positionen:

    **Gewichtungsformel:**
    - Position 1: Gewicht 1.0 (volle Relevanz)
    - Position 5: Gewicht ~0.55 (mittlere Relevanz)
    - Position 10: Gewicht ~0.26 (niedrige Relevanz)
    - Formel: exp(-0.15 * (position - 1))

    **Rueckgabe:**
    - `overall`: Gesamtstatistiken (CTR, weighted CTR, avg. erste Klickposition)
    - `by_search_type`: Aufschluesselung nach Suchtyp (fts, semantic, hybrid)
    - `top_queries_by_weighted_ctr`: Queries mit hoechster gewichteter CTR
    - `low_performing_queries`: Queries mit niedriger CTR (Verbesserungspotenzial)
    - `position_distribution`: Verteilung der Klicks nach Position

    **Anwendungsfaelle:**
    - Identifikation von Queries mit schlechtem Ranking
    - Vergleich der Suchtypen (FTS vs. Hybrid vs. Semantic)
    - Messung der Suchqualitaet ueber Zeit
    """
    try:
        analytics_service = get_search_analytics_service()

        result = await analytics_service.get_weighted_ctr_statistics(
            db=db,
            days=days,
            min_searches=min_searches,
            limit=limit,
        )

        logger.info(
            "weighted_ctr_analytics_retrieved",
            user_id=str(current_user.id),
            period_days=days,
            total_searches=result.get("overall", {}).get("total_searches", 0),
        )

        return result

    except OperationalError as e:
        logger.error("weighted_ctr_db_connection_error", error_type="OperationalError", **safe_error_log(e))
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Datenbankverbindung nicht verfuegbar"
        )
    except SQLAlchemyError as e:
        logger.error("weighted_ctr_db_error", error_type=type(e).__name__, **safe_error_log(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Datenbankfehler beim Abrufen der Weighted CTR Statistiken"
        )
    except Exception as e:
        logger.error("weighted_ctr_error", error_type=type(e).__name__, **safe_error_log(e), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Fehler beim Abrufen der Weighted CTR Statistiken"
        )
