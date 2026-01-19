"""
Finanz-KI Suite Module.

AI-gestuetzte Finanzanalyse-Services.

Services:
- PredictiveCashFlowService: ML-basierte Zahlungsvorhersagen
- FraudDetectionService: Anomalie-Erkennung bei Transaktionen
"""

from app.services.finanzki.predictive_cashflow_service import PredictiveCashFlowService

__all__ = ["PredictiveCashFlowService"]
