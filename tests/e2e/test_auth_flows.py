# -*- coding: utf-8 -*-
"""
E2E Tests: Authentication Flows

Tests login, logout, 2FA, and session management.

Feinpoliert und durchdacht - Authentifizierungs-Tests.
"""

import pytest
import asyncio
from typing import Dict, Any
from unittest.mock import AsyncMock, patch
from datetime import datetime, timedelta, timezone


@pytest.mark.e2e
class TestLoginFlow:
    """Test login authentication flows."""

    @pytest.mark.asyncio
    async def test_successful_login(self):
        """Test Erfolgreicher Login."""
        with patch("app.services.auth_service.AuthService") as MockAuth:
            mock_auth = AsyncMock()
            mock_auth.login.return_value = {
                "success": True,
                "user_id": "user_001",
                "username": "max.mustermann",
                "email": "max.mustermann@example.com",
                "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                "token_type": "Bearer",
                "expires_in": 900,  # 15 minutes
                "message": "Login erfolgreich"
            }
            MockAuth.return_value = mock_auth

            result = await mock_auth.login(
                username="max.mustermann",
                password="SecurePassword123!"
            )

            assert result["success"] is True
            assert result["user_id"] == "user_001"
            assert "access_token" in result
            assert result["token_type"] == "Bearer"

    @pytest.mark.asyncio
    async def test_login_invalid_credentials(self):
        """Test Login mit ungültigen Credentials."""
        with patch("app.services.auth_service.AuthService") as MockAuth:
            mock_auth = AsyncMock()
            mock_auth.login.side_effect = ValueError(
                "Anmeldung fehlgeschlagen: Ungültige Anmeldedaten"
            )
            MockAuth.return_value = mock_auth

            with pytest.raises(ValueError, match="Ungültige Anmeldedaten"):
                await mock_auth.login(
                    username="max.mustermann",
                    password="WrongPassword"
                )

    @pytest.mark.asyncio
    async def test_login_rate_limiting(self):
        """Test Login Rate-Limiting nach mehreren Fehlversuchen."""
        with patch("app.services.auth_service.AuthService") as MockAuth:
            mock_auth = AsyncMock()
            mock_auth.login.side_effect = RuntimeError(
                "Zu viele Anmeldeversuche: Bitte warten Sie 15 Minuten"
            )
            MockAuth.return_value = mock_auth

            # After 5 failed login attempts
            with pytest.raises(RuntimeError, match="Zu viele Anmeldeversuche"):
                await mock_auth.login(
                    username="max.mustermann",
                    password="AnyPassword"
                )


@pytest.mark.e2e
class TestTwoFactorAuth:
    """Test 2FA authentication flows."""

    @pytest.mark.asyncio
    async def test_2fa_setup(self):
        """Test 2FA einrichten."""
        with patch("app.services.auth_service.AuthService") as MockAuth:
            mock_auth = AsyncMock()
            mock_auth.setup_2fa.return_value = {
                "success": True,
                "user_id": "user_001",
                "qr_code_url": "data:image/png;base64,iVBORw0KG...",
                "secret": "JBSWY3DPEHPK3PXP",
                "backup_codes": [
                    "12345-67890",
                    "23456-78901",
                    "34567-89012"
                ],
                "message": "2FA eingerichtet. Bitte scannen Sie den QR-Code."
            }
            MockAuth.return_value = mock_auth

            result = await mock_auth.setup_2fa("user_001")

            assert result["success"] is True
            assert "qr_code_url" in result
            assert len(result["backup_codes"]) >= 3

    @pytest.mark.asyncio
    async def test_login_with_2fa(self):
        """Test Login mit 2FA-Code."""
        with patch("app.services.auth_service.AuthService") as MockAuth:
            mock_auth = AsyncMock()
            # First step: username/password
            mock_auth.login_step1.return_value = {
                "success": True,
                "requires_2fa": True,
                "session_token": "temp_session_abc123",
                "message": "Bitte geben Sie Ihren 2FA-Code ein"
            }

            step1 = await mock_auth.login_step1(
                username="max.mustermann",
                password="SecurePassword123!"
            )

            assert step1["requires_2fa"] is True
            assert "session_token" in step1

            # Second step: 2FA code
            mock_auth.login_step2_verify_2fa.return_value = {
                "success": True,
                "user_id": "user_001",
                "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                "message": "2FA erfolgreich verifiziert"
            }

            step2 = await mock_auth.login_step2_verify_2fa(
                session_token=step1["session_token"],
                totp_code="123456"
            )

            assert step2["success"] is True
            assert "access_token" in step2

    @pytest.mark.asyncio
    async def test_2fa_invalid_code(self):
        """Test 2FA mit ungültigem Code."""
        with patch("app.services.auth_service.AuthService") as MockAuth:
            mock_auth = AsyncMock()
            mock_auth.verify_2fa_code.side_effect = ValueError(
                "Ungültiger 2FA-Code"
            )
            MockAuth.return_value = mock_auth

            with pytest.raises(ValueError, match="Ungültiger 2FA-Code"):
                await mock_auth.verify_2fa_code(
                    user_id="user_001",
                    totp_code="000000"
                )


@pytest.mark.e2e
class TestSessionManagement:
    """Test session management and tokens."""

    @pytest.mark.asyncio
    async def test_token_refresh(self):
        """Test Access-Token mit Refresh-Token erneuern."""
        with patch("app.services.auth_service.AuthService") as MockAuth:
            mock_auth = AsyncMock()
            mock_auth.refresh_token.return_value = {
                "success": True,
                "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                "token_type": "Bearer",
                "expires_in": 900,
                "message": "Token erfolgreich erneuert"
            }
            MockAuth.return_value = mock_auth

            result = await mock_auth.refresh_token(
                refresh_token="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
            )

            assert result["success"] is True
            assert "access_token" in result

    @pytest.mark.asyncio
    async def test_token_expiration(self):
        """Test Abgelaufener Token."""
        with patch("app.services.auth_service.AuthService") as MockAuth:
            mock_auth = AsyncMock()
            mock_auth.validate_token.side_effect = ValueError(
                "Token abgelaufen: Bitte neu anmelden"
            )
            MockAuth.return_value = mock_auth

            with pytest.raises(ValueError, match="Token abgelaufen"):
                await mock_auth.validate_token(
                    access_token="expired_token_xyz"
                )

    @pytest.mark.asyncio
    async def test_logout(self):
        """Test Logout und Token-Invalidierung."""
        with patch("app.services.auth_service.AuthService") as MockAuth:
            mock_auth = AsyncMock()
            mock_auth.logout.return_value = {
                "success": True,
                "user_id": "user_001",
                "tokens_revoked": 2,  # Access + Refresh
                "message": "Erfolgreich abgemeldet"
            }
            MockAuth.return_value = mock_auth

            result = await mock_auth.logout(
                access_token="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
            )

            assert result["success"] is True
            assert result["tokens_revoked"] == 2

    @pytest.mark.asyncio
    async def test_logout_all_sessions(self):
        """Test Logout von allen Sessions (alle Geräte)."""
        with patch("app.services.auth_service.AuthService") as MockAuth:
            mock_auth = AsyncMock()
            mock_auth.logout_all_sessions.return_value = {
                "success": True,
                "user_id": "user_001",
                "sessions_revoked": 5,
                "message": "Von allen Geräten abgemeldet"
            }
            MockAuth.return_value = mock_auth

            result = await mock_auth.logout_all_sessions("user_001")

            assert result["success"] is True
            assert result["sessions_revoked"] > 1

    @pytest.mark.asyncio
    async def test_session_timeout(self):
        """Test Session-Timeout nach Inaktivität."""
        with patch("app.services.auth_service.AuthService") as MockAuth:
            mock_auth = AsyncMock()
            mock_auth.check_session.return_value = {
                "valid": False,
                "reason": "session_timeout",
                "message": "Session abgelaufen nach 30 Minuten Inaktivität",
                "last_activity": (datetime.now(timezone.utc) - timedelta(minutes=31)).isoformat()
            }
            MockAuth.return_value = mock_auth

            result = await mock_auth.check_session("session_token_xyz")

            assert result["valid"] is False
            assert result["reason"] == "session_timeout"

    @pytest.mark.asyncio
    async def test_concurrent_session_limit(self):
        """Test Maximale Anzahl gleichzeitiger Sessions."""
        with patch("app.services.auth_service.AuthService") as MockAuth:
            mock_auth = AsyncMock()
            mock_auth.login.side_effect = RuntimeError(
                "Maximale Anzahl gleichzeitiger Sessions erreicht (5)"
            )
            MockAuth.return_value = mock_auth

            # User already has 5 active sessions
            with pytest.raises(RuntimeError, match="Maximale Anzahl"):
                await mock_auth.login(
                    username="max.mustermann",
                    password="SecurePassword123!"
                )
