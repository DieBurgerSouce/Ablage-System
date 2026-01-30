"""Event-Sourcing API - Event Store und Projektionen."""

import structlog
from typing import List, Optional, Dict, Any
from uuid import UUID
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db, get_current_user
from app.core.safe_errors import safe_error_detail, safe_error_log
from app.db.models import User
from app.services.event_sourcing import EventStore, ProjectionService, SnapshotService

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/event-sourcing", tags=["event-sourcing"])


# ============================================================================
# Pydantic Models
# ============================================================================


class EventResponse(BaseModel):
    """Event-Response Model."""

    event_id: UUID
    aggregate_type: str
    aggregate_id: UUID
    sequence_number: int
    event_type: str
    event_data: Dict[str, Any]
    metadata: Dict[str, Any]
    correlation_id: Optional[UUID]
    causation_id: Optional[UUID]
    user_id: Optional[UUID]
    created_at: datetime

    class Config:
        from_attributes = True


class SnapshotResponse(BaseModel):
    """Snapshot-Response Model."""

    snapshot_id: UUID
    aggregate_type: str
    aggregate_id: UUID
    sequence_number: int
    state: Dict[str, Any]
    version: int
    created_at: datetime

    class Config:
        from_attributes = True


class ProjectionResponse(BaseModel):
    """Projection-Response Model."""

    aggregate_type: str
    aggregate_id: UUID
    state: Dict[str, Any]
    event_count: int
    last_sequence: int


class EventStatsResponse(BaseModel):
    """Event-Statistiken Response."""

    total_events: int
    events_by_type: Dict[str, int]
    events_by_aggregate: Dict[str, int]
    snapshots_count: int


# ============================================================================
# API Endpoints
# ============================================================================


@router.get(
    "/events/{aggregate_type}/{aggregate_id}",
    response_model=List[EventResponse],
    summary="Events abrufen",
    description="Holt alle Events fuer ein Aggregat in zeitlicher Reihenfolge."
)
async def get_events(
    aggregate_type: str,
    aggregate_id: UUID,
    after_sequence: int = Query(0, description="Nur Events nach dieser Sequenznummer"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> List[EventResponse]:
    """Holt Events fuer ein Aggregat."""
    try:
        event_store = EventStore()

        events = await event_store.get_events(
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            company_id=current_user.company_id,
            after_sequence=after_sequence,
            db=db,
        )

        return [
            EventResponse(
                event_id=e.event_id,
                aggregate_type=e.aggregate_type,
                aggregate_id=e.aggregate_id,
                sequence_number=e.sequence_number,
                event_type=e.event_type,
                event_data=e.event_data,
                metadata=e.metadata,
                correlation_id=e.correlation_id,
                causation_id=e.causation_id,
                user_id=e.user_id,
                created_at=e.created_at,
            )
            for e in events
        ]

    except ValueError as e:
        logger.warning("events_abruf_fehler", **safe_error_log(e))
        raise HTTPException(status_code=400, detail=safe_error_detail(e, "Event-Sourcing"))
    except Exception as e:
        logger.error("events_abruf_fehler", **safe_error_log(e))
        raise HTTPException(status_code=500, detail="Fehler beim Abrufen der Events")


@router.get(
    "/snapshot/{aggregate_type}/{aggregate_id}",
    response_model=Optional[SnapshotResponse],
    summary="Snapshot abrufen",
    description="Holt den neuesten Snapshot fuer ein Aggregat."
)
async def get_snapshot(
    aggregate_type: str,
    aggregate_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Optional[SnapshotResponse]:
    """Holt den neuesten Snapshot."""
    try:
        snapshot_service = SnapshotService()

        snapshot = await snapshot_service.get_latest_snapshot(
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            company_id=current_user.company_id,
            db=db,
        )

        if not snapshot:
            return None

        return SnapshotResponse(
            snapshot_id=snapshot.snapshot_id,
            aggregate_type=snapshot.aggregate_type,
            aggregate_id=snapshot.aggregate_id,
            sequence_number=snapshot.sequence_number,
            state=snapshot.state,
            version=snapshot.version,
            created_at=snapshot.created_at,
        )

    except Exception as e:
        logger.error("snapshot_abruf_fehler", **safe_error_log(e))
        raise HTTPException(status_code=500, detail="Fehler beim Abrufen des Snapshots")


@router.get(
    "/projection/{aggregate_type}/{aggregate_id}",
    response_model=ProjectionResponse,
    summary="Projektion abrufen",
    description="Rekonstruiert den aktuellen Zustand durch Event-Replay."
)
async def get_projection(
    aggregate_type: str,
    aggregate_id: UUID,
    at_sequence: Optional[int] = Query(None, description="Zustand bei Sequenznummer (Zeitreise)"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ProjectionResponse:
    """Projiziert den aktuellen Zustand."""
    try:
        projection_service = ProjectionService()
        event_store = EventStore()

        # Projektion durchfuehren
        if at_sequence is not None:
            state = await projection_service.project_at_sequence(
                aggregate_type=aggregate_type,
                aggregate_id=aggregate_id,
                target_sequence=at_sequence,
                company_id=current_user.company_id,
                db=db,
            )
        else:
            state = await projection_service.project(
                aggregate_type=aggregate_type,
                aggregate_id=aggregate_id,
                company_id=current_user.company_id,
                db=db,
            )

        # Event-Anzahl ermitteln
        event_count = await event_store.get_event_count(
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            company_id=current_user.company_id,
            db=db,
        )

        # Letzte Sequenznummer
        events = await event_store.get_events(
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            company_id=current_user.company_id,
            after_sequence=0,
            db=db,
        )
        last_sequence = events[-1].sequence_number if events else 0

        return ProjectionResponse(
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            state=state,
            event_count=event_count,
            last_sequence=last_sequence,
        )

    except ValueError as e:
        logger.warning("projektion_fehler", **safe_error_log(e))
        raise HTTPException(status_code=400, detail=safe_error_detail(e, "Event-Sourcing"))
    except Exception as e:
        logger.error("projektion_fehler", **safe_error_log(e))
        raise HTTPException(status_code=500, detail="Fehler bei der Projektion")


@router.get(
    "/stats",
    response_model=EventStatsResponse,
    summary="Event-Statistiken",
    description="Holt Statistiken ueber Events und Snapshots."
)
async def get_event_stats(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> EventStatsResponse:
    """Holt Event-Statistiken."""
    try:
        from app.db.models import DomainEvent, EventSnapshot
        from sqlalchemy import select, func

        # Gesamt-Events
        total_stmt = select(func.count(DomainEvent.id)).where(
            DomainEvent.company_id == current_user.company_id
        )
        total_result = await db.execute(total_stmt)
        total_events = total_result.scalar() or 0

        # Events nach Typ
        type_stmt = select(
            DomainEvent.event_type,
            func.count(DomainEvent.id).label("count")
        ).where(
            DomainEvent.company_id == current_user.company_id
        ).group_by(
            DomainEvent.event_type
        )
        type_result = await db.execute(type_stmt)
        events_by_type = {row[0]: row[1] for row in type_result.all()}

        # Events nach Aggregat-Typ
        agg_stmt = select(
            DomainEvent.aggregate_type,
            func.count(DomainEvent.id).label("count")
        ).where(
            DomainEvent.company_id == current_user.company_id
        ).group_by(
            DomainEvent.aggregate_type
        )
        agg_result = await db.execute(agg_stmt)
        events_by_aggregate = {row[0]: row[1] for row in agg_result.all()}

        # Snapshot-Anzahl
        snap_stmt = select(func.count(EventSnapshot.id)).where(
            EventSnapshot.company_id == current_user.company_id
        )
        snap_result = await db.execute(snap_stmt)
        snapshots_count = snap_result.scalar() or 0

        return EventStatsResponse(
            total_events=total_events,
            events_by_type=events_by_type,
            events_by_aggregate=events_by_aggregate,
            snapshots_count=snapshots_count,
        )

    except Exception as e:
        logger.error("stats_abruf_fehler", **safe_error_log(e))
        raise HTTPException(status_code=500, detail="Fehler beim Abrufen der Statistiken")
