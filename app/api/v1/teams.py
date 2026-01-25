# -*- coding: utf-8 -*-
"""
Teams API Endpoints.

REST API fuer Team-Verwaltung:
- Team CRUD
- Mitgliedschaften verwalten
- Team-Aktivitaeten
- Einladungen

Phase 3.1 der Strategischen Roadmap (Januar 2026).
"""

from typing import Optional, List
from uuid import UUID
from datetime import datetime
from enum import Enum

import structlog
from fastapi import APIRouter, Depends, HTTPException, status, Query, Body
from pydantic import BaseModel, Field, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import User
from app.db.models_team import (
    Team,
    TeamType,
    TeamStatus,
    TeamVisibility,
    TeamMembership,
    TeamMemberRole,
    TeamActivity,
    TeamActivityType,
    TeamInvitation,
    InvitationStatus,
    TeamDocument,
    TeamDocumentPermission,
)
from app.api.dependencies import get_db, get_current_active_user
from app.services.team_service import TeamService, get_team_service


logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/teams", tags=["Teams"])


# =============================================================================
# Pydantic Schemas
# =============================================================================


class TeamCreate(BaseModel):
    """Schema fuer Team-Erstellung."""
    name: str = Field(..., min_length=1, max_length=255, description="Team-Name")
    team_type: TeamType = Field(TeamType.DEPARTMENT, description="Team-Typ")
    description: Optional[str] = Field(None, max_length=2000, description="Beschreibung")
    code: Optional[str] = Field(None, max_length=50, description="Kurzcode")
    parent_team_id: Optional[UUID] = Field(None, description="Parent-Team fuer Hierarchie")
    visibility: TeamVisibility = Field(TeamVisibility.COMPANY, description="Sichtbarkeit")
    start_date: Optional[datetime] = Field(None, description="Startdatum (Projektteams)")
    end_date: Optional[datetime] = Field(None, description="Enddatum (Projektteams)")
    settings: Optional[dict] = Field(None, description="Team-Einstellungen")
    default_permissions: Optional[List[str]] = Field(None, description="Standard-Berechtigungen")
    tags: Optional[List[str]] = Field(None, description="Tags")


class TeamUpdate(BaseModel):
    """Schema fuer Team-Aktualisierung."""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = Field(None, max_length=2000)
    code: Optional[str] = Field(None, max_length=50)
    visibility: Optional[TeamVisibility] = None
    status: Optional[TeamStatus] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    settings: Optional[dict] = None
    default_permissions: Optional[List[str]] = None
    tags: Optional[List[str]] = None
    email: Optional[str] = Field(None, max_length=255)
    slack_channel: Optional[str] = Field(None, max_length=100)


class TeamMemberAdd(BaseModel):
    """Schema fuer Mitglied hinzufuegen."""
    user_id: UUID = Field(..., description="User UUID")
    role: TeamMemberRole = Field(TeamMemberRole.MEMBER, description="Rolle")
    title: Optional[str] = Field(None, max_length=100, description="Funktion im Team")
    allocation_percent: int = Field(100, ge=0, le=100, description="Prozentuale Zuordnung")
    valid_until: Optional[datetime] = Field(None, description="Gueltig bis")
    reason: Optional[str] = Field(None, max_length=500, description="Grund")


class TeamMemberUpdate(BaseModel):
    """Schema fuer Mitglied aktualisieren."""
    role: Optional[TeamMemberRole] = None
    title: Optional[str] = Field(None, max_length=100)
    allocation_percent: Optional[int] = Field(None, ge=0, le=100)
    valid_until: Optional[datetime] = None


class TeamInvitationCreate(BaseModel):
    """Schema fuer Einladung erstellen."""
    user_id: Optional[UUID] = Field(None, description="User UUID (wenn bekannt)")
    email: Optional[str] = Field(None, max_length=255, description="Email (fuer externe)")
    role: TeamMemberRole = Field(TeamMemberRole.MEMBER, description="Geplante Rolle")
    personal_message: Optional[str] = Field(None, max_length=1000, description="Nachricht")
    expires_in_days: int = Field(7, ge=1, le=30, description="Gueltigkeitsdauer in Tagen")


class TeamDocumentShare(BaseModel):
    """Schema fuer Dokument-Freigabe."""
    document_id: UUID = Field(..., description="Dokument UUID")
    permission: TeamDocumentPermission = Field(
        TeamDocumentPermission.READ, description="Berechtigung"
    )
    valid_until: Optional[datetime] = Field(None, description="Gueltig bis")
    note: Optional[str] = Field(None, max_length=500, description="Notiz")


# =============================================================================
# Response Schemas
# =============================================================================


class TeamMemberResponse(BaseModel):
    """Response fuer Team-Mitglied."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    user_name: Optional[str] = None
    user_email: Optional[str] = None
    role: TeamMemberRole
    is_active: bool
    is_primary: bool
    title: Optional[str] = None
    allocation_percent: int
    valid_from: datetime
    valid_until: Optional[datetime] = None
    joined_at: datetime


class TeamResponse(BaseModel):
    """Response fuer Team."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    code: Optional[str] = None
    description: Optional[str] = None
    team_type: TeamType
    status: TeamStatus
    visibility: TeamVisibility
    parent_team_id: Optional[UUID] = None
    level: int
    member_count: int
    active_member_count: int
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    tags: List[str] = []
    email: Optional[str] = None
    slack_channel: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class TeamDetailResponse(TeamResponse):
    """Detaillierte Team-Response mit Mitgliedern."""
    members: List[TeamMemberResponse] = []
    settings: dict = {}
    default_permissions: List[str] = []


class TeamListResponse(BaseModel):
    """Response fuer Team-Liste."""
    items: List[TeamResponse]
    total: int
    page: int
    per_page: int
    total_pages: int


class TeamActivityResponse(BaseModel):
    """Response fuer Team-Aktivitaet."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    activity_type: TeamActivityType
    actor_id: Optional[UUID] = None
    actor_name: Optional[str] = None
    target_user_id: Optional[UUID] = None
    target_document_id: Optional[UUID] = None
    title: str
    description: Optional[str] = None
    details: dict = {}
    created_at: datetime


class TeamActivityListResponse(BaseModel):
    """Response fuer Aktivitaeten-Liste."""
    items: List[TeamActivityResponse]
    total: int
    page: int
    per_page: int


class TeamInvitationResponse(BaseModel):
    """Response fuer Einladung."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    team_id: UUID
    user_id: Optional[UUID] = None
    email: Optional[str] = None
    role: TeamMemberRole
    status: InvitationStatus
    personal_message: Optional[str] = None
    expires_at: datetime
    created_at: datetime


class MessageResponse(BaseModel):
    """Einfache Nachricht-Response."""
    message: str


# =============================================================================
# Team CRUD Endpoints
# =============================================================================


@router.post(
    "",
    response_model=TeamResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Team erstellen",
    description="Erstellt ein neues Team. Der Ersteller wird automatisch Admin."
)
async def create_team(
    data: TeamCreate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> TeamResponse:
    """Erstellt ein neues Team."""
    service = get_team_service(db)

    try:
        team = await service.create_team(
            name=data.name,
            company_id=current_user.company_id,
            created_by_id=current_user.id,
            team_type=data.team_type,
            description=data.description,
            code=data.code,
            parent_team_id=data.parent_team_id,
            visibility=data.visibility,
            start_date=data.start_date,
            end_date=data.end_date,
            settings=data.settings,
            default_permissions=data.default_permissions,
            tags=data.tags,
        )

        logger.info(
            "team_created_via_api",
            team_id=str(team.id),
            name=team.name,
            user_id=str(current_user.id)[:8],
        )

        return TeamResponse.model_validate(team)

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get(
    "",
    response_model=TeamListResponse,
    summary="Teams auflisten",
    description="Listet alle Teams mit Filter- und Paginierungsoptionen"
)
async def list_teams(
    page: int = Query(1, ge=1, description="Seitennummer"),
    per_page: int = Query(20, ge=1, le=100, description="Eintraege pro Seite"),
    search: Optional[str] = Query(None, max_length=100, description="Suchbegriff"),
    team_type: Optional[TeamType] = Query(None, description="Nach Typ filtern"),
    status: Optional[TeamStatus] = Query(None, description="Nach Status filtern"),
    parent_team_id: Optional[UUID] = Query(None, description="Nach Parent filtern"),
    my_teams_only: bool = Query(False, description="Nur eigene Teams"),
    include_inactive: bool = Query(False, description="Inaktive einschliessen"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> TeamListResponse:
    """Listet Teams auf."""
    service = get_team_service(db)

    teams, total = await service.list_teams(
        company_id=current_user.company_id,
        team_type=team_type,
        status=status,
        parent_team_id=parent_team_id,
        user_id=current_user.id if my_teams_only else None,
        search=search,
        include_inactive=include_inactive,
        page=page,
        per_page=per_page,
    )

    return TeamListResponse(
        items=[TeamResponse.model_validate(t) for t in teams],
        total=total,
        page=page,
        per_page=per_page,
        total_pages=(total + per_page - 1) // per_page,
    )


@router.get(
    "/my",
    response_model=List[TeamResponse],
    summary="Meine Teams",
    description="Listet alle Teams in denen der aktuelle User Mitglied ist"
)
async def get_my_teams(
    include_inactive: bool = Query(False, description="Inaktive einschliessen"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> List[TeamResponse]:
    """Holt Teams des aktuellen Users."""
    service = get_team_service(db)

    teams = await service.get_user_teams(
        user_id=current_user.id,
        company_id=current_user.company_id,
        include_inactive=include_inactive,
    )

    return [TeamResponse.model_validate(t) for t in teams]


@router.get(
    "/{team_id}",
    response_model=TeamDetailResponse,
    summary="Team abrufen",
    description="Holt ein Team mit allen Details und Mitgliedern"
)
async def get_team(
    team_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> TeamDetailResponse:
    """Holt ein Team nach ID."""
    service = get_team_service(db)

    team = await service.get_team(team_id, include_members=True)
    if not team:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Team nicht gefunden"
        )

    # Zugangspruefung
    if team.company_id != current_user.company_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Kein Zugriff auf dieses Team"
        )

    # Bei privaten Teams: Mitgliedschaft pruefen
    if team.visibility == TeamVisibility.PRIVATE:
        is_member = await service.check_permission(team_id, current_user.id)
        if not is_member:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Kein Zugriff auf dieses private Team"
            )

    # Response bauen
    response = TeamDetailResponse(
        id=team.id,
        name=team.name,
        code=team.code,
        description=team.description,
        team_type=team.team_type,
        status=team.status,
        visibility=team.visibility,
        parent_team_id=team.parent_team_id,
        level=team.level,
        member_count=team.member_count,
        active_member_count=team.active_member_count,
        start_date=team.start_date,
        end_date=team.end_date,
        tags=team.tags or [],
        email=team.email,
        slack_channel=team.slack_channel,
        created_at=team.created_at,
        updated_at=team.updated_at,
        settings=team.settings or {},
        default_permissions=team.default_permissions or [],
        members=[
            TeamMemberResponse(
                id=m.id,
                user_id=m.user_id,
                user_name=m.user.name if m.user else None,
                user_email=m.user.email if m.user else None,
                role=m.role,
                is_active=m.is_active,
                is_primary=m.is_primary,
                title=m.title,
                allocation_percent=m.allocation_percent,
                valid_from=m.valid_from,
                valid_until=m.valid_until,
                joined_at=m.joined_at,
            )
            for m in team.memberships if m.is_active
        ],
    )

    return response


@router.patch(
    "/{team_id}",
    response_model=TeamResponse,
    summary="Team aktualisieren",
    description="Aktualisiert ein Team (nur fuer Team-Admins)"
)
async def update_team(
    team_id: UUID,
    data: TeamUpdate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> TeamResponse:
    """Aktualisiert ein Team."""
    service = get_team_service(db)

    # Admin-Berechtigung pruefen
    is_admin = await service.is_team_admin(team_id, current_user.id)
    if not is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Nur Team-Admins koennen das Team aktualisieren"
        )

    updates = data.model_dump(exclude_unset=True)
    team = await service.update_team(team_id, current_user.id, **updates)

    if not team:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Team nicht gefunden"
        )

    return TeamResponse.model_validate(team)


@router.delete(
    "/{team_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Team archivieren",
    description="Archiviert ein Team (nur fuer Team-Admins)"
)
async def archive_team(
    team_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Archiviert ein Team."""
    service = get_team_service(db)

    # Admin-Berechtigung pruefen
    is_admin = await service.is_team_admin(team_id, current_user.id)
    if not is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Nur Team-Admins koennen das Team archivieren"
        )

    team = await service.archive_team(team_id, current_user.id)
    if not team:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Team nicht gefunden"
        )


# =============================================================================
# Member Endpoints
# =============================================================================


@router.get(
    "/{team_id}/members",
    response_model=List[TeamMemberResponse],
    summary="Team-Mitglieder auflisten",
    description="Listet alle Mitglieder eines Teams"
)
async def list_members(
    team_id: UUID,
    role: Optional[TeamMemberRole] = Query(None, description="Nach Rolle filtern"),
    include_inactive: bool = Query(False, description="Inaktive einschliessen"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> List[TeamMemberResponse]:
    """Listet Team-Mitglieder."""
    service = get_team_service(db)

    # Zugriffspruefung
    team = await service.get_team(team_id)
    if not team or team.company_id != current_user.company_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Team nicht gefunden"
        )

    memberships, _ = await service.list_members(
        team_id=team_id,
        role=role,
        include_inactive=include_inactive,
    )

    return [
        TeamMemberResponse(
            id=m.id,
            user_id=m.user_id,
            user_name=m.user.name if m.user else None,
            user_email=m.user.email if m.user else None,
            role=m.role,
            is_active=m.is_active,
            is_primary=m.is_primary,
            title=m.title,
            allocation_percent=m.allocation_percent,
            valid_from=m.valid_from,
            valid_until=m.valid_until,
            joined_at=m.joined_at,
        )
        for m in memberships
    ]


@router.post(
    "/{team_id}/members",
    response_model=TeamMemberResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Mitglied hinzufuegen",
    description="Fuegt ein Mitglied zum Team hinzu (nur fuer Team-Admins)"
)
async def add_member(
    team_id: UUID,
    data: TeamMemberAdd,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> TeamMemberResponse:
    """Fuegt ein Mitglied hinzu."""
    service = get_team_service(db)

    # Admin-Berechtigung pruefen
    is_admin = await service.is_team_admin(team_id, current_user.id)
    if not is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Nur Team-Admins koennen Mitglieder hinzufuegen"
        )

    try:
        membership = await service.add_member(
            team_id=team_id,
            user_id=data.user_id,
            role=data.role,
            invited_by_id=current_user.id,
            title=data.title,
            allocation_percent=data.allocation_percent,
            valid_until=data.valid_until,
            reason=data.reason,
        )

        # User-Daten nachladen
        from sqlalchemy import select
        from app.db.models import User as UserModel
        user_result = await db.execute(
            select(UserModel).where(UserModel.id == data.user_id)
        )
        user = user_result.scalar_one_or_none()

        return TeamMemberResponse(
            id=membership.id,
            user_id=membership.user_id,
            user_name=user.name if user else None,
            user_email=user.email if user else None,
            role=membership.role,
            is_active=membership.is_active,
            is_primary=membership.is_primary,
            title=membership.title,
            allocation_percent=membership.allocation_percent,
            valid_from=membership.valid_from,
            valid_until=membership.valid_until,
            joined_at=membership.joined_at,
        )

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.patch(
    "/{team_id}/members/{user_id}",
    response_model=TeamMemberResponse,
    summary="Mitglied aktualisieren",
    description="Aktualisiert Rolle oder Details eines Mitglieds"
)
async def update_member(
    team_id: UUID,
    user_id: UUID,
    data: TeamMemberUpdate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> TeamMemberResponse:
    """Aktualisiert ein Mitglied."""
    service = get_team_service(db)

    # Admin-Berechtigung pruefen
    is_admin = await service.is_team_admin(team_id, current_user.id)
    if not is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Nur Team-Admins koennen Mitglieder aktualisieren"
        )

    membership = await service.get_membership(team_id, user_id)
    if not membership:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Mitgliedschaft nicht gefunden"
        )

    # Rolle aktualisieren
    if data.role is not None:
        membership = await service.update_member_role(
            team_id, user_id, data.role, current_user.id
        )

    return TeamMemberResponse(
        id=membership.id,
        user_id=membership.user_id,
        user_name=membership.user.name if membership.user else None,
        user_email=membership.user.email if membership.user else None,
        role=membership.role,
        is_active=membership.is_active,
        is_primary=membership.is_primary,
        title=membership.title,
        allocation_percent=membership.allocation_percent,
        valid_from=membership.valid_from,
        valid_until=membership.valid_until,
        joined_at=membership.joined_at,
    )


@router.delete(
    "/{team_id}/members/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Mitglied entfernen",
    description="Entfernt ein Mitglied aus dem Team"
)
async def remove_member(
    team_id: UUID,
    user_id: UUID,
    reason: Optional[str] = Query(None, max_length=500, description="Grund"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Entfernt ein Mitglied."""
    service = get_team_service(db)

    # Admin-Berechtigung pruefen (oder selbst austreten)
    is_admin = await service.is_team_admin(team_id, current_user.id)
    is_self = user_id == current_user.id

    if not is_admin and not is_self:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Nur Team-Admins koennen Mitglieder entfernen"
        )

    success = await service.remove_member(
        team_id=team_id,
        user_id=user_id,
        actor_id=current_user.id,
        reason=reason,
    )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Mitgliedschaft nicht gefunden"
        )


# =============================================================================
# Activity Endpoints
# =============================================================================


@router.get(
    "/{team_id}/activity",
    response_model=TeamActivityListResponse,
    summary="Team-Aktivitaeten",
    description="Holt den Activity Feed eines Teams"
)
async def get_team_activity(
    team_id: UUID,
    page: int = Query(1, ge=1, description="Seite"),
    per_page: int = Query(50, ge=1, le=100, description="Pro Seite"),
    activity_type: Optional[TeamActivityType] = Query(None, description="Nach Typ filtern"),
    since: Optional[datetime] = Query(None, description="Seit Zeitpunkt"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> TeamActivityListResponse:
    """Holt Team-Aktivitaeten."""
    service = get_team_service(db)

    # Zugriffspruefung
    is_member = await service.check_permission(team_id, current_user.id)
    if not is_member:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Kein Zugriff auf Team-Aktivitaeten"
        )

    activity_types = [activity_type] if activity_type else None

    activities, total = await service.get_team_activity(
        team_id=team_id,
        activity_types=activity_types,
        since=since,
        page=page,
        per_page=per_page,
    )

    return TeamActivityListResponse(
        items=[
            TeamActivityResponse(
                id=a.id,
                activity_type=a.activity_type,
                actor_id=a.actor_id,
                actor_name=a.actor.name if a.actor else None,
                target_user_id=a.target_user_id,
                target_document_id=a.target_document_id,
                title=a.title,
                description=a.description,
                details=a.details or {},
                created_at=a.created_at,
            )
            for a in activities
        ],
        total=total,
        page=page,
        per_page=per_page,
    )


# =============================================================================
# Invitation Endpoints
# =============================================================================


@router.post(
    "/{team_id}/invitations",
    response_model=TeamInvitationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Einladung erstellen",
    description="Erstellt eine Team-Einladung (nur fuer Team-Admins)"
)
async def create_invitation(
    team_id: UUID,
    data: TeamInvitationCreate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> TeamInvitationResponse:
    """Erstellt eine Einladung."""
    service = get_team_service(db)

    # Admin-Berechtigung pruefen
    is_admin = await service.is_team_admin(team_id, current_user.id)
    if not is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Nur Team-Admins koennen Einladungen erstellen"
        )

    try:
        invitation = await service.create_invitation(
            team_id=team_id,
            invited_by_id=current_user.id,
            user_id=data.user_id,
            email=data.email,
            role=data.role,
            personal_message=data.personal_message,
            expires_in_days=data.expires_in_days,
        )

        return TeamInvitationResponse.model_validate(invitation)

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post(
    "/invitations/{invitation_id}/accept",
    response_model=TeamMemberResponse,
    summary="Einladung annehmen",
    description="Nimmt eine Team-Einladung an"
)
async def accept_invitation(
    invitation_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> TeamMemberResponse:
    """Nimmt eine Einladung an."""
    service = get_team_service(db)

    try:
        membership = await service.accept_invitation(
            invitation_id=invitation_id,
            user_id=current_user.id,
        )

        return TeamMemberResponse(
            id=membership.id,
            user_id=membership.user_id,
            user_name=current_user.name,
            user_email=current_user.email,
            role=membership.role,
            is_active=membership.is_active,
            is_primary=membership.is_primary,
            title=membership.title,
            allocation_percent=membership.allocation_percent,
            valid_from=membership.valid_from,
            valid_until=membership.valid_until,
            joined_at=membership.joined_at,
        )

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post(
    "/invitations/{invitation_id}/decline",
    response_model=MessageResponse,
    summary="Einladung ablehnen",
    description="Lehnt eine Team-Einladung ab"
)
async def decline_invitation(
    invitation_id: UUID,
    reason: Optional[str] = Body(None, embed=True, max_length=500),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    """Lehnt eine Einladung ab."""
    service = get_team_service(db)

    try:
        success = await service.decline_invitation(
            invitation_id=invitation_id,
            user_id=current_user.id,
            reason=reason,
        )

        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Einladung nicht gefunden"
            )

        return MessageResponse(message="Einladung abgelehnt")

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


# =============================================================================
# Document Sharing Endpoints
# =============================================================================


@router.post(
    "/{team_id}/documents",
    response_model=MessageResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Dokument mit Team teilen",
    description="Teilt ein Dokument mit dem Team"
)
async def share_document_with_team(
    team_id: UUID,
    data: TeamDocumentShare,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    """Teilt ein Dokument mit dem Team."""
    service = get_team_service(db)

    # Mitgliedschaftspruefung
    is_member = await service.check_permission(team_id, current_user.id)
    if not is_member:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Nur Team-Mitglieder koennen Dokumente teilen"
        )

    await service.share_document(
        team_id=team_id,
        document_id=data.document_id,
        shared_by_id=current_user.id,
        permission=data.permission,
        valid_until=data.valid_until,
        note=data.note,
    )

    return MessageResponse(message="Dokument mit Team geteilt")
