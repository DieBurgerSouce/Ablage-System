"""
Multi-Model Orchestration System für Ablage-System.

Dieses Paket implementiert intelligentes Routing zwischen Claude-Modellen:
- Opus: Architektur, Security, komplexe Entscheidungen
- Sonnet: Implementierung, Tests, Dokumentation
- Haiku: Formatierung, Boilerplate, einfache Validierung

NEU: Claude Flow V3 Swarm Integration
- SwarmBridge: Automatisches Spawnen von Multi-Agent Swarms
- TaskComplexityAnalyzer: Entscheidet ob Swarm nötig ist
- auto_swarm(): Convenience-Funktion für automatische Swarms

Hauptkomponenten:
- TaskClassifier: Klassifiziert Aufgaben für das passende Modell
- ContextCompressor: Komprimiert Kontext für verschiedene Modelle
- DecisionCache: Cached Opus-Entscheidungen für Sonnet/Haiku
- QualityGate: Validiert Output und eskaliert bei Bedarf
- Orchestrator: Hauptkomponente die alles koordiniert
- SwarmBridge: Brücke zu Claude Flow V3 Swarms
"""

from .task_classifier import TaskClassifier, ModelTier, ClassificationResult
from .context_compressor import ContextCompressor, CompressionLevel, CompressedContext
from .decision_cache import DecisionCache, CachedDecision
from .quality_gate import QualityGate, QualityLevel, QualityResult
from .orchestrator import Orchestrator, OverrideMode, OrchestrationResult
from .learning_feedback import LearningFeedback, TaskExecution, PatternStatistics
from .user_feedback import UserFeedback, DisplayMode, OrchestrationFeedback
from .metrics import OrchestrationMetrics, MetricsSnapshot
from .token_counter import TokenCounter, ContentType
from .validators import OrchestrationValidator, ValidationError

# Claude Flow V3 Swarm Integration
from .swarm_bridge import (
    # Core Classes
    SwarmBridge,
    SwarmConfig,
    SwarmStrategy,
    SwarmTopology,
    SwarmPlan,
    SwarmAgent,
    AgentType,
    ComplexityAnalysis,
    # Analyzers
    TaskComplexityAnalyzer,
    SwarmPlanner,
    # Convenience Functions
    get_swarm_bridge,
    analyze_for_swarm,
    get_swarm_instructions,
)

__version__ = "1.0.0"
__author__ = "Ablage-System Team"

__all__ = [
    # Task Classification
    "TaskClassifier",
    "ModelTier",
    "ClassificationResult",

    # Context Compression
    "ContextCompressor",
    "CompressionLevel",
    "CompressedContext",

    # Decision Caching
    "DecisionCache",
    "CachedDecision",

    # Quality Gates
    "QualityGate",
    "QualityLevel",
    "QualityResult",

    # Main Orchestrator
    "Orchestrator",
    "OverrideMode",
    "OrchestrationResult",

    # Learning Feedback
    "LearningFeedback",
    "TaskExecution",
    "PatternStatistics",

    # User Feedback
    "UserFeedback",
    "DisplayMode",
    "OrchestrationFeedback",

    # Metrics
    "OrchestrationMetrics",
    "MetricsSnapshot",

    # Token Counter
    "TokenCounter",
    "ContentType",

    # Validators
    "OrchestrationValidator",
    "ValidationError",

    # Claude Flow V3 Swarm Integration
    "SwarmBridge",
    "SwarmConfig",
    "SwarmStrategy",
    "SwarmTopology",
    "SwarmPlan",
    "SwarmAgent",
    "AgentType",
    "ComplexityAnalysis",
    "TaskComplexityAnalyzer",
    "SwarmPlanner",
    "get_swarm_bridge",
    "analyze_for_swarm",
    "get_swarm_instructions",
]
