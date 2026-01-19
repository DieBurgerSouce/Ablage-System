"""OCR Services Package."""

from app.services.ocr.self_learning_service import (
    SelfLearningOCRService,
    LearningMode,
    ModelVersion,
    CorrectionFeedback,
    ModelPerformanceMetrics,
    ABTestConfig,
    ABTestResult,
    get_self_learning_service,
    CONFIDENCE_ADJUSTMENTS_KEY,
)

__all__ = [
    "SelfLearningOCRService",
    "LearningMode",
    "ModelVersion",
    "CorrectionFeedback",
    "ModelPerformanceMetrics",
    "ABTestConfig",
    "ABTestResult",
    "get_self_learning_service",
    "CONFIDENCE_ADJUSTMENTS_KEY",
]
