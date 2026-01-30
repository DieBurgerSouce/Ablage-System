# -*- coding: utf-8 -*-
"""
Explainable AI (XAI) Services.

Enterprise Feature: Transparente KI-Entscheidungen.

Module:
- decision_explainer: "Warum wurde X entschieden?"
- confidence_visualizer: Confidence-Score Breakdown
- case_comparator: "Basierend auf 47 aehnlichen Faellen"
"""

from app.services.ai.explainer.decision_explainer import (
    DecisionExplainer,
    get_decision_explainer,
    DecisionExplanation,
    ExplanationFactor,
    ExplanationType,
)

from app.services.ai.explainer.confidence_visualizer import (
    ConfidenceVisualizer,
    get_confidence_visualizer,
    ConfidenceBreakdown,
    ConfidenceComponent,
    ConfidenceLevel,
)

from app.services.ai.explainer.case_comparator import (
    CaseComparator,
    get_case_comparator,
    SimilarCase,
    CaseComparison,
    SimilarityScore,
)

__all__ = [
    # Decision Explainer
    "DecisionExplainer",
    "get_decision_explainer",
    "DecisionExplanation",
    "ExplanationFactor",
    "ExplanationType",
    # Confidence Visualizer
    "ConfidenceVisualizer",
    "get_confidence_visualizer",
    "ConfidenceBreakdown",
    "ConfidenceComponent",
    "ConfidenceLevel",
    # Case Comparator
    "CaseComparator",
    "get_case_comparator",
    "SimilarCase",
    "CaseComparison",
    "SimilarityScore",
]
