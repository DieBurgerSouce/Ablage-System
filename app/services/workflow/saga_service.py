# -*- coding: utf-8 -*-
"""Saga Service für Ablage-System.

Implementiert das Saga-Pattern für verteilte Transaktionen:
- Compensation-Aktionen pro Schritt
- Automatisches Rollback bei Fehler
- Transaktionslog für Debugging
- State Machine für Saga-Ausführung
- Dead Letter Queue für fehlgeschlagene Compensations

Alle Benutzer-sichtbaren Texte sind auf Deutsch.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple, TYPE_CHECKING
from uuid import UUID, uuid4

import structlog
from sqlalchemy import and_, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models_workflow_versioning import (
    Saga,
    SagaStatus,
    SagaStep,
    SagaStepStatus,
    SagaTransactionLog,
)
from app.core.safe_errors import safe_error_log, safe_error_detail

if TYPE_CHECKING:
    from app.db.models import User

logger = structlog.get_logger(__name__)


# ============================================================================
# Step Handler Registry
# ============================================================================


class StepHandlerRegistry:
    """Registry für Step-Handler und Compensation-Handler.

    Ermöglicht das Registrieren von Handlern für verschiedene
    Action-Types.
    """

    def __init__(self) -> None:
        """Initialisiert die Registry."""
        self._action_handlers: Dict[str, Callable] = {}
        self._compensation_handlers: Dict[str, Callable] = {}

    def register_action(
        self,
        action_type: str,
        handler: Callable,
    ) -> None:
        """Registriert einen Action-Handler.

        Args:
            action_type: Action-Typ-Name
            handler: Async Handler-Funktion
        """
        self._action_handlers[action_type] = handler

    def register_compensation(
        self,
        compensation_type: str,
        handler: Callable,
    ) -> None:
        """Registriert einen Compensation-Handler.

        Args:
            compensation_type: Compensation-Typ-Name
            handler: Async Handler-Funktion
        """
        self._compensation_handlers[compensation_type] = handler

    def get_action_handler(self, action_type: str) -> Optional[Callable]:
        """Holt einen Action-Handler.

        Args:
            action_type: Action-Typ-Name

        Returns:
            Handler oder None
        """
        return self._action_handlers.get(action_type)

    def get_compensation_handler(self, compensation_type: str) -> Optional[Callable]:
        """Holt einen Compensation-Handler.

        Args:
            compensation_type: Compensation-Typ-Name

        Returns:
            Handler oder None
        """
        return self._compensation_handlers.get(compensation_type)


# ============================================================================
# Saga Service
# ============================================================================


class SagaService:
    """Service für Saga-Orchestrierung.

    Implementiert:
    - Saga-Erstellung und -Ausführung
    - Automatische Compensation bei Fehler
    - Dead Letter Queue
    - Transaktionslog
    - State Machine

    Saga-Zustandsmaschine:
    PENDING -> RUNNING -> COMPLETED
                      -> COMPENSATING -> COMPENSATED
                                     -> PARTIALLY_COMPENSATED
                                     -> FAILED

    SECURITY: Alle Operationen validieren company_id für Multi-Tenant Isolation.
    """

    def __init__(
        self,
        db: AsyncSession,
        handler_registry: Optional[StepHandlerRegistry] = None,
    ) -> None:
        """Initialisiert den SagaService.

        Args:
            db: AsyncSession für Datenbankoperationen
            handler_registry: Optionale Handler-Registry
        """
        self.db = db
        self.handler_registry = handler_registry or StepHandlerRegistry()
        self._register_default_handlers()

    def _register_default_handlers(self) -> None:
        """Registriert Standard-Handler für gaengige Actions."""
        from app.services.orchestration.sagas import register_all_saga_handlers

        register_all_saga_handlers(self.handler_registry)

    # =========================================================================
    # Saga Creation
    # =========================================================================

    async def create_saga(
        self,
        company_id: UUID,
        user_id: UUID,
        name: str,
        steps: List[Dict[str, Any]],
        description: Optional[str] = None,
        execution_id: Optional[UUID] = None,
        context_data: Optional[Dict[str, Any]] = None,
        max_retries: int = 3,
    ) -> Saga:
        """Erstellt eine neue Saga mit Steps.

        Args:
            company_id: Company-ID (PFLICHT für Multi-Tenant)
            user_id: Initiator
            name: Saga-Name
            steps: Liste von Step-Definitionen
            description: Optionale Beschreibung
            execution_id: Optionale Workflow-Execution-ID
            context_data: Optionale Kontext-Daten
            max_retries: Max Wiederholungen

        Returns:
            Erstellte Saga

        Step-Format:
        {
            "name": "Schritt 1",
            "action_type": "move_document",
            "action_params": {"document_id": "...", "folder_id": "..."},
            "compensation_type": "restore_document",  # Optional
            "compensation_params": {"original_folder_id": "..."},  # Optional
            "timeout_seconds": 300,  # Optional
            "max_retries": 3,  # Optional
        }
        """
        saga = Saga(
            id=uuid4(),
            execution_id=execution_id,
            company_id=company_id,
            name=name,
            description=description,
            status=SagaStatus.PENDING.value,
            total_steps=len(steps),
            context_data=context_data or {},
            max_retries=max_retries,
            initiated_by_id=user_id,
        )

        self.db.add(saga)

        # Steps erstellen
        for order, step_def in enumerate(steps, start=1):
            step = SagaStep(
                id=uuid4(),
                saga_id=saga.id,
                step_order=order,
                name=step_def.get("name", f"Schritt {order}"),
                description=step_def.get("description"),
                action_type=step_def["action_type"],
                action_params=step_def.get("action_params", {}),
                compensation_type=step_def.get("compensation_type"),
                compensation_params=step_def.get("compensation_params"),
                has_compensation=bool(step_def.get("compensation_type")),
                status=SagaStepStatus.PENDING.value,
                timeout_seconds=step_def.get("timeout_seconds", 300),
                max_retries=step_def.get("max_retries", 3),
                idempotency_key=step_def.get("idempotency_key"),
            )
            self.db.add(step)

        await self.db.commit()
        await self.db.refresh(saga)

        # Log erstellen
        await self._log_event(
            saga_id=saga.id,
            event_type="saga_created",
            previous_state=None,
            new_state=SagaStatus.PENDING.value,
            event_data={
                "name": name,
                "total_steps": len(steps),
                "initiated_by": str(user_id),
            },
        )

        logger.info(
            "saga_created",
            saga_id=str(saga.id),
            name=name,
            total_steps=len(steps),
            company_id=str(company_id),
        )

        return saga

    # =========================================================================
    # Saga Execution
    # =========================================================================

    async def execute_saga(
        self,
        saga_id: UUID,
        company_id: UUID,
    ) -> Saga:
        """Führt eine Saga aus.

        Durchlaeuft alle Steps sequentiell. Bei Fehler wird automatisch
        die Compensation gestartet.

        Args:
            saga_id: Saga-ID
            company_id: Company-ID (PFLICHT für Multi-Tenant)

        Returns:
            Aktualisierte Saga

        Raises:
            ValueError: Wenn Saga nicht gefunden oder nicht startbar
        """
        saga = await self._get_saga_with_steps(saga_id, company_id)
        if not saga:
            raise ValueError("Saga nicht gefunden")

        if saga.status != SagaStatus.PENDING.value:
            raise ValueError(f"Saga kann nicht gestartet werden: Status={saga.status}")

        # Status auf RUNNING setzen
        saga.status = SagaStatus.RUNNING.value
        saga.started_at = datetime.now(timezone.utc)
        await self.db.commit()

        await self._log_event(
            saga_id=saga.id,
            event_type="saga_started",
            previous_state=SagaStatus.PENDING.value,
            new_state=SagaStatus.RUNNING.value,
        )

        logger.info(
            "saga_execution_started",
            saga_id=str(saga_id),
            total_steps=saga.total_steps,
        )

        # Steps ausführen
        try:
            await self._execute_forward(saga)
        except Exception as e:
            logger.exception(
                "saga_execution_error",
                saga_id=str(saga_id),
                **safe_error_log(e),
            )

        # Saga neu laden für aktuellen Status
        saga = await self._get_saga_with_steps(saga_id, company_id)
        return saga

    async def _execute_forward(self, saga: Saga) -> None:
        """Führt die Forward-Phase der Saga aus.

        Args:
            saga: Saga mit geladenen Steps
        """
        steps = sorted(saga.steps, key=lambda s: s.step_order)

        for step in steps:
            if step.status != SagaStepStatus.PENDING.value:
                # Bereits ausgeführt (z.B. bei Resume)
                continue

            saga.current_step_index = step.step_order
            await self.db.commit()

            # Step ausführen
            success = await self._execute_step(saga, step)

            if not success:
                # Fehler - Compensation starten
                saga.status = SagaStatus.COMPENSATING.value
                saga.error_step_id = step.id
                await self.db.commit()

                await self._log_event(
                    saga_id=saga.id,
                    step_id=step.id,
                    event_type="saga_compensation_triggered",
                    previous_state=SagaStatus.RUNNING.value,
                    new_state=SagaStatus.COMPENSATING.value,
                    event_data={"error_step": step.name},
                )

                logger.warning(
                    "saga_step_failed_starting_compensation",
                    saga_id=str(saga.id),
                    failed_step=step.name,
                )

                # Compensation ausführen
                await self._execute_compensation(saga)
                return

        # Alle Steps erfolgreich
        saga.status = SagaStatus.COMPLETED.value
        saga.completed_at = datetime.now(timezone.utc)
        await self.db.commit()

        await self._log_event(
            saga_id=saga.id,
            event_type="saga_completed",
            previous_state=SagaStatus.RUNNING.value,
            new_state=SagaStatus.COMPLETED.value,
        )

        logger.info(
            "saga_completed_successfully",
            saga_id=str(saga.id),
        )

    async def _execute_step(self, saga: Saga, step: SagaStep) -> bool:
        """Führt einen einzelnen Step aus.

        Args:
            saga: Parent Saga
            step: Auszuführender Step

        Returns:
            True wenn erfolgreich, False bei Fehler
        """
        step.status = SagaStepStatus.RUNNING.value
        step.executed_at = datetime.now(timezone.utc)
        await self.db.commit()

        await self._log_event(
            saga_id=saga.id,
            step_id=step.id,
            event_type="step_started",
            previous_state=SagaStepStatus.PENDING.value,
            new_state=SagaStepStatus.RUNNING.value,
        )

        # Handler holen
        handler = self.handler_registry.get_action_handler(step.action_type)

        try:
            if handler:
                # Handler ausführen mit Timeout
                result = await asyncio.wait_for(
                    handler(
                        action_params=step.action_params,
                        context_data=saga.context_data,
                        step_id=str(step.id),
                    ),
                    timeout=step.timeout_seconds,
                )
                step.result_data = result if isinstance(result, dict) else {"result": result}
            else:
                # Kein Handler - Mock-Erfolg (für Tests)
                logger.warning(
                    "no_handler_for_action_type",
                    action_type=step.action_type,
                    step_id=str(step.id),
                )
                step.result_data = {"mocked": True}

            step.status = SagaStepStatus.COMPLETED.value
            step.completed_at = datetime.now(timezone.utc)
            await self.db.commit()

            await self._log_event(
                saga_id=saga.id,
                step_id=step.id,
                event_type="step_completed",
                previous_state=SagaStepStatus.RUNNING.value,
                new_state=SagaStepStatus.COMPLETED.value,
                event_data={"result": step.result_data},
            )

            logger.debug(
                "saga_step_completed",
                saga_id=str(saga.id),
                step_name=step.name,
            )

            return True

        except asyncio.TimeoutError:
            step.status = SagaStepStatus.FAILED.value
            step.error_message = f"Timeout nach {step.timeout_seconds} Sekunden"
            step.completed_at = datetime.now(timezone.utc)
            await self.db.commit()

            await self._log_event(
                saga_id=saga.id,
                step_id=step.id,
                event_type="step_timeout",
                previous_state=SagaStepStatus.RUNNING.value,
                new_state=SagaStepStatus.FAILED.value,
                error_message=step.error_message,
            )

            return False

        except Exception as e:
            # Retry-Logik
            if step.can_retry:
                step.retry_count += 1
                step.status = SagaStepStatus.PENDING.value
                await self.db.commit()

                await self._log_event(
                    saga_id=saga.id,
                    step_id=step.id,
                    event_type="step_retry",
                    previous_state=SagaStepStatus.RUNNING.value,
                    new_state=SagaStepStatus.PENDING.value,
                    event_data={"retry_count": step.retry_count},
                    error_message=str(e),
                )

                # Exponential Backoff
                delay = min(step.retry_delay_seconds * (2 ** (step.retry_count - 1)), 300)
                await asyncio.sleep(delay)

                return await self._execute_step(saga, step)

            step.status = SagaStepStatus.FAILED.value
            step.error_message = safe_error_detail(e, "Saga")
            step.error_details = safe_error_log(e)
            step.completed_at = datetime.now(timezone.utc)
            await self.db.commit()

            await self._log_event(
                saga_id=saga.id,
                step_id=step.id,
                event_type="step_failed",
                previous_state=SagaStepStatus.RUNNING.value,
                new_state=SagaStepStatus.FAILED.value,
                error_message=str(e),
            )

            return False

    # =========================================================================
    # Compensation
    # =========================================================================

    async def _execute_compensation(self, saga: Saga) -> None:
        """Führt die Compensation-Phase aus.

        Geht alle erfolgreich ausgeführten Steps in umgekehrter
        Reihenfolge durch und führt deren Compensation aus.

        Args:
            saga: Saga mit geladenen Steps
        """
        saga.compensation_started_at = datetime.now(timezone.utc)
        await self.db.commit()

        # Erfolgreich ausgeführte Steps in umgekehrter Reihenfolge
        completed_steps = [
            s for s in saga.steps
            if s.status == SagaStepStatus.COMPLETED.value and s.has_compensation
        ]
        completed_steps.sort(key=lambda s: s.step_order, reverse=True)

        compensation_errors = []

        for step in completed_steps:
            success = await self._compensate_step(saga, step)

            if success:
                saga.steps_compensated += 1
            else:
                compensation_errors.append(step.id)

        await self.db.commit()

        # Finalen Status setzen
        if not compensation_errors:
            saga.status = SagaStatus.COMPENSATED.value
            saga.compensation_completed_at = datetime.now(timezone.utc)

            await self._log_event(
                saga_id=saga.id,
                event_type="saga_compensated",
                previous_state=SagaStatus.COMPENSATING.value,
                new_state=SagaStatus.COMPENSATED.value,
                event_data={"steps_compensated": saga.steps_compensated},
            )

            logger.info(
                "saga_fully_compensated",
                saga_id=str(saga.id),
                steps_compensated=saga.steps_compensated,
            )

        elif saga.steps_compensated > 0:
            saga.status = SagaStatus.PARTIALLY_COMPENSATED.value
            saga.in_dead_letter_queue = True
            saga.dead_letter_reason = f"{len(compensation_errors)} Compensation(s) fehlgeschlagen"
            saga.dead_letter_at = datetime.now(timezone.utc)

            await self._log_event(
                saga_id=saga.id,
                event_type="saga_partially_compensated",
                previous_state=SagaStatus.COMPENSATING.value,
                new_state=SagaStatus.PARTIALLY_COMPENSATED.value,
                event_data={
                    "steps_compensated": saga.steps_compensated,
                    "failed_compensations": [str(sid) for sid in compensation_errors],
                },
            )

            logger.warning(
                "saga_partially_compensated",
                saga_id=str(saga.id),
                steps_compensated=saga.steps_compensated,
                failed_count=len(compensation_errors),
            )

        else:
            saga.status = SagaStatus.FAILED.value
            saga.in_dead_letter_queue = True
            saga.dead_letter_reason = "Keine Compensation erfolgreich"
            saga.dead_letter_at = datetime.now(timezone.utc)

            await self._log_event(
                saga_id=saga.id,
                event_type="saga_compensation_failed",
                previous_state=SagaStatus.COMPENSATING.value,
                new_state=SagaStatus.FAILED.value,
            )

            logger.error(
                "saga_compensation_completely_failed",
                saga_id=str(saga.id),
            )

        await self.db.commit()

    async def _compensate_step(self, saga: Saga, step: SagaStep) -> bool:
        """Führt die Compensation für einen Step aus.

        Args:
            saga: Parent Saga
            step: Zu kompensierender Step

        Returns:
            True wenn erfolgreich, False bei Fehler
        """
        if not step.compensation_type:
            # Keine Compensation definiert
            step.status = SagaStepStatus.COMPENSATED.value
            step.compensated_at = datetime.now(timezone.utc)
            return True

        step.status = SagaStepStatus.COMPENSATING.value
        step.compensation_started_at = datetime.now(timezone.utc)
        await self.db.commit()

        await self._log_event(
            saga_id=saga.id,
            step_id=step.id,
            event_type="step_compensation_started",
            previous_state=SagaStepStatus.COMPLETED.value,
            new_state=SagaStepStatus.COMPENSATING.value,
        )

        # Handler holen
        handler = self.handler_registry.get_compensation_handler(step.compensation_type)

        try:
            if handler:
                await asyncio.wait_for(
                    handler(
                        compensation_params=step.compensation_params,
                        original_result=step.result_data,
                        context_data=saga.context_data,
                        step_id=str(step.id),
                    ),
                    timeout=step.timeout_seconds,
                )
            else:
                # Kein Handler - Mock-Erfolg (für Tests)
                logger.warning(
                    "no_handler_for_compensation_type",
                    compensation_type=step.compensation_type,
                    step_id=str(step.id),
                )

            step.status = SagaStepStatus.COMPENSATED.value
            step.compensated_at = datetime.now(timezone.utc)
            await self.db.commit()

            await self._log_event(
                saga_id=saga.id,
                step_id=step.id,
                event_type="step_compensated",
                previous_state=SagaStepStatus.COMPENSATING.value,
                new_state=SagaStepStatus.COMPENSATED.value,
            )

            logger.debug(
                "saga_step_compensated",
                saga_id=str(saga.id),
                step_name=step.name,
            )

            return True

        except Exception as e:
            # Compensation-Retry
            if step.compensation_retry_count < step.max_retries:
                step.compensation_retry_count += 1
                step.status = SagaStepStatus.COMPENSATING.value
                await self.db.commit()

                await self._log_event(
                    saga_id=saga.id,
                    step_id=step.id,
                    event_type="step_compensation_retry",
                    previous_state=SagaStepStatus.COMPENSATING.value,
                    new_state=SagaStepStatus.COMPENSATING.value,
                    event_data={"retry_count": step.compensation_retry_count},
                    error_message=str(e),
                )

                # Exponential Backoff
                delay = min(step.retry_delay_seconds * (2 ** (step.compensation_retry_count - 1)), 300)
                await asyncio.sleep(delay)

                return await self._compensate_step(saga, step)

            step.status = SagaStepStatus.COMPENSATION_FAILED.value
            step.compensation_error = safe_error_detail(e, "Saga")
            await self.db.commit()

            await self._log_event(
                saga_id=saga.id,
                step_id=step.id,
                event_type="step_compensation_failed",
                previous_state=SagaStepStatus.COMPENSATING.value,
                new_state=SagaStepStatus.COMPENSATION_FAILED.value,
                error_message=str(e),
            )

            logger.error(
                "saga_step_compensation_failed",
                saga_id=str(saga.id),
                step_name=step.name,
                error=str(e),
            )

            return False

    # =========================================================================
    # Saga Queries
    # =========================================================================

    async def get_saga(
        self,
        saga_id: UUID,
        company_id: UUID,
        include_steps: bool = True,
    ) -> Optional[Saga]:
        """Holt eine Saga nach ID.

        Args:
            saga_id: Saga-ID
            company_id: Company-ID (PFLICHT für Multi-Tenant)
            include_steps: Steps mit laden

        Returns:
            Saga oder None

        Note:
            company_id is included in the WHERE clause, providing implicit
            multi-tenant authorization. Returns None for both "saga not found"
            and "saga belongs to different tenant" (prevents enumeration attacks).
        """
        if include_steps:
            return await self._get_saga_with_steps(saga_id, company_id)
        else:
            query = select(Saga).where(
                and_(
                    Saga.id == saga_id,
                    Saga.company_id == company_id,
                )
            )
            result = await self.db.execute(query)
            return result.scalar_one_or_none()

    async def list_sagas(
        self,
        company_id: UUID,
        status: Optional[str] = None,
        execution_id: Optional[UUID] = None,
        in_dead_letter_queue: Optional[bool] = None,
        offset: int = 0,
        limit: int = 50,
    ) -> Tuple[List[Saga], int]:
        """Listet Sagas mit Filtern.

        Args:
            company_id: Company-ID (PFLICHT für Multi-Tenant)
            status: Optionaler Status-Filter
            execution_id: Optionaler Workflow-Execution-Filter
            in_dead_letter_queue: Filter für Dead Letter Queue
            offset: Pagination Offset
            limit: Pagination Limit

        Returns:
            Tuple aus Saga-Liste und Gesamtanzahl
        """
        conditions = [Saga.company_id == company_id]

        if status:
            conditions.append(Saga.status == status)
        if execution_id:
            conditions.append(Saga.execution_id == execution_id)
        if in_dead_letter_queue is not None:
            conditions.append(Saga.in_dead_letter_queue == in_dead_letter_queue)

        # Count
        count_query = select(func.count(Saga.id)).where(and_(*conditions))
        count_result = await self.db.execute(count_query)
        total = count_result.scalar() or 0

        # Data
        query = (
            select(Saga)
            .where(and_(*conditions))
            .order_by(Saga.created_at.desc())
            .offset(offset)
            .limit(limit)
        )

        result = await self.db.execute(query)
        sagas = list(result.scalars().all())

        return sagas, total

    async def get_dead_letter_sagas(
        self,
        company_id: UUID,
        offset: int = 0,
        limit: int = 50,
    ) -> Tuple[List[Saga], int]:
        """Holt Sagas aus der Dead Letter Queue.

        Args:
            company_id: Company-ID (PFLICHT für Multi-Tenant)
            offset: Pagination Offset
            limit: Pagination Limit

        Returns:
            Tuple aus Saga-Liste und Gesamtanzahl
        """
        return await self.list_sagas(
            company_id=company_id,
            in_dead_letter_queue=True,
            offset=offset,
            limit=limit,
        )

    async def get_saga_steps(
        self,
        saga_id: UUID,
        company_id: UUID,
    ) -> List[SagaStep]:
        """Holt alle Steps einer Saga.

        Args:
            saga_id: Saga-ID
            company_id: Company-ID (PFLICHT für Multi-Tenant)

        Returns:
            Liste der Steps

        Note:
            Implicit multi-tenant authorization is enforced via the preceding
            get_saga() call, which filters by company_id.
        """
        # Saga-Zugriff validieren
        saga = await self.get_saga(saga_id, company_id, include_steps=False)
        if not saga:
            return []

        query = (
            select(SagaStep)
            .where(SagaStep.saga_id == saga_id)
            .order_by(SagaStep.step_order)
        )

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_transaction_logs(
        self,
        saga_id: UUID,
        company_id: UUID,
        step_id: Optional[UUID] = None,
        offset: int = 0,
        limit: int = 100,
    ) -> Tuple[List[SagaTransactionLog], int]:
        """Holt Transaktionslogs für eine Saga.

        Args:
            saga_id: Saga-ID
            company_id: Company-ID (PFLICHT für Multi-Tenant)
            step_id: Optionaler Step-Filter
            offset: Pagination Offset
            limit: Pagination Limit

        Returns:
            Tuple aus Log-Liste und Gesamtanzahl

        Note:
            Implicit multi-tenant authorization is enforced via the preceding
            get_saga() call, which filters by company_id.
        """
        # Saga-Zugriff validieren
        saga = await self.get_saga(saga_id, company_id, include_steps=False)
        if not saga:
            return [], 0

        conditions = [SagaTransactionLog.saga_id == saga_id]
        if step_id:
            conditions.append(SagaTransactionLog.step_id == step_id)

        # Count
        count_query = select(func.count(SagaTransactionLog.id)).where(and_(*conditions))
        count_result = await self.db.execute(count_query)
        total = count_result.scalar() or 0

        # Data
        query = (
            select(SagaTransactionLog)
            .where(and_(*conditions))
            .order_by(SagaTransactionLog.created_at)
            .offset(offset)
            .limit(limit)
        )

        result = await self.db.execute(query)
        logs = list(result.scalars().all())

        return logs, total

    # =========================================================================
    # Saga Management
    # =========================================================================

    async def retry_saga(
        self,
        saga_id: UUID,
        company_id: UUID,
        user_id: UUID,
    ) -> Optional[Saga]:
        """Wiederholt eine fehlgeschlagene Saga.

        Args:
            saga_id: Saga-ID
            company_id: Company-ID (PFLICHT für Multi-Tenant)
            user_id: Ausführender User

        Returns:
            Aktualisierte Saga oder None
        """
        saga = await self._get_saga_with_steps(saga_id, company_id)
        if not saga:
            return None

        if saga.status not in (
            SagaStatus.FAILED.value,
            SagaStatus.PARTIALLY_COMPENSATED.value,
        ):
            logger.warning(
                "cannot_retry_saga_wrong_status",
                saga_id=str(saga_id),
                status=saga.status,
            )
            return None

        if saga.retry_count >= saga.max_retries:
            logger.warning(
                "saga_max_retries_exceeded",
                saga_id=str(saga_id),
                retry_count=saga.retry_count,
            )
            return None

        # Retry-Counter erhöhen
        saga.retry_count += 1
        saga.status = SagaStatus.PENDING.value
        saga.in_dead_letter_queue = False
        saga.dead_letter_reason = None
        saga.dead_letter_at = None
        saga.error_message = None
        saga.error_step_id = None

        # Fehlgeschlagene Steps zurücksetzen
        for step in saga.steps:
            if step.status in (
                SagaStepStatus.FAILED.value,
                SagaStepStatus.COMPENSATION_FAILED.value,
            ):
                step.status = SagaStepStatus.PENDING.value
                step.retry_count = 0
                step.error_message = None
                step.error_details = None

        await self.db.commit()

        await self._log_event(
            saga_id=saga.id,
            event_type="saga_retry_scheduled",
            previous_state=SagaStatus.FAILED.value,
            new_state=SagaStatus.PENDING.value,
            event_data={"retry_count": saga.retry_count, "user_id": str(user_id)},
        )

        logger.info(
            "saga_retry_scheduled",
            saga_id=str(saga_id),
            retry_count=saga.retry_count,
        )

        # Saga erneut ausführen
        return await self.execute_saga(saga_id, company_id)

    async def cancel_saga(
        self,
        saga_id: UUID,
        company_id: UUID,
        user_id: UUID,
        reason: Optional[str] = None,
    ) -> Optional[Saga]:
        """Bricht eine laufende Saga ab.

        Args:
            saga_id: Saga-ID
            company_id: Company-ID (PFLICHT für Multi-Tenant)
            user_id: Ausführender User
            reason: Optionaler Abbruchgrund

        Returns:
            Aktualisierte Saga oder None
        """
        saga = await self.get_saga(saga_id, company_id, include_steps=False)
        if not saga:
            return None

        if saga.status not in (
            SagaStatus.PENDING.value,
            SagaStatus.RUNNING.value,
            SagaStatus.COMPENSATING.value,
        ):
            logger.warning(
                "cannot_cancel_saga_wrong_status",
                saga_id=str(saga_id),
                status=saga.status,
            )
            return None

        previous_status = saga.status
        saga.status = SagaStatus.FAILED.value
        saga.error_message = reason or "Manuell abgebrochen"
        saga.completed_at = datetime.now(timezone.utc)

        await self.db.commit()

        await self._log_event(
            saga_id=saga.id,
            event_type="saga_cancelled",
            previous_state=previous_status,
            new_state=SagaStatus.FAILED.value,
            event_data={"reason": reason, "user_id": str(user_id)},
        )

        logger.info(
            "saga_cancelled",
            saga_id=str(saga_id),
            user_id=str(user_id),
            reason=reason,
        )

        return saga

    async def remove_from_dead_letter_queue(
        self,
        saga_id: UUID,
        company_id: UUID,
        user_id: UUID,
    ) -> Optional[Saga]:
        """Entfernt eine Saga aus der Dead Letter Queue.

        Args:
            saga_id: Saga-ID
            company_id: Company-ID (PFLICHT für Multi-Tenant)
            user_id: Ausführender User

        Returns:
            Aktualisierte Saga oder None
        """
        saga = await self.get_saga(saga_id, company_id, include_steps=False)
        if not saga or not saga.in_dead_letter_queue:
            return None

        saga.in_dead_letter_queue = False
        saga.dead_letter_reason = None
        saga.dead_letter_at = None

        await self.db.commit()

        await self._log_event(
            saga_id=saga.id,
            event_type="saga_removed_from_dlq",
            previous_state=saga.status,
            new_state=saga.status,
            event_data={"user_id": str(user_id)},
        )

        logger.info(
            "saga_removed_from_dead_letter_queue",
            saga_id=str(saga_id),
            user_id=str(user_id),
        )

        return saga

    # =========================================================================
    # Saga Visualization
    # =========================================================================

    async def get_saga_state_diagram(
        self,
        saga_id: UUID,
        company_id: UUID,
    ) -> Optional[Dict[str, Any]]:
        """Erstellt ein State-Diagramm für eine Saga.

        Args:
            saga_id: Saga-ID
            company_id: Company-ID (PFLICHT für Multi-Tenant)

        Returns:
            State-Diagramm als Dict oder None
        """
        saga = await self._get_saga_with_steps(saga_id, company_id)
        if not saga:
            return None

        nodes = []
        edges = []

        # Start-Node
        nodes.append({
            "id": "start",
            "type": "start",
            "label": "Start",
            "status": "completed" if saga.started_at else "pending",
        })

        prev_node_id = "start"

        # Step-Nodes
        for step in sorted(saga.steps, key=lambda s: s.step_order):
            step_node_id = f"step_{step.step_order}"

            nodes.append({
                "id": step_node_id,
                "type": "step",
                "label": step.name,
                "status": step.status,
                "action_type": step.action_type,
                "has_compensation": step.has_compensation,
                "duration_ms": step.duration_ms,
            })

            edges.append({
                "id": f"edge_{prev_node_id}_{step_node_id}",
                "source": prev_node_id,
                "target": step_node_id,
                "type": "forward",
            })

            prev_node_id = step_node_id

        # End-Node
        end_status = "completed" if saga.status == SagaStatus.COMPLETED.value else (
            "compensated" if saga.status == SagaStatus.COMPENSATED.value else (
                "failed" if saga.status == SagaStatus.FAILED.value else "pending"
            )
        )

        nodes.append({
            "id": "end",
            "type": "end",
            "label": "Ende",
            "status": end_status,
        })

        edges.append({
            "id": f"edge_{prev_node_id}_end",
            "source": prev_node_id,
            "target": "end",
            "type": "forward",
        })

        # Compensation-Edges (rückwärts)
        if saga.status in (
            SagaStatus.COMPENSATING.value,
            SagaStatus.COMPENSATED.value,
            SagaStatus.PARTIALLY_COMPENSATED.value,
        ):
            compensated_steps = [
                s for s in saga.steps
                if s.status in (
                    SagaStepStatus.COMPENSATED.value,
                    SagaStepStatus.COMPENSATING.value,
                    SagaStepStatus.COMPENSATION_FAILED.value,
                )
            ]

            for step in compensated_steps:
                step_node_id = f"step_{step.step_order}"
                # Rückwärts-Kante
                prev_step_order = step.step_order - 1
                target = f"step_{prev_step_order}" if prev_step_order > 0 else "start"

                edges.append({
                    "id": f"edge_comp_{step_node_id}_{target}",
                    "source": step_node_id,
                    "target": target,
                    "type": "compensation",
                    "status": step.status,
                })

        return {
            "saga_id": str(saga.id),
            "name": saga.name,
            "status": saga.status,
            "nodes": nodes,
            "edges": edges,
            "progress_percent": saga.progress_percent,
        }

    # =========================================================================
    # Statistics
    # =========================================================================

    async def get_saga_statistics(
        self,
        company_id: UUID,
    ) -> Dict[str, Any]:
        """Holt aggregierte Saga-Statistiken.

        Args:
            company_id: Company-ID (PFLICHT für Multi-Tenant)

        Returns:
            Statistik-Dictionary
        """
        # Gesamtzahlen
        total_query = select(func.count(Saga.id)).where(Saga.company_id == company_id)
        total_result = await self.db.execute(total_query)
        total = total_result.scalar() or 0

        # Nach Status
        status_query = (
            select(Saga.status, func.count(Saga.id))
            .where(Saga.company_id == company_id)
            .group_by(Saga.status)
        )
        status_result = await self.db.execute(status_query)
        status_counts = {row[0]: row[1] for row in status_result.fetchall()}

        # Dead Letter Queue
        dlq_query = select(func.count(Saga.id)).where(
            and_(
                Saga.company_id == company_id,
                Saga.in_dead_letter_queue == True,  # noqa: E712
            )
        )
        dlq_result = await self.db.execute(dlq_query)
        dlq_count = dlq_result.scalar() or 0

        # Erfolgsrate
        completed = status_counts.get(SagaStatus.COMPLETED.value, 0)
        failed = status_counts.get(SagaStatus.FAILED.value, 0)
        compensated = status_counts.get(SagaStatus.COMPENSATED.value, 0)
        partial = status_counts.get(SagaStatus.PARTIALLY_COMPENSATED.value, 0)

        finished = completed + failed + compensated + partial
        success_rate = (completed / finished * 100) if finished > 0 else 0

        return {
            "total": total,
            "by_status": status_counts,
            "dead_letter_queue": dlq_count,
            "success_rate": round(success_rate, 2),
            "completed": completed,
            "failed": failed,
            "compensated": compensated,
            "partially_compensated": partial,
        }

    # =========================================================================
    # Helper Methods
    # =========================================================================

    async def _get_saga_with_steps(
        self,
        saga_id: UUID,
        company_id: UUID,
    ) -> Optional[Saga]:
        """Laedt eine Saga mit allen Steps.

        Args:
            saga_id: Saga-ID
            company_id: Company-ID

        Returns:
            Saga mit Steps oder None
        """
        query = (
            select(Saga)
            .where(
                and_(
                    Saga.id == saga_id,
                    Saga.company_id == company_id,
                )
            )
            .options(selectinload(Saga.steps))
        )

        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def _log_event(
        self,
        saga_id: UUID,
        event_type: str,
        previous_state: Optional[str],
        new_state: str,
        step_id: Optional[UUID] = None,
        event_data: Optional[Dict[str, Any]] = None,
        error_message: Optional[str] = None,
        stack_trace: Optional[str] = None,
    ) -> None:
        """Erstellt einen Transaktionslog-Eintrag.

        Args:
            saga_id: Saga-ID
            event_type: Event-Typ
            previous_state: Vorheriger Status
            new_state: Neuer Status
            step_id: Optionale Step-ID
            event_data: Optionale Event-Daten
            error_message: Optionale Fehlermeldung
            stack_trace: Optionaler Stack-Trace
        """
        log = SagaTransactionLog(
            id=uuid4(),
            saga_id=saga_id,
            step_id=step_id,
            event_type=event_type,
            previous_state=previous_state,
            new_state=new_state,
            event_data=event_data or {},
            error_message=error_message,
            stack_trace=stack_trace,
        )

        self.db.add(log)
        await self.db.commit()
