# -*- coding: utf-8 -*-
"""
Process Mining Services for Ablage-System.

Vision 2.0 Feature: Process Mining & Autonome Automatisierung
Unterstützt:
- Prozess-Discovery aus Event-Logs
- Bottleneck-Erkennung
- Varianten-Analyse
- Automatisierungs-Vorschläge
- KPI-Berechnung

Feinpoliert und durchdacht.
"""

from app.services.process_mining.event_tracker import ProcessEventTracker
from app.services.process_mining.process_discovery_service import ProcessDiscoveryService
from app.services.process_mining.bottleneck_detector import BottleneckDetector
from app.services.process_mining.automation_suggester import AutomationSuggester

__all__ = [
    "ProcessEventTracker",
    "ProcessDiscoveryService",
    "BottleneckDetector",
    "AutomationSuggester",
]
