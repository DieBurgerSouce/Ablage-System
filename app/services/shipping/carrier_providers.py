# -*- coding: utf-8 -*-
"""Carrier Provider Implementations.

Jeder Provider implementiert die API-Anbindung fuer einen Paketdienst.
Die APIs sind entweder REST oder SOAP-basiert.

SECURITY:
- API-Keys werden aus Umgebungsvariablen geladen
- Keine Credentials in Logs
- Rate Limiting beachten
- Tracking-Nummern werden validiert und URL-encoded (CWE-20, CWE-116)
"""

import re
import hashlib
import hmac
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, TypedDict
from enum import Enum
from urllib.parse import quote

import httpx
import structlog

from app.core.config import settings
from app.core.safe_errors import safe_error_log

logger = structlog.get_logger(__name__)


# =============================================================================
# SECURITY: Tracking Number Validation (CWE-20 Improper Input Validation)
# =============================================================================

# Whitelist Pattern: Nur alphanumerische Zeichen erlaubt
TRACKING_NUMBER_PATTERN = re.compile(r"^[A-Za-z0-9]{6,30}$")


def validate_tracking_number(tracking_number: str) -> str:
    """Validiert und sanitiert Tracking-Nummer.

    SECURITY: Verhindert Injection-Angriffe durch:
    1. Whitespace-Normalisierung
    2. Whitelist-Validierung (nur alphanumerisch)
    3. Laengen-Pruefung (6-30 Zeichen)

    Args:
        tracking_number: Rohe Tracking-Nummer

    Returns:
        Normalisierte, sichere Tracking-Nummer

    Raises:
        ValueError: Bei ungueltiger Tracking-Nummer
    """
    if not tracking_number:
        raise ValueError("Tracking-Nummer darf nicht leer sein")

    # Normalisieren: Whitespace entfernen, Uppercase
    normalized = tracking_number.strip().replace(" ", "").replace("-", "").upper()

    # Whitelist-Validierung
    if not TRACKING_NUMBER_PATTERN.match(normalized):
        logger.warning(
            "tracking_number_validation_failed",
            reason="Invalid characters or length",
            # SECURITY: Keine PII loggen, nur Laenge
            length=len(tracking_number),
        )
        raise ValueError("Ungueltige Tracking-Nummer: Nur Buchstaben und Ziffern erlaubt (6-30 Zeichen)")

    return normalized


def safe_url_encode(value: str) -> str:
    """URL-encodiert Wert sicher.

    SECURITY: Verhindert URL-Injection (CWE-116).

    Args:
        value: Zu encodierender Wert

    Returns:
        URL-sicher encodierter Wert
    """
    return quote(value, safe="")


class ShipmentStatus(str, Enum):
    """Standardisierte Sendungsstatus (carrier-uebergreifend)."""
    UNKNOWN = "unknown"
    LABEL_CREATED = "label_created"          # Label erstellt, noch nicht abgeholt
    PICKED_UP = "picked_up"                  # Vom Carrier abgeholt
    IN_TRANSIT = "in_transit"                # Unterwegs
    OUT_FOR_DELIVERY = "out_for_delivery"    # In Zustellung
    DELIVERED = "delivered"                  # Zugestellt
    DELIVERY_ATTEMPT = "delivery_attempt"    # Zustellversuch (nicht angetroffen)
    HELD_AT_LOCATION = "held_at_location"    # Liegt zur Abholung bereit
    RETURNED = "returned"                    # Zurueck an Absender
    EXCEPTION = "exception"                  # Problem/Ausnahme
    CUSTOMS = "customs"                      # Im Zoll


class TrackingEvent(TypedDict):
    """Ein einzelnes Tracking-Event."""
    timestamp: datetime
    status: ShipmentStatus
    description: str
    location: Optional[str]
    postal_code: Optional[str]
    country_code: Optional[str]
    raw_status: str  # Original-Status vom Carrier


class TrackingResult(TypedDict):
    """Ergebnis einer Tracking-Abfrage."""
    tracking_number: str
    carrier: str
    current_status: ShipmentStatus
    status_description: str
    estimated_delivery: Optional[datetime]
    actual_delivery: Optional[datetime]
    origin: Optional[str]
    destination: Optional[str]
    weight_kg: Optional[float]
    service_type: Optional[str]
    events: List[TrackingEvent]
    raw_response: Dict[str, Any]  # Original API Response
    last_updated: datetime


class BaseCarrierProvider(ABC):
    """Basisklasse fuer alle Carrier Provider."""

    carrier_name: str = "unknown"
    tracking_url_template: str = ""

    # Tracking-Nummer Patterns (Regex)
    tracking_patterns: List[str] = []

    def __init__(self) -> None:
        """Initialisiert den Provider."""
        self.client = httpx.AsyncClient(timeout=30.0)

    async def close(self) -> None:
        """Schliesst HTTP Client."""
        await self.client.aclose()

    def matches_tracking_number(self, tracking_number: str) -> bool:
        """Prueft ob die Tracking-Nummer zu diesem Carrier passt.

        SECURITY: Verwendet validierte Tracking-Nummer.
        """
        try:
            normalized = validate_tracking_number(tracking_number)
        except ValueError:
            return False

        for pattern in self.tracking_patterns:
            if re.match(pattern, normalized):
                return True
        return False

    def get_tracking_url(self, tracking_number: str) -> str:
        """Gibt die oeffentliche Tracking-URL zurueck.

        SECURITY: URL-encodiert die Tracking-Nummer (CWE-116).
        """
        validated = validate_tracking_number(tracking_number)
        encoded = safe_url_encode(validated)
        return self.tracking_url_template.format(tracking_number=encoded)

    @abstractmethod
    async def track_shipment(self, tracking_number: str) -> TrackingResult:
        """Fragt Tracking-Informationen ab.

        SECURITY: Implementierungen MUESSEN validate_tracking_number() aufrufen!
        """
        pass

    def _normalize_status(self, raw_status: str) -> ShipmentStatus:
        """Mappt carrier-spezifische Status auf Standard-Status."""
        # Subklassen ueberschreiben dies mit carrier-spezifischem Mapping
        return ShipmentStatus.UNKNOWN

    def _parse_datetime(self, date_str: str, format_str: str = "%Y-%m-%dT%H:%M:%S") -> Optional[datetime]:
        """Parst Datum/Zeit-String sicher."""
        if not date_str:
            return None
        try:
            dt = datetime.strptime(date_str.split("+")[0].split("Z")[0], format_str)
            return dt.replace(tzinfo=timezone.utc)
        except ValueError:
            return None


class DHLProvider(BaseCarrierProvider):
    """DHL Paket Deutschland API Integration.

    API Dokumentation: https://developer.dhl.com/api-reference/shipment-tracking
    """

    carrier_name = "dhl"
    tracking_url_template = "https://www.dhl.de/de/privatkunden/pakete-empfangen/verfolgen.html?piececode={tracking_number}"

    # DHL Tracking-Nummer Patterns
    tracking_patterns = [
        r"^00340\d{17}$",        # DHL Paket DE (22 Stellen, beginnt mit 00340)
        r"^JJD\d{18,20}$",       # DHL Express (JJD + 18-20 Ziffern)
        r"^\d{12,14}$",          # Kuerzere DHL Nummern
        r"^[0-9]{20}$",          # 20-stellige Nummern
    ]

    # DHL Status Mapping
    STATUS_MAP = {
        "pre-transit": ShipmentStatus.LABEL_CREATED,
        "transit": ShipmentStatus.IN_TRANSIT,
        "out-for-delivery": ShipmentStatus.OUT_FOR_DELIVERY,
        "delivered": ShipmentStatus.DELIVERED,
        "failure": ShipmentStatus.EXCEPTION,
        "return": ShipmentStatus.RETURNED,
        "customs": ShipmentStatus.CUSTOMS,
    }

    async def track_shipment(self, tracking_number: str) -> TrackingResult:
        """Fragt DHL Tracking API ab.

        SECURITY: Tracking-Nummer wird validiert und URL-encoded.
        """
        # SECURITY: Input Validation (CWE-20)
        validated_number = validate_tracking_number(tracking_number)
        encoded_number = safe_url_encode(validated_number)

        api_key = getattr(settings, "DHL_API_KEY", None)

        if not api_key:
            # Fallback: Scraping oder Mock fuer Entwicklung
            logger.warning("dhl_api_key_missing", msg="DHL API Key nicht konfiguriert")
            return self._create_mock_result(validated_number)

        headers = {
            "DHL-API-Key": api_key,
            "Accept": "application/json",
        }

        # SECURITY: Verwende validierte und encodierte Tracking-Nummer
        url = f"https://api-eu.dhl.com/track/shipments?trackingNumber={encoded_number}"

        try:
            response = await self.client.get(url, headers=headers)
            response.raise_for_status()
            data = response.json()

            return self._parse_response(validated_number, data)
        except httpx.HTTPStatusError as e:
            logger.error("dhl_api_error", status_code=e.response.status_code)
            raise
        except Exception as e:
            logger.error("dhl_tracking_failed", **safe_error_log(e))
            raise

    def _parse_response(self, tracking_number: str, data: Dict[str, Any]) -> TrackingResult:
        """Parst DHL API Response."""
        shipments = data.get("shipments", [])
        if not shipments:
            return self._create_empty_result(tracking_number)

        shipment = shipments[0]
        status_obj = shipment.get("status", {})

        events: List[TrackingEvent] = []
        for event in shipment.get("events", []):
            events.append({
                "timestamp": self._parse_datetime(event.get("timestamp", "")),
                "status": self._normalize_status(event.get("statusCode", "")),
                "description": event.get("description", ""),
                "location": event.get("location", {}).get("address", {}).get("addressLocality"),
                "postal_code": event.get("location", {}).get("address", {}).get("postalCode"),
                "country_code": event.get("location", {}).get("address", {}).get("countryCode"),
                "raw_status": event.get("statusCode", ""),
            })

        return {
            "tracking_number": tracking_number,
            "carrier": self.carrier_name,
            "current_status": self._normalize_status(status_obj.get("statusCode", "")),
            "status_description": status_obj.get("description", ""),
            "estimated_delivery": self._parse_datetime(shipment.get("estimatedTimeOfDelivery", "")),
            "actual_delivery": self._parse_datetime(shipment.get("actualTimeOfDelivery", "")),
            "origin": shipment.get("origin", {}).get("address", {}).get("addressLocality"),
            "destination": shipment.get("destination", {}).get("address", {}).get("addressLocality"),
            "weight_kg": shipment.get("details", {}).get("weight", {}).get("value"),
            "service_type": shipment.get("service"),
            "events": events,
            "raw_response": data,
            "last_updated": datetime.now(timezone.utc),
        }

    def _normalize_status(self, raw_status: str) -> ShipmentStatus:
        """Mappt DHL Status auf Standard."""
        return self.STATUS_MAP.get(raw_status.lower(), ShipmentStatus.UNKNOWN)

    def _create_mock_result(self, tracking_number: str) -> TrackingResult:
        """Erstellt Mock-Ergebnis fuer Entwicklung."""
        return {
            "tracking_number": tracking_number,
            "carrier": self.carrier_name,
            "current_status": ShipmentStatus.UNKNOWN,
            "status_description": "API-Key nicht konfiguriert",
            "estimated_delivery": None,
            "actual_delivery": None,
            "origin": None,
            "destination": None,
            "weight_kg": None,
            "service_type": None,
            "events": [],
            "raw_response": {"mock": True},
            "last_updated": datetime.now(timezone.utc),
        }

    def _create_empty_result(self, tracking_number: str) -> TrackingResult:
        """Erstellt leeres Ergebnis wenn keine Sendung gefunden."""
        return {
            "tracking_number": tracking_number,
            "carrier": self.carrier_name,
            "current_status": ShipmentStatus.UNKNOWN,
            "status_description": "Sendung nicht gefunden",
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


class DPDProvider(BaseCarrierProvider):
    """DPD Deutschland API Integration.

    API: https://esolutions.dpd.com/
    """

    carrier_name = "dpd"
    tracking_url_template = "https://tracking.dpd.de/status/de_DE/parcel/{tracking_number}"

    # DPD Tracking-Nummer Patterns
    tracking_patterns = [
        r"^\d{14}$",            # 14-stellige Nummer
        r"^0\d{13}$",           # Mit fuehrender 0
        r"^[A-Z]{2}\d{9}[A-Z]{2}$",  # International
    ]

    STATUS_MAP = {
        "pickup": ShipmentStatus.PICKED_UP,
        "in_transit": ShipmentStatus.IN_TRANSIT,
        "in_delivery": ShipmentStatus.OUT_FOR_DELIVERY,
        "delivered": ShipmentStatus.DELIVERED,
        "not_delivered": ShipmentStatus.DELIVERY_ATTEMPT,
        "returned": ShipmentStatus.RETURNED,
        "depot": ShipmentStatus.HELD_AT_LOCATION,
    }

    async def track_shipment(self, tracking_number: str) -> TrackingResult:
        """Fragt DPD Tracking ab.

        SECURITY: Tracking-Nummer wird validiert.
        """
        # SECURITY: Input Validation (CWE-20)
        validated_number = validate_tracking_number(tracking_number)
        encoded_number = safe_url_encode(validated_number)

        api_user = getattr(settings, "DPD_API_USER", None)
        api_password = getattr(settings, "DPD_API_PASSWORD", None)

        if not api_user or not api_password:
            logger.warning("dpd_credentials_missing")
            return self._create_mock_result(validated_number)

        # DPD verwendet SOAP oder REST je nach Vertrag
        url = "https://tracking.dpd.de/rest/plc/de_DE"

        try:
            response = await self.client.get(
                f"{url}/{encoded_number}",
                auth=(api_user, api_password)
            )
            response.raise_for_status()
            data = response.json()
            return self._parse_response(validated_number, data)
        except Exception as e:
            logger.error("dpd_tracking_failed", **safe_error_log(e))
            return self._create_mock_result(validated_number)

    def _parse_response(self, tracking_number: str, data: Dict[str, Any]) -> TrackingResult:
        """Parst DPD Response."""
        parcel_info = data.get("parcellifecycleResponse", {}).get("parcelLifeCycleData", {})

        events: List[TrackingEvent] = []
        for scan in parcel_info.get("statusInfo", []):
            events.append({
                "timestamp": self._parse_datetime(scan.get("date", ""), "%Y-%m-%d %H:%M:%S"),
                "status": self._normalize_status(scan.get("status", "")),
                "description": scan.get("label", {}).get("label", ""),
                "location": scan.get("depot", ""),
                "postal_code": scan.get("depotPostalCode"),
                "country_code": "DE",
                "raw_status": scan.get("status", ""),
            })

        current = events[0] if events else None

        return {
            "tracking_number": tracking_number,
            "carrier": self.carrier_name,
            "current_status": current["status"] if current else ShipmentStatus.UNKNOWN,
            "status_description": current["description"] if current else "",
            "estimated_delivery": None,
            "actual_delivery": None,
            "origin": None,
            "destination": parcel_info.get("receiverInfo", {}).get("city"),
            "weight_kg": parcel_info.get("weight"),
            "service_type": parcel_info.get("product"),
            "events": events,
            "raw_response": data,
            "last_updated": datetime.now(timezone.utc),
        }

    def _normalize_status(self, raw_status: str) -> ShipmentStatus:
        return self.STATUS_MAP.get(raw_status.lower(), ShipmentStatus.UNKNOWN)

    def _create_mock_result(self, tracking_number: str) -> TrackingResult:
        return {
            "tracking_number": tracking_number,
            "carrier": self.carrier_name,
            "current_status": ShipmentStatus.UNKNOWN,
            "status_description": "DPD API nicht konfiguriert",
            "estimated_delivery": None,
            "actual_delivery": None,
            "origin": None,
            "destination": None,
            "weight_kg": None,
            "service_type": None,
            "events": [],
            "raw_response": {"mock": True},
            "last_updated": datetime.now(timezone.utc),
        }


class HermesProvider(BaseCarrierProvider):
    """Hermes Deutschland Tracking Integration."""

    carrier_name = "hermes"
    tracking_url_template = "https://www.myhermes.de/empfangen/sendungsverfolgung/?sendung={tracking_number}"

    # Hermes Tracking-Nummer Patterns
    tracking_patterns = [
        r"^H\d{19}$",           # H + 19 Ziffern
        r"^\d{16}$",            # 16-stellig
    ]

    STATUS_MAP = {
        "aufgegeben": ShipmentStatus.LABEL_CREATED,
        "in_bearbeitung": ShipmentStatus.IN_TRANSIT,
        "in_zustellung": ShipmentStatus.OUT_FOR_DELIVERY,
        "zugestellt": ShipmentStatus.DELIVERED,
        "im_paketshop": ShipmentStatus.HELD_AT_LOCATION,
        "retoure": ShipmentStatus.RETURNED,
    }

    async def track_shipment(self, tracking_number: str) -> TrackingResult:
        """Fragt Hermes Tracking ab.

        SECURITY: Tracking-Nummer wird validiert.
        """
        # SECURITY: Input Validation (CWE-20)
        validated_number = validate_tracking_number(tracking_number)

        api_key = getattr(settings, "HERMES_API_KEY", None)

        if not api_key:
            logger.warning("hermes_api_key_missing")
            return self._create_mock_result(validated_number)

        url = "https://api.hlg.de/svc/shipmenttracking/tracking"

        try:
            response = await self.client.get(
                url,
                params={"shp": validated_number},
                headers={"apiKey": api_key}
            )
            response.raise_for_status()
            data = response.json()
            return self._parse_response(validated_number, data)
        except Exception as e:
            logger.error("hermes_tracking_failed", **safe_error_log(e))
            return self._create_mock_result(validated_number)

    def _parse_response(self, tracking_number: str, data: Dict[str, Any]) -> TrackingResult:
        """Parst Hermes Response."""
        shipment = data.get("shipment", {})

        events: List[TrackingEvent] = []
        for event in shipment.get("events", []):
            events.append({
                "timestamp": self._parse_datetime(event.get("timestamp", "")),
                "status": self._normalize_status(event.get("statusCode", "")),
                "description": event.get("description", ""),
                "location": event.get("location"),
                "postal_code": None,
                "country_code": "DE",
                "raw_status": event.get("statusCode", ""),
            })

        return {
            "tracking_number": tracking_number,
            "carrier": self.carrier_name,
            "current_status": self._normalize_status(shipment.get("status", "")),
            "status_description": shipment.get("statusDescription", ""),
            "estimated_delivery": self._parse_datetime(shipment.get("estimatedDelivery", "")),
            "actual_delivery": self._parse_datetime(shipment.get("deliveryDate", "")),
            "origin": None,
            "destination": shipment.get("recipient", {}).get("city"),
            "weight_kg": shipment.get("weight"),
            "service_type": shipment.get("product"),
            "events": events,
            "raw_response": data,
            "last_updated": datetime.now(timezone.utc),
        }

    def _normalize_status(self, raw_status: str) -> ShipmentStatus:
        return self.STATUS_MAP.get(raw_status.lower(), ShipmentStatus.UNKNOWN)

    def _create_mock_result(self, tracking_number: str) -> TrackingResult:
        return {
            "tracking_number": tracking_number,
            "carrier": self.carrier_name,
            "current_status": ShipmentStatus.UNKNOWN,
            "status_description": "Hermes API nicht konfiguriert",
            "estimated_delivery": None,
            "actual_delivery": None,
            "origin": None,
            "destination": None,
            "weight_kg": None,
            "service_type": None,
            "events": [],
            "raw_response": {"mock": True},
            "last_updated": datetime.now(timezone.utc),
        }


class UPSProvider(BaseCarrierProvider):
    """UPS Tracking API Integration.

    API: https://developer.ups.com/api/reference?loc=en_US#tag/Tracking
    """

    carrier_name = "ups"
    tracking_url_template = "https://www.ups.com/track?tracknum={tracking_number}&loc=de_DE"

    # UPS Tracking-Nummer Patterns
    tracking_patterns = [
        r"^1Z[A-Z0-9]{16}$",    # Standard UPS (1Z + 16 alphanumerisch)
        r"^T\d{10}$",           # T + 10 Ziffern
        r"^[0-9]{26}$",         # 26-stellig Mail Innovations
    ]

    STATUS_MAP = {
        "m": ShipmentStatus.LABEL_CREATED,    # Manifest
        "i": ShipmentStatus.IN_TRANSIT,       # In Transit
        "x": ShipmentStatus.EXCEPTION,        # Exception
        "d": ShipmentStatus.DELIVERED,        # Delivered
        "p": ShipmentStatus.PICKED_UP,        # Pickup
        "o": ShipmentStatus.OUT_FOR_DELIVERY, # Out for Delivery
    }

    async def track_shipment(self, tracking_number: str) -> TrackingResult:
        """Fragt UPS Tracking API ab.

        SECURITY: Tracking-Nummer wird validiert und URL-encoded.
        """
        # SECURITY: Input Validation (CWE-20)
        validated_number = validate_tracking_number(tracking_number)
        encoded_number = safe_url_encode(validated_number)

        client_id = getattr(settings, "UPS_CLIENT_ID", None)
        client_secret = getattr(settings, "UPS_CLIENT_SECRET", None)

        if not client_id or not client_secret:
            logger.warning("ups_credentials_missing")
            return self._create_mock_result(validated_number)

        # OAuth2 Token holen
        token = await self._get_access_token(client_id, client_secret)
        if not token:
            return self._create_mock_result(validated_number)

        # SECURITY: URL-encoded tracking number
        url = f"https://onlinetools.ups.com/api/track/v1/details/{encoded_number}"

        try:
            response = await self.client.get(
                url,
                headers={
                    "Authorization": f"Bearer {token}",
                    "transId": validated_number,
                    "transactionSrc": "ablage-system",
                }
            )
            response.raise_for_status()
            data = response.json()
            return self._parse_response(validated_number, data)
        except Exception as e:
            logger.error("ups_tracking_failed", **safe_error_log(e))
            return self._create_mock_result(validated_number)

    async def _get_access_token(self, client_id: str, client_secret: str) -> Optional[str]:
        """Holt OAuth2 Access Token."""
        try:
            response = await self.client.post(
                "https://onlinetools.ups.com/security/v1/oauth/token",
                data={"grant_type": "client_credentials"},
                auth=(client_id, client_secret),
            )
            response.raise_for_status()
            return response.json().get("access_token")
        except Exception as e:
            logger.error("ups_auth_failed", **safe_error_log(e))
            return None

    def _parse_response(self, tracking_number: str, data: Dict[str, Any]) -> TrackingResult:
        """Parst UPS Response."""
        track_response = data.get("trackResponse", {})
        shipment = track_response.get("shipment", [{}])[0]
        package = shipment.get("package", [{}])[0]

        events: List[TrackingEvent] = []
        for activity in package.get("activity", []):
            location = activity.get("location", {}).get("address", {})
            events.append({
                "timestamp": self._parse_datetime(
                    f"{activity.get('date', '')} {activity.get('time', '')}",
                    "%Y%m%d %H%M%S"
                ),
                "status": self._normalize_status(activity.get("status", {}).get("type", "")),
                "description": activity.get("status", {}).get("description", ""),
                "location": location.get("city"),
                "postal_code": location.get("postalCode"),
                "country_code": location.get("country"),
                "raw_status": activity.get("status", {}).get("code", ""),
            })

        current_status = package.get("currentStatus", {})

        return {
            "tracking_number": tracking_number,
            "carrier": self.carrier_name,
            "current_status": self._normalize_status(current_status.get("type", "")),
            "status_description": current_status.get("description", ""),
            "estimated_delivery": self._parse_datetime(
                package.get("deliveryDate", [{}])[0].get("date", ""),
                "%Y%m%d"
            ),
            "actual_delivery": self._parse_datetime(
                package.get("deliveryDate", [{}])[0].get("date", "") if current_status.get("type") == "D" else "",
                "%Y%m%d"
            ),
            "origin": shipment.get("shipper", {}).get("address", {}).get("city"),
            "destination": shipment.get("shipTo", {}).get("address", {}).get("city"),
            "weight_kg": float(package.get("weight", {}).get("weight", 0)) * 0.453592 if package.get("weight") else None,  # lbs to kg
            "service_type": shipment.get("service", {}).get("description"),
            "events": events,
            "raw_response": data,
            "last_updated": datetime.now(timezone.utc),
        }

    def _normalize_status(self, raw_status: str) -> ShipmentStatus:
        return self.STATUS_MAP.get(raw_status.lower(), ShipmentStatus.UNKNOWN)

    def _create_mock_result(self, tracking_number: str) -> TrackingResult:
        return {
            "tracking_number": tracking_number,
            "carrier": self.carrier_name,
            "current_status": ShipmentStatus.UNKNOWN,
            "status_description": "UPS API nicht konfiguriert",
            "estimated_delivery": None,
            "actual_delivery": None,
            "origin": None,
            "destination": None,
            "weight_kg": None,
            "service_type": None,
            "events": [],
            "raw_response": {"mock": True},
            "last_updated": datetime.now(timezone.utc),
        }


class GLSProvider(BaseCarrierProvider):
    """GLS Germany Tracking Integration."""

    carrier_name = "gls"
    tracking_url_template = "https://gls-group.com/DE/de/paketverfolgung?match={tracking_number}"

    # GLS Tracking-Nummer Patterns
    tracking_patterns = [
        r"^\d{11,12}$",         # 11-12 Ziffern
        r"^Y\d{10}[A-Z]$",      # Y + 10 Ziffern + Buchstabe
    ]

    STATUS_MAP = {
        "preadvice": ShipmentStatus.LABEL_CREATED,
        "intransit": ShipmentStatus.IN_TRANSIT,
        "indelivery": ShipmentStatus.OUT_FOR_DELIVERY,
        "delivered": ShipmentStatus.DELIVERED,
        "stored": ShipmentStatus.HELD_AT_LOCATION,
    }

    async def track_shipment(self, tracking_number: str) -> TrackingResult:
        """Fragt GLS Tracking ab.

        SECURITY: Tracking-Nummer wird validiert und URL-encoded.
        """
        # SECURITY: Input Validation (CWE-20)
        validated_number = validate_tracking_number(tracking_number)
        encoded_number = safe_url_encode(validated_number)

        api_user = getattr(settings, "GLS_API_USER", None)
        api_password = getattr(settings, "GLS_API_PASSWORD", None)

        if not api_user or not api_password:
            logger.warning("gls_credentials_missing")
            return self._create_mock_result(validated_number)

        # SECURITY: URL-encoded tracking number
        url = f"https://api.gls-group.eu/public/v1/tracking/parcels/{encoded_number}"

        try:
            response = await self.client.get(
                url,
                auth=(api_user, api_password)
            )
            response.raise_for_status()
            data = response.json()
            return self._parse_response(validated_number, data)
        except Exception as e:
            logger.error("gls_tracking_failed", **safe_error_log(e))
            return self._create_mock_result(validated_number)

    def _parse_response(self, tracking_number: str, data: Dict[str, Any]) -> TrackingResult:
        """Parst GLS Response."""
        parcel = data.get("parcel", {})

        events: List[TrackingEvent] = []
        for event in parcel.get("history", []):
            events.append({
                "timestamp": self._parse_datetime(event.get("date", "")),
                "status": self._normalize_status(event.get("evtDscr", "")),
                "description": event.get("evtDscr", ""),
                "location": event.get("address", {}).get("city"),
                "postal_code": event.get("address", {}).get("zipCode"),
                "country_code": event.get("address", {}).get("countryCode"),
                "raw_status": event.get("evtDscr", ""),
            })

        return {
            "tracking_number": tracking_number,
            "carrier": self.carrier_name,
            "current_status": self._normalize_status(parcel.get("status", "")),
            "status_description": parcel.get("status", ""),
            "estimated_delivery": self._parse_datetime(parcel.get("expectedDeliveryDate", "")),
            "actual_delivery": self._parse_datetime(parcel.get("deliveryDate", "")),
            "origin": parcel.get("sender", {}).get("city"),
            "destination": parcel.get("consignee", {}).get("city"),
            "weight_kg": parcel.get("weight"),
            "service_type": parcel.get("product"),
            "events": events,
            "raw_response": data,
            "last_updated": datetime.now(timezone.utc),
        }

    def _normalize_status(self, raw_status: str) -> ShipmentStatus:
        status_lower = raw_status.lower().replace(" ", "")
        return self.STATUS_MAP.get(status_lower, ShipmentStatus.UNKNOWN)

    def _create_mock_result(self, tracking_number: str) -> TrackingResult:
        return {
            "tracking_number": tracking_number,
            "carrier": self.carrier_name,
            "current_status": ShipmentStatus.UNKNOWN,
            "status_description": "GLS API nicht konfiguriert",
            "estimated_delivery": None,
            "actual_delivery": None,
            "origin": None,
            "destination": None,
            "weight_kg": None,
            "service_type": None,
            "events": [],
            "raw_response": {"mock": True},
            "last_updated": datetime.now(timezone.utc),
        }


class FedExProvider(BaseCarrierProvider):
    """FedEx Tracking API Integration.

    API: https://developer.fedex.com/api/en-us/catalog/track/v1/docs.html
    """

    carrier_name = "fedex"
    tracking_url_template = "https://www.fedex.com/fedextrack/?trknbr={tracking_number}"

    # FedEx Tracking-Nummer Patterns
    tracking_patterns = [
        r"^\d{12}$",            # 12-stellig (Express)
        r"^\d{15}$",            # 15-stellig (Ground)
        r"^\d{20}$",            # 20-stellig
        r"^\d{22}$",            # 22-stellig (Door Tag)
    ]

    STATUS_MAP = {
        "pl": ShipmentStatus.LABEL_CREATED,    # Picked up
        "it": ShipmentStatus.IN_TRANSIT,       # In Transit
        "od": ShipmentStatus.OUT_FOR_DELIVERY, # Out for Delivery
        "dl": ShipmentStatus.DELIVERED,        # Delivered
        "de": ShipmentStatus.DELIVERY_ATTEMPT, # Delivery Exception
        "ca": ShipmentStatus.EXCEPTION,        # Cancelled
    }

    async def track_shipment(self, tracking_number: str) -> TrackingResult:
        """Fragt FedEx Tracking API ab.

        SECURITY: Tracking-Nummer wird validiert.
        """
        # SECURITY: Input Validation (CWE-20)
        validated_number = validate_tracking_number(tracking_number)

        client_id = getattr(settings, "FEDEX_CLIENT_ID", None)
        client_secret = getattr(settings, "FEDEX_CLIENT_SECRET", None)

        if not client_id or not client_secret:
            logger.warning("fedex_credentials_missing")
            return self._create_mock_result(validated_number)

        # OAuth2 Token
        token = await self._get_access_token(client_id, client_secret)
        if not token:
            return self._create_mock_result(validated_number)

        url = "https://apis.fedex.com/track/v1/trackingnumbers"

        try:
            response = await self.client.post(
                url,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                json={
                    "trackingInfo": [{
                        "trackingNumberInfo": {
                            # SECURITY: Validated tracking number in JSON body
                            "trackingNumber": validated_number
                        }
                    }],
                    "includeDetailedScans": True
                }
            )
            response.raise_for_status()
            data = response.json()
            return self._parse_response(validated_number, data)
        except Exception as e:
            logger.error("fedex_tracking_failed", **safe_error_log(e))
            return self._create_mock_result(validated_number)

    async def _get_access_token(self, client_id: str, client_secret: str) -> Optional[str]:
        """Holt OAuth2 Access Token."""
        try:
            response = await self.client.post(
                "https://apis.fedex.com/oauth/token",
                data={
                    "grant_type": "client_credentials",
                    "client_id": client_id,
                    "client_secret": client_secret,
                },
            )
            response.raise_for_status()
            return response.json().get("access_token")
        except Exception as e:
            logger.error("fedex_auth_failed", **safe_error_log(e))
            return None

    def _parse_response(self, tracking_number: str, data: Dict[str, Any]) -> TrackingResult:
        """Parst FedEx Response."""
        results = data.get("output", {}).get("completeTrackResults", [{}])[0]
        track_result = results.get("trackResults", [{}])[0]

        events: List[TrackingEvent] = []
        for scan in track_result.get("scanEvents", []):
            events.append({
                "timestamp": self._parse_datetime(scan.get("date", "")),
                "status": self._normalize_status(scan.get("derivedStatusCode", "")),
                "description": scan.get("eventDescription", ""),
                "location": scan.get("scanLocation", {}).get("city"),
                "postal_code": scan.get("scanLocation", {}).get("postalCode"),
                "country_code": scan.get("scanLocation", {}).get("countryCode"),
                "raw_status": scan.get("derivedStatusCode", ""),
            })

        latest_status = track_result.get("latestStatusDetail", {})

        return {
            "tracking_number": tracking_number,
            "carrier": self.carrier_name,
            "current_status": self._normalize_status(latest_status.get("code", "")),
            "status_description": latest_status.get("description", ""),
            "estimated_delivery": self._parse_datetime(
                track_result.get("estimatedDeliveryTimeWindow", {}).get("window", {}).get("ends", "")
            ),
            "actual_delivery": self._parse_datetime(
                track_result.get("dateAndTimes", [{}])[0].get("dateTime", "") if latest_status.get("code") == "DL" else ""
            ),
            "origin": track_result.get("shipperInformation", {}).get("address", {}).get("city"),
            "destination": track_result.get("recipientInformation", {}).get("address", {}).get("city"),
            "weight_kg": track_result.get("packageDetails", {}).get("weightAndDimensions", {}).get("weight", [{}])[0].get("value"),
            "service_type": track_result.get("serviceDetail", {}).get("type"),
            "events": events,
            "raw_response": data,
            "last_updated": datetime.now(timezone.utc),
        }

    def _normalize_status(self, raw_status: str) -> ShipmentStatus:
        return self.STATUS_MAP.get(raw_status.lower(), ShipmentStatus.UNKNOWN)

    def _create_mock_result(self, tracking_number: str) -> TrackingResult:
        return {
            "tracking_number": tracking_number,
            "carrier": self.carrier_name,
            "current_status": ShipmentStatus.UNKNOWN,
            "status_description": "FedEx API nicht konfiguriert",
            "estimated_delivery": None,
            "actual_delivery": None,
            "origin": None,
            "destination": None,
            "weight_kg": None,
            "service_type": None,
            "events": [],
            "raw_response": {"mock": True},
            "last_updated": datetime.now(timezone.utc),
        }


class DeutschePostProvider(BaseCarrierProvider):
    """Deutsche Post Sendungsverfolgung.

    Nutzt gleiche API wie DHL fuer Pakete.
    """

    carrier_name = "deutsche_post"
    tracking_url_template = "https://www.deutschepost.de/de/s/sendungsverfolgung.html?piececode={tracking_number}"

    # Deutsche Post Tracking-Nummer Patterns
    tracking_patterns = [
        r"^RR\d{9}DE$",         # Einschreiben (RR + 9 Ziffern + DE)
        r"^RA\d{9}DE$",         # Einschreiben Eil
        r"^CX\d{9}DE$",         # Paket
        r"^LX\d{9}DE$",         # Grossbrief
    ]

    STATUS_MAP = {
        "aufgegeben": ShipmentStatus.LABEL_CREATED,
        "in_bearbeitung": ShipmentStatus.IN_TRANSIT,
        "unterwegs": ShipmentStatus.IN_TRANSIT,
        "in_zustellung": ShipmentStatus.OUT_FOR_DELIVERY,
        "zugestellt": ShipmentStatus.DELIVERED,
        "nicht_zustellbar": ShipmentStatus.EXCEPTION,
    }

    async def track_shipment(self, tracking_number: str) -> TrackingResult:
        """Fragt Deutsche Post Tracking ab (nutzt DHL API).

        SECURITY: Tracking-Nummer wird validiert und URL-encoded.
        """
        # SECURITY: Input Validation (CWE-20)
        validated_number = validate_tracking_number(tracking_number)
        encoded_number = safe_url_encode(validated_number)

        api_key = getattr(settings, "DHL_API_KEY", None)  # Gleiche API wie DHL

        if not api_key:
            logger.warning("deutsche_post_api_key_missing")
            return self._create_mock_result(validated_number)

        headers = {
            "DHL-API-Key": api_key,
            "Accept": "application/json",
        }

        # SECURITY: URL-encoded tracking number
        url = f"https://api-eu.dhl.com/track/shipments?trackingNumber={encoded_number}"

        try:
            response = await self.client.get(url, headers=headers)
            response.raise_for_status()
            data = response.json()
            return self._parse_response(validated_number, data)
        except Exception as e:
            logger.error("deutsche_post_tracking_failed", **safe_error_log(e))
            return self._create_mock_result(validated_number)

    def _parse_response(self, tracking_number: str, data: Dict[str, Any]) -> TrackingResult:
        """Parst Deutsche Post/DHL Response."""
        shipments = data.get("shipments", [])
        if not shipments:
            return self._create_empty_result(tracking_number)

        shipment = shipments[0]
        status_obj = shipment.get("status", {})

        events: List[TrackingEvent] = []
        for event in shipment.get("events", []):
            events.append({
                "timestamp": self._parse_datetime(event.get("timestamp", "")),
                "status": self._normalize_status(event.get("statusCode", "")),
                "description": event.get("description", ""),
                "location": event.get("location", {}).get("address", {}).get("addressLocality"),
                "postal_code": event.get("location", {}).get("address", {}).get("postalCode"),
                "country_code": event.get("location", {}).get("address", {}).get("countryCode"),
                "raw_status": event.get("statusCode", ""),
            })

        return {
            "tracking_number": tracking_number,
            "carrier": self.carrier_name,
            "current_status": self._normalize_status(status_obj.get("statusCode", "")),
            "status_description": status_obj.get("description", ""),
            "estimated_delivery": self._parse_datetime(shipment.get("estimatedTimeOfDelivery", "")),
            "actual_delivery": self._parse_datetime(shipment.get("actualTimeOfDelivery", "")),
            "origin": shipment.get("origin", {}).get("address", {}).get("addressLocality"),
            "destination": shipment.get("destination", {}).get("address", {}).get("addressLocality"),
            "weight_kg": None,  # Deutsche Post gibt kein Gewicht zurueck
            "service_type": shipment.get("service"),
            "events": events,
            "raw_response": data,
            "last_updated": datetime.now(timezone.utc),
        }

    def _normalize_status(self, raw_status: str) -> ShipmentStatus:
        status_lower = raw_status.lower().replace("-", "_")
        return self.STATUS_MAP.get(status_lower, ShipmentStatus.UNKNOWN)

    def _create_mock_result(self, tracking_number: str) -> TrackingResult:
        return {
            "tracking_number": tracking_number,
            "carrier": self.carrier_name,
            "current_status": ShipmentStatus.UNKNOWN,
            "status_description": "Deutsche Post API nicht konfiguriert",
            "estimated_delivery": None,
            "actual_delivery": None,
            "origin": None,
            "destination": None,
            "weight_kg": None,
            "service_type": None,
            "events": [],
            "raw_response": {"mock": True},
            "last_updated": datetime.now(timezone.utc),
        }

    def _create_empty_result(self, tracking_number: str) -> TrackingResult:
        return {
            "tracking_number": tracking_number,
            "carrier": self.carrier_name,
            "current_status": ShipmentStatus.UNKNOWN,
            "status_description": "Sendung nicht gefunden",
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
