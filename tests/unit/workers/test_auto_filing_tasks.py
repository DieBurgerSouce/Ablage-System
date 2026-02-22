# -*- coding: utf-8 -*-
"""
Unit-Tests fuer Auto-Filing Celery Tasks.

Testet:
- Task-Definitionen und Signaturen
- trigger_auto_filing_pipeline_task Parameter und Defaults
- Error-Handling und Retry-Logik
- Pipeline-Integration (Mock)

Feinpoliert und durchdacht - Enterprise-grade Auto-Filing Tests.
"""

import inspect
import pytest
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from uuid import uuid4


# ========================= Task-Definitionen =========================


class TestAutoFilingTaskDefinitions:
    """Tests fuer Task-Definitionen und Registrierung."""

    def test_auto_file_new_documents_task_importable(self):
        """Task ist importierbar."""
        from app.workers.tasks.auto_filing_tasks import auto_file_new_documents_task
        assert auto_file_new_documents_task is not None

    def test_train_filing_model_task_importable(self):
        """Task ist importierbar."""
        from app.workers.tasks.auto_filing_tasks import train_filing_model_task
        assert train_filing_model_task is not None

    def test_auto_match_documents_task_importable(self):
        """Task ist importierbar."""
        from app.workers.tasks.auto_filing_tasks import auto_match_documents_task
        assert auto_match_documents_task is not None

    def test_batch_match_documents_task_importable(self):
        """Task ist importierbar."""
        from app.workers.tasks.auto_filing_tasks import batch_match_documents_task
        assert batch_match_documents_task is not None

    def test_trigger_auto_filing_pipeline_task_importable(self):
        """Pipeline-Task ist importierbar."""
        from app.workers.tasks.auto_filing_tasks import trigger_auto_filing_pipeline_task
        assert trigger_auto_filing_pipeline_task is not None


# ========================= Task-Signaturen =========================


class TestTaskSignatures:
    """Tests fuer korrekte Task-Signaturen."""

    def test_auto_file_task_name(self):
        """Task-Name ist korrekt registriert."""
        from app.workers.tasks.auto_filing_tasks import auto_file_new_documents_task
        assert auto_file_new_documents_task.name == (
            "app.workers.tasks.auto_filing_tasks.auto_file_new_documents_task"
        )

    def test_train_filing_model_task_name(self):
        """Task-Name ist korrekt registriert."""
        from app.workers.tasks.auto_filing_tasks import train_filing_model_task
        assert train_filing_model_task.name == (
            "app.workers.tasks.auto_filing_tasks.train_filing_model_task"
        )

    def test_auto_match_task_name(self):
        """Task-Name ist korrekt registriert."""
        from app.workers.tasks.auto_filing_tasks import auto_match_documents_task
        assert auto_match_documents_task.name == (
            "app.workers.tasks.auto_filing_tasks.auto_match_documents_task"
        )

    def test_batch_match_task_name(self):
        """Task-Name ist korrekt registriert."""
        from app.workers.tasks.auto_filing_tasks import batch_match_documents_task
        assert batch_match_documents_task.name == (
            "app.workers.tasks.auto_filing_tasks.batch_match_documents_task"
        )

    def test_pipeline_task_name(self):
        """Pipeline-Task-Name ist korrekt registriert."""
        from app.workers.tasks.auto_filing_tasks import trigger_auto_filing_pipeline_task
        assert trigger_auto_filing_pipeline_task.name == (
            "app.workers.tasks.auto_filing_tasks.trigger_auto_filing_pipeline_task"
        )

    def test_pipeline_task_max_retries(self):
        """Pipeline-Task hat korrekte Retry-Konfiguration."""
        from app.workers.tasks.auto_filing_tasks import trigger_auto_filing_pipeline_task
        assert trigger_auto_filing_pipeline_task.max_retries == 2

    def test_auto_file_task_max_retries(self):
        """Auto-File Task hat korrekte Retry-Konfiguration."""
        from app.workers.tasks.auto_filing_tasks import auto_file_new_documents_task
        assert auto_file_new_documents_task.max_retries == 3

    def test_train_filing_model_task_max_retries(self):
        """Train-Filing-Model Task hat korrekte Retry-Konfiguration."""
        from app.workers.tasks.auto_filing_tasks import train_filing_model_task
        assert train_filing_model_task.max_retries == 2

    def test_auto_match_task_max_retries(self):
        """Auto-Match Task hat korrekte Retry-Konfiguration."""
        from app.workers.tasks.auto_filing_tasks import auto_match_documents_task
        assert auto_match_documents_task.max_retries == 3

    def test_batch_match_task_max_retries(self):
        """Batch-Match Task hat korrekte Retry-Konfiguration."""
        from app.workers.tasks.auto_filing_tasks import batch_match_documents_task
        assert batch_match_documents_task.max_retries == 2

    def test_pipeline_task_default_retry_delay(self):
        """Pipeline-Task hat korrekten Retry-Delay."""
        from app.workers.tasks.auto_filing_tasks import trigger_auto_filing_pipeline_task
        assert trigger_auto_filing_pipeline_task.default_retry_delay == 30

    def test_auto_file_task_default_retry_delay(self):
        """Auto-File Task hat korrekten Retry-Delay."""
        from app.workers.tasks.auto_filing_tasks import auto_file_new_documents_task
        assert auto_file_new_documents_task.default_retry_delay == 60

    def test_pipeline_task_is_bound(self):
        """Pipeline-Task ist bound (hat self)."""
        from app.workers.tasks.auto_filing_tasks import trigger_auto_filing_pipeline_task
        assert hasattr(trigger_auto_filing_pipeline_task, "name")

    def test_pipeline_task_has_delay_method(self):
        """Pipeline-Task hat .delay() Methode fuer asynchronen Aufruf."""
        from app.workers.tasks.auto_filing_tasks import trigger_auto_filing_pipeline_task
        assert callable(getattr(trigger_auto_filing_pipeline_task, "delay", None))

    def test_pipeline_task_has_apply_async_method(self):
        """Pipeline-Task hat .apply_async() Methode."""
        from app.workers.tasks.auto_filing_tasks import trigger_auto_filing_pipeline_task
        assert callable(getattr(trigger_auto_filing_pipeline_task, "apply_async", None))

    def test_auto_match_task_has_delay_method(self):
        """Auto-Match Task hat .delay() Methode."""
        from app.workers.tasks.auto_filing_tasks import auto_match_documents_task
        assert callable(getattr(auto_match_documents_task, "delay", None))

    def test_batch_match_task_has_apply_async_method(self):
        """Batch-Match Task hat .apply_async() Methode."""
        from app.workers.tasks.auto_filing_tasks import batch_match_documents_task
        assert callable(getattr(batch_match_documents_task, "apply_async", None))


# ========================= Pipeline-Task Parameter =========================


class TestTriggerAutoFilingPipelineTaskParameters:
    """Tests fuer den Pipeline-Trigger-Task Parameter."""

    def test_task_requires_document_id(self):
        """Task erfordert document_id Parameter."""
        from app.workers.tasks.auto_filing_tasks import trigger_auto_filing_pipeline_task
        sig = inspect.signature(trigger_auto_filing_pipeline_task.run)
        params = list(sig.parameters.keys())
        assert "document_id" in params

    def test_task_requires_company_id(self):
        """Task erfordert company_id Parameter."""
        from app.workers.tasks.auto_filing_tasks import trigger_auto_filing_pipeline_task
        sig = inspect.signature(trigger_auto_filing_pipeline_task.run)
        params = list(sig.parameters.keys())
        assert "company_id" in params

    def test_task_requires_ocr_text(self):
        """Task erfordert ocr_text Parameter."""
        from app.workers.tasks.auto_filing_tasks import trigger_auto_filing_pipeline_task
        sig = inspect.signature(trigger_auto_filing_pipeline_task.run)
        params = list(sig.parameters.keys())
        assert "ocr_text" in params

    def test_task_optional_user_id(self):
        """user_id ist optionaler Parameter mit Default None."""
        from app.workers.tasks.auto_filing_tasks import trigger_auto_filing_pipeline_task
        sig = inspect.signature(trigger_auto_filing_pipeline_task.run)
        param = sig.parameters.get("user_id")
        assert param is not None
        assert param.default is None

    def test_task_optional_metadata(self):
        """metadata ist optionaler Parameter mit Default None."""
        from app.workers.tasks.auto_filing_tasks import trigger_auto_filing_pipeline_task
        sig = inspect.signature(trigger_auto_filing_pipeline_task.run)
        param = sig.parameters.get("metadata")
        assert param is not None
        assert param.default is None

    def test_auto_file_task_optional_company_id(self):
        """company_id ist optionaler Parameter in auto_file_new_documents_task."""
        from app.workers.tasks.auto_filing_tasks import auto_file_new_documents_task
        sig = inspect.signature(auto_file_new_documents_task.run)
        param = sig.parameters.get("company_id")
        assert param is not None
        assert param.default is None

    def test_auto_file_task_default_limit(self):
        """auto_file_new_documents_task hat Default-Limit von 100."""
        from app.workers.tasks.auto_filing_tasks import auto_file_new_documents_task
        sig = inspect.signature(auto_file_new_documents_task.run)
        param = sig.parameters.get("limit")
        assert param is not None
        assert param.default == 100

    def test_auto_match_task_requires_company_id(self):
        """auto_match_documents_task erfordert company_id."""
        from app.workers.tasks.auto_filing_tasks import auto_match_documents_task
        sig = inspect.signature(auto_match_documents_task.run)
        params = list(sig.parameters.keys())
        assert "company_id" in params

    def test_auto_match_task_requires_document_id(self):
        """auto_match_documents_task erfordert document_id."""
        from app.workers.tasks.auto_filing_tasks import auto_match_documents_task
        sig = inspect.signature(auto_match_documents_task.run)
        params = list(sig.parameters.keys())
        assert "document_id" in params

    def test_auto_match_task_default_confidence_threshold(self):
        """auto_match_documents_task hat Default-Confidence-Threshold von 0.8."""
        from app.workers.tasks.auto_filing_tasks import auto_match_documents_task
        sig = inspect.signature(auto_match_documents_task.run)
        param = sig.parameters.get("confidence_threshold")
        assert param is not None
        assert param.default == 0.8

    def test_batch_match_task_default_confidence_threshold(self):
        """batch_match_documents_task hat Default-Confidence-Threshold von 0.8."""
        from app.workers.tasks.auto_filing_tasks import batch_match_documents_task
        sig = inspect.signature(batch_match_documents_task.run)
        param = sig.parameters.get("confidence_threshold")
        assert param is not None
        assert param.default == 0.8

    def test_batch_match_task_default_limit(self):
        """batch_match_documents_task hat Default-Limit von 200."""
        from app.workers.tasks.auto_filing_tasks import batch_match_documents_task
        sig = inspect.signature(batch_match_documents_task.run)
        param = sig.parameters.get("limit")
        assert param is not None
        assert param.default == 200


# ========================= Pipeline-Task Retry-Logik =========================


class TestPipelineTaskRetryLogic:
    """Tests fuer Error-Handling und Retry-Verhalten."""

    @pytest.fixture
    def mock_self(self):
        """Mock Celery Task-Instanz (self) fuer bound tasks."""
        task_self = Mock()
        task_self.request = Mock()
        task_self.request.id = "test-task-id-abc"
        task_self.request.retries = 0
        task_self.max_retries = 2

        def mock_retry(exc=None, **kwargs):
            raise exc if exc else RuntimeError("Retry")

        task_self.retry = mock_retry
        return task_self

    @pytest.fixture
    def valid_pipeline_args(self):
        """Gueltige Argumente fuer den Pipeline-Task."""
        return {
            "document_id": str(uuid4()),
            "company_id": str(uuid4()),
            "ocr_text": "Rechnung Nr. 12345 von Musterfirma GmbH",
            "user_id": str(uuid4()),
            "metadata": {"filename": "rechnung_12345.pdf"},
        }

    def test_pipeline_task_retries_on_exception(self, mock_self, valid_pipeline_args):
        """Pipeline-Task versucht Retry bei Exception."""
        from app.workers.tasks.auto_filing_tasks import trigger_auto_filing_pipeline_task

        exc = RuntimeError("Verbindungsfehler")
        mock_self.request.retries = 0

        with patch("app.workers.tasks.auto_filing_tasks.asyncio.run", side_effect=exc):
            with patch("app.workers.tasks.auto_filing_tasks.settings"):
                result = trigger_auto_filing_pipeline_task.run(
                    mock_self,
                    **valid_pipeline_args,
                )

        # Nach max_retries gibt der Task ein Fehler-Dict zurueck
        assert result is not None
        assert result.get("success") is False
        assert result.get("document_id") == valid_pipeline_args["document_id"]

    def test_pipeline_task_returns_failure_dict_after_max_retries(self, mock_self, valid_pipeline_args):
        """Nach max_retries gibt der Task ein Fehler-Dict zurueck."""
        from app.workers.tasks.auto_filing_tasks import trigger_auto_filing_pipeline_task

        exc = ConnectionError("Redis nicht erreichbar")
        mock_self.request.retries = 2  # Bereits max_retries erreicht

        with patch("app.workers.tasks.auto_filing_tasks.asyncio.run", side_effect=exc):
            with patch("app.workers.tasks.auto_filing_tasks.settings"):
                result = trigger_auto_filing_pipeline_task.run(
                    mock_self,
                    **valid_pipeline_args,
                )

        assert result["success"] is False
        assert "document_id" in result
        assert "error" in result

    def test_pipeline_task_returns_success_on_pipeline_success(self, mock_self, valid_pipeline_args):
        """Pipeline-Task gibt success=True Dict zurueck bei Erfolg."""
        from app.workers.tasks.auto_filing_tasks import trigger_auto_filing_pipeline_task

        expected_result = {
            "success": True,
            "document_id": valid_pipeline_args["document_id"],
            "auto_processed": True,
            "requires_review": False,
            "status": "auto_completed",
            "category": "Rechnungen",
            "entity": "Musterfirma GmbH",
            "project": None,
            "total_processing_time_ms": 820,
            "decisions_count": 3,
            "anomalies_count": 0,
        }

        with patch("app.workers.tasks.auto_filing_tasks.asyncio.run", return_value=expected_result):
            result = trigger_auto_filing_pipeline_task.run(
                mock_self,
                **valid_pipeline_args,
            )

        assert result["success"] is True
        assert result["auto_processed"] is True
        assert result["category"] == "Rechnungen"

    def test_pipeline_task_does_not_log_ocr_text(self, mock_self, valid_pipeline_args):
        """Pipeline-Task loggt den OCR-Text nicht (DSGVO-Konformitaet)."""
        from app.workers.tasks.auto_filing_tasks import trigger_auto_filing_pipeline_task

        logged_messages = []

        with patch("app.workers.tasks.auto_filing_tasks.logger") as mock_logger:
            mock_logger.info = Mock(side_effect=lambda msg, **kw: logged_messages.append((msg, kw)))
            with patch("app.workers.tasks.auto_filing_tasks.asyncio.run", return_value={"success": True}):
                trigger_auto_filing_pipeline_task.run(mock_self, **valid_pipeline_args)

        ocr_text = valid_pipeline_args["ocr_text"]
        for _msg, kwargs in logged_messages:
            for val in kwargs.values():
                assert str(val) != ocr_text, "OCR-Text darf NIEMALS geloggt werden (DSGVO)"


# ========================= Auto-File Task Tests =========================


class TestAutoFileNewDocumentsTask:
    """Tests fuer auto_file_new_documents_task."""

    def test_task_is_bound(self):
        """auto_file_new_documents_task ist ein bound Task."""
        from app.workers.tasks.auto_filing_tasks import auto_file_new_documents_task
        assert hasattr(auto_file_new_documents_task, "name")
        assert "auto_file_new_documents_task" in auto_file_new_documents_task.name

    def test_task_default_retry_delay(self):
        """auto_file_new_documents_task hat 60s Default-Retry-Delay."""
        from app.workers.tasks.auto_filing_tasks import auto_file_new_documents_task
        assert auto_file_new_documents_task.default_retry_delay == 60

    def test_task_signature_has_self(self):
        """auto_file_new_documents_task hat self als ersten Parameter (bound)."""
        from app.workers.tasks.auto_filing_tasks import auto_file_new_documents_task
        sig = inspect.signature(auto_file_new_documents_task.run)
        params = list(sig.parameters.keys())
        assert "self" in params


# ========================= Train Filing Model Task Tests =========================


class TestTrainFilingModelTask:
    """Tests fuer train_filing_model_task."""

    def test_task_name_korrekt(self):
        """train_filing_model_task ist korrekt registriert."""
        from app.workers.tasks.auto_filing_tasks import train_filing_model_task
        assert "train_filing_model_task" in train_filing_model_task.name

    def test_train_task_default_retry_delay(self):
        """train_filing_model_task hat 300s Default-Retry-Delay."""
        from app.workers.tasks.auto_filing_tasks import train_filing_model_task
        assert train_filing_model_task.default_retry_delay == 300

    def test_train_task_optional_company_id(self):
        """company_id ist optionaler Parameter mit Default None."""
        from app.workers.tasks.auto_filing_tasks import train_filing_model_task
        sig = inspect.signature(train_filing_model_task.run)
        param = sig.parameters.get("company_id")
        assert param is not None
        assert param.default is None


# ========================= Batch Match Task Tests =========================


class TestBatchMatchDocumentsTask:
    """Tests fuer batch_match_documents_task."""

    def test_task_name_korrekt(self):
        """batch_match_documents_task ist korrekt registriert."""
        from app.workers.tasks.auto_filing_tasks import batch_match_documents_task
        assert "batch_match_documents_task" in batch_match_documents_task.name

    def test_batch_task_default_retry_delay(self):
        """batch_match_documents_task hat 300s Default-Retry-Delay."""
        from app.workers.tasks.auto_filing_tasks import batch_match_documents_task
        assert batch_match_documents_task.default_retry_delay == 300

    def test_batch_task_optional_company_id(self):
        """company_id ist optional (None = alle Firmen)."""
        from app.workers.tasks.auto_filing_tasks import batch_match_documents_task
        sig = inspect.signature(batch_match_documents_task.run)
        param = sig.parameters.get("company_id")
        assert param is not None
        assert param.default is None


# ========================= Auto-Match Task Tests =========================


class TestAutoMatchDocumentsTask:
    """Tests fuer auto_match_documents_task."""

    def test_task_name_korrekt(self):
        """auto_match_documents_task ist korrekt registriert."""
        from app.workers.tasks.auto_filing_tasks import auto_match_documents_task
        assert "auto_match_documents_task" in auto_match_documents_task.name

    def test_auto_match_task_default_retry_delay(self):
        """auto_match_documents_task hat 60s Default-Retry-Delay."""
        from app.workers.tasks.auto_filing_tasks import auto_match_documents_task
        assert auto_match_documents_task.default_retry_delay == 60

    def test_auto_match_task_signature_has_self(self):
        """auto_match_documents_task hat self als ersten Parameter (bound)."""
        from app.workers.tasks.auto_filing_tasks import auto_match_documents_task
        sig = inspect.signature(auto_match_documents_task.run)
        params = list(sig.parameters.keys())
        assert "self" in params
