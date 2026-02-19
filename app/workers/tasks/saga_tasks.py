"""Saga Tasks - Celery Tasks fuer Saga-Pattern Wartung.

Automatisierte Tasks fuer:
- Dead Letter Queue Processing (fehlgeschlagene Sagas wiederholen)
- DLQ Metriken aktualisieren
"""

import uuid
from typing import Optional, TypedDict

import structlog
from prometheus_client import Gauge

from app.core.safe_errors import safe_error_log, safe_error_detail
from app.db.session import async_session_factory
from app.db.models import Company
from app.workers.celery_app import celery_app
from sqlalchemy import select, and_

logger = structlog.get_logger(__name__)


class DLQProcessingResult(TypedDict):
    total_in_dlq: int
    retried: int
    skipped_max_retries: int
    errors: int


# Prometheus Metriken
SAGA_DLQ_PROCESSED = Gauge(
    "saga_dlq_processed_total",
    "Anzahl verarbeiteter Sagas aus der Dead Letter Queue",
)


@celery_app.task(
    name="saga.process_dead_letter_queue",
    bind=True,
    max_retries=0,
    soft_time_limit=120,
    time_limit=180,
)
def process_dead_letter_queue(self) -> DLQProcessingResult:
    """Verarbeitet Sagas in der Dead Letter Queue.

    Fuer jede Saga in der DLQ:
    - Pruefen ob retry moeglich (retry_count < max_retries)
    - Wenn ja: retry_saga() aufrufen
    - Wenn nein: Alert erstellen, Saga im DLQ belassen

    Wird halbstuendlich via Celery Beat ausgefuehrt.

    Returns:
        Dictionary mit Verarbeitungsergebnis
    """
    import asyncio

    async def _process():
        async with async_session_factory() as db:
            return await _process_dlq(db)

    try:
        result = asyncio.run(_process())
        logger.info("saga_dlq_processing_completed", **result)
        return result
    except Exception as e:
        logger.error("saga_dlq_processing_failed", **safe_error_log(e))
        raise


async def _process_dlq(db) -> DLQProcessingResult:
    """Interne Funktion fuer DLQ-Verarbeitung."""
    from app.db.models_workflow_versioning import Saga, SagaStatus
    from app.services.workflow.saga_service import SagaService

    results = {
        "total_in_dlq": 0,
        "retried": 0,
        "skipped_max_retries": 0,
        "errors": 0,
    }

    # Alle Sagas in der DLQ laden
    query = (
        select(Saga)
        .where(
            and_(
                Saga.in_dead_letter_queue == True,  # noqa: E712
                Saga.status != SagaStatus.COMPLETED.value,
            )
        )
        .order_by(Saga.dead_letter_at)
        .limit(50)
    )

    result = await db.execute(query)
    dlq_sagas = result.scalars().all()
    results["total_in_dlq"] = len(dlq_sagas)

    SAGA_DLQ_PROCESSED.set(len(dlq_sagas))

    for saga in dlq_sagas:
        try:
            if saga.retry_count < saga.max_retries:
                saga_service = SagaService(db)
                retried = await saga_service.retry_saga(
                    saga_id=saga.id,
                    company_id=saga.company_id,
                    user_id=saga.initiated_by_id or uuid.UUID(int=0),
                )
                if retried:
                    results["retried"] += 1
                    logger.info(
                        "saga_dlq_retry_success",
                        saga_id=str(saga.id),
                        retry_count=saga.retry_count,
                    )
                else:
                    results["skipped_max_retries"] += 1
            else:
                results["skipped_max_retries"] += 1
                logger.warning(
                    "saga_dlq_max_retries_exceeded",
                    saga_id=str(saga.id),
                    retry_count=saga.retry_count,
                    max_retries=saga.max_retries,
                )

                # Alert erstellen
                await _create_dlq_alert(db, saga)

        except Exception as e:
            results["errors"] += 1
            logger.error(
                "saga_dlq_processing_error",
                saga_id=str(saga.id),
                **safe_error_log(e),
            )

    return results


async def _create_dlq_alert(db, saga) -> None:
    """Erstellt einen Alert fuer eine Saga die nicht mehr retried werden kann."""
    try:
        from app.services.alert_center_service import AlertCenterService

        alert_service = AlertCenterService(db)
        await alert_service.create_alert(
            company_id=saga.company_id,
            alert_type="saga_dlq_stuck",
            severity="high",
            title=f"Saga '{saga.name}' in Dead Letter Queue blockiert",
            message=(
                f"Saga {saga.id} hat {saga.retry_count}/{saga.max_retries} "
                f"Versuche erreicht. Grund: {saga.dead_letter_reason or 'Unbekannt'}. "
                "Manuelle Intervention erforderlich."
            ),
            metadata={
                "saga_id": str(saga.id),
                "saga_name": saga.name,
                "retry_count": saga.retry_count,
                "dead_letter_reason": saga.dead_letter_reason,
            },
        )
    except Exception as alert_err:
        logger.warning(
            "saga_dlq_alert_creation_failed",
            saga_id=str(saga.id),
            error_type=type(alert_err).__name__,
        )
