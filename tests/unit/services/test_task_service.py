# -*- coding: utf-8 -*-
"""
Unit-Tests für Task Service.

Testet:
- Task-Einreichung (einzeln und Batch)
- Task-Status-Abfrage
- Task-Abbruch
- Prioritäts-Management
- Fehlerbehandlung

Feinpoliert und durchdacht - Umfassende Task-Service-Tests.
"""

import pytest
from datetime import datetime, timezone
from uuid import UUID, uuid4
from typing import Dict, Any, List
from unittest.mock import Mock, AsyncMock, patch, MagicMock

import sys
from pathlib import Path

# Add app to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))


# ========================= Test Fixtures =========================


@pytest.fixture
def mock_db_session():
    """Create mock database session."""
    session = AsyncMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    session.add = Mock()
    session.refresh = AsyncMock()
    return session


@pytest.fixture
def sample_document_id() -> UUID:
    """Provide sample document ID."""
    return uuid4()


@pytest.fixture
def mock_document(sample_document_id):
    """Create mock document."""
    doc = Mock()
    doc.id = sample_document_id
    doc.filename = "test_doc.pdf"
    doc.file_path = "/uploads/test_doc.pdf"
    doc.status = "uploaded"
    return doc


@pytest.fixture
def mock_celery_task():
    """Create mock Celery task result."""
    task = Mock()
    task.id = "task-12345-abcde"
    task.state = "PENDING"
    task.status = "PENDING"
    task.info = None
    task.result = None
    task.ready = Mock(return_value=False)
    task.successful = Mock(return_value=False)
    task.failed = Mock(return_value=False)
    task.revoke = Mock()
    return task


@pytest.fixture
def mock_celery_app(mock_celery_task):
    """Create mock Celery app."""
    app = Mock()

    # Mock AsyncResult
    mock_async_result = Mock(return_value=mock_celery_task)
    app.AsyncResult = mock_async_result

    return app


# ========================= Task Submission Tests =========================


class TestTaskSubmission:
    """Tests für Task-Einreichung."""

    @pytest.mark.asyncio
    async def test_submit_document_task_success(
        self,
        mock_db_session,
        mock_document,
        mock_celery_task,
        sample_document_id
    ):
        """Test erfolgreiche Task-Einreichung."""
        # Mock document query result
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = mock_document
        mock_db_session.execute.return_value = mock_result

        with patch("app.services.task_service.celery_app") as mock_celery, \
             patch("app.services.task_service.process_document_task") as mock_task:

            mock_task.apply_async.return_value = mock_celery_task

            from app.services.task_service import TaskService
            service = TaskService()

            result = await service.submit_document_task(
                session=mock_db_session,
                document_id=sample_document_id,
                backend="deepseek",
                language="de",
                priority="high"
            )

            assert result["task_id"] == "task-12345-abcde"
            assert result["status"] == "queued"
            assert result["priority"] == "high"
            mock_db_session.add.assert_called()
            mock_db_session.commit.assert_called()

    @pytest.mark.asyncio
    async def test_submit_document_task_not_found(
        self,
        mock_db_session,
        sample_document_id
    ):
        """Test Fehler wenn Dokument nicht gefunden."""
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute.return_value = mock_result

        with patch("app.services.task_service.celery_app"):

            from app.services.task_service import TaskService
            service = TaskService()

            with pytest.raises(ValueError, match="nicht gefunden"):
                await service.submit_document_task(
                    session=mock_db_session,
                    document_id=sample_document_id
                )

    @pytest.mark.asyncio
    async def test_submit_batch_task_success(
        self,
        mock_db_session,
        mock_celery_task
    ):
        """Test erfolgreiche Batch-Task-Einreichung."""
        document_ids = [uuid4() for _ in range(3)]

        with patch("app.services.task_service.celery_app"), \
             patch("app.services.task_service.batch_process_task") as mock_task:

            mock_task.apply_async.return_value = mock_celery_task

            from app.services.task_service import TaskService
            service = TaskService()

            result = await service.submit_batch_task(
                session=mock_db_session,
                document_ids=document_ids,
                backend="surya"
            )

            assert result["task_id"] == "task-12345-abcde"
            assert result["document_count"] == 3


# ========================= Task Status Tests =========================


class TestTaskStatus:
    """Tests für Task-Status-Abfragen."""

    def test_get_task_status_pending(self, mock_celery_task):
        """Test Status-Abfrage für wartende Task."""
        mock_celery_task.state = "PENDING"
        mock_celery_task.info = None

        # Mock states module to have PROGRESS attribute
        mock_states = Mock()
        mock_states.PROGRESS = "PROGRESS"

        with patch("app.services.task_service.celery_app") as mock_celery, \
             patch("app.services.task_service.AsyncResult") as mock_async_result, \
             patch("app.services.task_service.states", mock_states):
            mock_async_result.return_value = mock_celery_task

            from app.services.task_service import TaskService
            service = TaskService()

            # get_task_status is synchronous in the implementation
            status = service.get_task_status("task-12345")

            # Implementation returns "state" not "status"
            assert status["state"] == "PENDING"
            assert status["task_id"] == "task-12345"

    def test_get_task_status_processing(self, mock_celery_task):
        """Test Status-Abfrage für laufende Task."""
        mock_celery_task.state = "PROGRESS"
        mock_celery_task.info = {"progress": 50, "current": 2, "total": 4, "message": "Verarbeitung..."}
        mock_celery_task.ready.return_value = False

        # Mock states module to have PROGRESS attribute
        mock_states = Mock()
        mock_states.PROGRESS = "PROGRESS"

        with patch("app.services.task_service.celery_app") as mock_celery, \
             patch("app.services.task_service.AsyncResult") as mock_async_result, \
             patch("app.services.task_service.states", mock_states):
            mock_async_result.return_value = mock_celery_task

            from app.services.task_service import TaskService
            service = TaskService()

            status = service.get_task_status("task-12345")

            assert status["state"] == "PROGRESS"
            assert "progress" in status

    def test_get_task_status_success(self, mock_celery_task):
        """Test Status-Abfrage für erfolgreiche Task."""
        mock_celery_task.state = "SUCCESS"
        mock_celery_task.ready.return_value = True
        mock_celery_task.successful.return_value = True
        mock_celery_task.failed.return_value = False
        mock_celery_task.result = {
            "text": "Extrahierter Text",
            "confidence": 0.95
        }

        # Mock states module to have PROGRESS attribute
        mock_states = Mock()
        mock_states.PROGRESS = "PROGRESS"

        with patch("app.services.task_service.celery_app") as mock_celery, \
             patch("app.services.task_service.AsyncResult") as mock_async_result, \
             patch("app.services.task_service.states", mock_states):
            mock_async_result.return_value = mock_celery_task

            from app.services.task_service import TaskService
            service = TaskService()

            status = service.get_task_status("task-12345")

            assert status["state"] == "SUCCESS"
            assert "result" in status

    def test_get_task_status_failure(self, mock_celery_task):
        """Test Status-Abfrage für fehlgeschlagene Task."""
        mock_celery_task.state = "FAILURE"
        mock_celery_task.ready.return_value = True
        mock_celery_task.failed.return_value = True
        mock_celery_task.successful.return_value = False
        mock_celery_task.info = "OCR fehlgeschlagen"

        # Mock states module to have PROGRESS attribute
        mock_states = Mock()
        mock_states.PROGRESS = "PROGRESS"

        with patch("app.services.task_service.celery_app") as mock_celery, \
             patch("app.services.task_service.AsyncResult") as mock_async_result, \
             patch("app.services.task_service.states", mock_states):
            mock_async_result.return_value = mock_celery_task

            from app.services.task_service import TaskService
            service = TaskService()

            status = service.get_task_status("task-12345")

            assert status["state"] == "FAILURE"
            assert "error" in status


# ========================= Task Cancellation Tests =========================


class TestTaskCancellation:
    """Tests für Task-Abbruch."""

    def test_cancel_task_success(self, mock_celery_task):
        """Test erfolgreicher Task-Abbruch."""
        mock_celery_task.state = "PENDING"
        mock_celery_task.ready.return_value = False  # Task not yet complete

        with patch("app.services.task_service.celery_app") as mock_celery, \
             patch("app.services.task_service.AsyncResult") as mock_async_result:
            mock_async_result.return_value = mock_celery_task

            from app.services.task_service import TaskService
            service = TaskService()

            # cancel_task is synchronous in the implementation
            result = service.cancel_task("task-12345")

            mock_celery_task.revoke.assert_called_once_with(terminate=True)
            assert result["cancelled"] is True

    def test_cancel_completed_task(self, mock_celery_task):
        """Test Abbruch einer bereits abgeschlossenen Task."""
        mock_celery_task.state = "SUCCESS"
        mock_celery_task.ready.return_value = True  # Task already complete

        with patch("app.services.task_service.celery_app") as mock_celery, \
             patch("app.services.task_service.AsyncResult") as mock_async_result:
            mock_async_result.return_value = mock_celery_task

            from app.services.task_service import TaskService
            service = TaskService()

            result = service.cancel_task("task-12345")

            # Should not revoke completed tasks
            assert result["cancelled"] is False
            # Implementation uses message with "bereits abgeschlossen"
            assert "abgeschlossen" in result.get("message", "")


# ========================= Priority Tests =========================


class TestPriority:
    """Tests für Prioritäts-Management."""

    def test_get_priority_value_high(self):
        """Test Prioritätswert für 'high'."""
        with patch("app.services.task_service.celery_app"):
            from app.services.task_service import TaskService
            service = TaskService()

            value = service._get_priority_value("high")
            # Implementation: high=9, normal=5, low=1 (higher value = higher priority)
            assert value == 9

    def test_get_priority_value_normal(self):
        """Test Prioritätswert für 'normal'."""
        with patch("app.services.task_service.celery_app"):
            from app.services.task_service import TaskService
            service = TaskService()

            value = service._get_priority_value("normal")
            assert value == 5

    def test_get_priority_value_low(self):
        """Test Prioritätswert für 'low'."""
        with patch("app.services.task_service.celery_app"):
            from app.services.task_service import TaskService
            service = TaskService()

            value = service._get_priority_value("low")
            assert value == 1

    def test_get_celery_priority_high(self):
        """Test Celery-Priorität für 'high'."""
        with patch("app.services.task_service.celery_app"):
            from app.services.task_service import TaskService
            service = TaskService()

            priority = service._get_celery_priority("high")
            # Implementation returns same as _get_priority_value (9 for high)
            assert priority == 9


# ========================= Result Retrieval Tests =========================


class TestResultRetrieval:
    """Tests für Task-Ergebnis-Abruf."""

    def test_get_task_result_ready(self, mock_celery_task):
        """Test Ergebnis-Abruf für abgeschlossene Task."""
        mock_celery_task.ready.return_value = True
        mock_celery_task.result = {"text": "Extrahierter Text"}

        with patch("app.services.task_service.celery_app") as mock_celery, \
             patch("app.services.task_service.AsyncResult") as mock_async_result:
            mock_async_result.return_value = mock_celery_task

            from app.services.task_service import TaskService
            service = TaskService()

            result = service.get_task_result("task-12345")

            assert result == {"text": "Extrahierter Text"}

    def test_get_task_result_not_ready(self, mock_celery_task):
        """Test Ergebnis-Abruf für noch nicht abgeschlossene Task."""
        mock_celery_task.ready.return_value = False

        with patch("app.services.task_service.celery_app") as mock_celery, \
             patch("app.services.task_service.AsyncResult") as mock_async_result:
            mock_async_result.return_value = mock_celery_task

            from app.services.task_service import TaskService
            service = TaskService()

            with pytest.raises(ValueError, match="nicht abgeschlossen"):
                service.get_task_result("task-12345")


# ========================= User Task History Tests =========================


class TestUserTaskHistory:
    """Tests für Benutzer-Task-Historie."""

    @pytest.mark.asyncio
    async def test_get_user_tasks(self, mock_db_session, mock_celery_task):
        """Test Abruf der Benutzer-Tasks."""
        user_id = uuid4()

        # Mock query results - jobs without worker_id to avoid get_task_status call
        mock_jobs = [
            Mock(
                id=uuid4(),
                document_id=uuid4(),
                job_type="ocr",
                backend="surya",
                status="completed",
                priority=5,
                created_at=datetime.now(timezone.utc),
                started_at=datetime.now(timezone.utc),
                completed_at=datetime.now(timezone.utc),
                worker_id=None,  # No worker_id to avoid get_task_status call
            )
            for _ in range(3)
        ]

        mock_result = Mock()
        mock_result.scalars.return_value.all.return_value = mock_jobs
        mock_db_session.execute.return_value = mock_result

        with patch("app.services.task_service.celery_app"):
            from app.services.task_service import TaskService
            service = TaskService()

            tasks = await service.get_user_tasks(
                session=mock_db_session,
                user_id=user_id,
                limit=10
            )

            assert len(tasks) == 3


# ========================= Edge Cases =========================


class TestEdgeCases:
    """Tests für Grenzfälle."""

    @pytest.mark.asyncio
    async def test_submit_task_with_string_uuid(
        self,
        mock_db_session,
        mock_document,
        mock_celery_task
    ):
        """Test Task-Einreichung mit String-UUID."""
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = mock_document
        mock_db_session.execute.return_value = mock_result

        with patch("app.services.task_service.celery_app"), \
             patch("app.services.task_service.process_document_task") as mock_task:

            mock_task.apply_async.return_value = mock_celery_task

            from app.services.task_service import TaskService
            service = TaskService()

            # Pass string UUID instead of UUID object
            result = await service.submit_document_task(
                session=mock_db_session,
                document_id=str(uuid4()),  # String
                backend="auto"
            )

            assert "task_id" in result

    def test_get_status_invalid_task_id(self, mock_celery_task):
        """Test Status-Abfrage mit ungültiger Task-ID."""
        mock_celery_task.state = "PENDING"
        mock_celery_task.ready.return_value = False

        # Mock states module to have PROGRESS attribute
        mock_states = Mock()
        mock_states.PROGRESS = "PROGRESS"

        with patch("app.services.task_service.celery_app") as mock_celery, \
             patch("app.services.task_service.AsyncResult") as mock_async_result, \
             patch("app.services.task_service.states", mock_states):
            mock_async_result.return_value = mock_celery_task

            from app.services.task_service import TaskService
            service = TaskService()

            # Even invalid IDs return pending status in Celery
            status = service.get_task_status("invalid-id")

            assert status["state"] == "PENDING"

    @pytest.mark.asyncio
    async def test_submit_batch_empty_list(self, mock_db_session, mock_celery_task):
        """Test Batch-Einreichung mit leerer Liste."""
        with patch("app.services.task_service.celery_app"), \
             patch("app.services.task_service.batch_process_task") as mock_task:

            mock_task.apply_async.return_value = mock_celery_task

            from app.services.task_service import TaskService
            service = TaskService()

            result = await service.submit_batch_task(
                session=mock_db_session,
                document_ids=[],
                backend="auto"
            )

            assert result["document_count"] == 0
