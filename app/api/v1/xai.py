# -*- coding: utf-8 -*-
"""
Explainable AI (XAI) API Endpoints.

Enterprise Feature: Transparente KI-Entscheidungen.

Endpoints:
- GET  /xai/decisions/{id}/explain    - Entscheidung erklären
- GET  /xai/decisions/{id}/confidence - Confidence-Breakdown
- GET  /xai/decisions/{id}/similar    - Ähnliche Fälle
- GET  /xai/stats                     - XAI Statistiken
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_active_user, get_db
from app.core.rate_limiting import limiter, get_user_identifier
from app.core.safe_errors import safe_error_log
from app.db.models import User
from app.services.ai.explainer import (
    get_decision_explainer,
    get_confidence_visualizer,
    get_case_comparator,
    ExplanationType,
    ConfidenceLevel,
)

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/xai", tags=["Explainable AI"])


# =============================================================================
# Pydantic Schemas - Decision Explanation
# =============================================================================


class ExplanationFactorResponse(BaseModel):
    """Ein Faktor der zur Entscheidung beiträgt."""

    name: str = Field(..., description="Name des Faktors")
    contribution: float = Field(..., description="Beitrag zur Entscheidung (-1 bis 1)")
    value: str = Field(..., description="Aktueller Wert")
    importance: float = Field(..., description="Wichtigkeit des Faktors (0-1)")
    explanation: str = Field(..., description="Menschenlesbare Erklärung")


class CounterfactualResponse(BaseModel):
    """Ein Counterfactual - was wäre wenn?"""

    scenario: str = Field(..., description="Szenario-Beschreibung")
    changes: Dict[str, str] = Field(..., description="Notwendige Änderungen")
    predicted_outcome: str = Field(..., description="Vorhergesagtes Ergebnis")
    confidence: float = Field(..., description="Konfidenz des Szenarios")


class DecisionExplanationResponse(BaseModel):
    """Erklärung einer KI-Entscheidung."""

    decision_id: str = Field(..., description="Entscheidungs-ID")
    decision_type: str = Field(..., description="Typ der Entscheidung")
    decision_value: Dict[str, Any] = Field(..., description="Entscheidungswert")
    explanation_type: str = Field(..., description="Erklärungstyp")
    summary: str = Field(..., description="Zusammenfassung der Erklärung")
    factors: List[ExplanationFactorResponse] = Field(
        default=[], description="Beitragende Faktoren"
    )
    counterfactuals: List[CounterfactualResponse] = Field(
        default=[], description="Was-wäre-wenn Szenarien"
    )
    similar_cases_count: int = Field(..., description="Anzahl ähnlicher Fälle")
    confidence: float = Field(..., description="Gesamtkonfidenz")
    audit_trail: List[str] = Field(default=[], description="Audit-Trail")
    created_at: str = Field(..., description="Erstellungszeitpunkt")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "decision_id": "550e8400-e29b-41d4-a716-446655440000",
                "decision_type": "invoice_approval",
                "explanation_type": "feature_importance",
                "summary": "Rechnung wurde automatisch genehmigt basierend auf 3 Faktoren.",
                "confidence": 0.95,
                "similar_cases_count": 47,
            }
        }
    )


# =============================================================================
# Pydantic Schemas - Confidence Visualization
# =============================================================================


class ConfidenceComponentResponse(BaseModel):
    """Eine Komponente des Confidence-Scores."""

    name: str = Field(..., description="Komponentenname")
    score: float = Field(..., description="Score (0-1)")
    weight: float = Field(..., description="Gewichtung")
    contribution: float = Field(..., description="Beitrag zum Gesamtscore")
    description: str = Field(..., description="Beschreibung")
    color: str = Field(..., description="Farbcode für Visualisierung")


class HistoricalDataPointResponse(BaseModel):
    """Historischer Confidence-Datenpunkt."""

    date: str = Field(..., description="Datum")
    confidence: float = Field(..., description="Confidence-Wert")
    decision_count: int = Field(..., description="Anzahl Entscheidungen")


class ConfidenceBreakdownResponse(BaseModel):
    """Aufschlüsselung des Confidence-Scores."""

    decision_id: str = Field(..., description="Entscheidungs-ID")
    overall_confidence: float = Field(..., description="Gesamt-Confidence")
    confidence_level: str = Field(..., description="Level (high, medium, low)")
    components: List[ConfidenceComponentResponse] = Field(
        default=[], description="Komponenten"
    )
    calibration_factor: float = Field(..., description="Kalibrierungsfaktor")
    calibrated_confidence: float = Field(..., description="Kalibrierte Confidence")
    historical_accuracy: float = Field(..., description="Historische Genauigkeit")
    historical_data: List[HistoricalDataPointResponse] = Field(
        default=[], description="Historische Daten"
    )
    interpretation: str = Field(..., description="Interpretation")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "decision_id": "550e8400-e29b-41d4-a716-446655440000",
                "overall_confidence": 0.92,
                "confidence_level": "high",
                "calibration_factor": 0.98,
                "calibrated_confidence": 0.90,
                "historical_accuracy": 0.94,
            }
        }
    )


# =============================================================================
# Pydantic Schemas - Similar Cases
# =============================================================================


class SimilarCaseResponse(BaseModel):
    """Ein ähnlicher historischer Fall."""

    case_id: str = Field(..., description="Fall-ID")
    decision_type: str = Field(..., description="Entscheidungstyp")
    similarity_score: float = Field(..., description="Ähnlichkeit (0-1)")
    outcome: str = Field(..., description="Ergebnis des Falls")
    was_correct: bool = Field(..., description="War die Entscheidung korrekt?")
    matched_features: List[str] = Field(
        default=[], description="Übereinstimmende Merkmale"
    )
    differing_features: List[str] = Field(
        default=[], description="Unterschiedliche Merkmale"
    )
    created_at: str = Field(..., description="Erstellungszeitpunkt")


class CaseComparisonResponse(BaseModel):
    """Vergleich mit ähnlichen Fällen."""

    decision_id: str = Field(..., description="Entscheidungs-ID")
    total_similar_cases: int = Field(..., description="Anzahl ähnlicher Fälle")
    similar_cases: List[SimilarCaseResponse] = Field(
        default=[], description="Ähnliche Fälle"
    )
    success_rate: float = Field(..., description="Erfolgsrate bei ähnlichen Fällen")
    avg_confidence: float = Field(..., description="Durchschnittliche Confidence")
    pattern_insights: List[str] = Field(
        default=[], description="Muster-Erkenntnisse"
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "decision_id": "550e8400-e29b-41d4-a716-446655440000",
                "total_similar_cases": 47,
                "success_rate": 0.94,
                "avg_confidence": 0.89,
            }
        }
    )


# =============================================================================
# Endpoints
# =============================================================================


@router.get(
    "/decisions/{decision_id}/explain",
    response_model=DecisionExplanationResponse,
    summary="Entscheidung erklären",
)
@limiter.limit("60/minute")
async def explain_decision(
    request: Request,
    decision_id: UUID = Path(..., description="Entscheidungs-ID"),
    include_counterfactuals: bool = Query(True, description="Counterfactuals einbeziehen"),
    include_similar_cases: bool = Query(True, description="Ähnliche Fälle einbeziehen"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> DecisionExplanationResponse:
    """
    Erklärt eine KI-Entscheidung.

    Liefert:
    - Zusammenfassung der Entscheidung
    - Beitragende Faktoren mit Gewichtung
    - Was-wäre-wenn Szenarien (Counterfactuals)
    - Referenz zu ähnlichen Fällen

    Returns:
        DecisionExplanationResponse
    """
    explainer = get_decision_explainer()

    try:
        explanation = await explainer.explain(
            db=db,
            decision_id=decision_id,
            include_counterfactuals=include_counterfactuals,
            include_similar_cases=include_similar_cases,
        )

        if not explanation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Entscheidung nicht gefunden",
            )

        return DecisionExplanationResponse(
            decision_id=str(explanation["decision_id"]),
            decision_type=explanation["decision_type"],
            decision_value=explanation["decision_value"],
            explanation_type=explanation["explanation_type"],
            summary=explanation["summary"],
            factors=[
                ExplanationFactorResponse(
                    name=f["name"],
                    contribution=f["contribution"],
                    value=f["value"],
                    importance=f["importance"],
                    explanation=f["explanation"],
                )
                for f in explanation.get("factors", [])
            ],
            counterfactuals=[
                CounterfactualResponse(
                    scenario=cf["scenario"],
                    changes=cf["changes"],
                    predicted_outcome=cf["predicted_outcome"],
                    confidence=cf["confidence"],
                )
                for cf in explanation.get("counterfactuals", [])
            ],
            similar_cases_count=explanation.get("similar_cases_count", 0),
            confidence=explanation["confidence"],
            audit_trail=explanation.get("audit_trail", []),
            created_at=explanation["created_at"],
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("explain_decision_failed", **safe_error_log(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erklärung konnte nicht erstellt werden",
        )


@router.get(
    "/decisions/{decision_id}/confidence",
    response_model=ConfidenceBreakdownResponse,
    summary="Confidence-Breakdown abrufen",
)
@limiter.limit("60/minute")
async def get_confidence_breakdown(
    request: Request,
    decision_id: UUID = Path(..., description="Entscheidungs-ID"),
    include_history: bool = Query(True, description="Historische Daten einbeziehen"),
    history_days: int = Query(30, ge=1, le=90, description="Tage für Historie"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> ConfidenceBreakdownResponse:
    """
    Zeigt die Aufschlüsselung des Confidence-Scores.

    Returns:
        ConfidenceBreakdownResponse mit Komponenten und Historie
    """
    visualizer = get_confidence_visualizer()

    try:
        breakdown = await visualizer.breakdown(
            db=db,
            decision_id=decision_id,
            include_history=include_history,
            history_days=history_days,
        )

        if not breakdown:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Entscheidung nicht gefunden",
            )

        return ConfidenceBreakdownResponse(
            decision_id=str(breakdown["decision_id"]),
            overall_confidence=breakdown["overall_confidence"],
            confidence_level=breakdown["confidence_level"],
            components=[
                ConfidenceComponentResponse(
                    name=c["name"],
                    score=c["score"],
                    weight=c["weight"],
                    contribution=c["contribution"],
                    description=c["description"],
                    color=c["color"],
                )
                for c in breakdown.get("components", [])
            ],
            calibration_factor=breakdown["calibration_factor"],
            calibrated_confidence=breakdown["calibrated_confidence"],
            historical_accuracy=breakdown["historical_accuracy"],
            historical_data=[
                HistoricalDataPointResponse(
                    date=h["date"],
                    confidence=h["confidence"],
                    decision_count=h["decision_count"],
                )
                for h in breakdown.get("historical_data", [])
            ],
            interpretation=breakdown["interpretation"],
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("get_confidence_breakdown_failed", **safe_error_log(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Confidence-Breakdown konnte nicht abgerufen werden",
        )


@router.get(
    "/decisions/{decision_id}/similar",
    response_model=CaseComparisonResponse,
    summary="Ähnliche Fälle finden",
)
@limiter.limit("30/minute")
async def find_similar_cases(
    request: Request,
    decision_id: UUID = Path(..., description="Entscheidungs-ID"),
    max_cases: int = Query(10, ge=1, le=50, description="Maximale Anzahl"),
    min_similarity: float = Query(0.7, ge=0.5, le=1.0, description="Minimale Ähnlichkeit"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> CaseComparisonResponse:
    """
    Findet und vergleicht ähnliche historische Fälle.

    Returns:
        CaseComparisonResponse mit ähnlichen Fällen und Insights
    """
    comparator = get_case_comparator()

    try:
        comparison = await comparator.compare(
            db=db,
            decision_id=decision_id,
            max_cases=max_cases,
            min_similarity=min_similarity,
        )

        if not comparison:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Entscheidung nicht gefunden",
            )

        return CaseComparisonResponse(
            decision_id=str(comparison["decision_id"]),
            total_similar_cases=comparison["total_similar_cases"],
            similar_cases=[
                SimilarCaseResponse(
                    case_id=sc["case_id"],
                    decision_type=sc["decision_type"],
                    similarity_score=sc["similarity_score"],
                    outcome=sc["outcome"],
                    was_correct=sc["was_correct"],
                    matched_features=sc.get("matched_features", []),
                    differing_features=sc.get("differing_features", []),
                    created_at=sc["created_at"],
                )
                for sc in comparison.get("similar_cases", [])
            ],
            success_rate=comparison["success_rate"],
            avg_confidence=comparison["avg_confidence"],
            pattern_insights=comparison.get("pattern_insights", []),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("find_similar_cases_failed", **safe_error_log(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Ähnliche Fälle konnten nicht gefunden werden",
        )


@router.get(
    "/stats",
    summary="XAI Statistiken",
)
@limiter.limit("30/minute")
async def get_xai_stats(
    request: Request,
    days: int = Query(30, ge=1, le=365, description="Tage für Statistik"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Dict[str, Any]:
    """
    Gibt XAI-Nutzungsstatistiken zurück.

    Returns:
        Statistiken über erklärte Entscheidungen
    """
    explainer = get_decision_explainer()

    try:
        stats = await explainer.get_stats(
            db=db,
            company_id=current_user.company_id,
            days=days,
        )

        return {
            "period_days": days,
            "total_explanations_requested": stats.get("total_requests", 0),
            "by_decision_type": stats.get("by_type", {}),
            "avg_factors_per_explanation": stats.get("avg_factors", 0),
            "counterfactuals_generated": stats.get("counterfactuals", 0),
            "similar_cases_found": stats.get("similar_cases", 0),
            "user_feedback": {
                "helpful": stats.get("feedback_helpful", 0),
                "not_helpful": stats.get("feedback_not_helpful", 0),
            },
            "most_common_factors": stats.get("common_factors", []),
        }
    except Exception as e:
        logger.error("get_xai_stats_failed", **safe_error_log(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Statistiken konnten nicht abgerufen werden",
        )


@router.post(
    "/decisions/{decision_id}/feedback",
    summary="Feedback zur Erklärung geben",
)
@limiter.limit("30/minute")
async def submit_explanation_feedback(
    request: Request,
    decision_id: UUID = Path(..., description="Entscheidungs-ID"),
    helpful: bool = Query(..., description="War die Erklärung hilfreich?"),
    comment: Optional[str] = Query(None, max_length=500, description="Kommentar"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Dict[str, Any]:
    """
    Gibt Feedback zur Qualität einer Erklärung.

    Returns:
        Erfolgsmeldung
    """
    explainer = get_decision_explainer()

    try:
        await explainer.record_feedback(
            db=db,
            decision_id=decision_id,
            user_id=current_user.id,
            helpful=helpful,
            comment=comment,
        )

        return {
            "success": True,
            "message": "Feedback wurde gespeichert",
            "decision_id": str(decision_id),
        }
    except Exception as e:
        logger.error("submit_feedback_failed", **safe_error_log(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Feedback konnte nicht gespeichert werden",
        )
