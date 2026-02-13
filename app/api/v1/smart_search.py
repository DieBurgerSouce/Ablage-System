# -*- coding: utf-8 -*-
"""
Smart Search API Router.

Intelligente Suche mit automatischer Erkennung von NLQ vs. Keyword-Suche.
Feature #1 der Feature-Roadmap (Phase 2026 Q1)
"""

from typing import Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_active_user, get_db
from app.core.rate_limiting import limiter, get_user_identifier
from app.core.safe_errors import safe_error_detail
from app.db.models import User
from app.db.schemas import SearchFilters
from app.services.smart_search_service import (
    DetectedQueryType,
    SmartSearchService,
    get_smart_search_service,
)

router = APIRouter(prefix="/smart-search", tags=["smart-search"])


# ============================================================================
# Schemas
# ============================================================================


class SmartSearchEntityResponse(BaseModel):
    """Gefundene Business Entity."""
    entity_id: str
    entity_type: str
    name: str
    display_name: Optional[str] = None
    match_type: str
    confidence: float

    model_config = ConfigDict(from_attributes=True)


class SmartSearchInterpretationResponse(BaseModel):
    """Interpretation der Suchanfrage."""
    detected_type: str
    confidence: float
    reasoning: str
    nlq_intent: Optional[str] = None
    entities_found: List[str] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class SmartSearchDocumentResponse(BaseModel):
    """Dokument-Ergebnis."""
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

    model_config = ConfigDict(from_attributes=True)


class SmartSearchFacetsResponse(BaseModel):
    """Verfuegbare Facetten/Filter."""
    document_types: Dict[str, int] = Field(default_factory=dict)
    statuses: Dict[str, int] = Field(default_factory=dict)
    date_ranges: Dict[str, int] = Field(default_factory=dict)
    entities: Dict[str, int] = Field(default_factory=dict)
    total_count: int

    model_config = ConfigDict(from_attributes=True)


class SmartSearchResponse(BaseModel):
    """Antwort der Smart Search."""
    query: str
    detected_type: str
    interpretation: SmartSearchInterpretationResponse
    documents: List[SmartSearchDocumentResponse]
    total_documents: int
    entities: List[SmartSearchEntityResponse]
    total_entities: int
    natural_response: Optional[str] = None
    nlq_confidence: Optional[float] = None
    suggestions: List[str] = Field(default_factory=list)
    facets: Optional[SmartSearchFacetsResponse] = None
    search_time_ms: float
    document_search_time_ms: Optional[float] = None
    entity_search_time_ms: Optional[float] = None
    nlq_processing_time_ms: Optional[float] = None

    model_config = ConfigDict(from_attributes=True)


class SmartSearchRequest(BaseModel):
    """Anfrage fuer Smart Search."""
    query: str = Field(..., min_length=1, max_length=500, description="Suchanfrage")
    filters: Optional[SearchFilters] = Field(None, description="Optional Filter")
    limit: int = Field(20, ge=1, le=100, description="Maximale Anzahl Ergebnisse")
    include_suggestions: bool = Field(True, description="Query-Suggestions generieren")
    include_facets: bool = Field(True, description="Facetten berechnen")
    force_mode: Optional[str] = Field(None, description="Erzwungener Modus: 'nlq' oder 'keyword'")

    model_config = ConfigDict(from_attributes=True)


class AutocompleteResponse(BaseModel):
    """Autocomplete-Vorschlaege."""
    suggestions: List[str]

    model_config = ConfigDict(from_attributes=True)


# ============================================================================
# Endpoints
# ============================================================================


@router.post("", response_model=SmartSearchResponse)
@limiter.limit("100/minute", key_func=get_user_identifier)
async def smart_search(
    request: Request,
    search_request: SmartSearchRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> SmartSearchResponse:
    """
    Intelligente Suche mit automatischer Erkennung.

    Erkennt automatisch ob die Anfrage eine natuerlichsprachliche Frage
    ("Zeige mir alle Rechnungen von Mueller") oder eine Keyword-Suche
    ("Mueller Rechnung 2025") ist und routet entsprechend.

    Kombiniert:
    - NLQ-Verarbeitung fuer natuerliche Fragen
    - Unified Search fuer Keywords (FTS + Semantic)
    - Entity-Suche fuer Kunden/Lieferanten

    Args:
        request: FastAPI Request (fuer Rate Limiting)
        search_request: Suchanfrage mit Parametern
        db: Datenbank-Session
        current_user: Aktuell angemeldeter Benutzer

    Returns:
        Kombinierte Such-Ergebnisse mit Interpretation

    Raises:
        HTTPException: Bei Fehler in der Verarbeitung
    """
    try:
        service = get_smart_search_service()

        # Force-Mode validieren
        force_mode = None
        if search_request.force_mode:
            try:
                force_mode = DetectedQueryType(search_request.force_mode.lower())
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Ungueltiger force_mode: {search_request.force_mode}. "
                           f"Erlaubt: 'nlq', 'keyword'",
                )

        # Suche durchfuehren
        result = await service.search(
            db=db,
            query=search_request.query,
            user_id=current_user.id,
            company_id=current_user.company_id,
            filters=search_request.filters,
            limit=search_request.limit,
            include_suggestions=search_request.include_suggestions,
            include_facets=search_request.include_facets,
            force_mode=force_mode,
        )

        # Response konvertieren
        return SmartSearchResponse(
            query=result.query,
            detected_type=result.detected_type.value,
            interpretation=SmartSearchInterpretationResponse(
                detected_type=result.interpretation.detected_type.value,
                confidence=result.interpretation.confidence,
                reasoning=result.interpretation.reasoning,
                nlq_intent=result.interpretation.nlq_intent,
                entities_found=result.interpretation.entities_found,
            ),
            documents=[
                SmartSearchDocumentResponse(
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
                )
                for doc in result.documents
            ],
            total_documents=result.total_documents,
            entities=[
                SmartSearchEntityResponse(
                    entity_id=entity.entity_id,
                    entity_type=entity.entity_type,
                    name=entity.name,
                    display_name=entity.display_name,
                    match_type=entity.match_type,
                    confidence=entity.confidence,
                )
                for entity in result.entities
            ],
            total_entities=result.total_entities,
            natural_response=result.natural_response,
            nlq_confidence=result.nlq_confidence,
            suggestions=result.suggestions,
            facets=SmartSearchFacetsResponse(
                document_types=result.facets.document_types,
                statuses=result.facets.statuses,
                date_ranges=result.facets.date_ranges,
                entities=result.facets.entities,
                total_count=result.facets.total_count,
            ) if result.facets else None,
            search_time_ms=result.search_time_ms,
            document_search_time_ms=result.document_search_time_ms,
            entity_search_time_ms=result.entity_search_time_ms,
            nlq_processing_time_ms=result.nlq_processing_time_ms,
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=safe_error_detail(e, "Smart Search"),
        )


@router.get("/autocomplete", response_model=AutocompleteResponse)
@limiter.limit("200/minute", key_func=get_user_identifier)
async def autocomplete(
    request: Request,
    q: str = Query(..., min_length=1, max_length=100, description="Teilweise eingegebene Query"),
    limit: int = Query(10, ge=1, le=20, description="Maximale Anzahl Vorschlaege"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> AutocompleteResponse:
    """
    Autocomplete-Vorschlaege fuer Smart Search.

    Generiert Vorschlaege basierend auf haeufigen NLQ-Patterns und
    bereits bekannten Queries.

    Args:
        request: FastAPI Request (fuer Rate Limiting)
        q: Teilweise eingegebene Query
        limit: Maximale Anzahl Vorschlaege
        db: Datenbank-Session
        current_user: Aktuell angemeldeter Benutzer

    Returns:
        Liste von Autocomplete-Vorschlaegen

    Raises:
        HTTPException: Bei Fehler in der Verarbeitung
    """
    try:
        service = get_smart_search_service()

        suggestions = await service.autocomplete(
            db=db,
            query=q,
            limit=limit,
        )

        return AutocompleteResponse(suggestions=suggestions)

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=safe_error_detail(e, "Autocomplete"),
        )


@router.get("/health", status_code=status.HTTP_200_OK)
async def health_check() -> Dict[str, str]:
    """
    Health-Check fuer Smart Search Service.

    Returns:
        Status-Information
    """
    return {
        "status": "healthy",
        "service": "smart-search",
        "version": "1.0.0",
    }
