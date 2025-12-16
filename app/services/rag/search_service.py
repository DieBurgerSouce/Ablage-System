"""RAG Search Service - Semantische Chunk-Suche mit Reranking.

Erweitert die bestehende Search-Funktionalitaet um:
- Chunk-basierte semantische Suche
- Hybrid Search (Semantic + Keyword)
- Optional: Reranking mit BGE-Reranker
- LLM-gesteuerte Query Enhancement
"""

import asyncio
from typing import List, Optional, Dict, Any, Tuple
from uuid import UUID
from datetime import datetime, timezone
from dataclasses import dataclass

import structlog
from sqlalchemy import select, func, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models import RAGDocumentChunk, Document, RAGSectionType
from app.services.embedding_service import get_embedding_service
from app.api.schemas.rag import RAGChunkSearchResult, RAGSearchType

logger = structlog.get_logger(__name__)


@dataclass
class SearchResult:
    """Einzelnes Suchergebnis."""
    chunk_id: UUID
    document_id: UUID
    chunk_text: str
    chunk_index: int
    page_number: Optional[int]
    section_type: Optional[str]
    similarity: float
    rerank_score: Optional[float] = None


@dataclass
class SearchResponse:
    """Antwort der Suche."""
    query: str
    search_type: RAGSearchType
    results: List[SearchResult]
    total_results: int
    search_time_ms: int
    embedding_time_ms: Optional[int] = None
    rerank_time_ms: Optional[int] = None


class RAGSearchService:
    """Service fuer RAG-basierte Chunk-Suche.

    Implementiert:
    - Semantische Suche mit pgvector
    - Hybrid Search (FTS + Semantic)
    - Optionales Reranking
    - Query Enhancement
    """

    def __init__(self) -> None:
        self._embedding_service = get_embedding_service()
        self._reranker_available: Optional[bool] = None

    async def semantic_search(
        self,
        db: AsyncSession,
        query: str,
        limit: int = 20,
        threshold: float = 0.7,
        document_ids: Optional[List[UUID]] = None,
        section_types: Optional[List[RAGSectionType]] = None,
        rerank: bool = True
    ) -> SearchResponse:
        """Fuehrt semantische Suche auf Chunks durch.

        Args:
            db: Datenbank-Session
            query: Suchanfrage
            limit: Maximale Anzahl Ergebnisse
            threshold: Minimale Cosine Similarity
            document_ids: Optional: Nur in diesen Dokumenten suchen
            section_types: Optional: Nur diese Section-Typen
            rerank: Ergebnisse mit Reranker verbessern

        Returns:
            SearchResponse mit Ergebnissen und Metriken
        """
        start_time = datetime.now(timezone.utc)

        logger.info(
            "rag_semantic_search_start",
            query=query[:100],
            limit=limit,
            threshold=threshold,
            document_filter=document_ids is not None,
            section_filter=section_types is not None
        )

        # 1. Query Embedding generieren
        embed_start = datetime.now(timezone.utc)
        query_embedding = await self._embedding_service.generate_query_embedding_cached(query)
        embed_time = int((datetime.now(timezone.utc) - embed_start).total_seconds() * 1000)

        # 2. Vektor-Suche mit pgvector
        # Nutze die DB-Function rag_semantic_search falls verfuegbar
        results = await self._vector_search(
            db=db,
            query_embedding=query_embedding,
            limit=limit * 2 if rerank else limit,  # Mehr Kandidaten fuer Reranking
            threshold=threshold,
            document_ids=document_ids,
            section_types=section_types
        )

        # 3. Optional: Reranking
        rerank_time = None
        if rerank and len(results) > 1 and settings.RAG_RERANK_ENABLED:
            rerank_start = datetime.now(timezone.utc)
            results = await self._rerank_results(query, results, settings.RAG_RERANK_TOP_K)
            rerank_time = int((datetime.now(timezone.utc) - rerank_start).total_seconds() * 1000)

        # Auf Limit beschraenken
        results = results[:limit]

        total_time = int((datetime.now(timezone.utc) - start_time).total_seconds() * 1000)

        logger.info(
            "rag_semantic_search_complete",
            results_count=len(results),
            total_time_ms=total_time,
            embed_time_ms=embed_time,
            rerank_time_ms=rerank_time
        )

        return SearchResponse(
            query=query,
            search_type=RAGSearchType.SEMANTIC,
            results=results,
            total_results=len(results),
            search_time_ms=total_time,
            embedding_time_ms=embed_time,
            rerank_time_ms=rerank_time
        )

    async def hybrid_search(
        self,
        db: AsyncSession,
        query: str,
        limit: int = 20,
        semantic_weight: float = 0.7,
        keyword_weight: float = 0.3,
        threshold: float = 0.5,
        document_ids: Optional[List[UUID]] = None,
        rerank: bool = True
    ) -> SearchResponse:
        """Fuehrt Hybrid-Suche durch (Semantic + Keyword).

        Kombiniert:
        - Semantische Vektorsuche (pgvector)
        - Keyword-Suche (PostgreSQL FTS)

        Args:
            db: Datenbank-Session
            query: Suchanfrage
            limit: Maximale Anzahl Ergebnisse
            semantic_weight: Gewichtung semantische Suche (0-1)
            keyword_weight: Gewichtung Keyword-Suche (0-1)
            threshold: Minimaler kombinierter Score
            document_ids: Optional: Nur in diesen Dokumenten
            rerank: Ergebnisse reranken

        Returns:
            SearchResponse mit kombinierten Ergebnissen
        """
        start_time = datetime.now(timezone.utc)

        logger.info(
            "rag_hybrid_search_start",
            query=query[:100],
            semantic_weight=semantic_weight,
            keyword_weight=keyword_weight
        )

        # 1. Query Embedding
        embed_start = datetime.now(timezone.utc)
        query_embedding = await self._embedding_service.generate_query_embedding_cached(query)
        embed_time = int((datetime.now(timezone.utc) - embed_start).total_seconds() * 1000)

        # 2. Parallele Suchen
        semantic_task = self._vector_search(
            db=db,
            query_embedding=query_embedding,
            limit=limit * 2,
            threshold=0.5,  # Niedrigerer Threshold fuer Fusion
            document_ids=document_ids
        )

        keyword_task = self._keyword_search(
            db=db,
            query=query,
            limit=limit * 2,
            document_ids=document_ids
        )

        semantic_results, keyword_results = await asyncio.gather(
            semantic_task, keyword_task
        )

        # 3. Score Fusion (Reciprocal Rank Fusion)
        fused_results = self._fuse_results(
            semantic_results,
            keyword_results,
            semantic_weight,
            keyword_weight
        )

        # Filter nach Threshold
        fused_results = [r for r in fused_results if r.similarity >= threshold]

        # 4. Optional: Reranking
        rerank_time = None
        if rerank and len(fused_results) > 1 and settings.RAG_RERANK_ENABLED:
            rerank_start = datetime.now(timezone.utc)
            fused_results = await self._rerank_results(
                query, fused_results, settings.RAG_RERANK_TOP_K
            )
            rerank_time = int((datetime.now(timezone.utc) - rerank_start).total_seconds() * 1000)

        # Limit
        fused_results = fused_results[:limit]

        total_time = int((datetime.now(timezone.utc) - start_time).total_seconds() * 1000)

        logger.info(
            "rag_hybrid_search_complete",
            semantic_count=len(semantic_results),
            keyword_count=len(keyword_results),
            fused_count=len(fused_results),
            total_time_ms=total_time
        )

        return SearchResponse(
            query=query,
            search_type=RAGSearchType.HYBRID,
            results=fused_results,
            total_results=len(fused_results),
            search_time_ms=total_time,
            embedding_time_ms=embed_time,
            rerank_time_ms=rerank_time
        )

    async def keyword_search(
        self,
        db: AsyncSession,
        query: str,
        limit: int = 20,
        document_ids: Optional[List[UUID]] = None
    ) -> SearchResponse:
        """Fuehrt reine Keyword-Suche durch.

        Args:
            db: Datenbank-Session
            query: Suchanfrage
            limit: Maximale Anzahl Ergebnisse
            document_ids: Optional: Nur in diesen Dokumenten

        Returns:
            SearchResponse mit Ergebnissen
        """
        start_time = datetime.now(timezone.utc)

        results = await self._keyword_search(
            db=db,
            query=query,
            limit=limit,
            document_ids=document_ids
        )

        total_time = int((datetime.now(timezone.utc) - start_time).total_seconds() * 1000)

        return SearchResponse(
            query=query,
            search_type=RAGSearchType.KEYWORD,
            results=results,
            total_results=len(results),
            search_time_ms=total_time
        )

    async def _vector_search(
        self,
        db: AsyncSession,
        query_embedding: List[float],
        limit: int,
        threshold: float,
        document_ids: Optional[List[UUID]] = None,
        section_types: Optional[List[RAGSectionType]] = None
    ) -> List[SearchResult]:
        """Interne Vektorsuche mit pgvector."""
        # Embedding als String fuer PostgreSQL
        embedding_str = "[" + ",".join(str(x) for x in query_embedding) + "]"

        # Base Query mit Cosine Similarity
        # 1 - (embedding <=> query) gibt Similarity (0-1)
        query = select(
            RAGDocumentChunk.id,
            RAGDocumentChunk.document_id,
            RAGDocumentChunk.chunk_text,
            RAGDocumentChunk.chunk_index,
            RAGDocumentChunk.page_number,
            RAGDocumentChunk.section_type,
            (1 - RAGDocumentChunk.embedding.cosine_distance(query_embedding)).label("similarity")
        ).where(
            RAGDocumentChunk.embedding.isnot(None)
        )

        # Filter: Dokumente
        if document_ids:
            query = query.where(RAGDocumentChunk.document_id.in_(document_ids))

        # Filter: Section Types
        if section_types:
            query = query.where(RAGDocumentChunk.section_type.in_(section_types))

        # Threshold und Sortierung
        query = query.having(
            text("similarity >= :threshold")
        ).params(threshold=threshold).order_by(
            text("similarity DESC")
        ).limit(limit)

        result = await db.execute(query)
        rows = result.fetchall()

        return [
            SearchResult(
                chunk_id=row.id,
                document_id=row.document_id,
                chunk_text=row.chunk_text,
                chunk_index=row.chunk_index,
                page_number=row.page_number,
                section_type=row.section_type.value if row.section_type else None,
                similarity=float(row.similarity)
            )
            for row in rows
        ]

    async def _keyword_search(
        self,
        db: AsyncSession,
        query: str,
        limit: int,
        document_ids: Optional[List[UUID]] = None
    ) -> List[SearchResult]:
        """Interne Keyword-Suche mit PostgreSQL FTS."""
        # Erstelle tsquery aus Query
        # plainto_tsquery ist robuster als to_tsquery
        search_query = select(
            RAGDocumentChunk.id,
            RAGDocumentChunk.document_id,
            RAGDocumentChunk.chunk_text,
            RAGDocumentChunk.chunk_index,
            RAGDocumentChunk.page_number,
            RAGDocumentChunk.section_type,
            func.ts_rank(
                func.to_tsvector('german', RAGDocumentChunk.chunk_text),
                func.plainto_tsquery('german', query)
            ).label("rank")
        ).where(
            func.to_tsvector('german', RAGDocumentChunk.chunk_text).match(
                func.plainto_tsquery('german', query)
            )
        )

        if document_ids:
            search_query = search_query.where(
                RAGDocumentChunk.document_id.in_(document_ids)
            )

        search_query = search_query.order_by(text("rank DESC")).limit(limit)

        result = await db.execute(search_query)
        rows = result.fetchall()

        # Normalisiere Rank zu 0-1 Score
        max_rank = max((row.rank for row in rows), default=1.0) or 1.0

        return [
            SearchResult(
                chunk_id=row.id,
                document_id=row.document_id,
                chunk_text=row.chunk_text,
                chunk_index=row.chunk_index,
                page_number=row.page_number,
                section_type=row.section_type.value if row.section_type else None,
                similarity=float(row.rank) / max_rank  # Normalisiert
            )
            for row in rows
        ]

    def _fuse_results(
        self,
        semantic_results: List[SearchResult],
        keyword_results: List[SearchResult],
        semantic_weight: float,
        keyword_weight: float
    ) -> List[SearchResult]:
        """Fusioniert Ergebnisse mit Reciprocal Rank Fusion.

        RRF Score = sum(1 / (k + rank)) fuer jede Liste
        """
        k = 60  # RRF Konstante

        # Scores sammeln
        scores: Dict[UUID, Tuple[SearchResult, float]] = {}

        # Semantic Scores
        for rank, result in enumerate(semantic_results, 1):
            rrf_score = semantic_weight * (1 / (k + rank))
            scores[result.chunk_id] = (result, rrf_score)

        # Keyword Scores hinzufuegen
        for rank, result in enumerate(keyword_results, 1):
            rrf_score = keyword_weight * (1 / (k + rank))
            if result.chunk_id in scores:
                existing_result, existing_score = scores[result.chunk_id]
                scores[result.chunk_id] = (existing_result, existing_score + rrf_score)
            else:
                scores[result.chunk_id] = (result, rrf_score)

        # Nach kombiniertem Score sortieren
        sorted_results = sorted(
            scores.values(),
            key=lambda x: x[1],
            reverse=True
        )

        # Score als Similarity setzen
        return [
            SearchResult(
                chunk_id=r.chunk_id,
                document_id=r.document_id,
                chunk_text=r.chunk_text,
                chunk_index=r.chunk_index,
                page_number=r.page_number,
                section_type=r.section_type,
                similarity=score
            )
            for r, score in sorted_results
        ]

    async def _rerank_results(
        self,
        query: str,
        results: List[SearchResult],
        top_k: int
    ) -> List[SearchResult]:
        """Rerankt Ergebnisse mit Dual-Stack Cross-Encoder (GPU/CPU).

        Verwendet lokalen RerankerService fuer integriertes Reranking:
        - Primaer: BGE-Reranker-v2-m3 (GPU, ~1GB VRAM)
        - Fallback: MiniLM Cross-Encoder (CPU, ~300MB RAM)

        Falls beide fehlschlagen: Original-Reihenfolge beibehalten.
        """
        if not results or not settings.RAG_RERANK_ENABLED:
            return results[:top_k]

        try:
            from app.services.reranker_service import get_reranker_service

            reranker = get_reranker_service()
            documents = [r.chunk_text for r in results]

            # Async Reranking mit GPU/CPU Fallback
            reranked = await reranker.rerank_async(query, documents, top_k)

            # Ergebnisse mit Rerank-Scores aktualisieren und neu sortieren
            reranked_results = []
            for rr in reranked:
                original = results[rr.index]
                reranked_results.append(SearchResult(
                    chunk_id=original.chunk_id,
                    document_id=original.document_id,
                    chunk_text=original.chunk_text,
                    chunk_index=original.chunk_index,
                    page_number=original.page_number,
                    section_type=original.section_type,
                    similarity=original.similarity,
                    rerank_score=rr.score
                ))

            logger.debug(
                "rerank_complete",
                input_count=len(results),
                output_count=len(reranked_results),
                top_k=top_k,
                backend=reranker.get_stats().get("gpu_model_loaded", False)
                    and "gpu" or "cpu"
            )

            return reranked_results

        except Exception as e:
            logger.warning(
                "rerank_failed",
                error=str(e),
                fallback="using_original_scores"
            )
            return results[:top_k]

    async def search_for_context(
        self,
        db: AsyncSession,
        query: str,
        context_chunks: int = 5,
        document_ids: Optional[List[UUID]] = None
    ) -> List[Dict[str, Any]]:
        """Sucht Chunks fuer RAG-Kontext.

        Optimiert fuer die Verwendung mit LLM:
        - Weniger Ergebnisse, hoehere Qualitaet
        - Immer mit Reranking
        - Gibt vereinfachte Dicts zurueck

        Args:
            db: Datenbank-Session
            query: Suchanfrage
            context_chunks: Anzahl Kontext-Chunks
            document_ids: Optional: Nur in diesen Dokumenten

        Returns:
            Liste von Chunk-Dictionaries fuer RAG-Kontext
        """
        response = await self.hybrid_search(
            db=db,
            query=query,
            limit=context_chunks,
            semantic_weight=0.7,
            keyword_weight=0.3,
            threshold=0.5,
            document_ids=document_ids,
            rerank=True
        )

        return [
            {
                "chunk_id": str(r.chunk_id),
                "document_id": str(r.document_id),
                "text": r.chunk_text,
                "chunk_text": r.chunk_text,  # Alias
                "page_number": r.page_number,
                "section_type": r.section_type,
                "similarity": r.similarity,
                "rerank_score": r.rerank_score
            }
            for r in response.results
        ]


# Singleton-Instanz
_rag_search_service: Optional[RAGSearchService] = None


def get_rag_search_service() -> RAGSearchService:
    """Gibt die RAG Search Service Instanz zurueck."""
    global _rag_search_service
    if _rag_search_service is None:
        _rag_search_service = RAGSearchService()
    return _rag_search_service
