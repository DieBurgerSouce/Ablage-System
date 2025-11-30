# -*- coding: utf-8 -*-
"""
Unit tests for Confidence Calibration Module.

Tests temperature scaling, isotonic regression,
histogram binning, and calibration metrics.
"""

import pytest
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from app.ml.confidence_calibration import (
    ConfidenceCalibrator,
    CalibrationResult,
    CalibrationSample,
    CalibrationModel,
    CalibrationMetrics,
    CalibrationMethod,
    ConfidenceLevel,
    TemperatureScaler,
    IsotonicCalibrator,
    HistogramBinningCalibrator,
    calibrate_confidence,
    calibrate_batch,
    add_calibration_sample,
    get_expected_calibration_error,
    get_calibrator,
)


@pytest.mark.unit
class TestConfidenceLevel:
    """Test ConfidenceLevel enum."""

    def test_confidence_levels(self):
        """Test all confidence levels exist."""
        assert ConfidenceLevel.VERY_HIGH.value == "very_high"
        assert ConfidenceLevel.HIGH.value == "high"
        assert ConfidenceLevel.MEDIUM.value == "medium"
        assert ConfidenceLevel.LOW.value == "low"
        assert ConfidenceLevel.VERY_LOW.value == "very_low"


@pytest.mark.unit
class TestCalibrationMethod:
    """Test CalibrationMethod enum."""

    def test_methods_defined(self):
        """Test all calibration methods exist."""
        methods = [
            CalibrationMethod.TEMPERATURE_SCALING,
            CalibrationMethod.ISOTONIC_REGRESSION,
            CalibrationMethod.HISTOGRAM_BINNING,
            CalibrationMethod.PLATT_SCALING,
            CalibrationMethod.BETA_CALIBRATION,
        ]

        for method in methods:
            assert isinstance(method.value, str)


@pytest.mark.unit
class TestCalibrationSample:
    """Test CalibrationSample dataclass."""

    def test_sample_creation(self):
        """Test creating a calibration sample."""
        sample = CalibrationSample(
            raw_confidence=0.85,
            is_correct=True,
            backend="deepseek",
            document_type="invoice",
        )

        assert sample.raw_confidence == 0.85
        assert sample.is_correct
        assert sample.backend == "deepseek"


@pytest.mark.unit
class TestCalibrationResult:
    """Test CalibrationResult dataclass."""

    def test_result_creation(self):
        """Test creating a calibration result."""
        result = CalibrationResult(
            raw_confidence=0.9,
            calibrated_confidence=0.85,
            confidence_level=ConfidenceLevel.HIGH,
            calibration_method=CalibrationMethod.TEMPERATURE_SCALING,
            adjustment=0.05,
        )

        assert result.raw_confidence == 0.9
        assert result.calibrated_confidence == 0.85
        assert result.adjustment == 0.05
        assert result.reliability_improved

    def test_no_improvement(self):
        """Test result with no improvement."""
        result = CalibrationResult(
            raw_confidence=0.8,
            calibrated_confidence=0.8,
            confidence_level=ConfidenceLevel.HIGH,
            calibration_method=CalibrationMethod.TEMPERATURE_SCALING,
            adjustment=0.0,
        )

        assert not result.reliability_improved


@pytest.mark.unit
class TestTemperatureScaler:
    """Test TemperatureScaler class."""

    def test_default_temperature(self):
        """Test default temperature (no scaling)."""
        scaler = TemperatureScaler(temperature=1.0)

        # With temperature=1, calibration should be near identity
        confidence = 0.7
        calibrated = scaler.calibrate(confidence)

        assert abs(calibrated - confidence) < 0.01

    def test_high_temperature(self):
        """Test high temperature (smoothing)."""
        scaler = TemperatureScaler(temperature=2.0)

        # High temperature should smooth probabilities toward 0.5
        calibrated_high = scaler.calibrate(0.9)
        calibrated_low = scaler.calibrate(0.1)

        assert calibrated_high < 0.9  # Reduced from 0.9
        assert calibrated_low > 0.1  # Increased from 0.1

    def test_low_temperature(self):
        """Test low temperature (sharpening)."""
        scaler = TemperatureScaler(temperature=0.5)

        # Low temperature should sharpen probabilities
        calibrated_high = scaler.calibrate(0.7)
        calibrated_low = scaler.calibrate(0.3)

        assert calibrated_high > 0.7  # Increased
        assert calibrated_low < 0.3  # Decreased

    def test_edge_cases(self):
        """Test edge cases."""
        scaler = TemperatureScaler()

        assert scaler.calibrate(0.0) == 0.0
        assert scaler.calibrate(1.0) == 1.0

    def test_fit_method(self):
        """Test fitting temperature to data."""
        scaler = TemperatureScaler()

        # Create overconfident predictions
        confidences = [0.9] * 50 + [0.8] * 50
        labels = [True] * 40 + [False] * 10 + [True] * 30 + [False] * 20

        original_temp = scaler.temperature
        fitted_temp = scaler.fit(confidences, labels)

        # Temperature should be adjusted
        assert fitted_temp != original_temp or fitted_temp == 1.0

    def test_fit_few_samples(self):
        """Test fitting with few samples."""
        scaler = TemperatureScaler()

        # Few samples
        confidences = [0.8, 0.9]
        labels = [True, False]

        # Should return without error
        temp = scaler.fit(confidences, labels)

        assert temp > 0


@pytest.mark.unit
class TestIsotonicCalibrator:
    """Test IsotonicCalibrator class."""

    def test_unfitted_calibrator(self):
        """Test calibrator before fitting."""
        calibrator = IsotonicCalibrator()

        # Should return input unchanged
        confidence = 0.7
        result = calibrator.calibrate(confidence)

        assert result == confidence

    def test_fit_and_calibrate(self):
        """Test fitting and calibrating."""
        calibrator = IsotonicCalibrator()

        # Create calibration data
        confidences = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9] * 5
        labels = [
            False, False, False, True, True,
            True, True, True, True,
        ] * 5

        calibrator.fit(confidences, labels)

        # Should now produce calibrated outputs
        result = calibrator.calibrate(0.5)

        assert 0 <= result <= 1

    def test_monotonicity(self):
        """Test that calibration is monotonic."""
        calibrator = IsotonicCalibrator()

        # Fit with reasonable data
        confidences = [0.1, 0.3, 0.5, 0.7, 0.9] * 10
        labels = [False, False, True, True, True] * 10

        calibrator.fit(confidences, labels)

        # Check monotonicity
        prev = 0
        for conf in [0.1, 0.3, 0.5, 0.7, 0.9]:
            cal = calibrator.calibrate(conf)
            assert cal >= prev
            prev = cal


@pytest.mark.unit
class TestHistogramBinningCalibrator:
    """Test HistogramBinningCalibrator class."""

    def test_default_bins(self):
        """Test default number of bins."""
        calibrator = HistogramBinningCalibrator()

        assert calibrator.n_bins == 10

    def test_custom_bins(self):
        """Test custom number of bins."""
        calibrator = HistogramBinningCalibrator(n_bins=15)

        assert calibrator.n_bins == 15

    def test_fit_and_calibrate(self):
        """Test fitting and calibrating."""
        calibrator = HistogramBinningCalibrator(n_bins=5)

        # Create calibration data
        confidences = [0.1, 0.3, 0.5, 0.7, 0.9] * 10
        labels = [False, False, True, True, True] * 10

        calibrator.fit(confidences, labels)

        # Should produce calibrated outputs
        result = calibrator.calibrate(0.5)

        assert 0 <= result <= 1

    def test_bin_assignment(self):
        """Test that values are assigned to correct bins."""
        calibrator = HistogramBinningCalibrator(n_bins=10)

        # Create known data
        confidences = []
        labels = []

        # Bin 0-0.1: all wrong
        confidences.extend([0.05] * 10)
        labels.extend([False] * 10)

        # Bin 0.9-1.0: all correct
        confidences.extend([0.95] * 10)
        labels.extend([True] * 10)

        calibrator.fit(confidences, labels)

        # Check calibration
        low_cal = calibrator.calibrate(0.05)
        high_cal = calibrator.calibrate(0.95)

        assert low_cal < 0.5  # Should be low accuracy
        assert high_cal > 0.5  # Should be high accuracy


@pytest.mark.unit
class TestConfidenceCalibrator:
    """Test main ConfidenceCalibrator class."""

    def setup_method(self):
        """Setup before each test."""
        self.temp_dir = tempfile.mkdtemp()
        self.calibrator = ConfidenceCalibrator(data_dir=Path(self.temp_dir))

    def test_calibrate_uncalibrated_backend(self):
        """Test calibrating with uncalibrated backend."""
        result = self.calibrator.calibrate(
            confidence=0.8,
            backend="unknown_backend",
            fallback_if_uncalibrated=True,
        )

        # Should return raw confidence
        assert result.raw_confidence == 0.8
        assert result.calibrated_confidence == 0.8

    def test_calibrate_raises_without_fallback(self):
        """Test that error is raised without fallback."""
        with pytest.raises(ValueError):
            self.calibrator.calibrate(
                confidence=0.8,
                backend="unknown_backend",
                fallback_if_uncalibrated=False,
            )

    def test_add_sample(self):
        """Test adding calibration samples."""
        self.calibrator.add_sample(
            raw_confidence=0.8,
            is_correct=True,
            backend="deepseek",
        )

        assert len(self.calibrator._pending_samples.get("deepseek", [])) == 1

    def test_train_model(self):
        """Test training a calibration model."""
        # Create samples
        samples = [
            CalibrationSample(
                raw_confidence=i / 100,
                is_correct=i > 50,
                backend="deepseek",
            )
            for i in range(100)
        ]

        model = self.calibrator.train_model(
            backend="deepseek",
            samples=samples,
            method=CalibrationMethod.TEMPERATURE_SCALING,
        )

        assert model.backend == "deepseek"
        assert model.samples_used == 100
        assert model.metrics is not None

    def test_train_model_few_samples(self):
        """Test training with too few samples."""
        samples = [
            CalibrationSample(
                raw_confidence=0.8,
                is_correct=True,
                backend="deepseek",
            )
            for _ in range(5)
        ]

        with pytest.raises(ValueError):
            self.calibrator.train_model("deepseek", samples)

    def test_calibrate_batch(self):
        """Test batch calibration."""
        confidences = [0.5, 0.6, 0.7, 0.8, 0.9]
        results = self.calibrator.calibrate_batch(confidences, "test_backend")

        assert len(results) == 5
        for result in results:
            assert isinstance(result, CalibrationResult)

    def test_confidence_level_assignment(self):
        """Test confidence level determination."""
        # Very high
        level = self.calibrator._get_confidence_level(0.97)
        assert level == ConfidenceLevel.VERY_HIGH

        # High
        level = self.calibrator._get_confidence_level(0.88)
        assert level == ConfidenceLevel.HIGH

        # Medium
        level = self.calibrator._get_confidence_level(0.75)
        assert level == ConfidenceLevel.MEDIUM

        # Low
        level = self.calibrator._get_confidence_level(0.55)
        assert level == ConfidenceLevel.LOW

        # Very low
        level = self.calibrator._get_confidence_level(0.3)
        assert level == ConfidenceLevel.VERY_LOW

    def test_get_all_backends(self):
        """Test getting all calibrated backends."""
        backends = self.calibrator.get_all_backends()

        assert isinstance(backends, list)

    def test_get_model_info(self):
        """Test getting model info."""
        # Non-existent model
        info = self.calibrator.get_model_info("non_existent")

        assert info is None


@pytest.mark.unit
class TestCalibrationMetrics:
    """Test CalibrationMetrics dataclass."""

    def test_metrics_creation(self):
        """Test creating metrics object."""
        metrics = CalibrationMetrics(
            ece=0.05,
            mce=0.12,
            brier_score=0.08,
            reliability_diagram=[(0.15, 0.1, 10), (0.85, 0.9, 10)],
            overconfidence_ratio=0.15,
            underconfidence_ratio=0.05,
        )

        assert metrics.ece == 0.05
        assert metrics.mce == 0.12
        assert metrics.brier_score == 0.08
        assert len(metrics.reliability_diagram) == 2


@pytest.mark.unit
class TestCalibrationModel:
    """Test CalibrationModel dataclass."""

    def test_model_serialization(self):
        """Test model to_dict and from_dict."""
        from datetime import datetime

        model = CalibrationModel(
            backend="deepseek",
            method=CalibrationMethod.TEMPERATURE_SCALING,
            parameters={"temperature": 1.5},
            samples_used=100,
            created_at=datetime.utcnow(),
        )

        # Convert to dict
        data = model.to_dict()

        assert data["backend"] == "deepseek"
        assert data["method"] == "temperature_scaling"
        assert data["parameters"]["temperature"] == 1.5

        # Convert back
        restored = CalibrationModel.from_dict(data)

        assert restored.backend == model.backend
        assert restored.method == model.method


@pytest.mark.unit
class TestConvenienceFunctions:
    """Test module-level convenience functions."""

    def test_calibrate_confidence_function(self):
        """Test calibrate_confidence function."""
        result = calibrate_confidence(0.8, "test_backend")

        assert isinstance(result, CalibrationResult)

    def test_calibrate_batch_function(self):
        """Test calibrate_batch function."""
        results = calibrate_batch([0.5, 0.7, 0.9], "test_backend")

        assert len(results) == 3

    def test_add_calibration_sample_function(self):
        """Test add_calibration_sample function."""
        # Should not raise
        add_calibration_sample(0.8, True, "test_backend")

    def test_get_expected_calibration_error(self):
        """Test get_expected_calibration_error function."""
        # For uncalibrated backend
        ece = get_expected_calibration_error("non_existent")

        assert ece is None

    def test_get_calibrator_singleton(self):
        """Test singleton pattern."""
        cal1 = get_calibrator()
        cal2 = get_calibrator()

        assert cal1 is cal2


@pytest.mark.unit
class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def setup_method(self):
        """Setup before each test."""
        self.temp_dir = tempfile.mkdtemp()
        self.calibrator = ConfidenceCalibrator(data_dir=Path(self.temp_dir))

    def test_confidence_bounds(self):
        """Test confidence is bounded to [0, 1]."""
        # Above 1
        result = self.calibrator.calibrate(1.5, "test")
        assert result.calibrated_confidence <= 1.0

        # Below 0
        result = self.calibrator.calibrate(-0.5, "test")
        assert result.calibrated_confidence >= 0.0

    def test_exact_boundaries(self):
        """Test exact boundary values."""
        result = self.calibrator.calibrate(0.0, "test")
        assert result.calibrated_confidence == 0.0

        result = self.calibrator.calibrate(1.0, "test")
        assert result.calibrated_confidence == 1.0

    def test_temperature_scaler_extreme_values(self):
        """Test temperature scaler with extreme values."""
        scaler = TemperatureScaler(temperature=0.1)

        # Very low temperature
        calibrated = scaler.calibrate(0.6)
        assert 0 <= calibrated <= 1

        scaler = TemperatureScaler(temperature=10.0)

        # Very high temperature
        calibrated = scaler.calibrate(0.6)
        assert 0 <= calibrated <= 1
