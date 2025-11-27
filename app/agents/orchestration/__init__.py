"""
Orchestration Agents - Workflow coordination and management.

Contains:
- DocumentProcessingOrchestrator: Main workflow orchestrator
- OCRBackendRouter: Intelligent backend selection
- OCRRouterModel: ML model for routing (requires XGBoost)
- MLRouterTrainer: Training pipeline for ML model

Note: XGBoost ist optional. Prüfe XGBOOST_AVAILABLE um zu sehen ob ML-Routing verfügbar ist.
      Installation: pip install xgboost oder pip install ablage-system-ocr[ml]
"""

from .document_orchestrator import DocumentProcessingOrchestrator
from .ocr_router import OCRBackendRouter
from .ml_router_model import OCRRouterModel, OCRRouterFeatures
from .ml_trainer import MLRouterTrainer, TrainingSample, TrainingDataBuffer, XGBOOST_AVAILABLE

__all__ = [
    "DocumentProcessingOrchestrator",
    "OCRBackendRouter",
    "OCRRouterModel",
    "OCRRouterFeatures",
    "MLRouterTrainer",
    "TrainingSample",
    "TrainingDataBuffer",
    "XGBOOST_AVAILABLE",
]
