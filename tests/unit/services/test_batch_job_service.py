# -*- coding: utf-8 -*-
"""
Tests für BatchJobService.

Testet Batch-Job-Erstellung, Fortschrittsverfolgung und Lifecycle-Management.
"""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from app.services.batch_job_service import (
    BatchJobService,
    get_batch_job_service,
)
from app.db.models import ProcessingStatus


class TestBatchJobService:
    """Tests für BatchJobService."""

    @pytest.fixture
    def service(self):
        """Erstellt BatchJobService-Instanz."""
        return BatchJobService()

    @pytest.fixture
    def mock_db(self):
        """Mock AsyncSession."""
        db = AsyncMock()
        db.add = MagicMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock()
        return db

    @pytest.fixture
    def mock_batch_job(self):
        """Mock BatchJob."""
        job = MagicMock()
        job.id = uuid4()
        job.user_id = uuid4()
        job.job_type = "ocr"
        job.status = ProcessingStatus.QUEUED
        job.priority = 5
        job.total_documents = 10
        job.processed_documents = 0
        job.failed_documents = 0
        job.progress = 0
        job.document_ids = [str(uuid4()) for _ in range(10)]
        job.backend = "auto"
        job.language = "de"
        job.options = {}
        job.is_paused = False
        job.paused_at = None
        job.resume_from_index = None
        job.current_document = None
        job.message = None
        job.created_at = datetime.now(timezone.utc)
        job.started_at = None
        job.completed_at = None
        job.estimated_completion = None
        job.avg_time_per_document_ms = None
        job.total_processing_time_ms = None
        job.result_summary = None
        job.celery_task_id = None
        job.error_message = None
        return job

    @pytest.mark.asyncio
    async def test_create_batch_job(self, service, mock_db):
        """create_batch_job sollte BatchJob erstellen."""
        user_id = uuid4()
        document_ids = [uuid4() for _ in range(5)]

        # Mock _estimate_processing_time
        with patch.object(service, '_estimate_processing_time', return_value=15):
            # Mock db.refresh um das BatchJob-Objekt zurückzugeben
            async def mock_refresh(obj):
                obj.id = uuid4()
                obj.created_at = datetime.now(timezone.utc)
            mock_db.refresh = mock_refresh

            result = await service.create_batch_job(
                db=mock_db,
                user_id=user_id,
                document_ids=document_ids,
                job_type="ocr",
                backend="deepseek",
                language="de",
                priority=3
            )

            assert result is not None
            mock_db.add.assert_called_once()
            mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_start_batch_job(self, service, mock_db, mock_batch_job):
        """start_batch_job sollte Job starten und Status ändern."""
        with patch.object(service, '_get_batch_job', return_value=mock_batch_job):
            result = await service.start_batch_job(
                db=mock_db,
                batch_id=mock_batch_job.id,
                celery_task_id="task-123"
            )

            assert result.status == ProcessingStatus.PROCESSING
            assert result.started_at is not None
            assert result.celery_task_id == "task-123"
            mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_start_batch_job_not_found(self, service, mock_db):
        """start_batch_job sollte None zurückgeben wenn Job nicht existiert."""
        with patch.object(service, '_get_batch_job', return_value=None):
            result = await service.start_batch_job(
                db=mock_db,
                batch_id=uuid4()
            )

            assert result is None

    @pytest.mark.asyncio
    async def test_update_progress(self, service, mock_db, mock_batch_job):
        """update_progress sollte Fortschritt aktualisieren."""
        mock_batch_job.started_at = datetime.now(timezone.utc) - timedelta(seconds=30)

        with patch.object(service, '_get_batch_job', return_value=mock_batch_job):
            result = await service.update_progress(
                db=mock_db,
                batch_id=mock_batch_job.id,
                processed=5,
                failed=1,
                current_document="doc_123.pdf"
            )

            assert result.processed_documents == 5
            assert result.failed_documents == 1
            assert result.progress == 50  # 5/10 = 50%
            assert result.current_document == "doc_123.pdf"
            mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_progress_estimates_remaining_time(self, service, mock_db, mock_batch_job):
        """update_progress sollte Restzeit schätzen."""
        mock_batch_job.started_at = datetime.now(timezone.utc) - timedelta(seconds=10)

        with patch.object(service, '_get_batch_job', return_value=mock_batch_job):
            result = await service.update_progress(
                db=mock_db,
                batch_id=mock_batch_job.id,
                processed=5,
                failed=0
            )

            # 10s für 5 Dokumente = 2s pro Dokument
            # 5 verbleibend = 10s geschätzte Restzeit
            assert result.avg_time_per_document_ms is not None
            assert result.estimated_completion is not None

    @pytest.mark.asyncio
    async def test_complete_batch_job_success(self, service, mock_db, mock_batch_job):
        """complete_batch_job sollte Job als abgeschlossen markieren."""
        mock_batch_job.started_at = datetime.now(timezone.utc) - timedelta(seconds=60)
        mock_batch_job.processed_documents = 10
        mock_batch_job.failed_documents = 0

        with patch.object(service, '_get_batch_job', return_value=mock_batch_job):
            with patch('app.services.batch_job_service.get_webhook_dispatcher') as mock_webhook:
                mock_dispatcher = AsyncMock()
                mock_dispatcher.dispatch_event = AsyncMock(return_value=1)
                mock_webhook.return_value = mock_dispatcher

                result = await service.complete_batch_job(
                    db=mock_db,
                    batch_id=mock_batch_job.id
                )

                assert result.status == ProcessingStatus.COMPLETED
                assert result.progress == 100
                assert result.completed_at is not None
                mock_dispatcher.dispatch_event.assert_called_once()

    @pytest.mark.asyncio
    async def test_complete_batch_job_with_failures(self, service, mock_db, mock_batch_job):
        """complete_batch_job sollte Fehlgeschlagen markieren wenn alle fehlschlugen."""
        mock_batch_job.started_at = datetime.now(timezone.utc) - timedelta(seconds=60)
        mock_batch_job.processed_documents = 10
        mock_batch_job.failed_documents = 10  # Alle fehlgeschlagen

        with patch.object(service, '_get_batch_job', return_value=mock_batch_job):
            with patch('app.services.batch_job_service.get_webhook_dispatcher') as mock_webhook:
                mock_dispatcher = AsyncMock()
                mock_webhook.return_value = mock_dispatcher

                result = await service.complete_batch_job(
                    db=mock_db,
                    batch_id=mock_batch_job.id
                )

                assert result.status == ProcessingStatus.FAILED
                assert "fehlgeschlagen" in result.message.lower()

    @pytest.mark.asyncio
    async def test_complete_batch_job_with_error(self, service, mock_db, mock_batch_job):
        """complete_batch_job sollte Fehler speichern."""
        mock_batch_job.started_at = datetime.now(timezone.utc)

        with patch.object(service, '_get_batch_job', return_value=mock_batch_job):
            with patch('app.services.batch_job_service.get_webhook_dispatcher') as mock_webhook:
                mock_dispatcher = AsyncMock()
                mock_webhook.return_value = mock_dispatcher

                result = await service.complete_batch_job(
                    db=mock_db,
                    batch_id=mock_batch_job.id,
                    error_message="GPU Speicher voll"
                )

                assert result.status == ProcessingStatus.FAILED
                assert result.error_message == "GPU Speicher voll"

    @pytest.mark.asyncio
    async def test_pause_batch_job(self, service, mock_db, mock_batch_job):
        """pause_batch_job sollte laufenden Job pausieren."""
        mock_batch_job.status = ProcessingStatus.PROCESSING
        mock_batch_job.processed_documents = 3

        with patch.object(service, '_get_batch_job', return_value=mock_batch_job):
            result = await service.pause_batch_job(
                db=mock_db,
                batch_id=mock_batch_job.id,
                user_id=mock_batch_job.user_id
            )

            assert result.is_paused is True
            assert result.paused_at is not None
            assert result.resume_from_index == 3

    @pytest.mark.asyncio
    async def test_pause_batch_job_permission_error(self, service, mock_db, mock_batch_job):
        """pause_batch_job sollte Berechtigung prüfen."""
        mock_batch_job.status = ProcessingStatus.PROCESSING

        with patch.object(service, '_get_batch_job', return_value=mock_batch_job):
            with pytest.raises(PermissionError) as exc:
                await service.pause_batch_job(
                    db=mock_db,
                    batch_id=mock_batch_job.id,
                    user_id=uuid4()  # Falscher User
                )
            assert "Berechtigung" in str(exc.value)

    @pytest.mark.asyncio
    async def test_pause_batch_job_wrong_status(self, service, mock_db, mock_batch_job):
        """pause_batch_job sollte nur PROCESSING Jobs pausieren."""
        mock_batch_job.status = ProcessingStatus.COMPLETED

        with patch.object(service, '_get_batch_job', return_value=mock_batch_job):
            with pytest.raises(ValueError) as exc:
                await service.pause_batch_job(
                    db=mock_db,
                    batch_id=mock_batch_job.id,
                    user_id=mock_batch_job.user_id
                )
            assert "nicht pausiert werden" in str(exc.value)

    @pytest.mark.asyncio
    async def test_resume_batch_job(self, service, mock_db, mock_batch_job):
        """resume_batch_job sollte pausierten Job fortsetzen."""
        mock_batch_job.is_paused = True
        mock_batch_job.resume_from_index = 3

        with patch.object(service, '_get_batch_job', return_value=mock_batch_job):
            result = await service.resume_batch_job(
                db=mock_db,
                batch_id=mock_batch_job.id,
                user_id=mock_batch_job.user_id
            )

            assert result.is_paused is False
            assert result.paused_at is None
            assert "fortgesetzt" in result.message.lower()

    @pytest.mark.asyncio
    async def test_resume_batch_job_not_paused(self, service, mock_db, mock_batch_job):
        """resume_batch_job sollte Fehler werfen wenn nicht pausiert."""
        mock_batch_job.is_paused = False

        with patch.object(service, '_get_batch_job', return_value=mock_batch_job):
            with pytest.raises(ValueError) as exc:
                await service.resume_batch_job(
                    db=mock_db,
                    batch_id=mock_batch_job.id,
                    user_id=mock_batch_job.user_id
                )
            assert "nicht pausiert" in str(exc.value)

    @pytest.mark.asyncio
    async def test_cancel_batch_job(self, service, mock_db, mock_batch_job):
        """cancel_batch_job sollte Job abbrechen."""
        mock_batch_job.status = ProcessingStatus.PROCESSING
        mock_batch_job.processed_documents = 5

        with patch.object(service, '_get_batch_job', return_value=mock_batch_job):
            result = await service.cancel_batch_job(
                db=mock_db,
                batch_id=mock_batch_job.id,
                user_id=mock_batch_job.user_id
            )

            assert result.status == ProcessingStatus.CANCELLED
            assert result.completed_at is not None
            assert "abgebrochen" in result.message.lower()

    @pytest.mark.asyncio
    async def test_cancel_batch_job_already_completed(self, service, mock_db, mock_batch_job):
        """cancel_batch_job sollte Fehler werfen wenn bereits abgeschlossen."""
        mock_batch_job.status = ProcessingStatus.COMPLETED

        with patch.object(service, '_get_batch_job', return_value=mock_batch_job):
            with pytest.raises(ValueError) as exc:
                await service.cancel_batch_job(
                    db=mock_db,
                    batch_id=mock_batch_job.id,
                    user_id=mock_batch_job.user_id
                )
            assert "nicht abgebrochen werden" in str(exc.value)

    @pytest.mark.asyncio
    async def test_get_batch_job(self, service, mock_db, mock_batch_job):
        """get_batch_job sollte Job-Details zurückgeben."""
        with patch.object(service, '_get_batch_job', return_value=mock_batch_job):
            result = await service.get_batch_job(
                db=mock_db,
                batch_id=mock_batch_job.id,
                user_id=mock_batch_job.user_id
            )

            assert result is not None
            assert result["id"] == str(mock_batch_job.id)
            assert result["job_type"] == "ocr"

    @pytest.mark.asyncio
    async def test_get_batch_job_wrong_user(self, service, mock_db, mock_batch_job):
        """get_batch_job sollte None für falschen User zurückgeben."""
        with patch.object(service, '_get_batch_job', return_value=mock_batch_job):
            result = await service.get_batch_job(
                db=mock_db,
                batch_id=mock_batch_job.id,
                user_id=uuid4()  # Falscher User
            )

            assert result is None

    @pytest.mark.asyncio
    async def test_list_batch_jobs(self, service, mock_db, mock_batch_job):
        """list_batch_jobs sollte paginierte Liste zurückgeben."""
        # Mock execute für COUNT Query
        mock_count_result = MagicMock()
        mock_count_result.scalar.return_value = 1

        # Mock execute für SELECT Query
        mock_select_result = MagicMock()
        mock_select_result.scalars.return_value.all.return_value = [mock_batch_job]

        mock_db.execute = AsyncMock(side_effect=[mock_count_result, mock_select_result])

        result = await service.list_batch_jobs(
            db=mock_db,
            user_id=mock_batch_job.user_id,
            limit=10,
            offset=0
        )

        assert result["total"] == 1
        assert len(result["batch_jobs"]) == 1
        assert result["batch_jobs"][0]["id"] == str(mock_batch_job.id)

    @pytest.mark.asyncio
    async def test_list_batch_jobs_with_filters(self, service, mock_db, mock_batch_job):
        """list_batch_jobs sollte Filter unterstützen."""
        mock_count_result = MagicMock()
        mock_count_result.scalar.return_value = 0

        mock_select_result = MagicMock()
        mock_select_result.scalars.return_value.all.return_value = []

        mock_db.execute = AsyncMock(side_effect=[mock_count_result, mock_select_result])

        result = await service.list_batch_jobs(
            db=mock_db,
            user_id=mock_batch_job.user_id,
            status=ProcessingStatus.COMPLETED,
            job_type="embedding"
        )

        assert result["total"] == 0
        assert len(result["batch_jobs"]) == 0

    @pytest.mark.asyncio
    async def test_get_active_batch_jobs(self, service, mock_db, mock_batch_job):
        """get_active_batch_jobs sollte nur aktive Jobs zurückgeben."""
        mock_batch_job.status = ProcessingStatus.PROCESSING

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_batch_job]
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await service.get_active_batch_jobs(
            db=mock_db,
            user_id=mock_batch_job.user_id
        )

        assert len(result) == 1
        assert result[0]["status"] == ProcessingStatus.PROCESSING

    def test_batch_job_to_dict(self, service, mock_batch_job):
        """_batch_job_to_dict sollte korrekt konvertieren."""
        mock_batch_job.status = ProcessingStatus.PROCESSING
        mock_batch_job.estimated_completion = datetime.now(timezone.utc) + timedelta(seconds=120)

        result = service._batch_job_to_dict(mock_batch_job)

        assert result["id"] == str(mock_batch_job.id)
        assert result["job_type"] == "ocr"
        assert result["remaining_time_seconds"] is not None
        assert result["remaining_time_seconds"] > 0

    def test_batch_job_to_dict_completed(self, service, mock_batch_job):
        """_batch_job_to_dict sollte keine Restzeit für abgeschlossene Jobs zeigen."""
        mock_batch_job.status = ProcessingStatus.COMPLETED

        result = service._batch_job_to_dict(mock_batch_job)

        assert result["remaining_time_seconds"] is None

    @pytest.mark.asyncio
    async def test_estimate_processing_time_from_history(self, service, mock_db):
        """_estimate_processing_time sollte historische Daten nutzen."""
        # Mock: Durchschnitt von 2000ms pro Dokument aus Historie
        mock_result = MagicMock()
        mock_result.scalar.return_value = 2000.0  # 2s pro Dokument
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await service._estimate_processing_time(
            db=mock_db,
            user_id=uuid4(),
            document_count=10,
            job_type="ocr",
            backend="deepseek"
        )

        # 2000ms * 10 Dokumente = 20000ms = 20s
        assert result == 20

    @pytest.mark.asyncio
    async def test_estimate_processing_time_fallback(self, service, mock_db):
        """_estimate_processing_time sollte Fallback-Werte nutzen."""
        # Mock: Keine historischen Daten
        mock_result = MagicMock()
        mock_result.scalar.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await service._estimate_processing_time(
            db=mock_db,
            user_id=uuid4(),
            document_count=10,
            job_type="ocr",
            backend="auto"
        )

        # Fallback: 3000ms * 10 Dokumente = 30000ms = 30s
        assert result == 30


class TestBatchJobServiceSingleton:
    """Tests für Singleton-Funktion."""

    def test_get_batch_job_service_singleton(self):
        """get_batch_job_service sollte immer dieselbe Instanz zurückgeben."""
        s1 = get_batch_job_service()
        s2 = get_batch_job_service()
        assert s1 is s2
