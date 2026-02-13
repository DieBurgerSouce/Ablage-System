"""BPMN Celery Tasks.

Hintergrund-Tasks fuer die BPMN Process Engine:
- Timer-Verarbeitung (regelmaessig)
- Task-Eskalation (regelmaessig)
- Service Task Ausfuehrung (on-demand)
- Prozess-Cleanup (taeglich)

Beat Schedule (in celery_config.py hinzufuegen):
    'bpmn.process_due_timers': {
        'task': 'app.workers.bpmn_tasks.process_due_timers',
        'schedule': 60.0,  # Jede Minute
    },
    'bpmn.escalate_overdue_tasks': {
        'task': 'app.workers.bpmn_tasks.escalate_overdue_tasks',
        'schedule': crontab(minute='*/15'),  # Alle 15 Minuten
    },
    'bpmn.cleanup_old_timers': {
        'task': 'app.workers.bpmn_tasks.cleanup_old_timers',
        'schedule': crontab(hour=3, minute=0),  # Taeglich 03:00
    },
"""

from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any
from uuid import UUID
import structlog

from celery import shared_task
from sqlalchemy import select, and_

from app.workers.celery_app import celery_app
from app.db.session import async_session_maker
from app.db.bpmn_models.bpmn import (
    ProcessTask,
    ProcessInstance,
    TaskStatus,
    ProcessStatus,
)
from app.core.safe_errors import safe_error_detail, safe_error_log

logger = structlog.get_logger(__name__)


@celery_app.task(
    name="app.workers.bpmn_tasks.process_due_timers",
    bind=True,
    max_retries=3,
    default_retry_delay=30,
    queue="maintenance"
)
def process_due_timers(self, company_id: Optional[str] = None):
    """Verarbeitet alle faelligen Timer-Jobs.

    Wird regelmaessig von Celery Beat aufgerufen (z.B. jede Minute).

    Args:
        company_id: Optional Filter nach Mandant (fuer alle wenn None)
    """
    import asyncio

    async def _process():
        async with async_session_maker() as db:
            from app.services.bpmn import get_timer_service

            service = get_timer_service(db)

            cid = UUID(company_id) if company_id else None
            executed = await service.execute_due_timers(
                company_id=cid,
                batch_size=50
            )

            await db.commit()

            logger.info(
                "due_timers_processed",
                executed=executed,
                company_id=company_id
            )

            return executed

    try:
        return asyncio.get_event_loop().run_until_complete(_process())
    except RuntimeError:
        # Kein Event Loop vorhanden
        return asyncio.run(_process())


@celery_app.task(
    name="app.workers.bpmn_tasks.escalate_overdue_tasks",
    bind=True,
    max_retries=2,
    queue="maintenance"
)
def escalate_overdue_tasks(self, company_id: Optional[str] = None):
    """Eskaliert ueberfaellige Tasks.

    Wird regelmaessig aufgerufen (z.B. alle 15 Minuten).
    Erhoeht Eskalationsstufe und benachrichtigt ggf.

    Args:
        company_id: Optional Filter nach Mandant
    """
    import asyncio

    async def _escalate():
        async with async_session_maker() as db:
            from app.services.bpmn import get_task_service

            service = get_task_service(db)

            # Ueberfaellige Tasks laden
            cid = UUID(company_id) if company_id else None

            if cid:
                tasks = await service.get_overdue_tasks(cid)
            else:
                # Alle Mandanten - in Produktion besser aufteilen
                tasks = []

            escalated = 0
            for task in tasks:
                try:
                    # Nur eskalieren wenn noch nicht eskaliert oder
                    # letzte Eskalation > 24h her
                    if task.escalated_at:
                        hours_since = (
                            datetime.now(timezone.utc) - task.escalated_at
                        ).total_seconds() / 3600
                        if hours_since < 24:
                            continue

                    await service.escalate(
                        task_id=task.id,
                        company_id=task.company_id,
                        reason="Automatische Eskalation - Task ueberfaellig"
                    )
                    escalated += 1

                except Exception as e:
                    logger.error(
                        "task_escalation_failed",
                        task_id=str(task.id),
                        **safe_error_log(e, context="BPMN-Task")
                    )

            await db.commit()

            logger.info(
                "overdue_tasks_escalated",
                escalated=escalated,
                total_overdue=len(tasks)
            )

            return escalated

    try:
        return asyncio.get_event_loop().run_until_complete(_escalate())
    except RuntimeError:
        return asyncio.run(_escalate())


@celery_app.task(
    name="app.workers.bpmn_tasks.cleanup_old_timers",
    bind=True,
    queue="maintenance"
)
def cleanup_old_timers(self, days_old: int = 30):
    """Entfernt alte, inaktive Timer.

    Wird taeglich aufgerufen.

    Args:
        days_old: Alter in Tagen (Default: 30)
    """
    import asyncio

    async def _cleanup():
        async with async_session_maker() as db:
            from app.services.bpmn import get_timer_service

            service = get_timer_service(db)

            deleted = await service.cleanup_old_timers(days_old=days_old)
            await db.commit()

            logger.info(
                "old_timers_cleaned",
                deleted=deleted,
                days_old=days_old
            )

            return deleted

    try:
        return asyncio.get_event_loop().run_until_complete(_cleanup())
    except RuntimeError:
        return asyncio.run(_cleanup())


@celery_app.task(
    name="app.workers.bpmn_tasks.execute_service_task",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    queue="default"
)
def execute_service_task(
    self,
    instance_id: str,
    element_id: str,
    variables: Dict[str, Any],
    implementation: str,
    company_id: str
):
    """Fuehrt einen Service Task aus.

    Wird asynchron aufgerufen wenn ein Service Task im Prozess aktiviert wird.

    Args:
        instance_id: Prozess-Instanz ID
        element_id: BPMN Element ID
        variables: Prozess-Variablen
        implementation: Implementation (z.B. 'python:module.function')
        company_id: Mandant
    """
    import asyncio

    logger.info(
        "executing_service_task",
        instance_id=instance_id,
        element_id=element_id,
        implementation=implementation
    )

    async def _execute():
        async with async_session_maker() as db:
            from app.services.bpmn import get_process_execution_service

            result_variables = {}

            # Python-Implementierung ausfuehren
            if implementation.startswith("python:"):
                module_func = implementation[7:]
                try:
                    # SECURITY: Use safe module loader with whitelist
                    # instead of unrestricted importlib.import_module
                    # Prevents CWE-470 (Externally Controlled Reference)
                    from app.core.security.safe_module_loader import (
                        safe_load_function,
                        ModuleNotAllowedError,
                        FunctionNotAllowedError,
                    )

                    try:
                        func = safe_load_function(module_func)
                    except (ModuleNotAllowedError, FunctionNotAllowedError) as e:
                        logger.error(
                            "service_task_security_violation",
                            implementation=implementation,
                            **safe_error_log(e, context="BPMN-Task"),
                        )
                        raise ValueError(
                            f"Funktion nicht erlaubt: {module_func}"
                        ) from e

                    # Funktion aufrufen (sync oder async)
                    if asyncio.iscoroutinefunction(func):
                        result = await func(
                            instance_id=instance_id,
                            variables=variables
                        )
                    else:
                        result = func(
                            instance_id=instance_id,
                            variables=variables
                        )

                    if isinstance(result, dict):
                        result_variables = result

                except (ModuleNotAllowedError, FunctionNotAllowedError):
                    # Security violations should not be retried
                    raise
                except Exception as e:
                    logger.error(
                        "service_task_implementation_failed",
                        implementation=implementation,
                        **safe_error_log(e, context="BPMN-Task")
                    )
                    raise self.retry(exc=e)

            # Prozess fortsetzen
            execution_service = get_process_execution_service(db)
            await execution_service.continue_after_task(
                instance_id=UUID(instance_id),
                element_id=element_id,
                company_id=UUID(company_id),
                result_variables=result_variables
            )

            await db.commit()

            logger.info(
                "service_task_completed",
                instance_id=instance_id,
                element_id=element_id
            )

    try:
        asyncio.get_event_loop().run_until_complete(_execute())
    except RuntimeError:
        asyncio.run(_execute())


@celery_app.task(
    name="app.workers.bpmn_tasks.check_process_timeouts",
    bind=True,
    queue="maintenance"
)
def check_process_timeouts(self, timeout_hours: int = 24):
    """Prueft auf haengende Prozesse.

    Markiert Prozesse als FAILED wenn sie zu lange laufen.

    Args:
        timeout_hours: Stunden bis Timeout (Default: 24)
    """
    import asyncio

    async def _check():
        async with async_session_maker() as db:
            cutoff = datetime.now(timezone.utc) - timedelta(hours=timeout_hours)

            # Haengende Prozesse finden
            query = select(ProcessInstance).where(
                and_(
                    ProcessInstance.status == ProcessStatus.RUNNING,
                    ProcessInstance.started_at < cutoff,
                    ProcessInstance.current_elements == []  # Keine aktiven Elemente
                )
            )

            result = await db.execute(query)
            hanging_processes = list(result.scalars().all())

            failed = 0
            for process in hanging_processes:
                process.status = ProcessStatus.FAILED
                process.ended_at = datetime.now(timezone.utc)
                failed += 1

                logger.warning(
                    "process_timeout",
                    instance_id=str(process.id),
                    started_at=str(process.started_at)
                )

            await db.commit()

            logger.info(
                "process_timeouts_checked",
                failed=failed
            )

            return failed

    try:
        return asyncio.get_event_loop().run_until_complete(_check())
    except RuntimeError:
        return asyncio.run(_check())


@celery_app.task(
    name="app.workers.bpmn_tasks.send_task_reminder",
    bind=True,
    queue="notification"
)
def send_task_reminder(
    self,
    task_id: str,
    company_id: str
):
    """Sendet Erinnerung fuer einen Task.

    Wird von Timer oder Scheduler aufgerufen.

    Args:
        task_id: Task ID
        company_id: Mandant
    """
    import asyncio

    async def _send():
        async with async_session_maker() as db:
            from app.services.bpmn import get_task_service

            service = get_task_service(db)
            task = await service.get_task(UUID(task_id), UUID(company_id))

            if not task:
                logger.warning(
                    "task_not_found_for_reminder",
                    task_id=task_id
                )
                return

            if task.status in (TaskStatus.COMPLETED, TaskStatus.SKIPPED):
                logger.info(
                    "task_already_completed_skipping_reminder",
                    task_id=task_id
                )
                return

            # Send notification via NotificationService
            if task.assignee_id:
                from app.services.notification_service import get_notification_service

                notification_service = get_notification_service()
                await notification_service.notify(
                    notification_type="bpmn_task_reminder",
                    context={
                        "task_name": task.element_name or "Unbenannte Aufgabe",
                        "task_id": task_id,
                        "process_instance_id": str(task.process_instance_id),
                    },
                    user_id=str(task.assignee_id),
                    priority="normal",
                )

                logger.info(
                    "task_reminder_sent",
                    task_id=task_id,
                    assignee_id=str(task.assignee_id),
                    notification_sent=True,
                )
            else:
                logger.info(
                    "task_reminder_skipped_no_assignee",
                    task_id=task_id,
                )

    try:
        asyncio.get_event_loop().run_until_complete(_send())
    except RuntimeError:
        asyncio.run(_send())


