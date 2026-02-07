# -*- coding: utf-8 -*-
"""
Predictive Services.

Vision 2.0 Feature: Predictive Intelligence (Phase 5)
Bietet proaktive Ueberwachung und Vorhersagen:
- GPU VRAM Overflow Vorhersage
- Queue Overflow Vorhersage
- OCR Qualitaets-Degradation Erkennung
- Ressourcen-Forecasting
- Cashflow Prediction (Phase 2.2)

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
from app.services.predictive.cashflow_predictor_service import (
    CashflowPredictorService,
    get_cashflow_predictor_service,
    CashFlowPrediction,
    EntityPaymentProfile,
    LiquidityAlert,
    PaymentProbability,
    SeasonalPattern,
    PaymentConsistency,
    SeasonalPatternType,
    LiquidityAlertType,
)

__all__ = [
    # System Health
    "SystemHealthPredictor",
    "PredictionResult",
    "get_health_predictor",
    # OCR Quality
    "OCRQualityForecaster",
    "DegradationAlert",
    "get_quality_forecaster",
    # Predictive Alerts
    "PredictiveAlertsService",
    "PredictiveAlert",
    "get_predictive_alerts_service",
    # Cashflow Predictor
    "CashflowPredictorService",
    "get_cashflow_predictor_service",
    "CashFlowPrediction",
    "EntityPaymentProfile",
    "LiquidityAlert",
    "PaymentProbability",
    "SeasonalPattern",
    "PaymentConsistency",
    "SeasonalPatternType",
    "LiquidityAlertType",
]
