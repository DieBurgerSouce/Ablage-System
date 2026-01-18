# -*- coding: utf-8 -*-
"""Carrier Service - Zentraler Service fuer Paketdienst-Integration.

Features:
- Automatische Carrier-Erkennung anhand Tracking-Nummer
- Einheitliche Tracking-Abfrage fuer alle Carrier
- Caching von Tracking-Daten
- Batch-Tracking fuer mehrere Sendungen
- Kosten-Analyse

Unterstuetzte Carrier:
- DHL (Marktfuehrer Deutschland)
- DPD (sehr verbreitet B2B)
- Hermes (B2C stark)
- UPS (International)
- GLS (B2B stark)
- FedEx (Express/International)
- Deutsche Post (Briefe/Einschreiben)
"""

from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple, TypedDict
from uuid import UUID
from enum import Enum

import structlog
from sqlalchemy import select, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models import Shipment, ShipmentEvent, BusinessEntity

from .carrier_providers import (
    BaseCarrierProvider,
    DHLProvider,
    DPDProvider,
    HermesProvider,
    UPSProvider,
    GLSProvider,
    FedExProvider,
    DeutschePostProvider,
    ShipmentStatus,
    TrackingResult,
    TrackingEvent,
)

logger = structlog.get_logger(__name__)


class Carrier(str, Enum):
    """Unterstuetzte Paketdienste."""
    DHL = "dhl"
    DPD = "dpd"
    HERMES = "hermes"
    UPS = "ups"
    GLS = "gls"
    FEDEX = "fedex"
    DEUTSCHE_POST = "deutsche_post"
    UNKNOWN = "unknown"


class ShipmentDirection(str, Enum):
    """Sendungsrichtung."""
    INBOUND = "inbound"    # Eingehend (Wareneingang)
    OUTBOUND = "outbound"  # Ausgehend (Versand an Kunden)
    RETURN = "return"      # Retoure


class ShipmentSummary(TypedDict):
    """Zusammenfassung aller Sendungen."""
    total: int
    by_carrier: Dict[str, int]
    by_status: Dict[str, int]
    pending_delivery: int
    delivered_today: int
    exceptions: int


class CarrierStatistics(TypedDict):
    """Statistiken pro Carrier."""
    carrier: str
    total_shipments: int
    delivered: int
    avg_delivery_days: float
    on_time_rate: float
    exception_rate: float


class CarrierService:
    """Enterprise-Grade Paketdienst-Integration.

    Verwendung:
        service = CarrierService()

        # Carrier erkennen
        carrier = service.detect_carrier("00340434173456789012")
        # -> Carrier.DHL

        # Tracking abfragen
        result = await service.track_shipment(db, "00340434173456789012")

        # Alle aktiven Sendungen updaten
        await service.refresh_all_active_shipments(db, company_id)

        # Statistiken
        stats = await service.get_carrier_statistics(db, company_id)
    """

    def __init__(self) -> None:
        """Initialisiert Service mit allen Carrier-Providern."""
        self._providers: Dict[Carrier, BaseCarrierProvider] = {
            Carrier.DHL: DHLProvider(),
            Carrier.DPD: DPDProvider(),
            Carrier.HERMES: HermesProvider(),
            Carrier.UPS: UPSProvider(),
            Carrier.GLS: GLSProvider(),
            Carrier.FEDEX: FedExProvider(),
            Carrier.DEUTSCHE_POST: DeutschePostProvider(),
        }

        # Reihenfolge fuer Carrier-Erkennung (haeufigste zuerst)
        self._detection_order = [
            Carrier.DHL,
            Carrier.DPD,
            Carrier.HERMES,
            Carrier.UPS,
            Carrier.GLS,
            Carrier.FEDEX,
            Carrier.DEUTSCHE_POST,
        ]

        logger.info("carrier_service_initialized", carriers=list(self._providers.keys()))

    async def close(self) -> None:
        """Schliesst alle HTTP Clients."""
        for provider in self._providers.values():
            await provider.close()

    # ==================== Carrier Detection ====================

    def detect_carrier(self, tracking_number: str) -> Carrier:
        """Erkennt Carrier anhand der Tracking-Nummer.

        Args:
            tracking_number: Die Sendungsnummer

        Returns:
            Erkannter Carrier oder Carrier.UNKNOWN
        """
        normalized = tracking_number.replace(" ", "").replace("-", "").upper()

        for carrier in self._detection_order:
            provider = self._providers.get(carrier)
            if provider and provider.matches_tracking_number(normalized):
                logger.debug(
                    "carrier_detected",
                    tracking_number=normalized[:8] + "...",  # Nur Anfang loggen
                    carrier=carrier.value
                )
                return carrier

        logger.warning(
            "carrier_not_detected",
            tracking_number=normalized[:8] + "..."
        )
        return Carrier.UNKNOWN

    def get_tracking_url(self, tracking_number: str, carrier: Optional[Carrier] = None) -> Optional[str]:
        """Gibt die oeffentliche Tracking-URL zurueck.

        Args:
            tracking_number: Die Sendungsnummer
            carrier: Optional Carrier (sonst automatisch erkennen)

        Returns:
            Tracking URL oder None
        """
        if carrier is None:
            carrier = self.detect_carrier(tracking_number)

        if carrier == Carrier.UNKNOWN:
            return None

        provider = self._providers.get(carrier)
        if provider:
            return provider.get_tracking_url(tracking_number)

        return None

    # ==================== Tracking ====================

    async def track_shipment(
        self,
        db: AsyncSession,
        tracking_number: str,
        carrier: Optional[Carrier] = None,
        company_id: Optional[UUID] = None,
        save_to_db: bool = True,
    ) -> TrackingResult:
        """Fragt Tracking-Informationen ab und speichert sie.

        Args:
            db: Datenbank-Session
            tracking_number: Die Sendungsnummer
            carrier: Optional Carrier (sonst automatisch erkennen)
            company_id: Company ID fuer Multi-Tenant
            save_to_db: Ob Ergebnis in DB gespeichert werden soll

        Returns:
            TrackingResult mit allen Informationen
        """
        if carrier is None:
            carrier = self.detect_carrier(tracking_number)

        if carrier == Carrier.UNKNOWN:
            logger.warning("tracking_unknown_carrier", tracking_number=tracking_number[:8])
            return self._create_unknown_result(tracking_number)

        provider = self._providers.get(carrier)
        if not provider:
            return self._create_unknown_result(tracking_number)

        try:
            result = await provider.track_shipment(tracking_number)

            if save_to_db and company_id:
                await self._save_tracking_result(db, result, company_id)

            return result

        except Exception as e:
            logger.error(
                "tracking_failed",
                carrier=carrier.value,
                error=str(e)
            )
            raise

    async def track_multiple(
        self,
        db: AsyncSession,
        tracking_numbers: List[str],
        company_id: UUID,
    ) -> Dict[str, TrackingResult]:
        """Fragt Tracking fuer mehrere Sendungen ab.

        Args:
            db: Datenbank-Session
            tracking_numbers: Liste von Sendungsnummern
            company_id: Company ID

        Returns:
            Dict von Tracking-Nummer zu TrackingResult
        """
        results: Dict[str, TrackingResult] = {}

        for tracking_number in tracking_numbers:
            try:
                result = await self.track_shipment(
                    db, tracking_number, company_id=company_id
                )
                results[tracking_number] = result
            except Exception as e:
                logger.error(
                    "batch_tracking_error",
                    tracking_number=tracking_number[:8],
                    error=str(e)
                )
                results[tracking_number] = self._create_unknown_result(tracking_number)

        return results

    async def refresh_all_active_shipments(
        self,
        db: AsyncSession,
        company_id: UUID,
    ) -> Tuple[int, int]:
        """Aktualisiert alle aktiven Sendungen.

        Args:
            db: Datenbank-Session
            company_id: Company ID

        Returns:
            Tuple (aktualisiert, fehlgeschlagen)
        """
        # Hole alle nicht-zugestellten Sendungen
        query = select(Shipment).where(
            and_(
                Shipment.company_id == company_id,
                Shipment.status.notin_([
                    ShipmentStatus.DELIVERED.value,
                    ShipmentStatus.RETURNED.value,
                ]),
                Shipment.deleted_at.is_(None),
            )
        )

        result = await db.execute(query)
        shipments = result.scalars().all()

        updated = 0
        failed = 0

        for shipment in shipments:
            try:
                await self.track_shipment(
                    db,
                    shipment.tracking_number,
                    Carrier(shipment.carrier),
                    company_id,
                    save_to_db=True,
                )
                updated += 1
            except Exception as e:
                logger.error(
                    "shipment_refresh_failed",
                    shipment_id=str(shipment.id),
                    error=str(e)
                )
                failed += 1

        logger.info(
            "shipments_refreshed",
            company_id=str(company_id),
            updated=updated,
            failed=failed
        )

        return updated, failed

    # ==================== CRUD Operations ====================

    async def create_shipment(
        self,
        db: AsyncSession,
        company_id: UUID,
        tracking_number: str,
        direction: ShipmentDirection,
        carrier: Optional[Carrier] = None,
        entity_id: Optional[UUID] = None,
        document_id: Optional[UUID] = None,
        reference: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> Shipment:
        """Erstellt eine neue Sendung.

        Args:
            db: Datenbank-Session
            company_id: Company ID
            tracking_number: Sendungsnummer
            direction: Eingehend/Ausgehend/Retoure
            carrier: Optional Carrier (sonst automatisch)
            entity_id: Verknuepfte Entitaet (Kunde/Lieferant)
            document_id: Verknuepftes Dokument (Lieferschein)
            reference: Referenz (Bestellnummer, etc.)
            notes: Notizen

        Returns:
            Erstellte Shipment
        """
        if carrier is None:
            carrier = self.detect_carrier(tracking_number)

        shipment = Shipment(
            company_id=company_id,
            tracking_number=tracking_number,
            carrier=carrier.value,
            direction=direction.value,
            status=ShipmentStatus.LABEL_CREATED.value,
            entity_id=entity_id,
            document_id=document_id,
            reference=reference,
            notes=notes,
            tracking_url=self.get_tracking_url(tracking_number, carrier),
        )

        db.add(shipment)
        await db.commit()
        await db.refresh(shipment)

        logger.info(
            "shipment_created",
            shipment_id=str(shipment.id),
            carrier=carrier.value,
            direction=direction.value
        )

        # Initial Tracking abrufen
        try:
            await self.track_shipment(
                db, tracking_number, carrier, company_id, save_to_db=True
            )
        except Exception as e:
            logger.warning("initial_tracking_failed", error=str(e))

        return shipment

    async def get_shipment(
        self,
        db: AsyncSession,
        company_id: UUID,
        shipment_id: UUID,
    ) -> Optional[Shipment]:
        """Holt eine Sendung.

        Args:
            db: Datenbank-Session
            company_id: Company ID
            shipment_id: Sendungs-ID

        Returns:
            Shipment oder None
        """
        query = select(Shipment).where(
            and_(
                Shipment.id == shipment_id,
                Shipment.company_id == company_id,
                Shipment.deleted_at.is_(None),
            )
        )

        result = await db.execute(query)
        return result.scalar_one_or_none()

    async def get_shipment_by_tracking(
        self,
        db: AsyncSession,
        company_id: UUID,
        tracking_number: str,
    ) -> Optional[Shipment]:
        """Holt eine Sendung anhand Tracking-Nummer.

        Args:
            db: Datenbank-Session
            company_id: Company ID
            tracking_number: Sendungsnummer

        Returns:
            Shipment oder None
        """
        query = select(Shipment).where(
            and_(
                Shipment.tracking_number == tracking_number,
                Shipment.company_id == company_id,
                Shipment.deleted_at.is_(None),
            )
        )

        result = await db.execute(query)
        return result.scalar_one_or_none()

    async def list_shipments(
        self,
        db: AsyncSession,
        company_id: UUID,
        direction: Optional[ShipmentDirection] = None,
        status: Optional[ShipmentStatus] = None,
        carrier: Optional[Carrier] = None,
        entity_id: Optional[UUID] = None,
        page: int = 1,
        per_page: int = 20,
    ) -> Tuple[List[Shipment], int]:
        """Listet Sendungen mit Filtern.

        Args:
            db: Datenbank-Session
            company_id: Company ID
            direction: Filter nach Richtung
            status: Filter nach Status
            carrier: Filter nach Carrier
            entity_id: Filter nach Entitaet
            page: Seite (1-basiert)
            per_page: Eintraege pro Seite

        Returns:
            Tuple (Sendungen, Gesamt-Anzahl)
        """
        conditions = [
            Shipment.company_id == company_id,
            Shipment.deleted_at.is_(None),
        ]

        if direction:
            conditions.append(Shipment.direction == direction.value)
        if status:
            conditions.append(Shipment.status == status.value)
        if carrier:
            conditions.append(Shipment.carrier == carrier.value)
        if entity_id:
            conditions.append(Shipment.entity_id == entity_id)

        # Count Query
        count_query = select(func.count(Shipment.id)).where(and_(*conditions))
        total = (await db.execute(count_query)).scalar() or 0

        # Data Query
        query = (
            select(Shipment)
            .where(and_(*conditions))
            .order_by(Shipment.created_at.desc())
            .offset((page - 1) * per_page)
            .limit(per_page)
        )

        result = await db.execute(query)
        shipments = list(result.scalars().all())

        return shipments, total

    async def delete_shipment(
        self,
        db: AsyncSession,
        company_id: UUID,
        shipment_id: UUID,
    ) -> bool:
        """Loescht eine Sendung (soft delete).

        Args:
            db: Datenbank-Session
            company_id: Company ID
            shipment_id: Sendungs-ID

        Returns:
            True wenn geloescht
        """
        shipment = await self.get_shipment(db, company_id, shipment_id)
        if not shipment:
            return False

        shipment.deleted_at = datetime.now(timezone.utc)
        await db.commit()

        logger.info("shipment_deleted", shipment_id=str(shipment_id))
        return True

    # ==================== Statistics ====================

    async def get_shipment_summary(
        self,
        db: AsyncSession,
        company_id: UUID,
    ) -> ShipmentSummary:
        """Gibt eine Zusammenfassung aller Sendungen.

        Args:
            db: Datenbank-Session
            company_id: Company ID

        Returns:
            ShipmentSummary
        """
        base_condition = and_(
            Shipment.company_id == company_id,
            Shipment.deleted_at.is_(None),
        )

        # Total
        total_query = select(func.count(Shipment.id)).where(base_condition)
        total = (await db.execute(total_query)).scalar() or 0

        # By Carrier
        carrier_query = (
            select(Shipment.carrier, func.count(Shipment.id))
            .where(base_condition)
            .group_by(Shipment.carrier)
        )
        carrier_result = await db.execute(carrier_query)
        by_carrier = {row[0]: row[1] for row in carrier_result.all()}

        # By Status
        status_query = (
            select(Shipment.status, func.count(Shipment.id))
            .where(base_condition)
            .group_by(Shipment.status)
        )
        status_result = await db.execute(status_query)
        by_status = {row[0]: row[1] for row in status_result.all()}

        # Pending Delivery
        pending_query = select(func.count(Shipment.id)).where(
            and_(
                base_condition,
                Shipment.status.in_([
                    ShipmentStatus.IN_TRANSIT.value,
                    ShipmentStatus.OUT_FOR_DELIVERY.value,
                ])
            )
        )
        pending_delivery = (await db.execute(pending_query)).scalar() or 0

        # Delivered Today
        today = datetime.now(timezone.utc).date()
        delivered_today_query = select(func.count(Shipment.id)).where(
            and_(
                base_condition,
                Shipment.status == ShipmentStatus.DELIVERED.value,
                func.date(Shipment.actual_delivery) == today,
            )
        )
        delivered_today = (await db.execute(delivered_today_query)).scalar() or 0

        # Exceptions
        exceptions_query = select(func.count(Shipment.id)).where(
            and_(
                base_condition,
                Shipment.status == ShipmentStatus.EXCEPTION.value,
            )
        )
        exceptions = (await db.execute(exceptions_query)).scalar() or 0

        return {
            "total": total,
            "by_carrier": by_carrier,
            "by_status": by_status,
            "pending_delivery": pending_delivery,
            "delivered_today": delivered_today,
            "exceptions": exceptions,
        }

    async def get_carrier_statistics(
        self,
        db: AsyncSession,
        company_id: UUID,
        days: int = 90,
    ) -> List[CarrierStatistics]:
        """Berechnet Statistiken pro Carrier.

        Args:
            db: Datenbank-Session
            company_id: Company ID
            days: Zeitraum in Tagen

        Returns:
            Liste von CarrierStatistics
        """
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)

        base_condition = and_(
            Shipment.company_id == company_id,
            Shipment.deleted_at.is_(None),
            Shipment.created_at >= cutoff,
        )

        stats: List[CarrierStatistics] = []

        for carrier in Carrier:
            if carrier == Carrier.UNKNOWN:
                continue

            carrier_condition = and_(
                base_condition,
                Shipment.carrier == carrier.value,
            )

            # Total
            total = (await db.execute(
                select(func.count(Shipment.id)).where(carrier_condition)
            )).scalar() or 0

            if total == 0:
                continue

            # Delivered
            delivered = (await db.execute(
                select(func.count(Shipment.id)).where(
                    and_(
                        carrier_condition,
                        Shipment.status == ShipmentStatus.DELIVERED.value,
                    )
                )
            )).scalar() or 0

            # Avg Delivery Days (nur fuer zugestellte)
            avg_days_query = select(
                func.avg(
                    func.extract('epoch', Shipment.actual_delivery - Shipment.created_at) / 86400
                )
            ).where(
                and_(
                    carrier_condition,
                    Shipment.status == ShipmentStatus.DELIVERED.value,
                    Shipment.actual_delivery.isnot(None),
                )
            )
            avg_days = (await db.execute(avg_days_query)).scalar() or 0.0

            # Exceptions
            exceptions = (await db.execute(
                select(func.count(Shipment.id)).where(
                    and_(
                        carrier_condition,
                        Shipment.status == ShipmentStatus.EXCEPTION.value,
                    )
                )
            )).scalar() or 0

            # On-time Rate (geschaetzt anhand avg_days < 3)
            on_time = (await db.execute(
                select(func.count(Shipment.id)).where(
                    and_(
                        carrier_condition,
                        Shipment.status == ShipmentStatus.DELIVERED.value,
                        func.extract('epoch', Shipment.actual_delivery - Shipment.created_at) / 86400 <= 3,
                    )
                )
            )).scalar() or 0

            stats.append({
                "carrier": carrier.value,
                "total_shipments": total,
                "delivered": delivered,
                "avg_delivery_days": round(float(avg_days), 1),
                "on_time_rate": round(on_time / delivered * 100, 1) if delivered > 0 else 0.0,
                "exception_rate": round(exceptions / total * 100, 1) if total > 0 else 0.0,
            })

        # Sortieren nach Anzahl
        stats.sort(key=lambda x: x["total_shipments"], reverse=True)

        return stats

    # ==================== Private Methods ====================

    async def _save_tracking_result(
        self,
        db: AsyncSession,
        result: TrackingResult,
        company_id: UUID,
    ) -> None:
        """Speichert Tracking-Ergebnis in DB."""
        # Hole oder erstelle Shipment
        shipment = await self.get_shipment_by_tracking(
            db, company_id, result["tracking_number"]
        )

        if shipment:
            # Update existierende Sendung
            shipment.status = result["current_status"].value
            shipment.status_description = result["status_description"]
            shipment.estimated_delivery = result["estimated_delivery"]
            shipment.actual_delivery = result["actual_delivery"]
            shipment.origin = result["origin"]
            shipment.destination = result["destination"]
            shipment.weight_kg = result["weight_kg"]
            shipment.service_type = result["service_type"]
            shipment.last_tracking_update = datetime.now(timezone.utc)
            shipment.raw_tracking_data = result["raw_response"]

            # Events speichern (nur neue)
            existing_timestamps = {e.timestamp for e in shipment.events}

            for event in result["events"]:
                if event["timestamp"] and event["timestamp"] not in existing_timestamps:
                    shipment_event = ShipmentEvent(
                        shipment_id=shipment.id,
                        timestamp=event["timestamp"],
                        status=event["status"].value,
                        description=event["description"],
                        location=event["location"],
                        postal_code=event["postal_code"],
                        country_code=event["country_code"],
                        raw_status=event["raw_status"],
                    )
                    db.add(shipment_event)

            await db.commit()

    def _create_unknown_result(self, tracking_number: str) -> TrackingResult:
        """Erstellt Ergebnis fuer unbekannten Carrier."""
        return {
            "tracking_number": tracking_number,
            "carrier": "unknown",
            "current_status": ShipmentStatus.UNKNOWN,
            "status_description": "Carrier konnte nicht erkannt werden",
            "estimated_delivery": None,
            "actual_delivery": None,
            "origin": None,
            "destination": None,
            "weight_kg": None,
            "service_type": None,
            "events": [],
            "raw_response": {},
            "last_updated": datetime.now(timezone.utc),
        }


# Re-export fuer convenience
__all__ = [
    "CarrierService",
    "Carrier",
    "ShipmentDirection",
    "ShipmentStatus",
    "TrackingResult",
    "TrackingEvent",
    "ShipmentSummary",
    "CarrierStatistics",
]
