"""
Webhook Management API Endpoints.

Ermöglicht CRUD-Operationen für Webhook-Abonnements:
- Webhook erstellen/aktualisieren/löschen
- Event-Filter konfigurieren
- Secret-Rotation
- Test-Webhooks senden
- Zustellungsprotokoll einsehen

Feinpoliert und durchdacht - Enterprise-grade Webhooks.
"""

import secrets
import structlog
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, update

from app.db.models import User, WebhookSubscription, WebhookDelivery
from app.api.dependencies import get_current_user, get_db
from app.core.webhook_signature import (
    generate_signature_header,
    SIGNATURE_HEADER_NAME,
)
from app.db.schemas import (
    WebhookSubscriptionCreate,
    WebhookSubscriptionUpdate,
    WebhookSubscriptionResponse,
    WebhookSubscriptionWithSecret,
    WebhookSecretRotateResponse,
    WebhookDeliveryResponse,
    WebhookDeliveryListResponse,
    WebhookListResponse,
    WebhookTestRequest,
    WebhookTestResponse,
)

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


def generate_webhook_secret() -> str:
    """Generiert ein sicheres Webhook-Secret."""
    return f"whsec_{secrets.token_urlsafe(32)}"


@router.post(
    "/",
    response_model=WebhookSubscriptionWithSecret,
    status_code=status.HTTP_201_CREATED,
    summary="Webhook erstellen",
    description="Erstellt ein neues Webhook-Abonnement für Event-Benachrichtigungen."
)
async def create_webhook(
    webhook_data: WebhookSubscriptionCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> WebhookSubscriptionWithSecret:
    """
    Erstellt ein neues Webhook-Abonnement.

    Das Secret wird nur bei der Erstellung angezeigt und kann später
    nicht mehr abgerufen werden. Bei Verlust muss es rotiert werden.
    """
    # Generiere Secret
    secret = generate_webhook_secret()

    # Erstelle Webhook
    webhook = WebhookSubscription(
        user_id=current_user.id,
        name=webhook_data.name,
        url=webhook_data.url,
        description=webhook_data.description,
        event_types=webhook_data.event_types,
        headers=webhook_data.headers,
        secret=secret,
        max_retries=webhook_data.max_retries,
        retry_delay_seconds=webhook_data.retry_delay_seconds,
    )

    db.add(webhook)
    await db.commit()
    await db.refresh(webhook)

    logger.info(
        "webhook_created",
        webhook_id=str(webhook.id),
        user_id=str(current_user.id),
        event_types=webhook_data.event_types
    )

    # Rückgabe mit Secret (nur einmalig!)
    response = WebhookSubscriptionWithSecret.model_validate(webhook)
    response.secret = secret
    return response


@router.get(
    "/",
    response_model=WebhookListResponse,
    summary="Webhooks auflisten",
    description="Gibt alle Webhook-Abonnements des aktuellen Benutzers zurück."
)
async def list_webhooks(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    is_active: Optional[bool] = Query(None, description="Nach Aktivstatus filtern"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> WebhookListResponse:
    """Liste aller Webhook-Abonnements des Benutzers."""
    query = select(WebhookSubscription).where(
        WebhookSubscription.user_id == current_user.id
    )

    if is_active is not None:
        query = query.where(WebhookSubscription.is_active == is_active)

    # Total count
    count_query = select(func.count(WebhookSubscription.id)).where(
        WebhookSubscription.user_id == current_user.id
    )
    if is_active is not None:
        count_query = count_query.where(WebhookSubscription.is_active == is_active)

    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Fetch webhooks
    query = query.order_by(WebhookSubscription.created_at.desc()).limit(limit).offset(offset)
    result = await db.execute(query)
    webhooks = result.scalars().all()

    return WebhookListResponse(
        total=total,
        webhooks=[WebhookSubscriptionResponse.model_validate(w) for w in webhooks]
    )


@router.get(
    "/{webhook_id}",
    response_model=WebhookSubscriptionResponse,
    summary="Webhook-Details",
    description="Gibt Details eines spezifischen Webhook-Abonnements zurück."
)
async def get_webhook(
    webhook_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> WebhookSubscriptionResponse:
    """Webhook-Details abrufen."""
    result = await db.execute(
        select(WebhookSubscription).where(
            WebhookSubscription.id == webhook_id,
            WebhookSubscription.user_id == current_user.id
        )
    )
    webhook = result.scalar_one_or_none()

    if not webhook:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Webhook nicht gefunden"
        )

    return WebhookSubscriptionResponse.model_validate(webhook)


@router.patch(
    "/{webhook_id}",
    response_model=WebhookSubscriptionResponse,
    summary="Webhook aktualisieren",
    description="Aktualisiert ein Webhook-Abonnement."
)
async def update_webhook(
    webhook_id: UUID,
    webhook_data: WebhookSubscriptionUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> WebhookSubscriptionResponse:
    """Webhook aktualisieren."""
    result = await db.execute(
        select(WebhookSubscription).where(
            WebhookSubscription.id == webhook_id,
            WebhookSubscription.user_id == current_user.id
        )
    )
    webhook = result.scalar_one_or_none()

    if not webhook:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Webhook nicht gefunden"
        )

    # Update fields
    update_data = webhook_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(webhook, field, value)

    await db.commit()
    await db.refresh(webhook)

    logger.info(
        "webhook_updated",
        webhook_id=str(webhook_id),
        user_id=str(current_user.id),
        updated_fields=list(update_data.keys())
    )

    return WebhookSubscriptionResponse.model_validate(webhook)


@router.delete(
    "/{webhook_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Webhook löschen",
    description="Löscht ein Webhook-Abonnement und alle zugehörigen Zustellungsprotokolle."
)
async def delete_webhook(
    webhook_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> None:
    """Webhook löschen."""
    result = await db.execute(
        select(WebhookSubscription).where(
            WebhookSubscription.id == webhook_id,
            WebhookSubscription.user_id == current_user.id
        )
    )
    webhook = result.scalar_one_or_none()

    if not webhook:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Webhook nicht gefunden"
        )

    await db.delete(webhook)
    await db.commit()

    logger.info(
        "webhook_deleted",
        webhook_id=str(webhook_id),
        user_id=str(current_user.id)
    )


@router.post(
    "/{webhook_id}/rotate-secret",
    response_model=WebhookSecretRotateResponse,
    summary="Secret rotieren",
    description="Rotiert das HMAC-Secret eines Webhooks. Das alte Secret wird sofort ungültig."
)
async def rotate_webhook_secret(
    webhook_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> WebhookSecretRotateResponse:
    """Webhook-Secret rotieren."""
    result = await db.execute(
        select(WebhookSubscription).where(
            WebhookSubscription.id == webhook_id,
            WebhookSubscription.user_id == current_user.id
        )
    )
    webhook = result.scalar_one_or_none()

    if not webhook:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Webhook nicht gefunden"
        )

    # Generiere neues Secret
    new_secret = generate_webhook_secret()
    webhook.secret = new_secret

    await db.commit()

    logger.info(
        "webhook_secret_rotated",
        webhook_id=str(webhook_id),
        user_id=str(current_user.id)
    )

    return WebhookSecretRotateResponse(
        id=webhook.id,
        secret=new_secret,
        rotated_at=datetime.now(timezone.utc)
    )


@router.post(
    "/{webhook_id}/test",
    response_model=WebhookTestResponse,
    summary="Test-Webhook senden",
    description="Sendet einen Test-Webhook an den konfigurierten Endpoint."
)
async def test_webhook(
    webhook_id: UUID,
    test_data: WebhookTestRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> WebhookTestResponse:
    """Test-Webhook an den Endpoint senden."""
    import httpx
    import json
    import time

    result = await db.execute(
        select(WebhookSubscription).where(
            WebhookSubscription.id == webhook_id,
            WebhookSubscription.user_id == current_user.id
        )
    )
    webhook = result.scalar_one_or_none()

    if not webhook:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Webhook nicht gefunden"
        )

    # Test-Payload erstellen
    timestamp = int(time.time())
    payload = {
        "event_id": f"test_{secrets.token_hex(8)}",
        "event_type": test_data.event_type,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "api_version": "v1",
        "test": True,
        "data": {
            "document_id": "test_document_id",
            "filename": "test_document.pdf",
            "message": "Dies ist ein Test-Webhook vom Ablage-System"
        }
    }

    # Signatur generieren (neues Format mit Timestamp-Schutz)
    payload_bytes = json.dumps(payload, separators=(',', ':')).encode('utf-8')
    signature = generate_signature_header(payload_bytes, webhook.secret, timestamp)

    # Headers vorbereiten
    headers = {
        "Content-Type": "application/json",
        SIGNATURE_HEADER_NAME: signature,
        "X-Webhook-Delivery-ID": payload["event_id"],
        "X-Webhook-Timestamp": str(timestamp),
        "X-Webhook-Test": "true",
        "User-Agent": "Ablage-Webhook/1.0"
    }
    if webhook.headers:
        headers.update(webhook.headers)

    # Webhook senden
    start_time = time.time()
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                webhook.url,
                content=payload_bytes,
                headers=headers
            )

        response_time_ms = int((time.time() - start_time) * 1000)

        logger.info(
            "webhook_test_sent",
            webhook_id=str(webhook_id),
            status_code=response.status_code,
            response_time_ms=response_time_ms
        )

        return WebhookTestResponse(
            success=response.status_code in [200, 201, 202, 204],
            status_code=response.status_code,
            response_time_ms=response_time_ms,
            error=None if response.status_code < 400 else response.text[:500]
        )

    except httpx.TimeoutException:
        logger.warning("webhook_test_timeout", webhook_id=str(webhook_id))
        return WebhookTestResponse(
            success=False,
            status_code=None,
            response_time_ms=30000,
            error="Timeout: Keine Antwort innerhalb von 30 Sekunden"
        )

    except httpx.ConnectError as e:
        logger.warning("webhook_test_connection_error", webhook_id=str(webhook_id), error=str(e))
        return WebhookTestResponse(
            success=False,
            status_code=None,
            response_time_ms=None,
            error=f"Verbindungsfehler: {str(e)}"
        )

    except Exception as e:
        logger.error("webhook_test_error", webhook_id=str(webhook_id), error=str(e))
        return WebhookTestResponse(
            success=False,
            status_code=None,
            response_time_ms=None,
            error=f"Fehler: {str(e)}"
        )


@router.get(
    "/{webhook_id}/deliveries",
    response_model=WebhookDeliveryListResponse,
    summary="Zustellungsprotokoll",
    description="Gibt das Zustellungsprotokoll eines Webhooks zurück."
)
async def list_webhook_deliveries(
    webhook_id: UUID,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    status_filter: Optional[str] = Query(None, alias="status", description="Nach Status filtern"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> WebhookDeliveryListResponse:
    """Zustellungsprotokoll eines Webhooks."""
    # Prüfe ob Webhook existiert und gehört dem User
    webhook_result = await db.execute(
        select(WebhookSubscription).where(
            WebhookSubscription.id == webhook_id,
            WebhookSubscription.user_id == current_user.id
        )
    )
    webhook = webhook_result.scalar_one_or_none()

    if not webhook:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Webhook nicht gefunden"
        )

    # Query deliveries
    query = select(WebhookDelivery).where(
        WebhookDelivery.subscription_id == webhook_id
    )

    if status_filter:
        query = query.where(WebhookDelivery.status == status_filter)

    # Total count
    count_query = select(func.count(WebhookDelivery.id)).where(
        WebhookDelivery.subscription_id == webhook_id
    )
    if status_filter:
        count_query = count_query.where(WebhookDelivery.status == status_filter)

    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Fetch deliveries
    query = query.order_by(WebhookDelivery.created_at.desc()).limit(limit).offset(offset)
    result = await db.execute(query)
    deliveries = result.scalars().all()

    return WebhookDeliveryListResponse(
        subscription_id=webhook_id,
        total=total,
        deliveries=[WebhookDeliveryResponse.model_validate(d) for d in deliveries]
    )


@router.post(
    "/{webhook_id}/activate",
    response_model=WebhookSubscriptionResponse,
    summary="Webhook aktivieren",
    description="Aktiviert ein deaktiviertes Webhook-Abonnement."
)
async def activate_webhook(
    webhook_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> WebhookSubscriptionResponse:
    """Webhook aktivieren."""
    result = await db.execute(
        select(WebhookSubscription).where(
            WebhookSubscription.id == webhook_id,
            WebhookSubscription.user_id == current_user.id
        )
    )
    webhook = result.scalar_one_or_none()

    if not webhook:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Webhook nicht gefunden"
        )

    webhook.is_active = True
    await db.commit()
    await db.refresh(webhook)

    logger.info("webhook_activated", webhook_id=str(webhook_id))

    return WebhookSubscriptionResponse.model_validate(webhook)


@router.post(
    "/{webhook_id}/deactivate",
    response_model=WebhookSubscriptionResponse,
    summary="Webhook deaktivieren",
    description="Deaktiviert ein Webhook-Abonnement (stoppt Zustellungen)."
)
async def deactivate_webhook(
    webhook_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> WebhookSubscriptionResponse:
    """Webhook deaktivieren."""
    result = await db.execute(
        select(WebhookSubscription).where(
            WebhookSubscription.id == webhook_id,
            WebhookSubscription.user_id == current_user.id
        )
    )
    webhook = result.scalar_one_or_none()

    if not webhook:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Webhook nicht gefunden"
        )

    webhook.is_active = False
    await db.commit()
    await db.refresh(webhook)

    logger.info("webhook_deactivated", webhook_id=str(webhook_id))

    return WebhookSubscriptionResponse.model_validate(webhook)
