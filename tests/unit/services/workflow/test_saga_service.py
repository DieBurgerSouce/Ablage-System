# -*- coding: utf-8 -*-
"""Unit-Tests fuer SagaService.

Testet:
- Saga-Erstellung mit Steps
- Forward-Execution
- Compensation bei Fehler
- Dead Letter Queue
- Transaktionslog
- State Machine
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock, patch, call
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_workflow_versioning import (
    Saga,
    SagaStatus,
    SagaStep,
    SagaStepStatus,
    SagaTransactionLog,
)
from app.services.workflow.saga_service import (
    SagaService,
    StepHandlerRegistry,
)


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def mock_db() -> AsyncMock:
    """Erstellt eine Mock-Datenbank-Session."""
    db = AsyncMock(spec=AsyncSession)
    db.add = MagicMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    db.execute = AsyncMock()
    return db


@pytest.fixture
def handler_registry() -> StepHandlerRegistry:
    """Erstellt eine Handler-Registry."""
    return StepHandlerRegistry()


@pytest.fixture
def saga_service(
    mock_db: AsyncMock,
    handler_registry: StepHandlerRegistry,
) -> SagaService:
    """Erstellt einen SagaService."""
    return SagaService(db=mock_db, handler_registry=handler_registry)


@pytest.fixture
def sample_steps() -> List[Dict[str, Any]]:
    """Erstellt Sample-Step-Definitionen."""
    return [
        {
            "name": "Dokument verschieben",
            "action_type": "move_document",
            "action_params": {"document_id": str(uuid4()), "folder_id": str(uuid4())},
            "compensation_type": "restore_document",
            "compensation_params": {"original_folder_id": str(uuid4())},
        },
        {
            "name": "Benachrichtigung senden",
            "action_type": "send_notification",
            "action_params": {"user_id": str(uuid4()), "message": "Dokument verschoben"},
            "compensation_type": "cancel_notification",
            "compensation_params": {},
        },
        {
            "name": "Status aktualisieren",
            "action_type": "update_status",
            "action_params": {"status": "processed"},
            # Keine Compensation
        },
    ]


@pytest.fixture
def sample_saga() -> Saga:
    """Erstellt eine Sample-Saga."""
    saga = MagicMock(spec=Saga)
    saga.id = uuid4()
    saga.company_id = uuid4()
    saga.name = "Test Saga"
    saga.status = SagaStatus.PENDING.value
    saga.total_steps = 3
    saga.current_step_index = 0
    saga.retry_count = 0
    saga.max_retries = 3
    saga.context_data = {}
    saga.steps = []
    saga.in_dead_letter_queue = False
    saga.steps_compensated = 0
    return saga


# ============================================================================
# Test: StepHandlerRegistry
# ============================================================================


class TestStepHandlerRegistry:
    """Tests fuer StepHandlerRegistry."""

    def test_register_action_handler(
        self,
        handler_registry: StepHandlerRegistry,
    ) -> None:
        """Testet das Registrieren eines Action-Handlers."""

        async def mock_handler(**kwargs):
            return {"success": True}

        handler_registry.register_action("test_action", mock_handler)

        assert handler_registry.get_action_handler("test_action") is mock_handler

    def test_register_compensation_handler(
        self,
        handler_registry: StepHandlerRegistry,
    ) -> None:
        """Testet das Registrieren eines Compensation-Handlers."""

        async def mock_handler(**kwargs):
            return {"compensated": True}

        handler_registry.register_compensation("test_compensation", mock_handler)

        assert handler_registry.get_compensation_handler("test_compensation") is mock_handler

    def test_get_nonexistent_handler(
        self,
        handler_registry: StepHandlerRegistry,
    ) -> None:
        """Testet das Abrufen eines nicht existierenden Handlers."""
        assert handler_registry.get_action_handler("nonexistent") is None
        assert handler_registry.get_compensation_handler("nonexistent") is None


# ============================================================================
# Test: Saga Creation
# ============================================================================


class TestSagaCreation:
    """Tests fuer Saga-Erstellung."""

    @pytest.mark.asyncio
    async def test_create_saga(
        self,
        saga_service: SagaService,
        mock_db: AsyncMock,
        sample_steps: List[Dict[str, Any]],
    ) -> None:
        """Testet das Erstellen einer Saga."""
        company_id = uuid4()
        user_id = uuid4()

        saga = await saga_service.create_saga(
            company_id=company_id,
            user_id=user_id,
            name="Test Saga",
            steps=sample_steps,
            description="Testbeschreibung",
        )

        assert saga is not None
        # Saga + 3 Steps + 1 Log = 5 adds
        assert mock_db.add.call_count >= 4
        assert mock_db.commit.called

    @pytest.mark.asyncio
    async def test_create_saga_with_context(
        self,
        saga_service: SagaService,
        mock_db: AsyncMock,
    ) -> None:
        """Testet das Erstellen einer Saga mit Kontext-Daten."""
        company_id = uuid4()
        user_id = uuid4()
        context = {"document_id": str(uuid4()), "user_name": "Test User"}

        saga = await saga_service.create_saga(
            company_id=company_id,
            user_id=user_id,
            name="Kontext-Saga",
            steps=[{"name": "Step 1", "action_type": "test"}],
            context_data=context,
        )

        assert saga is not None
        assert mock_db.add.called


# ============================================================================
# Test: Step Execution
# ============================================================================


class TestStepExecution:
    """Tests fuer Step-Ausfuehrung."""

    @pytest.mark.asyncio
    async def test_execute_step_success(
        self,
        saga_service: SagaService,
        mock_db: AsyncMock,
        sample_saga: Saga,
    ) -> None:
        """Testet erfolgreiche Step-Ausfuehrung."""
        step = MagicMock(spec=SagaStep)
        step.id = uuid4()
        step.name = "Test Step"
        step.action_type = "test_action"
        step.action_params = {}
        step.status = SagaStepStatus.PENDING.value
        step.timeout_seconds = 300
        step.can_retry = True
        step.retry_count = 0
        step.max_retries = 3

        # Handler registrieren
        async def success_handler(**kwargs):
            return {"result": "success"}

        saga_service.handler_registry.register_action("test_action", success_handler)

        success = await saga_service._execute_step(sample_saga, step)

        assert success is True
        assert step.status == SagaStepStatus.COMPLETED.value
        assert step.result_data == {"result": "success"}

    @pytest.mark.asyncio
    async def test_execute_step_failure_with_retry(
        self,
        saga_service: SagaService,
        mock_db: AsyncMock,
        sample_saga: Saga,
    ) -> None:
        """Testet Step-Fehler mit Retry."""
        step = MagicMock(spec=SagaStep)
        step.id = uuid4()
        step.name = "Failing Step"
        step.action_type = "failing_action"
        step.action_params = {}
        step.status = SagaStepStatus.PENDING.value
        step.timeout_seconds = 300
        step.retry_count = 0
        step.max_retries = 2
        step.retry_delay_seconds = 0  # Keine Verzoegerung im Test
        step.can_retry = True

        call_count = 0

        async def failing_handler(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise Exception("Temporaerer Fehler")
            return {"recovered": True}

        saga_service.handler_registry.register_action("failing_action", failing_handler)

        # Patch asyncio.sleep um Tests schneller zu machen
        with patch("asyncio.sleep", new_callable=AsyncMock):
            success = await saga_service._execute_step(sample_saga, step)

        assert success is True
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_execute_step_timeout(
        self,
        saga_service: SagaService,
        mock_db: AsyncMock,
        sample_saga: Saga,
    ) -> None:
        """Testet Step-Timeout."""
        step = MagicMock(spec=SagaStep)
        step.id = uuid4()
        step.name = "Slow Step"
        step.action_type = "slow_action"
        step.action_params = {}
        step.status = SagaStepStatus.PENDING.value
        step.timeout_seconds = 0.01  # Sehr kurzes Timeout
        step.can_retry = False
        step.retry_count = 0
        step.max_retries = 0

        async def slow_handler(**kwargs):
            await asyncio.sleep(1)  # Laenger als Timeout
            return {"done": True}

        saga_service.handler_registry.register_action("slow_action", slow_handler)

        success = await saga_service._execute_step(sample_saga, step)

        assert success is False
        assert step.status == SagaStepStatus.FAILED.value
        assert "Timeout" in step.error_message


# ============================================================================
# Test: Compensation
# ============================================================================


class TestCompensation:
    """Tests fuer Compensation."""

    @pytest.mark.asyncio
    async def test_compensate_step_success(
        self,
        saga_service: SagaService,
        mock_db: AsyncMock,
        sample_saga: Saga,
    ) -> None:
        """Testet erfolgreiche Compensation."""
        step = MagicMock(spec=SagaStep)
        step.id = uuid4()
        step.name = "Completed Step"
        step.status = SagaStepStatus.COMPLETED.value
        step.compensation_type = "undo_action"
        step.compensation_params = {"restore": True}
        step.has_compensation = True
        step.result_data = {"original": "data"}
        step.timeout_seconds = 300
        step.max_retries = 3
        step.compensation_retry_count = 0

        async def compensation_handler(**kwargs):
            return {"undone": True}

        saga_service.handler_registry.register_compensation(
            "undo_action", compensation_handler
        )

        success = await saga_service._compensate_step(sample_saga, step)

        assert success is True
        assert step.status == SagaStepStatus.COMPENSATED.value

    @pytest.mark.asyncio
    async def test_compensate_step_without_compensation(
        self,
        saga_service: SagaService,
        mock_db: AsyncMock,
        sample_saga: Saga,
    ) -> None:
        """Testet Compensation ohne definierten Handler."""
        step = MagicMock(spec=SagaStep)
        step.id = uuid4()
        step.name = "No Compensation Step"
        step.status = SagaStepStatus.COMPLETED.value
        step.compensation_type = None
        step.has_compensation = False

        success = await saga_service._compensate_step(sample_saga, step)

        assert success is True
        assert step.status == SagaStepStatus.COMPENSATED.value

    @pytest.mark.asyncio
    async def test_compensate_step_failure(
        self,
        saga_service: SagaService,
        mock_db: AsyncMock,
        sample_saga: Saga,
    ) -> None:
        """Testet fehlgeschlagene Compensation."""
        step = MagicMock(spec=SagaStep)
        step.id = uuid4()
        step.name = "Failing Compensation"
        step.status = SagaStepStatus.COMPLETED.value
        step.compensation_type = "failing_undo"
        step.compensation_params = {}
        step.has_compensation = True
        step.result_data = {}
        step.timeout_seconds = 300
        step.max_retries = 1
        step.compensation_retry_count = 0
        step.retry_delay_seconds = 60  # echtes int fuer Exponential-Backoff-min()

        async def failing_compensation(**kwargs):
            raise Exception("Compensation fehlgeschlagen")

        saga_service.handler_registry.register_compensation(
            "failing_undo", failing_compensation
        )

        # Patch sleep
        with patch("asyncio.sleep", new_callable=AsyncMock):
            success = await saga_service._compensate_step(sample_saga, step)

        assert success is False
        assert step.status == SagaStepStatus.COMPENSATION_FAILED.value


# ============================================================================
# Test: Saga Status
# ============================================================================


class TestSagaStatus:
    """Tests fuer Saga-Status-Properties."""

    def test_saga_is_running(self) -> None:
        """Testet is_running Property."""
        saga = Saga()
        saga.status = SagaStatus.RUNNING.value
        assert saga.is_running is True

        saga.status = SagaStatus.COMPENSATING.value
        assert saga.is_running is True

        saga.status = SagaStatus.COMPLETED.value
        assert saga.is_running is False

    def test_saga_is_completed(self) -> None:
        """Testet is_completed Property."""
        saga = Saga()
        saga.status = SagaStatus.COMPLETED.value
        assert saga.is_completed is True

        saga.status = SagaStatus.RUNNING.value
        assert saga.is_completed is False

    def test_saga_needs_compensation(self) -> None:
        """Testet needs_compensation Property."""
        saga = Saga()
        saga.status = SagaStatus.FAILED.value
        assert saga.needs_compensation is True

        saga.status = SagaStatus.COMPLETED.value
        assert saga.needs_compensation is False

    def test_saga_progress_percent(self) -> None:
        """Testet progress_percent Property."""
        saga = Saga()
        saga.total_steps = 4
        saga.current_step_index = 2

        assert saga.progress_percent == 50

        saga.current_step_index = 4
        assert saga.progress_percent == 100

    def test_saga_progress_percent_zero_steps(self) -> None:
        """Testet progress_percent bei 0 Steps."""
        saga = Saga()
        saga.total_steps = 0
        saga.current_step_index = 0

        assert saga.progress_percent == 0


# ============================================================================
# Test: SagaStep Properties
# ============================================================================


class TestSagaStepProperties:
    """Tests fuer SagaStep-Properties."""

    def test_step_is_completed(self) -> None:
        """Testet is_completed Property."""
        step = SagaStep()
        step.status = SagaStepStatus.COMPLETED.value
        assert step.is_completed is True

        step.status = SagaStepStatus.FAILED.value
        assert step.is_completed is False

    def test_step_is_compensated(self) -> None:
        """Testet is_compensated Property."""
        step = SagaStep()
        step.status = SagaStepStatus.COMPENSATED.value
        assert step.is_compensated is True

        step.status = SagaStepStatus.COMPLETED.value
        assert step.is_compensated is False

    def test_step_can_retry(self) -> None:
        """Testet can_retry Property."""
        step = SagaStep()
        step.retry_count = 0
        step.max_retries = 3
        assert step.can_retry is True

        step.retry_count = 3
        assert step.can_retry is False

        step.retry_count = 4
        assert step.can_retry is False


# ============================================================================
# Test: State Diagram
# ============================================================================


class TestStateDiagram:
    """Tests fuer State-Diagramm-Generierung."""

    @pytest.mark.asyncio
    async def test_get_saga_state_diagram(
        self,
        saga_service: SagaService,
        mock_db: AsyncMock,
    ) -> None:
        """Testet die Generierung eines State-Diagramms."""
        saga_id = uuid4()
        company_id = uuid4()

        # Mock Saga mit Steps
        saga = MagicMock(spec=Saga)
        saga.id = saga_id
        saga.name = "Test Saga"
        saga.status = SagaStatus.RUNNING.value
        saga.started_at = datetime.now(timezone.utc)

        step1 = MagicMock(spec=SagaStep)
        step1.step_order = 1
        step1.name = "Step 1"
        step1.status = SagaStepStatus.COMPLETED.value
        step1.action_type = "action1"
        step1.has_compensation = True
        step1.duration_ms = 100

        step2 = MagicMock(spec=SagaStep)
        step2.step_order = 2
        step2.name = "Step 2"
        step2.status = SagaStepStatus.RUNNING.value
        step2.action_type = "action2"
        step2.has_compensation = False
        step2.duration_ms = None

        saga.steps = [step1, step2]

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = saga
        mock_db.execute.return_value = mock_result

        diagram = await saga_service.get_saga_state_diagram(saga_id, company_id)

        assert diagram is not None
        assert diagram["saga_id"] == str(saga_id)
        assert diagram["name"] == "Test Saga"
        assert diagram["status"] == SagaStatus.RUNNING.value
        assert len(diagram["nodes"]) == 4  # start + 2 steps + end
        assert len(diagram["edges"]) == 3  # 3 forward edges


# ============================================================================
# Test: Statistics
# ============================================================================


class TestSagaStatistics:
    """Tests fuer Saga-Statistiken."""

    @pytest.mark.asyncio
    async def test_get_saga_statistics(
        self,
        saga_service: SagaService,
        mock_db: AsyncMock,
    ) -> None:
        """Testet das Abrufen von Saga-Statistiken."""
        company_id = uuid4()

        # Mock Ergebnisse
        mock_total = MagicMock()
        mock_total.scalar.return_value = 100

        mock_status = MagicMock()
        mock_status.fetchall.return_value = [
            (SagaStatus.COMPLETED.value, 80),
            (SagaStatus.FAILED.value, 10),
            (SagaStatus.COMPENSATED.value, 5),
            (SagaStatus.PARTIALLY_COMPENSATED.value, 5),
        ]

        mock_dlq = MagicMock()
        mock_dlq.scalar.return_value = 15

        mock_db.execute.side_effect = [mock_total, mock_status, mock_dlq]

        stats = await saga_service.get_saga_statistics(company_id)

        assert stats["total"] == 100
        assert stats["completed"] == 80
        assert stats["failed"] == 10
        assert stats["compensated"] == 5
        assert stats["dead_letter_queue"] == 15
        assert stats["success_rate"] == 80.0
