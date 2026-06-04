# -*- coding: utf-8 -*-
"""
Bulk OCR Processing Service für Ablage-System OCR.

Orchestriert Massenverarbeitung aller Trainings-Dokumente durch alle OCR-Backends mit:
- Job-Management (Start, Pause, Resume, Status)
- GPU-Queue-Management für RTX 4080 (16GB VRAM)
- Checkpointing alle 100 Dokumente für Wiederaufnahme
- Fortschrittsanzeige mit ETA-Berechnung
- Dynamische Batch-Größen basierend auf VRAM

Feinpoliert und durchdacht - Enterprise-grade Bulk OCR Processing.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from enum import Enum
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple, AsyncIterator
from uuid import UUID, uuid4
import asyncio
import hashlib
import time

from sqlalchemy import select, and_, func, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
import structlog

from app.db.session import get_async_session_context

from app.db.models import (
    OCRTrainingSample,
    OCRBackendBenchmark,
    TrainingSampleStatus,
    OCRBulkProcessingJob as DBBulkProcessingJob,
    OCRDocumentOutput as DBDocumentOutput,
    OCRQualitySnapshot as DBQualitySnapshot,
    OCRModelDeployment as DBModelDeployment,
    BulkJobStatus as DBBulkJobStatus,
)
from app.services.benchmark_runner_service import (
    BenchmarkRunnerService,
    AVAILABLE_BACKENDS,
    DEFAULT_BACKENDS,
    BenchmarkResult,
)
from app.core.config import settings
from app.db.schemas import BulkProcessingProgress as BulkProgressSchema
from app.core.safe_errors import safe_error_log
from app.core.safe_errors import safe_error_detail

logger = structlog.get_logger(__name__)


# =============================================================================
# Enums und Konfiguration
# =============================================================================

class BulkJobStatus(str, Enum):
    """Status eines Bulk-Processing-Jobs."""
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class BackendBatchConfig:
    """Batch-Konfiguration pro Backend basierend auf VRAM."""
    backend_name: str
    batch_size: int
    vram_gb: float
    estimated_time_per_doc_ms: int


# Optimierte Batch-Größen für RTX 4080 (16GB VRAM)
BACKEND_BATCH_CONFIGS: Dict[str, BackendBatchConfig] = {
    "deepseek-janus-pro": BackendBatchConfig(
        backend_name="deepseek-janus-pro",
        batch_size=2,  # Konservativ wegen 12GB VRAM-Bedarf
        vram_gb=12.0,
        estimated_time_per_doc_ms=3000,
    ),
    "got-ocr-2.0": BackendBatchConfig(
        backend_name="got-ocr-2.0",
        batch_size=4,
        vram_gb=10.0,
        estimated_time_per_doc_ms=1500,
    ),
    "surya-gpu": BackendBatchConfig(
        backend_name="surya-gpu",
        batch_size=8,
        vram_gb=4.0,
        estimated_time_per_doc_ms=2000,
    ),
    "surya": BackendBatchConfig(
        backend_name="surya",
        batch_size=16,  # CPU-basiert, keine VRAM-Limits
        vram_gb=0.0,
        estimated_time_per_doc_ms=5000,
    ),
}

# Checkpoint-Intervall
CHECKPOINT_INTERVAL = 100  # Speichere Fortschritt alle 100 Dokumente


@dataclass
class BulkProcessingProgress:
    """Fortschrittsinformationen für einen Bulk-Processing-Job."""
    job_id: str
    status: BulkJobStatus
    current_backend: Optional[str]
    total_documents: int
    processed_documents: int
    documents_per_backend: Dict[str, int]
    failed_documents: int
    current_batch: int
    total_batches: int
    started_at: Optional[datetime]
    estimated_completion: Optional[datetime]
    elapsed_seconds: float
    documents_per_second: float
    last_checkpoint_at: Optional[datetime]
    error_message: Optional[str] = None


@dataclass
class BulkProcessingJob:
    """Repräsentiert einen Bulk-Processing-Job."""
    id: str
    name: str
    status: BulkJobStatus
    backends: List[str]
    total_documents: int
    processed_documents: int
    failed_documents: int
    current_backend: Optional[str]
    current_backend_index: int
    current_document_index: int
    documents_per_backend: Dict[str, int]
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    paused_at: Optional[datetime]
    last_checkpoint_at: Optional[datetime]
    error_log: List[Dict[str, Any]] = field(default_factory=list)
    configuration: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Konvertiert Job zu Dictionary."""
        return {
            "id": self.id,
            "name": self.name,
            "status": self.status.value,
            "backends": self.backends,
            "total_documents": self.total_documents,
            "processed_documents": self.processed_documents,
            "failed_documents": self.failed_documents,
            "current_backend": self.current_backend,
            "current_backend_index": self.current_backend_index,
            "current_document_index": self.current_document_index,
            "documents_per_backend": self.documents_per_backend,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "paused_at": self.paused_at.isoformat() if self.paused_at else None,
            "last_checkpoint_at": self.last_checkpoint_at.isoformat() if self.last_checkpoint_at else None,
            "error_log": self.error_log[-10:],  # Nur letzte 10 Fehler
            "configuration": self.configuration,
        }


# DB-Migration: Jobs werden in OCRBulkProcessingJob Tabelle persistiert (Multi-Worker Ready)
# In-Memory Cache nur für:
# - Cancel-Flags (Worker-lokal, schneller Zugriff)
# - Lokaler Job-Cache für aktiv laufende Jobs (Performance-Optimierung)
# HINWEIS: _job_cancel_flags.get() Aufrufe in Verarbeitungsschleifen
# sind absichtlich ohne Lock, da nur Bool-Reads (atomic) und Lock-Overhead vermieden wird.
_active_jobs_cache: Dict[str, BulkProcessingJob] = {}  # Lokaler Cache für laufende Jobs
_job_cancel_flags: Dict[str, bool] = {}
_job_storage_lock: asyncio.Lock = asyncio.Lock()  # Thread-Safety für concurrent access


def _db_job_to_dataclass(db_job) -> BulkProcessingJob:
    """Konvertiert DB-Model zu Dataclass."""
    return BulkProcessingJob(
        id=str(db_job.id),
        name=db_job.name,
        status=BulkJobStatus(db_job.status),
        backends=db_job.backends or [],
        total_documents=db_job.total_documents or 0,
        processed_documents=db_job.processed_documents or 0,
        failed_documents=db_job.failed_documents or 0,
        current_backend=db_job.current_backend,
        current_backend_index=db_job.current_backend_index or 0,
        current_document_index=db_job.current_document_index or 0,
        documents_per_backend=db_job.documents_per_backend or {},
        started_at=db_job.started_at,
        completed_at=db_job.completed_at,
        paused_at=db_job.paused_at,
        last_checkpoint_at=db_job.last_checkpoint_at,
        configuration=db_job.configuration or {},
        error_log=db_job.error_log or [],
    )


class BulkOCRProcessingService:
    """
    Service für Bulk OCR-Verarbeitung aller Trainings-Dokumente.

    Features:
    - Verarbeitung durch alle 4 OCR-Backends
    - GPU-Queue-Management
    - Checkpointing für Wiederaufnahme
    - Fortschrittsverfolgung
    """

    def __init__(self):
        """Initialisiere Bulk Processing Service."""
        self.benchmark_runner = BenchmarkRunnerService()
        logger.info(
            "bulk_ocr_processing_service_initialized",
            backends=list(BACKEND_BATCH_CONFIGS.keys())
        )

    # =========================================================================
    # JOB MANAGEMENT
    # =========================================================================

    async def create_job(
        self,
        db: AsyncSession,
        name: str,
        backends: Optional[List[str]] = None,
        source_directory: Optional[str] = None,
        sample_limit: Optional[int] = None,
    ) -> BulkProcessingJob:
        """
        Erstellt einen neuen Bulk-Processing-Job.

        Args:
            db: Datenbank-Session
            name: Job-Name
            backends: Liste der zu verwendenden Backends (default: alle 4)
            source_directory: Optionales Quellverzeichnis für Trainings-Daten
            sample_limit: Optionales Limit für Anzahl Samples

        Returns:
            BulkProcessingJob
        """
        job_id = str(uuid4())
        backends = backends or DEFAULT_BACKENDS

        # Zähle verfügbare Dokumente
        total_docs = await self._count_pending_documents(db, sample_limit)

        # Erstelle DB-Model (persistiert in OCRBulkProcessingJob Tabelle)
        from app.db.models import OCRBulkProcessingJob
        from uuid import UUID as UUIDType

        db_job = OCRBulkProcessingJob(
            id=UUIDType(job_id),
            name=name,
            status=BulkJobStatus.PENDING.value,
            backends=backends,
            total_documents=total_docs,
            processed_documents=0,
            failed_documents=0,
            current_backend=None,
            current_backend_index=0,
            current_document_index=0,
            documents_per_backend={b: 0 for b in backends},
            configuration={
                "source_directory": source_directory,
                "sample_limit": sample_limit,
                "checkpoint_interval": CHECKPOINT_INTERVAL,
            },
            error_log=[],
        )
        db.add(db_job)
        await db.commit()
        await db.refresh(db_job)

        # Erstelle Dataclass für Rückgabe
        job = _db_job_to_dataclass(db_job)

        # Cache und Cancel-Flag für laufende Verarbeitung
        async with _job_storage_lock:
            _active_jobs_cache[job_id] = job
            _job_cancel_flags[job_id] = False

        logger.info(
            "bulk_processing_job_created",
            job_id=job_id[:8],
            name=name,
            total_documents=total_docs,
            backends=backends,
            persisted_to_db=True,
        )

        return job

    async def start_job(
        self,
        db: AsyncSession,
        job_id: str,
        resume_from_checkpoint: bool = False,
    ) -> BulkProcessingJob:
        """
        Startet einen Bulk-Processing-Job.

        Args:
            db: Datenbank-Session
            job_id: Job-ID
            resume_from_checkpoint: Bei True wird vom letzten Checkpoint fortgesetzt

        Returns:
            Aktualisierter Job
        """
        from app.db.models import OCRBulkProcessingJob
        from uuid import UUID as UUIDType
        from sqlalchemy import select

        # Lade Job aus DB
        result = await db.execute(
            select(OCRBulkProcessingJob).where(OCRBulkProcessingJob.id == UUIDType(job_id))
        )
        db_job = result.scalar_one_or_none()

        if not db_job:
            raise ValueError(f"Job {job_id} nicht gefunden")

        if db_job.status == BulkJobStatus.RUNNING.value:
            raise ValueError(f"Job {job_id} läuft bereits")

        # Update DB
        db_job.status = BulkJobStatus.RUNNING.value
        db_job.started_at = db_job.started_at or datetime.now(timezone.utc)
        await db.commit()

        job = _db_job_to_dataclass(db_job)

        # Update Cache
        async with _job_storage_lock:
            _active_jobs_cache[job_id] = job
            _job_cancel_flags[job_id] = False

        logger.info(
            "bulk_processing_job_started",
            job_id=job_id[:8],
            resume=resume_from_checkpoint,
        )

        return job

    async def pause_job(self, db: AsyncSession, job_id: str) -> BulkProcessingJob:
        """Pausiert einen laufenden Job."""
        from app.db.models import OCRBulkProcessingJob
        from uuid import UUID as UUIDType
        from sqlalchemy import select

        result = await db.execute(
            select(OCRBulkProcessingJob).where(OCRBulkProcessingJob.id == UUIDType(job_id))
        )
        db_job = result.scalar_one_or_none()

        if not db_job:
            raise ValueError(f"Job {job_id} nicht gefunden")

        if db_job.status != BulkJobStatus.RUNNING.value:
            raise ValueError(f"Job {job_id} läuft nicht")

        # Update DB
        db_job.status = BulkJobStatus.PAUSED.value
        db_job.paused_at = datetime.now(timezone.utc)
        await db.commit()

        job = _db_job_to_dataclass(db_job)

        # Update Cache und setze Cancel-Flag
        async with _job_storage_lock:
            _job_cancel_flags[job_id] = True
            _active_jobs_cache[job_id] = job

        logger.info(
            "bulk_processing_job_paused",
            job_id=job_id[:8],
            processed=job.processed_documents,
        )

        return job

    async def cancel_job(self, db: AsyncSession, job_id: str) -> BulkProcessingJob:
        """Bricht einen Job ab."""
        from app.db.models import OCRBulkProcessingJob
        from uuid import UUID as UUIDType
        from sqlalchemy import select

        result = await db.execute(
            select(OCRBulkProcessingJob).where(OCRBulkProcessingJob.id == UUIDType(job_id))
        )
        db_job = result.scalar_one_or_none()

        if not db_job:
            raise ValueError(f"Job {job_id} nicht gefunden")

        # Update DB
        db_job.status = BulkJobStatus.CANCELLED.value
        db_job.completed_at = datetime.now(timezone.utc)
        await db.commit()

        job = _db_job_to_dataclass(db_job)

        # Update Cache und setze Cancel-Flag
        async with _job_storage_lock:
            _job_cancel_flags[job_id] = True
            _active_jobs_cache[job_id] = job

        logger.info(
            "bulk_processing_job_cancelled",
            job_id=job_id[:8],
            processed=job.processed_documents,
        )

        return job

    async def get_job(self, db: AsyncSession, job_id: str) -> Optional[BulkProcessingJob]:
        """Gibt einen Job zurück."""
        from app.db.models import OCRBulkProcessingJob
        from uuid import UUID as UUIDType
        from sqlalchemy import select

        # Erst Cache prüfen (für laufende Jobs)
        async with _job_storage_lock:
            if job_id in _active_jobs_cache:
                return _active_jobs_cache[job_id]

        # Dann aus DB laden
        result = await db.execute(
            select(OCRBulkProcessingJob).where(OCRBulkProcessingJob.id == UUIDType(job_id))
        )
        db_job = result.scalar_one_or_none()

        if not db_job:
            return None

        return _db_job_to_dataclass(db_job)

    async def get_job_progress(self, db: AsyncSession, job_id: str) -> Optional[BulkProcessingProgress]:
        """Berechnet detaillierte Fortschrittsinformationen."""
        job = await self.get_job(db, job_id)
        if not job:
            return None

        elapsed = 0.0
        docs_per_second = 0.0
        eta = None

        if job.started_at:
            elapsed = (datetime.now(timezone.utc) - job.started_at).total_seconds()
            if job.paused_at:
                elapsed = (job.paused_at - job.started_at).total_seconds()

            if elapsed > 0 and job.processed_documents > 0:
                docs_per_second = job.processed_documents / elapsed
                remaining = job.total_documents - job.processed_documents
                eta_seconds = remaining / docs_per_second if docs_per_second > 0 else 0
                eta = datetime.now(timezone.utc) + timedelta(seconds=eta_seconds)

        return BulkProcessingProgress(
            job_id=job.id,
            status=job.status,
            current_backend=job.current_backend,
            total_documents=job.total_documents,
            processed_documents=job.processed_documents,
            documents_per_backend=job.documents_per_backend,
            failed_documents=job.failed_documents,
            current_batch=job.current_document_index // CHECKPOINT_INTERVAL + 1,
            total_batches=(job.total_documents // CHECKPOINT_INTERVAL) + 1,
            started_at=job.started_at,
            estimated_completion=eta,
            elapsed_seconds=elapsed,
            documents_per_second=docs_per_second,
            last_checkpoint_at=job.last_checkpoint_at,
        )

    async def list_jobs(self, db: AsyncSession) -> List[BulkProcessingJob]:
        """Gibt alle Jobs zurück."""
        from app.db.models import OCRBulkProcessingJob

        from sqlalchemy import select

        result = await db.execute(
            select(OCRBulkProcessingJob).order_by(OCRBulkProcessingJob.created_at.desc())
        )
        db_jobs = result.scalars().all()

        return [_db_job_to_dataclass(job) for job in db_jobs]

    # =========================================================================
    # BULK PROCESSING EXECUTION
    # =========================================================================

    async def process_all_documents(
        self,
        db: AsyncSession,
        job_id: str,
    ) -> BulkProcessingJob:
        """
        Verarbeitet alle Dokumente durch alle Backends.

        Dies ist die Hauptmethode für die Bulk-Verarbeitung.
        Wird typischerweise von einem Celery-Task aufgerufen.

        Args:
            db: Datenbank-Session
            job_id: Job-ID

        Returns:
            Abgeschlossener Job
        """
        job = await self.get_job(job_id)
        if not job:
            raise ValueError(f"Job {job_id} nicht gefunden")

        try:
            # Starte Job falls noch nicht gestartet
            if job.status == BulkJobStatus.PENDING:
                job = await self.start_job(db, job_id)

            # Hole alle zu verarbeitenden Samples
            samples = await self._get_pending_samples(
                db,
                limit=job.configuration.get("sample_limit"),
            )

            total_samples = len(samples)
            logger.info(
                "bulk_processing_starting",
                job_id=job_id[:8],
                total_samples=total_samples,
                backends=job.backends,
            )

            # Verarbeite sequentiell durch alle Backends
            for backend_index, backend_name in enumerate(job.backends):
                if _job_cancel_flags.get(job_id, False):
                    logger.info("bulk_processing_cancelled", job_id=job_id[:8])
                    break

                job.current_backend = backend_name
                job.current_backend_index = backend_index

                batch_config = BACKEND_BATCH_CONFIGS.get(backend_name)
                if not batch_config:
                    logger.warning(
                        "unknown_backend_skipped",
                        backend=backend_name,
                    )
                    continue

                logger.info(
                    "bulk_processing_backend_starting",
                    job_id=job_id[:8],
                    backend=backend_name,
                    batch_size=batch_config.batch_size,
                )

                # Verarbeite in Batches
                await self._process_backend_batches(
                    db=db,
                    job=job,
                    samples=samples,
                    backend_name=backend_name,
                    batch_size=batch_config.batch_size,
                )

                logger.info(
                    "bulk_processing_backend_completed",
                    job_id=job_id[:8],
                    backend=backend_name,
                    processed=job.documents_per_backend.get(backend_name, 0),
                )

            # Job abschließen
            if not _job_cancel_flags.get(job_id, False):
                job.status = BulkJobStatus.COMPLETED
                job.completed_at = datetime.now(timezone.utc)

            logger.info(
                "bulk_processing_completed",
                job_id=job_id[:8],
                status=job.status.value,
                total_processed=job.processed_documents,
                failed=job.failed_documents,
            )

            return job

        except Exception as e:
            job.status = BulkJobStatus.FAILED
            job.error_log.append({
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "error": safe_error_detail(e, "Vorgang"),
                "backend": job.current_backend,
            })
            logger.exception(
                "bulk_processing_failed",
                job_id=job_id[:8],
                **safe_error_log(e),
            )
            raise

    async def _process_backend_batches(
        self,
        db: AsyncSession,
        job: BulkProcessingJob,
        samples: List[OCRTrainingSample],
        backend_name: str,
        batch_size: int,
    ) -> None:
        """
        Verarbeitet alle Samples durch ein Backend in Batches.

        Args:
            db: Datenbank-Session
            job: Job-Objekt
            samples: Zu verarbeitende Samples
            backend_name: Backend-Name
            batch_size: Batch-Größe
        """
        total_samples = len(samples)

        # Ensure OCR agents are loaded before processing
        await self.benchmark_runner._ensure_agents()

        for batch_start in range(0, total_samples, batch_size):
            if _job_cancel_flags.get(job.id, False):
                break

            batch_end = min(batch_start + batch_size, total_samples)
            batch_samples = samples[batch_start:batch_end]

            try:
                # Verarbeite Batch
                results = await self._process_batch(
                    db=db,
                    samples=batch_samples,
                    backend_name=backend_name,
                )

                # Update Fortschritt
                successful = sum(1 for r in results if r.success)
                failed = sum(1 for r in results if not r.success)

                job.documents_per_backend[backend_name] = (
                    job.documents_per_backend.get(backend_name, 0) + successful
                )
                job.processed_documents += successful
                job.failed_documents += failed
                job.current_document_index = batch_end

                # Checkpoint
                if batch_end % CHECKPOINT_INTERVAL < batch_size:
                    job.last_checkpoint_at = datetime.now(timezone.utc)
                    await self._save_checkpoint(db, job)

                    logger.info(
                        "bulk_processing_checkpoint",
                        job_id=job.id[:8],
                        backend=backend_name,
                        processed=batch_end,
                        total=total_samples,
                    )

            except Exception as e:
                job.error_log.append({
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "error": safe_error_detail(e, "Vorgang"),
                    "backend": backend_name,
                    "batch_start": batch_start,
                })
                logger.exception(
                    "batch_processing_error",
                    job_id=job.id[:8],
                    backend=backend_name,
                    batch_start=batch_start,
                    **safe_error_log(e),
                )

    async def _process_batch(
        self,
        db: AsyncSession,
        samples: List[OCRTrainingSample],
        backend_name: str,
    ) -> List[BenchmarkResult]:
        """
        Verarbeitet einen Batch von Samples durch ein Backend.

        Args:
            db: Datenbank-Session
            samples: Zu verarbeitende Samples
            backend_name: Backend-Name

        Returns:
            Liste der Benchmark-Ergebnisse
        """
        results: List[BenchmarkResult] = []

        for sample in samples:
            try:
                # Prüfe ob bereits verarbeitet
                existing = await self._get_existing_benchmark(
                    db, sample.id, backend_name
                )
                if existing:
                    results.append(BenchmarkResult(
                        backend_name=backend_name,
                        success=True,
                        raw_text=existing.raw_text,
                    ))
                    continue

                # Verarbeite mit BenchmarkRunner
                result = await self.benchmark_runner._run_single_benchmark(
                    sample=sample,
                    backend_name=backend_name,
                )

                # Speichere Ergebnis mit FRISCHER DB-Session
                # (verhindert Connection-Timeout bei langen OCR-Operationen)
                async with get_async_session_context() as fresh_db:
                    await self._save_benchmark_result(fresh_db, sample.id, result)

                results.append(result)

                logger.debug(
                    "benchmark_saved",
                    sample_id=str(sample.id)[:8],
                    backend=backend_name,
                )

            except Exception as e:
                results.append(BenchmarkResult(
                    backend_name=backend_name,
                    success=False,
                    **safe_error_log(e),
                ))
                logger.error(
                    "sample_processing_error",
                    sample_id=str(sample.id)[:8],
                    backend=backend_name,
                    **safe_error_log(e),
                )

        return results

    # =========================================================================
    # HELPER METHODS
    # =========================================================================

    async def _count_pending_documents(
        self,
        db: AsyncSession,
        limit: Optional[int] = None,
    ) -> int:
        """Zählt die Anzahl ausstehender Dokumente."""
        query = select(func.count(OCRTrainingSample.id))
        result = await db.execute(query)
        total = result.scalar() or 0
        return min(total, limit) if limit else total

    async def _get_pending_samples(
        self,
        db: AsyncSession,
        limit: Optional[int] = None,
    ) -> List[OCRTrainingSample]:
        """Holt alle zu verarbeitenden Samples."""
        query = select(OCRTrainingSample).order_by(OCRTrainingSample.created_at)
        if limit:
            query = query.limit(limit)
        result = await db.execute(query)
        return list(result.scalars().all())

    async def _get_existing_benchmark(
        self,
        db: AsyncSession,
        sample_id: UUID,
        backend_name: str,
    ) -> Optional[OCRBackendBenchmark]:
        """Prüft ob bereits ein vollständiger Benchmark existiert.

        Nur Benchmarks mit tatsächlichem OCR-Text werden als 'existierend'
        betrachtet, um leere/fehlgeschlagene Einträge zu überspringen.
        """
        query = select(OCRBackendBenchmark).where(
            and_(
                OCRBackendBenchmark.training_sample_id == sample_id,
                OCRBackendBenchmark.backend_name == backend_name,
                OCRBackendBenchmark.raw_text.isnot(None),  # Only count if has actual text
            )
        )
        result = await db.execute(query)
        return result.scalar_one_or_none()

    async def _save_benchmark_result(
        self,
        db: AsyncSession,
        sample_id: UUID,
        result: BenchmarkResult,
    ) -> OCRBackendBenchmark:
        """Speichert oder aktualisiert ein Benchmark-Ergebnis.

        Falls bereits ein (leerer) Eintrag existiert, wird dieser aktualisiert.
        """
        # Check for existing benchmark (including empty ones)
        query = select(OCRBackendBenchmark).where(
            and_(
                OCRBackendBenchmark.training_sample_id == sample_id,
                OCRBackendBenchmark.backend_name == result.backend_name,
            )
        )
        existing = await db.execute(query)
        benchmark = existing.scalar_one_or_none()

        if benchmark:
            # Update existing benchmark
            benchmark.raw_text = result.raw_text
            benchmark.confidence_score = result.confidence
            benchmark.cer = result.cer
            benchmark.wer = result.wer
            benchmark.umlaut_accuracy = result.umlaut_accuracy
            benchmark.capitalization_accuracy = result.capitalization_accuracy
            benchmark.processing_time_ms = result.processing_time_ms
            benchmark.gpu_memory_mb = result.gpu_memory_mb
            benchmark.insertions = result.insertions
            benchmark.deletions = result.deletions
            benchmark.substitutions = result.substitutions
            benchmark.error_patterns = result.error_patterns
            benchmark.field_accuracies = result.field_accuracies
        else:
            # Create new benchmark
            benchmark = OCRBackendBenchmark(
                training_sample_id=sample_id,
                backend_name=result.backend_name,
                raw_text=result.raw_text,
                confidence_score=result.confidence,
                cer=result.cer,
                wer=result.wer,
                umlaut_accuracy=result.umlaut_accuracy,
                capitalization_accuracy=result.capitalization_accuracy,
                processing_time_ms=result.processing_time_ms,
                gpu_memory_mb=result.gpu_memory_mb,
                insertions=result.insertions,
                deletions=result.deletions,
                substitutions=result.substitutions,
                error_patterns=result.error_patterns,
                field_accuracies=result.field_accuracies,
            )
            db.add(benchmark)

        await db.commit()
        return benchmark

    async def _save_checkpoint(
        self,
        db: AsyncSession,
        job: BulkProcessingJob,
    ) -> None:
        """Speichert einen Checkpoint des Jobs in der Datenbank."""
        now = datetime.now(timezone.utc)
        job.last_checkpoint_at = now

        # DB-Update mit allen relevanten Feldern
        try:
            await db.execute(
                update(DBBulkProcessingJob)
                .where(DBBulkProcessingJob.id == UUID(job.id))
                .values(
                    status=job.status.value,
                    processed_documents=job.processed_documents,
                    failed_documents=job.failed_documents,
                    current_backend=job.current_backend,
                    current_backend_index=job.current_backend_index,
                    current_document_index=job.current_document_index,
                    documents_per_backend=job.documents_per_backend,
                    error_log=job.error_log[-100:],  # Begrenzt auf 100 Einträge
                    last_checkpoint_at=now,
                )
            )
            await db.commit()
        except Exception as e:
            logger.warning(
                "checkpoint_db_save_failed",
                job_id=job.id[:8],
                **safe_error_log(e),
            )
            await db.rollback()

        # Lokaler Cache-Update für schnellen Zugriff
        async with _job_storage_lock:
            _active_jobs_cache[job.id] = job

        logger.debug(
            "checkpoint_saved",
            job_id=job.id[:8],
            processed=job.processed_documents,
            backend=job.current_backend,
        )

    # =========================================================================
    # TRAINING DATA IMPORT
    # =========================================================================

    async def import_training_files(
        self,
        db: AsyncSession,
        source_directory: str,
        file_patterns: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Importiert Trainings-Dateien aus einem Verzeichnis.

        Args:
            db: Datenbank-Session
            source_directory: Quellverzeichnis (z.B. "Trainings_Data")
            file_patterns: Datei-Muster (default: ["*.pdf", "*.tif", "*.PDF", "*.TIF"])

        Returns:
            Import-Statistiken
        """
        from pathlib import Path

        patterns = file_patterns or ["*.pdf", "*.tif", "*.PDF", "*.TIF", "*.png", "*.jpg"]
        source_path = Path(source_directory)

        if not source_path.exists():
            raise ValueError(f"Verzeichnis nicht gefunden: {source_directory}")

        imported = 0
        skipped = 0
        errors = 0
        error_list: List[Dict[str, str]] = []

        for pattern in patterns:
            for file_path in source_path.rglob(pattern):
                try:
                    # Berechne Hash
                    file_hash = hashlib.sha256(
                        str(file_path).encode()
                    ).hexdigest()

                    # Prüfe auf Duplikat
                    existing = await db.execute(
                        select(OCRTrainingSample).where(
                            OCRTrainingSample.file_hash == file_hash
                        )
                    )
                    if existing.scalar_one_or_none():
                        skipped += 1
                        continue

                    # Extrahiere Metadaten aus Pfad
                    language = "de"  # Default Deutsch
                    document_type = "unknown"

                    path_str = str(file_path).lower()
                    if "_nl_" in path_str or "/nl/" in path_str:
                        language = "nl"
                    elif "_pl_" in path_str or "/pl/" in path_str:
                        language = "pl"
                    elif "_en_" in path_str or "/en/" in path_str:
                        language = "en"

                    if "invoice" in path_str or "rechnung" in path_str:
                        document_type = "invoice"
                    elif "contract" in path_str or "vertrag" in path_str:
                        document_type = "contract"
                    elif "letter" in path_str or "brief" in path_str:
                        document_type = "letter"

                    # Erstelle Sample
                    sample = OCRTrainingSample(
                        file_path=str(file_path),
                        file_hash=file_hash,
                        language=language,
                        document_type=document_type,
                        status=TrainingSampleStatus.PENDING.value,
                    )
                    db.add(sample)
                    imported += 1

                    # Commit in Batches
                    if imported % 100 == 0:
                        await db.commit()
                        logger.info(
                            "import_progress",
                            imported=imported,
                            skipped=skipped,
                        )

                except Exception as e:
                    errors += 1
                    error_list.append({
                        "file": str(file_path),
                        "error": safe_error_detail(e, "Vorgang"),
                    })

        await db.commit()

        result = {
            "imported": imported,
            "skipped": skipped,
            "errors": errors,
            "error_list": error_list[:20],  # Nur erste 20 Fehler
            "source_directory": source_directory,
        }

        logger.info(
            "training_files_imported",
            **result,
        )

        return result


# =============================================================================
# Database-basierter Service für API-Integration
# =============================================================================

class BulkOCRProcessingServiceDB:
    """
    Database-basierter Service für Bulk OCR-Verarbeitung.

    Nutzt die SQLAlchemy-Modelle für persistente Speicherung.
    Wird von den API-Endpoints verwendet.
    """

    def __init__(self, db: AsyncSession):
        """Initialisiere mit Datenbank-Session."""
        self.db = db
        self._in_memory_service = BulkOCRProcessingService()

    # =========================================================================
    # JOB MANAGEMENT (Database-backed)
    # =========================================================================

    async def create_job(
        self,
        name: str,
        description: Optional[str] = None,
        backends: Optional[List[str]] = None,
        configuration: Optional[Dict[str, Any]] = None,
        created_by_id: Optional[UUID] = None,
    ) -> DBBulkProcessingJob:
        """Erstellt einen neuen Bulk Processing Job in der Datenbank."""
        backends = backends or DEFAULT_BACKENDS
        total_docs = await self._in_memory_service._count_pending_documents(self.db)

        job = DBBulkProcessingJob(
            name=name,
            description=description,
            status=DBBulkJobStatus.PENDING.value,
            backends=backends,
            total_documents=total_docs,
            processed_documents=0,
            failed_documents=0,
            current_backend_index=0,
            current_document_index=0,
            documents_per_backend={b: 0 for b in backends},
            configuration=configuration or {},
            error_log=[],
            created_by_id=created_by_id,
        )
        self.db.add(job)
        await self.db.commit()
        await self.db.refresh(job)

        logger.info(
            "bulk_job_created_db",
            job_id=str(job.id)[:8],
            name=name,
            total_documents=total_docs,
        )

        return job

    async def get_job(self, job_id: UUID) -> Optional[DBBulkProcessingJob]:
        """Ruft einen Job aus der Datenbank ab."""
        result = await self.db.execute(
            select(DBBulkProcessingJob).where(DBBulkProcessingJob.id == job_id)
        )
        return result.scalar_one_or_none()

    async def list_jobs(
        self,
        status: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Tuple[List[DBBulkProcessingJob], int]:
        """Listet alle Jobs mit optionalem Status-Filter."""
        query = select(DBBulkProcessingJob)

        if status:
            query = query.where(DBBulkProcessingJob.status == status)

        # Count total
        count_query = select(func.count()).select_from(query.subquery())
        total = (await self.db.execute(count_query)).scalar() or 0

        # Get page
        query = query.order_by(DBBulkProcessingJob.created_at.desc())
        query = query.offset(offset).limit(limit)

        result = await self.db.execute(query)
        jobs = list(result.scalars().all())

        return jobs, total

    async def update_job_status(
        self,
        job_id: UUID,
        status: str,
    ) -> DBBulkProcessingJob:
        """Aktualisiert den Status eines Jobs."""
        job = await self.get_job(job_id)
        if not job:
            raise ValueError(f"Job {job_id} nicht gefunden")

        job.status = status

        if status == "running" and not job.started_at:
            job.started_at = datetime.now(timezone.utc)
        elif status == "paused":
            job.paused_at = datetime.now(timezone.utc)
        elif status in ("completed", "failed", "cancelled"):
            job.completed_at = datetime.now(timezone.utc)

        await self.db.commit()
        await self.db.refresh(job)
        return job

    async def pause_job(self, job_id: UUID) -> DBBulkProcessingJob:
        """Pausiert einen laufenden Job."""
        job = await self.get_job(job_id)
        if not job:
            raise ValueError(f"Job {job_id} nicht gefunden")

        if job.status != DBBulkJobStatus.RUNNING.value:
            raise ValueError(f"Job kann nicht pausiert werden. Status: {job.status}")

        job.status = DBBulkJobStatus.PAUSED.value
        job.paused_at = datetime.now(timezone.utc)
        job.last_checkpoint_at = datetime.now(timezone.utc)

        await self.db.commit()
        await self.db.refresh(job)

        logger.info("bulk_job_paused", job_id=str(job_id)[:8])
        return job

    async def cancel_job(self, job_id: UUID) -> DBBulkProcessingJob:
        """Bricht einen Job ab."""
        job = await self.get_job(job_id)
        if not job:
            raise ValueError(f"Job {job_id} nicht gefunden")

        if job.status in (DBBulkJobStatus.COMPLETED.value, DBBulkJobStatus.CANCELLED.value):
            raise ValueError(f"Job kann nicht abgebrochen werden. Status: {job.status}")

        job.status = DBBulkJobStatus.CANCELLED.value
        job.completed_at = datetime.now(timezone.utc)

        await self.db.commit()
        await self.db.refresh(job)

        logger.info("bulk_job_cancelled", job_id=str(job_id)[:8])
        return job

    async def get_progress(self, job_id: UUID) -> Optional[BulkProgressSchema]:
        """Berechnet detaillierte Fortschrittsinformationen."""
        job = await self.get_job(job_id)
        if not job:
            return None

        elapsed_seconds = 0
        processing_rate = None
        estimated_remaining = None

        if job.started_at:
            now = datetime.now(timezone.utc)
            if job.paused_at:
                elapsed_seconds = int((job.paused_at - job.started_at).total_seconds())
            elif job.completed_at:
                elapsed_seconds = int((job.completed_at - job.started_at).total_seconds())
            else:
                elapsed_seconds = int((now - job.started_at).total_seconds())

            if elapsed_seconds > 0 and job.processed_documents > 0:
                processing_rate = job.processed_documents / elapsed_seconds * 60  # per minute
                remaining = job.total_documents - job.processed_documents
                if processing_rate > 0:
                    estimated_remaining = int(remaining / (processing_rate / 60))

        progress_percent = 0.0
        if job.total_documents > 0:
            progress_percent = (job.processed_documents / job.total_documents) * 100

        return BulkProgressSchema(
            job_id=job.id,
            status=job.status,
            total_documents=job.total_documents,
            processed_documents=job.processed_documents,
            failed_documents=job.failed_documents,
            progress_percent=round(progress_percent, 2),
            current_backend=job.current_backend,
            current_backend_index=job.current_backend_index,
            total_backends=len(job.backends) if job.backends else 0,
            documents_per_backend=job.documents_per_backend or {},
            estimated_time_remaining_seconds=estimated_remaining,
            processing_rate_per_minute=round(processing_rate, 2) if processing_rate else None,
            started_at=job.started_at,
            elapsed_seconds=elapsed_seconds,
        )

    # =========================================================================
    # OCR DOCUMENT OUTPUTS
    # =========================================================================

    async def get_sample_outputs(self, sample_id: UUID) -> List[DBDocumentOutput]:
        """Ruft alle OCR-Outputs für ein Sample ab."""
        result = await self.db.execute(
            select(DBDocumentOutput)
            .where(DBDocumentOutput.training_sample_id == sample_id)
            .order_by(DBDocumentOutput.backend_name)
        )
        return list(result.scalars().all())

    async def get_output(self, output_id: UUID) -> Optional[DBDocumentOutput]:
        """Ruft einen einzelnen OCR-Output ab."""
        result = await self.db.execute(
            select(DBDocumentOutput).where(DBDocumentOutput.id == output_id)
        )
        return result.scalar_one_or_none()

    async def save_document_output(
        self,
        sample_id: UUID,
        backend_name: str,
        raw_text: Optional[str],
        structured_output: Optional[Dict[str, Any]] = None,
        confidence_score: Optional[float] = None,
        processing_time_ms: Optional[int] = None,
        gpu_memory_mb: Optional[int] = None,
        error_message: Optional[str] = None,
        success: bool = True,
        bulk_job_id: Optional[UUID] = None,
    ) -> DBDocumentOutput:
        """Speichert einen OCR-Output in der Datenbank."""
        output = DBDocumentOutput(
            training_sample_id=sample_id,
            bulk_job_id=bulk_job_id,
            backend_name=backend_name,
            raw_text=raw_text,
            structured_output=structured_output,
            confidence_score=confidence_score,
            processing_time_ms=processing_time_ms,
            gpu_memory_mb=gpu_memory_mb,
            error_message=error_message,
            success=success,
        )
        self.db.add(output)
        await self.db.commit()
        await self.db.refresh(output)
        return output

    # =========================================================================
    # QUALITY SNAPSHOTS
    # =========================================================================

    async def get_quality_snapshots(
        self,
        backend_name: str,
        hours: int = 24,
    ) -> List[DBQualitySnapshot]:
        """Ruft Quality Snapshots für ein Backend ab."""
        since = datetime.now(timezone.utc) - timedelta(hours=hours)

        result = await self.db.execute(
            select(DBQualitySnapshot)
            .where(
                and_(
                    DBQualitySnapshot.backend_name == backend_name,
                    DBQualitySnapshot.snapshot_time >= since,
                )
            )
            .order_by(DBQualitySnapshot.snapshot_time.desc())
        )
        return list(result.scalars().all())

    async def create_quality_snapshot(
        self,
        backend_name: str,
    ) -> DBQualitySnapshot:
        """Erstellt einen Quality Snapshot für ein Backend."""
        # Berechne Metriken aus aktuellen Benchmarks
        stats_query = select(
            func.count(OCRBackendBenchmark.id).label("count"),
            func.avg(OCRBackendBenchmark.cer).label("avg_cer"),
            func.avg(OCRBackendBenchmark.wer).label("avg_wer"),
            func.avg(OCRBackendBenchmark.umlaut_accuracy).label("avg_umlaut"),
            func.avg(OCRBackendBenchmark.processing_time_ms).label("avg_time"),
        ).where(OCRBackendBenchmark.backend_name == backend_name)

        result = await self.db.execute(stats_query)
        stats = result.first()

        # Percentiles für CER (vereinfacht)
        cer_query = select(OCRBackendBenchmark.cer).where(
            and_(
                OCRBackendBenchmark.backend_name == backend_name,
                OCRBackendBenchmark.cer.isnot(None),
            )
        ).order_by(OCRBackendBenchmark.cer)

        cer_result = await self.db.execute(cer_query)
        cer_values = [r[0] for r in cer_result.fetchall()]

        p50_cer = p90_cer = p99_cer = None
        if cer_values:
            n = len(cer_values)
            p50_cer = cer_values[int(n * 0.50)] if n > 0 else None
            p90_cer = cer_values[int(n * 0.90)] if n > 0 else None
            p99_cer = cer_values[int(n * 0.99)] if n > 0 else None

        snapshot = DBQualitySnapshot(
            backend_name=backend_name,
            sample_count=stats.count if stats else 0,
            avg_cer=stats.avg_cer if stats else None,
            avg_wer=stats.avg_wer if stats else None,
            avg_umlaut_accuracy=stats.avg_umlaut if stats else None,
            avg_processing_time_ms=stats.avg_time if stats else None,
            p50_cer=p50_cer,
            p90_cer=p90_cer,
            p99_cer=p99_cer,
        )
        self.db.add(snapshot)
        await self.db.commit()
        await self.db.refresh(snapshot)

        logger.info(
            "quality_snapshot_created",
            backend=backend_name,
            sample_count=snapshot.sample_count,
        )
        return snapshot

    # =========================================================================
    # MODEL DEPLOYMENTS
    # =========================================================================

    async def get_model_deployments(self, model_name: str) -> List[DBModelDeployment]:
        """Ruft alle Deployments für ein Model ab."""
        result = await self.db.execute(
            select(DBModelDeployment)
            .where(DBModelDeployment.model_name == model_name)
            .order_by(DBModelDeployment.created_at.desc())
        )
        return list(result.scalars().all())

    async def create_model_deployment(
        self,
        model_name: str,
        version: str,
        model_type: str,
        checkpoint_path: Optional[str] = None,
        training_job_id: Optional[UUID] = None,
        traffic_percentage: float = 0.0,
        deployed_by_id: Optional[UUID] = None,
    ) -> DBModelDeployment:
        """Erstellt ein neues Model Deployment."""
        deployment = DBModelDeployment(
            model_name=model_name,
            version=version,
            model_type=model_type,
            is_active=False,
            is_default=False,
            traffic_percentage=traffic_percentage,
            checkpoint_path=checkpoint_path,
            training_job_id=training_job_id,
            deployed_by_id=deployed_by_id,
        )
        self.db.add(deployment)
        await self.db.commit()
        await self.db.refresh(deployment)

        logger.info(
            "model_deployment_created",
            model=model_name,
            version=version,
        )
        return deployment

    async def activate_deployment(self, deployment_id: UUID) -> DBModelDeployment:
        """Aktiviert ein Deployment und deaktiviert vorherige."""
        deployment = await self.db.execute(
            select(DBModelDeployment).where(DBModelDeployment.id == deployment_id)
        )
        deployment = deployment.scalar_one_or_none()

        if not deployment:
            raise ValueError(f"Deployment {deployment_id} nicht gefunden")

        # Deaktiviere andere Deployments des gleichen Models
        await self.db.execute(
            update(DBModelDeployment)
            .where(
                and_(
                    DBModelDeployment.model_name == deployment.model_name,
                    DBModelDeployment.is_active == True,  # noqa: E712
                )
            )
            .values(
                is_active=False,
                deactivated_at=datetime.now(timezone.utc),
            )
        )

        # Aktiviere neues Deployment
        deployment.is_active = True
        deployment.deployed_at = datetime.now(timezone.utc)

        await self.db.commit()
        await self.db.refresh(deployment)

        logger.info(
            "model_deployment_activated",
            model=deployment.model_name,
            version=deployment.version,
        )
        return deployment

    async def rollback_deployment(
        self,
        deployment_id: UUID,
        reason: str,
    ) -> DBModelDeployment:
        """Führt Rollback zu einer früheren Version durch."""
        deployment = await self.db.execute(
            select(DBModelDeployment).where(DBModelDeployment.id == deployment_id)
        )
        deployment = deployment.scalar_one_or_none()

        if not deployment:
            raise ValueError(f"Deployment {deployment_id} nicht gefunden")

        # Finde aktuelle aktive Version
        current_active = await self.db.execute(
            select(DBModelDeployment).where(
                and_(
                    DBModelDeployment.model_name == deployment.model_name,
                    DBModelDeployment.is_active == True,  # noqa: E712
                )
            )
        )
        current = current_active.scalar_one_or_none()

        if current:
            deployment.previous_version = current.version
            current.is_active = False
            current.deactivated_at = datetime.now(timezone.utc)

        deployment.is_active = True
        deployment.deployed_at = datetime.now(timezone.utc)
        deployment.rollback_reason = reason

        await self.db.commit()
        await self.db.refresh(deployment)

        logger.info(
            "model_deployment_rollback",
            model=deployment.model_name,
            to_version=deployment.version,
            reason=reason,
        )
        return deployment


# Singleton-Instanz (für In-Memory Service)
_service_instance: Optional[BulkOCRProcessingService] = None


def get_bulk_ocr_processing_service_sync() -> BulkOCRProcessingService:
    """Gibt die Singleton-Instanz des In-Memory Services zurück (für Celery Tasks)."""
    global _service_instance
    if _service_instance is None:
        _service_instance = BulkOCRProcessingService()
    return _service_instance


async def get_bulk_ocr_processing_service(db: AsyncSession) -> BulkOCRProcessingServiceDB:
    """
    Factory-Funktion für Database-backed Service.

    Wird von FastAPI Dependency Injection verwendet.
    """
    return BulkOCRProcessingServiceDB(db)
