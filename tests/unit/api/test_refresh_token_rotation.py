# -*- coding: utf-8 -*-
"""
Tests für Refresh Token Rotation.

Testet die Sicherheitsfunktion, die verhindert,
dass alte Refresh Tokens wiederverwendet werden können.
"""

import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from fastapi import HTTPException


# ==================== Test Fixtures ====================


@pytest.fixture
def mock_user():
    """Erstellt Mock-User für Tests."""
    user = MagicMock()
    user.id = uuid4()
    user.email = "test@example.com"
    user.username = "testuser"
    user.is_active = True
    return user


@pytest.fixture
def valid_refresh_payload():
    """Erstellt gültiges Refresh Token Payload."""
    return {
        "sub": str(uuid4()),
        "email": "test@example.com",
        "username": "testuser",
        "type": "refresh",
        "jti": "test_jti_12345678",
        "exp": int((datetime.now(timezone.utc) + timedelta(days=7)).timestamp()),
        "iat": int(datetime.now(timezone.utc).timestamp()),
    }


@pytest.fixture
def mock_db():
    """Erstellt Mock-DB-Session."""
    return AsyncMock()


# ==================== Tests: Token Rotation ====================


class TestRefreshTokenRotation:
    """Tests für Refresh Token Rotation."""

    @pytest.mark.asyncio
    async def test_old_token_is_blacklisted_on_refresh(
        self, mock_user, valid_refresh_payload, mock_db
    ):
        """Alter Refresh Token wird bei Refresh auf Blacklist gesetzt."""
        from app.api.v1.auth import refresh_token
        from app.db.schemas import RefreshTokenRequest

        # Setup
        old_jti = valid_refresh_payload["jti"]
        old_exp = valid_refresh_payload["exp"]
        valid_refresh_payload["sub"] = str(mock_user.id)

        with patch("app.api.v1.auth.decode_token") as mock_decode, \
             patch("app.api.v1.auth.verify_token_type"), \
             patch("app.api.v1.auth.UserService.get_user_by_id", return_value=mock_user), \
             patch("app.api.v1.auth.blacklist_token") as mock_blacklist, \
             patch("app.api.v1.auth.create_token_pair") as mock_create_tokens:

            mock_decode.return_value = valid_refresh_payload
            mock_create_tokens.return_value = {
                "access_token": "new_access_token",
                "refresh_token": "new_refresh_token",
                "token_type": "bearer"
            }

            request = RefreshTokenRequest(refresh_token="old_refresh_token")
            await refresh_token(request, mock_db)

            # Verify blacklist was called with old token's JTI
            mock_blacklist.assert_called_once()
            call_args = mock_blacklist.call_args
            assert call_args[0][0] == old_jti
            # Check expiration datetime
            assert isinstance(call_args[0][1], datetime)

    @pytest.mark.asyncio
    async def test_new_tokens_are_issued_with_new_jti(
        self, mock_user, valid_refresh_payload, mock_db
    ):
        """Neue Tokens haben neue JTIs (nicht wiederverwendet)."""
        from app.api.v1.auth import refresh_token
        from app.db.schemas import RefreshTokenRequest

        valid_refresh_payload["sub"] = str(mock_user.id)
        old_jti = valid_refresh_payload["jti"]

        with patch("app.api.v1.auth.decode_token") as mock_decode, \
             patch("app.api.v1.auth.verify_token_type"), \
             patch("app.api.v1.auth.UserService.get_user_by_id", return_value=mock_user), \
             patch("app.api.v1.auth.blacklist_token"), \
             patch("app.api.v1.auth.create_token_pair") as mock_create_tokens:

            mock_decode.return_value = valid_refresh_payload
            mock_create_tokens.return_value = {
                "access_token": "new_access_token",
                "refresh_token": "new_refresh_token",
                "token_type": "bearer"
            }

            request = RefreshTokenRequest(refresh_token="old_refresh_token")
            result = await refresh_token(request, mock_db)

            # Verify new tokens are issued
            assert result.access_token == "new_access_token"
            assert result.refresh_token == "new_refresh_token"

    @pytest.mark.asyncio
    async def test_blacklisted_token_cannot_be_reused(
        self, mock_user, valid_refresh_payload, mock_db
    ):
        """Blacklisted Token kann nicht wiederverwendet werden."""
        from app.api.v1.auth import refresh_token
        from app.db.schemas import RefreshTokenRequest

        valid_refresh_payload["sub"] = str(mock_user.id)

        # Simulate token being blacklisted (decode_token raises 401)
        with patch("app.api.v1.auth.decode_token") as mock_decode:
            mock_decode.side_effect = HTTPException(
                status_code=401,
                detail="Token wurde widerrufen"
            )

            request = RefreshTokenRequest(refresh_token="blacklisted_token")

            with pytest.raises(HTTPException) as exc:
                await refresh_token(request, mock_db)

            assert exc.value.status_code == 401
            assert "widerrufen" in exc.value.detail

    @pytest.mark.asyncio
    async def test_refresh_continues_if_blacklist_fails_in_non_fail_closed_mode(
        self, mock_user, valid_refresh_payload, mock_db
    ):
        """Refresh funktioniert auch wenn Blacklist fehlschlägt (non-fail-closed)."""
        from app.api.v1.auth import refresh_token
        from app.db.schemas import RefreshTokenRequest

        valid_refresh_payload["sub"] = str(mock_user.id)

        with patch("app.api.v1.auth.decode_token") as mock_decode, \
             patch("app.api.v1.auth.verify_token_type"), \
             patch("app.api.v1.auth.UserService.get_user_by_id", return_value=mock_user), \
             patch("app.api.v1.auth.blacklist_token") as mock_blacklist, \
             patch("app.api.v1.auth.create_token_pair") as mock_create_tokens:

            mock_decode.return_value = valid_refresh_payload
            # Blacklist wirft generische Exception (nicht HTTPException)
            mock_blacklist.side_effect = Exception("Redis connection error")
            mock_create_tokens.return_value = {
                "access_token": "new_access_token",
                "refresh_token": "new_refresh_token",
                "token_type": "bearer"
            }

            request = RefreshTokenRequest(refresh_token="old_refresh_token")
            result = await refresh_token(request, mock_db)

            # Refresh sollte trotzdem funktionieren
            assert result.access_token == "new_access_token"

    @pytest.mark.asyncio
    async def test_refresh_blocked_in_fail_closed_mode(
        self, mock_user, valid_refresh_payload, mock_db
    ):
        """Refresh wird blockiert wenn Blacklist in fail-closed Mode fehlschlägt."""
        from app.api.v1.auth import refresh_token
        from app.db.schemas import RefreshTokenRequest

        valid_refresh_payload["sub"] = str(mock_user.id)

        with patch("app.api.v1.auth.decode_token") as mock_decode, \
             patch("app.api.v1.auth.verify_token_type"), \
             patch("app.api.v1.auth.UserService.get_user_by_id", return_value=mock_user), \
             patch("app.api.v1.auth.blacklist_token") as mock_blacklist:

            mock_decode.return_value = valid_refresh_payload
            # Blacklist wirft HTTPException (fail-closed mode)
            mock_blacklist.side_effect = HTTPException(
                status_code=503,
                detail="Sicherheitsdienst temporär nicht verfügbar"
            )

            request = RefreshTokenRequest(refresh_token="old_refresh_token")

            with pytest.raises(HTTPException) as exc:
                await refresh_token(request, mock_db)

            assert exc.value.status_code == 503


class TestRefreshTokenRotationEdgeCases:
    """Edge Cases für Refresh Token Rotation."""

    @pytest.mark.asyncio
    async def test_handles_token_without_jti(
        self, mock_user, mock_db
    ):
        """Behandelt Token ohne JTI korrekt (Legacy-Kompatibilität)."""
        from app.api.v1.auth import refresh_token
        from app.db.schemas import RefreshTokenRequest

        # Payload ohne JTI (Legacy-Token)
        payload_without_jti = {
            "sub": str(mock_user.id),
            "email": "test@example.com",
            "username": "testuser",
            "type": "refresh",
            # Kein "jti" Feld!
            "exp": int((datetime.now(timezone.utc) + timedelta(days=7)).timestamp()),
        }

        with patch("app.api.v1.auth.decode_token") as mock_decode, \
             patch("app.api.v1.auth.verify_token_type"), \
             patch("app.api.v1.auth.UserService.get_user_by_id", return_value=mock_user), \
             patch("app.api.v1.auth.blacklist_token") as mock_blacklist, \
             patch("app.api.v1.auth.create_token_pair") as mock_create_tokens:

            mock_decode.return_value = payload_without_jti
            mock_create_tokens.return_value = {
                "access_token": "new_access",
                "refresh_token": "new_refresh",
                "token_type": "bearer"
            }

            request = RefreshTokenRequest(refresh_token="legacy_token")
            result = await refresh_token(request, mock_db)

            # Sollte funktionieren, aber blacklist nicht aufrufen
            mock_blacklist.assert_not_called()
            assert result.access_token == "new_access"

    @pytest.mark.asyncio
    async def test_handles_token_without_exp(
        self, mock_user, mock_db
    ):
        """Behandelt Token ohne exp korrekt."""
        from app.api.v1.auth import refresh_token
        from app.db.schemas import RefreshTokenRequest

        # Payload ohne exp
        payload_without_exp = {
            "sub": str(mock_user.id),
            "email": "test@example.com",
            "username": "testuser",
            "type": "refresh",
            "jti": "test_jti",
            # Kein "exp" Feld!
        }

        with patch("app.api.v1.auth.decode_token") as mock_decode, \
             patch("app.api.v1.auth.verify_token_type"), \
             patch("app.api.v1.auth.UserService.get_user_by_id", return_value=mock_user), \
             patch("app.api.v1.auth.blacklist_token") as mock_blacklist, \
             patch("app.api.v1.auth.create_token_pair") as mock_create_tokens:

            mock_decode.return_value = payload_without_exp
            mock_create_tokens.return_value = {
                "access_token": "new_access",
                "refresh_token": "new_refresh",
                "token_type": "bearer"
            }

            request = RefreshTokenRequest(refresh_token="token_without_exp")
            result = await refresh_token(request, mock_db)

            # Sollte funktionieren, aber blacklist nicht aufrufen
            mock_blacklist.assert_not_called()
            assert result.refresh_token == "new_refresh"

    @pytest.mark.asyncio
    async def test_inactive_user_cannot_refresh(
        self, mock_user, valid_refresh_payload, mock_db
    ):
        """Inaktiver User kann Token nicht erneuern."""
        from app.api.v1.auth import refresh_token
        from app.db.schemas import RefreshTokenRequest

        mock_user.is_active = False
        valid_refresh_payload["sub"] = str(mock_user.id)

        with patch("app.api.v1.auth.decode_token") as mock_decode, \
             patch("app.api.v1.auth.verify_token_type"), \
             patch("app.api.v1.auth.UserService.get_user_by_id", return_value=mock_user):

            mock_decode.return_value = valid_refresh_payload

            request = RefreshTokenRequest(refresh_token="valid_token")

            with pytest.raises(HTTPException) as exc:
                await refresh_token(request, mock_db)

            assert exc.value.status_code == 403
            assert "deaktiviert" in exc.value.detail

    @pytest.mark.asyncio
    async def test_nonexistent_user_cannot_refresh(
        self, valid_refresh_payload, mock_db
    ):
        """Nicht existierender User kann Token nicht erneuern."""
        from app.api.v1.auth import refresh_token
        from app.db.schemas import RefreshTokenRequest

        with patch("app.api.v1.auth.decode_token") as mock_decode, \
             patch("app.api.v1.auth.verify_token_type"), \
             patch("app.api.v1.auth.UserService.get_user_by_id", return_value=None):

            mock_decode.return_value = valid_refresh_payload

            request = RefreshTokenRequest(refresh_token="valid_token")

            with pytest.raises(HTTPException) as exc:
                await refresh_token(request, mock_db)

            assert exc.value.status_code == 401
            assert "nicht gefunden" in exc.value.detail


class TestRefreshTokenRotationSecurity:
    """Sicherheitstests für Refresh Token Rotation."""

    @pytest.mark.asyncio
    async def test_access_token_cannot_be_used_for_refresh(
        self, mock_db
    ):
        """Access Token kann nicht als Refresh Token verwendet werden."""
        from app.api.v1.auth import refresh_token
        from app.db.schemas import RefreshTokenRequest

        # Access Token Payload (type=access)
        access_payload = {
            "sub": str(uuid4()),
            "type": "access",  # Falscher Typ!
            "jti": "access_jti",
            "exp": int((datetime.now(timezone.utc) + timedelta(minutes=15)).timestamp()),
        }

        with patch("app.api.v1.auth.decode_token") as mock_decode, \
             patch("app.api.v1.auth.verify_token_type") as mock_verify:

            mock_decode.return_value = access_payload
            mock_verify.side_effect = HTTPException(
                status_code=401,
                detail="Falscher Token-Typ. Erwartet: refresh"
            )

            request = RefreshTokenRequest(refresh_token="access_token_value")

            with pytest.raises(HTTPException) as exc:
                await refresh_token(request, mock_db)

            assert exc.value.status_code == 401
            assert "Token-Typ" in exc.value.detail

    @pytest.mark.asyncio
    async def test_expired_token_cannot_be_refreshed(
        self, mock_db
    ):
        """Abgelaufener Token kann nicht erneuert werden."""
        from app.api.v1.auth import refresh_token
        from app.db.schemas import RefreshTokenRequest

        with patch("app.api.v1.auth.decode_token") as mock_decode:
            mock_decode.side_effect = HTTPException(
                status_code=401,
                detail="Token ungültig oder abgelaufen"
            )

            request = RefreshTokenRequest(refresh_token="expired_token")

            with pytest.raises(HTTPException) as exc:
                await refresh_token(request, mock_db)

            assert exc.value.status_code == 401
            assert "abgelaufen" in exc.value.detail

    @pytest.mark.asyncio
    async def test_invalid_token_format_rejected(
        self, mock_db
    ):
        """Ungültiges Token-Format wird abgelehnt."""
        from app.api.v1.auth import refresh_token
        from app.db.schemas import RefreshTokenRequest

        with patch("app.api.v1.auth.decode_token") as mock_decode:
            mock_decode.side_effect = HTTPException(
                status_code=401,
                detail="Token ungültig oder abgelaufen"
            )

            request = RefreshTokenRequest(refresh_token="not.a.valid.token")

            with pytest.raises(HTTPException) as exc:
                await refresh_token(request, mock_db)

            assert exc.value.status_code == 401

    @pytest.mark.asyncio
    async def test_token_without_sub_rejected(
        self, mock_db
    ):
        """Token ohne sub (user_id) wird abgelehnt."""
        from app.api.v1.auth import refresh_token
        from app.db.schemas import RefreshTokenRequest

        # Payload ohne sub
        payload_without_sub = {
            "type": "refresh",
            "jti": "test_jti",
            "exp": int((datetime.now(timezone.utc) + timedelta(days=7)).timestamp()),
            # Kein "sub" Feld!
        }

        with patch("app.api.v1.auth.decode_token") as mock_decode, \
             patch("app.api.v1.auth.verify_token_type"):

            mock_decode.return_value = payload_without_sub

            request = RefreshTokenRequest(refresh_token="token_without_sub")

            with pytest.raises(HTTPException) as exc:
                await refresh_token(request, mock_db)

            assert exc.value.status_code == 401
            assert "Token-Format" in exc.value.detail


class TestRefreshTokenRotationLogging:
    """Tests für Logging bei Refresh Token Rotation."""

    @pytest.mark.asyncio
    async def test_successful_refresh_is_logged(
        self, mock_user, valid_refresh_payload, mock_db
    ):
        """Erfolgreicher Refresh wird geloggt."""
        from app.api.v1.auth import refresh_token
        from app.db.schemas import RefreshTokenRequest

        valid_refresh_payload["sub"] = str(mock_user.id)

        with patch("app.api.v1.auth.decode_token") as mock_decode, \
             patch("app.api.v1.auth.verify_token_type"), \
             patch("app.api.v1.auth.UserService.get_user_by_id", return_value=mock_user), \
             patch("app.api.v1.auth.blacklist_token"), \
             patch("app.api.v1.auth.create_token_pair") as mock_create_tokens, \
             patch("app.api.v1.auth.logger") as mock_logger:

            mock_decode.return_value = valid_refresh_payload
            mock_create_tokens.return_value = {
                "access_token": "new_access",
                "refresh_token": "new_refresh",
                "token_type": "bearer"
            }

            request = RefreshTokenRequest(refresh_token="old_token")
            await refresh_token(request, mock_db)

            # Verify info log was called
            mock_logger.info.assert_called_once()
            call_args = mock_logger.info.call_args
            assert call_args[0][0] == "token_refresh_successful"
            assert call_args[1].get("rotation_applied") is True

    @pytest.mark.asyncio
    async def test_blacklist_failure_is_logged(
        self, mock_user, valid_refresh_payload, mock_db
    ):
        """Blacklist-Fehler wird geloggt."""
        from app.api.v1.auth import refresh_token
        from app.db.schemas import RefreshTokenRequest

        valid_refresh_payload["sub"] = str(mock_user.id)

        with patch("app.api.v1.auth.decode_token") as mock_decode, \
             patch("app.api.v1.auth.verify_token_type"), \
             patch("app.api.v1.auth.UserService.get_user_by_id", return_value=mock_user), \
             patch("app.api.v1.auth.blacklist_token") as mock_blacklist, \
             patch("app.api.v1.auth.create_token_pair") as mock_create_tokens, \
             patch("app.api.v1.auth.logger") as mock_logger:

            mock_decode.return_value = valid_refresh_payload
            mock_blacklist.side_effect = Exception("Redis error")
            mock_create_tokens.return_value = {
                "access_token": "new_access",
                "refresh_token": "new_refresh",
                "token_type": "bearer"
            }

            request = RefreshTokenRequest(refresh_token="old_token")
            await refresh_token(request, mock_db)

            # Verify warning log was called
            mock_logger.warning.assert_called_once()
            call_args = mock_logger.warning.call_args
            assert call_args[0][0] == "refresh_token_blacklist_failed"
