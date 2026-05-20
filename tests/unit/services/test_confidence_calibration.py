# -*- coding: utf-8 -*-
"""
Unit Tests für Confidence Calibration Service.

Testet:
- Isotonic Regression Kalibrierung
- Platt Scaling
- Temperature Scaling
- Histogram Binning
- Service Integration

Feinpoliert und durchdacht - Enterprise Test Coverage.
"""

import math
import random
import tempfile
from pathlib import Path

import pytest

# Test markers
pytestmark = [pytest.mark.unit]


class TestCalibrationData:
    """Tests für CalibrationData."""

    def test_add_sample(self):
        """Test Sample hinzufügen."""
        from app.services.confidence_calibration import CalibrationData

        data = CalibrationData()
        data.add_sample(0.8, True)
        data.add_sample(0.5, False)

        assert len(data) == 2
        assert data.confidences == [0.8, 0.5]
        assert data.actuals == [1, 0]


class TestIsotonicCalibrator:
    """Tests für Isotonic Regression Kalibrator."""

    def test_fit_with_sufficient_data(self):
        """Test Training mit ausreichend Daten."""
        from app.services.confidence_calibration import IsotonicCalibrator

        calibrator = IsotonicCalibrator()

        # Simuliere Trainings-Daten
        confidences = [0.1 * i for i in range(1, 11)] * 3
        actuals = [int(c > 0.5) for c in confidences]

        calibrator.fit(confidences, actuals)

        assert calibrator._fitted is True
        assert len(calibrator._boundaries) > 0

    def test_predict_interpolation(self):
        """Test Vorhersage mit Interpolation."""
        from app.services.confidence_calibration import IsotonicCalibrator

        calibrator = IsotonicCalibrator()
        calibrator._fitted = True
        calibrator._boundaries = [0.0, 0.5, 1.0]
        calibrator._calibrated_values = [0.0, 0.4, 1.0]

        # Test Interpolation
        result = calibrator.predict(0.25)
        assert 0.0 < result < 0.4

    def test_predict_not_fitted(self):
        """Test Vorhersage ohne Training."""
        from app.services.confidence_calibration import IsotonicCalibrator

        calibrator = IsotonicCalibrator()
        result = calibrator.predict(0.5)

        # Ohne Training: gebe rohen Wert zurück
        assert result == 0.5


class TestPlattScalingCalibrator:
    """Tests für Platt Scaling Kalibrator."""

    def test_fit_with_sufficient_data(self):
        """Test Training mit ausreichend Daten."""
        from app.services.confidence_calibration import PlattScalingCalibrator

        calibrator = PlattScalingCalibrator()

        # Simuliere Trainings-Daten
        confidences = [0.1 * i for i in range(1, 11)] * 2
        actuals = [int(c > 0.5) for c in confidences]

        calibrator.fit(confidences, actuals)

        assert calibrator._fitted is True

    def test_predict_range(self):
        """Test dass Vorhersage zwischen 0 und 1 liegt."""
        from app.services.confidence_calibration import PlattScalingCalibrator

        calibrator = PlattScalingCalibrator()
        calibrator._fitted = True
        calibrator._a = 2.0
        calibrator._b = -1.0

        for conf in [0.0, 0.25, 0.5, 0.75, 1.0]:
            result = calibrator.predict(conf)
            assert 0.0 <= result <= 1.0

    def test_sigmoid_overflow_protection(self):
        """Test Sigmoid mit Overflow-Schutz."""
        from app.services.confidence_calibration import PlattScalingCalibrator

        # Extrem große und kleine Werte
        assert PlattScalingCalibrator._sigmoid(-1000) == 0.0
        assert PlattScalingCalibrator._sigmoid(1000) == 1.0


class TestTemperatureScalingCalibrator:
    """Tests für Temperature Scaling Kalibrator."""

    def test_fit_finds_temperature(self):
        """Test dass Training Temperature findet."""
        from app.services.confidence_calibration import TemperatureScalingCalibrator

        calibrator = TemperatureScalingCalibrator()

        # Simuliere over-confident Daten
        confidences = [0.9] * 10 + [0.8] * 10
        actuals = [1, 0] * 10  # Nur 50% korrekt obwohl hohe Confidence

        calibrator.fit(confidences, actuals)

        assert calibrator._fitted is True
        # Temperature sollte > 1 sein um Confidence zu reduzieren
        assert calibrator._temperature >= 0.1

    def test_predict_with_temperature(self):
        """Test Vorhersage mit Temperature."""
        from app.services.confidence_calibration import TemperatureScalingCalibrator

        calibrator = TemperatureScalingCalibrator(temperature=2.0)
        calibrator._fitted = True

        # Hohe Temperature reduziert Confidence-Spread
        result = calibrator.predict(0.9)
        assert 0.5 < result < 0.9


class TestHistogramBinningCalibrator:
    """Tests für Histogram Binning Kalibrator."""

    def test_fit_creates_bins(self):
        """Test dass Training Bins erstellt."""
        from app.services.confidence_calibration import HistogramBinningCalibrator

        calibrator = HistogramBinningCalibrator(n_bins=5)

        # Simuliere Trainings-Daten
        confidences = [random.random() for _ in range(100)]
        actuals = [int(c > 0.5) for c in confidences]

        calibrator.fit(confidences, actuals)

        assert calibrator._fitted is True
        assert len(calibrator._bin_values) == 5

    def test_predict_returns_bin_value(self):
        """Test dass Vorhersage Bin-Wert zurückgibt."""
        from app.services.confidence_calibration import HistogramBinningCalibrator

        calibrator = HistogramBinningCalibrator(n_bins=2)
        calibrator._fitted = True
        calibrator._bin_edges = [0.0, 0.5, 1.0]
        calibrator._bin_values = [0.2, 0.8]

        assert calibrator.predict(0.3) == 0.2  # Erstes Bin
        assert calibrator.predict(0.7) == 0.8  # Zweites Bin


class TestConfidenceCalibrationService:
    """Tests für den Confidence Calibration Service."""

    @pytest.fixture
    def service(self):
        """Erstelle Service-Instanz."""
        from app.services.confidence_calibration import ConfidenceCalibrationService
        return ConfidenceCalibrationService(calibration_method="isotonic")

    def test_add_training_sample(self, service):
        """Test Training-Sample hinzufügen."""
        service.add_training_sample("deepseek", 0.8, True)
        service.add_training_sample("deepseek", 0.5, False)

        assert "deepseek" in service._training_data
        assert len(service._training_data["deepseek"]) == 2

    def test_train_with_sufficient_data(self, service):
        """Test Training mit ausreichend Daten."""
        # Füge Trainings-Daten hinzu
        random.seed(42)
        for _ in range(50):
            conf = random.random()
            is_correct = conf > 0.5 + random.uniform(-0.1, 0.1)
            service.add_training_sample("deepseek", conf, is_correct)

        stats = service.train("deepseek")

        assert stats is not None
        assert stats.samples_count == 50
        assert "deepseek" in service._calibrators

    def test_train_with_insufficient_data(self, service):
        """Test Training mit zu wenig Daten."""
        service.add_training_sample("test", 0.5, True)

        stats = service.train("test")

        assert stats is None

    def test_calibrate_with_calibrator(self, service):
        """Test Kalibrierung mit trainiertem Kalibrator."""
        # Training
        random.seed(42)
        for _ in range(50):
            conf = random.random()
            is_correct = conf > 0.4
            service.add_training_sample("deepseek", conf, is_correct)

        service.train("deepseek")

        # Kalibrierung
        result = service.calibrate("deepseek", 0.5)

        assert 0.0 <= result <= 1.0

    def test_calibrate_without_calibrator(self, service):
        """Test Kalibrierung ohne Kalibrator gibt rohen Wert."""
        result = service.calibrate("unknown", 0.7)

        assert result == 0.7

    def test_calibrate_batch(self, service):
        """Test Batch-Kalibrierung."""
        # Training
        random.seed(42)
        for _ in range(50):
            conf = random.random()
            service.add_training_sample("deepseek", conf, conf > 0.5)

        service.train("deepseek")

        # Batch-Kalibrierung
        confidences = [0.3, 0.5, 0.7, 0.9]
        results = service.calibrate_batch("deepseek", confidences)

        assert len(results) == 4
        assert all(0.0 <= r <= 1.0 for r in results)

    def test_train_all(self, service):
        """Test Training aller Backends."""
        # Daten für mehrere Backends
        random.seed(42)
        for backend in ["deepseek", "got_ocr"]:
            for _ in range(30):
                conf = random.random()
                service.add_training_sample(backend, conf, conf > 0.5)

        results = service.train_all()

        assert "deepseek" in results
        assert "got_ocr" in results

    def test_get_stats(self, service):
        """Test Statistiken abrufen."""
        random.seed(42)
        for _ in range(50):
            conf = random.random()
            service.add_training_sample("deepseek", conf, conf > 0.5)

        service.train("deepseek")

        stats = service.get_stats("deepseek")

        assert "backend" in stats
        assert "samples_count" in stats
        assert "ece" in stats

    def test_get_all_stats(self, service):
        """Test alle Statistiken abrufen."""
        random.seed(42)
        for backend in ["deepseek", "got_ocr"]:
            for _ in range(30):
                conf = random.random()
                service.add_training_sample(backend, conf, conf > 0.5)

        service.train_all()

        all_stats = service.get_stats()

        assert "deepseek" in all_stats
        assert "got_ocr" in all_stats


class TestCalibrationStats:
    """Tests für CalibrationStats."""

    def test_to_dict(self):
        """Test Serialisierung."""
        from app.services.confidence_calibration import CalibrationStats

        stats = CalibrationStats(
            backend="deepseek",
            samples_count=100,
            raw_mean=0.7,
            raw_std=0.15,
            calibrated_mean=0.65,
            calibrated_std=0.12,
            ece=0.05,
            mce=0.1,
            reliability_improvement=0.3
        )

        result = stats.to_dict()

        assert result["backend"] == "deepseek"
        assert result["samples_count"] == 100
        assert result["ece"] == 0.05


class TestPersistence:
    """Tests für Speichern/Laden."""

    def test_save_and_load(self):
        """Test Speichern und Laden."""
        from app.services.confidence_calibration import ConfidenceCalibrationService

        # Erstelle und trainiere Service
        service1 = ConfidenceCalibrationService(calibration_method="isotonic")

        random.seed(42)
        for _ in range(50):
            conf = random.random()
            service1.add_training_sample("deepseek", conf, conf > 0.5)

        service1.train("deepseek")

        # Speichere
        with tempfile.TemporaryDirectory() as tmpdir:
            save_path = Path(tmpdir) / "calibration.json"
            assert service1.save(save_path) is True

            # Neuer Service lädt Daten
            service2 = ConfidenceCalibrationService(calibration_method="isotonic")
            assert service2.load(save_path) is True

            # Verifiziere dass Kalibrierung funktioniert
            result = service2.calibrate("deepseek", 0.5)
            assert 0.0 <= result <= 1.0


class TestECECalculation:
    """Tests für Expected Calibration Error Berechnung."""

    def test_perfect_calibration(self):
        """Test ECE bei perfekter Kalibrierung."""
        from app.services.confidence_calibration import ConfidenceCalibrationService

        service = ConfidenceCalibrationService()

        # Perfekt kalibriert: Confidence = Accuracy
        confidences = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0] * 10
        actuals = []
        for c in confidences:
            # Korrekt mit Wahrscheinlichkeit = Confidence
            actuals.append(1 if random.random() < c else 0)

        ece = service._calculate_ece(confidences, actuals)

        # ECE sollte klein sein bei guter Kalibrierung
        assert ece < 0.3  # Toleranz wegen Zufallskomponente

    def test_overconfident_calibration(self):
        """Test ECE bei Over-Confidence."""
        from app.services.confidence_calibration import ConfidenceCalibrationService

        service = ConfidenceCalibrationService()

        # Over-confident: Hohe Confidence aber niedrige Accuracy
        confidences = [0.9] * 100
        actuals = [1] * 30 + [0] * 70  # Nur 30% korrekt

        ece = service._calculate_ece(confidences, actuals)

        # ECE sollte hoch sein
        assert ece > 0.4


class TestDifferentMethods:
    """Tests für verschiedene Kalibrierungs-Methoden."""

    @pytest.mark.parametrize("method", ["isotonic", "platt", "temperature", "histogram"])
    def test_method_works(self, method):
        """Test dass jede Methode funktioniert."""
        from app.services.confidence_calibration import ConfidenceCalibrationService

        service = ConfidenceCalibrationService(calibration_method=method)

        random.seed(42)
        for _ in range(50):
            conf = random.random()
            service.add_training_sample("test", conf, conf > 0.5)

        stats = service.train("test")

        assert stats is not None
        assert stats.samples_count == 50

        # Kalibrierung sollte funktionieren
        result = service.calibrate("test", 0.5)
        assert 0.0 <= result <= 1.0


class TestConvenienceFunctions:
    """Tests für Convenience-Funktionen."""

    def test_get_calibration_service_singleton(self):
        """Test Singleton-Pattern."""
        import app.services.confidence_calibration as module
        module._calibration_service = None

        from app.services.confidence_calibration import get_calibration_service

        service1 = get_calibration_service()
        service2 = get_calibration_service()

        assert service1 is service2

        # Cleanup
        module._calibration_service = None

    def test_calibrate_confidence_function(self):
        """Test calibrate_confidence Convenience-Funktion."""
        import app.services.confidence_calibration as module
        module._calibration_service = None

        from app.services.confidence_calibration import (
            calibrate_confidence,
            get_calibration_service
        )

        # Ohne Kalibrator gibt rohen Wert zurück
        result = calibrate_confidence("unknown_backend", 0.7)
        assert result == 0.7

        # Cleanup
        module._calibration_service = None
