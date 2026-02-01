"""
Odoo Webhook API Endpoints.

Phase 6: Odoo Integration Deepening
- Real-time sync via webhooks
- HMAC-SHA256 signature verification
- Idempotent event processing
- Rate limiting

Feinpoliert und durchdacht - Enterprise-grade Webhook Security.
"""

import hashlib
import hmac
import structlog
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db
from app.core.config import settings
from app.core.safe_errors import safe_error_detail, safe_error_log
from app.db.session import get_async_session_context
from app.schemas.odoo import (
    OdooWebhookPayload,
    OdooWebhookResponse,
    OdooWebhookEventType,
    OdooWebhookAction,
    OdooWebhookStatus,
    OdooCustomerWebhook,
    OdooSupplierWebhook,
    OdooInvoiceWebhook,
    OdooPaymentWebhook,
    OdooProductWebhook,
)

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/odoo/webhooks", tags=["odoo-webhooks"])


# =============================================================================
# Constants
# =============================================================================

# Maximum payload size (1MB)
MAX_PAYLOAD_SIZE = 1024 * 1024

# Webhook signature header name (configurable)
SIGNATURE_HEADER = "X-Odoo-Webhook-Signature"
TIMESTAMP_HEADER = "X-Odoo-Webhook-Timestamp"
WEBHOOK_ID_HEADER = "X-Odoo-Webhook-Id"

# Signature tolerance (5 minutes)
SIGNATURE_TIMESTAMP_TOLERANCE_SECONDS = 300


# =============================================================================
# Helper Functions
# =============================================================================


def compute_payload_hash(payload: bytes) -> str:
    """Berechnet SHA-256 Hash des Payloads."""
    return hashlib.sha256(payload).hexdigest()


def verify_webhook_signature(
    payload: bytes,
    signature: str,
    timestamp: str,
    webhook_secret: str,
) -> bool:
    """
    Verifiziert die HMAC-SHA256 Signatur eines Webhooks.

    Die Signatur wird berechnet als:
    HMAC-SHA256(webhook_secret, timestamp + "." + payload)

    Args:
        payload: Roher Request Body
        signature: Signatur aus Header
        timestamp: Timestamp aus Header
        webhook_secret: Webhook Secret fuer diese Verbindung

    Returns:
        True wenn Signatur gueltig
    """
    try:
        # Baue die zu signierende Nachricht
        message = f"{timestamp}.".encode() + payload

        # Berechne erwartete Signatur
        expected_signature = hmac.new(
            webhook_secret.encode(),
            message,
            hashlib.sha256
        ).hexdigest()

        # Sichere Vergleichsfunktion (timing-safe)
        return hmac.compare_digest(signature, expected_signature)

    except Exception as e:
        logger.warning("webhook_signature_verification_failed", error=str(e))
        return False


def validate_timestamp(timestamp_str: str) -> bool:
    """
    Validiert dass der Timestamp nicht zu alt ist.

    Schuetzt gegen Replay-Attacken.
    """
    try:
        # Parse Unix timestamp
        timestamp = int(timestamp_str)
        now = int(datetime.now(timezone.utc).timestamp())

        # Check tolerance
        return abs(now - timestamp) <= SIGNATURE_TIMESTAMP_TOLERANCE_SECONDS

    except (ValueError, TypeError):
        return False


def sanitize_payload_for_preview(data: dict) -> dict:
    """
    Entfernt PII aus Payload fuer sichere Speicherung.

    SECURITY: Entfernt Namen, Adressen, IBANs, etc.
    """
    # Felder die entfernt werden sollen (PII)
    pii_fields = {
        "name", "email", "phone", "mobile", "street", "street2",
        "city", "zip", "vat", "bank_ids", "iban", "bic",
        "contact_address", "comment", "ref", "title"
    }

    sanitized = {}
    for key, value in data.items():
        if key.lower() in pii_fields:
            sanitized[key] = "[REDACTED]"
        elif isinstance(value, dict):
            sanitized[key] = sanitize_payload_for_preview(value)
        elif isinstance(value, list) and len(value) > 0 and isinstance(value[0], dict):
            sanitized[key] = [sanitize_payload_for_preview(v) if isinstance(v, dict) else v for v in value]
        else:
            sanitized[key] = value

    return sanitized


async def get_webhook_secret(db: AsyncSession, connection_id: UUID) -> Optional[str]:
    """
    Holt das Webhook-Secret fuer eine ERP-Verbindung.

    Das Secret wird aus dem encrypted_api_key abgeleitet
    (in Produktion separat gespeichert).
    """
    from app.db.models import ERPConnection
    from app.core.encryption import decrypt_data, DecryptionError

    result = await db.execute(
        select(ERPConnection).where(
            and_(
                ERPConnection.id == connection_id,
                ERPConnection.is_active == True,
            )
        )
    )
    connection = result.scalar_one_or_none()

    if not connection:
        return None

    # Derive webhook secret from API key
    # In production, this should be a separate secret
    try:
        api_key = decrypt_data(
            connection.encrypted_api_key,
            associated_data=f"erp:{connection.company_id}"
        )
        # Derive a separate key for webhook verification
        webhook_secret = hashlib.sha256(
            f"webhook:{api_key}".encode()
        ).hexdigest()[:32]
        return webhook_secret

    except DecryptionError:
        logger.error("webhook_secret_decryption_failed", connection_id=str(connection_id))
        return None


async def check_event_processed(
    db: AsyncSession,
    connection_id: UUID,
    event_id: str,
) -> bool:
    """
    Prueft ob ein Event bereits verarbeitet wurde (Idempotenz).

    Returns:
        True wenn bereits verarbeitet
    """
    from app.db.models import OdooWebhookEvent

    result = await db.execute(
        select(OdooWebhookEvent).where(
            and_(
                OdooWebhookEvent.connection_id == connection_id,
                OdooWebhookEvent.event_id == event_id,
            )
        )
    )
    event = result.scalar_one_or_none()

    if event and event.status in (OdooWebhookStatus.SUCCESS.value, OdooWebhookStatus.PROCESSING.value):
        return True

    return False


async def store_webhook_event(
    db: AsyncSession,
    connection_id: UUID,
    event_id: str,
    event_type: str,
    action: str,
    payload_hash: str,
    payload_preview: dict,
    odoo_record_id: Optional[str] = None,
) -> UUID:
    """
    Speichert Webhook-Event fuer Tracking und Idempotenz.

    Returns:
        ID des erstellten Events
    """
    from app.db.models import OdooWebhookEvent
    import uuid

    event = OdooWebhookEvent(
        id=uuid.uuid4(),
        connection_id=connection_id,
        event_id=event_id,
        event_type=event_type,
        action=action,
        payload_hash=payload_hash,
        payload_preview=payload_preview,
        odoo_record_id=odoo_record_id,
        status=OdooWebhookStatus.PENDING.value,
    )

    db.add(event)
    await db.commit()
    await db.refresh(event)

    return event.id


# =============================================================================
# Webhook Endpoints
# =============================================================================


@router.post(
    "/{connection_id}/customer",
    response_model=OdooWebhookResponse,
    summary="Kunden-Webhook empfangen",
    description="Empfaengt Kunden-Events von Odoo (create/update/delete).",
)
async def receive_customer_webhook(
    connection_id: UUID,
    request: Request,
    x_odoo_webhook_signature: str = Header(..., alias=SIGNATURE_HEADER),
    x_odoo_webhook_timestamp: str = Header(..., alias=TIMESTAMP_HEADER),
    x_odoo_webhook_id: str = Header(None, alias=WEBHOOK_ID_HEADER),
    db: AsyncSession = Depends(get_db),
) -> OdooWebhookResponse:
    """Verarbeitet Kunden-Webhook von Odoo."""
    return await _process_webhook(
        connection_id=connection_id,
        event_type=OdooWebhookEventType.CUSTOMER,
        request=request,
        signature=x_odoo_webhook_signature,
        timestamp=x_odoo_webhook_timestamp,
        webhook_id=x_odoo_webhook_id,
        db=db,
    )


@router.post(
    "/{connection_id}/supplier",
    response_model=OdooWebhookResponse,
    summary="Lieferanten-Webhook empfangen",
)
async def receive_supplier_webhook(
    connection_id: UUID,
    request: Request,
    x_odoo_webhook_signature: str = Header(..., alias=SIGNATURE_HEADER),
    x_odoo_webhook_timestamp: str = Header(..., alias=TIMESTAMP_HEADER),
    x_odoo_webhook_id: str = Header(None, alias=WEBHOOK_ID_HEADER),
    db: AsyncSession = Depends(get_db),
) -> OdooWebhookResponse:
    """Verarbeitet Lieferanten-Webhook von Odoo."""
    return await _process_webhook(
        connection_id=connection_id,
        event_type=OdooWebhookEventType.SUPPLIER,
        request=request,
        signature=x_odoo_webhook_signature,
        timestamp=x_odoo_webhook_timestamp,
        webhook_id=x_odoo_webhook_id,
        db=db,
    )


@router.post(
    "/{connection_id}/invoice",
    response_model=OdooWebhookResponse,
    summary="Rechnungs-Webhook empfangen",
)
async def receive_invoice_webhook(
    connection_id: UUID,
    request: Request,
    x_odoo_webhook_signature: str = Header(..., alias=SIGNATURE_HEADER),
    x_odoo_webhook_timestamp: str = Header(..., alias=TIMESTAMP_HEADER),
    x_odoo_webhook_id: str = Header(None, alias=WEBHOOK_ID_HEADER),
    db: AsyncSession = Depends(get_db),
) -> OdooWebhookResponse:
    """Verarbeitet Rechnungs-Webhook von Odoo."""
    return await _process_webhook(
        connection_id=connection_id,
        event_type=OdooWebhookEventType.INVOICE,
        request=request,
        signature=x_odoo_webhook_signature,
        timestamp=x_odoo_webhook_timestamp,
        webhook_id=x_odoo_webhook_id,
        db=db,
    )


@router.post(
    "/{connection_id}/payment",
    response_model=OdooWebhookResponse,
    summary="Zahlungs-Webhook empfangen",
)
async def receive_payment_webhook(
    connection_id: UUID,
    request: Request,
    x_odoo_webhook_signature: str = Header(..., alias=SIGNATURE_HEADER),
    x_odoo_webhook_timestamp: str = Header(..., alias=TIMESTAMP_HEADER),
    x_odoo_webhook_id: str = Header(None, alias=WEBHOOK_ID_HEADER),
    db: AsyncSession = Depends(get_db),
) -> OdooWebhookResponse:
    """Verarbeitet Zahlungs-Webhook von Odoo."""
    return await _process_webhook(
        connection_id=connection_id,
        event_type=OdooWebhookEventType.PAYMENT,
        request=request,
        signature=x_odoo_webhook_signature,
        timestamp=x_odoo_webhook_timestamp,
        webhook_id=x_odoo_webhook_id,
        db=db,
    )


@router.post(
    "/{connection_id}/product",
    response_model=OdooWebhookResponse,
    summary="Produkt-Webhook empfangen",
)
async def receive_product_webhook(
    connection_id: UUID,
    request: Request,
    x_odoo_webhook_signature: str = Header(..., alias=SIGNATURE_HEADER),
    x_odoo_webhook_timestamp: str = Header(..., alias=TIMESTAMP_HEADER),
    x_odoo_webhook_id: str = Header(None, alias=WEBHOOK_ID_HEADER),
    db: AsyncSession = Depends(get_db),
) -> OdooWebhookResponse:
    """Verarbeitet Produkt-Webhook von Odoo."""
    return await _process_webhook(
        connection_id=connection_id,
        event_type=OdooWebhookEventType.PRODUCT,
        request=request,
        signature=x_odoo_webhook_signature,
        timestamp=x_odoo_webhook_timestamp,
        webhook_id=x_odoo_webhook_id,
        db=db,
    )


# =============================================================================
# Core Webhook Processing
# =============================================================================


async def _process_webhook(
    connection_id: UUID,
    event_type: OdooWebhookEventType,
    request: Request,
    signature: str,
    timestamp: str,
    webhook_id: Optional[str],
    db: AsyncSession,
) -> OdooWebhookResponse:
    """
    Kern-Logik fuer Webhook-Verarbeitung.

    1. Validiert Payload-Groesse
    2. Verifiziert Signatur (HMAC-SHA256)
    3. Prueft Timestamp (Replay-Schutz)
    4. Prueft Idempotenz (bereits verarbeitet?)
    5. Speichert Event
    6. Queued Celery Task zur Verarbeitung

    Returns:
        OdooWebhookResponse mit Status
    """
    # 1. Read and validate payload size
    try:
        body = await request.body()
        if len(body) > MAX_PAYLOAD_SIZE:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail="Payload zu gross",
            )
    except Exception as e:
        logger.error("webhook_payload_read_error", **safe_error_log(e))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Fehler beim Lesen des Payloads",
        )

    # 2. Get webhook secret
    webhook_secret = await get_webhook_secret(db, connection_id)
    if not webhook_secret:
        logger.warning(
            "webhook_connection_not_found",
            connection_id=str(connection_id),
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="ERP-Verbindung nicht gefunden oder inaktiv",
        )

    # 3. Verify signature
    if not verify_webhook_signature(body, signature, timestamp, webhook_secret):
        logger.warning(
            "webhook_signature_invalid",
            connection_id=str(connection_id),
            event_type=event_type.value,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Ungueltige Webhook-Signatur",
        )

    # 4. Validate timestamp (replay protection)
    if not validate_timestamp(timestamp):
        logger.warning(
            "webhook_timestamp_invalid",
            connection_id=str(connection_id),
            timestamp=timestamp,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Webhook-Timestamp abgelaufen oder ungueltig",
        )

    # 5. Parse payload
    try:
        import json
        payload_data = json.loads(body)
        webhook_payload = OdooWebhookPayload(**payload_data)
    except Exception as e:
        logger.error(
            "webhook_payload_parse_error",
            connection_id=str(connection_id),
            **safe_error_log(e),
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ungueltiges Payload-Format",
        )

    # 6. Check idempotency
    if await check_event_processed(db, connection_id, webhook_payload.event_id):
        logger.info(
            "webhook_event_already_processed",
            connection_id=str(connection_id),
            event_id=webhook_payload.event_id,
        )
        return OdooWebhookResponse(
            success=True,
            event_id=webhook_payload.event_id,
            message="Event bereits verarbeitet (idempotent)",
        )

    # 7. Compute payload hash and sanitize for storage
    payload_hash = compute_payload_hash(body)
    sanitized_preview = sanitize_payload_for_preview(webhook_payload.data)

    # 8. Store event
    try:
        event_db_id = await store_webhook_event(
            db=db,
            connection_id=connection_id,
            event_id=webhook_payload.event_id,
            event_type=event_type.value,
            action=webhook_payload.action.value,
            payload_hash=payload_hash,
            payload_preview=sanitized_preview,
            odoo_record_id=str(webhook_payload.record_id),
        )
    except Exception as e:
        logger.error(
            "webhook_event_store_error",
            connection_id=str(connection_id),
            **safe_error_log(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Fehler beim Speichern des Events",
        )

    # 9. Queue processing task
    try:
        from app.workers.tasks.odoo_tasks import process_odoo_webhook

        task = process_odoo_webhook.delay(
            event_db_id=str(event_db_id),
            connection_id=str(connection_id),
            event_type=event_type.value,
            action=webhook_payload.action.value,
            record_id=webhook_payload.record_id,
            data=webhook_payload.data,
        )

        logger.info(
            "webhook_event_queued",
            connection_id=str(connection_id),
            event_id=webhook_payload.event_id,
            event_type=event_type.value,
            task_id=task.id,
        )

        return OdooWebhookResponse(
            success=True,
            event_id=webhook_payload.event_id,
            message="Webhook empfangen und zur Verarbeitung eingereiht",
            task_id=task.id,
        )

    except Exception as e:
        logger.error(
            "webhook_task_queue_error",
            connection_id=str(connection_id),
            **safe_error_log(e),
        )
        # Event is stored, can be retried later
        return OdooWebhookResponse(
            success=True,
            event_id=webhook_payload.event_id,
            message="Webhook empfangen, wird spaeter verarbeitet",
        )


# =============================================================================
# Status Endpoints
# =============================================================================


@router.get(
    "/{connection_id}/events",
    summary="Webhook-Events auflisten",
    description="Listet die letzten Webhook-Events fuer eine Verbindung auf.",
)
async def list_webhook_events(
    connection_id: UUID,
    limit: int = 50,
    status_filter: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Listet Webhook-Events auf."""
    from app.db.models import OdooWebhookEvent, ERPConnection

    # Verify connection exists
    conn_result = await db.execute(
        select(ERPConnection.id).where(ERPConnection.id == connection_id)
    )
    if not conn_result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="ERP-Verbindung nicht gefunden",
        )

    query = select(OdooWebhookEvent).where(
        OdooWebhookEvent.connection_id == connection_id
    )

    if status_filter:
        query = query.where(OdooWebhookEvent.status == status_filter)

    query = query.order_by(OdooWebhookEvent.received_at.desc()).limit(limit)

    result = await db.execute(query)
    events = result.scalars().all()

    return {
        "events": [
            {
                "id": str(e.id),
                "event_id": e.event_id,
                "event_type": e.event_type,
                "action": e.action,
                "status": e.status,
                "received_at": e.received_at.isoformat() if e.received_at else None,
                "processed_at": e.processed_at.isoformat() if e.processed_at else None,
                "processing_attempts": e.processing_attempts,
                "error_message": e.error_message,
            }
            for e in events
        ],
        "total": len(events),
    }


@router.post(
    "/{connection_id}/events/{event_id}/retry",
    summary="Webhook-Event erneut verarbeiten",
)
async def retry_webhook_event(
    connection_id: UUID,
    event_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Verarbeitet ein fehlgeschlagenes Event erneut."""
    from app.db.models import OdooWebhookEvent

    result = await db.execute(
        select(OdooWebhookEvent).where(
            and_(
                OdooWebhookEvent.id == event_id,
                OdooWebhookEvent.connection_id == connection_id,
            )
        )
    )
    event = result.scalar_one_or_none()

    if not event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Event nicht gefunden",
        )

    if event.status == OdooWebhookStatus.SUCCESS.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Event wurde bereits erfolgreich verarbeitet",
        )

    # Queue retry
    from app.workers.tasks.odoo_tasks import retry_failed_odoo_webhook

    task = retry_failed_odoo_webhook.delay(str(event_id))

    return {
        "message": "Retry eingereiht",
        "event_id": str(event_id),
        "task_id": task.id,
    }
