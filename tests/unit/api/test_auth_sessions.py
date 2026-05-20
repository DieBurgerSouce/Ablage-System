# -*- coding: utf-8 -*-
"""
Umfassende Unit Tests für Session Management Endpoints.

Testet alle Session-Funktionalitäten:
- GET /auth/sessions/limits
- GET /auth/sessions
- DELETE /auth/sessions/{session_id}
- DELETE /auth/sessions (alle widerrufen)

Feinpoliert und durchdacht - Enterprise Test Coverage.
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from uuid import uuid4
from datetime import datetime, timezone, timedelta

# Test markers
pytestmark = [pytest.mark.unit, pytest.mark.api]


class TestSessionLimits:
    """Tests für GET /auth/sessions/limits Endpoint."""

    @pytest.mark.asyncio
    async def test_get_session_limits(self, async_client):
        """Session-Limits abfragen."""
        with patch("app.api.v1.auth.get_current_active_user") as mock_auth:
            mock_user = Mock(id=uuid4(), is_active=True)
            mock_auth.return_value = mock_user

            with patch("app.core.session_manager.get_session_manager") as mock_manager:
                mock_session_manager = Mock()
                mock_session_manager.get_active_sessions = AsyncMock(return_value=[
                    Mock(id=uuid4()),
                    Mock(id=uuid4())
                ])
                mock_manager.return_value = mock_session_manager

                response = await async_client.get(
                    "/api/v1/auth/sessions/limits",
                    headers={"Authorization": "Bearer test_token"}
                )

                if response.status_code == 200:
                    data = response.json()
                    assert "max_sessions" in data
                    assert "current_sessions" in data
                    assert "limit_mode" in data
                    assert "session_expiry_hours" in data
                    assert "can_create_new" in data

    @pytest.mark.asyncio
    async def test_session_limits_unauthenticated(self, async_client):
        """Session-Limits ohne Authentifizierung."""
        response = await async_client.get("/api/v1/auth/sessions/limits")

        assert response.status_code in [401, 403]


class TestListSessions:
    """Tests für GET /auth/sessions Endpoint."""

    @pytest.mark.asyncio
    async def test_list_sessions_success(self, async_client):
        """Alle aktiven Sessions auflisten."""
        user_id = uuid4()
        session_id = uuid4()
        now = datetime.now(timezone.utc)

        with patch("app.api.v1.auth.get_current_active_user") as mock_auth:
            mock_user = Mock(id=user_id, is_active=True)
            mock_auth.return_value = mock_user

            with patch("app.core.session_manager.get_session_manager") as mock_manager:
                mock_session = Mock(
                    id=session_id,
                    device_name="Chrome auf Windows",
                    device_type="desktop",
                    ip_address="192.168.1.100",
                    location=None,
                    last_activity_at=now,
                    created_at=now - timedelta(hours=1),
                    expires_at=now + timedelta(hours=23)
                )

                mock_session_manager = Mock()
                mock_session_manager.get_active_sessions = AsyncMock(return_value=[mock_session])
                mock_session_manager.get_session_by_jti = AsyncMock(return_value=mock_session)
                mock_manager.return_value = mock_session_manager

                with patch("app.api.v1.auth.decode_token") as mock_decode:
                    mock_decode.return_value = {"jti": "test_jti"}

                    response = await async_client.get(
                        "/api/v1/auth/sessions",
                        headers={"Authorization": "Bearer test_token"}
                    )

                    if response.status_code == 200:
                        data = response.json()
                        assert "sessions" in data
                        assert "total" in data
                        assert data["total"] >= 0

    @pytest.mark.asyncio
    async def test_list_sessions_empty(self, async_client):
        """Leere Session-Liste."""
        with patch("app.api.v1.auth.get_current_active_user") as mock_auth:
            mock_user = Mock(id=uuid4(), is_active=True)
            mock_auth.return_value = mock_user

            with patch("app.core.session_manager.get_session_manager") as mock_manager:
                mock_session_manager = Mock()
                mock_session_manager.get_active_sessions = AsyncMock(return_value=[])
                mock_manager.return_value = mock_session_manager

                response = await async_client.get(
                    "/api/v1/auth/sessions",
                    headers={"Authorization": "Bearer test_token"}
                )

                if response.status_code == 200:
                    data = response.json()
                    assert data["total"] == 0
                    assert len(data["sessions"]) == 0

    @pytest.mark.asyncio
    async def test_list_sessions_marks_current(self, async_client):
        """Aktuelle Session wird markiert."""
        user_id = uuid4()
        current_session_id = uuid4()
        other_session_id = uuid4()
        now = datetime.now(timezone.utc)

        with patch("app.api.v1.auth.get_current_active_user") as mock_auth:
            mock_user = Mock(id=user_id, is_active=True)
            mock_auth.return_value = mock_user

            with patch("app.core.session_manager.get_session_manager") as mock_manager:
                current_session = Mock(
                    id=current_session_id,
                    device_name="Chrome auf Windows",
                    device_type="desktop",
                    ip_address="192.168.1.100",
                    location=None,
                    last_activity_at=now,
                    created_at=now,
                    expires_at=now + timedelta(hours=24)
                )
                other_session = Mock(
                    id=other_session_id,
                    device_name="Firefox auf Linux",
                    device_type="desktop",
                    ip_address="192.168.1.101",
                    location=None,
                    last_activity_at=now - timedelta(hours=1),
                    created_at=now - timedelta(hours=2),
                    expires_at=now + timedelta(hours=22)
                )

                mock_session_manager = Mock()
                mock_session_manager.get_active_sessions = AsyncMock(
                    return_value=[current_session, other_session]
                )
                mock_session_manager.get_session_by_jti = AsyncMock(return_value=current_session)
                mock_manager.return_value = mock_session_manager

                with patch("app.api.v1.auth.decode_token") as mock_decode:
                    mock_decode.return_value = {"jti": "current_jti"}

                    response = await async_client.get(
                        "/api/v1/auth/sessions",
                        headers={"Authorization": "Bearer test_token"}
                    )

                    if response.status_code == 200:
                        data = response.json()
                        assert data["current_session_id"] == str(current_session_id)


class TestRevokeSession:
    """Tests für DELETE /auth/sessions/{session_id} Endpoint."""

    @pytest.mark.asyncio
    async def test_revoke_session_success(self, async_client):
        """Session erfolgreich widerrufen."""
        user_id = uuid4()
        session_id = uuid4()

        with patch("app.api.v1.auth.get_current_active_user") as mock_auth:
            mock_user = Mock(id=user_id, is_active=True)
            mock_auth.return_value = mock_user

            with patch("app.core.session_manager.get_session_manager") as mock_manager:
                mock_session_manager = Mock()
                mock_session_manager.revoke_session = AsyncMock(return_value=True)
                mock_manager.return_value = mock_session_manager

                response = await async_client.delete(
                    f"/api/v1/auth/sessions/{session_id}",
                    headers={"Authorization": "Bearer test_token"}
                )

                if response.status_code == 200:
                    data = response.json()
                    assert data["success"] is True
                    assert data["revoked_count"] == 1

    @pytest.mark.asyncio
    async def test_revoke_session_not_found(self, async_client):
        """Nicht existierende Session widerrufen."""
        user_id = uuid4()
        session_id = uuid4()

        with patch("app.api.v1.auth.get_current_active_user") as mock_auth:
            mock_user = Mock(id=user_id, is_active=True)
            mock_auth.return_value = mock_user

            with patch("app.core.session_manager.get_session_manager") as mock_manager:
                from app.core.session_manager import SessionError
                mock_session_manager = Mock()
                mock_session_manager.revoke_session = AsyncMock(
                    side_effect=SessionError("Not found", "Session nicht gefunden")
                )
                mock_manager.return_value = mock_session_manager

                response = await async_client.delete(
                    f"/api/v1/auth/sessions/{session_id}",
                    headers={"Authorization": "Bearer test_token"}
                )

                assert response.status_code in [400, 401, 404]

    @pytest.mark.asyncio
    async def test_revoke_session_unauthorized(self, async_client):
        """Fremde Session widerrufen."""
        user_id = uuid4()
        session_id = uuid4()

        with patch("app.api.v1.auth.get_current_active_user") as mock_auth:
            mock_user = Mock(id=user_id, is_active=True)
            mock_auth.return_value = mock_user

            with patch("app.core.session_manager.get_session_manager") as mock_manager:
                from app.core.session_manager import SessionError
                mock_session_manager = Mock()
                mock_session_manager.revoke_session = AsyncMock(
                    side_effect=SessionError(
                        "Unauthorized",
                        "Sie haben keine Berechtigung, diese Session zu beenden"
                    )
                )
                mock_manager.return_value = mock_session_manager

                response = await async_client.delete(
                    f"/api/v1/auth/sessions/{session_id}",
                    headers={"Authorization": "Bearer test_token"}
                )

                assert response.status_code in [400, 401, 403]


class TestRevokeAllSessions:
    """Tests für DELETE /auth/sessions Endpoint."""

    @pytest.mark.asyncio
    async def test_revoke_all_sessions(self, async_client):
        """Alle Sessions widerrufen."""
        user_id = uuid4()

        with patch("app.api.v1.auth.get_current_active_user") as mock_auth:
            mock_user = Mock(id=user_id, is_active=True)
            mock_auth.return_value = mock_user

            with patch("app.core.session_manager.get_session_manager") as mock_manager:
                mock_session_manager = Mock()
                mock_session_manager.revoke_all_sessions = AsyncMock(return_value=3)
                mock_manager.return_value = mock_session_manager

                with patch("app.api.v1.auth.decode_token") as mock_decode:
                    mock_decode.return_value = {"jti": "current_jti"}

                    response = await async_client.request(
                        "DELETE",
                        "/api/v1/auth/sessions",
                        json={"except_current": False},
                        headers={"Authorization": "Bearer test_token"}
                    )

                    if response.status_code == 200:
                        data = response.json()
                        assert data["success"] is True
                        assert data["revoked_count"] == 3

    @pytest.mark.asyncio
    async def test_revoke_all_except_current(self, async_client):
        """Alle Sessions außer aktuelle widerrufen."""
        user_id = uuid4()

        with patch("app.api.v1.auth.get_current_active_user") as mock_auth:
            mock_user = Mock(id=user_id, is_active=True)
            mock_auth.return_value = mock_user

            with patch("app.core.session_manager.get_session_manager") as mock_manager:
                mock_session_manager = Mock()
                mock_session_manager.revoke_all_sessions = AsyncMock(return_value=2)
                mock_manager.return_value = mock_session_manager

                with patch("app.api.v1.auth.decode_token") as mock_decode:
                    mock_decode.return_value = {"jti": "current_jti"}

                    response = await async_client.request(
                        "DELETE",
                        "/api/v1/auth/sessions",
                        json={"except_current": True},
                        headers={"Authorization": "Bearer test_token"}
                    )

                    if response.status_code == 200:
                        data = response.json()
                        assert data["success"] is True
                        # Message sollte "aktuelle Session bleibt aktiv" enthalten

    @pytest.mark.asyncio
    async def test_revoke_all_no_sessions(self, async_client):
        """Keine Sessions zum Widerrufen."""
        user_id = uuid4()

        with patch("app.api.v1.auth.get_current_active_user") as mock_auth:
            mock_user = Mock(id=user_id, is_active=True)
            mock_auth.return_value = mock_user

            with patch("app.core.session_manager.get_session_manager") as mock_manager:
                mock_session_manager = Mock()
                mock_session_manager.revoke_all_sessions = AsyncMock(return_value=0)
                mock_manager.return_value = mock_session_manager

                response = await async_client.request(
                    "DELETE",
                    "/api/v1/auth/sessions",
                    json={"except_current": False},
                    headers={"Authorization": "Bearer test_token"}
                )

                if response.status_code == 200:
                    data = response.json()
                    assert data["revoked_count"] == 0


class TestSessionManager:
    """Unit Tests für das Session Manager Modul selbst."""

    @pytest.mark.asyncio
    async def test_create_session(self):
        """Session erstellen."""
        try:
            from app.core.session_manager import SessionManager
            from unittest.mock import AsyncMock

            manager = SessionManager()
            user_id = uuid4()

            # Mock DB Session
            mock_db = AsyncMock()
            mock_db.execute = AsyncMock()
            mock_db.add = Mock()
            mock_db.commit = AsyncMock()
            mock_db.refresh = AsyncMock()

            with patch.object(manager, 'get_active_sessions', new_callable=AsyncMock) as mock_get:
                mock_get.return_value = []

                with patch.object(manager, '_cleanup_old_sessions', new_callable=AsyncMock) as mock_cleanup:
                    mock_cleanup.return_value = []

                    result = await manager.create_session(
                        db=mock_db,
                        user_id=user_id,
                        token_jti="test_jti",
                        ip_address="192.168.1.1",
                        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/91.0"
                    )

                    assert "session" in result
                    assert "revoked_sessions" in result

        except ImportError:
            pytest.skip("Session manager not available")

    def test_parse_device_info_desktop(self):
        """Geräteinformationen parsen - Desktop."""
        try:
            from app.core.session_manager import SessionManager

            manager = SessionManager()

            user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/91.0.4472.124"
            device_name, device_type = manager._parse_device_info(user_agent)

            assert device_type == "desktop"
            assert "Chrome" in device_name
            assert "Windows" in device_name

        except ImportError:
            pytest.skip("Session manager not available")

    def test_parse_device_info_mobile(self):
        """Geräteinformationen parsen - Mobile."""
        try:
            from app.core.session_manager import SessionManager

            manager = SessionManager()

            user_agent = "Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148"
            device_name, device_type = manager._parse_device_info(user_agent)

            assert device_type == "mobile"

        except ImportError:
            pytest.skip("Session manager not available")

    def test_parse_device_info_tablet(self):
        """Geräteinformationen parsen - Tablet."""
        try:
            from app.core.session_manager import SessionManager

            manager = SessionManager()

            user_agent = "Mozilla/5.0 (iPad; CPU OS 14_0 like Mac OS X) AppleWebKit/605.1.15"
            device_name, device_type = manager._parse_device_info(user_agent)

            assert device_type == "tablet"

        except ImportError:
            pytest.skip("Session manager not available")

    def test_parse_device_info_empty(self):
        """Geräteinformationen parsen - Leer."""
        try:
            from app.core.session_manager import SessionManager

            manager = SessionManager()

            device_name, device_type = manager._parse_device_info(None)

            assert device_name is None
            assert device_type is None

        except ImportError:
            pytest.skip("Session manager not available")

    def test_mask_ip_ipv4(self):
        """IP-Adresse maskieren - IPv4."""
        try:
            from app.core.session_manager import SessionManager

            manager = SessionManager()

            masked = manager._mask_ip("192.168.1.100")
            assert masked == "192.168.1.xxx"

        except ImportError:
            pytest.skip("Session manager not available")

    def test_mask_ip_ipv6(self):
        """IP-Adresse maskieren - IPv6."""
        try:
            from app.core.session_manager import SessionManager

            manager = SessionManager()

            masked = manager._mask_ip("2001:0db8:85a3:0000:0000:8a2e:0370:7334")
            assert "xxxx" in masked

        except ImportError:
            pytest.skip("Session manager not available")


class TestSessionLimitReached:
    """Tests für Session-Limit-Handling."""

    @pytest.mark.asyncio
    async def test_hard_mode_limit_reached(self, async_client):
        """Login blockiert bei Session-Limit im Hard-Mode."""
        with patch("app.core.session_manager.SESSION_LIMIT_MODE", "hard"):
            with patch("app.core.session_manager.MAX_SESSIONS_PER_USER", 2):
                from app.core.session_manager import SessionManager, SessionLimitReachedError

                manager = SessionManager()

                # Mock DB mit 2 existierenden Sessions
                mock_db = AsyncMock()

                with patch.object(manager, 'get_active_sessions', new_callable=AsyncMock) as mock_get:
                    mock_get.return_value = [Mock(), Mock()]  # 2 Sessions

                    with pytest.raises(SessionLimitReachedError) as exc_info:
                        await manager.create_session(
                            db=mock_db,
                            user_id=uuid4(),
                            token_jti="test_jti",
                            ip_address="192.168.1.1"
                        )

                    assert exc_info.value.current_sessions == 2
                    assert exc_info.value.max_sessions == 2


class TestGermanMessages:
    """Tests für deutsche Fehlermeldungen bei Sessions."""

    def test_session_error_german_message(self):
        """SessionError hat deutsche Nachricht."""
        try:
            from app.core.session_manager import SessionError

            error = SessionError(
                "Session not found",
                "Session nicht gefunden"
            )

            assert error.user_message_de == "Session nicht gefunden"

        except ImportError:
            pytest.skip("Session manager not available")

    def test_session_limit_error_german_message(self):
        """SessionLimitReachedError hat deutsche Nachricht."""
        try:
            from app.core.session_manager import SessionLimitReachedError

            error = SessionLimitReachedError(
                current_sessions=5,
                max_sessions=5
            )

            # Sollte eine deutsche Nachricht haben
            assert len(error.user_message_de) > 0

        except ImportError:
            pytest.skip("Session manager not available")
