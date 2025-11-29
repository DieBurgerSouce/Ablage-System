# -*- coding: utf-8 -*-
"""
Prometheus Metriken fuer Backup-Service.

Erfasst:
- Backup-Erfolge und -Fehler
- Backup-Dauer und -Groesse
- Validierungs-Status
- Remote-Synchronisation
- Speicherplatz-Nutzung

Feinpoliert und durchdacht - Observability fuer Backups in Produktion.
"""

import os
import shutil
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from functools import wraps
from pathlib import Path
from typing import Callable, Dict, Optional

import structlog

logger = structlog.get_logger(__name__)

# Thread-Safety fuer Singleton
_backup_metrics_lock = threading.Lock()

# Optional Prometheus integration
PROMETHEUS_AVAILABLE = False
try:
    from prometheus_client import (
        CONTENT_TYPE_LATEST,
        CollectorRegistry,
        Counter,
        Gauge,
        Histogram,
        generate_latest,
    )

    PROMETHEUS_AVAILABLE = True
except ImportError:
    logger.info("prometheus_client nicht installiert - Backup-Metriken deaktiviert")


# =============================================================================
# Metric Definitions
# =============================================================================

if PROMETHEUS_AVAILABLE:
    # Registry fuer alle Backup-Metriken
    BACKUP_REGISTRY = CollectorRegistry()

    # -------------------------------------------------------------------------
    # Backup-Status Metriken
    # -------------------------------------------------------------------------

    BACKUP_LAST_SUCCESS_TIMESTAMP = Gauge(
        "ablage_backup_last_success_timestamp",
        "Unix-Zeitstempel des letzten erfolgreichen Backups",
        ["backup_type"],  # postgres, redis, minio, config, full
        registry=BACKUP_REGISTRY,
    )

    BACKUP_LAST_FAILURE_TIMESTAMP = Gauge(
        "ablage_backup_last_failure_timestamp",
        "Unix-Zeitstempel des letzten fehlgeschlagenen Backups",
        ["backup_type"],
        registry=BACKUP_REGISTRY,
    )

    BACKUP_SUCCESS_TOTAL = Counter(
        "ablage_backup_success_total",
        "Gesamtzahl erfolgreicher Backups",
        ["backup_type"],
        registry=BACKUP_REGISTRY,
    )

    BACKUP_FAILURE_TOTAL = Counter(
        "ablage_backup_failure_total",
        "Gesamtzahl fehlgeschlagener Backups",
        ["backup_type"],
        registry=BACKUP_REGISTRY,
    )

    # -------------------------------------------------------------------------
    # Backup-Performance Metriken
    # -------------------------------------------------------------------------

    BACKUP_DURATION_SECONDS = Histogram(
        "ablage_backup_duration_seconds",
        "Dauer des Backups in Sekunden",
        ["backup_type"],
        buckets=[10, 30, 60, 120, 300, 600, 1200, 1800, 3600],
        registry=BACKUP_REGISTRY,
    )

    BACKUP_SIZE_BYTES = Gauge(
        "ablage_backup_size_bytes",
        "Groesse des Backups in Bytes",
        ["backup_type"],
        registry=BACKUP_REGISTRY,
    )

    # -------------------------------------------------------------------------
    # Validierungs-Metriken
    # -------------------------------------------------------------------------

    BACKUP_VALIDATION_SUCCESS_TOTAL = Counter(
        "ablage_backup_validation_success_total",
        "Erfolgreiche Backup-Validierungen",
        registry=BACKUP_REGISTRY,
    )

    BACKUP_VALIDATION_FAILURE_TOTAL = Counter(
        "ablage_backup_validation_failure_total",
        "Fehlgeschlagene Backup-Validierungen",
        registry=BACKUP_REGISTRY,
    )

    BACKUP_VALIDATION_LAST_RUN_TIMESTAMP = Gauge(
        "ablage_backup_validation_last_run_timestamp",
        "Zeitstempel der letzten Validierung",
        registry=BACKUP_REGISTRY,
    )

    BACKUP_VALIDATION_DURATION_SECONDS = Histogram(
        "ablage_backup_validation_duration_seconds",
        "Dauer der Backup-Validierung in Sekunden",
        buckets=[5, 10, 30, 60, 120, 300, 600],
        registry=BACKUP_REGISTRY,
    )

    # -------------------------------------------------------------------------
    # Wiederherstellungs-Test Metriken
    # -------------------------------------------------------------------------

    BACKUP_RESTORE_TEST_SUCCESS_TOTAL = Counter(
        "ablage_backup_restore_test_success_total",
        "Erfolgreiche Wiederherstellungstests",
        registry=BACKUP_REGISTRY,
    )

    BACKUP_RESTORE_TEST_FAILURE_TOTAL = Counter(
        "ablage_backup_restore_test_failure_total",
        "Fehlgeschlagene Wiederherstellungstests",
        registry=BACKUP_REGISTRY,
    )

    BACKUP_RESTORE_TEST_LAST_RUN_TIMESTAMP = Gauge(
        "ablage_backup_restore_test_last_run_timestamp",
        "Zeitstempel des letzten Wiederherstellungstests",
        registry=BACKUP_REGISTRY,
    )

    # -------------------------------------------------------------------------
    # Remote-Synchronisation Metriken
    # -------------------------------------------------------------------------

    BACKUP_REMOTE_SYNC_SUCCESS_TOTAL = Counter(
        "ablage_backup_remote_sync_success_total",
        "Erfolgreiche Remote-Synchronisationen",
        registry=BACKUP_REGISTRY,
    )

    BACKUP_REMOTE_SYNC_FAILURE_TOTAL = Counter(
        "ablage_backup_remote_sync_failure_total",
        "Fehlgeschlagene Remote-Synchronisationen",
        registry=BACKUP_REGISTRY,
    )

    BACKUP_REMOTE_SYNC_RETRY_TOTAL = Counter(
        "ablage_backup_remote_sync_retry_total",
        "Wiederholungsversuche der Remote-Synchronisation",
        registry=BACKUP_REGISTRY,
    )

    BACKUP_REMOTE_SYNC_DURATION_SECONDS = Histogram(
        "ablage_backup_remote_sync_duration_seconds",
        "Dauer der Remote-Synchronisation in Sekunden",
        buckets=[30, 60, 120, 300, 600, 1200, 1800],
        registry=BACKUP_REGISTRY,
    )

    # -------------------------------------------------------------------------
    # Speicherplatz Metriken
    # -------------------------------------------------------------------------

    BACKUP_DISK_USAGE_BYTES = Gauge(
        "ablage_backup_disk_usage_bytes",
        "Verwendeter Speicherplatz fuer Backups in Bytes",
        registry=BACKUP_REGISTRY,
    )

    BACKUP_DISK_FREE_BYTES = Gauge(
        "ablage_backup_disk_free_bytes",
        "Verfuegbarer Speicherplatz fuer Backups in Bytes",
        registry=BACKUP_REGISTRY,
    )

    BACKUP_DISK_TOTAL_BYTES = Gauge(
        "ablage_backup_disk_total_bytes",
        "Gesamter Speicherplatz fuer Backups in Bytes",
        registry=BACKUP_REGISTRY,
    )

    BACKUP_FILE_COUNT = Gauge(
        "ablage_backup_file_count",
        "Anzahl der Backup-Dateien",
        ["backup_type"],
        registry=BACKUP_REGISTRY,
    )

    # -------------------------------------------------------------------------
    # Verschluesselungs-Metriken
    # -------------------------------------------------------------------------

    BACKUP_ENCRYPTION_ENABLED = Gauge(
        "ablage_backup_encryption_enabled",
        "Ist Backup-Verschluesselung aktiviert (1=ja, 0=nein)",
        registry=BACKUP_REGISTRY,
    )

    BACKUP_ENCRYPTION_SUCCESS_TOTAL = Counter(
        "ablage_backup_encryption_success_total",
        "Erfolgreiche Backup-Verschluesselungen",
        registry=BACKUP_REGISTRY,
    )

    BACKUP_ENCRYPTION_FAILURE_TOTAL = Counter(
        "ablage_backup_encryption_failure_total",
        "Fehlgeschlagene Backup-Verschluesselungen",
        registry=BACKUP_REGISTRY,
    )


# =============================================================================
# Data Classes
# =============================================================================


@dataclass
class BackupMetricData:
    """Daten fuer Backup-Metriken."""

    backup_type: str
    success: bool
    duration_seconds: float
    size_bytes: int
    timestamp: datetime
    error_message: Optional[str] = None


@dataclass
class DiskUsageData:
    """Speicherplatz-Informationen."""

    total_bytes: int
    used_bytes: int
    free_bytes: int
    usage_percent: float


# =============================================================================
# BackupMetrics Class
# =============================================================================


class BackupMetrics:
    """
    Zentrale Klasse fuer Backup-Metriken.

    Kapselt alle Prometheus-Operationen und bietet
    Fallback wenn Prometheus nicht verfuegbar.
    """

    def __init__(self, backup_dir: Optional[str] = None) -> None:
        """
        Initialisiere BackupMetrics.

        Args:
            backup_dir: Pfad zum Backup-Verzeichnis fuer Speicherplatz-Metriken
        """
        self.enabled = PROMETHEUS_AVAILABLE
        self.backup_dir = backup_dir or os.getenv("BACKUP_DIR", "/var/backups/ablage")

        if self.enabled:
            logger.info("Prometheus Backup-Metriken aktiviert")
        else:
            logger.info("Prometheus nicht verfuegbar - Metriken nur als Logs")

    # -------------------------------------------------------------------------
    # Backup-Operationen
    # -------------------------------------------------------------------------

    def record_backup_success(
        self,
        backup_type: str,
        duration_seconds: float,
        size_bytes: int,
    ) -> None:
        """
        Erfasse erfolgreiches Backup.

        Args:
            backup_type: postgres, redis, minio, config, full
            duration_seconds: Dauer in Sekunden
            size_bytes: Groesse in Bytes
        """
        now = time.time()

        if self.enabled:
            BACKUP_SUCCESS_TOTAL.labels(backup_type=backup_type).inc()
            BACKUP_LAST_SUCCESS_TIMESTAMP.labels(backup_type=backup_type).set(now)
            BACKUP_DURATION_SECONDS.labels(backup_type=backup_type).observe(
                duration_seconds
            )
            BACKUP_SIZE_BYTES.labels(backup_type=backup_type).set(size_bytes)

        logger.info(
            "backup_erfolgreich",
            backup_type=backup_type,
            duration_s=round(duration_seconds, 2),
            size_mb=round(size_bytes / 1024 / 1024, 2),
        )

    def record_backup_failure(
        self,
        backup_type: str,
        duration_seconds: float,
        error_message: str,
    ) -> None:
        """
        Erfasse fehlgeschlagenes Backup.

        Args:
            backup_type: postgres, redis, minio, config, full
            duration_seconds: Dauer bis zum Fehler
            error_message: Fehlerbeschreibung
        """
        now = time.time()

        if self.enabled:
            BACKUP_FAILURE_TOTAL.labels(backup_type=backup_type).inc()
            BACKUP_LAST_FAILURE_TIMESTAMP.labels(backup_type=backup_type).set(now)
            BACKUP_DURATION_SECONDS.labels(backup_type=backup_type).observe(
                duration_seconds
            )

        logger.error(
            "backup_fehlgeschlagen",
            backup_type=backup_type,
            duration_s=round(duration_seconds, 2),
            error=error_message,
        )

    @contextmanager
    def measure_backup(self, backup_type: str):
        """
        Context Manager zur Zeitmessung von Backups.

        Args:
            backup_type: postgres, redis, minio, config, full

        Yields:
            Dict zum Speichern von Zusatzinformationen (size_bytes)
        """
        start = time.time()
        context: Dict[str, int] = {"size_bytes": 0}
        success = True
        error_msg = ""

        try:
            yield context
        except Exception as e:
            success = False
            error_msg = str(e)
            raise
        finally:
            duration = time.time() - start
            if success:
                self.record_backup_success(
                    backup_type=backup_type,
                    duration_seconds=duration,
                    size_bytes=context.get("size_bytes", 0),
                )
            else:
                self.record_backup_failure(
                    backup_type=backup_type,
                    duration_seconds=duration,
                    error_message=error_msg,
                )

    # -------------------------------------------------------------------------
    # Validierung
    # -------------------------------------------------------------------------

    def record_validation_success(self, duration_seconds: float) -> None:
        """
        Erfasse erfolgreiche Backup-Validierung.

        Args:
            duration_seconds: Dauer der Validierung
        """
        now = time.time()

        if self.enabled:
            BACKUP_VALIDATION_SUCCESS_TOTAL.inc()
            BACKUP_VALIDATION_LAST_RUN_TIMESTAMP.set(now)
            BACKUP_VALIDATION_DURATION_SECONDS.observe(duration_seconds)

        logger.info(
            "backup_validierung_erfolgreich",
            duration_s=round(duration_seconds, 2),
        )

    def record_validation_failure(
        self, duration_seconds: float, error_message: str
    ) -> None:
        """
        Erfasse fehlgeschlagene Backup-Validierung.

        Args:
            duration_seconds: Dauer bis zum Fehler
            error_message: Fehlerbeschreibung
        """
        now = time.time()

        if self.enabled:
            BACKUP_VALIDATION_FAILURE_TOTAL.inc()
            BACKUP_VALIDATION_LAST_RUN_TIMESTAMP.set(now)
            BACKUP_VALIDATION_DURATION_SECONDS.observe(duration_seconds)

        logger.error(
            "backup_validierung_fehlgeschlagen",
            duration_s=round(duration_seconds, 2),
            error=error_message,
        )

    @contextmanager
    def measure_validation(self):
        """Context Manager zur Zeitmessung von Validierungen."""
        start = time.time()
        success = True
        error_msg = ""

        try:
            yield
        except Exception as e:
            success = False
            error_msg = str(e)
            raise
        finally:
            duration = time.time() - start
            if success:
                self.record_validation_success(duration)
            else:
                self.record_validation_failure(duration, error_msg)

    # -------------------------------------------------------------------------
    # Wiederherstellungs-Test
    # -------------------------------------------------------------------------

    def record_restore_test_success(self) -> None:
        """Erfasse erfolgreichen Wiederherstellungstest."""
        now = time.time()

        if self.enabled:
            BACKUP_RESTORE_TEST_SUCCESS_TOTAL.inc()
            BACKUP_RESTORE_TEST_LAST_RUN_TIMESTAMP.set(now)

        logger.info("wiederherstellungstest_erfolgreich")

    def record_restore_test_failure(self, error_message: str) -> None:
        """
        Erfasse fehlgeschlagenen Wiederherstellungstest.

        Args:
            error_message: Fehlerbeschreibung
        """
        now = time.time()

        if self.enabled:
            BACKUP_RESTORE_TEST_FAILURE_TOTAL.inc()
            BACKUP_RESTORE_TEST_LAST_RUN_TIMESTAMP.set(now)

        logger.error(
            "wiederherstellungstest_fehlgeschlagen",
            error=error_message,
        )

    # -------------------------------------------------------------------------
    # Remote-Synchronisation
    # -------------------------------------------------------------------------

    def record_remote_sync_success(self, duration_seconds: float) -> None:
        """
        Erfasse erfolgreiche Remote-Synchronisation.

        Args:
            duration_seconds: Dauer der Synchronisation
        """
        if self.enabled:
            BACKUP_REMOTE_SYNC_SUCCESS_TOTAL.inc()
            BACKUP_REMOTE_SYNC_DURATION_SECONDS.observe(duration_seconds)

        logger.info(
            "remote_sync_erfolgreich",
            duration_s=round(duration_seconds, 2),
        )

    def record_remote_sync_failure(self, error_message: str) -> None:
        """
        Erfasse fehlgeschlagene Remote-Synchronisation.

        Args:
            error_message: Fehlerbeschreibung
        """
        if self.enabled:
            BACKUP_REMOTE_SYNC_FAILURE_TOTAL.inc()

        logger.error(
            "remote_sync_fehlgeschlagen",
            error=error_message,
        )

    def record_remote_sync_retry(self, attempt: int, max_attempts: int) -> None:
        """
        Erfasse Wiederholungsversuch der Remote-Synchronisation.

        Args:
            attempt: Aktueller Versuch
            max_attempts: Maximale Versuche
        """
        if self.enabled:
            BACKUP_REMOTE_SYNC_RETRY_TOTAL.inc()

        logger.warning(
            "remote_sync_wiederholung",
            versuch=attempt,
            max_versuche=max_attempts,
        )

    @contextmanager
    def measure_remote_sync(self):
        """Context Manager zur Zeitmessung von Remote-Synchronisation."""
        start = time.time()
        success = True
        error_msg = ""

        try:
            yield
        except Exception as e:
            success = False
            error_msg = str(e)
            raise
        finally:
            duration = time.time() - start
            if success:
                self.record_remote_sync_success(duration)
            else:
                self.record_remote_sync_failure(error_msg)

    # -------------------------------------------------------------------------
    # Speicherplatz
    # -------------------------------------------------------------------------

    def update_disk_usage(self, path: Optional[str] = None) -> DiskUsageData:
        """
        Aktualisiere Speicherplatz-Metriken.

        Args:
            path: Pfad zum Backup-Verzeichnis (optional)

        Returns:
            DiskUsageData mit aktuellen Werten
        """
        target_path = path or self.backup_dir

        try:
            usage = shutil.disk_usage(target_path)
            data = DiskUsageData(
                total_bytes=usage.total,
                used_bytes=usage.used,
                free_bytes=usage.free,
                usage_percent=(usage.used / usage.total * 100) if usage.total > 0 else 0,
            )

            if self.enabled:
                BACKUP_DISK_TOTAL_BYTES.set(data.total_bytes)
                BACKUP_DISK_USAGE_BYTES.set(data.used_bytes)
                BACKUP_DISK_FREE_BYTES.set(data.free_bytes)

            logger.debug(
                "speicherplatz_aktualisiert",
                total_gb=round(data.total_bytes / 1024 / 1024 / 1024, 2),
                frei_gb=round(data.free_bytes / 1024 / 1024 / 1024, 2),
                verwendung_prozent=round(data.usage_percent, 1),
            )

            return data

        except OSError as e:
            logger.error("speicherplatz_fehler", path=target_path, error=str(e))
            return DiskUsageData(
                total_bytes=0, used_bytes=0, free_bytes=0, usage_percent=0
            )

    def update_backup_file_counts(self, backup_dir: Optional[str] = None) -> Dict[str, int]:
        """
        Zaehle Backup-Dateien nach Typ.

        Args:
            backup_dir: Pfad zum Backup-Verzeichnis

        Returns:
            Dict mit Anzahl pro Backup-Typ
        """
        target_dir = Path(backup_dir or self.backup_dir)
        counts: Dict[str, int] = {
            "postgres": 0,
            "redis": 0,
            "minio": 0,
            "config": 0,
        }

        try:
            if (target_dir / "postgres").exists():
                counts["postgres"] = len(list((target_dir / "postgres").glob("*.sql.gz")))
            if (target_dir / "redis").exists():
                counts["redis"] = len(list((target_dir / "redis").glob("*.rdb")))
            if (target_dir / "minio").exists():
                counts["minio"] = len(list((target_dir / "minio").iterdir()))
            if (target_dir / "config").exists():
                counts["config"] = len(list((target_dir / "config").glob("*.tar.gz")))

            if self.enabled:
                for backup_type, count in counts.items():
                    BACKUP_FILE_COUNT.labels(backup_type=backup_type).set(count)

            logger.debug("backup_dateien_gezaehlt", counts=counts)

        except OSError as e:
            logger.error("backup_zaehlung_fehler", error=str(e))

        return counts

    # -------------------------------------------------------------------------
    # Verschluesselung
    # -------------------------------------------------------------------------

    def set_encryption_enabled(self, enabled: bool) -> None:
        """
        Setze Status der Backup-Verschluesselung.

        Args:
            enabled: Ist Verschluesselung aktiviert?
        """
        if self.enabled:
            BACKUP_ENCRYPTION_ENABLED.set(1 if enabled else 0)

        logger.info("verschluesselung_status", aktiviert=enabled)

    def record_encryption_success(self) -> None:
        """Erfasse erfolgreiche Verschluesselung."""
        if self.enabled:
            BACKUP_ENCRYPTION_SUCCESS_TOTAL.inc()

        logger.debug("verschluesselung_erfolgreich")

    def record_encryption_failure(self, error_message: str) -> None:
        """
        Erfasse fehlgeschlagene Verschluesselung.

        Args:
            error_message: Fehlerbeschreibung
        """
        if self.enabled:
            BACKUP_ENCRYPTION_FAILURE_TOTAL.inc()

        logger.error("verschluesselung_fehlgeschlagen", error=error_message)

    # -------------------------------------------------------------------------
    # Export
    # -------------------------------------------------------------------------

    def get_metrics(self) -> bytes:
        """Hole alle Backup-Metriken als Prometheus-Format."""
        if self.enabled:
            return generate_latest(BACKUP_REGISTRY)
        else:
            return b"# Prometheus not available\n"

    def get_content_type(self) -> str:
        """Hole Content-Type fuer Metriken."""
        if self.enabled:
            return CONTENT_TYPE_LATEST
        else:
            return "text/plain"

    def get_summary(self) -> Dict[str, any]:
        """
        Hole Zusammenfassung aller Backup-Metriken als Dict.

        Nuetzlich fuer JSON-Endpunkte und Health-Checks.
        """
        disk_usage = self.update_disk_usage()
        file_counts = self.update_backup_file_counts()

        return {
            "speicherplatz": {
                "total_gb": round(disk_usage.total_bytes / 1024 / 1024 / 1024, 2),
                "verwendet_gb": round(disk_usage.used_bytes / 1024 / 1024 / 1024, 2),
                "frei_gb": round(disk_usage.free_bytes / 1024 / 1024 / 1024, 2),
                "verwendung_prozent": round(disk_usage.usage_percent, 1),
            },
            "backup_dateien": file_counts,
            "prometheus_aktiv": self.enabled,
        }


# =============================================================================
# Singleton Instance
# =============================================================================

_backup_metrics: Optional[BackupMetrics] = None


def get_backup_metrics(backup_dir: Optional[str] = None) -> BackupMetrics:
    """Hole globale BackupMetrics Instanz (thread-safe)."""
    global _backup_metrics
    if _backup_metrics is not None:
        return _backup_metrics
    with _backup_metrics_lock:
        if _backup_metrics is None:
            logger.info("backup_metrics_initialisierung")
            _backup_metrics = BackupMetrics(backup_dir=backup_dir)
    return _backup_metrics


# =============================================================================
# Decorators
# =============================================================================


def track_backup(backup_type: str = "unknown"):
    """
    Decorator zum Tracking von Backup-Funktionen.

    Args:
        backup_type: postgres, redis, minio, config, full
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            metrics = get_backup_metrics()
            start = time.time()
            size_bytes = 0
            success = True
            error_msg = ""

            try:
                result = await func(*args, **kwargs)

                # Versuche Groesse aus Ergebnis zu extrahieren
                if isinstance(result, dict) and "size_bytes" in result:
                    size_bytes = result["size_bytes"]
                elif isinstance(result, Path) and result.exists():
                    size_bytes = result.stat().st_size

                return result
            except Exception as e:
                success = False
                error_msg = str(e)
                raise
            finally:
                duration = time.time() - start
                if success:
                    metrics.record_backup_success(
                        backup_type=backup_type,
                        duration_seconds=duration,
                        size_bytes=size_bytes,
                    )
                else:
                    metrics.record_backup_failure(
                        backup_type=backup_type,
                        duration_seconds=duration,
                        error_message=error_msg,
                    )

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            metrics = get_backup_metrics()
            start = time.time()
            size_bytes = 0
            success = True
            error_msg = ""

            try:
                result = func(*args, **kwargs)

                if isinstance(result, dict) and "size_bytes" in result:
                    size_bytes = result["size_bytes"]
                elif isinstance(result, Path) and result.exists():
                    size_bytes = result.stat().st_size

                return result
            except Exception as e:
                success = False
                error_msg = str(e)
                raise
            finally:
                duration = time.time() - start
                if success:
                    metrics.record_backup_success(
                        backup_type=backup_type,
                        duration_seconds=duration,
                        size_bytes=size_bytes,
                    )
                else:
                    metrics.record_backup_failure(
                        backup_type=backup_type,
                        duration_seconds=duration,
                        error_message=error_msg,
                    )

        # Waehle Wrapper basierend auf Funktionstyp
        import asyncio

        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper

    return decorator
