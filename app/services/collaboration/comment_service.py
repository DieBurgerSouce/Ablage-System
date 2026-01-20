# -*- coding: utf-8 -*-
"""
Comment Service for Ablage-System.

Enterprise-grade Kommentar-Verwaltung fuer Dokumente:
- CRUD-Operationen fuer DocumentComment
- Thread/Reply Management
- @Mention Parsing und Notification
- Feld-Kommentare (Inline auf Extraktionsfeldern)
- Reaktionen
- Statistiken

Multi-Tenant:
- Alle Operationen sind company_id-isoliert (RLS-Prinzip)

Security:
- User-Validierung bei Mentions
- PII wird nicht geloggt (keine Content-Details)

Feinpoliert und durchdacht - Collaboration auf Enterprise-Niveau.
"""

import re
import structlog
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.datetime_utils import utc_now
from app.services.realtime.event_broadcaster import get_event_broadcaster
from app.db.models import (
    Document,
    DocumentActivity,
    DocumentComment,
    ActivityType,
    User,
    UserCompany,
    UserNotification,
    NotificationType as DBNotificationType,
)
from app.db.schemas import MentionSchema

logger = structlog.get_logger(__name__)

# Pattern fuer @mention Erkennung: @username oder @vorname.nachname
MENTION_PATTERN = re.compile(r'@([\w]+(?:\.[\w]+)?)', re.UNICODE)


class CommentService:
    """Service fuer Dokument-Kommentar-Verwaltung.

    Alle Methoden erwarten company_id fuer Multi-Tenant Isolation.
    """

    def __init__(self, db: AsyncSession):
        """Initialisiert den CommentService.

        Args:
            db: AsyncSession fuer Datenbankoperationen
        """
        self.db = db

    # =========================================================================
    # CRUD Operations
    # =========================================================================

    async def create_comment(
        self,
        document_id: UUID,
        user_id: UUID,
        company_id: UUID,
        content: str,
        parent_id: Optional[UUID] = None,
        field_reference: Optional[str] = None,
        mentions: Optional[List[Dict[str, Any]]] = None,
        auto_parse_mentions: bool = True,
        notify_mentions: bool = True,
    ) -> DocumentComment:
        """Erstellt einen neuen Kommentar zu einem Dokument.

        Args:
            document_id: ID des Dokuments
            user_id: ID des erstellenden Users
            company_id: ID der Firma
            content: Kommentarinhalt
            parent_id: ID des Parent-Kommentars (fuer Replies)
            field_reference: Feldname fuer Inline-Kommentare
            mentions: Liste von Mentions [{"userId": ..., "userName": ..., ...}]
            auto_parse_mentions: Bei True werden @mentions aus content geparst
            notify_mentions: Bei True werden Notifications gesendet

        Returns:
            Erstellter DocumentComment

        Raises:
            ValueError: Bei ungueltigem Dokument, Parent oder User
        """
        # Validiere Dokument existiert und gehoert zur Firma
        doc_result = await self.db.execute(
            select(Document).where(
                and_(
                    Document.id == document_id,
                    Document.company_id == company_id,
                )
            )
        )
        document = doc_result.scalar_one_or_none()
        if not document:
            raise ValueError("Dokument nicht gefunden oder gehoert nicht zur Firma")

        # Validiere User existiert
        user_result = await self.db.execute(
            select(User).where(User.id == user_id)
        )
        user = user_result.scalar_one_or_none()
        if not user:
            raise ValueError("Benutzer nicht gefunden")

        # Validiere Parent-Kommentar falls angegeben
        if parent_id:
            parent_result = await self.db.execute(
                select(DocumentComment).where(
                    and_(
                        DocumentComment.id == parent_id,
                        DocumentComment.document_id == document_id,
                        DocumentComment.company_id == company_id,
                        DocumentComment.deleted_at.is_(None),
                    )
                )
            )
            parent = parent_result.scalar_one_or_none()
            if not parent:
                raise ValueError("Parent-Kommentar nicht gefunden")

        # Mentions verarbeiten
        final_mentions = mentions or []

        if auto_parse_mentions and not mentions:
            # @mentions aus Text parsen
            parsed_mentions = await self.parse_mentions_from_text(content, company_id)
            final_mentions = [
                {
                    "userId": str(m.userId),
                    "userName": m.userName,
                    "startIndex": m.startIndex,
                    "endIndex": m.endIndex,
                }
                for m in parsed_mentions
            ]

        # Kommentar erstellen
        comment = DocumentComment(
            document_id=document_id,
            user_id=user_id,
            company_id=company_id,
            parent_id=parent_id,
            field_reference=field_reference,
            content=content,
            mentions=final_mentions,
            reactions=[],
            is_edited=False,
            is_deleted=False,
        )

        self.db.add(comment)
        await self.db.flush()

        # Activity-Log erstellen
        activity_type = (
            ActivityType.COMMENT_REPLIED.value
            if parent_id
            else ActivityType.COMMENT_ADDED.value
        )
        await self._create_activity(
            document_id=document_id,
            user_id=user_id,
            activity_type=activity_type,
            description="Kommentar hinzugefuegt" if not parent_id else "Antwort hinzugefuegt",
            metadata={"comment_id": str(comment.id)},
        )

        # Mention-Benachrichtigungen senden
        if notify_mentions and final_mentions:
            await self._send_mention_notifications(
                comment=comment,
                document=document,
                from_user=user,
                mentions=final_mentions,
            )

        # Reply-Benachrichtigung an Parent-Autor
        if parent_id:
            await self._send_reply_notification(
                comment=comment,
                document_id=document_id,
                from_user=user,
                parent_id=parent_id,
            )

        await self.db.commit()
        await self.db.refresh(comment)

        logger.info(
            "comment_created",
            comment_id=str(comment.id),
            document_id=str(document_id),
            is_reply=bool(parent_id),
            has_field_reference=bool(field_reference),
            mention_count=len(final_mentions),
        )

        # WebSocket Real-Time Broadcast
        try:
            broadcaster = get_event_broadcaster()
            mentioned_user_ids = [m.get("userId") for m in final_mentions if m.get("userId")]

            if parent_id:
                # Thread-Antwort: Hole alle Teilnehmer des Threads
                thread_participants = await self._get_thread_participants(parent_id, company_id)
                await broadcaster.emit_comment_replied(
                    comment_id=str(comment.id),
                    parent_id=str(parent_id),
                    document_id=str(document_id),
                    user_id=str(user_id),
                    content_preview=content[:100] if content else "",
                    thread_participants=thread_participants,
                    company_id=str(company_id),
                )
            else:
                await broadcaster.emit_comment_created(
                    comment_id=str(comment.id),
                    document_id=str(document_id),
                    user_id=str(user_id),
                    content_preview=content[:100] if content else "",
                    parent_id=None,
                    mentioned_users=mentioned_user_ids,
                    company_id=str(company_id),
                )

            # Emit mention events for each mentioned user
            for mention in final_mentions:
                mentioned_user_id = mention.get("userId")
                if mentioned_user_id and mentioned_user_id != str(user_id):
                    await broadcaster.emit_user_mention(
                        mentioned_user_id=mentioned_user_id,
                        mentioner_user_id=str(user_id),
                        context_type="comment",
                        context_id=str(comment.id),
                        content_preview=content[:100] if content else "",
                        company_id=str(company_id),
                    )
        except Exception as e:
            # WebSocket-Fehler sollen nicht den Kommentar-Flow blockieren
            logger.warning("websocket_broadcast_failed", error=str(e), comment_id=str(comment.id))

        return comment

    async def get_comment(
        self,
        comment_id: UUID,
        company_id: UUID,
        include_deleted: bool = False,
    ) -> Optional[DocumentComment]:
        """Holt einen Kommentar anhand seiner ID.

        Args:
            comment_id: ID des Kommentars
            company_id: ID der Firma
            include_deleted: Bei True auch geloeschte Kommentare

        Returns:
            DocumentComment oder None
        """
        query = (
            select(DocumentComment)
            .options(
                selectinload(DocumentComment.user),
                selectinload(DocumentComment.document),
                selectinload(DocumentComment.parent),
            )
            .where(
                and_(
                    DocumentComment.id == comment_id,
                    DocumentComment.company_id == company_id,
                )
            )
        )

        if not include_deleted:
            query = query.where(DocumentComment.deleted_at.is_(None))

        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def update_comment(
        self,
        comment_id: UUID,
        company_id: UUID,
        user_id: UUID,
        content: str,
        mentions: Optional[List[Dict[str, Any]]] = None,
        auto_parse_mentions: bool = True,
    ) -> Optional[DocumentComment]:
        """Aktualisiert einen Kommentar.

        Args:
            comment_id: ID des Kommentars
            company_id: ID der Firma
            user_id: ID des aktualisierenden Users (muss Autor sein)
            content: Neuer Inhalt
            mentions: Neue Mentions
            auto_parse_mentions: Bei True werden @mentions geparst

        Returns:
            Aktualisierter DocumentComment oder None

        Raises:
            ValueError: Wenn User nicht Autor ist oder Kommentar geloescht
        """
        comment = await self.get_comment(comment_id, company_id)
        if not comment:
            return None

        # Nur der Autor kann bearbeiten
        if comment.user_id != user_id:
            raise ValueError("Nur der Autor kann den Kommentar bearbeiten")

        # Geloeschte Kommentare koennen nicht bearbeitet werden
        if comment.deleted_at:
            raise ValueError("Geloeschter Kommentar kann nicht bearbeitet werden")

        # Mentions verarbeiten
        final_mentions = mentions
        if auto_parse_mentions and mentions is None:
            parsed_mentions = await self.parse_mentions_from_text(content, company_id)
            final_mentions = [
                {
                    "userId": str(m.userId),
                    "userName": m.userName,
                    "startIndex": m.startIndex,
                    "endIndex": m.endIndex,
                }
                for m in parsed_mentions
            ]

        comment.content = content
        comment.is_edited = True
        comment.updated_at = utc_now()
        if final_mentions is not None:
            comment.mentions = final_mentions

        await self.db.commit()
        await self.db.refresh(comment)

        logger.info(
            "comment_updated",
            comment_id=str(comment_id),
            user_id=str(user_id),
        )

        # WebSocket Real-Time Broadcast
        try:
            broadcaster = get_event_broadcaster()
            await broadcaster.emit_comment_updated(
                comment_id=str(comment_id),
                document_id=str(comment.document_id),
                user_id=str(user_id),
                company_id=str(company_id),
            )
        except Exception as e:
            logger.warning("websocket_broadcast_failed", error=str(e), comment_id=str(comment_id))

        return comment

    async def delete_comment(
        self,
        comment_id: UUID,
        company_id: UUID,
        user_id: UUID,
        hard_delete: bool = False,
    ) -> bool:
        """Loescht einen Kommentar (Soft Delete).

        Args:
            comment_id: ID des Kommentars
            company_id: ID der Firma
            user_id: ID des loeschenden Users
            hard_delete: Bei True wird physisch geloescht (nur Admin)

        Returns:
            True bei Erfolg

        Raises:
            ValueError: Wenn User keine Berechtigung hat
        """
        comment = await self.get_comment(comment_id, company_id, include_deleted=True)
        if not comment:
            return False

        # Autor oder Document-Owner koennen loeschen
        doc_result = await self.db.execute(
            select(Document.owner_id).where(Document.id == comment.document_id)
        )
        doc_owner_id = doc_result.scalar()

        if comment.user_id != user_id and doc_owner_id != user_id:
            raise ValueError("Keine Berechtigung zum Loeschen")

        # Speichere document_id vor möglichem Delete
        document_id = comment.document_id

        if hard_delete:
            await self.db.delete(comment)
        else:
            comment.is_deleted = True  # Legacy-Flag
            comment.deleted_at = utc_now()
            comment.deleted_by_id = user_id

        await self.db.commit()

        logger.info(
            "comment_deleted",
            comment_id=str(comment_id),
            deleted_by=str(user_id),
            hard_delete=hard_delete,
        )

        # WebSocket Real-Time Broadcast
        try:
            broadcaster = get_event_broadcaster()
            await broadcaster.emit_comment_deleted(
                comment_id=str(comment_id),
                document_id=str(document_id),
                user_id=str(user_id),
                company_id=str(company_id),
            )
        except Exception as e:
            logger.warning("websocket_broadcast_failed", error=str(e), comment_id=str(comment_id))

        return True

    # =========================================================================
    # Thread/Reply Operations
    # =========================================================================

    async def get_comment_thread(
        self,
        comment_id: UUID,
        company_id: UUID,
    ) -> List[DocumentComment]:
        """Holt alle Antworten zu einem Kommentar.

        Args:
            comment_id: ID des Root-Kommentars
            company_id: ID der Firma

        Returns:
            Liste der Antworten (chronologisch sortiert)
        """
        result = await self.db.execute(
            select(DocumentComment)
            .options(selectinload(DocumentComment.user))
            .where(
                and_(
                    DocumentComment.parent_id == comment_id,
                    DocumentComment.company_id == company_id,
                    DocumentComment.deleted_at.is_(None),
                )
            )
            .order_by(DocumentComment.created_at.asc())
        )
        return list(result.scalars().all())

    async def create_reply(
        self,
        parent_id: UUID,
        user_id: UUID,
        company_id: UUID,
        content: str,
        mentions: Optional[List[Dict[str, Any]]] = None,
    ) -> DocumentComment:
        """Erstellt eine Antwort auf einen Kommentar.

        Args:
            parent_id: ID des Parent-Kommentars
            user_id: ID des Users
            company_id: ID der Firma
            content: Antwortinhalt
            mentions: Optional Mentions

        Returns:
            Erstellter DocumentComment

        Raises:
            ValueError: Wenn Parent nicht existiert
        """
        parent = await self.get_comment(parent_id, company_id)
        if not parent:
            raise ValueError("Parent-Kommentar nicht gefunden")

        return await self.create_comment(
            document_id=parent.document_id,
            user_id=user_id,
            company_id=company_id,
            content=content,
            parent_id=parent_id,
            mentions=mentions,
        )

    # =========================================================================
    # @Mention Operations
    # =========================================================================

    async def parse_mentions_from_text(
        self,
        content: str,
        company_id: UUID,
    ) -> List[MentionSchema]:
        """Parst @mentions aus Kommentartext.

        Erkennt Pattern wie @username oder @vorname.nachname

        Args:
            content: Kommentarinhalt
            company_id: ID der Firma (fuer User-Lookup)

        Returns:
            Liste von MentionSchema mit erkannten Usern
        """
        mentions: List[MentionSchema] = []

        for match in MENTION_PATTERN.finditer(content):
            username = match.group(1)
            user = await self._find_user_by_username(username, company_id)

            if user:
                mentions.append(MentionSchema(
                    userId=user.id,
                    userName=user.full_name or user.username or user.email,
                    startIndex=match.start(),
                    endIndex=match.end(),
                ))

        return mentions

    async def _find_user_by_username(
        self,
        username: str,
        company_id: UUID,
    ) -> Optional[User]:
        """Findet einen User anhand des Usernames innerhalb der Company.

        SECURITY: Multi-Tenant Isolation - nur User der gleichen Company!
        Sucht ueber UserCompany Join, um sicherzustellen, dass der User
        auch Zugriff auf die Company hat.

        Sucht nach:
        1. Exakter Username-Match (innerhalb der Company)
        2. full_name als "vorname.nachname" (case-insensitive, innerhalb der Company)

        Args:
            username: Der gesuchte Username
            company_id: ID der Firma (MUSS verwendet werden fuer Multi-Tenant!)

        Returns:
            User oder None
        """
        # SECURITY: Exakter Username-Match NUR innerhalb der Company
        result = await self.db.execute(
            select(User)
            .join(UserCompany, UserCompany.user_id == User.id)
            .where(
                and_(
                    func.lower(User.username) == func.lower(username),
                    User.is_active == True,
                    UserCompany.company_id == company_id,
                )
            )
        )
        user = result.scalar_one_or_none()
        if user:
            return user

        # full_name als "vorname.nachname" suchen (innerhalb der Company)
        # z.B. @max.mustermann -> sucht "Max Mustermann"
        name_parts = username.split(".")
        if len(name_parts) == 2:
            first_name, last_name = name_parts
            # SECURITY: Case-insensitive Suche NUR innerhalb der Company
            result = await self.db.execute(
                select(User)
                .join(UserCompany, UserCompany.user_id == User.id)
                .where(
                    and_(
                        func.lower(User.full_name).contains(func.lower(first_name)),
                        func.lower(User.full_name).contains(func.lower(last_name)),
                        User.is_active == True,
                        UserCompany.company_id == company_id,
                    )
                )
            )
            user = result.scalar_one_or_none()
            if user:
                return user

        return None

    async def _send_mention_notifications(
        self,
        comment: DocumentComment,
        document: Document,
        from_user: User,
        mentions: List[Dict[str, Any]],
    ) -> None:
        """Erstellt Benachrichtigungen fuer Mentions.

        Args:
            comment: Der Kommentar
            document: Das Dokument
            from_user: Der Absender
            mentions: Liste der Mentions
        """
        for mention in mentions:
            try:
                mentioned_user_id = UUID(mention.get("userId", ""))

                # Nicht sich selbst benachrichtigen
                if mentioned_user_id == from_user.id:
                    continue

                # Pruefe ob User existiert
                user_result = await self.db.execute(
                    select(User.id).where(
                        and_(
                            User.id == mentioned_user_id,
                            User.is_active == True,
                        )
                    )
                )
                if not user_result.scalar():
                    continue

                notification = UserNotification(
                    user_id=mentioned_user_id,
                    from_user_id=from_user.id,
                    document_id=document.id,
                    notification_type=DBNotificationType.MENTION.value,
                    title="Erwaehnung in Kommentar",
                    message=f"{from_user.full_name or from_user.username} hat Sie in einem Kommentar erwaehnt",
                    action_url=f"/documents/{document.id}?comment={comment.id}",
                )
                self.db.add(notification)

            except (ValueError, TypeError) as e:
                logger.warning(
                    "mention_notification_failed",
                    comment_id=str(comment.id),
                    error=str(e),
                )
                continue

    async def _send_reply_notification(
        self,
        comment: DocumentComment,
        document_id: UUID,
        from_user: User,
        parent_id: UUID,
    ) -> None:
        """Sendet Benachrichtigung an den Parent-Autor.

        Args:
            comment: Der neue Kommentar
            document_id: ID des Dokuments
            from_user: Der Absender
            parent_id: ID des Parent-Kommentars
        """
        parent_result = await self.db.execute(
            select(DocumentComment.user_id).where(DocumentComment.id == parent_id)
        )
        parent_user_id = parent_result.scalar()

        if parent_user_id and parent_user_id != from_user.id:
            notification = UserNotification(
                user_id=parent_user_id,
                from_user_id=from_user.id,
                document_id=document_id,
                notification_type=DBNotificationType.COMMENT_REPLY.value,
                title="Antwort auf Ihren Kommentar",
                message=f"{from_user.full_name or from_user.username} hat auf Ihren Kommentar geantwortet",
                action_url=f"/documents/{document_id}?comment={comment.id}",
            )
            self.db.add(notification)

    # =========================================================================
    # Query Operations
    # =========================================================================

    async def list_comments(
        self,
        document_id: UUID,
        company_id: UUID,
        limit: int = 50,
        offset: int = 0,
        include_deleted: bool = False,
        parent_id: Optional[UUID] = None,
    ) -> Tuple[List[DocumentComment], int]:
        """Listet Kommentare eines Dokuments.

        Args:
            document_id: ID des Dokuments
            company_id: ID der Firma
            limit: Max Anzahl
            offset: Offset
            include_deleted: Bei True auch geloeschte
            parent_id: Filtert auf Replies eines Parent-Kommentars

        Returns:
            Tuple (Kommentare, Gesamtanzahl)
        """
        base_filter = and_(
            DocumentComment.document_id == document_id,
            DocumentComment.company_id == company_id,
        )

        if not include_deleted:
            base_filter = and_(base_filter, DocumentComment.deleted_at.is_(None))

        if parent_id is not None:
            base_filter = and_(base_filter, DocumentComment.parent_id == parent_id)
        else:
            # Nur Top-Level Kommentare
            base_filter = and_(base_filter, DocumentComment.parent_id.is_(None))

        # Count
        count_result = await self.db.execute(
            select(func.count(DocumentComment.id)).where(base_filter)
        )
        total = count_result.scalar() or 0

        # Query
        result = await self.db.execute(
            select(DocumentComment)
            .options(selectinload(DocumentComment.user))
            .where(base_filter)
            .order_by(DocumentComment.created_at.asc())
            .limit(limit)
            .offset(offset)
        )

        return list(result.scalars().all()), total

    async def get_field_comments(
        self,
        document_id: UUID,
        company_id: UUID,
        field_name: str,
    ) -> List[DocumentComment]:
        """Holt alle Kommentare zu einem bestimmten Feld.

        Args:
            document_id: ID des Dokuments
            company_id: ID der Firma
            field_name: Name des Feldes (z.B. "invoice_number")

        Returns:
            Liste der Feld-Kommentare
        """
        result = await self.db.execute(
            select(DocumentComment)
            .options(selectinload(DocumentComment.user))
            .where(
                and_(
                    DocumentComment.document_id == document_id,
                    DocumentComment.company_id == company_id,
                    DocumentComment.field_reference == field_name,
                    DocumentComment.deleted_at.is_(None),
                )
            )
            .order_by(DocumentComment.created_at.asc())
        )
        return list(result.scalars().all())

    # =========================================================================
    # Statistics
    # =========================================================================

    async def get_comment_statistics(
        self,
        document_id: UUID,
        company_id: UUID,
    ) -> Dict[str, Any]:
        """Berechnet Statistiken fuer die Kommentare eines Dokuments.

        Args:
            document_id: ID des Dokuments
            company_id: ID der Firma

        Returns:
            Dict mit Statistiken
        """
        base_filter = and_(
            DocumentComment.document_id == document_id,
            DocumentComment.company_id == company_id,
            DocumentComment.deleted_at.is_(None),
        )

        # Total Kommentare
        total_result = await self.db.execute(
            select(func.count(DocumentComment.id)).where(base_filter)
        )
        total_comments = total_result.scalar() or 0

        # Antworten (mit parent_id)
        replies_result = await self.db.execute(
            select(func.count(DocumentComment.id)).where(
                and_(base_filter, DocumentComment.parent_id.isnot(None))
            )
        )
        total_replies = replies_result.scalar() or 0

        # Unique Commenters
        commenters_result = await self.db.execute(
            select(func.count(func.distinct(DocumentComment.user_id))).where(base_filter)
        )
        unique_commenters = commenters_result.scalar() or 0

        # Mentions zaehlen
        all_comments_result = await self.db.execute(
            select(DocumentComment.mentions).where(base_filter)
        )
        total_mentions = 0
        for (mentions,) in all_comments_result:
            if mentions:
                total_mentions += len(mentions)

        # Kommentare letzte 7 Tage
        seven_days_ago = utc_now() - timedelta(days=7)
        recent_7_result = await self.db.execute(
            select(func.count(DocumentComment.id)).where(
                and_(base_filter, DocumentComment.created_at >= seven_days_ago)
            )
        )
        comments_last_7_days = recent_7_result.scalar() or 0

        # Kommentare letzte 30 Tage
        thirty_days_ago = utc_now() - timedelta(days=30)
        recent_30_result = await self.db.execute(
            select(func.count(DocumentComment.id)).where(
                and_(base_filter, DocumentComment.created_at >= thirty_days_ago)
            )
        )
        comments_last_30_days = recent_30_result.scalar() or 0

        # Feld-Kommentare
        field_comments_result = await self.db.execute(
            select(func.count(DocumentComment.id)).where(
                and_(base_filter, DocumentComment.field_reference.isnot(None))
            )
        )
        field_comments = field_comments_result.scalar() or 0

        return {
            "totalComments": total_comments,
            "totalReplies": total_replies,
            "uniqueCommenters": unique_commenters,
            "totalMentions": total_mentions,
            "commentsLast7Days": comments_last_7_days,
            "commentsLast30Days": comments_last_30_days,
            "fieldComments": field_comments,
        }

    # =========================================================================
    # Reactions
    # =========================================================================

    async def add_reaction(
        self,
        comment_id: UUID,
        user_id: UUID,
        company_id: UUID,
        emoji: str,
    ) -> DocumentComment:
        """Fuegt eine Reaktion zu einem Kommentar hinzu.

        Args:
            comment_id: ID des Kommentars
            user_id: ID des reagierenden Users
            company_id: ID der Firma
            emoji: Unicode Emoji

        Returns:
            Aktualisierter DocumentComment

        Raises:
            ValueError: Wenn Kommentar nicht gefunden
        """
        comment = await self.get_comment(comment_id, company_id)
        if not comment:
            raise ValueError("Kommentar nicht gefunden")

        # Reactions aktualisieren
        reactions = list(comment.reactions or [])
        user_id_str = str(user_id)

        # Pruefe ob Emoji schon existiert
        existing_reaction = None
        for r in reactions:
            if r.get("emoji") == emoji:
                existing_reaction = r
                break

        if existing_reaction:
            # User zu bestehender Reaktion hinzufuegen (falls noch nicht dabei)
            if user_id_str not in existing_reaction.get("userIds", []):
                existing_reaction["userIds"].append(user_id_str)
                existing_reaction["count"] = len(existing_reaction["userIds"])
        else:
            # Neue Reaktion
            reactions.append({
                "emoji": emoji,
                "count": 1,
                "userIds": [user_id_str],
            })

        comment.reactions = reactions
        comment.updated_at = utc_now()

        await self.db.commit()
        await self.db.refresh(comment)

        # WebSocket Real-Time Broadcast
        try:
            broadcaster = get_event_broadcaster()
            await broadcaster.emit_comment_reaction(
                comment_id=str(comment_id),
                document_id=str(comment.document_id),
                user_id=str(user_id),
                reaction=emoji,
                action="added",
                company_id=str(company_id),
            )
        except Exception as e:
            logger.warning("websocket_broadcast_failed", error=str(e), comment_id=str(comment_id))

        return comment

    async def remove_reaction(
        self,
        comment_id: UUID,
        user_id: UUID,
        company_id: UUID,
        emoji: str,
    ) -> DocumentComment:
        """Entfernt eine Reaktion von einem Kommentar.

        Args:
            comment_id: ID des Kommentars
            user_id: ID des Users
            company_id: ID der Firma
            emoji: Unicode Emoji

        Returns:
            Aktualisierter DocumentComment

        Raises:
            ValueError: Wenn Kommentar nicht gefunden
        """
        comment = await self.get_comment(comment_id, company_id)
        if not comment:
            raise ValueError("Kommentar nicht gefunden")

        reactions = list(comment.reactions or [])
        user_id_str = str(user_id)

        # Suche Reaktion
        for i, r in enumerate(reactions):
            if r.get("emoji") == emoji:
                if user_id_str in r.get("userIds", []):
                    r["userIds"].remove(user_id_str)
                    r["count"] = len(r["userIds"])

                    # Reaktion entfernen wenn keine User mehr
                    if r["count"] == 0:
                        reactions.pop(i)
                break

        comment.reactions = reactions
        comment.updated_at = utc_now()

        await self.db.commit()
        await self.db.refresh(comment)

        # WebSocket Real-Time Broadcast
        try:
            broadcaster = get_event_broadcaster()
            await broadcaster.emit_comment_reaction(
                comment_id=str(comment_id),
                document_id=str(comment.document_id),
                user_id=str(user_id),
                reaction=emoji,
                action="removed",
                company_id=str(company_id),
            )
        except Exception as e:
            logger.warning("websocket_broadcast_failed", error=str(e), comment_id=str(comment_id))

        return comment

    # =========================================================================
    # Helper Methods
    # =========================================================================

    async def _get_thread_participants(
        self,
        parent_id: UUID,
        company_id: UUID,
    ) -> List[str]:
        """Holt alle User-IDs die an einem Thread teilnehmen.

        Args:
            parent_id: ID des Parent-Kommentars
            company_id: ID der Firma

        Returns:
            Liste von User-IDs als Strings
        """
        # Hole Parent-Autor
        parent_result = await self.db.execute(
            select(DocumentComment.user_id).where(
                and_(
                    DocumentComment.id == parent_id,
                    DocumentComment.company_id == company_id,
                )
            )
        )
        parent_user_id = parent_result.scalar()

        # Hole alle Reply-Autoren
        replies_result = await self.db.execute(
            select(func.distinct(DocumentComment.user_id)).where(
                and_(
                    DocumentComment.parent_id == parent_id,
                    DocumentComment.company_id == company_id,
                    DocumentComment.deleted_at.is_(None),
                )
            )
        )
        reply_user_ids = [str(uid) for uid in replies_result.scalars().all()]

        # Kombiniere und dedupliziere
        participants = set(reply_user_ids)
        if parent_user_id:
            participants.add(str(parent_user_id))

        return list(participants)

    async def _create_activity(
        self,
        document_id: UUID,
        user_id: UUID,
        activity_type: str,
        description: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Erstellt einen Activity-Log Eintrag.

        Args:
            document_id: ID des Dokuments
            user_id: ID des Users
            activity_type: Art der Aktivitaet
            description: Beschreibung
            metadata: Zusaetzliche Metadaten
        """
        activity = DocumentActivity(
            document_id=document_id,
            user_id=user_id,
            activity_type=activity_type,
            description=description,
            metadata=metadata or {},
        )
        self.db.add(activity)


def get_comment_service(db: AsyncSession) -> CommentService:
    """Factory-Funktion fuer CommentService.

    Args:
        db: AsyncSession

    Returns:
        CommentService Instanz
    """
    return CommentService(db)
