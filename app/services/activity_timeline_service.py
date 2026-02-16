# -*- coding: utf-8 -*-
"""
Activity Timeline Service für Ablage-System.

Multi-Level Activity Tracking:
- Dokument-zentriert: Alles was mit einem Dokument passiert
- Team-weit: Aktivitäten aller Team-Mitglieder
- Vorgang-basiert: Document Chains als Activity-Stream
- Projekt-basiert: Projektteam-Aktivitäten
- Company-Timeline: Admins sehen alles (permission-filtered)
- Benutzer-Timeline: Eigene Aktivitäten

Phase 3.3 der Strategischen Roadmap (Januar 2026).
"""

from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, Union
from uuid import UUID
from enum import Enum
import logging

from sqlalchemy import select, and_, or_, func, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from pydantic import BaseModel, Field

from app.db.models import (
    User,
    Document,
    DocumentActivity,
    Company,
)
from app.db.models_team import Team, TeamMembership, TeamActivity

logger = logging.getLogger(__name__)


# =============================================================================
# Activity Types & Models
# =============================================================================


class ActivitySource(str, Enum):
    """Quelle der Aktivität."""
    DOCUMENT = "document"
    TEAM = "team"
    CHAIN = "chain"
    WORKFLOW = "workflow"
    APPROVAL = "approval"
    COMMENT = "comment"
    SYSTEM = "system"


class UnifiedActivity(BaseModel):
    """Einheitliches Activity-Modell für alle Quellen."""
    id: UUID
    source: ActivitySource
    activity_type: str
    title: str
    description: Optional[str] = None

    # Actor
    actor_id: Optional[UUID] = None
    actor_name: Optional[str] = None
    actor_avatar: Optional[str] = None

    # Target Entity
    target_type: Optional[str] = None  # document, team, chain, etc.
    target_id: Optional[UUID] = None
    target_name: Optional[str] = None

    # Related Entity (secondary)
    related_type: Optional[str] = None
    related_id: Optional[UUID] = None
    related_name: Optional[str] = None

    # Context
    company_id: UUID
    team_id: Optional[UUID] = None
    chain_id: Optional[UUID] = None

    # Metadata
    metadata: Dict[str, Any] = Field(default_factory=dict)

    # Timestamps
    created_at: datetime

    # Display
    icon: Optional[str] = None
    color: Optional[str] = None
    is_important: bool = False

    class Config:
        from_attributes = True


class TimelineFilter(BaseModel):
    """Filter für Timeline-Abfragen."""
    sources: Optional[List[ActivitySource]] = None
    activity_types: Optional[List[str]] = None
    actor_ids: Optional[List[UUID]] = None
    target_types: Optional[List[str]] = None
    date_from: Optional[datetime] = None
    date_until: Optional[datetime] = None
    search_query: Optional[str] = None
    important_only: bool = False


# =============================================================================
# Activity Timeline Service
# =============================================================================


class ActivityTimelineService:
    """Service für Multi-Level Activity Timeline.

    Aggregiert Aktivitäten aus verschiedenen Quellen:
    - DocumentActivity (Dokument-bezogen)
    - TeamActivity (Team-bezogen)
    - Document Chains
    - Workflows & Approvals
    - Kommentare
    - System-Events
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    # =========================================================================
    # My Activities (Eigene Aktivitäten)
    # =========================================================================

    async def get_my_activities(
        self,
        user_id: UUID,
        company_id: UUID,
        filters: Optional[TimelineFilter] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[UnifiedActivity]:
        """Holt Aktivitäten des aktuellen Users.

        Umfasst:
        - Aktivitäten die der User selbst durchgeführt hat
        - Aktivitäten an Dokumenten die dem User gehören
        - Team-Aktivitäten in Teams wo User Mitglied ist

        Args:
            user_id: ID des Users
            company_id: Company-ID für Multi-Tenant
            filters: Optional Filter
            limit: Max. Anzahl
            offset: Offset für Pagination

        Returns:
            Liste von UnifiedActivity
        """
        activities = []

        # 1. Document Activities (vom User oder an seinen Dokumenten)
        doc_activities = await self._get_document_activities(
            company_id=company_id,
            user_id=user_id,
            include_owned_docs=True,
            filters=filters,
            limit=limit,
        )
        activities.extend(doc_activities)

        # 2. Team Activities (in Teams wo User Mitglied ist)
        team_activities = await self._get_team_activities_for_user(
            user_id=user_id,
            company_id=company_id,
            filters=filters,
            limit=limit,
        )
        activities.extend(team_activities)

        # Sortieren nach Zeit und limitieren
        activities.sort(key=lambda a: a.created_at, reverse=True)
        return activities[offset:offset + limit]

    # =========================================================================
    # Team Timeline
    # =========================================================================

    async def get_team_timeline(
        self,
        team_id: UUID,
        user_id: UUID,
        company_id: UUID,
        filters: Optional[TimelineFilter] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[UnifiedActivity]:
        """Holt Timeline für ein Team.

        Umfasst:
        - Team-Aktivitäten (Mitgliedschaften, Einstellungen)
        - Aktivitäten aller Team-Mitglieder an Team-Dokumenten

        Args:
            team_id: Team-ID
            user_id: Anfragender User (für Berechtigungsprüfung)
            company_id: Company-ID
            filters: Optional Filter
            limit: Max. Anzahl
            offset: Offset

        Returns:
            Liste von UnifiedActivity
        """
        # Berechtigung prüfen (User muss Team-Mitglied sein)
        is_member = await self._check_team_membership(team_id, user_id)
        if not is_member:
            return []

        activities = []

        # 1. Team-eigene Aktivitäten
        result = await self.db.execute(
            select(TeamActivity)
            .options(selectinload(TeamActivity.actor))
            .where(TeamActivity.team_id == team_id)
            .order_by(desc(TeamActivity.created_at))
            .limit(limit * 2)  # Mehr holen für Merge
        )
        team_acts = result.scalars().all()

        for ta in team_acts:
            activities.append(self._convert_team_activity(ta))

        # 2. Dokument-Aktivitäten von Team-Mitgliedern
        # Hole Team-Mitglieder
        members_result = await self.db.execute(
            select(TeamMembership.user_id)
            .where(
                TeamMembership.team_id == team_id,
                TeamMembership.is_active == True,
            )
        )
        member_ids = [m for m in members_result.scalars().all()]

        if member_ids:
            doc_activities = await self._get_document_activities_by_users(
                company_id=company_id,
                user_ids=member_ids,
                filters=filters,
                limit=limit,
            )
            activities.extend(doc_activities)

        # Sortieren und limitieren
        activities.sort(key=lambda a: a.created_at, reverse=True)
        return activities[offset:offset + limit]

    # =========================================================================
    # Document Timeline
    # =========================================================================

    async def get_document_timeline(
        self,
        document_id: UUID,
        company_id: UUID,
        filters: Optional[TimelineFilter] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[UnifiedActivity]:
        """Holt Timeline für ein einzelnes Dokument.

        Umfasst alle Aktivitäten die das Dokument betreffen:
        - Views, Downloads
        - Bearbeitungen
        - OCR-Verarbeitung
        - Kommentare
        - Genehmigungen
        - Chain-Verknüpfungen

        Args:
            document_id: Dokument-ID
            company_id: Company-ID
            filters: Optional Filter
            limit: Max. Anzahl
            offset: Offset

        Returns:
            Liste von UnifiedActivity
        """
        result = await self.db.execute(
            select(DocumentActivity)
            .where(DocumentActivity.document_id == document_id)
            .order_by(desc(DocumentActivity.created_at))
            .limit(limit)
            .offset(offset)
        )
        doc_activities = result.scalars().all()

        activities = []
        for da in doc_activities:
            # User laden
            user = None
            if da.user_id:
                user_result = await self.db.execute(
                    select(User).where(User.id == da.user_id)
                )
                user = user_result.scalar_one_or_none()

            # Document laden für Namen
            doc_result = await self.db.execute(
                select(Document).where(Document.id == da.document_id)
            )
            doc = doc_result.scalar_one_or_none()

            activities.append(self._convert_document_activity(da, user, doc))

        # Filter anwenden falls vorhanden
        if filters:
            activities = self._apply_filters(activities, filters)

        return activities

    # =========================================================================
    # Chain Timeline (Vorgangs-Timeline)
    # =========================================================================

    async def get_chain_timeline(
        self,
        chain_id: UUID,
        company_id: UUID,
        filters: Optional[TimelineFilter] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[UnifiedActivity]:
        """Holt Timeline für eine Document Chain (Vorgang).

        Aggregiert Aktivitäten aller Dokumente in der Chain:
        - Angebot erstellt
        - Auftrag verknüpft
        - Lieferschein hinzugefügt
        - Rechnung empfangen
        - Status-Änderungen

        Args:
            chain_id: Chain-ID
            company_id: Company-ID
            filters: Optional Filter
            limit: Max. Anzahl
            offset: Offset

        Returns:
            Liste von UnifiedActivity
        """
        # Document Chain Dokumente holen
        # Hier müsste DocumentChain Model importiert werden
        # Vereinfacht: Wir holen Dokumente mit chain_id Referenz

        activities = []

        # DocumentChain Integration - hole Aktivitäten für verknüpfte Dokumente
        try:
            from app.db.models import DocumentChain, DocumentChainItem

            # Lade Chain mit Items
            chain_query = select(DocumentChain).where(DocumentChain.id == chain_id)
            chain_result = await self.db.execute(chain_query)
            chain = chain_result.scalar_one_or_none()

            if not chain:
                return activities

            # Lade verknüpfte Dokument-IDs
            items_query = select(DocumentChainItem.document_id).where(
                DocumentChainItem.chain_id == chain_id
            )
            items_result = await self.db.execute(items_query)
            document_ids = items_result.scalars().all()

            # Hole Aktivitäten für alle Dokumente der Chain
            for doc_id in document_ids:
                doc_activities = await self.get_document_timeline(
                    document_id=doc_id,
                    user_id=user_id,
                    company_id=company_id,
                    limit=10,  # Begrenzt pro Dokument
                )
                activities.extend(doc_activities)

            # Sortiere nach Zeitstempel
            activities.sort(key=lambda a: a.timestamp, reverse=True)

        except ImportError:
            # DocumentChain Model nicht verfügbar
            pass
        except Exception as e:
            logger.warning("document_chain_timeline_error", error=str(e))

        return activities

    # =========================================================================
    # Company Timeline (Admin)
    # =========================================================================

    async def get_company_timeline(
        self,
        company_id: UUID,
        user_id: UUID,
        is_admin: bool = False,
        filters: Optional[TimelineFilter] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[UnifiedActivity]:
        """Holt Company-weite Timeline (nur für Admins).

        Zeigt alle Aktivitäten der Company:
        - Alle Dokument-Aktivitäten
        - Alle Team-Aktivitäten
        - System-Events

        Args:
            company_id: Company-ID
            user_id: Anfragender User
            is_admin: Ob User Admin ist
            filters: Optional Filter
            limit: Max. Anzahl
            offset: Offset

        Returns:
            Liste von UnifiedActivity
        """
        if not is_admin:
            # Nicht-Admins bekommen nur eingeschränkte Sicht
            return await self.get_my_activities(
                user_id=user_id,
                company_id=company_id,
                filters=filters,
                limit=limit,
                offset=offset,
            )

        activities = []

        # 1. Alle Document Activities der Company
        doc_activities = await self._get_document_activities(
            company_id=company_id,
            user_id=None,  # Alle User
            include_owned_docs=False,
            filters=filters,
            limit=limit,
        )
        activities.extend(doc_activities)

        # 2. Alle Team Activities der Company
        result = await self.db.execute(
            select(TeamActivity)
            .join(Team, TeamActivity.team_id == Team.id)
            .options(selectinload(TeamActivity.actor))
            .where(Team.company_id == company_id)
            .order_by(desc(TeamActivity.created_at))
            .limit(limit)
        )
        team_acts = result.scalars().all()

        for ta in team_acts:
            activities.extend([self._convert_team_activity(ta)])

        # Sortieren und limitieren
        activities.sort(key=lambda a: a.created_at, reverse=True)
        return activities[offset:offset + limit]

    # =========================================================================
    # Activity Statistics
    # =========================================================================

    async def get_activity_statistics(
        self,
        company_id: UUID,
        user_id: Optional[UUID] = None,
        team_id: Optional[UUID] = None,
        date_from: Optional[datetime] = None,
        date_until: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """Berechnet Aktivitäts-Statistiken.

        Args:
            company_id: Company-ID
            user_id: Optional User-Filter
            team_id: Optional Team-Filter
            date_from: Startdatum
            date_until: Enddatum

        Returns:
            Dict mit Statistiken
        """
        if not date_from:
            date_from = datetime.utcnow() - timedelta(days=30)
        if not date_until:
            date_until = datetime.utcnow()

        # Basis-Query für DocumentActivity
        base_query = select(func.count(DocumentActivity.id)).where(
            DocumentActivity.created_at >= date_from,
            DocumentActivity.created_at <= date_until,
        )

        if user_id:
            base_query = base_query.where(DocumentActivity.user_id == user_id)

        # Total Activities
        total_result = await self.db.execute(base_query)
        total_activities = total_result.scalar() or 0

        # Activities by Type
        type_query = (
            select(
                DocumentActivity.activity_type,
                func.count(DocumentActivity.id).label("count")
            )
            .where(
                DocumentActivity.created_at >= date_from,
                DocumentActivity.created_at <= date_until,
            )
            .group_by(DocumentActivity.activity_type)
        )

        if user_id:
            type_query = type_query.where(DocumentActivity.user_id == user_id)

        type_result = await self.db.execute(type_query)
        activities_by_type = {row[0]: row[1] for row in type_result.all()}

        # Activities by Day
        daily_query = (
            select(
                func.date_trunc('day', DocumentActivity.created_at).label("day"),
                func.count(DocumentActivity.id).label("count")
            )
            .where(
                DocumentActivity.created_at >= date_from,
                DocumentActivity.created_at <= date_until,
            )
            .group_by(func.date_trunc('day', DocumentActivity.created_at))
            .order_by(func.date_trunc('day', DocumentActivity.created_at))
        )

        if user_id:
            daily_query = daily_query.where(DocumentActivity.user_id == user_id)

        daily_result = await self.db.execute(daily_query)
        activities_by_day = [
            {"date": row[0].isoformat() if row[0] else None, "count": row[1]}
            for row in daily_result.all()
        ]

        # Top Active Users (nur für Company-Admin)
        top_users_query = (
            select(
                DocumentActivity.user_id,
                func.count(DocumentActivity.id).label("count")
            )
            .where(
                DocumentActivity.created_at >= date_from,
                DocumentActivity.created_at <= date_until,
            )
            .group_by(DocumentActivity.user_id)
            .order_by(desc(func.count(DocumentActivity.id)))
            .limit(10)
        )

        top_users_result = await self.db.execute(top_users_query)
        top_users_data = top_users_result.all()

        # User-Namen laden
        top_users = []
        for user_uuid, count in top_users_data:
            if user_uuid:
                user_result = await self.db.execute(
                    select(User).where(User.id == user_uuid)
                )
                user = user_result.scalar_one_or_none()
                if user:
                    top_users.append({
                        "user_id": str(user_uuid),
                        "user_name": user.full_name or user.username,
                        "activity_count": count
                    })

        return {
            "total_activities": total_activities,
            "activities_by_type": activities_by_type,
            "activities_by_day": activities_by_day,
            "top_users": top_users,
            "date_range": {
                "from": date_from.isoformat(),
                "until": date_until.isoformat(),
            }
        }

    # =========================================================================
    # Internal Helpers
    # =========================================================================

    async def _get_document_activities(
        self,
        company_id: UUID,
        user_id: Optional[UUID],
        include_owned_docs: bool,
        filters: Optional[TimelineFilter],
        limit: int,
    ) -> List[UnifiedActivity]:
        """Holt Document Activities mit diversen Filtern."""
        # Basis-Query mit Company-Join
        query = (
            select(DocumentActivity)
            .join(Document, DocumentActivity.document_id == Document.id)
            .where(Document.company_id == company_id)
            .order_by(desc(DocumentActivity.created_at))
        )

        if user_id and include_owned_docs:
            # Aktivitäten vom User ODER an seinen Dokumenten
            query = query.where(
                or_(
                    DocumentActivity.user_id == user_id,
                    Document.created_by_id == user_id,
                )
            )
        elif user_id:
            # Nur Aktivitäten vom User
            query = query.where(DocumentActivity.user_id == user_id)

        # Filter anwenden
        if filters:
            if filters.date_from:
                query = query.where(DocumentActivity.created_at >= filters.date_from)
            if filters.date_until:
                query = query.where(DocumentActivity.created_at <= filters.date_until)
            if filters.activity_types:
                query = query.where(
                    DocumentActivity.activity_type.in_(filters.activity_types)
                )

        query = query.limit(limit)

        result = await self.db.execute(query)
        doc_activities = result.scalars().all()

        activities = []
        for da in doc_activities:
            # User und Document laden
            user = None
            if da.user_id:
                user_result = await self.db.execute(
                    select(User).where(User.id == da.user_id)
                )
                user = user_result.scalar_one_or_none()

            doc_result = await self.db.execute(
                select(Document).where(Document.id == da.document_id)
            )
            doc = doc_result.scalar_one_or_none()

            activities.append(self._convert_document_activity(da, user, doc))

        return activities

    async def _get_document_activities_by_users(
        self,
        company_id: UUID,
        user_ids: List[UUID],
        filters: Optional[TimelineFilter],
        limit: int,
    ) -> List[UnifiedActivity]:
        """Holt Document Activities für bestimmte User."""
        query = (
            select(DocumentActivity)
            .join(Document, DocumentActivity.document_id == Document.id)
            .where(
                Document.company_id == company_id,
                DocumentActivity.user_id.in_(user_ids),
            )
            .order_by(desc(DocumentActivity.created_at))
            .limit(limit)
        )

        if filters:
            if filters.date_from:
                query = query.where(DocumentActivity.created_at >= filters.date_from)
            if filters.date_until:
                query = query.where(DocumentActivity.created_at <= filters.date_until)

        result = await self.db.execute(query)
        doc_activities = result.scalars().all()

        activities = []
        for da in doc_activities:
            user = None
            if da.user_id:
                user_result = await self.db.execute(
                    select(User).where(User.id == da.user_id)
                )
                user = user_result.scalar_one_or_none()

            doc_result = await self.db.execute(
                select(Document).where(Document.id == da.document_id)
            )
            doc = doc_result.scalar_one_or_none()

            activities.append(self._convert_document_activity(da, user, doc))

        return activities

    async def _get_team_activities_for_user(
        self,
        user_id: UUID,
        company_id: UUID,
        filters: Optional[TimelineFilter],
        limit: int,
    ) -> List[UnifiedActivity]:
        """Holt Team Activities für Teams wo User Mitglied ist."""
        # Finde Teams des Users
        membership_result = await self.db.execute(
            select(TeamMembership.team_id)
            .where(
                TeamMembership.user_id == user_id,
                TeamMembership.is_active == True,
            )
        )
        team_ids = [t for t in membership_result.scalars().all()]

        if not team_ids:
            return []

        # Team Activities holen
        query = (
            select(TeamActivity)
            .options(selectinload(TeamActivity.actor))
            .where(TeamActivity.team_id.in_(team_ids))
            .order_by(desc(TeamActivity.created_at))
            .limit(limit)
        )

        if filters:
            if filters.date_from:
                query = query.where(TeamActivity.created_at >= filters.date_from)
            if filters.date_until:
                query = query.where(TeamActivity.created_at <= filters.date_until)

        result = await self.db.execute(query)
        team_activities = result.scalars().all()

        return [self._convert_team_activity(ta) for ta in team_activities]

    async def _check_team_membership(self, team_id: UUID, user_id: UUID) -> bool:
        """Prüft ob User Mitglied eines Teams ist."""
        result = await self.db.execute(
            select(TeamMembership.id)
            .where(
                TeamMembership.team_id == team_id,
                TeamMembership.user_id == user_id,
                TeamMembership.is_active == True,
            )
        )
        return result.scalar_one_or_none() is not None

    def _convert_document_activity(
        self,
        activity: DocumentActivity,
        user: Optional[User],
        document: Optional[Document],
    ) -> UnifiedActivity:
        """Konvertiert DocumentActivity zu UnifiedActivity."""
        return UnifiedActivity(
            id=activity.id,
            source=ActivitySource.DOCUMENT,
            activity_type=activity.activity_type or "unknown",
            title=self._get_activity_title(activity.activity_type),
            description=activity.description,
            actor_id=activity.user_id,
            actor_name=user.full_name if user else "System",
            actor_avatar=None,
            target_type="document",
            target_id=activity.document_id,
            target_name=document.original_filename if document else None,
            company_id=document.company_id if document else UUID(int=0),
            metadata=activity.activity_metadata or {},
            created_at=activity.created_at,
            icon=self._get_activity_icon(activity.activity_type),
            color=self._get_activity_color(activity.activity_type),
        )

    def _convert_team_activity(self, activity: TeamActivity) -> UnifiedActivity:
        """Konvertiert TeamActivity zu UnifiedActivity."""
        actor = activity.actor

        return UnifiedActivity(
            id=activity.id,
            source=ActivitySource.TEAM,
            activity_type=activity.activity_type,
            title=activity.title,
            description=activity.description,
            actor_id=activity.actor_id,
            actor_name=actor.full_name if actor else "System",
            actor_avatar=None,
            target_type="team",
            target_id=activity.team_id,
            target_name=None,  # Team-Name müsste separat geladen werden
            related_type=activity.target_entity_type,
            related_id=activity.target_entity_id,
            company_id=UUID(int=0),  # Müsste über Team geladen werden
            team_id=activity.team_id,
            metadata=activity.details or {},
            created_at=activity.created_at,
            icon=self._get_team_activity_icon(activity.activity_type),
            color="blue",
        )

    def _apply_filters(
        self,
        activities: List[UnifiedActivity],
        filters: TimelineFilter,
    ) -> List[UnifiedActivity]:
        """Wendet Filter auf Activity-Liste an."""
        result = activities

        if filters.sources:
            result = [a for a in result if a.source in filters.sources]

        if filters.activity_types:
            result = [a for a in result if a.activity_type in filters.activity_types]

        if filters.actor_ids:
            result = [a for a in result if a.actor_id in filters.actor_ids]

        if filters.target_types:
            result = [a for a in result if a.target_type in filters.target_types]

        if filters.date_from:
            result = [a for a in result if a.created_at >= filters.date_from]

        if filters.date_until:
            result = [a for a in result if a.created_at <= filters.date_until]

        if filters.important_only:
            result = [a for a in result if a.is_important]

        if filters.search_query:
            query = filters.search_query.lower()
            result = [
                a for a in result
                if query in (a.title or "").lower()
                or query in (a.description or "").lower()
                or query in (a.actor_name or "").lower()
            ]

        return result

    def _get_activity_title(self, activity_type: Optional[str]) -> str:
        """Gibt deutschen Titel für Activity-Typ zurück."""
        titles = {
            "document_created": "Dokument erstellt",
            "document_uploaded": "Dokument hochgeladen",
            "document_viewed": "Dokument angesehen",
            "document_downloaded": "Dokument heruntergeladen",
            "document_edited": "Dokument bearbeitet",
            "document_deleted": "Dokument gelöscht",
            "document_archived": "Dokument archiviert",
            "document_restored": "Dokument wiederhergestellt",
            "document_shared": "Dokument geteilt",
            "document_moved": "Dokument verschoben",
            "ocr_started": "OCR gestartet",
            "ocr_completed": "OCR abgeschlossen",
            "ocr_failed": "OCR fehlgeschlagen",
            "approval_requested": "Genehmigung angefordert",
            "approval_granted": "Genehmigung erteilt",
            "approval_rejected": "Genehmigung abgelehnt",
            "comment_added": "Kommentar hinzugefügt",
            "tag_added": "Tag hinzugefügt",
            "tag_removed": "Tag entfernt",
        }
        return titles.get(activity_type or "", activity_type or "Aktivität")

    def _get_activity_icon(self, activity_type: Optional[str]) -> str:
        """Gibt Icon-Name für Activity-Typ zurück."""
        icons = {
            "document_created": "file-plus",
            "document_uploaded": "upload",
            "document_viewed": "eye",
            "document_downloaded": "download",
            "document_edited": "edit",
            "document_deleted": "trash",
            "document_archived": "archive",
            "document_restored": "rotate-ccw",
            "document_shared": "share-2",
            "document_moved": "folder-input",
            "ocr_started": "scan",
            "ocr_completed": "check-circle",
            "ocr_failed": "x-circle",
            "approval_requested": "clock",
            "approval_granted": "check",
            "approval_rejected": "x",
            "comment_added": "message-circle",
            "tag_added": "tag",
            "tag_removed": "x",
        }
        return icons.get(activity_type or "", "activity")

    def _get_activity_color(self, activity_type: Optional[str]) -> str:
        """Gibt Farbe für Activity-Typ zurück."""
        colors = {
            "document_created": "green",
            "document_uploaded": "green",
            "document_viewed": "gray",
            "document_downloaded": "blue",
            "document_edited": "yellow",
            "document_deleted": "red",
            "document_archived": "gray",
            "document_restored": "green",
            "document_shared": "purple",
            "document_moved": "blue",
            "ocr_started": "yellow",
            "ocr_completed": "green",
            "ocr_failed": "red",
            "approval_requested": "yellow",
            "approval_granted": "green",
            "approval_rejected": "red",
            "comment_added": "blue",
            "tag_added": "purple",
            "tag_removed": "gray",
        }
        return colors.get(activity_type or "", "gray")

    def _get_team_activity_icon(self, activity_type: str) -> str:
        """Gibt Icon-Name für Team-Activity-Typ zurück."""
        icons = {
            "member_joined": "user-plus",
            "member_left": "user-minus",
            "member_role_changed": "shield",
            "team_created": "users",
            "team_updated": "settings",
            "team_archived": "archive",
            "document_shared": "share-2",
            "invitation_sent": "mail",
            "invitation_accepted": "check",
            "invitation_declined": "x",
        }
        return icons.get(activity_type, "activity")
