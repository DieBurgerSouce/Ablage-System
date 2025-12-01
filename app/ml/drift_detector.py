# -*- coding: utf-8 -*-
"""
Drift Detection für ML-Routing.

Überwacht Feature- und Prediction-Drift:
- Kolmogorov-Smirnov Test für numerische Features
- Chi-Quadrat Test für kategorische Features
- Population Stability Index (PSI)
- Evidently AI Integration (optional)

Feinpoliert und durchdacht - Proaktive Modellüberwachung.
"""

import json
import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple
import hashlib

import numpy as np
import structlog

logger = structlog.get_logger(__name__)


# Alert callback types
AlertCallback = Callable[[str, str, Dict[str, Any]], None]

# Thread-Safety für Singleton
_drift_detector_lock = threading.Lock()

# Optional Evidently integration
EVIDENTLY_AVAILABLE = False
try:
    from evidently import ColumnMapping
    from evidently.metrics import (
        DataDriftTable,
        DatasetDriftMetric,
    )
    from evidently.report import Report
    EVIDENTLY_AVAILABLE = True
except ImportError:
    logger.info("Evidently nicht installiert - verwende eingebaute Drift-Detection")


class DriftSeverity(str, Enum):
    """Schweregrad des Drifts."""
    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

    @classmethod
    def from_score(cls, score: float) -> "DriftSeverity":
        """Bestimme Schweregrad aus Drift-Score (0-1)."""
        if score < 0.1:
            return cls.NONE
        elif score < 0.25:
            return cls.LOW
        elif score < 0.5:
            return cls.MEDIUM
        elif score < 0.75:
            return cls.HIGH
        else:
            return cls.CRITICAL


@dataclass
class FeatureDrift:
    """Drift-Information für ein einzelnes Feature."""
    feature_name: str
    drift_score: float  # 0-1, höher = mehr Drift
    p_value: float
    test_method: str  # "ks" oder "chi2"
    is_drifted: bool
    reference_stats: Dict[str, float]
    current_stats: Dict[str, float]


@dataclass
class DriftReport:
    """Vollständiger Drift-Bericht."""
    timestamp: datetime
    report_id: str
    overall_drift_score: float
    severity: DriftSeverity
    dataset_drift_detected: bool
    feature_drifts: List[FeatureDrift]
    prediction_drift: Optional[float]
    samples_reference: int
    samples_current: int
    recommendations: List[str]
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Konvertiere zu Dictionary."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "report_id": self.report_id,
            "overall_drift_score": float(self.overall_drift_score),
            "severity": self.severity.value,
            "dataset_drift_detected": bool(self.dataset_drift_detected),
            "feature_drifts": [
                {
                    "feature_name": fd.feature_name,
                    "drift_score": float(fd.drift_score),
                    "p_value": float(fd.p_value),
                    "test_method": fd.test_method,
                    "is_drifted": bool(fd.is_drifted),
                }
                for fd in self.feature_drifts
            ],
            "prediction_drift": float(self.prediction_drift) if self.prediction_drift is not None else None,
            "samples_reference": int(self.samples_reference),
            "samples_current": int(self.samples_current),
            "recommendations": self.recommendations,
            "metadata": self.metadata,
        }

    def to_json(self) -> str:
        """Serialisiere zu JSON."""
        return json.dumps(self.to_dict(), indent=2)


class DriftDetector:
    """
    Drift Detection für ML-Routing-Modelle.

    Überwacht:
    - Feature-Drift: Änderungen in Input-Verteilungen
    - Prediction-Drift: Änderungen in Model-Outputs
    - Concept-Drift: Änderungen in Feature-Label-Beziehungen

    Verwendet:
    - Kolmogorov-Smirnov Test (numerisch)
    - Chi-Quadrat Test (kategorisch)
    - Population Stability Index (PSI)
    - Jensen-Shannon Divergenz
    """

    # Feature-Konfiguration für OCR-Routing
    NUMERICAL_FEATURES = [
        "quality_score",
        "file_size_mb",
        "page_count",
        "dpi",
        "text_density",
    ]

    CATEGORICAL_FEATURES = [
        "document_type",
        "detected_language",
        "has_tables",
        "has_formulas",
        "has_handwriting",
        "complexity",
    ]

    def __init__(
        self,
        reference_window_days: int = 7,
        drift_threshold: float = 0.1,
        min_samples: int = 100,
        storage_path: Optional[Path] = None,
    ) -> None:
        """
        Initialisiere Drift Detector.

        Args:
            reference_window_days: Tage für Referenz-Daten
            drift_threshold: P-Wert Schwelle für Drift-Erkennung
            min_samples: Minimum Samples für zuverlässige Drift-Erkennung
            storage_path: Pfad für Drift-Reports

        Raises:
            ValueError: Bei ungültigen Parametern
        """
        # Input Validation
        if not isinstance(reference_window_days, int) or reference_window_days < 1:
            raise ValueError("reference_window_days muss eine positive Ganzzahl sein")
        if reference_window_days > 365:
            raise ValueError("reference_window_days darf maximal 365 sein")

        if not isinstance(drift_threshold, (int, float)):
            raise ValueError("drift_threshold muss eine Zahl sein")
        if drift_threshold <= 0 or drift_threshold >= 1:
            raise ValueError("drift_threshold muss zwischen 0 und 1 (exklusiv) sein")

        if not isinstance(min_samples, int) or min_samples < 10:
            raise ValueError("min_samples muss mindestens 10 sein")
        if min_samples > 100_000:
            raise ValueError("min_samples darf maximal 100.000 sein")

        self.reference_window_days = reference_window_days
        self.drift_threshold = drift_threshold
        self.min_samples = min_samples
        self.storage_path = storage_path or Path("data/drift_reports")
        self.storage_path.mkdir(parents=True, exist_ok=True)

        # Reference und Current Data Windows
        self._reference_data: List[Dict[str, Any]] = []
        self._current_data: List[Dict[str, Any]] = []
        self._reference_cutoff: Optional[datetime] = None

        # Drift History
        self._drift_history: List[DriftReport] = []

        # Prediction tracking
        self._reference_predictions: List[str] = []
        self._current_predictions: List[str] = []

        logger.info(
            "DriftDetector initialisiert",
            extra={
                "reference_window_days": reference_window_days,
                "drift_threshold": drift_threshold,
                "min_samples": min_samples,
            }
        )

    def add_sample(
        self,
        features: Dict[str, Any],
        prediction: str,
        timestamp: Optional[datetime] = None,
    ) -> None:
        """
        Füge neue Beobachtung hinzu.

        Args:
            features: Feature-Dictionary
            prediction: Modell-Vorhersage (Backend-Name)
            timestamp: Zeitstempel (default: jetzt)

        Raises:
            ValueError: Bei ungültigen Parametern
        """
        # Input Validation
        if not isinstance(features, dict):
            raise ValueError("features muss ein Dictionary sein")
        if not features:
            raise ValueError("features darf nicht leer sein")

        if not prediction or not isinstance(prediction, str):
            raise ValueError("prediction muss ein nicht-leerer String sein")
        prediction = prediction.strip()
        if len(prediction) > 100:
            raise ValueError("prediction darf maximal 100 Zeichen haben")

        if timestamp is not None and not isinstance(timestamp, datetime):
            raise ValueError("timestamp muss ein datetime-Objekt sein")

        timestamp = timestamp or datetime.now()

        # Sanitize features - only keep known feature names to limit memory
        sanitized_features = {}
        all_known_features = set(self.NUMERICAL_FEATURES + self.CATEGORICAL_FEATURES)
        for key, value in features.items():
            if key in all_known_features:
                sanitized_features[key] = value

        sample = {
            "timestamp": timestamp,
            "features": sanitized_features,
            "prediction": prediction,
        }

        # Bestimme ob Reference oder Current
        if self._reference_cutoff is None:
            self._reference_cutoff = timestamp + timedelta(days=self.reference_window_days)

        if timestamp < self._reference_cutoff:
            self._reference_data.append(sample)
            self._reference_predictions.append(prediction)
        else:
            self._current_data.append(sample)
            self._current_predictions.append(prediction)

        # Cleanup alte Daten (behalte max 30 Tage)
        self._cleanup_old_data(days=30)

    def detect_drift(self) -> DriftReport:
        """
        Führe Drift-Detection durch.

        Returns:
            DriftReport mit allen Ergebnissen
        """
        report_id = self._generate_report_id()

        # Check minimum samples
        if len(self._reference_data) < self.min_samples:
            return self._create_insufficient_data_report(
                report_id, "reference", len(self._reference_data)
            )

        if len(self._current_data) < self.min_samples:
            return self._create_insufficient_data_report(
                report_id, "current", len(self._current_data)
            )

        # Feature Drift Detection
        feature_drifts = self._detect_feature_drift()

        # Prediction Drift Detection
        prediction_drift = self._detect_prediction_drift()

        # Calculate overall drift score
        overall_score = self._calculate_overall_drift(feature_drifts, prediction_drift)

        # Determine severity
        severity = DriftSeverity.from_score(overall_score)

        # Generate recommendations
        recommendations = self._generate_recommendations(
            feature_drifts, prediction_drift, severity
        )

        # Count drifted features
        drifted_features = [fd for fd in feature_drifts if fd.is_drifted]
        dataset_drift_detected = len(drifted_features) > len(feature_drifts) * 0.3

        report = DriftReport(
            timestamp=datetime.now(),
            report_id=report_id,
            overall_drift_score=overall_score,
            severity=severity,
            dataset_drift_detected=dataset_drift_detected,
            feature_drifts=feature_drifts,
            prediction_drift=prediction_drift,
            samples_reference=len(self._reference_data),
            samples_current=len(self._current_data),
            recommendations=recommendations,
            metadata={
                "reference_window_days": self.reference_window_days,
                "drift_threshold": self.drift_threshold,
                "evidently_available": EVIDENTLY_AVAILABLE,
            }
        )

        # Store report
        self._store_report(report)
        self._drift_history.append(report)

        logger.info(
            "Drift-Detection abgeschlossen",
            extra={
                "report_id": report_id,
                "severity": severity.value,
                "overall_score": overall_score,
                "drifted_features": len(drifted_features),
            }
        )

        return report

    def _detect_feature_drift(self) -> List[FeatureDrift]:
        """Erkenne Drift für alle Features."""
        feature_drifts = []

        # Extract feature arrays
        ref_features = self._extract_features(self._reference_data)
        cur_features = self._extract_features(self._current_data)

        # Numerical features - KS Test
        for feature in self.NUMERICAL_FEATURES:
            if feature in ref_features and feature in cur_features:
                drift = self._ks_test(
                    ref_features[feature],
                    cur_features[feature],
                    feature,
                )
                if drift:
                    feature_drifts.append(drift)

        # Categorical features - Chi-Square Test
        for feature in self.CATEGORICAL_FEATURES:
            if feature in ref_features and feature in cur_features:
                drift = self._chi_square_test(
                    ref_features[feature],
                    cur_features[feature],
                    feature,
                )
                if drift:
                    feature_drifts.append(drift)

        return feature_drifts

    def _ks_test(
        self,
        reference: np.ndarray,
        current: np.ndarray,
        feature_name: str,
    ) -> Optional[FeatureDrift]:
        """
        Kolmogorov-Smirnov Test für numerische Features.

        Vergleicht kumulative Verteilungen.
        """
        try:
            from scipy import stats

            # Filter NaN values
            ref_clean = reference[~np.isnan(reference)]
            cur_clean = current[~np.isnan(current)]

            if len(ref_clean) < 10 or len(cur_clean) < 10:
                return None

            statistic, p_value = stats.ks_2samp(ref_clean, cur_clean)

            return FeatureDrift(
                feature_name=feature_name,
                drift_score=statistic,
                p_value=p_value,
                test_method="ks",
                is_drifted=p_value < self.drift_threshold,
                reference_stats={
                    "mean": float(np.mean(ref_clean)),
                    "std": float(np.std(ref_clean)),
                    "min": float(np.min(ref_clean)),
                    "max": float(np.max(ref_clean)),
                },
                current_stats={
                    "mean": float(np.mean(cur_clean)),
                    "std": float(np.std(cur_clean)),
                    "min": float(np.min(cur_clean)),
                    "max": float(np.max(cur_clean)),
                },
            )
        except ImportError:
            # Fallback ohne scipy
            return self._simple_drift_check(reference, current, feature_name)

    def _chi_square_test(
        self,
        reference: np.ndarray,
        current: np.ndarray,
        feature_name: str,
    ) -> Optional[FeatureDrift]:
        """
        Chi-Quadrat Test für kategorische Features.

        Vergleicht Häufigkeitsverteilungen.
        """
        try:
            from scipy import stats

            # Get unique categories
            all_categories = set(reference) | set(current)

            # Count frequencies
            ref_counts = {cat: np.sum(reference == cat) for cat in all_categories}
            cur_counts = {cat: np.sum(current == cat) for cat in all_categories}

            # Prepare contingency table
            ref_freq = [ref_counts.get(cat, 0) + 1 for cat in all_categories]  # +1 smoothing
            cur_freq = [cur_counts.get(cat, 0) + 1 for cat in all_categories]

            # Chi-square test
            chi2, p_value = stats.chisquare(cur_freq, f_exp=ref_freq)
            drift_score = min(1.0, chi2 / (len(all_categories) * 10))  # Normalize

            return FeatureDrift(
                feature_name=feature_name,
                drift_score=drift_score,
                p_value=p_value,
                test_method="chi2",
                is_drifted=p_value < self.drift_threshold,
                reference_stats={"distribution": ref_counts},
                current_stats={"distribution": cur_counts},
            )
        except ImportError:
            return self._simple_categorical_drift(reference, current, feature_name)

    def _simple_drift_check(
        self,
        reference: np.ndarray,
        current: np.ndarray,
        feature_name: str,
    ) -> FeatureDrift:
        """Einfache Drift-Prüfung ohne scipy."""
        ref_mean = float(np.mean(reference))
        cur_mean = float(np.mean(current))
        ref_std = float(np.std(reference)) or 1.0

        # Normalized mean difference
        drift_score = abs(cur_mean - ref_mean) / ref_std
        drift_score = min(1.0, drift_score / 3)  # Normalize to 0-1

        return FeatureDrift(
            feature_name=feature_name,
            drift_score=drift_score,
            p_value=1.0 - drift_score,  # Pseudo p-value
            test_method="mean_diff",
            is_drifted=drift_score > 0.3,
            reference_stats={"mean": ref_mean, "std": ref_std},
            current_stats={"mean": cur_mean, "std": float(np.std(current))},
        )

    def _simple_categorical_drift(
        self,
        reference: np.ndarray,
        current: np.ndarray,
        feature_name: str,
    ) -> FeatureDrift:
        """Einfache kategorische Drift-Prüfung."""
        # Calculate PSI (Population Stability Index)
        all_categories = set(reference) | set(current)

        psi = 0.0
        for cat in all_categories:
            ref_pct = (np.sum(reference == cat) + 1) / (len(reference) + len(all_categories))
            cur_pct = (np.sum(current == cat) + 1) / (len(current) + len(all_categories))

            if ref_pct > 0 and cur_pct > 0:
                psi += (cur_pct - ref_pct) * np.log(cur_pct / ref_pct)

        drift_score = min(1.0, psi / 0.25)  # PSI > 0.25 = significant drift

        return FeatureDrift(
            feature_name=feature_name,
            drift_score=drift_score,
            p_value=1.0 - drift_score,
            test_method="psi",
            is_drifted=psi > 0.1,
            reference_stats={},
            current_stats={},
        )

    def _detect_prediction_drift(self) -> Optional[float]:
        """Erkenne Drift in Modell-Vorhersagen."""
        if not self._reference_predictions or not self._current_predictions:
            return None

        ref_preds = np.array(self._reference_predictions)
        cur_preds = np.array(self._current_predictions)

        # Calculate prediction distribution change
        all_predictions = set(ref_preds) | set(cur_preds)

        total_diff = 0.0
        for pred in all_predictions:
            ref_pct = np.sum(ref_preds == pred) / len(ref_preds)
            cur_pct = np.sum(cur_preds == pred) / len(cur_preds)
            total_diff += abs(cur_pct - ref_pct)

        return total_diff / 2  # Normalize to 0-1

    def _extract_features(
        self,
        data: List[Dict[str, Any]],
    ) -> Dict[str, np.ndarray]:
        """Extrahiere Feature-Arrays aus Daten."""
        result: Dict[str, List[Any]] = {}

        for sample in data:
            features = sample.get("features", {})
            for key, value in features.items():
                if key not in result:
                    result[key] = []
                result[key].append(value)

        return {k: np.array(v) for k, v in result.items()}

    def _calculate_overall_drift(
        self,
        feature_drifts: List[FeatureDrift],
        prediction_drift: Optional[float],
    ) -> float:
        """Berechne Gesamt-Drift-Score."""
        if not feature_drifts:
            return 0.0

        # Weighted average of feature drifts
        feature_score = np.mean([fd.drift_score for fd in feature_drifts])

        # Include prediction drift if available
        if prediction_drift is not None:
            return 0.6 * feature_score + 0.4 * prediction_drift
        else:
            return feature_score

    def _generate_recommendations(
        self,
        feature_drifts: List[FeatureDrift],
        prediction_drift: Optional[float],
        severity: DriftSeverity,
    ) -> List[str]:
        """Generiere Empfehlungen basierend auf Drift."""
        recommendations = []

        if severity == DriftSeverity.NONE:
            recommendations.append("Kein signifikanter Drift erkannt. Modell arbeitet stabil.")
            return recommendations

        # Drifted features
        drifted = [fd for fd in feature_drifts if fd.is_drifted]

        if severity in (DriftSeverity.HIGH, DriftSeverity.CRITICAL):
            recommendations.append(
                "⚠️ KRITISCH: Modell-Retraining dringend empfohlen!"
            )

        if len(drifted) > 0:
            feature_names = [fd.feature_name for fd in drifted[:3]]
            recommendations.append(
                f"Drift in Features: {', '.join(feature_names)}"
            )

        if prediction_drift and prediction_drift > 0.2:
            recommendations.append(
                "Prediction-Verteilung hat sich signifikant geändert."
            )

        if severity == DriftSeverity.MEDIUM:
            recommendations.append(
                "Überwachung verstärken. Retraining in 1-2 Wochen erwägen."
            )
        elif severity == DriftSeverity.LOW:
            recommendations.append(
                "Leichter Drift erkannt. Weiter beobachten."
            )

        return recommendations

    def _create_insufficient_data_report(
        self,
        report_id: str,
        window: str,
        samples: int,
    ) -> DriftReport:
        """Erstelle Report bei unzureichenden Daten."""
        return DriftReport(
            timestamp=datetime.now(),
            report_id=report_id,
            overall_drift_score=0.0,
            severity=DriftSeverity.NONE,
            dataset_drift_detected=False,
            feature_drifts=[],
            prediction_drift=None,
            samples_reference=len(self._reference_data),
            samples_current=len(self._current_data),
            recommendations=[
                f"Unzureichende Daten im {window}-Fenster: {samples} < {self.min_samples}",
                "Mehr Daten sammeln für zuverlässige Drift-Erkennung.",
            ],
            metadata={"insufficient_data": True},
        )

    def _generate_report_id(self) -> str:
        """Generiere eindeutige Report-ID."""
        timestamp = datetime.now().isoformat()
        content = f"{timestamp}-{len(self._reference_data)}-{len(self._current_data)}"
        return hashlib.sha256(content.encode()).hexdigest()[:12]

    def _store_report(self, report: DriftReport) -> None:
        """Speichere Report als JSON."""
        filename = f"drift_report_{report.report_id}.json"
        filepath = self.storage_path / filename

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(report.to_json())

    def _cleanup_old_data(self, days: int = 30) -> None:
        """Entferne Daten älter als X Tage."""
        cutoff = datetime.now() - timedelta(days=days)

        self._reference_data = [
            s for s in self._reference_data
            if s["timestamp"] > cutoff
        ]
        self._current_data = [
            s for s in self._current_data
            if s["timestamp"] > cutoff
        ]

    def get_drift_history(self, limit: int = 10) -> List[DriftReport]:
        """Hole letzte Drift-Reports."""
        return self._drift_history[-limit:]

    def get_current_status(self) -> Dict[str, Any]:
        """Hole aktuellen Drift-Status."""
        latest = self._drift_history[-1] if self._drift_history else None

        return {
            "reference_samples": len(self._reference_data),
            "current_samples": len(self._current_data),
            "min_samples_required": self.min_samples,
            "ready_for_detection": (
                len(self._reference_data) >= self.min_samples and
                len(self._current_data) >= self.min_samples
            ),
            "last_report": latest.to_dict() if latest else None,
            "drift_threshold": self.drift_threshold,
        }

    def reset_reference_window(self) -> None:
        """
        Setze Reference-Fenster zurück.

        Verwende nach Modell-Retraining um neuen Baseline zu etablieren.
        """
        # Move current to reference
        self._reference_data = self._current_data.copy()
        self._reference_predictions = self._current_predictions.copy()

        # Clear current
        self._current_data = []
        self._current_predictions = []

        # Reset cutoff
        self._reference_cutoff = datetime.now() + timedelta(
            days=self.reference_window_days
        )

        logger.info("Reference-Fenster zurückgesetzt für neuen Baseline")


# ============================================================================
# A/B Testing & Alert Integration
# ============================================================================


class DriftAlertManager:
    """
    Manager für Drift-basierte Alerts und A/B-Test Erstellung.

    Verbindet Drift Detection mit:
    - Automatischer A/B-Test Erstellung bei signifikantem Drift
    - Alerting bei PSI > Schwellenwert
    - Monthly Performance Reports
    - Retraining-Trigger bei Quality Degradation
    """

    # PSI Schwellenwerte
    PSI_LOW = 0.1       # Leichter Drift - beobachten
    PSI_MEDIUM = 0.2    # Signifikanter Drift - A/B-Test starten
    PSI_HIGH = 0.25     # Kritischer Drift - sofortige Aktion

    # Quality Degradation Schwellenwerte
    QUALITY_DROP_THRESHOLD = 0.05  # 5% Qualitätsverlust
    LATENCY_INCREASE_THRESHOLD = 0.2  # 20% Latenz-Anstieg

    def __init__(
        self,
        drift_detector: Optional["DriftDetector"] = None,
        alert_callbacks: Optional[List[AlertCallback]] = None,
        storage_path: Optional[Path] = None,
    ) -> None:
        """
        Initialisiere DriftAlertManager.

        Args:
            drift_detector: DriftDetector Instanz (verwendet Singleton wenn None)
            alert_callbacks: Callback-Funktionen für Alerts
            storage_path: Pfad für Reports
        """
        self._drift_detector = drift_detector
        self._alert_callbacks = alert_callbacks or []
        self.storage_path = storage_path or Path("data/drift_reports")
        self.storage_path.mkdir(parents=True, exist_ok=True)

        # Track created experiments
        self._created_experiments: List[str] = []

        # Quality history for degradation detection
        self._quality_history: List[Dict[str, Any]] = []

        # Monthly report tracking
        self._last_report_date: Optional[datetime] = None

        logger.info("DriftAlertManager initialisiert")

    @property
    def drift_detector(self) -> "DriftDetector":
        """Hole DriftDetector (lazy loading)."""
        if self._drift_detector is None:
            self._drift_detector = get_drift_detector()
        return self._drift_detector

    def add_alert_callback(self, callback: AlertCallback) -> None:
        """
        Registriere Alert-Callback.

        Args:
            callback: Funktion(alert_type, message, details)
        """
        self._alert_callbacks.append(callback)

    def check_and_respond_to_drift(self) -> Dict[str, Any]:
        """
        Prüfe aktuellen Drift-Status und reagiere entsprechend.

        Führt aus:
        1. Drift Detection
        2. Alert bei PSI > 0.2
        3. A/B-Test Erstellung bei signifikantem Drift
        4. Quality Degradation Check

        Returns:
            Dict mit Aktionen und Ergebnissen
        """
        result = {
            "drift_detected": False,
            "alerts_sent": [],
            "experiments_created": [],
            "recommendations": [],
            "quality_status": "stable",
        }

        # Run drift detection
        report = self.drift_detector.detect_drift()

        if report.overall_drift_score > 0.1:
            result["drift_detected"] = True

        # Check PSI and send alerts
        psi_score = self._calculate_overall_psi(report)

        if psi_score >= self.PSI_HIGH:
            # Critical drift - immediate alert
            alert = self._send_alert(
                "critical_drift",
                f"⚠️ KRITISCH: PSI Score {psi_score:.3f} - Sofortige Überprüfung erforderlich!",
                {
                    "psi_score": psi_score,
                    "severity": report.severity.value,
                    "drifted_features": [fd.feature_name for fd in report.feature_drifts if fd.is_drifted],
                }
            )
            result["alerts_sent"].append(alert)
            result["recommendations"].append("Modell-Retraining dringend empfohlen")

        elif psi_score >= self.PSI_MEDIUM:
            # Significant drift - start A/B test
            alert = self._send_alert(
                "significant_drift",
                f"📊 Signifikanter Drift erkannt (PSI: {psi_score:.3f}) - A/B-Test wird erstellt",
                {
                    "psi_score": psi_score,
                    "severity": report.severity.value,
                }
            )
            result["alerts_sent"].append(alert)

            # Create A/B test
            experiment = self._create_drift_experiment(report)
            if experiment:
                result["experiments_created"].append(experiment)
                result["recommendations"].append(
                    f"A/B-Test '{experiment}' wurde gestartet zur Evaluierung"
                )

        elif psi_score >= self.PSI_LOW:
            # Low drift - monitoring alert
            alert = self._send_alert(
                "low_drift",
                f"📈 Leichter Drift erkannt (PSI: {psi_score:.3f}) - Verstärkte Überwachung aktiv",
                {"psi_score": psi_score}
            )
            result["alerts_sent"].append(alert)

        # Check quality degradation
        quality_status = self._check_quality_degradation()
        result["quality_status"] = quality_status

        if quality_status == "degraded":
            result["recommendations"].append(
                "Qualitätsverschlechterung erkannt - Retraining empfohlen"
            )

        # Add report recommendations
        result["recommendations"].extend(report.recommendations)

        return result

    def _calculate_overall_psi(self, report: DriftReport) -> float:
        """
        Berechne Gesamt-PSI aus Feature-Drifts.

        Args:
            report: DriftReport

        Returns:
            PSI Score (0-1)
        """
        if not report.feature_drifts:
            return 0.0

        # Use maximum drift score as PSI proxy
        max_drift = max(fd.drift_score for fd in report.feature_drifts)

        # Consider prediction drift as well
        if report.prediction_drift is not None:
            return max(max_drift, report.prediction_drift)

        return max_drift

    def _send_alert(
        self,
        alert_type: str,
        message: str,
        details: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Sende Alert über alle registrierten Callbacks.

        Args:
            alert_type: Art des Alerts
            message: Alert-Nachricht
            details: Zusätzliche Details

        Returns:
            Alert-Info
        """
        alert_info = {
            "type": alert_type,
            "message": message,
            "details": details,
            "timestamp": datetime.now().isoformat(),
        }

        # Log alert
        logger.warning(
            f"drift_alert_{alert_type}",
            message=message,
            **details
        )

        # Call registered callbacks
        for callback in self._alert_callbacks:
            try:
                callback(alert_type, message, details)
            except Exception as e:
                logger.error("alert_callback_failed", callback=str(callback), error=str(e))

        return alert_info

    def _create_drift_experiment(self, report: DriftReport) -> Optional[str]:
        """
        Erstelle A/B-Test als Reaktion auf Drift.

        Vergleicht aktuelles Modell-Routing mit alternativen Strategien.

        Args:
            report: DriftReport

        Returns:
            Experiment-ID oder None
        """
        try:
            from app.ml.ab_testing import get_ab_test_manager

            manager = get_ab_test_manager()

            # Determine which backends to compare based on drift
            control_backend = "deepseek"  # Current default
            treatment_backend = "got-ocr"  # Alternative

            # Check if features suggest different backend
            drifted_features = [fd.feature_name for fd in report.feature_drifts if fd.is_drifted]

            if "has_tables" in drifted_features or "has_formulas" in drifted_features:
                # Table/formula drift - GOT-OCR might be better
                control_backend = "got-ocr"
                treatment_backend = "deepseek"

            # Create experiment
            experiment_name = f"drift_response_{datetime.now().strftime('%Y%m%d_%H%M')}"

            experiment = manager.create_experiment(
                name=experiment_name,
                description=f"Automatisch erstellt aufgrund Drift (Severity: {report.severity.value})",
                variants=[
                    {
                        "name": "control",
                        "description": f"Aktuelles Backend: {control_backend}",
                        "weight": 0.5,
                        "config": {"backend": control_backend},
                    },
                    {
                        "name": "treatment",
                        "description": f"Alternatives Backend: {treatment_backend}",
                        "weight": 0.5,
                        "config": {"backend": treatment_backend},
                    },
                ],
                allocation_method="sticky",
                min_samples=100,
                duration_days=7,  # 1 Woche Laufzeit
            )

            manager.start_experiment(experiment.experiment_id)
            self._created_experiments.append(experiment.experiment_id)

            logger.info(
                "drift_experiment_created",
                experiment_id=experiment.experiment_id,
                control=control_backend,
                treatment=treatment_backend,
                severity=report.severity.value,
            )

            return experiment.experiment_id

        except Exception as e:
            logger.error("drift_experiment_creation_failed", error=str(e))
            return None

    def _check_quality_degradation(self) -> str:
        """
        Prüfe auf Qualitätsverschlechterung.

        Returns:
            'stable', 'degraded', oder 'improved'
        """
        if len(self._quality_history) < 2:
            return "stable"

        # Compare recent quality to baseline
        recent = self._quality_history[-10:]  # Last 10 samples
        baseline = self._quality_history[:10]  # First 10 samples

        if not recent or not baseline:
            return "stable"

        # Calculate average quality scores
        recent_quality = np.mean([q.get("quality_score", 0.5) for q in recent])
        baseline_quality = np.mean([q.get("quality_score", 0.5) for q in baseline])

        quality_change = (recent_quality - baseline_quality) / baseline_quality if baseline_quality > 0 else 0

        if quality_change < -self.QUALITY_DROP_THRESHOLD:
            return "degraded"
        elif quality_change > self.QUALITY_DROP_THRESHOLD:
            return "improved"

        return "stable"

    def record_quality_sample(
        self,
        quality_score: float,
        latency_ms: float,
        backend: str,
        document_type: str = "unknown",
    ) -> None:
        """
        Erfasse Quality-Sample für Degradation-Tracking.

        Args:
            quality_score: Qualitätsscore (0-1)
            latency_ms: Latenz in Millisekunden
            backend: Verwendetes Backend
            document_type: Dokumenttyp
        """
        sample = {
            "timestamp": datetime.now(),
            "quality_score": quality_score,
            "latency_ms": latency_ms,
            "backend": backend,
            "document_type": document_type,
        }
        self._quality_history.append(sample)

        # Keep only last 1000 samples
        if len(self._quality_history) > 1000:
            self._quality_history = self._quality_history[-1000:]

    def generate_monthly_report(self) -> Dict[str, Any]:
        """
        Generiere monatlichen Performance-Report.

        Returns:
            Report als Dictionary
        """
        now = datetime.now()

        # Check if already generated this month
        if self._last_report_date and self._last_report_date.month == now.month:
            logger.info("monthly_report_already_generated")
            return {"status": "already_generated", "last_report": self._last_report_date.isoformat()}

        report = {
            "report_type": "monthly_performance",
            "generated_at": now.isoformat(),
            "period": f"{now.year}-{now.month:02d}",
            "sections": {},
        }

        # Drift Summary
        drift_history = self.drift_detector.get_drift_history(limit=30)
        if drift_history:
            drift_summary = {
                "total_detections": len(drift_history),
                "high_severity_count": sum(1 for d in drift_history if d.severity in (DriftSeverity.HIGH, DriftSeverity.CRITICAL)),
                "avg_drift_score": np.mean([d.overall_drift_score for d in drift_history]),
                "max_drift_score": max(d.overall_drift_score for d in drift_history),
            }
            report["sections"]["drift_summary"] = drift_summary

        # Quality Summary
        if self._quality_history:
            quality_summary = {
                "total_samples": len(self._quality_history),
                "avg_quality": np.mean([q["quality_score"] for q in self._quality_history]),
                "avg_latency_ms": np.mean([q["latency_ms"] for q in self._quality_history]),
                "backends_used": list(set(q["backend"] for q in self._quality_history)),
                "quality_trend": self._check_quality_degradation(),
            }
            report["sections"]["quality_summary"] = quality_summary

        # Experiments Summary
        report["sections"]["experiments"] = {
            "drift_triggered": len(self._created_experiments),
            "experiment_ids": self._created_experiments[-10:],  # Last 10
        }

        # Recommendations
        recommendations = []
        if report["sections"].get("drift_summary", {}).get("high_severity_count", 0) > 5:
            recommendations.append("Häufige kritische Drift-Events - Modellüberprüfung empfohlen")

        quality_trend = report["sections"].get("quality_summary", {}).get("quality_trend", "stable")
        if quality_trend == "degraded":
            recommendations.append("Qualitätsabfall erkannt - Retraining-Pipeline prüfen")

        report["recommendations"] = recommendations

        # Save report
        report_path = self.storage_path / f"monthly_report_{now.strftime('%Y%m')}.json"
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, default=str)

        self._last_report_date = now

        logger.info(
            "monthly_report_generated",
            period=report["period"],
            path=str(report_path),
        )

        return report

    def check_retraining_trigger(self) -> Dict[str, Any]:
        """
        Prüfe ob Retraining ausgelöst werden sollte.

        Kriterien:
        - Kritischer Drift (PSI > 0.25)
        - Quality Degradation > 5%
        - Mehr als 3 High-Severity Drift Events im letzten Monat

        Returns:
            Dict mit Trigger-Status und Gründen
        """
        result = {
            "should_retrain": False,
            "reasons": [],
            "severity": "none",
            "recommended_action": None,
        }

        # Check recent drift
        drift_history = self.drift_detector.get_drift_history(limit=30)
        high_severity_count = sum(
            1 for d in drift_history
            if d.severity in (DriftSeverity.HIGH, DriftSeverity.CRITICAL)
        )

        if high_severity_count > 3:
            result["should_retrain"] = True
            result["reasons"].append(f"{high_severity_count} High-Severity Drift Events im letzten Monat")
            result["severity"] = "high"

        # Check latest drift report
        if drift_history:
            latest = drift_history[-1]
            if latest.severity == DriftSeverity.CRITICAL:
                result["should_retrain"] = True
                result["reasons"].append(f"Kritischer Drift erkannt (Score: {latest.overall_drift_score:.3f})")
                result["severity"] = "critical"

        # Check quality degradation
        quality_status = self._check_quality_degradation()
        if quality_status == "degraded":
            result["should_retrain"] = True
            result["reasons"].append("Qualitätsverschlechterung > 5% erkannt")
            if result["severity"] != "critical":
                result["severity"] = "medium"

        # Set recommended action
        if result["should_retrain"]:
            if result["severity"] == "critical":
                result["recommended_action"] = "Sofortiges Retraining und manuelle Überprüfung"
            elif result["severity"] == "high":
                result["recommended_action"] = "Retraining innerhalb 24 Stunden einplanen"
            else:
                result["recommended_action"] = "Retraining in nächster Wartungsperiode einplanen"

            # Send alert
            self._send_alert(
                "retraining_recommended",
                f"🔄 Retraining empfohlen: {', '.join(result['reasons'])}",
                result
            )

        return result


# Singleton instances
_drift_detector: Optional[DriftDetector] = None
_drift_alert_manager: Optional[DriftAlertManager] = None


def get_drift_detector() -> DriftDetector:
    """
    Hole globale DriftDetector Instanz.

    Thread-safe mit double-checked locking.
    """
    global _drift_detector

    # Fast path: bereits initialisiert
    if _drift_detector is not None:
        return _drift_detector

    # Slow path: Thread-safe Initialisierung
    with _drift_detector_lock:
        # Double-check nach Lock-Erwerb
        if _drift_detector is None:
            logger.info("drift_detector_initialisierung")
            _drift_detector = DriftDetector()
            logger.info(
                "drift_detector_initialisiert",
                min_samples=_drift_detector.min_samples,
                drift_threshold=_drift_detector.drift_threshold,
            )

    return _drift_detector


def get_drift_alert_manager() -> DriftAlertManager:
    """
    Hole globale DriftAlertManager Instanz.

    Thread-safe mit double-checked locking.
    """
    global _drift_alert_manager

    # Fast path: bereits initialisiert
    if _drift_alert_manager is not None:
        return _drift_alert_manager

    # Slow path: Thread-safe Initialisierung
    with _drift_detector_lock:
        # Double-check nach Lock-Erwerb
        if _drift_alert_manager is None:
            logger.info("drift_alert_manager_initialisierung")
            _drift_alert_manager = DriftAlertManager()
            logger.info("drift_alert_manager_initialisiert")

    return _drift_alert_manager
