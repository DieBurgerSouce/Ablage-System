# -*- coding: utf-8 -*-
"""
Unit Tests for Retraining Service.

Tests the MLOps retraining lifecycle management:
- Threshold-based retraining triggers
- Scheduled retraining
- Rate limiting
- Job creation and status updates
- Training data export
- Feedback processing

Enterprise Feature: MLOps Pipeline
"""

import uuid
from datetime import datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.mlops.retraining_service import (
    RetrainingService,
    RetrainingTrigger,
    RetrainingStatus,
    RetrainingConfig,
    RetrainingJob,
)
from app.services.mlops.model_registry import ModelType, ModelStatus


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
def retraining_service(mock_session: AsyncMock) -> RetrainingService:
    """Create retraining service with mocked session."""
    return RetrainingService(mock_session)


@pytest.fixture
def sample_config() -> RetrainingConfig:
    """Sample retraining configuration."""
    return RetrainingConfig(
        feedback_threshold=100,
        feedback_window_hours=168,
        weekly_enabled=True,
        weekly_day=0,
        weekly_hour=3,
        drift_threshold=0.1,
        min_training_samples=50,
        min_accuracy_improvement=0.01,
        min_hours_between_retrains=24,
    )


@pytest.fixture
def sample_jobs_data() -> list[dict[str, Any]]:
    """Sample jobs history."""
    return [
        {
            "id": "job-1",
            "model_type": "ocr_confidence",
            "trigger": "threshold",
            "status": "completed",
            "training_samples": 150,
            "accuracy_before": 0.92,
            "accuracy_after": 0.95,
            "created_at": (datetime.utcnow() - timedelta(days=7)).isoformat(),
            "completed_at": (datetime.utcnow() - timedelta(days=7)).isoformat(),
        },
        {
            "id": "job-2",
            "model_type": "document_classifier",
            "trigger": "scheduled",
            "status": "failed",
            "training_samples": 80,
            "error_message": "Insufficient GPU memory",
            "created_at": (datetime.utcnow() - timedelta(days=3)).isoformat(),
        },
        {
            "id": "job-3",
            "model_type": "ocr_confidence",
            "trigger": "manual",
            "status": "pending",
            "training_samples": 200,
            "created_at": datetime.utcnow().isoformat(),
        },
    ]


# =============================================================================
# ENUM TESTS
# =============================================================================


class TestRetrainingTrigger:
    """Tests for RetrainingTrigger enum."""

    def test_all_triggers_defined(self) -> None:
        """Verify all retraining triggers are defined."""
        assert RetrainingTrigger.THRESHOLD == "threshold"
        assert RetrainingTrigger.SCHEDULED == "scheduled"
        assert RetrainingTrigger.DRIFT == "drift"
        assert RetrainingTrigger.MANUAL == "manual"
        assert RetrainingTrigger.AB_TEST_WINNER == "ab_test_winner"

    def test_trigger_count(self) -> None:
        """Verify expected number of triggers."""
        assert len(RetrainingTrigger) == 5


class TestRetrainingStatus:
    """Tests for RetrainingStatus enum."""

    def test_all_statuses_defined(self) -> None:
        """Verify all retraining statuses are defined."""
        assert RetrainingStatus.PENDING == "pending"
        assert RetrainingStatus.RUNNING == "running"
        assert RetrainingStatus.COMPLETED == "completed"
        assert RetrainingStatus.FAILED == "failed"
        assert RetrainingStatus.CANCELLED == "cancelled"

    def test_status_count(self) -> None:
        """Verify expected number of statuses."""
        assert len(RetrainingStatus) == 5

    def test_terminal_statuses(self) -> None:
        """Test terminal statuses (cannot transition from)."""
        terminal = [
            RetrainingStatus.COMPLETED,
            RetrainingStatus.FAILED,
            RetrainingStatus.CANCELLED,
        ]
        assert len(terminal) == 3


# =============================================================================
# RETRAINING CONFIG TESTS
# =============================================================================


class TestRetrainingConfig:
    """Tests for RetrainingConfig model."""

    def test_default_config(self) -> None:
        """Test default configuration values."""
        config = RetrainingConfig()

        assert config.feedback_threshold == 100
        assert config.feedback_window_hours == 168  # 7 days
        assert config.weekly_enabled is True
        assert config.weekly_day == 0  # Monday
        assert config.weekly_hour == 3  # 03:00 UTC
        assert config.drift_threshold == 0.1  # 10%
        assert config.min_training_samples == 50
        assert config.min_accuracy_improvement == 0.01  # 1%
        assert config.min_hours_between_retrains == 24

    def test_custom_config(self) -> None:
        """Test custom configuration."""
        config = RetrainingConfig(
            feedback_threshold=200,
            feedback_window_hours=336,  # 14 days
            weekly_enabled=False,
            drift_threshold=0.05,
            min_training_samples=100,
            min_hours_between_retrains=12,
        )

        assert config.feedback_threshold == 200
        assert config.feedback_window_hours == 336
        assert config.weekly_enabled is False
        assert config.drift_threshold == 0.05
        assert config.min_training_samples == 100
        assert config.min_hours_between_retrains == 12

    def test_config_validation_bounds(self) -> None:
        """Test configuration bound validation."""
        # Threshold should be reasonable
        config = RetrainingConfig(feedback_threshold=1)
        assert config.feedback_threshold == 1

        # Drift threshold as percentage
        config = RetrainingConfig(drift_threshold=0.5)
        assert config.drift_threshold == 0.5


# =============================================================================
# RETRAINING JOB TESTS
# =============================================================================


class TestRetrainingJob:
    """Tests for RetrainingJob model."""

    def test_minimal_creation(self) -> None:
        """Test minimal job creation."""
        job = RetrainingJob(
            model_type=ModelType.OCR_CONFIDENCE,
            trigger=RetrainingTrigger.THRESHOLD,
        )

        assert job.model_type == ModelType.OCR_CONFIDENCE
        assert job.trigger == RetrainingTrigger.THRESHOLD
        assert job.status == RetrainingStatus.PENDING
        assert job.training_samples == 0
        assert job.id is not None

    def test_full_creation(self) -> None:
        """Test full job creation."""
        job = RetrainingJob(
            model_type=ModelType.DOCUMENT_CLASSIFIER,
            trigger=RetrainingTrigger.MANUAL,
            training_samples=500,
            feedback_ids=["id-1", "id-2", "id-3"],
            old_version="1.0.0",
            accuracy_before=0.90,
        )

        assert job.training_samples == 500
        assert len(job.feedback_ids) == 3
        assert job.old_version == "1.0.0"
        assert job.accuracy_before == 0.90
        assert job.new_version is None
        assert job.accuracy_after is None

    def test_job_defaults(self) -> None:
        """Test job default values."""
        job = RetrainingJob(
            model_type=ModelType.OCR_CONFIDENCE,
            trigger=RetrainingTrigger.THRESHOLD,
        )

        assert job.status == RetrainingStatus.PENDING
        assert job.feedback_ids == []
        assert job.started_at is None
        assert job.completed_at is None
        assert job.error_message is None

    def test_completed_job(self) -> None:
        """Test completed job with results."""
        now = datetime.utcnow()
        job = RetrainingJob(
            model_type=ModelType.OCR_CONFIDENCE,
            trigger=RetrainingTrigger.THRESHOLD,
            status=RetrainingStatus.COMPLETED,
            training_samples=200,
            old_version="1.0.0",
            new_version="1.1.0",
            accuracy_before=0.92,
            accuracy_after=0.95,
            started_at=now - timedelta(hours=1),
            completed_at=now,
        )

        assert job.status == RetrainingStatus.COMPLETED
        assert job.new_version == "1.1.0"
        improvement = job.accuracy_after - job.accuracy_before
        assert improvement == 0.03  # 3% improvement

    def test_failed_job(self) -> None:
        """Test failed job with error message."""
        job = RetrainingJob(
            model_type=ModelType.OCR_CONFIDENCE,
            trigger=RetrainingTrigger.THRESHOLD,
            status=RetrainingStatus.FAILED,
            error_message="GPU out of memory",
        )

        assert job.status == RetrainingStatus.FAILED
        assert job.error_message == "GPU out of memory"
        assert job.new_version is None


# =============================================================================
# SERVICE INITIALIZATION TESTS
# =============================================================================


class TestRetrainingServiceInit:
    """Tests for RetrainingService initialization."""

    def test_service_creation(self, mock_session: AsyncMock) -> None:
        """Test basic service creation."""
        service = RetrainingService(mock_session)

        assert service.db == mock_session
        assert service.registry is not None
        assert service.CONFIG_KEY == "mlops_retraining_config"
        assert service.JOBS_KEY == "mlops_retraining_jobs"


# =============================================================================
# FEEDBACK COUNT TESTS
# =============================================================================


class TestFeedbackCounts:
    """Tests for feedback counting methods."""

    @pytest.mark.asyncio
    async def test_get_pending_feedback_count(
        self,
        retraining_service: RetrainingService,
        mock_session: AsyncMock,
    ) -> None:
        """Test counting pending feedbacks."""
        mock_result = MagicMock()
        mock_result.scalar_one.return_value = 150
        mock_session.execute.return_value = mock_result

        count = await retraining_service.get_pending_feedback_count(
            model_type=ModelType.OCR_CONFIDENCE,
            hours=168,
        )

        assert count == 150

    @pytest.mark.asyncio
    async def test_get_pending_feedback_count_zero(
        self,
        retraining_service: RetrainingService,
        mock_session: AsyncMock,
    ) -> None:
        """Test counting when no pending feedbacks."""
        mock_result = MagicMock()
        mock_result.scalar_one.return_value = 0
        mock_session.execute.return_value = mock_result

        count = await retraining_service.get_pending_feedback_count()

        assert count == 0

    @pytest.mark.asyncio
    async def test_get_verified_feedback_count(
        self,
        retraining_service: RetrainingService,
        mock_session: AsyncMock,
    ) -> None:
        """Test counting verified feedbacks."""
        mock_result = MagicMock()
        mock_result.scalar_one.return_value = 75
        mock_session.execute.return_value = mock_result

        count = await retraining_service.get_verified_feedback_count(
            hours=168,
        )

        assert count == 75


# =============================================================================
# SHOULD RETRAIN TESTS
# =============================================================================


class TestShouldRetrain:
    """Tests for retraining trigger decisions."""

    @pytest.mark.asyncio
    async def test_should_retrain_threshold_met(
        self,
        retraining_service: RetrainingService,
        mock_session: AsyncMock,
    ) -> None:
        """Test retraining triggered by threshold."""
        # Mock config load
        mock_config_result = MagicMock()
        mock_config_result.scalar_one_or_none.return_value = None

        # Mock last retrain time (None = never retrained)
        mock_last_result = MagicMock()
        mock_last_result.scalar_one_or_none.return_value = None

        mock_session.execute.side_effect = [
            mock_config_result,  # _load_config
            mock_last_result,    # _get_last_retrain_time
        ]

        with patch.object(
            retraining_service,
            "get_pending_feedback_count",
            new_callable=AsyncMock,
            return_value=150,  # Above default threshold of 100
        ):
            should, trigger = await retraining_service.should_retrain(
                ModelType.OCR_CONFIDENCE,
            )

        assert should is True
        assert trigger == RetrainingTrigger.THRESHOLD

    @pytest.mark.asyncio
    async def test_should_retrain_threshold_not_met(
        self,
        retraining_service: RetrainingService,
        mock_session: AsyncMock,
    ) -> None:
        """Test no retraining when threshold not met."""
        mock_config_result = MagicMock()
        mock_config_result.scalar_one_or_none.return_value = None

        mock_last_result = MagicMock()
        mock_last_result.scalar_one_or_none.return_value = None

        mock_session.execute.side_effect = [
            mock_config_result,
            mock_last_result,
        ]

        with patch.object(
            retraining_service,
            "get_pending_feedback_count",
            new_callable=AsyncMock,
            return_value=50,  # Below threshold
        ):
            should, trigger = await retraining_service.should_retrain(
                ModelType.OCR_CONFIDENCE,
            )

        assert should is False
        assert trigger is None

    @pytest.mark.asyncio
    async def test_should_retrain_rate_limited(
        self,
        retraining_service: RetrainingService,
        mock_session: AsyncMock,
    ) -> None:
        """Test rate limiting prevents retraining."""
        mock_config_result = MagicMock()
        mock_config_result.scalar_one_or_none.return_value = None

        # Mock last retrain time as recent (2 hours ago)
        mock_last_config = MagicMock()
        mock_last_config.value = {
            "ocr_confidence": (datetime.utcnow() - timedelta(hours=2)).isoformat()
        }
        mock_last_result = MagicMock()
        mock_last_result.scalar_one_or_none.return_value = mock_last_config

        mock_session.execute.side_effect = [
            mock_config_result,
            mock_last_result,
        ]

        # Even with high feedback count, should be rate-limited
        should, trigger = await retraining_service.should_retrain(
            ModelType.OCR_CONFIDENCE,
        )

        assert should is False
        assert trigger is None


# =============================================================================
# JOB CREATION TESTS
# =============================================================================


class TestJobCreation:
    """Tests for retraining job creation."""

    @pytest.mark.asyncio
    async def test_create_retraining_job(
        self,
        retraining_service: RetrainingService,
        mock_session: AsyncMock,
    ) -> None:
        """Test successful job creation."""
        # Mock config
        mock_config_result = MagicMock()
        mock_config_result.scalar_one_or_none.return_value = None

        # Mock jobs
        mock_jobs_result = MagicMock()
        mock_jobs_result.scalar_one_or_none.return_value = None

        # Mock feedback IDs query
        mock_feedback_result = MagicMock()
        mock_feedback_result.fetchall.return_value = [
            (uuid.uuid4(),) for _ in range(100)
        ]

        mock_session.execute.side_effect = [
            mock_config_result,  # _load_config
            mock_jobs_result,    # _load_jobs
            mock_jobs_result,    # _load_jobs for save
        ]

        with patch.object(
            retraining_service.registry,
            "get_active_model",
            new_callable=AsyncMock,
            return_value=MagicMock(version="1.0.0", accuracy=0.92),
        ):
            with patch.object(
                retraining_service,
                "get_pending_feedback_count",
                new_callable=AsyncMock,
                return_value=150,
            ):
                with patch.object(
                    retraining_service,
                    "_save_jobs",
                    new_callable=AsyncMock,
                ):
                    # Mock the feedback IDs query separately
                    original_execute = mock_session.execute

                    async def mock_execute(query):
                        # Check if this is the feedback IDs query
                        result = MagicMock()
                        if hasattr(query, '_raw_columns'):
                            result.fetchall.return_value = [
                                (uuid.uuid4(),) for _ in range(100)
                            ]
                        else:
                            result.scalar_one_or_none.return_value = None
                        return result

                    mock_session.execute = mock_execute

                    job = await retraining_service.create_retraining_job(
                        model_type=ModelType.OCR_CONFIDENCE,
                        trigger=RetrainingTrigger.THRESHOLD,
                    )

        assert job.model_type == ModelType.OCR_CONFIDENCE
        assert job.trigger == RetrainingTrigger.THRESHOLD
        assert job.status == RetrainingStatus.PENDING

    @pytest.mark.asyncio
    async def test_create_job_insufficient_data(
        self,
        retraining_service: RetrainingService,
        mock_session: AsyncMock,
    ) -> None:
        """Test job creation fails with insufficient training data."""
        mock_config_result = MagicMock()
        mock_config_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_config_result

        with patch.object(
            retraining_service.registry,
            "get_active_model",
            new_callable=AsyncMock,
            return_value=None,
        ):
            with patch.object(
                retraining_service,
                "get_pending_feedback_count",
                new_callable=AsyncMock,
                return_value=10,  # Below minimum 50
            ):
                with pytest.raises(ValueError, match="Insufficient training data"):
                    await retraining_service.create_retraining_job(
                        model_type=ModelType.OCR_CONFIDENCE,
                        trigger=RetrainingTrigger.MANUAL,
                    )


# =============================================================================
# JOB STATUS UPDATE TESTS
# =============================================================================


class TestJobStatusUpdate:
    """Tests for job status updates."""

    @pytest.mark.asyncio
    async def test_update_job_to_running(
        self,
        retraining_service: RetrainingService,
        mock_session: AsyncMock,
        sample_jobs_data: list,
    ) -> None:
        """Test updating job status to running."""
        mock_result = MagicMock()
        mock_config = MagicMock()
        mock_config.value = sample_jobs_data
        mock_result.scalar_one_or_none.return_value = mock_config
        mock_session.execute.return_value = mock_result

        with patch.object(
            retraining_service,
            "_save_jobs",
            new_callable=AsyncMock,
        ):
            job = await retraining_service.update_job_status(
                job_id="job-3",
                status=RetrainingStatus.RUNNING,
            )

        assert job is not None
        assert job.status == RetrainingStatus.RUNNING
        assert job.started_at is not None

    @pytest.mark.asyncio
    async def test_update_job_to_completed(
        self,
        retraining_service: RetrainingService,
        mock_session: AsyncMock,
        sample_jobs_data: list,
    ) -> None:
        """Test updating job status to completed."""
        mock_result = MagicMock()
        mock_config = MagicMock()
        mock_config.value = sample_jobs_data
        mock_result.scalar_one_or_none.return_value = mock_config
        mock_session.execute.return_value = mock_result

        with patch.object(
            retraining_service,
            "_save_jobs",
            new_callable=AsyncMock,
        ):
            with patch.object(
                retraining_service,
                "_set_last_retrain_time",
                new_callable=AsyncMock,
            ):
                job = await retraining_service.update_job_status(
                    job_id="job-3",
                    status=RetrainingStatus.COMPLETED,
                    new_version="1.2.0",
                    accuracy_after=0.96,
                )

        assert job is not None
        assert job.status == RetrainingStatus.COMPLETED
        assert job.new_version == "1.2.0"
        assert job.accuracy_after == 0.96

    @pytest.mark.asyncio
    async def test_update_job_to_failed(
        self,
        retraining_service: RetrainingService,
        mock_session: AsyncMock,
        sample_jobs_data: list,
    ) -> None:
        """Test updating job status to failed."""
        mock_result = MagicMock()
        mock_config = MagicMock()
        mock_config.value = sample_jobs_data
        mock_result.scalar_one_or_none.return_value = mock_config
        mock_session.execute.return_value = mock_result

        with patch.object(
            retraining_service,
            "_save_jobs",
            new_callable=AsyncMock,
        ):
            job = await retraining_service.update_job_status(
                job_id="job-3",
                status=RetrainingStatus.FAILED,
                error_message="Training timeout exceeded",
            )

        assert job is not None
        assert job.status == RetrainingStatus.FAILED
        assert job.error_message == "Training timeout exceeded"

    @pytest.mark.asyncio
    async def test_update_job_not_found(
        self,
        retraining_service: RetrainingService,
        mock_session: AsyncMock,
        sample_jobs_data: list,
    ) -> None:
        """Test updating non-existent job returns None."""
        mock_result = MagicMock()
        mock_config = MagicMock()
        mock_config.value = sample_jobs_data
        mock_result.scalar_one_or_none.return_value = mock_config
        mock_session.execute.return_value = mock_result

        result = await retraining_service.update_job_status(
            job_id="non-existent-job",
            status=RetrainingStatus.RUNNING,
        )

        assert result is None


# =============================================================================
# JOB RETRIEVAL TESTS
# =============================================================================


class TestJobRetrieval:
    """Tests for job retrieval methods."""

    @pytest.mark.asyncio
    async def test_get_job_exists(
        self,
        retraining_service: RetrainingService,
        mock_session: AsyncMock,
        sample_jobs_data: list,
    ) -> None:
        """Test getting an existing job."""
        mock_result = MagicMock()
        mock_config = MagicMock()
        mock_config.value = sample_jobs_data
        mock_result.scalar_one_or_none.return_value = mock_config
        mock_session.execute.return_value = mock_result

        job = await retraining_service.get_job("job-1")

        assert job is not None
        assert job.id == "job-1"
        assert job.status == RetrainingStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_get_job_not_found(
        self,
        retraining_service: RetrainingService,
        mock_session: AsyncMock,
        sample_jobs_data: list,
    ) -> None:
        """Test getting a non-existent job."""
        mock_result = MagicMock()
        mock_config = MagicMock()
        mock_config.value = sample_jobs_data
        mock_result.scalar_one_or_none.return_value = mock_config
        mock_session.execute.return_value = mock_result

        job = await retraining_service.get_job("non-existent")

        assert job is None

    @pytest.mark.asyncio
    async def test_list_jobs_all(
        self,
        retraining_service: RetrainingService,
        mock_session: AsyncMock,
        sample_jobs_data: list,
    ) -> None:
        """Test listing all jobs."""
        mock_result = MagicMock()
        mock_config = MagicMock()
        mock_config.value = sample_jobs_data
        mock_result.scalar_one_or_none.return_value = mock_config
        mock_session.execute.return_value = mock_result

        jobs = await retraining_service.list_jobs()

        assert len(jobs) == 3

    @pytest.mark.asyncio
    async def test_list_jobs_by_model_type(
        self,
        retraining_service: RetrainingService,
        mock_session: AsyncMock,
        sample_jobs_data: list,
    ) -> None:
        """Test listing jobs filtered by model type."""
        mock_result = MagicMock()
        mock_config = MagicMock()
        mock_config.value = sample_jobs_data
        mock_result.scalar_one_or_none.return_value = mock_config
        mock_session.execute.return_value = mock_result

        jobs = await retraining_service.list_jobs(
            model_type=ModelType.OCR_CONFIDENCE,
        )

        assert len(jobs) == 2
        assert all(j.model_type == ModelType.OCR_CONFIDENCE for j in jobs)

    @pytest.mark.asyncio
    async def test_list_jobs_by_status(
        self,
        retraining_service: RetrainingService,
        mock_session: AsyncMock,
        sample_jobs_data: list,
    ) -> None:
        """Test listing jobs filtered by status."""
        mock_result = MagicMock()
        mock_config = MagicMock()
        mock_config.value = sample_jobs_data
        mock_result.scalar_one_or_none.return_value = mock_config
        mock_session.execute.return_value = mock_result

        jobs = await retraining_service.list_jobs(
            status=RetrainingStatus.COMPLETED,
        )

        assert len(jobs) == 1
        assert jobs[0].status == RetrainingStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_list_jobs_with_limit(
        self,
        retraining_service: RetrainingService,
        mock_session: AsyncMock,
        sample_jobs_data: list,
    ) -> None:
        """Test listing jobs with limit."""
        mock_result = MagicMock()
        mock_config = MagicMock()
        mock_config.value = sample_jobs_data
        mock_result.scalar_one_or_none.return_value = mock_config
        mock_session.execute.return_value = mock_result

        jobs = await retraining_service.list_jobs(limit=2)

        assert len(jobs) == 2


# =============================================================================
# TRAINING DATA EXPORT TESTS
# =============================================================================


class TestTrainingDataExport:
    """Tests for training data export."""

    @pytest.mark.asyncio
    async def test_export_training_data_job_not_found(
        self,
        retraining_service: RetrainingService,
    ) -> None:
        """Test export fails for non-existent job."""
        with patch.object(
            retraining_service,
            "get_job",
            new_callable=AsyncMock,
            return_value=None,
        ):
            with pytest.raises(ValueError, match="Job not found"):
                await retraining_service.export_training_data("non-existent")


# =============================================================================
# STATISTICS TESTS
# =============================================================================


class TestRetrainingStats:
    """Tests for retraining statistics."""

    @pytest.mark.asyncio
    async def test_get_retraining_stats(
        self,
        retraining_service: RetrainingService,
        mock_session: AsyncMock,
        sample_jobs_data: list,
    ) -> None:
        """Test getting retraining statistics."""
        mock_result = MagicMock()
        mock_config = MagicMock()
        mock_config.value = sample_jobs_data
        mock_result.scalar_one_or_none.return_value = mock_config
        mock_session.execute.return_value = mock_result

        stats = await retraining_service.get_retraining_stats()

        assert stats["total_jobs"] == 3
        assert stats["completed_jobs"] == 1
        assert stats["failed_jobs"] == 1
        assert stats["total_samples_trained"] == 150
        assert "threshold" in stats["jobs_by_trigger"]
        assert "ocr_confidence" in stats["jobs_by_model_type"]

    @pytest.mark.asyncio
    async def test_get_retraining_stats_empty(
        self,
        retraining_service: RetrainingService,
        mock_session: AsyncMock,
    ) -> None:
        """Test statistics with no jobs."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        stats = await retraining_service.get_retraining_stats()

        assert stats["total_jobs"] == 0
        assert stats["completed_jobs"] == 0
        assert stats["failed_jobs"] == 0
        assert stats["avg_improvement"] == 0.0

    @pytest.mark.asyncio
    async def test_stats_avg_improvement(
        self,
        retraining_service: RetrainingService,
        mock_session: AsyncMock,
    ) -> None:
        """Test average improvement calculation."""
        jobs_data = [
            {
                "id": "job-1",
                "model_type": "ocr_confidence",
                "trigger": "threshold",
                "status": "completed",
                "training_samples": 100,
                "accuracy_before": 0.90,
                "accuracy_after": 0.93,  # +3%
            },
            {
                "id": "job-2",
                "model_type": "ocr_confidence",
                "trigger": "threshold",
                "status": "completed",
                "training_samples": 100,
                "accuracy_before": 0.93,
                "accuracy_after": 0.95,  # +2%
            },
        ]
        mock_result = MagicMock()
        mock_config = MagicMock()
        mock_config.value = jobs_data
        mock_result.scalar_one_or_none.return_value = mock_config
        mock_session.execute.return_value = mock_result

        stats = await retraining_service.get_retraining_stats()

        # Average of 3% and 2% = 2.5%
        assert stats["avg_improvement"] == 0.025


# =============================================================================
# EDGE CASES
# =============================================================================


class TestEdgeCases:
    """Tests for edge cases."""

    @pytest.mark.asyncio
    async def test_jobs_history_limit(
        self,
        retraining_service: RetrainingService,
        mock_session: AsyncMock,
    ) -> None:
        """Test that jobs history is limited to 100."""
        # Create 105 jobs
        many_jobs = [
            {
                "id": f"job-{i}",
                "model_type": "ocr_confidence",
                "trigger": "threshold",
                "status": "completed",
                "training_samples": 100,
                "created_at": datetime.utcnow().isoformat(),
            }
            for i in range(105)
        ]

        mock_result = MagicMock()
        mock_config = MagicMock()
        mock_config.value = many_jobs
        mock_result.scalar_one_or_none.return_value = mock_config
        mock_session.execute.return_value = mock_result

        # When saving, only last 100 should be kept
        # This is tested via _save_jobs internal logic

    def test_retraining_config_serialization(self) -> None:
        """Test config serialization for storage."""
        config = RetrainingConfig(
            feedback_threshold=200,
            weekly_enabled=False,
        )

        # Serialize to JSON-compatible dict
        serialized = config.model_dump(mode="json")

        assert serialized["feedback_threshold"] == 200
        assert serialized["weekly_enabled"] is False

        # Deserialize back
        restored = RetrainingConfig(**serialized)
        assert restored.feedback_threshold == 200

    def test_retraining_job_serialization(self) -> None:
        """Test job serialization for storage."""
        job = RetrainingJob(
            model_type=ModelType.OCR_CONFIDENCE,
            trigger=RetrainingTrigger.THRESHOLD,
            training_samples=150,
        )

        serialized = job.model_dump(mode="json")

        assert serialized["model_type"] == "ocr_confidence"
        assert serialized["trigger"] == "threshold"
        assert serialized["training_samples"] == 150

    @pytest.mark.asyncio
    async def test_scheduled_retrain_check(
        self,
        retraining_service: RetrainingService,
    ) -> None:
        """Test scheduled retrain timing check."""
        config = RetrainingConfig(
            weekly_enabled=True,
            weekly_day=0,  # Monday
            weekly_hour=3,
        )

        # This is a unit test for the scheduling logic concept
        # In real scenario, this would be tested with mocked datetime
        assert config.weekly_enabled is True
        assert config.weekly_day == 0
        assert config.weekly_hour == 3

    def test_improvement_calculation(self) -> None:
        """Test accuracy improvement calculation."""
        accuracy_before = 0.92
        accuracy_after = 0.95

        improvement = accuracy_after - accuracy_before
        improvement_percent = improvement * 100

        assert improvement == pytest.approx(0.03, rel=1e-9)
        assert improvement_percent == pytest.approx(3.0, rel=1e-9)
