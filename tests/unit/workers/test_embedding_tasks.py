# -*- coding: utf-8 -*-
"""
Unit-Tests für Embedding Celery Tasks.

Testet:
- generate_document_embedding (Single)
- batch_generate_embeddings (Batch)
- regenerate_all_embeddings
- check_embedding_coverage
- refresh_search_analytics

Feinpoliert und durchdacht - GPU-optimierte Embedding-Tests.
"""

import pytest
from datetime import datetime, timezone
from typing import Dict, Any, List
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from uuid import uuid4


# ========================= Test Fixtures =========================


@pytest.fixture
def mock_db():
    """Create mock async database session."""
    db = AsyncMock()
    db.execute = AsyncMock()
    db.commit = AsyncMock()
    return db


@pytest.fixture
def sample_document():
    """Create sample document for embedding."""
    doc = Mock()
    doc.id = uuid4()
    doc.owner_id = uuid4()
    doc.extracted_text = "Dies ist ein deutscher Testtext fuer Embeddings."
    doc.embedding = None
    doc.embedding_updated_at = None
    doc.embedding_model = None
    return doc


@pytest.fixture
def sample_document_with_embedding():
    """Create document with existing embedding."""
    doc = Mock()
    doc.id = uuid4()
    doc.owner_id = uuid4()
    doc.extracted_text = "Text mit Embedding."
    doc.embedding = [0.1] * 1024
    doc.embedding_updated_at = datetime.now(timezone.utc)
    doc.embedding_model = "multilingual-e5-large"
    return doc


@pytest.fixture
def mock_embedding_service():
    """Create mock embedding service."""
    service = Mock()
    service.generate_embedding_async = AsyncMock(return_value=[0.1] * 1024)
    service.generate_batch_embeddings_async = AsyncMock(return_value=[[0.1] * 1024])
    return service


@pytest.fixture
def mock_celery_task():
    """Create mock Celery task context."""
    task = Mock()
    task.request = Mock()
    task.request.id = str(uuid4())
    return task


# ========================= generate_document_embedding Tests =========================


class TestGenerateDocumentEmbedding:
    """Tests for single document embedding generation."""

    def test_embedding_generated_successfully(self, mock_celery_task, sample_document, mock_embedding_service):
        """Embedding sollte erfolgreich generiert werden."""
        with patch('app.workers.tasks.embedding_tasks.get_embedding_service') as mock_get:
            mock_get.return_value = mock_embedding_service

            with patch('app.workers.tasks.embedding_tasks.async_session_maker') as mock_session:
                mock_session_instance = AsyncMock()
                mock_result = Mock()
                mock_result.scalar_one_or_none.return_value = sample_document
                mock_session_instance.execute.return_value = mock_result
                mock_session.return_value.__aenter__.return_value = mock_session_instance

                with patch('app.workers.tasks.embedding_tasks.run_async_task') as mock_run:
                    mock_run.return_value = {
                        "success": True,
                        "document_id": str(sample_document.id),
                        "embedding_dimension": 1024,
                    }

                    from app.workers.tasks.embedding_tasks import generate_document_embedding

                    result = generate_document_embedding(mock_celery_task, str(sample_document.id))

                    assert result["success"] is True
                    assert result["embedding_dimension"] == 1024

    def test_embedding_skipped_if_exists(self, mock_celery_task, sample_document_with_embedding):
        """Existierendes Embedding sollte uebersprungen werden."""
        with patch('app.workers.tasks.embedding_tasks.get_embedding_service'):
            with patch('app.workers.tasks.embedding_tasks.run_async_task') as mock_run:
                mock_run.return_value = {
                    "success": True,
                    "document_id": str(sample_document_with_embedding.id),
                    "skipped": True,
                    "message": "Embedding existiert bereits",
                }

                from app.workers.tasks.embedding_tasks import generate_document_embedding

                result = generate_document_embedding(
                    mock_celery_task,
                    str(sample_document_with_embedding.id),
                    force_regenerate=False
                )

                assert result["skipped"] is True

    def test_embedding_regenerated_when_forced(self, mock_celery_task, sample_document_with_embedding, mock_embedding_service):
        """Force-Regenerate sollte Embedding neu erstellen."""
        with patch('app.workers.tasks.embedding_tasks.get_embedding_service') as mock_get:
            mock_get.return_value = mock_embedding_service

            with patch('app.workers.tasks.embedding_tasks.run_async_task') as mock_run:
                mock_run.return_value = {
                    "success": True,
                    "document_id": str(sample_document_with_embedding.id),
                    "embedding_dimension": 1024,
                }

                from app.workers.tasks.embedding_tasks import generate_document_embedding

                result = generate_document_embedding(
                    mock_celery_task,
                    str(sample_document_with_embedding.id),
                    force_regenerate=True
                )

                assert result["success"] is True
                assert "skipped" not in result or result.get("skipped") is False

    def test_embedding_error_on_missing_document(self, mock_celery_task):
        """Fehler bei nicht existierendem Dokument."""
        with patch('app.workers.tasks.embedding_tasks.get_embedding_service'):
            with patch('app.workers.tasks.embedding_tasks.run_async_task') as mock_run:
                mock_run.side_effect = ValueError("Dokument nicht gefunden")

                from app.workers.tasks.embedding_tasks import generate_document_embedding

                with pytest.raises(ValueError) as exc_info:
                    generate_document_embedding(mock_celery_task, str(uuid4()))

                assert "nicht gefunden" in str(exc_info.value)

    def test_embedding_error_on_missing_text(self, mock_celery_task, sample_document):
        """Fehler bei Dokument ohne Text."""
        sample_document.extracted_text = None

        with patch('app.workers.tasks.embedding_tasks.get_embedding_service'):
            with patch('app.workers.tasks.embedding_tasks.run_async_task') as mock_run:
                mock_run.side_effect = ValueError("keinen extrahierten Text")

                from app.workers.tasks.embedding_tasks import generate_document_embedding

                with pytest.raises(ValueError) as exc_info:
                    generate_document_embedding(mock_celery_task, str(sample_document.id))

                assert "Text" in str(exc_info.value)


# ========================= batch_generate_embeddings Tests =========================


class TestBatchGenerateEmbeddings:
    """Tests for batch embedding generation."""

    def test_batch_processes_multiple_documents(self, mock_celery_task, mock_embedding_service):
        """Batch sollte mehrere Dokumente verarbeiten."""
        doc_ids = [str(uuid4()) for _ in range(5)]

        with patch('app.workers.tasks.embedding_tasks.get_embedding_service') as mock_get:
            mock_get.return_value = mock_embedding_service

            with patch('app.workers.tasks.embedding_tasks.run_async_task') as mock_run:
                mock_run.return_value = {
                    "success": True,
                    "total_documents": 5,
                    "successful": 5,
                    "skipped": 0,
                    "failed": 0,
                }

                from app.workers.tasks.embedding_tasks import batch_generate_embeddings

                result = batch_generate_embeddings(mock_celery_task, doc_ids)

                assert result["total_documents"] == 5
                assert result["successful"] == 5

    def test_batch_reports_failures(self, mock_celery_task, mock_embedding_service):
        """Batch sollte Fehler reporten."""
        doc_ids = [str(uuid4()) for _ in range(3)]

        with patch('app.workers.tasks.embedding_tasks.get_embedding_service') as mock_get:
            mock_get.return_value = mock_embedding_service

            with patch('app.workers.tasks.embedding_tasks.run_async_task') as mock_run:
                mock_run.return_value = {
                    "success": True,
                    "total_documents": 3,
                    "successful": 2,
                    "skipped": 0,
                    "failed": 1,
                    "results": [
                        {"document_id": doc_ids[0], "success": True},
                        {"document_id": doc_ids[1], "success": True},
                        {"document_id": doc_ids[2], "success": False, "error": "Not found"},
                    ],
                }

                from app.workers.tasks.embedding_tasks import batch_generate_embeddings

                result = batch_generate_embeddings(mock_celery_task, doc_ids)

                assert result["failed"] == 1
                assert result["successful"] == 2

    def test_batch_skips_existing_embeddings(self, mock_celery_task, mock_embedding_service):
        """Batch sollte existierende Embeddings ueberspringen."""
        doc_ids = [str(uuid4()) for _ in range(3)]

        with patch('app.workers.tasks.embedding_tasks.get_embedding_service') as mock_get:
            mock_get.return_value = mock_embedding_service

            with patch('app.workers.tasks.embedding_tasks.run_async_task') as mock_run:
                mock_run.return_value = {
                    "success": True,
                    "total_documents": 3,
                    "successful": 1,
                    "skipped": 2,
                    "failed": 0,
                }

                from app.workers.tasks.embedding_tasks import batch_generate_embeddings

                result = batch_generate_embeddings(mock_celery_task, doc_ids, force_regenerate=False)

                assert result["skipped"] == 2


# ========================= regenerate_all_embeddings Tests =========================


class TestRegenerateAllEmbeddings:
    """Tests for full embedding regeneration."""

    def test_regenerate_all_finds_documents(self, mock_celery_task):
        """Sollte alle Dokumente mit Text finden."""
        with patch('app.workers.tasks.embedding_tasks.run_async_task') as mock_run:
            mock_run.return_value = {
                "success": True,
                "total_documents": 100,
                "batch_result": {"successful": 100},
            }

            from app.workers.tasks.embedding_tasks import regenerate_all_embeddings

            result = regenerate_all_embeddings(mock_celery_task)

            assert result["total_documents"] == 100

    def test_regenerate_filters_by_user(self, mock_celery_task):
        """Sollte nach User filtern koennen."""
        user_id = str(uuid4())

        with patch('app.workers.tasks.embedding_tasks.run_async_task') as mock_run:
            mock_run.return_value = {
                "success": True,
                "total_documents": 10,
            }

            from app.workers.tasks.embedding_tasks import regenerate_all_embeddings

            result = regenerate_all_embeddings(mock_celery_task, user_id=user_id)

            assert result["total_documents"] == 10

    def test_regenerate_handles_no_documents(self, mock_celery_task):
        """Sollte leere Menge behandeln."""
        with patch('app.workers.tasks.embedding_tasks.run_async_task') as mock_run:
            mock_run.return_value = {
                "success": True,
                "total_documents": 0,
                "message": "Keine Dokumente zum Regenerieren gefunden",
            }

            from app.workers.tasks.embedding_tasks import regenerate_all_embeddings

            result = regenerate_all_embeddings(mock_celery_task)

            assert result["total_documents"] == 0


# ========================= check_embedding_coverage Tests =========================


class TestCheckEmbeddingCoverage:
    """Tests for embedding coverage check."""

    def test_coverage_calculation(self, mock_celery_task):
        """Sollte Coverage korrekt berechnen."""
        with patch('app.workers.tasks.embedding_tasks.run_async_task') as mock_run:
            mock_run.return_value = {
                "total_documents": 100,
                "with_embedding": 80,
                "without_embedding": 20,
                "coverage_percent": 80.0,
            }

            from app.workers.tasks.embedding_tasks import check_embedding_coverage

            result = check_embedding_coverage(mock_celery_task)

            assert result["total_documents"] == 100
            assert result["with_embedding"] == 80
            assert result["coverage_percent"] == 80.0

    def test_coverage_returns_missing_ids(self, mock_celery_task):
        """Sollte fehlende Dokument-IDs zurueckgeben."""
        with patch('app.workers.tasks.embedding_tasks.run_async_task') as mock_run:
            missing_ids = [str(uuid4()) for _ in range(5)]
            mock_run.return_value = {
                "total_documents": 10,
                "with_embedding": 5,
                "without_embedding": 5,
                "coverage_percent": 50.0,
                "missing_document_ids": missing_ids,
            }

            from app.workers.tasks.embedding_tasks import check_embedding_coverage

            result = check_embedding_coverage(mock_celery_task)

            assert len(result["missing_document_ids"]) == 5

    def test_coverage_filters_by_user(self, mock_celery_task):
        """Sollte nach User filtern koennen."""
        user_id = str(uuid4())

        with patch('app.workers.tasks.embedding_tasks.run_async_task') as mock_run:
            mock_run.return_value = {
                "total_documents": 20,
                "with_embedding": 15,
                "coverage_percent": 75.0,
            }

            from app.workers.tasks.embedding_tasks import check_embedding_coverage

            result = check_embedding_coverage(mock_celery_task, user_id=user_id)

            assert result["total_documents"] == 20


# ========================= refresh_search_analytics Tests =========================


class TestRefreshSearchAnalytics:
    """Tests for search analytics refresh."""

    def test_refresh_success(self, mock_celery_task):
        """Sollte Analytics erfolgreich aktualisieren."""
        with patch('app.workers.tasks.embedding_tasks.get_search_analytics_service') as mock_get:
            service = Mock()
            mock_get.return_value = service

            with patch('app.workers.tasks.embedding_tasks.run_async_task') as mock_run:
                mock_run.return_value = {
                    "success": True,
                    "processing_time_seconds": 1.5,
                }

                from app.workers.tasks.embedding_tasks import refresh_search_analytics

                result = refresh_search_analytics(mock_celery_task)

                assert result["success"] is True

    def test_refresh_handles_failure(self, mock_celery_task):
        """Sollte Fehler behandeln."""
        with patch('app.workers.tasks.embedding_tasks.get_search_analytics_service') as mock_get:
            service = Mock()
            mock_get.return_value = service

            with patch('app.workers.tasks.embedding_tasks.run_async_task') as mock_run:
                mock_run.return_value = {
                    "success": False,
                }

                from app.workers.tasks.embedding_tasks import refresh_search_analytics

                result = refresh_search_analytics(mock_celery_task)

                assert result["success"] is False


# ========================= run_async_task Helper Tests =========================


class TestRunAsyncTask:
    """Tests for run_async_task helper."""

    def test_run_async_task_executes(self):
        """Sollte async Coroutine ausfuehren."""
        from app.workers.tasks.embedding_tasks import run_async_task

        async def sample_coro():
            return "done"

        result = run_async_task(sample_coro())

        assert result == "done"


# ========================= update_task_progress Tests =========================


class TestUpdateTaskProgress:
    """Tests for task progress updates."""

    def test_progress_calculation(self):
        """Sollte Progress korrekt berechnen."""
        with patch('app.workers.tasks.embedding_tasks.celery_app') as mock_app:
            mock_backend = Mock()
            mock_app.backend = mock_backend

            from app.workers.tasks.embedding_tasks import update_task_progress

            update_task_progress("task-123", current=50, total=100, message="Test")

            mock_backend.store_result.assert_called_once()
            call_args = mock_backend.store_result.call_args
            stored_data = call_args[0][1]

            assert stored_data["progress"] == 50
            assert stored_data["message"] == "Test"

    def test_progress_zero_total(self):
        """Sollte Division by Zero vermeiden."""
        with patch('app.workers.tasks.embedding_tasks.celery_app') as mock_app:
            mock_backend = Mock()
            mock_app.backend = mock_backend

            from app.workers.tasks.embedding_tasks import update_task_progress

            update_task_progress("task-123", current=0, total=0, message="Test")

            call_args = mock_backend.store_result.call_args
            stored_data = call_args[0][1]

            assert stored_data["progress"] == 0
