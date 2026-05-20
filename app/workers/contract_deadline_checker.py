# -*- coding: utf-8 -*-
"""
Contract Deadline Checker - Celery Periodic Task.

Prüft täglich alle aktiven Verträge auf anstehende Fristen:
- Kündigungsfristen (30/60/90 Tage)
- Automatische Verlängerung
- Preisanpassungstermine
- Vertragsablauf

Erstellt Alerts über den Alert Center Service.

Beat Schedule (in celery_app.py registriert):
    'check-contract-deadlines': {
        'task': 'app.workers.contract_deadline_checker.check_contract_deadlines',
        'schedule': crontab(hour=6, minute=0),  # Täglich um 06:00 Uhr
    }
"""

import asyncio
from typing import Dict, Optional

import structlog

from app.workers.celery_app import celery_app
from app.core.safe_errors import safe_error_detail, safe_error_log

logger = structlog.get_logger(__name__)


@celery_app.task(
    name="app.workers.contract_deadline_checker.check_contract_deadlines",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    queue="metadata",
)
def check_contract_deadlines(self, company_id: Optional[str] = None) -> Dict[str, int]:
    """Prüft alle aktiven Verträge auf anstehende Fristen.

    Wird täglich von Celery Beat aufgerufen (06:00 Uhr).
    Nutzt den ContractRenewalService für die eigentliche Prüfung
    und erstellt Alerts über den Alert Center Service.

    Args:
        company_id: Optional - nur für bestimmten Mandanten prüfen

    Returns:
        Statistiken über geprüften Verträge und erstellte Alerts
    """
    logger.info(
        "contract_deadline_check_started",
        company_id=company_id,
    )

    try:
        result = asyncio.run(_check_deadlines_async(company_id))
        logger.info(
            "contract_deadline_check_completed",
            contracts_checked=result.get("contracts_checked", 0),
            alerts_created=result.get("alerts_created", 0),
            deadlines_found=result.get("deadlines_found", 0),
            errors=result.get("errors", 0),
        )
        return result

    except Exception as exc:
        logger.error(
            "contract_deadline_check_failed",
            error_type=type(exc).__name__,
            **safe_error_log(exc),
        )
        raise self.retry(exc=exc)


async def _check_deadlines_async(
    company_id: Optional[str] = None,
) -> Dict[str, int]:
    """Async-Implementierung der Vertragsfristen-Prüfung.

    Öffnet eine eigene DB-Session (Celery-Kontext) und delegiert
    an den ContractRenewalService.
    """
    from uuid import UUID
    from app.db.session import get_async_session_context
    from app.services.contracts.contract_renewal_service import ContractRenewalService

    parsed_company_id: Optional[UUID] = None
    if company_id:
        parsed_company_id = UUID(company_id)

    async with get_async_session_context() as session:
        renewal_service = ContractRenewalService(session)
        stats = await renewal_service.check_upcoming_deadlines(
            company_id=parsed_company_id,
        )
        return stats
