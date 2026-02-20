"""
Favorites Management API Endpoints.

Ermöglicht Benutzern, Dokumente als Favoriten zu markieren:
- Favoriten hinzufügen/entfernen
- Favoriten mit Notizen versehen
- Prioritäten setzen
- Favoriten-Liste abrufen

Feinpoliert und durchdacht - Schneller Zugriff auf wichtige Dokumente.
"""

import structlog
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload

from app.db.models import User, Document, DocumentFavorite
from app.api.dependencies import get_current_user, get_db
from app.db.schemas import (
    FavoriteCreate,
    FavoriteUpdate,
    FavoriteResponse,
    FavoriteWithDocumentResponse,
    FavoriteListResponse,
    FavoriteSortField,
)

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/favorites", tags=["favorites"])


@router.post(
    "/",
    response_model=FavoriteResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Favorit hinzufügen",
    description="Markiert ein Dokument als Favorit."
)
async def add_favorite(
    favorite_data: FavoriteCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> FavoriteResponse:
    """Dokument als Favorit markieren."""
    # Prüfe ob Dokument existiert
    doc_result = await db.execute(
        select(Document).where(Document.id == favorite_data.document_id)
    )
    document = doc_result.scalar_one_or_none()

    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dokument nicht gefunden"
        )

    # Prüfe ob Benutzer Zugriff auf das Dokument hat
    if document.owner_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Kein Zugriff auf dieses Dokument"
        )

    # Prüfe ob bereits Favorit
    existing = await db.execute(
        select(DocumentFavorite).where(
            DocumentFavorite.user_id == current_user.id,
            DocumentFavorite.document_id == favorite_data.document_id
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Dokument ist bereits ein Favorit"
        )

    # Erstelle Favorit
    favorite = DocumentFavorite(
        user_id=current_user.id,
        document_id=favorite_data.document_id,
        note=favorite_data.note,
        priority=favorite_data.priority
    )

    db.add(favorite)
    await db.commit()
    await db.refresh(favorite)

    logger.info(
        "favorite_added",
        favorite_id=str(favorite.id),
        document_id=str(favorite_data.document_id),
        user_id=str(current_user.id)
    )

    # Rückgabe mit Dokument-Infos
    response = FavoriteResponse.model_validate(favorite)
    response.document_filename = document.original_filename or document.filename
    response.document_status = document.status

    return response


@router.get(
    "/",
    response_model=FavoriteListResponse,
    summary="Favoriten auflisten",
    description="Gibt alle Favoriten des aktuellen Benutzers zurück."
)
async def list_favorites(
    page: int = Query(1, ge=1, description="Seitennummer (1-basiert)"),
    per_page: int = Query(50, ge=1, le=100, description="Eintraege pro Seite"),
    sort_by: FavoriteSortField = Query(FavoriteSortField.PRIORITY, description="Sortierung"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> FavoriteListResponse:
    """Liste aller Favoriten des Benutzers."""
    # Total count
    count_result = await db.execute(
        select(func.count(DocumentFavorite.id)).where(
            DocumentFavorite.user_id == current_user.id
        )
    )
    total = count_result.scalar() or 0

    # Query mit Join zu Document
    query = (
        select(DocumentFavorite, Document)
        .join(Document, DocumentFavorite.document_id == Document.id)
        .where(DocumentFavorite.user_id == current_user.id)
    )

    # Sortierung
    if sort_by == FavoriteSortField.PRIORITY:
        query = query.order_by(DocumentFavorite.priority.desc(), DocumentFavorite.created_at.desc())
    else:
        query = query.order_by(DocumentFavorite.created_at.desc())

    query = query.limit(per_page).offset((page - 1) * per_page)
    result = await db.execute(query)
    rows = result.all()

    favorites = []
    for fav, doc in rows:
        response = FavoriteResponse.model_validate(fav)
        response.document_filename = doc.original_filename or doc.filename
        response.document_status = doc.status
        favorites.append(response)

    return FavoriteListResponse(
        total=total,
        favorites=favorites
    )


@router.get(
    "/{favorite_id}",
    response_model=FavoriteWithDocumentResponse,
    summary="Favorit-Details",
    description="Gibt Details eines spezifischen Favoriten zurück."
)
async def get_favorite(
    favorite_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> FavoriteWithDocumentResponse:
    """Favorit-Details abrufen."""
    result = await db.execute(
        select(DocumentFavorite, Document)
        .join(Document, DocumentFavorite.document_id == Document.id)
        .where(
            DocumentFavorite.id == favorite_id,
            DocumentFavorite.user_id == current_user.id
        )
    )
    row = result.one_or_none()

    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Favorit nicht gefunden"
        )

    fav, doc = row
    response = FavoriteWithDocumentResponse.model_validate(fav)
    response.document_filename = doc.original_filename or doc.filename
    response.document_status = doc.status
    response.document = {
        "id": str(doc.id),
        "filename": doc.original_filename or doc.filename,
        "status": doc.status,
        "mime_type": doc.mime_type,
        "file_size": doc.file_size,
        "ocr_confidence": doc.ocr_confidence,
        "created_at": doc.created_at.isoformat() if doc.created_at else None,
    }

    return response


@router.patch(
    "/{favorite_id}",
    response_model=FavoriteResponse,
    summary="Favorit aktualisieren",
    description="Aktualisiert Notiz oder Priorität eines Favoriten."
)
async def update_favorite(
    favorite_id: UUID,
    favorite_data: FavoriteUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> FavoriteResponse:
    """Favorit aktualisieren."""
    result = await db.execute(
        select(DocumentFavorite, Document)
        .join(Document, DocumentFavorite.document_id == Document.id)
        .where(
            DocumentFavorite.id == favorite_id,
            DocumentFavorite.user_id == current_user.id
        )
    )
    row = result.one_or_none()

    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Favorit nicht gefunden"
        )

    fav, doc = row

    # Update fields
    update_data = favorite_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(fav, field, value)

    await db.commit()
    await db.refresh(fav)

    logger.info(
        "favorite_updated",
        favorite_id=str(favorite_id),
        user_id=str(current_user.id),
        updated_fields=list(update_data.keys())
    )

    response = FavoriteResponse.model_validate(fav)
    response.document_filename = doc.original_filename or doc.filename
    response.document_status = doc.status

    return response


@router.delete(
    "/{favorite_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    summary="Favorit entfernen",
    description="Entfernt ein Dokument aus den Favoriten."
)
async def remove_favorite(
    favorite_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> Response:
    """Favorit entfernen."""
    result = await db.execute(
        select(DocumentFavorite).where(
            DocumentFavorite.id == favorite_id,
            DocumentFavorite.user_id == current_user.id
        )
    )
    favorite = result.scalar_one_or_none()

    if not favorite:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Favorit nicht gefunden"
        )

    await db.delete(favorite)
    await db.commit()

    logger.info(
        "favorite_removed",
        favorite_id=str(favorite_id),
        user_id=str(current_user.id)
    )

    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete(
    "/document/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    summary="Favorit nach Dokument-ID entfernen",
    description="Entfernt ein Dokument aus den Favoriten anhand der Dokument-ID."
)
async def remove_favorite_by_document(
    document_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> Response:
    """Favorit anhand der Dokument-ID entfernen."""
    result = await db.execute(
        select(DocumentFavorite).where(
            DocumentFavorite.document_id == document_id,
            DocumentFavorite.user_id == current_user.id
        )
    )
    favorite = result.scalar_one_or_none()

    if not favorite:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dokument ist kein Favorit"
        )

    await db.delete(favorite)
    await db.commit()

    logger.info(
        "favorite_removed_by_document",
        document_id=str(document_id),
        user_id=str(current_user.id)
    )

    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/check/{document_id}",
    summary="Prüfen ob Favorit",
    description="Prüft ob ein Dokument als Favorit markiert ist."
)
async def check_favorite(
    document_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> dict:
    """Prüft ob ein Dokument ein Favorit ist."""
    result = await db.execute(
        select(DocumentFavorite).where(
            DocumentFavorite.document_id == document_id,
            DocumentFavorite.user_id == current_user.id
        )
    )
    favorite = result.scalar_one_or_none()

    return {
        "document_id": str(document_id),
        "is_favorite": favorite is not None,
        "favorite_id": str(favorite.id) if favorite else None,
        "note": favorite.note if favorite else None,
        "priority": favorite.priority if favorite else None
    }
