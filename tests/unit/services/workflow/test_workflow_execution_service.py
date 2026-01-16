"""Tests fuer den WorkflowExecutionService.

Testet:
- Execution Start/Stop/Pause
- Step Transitions
- Error Recovery und Retry
- Timeout Handling
- Progress Tracking
- User Actions (pause, resume, cancel)
"""

import asyncio
import pytest
from datetime import datetime, timezone, timedelta
from uuid import uuid4
from unittest.mock import AsyncMock, MagicMock, patch
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Workflow, WorkflowExecution, WorkflowStep, WorkflowStepExecution
from app.services.workflow.workflow_execution_service import (
    WorkflowExecutionService,
    ExecutionStatus,
    ExecutionContext,
)


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def mock_db() -> AsyncMock:
    """Mock-Datenbank-Session."""
    db = AsyncMock(spec=AsyncSession)
    db.execute = AsyncMock()
    db.add = MagicMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    return db


@pytest.fixture
def service(mock_db: AsyncMock) -> WorkflowExecutionService:
    """WorkflowExecutionService mit Mock-DB."""
    return WorkflowExecutionService(db=mock_db)


@pytest.fixture
def sample_workflow() -> MagicMock:
    """Beispiel-Workflow fuer Tests."""
    workflow = MagicMock(spec=Workflow)
    workflow.id = uuid4()
    workflow.name = "Test-Workflow"
    workflow.is_active = True
    workflow.max_concurrent_executions = 5
    workflow.variables = {"default_timeout": 60}
    workflow.execution_count = 0
    workflow.steps = []
    return workflow


@pytest.fixture
def sample_workflow_with_steps(sample_workflow: MagicMock) -> MagicMock:
    """Workflow mit Steps."""
    step1 = MagicMock(spec=WorkflowStep)
    step1.id = uuid4()
    step1.step_order = 1
    step1.step_type = "action"
    step1.step_name = "validate"
    step1.retry_on_failure = True
    step1.max_retries = 3

    step2 = MagicMock(spec=WorkflowStep)
    step2.id = uuid4()
    step2.step_order = 2
    step2.step_type = "action"
    step2.step_name = "process"
    step2.retry_on_failure = False
    step2.max_retries = 0

    sample_workflow.steps = [step1, step2]
    return sample_workflow


@pytest.fixture
def sample_execution() -> MagicMock:
    """Beispiel-Execution fuer Tests."""
    execution = MagicMock(spec=WorkflowExecution)
    execution.id = uuid4()
    execution.workflow_id = uuid4()
    execution.triggered_by_id = uuid4()
    execution.document_id = None
    execution.trigger_type = "manual"
    execution.status = ExecutionStatus.RUNNING.value
    execution.trigger_data = {}
    execution.variables = {}
    execution.started_at = datetime.now(timezone.utc)
    execution.progress_percent = 0
    return execution


@pytest.fixture
def sample_context(sample_execution: MagicMock) -> ExecutionContext:
    """Beispiel-ExecutionContext."""
    return ExecutionContext(
        execution_id=sample_execution.id,
        workflow_id=sample_execution.workflow_id,
        user_id=sample_execution.triggered_by_id,
        variables={},
    )


# =============================================================================
# EXECUTION CONTEXT TESTS
# =============================================================================

class TestExecutionContext:
    """Tests fuer ExecutionContext Dataclass."""

    def test_context_creation(self) -> None:
        """ExecutionContext wird korrekt erstellt."""
        execution_id = uuid4()
        workflow_id = uuid4()
        user_id = uuid4()

        context = ExecutionContext(
            execution_id=execution_id,
            workflow_id=workflow_id,
            user_id=user_id,
        )

        assert context.execution_id == execution_id
        assert context.workflow_id == workflow_id
        assert context.user_id == user_id
        assert context.variables == {}
        assert context.step_outputs == {}
        assert context.is_paused is False
        assert context.error is None

    def test_context_with_document(self) -> None:
        """ExecutionContext mit Dokument-Daten."""
        document_id = uuid4()
        document_data = {"filename": "test.pdf", "size": 1024}

        context = ExecutionContext(
            execution_id=uuid4(),
            workflow_id=uuid4(),
            user_id=uuid4(),
            document_id=document_id,
            document_data=document_data,
        )

        assert context.document_id == document_id
        assert context.document_data == document_data

    def test_context_with_trigger_data(self) -> None:
        """ExecutionContext mit Trigger-Daten."""
        trigger_data = {"event": "document_uploaded", "source": "api"}

        context = ExecutionContext(
            execution_id=uuid4(),
            workflow_id=uuid4(),
            user_id=uuid4(),
            trigger_data=trigger_data,
        )

        assert context.trigger_data == trigger_data


# =============================================================================
# EXECUTION STATUS TESTS
# =============================================================================

class TestExecutionStatus:
    """Tests fuer ExecutionStatus Enum."""

    def test_all_status_values(self) -> None:
        """Alle Status-Werte existieren."""
        assert ExecutionStatus.PENDING.value == "pending"
        assert ExecutionStatus.RUNNING.value == "running"
        assert ExecutionStatus.PAUSED.value == "paused"
        assert ExecutionStatus.COMPLETED.value == "completed"
        assert ExecutionStatus.FAILED.value == "failed"
        assert ExecutionStatus.CANCELLED.value == "cancelled"
        assert ExecutionStatus.TIMEOUT.value == "timeout"

    def test_status_is_string_enum(self) -> None:
        """ExecutionStatus ist String-Enum."""
        assert isinstance(ExecutionStatus.RUNNING.value, str)
        assert ExecutionStatus.RUNNING == "running"


# =============================================================================
# START EXECUTION TESTS
# =============================================================================

class TestStartExecution:
    """Tests fuer Execution-Start."""

    @pytest.mark.asyncio
    async def test_start_execution_basic(
        self,
        service: WorkflowExecutionService,
        mock_db: AsyncMock,
        sample_workflow: MagicMock,
    ) -> None:
        """Einfache Execution wird gestartet."""
        user_id = uuid4()

        # Mock workflow query
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_workflow
        mock_db.execute.return_value = mock_result

        # Mock running count
        with patch.object(service, "_count_running_executions", return_value=0):
            # Patch asyncio.create_task to prevent background execution
            with patch("asyncio.create_task"):
                execution = await service.start_execution(
                    workflow_id=sample_workflow.id,
                    user_id=user_id,
                )

        mock_db.add.assert_called_once()
        mock_db.commit.assert_awaited()
        assert sample_workflow.execution_count == 1

    @pytest.mark.asyncio
    async def test_start_execution_inactive_workflow_fails(
        self,
        service: WorkflowExecutionService,
        mock_db: AsyncMock,
        sample_workflow: MagicMock,
    ) -> None:
        """Inaktiver Workflow kann nicht gestartet werden."""
        sample_workflow.is_active = False

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_workflow
        mock_db.execute.return_value = mock_result

        with pytest.raises(ValueError, match="nicht aktiv"):
            await service.start_execution(
                workflow_id=sample_workflow.id,
                user_id=uuid4(),
            )

    @pytest.mark.asyncio
    async def test_start_execution_workflow_not_found(
        self,
        service: WorkflowExecutionService,
        mock_db: AsyncMock,
    ) -> None:
        """Nicht existierender Workflow wirft Fehler."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        with pytest.raises(ValueError, match="nicht gefunden"):
            await service.start_execution(
                workflow_id=uuid4(),
                user_id=uuid4(),
            )

    @pytest.mark.asyncio
    async def test_start_execution_max_concurrent_reached(
        self,
        service: WorkflowExecutionService,
        mock_db: AsyncMock,
        sample_workflow: MagicMock,
    ) -> None:
        """Max parallele Ausfuehrungen werden geprüft."""
        sample_workflow.max_concurrent_executions = 2

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_workflow
        mock_db.execute.return_value = mock_result

        with patch.object(service, "_count_running_executions", return_value=2):
            with pytest.raises(ValueError, match="Max parallele"):
                await service.start_execution(
                    workflow_id=sample_workflow.id,
                    user_id=uuid4(),
                )

    @pytest.mark.asyncio
    async def test_start_execution_with_document(
        self,
        service: WorkflowExecutionService,
        mock_db: AsyncMock,
        sample_workflow: MagicMock,
    ) -> None:
        """Execution mit Dokument-ID startet."""
        document_id = uuid4()
        document_data = {"filename": "test.pdf"}

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_workflow
        mock_db.execute.return_value = mock_result

        with patch.object(service, "_count_running_executions", return_value=0):
            with patch.object(
                service, "_load_document_data", return_value=document_data
            ):
                with patch("asyncio.create_task"):
                    execution = await service.start_execution(
                        workflow_id=sample_workflow.id,
                        user_id=uuid4(),
                        document_id=document_id,
                    )

        mock_db.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_start_execution_with_variables(
        self,
        service: WorkflowExecutionService,
        mock_db: AsyncMock,
        sample_workflow: MagicMock,
    ) -> None:
        """Execution mit initialen Variablen startet."""
        initial_vars = {"custom_var": "value"}

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_workflow
        mock_db.execute.return_value = mock_result

        with patch.object(service, "_count_running_executions", return_value=0):
            with patch("asyncio.create_task"):
                execution = await service.start_execution(
                    workflow_id=sample_workflow.id,
                    user_id=uuid4(),
                    initial_variables=initial_vars,
                )

        mock_db.add.assert_called_once()


# =============================================================================
# PAUSE EXECUTION TESTS
# =============================================================================

class TestPauseExecution:
    """Tests fuer Execution-Pause."""

    @pytest.mark.asyncio
    async def test_pause_running_execution(
        self,
        service: WorkflowExecutionService,
        mock_db: AsyncMock,
        sample_execution: MagicMock,
    ) -> None:
        """Laufende Execution wird pausiert."""
        user_id = sample_execution.triggered_by_id

        with patch.object(
            service, "_get_execution", return_value=sample_execution
        ):
            result = await service.pause_execution(
                execution_id=sample_execution.id,
                user_id=user_id,
            )

        assert result is True
        mock_db.execute.assert_awaited()
        mock_db.commit.assert_awaited()

    @pytest.mark.asyncio
    async def test_pause_non_running_execution_fails(
        self,
        service: WorkflowExecutionService,
        mock_db: AsyncMock,
        sample_execution: MagicMock,
    ) -> None:
        """Nicht-laufende Execution kann nicht pausiert werden."""
        sample_execution.status = ExecutionStatus.PAUSED.value

        with patch.object(
            service, "_get_execution", return_value=sample_execution
        ):
            result = await service.pause_execution(
                execution_id=sample_execution.id,
                user_id=sample_execution.triggered_by_id,
            )

        assert result is False

    @pytest.mark.asyncio
    async def test_pause_execution_not_found(
        self,
        service: WorkflowExecutionService,
        mock_db: AsyncMock,
    ) -> None:
        """Nicht existierende Execution gibt False zurueck."""
        with patch.object(service, "_get_execution", return_value=None):
            result = await service.pause_execution(
                execution_id=uuid4(),
                user_id=uuid4(),
            )

        assert result is False


# =============================================================================
# RESUME EXECUTION TESTS
# =============================================================================

class TestResumeExecution:
    """Tests fuer Execution-Resume."""

    @pytest.mark.asyncio
    async def test_resume_paused_execution(
        self,
        service: WorkflowExecutionService,
        mock_db: AsyncMock,
        sample_execution: MagicMock,
        sample_workflow: MagicMock,
    ) -> None:
        """Pausierte Execution wird fortgesetzt."""
        sample_execution.status = ExecutionStatus.PAUSED.value

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_workflow
        mock_db.execute.return_value = mock_result

        with patch.object(
            service, "_get_execution", return_value=sample_execution
        ):
            with patch("asyncio.create_task"):
                result = await service.resume_execution(
                    execution_id=sample_execution.id,
                    user_id=sample_execution.triggered_by_id,
                )

        assert result is True

    @pytest.mark.asyncio
    async def test_resume_non_paused_execution_fails(
        self,
        service: WorkflowExecutionService,
        mock_db: AsyncMock,
        sample_execution: MagicMock,
    ) -> None:
        """Nicht-pausierte Execution kann nicht fortgesetzt werden."""
        sample_execution.status = ExecutionStatus.RUNNING.value

        with patch.object(
            service, "_get_execution", return_value=sample_execution
        ):
            result = await service.resume_execution(
                execution_id=sample_execution.id,
                user_id=sample_execution.triggered_by_id,
            )

        assert result is False

    @pytest.mark.asyncio
    async def test_resume_execution_workflow_not_found(
        self,
        service: WorkflowExecutionService,
        mock_db: AsyncMock,
        sample_execution: MagicMock,
    ) -> None:
        """Resume schlaegt fehl wenn Workflow nicht gefunden."""
        sample_execution.status = ExecutionStatus.PAUSED.value

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        with patch.object(
            service, "_get_execution", return_value=sample_execution
        ):
            result = await service.resume_execution(
                execution_id=sample_execution.id,
                user_id=sample_execution.triggered_by_id,
            )

        assert result is False


# =============================================================================
# CANCEL EXECUTION TESTS
# =============================================================================

class TestCancelExecution:
    """Tests fuer Execution-Abbruch."""

    @pytest.mark.asyncio
    async def test_cancel_running_execution(
        self,
        service: WorkflowExecutionService,
        mock_db: AsyncMock,
        sample_execution: MagicMock,
    ) -> None:
        """Laufende Execution wird abgebrochen."""
        with patch.object(
            service, "_get_execution", return_value=sample_execution
        ):
            result = await service.cancel_execution(
                execution_id=sample_execution.id,
                user_id=sample_execution.triggered_by_id,
            )

        assert result is True
        mock_db.execute.assert_awaited()
        mock_db.commit.assert_awaited()

    @pytest.mark.asyncio
    async def test_cancel_paused_execution(
        self,
        service: WorkflowExecutionService,
        mock_db: AsyncMock,
        sample_execution: MagicMock,
    ) -> None:
        """Pausierte Execution kann abgebrochen werden."""
        sample_execution.status = ExecutionStatus.PAUSED.value

        with patch.object(
            service, "_get_execution", return_value=sample_execution
        ):
            result = await service.cancel_execution(
                execution_id=sample_execution.id,
                user_id=sample_execution.triggered_by_id,
            )

        assert result is True

    @pytest.mark.asyncio
    async def test_cancel_pending_execution(
        self,
        service: WorkflowExecutionService,
        mock_db: AsyncMock,
        sample_execution: MagicMock,
    ) -> None:
        """Pending Execution kann abgebrochen werden."""
        sample_execution.status = ExecutionStatus.PENDING.value

        with patch.object(
            service, "_get_execution", return_value=sample_execution
        ):
            result = await service.cancel_execution(
                execution_id=sample_execution.id,
                user_id=sample_execution.triggered_by_id,
            )

        assert result is True

    @pytest.mark.asyncio
    async def test_cancel_completed_execution_fails(
        self,
        service: WorkflowExecutionService,
        mock_db: AsyncMock,
        sample_execution: MagicMock,
    ) -> None:
        """Abgeschlossene Execution kann nicht abgebrochen werden."""
        sample_execution.status = ExecutionStatus.COMPLETED.value

        with patch.object(
            service, "_get_execution", return_value=sample_execution
        ):
            result = await service.cancel_execution(
                execution_id=sample_execution.id,
                user_id=sample_execution.triggered_by_id,
            )

        assert result is False

    @pytest.mark.asyncio
    async def test_cancel_failed_execution_fails(
        self,
        service: WorkflowExecutionService,
        mock_db: AsyncMock,
        sample_execution: MagicMock,
    ) -> None:
        """Fehlgeschlagene Execution kann nicht abgebrochen werden."""
        sample_execution.status = ExecutionStatus.FAILED.value

        with patch.object(
            service, "_get_execution", return_value=sample_execution
        ):
            result = await service.cancel_execution(
                execution_id=sample_execution.id,
                user_id=sample_execution.triggered_by_id,
            )

        assert result is False


# =============================================================================
# RETRY EXECUTION TESTS
# =============================================================================

class TestRetryExecution:
    """Tests fuer Execution-Retry."""

    @pytest.mark.asyncio
    async def test_retry_failed_execution(
        self,
        service: WorkflowExecutionService,
        mock_db: AsyncMock,
        sample_execution: MagicMock,
    ) -> None:
        """Fehlgeschlagene Execution wird wiederholt."""
        sample_execution.status = ExecutionStatus.FAILED.value
        sample_execution.trigger_data = {"source": "api"}
        sample_execution.variables = {"var1": "value1"}

        with patch.object(
            service, "_get_execution", return_value=sample_execution
        ):
            with patch.object(
                service, "start_execution", return_value=sample_execution
            ) as mock_start:
                result = await service.retry_execution(
                    execution_id=sample_execution.id,
                    user_id=sample_execution.triggered_by_id,
                )

                mock_start.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_retry_non_failed_execution_fails(
        self,
        service: WorkflowExecutionService,
        mock_db: AsyncMock,
        sample_execution: MagicMock,
    ) -> None:
        """Nicht-fehlgeschlagene Execution kann nicht wiederholt werden."""
        sample_execution.status = ExecutionStatus.COMPLETED.value

        with patch.object(
            service, "_get_execution", return_value=sample_execution
        ):
            result = await service.retry_execution(
                execution_id=sample_execution.id,
                user_id=sample_execution.triggered_by_id,
            )

        assert result is None


# =============================================================================
# QUERY METHODS TESTS
# =============================================================================

class TestQueryMethods:
    """Tests fuer Query-Methoden."""

    @pytest.mark.asyncio
    async def test_get_execution(
        self,
        service: WorkflowExecutionService,
        mock_db: AsyncMock,
        sample_execution: MagicMock,
    ) -> None:
        """Execution wird abgerufen."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_execution
        mock_db.execute.return_value = mock_result

        result = await service.get_execution(sample_execution.id)

        assert result == sample_execution

    @pytest.mark.asyncio
    async def test_get_execution_with_user_filter(
        self,
        service: WorkflowExecutionService,
        mock_db: AsyncMock,
        sample_execution: MagicMock,
    ) -> None:
        """Execution wird mit User-Filter abgerufen."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_execution
        mock_db.execute.return_value = mock_result

        result = await service.get_execution(
            sample_execution.id,
            user_id=sample_execution.triggered_by_id,
        )

        assert result == sample_execution

    @pytest.mark.asyncio
    async def test_list_executions(
        self,
        service: WorkflowExecutionService,
        mock_db: AsyncMock,
        sample_execution: MagicMock,
    ) -> None:
        """Executions werden gelistet."""
        # Mock count
        mock_count_result = MagicMock()
        mock_count_result.scalar.return_value = 1

        # Mock data
        mock_data_result = MagicMock()
        mock_data_result.scalars.return_value.all.return_value = [sample_execution]

        mock_db.execute.side_effect = [mock_count_result, mock_data_result]

        executions, total = await service.list_executions()

        assert total == 1
        assert len(executions) == 1
        assert executions[0] == sample_execution

    @pytest.mark.asyncio
    async def test_list_executions_with_filters(
        self,
        service: WorkflowExecutionService,
        mock_db: AsyncMock,
        sample_execution: MagicMock,
    ) -> None:
        """Executions werden mit Filtern gelistet."""
        mock_count_result = MagicMock()
        mock_count_result.scalar.return_value = 5

        mock_data_result = MagicMock()
        mock_data_result.scalars.return_value.all.return_value = [sample_execution] * 5

        mock_db.execute.side_effect = [mock_count_result, mock_data_result]

        executions, total = await service.list_executions(
            workflow_id=sample_execution.workflow_id,
            status=ExecutionStatus.RUNNING.value,
            offset=0,
            limit=10,
        )

        assert total == 5
        assert len(executions) == 5

    @pytest.mark.asyncio
    async def test_get_step_executions(
        self,
        service: WorkflowExecutionService,
        mock_db: AsyncMock,
    ) -> None:
        """Step-Executions werden abgerufen."""
        execution_id = uuid4()

        step_exec1 = MagicMock(spec=WorkflowStepExecution)
        step_exec1.id = uuid4()
        step_exec2 = MagicMock(spec=WorkflowStepExecution)
        step_exec2.id = uuid4()

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [step_exec1, step_exec2]
        mock_db.execute.return_value = mock_result

        result = await service.get_step_executions(execution_id)

        assert len(result) == 2


# =============================================================================
# HELPER METHODS TESTS
# =============================================================================

class TestHelperMethods:
    """Tests fuer Hilfsmethoden."""

    @pytest.mark.asyncio
    async def test_count_running_executions(
        self,
        service: WorkflowExecutionService,
        mock_db: AsyncMock,
    ) -> None:
        """Laufende Executions werden gezaehlt."""
        workflow_id = uuid4()

        mock_result = MagicMock()
        mock_result.scalar.return_value = 3
        mock_db.execute.return_value = mock_result

        count = await service._count_running_executions(workflow_id)

        assert count == 3

    @pytest.mark.asyncio
    async def test_count_running_executions_zero(
        self,
        service: WorkflowExecutionService,
        mock_db: AsyncMock,
    ) -> None:
        """Null bei keinen laufenden Executions."""
        workflow_id = uuid4()

        mock_result = MagicMock()
        mock_result.scalar.return_value = None
        mock_db.execute.return_value = mock_result

        count = await service._count_running_executions(workflow_id)

        assert count == 0

    @pytest.mark.asyncio
    async def test_load_document_data(
        self,
        service: WorkflowExecutionService,
        mock_db: AsyncMock,
    ) -> None:
        """Dokument-Daten werden geladen."""
        document_id = uuid4()

        mock_document = MagicMock()
        mock_document.id = document_id
        mock_document.filename = "test.pdf"
        mock_document.file_extension = "pdf"
        mock_document.file_size = 1024
        mock_document.mime_type = "application/pdf"
        mock_document.status = "processed"
        mock_document.document_type = "invoice"
        mock_document.folder_id = uuid4()
        mock_document.created_at = datetime.now(timezone.utc)
        mock_document.processed_at = datetime.now(timezone.utc)
        mock_document.extracted_data = {"amount": 100}

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_document
        mock_db.execute.return_value = mock_result

        data = await service._load_document_data(document_id)

        assert data is not None
        assert data["filename"] == "test.pdf"
        assert data["file_size"] == 1024

    @pytest.mark.asyncio
    async def test_load_document_data_not_found(
        self,
        service: WorkflowExecutionService,
        mock_db: AsyncMock,
    ) -> None:
        """None bei nicht gefundenem Dokument."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        data = await service._load_document_data(uuid4())

        assert data is None


# =============================================================================
# STATE MANAGEMENT TESTS
# =============================================================================

class TestStateManagement:
    """Tests fuer internes State-Management."""

    @pytest.mark.asyncio
    async def test_update_progress(
        self,
        service: WorkflowExecutionService,
        mock_db: AsyncMock,
    ) -> None:
        """Progress wird aktualisiert."""
        execution_id = uuid4()
        step_id = uuid4()

        await service._update_progress(execution_id, 50, step_id)

        mock_db.execute.assert_awaited()
        mock_db.commit.assert_awaited()

    @pytest.mark.asyncio
    async def test_complete_execution(
        self,
        service: WorkflowExecutionService,
        mock_db: AsyncMock,
        sample_execution: MagicMock,
        sample_context: ExecutionContext,
    ) -> None:
        """Execution wird als abgeschlossen markiert."""
        sample_context.step_outputs = {"validate": {"success": True}}

        await service._complete_execution(sample_execution, sample_context)

        mock_db.execute.assert_awaited()
        mock_db.commit.assert_awaited()

    @pytest.mark.asyncio
    async def test_fail_execution(
        self,
        service: WorkflowExecutionService,
        mock_db: AsyncMock,
        sample_execution: MagicMock,
        sample_context: ExecutionContext,
    ) -> None:
        """Execution wird als fehlgeschlagen markiert."""
        error_msg = "Verarbeitung fehlgeschlagen"

        await service._fail_execution(sample_execution, sample_context, error_msg)

        mock_db.execute.assert_awaited()
        mock_db.commit.assert_awaited()

    @pytest.mark.asyncio
    async def test_cancel_execution_internal(
        self,
        service: WorkflowExecutionService,
        mock_db: AsyncMock,
        sample_execution: MagicMock,
    ) -> None:
        """Interne Execution-Stornierung."""
        await service._cancel_execution(sample_execution)

        mock_db.execute.assert_awaited()
        mock_db.commit.assert_awaited()


# =============================================================================
# STEP EXECUTOR TESTS
# =============================================================================

class TestStepExecutorIntegration:
    """Tests fuer Step-Executor Integration."""

    def test_set_step_executor(
        self,
        service: WorkflowExecutionService,
    ) -> None:
        """Step-Executor kann gesetzt werden."""
        mock_executor = MagicMock()

        service.set_step_executor(mock_executor)

        assert service.step_executor == mock_executor

    def test_step_executor_initially_none(
        self,
        service: WorkflowExecutionService,
    ) -> None:
        """Step-Executor ist initial None."""
        assert service.step_executor is None
