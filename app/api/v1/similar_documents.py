# -*- coding: utf-8 -*-
"""
Aehnliche Dokumente API Endpoints.

Enterprise Feature: Dokumenten-Aehnlichkeitssuche basierend auf pgvector Embeddings.

Endpoints:
- GET  /documents/{document_id}/similar - Aehnliche Dokumente finden
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_active_user, get_db
from app.core.rate_limiting import limiter, get_user_identifier
from app.core.safe_errors import safe_error_log
from app.db.models import User
from app.services.search_service import SearchService

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/documents", tags=["Aehnliche Dokumente"])


# =============================================================================
# Pydantic Schemas - Similar Documents
# =============================================================================


class SimilarDocumentResponse(BaseModel):
    """Aehnliches Dokument mit Aehnlichkeitswert."""

    document_id: UUID
    filename: str
    document_type: str
    similarity_score: float = Field(..., description="Aehnlichkeitswert (0-1)")
    created_at: datetime
    text_preview: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class SimilarDocumentsListResponse(BaseModel):
    """Liste aehnlicher Dokumente."""

    document_id: UUID = Field(..., description="Quell-Dokument")
    similar_documents: List[SimilarDocumentResponse]
    total_found: int
    threshold_used: float


# =============================================================================
# API Endpoints
# =============================================================================


@router.get(
    "/{document_id}/similar",
    response_model=SimilarDocumentsListResponse,
    summary="Aehnliche Dokumente finden",
    description="Findet aehnliche Dokumente basierend auf Embedding-Aehnlichkeit (pgvector).",
    responses={
        200: {"description": "Liste aehnlicher Dokumente erfolgreich abgerufen"},
        404: {"description": "Quell-Dokument nicht gefunden"},
        429: {"description": "Rate Limit ueberschritten"},
        500: {"description": "Interner Serverfehler"},
    },
)
@limiter.limit("30/minute", key_func=get_user_identifier)
async def find_similar_documents(
    request: Request,
    document_id: UUID = Path(..., description="ID des Quell-Dokuments"),
    limit: int = Query(
        10,
        ge=1,
        le=50,
        description="Maximale Anzahl aehnlicher Dokumente"
    ),
    threshold: float = Query(
        0.6,
        ge=0.1,
        le=1.0,
        description="Minimaler Aehnlichkeitswert (0.1-1.0)"
    ),
    exclude_same_type: bool = Query(
        False,
        description="Dokumente desselben Typs ausschliessen"
    ),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> SimilarDocumentsListResponse:
    """
    Findet aehnliche Dokumente basierend auf Embedding-Aehnlichkeit.

    Verwendet pgvector fuer hochperformante Vektorsuche in der Datenbank.

    Args:
        request: FastAPI Request (fuer Rate Limiting)
        document_id: UUID des Quell-Dokuments
        limit: Maximale Anzahl Ergebnisse (1-50, Standard: 10)
        threshold: Minimaler Aehnlichkeitswert (0.1-1.0, Standard: 0.6)
        exclude_same_type: Dokumente desselben Typs ausschliessen (Standard: False)
        db: Datenbankverbindung
        current_user: Authentifizierter Benutzer

    Returns:
        Liste aehnlicher Dokumente mit Aehnlichkeitswerten

    Raises:
        HTTPException 404: Quell-Dokument nicht gefunden
        HTTPException 500: Fehler bei der Suche
    """
    logger.info(
        "similar_documents_request",
        document_id=str(document_id),
        user_id=str(current_user.id),
        limit=limit,
        threshold=threshold,
        exclude_same_type=exclude_same_type,
    )

    try:
        # Get search service singleton
        search_service = SearchService()

        # Find similar documents using the service
        results = await search_service.find_similar_documents(
            db=db,
            document_id=document_id,
            user_id=current_user.id,
            limit=limit,
            similarity_threshold=threshold,
            exclude_same_type=exclude_same_type,
        )

        # Convert results to response format
        similar_docs = [
            SimilarDocumentResponse(
                document_id=item.document_id,
                filename=item.filename,
                document_type=item.document_type.value,  # Convert enum to string
                similarity_score=item.similarity,
                created_at=item.created_at,
                text_preview=item.text_preview,
            )
            for item in results
        ]

        logger.info(
            "similar_documents_success",
            document_id=str(document_id),
            total_found=len(similar_docs),
        )

        return SimilarDocumentsListResponse(
            document_id=document_id,
            similar_documents=similar_docs,
            total_found=len(similar_docs),
            threshold_used=threshold,
        )

    except ValueError as e:
        # Document not found or access denied
        logger.warning(
            "similar_documents_not_found",
            document_id=str(document_id),
            user_id=str(current_user.id),
            **safe_error_log(e),
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dokument nicht gefunden oder kein Zugriff: {document_id}",
        )
    except Exception as e:
        logger.error(
            "similar_documents_error",
            document_id=str(document_id),
            user_id=str(current_user.id),
            **safe_error_log(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Fehler beim Suchen aehnlicher Dokumente",
        )
