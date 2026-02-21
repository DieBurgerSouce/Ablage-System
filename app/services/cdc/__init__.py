# -*- coding: utf-8 -*-
"""
Change Data Capture (CDC) Services.

Echtzeit-Aenderungserfassung fuer Datenbank-Synchronisation
mit DATEV/Lexware und Event-Streaming.
"""

from app.services.cdc.cdc_service import CDCService
from app.services.cdc.cdc_consumer import CDCConsumer

__all__ = [
    "CDCService",
    "CDCConsumer",
]
