from typing import List, Any
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Response, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.api import dependencies
from app.db import models
from app.api.schemas.tunes import TuneCreate, TuneUpdate, TuneResponse

router = APIRouter()


@router.get("/", response_model=List[TuneResponse])
async def get_tunes(
    db: AsyncSession = Depends(dependencies.get_db),
    current_user: models.User = Depends(dependencies.get_current_active_user),
    skip: int = Query(0, ge=0, description="Anzahl zu ueberspringender Eintraege"),
    limit: int = Query(100, ge=1, le=200, description="Maximale Anzahl zurueckzugebender Eintraege"),
    active_only: bool = False
) -> Any:
    """
    Alle Tunes abrufen (Authentifizierung erforderlich).

    Tunes definieren kontextspezifische Verarbeitungsregeln für Dokumente.
    """
    query = select(models.Tune)
    if active_only:
        query = query.where(models.Tune.is_active == True)

    query = query.offset(skip).limit(limit)
    result = await db.execute(query)
    return result.scalars().all()


@router.get("/{tune_id}", response_model=TuneResponse)
async def get_tune(
    tune_id: UUID,
    db: AsyncSession = Depends(dependencies.get_db),
    current_user: models.User = Depends(dependencies.get_current_superuser)  # Y.3 SECURITY FIX: Admin only
) -> Any:
    """
    Ein einzelnes Tune anhand der ID abrufen (Admin only).

    **REQUIRES ADMIN AUTHENTICATION**

    Args:
        tune_id: UUID des Tunes

    Returns:
        TuneResponse mit allen Tune-Details

    Raises:
        404: Wenn das Tune nicht gefunden wurde
        403: Wenn Benutzer kein Admin ist
    """
    query = select(models.Tune).where(models.Tune.id == tune_id)
    result = await db.execute(query)
    tune = result.scalars().first()

    if not tune:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tune nicht gefunden"
        )

    return tune


@router.post("/", response_model=TuneResponse, status_code=status.HTTP_201_CREATED)
async def create_tune(
    tune_in: TuneCreate,
    db: AsyncSession = Depends(dependencies.get_db),
    current_user: models.User = Depends(dependencies.get_current_superuser)
) -> Any:
    """
    Create new tune (Admin only).
    """
    # Check for name duplication
    query = select(models.Tune).where(models.Tune.name == tune_in.name)
    result = await db.execute(query)
    if result.scalars().first():
        raise HTTPException(
            status_code=400,
            detail="Ein Tune mit diesem Namen existiert bereits."
        )

    tune = models.Tune(**tune_in.model_dump())
    db.add(tune)
    await db.commit()
    await db.refresh(tune)
    return tune

@router.put("/{tune_id}", response_model=TuneResponse)
async def update_tune(
    tune_id: UUID,
    tune_in: TuneUpdate,
    db: AsyncSession = Depends(dependencies.get_db),
    current_user: models.User = Depends(dependencies.get_current_superuser)
) -> Any:
    """
    Update a tune (Admin only).
    """
    query = select(models.Tune).where(models.Tune.id == tune_id)
    result = await db.execute(query)
    tune = result.scalars().first()

    if not tune:
        raise HTTPException(status_code=404, detail="Tune nicht gefunden")

    update_data = tune_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(tune, field, value)

    db.add(tune)
    await db.commit()
    await db.refresh(tune)
    return tune

@router.delete("/{tune_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def delete_tune(
    tune_id: UUID,
    db: AsyncSession = Depends(dependencies.get_db),
    current_user: models.User = Depends(dependencies.get_current_superuser)
) -> Response:
    """
    Delete a tune (Admin only). System tunes cannot be deleted.
    """
    query = select(models.Tune).where(models.Tune.id == tune_id)
    result = await db.execute(query)
    tune = result.scalars().first()

    if not tune:
        raise HTTPException(status_code=404, detail="Tune nicht gefunden")

    if tune.is_system:
        raise HTTPException(status_code=400, detail="System-Tunes können nicht gelöscht werden.")

    await db.delete(tune)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
