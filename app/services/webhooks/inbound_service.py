# -*- coding: utf-8 -*-
"""
Inbound Webhook Service.

Generischer Service für den Empfang und die Verarbeitung
eingehender Webhooks von externen Providern (DATEV, DHL, DPD, UPS, GLS).

Implementiert den 9-Schritt-Flow (analog zu Odoo-Webhooks):
1. Payload-Größe validieren
2. Webhook-Secret holen
3. Signatur verifizieren (HMAC-SHA256)
4. Timestamp validieren (Replay-Schutz)
5. Payload parsen
6. Idempotenz prüfen
7. Payload hashen + PII sanitisieren
8. Event speichern
9. Celery-Task einreihen

Feinpoliert und durchdacht - Enterprise-grade Webhook Processing.
"""

import hashlib
import hmac
import json
import uuid
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

import structlog
from fastapi import HTTPException, Request, status
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.safe_errors import safe_error_detail, safe_error_log
from app.db.models_webhook_inbound import InboundWebhookEvent
from app.schemas.webhook_inbound import (
    InboundWebhookPayload,
    InboundWebhookResponse,
    InboundWebhookStatus,
)
from app.services.webhooks.providers import BaseWebhookProvider

logger = structlog.get_logger(__name__)

# Maximum payload size (1MB)
MAX_PAYLOAD_SIZE = 1024 * 1024

# Signature timestamp tolerance (5 Minuten)
SIGNATURE_TIMESTAMP_TOLERANCE_SECONDS = 300


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

    Format: HMAC-SHA256(webhook_secret, timestamp + "." + payload)

    Args:
        payload: Roher Request Body
        signature: Signatur aus Header
        timestamp: Timestamp aus Header
        webhook_secret: Webhook Secret

    Returns:
        True wenn Signatur gültig
    """
    try:
        message = f"{timestamp}.".encode() + payload
        expected_signature = hmac.new(
            webhook_secret.encode(),
            message,
            hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(signature, expected_signature)
    except Exception as e:
        logger.warning("inbound_webhook_signature_verification_failed", error=str(e))
        return False


def validate_timestamp(timestamp_str: str) -> bool:
    """Validiert dass der Timestamp nicht zu alt ist (Replay-Schutz)."""
    try:
        timestamp = int(timestamp_str)
        now = int(datetime.now(timezone.utc).timestamp())
        return abs(now - timestamp) <= SIGNATURE_TIMESTAMP_TOLERANCE_SECONDS
    except (ValueError, TypeError):
        return False


def sanitize_payload_for_preview(data: dict, pii_fields: set) -> dict:
    """
    Entfernt PII aus Payload für sichere Speicherung.

    SECURITY: Entfernt Namen, Adressen, IBANs, etc.

    Args:
        data: Original-Daten
        pii_fields: Set von PII-Feldnamen

    Returns:
        Sanitisiertes Dictionary
    """
    sanitized = {}
    for key, value in data.items():
        if key.lower() in pii_fields:
            sanitized[key] = "[REDACTED]"
        elif isinstance(value, dict):
            sanitized[key] = sanitize_payload_for_preview(value, pii_fields)
        elif isinstance(value, list) and len(value) > 0 and isinstance(value[0], dict):
            sanitized[key] = [
                sanitize_payload_for_preview(v, pii_fields) if isinstance(v, dict) else v
                for v in value
            ]
        else:
            sanitized[key] = value
    return sanitized


class InboundWebhookService:
    """Service für die Verarbeitung eingehender Webhooks."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def process_webhook(
        self,
        provider: str,
        config_id: UUID,
        request: Request,
        signature: Optional[str],
        timestamp: Optional[str],
        webhook_id: Optional[str],
        adapter: BaseWebhookProvider,
    ) -> InboundWebhookResponse:
        """
        Verarbeitet einen eingehenden Webhook (9-Schritt-Flow).

        Args:
            provider: Provider-Name (datev, dhl, etc.)
            config_id: ERP-Verbindungs-ID (für DATEV) oder Platzhalter
            request: FastAPI Request
            signature: Signatur aus Header
            timestamp: Timestamp aus Header
            webhook_id: Webhook-ID aus Header
            adapter: Provider-Adapter

        Returns:
            InboundWebhookResponse
        """
        # 1. Read and validate payload size
        try:
            body = await request.body()
            if len(body) > MAX_PAYLOAD_SIZE:
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail="Payload zu gross (max 1MB)",
                )
        except HTTPException:
            raise
        except Exception as e:
            logger.error("inbound_webhook_payload_read_error", **safe_error_log(e))
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Fehler beim Lesen des Payloads",
            )

        # 2. Get webhook secret
        webhook_secret = await self._get_webhook_secret(provider, config_id)
        if not webhook_secret:
            logger.warning(
                "inbound_webhook_secret_not_found",
                provider=provider,
                config_id=str(config_id),
            )
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Webhook-Konfiguration nicht gefunden oder inaktiv",
            )

        # 3. Verify signature
        if not signature:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Signatur-Header fehlt",
            )

        if not verify_webhook_signature(body, signature, timestamp or "", webhook_secret):
            logger.warning(
                "inbound_webhook_signature_invalid",
                provider=provider,
                config_id=str(config_id),
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Ungültige Webhook-Signatur",
            )

        # 4. Validate timestamp (replay protection)
        if timestamp and not validate_timestamp(timestamp):
            logger.warning(
                "inbound_webhook_timestamp_invalid",
                provider=provider,
                timestamp=timestamp,
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Webhook-Timestamp abgelaufen oder ungültig",
            )

        # 5. Parse payload
        try:
            payload_data = json.loads(body)
            webhook_payload = InboundWebhookPayload(**payload_data)
        except json.JSONDecodeError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Ungültiges JSON-Format",
            )
        except Exception as e:
            logger.error(
                "inbound_webhook_payload_parse_error",
                provider=provider,
                **safe_error_log(e),
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Ungültiges Payload-Format",
            )

        # 6. Check idempotency
        if await self._check_idempotency(provider, webhook_payload.event_id):
            logger.info(
                "inbound_webhook_already_processed",
                provider=provider,
                event_id=webhook_payload.event_id,
            )
            return InboundWebhookResponse(
                success=True,
                event_id=webhook_payload.event_id,
                message="Event bereits verarbeitet (idempotent)",
            )

        # 7. Compute hash + sanitize PII
        payload_hash = compute_payload_hash(body)
        pii_fields = adapter.get_pii_fields()
        sanitized_preview = sanitize_payload_for_preview(webhook_payload.data, pii_fields)

        # 8. Map to internal event + extract external ref
        internal_event = adapter.map_event(webhook_payload.event_type, webhook_payload.action)
        external_ref = adapter.extract_external_ref(webhook_payload.data)
        if webhook_payload.external_ref:
            external_ref = webhook_payload.external_ref

        # 9. Store event
        try:
            event_db_id = await self._store_event(
                provider=provider,
                config_id=config_id,
                event_id=webhook_payload.event_id,
                event_type=webhook_payload.event_type,
                action=webhook_payload.action,
                payload_hash=payload_hash,
                payload_preview=sanitized_preview,
                external_ref=external_ref,
                internal_event_type=internal_event.value if internal_event else None,
            )
        except Exception as e:
            logger.error(
                "inbound_webhook_store_error",
                provider=provider,
                **safe_error_log(e),
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Fehler beim Speichern des Events",
            )

        # 10. Queue Celery task
        try:
            from app.workers.tasks.webhook_inbound_tasks import process_inbound_webhook

            task = process_inbound_webhook.delay(
                event_db_id=str(event_db_id),
                provider=provider,
                event_type=webhook_payload.event_type,
                action=webhook_payload.action,
                data=webhook_payload.data,
                internal_event_type=internal_event.value if internal_event else None,
                external_ref=external_ref,
            )

            logger.info(
                "inbound_webhook_queued",
                provider=provider,
                event_id=webhook_payload.event_id,
                event_type=webhook_payload.event_type,
                task_id=task.id,
            )

            return InboundWebhookResponse(
                success=True,
                event_id=webhook_payload.event_id,
                message="Webhook empfangen und zur Verarbeitung eingereiht",
                task_id=task.id,
            )

        except Exception as e:
            logger.error(
                "inbound_webhook_task_queue_error",
                provider=provider,
                **safe_error_log(e),
            )
            # Event ist gespeichert, kann später retried werden
            return InboundWebhookResponse(
                success=True,
                event_id=webhook_payload.event_id,
                message="Webhook empfangen, wird später verarbeitet",
            )

    async def _get_webhook_secret(self, provider: str, config_id: UUID) -> Optional[str]:
        """Holt das Webhook-Secret für einen Provider.

        DATEV: Secret aus ERPConnection (wie Odoo)
        Carrier: Secret aus Settings
        """
        if provider == "datev":
            return await self._get_erp_connection_secret(config_id)

        # Carrier-Provider: Secret aus Settings
        from app.core.config import settings
        secret_attr = f"WEBHOOK_SECRET_{provider.upper()}"
        secret = getattr(settings, secret_attr, None)

        if not secret:
            # Fallback: Generisches Carrier-Webhook-Secret
            secret = getattr(settings, "WEBHOOK_SECRET_CARRIER", None)

        return secret

    async def _get_erp_connection_secret(self, config_id: UUID) -> Optional[str]:
        """Holt Webhook-Secret aus ERPConnection (für DATEV/Odoo)."""
        from app.db.models import ERPConnection
        from app.core.encryption import decrypt_data, DecryptionError

        result = await self.db.execute(
            select(ERPConnection).where(
                and_(
                    ERPConnection.id == config_id,
                    ERPConnection.is_active == True,
                )
            )
        )
        connection = result.scalar_one_or_none()

        if not connection:
            return None

        try:
            api_key = decrypt_data(
                connection.encrypted_api_key,
                associated_data=f"erp:{connection.company_id}"
            )
            webhook_secret = hashlib.sha256(
                f"webhook:{api_key}".encode()
            ).hexdigest()[:32]
            return webhook_secret
        except DecryptionError:
            logger.error(
                "inbound_webhook_secret_decryption_failed",
                config_id=str(config_id),
            )
            return None

    async def _check_idempotency(self, provider: str, event_id: str) -> bool:
        """Prüft ob ein Event bereits verarbeitet wurde."""
        result = await self.db.execute(
            select(InboundWebhookEvent).where(
                and_(
                    InboundWebhookEvent.provider == provider,
                    InboundWebhookEvent.event_id == event_id,
                )
            )
        )
        event = result.scalar_one_or_none()

        if event and event.status in (
            InboundWebhookStatus.SUCCESS.value,
            InboundWebhookStatus.PROCESSING.value,
        ):
            return True
        return False

    async def _store_event(
        self,
        provider: str,
        config_id: UUID,
        event_id: str,
        event_type: str,
        action: str,
        payload_hash: str,
        payload_preview: dict,
        external_ref: Optional[str],
        internal_event_type: Optional[str],
    ) -> UUID:
        """Speichert Webhook-Event für Tracking und Idempotenz."""
        event = InboundWebhookEvent(
            id=uuid.uuid4(),
            provider=provider,
            config_id=config_id,
            event_id=event_id,
            event_type=event_type,
            action=action,
            payload_hash=payload_hash,
            payload_preview=payload_preview,
            external_ref=external_ref,
            internal_event_type=internal_event_type,
            status=InboundWebhookStatus.PENDING.value,
        )

        self.db.add(event)
        await self.db.commit()
        await self.db.refresh(event)

        return event.id
