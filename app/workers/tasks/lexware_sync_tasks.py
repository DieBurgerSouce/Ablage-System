# -*- coding: utf-8 -*-
"""
Lexware Synchronisation Celery Tasks.

Automatische Synchronisation mit Lexware:
- Delta-Sync fuer Kunden, Lieferanten, Rechnungen
- Change-Tracking und Konfliktbehandlung
- Webhook-basierte Real-time Updates
- Offline-Queue Processing

Feinpoliert und durchdacht - Zuverlaessige ERP-Synchronisation.
"""

from datetime import timedelta
from typing import Any, Dict, List, Optional
from uuid import UUID

import structlog
from celery import shared_task

from app.core.datetime_utils import utc_now
from app.core.safe_errors import safe_error_log, safe_error_detail
from app.services.erp.base_connector import ERPEntity, ERPSyncDirection
from app.services.erp.lexware_connector import (
    LexwareConnectionConfig,
    LexwareConnector,
    LexwareWebhookEvent,
    get_lexware_connector,
)

logger = structlog.get_logger(__name__)


# =============================================================================
# Celery Beat Schedule (zu celery_app.py hinzufuegen)
# =============================================================================
#
# LEXWARE_BEAT_SCHEDULE = {
#     "lexware.sync_customers": {
#         "task": "lexware_sync.sync_customers",
#         "schedule": crontab(minute="*/15"),  # Alle 15 Min
#         "options": {"queue": "erp"},
#     },
#     "lexware.sync_suppliers": {
#         "task": "lexware_sync.sync_suppliers",
#         "schedule": crontab(minute="*/15"),  # Alle 15 Min
#         "options": {"queue": "erp"},
#     },
#     "lexware.sync_invoices": {
#         "task": "lexware_sync.sync_invoices",
#         "schedule": crontab(minute="*/30"),  # Alle 30 Min
#         "options": {"queue": "erp"},
#     },
#     "lexware.full_sync": {
#         "task": "lexware_sync.full_sync",
#         "schedule": crontab(hour=2, minute=0),  # Taeglich 02:00
#         "options": {"queue": "erp"},
#     },
#     "lexware.process_offline_queue": {
#         "task": "lexware_sync.process_offline_queue",
#         "schedule": crontab(minute="*/5"),  # Alle 5 Min
#         "options": {"queue": "erp"},
#     },
# }


# =============================================================================
# Delta-Sync Tasks
# =============================================================================


@shared_task(
    name="lexware_sync.sync_customers",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    queue="erp",
)
def sync_customers_task(
    self,
    company_id: Optional[str] = None,
    direction: str = "bidirectional",
    since_hours: int = 24,
) -> Dict[str, Any]:
    """
    Synchronisiert Kunden mit Lexware.

    Args:
        company_id: Optional Company UUID (fuer Multi-Tenant)
        direction: Sync-Richtung (pull, push, bidirectional)
        since_hours: Zeitraum fuer Delta-Sync

    Returns:
        Sync-Ergebnis
    """
    import asyncio

    async def _sync() -> Dict[str, Any]:
        connector = get_lexware_connector()
        if not connector:
            logger.warning("lexware_connector_not_configured")
            return {
                "success": False,
                "error": "Lexware Connector nicht konfiguriert",
            }

        if not await connector.connect():
            return {
                "success": False,
                "error": "Verbindung zu Lexware fehlgeschlagen",
            }

        try:
            sync_direction = ERPSyncDirection(direction)
            since = utc_now() - timedelta(hours=since_hours)

            result = await connector.sync_customers(
                direction=sync_direction,
                since=since,
            )

            logger.info(
                "lexware_sync_customers_completed",
                records_synced=result.records_synced,
                records_created=result.records_created,
                records_updated=result.records_updated,
                duration=result.duration_seconds,
            )

            return result.to_dict()

        finally:
            await connector.disconnect()

    try:
        return asyncio.get_event_loop().run_until_complete(_sync())
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(_sync())
        finally:
            loop.close()


@shared_task(
    name="lexware_sync.sync_suppliers",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    queue="erp",
)
def sync_suppliers_task(
    self,
    company_id: Optional[str] = None,
    direction: str = "bidirectional",
    since_hours: int = 24,
) -> Dict[str, Any]:
    """
    Synchronisiert Lieferanten mit Lexware.

    Args:
        company_id: Optional Company UUID
        direction: Sync-Richtung
        since_hours: Zeitraum fuer Delta-Sync

    Returns:
        Sync-Ergebnis
    """
    import asyncio

    async def _sync() -> Dict[str, Any]:
        connector = get_lexware_connector()
        if not connector:
            return {
                "success": False,
                "error": "Lexware Connector nicht konfiguriert",
            }

        if not await connector.connect():
            return {
                "success": False,
                "error": "Verbindung zu Lexware fehlgeschlagen",
            }

        try:
            sync_direction = ERPSyncDirection(direction)
            since = utc_now() - timedelta(hours=since_hours)

            result = await connector.sync_suppliers(
                direction=sync_direction,
                since=since,
            )

            logger.info(
                "lexware_sync_suppliers_completed",
                records_synced=result.records_synced,
                records_created=result.records_created,
                records_updated=result.records_updated,
                duration=result.duration_seconds,
            )

            return result.to_dict()

        finally:
            await connector.disconnect()

    try:
        return asyncio.get_event_loop().run_until_complete(_sync())
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(_sync())
        finally:
            loop.close()


@shared_task(
    name="lexware_sync.sync_invoices",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    queue="erp",
)
def sync_invoices_task(
    self,
    company_id: Optional[str] = None,
    direction: str = "pull",
    since_hours: int = 24,
) -> Dict[str, Any]:
    """
    Synchronisiert Rechnungen mit Lexware.

    Args:
        company_id: Optional Company UUID
        direction: Sync-Richtung (meist nur pull)
        since_hours: Zeitraum fuer Delta-Sync

    Returns:
        Sync-Ergebnis
    """
    import asyncio

    async def _sync() -> Dict[str, Any]:
        connector = get_lexware_connector()
        if not connector:
            return {
                "success": False,
                "error": "Lexware Connector nicht konfiguriert",
            }

        if not await connector.connect():
            return {
                "success": False,
                "error": "Verbindung zu Lexware fehlgeschlagen",
            }

        try:
            sync_direction = ERPSyncDirection(direction)
            since = utc_now() - timedelta(hours=since_hours)

            result = await connector.sync_invoices(
                direction=sync_direction,
                since=since,
            )

            logger.info(
                "lexware_sync_invoices_completed",
                records_synced=result.records_synced,
                records_created=result.records_created,
                records_updated=result.records_updated,
                duration=result.duration_seconds,
            )

            return result.to_dict()

        finally:
            await connector.disconnect()

    try:
        return asyncio.get_event_loop().run_until_complete(_sync())
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(_sync())
        finally:
            loop.close()


# =============================================================================
# Full Sync Task
# =============================================================================


@shared_task(
    name="lexware_sync.full_sync",
    bind=True,
    max_retries=1,
    default_retry_delay=300,
    queue="erp",
    time_limit=3600,  # 1 Stunde
)
def full_sync_task(
    self,
    company_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Fuehrt eine vollstaendige Synchronisation durch.

    Wird taeglich ausgefuehrt fuer Daten-Konsistenz.

    Args:
        company_id: Optional Company UUID

    Returns:
        Aggregiertes Sync-Ergebnis
    """
    import asyncio

    async def _full_sync() -> Dict[str, Any]:
        connector = get_lexware_connector()
        if not connector:
            return {
                "success": False,
                "error": "Lexware Connector nicht konfiguriert",
            }

        if not await connector.connect():
            return {
                "success": False,
                "error": "Verbindung zu Lexware fehlgeschlagen",
            }

        results: Dict[str, Any] = {
            "success": True,
            "entities": {},
            "total_synced": 0,
            "total_created": 0,
            "total_updated": 0,
            "errors": [],
        }

        try:
            # Sync all entities
            for entity_type, sync_func in [
                ("customers", connector.sync_customers),
                ("suppliers", connector.sync_suppliers),
                ("invoices", connector.sync_invoices),
            ]:
                try:
                    result = await sync_func(
                        direction=ERPSyncDirection.BIDIRECTIONAL,
                        since=None,  # Full sync
                    )

                    results["entities"][entity_type] = result.to_dict()
                    results["total_synced"] += result.records_synced
                    results["total_created"] += result.records_created
                    results["total_updated"] += result.records_updated

                    if not result.success:
                        results["errors"].append(
                            f"{entity_type}: {result.error_message}"
                        )

                except Exception as e:
                    results["errors"].append(f"{entity_type}: {safe_error_detail(e, 'Lexware')}")
                    logger.error(
                        "lexware_full_sync_entity_error",
                        entity=entity_type,
                        **safe_error_log(e),
                    )

            results["success"] = len(results["errors"]) == 0

            logger.info(
                "lexware_full_sync_completed",
                total_synced=results["total_synced"],
                total_created=results["total_created"],
                total_updated=results["total_updated"],
                errors=len(results["errors"]),
            )

            return results

        finally:
            await connector.disconnect()

    try:
        return asyncio.get_event_loop().run_until_complete(_full_sync())
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(_full_sync())
        finally:
            loop.close()


# =============================================================================
# Offline Queue Processing
# =============================================================================


@shared_task(
    name="lexware_sync.process_offline_queue",
    bind=True,
    max_retries=1,
    queue="erp",
)
def process_offline_queue_task(self) -> Dict[str, Any]:
    """
    Verarbeitet die Offline-Queue.

    Wird regelmaessig ausgefuehrt um fehlgeschlagene Requests
    erneut zu versuchen.

    Returns:
        Anzahl verarbeiteter Requests
    """
    import asyncio

    async def _process() -> Dict[str, Any]:
        connector = get_lexware_connector()
        if not connector:
            return {"processed": 0, "error": "Connector nicht konfiguriert"}

        if not await connector.connect():
            return {"processed": 0, "error": "Verbindung fehlgeschlagen"}

        try:
            processed = await connector.process_offline_queue()
            return {"processed": processed, "success": True}
        finally:
            await connector.disconnect()

    try:
        return asyncio.get_event_loop().run_until_complete(_process())
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(_process())
        finally:
            loop.close()


# =============================================================================
# Webhook-triggered Tasks
# =============================================================================


@shared_task(
    name="lexware_sync.handle_webhook",
    bind=True,
    max_retries=3,
    default_retry_delay=30,
    queue="webhooks",
)
def handle_webhook_task(
    self,
    event_type: str,
    resource_type: str,
    resource_id: str,
    data: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Verarbeitet einen Lexware Webhook Event.

    Wird vom API Endpoint aufgerufen wenn Webhook empfangen wird.

    Args:
        event_type: Event-Typ (contact.created, invoice.paid, etc.)
        resource_type: Ressourcen-Typ
        resource_id: Ressourcen-ID
        data: Event-Daten

    Returns:
        Verarbeitungsergebnis
    """
    import asyncio

    async def _handle() -> Dict[str, Any]:
        connector = get_lexware_connector()
        if not connector:
            return {"success": False, "error": "Connector nicht konfiguriert"}

        if not await connector.connect():
            return {"success": False, "error": "Verbindung fehlgeschlagen"}

        try:
            # Create event object
            event = LexwareWebhookEvent(
                id=data.get("id", ""),
                event_type=event_type,
                resource_type=resource_type,
                resource_id=resource_id,
                organization_id=data.get("organization_id", ""),
                timestamp=utc_now(),
                data=data,
            )

            await connector.handle_webhook({
                "id": event.id,
                "event": event_type,
                "resource_type": resource_type,
                "resource_id": resource_id,
                "organization_id": event.organization_id,
                "timestamp": event.timestamp.isoformat(),
                "data": data,
            })

            # Trigger immediate sync for the affected entity
            if resource_type == "customer":
                await connector.get_customer(resource_id)
            elif resource_type == "vendor":
                await connector.get_supplier(resource_id)
            elif resource_type == "invoice":
                await connector.get_invoice(resource_id)

            logger.info(
                "lexware_webhook_processed",
                event_type=event_type,
                resource_type=resource_type,
                resource_id=resource_id,
            )

            return {"success": True, "event_type": event_type}

        finally:
            await connector.disconnect()

    try:
        return asyncio.get_event_loop().run_until_complete(_handle())
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(_handle())
        finally:
            loop.close()


# =============================================================================
# Single Entity Sync Tasks
# =============================================================================


@shared_task(
    name="lexware_sync.sync_single_customer",
    bind=True,
    max_retries=3,
    default_retry_delay=30,
    queue="erp",
)
def sync_single_customer_task(
    self,
    erp_id: str,
    company_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Synchronisiert einen einzelnen Kunden.

    Args:
        erp_id: Lexware Kunden-ID
        company_id: Optional Company UUID

    Returns:
        Kundendaten oder Fehler
    """
    import asyncio

    async def _sync() -> Dict[str, Any]:
        connector = get_lexware_connector()
        if not connector:
            return {"success": False, "error": "Connector nicht konfiguriert"}

        if not await connector.connect():
            return {"success": False, "error": "Verbindung fehlgeschlagen"}

        try:
            customer = await connector.get_customer(erp_id)
            if customer:
                logger.info(
                    "lexware_customer_synced",
                    erp_id=erp_id,
                )
                return {"success": True, "data": customer}
            else:
                return {"success": False, "error": "Kunde nicht gefunden"}
        finally:
            await connector.disconnect()

    try:
        return asyncio.get_event_loop().run_until_complete(_sync())
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(_sync())
        finally:
            loop.close()


@shared_task(
    name="lexware_sync.sync_single_supplier",
    bind=True,
    max_retries=3,
    default_retry_delay=30,
    queue="erp",
)
def sync_single_supplier_task(
    self,
    erp_id: str,
    company_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Synchronisiert einen einzelnen Lieferanten.

    Args:
        erp_id: Lexware Lieferanten-ID
        company_id: Optional Company UUID

    Returns:
        Lieferantendaten oder Fehler
    """
    import asyncio

    async def _sync() -> Dict[str, Any]:
        connector = get_lexware_connector()
        if not connector:
            return {"success": False, "error": "Connector nicht konfiguriert"}

        if not await connector.connect():
            return {"success": False, "error": "Verbindung fehlgeschlagen"}

        try:
            supplier = await connector.get_supplier(erp_id)
            if supplier:
                logger.info(
                    "lexware_supplier_synced",
                    erp_id=erp_id,
                )
                return {"success": True, "data": supplier}
            else:
                return {"success": False, "error": "Lieferant nicht gefunden"}
        finally:
            await connector.disconnect()

    try:
        return asyncio.get_event_loop().run_until_complete(_sync())
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(_sync())
        finally:
            loop.close()


@shared_task(
    name="lexware_sync.update_payment_status",
    bind=True,
    max_retries=3,
    default_retry_delay=30,
    queue="erp",
)
def update_payment_status_task(
    self,
    invoice_erp_id: str,
    status: str,
    payment_date: Optional[str] = None,
    amount: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Aktualisiert den Zahlungsstatus einer Rechnung in Lexware.

    Args:
        invoice_erp_id: Lexware Rechnungs-ID
        status: Neuer Status (paid, partial, unpaid)
        payment_date: Zahlungsdatum (ISO format)
        amount: Gezahlter Betrag

    Returns:
        Ergebnis
    """
    import asyncio
    from datetime import datetime

    async def _update() -> Dict[str, Any]:
        connector = get_lexware_connector()
        if not connector:
            return {"success": False, "error": "Connector nicht konfiguriert"}

        if not await connector.connect():
            return {"success": False, "error": "Verbindung fehlgeschlagen"}

        try:
            payment_dt = None
            if payment_date:
                try:
                    payment_dt = datetime.fromisoformat(
                        payment_date.replace("Z", "+00:00")
                    )
                except ValueError as e:
                    logger.debug("parse_payment_date", error_type=type(e).__name__)

            success = await connector.update_payment_status(
                erp_id=invoice_erp_id,
                status=status,
                payment_date=payment_dt,
                amount=amount,
            )

            if success:
                logger.info(
                    "lexware_payment_status_updated",
                    invoice_id=invoice_erp_id,
                    status=status,
                    amount=amount,
                )
                return {"success": True}
            else:
                return {"success": False, "error": "Update fehlgeschlagen"}

        finally:
            await connector.disconnect()

    try:
        return asyncio.get_event_loop().run_until_complete(_update())
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(_update())
        finally:
            loop.close()


# =============================================================================
# Push Local Changes to Lexware
# =============================================================================


@shared_task(
    name="lexware_sync.push_entity_to_lexware",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    queue="erp",
)
def push_entity_to_lexware_task(
    self,
    entity_type: str,
    operation: str,
    data: Dict[str, Any],
    erp_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Pusht eine lokale Entitaet zu Lexware.

    Args:
        entity_type: customer, supplier
        operation: create, update
        data: Entitaetsdaten
        erp_id: ERP-ID fuer update

    Returns:
        Ergebnis mit ERP-ID
    """
    import asyncio

    async def _push() -> Dict[str, Any]:
        connector = get_lexware_connector()
        if not connector:
            return {"success": False, "error": "Connector nicht konfiguriert"}

        if not await connector.connect():
            return {"success": False, "error": "Verbindung fehlgeschlagen"}

        try:
            if entity_type == "customer":
                if operation == "create":
                    new_id = await connector.create_customer(
                        connector._map_to_lexware_customer(data)
                    )
                    if new_id:
                        return {"success": True, "erp_id": new_id}
                elif operation == "update" and erp_id:
                    success = await connector.update_customer(
                        erp_id,
                        connector._map_to_lexware_customer(data),
                    )
                    if success:
                        return {"success": True, "erp_id": erp_id}

            elif entity_type == "supplier":
                if operation == "create":
                    new_id = await connector.create_supplier(
                        connector._map_to_lexware_supplier(data)
                    )
                    if new_id:
                        return {"success": True, "erp_id": new_id}
                elif operation == "update" and erp_id:
                    success = await connector.update_supplier(
                        erp_id,
                        connector._map_to_lexware_supplier(data),
                    )
                    if success:
                        return {"success": True, "erp_id": erp_id}

            return {"success": False, "error": "Operation fehlgeschlagen"}

        finally:
            await connector.disconnect()

    try:
        return asyncio.get_event_loop().run_until_complete(_push())
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(_push())
        finally:
            loop.close()


# =============================================================================
# Connection Health Check
# =============================================================================


@shared_task(
    name="lexware_sync.health_check",
    bind=True,
    max_retries=1,
    queue="erp",
)
def health_check_task(self) -> Dict[str, Any]:
    """
    Prueft die Verbindung zu Lexware.

    Returns:
        Verbindungsstatus
    """
    import asyncio

    async def _check() -> Dict[str, Any]:
        connector = get_lexware_connector()
        if not connector:
            return {
                "healthy": False,
                "error": "Connector nicht konfiguriert",
                "status": "unconfigured",
            }

        try:
            if await connector.connect():
                version = await connector.get_version()
                return {
                    "healthy": True,
                    "status": "connected",
                    "api_version": version,
                }
            else:
                return {
                    "healthy": False,
                    "status": "connection_failed",
                    "error": connector.last_error,
                }
        except Exception as e:
            return {
                "healthy": False,
                "status": "error",
                "error": safe_error_detail(e, "Vorgang"),
            }
        finally:
            if connector:
                await connector.disconnect()

    try:
        return asyncio.get_event_loop().run_until_complete(_check())
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(_check())
        finally:
            loop.close()
