# -*- coding: utf-8 -*-
"""
Unit tests for Drift Detector.

Tests:
- DriftSeverity enum
- FeatureDrift dataclass
- DriftReport creation
- Sample collection
- Drift detection
- Report generation
"""

import pytest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import Mock, patch
import tempfile

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


class TestDriftSeverity:
    """Test DriftSeverity enum."""

    @pytest.mark.unit
    def test_severity_values(self):
        """Test severity enum values."""
        from app.ml.drift_detector import DriftSeverity

        assert DriftSeverity.NONE.value == "none"
        assert DriftSeverity.LOW.value == "low"
        assert DriftSeverity.MEDIUM.value == "medium"
        assert DriftSeverity.HIGH.value == "high"
        assert DriftSeverity.CRITICAL.value == "critical"

    @pytest.mark.unit
    def test_severity_from_score_none(self):
        """Test severity from low score."""
        from app.ml.drift_detector import DriftSeverity

        assert DriftSeverity.from_score(0.05) == DriftSeverity.NONE

    @pytest.mark.unit
    def test_severity_from_score_low(self):
        """Test severity from low-medium score."""
        from app.ml.drift_detector import DriftSeverity

        assert DriftSeverity.from_score(0.15) == DriftSeverity.LOW

    @pytest.mark.unit
    def test_severity_from_score_medium(self):
        """Test severity from medium score."""
        from app.ml.drift_detector import DriftSeverity

        assert DriftSeverity.from_score(0.4) == DriftSeverity.MEDIUM

    @pytest.mark.unit
    def test_severity_from_score_high(self):
        """Test severity from high score."""
        from app.ml.drift_detector import DriftSeverity

        assert DriftSeverity.from_score(0.6) == DriftSeverity.HIGH

    @pytest.mark.unit
    def test_severity_from_score_critical(self):
        """Test severity from critical score."""
        from app.ml.drift_detector import DriftSeverity

        assert DriftSeverity.from_score(0.9) == DriftSeverity.CRITICAL


class TestDriftReport:
    """Test DriftReport dataclass."""

    @pytest.mark.unit
    def test_drift_report_creation(self):
        """Test DriftReport creation."""
        from app.ml.drift_detector import DriftReport, DriftSeverity

        report = DriftReport(
            timestamp=datetime.now(),
            report_id="test123",
            overall_drift_score=0.3,
            severity=DriftSeverity.MEDIUM,
            dataset_drift_detected=True,
            feature_drifts=[],
            prediction_drift=0.1,
            samples_reference=100,
            samples_current=50,
            recommendations=["Überwachung verstärken"],
        )

        assert report.report_id == "test123"
        assert report.overall_drift_score == 0.3
        assert report.severity == DriftSeverity.MEDIUM

    @pytest.mark.unit
    def test_drift_report_to_dict(self):
        """Test DriftReport serialization."""
        from app.ml.drift_detector import DriftReport, DriftSeverity

        report = DriftReport(
            timestamp=datetime.now(),
            report_id="test123",
            overall_drift_score=0.3,
            severity=DriftSeverity.MEDIUM,
            dataset_drift_detected=False,
            feature_drifts=[],
            prediction_drift=None,
            samples_reference=100,
            samples_current=50,
            recommendations=[],
        )

        data = report.to_dict()

        assert "timestamp" in data
        assert data["report_id"] == "test123"
        assert data["severity"] == "medium"

    @pytest.mark.unit
    def test_drift_report_to_json(self):
        """Test DriftReport JSON serialization."""
        from app.ml.drift_detector import DriftReport, DriftSeverity
        import json

        report = DriftReport(
            timestamp=datetime.now(),
            report_id="test123",
            overall_drift_score=0.3,
            severity=DriftSeverity.LOW,
            dataset_drift_detected=False,
            feature_drifts=[],
            prediction_drift=None,
            samples_reference=100,
            samples_current=50,
            recommendations=[],
        )

        json_str = report.to_json()
        data = json.loads(json_str)

        assert data["report_id"] == "test123"


class TestDriftDetectorInitialization:
    """Test DriftDetector initialization."""

    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.mark.unit
    def test_detector_initialization(self, temp_dir):
        """Test detector initializes correctly."""
        from app.ml.drift_detector import DriftDetector

        detector = DriftDetector(
            reference_window_days=7,
            drift_threshold=0.1,
            min_samples=50,
            storage_path=temp_dir,
        )

        assert detector.reference_window_days == 7
        assert detector.drift_threshold == 0.1
        assert detector.min_samples == 50

    @pytest.mark.unit
    def test_detector_creates_storage_directory(self, temp_dir):
        """Test detector creates storage directory."""
        from app.ml.drift_detector import DriftDetector

        storage = temp_dir / "drift_reports"
        detector = DriftDetector(storage_path=storage)

        assert storage.exists()


class TestSampleCollection:
    """Test sample collection functionality."""

    @pytest.fixture
    def detector(self):
        """Create detector with temporary storage."""
        with tempfile.TemporaryDirectory() as tmpdir:
            from app.ml.drift_detector import DriftDetector
            yield DriftDetector(
                min_samples=10,
                storage_path=Path(tmpdir),
            )

    @pytest.mark.unit
    def test_add_sample(self, detector):
        """Test adding a sample."""
        detector.add_sample(
            features={"quality_score": 0.9, "complexity": "high"},
            prediction="deepseek",
        )

        status = detector.get_current_status()
        assert status["reference_samples"] == 1

    @pytest.mark.unit
    def test_samples_go_to_reference_initially(self, detector):
        """Test samples go to reference window first."""
        for i in range(5):
            detector.add_sample(
                features={"quality_score": 0.9},
                prediction="deepseek",
            )

        status = detector.get_current_status()
        assert status["reference_samples"] == 5
        assert status["current_samples"] == 0

    @pytest.mark.unit
    def test_samples_go_to_current_after_cutoff(self, detector):
        """Test samples go to current after reference window."""
        # Add reference samples with past timestamps
        past = datetime.now() - timedelta(days=10)
        for i in range(5):
            detector.add_sample(
                features={"quality_score": 0.9},
                prediction="deepseek",
                timestamp=past + timedelta(hours=i),
            )

        # Add current samples with recent timestamps
        now = datetime.now()
        for i in range(3):
            detector.add_sample(
                features={"quality_score": 0.8},
                prediction="got_ocr",
                timestamp=now + timedelta(hours=i),
            )

        status = detector.get_current_status()
        assert status["reference_samples"] == 5
        assert status["current_samples"] == 3


class TestDriftDetection:
    """Test drift detection functionality."""

    @pytest.fixture
    def detector_with_data(self):
        """Create detector with sample data."""
        with tempfile.TemporaryDirectory() as tmpdir:
            from app.ml.drift_detector import DriftDetector

            detector = DriftDetector(
                min_samples=10,
                storage_path=Path(tmpdir),
            )

            # Add reference data
            past = datetime.now() - timedelta(days=10)
            for i in range(15):
                detector.add_sample(
                    features={
                        "quality_score": 0.9,
                        "file_size_mb": 1.0,
                        "complexity": "medium",
                    },
                    prediction="deepseek",
                    timestamp=past + timedelta(hours=i),
                )

            # Add current data (with some drift)
            now = datetime.now()
            for i in range(15):
                detector.add_sample(
                    features={
                        "quality_score": 0.7,  # Lower quality
                        "file_size_mb": 2.0,   # Larger files
                        "complexity": "high",   # More complex
                    },
                    prediction="got_ocr",  # Different backend
                    timestamp=now + timedelta(hours=i),
                )

            yield detector

    @pytest.mark.unit
    def test_detect_drift_returns_report(self, detector_with_data):
        """Test detect_drift returns a report."""
        from app.ml.drift_detector import DriftReport

        report = detector_with_data.detect_drift()

        assert isinstance(report, DriftReport)
        assert report.report_id is not None
        assert report.timestamp is not None

    @pytest.mark.unit
    def test_detect_drift_has_scores(self, detector_with_data):
        """Test detect_drift calculates scores."""
        report = detector_with_data.detect_drift()

        assert report.overall_drift_score >= 0
        assert report.overall_drift_score <= 1

    @pytest.mark.unit
    def test_detect_drift_has_recommendations(self, detector_with_data):
        """Test detect_drift generates recommendations."""
        report = detector_with_data.detect_drift()

        assert isinstance(report.recommendations, list)

    @pytest.mark.unit
    def test_insufficient_data_report(self):
        """Test report with insufficient data."""
        with tempfile.TemporaryDirectory() as tmpdir:
            from app.ml.drift_detector import DriftDetector, DriftSeverity

            detector = DriftDetector(
                min_samples=100,
                storage_path=Path(tmpdir),
            )

            # Add only few samples
            for i in range(5):
                detector.add_sample(
                    features={"quality_score": 0.9},
                    prediction="deepseek",
                )

            report = detector.detect_drift()

            assert report.severity == DriftSeverity.NONE
            assert "Unzureichende Daten" in report.recommendations[0]


class TestDriftHistory:
    """Test drift history functionality."""

    @pytest.fixture
    def detector(self):
        """Create detector with temporary storage."""
        with tempfile.TemporaryDirectory() as tmpdir:
            from app.ml.drift_detector import DriftDetector
            yield DriftDetector(
                min_samples=10,
                storage_path=Path(tmpdir),
            )

    @pytest.mark.unit
    def test_get_drift_history_empty(self, detector):
        """Test empty drift history."""
        history = detector.get_drift_history()

        assert isinstance(history, list)
        assert len(history) == 0

    @pytest.mark.unit
    def test_drift_history_after_detection(self, detector):
        """Test history after running detection."""
        # Add enough data
        past = datetime.now() - timedelta(days=10)
        for i in range(10):
            detector.add_sample(
                features={"quality_score": 0.9},
                prediction="deepseek",
                timestamp=past + timedelta(hours=i),
            )

        now = datetime.now()
        for i in range(10):
            detector.add_sample(
                features={"quality_score": 0.8},
                prediction="got_ocr",
                timestamp=now + timedelta(hours=i),
            )

        # Run detection
        detector.detect_drift()

        history = detector.get_drift_history()
        assert len(history) == 1


class TestReferenceReset:
    """Test reference window reset."""

    @pytest.fixture
    def detector(self):
        """Create detector with temporary storage."""
        with tempfile.TemporaryDirectory() as tmpdir:
            from app.ml.drift_detector import DriftDetector
            yield DriftDetector(
                min_samples=10,
                storage_path=Path(tmpdir),
            )

    @pytest.mark.unit
    def test_reset_reference_window(self, detector):
        """Test resetting reference window."""
        # Add reference data
        past = datetime.now() - timedelta(days=10)
        for i in range(10):
            detector.add_sample(
                features={"quality_score": 0.9},
                prediction="deepseek",
                timestamp=past + timedelta(hours=i),
            )

        # Add current data
        now = datetime.now()
        for i in range(10):
            detector.add_sample(
                features={"quality_score": 0.8},
                prediction="got_ocr",
                timestamp=now + timedelta(hours=i),
            )

        status_before = detector.get_current_status()
        assert status_before["current_samples"] == 10

        # Reset
        detector.reset_reference_window()

        status_after = detector.get_current_status()
        assert status_after["reference_samples"] == 10
        assert status_after["current_samples"] == 0


class TestSingletonDetector:
    """Test singleton detector access."""

    @pytest.mark.unit
    def test_get_drift_detector_singleton(self, tmp_path, monkeypatch):
        """Test get_drift_detector returns same instance."""
        import app.ml.drift_detector as dd

        # Default-Storage 'data/drift_reports' ist auf dem read-only Container-
        # Rootfs nicht beschreibbar -> Singleton mit tmp-Pfad vorinitialisieren.
        detector = dd.DriftDetector(storage_path=tmp_path / "drift_reports")
        monkeypatch.setattr(dd, "_drift_detector", detector)

        from app.ml.drift_detector import get_drift_detector

        detector1 = get_drift_detector()
        detector2 = get_drift_detector()

        assert detector1 is detector2
        assert detector1 is detector


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-m", "unit"])
