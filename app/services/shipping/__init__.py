# -*- coding: utf-8 -*-
"""Shipping/Paketdienst Integration Module.

Unterstützte Carrier:
- DHL (Marktführer Deutschland)
- DPD (sehr verbreitet B2B)
- Hermes (B2C stark)
- UPS (International)
- GLS (B2B stark)
- FedEx (Express/International)
- Deutsche Post (Briefe/Pakete)
"""

from .carrier_service import (
    CarrierService,
    Carrier,
    ShipmentStatus,
    TrackingResult,
    TrackingEvent,
)
from .carrier_providers import (
    BaseCarrierProvider,
    DHLProvider,
    DPDProvider,
    HermesProvider,
    UPSProvider,
    GLSProvider,
    FedExProvider,
    DeutschePostProvider,
)

__all__ = [
    "CarrierService",
    "Carrier",
    "ShipmentStatus",
    "TrackingResult",
    "TrackingEvent",
    "BaseCarrierProvider",
    "DHLProvider",
    "DPDProvider",
    "HermesProvider",
    "UPSProvider",
    "GLSProvider",
    "FedExProvider",
    "DeutschePostProvider",
]
