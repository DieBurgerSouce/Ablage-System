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

NEU: Team Workflow System
- TeamClassifier: Klassifiziert Tasks und wählt optimales Team-Template
- QualityGates: 6-stufiges Gate-System für Qualitätssicherung
- SharedFileProtocol: Koordination für gemeinsame Datei-Zugriffe
- TeamSpawner: Automatisches Spawnen von spezialisierten Teams

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

# Team Workflow System
from .team_workflow import (
    # Core Types
    TeamType,
    TeamTemplate,
    TeamClassifier,
    ClassificationInput,
    ClassificationOutput,
    # Complexity & Phases
    Complexity,
    Coupling,
    PhaseMode,
    Phase,
    AgentSpec,
    # Safety Zones
    SafetyZone,
    PARALLEL_SAFE_ZONES,
    SEQUENTIAL_ONLY_FILES,
    # Constants & Templates
    TEAM_TEMPLATES,
    CLASSIFICATION_MATRIX,
    # Functions
    classify_task,
    get_team_template,
)

from .quality_gates import (
    # Core Types
    GateStatus,
    GateResult,
    CheckResult,
    CheckSeverity,
    GateType,
    # Gate Implementations
    Gate1ResearchComplete,
    Gate2DesignApproved,
    Gate3CodeQuality,
    Gate4TestsPassing,
    Gate5ReviewApproved,
    Gate6IntegrationClean,
    # Constants & Functions
    GATES,
    run_gate,
)

from .shared_file_protocol import (
    # Core Classes
    SharedFileProtocol,
    RegistrationManifest,
    BottleneckFile,
    ParallelZone,
    ValidationResult,
    # Constants (single source of truth)
    BOTTLENECK_FILES,
    # Convenience Functions
    is_bottleneck_file,
    validate_agent_files,
    merge_agent_manifests,
    generate_phase6_instructions,
)

from .team_spawner import (
    # Core Classes
    TeamSpawner,
    TeamSpawnPlan,
    PhaseSpawnPlan,
    SpawnInstruction,
    # Functions
    spawn_for_task,
    format_plan,
)

__version__ = "1.1.0"
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

    # Team Workflow System - team_workflow module
    "TeamType",
    "TeamTemplate",
    "TeamClassifier",
    "ClassificationInput",
    "ClassificationOutput",
    "Complexity",
    "Coupling",
    "PhaseMode",
    "Phase",
    "AgentSpec",
    "SafetyZone",
    "PARALLEL_SAFE_ZONES",
    "SEQUENTIAL_ONLY_FILES",
    "TEAM_TEMPLATES",
    "CLASSIFICATION_MATRIX",
    "classify_task",
    "get_team_template",

    # Team Workflow System - quality_gates module
    "GateStatus",
    "GateResult",
    "CheckResult",
    "CheckSeverity",
    "GateType",
    "Gate1ResearchComplete",
    "Gate2DesignApproved",
    "Gate3CodeQuality",
    "Gate4TestsPassing",
    "Gate5ReviewApproved",
    "Gate6IntegrationClean",
    "GATES",
    "run_gate",

    # Team Workflow System - shared_file_protocol module (single source of truth)
    "SharedFileProtocol",
    "RegistrationManifest",
    "BottleneckFile",
    "ParallelZone",
    "ValidationResult",
    "BOTTLENECK_FILES",
    "is_bottleneck_file",
    "validate_agent_files",
    "merge_agent_manifests",
    "generate_phase6_instructions",

    # Team Workflow System - team_spawner module
    "TeamSpawner",
    "TeamSpawnPlan",
    "PhaseSpawnPlan",
    "SpawnInstruction",
    "spawn_for_task",
    "format_plan",
]
