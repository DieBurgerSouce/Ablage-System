"""
Security Configuration Tests.

Tests für:
- SECRET_KEY Validierung (Pflicht in Production, min. 32 Zeichen)
- CORS Validierung (keine localhost/wildcard in Production)
- Sichere Fehler-Protokollierung (keine Secrets in Logs)

Diese Tests stellen sicher, dass Sicherheitskonfigurationen korrekt validiert werden.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone

import structlog


# ==================== SECRET_KEY Validation Tests ====================


class TestSecretKeyValidation:
    """Tests für SECRET_KEY Validierung in Settings."""

    def test_empty_secret_key_in_production_raises_error(self, monkeypatch):
        """Leerer SECRET_KEY in Production muss ValueError auslösen."""
        # Clear environment and set production mode
        monkeypatch.delenv("SECRET_KEY", raising=False)
        monkeypatch.setenv("DEBUG", "false")

        # Import fresh Settings class
        from pydantic import ValidationError
        import importlib
        import app.core.config as config_module

        # Create Settings with empty SECRET_KEY and DEBUG=False
        with pytest.raises((ValueError, ValidationError)) as exc_info:
            from pydantic_settings import BaseSettings

            # Temporarily modify environment
            with patch.dict("os.environ", {"SECRET_KEY": "", "DEBUG": "false"}, clear=False):
                # Force fresh instance creation
                class TestSettings(config_module.Settings):
                    DEBUG: bool = False
                    SECRET_KEY: str = ""

                TestSettings()

        # Check error message contains relevant info
        error_str = str(exc_info.value)
        assert "SECRET_KEY" in error_str or "secret" in error_str.lower()

    def test_short_secret_key_raises_error(self, monkeypatch):
        """SECRET_KEY unter 32 Zeichen muss ValueError auslösen."""
        short_key = "tooshort123"  # Only 11 characters

        from pydantic import ValidationError

        with pytest.raises((ValueError, ValidationError)) as exc_info:
            from app.core.config import Settings

            class TestSettings(Settings):
                SECRET_KEY: str = short_key
                DEBUG: bool = True  # Even in debug mode, short key should fail

            TestSettings()

        error_str = str(exc_info.value)
        assert "32" in error_str or "kurz" in error_str.lower() or "short" in error_str.lower()

    def test_valid_secret_key_in_production_succeeds(self, monkeypatch):
        """Gültiger SECRET_KEY (32+ Zeichen) in Production muss funktionieren."""
        import secrets
        valid_key = secrets.token_urlsafe(64)  # 86 characters

        from app.core.config import Settings

        class TestSettings(Settings):
            SECRET_KEY: str = valid_key
            DEBUG: bool = False
            # Override CORS to avoid validation errors
            CORS_ORIGINS: list = ["https://app.example.com"]

        settings = TestSettings()
        assert settings.SECRET_KEY == valid_key
        assert len(settings.SECRET_KEY) >= 32

    def test_empty_secret_key_in_development_auto_generates(self, monkeypatch):
        """Leerer SECRET_KEY in Development generiert automatisch einen Key."""
        from app.core.config import Settings

        class TestSettings(Settings):
            SECRET_KEY: str = ""
            DEBUG: bool = True

        settings = TestSettings()

        # Should have auto-generated a key
        assert settings.SECRET_KEY != ""
        assert len(settings.SECRET_KEY) >= 32


# ==================== CORS Validation Tests ====================


class TestCorsValidation:
    """Tests für CORS Origins Validierung."""

    def test_wildcard_with_credentials_raises_error(self):
        """CORS_ORIGINS='*' mit CORS_ALLOW_CREDENTIALS=True muss fehlschlagen."""
        from pydantic import ValidationError
        from app.core.config import Settings
        import secrets

        with pytest.raises((ValueError, ValidationError)) as exc_info:
            class TestSettings(Settings):
                SECRET_KEY: str = secrets.token_urlsafe(64)
                DEBUG: bool = True
                CORS_ORIGINS: list = ["*"]
                CORS_ALLOW_CREDENTIALS: bool = True

            TestSettings()

        error_str = str(exc_info.value)
        assert "*" in error_str or "wildcard" in error_str.lower() or "credentials" in error_str.lower()

    def test_wildcard_in_production_raises_error(self):
        """CORS_ORIGINS='*' in Production muss fehlschlagen."""
        from pydantic import ValidationError
        from app.core.config import Settings
        import secrets

        with pytest.raises((ValueError, ValidationError)) as exc_info:
            class TestSettings(Settings):
                SECRET_KEY: str = secrets.token_urlsafe(64)
                DEBUG: bool = False
                CORS_ORIGINS: list = ["*"]
                CORS_ALLOW_CREDENTIALS: bool = False  # Even without credentials

            TestSettings()

        error_str = str(exc_info.value)
        assert "*" in error_str or "production" in error_str.lower()

    def test_localhost_in_production_raises_error(self):
        """localhost in CORS_ORIGINS in Production muss fehlschlagen."""
        from pydantic import ValidationError
        from app.core.config import Settings
        import secrets

        localhost_origins = [
            ["http://localhost:3000"],
            ["http://127.0.0.1:8080"],
            ["http://localhost"],
            ["https://app.example.com", "http://localhost:3000"],  # Mixed
        ]

        for origins in localhost_origins:
            with pytest.raises((ValueError, ValidationError)) as exc_info:
                class TestSettings(Settings):
                    SECRET_KEY: str = secrets.token_urlsafe(64)
                    DEBUG: bool = False
                    CORS_ORIGINS: list = origins

                TestSettings()

            error_str = str(exc_info.value)
            assert (
                "localhost" in error_str.lower()
                or "127.0.0.1" in error_str
                or "production" in error_str.lower()
            ), f"Expected localhost/production error for origins {origins}, got: {error_str}"

    def test_localhost_in_development_allowed_with_warning(self, caplog):
        """localhost in Development ist erlaubt, aber mit Warnung."""
        from app.core.config import Settings
        import secrets

        class TestSettings(Settings):
            SECRET_KEY: str = secrets.token_urlsafe(64)
            DEBUG: bool = True
            CORS_ORIGINS: list = ["http://localhost:3000"]

        # Should not raise
        settings = TestSettings()
        assert "http://localhost:3000" in settings.CORS_ORIGINS

    def test_valid_production_cors_origins_succeeds(self):
        """Gültige Production CORS Origins funktionieren."""
        from app.core.config import Settings
        import secrets

        valid_origins = [
            "https://app.example.com",
            "https://admin.example.com",
        ]

        class TestSettings(Settings):
            SECRET_KEY: str = secrets.token_urlsafe(64)
            DEBUG: bool = False
            CORS_ORIGINS: list = valid_origins

        settings = TestSettings()
        assert settings.CORS_ORIGINS == valid_origins


# ==================== Secure Error Logging Tests ====================


class TestSecureErrorLogging:
    """Tests für sichere Fehler-Protokollierung ohne Credentials."""

    @pytest.mark.asyncio
    async def test_redis_error_logs_only_error_type(self):
        """Redis-Fehler sollten nur Fehlertyp loggen, nicht Details."""
        from app.core import security as security_module

        # Reset Redis state for testing
        security_module._redis_client = None
        security_module._redis_available = None

        # Mock the import and connection to fail with specific error
        class MockConnectionError(Exception):
            """Mock error containing sensitive info."""
            pass

        captured_logs = []

        def capture_log(_, method_name, **kwargs):
            captured_logs.append({"method": method_name, **kwargs})

        with patch.object(security_module, "_redis_client", None):
            with patch.object(security_module, "_redis_available", None):
                with patch("app.core.security.RedisStateManager") as mock_manager_class:
                    # Setup mock to raise error
                    mock_instance = MagicMock()
                    mock_manager_class.get_instance.return_value = mock_instance
                    mock_instance.connect = AsyncMock(
                        side_effect=MockConnectionError("redis://:password@host:6379")
                    )

                    with patch.object(security_module.logger, "warning") as mock_warning:
                        # Call the function that should log securely
                        result = await security_module._get_redis_client()

                        # Should return None on error
                        assert result is None

                        # Check that warning was called
                        mock_warning.assert_called()

                        # Check log call arguments
                        call_args = mock_warning.call_args
                        logged_kwargs = call_args[1] if call_args[1] else {}

                        # Should log error_type, not full error message
                        if "error_type" in logged_kwargs:
                            assert logged_kwargs["error_type"] == "MockConnectionError"

                        # Should NOT contain password or sensitive data
                        all_values = str(call_args)
                        assert "password" not in all_values.lower()
                        assert "redis://" not in all_values

    @pytest.mark.asyncio
    async def test_blacklist_token_redis_error_logs_securely(self):
        """blacklist_token_redis loggt Redis-Fehler sicher."""
        from app.core import security as security_module
        from datetime import datetime, timezone, timedelta

        # Create mock Redis client that raises error
        mock_redis = AsyncMock()
        mock_redis.setex = AsyncMock(side_effect=Exception("Connection to redis://:secret@host failed"))

        with patch.object(security_module, "_get_redis_client", return_value=mock_redis):
            with patch.object(security_module.logger, "warning") as mock_warning:
                expires = datetime.now(timezone.utc) + timedelta(hours=1)

                result = await security_module.blacklist_token_redis("test-jti", expires)

                # Should fall back to in-memory
                assert result is False

                # Check warning was called with error_type
                mock_warning.assert_called()
                call_args = mock_warning.call_args
                call_kwargs = call_args[1] if call_args[1] else {}

                # Should use error_type, not full error
                if "error_type" in call_kwargs:
                    assert call_kwargs["error_type"] == "Exception"

                # Should NOT contain sensitive data
                all_values = str(call_args)
                assert "secret" not in all_values.lower()
                assert "redis://" not in all_values

    @pytest.mark.asyncio
    async def test_is_token_blacklisted_redis_error_logs_securely(self):
        """is_token_blacklisted_redis loggt Redis-Fehler sicher."""
        from app.core import security as security_module

        # Create mock Redis client that raises error
        mock_redis = AsyncMock()
        mock_redis.exists = AsyncMock(side_effect=Exception("Auth failed: password=secret123"))

        with patch.object(security_module, "_get_redis_client", return_value=mock_redis):
            with patch.object(security_module.logger, "warning") as mock_warning:
                result = await security_module.is_token_blacklisted_redis("test-jti")

                # Should return False on error (token not confirmed blacklisted)
                assert result is False

                # Check warning was called
                mock_warning.assert_called()
                call_args = mock_warning.call_args

                # Should NOT contain sensitive data
                all_values = str(call_args)
                assert "secret" not in all_values.lower()
                assert "password" not in all_values.lower()


# ==================== Password Validation Tests ====================


class TestPasswordValidation:
    """Tests für Passwort-Validierung."""

    def test_password_too_short(self):
        """Passwort unter 8 Zeichen muss fehlschlagen."""
        from app.core.security import validate_password_strength

        is_valid, error = validate_password_strength("Short1!")
        assert is_valid is False
        assert "8" in error or "Zeichen" in error

    def test_password_missing_uppercase(self):
        """Passwort ohne Großbuchstaben muss fehlschlagen."""
        from app.core.security import validate_password_strength

        is_valid, error = validate_password_strength("lowercase1!")
        assert is_valid is False
        assert "Großbuchstaben" in error or "uppercase" in error.lower()

    def test_password_missing_lowercase(self):
        """Passwort ohne Kleinbuchstaben muss fehlschlagen."""
        from app.core.security import validate_password_strength

        is_valid, error = validate_password_strength("UPPERCASE1!")
        assert is_valid is False
        assert "Kleinbuchstaben" in error or "lowercase" in error.lower()

    def test_password_missing_digit(self):
        """Passwort ohne Ziffer muss fehlschlagen."""
        from app.core.security import validate_password_strength

        is_valid, error = validate_password_strength("NoDigits!")
        assert is_valid is False
        assert "Ziffer" in error or "digit" in error.lower()

    def test_password_missing_special_char(self):
        """Passwort ohne Sonderzeichen muss fehlschlagen."""
        from app.core.security import validate_password_strength

        is_valid, error = validate_password_strength("NoSpecial1")
        assert is_valid is False
        assert "Sonderzeichen" in error or "special" in error.lower()

    def test_valid_password_succeeds(self):
        """Gültiges Passwort muss erfolgreich sein."""
        from app.core.security import validate_password_strength

        is_valid, error = validate_password_strength("ValidPass1!")
        assert is_valid is True
        assert error is None


# ==================== Token Creation Tests ====================


class TestTokenCreation:
    """Tests für Token-Erstellung."""

    def test_access_token_contains_jti(self):
        """Access Token muss JTI (unique ID) enthalten."""
        from app.core.security import create_access_token
        from jose import jwt
        from app.core.config import settings

        token = create_access_token({"sub": "user123"})
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])

        assert "jti" in payload
        assert len(payload["jti"]) > 0

    def test_refresh_token_contains_jti(self):
        """Refresh Token muss JTI enthalten."""
        from app.core.security import create_refresh_token
        from jose import jwt
        from app.core.config import settings

        token = create_refresh_token({"sub": "user123"})
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])

        assert "jti" in payload
        assert len(payload["jti"]) > 0

    def test_access_token_has_correct_type(self):
        """Access Token muss type='access' haben."""
        from app.core.security import create_access_token
        from jose import jwt
        from app.core.config import settings

        token = create_access_token({"sub": "user123"})
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])

        assert payload["type"] == "access"

    def test_refresh_token_has_correct_type(self):
        """Refresh Token muss type='refresh' haben."""
        from app.core.security import create_refresh_token
        from jose import jwt
        from app.core.config import settings

        token = create_refresh_token({"sub": "user123"})
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])

        assert payload["type"] == "refresh"

    def test_token_pair_returns_both_tokens(self):
        """Token-Paar muss beide Token enthalten."""
        from app.core.security import create_token_pair

        tokens = create_token_pair({"sub": "user123", "email": "test@example.com"})

        assert "access_token" in tokens
        assert "refresh_token" in tokens
        assert "token_type" in tokens
        assert tokens["token_type"] == "bearer"


# ==================== Token Blacklisting Tests ====================


class TestTokenBlacklisting:
    """Tests für Token-Blacklisting."""

    @pytest.mark.asyncio
    async def test_blacklist_token_fallback_on_redis_unavailable(self):
        """Token-Blacklisting fällt auf In-Memory zurück wenn Redis nicht verfügbar."""
        from app.core import security as security_module
        from datetime import datetime, timezone, timedelta

        # Ensure Redis is "unavailable"
        security_module._redis_available = False
        security_module._redis_client = None

        expires = datetime.now(timezone.utc) + timedelta(hours=1)
        jti = "test-fallback-jti"

        # Clear any existing entries
        if jti in security_module._token_blacklist_fallback:
            del security_module._token_blacklist_fallback[jti]

        result = await security_module.blacklist_token(jti, expires)

        # Should be in fallback storage
        assert jti in security_module._token_blacklist_fallback

    @pytest.mark.asyncio
    async def test_is_token_blacklisted_checks_fallback(self):
        """is_token_blacklisted prüft auch Fallback-Speicher."""
        from app.core import security as security_module
        from datetime import datetime, timezone, timedelta

        security_module._redis_available = False
        security_module._redis_client = None

        jti = "test-check-fallback-jti"
        expires = datetime.now(timezone.utc) + timedelta(hours=1)

        # Add to fallback
        security_module._token_blacklist_fallback[jti] = expires

        # Should find in fallback
        is_blacklisted = await security_module.is_token_blacklisted(jti)
        assert is_blacklisted is True

        # Cleanup
        if jti in security_module._token_blacklist_fallback:
            del security_module._token_blacklist_fallback[jti]

    @pytest.mark.asyncio
    async def test_expired_token_removed_from_fallback(self):
        """Abgelaufene Tokens werden aus Fallback entfernt."""
        from app.core import security as security_module
        from datetime import datetime, timezone, timedelta

        security_module._redis_available = False
        security_module._redis_client = None

        jti = "test-expired-jti"
        # Already expired
        expires = datetime.now(timezone.utc) - timedelta(hours=1)

        # Add expired entry
        security_module._token_blacklist_fallback[jti] = expires

        # Should return False and remove entry
        is_blacklisted = await security_module.is_token_blacklisted(jti)
        assert is_blacklisted is False

        # Should be removed from fallback
        assert jti not in security_module._token_blacklist_fallback
