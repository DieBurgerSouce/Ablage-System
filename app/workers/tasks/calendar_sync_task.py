# -*- coding: utf-8 -*-
"""
Celery-Tasks fuer die Kalender-Synchronisierung.

Periodische und On-Demand Synchronisierung von Ablage-Fristen
mit externen Kalendern (Google Calendar, Microsoft Outlook, CalDAV).

Feinpoliert und durchdacht - Zuverlaessige Kalender-Automatisierung.
"""

import asyncio
import structlog
from datetime import datetime, timezone
from typing import Dict, List

from app.workers.celery_app import celery_app
from app.db.session import get_async_session_context
from app.core.safe_errors import safe_error_log

logger = structlog.get_logger(__name__)


# =============================================================================
# Periodische Synchronisierung aller Kalender
# =============================================================================


@celery_app.task(
    name="app.workers.tasks.calendar_sync_task.sync_all_calendars",
    bind=True,
    max_retries=2,
    default_retry_delay=300,
)
def sync_all_calendars(self) -> Dict[str, object]:
    """Synchronisiert alle aktiven Kalender-Konfigurationen.

    Wird periodisch via Celery Beat aufgerufen.
    Standard-Intervall: 60 Minuten.

    Returns:
        Dict mit Sync-Statistiken
    """

    async def _sync_all() -> Dict[str, object]:
        from app.db.models import CompanySettings
        from app.services.calendar.calendar_sync_service import (
            CalendarSyncService,
            CalendarProvider,
        )
        from app.services.calendar.calendar_sync_executor import (
            CalendarSyncExecutor,
        )
        from sqlalchemy import select

        stats: Dict[str, object] = {
            "companies_processed": 0,
            "total_created": 0,
            "total_updated": 0,
            "total_deleted": 0,
            "errors": [],
        }

        async with get_async_session_context() as db:
            # Alle CompanySettings mit aktiver Kalender-Sync laden
            result = await db.execute(select(CompanySettings))
            all_settings = result.scalars().all()

            for settings_row in all_settings:
                sync_service = CalendarSyncService(db)
                config = await sync_service.get_sync_config(settings_row.id)

                if not config or not config.auto_sync_enabled:
                    continue

                if config.provider == CalendarProvider.ICAL_FILE:
                    # iCal Export braucht keinen Sync
                    continue

                try:
                    executor = CalendarSyncExecutor()

                    # Kalender-ID aus der Konfiguration
                    cal_id = config.calendar_url or "primary"

                    sync_result = await executor.sync(
                        db=db,
                        company_id=settings_row.id,
                        provider=config.provider.value,
                        calendar_id=cal_id,
                        categories=config.sync_categories,
                        days_ahead=90,
                    )

                    stats["companies_processed"] = int(stats["companies_processed"]) + 1
                    stats["total_created"] = int(stats["total_created"]) + sync_result.created
                    stats["total_updated"] = int(stats["total_updated"]) + sync_result.updated
                    stats["total_deleted"] = int(stats["total_deleted"]) + sync_result.deleted

                    if sync_result.errors:
                        error_list = stats["errors"]
                        if isinstance(error_list, list):
                            error_list.extend(sync_result.errors)

                except Exception as e:
                    logger.error(
                        "calendar_sync_all_company_failed",
                        company_id=str(settings_row.id),
                        **safe_error_log(e),
                    )
                    error_list = stats["errors"]
                    if isinstance(error_list, list):
                        error_list.append(
                            f"Firma {settings_row.company_name}: {type(e).__name__}"
                        )

        return stats

    try:
        return asyncio.run(_sync_all())
    except Exception as e:
        logger.error("calendar_sync_all_task_failed", **safe_error_log(e))
        raise self.retry(exc=e)


# =============================================================================
# On-Demand Synchronisierung einer einzelnen Firma
# =============================================================================


@celery_app.task(
    name="app.workers.tasks.calendar_sync_task.sync_single_calendar",
    bind=True,
    max_retries=2,
    default_retry_delay=60,
)
def sync_single_calendar(self, company_id: str) -> Dict[str, object]:
    """Synchronisiert den Kalender einer einzelnen Firma.

    Wird on-demand aufgerufen (z.B. ueber API-Endpoint).

    Args:
        company_id: UUID der Firma als String

    Returns:
        Dict mit Sync-Ergebnis
    """
    from uuid import UUID

    async def _sync_single() -> Dict[str, object]:
        from app.services.calendar.calendar_sync_service import (
            CalendarSyncService,
            CalendarProvider,
        )
        from app.services.calendar.calendar_sync_executor import (
            CalendarSyncExecutor,
        )

        cid = UUID(company_id)

        async with get_async_session_context() as db:
            sync_service = CalendarSyncService(db)
            config = await sync_service.get_sync_config(cid)

            if not config:
                return {
                    "success": False,
                    "message": "Keine Kalender-Konfiguration vorhanden.",
                }

            if config.provider == CalendarProvider.ICAL_FILE:
                return {
                    "success": False,
                    "message": "iCal-Export benoetigt keine Synchronisierung.",
                }

            executor = CalendarSyncExecutor()
            cal_id = config.calendar_url or "primary"

            sync_result = await executor.sync(
                db=db,
                company_id=cid,
                provider=config.provider.value,
                calendar_id=cal_id,
                categories=config.sync_categories,
                days_ahead=90,
            )

            return {
                "success": len(sync_result.errors) == 0,
                "created": sync_result.created,
                "updated": sync_result.updated,
                "deleted": sync_result.deleted,
                "errors": sync_result.errors,
                "synced_at": sync_result.synced_at,
            }

    try:
        return asyncio.run(_sync_single())
    except Exception as e:
        logger.error(
            "calendar_sync_single_task_failed",
            company_id=company_id,
            **safe_error_log(e),
        )
        raise self.retry(exc=e)


