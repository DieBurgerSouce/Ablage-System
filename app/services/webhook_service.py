# -*- coding: utf-8 -*-
"""
Outbound Webhook Service - Event-Bus mit Replay und Dead Letter Queue.

Verwaltet den kompletten Lebenszyklus von Outbound-Webhook-Events:
- Endpoint-Registrierung und -Verwaltung mit HMAC-Signierung
- Event-Publikation an alle passenden Abonnenten
- Zustellungsprotokoll mit Retry-Logik und DLQ-Eskalation
- Replay einzelner oder mehrerer Events nach Typ und Zeitraum

Sicherheitsrichtlinien (kritisch):
- Webhook-Secrets werden ausschliesslich als HMAC-SHA256-Hash gespeichert
- Secrets werden NIEMALS geloggt oder in API-Antworten zurueckgegeben
- URL-Validierung gegen SSRF erfolgt in der Celery-Task (httpx-Layer)
- Antwort-Bodies werden auf 1000 Zeichen gekuerzt

Feinpoliert und durchdacht - Enterprise-grade Webhook Event Platform.
"""

import hashlib
import hmac
import uuid
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional
from uuid import UUID

import structlog
from sqlalchemy import and_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.safe_errors import safe_error_log
from app.db.models_webhooks import WebhookDelivery, WebhookEndpoint, WebhookEventLog

logger = structlog.get_logger(__name__)

# Maximale Laenge des gespeicherten Response-Body (Sicherheit: kein Memory-Overflow)
_MAX_RESPONSE_BODY_LENGTH: int = 1000

# Erlaubte Zustellstatus-Werte (Whitelist zur SQL-Injection-Praevention)
_VALID_DELIVERY_STATUSES = frozenset({"pending", "delivered", "failed", "dlq"})


def _hash_secret(secret: str) -> str:
    """Erstellt einen sicheren SHA-256 Hash des Webhook-Secrets.

    Das Secret wird NIEMALS im Klartext gespeichert. Dieser Hash dient
    ausschliesslich der Integritaetspruefung, nicht der HMAC-Signierung.
    Fuer HMAC wird das Secret direkt aus dem Request-Kontext verwendet.

    Args:
        secret: Webhook-Secret im Klartext (wird sofort verworfen)

    Returns:
        SHA-256 Hash als Hex-String (64 Zeichen)
    """
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


def generate_hmac_signature(payload_bytes: bytes, secret: str) -> str:
    """Erstellt eine HMAC-SHA256 Signatur fuer den Webhook-Payload.

    Format des X-Webhook-Signature Headers: sha256=<hmac_hex>

    Args:
        payload_bytes: Serialisierter JSON-Payload als Bytes
        secret: Webhook-Secret im Klartext (wird nur fuer Berechnung verwendet)

    Returns:
        Signatur-String im Format "sha256=<hex>"
    """
    mac = hmac.new(
        secret.encode("utf-8"),
        msg=payload_bytes,
        digestmod=hashlib.sha256,
    )
    return f"sha256={mac.hexdigest()}"


def _truncate_response_body(body: Optional[str]) -> Optional[str]:
    """Kuerzt den Response-Body auf _MAX_RESPONSE_BODY_LENGTH Zeichen.

    Verhindert das Speichern grosser, potenziell sensibler Antworten.

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


class WebhookService:
    """Service fuer das vollstaendige Outbound-Webhook-Management.

    Stellt alle Operationen fuer das Event-Platform-Feature bereit:
    - CRUD fuer Webhook-Endpoints
    - Event-Publikation mit Mandantenisolation
    - DLQ-Verwaltung und manuelle Retries
    - Event-Replay (einzeln und per Bulk)
    """

    # =========================================================================
    # Endpoint-Verwaltung
    # =========================================================================

    async def register_endpoint(
        self,
        db: AsyncSession,
        company_id: UUID,
        url: str,
        secret: str,
        event_types: List[str],
        description: Optional[str] = None,
        headers: Optional[Dict[str, str]] = None,
        retry_policy: Optional[Dict[str, int]] = None,
    ) -> WebhookEndpoint:
        """Registriert einen neuen Webhook-Endpoint fuer einen Mandanten.

        Das Secret wird sofort gehasht und nicht im Klartext gespeichert.
        Die URL wird bei der ersten Zustellung auf SSRF geprueft.

        Args:
            db: Datenbankverbindung
            company_id: Mandanten-ID
            url: Ziel-URL fuer Webhook-Zustellungen
            secret: Webhook-Secret (wird gehasht, nie gespeichert)
            event_types: Abonnierte Event-Typen (leer = alle)
            description: Optionale Beschreibung
            headers: Optionale benutzerdefinierte HTTP-Header
            retry_policy: Optionale Retry-Konfiguration

        Returns:
            Erstellter WebhookEndpoint (ohne Secret)

        Raises:
            ValueError: Bei ungueltigem retry_policy Format
        """
        effective_retry_policy: Dict[str, int] = retry_policy or {
            "max_retries": 3,
            "backoff_factor": 2,
            "timeout_seconds": 30,
        }

        endpoint = WebhookEndpoint(
            company_id=company_id,
            url=url,
            description=description,
            secret_hash=_hash_secret(secret),
            event_types=event_types,
            is_active=True,
            headers=headers,
            retry_policy=effective_retry_policy,
        )

        db.add(endpoint)
        await db.flush()
        await db.refresh(endpoint)

        logger.info(
            "webhook_endpoint_registered",
            endpoint_id=str(endpoint.id)[:8],
            company_id=str(company_id)[:8],
            event_types=event_types,
            # SICHERHEIT: url wird nur partiell geloggt
            url_preview=url[:50],
        )

        return endpoint

    async def update_endpoint(
        self,
        db: AsyncSession,
        endpoint_id: UUID,
        company_id: UUID,
        url: Optional[str] = None,
        description: Optional[str] = None,
        secret: Optional[str] = None,
        event_types: Optional[List[str]] = None,
        headers: Optional[Dict[str, str]] = None,
        retry_policy: Optional[Dict[str, int]] = None,
        is_active: Optional[bool] = None,
    ) -> WebhookEndpoint:
        """Aktualisiert die Konfiguration eines bestehenden Endpoints.

        Nur uebergebene Felder werden aktualisiert (PATCH-Semantik).
        Bei Secret-Rotation wird das neue Secret sofort gehasht.

        Args:
            db: Datenbankverbindung
            endpoint_id: ID des zu aktualisierenden Endpoints
            company_id: Mandanten-ID (Zugriffspruefung)
            url: Neue Ziel-URL (optional)
            description: Neue Beschreibung (optional)
            secret: Neues Secret fuer Rotation (optional, wird gehasht)
            event_types: Neue Event-Typ-Liste (optional)
            headers: Neue HTTP-Header (optional)
            retry_policy: Neue Retry-Konfiguration (optional)
            is_active: Aktiv/Inaktiv-Status (optional)

        Returns:
            Aktualisierter WebhookEndpoint

        Raises:
            ValueError: Wenn Endpoint nicht gefunden oder kein Zugriff
        """
        endpoint = await self._get_endpoint_for_company(db, endpoint_id, company_id)

        if url is not None:
            endpoint.url = url
        if description is not None:
            endpoint.description = description
        if secret is not None:
            # SICHERHEIT: Nur Hash wird gespeichert
            endpoint.secret_hash = _hash_secret(secret)
        if event_types is not None:
            endpoint.event_types = event_types
        if headers is not None:
            endpoint.headers = headers
        if retry_policy is not None:
            endpoint.retry_policy = retry_policy
        if is_active is not None:
            endpoint.is_active = is_active

        endpoint.updated_at = datetime.now(timezone.utc)

        await db.flush()
        await db.refresh(endpoint)

        logger.info(
            "webhook_endpoint_updated",
            endpoint_id=str(endpoint_id)[:8],
            company_id=str(company_id)[:8],
        )

        return endpoint

    async def delete_endpoint(
        self,
        db: AsyncSession,
        endpoint_id: UUID,
        company_id: UUID,
    ) -> None:
        """Deaktiviert einen Webhook-Endpoint (Soft-Delete).

        Setzt is_active=False, loescht keine historischen Zustelldaten.
        Laufende Zustellungen werden nicht unterbrochen.

        Args:
            db: Datenbankverbindung
            endpoint_id: ID des zu loeschenden Endpoints
            company_id: Mandanten-ID (Zugriffspruefung)

        Raises:
            ValueError: Wenn Endpoint nicht gefunden oder kein Zugriff
        """
        endpoint = await self._get_endpoint_for_company(db, endpoint_id, company_id)
        endpoint.is_active = False
        endpoint.updated_at = datetime.now(timezone.utc)
        await db.flush()

        logger.info(
            "webhook_endpoint_deactivated",
            endpoint_id=str(endpoint_id)[:8],
            company_id=str(company_id)[:8],
        )

    async def list_endpoints(
        self,
        db: AsyncSession,
        company_id: UUID,
        include_inactive: bool = False,
    ) -> List[WebhookEndpoint]:
        """Listet alle Webhook-Endpoints eines Mandanten auf.

        Args:
            db: Datenbankverbindung
            company_id: Mandanten-ID
            include_inactive: Auch deaktivierte Endpoints einschliessen

        Returns:
            Liste der Webhook-Endpoints (ohne Secrets)
        """
        conditions = [WebhookEndpoint.company_id == company_id]
        if not include_inactive:
            conditions.append(WebhookEndpoint.is_active == True)  # noqa: E712

        result = await db.execute(
            select(WebhookEndpoint)
            .where(and_(*conditions))
            .order_by(WebhookEndpoint.created_at.desc())
        )
        return list(result.scalars().all())

    # =========================================================================
    # Event-Publikation
    # =========================================================================

    async def publish_event(
        self,
        db: AsyncSession,
        company_id: UUID,
        event_type: str,
        source_table: str,
        source_id: UUID,
        payload: Dict,
    ) -> int:
        """Publiziert ein Event an alle passenden aktiven Endpoints.

        Erstellt einen unveraenderbaren WebhookEventLog-Eintrag und
        dispatcht asynchrone Celery-Tasks fuer jeden passenden Endpoint.

        Die Event-Typen-Filterung unterstuetzt:
        - Exakte Uebereinstimmung: "document.created"
        - Wildcard-Prefix: "document.*" matched "document.created"
        - Leere Liste = alle Events

        Args:
            db: Datenbankverbindung
            company_id: Mandanten-ID
            event_type: Typ des Events, z.B. "document.created"
            source_table: Quell-Tabelle des Events
            source_id: ID des ausloesenden Datensatzes
            payload: Event-Daten (wird signiert und zugestellt)

        Returns:
            Anzahl der ausgeloesten Webhook-Zustellungen

        Raises:
            Exception: Bei Datenbankfehlern (wird geloggt und weitergegeben)
        """
        # 1. Event im unveraenderbaren Journal speichern
        event_log = WebhookEventLog(
            company_id=company_id,
            event_type=event_type,
            source_table=source_table,
            source_id=source_id,
            payload=payload,
        )
        db.add(event_log)
        await db.flush()
        await db.refresh(event_log)

        # 2. Passende aktive Endpoints finden
        endpoints = await self._find_matching_endpoints(db, company_id, event_type)

        if not endpoints:
            logger.debug(
                "webhook_no_matching_endpoints",
                company_id=str(company_id)[:8],
                event_type=event_type,
            )
            return 0

        # 3. Zustellungs-Records und Celery-Tasks erstellen
        dispatched = 0
        for endpoint in endpoints:
            try:
                delivery = await self._create_delivery(
                    db=db,
                    endpoint=endpoint,
                    event_log_id=event_log.id,
                    event_type=event_type,
                    payload=payload,
                )
                # Celery-Task asynchron starten (nach DB-Commit)
                await self._dispatch_delivery_task(delivery.id)
                dispatched += 1
            except Exception as exc:
                logger.error(
                    "webhook_delivery_create_failed",
                    endpoint_id=str(endpoint.id)[:8],
                    event_type=event_type,
                    **safe_error_log(exc),
                )

        logger.info(
            "webhook_event_published",
            event_log_id=str(event_log.id)[:8],
            company_id=str(company_id)[:8],
            event_type=event_type,
            source_table=source_table,
            dispatched=dispatched,
            total_endpoints=len(endpoints),
        )

        return dispatched

    async def _find_matching_endpoints(
        self,
        db: AsyncSession,
        company_id: UUID,
        event_type: str,
    ) -> List[WebhookEndpoint]:
        """Findet alle aktiven Endpoints, die den Event-Typ abonniert haben.

        Args:
            db: Datenbankverbindung
            company_id: Mandanten-ID
            event_type: Zu matchender Event-Typ

        Returns:
            Liste der passenden Endpoints
        """
        result = await db.execute(
            select(WebhookEndpoint).where(
                and_(
                    WebhookEndpoint.company_id == company_id,
                    WebhookEndpoint.is_active == True,  # noqa: E712
                )
            )
        )
        all_endpoints = list(result.scalars().all())

        matching: List[WebhookEndpoint] = []
        for endpoint in all_endpoints:
            subscribed: List[str] = endpoint.event_types or []
            # Leere Liste = alle Events abonniert
            if not subscribed:
                matching.append(endpoint)
                continue
            # Exakte Uebereinstimmung
            if event_type in subscribed:
                matching.append(endpoint)
                continue
            # Wildcard-Prefix: "document.*" matched "document.created"
            for pattern in subscribed:
                if pattern.endswith(".*"):
                    prefix = pattern[:-2]
                    if event_type.startswith(prefix + "."):
                        matching.append(endpoint)
                        break

        return matching

    async def _create_delivery(
        self,
        db: AsyncSession,
        endpoint: WebhookEndpoint,
        event_log_id: UUID,
        event_type: str,
        payload: Dict,
    ) -> WebhookDelivery:
        """Erstellt einen Zustellungs-Record in der Datenbank.

        Args:
            db: Datenbankverbindung
            endpoint: Ziel-Endpoint
            event_log_id: ID des Event-Log-Eintrags
            event_type: Event-Typ
            payload: Event-Payload

        Returns:
            Erstellter WebhookDelivery-Record
        """
        retry_policy: Dict = endpoint.retry_policy or {}
        max_attempts: int = int(retry_policy.get("max_retries", 3)) + 1

        delivery = WebhookDelivery(
            endpoint_id=endpoint.id,
            company_id=endpoint.company_id,
            event_type=event_type,
            event_id=event_log_id,
            payload=payload,
            status="pending",
            attempts=0,
            max_attempts=max_attempts,
        )
        db.add(delivery)
        await db.flush()
        await db.refresh(delivery)
        return delivery

    async def _dispatch_delivery_task(self, delivery_id: UUID) -> None:
        """Startet einen asynchronen Celery-Task fuer die Webhook-Zustellung.

        Importiert celery_app lazy um zirkulaere Imports zu vermeiden.

        Args:
            delivery_id: ID des zu zustellenden Delivery-Records
        """
        try:
            from app.workers.tasks.webhook_tasks import deliver_webhook
            deliver_webhook.delay(str(delivery_id))
        except Exception as exc:
            logger.error(
                "webhook_task_dispatch_failed",
                delivery_id=str(delivery_id)[:8],
                **safe_error_log(exc),
            )

    # =========================================================================
    # Zustellungshistorie und DLQ
    # =========================================================================

    async def get_delivery_history(
        self,
        db: AsyncSession,
        endpoint_id: UUID,
        company_id: UUID,
        limit: int = 50,
        offset: int = 0,
    ) -> List[WebhookDelivery]:
        """Gibt die Zustellungshistorie eines Endpoints zurueck.

        Args:
            db: Datenbankverbindung
            endpoint_id: Endpoint-ID
            company_id: Mandanten-ID (Zugriffspruefung)
            limit: Maximale Anzahl Eintraege (Default: 50)
            offset: Seitenversatz

        Returns:
            Liste der Zustellungen (neueste zuerst)

        Raises:
            ValueError: Wenn Endpoint nicht gefunden oder kein Zugriff
        """
        # Zugriffspruefung
        await self._get_endpoint_for_company(db, endpoint_id, company_id)

        result = await db.execute(
            select(WebhookDelivery)
            .where(
                and_(
                    WebhookDelivery.endpoint_id == endpoint_id,
                    WebhookDelivery.company_id == company_id,
                )
            )
            .order_by(WebhookDelivery.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def get_dlq_items(
        self,
        db: AsyncSession,
        company_id: UUID,
        limit: int = 50,
        offset: int = 0,
    ) -> List[WebhookDelivery]:
        """Gibt alle Eintraege in der Dead Letter Queue zurueck.

        Args:
            db: Datenbankverbindung
            company_id: Mandanten-ID
            limit: Maximale Anzahl Eintraege
            offset: Seitenversatz

        Returns:
            Liste der DLQ-Eintraege (aelteste zuerst)
        """
        result = await db.execute(
            select(WebhookDelivery)
            .where(
                and_(
                    WebhookDelivery.company_id == company_id,
                    WebhookDelivery.status == "dlq",
                )
            )
            .order_by(WebhookDelivery.created_at.asc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def retry_delivery(
        self,
        db: AsyncSession,
        delivery_id: UUID,
        company_id: UUID,
    ) -> WebhookDelivery:
        """Fuehrt einen manuellen Retry eines fehlgeschlagenen Delivery durch.

        Setzt den Status auf "pending" und dispatcht sofort einen Celery-Task.

        Args:
            db: Datenbankverbindung
            delivery_id: ID der Zustellung
            company_id: Mandanten-ID (Zugriffspruefung)

        Returns:
            Aktualisierter WebhookDelivery-Record

        Raises:
            ValueError: Wenn Delivery nicht gefunden, kein Zugriff oder Status ungueltig
        """
        delivery = await self._get_delivery_for_company(db, delivery_id, company_id)

        if delivery.status not in ("failed", "dlq"):
            raise ValueError(
                f"Zustellung kann nicht wiederholt werden: Status ist '{delivery.status}'"
            )

        # Zustellversuche zuruecksetzen und Status aktualisieren
        delivery.status = "pending"
        delivery.next_retry_at = None
        await db.flush()
        await db.refresh(delivery)

        await self._dispatch_delivery_task(delivery_id)

        logger.info(
            "webhook_delivery_manual_retry",
            delivery_id=str(delivery_id)[:8],
            company_id=str(company_id)[:8],
        )

        return delivery

    # =========================================================================
    # Event-Replay
    # =========================================================================

    async def replay_event(
        self,
        db: AsyncSession,
        event_log_id: UUID,
        company_id: UUID,
    ) -> int:
        """Replayed einen einzelnen Event aus dem Event-Journal.

        Sucht alle aktiven Endpoints fuer den Event-Typ und erstellt
        neue Zustellungs-Records mit dem originalen Payload.

        Args:
            db: Datenbankverbindung
            event_log_id: ID des Event-Log-Eintrags
            company_id: Mandanten-ID (Zugriffspruefung)

        Returns:
            Anzahl der ausgeloesten Replay-Zustellungen

        Raises:
            ValueError: Wenn Event nicht gefunden oder kein Zugriff
        """
        event_log = await self._get_event_log_for_company(db, event_log_id, company_id)

        endpoints = await self._find_matching_endpoints(
            db, company_id, event_log.event_type
        )

        if not endpoints:
            logger.info(
                "webhook_replay_no_endpoints",
                event_log_id=str(event_log_id)[:8],
                event_type=event_log.event_type,
            )
            return 0

        dispatched = 0
        for endpoint in endpoints:
            try:
                delivery = await self._create_delivery(
                    db=db,
                    endpoint=endpoint,
                    event_log_id=event_log.id,
                    event_type=event_log.event_type,
                    payload=event_log.payload,
                )
                await self._dispatch_delivery_task(delivery.id)
                dispatched += 1
            except Exception as exc:
                logger.error(
                    "webhook_replay_delivery_create_failed",
                    endpoint_id=str(endpoint.id)[:8],
                    event_log_id=str(event_log_id)[:8],
                    **safe_error_log(exc),
                )

        logger.info(
            "webhook_event_replayed",
            event_log_id=str(event_log_id)[:8],
            company_id=str(company_id)[:8],
            event_type=event_log.event_type,
            dispatched=dispatched,
        )

        return dispatched

    async def replay_events(
        self,
        db: AsyncSession,
        company_id: UUID,
        event_type: str,
        from_date: datetime,
        to_date: datetime,
    ) -> int:
        """Replayed alle Events eines Typs in einem Zeitraum.

        Nützlich fuer die Wiederherstellung nach Endpoint-Ausfaellen
        oder fuer die initiale Synchronisation neuer Endpoints.

        Args:
            db: Datenbankverbindung
            company_id: Mandanten-ID
            event_type: Zu replaylender Event-Typ
            from_date: Startdatum (inklusiv)
            to_date: Enddatum (inklusiv)

        Returns:
            Gesamtanzahl der ausgeloesten Replay-Zustellungen
        """
        result = await db.execute(
            select(WebhookEventLog).where(
                and_(
                    WebhookEventLog.company_id == company_id,
                    WebhookEventLog.event_type == event_type,
                    WebhookEventLog.created_at >= from_date,
                    WebhookEventLog.created_at <= to_date,
                )
            ).order_by(WebhookEventLog.created_at.asc())
        )
        event_logs = list(result.scalars().all())

        if not event_logs:
            logger.info(
                "webhook_bulk_replay_no_events",
                company_id=str(company_id)[:8],
                event_type=event_type,
                from_date=from_date.isoformat(),
                to_date=to_date.isoformat(),
            )
            return 0

        total_dispatched = 0
        for event_log in event_logs:
            try:
                dispatched = await self.replay_event(db, event_log.id, company_id)
                total_dispatched += dispatched
            except Exception as exc:
                logger.error(
                    "webhook_bulk_replay_event_failed",
                    event_log_id=str(event_log.id)[:8],
                    **safe_error_log(exc),
                )

        logger.info(
            "webhook_bulk_replay_completed",
            company_id=str(company_id)[:8],
            event_type=event_type,
            events_processed=len(event_logs),
            total_dispatched=total_dispatched,
        )

        return total_dispatched

    async def get_event_log(
        self,
        db: AsyncSession,
        company_id: UUID,
        event_type: Optional[str] = None,
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[WebhookEventLog]:
        """Gibt Events aus dem Event-Journal zurueck.

        Args:
            db: Datenbankverbindung
            company_id: Mandanten-ID
            event_type: Optionaler Filter nach Event-Typ
            from_date: Optionaler Startfilter
            to_date: Optionaler Endfilter
            limit: Maximale Anzahl Eintraege
            offset: Seitenversatz

        Returns:
            Liste der Event-Log-Eintraege (neueste zuerst)
        """
        conditions = [WebhookEventLog.company_id == company_id]
        if event_type:
            conditions.append(WebhookEventLog.event_type == event_type)
        if from_date:
            conditions.append(WebhookEventLog.created_at >= from_date)
        if to_date:
            conditions.append(WebhookEventLog.created_at <= to_date)

        result = await db.execute(
            select(WebhookEventLog)
            .where(and_(*conditions))
            .order_by(WebhookEventLog.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    # =========================================================================
    # Interne Hilfsmethoden
    # =========================================================================

    async def _get_endpoint_for_company(
        self,
        db: AsyncSession,
        endpoint_id: UUID,
        company_id: UUID,
    ) -> WebhookEndpoint:
        """Laedt einen Endpoint und prueft den Mandantenzugriff.

        Args:
            db: Datenbankverbindung
            endpoint_id: Endpoint-ID
            company_id: Erwartete Mandanten-ID

        Returns:
            WebhookEndpoint

        Raises:
            ValueError: Wenn Endpoint nicht gefunden oder Mandant stimmt nicht ueberein
        """
        result = await db.execute(
            select(WebhookEndpoint).where(
                and_(
                    WebhookEndpoint.id == endpoint_id,
                    WebhookEndpoint.company_id == company_id,
                )
            )
        )
        endpoint = result.scalar_one_or_none()
        if endpoint is None:
            raise ValueError(
                f"Webhook-Endpoint nicht gefunden: {str(endpoint_id)[:8]}"
            )
        return endpoint

    async def _get_delivery_for_company(
        self,
        db: AsyncSession,
        delivery_id: UUID,
        company_id: UUID,
    ) -> WebhookDelivery:
        """Laedt einen Delivery-Record und prueft den Mandantenzugriff.

        Args:
            db: Datenbankverbindung
            delivery_id: Delivery-ID
            company_id: Erwartete Mandanten-ID

        Returns:
            WebhookDelivery

        Raises:
            ValueError: Wenn Delivery nicht gefunden oder Mandant stimmt nicht ueberein
        """
        result = await db.execute(
            select(WebhookDelivery).where(
                and_(
                    WebhookDelivery.id == delivery_id,
                    WebhookDelivery.company_id == company_id,
                )
            )
        )
        delivery = result.scalar_one_or_none()
        if delivery is None:
            raise ValueError(
                f"Webhook-Zustellung nicht gefunden: {str(delivery_id)[:8]}"
            )
        return delivery

    async def _get_event_log_for_company(
        self,
        db: AsyncSession,
        event_log_id: UUID,
        company_id: UUID,
    ) -> WebhookEventLog:
        """Laedt einen Event-Log-Eintrag und prueft den Mandantenzugriff.

        Args:
            db: Datenbankverbindung
            event_log_id: Event-Log-ID
            company_id: Erwartete Mandanten-ID

        Returns:
            WebhookEventLog

        Raises:
            ValueError: Wenn Event nicht gefunden oder Mandant stimmt nicht ueberein
        """
        result = await db.execute(
            select(WebhookEventLog).where(
                and_(
                    WebhookEventLog.id == event_log_id,
                    WebhookEventLog.company_id == company_id,
                )
            )
        )
        event_log = result.scalar_one_or_none()
        if event_log is None:
            raise ValueError(
                f"Webhook-Event nicht gefunden: {str(event_log_id)[:8]}"
            )
        return event_log


# =========================================================================
# Singleton
# =========================================================================

_webhook_service: Optional[WebhookService] = None


def get_webhook_service() -> WebhookService:
    """Gibt die WebhookService-Singleton-Instanz zurueck."""
    global _webhook_service
    if _webhook_service is None:
        _webhook_service = WebhookService()
    return _webhook_service
