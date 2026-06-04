# -*- coding: utf-8 -*-
"""Celery Tasks für Workflow-Automation.

6 Tasks:
- execute_workflow_async: Async Workflow-Ausführung
- execute_workflow_step: Einzelschritt-Ausführung
- check_scheduled_workflows: Prüft fällige Cron-Workflows (jede Minute)
- cleanup_old_workflow_executions: Löscht alte Executions (täglich)
- process_delayed_step: Fortsetzung nach Delay
- generate_workflow_report: Wöchentlicher Bericht
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional
from uuid import UUID

import structlog
from celery import shared_task
from sqlalchemy import and_, delete, select

from app.core.safe_errors import safe_error_log
from app.workers.celery_app import celery_app
from app.core.safe_errors import safe_error_detail

logger = structlog.get_logger(__name__)


@shared_task(
    bind=True,
    name="app.workers.tasks.workflow_tasks.execute_workflow_async",
    max_retries=3,
    default_retry_delay=60,
    autoretry_for=(Exception,),
    acks_late=True,
)
def execute_workflow_async(
    self,
    workflow_id: str,
    user_id: str,
    document_id: Optional[str] = None,
    trigger_data: Optional[Dict[str, Any]] = None,
    initial_variables: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Führt einen Workflow asynchron aus.

    Args:
        workflow_id: Workflow-ID
        user_id: User-ID
        document_id: Optionale Dokument-ID
        trigger_data: Trigger-Daten
        initial_variables: Initiale Variablen

    Returns:
        Execution-Ergebnis
    """
    import asyncio
    from app.db.session import async_session_factory
    from app.services.workflow import (
        WorkflowExecutionService,
        WorkflowStepExecutor,
    )

    async def _execute() -> Dict[str, Any]:
        async with async_session_factory() as db:
            step_executor = WorkflowStepExecutor(db)
            execution_service = WorkflowExecutionService(db, step_executor)

            try:
                execution = await execution_service.start_execution(
                    workflow_id=UUID(workflow_id),
                    user_id=UUID(user_id),
                    document_id=UUID(document_id) if document_id else None,
                    trigger_data=trigger_data,
                    initial_variables=initial_variables,
                )

                return {
                    "success": True,
                    "execution_id": str(execution.id),
                    "status": execution.status,
                }

            except Exception as e:
                logger.exception(
                    "workflow_async_execution_error",
                    workflow_id=workflow_id,
                    **safe_error_log(e),
                )
                return {
                    "success": False,
                    "error": safe_error_detail(e, "Vorgang"),
                }

    return asyncio.run(_execute())


@shared_task(
    bind=True,
    name="app.workers.tasks.workflow_tasks.execute_workflow_step",
    max_retries=3,
    default_retry_delay=30,
    acks_late=True,
)
def execute_workflow_step(
    self,
    execution_id: str,
    step_id: str,
    context_data: Dict[str, Any],
) -> Dict[str, Any]:
    """Führt einen einzelnen Workflow-Step aus.

    Args:
        execution_id: Execution-ID
        step_id: Step-ID
        context_data: Kontext-Daten

    Returns:
        Step-Ergebnis
    """
    import asyncio
    from app.db.session import async_session_factory
    from app.db.models import WorkflowStep
    from app.services.workflow import (
        ExecutionContext,
        WorkflowStepExecutor,
    )

    async def _execute_step() -> Dict[str, Any]:
        async with async_session_factory() as db:
            # Step laden
            query = select(WorkflowStep).where(WorkflowStep.id == UUID(step_id))
            result = await db.execute(query)
            step = result.scalar_one_or_none()

            if not step:
                return {"success": False, "error": "Step nicht gefunden"}

            # Context erstellen
            context = ExecutionContext(
                execution_id=UUID(execution_id),
                workflow_id=step.workflow_id,
                user_id=UUID(context_data.get("user_id", "")),
                document_id=UUID(context_data["document_id"]) if context_data.get("document_id") else None,
                document_data=context_data.get("document_data"),
                trigger_data=context_data.get("trigger_data", {}),
                variables=context_data.get("variables", {}),
                step_outputs=context_data.get("step_outputs", {}),
                data=context_data.get("data", {}),
            )

            # Step ausführen
            executor = WorkflowStepExecutor(db)
            result = await executor.execute_step(step, context)

            return {
                "success": result.success,
                "output": result.output,
                "error": result.error,
                "branch_result": result.branch_result,
            }

    return asyncio.run(_execute_step())


@shared_task(
    bind=True,
    name="app.workers.tasks.workflow_tasks.check_scheduled_workflows",
    acks_late=True,
)
def check_scheduled_workflows(self) -> Dict[str, Any]:
    """Prüft und startet fällige Schedule-Workflows.

    Wird jede Minute von Celery Beat aufgerufen.

    Returns:
        Anzahl gestarteter Workflows
    """
    import asyncio
    from app.db.session import async_session_factory
    from app.services.workflow import (
        WorkflowExecutionService,
        WorkflowStepExecutor,
        WorkflowTriggerService,
    )

    async def _check_scheduled() -> Dict[str, Any]:
        async with async_session_factory() as db:
            step_executor = WorkflowStepExecutor(db)
            execution_service = WorkflowExecutionService(db, step_executor)
            trigger_service = WorkflowTriggerService(db, execution_service)

            try:
                execution_ids = await trigger_service.check_scheduled_workflows()

                logger.info(
                    "scheduled_workflows_checked",
                    started_count=len(execution_ids),
                )

                return {
                    "success": True,
                    "started_count": len(execution_ids),
                    "execution_ids": [str(eid) for eid in execution_ids],
                }

            except Exception as e:
                logger.exception(
                    "scheduled_workflows_check_error",
                    **safe_error_log(e),
                )
                return {
                    "success": False,
                    "error": safe_error_detail(e, "Vorgang"),
                }

    return asyncio.run(_check_scheduled())


@shared_task(
    bind=True,
    name="app.workers.tasks.workflow_tasks.cleanup_old_workflow_executions",
    acks_late=True,
)
def cleanup_old_workflow_executions(
    self,
    retention_days: int = 90,
) -> Dict[str, Any]:
    """Löscht alte Workflow-Executions.

    Args:
        retention_days: Aufbewahrungsfrist in Tagen

    Returns:
        Anzahl gelöschter Executions
    """
    import asyncio
    from app.db.session import async_session_factory
    from app.db.models import WorkflowExecution, WorkflowStepExecution

    async def _cleanup() -> Dict[str, Any]:
        async with async_session_factory() as db:
            try:
                cutoff_date = datetime.now(timezone.utc) - timedelta(days=retention_days)

                # Alte Executions finden
                query = select(WorkflowExecution.id).where(
                    and_(
                        WorkflowExecution.completed_at.isnot(None),
                        WorkflowExecution.completed_at < cutoff_date,
                    )
                )

                result = await db.execute(query)
                old_execution_ids = [row[0] for row in result.all()]

                if not old_execution_ids:
                    return {"success": True, "deleted_count": 0}

                # Step-Executions löschen
                step_delete = delete(WorkflowStepExecution).where(
                    WorkflowStepExecution.execution_id.in_(old_execution_ids)
                )
                await db.execute(step_delete)

                # Executions löschen
                exec_delete = delete(WorkflowExecution).where(
                    WorkflowExecution.id.in_(old_execution_ids)
                )
                result = await db.execute(exec_delete)

                await db.commit()

                deleted_count = result.rowcount

                logger.info(
                    "workflow_executions_cleaned_up",
                    deleted_count=deleted_count,
                    retention_days=retention_days,
                )

                return {
                    "success": True,
                    "deleted_count": deleted_count,
                    "retention_days": retention_days,
                }

            except Exception as e:
                logger.exception(
                    "workflow_cleanup_error",
                    **safe_error_log(e),
                )
                await db.rollback()
                return {
                    "success": False,
                    "error": safe_error_detail(e, "Vorgang"),
                }

    return asyncio.run(_cleanup())


@shared_task(
    bind=True,
    name="app.workers.tasks.workflow_tasks.process_delayed_step",
    acks_late=True,
)
def process_delayed_step(
    self,
    execution_id: str,
    step_id: str,
    delay_seconds: int,
    context_data: Dict[str, Any],
) -> Dict[str, Any]:
    """Fortsetzt eine Workflow-Ausführung nach einer Verzögerung.

    Args:
        execution_id: Execution-ID
        step_id: Step-ID der nach dem Delay fortgesetzt werden soll
        delay_seconds: Verzögerung in Sekunden
        context_data: Kontext-Daten

    Returns:
        Execution-Ergebnis
    """
    import asyncio
    import time
    from app.db.session import async_session_factory
    from app.db.models import WorkflowExecution
    from app.services.workflow import (
        WorkflowExecutionService,
        WorkflowStepExecutor,
    )

    # Delay abwarten
    if delay_seconds > 0:
        time.sleep(delay_seconds)

    async def _continue_execution() -> Dict[str, Any]:
        async with async_session_factory() as db:
            # Execution-Status prüfen
            query = select(WorkflowExecution).where(
                WorkflowExecution.id == UUID(execution_id)
            )
            result = await db.execute(query)
            execution = result.scalar_one_or_none()

            if not execution:
                return {"success": False, "error": "Execution nicht gefunden"}

            if execution.status in ("cancelled", "failed"):
                return {
                    "success": False,
                    "error": f"Execution ist {execution.status}",
                }

            # Execution fortsetzen
            step_executor = WorkflowStepExecutor(db)
            execution_service = WorkflowExecutionService(db, step_executor)

            success = await execution_service.resume_execution(
                execution_id=UUID(execution_id),
                user_id=execution.user_id,
            )

            return {
                "success": success,
                "execution_id": execution_id,
            }

    return asyncio.run(_continue_execution())


@shared_task(
    bind=True,
    name="app.workers.tasks.workflow_tasks.generate_workflow_report",
    acks_late=True,
)
def generate_workflow_report(self) -> Dict[str, Any]:
    """Generiert einen wöchentlichen Workflow-Bericht.

    Returns:
        Berichts-Daten
    """
    import asyncio
    from app.db.session import async_session_factory
    from app.db.models import Workflow, WorkflowExecution
    from sqlalchemy import func

    async def _generate_report() -> Dict[str, Any]:
        async with async_session_factory() as db:
            try:
                # Zeitraum: Letzte 7 Tage
                end_date = datetime.now(timezone.utc)
                start_date = end_date - timedelta(days=7)

                # Gesamt-Statistiken
                total_query = select(
                    func.count(WorkflowExecution.id).label("total"),
                    func.sum(
                        func.cast(WorkflowExecution.status == "completed", Integer)
                    ).label("completed"),
                    func.sum(
                        func.cast(WorkflowExecution.status == "failed", Integer)
                    ).label("failed"),
                ).where(
                    and_(
                        WorkflowExecution.started_at >= start_date,
                        WorkflowExecution.started_at <= end_date,
                    )
                )

                from sqlalchemy import Integer

                result = await db.execute(total_query)
                totals = result.one()

                # Top Workflows
                top_query = (
                    select(
                        Workflow.id,
                        Workflow.name,
                        func.count(WorkflowExecution.id).label("execution_count"),
                    )
                    .join(WorkflowExecution, WorkflowExecution.workflow_id == Workflow.id)
                    .where(
                        and_(
                            WorkflowExecution.started_at >= start_date,
                            WorkflowExecution.started_at <= end_date,
                        )
                    )
                    .group_by(Workflow.id, Workflow.name)
                    .order_by(func.count(WorkflowExecution.id).desc())
                    .limit(10)
                )

                top_result = await db.execute(top_query)
                top_workflows = [
                    {
                        "id": str(row.id),
                        "name": row.name,
                        "execution_count": row.execution_count,
                    }
                    for row in top_result.all()
                ]

                # Fehler-Analyse
                error_query = (
                    select(
                        WorkflowExecution.error_message,
                        func.count(WorkflowExecution.id).label("count"),
                    )
                    .where(
                        and_(
                            WorkflowExecution.status == "failed",
                            WorkflowExecution.started_at >= start_date,
                            WorkflowExecution.started_at <= end_date,
                            WorkflowExecution.error_message.isnot(None),
                        )
                    )
                    .group_by(WorkflowExecution.error_message)
                    .order_by(func.count(WorkflowExecution.id).desc())
                    .limit(5)
                )

                error_result = await db.execute(error_query)
                top_errors = [
                    {
                        "error": row.error_message[:100] if row.error_message else "Unknown",
                        "count": row.count,
                    }
                    for row in error_result.all()
                ]

                report = {
                    "success": True,
                    "period": {
                        "start": start_date.isoformat(),
                        "end": end_date.isoformat(),
                    },
                    "summary": {
                        "total_executions": totals.total or 0,
                        "completed": totals.completed or 0,
                        "failed": totals.failed or 0,
                        "success_rate": (
                            (totals.completed / totals.total * 100)
                            if totals.total
                            else 0
                        ),
                    },
                    "top_workflows": top_workflows,
                    "top_errors": top_errors,
                }

                logger.info(
                    "workflow_report_generated",
                    total_executions=totals.total or 0,
                    success_rate=report["summary"]["success_rate"],
                )

                return report

            except Exception as e:
                logger.exception(
                    "workflow_report_error",
                    **safe_error_log(e),
                )
                return {
                    "success": False,
                    "error": safe_error_detail(e, "Vorgang"),
                }

    return asyncio.run(_generate_report())


# =============================================================================
# Document Event Handlers
# =============================================================================


@shared_task(
    bind=True,
    name="app.workers.tasks.workflow_tasks.on_document_created",
    acks_late=True,
)
def on_document_created(
    self,
    document_id: str,
    user_id: str,
) -> Dict[str, Any]:
    """Wird bei Dokument-Erstellung aufgerufen.

    Args:
        document_id: Dokument-ID
        user_id: User-ID

    Returns:
        Gestartete Executions
    """
    import asyncio
    from app.db.session import async_session_factory
    from app.services.workflow import (
        WorkflowExecutionService,
        WorkflowStepExecutor,
        WorkflowTriggerService,
    )

    async def _trigger() -> Dict[str, Any]:
        async with async_session_factory() as db:
            step_executor = WorkflowStepExecutor(db)
            execution_service = WorkflowExecutionService(db, step_executor)
            trigger_service = WorkflowTriggerService(db, execution_service)

            try:
                execution_ids = await trigger_service.on_document_created(
                    document_id=UUID(document_id),
                    user_id=UUID(user_id),
                )

                return {
                    "success": True,
                    "triggered_count": len(execution_ids),
                    "execution_ids": [str(eid) for eid in execution_ids],
                }

            except Exception as e:
                logger.exception(
                    "document_created_trigger_error",
                    document_id=document_id,
                    **safe_error_log(e),
                )
                return {
                    "success": False,
                    "error": safe_error_detail(e, "Vorgang"),
                }

    return asyncio.run(_trigger())


@shared_task(
    bind=True,
    name="app.workers.tasks.workflow_tasks.on_document_processed",
    acks_late=True,
)
def on_document_processed(
    self,
    document_id: str,
    user_id: str,
    ocr_result: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Wird nach OCR-Verarbeitung aufgerufen.

    Args:
        document_id: Dokument-ID
        user_id: User-ID
        ocr_result: OCR-Ergebnis

    Returns:
        Gestartete Executions
    """
    import asyncio
    from app.db.session import async_session_factory
    from app.services.workflow import (
        WorkflowExecutionService,
        WorkflowStepExecutor,
        WorkflowTriggerService,
    )

    async def _trigger() -> Dict[str, Any]:
        async with async_session_factory() as db:
            step_executor = WorkflowStepExecutor(db)
            execution_service = WorkflowExecutionService(db, step_executor)
            trigger_service = WorkflowTriggerService(db, execution_service)

            try:
                execution_ids = await trigger_service.on_document_processed(
                    document_id=UUID(document_id),
                    user_id=UUID(user_id),
                    ocr_result=ocr_result,
                )

                return {
                    "success": True,
                    "triggered_count": len(execution_ids),
                    "execution_ids": [str(eid) for eid in execution_ids],
                }

            except Exception as e:
                logger.exception(
                    "document_processed_trigger_error",
                    document_id=document_id,
                    **safe_error_log(e),
                )
                return {
                    "success": False,
                    "error": safe_error_detail(e, "Vorgang"),
                }

    return asyncio.run(_trigger())


@shared_task(
    bind=True,
    name="app.workers.tasks.workflow_tasks.on_document_failed",
    acks_late=True,
)
def on_document_failed(
    self,
    document_id: str,
    user_id: str,
    error: str,
) -> Dict[str, Any]:
    """Wird bei Dokument-Fehlern aufgerufen.

    Args:
        document_id: Dokument-ID
        user_id: User-ID
        error: Fehlermeldung

    Returns:
        Gestartete Executions
    """
    import asyncio
    from app.db.session import async_session_factory
    from app.services.workflow import (
        WorkflowExecutionService,
        WorkflowStepExecutor,
        WorkflowTriggerService,
    )

    async def _trigger() -> Dict[str, Any]:
        async with async_session_factory() as db:
            step_executor = WorkflowStepExecutor(db)
            execution_service = WorkflowExecutionService(db, step_executor)
            trigger_service = WorkflowTriggerService(db, execution_service)

            try:
                execution_ids = await trigger_service.on_document_failed(
                    document_id=UUID(document_id),
                    user_id=UUID(user_id),
                    error=error,
                )

                return {
                    "success": True,
                    "triggered_count": len(execution_ids),
                    "execution_ids": [str(eid) for eid in execution_ids],
                }

            except Exception as e:
                logger.exception(
                    "document_failed_trigger_error",
                    document_id=document_id,
                    **safe_error_log(e),
                )
                return {
                    "success": False,
                    "error": safe_error_detail(e, "Vorgang"),
                }

    return asyncio.run(_trigger())


# =============================================================================
# Celery Beat Schedule
# =============================================================================

# Diese Tasks werden in der Celery Beat Konfiguration registriert:
#
# check_scheduled_workflows: Jede Minute
# cleanup_old_workflow_executions: Täglich 03:00
# generate_workflow_report: Montag 07:00
