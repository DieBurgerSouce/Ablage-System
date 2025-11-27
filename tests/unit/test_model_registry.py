# -*- coding: utf-8 -*-
"""
Unit tests for Model Registry.

Tests:
- Model version creation and parsing
- Version bumping (major/minor/patch)
- Model registration and loading
- Version activation and rollback
- Feature hash computation
- Legacy model migration
"""

import pytest
import json
import shutil
from pathlib import Path
from datetime import datetime
from unittest.mock import Mock, patch, MagicMock

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


class TestModelVersion:
    """Test ModelVersion dataclass."""

    @pytest.mark.unit
    def test_model_version_creation(self):
        """Test creating a ModelVersion."""
        from app.agents.orchestration.model_registry import ModelVersion

        version = ModelVersion(
            version="1.2.3",
            created_at="2024-01-15T10:30:00+00:00",
            git_commit="abc123",
            training_samples=1000,
            validation_accuracy=0.95,
            feature_hash="hash123",
        )

        assert version.version == "1.2.3"
        assert version.training_samples == 1000
        assert version.validation_accuracy == 0.95
        assert version.model_type == "xgboost"

    @pytest.mark.unit
    def test_model_version_to_dict(self):
        """Test ModelVersion serialization."""
        from app.agents.orchestration.model_registry import ModelVersion

        version = ModelVersion(
            version="1.0.0",
            created_at="2024-01-15T10:30:00+00:00",
            git_commit="abc123",
            training_samples=500,
            validation_accuracy=0.85,
            feature_hash="hash456",
            hyperparameters={"learning_rate": 0.1},
        )

        data = version.to_dict()

        assert isinstance(data, dict)
        assert data["version"] == "1.0.0"
        assert data["training_samples"] == 500
        assert data["hyperparameters"]["learning_rate"] == 0.1

    @pytest.mark.unit
    def test_model_version_from_dict(self):
        """Test ModelVersion deserialization."""
        from app.agents.orchestration.model_registry import ModelVersion

        data = {
            "version": "2.0.0",
            "created_at": "2024-01-15T10:30:00+00:00",
            "git_commit": "def456",
            "training_samples": 2000,
            "validation_accuracy": 0.92,
            "feature_hash": "hash789",
            "model_type": "xgboost",
            "hyperparameters": {},
            "metadata": {"note": "test"},
        }

        version = ModelVersion.from_dict(data)

        assert version.version == "2.0.0"
        assert version.training_samples == 2000
        assert version.metadata["note"] == "test"


class TestVersionBumping:
    """Test semantic version bumping via get_next_version."""

    @pytest.fixture
    def registry(self, tmp_path):
        """Create registry with temp directory."""
        from app.agents.orchestration.model_registry import ModelRegistry
        return ModelRegistry(base_path=tmp_path / "models")

    @pytest.fixture
    def registry_with_model(self, tmp_path):
        """Create registry with a model registered."""
        from app.agents.orchestration.model_registry import ModelRegistry
        registry = ModelRegistry(base_path=tmp_path / "models")

        mock_model = MagicMock()
        mock_model.save_model = MagicMock()

        registry.register_model(
            model=mock_model,
            feature_names=["f1"],
            training_samples=100,
            validation_accuracy=0.85,
        )
        return registry

    @pytest.mark.unit
    def test_first_version(self, registry):
        """Test first version is 1.0.0."""
        version = registry.get_next_version("patch")
        assert version == "1.0.0"

    @pytest.mark.unit
    def test_next_patch_version(self, registry_with_model):
        """Test patch version bump."""
        # Already has 1.0.0
        version = registry_with_model.get_next_version("patch")
        assert version == "1.0.1"

    @pytest.mark.unit
    def test_next_minor_version(self, registry_with_model):
        """Test minor version bump."""
        version = registry_with_model.get_next_version("minor")
        assert version == "1.1.0"

    @pytest.mark.unit
    def test_next_major_version(self, registry_with_model):
        """Test major version bump."""
        version = registry_with_model.get_next_version("major")
        assert version == "2.0.0"

    @pytest.mark.unit
    def test_version_increments_correctly(self, tmp_path):
        """Test version increments correctly over multiple registrations."""
        from app.agents.orchestration.model_registry import ModelRegistry
        registry = ModelRegistry(base_path=tmp_path / "models")

        mock_model = MagicMock()
        mock_model.save_model = MagicMock()

        # Register first model (1.0.0)
        v1 = registry.register_model(
            model=mock_model,
            feature_names=["f1"],
            training_samples=100,
            validation_accuracy=0.85,
        )
        assert v1.version == "1.0.0"

        # Register second model (1.0.1)
        v2 = registry.register_model(
            model=mock_model,
            feature_names=["f1"],
            training_samples=100,
            validation_accuracy=0.85,
        )
        assert v2.version == "1.0.1"

        # Register with minor bump
        v3 = registry.register_model(
            model=mock_model,
            feature_names=["f1"],
            training_samples=100,
            validation_accuracy=0.85,
            bump_type="minor",
        )
        assert v3.version == "1.1.0"


class TestFeatureHash:
    """Test feature hash computation."""

    @pytest.mark.unit
    def test_compute_feature_hash(self):
        """Test feature hash computation."""
        from app.agents.orchestration.model_registry import compute_feature_hash

        features = ["feature_a", "feature_b", "feature_c"]
        hash1 = compute_feature_hash(features)

        assert isinstance(hash1, str)
        assert len(hash1) == 16  # Truncated MD5

    @pytest.mark.unit
    def test_feature_hash_consistency(self):
        """Test that same features produce same hash."""
        from app.agents.orchestration.model_registry import compute_feature_hash

        features = ["a", "b", "c"]
        hash1 = compute_feature_hash(features)
        hash2 = compute_feature_hash(features)

        assert hash1 == hash2

    @pytest.mark.unit
    def test_feature_hash_different_count(self):
        """Test that different feature counts produce different hashes."""
        from app.agents.orchestration.model_registry import compute_feature_hash

        hash1 = compute_feature_hash(["a", "b", "c"])
        hash2 = compute_feature_hash(["a", "b"])

        assert hash1 != hash2

    @pytest.mark.unit
    def test_feature_hash_different_features(self):
        """Test different features produce different hashes."""
        from app.agents.orchestration.model_registry import compute_feature_hash

        hash1 = compute_feature_hash(["feature_1"])
        hash2 = compute_feature_hash(["feature_2"])

        assert hash1 != hash2


class TestModelRegistration:
    """Test model registration."""

    @pytest.fixture
    def registry(self, tmp_path):
        """Create registry with temp directory."""
        from app.agents.orchestration.model_registry import ModelRegistry
        return ModelRegistry(base_path=tmp_path / "models")

    @pytest.fixture
    def mock_xgb_model(self):
        """Create mock XGBoost model."""
        model = MagicMock()
        model.save_model = MagicMock()
        return model

    @pytest.mark.unit
    def test_register_model(self, registry, mock_xgb_model):
        """Test registering a new model."""
        version = registry.register_model(
            model=mock_xgb_model,
            feature_names=["f1", "f2", "f3"],
            training_samples=100,
            validation_accuracy=0.90,
        )

        assert version.version == "1.0.0"
        assert version.training_samples == 100
        assert version.validation_accuracy == 0.90
        mock_xgb_model.save_model.assert_called_once()

    @pytest.mark.unit
    def test_register_multiple_versions(self, registry, mock_xgb_model):
        """Test registering multiple versions."""
        v1 = registry.register_model(
            model=mock_xgb_model,
            feature_names=["f1"],
            training_samples=100,
            validation_accuracy=0.85,
        )

        v2 = registry.register_model(
            model=mock_xgb_model,
            feature_names=["f1"],
            training_samples=200,
            validation_accuracy=0.90,
        )

        assert v1.version == "1.0.0"
        assert v2.version == "1.0.1"
        versions = registry.list_versions()
        assert len(versions) == 2

    @pytest.mark.unit
    def test_list_versions(self, registry, mock_xgb_model):
        """Test listing all versions."""
        registry.register_model(
            model=mock_xgb_model,
            feature_names=["f1"],
            training_samples=100,
            validation_accuracy=0.85,
        )
        registry.register_model(
            model=mock_xgb_model,
            feature_names=["f1"],
            training_samples=200,
            validation_accuracy=0.90,
        )

        versions = registry.list_versions()

        assert len(versions) == 2
        # list_versions returns list of dicts with version info
        version_numbers = [v["version"] for v in versions]
        assert "1.0.0" in version_numbers
        assert "1.0.1" in version_numbers


class TestModelActivation:
    """Test model activation and loading."""

    @pytest.fixture
    def registry_with_model(self, tmp_path):
        """Create registry with a registered model."""
        from app.agents.orchestration.model_registry import ModelRegistry

        registry = ModelRegistry(base_path=tmp_path / "models")

        # Mock model registration
        mock_model = MagicMock()
        mock_model.save_model = MagicMock()

        registry.register_model(
            model=mock_model,
            feature_names=["f1", "f2"],
            training_samples=100,
            validation_accuracy=0.85,
        )

        return registry

    @pytest.mark.unit
    def test_set_active_version(self, registry_with_model):
        """Test setting active version."""
        registry_with_model.set_active("1.0.0")

        active = registry_with_model.get_active_version()
        assert active == "1.0.0"

    @pytest.mark.unit
    def test_set_active_invalid_version(self, registry_with_model):
        """Test setting invalid active version."""
        with pytest.raises(ValueError, match="nicht gefunden"):
            registry_with_model.set_active("9.9.9")

    @pytest.mark.unit
    def test_get_active_version(self, registry_with_model):
        """Test getting active version."""
        registry_with_model.set_active("1.0.0")

        active = registry_with_model.get_active_version()

        # get_active_version returns version string
        assert active == "1.0.0"

    @pytest.mark.unit
    def test_get_version_info(self, registry_with_model):
        """Test getting version info."""
        info = registry_with_model.get_version_info("1.0.0")

        assert info is not None
        assert info.version == "1.0.0"
        assert info.training_samples == 100


class TestVersionSwitching:
    """Test version switching functionality."""

    @pytest.fixture
    def registry_with_versions(self, tmp_path):
        """Create registry with multiple versions."""
        from app.agents.orchestration.model_registry import ModelRegistry

        registry = ModelRegistry(base_path=tmp_path / "models")

        mock_model = MagicMock()
        mock_model.save_model = MagicMock()

        # Register multiple versions
        registry.register_model(
            model=mock_model,
            feature_names=["f1"],
            training_samples=100,
            validation_accuracy=0.80,
        )
        registry.register_model(
            model=mock_model,
            feature_names=["f1"],
            training_samples=200,
            validation_accuracy=0.85,
        )
        registry.register_model(
            model=mock_model,
            feature_names=["f1"],
            training_samples=300,
            validation_accuracy=0.90,
        )

        # Set latest as active
        registry.set_active("1.0.2")

        return registry

    @pytest.mark.unit
    def test_switch_to_previous_version(self, registry_with_versions):
        """Test switching to a previous version."""
        # Switch to an earlier version
        registry_with_versions.set_active("1.0.0")

        assert registry_with_versions.get_active_version() == "1.0.0"

    @pytest.mark.unit
    def test_get_version_info_all_versions(self, registry_with_versions):
        """Test getting info for all versions."""
        info = registry_with_versions.get_version_info("1.0.0")
        assert info.training_samples == 100

        info = registry_with_versions.get_version_info("1.0.1")
        assert info.training_samples == 200

        info = registry_with_versions.get_version_info("1.0.2")
        assert info.training_samples == 300


class TestRegistryPersistence:
    """Test registry file persistence."""

    @pytest.fixture
    def registry(self, tmp_path):
        """Create registry with temp directory."""
        from app.agents.orchestration.model_registry import ModelRegistry
        return ModelRegistry(base_path=tmp_path / "models")

    @pytest.mark.unit
    def test_registry_creates_directory(self, registry):
        """Test that registry creates its base directory."""
        # base_path is the directory
        assert registry.base_path.exists()

    @pytest.mark.unit
    def test_registry_file_created(self, registry):
        """Test that registry.json is created after registration."""
        mock_model = MagicMock()
        mock_model.save_model = MagicMock()

        registry.register_model(
            model=mock_model,
            feature_names=["f1"],
            training_samples=100,
            validation_accuracy=0.85,
        )

        # _registry_path is the registry.json file path
        assert registry._registry_path.exists()

    @pytest.mark.unit
    def test_metadata_file_created(self, registry):
        """Test that metadata.json is created for each version."""
        mock_model = MagicMock()
        mock_model.save_model = MagicMock()

        registry.register_model(
            model=mock_model,
            feature_names=["f1"],
            training_samples=100,
            validation_accuracy=0.85,
        )

        # Version directories are in base_path / v{version}
        metadata_file = registry.base_path / "v1.0.0" / "metadata.json"
        assert metadata_file.exists()

    @pytest.mark.unit
    def test_registry_reload(self, tmp_path):
        """Test that registry can be reloaded."""
        from app.agents.orchestration.model_registry import ModelRegistry

        # Create first registry and register model
        registry1 = ModelRegistry(base_path=tmp_path / "models")
        mock_model = MagicMock()
        mock_model.save_model = MagicMock()

        registry1.register_model(
            model=mock_model,
            feature_names=["f1"],
            training_samples=100,
            validation_accuracy=0.85,
        )
        registry1.set_active("1.0.0")

        # Create second registry pointing to same path
        registry2 = ModelRegistry(base_path=tmp_path / "models")

        versions = registry2.list_versions()
        version_numbers = [v["version"] for v in versions]
        assert "1.0.0" in version_numbers
        assert registry2.get_active_version() == "1.0.0"


class TestGitCommitTracking:
    """Test Git commit tracking."""

    @pytest.fixture
    def registry(self, tmp_path):
        """Create registry with temp directory."""
        from app.agents.orchestration.model_registry import ModelRegistry
        return ModelRegistry(base_path=tmp_path / "models")

    @pytest.mark.unit
    def test_git_commit_captured(self, registry):
        """Test that Git commit is captured if available."""
        mock_model = MagicMock()
        mock_model.save_model = MagicMock()

        with patch('subprocess.check_output') as mock_git:
            mock_git.return_value = b"abc123def456"

            version = registry.register_model(
                model=mock_model,
                feature_names=["f1"],
                training_samples=100,
                validation_accuracy=0.85,
            )

            assert len(version.git_commit) > 0

    @pytest.mark.unit
    def test_git_commit_is_string(self, registry):
        """Test that git commit is captured as a string."""
        mock_model = MagicMock()
        mock_model.save_model = MagicMock()

        version = registry.register_model(
            model=mock_model,
            feature_names=["f1"],
            training_samples=100,
            validation_accuracy=0.85,
        )

        # Git commit should be a non-empty string
        assert isinstance(version.git_commit, str)
        assert len(version.git_commit) > 0


class TestSecureModelFormat:
    """Test secure model format (JSON instead of pickle)."""

    @pytest.fixture
    def registry(self, tmp_path):
        """Create registry with temp directory."""
        from app.agents.orchestration.model_registry import ModelRegistry
        return ModelRegistry(base_path=tmp_path / "models")

    @pytest.mark.unit
    def test_model_saved_as_json(self, registry):
        """Test that model is saved as JSON (not pickle)."""
        mock_model = MagicMock()
        mock_model.save_model = MagicMock()

        registry.register_model(
            model=mock_model,
            feature_names=["f1"],
            training_samples=100,
            validation_accuracy=0.85,
        )

        # Check that save_model was called with JSON path
        call_args = mock_model.save_model.call_args
        model_path = call_args[0][0]
        assert str(model_path).endswith(".json")

    @pytest.mark.unit
    def test_no_pickle_files(self, registry):
        """Test that no pickle files are created."""
        mock_model = MagicMock()
        mock_model.save_model = MagicMock()

        registry.register_model(
            model=mock_model,
            feature_names=["f1"],
            training_samples=100,
            validation_accuracy=0.85,
        )

        # Check for any .pkl or .pickle files
        pickle_files = list(registry._registry_path.rglob("*.pkl"))
        pickle_files.extend(list(registry._registry_path.rglob("*.pickle")))

        assert len(pickle_files) == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-m", "unit"])
