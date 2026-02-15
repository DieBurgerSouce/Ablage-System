# -*- coding: utf-8 -*-
"""
Inbound Webhook Provider Adapters.

Generisches Provider-Registry fuer eingehende Webhooks.
Jeder Provider mappt seine Events auf interne EventTypes
und definiert provider-spezifische Header und PII-Felder.

Feinpoliert und durchdacht - DRY Provider Abstraction.
"""

from abc import ABC, abstractmethod
from typing import Dict, Optional, Set

import structlog

from app.services.events.event_bus import EventType

logger = structlog.get_logger(__name__)


class BaseWebhookProvider(ABC):
    """Basisklasse fuer Inbound-Webhook-Provider.

    Jeder Provider definiert:
    - Signatur-Header-Namen
    - Event-Mapping auf interne EventTypes
    - PII-Felder fuer Payload-Sanitisierung
    - Externe-Referenz-Extraktion
    """

    provider_name: str = "unknown"
    signature_header: str = "X-Webhook-Signature"
    timestamp_header: str = "X-Webhook-Timestamp"
    webhook_id_header: str = "X-Webhook-Id"

    @abstractmethod
    def map_event(self, event_type: str, action: str) -> Optional[EventType]:
        """Mappt externes Event auf internen EventType.

        Args:
            event_type: Provider-spezifischer Event-Typ
            action: Aktion (create, update, delete, status_change)

        Returns:
            Interner EventType oder None wenn kein Mapping existiert
        """

    @abstractmethod
    def extract_external_ref(self, data: Dict[str, object]) -> Optional[str]:
        """Extrahiert externe Referenz (Tracking-Nr, Rechnungs-Nr) aus Payload.

        Args:
            data: Provider-spezifische Event-Daten

        Returns:
            Externe Referenz oder None
        """

    def get_pii_fields(self) -> Set[str]:
        """Provider-spezifische PII-Felder fuer Sanitisierung.

        Returns:
            Set von Feldnamen die PII enthalten koennen
        """
        # Standard-PII-Felder (erweitert von Odoo-Pattern)
        return {
            "name", "email", "phone", "mobile", "street", "street2",
            "city", "zip", "vat", "bank_ids", "iban", "bic",
            "contact_address", "comment", "ref", "title",
            "address", "recipient", "sender", "customer_name",
            "account_number", "tax_id",
        }


class DATEVWebhookProvider(BaseWebhookProvider):
    """DATEV Webhook Provider.

    Empfaengt Events von DATEV Connect:
    - Dokument-Export-Benachrichtigungen
    - Rechnungs-Events
    - Buchungs-Events
    """

    provider_name = "datev"
    signature_header = "X-DATEV-Webhook-Signature"
    timestamp_header = "X-DATEV-Webhook-Timestamp"
    webhook_id_header = "X-DATEV-Webhook-Id"

    EVENT_MAP: Dict[str, EventType] = {
        "document.exported": EventType.DOCUMENT_OCR_COMPLETED,
        "document.received": EventType.DOCUMENT_UPLOADED,
        "invoice.received": EventType.FINANCE_TRANSACTION_ADDED,
        "invoice.updated": EventType.FINANCE_TRANSACTION_ADDED,
        "booking.created": EventType.FINANCE_TRANSACTION_ADDED,
        "booking.updated": EventType.FINANCE_TRANSACTION_ADDED,
    }

    def map_event(self, event_type: str, action: str) -> Optional[EventType]:
        """Mappt DATEV-Events auf interne EventTypes."""
        return self.EVENT_MAP.get(event_type)

    def extract_external_ref(self, data: Dict[str, object]) -> Optional[str]:
        """Extrahiert DATEV-Referenz (Belegnummer, Buchungsnummer)."""
        for key in ("document_number", "invoice_number", "booking_number", "belegnummer"):
            val = data.get(key)
            if val is not None:
                return str(val)
        return None

    def get_pii_fields(self) -> Set[str]:
        """DATEV-spezifische PII-Felder."""
        base = super().get_pii_fields()
        return base | {
            "steuernummer", "ust_id", "mandant_name",
            "kontoinhaber", "bankverbindung",
        }


class DHLWebhookProvider(BaseWebhookProvider):
    """DHL Webhook Provider.

    Empfaengt Sendungsstatus-Updates von DHL.
    """

    provider_name = "dhl"
    signature_header = "X-DHL-Signature"
    timestamp_header = "X-DHL-Timestamp"
    webhook_id_header = "X-DHL-Webhook-Id"

    # DHL Events werden nicht direkt auf EventBus-Events gemappt,
    # sondern ueber den CarrierService verarbeitet
    EVENT_MAP: Dict[str, Optional[EventType]] = {
        "shipment.in_transit": None,
        "shipment.out_for_delivery": None,
        "shipment.delivered": None,
        "shipment.exception": None,
        "shipment.returned": None,
    }

    def map_event(self, event_type: str, action: str) -> Optional[EventType]:
        """DHL-Events haben kein direktes EventBus-Mapping."""
        return self.EVENT_MAP.get(event_type)

    def extract_external_ref(self, data: Dict[str, object]) -> Optional[str]:
        """Extrahiert DHL Tracking-Nummer."""
        for key in ("tracking_number", "trackingNumber", "shipment_id"):
            val = data.get(key)
            if val is not None:
                return str(val)
        return None

    def get_pii_fields(self) -> Set[str]:
        """DHL-spezifische PII-Felder."""
        base = super().get_pii_fields()
        return base | {"receiver_name", "receiver_address", "shipper_name"}


class DPDWebhookProvider(BaseWebhookProvider):
    """DPD Webhook Provider.

    Empfaengt Sendungsstatus-Updates von DPD.
    """

    provider_name = "dpd"
    signature_header = "X-DPD-Signature"
    timestamp_header = "X-DPD-Timestamp"
    webhook_id_header = "X-DPD-Webhook-Id"

    EVENT_MAP: Dict[str, Optional[EventType]] = {
        "parcel.pickup": None,
        "parcel.in_transit": None,
        "parcel.in_delivery": None,
        "parcel.delivered": None,
        "parcel.not_delivered": None,
        "parcel.returned": None,
    }

    def map_event(self, event_type: str, action: str) -> Optional[EventType]:
        """DPD-Events haben kein direktes EventBus-Mapping."""
        return self.EVENT_MAP.get(event_type)

    def extract_external_ref(self, data: Dict[str, object]) -> Optional[str]:
        """Extrahiert DPD Paketnummer."""
        for key in ("parcel_number", "parcelNumber", "tracking_number"):
            val = data.get(key)
            if val is not None:
                return str(val)
        return None


class UPSWebhookProvider(BaseWebhookProvider):
    """UPS Webhook Provider.

    Empfaengt Sendungsstatus-Updates von UPS.
    """

    provider_name = "ups"
    signature_header = "X-UPS-Signature"
    timestamp_header = "X-UPS-Timestamp"
    webhook_id_header = "X-UPS-Webhook-Id"

    EVENT_MAP: Dict[str, Optional[EventType]] = {
        "tracking.manifest": None,
        "tracking.in_transit": None,
        "tracking.out_for_delivery": None,
        "tracking.delivered": None,
        "tracking.exception": None,
        "tracking.returned": None,
    }

    def map_event(self, event_type: str, action: str) -> Optional[EventType]:
        """UPS-Events haben kein direktes EventBus-Mapping."""
        return self.EVENT_MAP.get(event_type)

    def extract_external_ref(self, data: Dict[str, object]) -> Optional[str]:
        """Extrahiert UPS Tracking-Nummer."""
        for key in ("tracking_number", "trackingNumber", "inquiryNumber"):
            val = data.get(key)
            if val is not None:
                return str(val)
        return None


class GLSWebhookProvider(BaseWebhookProvider):
    """GLS Webhook Provider.

    Empfaengt Sendungsstatus-Updates von GLS.
    """

    provider_name = "gls"
    signature_header = "X-GLS-Signature"
    timestamp_header = "X-GLS-Timestamp"
    webhook_id_header = "X-GLS-Webhook-Id"

    EVENT_MAP: Dict[str, Optional[EventType]] = {
        "parcel.preadvice": None,
        "parcel.in_transit": None,
        "parcel.in_delivery": None,
        "parcel.delivered": None,
        "parcel.stored": None,
    }

    def map_event(self, event_type: str, action: str) -> Optional[EventType]:
        """GLS-Events haben kein direktes EventBus-Mapping."""
        return self.EVENT_MAP.get(event_type)

    def extract_external_ref(self, data: Dict[str, object]) -> Optional[str]:
        """Extrahiert GLS Paketnummer."""
        for key in ("parcel_number", "parcelNumber", "tracking_id"):
            val = data.get(key)
            if val is not None:
                return str(val)
        return None


# =============================================================================
# Provider Registry
# =============================================================================

PROVIDER_REGISTRY: Dict[str, BaseWebhookProvider] = {
    "datev": DATEVWebhookProvider(),
    "dhl": DHLWebhookProvider(),
    "dpd": DPDWebhookProvider(),
    "ups": UPSWebhookProvider(),
    "gls": GLSWebhookProvider(),
}


def get_provider(provider_name: str) -> Optional[BaseWebhookProvider]:
    """Gibt den Provider-Adapter fuer einen Provider-Namen zurueck.

    Args:
        provider_name: Name des Providers (z.B. "datev", "dhl")

    Returns:
        Provider-Adapter oder None wenn nicht gefunden
    """
    return PROVIDER_REGISTRY.get(provider_name)
