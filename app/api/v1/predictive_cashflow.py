"""
Predictive Cash-Flow API Endpoints.

API fuer ML-basierte Cashflow-Vorhersagen.

Endpoints:
- GET /cashflow/forecast - Liquiditaetsprognose
- GET /cashflow/predict/{invoice_id} - Zahlungsvorhersage fuer Rechnung
- GET /cashflow/recommendations - Zahlungsempfehlungen
- POST /cashflow/scenario - What-If Szenario-Analyse

Created: 2026-01-19
"""

from datetime import datetime, timezone
from typing import Optional, List, Dict

from app.core.types import JSONDict
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user, get_db
from app.db.models import User
from app.services.finanzki.predictive_cashflow_service import PredictiveCashFlowService

router = APIRouter(prefix="/cashflow", tags=["Predictive Cash-Flow"])


# ==================== Pydantic Models ====================


class PaymentPredictionResponse(BaseModel):
    """Zahlungsvorhersage fuer eine Rechnung."""
    invoice_id: str
    predicted_date: str
    predicted_days: int
    confidence: float
    delay_probability: float
    factors: JSONDict


class ForecastDayResponse(BaseModel):
    """Prognose fuer einen Tag."""
    date: str
    inflows: float
    outflows: float
    net_flow: float
    balance: float
    is_warning: bool
    is_critical: bool


class LiquidityWarningResponse(BaseModel):
    """Liquiditaetswarnung."""
    type: str
    date: str
    message: str


class LiquidityForecastResponse(BaseModel):
    """Liquiditaetsprognose."""
    company_id: str
    forecast_days: int
    current_balance: float
    min_balance: float
    min_balance_date: str
    total_expected_inflows: float
    total_expected_outflows: float
    forecast: List[ForecastDayResponse]
    warnings: List[LiquidityWarningResponse]
    currency: str


class PaymentRecommendationResponse(BaseModel):
    """Zahlungsempfehlung."""
    invoice_id: str
    invoice_number: Optional[str] = None
    amount: float
    due_date: Optional[str] = None
    days_until_due: int
    urgency: str
    recommendation: str
    reason: str
    skonto_savings: float
    skonto_deadline: Optional[str] = None


class ScenarioRequest(BaseModel):
    """Request fuer Szenario-Analyse."""
    scenario_type: str = Field(
        ...,
        pattern="^(delayed_payments|large_expense|revenue_drop)$",
        description="Szenario-Typ"
    )
    parameters: JSONDict = Field(
        default_factory=dict,
        description="Szenario-spezifische Parameter"
    )


class ScenarioResponse(BaseModel):
    """Ergebnis einer Szenario-Analyse."""
    scenario_type: str
    parameters: JSONDict
    base_min_balance: float
    scenario_min_balance: float
    forecast: List[ForecastDayResponse]
    impact: str


# ==================== Endpoints ====================


@router.get(
    "/forecast",
    response_model=LiquidityForecastResponse,
    summary="Liquiditaetsprognose",
    description="Erstellt eine Liquiditaetsprognose fuer die naechsten X Tage.",
)
async def get_liquidity_forecast(
    days: int = Query(30, ge=7, le=90, description="Prognosezeitraum in Tagen"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Hole Liquiditaetsprognose."""
    if not current_user.current_company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Keine Company ausgewaehlt"
        )

    service = PredictiveCashFlowService(db)
    forecast = await service.forecast_liquidity(
        company_id=current_user.current_company_id,
        days=days,
    )

    return LiquidityForecastResponse(
        company_id=forecast["company_id"],
        forecast_days=forecast["forecast_days"],
        current_balance=forecast["current_balance"],
        min_balance=forecast["min_balance"],
        min_balance_date=forecast["min_balance_date"],
        total_expected_inflows=forecast["total_expected_inflows"],
        total_expected_outflows=forecast["total_expected_outflows"],
        forecast=[ForecastDayResponse(**f) for f in forecast["forecast"]],
        warnings=[LiquidityWarningResponse(**w) for w in forecast["warnings"]],
        currency=forecast["currency"],
    )


@router.get(
    "/predict/{invoice_id}",
    response_model=PaymentPredictionResponse,
    summary="Zahlungsvorhersage",
    description="Vorhersage des Zahlungseingangs fuer eine Rechnung.",
)
async def predict_payment(
    invoice_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Vorhersage fuer eine einzelne Rechnung."""
    service = PredictiveCashFlowService(db)
    prediction = await service.predict_payment_date(invoice_id)

    if "error" in prediction:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=prediction["error"]
        )

    return PaymentPredictionResponse(**prediction)


@router.get(
    "/recommendations",
    response_model=List[PaymentRecommendationResponse],
    summary="Zahlungsempfehlungen",
    description="Empfehlungen fuer optimale Zahlungszeitpunkte.",
)
async def get_payment_recommendations(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Hole Zahlungsempfehlungen."""
    if not current_user.current_company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Keine Company ausgewaehlt"
        )

    service = PredictiveCashFlowService(db)
    recommendations = await service.get_payment_recommendations(
        company_id=current_user.current_company_id,
    )

    return [PaymentRecommendationResponse(**r) for r in recommendations]


@router.post(
    "/scenario",
    response_model=ScenarioResponse,
    summary="Szenario-Analyse",
    description="What-If Szenario-Analyse fuer Liquiditaetsplanung.",
)
async def run_scenario(
    request: ScenarioRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Fuehre What-If Szenario aus."""
    if not current_user.current_company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Keine Company ausgewaehlt"
        )

    service = PredictiveCashFlowService(db)
    result = await service.run_scenario(
        company_id=current_user.current_company_id,
        scenario_type=request.scenario_type,
        parameters=request.parameters,
    )

    if "error" in result:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result["error"]
        )

    return ScenarioResponse(
        scenario_type=result["scenario_type"],
        parameters=result["parameters"],
        base_min_balance=result["base_min_balance"],
        scenario_min_balance=result["scenario_min_balance"],
        forecast=[ForecastDayResponse(**f) for f in result["forecast"]],
        impact=result["impact"],
    )


@router.get(
    "/summary",
    summary="Cashflow-Zusammenfassung",
    description="Kurze Zusammenfassung der aktuellen Liquiditaetssituation.",
)
async def get_cashflow_summary(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Hole Cashflow-Zusammenfassung."""
    if not current_user.current_company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Keine Company ausgewaehlt"
        )

    service = PredictiveCashFlowService(db)

    # 7-Tage und 30-Tage Prognose
    forecast_7 = await service.forecast_liquidity(
        company_id=current_user.current_company_id,
        days=7,
    )
    forecast_30 = await service.forecast_liquidity(
        company_id=current_user.current_company_id,
        days=30,
    )

    # Zahlungsempfehlungen
    recommendations = await service.get_payment_recommendations(
        company_id=current_user.current_company_id,
    )

    # Dringende Empfehlungen zaehlen
    urgent_count = sum(1 for r in recommendations if r["urgency"] in ["critical", "overdue"])
    skonto_total = sum(r["skonto_savings"] for r in recommendations if r["skonto_savings"] > 0)

    return {
        "current_balance": forecast_7["current_balance"],
        "min_balance_7d": forecast_7["min_balance"],
        "min_balance_30d": forecast_30["min_balance"],
        "expected_inflows_7d": forecast_7["total_expected_inflows"],
        "expected_outflows_7d": forecast_7["total_expected_outflows"],
        "warnings_count": len(forecast_30["warnings"]),
        "urgent_payments": urgent_count,
        "potential_skonto_savings": round(skonto_total, 2),
        "currency": "EUR",
        "status": "critical" if forecast_7["min_balance"] < 0 else "warning" if forecast_30["min_balance"] < 0 else "healthy",
    }
