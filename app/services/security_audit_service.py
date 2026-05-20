# -*- coding: utf-8 -*-
"""
Security Audit Service.

Prüft das System auf Sicherheitsprobleme und Fehlkonfigurationen:
- Hardcoded Credentials
- Unsichere Defaults
- Fehlende Authentifizierung
- Schwache Konfigurationen
- Production Readiness

Feinpoliert und durchdacht - Enterprise-grade Security Auditing.
"""

import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Callable, Dict, List, Optional, Union

import structlog

logger = structlog.get_logger(__name__)


# =============================================================================
# ENUMS AND DATA CLASSES
# =============================================================================


class AuditSeverity(str, Enum):
    """Schweregrad eines Audit-Findings."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class AuditCategory(str, Enum):
    """Kategorie eines Audit-Findings."""

    AUTHENTICATION = "authentication"
    AUTHORIZATION = "authorization"
    CONFIGURATION = "configuration"
    ENCRYPTION = "encryption"
    INPUT_VALIDATION = "input_validation"
    SECRETS = "secrets"
    RATE_LIMITING = "rate_limiting"
    LOGGING = "logging"
    HEADERS = "headers"
    CORS = "cors"


@dataclass
class AuditFinding:
    """Ein einzelnes Audit-Finding."""

    id: str
    category: AuditCategory
    severity: AuditSeverity
    title: str
    description: str
    recommendation: str
    affected_component: str
    passed: bool
    details: Dict[str, Union[str, int, float, bool, None]] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, object]:
        """Konvertiert zu Dictionary."""
        return {
            "id": self.id,
            "category": self.category.value,
            "severity": self.severity.value,
            "title": self.title,
            "description": self.description,
            "recommendation": self.recommendation,
            "affected_component": self.affected_component,
            "passed": self.passed,
            "details": self.details,
        }


@dataclass
class AuditReport:
    """Vollständiger Audit-Report."""

    timestamp: datetime
    findings: List[AuditFinding]
    summary: Dict[str, int]
    score: float
    passed: bool

    def to_dict(self) -> Dict[str, object]:
        """Konvertiert zu Dictionary."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "findings": [f.to_dict() for f in self.findings],
            "summary": self.summary,
            "score": round(self.score, 1),
            "passed": self.passed,
            "total_findings": len(self.findings),
            "critical_count": sum(1 for f in self.findings if f.severity == AuditSeverity.CRITICAL and not f.passed),
            "high_count": sum(1 for f in self.findings if f.severity == AuditSeverity.HIGH and not f.passed),
        }


# =============================================================================
# SECURITY AUDIT SERVICE
# =============================================================================


class SecurityAuditService:
    """
    Service für Security Audits.

    Führt automatisierte Sicherheitsprüfungen durch:
    - Konfigurationsprüfungen
    - Credential-Checks
    - Header-Validierung
    - Best-Practice-Compliance
    """

    def __init__(self) -> None:
        """Initialisiere Audit Service."""
        self._checks: List[Callable[..., AuditFinding]] = [
            self._check_debug_mode,
            self._check_secret_key,
            self._check_database_url,
            self._check_cors_config,
            self._check_csrf_enabled,
            self._check_rate_limiting,
            self._check_minio_credentials,
            self._check_redis_password,
            self._check_jwt_algorithm,
            self._check_password_hashing,
            self._check_session_security,
            self._check_logging_config,
            self._check_api_key_config,
            self._check_https_enforcement,
        ]

    def run_audit(self) -> AuditReport:
        """
        Führt vollständigen Security Audit durch.

        Returns:
            AuditReport mit allen Findings
        """
        from app.core.config import settings


        findings: List[AuditFinding] = []

        for check in self._checks:
            try:
                finding = check(settings)
                if finding:
                    findings.append(finding)
            except Exception as e:
                logger.error(
                    "security_check_failed",
                    check=check.__name__,
                    **safe_error_log(e),
                )

        # Summary berechnen
        summary = self._calculate_summary(findings)
        score = self._calculate_score(findings)
        passed = score >= 70.0 and not any(
            f.severity == AuditSeverity.CRITICAL and not f.passed for f in findings
        )

        report = AuditReport(
            timestamp=datetime.now(timezone.utc),
            findings=findings,
            summary=summary,
            score=score,
            passed=passed,
        )

        logger.info(
            "security_audit_completed",
            score=score,
            passed=passed,
            total_findings=len(findings),
            critical_issues=summary.get("critical_failed", 0),
        )

        return report

    def _calculate_summary(self, findings: List[AuditFinding]) -> Dict[str, int]:
        """Berechnet Summary der Findings."""
        summary = {
            "total": len(findings),
            "passed": sum(1 for f in findings if f.passed),
            "failed": sum(1 for f in findings if not f.passed),
        }

        for severity in AuditSeverity:
            summary[f"{severity.value}_total"] = sum(
                1 for f in findings if f.severity == severity
            )
            summary[f"{severity.value}_passed"] = sum(
                1 for f in findings if f.severity == severity and f.passed
            )
            summary[f"{severity.value}_failed"] = sum(
                1 for f in findings if f.severity == severity and not f.passed
            )

        return summary

    def _calculate_score(self, findings: List[AuditFinding]) -> float:
        """Berechnet Security Score (0-100)."""
        if not findings:
            return 100.0

        # Gewichtung nach Severity
        weights = {
            AuditSeverity.CRITICAL: 25,
            AuditSeverity.HIGH: 15,
            AuditSeverity.MEDIUM: 8,
            AuditSeverity.LOW: 3,
            AuditSeverity.INFO: 1,
        }

        total_weight = sum(weights[f.severity] for f in findings)
        passed_weight = sum(weights[f.severity] for f in findings if f.passed)

        return (passed_weight / total_weight) * 100 if total_weight > 0 else 100.0

    # =========================================================================
    # INDIVIDUAL CHECKS
    # =========================================================================

    def _check_debug_mode(self, settings: object) -> AuditFinding:
        """Prüft ob Debug-Modus deaktiviert ist."""
        debug_enabled = getattr(settings, "DEBUG", False)

        return AuditFinding(
            id="SEC-001",
            category=AuditCategory.CONFIGURATION,
            severity=AuditSeverity.CRITICAL,
            title="Debug-Modus Status",
            description="Debug-Modus sollte in Production deaktiviert sein um Informationslecks zu vermeiden.",
            recommendation="Setze DEBUG=false in den Umgebungsvariablen.",
            affected_component="app.core.config",
            passed=not debug_enabled,
            details={"debug_enabled": debug_enabled},
        )

    def _check_secret_key(self, settings: object) -> AuditFinding:
        """Prüft ob ein sicherer Secret Key verwendet wird."""
        secret_key = str(getattr(settings, "SECRET_KEY", ""))

        # Prüfungen
        is_default = secret_key in ["", "changeme", "secret", "dev-secret-key"]
        is_short = len(secret_key) < 32
        is_weak = bool(re.match(r"^[a-z]+$", secret_key.lower()))

        passed = not (is_default or is_short or is_weak)

        return AuditFinding(
            id="SEC-002",
            category=AuditCategory.SECRETS,
            severity=AuditSeverity.CRITICAL,
            title="Secret Key Sicherheit",
            description="Der Secret Key muss lang, zufällig und einzigartig sein.",
            recommendation="Generiere einen neuen Secret Key: openssl rand -hex 32",
            affected_component="app.core.config.SECRET_KEY",
            passed=passed,
            details={
                "is_default": is_default,
                "is_short": is_short,
                "is_weak": is_weak,
                "length": len(secret_key),
            },
        )

    def _check_database_url(self, settings: object) -> AuditFinding:
        """Prüft Datenbank-URL auf Sicherheitsprobleme."""
        db_url = str(getattr(settings, "DATABASE_URL", ""))

        has_password = ":" in db_url and "@" in db_url
        uses_localhost = "localhost" in db_url or "127.0.0.1" in db_url
        uses_ssl = "sslmode=" in db_url

        # In Production sollte SSL verwendet werden
        passed = uses_ssl or uses_localhost  # Localhost ist OK ohne SSL

        return AuditFinding(
            id="SEC-003",
            category=AuditCategory.ENCRYPTION,
            severity=AuditSeverity.HIGH,
            title="Datenbank-Verbindungssicherheit",
            description="Datenbankverbindungen sollten verschlüsselt sein (SSL/TLS).",
            recommendation="Aktiviere sslmode=require in der DATABASE_URL.",
            affected_component="app.core.config.DATABASE_URL",
            passed=passed,
            details={
                "has_password": has_password,
                "uses_localhost": uses_localhost,
                "uses_ssl": uses_ssl,
            },
        )

    def _check_cors_config(self, settings: object) -> AuditFinding:
        """Prüft CORS-Konfiguration."""
        cors_origins = getattr(settings, "CORS_ORIGINS", [])
        allow_all = "*" in cors_origins

        return AuditFinding(
            id="SEC-004",
            category=AuditCategory.CORS,
            severity=AuditSeverity.MEDIUM,
            title="CORS-Konfiguration",
            description="CORS sollte auf spezifische Origins beschraenkt sein.",
            recommendation="Entferne '*' und definiere explizite Origins.",
            affected_component="app.core.config.CORS_ORIGINS",
            passed=not allow_all,
            details={
                "allow_all_origins": allow_all,
                "origins_count": len(cors_origins),
            },
        )

    def _check_csrf_enabled(self, settings: object) -> AuditFinding:
        """Prüft ob CSRF-Schutz aktiviert ist."""
        csrf_enabled = getattr(settings, "CSRF_ENABLED", True)

        return AuditFinding(
            id="SEC-005",
            category=AuditCategory.AUTHENTICATION,
            severity=AuditSeverity.HIGH,
            title="CSRF-Schutz",
            description="CSRF-Schutz sollte für state-changing Requests aktiviert sein.",
            recommendation="Setze CSRF_ENABLED=true.",
            affected_component="app.middleware.csrf",
            passed=csrf_enabled,
            details={"csrf_enabled": csrf_enabled},
        )

    def _check_rate_limiting(self, settings: object) -> AuditFinding:
        """Prüft ob Rate Limiting aktiviert ist."""
        rate_limit_enabled = getattr(settings, "RATE_LIMIT_ENABLED", False)

        return AuditFinding(
            id="SEC-006",
            category=AuditCategory.RATE_LIMITING,
            severity=AuditSeverity.HIGH,
            title="Rate Limiting",
            description="Rate Limiting schuetzt vor Brute-Force und DoS-Angriffen.",
            recommendation="Setze RATE_LIMIT_ENABLED=true.",
            affected_component="app.middleware.rate_limit",
            passed=rate_limit_enabled,
            details={"rate_limit_enabled": rate_limit_enabled},
        )

    def _check_minio_credentials(self, settings: object) -> AuditFinding:
        """Prüft MinIO-Credentials."""
        access_key = str(getattr(settings, "MINIO_ACCESS_KEY", ""))
        secret_key = str(getattr(settings, "MINIO_SECRET_KEY", ""))

        is_default_access = access_key in ["minioadmin", "minio"]
        is_default_secret = secret_key in ["minioadmin", "minioadmin123", "minio123"]

        passed = not (is_default_access and is_default_secret)

        return AuditFinding(
            id="SEC-007",
            category=AuditCategory.SECRETS,
            severity=AuditSeverity.HIGH,
            title="MinIO-Credentials",
            description="MinIO sollte nicht mit Default-Credentials betrieben werden.",
            recommendation="Ändere MINIO_ACCESS_KEY und MINIO_SECRET_KEY.",
            affected_component="app.core.config.MINIO_*",
            passed=passed,
            details={
                "default_access_key": is_default_access,
                "default_secret_key": is_default_secret,
            },
        )

    def _check_redis_password(self, settings: object) -> AuditFinding:
        """Prüft Redis-Authentifizierung."""
        redis_url = str(getattr(settings, "REDIS_URL", ""))

        has_password = "@" in redis_url and ":" in redis_url.split("@")[0]
        uses_localhost = "localhost" in redis_url or "127.0.0.1" in redis_url

        # Localhost ohne Passwort ist OK für Development
        passed = has_password or uses_localhost

        return AuditFinding(
            id="SEC-008",
            category=AuditCategory.AUTHENTICATION,
            severity=AuditSeverity.MEDIUM,
            title="Redis-Authentifizierung",
            description="Redis sollte mit Passwort gesichert sein (ausser localhost).",
            recommendation="Setze ein Redis-Passwort in REDIS_URL.",
            affected_component="app.core.config.REDIS_URL",
            passed=passed,
            details={
                "has_password": has_password,
                "uses_localhost": uses_localhost,
            },
        )

    def _check_jwt_algorithm(self, settings: object) -> AuditFinding:
        """Prüft JWT-Algorithmus."""
        algorithm = getattr(settings, "JWT_ALGORITHM", "HS256")

        # HS256 ist OK, aber RS256/ES256 waeren besser
        is_secure = algorithm in ["HS256", "HS384", "HS512", "RS256", "RS384", "RS512", "ES256", "ES384", "ES512"]
        is_optimal = algorithm in ["RS256", "RS384", "RS512", "ES256", "ES384", "ES512"]

        return AuditFinding(
            id="SEC-009",
            category=AuditCategory.ENCRYPTION,
            severity=AuditSeverity.LOW,
            title="JWT-Algorithmus",
            description="JWT sollte einen sicheren Algorithmus verwenden.",
            recommendation="HS256 ist sicher, aber asymmetrische Algorithmen (RS256, ES256) sind empfohlen.",
            affected_component="app.core.config.JWT_ALGORITHM",
            passed=is_secure,
            details={
                "algorithm": algorithm,
                "is_secure": is_secure,
                "is_optimal": is_optimal,
            },
        )

    def _check_password_hashing(self, settings: object) -> AuditFinding:
        """Prüft Password-Hashing-Konfiguration."""
        # Bcrypt rounds
        bcrypt_rounds = getattr(settings, "BCRYPT_ROUNDS", 12)

        passed = bcrypt_rounds >= 10

        return AuditFinding(
            id="SEC-010",
            category=AuditCategory.ENCRYPTION,
            severity=AuditSeverity.MEDIUM,
            title="Password-Hashing",
            description="Bcrypt sollte mindestens 10 Rounds verwenden.",
            recommendation="Setze BCRYPT_ROUNDS auf mindestens 12.",
            affected_component="app.core.security",
            passed=passed,
            details={
                "bcrypt_rounds": bcrypt_rounds,
                "recommended_minimum": 10,
            },
        )

    def _check_session_security(self, settings: object) -> AuditFinding:
        """Prüft Session-Sicherheit."""
        access_token_expire = getattr(settings, "ACCESS_TOKEN_EXPIRE_MINUTES", 30)
        refresh_token_expire = getattr(settings, "REFRESH_TOKEN_EXPIRE_DAYS", 7)

        # Access Token sollte kurz sein (<= 30 min)
        access_ok = access_token_expire <= 30
        # Refresh Token sollte nicht zu lang sein (<= 30 Tage)
        refresh_ok = refresh_token_expire <= 30

        passed = access_ok and refresh_ok

        return AuditFinding(
            id="SEC-011",
            category=AuditCategory.AUTHENTICATION,
            severity=AuditSeverity.MEDIUM,
            title="Token-Lebensdauer",
            description="Token sollten eine angemessene Lebensdauer haben.",
            recommendation="Access Token max 30 min, Refresh Token max 30 Tage.",
            affected_component="app.core.config",
            passed=passed,
            details={
                "access_token_minutes": access_token_expire,
                "refresh_token_days": refresh_token_expire,
            },
        )

    def _check_logging_config(self, settings: object) -> AuditFinding:
        """Prüft Logging-Konfiguration."""
        log_level = getattr(settings, "LOG_LEVEL", "INFO")

        # DEBUG in Production ist ein Problem
        debug_logging = log_level.upper() == "DEBUG"
        debug_mode = getattr(settings, "DEBUG", False)

        passed = not (debug_logging and not debug_mode)

        return AuditFinding(
            id="SEC-012",
            category=AuditCategory.LOGGING,
            severity=AuditSeverity.LOW,
            title="Log-Level",
            description="DEBUG-Logging kann sensible Informationen exponieren.",
            recommendation="Setze LOG_LEVEL auf INFO oder höher in Production.",
            affected_component="app.core.logging_config",
            passed=passed,
            details={
                "log_level": log_level,
                "debug_mode": debug_mode,
            },
        )

    def _check_api_key_config(self, settings: object) -> AuditFinding:
        """Prüft API-Key-Konfiguration."""
        api_key_length = getattr(settings, "API_KEY_LENGTH", 32)
        api_key_prefix = getattr(settings, "API_KEY_PREFIX", "ablage_")

        passed = api_key_length >= 32 and len(api_key_prefix) > 0

        return AuditFinding(
            id="SEC-013",
            category=AuditCategory.AUTHENTICATION,
            severity=AuditSeverity.LOW,
            title="API-Key-Konfiguration",
            description="API-Keys sollten ausreichend lang und mit Prefix versehen sein.",
            recommendation="Mindestens 32 Zeichen für API-Keys.",
            affected_component="app.services.api_key_service",
            passed=passed,
            details={
                "api_key_length": api_key_length,
                "has_prefix": len(api_key_prefix) > 0,
            },
        )

    def _check_https_enforcement(self, settings: object) -> AuditFinding:
        """Prüft HTTPS-Enforcement."""
        debug = getattr(settings, "DEBUG", False)
        cookie_secure = getattr(settings, "COOKIE_SECURE", not debug)

        # In Production sollten Cookies secure sein
        passed = cookie_secure or debug

        return AuditFinding(
            id="SEC-014",
            category=AuditCategory.ENCRYPTION,
            severity=AuditSeverity.HIGH,
            title="HTTPS-Enforcement",
            description="Cookies sollten mit Secure-Flag gesetzt werden.",
            recommendation="Setze COOKIE_SECURE=true in Production.",
            affected_component="app.middleware",
            passed=passed,
            details={
                "cookie_secure": cookie_secure,
                "debug_mode": debug,
            },
        )


# =============================================================================
# SINGLETON ACCESS
# =============================================================================


_security_audit_service: Optional[SecurityAuditService] = None


def get_security_audit_service() -> SecurityAuditService:
    """Gibt SecurityAuditService-Instanz zurück."""
    global _security_audit_service
    if _security_audit_service is None:
        _security_audit_service = SecurityAuditService()
    return _security_audit_service
