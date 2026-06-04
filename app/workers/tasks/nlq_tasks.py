"""
Natural Language Query (NLQ) Celery Tasks.

Wartungs-Tasks für NLQ-System:
- Cleanup alter Query-Logs
- Cache-Warming für häufige Queries
- Query-Pattern-Analyse
- Performance-Optimierung

Feinpoliert und durchdacht - Enterprise NLQ Maintenance.
"""

import asyncio
import structlog
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID
from collections import Counter

from sqlalchemy import select, and_, or_, func, delete

from app.workers.celery_app import celery_app
from app.workers.celery_metrics import (
    record_task_started,
    record_task_succeeded,
    record_task_failed,
)
from app.db.session import get_async_session_context
from app.db.models import NLQQueryLog, AppConfig
from app.core.safe_errors import safe_error_log
from app.core.safe_errors import safe_error_detail

logger = structlog.get_logger(__name__)


# =============================================================================
# Cleanup Old Query Logs
# =============================================================================


@celery_app.task(
    name="app.workers.tasks.nlq_tasks.cleanup_old_logs",
    bind=True,
    max_retries=2,
    default_retry_delay=300,
    queue="maintenance",
    soft_time_limit=240,
    time_limit=360,
)
def cleanup_old_logs(
    self,
    retention_days: int = 90,
    batch_size: int = 1000,
) -> Dict[str, Any]:
    """Lösche alte NLQ Query-Logs.

    Behaelt nur Logs der letzten X Tage für Performance und Privacy.
    Archiviert aggregierte Statistiken vor dem Löschen.

    Args:
        retention_days: Behalte Logs für X Tage (default: 90)
        batch_size: Anzahl der Logs pro Batch-Delete

    Returns:
        Dict mit Cleanup-Statistiken
    """
    record_task_started("nlq.cleanup_old_logs")
    logger.info("nlq_cleanup_started", retention_days=retention_days)

    async def _cleanup() -> Dict[str, Any]:
        async with get_async_session_context() as db:
            cutoff_date = datetime.now(timezone.utc) - timedelta(days=retention_days)

            # 1. Aggregiere Statistiken vor dem Löschen
            stats_query = select(
                func.count(NLQQueryLog.id).label("total_logs"),
                func.count(
                    func.distinct(NLQQueryLog.query_text)
                ).label("unique_queries"),
                func.avg(NLQQueryLog.processing_time_ms).label("avg_processing_time"),
                func.count(
                    func.case(
                        (NLQQueryLog.success == True, 1),
                        else_=None
                    )
                ).label("successful_queries"),
            ).where(
                NLQQueryLog.created_at < cutoff_date
            )

            stats_result = await db.execute(stats_query)
            stats = stats_result.one()

            # Speichere aggregierte Statistiken
            archive_data = {
                "period_end": cutoff_date.isoformat(),
                "total_logs": stats.total_logs or 0,
                "unique_queries": stats.unique_queries or 0,
                "avg_processing_time_ms": round(stats.avg_processing_time or 0, 2),
                "successful_queries": stats.successful_queries or 0,
                "success_rate": round(
                    (stats.successful_queries / stats.total_logs * 100)
                    if stats.total_logs else 0,
                    2
                ),
                "archived_at": datetime.now(timezone.utc).isoformat(),
            }

            # In AppConfig speichern
            config_query = select(AppConfig).where(
                AppConfig.key == "nlq_archived_stats"
            )
            config_result = await db.execute(config_query)
            config = config_result.scalar_one_or_none()

            if config:
                # Append zu existierenden Archives
                if isinstance(config.value, list):
                    config.value.append(archive_data)
                else:
                    config.value = [archive_data]
            else:
                config = AppConfig(
                    key="nlq_archived_stats",
                    value=[archive_data],
                )
                db.add(config)

            await db.commit()

            # 2. Batch-Delete alte Logs
            total_deleted = 0
            while True:
                # Finde IDs zum Löschen
                id_query = (
                    select(NLQQueryLog.id)
                    .where(NLQQueryLog.created_at < cutoff_date)
                    .limit(batch_size)
                )
                id_result = await db.execute(id_query)
                ids_to_delete = [row[0] for row in id_result.all()]

                if not ids_to_delete:
                    break

                # Lösche Batch
                delete_stmt = delete(NLQQueryLog).where(
                    NLQQueryLog.id.in_(ids_to_delete)
                )
                result = await db.execute(delete_stmt)
                await db.commit()

                deleted_count = result.rowcount
                total_deleted += deleted_count

                logger.debug(
                    "nlq_cleanup_batch_deleted",
                    batch_size=deleted_count,
                    total=total_deleted,
                )

                # Rate limiting zwischen Batches
                if deleted_count == batch_size:
                    await asyncio.sleep(1)

            return {
                "deleted_count": total_deleted,
                "retention_days": retention_days,
                "cutoff_date": cutoff_date.isoformat(),
                "archived_stats": archive_data,
            }

    try:
        result = asyncio.run(_cleanup())
        record_task_succeeded("nlq.cleanup_old_logs")
        logger.info(
            "nlq_cleanup_completed",
            deleted=result["deleted_count"],
            retention_days=retention_days,
        )
        return result
    except Exception as e:
        record_task_failed("nlq.cleanup_old_logs", str(e))
        logger.error("nlq_cleanup_failed", **safe_error_log(e))
        raise self.retry(exc=e)


# =============================================================================
# Cache Warming for Common Queries
# =============================================================================


@celery_app.task(
    name="app.workers.tasks.nlq_tasks.warm_cache",
    bind=True,
    max_retries=2,
    default_retry_delay=180,
    queue="maintenance",
    soft_time_limit=300,
    time_limit=600,
)
def warm_cache(
    self,
    top_n: int = 50,
    lookback_days: int = 7,
) -> Dict[str, Any]:
    """Pre-cache häufige NLQ-Queries für bessere Performance.

    Analysiert die Top N häufigsten Queries der letzten Tage
    und cached deren Ergebnisse vorab.

    Args:
        top_n: Anzahl der Top-Queries zum Cachen
        lookback_days: Tage für Query-Häufigkeitsanalyse

    Returns:
        Dict mit Cache-Warming-Statistiken
    """
    record_task_started("nlq.warm_cache")
    logger.info("nlq_cache_warming_started", top_n=top_n, lookback_days=lookback_days)

    async def _warm_cache() -> Dict[str, Any]:
        async with get_async_session_context() as db:
            cutoff_date = datetime.now(timezone.utc) - timedelta(days=lookback_days)

            # Finde Top N häufigste Queries
            query = (
                select(
                    NLQQueryLog.query_text,
                    NLQQueryLog.company_id,
                    func.count(NLQQueryLog.id).label("frequency"),
                    func.avg(NLQQueryLog.processing_time_ms).label("avg_time"),
                )
                .where(
                    and_(
                        NLQQueryLog.created_at >= cutoff_date,
                        NLQQueryLog.success == True,
                    )
                )
                .group_by(NLQQueryLog.query_text, NLQQueryLog.company_id)
                .order_by(func.count(NLQQueryLog.id).desc())
                .limit(top_n)
            )

            result = await db.execute(query)
            frequent_queries = result.all()

            stats = {
                "total_queries_analyzed": len(frequent_queries),
                "cached_successfully": 0,
                "cache_failures": 0,
                "total_cache_time_ms": 0,
                "errors": [],
            }

            # Cache jede Query
            from app.services.nlq.nlq_service import NLQService

            nlq_service = NLQService()

            for query_text, company_id, frequency, avg_time in frequent_queries:
                try:
                    start_time = datetime.now(timezone.utc)

                    # Führe Query aus und cache Ergebnis
                    # NLQService nutzt automatisch Redis-Cache
                    _ = await nlq_service.process_query(
                        query_text=query_text,
                        company_id=company_id,
                        user_id=None,  # System-Level Cache
                        db=db,
                    )

                    elapsed = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
                    stats["cached_successfully"] += 1
                    stats["total_cache_time_ms"] += int(elapsed)

                    logger.debug(
                        "nlq_query_cached",
                        query_text=query_text[:50],
                        frequency=frequency,
                        cache_time_ms=int(elapsed),
                    )

                except Exception as e:
                    stats["cache_failures"] += 1
                    stats["errors"].append({
                        "query_text": query_text[:100],
                        "error": safe_error_detail(e, "Vorgang"),
                    })
                    logger.warning(
                        "nlq_cache_failed",
                        query_text=query_text[:50],
                        **safe_error_log(e),
                    )

                # Rate limiting zwischen Queries
                await asyncio.sleep(0.5)

            return stats

    try:
        result = asyncio.run(_warm_cache())
        record_task_succeeded("nlq.warm_cache")
        logger.info(
            "nlq_cache_warming_completed",
            cached=result["cached_successfully"],
            failures=result["cache_failures"],
            total_time_ms=result["total_cache_time_ms"],
        )
        return result
    except Exception as e:
        record_task_failed("nlq.warm_cache", str(e))
        logger.error("nlq_cache_warming_failed", **safe_error_log(e))
        raise self.retry(exc=e)


# =============================================================================
# Query Pattern Analysis
# =============================================================================


@celery_app.task(
    name="app.workers.tasks.nlq_tasks.analyze_query_patterns",
    bind=True,
    max_retries=2,
    default_retry_delay=180,
    queue="maintenance",
    soft_time_limit=240,
    time_limit=360,
)
def analyze_query_patterns(
    self,
    lookback_days: int = 30,
) -> Dict[str, Any]:
    """Analysiere Query-Patterns für Optimierung.

    Identifiziert:
    - Häufige Query-Typen
    - Langsame Queries (>5s)
    - Fehlgeschlagene Queries
    - Peak-Nutzungszeiten

    Args:
        lookback_days: Anzahl der Tage für Analyse

    Returns:
        Dict mit Pattern-Analyse
    """
    record_task_started("nlq.analyze_patterns")
    logger.info("nlq_pattern_analysis_started", lookback_days=lookback_days)

    async def _analyze_patterns() -> Dict[str, Any]:
        async with get_async_session_context() as db:
            cutoff_date = datetime.now(timezone.utc) - timedelta(days=lookback_days)

            # Lade alle Logs im Zeitraum
            query = select(NLQQueryLog).where(
                NLQQueryLog.created_at >= cutoff_date
            )
            result = await db.execute(query)
            logs = result.scalars().all()

            if not logs:
                return {
                    "success": False,
                    "error": "Keine Query-Logs im Zeitraum gefunden",
                }

            # Analysiere Patterns
            query_types = Counter()
            slow_queries = []
            failed_queries = []
            hourly_distribution = Counter()

            for log in logs:
                # Query-Typ aus Metadata
                if log.metadata and "intent" in log.metadata:
                    query_types[log.metadata["intent"]] += 1

                # Langsame Queries (>5s)
                if log.processing_time_ms and log.processing_time_ms > 5000:
                    slow_queries.append({
                        "query_text": log.query_text[:100],
                        "processing_time_ms": log.processing_time_ms,
                        "created_at": log.created_at.isoformat(),
                    })

                # Fehlgeschlagene Queries
                if not log.success:
                    failed_queries.append({
                        "query_text": log.query_text[:100],
                        "error": log.error_message[:200] if log.error_message else "Unknown",
                        "created_at": log.created_at.isoformat(),
                    })

                # Stunden-Verteilung
                hour = log.created_at.hour
                hourly_distribution[hour] += 1

            # Peak-Nutzungszeit identifizieren
            peak_hour = hourly_distribution.most_common(1)[0] if hourly_distribution else (0, 0)

            analysis = {
                "period_days": lookback_days,
                "total_queries": len(logs),
                "query_types": dict(query_types.most_common(10)),
                "slow_queries_count": len(slow_queries),
                "slow_queries_sample": slow_queries[:10],
                "failed_queries_count": len(failed_queries),
                "failed_queries_sample": failed_queries[:10],
                "peak_usage_hour": peak_hour[0],
                "peak_usage_count": peak_hour[1],
                "hourly_distribution": dict(hourly_distribution),
                "success_rate": round(
                    ((len(logs) - len(failed_queries)) / len(logs) * 100),
                    2
                ),
                "analyzed_at": datetime.now(timezone.utc).isoformat(),
            }

            # Speichere Analyse in AppConfig
            config_query = select(AppConfig).where(
                AppConfig.key == "nlq_pattern_analysis"
            )
            config_result = await db.execute(config_query)
            config = config_result.scalar_one_or_none()

            if config:
                config.value = analysis
            else:
                config = AppConfig(
                    key="nlq_pattern_analysis",
                    value=analysis,
                )
                db.add(config)

            await db.commit()

            return analysis

    try:
        result = asyncio.run(_analyze_patterns())
        record_task_succeeded("nlq.analyze_patterns")
        logger.info(
            "nlq_pattern_analysis_completed",
            total_queries=result.get("total_queries"),
            success_rate=result.get("success_rate"),
            slow_queries=result.get("slow_queries_count"),
        )
        return result
    except Exception as e:
        record_task_failed("nlq.analyze_patterns", str(e))
        logger.error("nlq_pattern_analysis_failed", **safe_error_log(e))
        raise self.retry(exc=e)


# =============================================================================
# Failed Query Retry
# =============================================================================


@celery_app.task(
    name="app.workers.tasks.nlq_tasks.retry_failed_queries",
    bind=True,
    max_retries=1,
    default_retry_delay=300,
    queue="maintenance",
    soft_time_limit=180,
    time_limit=300,
)
def retry_failed_queries(
    self,
    max_retries: int = 3,
    age_hours: int = 24,
) -> Dict[str, Any]:
    """Versuche fehlgeschlagene Queries erneut.

    Nützlich nach System-Updates oder Bugfixes.

    Args:
        max_retries: Maximale Anzahl Retry-Versuche pro Query
        age_hours: Nur Queries der letzten X Stunden retrying

    Returns:
        Dict mit Retry-Statistiken
    """
    record_task_started("nlq.retry_failed_queries")
    logger.info("nlq_failed_query_retry_started", max_retries=max_retries)

    async def _retry_failed() -> Dict[str, Any]:
        async with get_async_session_context() as db:
            cutoff_date = datetime.now(timezone.utc) - timedelta(hours=age_hours)

            # Finde fehlgeschlagene Queries
            query = (
                select(NLQQueryLog)
                .where(
                    and_(
                        NLQQueryLog.success == False,
                        NLQQueryLog.created_at >= cutoff_date,
                    )
                )
                .limit(50)  # Max 50 Retries pro Run
            )

            result = await db.execute(query)
            failed_logs = result.scalars().all()

            stats = {
                "total_retried": 0,
                "successful_retries": 0,
                "still_failing": 0,
                "errors": [],
            }

            from app.services.nlq.nlq_service import NLQService

            nlq_service = NLQService()

            for log in failed_logs:
                # Prüfe Retry-Counter in Metadata
                retry_count = log.metadata.get("retry_count", 0) if log.metadata else 0

                if retry_count >= max_retries:
                    continue

                try:
                    stats["total_retried"] += 1

                    # Retry Query
                    _ = await nlq_service.process_query(
                        query_text=log.query_text,
                        company_id=log.company_id,
                        user_id=log.user_id,
                        db=db,
                    )

                    stats["successful_retries"] += 1

                    logger.debug(
                        "nlq_retry_succeeded",
                        original_log_id=str(log.id),
                        query_text=log.query_text[:50],
                    )

                except Exception as e:
                    stats["still_failing"] += 1
                    stats["errors"].append({
                        "log_id": str(log.id),
                        "query_text": log.query_text[:100],
                        "error": safe_error_detail(e, "Vorgang"),
                    })

                    # Update Retry-Counter
                    if not log.metadata:
                        log.metadata = {}
                    log.metadata["retry_count"] = retry_count + 1
                    log.updated_at = datetime.now(timezone.utc)

                await asyncio.sleep(1)  # Rate limiting

            await db.commit()
            return stats

    try:
        result = asyncio.run(_retry_failed())
        record_task_succeeded("nlq.retry_failed_queries")
        logger.info(
            "nlq_failed_query_retry_completed",
            total=result["total_retried"],
            successful=result["successful_retries"],
            still_failing=result["still_failing"],
        )
        return result
    except Exception as e:
        record_task_failed("nlq.retry_failed_queries", str(e))
        logger.error("nlq_failed_query_retry_failed", **safe_error_log(e))
        raise self.retry(exc=e)
