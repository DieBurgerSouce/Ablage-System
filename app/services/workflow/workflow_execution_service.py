# -*- coding: utf-8 -*-
"""Workflow Execution Service.

Verwaltet die Ausfuehrung von Workflows.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, TYPE_CHECKING
from uuid import UUID, uuid4

import structlog
from sqlalchemy import and_, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import (
    Document,
    Workflow,
    WorkflowExecution,
    WorkflowStep,
    WorkflowStepExecution,
)
from app.services.workflow.condition_evaluator import ConditionEvaluator
from app.core.safe_errors import safe_error_log, safe_error_detail

if TYPE_CHECKING:
    from app.services.workflow.workflow_step_executor import WorkflowStepExecutor

logger = structlog.get_logger(__name__)


class ExecutionStatus(str, Enum):
    """Status einer Workflow-Ausfuehrung."""

    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMEOUT = "timeout"


@dataclass
class ExecutionContext:
    """Kontext fuer Workflow-Ausfuehrung.

    Enthaelt alle Daten, die waehrend der Ausfuehrung verfuegbar sind.
    """

    execution_id: UUID
    workflow_id: UUID
    user_id: UUID
    company_id: Optional[UUID] = None  # SECURITY: Multi-Tenant Isolation
    document_id: Optional[UUID] = None
    document_data: Optional[Dict[str, Any]] = None
    trigger_data: Optional[Dict[str, Any]] = None
    variables: Dict[str, Any] = field(default_factory=dict)
    step_outputs: Dict[str, Any] = field(default_factory=dict)
    data: Dict[str, Any] = field(default_factory=dict)
    current_step_index: int = 0
    is_paused: bool = False
    error: Optional[str] = None


class WorkflowExecutionService:
    """Service fuer Workflow-Ausfuehrung.

    Verwaltet:
    - Workflow starten/stoppen
    - Execution Lifecycle
    - Step-Orchestrierung
    - Pause/Resume
    - Timeout-Handling
    """

    def __init__(
        self,
        db: AsyncSession,
        step_executor: Optional["WorkflowStepExecutor"] = None,
    ) -> None:
        """Initialisiert den WorkflowExecutionService.

        Args:
            db: AsyncSession fuer Datenbankoperationen
            step_executor: WorkflowStepExecutor fuer Step-Ausfuehrung
        """
        self.db = db
        self.step_executor = step_executor
        self.condition_evaluator = ConditionEvaluator()

    def set_step_executor(self, executor: "WorkflowStepExecutor") -> None:
        """Setzt den Step-Executor (fuer zirkulaere Abhaengigkeiten).

        Args:
            executor: WorkflowStepExecutor
        """
        self.step_executor = executor

    # =========================================================================
    # Execution Start/Stop
    # =========================================================================

    async def start_execution(
        self,
        workflow_id: UUID,
        user_id: UUID,
        company_id: Optional[UUID] = None,
        document_id: Optional[UUID] = None,
        trigger_data: Optional[Dict[str, Any]] = None,
        initial_variables: Optional[Dict[str, Any]] = None,
    ) -> WorkflowExecution:
        """Startet eine Workflow-Ausfuehrung.

        SECURITY: Wenn company_id angegeben wird, MUSS der Workflow zu dieser
        Company gehoeren (Multi-Tenant Isolation).

        Args:
            workflow_id: Workflow-ID
            user_id: User-ID
            company_id: Company-ID fuer Multi-Tenant Validierung (empfohlen)
            document_id: Optionale Dokument-ID
            trigger_data: Trigger-Daten
            initial_variables: Initiale Variablen

        Returns:
            WorkflowExecution

        Raises:
            ValueError: Wenn Workflow nicht gefunden, nicht aktiv, oder
                       company_id nicht matcht (Cross-Tenant Zugriff)
        """
        # Workflow laden
        query = (
            select(Workflow)
            .where(Workflow.id == workflow_id)
            .options(selectinload(Workflow.steps))
        )
        result = await self.db.execute(query)
        workflow = result.scalar_one_or_none()

        if not workflow:
            raise ValueError(f"Workflow {workflow_id} nicht gefunden")

        # SECURITY: Multi-Tenant Isolation - company_id Validierung
        if company_id and workflow.company_id and workflow.company_id != company_id:
            logger.warning(
                "cross_tenant_workflow_execution_blocked",
                workflow_id=str(workflow_id),
                workflow_company_id=str(workflow.company_id),
                requested_company_id=str(company_id),
                user_id=str(user_id),
            )
            raise ValueError(f"Workflow {workflow_id} nicht gefunden")

        if not workflow.is_active:
            raise ValueError(f"Workflow {workflow_id} ist nicht aktiv")

        # Concurrent Executions pruefen
        running_count = await self._count_running_executions(workflow_id)
        if running_count >= workflow.max_concurrent_executions:
            raise ValueError(
                f"Max parallele Ausfuehrungen erreicht ({workflow.max_concurrent_executions})"
            )

        # Dokument-Daten laden falls vorhanden
        document_data = None
        if document_id:
            document_data = await self._load_document_data(document_id)

        # Execution erstellen
        execution = WorkflowExecution(
            id=uuid4(),
            workflow_id=workflow_id,
            triggered_by_id=user_id,
            document_id=document_id,
            trigger_type="manual",
            status=ExecutionStatus.RUNNING.value,
            trigger_data=trigger_data or {},
            variables={**(workflow.variables or {}), **(initial_variables or {})},
            started_at=datetime.now(timezone.utc),
            progress_percent=0,
        )

        self.db.add(execution)

        # Workflow-Statistik aktualisieren
        workflow.execution_count = (workflow.execution_count or 0) + 1
        workflow.last_executed_at = datetime.now(timezone.utc)

        await self.db.commit()
        await self.db.refresh(execution)

        logger.info(
            "workflow_execution_started",
            execution_id=str(execution.id),
            workflow_id=str(workflow_id),
            workflow_name=workflow.name,
            document_id=str(document_id) if document_id else None,
        )

        # Context erstellen - SECURITY: company_id fuer Multi-Tenant Isolation im StepExecutor
        context = ExecutionContext(
            execution_id=execution.id,
            workflow_id=workflow_id,
            user_id=user_id,
            company_id=workflow.company_id,  # SECURITY: company_id aus Workflow
            document_id=document_id,
            document_data=document_data,
            trigger_data=trigger_data or {},
            variables=execution.variables or {},
        )

        # Ausfuehrung starten (async)
        asyncio.create_task(
            self._execute_workflow(workflow, execution, context)
        )

        return execution

    async def _execute_workflow(
        self,
        workflow: Workflow,
        execution: WorkflowExecution,
        context: ExecutionContext,
    ) -> None:
        """Fuehrt den Workflow aus.

        Args:
            workflow: Workflow
            execution: WorkflowExecution
            context: ExecutionContext
        """
        try:
            # Steps sortieren
            steps = sorted(workflow.steps, key=lambda s: s.step_order)

            if not steps:
                # Keine Steps - direkt abschliessen
                await self._complete_execution(execution, context)
                return

            total_steps = len(steps)

            # While-Loop fuer Branch-Navigation
            current_index = 0
            while current_index < total_steps:
                step = steps[current_index]

                # Abbruch pruefen
                if context.is_paused:
                    await self._pause_execution(execution, context, step.id)
                    return

                # Execution-Status pruefen
                execution = await self._refresh_execution(execution.id)
                if execution.status in (
                    ExecutionStatus.CANCELLED.value,
                    ExecutionStatus.TIMEOUT.value,
                ):
                    logger.info(
                        "workflow_execution_aborted",
                        execution_id=str(execution.id),
                        status=execution.status,
                    )
                    return

                # Progress aktualisieren
                progress = int((current_index / total_steps) * 100)
                await self._update_progress(execution.id, progress, step.id)

                # Step ausfuehren
                step_result = await self._execute_step(step, context)

                if not step_result.success:
                    # Retry-Logik
                    if step.retry_on_failure and step_result.retry_count < step.max_retries:
                        # Retry
                        step_result = await self._retry_step(step, context, step_result.retry_count + 1)

                    if not step_result.success:
                        # Endgueltig fehlgeschlagen
                        await self._fail_execution(execution, context, step_result.error)
                        return

                # Step-Output speichern
                if step.step_name:
                    context.step_outputs[step.step_name] = step_result.output

                # Branch-Handling
                if step.step_type == "branch":
                    branch_result = step_result.output.get("branch")
                    if branch_result:
                        # Branch-Navigation: Ziel-Step finden
                        target_step_id = branch_result.get("target_step_id")
                        target_step_name = branch_result.get("target_step_name")
                        target_step_order = branch_result.get("target_step_order")

                        target_index: Optional[int] = None

                        # Suche nach ID
                        if target_step_id:
                            target_uuid = UUID(target_step_id) if isinstance(target_step_id, str) else target_step_id
                            for idx, s in enumerate(steps):
                                if s.id == target_uuid:
                                    target_index = idx
                                    break

                        # Suche nach Name
                        elif target_step_name:
                            for idx, s in enumerate(steps):
                                if s.name == target_step_name:
                                    target_index = idx
                                    break

                        # Suche nach Order
                        elif target_step_order is not None:
                            for idx, s in enumerate(steps):
                                if s.step_order == target_step_order:
                                    target_index = idx
                                    break

                        if target_index is not None:
                            logger.info(
                                "workflow_branch_navigation",
                                execution_id=str(execution.id),
                                from_step=step.name,
                                to_step=steps[target_index].name,
                            )
                            current_index = target_index
                            continue

                # Normaler Fortschritt
                current_index += 1

            # Erfolgreich abgeschlossen
            await self._complete_execution(execution, context)

        except asyncio.CancelledError:
            logger.info(
                "workflow_execution_cancelled",
                execution_id=str(execution.id),
            )
            await self._cancel_execution(execution)

        except Exception as e:
            logger.exception(
                "workflow_execution_error",
                execution_id=str(execution.id),
                **safe_error_log(e),
            )
            await self._fail_execution(execution, context, str(e))

    async def _execute_step(
        self,
        step: WorkflowStep,
        context: ExecutionContext,
    ) -> "StepResult":
        """Fuehrt einen einzelnen Step aus.

        Args:
            step: WorkflowStep
            context: ExecutionContext

        Returns:
            StepResult
        """
        from app.services.workflow.workflow_step_executor import StepResult

        # Step-Execution erstellen
        step_execution = WorkflowStepExecution(
            id=uuid4(),
            execution_id=context.execution_id,
            step_id=step.id,
            status=ExecutionStatus.RUNNING.value,
            started_at=datetime.now(timezone.utc),
            input_data=context.data,
        )

        self.db.add(step_execution)
        await self.db.commit()

        try:
            # Step via Executor ausfuehren
            if self.step_executor:
                result = await self.step_executor.execute_step(step, context)
            else:
                # Fallback: Einfache Ausfuehrung
                result = StepResult(
                    success=True,
                    output={},
                    error=None,
                )

            # Step-Execution aktualisieren
            step_execution.status = (
                ExecutionStatus.COMPLETED.value if result.success else ExecutionStatus.FAILED.value
            )
            step_execution.completed_at = datetime.now(timezone.utc)
            step_execution.output_data = result.output
            step_execution.error_message = result.error

            await self.db.commit()

            logger.debug(
                "workflow_step_executed",
                step_id=str(step.id),
                step_type=step.step_type,
                success=result.success,
            )

            return result

        except Exception as e:
            step_execution.status = ExecutionStatus.FAILED.value
            step_execution.completed_at = datetime.now(timezone.utc)
            step_execution.error_message = safe_error_detail(e, "Workflow")

            await self.db.commit()

            return StepResult(success=False, output={}, **safe_error_log(e))

    async def _retry_step(
        self,
        step: WorkflowStep,
        context: ExecutionContext,
        retry_count: int,
    ) -> "StepResult":
        """Wiederholt einen fehlgeschlagenen Step.

        Args:
            step: WorkflowStep
            context: ExecutionContext
            retry_count: Aktuelle Wiederholungszahl

        Returns:
            StepResult
        """
        from app.services.workflow.workflow_step_executor import StepResult


        logger.info(
            "workflow_step_retry",
            step_id=str(step.id),
            retry_count=retry_count,
            max_retries=step.max_retries,
        )

        # Exponential Backoff
        delay = min(60 * (2 ** (retry_count - 1)), 300)  # Max 5 Minuten
        await asyncio.sleep(delay)

        result = await self._execute_step(step, context)
        result.retry_count = retry_count

        return result

    # =========================================================================
    # Execution State Management
    # =========================================================================

    async def _complete_execution(
        self,
        execution: WorkflowExecution,
        context: ExecutionContext,
    ) -> None:
        """Schliesst eine Ausfuehrung erfolgreich ab.

        Args:
            execution: WorkflowExecution
            context: ExecutionContext
        """
        stmt = (
            update(WorkflowExecution)
            .where(WorkflowExecution.id == execution.id)
            .values(
                status=ExecutionStatus.COMPLETED.value,
                completed_at=datetime.now(timezone.utc),
                progress_percent=100,
                result=context.step_outputs,
            )
        )

        await self.db.execute(stmt)
        await self.db.commit()

        logger.info(
            "workflow_execution_completed",
            execution_id=str(execution.id),
            workflow_id=str(execution.workflow_id),
        )

    async def _fail_execution(
        self,
        execution: WorkflowExecution,
        context: ExecutionContext,
        error: str,
    ) -> None:
        """Markiert eine Ausfuehrung als fehlgeschlagen.

        Args:
            execution: WorkflowExecution
            context: ExecutionContext
            error: Fehlermeldung
        """
        stmt = (
            update(WorkflowExecution)
            .where(WorkflowExecution.id == execution.id)
            .values(
                status=ExecutionStatus.FAILED.value,
                completed_at=datetime.now(timezone.utc),
                error_message=error,
                result=context.step_outputs,
            )
        )

        await self.db.execute(stmt)
        await self.db.commit()

        logger.error(
            "workflow_execution_failed",
            execution_id=str(execution.id),
            workflow_id=str(execution.workflow_id),
            error=error,
        )

    async def _pause_execution(
        self,
        execution: WorkflowExecution,
        context: ExecutionContext,
        current_step_id: UUID,
    ) -> None:
        """Pausiert eine Ausfuehrung.

        Args:
            execution: WorkflowExecution
            context: ExecutionContext
            current_step_id: Aktueller Step
        """
        stmt = (
            update(WorkflowExecution)
            .where(WorkflowExecution.id == execution.id)
            .values(
                status=ExecutionStatus.PAUSED.value,
                current_step_id=current_step_id,
                variables=context.variables,
            )
        )

        await self.db.execute(stmt)
        await self.db.commit()

        logger.info(
            "workflow_execution_paused",
            execution_id=str(execution.id),
            current_step_id=str(current_step_id),
        )

    async def _cancel_execution(
        self,
        execution: WorkflowExecution,
    ) -> None:
        """Bricht eine Ausfuehrung ab.

        Args:
            execution: WorkflowExecution
        """
        stmt = (
            update(WorkflowExecution)
            .where(WorkflowExecution.id == execution.id)
            .values(
                status=ExecutionStatus.CANCELLED.value,
                completed_at=datetime.now(timezone.utc),
            )
        )

        await self.db.execute(stmt)
        await self.db.commit()

    async def _update_progress(
        self,
        execution_id: UUID,
        progress: int,
        current_step_id: Optional[UUID] = None,
    ) -> None:
        """Aktualisiert den Fortschritt.

        Args:
            execution_id: Execution-ID
            progress: Fortschritt in Prozent
            current_step_id: Aktueller Step
        """
        values: Dict[str, Any] = {"progress_percent": progress}
        if current_step_id:
            values["current_step_id"] = current_step_id

        stmt = (
            update(WorkflowExecution)
            .where(WorkflowExecution.id == execution_id)
            .values(**values)
        )

        await self.db.execute(stmt)
        await self.db.commit()

    async def _refresh_execution(
        self,
        execution_id: UUID,
    ) -> WorkflowExecution:
        """Laedt Execution-Status neu.

        Args:
            execution_id: Execution-ID

        Returns:
            WorkflowExecution
        """
        query = select(WorkflowExecution).where(WorkflowExecution.id == execution_id)
        result = await self.db.execute(query)
        return result.scalar_one()

    # =========================================================================
    # User Actions
    # =========================================================================

    async def pause_execution(
        self,
        execution_id: UUID,
        user_id: UUID,
        company_id: Optional[UUID] = None,
    ) -> bool:
        """Pausiert eine laufende Ausfuehrung.

        SECURITY: Wenn company_id angegeben wird, MUSS die Execution zu einem
        Workflow dieser Company gehoeren (Multi-Tenant Isolation).

        Args:
            execution_id: Execution-ID
            user_id: User-ID
            company_id: Company-ID fuer Multi-Tenant Isolation (EMPFOHLEN)

        Returns:
            True wenn erfolgreich
        """
        execution = await self._get_execution(execution_id, user_id, company_id)
        if not execution or execution.status != ExecutionStatus.RUNNING.value:
            return False

        stmt = (
            update(WorkflowExecution)
            .where(WorkflowExecution.id == execution_id)
            .values(status=ExecutionStatus.PAUSED.value)
        )

        await self.db.execute(stmt)
        await self.db.commit()

        logger.info(
            "workflow_execution_pause_requested",
            execution_id=str(execution_id),
            user_id=str(user_id),
        )

        return True

    async def resume_execution(
        self,
        execution_id: UUID,
        user_id: UUID,
        company_id: Optional[UUID] = None,
    ) -> bool:
        """Setzt eine pausierte Ausfuehrung fort.

        SECURITY: Wenn company_id angegeben wird, MUSS die Execution zu einem
        Workflow dieser Company gehoeren (Multi-Tenant Isolation).

        Args:
            execution_id: Execution-ID
            user_id: User-ID
            company_id: Company-ID fuer Multi-Tenant Isolation (EMPFOHLEN)

        Returns:
            True wenn erfolgreich
        """
        execution = await self._get_execution(execution_id, user_id, company_id)
        if not execution or execution.status != ExecutionStatus.PAUSED.value:
            return False

        # Workflow laden (bereits company_id validiert durch _get_execution)
        query = (
            select(Workflow)
            .where(Workflow.id == execution.workflow_id)
            .options(selectinload(Workflow.steps))
        )
        result = await self.db.execute(query)
        workflow = result.scalar_one_or_none()

        if not workflow:
            return False

        # Status aktualisieren
        stmt = (
            update(WorkflowExecution)
            .where(WorkflowExecution.id == execution_id)
            .values(status=ExecutionStatus.RUNNING.value)
        )

        await self.db.execute(stmt)
        await self.db.commit()

        # Context wiederherstellen - SECURITY: company_id fuer Multi-Tenant Isolation
        document_data = None
        if execution.document_id:
            document_data = await self._load_document_data(execution.document_id)

        context = ExecutionContext(
            execution_id=execution.id,
            workflow_id=execution.workflow_id,
            user_id=user_id,
            company_id=workflow.company_id,  # SECURITY: company_id aus Workflow
            document_id=execution.document_id,
            document_data=document_data,
            trigger_data=execution.trigger_data or {},
            variables=execution.variables or {},
        )

        # Ausfuehrung fortsetzen
        asyncio.create_task(
            self._execute_workflow(workflow, execution, context)
        )

        logger.info(
            "workflow_execution_resumed",
            execution_id=str(execution_id),
        )

        return True

    async def cancel_execution(
        self,
        execution_id: UUID,
        user_id: UUID,
        company_id: Optional[UUID] = None,
    ) -> bool:
        """Bricht eine Ausfuehrung ab.

        SECURITY: Wenn company_id angegeben wird, MUSS die Execution zu einem
        Workflow dieser Company gehoeren (Multi-Tenant Isolation).

        Args:
            execution_id: Execution-ID
            user_id: User-ID
            company_id: Company-ID fuer Multi-Tenant Isolation (EMPFOHLEN)

        Returns:
            True wenn erfolgreich
        """
        execution = await self._get_execution(execution_id, user_id, company_id)
        if not execution or execution.status not in (
            ExecutionStatus.RUNNING.value,
            ExecutionStatus.PAUSED.value,
            ExecutionStatus.PENDING.value,
        ):
            return False

        stmt = (
            update(WorkflowExecution)
            .where(WorkflowExecution.id == execution_id)
            .values(
                status=ExecutionStatus.CANCELLED.value,
                completed_at=datetime.now(timezone.utc),
            )
        )

        await self.db.execute(stmt)
        await self.db.commit()

        logger.info(
            "workflow_execution_cancelled",
            execution_id=str(execution_id),
            user_id=str(user_id),
        )

        return True

    async def retry_execution(
        self,
        execution_id: UUID,
        user_id: UUID,
        company_id: Optional[UUID] = None,
    ) -> Optional[WorkflowExecution]:
        """Wiederholt eine fehlgeschlagene Ausfuehrung.

        SECURITY: Wenn company_id angegeben wird, MUSS die Execution zu einem
        Workflow dieser Company gehoeren (Multi-Tenant Isolation).

        Args:
            execution_id: Original Execution-ID
            user_id: User-ID
            company_id: Company-ID fuer Multi-Tenant Isolation (EMPFOHLEN)

        Returns:
            Neue WorkflowExecution oder None
        """
        execution = await self._get_execution(execution_id, user_id, company_id)
        if not execution or execution.status != ExecutionStatus.FAILED.value:
            return None

        # Neue Ausfuehrung starten (company_id weitergeben)
        return await self.start_execution(
            workflow_id=execution.workflow_id,
            user_id=user_id,
            company_id=company_id,
            document_id=execution.document_id,
            trigger_data=execution.trigger_data,
            initial_variables=execution.variables,
        )

    # =========================================================================
    # Query Methods
    # =========================================================================

    async def get_execution(
        self,
        execution_id: UUID,
        user_id: Optional[UUID] = None,
        company_id: Optional[UUID] = None,
    ) -> Optional[WorkflowExecution]:
        """Holt eine Ausfuehrung mit Multi-Tenant Isolation.

        SECURITY: Wenn company_id angegeben wird, MUSS die Execution zu einem
        Workflow dieser Company gehoeren (Multi-Tenant Isolation).

        Args:
            execution_id: Execution-ID
            user_id: Optionale User-ID fuer Berechtigungspruefung
            company_id: Company-ID fuer Multi-Tenant Isolation (EMPFOHLEN)

        Returns:
            WorkflowExecution oder None
        """
        return await self._get_execution(execution_id, user_id, company_id)

    async def list_executions(
        self,
        company_id: Optional[UUID] = None,
        workflow_id: Optional[UUID] = None,
        user_id: Optional[UUID] = None,
        status: Optional[str] = None,
        document_id: Optional[UUID] = None,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[List[WorkflowExecution], int]:
        """Listet Ausfuehrungen mit Multi-Tenant Isolation.

        SECURITY: Wenn company_id angegeben wird, werden NUR Executions von
        Workflows dieser Company zurueckgegeben (Multi-Tenant Isolation).

        Args:
            company_id: Company-ID fuer Multi-Tenant Isolation (EMPFOHLEN)
            workflow_id: Filter nach Workflow
            user_id: Filter nach User
            status: Filter nach Status
            document_id: Filter nach Dokument
            offset: Pagination Offset
            limit: Pagination Limit

        Returns:
            Tuple aus Liste und Gesamtanzahl
        """
        conditions = []

        # SECURITY: company_id Filter fuer Multi-Tenant Isolation
        # Filtert ueber Join mit Workflow-Tabelle
        if company_id:
            # Subquery: Workflow-IDs dieser Company
            workflow_subquery = (
                select(Workflow.id)
                .where(Workflow.company_id == company_id)
                .scalar_subquery()
            )
            conditions.append(WorkflowExecution.workflow_id.in_(workflow_subquery))

        if workflow_id:
            conditions.append(WorkflowExecution.workflow_id == workflow_id)
        if user_id:
            conditions.append(WorkflowExecution.triggered_by_id == user_id)
        if status:
            conditions.append(WorkflowExecution.status == status)
        if document_id:
            conditions.append(WorkflowExecution.document_id == document_id)

        # Count
        count_query = select(func.count(WorkflowExecution.id))
        if conditions:
            count_query = count_query.where(and_(*conditions))

        count_result = await self.db.execute(count_query)
        total = count_result.scalar() or 0

        # Data
        query = select(WorkflowExecution).order_by(
            WorkflowExecution.started_at.desc()
        )
        if conditions:
            query = query.where(and_(*conditions))

        query = query.offset(offset).limit(limit)

        result = await self.db.execute(query)
        executions = list(result.scalars().all())

        return executions, total

    async def get_step_executions(
        self,
        execution_id: UUID,
        user_id: Optional[UUID] = None,
        company_id: Optional[UUID] = None,
    ) -> List[WorkflowStepExecution]:
        """Holt Step-Ausfuehrungen mit Multi-Tenant Isolation.

        SECURITY: Wenn company_id angegeben wird, wird validiert dass die
        Execution zu einem Workflow dieser Company gehoert.

        Args:
            execution_id: Execution-ID
            user_id: User-ID fuer Berechtigungspruefung
            company_id: Company-ID fuer Multi-Tenant Isolation (EMPFOHLEN)

        Returns:
            Liste der Step-Executions (leer bei fehlendem Zugriff)
        """
        # SECURITY: Execution-Zugriff validieren (Multi-Tenant Isolation)
        if user_id or company_id:
            execution = await self._get_execution(execution_id, user_id, company_id)
            if not execution:
                logger.warning(
                    "get_step_executions_blocked_execution_not_accessible",
                    execution_id=str(execution_id),
                    user_id=str(user_id) if user_id else None,
                    company_id=str(company_id) if company_id else None,
                )
                return []

        query = (
            select(WorkflowStepExecution)
            .where(WorkflowStepExecution.execution_id == execution_id)
            .order_by(WorkflowStepExecution.started_at)
        )

        result = await self.db.execute(query)
        return list(result.scalars().all())

    # =========================================================================
    # Helper Methods
    # =========================================================================

    async def _get_execution(
        self,
        execution_id: UUID,
        user_id: Optional[UUID] = None,
        company_id: Optional[UUID] = None,
    ) -> Optional[WorkflowExecution]:
        """Interne Methode zum Laden einer Execution mit Multi-Tenant Isolation.

        SECURITY: Wenn company_id angegeben wird, wird validiert dass die
        Execution zu einem Workflow dieser Company gehoert.

        Args:
            execution_id: Execution-ID
            user_id: Optionale User-ID
            company_id: Company-ID fuer Multi-Tenant Isolation (EMPFOHLEN)

        Returns:
            WorkflowExecution oder None
        """
        query = select(WorkflowExecution).where(
            WorkflowExecution.id == execution_id
        )

        if user_id:
            query = query.where(WorkflowExecution.triggered_by_id == user_id)

        result = await self.db.execute(query)
        execution = result.scalar_one_or_none()

        # SECURITY: company_id Validierung ueber Workflow (Multi-Tenant Isolation)
        if execution and company_id:
            workflow_query = select(Workflow.company_id).where(
                Workflow.id == execution.workflow_id
            )
            workflow_result = await self.db.execute(workflow_query)
            workflow_company_id = workflow_result.scalar_one_or_none()

            if workflow_company_id != company_id:
                logger.warning(
                    "cross_tenant_execution_access_blocked",
                    execution_id=str(execution_id),
                    workflow_company_id=str(workflow_company_id) if workflow_company_id else None,
                    requested_company_id=str(company_id),
                    user_id=str(user_id) if user_id else None,
                )
                return None

        return execution

    async def _count_running_executions(
        self,
        workflow_id: UUID,
    ) -> int:
        """Zaehlt laufende Ausfuehrungen.

        Args:
            workflow_id: Workflow-ID

        Returns:
            Anzahl laufender Executions
        """
        query = select(func.count(WorkflowExecution.id)).where(
            and_(
                WorkflowExecution.workflow_id == workflow_id,
                WorkflowExecution.status.in_([
                    ExecutionStatus.RUNNING.value,
                    ExecutionStatus.PENDING.value,
                ]),
            )
        )

        result = await self.db.execute(query)
        return result.scalar() or 0

    async def _load_document_data(
        self,
        document_id: UUID,
    ) -> Optional[Dict[str, Any]]:
        """Laedt Dokument-Daten.

        Args:
            document_id: Dokument-ID

        Returns:
            Document-Daten als Dict oder None
        """
        query = select(Document).where(Document.id == document_id)
        result = await self.db.execute(query)
        document = result.scalar_one_or_none()

        if not document:
            return None

        return {
            "id": str(document.id),
            "filename": document.filename,
            "file_extension": document.file_extension,
            "file_size": document.file_size,
            "mime_type": document.mime_type,
            "status": document.status,
            "document_type": document.document_type,
            "folder_id": str(document.folder_id) if document.folder_id else None,
            "created_at": document.created_at.isoformat() if document.created_at else None,
            "processed_at": document.processed_at.isoformat() if document.processed_at else None,
            "extracted_data": document.extracted_data,
        }
