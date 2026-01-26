"""
Tag Administration API Endpoints.

Provides tag management for admins:
- CRUD operations for tags
- System tags protection
- Optional Tune linking

All endpoints require admin/superuser permissions.
"""

from typing import List
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, Response, status, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db, get_current_superuser
from app.db.models import User, Tag, Tune
from app.api.schemas.tags import TagCreate, TagUpdate, TagResponse

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/tags", tags=["Admin - Tags"])


# ==================== Endpoints ====================

@router.get(
    "",
    response_model=List[TagResponse],
    summary="Alle Tags abrufen",
    description="Ruft alle konfigurierten Tags ab"
)
async def get_tags(
    admin: User = Depends(get_current_superuser),
    db: AsyncSession = Depends(get_db),
    skip: int = Query(0, ge=0, description="Anzahl zu ueberspringender Eintraege"),
    limit: int = Query(100, ge=1, le=200, description="Maximale Anzahl zurueckzugebender Eintraege"),
    active_only: bool = Query(False, description="Nur aktive Tags anzeigen"),
    system_only: bool = Query(False, description="Nur System-Tags anzeigen"),
) -> List[TagResponse]:
    """
    Ruft alle Tags ab.

    Tags werden verwendet fuer:
    - Dokumentenkategorisierung
    - Optionale Verknuepfung mit Tunes fuer OCR-Feintuning

    Nur fuer Administratoren zugaenglich.
    """
    query = select(Tag)

    if active_only:
        query = query.where(Tag.is_active == True)

    if system_only:
        query = query.where(Tag.is_system == True)

    query = query.order_by(Tag.is_system.desc(), Tag.name).offset(skip).limit(limit)
    result = await db.execute(query)
    tags = result.scalars().all()

    logger.debug(
        "tags_listed",
        user_id=str(admin.id),
        count=len(tags),
        active_only=active_only,
        system_only=system_only
    )

    return tags


@router.get(
    "/{tag_id}",
    response_model=TagResponse,
    summary="Tag abrufen",
    description="Ruft ein einzelnes Tag anhand der ID ab"
)
async def get_tag(
    tag_id: UUID,
    admin: User = Depends(get_current_superuser),
    db: AsyncSession = Depends(get_db),
) -> TagResponse:
    """
    Ruft ein einzelnes Tag anhand der ID ab.

    Args:
        tag_id: UUID des Tags

    Returns:
        TagResponse mit allen Tag-Details

    Raises:
        404: Wenn das Tag nicht gefunden wurde
    """
    query = select(Tag).where(Tag.id == tag_id)
    result = await db.execute(query)
    tag = result.scalars().first()

    if not tag:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tag nicht gefunden"
        )

    return tag


@router.post(
    "",
    response_model=TagResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Tag erstellen",
    description="Erstellt ein neues Tag"
)
async def create_tag(
    tag_in: TagCreate,
    admin: User = Depends(get_current_superuser),
    db: AsyncSession = Depends(get_db),
) -> TagResponse:
    """
    Erstellt ein neues Tag.

    Tags werden verwendet fuer Dokumentenkategorisierung und
    koennen optional mit Tunes verknuepft werden.

    Nur fuer Administratoren zugaenglich.
    """
    # Check for name duplication
    query = select(Tag).where(Tag.name == tag_in.name)
    result = await db.execute(query)
    if result.scalars().first():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ein Tag mit diesem Namen existiert bereits."
        )

    # Validate tune_id if provided
    if tag_in.tune_id:
        tune_query = select(Tune).where(Tune.id == tag_in.tune_id)
        tune_result = await db.execute(tune_query)
        if not tune_result.scalars().first():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Das angegebene Tune existiert nicht."
            )

    tag = Tag(**tag_in.model_dump())
    db.add(tag)
    await db.commit()
    await db.refresh(tag)

    logger.info(
        "tag_created",
        user_id=str(admin.id),
        tag_id=str(tag.id),
        tag_name=tag.name
    )

    return tag


@router.put(
    "/{tag_id}",
    response_model=TagResponse,
    summary="Tag aktualisieren",
    description="Aktualisiert ein bestehendes Tag"
)
async def update_tag(
    tag_id: UUID,
    tag_in: TagUpdate,
    admin: User = Depends(get_current_superuser),
    db: AsyncSession = Depends(get_db),
) -> TagResponse:
    """
    Aktualisiert ein bestehendes Tag.

    System-Tags koennen bearbeitet, aber nicht geloescht werden.

    Nur fuer Administratoren zugaenglich.
    """
    query = select(Tag).where(Tag.id == tag_id)
    result = await db.execute(query)
    tag = result.scalars().first()

    if not tag:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tag nicht gefunden"
        )

    # Check for name duplication if name is being changed
    if tag_in.name and tag_in.name != tag.name:
        name_query = select(Tag).where(Tag.name == tag_in.name)
        name_result = await db.execute(name_query)
        if name_result.scalars().first():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Ein Tag mit diesem Namen existiert bereits."
            )

    # Validate tune_id if provided
    if tag_in.tune_id:
        tune_query = select(Tune).where(Tune.id == tag_in.tune_id)
        tune_result = await db.execute(tune_query)
        if not tune_result.scalars().first():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Das angegebene Tune existiert nicht."
            )

    update_data = tag_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(tag, field, value)

    db.add(tag)
    await db.commit()
    await db.refresh(tag)

    logger.info(
        "tag_updated",
        user_id=str(admin.id),
        tag_id=str(tag.id),
        tag_name=tag.name
    )

    return tag


@router.delete(
    "/{tag_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    summary="Tag loeschen",
    description="Loescht ein Tag (System-Tags koennen nicht geloescht werden)"
)
async def delete_tag(
    tag_id: UUID,
    admin: User = Depends(get_current_superuser),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """
    Loescht ein Tag.

    System-Tags (wie Eingangsrechnung, Ausgangsrechnung) koennen
    nicht geloescht werden.

    Nur fuer Administratoren zugaenglich.
    """
    query = select(Tag).where(Tag.id == tag_id)
    result = await db.execute(query)
    tag = result.scalars().first()

    if not tag:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tag nicht gefunden"
        )

    if tag.is_system:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="System-Tags koennen nicht geloescht werden."
        )

    tag_name = tag.name
    await db.delete(tag)
    await db.commit()

    logger.info(
        "tag_deleted",
        user_id=str(admin.id),
        tag_id=str(tag_id),
        tag_name=tag_name
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
