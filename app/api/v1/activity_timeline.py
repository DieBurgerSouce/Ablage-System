# -*- coding: utf-8 -*-
"""
Activity Timeline API fuer Ablage-System.

Multi-Level Activity Timeline:
- /activity/my - Eigene Aktivitaeten
- /activity/team/{team_id} - Team-Timeline
- /activity/document/{doc_id} - Dokument-Timeline
- /activity/chain/{chain_id} - Vorgang-Timeline
- /activity/company - Company-Timeline (Admin)
- /activity/stats - Statistiken

Phase 3.3 der Strategischen Roadmap (Januar 2026).
"""

from datetime import datetime
from typing import Optional, List, Dict

from app.core.types import JSONDict
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user, get_db
from app.db.models import User
from app.services.activity_timeline_service import (
    ActivityTimelineService,
    UnifiedActivity,
    ActivitySource,
    TimelineFilter,
)

router = APIRouter(prefix="/activity", tags=["Activity Timeline"])


# =============================================================================
# Pydantic Schemas
# =============================================================================


class ActivityResponse(BaseModel):
    """Response fuer eine einzelne Activity."""
    id: UUID
    source: ActivitySource
    activity_type: str
    title: str
    description: Optional[str] = None

    # Actor
    actor_id: Optional[UUID] = None
    actor_name: Optional[str] = None
    actor_avatar: Optional[str] = None

    # Target
    target_type: Optional[str] = None
    target_id: Optional[UUID] = None
    target_name: Optional[str] = None

    # Related
    related_type: Optional[str] = None
    related_id: Optional[UUID] = None
    related_name: Optional[str] = None

    # Context
    company_id: Optional[UUID] = None
    team_id: Optional[UUID] = None
    chain_id: Optional[UUID] = None

    # Metadata
    metadata: JSONDict = Field(default_factory=dict)

    # Timestamps
    created_at: datetime

    # Display
    icon: Optional[str] = None
    color: Optional[str] = None
    is_important: bool = False

    class Config:
        from_attributes = True


class TimelineResponse(BaseModel):
    """Response fuer Timeline-Abfragen."""
    items: List[ActivityResponse]
    total: int
    limit: int
    offset: int
    has_more: bool


class TimelineFilterRequest(BaseModel):
    """Request fuer Timeline-Filter."""
    sources: Optional[List[ActivitySource]] = None
    activity_types: Optional[List[str]] = None
    actor_ids: Optional[List[UUID]] = None
    target_types: Optional[List[str]] = None
    date_from: Optional[datetime] = None
    date_until: Optional[datetime] = None
    search_query: Optional[str] = Field(default=None, max_length=200)
    important_only: bool = False


class StatisticsResponse(BaseModel):
    """Response fuer Activity-Statistiken."""
    total_activities: int
    activities_by_type: Dict[str, int]
    activities_by_day: List[JSONDict]
    top_users: List[JSONDict]
    date_range: Dict[str, str]


# =============================================================================
# Helper Functions
# =============================================================================


def _activity_to_response(activity: UnifiedActivity) -> ActivityResponse:
    """Konvertiert UnifiedActivity zu Response."""
    return ActivityResponse(
        id=activity.id,
        source=activity.source,
        activity_type=activity.activity_type,
        title=activity.title,
        description=activity.description,
        actor_id=activity.actor_id,
        actor_name=activity.actor_name,
        actor_avatar=activity.actor_avatar,
        target_type=activity.target_type,
        target_id=activity.target_id,
        target_name=activity.target_name,
        related_type=activity.related_type,
        related_id=activity.related_id,
        related_name=activity.related_name,
        company_id=activity.company_id if activity.company_id and activity.company_id != UUID(int=0) else None,
        team_id=activity.team_id,
        chain_id=activity.chain_id,
        metadata=activity.metadata,
        created_at=activity.created_at,
        icon=activity.icon,
        color=activity.color,
        is_important=activity.is_important,
    )


def _filter_request_to_model(
    request: Optional[TimelineFilterRequest]
) -> Optional[TimelineFilter]:
    """Konvertiert Request zu interner Filter-Klasse."""
    if not request:
        return None
    return TimelineFilter(
        sources=request.sources,
        activity_types=request.activity_types,
        actor_ids=request.actor_ids,
        target_types=request.target_types,
        date_from=request.date_from,
        date_until=request.date_until,
        search_query=request.search_query,
        important_only=request.important_only,
    )


# =============================================================================
# My Activities Endpoint
# =============================================================================


@router.get("/my", response_model=TimelineResponse)
async def get_my_activities(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    source: Optional[ActivitySource] = Query(None, description="Quelle filtern"),
    activity_type: Optional[str] = Query(None, description="Typ filtern"),
    date_from: Optional[datetime] = Query(None, description="Von Datum"),
    date_until: Optional[datetime] = Query(None, description="Bis Datum"),
    search: Optional[str] = Query(None, max_length=200, description="Suche"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TimelineResponse:
    """Holt eigene Aktivitaeten.

    Zeigt:
    - Aktivitaeten die der User selbst durchgefuehrt hat
    - Aktivitaeten an eigenen Dokumenten
    - Team-Aktivitaeten in Teams wo User Mitglied ist
    """
    service = ActivityTimelineService(db)

    # Filter aufbauen
    filters = TimelineFilter(
        sources=[source] if source else None,
        activity_types=[activity_type] if activity_type else None,
        date_from=date_from,
        date_until=date_until,
        search_query=search,
    )

    activities = await service.get_my_activities(
        user_id=current_user.id,
        company_id=current_user.company_id,
        filters=filters,
        limit=limit + 1,  # +1 fuer has_more Check
        offset=offset,
    )

    has_more = len(activities) > limit
    if has_more:
        activities = activities[:limit]

    return TimelineResponse(
        items=[_activity_to_response(a) for a in activities],
        total=len(activities),  # Vereinfacht, koennte echte Zaehlung sein
        limit=limit,
        offset=offset,
        has_more=has_more,
    )


# =============================================================================
# Team Timeline Endpoint
# =============================================================================


@router.get("/team/{team_id}", response_model=TimelineResponse)
async def get_team_timeline(
    team_id: UUID,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    activity_type: Optional[str] = Query(None, description="Typ filtern"),
    date_from: Optional[datetime] = Query(None, description="Von Datum"),
    date_until: Optional[datetime] = Query(None, description="Bis Datum"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TimelineResponse:
    """Holt Timeline fuer ein Team.

    Zeigt:
    - Team-Aktivitaeten (Mitgliedschaften, Einstellungen)
    - Aktivitaeten aller Team-Mitglieder

    Erfordert Team-Mitgliedschaft.
    """
    service = ActivityTimelineService(db)

    filters = TimelineFilter(
        activity_types=[activity_type] if activity_type else None,
        date_from=date_from,
        date_until=date_until,
    )

    activities = await service.get_team_timeline(
        team_id=team_id,
        user_id=current_user.id,
        company_id=current_user.company_id,
        filters=filters,
        limit=limit + 1,
        offset=offset,
    )

    if not activities and offset == 0:
        # Koennte bedeuten: Keine Berechtigung oder kein Team
        # Service gibt [] zurueck bei fehlender Mitgliedschaft
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Keine Berechtigung fuer dieses Team oder Team nicht gefunden",
        )

    has_more = len(activities) > limit
    if has_more:
        activities = activities[:limit]

    return TimelineResponse(
        items=[_activity_to_response(a) for a in activities],
        total=len(activities),
        limit=limit,
        offset=offset,
        has_more=has_more,
    )


# =============================================================================
# Document Timeline Endpoint
# =============================================================================


@router.get("/document/{document_id}", response_model=TimelineResponse)
async def get_document_timeline(
    document_id: UUID,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    activity_type: Optional[str] = Query(None, description="Typ filtern"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TimelineResponse:
    """Holt Timeline fuer ein einzelnes Dokument.

    Zeigt alle Aktivitaeten die das Dokument betreffen:
    - Views, Downloads
    - Bearbeitungen
    - OCR-Verarbeitung
    - Kommentare
    - Genehmigungen
    """
    service = ActivityTimelineService(db)

    filters = TimelineFilter(
        activity_types=[activity_type] if activity_type else None,
    )

    activities = await service.get_document_timeline(
        document_id=document_id,
        company_id=current_user.company_id,
        filters=filters,
        limit=limit + 1,
        offset=offset,
    )

    has_more = len(activities) > limit
    if has_more:
        activities = activities[:limit]

    return TimelineResponse(
        items=[_activity_to_response(a) for a in activities],
        total=len(activities),
        limit=limit,
        offset=offset,
        has_more=has_more,
    )


# =============================================================================
# Chain Timeline Endpoint
# =============================================================================


@router.get("/chain/{chain_id}", response_model=TimelineResponse)
async def get_chain_timeline(
    chain_id: UUID,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TimelineResponse:
    """Holt Timeline fuer eine Document Chain (Vorgang).

    Aggregiert Aktivitaeten aller Dokumente in der Chain:
    - Angebot erstellt
    - Auftrag verknuepft
    - Lieferschein hinzugefuegt
    - Rechnung empfangen
    """
    service = ActivityTimelineService(db)

    activities = await service.get_chain_timeline(
        chain_id=chain_id,
        company_id=current_user.company_id,
        limit=limit + 1,
        offset=offset,
    )

    has_more = len(activities) > limit
    if has_more:
        activities = activities[:limit]

    return TimelineResponse(
        items=[_activity_to_response(a) for a in activities],
        total=len(activities),
        limit=limit,
        offset=offset,
        has_more=has_more,
    )


# =============================================================================
# Company Timeline Endpoint (Admin)
# =============================================================================


@router.get("/company", response_model=TimelineResponse)
async def get_company_timeline(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    source: Optional[ActivitySource] = Query(None, description="Quelle filtern"),
    activity_type: Optional[str] = Query(None, description="Typ filtern"),
    actor_id: Optional[UUID] = Query(None, description="User filtern"),
    date_from: Optional[datetime] = Query(None, description="Von Datum"),
    date_until: Optional[datetime] = Query(None, description="Bis Datum"),
    search: Optional[str] = Query(None, max_length=200, description="Suche"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TimelineResponse:
    """Holt Company-weite Timeline.

    Nur fuer Admins: Zeigt alle Aktivitaeten der Company.
    Nicht-Admins erhalten eingeschraenkte Sicht (nur eigene Aktivitaeten).
    """
    service = ActivityTimelineService(db)

    is_admin = current_user.role == "admin"

    filters = TimelineFilter(
        sources=[source] if source else None,
        activity_types=[activity_type] if activity_type else None,
        actor_ids=[actor_id] if actor_id else None,
        date_from=date_from,
        date_until=date_until,
        search_query=search,
    )

    activities = await service.get_company_timeline(
        company_id=current_user.company_id,
        user_id=current_user.id,
        is_admin=is_admin,
        filters=filters,
        limit=limit + 1,
        offset=offset,
    )

    has_more = len(activities) > limit
    if has_more:
        activities = activities[:limit]

    return TimelineResponse(
        items=[_activity_to_response(a) for a in activities],
        total=len(activities),
        limit=limit,
        offset=offset,
        has_more=has_more,
    )


# =============================================================================
# Statistics Endpoint
# =============================================================================


@router.get("/stats", response_model=StatisticsResponse)
async def get_activity_statistics(
    user_id: Optional[UUID] = Query(None, description="User-Filter (nur Admin)"),
    team_id: Optional[UUID] = Query(None, description="Team-Filter"),
    date_from: Optional[datetime] = Query(None, description="Von Datum"),
    date_until: Optional[datetime] = Query(None, description="Bis Datum"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StatisticsResponse:
    """Holt Activity-Statistiken.

    Zeigt:
    - Gesamtanzahl Aktivitaeten
    - Aktivitaeten nach Typ
    - Aktivitaeten nach Tag
    - Top aktive User (nur Admin)
    """
    service = ActivityTimelineService(db)

    # Nicht-Admins duerfen nur eigene Stats sehen
    if current_user.role != "admin":
        user_id = current_user.id

    stats = await service.get_activity_statistics(
        company_id=current_user.company_id,
        user_id=user_id,
        team_id=team_id,
        date_from=date_from,
        date_until=date_until,
    )

    return StatisticsResponse(
        total_activities=stats["total_activities"],
        activities_by_type=stats["activities_by_type"],
        activities_by_day=stats["activities_by_day"],
        top_users=stats["top_users"] if current_user.role == "admin" else [],
        date_range=stats["date_range"],
    )


# =============================================================================
# Filtered Timeline Endpoint (POST for complex filters)
# =============================================================================


@router.post("/filter", response_model=TimelineResponse)
async def filter_timeline(
    filter_request: TimelineFilterRequest,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TimelineResponse:
    """Holt gefilterte Timeline mit komplexen Filtern.

    Erlaubt mehrere Filter gleichzeitig via POST Body.
    """
    service = ActivityTimelineService(db)

    filters = _filter_request_to_model(filter_request)

    # Verwende my_activities als Basis (respektiert Berechtigungen)
    activities = await service.get_my_activities(
        user_id=current_user.id,
        company_id=current_user.company_id,
        filters=filters,
        limit=limit + 1,
        offset=offset,
    )

    has_more = len(activities) > limit
    if has_more:
        activities = activities[:limit]

    return TimelineResponse(
        items=[_activity_to_response(a) for a in activities],
        total=len(activities),
        limit=limit,
        offset=offset,
        has_more=has_more,
    )
