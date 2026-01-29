# -*- coding: utf-8 -*-
"""
Predictive Maintenance Services.

Vision 2.0 Feature: Predictive Maintenance (Phase 5)
Bietet proaktive Systemueberwachung:
- GPU VRAM Overflow Vorhersage
- Queue Overflow Vorhersage
- OCR Qualitaets-Degradation Erkennung
- Ressourcen-Forecasting

Feinpoliert und durchdacht.
"""

from app.services.predictive.system_health_predictor import (
    SystemHealthPredictor,
    PredictionResult,
    get_health_predictor,
)
from app.services.predictive.ocr_quality_forecaster import (
    OCRQualityForecaster,
    DegradationAlert,
    get_quality_forecaster,
)
from app.services.predictive.predictive_alerts_service import (
    PredictiveAlertsService,
    PredictiveAlert,
    get_predictive_alerts_service,
)

__all__ = [
    "SystemHealthPredictor",
    "PredictionResult",
    "get_health_predictor",
    "OCRQualityForecaster",
    "DegradationAlert",
    "get_quality_forecaster",
    "PredictiveAlertsService",
    "PredictiveAlert",
    "get_predictive_alerts_service",
]
