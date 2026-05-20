# -*- coding: utf-8 -*-
"""
Partition Maintenance Tasks fuer Ablage-System.

Celery-Tasks fuer automatische Partitionspflege:
- Sicherstellung zukuenftiger Partitionen (taeglich)
- Archivierung alter Partitionen (woechentlich)
- Aktualisierung der Partitionsstatistiken (taeglich)

Feinpoliert und durchdacht - Enterprise-grade Partition Maintenance.
"""

import asyncio
from typing import Dict

import structlog

from app.workers.celery_app import celery_app, CPUTask

logger = structlog.get_logger(__name__)


@celery_app.task(
    bind=True,
    base=CPUTask,
    name="partition.ensure_partitions",
    max_retries=3,
    default_retry_delay=300,
    soft_time_limit=120,
    time_limit=180,
    acks_late=True,
)
def ensure_partitions_task(
    self,
    months_ahead: int = 3,
) -> Dict[str, object]:
    """Stellt sicher, dass Partitionen fuer die naechsten N Monate existieren.

    Wird taeglich via Celery Beat ausgefuehrt.
    Erstellt fehlende Partitionen fuer alle konfigurierten Tabellen.

    Args:
        months_ahead: Monate im Voraus (Standard: 3)

    Returns:
        Dict mit Ergebnis der Partition-Erstellung
    """
    return asyncio.run(_ensure_partitions_async(months_ahead))


async def _ensure_partitions_async(months_ahead: int) -> Dict[str, object]:
    """Async-Implementierung der Partition-Sicherstellung."""
    from app.db.session import get_async_session_context
    from app.services.partitioning.partition_service import PartitionService

    try:
        async with get_async_session_context() as session:
            service = PartitionService(session)
            created = await service.ensure_partitions_exist(months_ahead)

            result: Dict[str, object] = {
                "status": "success",
                "created_count": len(created),
                "created_partitions": created,
                "months_ahead": months_ahead,
            }

            logger.info(
                "partition_ensure_completed",
                created_count=len(created),
            )

            return result

    except Exception as exc:
        logger.error(
            "partition_ensure_failed",
            error=str(exc),
        )
        return {
            "status": "error",
            "error": str(exc),
        }


@celery_app.task(
    bind=True,
    base=CPUTask,
    name="partition.archive_old",
    max_retries=2,
    default_retry_delay=600,
    soft_time_limit=300,
    time_limit=360,
    acks_late=True,
)
def archive_old_partitions_task(
    self,
    older_than_months: int = 24,
) -> Dict[str, object]:
    """Archiviert Partitionen aelter als N Monate.

    Wird woechentlich via Celery Beat ausgefuehrt.
    Detached alte Partitionen aus dem Abfragepfad.

    Args:
        older_than_months: Alter in Monaten (Standard: 24)

    Returns:
        Dict mit Archivierungs-Ergebnis
    """
    return asyncio.run(_archive_old_partitions_async(older_than_months))


async def _archive_old_partitions_async(
    older_than_months: int,
) -> Dict[str, object]:
    """Async-Implementierung der Partition-Archivierung."""
    from app.db.session import get_async_session_context
    from app.services.partitioning.partition_service import PartitionService

    try:
        async with get_async_session_context() as session:
            service = PartitionService(session)
            archived = await service.archive_old_partitions(older_than_months)

            result: Dict[str, object] = {
                "status": "success",
                "archived_count": archived,
                "older_than_months": older_than_months,
            }

            logger.info(
                "partition_archive_completed",
                archived_count=archived,
            )

            return result

    except Exception as exc:
        logger.error(
            "partition_archive_failed",
            error=str(exc),
        )
        return {
            "status": "error",
            "error": str(exc),
        }


@celery_app.task(
    bind=True,
    base=CPUTask,
    name="partition.update_stats",
    max_retries=2,
    default_retry_delay=120,
    soft_time_limit=300,
    time_limit=360,
    acks_late=True,
)
def update_partition_stats_task(self) -> Dict[str, object]:
    """Aktualisiert Row-Counts und Speicherverbrauch aller aktiven Partitionen.

    Wird taeglich via Celery Beat ausgefuehrt.
    Fuehrt pro Partition einen COUNT(*) und pg_total_relation_size() aus.

    Returns:
        Dict mit Aktualisierungs-Ergebnis
    """
    return asyncio.run(_update_partition_stats_async())


async def _update_partition_stats_async() -> Dict[str, object]:
    """Async-Implementierung der Statistik-Aktualisierung."""
    from app.db.session import get_async_session_context
    from app.services.partitioning.partition_service import PartitionService

    try:
        async with get_async_session_context() as session:
            service = PartitionService(session)
            updated = await service.update_row_counts()

            result: Dict[str, object] = {
                "status": "success",
                "updated_count": updated,
            }

            logger.info(
                "partition_stats_updated",
                updated_count=updated,
            )

            return result

    except Exception as exc:
        logger.error(
            "partition_stats_update_failed",
            error=str(exc),
        )
        return {
            "status": "error",
            "error": str(exc),
        }


@celery_app.task(
    bind=True,
    base=CPUTask,
    name="partition.health_check",
    max_retries=1,
    soft_time_limit=60,
    time_limit=90,
)
def partition_health_check_task(self) -> Dict[str, object]:
    """Prueft den Gesundheitszustand der Partitionierung.

    Kann bei Bedarf manuell oder via Monitoring aufgerufen werden.

    Returns:
        Dict mit Gesundheitsinformationen
    """
    return asyncio.run(_partition_health_check_async())


async def _partition_health_check_async() -> Dict[str, object]:
    """Async-Implementierung des Health-Checks."""
    from app.db.session import get_async_session_context
    from app.services.partitioning.partition_service import PartitionService

    try:
        async with get_async_session_context() as session:
            service = PartitionService(session)
            health = await service.get_health_status()

            if health.get("status") == "critical":
                logger.warning(
                    "partition_health_critical",
                    issues=health.get("issues"),
                )
            elif health.get("status") == "warning":
                logger.info(
                    "partition_health_warning",
                    issues=health.get("issues"),
                )

            return health

    except Exception as exc:
        logger.error(
            "partition_health_check_failed",
            error=str(exc),
        )
        return {
            "status": "error",
            "error": str(exc),
        }
