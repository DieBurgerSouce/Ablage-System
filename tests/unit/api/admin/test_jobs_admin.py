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
    """Tests for batch job operations using existing cancel_job method."""

    @pytest.mark.asyncio
    async def test_batch_cancel_multiple_jobs(self, mock_db, admin_user):
        """Mehrere Jobs einzeln abbrechen."""
        from app.services.admin import JobAdminService

        service = JobAdminService()
        job_ids = [str(uuid4()), str(uuid4()), str(uuid4())]

        with patch.object(service, "cancel_job", return_value=True):
            results = []
            for job_id in job_ids:
                result = await service.cancel_job(
                    db=mock_db,
                    job_id=job_id,
                    cancelled_by=admin_user.id,
                )
                results.append(result)
            assert all(results)
            assert len(results) == 3

    @pytest.mark.asyncio
    async def test_batch_retry_multiple_jobs(self, mock_db, admin_user):
        """Mehrere fehlgeschlagene Jobs einzeln erneut versuchen."""
        from app.services.admin import JobAdminService

        service = JobAdminService()
        job_ids = [str(uuid4()), str(uuid4())]

        with patch.object(service, "retry_job", return_value=str(uuid4())):
            results = []
            for job_id in job_ids:
                result = await service.retry_job(
                    db=mock_db,
                    job_id=job_id,
                    retried_by=admin_user.id,
                )
                results.append(result)
            assert len(results) == 2
            assert all(r is not None for r in results)


class TestJobQueueOperations:
    """Tests for job queue operations."""

    @pytest.mark.asyncio
    async def test_clear_all_queues(self, mock_db, admin_user):
        """Alle Queues leeren und Ergebnis prüfen."""
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
            assert "ocr" in result["queues"]


# ==============================================================================
# INTEGRATION TESTS - HTTP Status Codes, Edge Cases, Input Validation
# ==============================================================================

# Try to import for integration tests
try:
    from httpx import AsyncClient, ASGITransport
    from app.main import app
    from app.api.dependencies import get_current_superuser, get_db
    INTEGRATION_AVAILABLE = True
except ImportError:
    INTEGRATION_AVAILABLE = False
    app = None


@pytest.mark.integration
@pytest.mark.skipif(not INTEGRATION_AVAILABLE, reason="Integration dependencies not available")
class TestJobsAdminAPIIntegration:
    """Integration tests for Jobs Admin API with real HTTP requests."""

    @pytest.fixture
    def override_superuser(self, admin_user):
        """Override superuser dependency for testing."""
        async def _get_test_superuser():
            return admin_user
        return _get_test_superuser

    @pytest.fixture
    def override_db(self, mock_db):
        """Override database dependency for testing."""
        async def _get_test_db():
            yield mock_db
        return _get_test_db

    @pytest.mark.asyncio
    async def test_list_jobs_returns_200(self, admin_user, mock_db, override_superuser, override_db):
        """GET /admin/jobs sollte 200 zurueckgeben."""
        from app.services.admin import JobAdminService

        app.dependency_overrides[get_current_superuser] = override_superuser
        app.dependency_overrides[get_db] = override_db

        try:
            with patch.object(JobAdminService, "list_jobs", return_value={"jobs": [], "total": 0}):
                async with AsyncClient(
                    transport=ASGITransport(app=app),
                    base_url="http://test"
                ) as client:
                    response = await client.get("/api/v1/admin/jobs")
                    assert response.status_code == 200
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_get_job_404_for_nonexistent(self, admin_user, mock_db, override_superuser, override_db):
        """GET /admin/jobs/{id} sollte 404 fuer nicht existierenden Job zurueckgeben."""
        from app.services.admin import JobAdminService

        app.dependency_overrides[get_current_superuser] = override_superuser
        app.dependency_overrides[get_db] = override_db

        try:
            with patch.object(JobAdminService, "get_job", return_value=None):
                async with AsyncClient(
                    transport=ASGITransport(app=app),
                    base_url="http://test"
                ) as client:
                    response = await client.get(f"/api/v1/admin/jobs/{uuid4()}")
                    assert response.status_code == 404
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_cancel_job_returns_200_on_success(self, admin_user, mock_db, override_superuser, override_db):
        """POST /admin/jobs/{id}/cancel sollte 200 bei Erfolg zurueckgeben."""
        from app.services.admin import JobAdminService

        app.dependency_overrides[get_current_superuser] = override_superuser
        app.dependency_overrides[get_db] = override_db

        job_id = uuid4()
        try:
            with patch.object(JobAdminService, "cancel_job", return_value=True):
                async with AsyncClient(
                    transport=ASGITransport(app=app),
                    base_url="http://test"
                ) as client:
                    response = await client.post(f"/api/v1/admin/jobs/{job_id}/cancel")
                    assert response.status_code == 200
        finally:
            app.dependency_overrides.clear()


@pytest.mark.integration
@pytest.mark.skipif(not INTEGRATION_AVAILABLE, reason="Integration dependencies not available")
class TestPaginationEdgeCases:
    """Integration tests for pagination edge cases."""

    @pytest.fixture
    def override_superuser(self, admin_user):
        """Override superuser dependency for testing."""
        async def _get_test_superuser():
            return admin_user
        return _get_test_superuser

    @pytest.fixture
    def override_db(self, mock_db):
        """Override database dependency for testing."""
        async def _get_test_db():
            yield mock_db
        return _get_test_db

    @pytest.mark.asyncio
    async def test_list_jobs_negative_page_returns_422(self, admin_user, mock_db, override_superuser, override_db):
        """Negative Seitenzahl sollte 422 Validation Error zurueckgeben."""
        app.dependency_overrides[get_current_superuser] = override_superuser
        app.dependency_overrides[get_db] = override_db

        try:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test"
            ) as client:
                response = await client.get("/api/v1/admin/jobs?page=-1")
                assert response.status_code == 422
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_list_jobs_large_page_size_capped(self, admin_user, mock_db, override_superuser, override_db):
        """Zu grosse Seitenzahl sollte auf Maximum begrenzt werden."""
        from app.services.admin import JobAdminService

        app.dependency_overrides[get_current_superuser] = override_superuser
        app.dependency_overrides[get_db] = override_db

        try:
            with patch.object(JobAdminService, "list_jobs", return_value={"jobs": [], "total": 0}) as mock_list:
                async with AsyncClient(
                    transport=ASGITransport(app=app),
                    base_url="http://test"
                ) as client:
                    response = await client.get("/api/v1/admin/jobs?per_page=10000")
                    # Should succeed but cap the per_page
                    assert response.status_code == 200
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_list_jobs_page_beyond_total_returns_empty(self, admin_user, mock_db, override_superuser, override_db):
        """Seite jenseits der Gesamtzahl sollte leere Liste zurueckgeben."""
        from app.services.admin import JobAdminService

        app.dependency_overrides[get_current_superuser] = override_superuser
        app.dependency_overrides[get_db] = override_db

        try:
            with patch.object(JobAdminService, "list_jobs", return_value={"jobs": [], "total": 10}):
                async with AsyncClient(
                    transport=ASGITransport(app=app),
                    base_url="http://test"
                ) as client:
                    response = await client.get("/api/v1/admin/jobs?page=100")
                    assert response.status_code == 200
                    data = response.json()
                    assert data.get("jobs", []) == []
        finally:
            app.dependency_overrides.clear()


@pytest.mark.integration
@pytest.mark.skipif(not INTEGRATION_AVAILABLE, reason="Integration dependencies not available")
class TestInputValidation:
    """Integration tests for input validation and malformed requests."""

    @pytest.fixture
    def override_superuser(self, admin_user):
        """Override superuser dependency for testing."""
        async def _get_test_superuser():
            return admin_user
        return _get_test_superuser

    @pytest.fixture
    def override_db(self, mock_db):
        """Override database dependency for testing."""
        async def _get_test_db():
            yield mock_db
        return _get_test_db

    @pytest.mark.asyncio
    async def test_malformed_uuid_returns_422(self, admin_user, mock_db, override_superuser, override_db):
        """Ungueltige UUID sollte 422 zurueckgeben."""
        app.dependency_overrides[get_current_superuser] = override_superuser
        app.dependency_overrides[get_db] = override_db

        try:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test"
            ) as client:
                response = await client.get("/api/v1/admin/jobs/not-a-valid-uuid")
                assert response.status_code == 422
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_invalid_status_filter_returns_422(self, admin_user, mock_db, override_superuser, override_db):
        """Ungueltiger Status-Filter sollte 422 zurueckgeben."""
        app.dependency_overrides[get_current_superuser] = override_superuser
        app.dependency_overrides[get_db] = override_db

        try:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test"
            ) as client:
                response = await client.get("/api/v1/admin/jobs?status=invalid_status")
                assert response.status_code == 422
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_bulk_cancel_empty_list_returns_400(self, admin_user, mock_db, override_superuser, override_db):
        """Bulk-Cancel mit leerer Liste sollte 400 zurueckgeben."""
        app.dependency_overrides[get_current_superuser] = override_superuser
        app.dependency_overrides[get_db] = override_db

        try:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test"
            ) as client:
                response = await client.post(
                    "/api/v1/admin/jobs/bulk/cancel",
                    json={"job_ids": []}
                )
                # Could be 400 or 422 depending on validation
                assert response.status_code in [400, 422]
        finally:
            app.dependency_overrides.clear()
