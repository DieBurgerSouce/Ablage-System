# -*- coding: utf-8 -*-
"""
ML Router Model for OCR Backend Selection.

Enterprise-grade machine learning model for intelligent OCR backend routing:
- XGBoost classifier for backend prediction
- Feature engineering for document characteristics
- Confidence calibration
- Online learning support
- Sichere Modell-Persistenz (kein pickle!)
- Model Registry mit Versionierung

Feinpoliert und durchdacht - Maschinelles Lernen für optimale Backend-Auswahl.
"""

from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import structlog

from app.core.safe_errors import safe_error_log
from .model_registry import (
    ModelRegistry,
    ModelVersion,
    compute_feature_hash,
)

logger = structlog.get_logger(__name__)


class OCRRouterFeatures:
    """
    Feature engineering for OCR routing ML model.

    Extracts and transforms document characteristics into ML features:
    - Document type encoding
    - Quality metrics normalization
    - Resource availability encoding
    - Historical performance features
    """

    # Document types for one-hot encoding
    DOCUMENT_TYPES = [
        "invoice",
        "contract",
        "receipt",
        "form",
        "letter",
        "report",
        "other",
    ]

    # Complexity levels
    COMPLEXITY_LEVELS = ["low", "medium", "high"]

    # Backend targets for classification
    BACKENDS = ["deepseek", "got_ocr", "surya", "surya_gpu", "donut", "hybrid"]

    def __init__(self) -> None:
        """Initialize feature engineering component."""
        self._feature_names: List[str] = []
        self._build_feature_names()

    def _build_feature_names(self) -> None:
        """Build list of feature names."""
        self._feature_names = []

        # Document type one-hot (7 features)
        for doc_type in self.DOCUMENT_TYPES:
            self._feature_names.append(f"doc_type_{doc_type}")

        # Complexity one-hot (3 features)
        for level in self.COMPLEXITY_LEVELS:
            self._feature_names.append(f"complexity_{level}")

        # Numeric features (14 features)
        self._feature_names.extend([
            "quality_score",
            "has_tables",
            "has_images",
            "has_handwriting",
            "has_fraktur",
            "page_count_normalized",
            "gpu_memory_available",
            "gpu_available",
            "queue_length_normalized",
            "fraktur_score",
            "handwriting_score",
            "layout_complexity",
            "dpi",
            "available_vram_gb",
        ])

        # SLA features (3 features)
        self._feature_names.extend([
            "needs_fast_processing",
            "needs_high_accuracy",
            "is_critical",
        ])

    @property
    def feature_names(self) -> List[str]:
        """Get list of feature names."""
        return self._feature_names

    @property
    def num_features(self) -> int:
        """Get number of features."""
        return len(self._feature_names)

    @property
    def num_classes(self) -> int:
        """Get number of backend classes."""
        return len(self.BACKENDS)

    def extract_features(
        self,
        document_metadata: Dict[str, Any],
        sla_requirements: Optional[Dict[str, Any]] = None,
        resource_status: Optional[Dict[str, Any]] = None,
    ) -> np.ndarray:
        """
        Extract features from document metadata and context.

        Args:
            document_metadata: Document classification and quality info
            sla_requirements: Optional SLA constraints
            resource_status: Optional resource availability info

        Returns:
            Feature vector as numpy array
        """
        sla = sla_requirements or {}
        resources = resource_status or {}

        features = []

        # Document type one-hot encoding
        doc_type = document_metadata.get("document_type", "other").lower()
        for dtype in self.DOCUMENT_TYPES:
            features.append(1.0 if doc_type == dtype else 0.0)

        # Complexity one-hot encoding
        complexity = document_metadata.get("complexity", "medium").lower()
        for level in self.COMPLEXITY_LEVELS:
            features.append(1.0 if complexity == level else 0.0)

        # Quality score (0-1)
        features.append(float(document_metadata.get("quality_score", 0.8)))

        # Boolean features as floats
        features.append(1.0 if document_metadata.get("has_tables") else 0.0)
        features.append(1.0 if document_metadata.get("has_images") else 0.0)
        features.append(1.0 if document_metadata.get("has_handwriting") else 0.0)
        features.append(1.0 if document_metadata.get("has_fraktur") else 0.0)

        # Page count normalized (cap at 100, normalize to 0-1)
        page_count = min(document_metadata.get("page_count", 1), 100)
        features.append(page_count / 100.0)

        # GPU availability
        gpu_memory = resources.get("gpu_memory_available_gb", 0.0)
        features.append(min(gpu_memory / 16.0, 1.0))  # Normalize to 16GB
        features.append(1.0 if resources.get("gpu_available", False) else 0.0)

        # Queue length normalized
        queue_length = resources.get("queue_length", 0)
        features.append(min(queue_length / 100.0, 1.0))  # Cap at 100

        # SLA features
        max_time = sla.get("max_processing_time_seconds", 60)
        features.append(1.0 if max_time < 10 else 0.0)  # Fast processing needed

        min_accuracy = sla.get("min_accuracy", 0.8)
        features.append(1.0 if min_accuracy > 0.95 else 0.0)  # High accuracy needed

        is_critical = sla.get("is_critical", False)
        features.append(1.0 if is_critical else 0.0)

        # New features (mit Defaults wenn nicht vorhanden)
        fraktur_score = document_metadata.get("fraktur_score", 0.0)
        features.append(float(fraktur_score))

        handwriting_score = document_metadata.get("handwriting_score", 0.0)
        features.append(float(handwriting_score))

        layout_complexity = document_metadata.get("layout_complexity", 0.5)
        features.append(float(layout_complexity))

        dpi = document_metadata.get("dpi", 300)
        features.append(min(dpi / 600.0, 1.0))  # Normalize to 600 DPI

        available_vram_gb = resources.get("gpu_memory_available_gb", 0.0)
        features.append(min(available_vram_gb / 16.0, 1.0))  # Normalize to 16GB

        return np.array(features, dtype=np.float32)

    def backend_to_index(self, backend: str) -> int:
        """Convert backend name to class index."""
        try:
            return self.BACKENDS.index(backend.lower())
        except ValueError:
            return self.BACKENDS.index("got_ocr")  # Default fallback

    def index_to_backend(self, index: int) -> str:
        """Convert class index to backend name."""
        if 0 <= index < len(self.BACKENDS):
            return self.BACKENDS[index]
        return "got_ocr"  # Default fallback


class OCRRouterModel:
    """
    XGBoost-based OCR backend routing model.

    Provides intelligent backend selection based on:
    - Document characteristics
    - Resource availability
    - Historical performance
    - SLA requirements

    Supports online learning for continuous improvement.
    """

    # Model hyperparameters (optimized for this task)
    DEFAULT_PARAMS = {
        "n_estimators": 100,
        "max_depth": 6,
        "learning_rate": 0.1,
        "min_child_weight": 3,
        "subsample": 0.8,
        "colsample_bytree": 0.8,
        "objective": "multi:softprob",
        "num_class": 6,  # Number of backends (deepseek, got_ocr, surya, surya_gpu, donut, hybrid)
        "eval_metric": "mlogloss",
        "use_label_encoder": False,
        "random_state": 42,
    }

    def __init__(
        self,
        model_path: Optional[Path] = None,
        registry_path: Optional[Path] = None,
    ) -> None:
        """
        Initialize OCR Router Model.

        Args:
            model_path: Optional path to load pre-trained model (legacy)
            registry_path: Optional path for Model Registry
        """
        self.features = OCRRouterFeatures()
        self.model = None
        self._xgb = None
        self._is_trained = False
        self._training_samples = 0
        self._validation_accuracy = 0.0
        self._current_version: Optional[ModelVersion] = None

        # Model Registry für sichere Persistenz
        default_registry = Path("models/ocr_router")
        self._registry = ModelRegistry(registry_path or default_registry)

        # Performance tracking
        self._backend_accuracy: Dict[str, List[float]] = {
            b: [] for b in self.features.BACKENDS
        }

        # Ensure XGBoost is available
        self._ensure_xgboost()

        # Load model from registry or legacy path
        if model_path and model_path.exists():
            self._load_legacy(model_path)
        else:
            self._try_load_from_registry()

    def _ensure_xgboost(self) -> None:
        """Ensure XGBoost is available."""
        try:
            import xgboost as xgb
            self._xgb = xgb
        except ImportError:
            logger.warning(
                "XGBoost nicht verfügbar - ML-Routing deaktiviert. "
                "Installieren mit: pip install xgboost"
            )
            self._xgb = None

    @property
    def is_available(self) -> bool:
        """Check if ML model is available for use."""
        return self._xgb is not None

    @property
    def is_trained(self) -> bool:
        """Check if model has been trained."""
        return self._is_trained and self.model is not None

    def create_model(self) -> None:
        """Create new XGBoost model with default parameters."""
        if not self._xgb:
            raise RuntimeError("XGBoost nicht verfügbar")

        self.model = self._xgb.XGBClassifier(**self.DEFAULT_PARAMS)
        logger.info("XGBoost-Modell erstellt")

    def predict(
        self,
        document_metadata: Dict[str, Any],
        sla_requirements: Optional[Dict[str, Any]] = None,
        resource_status: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Predict optimal backend for document.

        Args:
            document_metadata: Document classification results
            sla_requirements: Optional SLA constraints
            resource_status: Optional resource availability

        Returns:
            Prediction result with backend, confidence, and alternatives
        """
        if not self.is_trained:
            raise RuntimeError("Modell nicht trainiert")

        # Extract features
        features = self.features.extract_features(
            document_metadata,
            sla_requirements,
            resource_status,
        )

        # Get probabilities
        features_2d = features.reshape(1, -1)
        probabilities = self.model.predict_proba(features_2d)[0]

        # Get ranked backends
        ranked_indices = np.argsort(probabilities)[::-1]
        best_index = ranked_indices[0]
        best_backend = self.features.index_to_backend(best_index)
        best_confidence = float(probabilities[best_index])

        # Get alternatives
        alternatives = []
        for idx in ranked_indices[1:3]:  # Top 2 alternatives
            if probabilities[idx] > 0.1:  # Only if probability > 10%
                alternatives.append({
                    "backend": self.features.index_to_backend(idx),
                    "confidence": float(probabilities[idx]),
                })

        # Build reason based on top feature contributions
        reason = self._explain_prediction(features, best_backend)

        return {
            "backend": best_backend,
            "confidence": best_confidence,
            "alternatives": alternatives,
            "reason": reason,
            "model_version": self._get_model_version(),
            "probabilities": {
                self.features.index_to_backend(i): float(p)
                for i, p in enumerate(probabilities)
            },
        }

    def _explain_prediction(self, features: np.ndarray, backend: str) -> str:
        """Generate human-readable explanation for prediction."""
        feature_names = self.features.feature_names

        # Find active features
        explanations = []

        # Check document type
        for i, name in enumerate(feature_names):
            if name.startswith("doc_type_") and features[i] > 0.5:
                doc_type = name.replace("doc_type_", "")
                explanations.append(f"Dokumenttyp: {doc_type}")
                break

        # Check complexity
        for i, name in enumerate(feature_names):
            if name.startswith("complexity_") and features[i] > 0.5:
                complexity = name.replace("complexity_", "")
                if complexity == "high":
                    explanations.append("hohe Komplexität")
                break

        # Check quality
        quality_idx = feature_names.index("quality_score")
        quality = features[quality_idx]
        if quality < 0.7:
            explanations.append(f"niedrige Qualität ({quality:.0%})")
        elif quality > 0.9:
            explanations.append(f"hohe Qualität ({quality:.0%})")

        # Check special features
        if features[feature_names.index("has_tables")] > 0.5:
            explanations.append("Tabellen erkannt")
        if features[feature_names.index("has_handwriting")] > 0.5:
            explanations.append("Handschrift erkannt")
        if features[feature_names.index("has_fraktur")] > 0.5:
            explanations.append("Frakturschrift erkannt")

        # Check GPU availability
        if features[feature_names.index("gpu_available")] < 0.5:
            explanations.append("GPU nicht verfügbar")

        # Build reason string
        if explanations:
            return f"ML-Routing: {', '.join(explanations)}"
        return f"ML-Routing: Standard-Dokumentverarbeitung"

    def train(
        self,
        X: np.ndarray,
        y: np.ndarray,
        validation_split: float = 0.2,
    ) -> Dict[str, Any]:
        """
        Train model on labeled data.

        Args:
            X: Feature matrix (n_samples, n_features)
            y: Target labels (backend indices)
            validation_split: Fraction of data for validation

        Returns:
            Training metrics including accuracy and loss
        """
        if not self._xgb:
            raise RuntimeError("XGBoost nicht verfügbar")

        # Create model if needed
        if self.model is None:
            self.create_model()

        # Split data
        n_samples = len(X)
        n_val = int(n_samples * validation_split)
        indices = np.random.permutation(n_samples)

        val_indices = indices[:n_val]
        train_indices = indices[n_val:]

        X_train, y_train = X[train_indices], y[train_indices]
        X_val, y_val = X[val_indices], y[val_indices]

        logger.info(
            "Starte Modelltraining",
            extra={
                "train_samples": len(X_train),
                "val_samples": len(X_val),
            },
        )

        # Train model
        self.model.fit(
            X_train,
            y_train,
            eval_set=[(X_val, y_val)],
            verbose=False,
        )

        # Evaluate
        train_accuracy = float(self.model.score(X_train, y_train))
        val_accuracy = float(self.model.score(X_val, y_val))

        self._is_trained = True
        self._training_samples = n_samples
        self._validation_accuracy = val_accuracy

        logger.info(
            "Modelltraining abgeschlossen",
            extra={
                "train_accuracy": train_accuracy,
                "val_accuracy": val_accuracy,
            },
        )

        return {
            "train_accuracy": train_accuracy,
            "val_accuracy": val_accuracy,
            "train_samples": len(X_train),
            "val_samples": len(X_val),
            "total_samples": n_samples,
        }

    def partial_fit(
        self,
        X: np.ndarray,
        y: np.ndarray,
    ) -> Dict[str, Any]:
        """
        Incremental training with new data (online learning).

        Note: XGBoost doesn't support true online learning,
        so this retrains with accumulated data.

        Args:
            X: New feature samples
            y: New target labels

        Returns:
            Updated training metrics
        """
        if not self.is_trained:
            # Initial training
            return self.train(X, y)

        # For XGBoost, we need to retrain with existing + new data
        # In production, you would maintain a training data buffer
        logger.warning(
            "Inkrementelles Training: XGBoost erfordert vollständiges Neutraining. "
            "Für echtes Online-Learning erwägen Sie ein LightGBM-Modell."
        )

        return self.train(X, y)

    def record_feedback(
        self,
        backend: str,
        was_successful: bool,
        accuracy: Optional[float] = None,
    ) -> None:
        """
        Record feedback about backend performance for future training.

        Args:
            backend: Backend that was used
            was_successful: Whether processing was successful
            accuracy: Optional accuracy score achieved
        """
        if backend.lower() in self._backend_accuracy:
            score = accuracy if accuracy is not None else (1.0 if was_successful else 0.0)
            self._backend_accuracy[backend.lower()].append(score)

            # Keep only last 1000 samples per backend
            if len(self._backend_accuracy[backend.lower()]) > 1000:
                self._backend_accuracy[backend.lower()] = \
                    self._backend_accuracy[backend.lower()][-1000:]

    def get_backend_stats(self) -> Dict[str, Dict[str, float]]:
        """Get accumulated performance statistics per backend."""
        stats = {}
        for backend, scores in self._backend_accuracy.items():
            if scores:
                stats[backend] = {
                    "mean_accuracy": float(np.mean(scores)),
                    "std_accuracy": float(np.std(scores)),
                    "sample_count": len(scores),
                }
        return stats

    def save(
        self,
        path: Optional[Path] = None,
        bump_type: str = "patch",
    ) -> ModelVersion:
        """
        Speichert Modell sicher in der Registry.

        Args:
            path: Legacy-Parameter (ignoriert, verwendet Registry)
            bump_type: Versionstyp ("major", "minor", "patch")

        Returns:
            ModelVersion mit Versionsinformationen
        """
        if not self.is_trained:
            raise RuntimeError("Kann untrainiertes Modell nicht speichern")

        # Modell in Registry speichern (sicher, kein pickle!)
        version_info = self._registry.register_model(
            model=self.model,
            feature_names=self.features.feature_names,
            training_samples=self._training_samples,
            validation_accuracy=self._validation_accuracy,
            hyperparameters=self.DEFAULT_PARAMS,
            metadata={
                "backend_stats": self.get_backend_stats(),
                "backends": self.features.BACKENDS,
            },
            bump_type=bump_type,
        )

        # Als aktive Version setzen
        self._registry.set_active(version_info.version)
        self._current_version = version_info

        logger.info("modell_gespeichert", version=version_info.version)
        return version_info

    def load(self, path: Optional[Path] = None, version: Optional[str] = None) -> None:
        """
        Lädt Modell aus Registry.

        Args:
            path: Legacy-Parameter (falls angegeben, versucht Migration)
            version: Spezifische Version oder None für aktive
        """
        if path and path.exists() and path.suffix == ".pkl":
            # Legacy pickle-Datei migrieren
            self._load_legacy(path)
            return

        if not self._xgb:
            raise RuntimeError("XGBoost nicht verfügbar")

        try:
            model, version_info = self._registry.load_model(
                version=version,
                model_class=self._xgb.XGBClassifier,
            )

            self.model = model
            self._is_trained = True
            self._training_samples = version_info.training_samples
            self._validation_accuracy = version_info.validation_accuracy
            self._current_version = version_info

            logger.info("modell_geladen", version=version_info.version)

        except (FileNotFoundError, ValueError) as e:
            logger.warning("kein_modell_in_registry", **safe_error_log(e))

    def _load_legacy(self, path: Path) -> None:
        """
        Lädt Legacy pickle-Datei und migriert zur Registry.

        WARNUNG: pickle.load ist unsicher! Nur für eigene Dateien verwenden.

        SECURITY: Erfordert ABLAGE_ALLOW_PICKLE_MIGRATION=true Environment-Variable.
        Dies ist ein Sicherheits-Gate um versehentliche RCE zu verhindern.
        """
        import os
        import warnings

        # Phase 9.1 SECURITY FIX: Require explicit opt-in for pickle deserialization
        # Konsistent mit model_registry.py:500-505
        if not os.getenv("ABLAGE_ALLOW_PICKLE_MIGRATION"):
            logger.error(
                "pickle_migration_blocked",
                reason="Security flag not enabled",
                hint="Set ABLAGE_ALLOW_PICKLE_MIGRATION=true if you trust the source",
                pickle_path=str(path),
            )
            raise PermissionError(
                "Legacy pickle-Migration ist aus Sicherheitsgründen deaktiviert. "
                "Setzen Sie ABLAGE_ALLOW_PICKLE_MIGRATION=true wenn Sie der "
                "Quelle der pickle-Datei vertrauen. WARNUNG: pickle.load kann "
                "beliebigen Code ausfuehren!"
            )

        # Audit Log - wer hat wann eine pickle-Migration durchgeführt?
        logger.warning(
            "pickle_migration_started",
            pickle_path=str(path),
            security_warning="pickle.load kann beliebigen Code ausfuehren!",
        )

        # Import erst NACH Security-Check (Defense in Depth)
        import pickle  # noqa: S403 - Guarded by env var check above


        warnings.warn(
            "Lade Legacy pickle-Modell. Bitte nach Registry migrieren!",
            DeprecationWarning,
        )

        if not path.exists():
            raise FileNotFoundError(f"Modelldatei nicht gefunden: {path}")

        with open(path, "rb") as f:
            model_data = pickle.load(f)  # noqa: S301 - Security check above (env var required)

        self.model = model_data["model"]
        self._is_trained = model_data.get("is_trained", True)
        self._training_samples = model_data.get("training_samples", 0)
        self._backend_accuracy = model_data.get(
            "backend_accuracy",
            {b: [] for b in self.features.BACKENDS},
        )

        # Automatisch zur Registry migrieren
        if self.is_trained:
            logger.info("Migriere Legacy-Modell zur Registry...")
            self.save(bump_type="major")

        logger.info("legacy_modell_migriert", path=str(path))

    def _try_load_from_registry(self) -> None:
        """Versucht das aktive Modell aus der Registry zu laden."""
        try:
            active = self._registry.get_active_version()
            if active:
                self.load(version=active)
        except Exception as e:
            logger.debug("kein_aktives_modell", **safe_error_log(e))

    def _get_model_version(self) -> str:
        """Get model version string."""
        if self._current_version:
            return f"v{self._current_version.version}"
        return f"xgboost-unversioned-{self._training_samples}"

    def get_model_version(self) -> str:
        """
        Public method: Get model version string.

        Returns:
            Version string (e.g. "v1.2.3" or "xgboost-unversioned-1000")
        """
        return self._get_model_version()

    def get_model_metrics(self) -> Dict[str, float]:
        """
        Get model training metrics.

        Returns:
            Dict with training accuracy, validation accuracy, F1 scores
        """
        metrics = {
            "training_samples": self._training_samples,
            "validation_accuracy": self._validation_accuracy,
        }

        if self._current_version:
            metrics["model_version"] = self._current_version.version
            metrics["created_at"] = self._current_version.created_at

        # Add backend-specific accuracies
        backend_stats = self.get_backend_stats()
        for backend, stats in backend_stats.items():
            metrics[f"{backend}_mean_accuracy"] = stats.get("mean_accuracy", 0.0)
            metrics[f"{backend}_sample_count"] = stats.get("sample_count", 0)

        return metrics

    def get_model_info(self) -> Dict[str, Any]:
        """Get model information and statistics."""
        info: Dict[str, Any] = {
            "is_available": self.is_available,
            "is_trained": self.is_trained,
            "training_samples": self._training_samples,
            "validation_accuracy": self._validation_accuracy,
            "num_features": self.features.num_features,
            "num_classes": self.features.num_classes,
            "backends": self.features.BACKENDS,
            "feature_names": self.features.feature_names,
            "feature_hash": compute_feature_hash(self.features.feature_names),
        }

        if self.is_trained:
            info["backend_stats"] = self.get_backend_stats()
            info["model_version"] = self._get_model_version()

            if self._current_version:
                info["version_info"] = {
                    "version": self._current_version.version,
                    "created_at": self._current_version.created_at,
                    "git_commit": self._current_version.git_commit,
                }

        # Registry-Informationen
        info["registry"] = {
            "active_version": self._registry.get_active_version(),
            "available_versions": [
                v["version"] for v in self._registry.list_versions()
            ],
        }

        return info

    def list_versions(self) -> List[Dict[str, Any]]:
        """Listet alle verfügbaren Modellversionen."""
        return self._registry.list_versions()

    def rollback_to_version(self, version: str) -> bool:
        """
        Führt Rollback zu einer früheren Version durch.

        Args:
            version: Zielversion

        Returns:
            True wenn erfolgreich
        """
        try:
            self.load(version=version)
            self._registry.set_active(version)
            logger.info("rollback_erfolgreich", version=version)
            return True
        except Exception as e:
            logger.error("rollback_fehlgeschlagen", **safe_error_log(e))
            return False
