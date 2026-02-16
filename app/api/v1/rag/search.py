"""RAG Search API Endpoints.

Chunk-basierte semantische Suche mit:
- Semantic Search (Vektor-Similarity)
- Hybrid Search (Semantic + Keyword)
- Optional Reranking
"""

import structlog
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status, Request
from sqlalchemy.ext.asyncio import AsyncSession

# SECURITY FIX 28-13: Rate Limiting für Search Endpoints
from app.core.rate_limiting import limiter, get_user_identifier

from app.db.models import User, RAGSectionType
from app.api.dependencies import get_current_user, get_db
from app.api.schemas.rag import (
    RAGSearchRequest,
    RAGSearchResponse,
    RAGChunkSearchResult,
    RAGSearchType,
)
from app.services.rag.search_service import get_rag_search_service, RAGSearchService
from app.core.safe_errors import safe_error_log

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/search", tags=["rag-search"])


def get_search_service_dep() -> RAGSearchService:
    """Dependency für RAGSearchService."""
    return get_rag_search_service()


# SECURITY FIX 28-13: Rate-Limit für Suche (Embedding-intensiv)
@limiter.limit("60/minute", key_func=get_user_identifier)
@router.post(
    "",
    response_model=RAGSearchResponse,
    summary="RAG Suche durchführen",
    description="Führt eine Chunk-basierte semantische Suche durch."
)
async def search_chunks(
    request: Request,  # SECURITY FIX: Required for rate limiter
    body: RAGSearchRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    search_service: RAGSearchService = Depends(get_search_service_dep)
) -> RAGSearchResponse:
    """
    Semantische Suche in Document Chunks.

    Unterstützte Suchtypen:
    - **semantic**: Reine Vektor-Suche (Standard)
    - **hybrid**: Kombination aus Semantic + Keyword
    - **keyword**: Reine Volltext-Suche

    Features:
    - Automatisches Query-Embedding
    - Optional: Reranking mit Cross-Encoder
    - Filterung nach Dokumenten und Section-Types
    """
    logger.info(
        "rag_search_request",
        user_id=str(current_user.id),
        query=body.query[:100],
        search_type=body.search_type.value,
        limit=body.limit
    )

    try:
        # Suchtyp-spezifische Verarbeitung
        if body.search_type == RAGSearchType.SEMANTIC:
            response = await search_service.semantic_search(
                db=db,
                query=body.query,
                limit=body.limit,
                threshold=body.threshold,
                document_ids=body.document_ids,
                section_types=body.section_types,
                rerank=body.rerank
            )
        elif body.search_type == RAGSearchType.HYBRID:
            response = await search_service.hybrid_search(
                db=db,
                query=body.query,
                limit=body.limit,
                threshold=body.threshold,
                document_ids=body.document_ids,
                rerank=body.rerank
            )
        else:  # KEYWORD
            response = await search_service.keyword_search(
                db=db,
                query=body.query,
                limit=body.limit,
                document_ids=body.document_ids
            )

        # Response konvertieren
        results = [
            RAGChunkSearchResult(
                chunk_id=r.chunk_id,
                document_id=r.document_id,
                chunk_text=r.chunk_text,
                chunk_index=r.chunk_index,
                page_number=r.page_number,
                section_type=r.section_type,
                similarity=r.similarity,
                rerank_score=r.rerank_score
            )
            for r in response.results
        ]

        return RAGSearchResponse(
            query=response.query,
            search_type=response.search_type,
            results=results,
            total_results=response.total_results,
            search_time_ms=response.search_time_ms,
            embedding_time_ms=response.embedding_time_ms,
            rerank_time_ms=response.rerank_time_ms
        )

    except Exception as e:
        # SECURITY FIX 28-23: Generische Fehlermeldung
        logger.exception(
            "rag_search_failed",
            user_id=str(current_user.id),
            query=request.query[:50],
            **safe_error_log(e)
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Suche fehlgeschlagen. Bitte versuchen Sie es erneut."
        )


@router.get(
    "/semantic",
    response_model=RAGSearchResponse,
    summary="Semantische Suche (GET)",
    description="Vereinfachte semantische Suche via GET."
)
async def semantic_search_get(
    q: str = Query(..., min_length=1, max_length=1000, description="Suchanfrage"),
    limit: int = Query(20, ge=1, le=100, description="Max Ergebnisse"),
    threshold: float = Query(0.7, ge=0.0, le=1.0, description="Min Similarity"),
    rerank: bool = Query(True, description="Reranking aktivieren"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    search_service: RAGSearchService = Depends(get_search_service_dep)
) -> RAGSearchResponse:
    """
    Semantische Suche via GET-Parameter.

    Für einfache Suchanfragen ohne Filter.
    """
    try:
        response = await search_service.semantic_search(
            db=db,
            query=q,
            limit=limit,
            threshold=threshold,
            rerank=rerank
        )

        results = [
            RAGChunkSearchResult(
                chunk_id=r.chunk_id,
                document_id=r.document_id,
                chunk_text=r.chunk_text,
                chunk_index=r.chunk_index,
                page_number=r.page_number,
                section_type=r.section_type,
                similarity=r.similarity,
                rerank_score=r.rerank_score
            )
            for r in response.results
        ]

        return RAGSearchResponse(
            query=response.query,
            search_type=RAGSearchType.SEMANTIC,
            results=results,
            total_results=response.total_results,
            search_time_ms=response.search_time_ms,
            embedding_time_ms=response.embedding_time_ms,
            rerank_time_ms=response.rerank_time_ms
        )

    except Exception as e:
        # SECURITY FIX 28-23: Generische Fehlermeldung
        logger.exception("semantic_search_get_failed", **safe_error_log(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Suche fehlgeschlagen. Bitte versuchen Sie es erneut."
        )


@router.get(
    "/hybrid",
    response_model=RAGSearchResponse,
    summary="Hybrid-Suche (GET)",
    description="Kombinierte Semantic + Keyword Suche via GET."
)
async def hybrid_search_get(
    q: str = Query(..., min_length=1, max_length=1000, description="Suchanfrage"),
    limit: int = Query(20, ge=1, le=100, description="Max Ergebnisse"),
    semantic_weight: float = Query(0.7, ge=0.0, le=1.0, description="Gewicht Semantic"),
    keyword_weight: float = Query(0.3, ge=0.0, le=1.0, description="Gewicht Keyword"),
    rerank: bool = Query(True, description="Reranking aktivieren"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    search_service: RAGSearchService = Depends(get_search_service_dep)
) -> RAGSearchResponse:
    """
    Hybrid-Suche via GET-Parameter.

    Kombiniert:
    - Semantische Vektor-Suche
    - Keyword-basierte Volltext-Suche

    Die Gewichte bestimmen die Balance zwischen beiden Methoden.
    """
    try:
        response = await search_service.hybrid_search(
            db=db,
            query=q,
            limit=limit,
            semantic_weight=semantic_weight,
            keyword_weight=keyword_weight,
            rerank=rerank
        )

        results = [
            RAGChunkSearchResult(
                chunk_id=r.chunk_id,
                document_id=r.document_id,
                chunk_text=r.chunk_text,
                chunk_index=r.chunk_index,
                page_number=r.page_number,
                section_type=r.section_type,
                similarity=r.similarity,
                rerank_score=r.rerank_score
            )
            for r in response.results
        ]

        return RAGSearchResponse(
            query=response.query,
            search_type=RAGSearchType.HYBRID,
            results=results,
            total_results=response.total_results,
            search_time_ms=response.search_time_ms,
            embedding_time_ms=response.embedding_time_ms,
            rerank_time_ms=response.rerank_time_ms
        )

    except Exception as e:
        # SECURITY FIX 28-23: Generische Fehlermeldung
        logger.exception("hybrid_search_get_failed", **safe_error_log(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Suche fehlgeschlagen. Bitte versuchen Sie es erneut."
        )
