# -*- coding: utf-8 -*-
"""
Team Service fuer Ablage-System.

Business Logic fuer:
- Team-Verwaltung (CRUD)
- Mitgliedschaften verwalten
- Team-Hierarchien
- Aktivitaets-Tracking
- Einladungen

Phase 3.1 der Strategischen Roadmap (Januar 2026).
"""

import secrets
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from uuid import UUID

import structlog
from sqlalchemy import select, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.datetime_utils import utc_now
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


logger = structlog.get_logger(__name__)


class TeamService:
    """Service fuer Team-Verwaltung."""

    def __init__(self, db: AsyncSession):
        """Initialisiert den Service."""
        self.db = db

    # =========================================================================
    # Team CRUD
    # =========================================================================

    async def create_team(
        self,
        name: str,
        company_id: UUID,
        created_by_id: UUID,
        team_type: TeamType = TeamType.DEPARTMENT,
        description: Optional[str] = None,
        code: Optional[str] = None,
        parent_team_id: Optional[UUID] = None,
        visibility: TeamVisibility = TeamVisibility.COMPANY,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        settings: Optional[Dict[str, Any]] = None,
        default_permissions: Optional[List[str]] = None,
        tags: Optional[List[str]] = None,
    ) -> Team:
        """
        Erstellt ein neues Team.

        Args:
            name: Team-Name
            company_id: Company UUID (Multi-Tenant)
            created_by_id: User der das Team erstellt
            team_type: Art des Teams (department, project, etc.)
            description: Beschreibung
            code: Kurzcode (z.B. "DEV")
            parent_team_id: Parent-Team fuer Hierarchie
            visibility: Sichtbarkeit
            start_date: Startdatum (fuer Projektteams)
            end_date: Enddatum (fuer Projektteams)
            settings: Team-Einstellungen
            default_permissions: Standard-Berechtigungen
            tags: Tags

        Returns:
            Erstelltes Team
        """
        # Hierarchie-Level und Path berechnen
        level = 0
        path = ""

        if parent_team_id:
            parent = await self.get_team(parent_team_id)
            if parent:
                level = parent.level + 1
                path = f"{parent.path}/{str(parent.id)}" if parent.path else str(parent.id)

        team = Team(
            name=name,
            company_id=company_id,
            created_by_id=created_by_id,
            team_type=team_type,
            description=description,
            code=code,
            parent_team_id=parent_team_id,
            visibility=visibility,
            start_date=start_date,
            end_date=end_date,
            settings=settings or {},
            default_permissions=default_permissions or [],
            tags=tags or [],
            level=level,
            path=path,
            status=TeamStatus.ACTIVE,
            member_count=1,  # Creator wird Mitglied
            active_member_count=1,
        )

        self.db.add(team)
        await self.db.flush()

        # Creator als Admin hinzufuegen
        membership = TeamMembership(
            team_id=team.id,
            user_id=created_by_id,
            role=TeamMemberRole.ADMIN,
            is_primary=True,
            title="Team-Ersteller",
            allocation_percent=100,
        )
        self.db.add(membership)

        # Activity loggen
        await self._log_activity(
            team_id=team.id,
            activity_type=TeamActivityType.TEAM_CREATED,
            actor_id=created_by_id,
            title=f"Team '{name}' erstellt",
            details={"team_type": team_type.value},
        )

        await self.db.commit()
        await self.db.refresh(team)

        logger.info(
            "team_created",
            team_id=str(team.id),
            name=name,
            team_type=team_type.value,
            created_by=str(created_by_id)[:8],
        )

        return team

    async def get_team(
        self,
        team_id: UUID,
        include_members: bool = False,
    ) -> Optional[Team]:
        """
        Holt ein Team nach ID.

        Args:
            team_id: Team UUID
            include_members: Mitglieder mitladen

        Returns:
            Team oder None
        """
        query = select(Team).where(Team.id == team_id)

        if include_members:
            query = query.options(
                selectinload(Team.memberships).selectinload(TeamMembership.user)
            )

        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def list_teams(
        self,
        company_id: UUID,
        team_type: Optional[TeamType] = None,
        status: Optional[TeamStatus] = None,
        parent_team_id: Optional[UUID] = None,
        user_id: Optional[UUID] = None,
        search: Optional[str] = None,
        include_inactive: bool = False,
        page: int = 1,
        per_page: int = 20,
    ) -> tuple[List[Team], int]:
        """
        Listet Teams mit Filtern.

        Args:
            company_id: Company UUID
            team_type: Nach Typ filtern
            status: Nach Status filtern
            parent_team_id: Nach Parent filtern
            user_id: Nur Teams in denen User Mitglied ist
            search: Suchbegriff
            include_inactive: Inaktive Teams einschliessen
            page: Seite
            per_page: Eintraege pro Seite

        Returns:
            Tuple aus (Teams, Total)
        """
        query = select(Team).where(Team.company_id == company_id)

        if not include_inactive:
            query = query.where(Team.status == TeamStatus.ACTIVE)
        elif status:
            query = query.where(Team.status == status)

        if team_type:
            query = query.where(Team.team_type == team_type)

        if parent_team_id:
            query = query.where(Team.parent_team_id == parent_team_id)

        if user_id:
            # Nur Teams in denen User Mitglied ist
            query = query.join(TeamMembership).where(
                TeamMembership.user_id == user_id,
                TeamMembership.is_active == True,
            )

        if search:
            search_term = f"%{search}%"
            query = query.where(
                or_(
                    Team.name.ilike(search_term),
                    Team.code.ilike(search_term),
                    Team.description.ilike(search_term),
                )
            )

        # Count
        count_query = select(func.count()).select_from(query.subquery())
        count_result = await self.db.execute(count_query)
        total = count_result.scalar() or 0

        # Pagination
        offset = (page - 1) * per_page
        query = query.order_by(Team.name).offset(offset).limit(per_page)

        result = await self.db.execute(query)
        teams = list(result.scalars().all())

        return teams, total

    async def update_team(
        self,
        team_id: UUID,
        actor_id: UUID,
        **updates: Any,
    ) -> Optional[Team]:
        """
        Aktualisiert ein Team.

        Args:
            team_id: Team UUID
            actor_id: User der aktualisiert
            **updates: Felder zum Aktualisieren

        Returns:
            Aktualisiertes Team oder None
        """
        team = await self.get_team(team_id)
        if not team:
            return None

        # Erlaubte Felder
        allowed_fields = {
            "name", "description", "code", "visibility", "status",
            "start_date", "end_date", "settings", "default_permissions",
            "tags", "email", "slack_channel",
        }

        changed_fields = []
        for field, value in updates.items():
            if field in allowed_fields and getattr(team, field) != value:
                setattr(team, field, value)
                changed_fields.append(field)

        if changed_fields:
            team.updated_at = utc_now()

            await self._log_activity(
                team_id=team_id,
                activity_type=TeamActivityType.TEAM_UPDATED,
                actor_id=actor_id,
                title=f"Team '{team.name}' aktualisiert",
                details={"updated_fields": changed_fields},
            )

            await self.db.commit()
            await self.db.refresh(team)

            logger.info(
                "team_updated",
                team_id=str(team_id),
                fields=changed_fields,
                actor=str(actor_id)[:8],
            )

        return team

    async def archive_team(
        self,
        team_id: UUID,
        actor_id: UUID,
    ) -> Optional[Team]:
        """
        Archiviert ein Team.

        Args:
            team_id: Team UUID
            actor_id: User der archiviert

        Returns:
            Archiviertes Team oder None
        """
        team = await self.get_team(team_id)
        if not team:
            return None

        team.status = TeamStatus.ARCHIVED
        team.archived_at = utc_now()

        # Alle Mitgliedschaften deaktivieren
        memberships_query = select(TeamMembership).where(
            TeamMembership.team_id == team_id,
            TeamMembership.is_active == True,
        )
        result = await self.db.execute(memberships_query)
        for membership in result.scalars().all():
            membership.is_active = False
            membership.left_at = utc_now()

        team.active_member_count = 0

        await self._log_activity(
            team_id=team_id,
            activity_type=TeamActivityType.TEAM_ARCHIVED,
            actor_id=actor_id,
            title=f"Team '{team.name}' archiviert",
        )

        await self.db.commit()
        await self.db.refresh(team)

        logger.info(
            "team_archived",
            team_id=str(team_id),
            actor=str(actor_id)[:8],
        )

        return team

    # =========================================================================
    # Mitgliedschaften
    # =========================================================================

    async def add_member(
        self,
        team_id: UUID,
        user_id: UUID,
        role: TeamMemberRole = TeamMemberRole.MEMBER,
        invited_by_id: Optional[UUID] = None,
        title: Optional[str] = None,
        allocation_percent: int = 100,
        valid_until: Optional[datetime] = None,
        reason: Optional[str] = None,
    ) -> TeamMembership:
        """
        Fuegt ein Mitglied zum Team hinzu.

        Args:
            team_id: Team UUID
            user_id: User UUID
            role: Rolle im Team
            invited_by_id: Wer hat eingeladen
            title: Funktion im Team
            allocation_percent: Prozentuale Zuordnung
            valid_until: Gueltig bis (fuer temporaere Mitgliedschaften)
            reason: Grund fuer Mitgliedschaft

        Returns:
            Erstellte Mitgliedschaft
        """
        # Pruefen ob bereits Mitglied
        existing = await self.get_membership(team_id, user_id)
        if existing:
            if existing.is_active:
                raise ValueError("User ist bereits Mitglied des Teams")
            # Reaktivieren
            existing.is_active = True
            existing.role = role
            existing.valid_until = valid_until
            existing.left_at = None
            existing.updated_at = utc_now()
            await self.db.commit()
            await self.db.refresh(existing)
            return existing

        membership = TeamMembership(
            team_id=team_id,
            user_id=user_id,
            role=role,
            invited_by_id=invited_by_id,
            title=title,
            allocation_percent=allocation_percent,
            valid_until=valid_until,
            reason=reason,
            is_active=True,
        )

        self.db.add(membership)

        # Team-Counter aktualisieren
        team = await self.get_team(team_id)
        if team:
            team.member_count += 1
            team.active_member_count += 1

        # Activity loggen
        await self._log_activity(
            team_id=team_id,
            activity_type=TeamActivityType.MEMBER_JOINED,
            actor_id=invited_by_id or user_id,
            target_user_id=user_id,
            title="Neues Mitglied",
            details={"role": role.value},
        )

        await self.db.commit()
        await self.db.refresh(membership)

        logger.info(
            "member_added",
            team_id=str(team_id),
            user_id=str(user_id)[:8],
            role=role.value,
        )

        return membership

    async def remove_member(
        self,
        team_id: UUID,
        user_id: UUID,
        actor_id: UUID,
        reason: Optional[str] = None,
    ) -> bool:
        """
        Entfernt ein Mitglied aus dem Team.

        Args:
            team_id: Team UUID
            user_id: User UUID
            actor_id: Wer entfernt
            reason: Grund

        Returns:
            True wenn erfolgreich
        """
        membership = await self.get_membership(team_id, user_id)
        if not membership or not membership.is_active:
            return False

        membership.is_active = False
        membership.left_at = utc_now()

        # Team-Counter aktualisieren
        team = await self.get_team(team_id)
        if team:
            team.active_member_count = max(0, team.active_member_count - 1)

        # Activity loggen
        await self._log_activity(
            team_id=team_id,
            activity_type=TeamActivityType.MEMBER_LEFT,
            actor_id=actor_id,
            target_user_id=user_id,
            title="Mitglied entfernt",
            details={"reason": reason} if reason else {},
        )

        await self.db.commit()

        logger.info(
            "member_removed",
            team_id=str(team_id),
            user_id=str(user_id)[:8],
            actor=str(actor_id)[:8],
        )

        return True

    async def update_member_role(
        self,
        team_id: UUID,
        user_id: UUID,
        new_role: TeamMemberRole,
        actor_id: UUID,
    ) -> Optional[TeamMembership]:
        """
        Aendert die Rolle eines Mitglieds.

        Args:
            team_id: Team UUID
            user_id: User UUID
            new_role: Neue Rolle
            actor_id: Wer aendert

        Returns:
            Aktualisierte Mitgliedschaft oder None
        """
        membership = await self.get_membership(team_id, user_id)
        if not membership or not membership.is_active:
            return None

        old_role = membership.role
        membership.role = new_role
        membership.updated_at = utc_now()

        # Activity loggen
        await self._log_activity(
            team_id=team_id,
            activity_type=TeamActivityType.MEMBER_ROLE_CHANGED,
            actor_id=actor_id,
            target_user_id=user_id,
            title="Rolle geaendert",
            details={
                "old_role": old_role.value,
                "new_role": new_role.value,
            },
        )

        await self.db.commit()
        await self.db.refresh(membership)

        logger.info(
            "member_role_changed",
            team_id=str(team_id),
            user_id=str(user_id)[:8],
            old_role=old_role.value,
            new_role=new_role.value,
        )

        return membership

    async def get_membership(
        self,
        team_id: UUID,
        user_id: UUID,
    ) -> Optional[TeamMembership]:
        """
        Holt eine Mitgliedschaft.

        Args:
            team_id: Team UUID
            user_id: User UUID

        Returns:
            Mitgliedschaft oder None
        """
        query = select(TeamMembership).where(
            TeamMembership.team_id == team_id,
            TeamMembership.user_id == user_id,
        )
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def list_members(
        self,
        team_id: UUID,
        role: Optional[TeamMemberRole] = None,
        include_inactive: bool = False,
        page: int = 1,
        per_page: int = 50,
    ) -> tuple[List[TeamMembership], int]:
        """
        Listet Team-Mitglieder.

        Args:
            team_id: Team UUID
            role: Nach Rolle filtern
            include_inactive: Inaktive einschliessen
            page: Seite
            per_page: Pro Seite

        Returns:
            Tuple aus (Mitgliedschaften, Total)
        """
        query = select(TeamMembership).where(
            TeamMembership.team_id == team_id
        ).options(selectinload(TeamMembership.user))

        if not include_inactive:
            query = query.where(TeamMembership.is_active == True)

        if role:
            query = query.where(TeamMembership.role == role)

        # Count
        count_query = select(func.count()).select_from(query.subquery())
        count_result = await self.db.execute(count_query)
        total = count_result.scalar() or 0

        # Pagination
        offset = (page - 1) * per_page
        query = query.order_by(
            TeamMembership.role,
            TeamMembership.joined_at,
        ).offset(offset).limit(per_page)

        result = await self.db.execute(query)
        memberships = list(result.scalars().all())

        return memberships, total

    async def get_user_teams(
        self,
        user_id: UUID,
        company_id: UUID,
        include_inactive: bool = False,
    ) -> List[Team]:
        """
        Holt alle Teams eines Users.

        Args:
            user_id: User UUID
            company_id: Company UUID
            include_inactive: Inaktive Teams einschliessen

        Returns:
            Liste der Teams
        """
        query = (
            select(Team)
            .join(TeamMembership)
            .where(
                TeamMembership.user_id == user_id,
                TeamMembership.is_active == True,
                Team.company_id == company_id,
            )
        )

        if not include_inactive:
            query = query.where(Team.status == TeamStatus.ACTIVE)

        result = await self.db.execute(query)
        return list(result.scalars().all())

    # =========================================================================
    # Einladungen
    # =========================================================================

    async def create_invitation(
        self,
        team_id: UUID,
        invited_by_id: UUID,
        user_id: Optional[UUID] = None,
        email: Optional[str] = None,
        role: TeamMemberRole = TeamMemberRole.MEMBER,
        personal_message: Optional[str] = None,
        expires_in_days: int = 7,
    ) -> TeamInvitation:
        """
        Erstellt eine Team-Einladung.

        Args:
            team_id: Team UUID
            invited_by_id: Einladender User
            user_id: Eingeladener User (wenn bekannt)
            email: Email (fuer externe Einladungen)
            role: Geplante Rolle
            personal_message: Persoenliche Nachricht
            expires_in_days: Gueltigkeitsdauer

        Returns:
            Erstellte Einladung
        """
        if not user_id and not email:
            raise ValueError("user_id oder email muss angegeben werden")

        # Pruefen ob bereits eingeladen
        if user_id:
            existing = await self._get_pending_invitation(team_id, user_id=user_id)
            if existing:
                raise ValueError("User wurde bereits eingeladen")
        elif email:
            existing = await self._get_pending_invitation(team_id, email=email)
            if existing:
                raise ValueError("Diese Email wurde bereits eingeladen")

        invitation = TeamInvitation(
            team_id=team_id,
            invited_by_id=invited_by_id,
            user_id=user_id,
            email=email,
            role=role,
            personal_message=personal_message,
            token=secrets.token_urlsafe(32),
            expires_at=utc_now() + timedelta(days=expires_in_days),
            status=InvitationStatus.PENDING,
            invitation_sent_at=utc_now(),
        )

        self.db.add(invitation)
        await self.db.commit()
        await self.db.refresh(invitation)

        logger.info(
            "invitation_created",
            team_id=str(team_id),
            invited_by=str(invited_by_id)[:8],
            target=str(user_id)[:8] if user_id else email,
        )

        return invitation

    async def accept_invitation(
        self,
        invitation_id: UUID,
        user_id: UUID,
    ) -> TeamMembership:
        """
        Nimmt eine Einladung an.

        Args:
            invitation_id: Einladungs-UUID
            user_id: User der annimmt

        Returns:
            Erstellte Mitgliedschaft
        """
        invitation = await self._get_invitation(invitation_id)
        if not invitation:
            raise ValueError("Einladung nicht gefunden")

        if invitation.status != InvitationStatus.PENDING:
            raise ValueError(f"Einladung hat Status: {invitation.status.value}")

        if invitation.is_expired:
            invitation.status = InvitationStatus.EXPIRED
            await self.db.commit()
            raise ValueError("Einladung ist abgelaufen")

        # Pruefen ob passender User
        if invitation.user_id and invitation.user_id != user_id:
            raise ValueError("Diese Einladung ist fuer einen anderen User")

        # Mitgliedschaft erstellen
        membership = await self.add_member(
            team_id=invitation.team_id,
            user_id=user_id,
            role=invitation.role,
            invited_by_id=invitation.invited_by_id,
            reason=f"Einladung angenommen ({invitation_id})",
        )

        # Einladung aktualisieren
        invitation.status = InvitationStatus.ACCEPTED
        invitation.responded_at = utc_now()

        await self.db.commit()

        logger.info(
            "invitation_accepted",
            invitation_id=str(invitation_id),
            user_id=str(user_id)[:8],
            team_id=str(invitation.team_id),
        )

        return membership

    async def decline_invitation(
        self,
        invitation_id: UUID,
        user_id: UUID,
        reason: Optional[str] = None,
    ) -> bool:
        """
        Lehnt eine Einladung ab.

        Args:
            invitation_id: Einladungs-UUID
            user_id: User der ablehnt
            reason: Grund fuer Ablehnung

        Returns:
            True wenn erfolgreich
        """
        invitation = await self._get_invitation(invitation_id)
        if not invitation:
            return False

        if invitation.user_id and invitation.user_id != user_id:
            raise ValueError("Diese Einladung ist fuer einen anderen User")

        invitation.status = InvitationStatus.DECLINED
        invitation.responded_at = utc_now()
        invitation.decline_reason = reason

        await self.db.commit()

        logger.info(
            "invitation_declined",
            invitation_id=str(invitation_id),
            user_id=str(user_id)[:8],
        )

        return True

    async def _get_invitation(self, invitation_id: UUID) -> Optional[TeamInvitation]:
        """Holt eine Einladung nach ID."""
        query = select(TeamInvitation).where(TeamInvitation.id == invitation_id)
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def _get_pending_invitation(
        self,
        team_id: UUID,
        user_id: Optional[UUID] = None,
        email: Optional[str] = None,
    ) -> Optional[TeamInvitation]:
        """Holt eine ausstehende Einladung."""
        query = select(TeamInvitation).where(
            TeamInvitation.team_id == team_id,
            TeamInvitation.status == InvitationStatus.PENDING,
        )

        if user_id:
            query = query.where(TeamInvitation.user_id == user_id)
        elif email:
            query = query.where(TeamInvitation.email == email)

        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    # =========================================================================
    # Aktivitaeten
    # =========================================================================

    async def _log_activity(
        self,
        team_id: UUID,
        activity_type: TeamActivityType,
        actor_id: Optional[UUID],
        title: str,
        description: Optional[str] = None,
        target_user_id: Optional[UUID] = None,
        target_document_id: Optional[UUID] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> TeamActivity:
        """Loggt eine Team-Aktivitaet."""
        activity = TeamActivity(
            team_id=team_id,
            activity_type=activity_type,
            actor_id=actor_id,
            title=title,
            description=description,
            target_user_id=target_user_id,
            target_document_id=target_document_id,
            details=details or {},
        )

        self.db.add(activity)
        return activity

    async def get_team_activity(
        self,
        team_id: UUID,
        activity_types: Optional[List[TeamActivityType]] = None,
        actor_id: Optional[UUID] = None,
        since: Optional[datetime] = None,
        page: int = 1,
        per_page: int = 50,
    ) -> tuple[List[TeamActivity], int]:
        """
        Holt Team-Aktivitaeten.

        Args:
            team_id: Team UUID
            activity_types: Nach Typen filtern
            actor_id: Nach Actor filtern
            since: Aktivitaeten seit Zeitpunkt
            page: Seite
            per_page: Pro Seite

        Returns:
            Tuple aus (Aktivitaeten, Total)
        """
        query = select(TeamActivity).where(
            TeamActivity.team_id == team_id,
            TeamActivity.is_public == True,
        ).options(
            selectinload(TeamActivity.actor),
            selectinload(TeamActivity.target_user),
        )

        if activity_types:
            query = query.where(TeamActivity.activity_type.in_(activity_types))

        if actor_id:
            query = query.where(TeamActivity.actor_id == actor_id)

        if since:
            query = query.where(TeamActivity.created_at >= since)

        # Count
        count_query = select(func.count()).select_from(query.subquery())
        count_result = await self.db.execute(count_query)
        total = count_result.scalar() or 0

        # Pagination (neueste zuerst)
        offset = (page - 1) * per_page
        query = query.order_by(TeamActivity.created_at.desc()).offset(offset).limit(per_page)

        result = await self.db.execute(query)
        activities = list(result.scalars().all())

        return activities, total

    # =========================================================================
    # Dokument-Freigabe
    # =========================================================================

    async def share_document(
        self,
        team_id: UUID,
        document_id: UUID,
        shared_by_id: UUID,
        permission: TeamDocumentPermission = TeamDocumentPermission.READ,
        valid_until: Optional[datetime] = None,
        note: Optional[str] = None,
    ) -> TeamDocument:
        """
        Teilt ein Dokument mit dem Team.

        Args:
            team_id: Team UUID
            document_id: Document UUID
            shared_by_id: Wer teilt
            permission: Berechtigung
            valid_until: Gueltig bis
            note: Notiz

        Returns:
            TeamDocument
        """
        # Pruefen ob bereits geteilt
        existing = await self._get_team_document(team_id, document_id)
        if existing:
            # Update permission
            existing.permission = permission
            existing.valid_until = valid_until
            existing.note = note
            await self.db.commit()
            await self.db.refresh(existing)
            return existing

        team_doc = TeamDocument(
            team_id=team_id,
            document_id=document_id,
            shared_by_id=shared_by_id,
            permission=permission,
            valid_until=valid_until,
            note=note,
        )

        self.db.add(team_doc)

        # Activity loggen
        await self._log_activity(
            team_id=team_id,
            activity_type=TeamActivityType.DOCUMENT_SHARED,
            actor_id=shared_by_id,
            target_document_id=document_id,
            title="Dokument geteilt",
            details={"permission": permission.value},
        )

        await self.db.commit()
        await self.db.refresh(team_doc)

        logger.info(
            "document_shared_with_team",
            team_id=str(team_id),
            document_id=str(document_id)[:8],
            permission=permission.value,
        )

        return team_doc

    async def _get_team_document(
        self,
        team_id: UUID,
        document_id: UUID,
    ) -> Optional[TeamDocument]:
        """Holt eine Team-Dokument-Verknuepfung."""
        query = select(TeamDocument).where(
            TeamDocument.team_id == team_id,
            TeamDocument.document_id == document_id,
        )
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    # =========================================================================
    # Berechtigungen pruefen
    # =========================================================================

    async def check_permission(
        self,
        team_id: UUID,
        user_id: UUID,
        required_role: TeamMemberRole = TeamMemberRole.MEMBER,
    ) -> bool:
        """
        Prueft ob User die erforderliche Rolle hat.

        Args:
            team_id: Team UUID
            user_id: User UUID
            required_role: Erforderliche Rolle

        Returns:
            True wenn berechtigt
        """
        membership = await self.get_membership(team_id, user_id)
        if not membership or not membership.is_currently_valid:
            return False

        # Rollen-Hierarchie: ADMIN > LEAD > DEPUTY > MEMBER > OBSERVER
        role_levels = {
            TeamMemberRole.OBSERVER: 0,
            TeamMemberRole.MEMBER: 1,
            TeamMemberRole.DEPUTY: 2,
            TeamMemberRole.LEAD: 3,
            TeamMemberRole.ADMIN: 4,
        }

        return role_levels.get(membership.role, 0) >= role_levels.get(required_role, 1)

    async def is_team_admin(self, team_id: UUID, user_id: UUID) -> bool:
        """Prueft ob User Team-Admin ist."""
        return await self.check_permission(team_id, user_id, TeamMemberRole.ADMIN)

    async def is_team_leader(self, team_id: UUID, user_id: UUID) -> bool:
        """Prueft ob User Team-Leader ist."""
        return await self.check_permission(team_id, user_id, TeamMemberRole.LEAD)


# =============================================================================
# Factory
# =============================================================================


def get_team_service(db: AsyncSession) -> TeamService:
    """Factory fuer TeamService."""
    return TeamService(db)
