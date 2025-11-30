"""
Cleanup Tasks für Ablage-System.

Periodische Aufräumarbeiten:
- Soft-Delete Cleanup (GDPR-konform, 30 Tage)
- Abgelaufene Cache-Einträge
- Verwaiste Dateien in MinIO

Feinpoliert und durchdacht - GDPR-konforme Datenlöschung.
"""

from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List
from uuid import UUID

import structlog
from celery import shared_task
from sqlalchemy import select, delete, and_, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings

logger = structlog.get_logger(__name__)

# Konstanten
SOFT_DELETE_RETENTION_DAYS = 30  # GDPR: 30 Tage Aufbewahrung vor permanenter Löschung
BATCH_SIZE = 100  # Dokumente pro Batch für schonende DB-Last


@shared_task(
    name="app.workers.tasks.cleanup_tasks.cleanup_soft_deleted_documents",
    bind=True,
    max_retries=3,
    default_retry_delay=300,  # 5 Minuten Retry-Delay
    autoretry_for=(Exception,),
)
def cleanup_soft_deleted_documents(
    self,
    retention_days: int = SOFT_DELETE_RETENTION_DAYS,
    dry_run: bool = False
) -> Dict[str, Any]:
    """
    Permanent löschen von Dokumenten, die länger als retention_days soft-deleted sind.

    GDPR-konform: Dokumente werden nach 30 Tagen Soft-Delete permanent gelöscht.

    Args:
        retention_days: Tage bis zur permanenten Löschung (default: 30)
        dry_run: Nur zählen, nicht löschen

    Returns:
        Dict mit Statistiken über gelöschte Dokumente
    """
    import asyncio
    return asyncio.get_event_loop().run_until_complete(
        _cleanup_soft_deleted_async(retention_days, dry_run)
    )


async def _cleanup_soft_deleted_async(
    retention_days: int,
    dry_run: bool
) -> Dict[str, Any]:
    """Async implementation of soft-delete cleanup."""
    from app.db.database import get_db_session
    from app.db.models import Document
    from app.services.storage_service import get_storage_service

    cutoff_date = datetime.now(timezone.utc) - timedelta(days=retention_days)

    logger.info(
        "soft_delete_cleanup_started",
        retention_days=retention_days,
        cutoff_date=cutoff_date.isoformat(),
        dry_run=dry_run,
    )

    stats = {
        "documents_found": 0,
        "documents_deleted": 0,
        "files_deleted": 0,
        "errors": [],
        "dry_run": dry_run,
        "retention_days": retention_days,
        "cutoff_date": cutoff_date.isoformat(),
    }

    async with get_db_session() as db:
        # Finde Dokumente, die vor cutoff_date soft-deleted wurden
        query = select(Document).where(
            and_(
                Document.deleted_at.isnot(None),
                Document.deleted_at < cutoff_date
            )
        ).limit(BATCH_SIZE * 10)  # Maximal 1000 pro Durchlauf

        result = await db.execute(query)
        documents = result.scalars().all()
        stats["documents_found"] = len(documents)

        if dry_run:
            logger.info(
                "soft_delete_cleanup_dry_run",
                documents_found=len(documents),
            )
            return stats

        if not documents:
            logger.info("soft_delete_cleanup_no_documents")
            return stats

        # Lösche in Batches
        storage = get_storage_service()
        document_ids: List[UUID] = []

        for doc in documents:
            try:
                # 1. Lösche Dateien aus MinIO
                if doc.file_path:
                    try:
                        await storage.delete_document(str(doc.id))
                        stats["files_deleted"] += 1
                    except Exception as e:
                        logger.warning(
                            "storage_delete_failed",
                            document_id=str(doc.id),
                            error=str(e),
                        )
                        # Fahre trotzdem mit DB-Löschung fort

                document_ids.append(doc.id)

            except Exception as e:
                stats["errors"].append({
                    "document_id": str(doc.id),
                    "error": str(e),
                })
                logger.error(
                    "soft_delete_cleanup_document_error",
                    document_id=str(doc.id),
                    error=str(e),
                )

        # 2. Batch-Delete aus Datenbank
        if document_ids:
            try:
                delete_stmt = delete(Document).where(Document.id.in_(document_ids))
                result = await db.execute(delete_stmt)
                await db.commit()
                stats["documents_deleted"] = result.rowcount

                logger.info(
                    "soft_delete_cleanup_completed",
                    documents_deleted=stats["documents_deleted"],
                    files_deleted=stats["files_deleted"],
                    errors=len(stats["errors"]),
                )

            except Exception as e:
                await db.rollback()
                logger.error(
                    "soft_delete_cleanup_db_error",
                    error=str(e),
                )
                stats["errors"].append({
                    "type": "database",
                    "error": str(e),
                })

    return stats


@shared_task(
    name="app.workers.tasks.cleanup_tasks.cleanup_orphaned_files",
    bind=True,
    max_retries=1,
)
def cleanup_orphaned_files(self) -> Dict[str, Any]:
    """
    Finde und lösche verwaiste Dateien in MinIO.

    Verwaiste Dateien: In MinIO vorhanden, aber kein DB-Eintrag.
    """
    import asyncio
    return asyncio.get_event_loop().run_until_complete(
        _cleanup_orphaned_files_async()
    )


async def _cleanup_orphaned_files_async() -> Dict[str, Any]:
    """Async implementation of orphaned files cleanup."""
    from app.db.database import get_db_session
    from app.db.models import Document
    from app.services.storage_service import get_storage_service

    logger.info("orphaned_files_cleanup_started")

    stats = {
        "files_checked": 0,
        "orphaned_found": 0,
        "orphaned_deleted": 0,
        "errors": [],
    }

    try:
        storage = get_storage_service()

        # Liste alle Dateien in MinIO
        minio_files = await storage.list_all_documents()
        stats["files_checked"] = len(minio_files)

        if not minio_files:
            return stats

        # Hole alle Dokument-IDs aus DB
        async with get_db_session() as db:
            query = select(Document.id)
            result = await db.execute(query)
            db_ids = {str(row[0]) for row in result.fetchall()}

        # Finde verwaiste Dateien
        orphaned = []
        for file_info in minio_files:
            file_id = file_info.get("id") or file_info.get("name", "").split("/")[0]
            if file_id and file_id not in db_ids:
                orphaned.append(file_info)

        stats["orphaned_found"] = len(orphaned)

        # Lösche verwaiste Dateien
        for file_info in orphaned:
            try:
                file_path = file_info.get("path") or file_info.get("name")
                if file_path:
                    await storage.delete_file(file_path)
                    stats["orphaned_deleted"] += 1
            except Exception as e:
                stats["errors"].append({
                    "file": str(file_info),
                    "error": str(e),
                })

        logger.info(
            "orphaned_files_cleanup_completed",
            files_checked=stats["files_checked"],
            orphaned_found=stats["orphaned_found"],
            orphaned_deleted=stats["orphaned_deleted"],
        )

    except Exception as e:
        logger.error("orphaned_files_cleanup_error", error=str(e))
        stats["errors"].append({"type": "general", "error": str(e)})

    return stats


@shared_task(
    name="app.workers.tasks.cleanup_tasks.cleanup_expired_cache",
    bind=True,
)
def cleanup_expired_cache(self) -> Dict[str, Any]:
    """
    Aufräumen abgelaufener Cache-Einträge.

    Redis TTL kümmert sich automatisch um Expiry,
    dieser Task räumt zusätzliche Artefakte auf.
    """
    import asyncio
    return asyncio.get_event_loop().run_until_complete(
        _cleanup_expired_cache_async()
    )


@shared_task(
    name="app.workers.tasks.cleanup_tasks.cleanup_search_analytics",
    bind=True,
    max_retries=2,
)
def cleanup_search_analytics(
    self,
    retention_months: int = 6,
    dry_run: bool = False
) -> Dict[str, Any]:
    """
    Archiviere/lösche alte SearchAnalytics-Einträge.

    GDPR-konform: Analytics älter als 6 Monate werden archiviert/gelöscht.

    Args:
        retention_months: Monate bis zur Archivierung (default: 6)
        dry_run: Nur zählen, nicht löschen

    Returns:
        Dict mit Statistiken
    """
    import asyncio
    return asyncio.get_event_loop().run_until_complete(
        _cleanup_search_analytics_async(retention_months, dry_run)
    )


async def _cleanup_search_analytics_async(
    retention_months: int,
    dry_run: bool
) -> Dict[str, Any]:
    """Async implementation of search analytics cleanup."""
    from app.db.database import get_db_session
    from app.db.models import SearchAnalytics

    cutoff_date = datetime.now(timezone.utc) - timedelta(days=retention_months * 30)

    logger.info(
        "search_analytics_cleanup_started",
        retention_months=retention_months,
        cutoff_date=cutoff_date.isoformat(),
        dry_run=dry_run,
    )

    stats = {
        "entries_found": 0,
        "entries_deleted": 0,
        "dry_run": dry_run,
        "retention_months": retention_months,
        "cutoff_date": cutoff_date.isoformat(),
    }

    async with get_db_session() as db:
        # Zähle alte Einträge
        count_query = select(func.count(SearchAnalytics.id)).where(
            SearchAnalytics.created_at < cutoff_date
        )
        result = await db.execute(count_query)
        stats["entries_found"] = result.scalar() or 0

        if dry_run or stats["entries_found"] == 0:
            logger.info(
                "search_analytics_cleanup_dry_run",
                entries_found=stats["entries_found"],
            )
            return stats

        # Lösche in Batches (10.000 pro Durchlauf)
        try:
            delete_stmt = delete(SearchAnalytics).where(
                SearchAnalytics.created_at < cutoff_date
            )
            result = await db.execute(delete_stmt)
            await db.commit()
            stats["entries_deleted"] = result.rowcount

            logger.info(
                "search_analytics_cleanup_completed",
                entries_deleted=stats["entries_deleted"],
            )

        except Exception as e:
            await db.rollback()
            logger.error("search_analytics_cleanup_error", error=str(e))
            raise

    return stats


async def _cleanup_expired_cache_async() -> Dict[str, Any]:
    """Async implementation of cache cleanup."""
    from app.core.rate_limiting import get_redis_storage

    logger.info("cache_cleanup_started")

    stats = {
        "patterns_checked": [],
        "keys_deleted": 0,
        "errors": [],
    }

    try:
        redis = await get_redis_storage()
        if not redis:
            return stats

        # Patterns für manuelle Cleanup (normalerweise TTL-basiert)
        cleanup_patterns = [
            "ocr_cache:lock:*",  # Alte Locks
            "idempotency:lock:*",  # Alte Idempotency Locks
            "temp:*",  # Temporäre Einträge
        ]

        for pattern in cleanup_patterns:
            stats["patterns_checked"].append(pattern)
            try:
                count = 0
                async for key in redis.scan_iter(match=pattern):
                    # Prüfe TTL - lösche nur wenn kein TTL gesetzt (sollte nicht passieren)
                    ttl = await redis.ttl(key)
                    if ttl == -1:  # Kein Expiry
                        await redis.delete(key)
                        count += 1
                stats["keys_deleted"] += count
            except Exception as e:
                stats["errors"].append({
                    "pattern": pattern,
                    "error": str(e),
                })

        logger.info(
            "cache_cleanup_completed",
            keys_deleted=stats["keys_deleted"],
        )

    except Exception as e:
        logger.error("cache_cleanup_error", error=str(e))
        stats["errors"].append({"type": "general", "error": str(e)})

    return stats
