# -*- coding: utf-8 -*-
"""Tests: bcrypt-72-Byte-Limit fuer Passwoerter (kein Truncating).

bcrypt >= 4.1 wirft ValueError fuer Passwoerter > 72 Bytes - sowohl in
hashpw (Registrierung/Passwort-Aenderung) als auch in checkpw (Login).
Ohne Validierung fuehrte das zu HTTP 500. Entscheidung 2026-06-11:
sauber ablehnen (422 via Schema-Validator), NIEMALS truncaten.
"""

import pytest
from pydantic import ValidationError

from app.core.security_auth import get_password_hash, verify_password
from app.db.schemas import (
    BCRYPT_MAX_PASSWORD_BYTES,
    PasswordResetConfirm,
    UserAdminCreate,
    UserChangePassword,
    UserCreate,
    validate_password_byte_length,
)

PW_72_BYTES = "a" * 72
PW_73_BYTES = "a" * 73
# 40 Umlaute = 80 Bytes UTF-8, aber nur 40 Zeichen -> max_length greift nicht
PW_UMLAUT_80_BYTES = "ä" * 40


class TestValidatePasswordByteLength:
    """Direkte Tests des Validators."""

    def test_72_bytes_ok(self) -> None:
        assert validate_password_byte_length(PW_72_BYTES) == PW_72_BYTES

    def test_73_bytes_abgelehnt(self) -> None:
        with pytest.raises(ValueError, match="72 Bytes"):
            validate_password_byte_length(PW_73_BYTES)

    def test_umlaute_zaehlen_als_bytes(self) -> None:
        assert len(PW_UMLAUT_80_BYTES) == 40  # Zeichen
        assert len(PW_UMLAUT_80_BYTES.encode("utf-8")) == 80  # Bytes
        with pytest.raises(ValueError, match="72 Bytes"):
            validate_password_byte_length(PW_UMLAUT_80_BYTES)

    def test_konstante_ist_72(self) -> None:
        assert BCRYPT_MAX_PASSWORD_BYTES == 72


class TestSchemaValidierung:
    """422-Pfad: Schemas lehnen ueberlange Passwoerter mit deutscher Meldung ab."""

    def test_user_create_73_bytes_abgelehnt(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            UserCreate(
                email="test@example.com",
                username="testuser",
                password=PW_73_BYTES,
            )
        assert "72 Bytes" in str(exc_info.value)

    def test_user_create_72_bytes_ok(self) -> None:
        user = UserCreate(
            email="test@example.com",
            username="testuser",
            password=PW_72_BYTES,
        )
        assert user.password == PW_72_BYTES

    def test_user_create_umlaut_passwort_abgelehnt(self) -> None:
        """40 Zeichen, aber 80 Bytes -> Byte-Check muss greifen."""
        with pytest.raises(ValidationError) as exc_info:
            UserCreate(
                email="test@example.com",
                username="testuser",
                password=PW_UMLAUT_80_BYTES,
            )
        assert "72 Bytes" in str(exc_info.value)

    def test_change_password_73_bytes_abgelehnt(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            UserChangePassword(
                current_password="altes-passwort",
                new_password=PW_73_BYTES,
            )
        assert "72 Bytes" in str(exc_info.value)

    def test_password_reset_confirm_ueberlang_abgelehnt(self) -> None:
        # Erfuellt alle Staerke-Regeln, ist aber > 72 Bytes
        strong_but_long = "Aa1!" + "ä" * 40
        with pytest.raises(ValidationError) as exc_info:
            PasswordResetConfirm(token="t" * 32, new_password=strong_but_long)
        assert "72 Bytes" in str(exc_info.value)

    def test_admin_create_73_bytes_abgelehnt(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            UserAdminCreate(
                email="admin@example.com",
                username="adminuser",
                password=PW_73_BYTES,
            )
        assert "72 Bytes" in str(exc_info.value)


class TestSecurityAuthGuards:
    """Hashing-/Login-Pfad: klare Fehler statt bcrypt-500."""

    def test_get_password_hash_72_bytes_ok(self) -> None:
        hashed = get_password_hash(PW_72_BYTES)
        assert hashed.startswith("$2")
        assert verify_password(PW_72_BYTES, hashed) is True

    def test_get_password_hash_73_bytes_deutsche_meldung(self) -> None:
        with pytest.raises(ValueError, match="72 Bytes"):
            get_password_hash(PW_73_BYTES)

    def test_get_password_hash_kein_truncating(self) -> None:
        """73-Byte-Passwort darf NICHT als 72-Byte-Hash durchgehen."""
        with pytest.raises(ValueError):
            get_password_hash(PW_73_BYTES)
        # Gegenprobe: das 72-Byte-Praefix ist ein anderes Passwort
        hashed = get_password_hash(PW_72_BYTES)
        assert verify_password(PW_73_BYTES, hashed) is False

    def test_verify_password_ueberlang_false_statt_valueerror(self) -> None:
        """Login-Pfad: bcrypt.checkpw wuerde ValueError werfen -> False."""
        hashed = get_password_hash("normales-Passwort1!")
        assert verify_password(PW_73_BYTES, hashed) is False
        assert verify_password(PW_UMLAUT_80_BYTES, hashed) is False
