from typing import List, Any
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete

from app.api import dependencies
from app.db import models
from app.api.schemas.tunes import TuneCreate, TuneUpdate, TuneResponse

router = APIRouter()

@router.get("/", response_model=List[TuneResponse])
async def get_tunes(
    db: AsyncSession = Depends(dependencies.get_db),
    skip: int = 0,
    limit: int = 100,
    active_only: bool = False
) -> Any:
    """
    Retrieve all tunes.
    """
    query = select(models.Tune)
    if active_only:
        query = query.where(models.Tune.is_active == True)

    query = query.offset(skip).limit(limit)
    result = await db.execute(query)
    return result.scalars().all()

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
            detail="A tune with this name already exists."
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
        raise HTTPException(status_code=404, detail="Tune not found")

    update_data = tune_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(tune, field, value)

    db.add(tune)
    await db.commit()
    await db.refresh(tune)
    return tune

@router.delete("/{tune_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_tune(
    tune_id: UUID,
    db: AsyncSession = Depends(dependencies.get_db),
    current_user: models.User = Depends(dependencies.get_current_superuser)
) -> None:
    """
    Delete a tune (Admin only). System tunes cannot be deleted.
    """
    query = select(models.Tune).where(models.Tune.id == tune_id)
    result = await db.execute(query)
    tune = result.scalars().first()

    if not tune:
        raise HTTPException(status_code=404, detail="Tune not found")

    if tune.is_system:
        raise HTTPException(status_code=400, detail="System tunes cannot be deleted.")

    await db.delete(tune)
    await db.commit()
