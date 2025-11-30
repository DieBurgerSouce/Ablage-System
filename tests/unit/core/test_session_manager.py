"""
Unit tests for Session Manager.

Tests:
- Session erstellen
- Aktive Sessions auflisten
- Session validieren
- Session widerrufen
- Alle Sessions widerrufen
- Abgelaufene Sessions bereinigen
"""

import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from app.core.session_manager import SessionManager, SessionError
from app.db.models import UserSession


@pytest.fixture
def session_manager():
    """Create SessionManager instance."""
    return SessionManager()


@pytest.fixture
def mock_db():
    """Create mock database session."""
    db = AsyncMock()
    return db


@pytest.fixture
def mock_user_session():
    """Create mock user session."""
    session = MagicMock(spec=UserSession)
    session.id = uuid4()
    session.user_id = uuid4()
    session.token_jti = "test-jti-12345"
    session.device_name = "Chrome auf Windows"
    session.device_type = "desktop"
    session.ip_address = "192.168.1.100"
    session.user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0"
    session.location = None
    session.last_activity_at = datetime.now(timezone.utc)
    session.created_at = datetime.now(timezone.utc)
    session.expires_at = datetime.now(timezone.utc) + timedelta(days=7)
    session.is_current = True
    session.revoked = False
    session.revoked_at = None
    return session


class TestCreateSession:
    """Tests for create_session method."""

    @pytest.mark.asyncio
    async def test_create_session_success(self, session_manager, mock_db):
        """Session erfolgreich erstellen."""
        user_id = uuid4()
        token_jti = "test-jti-" + str(uuid4())[:8]
        ip_address = "192.168.1.100"
        user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

        # Mock für alte Sessions abfrage
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result

        session = await session_manager.create_session(
            mock_db,
            user_id,
            token_jti,
            ip_address,
            user_agent
        )

        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()
        mock_db.refresh.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_session_with_location(self, session_manager, mock_db):
        """Session mit Standort erstellen."""
        user_id = uuid4()
        token_jti = "test-jti-" + str(uuid4())[:8]
        ip_address = "192.168.1.100"
        location = "Berlin, DE"

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result

        session = await session_manager.create_session(
            mock_db,
            user_id,
            token_jti,
            ip_address,
            location=location
        )

        mock_db.add.assert_called_once()


class TestGetActiveSessions:
    """Tests for get_active_sessions method."""

    @pytest.mark.asyncio
    async def test_get_active_sessions_success(
        self, session_manager, mock_db, mock_user_session
    ):
        """Aktive Sessions erfolgreich abrufen."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_user_session]
        mock_db.execute.return_value = mock_result

        sessions = await session_manager.get_active_sessions(
            mock_db, mock_user_session.user_id
        )

        assert len(sessions) == 1
        assert sessions[0].id == mock_user_session.id

    @pytest.mark.asyncio
    async def test_get_active_sessions_empty(self, session_manager, mock_db):
        """Keine aktiven Sessions vorhanden."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result

        sessions = await session_manager.get_active_sessions(mock_db, uuid4())

        assert len(sessions) == 0


class TestIsSessionValid:
    """Tests for is_session_valid method."""

    @pytest.mark.asyncio
    async def test_session_valid(self, session_manager, mock_db, mock_user_session):
        """Session ist gültig."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_user_session
        mock_db.execute.return_value = mock_result

        is_valid = await session_manager.is_session_valid(
            mock_db, mock_user_session.token_jti
        )

        assert is_valid is True

    @pytest.mark.asyncio
    async def test_session_not_found(self, session_manager, mock_db):
        """Session nicht gefunden."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        is_valid = await session_manager.is_session_valid(mock_db, "invalid-jti")

        assert is_valid is False

    @pytest.mark.asyncio
    async def test_session_revoked(self, session_manager, mock_db, mock_user_session):
        """Session wurde widerrufen."""
        mock_user_session.revoked = True

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_user_session
        mock_db.execute.return_value = mock_result

        is_valid = await session_manager.is_session_valid(
            mock_db, mock_user_session.token_jti
        )

        assert is_valid is False

    @pytest.mark.asyncio
    async def test_session_expired(self, session_manager, mock_db, mock_user_session):
        """Session ist abgelaufen."""
        mock_user_session.expires_at = datetime.now(timezone.utc) - timedelta(hours=1)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_user_session
        mock_db.execute.return_value = mock_result

        is_valid = await session_manager.is_session_valid(
            mock_db, mock_user_session.token_jti
        )

        assert is_valid is False


class TestRevokeSession:
    """Tests for revoke_session method."""

    @pytest.mark.asyncio
    async def test_revoke_session_success(
        self, session_manager, mock_db, mock_user_session
    ):
        """Session erfolgreich widerrufen."""
        mock_db.get.return_value = mock_user_session

        result = await session_manager.revoke_session(
            mock_db,
            mock_user_session.id,
            mock_user_session.user_id
        )

        assert result is True
        assert mock_user_session.revoked is True
        assert mock_user_session.revoked_at is not None
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_revoke_session_not_found(self, session_manager, mock_db):
        """Session nicht gefunden."""
        mock_db.get.return_value = None

        with pytest.raises(SessionError) as exc_info:
            await session_manager.revoke_session(mock_db, uuid4(), uuid4())

        assert "nicht gefunden" in str(exc_info.value.user_message_de)

    @pytest.mark.asyncio
    async def test_revoke_session_wrong_user(
        self, session_manager, mock_db, mock_user_session
    ):
        """Falscher Benutzer versucht Session zu widerrufen."""
        mock_db.get.return_value = mock_user_session
        different_user_id = uuid4()

        with pytest.raises(SessionError) as exc_info:
            await session_manager.revoke_session(
                mock_db, mock_user_session.id, different_user_id
            )

        assert "keine Berechtigung" in str(exc_info.value.user_message_de)

    @pytest.mark.asyncio
    async def test_revoke_session_already_revoked(
        self, session_manager, mock_db, mock_user_session
    ):
        """Session bereits widerrufen."""
        mock_user_session.revoked = True
        mock_db.get.return_value = mock_user_session

        with pytest.raises(SessionError) as exc_info:
            await session_manager.revoke_session(
                mock_db,
                mock_user_session.id,
                mock_user_session.user_id
            )

        assert "bereits beendet" in str(exc_info.value.user_message_de)


class TestRevokeAllSessions:
    """Tests for revoke_all_sessions method."""

    @pytest.mark.asyncio
    async def test_revoke_all_sessions_success(self, session_manager, mock_db):
        """Alle Sessions erfolgreich widerrufen."""
        user_id = uuid4()

        mock_result = MagicMock()
        mock_result.rowcount = 3
        mock_db.execute.return_value = mock_result

        count = await session_manager.revoke_all_sessions(mock_db, user_id)

        assert count == 3
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_revoke_all_except_current(self, session_manager, mock_db):
        """Alle Sessions außer aktueller widerrufen."""
        user_id = uuid4()
        current_jti = "current-jti-12345"

        mock_result = MagicMock()
        mock_result.rowcount = 2
        mock_db.execute.return_value = mock_result

        count = await session_manager.revoke_all_sessions(
            mock_db,
            user_id,
            except_current=True,
            current_jti=current_jti
        )

        assert count == 2
        mock_db.commit.assert_called_once()


class TestRevokeSessionByJti:
    """Tests for revoke_session_by_jti method."""

    @pytest.mark.asyncio
    async def test_revoke_by_jti_success(self, session_manager, mock_db):
        """Session per JTI erfolgreich widerrufen."""
        mock_result = MagicMock()
        mock_result.rowcount = 1
        mock_db.execute.return_value = mock_result

        result = await session_manager.revoke_session_by_jti(
            mock_db, "test-jti-12345"
        )

        assert result is True
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_revoke_by_jti_not_found(self, session_manager, mock_db):
        """Session per JTI nicht gefunden."""
        mock_result = MagicMock()
        mock_result.rowcount = 0
        mock_db.execute.return_value = mock_result

        result = await session_manager.revoke_session_by_jti(
            mock_db, "invalid-jti"
        )

        assert result is False


class TestCleanupExpiredSessions:
    """Tests for cleanup_expired_sessions method."""

    @pytest.mark.asyncio
    async def test_cleanup_expired_sessions(self, session_manager, mock_db):
        """Abgelaufene Sessions bereinigen."""
        mock_result = MagicMock()
        mock_result.rowcount = 5
        mock_db.execute.return_value = mock_result

        count = await session_manager.cleanup_expired_sessions(mock_db)

        assert count == 5
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_cleanup_no_expired_sessions(self, session_manager, mock_db):
        """Keine abgelaufenen Sessions vorhanden."""
        mock_result = MagicMock()
        mock_result.rowcount = 0
        mock_db.execute.return_value = mock_result

        count = await session_manager.cleanup_expired_sessions(mock_db)

        assert count == 0


class TestParseDeviceInfo:
    """Tests for _parse_device_info method."""

    def test_parse_chrome_windows(self, session_manager):
        """Chrome auf Windows erkennen."""
        user_agent = (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )

        device_name, device_type = session_manager._parse_device_info(user_agent)

        assert "Chrome" in device_name
        assert "Windows" in device_name
        assert device_type == "desktop"

    def test_parse_safari_iphone(self, session_manager):
        """Safari auf iPhone erkennen."""
        user_agent = (
            "Mozilla/5.0 (iPhone; CPU iPhone OS 17_1 like Mac OS X) "
            "AppleWebKit/605.1.15 (KHTML, like Gecko) "
            "Version/17.0 Mobile/15E148 Safari/604.1"
        )

        device_name, device_type = session_manager._parse_device_info(user_agent)

        assert device_type == "mobile"

    def test_parse_firefox_linux(self, session_manager):
        """Firefox auf Linux erkennen."""
        user_agent = (
            "Mozilla/5.0 (X11; Linux x86_64; rv:120.0) "
            "Gecko/20100101 Firefox/120.0"
        )

        device_name, device_type = session_manager._parse_device_info(user_agent)

        assert "Firefox" in device_name
        assert "Linux" in device_name
        assert device_type == "desktop"

    def test_parse_none_user_agent(self, session_manager):
        """Kein User-Agent vorhanden."""
        device_name, device_type = session_manager._parse_device_info(None)

        assert device_name is None
        assert device_type is None


class TestMaskIP:
    """Tests for _mask_ip method."""

    def test_mask_ipv4(self, session_manager):
        """IPv4-Adresse maskieren."""
        masked = session_manager._mask_ip("192.168.1.100")

        assert masked == "192.168.1.xxx"

    def test_mask_ipv6(self, session_manager):
        """IPv6-Adresse maskieren."""
        masked = session_manager._mask_ip("2001:0db8:85a3:0000:0000:8a2e:0370:7334")

        assert masked.startswith("2001:0db8:85a3:0000:")
        assert masked.endswith("xxxx:xxxx:xxxx:xxxx")


class TestUpdateActivity:
    """Tests for update_activity method."""

    @pytest.mark.asyncio
    async def test_update_activity_success(self, session_manager, mock_db):
        """Aktivität erfolgreich aktualisieren."""
        mock_result = MagicMock()
        mock_result.rowcount = 1
        mock_db.execute.return_value = mock_result

        result = await session_manager.update_activity(
            mock_db, "test-jti-12345", "192.168.1.101"
        )

        assert result is True
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_activity_session_not_found(self, session_manager, mock_db):
        """Session für Aktivitäts-Update nicht gefunden."""
        mock_result = MagicMock()
        mock_result.rowcount = 0
        mock_db.execute.return_value = mock_result

        result = await session_manager.update_activity(
            mock_db, "invalid-jti", "192.168.1.101"
        )

        assert result is False
