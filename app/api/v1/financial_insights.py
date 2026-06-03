# -*- coding: utf-8 -*-
"""
Financial Insights API Endpoints.

Vision 2026 Q4: Enterprise Financial Intelligence.

Endpoints:
- GET  /financial-insights/cashflow/predict      - Cashflow-Prognose (7-90 Tage)
- GET  /financial-insights/cashflow/history      - Historische Cashflow-Daten
- POST /financial-insights/cashflow/scenario     - What-If Szenario-Analyse
- GET  /financial-insights/fraud/scan            - Betrugs-Scan durchführen
- GET  /financial-insights/fraud/alerts          - Aktive Betrugs-Warnungen
- POST /financial-insights/fraud/dismiss         - Warnung verwerfen
- GET  /financial-insights/skonto/optimize       - Skonto-Optimierung
- GET  /financial-insights/skonto/recommendations - Zahlungsempfehlungen
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Optional

from app.core.types import JSONDict
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_active_user, get_db, get_user_company_id_dep
from app.core.rate_limiting import limiter, get_user_identifier
from app.core.safe_errors import safe_error_log
from app.db.models import User
from app.services.insights import (
    get_cashflow_predictor,
    get_fraud_early_warning_service,
    get_skonto_optimizer,
    CashflowPrediction,
    CashflowDataPoint,
    CashflowTrend,
    CashflowRiskLevel,
    FraudAlert,
    FraudAlertType,
    FraudSeverity,
    FraudScanResult,
    PaymentRecommendation,
    OptimizationResult,
    RecommendationType,
)

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/financial-insights", tags=["Financial Insights"])


# =============================================================================
# Pydantic Schemas - Cashflow
# =============================================================================


class CashflowDataPointResponse(BaseModel):
    """Ein Datenpunkt in der Cashflow-Prognose."""

    date: str = Field(..., description="Datum")
    predicted_balance: float = Field(..., description="Prognostizierter Kontostand")
    confidence_low: float = Field(..., description="Untere Konfidenzgrenze")
    confidence_high: float = Field(..., description="Obere Konfidenzgrenze")
    expected_inflows: float = Field(..., description="Erwartete Einnahmen")
    expected_outflows: float = Field(..., description="Erwartete Ausgaben")
    is_warning: bool = Field(..., description="Warnung bei niedrigem Stand")


class RecurringPaymentResponse(BaseModel):
    """Wiederkehrende Zahlung."""

    name: str = Field(..., description="Name/Beschreibung")
    amount: float = Field(..., description="Betrag")
    frequency: str = Field(..., description="Häufigkeit (monthly, weekly, etc.)")
    next_due: str = Field(..., description="Nächste Fälligkeit")
    is_inflow: bool = Field(..., description="Einnahme (True) oder Ausgabe (False)")


class PendingInvoiceResponse(BaseModel):
    """Ausstehende Rechnung."""

    invoice_id: str = Field(..., description="Rechnungs-ID")
    amount: float = Field(..., description="Betrag")
    due_date: str = Field(..., description="Fälligkeitsdatum")
    entity_name: str = Field(..., description="Kunde/Lieferant")
    is_incoming: bool = Field(..., description="Eingehend (True) oder Ausgehend (False)")
    payment_probability: float = Field(..., description="Zahlungswahrscheinlichkeit")


class CashflowPredictionResponse(BaseModel):
    """Cashflow-Prognose Ergebnis."""

    company_id: str = Field(..., description="Firmen-ID")
    prediction_date: str = Field(..., description="Zeitpunkt der Prognose")
    horizon_days: int = Field(..., description="Prognosezeitraum in Tagen")
    current_balance: float = Field(..., description="Aktueller Kontostand")
    data_points: List[CashflowDataPointResponse] = Field(
        ..., description="Prognosedaten"
    )
    trend: str = Field(..., description="Trend (improving, stable, declining)")
    risk_level: str = Field(..., description="Risiko-Level")
    risk_date: Optional[str] = Field(None, description="Datum des ersten Risikos")
    minimum_balance: float = Field(..., description="Minimaler prognostizierter Stand")
    minimum_balance_date: str = Field(..., description="Datum des Minimums")
    recurring_payments: List[RecurringPaymentResponse] = Field(
        default=[], description="Wiederkehrende Zahlungen"
    )
    pending_invoices: List[PendingInvoiceResponse] = Field(
        default=[], description="Ausstehende Rechnungen"
    )
    confidence_score: float = Field(..., description="Gesamtkonfidenz (0-1)")
    recommendations: List[str] = Field(default=[], description="Empfehlungen")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "company_id": "550e8400-e29b-41d4-a716-446655440000",
                "prediction_date": "2026-01-30T10:00:00Z",
                "horizon_days": 30,
                "current_balance": 50000.0,
                "trend": "stable",
                "risk_level": "low",
                "minimum_balance": 15000.0,
                "minimum_balance_date": "2026-02-15",
                "confidence_score": 0.85,
            }
        }
    )


class ScenarioRequest(BaseModel):
    """What-If Szenario Request."""

    adjustment_type: str = Field(
        ..., description="Typ: delay_payments, accelerate_receipts, add_expense, add_income"
    )
    amount: float = Field(..., description="Betrag")
    days: int = Field(default=0, description="Tage Verzögerung/Beschleunigung")
    description: str = Field(default="", description="Beschreibung")


# =============================================================================
# Pydantic Schemas - Fraud Detection
# =============================================================================


class FraudIndicatorResponse(BaseModel):
    """Ein Indikator für Betrugsverdacht."""

    indicator_type: str = Field(..., description="Typ des Indikators")
    description: str = Field(..., description="Beschreibung")
    value: str = Field(..., description="Gefundener Wert")
    expected_value: Optional[str] = Field(None, description="Erwarteter Wert")
    contribution: float = Field(..., description="Beitrag zum Gesamtscore")


class FraudAlertResponse(BaseModel):
    """Betrugswarnung."""

    id: str = Field(..., description="Alert-ID")
    alert_type: str = Field(..., description="Warnungstyp")
    severity: str = Field(..., description="Schweregrad")
    title: str = Field(..., description="Titel")
    description: str = Field(..., description="Beschreibung")
    document_id: Optional[str] = Field(None, description="Betroffenes Dokument")
    entity_id: Optional[str] = Field(None, description="Betroffene Entity")
    entity_name: Optional[str] = Field(None, description="Entity-Name")
    risk_score: float = Field(..., description="Risiko-Score (0-100)")
    indicators: List[FraudIndicatorResponse] = Field(
        default=[], description="Indikatoren"
    )
    recommendation: str = Field(..., description="Empfehlung")
    created_at: str = Field(..., description="Erstellungszeitpunkt")
    is_dismissed: bool = Field(default=False, description="Verworfen")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": "fraud-alert-001",
                "alert_type": "duplicate_invoice",
                "severity": "high",
                "title": "Mögliche Doppelrechnung erkannt",
                "description": "Rechnung R-2026-123 ähnelt stark R-2026-089",
                "risk_score": 85.5,
                "recommendation": "Manuelle Prüfung empfohlen",
            }
        }
    )


class FraudScanResultResponse(BaseModel):
    """Ergebnis eines Betrugs-Scans."""

    scan_id: str = Field(..., description="Scan-ID")
    scan_date: str = Field(..., description="Scan-Zeitpunkt")
    company_id: str = Field(..., description="Firmen-ID")
    documents_scanned: int = Field(..., description="Geprüfte Dokumente")
    alerts_found: int = Field(..., description="Gefundene Warnungen")
    alerts: List[FraudAlertResponse] = Field(default=[], description="Warnungen")
    by_severity: Dict[str, int] = Field(default={}, description="Nach Schweregrad")
    by_type: Dict[str, int] = Field(default={}, description="Nach Typ")
    scan_duration_ms: int = Field(..., description="Scan-Dauer in ms")


# =============================================================================
# Pydantic Schemas - Skonto Optimization
# =============================================================================


class PaymentRecommendationResponse(BaseModel):
    """Zahlungsempfehlung."""

    invoice_id: str = Field(..., description="Rechnungs-ID")
    invoice_number: str = Field(..., description="Rechnungsnummer")
    supplier_name: str = Field(..., description="Lieferant")
    amount: float = Field(..., description="Rechnungsbetrag")
    skonto_percentage: float = Field(..., description="Skonto-Prozentsatz")
    skonto_amount: float = Field(..., description="Skonto-Betrag")
    skonto_deadline: str = Field(..., description="Skonto-Frist")
    days_until_deadline: int = Field(..., description="Tage bis Frist")
    payment_deadline: str = Field(..., description="Zahlungsfrist")
    recommendation: str = Field(..., description="Empfehlungstyp")
    reason: str = Field(..., description="Begründung")
    roi_annualized: float = Field(..., description="Annualisierte Rendite in %")
    priority: int = Field(..., description="Priorität (1=höchste)")


class SkontoOptimizationResponse(BaseModel):
    """Skonto-Optimierungs-Ergebnis."""

    company_id: str = Field(..., description="Firmen-ID")
    analysis_date: str = Field(..., description="Analyse-Zeitpunkt")
    days_analyzed: int = Field(..., description="Analysierte Tage voraus")
    current_balance: float = Field(..., description="Aktueller Kontostand")
    total_invoices: int = Field(..., description="Rechnungen mit Skonto")
    total_skonto_available: float = Field(..., description="Verfügbares Skonto gesamt")
    recommended_savings: float = Field(..., description="Empfohlene Einsparungen")
    recommendations: List[PaymentRecommendationResponse] = Field(
        default=[], description="Zahlungsempfehlungen"
    )
    liquidity_impact: str = Field(
        ..., description="Liquiditäts-Auswirkung (positive, neutral, negative)"
    )
    cash_buffer_warning: bool = Field(
        ..., description="Warnung bei niedrigem Puffer"
    )
    optimal_payment_date: Optional[str] = Field(
        None, description="Optimaler Zahlungstermin"
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "company_id": "550e8400-e29b-41d4-a716-446655440000",
                "analysis_date": "2026-01-30T10:00:00Z",
                "days_analyzed": 14,
                "current_balance": 50000.0,
                "total_invoices": 5,
                "total_skonto_available": 450.0,
                "recommended_savings": 320.0,
                "liquidity_impact": "positive",
                "cash_buffer_warning": False,
            }
        }
    )


# =============================================================================
# Cashflow Endpoints
# =============================================================================


@router.get(
    "/cashflow/predict",
    response_model=CashflowPredictionResponse,
    summary="Cashflow-Prognose erstellen",
)
@limiter.limit("30/minute")
async def predict_cashflow(
    request: Request,
    horizon_days: int = Query(30, ge=7, le=90, description="Prognosezeitraum in Tagen"),
    include_scenarios: bool = Query(False, description="Szenarien einbeziehen"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_user_company_id_dep),
) -> CashflowPredictionResponse:
    """
    Erstellt eine ML-basierte Cashflow-Prognose.

    Die Prognose basiert auf:
    - Historischen Zahlungsmustern
    - Offenen Ein- und Ausgangsrechnungen
    - Wiederkehrenden Zahlungen
    - Saisonalen Faktoren

    Returns:
        CashflowPredictionResponse mit Prognose und Empfehlungen
    """
    predictor = get_cashflow_predictor()

    try:
        prediction = await predictor.predict(
            db=db,
            company_id=company_id,
            horizon_days=horizon_days,
            include_scenarios=include_scenarios,
        )

        return CashflowPredictionResponse(
            company_id=str(prediction["company_id"]),
            prediction_date=prediction["prediction_date"],
            horizon_days=prediction["horizon_days"],
            current_balance=prediction["current_balance"],
            data_points=[
                CashflowDataPointResponse(
                    date=dp["date"],
                    predicted_balance=dp["predicted_balance"],
                    confidence_low=dp["confidence_low"],
                    confidence_high=dp["confidence_high"],
                    expected_inflows=dp["expected_inflows"],
                    expected_outflows=dp["expected_outflows"],
                    is_warning=dp["is_warning"],
                )
                for dp in prediction.get("data_points", [])
            ],
            trend=prediction["trend"],
            risk_level=prediction["risk_level"],
            risk_date=prediction.get("risk_date"),
            minimum_balance=prediction["minimum_balance"],
            minimum_balance_date=prediction["minimum_balance_date"],
            recurring_payments=[
                RecurringPaymentResponse(**rp)
                for rp in prediction.get("recurring_payments", [])
            ],
            pending_invoices=[
                PendingInvoiceResponse(**pi)
                for pi in prediction.get("pending_invoices", [])
            ],
            confidence_score=prediction["confidence_score"],
            recommendations=prediction.get("recommendations", []),
        )
    except Exception as e:
        logger.error("cashflow_prediction_failed", **safe_error_log(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Cashflow-Prognose konnte nicht erstellt werden",
        )


@router.post(
    "/cashflow/scenario",
    response_model=CashflowPredictionResponse,
    summary="What-If Szenario analysieren",
)
@limiter.limit("20/minute")
async def analyze_scenario(
    request: Request,
    scenario: ScenarioRequest,
    horizon_days: int = Query(30, ge=7, le=90),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_user_company_id_dep),
) -> CashflowPredictionResponse:
    """
    Analysiert ein What-If Szenario.

    Szenarien:
    - delay_payments: Zahlungen verzögern
    - accelerate_receipts: Einnahmen beschleunigen
    - add_expense: Zusätzliche Ausgabe simulieren
    - add_income: Zusätzliche Einnahme simulieren

    Returns:
        Angepasste Cashflow-Prognose
    """
    predictor = get_cashflow_predictor()

    scenario_adjustments = {
        "type": scenario.adjustment_type,
        "amount": scenario.amount,
        "days": scenario.days,
        "description": scenario.description,
    }

    try:
        prediction = await predictor.predict(
            db=db,
            company_id=company_id,
            horizon_days=horizon_days,
            include_scenarios=True,
            scenario_adjustments=scenario_adjustments,
        )

        return CashflowPredictionResponse(
            company_id=str(prediction["company_id"]),
            prediction_date=prediction["prediction_date"],
            horizon_days=prediction["horizon_days"],
            current_balance=prediction["current_balance"],
            data_points=[
                CashflowDataPointResponse(**dp)
                for dp in prediction.get("data_points", [])
            ],
            trend=prediction["trend"],
            risk_level=prediction["risk_level"],
            risk_date=prediction.get("risk_date"),
            minimum_balance=prediction["minimum_balance"],
            minimum_balance_date=prediction["minimum_balance_date"],
            confidence_score=prediction["confidence_score"],
            recommendations=prediction.get("recommendations", []),
        )
    except Exception as e:
        logger.error("scenario_analysis_failed", **safe_error_log(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Szenario-Analyse fehlgeschlagen",
        )


# =============================================================================
# Fraud Detection Endpoints
# =============================================================================


@router.get(
    "/fraud/scan",
    response_model=FraudScanResultResponse,
    summary="Betrugs-Scan durchführen",
)
@limiter.limit("10/minute")
async def scan_for_fraud(
    request: Request,
    scan_days: int = Query(30, ge=1, le=365, description="Tage zurück zu scannen"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_user_company_id_dep),
) -> FraudScanResultResponse:
    """
    Führt einen proaktiven Betrugs-Scan durch.

    Prüft auf:
    - Doppelte Rechnungen
    - Preisanomalien
    - Phantom-Lieferanten
    - Ungewöhnliche Muster
    - Runde Beträge
    - Geschwindigkeits-Anomalien

    Returns:
        FraudScanResultResponse mit gefundenen Warnungen
    """
    fraud_service = get_fraud_early_warning_service()

    try:
        result = await fraud_service.scan(
            db=db,
            company_id=company_id,
            scan_days=scan_days,
        )

        return FraudScanResultResponse(
            scan_id=result["scan_id"],
            scan_date=result["scan_date"],
            company_id=str(result["company_id"]),
            documents_scanned=result["documents_scanned"],
            alerts_found=result["alerts_found"],
            alerts=[
                FraudAlertResponse(
                    id=alert["id"],
                    alert_type=alert["alert_type"],
                    severity=alert["severity"],
                    title=alert["title"],
                    description=alert["description"],
                    document_id=alert.get("document_id"),
                    entity_id=alert.get("entity_id"),
                    entity_name=alert.get("entity_name"),
                    risk_score=alert["risk_score"],
                    indicators=[
                        FraudIndicatorResponse(**ind)
                        for ind in alert.get("indicators", [])
                    ],
                    recommendation=alert["recommendation"],
                    created_at=alert["created_at"],
                    is_dismissed=alert.get("is_dismissed", False),
                )
                for alert in result.get("alerts", [])
            ],
            by_severity=result.get("by_severity", {}),
            by_type=result.get("by_type", {}),
            scan_duration_ms=result["scan_duration_ms"],
        )
    except Exception as e:
        logger.error("fraud_scan_failed", **safe_error_log(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Betrugs-Scan fehlgeschlagen",
        )


@router.get(
    "/fraud/alerts",
    response_model=List[FraudAlertResponse],
    summary="Aktive Betrugs-Warnungen abrufen",
)
@limiter.limit("60/minute")
async def get_fraud_alerts(
    request: Request,
    severity: Optional[str] = Query(None, description="Filter nach Schweregrad"),
    alert_type: Optional[str] = Query(None, description="Filter nach Typ"),
    include_dismissed: bool = Query(False, description="Verworfene einbeziehen"),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_user_company_id_dep),
) -> List[FraudAlertResponse]:
    """
    Ruft aktive Betrugs-Warnungen ab.

    Returns:
        Liste der FraudAlertResponse
    """
    fraud_service = get_fraud_early_warning_service()

    try:
        alerts = await fraud_service.get_alerts(
            db=db,
            company_id=company_id,
            severity=severity,
            alert_type=alert_type,
            include_dismissed=include_dismissed,
            limit=limit,
        )

        return [
            FraudAlertResponse(
                id=alert["id"],
                alert_type=alert["alert_type"],
                severity=alert["severity"],
                title=alert["title"],
                description=alert["description"],
                document_id=alert.get("document_id"),
                entity_id=alert.get("entity_id"),
                entity_name=alert.get("entity_name"),
                risk_score=alert["risk_score"],
                indicators=[
                    FraudIndicatorResponse(**ind)
                    for ind in alert.get("indicators", [])
                ],
                recommendation=alert["recommendation"],
                created_at=alert["created_at"],
                is_dismissed=alert.get("is_dismissed", False),
            )
            for alert in alerts
        ]
    except Exception as e:
        logger.error("get_fraud_alerts_failed", **safe_error_log(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Warnungen konnten nicht abgerufen werden",
        )


@router.post(
    "/fraud/alerts/{alert_id}/dismiss",
    summary="Betrugs-Warnung verwerfen",
)
@limiter.limit("30/minute")
async def dismiss_fraud_alert(
    request: Request,
    alert_id: str = Path(..., description="Alert-ID"),
    reason: str = Query(..., min_length=5, max_length=500, description="Begründung"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_user_company_id_dep),
) -> JSONDict:
    """
    Verwirft eine Betrugs-Warnung mit Begründung.

    Returns:
        Erfolgsmeldung
    """
    fraud_service = get_fraud_early_warning_service()

    try:
        success = await fraud_service.dismiss_alert(
            db=db,
            alert_id=alert_id,
            company_id=company_id,
            dismissed_by=current_user.id,
            reason=reason,
        )

        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Warnung nicht gefunden",
            )

        return {
            "success": True,
            "message": "Warnung wurde verworfen",
            "alert_id": alert_id,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("dismiss_fraud_alert_failed", **safe_error_log(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Warnung konnte nicht verworfen werden",
        )


# =============================================================================
# Skonto Optimization Endpoints
# =============================================================================


@router.get(
    "/skonto/optimize",
    response_model=SkontoOptimizationResponse,
    summary="Skonto-Optimierung berechnen",
)
@limiter.limit("30/minute")
async def optimize_skonto(
    request: Request,
    days_ahead: int = Query(14, ge=1, le=60, description="Tage voraus"),
    min_savings: float = Query(10.0, ge=0, description="Mindest-Ersparnis in EUR"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_user_company_id_dep),
) -> SkontoOptimizationResponse:
    """
    Berechnet optimale Skonto-Nutzung unter Berücksichtigung der Liquidität.

    Returns:
        SkontoOptimizationResponse mit Empfehlungen
    """
    optimizer = get_skonto_optimizer()

    try:
        result = await optimizer.optimize(
            db=db,
            company_id=company_id,
            days_ahead=days_ahead,
            min_savings=min_savings,
        )

        return SkontoOptimizationResponse(
            company_id=str(result["company_id"]),
            analysis_date=result["analysis_date"],
            days_analyzed=result["days_analyzed"],
            current_balance=result["current_balance"],
            total_invoices=result["total_invoices"],
            total_skonto_available=result["total_skonto_available"],
            recommended_savings=result["recommended_savings"],
            recommendations=[
                PaymentRecommendationResponse(
                    invoice_id=rec["invoice_id"],
                    invoice_number=rec["invoice_number"],
                    supplier_name=rec["supplier_name"],
                    amount=rec["amount"],
                    skonto_percentage=rec["skonto_percentage"],
                    skonto_amount=rec["skonto_amount"],
                    skonto_deadline=rec["skonto_deadline"],
                    days_until_deadline=rec["days_until_deadline"],
                    payment_deadline=rec["payment_deadline"],
                    recommendation=rec["recommendation"],
                    reason=rec["reason"],
                    roi_annualized=rec["roi_annualized"],
                    priority=rec["priority"],
                )
                for rec in result.get("recommendations", [])
            ],
            liquidity_impact=result["liquidity_impact"],
            cash_buffer_warning=result["cash_buffer_warning"],
            optimal_payment_date=result.get("optimal_payment_date"),
        )
    except Exception as e:
        logger.error("skonto_optimization_failed", **safe_error_log(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Skonto-Optimierung fehlgeschlagen",
        )


@router.get(
    "/skonto/recommendations",
    response_model=List[PaymentRecommendationResponse],
    summary="Zahlungsempfehlungen abrufen",
)
@limiter.limit("60/minute")
async def get_payment_recommendations(
    request: Request,
    days_ahead: int = Query(14, ge=1, le=60),
    only_urgent: bool = Query(False, description="Nur dringende Empfehlungen"),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_user_company_id_dep),
) -> List[PaymentRecommendationResponse]:
    """
    Ruft priorisierte Zahlungsempfehlungen ab.

    Returns:
        Liste der PaymentRecommendationResponse
    """
    optimizer = get_skonto_optimizer()

    try:
        recommendations = await optimizer.get_recommendations(
            db=db,
            company_id=company_id,
            days_ahead=days_ahead,
            only_urgent=only_urgent,
            limit=limit,
        )

        return [
            PaymentRecommendationResponse(
                invoice_id=rec["invoice_id"],
                invoice_number=rec["invoice_number"],
                supplier_name=rec["supplier_name"],
                amount=rec["amount"],
                skonto_percentage=rec["skonto_percentage"],
                skonto_amount=rec["skonto_amount"],
                skonto_deadline=rec["skonto_deadline"],
                days_until_deadline=rec["days_until_deadline"],
                payment_deadline=rec["payment_deadline"],
                recommendation=rec["recommendation"],
                reason=rec["reason"],
                roi_annualized=rec["roi_annualized"],
                priority=rec["priority"],
            )
            for rec in recommendations
        ]
    except Exception as e:
        logger.error("get_recommendations_failed", **safe_error_log(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Empfehlungen konnten nicht abgerufen werden",
        )


# =============================================================================
# Summary Endpoint
# =============================================================================


@router.get(
    "/summary",
    summary="Financial Insights Zusammenfassung",
)
@limiter.limit("30/minute")
async def get_financial_insights_summary(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_user_company_id_dep),
) -> JSONDict:
    """
    Gibt eine Zusammenfassung aller Financial Insights zurück.

    Returns:
        Übersicht mit Key-Metriken
    """
    # Hole Services
    cashflow_predictor = get_cashflow_predictor()
    fraud_service = get_fraud_early_warning_service()
    skonto_optimizer = get_skonto_optimizer()

    summary = {
        "timestamp": datetime.utcnow().isoformat(),
        "company_id": str(company_id),
    }

    # Cashflow Summary
    try:
        cashflow = await cashflow_predictor.predict(
            db=db,
            company_id=company_id,
            horizon_days=30,
        )
        summary["cashflow"] = {
            "current_balance": cashflow["current_balance"],
            "trend": cashflow["trend"],
            "risk_level": cashflow["risk_level"],
            "minimum_balance": cashflow["minimum_balance"],
            "minimum_balance_date": cashflow["minimum_balance_date"],
        }
    except Exception:
        summary["cashflow"] = {"error": "Nicht verfügbar"}

    # Fraud Summary
    try:
        fraud_result = await fraud_service.scan(
            db=db,
            company_id=company_id,
            scan_days=30,
        )
        summary["fraud"] = {
            "alerts_count": fraud_result["alerts_found"],
            "by_severity": fraud_result.get("by_severity", {}),
        }
    except Exception:
        summary["fraud"] = {"error": "Nicht verfügbar"}

    # Skonto Summary
    try:
        skonto = await skonto_optimizer.optimize(
            db=db,
            company_id=company_id,
            days_ahead=14,
        )
        summary["skonto"] = {
            "available_savings": skonto["total_skonto_available"],
            "recommended_savings": skonto["recommended_savings"],
            "invoices_with_skonto": skonto["total_invoices"],
            "liquidity_impact": skonto["liquidity_impact"],
        }
    except Exception:
        summary["skonto"] = {"error": "Nicht verfügbar"}

    return summary
