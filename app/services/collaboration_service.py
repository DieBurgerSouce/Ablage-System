"""
Collaboration Service.

Verwaltet Echtzeit-Kollaborationsfunktionen:
- Document Locking (Sperren von Dokumenten zur Bearbeitung)
- @Mentions (Benutzer-Erwähnungen in Kommentaren)
- Activity Feed (Aktivitäts-Log)
- Presence (Wer schaut gerade welches Dokument an)
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Dict, List, Optional, Set

import structlog
from sqlalchemy import and_, desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.datetime_utils import utc_now
from app.core.redis_state import get_redis
from app.core.safe_errors import safe_error_log
from app.db.models import User
from app.services.realtime.event_broadcaster import get_event_broadcaster

logger = structlog.get_logger(__name__)


class LockType(str, Enum):
    """Document Lock Types."""

    EDIT = "edit"
    REVIEW = "review"


class ActivityAction(str, Enum):
    """Activity Actions für Activity Feed."""

    VIEWED = "viewed"
    EDITED = "edited"
    COMMENTED = "commented"
    UPLOADED = "uploaded"
    APPROVED = "approved"
    REJECTED = "rejected"
    LOCKED = "locked"
    UNLOCKED = "unlocked"
    MENTIONED = "mentioned"
    CATEGORIZED = "categorized"
    DOWNLOADED = "downloaded"
    SHARED = "shared"
    UNSHARED = "unshared"
    MOVED = "moved"
    RENAMED = "renamed"


@dataclass
class DocumentLock:
    """Document Lock."""

    document_id: uuid.UUID
    locked_by: uuid.UUID
    locked_by_name: str
    locked_at: datetime
    lock_type: LockType
    expires_at: datetime

    def to_dict(self) -> Dict[str, object]:
        """Konvertiert zu Dictionary."""
        return {
            "document_id": str(self.document_id),
            "locked_by": str(self.locked_by),
            "locked_by_name": self.locked_by_name,
            "locked_at": self.locked_at.isoformat(),
            "lock_type": self.lock_type.value,
            "expires_at": self.expires_at.isoformat(),
        }


@dataclass
class Mention:
    """@Mention."""

    id: uuid.UUID
    document_id: uuid.UUID
    mentioned_user_id: uuid.UUID
    mentioned_by_id: uuid.UUID
    context: str
    read: bool
    created_at: datetime

    def to_dict(self) -> Dict[str, object]:
        """Konvertiert zu Dictionary."""
        return {
            "id": str(self.id),
            "document_id": str(self.document_id),
            "mentioned_user_id": str(self.mentioned_user_id),
            "mentioned_by_id": str(self.mentioned_by_id),
            "context": self.context,
            "read": self.read,
            "created_at": self.created_at.isoformat(),
        }


@dataclass
class ActivityEntry:
    """Activity Feed Entry."""

    id: uuid.UUID
    document_id: Optional[uuid.UUID]
    user_id: uuid.UUID
    user_name: str
    action: ActivityAction
    details: str
    created_at: datetime

    def to_dict(self) -> Dict[str, object]:
        """Konvertiert zu Dictionary."""
        return {
            "id": str(self.id),
            "document_id": str(self.document_id) if self.document_id else None,
            "user_id": str(self.user_id),
            "user_name": self.user_name,
            "action": self.action.value,
            "details": self.details,
            "created_at": self.created_at.isoformat(),
        }


class CollaborationService:
    """
    Collaboration Service.

    Features:
    - Document Locking mit Redis (auto-expire nach 30 Minuten)
    - @Mentions mit Datenbank-Persistierung
    - Activity Feed mit PostgreSQL
    - Presence über RealtimeWebSocketManager
    """

    LOCK_TIMEOUT_SECONDS = 1800  # 30 Minuten
    MENTION_PATTERN = re.compile(r"@[\w.-]+")

    def __init__(self) -> None:
        """Initialisiert den Collaboration Service."""
        self._broadcaster = get_event_broadcaster()

    # =========================================================================
    # DOCUMENT LOCKING
    # =========================================================================

    async def acquire_lock(
        self,
        db: AsyncSession,
        document_id: uuid.UUID,
        user_id: uuid.UUID,
        lock_type: LockType = LockType.EDIT,
    ) -> DocumentLock:
        """
        Sperrt ein Dokument für einen Benutzer.

        Args:
            db: Datenbank-Session
            document_id: Dokument-ID
            user_id: Benutzer-ID
            lock_type: Art der Sperre (EDIT oder REVIEW)

        Returns:
            DocumentLock Objekt

        Raises:
            ValueError: Wenn Dokument bereits gesperrt ist
        """
        redis = await get_redis()

        # Prüfe ob bereits gesperrt
        existing_lock = await self.check_lock(db, document_id)
        if existing_lock:
            if existing_lock.locked_by == user_id:
                # Refresh existing lock
                return await self.refresh_lock(db, document_id, user_id)
            raise ValueError(
                f"Dokument ist bereits von {existing_lock.locked_by_name} gesperrt"
            )

        # Hole Benutzername
        user = await db.get(User, user_id)
        if not user:
            raise ValueError("Benutzer nicht gefunden")

        user_name = f"{user.first_name} {user.last_name}".strip() or user.email

        # Erstelle Lock in Redis
        now = utc_now()
        expires_at = now + timedelta(seconds=self.LOCK_TIMEOUT_SECONDS)

        lock = DocumentLock(
            document_id=document_id,
            locked_by=user_id,
            locked_by_name=user_name,
            locked_at=now,
            lock_type=lock_type,
            expires_at=expires_at,
        )

        lock_key = f"doc_lock:{document_id}"
        import json

        await redis._redis.setex(
            lock_key,
            self.LOCK_TIMEOUT_SECONDS,
            json.dumps(lock.to_dict()),
        )

        logger.info(
            "document_locked",
            document_id=str(document_id),
            user_id=str(user_id),
            lock_type=lock_type.value,
        )

        # Broadcast Event
        await self._broadcaster._broadcast_event(
            event_type=self._broadcaster.RealtimeEventType.SYSTEM_NOTIFICATION,
            payload={
                "notification_type": "document_locked",
                "document_id": str(document_id),
                "locked_by": user_name,
                "lock_type": lock_type.value,
            },
            event_id=f"lock-{document_id}",
            user_id=str(user_id),
            company_id=None,
            priority="normal",
        )

        return lock

    async def release_lock(
        self, db: AsyncSession, document_id: uuid.UUID, user_id: uuid.UUID
    ) -> bool:
        """
        Gibt eine Dokumentsperre frei.

        Args:
            db: Datenbank-Session
            document_id: Dokument-ID
            user_id: Benutzer-ID

        Returns:
            True wenn erfolgreich freigegeben, False wenn keine Sperre existiert

        Raises:
            ValueError: Wenn User nicht der Lock-Owner ist
        """
        redis = await get_redis()

        # Prüfe ob Lock existiert und User berechtigt ist
        existing_lock = await self.check_lock(db, document_id)
        if not existing_lock:
            return False

        if existing_lock.locked_by != user_id:
            raise ValueError("Nur der Lock-Owner kann die Sperre aufheben")

        # Entferne Lock
        lock_key = f"doc_lock:{document_id}"
        await redis._redis.delete(lock_key)

        logger.info(
            "document_unlocked",
            document_id=str(document_id),
            user_id=str(user_id),
        )

        # Broadcast Event
        await self._broadcaster._broadcast_event(
            event_type=self._broadcaster.RealtimeEventType.SYSTEM_NOTIFICATION,
            payload={
                "notification_type": "document_unlocked",
                "document_id": str(document_id),
            },
            event_id=f"unlock-{document_id}",
            user_id=str(user_id),
            company_id=None,
            priority="normal",
        )

        return True

    async def check_lock(
        self, db: AsyncSession, document_id: uuid.UUID
    ) -> Optional[DocumentLock]:
        """
        Prüft ob ein Dokument gesperrt ist.

        Args:
            db: Datenbank-Session
            document_id: Dokument-ID

        Returns:
            DocumentLock oder None wenn nicht gesperrt
        """
        redis = await get_redis()

        lock_key = f"doc_lock:{document_id}"
        lock_data = await redis._redis.get(lock_key)

        if not lock_data:
            return None

        import json

        data = json.loads(lock_data)
        return DocumentLock(
            document_id=uuid.UUID(data["document_id"]),
            locked_by=uuid.UUID(data["locked_by"]),
            locked_by_name=data["locked_by_name"],
            locked_at=datetime.fromisoformat(data["locked_at"]),
            lock_type=LockType(data["lock_type"]),
            expires_at=datetime.fromisoformat(data["expires_at"]),
        )

    async def force_release(
        self, db: AsyncSession, document_id: uuid.UUID, admin_user_id: uuid.UUID
    ) -> bool:
        """
        Erzwingt die Freigabe einer Dokumentsperre (Admin-Override).

        Args:
            db: Datenbank-Session
            document_id: Dokument-ID
            admin_user_id: Admin-Benutzer-ID

        Returns:
            True wenn erfolgreich, False wenn keine Sperre existiert
        """
        redis = await get_redis()

        # Prüfe ob Lock existiert
        existing_lock = await self.check_lock(db, document_id)
        if not existing_lock:
            return False

        # Entferne Lock
        lock_key = f"doc_lock:{document_id}"
        await redis._redis.delete(lock_key)

        logger.warning(
            "document_lock_force_released",
            document_id=str(document_id),
            original_owner=str(existing_lock.locked_by),
            admin_user=str(admin_user_id),
        )

        return True

    async def refresh_lock(
        self, db: AsyncSession, document_id: uuid.UUID, user_id: uuid.UUID
    ) -> DocumentLock:
        """
        Verlängert die Gültigkeit eines Locks.

        Args:
            db: Datenbank-Session
            document_id: Dokument-ID
            user_id: Benutzer-ID

        Returns:
            Aktualisiertes DocumentLock Objekt

        Raises:
            ValueError: Wenn Lock nicht existiert oder User nicht berechtigt
        """
        existing_lock = await self.check_lock(db, document_id)
        if not existing_lock:
            raise ValueError("Keine Sperre vorhanden")

        if existing_lock.locked_by != user_id:
            raise ValueError("Nur der Lock-Owner kann die Sperre verlängern")

        # Erneuere Lock
        redis = await get_redis()
        now = utc_now()
        expires_at = now + timedelta(seconds=self.LOCK_TIMEOUT_SECONDS)

        updated_lock = DocumentLock(
            document_id=document_id,
            locked_by=user_id,
            locked_by_name=existing_lock.locked_by_name,
            locked_at=existing_lock.locked_at,
            lock_type=existing_lock.lock_type,
            expires_at=expires_at,
        )

        lock_key = f"doc_lock:{document_id}"
        import json

        await redis._redis.setex(
            lock_key,
            self.LOCK_TIMEOUT_SECONDS,
            json.dumps(updated_lock.to_dict()),
        )

        logger.debug(
            "document_lock_refreshed",
            document_id=str(document_id),
            user_id=str(user_id),
        )

        return updated_lock

    # =========================================================================
    # @MENTIONS
    # =========================================================================

    async def create_mention(
        self,
        db: AsyncSession,
        document_id: uuid.UUID,
        mentioned_user_id: uuid.UUID,
        mentioned_by_id: uuid.UUID,
        context: str,
        company_id: Optional[uuid.UUID] = None,
    ) -> Mention:
        """
        Erstellt eine @Mention.

        Args:
            db: Datenbank-Session
            document_id: Dokument-ID
            mentioned_user_id: ID des erwähnten Benutzers
            mentioned_by_id: ID des Benutzers der die Erwähnung macht
            context: Kontext-Text (z.B. Kommentar-Inhalt)
            company_id: Optional Company-ID für Multi-Tenant

        Returns:
            Mention Objekt
        """
        from app.db.models_collaboration import DocumentMention

        mention = DocumentMention(
            id=uuid.uuid4(),
            document_id=document_id,
            mentioned_user_id=mentioned_user_id,
            mentioned_by_id=mentioned_by_id,
            context=context[:500],  # Limitiere Kontext-Länge
            read=False,
            created_at=utc_now(),
        )

        db.add(mention)
        await db.commit()
        await db.refresh(mention)

        logger.info(
            "mention_created",
            mention_id=str(mention.id),
            document_id=str(document_id),
            mentioned_user=str(mentioned_user_id),
        )

        # Broadcast Mention Event
        await self._broadcaster.emit_user_mention(
            mentioned_user_id=str(mentioned_user_id),
            mentioner_user_id=str(mentioned_by_id),
            context_type="document",
            context_id=str(document_id),
            content_preview=context[:100],
            company_id=str(company_id) if company_id else None,
        )

        return Mention(
            id=mention.id,
            document_id=mention.document_id,
            mentioned_user_id=mention.mentioned_user_id,
            mentioned_by_id=mention.mentioned_by_id,
            context=mention.context,
            read=mention.read,
            created_at=mention.created_at,
        )

    async def get_unread_mentions(
        self, db: AsyncSession, user_id: uuid.UUID, company_id: uuid.UUID
    ) -> List[Mention]:
        """
        Holt ungelesene @Mentions für einen Benutzer.

        Args:
            db: Datenbank-Session
            user_id: Benutzer-ID
            company_id: Company-ID für Multi-Tenant

        Returns:
            Liste von Mention Objekten
        """
        from app.db.models_collaboration import DocumentMention

        # IMPORTANT: Multi-Tenant Isolation über document.company_id
        # Muss später über JOIN mit documents table validiert werden
        result = await db.execute(
            select(DocumentMention)
            .where(
                and_(
                    DocumentMention.mentioned_user_id == user_id,
                    DocumentMention.read == False,  # noqa: E712
                )
            )
            .order_by(desc(DocumentMention.created_at))
            .limit(50)
        )

        mentions = result.scalars().all()

        return [
            Mention(
                id=m.id,
                document_id=m.document_id,
                mentioned_user_id=m.mentioned_user_id,
                mentioned_by_id=m.mentioned_by_id,
                context=m.context,
                read=m.read,
                created_at=m.created_at,
            )
            for m in mentions
        ]

    async def get_all_mentions(
        self, db: AsyncSession, user_id: uuid.UUID, company_id: uuid.UUID
    ) -> List[Mention]:
        """
        Holt alle @Mentions für einen Benutzer (gelesen und ungelesen).

        Args:
            db: Datenbank-Session
            user_id: Benutzer-ID
            company_id: Company-ID für Multi-Tenant

        Returns:
            Liste von Mention Objekten
        """
        from app.db.models_collaboration import DocumentMention

        result = await db.execute(
            select(DocumentMention)
            .where(DocumentMention.mentioned_user_id == user_id)
            .order_by(desc(DocumentMention.created_at))
            .limit(50)
        )

        mentions = result.scalars().all()

        return [
            Mention(
                id=m.id,
                document_id=m.document_id,
                mentioned_user_id=m.mentioned_user_id,
                mentioned_by_id=m.mentioned_by_id,
                context=m.context,
                read=m.read,
                created_at=m.created_at,
            )
            for m in mentions
        ]

    async def mark_mention_read(
        self, db: AsyncSession, mention_id: uuid.UUID, user_id: uuid.UUID
    ) -> bool:
        """
        Markiert eine @Mention als gelesen.

        Args:
            db: Datenbank-Session
            mention_id: Mention-ID
            user_id: Benutzer-ID (muss Owner sein)

        Returns:
            True wenn erfolgreich, False wenn nicht gefunden
        """
        from app.db.models_collaboration import DocumentMention

        result = await db.execute(
            select(DocumentMention).where(
                and_(
                    DocumentMention.id == mention_id,
                    DocumentMention.mentioned_user_id == user_id,
                )
            )
        )

        mention = result.scalar_one_or_none()
        if not mention:
            return False

        mention.read = True
        await db.commit()

        logger.debug("mention_marked_read", mention_id=str(mention_id))

        return True

    def parse_mentions(self, text: str) -> List[str]:
        """
        Parst @Mentions aus Text.

        Args:
            text: Text der durchsucht werden soll

        Returns:
            Liste von Username-Strings (ohne @)
        """
        matches = self.MENTION_PATTERN.findall(text)
        return [match[1:] for match in matches]  # Entferne @ Prefix

    # =========================================================================
    # ACTIVITY FEED
    # =========================================================================

    async def record_activity(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        action: ActivityAction,
        details: str,
        document_id: Optional[uuid.UUID] = None,
    ) -> ActivityEntry:
        """
        Erstellt einen Activity Feed Eintrag.

        Args:
            db: Datenbank-Session
            user_id: Benutzer-ID
            action: Activity Action
            details: Deutsche Beschreibung
            document_id: Optional Dokument-ID

        Returns:
            ActivityEntry Objekt
        """
        from app.db.models_collaboration import DocumentActivity

        # Hole Benutzername
        user = await db.get(User, user_id)
        if not user:
            raise ValueError("Benutzer nicht gefunden")

        user_name = f"{user.first_name} {user.last_name}".strip() or user.email

        activity = DocumentActivity(
            id=uuid.uuid4(),
            document_id=document_id,
            user_id=user_id,
            action=action.value,
            details=details,
            created_at=utc_now(),
        )

        db.add(activity)
        await db.commit()
        await db.refresh(activity)

        logger.debug(
            "activity_recorded",
            activity_id=str(activity.id),
            action=action.value,
            user_id=str(user_id),
        )

        return ActivityEntry(
            id=activity.id,
            document_id=activity.document_id,
            user_id=activity.user_id,
            user_name=user_name,
            action=ActivityAction(activity.action),
            details=activity.details,
            created_at=activity.created_at,
        )

    async def get_document_activity(
        self, db: AsyncSession, document_id: uuid.UUID, limit: int = 50
    ) -> List[ActivityEntry]:
        """
        Holt Activity Feed für ein Dokument.

        Args:
            db: Datenbank-Session
            document_id: Dokument-ID
            limit: Maximale Anzahl Einträge

        Returns:
            Liste von ActivityEntry Objekten
        """
        from app.db.models_collaboration import DocumentActivity

        result = await db.execute(
            select(DocumentActivity)
            .where(DocumentActivity.document_id == document_id)
            .order_by(desc(DocumentActivity.created_at))
            .limit(limit)
        )

        activities = result.scalars().all()

        # Hole Benutzernamen in Batch
        user_ids = [a.user_id for a in activities]
        users_result = await db.execute(select(User).where(User.id.in_(user_ids)))
        users = {u.id: u for u in users_result.scalars().all()}

        entries: List[ActivityEntry] = []
        for activity in activities:
            user = users.get(activity.user_id)
            user_name = (
                f"{user.first_name} {user.last_name}".strip() or user.email
                if user
                else "Unbekannter Benutzer"
            )

            entries.append(
                ActivityEntry(
                    id=activity.id,
                    document_id=activity.document_id,
                    user_id=activity.user_id,
                    user_name=user_name,
                    action=ActivityAction(activity.action),
                    details=activity.details,
                    created_at=activity.created_at,
                )
            )

        return entries

    async def get_user_activity_feed(
        self, db: AsyncSession, user_id: uuid.UUID, company_id: uuid.UUID, limit: int = 50
    ) -> List[ActivityEntry]:
        """
        Holt Activity Feed für einen Benutzer (eigene Aktivitäten).

        Args:
            db: Datenbank-Session
            user_id: Benutzer-ID
            company_id: Company-ID für Multi-Tenant
            limit: Maximale Anzahl Einträge

        Returns:
            Liste von ActivityEntry Objekten
        """
        from app.db.models_collaboration import DocumentActivity

        # IMPORTANT: Multi-Tenant Isolation über document.company_id
        # Muss später über JOIN mit documents table validiert werden
        result = await db.execute(
            select(DocumentActivity)
            .where(DocumentActivity.user_id == user_id)
            .order_by(desc(DocumentActivity.created_at))
            .limit(limit)
        )

        activities = result.scalars().all()

        # Hole Benutzername
        user = await db.get(User, user_id)
        user_name = (
            f"{user.first_name} {user.last_name}".strip() or user.email if user else "Unbekannt"
        )

        return [
            ActivityEntry(
                id=a.id,
                document_id=a.document_id,
                user_id=a.user_id,
                user_name=user_name,
                action=ActivityAction(a.action),
                details=a.details,
                created_at=a.created_at,
            )
            for a in activities
        ]

    async def get_company_activity_feed(
        self,
        db: AsyncSession,
        company_id: uuid.UUID,
        limit: int = 50,
        since: Optional[datetime] = None,
    ) -> List[ActivityEntry]:
        """
        Holt Company-weiten Activity Feed.

        Args:
            db: Datenbank-Session
            company_id: Company-ID
            limit: Maximale Anzahl Einträge
            since: Optional Filter nach Zeitpunkt

        Returns:
            Liste von ActivityEntry Objekten
        """
        from app.db.models_collaboration import DocumentActivity

        # IMPORTANT: Multi-Tenant Isolation über document.company_id
        # Muss später über JOIN mit documents table validiert werden
        query = select(DocumentActivity).order_by(desc(DocumentActivity.created_at)).limit(limit)

        if since:
            query = query.where(DocumentActivity.created_at > since)

        result = await db.execute(query)
        activities = result.scalars().all()

        # Hole Benutzernamen in Batch
        user_ids = list({a.user_id for a in activities})
        users_result = await db.execute(select(User).where(User.id.in_(user_ids)))
        users = {u.id: u for u in users_result.scalars().all()}

        entries: List[ActivityEntry] = []
        for activity in activities:
            user = users.get(activity.user_id)
            user_name = (
                f"{user.first_name} {user.last_name}".strip() or user.email
                if user
                else "Unbekannter Benutzer"
            )

            entries.append(
                ActivityEntry(
                    id=activity.id,
                    document_id=activity.document_id,
                    user_id=activity.user_id,
                    user_name=user_name,
                    action=ActivityAction(activity.action),
                    details=activity.details,
                    created_at=activity.created_at,
                )
            )

        return entries

    # =========================================================================
    # PRESENCE
    # =========================================================================

    async def get_document_viewers(self, document_id: uuid.UUID) -> List[Dict[str, str]]:
        """
        Gibt alle Benutzer zurück die ein Dokument gerade betrachten.

        Nutzt RealtimeWebSocketManager für Presence-Tracking.

        Args:
            document_id: Dokument-ID

        Returns:
            Liste von Viewer-Informationen
        """
        from app.services.realtime.realtime_websocket_manager import (
            get_realtime_ws_manager,
        )

        ws_manager = get_realtime_ws_manager()
        return await ws_manager.get_document_viewers(str(document_id))


# Singleton Instance
_collaboration_service: Optional[CollaborationService] = None


def get_collaboration_service() -> CollaborationService:
    """Factory-Funktion für CollaborationService Singleton."""
    global _collaboration_service
    if _collaboration_service is None:
        _collaboration_service = CollaborationService()
    return _collaboration_service
