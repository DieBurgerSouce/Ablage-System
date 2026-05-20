# -*- coding: utf-8 -*-
"""
Tests fuer System Health Predictor.

Testet:
- Metrik-Aufzeichnung
- EMA-Berechnung
- Lineare Regression
- Vorhersagen (GPU, Queue, Disk)
"""

import pytest
import numpy as np
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

from app.services.predictive.system_health_predictor import (
    SystemHealthPredictor,
    PredictorConfig,
    PredictionResult,
    PredictionSeverity,
    MetricType,
    MetricHistory,
    MetricDataPoint,
    get_health_predictor,
)


class TestMetricHistory:
    """Tests fuer Metrik-History."""

    def test_add_datapoint(self) -> None:
        """Datenpunkte sollten hinzugefuegt werden."""
        history = MetricHistory(max_size=10)

        history.add(5.0)
        history.add(10.0)

        assert len(history) == 2

    def test_max_size_enforced(self) -> None:
        """Max-Size sollte eingehalten werden."""
        history = MetricHistory(max_size=5)

        for i in range(10):
            history.add(float(i))

        assert len(history) == 5

    def test_get_values(self) -> None:
        """Werte sollten abgerufen werden koennen."""
        history = MetricHistory()

        history.add(1.0)
        history.add(2.0)
        history.add(3.0)

        values = history.get_values()
        assert values == [1.0, 2.0, 3.0]

    def test_get_values_last_n(self) -> None:
        """Letzte N Werte sollten abgerufen werden."""
        history = MetricHistory()

        for i in range(10):
            history.add(float(i))

        values = history.get_values(last_n=3)
        assert values == [7.0, 8.0, 9.0]

    def test_clear(self) -> None:
        """Clear sollte History loeschen."""
        history = MetricHistory()

        history.add(1.0)
        history.add(2.0)
        history.clear()

        assert len(history) == 0


class TestPredictorInitialization:
    """Tests fuer Predictor-Initialisierung."""

    def test_default_config(self) -> None:
        """Standard-Konfiguration sollte geladen werden."""
        predictor = SystemHealthPredictor()

        assert predictor.config.max_history_points == 60
        assert predictor.config.gpu_vram_total_gb == 16.0

    def test_custom_config(self) -> None:
        """Benutzerdefinierte Konfiguration sollte funktionieren."""
        config = PredictorConfig(
            max_history_points=30,
            gpu_vram_total_gb=24.0
        )
        predictor = SystemHealthPredictor(config=config)

        assert predictor.config.max_history_points == 30
        assert predictor.config.gpu_vram_total_gb == 24.0


class TestMetricRecording:
    """Tests fuer Metrik-Aufzeichnung."""

    def test_record_metric(self) -> None:
        """Metriken sollten aufgezeichnet werden."""
        predictor = SystemHealthPredictor()

        predictor.record_metric(MetricType.GPU_VRAM, 10.5)
        predictor.record_metric(MetricType.GPU_VRAM, 11.0)

        history = predictor.get_metric_history(MetricType.GPU_VRAM)
        assert len(history) == 2

    def test_record_queue_metric(self) -> None:
        """Queue-Metriken sollten aufgezeichnet werden."""
        predictor = SystemHealthPredictor()

        predictor.record_queue_metric("ocr", 50)
        predictor.record_queue_metric("ocr", 60)

        assert "ocr" in predictor._queue_histories
        assert len(predictor._queue_histories["ocr"]) == 2


class TestEMACalculation:
    """Tests fuer EMA-Berechnung."""

    def test_ema_single_value(self) -> None:
        """EMA mit einem Wert sollte den Wert zurueckgeben."""
        predictor = SystemHealthPredictor()

        ema = predictor._calculate_ema([5.0])

        assert ema == [5.0]

    def test_ema_smoothing(self) -> None:
        """EMA sollte Werte glaetten."""
        predictor = SystemHealthPredictor()

        # Starker Sprung
        values = [10.0, 10.0, 10.0, 100.0, 10.0]
        ema = predictor._calculate_ema(values)

        # EMA sollte weniger sprunghaft sein
        max_diff_original = max(abs(values[i] - values[i - 1]) for i in range(1, len(values)))
        max_diff_ema = max(abs(ema[i] - ema[i - 1]) for i in range(1, len(ema)))

        assert max_diff_ema < max_diff_original


class TestLinearRegression:
    """Tests fuer Lineare Regression."""

    def test_linear_regression_positive_slope(self) -> None:
        """Positiver Trend sollte erkannt werden."""
        predictor = SystemHealthPredictor()

        values = [1.0, 2.0, 3.0, 4.0, 5.0]
        slope, intercept, r_squared = predictor._linear_regression(values)

        assert slope > 0
        assert r_squared > 0.99  # Perfekte Linie

    def test_linear_regression_negative_slope(self) -> None:
        """Negativer Trend sollte erkannt werden."""
        predictor = SystemHealthPredictor()

        values = [5.0, 4.0, 3.0, 2.0, 1.0]
        slope, intercept, r_squared = predictor._linear_regression(values)

        assert slope < 0
        assert r_squared > 0.99

    def test_linear_regression_flat(self) -> None:
        """Flacher Trend sollte Null-Steigung haben."""
        predictor = SystemHealthPredictor()

        values = [5.0, 5.0, 5.0, 5.0, 5.0]
        slope, intercept, r_squared = predictor._linear_regression(values)

        assert abs(slope) < 0.001

    def test_linear_regression_single_value(self) -> None:
        """Einzelner Wert sollte Null-Steigung haben."""
        predictor = SystemHealthPredictor()

        slope, intercept, r_squared = predictor._linear_regression([5.0])

        assert slope == 0.0


class TestTimeToThresholdPrediction:
    """Tests fuer Zeit-bis-Threshold-Berechnung."""

    def test_predict_time_positive_slope(self) -> None:
        """Zeit bis Threshold bei positivem Trend."""
        predictor = SystemHealthPredictor()

        time = predictor._predict_time_to_threshold(
            current=80.0,
            slope=1.0,
            threshold=90.0
        )

        # 10 Punkte bei 1 pro Punkt = 10 Punkte
        # Bei 60s Intervall = 10 Minuten
        assert time is not None
        assert time > 0

    def test_predict_time_negative_slope(self) -> None:
        """Kein Threshold bei negativem Trend."""
        predictor = SystemHealthPredictor()

        time = predictor._predict_time_to_threshold(
            current=80.0,
            slope=-1.0,  # Faellt
            threshold=90.0
        )

        assert time is None

    def test_predict_time_already_exceeded(self) -> None:
        """Bereits ueberschritten sollte 0 zurueckgeben."""
        predictor = SystemHealthPredictor()

        time = predictor._predict_time_to_threshold(
            current=95.0,  # Bereits ueber Threshold
            slope=1.0,
            threshold=90.0
        )

        assert time == 0.0


class TestGPUVRAMPrediction:
    """Tests fuer GPU VRAM Vorhersage."""

    @pytest.mark.asyncio
    async def test_predict_gpu_no_data(self) -> None:
        """Ohne Daten sollte None zurueckgegeben werden."""
        predictor = SystemHealthPredictor()

        result = await predictor.predict_gpu_vram_overflow()

        assert result is None

    @pytest.mark.asyncio
    async def test_predict_gpu_stable(self) -> None:
        """Stabiler VRAM sollte INFO-Severity haben."""
        predictor = SystemHealthPredictor()

        # Simuliere stabile Nutzung
        for _ in range(10):
            predictor.record_metric(MetricType.GPU_VRAM, 8.0)

        result = await predictor.predict_gpu_vram_overflow()

        assert result is not None
        assert result.severity == PredictionSeverity.INFO

    @pytest.mark.asyncio
    async def test_predict_gpu_increasing(self) -> None:
        """Steigender VRAM sollte WARNING/CRITICAL haben."""
        config = PredictorConfig(min_points_for_prediction=5)
        predictor = SystemHealthPredictor(config=config)

        # Simuliere steigenden Verbrauch (nahe am kritischen Bereich)
        values = np.linspace(12.0, 14.5, 10)  # Steigt von 12 auf 14.5 GB
        for v in values:
            predictor.record_metric(MetricType.GPU_VRAM, v)

        result = await predictor.predict_gpu_vram_overflow()

        assert result is not None
        # Bei schnellem Anstieg nahe am Threshold sollte WARNING oder hoeher sein
        assert result.severity in (PredictionSeverity.WARNING, PredictionSeverity.CRITICAL)


class TestQueuePrediction:
    """Tests fuer Queue-Vorhersage."""

    @pytest.mark.asyncio
    async def test_predict_queue_no_data(self) -> None:
        """Ohne Daten sollte None zurueckgegeben werden."""
        predictor = SystemHealthPredictor()

        result = await predictor.predict_queue_overflow("ocr")

        assert result is None

    @pytest.mark.asyncio
    async def test_predict_queue_stable(self) -> None:
        """Stabile Queue sollte INFO-Severity haben."""
        config = PredictorConfig(min_points_for_prediction=5)
        predictor = SystemHealthPredictor(config=config)

        # Simuliere stabile Queue
        for _ in range(10):
            predictor.record_queue_metric("ocr", 20)

        result = await predictor.predict_queue_overflow("ocr")

        assert result is not None
        assert result.severity == PredictionSeverity.INFO


class TestDiskPrediction:
    """Tests fuer Disk-Vorhersage."""

    @pytest.mark.asyncio
    async def test_predict_disk_no_data(self) -> None:
        """Ohne Daten sollte None zurueckgegeben werden."""
        predictor = SystemHealthPredictor()

        result = await predictor.predict_disk_exhaustion()

        assert result is None


class TestAllPredictions:
    """Tests fuer alle Vorhersagen."""

    @pytest.mark.asyncio
    async def test_get_all_predictions(self) -> None:
        """get_all_predictions sollte Liste zurueckgeben."""
        config = PredictorConfig(min_points_for_prediction=5)
        predictor = SystemHealthPredictor(config=config)

        # Fuege einige Daten hinzu
        for i in range(10):
            predictor.record_metric(MetricType.GPU_VRAM, 8.0 + i * 0.1)
            predictor.record_queue_metric("ocr", 10 + i)

        predictions = await predictor.get_all_predictions()

        assert isinstance(predictions, list)


class TestPredictionResult:
    """Tests fuer PredictionResult."""

    def test_to_dict(self) -> None:
        """to_dict sollte korrekt serialisieren."""
        result = PredictionResult(
            metric=MetricType.GPU_VRAM,
            current_value=12.5,
            predicted_value=14.4,
            threshold=14.4,
            eta_minutes=10.5,
            trend=0.2,
            severity=PredictionSeverity.WARNING,
            recommendation="Reduziere Batch-Size",
            confidence=0.95
        )

        d = result.to_dict()

        assert d["metric"] == "gpu_vram"
        assert d["current_value"] == 12.5
        assert d["severity"] == "warning"
        assert d["eta_minutes"] == 10.5


class TestSingleton:
    """Tests fuer Singleton-Pattern."""

    def test_get_health_predictor_singleton(self) -> None:
        """get_health_predictor sollte Singleton zurueckgeben."""
        pred1 = get_health_predictor()
        pred2 = get_health_predictor()

        assert pred1 is pred2
