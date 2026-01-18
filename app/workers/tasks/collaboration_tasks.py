# -*- coding: utf-8 -*-
"""
Celery Tasks fuer die Collaboration-Suite.

Geplante Tasks:
- process_hourly_digests: Stuendliche Digest-Emails (jede volle Stunde)
- process_daily_digests: Taegliche Digest-Emails (08:00 Uhr)
- process_weekly_digests: Woechentliche Digest-Emails (Montag 08:00)
- check_overdue_tasks: Aufgaben-Erinnerungen (stuendlich)
- escalate_overdue_tasks: Eskalation bei ueberfaelligen Aufgaben (alle 4 Stunden)
- cleanup_old_digest_entries: Alte Digest-Queue-Eintraege loeschen (woechentlich)

Feinpoliert und durchdacht - Zuverlaessige Kollaboration fuer Teams.
"""

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

import structlog
from celery import Task
from sqlalchemy import and_, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.workers.celery_app import celery_app, CPUTask
from app.db.session import get_async_session_context
from app.db.models import (
    DigestFrequency,
    DocumentTask,
    NotificationDigestQueue,
    NotificationPreference,
    NotificationType,
    TaskStatus,
    User,
    UserNotification,
)
from app.core.datetime_utils import utc_now

logger = structlog.get_logger(__name__)


def run_async(coro):
    """Hilfsfunktion um async Code in sync Celery Tasks auszufuehren.

    MEMORY FIX: Verwendet asyncio.run() statt new_event_loop() um Memory Leaks
    zu verhindern. asyncio.run() erstellt einen neuen Event-Loop, fuehrt die
    Coroutine aus und schliesst den Loop korrekt inkl. aller pending Tasks.
    """
    return asyncio.run(coro)


# =============================================================================
# DIGEST PROCESSING TASKS
# =============================================================================


@celery_app.task(
    bind=True,
    base=CPUTask,
    name="app.workers.tasks.collaboration_tasks.process_hourly_digests",
    max_retries=3,
    default_retry_delay=300,
)
def process_hourly_digests(self) -> Dict[str, Any]:
    """
    Celery Task fuer stuendliche Digest-Emails.

    Verarbeitet alle Queue-Eintraege mit hourly-Frequenz und
    sendet zusammengefasste Benachrichtigungen an Benutzer.

    Returns:
        Dict mit Ergebnissen (users_processed, emails_sent, errors)
    """
    logger.info("hourly_digest_task_gestartet", task_id=self.request.id)

    async def run_digest():
        from app.services.collaboration.digest_service import DigestService
        from app.services.notification_service import EmailNotifier

        async with get_async_session_context() as db:
            digest_service = DigestService(db)
            email_notifier = EmailNotifier()

            results = {
                "users_processed": 0,
                "emails_sent": 0,
                "emails_failed": 0,
                "entries_processed": 0,
            }

            # Hole ausstehende Digests
            pending_by_user = await digest_service.get_pending_digests(
                frequency=DigestFrequency.HOURLY.value,
                limit=500,
            )

            for user_id, entries in pending_by_user.items():
                results["users_processed"] += 1
                results["entries_processed"] += len(entries)

                try:
                    # Kompiliere Digest
                    digest_data = await digest_service.compile_digest(
                        user_id=user_id,
                        queue_entries=entries,
                    )

                    if not digest_data or not digest_data.get("user_email"):
                        continue

                    # Rendere HTML
                    html_body = digest_service.render_digest_html(
                        digest_data=digest_data,
                        frequency=DigestFrequency.HOURLY.value,
                    )
                    subject = digest_service.render_digest_subject(
                        digest_data=digest_data,
                        frequency=DigestFrequency.HOURLY.value,
                    )

                    # Sende Email
                    if email_notifier.is_configured:
                        success = await email_notifier.send(
                            to_email=digest_data["user_email"],
                            subject=subject,
                            body=html_body,
                            html=True,
                        )
                        if success:
                            results["emails_sent"] += 1
                            # Markiere als gesendet
                            queue_ids = [e.id for e in entries]
                            await digest_service.mark_digests_sent(queue_ids)
                        else:
                            results["emails_failed"] += 1
                    else:
                        logger.warning("email_notifier_not_configured")

                except Exception as e:
                    results["emails_failed"] += 1
                    logger.error(
                        "hourly_digest_user_error",
                        user_id=str(user_id),
                        error=str(e),
                    )

            return results

    try:
        results = run_async(run_digest())
        logger.info(
            "hourly_digest_task_abgeschlossen",
            task_id=self.request.id,
            **results,
        )
        return results

    except Exception as e:
        logger.error(
            "hourly_digest_task_fehler",
            task_id=self.request.id,
            error=str(e),
        )
        raise self.retry(exc=e)


@celery_app.task(
    bind=True,
    base=CPUTask,
    name="app.workers.tasks.collaboration_tasks.process_daily_digests",
    max_retries=3,
    default_retry_delay=300,
)
def process_daily_digests(self) -> Dict[str, Any]:
    """
    Celery Task fuer taegliche Digest-Emails.

    Wird taeglich um 08:00 Uhr ausgefuehrt.

    Returns:
        Dict mit Ergebnissen (users_processed, emails_sent, errors)
    """
    logger.info("daily_digest_task_gestartet", task_id=self.request.id)

    async def run_digest():
        from app.services.collaboration.digest_service import DigestService
        from app.services.notification_service import EmailNotifier

        async with get_async_session_context() as db:
            digest_service = DigestService(db)
            email_notifier = EmailNotifier()

            results = {
                "users_processed": 0,
                "emails_sent": 0,
                "emails_failed": 0,
                "entries_processed": 0,
            }

            # Hole ausstehende Digests
            pending_by_user = await digest_service.get_pending_digests(
                frequency=DigestFrequency.DAILY.value,
                limit=1000,
            )

            for user_id, entries in pending_by_user.items():
                results["users_processed"] += 1
                results["entries_processed"] += len(entries)

                try:
                    digest_data = await digest_service.compile_digest(
                        user_id=user_id,
                        queue_entries=entries,
                    )

                    if not digest_data or not digest_data.get("user_email"):
                        continue

                    html_body = digest_service.render_digest_html(
                        digest_data=digest_data,
                        frequency=DigestFrequency.DAILY.value,
                    )
                    subject = digest_service.render_digest_subject(
                        digest_data=digest_data,
                        frequency=DigestFrequency.DAILY.value,
                    )

                    if email_notifier.is_configured:
                        success = await email_notifier.send(
                            to_email=digest_data["user_email"],
                            subject=subject,
                            body=html_body,
                            html=True,
                        )
                        if success:
                            results["emails_sent"] += 1
                            queue_ids = [e.id for e in entries]
                            await digest_service.mark_digests_sent(queue_ids)
                        else:
                            results["emails_failed"] += 1

                except Exception as e:
                    results["emails_failed"] += 1
                    logger.error(
                        "daily_digest_user_error",
                        user_id=str(user_id),
                        error=str(e),
                    )

            return results

    try:
        results = run_async(run_digest())
        logger.info(
            "daily_digest_task_abgeschlossen",
            task_id=self.request.id,
            **results,
        )
        return results

    except Exception as e:
        logger.error(
            "daily_digest_task_fehler",
            task_id=self.request.id,
            error=str(e),
        )
        raise self.retry(exc=e)


@celery_app.task(
    bind=True,
    base=CPUTask,
    name="app.workers.tasks.collaboration_tasks.process_weekly_digests",
    max_retries=3,
    default_retry_delay=300,
)
def process_weekly_digests(self) -> Dict[str, Any]:
    """
    Celery Task fuer woechentliche Digest-Emails.

    Wird jeden Montag um 08:00 Uhr ausgefuehrt.

    Returns:
        Dict mit Ergebnissen (users_processed, emails_sent, errors)
    """
    logger.info("weekly_digest_task_gestartet", task_id=self.request.id)

    async def run_digest():
        from app.services.collaboration.digest_service import DigestService
        from app.services.notification_service import EmailNotifier

        async with get_async_session_context() as db:
            digest_service = DigestService(db)
            email_notifier = EmailNotifier()

            results = {
                "users_processed": 0,
                "emails_sent": 0,
                "emails_failed": 0,
                "entries_processed": 0,
            }

            pending_by_user = await digest_service.get_pending_digests(
                frequency=DigestFrequency.WEEKLY.value,
                limit=1000,
            )

            for user_id, entries in pending_by_user.items():
                results["users_processed"] += 1
                results["entries_processed"] += len(entries)

                try:
                    digest_data = await digest_service.compile_digest(
                        user_id=user_id,
                        queue_entries=entries,
                    )

                    if not digest_data or not digest_data.get("user_email"):
                        continue

                    html_body = digest_service.render_digest_html(
                        digest_data=digest_data,
                        frequency=DigestFrequency.WEEKLY.value,
                    )
                    subject = digest_service.render_digest_subject(
                        digest_data=digest_data,
                        frequency=DigestFrequency.WEEKLY.value,
                    )

                    if email_notifier.is_configured:
                        success = await email_notifier.send(
                            to_email=digest_data["user_email"],
                            subject=subject,
                            body=html_body,
                            html=True,
                        )
                        if success:
                            results["emails_sent"] += 1
                            queue_ids = [e.id for e in entries]
                            await digest_service.mark_digests_sent(queue_ids)
                        else:
                            results["emails_failed"] += 1

                except Exception as e:
                    results["emails_failed"] += 1
                    logger.error(
                        "weekly_digest_user_error",
                        user_id=str(user_id),
                        error=str(e),
                    )

            return results

    try:
        results = run_async(run_digest())
        logger.info(
            "weekly_digest_task_abgeschlossen",
            task_id=self.request.id,
            **results,
        )
        return results

    except Exception as e:
        logger.error(
            "weekly_digest_task_fehler",
            task_id=self.request.id,
            error=str(e),
        )
        raise self.retry(exc=e)


# =============================================================================
# TASK REMINDER AND ESCALATION
# =============================================================================


@celery_app.task(
    bind=True,
    base=CPUTask,
    name="app.workers.tasks.collaboration_tasks.check_overdue_tasks",
    max_retries=2,
    default_retry_delay=60,
)
def check_overdue_tasks(self) -> Dict[str, Any]:
    """
    Celery Task zum Pruefen ueberfaelliger Aufgaben.

    Sendet Erinnerungen an Bearbeiter wenn:
    - Aufgabe faellig ist (due_date erreicht)
    - Aufgabe noch nicht abgeschlossen
    - Keine kuerzliche Erinnerung gesendet (24h Cooldown)

    Wird stuendlich ausgefuehrt.

    Returns:
        Dict mit Statistiken
    """
    logger.info("check_overdue_tasks_gestartet", task_id=self.request.id)

    async def run_check():
        from app.services.notification_service import NotificationService

        async with get_async_session_context() as db:
            now = utc_now()
            reminder_cooldown = now - timedelta(hours=24)

            results = {
                "tasks_checked": 0,
                "reminders_sent": 0,
                "errors": 0,
            }

            # Finde ueberfaellige Aufgaben
            result = await db.execute(
                select(DocumentTask)
                .options(
                    selectinload(DocumentTask.assigned_to),
                    selectinload(DocumentTask.created_by),
                )
                .where(
                    and_(
                        DocumentTask.due_date <= now,
                        DocumentTask.status.in_([
                            TaskStatus.OPEN.value,
                            TaskStatus.IN_PROGRESS.value,
                            TaskStatus.BLOCKED.value,
                        ]),
                        # Nur wenn keine kuerzliche Erinnerung
                        (DocumentTask.last_reminder_at.is_(None)) |
                        (DocumentTask.last_reminder_at < reminder_cooldown),
                    )
                )
                .limit(500)
            )
            overdue_tasks = result.scalars().all()
            results["tasks_checked"] = len(overdue_tasks)

            notification_service = NotificationService(db)

            for task in overdue_tasks:
                try:
                    if not task.assigned_to_id:
                        continue

                    # Berechne Ueberfaelligkeit
                    overdue_hours = int((now - task.due_date).total_seconds() / 3600)
                    overdue_text = f"{overdue_hours} Stunden" if overdue_hours < 48 else f"{overdue_hours // 24} Tagen"

                    # Sende Erinnerung
                    await notification_service.create_notification(
                        user_id=task.assigned_to_id,
                        notification_type=NotificationType.TASK_REMINDER,
                        title=f"Aufgabe ueberfaellig: {task.title}",
                        message=f"Die Aufgabe '{task.title}' ist seit {overdue_text} ueberfaellig. Bitte bearbeiten Sie diese zeitnah.",
                        priority="high",
                        action_url=f"/documents/{task.document_id}/tasks/{task.id}",
                        metadata={
                            "task_id": str(task.id),
                            "document_id": str(task.document_id),
                            "overdue_hours": overdue_hours,
                        },
                    )

                    # Aktualisiere last_reminder_at
                    task.last_reminder_at = now
                    results["reminders_sent"] += 1

                except Exception as e:
                    results["errors"] += 1
                    logger.error(
                        "task_reminder_error",
                        task_id=str(task.id),
                        error=str(e),
                    )

            await db.commit()
            return results

    try:
        results = run_async(run_check())
        logger.info(
            "check_overdue_tasks_abgeschlossen",
            task_id=self.request.id,
            **results,
        )
        return results

    except Exception as e:
        logger.error(
            "check_overdue_tasks_fehler",
            task_id=self.request.id,
            error=str(e),
        )
        raise self.retry(exc=e)


@celery_app.task(
    bind=True,
    base=CPUTask,
    name="app.workers.tasks.collaboration_tasks.escalate_overdue_tasks",
    max_retries=2,
    default_retry_delay=120,
)
def escalate_overdue_tasks(
    self,
    escalation_threshold_hours: int = 48,
) -> Dict[str, Any]:
    """
    Celery Task zur Eskalation stark ueberfaelliger Aufgaben.

    Eskaliert Aufgaben die:
    - Laenger als escalation_threshold_hours ueberfaellig sind
    - Noch nicht eskaliert wurden
    - Nicht abgeschlossen/abgebrochen sind

    Benachrichtigt den Ersteller der Aufgabe und optional Manager.

    Args:
        escalation_threshold_hours: Stunden bis zur Eskalation (Default: 48)

    Returns:
        Dict mit Statistiken
    """
    logger.info(
        "escalate_overdue_tasks_gestartet",
        task_id=self.request.id,
        threshold_hours=escalation_threshold_hours,
    )

    async def run_escalation():
        from app.services.notification_service import NotificationService

        async with get_async_session_context() as db:
            now = utc_now()
            escalation_cutoff = now - timedelta(hours=escalation_threshold_hours)

            results = {
                "tasks_checked": 0,
                "tasks_escalated": 0,
                "notifications_sent": 0,
                "errors": 0,
            }

            # Finde stark ueberfaellige Aufgaben
            result = await db.execute(
                select(DocumentTask)
                .options(
                    selectinload(DocumentTask.assigned_to),
                    selectinload(DocumentTask.created_by),
                )
                .where(
                    and_(
                        DocumentTask.due_date <= escalation_cutoff,
                        DocumentTask.status.in_([
                            TaskStatus.OPEN.value,
                            TaskStatus.IN_PROGRESS.value,
                            TaskStatus.BLOCKED.value,
                        ]),
                        DocumentTask.escalated_at.is_(None),
                    )
                )
                .limit(200)
            )
            tasks_to_escalate = result.scalars().all()
            results["tasks_checked"] = len(tasks_to_escalate)

            notification_service = NotificationService(db)

            for task in tasks_to_escalate:
                try:
                    overdue_hours = int((now - task.due_date).total_seconds() / 3600)
                    overdue_days = overdue_hours // 24

                    # Markiere als eskaliert
                    task.escalated_at = now
                    results["tasks_escalated"] += 1

                    # Benachrichtige Ersteller
                    if task.created_by_id:
                        await notification_service.create_notification(
                            user_id=task.created_by_id,
                            notification_type=NotificationType.TASK_ESCALATED,
                            title=f"Aufgabe eskaliert: {task.title}",
                            message=f"Die Aufgabe '{task.title}' ist seit {overdue_days} Tagen ueberfaellig und wurde eskaliert.",
                            priority="urgent",
                            action_url=f"/documents/{task.document_id}/tasks/{task.id}",
                            metadata={
                                "task_id": str(task.id),
                                "document_id": str(task.document_id),
                                "assigned_to_id": str(task.assigned_to_id) if task.assigned_to_id else None,
                                "overdue_days": overdue_days,
                            },
                        )
                        results["notifications_sent"] += 1

                    # Benachrichtige auch Assignee falls unterschiedlich
                    if task.assigned_to_id and task.assigned_to_id != task.created_by_id:
                        await notification_service.create_notification(
                            user_id=task.assigned_to_id,
                            notification_type=NotificationType.TASK_ESCALATED,
                            title=f"Aufgabe eskaliert: {task.title}",
                            message=f"Die Ihnen zugewiesene Aufgabe '{task.title}' wurde aufgrund der Ueberfaelligkeit ({overdue_days} Tage) eskaliert.",
                            priority="urgent",
                            action_url=f"/documents/{task.document_id}/tasks/{task.id}",
                            metadata={
                                "task_id": str(task.id),
                                "document_id": str(task.document_id),
                                "overdue_days": overdue_days,
                            },
                        )
                        results["notifications_sent"] += 1

                    logger.warning(
                        "task_escalated",
                        task_id=str(task.id),
                        overdue_days=overdue_days,
                        assigned_to_id=str(task.assigned_to_id) if task.assigned_to_id else None,
                    )

                except Exception as e:
                    results["errors"] += 1
                    logger.error(
                        "task_escalation_error",
                        task_id=str(task.id),
                        error=str(e),
                    )

            await db.commit()
            return results

    try:
        results = run_async(run_escalation())
        logger.info(
            "escalate_overdue_tasks_abgeschlossen",
            task_id=self.request.id,
            **results,
        )
        return results

    except Exception as e:
        logger.error(
            "escalate_overdue_tasks_fehler",
            task_id=self.request.id,
            error=str(e),
        )
        raise self.retry(exc=e)


# =============================================================================
# CLEANUP TASKS
# =============================================================================


@celery_app.task(
    bind=True,
    base=CPUTask,
    name="app.workers.tasks.collaboration_tasks.cleanup_old_digest_entries",
    max_retries=2,
    default_retry_delay=60,
)
def cleanup_old_digest_entries(
    self,
    days_old: int = 7,
) -> Dict[str, Any]:
    """
    Celery Task zum Loeschen alter Digest-Queue-Eintraege.

    Loescht gesendete Eintraege die aelter als X Tage sind.
    Wird woechentlich ausgefuehrt.

    Args:
        days_old: Eintraege aelter als X Tage loeschen (Default: 7)

    Returns:
        Dict mit Anzahl geloeschter Eintraege
    """
    logger.info(
        "cleanup_old_digest_entries_gestartet",
        task_id=self.request.id,
        days_old=days_old,
    )

    async def run_cleanup():
        from app.services.collaboration.digest_service import DigestService

        async with get_async_session_context() as db:
            digest_service = DigestService(db)
            deleted_count = await digest_service.cleanup_old_digests(days_old=days_old)

            return {
                "deleted_count": deleted_count,
                "days_old": days_old,
            }

    try:
        results = run_async(run_cleanup())
        logger.info(
            "cleanup_old_digest_entries_abgeschlossen",
            task_id=self.request.id,
            **results,
        )
        return results

    except Exception as e:
        logger.error(
            "cleanup_old_digest_entries_fehler",
            task_id=self.request.id,
            error=str(e),
        )
        raise self.retry(exc=e)


@celery_app.task(
    bind=True,
    base=CPUTask,
    name="app.workers.tasks.collaboration_tasks.send_task_due_soon_reminders",
    max_retries=2,
    default_retry_delay=60,
)
def send_task_due_soon_reminders(
    self,
    hours_before: int = 24,
) -> Dict[str, Any]:
    """
    Celery Task fuer Erinnerungen an bald faellige Aufgaben.

    Sendet Erinnerungen an Bearbeiter wenn:
    - Aufgabe in weniger als hours_before faellig ist
    - Aufgabe noch nicht abgeschlossen
    - Noch keine "bald faellig" Erinnerung gesendet

    Wird alle 4 Stunden ausgefuehrt.

    Args:
        hours_before: Stunden vor Faelligkeit (Default: 24)

    Returns:
        Dict mit Statistiken
    """
    logger.info(
        "send_task_due_soon_reminders_gestartet",
        task_id=self.request.id,
        hours_before=hours_before,
    )

    async def run_reminders():
        from app.services.notification_service import NotificationService

        async with get_async_session_context() as db:
            now = utc_now()
            due_soon_cutoff = now + timedelta(hours=hours_before)

            results = {
                "tasks_checked": 0,
                "reminders_sent": 0,
                "errors": 0,
            }

            # Finde bald faellige Aufgaben
            result = await db.execute(
                select(DocumentTask)
                .options(selectinload(DocumentTask.assigned_to))
                .where(
                    and_(
                        DocumentTask.due_date > now,
                        DocumentTask.due_date <= due_soon_cutoff,
                        DocumentTask.status.in_([
                            TaskStatus.OPEN.value,
                            TaskStatus.IN_PROGRESS.value,
                        ]),
                        DocumentTask.reminder_sent.is_(False),
                    )
                )
                .limit(500)
            )
            due_soon_tasks = result.scalars().all()
            results["tasks_checked"] = len(due_soon_tasks)

            notification_service = NotificationService(db)

            for task in due_soon_tasks:
                try:
                    if not task.assigned_to_id:
                        continue

                    # Berechne verbleibende Zeit
                    hours_remaining = int((task.due_date - now).total_seconds() / 3600)
                    time_text = f"{hours_remaining} Stunden" if hours_remaining > 1 else "weniger als 1 Stunde"

                    await notification_service.create_notification(
                        user_id=task.assigned_to_id,
                        notification_type=NotificationType.TASK_REMINDER,
                        title=f"Aufgabe bald faellig: {task.title}",
                        message=f"Die Aufgabe '{task.title}' ist in {time_text} faellig.",
                        priority="normal",
                        action_url=f"/documents/{task.document_id}/tasks/{task.id}",
                        metadata={
                            "task_id": str(task.id),
                            "document_id": str(task.document_id),
                            "hours_remaining": hours_remaining,
                            "reminder_type": "due_soon",
                        },
                    )

                    task.reminder_sent = True
                    results["reminders_sent"] += 1

                except Exception as e:
                    results["errors"] += 1
                    logger.error(
                        "due_soon_reminder_error",
                        task_id=str(task.id),
                        error=str(e),
                    )

            await db.commit()
            return results

    try:
        results = run_async(run_reminders())
        logger.info(
            "send_task_due_soon_reminders_abgeschlossen",
            task_id=self.request.id,
            **results,
        )
        return results

    except Exception as e:
        logger.error(
            "send_task_due_soon_reminders_fehler",
            task_id=self.request.id,
            error=str(e),
        )
        raise self.retry(exc=e)


# =============================================================================
# COLLABORATION BEAT SCHEDULE (wird in celery_app.py importiert)
# =============================================================================

COLLABORATION_BEAT_SCHEDULE = {
    # Digest Processing
    "collaboration-hourly-digests": {
        "task": "app.workers.tasks.collaboration_tasks.process_hourly_digests",
        "schedule": 3600.0,  # Jede Stunde
    },
    "collaboration-daily-digests": {
        "task": "app.workers.tasks.collaboration_tasks.process_daily_digests",
        "schedule": {
            "hour": 8,
            "minute": 0,
        },  # Taeglich um 08:00 Uhr
    },
    "collaboration-weekly-digests": {
        "task": "app.workers.tasks.collaboration_tasks.process_weekly_digests",
        "schedule": {
            "day_of_week": 1,
            "hour": 8,
            "minute": 0,
        },  # Montag 08:00 Uhr
    },
    # Task Reminders
    "collaboration-overdue-check": {
        "task": "app.workers.tasks.collaboration_tasks.check_overdue_tasks",
        "schedule": 3600.0,  # Stuendlich
    },
    "collaboration-due-soon-reminders": {
        "task": "app.workers.tasks.collaboration_tasks.send_task_due_soon_reminders",
        "schedule": 14400.0,  # Alle 4 Stunden
    },
    # Escalation
    "collaboration-escalate-tasks": {
        "task": "app.workers.tasks.collaboration_tasks.escalate_overdue_tasks",
        "schedule": 14400.0,  # Alle 4 Stunden
        "kwargs": {"escalation_threshold_hours": 48},
    },
    # Cleanup
    "collaboration-cleanup-digests": {
        "task": "app.workers.tasks.collaboration_tasks.cleanup_old_digest_entries",
        "schedule": {
            "day_of_week": 0,
            "hour": 5,
            "minute": 0,
        },  # Sonntag 05:00 Uhr
        "kwargs": {"days_old": 7},
    },
}
