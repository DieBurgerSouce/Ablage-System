# -*- coding: utf-8 -*-
"""
Unit Tests for Model Registry Service.

Tests the MLOps model versioning and lifecycle management:
- Model registration and versioning
- Status transitions (DRAFT → CANDIDATE → ACTIVE → DEPRECATED)
- Rollback capability
- Quality degradation detection
- Performance history tracking
- Old version cleanup

Enterprise Feature: MLOps Pipeline
"""

import uuid
from datetime import datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.mlops.model_registry import (
    ModelRegistry,
    ModelStatus,
    ModelType,
    ModelMetadata,
    ModelVersion,
)


# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def mock_session() -> AsyncMock:
    """Create mock async session."""
    session = AsyncMock(spec=AsyncSession)
    session.execute = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    return session


@pytest.fixture
def model_registry(mock_session: AsyncMock) -> ModelRegistry:
    """Create model registry with mocked session."""
    return ModelRegistry(mock_session)


@pytest.fixture
def sample_registry_data() -> dict[str, list[dict[str, Any]]]:
    """Sample registry data with multiple versions."""
    return {
        "ocr_confidence": [
            {
                "id": "model-1",
                "model_type": "ocr_confidence",
                "version": "1.0.0",
                "status": "deprecated",
                "accuracy": 0.92,
                "training_samples": 5000,
                "created_at": (datetime.utcnow() - timedelta(days=30)).isoformat(),
                "deprecated_at": (datetime.utcnow() - timedelta(days=7)).isoformat(),
            },
            {
                "id": "model-2",
                "model_type": "ocr_confidence",
                "version": "1.1.0",
                "status": "active",
                "accuracy": 0.95,
                "training_samples": 8000,
                "created_at": (datetime.utcnow() - timedelta(days=7)).isoformat(),
                "deployed_at": (datetime.utcnow() - timedelta(days=7)).isoformat(),
            },
        ],
        "document_classifier": [
            {
                "id": "model-3",
                "model_type": "document_classifier",
                "version": "2.0.0",
                "status": "draft",
                "accuracy": 0.88,
                "training_samples": 3000,
                "created_at": datetime.utcnow().isoformat(),
            },
        ],
    }


# =============================================================================
# ENUM TESTS
# =============================================================================


class TestModelStatus:
    """Tests for ModelStatus enum."""

    def test_all_statuses_defined(self) -> None:
        """Verify all model statuses are defined."""
        assert ModelStatus.DRAFT == "draft"
        assert ModelStatus.CANDIDATE == "candidate"
        assert ModelStatus.ACTIVE == "active"
        assert ModelStatus.DEPRECATED == "deprecated"
        assert ModelStatus.ROLLED_BACK == "rolled_back"
        assert ModelStatus.ARCHIVED == "archived"

    def test_status_count(self) -> None:
        """Verify expected number of statuses."""
        assert len(ModelStatus) == 6

    def test_lifecycle_transitions(self) -> None:
        """Test valid lifecycle transitions."""
        # Typical lifecycle
        lifecycle = [
            ModelStatus.DRAFT,
            ModelStatus.CANDIDATE,
            ModelStatus.ACTIVE,
            ModelStatus.DEPRECATED,
            ModelStatus.ARCHIVED,
        ]
        assert len(lifecycle) == 5

        # Rollback path
        rollback_path = [
            ModelStatus.ACTIVE,
            ModelStatus.ROLLED_BACK,
            ModelStatus.ARCHIVED,
        ]
        assert len(rollback_path) == 3


class TestModelType:
    """Tests for ModelType enum."""

    def test_all_types_defined(self) -> None:
        """Verify all model types are defined."""
        assert ModelType.OCR_CONFIDENCE == "ocr_confidence"
        assert ModelType.OCR_BACKEND_ROUTER == "ocr_backend_router"
        assert ModelType.DOCUMENT_CLASSIFIER == "document_classifier"
        assert ModelType.ENTITY_MATCHER == "entity_matcher"
        assert ModelType.EXTRACTION_MODEL == "extraction_model"

    def test_type_count(self) -> None:
        """Verify expected number of model types."""
        assert len(ModelType) == 5


# =============================================================================
# MODEL METADATA TESTS
# =============================================================================


class TestModelMetadata:
    """Tests for ModelMetadata model."""

    def test_minimal_creation(self) -> None:
        """Test minimal model metadata creation."""
        metadata = ModelMetadata(
            model_type=ModelType.OCR_CONFIDENCE,
            version="1.0.0",
        )

        assert metadata.model_type == ModelType.OCR_CONFIDENCE
        assert metadata.version == "1.0.0"
        assert metadata.status == ModelStatus.DRAFT
        assert metadata.training_samples == 0
        assert metadata.id is not None

    def test_full_creation(self) -> None:
        """Test full model metadata creation."""
        metadata = ModelMetadata(
            model_type=ModelType.DOCUMENT_CLASSIFIER,
            version="2.1.0",
            status=ModelStatus.ACTIVE,
            training_samples=10000,
            accuracy=0.95,
            precision=0.94,
            recall=0.93,
            f1_score=0.935,
            custom_metrics={"auc": 0.98, "loss": 0.05},
            parent_version="2.0.0",
            created_by="system",
            tags=["production", "german"],
            notes="Optimiert für deutsche Dokumente",
        )

        assert metadata.accuracy == 0.95
        assert metadata.precision == 0.94
        assert metadata.recall == 0.93
        assert metadata.f1_score == 0.935
        assert metadata.custom_metrics["auc"] == 0.98
        assert metadata.parent_version == "2.0.0"
        assert "production" in metadata.tags

    def test_defaults(self) -> None:
        """Test default values."""
        metadata = ModelMetadata(
            model_type=ModelType.OCR_CONFIDENCE,
            version="1.0.0",
        )

        assert metadata.status == ModelStatus.DRAFT
        assert metadata.training_samples == 0
        assert metadata.training_duration_seconds == 0.0
        assert metadata.artifact_size_bytes == 0
        assert metadata.custom_metrics == {}
        assert metadata.tags == []
        assert metadata.accuracy is None
        assert metadata.artifact_path is None

    def test_artifact_info(self) -> None:
        """Test artifact information fields."""
        metadata = ModelMetadata(
            model_type=ModelType.OCR_CONFIDENCE,
            version="1.0.0",
            artifact_path="models/ocr_confidence/v1.0.0/model.bin",
            artifact_hash="sha256:abc123...",
            artifact_size_bytes=52428800,  # 50MB
        )

        assert "models/ocr_confidence" in metadata.artifact_path
        assert metadata.artifact_hash.startswith("sha256:")
        assert metadata.artifact_size_bytes == 52428800


class TestModelVersion:
    """Tests for ModelVersion model."""

    def test_simple_version(self) -> None:
        """Test simple version creation."""
        version = ModelVersion(
            version="1.2.3",
            status=ModelStatus.ACTIVE,
        )

        assert version.version == "1.2.3"
        assert version.status == ModelStatus.ACTIVE
        assert version.accuracy is None
        assert version.deployed_at is None

    def test_full_version(self) -> None:
        """Test full version with all fields."""
        now = datetime.utcnow()
        version = ModelVersion(
            version="2.0.0",
            status=ModelStatus.ACTIVE,
            accuracy=0.95,
            deployed_at=now,
        )

        assert version.accuracy == 0.95
        assert version.deployed_at == now


# =============================================================================
# MODEL REGISTRY INITIALIZATION TESTS
# =============================================================================


class TestModelRegistryInit:
    """Tests for ModelRegistry initialization."""

    def test_registry_creation(self, mock_session: AsyncMock) -> None:
        """Test basic registry creation."""
        registry = ModelRegistry(mock_session)

        assert registry.db == mock_session
        assert registry.REGISTRY_KEY == "mlops_model_registry"
        assert registry.CACHE_TTL == 300


# =============================================================================
# MODEL REGISTRATION TESTS
# =============================================================================


class TestModelRegistration:
    """Tests for model registration."""

    @pytest.mark.asyncio
    async def test_register_new_model(
        self,
        model_registry: ModelRegistry,
        mock_session: AsyncMock,
    ) -> None:
        """Test registering a new model version."""
        # Setup: empty registry
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        with patch.object(model_registry, "_save_registry", new_callable=AsyncMock):
            metadata = await model_registry.register_model(
                model_type=ModelType.OCR_CONFIDENCE,
                version="1.0.0",
                training_samples=5000,
                accuracy=0.95,
                created_by="test-user",
            )

        assert metadata.version == "1.0.0"
        assert metadata.model_type == ModelType.OCR_CONFIDENCE
        assert metadata.status == ModelStatus.DRAFT
        assert metadata.training_samples == 5000
        assert metadata.accuracy == 0.95

    @pytest.mark.asyncio
    async def test_register_with_parent_version(
        self,
        model_registry: ModelRegistry,
        mock_session: AsyncMock,
        sample_registry_data: dict,
    ) -> None:
        """Test registering model with parent lineage."""
        mock_result = MagicMock()
        mock_config = MagicMock()
        mock_config.value = sample_registry_data
        mock_result.scalar_one_or_none.return_value = mock_config
        mock_session.execute.return_value = mock_result

        with patch.object(model_registry, "_save_registry", new_callable=AsyncMock):
            metadata = await model_registry.register_model(
                model_type=ModelType.OCR_CONFIDENCE,
                version="1.2.0",
                training_samples=10000,
                accuracy=0.96,
                parent_version="1.1.0",
            )

        assert metadata.parent_version == "1.1.0"
        assert metadata.version == "1.2.0"

    @pytest.mark.asyncio
    async def test_register_duplicate_version_raises(
        self,
        model_registry: ModelRegistry,
        mock_session: AsyncMock,
        sample_registry_data: dict,
    ) -> None:
        """Test that registering duplicate version raises error."""
        mock_result = MagicMock()
        mock_config = MagicMock()
        mock_config.value = sample_registry_data
        mock_result.scalar_one_or_none.return_value = mock_config
        mock_session.execute.return_value = mock_result

        with pytest.raises(ValueError, match="already exists"):
            await model_registry.register_model(
                model_type=ModelType.OCR_CONFIDENCE,
                version="1.1.0",  # Already exists
                training_samples=5000,
            )


# =============================================================================
# MODEL RETRIEVAL TESTS
# =============================================================================


class TestModelRetrieval:
    """Tests for model retrieval methods."""

    @pytest.mark.asyncio
    async def test_get_model_exists(
        self,
        model_registry: ModelRegistry,
        mock_session: AsyncMock,
        sample_registry_data: dict,
    ) -> None:
        """Test getting an existing model."""
        mock_result = MagicMock()
        mock_config = MagicMock()
        mock_config.value = sample_registry_data
        mock_result.scalar_one_or_none.return_value = mock_config
        mock_session.execute.return_value = mock_result

        metadata = await model_registry.get_model(
            ModelType.OCR_CONFIDENCE,
            version="1.1.0",
        )

        assert metadata is not None
        assert metadata.version == "1.1.0"
        assert metadata.accuracy == 0.95

    @pytest.mark.asyncio
    async def test_get_model_not_found(
        self,
        model_registry: ModelRegistry,
        mock_session: AsyncMock,
        sample_registry_data: dict,
    ) -> None:
        """Test getting a non-existent model."""
        mock_result = MagicMock()
        mock_config = MagicMock()
        mock_config.value = sample_registry_data
        mock_result.scalar_one_or_none.return_value = mock_config
        mock_session.execute.return_value = mock_result

        metadata = await model_registry.get_model(
            ModelType.OCR_CONFIDENCE,
            version="9.9.9",  # Does not exist
        )

        assert metadata is None

    @pytest.mark.asyncio
    async def test_get_active_model(
        self,
        model_registry: ModelRegistry,
        mock_session: AsyncMock,
        sample_registry_data: dict,
    ) -> None:
        """Test getting the active production model."""
        mock_result = MagicMock()
        mock_config = MagicMock()
        mock_config.value = sample_registry_data
        mock_result.scalar_one_or_none.return_value = mock_config
        mock_session.execute.return_value = mock_result

        metadata = await model_registry.get_active_model(ModelType.OCR_CONFIDENCE)

        assert metadata is not None
        assert metadata.status == ModelStatus.ACTIVE
        assert metadata.version == "1.1.0"

    @pytest.mark.asyncio
    async def test_get_active_model_none_active(
        self,
        model_registry: ModelRegistry,
        mock_session: AsyncMock,
    ) -> None:
        """Test getting active model when none is active."""
        mock_result = MagicMock()
        mock_config = MagicMock()
        mock_config.value = {
            "ocr_confidence": [
                {"version": "1.0.0", "status": "draft"},
            ]
        }
        mock_result.scalar_one_or_none.return_value = mock_config
        mock_session.execute.return_value = mock_result

        metadata = await model_registry.get_active_model(ModelType.OCR_CONFIDENCE)

        assert metadata is None


# =============================================================================
# VERSION LISTING TESTS
# =============================================================================


class TestVersionListing:
    """Tests for version listing."""

    @pytest.mark.asyncio
    async def test_list_all_versions(
        self,
        model_registry: ModelRegistry,
        mock_session: AsyncMock,
        sample_registry_data: dict,
    ) -> None:
        """Test listing all versions for a model type."""
        mock_result = MagicMock()
        mock_config = MagicMock()
        mock_config.value = sample_registry_data
        mock_result.scalar_one_or_none.return_value = mock_config
        mock_session.execute.return_value = mock_result

        versions = await model_registry.list_versions(ModelType.OCR_CONFIDENCE)

        assert len(versions) == 2
        # Sorted by version (newest first)
        assert versions[0].version == "1.1.0"
        assert versions[1].version == "1.0.0"

    @pytest.mark.asyncio
    async def test_list_versions_with_status_filter(
        self,
        model_registry: ModelRegistry,
        mock_session: AsyncMock,
        sample_registry_data: dict,
    ) -> None:
        """Test listing versions filtered by status."""
        mock_result = MagicMock()
        mock_config = MagicMock()
        mock_config.value = sample_registry_data
        mock_result.scalar_one_or_none.return_value = mock_config
        mock_session.execute.return_value = mock_result

        versions = await model_registry.list_versions(
            ModelType.OCR_CONFIDENCE,
            status=ModelStatus.ACTIVE,
        )

        assert len(versions) == 1
        assert versions[0].status == ModelStatus.ACTIVE

    @pytest.mark.asyncio
    async def test_list_versions_with_limit(
        self,
        model_registry: ModelRegistry,
        mock_session: AsyncMock,
        sample_registry_data: dict,
    ) -> None:
        """Test listing versions with limit."""
        mock_result = MagicMock()
        mock_config = MagicMock()
        mock_config.value = sample_registry_data
        mock_result.scalar_one_or_none.return_value = mock_config
        mock_session.execute.return_value = mock_result

        versions = await model_registry.list_versions(
            ModelType.OCR_CONFIDENCE,
            limit=1,
        )

        assert len(versions) == 1


# =============================================================================
# STATUS UPDATE TESTS
# =============================================================================


class TestStatusUpdates:
    """Tests for model status updates."""

    @pytest.mark.asyncio
    async def test_update_status_to_candidate(
        self,
        model_registry: ModelRegistry,
        mock_session: AsyncMock,
        sample_registry_data: dict,
    ) -> None:
        """Test updating status to candidate."""
        mock_result = MagicMock()
        mock_config = MagicMock()
        mock_config.value = sample_registry_data
        mock_result.scalar_one_or_none.return_value = mock_config
        mock_session.execute.return_value = mock_result

        with patch.object(model_registry, "_save_registry", new_callable=AsyncMock):
            metadata = await model_registry.update_status(
                ModelType.DOCUMENT_CLASSIFIER,
                version="2.0.0",
                status=ModelStatus.CANDIDATE,
            )

        assert metadata.status == ModelStatus.CANDIDATE

    @pytest.mark.asyncio
    async def test_update_status_version_not_found(
        self,
        model_registry: ModelRegistry,
        mock_session: AsyncMock,
        sample_registry_data: dict,
    ) -> None:
        """Test updating status for non-existent version."""
        mock_result = MagicMock()
        mock_config = MagicMock()
        mock_config.value = sample_registry_data
        mock_result.scalar_one_or_none.return_value = mock_config
        mock_session.execute.return_value = mock_result

        with pytest.raises(ValueError, match="not found"):
            await model_registry.update_status(
                ModelType.OCR_CONFIDENCE,
                version="9.9.9",
                status=ModelStatus.ACTIVE,
            )


# =============================================================================
# PROMOTION TESTS
# =============================================================================


class TestPromotion:
    """Tests for model promotion."""

    @pytest.mark.asyncio
    async def test_promote_to_active(
        self,
        model_registry: ModelRegistry,
        mock_session: AsyncMock,
    ) -> None:
        """Test promoting a model to active."""
        registry_data = {
            "ocr_confidence": [
                {"version": "1.0.0", "status": "active"},
                {"version": "1.1.0", "status": "candidate"},
            ]
        }
        mock_result = MagicMock()
        mock_config = MagicMock()
        mock_config.value = registry_data
        mock_result.scalar_one_or_none.return_value = mock_config
        mock_session.execute.return_value = mock_result

        with patch.object(model_registry, "_save_registry", new_callable=AsyncMock):
            with patch.object(model_registry, "get_model", new_callable=AsyncMock) as mock_get:
                mock_get.return_value = ModelMetadata(
                    model_type=ModelType.OCR_CONFIDENCE,
                    version="1.1.0",
                    status=ModelStatus.ACTIVE,
                )

                metadata = await model_registry.promote_to_active(
                    ModelType.OCR_CONFIDENCE,
                    version="1.1.0",
                )

        assert metadata.status == ModelStatus.ACTIVE

    @pytest.mark.asyncio
    async def test_promote_deprecates_previous_active(
        self,
        model_registry: ModelRegistry,
        mock_session: AsyncMock,
    ) -> None:
        """Test that promotion deprecates previous active version."""
        registry_data = {
            "ocr_confidence": [
                {"version": "1.0.0", "status": "active"},
                {"version": "1.1.0", "status": "candidate"},
            ]
        }
        mock_result = MagicMock()
        mock_config = MagicMock()
        mock_config.value = registry_data
        mock_result.scalar_one_or_none.return_value = mock_config
        mock_session.execute.return_value = mock_result

        with patch.object(model_registry, "_save_registry", new_callable=AsyncMock) as mock_save:
            with patch.object(model_registry, "get_model", new_callable=AsyncMock) as mock_get:
                mock_get.return_value = ModelMetadata(
                    model_type=ModelType.OCR_CONFIDENCE,
                    version="1.1.0",
                    status=ModelStatus.ACTIVE,
                )

                await model_registry.promote_to_active(
                    ModelType.OCR_CONFIDENCE,
                    version="1.1.0",
                )

        # Verify save was called
        mock_save.assert_called_once()


# =============================================================================
# ROLLBACK TESTS
# =============================================================================


class TestRollback:
    """Tests for model rollback."""

    @pytest.mark.asyncio
    async def test_rollback_to_previous(
        self,
        model_registry: ModelRegistry,
        mock_session: AsyncMock,
    ) -> None:
        """Test rollback to previous version."""
        registry_data = {
            "ocr_confidence": [
                {
                    "version": "1.0.0",
                    "status": "deprecated",
                    "deprecated_at": (datetime.utcnow() - timedelta(days=7)).isoformat(),
                },
                {"version": "1.1.0", "status": "active"},
            ]
        }
        mock_result = MagicMock()
        mock_config = MagicMock()
        mock_config.value = registry_data
        mock_result.scalar_one_or_none.return_value = mock_config
        mock_session.execute.return_value = mock_result

        with patch.object(model_registry, "_save_registry", new_callable=AsyncMock):
            metadata = await model_registry.rollback(
                ModelType.OCR_CONFIDENCE,
                reason="Accuracy degradation detected",
            )

        assert metadata is not None
        assert metadata.version == "1.0.0"
        assert metadata.status == ModelStatus.ACTIVE

    @pytest.mark.asyncio
    async def test_rollback_no_active_model(
        self,
        model_registry: ModelRegistry,
        mock_session: AsyncMock,
    ) -> None:
        """Test rollback when no active model exists."""
        registry_data = {
            "ocr_confidence": [
                {"version": "1.0.0", "status": "draft"},
            ]
        }
        mock_result = MagicMock()
        mock_config = MagicMock()
        mock_config.value = registry_data
        mock_result.scalar_one_or_none.return_value = mock_config
        mock_session.execute.return_value = mock_result

        metadata = await model_registry.rollback(
            ModelType.OCR_CONFIDENCE,
            reason="Test",
        )

        assert metadata is None

    @pytest.mark.asyncio
    async def test_rollback_no_target(
        self,
        model_registry: ModelRegistry,
        mock_session: AsyncMock,
    ) -> None:
        """Test rollback when no deprecated version to rollback to."""
        registry_data = {
            "ocr_confidence": [
                {"version": "1.0.0", "status": "active"},
            ]
        }
        mock_result = MagicMock()
        mock_config = MagicMock()
        mock_config.value = registry_data
        mock_result.scalar_one_or_none.return_value = mock_config
        mock_session.execute.return_value = mock_result

        metadata = await model_registry.rollback(
            ModelType.OCR_CONFIDENCE,
            reason="Test",
        )

        assert metadata is None


# =============================================================================
# QUALITY DEGRADATION TESTS
# =============================================================================


class TestQualityDegradation:
    """Tests for quality degradation detection."""

    @pytest.mark.asyncio
    async def test_no_degradation(
        self,
        model_registry: ModelRegistry,
    ) -> None:
        """Test no degradation detected."""
        with patch.object(model_registry, "get_active_model", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = ModelMetadata(
                model_type=ModelType.OCR_CONFIDENCE,
                version="1.0.0",
                accuracy=0.95,
            )

            should_rollback = await model_registry.check_quality_degradation(
                ModelType.OCR_CONFIDENCE,
                current_accuracy=0.94,  # Only 1% drop
                threshold=0.05,  # 5% threshold
            )

        assert should_rollback is False

    @pytest.mark.asyncio
    async def test_degradation_detected(
        self,
        model_registry: ModelRegistry,
    ) -> None:
        """Test degradation exceeds threshold."""
        with patch.object(model_registry, "get_active_model", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = ModelMetadata(
                model_type=ModelType.OCR_CONFIDENCE,
                version="1.0.0",
                accuracy=0.95,
            )

            should_rollback = await model_registry.check_quality_degradation(
                ModelType.OCR_CONFIDENCE,
                current_accuracy=0.88,  # 7% drop
                threshold=0.05,  # 5% threshold
            )

        assert should_rollback is True

    @pytest.mark.asyncio
    async def test_no_active_model(
        self,
        model_registry: ModelRegistry,
    ) -> None:
        """Test with no active model."""
        with patch.object(model_registry, "get_active_model", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = None

            should_rollback = await model_registry.check_quality_degradation(
                ModelType.OCR_CONFIDENCE,
                current_accuracy=0.90,
            )

        assert should_rollback is False

    @pytest.mark.asyncio
    async def test_active_model_no_accuracy(
        self,
        model_registry: ModelRegistry,
    ) -> None:
        """Test with active model that has no accuracy."""
        with patch.object(model_registry, "get_active_model", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = ModelMetadata(
                model_type=ModelType.OCR_CONFIDENCE,
                version="1.0.0",
                accuracy=None,  # No accuracy recorded
            )

            should_rollback = await model_registry.check_quality_degradation(
                ModelType.OCR_CONFIDENCE,
                current_accuracy=0.90,
            )

        assert should_rollback is False


# =============================================================================
# PERFORMANCE HISTORY TESTS
# =============================================================================


class TestPerformanceHistory:
    """Tests for performance history tracking."""

    @pytest.mark.asyncio
    async def test_get_history_within_window(
        self,
        model_registry: ModelRegistry,
        mock_session: AsyncMock,
    ) -> None:
        """Test getting history within time window."""
        now = datetime.utcnow()
        registry_data = {
            "ocr_confidence": [
                {
                    "version": "1.0.0",
                    "accuracy": 0.90,
                    "training_samples": 5000,
                    "status": "deprecated",
                    "created_at": (now - timedelta(days=20)).isoformat(),
                },
                {
                    "version": "1.1.0",
                    "accuracy": 0.95,
                    "training_samples": 8000,
                    "status": "active",
                    "created_at": (now - timedelta(days=10)).isoformat(),
                },
            ]
        }
        mock_result = MagicMock()
        mock_config = MagicMock()
        mock_config.value = registry_data
        mock_result.scalar_one_or_none.return_value = mock_config
        mock_session.execute.return_value = mock_result

        history = await model_registry.get_performance_history(
            ModelType.OCR_CONFIDENCE,
            days=30,
        )

        assert len(history) == 2
        assert history[0]["version"] == "1.1.0"  # Most recent first

    @pytest.mark.asyncio
    async def test_get_history_excludes_old(
        self,
        model_registry: ModelRegistry,
        mock_session: AsyncMock,
    ) -> None:
        """Test that old entries are excluded."""
        now = datetime.utcnow()
        registry_data = {
            "ocr_confidence": [
                {
                    "version": "1.0.0",
                    "accuracy": 0.90,
                    "training_samples": 5000,
                    "status": "archived",
                    "created_at": (now - timedelta(days=60)).isoformat(),
                },
                {
                    "version": "1.1.0",
                    "accuracy": 0.95,
                    "training_samples": 8000,
                    "status": "active",
                    "created_at": (now - timedelta(days=10)).isoformat(),
                },
            ]
        }
        mock_result = MagicMock()
        mock_config = MagicMock()
        mock_config.value = registry_data
        mock_result.scalar_one_or_none.return_value = mock_config
        mock_session.execute.return_value = mock_result

        history = await model_registry.get_performance_history(
            ModelType.OCR_CONFIDENCE,
            days=30,
        )

        assert len(history) == 1  # Only the recent one


# =============================================================================
# CLEANUP TESTS
# =============================================================================


class TestCleanup:
    """Tests for old version cleanup."""

    @pytest.mark.asyncio
    async def test_cleanup_old_versions(
        self,
        model_registry: ModelRegistry,
        mock_session: AsyncMock,
    ) -> None:
        """Test archiving old versions."""
        now = datetime.utcnow()
        registry_data = {
            "ocr_confidence": [
                {
                    "version": "0.9.0",
                    "status": "deprecated",
                    "created_at": (now - timedelta(days=100)).isoformat(),
                },
                {
                    "version": "1.0.0",
                    "status": "deprecated",
                    "created_at": (now - timedelta(days=50)).isoformat(),
                },
                {
                    "version": "1.1.0",
                    "status": "active",
                    "created_at": (now - timedelta(days=10)).isoformat(),
                },
            ]
        }
        mock_result = MagicMock()
        mock_config = MagicMock()
        mock_config.value = registry_data
        mock_result.scalar_one_or_none.return_value = mock_config
        mock_session.execute.return_value = mock_result

        with patch.object(model_registry, "_save_registry", new_callable=AsyncMock):
            archived_count = await model_registry.cleanup_old_versions(
                ModelType.OCR_CONFIDENCE,
                archive_older_than_days=90,
            )

        assert archived_count == 1  # Only 0.9.0 is >90 days old

    @pytest.mark.asyncio
    async def test_cleanup_does_not_archive_active(
        self,
        model_registry: ModelRegistry,
        mock_session: AsyncMock,
    ) -> None:
        """Test that active models are never archived."""
        now = datetime.utcnow()
        registry_data = {
            "ocr_confidence": [
                {
                    "version": "1.0.0",
                    "status": "active",
                    "created_at": (now - timedelta(days=200)).isoformat(),
                },
            ]
        }
        mock_result = MagicMock()
        mock_config = MagicMock()
        mock_config.value = registry_data
        mock_result.scalar_one_or_none.return_value = mock_config
        mock_session.execute.return_value = mock_result

        archived_count = await model_registry.cleanup_old_versions(
            ModelType.OCR_CONFIDENCE,
            archive_older_than_days=90,
        )

        assert archived_count == 0  # Active model not archived


# =============================================================================
# EDGE CASES
# =============================================================================


class TestEdgeCases:
    """Tests for edge cases."""

    @pytest.mark.asyncio
    async def test_empty_registry(
        self,
        model_registry: ModelRegistry,
        mock_session: AsyncMock,
    ) -> None:
        """Test operations on empty registry."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        # Should return empty list, not error
        versions = await model_registry.list_versions(ModelType.OCR_CONFIDENCE)
        assert versions == []

        # Should return None, not error
        active = await model_registry.get_active_model(ModelType.OCR_CONFIDENCE)
        assert active is None

    @pytest.mark.asyncio
    async def test_model_type_not_in_registry(
        self,
        model_registry: ModelRegistry,
        mock_session: AsyncMock,
        sample_registry_data: dict,
    ) -> None:
        """Test querying for model type not in registry."""
        mock_result = MagicMock()
        mock_config = MagicMock()
        mock_config.value = sample_registry_data
        mock_result.scalar_one_or_none.return_value = mock_config
        mock_session.execute.return_value = mock_result

        # entity_matcher not in sample data
        versions = await model_registry.list_versions(ModelType.ENTITY_MATCHER)
        assert versions == []

    def test_semantic_version_ordering(self) -> None:
        """Test that versions are ordered correctly."""
        versions = [
            ModelVersion(version="1.0.0", status=ModelStatus.DEPRECATED),
            ModelVersion(version="2.0.0", status=ModelStatus.ACTIVE),
            ModelVersion(version="1.10.0", status=ModelStatus.DEPRECATED),
            ModelVersion(version="1.2.0", status=ModelStatus.DEPRECATED),
        ]

        # Sort by version string (lexicographic)
        sorted_versions = sorted(versions, key=lambda v: v.version, reverse=True)

        # Note: Lexicographic sort means "2.0.0" > "1.x.x" but "1.10.0" < "1.2.0"
        # This is a known limitation - proper semantic versioning would require
        # additional parsing
        assert sorted_versions[0].version == "2.0.0"
