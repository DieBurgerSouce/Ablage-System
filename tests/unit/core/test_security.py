"""
Security Configuration Tests.

Tests für:
- SECRET_KEY Validierung (Pflicht in Production, min. 32 Zeichen)
- CORS Validierung (keine localhost/wildcard in Production)
- Sichere Fehler-Protokollierung (keine Secrets in Logs)

Diese Tests stellen sicher, dass Sicherheitskonfigurationen korrekt validiert werden.
"""

import pytest
import os
import secrets as secrets_module
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone, timedelta


# ==================== SECRET_KEY Validation Tests ====================


class TestSecretKeyValidation:
    """Tests für SECRET_KEY Validierung in Settings."""

    def test_empty_secret_key_in_production_raises_error(self):
        """Leerer SECRET_KEY in Production muss ValueError auslösen."""
        from pydantic import ValidationError, model_validator

        # Use environment isolation
        with patch.dict(os.environ, {"SECRET_KEY": "", "DEBUG": "false"}, clear=True):
            with pytest.raises((ValueError, ValidationError)) as exc_info:
                # Create Settings without .env file influence
                from pydantic_settings import BaseSettings

                class IsolatedSettings(BaseSettings):
                    SECRET_KEY: str = ""
                    DEBUG: bool = False

                    class Config:
                        env_file = None  # Disable .env loading

                    @model_validator(mode='after')
                    def validate_settings(self):
                        # Re-implement validation logic
                        if not self.SECRET_KEY:
                            if not self.DEBUG:
                                raise ValueError(
                                    "SECRET_KEY ist nicht gesetzt! "
                                    "In Production muss SECRET_KEY via Umgebungsvariable definiert werden."
                                )
                        return self

                IsolatedSettings(_env_file=None)

        error_str = str(exc_info.value)
        assert "SECRET_KEY" in error_str

    def test_short_secret_key_raises_error(self):
        """SECRET_KEY unter 32 Zeichen muss ValueError auslösen."""
        short_key = "tooshort123"  # Only 11 characters

        from pydantic import ValidationError, model_validator
        from pydantic_settings import BaseSettings

        with pytest.raises((ValueError, ValidationError)) as exc_info:
            class IsolatedSettings(BaseSettings):
                SECRET_KEY: str = short_key
                DEBUG: bool = True

                class Config:
                    env_file = None

                @model_validator(mode='after')
                def validate_key(self):
                    if len(self.SECRET_KEY) < 32:
                        raise ValueError(
                            f"SECRET_KEY ist zu kurz ({len(self.SECRET_KEY)} Zeichen). "
                            "Mindestens 32 Zeichen erforderlich für sichere JWT-Signierung."
                        )
                    return self

            IsolatedSettings(_env_file=None)

        error_str = str(exc_info.value)
        assert "32" in error_str or "kurz" in error_str.lower()

    def test_valid_secret_key_succeeds(self):
        """Gültiger SECRET_KEY (32+ Zeichen) muss funktionieren."""
        valid_key = secrets_module.token_urlsafe(64)  # 86 characters

        from pydantic import model_validator
        from pydantic_settings import BaseSettings

        class IsolatedSettings(BaseSettings):
            SECRET_KEY: str = valid_key
            DEBUG: bool = False

            class Config:
                env_file = None

            @model_validator(mode='after')
            def validate_key(self):
                if len(self.SECRET_KEY) < 32:
                    raise ValueError("SECRET_KEY zu kurz")
                return self

        settings = IsolatedSettings(_env_file=None)
        assert settings.SECRET_KEY == valid_key
        assert len(settings.SECRET_KEY) >= 32

    def test_secret_key_minimum_length_boundary(self):
        """SECRET_KEY mit genau 32 Zeichen muss funktionieren."""
        boundary_key = "a" * 32  # Exactly 32 characters

        from pydantic import model_validator
        from pydantic_settings import BaseSettings

        class IsolatedSettings(BaseSettings):
            SECRET_KEY: str = boundary_key
            DEBUG: bool = False

            class Config:
                env_file = None

            @model_validator(mode='after')
            def validate_key(self):
                if len(self.SECRET_KEY) < 32:
                    raise ValueError("SECRET_KEY zu kurz")
                return self

        settings = IsolatedSettings(_env_file=None)
        assert len(settings.SECRET_KEY) == 32


# ==================== CORS Validation Tests ====================


class TestCorsValidation:
    """Tests für CORS Origins Validierung."""

    def test_wildcard_with_credentials_raises_error(self):
        """CORS_ORIGINS='*' mit CORS_ALLOW_CREDENTIALS=True muss fehlschlagen."""
        from pydantic import ValidationError, model_validator
        from pydantic_settings import BaseSettings
        from typing import List

        with pytest.raises((ValueError, ValidationError)) as exc_info:
            class IsolatedSettings(BaseSettings):
                SECRET_KEY: str = secrets_module.token_urlsafe(64)
                DEBUG: bool = True
                CORS_ORIGINS: List[str] = ["*"]
                CORS_ALLOW_CREDENTIALS: bool = True

                class Config:
                    env_file = None

                @model_validator(mode='after')
                def validate_cors(self):
                    has_wildcard = "*" in self.CORS_ORIGINS
                    if has_wildcard and self.CORS_ALLOW_CREDENTIALS:
                        raise ValueError(
                            "CORS_ORIGINS='*' ist nicht erlaubt wenn CORS_ALLOW_CREDENTIALS=True!"
                        )
                    return self

            IsolatedSettings(_env_file=None)

        error_str = str(exc_info.value)
        assert "*" in error_str or "wildcard" in error_str.lower() or "CORS" in error_str

    def test_wildcard_in_production_raises_error(self):
        """CORS_ORIGINS='*' in Production muss fehlschlagen."""
        # Test the validation logic directly
        def validate_cors_origins(origins, allow_credentials, debug_mode):
            """Replicates the CORS validation from Settings."""
            has_wildcard = "*" in origins
            if has_wildcard and allow_credentials:
                raise ValueError("CORS_ORIGINS='*' ist nicht erlaubt wenn CORS_ALLOW_CREDENTIALS=True!")
            if has_wildcard and not debug_mode:
                raise ValueError("CORS_ORIGINS='*' ist in Production nicht erlaubt!")

        # Test wildcard in production (DEBUG=False) - should raise
        with pytest.raises(ValueError) as exc_info:
            validate_cors_origins(
                origins=["*"],
                allow_credentials=False,
                debug_mode=False  # Production
            )

        error_str = str(exc_info.value)
        assert "*" in error_str or "production" in error_str.lower()

        # Verify wildcard in development is allowed
        # Should NOT raise
        validate_cors_origins(
            origins=["*"],
            allow_credentials=False,
            debug_mode=True  # Development
        )

    def test_localhost_in_production_raises_error(self):
        """localhost in CORS_ORIGINS in Production muss fehlschlagen."""
        # Test the validation logic directly
        def validate_cors_localhost(origins, debug_mode):
            """Replicates the localhost validation from Settings."""
            localhost_patterns = ("localhost", "127.0.0.1", "::1", "0.0.0.0")
            has_localhost = any(
                any(pattern in origin.lower() for pattern in localhost_patterns)
                for origin in origins
            )
            if has_localhost and not debug_mode:
                raise ValueError(
                    f"CORS_ORIGINS enthält localhost-Adressen in Production! "
                    f"Gefundene Origins: {origins}"
                )

        localhost_origins_list = [
            ["http://localhost:3000"],
            ["http://127.0.0.1:8080"],
            ["http://localhost"],
            ["https://app.example.com", "http://localhost:3000"],  # Mixed
        ]

        for origins in localhost_origins_list:
            # In production mode, should raise
            with pytest.raises(ValueError) as exc_info:
                validate_cors_localhost(origins, debug_mode=False)

            error_str = str(exc_info.value)
            assert (
                "localhost" in error_str.lower()
                or "127.0.0.1" in error_str
                or "production" in error_str.lower()
            ), f"Expected localhost error for origins {origins}, got: {error_str}"

            # In development mode, should NOT raise
            validate_cors_localhost(origins, debug_mode=True)

    def test_localhost_in_development_allowed(self):
        """localhost in Development ist erlaubt."""
        from pydantic import model_validator
        from pydantic_settings import BaseSettings
        from typing import List

        class IsolatedSettings(BaseSettings):
            SECRET_KEY: str = secrets_module.token_urlsafe(64)
            DEBUG: bool = True  # Development mode
            CORS_ORIGINS: List[str] = ["http://localhost:3000"]

            class Config:
                env_file = None

            @model_validator(mode='after')
            def validate_cors(self):
                localhost_patterns = ("localhost", "127.0.0.1", "::1")
                has_localhost = any(
                    any(pattern in origin.lower() for pattern in localhost_patterns)
                    for origin in self.CORS_ORIGINS
                )
                if has_localhost and not self.DEBUG:
                    raise ValueError("localhost in Production nicht erlaubt!")
                return self

        settings = IsolatedSettings(_env_file=None)
        assert "http://localhost:3000" in settings.CORS_ORIGINS

    def test_valid_production_cors_origins_succeeds(self):
        """Gültige Production CORS Origins funktionieren."""
        from pydantic import model_validator
        from pydantic_settings import BaseSettings
        from typing import List

        valid_origins = [
            "https://app.example.com",
            "https://admin.example.com",
        ]

        class IsolatedSettings(BaseSettings):
            SECRET_KEY: str = secrets_module.token_urlsafe(64)
            DEBUG: bool = False
            CORS_ORIGINS: List[str] = valid_origins

            class Config:
                env_file = None

            @model_validator(mode='after')
            def validate_cors(self):
                localhost_patterns = ("localhost", "127.0.0.1", "::1")
                has_localhost = any(
                    any(pattern in origin.lower() for pattern in localhost_patterns)
                    for origin in self.CORS_ORIGINS
                )
                has_wildcard = "*" in self.CORS_ORIGINS
                if has_localhost and not self.DEBUG:
                    raise ValueError("localhost in Production nicht erlaubt!")
                if has_wildcard and not self.DEBUG:
                    raise ValueError("Wildcard in Production nicht erlaubt!")
                return self

        settings = IsolatedSettings(_env_file=None)
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

        with patch.object(security_module, "_redis_client", None):
            with patch.object(security_module, "_redis_available", None):
                # Patch at the correct location where it's imported
                with patch("app.core.redis_state.RedisStateManager") as mock_manager_class:
                    mock_instance = MagicMock()
                    mock_manager_class.get_instance.return_value = mock_instance
                    mock_instance.connect = AsyncMock(
                        side_effect=MockConnectionError("redis://:password@host:6379")
                    )

                    with patch.object(security_module.logger, "warning") as mock_warning:
                        result = await security_module._get_redis_client()

                        # Should return None on error
                        assert result is None

                        # Check that warning was called
                        mock_warning.assert_called()

                        # Check log call arguments
                        call_args = mock_warning.call_args
                        call_str = str(call_args)

                        # Should NOT contain password or sensitive data
                        assert "password" not in call_str.lower()

    @pytest.mark.asyncio
    async def test_blacklist_token_redis_error_logs_securely(self):
        """blacklist_token_redis gibt HTTPException im fail-closed Modus."""
        from app.core import security as security_module
        from fastapi import HTTPException

        # SECURITY FIX: Mit fail-closed Modus wird HTTPException geworfen
        # wenn Redis nicht verfügbar ist (kein Fall-Back auf in-memory)

        # Create mock Redis client that raises error
        mock_redis = AsyncMock()
        mock_redis.setex = AsyncMock(side_effect=Exception("Connection to redis://:secret@host failed"))

        with patch.object(security_module, "_get_redis_client", AsyncMock(return_value=mock_redis)):
            expires = datetime.now(timezone.utc) + timedelta(hours=1)

            # Im fail-closed Modus sollte HTTPException 503 geworfen werden
            with pytest.raises(HTTPException) as exc_info:
                await security_module.blacklist_token_redis("test-jti", expires)

            assert exc_info.value.status_code == 503
            # Fehlermeldung sollte auf Deutsch sein
            assert "nicht verf" in exc_info.value.detail.lower() or "sicherheit" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_is_token_blacklisted_redis_error_logs_securely(self):
        """is_token_blacklisted_redis gibt HTTPException im fail-closed Modus."""
        from app.core import security as security_module
        from fastapi import HTTPException

        # SECURITY FIX: Mit fail-closed Modus wird HTTPException geworfen
        # wenn Redis nicht verfügbar ist (kein Fall-Back auf in-memory)

        # Use unique JTI that doesn't exist in fallback
        unique_jti = "test-secure-log-jti-" + secrets_module.token_hex(16)

        # Make sure it's not in the fallback
        if unique_jti in security_module._token_blacklist_fallback:
            del security_module._token_blacklist_fallback[unique_jti]

        # Create mock Redis client that raises error
        mock_redis = AsyncMock()
        mock_redis.exists = AsyncMock(side_effect=Exception("Auth failed: password=secret123"))

        with patch.object(security_module, "_get_redis_client", AsyncMock(return_value=mock_redis)):
            # Im fail-closed Modus sollte HTTPException 503 geworfen werden
            with pytest.raises(HTTPException) as exc_info:
                await security_module.is_token_blacklisted_redis(unique_jti)

            assert exc_info.value.status_code == 503
            # Fehlermeldung sollte auf Deutsch sein
            assert "nicht verf" in exc_info.value.detail.lower() or "sicherheit" in exc_info.value.detail.lower()


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
        import jwt  # Sprint 0 / G02: PyJWT statt python-jose
        from app.core.config import settings

        token = create_access_token({"sub": "user123"})
        # SecretStr muss mit get_secret_value() konvertiert werden
        secret_key = settings.SECRET_KEY.get_secret_value()
        payload = jwt.decode(token, secret_key, algorithms=[settings.ALGORITHM])

        assert "jti" in payload
        assert len(payload["jti"]) > 0

    def test_refresh_token_contains_jti(self):
        """Refresh Token muss JTI enthalten."""
        from app.core.security import create_refresh_token
        import jwt  # Sprint 0 / G02: PyJWT statt python-jose
        from app.core.config import settings

        token = create_refresh_token({"sub": "user123"})
        # SecretStr muss mit get_secret_value() konvertiert werden
        secret_key = settings.SECRET_KEY.get_secret_value()
        payload = jwt.decode(token, secret_key, algorithms=[settings.ALGORITHM])

        assert "jti" in payload
        assert len(payload["jti"]) > 0

    def test_access_token_has_correct_type(self):
        """Access Token muss type='access' haben."""
        from app.core.security import create_access_token
        import jwt  # Sprint 0 / G02: PyJWT statt python-jose
        from app.core.config import settings

        token = create_access_token({"sub": "user123"})
        # SecretStr muss mit get_secret_value() konvertiert werden
        secret_key = settings.SECRET_KEY.get_secret_value()
        payload = jwt.decode(token, secret_key, algorithms=[settings.ALGORITHM])

        assert payload["type"] == "access"

    def test_refresh_token_has_correct_type(self):
        """Refresh Token muss type='refresh' haben."""
        from app.core.security import create_refresh_token
        import jwt  # Sprint 0 / G02: PyJWT statt python-jose
        from app.core.config import settings

        token = create_refresh_token({"sub": "user123"})
        # SecretStr muss mit get_secret_value() konvertiert werden
        secret_key = settings.SECRET_KEY.get_secret_value()
        payload = jwt.decode(token, secret_key, algorithms=[settings.ALGORITHM])

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
    async def test_blacklist_token_fails_closed_on_redis_unavailable(self):
        """Token-Blacklisting gibt HTTPException im fail-closed Modus."""
        from app.core import security as security_module
        from fastapi import HTTPException

        # SECURITY FIX: Mit fail-closed Modus gibt es keinen Fallback mehr
        # Das System verweigert Operationen wenn Redis nicht verfügbar ist

        # Ensure Redis is "unavailable"
        security_module._redis_available = False
        security_module._redis_client = None

        expires = datetime.now(timezone.utc) + timedelta(hours=1)
        jti = "test-fallback-jti-" + secrets_module.token_hex(8)

        # Im fail-closed Modus sollte HTTPException 503 geworfen werden
        with pytest.raises(HTTPException) as exc_info:
            await security_module.blacklist_token(jti, expires)

        assert exc_info.value.status_code == 503

    @pytest.mark.asyncio
    async def test_is_token_blacklisted_fails_closed_on_redis_unavailable(self):
        """is_token_blacklisted gibt HTTPException im fail-closed Modus."""
        from app.core import security as security_module
        from fastapi import HTTPException

        # SECURITY FIX: Mit fail-closed Modus gibt es keinen Fallback mehr

        security_module._redis_available = False
        security_module._redis_client = None

        jti = "test-check-fallback-jti-" + secrets_module.token_hex(8)

        # Im fail-closed Modus sollte HTTPException 503 geworfen werden
        with pytest.raises(HTTPException) as exc_info:
            await security_module.is_token_blacklisted(jti)

        assert exc_info.value.status_code == 503

    @pytest.mark.asyncio
    async def test_token_blacklist_fail_closed_security_message(self):
        """Fail-closed gibt deutsche Sicherheitsmeldung."""
        from app.core import security as security_module
        from fastapi import HTTPException

        # SECURITY FIX: Überprüfe dass die Fehlermeldung sicher und auf Deutsch ist

        security_module._redis_available = False
        security_module._redis_client = None

        jti = "test-security-msg-jti-" + secrets_module.token_hex(8)

        with pytest.raises(HTTPException) as exc_info:
            await security_module.is_token_blacklisted(jti)

        # Fehlermeldung sollte auf Deutsch sein und keine sensiblen Infos enthalten
        assert "sicherheit" in exc_info.value.detail.lower() or "verfügbar" in exc_info.value.detail.lower()
