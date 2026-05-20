# -*- coding: utf-8 -*-
"""
Pipeline Services - Zero-Touch Document Processing.

Vision 2026 Q2: Vollautomatische Dokumentenverarbeitung mit 85% Confidence-Schwelle.
"""

from app.services.pipeline.document_pipeline_orchestrator import (
    DocumentPipelineOrchestrator,
    get_document_pipeline_orchestrator,
    PipelineResult,
    PipelineDecision,
    PipelineStatus,
    PipelineStep,
    DecisionConfidence,
    AnomalyResult,
)

from app.services.pipeline.intelligent_document_matcher import (
    IntelligentDocumentMatcher,
    get_intelligent_document_matcher,
    MatchResult,
    MatchStrategy,
    DocumentRelationType,
    MatchingConfig,
)

__all__ = [
    # Pipeline Orchestrator
    "DocumentPipelineOrchestrator",
    "get_document_pipeline_orchestrator",
    "PipelineResult",
    "PipelineDecision",
    "PipelineStatus",
    "PipelineStep",
    "DecisionConfidence",
    "AnomalyResult",
    # Intelligent Document Matcher
    "IntelligentDocumentMatcher",
    "get_intelligent_document_matcher",
    "MatchResult",
    "MatchStrategy",
    "DocumentRelationType",
    "MatchingConfig",
]
