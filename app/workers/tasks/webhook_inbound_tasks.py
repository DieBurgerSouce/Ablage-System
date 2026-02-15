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
from typing import Any, Dict, Optional
from uuid import UUID

from sqlalchemy import update

from app.core.safe_errors import safe_error_log
from app.db.models_webhook_inbound import InboundWebhookEvent
from app.db.session import get_async_session_context
from app.schemas.webhook_inbound import InboundWebhookStatus
from app.workers.celery_app import celery_app

logger = structlog.get_logger(__name__)


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
) -> Dict[str, Any]:
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

    async def _process() -> Dict[str, Any]:
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
                result["note"] = "Kein internes Event-Mapping fuer diesen Event-Typ"

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
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                return pool.submit(asyncio.run, _process()).result()
        return asyncio.run(_process())
    except Exception as e:
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
            except Exception:
                pass

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
