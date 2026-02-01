# -*- coding: utf-8 -*-
"""
Dashboard Widgets API Endpoints.

API-Endpoints fuer Dashboard-Widget-Daten:
- Cash-Flow Forecast (30/60/90 Tage Prognose)
- Supplier Performance (Lieferanten-Metriken)
- Customer Lifetime Value (Kundenwert-Analyse)

Enterprise Feature: Phase 7 Dashboard Widgets (Januar 2026)
"""

from datetime import date
from decimal import Decimal
from typing import Any, Dict, List, Optional
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_active_user, get_db
from app.db.models import User
from app.services.dashboard import (
    get_cash_flow_forecast_service,
    get_supplier_performance_service,
    get_customer_ltv_service,
)

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/dashboard-widgets", tags=["Dashboard Widgets"])


# =============================================================================
# Response Models - Cash-Flow Forecast
# =============================================================================


class ForecastDataPointResponse(BaseModel):
    """Einzelner Datenpunkt der Cash-Flow Prognose."""
    date: str = Field(..., description="Datum (ISO-Format)")
    income: float = Field(..., description="Erwartete Einnahmen")
    expenses: float = Field(..., description="Erwartete Ausgaben")
    net: float = Field(..., description="Netto-Cashflow")
    balance: float = Field(..., description="Kumulativer Saldo")
    confidence: float = Field(..., ge=0, le=1, description="Konfidenz (0-1)")


class PeriodForecastResponse(BaseModel):
    """Zusammenfassung fuer einen Prognosezeitraum."""
    periodDays: int = Field(..., description="Anzahl Tage")
    totalIncome: float = Field(..., description="Gesamt erwartete Einnahmen")
    totalExpenses: float = Field(..., description="Gesamt erwartete Ausgaben")
    netFlow: float = Field(..., description="Netto-Cashflow")
    endingBalance: float = Field(..., description="Erwarteter Endsaldo")
    confidenceScore: float = Field(..., description="Konfidenz-Score")
    incomeInvoiceCount: int = Field(..., description="Anzahl Eingangsrechnungen")
    expenseInvoiceCount: int = Field(..., description="Anzahl Ausgangsrechnungen")


class SkontoImpactResponse(BaseModel):
    """Skonto-Auswirkung auf Cash-Flow."""
    invoiceCount: int = Field(..., description="Anzahl Rechnungen mit Skonto")
    potentialSavings: float = Field(..., description="Potentielle Ersparnis")


class CashFlowForecastResponse(BaseModel):
    """Gesamtergebnis der Cash-Flow Prognose."""
    generatedAt: str = Field(..., description="Generierungszeitpunkt")
    currentBalance: float = Field(..., description="Aktueller Kontostand")
    forecast30: PeriodForecastResponse = Field(..., description="30-Tage Prognose")
    forecast60: PeriodForecastResponse = Field(..., description="60-Tage Prognose")
    forecast90: PeriodForecastResponse = Field(..., description="90-Tage Prognose")
    dailyData: List[ForecastDataPointResponse] = Field(default_factory=list)
    skontoImpact: SkontoImpactResponse = Field(..., description="Skonto-Auswirkung")
    riskWarning: Optional[str] = Field(None, description="Risikowarnung")


# =============================================================================
# Response Models - Supplier Performance
# =============================================================================


class SupplierMetricsResponse(BaseModel):
    """Metriken fuer einen Lieferanten."""
    id: str = Field(..., description="Lieferanten-ID")
    name: str = Field(..., description="Lieferantenname")
    punctuality: float = Field(..., description="Puenktlichkeit (%)")
    accuracy: float = Field(..., description="Genauigkeit (%)")
    orders: int = Field(..., description="Anzahl Bestellungen")
    volume: float = Field(..., description="Bestellvolumen")
    priceTrend: float = Field(..., description="Preistrend (%)")
    trendDirection: str = Field(..., description="Trend-Richtung (up/down/stable)")


class PriceTrendDataResponse(BaseModel):
    """Preistrend-Datenpunkt."""
    period: str = Field(..., description="Periode (YYYY-MM)")
    change: float = Field(..., description="Aenderung (%)")
    orders: int = Field(..., description="Anzahl Bestellungen")


class SupplierPerformanceResponse(BaseModel):
    """Gesamtergebnis der Lieferanten-Performance."""
    generatedAt: str = Field(..., description="Generierungszeitpunkt")
    periodDays: int = Field(..., description="Auswertungszeitraum")
    overallPunctuality: float = Field(..., description="Gesamt-Puenktlichkeit (%)")
    overallAccuracy: float = Field(..., description="Gesamt-Genauigkeit (%)")
    totalSuppliers: int = Field(..., description="Gesamtzahl Lieferanten")
    activeSuppliers: int = Field(..., description="Aktive Lieferanten")
    avgPriceChange: float = Field(..., description="Durchschn. Preistrend (%)")
    topSuppliers: List[SupplierMetricsResponse] = Field(default_factory=list)
    priceTrendData: List[PriceTrendDataResponse] = Field(default_factory=list)
    criticalCount: int = Field(..., description="Anzahl kritischer Lieferanten")


# =============================================================================
# Response Models - Customer LTV
# =============================================================================


class CustomerMetricsResponse(BaseModel):
    """Metriken fuer einen Kunden."""
    id: str = Field(..., description="Kunden-ID")
    name: str = Field(..., description="Kundenname")
    ltv: float = Field(..., description="Lifetime Value")
    orders: int = Field(..., description="Anzahl Bestellungen")
    avgOrder: float = Field(..., description="Durchschn. Bestellwert")
    trend: str = Field(..., description="Umsatz-Trend (growing/stable/declining)")
    trendPct: float = Field(..., description="Trend (%)")
    churnRisk: str = Field(..., description="Churn-Risiko (low/medium/high/critical)")
    churnScore: float = Field(..., description="Churn-Score (0-100)")
    daysSinceOrder: int = Field(..., description="Tage seit letzter Bestellung")


class AtRiskCustomerResponse(BaseModel):
    """Kunde mit Churn-Risiko."""
    id: str = Field(..., description="Kunden-ID")
    name: str = Field(..., description="Kundenname")
    ltv: float = Field(..., description="Lifetime Value")
    churnRisk: str = Field(..., description="Churn-Risiko")
    churnScore: float = Field(..., description="Churn-Score")
    daysSinceOrder: int = Field(..., description="Tage seit letzter Bestellung")


class TrendDataResponse(BaseModel):
    """Trend-Datenpunkt."""
    period: str = Field(..., description="Periode (YYYY-MM)")
    revenue: float = Field(..., description="Umsatz")
    customers: int = Field(..., description="Anzahl Kunden")
    avgOrder: float = Field(..., description="Durchschn. Bestellwert")


class CustomerLTVResponse(BaseModel):
    """Gesamtergebnis der Customer LTV Analyse."""
    generatedAt: str = Field(..., description="Generierungszeitpunkt")
    periodDays: int = Field(..., description="Auswertungszeitraum")
    totalCustomers: int = Field(..., description="Gesamtzahl Kunden")
    activeCustomers: int = Field(..., description="Aktive Kunden")
    totalLTV: float = Field(..., description="Gesamt-LTV")
    avgLTV: float = Field(..., description="Durchschn. LTV")
    avgChurnRisk: float = Field(..., description="Durchschn. Churn-Risiko")
    overallTrend: str = Field(..., description="Gesamt-Trend")
    trendPercentage: float = Field(..., description="Trend (%)")
    topCustomers: List[CustomerMetricsResponse] = Field(default_factory=list)
    atRiskCustomers: List[AtRiskCustomerResponse] = Field(default_factory=list)
    trendData: List[TrendDataResponse] = Field(default_factory=list)


# =============================================================================
# API Endpoints - Cash-Flow Forecast
# =============================================================================


@router.get(
    "/cash-flow-forecast",
    response_model=CashFlowForecastResponse,
    summary="Cash-Flow Prognose abrufen",
    description="Liefert 30/60/90 Tage Liquiditaetsprognose basierend auf offenen Rechnungen.",
)
async def get_cash_flow_forecast(
    starting_balance: Optional[float] = Query(
        None,
        description="Anfangssaldo (optional, wird sonst ermittelt)"
    ),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> CashFlowForecastResponse:
    """
    Ruft Cash-Flow Prognose fuer Dashboard-Widget ab.

    Die Prognose basiert auf:
    - Offenen Forderungen (erwartete Einnahmen)
    - Offenen Verbindlichkeiten (erwartete Ausgaben)
    - Skonto-Deadlines

    **Returns:**
    - 30/60/90 Tage Prognosen
    - Taegliche Datenpunkte fuer Chart
    - Skonto-Auswirkungen
    - Risikowanrungen bei kritischer Liquiditaet
    """
    service = get_cash_flow_forecast_service()

    balance = Decimal(str(starting_balance)) if starting_balance else None

    result = await service.get_forecast(
        db=db,
        user_id=current_user.id,
        company_id=current_user.company_id,
        starting_balance=balance,
    )

    logger.info(
        "cash_flow_forecast_requested",
        user_id=str(current_user.id),
    )

    return CashFlowForecastResponse(
        generatedAt=result.generated_at.isoformat(),
        currentBalance=float(result.current_balance),
        forecast30=PeriodForecastResponse(
            periodDays=result.forecast_30.period_days,
            totalIncome=float(result.forecast_30.total_expected_income),
            totalExpenses=float(result.forecast_30.total_expected_expenses),
            netFlow=float(result.forecast_30.net_flow),
            endingBalance=float(result.forecast_30.ending_balance),
            confidenceScore=result.forecast_30.confidence_score,
            incomeInvoiceCount=result.forecast_30.income_invoice_count,
            expenseInvoiceCount=result.forecast_30.expense_invoice_count,
        ),
        forecast60=PeriodForecastResponse(
            periodDays=result.forecast_60.period_days,
            totalIncome=float(result.forecast_60.total_expected_income),
            totalExpenses=float(result.forecast_60.total_expected_expenses),
            netFlow=float(result.forecast_60.net_flow),
            endingBalance=float(result.forecast_60.ending_balance),
            confidenceScore=result.forecast_60.confidence_score,
            incomeInvoiceCount=result.forecast_60.income_invoice_count,
            expenseInvoiceCount=result.forecast_60.expense_invoice_count,
        ),
        forecast90=PeriodForecastResponse(
            periodDays=result.forecast_90.period_days,
            totalIncome=float(result.forecast_90.total_expected_income),
            totalExpenses=float(result.forecast_90.total_expected_expenses),
            netFlow=float(result.forecast_90.net_flow),
            endingBalance=float(result.forecast_90.ending_balance),
            confidenceScore=result.forecast_90.confidence_score,
            incomeInvoiceCount=result.forecast_90.income_invoice_count,
            expenseInvoiceCount=result.forecast_90.expense_invoice_count,
        ),
        dailyData=[
            ForecastDataPointResponse(
                date=point.date.isoformat(),
                income=float(point.expected_income),
                expenses=float(point.expected_expenses),
                net=float(point.net_flow),
                balance=float(point.cumulative_balance),
                confidence=point.confidence,
            )
            for point in result.daily_data
        ],
        skontoImpact=SkontoImpactResponse(
            invoiceCount=result.skonto_impact.invoice_count,
            potentialSavings=float(result.skonto_impact.potential_savings),
        ),
        riskWarning=result.risk_warning,
    )


@router.get(
    "/cash-flow-forecast/chart",
    response_model=List[ForecastDataPointResponse],
    summary="Cash-Flow Chart-Daten",
    description="Liefert taegliche Datenpunkte fuer Chart-Visualisierung.",
)
async def get_cash_flow_chart_data(
    days: int = Query(30, ge=7, le=90, description="Anzahl Tage (7, 30, 60, 90)"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> List[ForecastDataPointResponse]:
    """
    Liefert Chart-Daten fuer Cash-Flow Visualisierung.

    Optimiert fuer Frontend-Charts mit:
    - Taeglichen Datenpunkten
    - Einnahmen vs Ausgaben
    - Kumulativem Saldo
    """
    service = get_cash_flow_forecast_service()

    data = await service.get_chart_data(
        db=db,
        user_id=current_user.id,
        company_id=current_user.company_id,
        days=days,
    )

    return [
        ForecastDataPointResponse(
            date=point["date"],
            income=point["income"],
            expenses=point["expenses"],
            net=point["net"],
            balance=point["balance"],
            confidence=point["confidence"],
        )
        for point in data
    ]


# =============================================================================
# API Endpoints - Supplier Performance
# =============================================================================


@router.get(
    "/supplier-performance",
    response_model=SupplierPerformanceResponse,
    summary="Lieferanten-Performance abrufen",
    description="Liefert Lieferanten-Metriken fuer Dashboard-Widget.",
)
async def get_supplier_performance(
    period_days: int = Query(90, ge=7, le=365, description="Auswertungszeitraum in Tagen"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> SupplierPerformanceResponse:
    """
    Ruft Lieferanten-Performance fuer Dashboard-Widget ab.

    Metriken:
    - Puenktlichkeit (On-Time %)
    - Genauigkeit (Korrekte Rechnungen %)
    - Preistrend (Preisentwicklung)
    - Top 5 Lieferanten

    **Returns:**
    - Aggregierte Metriken
    - Top-Lieferanten-Liste
    - Preistrend-Daten fuer Chart
    - Anzahl kritischer Lieferanten
    """
    service = get_supplier_performance_service()

    data = await service.get_widget_data(
        db=db,
        user_id=current_user.id,
        company_id=current_user.company_id,
        period_days=period_days,
    )

    logger.info(
        "supplier_performance_requested",
        user_id=str(current_user.id),
        period_days=period_days,
    )

    return SupplierPerformanceResponse(
        generatedAt=data["generatedAt"],
        periodDays=data["periodDays"],
        overallPunctuality=data["overallPunctuality"],
        overallAccuracy=data["overallAccuracy"],
        totalSuppliers=data["totalSuppliers"],
        activeSuppliers=data["activeSuppliers"],
        avgPriceChange=data["avgPriceChange"],
        topSuppliers=[
            SupplierMetricsResponse(**s) for s in data["topSuppliers"]
        ],
        priceTrendData=[
            PriceTrendDataResponse(**p) for p in data["priceTrendData"]
        ],
        criticalCount=data["criticalCount"],
    )


# =============================================================================
# API Endpoints - Customer LTV
# =============================================================================


@router.get(
    "/customer-ltv",
    response_model=CustomerLTVResponse,
    summary="Customer Lifetime Value abrufen",
    description="Liefert Kundenwert-Metriken fuer Dashboard-Widget.",
)
async def get_customer_ltv(
    period_days: int = Query(365, ge=30, le=730, description="Auswertungszeitraum in Tagen"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> CustomerLTVResponse:
    """
    Ruft Customer Lifetime Value fuer Dashboard-Widget ab.

    Metriken:
    - Kumulativer Umsatz pro Kunde
    - Trend-Analyse (wachsend/ruecklaeufig)
    - Churn-Risiko-Indikator
    - Top-Kunden-Ranking

    **Returns:**
    - Aggregierte LTV-Metriken
    - Top-Kunden-Liste
    - Risiko-Kunden-Liste
    - Trend-Daten fuer Chart
    """
    service = get_customer_ltv_service()

    data = await service.get_widget_data(
        db=db,
        user_id=current_user.id,
        company_id=current_user.company_id,
        period_days=period_days,
    )

    logger.info(
        "customer_ltv_requested",
        user_id=str(current_user.id),
        period_days=period_days,
    )

    return CustomerLTVResponse(
        generatedAt=data["generatedAt"],
        periodDays=data["periodDays"],
        totalCustomers=data["totalCustomers"],
        activeCustomers=data["activeCustomers"],
        totalLTV=data["totalLTV"],
        avgLTV=data["avgLTV"],
        avgChurnRisk=data["avgChurnRisk"],
        overallTrend=data["overallTrend"],
        trendPercentage=data["trendPercentage"],
        topCustomers=[
            CustomerMetricsResponse(**c) for c in data["topCustomers"]
        ],
        atRiskCustomers=[
            AtRiskCustomerResponse(**c) for c in data["atRiskCustomers"]
        ],
        trendData=[
            TrendDataResponse(**t) for t in data["trendData"]
        ],
    )
