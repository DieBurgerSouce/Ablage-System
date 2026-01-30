"""Life Events API Router.

Endpoints fuer den proaktiven Lebensberater.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user
from app.db.session import get_async_session
from app.services.privat.life_events.life_event_engine import LifeEventEngine

router = APIRouter(prefix="/privat/life-events", tags=["life-events"])


class LifeEventCreate(BaseModel):
    """Schema fuer neues Lebensereignis."""
    event_type: str = Field(..., pattern="^(umzug|heirat|kind|jobwechsel|ruhestand|todesfall|immobilienkauf|scheidung)$")
    event_date: Optional[datetime] = None
    notes: Optional[str] = Field(None, max_length=2000)


class ChecklistItemUpdate(BaseModel):
    """Schema fuer Checklist-Update."""
    item_id: str = Field(..., pattern="^[a-z_]{1,64}$")
    done: bool


class LifeEventResponse(BaseModel):
    """Schema fuer Lebensereignis-Antwort."""
    id: UUID
    event_type: str
    title: str
    description: Optional[str] = None
    event_date: datetime
    status: str
    detection_source: str
    checklist: list[dict]
    recommendations: list[dict]
    financial_impact: dict
    created_at: datetime

    model_config = {"from_attributes": True}


@router.get("/types")
async def get_event_types(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
) -> dict[str, dict[str, str]]:
    """Gibt alle verfuegbaren Event-Typen zurueck."""
    service = LifeEventEngine(db)
    return await service.get_event_types()


@router.post("", response_model=LifeEventResponse, status_code=status.HTTP_201_CREATED)
async def create_life_event(
    data: LifeEventCreate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
) -> LifeEventResponse:
    """Erstellt ein neues Lebensereignis mit Checkliste."""
    service = LifeEventEngine(db)
    event = await service.create_life_event(
        user_id=current_user["id"],
        company_id=current_user["company_id"],
        event_type=data.event_type,
        event_date=data.event_date,
        notes=data.notes,
    )
    await db.commit()
    return event


@router.get("", response_model=list[LifeEventResponse])
async def list_life_events(
    status_filter: Optional[str] = None,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
) -> list[LifeEventResponse]:
    """Listet alle Lebensereignisse des Benutzers."""
    service = LifeEventEngine(db)
    events = await service.get_life_events(
        user_id=current_user["id"],
        company_id=current_user["company_id"],
        status_filter=status_filter,
    )
    return events


@router.get("/{event_id}", response_model=LifeEventResponse)
async def get_life_event(
    event_id: UUID,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
) -> LifeEventResponse:
    """Holt ein einzelnes Lebensereignis."""
    service = LifeEventEngine(db)
    event = await service.get_life_event(
        event_id=event_id,
        company_id=current_user["company_id"],
    )
    if not event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lebensereignis nicht gefunden",
        )
    return event


@router.patch("/{event_id}/checklist", response_model=LifeEventResponse)
async def update_checklist(
    event_id: UUID,
    data: ChecklistItemUpdate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
) -> LifeEventResponse:
    """Aktualisiert einen Checklist-Eintrag."""
    service = LifeEventEngine(db)
    event = await service.update_checklist_item(
        event_id=event_id,
        company_id=current_user["company_id"],
        item_id=data.item_id,
        done=data.done,
    )
    if not event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lebensereignis nicht gefunden",
        )
    await db.commit()
    return event


@router.post("/{event_id}/complete", response_model=LifeEventResponse)
async def complete_life_event(
    event_id: UUID,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
) -> LifeEventResponse:
    """Markiert ein Lebensereignis als abgeschlossen."""
    service = LifeEventEngine(db)
    event = await service.complete_life_event(
        event_id=event_id,
        company_id=current_user["company_id"],
    )
    if not event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lebensereignis nicht gefunden",
        )
    await db.commit()
    return event


@router.get("/stats/active-count")
async def get_active_count(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
) -> dict[str, int]:
    """Zaehlt aktive Lebensereignisse."""
    service = LifeEventEngine(db)
    count = await service.get_active_events_count(
        user_id=current_user["id"],
        company_id=current_user["company_id"],
    )
    return {"active_count": count}
