# -*- coding: utf-8 -*-
"""
Celery Tasks fuer automatisierte Backups.

Geplante Tasks:
- backup_full_task: Taegliches vollstaendiges Backup (02:00 Uhr)
- apply_retention_task: Woechentliche Retention Policy (Sonntag 03:00)
- sync_to_remote_task: Taegliche Remote-Synchronisation (04:00 Uhr)

Phase 1.4: Audit Archive Tasks
- archive_audit_logs_monthly_task: Monatliche Audit-Log-Archivierung (1. des Monats 01:00)
- verify_audit_archives_task: Woechentliche Archiv-Verifikation (Samstag 04:00)

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


# ==================== Audit Archive Tasks (Phase 1.4) ====================

@celery_app.task(
    bind=True,
    base=CPUTask,
    name="app.workers.tasks.backup_tasks.archive_audit_logs_monthly_task",
    max_retries=3,
    default_retry_delay=3600,  # 1 Stunde
)
def archive_audit_logs_monthly_task(
    self,
    year: int = None,
    month: int = None,
) -> Dict[str, Any]:
    """
    Celery Task fuer monatliche Audit-Log-Archivierung.

    Archiviert Audit-Logs des Vormonats in MinIO WORM-Storage.
    Wird automatisch am 1. jedes Monats um 01:00 Uhr ausgefuehrt.

    Args:
        year: Jahr (default: Vormonat)
        month: Monat (default: Vormonat)

    Returns:
        Dict mit Archivierungsergebnis
    """
    from datetime import date

    logger.info("archive_audit_logs_monthly_task_gestartet", task_id=self.request.id)

    try:
        from app.db.session import get_async_session
        from app.services.compliance.audit_archive_service import archive_monthly_audit_logs

        # Bestimme Vormonat wenn nicht angegeben
        today = date.today()
        if year is None or month is None:
            if today.month == 1:
                year = today.year - 1
                month = 12
            else:
                year = today.year
                month = today.month - 1

        async def run_archive():
            async with get_async_session() as db:
                return await archive_monthly_audit_logs(db, year, month)

        result = run_async(run_archive())

        response = {
            "erfolg": True,
            "archiv_id": result.archive_id,
            "objekt_key": result.object_key,
            "eintraege": result.entries_archived,
            "start_sequenz": result.start_sequence,
            "end_sequenz": result.end_sequence,
            "content_hash": result.content_hash[:16] + "...",
            "aufbewahrung_bis": result.retention_until.isoformat(),
            "jahr": year,
            "monat": month,
        }

        logger.info(
            "archive_audit_logs_monthly_task_abgeschlossen",
            task_id=self.request.id,
            archiv_id=result.archive_id,
            eintraege=result.entries_archived,
        )

        return response

    except ValueError as e:
        # Keine Logs zum Archivieren
        logger.info(
            "archive_audit_logs_monthly_task_keine_logs",
            task_id=self.request.id,
            nachricht=str(e),
        )
        return {
            "erfolg": True,
            "nachricht": str(e),
            "archiviert": False,
        }

    except Exception as e:
        logger.exception("archive_audit_logs_monthly_task_fehler", task_id=self.request.id)
        raise self.retry(exc=e)


@celery_app.task(
    bind=True,
    base=CPUTask,
    name="app.workers.tasks.backup_tasks.verify_audit_archives_task",
)
def verify_audit_archives_task(
    self,
    year: int = None,
) -> Dict[str, Any]:
    """
    Celery Task fuer Audit-Archiv-Verifikation.

    Verifiziert alle Archive eines Jahres auf Integritaet.
    Wird woechentlich am Samstag um 04:00 Uhr ausgefuehrt.

    Args:
        year: Jahr (default: aktuelles Jahr)

    Returns:
        Dict mit Verifikationsergebnissen
    """
    from datetime import date

    logger.info("verify_audit_archives_task_gestartet", task_id=self.request.id)

    try:
        from app.services.compliance.audit_archive_service import verify_all_archives

        if year is None:
            year = date.today().year

        async def run_verification():
            return await verify_all_archives(year)

        results = run_async(run_verification())

        response = {
            "erfolg": results.get("valid", 0) == results.get("total_archives", 0),
            "jahr": year,
            "archive_gesamt": results.get("total_archives", 0),
            "verifiziert": results.get("verified", 0),
            "gueltig": results.get("valid", 0),
            "ungueltig": results.get("invalid", 0),
            "fehler": results.get("errors", [])[:5],  # Erste 5 Fehler
        }

        if results.get("invalid", 0) > 0:
            logger.warning(
                "verify_audit_archives_task_integritaetsfehler",
                task_id=self.request.id,
                ungueltig=results.get("invalid", 0),
            )
        else:
            logger.info(
                "verify_audit_archives_task_abgeschlossen",
                task_id=self.request.id,
                verifiziert=results.get("verified", 0),
            )

        return response

    except Exception as e:
        logger.exception("verify_audit_archives_task_fehler", task_id=self.request.id)
        raise


@celery_app.task(
    bind=True,
    base=CPUTask,
    name="app.workers.tasks.backup_tasks.get_audit_archive_statistics_task",
)
def get_audit_archive_statistics_task(self) -> Dict[str, Any]:
    """
    Celery Task fuer Audit-Archiv-Statistiken.

    Holt aktuelle Statistiken ueber alle archivierten Audit-Logs.

    Returns:
        Dict mit Archiv-Statistiken
    """
    logger.info("get_audit_archive_statistics_task_gestartet", task_id=self.request.id)

    try:
        from app.services.compliance.audit_archive_service import audit_archive_service

        async def run_stats():
            return await audit_archive_service.get_archive_statistics()

        stats = run_async(run_stats())

        logger.info(
            "get_audit_archive_statistics_task_abgeschlossen",
            task_id=self.request.id,
            archive_gesamt=stats.get("total_archives", 0),
        )

        return stats

    except Exception as e:
        logger.exception("get_audit_archive_statistics_task_fehler", task_id=self.request.id)
        return {
            "erfolg": False,
            "fehler": str(e),
        }


# ==================== Backup Restore Test Tasks (Phase 2.3) ====================

@celery_app.task(
    bind=True,
    base=CPUTask,
    name="app.workers.tasks.backup_tasks.backup_restore_test_task",
    max_retries=1,
    default_retry_delay=3600,  # 1 Stunde
)
def backup_restore_test_task(
    self,
    validation_level: str = "standard",
    cleanup_on_success: bool = True,
    cleanup_on_failure: bool = False,
) -> Dict[str, Any]:
    """
    Celery Task fuer automatisierte Backup-Restore-Tests.

    Validiert Backups durch:
    - Restore in temporaere Datenbank
    - Schema-Verifikation
    - Record-Count-Vergleich
    - Daten-Stichproben-Validierung

    Wird woechentlich am Sonntag um 02:00 Uhr ausgefuehrt.

    Args:
        validation_level: Validierungs-Level (minimal, standard, full)
        cleanup_on_success: Temp-DB nach erfolgreichem Test loeschen
        cleanup_on_failure: Temp-DB nach fehlgeschlagenem Test loeschen

    Returns:
        Dict mit Test-Ergebnis
    """
    logger.info(
        "backup_restore_test_task_gestartet",
        task_id=self.request.id,
        validation_level=validation_level,
    )

    try:
        from app.services.backup_restore_test_service import (
            get_backup_restore_test_service,
            ValidationLevel,
        )

        service = get_backup_restore_test_service()

        # Parse validation level
        level_map = {
            "minimal": ValidationLevel.MINIMAL,
            "standard": ValidationLevel.STANDARD,
            "full": ValidationLevel.THOROUGH,  # "full" ist Alias fuer THOROUGH
            "thorough": ValidationLevel.THOROUGH,
        }
        level = level_map.get(validation_level, ValidationLevel.STANDARD)

        async def run_test():
            return await service.run_restore_test(
                backup_path=None,  # Verwendet neuestes Backup
                validation_level=level,
                cleanup_on_success=cleanup_on_success,
                cleanup_on_failure=cleanup_on_failure,
            )

        result = run_async(run_test())

        # Schema-Validierung Zusammenfassung
        schema_passed = sum(1 for s in result.schema_results if s.column_match)
        schema_failed = [s.table_name for s in result.schema_results if not s.column_match]

        # Record-Count Zusammenfassung
        record_total = sum(r.source_count for r in result.record_count_results)
        record_matched = sum(1 for r in result.record_count_results if r.match)

        response = {
            "erfolg": result.passed,
            "status": result.status.value,
            "backup_pfad": result.backup_file or None,
            "temp_db": result.temp_db_name,
            "beginn": result.started_at.isoformat() if result.started_at else None,
            "ende": result.completed_at.isoformat() if result.completed_at else None,
            "dauer_sekunden": result.duration_seconds,
            "schema_validierung": {
                "erfolg": schema_passed == len(result.schema_results),
                "tabellen_geprueft": len(result.schema_results),
                "tabellen_bestanden": schema_passed,
                "fehlende_tabellen": schema_failed,
            } if result.schema_results else None,
            "record_counts": {
                "erfolg": record_matched == len(result.record_count_results),
                "tabellen_geprueft": len(result.record_count_results),
                "tabellen_match": record_matched,
                "total_records": record_total,
            } if result.record_count_results else None,
            "zusammenfassung": {
                "tabellen_geprueft": result.tables_checked,
                "tabellen_bestanden": result.tables_passed,
                "tabellen_fehlgeschlagen": result.tables_failed,
                "record_match_rate": round(result.record_match_rate, 2),
            },
            "fehler": result.errors[:5] if result.errors else [],  # Erste 5 Fehler
            "validation_level": validation_level,
        }

        if result.passed:
            logger.info(
                "backup_restore_test_task_erfolgreich",
                task_id=self.request.id,
                dauer_sekunden=result.duration_seconds,
            )
        else:
            logger.warning(
                "backup_restore_test_task_fehlgeschlagen",
                task_id=self.request.id,
                status=result.status.value,
                fehler_anzahl=len(result.errors) if result.errors else 0,
            )
            # Benachrichtigung bei Fehler
            async def notify():
                await service.notify_on_failure(result)
            run_async(notify())

        return response

    except FileNotFoundError as e:
        logger.warning(
            "backup_restore_test_task_kein_backup",
            task_id=self.request.id,
            nachricht=str(e),
        )
        return {
            "erfolg": False,
            "status": "no_backup_found",
            "nachricht": str(e),
        }

    except Exception as e:
        logger.exception("backup_restore_test_task_fehler", task_id=self.request.id)
        raise self.retry(exc=e)


@celery_app.task(
    bind=True,
    base=CPUTask,
    name="app.workers.tasks.backup_tasks.get_restore_test_history_task",
)
def get_restore_test_history_task(
    self,
    days: int = 30,
) -> Dict[str, Any]:
    """
    Celery Task fuer Restore-Test-Historie.

    Holt die letzten Restore-Test-Ergebnisse.

    Args:
        days: Anzahl Tage zurueckblicken

    Returns:
        Dict mit Test-Historie
    """
    logger.info(
        "get_restore_test_history_task_gestartet",
        task_id=self.request.id,
        days=days,
    )

    try:
        from app.services.backup_restore_test_service import get_backup_restore_test_service

        service = get_backup_restore_test_service()

        async def get_history():
            return await service.get_test_history(days=days)

        history = run_async(get_history())

        logger.info(
            "get_restore_test_history_task_abgeschlossen",
            task_id=self.request.id,
            eintraege=len(history),
        )

        return {
            "erfolg": True,
            "tage": days,
            "eintraege": len(history),
            "historie": history,
        }

    except Exception as e:
        logger.exception("get_restore_test_history_task_fehler", task_id=self.request.id)
        return {
            "erfolg": False,
            "fehler": str(e),
        }
