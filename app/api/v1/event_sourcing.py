"""Event-Sourcing API - Event Store und Projektionen."""

import structlog
from typing import List, Optional, Dict

from app.core.types import JSONDict
from uuid import UUID
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db, get_current_user, get_user_company_id_dep
from app.core.safe_errors import safe_error_detail, safe_error_log
from app.db.models import User
from app.services.event_sourcing import EventStore, ProjectionService, SnapshotService
from app.core.rate_limiting import limiter, get_user_identifier

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/event-sourcing", tags=["event-sourcing"])


# =============================================================================
# K6 (CRITICAL): Whitelist fuer aggregate_type-Pfadparameter
# =============================================================================
# Ohne Whitelist wird ein beliebiger String an den EventStore weitergereicht.
# Das ermoeglicht Injection-Vektoren (SQL/Redis-Keys downstream) und
# IDOR-Enumeration ueber alle Aggregate-Typen hinweg. Wir validieren vor dem
# Service-Call gegen die zentrale Whitelist, die mit
# app/services/event_sourcing/snapshot_service.py:66 abgestimmt ist.
ALLOWED_AGGREGATE_TYPES = frozenset({
    "document",
    "invoice",
    "payment",
    "entity",
    "alert",
    "workflow",
})


def _validate_aggregate_type(aggregate_type: str) -> None:
    """Werfe 400 wenn aggregate_type nicht in Whitelist ist.

    Wird VOR jedem Service-Call aufgerufen, sodass kein Reach-Through
    zum EventStore moeglich ist.
    """
    if aggregate_type not in ALLOWED_AGGREGATE_TYPES:
        logger.warning(
            "event_sourcing_invalid_aggregate_type",
            aggregate_type=aggregate_type,
            allowed=sorted(ALLOWED_AGGREGATE_TYPES),
        )
        raise HTTPException(
            status_code=400,
            detail=(
                f"Ungueltiger aggregate_type. Erlaubt: "
                f"{', '.join(sorted(ALLOWED_AGGREGATE_TYPES))}"
            ),
        )


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
    event_data: JSONDict
    metadata: JSONDict
    correlation_id: Optional[UUID]
    causation_id: Optional[UUID]
    user_id: Optional[UUID]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SnapshotResponse(BaseModel):
    """Snapshot-Response Model."""

    snapshot_id: UUID
    aggregate_type: str
    aggregate_id: UUID
    sequence_number: int
    state: JSONDict
    version: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ProjectionResponse(BaseModel):
    """Projection-Response Model."""

    aggregate_type: str
    aggregate_id: UUID
    state: JSONDict
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
    description="Holt alle Events für ein Aggregat in zeitlicher Reihenfolge."
)
@limiter.limit("60/minute", key_func=get_user_identifier)
async def get_events(
    request: Request,
    aggregate_type: str,
    aggregate_id: UUID,
    after_sequence: int = Query(0, description="Nur Events nach dieser Sequenznummer"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    company_id: UUID = Depends(get_user_company_id_dep),
) -> List[EventResponse]:
    """Holt Events für ein Aggregat."""
    _validate_aggregate_type(aggregate_type)
    try:
        event_store = EventStore()

        events = await event_store.get_events(
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            company_id=company_id,
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
    description="Holt den neuesten Snapshot für ein Aggregat."
)
@limiter.limit("60/minute", key_func=get_user_identifier)
async def get_snapshot(
    request: Request,
    aggregate_type: str,
    aggregate_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    company_id: UUID = Depends(get_user_company_id_dep),
) -> Optional[SnapshotResponse]:
    """Holt den neuesten Snapshot."""
    _validate_aggregate_type(aggregate_type)
    try:
        snapshot_service = SnapshotService()

        snapshot = await snapshot_service.get_latest_snapshot(
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            company_id=company_id,
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
@limiter.limit("60/minute", key_func=get_user_identifier)
async def get_projection(
    request: Request,
    aggregate_type: str,
    aggregate_id: UUID,
    at_sequence: Optional[int] = Query(None, description="Zustand bei Sequenznummer (Zeitreise)"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    company_id: UUID = Depends(get_user_company_id_dep),
) -> ProjectionResponse:
    """Projiziert den aktuellen Zustand."""
    _validate_aggregate_type(aggregate_type)
    try:
        projection_service = ProjectionService()
        event_store = EventStore()

        # Projektion durchführen
        if at_sequence is not None:
            state = await projection_service.project_at_sequence(
                aggregate_type=aggregate_type,
                aggregate_id=aggregate_id,
                target_sequence=at_sequence,
                company_id=company_id,
                db=db,
            )
        else:
            state = await projection_service.project(
                aggregate_type=aggregate_type,
                aggregate_id=aggregate_id,
                company_id=company_id,
                db=db,
            )

        # Event-Anzahl ermitteln
        event_count = await event_store.get_event_count(
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            company_id=company_id,
            db=db,
        )

        # Letzte Sequenznummer
        events = await event_store.get_events(
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            company_id=company_id,
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
    description="Holt Statistiken über Events und Snapshots."
)
@limiter.limit("60/minute", key_func=get_user_identifier)
async def get_event_stats(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    company_id: UUID = Depends(get_user_company_id_dep),
) -> EventStatsResponse:
    """Holt Event-Statistiken."""
    try:
        from app.db.models import DomainEvent, EventSnapshot
        from sqlalchemy import select, func

        # Gesamt-Events
        total_stmt = select(func.count(DomainEvent.id)).where(
            DomainEvent.company_id == company_id
        )
        total_result = await db.execute(total_stmt)
        total_events = total_result.scalar() or 0

        # Events nach Typ
        type_stmt = select(
            DomainEvent.event_type,
            func.count(DomainEvent.id).label("count")
        ).where(
            DomainEvent.company_id == company_id
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
            DomainEvent.company_id == company_id
        ).group_by(
            DomainEvent.aggregate_type
        )
        agg_result = await db.execute(agg_stmt)
        events_by_aggregate = {row[0]: row[1] for row in agg_result.all()}

        # Snapshot-Anzahl
        snap_stmt = select(func.count(EventSnapshot.id)).where(
            EventSnapshot.company_id == company_id
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
