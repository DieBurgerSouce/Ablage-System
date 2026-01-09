# -*- coding: utf-8 -*-
"""
Orchestration Services.

Dieses Modul bietet Services fuer intelligente Cross-Module Orchestrierung:

- CrossModuleOrchestrator: Das Gehirn des Systems
  - Reagiert automatisch auf Events aus allen Modulen
  - Triggert Workflows, Benachrichtigungen, Empfehlungen
  - Koordiniert Entscheidungen um Konflikte zu vermeiden
  - Analysiert kaskadierende Auswirkungen

- UnifiedDecisionEngine: Das Grosshirn des Systems
  - Sammelt ALLE anstehenden Entscheidungen
  - Priorisiert nach GESAMT-IMPACT
  - Erkennt und loest KONFLIKTE
  - Verhindert widersprüchliche Empfehlungen

TRUE Enterprise-Level: Das System HANDELT, nicht nur MELDET.
"""

from app.services.orchestration.cross_module_orchestrator import (
    CrossModuleOrchestrator,
    get_cross_module_orchestrator,
    start_orchestrator,
    stop_orchestrator,
    OrchestrationAction,
    OrchestrationDecision,
    CascadingImpact,
    ActionType,
    ActionPriority,
    ModuleType,
)

from app.services.orchestration.unified_decision_engine import (
    UnifiedDecisionEngine,
    get_unified_decision_engine,
    UnifiedDecision,
    ImpactScore,
    ConflictType,
    DecisionStatus,
    ImpactDimension,
)

from app.services.orchestration.explainability_service import (
    ExplainabilityService,
    get_explainability_service,
    DecisionExplanation,
    ExplanationFactor,
    ImpactBreakdown,
    AlternativeOption,
    FactorType,
    ConfidenceLevel,
)

from app.services.orchestration.whatif_simulator_service import (
    WhatIfSimulatorService,
    get_whatif_simulator,
    ScenarioInput,
    ScenarioResult,
    ScenarioType,
    TimeHorizon,
    ImpactSeverity,
    KPIProjection,
    TimelinePoint,
    ComparisonResult,
)

from app.services.orchestration.proactive_insights_service import (
    ProactiveInsightsService,
    get_proactive_insights_service,
    ProactiveInsight,
    ExtractedEntity,
    EnrichedResponse,
    InsightType,
    InsightPriority,
    EntityType,
    InsightRule,
    InsightRuleEngine,
)

from app.services.orchestration.personalized_thresholds_service import (
    PersonalizedThresholdsService,
    get_personalized_thresholds_service,
    ThresholdRegistry,
    UserProfile,
    UserThreshold,
    ThresholdDefinition,
    ThresholdAdjustment,
    ThresholdRecommendation,
    ProfessionType,
    RiskTolerance,
    ThresholdType,
    ThresholdCategory,
    AdjustmentSource,
)

from app.services.orchestration.seasonality_detection_service import (
    SeasonalityDetectionService,
    get_seasonality_detection_service,
    SeasonalPattern,
    MonthlyExpectation,
    SeasonalEvent,
    SeasonalAnomalyAnalysis,
    SeasonalForecast,
    SeasonType,
    PatternStrength,
    CategoryType,
    AnomalyContext,
    KNOWN_PATTERNS,
    KNOWN_EVENTS,
)

# PHASE 0 CRITICAL FIX: DB-backed PersonalizedThresholdsService
from app.services.orchestration.personalized_thresholds_db_service import (
    PersonalizedThresholdsDBService,
    get_personalized_thresholds_db_service,
)

__all__ = [
    # CrossModuleOrchestrator
    "CrossModuleOrchestrator",
    "get_cross_module_orchestrator",
    "start_orchestrator",
    "stop_orchestrator",
    "OrchestrationAction",
    "OrchestrationDecision",
    "CascadingImpact",
    "ActionType",
    "ActionPriority",
    "ModuleType",
    # UnifiedDecisionEngine
    "UnifiedDecisionEngine",
    "get_unified_decision_engine",
    "UnifiedDecision",
    "ImpactScore",
    "ConflictType",
    "DecisionStatus",
    "ImpactDimension",
    # ExplainabilityService
    "ExplainabilityService",
    "get_explainability_service",
    "DecisionExplanation",
    "ExplanationFactor",
    "ImpactBreakdown",
    "AlternativeOption",
    "FactorType",
    "ConfidenceLevel",
    # WhatIfSimulatorService
    "WhatIfSimulatorService",
    "get_whatif_simulator",
    "ScenarioInput",
    "ScenarioResult",
    "ScenarioType",
    "TimeHorizon",
    "ImpactSeverity",
    "KPIProjection",
    "TimelinePoint",
    "ComparisonResult",
    # ProactiveInsightsService
    "ProactiveInsightsService",
    "get_proactive_insights_service",
    "ProactiveInsight",
    "ExtractedEntity",
    "EnrichedResponse",
    "InsightType",
    "InsightPriority",
    "EntityType",
    "InsightRule",
    "InsightRuleEngine",
    # PersonalizedThresholdsService
    "PersonalizedThresholdsService",
    "get_personalized_thresholds_service",
    "ThresholdRegistry",
    "UserProfile",
    "UserThreshold",
    "ThresholdDefinition",
    "ThresholdAdjustment",
    "ThresholdRecommendation",
    "ProfessionType",
    "RiskTolerance",
    "ThresholdType",
    "ThresholdCategory",
    "AdjustmentSource",
    # SeasonalityDetectionService
    "SeasonalityDetectionService",
    "get_seasonality_detection_service",
    "SeasonalPattern",
    "MonthlyExpectation",
    "SeasonalEvent",
    "SeasonalAnomalyAnalysis",
    "SeasonalForecast",
    "SeasonType",
    "PatternStrength",
    "CategoryType",
    "AnomalyContext",
    "KNOWN_PATTERNS",
    "KNOWN_EVENTS",
    # DB-backed PersonalizedThresholdsService (PHASE 0 FIX)
    "PersonalizedThresholdsDBService",
    "get_personalized_thresholds_db_service",
]
