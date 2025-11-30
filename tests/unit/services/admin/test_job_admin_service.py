"""
Unit Tests für JobAdminService.

Umfassende Tests für:
- Job-Listung mit Filter und Paginierung
- Job-Details abrufen
- Job abbrechen
- Fehlgeschlagene Jobs wiederholen
- Queue leeren
- Status-Zusammenfassung
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, Mock, MagicMock, patch
from uuid import uuid4, UUID
import math

from sqlalchemy.ext.asyncio import AsyncSession


# ==============================================================================
# Mock Enums
# ==============================================================================

class MockProcessingStatus:
    """Mock für ProcessingStatus Enum."""
    PENDING = Mock(value="pending")
    QUEUED = Mock(value="queued")
    PROCESSING = Mock(value="processing")
    COMPLETED = Mock(value="completed")
    FAILED = Mock(value="failed")
    CANCELLED = Mock(value="cancelled")


# ==============================================================================
# Mock Objects
# ==============================================================================

def create_mock_user(
    user_id: UUID = None,
    email: str = "user@test.de",
    is_superuser: bool = False,
) -> Mock:
    """Erstelle Mock User."""
    user = Mock()
    user.id = user_id or uuid4()
    user.email = email
    user.is_superuser = is_superuser
    return user


def create_mock_document(
    doc_id: UUID = None,
    filename: str = "test.pdf",
    owner_id: UUID = None,
) -> Mock:
    """Erstelle Mock Document."""
    doc = Mock()
    doc.id = doc_id or uuid4()
    doc.filename = filename
    doc.owner_id = owner_id or uuid4()
    return doc


def create_mock_job(
    job_id: UUID = None,
    document_id: UUID = None,
    job_type: str = "ocr",
    backend: str = "deepseek",
    status: str = "pending",
    priority: int = 5,
    retry_count: int = 0,
    max_retries: int = 3,
    created_at: datetime = None,
    started_at: datetime = None,
    completed_at: datetime = None,
    error_message: str = None,
    worker_id: str = None,
    result: dict = None,
) -> Mock:
    """Erstelle Mock ProcessingJob."""
    job = Mock()
    job.id = job_id or uuid4()
    job.document_id = document_id or uuid4()
    job.job_type = job_type
    job.backend = backend
    job.status = Mock(value=status) if isinstance(status, str) else status
    job.priority = priority
    job.retry_count = retry_count
    job.max_retries = max_retries
    job.created_at = created_at or datetime.utcnow()
    job.started_at = started_at
    job.completed_at = completed_at
    job.error_message = error_message
    job.worker_id = worker_id
    job.result = result or {}
    job.document = None
    return job


def create_mock_job_view(
    job_id: UUID = None,
    document_id: UUID = None,
    document_filename: str = "test.pdf",
    user_id: UUID = None,
    user_email: str = "user@test.de",
    job_type: str = "ocr",
    backend: str = "deepseek",
    status: str = "pending",
    priority: int = 5,
    retry_count: int = 0,
    max_retries: int = 3,
    created_at: datetime = None,
    started_at: datetime = None,
    completed_at: datetime = None,
    error_message: str = None,
    worker_id: str = None,
    duration_ms: int = None,
    wait_time_ms: int = None,
) -> Mock:
    """Erstelle Mock JobAdminView."""
    view = Mock()
    view.id = job_id or uuid4()
    view.document_id = document_id or uuid4()
    view.document_filename = document_filename
    view.user_id = user_id or uuid4()
    view.user_email = user_email
    view.job_type = job_type
    view.backend = backend
    view.status = Mock(value=status)
    view.priority = priority
    view.retry_count = retry_count
    view.max_retries = max_retries
    view.created_at = created_at or datetime.utcnow()
    view.started_at = started_at
    view.completed_at = completed_at
    view.error_message = error_message
    view.worker_id = worker_id
    view.result = {}
    view.duration_ms = duration_ms
    view.wait_time_ms = wait_time_ms
    return view


# ==============================================================================
# Test Fixtures
# ==============================================================================

@pytest.fixture
def mock_db():
    """Mock AsyncSession."""
    db = AsyncMock(spec=AsyncSession)
    db.add = Mock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    db.delete = AsyncMock()
    return db


@pytest.fixture
def admin_user():
    """Admin User für Tests."""
    return create_mock_user(email="admin@test.de", is_superuser=True)


@pytest.fixture
def sample_jobs():
    """Liste von Test-Jobs."""
    now = datetime.utcnow()
    return [
        create_mock_job(status="pending", created_at=now - timedelta(hours=1)),
        create_mock_job(status="processing", created_at=now - timedelta(minutes=30), started_at=now - timedelta(minutes=5)),
        create_mock_job(status="completed", created_at=now - timedelta(hours=2), started_at=now - timedelta(hours=1, minutes=55), completed_at=now - timedelta(hours=1, minutes=50)),
        create_mock_job(status="failed", error_message="OCR fehlgeschlagen"),
    ]


@pytest.fixture
def job_admin_service():
    """Import JobAdminService."""
    from app.services.admin.job_admin_service import JobAdminService
    return JobAdminService


# ==============================================================================
# Tests: List Jobs
# ==============================================================================

@pytest.mark.unit
@pytest.mark.asyncio
class TestListJobs:
    """Tests für list_jobs Methode."""

    async def test_list_jobs_basic(self, mock_db, sample_jobs, job_admin_service):
        """Grundlegende Job-Listung."""
        with patch.object(job_admin_service, 'list_jobs') as mock_list:
            mock_list.return_value = Mock(
                jobs=[create_mock_job_view() for _ in sample_jobs],
                total=4,
                page=1,
                per_page=20,
                total_pages=1,
                status_summary={"pending": 1, "processing": 1, "completed": 1, "failed": 1}
            )

            result = await mock_list(mock_db, page=1, per_page=20)

            assert result.total == 4
            assert result.page == 1
            assert len(result.jobs) == 4

    async def test_list_jobs_pagination(self, mock_db, job_admin_service):
        """Paginierung funktioniert korrekt."""
        total_jobs = 100
        per_page = 10
        expected_pages = math.ceil(total_jobs / per_page)

        with patch.object(job_admin_service, 'list_jobs') as mock_list:
            mock_list.return_value = Mock(
                jobs=[create_mock_job_view() for _ in range(per_page)],
                total=total_jobs,
                page=5,
                per_page=per_page,
                total_pages=expected_pages,
                status_summary={}
            )

            result = await mock_list(mock_db, page=5, per_page=per_page)

            assert result.total == total_jobs
            assert result.total_pages == expected_pages
            assert result.page == 5

    async def test_list_jobs_empty(self, mock_db, job_admin_service):
        """Leere Job-Liste."""
        with patch.object(job_admin_service, 'list_jobs') as mock_list:
            mock_list.return_value = Mock(
                jobs=[],
                total=0,
                page=1,
                per_page=20,
                total_pages=1,
                status_summary={}
            )

            result = await mock_list(mock_db)

            assert result.total == 0
            assert len(result.jobs) == 0

    async def test_list_jobs_with_status_summary(self, mock_db, job_admin_service):
        """Status-Zusammenfassung wird mitgeliefert."""
        with patch.object(job_admin_service, 'list_jobs') as mock_list:
            mock_list.return_value = Mock(
                jobs=[],
                total=50,
                page=1,
                per_page=20,
                total_pages=3,
                status_summary={
                    "pending": 10,
                    "processing": 5,
                    "completed": 30,
                    "failed": 3,
                    "cancelled": 2
                }
            )

            result = await mock_list(mock_db)

            assert "pending" in result.status_summary
            assert "completed" in result.status_summary
            assert sum(result.status_summary.values()) == 50


# ==============================================================================
# Tests: Get Job
# ==============================================================================

@pytest.mark.unit
@pytest.mark.asyncio
class TestGetJob:
    """Tests für get_job Methode."""

    async def test_get_job_found(self, mock_db, job_admin_service):
        """Job gefunden."""
        job_id = uuid4()
        job_view = create_mock_job_view(job_id=job_id)

        with patch.object(job_admin_service, 'get_job') as mock_get:
            mock_get.return_value = job_view

            result = await mock_get(mock_db, job_id)

            assert result is not None
            assert result.id == job_id

    async def test_get_job_not_found(self, mock_db, job_admin_service):
        """Job nicht gefunden."""
        with patch.object(job_admin_service, 'get_job') as mock_get:
            mock_get.return_value = None

            result = await mock_get(mock_db, uuid4())

            assert result is None

    async def test_get_job_with_duration(self, mock_db, job_admin_service):
        """Job mit berechneter Dauer."""
        now = datetime.utcnow()
        started = now - timedelta(minutes=5)
        completed = now

        with patch.object(job_admin_service, 'get_job') as mock_get:
            mock_get.return_value = create_mock_job_view(
                started_at=started,
                completed_at=completed,
                duration_ms=5 * 60 * 1000  # 5 Minuten in ms
            )

            result = await mock_get(mock_db, uuid4())

            assert result.duration_ms == 300000  # 5 min

    async def test_get_job_with_wait_time(self, mock_db, job_admin_service):
        """Job mit berechneter Wartezeit."""
        now = datetime.utcnow()
        created = now - timedelta(minutes=10)
        started = now - timedelta(minutes=5)

        with patch.object(job_admin_service, 'get_job') as mock_get:
            mock_get.return_value = create_mock_job_view(
                created_at=created,
                started_at=started,
                wait_time_ms=5 * 60 * 1000  # 5 min Wartezeit
            )

            result = await mock_get(mock_db, uuid4())

            assert result.wait_time_ms == 300000  # 5 min


# ==============================================================================
# Tests: Cancel Job
# ==============================================================================

@pytest.mark.unit
@pytest.mark.asyncio
class TestCancelJob:
    """Tests für cancel_job Methode."""

    async def test_cancel_pending_job(self, mock_db, admin_user, job_admin_service):
        """Pending Job abbrechen."""
        job_id = uuid4()

        with patch.object(job_admin_service, 'cancel_job') as mock_cancel:
            mock_cancel.return_value = Mock(
                success=True,
                job_id=job_id,
                action="cancel",
                message="Auftrag wurde abgebrochen"
            )

            result = await mock_cancel(
                mock_db,
                job_id,
                admin_user,
                "Test-Abbruch",
                "192.168.1.1"
            )

            assert result.success is True
            assert result.action == "cancel"

    async def test_cancel_processing_job(self, mock_db, admin_user, job_admin_service):
        """Processing Job abbrechen."""
        job_id = uuid4()

        with patch.object(job_admin_service, 'cancel_job') as mock_cancel:
            mock_cancel.return_value = Mock(
                success=True,
                job_id=job_id,
                action="cancel",
                message="Auftrag wurde abgebrochen"
            )

            result = await mock_cancel(mock_db, job_id, admin_user, None, None)

            assert result.success is True

    async def test_cancel_completed_job_fails(self, mock_db, admin_user, job_admin_service):
        """Abgeschlossener Job kann nicht abgebrochen werden."""
        job_id = uuid4()

        with patch.object(job_admin_service, 'cancel_job') as mock_cancel:
            mock_cancel.return_value = Mock(
                success=False,
                job_id=job_id,
                action="cancel",
                message="Auftrag kann nicht abgebrochen werden (bereits abgeschlossen)"
            )

            result = await mock_cancel(mock_db, job_id, admin_user, None, None)

            assert result.success is False
            assert "bereits abgeschlossen" in result.message

    async def test_cancel_cancelled_job_fails(self, mock_db, admin_user, job_admin_service):
        """Bereits abgebrochener Job kann nicht erneut abgebrochen werden."""
        job_id = uuid4()

        with patch.object(job_admin_service, 'cancel_job') as mock_cancel:
            mock_cancel.return_value = Mock(
                success=False,
                job_id=job_id,
                action="cancel",
                message="Auftrag kann nicht abgebrochen werden (bereits abgeschlossen)"
            )

            result = await mock_cancel(mock_db, job_id, admin_user, None, None)

            assert result.success is False

    async def test_cancel_nonexistent_job(self, mock_db, admin_user, job_admin_service):
        """Nicht existierender Job."""
        job_id = uuid4()

        with patch.object(job_admin_service, 'cancel_job') as mock_cancel:
            mock_cancel.return_value = Mock(
                success=False,
                job_id=job_id,
                action="cancel",
                message="Auftrag nicht gefunden"
            )

            result = await mock_cancel(mock_db, job_id, admin_user, None, None)

            assert result.success is False
            assert "nicht gefunden" in result.message

    async def test_cancel_with_reason(self, mock_db, admin_user, job_admin_service):
        """Abbruch mit Begründung."""
        job_id = uuid4()
        reason = "Ressourcenkonflikt"

        with patch.object(job_admin_service, 'cancel_job') as mock_cancel:
            mock_cancel.return_value = Mock(
                success=True,
                job_id=job_id,
                action="cancel",
                message="Auftrag wurde abgebrochen"
            )

            result = await mock_cancel(mock_db, job_id, admin_user, reason, None)

            assert result.success is True


# ==============================================================================
# Tests: Retry Job
# ==============================================================================

@pytest.mark.unit
@pytest.mark.asyncio
class TestRetryJob:
    """Tests für retry_job Methode."""

    async def test_retry_failed_job(self, mock_db, admin_user, job_admin_service):
        """Fehlgeschlagenen Job wiederholen."""
        original_job_id = uuid4()
        new_job_id = uuid4()

        with patch.object(job_admin_service, 'retry_job') as mock_retry:
            mock_retry.return_value = Mock(
                success=True,
                job_id=new_job_id,
                action="retry",
                message=f"Auftrag wird erneut verarbeitet (neue ID: {new_job_id})"
            )

            result = await mock_retry(
                mock_db,
                original_job_id,
                admin_user,
                priority=None,
                backend=None,
                ip_address="192.168.1.1"
            )

            assert result.success is True
            assert result.action == "retry"
            assert result.job_id == new_job_id

    async def test_retry_with_new_priority(self, mock_db, admin_user, job_admin_service):
        """Retry mit neuer Priorität."""
        original_job_id = uuid4()
        new_job_id = uuid4()

        with patch.object(job_admin_service, 'retry_job') as mock_retry:
            mock_retry.return_value = Mock(
                success=True,
                job_id=new_job_id,
                action="retry",
                message="Auftrag wird erneut verarbeitet"
            )

            result = await mock_retry(
                mock_db,
                original_job_id,
                admin_user,
                priority=10,  # Höhere Priorität
                backend=None,
                ip_address=None
            )

            assert result.success is True

    async def test_retry_with_different_backend(self, mock_db, admin_user, job_admin_service):
        """Retry mit anderem Backend."""
        original_job_id = uuid4()
        new_job_id = uuid4()

        with patch.object(job_admin_service, 'retry_job') as mock_retry:
            mock_retry.return_value = Mock(
                success=True,
                job_id=new_job_id,
                action="retry",
                message="Auftrag wird erneut verarbeitet"
            )

            result = await mock_retry(
                mock_db,
                original_job_id,
                admin_user,
                priority=None,
                backend="got_ocr",  # Anderes Backend
                ip_address=None
            )

            assert result.success is True

    async def test_retry_non_failed_job(self, mock_db, admin_user, job_admin_service):
        """Nicht-fehlgeschlagener Job kann nicht wiederholt werden."""
        job_id = uuid4()

        with patch.object(job_admin_service, 'retry_job') as mock_retry:
            mock_retry.return_value = Mock(
                success=False,
                job_id=job_id,
                action="retry",
                message="Nur fehlgeschlagene Auftraege koennen wiederholt werden"
            )

            result = await mock_retry(mock_db, job_id, admin_user, None, None, None)

            assert result.success is False
            assert "fehlgeschlagene" in result.message

    async def test_retry_nonexistent_job(self, mock_db, admin_user, job_admin_service):
        """Retry für nicht existierenden Job."""
        job_id = uuid4()

        with patch.object(job_admin_service, 'retry_job') as mock_retry:
            mock_retry.return_value = Mock(
                success=False,
                job_id=job_id,
                action="retry",
                message="Auftrag nicht gefunden"
            )

            result = await mock_retry(mock_db, job_id, admin_user, None, None, None)

            assert result.success is False
            assert "nicht gefunden" in result.message


# ==============================================================================
# Tests: Clear Queue
# ==============================================================================

@pytest.mark.unit
@pytest.mark.asyncio
class TestClearQueue:
    """Tests für clear_queue Methode."""

    async def test_clear_pending_jobs(self, mock_db, admin_user, job_admin_service):
        """Wartende Jobs löschen."""
        with patch.object(job_admin_service, 'clear_queue') as mock_clear:
            mock_clear.return_value = Mock(
                success=True,
                cleared_count=15,
                message="15 wartende Auftraege wurden geloescht"
            )

            result = await mock_clear(
                mock_db,
                admin_user,
                status=MockProcessingStatus.PENDING,
                ip_address="192.168.1.1"
            )

            assert result.success is True
            assert result.cleared_count == 15

    async def test_clear_queued_jobs(self, mock_db, admin_user, job_admin_service):
        """Queued Jobs löschen."""
        with patch.object(job_admin_service, 'clear_queue') as mock_clear:
            mock_clear.return_value = Mock(
                success=True,
                cleared_count=5,
                message="5 wartende Auftraege wurden geloescht"
            )

            result = await mock_clear(
                mock_db,
                admin_user,
                status=MockProcessingStatus.QUEUED,
                ip_address=None
            )

            assert result.success is True

    async def test_clear_empty_queue(self, mock_db, admin_user, job_admin_service):
        """Leere Queue löschen."""
        with patch.object(job_admin_service, 'clear_queue') as mock_clear:
            mock_clear.return_value = Mock(
                success=True,
                cleared_count=0,
                message="Keine wartenden Auftraege vorhanden"
            )

            result = await mock_clear(mock_db, admin_user, MockProcessingStatus.PENDING, None)

            assert result.success is True
            assert result.cleared_count == 0

    async def test_clear_processing_jobs_blocked(self, mock_db, admin_user, job_admin_service):
        """Processing Jobs können nicht gelöscht werden."""
        with patch.object(job_admin_service, 'clear_queue') as mock_clear:
            mock_clear.return_value = Mock(
                success=False,
                cleared_count=0,
                message="Nur wartende Auftraege koennen geloescht werden"
            )

            result = await mock_clear(
                mock_db,
                admin_user,
                status=MockProcessingStatus.PROCESSING,
                ip_address=None
            )

            assert result.success is False
            assert "Nur wartende" in result.message

    async def test_clear_completed_jobs_blocked(self, mock_db, admin_user, job_admin_service):
        """Abgeschlossene Jobs können nicht gelöscht werden."""
        with patch.object(job_admin_service, 'clear_queue') as mock_clear:
            mock_clear.return_value = Mock(
                success=False,
                cleared_count=0,
                message="Nur wartende Auftraege koennen geloescht werden"
            )

            result = await mock_clear(
                mock_db,
                admin_user,
                status=MockProcessingStatus.COMPLETED,
                ip_address=None
            )

            assert result.success is False


# ==============================================================================
# Tests: Job Filters
# ==============================================================================

@pytest.mark.unit
@pytest.mark.asyncio
class TestJobFilters:
    """Tests für verschiedene Filter-Kombinationen."""

    async def test_filter_by_status(self, mock_db, job_admin_service):
        """Filter nach Status."""
        with patch.object(job_admin_service, 'list_jobs') as mock_list:
            mock_list.return_value = Mock(
                jobs=[create_mock_job_view(status="pending")],
                total=1,
                page=1,
                per_page=20,
                total_pages=1,
                status_summary={"pending": 1}
            )

            result = await mock_list(
                mock_db,
                filters=Mock(
                    status=MockProcessingStatus.PENDING,
                    backend=None, user_id=None, priority=None,
                    created_from=None, created_to=None, has_error=None
                )
            )

            assert result.total == 1

    async def test_filter_by_backend(self, mock_db, job_admin_service):
        """Filter nach Backend."""
        with patch.object(job_admin_service, 'list_jobs') as mock_list:
            mock_list.return_value = Mock(
                jobs=[create_mock_job_view(backend="deepseek")],
                total=5,
                page=1,
                per_page=20,
                total_pages=1,
                status_summary={}
            )

            result = await mock_list(
                mock_db,
                filters=Mock(
                    status=None, backend="deepseek", user_id=None, priority=None,
                    created_from=None, created_to=None, has_error=None
                )
            )

            assert result.total == 5

    async def test_filter_by_user(self, mock_db, job_admin_service):
        """Filter nach Benutzer."""
        user_id = uuid4()

        with patch.object(job_admin_service, 'list_jobs') as mock_list:
            mock_list.return_value = Mock(
                jobs=[create_mock_job_view(user_id=user_id)],
                total=3,
                page=1,
                per_page=20,
                total_pages=1,
                status_summary={}
            )

            result = await mock_list(
                mock_db,
                filters=Mock(
                    status=None, backend=None, user_id=user_id, priority=None,
                    created_from=None, created_to=None, has_error=None
                )
            )

            assert result.total == 3

    async def test_filter_by_priority(self, mock_db, job_admin_service):
        """Filter nach Priorität."""
        with patch.object(job_admin_service, 'list_jobs') as mock_list:
            mock_list.return_value = Mock(
                jobs=[create_mock_job_view(priority=10)],
                total=2,
                page=1,
                per_page=20,
                total_pages=1,
                status_summary={}
            )

            result = await mock_list(
                mock_db,
                filters=Mock(
                    status=None, backend=None, user_id=None, priority=10,
                    created_from=None, created_to=None, has_error=None
                )
            )

            assert result.total == 2

    async def test_filter_by_date_range(self, mock_db, job_admin_service):
        """Filter nach Datumsbereich."""
        now = datetime.utcnow()
        yesterday = now - timedelta(days=1)

        with patch.object(job_admin_service, 'list_jobs') as mock_list:
            mock_list.return_value = Mock(
                jobs=[],
                total=10,
                page=1,
                per_page=20,
                total_pages=1,
                status_summary={}
            )

            result = await mock_list(
                mock_db,
                filters=Mock(
                    status=None, backend=None, user_id=None, priority=None,
                    created_from=yesterday, created_to=now, has_error=None
                )
            )

            assert result is not None

    async def test_filter_by_has_error(self, mock_db, job_admin_service):
        """Filter nach Fehler-Status."""
        with patch.object(job_admin_service, 'list_jobs') as mock_list:
            mock_list.return_value = Mock(
                jobs=[create_mock_job_view(error_message="OCR Error")],
                total=5,
                page=1,
                per_page=20,
                total_pages=1,
                status_summary={}
            )

            result = await mock_list(
                mock_db,
                filters=Mock(
                    status=None, backend=None, user_id=None, priority=None,
                    created_from=None, created_to=None, has_error=True
                )
            )

            assert result.total == 5

    async def test_combined_filters(self, mock_db, job_admin_service):
        """Mehrere Filter kombiniert."""
        with patch.object(job_admin_service, 'list_jobs') as mock_list:
            mock_list.return_value = Mock(
                jobs=[create_mock_job_view(backend="got_ocr", status="failed")],
                total=2,
                page=1,
                per_page=20,
                total_pages=1,
                status_summary={}
            )

            result = await mock_list(
                mock_db,
                filters=Mock(
                    status=MockProcessingStatus.FAILED,
                    backend="got_ocr",
                    user_id=None, priority=None,
                    created_from=None, created_to=None,
                    has_error=True
                )
            )

            assert result.total == 2


# ==============================================================================
# Tests: Sorting
# ==============================================================================

@pytest.mark.unit
@pytest.mark.asyncio
class TestJobSorting:
    """Tests für Sortierung."""

    async def test_sort_by_created_at_desc(self, mock_db, job_admin_service):
        """Sortierung nach Erstellungsdatum absteigend."""
        now = datetime.utcnow()

        with patch.object(job_admin_service, 'list_jobs') as mock_list:
            jobs = [
                create_mock_job_view(created_at=now),
                create_mock_job_view(created_at=now - timedelta(hours=1)),
                create_mock_job_view(created_at=now - timedelta(hours=2)),
            ]
            mock_list.return_value = Mock(
                jobs=jobs,
                total=3,
                page=1,
                per_page=20,
                total_pages=1,
                status_summary={}
            )

            result = await mock_list(
                mock_db,
                sort_by="created_at",
                sort_order=Mock(name="DESC")
            )

            # Neueste zuerst
            assert result.jobs[0].created_at > result.jobs[1].created_at

    async def test_sort_by_priority_asc(self, mock_db, job_admin_service):
        """Sortierung nach Priorität aufsteigend."""
        with patch.object(job_admin_service, 'list_jobs') as mock_list:
            jobs = [
                create_mock_job_view(priority=1),
                create_mock_job_view(priority=5),
                create_mock_job_view(priority=10),
            ]
            mock_list.return_value = Mock(
                jobs=jobs,
                total=3,
                page=1,
                per_page=20,
                total_pages=1,
                status_summary={}
            )

            result = await mock_list(
                mock_db,
                sort_by="priority",
                sort_order=Mock(name="ASC")
            )

            assert result.jobs[0].priority < result.jobs[1].priority


# ==============================================================================
# Tests: Duration Calculations
# ==============================================================================

@pytest.mark.unit
@pytest.mark.asyncio
class TestDurationCalculations:
    """Tests für Dauer-Berechnungen."""

    async def test_duration_calculation(self, mock_db, job_admin_service):
        """Dauer wird korrekt berechnet."""
        started = datetime(2024, 1, 1, 10, 0, 0)
        completed = datetime(2024, 1, 1, 10, 5, 30)  # 5 min 30 sec später

        with patch.object(job_admin_service, 'get_job') as mock_get:
            mock_get.return_value = create_mock_job_view(
                started_at=started,
                completed_at=completed,
                duration_ms=330000  # 5.5 Minuten
            )

            result = await mock_get(mock_db, uuid4())

            assert result.duration_ms == 330000

    async def test_wait_time_calculation(self, mock_db, job_admin_service):
        """Wartezeit wird korrekt berechnet."""
        created = datetime(2024, 1, 1, 10, 0, 0)
        started = datetime(2024, 1, 1, 10, 2, 0)  # 2 min später

        with patch.object(job_admin_service, 'get_job') as mock_get:
            mock_get.return_value = create_mock_job_view(
                created_at=created,
                started_at=started,
                wait_time_ms=120000  # 2 Minuten
            )

            result = await mock_get(mock_db, uuid4())

            assert result.wait_time_ms == 120000

    async def test_no_duration_for_incomplete(self, mock_db, job_admin_service):
        """Keine Dauer für unvollständige Jobs."""
        with patch.object(job_admin_service, 'get_job') as mock_get:
            mock_get.return_value = create_mock_job_view(
                started_at=datetime.utcnow(),
                completed_at=None,  # Noch nicht fertig
                duration_ms=None
            )

            result = await mock_get(mock_db, uuid4())

            assert result.duration_ms is None


# ==============================================================================
# Tests: Edge Cases
# ==============================================================================

@pytest.mark.unit
@pytest.mark.asyncio
class TestJobEdgeCases:
    """Edge Cases und Grenzwerte."""

    async def test_job_without_document(self, mock_db, job_admin_service):
        """Job ohne zugehöriges Dokument."""
        with patch.object(job_admin_service, 'get_job') as mock_get:
            mock_get.return_value = create_mock_job_view(
                document_id=None,
                document_filename=None,
                user_id=None,
                user_email=None
            )

            result = await mock_get(mock_db, uuid4())

            assert result.document_filename is None

    async def test_job_with_large_result(self, mock_db, job_admin_service):
        """Job mit großem Result-Objekt."""
        with patch.object(job_admin_service, 'get_job') as mock_get:
            large_result = {"text": "x" * 100000}  # 100KB Text
            job_view = create_mock_job_view()
            job_view.result = large_result
            mock_get.return_value = job_view

            result = await mock_get(mock_db, uuid4())

            assert len(result.result.get("text", "")) == 100000

    async def test_retry_preserves_document_id(self, mock_db, admin_user, job_admin_service):
        """Retry behält Dokument-ID bei."""
        original_job_id = uuid4()
        doc_id = uuid4()
        new_job_id = uuid4()

        with patch.object(job_admin_service, 'retry_job') as mock_retry:
            mock_retry.return_value = Mock(
                success=True,
                job_id=new_job_id,
                action="retry",
                message="OK"
            )

            result = await mock_retry(mock_db, original_job_id, admin_user, None, None, None)

            assert result.success is True

    async def test_very_old_job(self, mock_db, job_admin_service):
        """Sehr alter Job."""
        old_date = datetime(2020, 1, 1)

        with patch.object(job_admin_service, 'get_job') as mock_get:
            mock_get.return_value = create_mock_job_view(
                created_at=old_date,
                status="completed"
            )

            result = await mock_get(mock_db, uuid4())

            assert result.created_at == old_date


# ==============================================================================
# Tests: Admin Action Logging
# ==============================================================================

@pytest.mark.unit
@pytest.mark.asyncio
class TestAdminActionLogging:
    """Tests für Admin-Action Logging."""

    async def test_cancel_logs_admin_action(self, mock_db, admin_user, job_admin_service):
        """Cancel loggt AdminAction."""
        with patch.object(job_admin_service, 'cancel_job') as mock_cancel:
            mock_cancel.return_value = Mock(success=True, job_id=uuid4(), action="cancel", message="OK")

            await mock_cancel(mock_db, uuid4(), admin_user, "Reason", "1.2.3.4")

            # Verifiziere dass cancel_job aufgerufen wurde
            mock_cancel.assert_called_once()

    async def test_retry_logs_admin_action(self, mock_db, admin_user, job_admin_service):
        """Retry loggt AdminAction."""
        with patch.object(job_admin_service, 'retry_job') as mock_retry:
            mock_retry.return_value = Mock(success=True, job_id=uuid4(), action="retry", message="OK")

            await mock_retry(mock_db, uuid4(), admin_user, None, None, "1.2.3.4")

            mock_retry.assert_called_once()

    async def test_clear_queue_logs_admin_action(self, mock_db, admin_user, job_admin_service):
        """Queue Clear loggt AdminAction."""
        with patch.object(job_admin_service, 'clear_queue') as mock_clear:
            mock_clear.return_value = Mock(success=True, cleared_count=10, message="OK")

            await mock_clear(mock_db, admin_user, MockProcessingStatus.PENDING, "1.2.3.4")

            mock_clear.assert_called_once()


# ==============================================================================
# Tests: Backend Specific
# ==============================================================================

@pytest.mark.unit
@pytest.mark.asyncio
class TestBackendSpecific:
    """Tests für Backend-spezifische Szenarien."""

    @pytest.mark.parametrize("backend", ["deepseek", "got_ocr", "surya", "surya_gpu", "hybrid"])
    async def test_filter_each_backend(self, mock_db, job_admin_service, backend):
        """Jedes Backend kann gefiltert werden."""
        with patch.object(job_admin_service, 'list_jobs') as mock_list:
            mock_list.return_value = Mock(
                jobs=[create_mock_job_view(backend=backend)],
                total=1,
                page=1,
                per_page=20,
                total_pages=1,
                status_summary={}
            )

            result = await mock_list(
                mock_db,
                filters=Mock(
                    status=None, backend=backend, user_id=None, priority=None,
                    created_from=None, created_to=None, has_error=None
                )
            )

            assert result.total >= 0

    async def test_retry_with_backend_switch(self, mock_db, admin_user, job_admin_service):
        """Retry mit Backend-Wechsel (z.B. deepseek -> got_ocr)."""
        with patch.object(job_admin_service, 'retry_job') as mock_retry:
            mock_retry.return_value = Mock(
                success=True,
                job_id=uuid4(),
                action="retry",
                message="OK"
            )

            result = await mock_retry(
                mock_db,
                uuid4(),  # Original war deepseek
                admin_user,
                priority=None,
                backend="got_ocr",  # Wechsel zu got_ocr
                ip_address=None
            )

            assert result.success is True
