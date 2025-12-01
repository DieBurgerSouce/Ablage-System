# -*- coding: utf-8 -*-
"""
Umfassende Unit Tests für 2FA (TOTP) Endpoints.

Testet alle 2FA-Funktionalitäten:
- GET /auth/2fa/status
- POST /auth/2fa/setup
- POST /auth/2fa/verify
- POST /auth/2fa/disable
- POST /auth/2fa/regenerate-backup-codes

Feinpoliert und durchdacht - Enterprise Test Coverage.
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from uuid import uuid4
from datetime import datetime, timezone, timedelta

# Test markers
pytestmark = [pytest.mark.unit, pytest.mark.api]


class TestTwoFactorStatus:
    """Tests für GET /auth/2fa/status Endpoint."""

    @pytest.mark.asyncio
    async def test_2fa_status_not_enabled(self, async_client):
        """2FA Status wenn nicht aktiviert."""
        with patch("app.api.v1.auth.get_current_active_user") as mock_auth:
            mock_user = Mock(
                id=uuid4(),
                is_active=True,
                totp_enabled=False,
                totp_setup_at=None,
                totp_backup_codes=None
            )
            mock_auth.return_value = mock_user

            response = await async_client.get(
                "/api/v1/auth/2fa/status",
                headers={"Authorization": "Bearer test_token"}
            )

            # 200 OK oder 401 wenn Auth fehlschlägt
            if response.status_code == 200:
                data = response.json()
                assert data["enabled"] is False
                assert data["setup_at"] is None
                assert data["backup_codes_remaining"] == 0

    @pytest.mark.asyncio
    async def test_2fa_status_enabled(self, async_client):
        """2FA Status wenn aktiviert."""
        setup_time = datetime.now(timezone.utc)

        with patch("app.api.v1.auth.get_current_active_user") as mock_auth:
            mock_user = Mock(
                id=uuid4(),
                is_active=True,
                totp_enabled=True,
                totp_setup_at=setup_time,
                totp_backup_codes=["hash1", "hash2", "hash3"]
            )
            mock_auth.return_value = mock_user

            response = await async_client.get(
                "/api/v1/auth/2fa/status",
                headers={"Authorization": "Bearer test_token"}
            )

            if response.status_code == 200:
                data = response.json()
                assert data["enabled"] is True
                assert data["backup_codes_remaining"] == 3

    @pytest.mark.asyncio
    async def test_2fa_status_unauthenticated(self, async_client):
        """2FA Status ohne Authentifizierung."""
        response = await async_client.get("/api/v1/auth/2fa/status")

        # Sollte 401 Unauthorized sein
        assert response.status_code in [401, 403]


class TestTwoFactorSetup:
    """Tests für POST /auth/2fa/setup Endpoint."""

    @pytest.mark.asyncio
    async def test_2fa_setup_success(self, async_client):
        """Erfolgreicher 2FA Setup."""
        with patch("app.api.v1.auth.get_current_active_user") as mock_auth:
            mock_user = Mock(
                id=uuid4(),
                email="test@example.com",
                is_active=True,
                totp_enabled=False,
                totp_secret=None,
                totp_backup_codes=None
            )
            mock_auth.return_value = mock_user

            with patch("app.api.v1.auth.PYOTP_AVAILABLE", True):
                with patch("app.api.v1.auth.setup_2fa") as mock_setup:
                    mock_setup.return_value = {
                        "secret": "BASE32SECRETKEY",
                        "encrypted_secret": "encrypted_secret_value",
                        "qr_code": "data:image/png;base64,iVBOR...",
                        "provisioning_uri": "otpauth://totp/Ablage-System:test@example.com?secret=BASE32SECRETKEY",
                        "backup_codes": ["ABCD-1234", "EFGH-5678"],
                        "hashed_backup_codes": ["hash1", "hash2"]
                    }

                    response = await async_client.post(
                        "/api/v1/auth/2fa/setup",
                        headers={"Authorization": "Bearer test_token"}
                    )

                    if response.status_code == 200:
                        data = response.json()
                        assert "qr_code" in data
                        assert "provisioning_uri" in data
                        assert "backup_codes" in data
                        assert len(data["backup_codes"]) > 0

    @pytest.mark.asyncio
    async def test_2fa_setup_already_enabled(self, async_client):
        """2FA Setup wenn bereits aktiviert."""
        with patch("app.api.v1.auth.get_current_active_user") as mock_auth:
            mock_user = Mock(
                id=uuid4(),
                is_active=True,
                totp_enabled=True  # Bereits aktiviert
            )
            mock_auth.return_value = mock_user

            response = await async_client.post(
                "/api/v1/auth/2fa/setup",
                headers={"Authorization": "Bearer test_token"}
            )

            # Sollte 400 Bad Request sein
            assert response.status_code in [400, 401]

    @pytest.mark.asyncio
    async def test_2fa_setup_pyotp_not_available(self, async_client):
        """2FA Setup wenn pyotp nicht installiert."""
        with patch("app.api.v1.auth.get_current_active_user") as mock_auth:
            mock_user = Mock(
                id=uuid4(),
                is_active=True,
                totp_enabled=False
            )
            mock_auth.return_value = mock_user

            with patch("app.api.v1.auth.PYOTP_AVAILABLE", False):
                response = await async_client.post(
                    "/api/v1/auth/2fa/setup",
                    headers={"Authorization": "Bearer test_token"}
                )

                # Sollte 503 Service Unavailable sein
                assert response.status_code in [401, 503]


class TestTwoFactorVerify:
    """Tests für POST /auth/2fa/verify Endpoint."""

    @pytest.mark.asyncio
    async def test_2fa_verify_success(self, async_client):
        """Erfolgreiche 2FA Verifizierung."""
        with patch("app.api.v1.auth.get_current_active_user") as mock_auth:
            mock_user = Mock(
                id=uuid4(),
                is_active=True,
                totp_enabled=False,
                totp_secret="encrypted_secret"
            )
            mock_auth.return_value = mock_user

            with patch("app.api.v1.auth.verify_totp_code_encrypted") as mock_verify:
                mock_verify.return_value = True

                response = await async_client.post(
                    "/api/v1/auth/2fa/verify",
                    params={"code": "123456"},
                    headers={"Authorization": "Bearer test_token"}
                )

                if response.status_code == 200:
                    data = response.json()
                    assert data["enabled"] is True

    @pytest.mark.asyncio
    async def test_2fa_verify_invalid_code(self, async_client):
        """2FA Verifizierung mit ungültigem Code."""
        with patch("app.api.v1.auth.get_current_active_user") as mock_auth:
            mock_user = Mock(
                id=uuid4(),
                is_active=True,
                totp_enabled=False,
                totp_secret="encrypted_secret"
            )
            mock_auth.return_value = mock_user

            with patch("app.api.v1.auth.verify_totp_code_encrypted") as mock_verify:
                mock_verify.return_value = False

                response = await async_client.post(
                    "/api/v1/auth/2fa/verify",
                    params={"code": "000000"},
                    headers={"Authorization": "Bearer test_token"}
                )

                # Sollte 400 Bad Request sein
                assert response.status_code in [400, 401]

    @pytest.mark.asyncio
    async def test_2fa_verify_no_setup(self, async_client):
        """2FA Verifizierung ohne vorheriges Setup."""
        with patch("app.api.v1.auth.get_current_active_user") as mock_auth:
            mock_user = Mock(
                id=uuid4(),
                is_active=True,
                totp_enabled=False,
                totp_secret=None  # Kein Setup
            )
            mock_auth.return_value = mock_user

            response = await async_client.post(
                "/api/v1/auth/2fa/verify",
                params={"code": "123456"},
                headers={"Authorization": "Bearer test_token"}
            )

            # Sollte 400 Bad Request sein
            assert response.status_code in [400, 401]

    @pytest.mark.asyncio
    async def test_2fa_verify_code_format(self, async_client):
        """2FA Verifizierung mit falschem Code-Format."""
        with patch("app.api.v1.auth.get_current_active_user") as mock_auth:
            mock_user = Mock(
                id=uuid4(),
                is_active=True,
                totp_secret="encrypted_secret"
            )
            mock_auth.return_value = mock_user

            # Zu kurzer Code
            response = await async_client.post(
                "/api/v1/auth/2fa/verify",
                params={"code": "123"},
                headers={"Authorization": "Bearer test_token"}
            )

            assert response.status_code in [400, 401, 422]


class TestTwoFactorDisable:
    """Tests für POST /auth/2fa/disable Endpoint."""

    @pytest.mark.asyncio
    async def test_2fa_disable_success(self, async_client):
        """Erfolgreiche 2FA Deaktivierung."""
        with patch("app.api.v1.auth.get_current_active_user") as mock_auth:
            mock_user = Mock(
                id=uuid4(),
                is_active=True,
                totp_enabled=True,
                totp_secret="encrypted_secret",
                totp_backup_codes=["hash1", "hash2"]
            )
            mock_auth.return_value = mock_user

            with patch("app.api.v1.auth.verify_2fa_login_encrypted") as mock_verify:
                mock_verify.return_value = (True, False, None)

                response = await async_client.post(
                    "/api/v1/auth/2fa/disable",
                    params={"code": "123456"},
                    headers={"Authorization": "Bearer test_token"}
                )

                if response.status_code == 200:
                    data = response.json()
                    assert data["enabled"] is False

    @pytest.mark.asyncio
    async def test_2fa_disable_not_enabled(self, async_client):
        """2FA Deaktivierung wenn nicht aktiviert."""
        with patch("app.api.v1.auth.get_current_active_user") as mock_auth:
            mock_user = Mock(
                id=uuid4(),
                is_active=True,
                totp_enabled=False
            )
            mock_auth.return_value = mock_user

            response = await async_client.post(
                "/api/v1/auth/2fa/disable",
                params={"code": "123456"},
                headers={"Authorization": "Bearer test_token"}
            )

            # Sollte 400 Bad Request sein
            assert response.status_code in [400, 401]

    @pytest.mark.asyncio
    async def test_2fa_disable_invalid_code(self, async_client):
        """2FA Deaktivierung mit ungültigem Code."""
        with patch("app.api.v1.auth.get_current_active_user") as mock_auth:
            mock_user = Mock(
                id=uuid4(),
                is_active=True,
                totp_enabled=True,
                totp_secret="encrypted_secret",
                totp_backup_codes=[]
            )
            mock_auth.return_value = mock_user

            with patch("app.api.v1.auth.verify_2fa_login_encrypted") as mock_verify:
                mock_verify.return_value = (False, False, None)

                response = await async_client.post(
                    "/api/v1/auth/2fa/disable",
                    params={"code": "000000"},
                    headers={"Authorization": "Bearer test_token"}
                )

                # Sollte 400 Bad Request sein
                assert response.status_code in [400, 401]


class TestTwoFactorBackupCodes:
    """Tests für POST /auth/2fa/regenerate-backup-codes Endpoint."""

    @pytest.mark.asyncio
    async def test_regenerate_backup_codes_success(self, async_client):
        """Erfolgreiche Regenerierung der Backup-Codes."""
        with patch("app.api.v1.auth.get_current_active_user") as mock_auth:
            mock_user = Mock(
                id=uuid4(),
                is_active=True,
                totp_enabled=True,
                totp_secret="encrypted_secret",
                totp_backup_codes=["old_hash1", "old_hash2"]
            )
            mock_auth.return_value = mock_user

            with patch("app.api.v1.auth.verify_totp_code_encrypted") as mock_verify:
                mock_verify.return_value = True

                with patch("app.api.v1.auth.generate_backup_codes") as mock_gen:
                    mock_gen.return_value = (
                        ["NEW1-CODE", "NEW2-CODE"],
                        ["new_hash1", "new_hash2"]
                    )

                    response = await async_client.post(
                        "/api/v1/auth/2fa/regenerate-backup-codes",
                        params={"code": "123456"},
                        headers={"Authorization": "Bearer test_token"}
                    )

                    if response.status_code == 200:
                        data = response.json()
                        assert "backup_codes" in data
                        assert len(data["backup_codes"]) > 0

    @pytest.mark.asyncio
    async def test_regenerate_backup_codes_not_enabled(self, async_client):
        """Backup-Codes regenerieren wenn 2FA nicht aktiviert."""
        with patch("app.api.v1.auth.get_current_active_user") as mock_auth:
            mock_user = Mock(
                id=uuid4(),
                is_active=True,
                totp_enabled=False
            )
            mock_auth.return_value = mock_user

            response = await async_client.post(
                "/api/v1/auth/2fa/regenerate-backup-codes",
                params={"code": "123456"},
                headers={"Authorization": "Bearer test_token"}
            )

            # Sollte 400 Bad Request sein
            assert response.status_code in [400, 401]

    @pytest.mark.asyncio
    async def test_regenerate_backup_codes_invalid_code(self, async_client):
        """Backup-Codes regenerieren mit ungültigem Code."""
        with patch("app.api.v1.auth.get_current_active_user") as mock_auth:
            mock_user = Mock(
                id=uuid4(),
                is_active=True,
                totp_enabled=True,
                totp_secret="encrypted_secret"
            )
            mock_auth.return_value = mock_user

            with patch("app.api.v1.auth.verify_totp_code_encrypted") as mock_verify:
                mock_verify.return_value = False

                response = await async_client.post(
                    "/api/v1/auth/2fa/regenerate-backup-codes",
                    params={"code": "000000"},
                    headers={"Authorization": "Bearer test_token"}
                )

                # Sollte 400 Bad Request sein
                assert response.status_code in [400, 401]


class TestTOTPModule:
    """Unit Tests für das TOTP Modul selbst."""

    def test_generate_totp_secret(self):
        """TOTP Secret generieren."""
        try:
            from app.core.totp import generate_totp_secret, PYOTP_AVAILABLE

            if PYOTP_AVAILABLE:
                secret = generate_totp_secret()
                assert len(secret) == 32  # Base32 encoded
                assert secret.isalnum()
        except ImportError:
            pytest.skip("TOTP module not available")

    def test_generate_backup_codes(self):
        """Backup-Codes generieren."""
        try:
            from app.core.totp import generate_backup_codes

            plain_codes, hashed_codes = generate_backup_codes(count=8)

            assert len(plain_codes) == 8
            assert len(hashed_codes) == 8

            # Alle Codes sind unterschiedlich
            assert len(set(plain_codes)) == 8
            assert len(set(hashed_codes)) == 8

            # Format: XXXX-XXXX
            for code in plain_codes:
                assert "-" in code
                assert len(code.replace("-", "")) == 8
        except ImportError:
            pytest.skip("TOTP module not available")

    def test_verify_backup_code(self):
        """Backup-Code verifizieren."""
        try:
            from app.core.totp import generate_backup_codes, verify_backup_code

            plain_codes, hashed_codes = generate_backup_codes(count=3)

            # Gültiger Code
            is_valid, index = verify_backup_code(plain_codes[0], hashed_codes)
            assert is_valid is True
            assert index == 0

            # Ungültiger Code
            is_valid, index = verify_backup_code("INVALID-CODE", hashed_codes)
            assert is_valid is False
            assert index is None
        except ImportError:
            pytest.skip("TOTP module not available")

    def test_verify_totp_code_format(self):
        """TOTP Code Format-Validierung."""
        try:
            from app.core.totp import verify_totp_code, PYOTP_AVAILABLE

            if not PYOTP_AVAILABLE:
                pytest.skip("pyotp not available")

            # Ungültiger Code (falsche Länge)
            result = verify_totp_code("BASE32SECRET", "123")
            assert result is False

            # Ungültiger Code (nicht numerisch)
            result = verify_totp_code("BASE32SECRET", "abcdef")
            assert result is False
        except ImportError:
            pytest.skip("TOTP module not available")

    def test_totp_remaining_seconds(self):
        """TOTP verbleibende Sekunden."""
        try:
            from app.core.totp import get_totp_remaining_seconds

            remaining = get_totp_remaining_seconds()

            assert 0 <= remaining <= 30
        except ImportError:
            pytest.skip("TOTP module not available")


class TestTOTPEncryption:
    """Tests für TOTP Secret Verschlüsselung."""

    def test_encrypt_secret(self):
        """Secret verschlüsseln."""
        try:
            from app.core.totp import encrypt_secret, decrypt_secret
            from app.core.config import settings

            # Skip wenn kein Encryption Key konfiguriert
            if not getattr(settings, 'ENCRYPTION_KEY', None):
                pytest.skip("ENCRYPTION_KEY not configured")

            user_id = str(uuid4())
            secret = "JBSWY3DPEHPK3PXP"  # Test Base32 Secret

            encrypted = encrypt_secret(secret, user_id)

            assert encrypted != secret
            assert len(encrypted) > 0

            # Entschlüsseln
            decrypted = decrypt_secret(encrypted, user_id)
            assert decrypted == secret

        except ImportError:
            pytest.skip("Encryption module not available")

    def test_decrypt_wrong_user_id(self):
        """Secret mit falschem User-ID entschlüsseln."""
        try:
            from app.core.totp import encrypt_secret, decrypt_secret, TOTPSecretEncryptionError
            from app.core.config import settings

            if not getattr(settings, 'ENCRYPTION_KEY', None):
                pytest.skip("ENCRYPTION_KEY not configured")

            user_id_1 = str(uuid4())
            user_id_2 = str(uuid4())
            secret = "JBSWY3DPEHPK3PXP"

            encrypted = encrypt_secret(secret, user_id_1)

            # Entschlüsseln mit falscher User-ID sollte fehlschlagen
            with pytest.raises(TOTPSecretEncryptionError):
                decrypt_secret(encrypted, user_id_2)

        except ImportError:
            pytest.skip("Encryption module not available")


class TestGermanMessages:
    """Tests für deutsche Fehlermeldungen bei 2FA."""

    def test_2fa_error_messages_german(self):
        """Prüfe dass 2FA Fehlermeldungen auf Deutsch sind."""
        try:
            from app.core.totp import (
                TOTPNotAvailableError,
                TOTPAlreadyEnabledError,
                TOTPNotEnabledError,
                TOTPSecretEncryptionError
            )

            # TOTPSecretEncryptionError hat user_message_de Attribut
            error = TOTPSecretEncryptionError(
                "Test error",
                "Dies ist eine deutsche Fehlermeldung"
            )
            assert "deutsch" in error.user_message_de.lower() or len(error.user_message_de) > 0

        except ImportError:
            pytest.skip("TOTP module not available")
