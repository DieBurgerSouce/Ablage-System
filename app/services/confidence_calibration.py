"""
Confidence Calibration Service für OCR Pipeline.

Kalibriert und normalisiert Confidence-Scores verschiedener OCR-Backends:
- Isotonic Regression Kalibrierung
- Platt Scaling (logistische Regression)
- Temperature Scaling
- Histogram Binning
- Backend-spezifische Kalibrierung

Ermöglicht faire Vergleiche zwischen DeepSeek, GOT-OCR, Surya etc.

Feinpoliert und durchdacht - Enterprise OCR Calibration.
"""

import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

import structlog
from app.core.safe_errors import safe_error_log

logger = structlog.get_logger(__name__)

# Optional imports
try:
    import numpy as np
    NUMPY_AVAILABLE = True
except ImportError:
    NUMPY_AVAILABLE = False
    np = None  # type: ignore


@dataclass
class CalibrationStats:
    """Statistiken für Kalibrierung."""

    backend: str
    samples_count: int = 0
    raw_mean: float = 0.0
    raw_std: float = 0.0
    calibrated_mean: float = 0.0
    calibrated_std: float = 0.0
    ece: float = 0.0  # Expected Calibration Error
    mce: float = 0.0  # Maximum Calibration Error
    reliability_improvement: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        """Konvertiere zu Dictionary."""
        return {
            "backend": self.backend,
            "samples_count": self.samples_count,
            "raw_mean": round(self.raw_mean, 4),
            "raw_std": round(self.raw_std, 4),
            "calibrated_mean": round(self.calibrated_mean, 4),
            "calibrated_std": round(self.calibrated_std, 4),
            "ece": round(self.ece, 4),
            "mce": round(self.mce, 4),
            "reliability_improvement": round(self.reliability_improvement, 4),
        }


@dataclass
class CalibrationData:
    """Trainings-Daten für Kalibrierung."""

    confidences: List[float] = field(default_factory=list)
    actuals: List[int] = field(default_factory=list)  # 1=korrekt, 0=falsch
    timestamps: List[float] = field(default_factory=list)  # Unix Timestamps für Sliding Window

    def add_sample(self, confidence: float, is_correct: bool, timestamp: Optional[float] = None) -> None:
        """Füge Trainings-Sample hinzu."""
        import time
        self.confidences.append(confidence)
        self.actuals.append(1 if is_correct else 0)
        self.timestamps.append(timestamp or time.time())

    def get_recent_samples(self, max_age_days: int = 30) -> Tuple[List[float], List[int]]:
        """
        Hole nur Samples aus den letzten max_age_days Tagen.

        Args:
            max_age_days: Maximales Alter in Tagen

        Returns:
            Tuple (confidences, actuals) der neueren Samples
        """
        import time

        cutoff = time.time() - (max_age_days * 24 * 60 * 60)

        recent_conf = []
        recent_act = []

        for conf, act, ts in zip(self.confidences, self.actuals, self.timestamps):
            if ts >= cutoff:
                recent_conf.append(conf)
                recent_act.append(act)

        return recent_conf, recent_act

    def __len__(self) -> int:
        return len(self.confidences)


# =============================================================================
# Document-Type Specific Calibration
# =============================================================================

class DocumentType:
    """Enum für Dokumenttypen."""
    INVOICE = "invoice"
    LETTER = "letter"
    CONTRACT = "contract"
    FORM = "form"
    HANDWRITTEN = "handwritten"
    FRAKTUR = "fraktur"
    UNKNOWN = "unknown"


@dataclass
class BackendDocTypeCalibrator:
    """
    Kalibrator für ein Backend + Dokumenttyp Kombination.

    Ermöglicht Backend-spezifische UND Dokumenttyp-spezifische Kalibrierung.
    """
    backend: str
    doc_type: str
    calibrator: Optional[Any] = None  # Runtime: CalibratorType (forward reference)
    training_data: CalibrationData = field(default_factory=CalibrationData)
    stats: Optional[CalibrationStats] = None
    auto_retrain_threshold: int = 50  # Retrain nach X neuen Samples

    _samples_since_train: int = 0

    def add_sample(self, confidence: float, is_correct: bool) -> bool:
        """
        Füge Sample hinzu und trainiere automatisch wenn Threshold erreicht.

        Returns:
            True wenn Retrain durchgeführt wurde
        """
        self.training_data.add_sample(confidence, is_correct)
        self._samples_since_train += 1

        if self._samples_since_train >= self.auto_retrain_threshold:
            return self.retrain()
        return False

    def retrain(self, method: str = "isotonic") -> bool:
        """Trainiere Kalibrator mit aktuellen Daten."""
        if len(self.training_data) < 10:
            return False

        # Verwende nur neuere Daten (Sliding Window)
        recent_conf, recent_act = self.training_data.get_recent_samples(max_age_days=60)

        if len(recent_conf) < 10:
            recent_conf = self.training_data.confidences
            recent_act = self.training_data.actuals

        # Erstelle und trainiere Kalibrator
        if method == "isotonic":
            self.calibrator = IsotonicCalibrator()
        elif method == "platt":
            self.calibrator = PlattScalingCalibrator()
        elif method == "temperature":
            self.calibrator = TemperatureScalingCalibrator()
        else:
            self.calibrator = HistogramBinningCalibrator()

        self.calibrator.fit(recent_conf, recent_act)
        self._samples_since_train = 0

        # Berechne und speichere Statistiken nach Training
        self._update_stats(recent_conf, recent_act)

        logger.debug(
            "backend_doctype_calibrator_retrained",
            backend=self.backend,
            doc_type=self.doc_type,
            samples=len(recent_conf)
        )
        return True

    def _update_stats(self, confidences: List[float], actuals: List[int]) -> None:
        """Aktualisiere Statistiken nach Training."""
        if self.calibrator is None or len(confidences) == 0:
            return

        raw_mean = sum(confidences) / len(confidences)
        raw_std = (sum((x - raw_mean) ** 2 for x in confidences) / len(confidences)) ** 0.5

        calibrated = [self.calibrator.predict(c) for c in confidences]
        cal_mean = sum(calibrated) / len(calibrated)
        cal_std = (sum((x - cal_mean) ** 2 for x in calibrated) / len(calibrated)) ** 0.5

        self.stats = CalibrationStats(
            backend=self.backend,
            samples_count=len(confidences),
            raw_mean=raw_mean,
            raw_std=raw_std,
            calibrated_mean=cal_mean,
            calibrated_std=cal_std,
        )

    def predict(self, confidence: float) -> float:
        """Kalibriere Confidence-Wert."""
        if self.calibrator is None:
            return confidence
        return self.calibrator.predict(confidence)

    def get_stats(self) -> Optional[Dict[str, Any]]:
        """Hole Statistiken mit None-Check.

        Returns:
            Dict mit Statistiken oder None wenn keine vorhanden
        """
        if self.stats is None:
            return None
        return self.stats.to_dict()


class IsotonicCalibrator:
    """
    Isotonic Regression Kalibrator.

    Non-parametrische Kalibrierung die monotone Transformation lernt.
    Beste Methode wenn genug Trainings-Daten vorhanden (>100 Samples).
    """

    def __init__(self):
        """Initialisiere Isotonic Calibrator."""
        self._fitted = False
        self._boundaries: List[float] = []
        self._calibrated_values: List[float] = []

    def fit(self, confidences: List[float], actuals: List[int]) -> None:
        """
        Trainiere Isotonic Regression.

        Args:
            confidences: Rohe Confidence-Scores
            actuals: Tatsächliche Korrektheit (1=korrekt, 0=falsch)
        """
        if len(confidences) < 10:
            logger.warning("isotonic_insufficient_data", count=len(confidences))
            return

        # Sortiere nach Confidence
        sorted_pairs = sorted(zip(confidences, actuals), key=lambda x: x[0])
        sorted_conf = [p[0] for p in sorted_pairs]
        sorted_actual = [p[1] for p in sorted_pairs]

        # Pool Adjacent Violators (PAV) Algorithmus
        n = len(sorted_conf)
        y = list(sorted_actual)
        w = [1.0] * n

        # PAV: Merge violators
        i = 0
        while i < n - 1:
            if y[i] > y[i + 1]:
                # Violation found - merge pools
                total_weight = w[i] + w[i + 1]
                weighted_mean = (y[i] * w[i] + y[i + 1] * w[i + 1]) / total_weight

                y[i] = weighted_mean
                w[i] = total_weight

                # Remove merged element
                y.pop(i + 1)
                w.pop(i + 1)
                sorted_conf.pop(i + 1)
                n -= 1

                # Check backwards
                if i > 0:
                    i -= 1
            else:
                i += 1

        # Store boundaries and values
        self._boundaries = sorted_conf
        self._calibrated_values = y
        self._fitted = True

        logger.info(
            "isotonic_calibrator_fitted",
            segments=len(self._boundaries),
            samples=len(confidences)
        )

    def predict(self, confidence: float) -> float:
        """
        Kalibriere einzelnen Confidence-Wert.

        Args:
            confidence: Roher Confidence-Score

        Returns:
            Kalibrierter Confidence-Score
        """
        if not self._fitted or not self._boundaries:
            return confidence

        # Binary search für richtige Position
        n = len(self._boundaries)

        if confidence <= self._boundaries[0]:
            return self._calibrated_values[0]
        if confidence >= self._boundaries[-1]:
            return self._calibrated_values[-1]

        # Interpolation
        for i in range(n - 1):
            if self._boundaries[i] <= confidence < self._boundaries[i + 1]:
                # Lineare Interpolation
                ratio = (confidence - self._boundaries[i]) / (
                    self._boundaries[i + 1] - self._boundaries[i]
                )
                return (
                    self._calibrated_values[i] +
                    ratio * (self._calibrated_values[i + 1] - self._calibrated_values[i])
                )

        return confidence


class PlattScalingCalibrator:
    """
    Platt Scaling Kalibrator.

    Logistische Regression Kalibrierung: P(correct | confidence) = sigmoid(A * conf + B)
    Einfacher als Isotonic, funktioniert auch mit weniger Daten.
    """

    def __init__(self):
        """Initialisiere Platt Scaling Calibrator."""
        self._fitted = False
        self._a: float = 1.0
        self._b: float = 0.0

    def fit(
        self,
        confidences: List[float],
        actuals: List[int],
        max_iter: int = 100,
        learning_rate: float = 0.1
    ) -> None:
        """
        Trainiere Platt Scaling via Gradient Descent.

        Args:
            confidences: Rohe Confidence-Scores
            actuals: Tatsächliche Korrektheit (1=korrekt, 0=falsch)
            max_iter: Maximale Iterationen
            learning_rate: Lernrate
        """
        if len(confidences) < 5:
            logger.warning("platt_insufficient_data", count=len(confidences))
            return

        a, b = 1.0, 0.0
        n = len(confidences)

        for _ in range(max_iter):
            grad_a, grad_b = 0.0, 0.0

            for conf, actual in zip(confidences, actuals):
                pred = self._sigmoid(a * conf + b)
                error = pred - actual
                grad_a += error * conf
                grad_b += error

            # Update parameters
            a -= learning_rate * grad_a / n
            b -= learning_rate * grad_b / n

        self._a = a
        self._b = b
        self._fitted = True

        logger.info("platt_calibrator_fitted", a=round(a, 4), b=round(b, 4))

    def predict(self, confidence: float) -> float:
        """Kalibriere einzelnen Confidence-Wert."""
        if not self._fitted:
            return confidence
        return self._sigmoid(self._a * confidence + self._b)

    @staticmethod
    def _sigmoid(x: float) -> float:
        """Sigmoid-Funktion mit Overflow-Schutz."""
        if x < -500:
            return 0.0
        if x > 500:
            return 1.0
        return 1.0 / (1.0 + math.exp(-x))


class TemperatureScalingCalibrator:
    """
    Temperature Scaling Kalibrator.

    Einfachste Methode: Division durch Temperature-Parameter T.
    calibrated = sigmoid(logit(confidence) / T)
    """

    def __init__(self, temperature: float = 1.0):
        """
        Initialisiere Temperature Scaling Calibrator.

        Args:
            temperature: Initial Temperature (1.0 = keine Kalibrierung)
        """
        self._temperature = temperature
        self._fitted = False

    def fit(
        self,
        confidences: List[float],
        actuals: List[int],
        search_range: Tuple[float, float] = (0.1, 5.0),
        steps: int = 50
    ) -> None:
        """
        Finde optimalen Temperature-Parameter.

        Args:
            confidences: Rohe Confidence-Scores
            actuals: Tatsächliche Korrektheit
            search_range: Suchbereich für Temperature
            steps: Anzahl der Suchschritte
        """
        if len(confidences) < 5:
            return

        best_temp = 1.0
        best_nll = float("inf")

        # Grid Search für Temperature
        for i in range(steps):
            temp = search_range[0] + (search_range[1] - search_range[0]) * i / steps
            nll = self._negative_log_likelihood(confidences, actuals, temp)

            if nll < best_nll:
                best_nll = nll
                best_temp = temp

        self._temperature = best_temp
        self._fitted = True

        logger.info(
            "temperature_calibrator_fitted",
            temperature=round(best_temp, 4),
            nll=round(best_nll, 4)
        )

    def predict(self, confidence: float) -> float:
        """Kalibriere einzelnen Confidence-Wert."""
        if not self._fitted or self._temperature == 1.0:
            return confidence

        # Clamp confidence to avoid log(0)
        conf = max(0.001, min(0.999, confidence))

        # logit -> scale -> sigmoid
        logit = math.log(conf / (1 - conf))
        scaled = logit / self._temperature
        return 1.0 / (1.0 + math.exp(-scaled))

    def _negative_log_likelihood(
        self,
        confidences: List[float],
        actuals: List[int],
        temperature: float
    ) -> float:
        """Berechne Negative Log Likelihood."""
        nll = 0.0
        for conf, actual in zip(confidences, actuals):
            conf = max(0.001, min(0.999, conf))
            logit = math.log(conf / (1 - conf))
            scaled_prob = 1.0 / (1.0 + math.exp(-logit / temperature))

            if actual == 1:
                nll -= math.log(max(1e-10, scaled_prob))
            else:
                nll -= math.log(max(1e-10, 1 - scaled_prob))

        return nll


class HistogramBinningCalibrator:
    """
    Histogram Binning Kalibrator.

    Teilt Confidence-Range in Bins und verwendet durchschnittliche Accuracy pro Bin.
    Einfach und interpretierbar.
    """

    def __init__(self, n_bins: int = 10):
        """
        Initialisiere Histogram Binning Calibrator.

        Args:
            n_bins: Anzahl der Bins (default: 10)
        """
        self._n_bins = n_bins
        self._bin_edges: List[float] = []
        self._bin_values: List[float] = []
        self._fitted = False

    def fit(self, confidences: List[float], actuals: List[int]) -> None:
        """
        Trainiere Histogram Binning.

        Args:
            confidences: Rohe Confidence-Scores
            actuals: Tatsächliche Korrektheit
        """
        if len(confidences) < self._n_bins:
            logger.warning("histogram_insufficient_data", count=len(confidences))
            return

        # Erstelle gleichmäßige Bins
        self._bin_edges = [i / self._n_bins for i in range(self._n_bins + 1)]
        self._bin_values = []

        for i in range(self._n_bins):
            lower = self._bin_edges[i]
            upper = self._bin_edges[i + 1]

            # Samples in diesem Bin
            bin_actuals = [
                a for c, a in zip(confidences, actuals)
                if lower <= c < upper or (i == self._n_bins - 1 and c == upper)
            ]

            # Durchschnittliche Accuracy
            if bin_actuals:
                self._bin_values.append(sum(bin_actuals) / len(bin_actuals))
            else:
                # Keine Samples - verwende Bin-Mitte
                self._bin_values.append((lower + upper) / 2)

        self._fitted = True

        logger.info(
            "histogram_calibrator_fitted",
            n_bins=self._n_bins,
            samples=len(confidences)
        )

    def predict(self, confidence: float) -> float:
        """Kalibriere einzelnen Confidence-Wert."""
        if not self._fitted:
            return confidence

        # Finde passendes Bin
        for i in range(self._n_bins):
            if confidence < self._bin_edges[i + 1]:
                return self._bin_values[i]

        return self._bin_values[-1]


# =============================================================================
# Type Alias für Kalibratoren (nach Klassendefinitionen)
# =============================================================================

# CalibratorType als Union aller Kalibrator-Klassen (Runtime-safe)
CalibratorType = Union[
    IsotonicCalibrator,
    PlattScalingCalibrator,
    TemperatureScalingCalibrator,
    HistogramBinningCalibrator,
]


class ConfidenceCalibrationService:
    """
    Zentraler Service für Confidence Calibration.

    Verwaltet Kalibratoren für verschiedene Backends und bietet
    einheitliche API für Kalibrierung.

    Features:
    - Backend-spezifische Kalibrierung (DeepSeek, GOT-OCR, Surya)
    - Document-Type-spezifische Kalibrierung (Invoice, Letter, Contract)
    - Online Learning mit automatischem Retrain
    - Sliding Window für aktuelle Kalibrierung
    """

    def __init__(
        self,
        calibration_method: str = "isotonic",
        persist_path: Optional[Path] = None,
        enable_doctype_calibration: bool = True,
        auto_retrain_threshold: int = 50,
        sliding_window_days: int = 60
    ):
        """
        Initialisiere Confidence Calibration Service.

        Args:
            calibration_method: Kalibrierungs-Methode
                - "isotonic": Isotonic Regression (empfohlen)
                - "platt": Platt Scaling
                - "temperature": Temperature Scaling
                - "histogram": Histogram Binning
            persist_path: Pfad zum Speichern/Laden von Kalibrierungs-Daten
            enable_doctype_calibration: Aktiviere Dokumenttyp-spezifische Kalibrierung
            auto_retrain_threshold: Anzahl Samples bis automatisches Retrain
            sliding_window_days: Tage für Sliding Window (ältere Daten ignorieren)
        """
        self._method = calibration_method
        self._persist_path = persist_path
        self._enable_doctype = enable_doctype_calibration
        self._auto_retrain_threshold = auto_retrain_threshold
        self._sliding_window_days = sliding_window_days

        # Kalibratoren pro Backend (für generische Kalibrierung)
        self._calibrators: Dict[str, Any] = {}

        # Trainings-Daten pro Backend
        self._training_data: Dict[str, CalibrationData] = {}

        # Statistiken
        self._stats: Dict[str, CalibrationStats] = {}

        # Backend + DocType spezifische Kalibratoren
        # Key: "backend:doctype", z.B. "deepseek:invoice"
        self._doctype_calibrators: Dict[str, BackendDocTypeCalibrator] = {}

        logger.info(
            "confidence_calibration_service_initialized",
            method=calibration_method,
            doctype_enabled=enable_doctype_calibration,
            auto_retrain=auto_retrain_threshold
        )

    def _create_calibrator(self):
        """Erstelle neuen Kalibrator basierend auf Methode."""
        if self._method == "isotonic":
            return IsotonicCalibrator()
        elif self._method == "platt":
            return PlattScalingCalibrator()
        elif self._method == "temperature":
            return TemperatureScalingCalibrator()
        elif self._method == "histogram":
            return HistogramBinningCalibrator()
        else:
            raise ValueError(f"Unbekannte Kalibrierungs-Methode: {self._method}")

    def add_training_sample(
        self,
        backend: str,
        confidence: float,
        is_correct: bool
    ) -> None:
        """
        Füge Trainings-Sample für Kalibrierung hinzu.

        Args:
            backend: OCR Backend Name
            confidence: Roher Confidence-Score
            is_correct: Ob das OCR-Ergebnis korrekt war
        """
        if backend not in self._training_data:
            self._training_data[backend] = CalibrationData()

        self._training_data[backend].add_sample(confidence, is_correct)

    def train(self, backend: str) -> Optional[CalibrationStats]:
        """
        Trainiere Kalibrator für ein Backend.

        Args:
            backend: OCR Backend Name

        Returns:
            CalibrationStats oder None bei Fehler
        """
        if backend not in self._training_data:
            logger.warning("no_training_data", backend=backend)
            return None

        data = self._training_data[backend]
        if len(data) < 10:
            logger.warning(
                "insufficient_training_data",
                backend=backend,
                count=len(data)
            )
            return None

        # Erstelle und trainiere Kalibrator
        calibrator = self._create_calibrator()
        calibrator.fit(data.confidences, data.actuals)
        self._calibrators[backend] = calibrator

        # Berechne Statistiken
        stats = self._calculate_stats(backend, data, calibrator)
        self._stats[backend] = stats

        logger.info(
            "calibrator_trained",
            backend=backend,
            samples=len(data),
            ece=round(stats.ece, 4)
        )

        return stats

    def train_all(self) -> Dict[str, CalibrationStats]:
        """Trainiere Kalibratoren für alle Backends."""
        results = {}
        for backend in self._training_data.keys():
            stats = self.train(backend)
            if stats:
                results[backend] = stats
        return results

    def calibrate(self, backend: str, confidence: float) -> float:
        """
        Kalibriere Confidence-Score.

        Args:
            backend: OCR Backend Name
            confidence: Roher Confidence-Score

        Returns:
            Kalibrierter Confidence-Score
        """
        if backend not in self._calibrators:
            # Kein Kalibrator - gebe rohen Score zurück
            return confidence

        calibrator = self._calibrators[backend]
        return calibrator.predict(confidence)

    def calibrate_batch(
        self,
        backend: str,
        confidences: List[float]
    ) -> List[float]:
        """Kalibriere Liste von Confidence-Scores."""
        return [self.calibrate(backend, c) for c in confidences]

    # =========================================================================
    # Document-Type-Specific Calibration Methods
    # =========================================================================

    def _get_doctype_key(self, backend: str, doc_type: str) -> str:
        """Erstelle Key für Backend + DocType Kombination."""
        return f"{backend}:{doc_type}"

    def add_doctype_training_sample(
        self,
        backend: str,
        doc_type: str,
        confidence: float,
        is_correct: bool
    ) -> bool:
        """
        Füge Trainings-Sample für Backend + Dokumenttyp hinzu.

        Args:
            backend: OCR Backend Name (z.B. "deepseek")
            doc_type: Dokumenttyp (z.B. "invoice", "letter")
            confidence: Roher Confidence-Score
            is_correct: Ob das OCR-Ergebnis korrekt war

        Returns:
            True wenn automatisches Retrain durchgeführt wurde
        """
        if not self._enable_doctype:
            # Fallback auf generische Kalibrierung
            self.add_training_sample(backend, confidence, is_correct)
            return False

        key = self._get_doctype_key(backend, doc_type)

        if key not in self._doctype_calibrators:
            self._doctype_calibrators[key] = BackendDocTypeCalibrator(
                backend=backend,
                doc_type=doc_type,
                auto_retrain_threshold=self._auto_retrain_threshold
            )

        retrained = self._doctype_calibrators[key].add_sample(confidence, is_correct)

        # Auch zur generischen Kalibrierung hinzufügen
        self.add_training_sample(backend, confidence, is_correct)

        if retrained:
            logger.info(
                "doctype_calibrator_auto_retrained",
                backend=backend,
                doc_type=doc_type
            )

        return retrained

    def calibrate_with_doctype(
        self,
        backend: str,
        doc_type: str,
        confidence: float
    ) -> float:
        """
        Kalibriere Confidence-Score mit Dokumenttyp-spezifischer Kalibrierung.

        Verwendet hierarchische Fallback-Strategie:
        1. Backend + DocType spezifischer Kalibrator (wenn genug Daten)
        2. Backend-generischer Kalibrator
        3. Roher Confidence-Wert

        Args:
            backend: OCR Backend Name
            doc_type: Dokumenttyp
            confidence: Roher Confidence-Score

        Returns:
            Kalibrierter Confidence-Score
        """
        if self._enable_doctype:
            key = self._get_doctype_key(backend, doc_type)

            if key in self._doctype_calibrators:
                calibrator = self._doctype_calibrators[key]
                if calibrator.calibrator is not None:
                    return calibrator.predict(confidence)

        # Fallback auf Backend-generische Kalibrierung
        return self.calibrate(backend, confidence)

    def train_doctype_calibrator(
        self,
        backend: str,
        doc_type: str
    ) -> bool:
        """
        Trainiere Kalibrator für Backend + Dokumenttyp.

        Args:
            backend: OCR Backend Name
            doc_type: Dokumenttyp

        Returns:
            True wenn erfolgreich trainiert
        """
        key = self._get_doctype_key(backend, doc_type)

        if key not in self._doctype_calibrators:
            logger.warning(
                "no_doctype_training_data",
                backend=backend,
                doc_type=doc_type
            )
            return False

        return self._doctype_calibrators[key].retrain(method=self._method)

    def train_all_doctype_calibrators(self) -> Dict[str, bool]:
        """Trainiere alle Dokumenttyp-spezifischen Kalibratoren."""
        results = {}
        for key, calibrator in self._doctype_calibrators.items():
            results[key] = calibrator.retrain(method=self._method)
        return results

    def get_doctype_stats(
        self,
        backend: Optional[str] = None,
        doc_type: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Hole Statistiken für Dokumenttyp-spezifische Kalibrierung.

        Args:
            backend: Optional - Filter auf Backend
            doc_type: Optional - Filter auf Dokumenttyp

        Returns:
            Dict mit Statistiken
        """
        stats = {}

        for key, calibrator in self._doctype_calibrators.items():
            b, dt = key.split(":")

            if backend and b != backend:
                continue
            if doc_type and dt != doc_type:
                continue

            # Nutze get_stats() mit None-Check
            calibrator_stats = calibrator.get_stats()

            stats[key] = {
                "backend": b,
                "doc_type": dt,
                "samples": len(calibrator.training_data),
                "has_calibrator": calibrator.calibrator is not None,
                "samples_since_train": calibrator._samples_since_train,
                "calibration_stats": calibrator_stats,  # None wenn nicht trainiert
            }

        return stats

    def get_best_backend_for_doctype(self, doc_type: str) -> Optional[str]:
        """
        Finde das beste Backend für einen Dokumenttyp basierend auf Kalibrierungsdaten.

        Args:
            doc_type: Dokumenttyp

        Returns:
            Backend Name oder None
        """
        best_backend = None
        best_accuracy = 0.0

        for key, calibrator in self._doctype_calibrators.items():
            b, dt = key.split(":")
            if dt != doc_type:
                continue

            if len(calibrator.training_data) >= 10:
                accuracy = sum(calibrator.training_data.actuals) / len(calibrator.training_data)
                if accuracy > best_accuracy:
                    best_accuracy = accuracy
                    best_backend = b

        return best_backend

    def _calculate_stats(
        self,
        backend: str,
        data: CalibrationData,
        calibrator
    ) -> CalibrationStats:
        """Berechne Kalibrierungs-Statistiken."""
        raw = data.confidences
        actuals = data.actuals
        calibrated = [calibrator.predict(c) for c in raw]

        # Grundlegende Statistiken
        raw_mean = sum(raw) / len(raw)
        raw_std = (sum((x - raw_mean) ** 2 for x in raw) / len(raw)) ** 0.5
        cal_mean = sum(calibrated) / len(calibrated)
        cal_std = (sum((x - cal_mean) ** 2 for x in calibrated) / len(calibrated)) ** 0.5

        # Expected Calibration Error (ECE) und Maximum Calibration Error (MCE)
        ece_raw = self._calculate_ece(raw, actuals)
        ece_cal = self._calculate_ece(calibrated, actuals)
        mce = self._calculate_mce(calibrated, actuals)

        improvement = (ece_raw - ece_cal) / max(0.001, ece_raw)

        return CalibrationStats(
            backend=backend,
            samples_count=len(data),
            raw_mean=raw_mean,
            raw_std=raw_std,
            calibrated_mean=cal_mean,
            calibrated_std=cal_std,
            ece=ece_cal,
            mce=mce,
            reliability_improvement=improvement
        )

    def _calculate_ece(
        self,
        confidences: List[float],
        actuals: List[int],
        n_bins: int = 10
    ) -> float:
        """
        Berechne Expected Calibration Error.

        ECE misst wie gut Confidence die tatsächliche Accuracy reflektiert.
        """
        ece = 0.0
        n = len(confidences)

        for i in range(n_bins):
            lower = i / n_bins
            upper = (i + 1) / n_bins

            # Samples in diesem Bin
            bin_pairs = [
                (c, a) for c, a in zip(confidences, actuals)
                if lower <= c < upper or (i == n_bins - 1 and c == upper)
            ]

            if bin_pairs:
                bin_conf = [p[0] for p in bin_pairs]
                bin_actual = [p[1] for p in bin_pairs]

                avg_conf = sum(bin_conf) / len(bin_conf)
                avg_acc = sum(bin_actual) / len(bin_actual)

                ece += len(bin_pairs) / n * abs(avg_acc - avg_conf)

        return ece

    def _calculate_mce(
        self,
        confidences: List[float],
        actuals: List[int],
        n_bins: int = 10
    ) -> float:
        """Berechne Maximum Calibration Error."""
        mce = 0.0

        for i in range(n_bins):
            lower = i / n_bins
            upper = (i + 1) / n_bins

            bin_pairs = [
                (c, a) for c, a in zip(confidences, actuals)
                if lower <= c < upper or (i == n_bins - 1 and c == upper)
            ]

            if bin_pairs:
                bin_conf = [p[0] for p in bin_pairs]
                bin_actual = [p[1] for p in bin_pairs]

                avg_conf = sum(bin_conf) / len(bin_conf)
                avg_acc = sum(bin_actual) / len(bin_actual)

                mce = max(mce, abs(avg_acc - avg_conf))

        return mce

    def get_stats(self, backend: Optional[str] = None) -> Dict[str, Any]:
        """Hole Kalibrierungs-Statistiken."""
        if backend:
            if backend in self._stats:
                return self._stats[backend].to_dict()
            return {}

        return {b: s.to_dict() for b, s in self._stats.items()}

    def save(self, path: Optional[Path] = None) -> bool:
        """Speichere Kalibrierungs-Daten."""
        save_path = path or self._persist_path
        if not save_path:
            return False

        try:
            data = {
                "method": self._method,
                "training_data": {
                    backend: {
                        "confidences": d.confidences,
                        "actuals": d.actuals
                    }
                    for backend, d in self._training_data.items()
                },
                "stats": {
                    backend: s.to_dict()
                    for backend, s in self._stats.items()
                }
            }

            save_path.parent.mkdir(parents=True, exist_ok=True)
            with open(save_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)

            logger.info("calibration_data_saved", path=str(save_path))
            return True

        except Exception as e:
            logger.error("calibration_save_failed", **safe_error_log(e))
            return False

    def load(self, path: Optional[Path] = None) -> bool:
        """Lade Kalibrierungs-Daten."""
        load_path = path or self._persist_path
        if not load_path or not load_path.exists():
            return False

        try:
            with open(load_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            self._method = data.get("method", self._method)

            for backend, td in data.get("training_data", {}).items():
                self._training_data[backend] = CalibrationData(
                    confidences=td["confidences"],
                    actuals=td["actuals"]
                )

            # Re-train calibrators
            self.train_all()

            logger.info("calibration_data_loaded", path=str(load_path))
            return True

        except Exception as e:
            logger.error("calibration_load_failed", **safe_error_log(e))
            return False


# =============================================================================
# Singleton und Convenience-Funktionen
# =============================================================================

_calibration_service: Optional[ConfidenceCalibrationService] = None


def get_calibration_service(
    method: str = "isotonic"
) -> ConfidenceCalibrationService:
    """
    Hole Singleton-Instanz des Calibration Service.

    Args:
        method: Kalibrierungs-Methode

    Returns:
        ConfidenceCalibrationService-Instanz
    """
    global _calibration_service
    if _calibration_service is None:
        _calibration_service = ConfidenceCalibrationService(
            calibration_method=method,
            persist_path=Path("data/calibration/calibration_data.json")
        )
    return _calibration_service


def calibrate_confidence(backend: str, confidence: float) -> float:
    """
    Convenience-Funktion zum Kalibrieren eines Confidence-Scores.

    Args:
        backend: OCR Backend Name
        confidence: Roher Confidence-Score

    Returns:
        Kalibrierter Confidence-Score
    """
    service = get_calibration_service()
    return service.calibrate(backend, confidence)
