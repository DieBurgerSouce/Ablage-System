# -*- coding: utf-8 -*-
"""
OCR Router Training Pipeline - Automatisiertes Training des ML-Routers.

Orchestriert:
- Datensammlung aus vergangenen OCR-Ergebnissen
- Feature-Extraktion und Aufbereitung
- XGBoost-Training mit Kreuzvalidierung
- Modell-Evaluation und Deployment
- A/B-Test-Integration für schrittweisen Rollout

Feinpoliert und durchdacht - Kontinuierliches Lernen für optimale Backend-Auswahl.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import structlog
from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.orchestration.ml_router_model import OCRRouterFeatures, OCRRouterModel
from app.agents.orchestration.ml_trainer import (
    MLRouterTrainer,
    TrainingSample,
    TrainingDataBuffer,
    XGBOOST_AVAILABLE,
)
from app.core.safe_errors import safe_error_log, safe_error_detail
from app.ml.ab_testing import (
    ABTestManager,
    get_ab_test_manager,
    Variant,
)

logger = structlog.get_logger(__name__)


@dataclass
class TrainingDataset:
    """Datensatz für ML-Training."""
    samples: List[TrainingSample]
    total_samples: int
    backend_distribution: Dict[str, int]
    date_range_days: int
    quality_metrics: Dict[str, float] = field(default_factory=dict)


@dataclass
class TrainingResult:
    """Ergebnis des Modelltrainings."""
    success: bool
    model_version: Optional[str] = None
    train_accuracy: float = 0.0
    validation_accuracy: float = 0.0
    total_samples: int = 0
    training_time_seconds: float = 0.0
    error_message: Optional[str] = None
    backend_accuracies: Dict[str, float] = field(default_factory=dict)


@dataclass
class EvaluationMetrics:
    """Evaluierungs-Metriken für Modell."""
    overall_accuracy: float
    backend_accuracies: Dict[str, float]
    precision_per_backend: Dict[str, float]
    recall_per_backend: Dict[str, float]
    f1_per_backend: Dict[str, float]
    confusion_matrix: Optional[List[List[int]]] = None
    test_samples: int = 0


@dataclass
class DeploymentResult:
    """Ergebnis des Modell-Deployments."""
    deployed: bool
    model_version: str
    deployment_method: str  # "direct" oder "ab_test"
    ab_test_id: Optional[str] = None
    message: str = ""


@dataclass
class ABTestConfig:
    """Konfiguration für A/B-Test des neuen Modells."""
    experiment_id: str
    test_name: str
    control_version: str
    treatment_version: str
    traffic_split: float  # Anteil für Treatment (0-1)
    min_samples_per_variant: int
    duration_days: int


class OCRRouterTrainingPipeline:
    """
    High-Level Training Pipeline für OCR Router ML-Modell.

    Orchestriert:
    - Datensammlung aus OCR-Ergebnissen
    - Training mit MLRouterTrainer
    - Evaluation und Vergleich mit aktuellem Modell
    - Deployment mit optionalem A/B-Test
    """

    # Deployment-Schwellwerte
    MIN_ACCURACY_IMPROVEMENT = 0.02  # 2% Verbesserung erforderlich
    MIN_DEPLOYMENT_ACCURACY = 0.80  # Mindestgenauigkeit für Deployment
    AB_TEST_TRAFFIC_SPLIT = 0.2  # 20% Traffic für neues Modell im A/B-Test
    AB_TEST_DURATION_DAYS = 7
    AB_TEST_MIN_SAMPLES = 200

    def __init__(
        self,
        model_dir: Optional[Path] = None,
        data_dir: Optional[Path] = None,
    ) -> None:
        """
        Initialize Training Pipeline.

        Args:
            model_dir: Directory for model storage
            data_dir: Directory for training data
        """
        self.model_dir = model_dir or Path("models/ocr_router")
        self.data_dir = data_dir or Path("/tmp/ablage_ml/training")

        # Initialize ML trainer
        self.trainer = MLRouterTrainer(
            model_dir=self.model_dir,
            data_dir=self.data_dir,
        )

        # A/B Test Manager
        self._ab_manager: Optional[ABTestManager] = None

        logger.info(
            "OCR Router Training Pipeline initialisiert",
            xgboost_available=XGBOOST_AVAILABLE,
        )

    @property
    def ab_manager(self) -> ABTestManager:
        """Get or create A/B test manager."""
        if self._ab_manager is None:
            self._ab_manager = get_ab_test_manager()
        return self._ab_manager

    async def collect_training_data(
        self,
        db: AsyncSession,
        since_days: int = 30,
        min_confidence: float = 0.7,
    ) -> TrainingDataset:
        """
        Sammle Trainingsdaten aus OCR-Ergebnissen.

        Args:
            db: Database session
            since_days: Daten der letzten N Tage sammeln
            min_confidence: Mindest-Confidence für Trainingsdaten

        Returns:
            TrainingDataset mit gesammelten Samples
        """
        logger.info(
            "Starte Trainingsdaten-Sammlung",
            since_days=since_days,
            min_confidence=min_confidence,
        )

        cutoff_date = datetime.now(timezone.utc) - timedelta(days=since_days)

        try:
            # Import hier um zirkuläre Imports zu vermeiden
            from app.db.models import OCRResult, Document

            # Query OCR results mit erfolgreichen Verarbeitungen
            query = (
                select(OCRResult)
                .join(Document, Document.id == OCRResult.document_id)
                .where(
                    and_(
                        OCRResult.created_at >= cutoff_date,
                        OCRResult.confidence_score >= min_confidence,
                        OCRResult.backend.isnot(None),
                        OCRResult.processing_time_ms.isnot(None),
                    )
                )
                .order_by(OCRResult.created_at.desc())
                .limit(10000)  # Max 10k Samples
            )

            result = await db.execute(query)
            ocr_results = result.scalars().all()

            if not ocr_results:
                logger.warning("Keine OCR-Ergebnisse gefunden für Training")
                return TrainingDataset(
                    samples=[],
                    total_samples=0,
                    backend_distribution={},
                    date_range_days=since_days,
                )

            # Konvertiere zu TrainingSamples
            samples = []
            backend_counts: Dict[str, int] = {}

            for ocr_result in ocr_results:
                # Extrahiere Metadaten aus dem verknuepften Dokument
                # (OCRResult selbst hat keine document_metadata-Spalte).
                doc = getattr(ocr_result, "document", None)
                metadata = (getattr(doc, "document_metadata", None) or {}) if doc is not None else {}
                document_metadata = {
                    "document_type": metadata.get("document_type", "other"),
                    "complexity": metadata.get("complexity", "medium"),
                    "quality_score": metadata.get("quality_score", 0.8),
                    "has_tables": metadata.get("has_tables", False),
                    "has_images": metadata.get("has_images", False),
                    "has_handwriting": metadata.get("has_handwriting", False),
                    "has_fraktur": metadata.get("has_fraktur", False),
                    "page_count": metadata.get("page_count", 1),
                }

                # SLA aus Metadaten oder Defaults
                sla_requirements = {
                    "max_processing_time_seconds": 60,
                    "min_accuracy": 0.8,
                    "is_critical": False,
                }

                # Resource Status (historisch nicht verfügbar, use defaults)
                resource_status = {
                    "gpu_available": True,
                    "gpu_memory_available_gb": 12.0,
                    "queue_length": 0,
                }

                sample = TrainingSample(
                    sample_id=str(ocr_result.id),
                    document_metadata=document_metadata,
                    sla_requirements=sla_requirements,
                    resource_status=resource_status,
                    selected_backend=ocr_result.backend,
                    was_successful=ocr_result.confidence_score >= min_confidence,
                    accuracy_score=ocr_result.confidence_score,
                    processing_time_ms=ocr_result.processing_time_ms or 0,
                    timestamp=ocr_result.created_at,
                )

                samples.append(sample)

                # Count backends
                backend = ocr_result.backend
                backend_counts[backend] = backend_counts.get(backend, 0) + 1

            logger.info(
                "Trainingsdaten gesammelt",
                total_samples=len(samples),
                backend_distribution=backend_counts,
            )

            return TrainingDataset(
                samples=samples,
                total_samples=len(samples),
                backend_distribution=backend_counts,
                date_range_days=since_days,
            )

        except Exception as e:
            logger.error("Fehler bei Trainingsdaten-Sammlung", **safe_error_log(e))
            raise

    async def train_model(
        self,
        dataset: TrainingDataset,
        force: bool = False,
    ) -> TrainingResult:
        """
        Trainiere Modell mit gesammelten Daten.

        Args:
            dataset: Trainingsdatensatz
            force: Erzwinge Training auch wenn Kriterien nicht erfüllt

        Returns:
            TrainingResult mit Metriken
        """
        if not XGBOOST_AVAILABLE:
            return TrainingResult(
                success=False,
                error_message="XGBoost nicht verfügbar. Installation: pip install xgboost",
            )

        if dataset.total_samples < self.trainer.MIN_SAMPLES_FOR_TRAINING and not force:
            return TrainingResult(
                success=False,
                error_message=f"Nicht genug Samples: {dataset.total_samples}/{self.trainer.MIN_SAMPLES_FOR_TRAINING}",
            )

        logger.info(
            "Starte Modelltraining",
            samples=dataset.total_samples,
            backends=list(dataset.backend_distribution.keys()),
        )

        start_time = datetime.now(timezone.utc)

        try:
            # Füge Samples zum Trainer-Buffer hinzu
            for sample in dataset.samples:
                self.trainer.data_buffer.add_sample(sample)

            # Training durchführen
            result = await self.trainer.train_model(force=True)

            training_time = (datetime.now(timezone.utc) - start_time).total_seconds()

            if result["status"] == "success":
                # Extrahiere Backend-Genauigkeiten
                model_info = self.trainer.model.get_model_info() if self.trainer.model else {}
                backend_stats = model_info.get("backend_stats", {})
                backend_accuracies = {
                    backend: stats.get("mean_accuracy", 0.0)
                    for backend, stats in backend_stats.items()
                }

                return TrainingResult(
                    success=True,
                    model_version=result.get("model_path", "unknown"),
                    train_accuracy=result["training_accuracy"],
                    validation_accuracy=result["validation_accuracy"],
                    total_samples=result["samples_used"],
                    training_time_seconds=training_time,
                    backend_accuracies=backend_accuracies,
                )
            else:
                return TrainingResult(
                    success=False,
                    error_message=result.get("reason", "Training fehlgeschlagen"),
                )

        except Exception as e:
            logger.error("Modelltraining fehlgeschlagen", **safe_error_log(e))
            return TrainingResult(
                success=False,
                error_message=safe_error_detail(e, "Training"),
            )

    async def evaluate_model(
        self,
        model: OCRRouterModel,
        test_data: Optional[List[TrainingSample]] = None,
    ) -> EvaluationMetrics:
        """
        Evaluiere Modell auf Testdaten.

        Args:
            model: Zu evaluierendes Modell
            test_data: Testdaten (verwendet Buffer wenn None)

        Returns:
            EvaluationMetrics mit detaillierten Metriken
        """
        if not model.is_trained:
            raise ValueError("Modell ist nicht trainiert")

        # Nutze test_data oder hole aus Buffer
        if test_data is None:
            all_samples = self.trainer.data_buffer.get_samples()
            test_size = max(len(all_samples) // 5, 10)
            test_data = all_samples[-test_size:]

        if not test_data:
            raise ValueError("Keine Testdaten verfügbar")

        logger.info("Evaluiere Modell", test_samples=len(test_data))

        # Pro-Backend Metriken
        backend_correct: Dict[str, int] = {}
        backend_total: Dict[str, int] = {}
        backend_true_positives: Dict[str, int] = {}
        backend_false_positives: Dict[str, int] = {}
        backend_false_negatives: Dict[str, int] = {}

        backends = model.features.BACKENDS

        for backend in backends:
            backend_correct[backend] = 0
            backend_total[backend] = 0
            backend_true_positives[backend] = 0
            backend_false_positives[backend] = 0
            backend_false_negatives[backend] = 0

        total_correct = 0

        for sample in test_data:
            try:
                # Vorhersage
                prediction = model.predict(
                    sample.document_metadata,
                    sample.sla_requirements,
                    sample.resource_status,
                )
                predicted_backend = prediction["backend"]
                actual_backend = sample.selected_backend

                # Normalisiere Backend-Namen
                predicted_backend = predicted_backend.lower()
                actual_backend = actual_backend.lower()

                # Gesamtgenauigkeit
                is_correct = predicted_backend == actual_backend
                if is_correct:
                    total_correct += 1

                # Pro-Backend Metriken
                backend_total[actual_backend] = backend_total.get(actual_backend, 0) + 1

                if is_correct:
                    backend_correct[actual_backend] = backend_correct.get(actual_backend, 0) + 1
                    backend_true_positives[actual_backend] = backend_true_positives.get(actual_backend, 0) + 1
                else:
                    backend_false_negatives[actual_backend] = backend_false_negatives.get(actual_backend, 0) + 1
                    backend_false_positives[predicted_backend] = backend_false_positives.get(predicted_backend, 0) + 1

            except Exception as e:
                logger.warning("Evaluation Fehler für Sample", **safe_error_log(e))
                continue

        # Berechne Metriken
        overall_accuracy = total_correct / len(test_data) if test_data else 0.0

        backend_accuracies = {}
        precision_per_backend = {}
        recall_per_backend = {}
        f1_per_backend = {}

        for backend in backends:
            total = backend_total.get(backend, 0)
            correct = backend_correct.get(backend, 0)
            tp = backend_true_positives.get(backend, 0)
            fp = backend_false_positives.get(backend, 0)
            fn = backend_false_negatives.get(backend, 0)

            # Accuracy
            backend_accuracies[backend] = correct / total if total > 0 else 0.0

            # Precision
            precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
            precision_per_backend[backend] = precision

            # Recall
            recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
            recall_per_backend[backend] = recall

            # F1
            if precision + recall > 0:
                f1_per_backend[backend] = 2 * (precision * recall) / (precision + recall)
            else:
                f1_per_backend[backend] = 0.0

        logger.info(
            "Evaluation abgeschlossen",
            overall_accuracy=overall_accuracy,
            test_samples=len(test_data),
        )

        return EvaluationMetrics(
            overall_accuracy=overall_accuracy,
            backend_accuracies=backend_accuracies,
            precision_per_backend=precision_per_backend,
            recall_per_backend=recall_per_backend,
            f1_per_backend=f1_per_backend,
            test_samples=len(test_data),
        )

    async def deploy_model(
        self,
        model: OCRRouterModel,
        metrics: EvaluationMetrics,
        use_ab_test: bool = True,
    ) -> DeploymentResult:
        """
        Deploye Modell mit optionalem A/B-Test.

        Args:
            model: Zu deployendes Modell
            metrics: Evaluation-Metriken
            use_ab_test: Nutze A/B-Test für schrittweisen Rollout

        Returns:
            DeploymentResult mit Deployment-Details
        """
        if metrics.overall_accuracy < self.MIN_DEPLOYMENT_ACCURACY:
            return DeploymentResult(
                deployed=False,
                model_version="none",
                deployment_method="rejected",
                message=f"Modell-Genauigkeit zu niedrig: {metrics.overall_accuracy:.2%} < {self.MIN_DEPLOYMENT_ACCURACY:.2%}",
            )

        # Vergleiche mit aktuellem Modell (falls vorhanden)
        current_model = self.trainer.model
        if current_model and current_model.is_trained:
            current_info = current_model.get_model_info()
            current_accuracy = current_info.get("validation_accuracy", 0.0)

            improvement = metrics.overall_accuracy - current_accuracy

            if improvement < self.MIN_ACCURACY_IMPROVEMENT and not use_ab_test:
                return DeploymentResult(
                    deployed=False,
                    model_version=current_info.get("model_version", "unknown"),
                    deployment_method="rejected",
                    message=f"Keine signifikante Verbesserung: {improvement:.2%} < {self.MIN_ACCURACY_IMPROVEMENT:.2%}",
                )

            logger.info(
                "Modell-Vergleich",
                current_accuracy=current_accuracy,
                new_accuracy=metrics.overall_accuracy,
                improvement=improvement,
            )

        # Speichere Modell
        model_version_info = model.save(bump_type="minor")
        model_version = f"v{model_version_info.version}"

        # Direktes Deployment oder A/B-Test?
        if use_ab_test and current_model and current_model.is_trained:
            # Erstelle A/B-Test
            ab_config = await self.setup_ab_test(
                control_version=current_model.get_model_info().get("model_version", "current"),
                treatment_version=model_version,
            )

            return DeploymentResult(
                deployed=True,
                model_version=model_version,
                deployment_method="ab_test",
                ab_test_id=ab_config.experiment_id,
                message=f"A/B-Test gestartet: {ab_config.traffic_split:.0%} Traffic für neues Modell",
            )
        else:
            # Direktes Deployment
            logger.info("Direktes Modell-Deployment", version=model_version)
            return DeploymentResult(
                deployed=True,
                model_version=model_version,
                deployment_method="direct",
                message=f"Modell direkt deployed: {model_version} (Genauigkeit: {metrics.overall_accuracy:.2%})",
            )

    async def setup_ab_test(
        self,
        control_version: str,
        treatment_version: str,
    ) -> ABTestConfig:
        """
        Erstelle A/B-Test für neues Modell.

        Args:
            control_version: Aktuelle Modellversion (Control)
            treatment_version: Neue Modellversion (Treatment)

        Returns:
            ABTestConfig mit Experiment-Details
        """
        test_name = f"ML Router: {control_version} vs {treatment_version}"

        experiment = self.ab_manager.create_experiment(
            name=test_name,
            description=f"A/B-Test für neues OCR Router Modell",
            variants=[
                {
                    "name": "control",
                    "description": f"Aktuelles Modell {control_version}",
                    "weight": 1.0 - self.AB_TEST_TRAFFIC_SPLIT,
                    "config": {"model_version": control_version},
                },
                {
                    "name": "treatment",
                    "description": f"Neues Modell {treatment_version}",
                    "weight": self.AB_TEST_TRAFFIC_SPLIT,
                    "config": {"model_version": treatment_version},
                },
            ],
            allocation_method="sticky",
            min_samples=self.AB_TEST_MIN_SAMPLES,
            duration_days=self.AB_TEST_DURATION_DAYS,
        )

        # Starte Experiment
        self.ab_manager.start_experiment(experiment.experiment_id)

        logger.info(
            "A/B-Test erstellt",
            experiment_id=experiment.experiment_id,
            control=control_version,
            treatment=treatment_version,
            traffic_split=self.AB_TEST_TRAFFIC_SPLIT,
        )

        return ABTestConfig(
            experiment_id=experiment.experiment_id,
            test_name=test_name,
            control_version=control_version,
            treatment_version=treatment_version,
            traffic_split=self.AB_TEST_TRAFFIC_SPLIT,
            min_samples_per_variant=self.AB_TEST_MIN_SAMPLES,
            duration_days=self.AB_TEST_DURATION_DAYS,
        )

    async def check_ab_test_results(
        self,
        experiment_id: str,
    ) -> Optional[str]:
        """
        Prüfe A/B-Test Ergebnisse und deploye Gewinner.

        Args:
            experiment_id: A/B-Test Experiment ID

        Returns:
            Gewinner-Version oder None
        """
        experiment = self.ab_manager.get_experiment(experiment_id)
        if not experiment:
            logger.warning("A/B-Test nicht gefunden", experiment_id=experiment_id)
            return None

        if not experiment.significance_reached:
            logger.info("A/B-Test noch nicht signifikant", experiment_id=experiment_id)
            return None

        winner_version = None
        if experiment.winner:
            for variant in experiment.variants:
                if variant.name == experiment.winner:
                    winner_version = variant.config.get("model_version")
                    break

        if winner_version:
            logger.info(
                "A/B-Test abgeschlossen",
                experiment_id=experiment_id,
                winner=winner_version,
            )

            # Schließe Experiment ab
            self.ab_manager.conclude_experiment(experiment_id)

        return winner_version

    async def full_training_pipeline(
        self,
        db: AsyncSession,
        since_days: int = 30,
        use_ab_test: bool = True,
    ) -> Dict[str, Any]:
        """
        Vollständige Training-Pipeline ausführen.

        Args:
            db: Database session
            since_days: Trainingsdaten der letzten N Tage
            use_ab_test: A/B-Test für Deployment nutzen

        Returns:
            Pipeline-Ergebnis mit allen Metriken
        """
        logger.info("Starte vollständige Training-Pipeline")

        result = {
            "status": "running",
            "steps": {},
        }

        try:
            # Schritt 1: Datensammlung
            dataset = await self.collect_training_data(db, since_days=since_days)
            result["steps"]["data_collection"] = {
                "status": "success",
                "samples": dataset.total_samples,
                "backends": dataset.backend_distribution,
            }

            if dataset.total_samples < self.trainer.MIN_SAMPLES_FOR_TRAINING:
                result["status"] = "insufficient_data"
                result["message"] = f"Nicht genug Trainingsdaten: {dataset.total_samples}"
                return result

            # Schritt 2: Training
            training_result = await self.train_model(dataset)
            result["steps"]["training"] = {
                "status": "success" if training_result.success else "failed",
                "accuracy": training_result.validation_accuracy,
                "samples": training_result.total_samples,
                "time_seconds": training_result.training_time_seconds,
            }

            if not training_result.success:
                result["status"] = "training_failed"
                result["error"] = training_result.error_message
                return result

            # Schritt 3: Evaluation
            model = self.trainer.model
            if not model:
                result["status"] = "error"
                result["error"] = "Modell nicht verfügbar nach Training"
                return result

            metrics = await self.evaluate_model(model)
            result["steps"]["evaluation"] = {
                "status": "success",
                "overall_accuracy": metrics.overall_accuracy,
                "backend_accuracies": metrics.backend_accuracies,
                "f1_scores": metrics.f1_per_backend,
            }

            # Schritt 4: Deployment
            deployment = await self.deploy_model(model, metrics, use_ab_test=use_ab_test)
            result["steps"]["deployment"] = {
                "status": "success" if deployment.deployed else "rejected",
                "method": deployment.deployment_method,
                "version": deployment.model_version,
                "message": deployment.message,
            }

            if deployment.ab_test_id:
                result["steps"]["deployment"]["ab_test_id"] = deployment.ab_test_id

            result["status"] = "success" if deployment.deployed else "rejected"
            result["final_accuracy"] = metrics.overall_accuracy

            logger.info(
                "Training-Pipeline abgeschlossen",
                status=result["status"],
                accuracy=metrics.overall_accuracy,
            )

            return result

        except Exception as e:
            logger.error("Training-Pipeline fehlgeschlagen", **safe_error_log(e))
            result["status"] = "error"
            result["error"] = safe_error_detail(e, "Pipeline")
            return result
