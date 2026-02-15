# -*- coding: utf-8 -*-
"""
Comment Reply Service.

Verschachtelte Antworten auf Kommentare mit @mentions.
Thread-Replies mit Benachrichtigungen bei @mentions.
Kommentar-basierte Aufgaben ('Bitte pruefen' -> erzeugt Task).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Dict, List, Optional
from uuid import UUID

import structlog
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.datetime_utils import utc_now
from app.db.models_annotations_extended import (
    CommentReply,
    CommentTask,
    CommentTaskStatus,
    MentionNotification,
)

logger = structlog.get_logger(__name__)


class CommentReplyService:
    """Verschachtelte Antworten auf Kommentare mit @mentions.

    Thread-Replies mit Benachrichtigungen bei @mentions.
    Kommentar-basierte Aufgaben ('Bitte pruefen' -> erzeugt Task).
    """

    async def create_reply(
        self,
        db: AsyncSession,
        company_id: UUID,
        thread_id: UUID,
        author_id: UUID,
        content: str,
        parent_reply_id: Optional[UUID] = None,
        mentions: Optional[List[UUID]] = None,
    ) -> CommentReply:
        """Antwort erstellen mit optionalen @mentions.

        Args:
            db: Datenbank-Session
            company_id: Mandant-ID
            thread_id: Thread-ID
            author_id: Autor-ID
            content: Antwort-Inhalt
            parent_reply_id: Eltern-Antwort fuer Verschachtelung
            mentions: Liste von erwaehnten User-IDs

        Returns:
            Erstellte CommentReply
        """
        mention_ids = [str(uid) for uid in (mentions or [])]

        reply = CommentReply(
            id=uuid.uuid4(),
            thread_id=thread_id,
            parent_reply_id=parent_reply_id,
            author_id=author_id,
            content=content,
            mentions=mention_ids,
        )

        db.add(reply)
        await db.flush()

        logger.info(
            "comment_reply_created",
            reply_id=str(reply.id),
            thread_id=str(thread_id),
            author_id=str(author_id),
        )

        # Mention-Benachrichtigungen erstellen
        if mentions:
            await self._process_mentions(
                db=db,
                company_id=company_id,
                mentioning_user_id=author_id,
                mentioned_user_ids=mentions,
                source_type="reply",
                source_id=reply.id,
                thread_id=thread_id,
            )

        return reply

    async def get_thread_replies(
        self,
        db: AsyncSession,
        thread_id: UUID,
    ) -> List[CommentReply]:
        """Alle Antworten eines Threads abrufen (flache Liste).

        Gibt eine flache Liste zurueck; parent_reply_id kann fuer
        Baum-Konstruktion im Frontend verwendet werden.

        Args:
            db: Datenbank-Session
            thread_id: Thread-ID

        Returns:
            Liste aller Antworten sortiert nach Erstelldatum
        """
        result = await db.execute(
            select(CommentReply)
            .where(CommentReply.thread_id == thread_id)
            .order_by(CommentReply.created_at)
        )
        return list(result.scalars().all())

    async def edit_reply(
        self,
        db: AsyncSession,
        reply_id: UUID,
        author_id: UUID,
        new_content: str,
    ) -> CommentReply:
        """Antwort bearbeiten (nur Autor).

        Args:
            db: Datenbank-Session
            reply_id: Antwort-ID
            author_id: Autor-ID (muss uebereinstimmen)
            new_content: Neuer Inhalt

        Returns:
            Aktualisierte CommentReply

        Raises:
            ValueError: Wenn Antwort nicht gefunden oder Benutzer nicht Autor
        """
        result = await db.execute(
            select(CommentReply).where(
                and_(
                    CommentReply.id == reply_id,
                    CommentReply.author_id == author_id,
                )
            )
        )
        reply = result.scalar_one_or_none()

        if not reply:
            raise ValueError("Antwort nicht gefunden oder keine Berechtigung")

        reply.content = new_content
        reply.is_edited = True
        reply.edited_at = utc_now()

        await db.flush()

        logger.info(
            "comment_reply_edited",
            reply_id=str(reply_id),
            author_id=str(author_id),
        )
        return reply

    async def create_task_from_comment(
        self,
        db: AsyncSession,
        company_id: UUID,
        created_by: UUID,
        title: str,
        thread_id: Optional[UUID] = None,
        reply_id: Optional[UUID] = None,
        assigned_to: Optional[UUID] = None,
        description: Optional[str] = None,
        due_date: Optional[datetime] = None,
    ) -> CommentTask:
        """Aufgabe aus Kommentar/Antwort erstellen ('Bitte pruefen' -> Task).

        Args:
            db: Datenbank-Session
            company_id: Mandant-ID
            created_by: Ersteller-ID
            title: Aufgabentitel
            thread_id: Optionale Thread-Referenz
            reply_id: Optionale Antwort-Referenz
            assigned_to: Optionale Zuweisung
            description: Optionale Beschreibung
            due_date: Optionales Faelligkeitsdatum

        Returns:
            Erstellte CommentTask
        """
        task = CommentTask(
            id=uuid.uuid4(),
            thread_id=thread_id,
            created_by_user_id=created_by,
            assigned_to_user_id=assigned_to,
            title=title,
            description=description,
            status=CommentTaskStatus.OFFEN.value,
            due_date=due_date,
        )

        db.add(task)
        await db.flush()

        logger.info(
            "comment_task_created",
            task_id=str(task.id),
            title=title,
            assigned_to=str(assigned_to) if assigned_to else None,
        )
        return task

    async def get_tasks(
        self,
        db: AsyncSession,
        company_id: UUID,
        assigned_to: Optional[UUID] = None,
        status: Optional[str] = None,
    ) -> List[CommentTask]:
        """Kommentar-Aufgaben abrufen.

        Args:
            db: Datenbank-Session
            company_id: Mandant-ID
            assigned_to: Optional nach Zuweisung filtern
            status: Optional nach Status filtern

        Returns:
            Liste der Aufgaben
        """
        conditions = []
        if assigned_to is not None:
            conditions.append(CommentTask.assigned_to_user_id == assigned_to)
        if status is not None:
            conditions.append(CommentTask.status == status)

        query = select(CommentTask)
        if conditions:
            query = query.where(and_(*conditions))
        result = await db.execute(query.order_by(CommentTask.created_at.desc()))
        return list(result.scalars().all())

    async def update_task_status(
        self,
        db: AsyncSession,
        task_id: UUID,
        company_id: UUID,
        new_status: str,
    ) -> CommentTask:
        """Aufgaben-Status aktualisieren.

        Args:
            db: Datenbank-Session
            task_id: Aufgaben-ID
            company_id: Mandant-ID
            new_status: Neuer Status

        Returns:
            Aktualisierte CommentTask

        Raises:
            ValueError: Wenn Aufgabe nicht gefunden
        """
        result = await db.execute(
            select(CommentTask).where(CommentTask.id == task_id)
        )
        task = result.scalar_one_or_none()

        if not task:
            raise ValueError("Aufgabe nicht gefunden")

        task.status = new_status
        if new_status == CommentTaskStatus.ERLEDIGT.value:
            task.completed_at = utc_now()

        await db.flush()

        logger.info(
            "comment_task_status_updated",
            task_id=str(task_id),
            new_status=new_status,
        )
        return task

    async def get_mention_notifications(
        self,
        db: AsyncSession,
        user_id: UUID,
        unread_only: bool = True,
    ) -> List[MentionNotification]:
        """@mention-Benachrichtigungen fuer einen Benutzer abrufen.

        Args:
            db: Datenbank-Session
            user_id: Benutzer-ID
            unread_only: Nur ungelesene Benachrichtigungen

        Returns:
            Liste der Mention-Benachrichtigungen
        """
        conditions = [MentionNotification.mentioned_user_id == user_id]
        if unread_only:
            conditions.append(MentionNotification.is_read == False)  # noqa: E712

        result = await db.execute(
            select(MentionNotification)
            .where(and_(*conditions))
            .order_by(MentionNotification.created_at.desc())
            .limit(50)
        )
        return list(result.scalars().all())

    async def mark_mention_read(
        self,
        db: AsyncSession,
        notification_id: UUID,
        user_id: UUID,
    ) -> MentionNotification:
        """Mention als gelesen markieren.

        Args:
            db: Datenbank-Session
            notification_id: Benachrichtigungs-ID
            user_id: Benutzer-ID (muss Empfaenger sein)

        Returns:
            Aktualisierte MentionNotification

        Raises:
            ValueError: Wenn Benachrichtigung nicht gefunden
        """
        result = await db.execute(
            select(MentionNotification).where(
                and_(
                    MentionNotification.id == notification_id,
                    MentionNotification.mentioned_user_id == user_id,
                )
            )
        )
        notification = result.scalar_one_or_none()

        if not notification:
            raise ValueError("Benachrichtigung nicht gefunden")

        notification.is_read = True
        notification.read_at = utc_now()

        await db.flush()

        logger.debug(
            "mention_notification_read",
            notification_id=str(notification_id),
            user_id=str(user_id),
        )
        return notification

    async def _process_mentions(
        self,
        db: AsyncSession,
        company_id: UUID,
        mentioning_user_id: UUID,
        mentioned_user_ids: List[UUID],
        source_type: str,
        source_id: UUID,
        thread_id: UUID,
    ) -> List[MentionNotification]:
        """Mention-Benachrichtigungen erstellen und Notification senden.

        Args:
            db: Datenbank-Session
            company_id: Mandant-ID
            mentioning_user_id: Erwaehner-ID
            mentioned_user_ids: Liste der erwaehnten User-IDs
            source_type: Quell-Typ (comment, reply, annotation)
            source_id: Quell-ID
            thread_id: Thread-ID fuer Dokument-Referenz

        Returns:
            Liste der erstellten MentionNotifications
        """
        # Thread laden fuer document_id
        from app.db.models_comments import CommentThread
        thread_result = await db.execute(
            select(CommentThread).where(CommentThread.id == thread_id)
        )
        thread = thread_result.scalar_one_or_none()

        if not thread:
            logger.warning(
                "mention_thread_not_found",
                thread_id=str(thread_id),
            )
            return []

        notifications: List[MentionNotification] = []
        for user_id in mentioned_user_ids:
            # Nicht sich selbst benachrichtigen
            if user_id == mentioning_user_id:
                continue

            notification = MentionNotification(
                id=uuid.uuid4(),
                company_id=company_id,
                mentioned_user_id=user_id,
                mentioning_user_id=mentioning_user_id,
                source_type=source_type,
                source_id=source_id,
                document_id=thread.document_id,
            )
            db.add(notification)
            notifications.append(notification)

        if notifications:
            await db.flush()
            logger.info(
                "mention_notifications_created",
                count=len(notifications),
                source_type=source_type,
                source_id=str(source_id),
            )

        return notifications


# Singleton
_comment_reply_service: Optional[CommentReplyService] = None


def get_comment_reply_service() -> CommentReplyService:
    """Factory-Funktion fuer CommentReplyService Singleton."""
    global _comment_reply_service
    if _comment_reply_service is None:
        _comment_reply_service = CommentReplyService()
    return _comment_reply_service
