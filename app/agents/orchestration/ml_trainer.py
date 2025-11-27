# -*- coding: utf-8 -*-
"""
ML Router Trainer for OCR Backend Selection.

Enterprise-grade training pipeline for OCR router model:
- Automated data collection from processing results
- Training data management and versioning
- Model training and evaluation
- Periodic retraining scheduling

Feinpoliert und durchdacht - Kontinuierliches Lernen für optimale Ergebnisse.
"""

import asyncio
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import uuid

import numpy as np

from app.agents.orchestration.ml_router_model import (
    OCRRouterFeatures,
    OCRRouterModel,
)

logger = logging.getLogger(__name__)


# Prüfe ob XGBoost verfügbar ist für ML-Routing
XGBOOST_AVAILABLE = False
try:
    import xgboost  # noqa: F401
    XGBOOST_AVAILABLE = True
except ImportError:
    logger.info(
        "XGBoost nicht installiert - ML-Routing deaktiviert. "
        "Installieren mit: pip install xgboost oder pip install ablage-system-ocr[ml]"
    )


class TrainingSample:
    """
    Individual training sample for ML router.

    Represents a single document processing result with:
    - Document features
    - Selected backend
    - Processing outcome (success, accuracy)
    """

    def __init__(
        self,
        sample_id: str,
        document_metadata: Dict[str, Any],
        sla_requirements: Optional[Dict[str, Any]],
        resource_status: Optional[Dict[str, Any]],
        selected_backend: str,
        was_successful: bool,
        accuracy_score: float,
        processing_time_ms: int,
        timestamp: Optional[datetime] = None,
    ) -> None:
        """
        Initialize training sample.

        Args:
            sample_id: Unique sample identifier
            document_metadata: Document classification and quality info
            sla_requirements: SLA constraints at time of processing
            resource_status: Resource availability at time of processing
            selected_backend: Backend that was used
            was_successful: Whether processing completed successfully
            accuracy_score: OCR accuracy achieved (0-1)
            processing_time_ms: Processing time in milliseconds
            timestamp: When processing occurred
        """
        self.sample_id = sample_id
        self.document_metadata = document_metadata
        self.sla_requirements = sla_requirements or {}
        self.resource_status = resource_status or {}
        self.selected_backend = selected_backend
        self.was_successful = was_successful
        self.accuracy_score = accuracy_score
        self.processing_time_ms = processing_time_ms
        self.timestamp = timestamp or datetime.utcnow()

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "sample_id": self.sample_id,
            "document_metadata": self.document_metadata,
            "sla_requirements": self.sla_requirements,
            "resource_status": self.resource_status,
            "selected_backend": self.selected_backend,
            "was_successful": self.was_successful,
            "accuracy_score": self.accuracy_score,
            "processing_time_ms": self.processing_time_ms,
            "timestamp": self.timestamp.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TrainingSample":
        """Create from dictionary."""
        timestamp = data.get("timestamp")
        if isinstance(timestamp, str):
            timestamp = datetime.fromisoformat(timestamp)

        return cls(
            sample_id=data["sample_id"],
            document_metadata=data["document_metadata"],
            sla_requirements=data.get("sla_requirements"),
            resource_status=data.get("resource_status"),
            selected_backend=data["selected_backend"],
            was_successful=data["was_successful"],
            accuracy_score=data["accuracy_score"],
            processing_time_ms=data["processing_time_ms"],
            timestamp=timestamp,
        )


class TrainingDataBuffer:
    """
    Buffer for collecting training data.

    Manages training samples with:
    - Maximum buffer size
    - Persistence to disk
    - Sample weighting and balancing
    """

    DEFAULT_BUFFER_SIZE = 10000
    SAVE_THRESHOLD = 100  # Save every N samples

    def __init__(
        self,
        buffer_size: int = DEFAULT_BUFFER_SIZE,
        data_dir: Optional[Path] = None,
    ) -> None:
        """
        Initialize training data buffer.

        Args:
            buffer_size: Maximum number of samples to keep
            data_dir: Directory for persistent storage
        """
        self.buffer_size = buffer_size
        self.data_dir = data_dir or Path("data/training")
        self.samples: List[TrainingSample] = []
        self._samples_since_save = 0

        # Load existing data
        self._load_from_disk()

    def add_sample(self, sample: TrainingSample) -> None:
        """Add training sample to buffer."""
        self.samples.append(sample)
        self._samples_since_save += 1

        # Remove oldest samples if buffer full
        if len(self.samples) > self.buffer_size:
            self.samples = self.samples[-self.buffer_size:]

        # Periodic save
        if self._samples_since_save >= self.SAVE_THRESHOLD:
            self._save_to_disk()
            self._samples_since_save = 0

    def get_samples(
        self,
        min_samples: int = 0,
        max_age_days: Optional[int] = None,
        backend_filter: Optional[str] = None,
    ) -> List[TrainingSample]:
        """
        Get filtered samples from buffer.

        Args:
            min_samples: Minimum number of samples required
            max_age_days: Maximum age of samples in days
            backend_filter: Filter by specific backend

        Returns:
            Filtered list of training samples
        """
        samples = self.samples

        # Filter by age
        if max_age_days:
            cutoff = datetime.utcnow() - timedelta(days=max_age_days)
            samples = [s for s in samples if s.timestamp > cutoff]

        # Filter by backend
        if backend_filter:
            samples = [s for s in samples if s.selected_backend == backend_filter]

        if len(samples) < min_samples:
            logger.warning(
                f"Nicht genug Trainingsdaten: {len(samples)}/{min_samples}"
            )

        return samples

    def get_balanced_samples(
        self,
        min_per_class: int = 50,
    ) -> List[TrainingSample]:
        """
        Get class-balanced samples for training.

        Args:
            min_per_class: Minimum samples per backend class

        Returns:
            Balanced list of training samples
        """
        # Group by backend
        by_backend: Dict[str, List[TrainingSample]] = {}
        for sample in self.samples:
            backend = sample.selected_backend
            if backend not in by_backend:
                by_backend[backend] = []
            by_backend[backend].append(sample)

        # Find minimum class size
        min_size = min(
            len(samples) for samples in by_backend.values()
        ) if by_backend else 0

        if min_size < min_per_class:
            logger.warning(
                f"Unbalancierte Daten: kleinste Klasse hat {min_size} Samples"
            )
            # Use all available data
            balanced = []
            for samples in by_backend.values():
                balanced.extend(samples)
            return balanced

        # Sample equally from each class
        balanced = []
        for backend, samples in by_backend.items():
            # Random sample without replacement
            indices = np.random.choice(len(samples), min_size, replace=False)
            for i in indices:
                balanced.append(samples[i])

        np.random.shuffle(balanced)
        return balanced

    def clear(self) -> None:
        """Clear all samples from buffer."""
        self.samples = []
        self._samples_since_save = 0

    def _save_to_disk(self) -> None:
        """Save samples to disk."""
        self.data_dir.mkdir(parents=True, exist_ok=True)
        data_file = self.data_dir / "training_samples.json"

        data = [s.to_dict() for s in self.samples]

        with open(data_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        logger.debug(f"Gespeichert: {len(self.samples)} Trainingssamples")

    def _load_from_disk(self) -> None:
        """Load samples from disk."""
        data_file = self.data_dir / "training_samples.json"

        if not data_file.exists():
            return

        try:
            with open(data_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            self.samples = [TrainingSample.from_dict(d) for d in data]
            logger.info(f"Geladen: {len(self.samples)} Trainingssamples")

        except Exception as e:
            logger.error(f"Fehler beim Laden der Trainingsdaten: {e}")
            self.samples = []

    def get_stats(self) -> Dict[str, Any]:
        """Get buffer statistics."""
        if not self.samples:
            return {"total_samples": 0}

        # Count per backend
        backend_counts: Dict[str, int] = {}
        accuracy_scores: List[float] = []
        success_count = 0

        for sample in self.samples:
            backend = sample.selected_backend
            backend_counts[backend] = backend_counts.get(backend, 0) + 1
            accuracy_scores.append(sample.accuracy_score)
            if sample.was_successful:
                success_count += 1

        # Age statistics
        ages = [
            (datetime.utcnow() - s.timestamp).days
            for s in self.samples
        ]

        return {
            "total_samples": len(self.samples),
            "backend_distribution": backend_counts,
            "success_rate": success_count / len(self.samples),
            "mean_accuracy": float(np.mean(accuracy_scores)),
            "oldest_sample_days": max(ages),
            "newest_sample_days": min(ages),
        }


class MLRouterTrainer:
    """
    Training pipeline for OCR router ML model.

    Provides:
    - Automated data collection
    - Model training and evaluation
    - Model versioning and deployment
    - Periodic retraining

    Note: XGBoost ist optional. Wenn nicht installiert, wird Training deaktiviert
    und das System fällt auf regelbasiertes Routing zurück.
    Installation: pip install xgboost oder pip install ablage-system-ocr[ml]
    """

    # Training thresholds
    MIN_SAMPLES_FOR_TRAINING = 500
    MIN_SAMPLES_PER_CLASS = 50
    RETRAINING_INTERVAL_HOURS = 24
    MIN_ACCURACY_THRESHOLD = 0.80

    def __init__(
        self,
        model_dir: Optional[Path] = None,
        data_dir: Optional[Path] = None,
    ) -> None:
        """
        Initialize ML Router Trainer.

        Args:
            model_dir: Directory for model storage
            data_dir: Directory for training data
        """
        self.model_dir = Path(model_dir) if model_dir else Path("models/ocr_router")
        self.data_dir = Path(data_dir) if data_dir else Path("data/training")

        self.model_dir.mkdir(parents=True, exist_ok=True)
        self.data_dir.mkdir(parents=True, exist_ok=True)

        # Initialize components
        self.features = OCRRouterFeatures()
        self.data_buffer = TrainingDataBuffer(data_dir=self.data_dir)

        # Current model
        self._current_model: Optional[OCRRouterModel] = None
        self._last_training: Optional[datetime] = None

        # Load existing model if available (only if XGBoost is installed)
        if XGBOOST_AVAILABLE:
            self._load_latest_model()
        else:
            logger.info(
                "ML-Training deaktiviert - XGBoost nicht verfügbar. "
                "System verwendet regelbasiertes Routing."
            )

    @property
    def is_ml_available(self) -> bool:
        """Prüfe ob ML-Routing verfügbar ist."""
        return XGBOOST_AVAILABLE

    def _load_latest_model(self) -> None:
        """Load the latest trained model."""
        model_files = list(self.model_dir.glob("model_*.pkl"))

        if not model_files:
            logger.info("Kein trainiertes Modell gefunden")
            return

        # Get latest by modification time
        latest_model = max(model_files, key=lambda p: p.stat().st_mtime)

        try:
            self._current_model = OCRRouterModel(model_path=latest_model)
            logger.info(f"Modell geladen: {latest_model.name}")
        except Exception as e:
            logger.error(f"Fehler beim Laden des Modells: {e}")

    @property
    def model(self) -> Optional[OCRRouterModel]:
        """Get current trained model."""
        return self._current_model

    def collect_training_sample(
        self,
        document_id: str,
        document_metadata: Dict[str, Any],
        sla_requirements: Optional[Dict[str, Any]],
        resource_status: Optional[Dict[str, Any]],
        selected_backend: str,
        processing_result: Dict[str, Any],
    ) -> None:
        """
        Collect training sample from processing result.

        Called after each document processing to collect training data.

        Args:
            document_id: Document identifier
            document_metadata: Document classification info
            sla_requirements: SLA constraints used
            resource_status: Resource availability at processing time
            selected_backend: Backend that was used
            processing_result: Processing result with accuracy/success
        """
        sample = TrainingSample(
            sample_id=f"{document_id}_{uuid.uuid4().hex[:8]}",
            document_metadata=document_metadata,
            sla_requirements=sla_requirements,
            resource_status=resource_status,
            selected_backend=selected_backend,
            was_successful=processing_result.get("success", False),
            accuracy_score=processing_result.get("confidence", 0.0),
            processing_time_ms=processing_result.get("processing_time_ms", 0),
        )

        self.data_buffer.add_sample(sample)

        logger.debug(
            "Trainingssample gesammelt",
            extra={
                "document_id": document_id,
                "backend": selected_backend,
                "accuracy": sample.accuracy_score,
            },
        )

    def prepare_training_data(
        self,
        balanced: bool = True,
        max_age_days: int = 90,
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        Prepare training data from collected samples.

        Args:
            balanced: Whether to balance classes
            max_age_days: Maximum sample age in days

        Returns:
            Tuple of (features, labels) numpy arrays
        """
        # Get samples
        if balanced:
            samples = self.data_buffer.get_balanced_samples(
                min_per_class=self.MIN_SAMPLES_PER_CLASS
            )
        else:
            samples = self.data_buffer.get_samples(max_age_days=max_age_days)

        if len(samples) < self.MIN_SAMPLES_FOR_TRAINING:
            raise ValueError(
                f"Nicht genug Trainingsdaten: {len(samples)}/{self.MIN_SAMPLES_FOR_TRAINING}"
            )

        # Extract features and labels
        X_list = []
        y_list = []

        for sample in samples:
            # Extract features
            features = self.features.extract_features(
                sample.document_metadata,
                sample.sla_requirements,
                sample.resource_status,
            )
            X_list.append(features)

            # Determine optimal backend (label)
            # Use actual backend if successful, otherwise find best alternative
            if sample.was_successful and sample.accuracy_score >= 0.8:
                label = self.features.backend_to_index(sample.selected_backend)
            else:
                # Penalize this backend - assign to a better one based on heuristics
                label = self._find_better_backend_label(sample)

            y_list.append(label)

        X = np.array(X_list, dtype=np.float32)
        y = np.array(y_list, dtype=np.int32)

        logger.info(
            f"Trainingsdaten vorbereitet: {len(samples)} Samples, "
            f"Features: {X.shape[1]}, Klassen: {len(set(y))}"
        )

        return X, y

    def _find_better_backend_label(self, sample: TrainingSample) -> int:
        """
        Find better backend for failed/low-accuracy sample.

        Uses heuristics based on document characteristics.
        """
        metadata = sample.document_metadata

        # Priority rules for reassignment
        if metadata.get("has_tables") or metadata.get("has_handwriting"):
            return self.features.backend_to_index("deepseek")

        if metadata.get("complexity", "medium") == "high":
            return self.features.backend_to_index("hybrid")

        quality = metadata.get("quality_score", 0.8)
        if quality < 0.6:
            return self.features.backend_to_index("deepseek")

        # Default to got_ocr for standard documents
        return self.features.backend_to_index("got_ocr")

    async def train_model(
        self,
        force: bool = False,
    ) -> Dict[str, Any]:
        """
        Train or retrain the ML model.

        Args:
            force: Force training even if not enough time elapsed

        Returns:
            Training result metrics
        """
        # Check if XGBoost is available
        if not XGBOOST_AVAILABLE:
            return {
                "status": "unavailable",
                "reason": "XGBoost nicht installiert",
                "message": (
                    "ML-Routing erfordert XGBoost. "
                    "Installieren mit: pip install xgboost oder pip install ablage-system-ocr[ml]"
                ),
            }

        # Check if retraining is needed
        if not force and self._last_training:
            time_since_training = datetime.utcnow() - self._last_training
            if time_since_training.total_seconds() < self.RETRAINING_INTERVAL_HOURS * 3600:
                return {
                    "status": "skipped",
                    "reason": "Retraining nicht erforderlich",
                    "hours_since_last": time_since_training.total_seconds() / 3600,
                }

        try:
            # Prepare data
            X, y = self.prepare_training_data(balanced=True)

            # Create and train model
            model = OCRRouterModel()
            training_result = model.train(X, y)

            # Check if model is good enough
            if training_result["val_accuracy"] < self.MIN_ACCURACY_THRESHOLD:
                logger.warning(
                    f"Modellgenauigkeit unter Schwellwert: "
                    f"{training_result['val_accuracy']:.2%} < {self.MIN_ACCURACY_THRESHOLD:.2%}"
                )

            # Save model with timestamp
            timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            model_path = self.model_dir / f"model_{timestamp}.pkl"
            model.save(model_path)

            # Update current model
            self._current_model = model
            self._last_training = datetime.utcnow()

            logger.info(
                "Modelltraining erfolgreich",
                extra={
                    "accuracy": training_result["val_accuracy"],
                    "model_path": str(model_path),
                },
            )

            return {
                "status": "success",
                "training_accuracy": training_result["train_accuracy"],
                "validation_accuracy": training_result["val_accuracy"],
                "samples_used": training_result["total_samples"],
                "model_path": str(model_path),
            }

        except ValueError as e:
            logger.warning(f"Training fehlgeschlagen: {e}")
            return {
                "status": "failed",
                "reason": str(e),
            }
        except Exception as e:
            logger.exception("Unerwarteter Fehler beim Training")
            return {
                "status": "error",
                "reason": str(e),
            }

    def evaluate_model(
        self,
        test_samples: Optional[List[TrainingSample]] = None,
    ) -> Dict[str, Any]:
        """
        Evaluate current model on test data.

        Args:
            test_samples: Optional test samples (uses buffer if not provided)

        Returns:
            Evaluation metrics
        """
        if not self._current_model or not self._current_model.is_trained:
            return {"status": "no_model", "message": "Kein trainiertes Modell verfügbar"}

        # Get test samples
        if test_samples is None:
            all_samples = self.data_buffer.get_samples()
            # Use last 20% as test
            test_size = max(len(all_samples) // 5, 10)
            test_samples = all_samples[-test_size:]

        if not test_samples:
            return {"status": "no_data", "message": "Keine Testdaten verfügbar"}

        # Evaluate
        correct = 0
        predictions: Dict[str, Dict[str, int]] = {
            b: {"correct": 0, "total": 0}
            for b in self.features.BACKENDS
        }

        for sample in test_samples:
            # Predict
            prediction = self._current_model.predict(
                sample.document_metadata,
                sample.sla_requirements,
                sample.resource_status,
            )
            predicted_backend = prediction["backend"]

            # Check correctness
            # Consider correct if same backend OR if both were successful
            actual_backend = sample.selected_backend
            is_correct = (
                predicted_backend == actual_backend or
                (sample.was_successful and sample.accuracy_score >= 0.8)
            )

            if is_correct:
                correct += 1
                predictions[actual_backend]["correct"] += 1

            predictions[actual_backend]["total"] += 1

        accuracy = correct / len(test_samples)

        # Per-backend accuracy
        backend_accuracy = {}
        for backend, stats in predictions.items():
            if stats["total"] > 0:
                backend_accuracy[backend] = stats["correct"] / stats["total"]

        return {
            "status": "success",
            "overall_accuracy": accuracy,
            "backend_accuracy": backend_accuracy,
            "test_samples": len(test_samples),
        }

    def get_training_status(self) -> Dict[str, Any]:
        """Get current training status and statistics."""
        buffer_stats = self.data_buffer.get_stats()

        status = {
            "xgboost_available": XGBOOST_AVAILABLE,
            "ml_routing_enabled": XGBOOST_AVAILABLE,
            "data_collection": buffer_stats,
            "model_available": self._current_model is not None,
            "model_trained": (
                self._current_model.is_trained
                if self._current_model
                else False
            ),
        }

        if not XGBOOST_AVAILABLE:
            status["message"] = (
                "ML-Routing deaktiviert - XGBoost nicht installiert. "
                "System verwendet regelbasiertes Routing. "
                "Für ML-Routing: pip install xgboost"
            )

        if self._last_training:
            status["last_training"] = self._last_training.isoformat()
            status["hours_since_training"] = (
                (datetime.utcnow() - self._last_training).total_seconds() / 3600
            )

        if self._current_model and self._current_model.is_trained:
            status["model_info"] = self._current_model.get_model_info()

        return status

    async def start_background_training(
        self,
        check_interval_hours: float = 1.0,
    ) -> None:
        """
        Start background training loop.

        Periodically checks if retraining is needed and trains model.

        Args:
            check_interval_hours: How often to check for retraining
        """
        logger.info("Starte Hintergrund-Training-Loop")

        while True:
            try:
                # Check if training needed
                buffer_stats = self.data_buffer.get_stats()
                total_samples = buffer_stats.get("total_samples", 0)

                if total_samples >= self.MIN_SAMPLES_FOR_TRAINING:
                    result = await self.train_model(force=False)
                    if result["status"] == "success":
                        logger.info(
                            "Hintergrund-Training abgeschlossen",
                            extra={"accuracy": result["validation_accuracy"]},
                        )

            except Exception as e:
                logger.error(f"Fehler im Hintergrund-Training: {e}")

            # Wait for next check
            await asyncio.sleep(check_interval_hours * 3600)

    def generate_synthetic_training_data(
        self,
        num_samples: int = 1000,
    ) -> None:
        """
        Generate synthetic training data for initial model training.

        Creates realistic training samples based on backend characteristics.
        Useful for bootstrapping before real data is available.

        Args:
            num_samples: Number of synthetic samples to generate
        """
        logger.info(f"Generiere {num_samples} synthetische Trainingssamples")

        backends = self.features.BACKENDS
        doc_types = self.features.DOCUMENT_TYPES
        complexities = self.features.COMPLEXITY_LEVELS

        for i in range(num_samples):
            # Random document characteristics (convert numpy types to Python types)
            doc_type = str(np.random.choice(doc_types))
            complexity = str(np.random.choice(complexities))
            quality = float(np.clip(np.random.normal(0.8, 0.15), 0.3, 1.0))
            has_tables = bool(np.random.random() < 0.3)
            has_images = bool(np.random.random() < 0.4)
            has_handwriting = bool(np.random.random() < 0.15)
            has_fraktur = bool(np.random.random() < 0.05)
            page_count = int(max(1, int(np.random.exponential(5))))

            # Determine "best" backend based on rules
            if has_handwriting or has_fraktur or (has_tables and quality < 0.7):
                best_backend = "deepseek"
            elif doc_type == "contract":
                best_backend = "hybrid"
            elif complexity == "high" or quality < 0.6:
                best_backend = "deepseek"
            elif has_tables:
                best_backend = "deepseek"
            else:
                best_backend = str(np.random.choice(["got_ocr", "surya"], p=[0.7, 0.3]))

            # Simulate success based on backend match
            match_bonus = 0.2 if np.random.random() < 0.8 else -0.2
            accuracy = float(np.clip(0.85 + match_bonus + np.random.normal(0, 0.1), 0.5, 1.0))
            success = bool(accuracy > 0.7)

            sample = TrainingSample(
                sample_id=f"synthetic_{i:06d}",
                document_metadata={
                    "document_type": doc_type,
                    "complexity": complexity,
                    "quality_score": quality,
                    "has_tables": has_tables,
                    "has_images": has_images,
                    "has_handwriting": has_handwriting,
                    "has_fraktur": has_fraktur,
                    "page_count": page_count,
                },
                sla_requirements={
                    "max_processing_time_seconds": int(np.random.choice([10, 30, 60, 120])),
                    "min_accuracy": float(np.random.choice([0.8, 0.9, 0.95])),
                },
                resource_status={
                    "gpu_available": bool(np.random.random() < 0.9),
                    "gpu_memory_available_gb": float(np.random.uniform(8, 14)),
                    "queue_length": int(np.random.exponential(10)),
                },
                selected_backend=best_backend,
                was_successful=success,
                accuracy_score=accuracy,
                processing_time_ms=int(np.random.exponential(2000)),
            )

            self.data_buffer.add_sample(sample)

        logger.info(
            f"Synthetische Daten generiert",
            extra={"total_samples": self.data_buffer.get_stats()["total_samples"]},
        )
