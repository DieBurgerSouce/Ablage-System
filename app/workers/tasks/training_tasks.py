# -*- coding: utf-8 -*-
"""
OCR Training Celery Tasks.

Enthält:
- Benchmark-Batch-Verarbeitung
- Tägliche Statistik-Aggregation
- Feedback-Queue-Verarbeitung
- Wöchentliche Benchmarks

Feinpoliert und durchdacht - OCR Training für Produktion.
"""

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import structlog

from app.workers.celery_app import celery_app, CPUTask, GPUTask
from app.core.config import settings

logger = structlog.get_logger(__name__)


# ==================== Benchmark Tasks ====================

@celery_app.task(
    bind=True,
    base=GPUTask,
    name="app.workers.tasks.training_tasks.run_benchmark_batch",
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 3},
    retry_backoff=True,
    retry_backoff_max=600,
    soft_time_limit=1800,  # 30 Minuten
    time_limit=2100,  # 35 Minuten
    acks_late=True,
    reject_on_worker_lost=True,
)
def run_benchmark_batch(
    self,
    sample_ids: List[str],
    backends: Optional[List[str]] = None,
    force_reprocess: bool = False,
) -> Dict[str, Any]:
    """
    Führe Benchmarks für eine Batch von Samples durch.

    Args:
        sample_ids: Liste der Training Sample IDs
        backends: Optionale Liste der zu testenden Backends
        force_reprocess: Erzwinge Neuverarbeitung

    Returns:
        Benchmark-Ergebnis-Zusammenfassung
    """
    task_id = self.request.id

    logger.info(
        "benchmark_batch_starting",
        task_id=task_id,
        sample_count=len(sample_ids),
        backends=backends,
        force_reprocess=force_reprocess,
    )

    try:
        from app.services.benchmark_runner_service import get_benchmark_runner_service
        from app.db.session import get_async_session_context
        from app.db.schemas import BenchmarkRunRequest
        from uuid import UUID

        # Async Funktion für Benchmark
        async def run_benchmarks() -> Dict[str, Any]:
            async with get_async_session_context() as session:
                runner = get_benchmark_runner_service()
                # Konvertiere sample_ids zu UUIDs falls nötig
                uuid_sample_ids = [
                    UUID(sid) if isinstance(sid, str) else sid
                    for sid in sample_ids
                ]
                request = BenchmarkRunRequest(
                    sample_ids=uuid_sample_ids,
                    backends=backends or ["deepseek-janus-pro", "got-ocr-2.0", "surya-gpu", "surya"],
                    force_rerun=force_reprocess,
                )
                result = await runner.run_benchmark( request=request)
                return {
                    "success": result.success,
                    "samples_processed": result.samples_processed,
                    "samples_failed": result.samples_failed,
                    "backends_used": result.backends_used,
                    "total_time_ms": result.total_time_ms,
                }

        # Event Loop für async Ausführung - asyncio.run() für sauberes Cleanup
        result = asyncio.run(run_benchmarks())

        logger.info(
            "benchmark_batch_completed",
            task_id=task_id,
            samples_processed=result["samples_processed"],
            samples_failed=result["samples_failed"],
            backends=result["backends_used"],
            total_time_ms=result["total_time_ms"],
        )

        return result

    except Exception as e:
        logger.exception("benchmark_batch_failed", task_id=task_id, error=str(e))
        raise


@celery_app.task(
    bind=True,
    base=GPUTask,
    name="app.workers.tasks.training_tasks.run_scheduled_benchmarks",
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 2},
    retry_backoff=True,
    retry_backoff_max=1800,
    soft_time_limit=7200,  # 2 Stunden
    time_limit=7500,  # 2.5 Stunden
    acks_late=True,
    reject_on_worker_lost=True,
)
def run_scheduled_benchmarks(
    self,
    max_samples: int = 100,
    only_verified: bool = True,
) -> Dict[str, Any]:
    """
    Führe wöchentliche Benchmarks auf verifizierten Samples durch.

    Args:
        max_samples: Maximale Anzahl zu verarbeitender Samples
        only_verified: Nur verifizierte Samples benchmarken

    Returns:
        Benchmark-Ergebnis-Zusammenfassung
    """
    task_id = self.request.id

    logger.info(
        "scheduled_benchmarks_starting",
        task_id=task_id,
        max_samples=max_samples,
        only_verified=only_verified,
    )

    try:
        from app.services.ocr_training_service import get_ocr_training_service
        from app.services.benchmark_runner_service import get_benchmark_runner_service
        from app.db.session import get_async_session_context
        from app.db.schemas import BenchmarkRunRequest

        async def run_scheduled() -> Dict[str, Any]:
            async with get_async_session_context() as session:
                training_service = get_ocr_training_service()
                runner = get_benchmark_runner_service()

                # Hole Samples für Benchmarks
                samples, total_count = await training_service.list_training_samples(
                    db=session,
                    status="verified" if only_verified else None,
                    has_ground_truth=True,
                    limit=max_samples,
                )

                if not samples:
                    return {
                        "success": True,
                        "message": "Keine Samples für Benchmarks gefunden",
                        "samples_processed": 0,
                    }

                sample_ids = [s.id for s in samples]

                # Führe Benchmarks durch
                request = BenchmarkRunRequest(
                    sample_ids=sample_ids,
                    backends=["deepseek-janus-pro", "got-ocr-2.0", "surya-gpu", "surya"],
                    force_rerun=False,
                )
                result = await runner.run_benchmark(db=session, request=request)

                return {
                    "success": result.success,
                    "samples_processed": result.samples_processed,
                    "samples_failed": result.samples_failed,
                    "backends_used": result.backends_used,
                    "total_time_ms": result.total_time_ms,
                }

        # asyncio.run() für sauberes Event-Loop Cleanup
        result = asyncio.run(run_scheduled())

        logger.info(
            "scheduled_benchmarks_completed",
            task_id=task_id,
            samples_processed=result.get("samples_processed", 0),
        )

        return result

    except Exception as e:
        logger.exception("scheduled_benchmarks_failed", task_id=task_id, error=str(e))
        raise


# ==================== Statistics Tasks ====================

@celery_app.task(
    bind=True,
    base=CPUTask,
    name="app.workers.tasks.training_tasks.generate_daily_stats",
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 3},
    retry_backoff=True,
    retry_backoff_max=300,
    soft_time_limit=300,
    time_limit=360,
    acks_late=True,
    reject_on_worker_lost=True,
)
def generate_daily_stats(self) -> Dict[str, Any]:
    """
    Generiere tägliche Statistik-Aggregationen.

    Aggregiert:
    - Backend-Performance-Metriken
    - Korrektur-Statistiken
    - Sample-Verteilungen

    Returns:
        Statistik-Zusammenfassung
    """
    task_id = self.request.id

    logger.info("daily_stats_starting", task_id=task_id)

    try:
        from app.services.ocr_training_service import get_ocr_training_service
        from app.db.session import get_async_session_context
        from app.db.models import OCRBackendStatsDaily
        from sqlalchemy import select, func
        from datetime import date

        async def generate_stats() -> Dict[str, Any]:
            async with get_async_session_context() as session:
                training_service = get_ocr_training_service()

                # Hole Backend-Statistiken für heute
                today = date.today()
                backend_stats = await training_service.get_backend_stats( days=1)

                stats_created = 0

                for stats in backend_stats:
                    # Erstelle oder aktualisiere tägliche Statistik
                    existing = await session.execute(
                        select(OCRBackendStatsDaily).where(
                            OCRBackendStatsDaily.stat_date == today,
                            OCRBackendStatsDaily.backend_name == stats.backend_name,
                        )
                    )
                    existing_stat = existing.scalar_one_or_none()

                    if existing_stat:
                        # Update
                        existing_stat.samples_processed = stats.samples_processed
                        existing_stat.avg_cer = stats.avg_cer
                        existing_stat.avg_wer = stats.avg_wer
                        existing_stat.avg_umlaut_accuracy = stats.avg_umlaut_accuracy
                        existing_stat.avg_processing_time_ms = stats.avg_processing_time_ms
                    else:
                        # Create
                        new_stat = OCRBackendStatsDaily(
                            stat_date=today,
                            backend_name=stats.backend_name,
                            samples_processed=stats.samples_processed,
                            avg_cer=stats.avg_cer,
                            avg_wer=stats.avg_wer,
                            avg_umlaut_accuracy=stats.avg_umlaut_accuracy,
                            avg_processing_time_ms=stats.avg_processing_time_ms,
                            corrections_processed=0,
                        )
                        session.add(new_stat)
                        stats_created += 1

                await session.commit()

                # Hole Übersichtsstatistiken
                overview = await training_service.get_training_overview_stats(db=session)

                return {
                    "date": today.isoformat(),
                    "backends_updated": len(backend_stats),
                    "stats_created": stats_created,
                    "total_samples": overview.total_samples,
                    "verified_samples": overview.verified_samples,
                    "pending_annotations": overview.pending_annotations,
                }

        # asyncio.run() für sauberes Event-Loop Cleanup
        result = asyncio.run(generate_stats())

        logger.info(
            "daily_stats_completed",
            task_id=task_id,
            date=result["date"],
            backends_updated=result["backends_updated"],
        )

        return result

    except Exception as e:
        logger.exception("daily_stats_failed", task_id=task_id, error=str(e))
        raise


# ==================== Feedback Learning Tasks ====================

@celery_app.task(
    bind=True,
    base=CPUTask,
    name="app.workers.tasks.training_tasks.process_feedback_queue",
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 3},
    retry_backoff=True,
    retry_backoff_max=300,
    soft_time_limit=600,
    time_limit=720,
    acks_late=True,
    reject_on_worker_lost=True,
)
def process_feedback_queue(
    self,
    batch_size: int = 100,
) -> Dict[str, Any]:
    """
    Verarbeite ausstehende Korrekturen für Self-Learning.

    Args:
        batch_size: Maximale Anzahl zu verarbeitender Korrekturen

    Returns:
        Verarbeitungs-Zusammenfassung
    """
    task_id = self.request.id

    logger.info(
        "feedback_queue_processing_starting",
        task_id=task_id,
        batch_size=batch_size,
    )

    try:
        from app.services.feedback_learning_service import get_feedback_learning_service
        from app.db.session import get_async_session_context

        async def process_feedback() -> Dict[str, Any]:
            async with get_async_session_context() as session:
                feedback_service = get_feedback_learning_service()

                # Verarbeite unverarbeitete Korrekturen
                processed_count = await feedback_service.process_unprocessed_corrections(
                    db=session,
                    batch_size=batch_size
                )

                return {
                    "processed": processed_count,
                    "backends_updated": [],  # Wird später implementiert
                }

        # asyncio.run() für sauberes Event-Loop Cleanup
        result = asyncio.run(process_feedback())

        logger.info(
            "feedback_queue_processing_completed",
            task_id=task_id,
            processed=result.get("processed", 0),
            backends_updated=result.get("backends_updated", []),
        )

        return result

    except Exception as e:
        logger.exception("feedback_queue_processing_failed", task_id=task_id, error=str(e))
        raise


@celery_app.task(
    bind=True,
    base=CPUTask,
    name="app.workers.tasks.training_tasks.update_learned_weights",
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 3},
    retry_backoff=True,
    retry_backoff_max=300,
    soft_time_limit=300,
    time_limit=360,
    acks_late=True,
    reject_on_worker_lost=True,
)
def update_learned_weights(
    self,
    force_refresh: bool = False,
) -> Dict[str, Any]:
    """
    Aktualisiere gelernte Backend-Gewichte.

    Args:
        force_refresh: Erzwinge Neuberechnung

    Returns:
        Aktualisierte Gewichte
    """
    task_id = self.request.id

    logger.info(
        "update_learned_weights_starting",
        task_id=task_id,
        force_refresh=force_refresh,
    )

    try:
        from app.services.feedback_learning_service import get_feedback_learning_service
        from app.db.session import get_async_session_context

        async def update_weights() -> Dict[str, Any]:
            async with get_async_session_context() as session:
                feedback_service = get_feedback_learning_service()

                weights = await feedback_service.get_learned_weights(
                    
                    force_refresh=force_refresh
                )

                return {
                    "weights": weights.weights,
                    "last_updated": weights.last_updated.isoformat() if weights.last_updated else None,
                    "samples_analyzed": weights.samples_analyzed,
                    "confidence": weights.confidence,
                }

        # asyncio.run() für sauberes Event-Loop Cleanup
        result = asyncio.run(update_weights())

        logger.info(
            "update_learned_weights_completed",
            task_id=task_id,
            weights=result["weights"],
            samples_analyzed=result["samples_analyzed"],
        )

        return result

    except Exception as e:
        logger.exception("update_learned_weights_failed", task_id=task_id, error=str(e))
        raise


# ==================== Batch Processing Tasks ====================

@celery_app.task(
    bind=True,
    base=CPUTask,
    name="app.workers.tasks.training_tasks.populate_training_batch",
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 3},
    retry_backoff=True,
    retry_backoff_max=300,
    soft_time_limit=300,
    time_limit=360,
    acks_late=True,
    reject_on_worker_lost=True,
)
def populate_training_batch(
    self,
    batch_id: str,
) -> Dict[str, Any]:
    """
    Befülle einen Training-Batch mit stratifizierten Samples.

    Args:
        batch_id: Batch-ID

    Returns:
        Befüllungs-Ergebnis
    """
    task_id = self.request.id

    logger.info(
        "populate_batch_starting",
        task_id=task_id,
        batch_id=batch_id,
    )

    try:
        from app.services.ocr_training_service import get_ocr_training_service
        from app.db.session import get_async_session_context
        from app.db.models import OCRTrainingBatch, OCRTrainingBatchItem, OCRTrainingSample
        from sqlalchemy import select, func
        import random

        async def populate() -> Dict[str, Any]:
            async with get_async_session_context() as session:
                # Hole Batch
                result = await session.execute(
                    select(OCRTrainingBatch).where(OCRTrainingBatch.id == batch_id)
                )
                batch = result.scalar_one_or_none()

                if not batch:
                    return {"error": f"Batch {batch_id} nicht gefunden"}

                if batch.status != "draft":
                    return {"error": f"Batch hat falschen Status: {batch.status}"}

                config = batch.stratification_config or {}
                target_size = batch.target_size

                # Baue Query basierend auf Stratifizierung
                query = select(OCRTrainingSample).where(
                    OCRTrainingSample.status.in_(["verified", "annotated"])
                )

                if config.get("languages"):
                    query = query.where(
                        OCRTrainingSample.language.in_(config["languages"])
                    )

                if config.get("document_types"):
                    query = query.where(
                        OCRTrainingSample.document_type.in_(config["document_types"])
                    )

                if config.get("require_umlauts"):
                    query = query.where(OCRTrainingSample.has_umlauts == True)

                if config.get("require_tables"):
                    query = query.where(OCRTrainingSample.has_tables == True)

                # Hole alle passenden Samples
                result = await session.execute(query)
                all_samples = list(result.scalars().all())

                if not all_samples:
                    return {
                        "error": "Keine passenden Samples gefunden",
                        "batch_id": batch_id,
                    }

                # Zufällige Auswahl
                selected_samples = random.sample(
                    all_samples,
                    min(target_size, len(all_samples))
                )

                # Erstelle Batch-Items
                for i, sample in enumerate(selected_samples):
                    item = OCRTrainingBatchItem(
                        batch_id=batch.id,
                        training_sample_id=sample.id,
                        sequence_number=i + 1,
                        status="pending",
                    )
                    session.add(item)

                # Aktualisiere Batch
                batch.actual_size = len(selected_samples)
                batch.items_pending = len(selected_samples)
                batch.status = "ready"

                await session.commit()

                return {
                    "batch_id": batch_id,
                    "samples_added": len(selected_samples),
                    "status": "ready",
                }

        # asyncio.run() für sauberes Event-Loop Cleanup
        result = asyncio.run(populate())

        logger.info(
            "populate_batch_completed",
            task_id=task_id,
            batch_id=batch_id,
            samples_added=result.get("samples_added", 0),
        )

        return result

    except Exception as e:
        logger.exception("populate_batch_failed", task_id=task_id, error=str(e))
        raise


@celery_app.task(
    bind=True,
    base=CPUTask,
    name="app.workers.tasks.training_tasks.generate_training_report",
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 3},
    retry_backoff=True,
    retry_backoff_max=300,
    soft_time_limit=300,
    time_limit=360,
    acks_late=True,
    reject_on_worker_lost=True,
)
def generate_training_report(self) -> Dict[str, Any]:
    """
    Generiere umfassenden Training-Status-Report.

    Enthält:
    - Sample-Statistiken
    - Backend-Vergleich
    - Trend-Daten
    - Empfehlungen

    Returns:
        Vollständiger Training-Report
    """
    task_id = self.request.id

    logger.info("training_report_starting", task_id=task_id)

    try:
        from app.services.ocr_training_service import get_ocr_training_service
        from app.services.feedback_learning_service import get_feedback_learning_service
        from app.services.benchmark_runner_service import get_benchmark_runner_service
        from app.db.session import get_async_session_context

        async def generate_report() -> Dict[str, Any]:
            async with get_async_session_context() as session:
                training_service = get_ocr_training_service()
                feedback_service = get_feedback_learning_service()
                benchmark_runner = get_benchmark_runner_service()

                # Sammle alle Statistiken
                overview = await training_service.get_training_overview_stats(db=session)
                backend_stats = await training_service.get_backend_stats( days=30)
                comparison = await benchmark_runner.get_backend_comparison(db=session)
                learned_weights = await feedback_service.get_learned_weights(db=session)

                # Generiere Empfehlungen
                recommendations = []

                if overview.pending_annotations > 50:
                    recommendations.append(
                        f"⚠️ {overview.pending_annotations} Samples warten auf Annotation"
                    )

                if overview.unprocessed_corrections > 20:
                    recommendations.append(
                        f"📝 {overview.unprocessed_corrections} Korrekturen noch unverarbeitet"
                    )

                if learned_weights.confidence < 0.5:
                    recommendations.append(
                        "📊 Mehr Daten für zuverlässige Backend-Gewichtung erforderlich"
                    )

                return {
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                    "overview": {
                        "total_samples": overview.total_samples,
                        "verified_samples": overview.verified_samples,
                        "pending_annotations": overview.pending_annotations,
                        "active_batches": overview.active_batches,
                        "recent_corrections_24h": overview.recent_corrections_24h,
                    },
                    "backend_comparison": {
                        "best_backend": comparison.best_backend,
                        "sample_count": comparison.sample_count,
                        "backends": {
                            name: {
                                "samples_processed": data.samples_processed,
                                "avg_cer": data.avg_cer,
                                "avg_wer": data.avg_wer,
                                "avg_umlaut_accuracy": data.avg_umlaut_accuracy,
                            }
                            for name, data in comparison.backends.items()
                        },
                    },
                    "learned_weights": {
                        "weights": learned_weights.weights,
                        "confidence": learned_weights.confidence,
                        "samples_analyzed": learned_weights.samples_analyzed,
                    },
                    "recommendations": recommendations,
                }

        # asyncio.run() für sauberes Event-Loop Cleanup
        result = asyncio.run(generate_report())

        logger.info(
            "training_report_completed",
            task_id=task_id,
            total_samples=result["overview"]["total_samples"],
            best_backend=result["backend_comparison"]["best_backend"],
        )

        return result

    except Exception as e:
        logger.exception("training_report_failed", task_id=task_id, error=str(e))
        raise


# ==================== Celery Beat Schedule ====================

# Diese Tasks sollten in der Celery Beat Konfiguration hinzugefügt werden
CELERY_BEAT_TRAINING_SCHEDULE = {
    "training-daily-stats": {
        "task": "app.workers.tasks.training_tasks.generate_daily_stats",
        "schedule": 86400.0,  # Täglich
        "options": {"queue": "default"},
    },
    "training-feedback-queue-hourly": {
        "task": "app.workers.tasks.training_tasks.process_feedback_queue",
        "schedule": 3600.0,  # Stündlich
        "options": {"queue": "default"},
    },
    "training-learned-weights-daily": {
        "task": "app.workers.tasks.training_tasks.update_learned_weights",
        "schedule": 86400.0,  # Täglich
        "options": {"queue": "default"},
    },
    "training-weekly-benchmarks": {
        "task": "app.workers.tasks.training_tasks.run_scheduled_benchmarks",
        "schedule": 604800.0,  # Wöchentlich (Sonntag 03:00)
        "options": {"queue": "gpu"},
    },
    "training-report-weekly": {
        "task": "app.workers.tasks.training_tasks.generate_training_report",
        "schedule": 604800.0,  # Wöchentlich
        "options": {"queue": "default"},
    },
}


# ==================== Bulk OCR Processing Tasks ====================

@celery_app.task(
    bind=True,
    base=GPUTask,
    name="app.workers.tasks.training_tasks.run_bulk_processing_job",
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 2},
    retry_backoff=True,
    retry_backoff_max=1800,
    soft_time_limit=86400,  # 24 Stunden
    time_limit=90000,  # 25 Stunden
    acks_late=True,
    reject_on_worker_lost=True,
)
def run_bulk_processing_job(
    self,
    job_id: str,
    resume_from_checkpoint: bool = False,
) -> Dict[str, Any]:
    """
    Fuehre Bulk OCR Processing Job aus.

    Verarbeitet alle Trainings-Dokumente durch alle OCR-Backends.
    Laeuft typischerweise ueber Nacht (geschaetzte Zeit: 32 Stunden).

    Args:
        job_id: Bulk Processing Job ID
        resume_from_checkpoint: Bei True wird vom letzten Checkpoint fortgesetzt

    Returns:
        Job-Ergebnis-Zusammenfassung
    """
    task_id = self.request.id

    logger.info(
        "bulk_processing_job_starting",
        task_id=task_id,
        job_id=job_id,
        resume=resume_from_checkpoint,
    )

    try:
        from app.services.bulk_ocr_processing_service import (
            get_bulk_ocr_processing_service_sync,
            get_bulk_ocr_processing_service,
            BulkProcessingJob,
            _active_jobs,
        )
        from app.db.session import get_async_session_context
        from uuid import UUID

        async def run_job() -> Dict[str, Any]:
            async with get_async_session_context() as session:
                # Load job from DB first
                db_service = await get_bulk_ocr_processing_service(session)
                db_job = await db_service.get_job(UUID(job_id))
                if not db_job:
                    raise ValueError(f"Job {job_id} nicht gefunden in der Datenbank")

                # Register job in in-memory store for processing
                from app.services.bulk_ocr_processing_service import BulkJobStatus
                backends_list = db_job.backends or ["deepseek", "got_ocr", "surya_gpu", "surya_cpu"]
                mem_job = BulkProcessingJob(
                    id=str(db_job.id),
                    name=db_job.name,
                    status=BulkJobStatus.PENDING,
                    backends=backends_list,
                    total_documents=db_job.total_documents,
                    processed_documents=0,
                    failed_documents=0,
                    current_backend=None,
                    current_backend_index=0,
                    current_document_index=0,
                    documents_per_backend={b: 0 for b in backends_list},
                    started_at=None,
                    completed_at=None,
                    paused_at=None,
                    last_checkpoint_at=None,
                    configuration=db_job.configuration or {},
                )
                _active_jobs[str(db_job.id)] = mem_job

                # Process using in-memory service
                service = get_bulk_ocr_processing_service_sync()
                processed_job = await service.process_all_documents(
                    db=session,
                    job_id=job_id,
                )

                # Update DB job status
                await db_service.update_job_status(
                    UUID(job_id),
                    processed_job.status.value if hasattr(processed_job.status, 'value') else processed_job.status,
                )

                return processed_job.to_dict()

        # asyncio.run() für sauberes Event-Loop Cleanup
        result = asyncio.run(run_job())

        logger.info(
            "bulk_processing_job_completed",
            task_id=task_id,
            job_id=job_id,
            status=result["status"],
            processed=result["processed_documents"],
            failed=result["failed_documents"],
        )

        return result

    except Exception as e:
        logger.exception(
            "bulk_processing_job_failed",
            task_id=task_id,
            job_id=job_id,
            error=str(e),
        )
        raise


@celery_app.task(
    bind=True,
    base=CPUTask,  # KEIN GPU-Lock für CPU-only Backends!
    name="app.workers.tasks.training_tasks.run_bulk_processing_job_cpu",
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 2},
    retry_backoff=True,
    retry_backoff_max=1800,
    soft_time_limit=86400,  # 24 Stunden
    time_limit=90000,  # 25 Stunden
    acks_late=True,
    reject_on_worker_lost=True,
)
def run_bulk_processing_job_cpu(
    self,
    job_id: str,
    resume_from_checkpoint: bool = False,
) -> Dict[str, Any]:
    """
    Fuehre Bulk OCR Processing Job aus - CPU-only Version.

    Identisch zu run_bulk_processing_job, aber ohne GPU-Lock.
    Fuer CPU-only Backends wie 'surya' (ohne GPU).

    Args:
        job_id: Bulk Processing Job ID
        resume_from_checkpoint: Bei True wird vom letzten Checkpoint fortgesetzt

    Returns:
        Job-Ergebnis-Zusammenfassung
    """
    task_id = self.request.id

    logger.info(
        "bulk_processing_job_cpu_starting",
        task_id=task_id,
        job_id=job_id,
        resume=resume_from_checkpoint,
    )

    try:
        from app.services.bulk_ocr_processing_service import (
            get_bulk_ocr_processing_service_sync,
            get_bulk_ocr_processing_service,
            BulkProcessingJob,
            _active_jobs,
        )
        from app.db.session import get_async_session_context
        from uuid import UUID

        async def run_job() -> Dict[str, Any]:
            async with get_async_session_context() as session:
                # Load job from DB first
                db_service = await get_bulk_ocr_processing_service(session)
                db_job = await db_service.get_job(UUID(job_id))
                if not db_job:
                    raise ValueError(f"Job {job_id} nicht gefunden in der Datenbank")

                # Register job in in-memory store for processing
                from app.services.bulk_ocr_processing_service import BulkJobStatus
                backends_list = db_job.backends or ["surya_cpu"]  # Default: nur CPU
                mem_job = BulkProcessingJob(
                    id=str(db_job.id),
                    name=db_job.name,
                    status=BulkJobStatus.PENDING,
                    backends=backends_list,
                    total_documents=db_job.total_documents,
                    processed_documents=0,
                    failed_documents=0,
                    current_backend=None,
                    current_backend_index=0,
                    current_document_index=0,
                    documents_per_backend={b: 0 for b in backends_list},
                    started_at=None,
                    completed_at=None,
                    paused_at=None,
                    last_checkpoint_at=None,
                    configuration=db_job.configuration or {},
                )
                _active_jobs[str(db_job.id)] = mem_job

                # Process using in-memory service
                service = get_bulk_ocr_processing_service_sync()
                processed_job = await service.process_all_documents(
                    db=session,
                    job_id=job_id,
                )

                # Update DB job status
                await db_service.update_job_status(
                    UUID(job_id),
                    processed_job.status.value if hasattr(processed_job.status, 'value') else processed_job.status,
                )

                return processed_job.to_dict()

        # asyncio.run() für sauberes Event-Loop Cleanup
        result = asyncio.run(run_job())

        logger.info(
            "bulk_processing_job_cpu_completed",
            task_id=task_id,
            job_id=job_id,
            status=result["status"],
            processed=result["processed_documents"],
            failed=result["failed_documents"],
        )

        return result

    except Exception as e:
        logger.exception(
            "bulk_processing_job_cpu_failed",
            task_id=task_id,
            job_id=job_id,
            error=str(e),
        )
        raise


@celery_app.task(
    bind=True,
    base=CPUTask,
    name="app.workers.tasks.training_tasks.import_training_files",
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 3},
    retry_backoff=True,
    retry_backoff_max=300,
    soft_time_limit=1800,  # 30 Minuten
    time_limit=2100,
    acks_late=True,
    reject_on_worker_lost=True,
)
def import_training_files(
    self,
    source_directory: str,
    file_patterns: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Importiere Trainings-Dateien aus einem Verzeichnis.

    Scannt das angegebene Verzeichnis nach Dokumenten (PDF, TIF, PNG, etc.)
    und erstellt Training Samples in der Datenbank.

    Args:
        source_directory: Quellverzeichnis (z.B. "Trainings_Data")
        file_patterns: Datei-Muster (default: ["*.pdf", "*.tif", ...])

    Returns:
        Import-Statistiken
    """
    task_id = self.request.id

    logger.info(
        "import_training_files_starting",
        task_id=task_id,
        source_directory=source_directory,
    )

    try:
        from app.services.bulk_ocr_processing_service import get_bulk_ocr_processing_service
        from app.db.session import get_async_session_context

        async def import_files() -> Dict[str, Any]:
            async with get_async_session_context() as session:
                service = await get_bulk_ocr_processing_service(session)
                result = await service.import_training_files(
                    
                    source_directory=source_directory,
                    file_patterns=file_patterns,
                )
                return result

        # asyncio.run() für sauberes Event-Loop Cleanup
        result = asyncio.run(import_files())

        logger.info(
            "import_training_files_completed",
            task_id=task_id,
            imported=result["imported"],
            skipped=result["skipped"],
            errors=result["errors"],
        )

        return result

    except Exception as e:
        logger.exception(
            "import_training_files_failed",
            task_id=task_id,
            error=str(e),
        )
        raise


@celery_app.task(
    bind=True,
    base=GPUTask,
    name="app.workers.tasks.training_tasks.process_document_batch",
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 3},
    retry_backoff=True,
    retry_backoff_max=600,
    soft_time_limit=3600,  # 1 Stunde
    time_limit=4200,
    acks_late=True,
    reject_on_worker_lost=True,
)
def process_document_batch(
    self,
    sample_ids: List[str],
    backend_name: str,
    job_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Verarbeite einen Batch von Dokumenten durch ein spezifisches Backend.

    Args:
        sample_ids: Liste der Training Sample IDs
        backend_name: OCR Backend Name
        job_id: Optionale Bulk Job ID fuer Tracking

    Returns:
        Batch-Verarbeitungsergebnis
    """
    task_id = self.request.id

    logger.info(
        "process_document_batch_starting",
        task_id=task_id,
        sample_count=len(sample_ids),
        backend=backend_name,
        job_id=job_id,
    )

    try:
        from app.services.benchmark_runner_service import get_benchmark_runner_service
        from app.db.session import get_async_session_context
        from app.db.models import OCRTrainingSample, OCRDocumentOutput
        from sqlalchemy import select
        from uuid import UUID

        async def process_batch() -> Dict[str, Any]:
            async with get_async_session_context() as session:
                runner = get_benchmark_runner_service()
                await runner._ensure_agents()

                # Lade Samples
                uuid_ids = [UUID(sid) for sid in sample_ids]
                result = await session.execute(
                    select(OCRTrainingSample).where(
                        OCRTrainingSample.id.in_(uuid_ids)
                    )
                )
                samples = list(result.scalars().all())

                processed = 0
                failed = 0
                results = []

                for sample in samples:
                    try:
                        benchmark_result = await runner._run_single_benchmark(
                            sample=sample,
                            backend_name=backend_name,
                        )

                        # Speichere Output
                        output = OCRDocumentOutput(
                            training_sample_id=sample.id,
                            bulk_job_id=UUID(job_id) if job_id else None,
                            backend_name=backend_name,
                            raw_text=benchmark_result.raw_text,
                            confidence_score=benchmark_result.confidence,
                            processing_time_ms=benchmark_result.processing_time_ms,
                            gpu_memory_mb=benchmark_result.gpu_memory_mb,
                            success=benchmark_result.success,
                            error_message=benchmark_result.error,
                        )
                        session.add(output)

                        if benchmark_result.success:
                            processed += 1
                        else:
                            failed += 1

                        results.append({
                            "sample_id": str(sample.id),
                            "success": benchmark_result.success,
                            "processing_time_ms": benchmark_result.processing_time_ms,
                        })

                    except Exception as e:
                        failed += 1
                        results.append({
                            "sample_id": str(sample.id),
                            "success": False,
                            "error": str(e),
                        })

                await session.commit()

                return {
                    "backend": backend_name,
                    "total": len(samples),
                    "processed": processed,
                    "failed": failed,
                    "results": results,
                }

        # asyncio.run() für sauberes Event-Loop Cleanup
        result = asyncio.run(process_batch())

        logger.info(
            "process_document_batch_completed",
            task_id=task_id,
            backend=backend_name,
            processed=result["processed"],
            failed=result["failed"],
        )

        return result

    except Exception as e:
        logger.exception(
            "process_document_batch_failed",
            task_id=task_id,
            backend=backend_name,
            error=str(e),
        )
        raise


@celery_app.task(
    bind=True,
    base=CPUTask,
    name="app.workers.tasks.training_tasks.create_quality_snapshot",
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 3},
    retry_backoff=True,
    soft_time_limit=300,
    time_limit=360,
    acks_late=True,
)
def create_quality_snapshot(
    self,
    backend_name: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Erstelle Quality Snapshot fuer Monitoring.

    Args:
        backend_name: Optionaler Backend-Name (default: alle Backends)

    Returns:
        Snapshot-Daten
    """
    task_id = self.request.id

    logger.info(
        "create_quality_snapshot_starting",
        task_id=task_id,
        backend=backend_name,
    )

    try:
        from app.db.session import get_async_session_context
        from app.db.models import (
            OCRBackendBenchmark,
            OCRValidationCorrection,
            OCRQualitySnapshot,
        )
        from sqlalchemy import select, func, and_
        from datetime import datetime, timezone, timedelta

        async def create_snapshot() -> Dict[str, Any]:
            async with get_async_session_context() as session:
                backends = [backend_name] if backend_name else [
                    "deepseek-janus-pro", "got-ocr-2.0", "surya-gpu", "surya"
                ]

                snapshots_created = []
                now = datetime.now(timezone.utc)
                one_hour_ago = now - timedelta(hours=1)

                for backend in backends:
                    # Aggregiere Metriken
                    result = await session.execute(
                        select(
                            func.count(OCRBackendBenchmark.id).label("count"),
                            func.avg(OCRBackendBenchmark.cer).label("avg_cer"),
                            func.avg(OCRBackendBenchmark.wer).label("avg_wer"),
                            func.avg(OCRBackendBenchmark.umlaut_accuracy).label("avg_umlaut"),
                            func.avg(OCRBackendBenchmark.processing_time_ms).label("avg_time"),
                        ).where(
                            and_(
                                OCRBackendBenchmark.backend_name == backend,
                                OCRBackendBenchmark.processed_at >= one_hour_ago,
                            )
                        )
                    )
                    row = result.first()

                    # Zaehle Korrekturen
                    correction_result = await session.execute(
                        select(func.count(OCRValidationCorrection.id)).where(
                            and_(
                                OCRValidationCorrection.backend_used == backend,
                                OCRValidationCorrection.created_at >= one_hour_ago,
                            )
                        )
                    )
                    correction_count = correction_result.scalar() or 0

                    # Erstelle Snapshot
                    snapshot = OCRQualitySnapshot(
                        backend_name=backend,
                        sample_count=row.count or 0,
                        avg_cer=row.avg_cer,
                        avg_wer=row.avg_wer,
                        avg_umlaut_accuracy=row.avg_umlaut,
                        avg_processing_time_ms=row.avg_time,
                        correction_count=correction_count,
                    )

                    # Check Alerts
                    if row.avg_cer and row.avg_cer > 0.10:
                        snapshot.alert_triggered = True
                        snapshot.alert_reason = f"CER zu hoch: {row.avg_cer:.2%}"
                    elif row.avg_umlaut and row.avg_umlaut < 0.95:
                        snapshot.alert_triggered = True
                        snapshot.alert_reason = f"Umlaut-Genauigkeit zu niedrig: {row.avg_umlaut:.1%}"

                    session.add(snapshot)
                    snapshots_created.append({
                        "backend": backend,
                        "sample_count": row.count or 0,
                        "avg_cer": row.avg_cer,
                        "alert": snapshot.alert_triggered,
                    })

                await session.commit()

                return {
                    "snapshots_created": len(snapshots_created),
                    "snapshots": snapshots_created,
                }

        # asyncio.run() für sauberes Event-Loop Cleanup
        result = asyncio.run(create_snapshot())

        logger.info(
            "create_quality_snapshot_completed",
            task_id=task_id,
            snapshots_created=result["snapshots_created"],
        )

        return result

    except Exception as e:
        logger.exception(
            "create_quality_snapshot_failed",
            task_id=task_id,
            error=str(e),
        )
        raise


# ==================== Fine-Tuning Tasks ====================

@celery_app.task(
    bind=True,
    base=GPUTask,
    name="app.workers.tasks.training_tasks.run_deepseek_lora_training",
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 1},
    retry_backoff=True,
    soft_time_limit=86400,  # 24 Stunden
    time_limit=90000,
    acks_late=True,
    reject_on_worker_lost=True,
)
def run_deepseek_lora_training(
    self,
    train_data_path: str,
    validation_data_path: Optional[str] = None,
    output_version: Optional[str] = None,
    config_overrides: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Führe DeepSeek-Janus-Pro LoRA Fine-Tuning durch.

    Args:
        train_data_path: Pfad zu train.jsonl
        validation_data_path: Pfad zu val.jsonl
        output_version: Optionale Version (auto-generiert wenn None)
        config_overrides: Optionale Konfigurationsüberschreibungen

    Returns:
        Training-Ergebnis mit Metriken
    """
    task_id = self.request.id

    logger.info(
        "deepseek_lora_training_starting",
        task_id=task_id,
        train_data=train_data_path,
        validation_data=validation_data_path,
    )

    try:
        from app.ml.finetuning.deepseek_lora_trainer import (
            DeepSeekLoRATrainer,
            LoRAConfig,
            TrainingConfig,
        )
        from app.ml.finetuning.checkpoint_manager import CheckpointManager

        # Konfiguration erstellen
        lora_config = LoRAConfig()
        training_config = TrainingConfig()

        if config_overrides:
            for key, value in config_overrides.items():
                if hasattr(training_config, key):
                    setattr(training_config, key, value)
                elif hasattr(lora_config, key):
                    setattr(lora_config, key, value)

        # Trainer initialisieren und ausführen
        trainer = DeepSeekLoRATrainer(
            lora_config=lora_config,
            training_config=training_config
        )

        async def run_training():
            return await trainer.train(
                train_data_path=train_data_path,
                validation_data_path=validation_data_path
            )

        # asyncio.run() für sauberes Event-Loop Cleanup
        result = asyncio.run(run_training())

        # Checkpoint registrieren
        if result.get("status") == "completed":
            checkpoint_manager = CheckpointManager()
            version = checkpoint_manager.create_version(
                model_name="deepseek",
                source_path=result["output_dir"],
                metrics={
                    "final_loss": result.get("final_loss"),
                    "best_validation_loss": result.get("best_validation_loss"),
                },
                training_config=config_overrides or {},
                notes=f"Celery Task {task_id}"
            )
            result["registered_version"] = version

        logger.info(
            "deepseek_lora_training_completed",
            task_id=task_id,
            status=result.get("status"),
            total_steps=result.get("total_steps"),
        )

        return result

    except Exception as e:
        logger.exception(
            "deepseek_lora_training_failed",
            task_id=task_id,
            error=str(e),
        )
        raise


@celery_app.task(
    bind=True,
    base=GPUTask,
    name="app.workers.tasks.training_tasks.run_surya_hf_training",
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 1},
    retry_backoff=True,
    soft_time_limit=86400,  # 24 Stunden
    time_limit=90000,
    acks_late=True,
    reject_on_worker_lost=True,
)
def run_surya_hf_training(
    self,
    train_data_path: str,
    test_data_path: Optional[str] = None,
    output_version: Optional[str] = None,
    config_overrides: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Führe Surya-OCR HuggingFace Training durch.

    Args:
        train_data_path: Pfad zu train.jsonl
        test_data_path: Pfad zu test.jsonl
        output_version: Optionale Version
        config_overrides: Optionale Konfigurationsüberschreibungen

    Returns:
        Training-Ergebnis mit Metriken
    """
    task_id = self.request.id

    logger.info(
        "surya_hf_training_starting",
        task_id=task_id,
        train_data=train_data_path,
        test_data=test_data_path,
    )

    try:
        from app.ml.finetuning.surya_hf_trainer import (
            SuryaOCRTrainer,
            SuryaTrainingConfig,
        )
        from app.ml.finetuning.checkpoint_manager import CheckpointManager

        # Konfiguration erstellen
        config = SuryaTrainingConfig()

        if config_overrides:
            for key, value in config_overrides.items():
                if hasattr(config, key):
                    setattr(config, key, value)

        # Trainer initialisieren und ausführen
        trainer = SuryaOCRTrainer(config=config)

        async def run_training():
            return await trainer.train(
                train_data_path=train_data_path,
                test_data_path=test_data_path
            )

        # asyncio.run() für sauberes Event-Loop Cleanup
        result = asyncio.run(run_training())

        # Checkpoint registrieren
        if result.get("status") == "completed":
            checkpoint_manager = CheckpointManager()
            version = checkpoint_manager.create_version(
                model_name="surya",
                source_path=result["output_dir"],
                metrics={
                    "train_loss": result.get("train_loss"),
                },
                training_config=config_overrides or {},
                notes=f"Celery Task {task_id}"
            )
            result["registered_version"] = version

        logger.info(
            "surya_hf_training_completed",
            task_id=task_id,
            status=result.get("status"),
        )

        return result

    except Exception as e:
        logger.exception(
            "surya_hf_training_failed",
            task_id=task_id,
            error=str(e),
        )
        raise


@celery_app.task(
    bind=True,
    base=CPUTask,
    name="app.workers.tasks.training_tasks.check_retraining_conditions",
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 3},
    retry_backoff=True,
    soft_time_limit=300,
    time_limit=360,
    acks_late=True,
)
def check_retraining_conditions(self) -> Dict[str, Any]:
    """
    Prüfe ob Retraining-Bedingungen erfüllt sind.

    Wird täglich ausgeführt und prüft:
    - Anzahl neuer Korrekturen
    - Qualitätsverschlechterung
    - Umlaut-Accuracy-Probleme

    Returns:
        Empfehlung mit Dringlichkeit
    """
    task_id = self.request.id

    logger.info("check_retraining_conditions_starting", task_id=task_id)

    try:
        from app.services.quality_monitoring_service import get_quality_monitoring_service
        from app.db.session import get_async_session_context

        async def check_conditions():
            async with get_async_session_context() as session:
                service = await get_quality_monitoring_service(session)
                recommendation = await service.get_retraining_recommendation()

                return {
                    "should_retrain": recommendation.should_retrain,
                    "urgency": recommendation.urgency,
                    "reasons": recommendation.reasons,
                    "focus_areas": recommendation.focus_areas,
                    "estimated_samples_needed": recommendation.estimated_samples_needed,
                }

        # asyncio.run() für sauberes Event-Loop Cleanup
        result = asyncio.run(check_conditions())

        logger.info(
            "check_retraining_conditions_completed",
            task_id=task_id,
            should_retrain=result["should_retrain"],
            urgency=result["urgency"],
        )

        return result

    except Exception as e:
        logger.exception(
            "check_retraining_conditions_failed",
            task_id=task_id,
            error=str(e),
        )
        raise


@celery_app.task(
    bind=True,
    base=CPUTask,
    name="app.workers.tasks.training_tasks.run_quality_monitoring",
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 3},
    retry_backoff=True,
    soft_time_limit=300,
    time_limit=360,
    acks_late=True,
)
def run_quality_monitoring(self) -> Dict[str, Any]:
    """
    Führe Qualitätsmonitoring durch und generiere Alerts.

    Wird stündlich ausgeführt.

    Returns:
        Monitoring-Ergebnis mit Alerts
    """
    task_id = self.request.id

    logger.info("run_quality_monitoring_starting", task_id=task_id)

    try:
        from app.services.quality_monitoring_service import get_quality_monitoring_service
        from app.db.session import get_async_session_context

        async def run_monitoring():
            async with get_async_session_context() as session:
                service = await get_quality_monitoring_service(session)
                alerts = await service.run_quality_check()

                return {
                    "alerts_count": len(alerts),
                    "critical_alerts": sum(1 for a in alerts if a.severity.value == "critical"),
                    "warning_alerts": sum(1 for a in alerts if a.severity.value == "warning"),
                    "alerts": [
                        {
                            "type": a.alert_type.value,
                            "severity": a.severity.value,
                            "message": a.message,
                            "affected_backend": a.affected_backend,
                        }
                        for a in alerts
                    ]
                }

        # asyncio.run() für sauberes Event-Loop Cleanup
        result = asyncio.run(run_monitoring())

        logger.info(
            "run_quality_monitoring_completed",
            task_id=task_id,
            alerts_count=result["alerts_count"],
            critical=result["critical_alerts"],
        )

        return result

    except Exception as e:
        logger.exception(
            "run_quality_monitoring_failed",
            task_id=task_id,
            error=str(e),
        )
        raise


# Erweitere Beat Schedule mit Bulk Processing und Fine-Tuning Tasks
CELERY_BEAT_TRAINING_SCHEDULE.update({
    "quality-snapshot-hourly": {
        "task": "app.workers.tasks.training_tasks.create_quality_snapshot",
        "schedule": 3600.0,  # Stündlich
        "options": {"queue": "default"},
    },
    "quality-monitoring-hourly": {
        "task": "app.workers.tasks.training_tasks.run_quality_monitoring",
        "schedule": 3600.0,  # Stündlich
        "options": {"queue": "default"},
    },
    "check-retraining-conditions-daily": {
        "task": "app.workers.tasks.training_tasks.check_retraining_conditions",
        "schedule": 86400.0,  # Täglich um 02:00
        "options": {"queue": "default"},
    },
})
