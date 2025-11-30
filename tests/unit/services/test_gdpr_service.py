"""
Unit tests for GDPR Service (Art. 17 DSGVO - Löschrecht).

Tests:
- Löschanfrage einreichen
- Löschanfrage zurückziehen
- Löschstatus abfragen
- Automatische Löschung nach Fristablauf
"""

import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from app.services.gdpr_service import GDPRService, DELETION_GRACE_PERIOD_DAYS
from app.core.exceptions import GDPRError, UserNotFoundError


@pytest.fixture
def gdpr_service():
    """Create GDPR service instance."""
    return GDPRService()


@pytest.fixture
def mock_user():
    """Create mock user object."""
    user = MagicMock()
    user.id = uuid4()
    user.email = "test@example.com"
    user.deletion_requested_at = None
    user.deletion_scheduled_for = None
    user.deletion_reason = None
    user.deletion_confirmed = False
    return user


@pytest.fixture
def mock_db():
    """Create mock database session."""
    db = AsyncMock()
    return db


class TestRequestDeletion:
    """Tests for request_deletion method."""

    @pytest.mark.asyncio
    async def test_request_deletion_success(self, gdpr_service, mock_user, mock_db):
        """Löschanfrage erfolgreich einreichen."""
        mock_db.get.return_value = mock_user

        scheduled_date = await gdpr_service.request_deletion(
            mock_db, mock_user.id, reason="Test-Löschung"
        )

        # Prüfe geplantes Datum (30 Tage in der Zukunft)
        expected_date = datetime.now(timezone.utc) + timedelta(days=DELETION_GRACE_PERIOD_DAYS)
        assert (scheduled_date - expected_date).total_seconds() < 60  # Max 1 Minute Differenz

        # Prüfe User-Updates
        assert mock_user.deletion_requested_at is not None
        assert mock_user.deletion_scheduled_for is not None
        assert mock_user.deletion_reason == "Test-Löschung"
        assert mock_user.deletion_confirmed is True

        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_request_deletion_user_not_found(self, gdpr_service, mock_db):
        """Fehler wenn User nicht existiert."""
        mock_db.get.return_value = None

        with pytest.raises(UserNotFoundError):
            await gdpr_service.request_deletion(mock_db, uuid4())

    @pytest.mark.asyncio
    async def test_request_deletion_already_requested(self, gdpr_service, mock_user, mock_db):
        """Fehler wenn bereits Löschanfrage existiert."""
        mock_user.deletion_requested_at = datetime.now(timezone.utc)
        mock_user.deletion_scheduled_for = datetime.now(timezone.utc) + timedelta(days=30)
        mock_db.get.return_value = mock_user

        with pytest.raises(GDPRError) as exc_info:
            await gdpr_service.request_deletion(mock_db, mock_user.id)

        assert "bereits vorhanden" in str(exc_info.value.user_message_de)


class TestCancelDeletion:
    """Tests for cancel_deletion method."""

    @pytest.mark.asyncio
    async def test_cancel_deletion_success(self, gdpr_service, mock_user, mock_db):
        """Löschanfrage erfolgreich zurückziehen."""
        mock_user.deletion_requested_at = datetime.now(timezone.utc)
        mock_user.deletion_scheduled_for = datetime.now(timezone.utc) + timedelta(days=30)
        mock_db.get.return_value = mock_user

        result = await gdpr_service.cancel_deletion(mock_db, mock_user.id)

        assert result is True
        assert mock_user.deletion_requested_at is None
        assert mock_user.deletion_scheduled_for is None
        assert mock_user.deletion_confirmed is False

        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_cancel_deletion_no_request(self, gdpr_service, mock_user, mock_db):
        """Fehler wenn keine Löschanfrage existiert."""
        mock_db.get.return_value = mock_user

        with pytest.raises(GDPRError) as exc_info:
            await gdpr_service.cancel_deletion(mock_db, mock_user.id)

        assert "Kein aktiver Löschantrag" in str(exc_info.value.user_message_de)

    @pytest.mark.asyncio
    async def test_cancel_deletion_expired(self, gdpr_service, mock_user, mock_db):
        """Fehler wenn Löschfrist bereits abgelaufen."""
        mock_user.deletion_requested_at = datetime.now(timezone.utc) - timedelta(days=31)
        mock_user.deletion_scheduled_for = datetime.now(timezone.utc) - timedelta(days=1)
        mock_db.get.return_value = mock_user

        with pytest.raises(GDPRError) as exc_info:
            await gdpr_service.cancel_deletion(mock_db, mock_user.id)

        assert "abgelaufen" in str(exc_info.value.user_message_de)


class TestGetDeletionStatus:
    """Tests for get_deletion_status method."""

    @pytest.mark.asyncio
    async def test_status_no_request(self, gdpr_service, mock_user):
        """Status wenn keine Anfrage vorliegt."""
        status = await gdpr_service.get_deletion_status(mock_user)

        assert status["deletion_requested"] is False
        assert status["can_cancel"] is False
        assert "Kein aktiver" in status["nachricht"]

    @pytest.mark.asyncio
    async def test_status_with_pending_request(self, gdpr_service, mock_user):
        """Status mit aktiver Löschanfrage."""
        now = datetime.now(timezone.utc)
        mock_user.deletion_requested_at = now
        mock_user.deletion_scheduled_for = now + timedelta(days=20)

        status = await gdpr_service.get_deletion_status(mock_user)

        assert status["deletion_requested"] is True
        assert status["days_remaining"] == 19 or status["days_remaining"] == 20
        assert status["can_cancel"] is True
        assert "geplant" in status["nachricht"]


class TestExecuteDeletion:
    """Tests for execute_deletion method."""

    @pytest.mark.asyncio
    async def test_execute_deletion_soft_delete(self, gdpr_service, mock_user, mock_db):
        """Soft-Delete (Anonymisierung) durchführen."""
        mock_db.get.return_value = mock_user

        # Mock document query
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result

        stats = await gdpr_service.execute_deletion(
            mock_db, mock_user.id, hard_delete=False
        )

        assert stats["documents"] == 0
        assert mock_user.email == f"deleted_{mock_user.id}@anonymized.gdpr.local"
        assert mock_user.full_name == "[GELÖSCHT]"
        assert mock_user.is_active is False

        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_deletion_user_not_found(self, gdpr_service, mock_db):
        """Fehler wenn User nicht existiert."""
        mock_db.get.return_value = None

        with pytest.raises(UserNotFoundError):
            await gdpr_service.execute_deletion(mock_db, uuid4())


class TestGetPendingDeletions:
    """Tests for get_pending_deletions method."""

    @pytest.mark.asyncio
    async def test_get_pending_deletions(self, gdpr_service, mock_db):
        """Fällige Löschanfragen abrufen."""
        mock_user1 = MagicMock()
        mock_user1.id = uuid4()
        mock_user2 = MagicMock()
        mock_user2.id = uuid4()

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_user1, mock_user2]
        mock_db.execute.return_value = mock_result

        pending = await gdpr_service.get_pending_deletions(mock_db)

        assert len(pending) == 2
