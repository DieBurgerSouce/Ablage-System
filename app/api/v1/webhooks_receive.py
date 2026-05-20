# -*- coding: utf-8 -*-
"""
Inbound Webhook Receive Endpoints.

Generischer Empfänger für eingehende Webhooks von externen Providern
(DATEV, DHL, DPD, UPS, GLS). Verwendet ein Provider-Registry für
DRY Event-Verarbeitung.

Endpunkt-Pattern:
  POST /api/v1/webhooks/receive/{provider}/{config_id}

Feinpoliert und durchdacht - Single Receiver, Multiple Providers.
"""

from typing import Optional
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select, func as sa_func
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db
from app.db.models_webhook_inbound import InboundWebhookEvent
from app.schemas.webhook_inbound import (
    InboundWebhookEventList,
    InboundWebhookEventSummary,
    InboundWebhookProvider,
    InboundWebhookResponse,
    InboundWebhookStatus,
)
from app.services.webhooks.inbound_service import InboundWebhookService
from app.services.webhooks.providers import PROVIDER_REGISTRY

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/webhooks/receive", tags=["webhooks-inbound"])


# =============================================================================
# Webhook Receive Endpoint
# =============================================================================


@router.post(
    "/{provider}/{config_id}",
    response_model=InboundWebhookResponse,
    summary="Inbound Webhook empfangen",
    description=(
        "Empfängt eingehende Webhooks von externen Providern. "
        "Verifiziert HMAC-SHA256 Signatur, prüft Idempotenz und "
        "reiht Event zur asynchronen Verarbeitung ein."
    ),
    responses={
        401: {"description": "Ungültige Signatur oder Timestamp"},
        404: {"description": "Provider-Konfiguration nicht gefunden"},
        413: {"description": "Payload zu gross"},
    },
)
async def receive_webhook(
    provider: InboundWebhookProvider,
    config_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> InboundWebhookResponse:
    """Empfängt und verarbeitet einen eingehenden Webhook."""
    adapter = PROVIDER_REGISTRY.get(provider.value)
    if not adapter:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unbekannter Provider: {provider.value}",
        )

    # Extract provider-specific signature headers
    signature = request.headers.get(adapter.signature_header)
    timestamp = request.headers.get(adapter.timestamp_header)
    webhook_id = request.headers.get(adapter.webhook_id_header)

    service = InboundWebhookService(db)
    return await service.process_webhook(
        provider=provider.value,
        config_id=config_id,
        request=request,
        signature=signature,
        timestamp=timestamp,
        webhook_id=webhook_id,
        adapter=adapter,
    )


# =============================================================================
# Event Listing & Retry Endpoints
# =============================================================================


@router.get(
    "/{provider}/events",
    response_model=InboundWebhookEventList,
    summary="Inbound Webhook-Events auflisten",
    description="Listet empfangene Webhook-Events für einen Provider auf.",
)
async def list_inbound_events(
    provider: InboundWebhookProvider,
    limit: int = Query(50, ge=1, le=500),
    status_filter: Optional[str] = Query(None, alias="status"),
    db: AsyncSession = Depends(get_db),
) -> InboundWebhookEventList:
    """Listet Inbound-Webhook-Events auf."""
    query = select(InboundWebhookEvent).where(
        InboundWebhookEvent.provider == provider.value
    )

    if status_filter:
        query = query.where(InboundWebhookEvent.status == status_filter)

    query = query.order_by(InboundWebhookEvent.received_at.desc()).limit(limit)

    result = await db.execute(query)
    events = result.scalars().all()

    return InboundWebhookEventList(
        events=[
            InboundWebhookEventSummary(
                id=e.id,
                provider=e.provider,
                event_id=e.event_id,
                event_type=e.event_type,
                action=e.action,
                status=e.status,
                external_ref=e.external_ref,
                internal_event_type=e.internal_event_type,
                received_at=e.received_at,
                processed_at=e.processed_at,
                attempts=e.attempts,
                error_message=e.error_message,
            )
            for e in events
        ],
        total=len(events),
    )


@router.post(
    "/{provider}/events/{event_id}/retry",
    summary="Fehlgeschlagenes Event erneut verarbeiten",
    description="Reiht ein fehlgeschlagenes Inbound-Webhook-Event zur erneuten Verarbeitung ein.",
)
async def retry_inbound_event(
    provider: InboundWebhookProvider,
    event_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Verarbeitet ein fehlgeschlagenes Event erneut."""
    from sqlalchemy import and_

    result = await db.execute(
        select(InboundWebhookEvent).where(
            and_(
                InboundWebhookEvent.id == event_id,
                InboundWebhookEvent.provider == provider.value,
            )
        )
    )
    event = result.scalar_one_or_none()

    if not event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Event nicht gefunden",
        )

    if event.status == InboundWebhookStatus.SUCCESS.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Event wurde bereits erfolgreich verarbeitet",
        )

    # Queue retry
    from app.workers.tasks.webhook_inbound_tasks import process_inbound_webhook

    task = process_inbound_webhook.delay(
        event_db_id=str(event.id),
        provider=event.provider,
        event_type=event.event_type,
        action=event.action,
        data=event.payload_preview or {},
        internal_event_type=event.internal_event_type,
        external_ref=event.external_ref,
    )

    return {
        "message": "Retry eingereiht",
        "event_id": str(event_id),
        "task_id": task.id,
    }
