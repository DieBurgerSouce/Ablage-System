# -*- coding: utf-8 -*-
"""
Tests fuer RAG Celery Tasks.

Testet:
- Task Registrierung
- Task Optionen und Einstellungen
- Helper Funktionen

HINWEIS: Die RAG-Tasks importieren Services dynamisch INSIDE der Funktionen.
Diese Tests fokussieren auf die statisch testbaren Aspekte (Konfiguration, Registrierung).
"""

import pytest
from datetime import datetime, timezone
from uuid import uuid4


class TestTaskRegistration:
    """Tests fuer Task Registrierung."""

    def test_chunk_document_is_registered(self):
        """Sollte chunk_document Task registriert haben."""
        from app.workers.tasks.rag_tasks import chunk_document

        assert chunk_document is not None
        assert hasattr(chunk_document, 'name')
        assert chunk_document.name == "app.workers.tasks.rag_tasks.chunk_document"

    def test_batch_chunk_documents_is_registered(self):
        """Sollte batch_chunk_documents Task registriert haben."""
        from app.workers.tasks.rag_tasks import batch_chunk_documents

        assert batch_chunk_documents is not None
        assert hasattr(batch_chunk_documents, 'name')
        assert batch_chunk_documents.name == "app.workers.tasks.rag_tasks.batch_chunk_documents"

    def test_regenerate_chunk_embeddings_is_registered(self):
        """Sollte regenerate_chunk_embeddings Task registriert haben."""
        from app.workers.tasks.rag_tasks import regenerate_chunk_embeddings

        assert regenerate_chunk_embeddings is not None
        assert hasattr(regenerate_chunk_embeddings, 'name')
        assert regenerate_chunk_embeddings.name == "app.workers.tasks.rag_tasks.regenerate_chunk_embeddings"

    def test_run_rag_batch_job_is_registered(self):
        """Sollte run_rag_batch_job Task registriert haben."""
        from app.workers.tasks.rag_tasks import run_rag_batch_job

        assert run_rag_batch_job is not None
        assert hasattr(run_rag_batch_job, 'name')
        assert run_rag_batch_job.name == "app.workers.tasks.rag_tasks.run_rag_batch_job"

    def test_get_rag_statistics_is_registered(self):
        """Sollte get_rag_statistics Task registriert haben."""
        from app.workers.tasks.rag_tasks import get_rag_statistics

        assert get_rag_statistics is not None
        assert hasattr(get_rag_statistics, 'name')
        assert get_rag_statistics.name == "app.workers.tasks.rag_tasks.get_rag_statistics"

    def test_scheduled_chunk_new_documents_is_registered(self):
        """Sollte scheduled_chunk_new_documents Task registriert haben."""
        from app.workers.tasks.rag_tasks import scheduled_chunk_new_documents

        assert scheduled_chunk_new_documents is not None
        assert hasattr(scheduled_chunk_new_documents, 'name')
        assert scheduled_chunk_new_documents.name == "app.workers.tasks.rag_tasks.scheduled_chunk_new_documents"

    def test_sync_customer_cards_scheduled_is_registered(self):
        """Sollte sync_customer_cards_scheduled Task registriert haben."""
        from app.workers.tasks.rag_tasks import sync_customer_cards_scheduled

        assert sync_customer_cards_scheduled is not None
        assert hasattr(sync_customer_cards_scheduled, 'name')
        assert sync_customer_cards_scheduled.name == "app.workers.tasks.rag_tasks.sync_customer_cards_scheduled"


class TestTaskOptions:
    """Tests fuer Task Optionen."""

    def test_chunk_document_is_gpu_task(self):
        """Sollte chunk_document als GPU Task konfiguriert sein."""
        from app.workers.tasks.rag_tasks import chunk_document
        from app.workers.celery_app import GPUTask

        # Check if task uses GPUTask base class
        assert isinstance(chunk_document, GPUTask), \
            "chunk_document sollte GPUTask als Base verwenden"

    def test_batch_chunk_is_gpu_task(self):
        """Sollte batch_chunk_documents als GPU Task konfiguriert sein."""
        from app.workers.tasks.rag_tasks import batch_chunk_documents
        from app.workers.celery_app import GPUTask

        # Check if task uses GPUTask base class
        assert isinstance(batch_chunk_documents, GPUTask), \
            "batch_chunk_documents sollte GPUTask als Base verwenden"

    def test_all_tasks_use_correct_base(self):
        """Sollte alle RAG Tasks mit GPUTask oder CPUTask Base konfigurieren."""
        from app.workers.tasks.rag_tasks import (
            chunk_document,
            batch_chunk_documents,
            regenerate_chunk_embeddings,
            run_rag_batch_job,
            get_rag_statistics,
            scheduled_chunk_new_documents,
            sync_customer_cards_scheduled,
        )
        from app.workers.celery_app import GPUTask, CPUTask

        # GPU-intensive tasks (embedding generation)
        gpu_tasks = [
            chunk_document,
            batch_chunk_documents,
            regenerate_chunk_embeddings,
        ]
        for task in gpu_tasks:
            assert isinstance(task, GPUTask), f"Task {task.name} sollte GPUTask verwenden"

        # CPU-only tasks
        cpu_tasks = [
            run_rag_batch_job,
            get_rag_statistics,
            scheduled_chunk_new_documents,
            sync_customer_cards_scheduled,
        ]
        for task in cpu_tasks:
            assert isinstance(task, CPUTask), f"Task {task.name} sollte CPUTask verwenden"


class TestTaskNaming:
    """Tests fuer Task Namenskonventionen."""

    def test_task_names_follow_convention(self):
        """Sollte Task-Namen nach Konvention benennen."""
        from app.workers.tasks.rag_tasks import (
            chunk_document,
            batch_chunk_documents,
            regenerate_chunk_embeddings,
            run_rag_batch_job,
            get_rag_statistics,
            scheduled_chunk_new_documents,
            sync_customer_cards_scheduled,
        )

        tasks = [
            chunk_document,
            batch_chunk_documents,
            regenerate_chunk_embeddings,
            run_rag_batch_job,
            get_rag_statistics,
            scheduled_chunk_new_documents,
            sync_customer_cards_scheduled,
        ]

        for task in tasks:
            assert task.name.startswith("app.workers.tasks.rag_tasks."), \
                f"Task {task.name} folgt nicht der Namenskonvention"


class TestTaskProgressUpdate:
    """Tests fuer update_task_progress Hilfsfunktion."""

    def test_update_progress_calculates_correctly(self):
        """Sollte Progress korrekt berechnen."""
        from app.workers.tasks.rag_tasks import update_task_progress
        from unittest.mock import patch, MagicMock

        with patch('app.workers.tasks.rag_tasks.celery_app') as mock_app:
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
        from app.workers.tasks.rag_tasks import update_task_progress
        from unittest.mock import patch, MagicMock

        with patch('app.workers.tasks.rag_tasks.celery_app') as mock_app:
            mock_backend = MagicMock()
            mock_app.backend = mock_backend

            update_task_progress("task-123", current=0, total=0, message="Empty batch")

            call_args = mock_backend.store_result.call_args
            result_data = call_args[0][1]
            assert result_data["progress"] == 0


class TestRunAsyncTaskHelper:
    """Tests fuer run_async_task Hilfsfunktion."""

    def test_run_async_task_success(self):
        """Sollte async Coroutine erfolgreich ausfuehren."""
        from app.workers.tasks.rag_tasks import run_async_task

        async def sample_coro():
            return {"chunks": 10, "tokens": 1000}

        result = run_async_task(sample_coro())
        assert result == {"chunks": 10, "tokens": 1000}

    def test_run_async_task_with_exception(self):
        """Sollte Exceptions durchreichen."""
        from app.workers.tasks.rag_tasks import run_async_task

        async def failing_coro():
            raise ValueError("Chunking failed")

        with pytest.raises(ValueError, match="Chunking failed"):
            run_async_task(failing_coro())

    def test_run_async_task_with_complex_result(self):
        """Sollte komplexe Ergebnisse korrekt zurueckgeben."""
        from app.workers.tasks.rag_tasks import run_async_task

        async def complex_coro():
            return {
                "success": True,
                "chunks_created": 25,
                "total_tokens": 5000,
                "strategy": "semantic",
                "documents": [str(uuid4()), str(uuid4())],
            }

        result = run_async_task(complex_coro())
        assert result["success"] is True
        assert result["chunks_created"] == 25
        assert result["strategy"] == "semantic"
        assert len(result["documents"]) == 2
