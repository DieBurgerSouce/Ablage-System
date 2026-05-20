# -*- coding: utf-8 -*-
"""
Tests fuer den Production Readiness Service.

Testet:
- Einzelne Readiness Checks
- Report Generierung
- Score Berechnung
- Status-Bestimmung
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.production_readiness_service import (
    CheckCategory,
    ProductionReadinessService,
    ReadinessCheck,
    ReadinessReport,
    ReadinessStatus,
    get_production_readiness_service,
)


# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def service():
    """Erstellt eine frische Service-Instanz."""
    return ProductionReadinessService()


@pytest.fixture
def mock_security_audit_report():
    """Mock Security Audit Report."""
    mock_report = MagicMock()
    mock_report.score = 85.0
    mock_report.findings = []
    return mock_report


@pytest.fixture
def mock_profiling_summary():
    """Mock Profiling Summary."""
    return {
        "p99_latency_ms": 500,
        "avg_latency_ms": 100,
        "error_rate_percent": 0.5,
        "total_requests": 1000,
    }


# =============================================================================
# READINESS CHECK DATA CLASS TESTS
# =============================================================================


class TestReadinessCheck:
    """Tests fuer ReadinessCheck Klasse."""

    def test_to_dict(self):
        """to_dict sollte korrektes Dictionary zurueckgeben."""
        check = ReadinessCheck(
            name="Test Check",
            category=CheckCategory.SECURITY,
            status=ReadinessStatus.READY,
            message="Alles in Ordnung",
            details={"key": "value"},
            recommendation="Keine Aenderung noetig",
        )

        result = check.to_dict()

        assert result["name"] == "Test Check"
        assert result["category"] == "security"
        assert result["status"] == "ready"
        assert result["message"] == "Alles in Ordnung"
        assert result["details"] == {"key": "value"}
        assert result["recommendation"] == "Keine Aenderung noetig"

    def test_to_dict_without_recommendation(self):
        """to_dict sollte ohne Recommendation funktionieren."""
        check = ReadinessCheck(
            name="Test Check",
            category=CheckCategory.HEALTH,
            status=ReadinessStatus.WARNINGS,
            message="Warnung vorhanden",
        )

        result = check.to_dict()

        assert result["recommendation"] is None


class TestReadinessReport:
    """Tests fuer ReadinessReport Klasse."""

    def test_to_dict(self):
        """to_dict sollte korrektes Dictionary zurueckgeben."""
        checks = [
            ReadinessCheck(
                name="Check 1",
                category=CheckCategory.SECURITY,
                status=ReadinessStatus.READY,
                message="OK",
            ),
            ReadinessCheck(
                name="Check 2",
                category=CheckCategory.HEALTH,
                status=ReadinessStatus.NOT_READY,
                message="Fehler",
            ),
        ]

        report = ReadinessReport(
            timestamp=datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
            overall_status=ReadinessStatus.NOT_READY,
            overall_score=50.0,
            checks=checks,
            summary={"total": 2, "ready": 1, "not_ready": 1},
        )

        result = report.to_dict()

        assert result["timestamp"] == "2025-01-01T12:00:00+00:00"
        assert result["overall_status"] == "not_ready"
        assert result["overall_score"] == 50.0
        assert result["total_checks"] == 2
        assert result["passed_checks"] == 1
        assert result["failed_checks"] == 1


# =============================================================================
# SECURITY CHECKS TESTS
# =============================================================================


class TestSecurityChecks:
    """Tests fuer Security Checks."""

    @pytest.mark.asyncio
    async def test_security_checks_with_high_score(self, service, mock_security_audit_report):
        """Security Check mit hohem Score sollte READY sein."""
        mock_security_audit_report.score = 95.0

        with patch(
            "app.services.security_audit_service.get_security_audit_service"
        ) as mock_get:
            mock_audit_service = MagicMock()
            mock_audit_service.run_audit.return_value = mock_security_audit_report
            mock_get.return_value = mock_audit_service

            checks = await service._run_security_checks()

        # Finde Security Score Check
        score_check = next(
            (c for c in checks if c.name == "Security Score"), None
        )
        assert score_check is not None
        assert score_check.status == ReadinessStatus.READY

    @pytest.mark.asyncio
    async def test_security_checks_with_medium_score(self, service, mock_security_audit_report):
        """Security Check mit mittlerem Score sollte WARNINGS sein."""
        mock_security_audit_report.score = 75.0

        with patch(
            "app.services.security_audit_service.get_security_audit_service"
        ) as mock_get:
            mock_audit_service = MagicMock()
            mock_audit_service.run_audit.return_value = mock_security_audit_report
            mock_get.return_value = mock_audit_service

            checks = await service._run_security_checks()

        score_check = next(
            (c for c in checks if c.name == "Security Score"), None
        )
        assert score_check is not None
        assert score_check.status == ReadinessStatus.WARNINGS

    @pytest.mark.asyncio
    async def test_security_checks_with_low_score(self, service, mock_security_audit_report):
        """Security Check mit niedrigem Score sollte NOT_READY sein."""
        mock_security_audit_report.score = 50.0

        with patch(
            "app.services.security_audit_service.get_security_audit_service"
        ) as mock_get:
            mock_audit_service = MagicMock()
            mock_audit_service.run_audit.return_value = mock_security_audit_report
            mock_get.return_value = mock_audit_service

            checks = await service._run_security_checks()

        score_check = next(
            (c for c in checks if c.name == "Security Score"), None
        )
        assert score_check is not None
        assert score_check.status == ReadinessStatus.NOT_READY

    @pytest.mark.asyncio
    async def test_security_checks_with_critical_issues(self, service):
        """Security Check mit kritischen Issues sollte CRITICAL sein."""
        mock_report = MagicMock()
        mock_report.score = 40.0

        # Mock Finding mit kritischem Issue
        mock_finding = MagicMock()
        mock_finding.severity = MagicMock()
        mock_finding.severity.value = "critical"
        mock_finding.passed = False
        mock_report.findings = [mock_finding]

        with patch(
            "app.services.security_audit_service.get_security_audit_service"
        ) as mock_get:
            mock_audit_service = MagicMock()
            mock_audit_service.run_audit.return_value = mock_report
            mock_get.return_value = mock_audit_service

            checks = await service._run_security_checks()

        critical_check = next(
            (c for c in checks if c.name == "Kritische Security-Issues"), None
        )
        assert critical_check is not None
        assert critical_check.status == ReadinessStatus.CRITICAL

    @pytest.mark.asyncio
    async def test_security_checks_without_critical_issues(self, service, mock_security_audit_report):
        """Security Check ohne kritische Issues sollte READY sein."""
        mock_security_audit_report.findings = []

        with patch(
            "app.services.security_audit_service.get_security_audit_service"
        ) as mock_get:
            mock_audit_service = MagicMock()
            mock_audit_service.run_audit.return_value = mock_security_audit_report
            mock_get.return_value = mock_audit_service

            checks = await service._run_security_checks()

        critical_check = next(
            (c for c in checks if c.name == "Kritische Security-Issues"), None
        )
        assert critical_check is not None
        assert critical_check.status == ReadinessStatus.READY


# =============================================================================
# PERFORMANCE CHECKS TESTS
# =============================================================================


class TestPerformanceChecks:
    """Tests fuer Performance Checks."""

    @pytest.mark.asyncio
    async def test_performance_checks_good_latency(self, service, mock_profiling_summary):
        """Performance Check mit niedriger Latenz sollte READY sein."""
        mock_profiling_summary["p99_latency_ms"] = 500

        with patch(
            "app.services.profiling_service.get_profiling_service"
        ) as mock_get:
            mock_profiling_service = MagicMock()
            mock_profiling_service.get_summary.return_value = mock_profiling_summary
            mock_get.return_value = mock_profiling_service

            checks = await service._run_performance_checks()

        latency_check = next(
            (c for c in checks if c.name == "P99 Latenz"), None
        )
        assert latency_check is not None
        assert latency_check.status == ReadinessStatus.READY

    @pytest.mark.asyncio
    async def test_performance_checks_medium_latency(self, service, mock_profiling_summary):
        """Performance Check mit mittlerer Latenz sollte WARNINGS sein."""
        mock_profiling_summary["p99_latency_ms"] = 1500

        with patch(
            "app.services.profiling_service.get_profiling_service"
        ) as mock_get:
            mock_profiling_service = MagicMock()
            mock_profiling_service.get_summary.return_value = mock_profiling_summary
            mock_get.return_value = mock_profiling_service

            checks = await service._run_performance_checks()

        latency_check = next(
            (c for c in checks if c.name == "P99 Latenz"), None
        )
        assert latency_check is not None
        assert latency_check.status == ReadinessStatus.WARNINGS

    @pytest.mark.asyncio
    async def test_performance_checks_high_latency(self, service, mock_profiling_summary):
        """Performance Check mit hoher Latenz sollte NOT_READY sein."""
        mock_profiling_summary["p99_latency_ms"] = 3000

        with patch(
            "app.services.profiling_service.get_profiling_service"
        ) as mock_get:
            mock_profiling_service = MagicMock()
            mock_profiling_service.get_summary.return_value = mock_profiling_summary
            mock_get.return_value = mock_profiling_service

            checks = await service._run_performance_checks()

        latency_check = next(
            (c for c in checks if c.name == "P99 Latenz"), None
        )
        assert latency_check is not None
        assert latency_check.status == ReadinessStatus.NOT_READY

    @pytest.mark.asyncio
    async def test_performance_checks_low_error_rate(self, service, mock_profiling_summary):
        """Performance Check mit niedriger Error Rate sollte READY sein."""
        mock_profiling_summary["error_rate_percent"] = 0.5

        with patch(
            "app.services.profiling_service.get_profiling_service"
        ) as mock_get:
            mock_profiling_service = MagicMock()
            mock_profiling_service.get_summary.return_value = mock_profiling_summary
            mock_get.return_value = mock_profiling_service

            checks = await service._run_performance_checks()

        error_check = next(
            (c for c in checks if c.name == "Error Rate"), None
        )
        assert error_check is not None
        assert error_check.status == ReadinessStatus.READY

    @pytest.mark.asyncio
    async def test_performance_checks_high_error_rate(self, service, mock_profiling_summary):
        """Performance Check mit hoher Error Rate sollte NOT_READY sein."""
        mock_profiling_summary["error_rate_percent"] = 10.0

        with patch(
            "app.services.profiling_service.get_profiling_service"
        ) as mock_get:
            mock_profiling_service = MagicMock()
            mock_profiling_service.get_summary.return_value = mock_profiling_summary
            mock_get.return_value = mock_profiling_service

            checks = await service._run_performance_checks()

        error_check = next(
            (c for c in checks if c.name == "Error Rate"), None
        )
        assert error_check is not None
        assert error_check.status == ReadinessStatus.NOT_READY


# =============================================================================
# CONFIGURATION CHECKS TESTS
# =============================================================================


class TestConfigurationChecks:
    """Tests fuer Configuration Checks."""

    @pytest.mark.asyncio
    async def test_config_debug_mode_disabled(self, service):
        """Debug-Modus deaktiviert sollte READY sein."""
        mock_settings = MagicMock()
        mock_settings.DEBUG = False
        mock_settings.RATE_LIMIT_ENABLED = True
        mock_settings.CSRF_ENABLED = True

        with patch("app.core.config.settings", mock_settings):
            checks = await service._run_configuration_checks()

        debug_check = next(
            (c for c in checks if c.name == "Debug-Modus"), None
        )
        assert debug_check is not None
        assert debug_check.status == ReadinessStatus.READY

    @pytest.mark.asyncio
    async def test_config_debug_mode_enabled(self, service):
        """Debug-Modus aktiviert sollte CRITICAL sein."""
        mock_settings = MagicMock()
        mock_settings.DEBUG = True
        mock_settings.RATE_LIMIT_ENABLED = True
        mock_settings.CSRF_ENABLED = True

        with patch("app.core.config.settings", mock_settings):
            checks = await service._run_configuration_checks()

        debug_check = next(
            (c for c in checks if c.name == "Debug-Modus"), None
        )
        assert debug_check is not None
        assert debug_check.status == ReadinessStatus.CRITICAL

    @pytest.mark.asyncio
    async def test_config_rate_limiting_enabled(self, service):
        """Rate Limiting aktiviert sollte READY sein."""
        mock_settings = MagicMock()
        mock_settings.DEBUG = False
        mock_settings.RATE_LIMIT_ENABLED = True
        mock_settings.CSRF_ENABLED = True

        with patch("app.core.config.settings", mock_settings):
            checks = await service._run_configuration_checks()

        rate_check = next(
            (c for c in checks if c.name == "Rate Limiting"), None
        )
        assert rate_check is not None
        assert rate_check.status == ReadinessStatus.READY

    @pytest.mark.asyncio
    async def test_config_rate_limiting_disabled(self, service):
        """Rate Limiting deaktiviert sollte NOT_READY sein."""
        mock_settings = MagicMock()
        mock_settings.DEBUG = False
        mock_settings.RATE_LIMIT_ENABLED = False
        mock_settings.CSRF_ENABLED = True

        with patch("app.core.config.settings", mock_settings):
            checks = await service._run_configuration_checks()

        rate_check = next(
            (c for c in checks if c.name == "Rate Limiting"), None
        )
        assert rate_check is not None
        assert rate_check.status == ReadinessStatus.NOT_READY

    @pytest.mark.asyncio
    async def test_config_csrf_enabled(self, service):
        """CSRF aktiviert sollte READY sein."""
        mock_settings = MagicMock()
        mock_settings.DEBUG = False
        mock_settings.RATE_LIMIT_ENABLED = True
        mock_settings.CSRF_ENABLED = True

        with patch("app.core.config.settings", mock_settings):
            checks = await service._run_configuration_checks()

        csrf_check = next(
            (c for c in checks if c.name == "CSRF-Schutz"), None
        )
        assert csrf_check is not None
        assert csrf_check.status == ReadinessStatus.READY


# =============================================================================
# SCORE AND STATUS CALCULATION TESTS
# =============================================================================


class TestScoreCalculation:
    """Tests fuer Score-Berechnung."""

    def test_calculate_score_all_ready(self, service):
        """Alle READY sollte Score 100 ergeben."""
        checks = [
            ReadinessCheck(
                name="Check 1",
                category=CheckCategory.SECURITY,
                status=ReadinessStatus.READY,
                message="OK",
            ),
            ReadinessCheck(
                name="Check 2",
                category=CheckCategory.HEALTH,
                status=ReadinessStatus.READY,
                message="OK",
            ),
        ]

        score = service._calculate_score(checks)

        assert score == 100.0

    def test_calculate_score_all_critical(self, service):
        """Alle CRITICAL sollte Score 0 ergeben."""
        checks = [
            ReadinessCheck(
                name="Check 1",
                category=CheckCategory.SECURITY,
                status=ReadinessStatus.CRITICAL,
                message="Fehler",
            ),
            ReadinessCheck(
                name="Check 2",
                category=CheckCategory.HEALTH,
                status=ReadinessStatus.CRITICAL,
                message="Fehler",
            ),
        ]

        score = service._calculate_score(checks)

        assert score == 0.0

    def test_calculate_score_mixed(self, service):
        """Gemischte Status sollten gewichteten Score ergeben."""
        checks = [
            ReadinessCheck(
                name="Check 1",
                category=CheckCategory.SECURITY,
                status=ReadinessStatus.READY,  # 1.0
                message="OK",
            ),
            ReadinessCheck(
                name="Check 2",
                category=CheckCategory.HEALTH,
                status=ReadinessStatus.WARNINGS,  # 0.7
                message="Warnung",
            ),
            ReadinessCheck(
                name="Check 3",
                category=CheckCategory.CONFIGURATION,
                status=ReadinessStatus.NOT_READY,  # 0.3
                message="Nicht bereit",
            ),
            ReadinessCheck(
                name="Check 4",
                category=CheckCategory.RESOURCES,
                status=ReadinessStatus.CRITICAL,  # 0.0
                message="Kritisch",
            ),
        ]

        score = service._calculate_score(checks)

        # (1.0 + 0.7 + 0.3 + 0.0) / 4 * 100 = 50.0
        assert score == 50.0

    def test_calculate_score_empty(self, service):
        """Keine Checks sollte Score 100 ergeben."""
        score = service._calculate_score([])
        assert score == 100.0


class TestOverallStatusDetermination:
    """Tests fuer Gesamt-Status-Bestimmung."""

    def test_determine_status_critical_overrides(self, service):
        """CRITICAL Status sollte immer CRITICAL ergeben."""
        checks = [
            ReadinessCheck(
                name="Check 1",
                category=CheckCategory.SECURITY,
                status=ReadinessStatus.READY,
                message="OK",
            ),
            ReadinessCheck(
                name="Check 2",
                category=CheckCategory.HEALTH,
                status=ReadinessStatus.CRITICAL,
                message="Kritisch",
            ),
        ]

        status = service._determine_overall_status(checks, 85.0)

        assert status == ReadinessStatus.CRITICAL

    def test_determine_status_not_ready_overrides(self, service):
        """NOT_READY Status sollte NOT_READY ergeben."""
        checks = [
            ReadinessCheck(
                name="Check 1",
                category=CheckCategory.SECURITY,
                status=ReadinessStatus.READY,
                message="OK",
            ),
            ReadinessCheck(
                name="Check 2",
                category=CheckCategory.HEALTH,
                status=ReadinessStatus.NOT_READY,
                message="Nicht bereit",
            ),
        ]

        status = service._determine_overall_status(checks, 85.0)

        assert status == ReadinessStatus.NOT_READY

    def test_determine_status_high_score_ready(self, service):
        """Hoher Score ohne Blocker sollte READY ergeben."""
        checks = [
            ReadinessCheck(
                name="Check 1",
                category=CheckCategory.SECURITY,
                status=ReadinessStatus.READY,
                message="OK",
            ),
            ReadinessCheck(
                name="Check 2",
                category=CheckCategory.HEALTH,
                status=ReadinessStatus.READY,
                message="OK",
            ),
        ]

        status = service._determine_overall_status(checks, 95.0)

        assert status == ReadinessStatus.READY

    def test_determine_status_medium_score_warnings(self, service):
        """Mittlerer Score ohne Blocker sollte WARNINGS ergeben."""
        checks = [
            ReadinessCheck(
                name="Check 1",
                category=CheckCategory.SECURITY,
                status=ReadinessStatus.WARNINGS,
                message="Warnung",
            ),
        ]

        status = service._determine_overall_status(checks, 75.0)

        assert status == ReadinessStatus.WARNINGS

    def test_determine_status_low_score_not_ready(self, service):
        """Niedriger Score ohne Blocker sollte NOT_READY ergeben."""
        checks = [
            ReadinessCheck(
                name="Check 1",
                category=CheckCategory.SECURITY,
                status=ReadinessStatus.WARNINGS,
                message="Warnung",
            ),
        ]

        status = service._determine_overall_status(checks, 50.0)

        assert status == ReadinessStatus.NOT_READY


class TestSummaryCalculation:
    """Tests fuer Summary-Berechnung."""

    def test_calculate_summary(self, service):
        """Summary sollte korrekte Zaehler haben."""
        checks = [
            ReadinessCheck(
                name="Check 1",
                category=CheckCategory.SECURITY,
                status=ReadinessStatus.READY,
                message="OK",
            ),
            ReadinessCheck(
                name="Check 2",
                category=CheckCategory.SECURITY,
                status=ReadinessStatus.WARNINGS,
                message="Warnung",
            ),
            ReadinessCheck(
                name="Check 3",
                category=CheckCategory.HEALTH,
                status=ReadinessStatus.NOT_READY,
                message="Nicht bereit",
            ),
            ReadinessCheck(
                name="Check 4",
                category=CheckCategory.HEALTH,
                status=ReadinessStatus.CRITICAL,
                message="Kritisch",
            ),
        ]

        summary = service._calculate_summary(checks)

        assert summary["total"] == 4
        assert summary["ready"] == 1
        assert summary["warnings"] == 1
        assert summary["not_ready"] == 1
        assert summary["critical"] == 1
        assert summary["security_total"] == 2
        assert summary["security_passed"] == 2
        assert summary["health_total"] == 2
        assert summary["health_passed"] == 0


# =============================================================================
# FULL READINESS CHECK TESTS
# =============================================================================


class TestFullReadinessCheck:
    """Tests fuer vollstaendigen Readiness Check."""

    @pytest.mark.asyncio
    async def test_run_readiness_check_returns_report(self, service):
        """run_readiness_check sollte ReadinessReport zurueckgeben."""
        # Mock alle Check-Methoden
        with patch.object(service, "_run_security_checks", new_callable=AsyncMock) as mock_sec:
            with patch.object(service, "_run_performance_checks", new_callable=AsyncMock) as mock_perf:
                with patch.object(service, "_run_health_checks", new_callable=AsyncMock) as mock_health:
                    with patch.object(service, "_run_configuration_checks", new_callable=AsyncMock) as mock_config:
                        with patch.object(service, "_run_resource_checks", new_callable=AsyncMock) as mock_res:
                            mock_sec.return_value = [
                                ReadinessCheck(
                                    name="Security",
                                    category=CheckCategory.SECURITY,
                                    status=ReadinessStatus.READY,
                                    message="OK",
                                )
                            ]
                            mock_perf.return_value = []
                            mock_health.return_value = []
                            mock_config.return_value = []
                            mock_res.return_value = []

                            report = await service.run_readiness_check()

        assert isinstance(report, ReadinessReport)
        assert len(report.checks) == 1
        assert report.overall_score == 100.0


# =============================================================================
# SINGLETON TESTS
# =============================================================================


class TestSingleton:
    """Tests fuer Singleton-Verhalten."""

    def test_get_production_readiness_service_returns_instance(self):
        """get_production_readiness_service sollte Instanz zurueckgeben."""
        service1 = get_production_readiness_service()
        service2 = get_production_readiness_service()

        assert service1 is service2
        assert isinstance(service1, ProductionReadinessService)
