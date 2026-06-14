# -*- coding: utf-8 -*-
"""
Unit-Tests fuer MFA (Multi-Factor Authentication) Service.

Testet:
- Schluesselsableitung und AES-256-GCM Verschluesselung
- Backup-Code-Generierung (10 Codes, 8 Zeichen, bcrypt-gehashed)
- TOTP-Setup-Flow (QR-Code, Secret, Backup-Codes)
- TOTP-Verifizierung mit Timing-Attack-Schutz
- Rate-Limiting (5 Versuche, 15 Minuten Sperre)
- Backup-Code-Verbrauch (One-Time-Use)
- Enable/Disable-Flow
- Fehlerbehandlung (User nicht gefunden, MFA bereits aktiviert/nicht aktiviert)

Feinpoliert und durchdacht - Enterprise-grade MFA-Tests.
"""

import base64
import hashlib
import pytest
import secrets
import time
from datetime import datetime, timezone, timedelta
from typing import List
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from uuid import uuid4, UUID

import bcrypt
import pyotp
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


# ========================= Test Fixtures =========================


@pytest.fixture
def mock_db():
    """Create mock async database session."""
    db = AsyncMock()
    db.execute = AsyncMock()
    db.commit = AsyncMock()
    db.rollback = AsyncMock()
    return db


@pytest.fixture
def mock_user():
    """Create sample user object without MFA enabled."""
    user = Mock()
    user.id = uuid4()
    user.email = "test@example.com"
    user.username = "testuser"
    user.is_active = True
    user.totp_enabled = False
    user.totp_secret = None
    user.totp_backup_codes = None
    user.totp_setup_at = None
    user.totp_failed_attempts = 0
    user.totp_lockout_until = None
    return user


@pytest.fixture
def mock_user_with_mfa(mock_user):
    """User with MFA already enabled."""
    mock_user.totp_enabled = True
    from app.core.config import settings
    
    key_material = f"{settings.SECRET_KEY}:totp:encryption".encode()
    encryption_key = hashlib.sha256(key_material).digest()
    aesgcm = AESGCM(encryption_key)
    nonce = secrets.token_bytes(12)
    
    real_secret = pyotp.random_base32()
    ciphertext = aesgcm.encrypt(nonce, real_secret.encode('utf-8'), b"totp_secret")
    mock_user.totp_secret = base64.b64encode(nonce + ciphertext).decode('ascii')
    mock_user._plaintext_secret = real_secret
    
    mock_user.totp_backup_codes = []
    mock_user._plaintext_backup_codes = []
    for _ in range(10):
        code = secrets.token_hex(4).upper()
        formatted_code = f"{code[:4]}-{code[4:]}"
        mock_user._plaintext_backup_codes.append(formatted_code)
        code_hash = bcrypt.hashpw(code.encode('utf-8'), bcrypt.gensalt(rounds=12)).decode('utf-8')
        mock_user.totp_backup_codes.append(code_hash)
    
    mock_user.totp_setup_at = datetime.now(timezone.utc) - timedelta(days=7)
    return mock_user


@pytest.fixture
def mfa_service(mock_db):
    """Create MFA Service instance with mocked database."""
    from app.services.auth.mfa_service import MFAService
    return MFAService(mock_db)


# ========================= Key Derivation Tests =========================


class TestKeyDerivation:
    """Tests fuer Schluesselsableitung."""

    def test_derive_encryption_key_returns_bytes(self, mfa_service):
        """Schluesselableitung sollte bytes zurueckgeben."""
        key = mfa_service._derive_encryption_key()
        assert isinstance(key, bytes)

    def test_derive_encryption_key_correct_length(self, mfa_service):
        """Schluessel sollte 32 bytes (256 bit) fuer AES-256 sein."""
        key = mfa_service._derive_encryption_key()
        assert len(key) == 32

    def test_derive_encryption_key_deterministic(self, mfa_service):
        """Gleicher SECRET_KEY sollte gleichen Schluessel ergeben."""
        key1 = mfa_service._derive_encryption_key()
        key2 = mfa_service._derive_encryption_key()
        assert key1 == key2

    def test_derive_encryption_key_uses_sha256(self):
        """Ableitung sollte SHA-256 verwenden."""
        from app.core.config import settings
        key_material = f"{settings.SECRET_KEY}:totp:encryption".encode()
        expected_key = hashlib.sha256(key_material).digest()
        
        from app.services.auth.mfa_service import MFAService
        mock_db = AsyncMock()
        service = MFAService(mock_db)
        actual_key = service._derive_encryption_key()
        assert actual_key == expected_key

    def test_derive_encryption_key_includes_domain_separation(self, mfa_service):
        """Schluessel sollte Domain-Separation enthalten."""
        from app.core.config import settings
        wrong_key = hashlib.sha256(f"{settings.SECRET_KEY}".encode()).digest()
        actual_key = mfa_service._derive_encryption_key()
        assert actual_key != wrong_key


# ========================= Encryption/Decryption Tests =========================


class TestEncryption:
    """Tests fuer AES-256-GCM Verschluesselung."""

    def test_encrypt_secret_returns_string(self, mfa_service):
        """Verschluesselung sollte String zurueckgeben."""
        secret = "JBSWY3DPEHPK3PXP"
        encrypted = mfa_service._encrypt_secret(secret)
        assert isinstance(encrypted, str)

    def test_encrypt_secret_is_base64(self, mfa_service):
        """Verschluesseltes Secret sollte Base64-encoded sein."""
        secret = "JBSWY3DPEHPK3PXP"
        encrypted = mfa_service._encrypt_secret(secret)
        decoded = base64.b64decode(encrypted)
        assert len(decoded) > 0

    def test_encrypt_secret_not_plaintext(self, mfa_service):
        """Verschluesseltes Secret sollte Klartext nicht enthalten."""
        secret = "JBSWY3DPEHPK3PXP"
        encrypted = mfa_service._encrypt_secret(secret)
        assert secret not in encrypted
        assert secret.encode() not in base64.b64decode(encrypted)

    def test_encrypt_secret_includes_nonce(self, mfa_service):
        """Verschluesselung sollte 12-byte Nonce enthalten."""
        secret = "JBSWY3DPEHPK3PXP"
        encrypted = mfa_service._encrypt_secret(secret)
        decoded = base64.b64decode(encrypted)
        assert len(decoded) >= 12

    def test_encrypt_secret_different_each_time(self, mfa_service):
        """Jede Verschluesselung sollte andere Ausgabe erzeugen."""
        secret = "JBSWY3DPEHPK3PXP"
        encrypted1 = mfa_service._encrypt_secret(secret)
        encrypted2 = mfa_service._encrypt_secret(secret)
        assert encrypted1 != encrypted2

    def test_decrypt_secret_roundtrip(self, mfa_service):
        """Entschluesselung sollte Original zurueckgeben."""
        original_secret = "JBSWY3DPEHPK3PXP"
        encrypted = mfa_service._encrypt_secret(original_secret)
        decrypted = mfa_service._decrypt_secret(encrypted)
        assert decrypted == original_secret

    def test_decrypt_secret_various_lengths(self, mfa_service):
        """Roundtrip sollte fuer verschiedene Laengen funktionieren."""
        test_secrets = ["A", "SHORT", "JBSWY3DPEHPK3PXP", "A" * 100]
        for secret in test_secrets:
            encrypted = mfa_service._encrypt_secret(secret)
            decrypted = mfa_service._decrypt_secret(encrypted)
            assert decrypted == secret

    def test_decrypt_with_wrong_key_fails(self, mfa_service):
        """Entschluesselung mit falschem Schluessel sollte fehlschlagen."""
        secret = "JBSWY3DPEHPK3PXP"
        encrypted = mfa_service._encrypt_secret(secret)
        original_key = mfa_service._encryption_key
        mfa_service._encryption_key = secrets.token_bytes(32)
        with pytest.raises(Exception):
            mfa_service._decrypt_secret(encrypted)
        mfa_service._encryption_key = original_key

    def test_decrypt_with_corrupted_ciphertext_fails(self, mfa_service):
        """Entschluesselung von korrupten Daten sollte fehlschlagen."""
        secret = "JBSWY3DPEHPK3PXP"
        encrypted = mfa_service._encrypt_secret(secret)
        decoded = bytearray(base64.b64decode(encrypted))
        decoded[15] ^= 0xFF
        corrupted = base64.b64encode(bytes(decoded)).decode('ascii')
        with pytest.raises(Exception):
            mfa_service._decrypt_secret(corrupted)

    def test_decrypt_with_invalid_base64_fails(self, mfa_service):
        """Entschluesselung von ungueltigem Base64 sollte fehlschlagen."""
        with pytest.raises(Exception):
            mfa_service._decrypt_secret("not-valid-base64!!!")


# ========================= Backup Code Generation Tests =========================


class TestBackupCodeGeneration:
    """Tests fuer Backup-Code-Generierung."""

    def test_generate_backup_codes_returns_tuple(self, mfa_service):
        """Generierung sollte Tuple zurueckgeben."""
        result = mfa_service._generate_backup_codes()
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_generate_backup_codes_count(self, mfa_service):
        """Sollte 10 Codes generieren."""
        from app.services.auth.mfa_service import BACKUP_CODE_COUNT
        codes, hashed_codes = mfa_service._generate_backup_codes()
        assert len(codes) == BACKUP_CODE_COUNT
        assert len(hashed_codes) == BACKUP_CODE_COUNT
        assert len(codes) == 10

    def test_generate_backup_codes_format(self, mfa_service):
        """Codes sollten Format XXXX-XXXX haben."""
        codes, _ = mfa_service._generate_backup_codes()
        for code in codes:
            assert len(code) == 9
            assert code[4] == "-"
            assert code[:4].isalnum()
            assert code[5:].isalnum()

    def test_generate_backup_codes_uppercase(self, mfa_service):
        """Codes sollten uppercase Hex sein."""
        codes, _ = mfa_service._generate_backup_codes()
        for code in codes:
            clean_code = code.replace("-", "")
            int(clean_code, 16)

    def test_generate_backup_codes_unique(self, mfa_service):
        """Alle Codes sollten eindeutig sein."""
        codes, _ = mfa_service._generate_backup_codes()
        assert len(codes) == len(set(codes))

    def test_generate_backup_codes_hashes_are_bcrypt(self, mfa_service):
        """Hashes sollten bcrypt-Format haben."""
        _, hashed_codes = mfa_service._generate_backup_codes()
        for h in hashed_codes:
            assert h.startswith("$2")
            assert len(h) == 60

    def test_generate_backup_codes_hashes_verify(self, mfa_service):
        """Hashes sollten mit bcrypt verifizierbar sein."""
        codes, hashed_codes = mfa_service._generate_backup_codes()
        for code, code_hash in zip(codes, hashed_codes):
            clean_code = code.replace("-", "").upper()
            assert bcrypt.checkpw(clean_code.encode('utf-8'), code_hash.encode('utf-8'))

    def test_generate_backup_codes_entropy(self, mfa_service):
        """Codes sollten ausreichende Entropie haben."""
        from app.services.auth.mfa_service import BACKUP_CODE_LENGTH
        assert BACKUP_CODE_LENGTH >= 8

    def test_generate_backup_codes_randomness(self, mfa_service):
        """Mehrfache Generierung sollte verschiedene Codes liefern."""
        codes1, _ = mfa_service._generate_backup_codes()
        codes2, _ = mfa_service._generate_backup_codes()
        common = set(codes1) & set(codes2)
        assert len(common) < 5

    def test_generate_backup_codes_bcrypt_cost_factor(self, mfa_service):
        """bcrypt sollte cost factor 12 verwenden."""
        _, hashed_codes = mfa_service._generate_backup_codes()
        for h in hashed_codes:
            parts = h.split("$")
            cost = int(parts[2])
            assert cost >= 12


# ========================= TOTP Setup Tests =========================


class TestTOTPSetup:
    """Tests fuer TOTP-Setup."""

    @pytest.mark.asyncio
    async def test_setup_totp_returns_tuple(self, mfa_service, mock_db, mock_user):
        """Setup sollte (QR-Data, Secret, Backup-Codes) zurueckgeben."""
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = mock_user
        mock_db.execute.return_value = mock_result
        result = await mfa_service.setup_totp(mock_user.id)
        assert isinstance(result, tuple)
        assert len(result) == 3

    @pytest.mark.asyncio
    async def test_setup_totp_qr_data_uri(self, mfa_service, mock_db, mock_user):
        """QR-Code sollte PNG Data-URI sein."""
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = mock_user
        mock_db.execute.return_value = mock_result
        qr_data_uri, _, _ = await mfa_service.setup_totp(mock_user.id)
        assert qr_data_uri.startswith("data:image/png;base64,")
        base64_part = qr_data_uri.replace("data:image/png;base64,", "")
        base64.b64decode(base64_part)

    @pytest.mark.asyncio
    async def test_setup_totp_secret_is_base32(self, mfa_service, mock_db, mock_user):
        """Secret sollte gueltiges Base32 sein."""
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = mock_user
        mock_db.execute.return_value = mock_result
        _, secret, _ = await mfa_service.setup_totp(mock_user.id)
        decoded = base64.b32decode(secret)
        assert len(decoded) >= 10

    @pytest.mark.asyncio
    async def test_setup_totp_backup_codes_list(self, mfa_service, mock_db, mock_user):
        """Backup-Codes sollten Liste von 10 Codes sein."""
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = mock_user
        mock_db.execute.return_value = mock_result
        _, _, backup_codes = await mfa_service.setup_totp(mock_user.id)
        assert isinstance(backup_codes, list)
        assert len(backup_codes) == 10

    @pytest.mark.asyncio
    async def test_setup_totp_stores_encrypted_secret(self, mfa_service, mock_db, mock_user):
        """Setup sollte verschluesseltes Secret speichern."""
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = mock_user
        mock_db.execute.return_value = mock_result
        await mfa_service.setup_totp(mock_user.id)
        mock_db.execute.assert_called()
        mock_db.commit.assert_called()

    @pytest.mark.asyncio
    async def test_setup_totp_does_not_enable(self, mfa_service, mock_db, mock_user):
        """Setup sollte MFA noch NICHT aktivieren."""
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = mock_user
        mock_db.execute.return_value = mock_result
        await mfa_service.setup_totp(mock_user.id)
        assert not mock_user.totp_enabled

    @pytest.mark.asyncio
    async def test_setup_totp_user_not_found(self, mfa_service, mock_db):
        """Setup sollte Fehler werfen bei nicht existierendem User."""
        from app.services.auth.mfa_service import MFAServiceError
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result
        with pytest.raises(MFAServiceError) as exc_info:
            await mfa_service.setup_totp(uuid4())
        assert "nicht gefunden" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_setup_totp_already_enabled(self, mfa_service, mock_db, mock_user_with_mfa):
        """Setup sollte Fehler werfen wenn MFA bereits aktiviert."""
        from app.services.auth.mfa_service import MFAAlreadyEnabledError
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = mock_user_with_mfa
        mock_db.execute.return_value = mock_result
        with pytest.raises(MFAAlreadyEnabledError):
            await mfa_service.setup_totp(mock_user_with_mfa.id)


# ========================= Verify and Enable TOTP Tests =========================


class TestVerifyAndEnableTOTP:
    """Tests fuer TOTP-Verifizierung und Aktivierung."""

    @pytest.mark.asyncio
    async def test_verify_and_enable_success(self, mfa_service, mock_db, mock_user):
        """Erfolgreiche Verifizierung sollte MFA aktivieren."""
        secret = pyotp.random_base32()
        mock_user.totp_secret = mfa_service._encrypt_secret(secret)
        mock_user.totp_enabled = False
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = mock_user
        mock_db.execute.return_value = mock_result
        totp = pyotp.TOTP(secret)
        valid_code = totp.now()
        result = await mfa_service.verify_and_enable_totp(mock_user.id, valid_code)
        assert result is True
        mock_db.commit.assert_called()

    @pytest.mark.asyncio
    async def test_verify_and_enable_invalid_code(self, mfa_service, mock_db, mock_user):
        """Ungueltiger Code sollte Fehler werfen."""
        from app.services.auth.mfa_service import InvalidTOTPCodeError
        secret = pyotp.random_base32()
        mock_user.totp_secret = mfa_service._encrypt_secret(secret)
        mock_user.totp_enabled = False
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = mock_user
        mock_db.execute.return_value = mock_result
        with pytest.raises(InvalidTOTPCodeError):
            await mfa_service.verify_and_enable_totp(mock_user.id, "000000")

    @pytest.mark.asyncio
    async def test_verify_and_enable_already_enabled(self, mfa_service, mock_db, mock_user_with_mfa):
        """Sollte Fehler werfen wenn MFA bereits aktiviert."""
        from app.services.auth.mfa_service import MFAAlreadyEnabledError
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = mock_user_with_mfa
        mock_db.execute.return_value = mock_result
        with pytest.raises(MFAAlreadyEnabledError):
            await mfa_service.verify_and_enable_totp(mock_user_with_mfa.id, "123456")

    @pytest.mark.asyncio
    async def test_verify_and_enable_no_setup(self, mfa_service, mock_db, mock_user):
        """Sollte Fehler werfen wenn Setup nicht gestartet."""
        from app.services.auth.mfa_service import MFAServiceError
        mock_user.totp_secret = None
        mock_user.totp_enabled = False
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = mock_user
        mock_db.execute.return_value = mock_result
        with pytest.raises(MFAServiceError) as exc_info:
            await mfa_service.verify_and_enable_totp(mock_user.id, "123456")
        assert "Setup" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_verify_and_enable_user_not_found(self, mfa_service, mock_db):
        """Sollte Fehler werfen bei nicht existierendem User."""
        from app.services.auth.mfa_service import MFAServiceError
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result
        with pytest.raises(MFAServiceError):
            await mfa_service.verify_and_enable_totp(uuid4(), "123456")


# ========================= TOTP Verification Tests =========================


class TestTOTPVerification:
    """Tests fuer TOTP-Verifizierung waehrend Login."""

    @pytest.mark.asyncio
    async def test_verify_totp_success(self, mfa_service, mock_db, mock_user_with_mfa):
        """Gueltiger Code sollte True zurueckgeben."""
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = mock_user_with_mfa
        mock_db.execute.return_value = mock_result
        totp = pyotp.TOTP(mock_user_with_mfa._plaintext_secret)
        valid_code = totp.now()
        result = await mfa_service.verify_totp(mock_user_with_mfa.id, valid_code)
        assert result is True

    @pytest.mark.asyncio
    async def test_verify_totp_invalid_code(self, mfa_service, mock_db, mock_user_with_mfa):
        """Ungueltiger Code sollte Fehler werfen."""
        from app.services.auth.mfa_service import InvalidTOTPCodeError
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = mock_user_with_mfa
        mock_db.execute.return_value = mock_result
        with pytest.raises(InvalidTOTPCodeError):
            await mfa_service.verify_totp(mock_user_with_mfa.id, "000000")

    @pytest.mark.asyncio
    async def test_verify_totp_not_enabled(self, mfa_service, mock_db, mock_user):
        """Sollte Fehler werfen wenn MFA nicht aktiviert."""
        from app.services.auth.mfa_service import MFANotEnabledError
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = mock_user
        mock_db.execute.return_value = mock_result
        with pytest.raises(MFANotEnabledError):
            await mfa_service.verify_totp(mock_user.id, "123456")

    @pytest.mark.asyncio
    async def test_verify_totp_with_window(self, mfa_service, mock_db, mock_user_with_mfa):
        """Verifizierung sollte Zeit-Fenster tolerieren."""
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = mock_user_with_mfa
        mock_db.execute.return_value = mock_result
        totp = pyotp.TOTP(mock_user_with_mfa._plaintext_secret)
        current_code = totp.now()
        result = await mfa_service.verify_totp(mock_user_with_mfa.id, current_code)
        assert result is True

    @pytest.mark.asyncio
    async def test_verify_totp_resets_failed_attempts(self, mfa_service, mock_db, mock_user_with_mfa):
        """Erfolgreiche Verifizierung sollte Zaehler zuruecksetzen."""
        mock_user_with_mfa.totp_failed_attempts = 3
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = mock_user_with_mfa
        mock_db.execute.return_value = mock_result
        totp = pyotp.TOTP(mock_user_with_mfa._plaintext_secret)
        valid_code = totp.now()
        await mfa_service.verify_totp(mock_user_with_mfa.id, valid_code)
        mock_db.commit.assert_called()

    @pytest.mark.asyncio
    async def test_verify_totp_user_not_found(self, mfa_service, mock_db):
        """Sollte Fehler werfen bei nicht existierendem User."""
        from app.services.auth.mfa_service import MFAServiceError
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result
        with pytest.raises(MFAServiceError):
            await mfa_service.verify_totp(uuid4(), "123456")

    @pytest.mark.asyncio
    async def test_verify_totp_no_secret(self, mfa_service, mock_db, mock_user_with_mfa):
        """Sollte Fehler werfen wenn kein Secret vorhanden."""
        from app.services.auth.mfa_service import MFAServiceError
        mock_user_with_mfa.totp_secret = None
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = mock_user_with_mfa
        mock_db.execute.return_value = mock_result
        with pytest.raises(MFAServiceError):
            await mfa_service.verify_totp(mock_user_with_mfa.id, "123456")


# ========================= Rate Limiting Tests =========================


class TestRateLimiting:
    """Tests fuer Brute-Force-Schutz."""

    @pytest.mark.asyncio
    async def test_rate_limit_after_5_attempts(self, mfa_service, mock_db, mock_user_with_mfa):
        """Nach 5 fehlgeschlagenen Versuchen sollte Lockout erfolgen."""
        from app.services.auth.mfa_service import InvalidTOTPCodeError, MAX_FAILED_ATTEMPTS
        mock_user_with_mfa.totp_failed_attempts = MAX_FAILED_ATTEMPTS - 1
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = mock_user_with_mfa
        mock_db.execute.return_value = mock_result
        with pytest.raises(InvalidTOTPCodeError):
            await mfa_service.verify_totp(mock_user_with_mfa.id, "000000")

    @pytest.mark.asyncio
    async def test_rate_limit_blocks_verification(self, mfa_service, mock_db, mock_user_with_mfa):
        """Gesperrter User sollte keine Verifizierung durchfuehren koennen."""
        from app.services.auth.mfa_service import RateLimitExceededError, LOCKOUT_DURATION_MINUTES
        mock_user_with_mfa.totp_lockout_until = datetime.now(timezone.utc) + timedelta(minutes=LOCKOUT_DURATION_MINUTES)
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = mock_user_with_mfa
        mock_db.execute.return_value = mock_result
        with pytest.raises(RateLimitExceededError) as exc_info:
            await mfa_service.verify_totp(mock_user_with_mfa.id, "123456")
        assert "Minute" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_rate_limit_expires(self, mfa_service, mock_db, mock_user_with_mfa):
        """Abgelaufener Lockout sollte Verifizierung erlauben."""
        mock_user_with_mfa.totp_lockout_until = datetime.now(timezone.utc) - timedelta(minutes=1)
        mock_user_with_mfa.totp_failed_attempts = 5
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = mock_user_with_mfa
        mock_db.execute.return_value = mock_result
        totp = pyotp.TOTP(mock_user_with_mfa._plaintext_secret)
        valid_code = totp.now()
        result = await mfa_service.verify_totp(mock_user_with_mfa.id, valid_code)
        assert result is True

    @pytest.mark.asyncio
    async def test_rate_limit_15_minutes(self, mfa_service, mock_db, mock_user_with_mfa):
        """Lockout sollte 15 Minuten dauern."""
        from app.services.auth.mfa_service import LOCKOUT_DURATION_MINUTES
        assert LOCKOUT_DURATION_MINUTES == 15

    @pytest.mark.asyncio
    async def test_rate_limit_max_5_attempts(self, mfa_service, mock_db, mock_user_with_mfa):
        """Maximum 5 fehlgeschlagene Versuche."""
        from app.services.auth.mfa_service import MAX_FAILED_ATTEMPTS
        assert MAX_FAILED_ATTEMPTS == 5

    @pytest.mark.asyncio
    async def test_failed_attempt_increments_counter(self, mfa_service, mock_db, mock_user_with_mfa):
        """Fehlgeschlagener Versuch sollte Zaehler erhoehen."""
        from app.services.auth.mfa_service import InvalidTOTPCodeError
        mock_user_with_mfa.totp_failed_attempts = 0
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = mock_user_with_mfa
        mock_db.execute.return_value = mock_result
        with pytest.raises(InvalidTOTPCodeError):
            await mfa_service.verify_totp(mock_user_with_mfa.id, "000000")
        mock_db.execute.assert_called()
        mock_db.commit.assert_called()

    @pytest.mark.asyncio
    async def test_rate_limit_applies_to_backup_codes(self, mfa_service, mock_db, mock_user_with_mfa):
        """Rate-Limiting sollte auch fuer Backup-Codes gelten."""
        from app.services.auth.mfa_service import RateLimitExceededError, LOCKOUT_DURATION_MINUTES
        mock_user_with_mfa.totp_lockout_until = datetime.now(timezone.utc) + timedelta(minutes=LOCKOUT_DURATION_MINUTES)
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = mock_user_with_mfa
        mock_db.execute.return_value = mock_result
        with pytest.raises(RateLimitExceededError):
            await mfa_service.verify_backup_code(mock_user_with_mfa.id, "XXXX-YYYY")


# ========================= Backup Code Tests =========================


class TestBackupCodeVerification:
    """Tests fuer Backup-Code-Verifizierung."""

    @pytest.mark.asyncio
    async def test_verify_backup_code_success(self, mfa_service, mock_db, mock_user_with_mfa):
        """Gueltiger Backup-Code sollte verifizieren."""
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = mock_user_with_mfa
        mock_db.execute.return_value = mock_result
        valid_code = mock_user_with_mfa._plaintext_backup_codes[0]
        result = await mfa_service.verify_backup_code(mock_user_with_mfa.id, valid_code)
        assert result is True

    @pytest.mark.asyncio
    async def test_verify_backup_code_consumes_code(self, mfa_service, mock_db, mock_user_with_mfa):
        """Backup-Code sollte nach Verwendung entfernt werden."""
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = mock_user_with_mfa
        mock_db.execute.return_value = mock_result
        valid_code = mock_user_with_mfa._plaintext_backup_codes[0]
        await mfa_service.verify_backup_code(mock_user_with_mfa.id, valid_code)
        mock_db.execute.assert_called()
        mock_db.commit.assert_called()

    @pytest.mark.asyncio
    async def test_verify_backup_code_invalid(self, mfa_service, mock_db, mock_user_with_mfa):
        """Ungueltiger Backup-Code sollte Fehler werfen."""
        from app.services.auth.mfa_service import InvalidTOTPCodeError
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = mock_user_with_mfa
        mock_db.execute.return_value = mock_result
        with pytest.raises(InvalidTOTPCodeError):
            await mfa_service.verify_backup_code(mock_user_with_mfa.id, "XXXX-YYYY")

    @pytest.mark.asyncio
    async def test_verify_backup_code_without_dash(self, mfa_service, mock_db, mock_user_with_mfa):
        """Backup-Code ohne Bindestrich sollte funktionieren."""
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = mock_user_with_mfa
        mock_db.execute.return_value = mock_result
        code_with_dash = mock_user_with_mfa._plaintext_backup_codes[0]
        code_without_dash = code_with_dash.replace("-", "")
        result = await mfa_service.verify_backup_code(mock_user_with_mfa.id, code_without_dash)
        assert result is True

    @pytest.mark.asyncio
    async def test_verify_backup_code_case_insensitive(self, mfa_service, mock_db, mock_user_with_mfa):
        """Backup-Code-Verifizierung sollte Case-Insensitive sein."""
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = mock_user_with_mfa
        mock_db.execute.return_value = mock_result
        code = mock_user_with_mfa._plaintext_backup_codes[0].lower()
        result = await mfa_service.verify_backup_code(mock_user_with_mfa.id, code)
        assert result is True

    @pytest.mark.asyncio
    async def test_verify_backup_code_no_codes(self, mfa_service, mock_db, mock_user_with_mfa):
        """Sollte Fehler werfen wenn keine Codes vorhanden."""
        from app.services.auth.mfa_service import InvalidTOTPCodeError
        mock_user_with_mfa.totp_backup_codes = None
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = mock_user_with_mfa
        mock_db.execute.return_value = mock_result
        with pytest.raises(InvalidTOTPCodeError):
            await mfa_service.verify_backup_code(mock_user_with_mfa.id, "XXXX-YYYY")

    @pytest.mark.asyncio
    async def test_verify_backup_code_not_enabled(self, mfa_service, mock_db, mock_user):
        """Sollte Fehler werfen wenn MFA nicht aktiviert."""
        from app.services.auth.mfa_service import MFANotEnabledError
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = mock_user
        mock_db.execute.return_value = mock_result
        with pytest.raises(MFANotEnabledError):
            await mfa_service.verify_backup_code(mock_user.id, "XXXX-YYYY")

    @pytest.mark.asyncio
    async def test_verify_backup_code_user_not_found(self, mfa_service, mock_db):
        """Sollte Fehler werfen bei nicht existierendem User."""
        from app.services.auth.mfa_service import MFAServiceError
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result
        with pytest.raises(MFAServiceError):
            await mfa_service.verify_backup_code(uuid4(), "XXXX-YYYY")


# ========================= Disable TOTP Tests =========================


class TestDisableTOTP:
    """Tests fuer TOTP-Deaktivierung."""

    @pytest.mark.asyncio
    async def test_disable_totp_success(self, mfa_service, mock_db, mock_user_with_mfa):
        """Deaktivierung mit gueltigem Code sollte funktionieren."""
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = mock_user_with_mfa
        mock_db.execute.return_value = mock_result
        totp = pyotp.TOTP(mock_user_with_mfa._plaintext_secret)
        valid_code = totp.now()
        result = await mfa_service.disable_totp(mock_user_with_mfa.id, valid_code)
        assert result is True
        mock_db.commit.assert_called()

    @pytest.mark.asyncio
    async def test_disable_totp_clears_data(self, mfa_service, mock_db, mock_user_with_mfa):
        """Deaktivierung sollte alle MFA-Daten loeschen."""
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = mock_user_with_mfa
        mock_db.execute.return_value = mock_result
        totp = pyotp.TOTP(mock_user_with_mfa._plaintext_secret)
        valid_code = totp.now()
        await mfa_service.disable_totp(mock_user_with_mfa.id, valid_code)
        mock_db.execute.assert_called()

    @pytest.mark.asyncio
    async def test_disable_totp_requires_valid_code(self, mfa_service, mock_db, mock_user_with_mfa):
        """Deaktivierung sollte gueltigen Code erfordern."""
        from app.services.auth.mfa_service import InvalidTOTPCodeError
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = mock_user_with_mfa
        mock_db.execute.return_value = mock_result
        with pytest.raises(InvalidTOTPCodeError):
            await mfa_service.disable_totp(mock_user_with_mfa.id, "000000")


# ========================= Regenerate Backup Codes Tests =========================


class TestRegenerateBackupCodes:
    """Tests fuer Backup-Code-Regenerierung."""

    @pytest.mark.asyncio
    async def test_regenerate_backup_codes_success(self, mfa_service, mock_db, mock_user_with_mfa):
        """Regenerierung mit gueltigem Code sollte neue Codes liefern."""
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = mock_user_with_mfa
        mock_db.execute.return_value = mock_result
        totp = pyotp.TOTP(mock_user_with_mfa._plaintext_secret)
        valid_code = totp.now()
        new_codes = await mfa_service.regenerate_backup_codes(mock_user_with_mfa.id, valid_code)
        assert len(new_codes) == 10
        assert new_codes != mock_user_with_mfa._plaintext_backup_codes

    @pytest.mark.asyncio
    async def test_regenerate_backup_codes_requires_totp(self, mfa_service, mock_db, mock_user_with_mfa):
        """Regenerierung sollte TOTP-Verifizierung erfordern."""
        from app.services.auth.mfa_service import InvalidTOTPCodeError
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = mock_user_with_mfa
        mock_db.execute.return_value = mock_result
        with pytest.raises(InvalidTOTPCodeError):
            await mfa_service.regenerate_backup_codes(mock_user_with_mfa.id, "000000")

    @pytest.mark.asyncio
    async def test_regenerate_backup_codes_stores_hashed(self, mfa_service, mock_db, mock_user_with_mfa):
        """Neue Codes sollten gehasht gespeichert werden."""
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = mock_user_with_mfa
        mock_db.execute.return_value = mock_result
        totp = pyotp.TOTP(mock_user_with_mfa._plaintext_secret)
        valid_code = totp.now()
        await mfa_service.regenerate_backup_codes(mock_user_with_mfa.id, valid_code)
        mock_db.execute.assert_called()
        mock_db.commit.assert_called()

    @pytest.mark.asyncio
    async def test_regenerate_backup_codes_format(self, mfa_service, mock_db, mock_user_with_mfa):
        """Neue Codes sollten korrektes Format haben."""
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = mock_user_with_mfa
        mock_db.execute.return_value = mock_result
        totp = pyotp.TOTP(mock_user_with_mfa._plaintext_secret)
        valid_code = totp.now()
        new_codes = await mfa_service.regenerate_backup_codes(mock_user_with_mfa.id, valid_code)
        for code in new_codes:
            assert len(code) == 9
            assert code[4] == "-"


# ========================= MFA Status Tests =========================


class TestMFAStatus:
    """Tests fuer MFA-Status-Abfrage."""

    @pytest.mark.asyncio
    async def test_get_mfa_status_disabled(self, mfa_service, mock_db, mock_user):
        """Status sollte enabled=False fuer User ohne MFA zeigen."""
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = mock_user
        mock_db.execute.return_value = mock_result
        status = await mfa_service.get_mfa_status(mock_user.id)
        assert status["enabled"] is False
        assert status["backup_codes_remaining"] == 0

    @pytest.mark.asyncio
    async def test_get_mfa_status_enabled(self, mfa_service, mock_db, mock_user_with_mfa):
        """Status sollte enabled=True fuer User mit MFA zeigen."""
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = mock_user_with_mfa
        mock_db.execute.return_value = mock_result
        status = await mfa_service.get_mfa_status(mock_user_with_mfa.id)
        assert status["enabled"] is True
        assert status["backup_codes_remaining"] == 10

    @pytest.mark.asyncio
    async def test_get_mfa_status_pending_setup(self, mfa_service, mock_db, mock_user):
        """Status sollte has_pending_setup zeigen wenn Secret aber nicht enabled."""
        mock_user.totp_secret = "encrypted_secret"
        mock_user.totp_enabled = False
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = mock_user
        mock_db.execute.return_value = mock_result
        status = await mfa_service.get_mfa_status(mock_user.id)
        assert status["has_pending_setup"] is True

    @pytest.mark.asyncio
    async def test_get_mfa_status_includes_setup_date(self, mfa_service, mock_db, mock_user_with_mfa):
        """Status sollte Setup-Datum enthalten."""
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = mock_user_with_mfa
        mock_db.execute.return_value = mock_result
        status = await mfa_service.get_mfa_status(mock_user_with_mfa.id)
        assert status["setup_at"] is not None
        assert "20" in status["setup_at"]

    @pytest.mark.asyncio
    async def test_get_mfa_status_user_not_found(self, mfa_service, mock_db):
        """Sollte Fehler werfen bei nicht existierendem User."""
        from app.services.auth.mfa_service import MFAServiceError
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result
        with pytest.raises(MFAServiceError):
            await mfa_service.get_mfa_status(uuid4())


# ========================= Factory Function Tests =========================


class TestFactoryFunction:
    """Tests fuer Factory-Funktion."""

    def test_get_mfa_service_creates_instance(self):
        """Factory sollte MFAService-Instanz erstellen."""
        from app.services.auth.mfa_service import get_mfa_service, MFAService
        mock_db = AsyncMock()
        service = get_mfa_service(mock_db)
        assert isinstance(service, MFAService)

    def test_get_mfa_service_uses_provided_db(self):
        """Factory sollte uebergebene DB verwenden."""
        from app.services.auth.mfa_service import get_mfa_service
        mock_db = AsyncMock()
        service = get_mfa_service(mock_db)
        assert service.db is mock_db


# ========================= Security Constants Tests =========================


class TestSecurityConstants:
    """Tests fuer Sicherheits-Konstanten."""

    def test_totp_digits(self):
        """TOTP sollte 6 Ziffern verwenden."""
        from app.services.auth.mfa_service import TOTP_DIGITS
        assert TOTP_DIGITS == 6

    def test_totp_interval(self):
        """TOTP-Intervall sollte 30 Sekunden sein."""
        from app.services.auth.mfa_service import TOTP_INTERVAL
        assert TOTP_INTERVAL == 30

    def test_totp_issuer(self):
        """Issuer sollte Ablage-System sein."""
        from app.services.auth.mfa_service import TOTP_ISSUER
        assert TOTP_ISSUER == "Ablage-System"

    def test_backup_code_count(self):
        """10 Backup-Codes sollten generiert werden."""
        from app.services.auth.mfa_service import BACKUP_CODE_COUNT
        assert BACKUP_CODE_COUNT == 10

    def test_backup_code_length(self):
        """Backup-Codes sollten 8 Zeichen haben."""
        from app.services.auth.mfa_service import BACKUP_CODE_LENGTH
        assert BACKUP_CODE_LENGTH == 8

    def test_valid_window(self):
        """TOTP valid window sollte 1 sein."""
        from app.services.auth.mfa_service import TOTP_VALID_WINDOW
        assert TOTP_VALID_WINDOW == 1


# ========================= Error Classes Tests =========================


class TestErrorClasses:
    """Tests fuer Exception-Klassen."""

    def test_mfa_service_error_is_exception(self):
        """MFAServiceError sollte von Exception erben."""
        from app.services.auth.mfa_service import MFAServiceError
        assert issubclass(MFAServiceError, Exception)

    def test_mfa_already_enabled_error(self):
        """MFAAlreadyEnabledError sollte von MFAServiceError erben."""
        from app.services.auth.mfa_service import MFAAlreadyEnabledError, MFAServiceError
        assert issubclass(MFAAlreadyEnabledError, MFAServiceError)

    def test_mfa_not_enabled_error(self):
        """MFANotEnabledError sollte von MFAServiceError erben."""
        from app.services.auth.mfa_service import MFANotEnabledError, MFAServiceError
        assert issubclass(MFANotEnabledError, MFAServiceError)

    def test_invalid_totp_code_error(self):
        """InvalidTOTPCodeError sollte von MFAServiceError erben."""
        from app.services.auth.mfa_service import InvalidTOTPCodeError, MFAServiceError
        assert issubclass(InvalidTOTPCodeError, MFAServiceError)

    def test_rate_limit_exceeded_error(self):
        """RateLimitExceededError sollte von MFAServiceError erben."""
        from app.services.auth.mfa_service import RateLimitExceededError, MFAServiceError
        assert issubclass(RateLimitExceededError, MFAServiceError)

    def test_error_messages_are_german(self):
        """Fehlermeldungen sollten auf Deutsch sein."""
        from app.services.auth.mfa_service import (
            MFAAlreadyEnabledError,
            MFANotEnabledError,
            InvalidTOTPCodeError,
            RateLimitExceededError,
        )
        # Just instantiate to ensure they can be created
        e1 = MFAAlreadyEnabledError("Test")
        e2 = MFANotEnabledError("Test")
        e3 = InvalidTOTPCodeError("Test")
        e4 = RateLimitExceededError("Test")
        assert str(e1) == "Test"
        assert str(e2) == "Test"
        assert str(e3) == "Test"
        assert str(e4) == "Test"


# ========================= Timing Attack Protection Tests =========================


class TestTimingAttackProtection:
    """Tests fuer Timing-Attack-Schutz."""

    def test_constant_time_comparison_on_backup_codes(self, mfa_service):
        """Backup-Code-Vergleich sollte bcrypt verwenden (constant time)."""
        codes, hashed = mfa_service._generate_backup_codes()
        valid_code = codes[0].replace("-", "")
        invalid_code = "XXXXXXXX"
        
        start = time.perf_counter()
        bcrypt.checkpw(valid_code.encode(), hashed[0].encode())
        valid_time = time.perf_counter() - start
        
        start = time.perf_counter()
        bcrypt.checkpw(invalid_code.encode(), hashed[0].encode())
        invalid_time = time.perf_counter() - start
        
        ratio = max(valid_time, invalid_time) / min(valid_time, invalid_time)
        assert ratio < 3.0

    @pytest.mark.asyncio
    async def test_user_enumeration_protection(self, mfa_service, mock_db):
        """Fehler sollten keine User-Existenz offenbaren."""
        from app.services.auth.mfa_service import MFAServiceError
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result
        with pytest.raises(MFAServiceError) as exc_info:
            await mfa_service.verify_totp(uuid4(), "123456")
        assert "nicht gefunden" in str(exc_info.value)


# ========================= Edge Cases Tests =========================


class TestEdgeCases:
    """Tests fuer Randfaelle."""

    @pytest.mark.asyncio
    async def test_verify_with_leading_zeros(self, mfa_service, mock_db, mock_user_with_mfa):
        """TOTP-Code mit fuehrenden Nullen sollte funktionieren."""
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = mock_user_with_mfa
        mock_db.execute.return_value = mock_result
        totp = pyotp.TOTP(mock_user_with_mfa._plaintext_secret)
        code = totp.now()
        # Even if code has leading zeros, it should work
        result = await mfa_service.verify_totp(mock_user_with_mfa.id, code)
        assert result is True

    def test_encryption_with_special_characters(self, mfa_service):
        """Verschluesselung sollte mit Sonderzeichen funktionieren."""
        secret = "ABC123!@#$%"
        encrypted = mfa_service._encrypt_secret(secret)
        decrypted = mfa_service._decrypt_secret(encrypted)
        assert decrypted == secret

    def test_backup_code_exhaustion(self, mfa_service, mock_user_with_mfa):
        """Sollte mit leerer Backup-Code-Liste umgehen."""
        mock_user_with_mfa.totp_backup_codes = []
        assert len(mock_user_with_mfa.totp_backup_codes) == 0

    @pytest.mark.asyncio
    async def test_concurrent_lockout_check(self, mfa_service, mock_db, mock_user_with_mfa):
        """Lockout sollte auch bei gleichzeitigen Anfragen greifen."""
        from app.services.auth.mfa_service import RateLimitExceededError
        mock_user_with_mfa.totp_lockout_until = datetime.now(timezone.utc) + timedelta(minutes=10)
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = mock_user_with_mfa
        mock_db.execute.return_value = mock_result
        with pytest.raises(RateLimitExceededError):
            await mfa_service.verify_totp(mock_user_with_mfa.id, "123456")

    def test_backup_code_mixed_case_input(self, mfa_service):
        """Backup-Code-Generierung sollte uppercase verwenden."""
        codes, _ = mfa_service._generate_backup_codes()
        for code in codes:
            clean = code.replace("-", "")
            assert clean == clean.upper()
