"""Such-Service fuer Volltextsuche und semantische Suche.

Kombiniert PostgreSQL Full-Text Search (FTS) mit pgvector semantischer Suche.
Unterstuetzt Hybrid-Suche mit Reciprocal Rank Fusion.
"""

from typing import List, Optional, Dict, Any, Tuple, Set
from datetime import datetime
from uuid import UUID
import time
import math
import hashlib
import json

import structlog
from sqlalchemy import select, func, text, and_, or_, desc, asc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import Document, Tag, document_tags
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
    split_for_search
)

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
        skip_cache: bool = False
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

        # Query mit Compound-Splits erweitern (fuer FTS und Hybrid)
        expanded_query = query
        compound_terms: List[str] = []
        if search_type in (SearchType.FTS, SearchType.HYBRID):
            expanded_query, compound_terms = self._expand_query_with_compounds(query)

        logger.info(
            "search_started",
            query=query[:100],
            expanded_query=expanded_query[:100] if expanded_query != query else None,
            compound_terms_count=len(compound_terms),
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
                db, expanded_query, user_id, filters, page, per_page, highlight, threshold
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
        """PostgreSQL Full-Text Search mit German Config."""
        offset = (page - 1) * per_page

        # Base query mit tsvector Suche
        fts_query = text("""
            WITH search_query AS (
                SELECT plainto_tsquery('german_text', :query) AS query
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
                    ts_rank_cd(d.search_vector, sq.query) AS fts_rank,
                    ts_headline('german_text', COALESCE(d.extracted_text, ''), sq.query,
                        'MaxWords=50, MinWords=25, StartSel=<mark>, StopSel=</mark>'
                    ) AS highlight
                FROM documents d, search_query sq
                WHERE d.owner_id = :user_id
                    AND d.search_vector @@ sq.query
                    {filters}
                ORDER BY fts_rank DESC
            )
            SELECT * FROM ranked_docs
            LIMIT :limit OFFSET :offset
        """.format(filters=self._build_filter_sql(filters)))

        # Count query
        count_query = text("""
            SELECT COUNT(*) FROM documents d,
                plainto_tsquery('german_text', :query) AS query
            WHERE d.owner_id = :user_id
                AND d.search_vector @@ query
                {filters}
        """.format(filters=self._build_filter_sql(filters)))

        params = {
            "query": query,
            "user_id": str(user_id),
            "limit": per_page,
            "offset": offset
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

        # Semantic search query
        semantic_query = text("""
            WITH semantic_results AS (
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
                WHERE d.owner_id = :user_id
                    AND d.embedding IS NOT NULL
                    AND 1 - (d.embedding <=> :embedding::vector) >= :threshold
                    {filters}
                ORDER BY d.embedding <=> :embedding::vector
            )
            SELECT * FROM semantic_results
            LIMIT :limit OFFSET :offset
        """.format(filters=self._build_filter_sql(filters)))

        # Count query
        count_query = text("""
            SELECT COUNT(*) FROM documents d
            WHERE d.owner_id = :user_id
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
        threshold: float
    ) -> Tuple[List[SearchResultItem], int]:
        """Hybrid-Suche mit Reciprocal Rank Fusion (RRF)."""
        # Beide Suchmethoden ausfuehren (mehr Ergebnisse holen fuer Fusion)
        expanded_limit = per_page * HYBRID_EXPANSION_FACTOR

        fts_results, _ = await self._search_fts(
            db, query, user_id, filters, 1, expanded_limit, highlight
        )
        semantic_results, _ = await self._search_semantic(
            db, query, user_id, filters, 1, expanded_limit, threshold
        )

        # RRF Score berechnen mit Standard-Konstante
        k = RRF_K_CONSTANT
        scores: Dict[UUID, Dict[str, Any]] = {}

        # FTS Scores
        for rank, result in enumerate(fts_results):
            doc_id = result.document_id
            rrf_score = self.fts_weight / (k + rank + 1)
            scores[doc_id] = {
                "result": result,
                "rrf_score": rrf_score,
                "fts_rank": rank + 1
            }

        # Semantic Scores hinzufuegen/kombinieren
        for rank, result in enumerate(semantic_results):
            doc_id = result.document_id
            rrf_contribution = self.semantic_weight / (k + rank + 1)

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

        # Pagination anwenden
        offset = (page - 1) * per_page
        paginated = sorted_items[offset:offset + per_page]

        # Score normalisieren und Ergebnisse erstellen
        max_score = sorted_items[0]["rrf_score"] if sorted_items else 1.0
        results = []
        for item in paginated:
            result = item["result"]
            result.score = item["rrf_score"] / max_score  # Normalisieren auf 0-1
            results.append(result)

        total = len(sorted_items)
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

        # Embedding des Quelldokuments holen
        doc_query = select(Document).where(
            and_(Document.id == document_id, Document.owner_id == user_id)
        )
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

        # Aehnliche Dokumente suchen
        type_filter = ""
        if exclude_same_type and source_doc.document_type:
            type_filter = "AND d.document_type != :source_type"

        similar_query = text(f"""
            SELECT
                d.id AS document_id,
                d.filename,
                d.document_type,
                1 - (d.embedding <=> :embedding::vector) AS similarity,
                d.created_at,
                LEFT(d.extracted_text, 200) AS text_preview
            FROM documents d
            WHERE d.owner_id = :user_id
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


# Dependency Injection
_search_service: Optional[SearchService] = None


def get_search_service() -> SearchService:
    """Search-Service-Instanz abrufen."""
    global _search_service
    if _search_service is None:
        _search_service = SearchService()
    return _search_service
