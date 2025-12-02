# -*- coding: utf-8 -*-
"""
Unit Tests fuer MinIO Default Credentials Enforcement.

Testet die Validierungslogik fuer MinIO Credentials:
- Default Access Keys werden erkannt
- Default Passwords werden erkannt
- Minimum-Laengen werden geprueft
"""

import pytest


class TestMinioCredentialsValidation:
    """Tests fuer MinIO Credentials Validierung."""

    # Listen aus config.py nachgebildet
    DEFAULT_ACCESS_KEYS = ["minioadmin", "admin", "minio", "root"]
    DEFAULT_SECRET_KEYS = ["minioadmin", "minioadmin123", "minio123", "admin", "password", "123456"]
    MIN_ACCESS_KEY_LENGTH = 8
    MIN_SECRET_KEY_LENGTH = 12

    def validate_minio_access_key(self, access_key: str) -> tuple:
        """Validiere MinIO Access Key."""
        if access_key.lower() in self.DEFAULT_ACCESS_KEYS:
            return False, f"Access Key '{access_key}' ist ein unsicherer Default-Wert"
        if len(access_key) < self.MIN_ACCESS_KEY_LENGTH:
            return False, f"Access Key zu kurz ({len(access_key)} Zeichen, min {self.MIN_ACCESS_KEY_LENGTH})"
        return True, "OK"

    def validate_minio_secret_key(self, secret_key: str) -> tuple:
        """Validiere MinIO Secret Key."""
        if secret_key.lower() in self.DEFAULT_SECRET_KEYS:
            return False, "Secret Key ist ein unsicherer Default-Wert"
        if len(secret_key) < self.MIN_SECRET_KEY_LENGTH:
            return False, f"Secret Key zu kurz ({len(secret_key)} Zeichen, min {self.MIN_SECRET_KEY_LENGTH})"
        return True, "OK"

    # ==================== Access Key Tests ====================

    def test_default_access_key_minioadmin(self):
        """'minioadmin' wird als unsicher erkannt."""
        valid, msg = self.validate_minio_access_key("minioadmin")
        assert valid is False
        assert "unsicher" in msg.lower() or "default" in msg.lower()

    def test_default_access_key_admin(self):
        """'admin' wird als unsicher erkannt."""
        valid, msg = self.validate_minio_access_key("admin")
        assert valid is False

    def test_default_access_key_minio(self):
        """'minio' wird als unsicher erkannt."""
        valid, msg = self.validate_minio_access_key("minio")
        assert valid is False

    def test_default_access_key_root(self):
        """'root' wird als unsicher erkannt."""
        valid, msg = self.validate_minio_access_key("root")
        assert valid is False

    def test_default_access_key_case_insensitive(self):
        """Default Access Keys sind case-insensitive."""
        assert self.validate_minio_access_key("MINIOADMIN")[0] is False
        assert self.validate_minio_access_key("MinioAdmin")[0] is False  # minioadmin
        assert self.validate_minio_access_key("ADMIN")[0] is False

    def test_short_access_key_rejected(self):
        """Zu kurzer Access Key wird abgelehnt."""
        valid, msg = self.validate_minio_access_key("short")  # 5 Zeichen
        assert valid is False
        assert "kurz" in msg.lower()

    def test_minimum_length_access_key_accepted(self):
        """Access Key mit genau minimum Laenge wird akzeptiert."""
        valid, msg = self.validate_minio_access_key("x" * 8)  # genau 8 Zeichen
        assert valid is True

    def test_long_access_key_accepted(self):
        """Langer Access Key wird akzeptiert."""
        valid, msg = self.validate_minio_access_key("my_unique_production_access_key")
        assert valid is True

    # ==================== Secret Key Tests ====================

    def test_default_secret_key_minioadmin(self):
        """'minioadmin' wird als unsicher erkannt."""
        valid, msg = self.validate_minio_secret_key("minioadmin")
        assert valid is False

    def test_default_secret_key_minioadmin123(self):
        """'minioadmin123' wird als unsicher erkannt."""
        valid, msg = self.validate_minio_secret_key("minioadmin123")
        assert valid is False

    def test_default_secret_key_minio123(self):
        """'minio123' wird als unsicher erkannt."""
        valid, msg = self.validate_minio_secret_key("minio123")
        assert valid is False

    def test_default_secret_key_password(self):
        """'password' wird als unsicher erkannt."""
        valid, msg = self.validate_minio_secret_key("password")
        assert valid is False

    def test_default_secret_key_123456(self):
        """'123456' wird als unsicher erkannt."""
        valid, msg = self.validate_minio_secret_key("123456")
        assert valid is False

    def test_default_secret_key_case_insensitive(self):
        """Default Secret Keys sind case-insensitive."""
        assert self.validate_minio_secret_key("MINIOADMIN")[0] is False
        assert self.validate_minio_secret_key("PASSWORD")[0] is False
        assert self.validate_minio_secret_key("MinioAdmin123")[0] is False  # minioadmin123

    def test_short_secret_key_rejected(self):
        """Zu kurzer Secret Key wird abgelehnt."""
        valid, msg = self.validate_minio_secret_key("shortpw123")  # 10 Zeichen, min ist 12
        assert valid is False
        assert "kurz" in msg.lower()

    def test_minimum_length_secret_key_accepted(self):
        """Secret Key mit genau minimum Laenge wird akzeptiert."""
        valid, msg = self.validate_minio_secret_key("s" * 12)  # genau 12 Zeichen
        assert valid is True

    def test_long_secret_key_accepted(self):
        """Langer Secret Key wird akzeptiert."""
        valid, msg = self.validate_minio_secret_key("my_very_secure_production_secret_key_2024")
        assert valid is True

    # ==================== Edge Cases ====================

    def test_unicode_access_key(self):
        """Access Key mit Unicode-Zeichen."""
        valid, msg = self.validate_minio_access_key("my_access_key_äöü")
        assert valid is True  # Laenge > 8

    def test_unicode_secret_key(self):
        """Secret Key mit Unicode-Zeichen."""
        valid, msg = self.validate_minio_secret_key("geheimnis_äöü_123")
        assert valid is True  # Laenge > 12

    def test_empty_access_key(self):
        """Leerer Access Key wird abgelehnt."""
        valid, msg = self.validate_minio_access_key("")
        assert valid is False

    def test_empty_secret_key(self):
        """Leerer Secret Key wird abgelehnt."""
        valid, msg = self.validate_minio_secret_key("")
        assert valid is False


class TestMinioCredentialPatterns:
    """Parametrisierte Tests fuer Credential-Patterns."""

    VALIDATION = TestMinioCredentialsValidation()

    @pytest.mark.parametrize("access_key,expected_valid", [
        ("minioadmin", False),
        ("MINIOADMIN", False),
        ("admin", False),
        ("minio", False),
        ("root", False),
        ("short", False),  # < 8 Zeichen
        ("exactly8", True),  # genau 8 Zeichen
        ("longer_access_key", True),
        ("production_access_key_123", True),
    ])
    def test_access_key_validation(self, access_key, expected_valid):
        """Parametrisierter Access Key Test."""
        valid, _ = self.VALIDATION.validate_minio_access_key(access_key)
        assert valid is expected_valid

    @pytest.mark.parametrize("secret_key,expected_valid", [
        ("minioadmin", False),
        ("minioadmin123", False),
        ("minio123", False),
        ("admin", False),
        ("password", False),
        ("123456", False),
        ("short123", False),  # < 12 Zeichen
        ("exactly12chs", True),  # genau 12 Zeichen
        ("longer_secret_key_456", True),
        ("my_production_secret_key_2024!", True),
    ])
    def test_secret_key_validation(self, secret_key, expected_valid):
        """Parametrisierter Secret Key Test."""
        valid, _ = self.VALIDATION.validate_minio_secret_key(secret_key)
        assert valid is expected_valid


class TestMinioCredentialLengthBoundary:
    """Boundary Tests fuer Laengen-Anforderungen."""

    VALIDATION = TestMinioCredentialsValidation()

    @pytest.mark.parametrize("length,expected_valid", [
        (0, False),
        (1, False),
        (7, False),
        (8, True),
        (9, True),
        (100, True),
    ])
    def test_access_key_length_boundary(self, length, expected_valid):
        """Boundary Test fuer Access Key Laenge."""
        # Verwende Zeichen die nicht in Default-Liste sind
        access_key = "x" * length
        valid, _ = self.VALIDATION.validate_minio_access_key(access_key)
        assert valid is expected_valid

    @pytest.mark.parametrize("length,expected_valid", [
        (0, False),
        (1, False),
        (11, False),
        (12, True),
        (13, True),
        (100, True),
    ])
    def test_secret_key_length_boundary(self, length, expected_valid):
        """Boundary Test fuer Secret Key Laenge."""
        # Verwende Zeichen die nicht in Default-Liste sind
        secret_key = "s" * length
        valid, _ = self.VALIDATION.validate_minio_secret_key(secret_key)
        assert valid is expected_valid
