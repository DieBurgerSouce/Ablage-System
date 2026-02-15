# -*- coding: utf-8 -*-
"""
Celery Tasks fuer Annotationen und Kommentare.

Tasks:
- process_mention_notifications_task: Benachrichtigungen bei @mentions versenden
- check_overdue_comment_tasks_task: Taeglich ueberfaellige Aufgaben pruefen
- cleanup_orphaned_annotations_task: Woechentlich verwaiste Annotationen bereinigen
- cleanup_resolved_annotations_task: Alte erledigte Annotationen aufraeumen

Feinpoliert und durchdacht - Zuverlaessige Annotation-Verwaltung.
"""

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Dict, List

import structlog
from sqlalchemy import and_, select, func, update, delete

from app.workers.celery_app import celery_app
from app.db.session import get_async_session_context
from app.core.safe_errors import safe_error_log

logger = structlog.get_logger(__name__)


def _run_async(coro):
    """Hilfsfunktion um async Code in sync Celery Tasks auszufuehren."""
    return asyncio.run(coro)


@celery_app.task(
    bind=True,
    name="annotations.process_mention_notifications",
    max_retries=3,
    default_retry_delay=30,
    soft_time_limit=60,
    time_limit=120,
)
def process_mention_notifications_task(
    self,
    thread_id: str,
    reply_id: str,
    author_id: str,
    mentioned_user_ids: List[str],
) -> Dict[str, object]:
    """Verarbeitet @Mention-Benachrichtigungen asynchron.

    Wird ausgeloest wenn ein Benutzer in einem Kommentar erwaehnt wird.
    Sendet In-App-Benachrichtigungen an alle erwaehnten Benutzer.

    Args:
        thread_id: Thread-ID
        reply_id: Reply-ID
        author_id: ID des Erwaehnenden
        mentioned_user_ids: Liste der erwaehnten User-IDs

    Returns:
        Dict mit Sendestatus
    """
    logger.info(
        "mention_notification_task_gestartet",
        task_id=self.request.id,
        thread_id=thread_id,
        mention_count=len(mentioned_user_ids),
    )

    async def _do_notify() -> Dict[str, object]:
        from app.services.notification_service import get_notification_service

        notification_service = get_notification_service()
        sent_count = 0
        failed_count = 0

        for user_id in mentioned_user_ids:
            # Nicht sich selbst benachrichtigen
            if user_id == author_id:
                continue

            try:
                await notification_service.in_app.store(
                    user_id=user_id,
                    notification={
                        "type": "comment_mention",
                        "title": "Neue Erwaehnung in Kommentar",
                        "message": (
                            "Sie wurden in einem Kommentar-Thread erwaehnt."
                        ),
                        "priority": "normal",
                        "thread_id": thread_id,
                        "reply_id": reply_id,
                    },
                )
                sent_count += 1
            except Exception as e:
                logger.warning(
                    "mention_notification_send_failed",
                    user_id=user_id,
                    **safe_error_log(e),
                )
                failed_count += 1

        return {
            "thread_id": thread_id,
            "reply_id": reply_id,
            "sent": sent_count,
            "failed": failed_count,
        }

    try:
        result = _run_async(_do_notify())
        logger.info(
            "mention_notification_task_abgeschlossen",
            task_id=self.request.id,
            **result,
        )
        return result

    except Exception as exc:
        logger.error(
            "mention_notification_task_fehler",
            task_id=self.request.id,
            **safe_error_log(exc),
        )
        raise self.retry(exc=exc)


@celery_app.task(
    bind=True,
    name="annotations.check_overdue_comment_tasks",
    max_retries=2,
    default_retry_delay=120,
    soft_time_limit=300,
    time_limit=600,
)
def check_overdue_comment_tasks_task(self) -> Dict[str, object]:
    """Prueft taeglich auf ueberfaellige Kommentar-Aufgaben.

    Findet offene Aufgaben deren Faelligkeitsdatum ueberschritten ist
    und sendet Erinnerungen an die zugewiesenen Benutzer.

    Returns:
        Dict mit Anzahl ueberfaelliger Aufgaben und versendeter Benachrichtigungen
    """
    logger.info(
        "check_overdue_tasks_gestartet",
        task_id=self.request.id,
    )

    async def _do_check() -> Dict[str, object]:
        from app.db.models_annotations_extended import (
            CommentTask,
            CommentTaskStatus,
        )
        from app.services.notification_service import get_notification_service

        notification_service = get_notification_service()

        async with get_async_session_context() as db:
            now = datetime.now(timezone.utc)

            # Finde ueberfaellige offene Aufgaben
            result = await db.execute(
                select(CommentTask).where(
                    and_(
                        CommentTask.status.in_([
                            CommentTaskStatus.OFFEN.value,
                            CommentTaskStatus.IN_BEARBEITUNG.value,
                        ]),
                        CommentTask.due_date.isnot(None),
                        CommentTask.due_date < now,
                    )
                )
            )
            overdue_tasks = result.scalars().all()

            stats: Dict[str, int] = {
                "ueberfaellig": len(overdue_tasks),
                "benachrichtigt": 0,
                "fehler": 0,
            }

            for task in overdue_tasks:
                try:
                    days_overdue = 0
                    if task.due_date:
                        delta = now - task.due_date
                        days_overdue = max(0, delta.days)

                    await notification_service.in_app.store(
                        user_id=str(task.assigned_to_user_id),
                        notification={
                            "type": "task_overdue",
                            "title": "Ueberfaellige Aufgabe",
                            "message": (
                                f"Die Aufgabe '{task.title}' ist seit "
                                f"{days_overdue} Tag(en) ueberfaellig."
                            ),
                            "priority": "high",
                            "task_id": str(task.id),
                            "thread_id": str(task.thread_id),
                        },
                    )
                    stats["benachrichtigt"] += 1

                except Exception as e:
                    logger.warning(
                        "deadline_notification_failed",
                        task_id=str(task.id),
                        **safe_error_log(e),
                    )
                    stats["fehler"] += 1

            return stats

    try:
        result = _run_async(_do_check())
        logger.info(
            "check_overdue_tasks_abgeschlossen",
            task_id=self.request.id,
            **result,
        )
        return result

    except Exception as exc:
        logger.error(
            "check_overdue_tasks_fehler",
            task_id=self.request.id,
            **safe_error_log(exc),
        )
        raise self.retry(exc=exc)


@celery_app.task(
    bind=True,
    name="annotations.cleanup_orphaned_annotations",
    max_retries=2,
    default_retry_delay=120,
    soft_time_limit=600,
    time_limit=900,
)
def cleanup_orphaned_annotations_task(self) -> Dict[str, object]:
    """Bereinigt woechentlich verwaiste Annotationen.

    Soft-Deleted Annotationen die zu geloeschten Dokumenten gehoeren.

    Returns:
        Dict mit Anzahl bereinigter Annotationen
    """
    logger.info(
        "cleanup_orphaned_annotations_gestartet",
        task_id=self.request.id,
    )

    async def _do_cleanup() -> Dict[str, object]:
        from app.core.datetime_utils import utc_now
        from app.db.models import Document
        from app.db.models_annotations_extended import BoundingBoxAnnotation

        cleaned_bbox = 0

        async with get_async_session_context() as db:
            # BoundingBox-Annotationen fuer geloeschte Dokumente
            orphaned_query = (
                select(BoundingBoxAnnotation.id)
                .join(
                    Document,
                    BoundingBoxAnnotation.document_id == Document.id,
                )
                .where(
                    and_(
                        Document.deleted_at.isnot(None),
                        BoundingBoxAnnotation.is_deleted == False,  # noqa: E712
                    )
                )
            )

            result = await db.execute(orphaned_query)
            orphaned_ids = [row[0] for row in result.all()]

            if orphaned_ids:
                now = utc_now()
                await db.execute(
                    update(BoundingBoxAnnotation)
                    .where(BoundingBoxAnnotation.id.in_(orphaned_ids))
                    .values(is_deleted=True, deleted_at=now)
                )
                cleaned_bbox = len(orphaned_ids)

            await db.commit()

        return {
            "cleaned_bounding_box_annotations": cleaned_bbox,
        }

    try:
        result = _run_async(_do_cleanup())
        logger.info(
            "cleanup_orphaned_annotations_abgeschlossen",
            task_id=self.request.id,
            **result,
        )
        return result

    except Exception as exc:
        logger.error(
            "cleanup_orphaned_annotations_fehler",
            task_id=self.request.id,
            **safe_error_log(exc),
        )
        raise self.retry(exc=exc)


@celery_app.task(
    bind=True,
    name="annotations.cleanup_resolved_annotations",
    max_retries=2,
    default_retry_delay=60,
    soft_time_limit=300,
    time_limit=600,
)
def cleanup_resolved_annotations_task(self, days: int = 180) -> Dict[str, object]:
    """Aufraeumen alter erledigter DocumentAnnotations.

    Entfernt erledigte Annotationen die aelter als X Tage sind.
    Wird monatlich ausgefuehrt.

    Args:
        days: Anzahl Tage nach denen erledigte Annotationen entfernt werden

    Returns:
        Dict mit Anzahl entfernter Annotationen
    """
    logger.info(
        "cleanup_resolved_annotations_gestartet",
        task_id=self.request.id,
        days=days,
    )

    async def _do_cleanup() -> Dict[str, object]:
        from app.db.models import DocumentAnnotation

        async with get_async_session_context() as db:
            cutoff = datetime.now(timezone.utc) - timedelta(days=days)

            # Zaehle zu entfernende Annotationen
            count_result = await db.execute(
                select(func.count(DocumentAnnotation.id)).where(
                    and_(
                        DocumentAnnotation.is_resolved == True,  # noqa: E712
                        DocumentAnnotation.resolved_at.isnot(None),
                        DocumentAnnotation.resolved_at < cutoff,
                    )
                )
            )
            count = count_result.scalar() or 0

            if count > 0:
                await db.execute(
                    delete(DocumentAnnotation).where(
                        and_(
                            DocumentAnnotation.is_resolved == True,  # noqa: E712
                            DocumentAnnotation.resolved_at.isnot(None),
                            DocumentAnnotation.resolved_at < cutoff,
                        )
                    )
                )
                await db.commit()

            return {
                "entfernt": count,
                "cutoff_datum": cutoff.isoformat(),
            }

    try:
        result = _run_async(_do_cleanup())
        logger.info(
            "cleanup_resolved_annotations_abgeschlossen",
            task_id=self.request.id,
            **result,
        )
        return result

    except Exception as exc:
        logger.error(
            "cleanup_resolved_annotations_fehler",
            task_id=self.request.id,
            **safe_error_log(exc),
        )
        raise self.retry(exc=exc)
