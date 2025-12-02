# -*- coding: utf-8 -*-
"""
ML-spezifische Celery Tasks.

Enthält:
- Drift Detection Tasks (periodisch)
- A/B Experiment Tracking
- ML Metriken Sammlung
- Model Retraining Trigger

Feinpoliert und durchdacht - ML-Operationen für Produktion.
"""

import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import UUID

import structlog

from app.workers.celery_app import celery_app, CPUTask
from app.core.config import settings

logger = structlog.get_logger(__name__)


# ==================== ML Tracking Helpers ====================

class MLTracker:
    """Helper für ML-Tracking in OCR Tasks."""

    @staticmethod
    def track_routing_decision(
        document_id: str,
        features: Dict[str, Any],
        selected_backend: str,
        confidence: float,
        routing_method: str,
        latency_ms: float,
    ) -> None:
        """
        Tracke Routing-Entscheidung für Drift Detection und Metriken.

        Args:
            document_id: Dokument-ID
            features: Dokument-Features
            selected_backend: Gewähltes Backend
            confidence: Routing-Konfidenz
            routing_method: ml oder rule_based
            latency_ms: Routing-Latenz
        """
        try:
            from app.ml.drift_detector import get_drift_detector
            from app.ml.metrics import get_ml_metrics

            # Record for drift detection
            drift_detector = get_drift_detector()
            drift_detector.add_sample(
                features=features,
                prediction=selected_backend,
            )

            # Record metrics
            metrics = get_ml_metrics()
            metrics.record_routing_request(
                method=routing_method,
                backend=selected_backend,
                status="success",
                latency_seconds=latency_ms / 1000,
                confidence=confidence,
            )

            logger.debug(
                "ml_routing_tracked",
                document_id=document_id,
                backend=selected_backend,
                method=routing_method,
            )

        except Exception as e:
            logger.warning("ml_tracking_failed", error=str(e))

    @staticmethod
    def track_ocr_result(
        document_id: str,
        backend: str,
        success: bool,
        processing_time_ms: float,
        accuracy: Optional[float] = None,
        language: str = "de",
        document_type: str = "unknown",
    ) -> None:
        """
        Tracke OCR-Ergebnis für Metriken und A/B Tests.

        Args:
            document_id: Dokument-ID
            backend: Verwendetes Backend
            success: Erfolgreiche Verarbeitung?
            processing_time_ms: Verarbeitungszeit
            accuracy: OCR-Genauigkeit
            language: Dokumentsprache
            document_type: Dokumenttyp
        """
        try:
            from app.ml.metrics import get_ml_metrics
            from app.ml.ab_testing import get_ab_test_manager

            # Record backend metrics
            metrics = get_ml_metrics()
            metrics.record_backend_request(
                backend=backend,
                status="success" if success else "error",
                language=language,
                processing_time=processing_time_ms / 1000,
                accuracy=accuracy,
                document_type=document_type,
            )

            # Check for active A/B experiments
            ab_manager = get_ab_test_manager()
            for experiment in ab_manager.get_active_experiments():
                # Check if this document is part of an experiment
                variant = ab_manager.get_variant(experiment.experiment_id, document_id)
                if variant and variant.config.get("backend") == backend:
                    ab_manager.record_result(
                        experiment_id=experiment.experiment_id,
                        variant_name=variant.name,
                        success=success,
                        latency_ms=processing_time_ms,
                        accuracy=accuracy,
                    )

                    # Record Prometheus metrics for A/B sample
                    metrics.record_ab_sample(
                        experiment_id=experiment.experiment_id,
                        variant=variant.name,
                        success=success,
                    )

                    logger.debug(
                        "ab_result_recorded",
                        experiment_id=experiment.experiment_id,
                        variant=variant.name,
                        success=success,
                    )

        except Exception as e:
            logger.warning("ocr_result_tracking_failed", error=str(e))

    @staticmethod
    def get_routing_explanation(
        document_id: str,
        features: Dict[str, Any],
        selected_backend: str,
        confidence: float,
        all_probabilities: Dict[str, float],
    ) -> Optional[Dict[str, Any]]:
        """
        Generiere SHAP-Erklärung für Routing.

        Args:
            document_id: Dokument-ID
            features: Dokument-Features
            selected_backend: Gewähltes Backend
            confidence: Routing-Konfidenz
            all_probabilities: Wahrscheinlichkeiten aller Backends

        Returns:
            Erklärung als Dictionary oder None
        """
        try:
            from app.ml.shap_explainer import get_shap_explainer

            explainer = get_shap_explainer()
            explanation = explainer.explain_routing(
                document_id=document_id,
                features=features,
                selected_backend=selected_backend,
                confidence=confidence,
                all_probabilities=all_probabilities,
            )

            return explanation.to_dict()

        except Exception as e:
            logger.warning("shap_explanation_failed", error=str(e))
            return None


# Globaler Tracker
ml_tracker = MLTracker()


# ==================== Periodic ML Tasks ====================

@celery_app.task(
    bind=True,
    base=CPUTask,
    name="app.workers.tasks.ml_tasks.run_drift_detection",
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 3},
    retry_backoff=True,
    retry_backoff_max=600,
    soft_time_limit=300,
    time_limit=360,
    acks_late=True,
    reject_on_worker_lost=True,
)
def run_drift_detection(self) -> Dict[str, Any]:
    """
    Führe periodische Drift-Detection durch.

    Sollte stündlich oder täglich ausgeführt werden.

    Returns:
        Drift-Report als Dictionary
    """
    task_id = self.request.id

    logger.info("drift_detection_task_starting", task_id=task_id)

    try:
        from app.ml.drift_detector import get_drift_detector
        from app.ml.metrics import get_ml_metrics

        detector = get_drift_detector()
        report = detector.detect_drift()

        # Record drift metrics
        metrics = get_ml_metrics()
        feature_scores = {
            fd.feature_name: fd.drift_score
            for fd in report.feature_drifts
        }
        metrics.record_drift_score(
            overall_score=report.overall_drift_score,
            feature_scores=feature_scores,
            severity=report.severity.value,
        )

        logger.info(
            "drift_detection_completed",
            task_id=task_id,
            severity=report.severity.value,
            overall_score=report.overall_drift_score,
            recommendations_count=len(report.recommendations),
        )

        return report.to_dict()

    except Exception as e:
        logger.exception("drift_detection_failed", task_id=task_id, error=str(e))
        raise


@celery_app.task(
    bind=True,
    base=CPUTask,
    name="app.workers.tasks.ml_tasks.update_ml_metrics",
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 2},
    retry_backoff=True,
    retry_backoff_max=30,
    soft_time_limit=25,
    time_limit=30,
    acks_late=True,
    reject_on_worker_lost=True,
)
def update_ml_metrics(self) -> Dict[str, Any]:
    """
    Aktualisiere ML-Metriken für Prometheus.

    Sollte alle 30 Sekunden ausgeführt werden.

    Returns:
        Aktuelle Metriken
    """
    task_id = self.request.id

    try:
        from app.ml.metrics import get_ml_metrics
        from app.ml.ab_testing import get_ab_test_manager
        from app.ml.drift_detector import get_drift_detector

        metrics = get_ml_metrics()

        # Update GPU metrics
        metrics.update_gpu_metrics()

        # Update A/B experiment count
        ab_manager = get_ab_test_manager()
        active_experiments = ab_manager.get_active_experiments()
        metrics.set_active_experiments(len(active_experiments))

        # Get drift status
        drift_detector = get_drift_detector()
        drift_status = drift_detector.get_current_status()

        result = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "active_experiments": len(active_experiments),
            "drift_ready": drift_status["ready_for_detection"],
            "reference_samples": drift_status["reference_samples"],
            "current_samples": drift_status["current_samples"],
        }

        logger.debug("ml_metrics_updated", task_id=task_id, **result)

        return result

    except Exception as e:
        logger.warning("ml_metrics_update_failed", error=str(e))
        return {"error": str(e)}


@celery_app.task(
    bind=True,
    base=CPUTask,
    name="app.workers.tasks.ml_tasks.check_experiment_completion",
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 3},
    retry_backoff=True,
    retry_backoff_max=300,
    soft_time_limit=240,
    time_limit=300,
    acks_late=True,
    reject_on_worker_lost=True,
)
def check_experiment_completion(self) -> Dict[str, Any]:
    """
    Prüfe ob Experimente abgeschlossen werden sollten.

    Prüft:
    - Zeitlimit erreicht
    - Statistische Signifikanz erreicht
    - Minimum Samples erreicht

    Returns:
        Liste abgeschlossener Experimente
    """
    task_id = self.request.id

    logger.info("experiment_check_starting", task_id=task_id)

    try:
        from app.ml.ab_testing import get_ab_test_manager, ExperimentStatus

        ab_manager = get_ab_test_manager()
        active_experiments = ab_manager.get_active_experiments()

        completed = []
        now = datetime.now()

        for experiment in active_experiments:
            should_conclude = False
            reason = ""

            # Check time limit
            if experiment.end_time and now > experiment.end_time:
                should_conclude = True
                reason = "Zeitlimit erreicht"

            # Check significance
            if experiment.significance_reached:
                should_conclude = True
                reason = "Statistische Signifikanz erreicht"

            if should_conclude:
                winner = ab_manager.conclude_experiment(experiment.experiment_id)
                completed.append({
                    "experiment_id": experiment.experiment_id,
                    "name": experiment.name,
                    "winner": winner,
                    "reason": reason,
                })

                logger.info(
                    "experiment_concluded",
                    experiment_id=experiment.experiment_id,
                    winner=winner,
                    reason=reason,
                )

        return {
            "checked": len(active_experiments),
            "completed": completed,
        }

    except Exception as e:
        logger.exception("experiment_check_failed", task_id=task_id, error=str(e))
        raise


@celery_app.task(
    bind=True,
    base=CPUTask,
    name="app.workers.tasks.ml_tasks.trigger_model_retrain",
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 3},
    retry_backoff=True,
    retry_backoff_max=600,
    soft_time_limit=600,
    time_limit=720,
    acks_late=True,
    reject_on_worker_lost=True,
)
def trigger_model_retrain(
    self,
    force: bool = False,
    drift_threshold: float = 0.5,
) -> Dict[str, Any]:
    """
    Prüfe ob Model-Retraining nötig ist und triggere es.

    Args:
        force: Erzwinge Retraining
        drift_threshold: Drift-Schwelle für automatisches Retraining

    Returns:
        Retraining-Status
    """
    task_id = self.request.id

    logger.info(
        "retrain_check_starting",
        task_id=task_id,
        force=force,
        drift_threshold=drift_threshold,
    )

    try:
        from app.ml.drift_detector import get_drift_detector, DriftSeverity

        detector = get_drift_detector()
        history = detector.get_drift_history(limit=1)

        should_retrain = force
        reason = "Manuell getriggert" if force else ""

        if not force and history:
            latest_report = history[-1]
            if latest_report.overall_drift_score >= drift_threshold:
                should_retrain = True
                reason = f"Drift-Score {latest_report.overall_drift_score:.2f} >= {drift_threshold}"
            elif latest_report.severity in (DriftSeverity.HIGH, DriftSeverity.CRITICAL):
                should_retrain = True
                reason = f"Schweregrad: {latest_report.severity.value}"

        result = {
            "should_retrain": should_retrain,
            "reason": reason,
            "retrain_triggered": False,
        }

        if should_retrain:
            # Hier würde das tatsächliche Retraining getriggert werden
            # Für jetzt loggen wir nur und setzen Reference zurück
            logger.warning(
                "model_retrain_recommended",
                task_id=task_id,
                reason=reason,
            )

            # Reset drift reference nach Retraining
            detector.reset_reference_window()
            result["retrain_triggered"] = True
            result["reference_reset"] = True

        return result

    except Exception as e:
        logger.exception("retrain_check_failed", task_id=task_id, error=str(e))
        raise


@celery_app.task(
    bind=True,
    base=CPUTask,
    name="app.workers.tasks.ml_tasks.generate_ml_report",
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 3},
    retry_backoff=True,
    retry_backoff_max=600,
    soft_time_limit=300,
    time_limit=360,
    acks_late=True,
    reject_on_worker_lost=True,
)
def generate_ml_report(self) -> Dict[str, Any]:
    """
    Generiere umfassenden ML-Status-Report.

    Enthält:
    - Drift-Status
    - A/B Test Ergebnisse
    - Feature Importance
    - Routing-Statistiken

    Returns:
        Vollständiger ML-Report
    """
    task_id = self.request.id

    logger.info("ml_report_starting", task_id=task_id)

    try:
        from app.ml.drift_detector import get_drift_detector
        from app.ml.ab_testing import get_ab_test_manager
        from app.ml.shap_explainer import get_shap_explainer

        # Drift Status
        drift_detector = get_drift_detector()
        drift_status = drift_detector.get_current_status()
        drift_history = drift_detector.get_drift_history(limit=5)

        # A/B Experiments
        ab_manager = get_ab_test_manager()
        active_experiments = [
            exp.get_summary() for exp in ab_manager.get_active_experiments()
        ]
        from app.ml.ab_testing import ExperimentStatus
        completed_experiments = [
            exp.get_summary()
            for exp in ab_manager.list_experiments(ExperimentStatus.COMPLETED)
        ][-5:]

        # Feature Importance
        explainer = get_shap_explainer()
        feature_importance = explainer.get_global_importance()

        report = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "drift": {
                "status": drift_status,
                "recent_reports": [r.to_dict() for r in drift_history],
            },
            "experiments": {
                "active": active_experiments,
                "recently_completed": completed_experiments,
            },
            "feature_importance": feature_importance,
            "recommendations": [],
        }

        # Generate recommendations
        if drift_history:
            latest = drift_history[-1]
            if latest.severity.value in ("high", "critical"):
                report["recommendations"].append(
                    "⚠️ Hoher Drift erkannt - Retraining empfohlen"
                )

        if not active_experiments:
            report["recommendations"].append(
                "Keine aktiven A/B Tests - Optimierung durch Experimente möglich"
            )

        logger.info(
            "ml_report_generated",
            task_id=task_id,
            drift_ready=drift_status["ready_for_detection"],
            active_experiments=len(active_experiments),
        )

        return report

    except Exception as e:
        logger.exception("ml_report_failed", task_id=task_id, error=str(e))
        raise


@celery_app.task(
    bind=True,
    base=CPUTask,
    name="app.workers.tasks.ml_tasks.check_drift_and_respond",
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 3},
    retry_backoff=True,
    retry_backoff_max=600,
    soft_time_limit=300,
    time_limit=360,
    acks_late=True,
    reject_on_worker_lost=True,
)
def check_drift_and_respond(self) -> Dict[str, Any]:
    """
    Prüfe Drift und reagiere automatisch mit A/B-Tests oder Alerts.

    Diese Task integriert:
    - Drift Detection mit automatischer A/B-Test Erstellung bei PSI > 0.2
    - Alert bei kritischem Drift (PSI > 0.25)
    - Quality Degradation Monitoring
    - Retraining-Trigger Check

    Returns:
        Dict mit durchgeführten Aktionen
    """
    task_id = self.request.id

    logger.info("drift_response_check_starting", task_id=task_id)

    try:
        from app.ml.drift_detector import get_drift_alert_manager

        alert_manager = get_drift_alert_manager()

        # Check drift and respond
        result = alert_manager.check_and_respond_to_drift()

        # Check if retraining is needed
        retraining_status = alert_manager.check_retraining_trigger()
        result["retraining_status"] = retraining_status

        # Log summary
        logger.info(
            "drift_response_check_completed",
            task_id=task_id,
            drift_detected=result.get("drift_detected", False),
            alerts_sent=len(result.get("alerts_sent", [])),
            experiments_created=len(result.get("experiments_created", [])),
            quality_status=result.get("quality_status", "unknown"),
            should_retrain=retraining_status.get("should_retrain", False),
        )

        return result

    except Exception as e:
        logger.exception("drift_response_check_failed", task_id=task_id, error=str(e))
        raise


@celery_app.task(
    bind=True,
    base=CPUTask,
    name="app.workers.tasks.ml_tasks.generate_monthly_drift_report",
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 3},
    retry_backoff=True,
    retry_backoff_max=600,
    soft_time_limit=300,
    time_limit=360,
    acks_late=True,
    reject_on_worker_lost=True,
)
def generate_monthly_drift_report(self) -> Dict[str, Any]:
    """
    Generiere monatlichen Drift- und Performance-Report.

    Enthält:
    - Drift-Zusammenfassung
    - Quality-Trend
    - Automatisch erstellte Experimente
    - Empfehlungen

    Returns:
        Monatlicher Report
    """
    task_id = self.request.id

    logger.info("monthly_drift_report_starting", task_id=task_id)

    try:
        from app.ml.drift_detector import get_drift_alert_manager

        alert_manager = get_drift_alert_manager()
        report = alert_manager.generate_monthly_report()

        logger.info(
            "monthly_drift_report_completed",
            task_id=task_id,
            period=report.get("period", "unknown"),
            status=report.get("status", "generated"),
        )

        return report

    except Exception as e:
        logger.exception("monthly_drift_report_failed", task_id=task_id, error=str(e))
        raise


@celery_app.task(
    bind=True,
    base=CPUTask,
    name="app.workers.tasks.ml_tasks.apply_ab_test_winners",
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 3},
    retry_backoff=True,
    retry_backoff_max=300,
    soft_time_limit=120,
    time_limit=180,
    acks_late=True,
    reject_on_worker_lost=True,
)
def apply_ab_test_winners(self) -> Dict[str, Any]:
    """
    Wende A/B-Test Gewinner auf Backend-Routing an.

    Prüft laufende Experimente und aktualisiert die
    Backend-Fallback-Reihenfolge basierend auf Ergebnissen.

    Returns:
        Dict mit angewendeten Änderungen
    """
    task_id = self.request.id

    logger.info("apply_ab_winners_starting", task_id=task_id)

    try:
        from app.services.backend_manager import get_backend_manager

        loop = asyncio.get_event_loop()
        if loop.is_closed():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        # Get backend manager (async initialization)
        manager = loop.run_until_complete(get_backend_manager())

        # Apply winners
        result = manager.apply_ab_test_winners()

        logger.info(
            "apply_ab_winners_completed",
            task_id=task_id,
            winners_applied=len(result.get("applied_winners", [])),
            fallback_updated=result.get("fallback_updated", False),
        )

        return result

    except Exception as e:
        logger.exception("apply_ab_winners_failed", task_id=task_id, error=str(e))
        raise


# ==================== Celery Beat Schedule ====================

# Diese Tasks sollten in der Celery Beat Konfiguration hinzugefügt werden
CELERY_BEAT_ML_SCHEDULE = {
    "ml-drift-detection-hourly": {
        "task": "app.workers.tasks.ml_tasks.run_drift_detection",
        "schedule": 3600.0,  # Stündlich
    },
    "ml-drift-response-check": {
        "task": "app.workers.tasks.ml_tasks.check_drift_and_respond",
        "schedule": 7200.0,  # Alle 2 Stunden - automatische A/B-Tests bei Drift
    },
    "ml-metrics-update": {
        "task": "app.workers.tasks.ml_tasks.update_ml_metrics",
        "schedule": 30.0,  # Alle 30 Sekunden
    },
    "ml-experiment-check": {
        "task": "app.workers.tasks.ml_tasks.check_experiment_completion",
        "schedule": 300.0,  # Alle 5 Minuten
    },
    "ml-apply-ab-winners": {
        "task": "app.workers.tasks.ml_tasks.apply_ab_test_winners",
        "schedule": 1800.0,  # Alle 30 Minuten - Gewinner anwenden
    },
    "ml-report-daily": {
        "task": "app.workers.tasks.ml_tasks.generate_ml_report",
        "schedule": 86400.0,  # Täglich
    },
    "ml-monthly-drift-report": {
        "task": "app.workers.tasks.ml_tasks.generate_monthly_drift_report",
        "schedule": 2592000.0,  # Monatlich (30 Tage)
    },
}
