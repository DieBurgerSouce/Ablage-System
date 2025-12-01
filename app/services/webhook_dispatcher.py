# -*- coding: utf-8 -*-
"""
Webhook Event Dispatcher für Ablage-System OCR.

Verknüpft System-Events mit Webhook-Abonnements und führt
die Zustellung mit Retry-Logik durch.

Feinpoliert und durchdacht - Enterprise-grade Event Delivery.
"""

import asyncio
import json
import secrets
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID
from enum import Enum

import httpx
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.db.models import WebhookSubscription, WebhookDelivery, User
from app.core.webhook_signature import (
    generate_signature,
    SIGNATURE_HEADER_NAME,
)

logger = structlog.get_logger(__name__)


class WebhookEventType(str, Enum):
    """Verfügbare Webhook-Event-Typen."""
    # Dokument-Events
    DOCUMENT_CREATED = "document.created"
    DOCUMENT_PROCESSED = "document.processed"
    DOCUMENT_FAILED = "document.failed"
    DOCUMENT_DELETED = "document.deleted"
    DOCUMENT_UPDATED = "document.updated"

    # OCR-Events
    OCR_STARTED = "ocr.started"
    OCR_COMPLETED = "ocr.completed"
    OCR_FAILED = "ocr.failed"
    OCR_QUALITY_WARNING = "ocr.quality_warning"

    # Batch-Events
    BATCH_STARTED = "batch.started"
    BATCH_COMPLETED = "batch.completed"
    BATCH_FAILED = "batch.failed"

    # System-Events
    SYSTEM_ALERT = "system.alert"
    BACKUP_COMPLETED = "backup.completed"
    SECURITY_INCIDENT = "security.incident"


class DeliveryStatus(str, Enum):
    """Webhook-Zustellungsstatus."""
    PENDING = "pending"
    SUCCESS = "success"
    FAILED = "failed"
    RETRYING = "retrying"


class WebhookDispatcher:
    """
    Event Dispatcher für Webhook-Zustellungen.

    Verarbeitet System-Events und stellt Webhooks zu:
    - Findet passende Abonnements für Events
    - Sendet Webhooks mit HMAC-Signatur
    - Implementiert Retry-Logik mit exponential backoff
    - Protokolliert Zustellungen
    """

    DEFAULT_TIMEOUT = 30
    DISPATCH_TIMEOUT = 120  # Max time for all webhooks in a dispatch batch
    MAX_PAYLOAD_SIZE = 1024 * 1024  # 1MB

    def __init__(self):
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Lazy initialization des HTTP-Clients."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.DEFAULT_TIMEOUT),
                limits=httpx.Limits(max_connections=100)
            )
        return self._client

    async def close(self):
        """Schließt den HTTP-Client."""
        if self._client:
            await self._client.aclose()
            self._client = None

    async def dispatch_event(
        self,
        db: AsyncSession,
        user_id: UUID,
        event_type: str,
        payload: Dict[str, Any],
        metadata: Optional[Dict[str, Any]] = None
    ) -> int:
        """
        Dispatcht ein Event an alle passenden Webhook-Abonnements.

        Args:
            db: Datenbank-Session
            user_id: Benutzer-ID dessen Webhooks getriggert werden
            event_type: Event-Typ (z.B. "document.processed")
            payload: Event-Daten
            metadata: Zusätzliche Metadaten

        Returns:
            Anzahl der ausgelösten Webhooks
        """
        # Finde aktive Abonnements für diesen Event-Typ
        subscriptions = await self._get_matching_subscriptions(
            db, user_id, event_type
        )

        if not subscriptions:
            logger.debug(
                "webhook_no_subscriptions",
                user_id=str(user_id)[:8],
                event_type=event_type
            )
            return 0

        # Erstelle vollständiges Event-Payload
        event_payload = self._create_event_payload(event_type, payload, metadata)

        # Dispatche an alle Abonnements parallel
        tasks = [
            self._deliver_webhook(db, subscription, event_payload)
            for subscription in subscriptions
        ]

        try:
            results = await asyncio.wait_for(
                asyncio.gather(*tasks, return_exceptions=True),
                timeout=self.DISPATCH_TIMEOUT
            )
        except asyncio.TimeoutError:
            logger.error(
                "webhook_dispatch_timeout",
                user_id=str(user_id)[:8],
                event_type=event_type,
                subscriptions=len(subscriptions),
                timeout_seconds=self.DISPATCH_TIMEOUT
            )
            # Return 0 successful deliveries on timeout
            return 0

        # Zähle erfolgreiche Zustellungen
        success_count = sum(1 for r in results if r is True)

        logger.info(
            "webhook_event_dispatched",
            user_id=str(user_id)[:8],
            event_type=event_type,
            subscriptions=len(subscriptions),
            successful=success_count
        )

        return len(subscriptions)

    async def _get_matching_subscriptions(
        self,
        db: AsyncSession,
        user_id: UUID,
        event_type: str
    ) -> List[WebhookSubscription]:
        """Findet alle aktiven Abonnements für einen Event-Typ."""
        result = await db.execute(
            select(WebhookSubscription).where(
                and_(
                    WebhookSubscription.user_id == user_id,
                    WebhookSubscription.is_active == True
                )
            )
        )
        subscriptions = list(result.scalars().all())

        # Filtere nach Event-Typ (event_types ist eine Liste)
        matching = []
        for sub in subscriptions:
            # Leere Liste = alle Events
            if not sub.event_types or event_type in sub.event_types:
                matching.append(sub)
            # Wildcard-Unterstützung (z.B. "document.*")
            elif any(
                event_type.startswith(et.replace("*", ""))
                for et in sub.event_types
                if "*" in et
            ):
                matching.append(sub)

        return matching

    def _create_event_payload(
        self,
        event_type: str,
        data: Dict[str, Any],
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Erstellt das vollständige Event-Payload."""
        return {
            "event_id": f"evt_{secrets.token_hex(12)}",
            "event_type": event_type,
            "api_version": "v1",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "data": data,
            "metadata": metadata or {}
        }

    def _sign_payload(self, payload: bytes, secret: str, timestamp: int) -> str:
        """
        Erstellt HMAC-SHA256 Signatur für Payload.

        Verwendet das neue Signaturformat mit Timestamp-Schutz:
        Format: t=<timestamp>,v1=<signature>
        """
        signature_header, _ = generate_signature(payload, secret, timestamp)
        return signature_header

    async def _deliver_webhook(
        self,
        db: AsyncSession,
        subscription: WebhookSubscription,
        payload: Dict[str, Any]
    ) -> bool:
        """
        Liefert Webhook an Subscription mit Retry-Logik.

        Args:
            db: Datenbank-Session
            subscription: Webhook-Abonnement
            payload: Event-Payload

        Returns:
            True wenn erfolgreich zugestellt
        """
        # Erstelle Delivery-Record
        delivery = WebhookDelivery(
            subscription_id=subscription.id,
            event_id=payload["event_id"],
            event_type=payload["event_type"],
            payload=payload,
            status=DeliveryStatus.PENDING.value
        )
        db.add(delivery)
        await db.commit()
        await db.refresh(delivery)

        # Serialisiere Payload
        payload_bytes = json.dumps(payload, separators=(",", ":")).encode("utf-8")

        # Prüfe Payload-Größe
        if len(payload_bytes) > self.MAX_PAYLOAD_SIZE:
            logger.warning(
                "webhook_payload_too_large",
                subscription_id=str(subscription.id)[:8],
                size=len(payload_bytes)
            )
            delivery.status = DeliveryStatus.FAILED.value
            delivery.error_message = "Payload zu groß"
            await db.commit()
            return False

        # Timestamp für Signatur (Unix-Timestamp)
        import time
        signature_timestamp = int(time.time())

        # Signatur erstellen (neues Format mit Timestamp-Schutz)
        signature = self._sign_payload(
            payload_bytes, subscription.secret, signature_timestamp
        )

        # Headers vorbereiten (mit standardisiertem Signatur-Header)
        headers = {
            "Content-Type": "application/json",
            SIGNATURE_HEADER_NAME: signature,
            "X-Webhook-Delivery-ID": payload["event_id"],
            "X-Webhook-Event": payload["event_type"],
            "X-Webhook-Timestamp": str(signature_timestamp),
            "User-Agent": "Ablage-Webhook/1.0"
        }

        # Custom Headers hinzufügen
        if subscription.headers:
            headers.update(subscription.headers)

        # Sende mit Retry-Logik
        max_retries = subscription.max_retries or 3
        retry_delay = subscription.retry_delay_seconds or 60

        for attempt in range(max_retries + 1):
            try:
                client = await self._get_client()

                start_time = datetime.now(timezone.utc)
                response = await client.post(
                    subscription.url,
                    content=payload_bytes,
                    headers=headers
                )
                response_time_ms = int(
                    (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
                )

                # Erfolg (2xx Status)
                if 200 <= response.status_code < 300:
                    delivery.status = DeliveryStatus.SUCCESS.value
                    delivery.status_code = response.status_code
                    delivery.response_time_ms = response_time_ms
                    delivery.delivered_at = datetime.now(timezone.utc)
                    delivery.attempts = attempt + 1
                    await db.commit()

                    logger.info(
                        "webhook_delivered",
                        subscription_id=str(subscription.id)[:8],
                        event_type=payload["event_type"],
                        status_code=response.status_code,
                        response_time_ms=response_time_ms
                    )
                    return True

                # Client-Fehler (4xx) - nicht retryable
                if 400 <= response.status_code < 500:
                    delivery.status = DeliveryStatus.FAILED.value
                    delivery.status_code = response.status_code
                    delivery.response_time_ms = response_time_ms
                    delivery.error_message = f"HTTP {response.status_code}: {response.text[:500]}"
                    delivery.attempts = attempt + 1
                    await db.commit()

                    logger.warning(
                        "webhook_client_error",
                        subscription_id=str(subscription.id)[:8],
                        status_code=response.status_code
                    )
                    return False

                # Server-Fehler (5xx) - retry
                delivery.status = DeliveryStatus.RETRYING.value
                delivery.status_code = response.status_code
                delivery.attempts = attempt + 1
                await db.commit()

                if attempt < max_retries:
                    # Exponential backoff
                    wait_time = retry_delay * (2 ** attempt)
                    logger.info(
                        "webhook_retry_scheduled",
                        subscription_id=str(subscription.id)[:8],
                        attempt=attempt + 1,
                        wait_seconds=wait_time
                    )
                    await asyncio.sleep(wait_time)

            except httpx.TimeoutException:
                delivery.status = DeliveryStatus.RETRYING.value
                delivery.error_message = "Timeout"
                delivery.attempts = attempt + 1
                await db.commit()

                if attempt < max_retries:
                    await asyncio.sleep(retry_delay * (2 ** attempt))
                continue

            except httpx.ConnectError as e:
                delivery.status = DeliveryStatus.RETRYING.value
                delivery.error_message = f"Verbindungsfehler: {str(e)[:200]}"
                delivery.attempts = attempt + 1
                await db.commit()

                if attempt < max_retries:
                    await asyncio.sleep(retry_delay * (2 ** attempt))
                continue

            except Exception as e:
                logger.error(
                    "webhook_delivery_error",
                    subscription_id=str(subscription.id)[:8],
                    error=str(e)
                )
                delivery.status = DeliveryStatus.FAILED.value
                delivery.error_message = str(e)[:500]
                delivery.attempts = attempt + 1
                await db.commit()
                return False

        # Alle Retries fehlgeschlagen
        delivery.status = DeliveryStatus.FAILED.value
        delivery.error_message = f"Alle {max_retries + 1} Versuche fehlgeschlagen"
        await db.commit()

        logger.warning(
            "webhook_delivery_failed_all_retries",
            subscription_id=str(subscription.id)[:8],
            event_type=payload["event_type"],
            attempts=max_retries + 1
        )

        return False


# ==================== Convenience Functions ====================

async def dispatch_document_event(
    db: AsyncSession,
    user_id: UUID,
    event_type: str,
    document_id: str,
    filename: str,
    **extra_data
) -> int:
    """
    Dispatcht ein Dokument-Event.

    Convenience-Funktion für häufige Dokument-Events.
    """
    dispatcher = get_webhook_dispatcher()
    return await dispatcher.dispatch_event(
        db=db,
        user_id=user_id,
        event_type=event_type,
        payload={
            "document_id": document_id,
            "filename": filename,
            **extra_data
        }
    )


async def dispatch_ocr_completed(
    db: AsyncSession,
    user_id: UUID,
    document_id: str,
    filename: str,
    backend: str,
    confidence: float,
    word_count: int,
    processing_time_ms: int
) -> int:
    """Dispatcht OCR-Completed Event."""
    return await dispatch_document_event(
        db=db,
        user_id=user_id,
        event_type=WebhookEventType.OCR_COMPLETED.value,
        document_id=document_id,
        filename=filename,
        backend=backend,
        confidence=confidence,
        word_count=word_count,
        processing_time_ms=processing_time_ms
    )


async def dispatch_ocr_failed(
    db: AsyncSession,
    user_id: UUID,
    document_id: str,
    filename: str,
    error_message: str,
    backend: Optional[str] = None
) -> int:
    """Dispatcht OCR-Failed Event."""
    return await dispatch_document_event(
        db=db,
        user_id=user_id,
        event_type=WebhookEventType.OCR_FAILED.value,
        document_id=document_id,
        filename=filename,
        error_message=error_message,
        backend=backend
    )


async def dispatch_batch_completed(
    db: AsyncSession,
    user_id: UUID,
    batch_id: str,
    total_documents: int,
    successful: int,
    failed: int,
    total_time_ms: int
) -> int:
    """Dispatcht Batch-Completed Event."""
    dispatcher = get_webhook_dispatcher()
    return await dispatcher.dispatch_event(
        db=db,
        user_id=user_id,
        event_type=WebhookEventType.BATCH_COMPLETED.value,
        payload={
            "batch_id": batch_id,
            "total_documents": total_documents,
            "successful": successful,
            "failed": failed,
            "total_time_ms": total_time_ms,
            "success_rate": round(successful / total_documents * 100, 1) if total_documents > 0 else 0
        }
    )


# ==================== Singleton ====================

_webhook_dispatcher: Optional[WebhookDispatcher] = None


def get_webhook_dispatcher() -> WebhookDispatcher:
    """Gibt WebhookDispatcher-Singleton zurück."""
    global _webhook_dispatcher
    if _webhook_dispatcher is None:
        _webhook_dispatcher = WebhookDispatcher()
    return _webhook_dispatcher
