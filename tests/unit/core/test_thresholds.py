# -*- coding: utf-8 -*-
"""
Unit Tests für Konfigurierbare Thresholds.

Testet:
- OCR Confidence Thresholds
- GPU Memory Thresholds
- Batch Processing Thresholds
- A/B Testing Thresholds
- Validierung und Konsistenz

Feinpoliert und durchdacht - Enterprise Test Coverage.
"""

import os
from unittest.mock import patch

import pytest

# Test markers
pytestmark = [pytest.mark.unit]


class TestOCRConfidenceThresholds:
    """Tests für OCR Confidence Thresholds."""

    def test_default_values(self):
        """Test Default-Werte."""
        from app.core.thresholds import OCRConfidenceThresholds

        thresholds = OCRConfidenceThresholds()

        assert thresholds.minimum == 0.3
        assert thresholds.low == 0.6
        assert thresholds.medium == 0.75
        assert thresholds.high == 0.9
        assert thresholds.excellent == 0.95

    def test_classify_rejected(self):
        """Test Klassifikation: rejected."""
        from app.core.thresholds import OCRConfidenceThresholds

        thresholds = OCRConfidenceThresholds()

        assert thresholds.classify(0.1) == "rejected"
        assert thresholds.classify(0.29) == "rejected"

    def test_classify_low(self):
        """Test Klassifikation: low."""
        from app.core.thresholds import OCRConfidenceThresholds

        thresholds = OCRConfidenceThresholds()

        assert thresholds.classify(0.3) == "low"
        assert thresholds.classify(0.5) == "low"

    def test_classify_medium(self):
        """Test Klassifikation: medium."""
        from app.core.thresholds import OCRConfidenceThresholds

        thresholds = OCRConfidenceThresholds()

        assert thresholds.classify(0.6) == "medium"
        assert thresholds.classify(0.8) == "medium"

    def test_classify_high(self):
        """Test Klassifikation: high."""
        from app.core.thresholds import OCRConfidenceThresholds

        thresholds = OCRConfidenceThresholds()

        assert thresholds.classify(0.9) == "high"
        assert thresholds.classify(0.94) == "high"

    def test_classify_excellent(self):
        """Test Klassifikation: excellent."""
        from app.core.thresholds import OCRConfidenceThresholds

        thresholds = OCRConfidenceThresholds()

        assert thresholds.classify(0.95) == "excellent"
        assert thresholds.classify(1.0) == "excellent"

    def test_needs_review(self):
        """Test needs_review Logik."""
        from app.core.thresholds import OCRConfidenceThresholds

        thresholds = OCRConfidenceThresholds()

        # Unter auto_accept (0.85) braucht Review
        assert thresholds.needs_review(0.5) is True
        assert thresholds.needs_review(0.8) is True

        # Über auto_accept braucht kein Review
        assert thresholds.needs_review(0.9) is False

        # Unter minimum braucht auch kein Review (wird abgelehnt)
        assert thresholds.needs_review(0.1) is False

    def test_should_retry(self):
        """Test should_retry Logik."""
        from app.core.thresholds import OCRConfidenceThresholds

        thresholds = OCRConfidenceThresholds()

        # Unter auto_reject sollte Retry
        assert thresholds.should_retry(0.3) is True

        # Über auto_reject sollte nicht Retry
        assert thresholds.should_retry(0.5) is False


class TestGPUMemoryThresholds:
    """Tests für GPU Memory Thresholds."""

    def test_default_values(self):
        """Test Default-Werte."""
        from app.core.thresholds import GPUMemoryThresholds

        thresholds = GPUMemoryThresholds()

        assert thresholds.max_usage_percent == 85.0
        assert thresholds.warning_percent == 75.0
        assert thresholds.critical_percent == 90.0
        assert thresholds.min_reserve_gb == 2.0

    def test_get_max_bytes(self):
        """Test Berechnung maximaler Bytes."""
        from app.core.thresholds import GPUMemoryThresholds

        thresholds = GPUMemoryThresholds()

        # 16GB VRAM
        total_bytes = 16 * 1024**3
        max_bytes = thresholds.get_max_bytes(total_bytes)

        # 85% von 16GB = 13.6GB
        expected = int(total_bytes * 0.85)
        assert max_bytes == expected

    def test_get_status_ok(self):
        """Test Status: ok."""
        from app.core.thresholds import GPUMemoryThresholds

        thresholds = GPUMemoryThresholds()

        assert thresholds.get_status(50.0) == "ok"
        assert thresholds.get_status(74.9) == "ok"

    def test_get_status_warning(self):
        """Test Status: warning."""
        from app.core.thresholds import GPUMemoryThresholds

        thresholds = GPUMemoryThresholds()

        assert thresholds.get_status(75.0) == "warning"
        assert thresholds.get_status(89.9) == "warning"

    def test_get_status_critical(self):
        """Test Status: critical."""
        from app.core.thresholds import GPUMemoryThresholds

        thresholds = GPUMemoryThresholds()

        assert thresholds.get_status(90.0) == "critical"
        assert thresholds.get_status(100.0) == "critical"


class TestBatchProcessingThresholds:
    """Tests für Batch Processing Thresholds."""

    def test_default_values(self):
        """Test Default-Werte."""
        from app.core.thresholds import BatchProcessingThresholds

        thresholds = BatchProcessingThresholds()

        assert thresholds.min_batch_size == 1
        assert thresholds.max_batch_size == 32
        assert thresholds.default_batch_size == 4
        assert thresholds.hysteresis_threshold == 100

    def test_calculate_optimal_batch(self):
        """Test optimale Batch-Berechnung."""
        from app.core.thresholds import BatchProcessingThresholds

        thresholds = BatchProcessingThresholds()

        # 10GB verfügbar, 500MB pro Doc = 10*1024*0.85/500 = ~17
        optimal = thresholds.calculate_optimal_batch(10.0, 500)
        assert 1 <= optimal <= 32

    def test_calculate_optimal_batch_clamp_min(self):
        """Test Batch-Berechnung wird nach unten begrenzt."""
        from app.core.thresholds import BatchProcessingThresholds

        thresholds = BatchProcessingThresholds()

        # Sehr wenig VRAM
        optimal = thresholds.calculate_optimal_batch(0.1, 500)
        assert optimal >= thresholds.min_batch_size

    def test_calculate_optimal_batch_clamp_max(self):
        """Test Batch-Berechnung wird nach oben begrenzt."""
        from app.core.thresholds import BatchProcessingThresholds

        thresholds = BatchProcessingThresholds()

        # Sehr viel VRAM
        optimal = thresholds.calculate_optimal_batch(100.0, 100)
        assert optimal <= thresholds.max_batch_size


class TestABTestingThresholds:
    """Tests für A/B Testing Thresholds."""

    def test_default_values(self):
        """Test Default-Werte."""
        from app.core.thresholds import ABTestingThresholds

        thresholds = ABTestingThresholds()

        assert thresholds.min_sample_size == 30
        assert thresholds.confidence_level == 0.95
        assert thresholds.default_traffic_split == 0.5
        assert thresholds.early_stopping_enabled is True


class TestQualityAssuranceThresholds:
    """Tests für Quality Assurance Thresholds."""

    def test_default_values(self):
        """Test Default-Werte."""
        from app.core.thresholds import QualityAssuranceThresholds

        thresholds = QualityAssuranceThresholds()

        assert thresholds.review_threshold == 0.7
        assert thresholds.max_error_rate == 0.1
        assert thresholds.sampling_rate == 0.05


class TestBackendSpecificThresholds:
    """Tests für Backend-spezifische Thresholds."""

    def test_default_values(self):
        """Test Default-Werte."""
        from app.core.thresholds import BackendSpecificThresholds

        thresholds = BackendSpecificThresholds()

        assert thresholds.deepseek_vram_gb == 12.0
        assert thresholds.got_ocr_vram_gb == 10.0
        assert thresholds.surya_gpu_vram_gb == 8.0

    def test_get_backend_config(self):
        """Test Backend-Konfiguration abrufen."""
        from app.core.thresholds import BackendSpecificThresholds

        thresholds = BackendSpecificThresholds()

        config = thresholds.get_backend_config("deepseek")
        assert "min_confidence" in config
        assert "vram_gb" in config
        assert "batch_size" in config

    def test_get_backend_config_unknown(self):
        """Test unbekanntes Backend gibt leeres Dict."""
        from app.core.thresholds import BackendSpecificThresholds

        thresholds = BackendSpecificThresholds()

        config = thresholds.get_backend_config("unknown_backend")
        assert config == {}


class TestThresholdConfig:
    """Tests für zentrale Threshold-Konfiguration."""

    def test_all_categories_present(self):
        """Test dass alle Kategorien vorhanden sind."""
        from app.core.thresholds import ThresholdConfig

        config = ThresholdConfig()

        assert config.confidence is not None
        assert config.gpu_memory is not None
        assert config.batch_processing is not None
        assert config.ab_testing is not None
        assert config.quality_assurance is not None
        assert config.backends is not None

    def test_to_dict(self):
        """Test Serialisierung zu Dict."""
        from app.core.thresholds import ThresholdConfig

        config = ThresholdConfig()
        result = config.to_dict()

        assert "confidence" in result
        assert "gpu_memory" in result
        assert "batch_processing" in result
        assert "ab_testing" in result
        assert "quality_assurance" in result
        assert "backends" in result

    def test_validate_no_errors(self):
        """Test Validierung ohne Fehler."""
        from app.core.thresholds import ThresholdConfig

        config = ThresholdConfig()
        errors = config.validate()

        # Mit Default-Werten sollte keine Fehler geben
        assert len(errors) == 0


class TestValidation:
    """Tests für Threshold-Validierung."""

    def test_confidence_order_violation(self):
        """Test Validierung bei falscher Confidence-Reihenfolge."""
        from app.core.thresholds import ThresholdConfig, OCRConfidenceThresholds

        config = ThresholdConfig()
        # Manipuliere für ungültige Werte
        config.confidence.minimum = 0.8  # Höher als low
        config.confidence.low = 0.6

        errors = config.validate()
        assert len(errors) > 0
        assert any("OCR_CONFIDENCE_MIN" in e for e in errors)

    def test_gpu_threshold_violation(self):
        """Test Validierung bei falschen GPU-Thresholds."""
        from app.core.thresholds import ThresholdConfig

        config = ThresholdConfig()
        config.gpu_memory.warning_percent = 95.0  # Höher als critical
        config.gpu_memory.critical_percent = 90.0

        errors = config.validate()
        assert len(errors) > 0
        assert any("GPU_WARNING_PERCENT" in e for e in errors)

    def test_batch_size_violation(self):
        """Test Validierung bei falschen Batch-Thresholds."""
        from app.core.thresholds import ThresholdConfig

        config = ThresholdConfig()
        config.batch_processing.min_batch_size = 64
        config.batch_processing.max_batch_size = 32

        errors = config.validate()
        assert len(errors) > 0
        assert any("BATCH_MIN_SIZE" in e for e in errors)


class TestEnvironmentVariables:
    """Tests für Umgebungsvariablen-Konfiguration."""

    def test_env_float_override(self):
        """Test Float-Override via Umgebungsvariable."""
        with patch.dict(os.environ, {"OCR_CONFIDENCE_MIN": "0.5"}):
            from app.core.thresholds import OCRConfidenceThresholds

            # Neues Objekt erstellen um Env-Var zu lesen
            thresholds = OCRConfidenceThresholds()
            assert thresholds.minimum == 0.5

    def test_env_int_override(self):
        """Test Int-Override via Umgebungsvariable."""
        with patch.dict(os.environ, {"BATCH_MAX_SIZE": "64"}):
            from app.core.thresholds import BatchProcessingThresholds

            thresholds = BatchProcessingThresholds()
            assert thresholds.max_batch_size == 64

    def test_env_bool_override(self):
        """Test Bool-Override via Umgebungsvariable."""
        with patch.dict(os.environ, {"AB_EARLY_STOPPING": "false"}):
            from app.core.thresholds import ABTestingThresholds

            thresholds = ABTestingThresholds()
            assert thresholds.early_stopping_enabled is False

    def test_env_invalid_float_uses_default(self):
        """Test ungültiger Float-Wert verwendet Default."""
        with patch.dict(os.environ, {"OCR_CONFIDENCE_MIN": "not_a_number"}):
            from app.core.thresholds import OCRConfidenceThresholds

            thresholds = OCRConfidenceThresholds()
            assert thresholds.minimum == 0.3  # Default


class TestConvenienceFunctions:
    """Tests für Convenience-Funktionen."""

    def test_get_threshold_config_singleton(self):
        """Test Singleton-Pattern."""
        import app.core.thresholds as module
        module._threshold_config = None

        from app.core.thresholds import get_threshold_config

        config1 = get_threshold_config()
        config2 = get_threshold_config()

        assert config1 is config2

        # Cleanup
        module._threshold_config = None

    def test_reload_threshold_config(self):
        """Test Neu-Laden der Konfiguration."""
        import app.core.thresholds as module
        module._threshold_config = None

        from app.core.thresholds import get_threshold_config, reload_threshold_config

        config1 = get_threshold_config()
        config2 = reload_threshold_config()

        # Nach Reload sollte neue Instanz sein
        assert config1 is not config2

        # Cleanup
        module._threshold_config = None

    def test_convenience_aliases(self):
        """Test Convenience-Aliases."""
        import app.core.thresholds as module
        module._threshold_config = None

        from app.core.thresholds import (
            get_confidence_thresholds,
            get_gpu_thresholds,
            get_batch_thresholds,
            get_ab_thresholds,
            get_qa_thresholds,
            get_backend_thresholds,
        )

        assert get_confidence_thresholds() is not None
        assert get_gpu_thresholds() is not None
        assert get_batch_thresholds() is not None
        assert get_ab_thresholds() is not None
        assert get_qa_thresholds() is not None
        assert isinstance(get_backend_thresholds("deepseek"), dict)

        # Cleanup
        module._threshold_config = None
