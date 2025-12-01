# -*- coding: utf-8 -*-
"""
Tests fuer den Security Audit Service.

Testet:
- Einzelne Security Checks
- Audit Report Generierung
- Score Berechnung
- Finding Kategorisierung
"""

from unittest.mock import MagicMock, patch

import pytest

from app.services.security_audit_service import (
    AuditCategory,
    AuditFinding,
    AuditReport,
    AuditSeverity,
    SecurityAuditService,
    get_security_audit_service,
)


# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def service():
    """Erstellt eine frische Service-Instanz."""
    return SecurityAuditService()


@pytest.fixture
def mock_settings():
    """Mock Settings fuer Tests."""
    settings = MagicMock()
    settings.DEBUG = False
    settings.SECRET_KEY = "a" * 64  # 64 char secure key
    settings.DATABASE_URL = "postgresql://user:pass@localhost:5432/db?sslmode=require"
    settings.CORS_ORIGINS = ["https://example.com"]
    settings.CSRF_ENABLED = True
    settings.RATE_LIMIT_ENABLED = True
    settings.MINIO_ACCESS_KEY = "custom_access_key"
    settings.MINIO_SECRET_KEY = "custom_secret_key_12345"
    settings.REDIS_URL = "redis://:password@localhost:6379/0"
    settings.JWT_ALGORITHM = "HS256"
    settings.BCRYPT_ROUNDS = 12
    settings.ACCESS_TOKEN_EXPIRE_MINUTES = 15
    settings.REFRESH_TOKEN_EXPIRE_DAYS = 7
    settings.LOG_LEVEL = "INFO"
    settings.API_KEY_LENGTH = 32
    settings.API_KEY_PREFIX = "ablage_"
    settings.COOKIE_SECURE = True
    return settings


# =============================================================================
# AUDIT FINDING TESTS
# =============================================================================


class TestAuditFinding:
    """Tests fuer AuditFinding Klasse."""

    def test_to_dict(self):
        """to_dict sollte korrektes Dictionary zurueckgeben."""
        finding = AuditFinding(
            id="SEC-001",
            category=AuditCategory.AUTHENTICATION,
            severity=AuditSeverity.HIGH,
            title="Test Finding",
            description="Test Description",
            recommendation="Test Recommendation",
            affected_component="test.component",
            passed=True,
            details={"key": "value"},
        )

        result = finding.to_dict()

        assert result["id"] == "SEC-001"
        assert result["category"] == "authentication"
        assert result["severity"] == "high"
        assert result["passed"] is True


# =============================================================================
# SECURITY AUDIT SERVICE TESTS
# =============================================================================


class TestDebugModeCheck:
    """Tests fuer Debug-Mode Check."""

    def test_debug_mode_disabled(self, service):
        """Debug-Modus deaktiviert sollte bestehen."""
        settings = MagicMock()
        settings.DEBUG = False

        finding = service._check_debug_mode(settings)

        assert finding.passed is True
        assert finding.severity == AuditSeverity.CRITICAL

    def test_debug_mode_enabled(self, service):
        """Debug-Modus aktiviert sollte fehlschlagen."""
        settings = MagicMock()
        settings.DEBUG = True

        finding = service._check_debug_mode(settings)

        assert finding.passed is False


class TestSecretKeyCheck:
    """Tests fuer Secret Key Check."""

    def test_secure_secret_key(self, service):
        """Sicherer Secret Key sollte bestehen."""
        settings = MagicMock()
        # Zufaelliger Key mit Gross/Kleinschreibung und Zahlen
        settings.SECRET_KEY = "aB3cD4eF5gH6iJ7kL8mN9oP0qR1sT2uV3wX4yZ5aB6cD7eF8gH9"

        finding = service._check_secret_key(settings)

        assert finding.passed is True

    def test_default_secret_key(self, service):
        """Default Secret Key sollte fehlschlagen."""
        settings = MagicMock()
        settings.SECRET_KEY = "changeme"

        finding = service._check_secret_key(settings)

        assert finding.passed is False

    def test_short_secret_key(self, service):
        """Kurzer Secret Key sollte fehlschlagen."""
        settings = MagicMock()
        settings.SECRET_KEY = "short"

        finding = service._check_secret_key(settings)

        assert finding.passed is False


class TestCorsCheck:
    """Tests fuer CORS Check."""

    def test_specific_origins(self, service):
        """Spezifische Origins sollten bestehen."""
        settings = MagicMock()
        settings.CORS_ORIGINS = ["https://example.com"]

        finding = service._check_cors_config(settings)

        assert finding.passed is True

    def test_wildcard_origin(self, service):
        """Wildcard Origin sollte fehlschlagen."""
        settings = MagicMock()
        settings.CORS_ORIGINS = ["*"]

        finding = service._check_cors_config(settings)

        assert finding.passed is False


class TestCsrfCheck:
    """Tests fuer CSRF Check."""

    def test_csrf_enabled(self, service):
        """CSRF aktiviert sollte bestehen."""
        settings = MagicMock()
        settings.CSRF_ENABLED = True

        finding = service._check_csrf_enabled(settings)

        assert finding.passed is True

    def test_csrf_disabled(self, service):
        """CSRF deaktiviert sollte fehlschlagen."""
        settings = MagicMock()
        settings.CSRF_ENABLED = False

        finding = service._check_csrf_enabled(settings)

        assert finding.passed is False


class TestRateLimitingCheck:
    """Tests fuer Rate Limiting Check."""

    def test_rate_limiting_enabled(self, service):
        """Rate Limiting aktiviert sollte bestehen."""
        settings = MagicMock()
        settings.RATE_LIMIT_ENABLED = True

        finding = service._check_rate_limiting(settings)

        assert finding.passed is True

    def test_rate_limiting_disabled(self, service):
        """Rate Limiting deaktiviert sollte fehlschlagen."""
        settings = MagicMock()
        settings.RATE_LIMIT_ENABLED = False

        finding = service._check_rate_limiting(settings)

        assert finding.passed is False


class TestMinioCredentialsCheck:
    """Tests fuer MinIO Credentials Check."""

    def test_custom_credentials(self, service):
        """Benutzerdefinierte Credentials sollten bestehen."""
        settings = MagicMock()
        settings.MINIO_ACCESS_KEY = "custom_key"
        settings.MINIO_SECRET_KEY = "custom_secret_12345"

        finding = service._check_minio_credentials(settings)

        assert finding.passed is True

    def test_default_credentials(self, service):
        """Default Credentials sollten fehlschlagen."""
        settings = MagicMock()
        settings.MINIO_ACCESS_KEY = "minioadmin"
        settings.MINIO_SECRET_KEY = "minioadmin"

        finding = service._check_minio_credentials(settings)

        assert finding.passed is False


class TestDatabaseCheck:
    """Tests fuer Datenbank Check."""

    def test_database_with_ssl(self, service):
        """Datenbank mit SSL sollte bestehen."""
        settings = MagicMock()
        settings.DATABASE_URL = "postgresql://user:pass@host:5432/db?sslmode=require"

        finding = service._check_database_url(settings)

        assert finding.passed is True

    def test_database_localhost_no_ssl(self, service):
        """Localhost ohne SSL sollte bestehen."""
        settings = MagicMock()
        settings.DATABASE_URL = "postgresql://user:pass@localhost:5432/db"

        finding = service._check_database_url(settings)

        assert finding.passed is True


class TestJwtAlgorithmCheck:
    """Tests fuer JWT Algorithmus Check."""

    def test_hs256_algorithm(self, service):
        """HS256 sollte bestehen."""
        settings = MagicMock()
        settings.JWT_ALGORITHM = "HS256"

        finding = service._check_jwt_algorithm(settings)

        assert finding.passed is True

    def test_rs256_algorithm(self, service):
        """RS256 sollte bestehen."""
        settings = MagicMock()
        settings.JWT_ALGORITHM = "RS256"

        finding = service._check_jwt_algorithm(settings)

        assert finding.passed is True


class TestPasswordHashingCheck:
    """Tests fuer Password Hashing Check."""

    def test_sufficient_rounds(self, service):
        """Ausreichende Bcrypt Rounds sollten bestehen."""
        settings = MagicMock()
        settings.BCRYPT_ROUNDS = 12

        finding = service._check_password_hashing(settings)

        assert finding.passed is True

    def test_insufficient_rounds(self, service):
        """Zu wenige Rounds sollten fehlschlagen."""
        settings = MagicMock()
        settings.BCRYPT_ROUNDS = 4

        finding = service._check_password_hashing(settings)

        assert finding.passed is False


class TestSessionSecurityCheck:
    """Tests fuer Session Security Check."""

    def test_secure_token_expiry(self, service):
        """Sichere Token-Ablaufzeiten sollten bestehen."""
        settings = MagicMock()
        settings.ACCESS_TOKEN_EXPIRE_MINUTES = 15
        settings.REFRESH_TOKEN_EXPIRE_DAYS = 7

        finding = service._check_session_security(settings)

        assert finding.passed is True

    def test_long_access_token(self, service):
        """Zu langer Access Token sollte fehlschlagen."""
        settings = MagicMock()
        settings.ACCESS_TOKEN_EXPIRE_MINUTES = 60
        settings.REFRESH_TOKEN_EXPIRE_DAYS = 7

        finding = service._check_session_security(settings)

        assert finding.passed is False


# =============================================================================
# FULL AUDIT TESTS
# =============================================================================


class TestFullAudit:
    """Tests fuer vollstaendigen Audit."""

    def test_run_audit_returns_report(self, service, mock_settings):
        """run_audit sollte AuditReport zurueckgeben."""
        with patch("app.core.config.settings", mock_settings):
            with patch.object(service, "_checks", [service._check_debug_mode]):
                report = service.run_audit()

        assert isinstance(report, AuditReport)
        assert len(report.findings) == 1

    def test_calculate_summary(self, service):
        """_calculate_summary sollte korrektes Summary zurueckgeben."""
        findings = [
            AuditFinding(
                id="1", category=AuditCategory.AUTHENTICATION,
                severity=AuditSeverity.CRITICAL, title="T", description="D",
                recommendation="R", affected_component="C", passed=True,
            ),
            AuditFinding(
                id="2", category=AuditCategory.CONFIGURATION,
                severity=AuditSeverity.HIGH, title="T", description="D",
                recommendation="R", affected_component="C", passed=False,
            ),
        ]

        summary = service._calculate_summary(findings)

        assert summary["total"] == 2
        assert summary["passed"] == 1
        assert summary["failed"] == 1
        assert summary["critical_passed"] == 1
        assert summary["high_failed"] == 1

    def test_calculate_score(self, service):
        """_calculate_score sollte korrekten Score berechnen."""
        # Alle bestanden
        all_passed = [
            AuditFinding(
                id="1", category=AuditCategory.AUTHENTICATION,
                severity=AuditSeverity.CRITICAL, title="T", description="D",
                recommendation="R", affected_component="C", passed=True,
            ),
        ]

        score = service._calculate_score(all_passed)
        assert score == 100.0

        # Alle fehlgeschlagen
        all_failed = [
            AuditFinding(
                id="1", category=AuditCategory.AUTHENTICATION,
                severity=AuditSeverity.CRITICAL, title="T", description="D",
                recommendation="R", affected_component="C", passed=False,
            ),
        ]

        score = service._calculate_score(all_failed)
        assert score == 0.0


# =============================================================================
# SINGLETON TESTS
# =============================================================================


class TestSingleton:
    """Tests fuer Singleton-Verhalten."""

    def test_get_security_audit_service_returns_instance(self):
        """get_security_audit_service sollte Instanz zurueckgeben."""
        service1 = get_security_audit_service()
        service2 = get_security_audit_service()

        assert service1 is service2
        assert isinstance(service1, SecurityAuditService)
