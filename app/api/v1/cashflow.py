# -*- coding: utf-8 -*-
"""
Cashflow Prediction API Endpoints.

Phase 2.2: Predictive Cash Flow AI Service

API für Entity-basierte Cashflow-Vorhersagen:
- GET /api/v1/cashflow/forecast - 30/60/90 Tage Prognose
- GET /api/v1/cashflow/invoice/{id}/prediction - Einzelne Rechnung
- GET /api/v1/cashflow/entity/{id}/profile - Entity Zahlungsprofil
- GET /api/v1/cashflow/alerts - Liquiditaetswarnungen

SECURITY:
- Alle Endpoints erfordern Authentifizierung
- Company-Isolation via current_user.current_company_id
- Keine PII in Responses (Entity-Namen werden maskiert)

Created: 2026-02-02
"""

from datetime import date
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user, get_db
from app.db.models import User
from app.services.predictive.cashflow_predictor_service import (
    CashflowPredictorService,
    get_cashflow_predictor_service,
    CashFlowPrediction,
    EntityPaymentProfile,
    LiquidityAlert,
    PaymentProbability,
)

router = APIRouter(prefix="/cashflow", tags=["Cashflow Prediction"])


# =============================================================================
# PYDANTIC MODELS - Response Schemas
# =============================================================================


class ConfidenceIntervalResponse(BaseModel):
    """Konfidenzintervall für Prognosen."""

    low: float = Field(..., description="Pessimistisches Szenario (10. Perzentil)")
    mid: float = Field(..., description="Realistisches Szenario (Median)")
    high: float = Field(..., description="Optimistisches Szenario (90. Perzentil)")


class CashFlowPredictionResponse(BaseModel):
    """Tagesweise Cashflow-Prognose."""

    prediction_date: str
    expected_inflows: float
    expected_outflows: float
    net_cash_flow: float
    confidence: ConfidenceIntervalResponse
    contributing_invoices: List[str]
    inflow_count: int
    outflow_count: int
    risk_factors: List[str]


class CashFlowForecastResponse(BaseModel):
    """Antwort für Cashflow-Prognose."""

    company_id: str
    forecast_days: int
    current_balance: float
    min_balance: float
    min_balance_date: str
    total_expected_inflows: float
    total_expected_outflows: float
    forecast: List[CashFlowPredictionResponse]
    generated_at: str
    currency: str = "EUR"


class SeasonalPatternResponse(BaseModel):
    """Erkanntes saisonales Muster."""

    type: str
    affected_months: List[int]
    avg_delay_adjustment: float
    confidence: float
    description: str


class EntityPaymentProfileResponse(BaseModel):
    """Zahlungsprofil eines Geschäftspartners."""

    entity_id: str
    avg_payment_delay_days: int
    payment_consistency: str
    consistency_score: float
    seasonal_pattern: Optional[SeasonalPatternResponse] = None
    risk_adjusted_probability: float
    sample_count: int
    stddev_days: float
    risk_score: float
    payment_behavior_score: float
    profile_updated_at: str


class PaymentProbabilityConfidenceResponse(BaseModel):
    """Konfidenzintervall für Zahlungsdatum."""

    optimistic: str
    pessimistic: str


class PaymentProbabilityResponse(BaseModel):
    """Zahlungswahrscheinlichkeit für eine Rechnung."""

    invoice_id: str
    entity_id: Optional[str] = None
    amount: float
    due_date: str
    predicted_payment_date: str
    probability: float
    delay_days: int
    confidence_interval: PaymentProbabilityConfidenceResponse
    risk_factors: List[str]


class LiquidityAlertResponse(BaseModel):
    """Liquiditaetswarnung."""

    alert_type: str
    severity: str
    trigger_date: str
    predicted_balance: float
    expected_inflows: float
    expected_outflows: float
    message: str
    recommendations: List[str]
    days_until_trigger: int


class LiquidityAlertsResponse(BaseModel):
    """Antwort für Liquiditaetswarnungen."""

    company_id: str
    alert_count: int
    critical_count: int
    warning_count: int
    alerts: List[LiquidityAlertResponse]
    generated_at: str


# =============================================================================
# API ENDPOINTS
# =============================================================================


@router.get(
    "/forecast",
    response_model=CashFlowForecastResponse,
    summary="Cashflow-Prognose",
    description="Erstellt eine Cashflow-Prognose für 30, 60 oder 90 Tage.",
)
async def get_cashflow_forecast(
    days: int = Query(
        30,
        ge=7,
        le=90,
        description="Prognosezeitraum in Tagen (30, 60, oder 90)"
    ),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CashFlowForecastResponse:
    """
    Erstellt eine Entity-basierte Cashflow-Prognose.

    Verwendet historische Zahlungsmuster und Risk Scores für praezise
    Vorhersagen. Berücksichtigt saisonale Faktoren und Zahlungskonsistenz.

    Returns:
        Tagesweise Prognose mit Konfidenzintervallen
    """
    if not current_user.current_company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Keine Company ausgewaehlt",
        )

    service = get_cashflow_predictor_service(db)

    # Prognose erstellen
    predictions = await service.get_cashflow_forecast(
        company_id=current_user.current_company_id,
        days=days,
    )

    if not predictions:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Keine Prognosedaten verfügbar",
        )

    # Aktueller Kontostand
    current_balance = await service._get_current_balance(
        current_user.current_company_id
    )

    # Zusammenfassung berechnen
    min_balance = min(p.confidence_mid for p in predictions)
    min_balance_date = next(
        p.prediction_date for p in predictions
        if p.confidence_mid == min_balance
    )

    total_inflows = sum(p.expected_inflows for p in predictions)
    total_outflows = sum(p.expected_outflows for p in predictions)

    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)

    return CashFlowForecastResponse(
        company_id=str(current_user.current_company_id),
        forecast_days=days,
        current_balance=float(current_balance),
        min_balance=float(min_balance),
        min_balance_date=min_balance_date.isoformat(),
        total_expected_inflows=float(total_inflows),
        total_expected_outflows=float(total_outflows),
        forecast=[
            CashFlowPredictionResponse(
                prediction_date=p.prediction_date.isoformat(),
                expected_inflows=float(p.expected_inflows),
                expected_outflows=float(p.expected_outflows),
                net_cash_flow=float(p.net_cash_flow),
                confidence=ConfidenceIntervalResponse(
                    low=float(p.confidence_low),
                    mid=float(p.confidence_mid),
                    high=float(p.confidence_high),
                ),
                contributing_invoices=[str(i) for i in p.contributing_invoices],
                inflow_count=p.inflow_count,
                outflow_count=p.outflow_count,
                risk_factors=p.risk_factors,
            )
            for p in predictions
        ],
        generated_at=now.isoformat(),
    )


@router.get(
    "/invoice/{invoice_id}/prediction",
    response_model=PaymentProbabilityResponse,
    summary="Zahlungsvorhersage für Rechnung",
    description="Berechnet die Zahlungswahrscheinlichkeit für eine einzelne Rechnung.",
)
async def get_invoice_payment_prediction(
    invoice_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PaymentProbabilityResponse:
    """
    Berechnet die Zahlungswahrscheinlichkeit für eine einzelne Rechnung.

    Basiert auf:
    - Historischem Zahlungsverhalten der Entity
    - Rechnungsbetrag und Fälligkeitsdatum
    - Saisonalen Faktoren
    - Risk Score der Entity

    Returns:
        Vorhergesagtes Zahlungsdatum mit Konfidenzintervall
    """
    if not current_user.current_company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Keine Company ausgewaehlt",
        )

    service = get_cashflow_predictor_service(db)

    probability = await service.get_invoice_payment_probability(
        invoice_id=invoice_id,
        company_id=current_user.current_company_id,
    )

    if not probability:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Rechnung nicht gefunden",
        )

    return PaymentProbabilityResponse(
        invoice_id=str(probability.invoice_id),
        entity_id=str(probability.entity_id) if probability.entity_id else None,
        amount=float(probability.amount),
        due_date=probability.due_date.isoformat(),
        predicted_payment_date=probability.predicted_payment_date.isoformat(),
        probability=round(probability.probability, 3),
        delay_days=probability.delay_days,
        confidence_interval=PaymentProbabilityConfidenceResponse(
            optimistic=probability.optimistic_date.isoformat(),
            pessimistic=probability.pessimistic_date.isoformat(),
        ),
        risk_factors=probability.risk_factors,
    )


@router.get(
    "/entity/{entity_id}/profile",
    response_model=EntityPaymentProfileResponse,
    summary="Entity Zahlungsprofil",
    description="Ruft das vollständige Zahlungsprofil eines Geschäftspartners ab.",
)
async def get_entity_payment_profile(
    entity_id: UUID,
    force_refresh: bool = Query(
        False,
        description="Cache ignorieren und neu berechnen"
    ),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> EntityPaymentProfileResponse:
    """
    Ruft das Zahlungsprofil eines Geschäftspartners ab.

    Beinhaltet:
    - Durchschnittliche Zahlungsverzögerung
    - Zahlungskonsistenz (puenktlich, verspätet, variabel)
    - Saisonale Muster
    - Risiko-adjustierte Zahlungswahrscheinlichkeit

    Returns:
        Vollständiges EntityPaymentProfile
    """
    if not current_user.current_company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Keine Company ausgewaehlt",
        )

    service = get_cashflow_predictor_service(db)

    profile = await service.get_entity_payment_profile(
        entity_id=entity_id,
        company_id=current_user.current_company_id,
        force_refresh=force_refresh,
    )

    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Keine Zahlungshistorie für diese Entity vorhanden",
        )

    seasonal_pattern = None
    if profile.seasonal_pattern:
        seasonal_pattern = SeasonalPatternResponse(
            type=profile.seasonal_pattern.pattern_type.value,
            affected_months=profile.seasonal_pattern.affected_months,
            avg_delay_adjustment=profile.seasonal_pattern.avg_delay_adjustment,
            confidence=profile.seasonal_pattern.confidence,
            description=profile.seasonal_pattern.description,
        )

    return EntityPaymentProfileResponse(
        entity_id=str(profile.entity_id),
        avg_payment_delay_days=profile.avg_payment_delay_days,
        payment_consistency=profile.payment_consistency.value,
        consistency_score=round(profile.consistency_score, 2),
        seasonal_pattern=seasonal_pattern,
        risk_adjusted_probability=round(profile.risk_adjusted_probability, 3),
        sample_count=profile.sample_count,
        stddev_days=round(profile.stddev_days, 1),
        risk_score=round(profile.risk_score, 1),
        payment_behavior_score=round(profile.payment_behavior_score, 1),
        profile_updated_at=profile.profile_updated_at.isoformat(),
    )


@router.get(
    "/alerts",
    response_model=LiquidityAlertsResponse,
    summary="Liquiditaetswarnungen",
    description="Generiert Warnungen für bevorstehende Liquiditaetsprobleme.",
)
async def get_liquidity_alerts(
    days: int = Query(
        30,
        ge=7,
        le=90,
        description="Vorausschau in Tagen"
    ),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> LiquidityAlertsResponse:
    """
    Generiert Liquiditaetswarnungen basierend auf Cashflow-Prognose.

    Warnt bei:
    - Kritischen Liquiditaetsengpaessen (Balance < 0)
    - Cashflow-Lücken (Ausgaenge >> Eingaenge)
    - Negativem Trend
    - Hoher Konzentration von High-Risk Entities

    Returns:
        Liste von Warnungen sortiert nach Dringlichkeit
    """
    if not current_user.current_company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Keine Company ausgewaehlt",
        )

    service = get_cashflow_predictor_service(db)

    alerts = await service.get_liquidity_alerts(
        company_id=current_user.current_company_id,
        forecast_days=days,
    )

    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)

    critical_count = sum(
        1 for a in alerts if a.severity.value == "critical"
    )
    warning_count = sum(
        1 for a in alerts if a.severity.value == "warning"
    )

    return LiquidityAlertsResponse(
        company_id=str(current_user.current_company_id),
        alert_count=len(alerts),
        critical_count=critical_count,
        warning_count=warning_count,
        alerts=[
            LiquidityAlertResponse(
                alert_type=a.alert_type.value,
                severity=a.severity.value,
                trigger_date=a.trigger_date.isoformat(),
                predicted_balance=float(a.predicted_balance),
                expected_inflows=float(a.expected_inflows),
                expected_outflows=float(a.expected_outflows),
                message=a.message,
                recommendations=a.recommendations,
                days_until_trigger=a.days_until_trigger,
            )
            for a in alerts
        ],
        generated_at=now.isoformat(),
    )


@router.post(
    "/entity/{entity_id}/profile/refresh",
    response_model=EntityPaymentProfileResponse,
    summary="Entity Profil aktualisieren",
    description="Erzwingt Neuberechnung des Entity-Zahlungsprofils.",
)
async def refresh_entity_profile(
    entity_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> EntityPaymentProfileResponse:
    """
    Erzwingt die Neuberechnung des Zahlungsprofils.

    Nuetzlich nach signifikanten Änderungen im Zahlungsverhalten
    oder nach manuellen Korrekturen.

    Returns:
        Aktualisiertes EntityPaymentProfile
    """
    if not current_user.current_company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Keine Company ausgewaehlt",
        )

    service = get_cashflow_predictor_service(db)

    profile = await service.get_entity_payment_profile(
        entity_id=entity_id,
        company_id=current_user.current_company_id,
        force_refresh=True,
    )

    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Keine Zahlungshistorie für diese Entity vorhanden",
        )

    seasonal_pattern = None
    if profile.seasonal_pattern:
        seasonal_pattern = SeasonalPatternResponse(
            type=profile.seasonal_pattern.pattern_type.value,
            affected_months=profile.seasonal_pattern.affected_months,
            avg_delay_adjustment=profile.seasonal_pattern.avg_delay_adjustment,
            confidence=profile.seasonal_pattern.confidence,
            description=profile.seasonal_pattern.description,
        )

    return EntityPaymentProfileResponse(
        entity_id=str(profile.entity_id),
        avg_payment_delay_days=profile.avg_payment_delay_days,
        payment_consistency=profile.payment_consistency.value,
        consistency_score=round(profile.consistency_score, 2),
        seasonal_pattern=seasonal_pattern,
        risk_adjusted_probability=round(profile.risk_adjusted_probability, 3),
        sample_count=profile.sample_count,
        stddev_days=round(profile.stddev_days, 1),
        risk_score=round(profile.risk_score, 1),
        payment_behavior_score=round(profile.payment_behavior_score, 1),
        profile_updated_at=profile.profile_updated_at.isoformat(),
    )


@router.get(
    "/summary",
    summary="Cashflow-Zusammenfassung",
    description="Kurze Zusammenfassung der aktuellen Liquiditaetssituation.",
    # Eindeutige operation_id: kollidierte mit banking_fints.py (gleicher Pfad)
    operation_id="cashflow_get_cashflow_summary",
)
async def get_cashflow_summary(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Liefert eine kompakte Zusammenfassung der Liquiditaetssituation.

    Ideal für Dashboard-Widgets.

    Returns:
        Dictionary mit Kennzahlen
    """
    if not current_user.current_company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Keine Company ausgewaehlt",
        )

    service = get_cashflow_predictor_service(db)

    # 7-Tage und 30-Tage Prognose
    forecast_7 = await service.get_cashflow_forecast(
        company_id=current_user.current_company_id,
        days=7,
    )
    forecast_30 = await service.get_cashflow_forecast(
        company_id=current_user.current_company_id,
        days=30,
    )

    # Alerts
    alerts = await service.get_liquidity_alerts(
        company_id=current_user.current_company_id,
        forecast_days=30,
    )

    # Aktueller Kontostand
    current_balance = await service._get_current_balance(
        current_user.current_company_id
    )

    # Kennzahlen berechnen
    min_7d = min(p.confidence_mid for p in forecast_7) if forecast_7 else current_balance
    min_30d = min(p.confidence_mid for p in forecast_30) if forecast_30 else current_balance

    inflows_7d = sum(p.expected_inflows for p in forecast_7) if forecast_7 else 0
    outflows_7d = sum(p.expected_outflows for p in forecast_7) if forecast_7 else 0

    critical_alerts = sum(1 for a in alerts if a.severity.value == "critical")

    # Status bestimmen
    if min_7d < 0:
        status_val = "critical"
    elif min_30d < 0:
        status_val = "warning"
    elif critical_alerts > 0:
        status_val = "warning"
    else:
        status_val = "healthy"

    return {
        "current_balance": float(current_balance),
        "min_balance_7d": float(min_7d),
        "min_balance_30d": float(min_30d),
        "expected_inflows_7d": float(inflows_7d),
        "expected_outflows_7d": float(outflows_7d),
        "net_flow_7d": float(inflows_7d - outflows_7d),
        "alerts_count": len(alerts),
        "critical_alerts": critical_alerts,
        "status": status_val,
        "currency": "EUR",
    }
