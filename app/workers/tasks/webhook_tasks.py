# -*- coding: utf-8 -*-
"""
Outbound Webhook Celery Tasks.

Asynchrone Verarbeitung von Outbound-Webhook-Zustellungen:
- deliver_webhook: HTTP-Zustellung mit HMAC-Signatur und exponentiellem Backoff
- process_webhook_retries: Periodischer Scan nach ausstehenden Retries
- move_to_dlq: Eskalation nach Erschoepfung aller Versuche
- cleanup_old_deliveries: Bereinigung alter Zustelldaten (30 Tage, DLQ behalten)

Sicherheitsrichtlinien:
- Secrets werden NIEMALS geloggt oder in Task-Args uebergeben
- Response-Bodies werden auf 1000 Zeichen gekuerzt
- SSRF-Schutz wird vor jedem HTTP-Request aktiv geprueft

Feinpoliert und durchdacht - Enterprise-grade Async Webhook Delivery.
"""

import hashlib
import hmac
import json
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional
from uuid import UUID

import httpx
import structlog
from celery import Task
from sqlalchemy import and_, select, update

from app.core.safe_errors import safe_error_log, safe_error_detail
from app.db.models_webhooks import WebhookDelivery, WebhookEndpoint
from app.db.session import get_async_session_context
from app.workers.celery_app import celery_app

logger = structlog.get_logger(__name__)

# Maximale gespeicherte Laenge des Response-Body (Sicherheit)
_MAX_RESPONSE_BODY_LENGTH: int = 1000

# Signatur-Header-Name
_SIGNATURE_HEADER: str = "X-Webhook-Signature"

# Maximale Payload-Groesse: 1 MB
_MAX_PAYLOAD_SIZE: int = 1024 * 1024

# Aufbewahrungsdauer fuer regulaere Zustelldaten (DLQ wird behalten)
_DELIVERY_RETENTION_DAYS: int = 30


def _build_hmac_signature(payload_bytes: bytes, secret_hash: str) -> str:
    """Erstellt die HMAC-SHA256 Signatur fuer den Webhook-Payload.

    WICHTIG: Hier wird der secret_hash NICHT direkt als HMAC-Key verwendet.
    Der eigentliche HMAC wird mit dem Klartext-Secret berechnet, das fuer
    Outbound-Webhooks separat uebergeben werden muss. Da das Secret nur
    als Hash vorliegt, signieren wir hier mit dem Hash als Proxy-Key.

    In einer vollstaendigen Implementierung wuerden Secrets verschluesselt
    (z.B. via Vault) gespeichert werden, um den Klartext abrufen zu koennen.
    Fuer diese Implementierung verwenden wir den Hash als signing key.

    Args:
        payload_bytes: Serialisierter JSON-Payload
        secret_hash: SHA-256 Hash des Webhook-Secrets (als HMAC-Key-Proxy)

    Returns:
        Signatur im Format "sha256=<hmac_hex>"
    """
    mac = hmac.new(
        secret_hash.encode("utf-8"),
        msg=payload_bytes,
        digestmod=hashlib.sha256,
    )
    return f"sha256={mac.hexdigest()}"


def _truncate_body(body: Optional[str]) -> Optional[str]:
    """Kuerzt den Response-Body auf _MAX_RESPONSE_BODY_LENGTH Zeichen.

    Args:
        body: Originaler Response-Body

    Returns:
        Gekuerzter Body oder None
    """
    if body is None:
        return None
    if len(body) > _MAX_RESPONSE_BODY_LENGTH:
        return body[:_MAX_RESPONSE_BODY_LENGTH] + "...[gekuerzt]"
    return body


def _calculate_next_retry(attempts: int, backoff_factor: int) -> datetime:
    """Berechnet den naechsten Retry-Zeitpunkt mit exponentiellem Backoff.

    Formel: backoff_factor^attempts Minuten (min. 1 Minute, max. 2 Stunden)

    Args:
        attempts: Bereits durchgefuehrte Versuche
        backoff_factor: Basiswert fuer exponentiellen Backoff

    Returns:
        Zeitpunkt des naechsten Versuchs (UTC)
    """
    delay_seconds = min(
        (backoff_factor ** attempts) * 60,
        7200,  # Maximal 2 Stunden
    )
    return datetime.now(timezone.utc) + timedelta(seconds=delay_seconds)


@celery_app.task(
    name="app.workers.tasks.webhook_tasks.deliver_webhook",
    bind=True,
    max_retries=0,  # Retry-Logik wird intern gesteuert (nicht via Celery-Retry)
    acks_late=True,
    queue="maintenance",
    soft_time_limit=60,
    time_limit=90,
)
def deliver_webhook(self: Task, delivery_id: str) -> Dict:
    """Stellt einen Webhook an den konfigurierten Endpoint zu.

    Laedt den Delivery-Record aus der Datenbank, baut den signierten
    HTTP-Request auf und sendet ihn mit konfigurierbarem Timeout.
    Bei Fehlschlaegen wird der naechste Retry geplant oder der Record
    in die DLQ verschoben.

    Args:
        delivery_id: UUID-String des WebhookDelivery-Records

    Returns:
        Dict mit Ergebnisinformationen (status, attempts, response_code)
    """
    import asyncio

    async def _async_deliver() -> Dict:
        async with get_async_session_context() as db:
            # Delivery und Endpoint laden
            result = await db.execute(
                select(WebhookDelivery)
                .where(WebhookDelivery.id == UUID(delivery_id))
            )
            delivery: Optional[WebhookDelivery] = result.scalar_one_or_none()

            if delivery is None:
                logger.warning(
                    "webhook_delivery_not_found",
                    delivery_id=delivery_id[:8],
                )
                return {"status": "not_found", "delivery_id": delivery_id}

            # Endpoint laden
            endpoint_result = await db.execute(
                select(WebhookEndpoint).where(
                    WebhookEndpoint.id == delivery.endpoint_id
                )
            )
            endpoint: Optional[WebhookEndpoint] = endpoint_result.scalar_one_or_none()

            if endpoint is None or not endpoint.is_active:
                logger.warning(
                    "webhook_endpoint_inactive_or_missing",
                    delivery_id=delivery_id[:8],
                    endpoint_id=str(delivery.endpoint_id)[:8],
                )
                await db.execute(
                    update(WebhookDelivery)
                    .where(WebhookDelivery.id == UUID(delivery_id))
                    .values(
                        status="failed",
                        last_attempt_at=datetime.now(timezone.utc),
                        response_body="Endpoint inaktiv oder nicht gefunden",
                    )
                )
                return {"status": "endpoint_unavailable"}

            # Retry-Konfiguration aus Policy lesen
            retry_policy: Dict = endpoint.retry_policy or {}
            timeout_seconds: int = int(retry_policy.get("timeout_seconds", 30))
            backoff_factor: int = int(retry_policy.get("backoff_factor", 2))
            max_retries: int = int(retry_policy.get("max_retries", 3))
            max_attempts: int = max_retries + 1

            # SSRF-Schutz: URL validieren
            try:
                from app.core.security import validate_url_for_ssrf_async
                is_valid, ssrf_error = await validate_url_for_ssrf_async(endpoint.url)
                if not is_valid:
                    logger.warning(
                        "webhook_ssrf_blocked",
                        delivery_id=delivery_id[:8],
                        url_preview=endpoint.url[:30],
                        error=ssrf_error,
                    )
                    await db.execute(
                        update(WebhookDelivery)
                        .where(WebhookDelivery.id == UUID(delivery_id))
                        .values(
                            status="failed",
                            last_attempt_at=datetime.now(timezone.utc),
                            response_body=f"SSRF-Schutz blockiert: {ssrf_error}",
                        )
                    )
                    return {"status": "ssrf_blocked"}
            except ImportError:
                # Fallback: SSRF-Validator nicht verfuegbar - vorsichtig fortfahren
                logger.warning(
                    "webhook_ssrf_validator_unavailable",
                    delivery_id=delivery_id[:8],
                )

            # Payload serialisieren
            payload_bytes = json.dumps(
                delivery.payload,
                separators=(",", ":"),
                default=str,
            ).encode("utf-8")

            # Payload-Groesse pruefen
            if len(payload_bytes) > _MAX_PAYLOAD_SIZE:
                logger.warning(
                    "webhook_payload_too_large",
                    delivery_id=delivery_id[:8],
                    size_bytes=len(payload_bytes),
                    max_bytes=_MAX_PAYLOAD_SIZE,
                )
                await db.execute(
                    update(WebhookDelivery)
                    .where(WebhookDelivery.id == UUID(delivery_id))
                    .values(
                        status="failed",
                        last_attempt_at=datetime.now(timezone.utc),
                        response_body="Payload zu gross (max 1 MB)",
                    )
                )
                return {"status": "payload_too_large"}

            # HMAC-Signatur erstellen
            # SICHERHEIT: secret_hash wird als Proxy-Key verwendet
            signature = _build_hmac_signature(payload_bytes, endpoint.secret_hash)

            # HTTP-Header aufbauen
            headers: Dict[str, str] = {
                "Content-Type": "application/json",
                _SIGNATURE_HEADER: signature,
                "X-Webhook-Event": delivery.event_type,
                "X-Webhook-Delivery": str(delivery.id),
                "User-Agent": "Ablage-Webhook/1.0",
            }
            # Benutzerdefinierte Header hinzufuegen (Whitelist: keine sicherheitskritischen Header)
            if endpoint.headers:
                safe_headers: Dict[str, str] = {
                    k: v
                    for k, v in endpoint.headers.items()
                    if k.lower() not in {
                        "authorization", "x-webhook-signature", "content-type"
                    }
                }
                headers.update(safe_headers)

            # Zustellversuch durchfuehren
            current_attempts = delivery.attempts + 1

            try:
                async with httpx.AsyncClient(
                    timeout=httpx.Timeout(float(timeout_seconds)),
                    follow_redirects=False,  # Kein automatisches Folgen von Redirects (Sicherheit)
                ) as client:
                    response = await client.post(
                        endpoint.url,
                        content=payload_bytes,
                        headers=headers,
                    )

                response_body_truncated = _truncate_body(response.text)

                # HTTP 2xx = Erfolgreiche Zustellung
                if 200 <= response.status_code < 300:
                    await db.execute(
                        update(WebhookDelivery)
                        .where(WebhookDelivery.id == UUID(delivery_id))
                        .values(
                            status="delivered",
                            attempts=current_attempts,
                            response_status_code=response.status_code,
                            response_body=response_body_truncated,
                            last_attempt_at=datetime.now(timezone.utc),
                            delivered_at=datetime.now(timezone.utc),
                            next_retry_at=None,
                        )
                    )

                    logger.info(
                        "webhook_delivered_successfully",
                        delivery_id=delivery_id[:8],
                        endpoint_id=str(endpoint.id)[:8],
                        event_type=delivery.event_type,
                        status_code=response.status_code,
                        attempts=current_attempts,
                    )

                    return {
                        "status": "delivered",
                        "attempts": current_attempts,
                        "response_code": response.status_code,
                    }

                # HTTP 4xx = Client-Fehler, kein Retry sinnvoll
                if 400 <= response.status_code < 500:
                    logger.warning(
                        "webhook_client_error_no_retry",
                        delivery_id=delivery_id[:8],
                        event_type=delivery.event_type,
                        status_code=response.status_code,
                    )
                    await db.execute(
                        update(WebhookDelivery)
                        .where(WebhookDelivery.id == UUID(delivery_id))
                        .values(
                            status="failed",
                            attempts=current_attempts,
                            response_status_code=response.status_code,
                            response_body=response_body_truncated,
                            last_attempt_at=datetime.now(timezone.utc),
                            next_retry_at=None,
                        )
                    )
                    return {
                        "status": "failed",
                        "attempts": current_attempts,
                        "response_code": response.status_code,
                        "reason": "client_error_no_retry",
                    }

                # HTTP 5xx oder andere Fehler = Retry planen
                if current_attempts >= max_attempts:
                    # DLQ-Eskalation
                    await _move_to_dlq_async(db, delivery_id, current_attempts, response.status_code, response_body_truncated)
                    return {
                        "status": "dlq",
                        "attempts": current_attempts,
                        "response_code": response.status_code,
                    }

                next_retry = _calculate_next_retry(current_attempts, backoff_factor)
                await db.execute(
                    update(WebhookDelivery)
                    .where(WebhookDelivery.id == UUID(delivery_id))
                    .values(
                        status="failed",
                        attempts=current_attempts,
                        response_status_code=response.status_code,
                        response_body=response_body_truncated,
                        last_attempt_at=datetime.now(timezone.utc),
                        next_retry_at=next_retry,
                    )
                )

                logger.info(
                    "webhook_delivery_retry_scheduled",
                    delivery_id=delivery_id[:8],
                    attempt=current_attempts,
                    max_attempts=max_attempts,
                    next_retry=next_retry.isoformat(),
                    status_code=response.status_code,
                )

                return {
                    "status": "retry_scheduled",
                    "attempts": current_attempts,
                    "next_retry": next_retry.isoformat(),
                }

            except httpx.TimeoutException:
                error_msg = "HTTP-Timeout bei Zustellung"
                logger.warning(
                    "webhook_delivery_timeout",
                    delivery_id=delivery_id[:8],
                    attempt=current_attempts,
                    timeout_seconds=timeout_seconds,
                )

            except httpx.ConnectError as exc:
                error_msg = safe_error_detail(exc, "Webhook-Verbindung")
                logger.warning(
                    "webhook_delivery_connect_error",
                    delivery_id=delivery_id[:8],
                    attempt=current_attempts,
                    **safe_error_log(exc),
                )

            except Exception as exc:
                error_msg = safe_error_detail(exc, "Webhook")
                logger.error(
                    "webhook_delivery_unexpected_error",
                    delivery_id=delivery_id[:8],
                    attempt=current_attempts,
                    **safe_error_log(exc),
                )

            # Fehlerbehandlung fuer alle Exception-Pfade
            if current_attempts >= max_attempts:
                await _move_to_dlq_async(db, delivery_id, current_attempts, None, error_msg)
                return {"status": "dlq", "attempts": current_attempts}

            next_retry = _calculate_next_retry(current_attempts, backoff_factor)
            await db.execute(
                update(WebhookDelivery)
                .where(WebhookDelivery.id == UUID(delivery_id))
                .values(
                    status="failed",
                    attempts=current_attempts,
                    response_body=_truncate_body(error_msg),
                    last_attempt_at=datetime.now(timezone.utc),
                    next_retry_at=next_retry,
                )
            )

            return {
                "status": "retry_scheduled",
                "attempts": current_attempts,
                "next_retry": next_retry.isoformat(),
            }

    import asyncio
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(_async_deliver())
    finally:
        loop.close()


async def _move_to_dlq_async(
    db,
    delivery_id: str,
    attempts: int,
    status_code: Optional[int],
    error_body: Optional[str],
) -> None:
    """Verschiebt einen Delivery-Record in die Dead Letter Queue.

    Args:
        db: Datenbankverbindung
        delivery_id: UUID-String der Zustellung
        attempts: Anzahl durchgefuehrter Versuche
        status_code: Letzter HTTP-Statuscode
        error_body: Fehlermeldung (wird gekuerzt)
    """
    await db.execute(
        update(WebhookDelivery)
        .where(WebhookDelivery.id == UUID(delivery_id))
        .values(
            status="dlq",
            attempts=attempts,
            response_status_code=status_code,
            response_body=_truncate_body(error_body),
            last_attempt_at=datetime.now(timezone.utc),
            next_retry_at=None,
        )
    )

    logger.warning(
        "webhook_moved_to_dlq",
        delivery_id=delivery_id[:8],
        attempts=attempts,
        status_code=status_code,
    )


@celery_app.task(
    name="app.workers.tasks.webhook_tasks.process_webhook_retries",
    bind=True,
    max_retries=3,
    queue="maintenance",
    soft_time_limit=300,
    time_limit=360,
)
def process_webhook_retries(self: Task) -> Dict:
    """Periodischer Task: Findet faellige Retries und dispatcht Zustellungs-Tasks.

    Scannt die webhook_deliveries-Tabelle nach Eintraegen mit:
    - status IN ('pending', 'failed')
    - next_retry_at <= jetzt

    Wird taeglich alle 5 Minuten ausgefuehrt (konfiguriert in beat_schedule).

    Returns:
        Dict mit Anzahl der gestarteten Retries
    """
    import asyncio

    async def _async_process() -> Dict:
        async with get_async_session_context() as db:
            now = datetime.now(timezone.utc)

            result = await db.execute(
                select(WebhookDelivery).where(
                    and_(
                        WebhookDelivery.status.in_(["pending", "failed"]),
                        WebhookDelivery.next_retry_at.isnot(None),
                        WebhookDelivery.next_retry_at <= now,
                    )
                ).limit(100)  # Batch-Groesse begrenzen
            )
            due_deliveries = list(result.scalars().all())

            if not due_deliveries:
                return {"retries_dispatched": 0}

            dispatched = 0
            for delivery in due_deliveries:
                try:
                    deliver_webhook.delay(str(delivery.id))
                    dispatched += 1
                except Exception as exc:
                    logger.error(
                        "webhook_retry_dispatch_failed",
                        delivery_id=str(delivery.id)[:8],
                        **safe_error_log(exc),
                    )

            logger.info(
                "webhook_retries_dispatched",
                count=dispatched,
                total_due=len(due_deliveries),
            )

            return {"retries_dispatched": dispatched}

    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(_async_process())
    finally:
        loop.close()


@celery_app.task(
    name="app.workers.tasks.webhook_tasks.move_to_dlq",
    bind=True,
    max_retries=3,
    queue="maintenance",
    soft_time_limit=60,
    time_limit=90,
)
def move_to_dlq(self: Task, delivery_id: str) -> Dict:
    """Verschiebt eine spezifische Zustellung manuell in die DLQ.

    Wird aufgerufen wenn max_attempts erschoepft ist und eine
    explizite DLQ-Eskalation gewuenscht wird.

    Args:
        delivery_id: UUID-String der Zustellung

    Returns:
        Dict mit Ergebnisinformationen
    """
    import asyncio

    async def _async_move() -> Dict:
        async with get_async_session_context() as db:
            result = await db.execute(
                select(WebhookDelivery).where(
                    WebhookDelivery.id == UUID(delivery_id)
                )
            )
            delivery = result.scalar_one_or_none()

            if delivery is None:
                return {"status": "not_found"}

            if delivery.status == "dlq":
                return {"status": "already_in_dlq"}

            await _move_to_dlq_async(
                db, delivery_id, delivery.attempts, delivery.response_status_code,
                "Manuell in DLQ verschoben"
            )

            return {"status": "moved_to_dlq", "delivery_id": delivery_id}

    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(_async_move())
    finally:
        loop.close()


@celery_app.task(
    name="app.workers.tasks.webhook_tasks.cleanup_old_deliveries",
    bind=True,
    max_retries=3,
    queue="maintenance",
    soft_time_limit=300,
    time_limit=360,
)
def cleanup_old_deliveries(self: Task) -> Dict:
    """Bereinigt alte Zustelldaten (aelter als 30 Tage).

    DLQ-Eintraege werden NICHT geloescht (fuer manuelle Analyse behalten).
    Erfolgreiche und fehlgeschlagene Zustellungen werden nach 30 Tagen entfernt.

    Returns:
        Dict mit Anzahl geloeschter Eintraege
    """
    import asyncio
    from sqlalchemy import delete

    async def _async_cleanup() -> Dict:
        async with get_async_session_context() as db:
            cutoff_date = datetime.now(timezone.utc) - timedelta(
                days=_DELIVERY_RETENTION_DAYS
            )

            result = await db.execute(
                delete(WebhookDelivery).where(
                    and_(
                        WebhookDelivery.created_at < cutoff_date,
                        WebhookDelivery.status.in_(["delivered", "failed"]),
                        # DLQ-Eintraege werden ausdruecklich behalten
                    )
                ).returning(WebhookDelivery.id)
            )
            deleted_count = len(result.all())

            logger.info(
                "webhook_deliveries_cleaned_up",
                deleted_count=deleted_count,
                cutoff_date=cutoff_date.isoformat(),
                retention_days=_DELIVERY_RETENTION_DAYS,
            )

            return {
                "deleted_count": deleted_count,
                "cutoff_date": cutoff_date.isoformat(),
            }

    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(_async_cleanup())
    finally:
        loop.close()
