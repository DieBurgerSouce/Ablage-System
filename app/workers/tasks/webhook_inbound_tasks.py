# -*- coding: utf-8 -*-
"""
Inbound Webhook Celery Tasks.

Asynchrone Verarbeitung eingehender Webhook-Events.
Publiziert gemappte Events an den EventBus und aktualisiert
den Event-Status in der Datenbank.

Feinpoliert und durchdacht - Reliable Inbound Webhook Processing.
"""

import structlog
from datetime import datetime, timezone
from typing import Any, Dict, Optional, TypedDict
from uuid import UUID

from sqlalchemy import update

from app.core.safe_errors import safe_error_log
from app.db.models_webhook_inbound import InboundWebhookEvent
from app.db.session import get_async_session_context
from app.schemas.webhook_inbound import InboundWebhookStatus
from app.workers.celery_app import celery_app
from prometheus_client import Counter, Histogram

# Prometheus Metriken fuer Webhook-Verarbeitung
WEBHOOK_PROCESSED = Counter(
    "webhook_inbound_processed_total",
    "Verarbeitete Inbound Webhooks",
    ["provider", "status"],  # status: success, failed
)
WEBHOOK_PROCESSING_DURATION = Histogram(
    "webhook_inbound_processing_seconds",
    "Webhook Verarbeitungsdauer",
    ["provider"],
)
WEBHOOK_RETRY_TOTAL = Counter(
    "webhook_inbound_retry_total",
    "Inbound Webhook Retry-Versuche",
    ["result"],  # result: retried, skipped, error
)

logger = structlog.get_logger(__name__)


class WebhookProcessResult(TypedDict, total=False):
    """Ergebnis der Webhook-Verarbeitung."""

    event_db_id: str
    provider: str
    event_type: str
    action: str
    event_bus_published: bool
    internal_event_type: str
    event_bus_error: str
    note: str


class WebhookRetryResult(TypedDict):
    """Ergebnis des Webhook-Retry-Batches."""

    checked: int
    retried: int
    skipped: int
    errors: int


@celery_app.task(
    name="app.workers.tasks.webhook_inbound_tasks.process_inbound_webhook",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    autoretry_for=(Exception,),
    retry_backoff=True,
)
def process_inbound_webhook(
    self,
    event_db_id: str,
    provider: str,
    event_type: str,
    action: str,
    data: Dict[str, Any],
    internal_event_type: Optional[str] = None,
    external_ref: Optional[str] = None,
) -> WebhookProcessResult:
    """
    Verarbeitet ein eingehendes Webhook-Event.

    1. Laedt Event aus DB
    2. Aktualisiert Status auf "processing"
    3. Publiziert auf EventBus (falls interner EventType gemappt)
    4. Aktualisiert Status auf "success"
    Bei Fehler: Status auf "failed", DLQ nach max Retries

    Args:
        event_db_id: DB-ID des InboundWebhookEvent
        provider: Provider-Name
        event_type: Provider-spezifischer Event-Typ
        action: Aktion (create, update, delete, status_change)
        data: Event-Daten
        internal_event_type: Interner EventType (nach Mapping)
        external_ref: Externe Referenz

    Returns:
        Verarbeitungsergebnis
    """
    import asyncio

    async def _process() -> WebhookProcessResult:
        async with get_async_session_context() as db:
            # Update status to processing
            await db.execute(
                update(InboundWebhookEvent)
                .where(InboundWebhookEvent.id == UUID(event_db_id))
                .values(
                    status=InboundWebhookStatus.PROCESSING.value,
                    attempts=InboundWebhookEvent.attempts + 1,
                    last_attempt_at=datetime.now(timezone.utc),
                    task_id=self.request.id,
                )
            )
            await db.commit()

            result: Dict[str, Any] = {
                "event_db_id": event_db_id,
                "provider": provider,
                "event_type": event_type,
                "action": action,
            }

            # Publish to EventBus if internal event type is mapped
            if internal_event_type:
                try:
                    from app.services.events.event_bus import EventType, get_event_bus

                    event_bus = get_event_bus()
                    internal_type = EventType(internal_event_type)

                    await event_bus.publish_event(
                        event_type=internal_type,
                        payload={
                            "source_provider": provider,
                            "source_event_type": event_type,
                            "action": action,
                            "external_ref": external_ref,
                            "data": data,
                        },
                        source=f"inbound_webhook:{provider}",
                    )

                    result["event_bus_published"] = True
                    result["internal_event_type"] = internal_event_type

                    logger.info(
                        "inbound_webhook_event_published",
                        provider=provider,
                        event_type=event_type,
                        internal_event_type=internal_event_type,
                    )

                except Exception as e:
                    logger.warning(
                        "inbound_webhook_eventbus_publish_failed",
                        provider=provider,
                        **safe_error_log(e),
                    )
                    result["event_bus_published"] = False
                    result["event_bus_error"] = str(e)
            else:
                result["event_bus_published"] = False
                result["note"] = "Kein internes Event-Mapping für diesen Event-Typ"

            # Update status to success
            await db.execute(
                update(InboundWebhookEvent)
                .where(InboundWebhookEvent.id == UUID(event_db_id))
                .values(
                    status=InboundWebhookStatus.SUCCESS.value,
                    processed_at=datetime.now(timezone.utc),
                )
            )
            await db.commit()

            logger.info(
                "inbound_webhook_processed",
                provider=provider,
                event_db_id=event_db_id,
                event_type=event_type,
            )

            return result

    try:
        with WEBHOOK_PROCESSING_DURATION.labels(provider=provider).time():
            result = asyncio.run(_process())
        WEBHOOK_PROCESSED.labels(provider=provider, status="success").inc()
        return result
    except Exception as e:
        WEBHOOK_PROCESSED.labels(provider=provider, status="failed").inc()
        logger.error(
            "inbound_webhook_processing_failed",
            event_db_id=event_db_id,
            provider=provider,
            attempt=self.request.retries + 1,
            **safe_error_log(e),
        )

        # Update status to failed on final retry
        if self.request.retries >= self.max_retries:
            try:
                asyncio.run(_mark_failed(event_db_id, str(e)))
            except Exception as mark_err:
                # Status-Update auf 'failed' fehlgeschlagen: Original-Fehler wird trotzdem erneut geworfen
                logger.debug(
                    "webhook_mark_failed_error",
                    event_db_id=event_db_id,
                    **safe_error_log(mark_err),
                )

        raise


async def _mark_failed(event_db_id: str, error_message: str) -> None:
    """Markiert Event als fehlgeschlagen nach max Retries."""
    async with get_async_session_context() as db:
        await db.execute(
            update(InboundWebhookEvent)
            .where(InboundWebhookEvent.id == UUID(event_db_id))
            .values(
                status=InboundWebhookStatus.FAILED.value,
                error_message=error_message[:2000],  # Truncate error message
            )
        )
        await db.commit()


@celery_app.task(
    name="app.workers.tasks.webhook_inbound_tasks.retry_failed_inbound_webhooks",
    bind=True,
    max_retries=1,
    soft_time_limit=60,
    time_limit=120,
)
def retry_failed_inbound_webhooks(self) -> WebhookRetryResult:
    """Periodischer Retry fehlgeschlagener Inbound Webhook Events.

    Wird alle 30 Minuten via Celery Beat aufgerufen.
    Laedt alle Events mit status=FAILED und attempts < 5,
    und queued sie erneut als process_inbound_webhook Tasks.

    Returns:
        Dict mit Retry-Statistiken
    """
    import asyncio

    async def _retry_failed() -> WebhookRetryResult:
        from sqlalchemy import select, and_

        stats: Dict[str, Any] = {
            "checked": 0,
            "retried": 0,
            "skipped": 0,
            "errors": 0,
        }

        async with get_async_session_context() as db:
            result = await db.execute(
                select(InboundWebhookEvent).where(
                    and_(
                        InboundWebhookEvent.status == InboundWebhookStatus.FAILED.value,
                        InboundWebhookEvent.attempts < 5,
                    )
                ).limit(50)
            )
            events = result.scalars().all()
            stats["checked"] = len(events)

            for event in events:
                try:
                    process_inbound_webhook.delay(
                        event_db_id=str(event.id),
                        provider=event.provider,
                        event_type=event.event_type,
                        action=event.action or "unknown",
                        data=event.payload_sanitized or {},
                        internal_event_type=event.internal_event_type,
                        external_ref=event.external_ref,
                    )
                    stats["retried"] += 1
                    WEBHOOK_RETRY_TOTAL.labels(result="retried").inc()

                    logger.info(
                        "webhook_inbound_retry_queued",
                        event_id=str(event.id),
                        provider=event.provider,
                        attempts=event.attempts,
                    )

                except Exception as e:
                    stats["errors"] += 1
                    WEBHOOK_RETRY_TOTAL.labels(result="error").inc()
                    logger.warning(
                        "webhook_inbound_retry_queue_failed",
                        event_id=str(event.id),
                        **safe_error_log(e),
                    )

        return stats

    try:
        result = asyncio.run(_retry_failed())
        logger.info(
            "webhook_inbound_retry_batch_completed",
            **{k: v for k, v in result.items() if k != "errors" or v > 0},
        )
        return result
    except Exception as e:
        logger.error("webhook_inbound_retry_batch_failed", **safe_error_log(e))
        raise self.retry(exc=e)
