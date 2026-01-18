# -*- coding: utf-8 -*-
"""
Unit-Tests fuer DocumentTaskService.

Testet:
- CRUD Operations (Create, Read, Update, Delete)
- Status Transitions (start, complete, cancel)
- Assignment (assign, reassign)
- Query Methods (list, overdue, by assignee)
- Notifications (assignment, status changes)

Feinpoliert und durchdacht - DocumentTask-Service-Tests.
"""

import pytest
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from unittest.mock import Mock, AsyncMock, patch, MagicMock

import sys
from pathlib import Path

# Add app to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent))


# Test constants
TEST_USER_ID = uuid4()
TEST_COMPANY_ID = uuid4()
TEST_DOCUMENT_ID = uuid4()
TEST_TASK_ID = uuid4()


# ========================= Test Fixtures =========================


@pytest.fixture
def mock_db_session():
    """Create mock database session."""
    session = AsyncMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    session.add = Mock()
    session.delete = AsyncMock()
    session.refresh = AsyncMock()
    return session


@pytest.fixture
def mock_document():
    """Create mock document."""
    doc = Mock()
    doc.id = TEST_DOCUMENT_ID
    doc.company_id = TEST_COMPANY_ID
    doc.filename = "test_document.pdf"
    doc.original_filename = "Test Document.pdf"
    return doc


@pytest.fixture
def mock_user():
    """Create mock user."""
    user = Mock()
    user.id = TEST_USER_ID
    user.email = "test@example.com"
    user.username = "testuser"
    user.full_name = "Test User"
    return user


@pytest.fixture
def mock_assignee():
    """Create mock assignee user."""
    user = Mock()
    user.id = uuid4()
    user.email = "assignee@example.com"
    user.username = "assignee"
    user.full_name = "Assignee User"
    return user


@pytest.fixture
def mock_task(mock_document, mock_user, mock_assignee):
    """Create mock document task."""
    task = Mock()
    task.id = TEST_TASK_ID
    task.document_id = mock_document.id
    task.company_id = TEST_COMPANY_ID
    task.title = "Bitte pruefen"
    task.description = "Dokument muss geprueft werden"
    task.task_type = "review"
    task.status = "open"
    task.priority = "normal"
    task.created_by_id = mock_user.id
    task.assigned_to_id = mock_assignee.id
    task.due_date = datetime.now(timezone.utc) + timedelta(days=3)
    task.task_metadata = {}
    task.escalation_level = 0
    task.is_escalated = False
    task.document = mock_document
    task.created_by = mock_user
    task.assigned_to = mock_assignee
    task.created_at = datetime.now(timezone.utc)
    task.updated_at = datetime.now(timezone.utc)
    task.last_reminder_at = None
    return task


# ========================= CRUD Tests =========================


class TestDocumentTaskServiceCRUD:
    """Tests fuer CRUD Operations."""

    @pytest.mark.asyncio
    async def test_create_task_success(self, mock_db_session, mock_document, mock_user):
        """Sollte Task erfolgreich erstellen."""
        from app.services.collaboration.document_task_service import DocumentTaskService

        # Mock document lookup
        mock_doc_result = Mock()
        mock_doc_result.scalar_one_or_none.return_value = mock_document
        mock_db_session.execute.return_value = mock_doc_result

        service = DocumentTaskService(mock_db_session)

        with patch.object(service, '_send_assignment_notification', new_callable=AsyncMock):
            result = await service.create_task(
                document_id=mock_document.id,
                company_id=TEST_COMPANY_ID,
                created_by_id=mock_user.id,
                title="Bitte pruefen",
                description="Test-Beschreibung",
                task_type="review",
                priority="normal",
            )

        mock_db_session.add.assert_called_once()
        mock_db_session.commit.assert_called()

    @pytest.mark.asyncio
    async def test_create_task_document_not_found(self, mock_db_session, mock_user):
        """Sollte ValueError werfen wenn Dokument nicht gefunden."""
        from app.services.collaboration.document_task_service import DocumentTaskService

        # Mock document lookup returns None
        mock_doc_result = Mock()
        mock_doc_result.scalar_one_or_none.return_value = None
        mock_db_session.execute.return_value = mock_doc_result

        service = DocumentTaskService(mock_db_session)

        with pytest.raises(ValueError, match="Dokument nicht gefunden"):
            await service.create_task(
                document_id=uuid4(),
                company_id=TEST_COMPANY_ID,
                created_by_id=mock_user.id,
                title="Test Task",
            )

    @pytest.mark.asyncio
    async def test_create_task_with_assignment(self, mock_db_session, mock_document, mock_user, mock_assignee):
        """Sollte Task mit Zuweisung erstellen und Benachrichtigung senden."""
        from app.services.collaboration.document_task_service import DocumentTaskService

        # Setup sequential mock returns: first for document, then for user
        call_count = 0
        def execute_side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            result = Mock()
            if call_count == 1:
                result.scalar_one_or_none.return_value = mock_document
            else:
                result.scalar_one_or_none.return_value = mock_assignee
            return result

        mock_db_session.execute.side_effect = execute_side_effect

        service = DocumentTaskService(mock_db_session)

        with patch.object(service, '_send_assignment_notification', new_callable=AsyncMock) as mock_notify:
            result = await service.create_task(
                document_id=mock_document.id,
                company_id=TEST_COMPANY_ID,
                created_by_id=mock_user.id,
                title="Bitte pruefen",
                assigned_to_id=mock_assignee.id,
                notify_assignee=True,
            )

            mock_notify.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_task_found(self, mock_db_session, mock_task):
        """Sollte Task zurueckgeben wenn gefunden."""
        from app.services.collaboration.document_task_service import DocumentTaskService

        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = mock_task
        mock_db_session.execute.return_value = mock_result

        service = DocumentTaskService(mock_db_session)
        result = await service.get_task(TEST_TASK_ID)

        assert result is not None
        assert result.id == TEST_TASK_ID
        assert result.title == "Bitte pruefen"

    @pytest.mark.asyncio
    async def test_get_task_not_found(self, mock_db_session):
        """Sollte None zurueckgeben wenn Task nicht gefunden."""
        from app.services.collaboration.document_task_service import DocumentTaskService

        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute.return_value = mock_result

        service = DocumentTaskService(mock_db_session)
        result = await service.get_task(uuid4())

        assert result is None

    @pytest.mark.asyncio
    async def test_get_task_with_company_filter(self, mock_db_session, mock_task):
        """Sollte Task mit Firmenfilter zurueckgeben."""
        from app.services.collaboration.document_task_service import DocumentTaskService

        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = mock_task
        mock_db_session.execute.return_value = mock_result

        service = DocumentTaskService(mock_db_session)
        result = await service.get_task(TEST_TASK_ID, company_id=TEST_COMPANY_ID)

        assert result is not None
        mock_db_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_task_success(self, mock_db_session, mock_task):
        """Sollte Task erfolgreich aktualisieren."""
        from app.services.collaboration.document_task_service import DocumentTaskService

        service = DocumentTaskService(mock_db_session)

        with patch.object(service, 'get_task', new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_task

            result = await service.update_task(
                task_id=TEST_TASK_ID,
                company_id=TEST_COMPANY_ID,
                updated_by_id=TEST_USER_ID,
                title="Neuer Titel",
                priority="high",
            )

            assert result.title == "Neuer Titel"
            assert result.priority == "high"
            mock_db_session.commit.assert_called()

    @pytest.mark.asyncio
    async def test_update_task_not_found(self, mock_db_session):
        """Sollte None zurueckgeben wenn Task nicht gefunden."""
        from app.services.collaboration.document_task_service import DocumentTaskService

        service = DocumentTaskService(mock_db_session)

        with patch.object(service, 'get_task', new_callable=AsyncMock) as mock_get:
            mock_get.return_value = None

            result = await service.update_task(
                task_id=uuid4(),
                company_id=TEST_COMPANY_ID,
                updated_by_id=TEST_USER_ID,
                title="Neuer Titel",
            )

            assert result is None

    @pytest.mark.asyncio
    async def test_update_task_wrong_status(self, mock_db_session, mock_task):
        """Sollte ValueError werfen bei falschem Status."""
        from app.services.collaboration.document_task_service import DocumentTaskService

        mock_task.status = "completed"  # Nicht aktualisierbar

        service = DocumentTaskService(mock_db_session)

        with patch.object(service, 'get_task', new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_task

            with pytest.raises(ValueError, match="kann nicht aktualisiert werden"):
                await service.update_task(
                    task_id=TEST_TASK_ID,
                    company_id=TEST_COMPANY_ID,
                    updated_by_id=TEST_USER_ID,
                    title="Neuer Titel",
                )

    @pytest.mark.asyncio
    async def test_delete_task_success(self, mock_db_session, mock_task):
        """Sollte Task erfolgreich loeschen."""
        from app.services.collaboration.document_task_service import DocumentTaskService

        service = DocumentTaskService(mock_db_session)

        with patch.object(service, 'get_task', new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_task

            result = await service.delete_task(
                task_id=TEST_TASK_ID,
                company_id=TEST_COMPANY_ID,
                deleted_by_id=TEST_USER_ID,
            )

            assert result is True
            mock_db_session.delete.assert_called_once_with(mock_task)
            mock_db_session.commit.assert_called()

    @pytest.mark.asyncio
    async def test_delete_task_not_found(self, mock_db_session):
        """Sollte False zurueckgeben wenn Task nicht gefunden."""
        from app.services.collaboration.document_task_service import DocumentTaskService

        service = DocumentTaskService(mock_db_session)

        with patch.object(service, 'get_task', new_callable=AsyncMock) as mock_get:
            mock_get.return_value = None

            result = await service.delete_task(
                task_id=uuid4(),
                company_id=TEST_COMPANY_ID,
                deleted_by_id=TEST_USER_ID,
            )

            assert result is False
            mock_db_session.delete.assert_not_called()


# ========================= Status Transition Tests =========================


class TestDocumentTaskServiceStatusTransitions:
    """Tests fuer Status-Uebergaenge."""

    @pytest.mark.asyncio
    async def test_start_task_success(self, mock_db_session, mock_task):
        """Sollte Task erfolgreich starten."""
        from app.services.collaboration.document_task_service import DocumentTaskService

        mock_task.status = "open"

        service = DocumentTaskService(mock_db_session)

        with patch.object(service, 'get_task', new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_task

            result = await service.start_task(
                task_id=TEST_TASK_ID,
                company_id=TEST_COMPANY_ID,
                user_id=TEST_USER_ID,
            )

            assert result.status == "in_progress"
            mock_db_session.commit.assert_called()

    @pytest.mark.asyncio
    async def test_start_task_wrong_status(self, mock_db_session, mock_task):
        """Sollte ValueError werfen wenn Task nicht offen ist."""
        from app.services.collaboration.document_task_service import DocumentTaskService

        mock_task.status = "in_progress"

        service = DocumentTaskService(mock_db_session)

        with patch.object(service, 'get_task', new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_task

            with pytest.raises(ValueError, match="Nur offene Aufgaben"):
                await service.start_task(
                    task_id=TEST_TASK_ID,
                    company_id=TEST_COMPANY_ID,
                    user_id=TEST_USER_ID,
                )

    @pytest.mark.asyncio
    async def test_complete_task_success(self, mock_db_session, mock_task):
        """Sollte Task erfolgreich abschliessen."""
        from app.services.collaboration.document_task_service import DocumentTaskService

        mock_task.status = "in_progress"

        service = DocumentTaskService(mock_db_session)

        with patch.object(service, 'get_task', new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_task

            with patch.object(service, '_send_completion_notification', new_callable=AsyncMock):
                result = await service.complete_task(
                    task_id=TEST_TASK_ID,
                    company_id=TEST_COMPANY_ID,
                    completed_by_id=TEST_USER_ID,
                )

            assert result.status == "completed"
            mock_db_session.commit.assert_called()

    @pytest.mark.asyncio
    async def test_complete_task_from_open_allowed(self, mock_db_session, mock_task):
        """Sollte direktes Abschliessen von offener Aufgabe erlauben."""
        from app.services.collaboration.document_task_service import DocumentTaskService

        mock_task.status = "open"

        service = DocumentTaskService(mock_db_session)

        with patch.object(service, 'get_task', new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_task

            with patch.object(service, '_send_completion_notification', new_callable=AsyncMock):
                result = await service.complete_task(
                    task_id=TEST_TASK_ID,
                    company_id=TEST_COMPANY_ID,
                    completed_by_id=TEST_USER_ID,
                )

            assert result.status == "completed"

    @pytest.mark.asyncio
    async def test_cancel_task_success(self, mock_db_session, mock_task):
        """Sollte Task erfolgreich abbrechen."""
        from app.services.collaboration.document_task_service import DocumentTaskService

        mock_task.status = "open"

        service = DocumentTaskService(mock_db_session)

        with patch.object(service, 'get_task', new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_task

            result = await service.cancel_task(
                task_id=TEST_TASK_ID,
                company_id=TEST_COMPANY_ID,
                cancelled_by_id=TEST_USER_ID,
                reason="Nicht mehr benoetigt",
            )

            assert result.status == "cancelled"
            mock_db_session.commit.assert_called()

    @pytest.mark.asyncio
    async def test_cancel_task_already_completed(self, mock_db_session, mock_task):
        """Sollte ValueError werfen bei bereits abgeschlossenem Task."""
        from app.services.collaboration.document_task_service import DocumentTaskService

        mock_task.status = "completed"

        service = DocumentTaskService(mock_db_session)

        with patch.object(service, 'get_task', new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_task

            with pytest.raises(ValueError, match="Abgeschlossene Aufgaben"):
                await service.cancel_task(
                    task_id=TEST_TASK_ID,
                    company_id=TEST_COMPANY_ID,
                    cancelled_by_id=TEST_USER_ID,
                )


# ========================= Assignment Tests =========================


class TestDocumentTaskServiceAssignment:
    """Tests fuer Aufgabenzuweisung."""

    @pytest.mark.asyncio
    async def test_assign_task_success(self, mock_db_session, mock_task, mock_assignee):
        """Sollte Task erfolgreich zuweisen."""
        from app.services.collaboration.document_task_service import DocumentTaskService

        mock_task.assigned_to_id = None

        service = DocumentTaskService(mock_db_session)

        # Mock user lookup
        mock_user_result = Mock()
        mock_user_result.scalar_one_or_none.return_value = mock_assignee
        mock_db_session.execute.return_value = mock_user_result

        with patch.object(service, 'get_task', new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_task

            with patch.object(service, '_send_assignment_notification', new_callable=AsyncMock) as mock_notify:
                result = await service.assign_task(
                    task_id=TEST_TASK_ID,
                    company_id=TEST_COMPANY_ID,
                    assigned_to_id=mock_assignee.id,
                    assigned_by_id=TEST_USER_ID,
                )

                assert result.assigned_to_id == mock_assignee.id
                mock_notify.assert_called_once()

    @pytest.mark.asyncio
    async def test_assign_task_user_not_found(self, mock_db_session, mock_task):
        """Sollte ValueError werfen wenn Benutzer nicht gefunden."""
        from app.services.collaboration.document_task_service import DocumentTaskService

        service = DocumentTaskService(mock_db_session)

        mock_user_result = Mock()
        mock_user_result.scalar_one_or_none.return_value = None
        mock_db_session.execute.return_value = mock_user_result

        with patch.object(service, 'get_task', new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_task

            with pytest.raises(ValueError, match="Benutzer nicht gefunden"):
                await service.assign_task(
                    task_id=TEST_TASK_ID,
                    company_id=TEST_COMPANY_ID,
                    assigned_to_id=uuid4(),
                    assigned_by_id=TEST_USER_ID,
                )

    @pytest.mark.asyncio
    async def test_reassign_task(self, mock_db_session, mock_task, mock_assignee):
        """Sollte Task erfolgreich neu zuweisen."""
        from app.services.collaboration.document_task_service import DocumentTaskService

        original_assignee = mock_task.assigned_to_id
        new_assignee = Mock()
        new_assignee.id = uuid4()
        new_assignee.full_name = "New Assignee"

        service = DocumentTaskService(mock_db_session)

        mock_user_result = Mock()
        mock_user_result.scalar_one_or_none.return_value = new_assignee
        mock_db_session.execute.return_value = mock_user_result

        with patch.object(service, 'get_task', new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_task

            with patch.object(service, '_send_assignment_notification', new_callable=AsyncMock):
                result = await service.assign_task(
                    task_id=TEST_TASK_ID,
                    company_id=TEST_COMPANY_ID,
                    assigned_to_id=new_assignee.id,
                    assigned_by_id=TEST_USER_ID,
                )

                assert result.assigned_to_id == new_assignee.id

    @pytest.mark.asyncio
    async def test_unassign_task(self, mock_db_session, mock_task):
        """Sollte Task-Zuweisung entfernen."""
        from app.services.collaboration.document_task_service import DocumentTaskService

        service = DocumentTaskService(mock_db_session)

        with patch.object(service, 'get_task', new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_task

            result = await service.unassign_task(
                task_id=TEST_TASK_ID,
                company_id=TEST_COMPANY_ID,
                unassigned_by_id=TEST_USER_ID,
            )

            assert result.assigned_to_id is None


# ========================= Query Tests =========================


class TestDocumentTaskServiceQueries:
    """Tests fuer Abfrage-Methoden."""

    @pytest.mark.asyncio
    async def test_get_document_tasks(self, mock_db_session, mock_task):
        """Sollte Tasks fuer ein Dokument auflisten."""
        from app.services.collaboration.document_task_service import DocumentTaskService

        mock_result = Mock()
        mock_result.scalars.return_value.all.return_value = [mock_task]
        mock_db_session.execute.return_value = mock_result

        service = DocumentTaskService(mock_db_session)
        result = await service.get_document_tasks(
            document_id=TEST_DOCUMENT_ID,
            company_id=TEST_COMPANY_ID,
        )

        assert len(result) == 1
        assert result[0].id == TEST_TASK_ID

    @pytest.mark.asyncio
    async def test_get_my_tasks(self, mock_db_session, mock_task):
        """Sollte Tasks fuer einen Benutzer auflisten."""
        from app.services.collaboration.document_task_service import DocumentTaskService

        # get_my_tasks calls list_tasks which does 2 queries: count + tasks
        mock_count_result = Mock()
        mock_count_result.scalar.return_value = 1

        mock_tasks_result = Mock()
        mock_tasks_result.scalars.return_value.all.return_value = [mock_task]

        mock_db_session.execute.side_effect = [mock_count_result, mock_tasks_result]

        service = DocumentTaskService(mock_db_session)
        tasks, total = await service.get_my_tasks(
            user_id=TEST_USER_ID,
            company_id=TEST_COMPANY_ID,
        )

        assert len(tasks) == 1
        assert total == 1

    @pytest.mark.asyncio
    async def test_get_overdue_tasks(self, mock_db_session, mock_task):
        """Sollte ueberfaellige Tasks zurueckgeben."""
        from app.services.collaboration.document_task_service import DocumentTaskService

        mock_task.due_date = datetime.now(timezone.utc) - timedelta(days=1)

        mock_result = Mock()
        mock_result.scalars.return_value.all.return_value = [mock_task]
        mock_db_session.execute.return_value = mock_result

        service = DocumentTaskService(mock_db_session)
        result = await service.get_overdue_tasks(company_id=TEST_COMPANY_ID)

        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_get_tasks_due_soon(self, mock_db_session, mock_task):
        """Sollte bald faellige Tasks zurueckgeben."""
        from app.services.collaboration.document_task_service import DocumentTaskService

        mock_task.due_date = datetime.now(timezone.utc) + timedelta(hours=12)

        mock_result = Mock()
        mock_result.scalars.return_value.all.return_value = [mock_task]
        mock_db_session.execute.return_value = mock_result

        service = DocumentTaskService(mock_db_session)
        result = await service.get_tasks_due_soon(
            company_id=TEST_COMPANY_ID,
            hours=24,
        )

        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_list_tasks_with_filters(self, mock_db_session, mock_task):
        """Sollte Tasks mit Filtern auflisten."""
        from app.services.collaboration.document_task_service import DocumentTaskService

        # list_tasks does 2 queries: count + tasks
        mock_count_result = Mock()
        mock_count_result.scalar.return_value = 1

        mock_tasks_result = Mock()
        mock_tasks_result.scalars.return_value.all.return_value = [mock_task]

        mock_db_session.execute.side_effect = [mock_count_result, mock_tasks_result]

        service = DocumentTaskService(mock_db_session)
        tasks, total = await service.list_tasks(
            company_id=TEST_COMPANY_ID,
            document_id=TEST_DOCUMENT_ID,
            assigned_to_id=TEST_USER_ID,
        )

        assert len(tasks) == 1
        assert total == 1


# ========================= Statistics Tests =========================


class TestDocumentTaskServiceStatistics:
    """Tests fuer Statistik-Methoden."""

    @pytest.mark.asyncio
    async def test_get_task_statistics(self, mock_db_session):
        """Sollte Task-Statistiken zurueckgeben."""
        from app.services.collaboration.document_task_service import DocumentTaskService

        # get_task_statistics makes 11 queries:
        # 1 total + 5 status counts + 1 overdue + 4 priority counts
        mock_results = [
            Mock(scalar=Mock(return_value=10)),  # total
            Mock(scalar=Mock(return_value=3)),   # open
            Mock(scalar=Mock(return_value=4)),   # in_progress
            Mock(scalar=Mock(return_value=2)),   # completed
            Mock(scalar=Mock(return_value=0)),   # cancelled
            Mock(scalar=Mock(return_value=1)),   # blocked
            Mock(scalar=Mock(return_value=2)),   # overdue
            Mock(scalar=Mock(return_value=1)),   # low priority
            Mock(scalar=Mock(return_value=5)),   # normal priority
            Mock(scalar=Mock(return_value=3)),   # high priority
            Mock(scalar=Mock(return_value=1)),   # urgent priority
        ]
        mock_db_session.execute.side_effect = mock_results

        service = DocumentTaskService(mock_db_session)
        result = await service.get_task_statistics(company_id=TEST_COMPANY_ID)

        assert result["totalTasks"] == 10
        assert result["openTasks"] == 3
        assert result["inProgressTasks"] == 4
        assert result["completedTasks"] == 2
        assert result["overdueTasks"] == 2
        assert "byPriority" in result


# ========================= Factory Function Tests =========================


class TestGetDocumentTaskService:
    """Tests fuer Factory Function."""

    def test_get_document_task_service(self, mock_db_session):
        """Sollte DocumentTaskService-Instanz erstellen."""
        from app.services.collaboration.document_task_service import (
            get_document_task_service,
            DocumentTaskService,
        )

        result = get_document_task_service(mock_db_session)

        assert isinstance(result, DocumentTaskService)
        assert result.db == mock_db_session
