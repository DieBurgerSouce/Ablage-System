# -*- coding: utf-8 -*-
"""Celery Tasks fuer Sendungsverfolgung.

Automatische Tracking-Updates:
- Stuendlich: Aktive Sendungen aktualisieren
- Bei Aenderung: Benachrichtigung senden
- Taeglich: Statistik-Generierung

Carrier:
- DHL, DPD, Hermes, UPS, GLS, FedEx, Deutsche Post
"""

import asyncio
from datetime import datetime, timezone, timedelta
from typing import List, Optional
from uuid import UUID

import structlog
from celery import shared_task
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import async_session_factory
from app.db.models import Shipment, Company, ShipmentStatusEnum
from app.services.shipping import CarrierService, Carrier, ShipmentStatus
from app.services.notification_service import NotificationService, NotificationType

logger = structlog.get_logger(__name__)


def run_async(coro):
    """Helper um async Code in Celery auszufuehren."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@shared_task(
    name="shipment_tracking.refresh_active",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    queue="tracking",
)
def refresh_active_shipments(self, company_id: Optional[str] = None) -> dict:
    """Aktualisiert alle aktiven Sendungen.

    Wird stuendlich ausgefuehrt (via Celery Beat).

    Args:
        company_id: Optional Company ID. Wenn None, alle Companies.

    Returns:
        Dict mit Statistiken
    """
    return run_async(_refresh_active_shipments(company_id))


async def _refresh_active_shipments(company_id_str: Optional[str] = None) -> dict:
    """Async Implementation fuer refresh_active_shipments."""
    service = CarrierService()
    total_updated = 0
    total_failed = 0
    status_changes = 0

    try:
        async with async_session_factory() as db:
            # Hole Companies
            if company_id_str:
                company_ids = [UUID(company_id_str)]
            else:
                result = await db.execute(
                    select(Company.id).where(Company.is_active == True)
                )
                company_ids = [row[0] for row in result.all()]

            for company_id in company_ids:
                try:
                    # Hole aktive Sendungen (nicht zugestellt/zurueck)
                    query = select(Shipment).where(
                        and_(
                            Shipment.company_id == company_id,
                            Shipment.status.notin_([
                                ShipmentStatusEnum.DELIVERED.value,
                                ShipmentStatusEnum.RETURNED.value,
                            ]),
                            Shipment.deleted_at.is_(None),
                        )
                    )

                    result = await db.execute(query)
                    shipments = result.scalars().all()

                    for shipment in shipments:
                        old_status = shipment.status

                        try:
                            # Tracking abfragen
                            tracking_result = await service.track_shipment(
                                db=db,
                                tracking_number=shipment.tracking_number,
                                carrier=Carrier(shipment.carrier),
                                company_id=company_id,
                                save_to_db=True,
                            )

                            # Pruefen ob Status sich geaendert hat
                            new_status = tracking_result["current_status"].value
                            if old_status != new_status:
                                status_changes += 1

                                # Benachrichtigung bei wichtigen Status-Aenderungen
                                await _notify_status_change(
                                    db, shipment, old_status, new_status
                                )

                            total_updated += 1

                        except Exception as e:
                            logger.warning(
                                "shipment_update_failed",
                                shipment_id=str(shipment.id),
                                error=str(e)
                            )
                            total_failed += 1

                except Exception as e:
                    logger.error(
                        "company_shipment_refresh_failed",
                        company_id=str(company_id),
                        error=str(e)
                    )

        logger.info(
            "active_shipments_refreshed",
            updated=total_updated,
            failed=total_failed,
            status_changes=status_changes
        )

    finally:
        await service.close()

    return {
        "updated": total_updated,
        "failed": total_failed,
        "status_changes": status_changes,
    }


@shared_task(
    name="shipment_tracking.refresh_single",
    bind=True,
    max_retries=3,
    default_retry_delay=30,
    queue="tracking",
)
def refresh_single_shipment(
    self,
    shipment_id: str,
    company_id: str,
) -> dict:
    """Aktualisiert eine einzelne Sendung.

    Wird on-demand oder nach Erstellung aufgerufen.

    Args:
        shipment_id: Sendungs-ID
        company_id: Company ID

    Returns:
        Dict mit Status
    """
    return run_async(_refresh_single_shipment(shipment_id, company_id))


async def _refresh_single_shipment(shipment_id: str, company_id: str) -> dict:
    """Async Implementation fuer refresh_single_shipment."""
    service = CarrierService()

    try:
        async with async_session_factory() as db:
            shipment = await db.get(Shipment, UUID(shipment_id))

            if not shipment or str(shipment.company_id) != company_id:
                return {"success": False, "error": "Sendung nicht gefunden"}

            if shipment.deleted_at:
                return {"success": False, "error": "Sendung geloescht"}

            old_status = shipment.status

            try:
                tracking_result = await service.track_shipment(
                    db=db,
                    tracking_number=shipment.tracking_number,
                    carrier=Carrier(shipment.carrier),
                    company_id=UUID(company_id),
                    save_to_db=True,
                )

                new_status = tracking_result["current_status"].value
                status_changed = old_status != new_status

                if status_changed:
                    await _notify_status_change(db, shipment, old_status, new_status)

                return {
                    "success": True,
                    "status": new_status,
                    "status_changed": status_changed,
                }

            except Exception as e:
                logger.error(
                    "single_shipment_refresh_failed",
                    shipment_id=shipment_id,
                    error=str(e)
                )
                return {"success": False, "error": str(e)}

    finally:
        await service.close()


@shared_task(
    name="shipment_tracking.check_delayed",
    bind=True,
    queue="maintenance",
)
def check_delayed_shipments(self) -> dict:
    """Prueft auf verspaetete Sendungen.

    Wird taeglich ausgefuehrt (via Celery Beat).
    Benachrichtigt bei:
    - Sendungen die laenger als 5 Tage unterwegs sind
    - Sendungen mit Exception-Status

    Returns:
        Dict mit Statistiken
    """
    return run_async(_check_delayed_shipments())


async def _check_delayed_shipments() -> dict:
    """Async Implementation fuer check_delayed_shipments."""
    delayed_count = 0
    exception_count = 0
    notifications_sent = 0

    async with async_session_factory() as db:
        # Hole Companies
        result = await db.execute(
            select(Company.id).where(Company.is_active == True)
        )
        company_ids = [row[0] for row in result.all()]

        for company_id in company_ids:
            # Verspaetete Sendungen (>5 Tage in Transit)
            cutoff = datetime.now(timezone.utc) - timedelta(days=5)
            delayed_query = select(Shipment).where(
                and_(
                    Shipment.company_id == company_id,
                    Shipment.status == ShipmentStatusEnum.IN_TRANSIT.value,
                    Shipment.created_at < cutoff,
                    Shipment.deleted_at.is_(None),
                )
            )

            delayed_result = await db.execute(delayed_query)
            delayed_shipments = delayed_result.scalars().all()
            delayed_count += len(delayed_shipments)

            for shipment in delayed_shipments:
                await _send_delay_notification(db, shipment)
                notifications_sent += 1

            # Exception Sendungen
            exception_query = select(Shipment).where(
                and_(
                    Shipment.company_id == company_id,
                    Shipment.status == ShipmentStatusEnum.EXCEPTION.value,
                    Shipment.deleted_at.is_(None),
                )
            )

            exception_result = await db.execute(exception_query)
            exception_shipments = exception_result.scalars().all()
            exception_count += len(exception_shipments)

    logger.info(
        "delayed_shipments_checked",
        delayed=delayed_count,
        exceptions=exception_count,
        notifications=notifications_sent
    )

    return {
        "delayed_shipments": delayed_count,
        "exception_shipments": exception_count,
        "notifications_sent": notifications_sent,
    }


@shared_task(
    name="shipment_tracking.generate_statistics",
    bind=True,
    queue="maintenance",
)
def generate_shipment_statistics(self, company_id: str) -> dict:
    """Generiert Sendungsstatistiken fuer eine Company.

    Wird woechentlich ausgefuehrt (via Celery Beat).

    Args:
        company_id: Company ID

    Returns:
        Dict mit Statistiken
    """
    return run_async(_generate_statistics(company_id))


async def _generate_statistics(company_id_str: str) -> dict:
    """Async Implementation fuer generate_shipment_statistics."""
    company_id = UUID(company_id_str)
    service = CarrierService()

    try:
        async with async_session_factory() as db:
            summary = await service.get_shipment_summary(db, company_id)
            carrier_stats = await service.get_carrier_statistics(db, company_id, days=30)

            logger.info(
                "shipment_statistics_generated",
                company_id=company_id_str,
                total=summary["total"]
            )

            return {
                "summary": summary,
                "carrier_statistics": carrier_stats,
            }

    finally:
        await service.close()


# ==================== Helper Functions ====================


async def _notify_status_change(
    db: AsyncSession,
    shipment: Shipment,
    old_status: str,
    new_status: str,
) -> None:
    """Sendet Benachrichtigung bei Status-Aenderung."""
    # Wichtige Status-Aenderungen
    important_transitions = [
        (ShipmentStatusEnum.IN_TRANSIT.value, ShipmentStatusEnum.OUT_FOR_DELIVERY.value),
        (None, ShipmentStatusEnum.DELIVERED.value),  # Any -> Delivered
        (None, ShipmentStatusEnum.EXCEPTION.value),  # Any -> Exception
        (None, ShipmentStatusEnum.RETURNED.value),   # Any -> Returned
    ]

    should_notify = False
    for from_status, to_status in important_transitions:
        if to_status == new_status:
            if from_status is None or from_status == old_status:
                should_notify = True
                break

    if not should_notify:
        return

    try:
        notification_service = NotificationService()

        # Notification-Typ basierend auf neuem Status
        if new_status == ShipmentStatusEnum.DELIVERED.value:
            notification_type = "SHIPMENT_DELIVERED"
            title = "Sendung zugestellt"
            message = f"Sendung {shipment.tracking_number} ({shipment.carrier.upper()}) wurde zugestellt."
        elif new_status == ShipmentStatusEnum.OUT_FOR_DELIVERY.value:
            notification_type = "SHIPMENT_OUT_FOR_DELIVERY"
            title = "Sendung in Zustellung"
            message = f"Sendung {shipment.tracking_number} ({shipment.carrier.upper()}) ist heute in Zustellung."
        elif new_status == ShipmentStatusEnum.EXCEPTION.value:
            notification_type = "SHIPMENT_EXCEPTION"
            title = "Sendungsproblem"
            message = f"Bei Sendung {shipment.tracking_number} ({shipment.carrier.upper()}) ist ein Problem aufgetreten."
        elif new_status == ShipmentStatusEnum.RETURNED.value:
            notification_type = "SHIPMENT_RETURNED"
            title = "Sendung zurueckgeschickt"
            message = f"Sendung {shipment.tracking_number} ({shipment.carrier.upper()}) wurde zurueckgeschickt."
        else:
            return

        # In-App Notification erstellen
        await notification_service.create_notification(
            db=db,
            company_id=shipment.company_id,
            notification_type=notification_type,
            title=title,
            message=message,
            reference_type="shipment",
            reference_id=shipment.id,
            data={
                "tracking_number": shipment.tracking_number,
                "carrier": shipment.carrier,
                "old_status": old_status,
                "new_status": new_status,
                "tracking_url": shipment.tracking_url,
            },
        )

        logger.info(
            "shipment_notification_sent",
            shipment_id=str(shipment.id),
            notification_type=notification_type
        )

    except Exception as e:
        logger.warning(
            "shipment_notification_failed",
            shipment_id=str(shipment.id),
            error=str(e)
        )


async def _send_delay_notification(
    db: AsyncSession,
    shipment: Shipment,
) -> None:
    """Sendet Benachrichtigung bei verspaeteter Sendung."""
    try:
        notification_service = NotificationService()

        days_in_transit = (datetime.now(timezone.utc) - shipment.created_at).days

        await notification_service.create_notification(
            db=db,
            company_id=shipment.company_id,
            notification_type="SHIPMENT_DELAYED",
            title="Verspaetete Sendung",
            message=f"Sendung {shipment.tracking_number} ({shipment.carrier.upper()}) ist seit {days_in_transit} Tagen unterwegs.",
            reference_type="shipment",
            reference_id=shipment.id,
            data={
                "tracking_number": shipment.tracking_number,
                "carrier": shipment.carrier,
                "days_in_transit": days_in_transit,
                "tracking_url": shipment.tracking_url,
            },
        )

    except Exception as e:
        logger.warning(
            "delay_notification_failed",
            shipment_id=str(shipment.id),
            error=str(e)
        )
