"""
Tests fuer Security Audit Logger.

Testet:
- Event-Logging
- Sensitive-Data-Filterung
- Convenience-Methoden
- Singleton-Instanz

Coverage-Ziel: 90%+ fuer alle Audit-Funktionen
"""
from unittest.mock import Mock, AsyncMock, patch
import pytest


class TestSecurityEventType:
    """Tests fuer SecurityEventType Enum."""

    def test_authentication_events_exist(self):
        """Authentifizierungs-Events sollten definiert sein."""
        from app.core.audit_logger import SecurityEventType

        assert SecurityEventType.LOGIN_SUCCESS.value == "login_success"
        assert SecurityEventType.LOGIN_FAILED.value == "login_failed"
        assert SecurityEventType.LOGOUT.value == "logout"
        assert SecurityEventType.TOKEN_REFRESH.value == "token_refresh"
        assert SecurityEventType.TOKEN_REVOKED.value == "token_revoked"

    def test_2fa_events_exist(self):
        """2FA-Events sollten definiert sein."""
        from app.core.audit_logger import SecurityEventType

        assert SecurityEventType.TWO_FA_SETUP_INITIATED.value == "2fa_setup_initiated"
        assert SecurityEventType.TWO_FA_ENABLED.value == "2fa_enabled"
        assert SecurityEventType.TWO_FA_DISABLED.value == "2fa_disabled"
        assert SecurityEventType.TWO_FA_BACKUP_USED.value == "2fa_backup_used"
        assert SecurityEventType.TWO_FA_FAILED.value == "2fa_failed"

    def test_account_events_exist(self):
        """Account-Events sollten definiert sein."""
        from app.core.audit_logger import SecurityEventType

        assert SecurityEventType.ACCOUNT_CREATED.value == "account_created"
        assert SecurityEventType.ACCOUNT_LOCKED.value == "account_locked"
        assert SecurityEventType.ACCOUNT_UNLOCKED.value == "account_unlocked"

    def test_password_events_exist(self):
        """Passwort-Events sollten definiert sein."""
        from app.core.audit_logger import SecurityEventType

        assert SecurityEventType.PASSWORD_CHANGED.value == "password_changed"
        assert SecurityEventType.PASSWORD_RESET_REQUESTED.value == "password_reset_requested"
        assert SecurityEventType.PASSWORD_RESET_COMPLETED.value == "password_reset_completed"

    def test_security_violation_events_exist(self):
        """Sicherheitsverletzungs-Events sollten definiert sein."""
        from app.core.audit_logger import SecurityEventType

        assert SecurityEventType.RATE_LIMIT_EXCEEDED.value == "rate_limit_exceeded"
        assert SecurityEventType.BRUTE_FORCE_DETECTED.value == "brute_force_detected"
        assert SecurityEventType.INVALID_TOKEN_USED.value == "invalid_token_used"
        assert SecurityEventType.UNAUTHORIZED_ACCESS.value == "unauthorized_access"


class TestSensitiveDataFiltering:
    """Tests fuer sensitive Datenfilterung."""

    def test_filter_password_fields(self):
        """Passwort-Felder sollten gefiltert werden."""
        from app.core.audit_logger import SecurityAuditLogger

        logger = SecurityAuditLogger()
        data = {
            "username": "test",
            "password": "secret123",
            "password_hash": "abc123hash"
        }

        filtered = logger._filter_sensitive_data(data)

        assert filtered["username"] == "test"
        assert filtered["password"] == "[REDACTED]"
        assert filtered["password_hash"] == "[REDACTED]"

    def test_filter_token_fields(self):
        """Token-Felder sollten gefiltert werden."""
        from app.core.audit_logger import SecurityAuditLogger

        logger = SecurityAuditLogger()
        data = {
            "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
            "access_token": "access123",
            "refresh_token": "refresh456"
        }

        filtered = logger._filter_sensitive_data(data)

        assert filtered["token"] == "[REDACTED]"
        assert filtered["access_token"] == "[REDACTED]"
        assert filtered["refresh_token"] == "[REDACTED]"

    def test_filter_secret_fields(self):
        """Secret-Felder sollten gefiltert werden."""
        from app.core.audit_logger import SecurityAuditLogger

        logger = SecurityAuditLogger()
        data = {
            "secret": "my-secret",
            "totp_secret": "JBSWY3DPEHPK3PXP",
            "api_key": "key123"
        }

        filtered = logger._filter_sensitive_data(data)

        assert filtered["secret"] == "[REDACTED]"
        assert filtered["totp_secret"] == "[REDACTED]"
        assert filtered["api_key"] == "[REDACTED]"

    def test_mask_email(self):
        """E-Mail sollte maskiert werden."""
        from app.core.audit_logger import SecurityAuditLogger

        logger = SecurityAuditLogger()
        data = {"email": "test@example.com"}

        filtered = logger._filter_sensitive_data(data)

        assert filtered["email"] == "tes***"

    def test_mask_short_email(self):
        """Kurze E-Mail sollte vollstaendig maskiert werden."""
        from app.core.audit_logger import SecurityAuditLogger

        logger = SecurityAuditLogger()
        data = {"email": "ab"}

        filtered = logger._filter_sensitive_data(data)

        assert filtered["email"] == "***"

    def test_truncate_user_id(self):
        """User-ID sollte gekuerzt werden."""
        from app.core.audit_logger import SecurityAuditLogger

        logger = SecurityAuditLogger()
        data = {"user_id": "12345678-1234-1234-1234-123456789012"}

        filtered = logger._filter_sensitive_data(data)

        assert filtered["user_id"] == "12345678..."

    def test_keep_safe_fields(self):
        """Sichere Felder sollten unveraendert bleiben."""
        from app.core.audit_logger import SecurityAuditLogger

        logger = SecurityAuditLogger()
        data = {
            "action": "login",
            "ip_address": "192.168.1.1",
            "timestamp": "2024-01-01T00:00:00Z"
        }

        filtered = logger._filter_sensitive_data(data)

        assert filtered["action"] == "login"
        assert filtered["ip_address"] == "192.168.1.1"
        assert filtered["timestamp"] == "2024-01-01T00:00:00Z"


class TestSecurityAuditLoggerInit:
    """Tests fuer SecurityAuditLogger Initialisierung."""

    def test_init_without_db(self):
        """Logger sollte ohne DB-Session initialisierbar sein."""
        from app.core.audit_logger import SecurityAuditLogger

        logger = SecurityAuditLogger()

        assert logger.db is None

    def test_init_with_db(self):
        """Logger sollte mit DB-Session initialisierbar sein."""
        from app.core.audit_logger import SecurityAuditLogger

        mock_db = Mock()
        logger = SecurityAuditLogger(db=mock_db)

        assert logger.db is mock_db


class TestLogEvent:
    """Tests fuer log_event Methode."""

    @pytest.mark.asyncio
    async def test_log_event_without_db(self):
        """log_event sollte ohne DB funktionieren (nur structlog)."""
        from app.core.audit_logger import SecurityAuditLogger, SecurityEventType

        logger = SecurityAuditLogger()

        with patch("app.core.audit_logger.logger") as mock_structlog:
            result = await logger.log_event(
                event_type=SecurityEventType.LOGIN_SUCCESS,
                user_id="12345678-1234-1234-1234-123456789012",
                ip_address="192.168.1.1"
            )

            # Sollte None zurueckgeben (keine DB-ID)
            assert result is None

            # structlog sollte aufgerufen worden sein
            mock_structlog.info.assert_called_once()

    @pytest.mark.asyncio
    async def test_log_event_with_warning_severity(self):
        """Events mit warning severity sollten als warning geloggt werden."""
        from app.core.audit_logger import SecurityAuditLogger, SecurityEventType

        logger = SecurityAuditLogger()

        with patch("app.core.audit_logger.logger") as mock_structlog:
            await logger.log_event(
                event_type=SecurityEventType.LOGIN_FAILED,
                severity="warning"
            )

            mock_structlog.warning.assert_called_once()

    @pytest.mark.asyncio
    async def test_log_event_with_error_severity(self):
        """Events mit error severity sollten als error geloggt werden."""
        from app.core.audit_logger import SecurityAuditLogger, SecurityEventType

        logger = SecurityAuditLogger()

        with patch("app.core.audit_logger.logger") as mock_structlog:
            await logger.log_event(
                event_type=SecurityEventType.INVALID_TOKEN_USED,
                severity="error"
            )

            mock_structlog.error.assert_called_once()

    @pytest.mark.asyncio
    async def test_log_event_with_critical_severity(self):
        """Events mit critical severity sollten als critical geloggt werden."""
        from app.core.audit_logger import SecurityAuditLogger, SecurityEventType

        logger = SecurityAuditLogger()

        with patch("app.core.audit_logger.logger") as mock_structlog:
            await logger.log_event(
                event_type=SecurityEventType.BRUTE_FORCE_DETECTED,
                severity="critical"
            )

            mock_structlog.critical.assert_called_once()


class TestConvenienceMethods:
    """Tests fuer Convenience-Methoden."""

    @pytest.mark.asyncio
    async def test_log_login_success(self):
        """log_login_success sollte korrekten Event-Typ verwenden."""
        from app.core.audit_logger import SecurityAuditLogger, SecurityEventType

        logger = SecurityAuditLogger()

        with patch.object(logger, "log_event", new_callable=AsyncMock) as mock_log:
            await logger.log_login_success(
                user_id="test-user-123",
                ip_address="192.168.1.1"
            )

            mock_log.assert_called_once_with(
                event_type=SecurityEventType.LOGIN_SUCCESS,
                user_id="test-user-123",
                ip_address="192.168.1.1",
                user_agent=None,
                details=None
            )

    @pytest.mark.asyncio
    async def test_log_login_failed(self):
        """log_login_failed sollte korrekten Event-Typ und Severity verwenden."""
        from app.core.audit_logger import SecurityAuditLogger, SecurityEventType

        logger = SecurityAuditLogger()

        with patch.object(logger, "log_event", new_callable=AsyncMock) as mock_log:
            await logger.log_login_failed(
                email="test@example.com",
                ip_address="192.168.1.1",
                reason="invalid_password"
            )

            mock_log.assert_called_once()
            call_kwargs = mock_log.call_args[1]
            assert call_kwargs["event_type"] == SecurityEventType.LOGIN_FAILED
            assert call_kwargs["severity"] == "warning"
            assert call_kwargs["details"]["reason"] == "invalid_password"

    @pytest.mark.asyncio
    async def test_log_2fa_enabled(self):
        """log_2fa_enabled sollte korrekten Event-Typ verwenden."""
        from app.core.audit_logger import SecurityAuditLogger, SecurityEventType

        logger = SecurityAuditLogger()

        with patch.object(logger, "log_event", new_callable=AsyncMock) as mock_log:
            await logger.log_2fa_enabled(
                user_id="test-user-123",
                ip_address="192.168.1.1"
            )

            mock_log.assert_called_once_with(
                event_type=SecurityEventType.TWO_FA_ENABLED,
                user_id="test-user-123",
                ip_address="192.168.1.1"
            )

    @pytest.mark.asyncio
    async def test_log_2fa_disabled(self):
        """log_2fa_disabled sollte warning severity haben."""
        from app.core.audit_logger import SecurityAuditLogger, SecurityEventType

        logger = SecurityAuditLogger()

        with patch.object(logger, "log_event", new_callable=AsyncMock) as mock_log:
            await logger.log_2fa_disabled(
                user_id="test-user-123",
                used_backup=True
            )

            call_kwargs = mock_log.call_args[1]
            assert call_kwargs["event_type"] == SecurityEventType.TWO_FA_DISABLED
            assert call_kwargs["severity"] == "warning"
            assert call_kwargs["details"]["used_backup_code"] is True

    @pytest.mark.asyncio
    async def test_log_account_locked(self):
        """log_account_locked sollte Details enthalten."""
        from app.core.audit_logger import SecurityAuditLogger, SecurityEventType

        logger = SecurityAuditLogger()

        with patch.object(logger, "log_event", new_callable=AsyncMock) as mock_log:
            await logger.log_account_locked(
                user_id="test-user-123",
                lockout_duration_seconds=900,
                failed_attempts=5
            )

            call_kwargs = mock_log.call_args[1]
            assert call_kwargs["details"]["lockout_duration_seconds"] == 900
            assert call_kwargs["details"]["failed_attempts"] == 5

    @pytest.mark.asyncio
    async def test_log_brute_force_detected(self):
        """log_brute_force_detected sollte critical severity haben."""
        from app.core.audit_logger import SecurityAuditLogger, SecurityEventType

        logger = SecurityAuditLogger()

        with patch.object(logger, "log_event", new_callable=AsyncMock) as mock_log:
            await logger.log_brute_force_detected(
                ip_address="192.168.1.1",
                target_email="test@example.com",
                attempts=100
            )

            call_kwargs = mock_log.call_args[1]
            assert call_kwargs["event_type"] == SecurityEventType.BRUTE_FORCE_DETECTED
            assert call_kwargs["severity"] == "critical"
            assert call_kwargs["details"]["attempts"] == 100

    @pytest.mark.asyncio
    async def test_log_password_changed(self):
        """log_password_changed sollte forced_by_admin Detail enthalten."""
        from app.core.audit_logger import SecurityAuditLogger, SecurityEventType

        logger = SecurityAuditLogger()

        with patch.object(logger, "log_event", new_callable=AsyncMock) as mock_log:
            await logger.log_password_changed(
                user_id="test-user-123",
                forced_by_admin=True
            )

            call_kwargs = mock_log.call_args[1]
            assert call_kwargs["details"]["forced_by_admin"] is True

    @pytest.mark.asyncio
    async def test_log_role_changed(self):
        """log_role_changed sollte alte und neue Rolle enthalten."""
        from app.core.audit_logger import SecurityAuditLogger, SecurityEventType

        logger = SecurityAuditLogger()

        with patch.object(logger, "log_event", new_callable=AsyncMock) as mock_log:
            await logger.log_role_changed(
                user_id="test-user-123",
                admin_id="admin-456",
                old_role="user",
                new_role="admin"
            )

            call_kwargs = mock_log.call_args[1]
            assert call_kwargs["details"]["old_role"] == "user"
            assert call_kwargs["details"]["new_role"] == "admin"
            assert call_kwargs["details"]["admin_id"] == "admin-456"
            assert call_kwargs["severity"] == "warning"

    @pytest.mark.asyncio
    async def test_log_unauthorized_access(self):
        """log_unauthorized_access sollte Resource-Info enthalten."""
        from app.core.audit_logger import SecurityAuditLogger, SecurityEventType

        logger = SecurityAuditLogger()

        with patch.object(logger, "log_event", new_callable=AsyncMock) as mock_log:
            await logger.log_unauthorized_access(
                user_id="test-user-123",
                resource_type="document",
                resource_id="doc-789",
                reason="no_permission"
            )

            call_kwargs = mock_log.call_args[1]
            assert call_kwargs["resource_type"] == "document"
            assert call_kwargs["resource_id"] == "doc-789"
            assert call_kwargs["details"]["reason"] == "no_permission"


class TestGetAuditLogger:
    """Tests fuer get_audit_logger Factory."""

    def test_get_audit_logger_without_db(self):
        """Sollte Singleton zurueckgeben ohne DB."""
        from app.core.audit_logger import get_audit_logger

        logger1 = get_audit_logger()
        logger2 = get_audit_logger()

        assert logger1 is logger2

    def test_get_audit_logger_with_db(self):
        """Sollte neue Instanz zurueckgeben mit DB."""
        from app.core.audit_logger import get_audit_logger

        mock_db = Mock()
        logger = get_audit_logger(db=mock_db)

        assert logger.db is mock_db

    def test_get_audit_logger_with_db_creates_new_instance(self):
        """Mit DB sollte jedes Mal neue Instanz erstellt werden."""
        from app.core.audit_logger import get_audit_logger

        mock_db1 = Mock()
        mock_db2 = Mock()

        logger1 = get_audit_logger(db=mock_db1)
        logger2 = get_audit_logger(db=mock_db2)

        assert logger1 is not logger2
        assert logger1.db is mock_db1
        assert logger2.db is mock_db2


# ==================== AP6: Immutability Tests ====================

class TestCalculateEntryHash:
    """Tests fuer Hash-Berechnung (AP6)."""

    def test_calculate_hash_returns_sha256(self):
        """Hash sollte SHA-256 Format haben (64 Hex-Zeichen)."""
        from app.core.audit_logger import calculate_entry_hash, GENESIS_HASH
        from datetime import datetime, timezone

        result = calculate_entry_hash(
            sequence_number=1,
            user_id="test-user",
            action="login_success",
            resource_type="security",
            resource_id=None,
            ip_address="192.168.1.1",
            created_at=datetime.now(timezone.utc),
            metadata={},
            previous_hash=GENESIS_HASH,
        )

        assert isinstance(result, str)
        assert len(result) == 64
        assert all(c in '0123456789abcdef' for c in result)

    def test_calculate_hash_deterministic(self):
        """Gleiche Inputs sollten gleichen Hash erzeugen."""
        from app.core.audit_logger import calculate_entry_hash, GENESIS_HASH
        from datetime import datetime, timezone

        timestamp = datetime(2025, 11, 30, 12, 0, 0, tzinfo=timezone.utc)
        args = {
            "sequence_number": 1,
            "user_id": "test-user",
            "action": "login_success",
            "resource_type": "security",
            "resource_id": None,
            "ip_address": "192.168.1.1",
            "created_at": timestamp,
            "metadata": {"key": "value"},
            "previous_hash": GENESIS_HASH,
        }

        hash1 = calculate_entry_hash(**args)
        hash2 = calculate_entry_hash(**args)

        assert hash1 == hash2

    def test_calculate_hash_changes_with_sequence(self):
        """Aenderung der Sequenznummer aendert Hash."""
        from app.core.audit_logger import calculate_entry_hash, GENESIS_HASH
        from datetime import datetime, timezone

        timestamp = datetime(2025, 11, 30, 12, 0, 0, tzinfo=timezone.utc)
        base_args = {
            "user_id": "test-user",
            "action": "login_success",
            "resource_type": "security",
            "resource_id": None,
            "ip_address": "192.168.1.1",
            "created_at": timestamp,
            "metadata": {},
            "previous_hash": GENESIS_HASH,
        }

        hash1 = calculate_entry_hash(sequence_number=1, **base_args)
        hash2 = calculate_entry_hash(sequence_number=2, **base_args)

        assert hash1 != hash2

    def test_calculate_hash_changes_with_previous_hash(self):
        """Aenderung des previous_hash aendert Hash."""
        from app.core.audit_logger import calculate_entry_hash, GENESIS_HASH
        from datetime import datetime, timezone

        timestamp = datetime(2025, 11, 30, 12, 0, 0, tzinfo=timezone.utc)
        base_args = {
            "sequence_number": 1,
            "user_id": "test-user",
            "action": "login_success",
            "resource_type": "security",
            "resource_id": None,
            "ip_address": "192.168.1.1",
            "created_at": timestamp,
            "metadata": {},
        }

        hash1 = calculate_entry_hash(previous_hash=GENESIS_HASH, **base_args)
        hash2 = calculate_entry_hash(previous_hash="a" * 64, **base_args)

        assert hash1 != hash2


class TestVerifyEntryIntegrity:
    """Tests fuer Integritaetspruefung (AP6)."""

    def test_verify_valid_entry(self):
        """Gueltiger Eintrag sollte verifiziert werden."""
        from app.core.audit_logger import (
            calculate_entry_hash,
            verify_entry_integrity,
            GENESIS_HASH
        )
        from datetime import datetime, timezone

        timestamp = datetime(2025, 11, 30, 12, 0, 0, tzinfo=timezone.utc)

        entry = Mock()
        entry.sequence_number = 1
        entry.user_id = None
        entry.action = "login_success"
        entry.resource_type = "security"
        entry.resource_id = None
        entry.ip_address = "192.168.1.1"
        entry.created_at = timestamp
        entry.audit_metadata = {}
        entry.previous_hash = GENESIS_HASH

        entry.integrity_hash = calculate_entry_hash(
            sequence_number=1,
            user_id=None,
            action="login_success",
            resource_type="security",
            resource_id=None,
            ip_address="192.168.1.1",
            created_at=timestamp,
            metadata={},
            previous_hash=GENESIS_HASH,
        )

        is_valid, error = verify_entry_integrity(entry)

        assert is_valid is True
        assert error is None

    def test_verify_tampered_entry(self):
        """Manipulierter Eintrag sollte erkannt werden."""
        from app.core.audit_logger import verify_entry_integrity, GENESIS_HASH
        from datetime import datetime, timezone

        timestamp = datetime(2025, 11, 30, 12, 0, 0, tzinfo=timezone.utc)

        entry = Mock()
        entry.sequence_number = 1
        entry.user_id = None
        entry.action = "login_success"
        entry.resource_type = "security"
        entry.resource_id = None
        entry.ip_address = "192.168.1.1"
        entry.created_at = timestamp
        entry.audit_metadata = {}
        entry.previous_hash = GENESIS_HASH
        entry.integrity_hash = "0" * 64  # Falscher Hash

        is_valid, error = verify_entry_integrity(entry)

        assert is_valid is False
        assert "mismatch" in error.lower()

    def test_verify_chain_broken(self):
        """Unterbrochene Kette sollte erkannt werden."""
        from app.core.audit_logger import (
            calculate_entry_hash,
            verify_entry_integrity,
        )
        from datetime import datetime, timezone

        timestamp = datetime(2025, 11, 30, 12, 0, 0, tzinfo=timezone.utc)

        entry = Mock()
        entry.sequence_number = 2
        entry.user_id = None
        entry.action = "login_success"
        entry.resource_type = "security"
        entry.resource_id = None
        entry.ip_address = "192.168.1.1"
        entry.created_at = timestamp
        entry.audit_metadata = {}
        entry.previous_hash = "a" * 64

        entry.integrity_hash = calculate_entry_hash(
            sequence_number=2,
            user_id=None,
            action="login_success",
            resource_type="security",
            resource_id=None,
            ip_address="192.168.1.1",
            created_at=timestamp,
            metadata={},
            previous_hash="a" * 64,
        )

        # Pruefe mit falschem expected_previous_hash
        is_valid, error = verify_entry_integrity(entry, expected_previous_hash="b" * 64)

        assert is_valid is False
        assert "chain broken" in error.lower()


class TestGenesisHash:
    """Tests fuer GENESIS_HASH Konstante (AP6)."""

    def test_genesis_hash_format(self):
        """GENESIS_HASH sollte 64 Nullen sein."""
        from app.core.audit_logger import GENESIS_HASH

        assert len(GENESIS_HASH) == 64
        assert all(c == '0' for c in GENESIS_HASH)

    def test_genesis_hash_is_constant(self):
        """GENESIS_HASH sollte konstant sein."""
        from app.core.audit_logger import GENESIS_HASH

        expected = "0" * 64
        assert GENESIS_HASH == expected
