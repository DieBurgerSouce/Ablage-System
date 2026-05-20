"""Zero-Touch OCR - Automatische Dokumentverarbeitung ohne manuellen Eingriff."""
from app.services.zero_touch.zero_touch_orchestrator import ZeroTouchOrchestrator
from app.services.zero_touch.business_object_factory import BusinessObjectFactory
from app.services.zero_touch.confidence_aggregator import ConfidenceAggregator
from app.services.zero_touch.auto_filing_service import AutoFilingService

__all__ = [
    "ZeroTouchOrchestrator",
    "BusinessObjectFactory",
    "ConfidenceAggregator",
    "AutoFilingService",
]
