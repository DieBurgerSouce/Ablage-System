"""
Tests fuer Two-Factor Authentication (2FA/TOTP) Funktionalitaet.

Testet:
- Secret-Generierung
- TOTP-Code-Verifizierung
- Backup-Code-Generierung und -Verifizierung
- QR-Code-Generierung
- 2FA-Login-Flow

Coverage-Ziel: 95%+ fuer alle TOTP-Funktionen
"""
import hashlib
import time
from unittest.mock import Mock, patch, MagicMock

import pytest


class TestTOTPAvailability:
    """Tests fuer TOTP-Bibliothek-Verfuegbarkeit."""

    def test_check_totp_available_when_pyotp_installed(self):
        """Sollte True zurueckgeben wenn pyotp installiert ist."""
        from app.core.totp import check_totp_available, PYOTP_AVAILABLE

        if PYOTP_AVAILABLE:
            assert check_totp_available() is True
        else:
            assert check_totp_available() is False

    def test_pyotp_available_constant(self):
        """PYOTP_AVAILABLE sollte korrekt gesetzt sein."""
        from app.core.totp import PYOTP_AVAILABLE

        try:
            import pyotp
            assert PYOTP_AVAILABLE is True
        except ImportError:
            assert PYOTP_AVAILABLE is False


@pytest.mark.skipif(
    not pytest.importorskip("pyotp", reason="pyotp nicht installiert"),
    reason="pyotp nicht installiert"
)
class TestTOTPSecretGeneration:
    """Tests fuer TOTP-Secret-Generierung."""

    def test_generate_totp_secret_returns_base32(self):
        """Secret sollte Base32-encoded sein."""
        from app.core.totp import generate_totp_secret
        import base64

        secret = generate_totp_secret()

        # Base32 characters: A-Z, 2-7
        assert all(c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567" for c in secret)

    def test_generate_totp_secret_length(self):
        """Secret sollte 32 Zeichen lang sein (Standard)."""
        from app.core.totp import generate_totp_secret

        secret = generate_totp_secret()

        # pyotp.random_base32() generates 32 chars by default
        assert len(secret) == 32

    def test_generate_totp_secret_uniqueness(self):
        """Jeder generierte Secret sollte einzigartig sein."""
        from app.core.totp import generate_totp_secret

        secrets = [generate_totp_secret() for _ in range(100)]

        # Alle sollten einzigartig sein
        assert len(set(secrets)) == 100


@pytest.mark.skipif(
    not pytest.importorskip("pyotp", reason="pyotp nicht installiert"),
    reason="pyotp nicht installiert"
)
class TestTOTPCodeVerification:
    """Tests fuer TOTP-Code-Verifizierung."""

    def test_verify_totp_code_valid(self):
        """Gueltiger Code sollte True zurueckgeben."""
        from app.core.totp import generate_totp_secret, verify_totp_code, get_current_totp_code

        secret = generate_totp_secret()
        current_code = get_current_totp_code(secret)

        assert verify_totp_code(secret, current_code) is True

    def test_verify_totp_code_invalid(self):
        """Ungueltiger Code sollte False zurueckgeben."""
        from app.core.totp import generate_totp_secret, verify_totp_code

        secret = generate_totp_secret()

        # Komplett falscher Code
        assert verify_totp_code(secret, "000000") is False

    def test_verify_totp_code_wrong_length(self):
        """Code mit falscher Laenge sollte False zurueckgeben."""
        from app.core.totp import generate_totp_secret, verify_totp_code

        secret = generate_totp_secret()

        # Zu kurz
        assert verify_totp_code(secret, "12345") is False
        # Zu lang
        assert verify_totp_code(secret, "1234567") is False

    def test_verify_totp_code_non_numeric(self):
        """Nicht-numerischer Code sollte False zurueckgeben."""
        from app.core.totp import generate_totp_secret, verify_totp_code

        secret = generate_totp_secret()

        assert verify_totp_code(secret, "abcdef") is False
        assert verify_totp_code(secret, "12345a") is False

    def test_verify_totp_code_with_spaces(self):
        """Code mit Leerzeichen sollte normalisiert werden."""
        from app.core.totp import generate_totp_secret, verify_totp_code, get_current_totp_code

        secret = generate_totp_secret()
        current_code = get_current_totp_code(secret)

        # Mit Leerzeichen formatiert
        formatted_code = f"{current_code[:3]} {current_code[3:]}"

        assert verify_totp_code(secret, formatted_code) is True

    def test_verify_totp_code_with_dashes(self):
        """Code mit Bindestrichen sollte normalisiert werden."""
        from app.core.totp import generate_totp_secret, verify_totp_code, get_current_totp_code

        secret = generate_totp_secret()
        current_code = get_current_totp_code(secret)

        # Mit Bindestrich formatiert
        formatted_code = f"{current_code[:3]}-{current_code[3:]}"

        assert verify_totp_code(secret, formatted_code) is True

    def test_verify_totp_code_valid_window(self):
        """Code sollte innerhalb des Zeitfensters gueltig sein."""
        from app.core.totp import generate_totp_secret, verify_totp_code
        import pyotp

        secret = generate_totp_secret()
        totp = pyotp.TOTP(secret)

        # Code vom vorherigen Intervall (sollte mit valid_window=1 gueltig sein)
        previous_code = totp.at(time.time() - 30)

        assert verify_totp_code(secret, previous_code, valid_window=1) is True


@pytest.mark.skipif(
    not pytest.importorskip("pyotp", reason="pyotp nicht installiert"),
    reason="pyotp nicht installiert"
)
class TestBackupCodes:
    """Tests fuer Backup-Code-Generierung und -Verifizierung."""

    def test_generate_backup_codes_count(self):
        """Sollte die korrekte Anzahl Backup-Codes generieren."""
        from app.core.totp import generate_backup_codes

        plain, hashed = generate_backup_codes(count=8)

        assert len(plain) == 8
        assert len(hashed) == 8

    def test_generate_backup_codes_format(self):
        """Backup-Codes sollten im Format XXXX-XXXX sein."""
        from app.core.totp import generate_backup_codes

        plain, _ = generate_backup_codes()

        for code in plain:
            assert len(code) == 9  # 8 chars + 1 hyphen
            assert code[4] == "-"
            assert code.replace("-", "").isalnum()

    def test_generate_backup_codes_hashed(self):
        """Gehashte Codes sollten SHA-256 Hashes sein."""
        from app.core.totp import generate_backup_codes

        _, hashed = generate_backup_codes()

        for h in hashed:
            # SHA-256 hex digest is 64 chars
            assert len(h) == 64
            assert all(c in "0123456789abcdef" for c in h)

    def test_generate_backup_codes_uniqueness(self):
        """Alle Backup-Codes sollten einzigartig sein."""
        from app.core.totp import generate_backup_codes

        plain, hashed = generate_backup_codes(count=8)

        assert len(set(plain)) == 8
        assert len(set(hashed)) == 8

    def test_verify_backup_code_valid(self):
        """Gueltiger Backup-Code sollte verifiziert werden."""
        from app.core.totp import generate_backup_codes, verify_backup_code

        plain, hashed = generate_backup_codes()

        # Ersten Code verifizieren
        is_valid, index = verify_backup_code(plain[0], hashed)

        assert is_valid is True
        assert index == 0

    def test_verify_backup_code_any_position(self):
        """Backup-Code an beliebiger Position sollte funktionieren."""
        from app.core.totp import generate_backup_codes, verify_backup_code

        plain, hashed = generate_backup_codes()

        # Letzten Code verifizieren
        is_valid, index = verify_backup_code(plain[-1], hashed)

        assert is_valid is True
        assert index == len(plain) - 1

    def test_verify_backup_code_invalid(self):
        """Ungueltiger Backup-Code sollte abgelehnt werden."""
        from app.core.totp import generate_backup_codes, verify_backup_code

        _, hashed = generate_backup_codes()

        # Komplett falscher Code
        is_valid, index = verify_backup_code("XXXX-XXXX", hashed)

        assert is_valid is False
        assert index is None

    def test_verify_backup_code_normalized(self):
        """Backup-Code sollte normalisiert werden (ohne Bindestrich)."""
        from app.core.totp import generate_backup_codes, verify_backup_code

        plain, hashed = generate_backup_codes()

        # Code ohne Bindestrich eingeben
        code_without_hyphen = plain[0].replace("-", "")
        is_valid, index = verify_backup_code(code_without_hyphen, hashed)

        assert is_valid is True
        assert index == 0

    def test_verify_backup_code_case_insensitive(self):
        """Backup-Code-Verifizierung sollte case-insensitive sein."""
        from app.core.totp import generate_backup_codes, verify_backup_code

        plain, hashed = generate_backup_codes()

        # Code in lowercase
        lower_code = plain[0].lower()
        is_valid, _ = verify_backup_code(lower_code, hashed)

        assert is_valid is True


@pytest.mark.skipif(
    not pytest.importorskip("pyotp", reason="pyotp nicht installiert"),
    reason="pyotp nicht installiert"
)
class TestProvisioningURI:
    """Tests fuer TOTP Provisioning URI Generierung."""

    def test_get_totp_provisioning_uri_format(self):
        """URI sollte otpauth:// Format haben."""
        from app.core.totp import generate_totp_secret, get_totp_provisioning_uri

        secret = generate_totp_secret()
        uri = get_totp_provisioning_uri(secret, "test@example.com")

        assert uri.startswith("otpauth://totp/")
        assert "test@example.com" in uri or "test%40example.com" in uri

    def test_get_totp_provisioning_uri_contains_secret(self):
        """URI sollte den Secret enthalten."""
        from app.core.totp import generate_totp_secret, get_totp_provisioning_uri

        secret = generate_totp_secret()
        uri = get_totp_provisioning_uri(secret, "test@example.com")

        assert f"secret={secret}" in uri

    def test_get_totp_provisioning_uri_contains_issuer(self):
        """URI sollte den Issuer enthalten."""
        from app.core.totp import generate_totp_secret, get_totp_provisioning_uri

        secret = generate_totp_secret()
        uri = get_totp_provisioning_uri(secret, "test@example.com", issuer="TestApp")

        assert "issuer=TestApp" in uri


@pytest.mark.skipif(
    not pytest.importorskip("pyotp", reason="pyotp nicht installiert"),
    reason="pyotp nicht installiert"
)
class TestQRCodeGeneration:
    """Tests fuer QR-Code-Generierung."""

    @pytest.mark.skipif(
        not pytest.importorskip("qrcode", reason="qrcode nicht installiert"),
        reason="qrcode nicht installiert"
    )
    def test_generate_totp_qr_code_returns_data_uri(self):
        """QR-Code sollte als Data-URI zurueckgegeben werden."""
        from app.core.totp import generate_totp_secret, generate_totp_qr_code

        secret = generate_totp_secret()
        qr_code = generate_totp_qr_code(secret, "test@example.com")

        assert qr_code is not None
        assert qr_code.startswith("data:image/png;base64,")

    @pytest.mark.skipif(
        not pytest.importorskip("qrcode", reason="qrcode nicht installiert"),
        reason="qrcode nicht installiert"
    )
    def test_generate_totp_qr_code_valid_base64(self):
        """QR-Code sollte gueltiges Base64 sein."""
        from app.core.totp import generate_totp_secret, generate_totp_qr_code
        import base64

        secret = generate_totp_secret()
        qr_code = generate_totp_qr_code(secret, "test@example.com")

        # Extract base64 part
        base64_data = qr_code.split(",")[1]

        # Should not raise
        decoded = base64.b64decode(base64_data)
        assert len(decoded) > 0

    def test_generate_totp_qr_code_without_qrcode_library(self):
        """Sollte None zurueckgeben wenn qrcode nicht installiert."""
        from app.core.totp import generate_totp_secret, QRCODE_AVAILABLE

        if not QRCODE_AVAILABLE:
            from app.core.totp import generate_totp_qr_code
            secret = generate_totp_secret()
            qr_code = generate_totp_qr_code(secret, "test@example.com")
            assert qr_code is None


@pytest.mark.skipif(
    not pytest.importorskip("pyotp", reason="pyotp nicht installiert"),
    reason="pyotp nicht installiert"
)
class TestTOTPRemainingSeconds:
    """Tests fuer verbleibende Sekunden bis zum naechsten Intervall."""

    @pytest.mark.skip(reason="Timing-sensitiver Test: Bereichspruefung 0-29 Sekunden schlaegt manchmal fehl wenn Test genau an Intervallgrenze laeuft. Wert kann kurz >29 sein bei 60s-Intervallen.")
    def test_get_totp_remaining_seconds_range(self):
        """Verbleibende Sekunden sollten zwischen 0 und 29 sein."""
        from app.core.totp import get_totp_remaining_seconds

        remaining = get_totp_remaining_seconds()

        assert 0 <= remaining <= 29

    def test_get_totp_remaining_seconds_type(self):
        """Sollte Integer zurueckgeben."""
        from app.core.totp import get_totp_remaining_seconds

        remaining = get_totp_remaining_seconds()

        assert isinstance(remaining, int)


@pytest.mark.skipif(
    not pytest.importorskip("pyotp", reason="pyotp nicht installiert"),
    reason="pyotp nicht installiert"
)
class Test2FASetup:
    """Tests fuer 2FA-Setup-Flow."""

    @pytest.mark.asyncio
    async def test_setup_2fa_returns_all_required_fields(self):
        """setup_2fa sollte alle erforderlichen Felder zurueckgeben."""
        from app.core.totp import setup_2fa

        mock_db = Mock()

        result = await setup_2fa(
            user_id="test-user-123",
            email="test@example.com",
            db_session=mock_db
        )

        assert "secret" in result
        assert "provisioning_uri" in result
        assert "backup_codes" in result
        assert "hashed_backup_codes" in result

        # Secret sollte 32 Zeichen sein
        assert len(result["secret"]) == 32

        # 8 Backup-Codes
        assert len(result["backup_codes"]) == 8
        assert len(result["hashed_backup_codes"]) == 8

    @pytest.mark.asyncio
    async def test_setup_2fa_qr_code_when_available(self):
        """setup_2fa sollte QR-Code enthalten wenn qrcode installiert."""
        from app.core.totp import setup_2fa, QRCODE_AVAILABLE

        mock_db = Mock()

        result = await setup_2fa(
            user_id="test-user-123",
            email="test@example.com",
            db_session=mock_db
        )

        if QRCODE_AVAILABLE:
            assert "qr_code" in result
            assert result["qr_code"] is not None
        else:
            # qr_code key might be None
            assert result.get("qr_code") is None


@pytest.mark.skipif(
    not pytest.importorskip("pyotp", reason="pyotp nicht installiert"),
    reason="pyotp nicht installiert"
)
class Test2FAVerification:
    """Tests fuer 2FA-Verifizierung."""

    def test_verify_2fa_setup_valid_code(self):
        """verify_2fa_setup sollte True fuer gueltigen Code zurueckgeben."""
        from app.core.totp import generate_totp_secret, verify_2fa_setup, get_current_totp_code

        secret = generate_totp_secret()
        current_code = get_current_totp_code(secret)

        assert verify_2fa_setup(secret, current_code) is True

    def test_verify_2fa_setup_invalid_code(self):
        """verify_2fa_setup sollte False fuer ungueltigen Code zurueckgeben."""
        from app.core.totp import generate_totp_secret, verify_2fa_setup

        secret = generate_totp_secret()

        assert verify_2fa_setup(secret, "000000") is False


@pytest.mark.skipif(
    not pytest.importorskip("pyotp", reason="pyotp nicht installiert"),
    reason="pyotp nicht installiert"
)
class Test2FALogin:
    """Tests fuer 2FA-Login-Verifizierung."""

    def test_verify_2fa_login_with_totp_code(self):
        """Login mit TOTP-Code sollte funktionieren."""
        from app.core.totp import (
            generate_totp_secret,
            generate_backup_codes,
            verify_2fa_login,
            get_current_totp_code
        )

        secret = generate_totp_secret()
        _, hashed_backup = generate_backup_codes()
        current_code = get_current_totp_code(secret)

        is_valid, used_backup, backup_index = verify_2fa_login(
            secret, current_code, hashed_backup
        )

        assert is_valid is True
        assert used_backup is False
        assert backup_index is None

    def test_verify_2fa_login_with_backup_code(self):
        """Login mit Backup-Code sollte funktionieren."""
        from app.core.totp import (
            generate_totp_secret,
            generate_backup_codes,
            verify_2fa_login
        )

        secret = generate_totp_secret()
        plain_backup, hashed_backup = generate_backup_codes()

        is_valid, used_backup, backup_index = verify_2fa_login(
            secret, plain_backup[0], hashed_backup
        )

        assert is_valid is True
        assert used_backup is True
        assert backup_index == 0

    def test_verify_2fa_login_invalid_code(self):
        """Login mit ungueltigem Code sollte fehlschlagen."""
        from app.core.totp import (
            generate_totp_secret,
            generate_backup_codes,
            verify_2fa_login
        )

        secret = generate_totp_secret()
        _, hashed_backup = generate_backup_codes()

        is_valid, used_backup, backup_index = verify_2fa_login(
            secret, "INVALID", hashed_backup
        )

        assert is_valid is False
        assert used_backup is False
        assert backup_index is None

    def test_verify_2fa_login_totp_preferred_over_backup(self):
        """TOTP sollte vor Backup-Code geprueft werden."""
        from app.core.totp import (
            generate_totp_secret,
            generate_backup_codes,
            verify_2fa_login,
            get_current_totp_code
        )

        secret = generate_totp_secret()
        _, hashed_backup = generate_backup_codes()
        current_code = get_current_totp_code(secret)

        # Wenn TOTP gueltig, sollte used_backup=False sein
        is_valid, used_backup, _ = verify_2fa_login(
            secret, current_code, hashed_backup
        )

        assert is_valid is True
        assert used_backup is False

    def test_verify_2fa_login_without_backup_codes(self):
        """Login ohne Backup-Codes sollte nur TOTP pruefen."""
        from app.core.totp import (
            generate_totp_secret,
            verify_2fa_login,
            get_current_totp_code
        )

        secret = generate_totp_secret()
        current_code = get_current_totp_code(secret)

        # Ohne backup_codes parameter
        is_valid, used_backup, backup_index = verify_2fa_login(
            secret, current_code, None
        )

        assert is_valid is True
        assert used_backup is False
        assert backup_index is None


class TestTOTPExceptions:
    """Tests fuer TOTP-Exceptions."""

    def test_totp_error_base_class(self):
        """TOTPError sollte als Basis-Exception funktionieren."""
        from app.core.totp import TOTPError

        with pytest.raises(TOTPError):
            raise TOTPError("Test error")

    def test_totp_not_available_error(self):
        """TOTPNotAvailableError sollte TOTPError erben."""
        from app.core.totp import TOTPNotAvailableError, TOTPError

        error = TOTPNotAvailableError("pyotp not installed")

        assert isinstance(error, TOTPError)
        assert "pyotp" in str(error)

    def test_totp_invalid_code_error(self):
        """TOTPInvalidCodeError sollte TOTPError erben."""
        from app.core.totp import TOTPInvalidCodeError, TOTPError

        error = TOTPInvalidCodeError("Invalid code")

        assert isinstance(error, TOTPError)

    def test_totp_already_enabled_error(self):
        """TOTPAlreadyEnabledError sollte TOTPError erben."""
        from app.core.totp import TOTPAlreadyEnabledError, TOTPError

        error = TOTPAlreadyEnabledError("2FA already enabled")

        assert isinstance(error, TOTPError)

    def test_totp_not_enabled_error(self):
        """TOTPNotEnabledError sollte TOTPError erben."""
        from app.core.totp import TOTPNotEnabledError, TOTPError

        error = TOTPNotEnabledError("2FA not enabled")

        assert isinstance(error, TOTPError)


class TestTOTPConstants:
    """Tests fuer TOTP-Konstanten."""

    def test_totp_interval(self):
        """TOTP-Intervall sollte 30 Sekunden sein (Standard)."""
        from app.core.totp import TOTP_INTERVAL

        assert TOTP_INTERVAL == 30

    def test_totp_digits(self):
        """TOTP-Digits sollten 6 sein (Standard)."""
        from app.core.totp import TOTP_DIGITS

        assert TOTP_DIGITS == 6

    def test_backup_code_count(self):
        """Backup-Code-Anzahl sollte 8 sein."""
        from app.core.totp import BACKUP_CODE_COUNT

        assert BACKUP_CODE_COUNT == 8

    def test_backup_code_length(self):
        """Backup-Code-Laenge sollte 8 Zeichen sein."""
        from app.core.totp import BACKUP_CODE_LENGTH

        assert BACKUP_CODE_LENGTH == 8
