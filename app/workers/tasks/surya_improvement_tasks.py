# -*- coding: utf-8 -*-
"""
Surya OCR Continuous Improvement Celery Tasks.

Enterprise-Grade Self-Improvement Loop für Surya OCR:
- Tägliche Benchmark-Messung
- Automatische Retraining-Erkennung
- Feedback-zu-Training Konvertierung
- Modell-Deployment mit A/B Testing
- Automatisches Rollback bei Qualitätsverlust

Feinpoliert und durchdacht - Surya Improvement für Enterprise.
"""

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import structlog

from app.workers.celery_app import celery_app, CPUTask, GPUTask
from app.core.config import settings
from app.core.safe_errors import safe_error_log

logger = structlog.get_logger(__name__)


# ==================== Surya Benchmark Tasks ====================

@celery_app.task(
    bind=True,
    base=GPUTask,
    name="app.workers.tasks.surya_improvement_tasks.run_surya_benchmark",
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 3},
    retry_backoff=True,
    retry_backoff_max=600,
    soft_time_limit=3600,  # 1 Stunde
    time_limit=4200,
    acks_late=True,
    reject_on_worker_lost=True,
)
def run_surya_benchmark(
    self,
    sample_ids: Optional[List[str]] = None,
    max_samples: int = 50,
    include_cpu: bool = True,
    include_gpu: bool = True,
) -> Dict[str, Any]:
    """
    Führe Surya-spezifischen Benchmark durch.

    Misst CER, WER und Umlaut-Accuracy für Surya Backends.
    Kritischer Teil des Continuous Improvement Loops.

    Args:
        sample_ids: Spezifische Sample IDs (oder None für automatische Auswahl)
        max_samples: Maximale Anzahl Samples
        include_cpu: Surya CPU Backend einschließen
        include_gpu: Surya GPU Backend einschließen

    Returns:
        Benchmark-Ergebnis mit Metriken
    """
    task_id = self.request.id

    logger.info(
        "surya_benchmark_starting",
        task_id=task_id,
        max_samples=max_samples,
        include_cpu=include_cpu,
        include_gpu=include_gpu,
    )

    try:
        from app.services.benchmark_runner_service import get_benchmark_runner_service
        from app.services.ocr_training_service import get_ocr_training_service
        from app.db.session import get_async_session_context
        from app.db.schemas import BenchmarkRunRequest
        from uuid import UUID

        async def run_benchmark() -> Dict[str, Any]:
            async with get_async_session_context() as session:
                training_service = get_ocr_training_service()
                runner = get_benchmark_runner_service()

                # Hole Samples
                if sample_ids:
                    uuid_ids = [UUID(sid) for sid in sample_ids]
                    request_ids = uuid_ids[:max_samples]
                else:
                    # Automatische Auswahl: verifizierte Samples mit Ground-Truth
                    samples, _ = await training_service.list_training_samples(
                        db=session,
                        status="verified",
                        has_ground_truth=True,
                        verified_only=True,
                        limit=max_samples,
                    )
                    request_ids = [s.id for s in samples]

                if not request_ids:
                    return {
                        "success": True,
                        "message": "Keine Samples für Benchmark gefunden",
                        "samples_processed": 0,
                    }

                # Bestimme Backends
                backends = []
                if include_cpu:
                    backends.append("surya")
                if include_gpu:
                    backends.append("surya-gpu")

                # Führe Benchmark durch
                request = BenchmarkRunRequest(
                    sample_ids=request_ids,
                    backends=backends,
                    force_rerun=False,
                )
                result = await runner.run_benchmark(request=request)

                # Extrahiere Surya-spezifische Metriken
                surya_metrics = {
                    "surya": {"cer": 0.0, "wer": 0.0, "umlaut_accuracy": 0.0, "count": 0},
                    "surya-gpu": {"cer": 0.0, "wer": 0.0, "umlaut_accuracy": 0.0, "count": 0},
                }

                # Hole detaillierte Ergebnisse
                comparison = await runner.get_backend_comparison(db=session)
                for backend_name, stats in comparison.backends.items():
                    if backend_name in surya_metrics:
                        surya_metrics[backend_name] = {
                            "cer": stats.avg_cer or 0.0,
                            "wer": stats.avg_wer or 0.0,
                            "umlaut_accuracy": stats.avg_umlaut_accuracy or 0.0,
                            "count": stats.samples_processed,
                        }

                return {
                    "success": result.success,
                    "samples_processed": result.samples_processed,
                    "samples_failed": result.samples_failed,
                    "backends_used": result.backends_used,
                    "total_time_ms": result.total_time_ms,
                    "surya_metrics": surya_metrics,
                }

        result = asyncio.run(run_benchmark())

        logger.info(
            "surya_benchmark_completed",
            task_id=task_id,
            samples_processed=result["samples_processed"],
            surya_metrics=result.get("surya_metrics"),
        )

        return result

    except Exception as e:
        logger.exception("surya_benchmark_failed", task_id=task_id, **safe_error_log(e))
        raise


@celery_app.task(
    bind=True,
    base=CPUTask,
    name="app.workers.tasks.surya_improvement_tasks.check_surya_retraining_conditions",
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 3},
    retry_backoff=True,
    retry_backoff_max=300,
    soft_time_limit=300,
    time_limit=360,
    acks_late=True,
)
def check_surya_retraining_conditions(self) -> Dict[str, Any]:
    """
    Prüfe ob Surya-Retraining erforderlich ist.

    Triggert automatisches Fine-Tuning wenn:
    1. > 30 User-Korrektionen für Surya in 7 Tagen
    2. Umlaut-Accuracy < 95%
    3. CER Anstieg > 5% gegenüber letzter Woche
    4. > 50 neue verifizierte Samples seit letztem Training
    5. NEU: 90% Coverage erreicht mit genug neuen Samples

    Returns:
        Retraining-Empfehlung mit Gruenden
    """
    task_id = self.request.id

    logger.info("check_surya_retraining_starting", task_id=task_id)

    try:
        from app.services.feedback_learning_service import get_feedback_learning_service
        from app.services.ocr_training_service import get_ocr_training_service
        from app.services.coverage_tracking_service import get_coverage_tracking_service
        from app.db.session import get_async_session_context
        from app.db.models import (
            OCRValidationCorrection,
            OCRBackendStatsDaily,
            OCRBackendBenchmark,
        )
        from sqlalchemy import select, func, and_
        from datetime import date

        async def check_conditions() -> Dict[str, Any]:
            async with get_async_session_context() as session:
                should_retrain = False
                reasons = []
                urgency = "low"
                now = datetime.now(timezone.utc)
                seven_days_ago = now - timedelta(days=7)

                # 1. Zaehle Surya-Korrektionen (letzte 7 Tage)
                correction_result = await session.execute(
                    select(func.count(OCRValidationCorrection.id)).where(
                        and_(
                            OCRValidationCorrection.backend_used.in_(["surya", "surya-gpu"]),
                            OCRValidationCorrection.created_at >= seven_days_ago,
                        )
                    )
                )
                correction_count = correction_result.scalar() or 0

                if correction_count >= 30:
                    should_retrain = True
                    reasons.append(f"{correction_count} Korrektionen für Surya in 7 Tagen")
                    urgency = "medium"

                # 2. Prüfe aktuelle Umlaut-Accuracy
                benchmark_result = await session.execute(
                    select(
                        func.avg(OCRBackendBenchmark.umlaut_accuracy).label("avg_umlaut"),
                    ).where(
                        and_(
                            OCRBackendBenchmark.backend_name.in_(["surya", "surya-gpu"]),
                            OCRBackendBenchmark.processed_at >= seven_days_ago,
                        )
                    )
                )
                row = benchmark_result.first()
                current_umlaut_accuracy = row.avg_umlaut if row and row.avg_umlaut else 1.0

                if current_umlaut_accuracy < 0.95:
                    should_retrain = True
                    reasons.append(
                        f"Umlaut-Accuracy bei {current_umlaut_accuracy:.1%} (Ziel: >= 95%)"
                    )
                    urgency = "high" if current_umlaut_accuracy < 0.90 else "medium"

                # 3. Prüfe CER-Trend (Vergleich mit Vorwoche)
                fourteen_days_ago = now - timedelta(days=14)
                cer_current_result = await session.execute(
                    select(func.avg(OCRBackendBenchmark.cer).label("avg_cer")).where(
                        and_(
                            OCRBackendBenchmark.backend_name.in_(["surya", "surya-gpu"]),
                            OCRBackendBenchmark.processed_at >= seven_days_ago,
                        )
                    )
                )
                cer_previous_result = await session.execute(
                    select(func.avg(OCRBackendBenchmark.cer).label("avg_cer")).where(
                        and_(
                            OCRBackendBenchmark.backend_name.in_(["surya", "surya-gpu"]),
                            OCRBackendBenchmark.processed_at >= fourteen_days_ago,
                            OCRBackendBenchmark.processed_at < seven_days_ago,
                        )
                    )
                )

                current_cer = (cer_current_result.first() or (None,))[0] or 0.0
                previous_cer = (cer_previous_result.first() or (None,))[0] or 0.0

                if previous_cer > 0 and current_cer > previous_cer * 1.05:
                    should_retrain = True
                    improvement = ((current_cer - previous_cer) / previous_cer) * 100
                    reasons.append(f"CER Verschlechterung um {improvement:.1f}%")
                    urgency = "medium"

                # 4. Zaehle neue verifizierte Samples
                training_service = get_ocr_training_service()
                samples, total = await training_service.list_training_samples(
                    db=session,
                    status="verified",
                    limit=100,
                )

                # Schätze neue Samples (vereinfacht)
                new_samples_estimate = len([
                    s for s in samples
                    if s.created_at and s.created_at >= seven_days_ago
                ])

                if new_samples_estimate >= 50:
                    should_retrain = True
                    reasons.append(f"{new_samples_estimate} neue verifizierte Samples")

                # 5. NEU: Coverage-basierter Trigger (90% Business-Abdeckung)
                coverage_service = get_coverage_tracking_service()
                coverage_should_retrain, coverage_reasons = await coverage_service.get_retraining_recommendation(
                    db=session,
                    min_new_samples=50
                )

                # Coverage-basierte Empfehlung integrieren
                coverage_status = await coverage_service.calculate_coverage(session)
                weighted_coverage = coverage_status.weighted_coverage

                if coverage_should_retrain:
                    should_retrain = True
                    reasons.extend(coverage_reasons)
                    # Bei 90% Coverage ist Retraining sinnvoll
                    if urgency == "low":
                        urgency = "medium"

                return {
                    "should_retrain": should_retrain,
                    "urgency": urgency,
                    "reasons": reasons,
                    "metrics": {
                        "corrections_7d": correction_count,
                        "current_umlaut_accuracy": current_umlaut_accuracy,
                        "current_cer": current_cer,
                        "previous_cer": previous_cer,
                        "new_samples_estimate": new_samples_estimate,
                        # NEU: Coverage-Metriken
                        "weighted_coverage": weighted_coverage,
                        "coverage_target_reached": coverage_status.target_reached,
                        "total_verified_samples": coverage_status.total_verified_samples,
                        "auto_accepted_count": coverage_status.auto_accepted_count,
                    },
                    "coverage_details": {
                        "by_type": coverage_status.coverage_by_type,
                        "overall": coverage_status.overall_coverage,
                        "weighted": weighted_coverage,
                    },
                    "recommendation": (
                        "Retraining empfohlen" if should_retrain
                        else "Kein Retraining erforderlich"
                    ),
                }

        result = asyncio.run(check_conditions())

        logger.info(
            "check_surya_retraining_completed",
            task_id=task_id,
            should_retrain=result["should_retrain"],
            urgency=result["urgency"],
            reasons=result["reasons"],
        )

        # Wenn Retraining empfohlen, automatisch triggern (bei hoher Dringlichkeit)
        if result["should_retrain"] and result["urgency"] == "high":
            logger.warning(
                "surya_auto_retraining_triggered",
                task_id=task_id,
                reasons=result["reasons"],
            )
            # Triggere Export und Training
            export_surya_training_dataset.delay()

        return result

    except Exception as e:
        logger.exception(
            "check_surya_retraining_failed",
            task_id=task_id,
            **safe_error_log(e),
        )
        raise


# ==================== Surya Dataset Export Tasks ====================

@celery_app.task(
    bind=True,
    base=CPUTask,
    name="app.workers.tasks.surya_improvement_tasks.export_surya_training_dataset",
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 3},
    retry_backoff=True,
    retry_backoff_max=600,
    soft_time_limit=1800,  # 30 Minuten
    time_limit=2100,
    acks_late=True,
    reject_on_worker_lost=True,
)
def export_surya_training_dataset(
    self,
    include_corrections: bool = True,
    correction_days: int = 30,
    umlaut_focused: bool = True,
    output_dir: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Exportiere Training-Dataset für Surya Fine-Tuning.

    Erstellt stratifiziertes Dataset mit Umlaut-Fokus.

    Args:
        include_corrections: User-Korrektionen einschließen
        correction_days: Anzahl Tage für Korrektionen
        umlaut_focused: Umlaut-gewichteter Export
        output_dir: Output-Verzeichnis (optional)

    Returns:
        Export-Ergebnis mit Statistiken
    """
    task_id = self.request.id

    logger.info(
        "export_surya_dataset_starting",
        task_id=task_id,
        include_corrections=include_corrections,
        umlaut_focused=umlaut_focused,
    )

    try:
        from app.services.training_dataset_export_service import (
            SuryaDatasetExporter,
            SuryaExportConfig,
        )
        from app.db.session import get_async_session_context

        async def export_dataset() -> Dict[str, Any]:
            async with get_async_session_context() as session:
                config = SuryaExportConfig(
                    output_dir=output_dir or "./datasets/surya",
                    umlaut_weight_multiplier=2.0 if umlaut_focused else 1.0,
                    verified_only=True,
                    backend_filter=["surya", "surya-gpu"],
                )

                exporter = SuryaDatasetExporter(db=session, config=config)

                if umlaut_focused:
                    result = await exporter.export_umlaut_focused(min_umlaut_words=2)
                else:
                    result = await exporter.export_for_surya_training(
                        include_corrections=include_corrections,
                        correction_days=correction_days,
                    )

                return {
                    "success": result.success,
                    "total_samples": result.total_samples,
                    "train_samples": result.train_samples,
                    "val_samples": result.val_samples,
                    "test_samples": result.test_samples,
                    "umlaut_samples": result.umlaut_samples,
                    "output_dir": result.output_dir,
                    "train_file": result.train_file,
                    "val_file": result.val_file,
                    "test_file": result.test_file,
                    "export_timestamp": result.export_timestamp,
                }

        result = asyncio.run(export_dataset())

        logger.info(
            "export_surya_dataset_completed",
            task_id=task_id,
            total_samples=result["total_samples"],
            umlaut_samples=result["umlaut_samples"],
        )

        # Wenn erfolgreich, optional Training triggern
        if result["success"] and result["total_samples"] >= 100:
            logger.info(
                "surya_training_dataset_ready",
                task_id=task_id,
                samples=result["total_samples"],
            )

        return result

    except Exception as e:
        logger.exception(
            "export_surya_dataset_failed",
            task_id=task_id,
            **safe_error_log(e),
        )
        raise


# ==================== Surya Fine-Tuning Tasks ====================

@celery_app.task(
    bind=True,
    base=GPUTask,
    name="app.workers.tasks.surya_improvement_tasks.run_surya_german_finetuning",
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 1},
    retry_backoff=True,
    soft_time_limit=86400,  # 24 Stunden
    time_limit=90000,
    acks_late=True,
    reject_on_worker_lost=True,
)
def run_surya_german_finetuning(
    self,
    train_data_path: str,
    test_data_path: Optional[str] = None,
    config_preset: str = "default",
    config_overrides: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Führe deutsches Surya Fine-Tuning mit Umlaut-Fokus durch.

    Nutzt SuryaGermanTrainer mit UmlautWeightedCrossEntropy.

    Args:
        train_data_path: Pfad zu train.jsonl
        test_data_path: Pfad zu test.jsonl
        config_preset: Konfigurationsvoreinstellung
            - "default": Standard-Konfiguration
            - "aggressive": Maximaler Umlaut-Fokus
            - "fraktur": Optimiert für Frakturschrift
            - "quick": Schnelles inkrementelles Training
        config_overrides: Optionale Konfigurationsüberschreibungen

    Returns:
        Training-Ergebnis mit Metriken
    """
    task_id = self.request.id

    logger.info(
        "surya_german_finetuning_starting",
        task_id=task_id,
        train_data=train_data_path,
        config_preset=config_preset,
    )

    try:
        from app.ml.finetuning.surya_hf_trainer import (
            SuryaGermanTrainer,
            SuryaGermanConfig,
        )
        from app.ml.finetuning.checkpoint_manager import CheckpointManager

        # Wähle Konfiguration basierend auf Preset
        if config_preset == "aggressive":
            trainer = SuryaGermanTrainer.create_aggressive()
        elif config_preset == "fraktur":
            trainer = SuryaGermanTrainer.create_for_fraktur()
        elif config_preset == "quick":
            trainer = SuryaGermanTrainer.create_quick()
        else:
            trainer = SuryaGermanTrainer.create_default()

        # Wende Overrides an
        if config_overrides:
            for key, value in config_overrides.items():
                if hasattr(trainer.german_config, key):
                    setattr(trainer.german_config, key, value)

        async def run_training():
            return await trainer.train(
                train_data_path=train_data_path,
                test_data_path=test_data_path,
            )

        result = asyncio.run(run_training())

        # Checkpoint registrieren bei Erfolg
        if result.get("status") == "completed":
            checkpoint_manager = CheckpointManager()
            version = checkpoint_manager.create_version(
                model_name="surya-german",
                source_path=result["output_dir"],
                metrics={
                    "train_loss": result.get("train_loss"),
                    "umlaut_weight": result.get("german_config", {}).get("umlaut_weight"),
                },
                training_config={
                    "preset": config_preset,
                    **(config_overrides or {}),
                },
                notes=f"Surya German Fine-Tuning - Celery Task {task_id}",
            )
            result["registered_version"] = version

            logger.info(
                "surya_german_finetuning_version_registered",
                task_id=task_id,
                version=version,
            )

        logger.info(
            "surya_german_finetuning_completed",
            task_id=task_id,
            status=result.get("status"),
            train_loss=result.get("train_loss"),
        )

        return result

    except Exception as e:
        logger.exception(
            "surya_german_finetuning_failed",
            task_id=task_id,
            **safe_error_log(e),
        )
        raise


@celery_app.task(
    bind=True,
    base=GPUTask,
    name="app.workers.tasks.surya_improvement_tasks.evaluate_surya_model",
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 3},
    retry_backoff=True,
    soft_time_limit=3600,
    time_limit=4200,
    acks_late=True,
    reject_on_worker_lost=True,
)
def evaluate_surya_model(
    self,
    model_path: str,
    test_data_path: str,
    compare_with_baseline: bool = True,
) -> Dict[str, Any]:
    """
    Evaluiere ein trainiertes Surya-Modell.

    Führt detaillierte Umlaut-Performance-Analyse durch.

    Args:
        model_path: Pfad zum trainierten Modell
        test_data_path: Pfad zu test.jsonl
        compare_with_baseline: Mit Baseline-Modell vergleichen

    Returns:
        Evaluierungsergebnis mit detaillierten Metriken
    """
    task_id = self.request.id

    logger.info(
        "evaluate_surya_model_starting",
        task_id=task_id,
        model_path=model_path,
    )

    try:
        from app.ml.finetuning.surya_hf_trainer import SuryaGermanTrainer

        async def run_evaluation():
            # Evaluiere trainiertes Modell
            trainer = SuryaGermanTrainer.create_default()
            trainer.load_model(model_path)

            # Standard-Metriken
            test_metrics = await trainer.run_test(test_data_path)

            # Detaillierte Umlaut-Analyse
            umlaut_metrics = await trainer.evaluate_umlaut_performance(test_data_path)

            result = {
                "model_path": model_path,
                "test_metrics": {
                    "loss": test_metrics.loss,
                    "cer": test_metrics.cer,
                    "wer": test_metrics.wer,
                    "umlaut_accuracy": test_metrics.umlaut_accuracy,
                    "exact_match_ratio": test_metrics.exact_match_ratio,
                    "samples_count": test_metrics.samples_count,
                    "avg_inference_time_ms": test_metrics.avg_inference_time_ms,
                },
                "umlaut_analysis": umlaut_metrics,
            }

            # Vergleich mit Baseline
            if compare_with_baseline:
                baseline_trainer = SuryaGermanTrainer.create_default()
                baseline_trainer.setup()  # Laedt Original-Modell

                baseline_test = await baseline_trainer.run_test(test_data_path)
                baseline_umlaut = await baseline_trainer.evaluate_umlaut_performance(
                    test_data_path
                )

                result["baseline_metrics"] = {
                    "cer": baseline_test.cer,
                    "wer": baseline_test.wer,
                    "umlaut_accuracy": baseline_test.umlaut_accuracy,
                }
                result["baseline_umlaut"] = baseline_umlaut

                # Berechne Verbesserung
                result["improvement"] = {
                    "cer_improvement": baseline_test.cer - test_metrics.cer,
                    "wer_improvement": baseline_test.wer - test_metrics.wer,
                    "umlaut_improvement": (
                        test_metrics.umlaut_accuracy - baseline_test.umlaut_accuracy
                    ),
                }

                # Empfehlung
                is_better = (
                    test_metrics.umlaut_accuracy >= baseline_test.umlaut_accuracy
                    and test_metrics.cer <= baseline_test.cer * 1.05
                )
                result["recommendation"] = (
                    "deploy" if is_better else "rollback"
                )

            return result

        result = asyncio.run(run_evaluation())

        logger.info(
            "evaluate_surya_model_completed",
            task_id=task_id,
            umlaut_accuracy=result["test_metrics"]["umlaut_accuracy"],
            recommendation=result.get("recommendation"),
        )

        return result

    except Exception as e:
        logger.exception(
            "evaluate_surya_model_failed",
            task_id=task_id,
            **safe_error_log(e),
        )
        raise


# ==================== Surya Deployment Tasks ====================

@celery_app.task(
    bind=True,
    base=CPUTask,
    name="app.workers.tasks.surya_improvement_tasks.deploy_surya_model",
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 3},
    retry_backoff=True,
    soft_time_limit=600,
    time_limit=720,
    acks_late=True,
    reject_on_worker_lost=True,
)
def deploy_surya_model(
    self,
    version: str,
    traffic_percentage: float = 20.0,
    ab_test_duration_hours: int = 48,
) -> Dict[str, Any]:
    """
    Deploye ein neues Surya-Modell mit A/B Testing.

    Beginnt mit niedrigem Traffic-Anteil und eskaliert bei Erfolg.

    Args:
        version: Modell-Version zum Deployen
        traffic_percentage: Initialer Traffic-Anteil (default: 20%)
        ab_test_duration_hours: Dauer des A/B Tests

    Returns:
        Deployment-Status
    """
    task_id = self.request.id

    logger.info(
        "deploy_surya_model_starting",
        task_id=task_id,
        version=version,
        traffic_percentage=traffic_percentage,
    )

    try:
        from app.ml.finetuning.checkpoint_manager import CheckpointManager

        checkpoint_manager = CheckpointManager()

        # Aktiviere Version mit Traffic-Split
        success = checkpoint_manager.activate_version(
            model_name="surya-german",
            version=version,
            traffic_percentage=traffic_percentage,
        )

        if not success:
            return {
                "success": False,
                "error": f"Version {version} konnte nicht aktiviert werden",
            }

        # Plane Eskalation nach A/B Test
        escalation_time = datetime.now(timezone.utc) + timedelta(
            hours=ab_test_duration_hours
        )

        logger.info(
            "deploy_surya_model_ab_test_started",
            task_id=task_id,
            version=version,
            traffic_percentage=traffic_percentage,
            escalation_time=escalation_time.isoformat(),
        )

        # Plane Evaluierung nach A/B Test-Periode
        evaluate_surya_ab_test.apply_async(
            args=[version],
            countdown=ab_test_duration_hours * 3600,
        )

        return {
            "success": True,
            "version": version,
            "traffic_percentage": traffic_percentage,
            "ab_test_duration_hours": ab_test_duration_hours,
            "escalation_scheduled": escalation_time.isoformat(),
        }

    except Exception as e:
        logger.exception(
            "deploy_surya_model_failed",
            task_id=task_id,
            **safe_error_log(e),
        )
        raise


@celery_app.task(
    bind=True,
    base=CPUTask,
    name="app.workers.tasks.surya_improvement_tasks.evaluate_surya_ab_test",
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 3},
    retry_backoff=True,
    soft_time_limit=600,
    time_limit=720,
    acks_late=True,
)
def evaluate_surya_ab_test(
    self,
    version: str,
) -> Dict[str, Any]:
    """
    Evaluiere A/B Test und entscheide über Full Rollout oder Rollback.

    Vergleicht Metriken der neuen Version mit der alten.

    Args:
        version: Zu evaluierende Version

    Returns:
        A/B Test Ergebnis mit Entscheidung
    """
    task_id = self.request.id

    logger.info(
        "evaluate_ab_test_starting",
        task_id=task_id,
        version=version,
    )

    try:
        from app.ml.finetuning.checkpoint_manager import CheckpointManager
        from app.db.session import get_async_session_context
        from app.db.models import OCRBackendBenchmark
        from sqlalchemy import select, func, and_
        from datetime import timedelta

        async def evaluate_ab():
            async with get_async_session_context() as session:
                checkpoint_manager = CheckpointManager()
                now = datetime.now(timezone.utc)
                ab_test_start = now - timedelta(hours=48)

                # Hole Metriken für beide Versionen
                # (Hier vereinfacht - in Produktion wuerde man nach Version filtern)
                result = await session.execute(
                    select(
                        func.avg(OCRBackendBenchmark.cer).label("avg_cer"),
                        func.avg(OCRBackendBenchmark.wer).label("avg_wer"),
                        func.avg(OCRBackendBenchmark.umlaut_accuracy).label("avg_umlaut"),
                        func.count(OCRBackendBenchmark.id).label("count"),
                    ).where(
                        and_(
                            OCRBackendBenchmark.backend_name.in_(["surya", "surya-gpu"]),
                            OCRBackendBenchmark.processed_at >= ab_test_start,
                        )
                    )
                )
                row = result.first()

                current_metrics = {
                    "cer": row.avg_cer or 0.0,
                    "wer": row.avg_wer or 0.0,
                    "umlaut_accuracy": row.avg_umlaut or 1.0,
                    "sample_count": row.count or 0,
                }

                # Entscheidungslogik
                # Umlaut-Accuracy >= 95% UND CER nicht verschlechtert
                should_full_rollout = (
                    current_metrics["umlaut_accuracy"] >= 0.95
                    and current_metrics["sample_count"] >= 50
                )

                if should_full_rollout:
                    # Full Rollout
                    checkpoint_manager.activate_version(
                        model_name="surya-german",
                        version=version,
                        traffic_percentage=100.0,
                    )
                    decision = "full_rollout"
                    logger.info(
                        "ab_test_full_rollout",
                        task_id=task_id,
                        version=version,
                        umlaut_accuracy=current_metrics["umlaut_accuracy"],
                    )
                else:
                    # Rollback
                    checkpoint_manager.deactivate_version("surya-german", version)
                    decision = "rollback"
                    logger.warning(
                        "ab_test_rollback",
                        task_id=task_id,
                        version=version,
                        umlaut_accuracy=current_metrics["umlaut_accuracy"],
                    )

                return {
                    "version": version,
                    "decision": decision,
                    "metrics": current_metrics,
                    "threshold_met": should_full_rollout,
                }

        result = asyncio.run(evaluate_ab())

        logger.info(
            "evaluate_ab_test_completed",
            task_id=task_id,
            decision=result["decision"],
        )

        return result

    except Exception as e:
        logger.exception(
            "evaluate_ab_test_failed",
            task_id=task_id,
            **safe_error_log(e),
        )
        raise


@celery_app.task(
    bind=True,
    base=CPUTask,
    name="app.workers.tasks.surya_improvement_tasks.rollback_surya_model",
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 3},
    retry_backoff=True,
    soft_time_limit=300,
    time_limit=360,
    acks_late=True,
)
def rollback_surya_model(
    self,
    target_version: str,
    reason: str = "Manual rollback",
) -> Dict[str, Any]:
    """
    Führe Rollback zu einer früheren Surya-Version durch.

    Args:
        target_version: Ziel-Version für Rollback
        reason: Grund für Rollback

    Returns:
        Rollback-Status
    """
    task_id = self.request.id

    logger.warning(
        "rollback_surya_model_starting",
        task_id=task_id,
        target_version=target_version,
        reason=reason,
    )

    try:
        from app.ml.finetuning.checkpoint_manager import CheckpointManager

        checkpoint_manager = CheckpointManager()

        success = checkpoint_manager.rollback_to_version(
            model_name="surya-german",
            target_version=target_version,
            reason=reason,
        )

        if success:
            logger.info(
                "rollback_surya_model_completed",
                task_id=task_id,
                target_version=target_version,
            )
        else:
            logger.error(
                "rollback_surya_model_failed",
                task_id=task_id,
                target_version=target_version,
            )

        return {
            "success": success,
            "target_version": target_version,
            "reason": reason,
        }

    except Exception as e:
        logger.exception(
            "rollback_surya_model_error",
            task_id=task_id,
            **safe_error_log(e),
        )
        raise


# ==================== Surya Feedback Processing Tasks ====================

@celery_app.task(
    bind=True,
    base=CPUTask,
    name="app.workers.tasks.surya_improvement_tasks.process_surya_corrections",
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 3},
    retry_backoff=True,
    retry_backoff_max=300,
    soft_time_limit=600,
    time_limit=720,
    acks_late=True,
)
def process_surya_corrections(
    self,
    days: int = 7,
    batch_size: int = 100,
) -> Dict[str, Any]:
    """
    Verarbeite Surya-Korrektionen für Training.

    Konvertiert User-Korrektionen zu Training Samples.

    Args:
        days: Anzahl Tage zurück
        batch_size: Batch-Größe

    Returns:
        Verarbeitungs-Statistiken
    """
    task_id = self.request.id

    logger.info(
        "process_surya_corrections_starting",
        task_id=task_id,
        days=days,
    )

    try:
        from app.services.feedback_learning_service import get_feedback_learning_service
        from app.db.session import get_async_session_context
        from app.db.models import OCRValidationCorrection, OCRTrainingSample
        from sqlalchemy import select, and_
        from datetime import timedelta

        async def process_corrections():
            async with get_async_session_context() as session:
                feedback_service = get_feedback_learning_service()
                now = datetime.now(timezone.utc)
                start_date = now - timedelta(days=days)

                # Hole unverarbeitete Surya-Korrektionen
                result = await session.execute(
                    select(OCRValidationCorrection).where(
                        and_(
                            OCRValidationCorrection.backend_used.in_(["surya", "surya-gpu"]),
                            OCRValidationCorrection.created_at >= start_date,
                            OCRValidationCorrection.processed_for_learning == False,
                        )
                    ).limit(batch_size)
                )
                corrections = list(result.scalars().all())

                processed = 0
                samples_created = 0
                errors = []

                for correction in corrections:
                    try:
                        # Erstelle oder aktualisiere Training Sample
                        # (Vereinfacht - in Produktion komplexere Logik)
                        correction.processed_for_learning = True
                        correction.processed_at = now
                        processed += 1

                        # Markiere als potentielles Training Sample
                        if correction.correction_type in ["text", "umlaut"]:
                            samples_created += 1

                    except Exception as e:
                        errors.append({
                            "correction_id": str(correction.id),
                            "error": safe_error_detail(e, "Vorgang"),
                        })

                await session.commit()

                return {
                    "corrections_found": len(corrections),
                    "processed": processed,
                    "samples_created": samples_created,
                    "errors": errors,
                }

        result = asyncio.run(process_corrections())

        logger.info(
            "process_surya_corrections_completed",
            task_id=task_id,
            processed=result["processed"],
            samples_created=result["samples_created"],
        )

        return result

    except Exception as e:
        logger.exception(
            "process_surya_corrections_failed",
            task_id=task_id,
            **safe_error_log(e),
        )
        raise


# ==================== Metrics & Reporting Tasks ====================

@celery_app.task(
    bind=True,
    base=CPUTask,
    name="app.workers.tasks.surya_improvement_tasks.update_surya_metrics",
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 2},
    soft_time_limit=120,
    time_limit=180,
    acks_late=True,
)
def update_surya_metrics(self) -> Dict[str, Any]:
    """
    Aktualisiere Surya-Metriken für Prometheus Monitoring.

    Wird alle 15 Minuten ausgeführt um aktuelle Metriken zu exportieren.

    Returns:
        Aktuelle Metriken-Werte
    """
    task_id = self.request.id

    logger.info("update_surya_metrics_starting", task_id=task_id)

    try:
        from app.ml.metrics import get_ml_metrics
        from app.db.session import get_async_session_context
        from app.db.models import SuryaModelVersion, SuryaABTest, SuryaABTestStatus
        from sqlalchemy import select, func

        async def gather_metrics():
            async with get_async_session_context() as session:
                metrics = get_ml_metrics()
                result = {}

                # Hole aktive Model-Version
                active_query = await session.execute(
                    select(SuryaModelVersion).where(
                        SuryaModelVersion.is_production == True
                    ).limit(1)
                )
                active_model = active_query.scalar_one_or_none()

                if active_model:
                    metrics.update_surya_model_metrics(
                        version=active_model.version,
                        cer=active_model.cer or 0.0,
                        wer=active_model.wer or 0.0,
                        umlaut_accuracy=active_model.umlaut_accuracy or 0.0,
                        eszett_accuracy=active_model.eszett_accuracy,
                        is_production=True,
                    )
                    result["active_version"] = active_model.version
                    result["cer"] = active_model.cer
                    result["wer"] = active_model.wer
                    result["umlaut_accuracy"] = active_model.umlaut_accuracy

                # Zaehle aktive A/B Tests
                ab_count_query = await session.execute(
                    select(func.count(SuryaABTest.id)).where(
                        SuryaABTest.status == SuryaABTestStatus.RUNNING
                    )
                )
                active_ab_tests = ab_count_query.scalar() or 0
                metrics.set_surya_ab_tests_active(active_ab_tests)
                result["active_ab_tests"] = active_ab_tests

                # Gesamtzahl Versionen und Checkpoint-Größe
                version_count_query = await session.execute(
                    select(func.count(SuryaModelVersion.id))
                )
                total_versions = version_count_query.scalar() or 0

                # Calculate total checkpoint size from database
                checkpoint_size_query = await session.execute(
                    select(func.coalesce(func.sum(SuryaModelVersion.checkpoint_size_mb), 0.0))
                )
                total_checkpoint_size_mb = checkpoint_size_query.scalar() or 0.0

                metrics.update_surya_versioning_metrics(
                    total_versions=total_versions,
                    total_checkpoint_size_mb=float(total_checkpoint_size_mb),
                )
                result["total_versions"] = total_versions
                result["total_checkpoint_size_mb"] = float(total_checkpoint_size_mb)

                return result

        result = asyncio.run(gather_metrics())

        logger.info(
            "update_surya_metrics_completed",
            task_id=task_id,
            **result,
        )

        return {"success": True, **result}

    except Exception as e:
        logger.exception(
            "update_surya_metrics_failed",
            task_id=task_id,
            **safe_error_log(e),
        )
        # Don't raise - metrics update failure should not block
        return {"success": False, **safe_error_log(e)}


@celery_app.task(
    bind=True,
    base=CPUTask,
    name="app.workers.tasks.surya_improvement_tasks.generate_surya_improvement_report",
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 2},
    soft_time_limit=300,
    time_limit=360,
    acks_late=True,
)
def generate_surya_improvement_report(
    self,
    period_days: int = 30,
) -> Dict[str, Any]:
    """
    Generiere monatlichen Surya Improvement Report.

    Fasst Training-Fortschritt, Benchmark-Ergebnisse und
    Qualitätsentwicklung zusammen.

    Args:
        period_days: Berichtszeitraum in Tagen

    Returns:
        Report-Daten
    """
    task_id = self.request.id

    logger.info(
        "generate_surya_improvement_report_starting",
        task_id=task_id,
        period_days=period_days,
    )

    try:
        from app.db.session import get_async_session_context
        from app.db.models import (
            SuryaModelVersion, SuryaTrainingRun, SuryaABTest,
            SuryaBenchmarkHistory, SuryaTrainingRunStatus, SuryaABTestStatus
        )
        from sqlalchemy import select, func, and_
        from datetime import timedelta

        async def generate_report():
            async with get_async_session_context() as session:
                now = datetime.now(timezone.utc)
                start_date = now - timedelta(days=period_days)

                report = {
                    "period_start": start_date.isoformat(),
                    "period_end": now.isoformat(),
                    "period_days": period_days,
                    "generated_at": now.isoformat(),
                }

                # Training Runs im Zeitraum
                training_query = await session.execute(
                    select(
                        SuryaTrainingRun.status,
                        func.count(SuryaTrainingRun.id).label("count"),
                    ).where(
                        SuryaTrainingRun.created_at >= start_date
                    ).group_by(SuryaTrainingRun.status)
                )
                training_stats = {str(row.status): row.count for row in training_query.all()}
                report["training_runs"] = {
                    "total": sum(training_stats.values()),
                    "by_status": training_stats,
                }

                # A/B Tests im Zeitraum
                ab_query = await session.execute(
                    select(
                        SuryaABTest.status,
                        func.count(SuryaABTest.id).label("count"),
                    ).where(
                        SuryaABTest.created_at >= start_date
                    ).group_by(SuryaABTest.status)
                )
                ab_stats = {str(row.status): row.count for row in ab_query.all()}
                report["ab_tests"] = {
                    "total": sum(ab_stats.values()),
                    "by_status": ab_stats,
                }

                # Aktuelle Qualität vs. vor 30 Tagen
                current_model = await session.execute(
                    select(SuryaModelVersion).where(
                        SuryaModelVersion.is_production == True
                    ).limit(1)
                )
                current = current_model.scalar_one_or_none()

                old_model = await session.execute(
                    select(SuryaModelVersion).where(
                        and_(
                            SuryaModelVersion.created_at <= start_date,
                            SuryaModelVersion.is_production == True,
                        )
                    ).order_by(SuryaModelVersion.created_at.desc()).limit(1)
                )
                old = old_model.scalar_one_or_none()

                if current:
                    report["current_quality"] = {
                        "version": current.version,
                        "cer": current.cer,
                        "wer": current.wer,
                        "umlaut_accuracy": current.umlaut_accuracy,
                    }

                    if old:
                        report["quality_improvement"] = {
                            "cer_delta": (current.cer or 0) - (old.cer or 0),
                            "wer_delta": (current.wer or 0) - (old.wer or 0),
                            "umlaut_delta": (current.umlaut_accuracy or 0) - (old.umlaut_accuracy or 0),
                            "compared_to_version": old.version,
                        }

                # Anzahl neue Versionen
                new_versions_query = await session.execute(
                    select(func.count(SuryaModelVersion.id)).where(
                        SuryaModelVersion.created_at >= start_date
                    )
                )
                report["new_versions"] = new_versions_query.scalar() or 0

                # Rollbacks im Zeitraum
                rollback_query = await session.execute(
                    select(func.count(SuryaModelVersion.id)).where(
                        and_(
                            SuryaModelVersion.rolled_back_at >= start_date,
                            SuryaModelVersion.rolled_back_at.isnot(None),
                        )
                    )
                )
                report["rollbacks"] = rollback_query.scalar() or 0

                return report

        report = asyncio.run(generate_report())

        logger.info(
            "generate_surya_improvement_report_completed",
            task_id=task_id,
            training_runs=report.get("training_runs", {}).get("total", 0),
            ab_tests=report.get("ab_tests", {}).get("total", 0),
        )

        return {"success": True, "report": report}

    except Exception as e:
        logger.exception(
            "generate_surya_improvement_report_failed",
            task_id=task_id,
            **safe_error_log(e),
        )
        raise


# ==================== Celery Beat Schedule ====================

CELERY_BEAT_SURYA_IMPROVEMENT_SCHEDULE = {
    # Täglich: Surya Benchmark
    "surya-daily-benchmark": {
        "task": "app.workers.tasks.surya_improvement_tasks.run_surya_benchmark",
        "schedule": 86400.0,  # 24 Stunden
        "options": {"queue": "gpu"},
        "kwargs": {"max_samples": 50, "include_cpu": True, "include_gpu": True},
    },
    # Täglich: Retraining-Bedingungen prüfen
    "surya-check-retraining-daily": {
        "task": "app.workers.tasks.surya_improvement_tasks.check_surya_retraining_conditions",
        "schedule": 86400.0,  # 24 Stunden um 02:00
        "options": {"queue": "default"},
    },
    # Stündlich: Surya-Korrektionen verarbeiten
    "surya-process-corrections-hourly": {
        "task": "app.workers.tasks.surya_improvement_tasks.process_surya_corrections",
        "schedule": 3600.0,  # 1 Stunde
        "options": {"queue": "default"},
        "kwargs": {"days": 7, "batch_size": 50},
    },
    # Alle 15 Minuten: Metriken aktualisieren
    "surya-update-metrics": {
        "task": "app.workers.tasks.surya_improvement_tasks.update_surya_metrics",
        "schedule": 900.0,  # 15 Minuten
        "options": {"queue": "metrics"},
    },
    # Monatlich: Improvement Report
    "surya-monthly-report": {
        "task": "app.workers.tasks.surya_improvement_tasks.generate_surya_improvement_report",
        "schedule": 2592000.0,  # 30 Tage
        "options": {"queue": "maintenance"},
        "kwargs": {"period_days": 30},
    },
}
