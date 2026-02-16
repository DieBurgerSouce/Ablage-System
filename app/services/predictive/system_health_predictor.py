# -*- coding: utf-8 -*-
"""
System Health Predictor.

Prognostiziert Ressourcen-Erschoepfung:
- GPU VRAM Overflow
- Queue Overflow
- Disk Space Erschoepfung
- Worker Health Degradation

Verwendet EMA (Exponential Moving Average) und Lineare Regression.

Vision 2.0 Feature: Predictive Maintenance (Phase 5)
Feinpoliert und durchdacht.
"""

import logging
import math
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Deque, Dict, List, Optional, Tuple, Union
from typing_extensions import TypedDict
from uuid import UUID

import numpy as np

logger = logging.getLogger(__name__)

# Type definitions for mypy strict mode
MetadataValue = Union[str, int, float, bool, None]
MetadataDict = Dict[str, MetadataValue]


class PredictionResultDict(TypedDict):
    """Typed dictionary for PredictionResult serialization."""
    metric: str
    current_value: float
    predicted_value: float
    threshold: float
    eta_minutes: Optional[float]
    trend_per_minute: float
    severity: str
    recommendation: str
    confidence: float
    prediction_time: str


class PredictionSeverity(str, Enum):
    """Schweregrad der Vorhersage."""
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class MetricType(str, Enum):
    """Typen von überwachten Metriken."""
    GPU_VRAM = "gpu_vram"
    GPU_UTILIZATION = "gpu_utilization"
    QUEUE_DEPTH = "queue_depth"
    DISK_USAGE = "disk_usage"
    WORKER_FAILURES = "worker_failures"
    MEMORY_USAGE = "memory_usage"
    CPU_USAGE = "cpu_usage"


@dataclass
class MetricDataPoint:
    """Ein einzelner Datenpunkt einer Metrik."""
    timestamp: datetime
    value: float
    metadata: MetadataDict = field(default_factory=dict)


@dataclass
class PredictionResult:
    """Ergebnis einer Vorhersage."""
    metric: MetricType
    current_value: float
    predicted_value: float
    threshold: float
    eta_minutes: Optional[float]  # None wenn kein Overflow erwartet
    trend: float  # Steigung pro Minute
    severity: PredictionSeverity
    recommendation: str
    confidence: float  # 0-1
    prediction_time: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: MetadataDict = field(default_factory=dict)

    def to_dict(self) -> PredictionResultDict:
        """Konvertiert zu Dictionary."""
        return PredictionResultDict(
            metric=self.metric.value,
            current_value=round(self.current_value, 2),
            predicted_value=round(self.predicted_value, 2),
            threshold=self.threshold,
            eta_minutes=round(self.eta_minutes, 1) if self.eta_minutes else None,
            trend_per_minute=round(self.trend, 4),
            severity=self.severity.value,
            recommendation=self.recommendation,
            confidence=round(self.confidence, 2),
            prediction_time=self.prediction_time.isoformat(),
        )


@dataclass
class PredictorConfig:
    """Konfiguration für den Predictor."""
    # Datensammlung
    max_history_points: int = 60  # Letzte 60 Datenpunkte
    collection_interval_seconds: int = 60  # Alle 60 Sekunden

    # GPU VRAM
    gpu_vram_total_gb: float = 16.0  # RTX 4080
    gpu_vram_warning_threshold: float = 0.85  # 85%
    gpu_vram_critical_threshold: float = 0.90  # 90%

    # Queues
    queue_warning_depth: int = 100
    queue_critical_depth: int = 500

    # Disk
    disk_warning_threshold: float = 0.85
    disk_critical_threshold: float = 0.95

    # Prediction
    ema_alpha: float = 0.3  # EMA Smoothing Factor
    min_points_for_prediction: int = 5
    prediction_horizon_minutes: int = 10


class MetricHistory:
    """Speichert historische Metrik-Daten."""

    def __init__(self, max_size: int = 60) -> None:
        """Initialisiert die History."""
        self._data: Deque[MetricDataPoint] = deque(maxlen=max_size)

    def add(self, value: float, metadata: Optional[MetadataDict] = None) -> None:
        """Fuegt Datenpunkt hinzu."""
        self._data.append(MetricDataPoint(
            timestamp=datetime.now(timezone.utc),
            value=value,
            metadata=metadata or {}
        ))

    def get_values(self, last_n: Optional[int] = None) -> List[float]:
        """Gibt letzte N Werte zurück."""
        if last_n is None:
            return [dp.value for dp in self._data]
        return [dp.value for dp in list(self._data)[-last_n:]]

    def get_timestamps(self, last_n: Optional[int] = None) -> List[datetime]:
        """Gibt letzte N Timestamps zurück."""
        if last_n is None:
            return [dp.timestamp for dp in self._data]
        return [dp.timestamp for dp in list(self._data)[-last_n:]]

    def __len__(self) -> int:
        return len(self._data)

    def clear(self) -> None:
        self._data.clear()


class SystemHealthPredictor:
    """
    Prognostiziert System-Gesundheit und Ressourcen-Erschoepfung.

    Verwendet:
    - EMA für geglättete Trendanalyse
    - Lineare Regression für Zeitvorhersage
    - Konfidenzintervalle für Unsicherheit
    """

    def __init__(self, config: Optional[PredictorConfig] = None) -> None:
        """Initialisiert den Predictor."""
        self.config = config or PredictorConfig()

        # Metrik-Historien
        self._histories: Dict[str, MetricHistory] = {
            MetricType.GPU_VRAM.value: MetricHistory(self.config.max_history_points),
            MetricType.GPU_UTILIZATION.value: MetricHistory(self.config.max_history_points),
            MetricType.QUEUE_DEPTH.value: MetricHistory(self.config.max_history_points),
            MetricType.DISK_USAGE.value: MetricHistory(self.config.max_history_points),
            MetricType.WORKER_FAILURES.value: MetricHistory(self.config.max_history_points),
            MetricType.MEMORY_USAGE.value: MetricHistory(self.config.max_history_points),
            MetricType.CPU_USAGE.value: MetricHistory(self.config.max_history_points),
        }

        # Queue-spezifische Historien
        self._queue_histories: Dict[str, MetricHistory] = {}

        logger.info(
            "system_health_predictor_initialized",
            max_history=self.config.max_history_points,
            ema_alpha=self.config.ema_alpha
        )

    def record_metric(
        self,
        metric: MetricType,
        value: float,
        metadata: Optional[MetadataDict] = None
    ) -> None:
        """
        Zeichnet einen Metrik-Wert auf.

        Args:
            metric: Metrik-Typ
            value: Aktueller Wert
            metadata: Zusätzliche Informationen
        """
        history = self._histories.get(metric.value)
        if history:
            history.add(value, metadata)

    def record_queue_metric(
        self,
        queue_name: str,
        depth: int
    ) -> None:
        """
        Zeichnet Queue-Tiefe auf.

        Args:
            queue_name: Name der Queue (ocr, high_priority, default)
            depth: Aktuelle Tiefe
        """
        if queue_name not in self._queue_histories:
            self._queue_histories[queue_name] = MetricHistory(
                self.config.max_history_points
            )
        self._queue_histories[queue_name].add(float(depth))

    def _calculate_ema(self, values: List[float]) -> List[float]:
        """Berechnet EMA (Exponential Moving Average)."""
        if not values:
            return []

        alpha = self.config.ema_alpha
        ema = [values[0]]

        for i in range(1, len(values)):
            ema.append(alpha * values[i] + (1 - alpha) * ema[-1])

        return ema

    def _linear_regression(self, values: List[float]) -> Tuple[float, float, float]:
        """
        Führt lineare Regression durch.

        Returns:
            Tuple von (slope, intercept, r_squared)
        """
        n = len(values)
        if n < 2:
            return 0.0, values[0] if values else 0.0, 0.0

        x = np.arange(n)
        y = np.array(values)

        # Lineare Regression
        x_mean = np.mean(x)
        y_mean = np.mean(y)

        numerator = np.sum((x - x_mean) * (y - y_mean))
        denominator = np.sum((x - x_mean) ** 2)

        if denominator == 0:
            return 0.0, y_mean, 0.0

        slope = numerator / denominator
        intercept = y_mean - slope * x_mean

        # R-squared
        y_pred = slope * x + intercept
        ss_res = np.sum((y - y_pred) ** 2)
        ss_tot = np.sum((y - y_mean) ** 2)
        r_squared = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0.0

        return slope, intercept, max(0, r_squared)

    def _predict_time_to_threshold(
        self,
        current: float,
        slope: float,
        threshold: float
    ) -> Optional[float]:
        """
        Berechnet Zeit bis Threshold erreicht wird.

        Args:
            current: Aktueller Wert
            slope: Steigung pro Datenpunkt
            threshold: Zielwert

        Returns:
            Minuten bis Threshold oder None wenn nicht erreichbar
        """
        if slope <= 0:
            return None  # Trend ist fallend oder stabil

        if current >= threshold:
            return 0.0  # Bereits überschritten

        # Datenpunkte pro Minute
        points_per_minute = 60.0 / self.config.collection_interval_seconds

        # Datenpunkte bis Threshold
        points_to_threshold = (threshold - current) / slope

        # Minuten
        return points_to_threshold / points_per_minute

    async def predict_gpu_vram_overflow(self) -> Optional[PredictionResult]:
        """
        Prognostiziert GPU VRAM Overflow.

        Returns:
            PredictionResult oder None wenn keine Vorhersage möglich
        """
        history = self._histories[MetricType.GPU_VRAM.value]
        values = history.get_values()

        if len(values) < self.config.min_points_for_prediction:
            return None

        # EMA für geglättete Werte
        ema_values = self._calculate_ema(values)
        current = ema_values[-1]

        # Lineare Regression
        slope, _, r_squared = self._linear_regression(ema_values)

        # Threshold in GB
        vram_total = self.config.gpu_vram_total_gb
        warning_threshold = vram_total * self.config.gpu_vram_warning_threshold
        critical_threshold = vram_total * self.config.gpu_vram_critical_threshold

        # Zeit bis Threshold
        eta_warning = self._predict_time_to_threshold(current, slope, warning_threshold)
        eta_critical = self._predict_time_to_threshold(current, slope, critical_threshold)

        # Schweregrad bestimmen
        severity = PredictionSeverity.INFO
        eta = eta_warning
        threshold = warning_threshold

        if eta_critical is not None and eta_critical < 5:
            severity = PredictionSeverity.CRITICAL
            eta = eta_critical
            threshold = critical_threshold
        elif eta_warning is not None and eta_warning < 10:
            severity = PredictionSeverity.WARNING
            eta = eta_warning

        # Keine Warnung noetig wenn Trend negativ oder weit entfernt
        if slope <= 0 or (eta is not None and eta > 30):
            return PredictionResult(
                metric=MetricType.GPU_VRAM,
                current_value=current,
                predicted_value=current + slope * 10,  # In 10 Punkten
                threshold=warning_threshold,
                eta_minutes=None,
                trend=slope,
                severity=PredictionSeverity.INFO,
                recommendation="GPU VRAM stabil. Keine Aktion erforderlich.",
                confidence=r_squared,
                metadata={"unit": "GB", "total": vram_total}
            )

        # Recommendation basierend auf Schweregrad
        if severity == PredictionSeverity.CRITICAL:
            recommendation = (
                "KRITISCH: GPU VRAM Overflow in weniger als 5 Minuten erwartet. "
                "Sofort Batch-Size reduzieren oder GPU-Cleanup starten."
            )
        else:
            recommendation = (
                "WARNUNG: GPU VRAM steigt an. "
                "Batch-Size reduzieren oder nicht-kritische GPU-Tasks pausieren."
            )

        return PredictionResult(
            metric=MetricType.GPU_VRAM,
            current_value=current,
            predicted_value=threshold,
            threshold=threshold,
            eta_minutes=eta,
            trend=slope,
            severity=severity,
            recommendation=recommendation,
            confidence=r_squared,
            metadata={"unit": "GB", "total": vram_total}
        )

    async def predict_queue_overflow(
        self,
        queue_name: str = "default"
    ) -> Optional[PredictionResult]:
        """
        Prognostiziert Queue Overflow.

        Args:
            queue_name: Name der Queue

        Returns:
            PredictionResult oder None
        """
        history = self._queue_histories.get(queue_name)
        if not history or len(history) < self.config.min_points_for_prediction:
            return None

        values = history.get_values()
        ema_values = self._calculate_ema(values)
        current = ema_values[-1]

        slope, _, r_squared = self._linear_regression(ema_values)

        warning_threshold = float(self.config.queue_warning_depth)
        critical_threshold = float(self.config.queue_critical_depth)

        eta_warning = self._predict_time_to_threshold(current, slope, warning_threshold)
        eta_critical = self._predict_time_to_threshold(current, slope, critical_threshold)

        # Schweregrad
        severity = PredictionSeverity.INFO
        eta = eta_warning
        threshold = warning_threshold

        if eta_critical is not None and eta_critical < 10:
            severity = PredictionSeverity.CRITICAL
            eta = eta_critical
            threshold = critical_threshold
        elif eta_warning is not None and eta_warning < 15:
            severity = PredictionSeverity.WARNING

        if slope <= 0 or (eta is not None and eta > 30):
            return PredictionResult(
                metric=MetricType.QUEUE_DEPTH,
                current_value=current,
                predicted_value=current,
                threshold=warning_threshold,
                eta_minutes=None,
                trend=slope,
                severity=PredictionSeverity.INFO,
                recommendation=f"Queue '{queue_name}' stabil.",
                confidence=r_squared,
                metadata={"queue_name": queue_name}
            )

        if severity == PredictionSeverity.CRITICAL:
            recommendation = (
                f"KRITISCH: Queue '{queue_name}' droht überzulaufen. "
                "Zusätzliche Worker starten oder Rate-Limiting aktivieren."
            )
        else:
            recommendation = (
                f"WARNUNG: Queue '{queue_name}' waechst. "
                "Workload beobachten und ggf. skalieren."
            )

        return PredictionResult(
            metric=MetricType.QUEUE_DEPTH,
            current_value=current,
            predicted_value=threshold,
            threshold=threshold,
            eta_minutes=eta,
            trend=slope,
            severity=severity,
            recommendation=recommendation,
            confidence=r_squared,
            metadata={"queue_name": queue_name}
        )

    async def predict_disk_exhaustion(self) -> Optional[PredictionResult]:
        """
        Prognostiziert Disk Space Erschoepfung.

        Returns:
            PredictionResult oder None
        """
        history = self._histories[MetricType.DISK_USAGE.value]
        values = history.get_values()

        if len(values) < self.config.min_points_for_prediction:
            return None

        ema_values = self._calculate_ema(values)
        current = ema_values[-1]  # Als Prozent

        slope, _, r_squared = self._linear_regression(ema_values)

        warning_threshold = self.config.disk_warning_threshold * 100
        critical_threshold = self.config.disk_critical_threshold * 100

        eta = self._predict_time_to_threshold(current, slope, critical_threshold)

        # Konvertiere zu Tagen für Disk (langsamerer Prozess)
        eta_days = eta / (60 * 24) if eta else None

        if slope <= 0 or (eta_days is not None and eta_days > 7):
            severity = PredictionSeverity.INFO
            recommendation = "Disk Space stabil."
        elif eta_days is not None and eta_days < 1:
            severity = PredictionSeverity.CRITICAL
            recommendation = (
                "KRITISCH: Disk Space in weniger als 24 Stunden erschoepft. "
                "Sofort alte Dateien löschen oder Storage erweitern."
            )
        elif eta_days is not None and eta_days < 7:
            severity = PredictionSeverity.WARNING
            recommendation = (
                "WARNUNG: Disk Space wird in wenigen Tagen erschoepft. "
                "Cleanup planen oder Storage erweitern."
            )
        else:
            severity = PredictionSeverity.INFO
            recommendation = "Disk Space ausreichend."

        return PredictionResult(
            metric=MetricType.DISK_USAGE,
            current_value=current,
            predicted_value=critical_threshold,
            threshold=critical_threshold,
            eta_minutes=eta,
            trend=slope,
            severity=severity,
            recommendation=recommendation,
            confidence=r_squared,
            metadata={"unit": "percent", "eta_days": eta_days}
        )

    async def get_all_predictions(self) -> List[PredictionResult]:
        """
        Führt alle Vorhersagen aus und gibt Liste zurück.

        Returns:
            Liste von PredictionResult
        """
        predictions: List[PredictionResult] = []

        # GPU VRAM
        gpu_pred = await self.predict_gpu_vram_overflow()
        if gpu_pred:
            predictions.append(gpu_pred)

        # Queues
        for queue_name in self._queue_histories.keys():
            queue_pred = await self.predict_queue_overflow(queue_name)
            if queue_pred:
                predictions.append(queue_pred)

        # Disk
        disk_pred = await self.predict_disk_exhaustion()
        if disk_pred:
            predictions.append(disk_pred)

        return predictions

    def get_metric_history(
        self,
        metric: MetricType,
        last_n: Optional[int] = None
    ) -> List[MetricDataPoint]:
        """Gibt Metrik-History zurück."""
        history = self._histories.get(metric.value)
        if not history:
            return []
        return list(history._data)[-last_n:] if last_n else list(history._data)

    def clear_history(self, metric: Optional[MetricType] = None) -> None:
        """Löscht History."""
        if metric:
            history = self._histories.get(metric.value)
            if history:
                history.clear()
        else:
            for h in self._histories.values():
                h.clear()
            for h in self._queue_histories.values():
                h.clear()


# Singleton-Instanz
_health_predictor: Optional[SystemHealthPredictor] = None


def get_health_predictor() -> SystemHealthPredictor:
    """Gibt Singleton-Instanz des Health Predictors zurück."""
    global _health_predictor
    if _health_predictor is None:
        _health_predictor = SystemHealthPredictor()
    return _health_predictor
