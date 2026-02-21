# -*- coding: utf-8 -*-
"""Anomalie-Erkennung Service-Paket.

Hybrid-Ansatz: Regelbasiert + Statistisch.
Erkennt verdaechtige Muster in Rechnungen, Zahlungen und Dokumenten.
"""

from app.services.anomaly.anomaly_detection_service import (
    AnomalyDetectionService,
    get_anomaly_detection_service,
)

__all__ = [
    "AnomalyDetectionService",
    "get_anomaly_detection_service",
]
