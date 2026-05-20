# -*- coding: utf-8 -*-
"""
Unit-Tests fuer DigestService.

Testet:
- Preference Management (CRUD)
- Digest Queue Management
- Scheduled Time Calculation
- Digest Compilation
- HTML Rendering

Feinpoliert und durchdacht - Digest-Service-Tests.
"""

import pytest
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from typing import List

import sys
from pathlib import Path

# Add app to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent))


# Test constants
TEST_USER_ID = uuid4()
TEST_COMPANY_ID = uuid4()


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
def mock_user():
    """Create mock user."""
    user = Mock()
    user.id = TEST_USER_ID
    user.email = "test@example.com"
    user.username = "testuser"
    user.full_name = "Test User"
    return user


@pytest.fixture
def mock_notification():
    """Create mock notification (UserNotification)."""
    notif = Mock()
    notif.id = uuid4()
    notif.user_id = TEST_USER_ID
    notif.notification_type = "task_assigned"
    notif.title = "Neue Aufgabe"
    notif.message = "Sie haben eine neue Aufgabe erhalten"
    notif.action_url = "/tasks/123"
    notif.document_id = None
    notif.from_user_id = None
    notif.created_at = datetime.now(timezone.utc)
    return notif


@pytest.fixture
def mock_preference():
    """Create mock notification preference.

    NotificationPreference uses enabled_channels JSONB, not individual boolean fields.
    """
    pref = Mock()
    pref.id = uuid4()
    pref.user_id = TEST_USER_ID
    pref.notification_type = "task_assigned"
    # Model uses enabled_channels JSONB
    pref.enabled_channels = {
        "in_app": True,
        "email": True,
        "websocket": True,
        "slack": False,
        "sms": False,
    }
    pref.digest_frequency = "daily"
    pref.updated_at = None
    return pref


@pytest.fixture
def mock_queue_entry(mock_notification):
    """Create mock digest queue entry.

    NotificationDigestQueue stores notification data directly (not as FK reference).
    """
    entry = Mock()
    entry.id = uuid4()
    entry.user_id = TEST_USER_ID
    # Data stored directly on queue entry (not via relationship)
    entry.notification_type = mock_notification.notification_type
    entry.title = mock_notification.title
    entry.message = mock_notification.message
    entry.action_url = mock_notification.action_url
    entry.document_id = None
    entry.from_user_id = None
    entry.digest_frequency = "daily"
    entry.scheduled_for = datetime.now(timezone.utc) - timedelta(hours=1)
    entry.is_sent = False
    entry.sent_at = None
    entry.created_at = datetime.now(timezone.utc) - timedelta(hours=2)
    return entry


# ========================= DigestService Tests =========================


class TestDigestServicePreferences:
    """Tests fuer Preference Management."""

    @pytest.mark.asyncio
    async def test_get_user_preferences_empty(self, mock_db_session):
        """Sollte leere Liste zurueckgeben wenn keine Praeferenzen existieren."""
        from app.services.collaboration.digest_service import DigestService

        # Setup mock to return empty result
        mock_result = Mock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db_session.execute.return_value = mock_result

        service = DigestService(mock_db_session)
        result = await service.get_user_preferences(TEST_USER_ID)

        assert result == []
        mock_db_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_user_preferences_with_results(self, mock_db_session, mock_preference):
        """Sollte Praeferenzen-Liste zurueckgeben."""
        from app.services.collaboration.digest_service import DigestService

        mock_result = Mock()
        mock_result.scalars.return_value.all.return_value = [mock_preference]
        mock_db_session.execute.return_value = mock_result

        service = DigestService(mock_db_session)
        result = await service.get_user_preferences(TEST_USER_ID)

        assert len(result) == 1
        assert result[0].notification_type == "task_assigned"

    @pytest.mark.asyncio
    async def test_get_preference_found(self, mock_db_session, mock_preference):
        """Sollte spezifische Praeferenz zurueckgeben."""
        from app.services.collaboration.digest_service import DigestService

        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = mock_preference
        mock_db_session.execute.return_value = mock_result

        service = DigestService(mock_db_session)
        result = await service.get_preference(TEST_USER_ID, "task_assigned")

        assert result is not None
        assert result.notification_type == "task_assigned"

    @pytest.mark.asyncio
    async def test_get_preference_not_found(self, mock_db_session):
        """Sollte None zurueckgeben wenn Praeferenz nicht existiert."""
        from app.services.collaboration.digest_service import DigestService

        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute.return_value = mock_result

        service = DigestService(mock_db_session)
        result = await service.get_preference(TEST_USER_ID, "nonexistent")

        assert result is None

    @pytest.mark.asyncio
    async def test_set_preference_create_new(self, mock_db_session):
        """Sollte neue Praeferenz erstellen wenn nicht vorhanden."""
        from app.services.collaboration.digest_service import DigestService

        # Mock get_preference to return None (not found)
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute.return_value = mock_result

        service = DigestService(mock_db_session)

        with patch.object(service, 'get_preference', new_callable=AsyncMock) as mock_get:
            mock_get.return_value = None

            result = await service.set_preference(
                user_id=TEST_USER_ID,
                notification_type="task_assigned",
                email_enabled=True,
                digest_frequency="daily",
            )

            mock_db_session.add.assert_called_once()
            mock_db_session.commit.assert_called()

    @pytest.mark.asyncio
    async def test_delete_preference_success(self, mock_db_session, mock_preference):
        """Sollte Praeferenz erfolgreich loeschen."""
        from app.services.collaboration.digest_service import DigestService

        service = DigestService(mock_db_session)

        with patch.object(service, 'get_preference', new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_preference

            result = await service.delete_preference(TEST_USER_ID, "task_assigned")

            assert result is True
            mock_db_session.delete.assert_called_once_with(mock_preference)
            mock_db_session.commit.assert_called()

    @pytest.mark.asyncio
    async def test_delete_preference_not_found(self, mock_db_session):
        """Sollte False zurueckgeben wenn Praeferenz nicht existiert."""
        from app.services.collaboration.digest_service import DigestService

        service = DigestService(mock_db_session)

        with patch.object(service, 'get_preference', new_callable=AsyncMock) as mock_get:
            mock_get.return_value = None

            result = await service.delete_preference(TEST_USER_ID, "nonexistent")

            assert result is False
            mock_db_session.delete.assert_not_called()


class TestDigestServiceQueueManagement:
    """Tests fuer Digest Queue Management."""

    @pytest.mark.asyncio
    async def test_queue_for_digest(self, mock_db_session, mock_notification):
        """Sollte Benachrichtigung zur Queue hinzufuegen."""
        from app.services.collaboration.digest_service import DigestService

        service = DigestService(mock_db_session)

        result = await service.queue_for_digest(
            notification=mock_notification,
            digest_frequency="daily",
        )

        mock_db_session.add.assert_called_once()
        mock_db_session.commit.assert_called()

    @pytest.mark.asyncio
    async def test_get_pending_digests(self, mock_db_session, mock_queue_entry):
        """Sollte ausstehende Digests gruppiert nach User zurueckgeben."""
        from app.services.collaboration.digest_service import DigestService

        mock_result = Mock()
        mock_result.scalars.return_value.all.return_value = [mock_queue_entry]
        mock_db_session.execute.return_value = mock_result

        service = DigestService(mock_db_session)
        result = await service.get_pending_digests("daily")

        assert TEST_USER_ID in result
        assert len(result[TEST_USER_ID]) == 1

    @pytest.mark.asyncio
    async def test_mark_digests_sent(self, mock_db_session):
        """Sollte Queue-Eintraege als gesendet markieren."""
        from app.services.collaboration.digest_service import DigestService

        mock_result = Mock()
        mock_result.rowcount = 3
        mock_db_session.execute.return_value = mock_result

        service = DigestService(mock_db_session)
        queue_ids = [uuid4(), uuid4(), uuid4()]

        result = await service.mark_digests_sent(queue_ids)

        assert result == 3
        mock_db_session.commit.assert_called()

    @pytest.mark.asyncio
    async def test_mark_digests_sent_empty(self, mock_db_session):
        """Sollte 0 zurueckgeben bei leerer ID-Liste."""
        from app.services.collaboration.digest_service import DigestService

        service = DigestService(mock_db_session)
        result = await service.mark_digests_sent([])

        assert result == 0
        mock_db_session.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_cleanup_old_digests(self, mock_db_session):
        """Sollte alte gesendete Digests loeschen."""
        from app.services.collaboration.digest_service import DigestService

        mock_result = Mock()
        mock_result.rowcount = 10
        mock_db_session.execute.return_value = mock_result

        service = DigestService(mock_db_session)
        result = await service.cleanup_old_digests(days_old=7)

        assert result == 10
        mock_db_session.commit.assert_called()


class TestDigestServiceScheduling:
    """Tests fuer Scheduled Time Calculation."""

    def test_calculate_scheduled_time_immediate(self, mock_db_session):
        """IMMEDIATE sollte aktuelle Zeit zurueckgeben."""
        from app.services.collaboration.digest_service import DigestService
        from app.db.models import DigestFrequency

        service = DigestService(mock_db_session)

        with patch('app.services.collaboration.digest_service.utc_now') as mock_now:
            now = datetime(2026, 1, 17, 10, 30, 0, tzinfo=timezone.utc)
            mock_now.return_value = now

            result = service._calculate_scheduled_time(DigestFrequency.IMMEDIATE.value)

            assert result == now

    def test_calculate_scheduled_time_hourly(self, mock_db_session):
        """HOURLY sollte naechste volle Stunde zurueckgeben."""
        from app.services.collaboration.digest_service import DigestService
        from app.db.models import DigestFrequency

        service = DigestService(mock_db_session)

        with patch('app.services.collaboration.digest_service.utc_now') as mock_now:
            now = datetime(2026, 1, 17, 10, 30, 45, tzinfo=timezone.utc)
            mock_now.return_value = now

            result = service._calculate_scheduled_time(DigestFrequency.HOURLY.value)

            assert result.hour == 11
            assert result.minute == 0
            assert result.second == 0

    def test_calculate_scheduled_time_daily(self, mock_db_session):
        """DAILY sollte morgen 08:00 Uhr zurueckgeben."""
        from app.services.collaboration.digest_service import DigestService
        from app.db.models import DigestFrequency

        service = DigestService(mock_db_session)

        with patch('app.services.collaboration.digest_service.utc_now') as mock_now:
            now = datetime(2026, 1, 17, 10, 30, 0, tzinfo=timezone.utc)
            mock_now.return_value = now

            result = service._calculate_scheduled_time(DigestFrequency.DAILY.value)

            assert result.day == 18
            assert result.hour == 8
            assert result.minute == 0

    def test_calculate_scheduled_time_weekly(self, mock_db_session):
        """WEEKLY sollte naechsten Montag 08:00 Uhr zurueckgeben."""
        from app.services.collaboration.digest_service import DigestService
        from app.db.models import DigestFrequency

        service = DigestService(mock_db_session)

        with patch('app.services.collaboration.digest_service.utc_now') as mock_now:
            # Samstag, 17. Januar 2026 (weekday=5)
            now = datetime(2026, 1, 17, 10, 30, 0, tzinfo=timezone.utc)
            mock_now.return_value = now

            result = service._calculate_scheduled_time(DigestFrequency.WEEKLY.value)

            # Naechster Montag ist der 19. Januar
            assert result.weekday() == 0  # Montag
            assert result.day == 19
            assert result.hour == 8
            assert result.minute == 0


class TestDigestServiceCompilation:
    """Tests fuer Digest Compilation."""

    @pytest.mark.asyncio
    async def test_compile_digest(self, mock_db_session, mock_user, mock_queue_entry):
        """Sollte Digest korrekt kompilieren."""
        from app.services.collaboration.digest_service import DigestService

        # Setup user query mock
        mock_user_result = Mock()
        mock_user_result.scalar_one_or_none.return_value = mock_user
        mock_db_session.execute.return_value = mock_user_result

        service = DigestService(mock_db_session)

        result = await service.compile_digest(
            user_id=TEST_USER_ID,
            queue_entries=[mock_queue_entry],
        )

        assert result["user_id"] == str(TEST_USER_ID)
        assert result["user_email"] == "test@example.com"
        assert result["notification_count"] == 1
        assert "notifications_by_type" in result

    @pytest.mark.asyncio
    async def test_compile_digest_user_not_found(self, mock_db_session):
        """Sollte leeres Dict zurueckgeben wenn User nicht gefunden."""
        from app.services.collaboration.digest_service import DigestService

        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute.return_value = mock_result

        service = DigestService(mock_db_session)

        result = await service.compile_digest(
            user_id=TEST_USER_ID,
            queue_entries=[],
        )

        assert result == {}


class TestDigestServiceRendering:
    """Tests fuer HTML Rendering."""

    def test_render_digest_html(self, mock_db_session):
        """Sollte valides HTML generieren."""
        from app.services.collaboration.digest_service import DigestService
        from app.db.models import DigestFrequency

        service = DigestService(mock_db_session)

        digest_data = {
            "user_name": "Test User",
            "notification_count": 3,
            "notifications_by_type": {
                "task_assigned": [
                    {
                        "id": str(uuid4()),
                        "title": "Neue Aufgabe",
                        "message": "Test-Nachricht",
                        "action_url": "/tasks/1",
                        "created_at": "2026-01-17T10:00:00",
                    }
                ],
            },
        }

        result = service.render_digest_html(digest_data, DigestFrequency.DAILY.value)

        assert "<!DOCTYPE html>" in result
        assert "Tägliche Zusammenfassung" in result
        assert "Test User" in result
        assert "3 neue Benachrichtigungen" in result
        assert "Zugewiesene Aufgaben" in result

    def test_render_digest_subject(self, mock_db_session):
        """Sollte korrekten Email-Betreff generieren."""
        from app.services.collaboration.digest_service import DigestService
        from app.db.models import DigestFrequency

        service = DigestService(mock_db_session)

        digest_data = {"notification_count": 5}

        result = service.render_digest_subject(digest_data, DigestFrequency.DAILY.value)

        assert "Tägliche Zusammenfassung" in result
        assert "5 neue Benachrichtigungen" in result


class TestGetDigestService:
    """Tests fuer Factory Function."""

    def test_get_digest_service(self, mock_db_session):
        """Sollte DigestService-Instanz erstellen."""
        from app.services.collaboration.digest_service import get_digest_service, DigestService

        result = get_digest_service(mock_db_session)

        assert isinstance(result, DigestService)
        assert result.db == mock_db_session
