# -*- coding: utf-8 -*-
"""Celery Tasks fuer Wechselkurs-Management.

Tasks:
- Taeglicher ECB-Kursabruf (17:00 CET, nach ECB-Veroeffentlichung)
- Monatliche Kursbewertung (unrealisierte Gewinne/Verluste)
"""

from __future__ import annotations

from datetime import date
from typing import Dict, Any

import structlog

from app.core.safe_errors import safe_error_log
from app.workers.celery_app import celery_app

logger = structlog.get_logger(__name__)


@celery_app.task(
    name="app.workers.tasks.fx_rate_tasks.fetch_ecb_rates_daily",
    bind=True,
    acks_late=True,
    max_retries=3,
    default_retry_delay=300,  # 5 min retry
)
def fetch_ecb_rates_daily(self) -> Dict[str, Any]:
    """Taeglicher Abruf der ECB Referenzkurse (17:00 CET via Beat)."""
    import asyncio
    from app.db.session import get_async_session
    from app.services.accounting.fx_rate_service import FXRateService

    async def _fetch() -> Dict[str, Any]:
        async with get_async_session() as db:
            service = FXRateService(db)
            count = await service.fetch_ecb_rates(historical=False)
            return {"imported_rates": count, "date": str(date.today())}

    try:
        result = asyncio.run(_fetch())
        logger.info("ecb_rates_imported", imported_rates=result["imported_rates"])
        return result
    except Exception as exc:
        logger.error("ecb_rates_fetch_failed", **safe_error_log(exc))
        raise self.retry(exc=exc)


@celery_app.task(
    name="app.workers.tasks.fx_rate_tasks.fetch_ecb_rates_historical",
    bind=True,
    acks_late=True,
    max_retries=2,
    default_retry_delay=300,
)
def fetch_ecb_rates_historical(self) -> Dict[str, Any]:
    """Einmaliger Abruf der letzten 90 Tage ECB Kurse."""
    import asyncio
    from app.db.session import get_async_session
    from app.services.accounting.fx_rate_service import FXRateService

    async def _fetch() -> Dict[str, Any]:
        async with get_async_session() as db:
            service = FXRateService(db)
            count = await service.fetch_ecb_rates(historical=True)
            return {"imported_rates": count, "historical": True}

    try:
        return asyncio.run(_fetch())
    except Exception as exc:
        logger.error("ecb_rates_historical_fetch_failed", **safe_error_log(exc))
        raise self.retry(exc=exc)


@celery_app.task(
    name="app.workers.tasks.fx_rate_tasks.month_end_revaluation",
    bind=True,
    acks_late=True,
    max_retries=2,
    default_retry_delay=300,
)
def month_end_revaluation(self, company_id: str) -> Dict[str, Any]:
    """
    Monatsabschluss: Unrealisierte Kursdifferenzen berechnen.
    Bewertet alle offenen Fremdwaehrungspositionen zum Stichtagskurs.

    Wird am letzten Tag des Monats automatisch via Beat ausgefuehrt
    oder manuell ueber die API getriggert.
    """
    import asyncio
    from uuid import UUID
    from app.db.session import get_async_session_context
    from app.services.accounting.fx_rate_service import FXRateService

    logger.info("month_end_revaluation_started", company_id=company_id)

    async def _revaluate() -> Dict[str, Any]:
        async with get_async_session_context() as db:
            service = FXRateService(db)
            revaluation_date = date.today()
            summary = await service.month_end_revaluation(
                company_id=UUID(company_id),
                revaluation_date=revaluation_date,
                db=db,
            )
            return {
                "company_id": company_id,
                "status": "completed",
                "revaluation_date": str(revaluation_date),
                "entries_processed": summary.entries_processed,
                "total_gain": str(summary.total_gain),
                "total_loss": str(summary.total_loss),
                "currency_breakdown": summary.currency_breakdown,
            }

    try:
        result = asyncio.run(_revaluate())
        logger.info(
            "month_end_revaluation_completed",
            company_id=company_id,
            entries_processed=result["entries_processed"],
        )
        return result
    except Exception as exc:
        logger.error("month_end_revaluation_failed", **safe_error_log(exc))
        raise self.retry(exc=exc)


@celery_app.task(
    name="app.workers.tasks.fx_rate_tasks.run_month_end_fx_revaluation_all",
    bind=True,
    acks_late=True,
    max_retries=1,
    default_retry_delay=600,
)
def run_month_end_fx_revaluation_all(self) -> Dict[str, Any]:
    """
    Fuehrt Monatsabschluss-Bewertung fuer ALLE aktiven Firmen aus.

    Wird via Celery Beat am letzten Tag des Monats getriggert.
    Startet fuer jede aktive Firma eine eigene month_end_revaluation Task.
    """
    import asyncio
    from app.db.session import get_async_session_context
    from sqlalchemy import select, and_
    from app.db.models import Company

    logger.info("run_month_end_fx_revaluation_all_started")

    async def _get_active_companies():
        async with get_async_session_context() as db:
            result = await db.execute(
                select(Company.id).where(
                    and_(
                        Company.is_active == True,  # noqa: E712
                    )
                )
            )
            return [str(row[0]) for row in result.all()]

    try:
        company_ids = asyncio.run(_get_active_companies())
        dispatched = 0

        for cid in company_ids:
            month_end_revaluation.delay(cid)
            dispatched += 1

        logger.info(
            "run_month_end_fx_revaluation_all_dispatched",
            companies=dispatched,
        )

        return {
            "status": "dispatched",
            "companies_dispatched": dispatched,
            "date": str(date.today()),
        }
    except Exception as exc:
        logger.error("run_month_end_fx_revaluation_all_failed", **safe_error_log(exc))
        raise self.retry(exc=exc)
