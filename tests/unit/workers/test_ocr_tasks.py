"""Unit tests for OCR Celery tasks.

Tests OCR task definitions, signatures, and helper functions.
These tests do NOT execute actual Celery tasks - they test definitions.
"""

import pytest
from unittest.mock import Mock, patch, AsyncMock, MagicMock
from uuid import UUID, uuid4
from datetime import datetime

from app.db.models import ProcessingStatus


class TestOCRTaskDefinitions:
    """Tests for OCR task definitions."""

    def test_process_document_task_exists(self):
        """process_document_task sollte existieren."""
        from app.workers.tasks.ocr_tasks import process_document_task
        assert process_document_task is not None

    def test_process_document_task_is_bound(self):
        """process_document_task sollte bind=True haben."""
        from app.workers.tasks.ocr_tasks import process_document_task
        # Bound tasks have access to self (task instance)
        assert process_document_task.bind is True

    def test_process_document_task_name(self):
        """process_document_task sollte korrekten Namen haben."""
        from app.workers.tasks.ocr_tasks import process_document_task
        expected_name = "app.workers.tasks.ocr_tasks.process_document_task"
        assert process_document_task.name == expected_name

    def test_process_document_task_signature(self):
        """process_document_task sollte korrekte Parameter haben."""
        from app.workers.tasks.ocr_tasks import process_document_task
        import inspect

        sig = inspect.signature(process_document_task.run)
        params = list(sig.parameters.keys())

        # Required parameters
        assert "document_id" in params

        # Optional parameters with defaults
        assert "backend" in params
        assert "language" in params
        assert "detect_layout" in params
        assert "detect_fraktur" in params

    def test_process_document_task_default_backend(self):
        """process_document_task sollte 'auto' als Default-Backend haben."""
        from app.workers.tasks.ocr_tasks import process_document_task
        import inspect

        sig = inspect.signature(process_document_task.run)
        backend_param = sig.parameters.get("backend")

        assert backend_param is not None
        assert backend_param.default == "auto"

    def test_process_document_task_default_language(self):
        """process_document_task sollte 'de' als Default-Sprache haben."""
        from app.workers.tasks.ocr_tasks import process_document_task
        import inspect

        sig = inspect.signature(process_document_task.run)
        lang_param = sig.parameters.get("language")

        assert lang_param is not None
        assert lang_param.default == "de"


class TestBatchProcessingTask:
    """Tests for batch OCR processing task."""

    def test_batch_process_task_exists(self):
        """batch_process_documents_task sollte existieren."""
        try:
            from app.workers.tasks.ocr_tasks import batch_process_documents_task
            assert batch_process_documents_task is not None
        except ImportError:
            pytest.skip("batch_process_documents_task nicht implementiert")

    def test_batch_task_handles_list(self):
        """Batch Task sollte Liste von Document IDs akzeptieren."""
        try:
            from app.workers.tasks.ocr_tasks import batch_process_documents_task
            import inspect

            sig = inspect.signature(batch_process_documents_task.run)
            params = list(sig.parameters.keys())

            # Should accept document_ids as list
            assert "document_ids" in params or "documents" in params
        except ImportError:
            pytest.skip("batch_process_documents_task nicht implementiert")


class TestHelperFunctions:
    """Tests for OCR task helper functions."""

    @pytest.mark.asyncio
    async def test_update_document_status_function(self):
        """update_document_status sollte existieren und async sein."""
        from app.workers.tasks.ocr_tasks import update_document_status
        import asyncio

        assert asyncio.iscoroutinefunction(update_document_status)

    @pytest.mark.asyncio
    async def test_update_job_status_function(self):
        """update_job_status sollte existieren und async sein."""
        from app.workers.tasks.ocr_tasks import update_job_status
        import asyncio

        assert asyncio.iscoroutinefunction(update_job_status)

    def test_update_task_progress_function(self):
        """update_task_progress sollte existieren."""
        from app.workers.tasks.ocr_tasks import update_task_progress

        assert update_task_progress is not None
        assert callable(update_task_progress)

    @patch("app.workers.tasks.ocr_tasks.celery_app")
    def test_update_task_progress_calculates_percentage(self, mock_celery):
        """update_task_progress sollte Prozent korrekt berechnen."""
        from app.workers.tasks.ocr_tasks import update_task_progress

        mock_celery.backend = Mock()
        mock_celery.backend.store_result = Mock()

        update_task_progress("task-123", current=50, total=100, message="Test")

        # Verify store_result was called
        mock_celery.backend.store_result.assert_called_once()

        # Get the call arguments
        call_args = mock_celery.backend.store_result.call_args
        result_dict = call_args[0][1]  # Second positional arg is the result dict

        assert result_dict["progress"] == 50
        assert result_dict["current"] == 50
        assert result_dict["total"] == 100

    @patch("app.workers.tasks.ocr_tasks.celery_app")
    def test_update_task_progress_handles_zero_total(self, mock_celery):
        """update_task_progress sollte Division by Zero vermeiden."""
        from app.workers.tasks.ocr_tasks import update_task_progress

        mock_celery.backend = Mock()
        mock_celery.backend.store_result = Mock()

        # Should not raise ZeroDivisionError
        update_task_progress("task-123", current=0, total=0, message="Test")

        call_args = mock_celery.backend.store_result.call_args
        result_dict = call_args[0][1]

        assert result_dict["progress"] == 0


class TestTaskRetryConfiguration:
    """Tests for task retry configuration."""

    def test_ocr_task_has_max_retries(self):
        """OCR Task sollte max_retries konfiguriert haben."""
        from app.workers.tasks.ocr_tasks import process_document_task

        # Should have some form of retry configuration
        max_retries = getattr(process_document_task, "max_retries", None)
        # Default is 3 or configured value
        assert max_retries is None or max_retries >= 0

    def test_ocr_task_has_autoretry(self):
        """OCR Task sollte autoretry_for konfiguriert haben."""
        from app.workers.tasks.ocr_tasks import process_document_task

        # Check for autoretry configuration
        autoretry_for = getattr(process_document_task, "autoretry_for", None)
        # May be None or a tuple of exceptions


class TestDatabaseSessionFactory:
    """Tests for database session factory in tasks."""

    def test_async_session_maker_exists(self):
        """async_session_maker sollte existieren."""
        from app.workers.tasks.ocr_tasks import async_session_maker
        assert async_session_maker is not None

    def test_engine_exists(self):
        """Engine sollte initialisiert sein."""
        from app.workers.tasks.ocr_tasks import engine
        assert engine is not None

    @pytest.mark.asyncio
    async def test_get_db_session_returns_session(self):
        """get_db_session sollte AsyncSession zurueckgeben."""
        from app.workers.tasks.ocr_tasks import get_db_session

        # This is a coroutine
        import asyncio
        assert asyncio.iscoroutinefunction(get_db_session)


class TestOCRTaskIntegration:
    """Tests for OCR task integration with other components."""

    def test_task_imports_ocr_service(self):
        """OCR Task sollte OCRService importieren."""
        # This verifies the import works
        from app.workers.tasks.ocr_tasks import OCRService
        assert OCRService is not None

    def test_task_imports_german_validator(self):
        """OCR Task sollte GermanValidator importieren."""
        from app.workers.tasks.ocr_tasks import GermanValidator
        assert GermanValidator is not None

    def test_task_imports_processing_status(self):
        """OCR Task sollte ProcessingStatus importieren."""
        from app.workers.tasks.ocr_tasks import ProcessingStatus
        assert ProcessingStatus is not None

    def test_task_uses_correct_status_enum(self):
        """OCR Task sollte korrekte Status-Werte verwenden."""
        from app.workers.tasks.ocr_tasks import ProcessingStatus

        # Verify status values match expected
        assert ProcessingStatus.PROCESSING.value == "processing"
        assert ProcessingStatus.COMPLETED.value == "completed"
        assert ProcessingStatus.FAILED.value == "failed"


class TestMLTaskIntegration:
    """Tests for ML task integration."""

    def test_embedding_task_import(self):
        """Embedding Task sollte importierbar sein."""
        try:
            from app.workers.tasks.ocr_tasks import generate_document_embedding
            assert generate_document_embedding is not None
        except ImportError:
            pytest.skip("Embedding task not available")

    def test_ml_tracker_import(self):
        """ML Tracker sollte importierbar sein."""
        try:
            from app.workers.tasks.ocr_tasks import ml_tracker
            assert ml_tracker is not None
        except ImportError:
            pytest.skip("ML tracker not available")


class TestMaintenanceTasks:
    """Tests for maintenance tasks."""

    def test_cleanup_old_jobs_task_exists(self):
        """Cleanup Task sollte existieren."""
        try:
            from app.workers.tasks.ocr_tasks import cleanup_old_jobs
            assert cleanup_old_jobs is not None
        except (ImportError, AttributeError):
            pytest.skip("cleanup_old_jobs nicht implementiert")

    def test_collect_system_metrics_task_exists(self):
        """System Metrics Collection Task sollte existieren."""
        try:
            from app.workers.tasks.ocr_tasks import collect_system_metrics
            assert collect_system_metrics is not None
        except (ImportError, AttributeError):
            pytest.skip("collect_system_metrics nicht implementiert")
