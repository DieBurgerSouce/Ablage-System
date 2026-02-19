# -*- coding: utf-8 -*-
"""API-Endpunkte fuer Semantische Suche.

Endpunkte:
- POST /api/v1/search/semantic - Natuerlichsprachliche Suche
- GET  /api/v1/search/similar/{document_id} - Aehnliche Dokumente
- GET  /api/v1/search/semantic/stats - Embedding-Abdeckung
- POST /api/v1/search/semantic/batch-embed - Batch-Embedding starten
"""

import uuid
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user, get_db
from app.core.rate_limiting import limiter, get_user_identifier
from app.api.schemas.semantic_search import (
    BatchEmbedRequest,
    BatchEmbedResponse,
    EmbeddingCoverageStats as EmbeddingCoverageStatsSchema,
    SemanticSearchRequest,
    SemanticSearchResponse,
    SemanticSearchResultItem,
    SimilarDocumentResultItem,
    SimilarDocumentsRequest,
    SimilarDocumentsResponse,
)
from app.db.models import User
from app.services.semantic_search_service import get_semantic_search_service

logger = structlog.get_logger(__name__)

router = APIRouter(
    prefix="/search",
    tags=["Semantische Suche"],
)


# ============================================================================
# POST /search/semantic
# ============================================================================


@router.post(
    "/semantic",
    response_model=SemanticSearchResponse,
    summary="Semantische Dokumentensuche",
    description="Natuerlichsprachliche Suche ueber alle Dokumente mit Vektor-Aehnlichkeit.",
)
@limiter.limit("20/minute", key_func=get_user_identifier)
async def semantic_search(
    http_request: Request,
    request: SemanticSearchRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SemanticSearchResponse:
    """Fuehrt eine semantische Suche durch."""
    import time

    start = time.perf_counter()
    service = get_semantic_search_service()

    try:
        results = await service.semantic_search(
            query=request.query,
            session=db,
            user_id=current_user.id,
            limit=request.limit,
            threshold=request.threshold,
            document_type=request.document_type,
            date_from=request.date_from,
            date_to=request.date_to,
        )

        elapsed_ms = (time.perf_counter() - start) * 1000

        from app.core.config import settings

        return SemanticSearchResponse(
            query=request.query,
            total=len(results),
            results=[
                SemanticSearchResultItem(
                    document_id=r.document_id,
                    filename=r.filename,
                    original_filename=r.original_filename,
                    document_type=r.document_type,
                    similarity=r.similarity,
                    created_at=r.created_at,
                    text_preview=r.text_preview,
                    page_count=r.page_count,
                )
                for r in results
            ],
            search_time_ms=round(elapsed_ms, 1),
            embedding_model=settings.EMBEDDING_MODEL,
            threshold_applied=request.threshold,
        )

    except Exception as e:
        logger.error(
            "semantic_search_api_error",
            query=request.query[:100],
            error=str(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Semantische Suche fehlgeschlagen",
        )


# ============================================================================
# GET /search/similar/{document_id}
# ============================================================================


@router.get(
    "/similar/{document_id}",
    response_model=SimilarDocumentsResponse,
    summary="Aehnliche Dokumente finden",
    description="Findet Dokumente mit aehnlichem Inhalt basierend auf Vektor-Aehnlichkeit.",
)
@limiter.limit("20/minute", key_func=get_user_identifier)
async def find_similar_documents(
    request: Request,
    document_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    limit: int = Query(10, ge=1, le=50, description="Maximale Ergebnisanzahl"),
    threshold: float = Query(0.7, ge=0.0, le=1.0, description="Minimaler Aehnlichkeitsscore"),
) -> SimilarDocumentsResponse:
    """Findet aehnliche Dokumente zu einem Quelldokument."""
    import time

    start = time.perf_counter()
    service = get_semantic_search_service()

    try:
        results = await service.find_similar_documents(
            document_id=document_id,
            session=db,
            user_id=current_user.id,
            limit=limit,
            threshold=threshold,
        )

        elapsed_ms = (time.perf_counter() - start) * 1000

        return SimilarDocumentsResponse(
            source_document_id=document_id,
            total=len(results),
            results=[
                SimilarDocumentResultItem(
                    document_id=r.document_id,
                    filename=r.filename,
                    document_type=r.document_type,
                    similarity=r.similarity,
                    created_at=r.created_at,
                    text_preview=r.text_preview,
                )
                for r in results
            ],
            search_time_ms=round(elapsed_ms, 1),
        )

    except Exception as e:
        logger.error(
            "similar_search_api_error",
            document_id=str(document_id),
            error=str(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Aehnlichkeitssuche fehlgeschlagen",
        )


# ============================================================================
# GET /search/semantic/stats
# ============================================================================


@router.get(
    "/semantic/stats",
    response_model=EmbeddingCoverageStatsSchema,
    summary="Embedding-Abdeckungsstatistik",
    description="Zeigt wie viele Dokumente bereits Embeddings haben.",
)
async def get_embedding_stats(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> EmbeddingCoverageStatsSchema:
    """Gibt Embedding-Abdeckungsstatistiken zurueck."""
    service = get_semantic_search_service()

    try:
        stats = await service.get_embedding_coverage(db)

        return EmbeddingCoverageStatsSchema(
            total_documents=stats.total_documents,
            documents_with_embedding=stats.documents_with_embedding,
            documents_without_embedding=stats.documents_without_embedding,
            coverage_percent=stats.coverage_percent,
            embedding_model=stats.embedding_model,
            oldest_embedding=stats.oldest_embedding,
            newest_embedding=stats.newest_embedding,
        )

    except Exception as e:
        logger.error(
            "embedding_stats_api_error",
            error=str(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Statistik-Abfrage fehlgeschlagen",
        )


# ============================================================================
# POST /search/semantic/batch-embed
# ============================================================================


@router.post(
    "/semantic/batch-embed",
    response_model=BatchEmbedResponse,
    summary="Batch-Embedding starten",
    description="Startet einen Celery-Task fuer die Batch-Embedding-Generierung.",
)
@limiter.limit("5/minute", key_func=get_user_identifier)
async def start_batch_embed(
    http_request: Request,
    request: BatchEmbedRequest,
    current_user: Annotated[User, Depends(get_current_user)],
) -> BatchEmbedResponse:
    """Startet Batch-Embedding als Hintergrund-Task."""
    if not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Nur Administratoren koennen Batch-Embedding starten",
        )

    try:
        from app.workers.tasks.semantic_search_tasks import batch_embed_documents_task

        result = batch_embed_documents_task.apply_async(
            kwargs={"batch_size": request.batch_size},
            priority=7,  # Niedrige Prioritaet
        )

        return BatchEmbedResponse(
            task_id=result.id,
            message=f"Batch-Embedding gestartet (Batch-Groesse: {request.batch_size})",
        )

    except Exception as e:
        logger.error(
            "batch_embed_start_error",
            error=str(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Batch-Embedding konnte nicht gestartet werden",
        )
