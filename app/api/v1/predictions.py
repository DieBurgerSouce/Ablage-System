# -*- coding: utf-8 -*-
"""
Predictive Payment AI API Endpoints.

REST API fuer Zahlungsverhaltens-Vorhersagen:
- Zahlungsverzoegerung-Prognose pro Entity
- Ausfallwahrscheinlichkeit
- Optimale Zahlungsbedingungen
- Cash-Flow-Projektion
- Skonto-Optimierung

Phase 3: Predictive Payment AI
Feinpoliert und durchdacht.
"""

from datetime import datetime, timezone
from typing import Optional, List, Dict
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import User
from app.api.dependencies import get_db, get_current_active_user
from app.core.safe_errors import safe_error_detail, safe_error_log

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/predictions", tags=["Predictive Payment AI"])


# =============================================================================
# Response Models
# =============================================================================


class PaymentDelayPredictionResponse(BaseModel):
    """Response fuer Zahlungsverzoegerungs-Vorhersage."""
    entity_id: str
    predicted_delay_days: float = Field(..., description="Erwartete Verzoegerung in Tagen")
    confidence: float = Field(..., ge=0, le=1, description="Konfidenz der Vorhersage")
    risk_tier: str = Field(..., description="Risiko-Klassifizierung: low/medium/high/critical")
    delay_range_min: float = Field(..., description="Untere Grenze (25. Perzentil)")
    delay_range_max: float = Field(..., description="Obere Grenze (75. Perzentil)")
    prediction_timestamp: datetime
    top_factors: List[Dict] = Field(default_factory=list, description="Wichtigste Einflussfaktoren")


class DefaultProbabilityResponse(BaseModel):
    """Response fuer Ausfallwahrscheinlichkeit."""
    entity_id: str
    default_probability: float = Field(..., ge=0, le=1, description="Ausfallwahrscheinlichkeit")
    confidence: float = Field(..., ge=0, le=1)
    risk_tier: str
    prediction_timestamp: datetime
    contributing_factors: Dict[str, float] = Field(default_factory=dict)


class PaymentTermsSuggestionResponse(BaseModel):
    """Response fuer Zahlungsbedingungen-Empfehlung."""
    entity_id: str
    invoice_amount: float
    suggested_term: str
    suggested_days: int
    suggested_skonto_percentage: float
    suggested_skonto_days: int
    expected_payment_date: datetime
    reasoning: str
    confidence: float


class CashFlowProjectionResponse(BaseModel):
    """Response fuer Cash-Flow-Projektion."""
    projection_date: datetime
    days_ahead: int
    expected_inflow: float
    expected_inflow_min: float
    expected_inflow_max: float
    expected_outflow: float
    net_flow: float
    cumulative_balance: float


class CashFlowSummaryResponse(BaseModel):
    """Zusammenfassung der Cash-Flow-Projektion."""
    generated_at: datetime
    days_ahead: int
    total_expected_inflow: float
    total_expected_inflow_min: float
    total_expected_inflow_max: float
    final_balance: float
    daily_projections: List[CashFlowProjectionResponse]


class SkontoOptimizationResponse(BaseModel):
    """Response fuer Skonto-Optimierung."""
    entity_id: str
    invoice_amount: float
    recommended_percentage: float
    recommended_days: int
    net_payment_days: int
    expected_usage_probability: float
    expected_savings_if_used: float
    expected_cash_advance_days: float
    expected_net_benefit: float
    reasoning: str
    confidence: float


class SkontoImpactResponse(BaseModel):
    """Response fuer Skonto-Impact-Analyse."""
    analysis_date: datetime
    days_analyzed: int
    total_invoices_analyzed: int
    total_skonto_eligible_amount: float
    expected_skonto_usage_amount: float
    expected_total_discount: float
    expected_working_capital_improvement: float
    top_skonto_candidates: List[Dict]


class PredictionFeedbackRequest(BaseModel):
    """Request fuer Vorhersage-Feedback."""
    prediction_type: str = Field(..., description="delay, default, oder terms")
    predicted_value: float
    actual_value: float


class PredictionFeedbackResponse(BaseModel):
    """Response fuer Feedback-Submission."""
    success: bool
    message: str
    was_accurate: bool


# =============================================================================
# Payment Delay Prediction
# =============================================================================


@router.get(
    "/entity/{entity_id}/payment",
    response_model=PaymentDelayPredictionResponse,
    summary="Zahlungsverzoegerung vorhersagen",
    description="Prognostiziert die erwartete Zahlungsverzoegerung fuer einen Geschaeftspartner"
)
async def predict_payment_delay(
    entity_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> PaymentDelayPredictionResponse:
    """
    Vorhersage der Zahlungsverzoegerung fuer einen Geschaeftspartner.

    Basiert auf:
    - Historischem Zahlungsverhalten
    - Aktuelle ausstehende Betraege
    - Mahnhistorie
    - Saisonale Faktoren
    """
    from app.services.ai.predictive_payment_service import (
        get_predictive_payment_service,
    )

    try:
        service = get_predictive_payment_service()
        prediction = await service.predict_payment_delay(db, entity_id)

        return PaymentDelayPredictionResponse(
            entity_id=str(prediction.entity_id),
            predicted_delay_days=prediction.predicted_delay_days,
            confidence=prediction.confidence,
            risk_tier=prediction.risk_tier.value,
            delay_range_min=prediction.delay_range_min,
            delay_range_max=prediction.delay_range_max,
            prediction_timestamp=prediction.prediction_timestamp,
            top_factors=[
                {"factor": f[0], "weight": f[1]}
                for f in prediction.top_factors
            ],
        )

    except Exception as e:
        logger.error(
            "payment_delay_prediction_failed",
            entity_id=str(entity_id),
            **safe_error_log(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=safe_error_detail(e, "Zahlungsvorhersage"),
        )


@router.get(
    "/entity/{entity_id}/default",
    response_model=DefaultProbabilityResponse,
    summary="Ausfallwahrscheinlichkeit vorhersagen",
    description="Prognostiziert die Wahrscheinlichkeit eines Zahlungsausfalls"
)
async def predict_default_probability(
    entity_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> DefaultProbabilityResponse:
    """
    Vorhersage der Ausfallwahrscheinlichkeit fuer einen Geschaeftspartner.

    Faktoren:
    - Ueberfaelligkeitsrate
    - Mahnhistorie
    - Zahlungsverzoegerungen
    - Beziehungsdauer
    """
    from app.services.ai.predictive_payment_service import (
        get_predictive_payment_service,
    )

    try:
        service = get_predictive_payment_service()
        prediction = await service.predict_default_probability(db, entity_id)

        return DefaultProbabilityResponse(
            entity_id=str(prediction.entity_id),
            default_probability=prediction.default_probability,
            confidence=prediction.confidence,
            risk_tier=prediction.risk_tier.value,
            prediction_timestamp=prediction.prediction_timestamp,
            contributing_factors=prediction.contributing_factors,
        )

    except Exception as e:
        logger.error(
            "default_probability_prediction_failed",
            entity_id=str(entity_id),
            **safe_error_log(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=safe_error_detail(e, "Ausfallvorhersage"),
        )


# =============================================================================
# Payment Terms Suggestion
# =============================================================================


@router.get(
    "/entity/{entity_id}/payment-terms",
    response_model=PaymentTermsSuggestionResponse,
    summary="Optimale Zahlungsbedingungen empfehlen",
    description="Empfiehlt optimale Zahlungsbedingungen basierend auf Risikoprofil"
)
async def suggest_payment_terms(
    entity_id: UUID,
    invoice_amount: float = Query(..., gt=0, description="Rechnungsbetrag in EUR"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> PaymentTermsSuggestionResponse:
    """
    Empfiehlt optimale Zahlungsbedingungen fuer einen Geschaeftspartner.

    Beruecksichtigt:
    - Historisches Zahlungsverhalten
    - Risikoniveau
    - Rechnungsbetrag
    - Geschaeftsbeziehung
    """
    from app.services.ai.predictive_payment_service import (
        get_predictive_payment_service,
    )

    try:
        service = get_predictive_payment_service()
        suggestion = await service.suggest_payment_terms(
            db, entity_id, invoice_amount
        )

        return PaymentTermsSuggestionResponse(
            entity_id=str(suggestion.entity_id),
            invoice_amount=suggestion.invoice_amount,
            suggested_term=suggestion.suggested_term.value,
            suggested_days=suggestion.suggested_days,
            suggested_skonto_percentage=suggestion.suggested_skonto_percentage,
            suggested_skonto_days=suggestion.suggested_skonto_days,
            expected_payment_date=suggestion.expected_payment_date,
            reasoning=suggestion.reasoning,
            confidence=suggestion.confidence,
        )

    except Exception as e:
        logger.error(
            "payment_terms_suggestion_failed",
            entity_id=str(entity_id),
            **safe_error_log(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=safe_error_detail(e, "Zahlungsempfehlung"),
        )


# =============================================================================
# Cash Flow Projection
# =============================================================================


@router.get(
    "/cash-flow",
    response_model=CashFlowSummaryResponse,
    summary="Cash-Flow-Prognose abrufen",
    description="Projiziert den Cash-Flow basierend auf ML-Vorhersagen"
)
async def get_cash_flow_forecast(
    days_ahead: int = Query(30, ge=1, le=90, description="Prognosezeitraum in Tagen"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> CashFlowSummaryResponse:
    """
    Cash-Flow-Prognose mit ML-basierten Zahlungsvorhersagen.

    Beruecksichtigt:
    - Offene Rechnungen mit Faelligkeiten
    - Vorhergesagte Zahlungsverzoegerungen
    - Ausfallwahrscheinlichkeiten
    """
    from app.services.ai.predictive_payment_service import (
        get_predictive_payment_service,
    )

    company_id = current_user.company_id
    if not company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Benutzer hat keine Firmenzuordnung",
        )

    try:
        service = get_predictive_payment_service()
        projections = await service.calculate_expected_cash_flow(
            db, company_id, days_ahead=days_ahead
        )

        if not projections:
            return CashFlowSummaryResponse(
                generated_at=datetime.now(timezone.utc),
                days_ahead=days_ahead,
                total_expected_inflow=0.0,
                total_expected_inflow_min=0.0,
                total_expected_inflow_max=0.0,
                final_balance=0.0,
                daily_projections=[],
            )

        total_inflow = sum(p.expected_inflow for p in projections)
        total_inflow_min = sum(p.expected_inflow_min for p in projections)
        total_inflow_max = sum(p.expected_inflow_max for p in projections)
        final_balance = projections[-1].cumulative_balance

        daily_projections = [
            CashFlowProjectionResponse(
                projection_date=p.projection_date,
                days_ahead=p.days_ahead,
                expected_inflow=p.expected_inflow,
                expected_inflow_min=p.expected_inflow_min,
                expected_inflow_max=p.expected_inflow_max,
                expected_outflow=p.expected_outflow,
                net_flow=p.net_flow,
                cumulative_balance=p.cumulative_balance,
            )
            for p in projections
        ]

        return CashFlowSummaryResponse(
            generated_at=datetime.now(timezone.utc),
            days_ahead=days_ahead,
            total_expected_inflow=round(total_inflow, 2),
            total_expected_inflow_min=round(total_inflow_min, 2),
            total_expected_inflow_max=round(total_inflow_max, 2),
            final_balance=round(final_balance, 2),
            daily_projections=daily_projections,
        )

    except Exception as e:
        logger.error(
            "cash_flow_forecast_failed",
            company_id=str(company_id),
            **safe_error_log(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=safe_error_detail(e, "Cash-Flow-Prognose"),
        )


# =============================================================================
# Skonto Optimization
# =============================================================================


@router.get(
    "/skonto-optimization",
    response_model=SkontoImpactResponse,
    summary="Skonto-Impact-Analyse",
    description="Analysiert die Auswirkungen von Skonto auf den Cash-Flow"
)
async def get_skonto_impact(
    days_ahead: int = Query(30, ge=1, le=90, description="Analysezeitraum"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> SkontoImpactResponse:
    """
    Skonto-Impact-Analyse fuer Cash-Flow-Optimierung.

    Zeigt:
    - Erwartete Skonto-Nutzung
    - Working-Capital-Verbesserung
    - Top Skonto-Kandidaten
    """
    from app.services.ai.skonto_optimizer_service import (
        get_skonto_optimizer_service,
    )

    company_id = current_user.company_id
    if not company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Benutzer hat keine Firmenzuordnung",
        )

    try:
        optimizer = get_skonto_optimizer_service()
        analysis = await optimizer.calculate_skonto_impact(
            db, company_id, days_ahead=days_ahead
        )

        return SkontoImpactResponse(
            analysis_date=analysis.analysis_date,
            days_analyzed=analysis.days_analyzed,
            total_invoices_analyzed=analysis.total_invoices_analyzed,
            total_skonto_eligible_amount=round(
                analysis.total_skonto_eligible_amount, 2
            ),
            expected_skonto_usage_amount=round(
                analysis.expected_skonto_usage_amount, 2
            ),
            expected_total_discount=round(analysis.expected_total_discount, 2),
            expected_working_capital_improvement=round(
                analysis.expected_working_capital_improvement, 2
            ),
            top_skonto_candidates=analysis.top_skonto_candidates[:10],
        )

    except Exception as e:
        logger.error(
            "skonto_impact_analysis_failed",
            company_id=str(company_id),
            **safe_error_log(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=safe_error_detail(e, "Skonto-Analyse"),
        )


@router.get(
    "/entity/{entity_id}/skonto-optimization",
    response_model=SkontoOptimizationResponse,
    summary="Optimale Skonto-Konditionen berechnen",
    description="Berechnet optimale Skonto-Konditionen fuer einen Geschaeftspartner"
)
async def optimize_skonto_for_entity(
    entity_id: UUID,
    invoice_amount: Optional[float] = Query(
        None, gt=0, description="Rechnungsbetrag (optional)"
    ),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> SkontoOptimizationResponse:
    """
    Optimiert Skonto-Konditionen fuer einen Geschaeftspartner.

    Optimiert auf:
    - Maximale Wahrscheinlichkeit der Nutzung
    - Positiver NPV fuer das Unternehmen
    """
    from app.services.ai.skonto_optimizer_service import (
        get_skonto_optimizer_service,
    )

    try:
        optimizer = get_skonto_optimizer_service()
        result = await optimizer.optimize_skonto_offer(
            db, entity_id, invoice_amount
        )

        return SkontoOptimizationResponse(
            entity_id=str(result.entity_id),
            invoice_amount=result.invoice_amount,
            recommended_percentage=result.recommended_percentage,
            recommended_days=result.recommended_days,
            net_payment_days=result.net_payment_days,
            expected_usage_probability=result.expected_usage_probability,
            expected_savings_if_used=round(result.expected_savings_if_used, 2),
            expected_cash_advance_days=result.expected_cash_advance_days,
            expected_net_benefit=round(result.expected_net_benefit, 2),
            reasoning=result.reasoning,
            confidence=result.confidence,
        )

    except Exception as e:
        logger.error(
            "skonto_optimization_failed",
            entity_id=str(entity_id),
            **safe_error_log(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=safe_error_detail(e, "Skonto-Optimierung"),
        )


@router.get(
    "/entity/{entity_id}/skonto-usage",
    summary="Skonto-Nutzungswahrscheinlichkeit",
    description="Prognostiziert ob ein Geschaeftspartner Skonto nutzen wird"
)
async def predict_skonto_usage(
    entity_id: UUID,
    skonto_percentage: float = Query(
        2.0, ge=0.5, le=5.0, description="Angebotener Skonto-Prozentsatz"
    ),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Prognostiziert die Wahrscheinlichkeit der Skonto-Nutzung.

    Beruecksichtigt:
    - Historische Skonto-Nutzung
    - Zahlungsverhalten
    - Skonto-Hoehe
    """
    from app.services.ai.skonto_optimizer_service import (
        get_skonto_optimizer_service,
    )

    try:
        optimizer = get_skonto_optimizer_service()
        prediction = await optimizer.predict_skonto_usage(
            db, entity_id, skonto_percentage
        )

        return {
            "entity_id": str(prediction.entity_id),
            "usage_probability": prediction.usage_probability,
            "confidence": prediction.confidence,
            "prediction_timestamp": prediction.prediction_timestamp.isoformat(),
            "historical_usage_rate": prediction.historical_usage_rate,
            "contributing_factors": prediction.contributing_factors,
        }

    except Exception as e:
        logger.error(
            "skonto_usage_prediction_failed",
            entity_id=str(entity_id),
            **safe_error_log(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=safe_error_detail(e, "Skonto-Nutzungsvorhersage"),
        )


# =============================================================================
# Feedback for Learning Loop
# =============================================================================


@router.post(
    "/feedback",
    response_model=PredictionFeedbackResponse,
    summary="Vorhersage-Feedback einreichen",
    description="Meldet tatsaechliche Ergebnisse zurueck fuer kontinuierliches Lernen"
)
async def submit_prediction_feedback(
    entity_id: UUID,
    feedback: PredictionFeedbackRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> PredictionFeedbackResponse:
    """
    Feedback fuer Vorhersagen einreichen.

    Wird fuer das kontinuierliche Lernen der ML-Modelle verwendet.
    Vergleicht Vorhersagen mit tatsaechlichen Ergebnissen.
    """
    from app.services.ai.predictive_payment_service import (
        get_predictive_payment_service,
        PredictionFeedback,
    )
    from uuid import uuid4

    # Validierung
    valid_types = ["delay", "default", "terms"]
    if feedback.prediction_type not in valid_types:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"prediction_type muss einer von {valid_types} sein",
        )

    company_id = current_user.company_id
    if not company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Benutzer hat keine Firmenzuordnung",
        )

    try:
        service = get_predictive_payment_service()

        feedback_obj = PredictionFeedback(
            prediction_id=str(uuid4()),
            entity_id=entity_id,
            prediction_type=feedback.prediction_type,
            predicted_value=feedback.predicted_value,
            actual_value=feedback.actual_value,
        )

        await service.record_prediction_feedback(db, feedback_obj, company_id)

        return PredictionFeedbackResponse(
            success=True,
            message="Feedback erfolgreich gespeichert",
            was_accurate=feedback_obj.was_accurate,
        )

    except Exception as e:
        logger.error(
            "prediction_feedback_failed",
            entity_id=str(entity_id),
            **safe_error_log(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=safe_error_detail(e, "Feedback-Speicherung"),
        )


# =============================================================================
# Batch Operations
# =============================================================================


@router.get(
    "/batch/high-risk-entities",
    summary="Hochrisiko-Geschaeftspartner auflisten",
    description="Listet alle Geschaeftspartner mit hohem Ausfallrisiko"
)
async def list_high_risk_entities(
    risk_threshold: float = Query(
        0.5, ge=0.1, le=0.9, description="Risiko-Schwellenwert"
    ),
    limit: int = Query(50, ge=1, le=200),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Listet Geschaeftspartner mit hohem Ausfallrisiko.

    Nuetzlich fuer:
    - Proaktives Risikomanagement
    - Fokussierte Kundenbetreuung
    - Kreditlimit-Ueberpruefung
    """
    from sqlalchemy import select, and_
    from app.db.models import BusinessEntity
    from app.services.ai.predictive_payment_service import (
        get_predictive_payment_service,
    )

    company_id = current_user.company_id
    if not company_id:
        return {"entities": [], "total": 0}

    try:
        service = get_predictive_payment_service()

        # Hole Entities der Firma
        query = (
            select(BusinessEntity)
            .where(
                and_(
                    BusinessEntity.company_id == company_id,
                    BusinessEntity.is_active == True,
                    BusinessEntity.deleted_at.is_(None),
                )
            )
            .limit(limit * 2)  # Mehr laden fuer Filterung
        )

        result = await db.execute(query)
        entities = result.scalars().all()

        high_risk_entities = []

        for entity in entities:
            try:
                prediction = await service.predict_default_probability(
                    db, entity.id
                )

                if prediction.default_probability >= risk_threshold:
                    high_risk_entities.append({
                        "entity_id": str(entity.id),
                        "default_probability": prediction.default_probability,
                        "risk_tier": prediction.risk_tier.value,
                        "contributing_factors": prediction.contributing_factors,
                    })

                if len(high_risk_entities) >= limit:
                    break

            except Exception as e:
                logger.debug(
                    "high_risk_check_failed",
                    entity_id=str(entity.id),
                    error_type=type(e).__name__,
                )

        # Nach Risiko sortieren
        high_risk_entities.sort(
            key=lambda x: x["default_probability"], reverse=True
        )

        return {
            "entities": high_risk_entities,
            "total": len(high_risk_entities),
            "threshold_used": risk_threshold,
        }

    except Exception as e:
        logger.error(
            "high_risk_entities_failed",
            **safe_error_log(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=safe_error_detail(e, "Hochrisiko-Analyse"),
        )


@router.get(
    "/summary",
    summary="Vorhersage-Zusammenfassung",
    description="Aggregierte Statistiken ueber alle Vorhersagen"
)
async def get_prediction_summary(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Zusammenfassung der Vorhersage-Metriken.

    Zeigt:
    - Durchschnittliche Risiko-Scores
    - Verteilung nach Risiko-Tiers
    - Modell-Performance
    """
    from sqlalchemy import select, func
    from app.db.models import BusinessEntity

    company_id = current_user.company_id
    if not company_id:
        return {
            "error": "Keine Firmenzuordnung",
        }

    try:
        # Zaehle Entities
        count_query = (
            select(func.count(BusinessEntity.id))
            .where(
                and_(
                    BusinessEntity.company_id == company_id,
                    BusinessEntity.is_active == True,
                    BusinessEntity.deleted_at.is_(None),
                )
            )
        )
        count_result = await db.execute(count_query)
        total_entities = count_result.scalar() or 0

        # Durchschnittliche Risk-Scores
        avg_query = (
            select(
                func.avg(BusinessEntity.risk_score).label("avg_risk"),
                func.avg(BusinessEntity.payment_behavior_score).label("avg_payment"),
            )
            .where(
                and_(
                    BusinessEntity.company_id == company_id,
                    BusinessEntity.is_active == True,
                    BusinessEntity.deleted_at.is_(None),
                    BusinessEntity.risk_score.isnot(None),
                )
            )
        )
        avg_result = await db.execute(avg_query)
        avg_row = avg_result.one()

        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "total_entities": total_entities,
            "average_risk_score": round(float(avg_row.avg_risk or 0), 1),
            "average_payment_behavior_score": round(
                float(avg_row.avg_payment or 0), 1
            ),
            "model_version": "1.0.0",
            "model_status": "active",
        }

    except Exception as e:
        logger.error(
            "prediction_summary_failed",
            **safe_error_log(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=safe_error_detail(e, "Vorhersage-Zusammenfassung"),
        )
