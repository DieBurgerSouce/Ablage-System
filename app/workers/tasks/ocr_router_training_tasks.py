# -*- coding: utf-8 -*-
"""
Celery Tasks für OCR Router Training.

Automatisierte Tasks für:
- Periodisches Modelltraining
- A/B-Test Evaluation
- Modell-Deployment

Feinpoliert und durchdacht - Automatisierung für kontinuierliche Verbesserung.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict

import structlog
from celery import Task

from app.workers.celery_app import celery_app
from app.core.safe_errors import safe_error_log, safe_error_detail
from app.ml.ocr_router_trainer import OCRRouterTrainingPipeline

logger = structlog.get_logger(__name__)


class OCRRouterTrainingTask(Task):
    """
    Base Task für OCR Router Training mit gemeinsamer Initialisierung.
    """
    _pipeline: OCRRouterTrainingPipeline = None

    @property
    def pipeline(self) -> OCRRouterTrainingPipeline:
        """Lazy-load Training Pipeline."""
        if self._pipeline is None:
            self._pipeline = OCRRouterTrainingPipeline()
        return self._pipeline


@celery_app.task(
    name="ocr_router.collect_and_train",
    base=OCRRouterTrainingTask,
    bind=True,
    max_retries=3,
    default_retry_delay=3600,  # 1 Stunde Retry-Delay
)
def collect_and_train_task(
    self: OCRRouterTrainingTask,
    min_samples: int = 100,
    since_days: int = 30,
    use_ab_test: bool = True,
) -> Dict[str, Any]:
    """
    Sammelt Daten und trainiert den OCR-Router neu.

    Args:
        min_samples: Minimale Anzahl Samples erforderlich
        since_days: Daten der letzten N Tage sammeln
        use_ab_test: A/B-Test für Deployment nutzen

    Returns:
        Dict mit Training-Ergebnis
    """
    logger.info(
        "Starte OCR Router Training Task",
        min_samples=min_samples,
        since_days=since_days,
        use_ab_test=use_ab_test,
    )

    try:
        # Asynchrone DB-Session für Datensammlung
        import asyncio
        from app.db.session import get_async_session

        async def run_pipeline() -> Dict[str, Any]:
            async with get_async_session() as db:
                result = await self.pipeline.full_training_pipeline(
                    db=db,
                    since_days=since_days,
                    use_ab_test=use_ab_test,
                )
                return result

        # Run in event loop
        result = asyncio.run(run_pipeline())

        # Prüfe Ergebnis
        if result["status"] == "success":
            logger.info(
                "OCR Router Training erfolgreich",
                accuracy=result.get("final_accuracy"),
                deployment=result["steps"].get("deployment", {}).get("method"),
            )
        elif result["status"] == "insufficient_data":
            logger.warning(
                "OCR Router Training übersprungen - nicht genug Daten",
                samples=result.get("steps", {}).get("data_collection", {}).get("samples", 0),
            )
        else:
            logger.warning(
                "OCR Router Training fehlgeschlagen",
                status=result["status"],
                error=result.get("error"),
            )

        return result

    except Exception as exc:
        logger.error("OCR Router Training Task fehlgeschlagen", **safe_error_log(exc))

        # Retry bei bestimmten Fehlern
        if "database" in str(exc).lower() or "connection" in str(exc).lower():
            raise self.retry(exc=exc)

        return {
            "status": "error",
            "error": safe_error_detail(exc, "Training Task"),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }


@celery_app.task(
    name="ocr_router.evaluate_ab_test",
    base=OCRRouterTrainingTask,
    bind=True,
    max_retries=3,
)
def evaluate_ab_test_task(
    self: OCRRouterTrainingTask,
    test_id: str,
) -> Dict[str, Any]:
    """
    Evaluiert einen laufenden A/B-Test des OCR-Routers.

    Prüft ob statistische Signifikanz erreicht wurde und
    deployt automatisch den Gewinner.

    Args:
        test_id: A/B-Test Experiment ID

    Returns:
        Dict mit Evaluation-Ergebnis
    """
    logger.info("Starte A/B-Test Evaluation", test_id=test_id)

    try:
        import asyncio

        async def check_test() -> Dict[str, Any]:
            winner = await self.pipeline.check_ab_test_results(test_id)

            if winner:
                return {
                    "status": "completed",
                    "test_id": test_id,
                    "winner": winner,
                    "message": f"A/B-Test abgeschlossen, Gewinner: {winner}",
                }
            else:
                # Hole Experiment-Status
                experiment = self.pipeline.ab_manager.get_experiment(test_id)
                if not experiment:
                    return {
                        "status": "not_found",
                        "test_id": test_id,
                        "message": "A/B-Test nicht gefunden",
                    }

                total_samples = sum(v.samples for v in experiment.variants)
                return {
                    "status": "running",
                    "test_id": test_id,
                    "samples": total_samples,
                    "significance_reached": experiment.significance_reached,
                    "message": "A/B-Test läuft noch",
                }

        result = asyncio.run(check_test())

        logger.info(
            "A/B-Test Evaluation abgeschlossen",
            test_id=test_id,
            status=result["status"],
        )

        return result

    except Exception as exc:
        logger.error("A/B-Test Evaluation fehlgeschlagen", **safe_error_log(exc))
        return {
            "status": "error",
            "test_id": test_id,
            "error": safe_error_detail(exc, "A/B-Test Evaluation"),
        }


@celery_app.task(name="ocr_router.check_all_ab_tests")
def check_all_ab_tests_task() -> Dict[str, Any]:
    """
    Prüft alle laufenden A/B-Tests und wendet Gewinner an.

    Returns:
        Dict mit Ergebnissen aller geprüften Tests
    """
    logger.info("Prüfe alle laufenden A/B-Tests")

    try:
        from app.ml.ab_testing import get_ab_test_manager

        ab_manager = get_ab_test_manager()

        # Prüfe und wende Gewinner an
        winners = ab_manager.check_and_apply_winners(
            auto_conclude=True,
            min_improvement_percent=2.0,  # 2% Mindestverbesserung
        )

        if winners:
            logger.info(
                "A/B-Test Gewinner gefunden",
                count=len(winners),
                experiments=[w["experiment_id"] for w in winners],
            )
        else:
            logger.debug("Keine abgeschlossenen A/B-Tests gefunden")

        return {
            "status": "success",
            "winners_found": len(winners),
            "winners": winners,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    except Exception as exc:
        logger.error("A/B-Test Check fehlgeschlagen", **safe_error_log(exc))
        return {
            "status": "error",
            "error": safe_error_detail(exc, "A/B-Test Check"),
        }


@celery_app.task(name="ocr_router.generate_synthetic_data")
def generate_synthetic_data_task(num_samples: int = 1000) -> Dict[str, Any]:
    """
    Generiert synthetische Trainingsdaten für Bootstrapping.

    Args:
        num_samples: Anzahl zu generierender Samples

    Returns:
        Dict mit Ergebnis
    """
    logger.info("Generiere synthetische Trainingsdaten", num_samples=num_samples)

    try:
        from app.agents.orchestration.ml_trainer import MLRouterTrainer

        trainer = MLRouterTrainer()
        trainer.generate_synthetic_training_data(num_samples=num_samples)

        buffer_stats = trainer.data_buffer.get_stats()

        logger.info(
            "Synthetische Daten generiert",
            generated=num_samples,
            total_samples=buffer_stats["total_samples"],
        )

        return {
            "status": "success",
            "generated_samples": num_samples,
            "total_samples": buffer_stats["total_samples"],
            "backend_distribution": buffer_stats["backend_distribution"],
        }

    except Exception as exc:
        logger.error("Synthetische Daten-Generierung fehlgeschlagen", **safe_error_log(exc))
        return {
            "status": "error",
            "error": safe_error_detail(exc, "Synthetic Data"),
        }


# Periodic Task Setup (via Celery Beat)
@celery_app.on_after_finalize.connect
def setup_periodic_tasks(sender: Any, **kwargs: Any) -> None:
    """
    Setup periodic tasks für automatisches Training.

    Wird beim Start von Celery Beat ausgeführt.
    """
    # Tägliches Training um 2 Uhr nachts
    sender.add_periodic_task(
        86400.0,  # 24 Stunden
        collect_and_train_task.s(
            min_samples=500,
            since_days=30,
            use_ab_test=True,
        ),
        name="daily_ocr_router_training",
    )

    # Stündliches A/B-Test Check
    sender.add_periodic_task(
        3600.0,  # 1 Stunde
        check_all_ab_tests_task.s(),
        name="hourly_ab_test_check",
    )

    logger.info("OCR Router Training - Periodic Tasks registriert")
