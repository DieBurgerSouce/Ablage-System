"""
Chat Sharing Service fuer Real-time Collaboration.

Stellt Funktionen fuer:
- Chat Session Sharing mit anderen Benutzern
- Zugriffsebenen-Verwaltung (View, Contribute, Manage)
- Collaborator-Management
"""

from typing import Optional, List
from uuid import UUID

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
import structlog

from app.db.models import (
    User,
    RAGChatSession,
    ChatSessionAccess,
    ChatSessionAccessLevel,
)

logger = structlog.get_logger(__name__)


class ChatSharingService:
    """
    Service fuer Chat Session Sharing.

    Bietet:
    - Sessions mit anderen Benutzern teilen
    - Zugriff entziehen
    - Collaborators auflisten
    - Geteilte Sessions abrufen
    - Zugriffspruefung
    """

    def __init__(self, db: AsyncSession):
        """
        Initialisiert den ChatSharingService.

        Args:
            db: AsyncSession fuer Datenbankzugriff
        """
        self.db = db

    async def share_session(
        self,
        session_id: UUID,
        owner_id: UUID,
        target_user_id: UUID,
        access_level: ChatSessionAccessLevel,
    ) -> ChatSessionAccess:
        """
        Teilt eine Chat Session mit einem anderen Benutzer.

        Args:
            session_id: ID der Chat Session
            owner_id: ID des Owners (muss Owner oder MANAGE sein)
            target_user_id: ID des Benutzers der Zugriff erhaelt
            access_level: Zugriffsebene (VIEW, CONTRIBUTE, MANAGE)

        Returns:
            ChatSessionAccess Objekt

        Raises:
            ValueError: Bei ungueltigem Zugriff oder Session
        """
        # Session laden und pruefen
        session = await self.db.get(RAGChatSession, session_id)
        if not session:
            logger.warning(
                "share_session_not_found",
                session_id=str(session_id),
                owner_id=str(owner_id),
            )
            raise ValueError("Chat Session nicht gefunden")

        # Zugriffspruefung: Owner oder MANAGE
        has_access = await self._can_manage(session, owner_id)
        if not has_access:
            logger.warning(
                "share_session_access_denied",
                session_id=str(session_id),
                owner_id=str(owner_id),
            )
            raise ValueError("Keine Berechtigung zum Teilen dieser Session")

        # Nicht mit sich selbst teilen
        if target_user_id == session.user_id:
            raise ValueError("Session kann nicht mit dem Owner geteilt werden")

        # Pruefen ob Ziel-User existiert
        target_user = await self.db.get(User, target_user_id)
        if not target_user:
            raise ValueError("Ziel-Benutzer nicht gefunden")

        # Existierenden Zugriff pruefen/aktualisieren
        existing = await self._get_access(session_id, target_user_id)
        if existing:
            # Update existing access level
            existing.access_level = access_level.value
            existing.granted_by_id = owner_id
            await self.db.flush()
            logger.info(
                "share_session_updated",
                session_id=str(session_id),
                target_user_id=str(target_user_id),
                access_level=access_level.value,
            )
            return existing

        # Neuen Zugriff erstellen
        access = ChatSessionAccess(
            session_id=session_id,
            user_id=target_user_id,
            granted_by_id=owner_id,
            access_level=access_level.value,
        )
        self.db.add(access)
        await self.db.flush()

        logger.info(
            "share_session_created",
            session_id=str(session_id),
            target_user_id=str(target_user_id),
            access_level=access_level.value,
            granted_by_id=str(owner_id),
        )

        return access

    async def revoke_access(
        self,
        session_id: UUID,
        owner_id: UUID,
        target_user_id: UUID,
    ) -> bool:
        """
        Entzieht einem Benutzer den Zugriff auf eine Chat Session.

        Args:
            session_id: ID der Chat Session
            owner_id: ID des Owners (muss Owner oder MANAGE sein)
            target_user_id: ID des Benutzers dessen Zugriff entzogen wird

        Returns:
            True wenn Zugriff entzogen wurde, False wenn kein Zugriff vorhanden war
        """
        # Session laden und pruefen
        session = await self.db.get(RAGChatSession, session_id)
        if not session:
            raise ValueError("Chat Session nicht gefunden")

        # Zugriffspruefung: Owner oder MANAGE
        has_access = await self._can_manage(session, owner_id)
        if not has_access:
            logger.warning(
                "revoke_access_denied",
                session_id=str(session_id),
                owner_id=str(owner_id),
            )
            raise ValueError("Keine Berechtigung zum Verwalten dieser Session")

        # Zugriff loeschen
        result = await self.db.execute(
            delete(ChatSessionAccess).where(
                ChatSessionAccess.session_id == session_id,
                ChatSessionAccess.user_id == target_user_id,
            )
        )
        await self.db.flush()

        deleted = result.rowcount > 0
        if deleted:
            logger.info(
                "share_session_revoked",
                session_id=str(session_id),
                target_user_id=str(target_user_id),
                revoked_by_id=str(owner_id),
            )

        return deleted

    async def get_collaborators(
        self,
        session_id: UUID,
        user_id: UUID,
    ) -> List[dict]:
        """
        Listet alle Collaborators einer Chat Session auf.

        Args:
            session_id: ID der Chat Session
            user_id: ID des anfragenden Users (muss Zugriff haben)

        Returns:
            Liste von Collaborator-Dicts mit user_id, username, email, access_level
        """
        # Zugriffspruefung (mindestens VIEW)
        if not await self.check_access(session_id, user_id, ChatSessionAccessLevel.VIEW):
            raise ValueError("Kein Zugriff auf diese Session")

        # Session mit Owner laden
        session = await self.db.get(RAGChatSession, session_id, options=[selectinload(RAGChatSession.user)])
        if not session:
            raise ValueError("Chat Session nicht gefunden")

        # Alle Zugriffsberechtigungen laden
        result = await self.db.execute(
            select(ChatSessionAccess)
            .where(ChatSessionAccess.session_id == session_id)
            .options(selectinload(ChatSessionAccess.user))
        )
        access_list = result.scalars().all()

        # Collaborators zusammenstellen (Owner + Shared)
        collaborators = []

        # Owner hinzufuegen
        collaborators.append({
            "user_id": str(session.user_id),
            "username": session.user.username if session.user else "Unbekannt",
            "email": session.user.email if session.user else None,
            "access_level": "owner",
            "is_owner": True,
            "granted_at": str(session.created_at) if session.created_at else None,
        })

        # Shared Users hinzufuegen
        for access in access_list:
            collaborators.append({
                "user_id": str(access.user_id),
                "username": access.user.username if access.user else "Unbekannt",
                "email": access.user.email if access.user else None,
                "access_level": access.access_level,
                "is_owner": False,
                "granted_at": str(access.granted_at) if access.granted_at else None,
            })

        return collaborators

    async def get_shared_sessions(
        self,
        user_id: UUID,
    ) -> List[RAGChatSession]:
        """
        Holt alle Sessions die mit einem User geteilt wurden.

        Args:
            user_id: ID des Benutzers

        Returns:
            Liste von RAGChatSession Objekten
        """
        result = await self.db.execute(
            select(RAGChatSession)
            .join(ChatSessionAccess, ChatSessionAccess.session_id == RAGChatSession.id)
            .where(ChatSessionAccess.user_id == user_id)
            .where(RAGChatSession.status == "active")
            .order_by(RAGChatSession.last_message_at.desc().nullslast())
        )
        return list(result.scalars().all())

    async def check_access(
        self,
        session_id: UUID,
        user_id: UUID,
        required_level: ChatSessionAccessLevel = ChatSessionAccessLevel.VIEW,
    ) -> bool:
        """
        Prueft ob ein User Zugriff auf eine Session hat.

        Args:
            session_id: ID der Chat Session
            user_id: ID des Benutzers
            required_level: Mindest-Zugriffsebene

        Returns:
            True wenn Zugriff vorhanden, sonst False
        """
        # Session laden
        session = await self.db.get(RAGChatSession, session_id)
        if not session:
            return False

        # Owner hat immer vollen Zugriff
        if session.user_id == user_id:
            return True

        # Shared Access pruefen
        access = await self._get_access(session_id, user_id)
        if not access:
            return False

        # Level pruefen
        level_hierarchy = {
            ChatSessionAccessLevel.VIEW.value: 1,
            ChatSessionAccessLevel.CONTRIBUTE.value: 2,
            ChatSessionAccessLevel.MANAGE.value: 3,
        }

        user_level = level_hierarchy.get(access.access_level, 0)
        required = level_hierarchy.get(required_level.value, 0)

        return user_level >= required

    async def get_access_level(
        self,
        session_id: UUID,
        user_id: UUID,
    ) -> Optional[str]:
        """
        Holt das Zugriffslevel eines Users fuer eine Session.

        Args:
            session_id: ID der Chat Session
            user_id: ID des Benutzers

        Returns:
            Zugriffsebene als String oder None wenn kein Zugriff
        """
        # Session laden
        session = await self.db.get(RAGChatSession, session_id)
        if not session:
            return None

        # Owner hat "owner" Level
        if session.user_id == user_id:
            return "owner"

        # Shared Access pruefen
        access = await self._get_access(session_id, user_id)
        if not access:
            return None

        return access.access_level

    async def _get_access(
        self,
        session_id: UUID,
        user_id: UUID,
    ) -> Optional[ChatSessionAccess]:
        """Holt ChatSessionAccess fuer User/Session Kombination."""
        result = await self.db.execute(
            select(ChatSessionAccess).where(
                ChatSessionAccess.session_id == session_id,
                ChatSessionAccess.user_id == user_id,
            )
        )
        return result.scalar_one_or_none()

    async def _can_manage(
        self,
        session: RAGChatSession,
        user_id: UUID,
    ) -> bool:
        """Prueft ob User MANAGE-Berechtigung hat (Owner oder MANAGE-Level)."""
        # Owner kann immer verwalten
        if session.user_id == user_id:
            return True

        # Shared Access pruefen
        access = await self._get_access(session.id, user_id)
        if not access:
            return False

        return access.access_level == ChatSessionAccessLevel.MANAGE.value


# Singleton-Pattern fuer Service-Instanz (wird in Dependency Injection verwendet)
def get_chat_sharing_service(db: AsyncSession) -> ChatSharingService:
    """Factory-Funktion fuer ChatSharingService."""
    return ChatSharingService(db)
