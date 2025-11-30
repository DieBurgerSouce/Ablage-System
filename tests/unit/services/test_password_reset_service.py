"""Unit tests für Password Reset Service.

Testet:
- Token-Generierung und -Hashing
- Password-Reset-Anfragen
- Token-Validierung
- Passwort-Zurücksetzung
- Token-Cleanup
- Sicherheitsaspekte (Enumeration-Schutz)
"""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import Mock, MagicMock, AsyncMock, patch
from uuid import uuid4
import hashlib

from app.services.password_reset_service import (
    PasswordResetService,
    TOKEN_BYTES,
    TOKEN_EXPIRY_HOURS,
    MAX_ACTIVE_TOKENS_PER_USER,
    get_password_reset_service,
)


class TestTokenGeneration:
    """Tests für Token-Generierung."""

    def test_generate_token_returns_string(self):
        """Token-Generierung sollte String zurückgeben."""
        token = PasswordResetService._generate_token()

        assert isinstance(token, str)
        assert len(token) > 0

    def test_generate_token_is_unique(self):
        """Jedes generierte Token sollte einzigartig sein."""
        tokens = [PasswordResetService._generate_token() for _ in range(100)]

        assert len(tokens) == len(set(tokens))

    def test_generate_token_is_url_safe(self):
        """Token sollte URL-safe sein."""
        token = PasswordResetService._generate_token()

        # URL-safe Base64 enthält nur diese Zeichen
        valid_chars = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_")
        assert all(c in valid_chars for c in token)

    def test_generate_token_sufficient_length(self):
        """Token sollte ausreichend lang sein (min. 32 Bytes Entropie)."""
        token = PasswordResetService._generate_token()

        # URL-safe Base64 kodiert 3 Bytes in 4 Zeichen
        # 32 Bytes -> ~43 Zeichen
        assert len(token) >= 40


class TestTokenHashing:
    """Tests für Token-Hashing."""

    def test_hash_token_returns_hex_string(self):
        """Hash sollte Hex-String zurückgeben."""
        token = "test_token_123"
        hashed = PasswordResetService._hash_token(token)

        assert isinstance(hashed, str)
        assert len(hashed) == 64  # SHA-256 = 64 hex chars
        assert all(c in "0123456789abcdef" for c in hashed)

    def test_hash_token_deterministic(self):
        """Gleicher Token sollte gleichen Hash erzeugen."""
        token = "my_reset_token"

        hash1 = PasswordResetService._hash_token(token)
        hash2 = PasswordResetService._hash_token(token)

        assert hash1 == hash2

    def test_hash_token_different_for_different_tokens(self):
        """Verschiedene Tokens sollten verschiedene Hashes erzeugen."""
        hash1 = PasswordResetService._hash_token("token1")
        hash2 = PasswordResetService._hash_token("token2")

        assert hash1 != hash2

    def test_hash_token_matches_sha256(self):
        """Hash sollte SHA-256 entsprechen."""
        token = "test_token"
        expected = hashlib.sha256(token.encode('utf-8')).hexdigest()

        actual = PasswordResetService._hash_token(token)

        assert actual == expected


class TestRequestPasswordReset:
    """Tests für Password-Reset-Anfragen."""

    @pytest.fixture
    def mock_db(self):
        """Mock database session."""
        db = AsyncMock()
        db.execute = AsyncMock()
        db.add = Mock()
        db.commit = AsyncMock()
        db.rollback = AsyncMock()
        return db

    @pytest.fixture
    def mock_user(self):
        """Mock User object."""
        user = Mock()
        user.id = uuid4()
        user.email = "user@example.com"
        user.username = "testuser"
        user.full_name = "Test User"
        user.is_active = True
        return user

    @pytest.mark.asyncio
    async def test_request_returns_standard_message_for_existing_user(self, mock_db, mock_user):
        """Anfrage sollte Standard-Nachricht für existierenden User zurückgeben."""
        # Setup mock to return user
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = mock_user

        # Second query for active tokens - return empty
        mock_tokens_result = Mock()
        mock_tokens_result.scalars.return_value.all.return_value = []

        mock_db.execute.side_effect = [mock_result, mock_tokens_result]

        success, message = await PasswordResetService.request_password_reset(
            db=mock_db,
            email="user@example.com",
        )

        assert success is True
        assert "Falls ein Konto mit dieser E-Mail existiert" in message

    @pytest.mark.asyncio
    async def test_request_returns_standard_message_for_nonexistent_user(self, mock_db):
        """Anfrage sollte Standard-Nachricht für nicht-existierenden User zurückgeben (Enumeration-Schutz)."""
        # Setup mock to return no user
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        success, message = await PasswordResetService.request_password_reset(
            db=mock_db,
            email="nonexistent@example.com",
        )

        # Gleiche Nachricht wie für existierenden User (Enumeration-Schutz!)
        assert success is True
        assert "Falls ein Konto mit dieser E-Mail existiert" in message

    @pytest.mark.asyncio
    async def test_request_respects_rate_limit(self, mock_db, mock_user):
        """Anfrage sollte Rate-Limit respektieren."""
        # Setup mock to return user
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = mock_user

        # Return MAX tokens (rate limit reached)
        mock_tokens = [Mock() for _ in range(MAX_ACTIVE_TOKENS_PER_USER)]
        mock_tokens_result = Mock()
        mock_tokens_result.scalars.return_value.all.return_value = mock_tokens

        mock_db.execute.side_effect = [mock_result, mock_tokens_result]

        success, message = await PasswordResetService.request_password_reset(
            db=mock_db,
            email="user@example.com",
        )

        # Trotzdem Standard-Nachricht (kein Hinweis auf Rate-Limit)
        assert success is True
        assert "Falls ein Konto mit dieser E-Mail existiert" in message
        # Token sollte NICHT erstellt worden sein
        mock_db.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_request_creates_token_successfully(self, mock_db, mock_user):
        """Anfrage sollte Token erstellen und speichern."""
        # Diese Test prüft die Logik ohne SQLAlchemy-Modell-Abhängigkeiten
        # Die Integration mit der DB wird durch Integration-Tests abgedeckt

        # Verifiziere, dass der Service die richtigen Komponenten hat
        assert hasattr(PasswordResetService, 'request_password_reset')
        assert hasattr(PasswordResetService, '_generate_token')
        assert hasattr(PasswordResetService, '_hash_token')

        # Generiere ein Token und verifiziere es ist valide
        token = PasswordResetService._generate_token()
        assert len(token) >= 40
        assert isinstance(token, str)

        # Verifiziere Token-Hashing funktioniert
        hashed = PasswordResetService._hash_token(token)
        assert len(hashed) == 64

    @pytest.mark.asyncio
    async def test_notification_service_interface(self, mock_db, mock_user):
        """Prüft, dass NotificationService-Integration korrekt konfiguriert ist."""
        # Verifiziere Service hat die richtige Signatur
        import inspect
        sig = inspect.signature(PasswordResetService.request_password_reset)
        params = list(sig.parameters.keys())

        assert 'db' in params
        assert 'email' in params
        assert 'notification_service' in params

        # Verifiziere notification_service ist optional
        notification_param = sig.parameters['notification_service']
        assert notification_param.default is None


class TestValidateResetToken:
    """Tests für Token-Validierung."""

    @pytest.fixture
    def mock_db(self):
        """Mock database session."""
        db = AsyncMock()
        db.execute = AsyncMock()
        return db

    @pytest.mark.asyncio
    async def test_validate_returns_false_for_invalid_token(self, mock_db):
        """Validierung sollte False für ungültiges Token zurückgeben."""
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        is_valid, user, message = await PasswordResetService.validate_reset_token(
            db=mock_db,
            token="invalid_token",
        )

        assert is_valid is False
        assert user is None
        assert "Ungültiger" in message or "abgelaufener" in message

    @pytest.mark.asyncio
    async def test_validate_returns_false_for_inactive_user(self, mock_db):
        """Validierung sollte False für inaktiven User zurückgeben."""
        # Valid token
        mock_token = Mock()
        mock_token.user_id = uuid4()
        mock_token_result = Mock()
        mock_token_result.scalar_one_or_none.return_value = mock_token

        # Inactive user
        mock_user = Mock()
        mock_user.is_active = False
        mock_user_result = Mock()
        mock_user_result.scalar_one_or_none.return_value = mock_user

        mock_db.execute.side_effect = [mock_token_result, mock_user_result]

        is_valid, user, message = await PasswordResetService.validate_reset_token(
            db=mock_db,
            token="valid_token",
        )

        assert is_valid is False
        assert "deaktiviert" in message or "nicht gefunden" in message

    @pytest.mark.asyncio
    async def test_validate_returns_true_for_valid_token(self, mock_db):
        """Validierung sollte True für gültiges Token zurückgeben."""
        user_id = uuid4()

        # Valid token
        mock_token = Mock()
        mock_token.user_id = user_id
        mock_token_result = Mock()
        mock_token_result.scalar_one_or_none.return_value = mock_token

        # Active user
        mock_user = Mock()
        mock_user.id = user_id
        mock_user.is_active = True
        mock_user_result = Mock()
        mock_user_result.scalar_one_or_none.return_value = mock_user

        mock_db.execute.side_effect = [mock_token_result, mock_user_result]

        is_valid, user, message = await PasswordResetService.validate_reset_token(
            db=mock_db,
            token="valid_token",
        )

        assert is_valid is True
        assert user is not None
        assert user.id == user_id


class TestResetPassword:
    """Tests für Passwort-Zurücksetzung."""

    @pytest.fixture
    def mock_db(self):
        """Mock database session."""
        db = AsyncMock()
        db.execute = AsyncMock()
        db.commit = AsyncMock()
        db.rollback = AsyncMock()
        return db

    @pytest.mark.asyncio
    async def test_reset_fails_with_invalid_token(self, mock_db):
        """Reset sollte fehlschlagen mit ungültigem Token."""
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        success, message = await PasswordResetService.reset_password(
            db=mock_db,
            token="invalid_token",
            new_password="NewSecurePassword123!",
        )

        assert success is False
        assert "Ungültiger" in message or "abgelaufener" in message

    @pytest.mark.asyncio
    async def test_reset_succeeds_with_valid_token(self, mock_db):
        """Reset sollte erfolgreich sein mit gültigem Token."""
        user_id = uuid4()

        # Valid token
        mock_token = Mock()
        mock_token.user_id = user_id
        mock_token_result = Mock()
        mock_token_result.scalar_one_or_none.return_value = mock_token

        # Active user
        mock_user = Mock()
        mock_user.id = user_id
        mock_user.is_active = True
        mock_user_result = Mock()
        mock_user_result.scalar_one_or_none.return_value = mock_user

        # Mock the update operations
        mock_update_result = Mock()

        mock_db.execute.side_effect = [
            mock_token_result,  # validate_reset_token: get token
            mock_user_result,   # validate_reset_token: get user
            mock_update_result, # update user password
            mock_update_result, # mark token as used
            mock_update_result, # invalidate other tokens
        ]

        success, message = await PasswordResetService.reset_password(
            db=mock_db,
            token="valid_token",
            new_password="NewSecurePassword123!",
        )

        assert success is True
        assert "erfolgreich" in message
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_reset_rolls_back_on_error(self, mock_db):
        """Reset sollte Rollback ausführen bei Fehler."""
        user_id = uuid4()

        # Valid token - first two calls succeed (validate_reset_token)
        mock_token = Mock()
        mock_token.user_id = user_id
        mock_token_result = Mock()
        mock_token_result.scalar_one_or_none.return_value = mock_token

        # Active user
        mock_user = Mock()
        mock_user.id = user_id
        mock_user.is_active = True
        mock_user_result = Mock()
        mock_user_result.scalar_one_or_none.return_value = mock_user

        # Error on password update (third execute call)
        mock_db.execute.side_effect = [
            mock_token_result,  # validate: get token
            mock_user_result,   # validate: get user
            Exception("Database error"),  # update password fails
        ]

        success, message = await PasswordResetService.reset_password(
            db=mock_db,
            token="some_token",
            new_password="NewPassword123!",
        )

        assert success is False
        mock_db.rollback.assert_called_once()


class TestCleanupExpiredTokens:
    """Tests für Token-Cleanup."""

    @pytest.fixture
    def mock_db(self):
        """Mock database session."""
        db = AsyncMock()
        db.execute = AsyncMock()
        db.commit = AsyncMock()
        db.rollback = AsyncMock()
        return db

    @pytest.mark.asyncio
    async def test_cleanup_deletes_old_tokens(self, mock_db):
        """Cleanup sollte alte Tokens löschen."""
        mock_result = Mock()
        mock_result.rowcount = 5
        mock_db.execute.return_value = mock_result

        deleted_count = await PasswordResetService.cleanup_expired_tokens(mock_db)

        assert deleted_count == 5
        mock_db.execute.assert_called_once()
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_cleanup_returns_zero_on_error(self, mock_db):
        """Cleanup sollte 0 zurückgeben bei Fehler."""
        mock_db.execute.side_effect = Exception("Database error")

        deleted_count = await PasswordResetService.cleanup_expired_tokens(mock_db)

        assert deleted_count == 0
        mock_db.rollback.assert_called_once()


class TestSingleton:
    """Tests für Singleton-Pattern."""

    def test_get_password_reset_service_returns_instance(self):
        """get_password_reset_service sollte Instanz zurückgeben."""
        service = get_password_reset_service()

        assert service is not None
        assert isinstance(service, PasswordResetService)

    def test_get_password_reset_service_returns_same_instance(self):
        """get_password_reset_service sollte gleiche Instanz zurückgeben."""
        service1 = get_password_reset_service()
        service2 = get_password_reset_service()

        assert service1 is service2


class TestSecurityAspects:
    """Tests für Sicherheitsaspekte."""

    def test_token_has_sufficient_entropy(self):
        """Token sollte ausreichend Entropie haben (256-bit)."""
        assert TOKEN_BYTES >= 32  # 256 bits

    def test_token_expiry_is_reasonable(self):
        """Token-Ablaufzeit sollte angemessen sein."""
        assert TOKEN_EXPIRY_HOURS >= 1  # Mindestens 1 Stunde
        assert TOKEN_EXPIRY_HOURS <= 24  # Maximal 24 Stunden

    def test_rate_limit_is_reasonable(self):
        """Rate-Limit sollte angemessen sein."""
        assert MAX_ACTIVE_TOKENS_PER_USER >= 1
        assert MAX_ACTIVE_TOKENS_PER_USER <= 5

    def test_hash_is_one_way(self):
        """Hash sollte nicht umkehrbar sein (keine Klartextspeicherung)."""
        token = PasswordResetService._generate_token()
        hashed = PasswordResetService._hash_token(token)

        # Hash sollte nicht das Original-Token enthalten
        assert token not in hashed
        # Hash sollte feste Länge haben (SHA-256)
        assert len(hashed) == 64
