# -*- coding: utf-8 -*-
"""
Orchestration API Endpoints.

Enterprise Feature: Cross-Module Orchestration und Unified Decision Engine.

Endpoints:
- GET  /orchestration/decisions        - Priorisierte Entscheidungen abrufen
- GET  /orchestration/decisions/{id}   - Einzelne Entscheidung abrufen
- POST /orchestration/decisions/{id}/approve  - Entscheidung genehmigen
- POST /orchestration/decisions/{id}/reject   - Entscheidung ablehnen
- GET  /orchestration/summary          - Entscheidungs-Zusammenfassung
- GET  /orchestration/metrics          - System-Metriken
- GET  /orchestration/pending-actions  - Ausstehende Aktionen
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, status
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
import re

from app.api.dependencies import get_current_active_user
from app.core.rate_limiting import limiter, get_user_identifier
from app.db.models import User
from app.services.orchestration import (
    get_cross_module_orchestrator,
    get_unified_decision_engine,
    get_explainability_service,
    get_whatif_simulator,
    DecisionStatus,
    ConfidenceLevel,
    ScenarioType,
    ScenarioInput,
)
from decimal import Decimal

router = APIRouter(prefix="/orchestration", tags=["Orchestration"])


# =============================================================================
# Pydantic Schemas
# =============================================================================

class ImpactScoreResponse(BaseModel):
    """Impact-Score einer Entscheidung."""
    financial_impact: float = Field(..., description="Finanzielle Auswirkung in EUR")
    risk_reduction: float = Field(..., description="Risikoreduktion (0-100)")
    compliance_urgency: float = Field(..., description="Compliance-Dringlichkeit (0-100)")
    opportunity_value: float = Field(..., description="Opportunitaetswert in EUR")
    convenience_gain: float = Field(..., description="Komfortgewinn (0-100)")
    total_score: float = Field(..., description="Gewichteter Gesamt-Score")

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "financial_impact": 500.0,
            "risk_reduction": 30.0,
            "compliance_urgency": 80.0,
            "opportunity_value": 200.0,
            "convenience_gain": 10.0,
            "total_score": 52.5,
        }
    })


class DecisionResponse(BaseModel):
    """Eine Entscheidung aus dem System."""
    id: str = Field(..., description="Entscheidungs-ID")
    title: str = Field(..., description="Titel der Entscheidung")
    description: str = Field(..., description="Beschreibung")
    reasoning: str = Field(..., description="Begruendung")
    primary_module: str = Field(..., description="Primaeres Modul")
    affected_modules: List[str] = Field(..., description="Betroffene Module")
    impact_score: ImpactScoreResponse = Field(..., description="Impact-Score")
    status: str = Field(..., description="Status der Entscheidung")
    conflicts_with: List[str] = Field(default=[], description="IDs konfliktierender Entscheidungen")
    conflict_type: Optional[str] = Field(None, description="Art des Konflikts")
    conflict_resolution: str = Field(default="", description="Konfliktloesung")
    created_at: str = Field(..., description="Erstellungszeitpunkt")
    processed_at: Optional[str] = Field(None, description="Verarbeitungszeitpunkt")
    source_actions_count: int = Field(..., description="Anzahl zugrunde liegender Aktionen")

    class Config:
        json_schema_extra = {
            "example": {
                "id": "550e8400-e29b-41d4-a716-446655440000",
                "title": "Versicherungsluecke schliessen",
                "description": "Fuer das Fahrzeug wurde eine Deckungsluecke erkannt.",
                "reasoning": "Versicherungsluecke 'Teilkasko' erkannt",
                "primary_module": "insurance",
                "affected_modules": ["insurance", "vehicle"],
                "impact_score": {
                    "financial_impact": 500.0,
                    "risk_reduction": 50.0,
                    "compliance_urgency": 0.0,
                    "opportunity_value": 0.0,
                    "convenience_gain": 0.0,
                    "total_score": 35.0,
                },
                "status": "pending",
                "conflicts_with": [],
                "conflict_type": None,
                "conflict_resolution": "",
                "created_at": "2024-01-15T10:30:00Z",
                "processed_at": None,
                "source_actions_count": 2,
            }
        }


class DecisionSummaryResponse(BaseModel):
    """Zusammenfassung aller Entscheidungen."""
    total_decisions: int = Field(..., description="Gesamtzahl Entscheidungen")
    status_distribution: Dict[str, int] = Field(..., description="Verteilung nach Status")
    module_distribution: Dict[str, int] = Field(..., description="Verteilung nach Modul")
    top_decisions: List[Dict[str, Any]] = Field(..., description="Top-Entscheidungen nach Impact")
    conflict_count: int = Field(..., description="Anzahl erkannter Konflikte")
    potential_financial_impact: float = Field(..., description="Potenzieller Gesamt-Impact in EUR")
    average_impact_score: float = Field(..., description="Durchschnittlicher Impact-Score")


class OrchestratorMetricsResponse(BaseModel):
    """Metriken des Orchestrators."""
    pending_actions_count: int = Field(..., description="Ausstehende Aktionen")
    decision_history_count: int = Field(..., description="Entscheidungen in History")
    active_entity_actions: Dict[str, List[str]] = Field(..., description="Aktive Entity-Aktionen")


class DecisionEngineMetricsResponse(BaseModel):
    """Metriken der Decision Engine."""
    queue_size: int = Field(..., description="Groesse der Queue")
    pending_count: int = Field(..., description="Ausstehende Entscheidungen")
    approved_count: int = Field(..., description="Genehmigte Entscheidungen")
    processed_count: int = Field(..., description="Verarbeitete Entscheidungen")
    known_conflicts: int = Field(..., description="Bekannte Konflikte")


class CombinedMetricsResponse(BaseModel):
    """Kombinierte Metriken."""
    orchestrator: OrchestratorMetricsResponse
    decision_engine: DecisionEngineMetricsResponse


class ActionResponse(BaseModel):
    """Eine ausstehende Aktion."""
    id: str = Field(..., description="Aktions-ID")
    action_type: str = Field(..., description="Typ der Aktion")
    priority: str = Field(..., description="Prioritaet")
    source_module: Optional[str] = Field(None, description="Quell-Modul")
    target_entity_id: Optional[str] = Field(None, description="Ziel-Entity-ID")
    target_entity_type: Optional[str] = Field(None, description="Ziel-Entity-Typ")
    reason: str = Field(..., description="Begruendung")
    status: str = Field(..., description="Status")
    created_at: str = Field(..., description="Erstellungszeitpunkt")


class RejectDecisionRequest(BaseModel):
    """Request zum Ablehnen einer Entscheidung."""
    reason: str = Field(default="", max_length=1000, description="Begruendung fuer Ablehnung")

    @field_validator("reason")
    @classmethod
    def validate_reason(cls, v: str) -> str:
        """Validiert und bereinigt die Ablehnungsbegruendung."""
        # Strip whitespace
        v = v.strip()
        # Prevent potential XSS/Injection - only allow safe characters
        if v and not re.match(r'^[\w\s\-.,!?äöüÄÖÜß()]+$', v, re.UNICODE):
            raise ValueError(
                "Begruendung enthaelt ungueltige Zeichen. "
                "Erlaubt sind: Buchstaben, Zahlen, Leerzeichen, -.!?()"
            )
        return v


# =============================================================================
# API Endpoints
# =============================================================================

@limiter.limit("60/minute", key_func=get_user_identifier)
@router.get(
    "/decisions",
    response_model=List[DecisionResponse],
    summary="Priorisierte Entscheidungen abrufen",
    description="""
    Gibt die priorisierten Entscheidungen zurueck.

    Die Entscheidungen werden nach Impact-Score sortiert (hoechster zuerst).
    Konflikte werden automatisch erkannt und aufgeloest.

    **Features:**
    - Multi-dimensionales Impact-Scoring (Finanzen, Risiko, Compliance, ...)
    - Automatische Konflikterkennung zwischen Entscheidungen
    - Filterung nach Mindest-Score

    **Enterprise Feature** - Teil der Cross-Module Orchestration.
    """,
)
async def get_prioritized_decisions(
    request: Request,
    limit: int = Query(default=10, ge=1, le=100, description="Maximale Anzahl"),
    min_score: Optional[float] = Query(default=None, ge=0, description="Mindest-Impact-Score"),
    current_user: User = Depends(get_current_active_user),
) -> List[DecisionResponse]:
    """Gibt priorisierte Entscheidungen zurueck."""
    engine = get_unified_decision_engine()

    decisions = await engine.get_prioritized_decisions(
        user_id=current_user.id,
        limit=limit,
        min_score=min_score,
    )

    return [
        DecisionResponse(**decision.to_dict())
        for decision in decisions
    ]


@limiter.limit("60/minute", key_func=get_user_identifier)
@router.get(
    "/decisions/{decision_id}",
    response_model=DecisionResponse,
    summary="Einzelne Entscheidung abrufen",
)
async def get_decision(
    request: Request,
    decision_id: UUID,
    current_user: User = Depends(get_current_active_user),
) -> DecisionResponse:
    """Gibt eine einzelne Entscheidung zurueck."""
    engine = get_unified_decision_engine()

    # In Queue suchen
    async with engine._queue_lock:
        for decision in engine._decision_queue:
            if decision.id == decision_id:
                return DecisionResponse(**decision.to_dict())

    # In History suchen
    for decision in engine._processed_decisions:
        if decision.id == decision_id:
            return DecisionResponse(**decision.to_dict())

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Entscheidung nicht gefunden",
    )


@limiter.limit("10/minute", key_func=get_user_identifier)
@router.post(
    "/decisions/{decision_id}/approve",
    response_model=Dict[str, Any],
    summary="Entscheidung genehmigen",
    description="Genehmigt eine Entscheidung zur Ausfuehrung.",
)
async def approve_decision(
    request: Request,
    decision_id: UUID,
    current_user: User = Depends(get_current_active_user),
) -> Dict[str, Any]:
    """Genehmigt eine Entscheidung."""
    engine = get_unified_decision_engine()

    success = await engine.approve_decision(decision_id)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Entscheidung nicht gefunden oder bereits verarbeitet",
        )

    return {
        "status": "approved",
        "decision_id": str(decision_id),
        "message": "Entscheidung wurde genehmigt und wird ausgefuehrt",
    }


@limiter.limit("10/minute", key_func=get_user_identifier)
@router.post(
    "/decisions/{decision_id}/reject",
    response_model=Dict[str, Any],
    summary="Entscheidung ablehnen",
    description="Lehnt eine Entscheidung ab.",
)
async def reject_decision(
    fastapi_request: Request,
    decision_id: UUID,
    request: RejectDecisionRequest,
    current_user: User = Depends(get_current_active_user),
) -> Dict[str, Any]:
    """Lehnt eine Entscheidung ab."""
    engine = get_unified_decision_engine()

    success = await engine.reject_decision(decision_id, request.reason)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Entscheidung nicht gefunden oder bereits verarbeitet",
        )

    return {
        "status": "rejected",
        "decision_id": str(decision_id),
        "reason": request.reason,
        "message": "Entscheidung wurde abgelehnt",
    }


@limiter.limit("60/minute", key_func=get_user_identifier)
@router.get(
    "/summary",
    response_model=DecisionSummaryResponse,
    summary="Entscheidungs-Zusammenfassung",
    description="""
    Gibt eine Zusammenfassung aller Entscheidungen zurueck.

    Ideal fuer Dashboard-Anzeige:
    - Status-Verteilung (pending, approved, rejected, ...)
    - Modul-Verteilung (finance, insurance, property, ...)
    - Top-Entscheidungen nach Impact
    - Konflikt-Statistik
    - Potentieller Gesamt-Impact
    """,
)
async def get_decision_summary(
    request: Request,
    current_user: User = Depends(get_current_active_user),
) -> DecisionSummaryResponse:
    """Gibt Entscheidungs-Zusammenfassung zurueck."""
    engine = get_unified_decision_engine()

    summary = await engine.get_decision_summary(user_id=current_user.id)

    return DecisionSummaryResponse(**summary)


@limiter.limit("60/minute", key_func=get_user_identifier)
@router.get(
    "/metrics",
    response_model=CombinedMetricsResponse,
    summary="System-Metriken abrufen",
    description="Gibt Metriken des Orchestrators und der Decision Engine zurueck.",
)
async def get_orchestration_metrics(
    request: Request,
    current_user: User = Depends(get_current_active_user),
) -> CombinedMetricsResponse:
    """Gibt Orchestration-Metriken zurueck."""
    orchestrator = get_cross_module_orchestrator()
    engine = get_unified_decision_engine()

    orch_metrics = await orchestrator.get_metrics()
    engine_metrics = await engine.get_metrics()

    return CombinedMetricsResponse(
        orchestrator=OrchestratorMetricsResponse(**orch_metrics),
        decision_engine=DecisionEngineMetricsResponse(**engine_metrics),
    )


@limiter.limit("60/minute", key_func=get_user_identifier)
@router.get(
    "/pending-actions",
    response_model=List[ActionResponse],
    summary="Ausstehende Aktionen abrufen",
    description="Gibt alle ausstehenden Orchestrierungs-Aktionen zurueck.",
)
async def get_pending_actions(
    request: Request,
    current_user: User = Depends(get_current_active_user),
) -> List[ActionResponse]:
    """Gibt ausstehende Aktionen zurueck."""
    orchestrator = get_cross_module_orchestrator()

    actions = orchestrator.get_pending_actions()

    return [
        ActionResponse(
            id=str(action.id),
            action_type=action.action_type.value,
            priority=action.priority.value,
            source_module=action.source_module.value if action.source_module else None,
            target_entity_id=str(action.target_entity_id) if action.target_entity_id else None,
            target_entity_type=action.target_entity_type,
            reason=action.reason,
            status=action.status,
            created_at=action.created_at.isoformat(),
        )
        for action in actions
    ]


@limiter.limit("5/minute", key_func=get_user_identifier)
@router.post(
    "/execute-approved",
    response_model=Dict[str, Any],
    summary="Genehmigte Entscheidungen ausfuehren",
    description="Fuehrt alle genehmigten Entscheidungen aus. Normalerweise via Celery Beat.",
)
async def execute_approved_decisions(
    request: Request,
    current_user: User = Depends(get_current_active_user),
) -> Dict[str, Any]:
    """Fuehrt genehmigte Entscheidungen aus."""
    engine = get_unified_decision_engine()

    executed_count = await engine.execute_approved_decisions()

    return {
        "status": "success",
        "executed_count": executed_count,
        "message": f"{executed_count} Entscheidungen wurden ausgefuehrt",
    }


@limiter.limit("60/minute", key_func=get_user_identifier)
@router.get(
    "/decision-history",
    response_model=List[DecisionResponse],
    summary="Entscheidungs-History abrufen",
    description="Gibt die letzten verarbeiteten Entscheidungen zurueck.",
)
async def get_decision_history(
    request: Request,
    limit: int = Query(default=20, ge=1, le=100, description="Maximale Anzahl"),
    current_user: User = Depends(get_current_active_user),
) -> List[DecisionResponse]:
    """Gibt Entscheidungs-History zurueck."""
    orchestrator = get_cross_module_orchestrator()

    decisions = orchestrator.get_decision_history(limit=limit)

    # OrchestrationDecision zu DecisionResponse konvertieren
    results = []
    for decision in decisions:
        # Vereinfachte Konvertierung
        if decision.actions:
            first_action = decision.actions[0]
            results.append(DecisionResponse(
                id=str(decision.decision_id),
                title=first_action.action_data.get("title", "Systemempfehlung"),
                description=first_action.impact_description or "",
                reasoning=decision.reasoning,
                primary_module=first_action.source_module.value if first_action.source_module else "system",
                affected_modules=[],
                impact_score=ImpactScoreResponse(
                    financial_impact=0,
                    risk_reduction=0,
                    compliance_urgency=0,
                    opportunity_value=0,
                    convenience_gain=0,
                    total_score=decision.confidence * 100,
                ),
                status="executed",
                conflicts_with=[],
                conflict_type=None,
                conflict_resolution="",
                created_at=decision.created_at.isoformat(),
                processed_at=None,
                source_actions_count=len(decision.actions),
            ))

    return results


# =============================================================================
# Explainability Schemas
# =============================================================================

class ExplanationFactorResponse(BaseModel):
    """Ein Erklaerungsfaktor."""
    factor_type: str = Field(..., description="Typ des Faktors")
    name: str = Field(..., description="Name des Faktors")
    description: str = Field(..., description="Beschreibung")
    current_value: Optional[float] = Field(None, description="Aktueller Wert")
    reference_value: Optional[float] = Field(None, description="Referenzwert")
    impact_direction: str = Field(..., description="Richtung des Impacts (positive/negative/neutral)")
    impact_weight: float = Field(..., description="Gewicht des Impacts")


class ImpactBreakdownResponse(BaseModel):
    """Aufschluesselung der Auswirkungen."""
    immediate_savings: float = Field(..., description="Sofortige Ersparnis in EUR")
    annual_savings: float = Field(..., description="Jaehrliche Ersparnis in EUR")
    one_time_cost: float = Field(..., description="Einmalige Kosten in EUR")
    risk_before: float = Field(..., description="Risiko vorher (0-100)")
    risk_after: float = Field(..., description="Risiko nachher (0-100)")
    net_benefit: float = Field(..., description="Netto-Nutzen in EUR")


class AlternativeOptionResponse(BaseModel):
    """Eine alternative Option."""
    title: str = Field(..., description="Titel der Alternative")
    description: str = Field(..., description="Beschreibung")
    impact_comparison: str = Field(..., description="Vergleich zum Original")
    trade_offs: List[str] = Field(default=[], description="Trade-offs")


class DecisionExplanationResponse(BaseModel):
    """Vollstaendige Erklaerung einer Entscheidung."""
    headline: str = Field(..., description="Praegnante Ueberschrift")
    summary: str = Field(..., description="Zusammenfassung in 2-3 Saetzen")
    main_reason: str = Field(..., description="Hauptgrund")
    factors: List[ExplanationFactorResponse] = Field(default=[], description="Erklaerungsfaktoren")
    impact_breakdown: ImpactBreakdownResponse = Field(..., description="Impact-Aufschluesselung")
    alternatives: List[AlternativeOptionResponse] = Field(default=[], description="Alternativen")
    confidence_level: str = Field(..., description="Konfidenz-Level")
    confidence_percentage: float = Field(..., description="Konfidenz in Prozent")
    data_basis: str = Field(..., description="Datenbasis der Erklaerung")

    class Config:
        json_schema_extra = {
            "example": {
                "headline": "Kredit-Refinanzierung spart 15.600 EUR",
                "summary": "Bei aktuellem Marktzins von 3.1% lohnt sich eine Refinanzierung.",
                "main_reason": "Zinsdifferenz von 1.1 Prozentpunkten",
                "factors": [
                    {
                        "factor_type": "financial",
                        "name": "Zinsdifferenz",
                        "description": "Aktueller Zins vs. Marktzins",
                        "current_value": 4.2,
                        "reference_value": 3.1,
                        "impact_direction": "positive",
                        "impact_weight": 0.8,
                    }
                ],
                "impact_breakdown": {
                    "immediate_savings": 0,
                    "annual_savings": 1300,
                    "one_time_cost": 500,
                    "risk_before": 20,
                    "risk_after": 15,
                    "net_benefit": 15100,
                },
                "alternatives": [],
                "confidence_level": "high",
                "confidence_percentage": 89.5,
                "data_basis": "24 Monate historische Daten",
            }
        }


class HealthScoreBreakdownRequest(BaseModel):
    """Request fuer Health Score Breakdown."""
    health_score: float = Field(..., ge=0, le=100, description="Aktueller Health Score")
    dti_ratio: Optional[float] = Field(
        None,
        ge=0,
        le=200,
        description="Debt-to-Income Ratio"
    )
    savings_rate: Optional[float] = Field(
        None,
        ge=-100,
        le=100,
        description="Sparquote"
    )
    emergency_fund_months: Optional[float] = Field(
        None,
        ge=0,
        le=120,
        description="Notgroschen in Monaten"
    )
    diversification_score: Optional[float] = Field(
        None,
        ge=0,
        le=100,
        description="Diversifikations-Score"
    )
    insurance_coverage: Optional[float] = Field(
        None,
        ge=0,
        le=100,
        description="Versicherungsabdeckung"
    )
    liquidity_ratio: Optional[float] = Field(
        None,
        ge=0,
        le=1000,
        description="Liquiditaetsquote"
    )


class EarlyWarningExplainRequest(BaseModel):
    """Request fuer Early Warning Erklaerung."""
    kpi_name: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Name des KPI"
    )
    current_value: float = Field(..., ge=-1e12, le=1e12, description="Aktueller Wert")
    projected_value: float = Field(..., ge=-1e12, le=1e12, description="Projizierter Wert")
    threshold_value: float = Field(..., ge=-1e12, le=1e12, description="Schwellenwert")
    months_until_breach: int = Field(
        ...,
        ge=0,
        le=120,
        description="Monate bis Schwellenwert-Verletzung"
    )
    trend_direction: str = Field(..., description="Trend-Richtung (up/down/stable)")

    @field_validator("kpi_name")
    @classmethod
    def validate_kpi_name(cls, v: str) -> str:
        """Validiert den KPI-Namen."""
        v = v.strip()
        # Nur alphanumerische Zeichen und Unterstriche
        if not re.match(r'^[a-zA-Z][a-zA-Z0-9_]*$', v):
            raise ValueError(
                "KPI-Name muss mit Buchstabe beginnen und darf nur "
                "Buchstaben, Zahlen und Unterstriche enthalten"
            )
        return v

    @field_validator("trend_direction")
    @classmethod
    def validate_trend_direction(cls, v: str) -> str:
        """Validiert die Trend-Richtung."""
        allowed = {"up", "down", "stable"}
        v_lower = v.lower().strip()
        if v_lower not in allowed:
            raise ValueError(
                f"Trend-Richtung muss einer der folgenden sein: {', '.join(allowed)}"
            )
        return v_lower


# =============================================================================
# Explainability Endpoints
# =============================================================================

@limiter.limit("60/minute", key_func=get_user_identifier)
@router.get(
    "/explain/recommendation/{recommendation_id}",
    response_model=DecisionExplanationResponse,
    summary="Empfehlung erklaeren",
    description="""
    Generiert eine ausfuehrliche Erklaerung fuer eine Empfehlung.

    Die Erklaerung enthaelt:
    - **Headline**: Praegnante Zusammenfassung mit konkreten Zahlen
    - **Faktoren**: Alle Faktoren die zur Empfehlung gefuehrt haben
    - **Impact-Breakdown**: Konkrete finanzielle Auswirkungen
    - **Alternativen**: Moegliche andere Optionen mit Trade-offs
    - **Konfidenz**: Wie sicher ist die Empfehlung?

    **Enterprise Feature** - Teil des Explainability-Systems.
    """,
)
async def explain_recommendation(
    request: Request,
    recommendation_id: UUID,
    current_user: User = Depends(get_current_active_user),
) -> DecisionExplanationResponse:
    """Erklaert eine Empfehlung im Detail."""
    explainability = get_explainability_service()

    # Empfehlung aus Engine holen
    engine = get_unified_decision_engine()
    decision = None

    async with engine._queue_lock:
        for d in engine._decision_queue:
            if d.id == recommendation_id:
                decision = d
                break

    if not decision:
        for d in engine._processed_decisions:
            if d.id == recommendation_id:
                decision = d
                break

    if not decision:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Empfehlung nicht gefunden",
        )

    # Daten fuer Erklaerung aufbereiten
    recommendation_data = {
        "title": decision.title,
        "category": decision.primary_module.value if decision.primary_module else "system",
        "potential_savings": float(decision.impact_score.financial_impact),
        "reasoning": decision.reasoning,
        "impact_score": decision.impact_score.total_score,
    }

    explanation = await explainability.explain_recommendation(
        recommendation_id=str(recommendation_id),
        recommendation_data=recommendation_data,
    )

    return DecisionExplanationResponse(
        headline=explanation.headline,
        summary=explanation.summary,
        main_reason=explanation.main_reason,
        factors=[
            ExplanationFactorResponse(
                factor_type=f.factor_type.value,
                name=f.name,
                description=f.description,
                current_value=f.current_value,
                reference_value=f.reference_value,
                impact_direction=f.impact_direction.value,
                impact_weight=f.impact_weight,
            )
            for f in explanation.factors
        ],
        impact_breakdown=ImpactBreakdownResponse(
            immediate_savings=float(explanation.impact_breakdown.immediate_savings),
            annual_savings=float(explanation.impact_breakdown.annual_savings),
            one_time_cost=float(explanation.impact_breakdown.one_time_cost),
            risk_before=explanation.impact_breakdown.risk_before,
            risk_after=explanation.impact_breakdown.risk_after,
            net_benefit=float(explanation.impact_breakdown.net_benefit),
        ),
        alternatives=[
            AlternativeOptionResponse(
                title=a.title,
                description=a.description,
                impact_comparison=a.impact_comparison,
                trade_offs=a.trade_offs,
            )
            for a in explanation.alternatives
        ],
        confidence_level=explanation.confidence_level.value,
        confidence_percentage=explanation.confidence_percentage,
        data_basis=explanation.data_basis,
    )


@limiter.limit("60/minute", key_func=get_user_identifier)
@router.post(
    "/explain/early-warning",
    response_model=DecisionExplanationResponse,
    summary="Early Warning erklaeren",
    description="""
    Generiert eine Erklaerung fuer eine Fruehwarnung.

    Erklaert WARUM das System eine Warnung ausgibt und WAS der User tun kann.
    """,
)
async def explain_early_warning(
    fastapi_request: Request,
    request: EarlyWarningExplainRequest,
    current_user: User = Depends(get_current_active_user),
) -> DecisionExplanationResponse:
    """Erklaert eine Early Warning im Detail."""
    explainability = get_explainability_service()

    warning_data = {
        "kpi_name": request.kpi_name,
        "current_value": request.current_value,
        "projected_value": request.projected_value,
        "threshold_value": request.threshold_value,
        "months_until_breach": request.months_until_breach,
        "trend_direction": request.trend_direction,
    }

    explanation = await explainability.explain_early_warning(warning_data)

    return DecisionExplanationResponse(
        headline=explanation.headline,
        summary=explanation.summary,
        main_reason=explanation.main_reason,
        factors=[
            ExplanationFactorResponse(
                factor_type=f.factor_type.value,
                name=f.name,
                description=f.description,
                current_value=f.current_value,
                reference_value=f.reference_value,
                impact_direction=f.impact_direction.value,
                impact_weight=f.impact_weight,
            )
            for f in explanation.factors
        ],
        impact_breakdown=ImpactBreakdownResponse(
            immediate_savings=float(explanation.impact_breakdown.immediate_savings),
            annual_savings=float(explanation.impact_breakdown.annual_savings),
            one_time_cost=float(explanation.impact_breakdown.one_time_cost),
            risk_before=explanation.impact_breakdown.risk_before,
            risk_after=explanation.impact_breakdown.risk_after,
            net_benefit=float(explanation.impact_breakdown.net_benefit),
        ),
        alternatives=[
            AlternativeOptionResponse(
                title=a.title,
                description=a.description,
                impact_comparison=a.impact_comparison,
                trade_offs=a.trade_offs,
            )
            for a in explanation.alternatives
        ],
        confidence_level=explanation.confidence_level.value,
        confidence_percentage=explanation.confidence_percentage,
        data_basis=explanation.data_basis,
    )


@limiter.limit("60/minute", key_func=get_user_identifier)
@router.post(
    "/explain/health-score",
    response_model=DecisionExplanationResponse,
    summary="Health Score erklaeren",
    description="""
    Erklaert WARUM der Health Score einen bestimmten Wert hat.

    Zeigt:
    - Welche Faktoren positiv/negativ beitragen
    - Wie viel Punkte jeder Faktor kostet/bringt
    - Was getan werden kann um den Score zu verbessern
    """,
)
async def explain_health_score(
    fastapi_request: Request,
    request: HealthScoreBreakdownRequest,
    current_user: User = Depends(get_current_active_user),
) -> DecisionExplanationResponse:
    """Erklaert den Health Score im Detail."""
    explainability = get_explainability_service()

    score_data = {
        "health_score": request.health_score,
        "dti_ratio": request.dti_ratio,
        "savings_rate": request.savings_rate,
        "emergency_fund_months": request.emergency_fund_months,
        "diversification_score": request.diversification_score,
        "insurance_coverage": request.insurance_coverage,
        "liquidity_ratio": request.liquidity_ratio,
    }

    explanation = await explainability.explain_health_score(score_data)

    return DecisionExplanationResponse(
        headline=explanation.headline,
        summary=explanation.summary,
        main_reason=explanation.main_reason,
        factors=[
            ExplanationFactorResponse(
                factor_type=f.factor_type.value,
                name=f.name,
                description=f.description,
                current_value=f.current_value,
                reference_value=f.reference_value,
                impact_direction=f.impact_direction.value,
                impact_weight=f.impact_weight,
            )
            for f in explanation.factors
        ],
        impact_breakdown=ImpactBreakdownResponse(
            immediate_savings=float(explanation.impact_breakdown.immediate_savings),
            annual_savings=float(explanation.impact_breakdown.annual_savings),
            one_time_cost=float(explanation.impact_breakdown.one_time_cost),
            risk_before=explanation.impact_breakdown.risk_before,
            risk_after=explanation.impact_breakdown.risk_after,
            net_benefit=float(explanation.impact_breakdown.net_benefit),
        ),
        alternatives=[
            AlternativeOptionResponse(
                title=a.title,
                description=a.description,
                impact_comparison=a.impact_comparison,
                trade_offs=a.trade_offs,
            )
            for a in explanation.alternatives
        ],
        confidence_level=explanation.confidence_level.value,
        confidence_percentage=explanation.confidence_percentage,
        data_basis=explanation.data_basis,
    )


# =============================================================================
# What-If Simulator Schemas
# =============================================================================

class KPIProjectionResponse(BaseModel):
    """Projektion eines einzelnen KPI."""
    kpi_name: str = Field(..., description="Name des KPI")
    current_value: float = Field(..., description="Aktueller Wert")
    projected_value: float = Field(..., description="Projizierter Wert")
    change_absolute: float = Field(..., description="Absolute Aenderung")
    change_percentage: float = Field(..., description="Prozentuale Aenderung")
    impact_severity: str = Field(..., description="Schweregrad des Impacts")
    threshold_warning: Optional[str] = Field(None, description="Warnung bei Schwellenwert")


class TimelinePointResponse(BaseModel):
    """Ein Punkt auf der Zeitleiste."""
    month: int = Field(..., description="Monat (0 = jetzt)")
    date: str = Field(..., description="Datum")
    health_score: float = Field(..., description="Health Score zu diesem Zeitpunkt")
    key_kpis: Dict[str, float] = Field(default={}, description="Wichtige KPIs")
    events: List[str] = Field(default=[], description="Ereignisse")


class ScenarioResultResponse(BaseModel):
    """Ergebnis einer Szenario-Simulation."""
    scenario_id: str = Field(..., description="Szenario-ID")
    scenario_type: str = Field(..., description="Typ des Szenarios")
    scenario_description: str = Field(..., description="Beschreibung")

    current_health_score: float = Field(..., description="Aktueller Health Score")
    current_kpis: Dict[str, float] = Field(..., description="Aktuelle KPIs")

    projected_health_score: float = Field(..., description="Projizierter Health Score")
    projected_kpis: List[KPIProjectionResponse] = Field(..., description="Projizierte KPIs")

    health_score_change: float = Field(..., description="Health Score Aenderung")
    health_score_change_percentage: float = Field(..., description="Prozentuale Aenderung")
    overall_impact_severity: str = Field(..., description="Gesamter Impact-Schweregrad")

    timeline: List[TimelinePointResponse] = Field(..., description="Zeitleiste")

    total_cost: float = Field(..., description="Gesamtkosten in EUR")
    total_benefit: float = Field(..., description="Gesamtnutzen in EUR")
    net_benefit: float = Field(..., description="Netto-Nutzen in EUR")
    payback_months: Optional[int] = Field(None, description="Amortisationszeit in Monaten")

    risks: List[str] = Field(default=[], description="Risiken")
    warnings: List[str] = Field(default=[], description="Warnungen")
    opportunities: List[str] = Field(default=[], description="Chancen")

    calculated_at: str = Field(..., description="Berechnungszeitpunkt")
    confidence_percentage: float = Field(..., description="Konfidenz in Prozent")
    data_basis: str = Field(..., description="Datenbasis")

    class Config:
        json_schema_extra = {
            "example": {
                "scenario_id": "550e8400-e29b-41d4-a716-446655440000",
                "scenario_type": "extra_savings",
                "scenario_description": "300 EUR/Monat zusaetzlich sparen",
                "current_health_score": 67.5,
                "current_kpis": {"dti_ratio": 38.5, "savings_rate": 12.0},
                "projected_health_score": 78.2,
                "projected_kpis": [],
                "health_score_change": 10.7,
                "health_score_change_percentage": 15.9,
                "overall_impact_severity": "positive",
                "timeline": [],
                "total_cost": 0,
                "total_benefit": 3600,
                "net_benefit": 3600,
                "payback_months": None,
                "risks": [],
                "warnings": [],
                "opportunities": ["Notgroschen waechst auf 5.2 Monate"],
                "calculated_at": "2024-01-15T10:30:00Z",
                "confidence_percentage": 85.0,
                "data_basis": "Vollstaendige Finanzdaten",
            }
        }


class ComparisonResultResponse(BaseModel):
    """Ergebnis eines Szenario-Vergleichs."""
    comparison_id: str = Field(..., description="Vergleichs-ID")
    scenarios: List[ScenarioResultResponse] = Field(..., description="Alle Szenarien")
    best_scenario_id: str = Field(..., description="ID des besten Szenarios")
    best_scenario_reason: str = Field(..., description="Begruendung")
    ranking: List[Dict[str, Any]] = Field(..., description="Ranking nach Net-Benefit")
    recommendation: str = Field(..., description="Empfehlung")


class SimulateScenarioRequest(BaseModel):
    """Request fuer eine Szenario-Simulation."""
    scenario_type: str = Field(
        ...,
        min_length=1,
        max_length=50,
        description="Typ des Szenarios"
    )
    amount: float = Field(
        default=0,
        ge=-1e9,
        le=1e9,
        description="Betrag in EUR"
    )
    percentage: float = Field(
        default=0,
        ge=-100,
        le=1000,
        description="Prozentuale Aenderung"
    )
    duration_months: int = Field(default=12, ge=1, le=60, description="Dauer in Monaten")
    target_entity_id: Optional[str] = Field(
        None,
        max_length=36,
        description="Ziel-Entity-ID (z.B. Kredit)"
    )
    additional_params: Dict[str, Any] = Field(default={}, description="Zusaetzliche Parameter")

    @field_validator("scenario_type")
    @classmethod
    def validate_scenario_type(cls, v: str) -> str:
        """Validiert den Szenario-Typ."""
        allowed_types = {
            "extra_savings",
            "extra_payment",
            "income_change",
            "interest_rate_change",
            "expense_reduction",
            "asset_sale",
            "debt_consolidation",
            "investment_reallocation",
        }
        v = v.strip().lower()
        if v not in allowed_types:
            raise ValueError(
                f"Ungueltiger Szenario-Typ. Erlaubt sind: {', '.join(sorted(allowed_types))}"
            )
        return v

    @field_validator("target_entity_id")
    @classmethod
    def validate_target_entity_id(cls, v: Optional[str]) -> Optional[str]:
        """Validiert die Entity-ID als UUID."""
        if v is None:
            return None
        v = v.strip()
        # Validate UUID format
        uuid_pattern = r'^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$'
        if not re.match(uuid_pattern, v):
            raise ValueError("target_entity_id muss eine gueltige UUID sein")
        return v

    @field_validator("additional_params")
    @classmethod
    def validate_additional_params(cls, v: Dict[str, Any]) -> Dict[str, Any]:
        """Validiert und begrenzt additional_params."""
        if len(v) > 20:
            raise ValueError("additional_params darf maximal 20 Eintraege haben")
        # Prevent deeply nested structures
        import json
        try:
            serialized = json.dumps(v)
            if len(serialized) > 10000:
                raise ValueError("additional_params ist zu gross (max 10KB)")
        except (TypeError, ValueError) as e:
            raise ValueError(f"additional_params muss JSON-serialisierbar sein: {e}")
        return v

    class Config:
        json_schema_extra = {
            "example": {
                "scenario_type": "extra_savings",
                "amount": 300,
                "duration_months": 12,
            }
        }


class CurrentKPIsRequest(BaseModel):
    """Aktuelle KPIs fuer die Simulation."""
    health_score: float = Field(
        default=70.0,
        ge=0,
        le=100,
        description="Aktueller Health Score"
    )
    dti_ratio: float = Field(
        default=35.0,
        ge=0,
        le=200,
        description="Debt-to-Income Ratio"
    )
    savings_rate: float = Field(
        default=10.0,
        ge=-100,
        le=100,
        description="Sparquote (kann negativ sein bei Entsparen)"
    )
    emergency_fund_months: float = Field(
        default=3.0,
        ge=0,
        le=120,
        description="Notgroschen in Monaten"
    )
    monthly_income: float = Field(
        default=5000.0,
        ge=0,
        le=1e8,
        description="Monatseinkommen"
    )
    monthly_expenses: float = Field(
        default=3500.0,
        ge=0,
        le=1e8,
        description="Monatliche Ausgaben"
    )
    total_debt: float = Field(
        default=100000.0,
        ge=0,
        le=1e10,
        description="Gesamtschulden"
    )

    @model_validator(mode="after")
    def validate_expenses_vs_income(self) -> "CurrentKPIsRequest":
        """Warnt wenn Ausgaben das Einkommen uebersteigen."""
        # Nicht blockieren, nur logisch pruefen
        # Bei negativer Sparquote kann das legitim sein
        return self


class SimulateRequest(BaseModel):
    """Kombinierter Request fuer Simulation."""
    scenario: SimulateScenarioRequest = Field(..., description="Szenario-Definition")
    current_kpis: CurrentKPIsRequest = Field(..., description="Aktuelle KPIs")


class CompareRequest(BaseModel):
    """Request fuer Szenario-Vergleich."""
    scenarios: List[SimulateScenarioRequest] = Field(..., min_length=2, max_length=5, description="Zu vergleichende Szenarien")
    current_kpis: CurrentKPIsRequest = Field(..., description="Aktuelle KPIs")


class CombineRequest(BaseModel):
    """Request fuer kombinierte Szenarien."""
    scenarios: List[SimulateScenarioRequest] = Field(..., min_length=1, max_length=5, description="Zu kombinierende Szenarien")
    current_kpis: CurrentKPIsRequest = Field(..., description="Aktuelle KPIs")


# =============================================================================
# What-If Simulator Endpoints
# =============================================================================

@limiter.limit("5/minute", key_func=get_user_identifier)
@router.post(
    "/simulator/what-if",
    response_model=ScenarioResultResponse,
    summary="Szenario simulieren",
    description="""
    Simuliert ein hypothetisches Szenario und zeigt die Auswirkungen.

    **Beispiel-Szenarien:**
    - Was passiert wenn ich 300 EUR/Monat mehr spare?
    - Was passiert wenn ich 5000 EUR Sondertilgung mache?
    - Was passiert wenn die Zinsen um 2% steigen?
    - Was passiert wenn mein Einkommen um 10% sinkt?

    **Szenario-Typen:**
    - `extra_savings` - Zusaetzliche Sparrate
    - `extra_payment` - Sondertilgung
    - `income_change` - Einkommensaenderung
    - `interest_rate_change` - Zinssatzaenderung

    **Enterprise Feature** - Teil des What-If Simulators.
    """,
)
async def simulate_scenario(
    fastapi_request: Request,
    request: SimulateRequest,
    current_user: User = Depends(get_current_active_user),
) -> ScenarioResultResponse:
    """Simuliert ein einzelnes Szenario."""
    simulator = get_whatif_simulator()

    # ScenarioInput erstellen
    try:
        scenario_type = ScenarioType(request.scenario.scenario_type)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Ungueltiger Szenario-Typ: {request.scenario.scenario_type}",
        )

    scenario_input = ScenarioInput(
        scenario_type=scenario_type,
        amount=Decimal(str(request.scenario.amount)),
        percentage=request.scenario.percentage,
        duration_months=request.scenario.duration_months,
        target_entity_id=UUID(request.scenario.target_entity_id) if request.scenario.target_entity_id else None,
        additional_params=request.scenario.additional_params,
    )

    # KPIs zu Dict konvertieren
    current_kpis = {
        "health_score": request.current_kpis.health_score,
        "dti_ratio": request.current_kpis.dti_ratio,
        "savings_rate": request.current_kpis.savings_rate,
        "emergency_fund_months": request.current_kpis.emergency_fund_months,
        "monthly_income": request.current_kpis.monthly_income,
        "monthly_expenses": request.current_kpis.monthly_expenses,
        "total_debt": request.current_kpis.total_debt,
    }

    result = await simulator.simulate_scenario(
        scenario_input=scenario_input,
        current_kpis=current_kpis,
        user_id=current_user.id,
    )

    return _convert_scenario_result(result)


@limiter.limit("5/minute", key_func=get_user_identifier)
@router.post(
    "/simulator/compare",
    response_model=ComparisonResultResponse,
    summary="Szenarien vergleichen",
    description="""
    Vergleicht mehrere Szenarien miteinander und empfiehlt das beste.

    **Beispiel:** Vergleiche:
    - 300 EUR/Monat mehr sparen vs.
    - 5000 EUR Sondertilgung vs.
    - 200 EUR/Monat + 2000 EUR Sondertilgung

    Gibt ein Ranking nach Netto-Nutzen zurueck.
    """,
)
async def compare_scenarios(
    fastapi_request: Request,
    request: CompareRequest,
    current_user: User = Depends(get_current_active_user),
) -> ComparisonResultResponse:
    """Vergleicht mehrere Szenarien."""
    simulator = get_whatif_simulator()

    # ScenarioInputs erstellen
    scenario_inputs = []
    for s in request.scenarios:
        try:
            scenario_type = ScenarioType(s.scenario_type)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Ungueltiger Szenario-Typ: {s.scenario_type}",
            )

        scenario_inputs.append(ScenarioInput(
            scenario_type=scenario_type,
            amount=Decimal(str(s.amount)),
            percentage=s.percentage,
            duration_months=s.duration_months,
            target_entity_id=UUID(s.target_entity_id) if s.target_entity_id else None,
            additional_params=s.additional_params,
        ))

    current_kpis = {
        "health_score": request.current_kpis.health_score,
        "dti_ratio": request.current_kpis.dti_ratio,
        "savings_rate": request.current_kpis.savings_rate,
        "emergency_fund_months": request.current_kpis.emergency_fund_months,
        "monthly_income": request.current_kpis.monthly_income,
        "monthly_expenses": request.current_kpis.monthly_expenses,
        "total_debt": request.current_kpis.total_debt,
    }

    result = await simulator.compare_scenarios(
        scenarios=scenario_inputs,
        current_kpis=current_kpis,
        user_id=current_user.id,
    )

    return ComparisonResultResponse(
        comparison_id=str(result.comparison_id),
        scenarios=[_convert_scenario_result(s) for s in result.scenarios],
        best_scenario_id=str(result.best_scenario_id),
        best_scenario_reason=result.best_scenario_reason,
        ranking=result.ranking,
        recommendation=result.recommendation,
    )


@limiter.limit("5/minute", key_func=get_user_identifier)
@router.post(
    "/simulator/combine",
    response_model=ScenarioResultResponse,
    summary="Szenarien kombinieren",
    description="""
    Kombiniert mehrere Szenarien und zeigt den kumulativen Effekt.

    **Beispiel:** Was passiert wenn ich BEIDES mache:
    - 200 EUR/Monat mehr sparen UND
    - 3000 EUR Sondertilgung

    Die Effekte werden kumuliert berechnet.
    """,
)
async def combine_scenarios(
    fastapi_request: Request,
    request: CombineRequest,
    current_user: User = Depends(get_current_active_user),
) -> ScenarioResultResponse:
    """Kombiniert mehrere Szenarien."""
    simulator = get_whatif_simulator()

    # ScenarioInputs erstellen
    scenario_inputs = []
    for s in request.scenarios:
        try:
            scenario_type = ScenarioType(s.scenario_type)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Ungueltiger Szenario-Typ: {s.scenario_type}",
            )

        scenario_inputs.append(ScenarioInput(
            scenario_type=scenario_type,
            amount=Decimal(str(s.amount)),
            percentage=s.percentage,
            duration_months=s.duration_months,
            target_entity_id=UUID(s.target_entity_id) if s.target_entity_id else None,
            additional_params=s.additional_params,
        ))

    current_kpis = {
        "health_score": request.current_kpis.health_score,
        "dti_ratio": request.current_kpis.dti_ratio,
        "savings_rate": request.current_kpis.savings_rate,
        "emergency_fund_months": request.current_kpis.emergency_fund_months,
        "monthly_income": request.current_kpis.monthly_income,
        "monthly_expenses": request.current_kpis.monthly_expenses,
        "total_debt": request.current_kpis.total_debt,
    }

    result = await simulator.simulate_combined_scenarios(
        scenarios=scenario_inputs,
        current_kpis=current_kpis,
        user_id=current_user.id,
    )

    return _convert_scenario_result(result)


@limiter.limit("60/minute", key_func=get_user_identifier)
@router.get(
    "/simulator/quick-scenarios",
    response_model=List[Dict[str, Any]],
    summary="Schnell-Szenarien abrufen",
    description="""
    Gibt vordefinierte Schnell-Szenarien zurueck, basierend auf aktuellen KPIs.

    Das System schlaegt intelligent relevante Szenarien vor:
    - Bei hohem DTI: Schuldenabbau-Szenarien
    - Bei niedrigem Notgroschen: Spar-Szenarien
    - Immer: Stresstest-Szenarien (Zinsanstieg, Einkommensausfall)
    """,
)
async def get_quick_scenarios(
    request: Request,
    health_score: float = Query(default=70.0, description="Aktueller Health Score"),
    dti_ratio: float = Query(default=35.0, description="DTI Ratio"),
    savings_rate: float = Query(default=10.0, description="Sparquote"),
    emergency_fund_months: float = Query(default=3.0, description="Notgroschen in Monaten"),
    monthly_income: float = Query(default=5000.0, description="Monatseinkommen"),
    monthly_expenses: float = Query(default=3500.0, description="Monatliche Ausgaben"),
    current_user: User = Depends(get_current_active_user),
) -> List[Dict[str, Any]]:
    """Gibt Schnell-Szenarien basierend auf aktuellen KPIs zurueck."""
    simulator = get_whatif_simulator()

    current_kpis = {
        "health_score": health_score,
        "dti_ratio": dti_ratio,
        "savings_rate": savings_rate,
        "emergency_fund_months": emergency_fund_months,
        "monthly_income": monthly_income,
        "monthly_expenses": monthly_expenses,
    }

    return await simulator.get_quick_scenarios(current_kpis)


# =============================================================================
# Helper Functions
# =============================================================================

def _convert_scenario_result(result) -> ScenarioResultResponse:
    """Konvertiert ScenarioResult zu Response."""
    return ScenarioResultResponse(
        scenario_id=str(result.scenario_id),
        scenario_type=result.scenario_type.value,
        scenario_description=result.scenario_description,
        current_health_score=result.current_health_score,
        current_kpis=result.current_kpis,
        projected_health_score=result.projected_health_score,
        projected_kpis=[
            KPIProjectionResponse(
                kpi_name=kpi.kpi_name,
                current_value=kpi.current_value,
                projected_value=kpi.projected_value,
                change_absolute=kpi.change_absolute,
                change_percentage=kpi.change_percentage,
                impact_severity=kpi.impact_severity.value,
                threshold_warning=kpi.threshold_warning,
            )
            for kpi in result.projected_kpis
        ],
        health_score_change=result.health_score_change,
        health_score_change_percentage=result.health_score_change_percentage,
        overall_impact_severity=result.overall_impact_severity.value,
        timeline=[
            TimelinePointResponse(
                month=tp.month,
                date=tp.date.isoformat(),
                health_score=tp.health_score,
                key_kpis=tp.key_kpis,
                events=tp.events,
            )
            for tp in result.timeline
        ],
        total_cost=float(result.total_cost),
        total_benefit=float(result.total_benefit),
        net_benefit=float(result.net_benefit),
        payback_months=result.payback_months,
        risks=result.risks,
        warnings=result.warnings,
        opportunities=result.opportunities,
        calculated_at=result.calculated_at.isoformat(),
        confidence_percentage=result.confidence_percentage,
        data_basis=result.data_basis,
    )


# =============================================================================
# Proactive Insights Schemas
# =============================================================================

class ProactiveInsightResponse(BaseModel):
    """Ein proaktiver Insight."""
    id: str = Field(..., description="Insight-ID")
    insight_type: str = Field(..., description="Typ des Insights")
    priority: str = Field(..., description="Prioritaet (critical, high, medium, low)")
    title: str = Field(..., description="Titel des Insights")
    message: str = Field(..., description="Detaillierte Nachricht")
    entity_type: Optional[str] = Field(None, description="Betroffener Entity-Typ")
    entity_id: Optional[str] = Field(None, description="Betroffene Entity-ID")
    entity_name: Optional[str] = Field(None, description="Betroffener Entity-Name")
    potential_value: Optional[float] = Field(None, description="Potenzieller Wert in EUR")
    recommendation: Optional[str] = Field(None, description="Empfehlung")
    action_url: Optional[str] = Field(None, description="Action-URL")
    confidence: float = Field(..., description="Konfidenz (0-1)")
    source_rule: Optional[str] = Field(None, description="Auslösende Regel")
    expires_at: Optional[str] = Field(None, description="Ablaufzeitpunkt")

    class Config:
        json_schema_extra = {
            "example": {
                "id": "550e8400-e29b-41d4-a716-446655440000",
                "insight_type": "optimization",
                "priority": "high",
                "title": "Lieferanten-Preisalarm",
                "message": "Lieferant 'Mueller GmbH' ist 23% teurer als der Marktdurchschnitt.",
                "entity_type": "supplier",
                "entity_id": "sup-123",
                "entity_name": "Mueller GmbH",
                "potential_value": 1500.0,
                "recommendation": "Alternative Lieferanten pruefen?",
                "action_url": "/suppliers/sup-123/alternatives",
                "confidence": 0.87,
                "source_rule": "supplier_pricing_check",
                "expires_at": None,
            }
        }


class ExtractedEntityResponse(BaseModel):
    """Eine extrahierte Entity aus dem Text."""
    entity_type: str = Field(..., description="Entity-Typ")
    entity_id: Optional[str] = Field(None, description="Entity-ID")
    entity_name: str = Field(..., description="Entity-Name")
    original_text: str = Field(..., description="Original-Text")
    start_position: int = Field(..., description="Start-Position im Text")
    end_position: int = Field(..., description="End-Position im Text")
    confidence: float = Field(..., description="Konfidenz der Extraktion")


class EnrichedResponseResponse(BaseModel):
    """Angereicherte Chat-Antwort mit proaktiven Insights."""
    original_response: str = Field(..., description="Urspruengliche Antwort")
    insights: List[ProactiveInsightResponse] = Field(..., description="Proaktive Insights")
    extracted_entities: List[ExtractedEntityResponse] = Field(..., description="Extrahierte Entities")
    follow_up_suggestions: List[str] = Field(..., description="Follow-Up Vorschlaege")
    processing_time_ms: float = Field(..., description="Verarbeitungszeit in ms")


class EnrichChatRequest(BaseModel):
    """Request zur Anreicherung einer Chat-Antwort."""
    user_question: str = Field(..., description="Frage des Benutzers")
    base_answer: str = Field(..., description="Basis-Antwort")
    current_kpis: Optional[Dict[str, Any]] = Field(None, description="Aktuelle KPIs")
    max_insights: int = Field(5, ge=1, le=20, description="Maximale Anzahl Insights")


class ContextualInsightRequest(BaseModel):
    """Request fuer kontextbezogene Insights."""
    context_source: str = Field(..., description="Kontext-Quelle (chat, document, dashboard)")
    context_data: Dict[str, Any] = Field(..., description="Kontext-Daten")
    current_kpis: Optional[Dict[str, Any]] = Field(None, description="Aktuelle KPIs")
    max_insights: int = Field(10, ge=1, le=50, description="Maximale Anzahl Insights")


class DashboardInsightRequest(BaseModel):
    """Request fuer Dashboard-Insights."""
    health_score: float = Field(..., ge=0, le=100, description="Aktueller Health Score")
    dti_ratio: Optional[float] = Field(None, description="Debt-to-Income Ratio")
    emergency_fund_months: Optional[float] = Field(None, description="Notgroschen in Monaten")
    net_worth: Optional[float] = Field(None, description="Nettovermoegen")
    monthly_savings_rate: Optional[float] = Field(None, description="Sparrate in %")
    portfolio_diversity: Optional[float] = Field(None, description="Portfolio-Diversitaet (0-1)")
    monthly_income: Optional[float] = Field(None, description="Monatliches Einkommen")
    monthly_expenses: Optional[float] = Field(None, description="Monatliche Ausgaben")


class InsightFeedbackRequest(BaseModel):
    """Feedback zu einem Insight."""
    insight_id: str = Field(..., description="Insight-ID")
    feedback_type: str = Field(..., description="Feedback-Typ (helpful, not_helpful, acted_on, dismissed)")
    comment: Optional[str] = Field(None, description="Optionaler Kommentar")


class InsightFeedbackResponse(BaseModel):
    """Antwort auf Insight-Feedback."""
    success: bool = Field(..., description="Ob Feedback erfolgreich gespeichert")
    message: str = Field(..., description="Nachricht")
    insight_id: str = Field(..., description="Insight-ID")
    feedback_type: str = Field(..., description="Feedback-Typ")


class InsightRuleResponse(BaseModel):
    """Eine Insight-Regel."""
    rule_id: str = Field(..., description="Regel-ID")
    name: str = Field(..., description="Regelname")
    description: str = Field(..., description="Beschreibung")
    entity_type: str = Field(..., description="Entity-Typ auf den die Regel anwendet")
    insight_type: str = Field(..., description="Insight-Typ der generiert wird")
    priority: str = Field(..., description="Prioritaet des generierten Insights")
    is_enabled: bool = Field(..., description="Ob Regel aktiv ist")


# =============================================================================
# Proactive Insights Endpoints
# =============================================================================

@limiter.limit("60/minute", key_func=get_user_identifier)
@router.post(
    "/insights/enrich-response",
    response_model=EnrichedResponseResponse,
    summary="Chat-Antwort mit Insights anreichern",
    description="""
    Reichert eine Chat-Antwort mit proaktiven Insights an.

    Das System analysiert die User-Frage und Base-Antwort:
    - Extrahiert relevante Entities (Lieferanten, Immobilien, Versicherungen, etc.)
    - Generiert Insights basierend auf dem Kontext
    - Fuegt Follow-Up-Vorschlaege hinzu

    Beispiel:
    - User fragt nach "Lieferant Mueller"
    - System erkennt: Mueller ist 23% teurer als Durchschnitt
    - Insight: "Preisanstieg bei Mueller GmbH - Alternativen pruefen?"
    """
)
async def enrich_chat_response(
    fastapi_request: Request,
    request: EnrichChatRequest,
    current_user: User = Depends(get_current_active_user),
) -> EnrichedResponseResponse:
    """Reichert eine Chat-Antwort mit proaktiven Insights an."""
    from app.services.orchestration import get_proactive_insights_service
    import time

    start_time = time.time()

    service = get_proactive_insights_service()
    enriched = await service.enrich_chat_response(
        user_id=current_user.id,
        user_question=request.user_question,
        base_answer=request.base_answer,
        current_kpis=request.current_kpis,
        max_insights=request.max_insights,
    )

    processing_time = (time.time() - start_time) * 1000

    return EnrichedResponseResponse(
        original_response=enriched.original_response,
        insights=[
            ProactiveInsightResponse(
                id=str(insight.id),
                insight_type=insight.insight_type.value,
                priority=insight.priority.value,
                title=insight.title,
                message=insight.message,
                entity_type=insight.entity_type.value if insight.entity_type else None,
                entity_id=insight.entity_id,
                entity_name=insight.entity_name,
                potential_value=float(insight.potential_value) if insight.potential_value else None,
                recommendation=insight.recommendation,
                action_url=insight.action_url,
                confidence=insight.confidence,
                source_rule=insight.source_rule,
                expires_at=insight.expires_at.isoformat() if insight.expires_at else None,
            )
            for insight in enriched.insights
        ],
        extracted_entities=[
            ExtractedEntityResponse(
                entity_type=entity.entity_type.value,
                entity_id=entity.entity_id,
                entity_name=entity.entity_name,
                original_text=entity.original_text,
                start_position=entity.start_position,
                end_position=entity.end_position,
                confidence=entity.confidence,
            )
            for entity in enriched.extracted_entities
        ],
        follow_up_suggestions=enriched.follow_up_suggestions,
        processing_time_ms=processing_time,
    )


@limiter.limit("60/minute", key_func=get_user_identifier)
@router.get(
    "/insights/dashboard",
    response_model=List[ProactiveInsightResponse],
    summary="Dashboard-Insights abrufen",
    description="""
    Ruft proaktive Insights fuer das Dashboard ab.

    Analysiert aktuelle KPIs und generiert relevante Insights:
    - Early Warnings bei kritischen KPIs
    - Optimierungsvorschlaege
    - Opportunitaeten

    Die Insights sind priorisiert nach Wichtigkeit.
    """
)
async def get_dashboard_insights(
    request: Request,
    health_score: float = Query(..., ge=0, le=100, description="Aktueller Health Score"),
    dti_ratio: Optional[float] = Query(None, description="Debt-to-Income Ratio"),
    emergency_fund_months: Optional[float] = Query(None, description="Notgroschen in Monaten"),
    net_worth: Optional[float] = Query(None, description="Nettovermoegen"),
    monthly_savings_rate: Optional[float] = Query(None, description="Sparrate in %"),
    portfolio_diversity: Optional[float] = Query(None, description="Portfolio-Diversitaet (0-1)"),
    monthly_income: Optional[float] = Query(None, description="Monatliches Einkommen"),
    monthly_expenses: Optional[float] = Query(None, description="Monatliche Ausgaben"),
    max_insights: int = Query(10, ge=1, le=50, description="Maximale Anzahl Insights"),
    current_user: User = Depends(get_current_active_user),
) -> List[ProactiveInsightResponse]:
    """Ruft proaktive Insights fuer das Dashboard ab."""
    from app.services.orchestration import get_proactive_insights_service

    service = get_proactive_insights_service()

    current_kpis = {
        "health_score": health_score,
        "dti_ratio": dti_ratio,
        "emergency_fund_months": emergency_fund_months,
        "net_worth": net_worth,
        "monthly_savings_rate": monthly_savings_rate,
        "portfolio_diversity": portfolio_diversity,
        "monthly_income": monthly_income,
        "monthly_expenses": monthly_expenses,
    }
    # Entferne None-Werte
    current_kpis = {k: v for k, v in current_kpis.items() if v is not None}

    insights = await service.get_dashboard_insights(
        user_id=current_user.id,
        current_kpis=current_kpis,
        max_insights=max_insights,
    )

    return [
        ProactiveInsightResponse(
            id=str(insight.id),
            insight_type=insight.insight_type.value,
            priority=insight.priority.value,
            title=insight.title,
            message=insight.message,
            entity_type=insight.entity_type.value if insight.entity_type else None,
            entity_id=insight.entity_id,
            entity_name=insight.entity_name,
            potential_value=float(insight.potential_value) if insight.potential_value else None,
            recommendation=insight.recommendation,
            action_url=insight.action_url,
            confidence=insight.confidence,
            source_rule=insight.source_rule,
            expires_at=insight.expires_at.isoformat() if insight.expires_at else None,
        )
        for insight in insights
    ]


@limiter.limit("60/minute", key_func=get_user_identifier)
@router.post(
    "/insights/contextual",
    response_model=List[ProactiveInsightResponse],
    summary="Kontextbezogene Insights abrufen",
    description="""
    Generiert Insights basierend auf spezifischem Kontext.

    Moegliche Kontextquellen:
    - "chat": Chat-Konversation
    - "document": Dokument-Analyse
    - "dashboard": Dashboard-Ansicht
    - "module": Modul-Ansicht (privat, immobilien, etc.)

    Der Kontext wird analysiert und relevante Insights generiert.
    """
)
async def get_contextual_insights(
    fastapi_request: Request,
    request: ContextualInsightRequest,
    current_user: User = Depends(get_current_active_user),
) -> List[ProactiveInsightResponse]:
    """Generiert kontextbezogene Insights."""
    from app.services.orchestration import get_proactive_insights_service

    service = get_proactive_insights_service()

    insights = await service.get_contextual_insights(
        user_id=current_user.id,
        context_source=request.context_source,
        context_data=request.context_data,
        current_kpis=request.current_kpis,
        max_insights=request.max_insights,
    )

    return [
        ProactiveInsightResponse(
            id=str(insight.id),
            insight_type=insight.insight_type.value,
            priority=insight.priority.value,
            title=insight.title,
            message=insight.message,
            entity_type=insight.entity_type.value if insight.entity_type else None,
            entity_id=insight.entity_id,
            entity_name=insight.entity_name,
            potential_value=float(insight.potential_value) if insight.potential_value else None,
            recommendation=insight.recommendation,
            action_url=insight.action_url,
            confidence=insight.confidence,
            source_rule=insight.source_rule,
            expires_at=insight.expires_at.isoformat() if insight.expires_at else None,
        )
        for insight in insights
    ]


@limiter.limit("60/minute", key_func=get_user_identifier)
@router.post(
    "/insights/feedback",
    response_model=InsightFeedbackResponse,
    summary="Feedback zu Insight geben",
    description="""
    Speichert User-Feedback zu einem Insight.

    Feedback-Typen:
    - "helpful": Insight war hilfreich
    - "not_helpful": Insight war nicht hilfreich
    - "acted_on": User hat auf Insight reagiert
    - "dismissed": User hat Insight abgelehnt

    Dieses Feedback wird fuer Self-Learning verwendet.
    """
)
async def submit_insight_feedback(
    fastapi_request: Request,
    request: InsightFeedbackRequest,
    current_user: User = Depends(get_current_active_user),
) -> InsightFeedbackResponse:
    """Speichert Feedback zu einem Insight."""
    from app.services.orchestration import get_proactive_insights_service

    service = get_proactive_insights_service()

    await service.record_feedback(
        user_id=current_user.id,
        insight_id=request.insight_id,
        feedback_type=request.feedback_type,
        comment=request.comment,
    )

    return InsightFeedbackResponse(
        success=True,
        message="Feedback erfolgreich gespeichert",
        insight_id=request.insight_id,
        feedback_type=request.feedback_type,
    )


@limiter.limit("60/minute", key_func=get_user_identifier)
@router.get(
    "/insights/rules",
    response_model=List[InsightRuleResponse],
    summary="Insight-Regeln abrufen",
    description="""
    Ruft alle konfigurierten Insight-Regeln ab.

    Regeln definieren, unter welchen Bedingungen Insights generiert werden.
    Jede Regel ist einem Entity-Typ zugeordnet und generiert einen
    spezifischen Insight-Typ.
    """
)
async def get_insight_rules(
    request: Request,
    current_user: User = Depends(get_current_active_user),
) -> List[InsightRuleResponse]:
    """Ruft alle Insight-Regeln ab."""
    from app.services.orchestration import get_proactive_insights_service

    service = get_proactive_insights_service()
    rules = service.rule_engine.get_all_rules()

    return [
        InsightRuleResponse(
            rule_id=rule.rule_id,
            name=rule.name,
            description=rule.description,
            entity_type=rule.entity_type.value,
            insight_type=rule.insight_type.value,
            priority=rule.priority.value,
            is_enabled=rule.is_enabled,
        )
        for rule in rules
    ]


@limiter.limit("60/minute", key_func=get_user_identifier)
@router.get(
    "/insights/stats",
    response_model=Dict[str, Any],
    summary="Insight-Statistiken abrufen",
    description="""
    Ruft Statistiken zu Insights ab:
    - Anzahl generierter Insights nach Typ
    - Feedback-Verteilung
    - Durchschnittliche Konfidenz
    - Beliebteste Insight-Typen
    """
)
async def get_insight_stats(
    request: Request,
    current_user: User = Depends(get_current_active_user),
) -> Dict[str, Any]:
    """Ruft Insight-Statistiken ab."""
    from app.services.orchestration import get_proactive_insights_service

    service = get_proactive_insights_service()
    stats = await service.get_statistics(user_id=current_user.id)

    return stats


# =============================================================================
# Personalized Thresholds Schemas
# =============================================================================

class ThresholdDefinitionResponse(BaseModel):
    """Definition eines Schwellenwertes."""
    threshold_type: str = Field(..., description="Schwellenwert-Typ")
    category: str = Field(..., description="Kategorie")
    name: str = Field(..., description="Name")
    description: str = Field(..., description="Beschreibung")
    unit: str = Field(..., description="Einheit")
    default_value: float = Field(..., description="Standard-Wert")
    min_allowed: float = Field(..., description="Minimum erlaubt")
    max_allowed: float = Field(..., description="Maximum erlaubt")

    class Config:
        json_schema_extra = {
            "example": {
                "threshold_type": "dti_warning",
                "category": "debt",
                "name": "DTI Warnschwelle",
                "description": "Debt-to-Income Ratio ab der eine Warnung erscheint",
                "unit": "%",
                "default_value": 36.0,
                "min_allowed": 20.0,
                "max_allowed": 60.0,
            }
        }


class UserThresholdResponse(BaseModel):
    """Ein personalisierter Schwellenwert."""
    id: str = Field(..., description="Threshold-ID")
    threshold_type: str = Field(..., description="Schwellenwert-Typ")
    default_value: float = Field(..., description="Standard-Wert")
    current_value: float = Field(..., description="Aktueller personalisierter Wert")
    adjustment_source: str = Field(..., description="Quelle der Anpassung")
    adjustment_reason: Optional[str] = Field(None, description="Begruendung")
    confidence: float = Field(..., description="Konfidenz (0-1)")
    effectiveness_score: float = Field(..., description="Effektivitaets-Score (0-1)")
    times_triggered: int = Field(..., description="Wie oft getriggert")
    times_acted_on: int = Field(..., description="Wie oft reagiert")
    created_at: str = Field(..., description="Erstellt am")
    updated_at: str = Field(..., description="Aktualisiert am")

    class Config:
        json_schema_extra = {
            "example": {
                "id": "550e8400-e29b-41d4-a716-446655440000",
                "threshold_type": "dti_warning",
                "default_value": 36.0,
                "current_value": 40.0,
                "adjustment_source": "profession_profile",
                "adjustment_reason": "Basierend auf Berufsprofil: civil_servant",
                "confidence": 0.75,
                "effectiveness_score": 0.85,
                "times_triggered": 12,
                "times_acted_on": 10,
                "created_at": "2025-12-01T10:00:00Z",
                "updated_at": "2026-01-05T14:30:00Z",
            }
        }


class UserProfileResponse(BaseModel):
    """User-Profil fuer Schwellenwert-Personalisierung."""
    user_id: str = Field(..., description="User-ID")
    profession_type: str = Field(..., description="Berufstyp")
    risk_tolerance: str = Field(..., description="Risikotoleranz")
    income_stability: float = Field(..., description="Einkommensstabilitaet (0-1)")
    age_group: str = Field(..., description="Altersgruppe")
    household_size: int = Field(..., description="Haushaltsgroesse")
    has_dependents: bool = Field(..., description="Hat Unterhaltsberechtigte")
    is_homeowner: bool = Field(..., description="Ist Eigentuemer")
    has_pension_plan: bool = Field(..., description="Hat Altersvorsorge")
    prefers_aggressive_alerts: bool = Field(..., description="Bevorzugt aggressive Warnungen")
    prefers_conservative_targets: bool = Field(..., description="Bevorzugt konservative Ziele")
    created_at: str = Field(..., description="Erstellt am")
    updated_at: str = Field(..., description="Aktualisiert am")


class UpdateProfileRequest(BaseModel):
    """Request zur Aktualisierung des User-Profils."""
    profession_type: Optional[str] = Field(None, description="Berufstyp")
    risk_tolerance: Optional[str] = Field(None, description="Risikotoleranz")
    income_stability: Optional[float] = Field(None, ge=0, le=1, description="Einkommensstabilitaet")
    age_group: Optional[str] = Field(None, description="Altersgruppe (18-30, 31-45, 46-60, 60+)")
    household_size: Optional[int] = Field(None, ge=1, le=20, description="Haushaltsgroesse")
    has_dependents: Optional[bool] = Field(None, description="Hat Unterhaltsberechtigte")
    is_homeowner: Optional[bool] = Field(None, description="Ist Eigentuemer")
    has_pension_plan: Optional[bool] = Field(None, description="Hat Altersvorsorge")
    prefers_aggressive_alerts: Optional[bool] = Field(None, description="Bevorzugt aggressive Warnungen")
    prefers_conservative_targets: Optional[bool] = Field(None, description="Bevorzugt konservative Ziele")


class SetThresholdRequest(BaseModel):
    """Request zum Setzen eines Schwellenwertes."""
    value: float = Field(..., description="Neuer Wert")
    reason: Optional[str] = Field(None, max_length=500, description="Begruendung")


class ThresholdRecommendationResponse(BaseModel):
    """Empfehlung fuer Schwellenwert-Anpassung."""
    id: str = Field(..., description="Empfehlungs-ID")
    threshold_type: str = Field(..., description="Schwellenwert-Typ")
    current_value: float = Field(..., description="Aktueller Wert")
    recommended_value: float = Field(..., description="Empfohlener Wert")
    reason: str = Field(..., description="Begruendung")
    confidence: float = Field(..., description="Konfidenz (0-1)")
    potential_impact: str = Field(..., description="Potenzielle Auswirkung")
    created_at: str = Field(..., description="Erstellt am")
    expires_at: str = Field(..., description="Gueltig bis")


class ThresholdAdjustmentResponse(BaseModel):
    """Eine historische Schwellenwert-Anpassung."""
    id: str = Field(..., description="Anpassungs-ID")
    threshold_type: str = Field(..., description="Schwellenwert-Typ")
    previous_value: float = Field(..., description="Vorheriger Wert")
    new_value: float = Field(..., description="Neuer Wert")
    adjustment_source: str = Field(..., description="Quelle")
    reason: str = Field(..., description="Begruendung")
    confidence: float = Field(..., description="Konfidenz")
    applied_at: str = Field(..., description="Angewendet am")


class ThresholdStatisticsResponse(BaseModel):
    """Statistiken zu Schwellenwerten."""
    total_thresholds: int = Field(..., description="Gesamt-Anzahl Schwellenwerte")
    customized_count: int = Field(..., description="Anzahl angepasster Schwellenwerte")
    system_defaults_count: int = Field(..., description="Anzahl System-Defaults")
    average_effectiveness: float = Field(..., description="Durchschnittliche Effektivitaet")
    total_triggers: int = Field(..., description="Gesamt-Trigger")
    total_actions: int = Field(..., description="Gesamt-Aktionen")
    pending_recommendations: int = Field(..., description="Ausstehende Empfehlungen")


# =============================================================================
# Personalized Thresholds Endpoints
# =============================================================================

@limiter.limit("60/minute", key_func=get_user_identifier)
@router.get(
    "/thresholds/definitions",
    response_model=List[ThresholdDefinitionResponse],
    summary="Schwellenwert-Definitionen abrufen",
    description="""
    Ruft alle verfuegbaren Schwellenwert-Definitionen ab.

    Jede Definition enthaelt:
    - Typ und Kategorie
    - Standard-Wert und erlaubter Bereich
    - Beschreibung und Einheit
    """
)
async def get_threshold_definitions(
    request: Request,
    category: Optional[str] = Query(None, description="Filter nach Kategorie"),
    current_user: User = Depends(get_current_active_user),
) -> List[ThresholdDefinitionResponse]:
    """Ruft alle Schwellenwert-Definitionen ab."""
    from app.services.orchestration import get_personalized_thresholds_service, ThresholdCategory

    service = get_personalized_thresholds_service()

    if category:
        try:
            cat = ThresholdCategory(category)
            definitions = service.registry.get_thresholds_by_category(cat)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Ungueltige Kategorie: {category}",
            )
    else:
        definitions = service.registry.get_all_thresholds()

    return [
        ThresholdDefinitionResponse(
            threshold_type=d.threshold_type.value,
            category=d.category.value,
            name=d.name,
            description=d.description,
            unit=d.unit,
            default_value=d.default_value,
            min_allowed=d.min_allowed,
            max_allowed=d.max_allowed,
        )
        for d in definitions
    ]


@limiter.limit("60/minute", key_func=get_user_identifier)
@router.get(
    "/thresholds/profile",
    response_model=UserProfileResponse,
    summary="User-Profil abrufen",
    description="""
    Ruft das User-Profil fuer Schwellenwert-Personalisierung ab.

    Das Profil enthaelt:
    - Berufstyp und Risikotoleranz
    - Demographische Informationen
    - Praeferenzen
    """
)
async def get_user_profile(
    request: Request,
    current_user: User = Depends(get_current_active_user),
) -> UserProfileResponse:
    """Ruft das User-Profil ab."""
    from app.services.orchestration import get_personalized_thresholds_service

    service = get_personalized_thresholds_service()
    profile = await service.get_or_create_profile(current_user.id)

    return UserProfileResponse(
        user_id=str(profile.user_id),
        profession_type=profile.profession_type.value,
        risk_tolerance=profile.risk_tolerance.value,
        income_stability=profile.income_stability,
        age_group=profile.age_group,
        household_size=profile.household_size,
        has_dependents=profile.has_dependents,
        is_homeowner=profile.is_homeowner,
        has_pension_plan=profile.has_pension_plan,
        prefers_aggressive_alerts=profile.prefers_aggressive_alerts,
        prefers_conservative_targets=profile.prefers_conservative_targets,
        created_at=profile.created_at.isoformat(),
        updated_at=profile.updated_at.isoformat(),
    )


@limiter.limit("10/minute", key_func=get_user_identifier)
@router.put(
    "/thresholds/profile",
    response_model=UserProfileResponse,
    summary="User-Profil aktualisieren",
    description="""
    Aktualisiert das User-Profil.

    Nach einer Profil-Aenderung werden alle Schwellenwerte
    automatisch neu berechnet (ausser User-Overrides).
    """
)
async def update_user_profile(
    fastapi_request: Request,
    request: UpdateProfileRequest,
    current_user: User = Depends(get_current_active_user),
) -> UserProfileResponse:
    """Aktualisiert das User-Profil."""
    from app.services.orchestration import get_personalized_thresholds_service

    service = get_personalized_thresholds_service()

    updates = request.model_dump(exclude_unset=True)
    profile = await service.update_profile(current_user.id, updates)

    return UserProfileResponse(
        user_id=str(profile.user_id),
        profession_type=profile.profession_type.value,
        risk_tolerance=profile.risk_tolerance.value,
        income_stability=profile.income_stability,
        age_group=profile.age_group,
        household_size=profile.household_size,
        has_dependents=profile.has_dependents,
        is_homeowner=profile.is_homeowner,
        has_pension_plan=profile.has_pension_plan,
        prefers_aggressive_alerts=profile.prefers_aggressive_alerts,
        prefers_conservative_targets=profile.prefers_conservative_targets,
        created_at=profile.created_at.isoformat(),
        updated_at=profile.updated_at.isoformat(),
    )


@limiter.limit("60/minute", key_func=get_user_identifier)
@router.get(
    "/thresholds",
    response_model=List[UserThresholdResponse],
    summary="Personalisierte Schwellenwerte abrufen",
    description="""
    Ruft alle personalisierten Schwellenwerte des Users ab.

    Die Werte sind basierend auf dem User-Profil berechnet,
    koennen aber individuell ueberschrieben werden.
    """
)
async def get_user_thresholds(
    request: Request,
    category: Optional[str] = Query(None, description="Filter nach Kategorie"),
    current_user: User = Depends(get_current_active_user),
) -> List[UserThresholdResponse]:
    """Ruft alle personalisierten Schwellenwerte ab."""
    from app.services.orchestration import get_personalized_thresholds_service, ThresholdCategory

    service = get_personalized_thresholds_service()

    cat = None
    if category:
        try:
            cat = ThresholdCategory(category)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Ungueltige Kategorie: {category}",
            )

    thresholds = await service.get_all_thresholds(current_user.id, cat)

    return [
        UserThresholdResponse(
            id=str(t.id),
            threshold_type=t.threshold_type.value,
            default_value=t.default_value,
            current_value=t.current_value,
            adjustment_source=t.adjustment_source.value,
            adjustment_reason=t.adjustment_reason,
            confidence=t.confidence,
            effectiveness_score=t.effectiveness_score,
            times_triggered=t.times_triggered,
            times_acted_on=t.times_acted_on,
            created_at=t.created_at.isoformat(),
            updated_at=t.updated_at.isoformat(),
        )
        for t in thresholds
    ]


@limiter.limit("60/minute", key_func=get_user_identifier)
@router.get(
    "/thresholds/{threshold_type}",
    response_model=UserThresholdResponse,
    summary="Einzelnen Schwellenwert abrufen",
    description="Ruft einen einzelnen personalisierten Schwellenwert ab."
)
async def get_user_threshold(
    request: Request,
    threshold_type: str,
    current_user: User = Depends(get_current_active_user),
) -> UserThresholdResponse:
    """Ruft einen einzelnen Schwellenwert ab."""
    from app.services.orchestration import get_personalized_thresholds_service, ThresholdType

    service = get_personalized_thresholds_service()

    try:
        tt = ThresholdType(threshold_type)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Ungueltiger Schwellenwert-Typ: {threshold_type}",
        )

    threshold = await service.get_threshold(current_user.id, tt)
    if not threshold:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Schwellenwert nicht gefunden: {threshold_type}",
        )

    return UserThresholdResponse(
        id=str(threshold.id),
        threshold_type=threshold.threshold_type.value,
        default_value=threshold.default_value,
        current_value=threshold.current_value,
        adjustment_source=threshold.adjustment_source.value,
        adjustment_reason=threshold.adjustment_reason,
        confidence=threshold.confidence,
        effectiveness_score=threshold.effectiveness_score,
        times_triggered=threshold.times_triggered,
        times_acted_on=threshold.times_acted_on,
        created_at=threshold.created_at.isoformat(),
        updated_at=threshold.updated_at.isoformat(),
    )


@limiter.limit("10/minute", key_func=get_user_identifier)
@router.put(
    "/thresholds/{threshold_type}",
    response_model=UserThresholdResponse,
    summary="Schwellenwert setzen",
    description="""
    Setzt einen personalisierten Schwellenwert.

    Der Wert muss innerhalb des erlaubten Bereichs liegen.
    Diese Einstellung ueberschreibt die Profil-basierte Berechnung.
    """
)
async def set_user_threshold(
    fastapi_request: Request,
    threshold_type: str,
    request: SetThresholdRequest,
    current_user: User = Depends(get_current_active_user),
) -> UserThresholdResponse:
    """Setzt einen Schwellenwert."""
    from app.services.orchestration import get_personalized_thresholds_service, ThresholdType

    service = get_personalized_thresholds_service()

    try:
        tt = ThresholdType(threshold_type)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Ungueltiger Schwellenwert-Typ: {threshold_type}",
        )

    try:
        threshold = await service.set_threshold(
            user_id=current_user.id,
            threshold_type=tt,
            value=request.value,
            reason=request.reason,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    return UserThresholdResponse(
        id=str(threshold.id),
        threshold_type=threshold.threshold_type.value,
        default_value=threshold.default_value,
        current_value=threshold.current_value,
        adjustment_source=threshold.adjustment_source.value,
        adjustment_reason=threshold.adjustment_reason,
        confidence=threshold.confidence,
        effectiveness_score=threshold.effectiveness_score,
        times_triggered=threshold.times_triggered,
        times_acted_on=threshold.times_acted_on,
        created_at=threshold.created_at.isoformat(),
        updated_at=threshold.updated_at.isoformat(),
    )


@limiter.limit("10/minute", key_func=get_user_identifier)
@router.post(
    "/thresholds/{threshold_type}/reset",
    response_model=UserThresholdResponse,
    summary="Schwellenwert zuruecksetzen",
    description="""
    Setzt einen Schwellenwert auf den Profil-basierten Default zurueck.

    Dies entfernt alle User-Overrides fuer diesen Schwellenwert.
    """
)
async def reset_user_threshold(
    request: Request,
    threshold_type: str,
    current_user: User = Depends(get_current_active_user),
) -> UserThresholdResponse:
    """Setzt einen Schwellenwert zurueck."""
    from app.services.orchestration import get_personalized_thresholds_service, ThresholdType

    service = get_personalized_thresholds_service()

    try:
        tt = ThresholdType(threshold_type)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Ungueltiger Schwellenwert-Typ: {threshold_type}",
        )

    threshold = await service.reset_threshold(current_user.id, tt)

    return UserThresholdResponse(
        id=str(threshold.id),
        threshold_type=threshold.threshold_type.value,
        default_value=threshold.default_value,
        current_value=threshold.current_value,
        adjustment_source=threshold.adjustment_source.value,
        adjustment_reason=threshold.adjustment_reason,
        confidence=threshold.confidence,
        effectiveness_score=threshold.effectiveness_score,
        times_triggered=threshold.times_triggered,
        times_acted_on=threshold.times_acted_on,
        created_at=threshold.created_at.isoformat(),
        updated_at=threshold.updated_at.isoformat(),
    )


@limiter.limit("10/minute", key_func=get_user_identifier)
@router.post(
    "/thresholds/reset-all",
    response_model=List[UserThresholdResponse],
    summary="Alle Schwellenwerte zuruecksetzen",
    description="Setzt alle Schwellenwerte auf Profil-basierte Defaults zurueck."
)
async def reset_all_thresholds(
    request: Request,
    current_user: User = Depends(get_current_active_user),
) -> List[UserThresholdResponse]:
    """Setzt alle Schwellenwerte zurueck."""
    from app.services.orchestration import get_personalized_thresholds_service

    service = get_personalized_thresholds_service()
    thresholds = await service.reset_all_thresholds(current_user.id)

    return [
        UserThresholdResponse(
            id=str(t.id),
            threshold_type=t.threshold_type.value,
            default_value=t.default_value,
            current_value=t.current_value,
            adjustment_source=t.adjustment_source.value,
            adjustment_reason=t.adjustment_reason,
            confidence=t.confidence,
            effectiveness_score=t.effectiveness_score,
            times_triggered=t.times_triggered,
            times_acted_on=t.times_acted_on,
            created_at=t.created_at.isoformat(),
            updated_at=t.updated_at.isoformat(),
        )
        for t in thresholds
    ]


@limiter.limit("60/minute", key_func=get_user_identifier)
@router.get(
    "/thresholds/recommendations",
    response_model=List[ThresholdRecommendationResponse],
    summary="Schwellenwert-Empfehlungen abrufen",
    description="""
    Ruft ausstehende Empfehlungen fuer Schwellenwert-Anpassungen ab.

    Empfehlungen werden generiert basierend auf:
    - Aktuellem Verhalten des Users
    - KPI-Entwicklung
    - Effektivitaet bisheriger Schwellenwerte
    """
)
async def get_threshold_recommendations(
    request: Request,
    current_user: User = Depends(get_current_active_user),
) -> List[ThresholdRecommendationResponse]:
    """Ruft Schwellenwert-Empfehlungen ab."""
    from app.services.orchestration import get_personalized_thresholds_service

    service = get_personalized_thresholds_service()
    recommendations = await service.get_pending_recommendations(current_user.id)

    return [
        ThresholdRecommendationResponse(
            id=str(r.id),
            threshold_type=r.threshold_type.value,
            current_value=r.current_value,
            recommended_value=r.recommended_value,
            reason=r.reason,
            confidence=r.confidence,
            potential_impact=r.potential_impact,
            created_at=r.created_at.isoformat(),
            expires_at=r.expires_at.isoformat(),
        )
        for r in recommendations
    ]


@limiter.limit("10/minute", key_func=get_user_identifier)
@router.post(
    "/thresholds/recommendations/generate",
    response_model=List[ThresholdRecommendationResponse],
    summary="Schwellenwert-Empfehlungen generieren",
    description="""
    Generiert neue Empfehlungen basierend auf aktuellen KPIs.

    Die KPIs werden analysiert und sinnvolle Anpassungen vorgeschlagen.
    """
)
async def generate_threshold_recommendations(
    request: Request,
    health_score: float = Query(..., ge=0, le=100),
    dti_ratio: Optional[float] = Query(None),
    emergency_fund_months: Optional[float] = Query(None),
    monthly_savings_rate: Optional[float] = Query(None),
    current_user: User = Depends(get_current_active_user),
) -> List[ThresholdRecommendationResponse]:
    """Generiert Schwellenwert-Empfehlungen."""
    from app.services.orchestration import get_personalized_thresholds_service

    service = get_personalized_thresholds_service()

    current_kpis = {
        "health_score": health_score,
    }
    if dti_ratio is not None:
        current_kpis["dti_ratio"] = dti_ratio
    if emergency_fund_months is not None:
        current_kpis["emergency_fund_months"] = emergency_fund_months
    if monthly_savings_rate is not None:
        current_kpis["monthly_savings_rate"] = monthly_savings_rate

    recommendations = await service.generate_threshold_recommendations(
        current_user.id, current_kpis
    )

    return [
        ThresholdRecommendationResponse(
            id=str(r.id),
            threshold_type=r.threshold_type.value,
            current_value=r.current_value,
            recommended_value=r.recommended_value,
            reason=r.reason,
            confidence=r.confidence,
            potential_impact=r.potential_impact,
            created_at=r.created_at.isoformat(),
            expires_at=r.expires_at.isoformat(),
        )
        for r in recommendations
    ]


@limiter.limit("10/minute", key_func=get_user_identifier)
@router.post(
    "/thresholds/recommendations/{recommendation_id}/accept",
    response_model=UserThresholdResponse,
    summary="Empfehlung akzeptieren",
    description="Akzeptiert eine Schwellenwert-Empfehlung und wendet sie an."
)
async def accept_threshold_recommendation(
    request: Request,
    recommendation_id: str,
    current_user: User = Depends(get_current_active_user),
) -> UserThresholdResponse:
    """Akzeptiert eine Empfehlung."""
    from app.services.orchestration import get_personalized_thresholds_service

    service = get_personalized_thresholds_service()

    try:
        rec_uuid = UUID(recommendation_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ungueltige Empfehlungs-ID",
        )

    threshold = await service.accept_recommendation(current_user.id, rec_uuid)
    if not threshold:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Empfehlung nicht gefunden oder bereits verarbeitet",
        )

    return UserThresholdResponse(
        id=str(threshold.id),
        threshold_type=threshold.threshold_type.value,
        default_value=threshold.default_value,
        current_value=threshold.current_value,
        adjustment_source=threshold.adjustment_source.value,
        adjustment_reason=threshold.adjustment_reason,
        confidence=threshold.confidence,
        effectiveness_score=threshold.effectiveness_score,
        times_triggered=threshold.times_triggered,
        times_acted_on=threshold.times_acted_on,
        created_at=threshold.created_at.isoformat(),
        updated_at=threshold.updated_at.isoformat(),
    )


@limiter.limit("10/minute", key_func=get_user_identifier)
@router.post(
    "/thresholds/recommendations/{recommendation_id}/reject",
    summary="Empfehlung ablehnen",
    description="Lehnt eine Schwellenwert-Empfehlung ab."
)
async def reject_threshold_recommendation(
    request: Request,
    recommendation_id: str,
    reason: Optional[str] = Query(None, max_length=500),
    current_user: User = Depends(get_current_active_user),
) -> Dict[str, Any]:
    """Lehnt eine Empfehlung ab."""
    from app.services.orchestration import get_personalized_thresholds_service

    service = get_personalized_thresholds_service()

    try:
        rec_uuid = UUID(recommendation_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ungueltige Empfehlungs-ID",
        )

    success = await service.reject_recommendation(current_user.id, rec_uuid, reason)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Empfehlung nicht gefunden oder bereits verarbeitet",
        )

    return {
        "success": True,
        "message": "Empfehlung abgelehnt",
        "recommendation_id": recommendation_id,
    }


@limiter.limit("60/minute", key_func=get_user_identifier)
@router.get(
    "/thresholds/history",
    response_model=List[ThresholdAdjustmentResponse],
    summary="Anpassungs-Historie abrufen",
    description="Ruft die Historie aller Schwellenwert-Anpassungen ab."
)
async def get_threshold_history(
    request: Request,
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_active_user),
) -> List[ThresholdAdjustmentResponse]:
    """Ruft Anpassungs-Historie ab."""
    from app.services.orchestration import get_personalized_thresholds_service

    service = get_personalized_thresholds_service()
    history = await service.get_adjustment_history(current_user.id, limit)

    return [
        ThresholdAdjustmentResponse(
            id=str(h.id),
            threshold_type=h.threshold_type.value,
            previous_value=h.previous_value,
            new_value=h.new_value,
            adjustment_source=h.adjustment_source.value,
            reason=h.reason,
            confidence=h.confidence,
            applied_at=h.applied_at.isoformat(),
        )
        for h in history
    ]


@limiter.limit("60/minute", key_func=get_user_identifier)
@router.get(
    "/thresholds/stats",
    response_model=ThresholdStatisticsResponse,
    summary="Schwellenwert-Statistiken abrufen",
    description="""
    Ruft Statistiken zu Schwellenwerten ab:
    - Anzahl personalisiert vs. Standard
    - Durchschnittliche Effektivitaet
    - Trigger- und Aktions-Counts
    """
)
async def get_threshold_stats(
    request: Request,
    current_user: User = Depends(get_current_active_user),
) -> ThresholdStatisticsResponse:
    """Ruft Schwellenwert-Statistiken ab."""
    from app.services.orchestration import get_personalized_thresholds_service

    service = get_personalized_thresholds_service()
    stats = await service.get_threshold_statistics(current_user.id)

    return ThresholdStatisticsResponse(
        total_thresholds=stats["total_thresholds"],
        customized_count=stats["customized_count"],
        system_defaults_count=stats["system_defaults_count"],
        average_effectiveness=stats["average_effectiveness"],
        total_triggers=stats["total_triggers"],
        total_actions=stats["total_actions"],
        pending_recommendations=stats["pending_recommendations"],
    )


# =============================================================================
# SEASONALITY DETECTION ENDPOINTS
# =============================================================================

# ----------------------
# Seasonality Pydantic Models
# ----------------------

class SeasonalPatternResponse(BaseModel):
    """Response fuer ein erkanntes saisonales Muster."""
    id: str
    category: str
    season_type: str
    strength: str
    peak_months: List[int]
    peak_weeks: Optional[List[int]] = None
    peak_days: Optional[List[int]] = None
    seasonal_factor: float
    typical_min_factor: float
    typical_max_factor: float
    average_amount: float
    std_deviation: float
    confidence: float
    description: str
    data_points: int
    detected_at: str


class MonthlyExpectationResponse(BaseModel):
    """Response fuer monatliche Erwartungen."""
    month: int
    year: int
    category: str
    expected_amount: float
    expected_range_min: float
    expected_range_max: float
    seasonal_factor: float
    is_peak_season: bool
    expected_events: List[str]
    confidence: float


class SeasonalEventResponse(BaseModel):
    """Response fuer ein saisonales Event."""
    id: str
    name: str
    description: str
    typical_month: int
    typical_day: Optional[int] = None
    flexible_date: bool
    categories_affected: List[str]
    typical_impact: float
    impact_range_min: float
    impact_range_max: float
    is_recurring: bool


class SeasonalAnomalyRequest(BaseModel):
    """Request fuer Anomalie-Analyse."""
    transaction_date: str
    category: str
    amount: float
    historical_avg: Optional[float] = None


class SeasonalAnomalyResponse(BaseModel):
    """Response fuer Anomalie-Analyse mit saisonalem Kontext."""
    id: str
    transaction_date: str
    category: str
    amount: float
    context: str
    has_seasonal_pattern: bool
    expected_amount: float
    expected_range_min: float
    expected_range_max: float
    deviation_percentage: float
    is_true_anomaly: bool
    confidence: float
    explanation: str


class SeasonalForecastResponse(BaseModel):
    """Response fuer saisonale Prognose."""
    id: str
    forecast_date: str
    horizon_months: int
    total_expected: float
    total_range_min: float
    total_range_max: float
    high_expense_months: List[int]
    peak_categories: Dict[int, List[str]]
    overall_confidence: float
    monthly_forecasts: Dict[str, Dict[str, MonthlyExpectationResponse]]


class DetectPatternsRequest(BaseModel):
    """Request fuer Pattern-Erkennung."""
    historical_data: List[Dict[str, Any]]
    min_data_points: int = 12


class AddCustomEventRequest(BaseModel):
    """Request fuer benutzerdefiniertes Event."""
    name: str
    month: int
    categories: List[str]
    typical_impact: float
    description: Optional[str] = None


class SeasonalityStatisticsResponse(BaseModel):
    """Response fuer Saisonalitaets-Statistiken."""
    detected_patterns: int
    strong_patterns: int
    known_events: int
    custom_events: int
    categories_analyzed: List[str]
    average_confidence: float
    peak_months_identified: List[int]


# ----------------------
# Seasonality API Endpoints
# ----------------------

@limiter.limit("5/minute", key_func=get_user_identifier)
@router.post(
    "/seasonality/detect-patterns",
    response_model=List[SeasonalPatternResponse],
    summary="Saisonale Muster erkennen",
    description="""
    Analysiert historische Transaktionsdaten und erkennt saisonale Muster.

    Features:
    - Monatliche Muster (z.B. hohe Heizkosten im Winter)
    - Jaehrliche Zyklen (z.B. Weihnachten, Urlaub)
    - Staerke-Klassifizierung (sehr stark bis schwach)
    - Kombiniert mit bekannten deutschen Mustern

    Input:
    - historical_data: Liste von {date, category, amount}
    - min_data_points: Minimum Datenpunkte pro Kategorie (Standard: 12)
    """
)
async def detect_seasonal_patterns(
    fastapi_request: Request,
    request: DetectPatternsRequest,
    current_user: User = Depends(get_current_active_user),
) -> List[SeasonalPatternResponse]:
    """Erkennt saisonale Muster aus historischen Daten."""
    from app.services.orchestration import get_seasonality_detection_service

    service = get_seasonality_detection_service()
    patterns = await service.detect_patterns(
        user_id=current_user.id,
        historical_data=request.historical_data,
        min_data_points=request.min_data_points,
    )

    return [
        SeasonalPatternResponse(
            id=str(p.id),
            category=p.category.value,
            season_type=p.season_type.value,
            strength=p.strength.value,
            peak_months=p.peak_months,
            peak_weeks=p.peak_weeks,
            peak_days=p.peak_days,
            seasonal_factor=p.seasonal_factor,
            typical_min_factor=p.typical_min_factor,
            typical_max_factor=p.typical_max_factor,
            average_amount=float(p.average_amount),
            std_deviation=float(p.std_deviation),
            confidence=p.confidence,
            description=p.description,
            data_points=p.data_points,
            detected_at=p.detected_at.isoformat(),
        )
        for p in patterns
    ]


@limiter.limit("60/minute", key_func=get_user_identifier)
@router.get(
    "/seasonality/expectations/{month}",
    response_model=List[MonthlyExpectationResponse],
    summary="Monatliche Erwartungen abrufen",
    description="""
    Berechnet erwartete Ausgaben fuer einen bestimmten Monat basierend auf:
    - Erkannten saisonalen Mustern
    - Bekannten deutschen Saisonmustern (Heizung, Urlaub, etc.)
    - Bevorstehenden Events (Weihnachten, Ostern, etc.)

    Parameter:
    - month: Monat (1-12)
    - year: Jahr (optional, Standard: aktuelles Jahr)
    - categories: Komma-getrennte Liste von Kategorien (optional)
    """
)
async def get_monthly_expectations(
    request: Request,
    month: int = Path(..., ge=1, le=12, description="Monat (1-12)"),
    year: Optional[int] = Query(None, description="Jahr"),
    categories: Optional[str] = Query(None, description="Kategorien (komma-getrennt)"),
    current_user: User = Depends(get_current_active_user),
) -> List[MonthlyExpectationResponse]:
    """Berechnet monatliche Erwartungen."""
    from datetime import date
    from app.services.orchestration import get_seasonality_detection_service, CategoryType

    service = get_seasonality_detection_service()

    # Parse year
    target_year = year or date.today().year

    # Parse categories
    category_list = None
    if categories:
        category_list = []
        for cat in categories.split(","):
            try:
                category_list.append(CategoryType(cat.strip()))
            except ValueError:
                pass  # Ignoriere unbekannte Kategorien

    expectations = await service.get_monthly_expectations(
        user_id=current_user.id,
        month=month,
        year=target_year,
        categories=category_list,
    )

    return [
        MonthlyExpectationResponse(
            month=e.month,
            year=e.year,
            category=e.category.value,
            expected_amount=float(e.expected_amount),
            expected_range_min=float(e.expected_range_min),
            expected_range_max=float(e.expected_range_max),
            seasonal_factor=e.seasonal_factor,
            is_peak_season=e.is_peak_season,
            expected_events=e.expected_events,
            confidence=e.confidence,
        )
        for e in expectations
    ]


@limiter.limit("60/minute", key_func=get_user_identifier)
@router.post(
    "/seasonality/analyze-anomaly",
    response_model=SeasonalAnomalyResponse,
    summary="Anomalie mit saisonalem Kontext analysieren",
    description="""
    Analysiert eine potenzielle Anomalie unter Beruecksichtigung des saisonalen Kontexts.

    Das System unterscheidet:
    - EXPECTED_SEASONAL: Erwartet wegen Saison (z.B. hohe Heizkosten im Winter)
    - EXPECTED_EVENT: Erwartet wegen Event (z.B. Weihnachtsgeschenke im Dezember)
    - UNEXPECTED_SEASONAL: Unerwartet trotz Saison (ungewoehnlich hohe Peak-Ausgaben)
    - TRUE_ANOMALY: Echte Anomalie ohne saisonale Erklaerung

    Vorteile:
    - Weniger False Positives bei saisonalen Ausgaben
    - Bessere Erklaerungen fuer User
    - Kontextbewusste Empfehlungen
    """
)
async def analyze_seasonal_anomaly(
    fastapi_request: Request,
    request: SeasonalAnomalyRequest,
    current_user: User = Depends(get_current_active_user),
) -> SeasonalAnomalyResponse:
    """Analysiert Anomalie mit saisonalem Kontext."""
    from datetime import date
    from decimal import Decimal
    from app.services.orchestration import get_seasonality_detection_service, CategoryType

    service = get_seasonality_detection_service()

    # Parse inputs
    tx_date = date.fromisoformat(request.transaction_date)
    try:
        category = CategoryType(request.category)
    except ValueError:
        category = CategoryType.OTHER

    historical_avg = Decimal(str(request.historical_avg)) if request.historical_avg else None

    analysis = await service.analyze_anomaly(
        user_id=current_user.id,
        transaction_date=tx_date,
        category=category,
        amount=Decimal(str(request.amount)),
        historical_avg=historical_avg,
    )

    return SeasonalAnomalyResponse(
        id=str(analysis.id),
        transaction_date=analysis.transaction_date.isoformat(),
        category=analysis.category.value,
        amount=float(analysis.amount),
        context=analysis.context.value,
        has_seasonal_pattern=analysis.seasonal_pattern is not None,
        expected_amount=float(analysis.expected_amount),
        expected_range_min=float(analysis.expected_range[0]),
        expected_range_max=float(analysis.expected_range[1]),
        deviation_percentage=analysis.deviation_percentage,
        is_true_anomaly=analysis.is_true_anomaly,
        confidence=analysis.confidence,
        explanation=analysis.explanation,
    )


@limiter.limit("5/minute", key_func=get_user_identifier)
@router.get(
    "/seasonality/forecast",
    response_model=SeasonalForecastResponse,
    summary="Saisonale Prognose generieren",
    description="""
    Generiert eine saisonale Prognose fuer zukuenftige Monate.

    Beinhaltet:
    - Erwartete Ausgaben pro Kategorie und Monat
    - Gesamtprognose mit Unsicherheitsbereich
    - Monate mit hohen erwarteten Ausgaben
    - Peak-Kategorien pro Monat

    Nuetzlich fuer:
    - Budgetplanung
    - Cash-Flow Vorhersage
    - Fruehwarnung bei teuren Monaten
    """
)
async def generate_seasonal_forecast(
    request: Request,
    horizon_months: int = Query(12, ge=1, le=24, description="Prognose-Horizont in Monaten"),
    current_user: User = Depends(get_current_active_user),
) -> SeasonalForecastResponse:
    """Generiert saisonale Prognose."""
    from app.services.orchestration import get_seasonality_detection_service

    service = get_seasonality_detection_service()
    forecast = await service.generate_forecast(
        user_id=current_user.id,
        horizon_months=horizon_months,
    )

    # Convert monthly forecasts
    monthly_response: Dict[str, Dict[str, MonthlyExpectationResponse]] = {}
    for cat_key, month_dict in forecast.monthly_forecasts.items():
        monthly_response[cat_key] = {}
        for month, exp in month_dict.items():
            monthly_response[cat_key][str(month)] = MonthlyExpectationResponse(
                month=exp.month,
                year=exp.year,
                category=exp.category.value,
                expected_amount=float(exp.expected_amount),
                expected_range_min=float(exp.expected_range_min),
                expected_range_max=float(exp.expected_range_max),
                seasonal_factor=exp.seasonal_factor,
                is_peak_season=exp.is_peak_season,
                expected_events=exp.expected_events,
                confidence=exp.confidence,
            )

    # Convert peak categories
    peak_cats: Dict[int, List[str]] = {}
    for month, cats in forecast.peak_categories.items():
        peak_cats[month] = [c.value for c in cats]

    return SeasonalForecastResponse(
        id=str(forecast.id),
        forecast_date=forecast.forecast_date.isoformat(),
        horizon_months=forecast.horizon_months,
        total_expected=float(forecast.total_expected),
        total_range_min=float(forecast.total_range[0]),
        total_range_max=float(forecast.total_range[1]),
        high_expense_months=forecast.high_expense_months,
        peak_categories=peak_cats,
        overall_confidence=forecast.overall_confidence,
        monthly_forecasts=monthly_response,
    )


@limiter.limit("10/minute", key_func=get_user_identifier)
@router.post(
    "/seasonality/events",
    response_model=SeasonalEventResponse,
    summary="Benutzerdefiniertes Event hinzufuegen",
    description="""
    Fuegt ein benutzerdefiniertes saisonales Event hinzu.

    Beispiele:
    - Geburtstage
    - Jubilaeen
    - Jaehrliche Mitgliedsbeitraege
    - Wiederkehrende Reparaturen

    Das Event wird bei zukuenftigen Prognosen und Anomalie-Analysen beruecksichtigt.
    """
)
async def add_custom_event(
    fastapi_request: Request,
    request: AddCustomEventRequest,
    current_user: User = Depends(get_current_active_user),
) -> SeasonalEventResponse:
    """Fuegt benutzerdefiniertes Event hinzu."""
    from decimal import Decimal
    from app.services.orchestration import get_seasonality_detection_service, CategoryType

    service = get_seasonality_detection_service()

    # Parse categories
    categories = []
    for cat in request.categories:
        try:
            categories.append(CategoryType(cat))
        except ValueError:
            categories.append(CategoryType.OTHER)

    event = await service.add_custom_event(
        user_id=current_user.id,
        name=request.name,
        month=request.month,
        categories=categories,
        typical_impact=Decimal(str(request.typical_impact)),
        description=request.description,
    )

    return SeasonalEventResponse(
        id=str(event.id),
        name=event.name,
        description=event.description,
        typical_month=event.typical_month,
        typical_day=event.typical_day,
        flexible_date=event.flexible_date,
        categories_affected=[c.value for c in event.categories_affected],
        typical_impact=float(event.typical_impact),
        impact_range_min=float(event.impact_range[0]),
        impact_range_max=float(event.impact_range[1]),
        is_recurring=event.is_recurring,
    )


@limiter.limit("60/minute", key_func=get_user_identifier)
@router.get(
    "/seasonality/events/{month}",
    response_model=List[SeasonalEventResponse],
    summary="Events fuer Monat abrufen",
    description="""
    Ruft alle bekannten Events fuer einen bestimmten Monat ab.

    Beinhaltet:
    - System-Events (Weihnachten, Ostern, etc.)
    - Benutzerdefinierte Events
    """
)
async def get_events_for_month(
    request: Request,
    month: int = Path(..., ge=1, le=12, description="Monat (1-12)"),
    current_user: User = Depends(get_current_active_user),
) -> List[SeasonalEventResponse]:
    """Ruft Events fuer einen Monat ab."""
    from app.services.orchestration import get_seasonality_detection_service

    service = get_seasonality_detection_service()
    events = await service.get_events_for_month(
        user_id=current_user.id,
        month=month,
    )

    return [
        SeasonalEventResponse(
            id=str(e.id),
            name=e.name,
            description=e.description,
            typical_month=e.typical_month,
            typical_day=e.typical_day,
            flexible_date=e.flexible_date,
            categories_affected=[c.value for c in e.categories_affected],
            typical_impact=float(e.typical_impact),
            impact_range_min=float(e.impact_range[0]),
            impact_range_max=float(e.impact_range[1]),
            is_recurring=e.is_recurring,
        )
        for e in events
    ]


@limiter.limit("60/minute", key_func=get_user_identifier)
@router.get(
    "/seasonality/known-patterns",
    response_model=Dict[str, Any],
    summary="Bekannte Saisonmuster abrufen",
    description="""
    Ruft alle bekannten deutschen Saisonmuster ab.

    Beinhaltet Muster fuer:
    - Heizkosten (hoehr im Winter)
    - Stromkosten (hoehr im Winter)
    - Urlaubsausgaben (Sommer, Weihnachten)
    - Weihnachtsgeschenke (November/Dezember)
    - Versicherungen (Jahreszahlungen)
    - Steuern (Maerz-Juni)
    - Schulbedarf (August/September)
    - Kleidung (Saisonwechsel)
    """
)
async def get_known_patterns(
    request: Request,
    current_user: User = Depends(get_current_active_user),
) -> Dict[str, Any]:
    """Ruft bekannte Saisonmuster ab."""
    from app.services.orchestration import KNOWN_PATTERNS, KNOWN_EVENTS

    patterns = {}
    for cat, pattern in KNOWN_PATTERNS.items():
        patterns[cat.value] = {
            "peak_months": pattern.get("peak_months", []),
            "low_months": pattern.get("low_months", []),
            "peak_factor": pattern.get("peak_factor", 1.0),
            "low_factor": pattern.get("low_factor", 1.0),
            "description": pattern.get("description", ""),
        }

    events = [
        {
            "name": e.name,
            "description": e.description,
            "typical_month": e.typical_month,
            "categories_affected": [c.value for c in e.categories_affected],
            "typical_impact": float(e.typical_impact),
        }
        for e in KNOWN_EVENTS
    ]

    return {
        "patterns": patterns,
        "events": events,
        "pattern_count": len(patterns),
        "event_count": len(events),
    }


@limiter.limit("60/minute", key_func=get_user_identifier)
@router.get(
    "/seasonality/stats",
    response_model=SeasonalityStatisticsResponse,
    summary="Saisonalitaets-Statistiken abrufen",
    description="""
    Ruft Statistiken zur Saisonalitaets-Erkennung ab:
    - Anzahl erkannter Muster
    - Starke vs. schwache Muster
    - Benutzerdefinierte Events
    - Analysierte Kategorien
    """
)
async def get_seasonality_stats(
    request: Request,
    current_user: User = Depends(get_current_active_user),
) -> SeasonalityStatisticsResponse:
    """Ruft Saisonalitaets-Statistiken ab."""
    from app.services.orchestration import get_seasonality_detection_service

    service = get_seasonality_detection_service()
    stats = await service.get_seasonality_statistics(current_user.id)

    return SeasonalityStatisticsResponse(
        detected_patterns=stats["detected_patterns"],
        strong_patterns=stats["strong_patterns"],
        known_events=stats["known_events"],
        custom_events=stats["custom_events"],
        categories_analyzed=[c.value for c in stats["categories_analyzed"]],
        average_confidence=stats["average_confidence"],
        peak_months_identified=stats["peak_months_identified"],
    )
