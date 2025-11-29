"""
Tests for Admin Jobs API endpoints.

Tests job management functionality:
- List jobs with filtering
- Get job details
- Cancel jobs
- Retry failed jobs
- Clear queue
- Batch operations
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from app.db.models import User
from app.db.schemas import (
    UserRole,
    ProcessingStatus,
    MessageResponse,
)


@pytest.fixture
def mock_db():
    """Mock database session."""
    return AsyncMock()


@pytest.fixture
def admin_user():
    """Create admin user for testing."""
    from unittest.mock import Mock
    user = Mock(spec=User)
    user.id = str(uuid4())
    user.email = "admin@test.de"
    user.username = "admin"
    user.is_active = True
    user.is_superuser = True
    user.tier = "enterprise"
    user.created_at = datetime.utcnow()
    return user


@pytest.fixture
def sample_job():
    """Create sample job for testing."""
    return {
        "id": str(uuid4()),
        "task_id": f"celery-task-{uuid4()}",
        "status": ProcessingStatus.PENDING,
        "queue": "ocr",
        "document_id": str(uuid4()),
        "user_id": str(uuid4()),
        "created_at": datetime.utcnow(),
        "started_at": None,
        "completed_at": None,
        "error": None,
    }


class TestListJobs:
    """Tests for GET /admin/jobs endpoint."""

    @pytest.mark.asyncio
    async def test_list_jobs_success(self, mock_db, admin_user, sample_job):
        """Jobs erfolgreich auflisten."""
        from app.services.admin import JobAdminService

        service = JobAdminService()

        with patch.object(service, "list_jobs", return_value=[sample_job]):
            result = await service.list_jobs(db=mock_db, page=1, page_size=10)
            assert len(result) == 1
            assert result[0]["status"] == ProcessingStatus.PENDING

    @pytest.mark.asyncio
    async def test_list_jobs_by_status(self, mock_db, admin_user, sample_job):
        """Jobs nach Status filtern."""
        from app.services.admin import JobAdminService

        service = JobAdminService()

        with patch.object(service, "list_jobs", return_value=[sample_job]):
            result = await service.list_jobs(
                db=mock_db,
                page=1,
                page_size=10,
                status=ProcessingStatus.PENDING,
            )
            assert all(j["status"] == ProcessingStatus.PENDING for j in result)

    @pytest.mark.asyncio
    async def test_list_jobs_by_queue(self, mock_db, admin_user, sample_job):
        """Jobs nach Queue filtern."""
        from app.services.admin import JobAdminService

        service = JobAdminService()

        with patch.object(service, "list_jobs", return_value=[sample_job]):
            result = await service.list_jobs(
                db=mock_db,
                page=1,
                page_size=10,
                queue="ocr",
            )
            assert all(j["queue"] == "ocr" for j in result)

    @pytest.mark.asyncio
    async def test_list_jobs_by_user(self, mock_db, admin_user, sample_job):
        """Jobs nach Benutzer filtern."""
        from app.services.admin import JobAdminService

        service = JobAdminService()
        user_id = sample_job["user_id"]

        with patch.object(service, "list_jobs", return_value=[sample_job]):
            result = await service.list_jobs(
                db=mock_db,
                page=1,
                page_size=10,
                user_id=user_id,
            )
            assert all(j["user_id"] == user_id for j in result)


class TestGetJob:
    """Tests for GET /admin/jobs/{job_id} endpoint."""

    @pytest.mark.asyncio
    async def test_get_job_success(self, mock_db, admin_user, sample_job):
        """Job-Details erfolgreich abrufen."""
        from app.services.admin import JobAdminService

        service = JobAdminService()

        with patch.object(service, "get_job", return_value=sample_job):
            result = await service.get_job(db=mock_db, job_id=sample_job["id"])
            assert result["id"] == sample_job["id"]

    @pytest.mark.asyncio
    async def test_get_job_not_found(self, mock_db, admin_user):
        """Nicht existierenden Job abrufen."""
        from app.services.admin import JobAdminService

        service = JobAdminService()

        with patch.object(service, "get_job", return_value=None):
            result = await service.get_job(db=mock_db, job_id="nonexistent")
            assert result is None


class TestCancelJob:
    """Tests for POST /admin/jobs/{job_id}/cancel endpoint."""

    @pytest.mark.asyncio
    async def test_cancel_job_success(self, mock_db, admin_user, sample_job):
        """Job erfolgreich abbrechen."""
        from app.services.admin import JobAdminService

        service = JobAdminService()

        with patch.object(service, "cancel_job", return_value=True):
            result = await service.cancel_job(
                db=mock_db,
                job_id=sample_job["id"],
                cancelled_by=admin_user.id,
            )
            assert result is True

    @pytest.mark.asyncio
    async def test_cancel_completed_job(self, mock_db, admin_user, sample_job):
        """Bereits abgeschlossenen Job abbrechen."""
        from app.services.admin import JobAdminService
        from fastapi import HTTPException, status

        service = JobAdminService()
        sample_job["status"] = ProcessingStatus.COMPLETED

        with patch.object(
            service,
            "cancel_job",
            side_effect=HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Abgeschlossene Jobs können nicht abgebrochen werden",
            ),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await service.cancel_job(
                    db=mock_db,
                    job_id=sample_job["id"],
                    cancelled_by=admin_user.id,
                )
            assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST


class TestRetryJob:
    """Tests for POST /admin/jobs/{job_id}/retry endpoint."""

    @pytest.mark.asyncio
    async def test_retry_job_success(self, mock_db, admin_user, sample_job):
        """Fehlgeschlagenen Job erneut versuchen."""
        from app.services.admin import JobAdminService

        service = JobAdminService()
        sample_job["status"] = ProcessingStatus.FAILED
        new_job_id = str(uuid4())

        with patch.object(service, "retry_job", return_value=new_job_id):
            result = await service.retry_job(
                db=mock_db,
                job_id=sample_job["id"],
                retried_by=admin_user.id,
            )
            assert result == new_job_id

    @pytest.mark.asyncio
    async def test_retry_running_job(self, mock_db, admin_user, sample_job):
        """Laufenden Job erneut versuchen (sollte fehlschlagen)."""
        from app.services.admin import JobAdminService
        from fastapi import HTTPException, status

        service = JobAdminService()
        sample_job["status"] = ProcessingStatus.PROCESSING

        with patch.object(
            service,
            "retry_job",
            side_effect=HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Nur fehlgeschlagene Jobs können erneut versucht werden",
            ),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await service.retry_job(
                    db=mock_db,
                    job_id=sample_job["id"],
                    retried_by=admin_user.id,
                )
            assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST


class TestClearQueue:
    """Tests for POST /admin/jobs/queue/clear endpoint."""

    @pytest.mark.asyncio
    async def test_clear_queue_all(self, mock_db, admin_user):
        """Alle Queues leeren."""
        from app.services.admin import JobAdminService

        service = JobAdminService()

        with patch.object(
            service,
            "clear_queue",
            return_value={"cleared": 25, "queues": ["default", "ocr", "high_priority"]},
        ):
            result = await service.clear_queue(
                cleared_by=admin_user.id,
            )
            assert result["cleared"] == 25

    @pytest.mark.asyncio
    async def test_clear_queue_specific(self, mock_db, admin_user):
        """Bestimmte Queue leeren."""
        from app.services.admin import JobAdminService

        service = JobAdminService()

        with patch.object(
            service,
            "clear_queue",
            return_value={"cleared": 10, "queues": ["ocr"]},
        ):
            result = await service.clear_queue(
                queue="ocr",
                cleared_by=admin_user.id,
            )
            assert result["cleared"] == 10
            assert result["queues"] == ["ocr"]


class TestBatchOperations:
    """Tests for batch job operations."""

    @pytest.mark.asyncio
    async def test_batch_cancel(self, mock_db, admin_user):
        """Mehrere Jobs abbrechen."""
        from app.services.admin import JobAdminService

        service = JobAdminService()
        job_ids = [str(uuid4()), str(uuid4()), str(uuid4())]

        with patch.object(
            service,
            "batch_cancel",
            return_value={"cancelled": 3, "failed": 0},
        ):
            result = await service.batch_cancel(
                db=mock_db,
                job_ids=job_ids,
                cancelled_by=admin_user.id,
            )
            assert result["cancelled"] == 3

    @pytest.mark.asyncio
    async def test_batch_retry(self, mock_db, admin_user):
        """Mehrere fehlgeschlagene Jobs erneut versuchen."""
        from app.services.admin import JobAdminService

        service = JobAdminService()
        job_ids = [str(uuid4()), str(uuid4())]

        with patch.object(
            service,
            "batch_retry",
            return_value={"retried": 2, "new_job_ids": [str(uuid4()), str(uuid4())]},
        ):
            result = await service.batch_retry(
                db=mock_db,
                job_ids=job_ids,
                retried_by=admin_user.id,
            )
            assert result["retried"] == 2


class TestJobStatistics:
    """Tests for job statistics endpoint."""

    @pytest.mark.asyncio
    async def test_get_job_stats(self, mock_db, admin_user):
        """Job-Statistiken abrufen."""
        from app.services.admin import JobAdminService

        service = JobAdminService()

        mock_stats = {
            "total_jobs": 1500,
            "by_status": {
                "pending": 25,
                "running": 5,
                "completed": 1400,
                "failed": 70,
            },
            "by_queue": {
                "default": 500,
                "ocr": 900,
                "high_priority": 100,
            },
            "average_duration_seconds": 45.5,
            "success_rate_percent": 95.2,
            "last_24h": {
                "processed": 120,
                "failed": 5,
            },
        }

        with patch.object(service, "get_statistics", return_value=mock_stats):
            result = await service.get_statistics(db=mock_db)
            assert result["total_jobs"] == 1500
            assert result["success_rate_percent"] == 95.2
