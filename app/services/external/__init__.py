"""
External Services Module.

Stellt Services für externe API-Integrationen bereit.
WICHTIG: Nur kostenlose APIs, nur auf manuelle Anfrage (Button-Klick).
"""

from app.services.external.market_data_service import (
    MarketDataService,
    PropertyMarketData,
    VehicleMarketData,
    get_market_data_service,
)

__all__ = [
    "MarketDataService",
    "PropertyMarketData",
    "VehicleMarketData",
    "get_market_data_service",
]
