# -*- coding: utf-8 -*-
"""
OCR Quality Forecaster.

Erkennt Qualitäts-Degradation bei OCR-Backends:
- CER/WER Trend-Analyse
- Backend-spezifische Überwachung
- Automatische Retraining-Empfehlungen

Vision 2.0 Feature: Predictive Maintenance (Phase 5)
Feinpoliert und durchdacht.
"""

import logging
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Deque, Dict, List, Optional, Tuple, Union
from typing_extensions import TypedDict

import numpy as np

logger = logging.getLogger(__name__)

# Type definitions for mypy strict mode
MetadataValue = Union[str, int, float, bool, None]
MetadataDict = Dict[str, MetadataValue]


class DegradationAlertDict(TypedDict):
    """Typed dictionary for DegradationAlert serialization."""
    backend: str
    metric: str
    current_value: float
    threshold: float
    trend_per_day: float
    days_to_threshold: Optional[float]
    severity: str
    recommendation: str
    confidence: float
    detected_at: str


class MetricStatsDict(TypedDict, total=False):
    """Typed dictionary for metric statistics."""
    current: float
    avg_24h: float
    min_24h: float
    max_24h: float
    samples: int


class QualitySummaryDict(TypedDict):
    """Typed dictionary for quality summary."""
    backend: str
    metrics: Dict[str, MetricStatsDict]


class QualityMetric(str, Enum):
    """OCR Qualitätsmetriken."""
    CER = "cer"  # Character Error Rate
    WER = "wer"  # Word Error Rate
    CONFIDENCE = "confidence"
    UMLAUT_ACCURACY = "umlaut_accuracy"


class OCRBackend(str, Enum):
    """Unterstützte OCR-Backends."""
    DEEPSEEK = "deepseek"
    GOT_OCR = "got_ocr"
    SURYA = "surya"
    SURYA_GPU = "surya_gpu"


@dataclass
class QualityDataPoint:
    """Ein einzelner Qualitäts-Datenpunkt."""
    timestamp: datetime
    value: float
    backend: OCRBackend
    document_count: int = 1
    metadata: MetadataDict = field(default_factory=dict)


@dataclass
class DegradationAlert:
    """Warnung bei Qualitäts-Degradation."""
    backend: OCRBackend
    metric: QualityMetric
    current_value: float
    threshold: float
    trend_per_day: float
    days_to_threshold: Optional[float]
    severity: str  # info, warning, critical
    recommendation: str
    confidence: float
    detected_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: MetadataDict = field(default_factory=dict)

    def to_dict(self) -> DegradationAlertDict:
        """Konvertiert zu Dictionary."""
        return DegradationAlertDict(
            backend=self.backend.value,
            metric=self.metric.value,
            current_value=round(self.current_value, 4),
            threshold=self.threshold,
            trend_per_day=round(self.trend_per_day, 6),
            days_to_threshold=round(self.days_to_threshold, 1) if self.days_to_threshold else None,
            severity=self.severity,
            recommendation=self.recommendation,
            confidence=round(self.confidence, 2),
            detected_at=self.detected_at.isoformat(),
        )


@dataclass
class QualityForecastConfig:
    """Konfiguration für den Forecaster."""
    # Datensammlung
    max_history_days: int = 30
    samples_per_day: int = 24  # Stuendliche Aggregation

    # Thresholds (je niedriger desto besser bei CER/WER)
    cer_warning_threshold: float = 0.03  # 3%
    cer_critical_threshold: float = 0.05  # 5%
    wer_warning_threshold: float = 0.08  # 8%
    wer_critical_threshold: float = 0.12  # 12%
    confidence_warning_threshold: float = 0.85  # Unter 85%
    umlaut_warning_threshold: float = 0.95  # Unter 95%

    # Analyse
    min_samples_for_forecast: int = 24  # Mindestens 24 Stunden Daten
    trend_window_hours: int = 168  # 7 Tage für Trend


class QualityHistory:
    """Speichert Qualitäts-Historie für ein Backend."""

    def __init__(self, max_samples: int = 720) -> None:  # 30 Tage * 24
        """Initialisiert die History."""
        self._data: Dict[QualityMetric, Deque[QualityDataPoint]] = {
            metric: deque(maxlen=max_samples)
            for metric in QualityMetric
        }

    def add(
        self,
        metric: QualityMetric,
        value: float,
        backend: OCRBackend,
        document_count: int = 1
    ) -> None:
        """Fuegt Datenpunkt hinzu."""
        self._data[metric].append(QualityDataPoint(
            timestamp=datetime.now(timezone.utc),
            value=value,
            backend=backend,
            document_count=document_count
        ))

    def get_values(
        self,
        metric: QualityMetric,
        hours: Optional[int] = None
    ) -> List[float]:
        """Gibt Werte zurück, optional gefiltert nach Zeit."""
        data = self._data[metric]

        if hours is None:
            return [dp.value for dp in data]

        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        return [dp.value for dp in data if dp.timestamp > cutoff]

    def get_datapoints(
        self,
        metric: QualityMetric,
        hours: Optional[int] = None
    ) -> List[QualityDataPoint]:
        """Gibt vollständige Datenpunkte zurück."""
        data = self._data[metric]

        if hours is None:
            return list(data)

        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        return [dp for dp in data if dp.timestamp > cutoff]

    def __len__(self) -> int:
        return sum(len(q) for q in self._data.values())


class OCRQualityForecaster:
    """
    Prognostiziert OCR-Qualitäts-Degradation.

    Analysiert Trends in CER/WER/Confidence und warnt vor Problemen.
    """

    def __init__(self, config: Optional[QualityForecastConfig] = None) -> None:
        """Initialisiert den Forecaster."""
        self.config = config or QualityForecastConfig()

        # Historie pro Backend
        max_samples = self.config.max_history_days * self.config.samples_per_day
        self._histories: Dict[OCRBackend, QualityHistory] = {
            backend: QualityHistory(max_samples)
            for backend in OCRBackend
        }

        logger.info(
            "ocr_quality_forecaster_initialized",
            max_history_days=self.config.max_history_days
        )

    def record_quality(
        self,
        backend: OCRBackend,
        cer: Optional[float] = None,
        wer: Optional[float] = None,
        confidence: Optional[float] = None,
        umlaut_accuracy: Optional[float] = None,
        document_count: int = 1
    ) -> None:
        """
        Zeichnet Qualitäts-Metriken auf.

        Args:
            backend: OCR-Backend
            cer: Character Error Rate (0-1)
            wer: Word Error Rate (0-1)
            confidence: Durchschnittliche Confidence (0-1)
            umlaut_accuracy: Umlaut-Genauigkeit (0-1)
            document_count: Anzahl verarbeiteter Dokumente
        """
        history = self._histories[backend]

        if cer is not None:
            history.add(QualityMetric.CER, cer, backend, document_count)
        if wer is not None:
            history.add(QualityMetric.WER, wer, backend, document_count)
        if confidence is not None:
            history.add(QualityMetric.CONFIDENCE, confidence, backend, document_count)
        if umlaut_accuracy is not None:
            history.add(QualityMetric.UMLAUT_ACCURACY, umlaut_accuracy, backend, document_count)

    def _calculate_trend(self, values: List[float]) -> Tuple[float, float]:
        """
        Berechnet Trend (Steigung) und R-squared.

        Returns:
            Tuple von (slope_per_day, r_squared)
        """
        n = len(values)
        if n < 2:
            return 0.0, 0.0

        x = np.arange(n)
        y = np.array(values)

        x_mean = np.mean(x)
        y_mean = np.mean(y)

        numerator = np.sum((x - x_mean) * (y - y_mean))
        denominator = np.sum((x - x_mean) ** 2)

        if denominator == 0:
            return 0.0, 0.0

        slope_per_sample = numerator / denominator

        # R-squared
        y_pred = slope_per_sample * x + (y_mean - slope_per_sample * x_mean)
        ss_res = np.sum((y - y_pred) ** 2)
        ss_tot = np.sum((y - y_mean) ** 2)
        r_squared = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0.0

        # Konvertiere zu Steigung pro Tag (samples_per_day pro Tag)
        slope_per_day = slope_per_sample * self.config.samples_per_day

        return slope_per_day, max(0, r_squared)

    def _rolling_average(
        self,
        values: List[float],
        window: int = 24
    ) -> List[float]:
        """Berechnet rollenden Durchschnitt."""
        if len(values) < window:
            return values

        result = []
        for i in range(len(values)):
            start = max(0, i - window + 1)
            result.append(np.mean(values[start:i + 1]))

        return result

    async def detect_degradation(
        self,
        backend: OCRBackend
    ) -> List[DegradationAlert]:
        """
        Erkennt Qualitäts-Degradation für ein Backend.

        Args:
            backend: OCR-Backend zu analysieren

        Returns:
            Liste von DegradationAlerts
        """
        history = self._histories[backend]
        alerts: List[DegradationAlert] = []

        # CER Analyse
        cer_values = history.get_values(
            QualityMetric.CER,
            hours=self.config.trend_window_hours
        )
        if len(cer_values) >= self.config.min_samples_for_forecast:
            alert = self._analyze_metric(
                backend=backend,
                metric=QualityMetric.CER,
                values=cer_values,
                warning_threshold=self.config.cer_warning_threshold,
                critical_threshold=self.config.cer_critical_threshold,
                higher_is_worse=True
            )
            if alert:
                alerts.append(alert)

        # WER Analyse
        wer_values = history.get_values(
            QualityMetric.WER,
            hours=self.config.trend_window_hours
        )
        if len(wer_values) >= self.config.min_samples_for_forecast:
            alert = self._analyze_metric(
                backend=backend,
                metric=QualityMetric.WER,
                values=wer_values,
                warning_threshold=self.config.wer_warning_threshold,
                critical_threshold=self.config.wer_critical_threshold,
                higher_is_worse=True
            )
            if alert:
                alerts.append(alert)

        # Confidence Analyse
        conf_values = history.get_values(
            QualityMetric.CONFIDENCE,
            hours=self.config.trend_window_hours
        )
        if len(conf_values) >= self.config.min_samples_for_forecast:
            alert = self._analyze_metric(
                backend=backend,
                metric=QualityMetric.CONFIDENCE,
                values=conf_values,
                warning_threshold=self.config.confidence_warning_threshold,
                critical_threshold=0.7,  # Kritisch unter 70%
                higher_is_worse=False  # Niedriger ist schlechter
            )
            if alert:
                alerts.append(alert)

        # Umlaut Analyse
        umlaut_values = history.get_values(
            QualityMetric.UMLAUT_ACCURACY,
            hours=self.config.trend_window_hours
        )
        if len(umlaut_values) >= self.config.min_samples_for_forecast:
            alert = self._analyze_metric(
                backend=backend,
                metric=QualityMetric.UMLAUT_ACCURACY,
                values=umlaut_values,
                warning_threshold=self.config.umlaut_warning_threshold,
                critical_threshold=0.9,
                higher_is_worse=False
            )
            if alert:
                alerts.append(alert)

        return alerts

    def _analyze_metric(
        self,
        backend: OCRBackend,
        metric: QualityMetric,
        values: List[float],
        warning_threshold: float,
        critical_threshold: float,
        higher_is_worse: bool
    ) -> Optional[DegradationAlert]:
        """
        Analysiert eine einzelne Metrik.

        Args:
            backend: OCR-Backend
            metric: Metrik-Typ
            values: Historische Werte
            warning_threshold: Warnungs-Schwelle
            critical_threshold: Kritische Schwelle
            higher_is_worse: True wenn steigende Werte schlecht sind

        Returns:
            DegradationAlert oder None
        """
        # Rolling Average für Glaettung
        smoothed = self._rolling_average(values)
        current = smoothed[-1]

        # Trend berechnen
        trend_per_day, r_squared = self._calculate_trend(smoothed)

        # Für "niedriger ist schlechter" Metriken: negieren wir die Logik
        if not higher_is_worse:
            # z.B. Confidence: Wert faellt = schlecht
            is_degrading = trend_per_day < 0
            trend_for_calc = -trend_per_day  # Positiv machen für Berechnung
        else:
            # z.B. CER: Wert steigt = schlecht
            is_degrading = trend_per_day > 0
            trend_for_calc = trend_per_day

        # Wenn kein negativer Trend, keine Warnung
        if not is_degrading:
            return None

        # Zeit bis Threshold berechnen
        if higher_is_worse:
            distance = critical_threshold - current
        else:
            distance = current - critical_threshold

        if distance <= 0:
            # Bereits überschritten
            days_to_threshold = 0.0
        elif trend_for_calc > 0:
            days_to_threshold = distance / trend_for_calc
        else:
            days_to_threshold = None

        # Schweregrad bestimmen
        if days_to_threshold is not None and days_to_threshold < 3:
            severity = "critical"
        elif days_to_threshold is not None and days_to_threshold < 7:
            severity = "warning"
        elif days_to_threshold is None or days_to_threshold > 14:
            # Kein Alert wenn >14 Tage oder kein Trend
            return None
        else:
            severity = "info"

        # Empfehlung generieren
        if severity == "critical":
            recommendation = (
                f"KRITISCH: {metric.value.upper()} für {backend.value} degradiert schnell. "
                f"Sofortiges Retraining oder Backend-Wechsel empfohlen."
            )
        elif severity == "warning":
            recommendation = (
                f"WARNUNG: {metric.value.upper()} für {backend.value} verschlechtert sich. "
                f"Retraining planen oder Ursache analysieren."
            )
        else:
            recommendation = (
                f"INFO: Leichte Degradation bei {metric.value.upper()} für {backend.value}. "
                f"Beobachten."
            )

        return DegradationAlert(
            backend=backend,
            metric=metric,
            current_value=current,
            threshold=critical_threshold,
            trend_per_day=trend_per_day,
            days_to_threshold=days_to_threshold,
            severity=severity,
            recommendation=recommendation,
            confidence=r_squared
        )

    async def get_all_degradation_alerts(self) -> List[DegradationAlert]:
        """
        Prüft alle Backends auf Degradation.

        Returns:
            Liste aller Alerts
        """
        all_alerts: List[DegradationAlert] = []

        for backend in OCRBackend:
            alerts = await self.detect_degradation(backend)
            all_alerts.extend(alerts)

        # Sortiere nach Schweregrad
        severity_order = {"critical": 0, "warning": 1, "info": 2}
        all_alerts.sort(key=lambda a: severity_order.get(a.severity, 3))

        return all_alerts

    def get_quality_summary(
        self,
        backend: OCRBackend
    ) -> QualitySummaryDict:
        """
        Gibt Qualitäts-Zusammenfassung für ein Backend zurück.

        Args:
            backend: OCR-Backend

        Returns:
            Dict mit Qualitäts-Metriken
        """
        history = self._histories[backend]

        metrics: Dict[str, MetricStatsDict] = {}

        for metric in QualityMetric:
            values = history.get_values(metric, hours=24)
            if values:
                metrics[metric.value] = MetricStatsDict(
                    current=round(values[-1], 4),
                    avg_24h=round(float(np.mean(values)), 4),
                    min_24h=round(min(values), 4),
                    max_24h=round(max(values), 4),
                    samples=len(values),
                )

        return QualitySummaryDict(
            backend=backend.value,
            metrics=metrics,
        )


# Singleton-Instanz
_quality_forecaster: Optional[OCRQualityForecaster] = None


def get_quality_forecaster() -> OCRQualityForecaster:
    """Gibt Singleton-Instanz des Quality Forecasters zurück."""
    global _quality_forecaster
    if _quality_forecaster is None:
        _quality_forecaster = OCRQualityForecaster()
    return _quality_forecaster
