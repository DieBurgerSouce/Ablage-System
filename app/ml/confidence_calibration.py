# -*- coding: utf-8 -*-
"""
OCR Confidence Calibration Module.

Ermöglicht:
- Kalibrierung von OCR-Konfidenzwerten
- Temperature Scaling für bessere Wahrscheinlichkeiten
- Isotonische Regression für monotone Kalibrierung
- Per-Backend Kalibrierungsmodelle
- Erwartete Kalibrierungsfehler (ECE) Berechnung

Feinpoliert und durchdacht - Zuverlässige Konfidenzschätzungen.
"""

import json
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import structlog

logger = structlog.get_logger(__name__)


# =============================================================================
# Enums
# =============================================================================


class CalibrationMethod(str, Enum):
    """Kalibrierungsmethoden."""
    TEMPERATURE_SCALING = "temperature_scaling"
    ISOTONIC_REGRESSION = "isotonic_regression"
    PLATT_SCALING = "platt_scaling"
    HISTOGRAM_BINNING = "histogram_binning"
    BETA_CALIBRATION = "beta_calibration"


class ConfidenceLevel(str, Enum):
    """Kalibrierte Konfidenz-Level."""
    VERY_HIGH = "very_high"       # >= 0.95
    HIGH = "high"                 # >= 0.85
    MEDIUM = "medium"             # >= 0.70
    LOW = "low"                   # >= 0.50
    VERY_LOW = "very_low"         # < 0.50


# =============================================================================
# Data Classes
# =============================================================================


@dataclass
class CalibrationSample:
    """Einzelner Kalibrierungsdatenpunkt."""
    raw_confidence: float
    is_correct: bool
    backend: str
    document_type: str = "unknown"
    timestamp: Optional[datetime] = None


@dataclass
class CalibrationResult:
    """Ergebnis einer Konfidenz-Kalibrierung."""
    raw_confidence: float
    calibrated_confidence: float
    confidence_level: ConfidenceLevel
    calibration_method: CalibrationMethod
    adjustment: float  # Differenz raw - calibrated

    @property
    def reliability_improved(self) -> bool:
        """Wurde die Zuverlässigkeit verbessert?"""
        # Kalibrierung sollte extreme Werte moderieren
        return abs(self.adjustment) > 0.01


@dataclass
class CalibrationMetrics:
    """Metriken zur Bewertung der Kalibrierung."""
    ece: float                    # Expected Calibration Error
    mce: float                    # Maximum Calibration Error
    brier_score: float            # Brier Score
    reliability_diagram: List[Tuple[float, float, int]]  # (bin_center, accuracy, count)
    overconfidence_ratio: float   # Anteil überconfidenter Vorhersagen
    underconfidence_ratio: float  # Anteil unterconfidenter Vorhersagen


@dataclass
class CalibrationModel:
    """Kalibrierungsmodell für ein Backend."""
    backend: str
    method: CalibrationMethod
    parameters: Dict[str, Any]
    samples_used: int
    created_at: datetime
    metrics: Optional[CalibrationMetrics] = None

    def to_dict(self) -> Dict[str, Any]:
        """Konvertiere zu Dictionary für Serialisierung."""
        return {
            "backend": self.backend,
            "method": self.method.value,
            "parameters": self.parameters,
            "samples_used": self.samples_used,
            "created_at": self.created_at.isoformat(),
            "metrics": {
                "ece": self.metrics.ece,
                "mce": self.metrics.mce,
                "brier_score": self.metrics.brier_score,
            } if self.metrics else None,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CalibrationModel":
        """Erstelle aus Dictionary."""
        return cls(
            backend=data["backend"],
            method=CalibrationMethod(data["method"]),
            parameters=data["parameters"],
            samples_used=data["samples_used"],
            created_at=datetime.fromisoformat(data["created_at"]),
            metrics=None,  # Metriken werden bei Bedarf neu berechnet
        )


# =============================================================================
# Temperature Scaling
# =============================================================================


class TemperatureScaler:
    """
    Temperature Scaling für Konfidenz-Kalibrierung.

    Eine einfache aber effektive Methode:
    calibrated = sigmoid(logit(raw) / temperature)

    Niedrigere Temperatur = schärfere Vorhersagen
    Höhere Temperatur = weichere Vorhersagen
    """

    def __init__(self, temperature: float = 1.0) -> None:
        self.temperature = temperature

    def calibrate(self, confidence: float) -> float:
        """Kalibriere einzelnen Konfidenzwert."""
        if confidence <= 0:
            return 0.0
        if confidence >= 1:
            return 1.0

        # Logit transformation
        logit = math.log(confidence / (1 - confidence))

        # Temperature scaling
        scaled_logit = logit / self.temperature

        # Sigmoid zurück
        calibrated = 1 / (1 + math.exp(-scaled_logit))

        return calibrated

    def fit(
        self,
        confidences: List[float],
        labels: List[bool],
        learning_rate: float = 0.01,
        max_iterations: int = 100,
    ) -> float:
        """
        Optimiere Temperatur basierend auf Daten.

        Minimiert Negative Log Likelihood.
        """
        if len(confidences) != len(labels):
            raise ValueError("Länge von confidences und labels muss übereinstimmen")

        if len(confidences) < 10:
            logger.warning("temperature_scaling_few_samples", count=len(confidences))
            return self.temperature

        # Grid Search für beste Temperatur
        best_temp = 1.0
        best_nll = float("inf")

        for temp in np.linspace(0.1, 5.0, 50):
            self.temperature = temp
            nll = self._compute_nll(confidences, labels)
            if nll < best_nll:
                best_nll = nll
                best_temp = temp

        self.temperature = best_temp
        logger.info(
            "temperature_scaling_fitted",
            temperature=round(best_temp, 3),
            nll=round(best_nll, 4),
        )

        return self.temperature

    def _compute_nll(self, confidences: List[float], labels: List[bool]) -> float:
        """Berechne Negative Log Likelihood."""
        nll = 0.0
        eps = 1e-10

        for conf, label in zip(confidences, labels):
            cal = self.calibrate(conf)
            if label:
                nll -= math.log(cal + eps)
            else:
                nll -= math.log(1 - cal + eps)

        return nll / len(confidences)


# =============================================================================
# Isotonic Regression
# =============================================================================


class IsotonicCalibrator:
    """
    Isotonische Regression für Konfidenz-Kalibrierung.

    Erzwingt monotone Kalibrierungsfunktion:
    Höhere rohe Konfidenz → höhere kalibrierte Konfidenz

    Nicht-parametrische Methode, sehr flexibel.
    """

    def __init__(self) -> None:
        self._isotonic_map: List[Tuple[float, float]] = []
        self._fitted = False

    def fit(self, confidences: List[float], labels: List[bool]) -> None:
        """
        Fitte isotonisches Kalibrierungsmodell.

        Verwendet Pool Adjacent Violators Algorithm (PAVA).
        """
        if len(confidences) != len(labels):
            raise ValueError("Länge muss übereinstimmen")

        if len(confidences) < 10:
            logger.warning("isotonic_few_samples", count=len(confidences))
            self._fitted = False
            return

        # Sortiere nach Konfidenz
        sorted_pairs = sorted(
            zip(confidences, [1.0 if l else 0.0 for l in labels]),
            key=lambda x: x[0]
        )

        # PAVA Algorithmus
        blocks: List[Tuple[float, float, float, int]] = []  # (conf_start, conf_end, y, count)

        for conf, y in sorted_pairs:
            blocks.append((conf, conf, y, 1))

            # Merge violating blocks
            while len(blocks) > 1 and blocks[-2][2] > blocks[-1][2]:
                # Pool adjacent violators
                b1 = blocks.pop()
                b2 = blocks.pop()

                merged_y = (b2[2] * b2[3] + b1[2] * b1[3]) / (b2[3] + b1[3])
                merged = (b2[0], b1[1], merged_y, b2[3] + b1[3])
                blocks.append(merged)

        # Erstelle Kalibrierungskarte
        self._isotonic_map = []
        for conf_start, conf_end, y, _ in blocks:
            mid = (conf_start + conf_end) / 2
            self._isotonic_map.append((mid, y))

        self._fitted = True

        logger.info(
            "isotonic_calibrator_fitted",
            blocks=len(self._isotonic_map),
            samples=len(confidences),
        )

    def calibrate(self, confidence: float) -> float:
        """Kalibriere einzelnen Konfidenzwert."""
        if not self._fitted or not self._isotonic_map:
            return confidence

        # Finde nächsten Punkt und interpoliere
        if confidence <= self._isotonic_map[0][0]:
            return self._isotonic_map[0][1]

        if confidence >= self._isotonic_map[-1][0]:
            return self._isotonic_map[-1][1]

        # Lineare Interpolation
        for i in range(len(self._isotonic_map) - 1):
            x1, y1 = self._isotonic_map[i]
            x2, y2 = self._isotonic_map[i + 1]

            if x1 <= confidence <= x2:
                if x2 == x1:
                    return y1
                t = (confidence - x1) / (x2 - x1)
                return y1 + t * (y2 - y1)

        return confidence


# =============================================================================
# Histogram Binning
# =============================================================================


class HistogramBinningCalibrator:
    """
    Histogram Binning für Konfidenz-Kalibrierung.

    Teilt Konfidenzbereich in Bins und ersetzt
    durch durchschnittliche Genauigkeit pro Bin.
    """

    def __init__(self, n_bins: int = 10) -> None:
        self.n_bins = n_bins
        self._bin_accuracies: List[float] = []
        self._bin_edges: List[float] = []
        self._fitted = False

    def fit(self, confidences: List[float], labels: List[bool]) -> None:
        """Fitte Histogram Binning Modell."""
        if len(confidences) < self.n_bins:
            logger.warning("histogram_binning_few_samples", count=len(confidences))
            self._fitted = False
            return

        # Erstelle Bins
        self._bin_edges = [i / self.n_bins for i in range(self.n_bins + 1)]
        self._bin_accuracies = []

        for i in range(self.n_bins):
            lower = self._bin_edges[i]
            upper = self._bin_edges[i + 1]

            # Sammle Samples in diesem Bin
            bin_labels = [
                l for c, l in zip(confidences, labels)
                if lower <= c < upper
            ]

            if bin_labels:
                accuracy = sum(bin_labels) / len(bin_labels)
            else:
                # Fallback: Mitte des Bins
                accuracy = (lower + upper) / 2

            self._bin_accuracies.append(accuracy)

        self._fitted = True

        logger.info(
            "histogram_binning_fitted",
            bins=self.n_bins,
            samples=len(confidences),
        )

    def calibrate(self, confidence: float) -> float:
        """Kalibriere einzelnen Konfidenzwert."""
        if not self._fitted:
            return confidence

        # Finde passenden Bin
        bin_idx = min(
            int(confidence * self.n_bins),
            self.n_bins - 1
        )

        return self._bin_accuracies[bin_idx]


# =============================================================================
# Confidence Calibrator (Haupt-Klasse)
# =============================================================================


class ConfidenceCalibrator:
    """
    Haupt-Kalibrierungsklasse für OCR-Konfidenzen.

    Unterstützt:
    - Mehrere Kalibrierungsmethoden
    - Per-Backend Kalibrierung
    - Persistenz von Modellen
    - Metriken-Berechnung
    """

    DEFAULT_METHODS = {
        "deepseek": CalibrationMethod.TEMPERATURE_SCALING,
        "got_ocr": CalibrationMethod.ISOTONIC_REGRESSION,
        "surya": CalibrationMethod.HISTOGRAM_BINNING,
        "surya_gpu": CalibrationMethod.HISTOGRAM_BINNING,
    }

    def __init__(
        self,
        data_dir: Optional[Path] = None,
        default_method: CalibrationMethod = CalibrationMethod.TEMPERATURE_SCALING,
    ) -> None:
        """
        Initialisiere Calibrator.

        Args:
            data_dir: Verzeichnis für Modell-Persistenz
            default_method: Standard-Kalibrierungsmethode
        """
        self.data_dir = data_dir or Path("data/calibration")
        self.default_method = default_method

        # Kalibrierungsmodelle pro Backend
        self._models: Dict[str, CalibrationModel] = {}

        # Calibrator-Instanzen
        self._temperature_scalers: Dict[str, TemperatureScaler] = {}
        self._isotonic_calibrators: Dict[str, IsotonicCalibrator] = {}
        self._histogram_calibrators: Dict[str, HistogramBinningCalibrator] = {}

        # Kalibrierungsdaten sammeln
        self._pending_samples: Dict[str, List[CalibrationSample]] = {}

        # Lade existierende Modelle
        self._load_models()

        logger.info(
            "ConfidenceCalibrator initialisiert",
            data_dir=str(self.data_dir),
            loaded_models=len(self._models),
        )

    def calibrate(
        self,
        confidence: float,
        backend: str,
        fallback_if_uncalibrated: bool = True,
    ) -> CalibrationResult:
        """
        Kalibriere Konfidenzwert.

        Args:
            confidence: Roher Konfidenzwert (0-1)
            backend: OCR-Backend Name
            fallback_if_uncalibrated: Gib raw zurück wenn nicht kalibriert

        Returns:
            CalibrationResult
        """
        # Validierung
        confidence = max(0.0, min(1.0, confidence))

        # Prüfe ob Modell existiert
        model = self._models.get(backend)

        if model is None:
            if fallback_if_uncalibrated:
                return CalibrationResult(
                    raw_confidence=confidence,
                    calibrated_confidence=confidence,
                    confidence_level=self._get_confidence_level(confidence),
                    calibration_method=self.default_method,
                    adjustment=0.0,
                )
            else:
                raise ValueError(f"Kein Kalibrierungsmodell für Backend: {backend}")

        # Kalibriere basierend auf Methode
        calibrated = self._apply_calibration(confidence, backend, model.method)

        return CalibrationResult(
            raw_confidence=confidence,
            calibrated_confidence=calibrated,
            confidence_level=self._get_confidence_level(calibrated),
            calibration_method=model.method,
            adjustment=confidence - calibrated,
        )

    def calibrate_batch(
        self,
        confidences: List[float],
        backend: str,
    ) -> List[CalibrationResult]:
        """Kalibriere mehrere Konfidenzwerte."""
        return [self.calibrate(c, backend) for c in confidences]

    def add_sample(
        self,
        raw_confidence: float,
        is_correct: bool,
        backend: str,
        document_type: str = "unknown",
    ) -> None:
        """
        Füge Kalibrierungssample hinzu.

        Samples werden gesammelt und bei Schwellenwert
        automatisch zum Neutrainieren verwendet.
        """
        sample = CalibrationSample(
            raw_confidence=raw_confidence,
            is_correct=is_correct,
            backend=backend,
            document_type=document_type,
            timestamp=datetime.now(timezone.utc),
        )

        if backend not in self._pending_samples:
            self._pending_samples[backend] = []

        self._pending_samples[backend].append(sample)

        # Auto-Retrain bei genug Samples
        if len(self._pending_samples[backend]) >= 100:
            self._retrain_model(backend)

    def train_model(
        self,
        backend: str,
        samples: List[CalibrationSample],
        method: Optional[CalibrationMethod] = None,
    ) -> CalibrationModel:
        """
        Trainiere Kalibrierungsmodell für Backend.

        Args:
            backend: Backend-Name
            samples: Kalibrierungssamples
            method: Kalibrierungsmethode (Default basierend auf Backend)

        Returns:
            CalibrationModel
        """
        if len(samples) < 20:
            raise ValueError(f"Mindestens 20 Samples benötigt, nur {len(samples)} vorhanden")

        method = method or self.DEFAULT_METHODS.get(backend, self.default_method)

        confidences = [s.raw_confidence for s in samples]
        labels = [s.is_correct for s in samples]

        parameters: Dict[str, Any] = {}

        if method == CalibrationMethod.TEMPERATURE_SCALING:
            scaler = TemperatureScaler()
            temp = scaler.fit(confidences, labels)
            self._temperature_scalers[backend] = scaler
            parameters["temperature"] = temp

        elif method == CalibrationMethod.ISOTONIC_REGRESSION:
            calibrator = IsotonicCalibrator()
            calibrator.fit(confidences, labels)
            self._isotonic_calibrators[backend] = calibrator
            parameters["mapping_points"] = len(calibrator._isotonic_map)

        elif method == CalibrationMethod.HISTOGRAM_BINNING:
            calibrator = HistogramBinningCalibrator(n_bins=15)
            calibrator.fit(confidences, labels)
            self._histogram_calibrators[backend] = calibrator
            parameters["bin_accuracies"] = calibrator._bin_accuracies

        # Berechne Metriken
        metrics = self._compute_metrics(confidences, labels, backend, method)

        model = CalibrationModel(
            backend=backend,
            method=method,
            parameters=parameters,
            samples_used=len(samples),
            created_at=datetime.now(timezone.utc),
            metrics=metrics,
        )

        self._models[backend] = model
        self._save_model(model)

        logger.info(
            "calibration_model_trained",
            backend=backend,
            method=method.value,
            samples=len(samples),
            ece=round(metrics.ece, 4) if metrics else None,
        )

        return model

    def _apply_calibration(
        self,
        confidence: float,
        backend: str,
        method: CalibrationMethod,
    ) -> float:
        """Wende Kalibrierung basierend auf Methode an."""
        if method == CalibrationMethod.TEMPERATURE_SCALING:
            if backend in self._temperature_scalers:
                return self._temperature_scalers[backend].calibrate(confidence)

        elif method == CalibrationMethod.ISOTONIC_REGRESSION:
            if backend in self._isotonic_calibrators:
                return self._isotonic_calibrators[backend].calibrate(confidence)

        elif method == CalibrationMethod.HISTOGRAM_BINNING:
            if backend in self._histogram_calibrators:
                return self._histogram_calibrators[backend].calibrate(confidence)

        return confidence

    def _compute_metrics(
        self,
        confidences: List[float],
        labels: List[bool],
        backend: str,
        method: CalibrationMethod,
    ) -> CalibrationMetrics:
        """Berechne Kalibrierungsmetriken."""
        n_bins = 10
        bin_boundaries = np.linspace(0, 1, n_bins + 1)

        # Kalibrierte Werte
        calibrated = [
            self._apply_calibration(c, backend, method)
            for c in confidences
        ]

        # ECE und MCE Berechnung
        bin_accs = []
        bin_confs = []
        bin_counts = []
        reliability_diagram = []

        for i in range(n_bins):
            lower = bin_boundaries[i]
            upper = bin_boundaries[i + 1]

            # Samples in diesem Bin
            mask = [(lower <= c < upper) for c in calibrated]
            bin_labels = [l for l, m in zip(labels, mask) if m]
            bin_confs_list = [c for c, m in zip(calibrated, mask) if m]

            if bin_labels:
                acc = sum(bin_labels) / len(bin_labels)
                conf = sum(bin_confs_list) / len(bin_confs_list)
                count = len(bin_labels)
            else:
                acc = 0.0
                conf = (lower + upper) / 2
                count = 0

            bin_accs.append(acc)
            bin_confs.append(conf)
            bin_counts.append(count)
            reliability_diagram.append(((lower + upper) / 2, acc, count))

        # ECE: gewichteter Durchschnitt der Abweichungen
        total = sum(bin_counts)
        if total > 0:
            ece = sum(
                (count / total) * abs(acc - conf)
                for acc, conf, count in zip(bin_accs, bin_confs, bin_counts)
            )
            mce = max(
                abs(acc - conf)
                for acc, conf in zip(bin_accs, bin_confs)
            )
        else:
            ece = 0.0
            mce = 0.0

        # Brier Score
        brier = sum(
            (c - (1.0 if l else 0.0)) ** 2
            for c, l in zip(calibrated, labels)
        ) / len(labels) if labels else 0.0

        # Over/Underconfidence
        overconfident = sum(
            1 for c, l in zip(calibrated, labels)
            if c > 0.5 and not l
        )
        underconfident = sum(
            1 for c, l in zip(calibrated, labels)
            if c < 0.5 and l
        )

        total_samples = len(labels)
        overconfidence_ratio = overconfident / total_samples if total_samples > 0 else 0.0
        underconfidence_ratio = underconfident / total_samples if total_samples > 0 else 0.0

        return CalibrationMetrics(
            ece=ece,
            mce=mce,
            brier_score=brier,
            reliability_diagram=reliability_diagram,
            overconfidence_ratio=overconfidence_ratio,
            underconfidence_ratio=underconfidence_ratio,
        )

    def _get_confidence_level(self, confidence: float) -> ConfidenceLevel:
        """Bestimme Konfidenz-Level."""
        if confidence >= 0.95:
            return ConfidenceLevel.VERY_HIGH
        elif confidence >= 0.85:
            return ConfidenceLevel.HIGH
        elif confidence >= 0.70:
            return ConfidenceLevel.MEDIUM
        elif confidence >= 0.50:
            return ConfidenceLevel.LOW
        else:
            return ConfidenceLevel.VERY_LOW

    def _retrain_model(self, backend: str) -> None:
        """Trainiere Modell mit gesammelten Samples neu."""
        samples = self._pending_samples.get(backend, [])
        if len(samples) >= 20:
            try:
                self.train_model(backend, samples)
                self._pending_samples[backend] = []  # Clear nach Training
            except Exception as e:
                logger.error("retrain_failed", backend=backend, error=str(e))

    def _save_model(self, model: CalibrationModel) -> None:
        """Speichere Modell auf Disk."""
        try:
            self.data_dir.mkdir(parents=True, exist_ok=True)
            model_path = self.data_dir / f"{model.backend}_calibration.json"

            with open(model_path, "w", encoding="utf-8") as f:
                json.dump(model.to_dict(), f, indent=2, ensure_ascii=False)

            logger.debug("calibration_model_saved", path=str(model_path))

        except Exception as e:
            logger.error("calibration_save_failed", error=str(e))

    def _load_models(self) -> None:
        """Lade alle Modelle von Disk."""
        if not self.data_dir.exists():
            return

        for model_path in self.data_dir.glob("*_calibration.json"):
            try:
                with open(model_path, "r", encoding="utf-8") as f:
                    data = json.load(f)

                model = CalibrationModel.from_dict(data)
                self._models[model.backend] = model

                # Rekonstruiere Calibrator-Instanzen
                self._reconstruct_calibrator(model)

                logger.debug("calibration_model_loaded", backend=model.backend)

            except Exception as e:
                logger.warning(
                    "calibration_load_failed",
                    path=str(model_path),
                    error=str(e),
                )

    def _reconstruct_calibrator(self, model: CalibrationModel) -> None:
        """Rekonstruiere Calibrator aus gespeicherten Parametern."""
        if model.method == CalibrationMethod.TEMPERATURE_SCALING:
            temp = model.parameters.get("temperature", 1.0)
            self._temperature_scalers[model.backend] = TemperatureScaler(temp)

        elif model.method == CalibrationMethod.HISTOGRAM_BINNING:
            accuracies = model.parameters.get("bin_accuracies", [])
            if accuracies:
                calibrator = HistogramBinningCalibrator(n_bins=len(accuracies))
                calibrator._bin_accuracies = accuracies
                calibrator._bin_edges = [i / len(accuracies) for i in range(len(accuracies) + 1)]
                calibrator._fitted = True
                self._histogram_calibrators[model.backend] = calibrator

    def get_model_info(self, backend: str) -> Optional[Dict[str, Any]]:
        """Hole Informationen zu einem Modell."""
        model = self._models.get(backend)
        if model:
            return model.to_dict()
        return None

    def get_all_backends(self) -> List[str]:
        """Liste aller kalibrierten Backends."""
        return list(self._models.keys())


# =============================================================================
# Singleton
# =============================================================================


_calibrator: Optional[ConfidenceCalibrator] = None


def get_calibrator() -> ConfidenceCalibrator:
    """Hole globale Calibrator-Instanz."""
    global _calibrator
    if _calibrator is None:
        _calibrator = ConfidenceCalibrator()
        logger.info("ConfidenceCalibrator initialisiert")
    return _calibrator


# =============================================================================
# Convenience Functions
# =============================================================================


def calibrate_confidence(
    confidence: float,
    backend: str,
) -> CalibrationResult:
    """Kalibriere einzelnen Konfidenzwert."""
    return get_calibrator().calibrate(confidence, backend)


def calibrate_batch(
    confidences: List[float],
    backend: str,
) -> List[CalibrationResult]:
    """Kalibriere mehrere Konfidenzwerte."""
    return get_calibrator().calibrate_batch(confidences, backend)


def add_calibration_sample(
    raw_confidence: float,
    is_correct: bool,
    backend: str,
    document_type: str = "unknown",
) -> None:
    """Füge Kalibrierungssample hinzu."""
    get_calibrator().add_sample(raw_confidence, is_correct, backend, document_type)


def get_expected_calibration_error(backend: str) -> Optional[float]:
    """Hole ECE für ein Backend."""
    calibrator = get_calibrator()
    model = calibrator._models.get(backend)
    if model and model.metrics:
        return model.metrics.ece
    return None
