"""
Tests für das Security-Modul mit Redis-basierter Token-Blacklist.

Testet:
- Token-Blacklist (Redis + In-Memory Fallback)
- JWT Token Generierung und Validierung
- Passwort-Hashing
- Passwort-Stärke-Validierung
"""

import pytest
import pytest_asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, AsyncMock, patch
import secrets

# Import security module
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


class TestPasswordHashing:
    """Tests für Passwort-Hashing Funktionen."""

    def test_password_hash_creation(self):
        """Test: Passwort-Hash wird korrekt erstellt."""
        from app.core.security import get_password_hash

        password = "TestPasswort123!"
        hashed = get_password_hash(password)

        assert hashed is not None
        assert hashed != password
        assert hashed.startswith("$2b$")  # bcrypt prefix
        assert len(hashed) == 60  # bcrypt hash length

    def test_password_verification_correct(self):
        """Test: Korrektes Passwort wird verifiziert."""
        from app.core.security import get_password_hash, verify_password

        password = "MeinSicheresPasswort123!"
        hashed = get_password_hash(password)

        assert verify_password(password, hashed) is True

    def test_password_verification_incorrect(self):
        """Test: Falsches Passwort wird abgelehnt."""
        from app.core.security import get_password_hash, verify_password

        password = "RichtigesPasswort123!"
        wrong_password = "FalschesPasswort456!"
        hashed = get_password_hash(password)

        assert verify_password(wrong_password, hashed) is False

    def test_password_hash_unique(self):
        """Test: Gleiche Passwörter erzeugen unterschiedliche Hashes."""
        from app.core.security import get_password_hash

        password = "GleichesPasswort123!"
        hash1 = get_password_hash(password)
        hash2 = get_password_hash(password)

        assert hash1 != hash2  # Unterschiedliche Salts

    def test_unicode_password(self):
        """Test: Deutsche Umlaute in Passwörtern funktionieren."""
        from app.core.security import get_password_hash, verify_password

        password = "MüllerÜberprüfung123!"
        hashed = get_password_hash(password)

        assert verify_password(password, hashed) is True


class TestPasswordValidation:
    """Tests für Passwort-Stärke-Validierung."""

    def test_valid_password(self):
        """Test: Gültiges Passwort wird akzeptiert."""
        from app.core.security import validate_password_strength

        valid, error = validate_password_strength("SecurePass123!")

        assert valid is True
        assert error is None

    def test_password_too_short(self):
        """Test: Zu kurzes Passwort wird abgelehnt."""
        from app.core.security import validate_password_strength

        valid, error = validate_password_strength("Short1!")

        assert valid is False
        assert "8 Zeichen" in error

    def test_password_no_uppercase(self):
        """Test: Passwort ohne Großbuchstaben wird abgelehnt."""
        from app.core.security import validate_password_strength

        valid, error = validate_password_strength("lowercase123!")

        assert valid is False
        assert "Großbuchstaben" in error

    def test_password_no_lowercase(self):
        """Test: Passwort ohne Kleinbuchstaben wird abgelehnt."""
        from app.core.security import validate_password_strength

        valid, error = validate_password_strength("UPPERCASE123!")

        assert valid is False
        assert "Kleinbuchstaben" in error

    def test_password_no_digit(self):
        """Test: Passwort ohne Ziffer wird abgelehnt."""
        from app.core.security import validate_password_strength

        valid, error = validate_password_strength("NoDigitsHere!")

        assert valid is False
        assert "Ziffer" in error

    def test_password_no_special(self):
        """Test: Passwort ohne Sonderzeichen wird abgelehnt."""
        from app.core.security import validate_password_strength

        valid, error = validate_password_strength("NoSpecial123")

        assert valid is False
        assert "Sonderzeichen" in error


class TestJWTTokens:
    """Tests für JWT Token Generierung."""

    def test_access_token_creation(self):
        """Test: Access Token wird korrekt erstellt."""
        from app.core.security import create_access_token

        user_data = {"sub": "user-123", "email": "test@example.com"}
        token = create_access_token(user_data)

        assert token is not None
        assert isinstance(token, str)
        assert len(token) > 50

    def test_refresh_token_creation(self):
        """Test: Refresh Token wird korrekt erstellt."""
        from app.core.security import create_refresh_token

        user_data = {"sub": "user-123", "email": "test@example.com"}
        token = create_refresh_token(user_data)

        assert token is not None
        assert isinstance(token, str)

    def test_token_pair_creation(self):
        """Test: Token-Paar wird korrekt erstellt."""
        from app.core.security import create_token_pair

        user_data = {"sub": "user-123", "email": "test@example.com"}
        tokens = create_token_pair(user_data)

        assert "access_token" in tokens
        assert "refresh_token" in tokens
        assert "token_type" in tokens
        assert tokens["token_type"] == "bearer"

    def test_access_token_contains_jti(self):
        """Test: Access Token enthält JTI für Blacklisting."""
        from app.core.security import create_access_token, decode_token_sync

        user_data = {"sub": "user-123"}
        token = create_access_token(user_data)
        payload = decode_token_sync(token)

        assert "jti" in payload
        assert len(payload["jti"]) > 0

    def test_token_expiration(self):
        """Test: Token enthält Ablaufzeit."""
        from app.core.security import create_access_token, decode_token_sync

        user_data = {"sub": "user-123"}
        token = create_access_token(user_data)
        payload = decode_token_sync(token)

        assert "exp" in payload
        assert "iat" in payload


class TestTokenBlacklistFallback:
    """Tests für In-Memory Token-Blacklist (Fallback)."""

    def test_blacklist_token_sync(self):
        """Test: Token kann synchron zur Blacklist hinzugefügt werden."""
        from app.core.security import blacklist_token_sync, is_token_blacklisted_sync

        jti = secrets.token_urlsafe(32)
        expires = datetime.now(timezone.utc) + timedelta(hours=1)

        blacklist_token_sync(jti, expires)

        assert is_token_blacklisted_sync(jti) is True

    def test_expired_token_removed_from_blacklist(self):
        """Test: Abgelaufene Tokens werden aus Blacklist entfernt."""
        from app.core.security import blacklist_token_sync, is_token_blacklisted_sync

        jti = secrets.token_urlsafe(32)
        # Token bereits abgelaufen
        expires = datetime.now(timezone.utc) - timedelta(seconds=1)

        blacklist_token_sync(jti, expires)

        # Beim Prüfen sollte es als nicht-blacklisted gelten (und entfernt werden)
        assert is_token_blacklisted_sync(jti) is False

    def test_non_blacklisted_token(self):
        """Test: Nicht-blacklistete Tokens werden als gültig erkannt."""
        from app.core.security import is_token_blacklisted_sync

        jti = secrets.token_urlsafe(32)

        assert is_token_blacklisted_sync(jti) is False


@pytest.mark.asyncio
class TestTokenBlacklistRedis:
    """Tests für Redis-basierte Token-Blacklist."""

    async def test_blacklist_token_redis_fallback(self):
        """Test: Fallback auf In-Memory wenn Redis nicht verfügbar."""
        from app.core.security import (
            blacklist_token_redis,
            is_token_blacklisted_redis,
            _token_blacklist_fallback
        )

        # Simuliere Redis nicht verfügbar und fail-closed deaktiviert
        with patch('app.core.security._redis_available', False):
            with patch('app.core.security.TOKEN_BLACKLIST_FAIL_CLOSED', False):
                jti = secrets.token_urlsafe(32)
                expires = datetime.now(timezone.utc) + timedelta(hours=1)

                result = await blacklist_token_redis(jti, expires)

                # Sollte False zurückgeben (Fallback verwendet)
                assert result is False
                # Token sollte im Fallback sein
                assert jti in _token_blacklist_fallback

    async def test_blacklist_check_fallback(self):
        """Test: Blacklist-Check funktioniert mit Fallback."""
        from app.core.security import (
            is_token_blacklisted_redis,
            _token_blacklist_fallback
        )

        jti = secrets.token_urlsafe(32)
        expires = datetime.now(timezone.utc) + timedelta(hours=1)

        # Manuell zum Fallback hinzufügen
        _token_blacklist_fallback[jti] = expires

        # Simuliere Redis nicht verfügbar und fail-closed deaktiviert
        with patch('app.core.security._redis_available', False):
            with patch('app.core.security.TOKEN_BLACKLIST_FAIL_CLOSED', False):
                result = await is_token_blacklisted_redis(jti)
                assert result is True

    async def test_get_blacklist_stats(self):
        """Test: Blacklist-Statistiken werden korrekt zurückgegeben."""
        from app.core.security import get_blacklist_stats

        with patch('app.core.security._redis_available', False):
            stats = await get_blacklist_stats()

            assert "redis_available" in stats
            assert "fallback_count" in stats
            assert "storage_type" in stats
            assert stats["storage_type"] == "in-memory"


@pytest.mark.asyncio
class TestAsyncTokenOperations:
    """Tests für async Token-Operationen."""

    async def test_blacklist_token_async(self):
        """Test: Async blacklist_token funktioniert."""
        from app.core.security import blacklist_token, is_token_blacklisted

        jti = secrets.token_urlsafe(32)
        expires = datetime.now(timezone.utc) + timedelta(hours=1)

        with patch('app.core.security._redis_available', False):
            with patch('app.core.security.TOKEN_BLACKLIST_FAIL_CLOSED', False):
                await blacklist_token(jti, expires)
                result = await is_token_blacklisted(jti)

                assert result is True

    async def test_decode_token_async(self):
        """Test: Async decode_token funktioniert."""
        from app.core.security import create_access_token, decode_token

        user_data = {"sub": "user-123", "email": "test@example.com"}
        token = create_access_token(user_data)

        with patch('app.core.security._redis_available', False):
            with patch('app.core.security.TOKEN_BLACKLIST_FAIL_CLOSED', False):
                payload = await decode_token(token)

                assert payload["sub"] == "user-123"
                assert payload["email"] == "test@example.com"

    async def test_decode_blacklisted_token_raises(self):
        """Test: Blacklisteter Token wird abgelehnt."""
        from app.core.security import (
            create_access_token,
            decode_token,
            blacklist_token,
            decode_token_sync
        )
        from fastapi import HTTPException

        user_data = {"sub": "user-123"}
        token = create_access_token(user_data)

        # Token blacklisten
        payload = decode_token_sync(token)
        jti = payload["jti"]
        exp = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)

        with patch('app.core.security._redis_available', False):
            with patch('app.core.security.TOKEN_BLACKLIST_FAIL_CLOSED', False):
                await blacklist_token(jti, exp)

                with pytest.raises(HTTPException) as exc_info:
                    await decode_token(token)

                assert exc_info.value.status_code == 401
                assert "widerrufen" in exc_info.value.detail

    async def test_extract_user_id_async(self):
        """Test: Async User-ID Extraktion funktioniert."""
        from app.core.security import create_access_token, extract_user_id_from_token

        user_id = "user-abc-123"
        token = create_access_token({"sub": user_id})

        with patch('app.core.security._redis_available', False):
            with patch('app.core.security.TOKEN_BLACKLIST_FAIL_CLOSED', False):
                extracted_id = await extract_user_id_from_token(token)

                assert extracted_id == user_id


class TestTokenTypeVerification:
    """Tests für Token-Typ-Verifizierung."""

    def test_verify_access_token_type(self):
        """Test: Access Token Typ wird korrekt verifiziert."""
        from app.core.security import create_access_token, verify_token_type, decode_token_sync

        token = create_access_token({"sub": "user-123"})
        payload = decode_token_sync(token)

        # Sollte keine Exception werfen
        verify_token_type(payload, "access")

    def test_verify_refresh_token_type(self):
        """Test: Refresh Token Typ wird korrekt verifiziert."""
        from app.core.security import create_refresh_token, verify_token_type, decode_token_sync

        token = create_refresh_token({"sub": "user-123"})
        payload = decode_token_sync(token)

        # Sollte keine Exception werfen
        verify_token_type(payload, "refresh")

    def test_wrong_token_type_raises(self):
        """Test: Falscher Token-Typ wirft Exception."""
        from app.core.security import create_access_token, verify_token_type, decode_token_sync
        from fastapi import HTTPException

        # Access Token erstellen
        token = create_access_token({"sub": "user-123"})
        payload = decode_token_sync(token)

        # Als Refresh Token verifizieren sollte fehlschlagen
        with pytest.raises(HTTPException) as exc_info:
            verify_token_type(payload, "refresh")

        assert exc_info.value.status_code == 401
        assert "Token-Typ" in exc_info.value.detail


class TestCleanupFallbackBlacklist:
    """Tests für Fallback-Blacklist Cleanup."""

    def test_cleanup_removes_expired(self):
        """Test: Cleanup entfernt abgelaufene Tokens."""
        from app.core.security import _cleanup_fallback_blacklist, _token_blacklist_fallback

        # Abgelaufenes Token hinzufügen
        expired_jti = secrets.token_urlsafe(32)
        _token_blacklist_fallback[expired_jti] = datetime.now(timezone.utc) - timedelta(hours=1)

        # Gültiges Token hinzufügen
        valid_jti = secrets.token_urlsafe(32)
        _token_blacklist_fallback[valid_jti] = datetime.now(timezone.utc) + timedelta(hours=1)

        removed = _cleanup_fallback_blacklist()

        assert removed >= 1
        assert expired_jti not in _token_blacklist_fallback
        assert valid_jti in _token_blacklist_fallback

        # Cleanup
        del _token_blacklist_fallback[valid_jti]
