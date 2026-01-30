# -*- coding: utf-8 -*-
"""Liquidity Scenario API Endpoints.

API fuer What-If Analyse und Liquiditaets-Szenarien.

Endpoints:
- POST /cashflow/scenarios - Szenario erstellen
- GET /cashflow/scenarios - Szenarien auflisten
- GET /cashflow/scenarios/{id} - Szenario abrufen
- DELETE /cashflow/scenarios/{id} - Szenario loeschen
- GET /cashflow/scenarios/standard - Standard-Szenarien (Best/Worst/Expected)
- POST /cashflow/scenarios/monte-carlo - Monte-Carlo-Simulation
- POST /cashflow/scenarios/compare - Szenarien vergleichen
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user, get_db
from app.api.v1.workflows import get_user_company_id
from app.core.safe_errors import safe_error_detail, safe_error_log
from app.db.models import User
from app.services.finanzki.liquidity_scenario_service import (
    LiquidityScenarioService,
    ScenarioType,
    RiskLevel,
)

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/cashflow/scenarios", tags=["liquidity-scenarios"])


# =============================================================================
# Pydantic Schemas
# =============================================================================


class ScenarioAssumptionCreate(BaseModel):
    """Annahme fuer ein Szenario."""

    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = None
    parameter: str = Field(..., min_length=1, max_length=50)
    value: float
    unit: Optional[str] = None
    impact_type: str = Field(default="multiplicative", pattern="^(multiplicative|additive)$")


class ScenarioCreate(BaseModel):
    """Anfrage fuer Szenario-Erstellung."""

    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    scenario_type: str = Field(default="custom", pattern="^(base|best_case|worst_case|expected|custom)$")
    assumptions: List[ScenarioAssumptionCreate] = Field(default_factory=list)
    forecast_days: int = Field(default=30, ge=7, le=365)


class DailyForecastResponse(BaseModel):
    """Tagesweise Prognose."""

    date: str
    inflows: float
    outflows: float
    net_flow: float
    balance: float


class ScenarioResponse(BaseModel):
    """Szenario-Ergebnis."""

    scenario_id: str
    scenario_type: str
    name: str
    description: str
    assumptions: List[Dict[str, Any]]
    forecast_days: int
    current_balance: float
    min_balance: float
    min_balance_date: str
    max_balance: float
    end_balance: float
    total_inflows: float
    total_outflows: float
    risk_level: str
    warnings: List[str]
    recommendations: List[str]
    created_at: str
    daily_forecast: Optional[List[DailyForecastResponse]] = None


class ScenarioListItem(BaseModel):
    """Szenario in Liste."""

    scenario_id: str
    name: str
    scenario_type: str
    risk_level: str
    min_balance: float
    created_at: str


class ScenarioListResponse(BaseModel):
    """Liste von Szenarien."""

    scenarios: List[ScenarioListItem]
    total: int


class LiquidityCorridorPoint(BaseModel):
    """Punkt im Liquiditaets-Korridor."""

    date: str
    p5: float
    p25: float
    p50: float
    p75: float
    p95: float
    expected: float


class MonteCarloRequest(BaseModel):
    """Anfrage fuer Monte-Carlo-Simulation."""

    forecast_days: int = Field(default=30, ge=7, le=90)
    iterations: int = Field(default=1000, ge=100, le=10000)
    confidence_level: float = Field(default=0.95, ge=0.80, le=0.99)


class MonteCarloResponse(BaseModel):
    """Ergebnis der Monte-Carlo-Simulation."""

    iterations: int
    confidence_level: float
    percentiles: Dict[str, float]
    mean_min_balance: float
    std_dev_min_balance: float
    probability_negative: float
    probability_critical: float
    confidence_corridor: List[Dict[str, Any]]


class CompareRequest(BaseModel):
    """Anfrage fuer Szenario-Vergleich."""

    scenario_ids: List[str] = Field(..., min_length=2, max_length=10)


class ComparisonMetric(BaseModel):
    """Vergleichs-Metrik fuer ein Szenario."""

    min_balance: float
    min_balance_diff: float
    end_balance: float
    end_balance_diff: float
    total_inflows: float
    total_outflows: float
    net_flow: float


class CompareResponse(BaseModel):
    """Ergebnis des Szenario-Vergleichs."""

    scenarios: List[ScenarioResponse]
    base_scenario_id: str
    comparison_metrics: Dict[str, ComparisonMetric]
    corridor: List[LiquidityCorridorPoint]


class StandardScenariosResponse(BaseModel):
    """Standard-Szenarien (Best/Worst/Expected)."""

    scenarios: List[ScenarioResponse]
    corridor: List[LiquidityCorridorPoint]
    summary: Dict[str, Any]


# =============================================================================
# Endpoints
# =============================================================================


@router.post(
    "",
    response_model=ScenarioResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Szenario erstellen",
)
async def create_scenario(
    data: ScenarioCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ScenarioResponse:
    """Erstellt ein neues Liquiditaets-Szenario.

    Annahmen koennen sein:
    - payment_delay: Zahlungsverzoegerung in Tagen
    - payment_speed: Faktor fuer Zahlungsgeschwindigkeit (1.0 = normal)
    - default_rate: Ausfallrate (1.0 = normal, 2.0 = doppelt)
    - extra_costs: Zusaetzliche Kosten in EUR
    - inflow_change: Aenderung der Eingaenge (multiplikativ oder additiv)
    - outflow_change: Aenderung der Ausgaenge (multiplikativ oder additiv)
    """
    company_id = await get_user_company_id(db, current_user)
    if not company_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Benutzer muss einer Firma zugeordnet sein",
        )

    service = LiquidityScenarioService(db)

    try:
        scenario_type = ScenarioType(data.scenario_type)
    except ValueError:
        scenario_type = ScenarioType.CUSTOM

    assumptions = [
        {
            "name": a.name,
            "description": a.description,
            "parameter": a.parameter,
            "value": a.value,
            "unit": a.unit,
            "impact_type": a.impact_type,
        }
        for a in data.assumptions
    ]

    result = await service.create_scenario(
        company_id=company_id,
        name=data.name,
        scenario_type=scenario_type,
        assumptions=assumptions,
        forecast_days=data.forecast_days,
        description=data.description,
    )

    return _convert_scenario_to_response(result, include_daily=True)


@router.get(
    "",
    response_model=ScenarioListResponse,
    summary="Szenarien auflisten",
)
async def list_scenarios(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ScenarioListResponse:
    """Listet alle gespeicherten Szenarien."""
    company_id = await get_user_company_id(db, current_user)
    if not company_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Benutzer muss einer Firma zugeordnet sein",
        )

    service = LiquidityScenarioService(db)
    scenarios = await service.list_scenarios(company_id)

    return ScenarioListResponse(
        scenarios=[
            ScenarioListItem(
                scenario_id=s["scenario_id"],
                name=s["name"],
                scenario_type=s["scenario_type"],
                risk_level=s["risk_level"],
                min_balance=s["min_balance"],
                created_at=s["created_at"],
            )
            for s in scenarios
        ],
        total=len(scenarios),
    )


@router.get(
    "/standard",
    response_model=StandardScenariosResponse,
    summary="Standard-Szenarien abrufen",
)
async def get_standard_scenarios(
    forecast_days: int = Query(default=30, ge=7, le=90),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> StandardScenariosResponse:
    """Erstellt und gibt Standard-Szenarien zurueck.

    Generiert automatisch:
    - Base Case (aktuelle Prognose)
    - Best Case (optimistisch)
    - Worst Case (pessimistisch)
    - Expected Case (wahrscheinlichstes Szenario)
    """
    company_id = await get_user_company_id(db, current_user)
    if not company_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Benutzer muss einer Firma zugeordnet sein",
        )

    service = LiquidityScenarioService(db)

    comparison = await service.get_standard_scenarios(
        company_id=company_id,
        forecast_days=forecast_days,
    )

    scenarios = [
        _convert_scenario_to_response(s, include_daily=False)
        for s in comparison.scenarios
    ]

    corridor = [
        LiquidityCorridorPoint(
            date=c.date,
            p5=c.p5,
            p25=c.p25,
            p50=c.p50,
            p75=c.p75,
            p95=c.p95,
            expected=c.expected,
        )
        for c in comparison.corridor
    ]

    # Zusammenfassung
    base = next((s for s in comparison.scenarios if s.scenario_type == ScenarioType.BASE), None)
    worst = next((s for s in comparison.scenarios if s.scenario_type == ScenarioType.WORST_CASE), None)
    best = next((s for s in comparison.scenarios if s.scenario_type == ScenarioType.BEST_CASE), None)

    summary = {
        "base_min_balance": base.min_balance if base else 0,
        "worst_min_balance": worst.min_balance if worst else 0,
        "best_min_balance": best.min_balance if best else 0,
        "spread": (best.min_balance if best else 0) - (worst.min_balance if worst else 0),
    }

    return StandardScenariosResponse(
        scenarios=scenarios,
        corridor=corridor,
        summary=summary,
    )


@router.get(
    "/{scenario_id}",
    response_model=ScenarioResponse,
    summary="Szenario abrufen",
)
async def get_scenario(
    scenario_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ScenarioResponse:
    """Ruft ein gespeichertes Szenario ab."""
    company_id = await get_user_company_id(db, current_user)
    if not company_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Benutzer muss einer Firma zugeordnet sein",
        )

    service = LiquidityScenarioService(db)

    result = await service.get_scenario(company_id, scenario_id)

    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Szenario nicht gefunden",
        )

    return _convert_scenario_to_response(result, include_daily=True)


@router.delete(
    "/{scenario_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    summary="Szenario loeschen",
)
async def delete_scenario(
    scenario_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Loescht ein gespeichertes Szenario."""
    company_id = await get_user_company_id(db, current_user)
    if not company_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Benutzer muss einer Firma zugeordnet sein",
        )

    service = LiquidityScenarioService(db)

    success = await service.delete_scenario(company_id, scenario_id)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Szenario nicht gefunden",
        )


@router.post(
    "/monte-carlo",
    response_model=MonteCarloResponse,
    summary="Monte-Carlo-Simulation",
)
async def run_monte_carlo(
    data: MonteCarloRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> MonteCarloResponse:
    """Fuehrt Monte-Carlo-Simulation fuer Cashflow-Prognose durch.

    Simuliert viele zufaellige Szenarien um:
    - Wahrscheinlichkeitsverteilung des Minimum-Saldos zu berechnen
    - Risiko eines negativen Saldos zu quantifizieren
    - Konfidenz-Korridor zu erstellen
    """
    company_id = await get_user_company_id(db, current_user)
    if not company_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Benutzer muss einer Firma zugeordnet sein",
        )

    service = LiquidityScenarioService(db)

    result = await service.run_monte_carlo(
        company_id=company_id,
        forecast_days=data.forecast_days,
        iterations=data.iterations,
        confidence_level=data.confidence_level,
    )

    return MonteCarloResponse(
        iterations=result.iterations,
        confidence_level=result.confidence_level,
        percentiles=result.percentiles,
        mean_min_balance=result.mean_min_balance,
        std_dev_min_balance=result.std_dev_min_balance,
        probability_negative=result.probability_negative,
        probability_critical=result.probability_critical,
        confidence_corridor=result.confidence_corridor,
    )


@router.post(
    "/compare",
    response_model=CompareResponse,
    summary="Szenarien vergleichen",
)
async def compare_scenarios(
    data: CompareRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> CompareResponse:
    """Vergleicht mehrere Szenarien miteinander.

    Das erste Szenario in der Liste wird als Basis fuer den Vergleich verwendet.
    """
    company_id = await get_user_company_id(db, current_user)
    if not company_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Benutzer muss einer Firma zugeordnet sein",
        )

    service = LiquidityScenarioService(db)

    try:
        comparison = await service.compare_scenarios(
            company_id=company_id,
            scenario_ids=data.scenario_ids,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=safe_error_detail(e, "Liquiditäts-Szenario"),
        )

    scenarios = [
        _convert_scenario_to_response(s, include_daily=False)
        for s in comparison.scenarios
    ]

    corridor = [
        LiquidityCorridorPoint(
            date=c.date,
            p5=c.p5,
            p25=c.p25,
            p50=c.p50,
            p75=c.p75,
            p95=c.p95,
            expected=c.expected,
        )
        for c in comparison.corridor
    ]

    metrics = {
        sid: ComparisonMetric(
            min_balance=m["min_balance"],
            min_balance_diff=m["min_balance_diff"],
            end_balance=m["end_balance"],
            end_balance_diff=m["end_balance_diff"],
            total_inflows=m["total_inflows"],
            total_outflows=m["total_outflows"],
            net_flow=m["net_flow"],
        )
        for sid, m in comparison.comparison_metrics.items()
    }

    return CompareResponse(
        scenarios=scenarios,
        base_scenario_id=comparison.base_scenario_id,
        comparison_metrics=metrics,
        corridor=corridor,
    )


# =============================================================================
# Helper Functions
# =============================================================================


def _convert_scenario_to_response(
    result: Any,
    include_daily: bool = False,
) -> ScenarioResponse:
    """Konvertiert ScenarioResult zu Response-Schema."""
    assumptions = [
        {
            "name": a.name,
            "parameter": a.parameter,
            "value": a.value,
            "unit": a.unit,
        }
        for a in result.assumptions
    ]

    daily = None
    if include_daily and result.daily_forecast:
        daily = [
            DailyForecastResponse(
                date=d.get("date", ""),
                inflows=d.get("inflows", 0),
                outflows=d.get("outflows", 0),
                net_flow=d.get("net_flow", 0),
                balance=d.get("balance", 0),
            )
            for d in result.daily_forecast
        ]

    return ScenarioResponse(
        scenario_id=result.scenario_id,
        scenario_type=result.scenario_type.value,
        name=result.name,
        description=result.description or "",
        assumptions=assumptions,
        forecast_days=result.forecast_days,
        current_balance=result.current_balance,
        min_balance=result.min_balance,
        min_balance_date=result.min_balance_date,
        max_balance=result.max_balance,
        end_balance=result.end_balance,
        total_inflows=result.total_inflows,
        total_outflows=result.total_outflows,
        risk_level=result.risk_level.value,
        warnings=result.warnings,
        recommendations=result.recommendations,
        created_at=result.created_at.isoformat(),
        daily_forecast=daily,
    )
