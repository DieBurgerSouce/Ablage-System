"""
Orchestration Agents - Workflow coordination and management.

Contains:
- DocumentProcessingOrchestrator: Main workflow orchestrator
- UnifiedOCRRouter: Konsolidierter Router (ML + Regeln) - NEU!
- OCRBackendRouter: Legacy router (use UnifiedOCRRouter instead)
- OCRRouterModel: ML model for routing (requires XGBoost)
- MLRouterTrainer: Training pipeline for ML model
- ModelRegistry: Sichere Modellverwaltung und Versionierung

Note: XGBoost ist optional. Prüfe XGBOOST_AVAILABLE um zu sehen ob ML-Routing verfügbar ist.
      Installation: pip install xgboost oder pip install ablage-system-ocr[ml]

Sicherheit:
- Modelle werden im sicheren JSON-Format gespeichert (kein pickle!)
- Model Registry mit Versionierung und Rollback-Support
"""

from .document_orchestrator import DocumentProcessingOrchestrator
from .ocr_router import OCRBackendRouter
from .ml_router_model import OCRRouterModel, OCRRouterFeatures
from .ml_trainer import MLRouterTrainer, TrainingSample, TrainingDataBuffer, XGBOOST_AVAILABLE
from .model_registry import ModelRegistry, ModelVersion, compute_feature_hash
from .unified_router import (
    UnifiedOCRRouter,
    BackendType,
    DocumentAnalysis,
    SLARequirements,
    RoutingResult,
    RoutingMethod,
)
from .language_detector import (
    LanguageDetector,
    LanguageDetectionResult,
    LanguageCode,
    ScriptType,
    detect_language,
    get_language_backends,
)

__all__ = [
    # Main router (use this!)
    "UnifiedOCRRouter",
    "BackendType",
    "DocumentAnalysis",
    "SLARequirements",
    "RoutingResult",
    "RoutingMethod",
    # Language detection
    "LanguageDetector",
    "LanguageDetectionResult",
    "LanguageCode",
    "ScriptType",
    "detect_language",
    "get_language_backends",
    # Orchestration
    "DocumentProcessingOrchestrator",
    # Legacy router
    "OCRBackendRouter",
    # ML components
    "OCRRouterModel",
    "OCRRouterFeatures",
    "MLRouterTrainer",
    "TrainingSample",
    "TrainingDataBuffer",
    "XGBOOST_AVAILABLE",
    # Model management
    "ModelRegistry",
    "ModelVersion",
    "compute_feature_hash",
]
