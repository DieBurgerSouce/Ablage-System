# -*- coding: utf-8 -*-
"""
Production Readiness Service.

Kombiniert alle Monitoring- und Audit-Funktionen fuer einen
umfassenden Production Readiness Check:
- Security Score
- Performance Metriken
- System Health
- Konfigurationspruefung
- Ressourcen-Check

Feinpoliert und durchdacht - Enterprise Production Readiness.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

import structlog

logger = structlog.get_logger(__name__)


# =============================================================================
# ENUMS AND DATA CLASSES
# =============================================================================


class ReadinessStatus(str, Enum):
    """Status der Production Readiness."""

    READY = "ready"
    WARNINGS = "warnings"
    NOT_READY = "not_ready"
    CRITICAL = "critical"


class CheckCategory(str, Enum):
    """Kategorie eines Readiness-Checks."""

    SECURITY = "security"
    PERFORMANCE = "performance"
    HEALTH = "health"
    CONFIGURATION = "configuration"
    RESOURCES = "resources"
    DEPENDENCIES = "dependencies"


@dataclass
class ReadinessCheck:
    """Einzelner Readiness Check."""

    name: str
    category: CheckCategory
    status: ReadinessStatus
    message: str
    details: Dict[str, Any] = field(default_factory=dict)
    recommendation: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Konvertiert zu Dictionary."""
        return {
            "name": self.name,
            "category": self.category.value,
            "status": self.status.value,
            "message": self.message,
            "details": self.details,
            "recommendation": self.recommendation,
        }


@dataclass
class ReadinessReport:
    """Vollstaendiger Readiness Report."""

    timestamp: datetime
    overall_status: ReadinessStatus
    overall_score: float
    checks: List[ReadinessCheck]
    summary: Dict[str, int]

    def to_dict(self) -> Dict[str, Any]:
        """Konvertiert zu Dictionary."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "overall_status": self.overall_status.value,
            "overall_score": round(self.overall_score, 1),
            "checks": [c.to_dict() for c in self.checks],
            "summary": self.summary,
            "total_checks": len(self.checks),
            "passed_checks": sum(1 for c in self.checks if c.status in (ReadinessStatus.READY, ReadinessStatus.WARNINGS)),
            "failed_checks": sum(1 for c in self.checks if c.status in (ReadinessStatus.NOT_READY, ReadinessStatus.CRITICAL)),
        }


# =============================================================================
# PRODUCTION READINESS SERVICE
# =============================================================================


class ProductionReadinessService:
    """
    Service fuer Production Readiness Checks.

    Kombiniert:
    - Security Audit
    - Performance Profiling
    - System Health
    - Konfiguration
    - Ressourcen
    """

    def __init__(self) -> None:
        """Initialisiere Production Readiness Service."""
        # Stateless service - keine Initialisierung erforderlich

    async def run_readiness_check(self) -> ReadinessReport:
        """
        Fuehrt vollstaendigen Production Readiness Check durch.

        Returns:
            ReadinessReport mit allen Checks
        """
        checks: List[ReadinessCheck] = []

        # Security Checks
        checks.extend(await self._run_security_checks())

        # Performance Checks
        checks.extend(await self._run_performance_checks())

        # Health Checks
        checks.extend(await self._run_health_checks())

        # Configuration Checks
        checks.extend(await self._run_configuration_checks())

        # Resource Checks
        checks.extend(await self._run_resource_checks())

        # Summary berechnen
        summary = self._calculate_summary(checks)
        score = self._calculate_score(checks)
        overall_status = self._determine_overall_status(checks, score)

        report = ReadinessReport(
            timestamp=datetime.now(timezone.utc),
            overall_status=overall_status,
            overall_score=score,
            checks=checks,
            summary=summary,
        )

        logger.info(
            "production_readiness_check_completed",
            overall_status=overall_status.value,
            score=score,
            total_checks=len(checks),
        )

        return report

    async def _run_security_checks(self) -> List[ReadinessCheck]:
        """Fuehrt Security Checks durch."""
        checks = []

        try:
            from app.services.security_audit_service import get_security_audit_service

            audit_service = get_security_audit_service()
            audit_report = audit_service.run_audit()

            # Security Score Check
            if audit_report.score >= 90:
                status = ReadinessStatus.READY
                message = f"Security Score: {audit_report.score:.1f}% (Ausgezeichnet)"
            elif audit_report.score >= 70:
                status = ReadinessStatus.WARNINGS
                message = f"Security Score: {audit_report.score:.1f}% (Akzeptabel)"
            else:
                status = ReadinessStatus.NOT_READY
                message = f"Security Score: {audit_report.score:.1f}% (Unzureichend)"

            checks.append(ReadinessCheck(
                name="Security Score",
                category=CheckCategory.SECURITY,
                status=status,
                message=message,
                details={
                    "score": audit_report.score,
                    "critical_issues": sum(1 for f in audit_report.findings if f.severity.value == "critical" and not f.passed),
                    "high_issues": sum(1 for f in audit_report.findings if f.severity.value == "high" and not f.passed),
                },
                recommendation="Behebe kritische Security-Issues vor Production-Deployment" if status != ReadinessStatus.READY else None,
            ))

            # Critical Issues Check
            critical_count = sum(1 for f in audit_report.findings if f.severity.value == "critical" and not f.passed)
            if critical_count == 0:
                checks.append(ReadinessCheck(
                    name="Kritische Security-Issues",
                    category=CheckCategory.SECURITY,
                    status=ReadinessStatus.READY,
                    message="Keine kritischen Security-Issues",
                ))
            else:
                checks.append(ReadinessCheck(
                    name="Kritische Security-Issues",
                    category=CheckCategory.SECURITY,
                    status=ReadinessStatus.CRITICAL,
                    message=f"{critical_count} kritische Security-Issues gefunden",
                    details={"count": critical_count},
                    recommendation="Kritische Issues MUESSEN vor Production behoben werden",
                ))

        except Exception as e:
            logger.warning("security_checks_failed", error=str(e))
            checks.append(ReadinessCheck(
                name="Security Audit",
                category=CheckCategory.SECURITY,
                status=ReadinessStatus.NOT_READY,
                message=f"Security Audit fehlgeschlagen: {str(e)}",
            ))

        return checks

    async def _run_performance_checks(self) -> List[ReadinessCheck]:
        """Fuehrt Performance Checks durch."""
        checks = []

        try:
            from app.services.profiling_service import get_profiling_service

            profiling_service = get_profiling_service()
            summary = profiling_service.get_summary()

            # P99 Latenz Check
            p99 = summary.get("p99_latency_ms", 0)
            if p99 < 1000:
                status = ReadinessStatus.READY
                message = f"P99 Latenz: {p99:.0f}ms (Gut)"
            elif p99 < 2000:
                status = ReadinessStatus.WARNINGS
                message = f"P99 Latenz: {p99:.0f}ms (Akzeptabel)"
            else:
                status = ReadinessStatus.NOT_READY
                message = f"P99 Latenz: {p99:.0f}ms (Zu hoch)"

            checks.append(ReadinessCheck(
                name="P99 Latenz",
                category=CheckCategory.PERFORMANCE,
                status=status,
                message=message,
                details={"p99_ms": p99, "avg_ms": summary.get("avg_latency_ms", 0)},
                recommendation="Optimiere langsame Endpoints" if status != ReadinessStatus.READY else None,
            ))

            # Error Rate Check
            error_rate = summary.get("error_rate_percent", 0)
            if error_rate < 1:
                status = ReadinessStatus.READY
                message = f"Error Rate: {error_rate:.2f}% (Excellent)"
            elif error_rate < 5:
                status = ReadinessStatus.WARNINGS
                message = f"Error Rate: {error_rate:.2f}% (Akzeptabel)"
            else:
                status = ReadinessStatus.NOT_READY
                message = f"Error Rate: {error_rate:.2f}% (Zu hoch)"

            checks.append(ReadinessCheck(
                name="Error Rate",
                category=CheckCategory.PERFORMANCE,
                status=status,
                message=message,
                details={"error_rate_percent": error_rate},
                recommendation="Untersuche und behebe haeufige Fehler" if status != ReadinessStatus.READY else None,
            ))

        except Exception as e:
            logger.warning("performance_checks_failed", error=str(e))

        return checks

    async def _run_health_checks(self) -> List[ReadinessCheck]:
        """Fuehrt Health Checks durch."""
        checks = []

        # Database Check
        try:
            from app.db.session import async_session_maker
            from sqlalchemy import text

            async with async_session_maker() as session:
                await session.execute(text("SELECT 1"))

            checks.append(ReadinessCheck(
                name="Database Verbindung",
                category=CheckCategory.HEALTH,
                status=ReadinessStatus.READY,
                message="PostgreSQL erreichbar",
            ))
        except Exception as e:
            checks.append(ReadinessCheck(
                name="Database Verbindung",
                category=CheckCategory.HEALTH,
                status=ReadinessStatus.CRITICAL,
                message=f"PostgreSQL nicht erreichbar: {str(e)[:100]}",
                recommendation="Pruefe DATABASE_URL und PostgreSQL-Status",
            ))

        # Redis Check
        try:
            from app.core.redis_state import get_redis

            redis = await get_redis()
            if await redis.ping():
                checks.append(ReadinessCheck(
                    name="Redis Verbindung",
                    category=CheckCategory.HEALTH,
                    status=ReadinessStatus.READY,
                    message="Redis erreichbar",
                ))
            else:
                raise ConnectionError("Redis Ping fehlgeschlagen")
        except Exception as e:
            checks.append(ReadinessCheck(
                name="Redis Verbindung",
                category=CheckCategory.HEALTH,
                status=ReadinessStatus.CRITICAL,
                message=f"Redis nicht erreichbar: {str(e)[:100]}",
                recommendation="Pruefe REDIS_URL und Redis-Status",
            ))

        # GPU Check
        try:
            import torch

            if torch.cuda.is_available():
                gpu_name = torch.cuda.get_device_name(0)
                vram_total = torch.cuda.get_device_properties(0).total_memory / (1024**3)
                vram_used = torch.cuda.memory_allocated(0) / (1024**3)
                vram_percent = (vram_used / vram_total) * 100

                if vram_percent < 85:
                    status = ReadinessStatus.READY
                    message = f"GPU verfuegbar: {gpu_name} ({vram_percent:.0f}% VRAM)"
                else:
                    status = ReadinessStatus.WARNINGS
                    message = f"GPU VRAM hoch: {vram_percent:.0f}%"

                checks.append(ReadinessCheck(
                    name="GPU Status",
                    category=CheckCategory.HEALTH,
                    status=status,
                    message=message,
                    details={
                        "gpu_name": gpu_name,
                        "vram_total_gb": round(vram_total, 1),
                        "vram_used_gb": round(vram_used, 1),
                        "vram_percent": round(vram_percent, 1),
                    },
                ))
            else:
                checks.append(ReadinessCheck(
                    name="GPU Status",
                    category=CheckCategory.HEALTH,
                    status=ReadinessStatus.WARNINGS,
                    message="Keine GPU verfuegbar - CPU-Fallback aktiv",
                    recommendation="GPU wird fuer optimale OCR-Performance empfohlen",
                ))
        except ImportError:
            checks.append(ReadinessCheck(
                name="GPU Status",
                category=CheckCategory.HEALTH,
                status=ReadinessStatus.WARNINGS,
                message="PyTorch nicht installiert",
            ))

        return checks

    async def _run_configuration_checks(self) -> List[ReadinessCheck]:
        """Fuehrt Konfiguration Checks durch."""
        checks = []

        try:
            from app.core.config import settings

            # Debug Mode
            if not settings.DEBUG:
                checks.append(ReadinessCheck(
                    name="Debug-Modus",
                    category=CheckCategory.CONFIGURATION,
                    status=ReadinessStatus.READY,
                    message="Debug-Modus deaktiviert",
                ))
            else:
                checks.append(ReadinessCheck(
                    name="Debug-Modus",
                    category=CheckCategory.CONFIGURATION,
                    status=ReadinessStatus.CRITICAL,
                    message="Debug-Modus aktiviert!",
                    recommendation="Setze DEBUG=false fuer Production",
                ))

            # Rate Limiting
            if getattr(settings, "RATE_LIMIT_ENABLED", False):
                checks.append(ReadinessCheck(
                    name="Rate Limiting",
                    category=CheckCategory.CONFIGURATION,
                    status=ReadinessStatus.READY,
                    message="Rate Limiting aktiviert",
                ))
            else:
                checks.append(ReadinessCheck(
                    name="Rate Limiting",
                    category=CheckCategory.CONFIGURATION,
                    status=ReadinessStatus.NOT_READY,
                    message="Rate Limiting deaktiviert",
                    recommendation="Aktiviere Rate Limiting fuer Production",
                ))

            # CSRF
            if getattr(settings, "CSRF_ENABLED", True):
                checks.append(ReadinessCheck(
                    name="CSRF-Schutz",
                    category=CheckCategory.CONFIGURATION,
                    status=ReadinessStatus.READY,
                    message="CSRF-Schutz aktiviert",
                ))
            else:
                checks.append(ReadinessCheck(
                    name="CSRF-Schutz",
                    category=CheckCategory.CONFIGURATION,
                    status=ReadinessStatus.NOT_READY,
                    message="CSRF-Schutz deaktiviert",
                    recommendation="Aktiviere CSRF fuer Web-Clients",
                ))

        except Exception as e:
            logger.warning("configuration_checks_failed", error=str(e))

        return checks

    async def _run_resource_checks(self) -> List[ReadinessCheck]:
        """Fuehrt Ressourcen Checks durch."""
        checks = []

        try:
            import psutil

            # CPU
            cpu_percent = psutil.cpu_percent(interval=1)
            if cpu_percent < 80:
                status = ReadinessStatus.READY
                message = f"CPU-Auslastung: {cpu_percent}%"
            elif cpu_percent < 95:
                status = ReadinessStatus.WARNINGS
                message = f"CPU-Auslastung hoch: {cpu_percent}%"
            else:
                status = ReadinessStatus.NOT_READY
                message = f"CPU-Auslastung kritisch: {cpu_percent}%"

            checks.append(ReadinessCheck(
                name="CPU-Auslastung",
                category=CheckCategory.RESOURCES,
                status=status,
                message=message,
                details={"cpu_percent": cpu_percent},
            ))

            # Memory
            memory = psutil.virtual_memory()
            if memory.percent < 80:
                status = ReadinessStatus.READY
                message = f"RAM-Auslastung: {memory.percent}%"
            elif memory.percent < 90:
                status = ReadinessStatus.WARNINGS
                message = f"RAM-Auslastung hoch: {memory.percent}%"
            else:
                status = ReadinessStatus.NOT_READY
                message = f"RAM-Auslastung kritisch: {memory.percent}%"

            checks.append(ReadinessCheck(
                name="RAM-Auslastung",
                category=CheckCategory.RESOURCES,
                status=status,
                message=message,
                details={
                    "percent": memory.percent,
                    "available_gb": round(memory.available / (1024**3), 1),
                },
            ))

            # Disk
            disk = psutil.disk_usage("/")
            if disk.percent < 80:
                status = ReadinessStatus.READY
                message = f"Disk-Auslastung: {disk.percent}%"
            elif disk.percent < 90:
                status = ReadinessStatus.WARNINGS
                message = f"Disk-Auslastung hoch: {disk.percent}%"
            else:
                status = ReadinessStatus.NOT_READY
                message = f"Disk-Auslastung kritisch: {disk.percent}%"

            checks.append(ReadinessCheck(
                name="Disk-Auslastung",
                category=CheckCategory.RESOURCES,
                status=status,
                message=message,
                details={
                    "percent": disk.percent,
                    "free_gb": round(disk.free / (1024**3), 1),
                },
            ))

        except Exception as e:
            logger.warning("resource_checks_failed", error=str(e))

        return checks

    def _calculate_summary(self, checks: List[ReadinessCheck]) -> Dict[str, int]:
        """Berechnet Summary."""
        summary = {
            "total": len(checks),
            "ready": sum(1 for c in checks if c.status == ReadinessStatus.READY),
            "warnings": sum(1 for c in checks if c.status == ReadinessStatus.WARNINGS),
            "not_ready": sum(1 for c in checks if c.status == ReadinessStatus.NOT_READY),
            "critical": sum(1 for c in checks if c.status == ReadinessStatus.CRITICAL),
        }

        for category in CheckCategory:
            summary[f"{category.value}_total"] = sum(1 for c in checks if c.category == category)
            summary[f"{category.value}_passed"] = sum(
                1 for c in checks
                if c.category == category and c.status in (ReadinessStatus.READY, ReadinessStatus.WARNINGS)
            )

        return summary

    def _calculate_score(self, checks: List[ReadinessCheck]) -> float:
        """Berechnet Score (0-100)."""
        if not checks:
            return 100.0

        weights = {
            ReadinessStatus.READY: 1.0,
            ReadinessStatus.WARNINGS: 0.7,
            ReadinessStatus.NOT_READY: 0.3,
            ReadinessStatus.CRITICAL: 0.0,
        }

        total_score = sum(weights[c.status] for c in checks)
        return (total_score / len(checks)) * 100

    def _determine_overall_status(self, checks: List[ReadinessCheck], score: float) -> ReadinessStatus:
        """Bestimmt Gesamt-Status."""
        # Critical Issues blockieren
        if any(c.status == ReadinessStatus.CRITICAL for c in checks):
            return ReadinessStatus.CRITICAL

        # Not Ready Issues
        if any(c.status == ReadinessStatus.NOT_READY for c in checks):
            return ReadinessStatus.NOT_READY

        # Score-basiert
        if score >= 90:
            return ReadinessStatus.READY
        elif score >= 70:
            return ReadinessStatus.WARNINGS
        else:
            return ReadinessStatus.NOT_READY


# =============================================================================
# SINGLETON ACCESS
# =============================================================================


_production_readiness_service: Optional[ProductionReadinessService] = None


def get_production_readiness_service() -> ProductionReadinessService:
    """Gibt ProductionReadinessService-Instanz zurueck."""
    global _production_readiness_service
    if _production_readiness_service is None:
        _production_readiness_service = ProductionReadinessService()
    return _production_readiness_service
