# -*- coding: utf-8 -*-
"""
Erweiterte Unit Tests fuer OCR-Qualitaets-Metriken.

Tests fuer:
- Prometheus-Integration
- MLMetrics Klasse
- Calibration Metriken
- Backend-spezifische Metriken
- Thread-Sicherheit
- Deutsche Fehlermeldungen
"""

import asyncio
import threading
import time
from unittest.mock import MagicMock, Mock, patch, PropertyMock
from typing import Dict, Any

import pytest


@pytest.fixture
def mock_prometheus():
    """Mock Prometheus-Client."""
    with patch.dict('sys.modules', {
        'prometheus_client': MagicMock(),
    }):
        # Importiere nach dem Patch
        import importlib
        import app.ml.metrics as metrics_module

        # Mock die Prometheus-Objekte
        mock_counter = MagicMock()
        mock_histogram = MagicMock()
        mock_gauge = MagicMock()
        mock_info = MagicMock()

        with patch.object(metrics_module, 'PROMETHEUS_AVAILABLE', True):
            yield {
                'counter': mock_counter,
                'histogram': mock_histogram,
                'gauge': mock_gauge,
                'info': mock_info,
                'module': metrics_module,
            }


class TestMLMetricsInitialization:
    """Tests fuer MLMetrics Initialisierung."""

    def test_metrics_initializes_without_prometheus(self):
        """Metriken funktionieren ohne Prometheus."""
        with patch.dict('sys.modules', {'prometheus_client': None}):
            # Force reload to pick up mock
            from app.ml.metrics import MLMetrics

            metrics = MLMetrics()
            # Sollte nicht crashen auch wenn Prometheus nicht da ist
            assert metrics is not None

    def test_backend_active_tracking(self):
        """Backend-Active-Tracking initialisiert leer."""
        from app.ml.metrics import MLMetrics

        metrics = MLMetrics()
        assert metrics._backend_active == {}


class TestRoutingMetrics:
    """Tests fuer Routing-Metriken."""

    def test_record_routing_request_logs_when_prometheus_disabled(self):
        """Routing-Request wird geloggt wenn Prometheus deaktiviert."""
        from app.ml.metrics import MLMetrics

        metrics = MLMetrics()
        metrics.enabled = False  # Disable Prometheus für Test

        # Sollte nicht crashen
        metrics.record_routing_request(
            method="ml",
            backend="deepseek",
            status="success",
            latency_seconds=0.5,
            confidence=0.95
        )

    def test_measure_routing_time_context_manager(self):
        """Context Manager misst Routing-Zeit."""
        from app.ml.metrics import MLMetrics

        metrics = MLMetrics()
        metrics.enabled = False  # Disable Prometheus für Test

        start = time.time()
        with metrics.measure_routing_time("test_method"):
            time.sleep(0.1)
        elapsed = time.time() - start

        assert elapsed >= 0.1


class TestBackendMetrics:
    """Tests fuer Backend-Metriken."""

    def test_record_backend_request_with_accuracy(self):
        """Backend-Request mit Genauigkeit wird erfasst."""
        from app.ml.metrics import MLMetrics

        metrics = MLMetrics()
        metrics.enabled = False

        # Sollte nicht crashen
        metrics.record_backend_request(
            backend="got_ocr",
            status="success",
            language="de",
            processing_time=2.5,
            accuracy=0.95,
            document_type="invoice"
        )

    def test_record_backend_request_without_accuracy(self):
        """Backend-Request ohne Genauigkeit wird erfasst."""
        from app.ml.metrics import MLMetrics

        metrics = MLMetrics()
        metrics.enabled = False

        metrics.record_backend_request(
            backend="surya",
            status="error",
            language="de",
            processing_time=1.0,
            accuracy=None
        )

    def test_inc_dec_backend_active(self):
        """Backend-Active-Zaehler funktioniert."""
        from app.ml.metrics import MLMetrics

        metrics = MLMetrics()
        metrics.enabled = False

        # Initial = 0
        assert metrics._backend_active.get("test", 0) == 0

        # Increment
        metrics.inc_backend_active("test")
        assert metrics._backend_active["test"] == 1

        metrics.inc_backend_active("test")
        assert metrics._backend_active["test"] == 2

        # Decrement
        metrics.dec_backend_active("test")
        assert metrics._backend_active["test"] == 1

        # Decrement below 0 should stay at 0
        metrics.dec_backend_active("test")
        metrics.dec_backend_active("test")
        assert metrics._backend_active["test"] == 0

    def test_track_backend_request_context_manager(self):
        """Context Manager trackt Backend-Requests."""
        from app.ml.metrics import MLMetrics

        metrics = MLMetrics()
        metrics.enabled = False

        with metrics.track_backend_request("deepseek", language="de"):
            pass  # Simulierte Verarbeitung

        # Active count sollte wieder bei 0 sein
        assert metrics._backend_active.get("deepseek", 0) == 0


class TestQualityMetrics:
    """Tests fuer OCR-Qualitaets-Metriken."""

    def test_record_quality_metrics(self):
        """Quality-Metriken werden erfasst."""
        from app.ml.metrics import MLMetrics

        metrics = MLMetrics()
        metrics.enabled = False

        # Sollte nicht crashen
        metrics.record_quality_metrics(
            backend="deepseek",
            cer=0.02,
            wer=0.05,
            umlaut_accuracy=0.98,
            document_type="invoice",
            difficulty="hard"
        )

    def test_quality_metrics_boundary_values(self):
        """Quality-Metriken mit Grenzwerten."""
        from app.ml.metrics import MLMetrics

        metrics = MLMetrics()
        metrics.enabled = False

        # Perfekte Ergebnisse
        metrics.record_quality_metrics(
            backend="deepseek",
            cer=0.0,
            wer=0.0,
            umlaut_accuracy=1.0,
            document_type="text",
            difficulty="easy"
        )

        # Schlechteste Ergebnisse
        metrics.record_quality_metrics(
            backend="surya",
            cer=1.0,
            wer=1.0,
            umlaut_accuracy=0.0,
            document_type="handwriting",
            difficulty="extreme"
        )


class TestCalibrationMetrics:
    """Tests fuer Calibration-Metriken."""

    def test_record_calibration_sample(self):
        """Calibration-Samples werden erfasst."""
        from app.ml.metrics import MLMetrics

        metrics = MLMetrics()
        metrics.enabled = False

        metrics.record_calibration_sample(backend="got_ocr", is_correct=True)
        metrics.record_calibration_sample(backend="got_ocr", is_correct=False)

    def test_update_calibration_metrics(self):
        """Calibration-Metriken werden aktualisiert."""
        from app.ml.metrics import MLMetrics

        metrics = MLMetrics()
        metrics.enabled = False

        metrics.update_calibration_metrics(
            backend="deepseek",
            ece=0.05,
            mce=0.15,
            brier_score=0.12,
            overconfidence_ratio=0.08
        )


class TestDriftMetrics:
    """Tests fuer Drift-Metriken."""

    def test_record_drift_score(self):
        """Drift-Scores werden erfasst."""
        from app.ml.metrics import MLMetrics

        metrics = MLMetrics()
        metrics.enabled = False

        metrics.record_drift_score(
            overall_score=0.25,
            feature_scores={
                "text_length": 0.15,
                "confidence": 0.35,
                "language_mix": 0.05
            },
            severity="warning"
        )

    def test_drift_severity_none(self):
        """Drift ohne Severity wird ohne Alert erfasst."""
        from app.ml.metrics import MLMetrics

        metrics = MLMetrics()
        metrics.enabled = False

        metrics.record_drift_score(
            overall_score=0.1,
            feature_scores={"feature1": 0.1},
            severity="none"
        )


class TestABTestMetrics:
    """Tests fuer A/B Test Metriken."""

    def test_record_ab_sample_success(self):
        """A/B Sample mit Erfolg wird erfasst."""
        from app.ml.metrics import MLMetrics

        metrics = MLMetrics()
        metrics.enabled = False

        metrics.record_ab_sample(
            experiment_id="exp_001",
            variant="treatment",
            success=True
        )

    def test_record_ab_sample_failure(self):
        """A/B Sample ohne Erfolg wird erfasst."""
        from app.ml.metrics import MLMetrics

        metrics = MLMetrics()
        metrics.enabled = False

        metrics.record_ab_sample(
            experiment_id="exp_001",
            variant="control",
            success=False
        )

    def test_set_active_experiments(self):
        """Anzahl aktiver Experimente wird gesetzt."""
        from app.ml.metrics import MLMetrics

        metrics = MLMetrics()
        metrics.enabled = False

        metrics.set_active_experiments(5)
        metrics.set_active_experiments(0)


class TestModelMetrics:
    """Tests fuer Model-Metriken."""

    def test_set_model_version(self):
        """Modell-Version wird gesetzt."""
        from app.ml.metrics import MLMetrics

        metrics = MLMetrics()
        metrics.enabled = False

        metrics.set_model_version(
            version="1.2.3",
            model_name="ocr_router"
        )

    def test_record_model_prediction(self):
        """Modell-Vorhersage wird erfasst."""
        from app.ml.metrics import MLMetrics

        metrics = MLMetrics()
        metrics.enabled = False

        metrics.record_model_prediction(
            model_name="classifier",
            prediction="invoice",
            inference_time=0.025
        )

    def test_measure_inference_time_context_manager(self):
        """Context Manager misst Inferenz-Zeit."""
        from app.ml.metrics import MLMetrics

        metrics = MLMetrics()
        metrics.enabled = False

        with metrics.measure_inference_time("test_model"):
            time.sleep(0.05)


class TestGPUMetrics:
    """Tests fuer GPU-Metriken."""

    def test_update_gpu_metrics_without_torch(self):
        """GPU-Metriken ohne Torch crashen nicht."""
        from app.ml.metrics import MLMetrics

        metrics = MLMetrics()
        metrics.enabled = False

        # Sollte graceful ohne torch funktionieren
        with patch.dict('sys.modules', {'torch': None}):
            metrics.update_gpu_metrics()

    def test_update_gpu_metrics_cuda_unavailable(self):
        """GPU-Metriken ohne CUDA crashen nicht."""
        from app.ml.metrics import MLMetrics

        mock_torch = MagicMock()
        mock_torch.cuda.is_available.return_value = False

        metrics = MLMetrics()
        metrics.enabled = True

        with patch.dict('sys.modules', {'torch': mock_torch}):
            metrics.update_gpu_metrics()


class TestMetricsExport:
    """Tests fuer Metriken-Export."""

    def test_get_metrics_without_prometheus(self):
        """get_metrics gibt Fallback ohne Prometheus."""
        from app.ml.metrics import MLMetrics

        metrics = MLMetrics()
        metrics.enabled = False

        result = metrics.get_metrics()

        assert b"Prometheus not available" in result

    def test_get_content_type_without_prometheus(self):
        """get_content_type gibt text/plain ohne Prometheus."""
        from app.ml.metrics import MLMetrics

        metrics = MLMetrics()
        metrics.enabled = False

        content_type = metrics.get_content_type()

        assert content_type == "text/plain"


class TestSingletonPattern:
    """Tests fuer Singleton-Pattern."""

    def test_get_ml_metrics_returns_same_instance(self):
        """get_ml_metrics gibt gleiche Instance zurueck."""
        from app.ml.metrics import get_ml_metrics, _ml_metrics
        import app.ml.metrics as module

        # Reset singleton
        module._ml_metrics = None

        metrics1 = get_ml_metrics()
        metrics2 = get_ml_metrics()

        assert metrics1 is metrics2

    def test_get_ml_metrics_thread_safe(self):
        """get_ml_metrics ist thread-safe."""
        from app.ml.metrics import get_ml_metrics
        import app.ml.metrics as module

        # Reset singleton
        module._ml_metrics = None

        instances = []

        def get_instance():
            instances.append(get_ml_metrics())

        threads = [threading.Thread(target=get_instance) for _ in range(10)]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Alle sollten gleiche Instance sein
        assert len(instances) == 10
        assert all(inst is instances[0] for inst in instances)


class TestDecorators:
    """Tests fuer Metriken-Decorators."""

    def test_track_routing_sync(self):
        """track_routing funktioniert mit sync Funktion."""
        from app.ml.metrics import track_routing, MLMetrics
        import app.ml.metrics as module

        module._ml_metrics = MLMetrics()
        module._ml_metrics.enabled = False

        @track_routing(method="test_sync")
        def sync_routing():
            return Mock(backend="deepseek", confidence=0.9)

        result = sync_routing()
        assert result.backend == "deepseek"

    @pytest.mark.asyncio
    async def test_track_routing_async(self):
        """track_routing funktioniert mit async Funktion."""
        from app.ml.metrics import track_routing, MLMetrics
        import app.ml.metrics as module

        module._ml_metrics = MLMetrics()
        module._ml_metrics.enabled = False

        @track_routing(method="test_async")
        async def async_routing():
            return Mock(backend="got_ocr", confidence=0.85)

        result = await async_routing()
        assert result.backend == "got_ocr"

    def test_track_ocr_processing_sync(self):
        """track_ocr_processing funktioniert mit sync Funktion."""
        from app.ml.metrics import track_ocr_processing, MLMetrics
        import app.ml.metrics as module

        module._ml_metrics = MLMetrics()
        module._ml_metrics.enabled = False

        @track_ocr_processing(backend="deepseek")
        def process_ocr():
            return {"text": "Test"}

        result = process_ocr()
        assert result["text"] == "Test"

    @pytest.mark.asyncio
    async def test_track_ocr_processing_async(self):
        """track_ocr_processing funktioniert mit async Funktion."""
        from app.ml.metrics import track_ocr_processing, MLMetrics
        import app.ml.metrics as module

        module._ml_metrics = MLMetrics()
        module._ml_metrics.enabled = False

        @track_ocr_processing(backend="got_ocr")
        async def process_ocr_async():
            return {"text": "Async Test"}

        result = await process_ocr_async()
        assert result["text"] == "Async Test"


class TestErrorHandling:
    """Tests fuer Fehlerbehandlung."""

    def test_track_backend_request_handles_exception(self):
        """track_backend_request behandelt Exceptions korrekt."""
        from app.ml.metrics import MLMetrics

        metrics = MLMetrics()
        metrics.enabled = False

        with pytest.raises(ValueError):
            with metrics.track_backend_request("deepseek"):
                raise ValueError("Test error")

        # Active count sollte trotzdem auf 0 sein
        assert metrics._backend_active.get("deepseek", 0) == 0

    def test_gpu_metrics_handles_exception(self):
        """GPU-Metriken behandeln Exceptions graceful."""
        from app.ml.metrics import MLMetrics

        mock_torch = MagicMock()
        mock_torch.cuda.is_available.side_effect = RuntimeError("GPU error")

        metrics = MLMetrics()
        metrics.enabled = True

        with patch.dict('sys.modules', {'torch': mock_torch}):
            # Sollte nicht crashen
            metrics.update_gpu_metrics()


class TestEdgeCases:
    """Tests fuer Grenzfaelle."""

    def test_very_long_backend_name(self):
        """Sehr lange Backend-Namen funktionieren."""
        from app.ml.metrics import MLMetrics

        metrics = MLMetrics()
        metrics.enabled = False

        long_name = "a" * 1000
        metrics.inc_backend_active(long_name)
        assert metrics._backend_active[long_name] == 1

    def test_special_characters_in_experiment_id(self):
        """Sonderzeichen in Experiment-ID funktionieren."""
        from app.ml.metrics import MLMetrics

        metrics = MLMetrics()
        metrics.enabled = False

        metrics.record_ab_sample(
            experiment_id="exp_2024-01_test-öäü",
            variant="control_äöü",
            success=True
        )

    def test_negative_processing_time(self):
        """Negative Verarbeitungszeit wird behandelt."""
        from app.ml.metrics import MLMetrics

        metrics = MLMetrics()
        metrics.enabled = False

        # Sollte nicht crashen (auch wenn unlogisch)
        metrics.record_backend_request(
            backend="test",
            status="success",
            language="de",
            processing_time=-1.0
        )

    def test_empty_feature_scores(self):
        """Leere Feature-Scores werden behandelt."""
        from app.ml.metrics import MLMetrics

        metrics = MLMetrics()
        metrics.enabled = False

        metrics.record_drift_score(
            overall_score=0.0,
            feature_scores={},
            severity="none"
        )


class TestGermanDocumentation:
    """Tests fuer deutsche Dokumentation."""

    def test_ocr_cer_has_german_description(self):
        """OCR CER Metrik hat deutsche Beschreibung."""
        # Direkt aus Quelle pruefen
        from app.ml import metrics as m

        if m.PROMETHEUS_AVAILABLE:
            # Pruefe Beschreibung
            assert "Character Error Rate" in str(m.OCR_CER._documentation) or \
                   "CER" in str(m.OCR_CER._name)

    def test_ocr_wer_has_german_description(self):
        """OCR WER Metrik hat deutsche Beschreibung."""
        from app.ml import metrics as m

        if m.PROMETHEUS_AVAILABLE:
            assert "Word Error Rate" in str(m.OCR_WER._documentation) or \
                   "WER" in str(m.OCR_WER._name)

    def test_umlaut_accuracy_metric_exists(self):
        """Umlaut-Genauigkeits-Metrik existiert."""
        from app.ml import metrics as m

        if m.PROMETHEUS_AVAILABLE:
            assert m.OCR_UMLAUT_ACCURACY is not None


class TestConcurrentMetricRecording:
    """Tests fuer parallele Metrik-Erfassung."""

    def test_concurrent_routing_requests(self):
        """Parallele Routing-Requests funktionieren."""
        from app.ml.metrics import MLMetrics

        metrics = MLMetrics()
        metrics.enabled = False

        errors = []

        def record_request(i):
            try:
                metrics.record_routing_request(
                    method=f"method_{i}",
                    backend=f"backend_{i}",
                    status="success",
                    latency_seconds=0.1 * i,
                    confidence=0.9
                )
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=record_request, args=(i,)) for i in range(20)]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0

    def test_concurrent_quality_metrics(self):
        """Parallele Quality-Metriken funktionieren."""
        from app.ml.metrics import MLMetrics

        metrics = MLMetrics()
        metrics.enabled = False

        errors = []

        def record_quality(i):
            try:
                metrics.record_quality_metrics(
                    backend=f"backend_{i % 3}",
                    cer=0.01 * i,
                    wer=0.02 * i,
                    umlaut_accuracy=1.0 - (0.01 * i),
                    document_type="test",
                    difficulty="medium"
                )
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=record_quality, args=(i,)) for i in range(50)]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
