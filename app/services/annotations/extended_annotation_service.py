"""Erweiterter Annotations-Service.

Verwaltet Bounding-Box-Annotationen, verschachtelte Kommentar-Antworten
und Aufgaben aus Kommentar-Threads.

Erweitert den bestehenden AnnotationService um:
- BoundingBox-Annotationen mit praeziser PDF-Positionierung
- Verschachtelte Antworten (Replies) mit @Mention-Verarbeitung
- Aufgabenverwaltung aus Kommentar-Threads
- Soft-Delete fuer Annotationen
"""

from __future__ import annotations

import uuid as uuid_module
from datetime import datetime
from typing import Dict, List, Optional, Sequence

import structlog
from sqlalchemy import and_, desc, select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.datetime_utils import utc_now
from app.core.safe_errors import safe_error_log
from app.db.models import User
from app.db.models_annotations_extended import (
    AnnotationType,
    BoundingBoxAnnotation,
    CommentReply,
    CommentTask,
    CommentTaskStatus,
)
from app.db.models_comments import CommentThread

logger = structlog.get_logger(__name__)


class ExtendedAnnotationService:
    """Service fuer erweiterte Dokument-Annotationen.

    Bietet CRUD-Operationen fuer:
    - BoundingBox-Annotationen (PDF-Markierungen)
    - Verschachtelte Kommentar-Antworten
    - Kommentar-Aufgaben
    """

    def __init__(self, db: AsyncSession) -> None:
        """Initialisiert den Service.

        Args:
            db: Async Datenbank-Session
        """
        self.db = db

    # =========================================================================
    # BOUNDING BOX ANNOTATIONS
    # =========================================================================

    async def create_bounding_box(
        self,
        document_id: uuid_module.UUID,
        page_number: int,
        x: float,
        y: float,
        width: float,
        height: float,
        author_id: uuid_module.UUID,
        label: Optional[str] = None,
        color: str = "#FFD700",
        annotation_type: str = AnnotationType.BOUNDING_BOX.value,
        thread_id: Optional[uuid_module.UUID] = None,
    ) -> BoundingBoxAnnotation:
        """Erstellt eine Bounding-Box-Annotation auf einer PDF-Seite.

        Args:
            document_id: Dokument-ID
            page_number: Seitennummer (1-basiert)
            x: X-Position (0.0 - 1.0)
            y: Y-Position (0.0 - 1.0)
            width: Breite (0.0 - 1.0)
            height: Hoehe (0.0 - 1.0)
            author_id: Ersteller-ID
            label: Optionale Beschriftung
            color: Farbe (Hex, Standard: #FFD700)
            annotation_type: Annotationstyp
            thread_id: Optionaler verknuepfter Kommentar-Thread

        Returns:
            Erstellte BoundingBoxAnnotation

        Raises:
            ValueError: Bei ungueltigen Koordinaten
        """
        # Validierung der Koordinaten
        if not (0.0 <= x <= 1.0):
            raise ValueError("X-Position muss zwischen 0.0 und 1.0 liegen")
        if not (0.0 <= y <= 1.0):
            raise ValueError("Y-Position muss zwischen 0.0 und 1.0 liegen")
        if not (0.0 <= width <= 1.0):
            raise ValueError("Breite muss zwischen 0.0 und 1.0 liegen")
        if not (0.0 <= height <= 1.0):
            raise ValueError("Hoehe muss zwischen 0.0 und 1.0 liegen")
        if page_number < 1:
            raise ValueError("Seitennummer muss mindestens 1 sein")

        annotation = BoundingBoxAnnotation(
            document_id=document_id,
            page_number=page_number,
            x=x,
            y=y,
            width=width,
            height=height,
            annotation_type=annotation_type,
            label=label[:500] if label else None,
            color=color[:20],
            author_id=author_id,
            thread_id=thread_id,
        )

        self.db.add(annotation)
        await self.db.flush()

        logger.info(
            "bounding_box_annotation_created",
            annotation_id=str(annotation.id),
            document_id=str(document_id),
            page_number=page_number,
            annotation_type=annotation_type,
        )

        return annotation

    async def get_page_annotations(
        self,
        document_id: uuid_module.UUID,
        page_number: int,
    ) -> Sequence[BoundingBoxAnnotation]:
        """Holt alle Bounding-Box-Annotationen fuer eine Seite.

        Args:
            document_id: Dokument-ID
            page_number: Seitennummer

        Returns:
            Liste von BoundingBoxAnnotation-Objekten
        """
        query = (
            select(BoundingBoxAnnotation)
            .where(
                and_(
                    BoundingBoxAnnotation.document_id == document_id,
                    BoundingBoxAnnotation.page_number == page_number,
                    BoundingBoxAnnotation.is_deleted == False,  # noqa: E712
                )
            )
            .order_by(BoundingBoxAnnotation.created_at)
        )

        result = await self.db.execute(query)
        return result.scalars().all()

    async def get_document_annotations(
        self,
        document_id: uuid_module.UUID,
    ) -> Sequence[BoundingBoxAnnotation]:
        """Holt alle Bounding-Box-Annotationen fuer ein Dokument.

        Args:
            document_id: Dokument-ID

        Returns:
            Liste von BoundingBoxAnnotation-Objekten
        """
        query = (
            select(BoundingBoxAnnotation)
            .where(
                and_(
                    BoundingBoxAnnotation.document_id == document_id,
                    BoundingBoxAnnotation.is_deleted == False,  # noqa: E712
                )
            )
            .order_by(
                BoundingBoxAnnotation.page_number,
                BoundingBoxAnnotation.created_at,
            )
        )

        result = await self.db.execute(query)
        return result.scalars().all()

    async def delete_annotation(
        self,
        annotation_id: uuid_module.UUID,
        user_id: uuid_module.UUID,
    ) -> bool:
        """Soft-Delete einer Bounding-Box-Annotation.

        Nur der Ersteller kann seine eigene Annotation loeschen.

        Args:
            annotation_id: Annotation-ID
            user_id: ID des anfragenden Benutzers

        Returns:
            True wenn erfolgreich geloescht, False wenn nicht gefunden
        """
        query = select(BoundingBoxAnnotation).where(
            and_(
                BoundingBoxAnnotation.id == annotation_id,
                BoundingBoxAnnotation.author_id == user_id,
                BoundingBoxAnnotation.is_deleted == False,  # noqa: E712
            )
        )
        result = await self.db.execute(query)
        annotation = result.scalar_one_or_none()

        if not annotation:
            return False

        annotation.is_deleted = True
        annotation.deleted_at = utc_now()
        await self.db.flush()

        logger.info(
            "bounding_box_annotation_deleted",
            annotation_id=str(annotation_id),
            user_id=str(user_id),
        )

        return True

    # =========================================================================
    # COMMENT REPLIES (Verschachtelte Antworten)
    # =========================================================================

    async def create_reply(
        self,
        thread_id: uuid_module.UUID,
        author_id: uuid_module.UUID,
        content: str,
        mentions: Optional[List[str]] = None,
        parent_reply_id: Optional[uuid_module.UUID] = None,
    ) -> CommentReply:
        """Erstellt eine verschachtelte Antwort auf einen Kommentar-Thread.

        Args:
            thread_id: Thread-ID
            author_id: Ersteller-ID
            content: Antwort-Inhalt
            mentions: Liste von erwaehnten User-UUIDs (als Strings)
            parent_reply_id: Optionale Eltern-Antwort fuer Verschachtelung

        Returns:
            Erstellte CommentReply

        Raises:
            ValueError: Wenn Thread nicht existiert
        """
        # Thread-Existenz pruefen
        thread_query = select(CommentThread).where(
            CommentThread.id == thread_id
        )
        thread_result = await self.db.execute(thread_query)
        thread = thread_result.scalar_one_or_none()

        if not thread:
            raise ValueError("Kommentar-Thread nicht gefunden")

        # Eltern-Antwort validieren falls angegeben
        if parent_reply_id is not None:
            parent_query = select(CommentReply).where(
                and_(
                    CommentReply.id == parent_reply_id,
                    CommentReply.thread_id == thread_id,
                    CommentReply.is_deleted == False,  # noqa: E712
                )
            )
            parent_result = await self.db.execute(parent_query)
            parent = parent_result.scalar_one_or_none()
            if not parent:
                raise ValueError(
                    "Eltern-Antwort nicht gefunden oder gehoert nicht zum Thread"
                )

        # Mentions bereinigen und validieren
        validated_mentions: List[str] = []
        if mentions:
            for mention_str in mentions:
                try:
                    uuid_module.UUID(mention_str)
                    validated_mentions.append(mention_str)
                except ValueError:
                    logger.warning(
                        "invalid_mention_uuid_skipped",
                        mention=str(mention_str)[:50],
                    )

        reply = CommentReply(
            thread_id=thread_id,
            author_id=author_id,
            content=content[:5000],
            mentions=validated_mentions,
            parent_reply_id=parent_reply_id,
        )

        self.db.add(reply)

        # Thread reply_count aktualisieren
        thread.reply_count = (thread.reply_count or 0) + 1

        await self.db.flush()

        logger.info(
            "comment_reply_created",
            reply_id=str(reply.id),
            thread_id=str(thread_id),
            author_id=str(author_id),
            mention_count=len(validated_mentions),
        )

        # @Mentions verarbeiten
        if validated_mentions:
            await self.process_mentions(
                thread_id=thread_id,
                reply_id=reply.id,
                author_id=author_id,
                mentions=validated_mentions,
            )

        return reply

    async def get_thread_with_replies(
        self,
        thread_id: uuid_module.UUID,
    ) -> Dict[str, object]:
        """Holt einen Thread mit allen verschachtelten Antworten als Baumstruktur.

        Args:
            thread_id: Thread-ID

        Returns:
            Dict mit Thread-Info und verschachtelten Replies
        """
        # Thread laden
        thread_query = select(CommentThread).where(
            CommentThread.id == thread_id
        )
        thread_result = await self.db.execute(thread_query)
        thread = thread_result.scalar_one_or_none()

        if not thread:
            raise ValueError("Kommentar-Thread nicht gefunden")

        # Alle Replies laden
        replies_query = (
            select(CommentReply)
            .where(
                and_(
                    CommentReply.thread_id == thread_id,
                    CommentReply.is_deleted == False,  # noqa: E712
                )
            )
            .order_by(CommentReply.created_at)
        )
        replies_result = await self.db.execute(replies_query)
        all_replies = replies_result.scalars().all()

        # Autoren-Namen laden
        author_ids = list({r.author_id for r in all_replies})
        authors_map: Dict[uuid_module.UUID, str] = {}
        if author_ids:
            users_result = await self.db.execute(
                select(User).where(User.id.in_(author_ids))
            )
            for user in users_result.scalars().all():
                display_name = user.full_name or user.email
                authors_map[user.id] = display_name

        # Baumstruktur aufbauen
        def _build_reply_tree(
            reply: CommentReply,
        ) -> Dict[str, object]:
            children = [
                r for r in all_replies
                if r.parent_reply_id == reply.id
            ]
            return {
                "id": str(reply.id),
                "thread_id": str(reply.thread_id),
                "parent_reply_id": (
                    str(reply.parent_reply_id)
                    if reply.parent_reply_id
                    else None
                ),
                "author_id": str(reply.author_id),
                "author_name": authors_map.get(
                    reply.author_id, "Unbekannter Benutzer"
                ),
                "content": reply.content,
                "mentions": reply.mentions or [],
                "is_edited": reply.is_edited,
                "edited_at": (
                    reply.edited_at.isoformat() if reply.edited_at else None
                ),
                "created_at": (
                    reply.created_at.isoformat() if reply.created_at else None
                ),
                "children": [
                    _build_reply_tree(child) for child in children
                ],
            }

        # Root-Replies (ohne parent_reply_id) als Ausgangspunkt
        root_replies = [
            r for r in all_replies if r.parent_reply_id is None
        ]

        return {
            "thread": {
                "id": str(thread.id),
                "document_id": str(thread.document_id),
                "status": thread.status,
                "subject": thread.subject,
                "reply_count": thread.reply_count or 0,
                "created_at": (
                    thread.created_at.isoformat()
                    if thread.created_at
                    else None
                ),
            },
            "replies": [
                _build_reply_tree(reply) for reply in root_replies
            ],
        }

    async def process_mentions(
        self,
        thread_id: uuid_module.UUID,
        reply_id: uuid_module.UUID,
        author_id: uuid_module.UUID,
        mentions: List[str],
    ) -> int:
        """Verarbeitet @Mentions und sendet Benachrichtigungen.

        Args:
            thread_id: Thread-ID fuer Kontext
            reply_id: Reply-ID fuer Kontext
            author_id: ID des Erwaehnenden
            mentions: Liste von User-UUIDs (als Strings)

        Returns:
            Anzahl erfolgreich versendeter Benachrichtigungen
        """
        sent_count = 0

        for mention_str in mentions:
            try:
                mentioned_user_id = uuid_module.UUID(mention_str)

                # Nicht sich selbst benachrichtigen
                if mentioned_user_id == author_id:
                    continue

                # Benutzer existiert?
                user = await self.db.get(User, mentioned_user_id)
                if not user:
                    logger.warning(
                        "mention_user_not_found",
                        user_id=mention_str,
                    )
                    continue

                # Benachrichtigung senden
                try:
                    from app.services.notification_service import (
                        get_notification_service,
                        NotificationType,
                    )

                    notification_service = get_notification_service()
                    await notification_service.in_app.store(
                        user_id=mention_str,
                        notification={
                            "type": "comment_mention",
                            "title": "Neue Erwaehnung in Kommentar",
                            "message": (
                                "Sie wurden in einem Kommentar-Thread erwaehnt."
                            ),
                            "priority": "normal",
                            "thread_id": str(thread_id),
                            "reply_id": str(reply_id),
                        },
                    )
                    sent_count += 1

                    logger.debug(
                        "mention_notification_sent",
                        mentioned_user_id=mention_str,
                        thread_id=str(thread_id),
                    )

                except Exception as e:
                    logger.warning(
                        "mention_notification_failed",
                        mentioned_user_id=mention_str,
                        **safe_error_log(e),
                    )

            except ValueError:
                logger.warning(
                    "invalid_mention_uuid",
                    mention=str(mention_str)[:50],
                )

        return sent_count

    # =========================================================================
    # COMMENT TASKS (Aufgaben aus Kommentaren)
    # =========================================================================

    async def create_comment_task(
        self,
        thread_id: uuid_module.UUID,
        assigned_to_user_id: uuid_module.UUID,
        title: str,
        created_by_user_id: uuid_module.UUID,
        description: Optional[str] = None,
        due_date: Optional[datetime] = None,
    ) -> CommentTask:
        """Erstellt eine Aufgabe aus einem Kommentar-Thread.

        Args:
            thread_id: Thread-ID
            assigned_to_user_id: Zugewiesener Benutzer
            title: Aufgabentitel
            created_by_user_id: Ersteller
            description: Optionale Beschreibung
            due_date: Optionales Faelligkeitsdatum

        Returns:
            Erstellte CommentTask

        Raises:
            ValueError: Wenn Thread oder Benutzer nicht existiert
        """
        # Thread-Existenz pruefen
        thread_query = select(CommentThread).where(
            CommentThread.id == thread_id
        )
        thread_result = await self.db.execute(thread_query)
        thread = thread_result.scalar_one_or_none()

        if not thread:
            raise ValueError("Kommentar-Thread nicht gefunden")

        # Zugewiesener Benutzer existiert?
        assigned_user = await self.db.get(User, assigned_to_user_id)
        if not assigned_user:
            raise ValueError("Zugewiesener Benutzer nicht gefunden")

        task = CommentTask(
            thread_id=thread_id,
            assigned_to_user_id=assigned_to_user_id,
            title=title[:500],
            description=description[:5000] if description else None,
            status=CommentTaskStatus.OFFEN.value,
            due_date=due_date,
            created_by_user_id=created_by_user_id,
        )

        self.db.add(task)
        await self.db.flush()

        logger.info(
            "comment_task_created",
            task_id=str(task.id),
            thread_id=str(thread_id),
            assigned_to=str(assigned_to_user_id),
        )

        # Benachrichtigung an zugewiesenen Benutzer
        try:
            from app.services.notification_service import (
                get_notification_service,
            )

            notification_service = get_notification_service()
            await notification_service.in_app.store(
                user_id=str(assigned_to_user_id),
                notification={
                    "type": "task_assigned",
                    "title": "Neue Aufgabe zugewiesen",
                    "message": f"Ihnen wurde eine Aufgabe zugewiesen: {title}",
                    "priority": "normal",
                    "task_id": str(task.id),
                    "thread_id": str(thread_id),
                },
            )
        except Exception as e:
            logger.warning(
                "task_assignment_notification_failed",
                task_id=str(task.id),
                **safe_error_log(e),
            )

        return task

    async def get_user_tasks(
        self,
        user_id: uuid_module.UUID,
        status: Optional[str] = None,
        limit: int = 50,
    ) -> Sequence[CommentTask]:
        """Holt Aufgaben fuer einen Benutzer.

        Args:
            user_id: Benutzer-ID
            status: Optionaler Status-Filter
            limit: Maximale Anzahl Ergebnisse

        Returns:
            Liste von CommentTask-Objekten
        """
        query = select(CommentTask).where(
            CommentTask.assigned_to_user_id == user_id
        )

        if status is not None:
            query = query.where(CommentTask.status == status)

        query = query.order_by(
            # Offene Aufgaben zuerst, dann nach Faelligkeitsdatum
            desc(CommentTask.status == CommentTaskStatus.OFFEN.value),
            CommentTask.due_date.asc().nullslast(),
            CommentTask.created_at.desc(),
        ).limit(limit)

        result = await self.db.execute(query)
        return result.scalars().all()

    async def update_task_status(
        self,
        task_id: uuid_module.UUID,
        status: str,
        user_id: uuid_module.UUID,
    ) -> Optional[CommentTask]:
        """Aktualisiert den Status einer Kommentar-Aufgabe.

        Args:
            task_id: Aufgaben-ID
            status: Neuer Status
            user_id: ID des aenderenden Benutzers

        Returns:
            Aktualisierte CommentTask oder None wenn nicht gefunden

        Raises:
            ValueError: Bei ungueltigem Status
        """
        # Status validieren
        valid_statuses = {s.value for s in CommentTaskStatus}
        if status not in valid_statuses:
            raise ValueError(
                f"Ungueltiger Status: {status}. "
                f"Erlaubt: {', '.join(valid_statuses)}"
            )

        query = select(CommentTask).where(CommentTask.id == task_id)
        result = await self.db.execute(query)
        task = result.scalar_one_or_none()

        if not task:
            return None

        # Nur zugewiesener Benutzer oder Ersteller darf aendern
        if (
            task.assigned_to_user_id != user_id
            and task.created_by_user_id != user_id
        ):
            raise ValueError(
                "Nur der zugewiesene Benutzer oder Ersteller kann "
                "den Status aendern"
            )

        old_status = task.status
        task.status = status

        if status == CommentTaskStatus.ERLEDIGT.value:
            task.completed_at = utc_now()
        elif old_status == CommentTaskStatus.ERLEDIGT.value:
            # Aufgabe wieder geoeffnet
            task.completed_at = None

        await self.db.flush()

        logger.info(
            "comment_task_status_updated",
            task_id=str(task_id),
            old_status=old_status,
            new_status=status,
            user_id=str(user_id),
        )

        return task

    async def get_overdue_tasks(self) -> Sequence[CommentTask]:
        """Holt alle ueberfaelligen Aufgaben.

        Returns:
            Liste von ueberfaelligen CommentTask-Objekten
        """
        now = utc_now()
        query = (
            select(CommentTask)
            .where(
                and_(
                    CommentTask.due_date < now,
                    CommentTask.status != CommentTaskStatus.ERLEDIGT.value,
                    CommentTask.due_date.isnot(None),
                )
            )
            .order_by(CommentTask.due_date)
        )

        result = await self.db.execute(query)
        return result.scalars().all()
