"""
Retraining Service

Manages automated model retraining based on feedback thresholds,
drift detection, and scheduled triggers.

Features:
- Threshold-based retraining (e.g., 100+ corrections)
- Scheduled weekly retraining
- Drift-triggered retraining
- Training data export for external training
"""

import logging
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Optional
from uuid import uuid4

from pydantic import BaseModel, Field
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.redis_state import get_redis
from app.db.models import AppConfig
from app.db.models_ocr_feedback import (
    OCRCorrectionFeedback,
    FeedbackStatus,
    CorrectionType,
)
from app.services.mlops.model_registry import ModelRegistry, ModelType, ModelStatus

logger = logging.getLogger(__name__)


class RetrainingTrigger(str, Enum):
    """Reasons for triggering retraining."""

    THRESHOLD = "threshold"  # Feedback count exceeded threshold
    SCHEDULED = "scheduled"  # Weekly/daily schedule
    DRIFT = "drift"  # Drift detected
    MANUAL = "manual"  # Manually triggered
    AB_TEST_WINNER = "ab_test_winner"  # A/B test concluded with winner


class RetrainingStatus(str, Enum):
    """Status of a retraining job."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class RetrainingConfig(BaseModel):
    """Configuration for retraining triggers."""

    # Feedback threshold trigger
    feedback_threshold: int = 100  # Trigger at N+ corrections
    feedback_window_hours: int = 168  # Consider feedbacks from last 7 days

    # Scheduled triggers
    weekly_enabled: bool = True
    weekly_day: int = 0  # 0=Monday, 6=Sunday
    weekly_hour: int = 3  # 03:00 UTC

    # Drift trigger
    drift_threshold: float = 0.1  # 10% drift triggers retraining
    drift_check_interval_hours: int = 24

    # Quality thresholds
    min_training_samples: int = 50  # Minimum samples for training
    min_accuracy_improvement: float = 0.01  # 1% improvement required

    # Rate limiting
    min_hours_between_retrains: int = 24  # Max once per day


class RetrainingJob(BaseModel):
    """Retraining job metadata."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    model_type: ModelType
    trigger: RetrainingTrigger
    status: RetrainingStatus = RetrainingStatus.PENDING

    # Configuration
    config: RetrainingConfig = Field(default_factory=RetrainingConfig)

    # Training data
    training_samples: int = 0
    feedback_ids: list[str] = Field(default_factory=list)

    # Timing
    created_at: datetime = Field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    # Results
    old_version: Optional[str] = None
    new_version: Optional[str] = None
    accuracy_before: Optional[float] = None
    accuracy_after: Optional[float] = None
    error_message: Optional[str] = None

    class Config:
        use_enum_values = True


class RetrainingService:
    """
    Service for managing model retraining lifecycle.

    Coordinates between:
    - OCR Correction Feedback (training data)
    - Model Registry (versioning)
    - Celery Tasks (actual training)

    Usage:
        service = RetrainingService(db)

        # Check if retraining is needed
        if await service.should_retrain(ModelType.OCR_CONFIDENCE):
            job = await service.create_retraining_job(
                ModelType.OCR_CONFIDENCE,
                RetrainingTrigger.THRESHOLD
            )

        # Export training data
        data = await service.export_training_data(job.id)
    """

    CONFIG_KEY = "mlops_retraining_config"
    JOBS_KEY = "mlops_retraining_jobs"
    LAST_RETRAIN_KEY = "mlops_last_retrain"

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.registry = ModelRegistry(db)

    async def _load_config(self) -> RetrainingConfig:
        """Load retraining configuration."""
        result = await self.db.execute(
            select(AppConfig).where(AppConfig.key == self.CONFIG_KEY)
        )
        config = result.scalar_one_or_none()

        if config and config.value:
            return RetrainingConfig(**config.value)
        return RetrainingConfig()

    async def _save_config(self, config: RetrainingConfig) -> None:
        """Save retraining configuration."""
        result = await self.db.execute(
            select(AppConfig).where(AppConfig.key == self.CONFIG_KEY)
        )
        app_config = result.scalar_one_or_none()

        if app_config:
            app_config.value = config.model_dump(mode="json")
            app_config.updated_at = datetime.utcnow()
        else:
            app_config = AppConfig(
                key=self.CONFIG_KEY,
                value=config.model_dump(mode="json"),
                description="MLOps Retraining Configuration"
            )
            self.db.add(app_config)

        await self.db.flush()

    async def _load_jobs(self) -> list[dict[str, Any]]:
        """Load retraining jobs history."""
        result = await self.db.execute(
            select(AppConfig).where(AppConfig.key == self.JOBS_KEY)
        )
        config = result.scalar_one_or_none()

        if config and config.value:
            return config.value
        return []

    async def _save_jobs(self, jobs: list[dict[str, Any]]) -> None:
        """Save retraining jobs."""
        result = await self.db.execute(
            select(AppConfig).where(AppConfig.key == self.JOBS_KEY)
        )
        config = result.scalar_one_or_none()

        # Keep only last 100 jobs
        jobs = jobs[-100:] if len(jobs) > 100 else jobs

        if config:
            config.value = jobs
            config.updated_at = datetime.utcnow()
        else:
            config = AppConfig(
                key=self.JOBS_KEY,
                value=jobs,
                description="MLOps Retraining Jobs History"
            )
            self.db.add(config)

        await self.db.flush()

    async def _get_last_retrain_time(
        self,
        model_type: ModelType,
    ) -> Optional[datetime]:
        """Get the last retraining time for a model type."""
        result = await self.db.execute(
            select(AppConfig).where(AppConfig.key == self.LAST_RETRAIN_KEY)
        )
        config = result.scalar_one_or_none()

        if config and config.value:
            timestamp = config.value.get(model_type.value)
            if timestamp:
                return datetime.fromisoformat(timestamp)
        return None

    async def _set_last_retrain_time(
        self,
        model_type: ModelType,
    ) -> None:
        """Record retraining time for a model type."""
        result = await self.db.execute(
            select(AppConfig).where(AppConfig.key == self.LAST_RETRAIN_KEY)
        )
        config = result.scalar_one_or_none()

        timestamps = {}
        if config and config.value:
            timestamps = config.value

        timestamps[model_type.value] = datetime.utcnow().isoformat()

        if config:
            config.value = timestamps
            config.updated_at = datetime.utcnow()
        else:
            config = AppConfig(
                key=self.LAST_RETRAIN_KEY,
                value=timestamps,
                description="MLOps Last Retraining Timestamps"
            )
            self.db.add(config)

        await self.db.flush()

    async def get_pending_feedback_count(
        self,
        model_type: Optional[ModelType] = None,
        hours: int = 168,  # 7 days
    ) -> int:
        """Count pending OCR corrections in the time window."""
        cutoff = datetime.utcnow() - timedelta(hours=hours)

        query = select(func.count(OCRCorrectionFeedback.id)).where(
            and_(
                OCRCorrectionFeedback.created_at >= cutoff,
                OCRCorrectionFeedback.status == FeedbackStatus.PENDING,
            )
        )

        result = await self.db.execute(query)
        return result.scalar_one() or 0

    async def get_verified_feedback_count(
        self,
        model_type: Optional[ModelType] = None,
        hours: int = 168,
    ) -> int:
        """Count verified OCR corrections (higher quality training data)."""
        cutoff = datetime.utcnow() - timedelta(hours=hours)

        query = select(func.count(OCRCorrectionFeedback.id)).where(
            and_(
                OCRCorrectionFeedback.created_at >= cutoff,
                OCRCorrectionFeedback.status == FeedbackStatus.VERIFIED,
            )
        )

        result = await self.db.execute(query)
        return result.scalar_one() or 0

    async def should_retrain(
        self,
        model_type: ModelType,
        trigger: Optional[RetrainingTrigger] = None,
    ) -> tuple[bool, Optional[RetrainingTrigger]]:
        """
        Check if retraining should be triggered.

        Args:
            model_type: Type of model to check
            trigger: Specific trigger to check (or check all if None)

        Returns:
            Tuple of (should_retrain, trigger_reason)
        """
        config = await self._load_config()

        # Check rate limiting
        last_retrain = await self._get_last_retrain_time(model_type)
        if last_retrain:
            hours_since = (datetime.utcnow() - last_retrain).total_seconds() / 3600
            if hours_since < config.min_hours_between_retrains:
                logger.debug(
                    f"Retraining rate-limited: {hours_since:.1f}h since last "
                    f"(min {config.min_hours_between_retrains}h)"
                )
                return False, None

        # Check feedback threshold
        if trigger is None or trigger == RetrainingTrigger.THRESHOLD:
            feedback_count = await self.get_pending_feedback_count(
                model_type,
                hours=config.feedback_window_hours,
            )

            if feedback_count >= config.feedback_threshold:
                logger.info(
                    f"Retraining threshold reached: {feedback_count} >= "
                    f"{config.feedback_threshold} feedbacks"
                )
                return True, RetrainingTrigger.THRESHOLD

        # Check scheduled trigger
        if trigger is None or trigger == RetrainingTrigger.SCHEDULED:
            if config.weekly_enabled:
                now = datetime.utcnow()
                if (
                    now.weekday() == config.weekly_day
                    and now.hour == config.weekly_hour
                ):
                    # Only trigger if we haven't retrained today
                    if not last_retrain or last_retrain.date() < now.date():
                        logger.info("Scheduled weekly retraining triggered")
                        return True, RetrainingTrigger.SCHEDULED

        return False, None

    async def create_retraining_job(
        self,
        model_type: ModelType,
        trigger: RetrainingTrigger,
        custom_config: Optional[RetrainingConfig] = None,
    ) -> RetrainingJob:
        """
        Create a new retraining job.

        Args:
            model_type: Type of model to retrain
            trigger: What triggered the retraining
            custom_config: Optional custom configuration

        Returns:
            RetrainingJob with pending status
        """
        config = custom_config or await self._load_config()

        # Get current model version
        active_model = await self.registry.get_active_model(model_type)
        old_version = active_model.version if active_model else None
        accuracy_before = active_model.accuracy if active_model else None

        # Count available training data
        training_samples = await self.get_pending_feedback_count(
            model_type,
            hours=config.feedback_window_hours,
        )

        if training_samples < config.min_training_samples:
            raise ValueError(
                f"Insufficient training data: {training_samples} < "
                f"{config.min_training_samples} minimum"
            )

        # Get feedback IDs for training
        cutoff = datetime.utcnow() - timedelta(hours=config.feedback_window_hours)
        result = await self.db.execute(
            select(OCRCorrectionFeedback.id).where(
                and_(
                    OCRCorrectionFeedback.created_at >= cutoff,
                    OCRCorrectionFeedback.status.in_([
                        FeedbackStatus.PENDING,
                        FeedbackStatus.VERIFIED,
                    ]),
                )
            ).limit(10000)  # Safety limit
        )
        feedback_ids = [str(row[0]) for row in result.fetchall()]

        job = RetrainingJob(
            model_type=model_type,
            trigger=trigger,
            config=config,
            training_samples=training_samples,
            feedback_ids=feedback_ids,
            old_version=old_version,
            accuracy_before=accuracy_before,
        )

        # Save job
        jobs = await self._load_jobs()
        jobs.append(job.model_dump(mode="json"))
        await self._save_jobs(jobs)

        logger.info(
            f"Created retraining job: {job.id} for {model_type.value} "
            f"(trigger={trigger.value}, samples={training_samples})"
        )

        return job

    async def update_job_status(
        self,
        job_id: str,
        status: RetrainingStatus,
        new_version: Optional[str] = None,
        accuracy_after: Optional[float] = None,
        error_message: Optional[str] = None,
    ) -> Optional[RetrainingJob]:
        """Update retraining job status."""
        jobs = await self._load_jobs()

        for job_data in jobs:
            if job_data.get("id") == job_id:
                job_data["status"] = status.value
                job_data["updated_at"] = datetime.utcnow().isoformat()

                if status == RetrainingStatus.RUNNING:
                    job_data["started_at"] = datetime.utcnow().isoformat()
                elif status in [RetrainingStatus.COMPLETED, RetrainingStatus.FAILED]:
                    job_data["completed_at"] = datetime.utcnow().isoformat()

                if new_version:
                    job_data["new_version"] = new_version
                if accuracy_after is not None:
                    job_data["accuracy_after"] = accuracy_after
                if error_message:
                    job_data["error_message"] = error_message

                await self._save_jobs(jobs)

                # Update last retrain time on completion
                if status == RetrainingStatus.COMPLETED:
                    model_type = ModelType(job_data.get("model_type"))
                    await self._set_last_retrain_time(model_type)

                return RetrainingJob(**job_data)

        return None

    async def get_job(self, job_id: str) -> Optional[RetrainingJob]:
        """Get retraining job by ID."""
        jobs = await self._load_jobs()

        for job_data in jobs:
            if job_data.get("id") == job_id:
                return RetrainingJob(**job_data)

        return None

    async def list_jobs(
        self,
        model_type: Optional[ModelType] = None,
        status: Optional[RetrainingStatus] = None,
        limit: int = 20,
    ) -> list[RetrainingJob]:
        """List retraining jobs with optional filters."""
        jobs = await self._load_jobs()
        result = []

        for job_data in reversed(jobs):  # Most recent first
            if model_type and job_data.get("model_type") != model_type.value:
                continue
            if status and job_data.get("status") != status.value:
                continue

            result.append(RetrainingJob(**job_data))

            if len(result) >= limit:
                break

        return result

    async def export_training_data(
        self,
        job_id: str,
        format: str = "jsonl",
    ) -> list[dict[str, Any]]:
        """
        Export training data for a retraining job.

        Args:
            job_id: Retraining job ID
            format: Export format (jsonl, csv)

        Returns:
            List of training samples
        """
        job = await self.get_job(job_id)
        if not job:
            raise ValueError(f"Job not found: {job_id}")

        # Fetch feedback records
        from uuid import UUID as UUIDType

        feedback_uuids = [UUIDType(fid) for fid in job.feedback_ids[:1000]]

        result = await self.db.execute(
            select(OCRCorrectionFeedback).where(
                OCRCorrectionFeedback.id.in_(feedback_uuids)
            )
        )
        feedbacks = result.scalars().all()

        training_data = []
        for fb in feedbacks:
            sample = {
                "id": str(fb.id),
                "document_id": str(fb.document_id) if fb.document_id else None,
                "backend": fb.backend,
                "field_name": fb.field_name,
                "correction_type": fb.correction_type.value if fb.correction_type else None,
                "original_value": fb.original_value,
                "corrected_value": fb.corrected_value,
                "confidence_before": fb.confidence_before,
                "confidence_after": fb.confidence_after,
                "error_category": fb.error_category,
                "document_type": fb.document_type,
                "created_at": fb.created_at.isoformat() if fb.created_at else None,
            }
            training_data.append(sample)

        logger.info(f"Exported {len(training_data)} training samples for job {job_id}")

        return training_data

    async def mark_feedbacks_processed(
        self,
        job_id: str,
    ) -> int:
        """
        Mark feedbacks as processed after successful training.

        Returns number of feedbacks marked.
        """
        job = await self.get_job(job_id)
        if not job:
            raise ValueError(f"Job not found: {job_id}")

        from uuid import UUID as UUIDType

        feedback_uuids = [UUIDType(fid) for fid in job.feedback_ids]

        result = await self.db.execute(
            select(OCRCorrectionFeedback).where(
                OCRCorrectionFeedback.id.in_(feedback_uuids)
            )
        )
        feedbacks = result.scalars().all()

        count = 0
        for fb in feedbacks:
            if fb.status == FeedbackStatus.PENDING:
                fb.status = FeedbackStatus.PROCESSED
                fb.processed_at = datetime.utcnow()
                count += 1

        await self.db.flush()

        logger.info(f"Marked {count} feedbacks as processed for job {job_id}")
        return count

    async def get_retraining_stats(self) -> dict[str, Any]:
        """Get overall retraining statistics."""
        jobs = await self._load_jobs()

        stats = {
            "total_jobs": len(jobs),
            "completed_jobs": 0,
            "failed_jobs": 0,
            "avg_improvement": 0.0,
            "total_samples_trained": 0,
            "jobs_by_trigger": {},
            "jobs_by_model_type": {},
        }

        improvements = []

        for job_data in jobs:
            status = job_data.get("status")
            trigger = job_data.get("trigger", "unknown")
            model_type = job_data.get("model_type", "unknown")

            if status == RetrainingStatus.COMPLETED.value:
                stats["completed_jobs"] += 1
                stats["total_samples_trained"] += job_data.get("training_samples", 0)

                before = job_data.get("accuracy_before")
                after = job_data.get("accuracy_after")
                if before is not None and after is not None:
                    improvements.append(after - before)

            elif status == RetrainingStatus.FAILED.value:
                stats["failed_jobs"] += 1

            # Count by trigger
            stats["jobs_by_trigger"][trigger] = stats["jobs_by_trigger"].get(trigger, 0) + 1

            # Count by model type
            stats["jobs_by_model_type"][model_type] = (
                stats["jobs_by_model_type"].get(model_type, 0) + 1
            )

        if improvements:
            stats["avg_improvement"] = sum(improvements) / len(improvements)

        return stats
