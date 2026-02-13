"""Escalation Chain Advancement Tasks.

Celery-Beat-Task fuer automatische Eskalationsfortschritt-Pruefung.
Prueft alle aktiven Eskalationen und fuehrt faellige Eskalationsstufen aus.
"""

from __future__ import annotations

from typing import Dict, List
import structlog
from app.workers.celery_app import celery_app
from app.core.safe_errors import safe_error_log
from app.db.session import async_session_factory

logger = structlog.get_logger(__name__)


@celery_app.task(
    name="app.workers.tasks.escalation_tasks.advance_pending_escalations_task",
    bind=True,
    acks_late=True,
    max_retries=3,
    default_retry_delay=120,
)
def advance_pending_escalations_task(self) -> Dict[str, object]:
    """Prueft und eskaliert faellige Benachrichtigungen.

    Wird alle 15 Minuten via Celery Beat ausgefuehrt.
    Ruft den EscalationChainService auf um alle aktiven
    Eskalationen zu pruefen und ggf. zur naechsten Stufe zu eskalieren.

    Returns:
        Dictionary mit Statistiken
    """
    import asyncio

    async def _advance() -> Dict[str, object]:
        async with async_session_factory() as db:
            from app.services.notification.escalation_chain_service import (
                EscalationChainService,
            )
            service = EscalationChainService(db)
            escalated = await service.check_escalations()

            return {
                "escalated_count": len(escalated),
                "escalated": escalated,
            }

    try:
        result = asyncio.get_event_loop().run_until_complete(_advance())
        logger.info(
            "escalation_check_completed",
            escalated_count=result["escalated_count"],
        )
        return result
    except Exception as e:
        logger.error(
            "escalation_check_failed",
            **safe_error_log(e),
        )
        raise self.retry(exc=e)
