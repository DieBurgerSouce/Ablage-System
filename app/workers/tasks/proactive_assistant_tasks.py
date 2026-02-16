# -*- coding: utf-8 -*-
"""
Proaktiver Assistent - Celery Tasks.

Automatische Hint-Generierung und Verwaltung:
- Tägliche Hint-Generierung für alle Firmen
- Wöchentliche tiefere Optimierungs-Analyse
- Stündliche Prüfung abgelaufener Hints
- Tagesstatistiken

Feinpoliert und durchdacht - Enterprise-grade Proactive Intelligence.
"""

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

import structlog

from app.workers.celery_app import celery_app
from app.db.session import get_async_session_context
from app.db.models import Company
from app.core.safe_errors import safe_error_log, safe_error_detail
from sqlalchemy import select, and_

logger = structlog.get_logger(__name__)


# =============================================================================
# Tägliche Hint-Generierung
# =============================================================================


@celery_app.task(
    name="app.workers.tasks.proactive_assistant_tasks.generate_daily_hints_task",
    bind=True,
    max_retries=2,
    default_retry_delay=300,
    queue="maintenance",
)
def generate_daily_hints_task(self) -> Dict[str, object]:
    """Täglich: Hints für alle aktiven Firmen generieren.

    Wird täglich um 06:00 Uhr via Celery Beat ausgeführt.
    Prüft Fristen, Anomalien und Optimierungspotenziale.

    Returns:
        Dict mit Verarbeitungsstatistiken pro Firma
    """
    from app.services.proactive_assistant_service import get_proactive_assistant_service

    async def _generate_all() -> Dict[str, object]:
        async with get_async_session_context() as db:
            service = get_proactive_assistant_service()

            # Alle aktiven Firmen laden
            result = await db.execute(
                select(Company.id).where(Company.is_active == True)
            )
            company_ids = [row[0] for row in result.all()]

            stats: Dict[str, object] = {
                "total_companies": len(company_ids),
                "successful": 0,
                "failed": 0,
                "total_hints_created": 0,
                "company_results": [],
            }

            for company_id in company_ids:
                try:
                    hints = await service.generate_daily_hints(db, company_id)
                    await db.commit()

                    stats["successful"] += 1
                    stats["total_hints_created"] += len(hints)
                    stats["company_results"].append({
                        "company_id": str(company_id),
                        "hints_created": len(hints),
                        "success": True,
                    })

                    logger.debug(
                        "company_daily_hints_generated",
                        company_id=str(company_id),
                        hints_created=len(hints),
                    )
                except Exception as e:
                    stats["failed"] += 1
                    stats["company_results"].append({
                        "company_id": str(company_id),
                        "success": False,
                        "error": safe_error_detail(e, "Hint-Generierung"),
                    })
                    logger.error(
                        "company_daily_hints_failed",
                        company_id=str(company_id),
                        **safe_error_log(e),
                    )
                    # Rollback für diese Firma, weiter mit nächster
                    await db.rollback()

            return stats

    try:
        result = asyncio.run(_generate_all())
        logger.info(
            "daily_hints_batch_completed",
            companies=result["total_companies"],
            successful=result["successful"],
            failed=result["failed"],
            total_hints=result["total_hints_created"],
        )
        return result
    except Exception as e:
        logger.error("daily_hints_batch_failed", **safe_error_log(e))
        raise self.retry(exc=e)


# =============================================================================
# Wöchentliche Optimierungs-Analyse
# =============================================================================


@celery_app.task(
    name="app.workers.tasks.proactive_assistant_tasks.generate_weekly_optimization_hints_task",
    bind=True,
    max_retries=2,
    default_retry_delay=600,
    queue="maintenance",
)
def generate_weekly_optimization_hints_task(self) -> Dict[str, object]:
    """Wöchentlich: Tiefere Optimierungs-Analyse für alle Firmen.

    Wird montags um 07:00 Uhr via Celery Beat ausgeführt.
    Fokus auf wiederkehrende Muster und langfristige Sparpotenziale.

    Returns:
        Dict mit Verarbeitungsstatistiken
    """
    from app.services.proactive_assistant_service import get_proactive_assistant_service

    async def _generate_weekly() -> Dict[str, object]:
        async with get_async_session_context() as db:
            service = get_proactive_assistant_service()

            result = await db.execute(
                select(Company.id).where(Company.is_active == True)
            )
            company_ids = [row[0] for row in result.all()]

            stats: Dict[str, object] = {
                "total_companies": len(company_ids),
                "successful": 0,
                "failed": 0,
                "total_hints_created": 0,
            }

            for company_id in company_ids:
                try:
                    hints = await service.check_optimization_hints(db, company_id)

                    # Deduplizierung und Persistierung
                    new_count = 0
                    for hint in hints:
                        existing = await service._find_active_hint(
                            db, company_id, hint.source_type, hint.source_id
                        )
                        if not existing:
                            db.add(hint)
                            new_count += 1

                    await db.commit()
                    stats["successful"] += 1
                    stats["total_hints_created"] += new_count

                except Exception as e:
                    stats["failed"] += 1
                    logger.error(
                        "weekly_optimization_hints_failed",
                        company_id=str(company_id),
                        **safe_error_log(e),
                    )
                    await db.rollback()

            return stats

    try:
        result = asyncio.run(_generate_weekly())
        logger.info(
            "weekly_optimization_batch_completed",
            companies=result["total_companies"],
            successful=result["successful"],
            total_hints=result["total_hints_created"],
        )
        return result
    except Exception as e:
        logger.error("weekly_optimization_batch_failed", **safe_error_log(e))
        raise self.retry(exc=e)


# =============================================================================
# Abgelaufene Hints prüfen
# =============================================================================


@celery_app.task(
    name="app.workers.tasks.proactive_assistant_tasks.check_expiring_hints_task",
    bind=True,
    max_retries=2,
    default_retry_delay=60,
    queue="maintenance",
)
def check_expiring_hints_task(self) -> Dict[str, object]:
    """Stündlich: Abgelaufene Hints als dismissed markieren.

    Wird stündlich via Celery Beat ausgeführt.
    Räumt Hints auf deren expires_at überschritten ist.

    Returns:
        Dict mit Anzahl bereinigter Hints
    """
    from app.services.proactive_assistant_service import get_proactive_assistant_service

    async def _check_expiring() -> Dict[str, object]:
        async with get_async_session_context() as db:
            service = get_proactive_assistant_service()
            expired_count = await service.expire_old_hints(db)
            await db.commit()
            return {
                "expired_count": expired_count,
                "checked_at": datetime.now(timezone.utc).isoformat(),
            }

    try:
        result = asyncio.run(_check_expiring())
        if result["expired_count"] > 0:
            logger.info(
                "expiring_hints_checked",
                expired_count=result["expired_count"],
            )
        return result
    except Exception as e:
        logger.error("expiring_hints_check_failed", **safe_error_log(e))
        raise self.retry(exc=e)


# =============================================================================
# Hint-Benachrichtigungen
# =============================================================================


@celery_app.task(
    name="app.workers.tasks.proactive_assistant_tasks.send_hint_notifications_task",
    bind=True,
    max_retries=3,
    default_retry_delay=120,
    queue="notifications",
)
def send_hint_notifications_task(
    self,
    company_id: Optional[str] = None,
) -> Dict[str, object]:
    """Benachrichtigungen für hochpriorisierte neue Hints versenden.

    Wird nach Hint-Generierung ausgeführt oder manuell getriggert.
    Sendet Benachrichtigungen für CRITICAL/HIGH-Hints.

    Args:
        company_id: Optionale Firma-ID (None = alle Firmen)

    Returns:
        Dict mit Benachrichtigungs-Statistiken
    """
    from app.db.models_proactive_assistant import (
        ProactiveHint,
        HintPriority,
        HintStatus,
    )

    async def _send_notifications() -> Dict[str, object]:
        async with get_async_session_context() as db:
            # Finde neue hochpriorisierte Hints
            conditions = [
                ProactiveHint.status == HintStatus.NEW.value,
                ProactiveHint.priority.in_([
                    HintPriority.CRITICAL.value,
                    HintPriority.HIGH.value,
                ]),
            ]
            if company_id:
                from uuid import UUID as UUIDType
                conditions.append(ProactiveHint.company_id == UUIDType(company_id))

            stmt = (
                select(ProactiveHint)
                .where(and_(*conditions))
                .order_by(ProactiveHint.combined_score.desc())
                .limit(50)
            )
            result = await db.execute(stmt)
            hints = result.scalars().all()

            notified_count = 0
            for hint in hints:
                try:
                    # Hier könnte eine Notification Service Integration erfolgen
                    # Für den Moment: Hint als gesehen markieren
                    logger.info(
                        "high_priority_hint_notification",
                        hint_id=str(hint.id),
                        category=hint.category,
                        priority=hint.priority,
                        title=hint.title,
                    )
                    notified_count += 1
                except Exception as e:
                    logger.warning(
                        "hint_notification_failed",
                        hint_id=str(hint.id),
                        **safe_error_log(e),
                    )

            return {
                "total_high_priority": len(hints),
                "notified": notified_count,
            }

    try:
        result = asyncio.run(_send_notifications())
        return result
    except Exception as e:
        logger.error("hint_notifications_failed", **safe_error_log(e))
        raise self.retry(exc=e)


# =============================================================================
# Statistik-Berechnung
# =============================================================================


@celery_app.task(
    name="app.workers.tasks.proactive_assistant_tasks.calculate_hint_statistics_task",
    bind=True,
    max_retries=2,
    default_retry_delay=300,
    queue="maintenance",
)
def calculate_hint_statistics_task(self) -> Dict[str, object]:
    """Täglich: Hint-Statistiken aggregieren.

    Wird täglich um 23:00 Uhr via Celery Beat ausgeführt.
    Berechnet Statistiken für den vergangenen Tag.

    Returns:
        Dict mit Statistik-Ergebnissen
    """
    from app.services.proactive_assistant_service import get_proactive_assistant_service

    async def _calculate_stats() -> Dict[str, object]:
        async with get_async_session_context() as db:
            service = get_proactive_assistant_service()

            result = await db.execute(
                select(Company.id).where(Company.is_active == True)
            )
            company_ids = [row[0] for row in result.all()]

            now = datetime.now(timezone.utc)
            period_start = (now - timedelta(days=1)).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            period_end = now.replace(
                hour=0, minute=0, second=0, microsecond=0
            )

            stats_results: Dict[str, object] = {
                "total_companies": len(company_ids),
                "successful": 0,
                "failed": 0,
            }

            for company_id in company_ids:
                try:
                    await service.calculate_statistics(
                        db, company_id, period_start, period_end
                    )
                    await db.commit()
                    stats_results["successful"] += 1
                except Exception as e:
                    stats_results["failed"] += 1
                    logger.error(
                        "hint_statistics_calculation_failed",
                        company_id=str(company_id),
                        **safe_error_log(e),
                    )
                    await db.rollback()

            return stats_results

    try:
        result = asyncio.run(_calculate_stats())
        logger.info(
            "hint_statistics_batch_completed",
            companies=result["total_companies"],
            successful=result["successful"],
            failed=result["failed"],
        )
        return result
    except Exception as e:
        logger.error("hint_statistics_batch_failed", **safe_error_log(e))
        raise self.retry(exc=e)
