"""
Unit tests for Email Verification Service.

Tests:
- Verifizierungs-Token erstellen
- Email verifizieren
- Email-Änderung anfordern
- Rate-Limiting für Resend
- Abgelaufene Tokens bereinigen
"""

import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from app.services.email_verification_service import EmailVerificationService
from app.db.models import User, EmailVerificationToken
from app.core.exceptions import EmailVerificationError


@pytest.fixture
def service():
    """Create EmailVerificationService instance."""
    return EmailVerificationService()


@pytest.fixture
def mock_db():
    """Create mock database session."""
    db = AsyncMock()
    return db


@pytest.fixture
def mock_user():
    """Create mock user object."""
    user = MagicMock(spec=User)
    user.id = uuid4()
    user.email = "test@example.com"
    user.email_verified = False
    user.email_verified_at = None
    return user


@pytest.fixture
def mock_token():
    """Create mock verification token."""
    token = MagicMock(spec=EmailVerificationToken)
    token.id = uuid4()
    token.user_id = uuid4()
    token.token_hash = "a" * 64
    token.email = "test@example.com"
    token.token_type = "verification"
    token.new_email = None
    token.created_at = datetime.now(timezone.utc)
    token.expires_at = datetime.now(timezone.utc) + timedelta(hours=24)
    token.used_at = None
    token.ip_address = "192.168.1.100"
    return token


class TestGenerateToken:
    """Tests for token generation."""

    def test_generate_token_returns_tuple(self, service):
        """Token-Generierung gibt Tuple zurück."""
        plain, hashed = service._generate_token()

        assert isinstance(plain, str)
        assert isinstance(hashed, str)
        assert len(hashed) == 64  # SHA-256 hex

    def test_generate_token_unique(self, service):
        """Jedes Token ist einzigartig."""
        tokens = [service._generate_token() for _ in range(10)]
        plain_tokens = [t[0] for t in tokens]

        assert len(set(plain_tokens)) == 10


class TestHashToken:
    """Tests for token hashing."""

    def test_hash_token_consistent(self, service):
        """Gleicher Input gibt gleichen Hash."""
        token = "test-token-12345"

        hash1 = service._hash_token(token)
        hash2 = service._hash_token(token)

        assert hash1 == hash2

    def test_hash_token_different_inputs(self, service):
        """Unterschiedliche Inputs geben unterschiedliche Hashes."""
        hash1 = service._hash_token("token1")
        hash2 = service._hash_token("token2")

        assert hash1 != hash2


class TestCreateVerificationToken:
    """Tests for create_verification_token method."""

    @pytest.mark.asyncio
    async def test_create_token_success(self, service, mock_db):
        """Token erfolgreich erstellen."""
        user_id = uuid4()
        email = "test@example.com"

        # Mock delete für alte Tokens
        mock_result = MagicMock()
        mock_result.rowcount = 0
        mock_db.execute.return_value = mock_result

        token = await service.create_verification_token(
            mock_db, user_id, email, "192.168.1.100"
        )

        assert isinstance(token, str)
        assert len(token) > 32
        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()


class TestVerifyEmail:
    """Tests for verify_email method."""

    @pytest.mark.asyncio
    async def test_verify_email_success(self, service, mock_db, mock_token, mock_user):
        """Email erfolgreich verifizieren."""
        mock_token.token_type = "verification"

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_token
        mock_db.execute.return_value = mock_result
        mock_db.get.return_value = mock_user

        success, message, user = await service.verify_email(mock_db, "test-token")

        assert success is True
        assert mock_user.email_verified is True
        assert mock_user.email_verified_at is not None
        assert "erfolgreich" in message
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_verify_email_invalid_token(self, service, mock_db):
        """Ungültiges Token."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        success, message, user = await service.verify_email(mock_db, "invalid-token")

        assert success is False
        assert "Ungültiger" in message
        assert user is None

    @pytest.mark.asyncio
    async def test_verify_email_expired_token(self, service, mock_db, mock_token, mock_user):
        """Abgelaufenes Token."""
        mock_token.expires_at = datetime.now(timezone.utc) - timedelta(hours=1)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_token
        mock_db.execute.return_value = mock_result

        success, message, user = await service.verify_email(mock_db, "test-token")

        assert success is False
        assert "abgelaufen" in message

    @pytest.mark.asyncio
    async def test_verify_email_change_success(
        self, service, mock_db, mock_token, mock_user
    ):
        """Email-Änderung erfolgreich."""
        mock_token.token_type = "email_change"
        mock_token.new_email = "new@example.com"

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_token
        mock_db.execute.return_value = mock_result
        mock_db.get.return_value = mock_user

        success, message, user = await service.verify_email(mock_db, "test-token")

        assert success is True
        assert mock_user.email == "new@example.com"
        assert mock_user.email_verified is True
        assert "geändert" in message


class TestCreateEmailChangeToken:
    """Tests for create_email_change_token method."""

    @pytest.mark.asyncio
    async def test_create_email_change_token_success(self, service, mock_db):
        """Email-Änderungs-Token erstellen."""
        user_id = uuid4()

        # Mock: Keine existierende Email
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_result.rowcount = 0
        mock_db.execute.return_value = mock_result

        token = await service.create_email_change_token(
            mock_db,
            user_id,
            "old@example.com",
            "new@example.com",
            "192.168.1.100"
        )

        assert isinstance(token, str)
        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_email_change_token_email_exists(self, service, mock_db, mock_user):
        """Fehler wenn neue Email bereits existiert."""
        # Mock: Email bereits verwendet
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_user
        mock_db.execute.return_value = mock_result

        with pytest.raises(EmailVerificationError) as exc_info:
            await service.create_email_change_token(
                mock_db,
                uuid4(),
                "old@example.com",
                mock_user.email,
                "192.168.1.100"
            )

        assert "bereits verwendet" in str(exc_info.value.user_message_de)


class TestResendVerification:
    """Tests for resend_verification method."""

    @pytest.mark.asyncio
    async def test_resend_verification_success(self, service, mock_db, mock_user):
        """Verifizierung erneut senden."""
        mock_db.get.return_value = mock_user

        # Mock: Keine kürzlichen Tokens
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_result.rowcount = 0
        mock_db.execute.return_value = mock_result

        token = await service.resend_verification(mock_db, mock_user.id, "192.168.1.100")

        assert isinstance(token, str)

    @pytest.mark.asyncio
    async def test_resend_verification_already_verified(self, service, mock_db, mock_user):
        """Bereits verifiziert - kein Token."""
        mock_user.email_verified = True
        mock_db.get.return_value = mock_user

        token = await service.resend_verification(mock_db, mock_user.id)

        assert token is None

    @pytest.mark.asyncio
    async def test_resend_verification_rate_limited(self, service, mock_db, mock_user):
        """Rate-Limiting: Zu viele Anfragen."""
        mock_db.get.return_value = mock_user

        # Mock: 3 kürzliche Tokens
        recent_tokens = [MagicMock() for _ in range(3)]
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = recent_tokens
        mock_db.execute.return_value = mock_result

        with pytest.raises(EmailVerificationError) as exc_info:
            await service.resend_verification(mock_db, mock_user.id)

        assert "Zu viele" in str(exc_info.value.user_message_de)

    @pytest.mark.asyncio
    async def test_resend_verification_user_not_found(self, service, mock_db):
        """Benutzer nicht gefunden."""
        mock_db.get.return_value = None

        with pytest.raises(EmailVerificationError) as exc_info:
            await service.resend_verification(mock_db, uuid4())

        assert "nicht gefunden" in str(exc_info.value.user_message_de)


class TestCheckVerificationStatus:
    """Tests for check_verification_status method."""

    @pytest.mark.asyncio
    async def test_check_status_verified(self, service, mock_db, mock_user):
        """Status: Verifiziert."""
        mock_user.email_verified = True
        mock_user.email_verified_at = datetime.now(timezone.utc)
        mock_db.get.return_value = mock_user

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result

        status = await service.check_verification_status(mock_db, mock_user.id)

        assert status["email_verified"] is True
        assert status["pending_verification"] is False

    @pytest.mark.asyncio
    async def test_check_status_pending(self, service, mock_db, mock_user, mock_token):
        """Status: Verifizierung ausstehend."""
        mock_db.get.return_value = mock_user

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_token]
        mock_db.execute.return_value = mock_result

        status = await service.check_verification_status(mock_db, mock_user.id)

        assert status["email_verified"] is False
        assert status["pending_verification"] is True

    @pytest.mark.asyncio
    async def test_check_status_pending_email_change(
        self, service, mock_db, mock_user, mock_token
    ):
        """Status: Email-Änderung ausstehend."""
        mock_token.token_type = "email_change"
        mock_db.get.return_value = mock_user

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_token]
        mock_db.execute.return_value = mock_result

        status = await service.check_verification_status(mock_db, mock_user.id)

        assert status["pending_email_change"] is True


class TestCleanupExpiredTokens:
    """Tests for cleanup_expired_tokens method."""

    @pytest.mark.asyncio
    async def test_cleanup_expired_tokens(self, service, mock_db):
        """Abgelaufene Tokens bereinigen."""
        mock_result = MagicMock()
        mock_result.rowcount = 5
        mock_db.execute.return_value = mock_result

        count = await service.cleanup_expired_tokens(mock_db)

        assert count == 5
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_cleanup_no_expired_tokens(self, service, mock_db):
        """Keine abgelaufenen Tokens."""
        mock_result = MagicMock()
        mock_result.rowcount = 0
        mock_db.execute.return_value = mock_result

        count = await service.cleanup_expired_tokens(mock_db)

        assert count == 0
