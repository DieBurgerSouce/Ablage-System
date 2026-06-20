# -*- coding: utf-8 -*-
"""
Unit Tests für Logout mit Token Blacklisting.

Testet:
- Access Token Blacklisting bei Logout
- Refresh Token Blacklisting bei Logout
- Session Revocation
- Blacklisted Token Rejection
- Fail-Closed Behavior

SECURITY FIX: Access Tokens werden jetzt sofort bei Logout ungültig,
nicht erst nach 15 Minuten Ablauf.

Feinpoliert und durchdacht - Enterprise Test Coverage.
"""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
import secrets

# Test markers
pytestmark = [pytest.mark.unit]


class TestLogoutAccessTokenBlacklisting:
    """Tests für Access Token Blacklisting bei Logout."""

    @pytest.fixture
    def mock_user(self):
        """Erstelle Mock-User."""
        user = MagicMock()
        user.id = "test-user-id-12345"
        user.username = "testuser"
        user.email = "test@example.com"
        user.is_active = True
        return user

    @pytest.fixture
    def mock_tokens(self):
        """Erstelle Mock-Token-Daten."""
        return {
            "access_jti": "access-jti-" + secrets.token_hex(16),
            "access_exp": int((datetime.now(timezone.utc) + timedelta(minutes=15)).timestamp()),
            "refresh_jti": "refresh-jti-" + secrets.token_hex(16),
            "refresh_exp": int((datetime.now(timezone.utc) + timedelta(days=7)).timestamp()),
        }

    @pytest.mark.asyncio
    async def test_logout_blacklists_access_token(self, mock_user, mock_tokens):
        """Logout muss Access Token auf Blacklist setzen."""
        from app.api.v1.auth import logout
        from app.db.schemas import LogoutRequest

        blacklisted_tokens = []

        async def mock_blacklist(jti, expires_at):
            blacklisted_tokens.append(jti)

        async def mock_decode(token, expected_type=None):
            if "access" in token:
                return {
                    "jti": mock_tokens["access_jti"],
                    "exp": mock_tokens["access_exp"],
                    "type": "access",
                    "sub": str(mock_user.id)
                }
            return {
                "jti": mock_tokens["refresh_jti"],
                "exp": mock_tokens["refresh_exp"],
                "type": "refresh",
                "sub": str(mock_user.id)
            }

        # Mock request
        mock_request = MagicMock()
        mock_request.headers.get.return_value = "Bearer access-token-123"

        # Mock database session
        mock_db = AsyncMock()

        with patch("app.api.v1.auth.decode_token", side_effect=mock_decode):
            with patch("app.api.v1.auth.blacklist_token", side_effect=mock_blacklist):
                # Mock session manager at the source module
                with patch("app.core.session_manager.get_session_manager") as mock_session_mgr:
                    mock_session_mgr.return_value.revoke_session_by_jti = AsyncMock()

                    logout_data = LogoutRequest(refresh_token=None)
                    result = await logout(mock_request, logout_data, mock_user, mock_db)

        # Access token JTI sollte auf Blacklist sein
        assert mock_tokens["access_jti"] in blacklisted_tokens
        assert result.message == "Erfolgreich abgemeldet"

    @pytest.mark.asyncio
    async def test_logout_blacklists_both_tokens(self, mock_user, mock_tokens):
        """Logout muss sowohl Access als auch Refresh Token blacklisten."""
        from app.api.v1.auth import logout
        from app.db.schemas import LogoutRequest

        blacklisted_tokens = []

        async def mock_blacklist(jti, expires_at):
            blacklisted_tokens.append(jti)

        async def mock_decode(token, expected_type=None):
            if "access" in token:
                return {
                    "jti": mock_tokens["access_jti"],
                    "exp": mock_tokens["access_exp"],
                    "type": "access",
                    "sub": str(mock_user.id)
                }
            return {
                "jti": mock_tokens["refresh_jti"],
                "exp": mock_tokens["refresh_exp"],
                "type": "refresh",
                "sub": str(mock_user.id)
            }

        mock_request = MagicMock()
        mock_request.headers.get.return_value = "Bearer access-token-123"
        mock_db = AsyncMock()

        with patch("app.api.v1.auth.decode_token", side_effect=mock_decode):
            with patch("app.api.v1.auth.blacklist_token", side_effect=mock_blacklist):
                with patch("app.core.session_manager.get_session_manager") as mock_session_mgr:
                    mock_session_mgr.return_value.revoke_session_by_jti = AsyncMock()

                    # Logout mit Refresh Token
                    logout_data = LogoutRequest(refresh_token="refresh-token-456")
                    await logout(mock_request, logout_data, mock_user, mock_db)

        # Beide Token JTIs sollten auf Blacklist sein
        assert mock_tokens["access_jti"] in blacklisted_tokens
        assert mock_tokens["refresh_jti"] in blacklisted_tokens
        assert len(blacklisted_tokens) == 2

    @pytest.mark.asyncio
    async def test_logout_continues_on_blacklist_failure(self, mock_user, mock_tokens):
        """Logout darf nicht fehlschlagen wenn Blacklisting fehlschlägt."""
        from app.api.v1.auth import logout
        from app.db.schemas import LogoutRequest
        from fastapi import HTTPException

        async def mock_blacklist_failing(jti, expires_at):
            raise HTTPException(status_code=503, detail="Redis nicht verfügbar")

        async def mock_decode(token, expected_type=None):
            return {
                "jti": mock_tokens["access_jti"],
                "exp": mock_tokens["access_exp"],
                "type": "access",
                "sub": str(mock_user.id)
            }

        mock_request = MagicMock()
        mock_request.headers.get.return_value = "Bearer access-token-123"
        mock_db = AsyncMock()

        with patch("app.api.v1.auth.decode_token", side_effect=mock_decode):
            with patch("app.api.v1.auth.blacklist_token", side_effect=mock_blacklist_failing):
                with patch("app.core.session_manager.get_session_manager") as mock_session_mgr:
                    mock_session_mgr.return_value.revoke_session_by_jti = AsyncMock()

                    logout_data = LogoutRequest(refresh_token=None)
                    # Sollte NICHT fehlschlagen
                    result = await logout(mock_request, logout_data, mock_user, mock_db)

        # Logout sollte trotzdem erfolgreich sein
        assert result.message == "Erfolgreich abgemeldet"


class TestBlacklistedTokenRejection:
    """Tests dass blacklisted Tokens abgelehnt werden."""

    @pytest.mark.asyncio
    async def test_blacklisted_access_token_rejected(self):
        """Blacklisted Access Token muss abgelehnt werden."""
        from app.core.security import decode_token, blacklist_token
        from app.core.security import create_access_token
        from fastapi import HTTPException

        # Erstelle Token
        token = create_access_token({"sub": "user123", "email": "test@example.com"})

        # Decode um JTI zu bekommen
        import jwt  # Sprint 0 / G02: PyJWT statt python-jose
        from app.core.config import settings
        secret_key = settings.SECRET_KEY.get_secret_value()
        payload = jwt.decode(token, secret_key, algorithms=[settings.ALGORITHM])
        jti = payload["jti"]
        exp = payload["exp"]

        # Blacklist Token
        exp_datetime = datetime.fromtimestamp(exp, tz=timezone.utc)

        # Mock Redis für diesen Test
        with patch("app.core.security_auth._get_redis_client") as mock_redis:
            mock_client = AsyncMock()
            mock_redis.return_value = mock_client
            mock_client.setex = AsyncMock()
            mock_client.exists = AsyncMock(return_value=True)

            await blacklist_token(jti, exp_datetime)

            # Versuche Token zu dekodieren - sollte fehlschlagen
            with pytest.raises(HTTPException) as exc_info:
                await decode_token(token)

            assert exc_info.value.status_code == 401
            assert "widerrufen" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_valid_token_accepted(self):
        """Nicht-blacklisted Token muss akzeptiert werden."""
        from app.core.security import decode_token, create_access_token

        # Erstelle Token
        token = create_access_token({"sub": "user123", "email": "test@example.com"})

        # Mock Redis - Token nicht auf Blacklist
        with patch("app.core.security_auth._get_redis_client") as mock_redis:
            mock_client = AsyncMock()
            mock_redis.return_value = mock_client
            mock_client.exists = AsyncMock(return_value=False)

            # Token sollte erfolgreich dekodiert werden
            payload = await decode_token(token)

            assert payload["sub"] == "user123"
            assert payload["type"] == "access"


class TestSessionRevocation:
    """Tests für Session Revocation bei Logout."""

    @pytest.mark.asyncio
    async def test_logout_revokes_session(self):
        """Logout muss Session in Datenbank widerrufen."""
        from app.api.v1.auth import logout
        from app.db.schemas import LogoutRequest

        mock_user = MagicMock()
        mock_user.id = "test-user-id"
        mock_user.username = "testuser"

        session_revoked = False
        revoked_jti = None

        async def mock_revoke_session(db, jti):
            nonlocal session_revoked, revoked_jti
            session_revoked = True
            revoked_jti = jti

        async def mock_decode(token, expected_type=None):
            return {
                "jti": "session-jti-123",
                "exp": int((datetime.now(timezone.utc) + timedelta(minutes=15)).timestamp()),
                "type": "access",
                "sub": str(mock_user.id)
            }

        mock_request = MagicMock()
        mock_request.headers.get.return_value = "Bearer access-token"
        mock_db = AsyncMock()

        with patch("app.api.v1.auth.decode_token", side_effect=mock_decode):
            with patch("app.api.v1.auth.blacklist_token", AsyncMock()):
                with patch("app.core.session_manager.get_session_manager") as mock_session_mgr:
                    mock_mgr_instance = MagicMock()
                    mock_mgr_instance.revoke_session_by_jti = mock_revoke_session
                    mock_session_mgr.return_value = mock_mgr_instance

                    logout_data = LogoutRequest(refresh_token=None)
                    await logout(mock_request, logout_data, mock_user, mock_db)

        assert session_revoked is True
        assert revoked_jti == "session-jti-123"


class TestLogoutWithoutAuthHeader:
    """Tests für Logout ohne Authorization Header."""

    @pytest.mark.asyncio
    async def test_logout_without_bearer_header(self):
        """Logout ohne Bearer Header sollte graceful behandelt werden."""
        from app.api.v1.auth import logout
        from app.db.schemas import LogoutRequest

        mock_user = MagicMock()
        mock_user.id = "test-user-id"
        mock_user.username = "testuser"

        mock_request = MagicMock()
        mock_request.headers.get.return_value = ""  # Kein Auth Header
        mock_db = AsyncMock()

        with patch("app.api.v1.auth.decode_token", AsyncMock()):
            with patch("app.api.v1.auth.blacklist_token", AsyncMock()):
                with patch("app.core.session_manager.get_session_manager") as mock_session_mgr:
                    mock_session_mgr.return_value.revoke_session_by_jti = AsyncMock()

                    logout_data = LogoutRequest(refresh_token=None)
                    result = await logout(mock_request, logout_data, mock_user, mock_db)

        # Logout sollte trotzdem erfolgreich sein
        assert result.message == "Erfolgreich abgemeldet"


class TestLogoutTokenExpiration:
    """Tests für korrekte TTL bei Token Blacklisting."""

    @pytest.mark.asyncio
    async def test_blacklist_uses_correct_ttl(self):
        """Blacklist muss korrekte TTL basierend auf Token-Expiration verwenden."""
        from app.core.security import blacklist_token_redis

        captured_ttl = None
        captured_key = None

        async def mock_setex(key, ttl, value):
            nonlocal captured_ttl, captured_key
            captured_key = key
            captured_ttl = ttl

        mock_redis = AsyncMock()
        mock_redis.setex = mock_setex

        with patch("app.core.security_auth._get_redis_client", AsyncMock(return_value=mock_redis)):
            # Token läuft in 10 Minuten ab
            expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)
            await blacklist_token_redis("test-jti", expires_at)

        # TTL sollte ca. 600 Sekunden sein (10 Minuten)
        assert captured_ttl is not None
        assert 590 <= captured_ttl <= 610  # Toleranz für Ausführungszeit
        assert "token:blacklist:test-jti" == captured_key


class TestLogoutResponseMessage:
    """Tests für Logout Response Messages."""

    @pytest.mark.asyncio
    async def test_logout_returns_german_message(self):
        """Logout muss deutsche Erfolgsmeldung zurückgeben."""
        from app.api.v1.auth import logout
        from app.db.schemas import LogoutRequest

        mock_user = MagicMock()
        mock_user.id = "test-user-id"
        mock_user.username = "testuser"

        mock_request = MagicMock()
        mock_request.headers.get.return_value = ""
        mock_db = AsyncMock()

        with patch("app.api.v1.auth.decode_token", AsyncMock()):
            with patch("app.api.v1.auth.blacklist_token", AsyncMock()):
                with patch("app.core.session_manager.get_session_manager") as mock_session_mgr:
                    mock_session_mgr.return_value.revoke_session_by_jti = AsyncMock()

                    logout_data = LogoutRequest(refresh_token=None)
                    result = await logout(mock_request, logout_data, mock_user, mock_db)

        # Deutsche Meldungen
        assert "abgemeldet" in result.message.lower()
        assert "widerrufen" in result.detail.lower() or "anmelden" in result.detail.lower()


class TestBlacklistStatistics:
    """Tests für Blacklist Statistiken."""

    @pytest.mark.asyncio
    async def test_get_blacklist_stats_returns_info(self):
        """get_blacklist_stats muss Statistiken zurückgeben."""
        from app.core.security import get_blacklist_stats

        mock_redis = AsyncMock()
        mock_redis.scan = AsyncMock(return_value=(0, ["token:blacklist:1", "token:blacklist:2"]))

        with patch("app.core.security_auth._get_redis_client", AsyncMock(return_value=mock_redis)):
            stats = await get_blacklist_stats()

        assert "redis_available" in stats
        assert "fallback_count" in stats
        assert "storage_type" in stats

    @pytest.mark.asyncio
    async def test_get_blacklist_stats_without_redis(self):
        """get_blacklist_stats ohne Redis zeigt Fallback-Info."""
        from app.core.security import get_blacklist_stats

        with patch("app.core.security_auth._get_redis_client", AsyncMock(return_value=None)):
            stats = await get_blacklist_stats()

        assert stats["redis_available"] is False
        assert stats["storage_type"] == "in-memory"


class TestTokenTypeValidation:
    """Tests für Token-Typ-Validierung bei Blacklisting."""

    @pytest.mark.asyncio
    async def test_access_token_has_correct_type_in_payload(self):
        """Access Token muss type='access' haben."""
        from app.core.security import create_access_token
        import jwt  # Sprint 0 / G02: PyJWT statt python-jose
        from app.core.config import settings

        token = create_access_token({"sub": "user123"})
        secret_key = settings.SECRET_KEY.get_secret_value()
        payload = jwt.decode(token, secret_key, algorithms=[settings.ALGORITHM])

        assert payload["type"] == "access"
        assert "jti" in payload

    @pytest.mark.asyncio
    async def test_refresh_token_has_correct_type_in_payload(self):
        """Refresh Token muss type='refresh' haben."""
        from app.core.security import create_refresh_token
        import jwt  # Sprint 0 / G02: PyJWT statt python-jose
        from app.core.config import settings

        token = create_refresh_token({"sub": "user123"})
        secret_key = settings.SECRET_KEY.get_secret_value()
        payload = jwt.decode(token, secret_key, algorithms=[settings.ALGORITHM])

        assert payload["type"] == "refresh"
        assert "jti" in payload


class TestConcurrentBlacklisting:
    """Tests für gleichzeitiges Blacklisting."""

    @pytest.mark.asyncio
    async def test_concurrent_blacklist_operations(self):
        """Gleichzeitige Blacklist-Operationen müssen thread-safe sein."""
        import asyncio
        from app.core.security import blacklist_token_redis

        blacklisted = []

        async def mock_setex(key, ttl, value):
            blacklisted.append(key)

        mock_redis = AsyncMock()
        mock_redis.setex = mock_setex

        with patch("app.core.security_auth._get_redis_client", AsyncMock(return_value=mock_redis)):
            # Starte 10 gleichzeitige Blacklist-Operationen
            expires = datetime.now(timezone.utc) + timedelta(hours=1)
            tasks = [
                blacklist_token_redis(f"jti-{i}", expires)
                for i in range(10)
            ]
            await asyncio.gather(*tasks)

        # Alle 10 sollten blacklisted sein
        assert len(blacklisted) == 10
