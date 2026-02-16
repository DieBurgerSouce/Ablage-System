# -*- coding: utf-8 -*-
"""
Unified Search API Endpoint.

Vereint Dokument-Suche und Chunk-basierte RAG-Suche in einem Endpoint.
"""

from typing import List, Optional
from uuid import UUID

from app.core.types import JSONDict

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import User
from app.db.session import get_async_session
from app.api.dependencies import get_current_user
from app.db.schemas import SearchType, SearchFilters, SortField, SortOrder
from app.services.unified_search_service import (
    UnifiedSearchService,
    UnifiedSearchMode,
    get_unified_search_service,
)

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/unified-search", tags=["Unified Search"])


# ==================== Pydantic Schemas ====================

class UnifiedChunkResultSchema(BaseModel):
    """Schema für Chunk-Ergebnis."""
    chunk_id: str
    document_id: str
    content: str
    section_type: Optional[str] = None
    score: float
    highlight: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class UnifiedDocumentResultSchema(BaseModel):
    """Schema für Dokument-Ergebnis."""
    document_id: str
    filename: str
    original_filename: Optional[str] = None
    score: float
    document_type: Optional[str] = None
    status: Optional[str] = None
    created_at: Optional[str] = None
    mime_type: Optional[str] = None
    page_count: Optional[int] = None
    extracted_text_preview: Optional[str] = None
    matched_chunks: List[UnifiedChunkResultSchema] = Field(default_factory=list)
    fts_score: Optional[float] = None
    semantic_score: Optional[float] = None
    rerank_score: Optional[float] = None

    model_config = ConfigDict(from_attributes=True)


class UnifiedSearchResponseSchema(BaseModel):
    """Schema für Unified Search Response."""
    query: str
    mode: str
    documents: List[UnifiedDocumentResultSchema]
    total_documents: int
    chunk_results: List[UnifiedChunkResultSchema]
    total_chunks: int
    search_time_ms: float
    document_search_time_ms: Optional[float] = None
    chunk_search_time_ms: Optional[float] = None
    synonyms_used: List[str] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class UnifiedSearchRequest(BaseModel):
    """Request-Body für Unified Search."""
    query: str = Field(..., min_length=1, max_length=500, description="Suchbegriff")
    mode: UnifiedSearchMode = Field(
        default=UnifiedSearchMode.COMBINED,
        description="Suchmodus: document, chunk, combined"
    )
    # Dokument-Suche Parameter
    search_type: SearchType = Field(
        default=SearchType.HYBRID,
        description="Suchtyp: fts, semantic, hybrid"
    )
    page: int = Field(default=1, ge=1, description="Seitennummer")
    per_page: int = Field(default=20, ge=1, le=100, description="Ergebnisse pro Seite")
    expand_synonyms: bool = Field(default=True, description="Synonyme verwenden")
    # Chunk-Suche Parameter
    chunk_limit: int = Field(default=10, ge=1, le=50, description="Max. Chunk-Ergebnisse")
    chunk_threshold: float = Field(default=0.5, ge=0.0, le=1.0, description="Min. Chunk-Score")
    rerank: bool = Field(default=True, description="Reranking aktivieren")
    # Filter
    document_ids: Optional[List[str]] = Field(
        default=None,
        description="Filter auf bestimmte Dokument-IDs"
    )
    document_type: Optional[str] = Field(default=None, description="Filter: Dokumenttyp")
    status: Optional[str] = Field(default=None, description="Filter: Status")


# ==================== Dependency ====================

def get_unified_service() -> UnifiedSearchService:
    """Dependency für UnifiedSearchService."""
    return get_unified_search_service()


# ==================== Endpoints ====================

@router.post(
    "",
    response_model=UnifiedSearchResponseSchema,
    summary="Unified Search durchführen",
    description="Kombinierte Dokument- und Chunk-basierte Suche"
)
async def unified_search(
    request: UnifiedSearchRequest,
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user),
    service: UnifiedSearchService = Depends(get_unified_service),
) -> UnifiedSearchResponseSchema:
    """
    Führt eine vereinheitlichte Suche durch.

    **Modi:**
    - **document**: Nur Dokument-basierte Suche (Volltext + Semantic)
    - **chunk**: Nur Chunk-basierte RAG-Suche
    - **combined**: Beide kombiniert mit Chunk-Zuordnung zu Dokumenten

    **Suchtypen (für Document-Mode):**
    - **fts**: PostgreSQL Full-Text Search
    - **semantic**: Embedding-basierte Ähnlichkeitssuche
    - **hybrid**: Kombination beider via Reciprocal Rank Fusion
    """
    # Parse document_ids
    document_ids = None
    if request.document_ids:
        try:
            document_ids = [UUID(did) for did in request.document_ids]
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Ungültige Dokument-ID(s)"
            )

    # Build filters
    filters = None
    if request.document_type or request.status:
        from app.db.schemas import DocumentType, ProcessingStatus

        filters = SearchFilters(
            document_type=DocumentType(request.document_type) if request.document_type else None,
            status=ProcessingStatus(request.status) if request.status else None,
        )

    response = await service.search(
        db=db,
        query=request.query,
        user_id=current_user.id,
        mode=request.mode,
        search_type=request.search_type,
        filters=filters,
        page=request.page,
        per_page=request.per_page,
        expand_synonyms=request.expand_synonyms,
        chunk_limit=request.chunk_limit,
        chunk_threshold=request.chunk_threshold,
        rerank=request.rerank,
        document_ids=document_ids,
    )

    # Convert to schema
    return UnifiedSearchResponseSchema(
        query=response.query,
        mode=response.mode.value,
        documents=[
            UnifiedDocumentResultSchema(
                document_id=doc.document_id,
                filename=doc.filename,
                original_filename=doc.original_filename,
                score=doc.score,
                document_type=doc.document_type,
                status=doc.status,
                created_at=doc.created_at,
                mime_type=doc.mime_type,
                page_count=doc.page_count,
                extracted_text_preview=doc.extracted_text_preview,
                matched_chunks=[
                    UnifiedChunkResultSchema(
                        chunk_id=chunk.chunk_id,
                        document_id=chunk.document_id,
                        content=chunk.content,
                        section_type=chunk.section_type,
                        score=chunk.score,
                        highlight=chunk.highlight,
                    )
                    for chunk in doc.matched_chunks
                ],
                fts_score=doc.fts_score,
                semantic_score=doc.semantic_score,
                rerank_score=doc.rerank_score,
            )
            for doc in response.documents
        ],
        total_documents=response.total_documents,
        chunk_results=[
            UnifiedChunkResultSchema(
                chunk_id=chunk.chunk_id,
                document_id=chunk.document_id,
                content=chunk.content,
                section_type=chunk.section_type,
                score=chunk.score,
                highlight=chunk.highlight,
            )
            for chunk in response.chunk_results
        ],
        total_chunks=response.total_chunks,
        search_time_ms=response.search_time_ms,
        document_search_time_ms=response.document_search_time_ms,
        chunk_search_time_ms=response.chunk_search_time_ms,
        synonyms_used=response.synonyms_used,
    )


@router.get(
    "/modes",
    summary="Verfügbare Suchmodi",
    description="Gibt die verfügbaren Suchmodi zurück"
)
async def get_search_modes() -> JSONDict:
    """Gibt die verfügbaren Suchmodi mit Beschreibungen zurück."""
    return {
        "modes": [
            {
                "id": UnifiedSearchMode.DOCUMENT.value,
                "name": "Dokument-Suche",
                "description": "Sucht auf Dokument-Ebene mit Volltext und Semantik",
                "supports_pagination": True,
                "supports_filters": True,
            },
            {
                "id": UnifiedSearchMode.CHUNK.value,
                "name": "Chunk-Suche",
                "description": "Sucht in Dokumenten-Abschnitten für praezise Treffer",
                "supports_pagination": False,
                "supports_filters": False,
            },
            {
                "id": UnifiedSearchMode.COMBINED.value,
                "name": "Kombinierte Suche",
                "description": "Dokument-Suche mit zugeordneten Chunk-Treffern",
                "supports_pagination": True,
                "supports_filters": True,
            },
        ],
        "search_types": [
            {
                "id": SearchType.FTS.value,
                "name": "Volltext",
                "description": "PostgreSQL Full-Text Search mit deutschen Stemmern",
            },
            {
                "id": SearchType.SEMANTIC.value,
                "name": "Semantisch",
                "description": "Embedding-basierte Ähnlichkeitssuche",
            },
            {
                "id": SearchType.HYBRID.value,
                "name": "Hybrid",
                "description": "Kombination aus Volltext und Semantik (empfohlen)",
            },
        ],
    }
