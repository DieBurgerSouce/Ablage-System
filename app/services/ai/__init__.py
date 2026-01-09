"""
AI Autonomy Services.

Confidence-basierte Autonomie fuer Dokument-Verarbeitung:
- 95%+ Konfidenz: Automatisch verarbeiten
- 80-95% Konfidenz: Vorschlag mit 1-Click Bestaetigung
- <80% Konfidenz: Manuelle Review Queue
"""

from app.services.ai.decision_service import AIDecisionService
from app.services.ai.auto_categorization_service import AutoCategorizationService
from app.services.ai.smart_matching_service import SmartMatchingService
from app.services.ai.anomaly_detection_service import AnomalyDetectionService
from app.services.ai.duplicate_detection_service import DuplicateDetectionService
from app.services.ai.learning_pipeline import AILearningPipeline
from app.services.ai.ollama_service import (
    OllamaService,
    OllamaConfig,
    ExtractedEntities,
    ContractAnalysis,
    get_ollama_service,
)

__all__ = [
    "AIDecisionService",
    "AutoCategorizationService",
    "SmartMatchingService",
    "AnomalyDetectionService",
    "DuplicateDetectionService",
    "AILearningPipeline",
    # Ollama (lokale LLM)
    "OllamaService",
    "OllamaConfig",
    "ExtractedEntities",
    "ContractAnalysis",
    "get_ollama_service",
]
