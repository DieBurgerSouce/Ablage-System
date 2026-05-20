# -*- coding: utf-8 -*-
"""
Tests fuer Document Intelligence Celery Tasks.

Testet:
- Task Registrierung
- Task Optionen und Einstellungen
- Helper Funktionen

HINWEIS: Die Document Intelligence Tasks importieren Services dynamisch INSIDE der Funktionen.
Diese Tests fokussieren auf die statisch testbaren Aspekte (Konfiguration, Registrierung).
"""

import pytest
from unittest.mock import patch, MagicMock


class TestTaskRegistration:
    """Tests fuer Task Registrierung."""

    def test_detect_document_groups_is_registered(self):
        """Sollte detect_document_groups Task registriert haben."""
        from app.workers.tasks.document_intelligence_tasks import detect_document_groups

        assert detect_document_groups is not None
        assert hasattr(detect_document_groups, 'name')
        assert detect_document_groups.name == "app.workers.tasks.document_intelligence_tasks.detect_document_groups"

    def test_batch_detect_groups_is_registered(self):
        """Sollte batch_detect_groups_by_folder Task registriert haben."""
        from app.workers.tasks.document_intelligence_tasks import batch_detect_groups_by_folder

        assert batch_detect_groups_by_folder is not None
        assert hasattr(batch_detect_groups_by_folder, 'name')
        assert batch_detect_groups_by_folder.name == "app.workers.tasks.document_intelligence_tasks.batch_detect_groups_by_folder"

    def test_extract_entities_is_registered(self):
        """Sollte extract_entities_from_document Task registriert haben."""
        from app.workers.tasks.document_intelligence_tasks import extract_entities_from_document

        assert extract_entities_from_document is not None
        assert hasattr(extract_entities_from_document, 'name')
        assert extract_entities_from_document.name == "app.workers.tasks.document_intelligence_tasks.extract_entities_from_document"

    def test_batch_extract_entities_is_registered(self):
        """Sollte batch_extract_entities Task registriert haben."""
        from app.workers.tasks.document_intelligence_tasks import batch_extract_entities

        assert batch_extract_entities is not None
        assert hasattr(batch_extract_entities, 'name')
        assert batch_extract_entities.name == "app.workers.tasks.document_intelligence_tasks.batch_extract_entities"

    def test_run_pipeline_is_registered(self):
        """Sollte run_document_intelligence_pipeline Task registriert haben."""
        from app.workers.tasks.document_intelligence_tasks import run_document_intelligence_pipeline

        assert run_document_intelligence_pipeline is not None
        assert hasattr(run_document_intelligence_pipeline, 'name')
        assert run_document_intelligence_pipeline.name == "app.workers.tasks.document_intelligence_tasks.run_document_intelligence_pipeline"

    def test_update_metrics_is_registered(self):
        """Sollte update_intelligence_metrics Task registriert haben."""
        from app.workers.tasks.document_intelligence_tasks import update_intelligence_metrics

        assert update_intelligence_metrics is not None
        assert hasattr(update_intelligence_metrics, 'name')
        assert update_intelligence_metrics.name == "app.workers.tasks.document_intelligence_tasks.update_intelligence_metrics"


class TestTaskOptions:
    """Tests fuer Task Optionen."""

    def test_detect_groups_has_time_limits(self):
        """Sollte detect_document_groups Zeitlimits haben."""
        from app.workers.tasks.document_intelligence_tasks import detect_document_groups

        assert detect_document_groups.soft_time_limit == 300  # 5 Minuten
        assert detect_document_groups.time_limit == 360

    def test_batch_detect_has_long_time_limits(self):
        """Sollte batch_detect_groups_by_folder lange Zeitlimits haben."""
        from app.workers.tasks.document_intelligence_tasks import batch_detect_groups_by_folder

        assert batch_detect_groups_by_folder.soft_time_limit == 1800  # 30 Minuten
        assert batch_detect_groups_by_folder.time_limit == 1860

    def test_extract_entities_has_time_limits(self):
        """Sollte extract_entities_from_document kurze Zeitlimits haben."""
        from app.workers.tasks.document_intelligence_tasks import extract_entities_from_document

        assert extract_entities_from_document.soft_time_limit == 60
        assert extract_entities_from_document.time_limit == 90

    def test_batch_extract_has_long_time_limits(self):
        """Sollte batch_extract_entities lange Zeitlimits haben."""
        from app.workers.tasks.document_intelligence_tasks import batch_extract_entities

        assert batch_extract_entities.soft_time_limit == 1800  # 30 Minuten
        assert batch_extract_entities.time_limit == 1860

    def test_pipeline_has_very_long_time_limits(self):
        """Sollte run_document_intelligence_pipeline sehr lange Zeitlimits haben."""
        from app.workers.tasks.document_intelligence_tasks import run_document_intelligence_pipeline

        assert run_document_intelligence_pipeline.soft_time_limit == 3600  # 1 Stunde
        assert run_document_intelligence_pipeline.time_limit == 3660

    def test_update_metrics_has_short_time_limits(self):
        """Sollte update_intelligence_metrics kurze Zeitlimits haben."""
        from app.workers.tasks.document_intelligence_tasks import update_intelligence_metrics

        assert update_intelligence_metrics.soft_time_limit == 60
        assert update_intelligence_metrics.time_limit == 90


class TestTaskBaseClass:
    """Tests fuer Task Base Class Konfiguration."""

    def test_all_tasks_use_cpu_base(self):
        """Sollte alle Document Intelligence Tasks mit CPUTask Base konfigurieren."""
        from app.workers.tasks.document_intelligence_tasks import (
            detect_document_groups,
            batch_detect_groups_by_folder,
            extract_entities_from_document,
            batch_extract_entities,
            run_document_intelligence_pipeline,
            update_intelligence_metrics,
        )
        from app.workers.celery_app import CPUTask

        tasks = [
            detect_document_groups,
            batch_detect_groups_by_folder,
            extract_entities_from_document,
            batch_extract_entities,
            run_document_intelligence_pipeline,
            update_intelligence_metrics,
        ]

        for task in tasks:
            assert isinstance(task, CPUTask), f"Task {task.name} sollte CPUTask verwenden"


class TestTaskNaming:
    """Tests fuer Task Namenskonventionen."""

    def test_task_names_follow_convention(self):
        """Sollte Task-Namen nach Konvention benennen."""
        from app.workers.tasks.document_intelligence_tasks import (
            detect_document_groups,
            batch_detect_groups_by_folder,
            extract_entities_from_document,
            batch_extract_entities,
            run_document_intelligence_pipeline,
            update_intelligence_metrics,
        )

        tasks = [
            detect_document_groups,
            batch_detect_groups_by_folder,
            extract_entities_from_document,
            batch_extract_entities,
            run_document_intelligence_pipeline,
            update_intelligence_metrics,
        ]

        for task in tasks:
            assert task.name.startswith("app.workers.tasks.document_intelligence_tasks."), \
                f"Task {task.name} folgt nicht der Namenskonvention"


class TestRunAsyncTaskHelper:
    """Tests fuer run_async_task Hilfsfunktion."""

    def test_run_async_task_success(self):
        """Sollte async Coroutine erfolgreich ausfuehren."""
        from app.workers.tasks.document_intelligence_tasks import run_async_task

        async def sample_coro():
            return {"groups_found": 5, "entities": 10}

        result = run_async_task(sample_coro())
        assert result == {"groups_found": 5, "entities": 10}

    def test_run_async_task_with_exception(self):
        """Sollte Exceptions durchreichen."""
        from app.workers.tasks.document_intelligence_tasks import run_async_task

        async def failing_coro():
            raise ValueError("Entity extraction failed")

        with pytest.raises(ValueError, match="Entity extraction failed"):
            run_async_task(failing_coro())


class TestUpdateTaskProgressHelper:
    """Tests fuer update_task_progress Hilfsfunktion."""

    def test_update_progress_calculates_correctly(self):
        """Sollte Progress korrekt berechnen."""
        from app.workers.tasks.document_intelligence_tasks import update_task_progress

        with patch('app.workers.tasks.document_intelligence_tasks.celery_app') as mock_app:
            mock_backend = MagicMock()
            mock_app.backend = mock_backend

            update_task_progress("task-123", current=50, total=100, message="Processing...")

            mock_backend.store_result.assert_called_once()
            call_args = mock_backend.store_result.call_args
            assert call_args[0][0] == "task-123"
            result_data = call_args[0][1]
            assert result_data["progress"] == 50
            assert result_data["current"] == 50
            assert result_data["total"] == 100

    def test_update_progress_handles_zero_total(self):
        """Sollte Division durch Null vermeiden."""
        from app.workers.tasks.document_intelligence_tasks import update_task_progress

        with patch('app.workers.tasks.document_intelligence_tasks.celery_app') as mock_app:
            mock_backend = MagicMock()
            mock_app.backend = mock_backend

            update_task_progress("task-123", current=0, total=0, message="Empty batch")

            call_args = mock_backend.store_result.call_args
            result_data = call_args[0][1]
            assert result_data["progress"] == 0
