"""
Model Registry Service

Provides versioning, rollback, and lifecycle management for ML models.
Stores metadata in PostgreSQL with model artifacts in MinIO.

Features:
- Model versioning with semantic versioning
- Automatic rollback on quality degradation
- A/B test integration
- Performance history tracking
"""

import hashlib
import json
import structlog
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.redis_state import get_redis
from app.db.models import AppConfig

logger = structlog.get_logger(__name__)


class ModelStatus(str, Enum):
    """Model lifecycle status."""

    DRAFT = "draft"  # Being developed
    CANDIDATE = "candidate"  # Ready for A/B testing
    ACTIVE = "active"  # Production model
    DEPRECATED = "deprecated"  # Replaced by newer version
    ROLLED_BACK = "rolled_back"  # Rolled back due to issues
    ARCHIVED = "archived"  # No longer in use


class ModelType(str, Enum):
    """Types of models managed by the registry."""

    OCR_CONFIDENCE = "ocr_confidence"  # Confidence calibration model
    OCR_BACKEND_ROUTER = "ocr_backend_router"  # Backend selection model
    DOCUMENT_CLASSIFIER = "document_classifier"  # Document type classifier
    ENTITY_MATCHER = "entity_matcher"  # Entity matching model
    EXTRACTION_MODEL = "extraction_model"  # Field extraction model


class ModelMetadata(BaseModel):
    """Metadata for a registered model version."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    model_type: ModelType
    version: str  # Semantic version: "1.2.3"
    status: ModelStatus = ModelStatus.DRAFT

    # Training info
    trained_at: Optional[datetime] = None
    training_samples: int = 0
    training_duration_seconds: float = 0.0

    # Performance metrics
    accuracy: Optional[float] = None
    precision: Optional[float] = None
    recall: Optional[float] = None
    f1_score: Optional[float] = None
    custom_metrics: dict[str, float] = Field(default_factory=dict)

    # Artifact info
    artifact_path: Optional[str] = None  # MinIO path
    artifact_hash: Optional[str] = None  # SHA256 hash
    artifact_size_bytes: int = 0

    # Lineage
    parent_version: Optional[str] = None
    created_by: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    # A/B test info
    ab_test_id: Optional[str] = None
    ab_test_variant: Optional[str] = None

    # Deployment info
    deployed_at: Optional[datetime] = None
    deprecated_at: Optional[datetime] = None
    rollback_reason: Optional[str] = None

    # Tags and notes
    tags: list[str] = Field(default_factory=list)
    notes: Optional[str] = None

    class Config:
        use_enum_values = True


class ModelVersion(BaseModel):
    """Simplified model version for quick lookups."""

    version: str
    status: ModelStatus
    accuracy: Optional[float] = None
    deployed_at: Optional[datetime] = None


class ModelRegistry:
    """
    Model Registry for ML model lifecycle management.

    Stores model metadata in PostgreSQL (via AppConfig JSONB)
    and artifacts in MinIO for production deployments.

    Usage:
        registry = ModelRegistry(db_session)

        # Register new model
        metadata = await registry.register_model(
            model_type=ModelType.OCR_CONFIDENCE,
            version="1.0.0",
            training_samples=5000,
            accuracy=0.95
        )

        # Promote to production
        await registry.promote_to_active(model_type, "1.0.0")

        # Rollback if issues
        await registry.rollback(model_type, reason="Accuracy drop")
    """

    REGISTRY_KEY = "mlops_model_registry"
    ACTIVE_MODELS_KEY = "mlops_active_models"
    CACHE_TTL = 300  # 5 minutes

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self._cache_key = "model_registry"

    async def _load_registry(self) -> dict[str, list[dict[str, Any]]]:
        """Load registry from database."""
        result = await self.db.execute(
            select(AppConfig).where(AppConfig.key == self.REGISTRY_KEY)
        )
        config = result.scalar_one_or_none()

        if config and config.value:
            return config.value
        return {}

    async def _save_registry(self, registry: dict[str, list[dict[str, Any]]]) -> None:
        """Save registry to database."""
        result = await self.db.execute(
            select(AppConfig).where(AppConfig.key == self.REGISTRY_KEY)
        )
        config = result.scalar_one_or_none()

        if config:
            config.value = registry
            config.updated_at = datetime.utcnow()
        else:
            config = AppConfig(
                key=self.REGISTRY_KEY,
                value=registry,
                description="MLOps Model Registry - Model versions and metadata"
            )
            self.db.add(config)

        await self.db.flush()

        # Invalidate cache
        try:
            redis = await get_redis()
            await redis.delete(self._cache_key)
        except Exception as e:
            logger.warning(f"Cache invalidation failed: {e}")

    async def register_model(
        self,
        model_type: ModelType,
        version: str,
        training_samples: int = 0,
        accuracy: Optional[float] = None,
        precision: Optional[float] = None,
        recall: Optional[float] = None,
        f1_score: Optional[float] = None,
        custom_metrics: Optional[dict[str, float]] = None,
        parent_version: Optional[str] = None,
        created_by: Optional[str] = None,
        tags: Optional[list[str]] = None,
        notes: Optional[str] = None,
    ) -> ModelMetadata:
        """
        Register a new model version.

        Args:
            model_type: Type of model
            version: Semantic version string
            training_samples: Number of samples used for training
            accuracy: Model accuracy metric
            precision: Model precision metric
            recall: Model recall metric
            f1_score: F1 score metric
            custom_metrics: Additional custom metrics
            parent_version: Previous version this was trained from
            created_by: User or system that created this version
            tags: Tags for categorization
            notes: Additional notes

        Returns:
            ModelMetadata for the registered model
        """
        registry = await self._load_registry()
        type_key = model_type.value

        if type_key not in registry:
            registry[type_key] = []

        # Check for duplicate version
        for existing in registry[type_key]:
            if existing.get("version") == version:
                raise ValueError(
                    f"Version {version} already exists for {model_type.value}"
                )

        metadata = ModelMetadata(
            model_type=model_type,
            version=version,
            status=ModelStatus.DRAFT,
            training_samples=training_samples,
            accuracy=accuracy,
            precision=precision,
            recall=recall,
            f1_score=f1_score,
            custom_metrics=custom_metrics or {},
            parent_version=parent_version,
            created_by=created_by,
            tags=tags or [],
            notes=notes,
        )

        registry[type_key].append(metadata.model_dump(mode="json"))
        await self._save_registry(registry)

        logger.info(
            f"Registered model: {model_type.value} v{version} "
            f"(samples={training_samples}, accuracy={accuracy})"
        )

        return metadata

    async def get_model(
        self,
        model_type: ModelType,
        version: str,
    ) -> Optional[ModelMetadata]:
        """Get specific model version metadata."""
        registry = await self._load_registry()
        type_key = model_type.value

        if type_key not in registry:
            return None

        for model_data in registry[type_key]:
            if model_data.get("version") == version:
                return ModelMetadata(**model_data)

        return None

    async def get_active_model(
        self,
        model_type: ModelType,
    ) -> Optional[ModelMetadata]:
        """Get the currently active production model."""
        registry = await self._load_registry()
        type_key = model_type.value

        if type_key not in registry:
            return None

        for model_data in registry[type_key]:
            if model_data.get("status") == ModelStatus.ACTIVE.value:
                return ModelMetadata(**model_data)

        return None

    async def list_versions(
        self,
        model_type: ModelType,
        status: Optional[ModelStatus] = None,
        limit: int = 20,
    ) -> list[ModelVersion]:
        """List model versions with optional status filter."""
        registry = await self._load_registry()
        type_key = model_type.value

        if type_key not in registry:
            return []

        versions = []
        for model_data in registry[type_key]:
            if status and model_data.get("status") != status.value:
                continue

            versions.append(ModelVersion(
                version=model_data.get("version", "unknown"),
                status=ModelStatus(model_data.get("status", "draft")),
                accuracy=model_data.get("accuracy"),
                deployed_at=model_data.get("deployed_at"),
            ))

        # Sort by version (newest first)
        versions.sort(key=lambda v: v.version, reverse=True)
        return versions[:limit]

    async def update_status(
        self,
        model_type: ModelType,
        version: str,
        status: ModelStatus,
        reason: Optional[str] = None,
    ) -> ModelMetadata:
        """Update model status."""
        registry = await self._load_registry()
        type_key = model_type.value

        if type_key not in registry:
            raise ValueError(f"No models registered for {model_type.value}")

        for model_data in registry[type_key]:
            if model_data.get("version") == version:
                old_status = model_data.get("status")
                model_data["status"] = status.value
                model_data["updated_at"] = datetime.utcnow().isoformat()

                if status == ModelStatus.ACTIVE:
                    model_data["deployed_at"] = datetime.utcnow().isoformat()
                elif status == ModelStatus.DEPRECATED:
                    model_data["deprecated_at"] = datetime.utcnow().isoformat()
                elif status == ModelStatus.ROLLED_BACK:
                    model_data["rollback_reason"] = reason

                await self._save_registry(registry)

                logger.info(
                    f"Model status updated: {model_type.value} v{version} "
                    f"{old_status} -> {status.value}"
                )

                return ModelMetadata(**model_data)

        raise ValueError(f"Version {version} not found for {model_type.value}")

    async def promote_to_active(
        self,
        model_type: ModelType,
        version: str,
    ) -> ModelMetadata:
        """
        Promote a model version to active production status.

        This will:
        1. Deprecate the current active version (if any)
        2. Set the specified version to ACTIVE
        """
        registry = await self._load_registry()
        type_key = model_type.value

        if type_key not in registry:
            raise ValueError(f"No models registered for {model_type.value}")

        target_found = False

        for model_data in registry[type_key]:
            # Deprecate current active
            if model_data.get("status") == ModelStatus.ACTIVE.value:
                model_data["status"] = ModelStatus.DEPRECATED.value
                model_data["deprecated_at"] = datetime.utcnow().isoformat()
                model_data["updated_at"] = datetime.utcnow().isoformat()
                logger.info(
                    f"Deprecated previous active: {model_type.value} "
                    f"v{model_data.get('version')}"
                )

            # Promote target version
            if model_data.get("version") == version:
                target_found = True
                model_data["status"] = ModelStatus.ACTIVE.value
                model_data["deployed_at"] = datetime.utcnow().isoformat()
                model_data["updated_at"] = datetime.utcnow().isoformat()

        if not target_found:
            raise ValueError(f"Version {version} not found for {model_type.value}")

        await self._save_registry(registry)

        logger.info(f"Promoted to active: {model_type.value} v{version}")

        return await self.get_model(model_type, version)  # type: ignore

    async def rollback(
        self,
        model_type: ModelType,
        reason: str,
    ) -> Optional[ModelMetadata]:
        """
        Rollback to the previous active model version.

        This will:
        1. Mark current active as ROLLED_BACK
        2. Find the most recent DEPRECATED version
        3. Promote it back to ACTIVE

        Returns the newly active model, or None if no rollback target found.
        """
        registry = await self._load_registry()
        type_key = model_type.value

        if type_key not in registry:
            logger.warning(f"No models to rollback for {model_type.value}")
            return None

        current_active = None
        rollback_target = None

        # Find current active and best rollback target
        deprecated_versions = []

        for model_data in registry[type_key]:
            if model_data.get("status") == ModelStatus.ACTIVE.value:
                current_active = model_data
            elif model_data.get("status") == ModelStatus.DEPRECATED.value:
                deprecated_versions.append(model_data)

        if not current_active:
            logger.warning(f"No active model to rollback for {model_type.value}")
            return None

        # Find most recently deprecated version
        if deprecated_versions:
            deprecated_versions.sort(
                key=lambda x: x.get("deprecated_at", ""),
                reverse=True
            )
            rollback_target = deprecated_versions[0]

        if not rollback_target:
            logger.warning(
                f"No rollback target found for {model_type.value}. "
                "Consider using a baseline model."
            )
            return None

        # Perform rollback
        current_active["status"] = ModelStatus.ROLLED_BACK.value
        current_active["rollback_reason"] = reason
        current_active["updated_at"] = datetime.utcnow().isoformat()

        rollback_target["status"] = ModelStatus.ACTIVE.value
        rollback_target["deployed_at"] = datetime.utcnow().isoformat()
        rollback_target["updated_at"] = datetime.utcnow().isoformat()

        await self._save_registry(registry)

        logger.info(
            f"Rolled back {model_type.value}: "
            f"v{current_active.get('version')} -> v{rollback_target.get('version')} "
            f"(reason: {reason})"
        )

        return ModelMetadata(**rollback_target)

    async def check_quality_degradation(
        self,
        model_type: ModelType,
        current_accuracy: float,
        threshold: float = 0.05,
    ) -> bool:
        """
        Check if model quality has degraded beyond threshold.

        Args:
            model_type: Type of model to check
            current_accuracy: Current measured accuracy
            threshold: Maximum allowed degradation (default 5%)

        Returns:
            True if degradation exceeds threshold (should rollback)
        """
        active = await self.get_active_model(model_type)

        if not active or active.accuracy is None:
            return False

        degradation = active.accuracy - current_accuracy

        if degradation > threshold:
            logger.warning(
                f"Quality degradation detected for {model_type.value}: "
                f"baseline={active.accuracy:.3f}, current={current_accuracy:.3f}, "
                f"degradation={degradation:.3f} (threshold={threshold})"
            )
            return True

        return False

    async def get_performance_history(
        self,
        model_type: ModelType,
        days: int = 30,
    ) -> list[dict[str, Any]]:
        """Get performance history for model type."""
        registry = await self._load_registry()
        type_key = model_type.value

        if type_key not in registry:
            return []

        cutoff = datetime.utcnow() - timedelta(days=days)
        history = []

        for model_data in registry[type_key]:
            created_at = model_data.get("created_at")
            if created_at:
                if isinstance(created_at, str):
                    created_at = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                if created_at >= cutoff:
                    history.append({
                        "version": model_data.get("version"),
                        "accuracy": model_data.get("accuracy"),
                        "training_samples": model_data.get("training_samples"),
                        "created_at": model_data.get("created_at"),
                        "status": model_data.get("status"),
                    })

        history.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        return history

    async def cleanup_old_versions(
        self,
        model_type: ModelType,
        keep_active: int = 1,
        keep_deprecated: int = 3,
        archive_older_than_days: int = 90,
    ) -> int:
        """
        Archive old model versions to reduce registry size.

        Args:
            model_type: Type of model to clean up
            keep_active: Number of active versions to keep (latest)
            keep_deprecated: Number of deprecated versions to keep
            archive_older_than_days: Archive versions older than this

        Returns:
            Number of versions archived
        """
        registry = await self._load_registry()
        type_key = model_type.value

        if type_key not in registry:
            return 0

        cutoff = datetime.utcnow() - timedelta(days=archive_older_than_days)
        archived_count = 0

        for model_data in registry[type_key]:
            status = model_data.get("status")

            # Skip already archived
            if status == ModelStatus.ARCHIVED.value:
                continue

            # Don't archive active models
            if status == ModelStatus.ACTIVE.value:
                continue

            created_at = model_data.get("created_at")
            if created_at:
                if isinstance(created_at, str):
                    created_at = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                if created_at < cutoff:
                    model_data["status"] = ModelStatus.ARCHIVED.value
                    model_data["updated_at"] = datetime.utcnow().isoformat()
                    archived_count += 1

        if archived_count > 0:
            await self._save_registry(registry)
            logger.info(f"Archived {archived_count} old versions for {model_type.value}")

        return archived_count
