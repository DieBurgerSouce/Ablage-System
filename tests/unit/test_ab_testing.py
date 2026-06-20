# -*- coding: utf-8 -*-
"""
Unit tests for A/B Testing Framework.

Tests:
- Variant creation and metrics
- Experiment creation and lifecycle
- Traffic allocation methods
- Result recording
- Statistical significance
"""

import pytest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import Mock, patch
import tempfile

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


class TestVariant:
    """Test Variant dataclass."""

    @pytest.mark.unit
    def test_variant_creation(self):
        """Test Variant creation."""
        from app.ml.ab_testing import Variant

        variant = Variant(
            name="control",
            description="Control group",
            weight=0.5,
            config={"backend": "deepseek"},
        )

        assert variant.name == "control"
        assert variant.weight == 0.5
        assert variant.samples == 0

    @pytest.mark.unit
    def test_variant_conversion_rate(self):
        """Test conversion rate calculation."""
        from app.ml.ab_testing import Variant

        variant = Variant(
            name="test",
            description="Test",
            weight=0.5,
            config={},
            samples=100,
            conversions=80,
        )

        assert variant.conversion_rate == 0.8

    @pytest.mark.unit
    def test_variant_conversion_rate_zero_samples(self):
        """Test conversion rate with zero samples."""
        from app.ml.ab_testing import Variant

        variant = Variant(
            name="test",
            description="Test",
            weight=0.5,
            config={},
        )

        assert variant.conversion_rate == 0.0

    @pytest.mark.unit
    def test_variant_avg_latency(self):
        """Test average latency calculation."""
        from app.ml.ab_testing import Variant

        variant = Variant(
            name="test",
            description="Test",
            weight=0.5,
            config={},
            samples=10,
            total_latency_ms=1000.0,
        )

        assert variant.avg_latency_ms == 100.0

    @pytest.mark.unit
    def test_variant_to_dict(self):
        """Test Variant serialization."""
        from app.ml.ab_testing import Variant

        variant = Variant(
            name="control",
            description="Control",
            weight=0.5,
            config={"backend": "deepseek"},
            samples=50,
            conversions=45,
        )

        data = variant.to_dict()

        assert data["name"] == "control"
        assert "metrics" in data
        assert data["metrics"]["samples"] == 50
        assert data["metrics"]["conversion_rate"] == 0.9


class TestExperimentStatus:
    """Test ExperimentStatus enum."""

    @pytest.mark.unit
    def test_status_values(self):
        """Test status enum values."""
        from app.ml.ab_testing import ExperimentStatus

        assert ExperimentStatus.DRAFT.value == "draft"
        assert ExperimentStatus.RUNNING.value == "running"
        assert ExperimentStatus.COMPLETED.value == "completed"


class TestAllocationMethod:
    """Test AllocationMethod enum."""

    @pytest.mark.unit
    def test_allocation_values(self):
        """Test allocation method values."""
        from app.ml.ab_testing import AllocationMethod

        assert AllocationMethod.RANDOM.value == "random"
        assert AllocationMethod.STICKY.value == "sticky"
        assert AllocationMethod.ROUND_ROBIN.value == "round_robin"


class TestExperiment:
    """Test Experiment class."""

    @pytest.fixture
    def experiment(self):
        """Create test experiment."""
        from app.ml.ab_testing import Experiment, Variant

        return Experiment(
            experiment_id="exp_test_123",
            name="Test Experiment",
            description="Testing A/B",
            variants=[
                Variant(
                    name="control",
                    description="Control",
                    weight=0.5,
                    config={"backend": "deepseek"},
                ),
                Variant(
                    name="treatment",
                    description="Treatment",
                    weight=0.5,
                    config={"backend": "got_ocr"},
                ),
            ],
        )

    @pytest.mark.unit
    def test_experiment_creation(self, experiment):
        """Test experiment creation."""
        from app.ml.ab_testing import ExperimentStatus

        assert experiment.experiment_id == "exp_test_123"
        assert experiment.status == ExperimentStatus.DRAFT
        assert len(experiment.variants) == 2

    @pytest.mark.unit
    def test_experiment_weight_normalization(self):
        """Test that weights are normalized."""
        from app.ml.ab_testing import Experiment, Variant

        experiment = Experiment(
            experiment_id="test",
            name="Test",
            description="Test",
            variants=[
                Variant(name="a", description="A", weight=1.0, config={}),
                Variant(name="b", description="B", weight=1.0, config={}),
            ],
        )

        total = sum(v.weight for v in experiment.variants)
        assert abs(total - 1.0) < 0.01

    @pytest.mark.unit
    def test_sticky_allocation_consistency(self, experiment):
        """Test sticky allocation returns same variant for same ID."""
        variant1 = experiment.allocate_variant("doc123")
        variant2 = experiment.allocate_variant("doc123")

        assert variant1.name == variant2.name

    @pytest.mark.unit
    def test_sticky_allocation_different_ids(self, experiment):
        """Test different IDs can get different variants."""
        variants = set()
        for i in range(100):
            v = experiment.allocate_variant(f"doc_{i}")
            variants.add(v.name)

        # With 50/50 split, should see both variants over 100 samples
        assert len(variants) == 2

    @pytest.mark.unit
    def test_round_robin_allocation(self):
        """Test round robin alternates variants."""
        from app.ml.ab_testing import Experiment, Variant, AllocationMethod

        experiment = Experiment(
            experiment_id="test",
            name="Test",
            description="Test",
            allocation_method=AllocationMethod.ROUND_ROBIN,
            variants=[
                Variant(name="a", description="A", weight=0.5, config={}),
                Variant(name="b", description="B", weight=0.5, config={}),
            ],
        )

        v1 = experiment.allocate_variant("doc1")
        v2 = experiment.allocate_variant("doc2")
        v3 = experiment.allocate_variant("doc3")

        # Should alternate
        assert v1.name != v2.name
        assert v3.name == v1.name

    @pytest.mark.unit
    def test_record_result(self, experiment):
        """Test recording a result."""
        experiment.record_result(
            variant_name="control",
            success=True,
            latency_ms=100.0,
            accuracy=0.95,
        )

        control = next(v for v in experiment.variants if v.name == "control")
        assert control.samples == 1
        assert control.conversions == 1
        assert control.total_latency_ms == 100.0

    @pytest.mark.unit
    def test_record_failure(self, experiment):
        """Test recording a failure."""
        experiment.record_result(
            variant_name="control",
            success=False,
            latency_ms=50.0,
        )

        control = next(v for v in experiment.variants if v.name == "control")
        assert control.samples == 1
        assert control.conversions == 0
        assert control.errors == 1

    @pytest.mark.unit
    def test_get_summary(self, experiment):
        """Test getting experiment summary."""
        summary = experiment.get_summary()

        assert summary["experiment_id"] == "exp_test_123"
        assert summary["name"] == "Test Experiment"
        assert len(summary["variants"]) == 2

    @pytest.mark.unit
    def test_to_json(self, experiment):
        """Test JSON serialization."""
        import json

        json_str = experiment.to_json()
        data = json.loads(json_str)

        assert data["experiment_id"] == "exp_test_123"


class TestABTestManager:
    """Test ABTestManager class."""

    @pytest.fixture
    def manager(self):
        """Create test manager."""
        with tempfile.TemporaryDirectory() as tmpdir:
            from app.ml.ab_testing import ABTestManager
            yield ABTestManager(storage_path=Path(tmpdir))

    @pytest.mark.unit
    def test_create_experiment(self, manager):
        """Test creating an experiment."""
        experiment = manager.create_experiment(
            name="Test",
            description="Testing",
            variants=[
                {"name": "control", "config": {"backend": "deepseek"}},
                {"name": "treatment", "config": {"backend": "got_ocr"}},
            ],
        )

        assert experiment.name == "Test"
        assert len(experiment.variants) == 2

    @pytest.mark.unit
    def test_start_experiment(self, manager):
        """Test starting an experiment."""
        from app.ml.ab_testing import ExperimentStatus

        experiment = manager.create_experiment(
            name="Test",
            description="Testing",
            variants=[
                {"name": "a", "config": {}},
                {"name": "b", "config": {}},
            ],
        )

        success = manager.start_experiment(experiment.experiment_id)

        assert success == True
        assert experiment.status == ExperimentStatus.RUNNING

    @pytest.mark.unit
    def test_get_variant_running_experiment(self, manager):
        """Test getting variant from running experiment."""
        experiment = manager.create_experiment(
            name="Test",
            description="Testing",
            variants=[
                {"name": "a", "config": {}},
                {"name": "b", "config": {}},
            ],
        )
        manager.start_experiment(experiment.experiment_id)

        variant = manager.get_variant(experiment.experiment_id, "doc123")

        assert variant is not None
        assert variant.name in ["a", "b"]

    @pytest.mark.unit
    def test_get_variant_draft_experiment(self, manager):
        """Test getting variant from draft experiment returns None."""
        experiment = manager.create_experiment(
            name="Test",
            description="Testing",
            variants=[
                {"name": "a", "config": {}},
                {"name": "b", "config": {}},
            ],
        )

        # Don't start - should return None
        variant = manager.get_variant(experiment.experiment_id, "doc123")

        assert variant is None

    @pytest.mark.unit
    def test_list_experiments(self, manager):
        """Test listing experiments."""
        manager.create_experiment(
            name="Test 1",
            description="Testing",
            variants=[{"name": "a", "config": {}}, {"name": "b", "config": {}}],
        )
        manager.create_experiment(
            name="Test 2",
            description="Testing",
            variants=[{"name": "a", "config": {}}, {"name": "b", "config": {}}],
        )

        experiments = manager.list_experiments()

        assert len(experiments) == 2

    @pytest.mark.unit
    def test_conclude_experiment(self, manager):
        """Test concluding an experiment."""
        from app.ml.ab_testing import ExperimentStatus

        experiment = manager.create_experiment(
            name="Test",
            description="Testing",
            variants=[
                {"name": "control", "config": {}},
                {"name": "treatment", "config": {}},
            ],
        )
        manager.start_experiment(experiment.experiment_id)

        # Record some results
        for i in range(10):
            manager.record_result(
                experiment_id=experiment.experiment_id,
                variant_name="control",
                success=True,
                latency_ms=100.0,
            )
            manager.record_result(
                experiment_id=experiment.experiment_id,
                variant_name="treatment",
                success=i < 8,  # 80% success rate
                latency_ms=90.0,
            )

        winner = manager.conclude_experiment(experiment.experiment_id)

        assert winner is not None
        assert experiment.status == ExperimentStatus.COMPLETED


class TestConvenienceFunctions:
    """Test convenience functions."""

    @pytest.fixture
    def writable_singleton(self, tmp_path, monkeypatch):
        """Setzt das globale ABTestManager-Singleton auf einen beschreibbaren tmp-Pfad.

        Der Default-Storage-Pfad ist 'data/ab_tests'; das Container-Rootfs ist
        read-only -> ohne Override schlaegt mkdir/_save_experiment mit OSError fehl.
        """
        import app.ml.ab_testing as ab
        manager = ab.ABTestManager(storage_path=tmp_path / "ab_tests")
        monkeypatch.setattr(ab, "_ab_test_manager", manager)
        return manager

    @pytest.mark.unit
    def test_get_ab_test_manager_singleton(self, writable_singleton):
        """Test singleton access."""
        from app.ml.ab_testing import get_ab_test_manager

        manager1 = get_ab_test_manager()
        manager2 = get_ab_test_manager()

        assert manager1 is manager2
        assert manager1 is writable_singleton

    @pytest.mark.unit
    def test_create_routing_experiment(self, writable_singleton):
        """Test quick routing experiment creation."""
        from app.ml.ab_testing import create_routing_experiment, ExperimentStatus

        experiment = create_routing_experiment(
            name="DeepSeek vs GOT",
            control_backend="deepseek",
            treatment_backend="got_ocr",
        )

        assert experiment.status == ExperimentStatus.RUNNING
        assert len(experiment.variants) == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-m", "unit"])
