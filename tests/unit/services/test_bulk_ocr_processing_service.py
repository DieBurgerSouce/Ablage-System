# -*- coding: utf-8 -*-
"""
Unit Tests fuer BulkOCRProcessingService.

Testet die Bulk OCR-Verarbeitung:
- Job-Management (Create, Start, Pause, Cancel)
- Fortschrittsverfolgung
- Checkpoint-Mechanismus
- GPU-Queue-Management
"""

import pytest
import asyncio
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from app.services.bulk_ocr_processing_service import (
    BulkOCRProcessingService,
    BulkProcessingJob,
    BulkJobStatus,
    BulkProcessingProgress,
    BackendBatchConfig,
    BACKEND_BATCH_CONFIGS,
    CHECKPOINT_INTERVAL,
    _active_jobs,
    _job_cancel_flags,
    _job_storage_lock,
)


class TestBulkOCRProcessingService:
    """Tests fuer BulkOCRProcessingService."""

    @pytest.fixture
    def service(self) -> BulkOCRProcessingService:
        """Erstellt eine frische Service-Instanz."""
        return BulkOCRProcessingService()

    @pytest.fixture
    def mock_db(self) -> AsyncMock:
        """Erstellt eine Mock-Datenbank-Session."""
        db = AsyncMock()
        # Mock execute() to return a result with scalar()
        mock_result = MagicMock()
        mock_result.scalar.return_value = 100  # 100 Dokumente
        mock_result.scalars.return_value.all.return_value = []
        db.execute.return_value = mock_result
        return db

    @pytest.fixture(autouse=True)
    async def cleanup_jobs(self):
        """Bereinigt Jobs vor und nach jedem Test."""
        # Cleanup vor dem Test
        async with _job_storage_lock:
            _active_jobs.clear()
            _job_cancel_flags.clear()
        yield
        # Cleanup nach dem Test
        async with _job_storage_lock:
            _active_jobs.clear()
            _job_cancel_flags.clear()

    # =========================================================================
    # JOB CREATION TESTS
    # =========================================================================

    @pytest.mark.asyncio
    async def test_create_job_basic(
        self,
        service: BulkOCRProcessingService,
        mock_db: AsyncMock,
    ) -> None:
        """Erstellt einen einfachen Bulk-Processing-Job."""
        job = await service.create_job(
            db=mock_db,
            name="Test Bulk Job",
        )

        assert job is not None
        assert job.name == "Test Bulk Job"
        assert job.status == BulkJobStatus.PENDING
        assert job.total_documents == 100
        assert job.processed_documents == 0
        assert job.failed_documents == 0
        assert len(job.backends) > 0

    @pytest.mark.asyncio
    async def test_create_job_with_custom_backends(
        self,
        service: BulkOCRProcessingService,
        mock_db: AsyncMock,
    ) -> None:
        """Erstellt einen Job mit spezifischen Backends."""
        backends = ["deepseek-janus-pro", "got-ocr-2.0"]

        job = await service.create_job(
            db=mock_db,
            name="Custom Backend Job",
            backends=backends,
        )

        assert job.backends == backends
        assert len(job.documents_per_backend) == 2
        assert "deepseek-janus-pro" in job.documents_per_backend
        assert "got-ocr-2.0" in job.documents_per_backend

    @pytest.mark.asyncio
    async def test_create_job_with_sample_limit(
        self,
        service: BulkOCRProcessingService,
        mock_db: AsyncMock,
    ) -> None:
        """Erstellt einen Job mit Sample-Limit."""
        mock_result = MagicMock()
        mock_result.scalar.return_value = 500  # Mehr als Limit
        mock_db.execute.return_value = mock_result

        job = await service.create_job(
            db=mock_db,
            name="Limited Job",
            sample_limit=50,
        )

        assert job.total_documents == 50
        assert job.configuration.get("sample_limit") == 50

    # =========================================================================
    # JOB LIFECYCLE TESTS
    # =========================================================================

    @pytest.mark.asyncio
    async def test_start_job(
        self,
        service: BulkOCRProcessingService,
        mock_db: AsyncMock,
    ) -> None:
        """Startet einen erstellten Job."""
        job = await service.create_job(db=mock_db, name="Start Test")

        started_job = await service.start_job(db=mock_db, job_id=job.id)

        assert started_job.status == BulkJobStatus.RUNNING
        assert started_job.started_at is not None

    @pytest.mark.asyncio
    async def test_start_job_not_found(
        self,
        service: BulkOCRProcessingService,
        mock_db: AsyncMock,
    ) -> None:
        """Fehler bei Starten eines nicht existierenden Jobs."""
        with pytest.raises(ValueError, match="nicht gefunden"):
            await service.start_job(db=mock_db, job_id="non-existent-id")

    @pytest.mark.asyncio
    async def test_start_job_already_running(
        self,
        service: BulkOCRProcessingService,
        mock_db: AsyncMock,
    ) -> None:
        """Fehler bei Starten eines bereits laufenden Jobs."""
        job = await service.create_job(db=mock_db, name="Already Running Test")
        await service.start_job(db=mock_db, job_id=job.id)

        with pytest.raises(ValueError, match="(laeuft bereits|läuft bereits)"):
            await service.start_job(db=mock_db, job_id=job.id)

    @pytest.mark.asyncio
    async def test_pause_job(
        self,
        service: BulkOCRProcessingService,
        mock_db: AsyncMock,
    ) -> None:
        """Pausiert einen laufenden Job."""
        job = await service.create_job(db=mock_db, name="Pause Test")
        await service.start_job(db=mock_db, job_id=job.id)

        paused_job = await service.pause_job(job_id=job.id)

        assert paused_job.status == BulkJobStatus.PAUSED
        assert paused_job.paused_at is not None

    @pytest.mark.asyncio
    async def test_pause_job_not_running(
        self,
        service: BulkOCRProcessingService,
        mock_db: AsyncMock,
    ) -> None:
        """Fehler beim Pausieren eines nicht laufenden Jobs."""
        job = await service.create_job(db=mock_db, name="Not Running Test")

        with pytest.raises(ValueError, match="(laeuft nicht|läuft nicht)"):
            await service.pause_job(job_id=job.id)

    @pytest.mark.asyncio
    async def test_cancel_job(
        self,
        service: BulkOCRProcessingService,
        mock_db: AsyncMock,
    ) -> None:
        """Bricht einen Job ab."""
        job = await service.create_job(db=mock_db, name="Cancel Test")

        cancelled_job = await service.cancel_job(job_id=job.id)

        assert cancelled_job.status == BulkJobStatus.CANCELLED
        assert cancelled_job.completed_at is not None

    @pytest.mark.asyncio
    async def test_cancel_job_not_found(
        self,
        service: BulkOCRProcessingService,
        mock_db: AsyncMock,
    ) -> None:
        """Fehler beim Abbrechen eines nicht existierenden Jobs."""
        with pytest.raises(ValueError, match="nicht gefunden"):
            await service.cancel_job(job_id="non-existent-id")

    # =========================================================================
    # JOB RETRIEVAL TESTS
    # =========================================================================

    @pytest.mark.asyncio
    async def test_get_job(
        self,
        service: BulkOCRProcessingService,
        mock_db: AsyncMock,
    ) -> None:
        """Ruft einen Job ab."""
        job = await service.create_job(db=mock_db, name="Get Test")

        retrieved_job = await service.get_job(job_id=job.id)

        assert retrieved_job is not None
        assert retrieved_job.id == job.id
        assert retrieved_job.name == "Get Test"

    @pytest.mark.asyncio
    async def test_get_job_not_found(
        self,
        service: BulkOCRProcessingService,
    ) -> None:
        """Gibt None zurueck fuer nicht existierenden Job."""
        retrieved_job = await service.get_job(job_id="non-existent-id")

        assert retrieved_job is None

    @pytest.mark.asyncio
    async def test_list_jobs(
        self,
        service: BulkOCRProcessingService,
        mock_db: AsyncMock,
    ) -> None:
        """Listet alle Jobs auf."""
        await service.create_job(db=mock_db, name="Job 1")
        await service.create_job(db=mock_db, name="Job 2")
        await service.create_job(db=mock_db, name="Job 3")

        jobs = await service.list_jobs()

        assert len(jobs) == 3
        names = [job.name for job in jobs]
        assert "Job 1" in names
        assert "Job 2" in names
        assert "Job 3" in names

    # =========================================================================
    # PROGRESS TRACKING TESTS
    # =========================================================================

    @pytest.mark.asyncio
    async def test_get_job_progress_pending(
        self,
        service: BulkOCRProcessingService,
        mock_db: AsyncMock,
    ) -> None:
        """Fortschritt fuer pending Job."""
        job = await service.create_job(db=mock_db, name="Progress Test")

        progress = await service.get_job_progress(job_id=job.id)

        assert progress is not None
        assert progress.status == BulkJobStatus.PENDING
        assert progress.processed_documents == 0
        assert progress.documents_per_second == 0.0

    @pytest.mark.asyncio
    async def test_get_job_progress_running(
        self,
        service: BulkOCRProcessingService,
        mock_db: AsyncMock,
    ) -> None:
        """Fortschritt fuer laufenden Job."""
        job = await service.create_job(db=mock_db, name="Progress Running Test")
        await service.start_job(db=mock_db, job_id=job.id)

        # Simuliere verarbeitete Dokumente
        async with _job_storage_lock:
            _active_jobs[job.id].processed_documents = 50

        progress = await service.get_job_progress(job_id=job.id)

        assert progress.status == BulkJobStatus.RUNNING
        assert progress.processed_documents == 50
        assert progress.started_at is not None

    @pytest.mark.asyncio
    async def test_get_job_progress_not_found(
        self,
        service: BulkOCRProcessingService,
    ) -> None:
        """Gibt None zurueck fuer nicht existierenden Job."""
        progress = await service.get_job_progress(job_id="non-existent-id")

        assert progress is None

    # =========================================================================
    # CONFIGURATION TESTS
    # =========================================================================

    def test_backend_batch_configs_exist(self) -> None:
        """Alle erwarteten Backend-Konfigurationen sind vorhanden."""
        expected_backends = ["deepseek-janus-pro", "got-ocr-2.0", "surya-gpu", "surya"]

        for backend in expected_backends:
            assert backend in BACKEND_BATCH_CONFIGS
            config = BACKEND_BATCH_CONFIGS[backend]
            assert isinstance(config, BackendBatchConfig)
            assert config.batch_size > 0
            assert config.estimated_time_per_doc_ms > 0

    def test_checkpoint_interval_configured(self) -> None:
        """Checkpoint-Intervall ist konfiguriert."""
        assert CHECKPOINT_INTERVAL > 0
        assert CHECKPOINT_INTERVAL == 100  # Laut Dokumentation

    # =========================================================================
    # JOB TO_DICT TESTS
    # =========================================================================

    @pytest.mark.asyncio
    async def test_job_to_dict(
        self,
        service: BulkOCRProcessingService,
        mock_db: AsyncMock,
    ) -> None:
        """Job kann zu Dictionary konvertiert werden."""
        job = await service.create_job(db=mock_db, name="Dict Test")
        await service.start_job(db=mock_db, job_id=job.id)

        job_dict = job.to_dict()

        assert isinstance(job_dict, dict)
        assert job_dict["id"] == job.id
        assert job_dict["name"] == "Dict Test"
        assert job_dict["status"] == "running"
        assert "backends" in job_dict
        assert "documents_per_backend" in job_dict

    # =========================================================================
    # THREAD-SAFETY TESTS
    # =========================================================================

    @pytest.mark.asyncio
    async def test_concurrent_job_creation(
        self,
        service: BulkOCRProcessingService,
        mock_db: AsyncMock,
    ) -> None:
        """Mehrere Jobs koennen gleichzeitig erstellt werden."""
        async def create_job(name: str):
            return await service.create_job(db=mock_db, name=name)

        # Erstelle 10 Jobs gleichzeitig
        tasks = [create_job(f"Concurrent Job {i}") for i in range(10)]
        jobs = await asyncio.gather(*tasks)

        assert len(jobs) == 10
        job_ids = [job.id for job in jobs]
        assert len(set(job_ids)) == 10  # Alle IDs sind einzigartig

    @pytest.mark.asyncio
    async def test_concurrent_job_access(
        self,
        service: BulkOCRProcessingService,
        mock_db: AsyncMock,
    ) -> None:
        """Jobs koennen gleichzeitig abgerufen werden."""
        job = await service.create_job(db=mock_db, name="Access Test")

        async def get_job_multiple_times():
            return await service.get_job(job_id=job.id)

        # 10 gleichzeitige Abrufe
        tasks = [get_job_multiple_times() for _ in range(10)]
        results = await asyncio.gather(*tasks)

        assert all(r is not None for r in results)
        assert all(r.id == job.id for r in results)
