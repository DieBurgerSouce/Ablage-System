# -*- coding: utf-8 -*-
"""
Pipeline EventBus Subscriber.

Lauscht auf IMPORT_COMPLETED Events und startet die automatische
Dokument-Verarbeitungspipeline fuer relevante Dokumenttypen.

Relevante Dokumenttypen (loesen Pipeline aus):
- invoice (Rechnung)
- order (Bestellung)
- delivery_note (Lieferschein)
- offer (Angebot)

Alle anderen Dokumenttypen werden uebersprungen.
"""

import structlog

from app.services.events.event_bus import Event, EventBus, EventType

logger = structlog.get_logger(__name__)

# Dokumenttypen, die die Pipeline ausloesen
PIPELINE_DOCUMENT_TYPES = frozenset({"invoice", "order", "delivery_note", "offer"})


async def on_import_completed(event: Event) -> None:
    """
    Handler fuer IMPORT_COMPLETED Events.

    Prueft ob der importierte Dokumenttyp relevant fuer die
    Verarbeitungspipeline ist und startet ggf. den Celery Task.

    Args:
        event: Das IMPORT_COMPLETED Event mit Payload-Keys:
               document_id, company_id, document_type, filename, ...
    """
    from app.workers.pipeline_tasks import process_document_pipeline

    payload = event.payload
    document_id = payload.get("document_id")
    company_id = payload.get("company_id")
    document_type = payload.get("document_type", "")

    if not document_id or not company_id:
        logger.warning(
            "pipeline_subscriber_missing_ids",
            event_id=str(event.event_id),
            document_id=document_id,
            company_id=company_id,
        )
        return

    if document_type not in PIPELINE_DOCUMENT_TYPES:
        logger.debug(
            "pipeline_subscriber_skipped_document_type",
            event_id=str(event.event_id),
            document_id=str(document_id),
            document_type=document_type,
        )
        return

    logger.info(
        "pipeline_subscriber_triggering_pipeline",
        event_id=str(event.event_id),
        document_id=str(document_id),
        company_id=str(company_id),
        document_type=document_type,
        source=event.source,
    )

    try:
        task = process_document_pipeline.delay(
            document_id=str(document_id),
            company_id=str(company_id),
            user_id=str(event.user_id) if event.user_id else None,
        )

        logger.info(
            "pipeline_subscriber_task_dispatched",
            document_id=str(document_id),
            company_id=str(company_id),
            document_type=document_type,
            task_id=task.id,
        )

    except Exception as exc:
        logger.error(
            "pipeline_subscriber_dispatch_failed",
            event_id=str(event.event_id),
            document_id=str(document_id),
            company_id=str(company_id),
            document_type=document_type,
            error=str(exc),
        )


def register_pipeline_subscribers(event_bus: EventBus) -> None:
    """
    Registriert alle Pipeline-Subscriber am EventBus.

    Convenience-Funktion zum Einbinden in die Anwendungs-Initialisierung
    (z.B. in app/main.py beim Startup).

    Args:
        event_bus: Die globale EventBus-Instanz
    """
    event_bus.subscribe(EventType.IMPORT_COMPLETED, on_import_completed)

    logger.info(
        "pipeline_subscribers_registered",
        event_type=EventType.IMPORT_COMPLETED.value,
        handler=on_import_completed.__name__,
    )
