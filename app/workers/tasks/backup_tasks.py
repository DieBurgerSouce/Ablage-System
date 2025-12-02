# -*- coding: utf-8 -*-
"""
Celery Tasks fuer automatisierte Backups.

Geplante Tasks:
- backup_full_task: Taegliches vollstaendiges Backup (02:00 Uhr)
- apply_retention_task: Woechentliche Retention Policy (Sonntag 03:00)
- sync_to_remote_task: Taegliche Remote-Synchronisation (04:00 Uhr)

Feinpoliert und durchdacht - Automatisierte Backups in Produktion.
"""

import asyncio
from typing import Any, Dict, List

import structlog

from app.workers.celery_app import celery_app, CPUTask

logger = structlog.get_logger(__name__)


def run_async(coro):
    """Hilfsfunktion um async Code in sync Celery Tasks auszufuehren.

    MEMORY FIX: Verwendet asyncio.run() statt new_event_loop() um Memory Leaks
    zu verhindern. asyncio.run() erstellt einen neuen Event-Loop, fuehrt die
    Coroutine aus und schließt den Loop korrekt inkl. aller pending Tasks.
    """
    return asyncio.run(coro)


@celery_app.task(
    bind=True,
    base=CPUTask,
    name="app.workers.tasks.backup_tasks.backup_full_task",
    max_retries=3,
    default_retry_delay=300,  # 5 Minuten
)
def backup_full_task(self) -> Dict[str, Any]:
    """
    Celery Task fuer vollstaendiges Backup.

    Erstellt Backups fuer:
    - PostgreSQL
    - Redis
    - MinIO
    - Konfiguration

    Returns:
        Dict mit Backup-Ergebnissen
    """
    logger.info("backup_full_task_gestartet", task_id=self.request.id)

    try:
        # Lazy import um zirkulaere Imports zu vermeiden
        from app.services.backup_service import get_backup_service

        service = get_backup_service()

        async def run_backup():
            return await service.backup_full()

        results = run_async(run_backup())

        # Ergebnisse in serialisierbares Format umwandeln
        response = {
            "erfolg": all(r.success for r in results),
            "erfolgreich": sum(1 for r in results if r.success),
            "fehlgeschlagen": sum(1 for r in results if not r.success),
            "details": [
                {
                    "typ": r.backup_type,
                    "erfolg": r.success,
                    "pfad": str(r.path) if r.path else None,
                    "groesse_mb": round(r.size_bytes / 1024 / 1024, 2) if r.size_bytes else 0,
                    "fehler": r.error,
                }
                for r in results
            ],
        }

        logger.info(
            "backup_full_task_abgeschlossen",
            task_id=self.request.id,
            erfolgreich=response["erfolgreich"],
            fehlgeschlagen=response["fehlgeschlagen"],
        )

        return response

    except Exception as e:
        logger.exception("backup_full_task_fehler", task_id=self.request.id)
        # Retry bei transientem Fehler
        raise self.retry(exc=e)


@celery_app.task(
    bind=True,
    base=CPUTask,
    name="app.workers.tasks.backup_tasks.backup_postgres_task",
)
def backup_postgres_task(self) -> Dict[str, Any]:
    """Celery Task fuer PostgreSQL-Backup."""
    logger.info("backup_postgres_task_gestartet", task_id=self.request.id)

    try:
        from app.services.backup_service import get_backup_service

        service = get_backup_service()

        async def run_backup():
            return await service.backup_postgres()

        result = run_async(run_backup())

        response = {
            "erfolg": result.success,
            "typ": result.backup_type,
            "pfad": str(result.path) if result.path else None,
            "groesse_mb": round(result.size_bytes / 1024 / 1024, 2) if result.size_bytes else 0,
            "fehler": result.error,
        }

        logger.info("backup_postgres_task_abgeschlossen", task_id=self.request.id, erfolg=result.success)
        return response

    except Exception as e:
        logger.exception("backup_postgres_task_fehler", task_id=self.request.id)
        raise self.retry(exc=e)


@celery_app.task(
    bind=True,
    base=CPUTask,
    name="app.workers.tasks.backup_tasks.backup_redis_task",
)
def backup_redis_task(self) -> Dict[str, Any]:
    """Celery Task fuer Redis-Backup."""
    logger.info("backup_redis_task_gestartet", task_id=self.request.id)

    try:
        from app.services.backup_service import get_backup_service

        service = get_backup_service()

        async def run_backup():
            return await service.backup_redis()

        result = run_async(run_backup())

        response = {
            "erfolg": result.success,
            "typ": result.backup_type,
            "pfad": str(result.path) if result.path else None,
            "groesse_mb": round(result.size_bytes / 1024 / 1024, 2) if result.size_bytes else 0,
            "fehler": result.error,
        }

        logger.info("backup_redis_task_abgeschlossen", task_id=self.request.id, erfolg=result.success)
        return response

    except Exception as e:
        logger.exception("backup_redis_task_fehler", task_id=self.request.id)
        raise self.retry(exc=e)


@celery_app.task(
    bind=True,
    base=CPUTask,
    name="app.workers.tasks.backup_tasks.apply_retention_task",
)
def apply_retention_task(self) -> Dict[str, Any]:
    """
    Celery Task fuer Retention Policy.

    Loescht alte Backups gemaess konfigurierter Aufbewahrungsdauer.

    Returns:
        Dict mit Anzahl geloeschter Dateien
    """
    logger.info("retention_task_gestartet", task_id=self.request.id)

    try:
        from app.services.backup_service import get_backup_service

        service = get_backup_service()

        async def run_retention():
            return await service.apply_retention_policy()

        deleted = run_async(run_retention())
        total = sum(deleted.values())

        response = {
            "erfolg": True,
            "geloescht_gesamt": total,
            "details": deleted,
        }

        logger.info(
            "retention_task_abgeschlossen",
            task_id=self.request.id,
            geloescht=total,
        )

        return response

    except Exception as e:
        logger.exception("retention_task_fehler", task_id=self.request.id)
        raise


@celery_app.task(
    bind=True,
    base=CPUTask,
    name="app.workers.tasks.backup_tasks.sync_to_remote_task",
    max_retries=3,
    default_retry_delay=600,  # 10 Minuten
)
def sync_to_remote_task(self) -> Dict[str, Any]:
    """
    Celery Task fuer Remote-Synchronisation.

    Synchronisiert lokale Backups zum konfigurierten Remote-Server.

    Returns:
        Dict mit Sync-Status
    """
    logger.info("sync_to_remote_task_gestartet", task_id=self.request.id)

    try:
        from app.services.backup_service import get_backup_service

        service = get_backup_service()

        if not service.config.remote_enabled:
            logger.info("remote_sync_deaktiviert", task_id=self.request.id)
            return {
                "erfolg": True,
                "nachricht": "Remote-Sync ist deaktiviert.",
                "synchronisiert": False,
            }

        async def run_sync():
            return await service.sync_to_remote()

        success = run_async(run_sync())

        response = {
            "erfolg": success,
            "synchronisiert": success,
            "ziel": service.config.remote_target if success else None,
            "nachricht": "Synchronisation erfolgreich." if success else "Synchronisation fehlgeschlagen.",
        }

        logger.info(
            "sync_to_remote_task_abgeschlossen",
            task_id=self.request.id,
            erfolg=success,
        )

        return response

    except Exception as e:
        logger.exception("sync_to_remote_task_fehler", task_id=self.request.id)
        raise self.retry(exc=e)


@celery_app.task(
    bind=True,
    base=CPUTask,
    name="app.workers.tasks.backup_tasks.update_backup_metrics_task",
)
def update_backup_metrics_task(self) -> Dict[str, Any]:
    """
    Celery Task fuer Backup-Metriken-Aktualisierung.

    Aktualisiert Speicherplatz- und Dateizaehl-Metriken.

    Returns:
        Dict mit aktuellen Metriken
    """
    logger.info("backup_metrics_task_gestartet", task_id=self.request.id)

    try:
        from app.services.backup_service import get_backup_service

        service = get_backup_service()
        metrics = service.metrics

        disk_usage = metrics.update_disk_usage()
        file_counts = metrics.update_backup_file_counts()

        response = {
            "erfolg": True,
            "speicherplatz": {
                "total_gb": round(disk_usage.total_bytes / 1024 / 1024 / 1024, 2),
                "frei_gb": round(disk_usage.free_bytes / 1024 / 1024 / 1024, 2),
                "verwendung_prozent": round(disk_usage.usage_percent, 1),
            },
            "dateien": file_counts,
        }

        logger.info(
            "backup_metrics_task_abgeschlossen",
            task_id=self.request.id,
        )

        return response

    except Exception as e:
        logger.exception("backup_metrics_task_fehler", task_id=self.request.id)
        raise
