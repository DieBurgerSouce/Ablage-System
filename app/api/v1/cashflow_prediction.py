# -*- coding: utf-8 -*-
"""
Cashflow Prediction API Endpoints.

Enterprise Feature: Februar 2026

Endpoints:
- GET /forecast - Liquiditaetsprognose mit Monte Carlo Simulation
- GET /warnings - Cashflow-Warnungen und Empfehlungen
- POST /scenario - What-If Szenario-Simulation
- GET /metrics - Vorhersagegenauigkeit-Metriken
- GET /payment-delays - Zahlungsverhaltens-Analyse

SECURITY:
- Alle Endpoints erfordern Authentifizierung
- Company-Isolation via get_current_company_id
- Keine PII in Responses (Entity-Namen nur mit Berechtigung)

Feinpoliert und durchdacht.
"""

import datetime as dt
from datetime import date, datetime
from decimal import Decimal
from typing import Dict, List, Optional

from app.core.types import JSONDict
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user, get_db, get_company_id
from app.db.models import User
from app.services.ai.cashflow_prediction_service import (
    CashflowPredictionService,
    ScenarioType,
    WarningSeverity,
    WarningType,
    get_cashflow_prediction_service,
)

router = APIRouter(prefix="/cashflow-prediction", tags=["Cashflow Prediction"])


# =============================================================================
# PYDANTIC MODELS - Request/Response Schemas
# =============================================================================


class CashflowForecastItem(BaseModel):
    """Einzelner Tag der Cashflow-Prognose."""

    date: dt.date = Field(..., description="Datum der Prognose")
    predicted_balance: float = Field(..., description="Vorhergesagter Kontostand in EUR")
    lower_bound: float = Field(..., description="Untere Grenze des Konfidenzintervalls")
    upper_bound: float = Field(..., description="Obere Grenze des Konfidenzintervalls")
    incoming: float = Field(..., description="Erwartete Eingaenge in EUR")
    outgoing: float = Field(..., description="Erwartete Ausgaenge in EUR")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Konfidenz der Vorhersage (0-1)")
    incoming_count: int = Field(0, description="Anzahl erwarteter Eingaenge")
    outgoing_count: int = Field(0, description="Anzahl erwarteter Ausgaenge")

    class Config:
        json_schema_extra = {
            "example": {
                "date": "2026-02-15",
                "predicted_balance": 25430.50,
                "lower_bound": 18500.00,
                "upper_bound": 32000.00,
                "incoming": 5000.00,
                "outgoing": 3200.00,
                "confidence": 0.85,
                "incoming_count": 2,
                "outgoing_count": 1,
            }
        }


class CashflowForecastResponse(BaseModel):
    """Response für Cashflow-Prognose."""

    company_id: str = Field(..., description="Mandanten-ID")
    forecast_days: int = Field(..., description="Prognosezeitraum in Tagen")
    confidence_level: float = Field(..., description="Verwendetes Konfidenzintervall")
    current_balance: float = Field(..., description="Aktueller Kontostand in EUR")
    min_balance: float = Field(..., description="Minimaler vorhergesagter Kontostand")
    min_balance_date: dt.date = Field(..., description="Datum des minimalen Kontostands")
    avg_balance: float = Field(..., description="Durchschnittlicher vorhergesagter Kontostand")
    total_expected_inflows: float = Field(..., description="Summe erwarteter Eingaenge")
    total_expected_outflows: float = Field(..., description="Summe erwarteter Ausgaenge")
    forecast: List[CashflowForecastItem] = Field(..., description="Tagesweise Prognose")
    generated_at: datetime = Field(..., description="Zeitpunkt der Generierung")
    currency: str = Field("EUR", description="Währung")


class CashflowWarningItem(BaseModel):
    """Einzelne Cashflow-Warnung."""

    type: str = Field(..., description="Warnungstyp")
    severity: str = Field(..., description="Schweregrad: info, warning, critical")
    date: dt.date = Field(..., description="Datum des erwarteten Problems")
    predicted_balance: float = Field(..., description="Vorhergesagter Kontostand an diesem Tag")
    message: str = Field(..., description="Warnungsmeldung (Deutsch)")
    suggested_actions: List[str] = Field(..., description="Handlungsempfehlungen (Deutsch)")
    days_until_trigger: int = Field(0, description="Tage bis zum Problem")
    affected_amount: Optional[float] = Field(None, description="Betroffener Betrag in EUR")

    class Config:
        json_schema_extra = {
            "example": {
                "type": "shortfall",
                "severity": "critical",
                "date": "2026-02-20",
                "predicted_balance": -2500.00,
                "message": "Kritischer Liquiditaetsengpass am 20.02.2026: Prognostizierter Saldo -2.500,00 EUR",
                "suggested_actions": [
                    "Zahlungseingaenge beschleunigen (Skonto anbieten)",
                    "Nicht-kritische Zahlungen verschieben",
                ],
                "days_until_trigger": 19,
                "affected_amount": 2500.00,
            }
        }


class CashflowWarningsResponse(BaseModel):
    """Response für Cashflow-Warnungen."""

    company_id: str = Field(..., description="Mandanten-ID")
    warning_count: int = Field(..., description="Anzahl Warnungen")
    critical_count: int = Field(..., description="Anzahl kritischer Warnungen")
    warnings: List[CashflowWarningItem] = Field(..., description="Liste der Warnungen")
    generated_at: datetime = Field(..., description="Zeitpunkt der Generierung")


class ScenarioRequest(BaseModel):
    """Request für Szenario-Simulation."""

    scenario_type: str = Field(
        ...,
        description="Art des Szenarios: customer_late_payment, delay_outgoing, new_order, customer_default, accelerate_collection"
    )
    parameters: JSONDict = Field(
        default_factory=dict,
        description="Szenario-spezifische Parameter"
    )

    @field_validator("scenario_type")
    @classmethod
    def validate_scenario_type(cls, v: str) -> str:
        valid_types = [st.value for st in ScenarioType]
        if v not in valid_types:
            raise ValueError(f"Ungültiger Szenario-Typ. Erlaubt: {valid_types}")
        return v

    class Config:
        json_schema_extra = {
            "example": {
                "scenario_type": "customer_late_payment",
                "parameters": {
                    "entity_id": "123e4567-e89b-12d3-a456-426614174000",
                    "delay_days": 14
                }
            }
        }


class ScenarioResponse(BaseModel):
    """Response für Szenario-Simulation."""

    scenario_type: str = Field(..., description="Art des Szenarios")
    description: str = Field(..., description="Beschreibung des Szenarios (Deutsch)")
    impact_on_min_balance: float = Field(..., description="Auswirkung auf minimalen Kontostand in EUR")
    impact_on_avg_balance: float = Field(..., description="Auswirkung auf durchschnittlichen Kontostand in EUR")
    risk_assessment: str = Field(..., description="Risikobewertung (Deutsch)")
    recommendations: List[str] = Field(..., description="Empfehlungen (Deutsch)")
    forecast: List[CashflowForecastItem] = Field(..., description="Neue Prognose unter diesem Szenario")


class PredictionMetricsResponse(BaseModel):
    """Response für Vorhersage-Metriken."""

    total_predictions: int = Field(..., description="Gesamtzahl ausgewerteter Vorhersagen")
    correct_predictions: int = Field(..., description="Anzahl korrekter Vorhersagen")
    mean_absolute_error_days: float = Field(..., description="Mittlerer absoluter Fehler in Tagen")
    accuracy_rate: float = Field(..., description="Genauigkeitsrate in Prozent")
    last_evaluated: datetime = Field(..., description="Zeitpunkt der letzten Auswertung")


class PaymentDelayStatsItem(BaseModel):
    """Zahlungsverhaltens-Statistiken für einen Kunden."""

    entity_id: str = Field(..., description="Entity-ID (anonymisiert)")
    average_delay_days: float = Field(..., description="Durchschnittliche Zahlungsverzögerung in Tagen")
    std_deviation: float = Field(..., description="Standardabweichung in Tagen")
    sample_count: int = Field(..., description="Anzahl ausgewerteter Zahlungen")
    payment_behavior_score: float = Field(..., ge=0, le=100, description="Zahlungsverhalten-Score (0-100, höher=besser)")
    risk_score: float = Field(..., ge=0, le=100, description="Risiko-Score (0-100, höher=riskanter)")
    last_payment_date: Optional[datetime] = Field(None, description="Datum der letzten Zahlung")


class PaymentDelayAnalysisResponse(BaseModel):
    """Response für Zahlungsverhaltens-Analyse."""

    company_id: str = Field(..., description="Mandanten-ID")
    entity_count: int = Field(..., description="Anzahl analysierter Kunden")
    high_risk_count: int = Field(..., description="Anzahl Hochrisiko-Kunden (Score > 50)")
    stats: List[PaymentDelayStatsItem] = Field(..., description="Statistiken pro Kunde")
    generated_at: datetime = Field(..., description="Zeitpunkt der Generierung")


# =============================================================================
# API ENDPOINTS
# =============================================================================


@router.get(
    "/forecast",
    response_model=CashflowForecastResponse,
    summary="Liquiditaetsprognose",
    description="""
    Erstellt eine detaillierte Cashflow-Prognose für die nächsten 7-90 Tage.

    Verwendet Monte Carlo Simulation für probabilistische Vorhersagen mit
    Konfidenzintervallen. Berücksichtigt:
    - Offene Forderungen mit kundenspezifischen Zahlungswahrscheinlichkeiten
    - Offene Verbindlichkeiten inkl. Skonto-Optimierung
    - Wiederkehrende Zahlungsmuster

    **Response:**
    - `forecast`: Tagesweise Prognose mit Unsicherheitsbereichen
    - `min_balance`: Niedrigster vorhergesagter Kontostand (kritischer Indikator)
    - `confidence_level`: Verwendetes Konfidenzintervall (Standard: 90%)
    """,
    responses={
        200: {"description": "Prognose erfolgreich erstellt"},
        400: {"description": "Ungültige Parameter"},
        401: {"description": "Nicht authentifiziert"},
    },
)
async def get_cashflow_forecast(
    days: int = Query(
        default=30,
        ge=7,
        le=90,
        description="Prognosezeitraum in Tagen (7-90)"
    ),
    confidence_level: float = Query(
        default=0.9,
        ge=0.8,
        le=0.99,
        description="Konfidenzintervall (0.8-0.99)"
    ),
    include_recurring: bool = Query(
        default=True,
        description="Wiederkehrende Muster einbeziehen"
    ),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    company_id: UUID = Depends(get_company_id),
):
    """Hole Cashflow-Prognose für die nächsten X Tage."""
    service = get_cashflow_prediction_service(db)

    forecasts = await service.get_cashflow_forecast(
        company_id=company_id,
        days=days,
        confidence_level=confidence_level,
        include_recurring=include_recurring,
    )

    if not forecasts:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Keine Daten für Prognose verfügbar"
        )

    # Berechnungen für Response
    min_forecast = min(forecasts, key=lambda f: f.predicted_balance)
    total_inflows = sum(f.incoming for f in forecasts)
    total_outflows = sum(f.outgoing for f in forecasts)
    avg_balance = sum(f.predicted_balance for f in forecasts) / len(forecasts)

    return CashflowForecastResponse(
        company_id=str(company_id),
        forecast_days=days,
        confidence_level=confidence_level,
        current_balance=float(forecasts[0].predicted_balance) if forecasts else 0.0,
        min_balance=float(min_forecast.predicted_balance),
        min_balance_date=min_forecast.date,
        avg_balance=round(float(avg_balance), 2),
        total_expected_inflows=round(float(total_inflows), 2),
        total_expected_outflows=round(float(total_outflows), 2),
        forecast=[
            CashflowForecastItem(
                date=f.date,
                predicted_balance=round(float(f.predicted_balance), 2),
                lower_bound=round(float(f.lower_bound), 2),
                upper_bound=round(float(f.upper_bound), 2),
                incoming=round(float(f.incoming), 2),
                outgoing=round(float(f.outgoing), 2),
                confidence=round(float(f.confidence), 2),
                incoming_count=f.incoming_count,
                outgoing_count=f.outgoing_count,
            )
            for f in forecasts
        ],
        generated_at=datetime.now(),
        currency="EUR",
    )


@router.get(
    "/warnings",
    response_model=CashflowWarningsResponse,
    summary="Cashflow-Warnungen",
    description="""
    Generiert Warnungen für bevorstehende Cashflow-Probleme.

    **Warnungstypen:**
    - `shortfall`: Liquiditaetsengpass (negatives Konto)
    - `low_balance`: Niedriger Kontostand
    - `large_outgoing`: Grosse anstehende Zahlung
    - `trend_negative`: Negativer Liquiditaetstrend
    - `high_uncertainty`: Hohe Prognoseunsicherheit

    **Schweregrade:**
    - `critical`: Sofortige Aktion erforderlich
    - `warning`: Aufmerksamkeit erforderlich
    - `info`: Informativ
    """,
    responses={
        200: {"description": "Warnungen erfolgreich generiert"},
        401: {"description": "Nicht authentifiziert"},
    },
)
async def get_cashflow_warnings(
    days: int = Query(
        default=30,
        ge=7,
        le=90,
        description="Vorausschau in Tagen"
    ),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    company_id: UUID = Depends(get_company_id),
):
    """Hole Liste von Cashflow-Warnungen."""
    service = get_cashflow_prediction_service(db)

    warnings = await service.get_cashflow_warnings(
        company_id=company_id,
        days=days,
    )

    critical_count = sum(1 for w in warnings if w.severity == WarningSeverity.CRITICAL)

    return CashflowWarningsResponse(
        company_id=str(company_id),
        warning_count=len(warnings),
        critical_count=critical_count,
        warnings=[
            CashflowWarningItem(
                type=w.type.value,
                severity=w.severity.value,
                date=w.date,
                predicted_balance=round(float(w.predicted_balance), 2),
                message=w.message,
                suggested_actions=w.suggested_actions,
                days_until_trigger=w.days_until_trigger,
                affected_amount=round(float(w.affected_amount), 2) if w.affected_amount else None,
            )
            for w in warnings
        ],
        generated_at=datetime.now(),
    )


@router.post(
    "/scenario",
    response_model=ScenarioResponse,
    summary="Szenario-Simulation",
    description="""
    Führt eine What-If Szenario-Simulation durch.

    **Verfügbare Szenarien:**

    1. `customer_late_payment` - Was wenn ein Kunde später zahlt?
       - Parameter: `entity_id` (UUID), `delay_days` (int)

    2. `delay_outgoing` - Was wenn wir eine Zahlung verschieben?
       - Parameter: `invoice_id` (UUID), `delay_days` (int)

    3. `new_order` - Was wenn wir einen neuen Auftrag bekommen?
       - Parameter: `amount` (float), `payment_due_days` (int)

    4. `customer_default` - Was wenn ein Kunde komplett ausfaellt?
       - Parameter: `entity_id` (UUID)

    5. `accelerate_collection` - Was wenn wir Forderungseinzug beschleunigen?
       - Parameter: `days_improvement` (int)
    """,
    responses={
        200: {"description": "Simulation erfolgreich durchgeführt"},
        400: {"description": "Ungültige Parameter"},
        401: {"description": "Nicht authentifiziert"},
    },
)
async def simulate_scenario(
    request: ScenarioRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    company_id: UUID = Depends(get_company_id),
):
    """Führe What-If Szenario-Simulation durch."""
    service = get_cashflow_prediction_service(db)

    try:
        scenario_type = ScenarioType(request.scenario_type)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Ungültiger Szenario-Typ: {request.scenario_type}"
        )

    # UUID-Parameter konvertieren falls vorhanden
    parameters = request.parameters.copy()
    for key in ["entity_id", "invoice_id"]:
        if key in parameters and parameters[key]:
            try:
                parameters[key] = UUID(str(parameters[key]))
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Ungültige UUID für {key}: {parameters[key]}"
                )

    result = await service.simulate_scenario(
        company_id=company_id,
        scenario_type=scenario_type,
        parameters=parameters,
    )

    return ScenarioResponse(
        scenario_type=result.scenario_type.value,
        description=result.description,
        impact_on_min_balance=round(float(result.impact_on_min_balance), 2),
        impact_on_avg_balance=round(float(result.impact_on_avg_balance), 2),
        risk_assessment=result.risk_assessment,
        recommendations=result.recommendations,
        forecast=[
            CashflowForecastItem(
                date=f.date,
                predicted_balance=round(float(f.predicted_balance), 2),
                lower_bound=round(float(f.lower_bound), 2),
                upper_bound=round(float(f.upper_bound), 2),
                incoming=round(float(f.incoming), 2),
                outgoing=round(float(f.outgoing), 2),
                confidence=round(float(f.confidence), 2),
                incoming_count=f.incoming_count,
                outgoing_count=f.outgoing_count,
            )
            for f in result.new_forecasts
        ],
    )


@router.get(
    "/metrics",
    response_model=PredictionMetricsResponse,
    summary="Vorhersage-Metriken",
    description="""
    Ruft Metriken zur Vorhersagegenauigkeit ab.

    Vergleicht historische Vorhersagen mit tatsaechlichen Zahlungen
    der letzten 90 Tage.

    **Metriken:**
    - `accuracy_rate`: Prozentsatz korrekter Vorhersagen (Toleranz: 5 Tage)
    - `mean_absolute_error_days`: Durchschnittlicher Fehler in Tagen
    """,
    responses={
        200: {"description": "Metriken erfolgreich abgerufen"},
        401: {"description": "Nicht authentifiziert"},
    },
)
async def get_prediction_metrics(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    company_id: UUID = Depends(get_company_id),
):
    """Hole Vorhersagegenauigkeit-Metriken."""
    service = get_cashflow_prediction_service(db)

    metrics = await service.get_prediction_metrics(company_id=company_id)

    return PredictionMetricsResponse(
        total_predictions=metrics.total_predictions,
        correct_predictions=metrics.correct_predictions,
        mean_absolute_error_days=metrics.mean_absolute_error_days,
        accuracy_rate=metrics.accuracy_rate,
        last_evaluated=metrics.last_evaluated,
    )


@router.get(
    "/payment-delays",
    response_model=PaymentDelayAnalysisResponse,
    summary="Zahlungsverhaltens-Analyse",
    description="""
    Analysiert das Zahlungsverhalten von Kunden.

    Berechnet für jeden Kunden:
    - Durchschnittliche Zahlungsverzögerung
    - Payment Behavior Score (0-100, höher = besser)
    - Risk Score (0-100, höher = riskanter)

    Optional kann ein einzelner Kunde analysiert werden.
    """,
    responses={
        200: {"description": "Analyse erfolgreich durchgeführt"},
        401: {"description": "Nicht authentifiziert"},
    },
)
async def get_payment_delay_analysis(
    entity_id: Optional[UUID] = Query(
        default=None,
        description="Optional: Nur für bestimmten Kunden"
    ),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    company_id: UUID = Depends(get_company_id),
):
    """Hole Zahlungsverhaltens-Analyse."""
    service = get_cashflow_prediction_service(db)

    stats = await service.get_payment_delay_analysis(
        company_id=company_id,
        entity_id=entity_id,
    )

    high_risk_count = sum(1 for s in stats if s.risk_score > 50)

    return PaymentDelayAnalysisResponse(
        company_id=str(company_id),
        entity_count=len(stats),
        high_risk_count=high_risk_count,
        stats=[
            PaymentDelayStatsItem(
                entity_id=str(s.entity_id),
                average_delay_days=s.average_delay_days,
                std_deviation=s.std_deviation,
                sample_count=s.sample_count,
                payment_behavior_score=s.payment_behavior_score,
                risk_score=s.risk_score,
                last_payment_date=s.last_payment_date,
            )
            for s in stats
        ],
        generated_at=datetime.now(),
    )


@router.get(
    "/summary",
    summary="Cashflow-Zusammenfassung",
    description="Kurze Zusammenfassung der aktuellen Liquiditaetssituation.",
    responses={
        200: {"description": "Zusammenfassung erfolgreich erstellt"},
        401: {"description": "Nicht authentifiziert"},
    },
)
async def get_cashflow_summary(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    company_id: UUID = Depends(get_company_id),
):
    """Hole kompakte Cashflow-Zusammenfassung."""
    service = get_cashflow_prediction_service(db)

    # 7-Tage und 30-Tage Prognose
    forecast_7 = await service.get_cashflow_forecast(company_id=company_id, days=7)
    forecast_30 = await service.get_cashflow_forecast(company_id=company_id, days=30)

    # Warnungen
    warnings = await service.get_cashflow_warnings(company_id=company_id, days=30)

    # Berechnungen
    current_balance = float(forecast_7[0].predicted_balance) if forecast_7 else 0.0
    min_7 = min(f.predicted_balance for f in forecast_7) if forecast_7 else Decimal("0")
    min_30 = min(f.predicted_balance for f in forecast_30) if forecast_30 else Decimal("0")

    critical_count = sum(1 for w in warnings if w.severity == WarningSeverity.CRITICAL)
    warning_count = sum(1 for w in warnings if w.severity == WarningSeverity.WARNING)

    # Status bestimmen
    if min_7 < Decimal("0"):
        status_text = "critical"
    elif min_30 < Decimal("0"):
        status_text = "warning"
    elif min_30 < Decimal("5000"):
        status_text = "caution"
    else:
        status_text = "healthy"

    # Tage bis kritisch (falls vorhanden)
    days_until_critical = None
    for i, f in enumerate(forecast_30):
        if f.predicted_balance < Decimal("0"):
            days_until_critical = i
            break

    return {
        "company_id": str(company_id),
        "current_balance": round(current_balance, 2),
        "min_balance_7d": round(float(min_7), 2),
        "min_balance_30d": round(float(min_30), 2),
        "expected_inflows_7d": round(float(sum(f.incoming for f in forecast_7)), 2),
        "expected_outflows_7d": round(float(sum(f.outgoing for f in forecast_7)), 2),
        "net_flow_7d": round(float(sum(f.incoming - f.outgoing for f in forecast_7)), 2),
        "critical_warnings": critical_count,
        "total_warnings": len(warnings),
        "status": status_text,
        "days_until_critical": days_until_critical,
        "currency": "EUR",
        "generated_at": datetime.now().isoformat(),
    }
