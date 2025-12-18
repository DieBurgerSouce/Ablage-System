"""Such-Service fuer Volltextsuche und semantische Suche.

Kombiniert PostgreSQL Full-Text Search (FTS) mit pgvector semantischer Suche.
Unterstuetzt Hybrid-Suche mit Reciprocal Rank Fusion.
"""

from typing import List, Optional, Dict, Any, Tuple, Set
from datetime import datetime
from functools import lru_cache
from uuid import UUID
import time
import math
import hashlib
import json

import structlog
from sqlalchemy import select, func, text, and_, or_, desc, asc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import Document, Tag, document_tags, DocumentAccess
from app.db.schemas import (
    SearchType, SearchFilters, SearchResultItem, SearchResponse,
    SimilarDocumentItem, SortField, SortOrder, DocumentType, ProcessingStatus
)
from app.core.config import settings
from app.core.redis_state import RedisStateManager
from app.services.embedding_service import get_embedding_service
from app.services.search_metrics import get_search_metrics
from app.services.german_compound_splitter import (
    GermanCompoundSplitter,
    get_compound_splitter,
    split_for_search,
    expand_umlaut_variants,
    expand_query_with_umlauts
)
from app.services.reranker_service import get_reranker_service, RerankerService

logger = structlog.get_logger(__name__)

# Konstanten fuer Suche
RRF_K_CONSTANT = 60  # Standard RRF Fusion Konstante (bewahrt fuer Ranking-Stabilitaet)
HYBRID_EXPANSION_FACTOR = 3  # Faktor fuer erweiterte Ergebnisse bei Hybrid-Suche


class SearchService:
    """Service fuer Dokumentensuche.

    Bietet drei Suchmodi:
    - FTS (Volltext): PostgreSQL tsvector mit deutschen Wortstaemmen
    - Semantic: pgvector Cosine-Aehnlichkeit mit multilingual-e5-large
    - Hybrid: Kombination beider Methoden via Reciprocal Rank Fusion
    """

    def __init__(self) -> None:
        self.embedding_service = get_embedding_service()
        self.fts_weight = settings.HYBRID_FTS_WEIGHT
        self.semantic_weight = settings.HYBRID_SEMANTIC_WEIGHT
        self.similarity_threshold = settings.SEMANTIC_SIMILARITY_THRESHOLD
        # Cache settings
        self._cache_enabled = settings.SEARCH_CACHE_ENABLED
        self._cache_ttl = settings.SEARCH_CACHE_TTL
        self._embedding_cache_ttl = settings.SEARCH_EMBEDDING_CACHE_TTL
        self._similar_cache_ttl = settings.SEARCH_SIMILAR_CACHE_TTL
        self._redis_manager: Optional[RedisStateManager] = None

        # German Compound Splitter (für verbesserte Suche)
        self._compound_splitting_enabled = settings.COMPOUND_SPLITTING_ENABLED
        self._compound_splitter: Optional[GermanCompoundSplitter] = None

        # Reranker fuer verbesserte Relevanz (BGE-Reranker GPU/CPU Dual-Stack)
        self._reranker: Optional[RerankerService] = None
        self._rerank_enabled = settings.RAG_RERANK_ENABLED
        self._rerank_top_k = settings.RAG_RERANK_TOP_K

        # Adaptive RRF-Gewichte (Query-laengenabhaengig)
        self._adaptive_weights_enabled = settings.ADAPTIVE_RRF_WEIGHTS_ENABLED

    async def _get_redis(self) -> RedisStateManager:
        """Lazy-load Redis connection."""
        if self._redis_manager is None:
            self._redis_manager = RedisStateManager.get_instance()
            await self._redis_manager.connect()
        return self._redis_manager

    def _generate_search_cache_key(
        self,
        query: str,
        user_id: UUID,
        search_type: SearchType,
        filters: Optional[SearchFilters],
        page: int,
        per_page: int,
        sort_by: SortField,
        sort_order: SortOrder
    ) -> str:
        """Generiert einen eindeutigen Cache-Key fuer Suchanfragen."""
        # Hash der Query
        query_hash = hashlib.sha256(query.encode()).hexdigest()[:12]

        # Hash der Filter (wenn vorhanden)
        filter_hash = "nofilter"
        if filters:
            filter_dict = {
                "type": filters.document_type.value if filters.document_type else None,
                "status": filters.status.value if filters.status else None,
                "from": filters.date_from.isoformat() if filters.date_from else None,
                "to": filters.date_to.isoformat() if filters.date_to else None,
                "tags": sorted(filters.tags) if filters.tags else None,
                "conf": filters.confidence_min,
                "lang": filters.language,
                "emb": filters.has_embedding
            }
            filter_json = json.dumps(filter_dict, sort_keys=True)
            filter_hash = hashlib.sha256(filter_json.encode()).hexdigest()[:8]

        return f"search:{search_type.value}:{user_id}:{query_hash}:{page}:{per_page}:{sort_by.value}:{sort_order.value}:{filter_hash}"

    def _generate_similar_cache_key(
        self,
        document_id: UUID,
        user_id: UUID,
        limit: int,
        threshold: float
    ) -> str:
        """Generiert Cache-Key fuer aehnliche Dokumente."""
        return f"search:similar:{user_id}:{document_id}:{limit}:{threshold}"

    def _generate_embedding_cache_key(self, query: str) -> str:
        """Generiert Cache-Key fuer Query-Embeddings."""
        query_hash = hashlib.sha256(query.encode()).hexdigest()[:16]
        return f"search:embedding:{query_hash}"

    def _get_compound_splitter(self) -> Optional[GermanCompoundSplitter]:
        """Lazy-load Compound Splitter."""
        if self._compound_splitter is None and self._compound_splitting_enabled:
            try:
                self._compound_splitter = GermanCompoundSplitter(
                    min_part_length=settings.COMPOUND_MIN_PART_LENGTH
                )
                logger.info(
                    "compound_splitter_loaded",
                    min_part_length=settings.COMPOUND_MIN_PART_LENGTH
                )
            except Exception as e:
                logger.warning("compound_splitter_load_error", error=str(e))
                self._compound_splitting_enabled = False
        return self._compound_splitter

    def _expand_query_with_compounds(self, query: str) -> Tuple[str, List[str]]:
        """Erweitert eine Suchanfrage mit Compound-Word-Teilen.

        Beispiel: "Bundesfinanzministerium" -> auch nach "Bundes", "Finanz", "Ministerium" suchen

        Args:
            query: Originale Suchanfrage

        Returns:
            Tuple von (erweiterte_query_string, liste_der_zusaetzlichen_terms)
        """
        if not self._compound_splitting_enabled:
            return query, []

        splitter = self._get_compound_splitter()
        if not splitter:
            return query, []

        # Alle Woerter in der Query
        words = query.split()
        all_terms: Set[str] = set(words)
        additional_terms: List[str] = []

        for word in words:
            # Nur Woerter mit mindestens 6 Zeichen (potentielle Komposita)
            if len(word) >= 6:
                search_terms = splitter.split_for_search(word)
                for term in search_terms:
                    if term.lower() not in {w.lower() for w in all_terms}:
                        all_terms.add(term)
                        additional_terms.append(term)

        if additional_terms:
            logger.debug(
                "query_expanded_with_compounds",
                original=query,
                additional_terms=additional_terms[:5],  # Max 5 fuer Logging
                total_additional=len(additional_terms)
            )

        # Erweiterte Query: Original + OR-verknuepfte Zusatzterms
        if additional_terms:
            expanded_query = query + " " + " ".join(additional_terms[:10])  # Max 10 Zusatzterms
            return expanded_query, additional_terms
        return query, []

    def _get_adaptive_weights(self, query: str) -> Tuple[float, float]:
        """Waehlt RRF-Gewichte basierend auf Query-Laenge.

        Kurze Queries (1-2 Woerter): 50/50 - Benoetigen sowohl exakte als auch semantische Matches
        Mittlere Queries (3-5 Woerter): 30/70 - Standard, semantisch hilft bei Kontext
        Lange Queries (6+ Woerter): 20/80 - Lange Queries sind semantischer Natur

        Args:
            query: Suchanfrage

        Returns:
            Tuple von (fts_weight, semantic_weight)
        """
        if not self._adaptive_weights_enabled:
            return self.fts_weight, self.semantic_weight

        word_count = len(query.split())

        if word_count <= 2:  # Kurze Query
            fts_weight = settings.HYBRID_WEIGHTS_SHORT_FTS
            semantic_weight = settings.HYBRID_WEIGHTS_SHORT_SEMANTIC
            weight_category = "short"
        elif word_count <= 5:  # Mittlere Query
            fts_weight = settings.HYBRID_WEIGHTS_MEDIUM_FTS
            semantic_weight = settings.HYBRID_WEIGHTS_MEDIUM_SEMANTIC
            weight_category = "medium"
        else:  # Lange Query
            fts_weight = settings.HYBRID_WEIGHTS_LONG_FTS
            semantic_weight = settings.HYBRID_WEIGHTS_LONG_SEMANTIC
            weight_category = "long"

        logger.debug(
            "adaptive_weights_selected",
            query_words=word_count,
            category=weight_category,
            fts_weight=fts_weight,
            semantic_weight=semantic_weight
        )

        return fts_weight, semantic_weight

    def _validate_embedding(self, embedding: List[float]) -> bool:
        """Validiert dass ein Embedding nur finite numerische Werte enthaelt.

        Args:
            embedding: Liste von Embedding-Werten

        Returns:
            True wenn alle Werte valide sind, False sonst
        """
        return all(isinstance(x, (int, float)) and math.isfinite(x) for x in embedding)

    async def invalidate_user_search_cache(self, user_id: UUID, reason: str = "user_update") -> int:
        """Invalidiert alle Such-Caches fuer einen Benutzer.

        Sollte aufgerufen werden wenn Dokumente erstellt, aktualisiert oder
        geloescht werden, da Suchergebnisse nicht mehr aktuell sind.

        Args:
            user_id: Benutzer-ID
            reason: Grund der Invalidierung

        Returns:
            Anzahl der invalidierten Cache-Eintraege
        """
        if not self._cache_enabled:
            return 0

        try:
            redis = await self._get_redis()
            # Pattern fuer alle Benutzer-Caches: search:*:{user_id}:*
            pattern = f"search:*:{user_id}:*"
            count = await redis.invalidate_cache(pattern)

            # Metriken erfassen
            metrics = get_search_metrics()
            metrics.record_cache_invalidation(reason=reason, count=count)

            logger.info(
                "user_search_cache_invalidated",
                user_id=str(user_id),
                invalidated_count=count
            )
            return count
        except Exception as e:
            logger.warning(
                "cache_invalidation_error",
                user_id=str(user_id),
                error=str(e)
            )
            return 0

    async def invalidate_document_cache(
        self,
        document_id: UUID,
        user_id: UUID,
        reason: str = "document_update"
    ) -> int:
        """Invalidiert Caches fuer ein spezifisches Dokument.

        Invalidiert:
        - Aehnliche-Dokumente-Cache fuer dieses Dokument
        - Alle Such-Caches des Benutzers (da Ergebnisse betroffen sein koennten)

        Args:
            document_id: Dokument-ID
            user_id: Benutzer-ID
            reason: Grund der Invalidierung

        Returns:
            Anzahl der invalidierten Cache-Eintraege
        """
        if not self._cache_enabled:
            return 0

        total_invalidated = 0
        try:
            redis = await self._get_redis()
            metrics = get_search_metrics()

            # 1. Aehnliche-Dokumente-Cache invalidieren
            similar_pattern = f"search:similar:*:{document_id}:*"
            count = await redis.invalidate_cache(similar_pattern)
            total_invalidated += count

            # 2. Benutzer-Such-Caches invalidieren (mit Reason)
            user_count = await self.invalidate_user_search_cache(user_id, reason=reason)
            total_invalidated += user_count

            logger.info(
                "document_cache_invalidated",
                document_id=str(document_id),
                user_id=str(user_id),
                total_invalidated=total_invalidated
            )
            return total_invalidated
        except Exception as e:
            logger.warning(
                "document_cache_invalidation_error",
                document_id=str(document_id),
                error=str(e)
            )
            return 0

    async def invalidate_all_search_cache(self) -> int:
        """Invalidiert alle Such-Caches (Admin-Funktion).

        Returns:
            Anzahl der invalidierten Cache-Eintraege
        """
        if not self._cache_enabled:
            return 0

        try:
            redis = await self._get_redis()
            count = await redis.invalidate_cache("search:*")

            # Metriken erfassen
            metrics = get_search_metrics()
            metrics.record_cache_invalidation(reason="admin", count=count)

            logger.info("all_search_cache_invalidated", invalidated_count=count)
            return count
        except Exception as e:
            logger.warning("cache_invalidation_error", error=str(e))
            return 0

    async def search(
        self,
        db: AsyncSession,
        query: str,
        user_id: UUID,
        search_type: SearchType = SearchType.HYBRID,
        filters: Optional[SearchFilters] = None,
        page: int = 1,
        per_page: int = 20,
        sort_by: SortField = SortField.RELEVANCE,
        sort_order: SortOrder = SortOrder.DESC,
        highlight: bool = True,
        similarity_threshold: Optional[float] = None,
        skip_cache: bool = False,
        rerank: bool = True
    ) -> SearchResponse:
        """Dokumente durchsuchen.

        Args:
            db: Datenbank-Session
            query: Suchbegriff
            user_id: Benutzer-ID fuer Zugriffsfilter
            search_type: Art der Suche (fts, semantic, hybrid)
            filters: Optionale Filter
            page: Seitennummer (1-basiert)
            per_page: Ergebnisse pro Seite
            sort_by: Sortierfeld
            sort_order: Sortierreihenfolge
            highlight: Text-Highlighting aktivieren
            similarity_threshold: Min. Aehnlichkeit fuer semantische Suche
            skip_cache: Cache fuer diese Anfrage umgehen
            rerank: Ergebnisse mit BGE-Reranker neu sortieren (verbessert Relevanz)

        Returns:
            SearchResponse mit Ergebnissen und Metadaten
        """
        start_time = time.time()
        threshold = similarity_threshold or self.similarity_threshold

        # Cache-Key generieren
        cache_key = self._generate_search_cache_key(
            query, user_id, search_type, filters, page, per_page, sort_by, sort_order
        )

        # Cache pruefen (wenn aktiviert)
        metrics = get_search_metrics()
        cache_hit = False

        if self._cache_enabled and not skip_cache:
            try:
                redis = await self._get_redis()
                cached = await redis.get_cached_result(cache_key)
                if cached:
                    cache_hit = True
                    metrics.record_cache_hit()
                    logger.info(
                        "search_cache_hit",
                        cache_key=cache_key[:50],
                        query=query[:50]
                    )
                    # SearchResponse aus Cache rekonstruieren
                    cached["search_type"] = SearchType(cached["search_type"])
                    cached["results"] = [
                        SearchResultItem(**r) for r in cached.get("results", [])
                    ]
                    # Metriken fuer Cache-Hit erfassen
                    took_ms = int((time.time() - start_time) * 1000)
                    metrics.record_search(
                        search_type=search_type.value,
                        duration_seconds=(time.time() - start_time),
                        results_count=cached.get("total", 0),
                        cached=True,
                        success=True,
                    )
                    return SearchResponse(**cached)
                else:
                    metrics.record_cache_miss()
            except Exception as e:
                logger.warning("search_cache_error", error=str(e), cache_key=cache_key[:50])

        # Query erweitern: Compound-Splits + Umlaut-Varianten (fuer FTS und Hybrid)
        expanded_query = query
        compound_terms: List[str] = []
        umlaut_terms: List[str] = []
        if search_type in (SearchType.FTS, SearchType.HYBRID):
            # 1. Umlaut-Varianten expandieren (z.B. "Größe" -> auch "Groesse", "Grosse")
            expanded_query, umlaut_terms = expand_query_with_umlauts(query)
            # 2. Compound-Splits hinzufuegen (z.B. "Finanzamt" -> "Finanz", "Amt")
            expanded_query, compound_terms = self._expand_query_with_compounds(expanded_query)

        logger.info(
            "search_started",
            query=query[:100],
            expanded_query=expanded_query[:100] if expanded_query != query else None,
            compound_terms_count=len(compound_terms),
            umlaut_terms_count=len(umlaut_terms),
            search_type=search_type.value,
            user_id=str(user_id)
        )

        if search_type == SearchType.FTS:
            results, total = await self._search_fts(
                db, expanded_query, user_id, filters, page, per_page, highlight
            )
        elif search_type == SearchType.SEMANTIC:
            results, total = await self._search_semantic(
                db, query, user_id, filters, page, per_page, threshold
            )
        else:  # HYBRID
            results, total = await self._search_hybrid(
                db, expanded_query, user_id, filters, page, per_page, highlight, threshold, rerank
            )

        # Sortierung anwenden (ausser bei Relevanz - schon sortiert)
        if sort_by != SortField.RELEVANCE:
            results = self._sort_results(results, sort_by, sort_order)

        took_ms = int((time.time() - start_time) * 1000)
        total_pages = math.ceil(total / per_page) if total > 0 else 0

        logger.info(
            "search_completed",
            results_count=len(results),
            total=total,
            took_ms=took_ms
        )

        # Metriken erfassen
        metrics.record_search(
            search_type=search_type.value,
            duration_seconds=took_ms / 1000.0,
            results_count=total,
            cached=False,
            success=True,
        )

        # Filter-Nutzung erfassen
        if filters:
            metrics.record_filters_from_request(
                document_type=filters.document_type is not None,
                date=filters.date_from is not None or filters.date_to is not None,
                status=filters.status is not None,
                tags=bool(filters.tags),
                confidence=filters.confidence_min is not None,
                language=filters.language is not None,
                embedding=filters.has_embedding is not None,
            )

        response = SearchResponse(
            query=query,
            search_type=search_type,
            total=total,
            page=page,
            per_page=per_page,
            total_pages=total_pages,
            results=results,
            took_ms=took_ms,
            filters_applied=filters.model_dump(exclude_none=True) if filters else {}
        )

        # Ergebnis cachen (wenn aktiviert und Ergebnisse vorhanden)
        if self._cache_enabled and not skip_cache and total > 0:
            try:
                redis = await self._get_redis()
                # Response serialisieren (search_type zu string, results zu dicts)
                cache_data = response.model_dump()
                cache_data["search_type"] = search_type.value
                cache_data["results"] = [r.model_dump() for r in results]
                await redis.cache_result(cache_key, cache_data, ttl=self._cache_ttl)
                metrics.record_cache_store(success=True)
                logger.debug(
                    "search_cache_stored",
                    cache_key=cache_key[:50],
                    ttl=self._cache_ttl
                )
            except Exception as e:
                metrics.record_cache_store(success=False)
                logger.warning("search_cache_store_error", error=str(e))

        return response

    async def _search_fts(
        self,
        db: AsyncSession,
        query: str,
        user_id: UUID,
        filters: Optional[SearchFilters],
        page: int,
        per_page: int,
        highlight: bool
    ) -> Tuple[List[SearchResultItem], int]:
        """PostgreSQL Full-Text Search mit German Config und Field-Level Boosting."""
        offset = (page - 1) * per_page

        # Field-Level Boost-Werte aus Config
        filename_boost = settings.FTS_FIELD_BOOST_FILENAME
        orig_filename_boost = settings.FTS_FIELD_BOOST_ORIGINAL_FILENAME
        text_boost = settings.FTS_FIELD_BOOST_EXTRACTED_TEXT

        # Base query mit tsvector Suche und Field-Level Boosting
        # Inkludiert eigene UND geteilte Dokumente (via DocumentAccess)
        # Boosting: Treffer im Dateinamen ranken hoeher als im extrahierten Text
        fts_query = text("""
            WITH search_query AS (
                SELECT plainto_tsquery('german_text', :query) AS query
            ),
            accessible_docs AS (
                -- Eigene Dokumente
                SELECT document_id FROM (
                    SELECT id AS document_id FROM documents WHERE owner_id = :user_id
                ) owned
                UNION
                -- Geteilte Dokumente (nicht abgelaufen)
                SELECT document_id FROM document_access
                WHERE user_id = :user_id
                    AND (expires_at IS NULL OR expires_at > NOW())
            ),
            ranked_docs AS (
                SELECT
                    d.id,
                    d.filename,
                    d.original_filename,
                    d.document_type,
                    d.status,
                    d.created_at,
                    d.updated_at,
                    d.file_size,
                    d.page_count,
                    d.ocr_confidence,
                    d.owner_id,
                    d.extracted_text,
                    -- Field-Level Boosting: Filename-Treffer ranken hoeher
                    ts_rank_cd(d.search_vector, sq.query) *
                    CASE
                        WHEN lower(d.filename) LIKE '%' || lower(:raw_query) || '%'
                            THEN :filename_boost
                        WHEN lower(d.original_filename) LIKE '%' || lower(:raw_query) || '%'
                            THEN :orig_filename_boost
                        ELSE :text_boost
                    END AS fts_rank,
                    ts_headline('german_text', COALESCE(d.extracted_text, ''), sq.query,
                        'MaxWords=50, MinWords=25, StartSel=<mark>, StopSel=</mark>'
                    ) AS highlight
                FROM documents d, search_query sq
                WHERE d.id IN (SELECT document_id FROM accessible_docs)
                    AND d.search_vector @@ sq.query
                    {filters}
                ORDER BY fts_rank DESC
            )
            SELECT * FROM ranked_docs
            LIMIT :limit OFFSET :offset
        """.format(filters=self._build_filter_sql(filters)))

        # Count query (inkl. geteilte Dokumente)
        count_query = text("""
            WITH accessible_docs AS (
                SELECT id AS document_id FROM documents WHERE owner_id = :user_id
                UNION
                SELECT document_id FROM document_access
                WHERE user_id = :user_id
                    AND (expires_at IS NULL OR expires_at > NOW())
            )
            SELECT COUNT(*) FROM documents d,
                plainto_tsquery('german_text', :query) AS query
            WHERE d.id IN (SELECT document_id FROM accessible_docs)
                AND d.search_vector @@ query
                {filters}
        """.format(filters=self._build_filter_sql(filters)))

        # Extrahiere erstes Wort der Query fuer Filename-Matching (ohne Expansion)
        raw_query_first_word = query.split()[0] if query.split() else query

        params = {
            "query": query,
            "raw_query": raw_query_first_word,  # Fuer LIKE-Matching im Filename
            "user_id": str(user_id),
            "limit": per_page,
            "offset": offset,
            "filename_boost": filename_boost,
            "orig_filename_boost": orig_filename_boost,
            "text_boost": text_boost
        }
        params.update(self._get_filter_params(filters))

        # Execute queries
        result = await db.execute(fts_query, params)
        rows = result.fetchall()

        count_result = await db.execute(count_query, params)
        total = count_result.scalar() or 0

        # Tags laden
        doc_ids = [row.id for row in rows]
        tags_map = await self._load_tags_for_documents(db, doc_ids)

        # Ergebnisse konvertieren
        results = []
        for row in rows:
            results.append(SearchResultItem(
                document_id=row.id,
                filename=row.filename,
                original_filename=row.original_filename,
                document_type=DocumentType(row.document_type) if row.document_type else DocumentType.OTHER,
                status=ProcessingStatus(row.status),
                created_at=row.created_at,
                updated_at=row.updated_at,
                file_size=row.file_size or 0,
                page_count=row.page_count,
                ocr_confidence=row.ocr_confidence,
                score=min(row.fts_rank, 1.0),  # Normalisieren auf 0-1
                fts_rank=row.fts_rank,
                semantic_similarity=None,
                highlight=row.highlight if highlight else None,
                text_preview=self._truncate_text(row.extracted_text, 500) if not highlight else None,
                tags=tags_map.get(row.id, []),
                owner_id=row.owner_id
            ))

        return results, total

    async def _search_semantic(
        self,
        db: AsyncSession,
        query: str,
        user_id: UUID,
        filters: Optional[SearchFilters],
        page: int,
        per_page: int,
        threshold: float
    ) -> Tuple[List[SearchResultItem], int]:
        """Semantische Suche mit pgvector."""
        offset = (page - 1) * per_page

        # Query-Embedding generieren
        query_embedding = await self.embedding_service.generate_embedding_async(query, is_query=True)
        embedding_str = "[" + ",".join(str(x) for x in query_embedding) + "]"

        # Semantic search query (inkl. geteilte Dokumente)
        semantic_query = text("""
            WITH accessible_docs AS (
                SELECT id AS document_id FROM documents WHERE owner_id = :user_id
                UNION
                SELECT document_id FROM document_access
                WHERE user_id = :user_id
                    AND (expires_at IS NULL OR expires_at > NOW())
            ),
            semantic_results AS (
                SELECT
                    d.id,
                    d.filename,
                    d.original_filename,
                    d.document_type,
                    d.status,
                    d.created_at,
                    d.updated_at,
                    d.file_size,
                    d.page_count,
                    d.ocr_confidence,
                    d.owner_id,
                    d.extracted_text,
                    1 - (d.embedding <=> :embedding::vector) AS similarity
                FROM documents d
                WHERE d.id IN (SELECT document_id FROM accessible_docs)
                    AND d.embedding IS NOT NULL
                    AND 1 - (d.embedding <=> :embedding::vector) >= :threshold
                    {filters}
                ORDER BY d.embedding <=> :embedding::vector
            )
            SELECT * FROM semantic_results
            LIMIT :limit OFFSET :offset
        """.format(filters=self._build_filter_sql(filters)))

        # Count query (inkl. geteilte Dokumente)
        count_query = text("""
            WITH accessible_docs AS (
                SELECT id AS document_id FROM documents WHERE owner_id = :user_id
                UNION
                SELECT document_id FROM document_access
                WHERE user_id = :user_id
                    AND (expires_at IS NULL OR expires_at > NOW())
            )
            SELECT COUNT(*) FROM documents d
            WHERE d.id IN (SELECT document_id FROM accessible_docs)
                AND d.embedding IS NOT NULL
                AND 1 - (d.embedding <=> :embedding::vector) >= :threshold
                {filters}
        """.format(filters=self._build_filter_sql(filters)))

        params = {
            "embedding": embedding_str,
            "user_id": str(user_id),
            "threshold": threshold,
            "limit": per_page,
            "offset": offset
        }
        params.update(self._get_filter_params(filters))

        result = await db.execute(semantic_query, params)
        rows = result.fetchall()

        count_result = await db.execute(count_query, params)
        total = count_result.scalar() or 0

        # Tags laden
        doc_ids = [row.id for row in rows]
        tags_map = await self._load_tags_for_documents(db, doc_ids)

        # Ergebnisse konvertieren
        results = []
        for row in rows:
            results.append(SearchResultItem(
                document_id=row.id,
                filename=row.filename,
                original_filename=row.original_filename,
                document_type=DocumentType(row.document_type) if row.document_type else DocumentType.OTHER,
                status=ProcessingStatus(row.status),
                created_at=row.created_at,
                updated_at=row.updated_at,
                file_size=row.file_size or 0,
                page_count=row.page_count,
                ocr_confidence=row.ocr_confidence,
                score=row.similarity,
                fts_rank=None,
                semantic_similarity=row.similarity,
                highlight=None,
                text_preview=self._truncate_text(row.extracted_text, 500),
                tags=tags_map.get(row.id, []),
                owner_id=row.owner_id
            ))

        return results, total

    async def _search_hybrid(
        self,
        db: AsyncSession,
        query: str,
        user_id: UUID,
        filters: Optional[SearchFilters],
        page: int,
        per_page: int,
        highlight: bool,
        threshold: float,
        rerank: bool = True
    ) -> Tuple[List[SearchResultItem], int]:
        """Hybrid-Suche mit Reciprocal Rank Fusion (RRF) und optionalem Reranking."""
        # Adaptive Gewichte basierend auf Query-Laenge waehlen
        fts_weight, semantic_weight = self._get_adaptive_weights(query)

        # Beide Suchmethoden ausfuehren (mehr Ergebnisse holen fuer Fusion)
        expanded_limit = per_page * HYBRID_EXPANSION_FACTOR

        fts_results, _ = await self._search_fts(
            db, query, user_id, filters, 1, expanded_limit, highlight
        )
        semantic_results, _ = await self._search_semantic(
            db, query, user_id, filters, 1, expanded_limit, threshold
        )

        # RRF Score berechnen mit Standard-Konstante und adaptiven Gewichten
        k = RRF_K_CONSTANT
        scores: Dict[UUID, Dict[str, Any]] = {}

        # FTS Scores (mit adaptiver Gewichtung)
        for rank, result in enumerate(fts_results):
            doc_id = result.document_id
            rrf_score = fts_weight / (k + rank + 1)
            scores[doc_id] = {
                "result": result,
                "rrf_score": rrf_score,
                "fts_rank": rank + 1
            }

        # Semantic Scores hinzufuegen/kombinieren (mit adaptiver Gewichtung)
        for rank, result in enumerate(semantic_results):
            doc_id = result.document_id
            rrf_contribution = semantic_weight / (k + rank + 1)

            if doc_id in scores:
                scores[doc_id]["rrf_score"] += rrf_contribution
                scores[doc_id]["semantic_rank"] = rank + 1
                # Semantic similarity uebernehmen
                scores[doc_id]["result"].semantic_similarity = result.semantic_similarity
            else:
                result.fts_rank = None  # Nicht in FTS gefunden
                scores[doc_id] = {
                    "result": result,
                    "rrf_score": rrf_contribution,
                    "semantic_rank": rank + 1
                }

        # Nach RRF Score sortieren
        sorted_items = sorted(
            scores.values(),
            key=lambda x: x["rrf_score"],
            reverse=True
        )

        total = len(sorted_items)

        # Reranking mit BGE-Reranker (GPU/CPU Dual-Stack)
        if rerank and self._rerank_enabled and len(sorted_items) > 1:
            # Top-Kandidaten fuer Reranking (max 30 fuer Performance)
            rerank_candidates = [item["result"] for item in sorted_items[:30]]
            reranked_results = await self._rerank_results(query, rerank_candidates, per_page)

            if reranked_results:
                # Score normalisieren
                max_score = max(r.score for r in reranked_results) if reranked_results else 1.0
                for r in reranked_results:
                    r.score = r.score / max_score if max_score > 0 else r.score
                return reranked_results, total

        # Fallback: Pagination ohne Reranking
        offset = (page - 1) * per_page
        paginated = sorted_items[offset:offset + per_page]

        # Score normalisieren und Ergebnisse erstellen
        max_score = sorted_items[0]["rrf_score"] if sorted_items else 1.0
        results = []
        for item in paginated:
            result = item["result"]
            result.score = item["rrf_score"] / max_score  # Normalisieren auf 0-1
            results.append(result)

        return results, total

    async def find_similar_documents(
        self,
        db: AsyncSession,
        document_id: UUID,
        user_id: UUID,
        limit: int = 10,
        similarity_threshold: float = 0.6,
        exclude_same_type: bool = False,
        skip_cache: bool = False
    ) -> List[SimilarDocumentItem]:
        """Aehnliche Dokumente basierend auf Embedding-Aehnlichkeit finden."""
        start_time = time.time()
        metrics = get_search_metrics()

        # Cache-Key generieren
        cache_key = self._generate_similar_cache_key(
            document_id, user_id, limit, similarity_threshold
        )

        # Cache pruefen
        if self._cache_enabled and not skip_cache:
            try:
                redis = await self._get_redis()
                cached = await redis.get_cached_result(cache_key)
                if cached:
                    metrics.record_cache_hit()
                    logger.info("similar_cache_hit", document_id=str(document_id))
                    results = [SimilarDocumentItem(**item) for item in cached]
                    metrics.record_similar_documents(
                        count=len(results),
                        duration_seconds=(time.time() - start_time),
                        cached=True,
                        success=True,
                    )
                    return results
                else:
                    metrics.record_cache_miss()
            except Exception as e:
                logger.warning("similar_cache_error", error=str(e))

        # Embedding des Quelldokuments holen (eigenes oder geteiltes)
        # Prüfe ob Benutzer Zugriff hat (Owner oder via DocumentAccess)
        doc_query = text("""
            SELECT d.* FROM documents d
            WHERE d.id = :document_id
            AND (
                d.owner_id = :user_id
                OR d.id IN (
                    SELECT document_id FROM document_access
                    WHERE user_id = :user_id
                    AND (expires_at IS NULL OR expires_at > NOW())
                )
            )
        """)
        result = await db.execute(doc_query, {"document_id": str(document_id), "user_id": str(user_id)})
        source_row = result.first()

        if not source_row:
            logger.warning("document_not_found_or_no_access", document_id=str(document_id))
            return []

        # Lade das vollständige Document-Objekt
        doc_query = select(Document).where(Document.id == document_id)
        result = await db.execute(doc_query)
        source_doc = result.scalar_one_or_none()

        if not source_doc:
            logger.warning("document_not_found", document_id=str(document_id))
            return []

        if source_doc.embedding is None:
            logger.warning("document_has_no_embedding", document_id=str(document_id))
            return []

        # Validiere Embedding auf NaN/Inf-Werte
        if not self._validate_embedding(source_doc.embedding):
            logger.error(
                "invalid_embedding_values",
                document_id=str(document_id),
                message="Embedding enthaelt NaN oder Inf-Werte"
            )
            raise ValueError("Embedding enthaelt ungueltige Werte (NaN/Inf)")

        embedding_str = "[" + ",".join(str(x) for x in source_doc.embedding) + "]"

        # Aehnliche Dokumente suchen (inkl. geteilte Dokumente)
        type_filter = ""
        if exclude_same_type and source_doc.document_type:
            type_filter = "AND d.document_type != :source_type"

        similar_query = text(f"""
            WITH accessible_docs AS (
                SELECT id AS document_id FROM documents WHERE owner_id = :user_id
                UNION
                SELECT document_id FROM document_access
                WHERE user_id = :user_id
                    AND (expires_at IS NULL OR expires_at > NOW())
            )
            SELECT
                d.id AS document_id,
                d.filename,
                d.document_type,
                1 - (d.embedding <=> :embedding::vector) AS similarity,
                d.created_at,
                LEFT(d.extracted_text, 200) AS text_preview
            FROM documents d
            WHERE d.id IN (SELECT document_id FROM accessible_docs)
                AND d.id != :source_id
                AND d.embedding IS NOT NULL
                AND 1 - (d.embedding <=> :embedding::vector) >= :threshold
                {type_filter}
            ORDER BY d.embedding <=> :embedding::vector
            LIMIT :limit
        """)

        params = {
            "embedding": embedding_str,
            "user_id": str(user_id),
            "source_id": str(document_id),
            "threshold": similarity_threshold,
            "limit": limit
        }
        if exclude_same_type and source_doc.document_type:
            params["source_type"] = source_doc.document_type

        result = await db.execute(similar_query, params)
        rows = result.fetchall()

        results = [
            SimilarDocumentItem(
                document_id=row.document_id,
                filename=row.filename,
                document_type=DocumentType(row.document_type) if row.document_type else DocumentType.OTHER,
                similarity=row.similarity,
                created_at=row.created_at,
                text_preview=row.text_preview
            )
            for row in rows
        ]

        # Metriken erfassen
        metrics.record_similar_documents(
            count=len(results),
            duration_seconds=(time.time() - start_time),
            cached=False,
            success=True,
        )

        # Ergebnisse cachen
        if self._cache_enabled and not skip_cache and results:
            try:
                redis = await self._get_redis()
                cache_data = [r.model_dump() for r in results]
                await redis.cache_result(cache_key, cache_data, ttl=self._similar_cache_ttl)
                metrics.record_cache_store(success=True)
                logger.debug("similar_cache_stored", document_id=str(document_id))
            except Exception as e:
                metrics.record_cache_store(success=False)
                logger.warning("similar_cache_store_error", error=str(e))

        return results

    async def _load_tags_for_documents(
        self,
        db: AsyncSession,
        doc_ids: List[UUID]
    ) -> Dict[UUID, List[str]]:
        """Tags fuer mehrere Dokumente laden."""
        if not doc_ids:
            return {}

        query = text("""
            SELECT dt.document_id, t.name
            FROM document_tags dt
            JOIN tags t ON t.id = dt.tag_id
            WHERE dt.document_id = ANY(:doc_ids)
        """)

        result = await db.execute(query, {"doc_ids": [str(d) for d in doc_ids]})
        rows = result.fetchall()

        tags_map: Dict[UUID, List[str]] = {doc_id: [] for doc_id in doc_ids}
        for row in rows:
            tags_map[row.document_id].append(row.name)

        return tags_map

    def _build_filter_sql(self, filters: Optional[SearchFilters]) -> str:
        """SQL-Fragment fuer Filter generieren."""
        if not filters:
            return ""

        conditions = []

        if filters.document_type:
            conditions.append("AND d.document_type = :filter_type")

        if filters.status:
            conditions.append("AND d.status = :filter_status")

        if filters.date_from:
            conditions.append("AND d.created_at >= :filter_date_from")

        if filters.date_to:
            conditions.append("AND d.created_at <= :filter_date_to")

        if filters.confidence_min is not None:
            conditions.append("AND d.ocr_confidence >= :filter_confidence_min")

        if filters.has_embedding is not None:
            if filters.has_embedding:
                conditions.append("AND d.embedding IS NOT NULL")
            else:
                conditions.append("AND d.embedding IS NULL")

        if filters.language:
            conditions.append("AND d.detected_language = :filter_language")

        if filters.tags:
            # Subquery fuer Dokumente mit ALLEN angegebenen Tags
            conditions.append("""
                AND d.id IN (
                    SELECT dt.document_id
                    FROM document_tags dt
                    JOIN tags t ON t.id = dt.tag_id
                    WHERE t.name = ANY(:filter_tags)
                    GROUP BY dt.document_id
                    HAVING COUNT(DISTINCT t.name) = :filter_tags_count
                )
            """)

        return " ".join(conditions)

    def _get_filter_params(self, filters: Optional[SearchFilters]) -> Dict[str, Any]:
        """Parameter fuer Filter-SQL generieren."""
        if not filters:
            return {}

        params = {}

        if filters.document_type:
            params["filter_type"] = filters.document_type.value

        if filters.status:
            params["filter_status"] = filters.status.value

        if filters.date_from:
            params["filter_date_from"] = filters.date_from

        if filters.date_to:
            params["filter_date_to"] = filters.date_to

        if filters.confidence_min is not None:
            params["filter_confidence_min"] = filters.confidence_min

        if filters.language:
            params["filter_language"] = filters.language

        if filters.tags:
            params["filter_tags"] = filters.tags
            params["filter_tags_count"] = len(filters.tags)

        return params

    def _sort_results(
        self,
        results: List[SearchResultItem],
        sort_by: SortField,
        sort_order: SortOrder
    ) -> List[SearchResultItem]:
        """Ergebnisse sortieren."""
        reverse = sort_order == SortOrder.DESC

        sort_key_map = {
            SortField.CREATED_AT: lambda x: x.created_at,
            SortField.UPDATED_AT: lambda x: x.updated_at,
            SortField.FILENAME: lambda x: x.filename.lower(),
            SortField.FILE_SIZE: lambda x: x.file_size,
            SortField.OCR_CONFIDENCE: lambda x: x.ocr_confidence or 0,
            SortField.RELEVANCE: lambda x: x.score
        }

        key_func = sort_key_map.get(sort_by, lambda x: x.score)
        return sorted(results, key=key_func, reverse=reverse)

    def _truncate_text(self, text: Optional[str], max_length: int = 500) -> Optional[str]:
        """Text auf maximale Laenge kuerzen."""
        if not text:
            return None
        if len(text) <= max_length:
            return text
        return text[:max_length - 3] + "..."

    # ==================== Reranking ====================

    async def _rerank_results(
        self,
        query: str,
        results: List[SearchResultItem],
        top_k: int
    ) -> List[SearchResultItem]:
        """Rerankt Suchergebnisse mit BGE-Reranker (GPU/CPU Dual-Stack).

        Verwendet den lokalen RerankerService fuer integriertes Reranking:
        - Primaer: BGE-Reranker-v2-m3 (GPU, ~1GB VRAM)
        - Fallback: MiniLM Cross-Encoder (CPU, ~300MB RAM)

        Falls beide fehlschlagen: Original-Reihenfolge beibehalten.

        Args:
            query: Suchanfrage
            results: Liste von Suchergebnissen (nach RRF sortiert)
            top_k: Anzahl der zurueckzugebenden Ergebnisse

        Returns:
            Rerankte Liste von Suchergebnissen
        """
        if not results or not self._rerank_enabled:
            return results[:top_k]

        try:
            # Lazy-load Reranker
            if self._reranker is None:
                self._reranker = get_reranker_service()

            # Text fuer Reranking extrahieren (highlight oder text_preview)
            documents = []
            for r in results:
                # Priorisiere: highlight > text_preview > filename
                text = r.highlight or r.text_preview or r.filename
                # Auf max. 512 Zeichen beschraenken (Reranker-Limit)
                documents.append(text[:512] if text else "")

            # Async Reranking mit GPU/CPU Fallback
            reranked = await self._reranker.rerank_async(query, documents, top_k)

            # Ergebnisse mit Rerank-Scores aktualisieren und neu sortieren
            reranked_results = []
            for rr in reranked:
                original = results[rr.index]
                # Score mit Rerank-Score aktualisieren
                original.score = rr.score
                reranked_results.append(original)

            logger.info(
                "search_rerank_complete",
                input_count=len(results),
                output_count=len(reranked_results),
                top_k=top_k,
                backend="gpu" if self._reranker.get_stats().get("gpu_model_loaded", False) else "cpu"
            )

            return reranked_results

        except Exception as e:
            logger.warning(
                "search_rerank_failed",
                error=str(e),
                fallback="using_rrf_scores"
            )
            return results[:top_k]

    # ==================== Facets ====================

    async def get_facets(
        self,
        db: AsyncSession,
        user_id: UUID,
        facet_fields: List[str],
        filters: Optional[SearchFilters] = None
    ) -> Dict[str, Any]:
        """
        Berechnet Facetten fuer die Suchseite.

        Args:
            db: Datenbank-Session
            user_id: Benutzer-ID fuer Zugriffsfilter
            facet_fields: Felder fuer Facetten (z.B. ["document_type", "status", "tags"])
            filters: Optionale Filter (werden auf Facetten angewendet)

        Returns:
            Dict mit Facetten-Gruppen
        """
        from app.db.schemas import FacetGroup, FacetValue

        # Label-Mapping fuer deutsche UI
        field_labels = {
            "document_type": "Dokumenttyp",
            "status": "Status",
            "tags": "Tags",
            "ocr_backend_used": "OCR-Backend",
            "mime_type": "Dateityp",
            "language": "Sprache",
        }

        # Value-Labels fuer deutsche UI
        value_labels = {
            "document_type": {
                "invoice": "Rechnung",
                "contract": "Vertrag",
                "receipt": "Quittung",
                "form": "Formular",
                "letter": "Brief",
                "report": "Bericht",
                "other": "Sonstiges",
            },
            "status": {
                "pending": "Ausstehend",
                "queued": "In Warteschlange",
                "processing": "Verarbeitung",
                "completed": "Abgeschlossen",
                "failed": "Fehlgeschlagen",
                "cancelled": "Abgebrochen",
            },
        }

        facets: List[FacetGroup] = []

        # Basis-Query mit Benutzer-Filter
        base_conditions = [Document.owner_id == user_id]

        # Zusaetzliche Filter anwenden
        if filters:
            if filters.document_type:
                base_conditions.append(Document.document_type == filters.document_type.value)
            if filters.status:
                base_conditions.append(Document.status == filters.status.value)
            if filters.date_from:
                base_conditions.append(Document.created_at >= filters.date_from)
            if filters.date_to:
                base_conditions.append(Document.created_at <= filters.date_to)

        # Facet fuer jedes Feld berechnen
        for field in facet_fields:
            if field == "document_type":
                result = await db.execute(
                    select(Document.document_type, func.count(Document.id))
                    .where(and_(*base_conditions))
                    .group_by(Document.document_type)
                    .order_by(func.count(Document.id).desc())
                )
                rows = result.all()
                values = [
                    FacetValue(
                        value=row[0] or "other",
                        count=row[1],
                        label=value_labels.get("document_type", {}).get(row[0], row[0])
                    )
                    for row in rows if row[0]
                ]
                facets.append(FacetGroup(
                    field=field,
                    label=field_labels.get(field, field),
                    values=values,
                    total_distinct=len(values)
                ))

            elif field == "status":
                result = await db.execute(
                    select(Document.status, func.count(Document.id))
                    .where(and_(*base_conditions))
                    .group_by(Document.status)
                    .order_by(func.count(Document.id).desc())
                )
                rows = result.all()
                values = [
                    FacetValue(
                        value=row[0],
                        count=row[1],
                        label=value_labels.get("status", {}).get(row[0], row[0])
                    )
                    for row in rows if row[0]
                ]
                facets.append(FacetGroup(
                    field=field,
                    label=field_labels.get(field, field),
                    values=values,
                    total_distinct=len(values)
                ))

            elif field == "ocr_backend_used":
                result = await db.execute(
                    select(Document.ocr_backend_used, func.count(Document.id))
                    .where(and_(*base_conditions, Document.ocr_backend_used.isnot(None)))
                    .group_by(Document.ocr_backend_used)
                    .order_by(func.count(Document.id).desc())
                )
                rows = result.all()
                values = [
                    FacetValue(value=row[0], count=row[1], label=row[0].upper() if row[0] else None)
                    for row in rows if row[0]
                ]
                facets.append(FacetGroup(
                    field=field,
                    label=field_labels.get(field, field),
                    values=values,
                    total_distinct=len(values)
                ))

            elif field == "tags":
                # Join mit Tags-Tabelle
                result = await db.execute(
                    select(Tag.name, func.count(Document.id))
                    .select_from(Document)
                    .join(document_tags, Document.id == document_tags.c.document_id)
                    .join(Tag, Tag.id == document_tags.c.tag_id)
                    .where(and_(*base_conditions))
                    .group_by(Tag.name)
                    .order_by(func.count(Document.id).desc())
                    .limit(20)  # Top 20 Tags
                )
                rows = result.all()
                values = [
                    FacetValue(value=row[0], count=row[1])
                    for row in rows
                ]
                facets.append(FacetGroup(
                    field=field,
                    label=field_labels.get(field, field),
                    values=values,
                    total_distinct=len(values)
                ))

            elif field == "mime_type":
                result = await db.execute(
                    select(Document.mime_type, func.count(Document.id))
                    .where(and_(*base_conditions))
                    .group_by(Document.mime_type)
                    .order_by(func.count(Document.id).desc())
                )
                rows = result.all()
                values = [
                    FacetValue(value=row[0], count=row[1])
                    for row in rows if row[0]
                ]
                facets.append(FacetGroup(
                    field=field,
                    label=field_labels.get(field, field),
                    values=values,
                    total_distinct=len(values)
                ))

        # Gesamtanzahl der Dokumente
        total_result = await db.execute(
            select(func.count(Document.id)).where(and_(*base_conditions))
        )
        total_documents = total_result.scalar() or 0

        logger.debug(
            "facets_calculated",
            user_id=str(user_id),
            fields=facet_fields,
            total_documents=total_documents
        )

        return {
            "facets": facets,
            "total_documents": total_documents
        }

    # ==================== Suggestions ====================

    async def get_suggestions(
        self,
        db: AsyncSession,
        user_id: UUID,
        query: str,
        limit: int = 10
    ) -> Dict[str, Any]:
        """
        Autovervollstaendigung fuer Suchanfragen.

        Sucht in:
        - Dokumentnamen
        - Tags
        - Extrahiertem Text (Schlagwoerter)

        Args:
            db: Datenbank-Session
            user_id: Benutzer-ID fuer Zugriffsfilter
            query: Suchbegriff (mind. 2 Zeichen)
            limit: Maximale Anzahl Vorschlaege

        Returns:
            Dict mit Vorschlaegen
        """
        from app.db.schemas import SuggestItem

        if len(query) < 2:
            return {"query": query, "suggestions": [], "total": 0}

        suggestions: List[SuggestItem] = []
        query_lower = query.lower()
        query_pattern = f"%{query_lower}%"

        # 1. Dokumentnamen durchsuchen
        doc_result = await db.execute(
            select(Document.id, Document.original_filename, Document.filename)
            .where(
                Document.owner_id == user_id,
                or_(
                    func.lower(Document.original_filename).like(query_pattern),
                    func.lower(Document.filename).like(query_pattern)
                )
            )
            .order_by(Document.created_at.desc())
            .limit(5)
        )
        doc_rows = doc_result.all()

        for doc_id, orig_name, name in doc_rows:
            display_name = orig_name or name
            # Highlight erstellen
            highlight = self._create_highlight(display_name, query)
            suggestions.append(SuggestItem(
                text=display_name,
                type="document",
                score=1.0,
                document_id=doc_id,
                highlight=highlight
            ))

        # 2. Tags durchsuchen
        tag_result = await db.execute(
            select(Tag.name, func.count(document_tags.c.document_id).label("doc_count"))
            .select_from(Tag)
            .join(document_tags, Tag.id == document_tags.c.tag_id)
            .join(Document, Document.id == document_tags.c.document_id)
            .where(
                Document.owner_id == user_id,
                func.lower(Tag.name).like(query_pattern)
            )
            .group_by(Tag.name)
            .order_by(desc("doc_count"))
            .limit(5)
        )
        tag_rows = tag_result.all()

        for tag_name, doc_count in tag_rows:
            highlight = self._create_highlight(tag_name, query)
            suggestions.append(SuggestItem(
                text=tag_name,
                type="tag",
                score=0.9,
                highlight=highlight
            ))

        # 3. Häufige Wörter aus extrahiertem Text (vereinfacht)
        # Suche in FTS-Vektor nach passenden Begriffen
        try:
            text_result = await db.execute(
                text("""
                    SELECT DISTINCT word
                    FROM (
                        SELECT unnest(string_to_array(
                            regexp_replace(lower(extracted_text), '[^a-zäöüß ]+', ' ', 'g'),
                            ' '
                        )) as word
                        FROM documents
                        WHERE owner_id = :user_id
                        AND extracted_text IS NOT NULL
                        AND length(extracted_text) > 100
                        LIMIT 1000
                    ) words
                    WHERE word LIKE :pattern
                    AND length(word) > 3
                    LIMIT 5
                """),
                {"user_id": str(user_id), "pattern": query_pattern}
            )
            text_rows = text_result.all()

            for (word,) in text_rows:
                # Nur hinzufügen, wenn nicht schon als Dokument/Tag vorhanden
                if not any(s.text.lower() == word for s in suggestions):
                    highlight = self._create_highlight(word, query)
                    suggestions.append(SuggestItem(
                        text=word,
                        type="term",
                        score=0.7,
                        highlight=highlight
                    ))
        except Exception as e:
            # Log at WARNING for unexpected failures (schema issues, etc.)
            # SQLite limitation is expected and harmless, but other errors need visibility
            logger.warning("text_suggest_failed", error=str(e), error_type=type(e).__name__)

        # Nach Score sortieren und limitieren
        suggestions.sort(key=lambda x: x.score, reverse=True)
        suggestions = suggestions[:limit]

        logger.debug(
            "suggestions_generated",
            user_id=str(user_id),
            query=query,
            count=len(suggestions)
        )

        return {
            "query": query,
            "suggestions": suggestions,
            "total": len(suggestions)
        }

    def _create_highlight(self, text: str, query: str) -> str:
        """Erstellt sicheres HTML-Highlight fuer Suchbegriff (ReDoS-geschuetzt)."""
        from app.core.input_sanitization import create_safe_highlight
        return create_safe_highlight(text, query, tag="mark")


# Thread-safe singleton via lru_cache
@lru_cache(maxsize=1)
def get_search_service() -> SearchService:
    """Search-Service-Instanz abrufen (thread-safe singleton)."""
    return SearchService()
