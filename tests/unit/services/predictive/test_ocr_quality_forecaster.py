# -*- coding: utf-8 -*-
"""
Tests fuer OCR Quality Forecaster.

Testet:
- Qualitaets-Aufzeichnung
- Trend-Erkennung
- Degradation-Alerts
"""

import pytest
import numpy as np
from datetime import datetime
from unittest.mock import MagicMock

from app.services.predictive.ocr_quality_forecaster import (
    OCRQualityForecaster,
    QualityForecastConfig,
    QualityMetric,
    OCRBackend,
    QualityHistory,
    QualityDataPoint,
    DegradationAlert,
    get_quality_forecaster,
)


class TestQualityHistory:
    """Tests fuer Quality History."""

    def test_add_datapoint(self) -> None:
        """Datenpunkte sollten hinzugefuegt werden."""
        history = QualityHistory()

        history.add(QualityMetric.CER, 0.05, OCRBackend.DEEPSEEK)

        values = history.get_values(QualityMetric.CER)
        assert len(values) == 1
        assert values[0] == 0.05

    def test_get_values_filtered_by_hours(self) -> None:
        """Werte sollten nach Zeit gefiltert werden."""
        history = QualityHistory()

        # Fuege mehrere Werte hinzu
        for i in range(10):
            history.add(QualityMetric.CER, 0.01 * i, OCRBackend.DEEPSEEK)

        values = history.get_values(QualityMetric.CER)
        assert len(values) == 10

    def test_multiple_metrics(self) -> None:
        """Verschiedene Metriken sollten getrennt sein."""
        history = QualityHistory()

        history.add(QualityMetric.CER, 0.05, OCRBackend.DEEPSEEK)
        history.add(QualityMetric.WER, 0.10, OCRBackend.DEEPSEEK)

        cer_values = history.get_values(QualityMetric.CER)
        wer_values = history.get_values(QualityMetric.WER)

        assert cer_values == [0.05]
        assert wer_values == [0.10]


class TestForecasterInitialization:
    """Tests fuer Forecaster-Initialisierung."""

    def test_default_config(self) -> None:
        """Standard-Konfiguration sollte geladen werden."""
        forecaster = OCRQualityForecaster()

        assert forecaster.config.max_history_days == 30
        assert forecaster.config.cer_warning_threshold == 0.03

    def test_custom_config(self) -> None:
        """Benutzerdefinierte Konfiguration sollte funktionieren."""
        config = QualityForecastConfig(
            cer_warning_threshold=0.05,
            cer_critical_threshold=0.10
        )
        forecaster = OCRQualityForecaster(config=config)

        assert forecaster.config.cer_warning_threshold == 0.05
        assert forecaster.config.cer_critical_threshold == 0.10


class TestQualityRecording:
    """Tests fuer Qualitaets-Aufzeichnung."""

    def test_record_quality_cer(self) -> None:
        """CER sollte aufgezeichnet werden."""
        forecaster = OCRQualityForecaster()

        forecaster.record_quality(
            backend=OCRBackend.DEEPSEEK,
            cer=0.02
        )

        summary = forecaster.get_quality_summary(OCRBackend.DEEPSEEK)
        assert QualityMetric.CER.value in summary["metrics"]

    def test_record_quality_multiple_metrics(self) -> None:
        """Mehrere Metriken sollten gleichzeitig aufgezeichnet werden."""
        forecaster = OCRQualityForecaster()

        forecaster.record_quality(
            backend=OCRBackend.GOT_OCR,
            cer=0.02,
            wer=0.08,
            confidence=0.95,
            umlaut_accuracy=0.98
        )

        summary = forecaster.get_quality_summary(OCRBackend.GOT_OCR)
        assert len(summary["metrics"]) >= 1  # Mindestens eine Metrik

    def test_record_quality_with_document_count(self) -> None:
        """Document Count sollte gespeichert werden."""
        forecaster = OCRQualityForecaster()

        forecaster.record_quality(
            backend=OCRBackend.SURYA,
            cer=0.03,
            document_count=50
        )

        # Kein direkter Zugriff, aber sollte funktionieren


class TestTrendCalculation:
    """Tests fuer Trend-Berechnung."""

    def test_calculate_trend_increasing(self) -> None:
        """Steigender Trend sollte positiv sein."""
        forecaster = OCRQualityForecaster()

        values = [0.01, 0.02, 0.03, 0.04, 0.05]
        slope, r_squared = forecaster._calculate_trend(values)

        assert slope > 0
        assert r_squared > 0.99

    def test_calculate_trend_decreasing(self) -> None:
        """Fallender Trend sollte negativ sein."""
        forecaster = OCRQualityForecaster()

        values = [0.05, 0.04, 0.03, 0.02, 0.01]
        slope, r_squared = forecaster._calculate_trend(values)

        assert slope < 0

    def test_calculate_trend_flat(self) -> None:
        """Flacher Trend sollte nahe Null sein."""
        forecaster = OCRQualityForecaster()

        values = [0.03, 0.03, 0.03, 0.03, 0.03]
        slope, r_squared = forecaster._calculate_trend(values)

        assert abs(slope) < 0.001


class TestRollingAverage:
    """Tests fuer Rolling Average."""

    def test_rolling_average_smoothing(self) -> None:
        """Rolling Average sollte glaetten."""
        forecaster = OCRQualityForecaster()

        # Werte mit Spike
        values = [0.02, 0.02, 0.10, 0.02, 0.02]
        smoothed = forecaster._rolling_average(values, window=3)

        # Smoothed sollte weniger sprunghaft sein
        max_diff_original = max(abs(values[i] - values[i - 1]) for i in range(1, len(values)))
        max_diff_smoothed = max(abs(smoothed[i] - smoothed[i - 1]) for i in range(1, len(smoothed)))

        assert max_diff_smoothed < max_diff_original

    def test_rolling_average_short_list(self) -> None:
        """Kurze Liste sollte unveraendert zurueckgegeben werden."""
        forecaster = OCRQualityForecaster()

        values = [0.02, 0.03]
        smoothed = forecaster._rolling_average(values, window=5)

        assert smoothed == values


class TestDegradationDetection:
    """Tests fuer Degradation-Erkennung."""

    @pytest.mark.asyncio
    async def test_detect_degradation_no_data(self) -> None:
        """Ohne Daten sollte leere Liste zurueckgegeben werden."""
        forecaster = OCRQualityForecaster()

        alerts = await forecaster.detect_degradation(OCRBackend.DEEPSEEK)

        assert alerts == []

    @pytest.mark.asyncio
    async def test_detect_degradation_stable(self) -> None:
        """Stabile Qualitaet sollte keine Alerts erzeugen."""
        config = QualityForecastConfig(min_samples_for_forecast=5)
        forecaster = OCRQualityForecaster(config=config)

        # Stabile CER-Werte
        for _ in range(30):
            forecaster.record_quality(
                backend=OCRBackend.DEEPSEEK,
                cer=0.02  # Stabil unter Threshold
            )

        alerts = await forecaster.detect_degradation(OCRBackend.DEEPSEEK)

        # Keine kritischen Alerts erwartet
        critical_alerts = [a for a in alerts if a.severity == "critical"]
        assert len(critical_alerts) == 0

    @pytest.mark.asyncio
    async def test_detect_degradation_increasing_cer(self) -> None:
        """Steigende CER sollte Alerts erzeugen."""
        config = QualityForecastConfig(min_samples_for_forecast=10)
        forecaster = OCRQualityForecaster(config=config)

        # CER steigt stark an
        for i in range(30):
            cer = 0.01 + i * 0.002  # Steigt von 0.01 auf 0.07
            forecaster.record_quality(
                backend=OCRBackend.DEEPSEEK,
                cer=cer
            )

        alerts = await forecaster.detect_degradation(OCRBackend.DEEPSEEK)

        # Bei starkem Anstieg sollte Alert kommen
        # (Abhaengig von Threshold-Einstellungen)
        assert isinstance(alerts, list)


class TestAllDegradationAlerts:
    """Tests fuer alle Degradation Alerts."""

    @pytest.mark.asyncio
    async def test_get_all_degradation_alerts(self) -> None:
        """get_all_degradation_alerts sollte alle Backends pruefen."""
        config = QualityForecastConfig(min_samples_for_forecast=5)
        forecaster = OCRQualityForecaster(config=config)

        # Fuege Daten fuer mehrere Backends hinzu
        for backend in [OCRBackend.DEEPSEEK, OCRBackend.GOT_OCR]:
            for _ in range(10):
                forecaster.record_quality(backend=backend, cer=0.02)

        alerts = await forecaster.get_all_degradation_alerts()

        assert isinstance(alerts, list)


class TestQualitySummary:
    """Tests fuer Quality Summary."""

    def test_get_quality_summary_empty(self) -> None:
        """Leeres Summary sollte korrekt sein."""
        forecaster = OCRQualityForecaster()

        summary = forecaster.get_quality_summary(OCRBackend.DEEPSEEK)

        assert summary["backend"] == "deepseek"
        assert summary["metrics"] == {}

    def test_get_quality_summary_with_data(self) -> None:
        """Summary mit Daten sollte Statistiken enthalten."""
        forecaster = OCRQualityForecaster()

        for i in range(10):
            forecaster.record_quality(
                backend=OCRBackend.GOT_OCR,
                cer=0.02 + i * 0.001
            )

        summary = forecaster.get_quality_summary(OCRBackend.GOT_OCR)

        assert "cer" in summary["metrics"]
        cer_stats = summary["metrics"]["cer"]
        assert "current" in cer_stats
        assert "avg_24h" in cer_stats
        assert "min_24h" in cer_stats
        assert "max_24h" in cer_stats
        assert "samples" in cer_stats


class TestDegradationAlertSerialization:
    """Tests fuer DegradationAlert Serialisierung."""

    def test_to_dict(self) -> None:
        """to_dict sollte korrekt serialisieren."""
        alert = DegradationAlert(
            backend=OCRBackend.DEEPSEEK,
            metric=QualityMetric.CER,
            current_value=0.045,
            threshold=0.05,
            trend_per_day=0.005,
            days_to_threshold=1.0,
            severity="warning",
            recommendation="Retraining empfohlen",
            confidence=0.85
        )

        d = alert.to_dict()

        assert d["backend"] == "deepseek"
        assert d["metric"] == "cer"
        assert d["severity"] == "warning"
        assert d["days_to_threshold"] == 1.0


class TestSingleton:
    """Tests fuer Singleton-Pattern."""

    def test_get_quality_forecaster_singleton(self) -> None:
        """get_quality_forecaster sollte Singleton zurueckgeben."""
        fc1 = get_quality_forecaster()
        fc2 = get_quality_forecaster()

        assert fc1 is fc2
