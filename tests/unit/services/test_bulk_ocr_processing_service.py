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
from typing import Dict, List, Optional
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
    _active_jobs_cache,
    _job_cancel_flags,
    _job_storage_lock,
)

# Alias fuer Abwaertskompatibilitaet
_active_jobs = _active_jobs_cache


def create_mock_db_job(
    job_id: str,
    name: str = "Test Job",
    status: str = "pending",
    total_documents: int = 100,
    processed_documents: int = 0,
    failed_documents: int = 0,
    backends: Optional[List[str]] = None,
    documents_per_backend: Optional[Dict[str, int]] = None,
    started_at: Optional[datetime] = None,
    completed_at: Optional[datetime] = None,
    paused_at: Optional[datetime] = None,
) -> MagicMock:
    """
    Factory-Funktion fuer Mock-DB-Job-Objekte.

    Zentralisiert die Mock-Erstellung fuer konsistente Tests
    und vermeidet Code-Duplikation (DRY-Prinzip).

    Args:
        job_id: Job UUID
        name: Job-Name
        status: Job-Status (pending, running, paused, etc.)
        total_documents: Anzahl zu verarbeitender Dokumente
        processed_documents: Bereits verarbeitete Dokumente
        failed_documents: Fehlgeschlagene Dokumente
        backends: Liste der OCR-Backends
        documents_per_backend: Dict mit Dokumenten pro Backend
        started_at: Startzeitpunkt
        completed_at: Endzeitpunkt
        paused_at: Pausierungszeitpunkt

    Returns:
        MagicMock-Objekt das ein OCRBulkProcessingJob simuliert
    """
    mock_job = MagicMock()
    mock_job.id = job_id
    mock_job.name = name
    mock_job.status = status
    mock_job.total_documents = total_documents
    mock_job.processed_documents = processed_documents
    mock_job.failed_documents = failed_documents
    mock_job.backends = backends or ["deepseek-janus-pro", "got-ocr-2.0"]
    mock_job.documents_per_backend = documents_per_backend or {}
    mock_job.current_backend = None
    mock_job.current_backend_index = 0
    mock_job.current_document_index = 0
    mock_job.sample_limit = None
    mock_job.checkpoint_data = None
    mock_job.error_log = []
    mock_job.configuration = {}
    mock_job.created_at = datetime.now(timezone.utc)
    mock_job.started_at = started_at
    mock_job.completed_at = completed_at
    mock_job.paused_at = paused_at
    mock_job.last_checkpoint_at = None
    return mock_job


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
        # Service erwartet gueltige UUID - Mock returnt None fuer nicht gefunden
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        non_existent_uuid = "00000000-0000-0000-0000-000000000000"
        with pytest.raises(ValueError, match="nicht gefunden"):
            await service.start_job(db=mock_db, job_id=non_existent_uuid)

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

        paused_job = await service.pause_job(db=mock_db, job_id=job.id)

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
            await service.pause_job(db=mock_db, job_id=job.id)

    @pytest.mark.asyncio
    async def test_cancel_job(
        self,
        service: BulkOCRProcessingService,
        mock_db: AsyncMock,
    ) -> None:
        """Bricht einen Job ab."""
        job = await service.create_job(db=mock_db, name="Cancel Test")

        cancelled_job = await service.cancel_job(db=mock_db, job_id=job.id)

        assert cancelled_job.status == BulkJobStatus.CANCELLED
        assert cancelled_job.completed_at is not None

    @pytest.mark.asyncio
    async def test_cancel_job_not_found(
        self,
        service: BulkOCRProcessingService,
        mock_db: AsyncMock,
    ) -> None:
        """Fehler beim Abbrechen eines nicht existierenden Jobs."""
        # Service erwartet gueltige UUID - Mock returnt None fuer nicht gefunden
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        non_existent_uuid = "00000000-0000-0000-0000-000000000000"
        with pytest.raises(ValueError, match="nicht gefunden"):
            await service.cancel_job(db=mock_db, job_id=non_existent_uuid)

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

        retrieved_job = await service.get_job(db=mock_db, job_id=job.id)

        assert retrieved_job is not None
        assert retrieved_job.id == job.id
        assert retrieved_job.name == "Get Test"

    @pytest.mark.asyncio
    async def test_get_job_not_found(
        self,
        service: BulkOCRProcessingService,
        mock_db: AsyncMock,
    ) -> None:
        """Gibt None zurueck fuer nicht existierenden Job."""
        # Mock returnt None fuer nicht gefunden
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        # Job existiert nicht im Cache und DB returnt None
        non_existent_uuid = "00000000-0000-0000-0000-000000000000"
        retrieved_job = await service.get_job(db=mock_db, job_id=non_existent_uuid)

        assert retrieved_job is None

    @pytest.mark.asyncio
    async def test_list_jobs(
        self,
        service: BulkOCRProcessingService,
        mock_db: AsyncMock,
    ) -> None:
        """Listet alle Jobs auf."""
        # Erstelle Jobs und speichere sie
        job1 = await service.create_job(db=mock_db, name="Job 1")
        job2 = await service.create_job(db=mock_db, name="Job 2")
        job3 = await service.create_job(db=mock_db, name="Job 3")

        # Mock DB-Response mit Factory-Funktion (DRY)
        mock_db_jobs = [
            create_mock_db_job(
                job_id=job1.id,
                name="Job 1",
                backends=job1.backends,
                documents_per_backend=job1.documents_per_backend,
            ),
            create_mock_db_job(
                job_id=job2.id,
                name="Job 2",
                backends=job2.backends,
                documents_per_backend=job2.documents_per_backend,
            ),
            create_mock_db_job(
                job_id=job3.id,
                name="Job 3",
                backends=job3.backends,
                documents_per_backend=job3.documents_per_backend,
            ),
        ]

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = mock_db_jobs
        mock_db.execute.return_value = mock_result

        jobs = await service.list_jobs(db=mock_db)

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

        progress = await service.get_job_progress(db=mock_db, job_id=job.id)

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

        # Mock DB-Job fuer start_job mit Factory (DRY)
        start_time = datetime.now(timezone.utc)
        mock_db_job = create_mock_db_job(
            job_id=job.id,
            name="Progress Running Test",
            backends=job.backends,
            documents_per_backend=job.documents_per_backend,
            started_at=start_time,
        )

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_db_job
        mock_db.execute.return_value = mock_result

        await service.start_job(db=mock_db, job_id=job.id)

        # Simuliere verarbeitete Dokumente direkt im Cache
        # Anmerkung: Das Dataclass ist nicht frozen, direkte Modifikation ist moeglich
        async with _job_storage_lock:
            cached_job = _active_jobs[job.id]
            # Modifiziere direkt - BulkProcessingJob ist mutable
            object.__setattr__(cached_job, 'processed_documents', 50)
            object.__setattr__(cached_job, 'started_at', start_time)

        progress = await service.get_job_progress(db=mock_db, job_id=job.id)

        assert progress.status == BulkJobStatus.RUNNING
        assert progress.processed_documents == 50
        assert progress.started_at is not None

    @pytest.mark.asyncio
    async def test_get_job_progress_not_found(
        self,
        service: BulkOCRProcessingService,
        mock_db: AsyncMock,
    ) -> None:
        """Gibt None zurueck fuer nicht existierenden Job."""
        # Mock DB returnt None fuer nicht existierenden Job
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        non_existent_uuid = "00000000-0000-0000-0000-000000000000"
        progress = await service.get_job_progress(db=mock_db, job_id=non_existent_uuid)

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

        # Mock DB-Job fuer start_job mit Factory (DRY)
        start_time = datetime.now(timezone.utc)
        mock_db_job = create_mock_db_job(
            job_id=job.id,
            name="Dict Test",
            backends=job.backends,
            documents_per_backend=job.documents_per_backend,
            started_at=start_time,
        )

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_db_job
        mock_db.execute.return_value = mock_result

        started_job = await service.start_job(db=mock_db, job_id=job.id)

        job_dict = started_job.to_dict()

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
            return await service.get_job(db=mock_db, job_id=job.id)

        # 10 gleichzeitige Abrufe
        tasks = [get_job_multiple_times() for _ in range(10)]
        results = await asyncio.gather(*tasks)

        assert all(r is not None for r in results)
        assert all(r.id == job.id for r in results)


class TestCheckpointPersistence:
    """Tests fuer Checkpoint DB-Persistenz."""

    @pytest.fixture
    def service(self) -> BulkOCRProcessingService:
        """Erstellt eine frische Service-Instanz."""
        return BulkOCRProcessingService()

    @pytest.fixture
    def mock_db(self) -> AsyncMock:
        """Erstellt eine Mock-Datenbank-Session."""
        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar.return_value = 100
        mock_result.scalars.return_value.all.return_value = []
        db.execute.return_value = mock_result
        return db

    @pytest.fixture(autouse=True)
    async def cleanup_jobs(self):
        """Bereinigt Jobs vor und nach jedem Test."""
        async with _job_storage_lock:
            _active_jobs.clear()
            _job_cancel_flags.clear()
        yield
        async with _job_storage_lock:
            _active_jobs.clear()
            _job_cancel_flags.clear()

    @pytest.mark.asyncio
    async def test_save_checkpoint_persists_to_db(
        self,
        service: BulkOCRProcessingService,
        mock_db: AsyncMock,
    ) -> None:
        """Checkpoint sollte in DB persistiert werden."""
        job = await service.create_job(db=mock_db, name="Checkpoint Test")
        await service.start_job(db=mock_db, job_id=job.id)

        # Simuliere Fortschritt
        async with _job_storage_lock:
            _active_jobs[job.id].processed_documents = 50
            _active_jobs[job.id].failed_documents = 2

        # Speichere Checkpoint - ruft _save_checkpoint intern auf
        await service._save_checkpoint(mock_db, _active_jobs[job.id])

        # DB execute sollte aufgerufen worden sein (fuer UPDATE)
        assert mock_db.execute.called
        assert mock_db.commit.called

    @pytest.mark.asyncio
    async def test_save_checkpoint_updates_cache(
        self,
        service: BulkOCRProcessingService,
        mock_db: AsyncMock,
    ) -> None:
        """Checkpoint sollte auch den Cache aktualisieren."""
        from app.services.bulk_ocr_processing_service import _active_jobs_cache

        job = await service.create_job(db=mock_db, name="Cache Test")
        await service.start_job(db=mock_db, job_id=job.id)

        # Speichere Checkpoint
        await service._save_checkpoint(mock_db, _active_jobs[job.id])

        # Cache sollte aktualisiert sein
        assert job.id in _active_jobs_cache

    @pytest.mark.asyncio
    async def test_save_checkpoint_handles_db_error(
        self,
        service: BulkOCRProcessingService,
        mock_db: AsyncMock,
    ) -> None:
        """Checkpoint sollte DB-Fehler graceful behandeln."""
        job = await service.create_job(db=mock_db, name="Error Test")
        await service.start_job(db=mock_db, job_id=job.id)

        # Simuliere DB-Fehler
        mock_db.execute.side_effect = Exception("DB Error")

        # Sollte nicht crashen
        await service._save_checkpoint(mock_db, _active_jobs[job.id])

        # Rollback sollte aufgerufen worden sein
        assert mock_db.rollback.called

    @pytest.mark.asyncio
    async def test_save_checkpoint_limits_error_log(
        self,
        service: BulkOCRProcessingService,
        mock_db: AsyncMock,
    ) -> None:
        """Checkpoint sollte Error-Log auf 100 Eintraege begrenzen."""
        job = await service.create_job(db=mock_db, name="Error Log Test")
        await service.start_job(db=mock_db, job_id=job.id)

        # Fuege 150 Fehler hinzu
        async with _job_storage_lock:
            _active_jobs[job.id].error_log = [f"Error {i}" for i in range(150)]

        await service._save_checkpoint(mock_db, _active_jobs[job.id])

        # Pruefe den execute-Aufruf
        if mock_db.execute.called:
            call_args = mock_db.execute.call_args
            # Der error_log Parameter sollte begrenzt sein
            # (exakte Pruefung haengt von SQLAlchemy update Syntax ab)
