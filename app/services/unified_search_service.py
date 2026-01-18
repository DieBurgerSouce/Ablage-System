# -*- coding: utf-8 -*-
"""
Unified Search Service.

Vereint Dokument-Suche und Chunk-basierte RAG-Suche in einem Service.
Ermoeglicht sowohl separate als auch kombinierte Suche.
"""

from typing import List, Optional, Dict, Any, Set
from uuid import UUID
from dataclasses import dataclass, field
from enum import Enum
import time

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.search_service import SearchService, get_search_service
from app.services.rag.search_service import RAGSearchService, get_rag_search_service
from app.db.schemas import (
    SearchType,
    SearchFilters,
    SearchResultItem,
    SortField,
    SortOrder,
)

logger = structlog.get_logger(__name__)


# ==================== Enums ====================

class UnifiedSearchMode(str, Enum):
    """Suchmodi fuer die Unified Search."""
    DOCUMENT = "document"      # Nur Dokument-Suche
    CHUNK = "chunk"           # Nur Chunk-basierte RAG-Suche
    COMBINED = "combined"     # Beide kombiniert


# ==================== Data Classes ====================

@dataclass
class UnifiedChunkResult:
    """Ergebnis eines Chunk-Matches."""
    chunk_id: str
    document_id: str
    content: str
    section_type: Optional[str]
    score: float
    highlight: Optional[str] = None


@dataclass
class UnifiedDocumentResult:
    """Ergebnis eines Dokument-Matches."""
    document_id: str
    filename: str
    original_filename: Optional[str]
    score: float
    document_type: Optional[str]
    status: Optional[str]
    created_at: Optional[str]
    mime_type: Optional[str]
    page_count: Optional[int]
    extracted_text_preview: Optional[str] = None
    # Zugehoerige Chunks (bei Combined-Suche)
    matched_chunks: List[UnifiedChunkResult] = field(default_factory=list)
    # Score-Breakdown
    fts_score: Optional[float] = None
    semantic_score: Optional[float] = None
    rerank_score: Optional[float] = None


@dataclass
class UnifiedSearchResponse:
    """Antwort der Unified Search."""
    query: str
    mode: UnifiedSearchMode
    documents: List[UnifiedDocumentResult]
    total_documents: int
    chunk_results: List[UnifiedChunkResult]
    total_chunks: int
    search_time_ms: float
    document_search_time_ms: Optional[float] = None
    chunk_search_time_ms: Optional[float] = None
    synonyms_used: List[str] = field(default_factory=list)


# ==================== Service ====================

class UnifiedSearchService:
    """
    Service fuer vereinheitlichte Suche.

    Kombiniert:
    - SearchService: Dokument-basierte Suche (FTS + Semantic + Hybrid)
    - RAGSearchService: Chunk-basierte semantische Suche
    """

    def __init__(self) -> None:
        self._search_service: Optional[SearchService] = None
        self._rag_service: Optional[RAGSearchService] = None

    def _get_search_service(self) -> SearchService:
        """Lazy-load SearchService."""
        if self._search_service is None:
            self._search_service = get_search_service()
        return self._search_service

    def _get_rag_service(self) -> RAGSearchService:
        """Lazy-load RAGSearchService."""
        if self._rag_service is None:
            self._rag_service = get_rag_search_service()
        return self._rag_service

    async def search(
        self,
        db: AsyncSession,
        query: str,
        user_id: UUID,
        mode: UnifiedSearchMode = UnifiedSearchMode.COMBINED,
        # Document search params
        search_type: SearchType = SearchType.HYBRID,
        filters: Optional[SearchFilters] = None,
        page: int = 1,
        per_page: int = 20,
        sort_by: SortField = SortField.RELEVANCE,
        sort_order: SortOrder = SortOrder.DESC,
        expand_synonyms: bool = True,
        # Chunk search params
        chunk_limit: int = 10,
        chunk_threshold: float = 0.5,
        rerank: bool = True,
        document_ids: Optional[List[UUID]] = None,
    ) -> UnifiedSearchResponse:
        """
        Fuehrt eine vereinheitlichte Suche durch.

        Args:
            db: Datenbank-Session
            query: Suchbegriff
            user_id: Benutzer-ID fuer Zugriffsrechte
            mode: Suchmodus (document, chunk, combined)
            search_type: Typ der Dokumentensuche (fts, semantic, hybrid)
            filters: Filter fuer Dokumentensuche
            page: Seite fuer Dokumentensuche
            per_page: Ergebnisse pro Seite
            sort_by: Sortierfeld
            sort_order: Sortierrichtung
            expand_synonyms: Synonyme verwenden
            chunk_limit: Max. Chunk-Ergebnisse
            chunk_threshold: Min. Chunk-Score
            rerank: Reranking aktivieren
            document_ids: Filter auf bestimmte Dokumente

        Returns:
            UnifiedSearchResponse mit kombinierten Ergebnissen
        """
        start_time = time.perf_counter()

        documents: List[UnifiedDocumentResult] = []
        chunks: List[UnifiedChunkResult] = []
        total_documents = 0
        total_chunks = 0
        doc_search_time = None
        chunk_search_time = None
        synonyms_used: List[str] = []

        # Dokument-Suche
        if mode in (UnifiedSearchMode.DOCUMENT, UnifiedSearchMode.COMBINED):
            doc_start = time.perf_counter()
            search_service = self._get_search_service()

            doc_response = await search_service.search(
                db=db,
                query=query,
                user_id=user_id,
                search_type=search_type,
                filters=filters,
                page=page,
                per_page=per_page,
                sort_by=sort_by,
                sort_order=sort_order,
                expand_synonyms=expand_synonyms,
            )

            doc_search_time = (time.perf_counter() - doc_start) * 1000
            total_documents = doc_response.total_count

            for item in doc_response.results:
                documents.append(UnifiedDocumentResult(
                    document_id=item.id,
                    filename=item.filename,
                    original_filename=item.original_filename,
                    score=item.score,
                    document_type=item.document_type.value if item.document_type else None,
                    status=item.status.value if item.status else None,
                    created_at=item.created_at.isoformat() if item.created_at else None,
                    mime_type=item.mime_type,
                    page_count=item.page_count,
                    extracted_text_preview=item.highlight or (
                        item.extracted_text[:200] if item.extracted_text else None
                    ),
                    fts_score=item.fts_score if hasattr(item, 'fts_score') else None,
                    semantic_score=item.semantic_score if hasattr(item, 'semantic_score') else None,
                    rerank_score=item.rerank_score if hasattr(item, 'rerank_score') else None,
                ))

            # Synonyme aus Response
            if doc_response.synonym_expansion:
                synonyms_used = [
                    syn.expanded_term
                    for syn in doc_response.synonym_expansion
                ]

        # Chunk-Suche (RAG)
        if mode in (UnifiedSearchMode.CHUNK, UnifiedSearchMode.COMBINED):
            chunk_start = time.perf_counter()
            rag_service = self._get_rag_service()

            try:
                rag_response = await rag_service.hybrid_search(
                    db=db,
                    query=query,
                    limit=chunk_limit,
                    document_ids=[str(d) for d in document_ids] if document_ids else None,
                    rerank=rerank,
                    user_id=user_id,
                )

                chunk_search_time = (time.perf_counter() - chunk_start) * 1000
                total_chunks = len(rag_response.results)

                for chunk_result in rag_response.results:
                    if chunk_result.score >= chunk_threshold:
                        chunks.append(UnifiedChunkResult(
                            chunk_id=str(chunk_result.chunk_id),
                            document_id=str(chunk_result.document_id),
                            content=chunk_result.content,
                            section_type=chunk_result.section_type,
                            score=chunk_result.score,
                            highlight=chunk_result.highlight if hasattr(chunk_result, 'highlight') else None,
                        ))

                # Bei Combined-Mode: Chunks zu Dokumenten zuordnen
                if mode == UnifiedSearchMode.COMBINED and documents and chunks:
                    self._merge_chunks_to_documents(documents, chunks)

            except Exception as e:
                logger.warning(
                    "chunk_search_failed",
                    error=str(e),
                    query=query,
                )
                # Bei Fehler in Chunk-Suche trotzdem Dokument-Ergebnisse zurueckgeben
                chunk_search_time = (time.perf_counter() - chunk_start) * 1000

        total_time = (time.perf_counter() - start_time) * 1000

        logger.info(
            "unified_search_completed",
            mode=mode.value,
            query_length=len(query),
            document_count=len(documents),
            chunk_count=len(chunks),
            total_time_ms=total_time,
        )

        return UnifiedSearchResponse(
            query=query,
            mode=mode,
            documents=documents,
            total_documents=total_documents,
            chunk_results=chunks,
            total_chunks=total_chunks,
            search_time_ms=total_time,
            document_search_time_ms=doc_search_time,
            chunk_search_time_ms=chunk_search_time,
            synonyms_used=synonyms_used,
        )

    def _merge_chunks_to_documents(
        self,
        documents: List[UnifiedDocumentResult],
        chunks: List[UnifiedChunkResult],
    ) -> None:
        """Ordnet Chunks den entsprechenden Dokumenten zu."""
        doc_id_map: Dict[str, UnifiedDocumentResult] = {
            doc.document_id: doc for doc in documents
        }

        for chunk in chunks:
            if chunk.document_id in doc_id_map:
                doc_id_map[chunk.document_id].matched_chunks.append(chunk)


# ==================== Singleton ====================

_unified_search_service: Optional[UnifiedSearchService] = None


def get_unified_search_service() -> UnifiedSearchService:
    """Gibt Singleton-Instanz des UnifiedSearchService zurueck."""
    global _unified_search_service
    if _unified_search_service is None:
        _unified_search_service = UnifiedSearchService()
    return _unified_search_service
