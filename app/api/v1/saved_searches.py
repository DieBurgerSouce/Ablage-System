# -*- coding: utf-8 -*-
"""
Saved Searches API Endpoint.

Verwaltet gespeicherte Such-Konfigurationen fuer Benutzer:
- Erstellen, Aendern, Loeschen von gespeicherten Suchen
- Ausfuehren von gespeicherten Suchen mit Statistik-Tracking
- Standard-Suche pro Benutzer
"""

from typing import List, Optional
from uuid import UUID
from datetime import datetime

from app.core.types import JSONDict

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, update, delete, and_, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from app.db.models import User
from app.db.models_saved_search import SavedSearch
from app.db.session import get_async_session
from app.api.dependencies import get_current_user
from app.core.safe_errors import safe_error_log
from app.db.schemas import SearchType
from app.services.unified_search_service import (
    UnifiedSearchService,
    UnifiedSearchMode,
    get_unified_search_service,
)

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/saved-searches", tags=["Gespeicherte Suchen"])


# ==================== Pydantic Schemas ====================

class SavedSearchFilters(BaseModel):
    """Filter-Konfiguration fuer gespeicherte Suchen."""
    document_type: Optional[str] = None
    status: Optional[str] = None
    date_from: Optional[str] = None
    date_to: Optional[str] = None
    tags: Optional[List[str]] = None
    entity_id: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class SavedSearchCreate(BaseModel):
    """Schema zum Erstellen einer gespeicherten Suche."""
    name: str = Field(..., min_length=1, max_length=200, description="Name der gespeicherten Suche")
    query: str = Field(..., min_length=1, description="Suchbegriff")
    search_type: str = Field(default="hybrid", description="Suchtyp: fts, semantic, hybrid")
    filters: Optional[JSONDict] = Field(default=None, description="Filter-Zustand")
    sort_field: Optional[str] = Field(default=None, max_length=50, description="Sortierfeld")
    sort_order: Optional[str] = Field(default=None, pattern="^(asc|desc)$", description="Sortierreihenfolge")
    is_default: bool = Field(default=False, description="Als Standard-Suche markieren")

    model_config = ConfigDict(from_attributes=True)


class SavedSearchUpdate(BaseModel):
    """Schema zum Aktualisieren einer gespeicherten Suche."""
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    query: Optional[str] = Field(None, min_length=1)
    search_type: Optional[str] = None
    filters: Optional[JSONDict] = None
    sort_field: Optional[str] = Field(None, max_length=50)
    sort_order: Optional[str] = Field(None, pattern="^(asc|desc)$")
    is_default: Optional[bool] = None

    model_config = ConfigDict(from_attributes=True)


class SavedSearchResponse(BaseModel):
    """Schema fuer gespeicherte Such-Antworten."""
    id: UUID
    user_id: UUID
    name: str
    query: str
    search_type: str
    filters: Optional[JSONDict] = None
    sort_field: Optional[str] = None
    sort_order: Optional[str] = None
    is_default: bool
    use_count: int
    last_used_at: Optional[datetime] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class SavedSearchListResponse(BaseModel):
    """Schema fuer Listen-Antworten."""
    searches: List[SavedSearchResponse]
    total: int

    model_config = ConfigDict(from_attributes=True)


# ==================== Helper Functions ====================

async def _get_saved_search_or_404(
    search_id: UUID,
    user_id: UUID,
    db: AsyncSession
) -> SavedSearch:
    """
    Holt eine gespeicherte Suche oder wirft 404.

    Stellt sicher, dass die Suche dem aktuellen Benutzer gehoert.
    """
    result = await db.execute(
        select(SavedSearch).where(
            and_(
                SavedSearch.id == search_id,
                SavedSearch.user_id == user_id
            )
        )
    )
    saved_search = result.scalar_one_or_none()

    if not saved_search:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Gespeicherte Suche nicht gefunden"
        )

    return saved_search


async def _unset_other_defaults(user_id: UUID, db: AsyncSession) -> None:
    """
    Setzt alle anderen Standard-Suchen des Benutzers zurueck.

    Nur eine Suche kann Standard sein.
    """
    await db.execute(
        update(SavedSearch)
        .where(SavedSearch.user_id == user_id)
        .values(is_default=False)
    )


# ==================== Endpoints ====================

@router.get(
    "",
    response_model=SavedSearchListResponse,
    summary="Gespeicherte Suchen auflisten",
    description="Listet alle gespeicherten Suchen des aktuellen Benutzers"
)
async def list_saved_searches(
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user),
) -> SavedSearchListResponse:
    """
    Listet alle gespeicherten Suchen des Benutzers.

    Sortierung: Nach Nutzungshaeufigkeit (use_count) absteigend,
    dann nach Erstellungsdatum absteigend.
    """
    try:
        # Query mit Sortierung
        result = await db.execute(
            select(SavedSearch)
            .where(SavedSearch.user_id == current_user.id)
            .order_by(SavedSearch.use_count.desc(), SavedSearch.created_at.desc())
        )
        searches = result.scalars().all()

        return SavedSearchListResponse(
            searches=[SavedSearchResponse.model_validate(s) for s in searches],
            total=len(searches)
        )
    except Exception as e:
        logger.error("Fehler beim Auflisten gespeicherter Suchen", **safe_error_log(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Fehler beim Laden der gespeicherten Suchen"
        )


@router.post(
    "",
    response_model=SavedSearchResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Gespeicherte Suche erstellen",
    description="Erstellt eine neue gespeicherte Such-Konfiguration"
)
async def create_saved_search(
    data: SavedSearchCreate,
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user),
) -> SavedSearchResponse:
    """
    Erstellt eine neue gespeicherte Suche.

    Der Name muss fuer den Benutzer eindeutig sein.
    Wenn is_default=True, werden alle anderen Standard-Suchen zurueckgesetzt.
    """
    try:
        # Wenn diese Suche Standard wird, andere zuruecksetzen
        if data.is_default:
            await _unset_other_defaults(current_user.id, db)

        # Neue Suche erstellen
        saved_search = SavedSearch(
            user_id=current_user.id,
            name=data.name,
            query=data.query,
            search_type=data.search_type,
            filters=data.filters,
            sort_field=data.sort_field,
            sort_order=data.sort_order,
            is_default=data.is_default,
        )

        db.add(saved_search)
        await db.commit()
        await db.refresh(saved_search)

        logger.info(
            "Gespeicherte Suche erstellt",
            saved_search_id=str(saved_search.id),
            user_id=str(current_user.id),
            name=data.name
        )

        return SavedSearchResponse.model_validate(saved_search)

    except IntegrityError as e:
        await db.rollback()
        # UniqueConstraint Verletzung - Name bereits vorhanden
        if "uq_saved_searches_user_name" in str(e):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Eine gespeicherte Suche mit dem Namen '{data.name}' existiert bereits"
            )
        logger.error("Integritaetsfehler beim Erstellen", **safe_error_log(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Fehler beim Erstellen der gespeicherten Suche"
        )
    except Exception as e:
        await db.rollback()
        logger.error("Fehler beim Erstellen gespeicherter Suche", **safe_error_log(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Fehler beim Erstellen der gespeicherten Suche"
        )


@router.get(
    "/{search_id}",
    response_model=SavedSearchResponse,
    summary="Gespeicherte Suche abrufen",
    description="Ruft Details einer gespeicherten Suche ab"
)
async def get_saved_search(
    search_id: UUID,
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user),
) -> SavedSearchResponse:
    """Ruft eine einzelne gespeicherte Suche ab."""
    saved_search = await _get_saved_search_or_404(search_id, current_user.id, db)
    return SavedSearchResponse.model_validate(saved_search)


@router.patch(
    "/{search_id}",
    response_model=SavedSearchResponse,
    summary="Gespeicherte Suche aktualisieren",
    description="Aktualisiert eine gespeicherte Such-Konfiguration"
)
async def update_saved_search(
    search_id: UUID,
    data: SavedSearchUpdate,
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user),
) -> SavedSearchResponse:
    """
    Aktualisiert eine gespeicherte Suche.

    Nur angegebene Felder werden aktualisiert (Partial Update).
    """
    saved_search = await _get_saved_search_or_404(search_id, current_user.id, db)

    try:
        # Wenn diese Suche Standard wird, andere zuruecksetzen
        if data.is_default is True and not saved_search.is_default:
            await _unset_other_defaults(current_user.id, db)

        # Felder aktualisieren (nur wenn gesetzt)
        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(saved_search, field, value)

        await db.commit()
        await db.refresh(saved_search)

        logger.info(
            "Gespeicherte Suche aktualisiert",
            saved_search_id=str(search_id),
            user_id=str(current_user.id)
        )

        return SavedSearchResponse.model_validate(saved_search)

    except IntegrityError as e:
        await db.rollback()
        # UniqueConstraint Verletzung - Name bereits vorhanden
        if "uq_saved_searches_user_name" in str(e):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Eine gespeicherte Suche mit dem Namen '{data.name}' existiert bereits"
            )
        logger.error("Integritaetsfehler beim Aktualisieren", **safe_error_log(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Fehler beim Aktualisieren der gespeicherten Suche"
        )
    except Exception as e:
        await db.rollback()
        logger.error("Fehler beim Aktualisieren", **safe_error_log(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Fehler beim Aktualisieren der gespeicherten Suche"
        )


@router.delete(
    "/{search_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Gespeicherte Suche loeschen",
    description="Loescht eine gespeicherte Suche"
)
async def delete_saved_search(
    search_id: UUID,
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user),
) -> None:
    """Loescht eine gespeicherte Suche."""
    saved_search = await _get_saved_search_or_404(search_id, current_user.id, db)

    try:
        await db.delete(saved_search)
        await db.commit()

        logger.info(
            "Gespeicherte Suche geloescht",
            saved_search_id=str(search_id),
            user_id=str(current_user.id)
        )
    except Exception as e:
        await db.rollback()
        logger.error("Fehler beim Loeschen", **safe_error_log(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Fehler beim Loeschen der gespeicherten Suche"
        )


@router.post(
    "/{search_id}/execute",
    response_model=JSONDict,
    summary="Gespeicherte Suche ausfuehren",
    description="Fuehrt eine gespeicherte Suche aus und aktualisiert Statistiken"
)
async def execute_saved_search(
    search_id: UUID,
    page: int = Query(default=1, ge=1, description="Seitennummer"),
    per_page: int = Query(default=20, ge=1, le=100, description="Ergebnisse pro Seite"),
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user),
    service: UnifiedSearchService = Depends(get_unified_search_service),
) -> JSONDict:
    """
    Fuehrt eine gespeicherte Suche aus.

    Inkrementiert use_count und aktualisiert last_used_at.
    Delegiert die eigentliche Suche an den UnifiedSearchService.
    """
    saved_search = await _get_saved_search_or_404(search_id, current_user.id, db)

    try:
        # Statistiken aktualisieren
        saved_search.use_count += 1
        saved_search.last_used_at = datetime.utcnow()
        await db.commit()

        # Parse search_type
        try:
            search_type = SearchType(saved_search.search_type)
        except ValueError:
            search_type = SearchType.HYBRID

        # Parse filters
        filters = None
        if saved_search.filters:
            from app.db.schemas import SearchFilters, DocumentType, ProcessingStatus

            filters_dict = saved_search.filters
            filters = SearchFilters(
                document_type=DocumentType(filters_dict.get("document_type")) if filters_dict.get("document_type") else None,
                status=ProcessingStatus(filters_dict.get("status")) if filters_dict.get("status") else None,
                date_from=filters_dict.get("date_from"),
                date_to=filters_dict.get("date_to"),
            )

        # Suche ausfuehren
        response = await service.search(
            db=db,
            query=saved_search.query,
            user_id=current_user.id,
            mode=UnifiedSearchMode.COMBINED,
            search_type=search_type,
            filters=filters,
            page=page,
            per_page=per_page,
            expand_synonyms=True,
            chunk_limit=10,
            chunk_threshold=0.5,
            rerank=True,
        )

        logger.info(
            "Gespeicherte Suche ausgefuehrt",
            saved_search_id=str(search_id),
            user_id=str(current_user.id),
            query=saved_search.query,
            use_count=saved_search.use_count
        )

        # Konvertiere Response zu Dict
        return {
            "saved_search_id": str(saved_search.id),
            "saved_search_name": saved_search.name,
            "query": response.query,
            "mode": response.mode.value,
            "documents": [
                {
                    "document_id": doc.document_id,
                    "filename": doc.filename,
                    "original_filename": doc.original_filename,
                    "score": doc.score,
                    "document_type": doc.document_type,
                    "status": doc.status,
                    "created_at": doc.created_at,
                    "mime_type": doc.mime_type,
                    "page_count": doc.page_count,
                    "extracted_text_preview": doc.extracted_text_preview,
                    "fts_score": doc.fts_score,
                    "semantic_score": doc.semantic_score,
                    "rerank_score": doc.rerank_score,
                }
                for doc in response.documents
            ],
            "total_documents": response.total_documents,
            "chunk_results": [
                {
                    "chunk_id": chunk.chunk_id,
                    "document_id": chunk.document_id,
                    "content": chunk.content,
                    "section_type": chunk.section_type,
                    "score": chunk.score,
                    "highlight": chunk.highlight,
                }
                for chunk in response.chunk_results
            ],
            "total_chunks": response.total_chunks,
            "search_time_ms": response.search_time_ms,
            "document_search_time_ms": response.document_search_time_ms,
            "chunk_search_time_ms": response.chunk_search_time_ms,
            "synonyms_used": response.synonyms_used,
        }

    except Exception as e:
        await db.rollback()
        logger.error("Fehler beim Ausfuehren der gespeicherten Suche", **safe_error_log(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Fehler beim Ausfuehren der gespeicherten Suche"
        )
