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
                result = await runner.run_benchmark(db=session, request=request)
                return {
                    "success": result.success,
                    "samples_processed": result.samples_processed,
                    "samples_failed": result.samples_failed,
                    "backends_used": result.backends_used,
                    "total_time_ms": result.total_time_ms,
                }

        # Event Loop für async Ausführung
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        result = loop.run_until_complete(run_benchmarks())

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

        loop = asyncio.get_event_loop()
        if loop.is_closed():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        result = loop.run_until_complete(run_scheduled())

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
                backend_stats = await training_service.get_backend_stats(db=session, days=1)

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

        loop = asyncio.get_event_loop()
        if loop.is_closed():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        result = loop.run_until_complete(generate_stats())

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

        loop = asyncio.get_event_loop()
        if loop.is_closed():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        result = loop.run_until_complete(process_feedback())

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
                    db=session,
                    force_refresh=force_refresh
                )

                return {
                    "weights": weights.weights,
                    "last_updated": weights.last_updated.isoformat() if weights.last_updated else None,
                    "samples_analyzed": weights.samples_analyzed,
                    "confidence": weights.confidence,
                }

        loop = asyncio.get_event_loop()
        if loop.is_closed():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        result = loop.run_until_complete(update_weights())

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

        loop = asyncio.get_event_loop()
        if loop.is_closed():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        result = loop.run_until_complete(populate())

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
                backend_stats = await training_service.get_backend_stats(db=session, days=30)
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

        loop = asyncio.get_event_loop()
        if loop.is_closed():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        result = loop.run_until_complete(generate_report())

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
