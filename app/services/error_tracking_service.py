# -*- coding: utf-8 -*-
"""
Error Tracking Service fuer Ablage-System OCR.

Zentrales Error-Tracking mit:
- Fehlerfrequenz-Tracking pro Kategorie
- Error Analytics und Statistiken
- Prometheus Metriken Integration
- Alert-Schwellenwerte
- Historische Fehler-Analyse

Feinpoliert und durchdacht - Enterprise Error Tracking.
"""

import asyncio
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from enum import Enum
from threading import Lock
from typing import Any, Dict, List, Optional, Callable

import structlog
from prometheus_client import Counter, Gauge, Histogram

logger = structlog.get_logger(__name__)


# =============================================================================
# PROMETHEUS METRIKEN
# =============================================================================

error_total = Counter(
    "ablage_errors_total",
    "Gesamtzahl aufgetretener Fehler",
    ["category", "error_type", "severity"]
)

error_rate = Gauge(
    "ablage_error_rate_per_minute",
    "Fehlerrate pro Minute",
    ["category"]
)

error_response_time = Histogram(
    "ablage_error_response_time_seconds",
    "Response-Zeit bei Fehleranfragen",
    ["error_type"],
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]
)

active_error_alerts = Gauge(
    "ablage_active_error_alerts",
    "Anzahl aktiver Fehler-Alerts",
    ["category"]
)


# =============================================================================
# ENUMS & DATACLASSES
# =============================================================================


class ErrorSeverity(str, Enum):
    """Fehler-Schweregrad."""
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class ErrorCategory(str, Enum):
    """Fehler-Kategorien."""
    OCR = "ocr"
    GPU = "gpu"
    DATABASE = "database"
    AUTH = "auth"
    VALIDATION = "validation"
    NETWORK = "network"
    FILE = "file"
    COMPLIANCE = "compliance"
    SYSTEM = "system"
    UNKNOWN = "unknown"


@dataclass
class TrackedError:
    """Ein einzelner getrackter Fehler."""
    timestamp: datetime
    category: ErrorCategory
    error_type: str
    severity: ErrorSeverity
    message: str
    path: Optional[str] = None
    user_id: Optional[str] = None
    request_id: Optional[str] = None
    details: Optional[Dict[str, Any]] = None
    stack_trace: Optional[str] = None
    response_time_ms: Optional[float] = None


@dataclass
class ErrorStats:
    """Fehler-Statistiken fuer eine Kategorie."""
    total_count: int = 0
    last_hour_count: int = 0
    last_24h_count: int = 0
    last_error_time: Optional[datetime] = None
    error_types: Dict[str, int] = field(default_factory=dict)
    severity_counts: Dict[str, int] = field(default_factory=dict)
    rate_per_minute: float = 0.0


@dataclass
class AlertConfig:
    """Konfiguration fuer Error-Alerts."""
    category: ErrorCategory
    threshold_per_minute: float = 10.0
    threshold_severity: ErrorSeverity = ErrorSeverity.ERROR
    cooldown_minutes: int = 5
    callback: Optional[Callable[[str, Dict[str, Any]], None]] = None


# =============================================================================
# ERROR TRACKING SERVICE
# =============================================================================


class ErrorTrackingService:
    """
    Zentraler Error-Tracking-Service.

    Features:
    - In-Memory Error Buffer mit konfigurierbarer Groesse
    - Fehler-Kategorisierung und Severity-Tracking
    - Prometheus-Metriken Integration
    - Alert-Schwellenwerte
    - Historische Analyse

    Thread-safe fuer concurrent access.
    """

    _instance: Optional["ErrorTrackingService"] = None
    _lock = Lock()

    def __new__(cls) -> "ErrorTrackingService":
        """Singleton-Pattern."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(
        self,
        max_buffer_size: int = 10000,
        retention_hours: int = 24,
    ):
        """
        Initialisiere Error Tracking Service.

        Args:
            max_buffer_size: Maximale Anzahl Fehler im Buffer
            retention_hours: Wie lange Fehler aufbewahrt werden
        """
        if getattr(self, "_initialized", False):
            return

        self._max_buffer_size = max_buffer_size
        self._retention_hours = retention_hours
        self._error_buffer: List[TrackedError] = []
        self._buffer_lock = Lock()

        # Statistiken pro Kategorie
        self._stats: Dict[ErrorCategory, ErrorStats] = {
            cat: ErrorStats() for cat in ErrorCategory
        }
        self._stats_lock = Lock()

        # Alert-Konfigurationen
        self._alert_configs: Dict[ErrorCategory, AlertConfig] = {}
        self._active_alerts: Dict[ErrorCategory, datetime] = {}
        self._alert_lock = Lock()

        # Rate-Tracking (gleitendes Fenster)
        self._minute_buckets: Dict[ErrorCategory, Dict[int, int]] = defaultdict(dict)
        self._rate_lock = Lock()

        # Background task flag
        self._cleanup_task_started = False

        self._initialized = True
        logger.info("error_tracking_service_initialized")

    def track_error(
        self,
        category: ErrorCategory,
        error_type: str,
        severity: ErrorSeverity,
        message: str,
        path: Optional[str] = None,
        user_id: Optional[str] = None,
        request_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        stack_trace: Optional[str] = None,
        response_time_ms: Optional[float] = None,
    ) -> None:
        """
        Tracke einen Fehler.

        Args:
            category: Fehler-Kategorie
            error_type: Spezifischer Fehlertyp (z.B. "OCRProcessingError")
            severity: Schweregrad
            message: Fehlernachricht (KEINE PII!)
            path: Request-Pfad
            user_id: User-ID (anonymisiert)
            request_id: Request-ID fuer Korrelation
            details: Zusaetzliche Details (KEINE PII!)
            stack_trace: Stack-Trace (nur in DEBUG)
            response_time_ms: Response-Zeit in ms
        """
        now = datetime.now(timezone.utc)

        # Erstelle Fehler-Objekt
        error = TrackedError(
            timestamp=now,
            category=category,
            error_type=error_type,
            severity=severity,
            message=message[:500] if message else "",  # Truncate
            path=path,
            user_id=user_id,
            request_id=request_id,
            details=self._sanitize_details(details) if details else None,
            stack_trace=stack_trace[:2000] if stack_trace else None,  # Truncate
            response_time_ms=response_time_ms,
        )

        # Buffer aktualisieren
        with self._buffer_lock:
            self._error_buffer.append(error)
            # Ring-Buffer: Alte entfernen wenn zu voll
            if len(self._error_buffer) > self._max_buffer_size:
                self._error_buffer = self._error_buffer[-self._max_buffer_size:]

        # Statistiken aktualisieren
        self._update_stats(error)

        # Rate-Tracking
        self._update_rate(category, now)

        # Prometheus Metriken
        error_total.labels(
            category=category.value,
            error_type=error_type,
            severity=severity.value
        ).inc()

        if response_time_ms:
            error_response_time.labels(error_type=error_type).observe(
                response_time_ms / 1000.0
            )

        # Alert-Pruefung
        self._check_alerts(category, now)

        # Strukturiertes Logging
        log_level = self._severity_to_log_level(severity)
        log_method = getattr(logger, log_level, logger.error)
        log_method(
            "error_tracked",
            category=category.value,
            error_type=error_type,
            severity=severity.value,
            path=path,
            request_id=request_id,
        )

    def _update_stats(self, error: TrackedError) -> None:
        """Aktualisiere Statistiken fuer Fehler-Kategorie."""
        with self._stats_lock:
            stats = self._stats[error.category]
            stats.total_count += 1
            stats.last_error_time = error.timestamp

            # Error-Type Counter
            if error.error_type not in stats.error_types:
                stats.error_types[error.error_type] = 0
            stats.error_types[error.error_type] += 1

            # Severity Counter
            if error.severity.value not in stats.severity_counts:
                stats.severity_counts[error.severity.value] = 0
            stats.severity_counts[error.severity.value] += 1

    def _update_rate(self, category: ErrorCategory, now: datetime) -> None:
        """Aktualisiere Rate-Tracking (Fehler pro Minute)."""
        minute_key = int(now.timestamp() // 60)

        with self._rate_lock:
            buckets = self._minute_buckets[category]

            # Aktuellen Bucket erhoehen
            if minute_key not in buckets:
                buckets[minute_key] = 0
            buckets[minute_key] += 1

            # Alte Buckets entfernen (aelter als 1 Stunde)
            cutoff = minute_key - 60
            old_keys = [k for k in buckets if k < cutoff]
            for k in old_keys:
                del buckets[k]

            # Rate berechnen (Durchschnitt letzte 5 Minuten)
            recent_keys = [k for k in buckets if k >= minute_key - 5]
            if recent_keys:
                rate = sum(buckets[k] for k in recent_keys) / len(recent_keys)
                self._stats[category].rate_per_minute = rate
                error_rate.labels(category=category.value).set(rate)

    def _check_alerts(self, category: ErrorCategory, now: datetime) -> None:
        """Pruefe ob Alert ausgeloest werden soll."""
        with self._alert_lock:
            config = self._alert_configs.get(category)
            if not config:
                return

            # Cooldown pruefen
            last_alert = self._active_alerts.get(category)
            if last_alert:
                if (now - last_alert).total_seconds() < config.cooldown_minutes * 60:
                    return

            # Rate pruefen
            stats = self._stats[category]
            if stats.rate_per_minute >= config.threshold_per_minute:
                # Alert ausloesen
                self._active_alerts[category] = now
                active_error_alerts.labels(category=category.value).set(1)

                alert_data = {
                    "category": category.value,
                    "rate_per_minute": stats.rate_per_minute,
                    "threshold": config.threshold_per_minute,
                    "total_last_hour": stats.last_hour_count,
                    "timestamp": now.isoformat(),
                }

                logger.warning(
                    "error_alert_triggered",
                    **alert_data,
                )

                if config.callback:
                    try:
                        config.callback(f"Error-Alert: {category.value}", alert_data)
                    except Exception as e:
                        logger.error("alert_callback_failed", error=str(e))

    def configure_alert(
        self,
        category: ErrorCategory,
        threshold_per_minute: float = 10.0,
        cooldown_minutes: int = 5,
        callback: Optional[Callable[[str, Dict[str, Any]], None]] = None,
    ) -> None:
        """
        Konfiguriere Alert fuer eine Kategorie.

        Args:
            category: Fehler-Kategorie
            threshold_per_minute: Schwellenwert fuer Alert
            cooldown_minutes: Cooldown zwischen Alerts
            callback: Optionale Callback-Funktion bei Alert
        """
        with self._alert_lock:
            self._alert_configs[category] = AlertConfig(
                category=category,
                threshold_per_minute=threshold_per_minute,
                cooldown_minutes=cooldown_minutes,
                callback=callback,
            )
        logger.info(
            "alert_configured",
            category=category.value,
            threshold=threshold_per_minute,
        )

    def clear_alert(self, category: ErrorCategory) -> None:
        """Loesche aktiven Alert fuer Kategorie."""
        with self._alert_lock:
            if category in self._active_alerts:
                del self._active_alerts[category]
                active_error_alerts.labels(category=category.value).set(0)
                logger.info("alert_cleared", category=category.value)

    def get_stats(self, category: Optional[ErrorCategory] = None) -> Dict[str, Any]:
        """
        Hole Fehler-Statistiken.

        Args:
            category: Optional spezifische Kategorie, sonst alle

        Returns:
            Dict mit Statistiken
        """
        now = datetime.now(timezone.utc)
        hour_ago = now - timedelta(hours=1)
        day_ago = now - timedelta(hours=24)

        with self._stats_lock:
            if category:
                stats = self._stats[category]
                return self._format_stats(category, stats, hour_ago, day_ago)
            else:
                result = {}
                for cat, stats in self._stats.items():
                    result[cat.value] = self._format_stats(cat, stats, hour_ago, day_ago)
                return result

    def _format_stats(
        self,
        category: ErrorCategory,
        stats: ErrorStats,
        hour_ago: datetime,
        day_ago: datetime,
    ) -> Dict[str, Any]:
        """Formatiere Statistiken fuer Output."""
        # Zaehle Fehler in Zeitraeumen
        with self._buffer_lock:
            last_hour = sum(
                1 for e in self._error_buffer
                if e.category == category and e.timestamp >= hour_ago
            )
            last_24h = sum(
                1 for e in self._error_buffer
                if e.category == category and e.timestamp >= day_ago
            )

        return {
            "total_count": stats.total_count,
            "last_hour_count": last_hour,
            "last_24h_count": last_24h,
            "rate_per_minute": round(stats.rate_per_minute, 2),
            "last_error_time": stats.last_error_time.isoformat() if stats.last_error_time else None,
            "error_types": dict(stats.error_types),
            "severity_counts": dict(stats.severity_counts),
            "alert_active": category in self._active_alerts,
        }

    def get_recent_errors(
        self,
        category: Optional[ErrorCategory] = None,
        severity: Optional[ErrorSeverity] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """
        Hole letzte Fehler.

        Args:
            category: Filter nach Kategorie
            severity: Filter nach Severity
            limit: Maximale Anzahl

        Returns:
            Liste der letzten Fehler
        """
        with self._buffer_lock:
            errors = self._error_buffer.copy()

        # Filter anwenden
        if category:
            errors = [e for e in errors if e.category == category]
        if severity:
            errors = [e for e in errors if e.severity == severity]

        # Sortieren (neueste zuerst) und limitieren
        errors = sorted(errors, key=lambda e: e.timestamp, reverse=True)[:limit]

        return [
            {
                "timestamp": e.timestamp.isoformat(),
                "category": e.category.value,
                "error_type": e.error_type,
                "severity": e.severity.value,
                "message": e.message,
                "path": e.path,
                "request_id": e.request_id,
            }
            for e in errors
        ]

    def get_error_trends(
        self,
        category: ErrorCategory,
        hours: int = 24,
    ) -> Dict[str, Any]:
        """
        Hole Fehler-Trends ueber Zeit.

        Args:
            category: Kategorie
            hours: Zeitraum in Stunden

        Returns:
            Dict mit stuendlichen Fehler-Counts
        """
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(hours=hours)

        with self._buffer_lock:
            errors = [
                e for e in self._error_buffer
                if e.category == category and e.timestamp >= cutoff
            ]

        # Gruppiere nach Stunde
        hourly_counts: Dict[str, int] = {}
        for e in errors:
            hour_key = e.timestamp.strftime("%Y-%m-%d %H:00")
            if hour_key not in hourly_counts:
                hourly_counts[hour_key] = 0
            hourly_counts[hour_key] += 1

        # Sortiere chronologisch
        sorted_counts = dict(sorted(hourly_counts.items()))

        return {
            "category": category.value,
            "period_hours": hours,
            "total_errors": len(errors),
            "hourly_counts": sorted_counts,
            "average_per_hour": len(errors) / hours if hours > 0 else 0,
        }

    def get_top_errors(
        self,
        category: Optional[ErrorCategory] = None,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """
        Hole haeufigste Fehler.

        Args:
            category: Optional Kategorie-Filter
            limit: Anzahl

        Returns:
            Liste der haeufigsten Fehler-Typen
        """
        with self._stats_lock:
            if category:
                error_types = self._stats[category].error_types
                return [
                    {"error_type": et, "count": c, "category": category.value}
                    for et, c in sorted(error_types.items(), key=lambda x: -x[1])[:limit]
                ]
            else:
                all_errors: List[tuple] = []
                for cat, stats in self._stats.items():
                    for et, count in stats.error_types.items():
                        all_errors.append((et, count, cat.value))

                return [
                    {"error_type": et, "count": c, "category": cat}
                    for et, c, cat in sorted(all_errors, key=lambda x: -x[1])[:limit]
                ]

    async def cleanup_old_errors(self) -> int:
        """
        Entferne alte Fehler aus dem Buffer.

        Returns:
            Anzahl entfernter Fehler
        """
        cutoff = datetime.now(timezone.utc) - timedelta(hours=self._retention_hours)

        with self._buffer_lock:
            old_count = len(self._error_buffer)
            self._error_buffer = [
                e for e in self._error_buffer
                if e.timestamp >= cutoff
            ]
            removed = old_count - len(self._error_buffer)

        if removed > 0:
            logger.info("errors_cleaned_up", removed_count=removed)

        return removed

    async def start_cleanup_task(self) -> None:
        """Starte periodischen Cleanup-Task."""
        if self._cleanup_task_started:
            return

        self._cleanup_task_started = True

        async def cleanup_loop():
            while True:
                await asyncio.sleep(3600)  # Jede Stunde
                await self.cleanup_old_errors()

        asyncio.create_task(cleanup_loop())
        logger.info("error_cleanup_task_started")

    def reset_stats(self, category: Optional[ErrorCategory] = None) -> None:
        """
        Setze Statistiken zurueck.

        Args:
            category: Optional spezifische Kategorie, sonst alle
        """
        with self._stats_lock:
            if category:
                self._stats[category] = ErrorStats()
            else:
                self._stats = {cat: ErrorStats() for cat in ErrorCategory}

        with self._buffer_lock:
            if category:
                self._error_buffer = [
                    e for e in self._error_buffer
                    if e.category != category
                ]
            else:
                self._error_buffer.clear()

        logger.info("error_stats_reset", category=category.value if category else "all")

    def _sanitize_details(self, details: Dict[str, Any]) -> Dict[str, Any]:
        """Entferne sensible Daten aus Details."""
        sensitive_keys = {
            "password", "token", "secret", "key", "auth",
            "credential", "api_key", "access_token", "refresh_token",
            "ssn", "iban", "tax_id", "email", "phone",
        }

        safe = {}
        for key, value in details.items():
            key_lower = key.lower()
            if any(sensitive in key_lower for sensitive in sensitive_keys):
                continue  # Ueberspringen
            elif isinstance(value, dict):
                safe[key] = self._sanitize_details(value)
            elif isinstance(value, str) and len(value) > 200:
                safe[key] = value[:200] + "..."
            else:
                safe[key] = value

        return safe

    @staticmethod
    def _severity_to_log_level(severity: ErrorSeverity) -> str:
        """Konvertiere Severity zu structlog Level."""
        mapping = {
            ErrorSeverity.DEBUG: "debug",
            ErrorSeverity.INFO: "info",
            ErrorSeverity.WARNING: "warning",
            ErrorSeverity.ERROR: "error",
            ErrorSeverity.CRITICAL: "critical",
        }
        return mapping.get(severity, "error")


# =============================================================================
# SINGLETON ACCESSOR
# =============================================================================


_error_tracking_service: Optional[ErrorTrackingService] = None


def get_error_tracking_service() -> ErrorTrackingService:
    """Hole Error Tracking Service Singleton."""
    global _error_tracking_service
    if _error_tracking_service is None:
        _error_tracking_service = ErrorTrackingService()
    return _error_tracking_service


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================


def track_error(
    category: ErrorCategory,
    error_type: str,
    message: str,
    severity: ErrorSeverity = ErrorSeverity.ERROR,
    **kwargs,
) -> None:
    """
    Convenience-Funktion zum Tracken von Fehlern.

    Usage:
        from app.services.error_tracking_service import track_error, ErrorCategory

        track_error(
            ErrorCategory.OCR,
            "OCRProcessingError",
            "OCR failed for document",
            path="/api/v1/ocr/process",
        )
    """
    service = get_error_tracking_service()
    service.track_error(
        category=category,
        error_type=error_type,
        message=message,
        severity=severity,
        **kwargs,
    )


def track_ocr_error(error_type: str, message: str, **kwargs) -> None:
    """Track OCR-spezifischen Fehler."""
    track_error(ErrorCategory.OCR, error_type, message, **kwargs)


def track_gpu_error(error_type: str, message: str, **kwargs) -> None:
    """Track GPU-spezifischen Fehler."""
    track_error(ErrorCategory.GPU, error_type, message, ErrorSeverity.WARNING, **kwargs)


def track_auth_error(error_type: str, message: str, **kwargs) -> None:
    """Track Auth-spezifischen Fehler."""
    track_error(ErrorCategory.AUTH, error_type, message, ErrorSeverity.WARNING, **kwargs)


def track_db_error(error_type: str, message: str, **kwargs) -> None:
    """Track Database-spezifischen Fehler."""
    track_error(ErrorCategory.DATABASE, error_type, message, ErrorSeverity.ERROR, **kwargs)
