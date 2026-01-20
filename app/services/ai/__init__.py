"""
AI Autonomy Services.

Confidence-basierte Autonomie fuer Dokument-Verarbeitung:
- 95%+ Konfidenz: Automatisch verarbeiten
- 80-95% Konfidenz: Vorschlag mit 1-Click Bestaetigung
- <80% Konfidenz: Manuelle Review Queue

Services:
- AIDecisionService: Basis-Entscheidungslogik mit Audit-Trail
- AutonomousActionsService: Konkrete autonome Aktionen (Ablage, Freigabe, etc.)
- NLQService: Natural Language Queries (deutsch)
- RoutingIntelligenceService: Intelligentes Dokumenten-Routing
- PredictiveActionService: Proaktive Handlungsvorschlaege
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
from app.services.ai.autonomous_actions_service import (
    AutonomousActionsService,
    AutonomyConfig,
    create_autonomy_config,
    AutonomousAction,
    ActionProposal,
    ActionResult,
)
from app.services.ai.nlq_service import (
    NLQService,
    NLQResult,
    QueryIntent,
    EntityType,
    ExtractedEntity,
)
from app.services.ai.routing_intelligence_service import (
    RoutingIntelligenceService,
    RoutingDecision,
    RoutingTarget,
    RoutingRule,
    Priority,
    Department,
    get_routing_intelligence_service,
)
from app.services.ai.predictive_action_service import (
    PredictiveActionService,
    ActionType,
    ActionPriority,
    ActionStatus,
)

__all__ = [
    # Core Decision Service
    "AIDecisionService",
    # Categorization & Matching
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
    # Autonomous Actions (Neu: Januar 2026)
    "AutonomousActionsService",
    "AutonomyConfig",
    "create_autonomy_config",
    "AutonomousAction",
    "ActionProposal",
    "ActionResult",
    # Natural Language Queries (Neu: Januar 2026)
    "NLQService",
    "NLQResult",
    "QueryIntent",
    "EntityType",
    "ExtractedEntity",
    # Routing Intelligence (Neu: Januar 2026)
    "RoutingIntelligenceService",
    "RoutingDecision",
    "RoutingTarget",
    "RoutingRule",
    "Priority",
    "Department",
    "get_routing_intelligence_service",
    # Predictive Actions
    "PredictiveActionService",
    "ActionType",
    "ActionPriority",
    "ActionStatus",
]
