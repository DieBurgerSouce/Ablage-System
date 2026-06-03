# -*- coding: utf-8 -*-
"""
Dashboard Widgets API Endpoints.

API-Endpoints für Dashboard-Widget-Daten:
- Cash-Flow Forecast (30/60/90 Tage Prognose)
- Supplier Performance (Lieferanten-Metriken)
- Customer Lifetime Value (Kundenwert-Analyse)
- Revenue Trend (Umsatz-Trend-Analyse)
- DSO Tracker (Days Sales Outstanding)
- Margin Analyzer (Margen-Analyse)

Enterprise Feature: Phase 7 Dashboard Widgets (Januar 2026)
"""

from datetime import date
from decimal import Decimal
from typing import Dict, List, Optional
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_active_user, get_db, get_user_company_id_dep
from app.core.rate_limiting import limiter, get_user_identifier
from app.core.safe_errors import safe_error_log
from app.db.models import User
from app.services.dashboard import (
    get_cash_flow_forecast_service,
    get_supplier_performance_service,
    get_customer_ltv_service,
    get_revenue_trend_service,
    get_dso_tracker_service,
    get_margin_analyzer_service,
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
    """Zusammenfassung für einen Prognosezeitraum."""
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
    """Metriken für einen Lieferanten."""
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
    change: float = Field(..., description="Änderung (%)")
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
    """Metriken für einen Kunden."""
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
@limiter.limit("60/minute", key_func=get_user_identifier)
async def get_cash_flow_forecast(
    request: Request,  # Required for rate limiter
    starting_balance: Optional[float] = Query(
        None,
        description="Anfangssaldo (optional, wird sonst ermittelt)"
    ),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_user_company_id_dep),
) -> CashFlowForecastResponse:
    """
    Ruft Cash-Flow Prognose für Dashboard-Widget ab.

    Die Prognose basiert auf:
    - Offenen Forderungen (erwartete Einnahmen)
    - Offenen Verbindlichkeiten (erwartete Ausgaben)
    - Skonto-Deadlines

    **Returns:**
    - 30/60/90 Tage Prognosen
    - Tägliche Datenpunkte für Chart
    - Skonto-Auswirkungen
    - Risikowanrungen bei kritischer Liquiditaet
    """
    try:
        service = get_cash_flow_forecast_service()

        balance = Decimal(str(starting_balance)) if starting_balance else None

        result = await service.get_forecast(
            db=db,
            user_id=current_user.id,
            company_id=company_id,
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
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("cash_flow_forecast_failed", **safe_error_log(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Verarbeitung fehlgeschlagen",
        )


@router.get(
    "/cash-flow-forecast/chart",
    response_model=List[ForecastDataPointResponse],
    summary="Cash-Flow Chart-Daten",
    description="Liefert tägliche Datenpunkte für Chart-Visualisierung.",
)
@limiter.limit("60/minute", key_func=get_user_identifier)
async def get_cash_flow_chart_data(
    request: Request,  # Required for rate limiter
    days: int = Query(30, ge=7, le=90, description="Anzahl Tage (7, 30, 60, 90)"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_user_company_id_dep),
) -> List[ForecastDataPointResponse]:
    """
    Liefert Chart-Daten für Cash-Flow Visualisierung.

    Optimiert für Frontend-Charts mit:
    - Täglichen Datenpunkten
    - Einnahmen vs Ausgaben
    - Kumulativem Saldo
    """
    try:
        service = get_cash_flow_forecast_service()

        data = await service.get_chart_data(
            db=db,
            user_id=current_user.id,
            company_id=company_id,
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
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("cash_flow_chart_failed", **safe_error_log(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Verarbeitung fehlgeschlagen",
        )


# =============================================================================
# API Endpoints - Supplier Performance
# =============================================================================


@router.get(
    "/supplier-performance",
    response_model=SupplierPerformanceResponse,
    summary="Lieferanten-Performance abrufen",
    description="Liefert Lieferanten-Metriken für Dashboard-Widget.",
)
@limiter.limit("60/minute", key_func=get_user_identifier)
async def get_supplier_performance(
    request: Request,  # Required for rate limiter
    period_days: int = Query(90, ge=7, le=365, description="Auswertungszeitraum in Tagen"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_user_company_id_dep),
) -> SupplierPerformanceResponse:
    """
    Ruft Lieferanten-Performance für Dashboard-Widget ab.

    Metriken:
    - Puenktlichkeit (On-Time %)
    - Genauigkeit (Korrekte Rechnungen %)
    - Preistrend (Preisentwicklung)
    - Top 5 Lieferanten

    **Returns:**
    - Aggregierte Metriken
    - Top-Lieferanten-Liste
    - Preistrend-Daten für Chart
    - Anzahl kritischer Lieferanten
    """
    try:
        service = get_supplier_performance_service()

        data = await service.get_widget_data(
            db=db,
            user_id=current_user.id,
            company_id=company_id,
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
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("supplier_performance_failed", **safe_error_log(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Verarbeitung fehlgeschlagen",
        )


# =============================================================================
# API Endpoints - Customer LTV
# =============================================================================


@router.get(
    "/customer-ltv",
    response_model=CustomerLTVResponse,
    summary="Customer Lifetime Value abrufen",
    description="Liefert Kundenwert-Metriken für Dashboard-Widget.",
)
@limiter.limit("60/minute", key_func=get_user_identifier)
async def get_customer_ltv(
    request: Request,  # Required for rate limiter
    period_days: int = Query(365, ge=30, le=730, description="Auswertungszeitraum in Tagen"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_user_company_id_dep),
) -> CustomerLTVResponse:
    """
    Ruft Customer Lifetime Value für Dashboard-Widget ab.

    Metriken:
    - Kumulativer Umsatz pro Kunde
    - Trend-Analyse (wachsend/rücklaeufig)
    - Churn-Risiko-Indikator
    - Top-Kunden-Ranking

    **Returns:**
    - Aggregierte LTV-Metriken
    - Top-Kunden-Liste
    - Risiko-Kunden-Liste
    - Trend-Daten für Chart
    """
    try:
        service = get_customer_ltv_service()

        data = await service.get_widget_data(
            db=db,
            user_id=current_user.id,
            company_id=company_id,
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
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("customer_ltv_failed", **safe_error_log(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Verarbeitung fehlgeschlagen",
        )


# =============================================================================
# Response Models - Revenue Trend
# =============================================================================


class RevenueDataPointResponse(BaseModel):
    """Einzelner Datenpunkt im Umsatz-Trend."""
    period: str = Field(..., description="Periode (YYYY-MM)")
    revenue: float = Field(..., description="Umsatz")
    expense: float = Field(..., description="Ausgaben")
    net: float = Field(..., description="Netto-Ergebnis")
    documentCount: int = Field(..., description="Anzahl Dokumente")
    category: str = Field(..., description="Kategorie")


class RevenueTrendResponse(BaseModel):
    """Gesamtergebnis der Umsatz-Trend-Analyse."""
    generatedAt: str = Field(..., description="Generierungszeitpunkt")
    dateFrom: str = Field(..., description="Startdatum")
    dateTo: str = Field(..., description="Enddatum")
    totalRevenue: float = Field(..., description="Gesamtumsatz")
    totalExpenses: float = Field(..., description="Gesamtausgaben")
    netIncome: float = Field(..., description="Netto-Einkommen")
    dataPoints: List[RevenueDataPointResponse] = Field(
        default_factory=list, description="Umsatz-Datenpunkte"
    )
    comparison: Optional[Dict[str, str]] = Field(
        None, description="Vergleich mit Vorperiode"
    )


# =============================================================================
# Response Models - DSO Tracker
# =============================================================================


class DSODataPointResponse(BaseModel):
    """Einzelner Datenpunkt im DSO-Trend."""
    period: str = Field(..., description="Periode (YYYY-MM)")
    dsoValue: float = Field(..., description="DSO-Wert in Tagen")
    invoiceCount: int = Field(..., description="Anzahl Rechnungen")
    totalOutstanding: float = Field(..., description="Ausstehender Gesamtbetrag")
    totalRevenue: float = Field(..., description="Gesamtumsatz")


class AgingBucketResponse(BaseModel):
    """Fälligkeitsklasse für ausstehende Rechnungen."""
    label: str = Field(..., description="Bezeichnung der Fälligkeitsklasse")
    count: int = Field(..., description="Anzahl Rechnungen")
    amount: float = Field(..., description="Gesamtbetrag")
    percentage: float = Field(..., description="Anteil in Prozent")


class DSOTrackerResponse(BaseModel):
    """Gesamtergebnis der DSO-Analyse."""
    generatedAt: str = Field(..., description="Generierungszeitpunkt")
    dateFrom: str = Field(..., description="Startdatum")
    dateTo: str = Field(..., description="Enddatum")
    currentDSO: float = Field(..., description="Aktueller DSO-Wert in Tagen")
    benchmarkDSO: float = Field(..., description="Branchendurchschnitt DSO in Tagen")
    dsoTrend: List[DSODataPointResponse] = Field(
        default_factory=list, description="DSO-Trend-Datenpunkte"
    )
    agingBuckets: List[AgingBucketResponse] = Field(
        default_factory=list, description="Fälligkeitsverteilung"
    )
    totalOutstanding: float = Field(..., description="Gesamt ausstehender Betrag")
    totalReceivables: float = Field(..., description="Gesamtforderungen")
    overdueCount: int = Field(..., description="Anzahl überfälliger Rechnungen")
    comparison: Optional[Dict[str, str]] = Field(
        None, description="Vergleich mit Vorperiode"
    )


# =============================================================================
# Response Models - Margin Analyzer
# =============================================================================


class CategoryMarginResponse(BaseModel):
    """Margen-Daten für eine Kategorie."""
    category: str = Field(..., description="Dokumentkategorie")
    revenue: float = Field(..., description="Umsatz")
    costs: float = Field(..., description="Kosten")
    margin: float = Field(..., description="Marge (absolut)")
    marginPct: float = Field(..., description="Marge in Prozent")
    documentCount: int = Field(..., description="Anzahl Dokumente")


class MarginTrendPointResponse(BaseModel):
    """Margen-Trend-Datenpunkt."""
    period: str = Field(..., description="Periode (YYYY-MM)")
    revenue: float = Field(..., description="Umsatz")
    costs: float = Field(..., description="Kosten")
    margin: float = Field(..., description="Marge (absolut)")
    marginPct: float = Field(..., description="Marge in Prozent")


class MarginAnalyzerResponse(BaseModel):
    """Gesamtergebnis der Margen-Analyse."""
    generatedAt: str = Field(..., description="Generierungszeitpunkt")
    dateFrom: str = Field(..., description="Startdatum")
    dateTo: str = Field(..., description="Enddatum")
    totalRevenue: float = Field(..., description="Gesamtumsatz")
    totalCosts: float = Field(..., description="Gesamtkosten")
    overallMargin: float = Field(..., description="Gesamtmarge (absolut)")
    overallMarginPct: float = Field(..., description="Gesamtmarge in Prozent")
    categories: List[CategoryMarginResponse] = Field(
        default_factory=list, description="Margen nach Kategorie"
    )
    trend: List[MarginTrendPointResponse] = Field(
        default_factory=list, description="Margen-Trend-Datenpunkte"
    )
    comparison: Optional[Dict[str, str]] = Field(
        None, description="Vergleich mit Vorperiode"
    )


# =============================================================================
# API Endpoints - Revenue Trend
# =============================================================================


@router.get(
    "/revenue-trend",
    response_model=RevenueTrendResponse,
    summary="Umsatz-Trend abrufen",
    description="Liefert Umsatz-Trend-Daten für Dashboard-Widget mit Zeitreihen.",
)
@limiter.limit("60/minute", key_func=get_user_identifier)
async def get_revenue_trend(
    request: Request,  # Required for rate limiter
    date_from: Optional[date] = Query(
        None, description="Startdatum (Standard: 6 Monate zurück)"
    ),
    date_to: Optional[date] = Query(
        None, description="Enddatum (Standard: heute)"
    ),
    compare_period: Optional[str] = Query(
        None, description="Vergleichszeitraum (previous_period, yoy)"
    ),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_user_company_id_dep),
) -> RevenueTrendResponse:
    """
    Ruft Umsatz-Trend für Dashboard-Widget ab.

    Metriken:
    - Monatlicher Umsatz und Ausgaben
    - Netto-Ergebnis pro Periode
    - Optionaler Periodenvergleich

    **Returns:**
    - Zeitreihen-Datenpunkte für Chart
    - Aggregierte Gesamtwerte
    - Vergleichsdaten (optional)
    """
    try:
        service = get_revenue_trend_service()

        result = await service.get_revenue_trend(
            db=db,
            user_id=current_user.id,
            company_id=company_id,
            date_from=date_from,
            date_to=date_to,
            compare_period=compare_period,
        )

        logger.info(
            "revenue_trend_requested",
            user_id=str(current_user.id),
        )

        return RevenueTrendResponse(
            generatedAt=result.generated_at.isoformat(),
            dateFrom=result.date_from.isoformat(),
            dateTo=result.date_to.isoformat(),
            totalRevenue=result.total_revenue,
            totalExpenses=result.total_expenses,
            netIncome=result.net_income,
            dataPoints=[
                RevenueDataPointResponse(
                    period=dp.period,
                    revenue=dp.revenue,
                    expense=dp.expense,
                    net=dp.net,
                    documentCount=dp.document_count,
                    category=dp.category,
                )
                for dp in result.data_points
            ],
            comparison=result.comparison,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("revenue_trend_failed", **safe_error_log(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Verarbeitung fehlgeschlagen",
        )


# =============================================================================
# API Endpoints - DSO Tracker
# =============================================================================


@router.get(
    "/dso-tracker",
    response_model=DSOTrackerResponse,
    summary="DSO-Tracker abrufen",
    description="Liefert Days Sales Outstanding Metriken für Dashboard-Widget.",
)
@limiter.limit("60/minute", key_func=get_user_identifier)
async def get_dso_tracker(
    request: Request,  # Required for rate limiter
    date_from: Optional[date] = Query(
        None, description="Startdatum (Standard: 6 Monate zurück)"
    ),
    date_to: Optional[date] = Query(
        None, description="Enddatum (Standard: heute)"
    ),
    compare_period: Optional[str] = Query(
        None, description="Vergleichszeitraum (previous_period, yoy)"
    ),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_user_company_id_dep),
) -> DSOTrackerResponse:
    """
    Ruft DSO-Metriken für Dashboard-Widget ab.

    Metriken:
    - Aktueller DSO-Wert
    - 6-Monats-Trend
    - Fälligkeitsverteilung (Aging Buckets)
    - Branchenbenchmark

    **Returns:**
    - DSO-Trend-Datenpunkte
    - Fälligkeitsklassen
    - Ausstehende Betraege
    - Vergleichsdaten (optional)
    """
    try:
        service = get_dso_tracker_service()

        result = await service.get_dso_data(
            db=db,
            user_id=current_user.id,
            company_id=company_id,
            date_from=date_from,
            date_to=date_to,
            compare_period=compare_period,
        )

        logger.info(
            "dso_tracker_requested",
            user_id=str(current_user.id),
        )

        return DSOTrackerResponse(
            generatedAt=result.generated_at.isoformat(),
            dateFrom=result.date_from.isoformat(),
            dateTo=result.date_to.isoformat(),
            currentDSO=result.current_dso,
            benchmarkDSO=result.benchmark_dso,
            dsoTrend=[
                DSODataPointResponse(
                    period=dp.period,
                    dsoValue=dp.dso_value,
                    invoiceCount=dp.invoice_count,
                    totalOutstanding=dp.total_outstanding,
                    totalRevenue=dp.total_revenue,
                )
                for dp in result.dso_trend
            ],
            agingBuckets=[
                AgingBucketResponse(
                    label=ab.label,
                    count=ab.count,
                    amount=ab.amount,
                    percentage=ab.percentage,
                )
                for ab in result.aging_buckets
            ],
            totalOutstanding=result.total_outstanding,
            totalReceivables=result.total_receivables,
            overdueCount=result.overdue_count,
            comparison=result.comparison,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("dso_tracker_failed", **safe_error_log(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Verarbeitung fehlgeschlagen",
        )


# =============================================================================
# API Endpoints - Margin Analyzer
# =============================================================================


@router.get(
    "/margin-analyzer",
    response_model=MarginAnalyzerResponse,
    summary="Margen-Analyse abrufen",
    description="Liefert Margen-Analyse-Daten nach Kategorie für Dashboard-Widget.",
)
@limiter.limit("60/minute", key_func=get_user_identifier)
async def get_margin_analyzer(
    request: Request,  # Required for rate limiter
    date_from: Optional[date] = Query(
        None, description="Startdatum (Standard: 6 Monate zurück)"
    ),
    date_to: Optional[date] = Query(
        None, description="Enddatum (Standard: heute)"
    ),
    compare_period: Optional[str] = Query(
        None, description="Vergleichszeitraum (previous_period, yoy)"
    ),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_user_company_id_dep),
) -> MarginAnalyzerResponse:
    """
    Ruft Margen-Analyse für Dashboard-Widget ab.

    Metriken:
    - Umsatz vs. Kosten nach Kategorie
    - Margen-Prozentsatz
    - Monatlicher Margen-Trend
    - Kategorie-Aufschluesselung

    **Returns:**
    - Margen nach Dokumentkategorie
    - Trend-Datenpunkte für Chart
    - Gesamtmarge
    - Vergleichsdaten (optional)
    """
    try:
        service = get_margin_analyzer_service()

        result = await service.get_margin_data(
            db=db,
            user_id=current_user.id,
            company_id=company_id,
            date_from=date_from,
            date_to=date_to,
            compare_period=compare_period,
        )

        logger.info(
            "margin_analyzer_requested",
            user_id=str(current_user.id),
        )

        return MarginAnalyzerResponse(
            generatedAt=result.generated_at.isoformat(),
            dateFrom=result.date_from.isoformat(),
            dateTo=result.date_to.isoformat(),
            totalRevenue=result.total_revenue,
            totalCosts=result.total_costs,
            overallMargin=result.overall_margin,
            overallMarginPct=result.overall_margin_pct,
            categories=[
                CategoryMarginResponse(
                    category=cm.category,
                    revenue=cm.revenue,
                    costs=cm.costs,
                    margin=cm.margin,
                    marginPct=cm.margin_pct,
                    documentCount=cm.document_count,
                )
                for cm in result.categories
            ],
            trend=[
                MarginTrendPointResponse(
                    period=tp.period,
                    revenue=tp.revenue,
                    costs=tp.costs,
                    margin=tp.margin,
                    marginPct=tp.margin_pct,
                )
                for tp in result.trend
            ],
            comparison=result.comparison,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("margin_analyzer_failed", **safe_error_log(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Verarbeitung fehlgeschlagen",
        )
