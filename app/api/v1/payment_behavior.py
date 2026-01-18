# -*- coding: utf-8 -*-
"""
Payment Behavior Report API Endpoints.

Endpoints fuer Kunden-Zahlungsverhaltens-Analyse:
- Einzelanalyse eines Kunden
- Gesamtreport ueber alle Kunden
- Kunden-Ranking nach Zahlungsverhalten
"""

from datetime import date
from decimal import Decimal
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_active_user, get_db
from app.db.models import User
from app.services.payment_behavior_report_service import (
    get_payment_behavior_report_service,
    PaymentBehaviorCategory,
    PaymentTrend,
)


router = APIRouter(prefix="/payment-behavior", tags=["Payment Behavior"])


# =============================================================================
# Response Models
# =============================================================================

class PaymentMetricsResponse(BaseModel):
    """Zahlungsmetriken fuer einen Kunden."""
    entity_id: str = Field(..., description="Kunden-ID")
    entity_name: str = Field(..., description="Kundenname")

    # Basis-Statistiken
    total_invoices: int = Field(..., description="Gesamtanzahl Rechnungen")
    paid_invoices: int = Field(..., description="Bezahlte Rechnungen")
    unpaid_invoices: int = Field(..., description="Unbezahlte Rechnungen")
    overdue_invoices: int = Field(..., description="Ueberfaellige Rechnungen")

    # Volumen
    total_volume: float = Field(..., description="Gesamtvolumen EUR")
    paid_volume: float = Field(..., description="Bezahltes Volumen EUR")
    outstanding_volume: float = Field(..., description="Ausstehendes Volumen EUR")
    overdue_volume: float = Field(..., description="Ueberfaelliges Volumen EUR")

    # Zeitbasierte Metriken
    avg_payment_days: float = Field(..., description="Durchschnittliche Zahlungsdauer in Tagen")
    min_payment_days: int = Field(..., description="Minimale Zahlungsdauer")
    max_payment_days: int = Field(..., description="Maximale Zahlungsdauer")
    median_payment_days: float = Field(..., description="Median Zahlungsdauer")

    # Verhalten
    punctuality_rate: float = Field(..., ge=0, le=1, description="Puenktlichkeitsrate (0-1)")
    early_payment_rate: float = Field(..., ge=0, le=1, description="Rate vorzeitiger Zahlungen")
    late_payment_rate: float = Field(..., ge=0, le=1, description="Rate verspaeteter Zahlungen")
    default_rate: float = Field(..., ge=0, le=1, description="Ausfallrate")

    # Skonto
    skonto_utilization_rate: float = Field(..., ge=0, le=1, description="Skonto-Nutzungsrate")
    skonto_saved: float = Field(..., description="Eingesparter Skonto-Betrag EUR")

    # Kategorisierung
    behavior_category: str = Field(..., description="Verhaltens-Kategorie")
    behavior_category_label: str = Field(..., description="Deutsche Bezeichnung")
    payment_trend: str = Field(..., description="Zahlungstrend")
    payment_trend_label: str = Field(..., description="Trend-Bezeichnung")

    # Score
    payment_score: float = Field(..., ge=0, le=100, description="Zahlungs-Score (0-100)")

    # Zeitraum
    first_invoice_date: Optional[str] = Field(None, description="Erstes Rechnungsdatum")
    last_invoice_date: Optional[str] = Field(None, description="Letztes Rechnungsdatum")
    analysis_period_days: int = Field(..., description="Auswertungszeitraum in Tagen")

    class Config:
        json_schema_extra = {
            "example": {
                "entity_id": "123e4567-e89b-12d3-a456-426614174000",
                "entity_name": "Mustermann GmbH",
                "total_invoices": 24,
                "paid_invoices": 20,
                "unpaid_invoices": 4,
                "overdue_invoices": 1,
                "total_volume": 50000.00,
                "paid_volume": 45000.00,
                "outstanding_volume": 5000.00,
                "overdue_volume": 1200.00,
                "avg_payment_days": 28.5,
                "min_payment_days": 14,
                "max_payment_days": 45,
                "median_payment_days": 27.0,
                "punctuality_rate": 0.85,
                "early_payment_rate": 0.15,
                "late_payment_rate": 0.10,
                "default_rate": 0.02,
                "skonto_utilization_rate": 0.60,
                "skonto_saved": 450.00,
                "behavior_category": "punctual",
                "behavior_category_label": "Puenktlich",
                "payment_trend": "stable",
                "payment_trend_label": "Stabil",
                "payment_score": 82.5,
                "first_invoice_date": "2025-03-15",
                "last_invoice_date": "2026-01-10",
                "analysis_period_days": 365
            }
        }


class PaymentBehaviorSummaryResponse(BaseModel):
    """Zusammenfassung des Zahlungsverhaltens."""
    excellent_count: int = Field(..., description="Anzahl exzellenter Zahler")
    punctual_count: int = Field(..., description="Anzahl puenktlicher Zahler")
    delayed_count: int = Field(..., description="Anzahl verspaeteter Zahler")
    problematic_count: int = Field(..., description="Anzahl problematischer Zahler")
    defaulter_count: int = Field(..., description="Anzahl Ausfaeller")

    avg_payment_days_overall: float = Field(..., description="Durchschnittliche Zahlungsdauer gesamt")
    avg_punctuality_rate: float = Field(..., description="Durchschnittliche Puenktlichkeitsrate")
    avg_payment_score: float = Field(..., description="Durchschnittlicher Payment-Score")

    volume_at_risk: float = Field(..., description="Volumen bei Risiko-Kunden EUR")
    overdue_total: float = Field(..., description="Gesamtes ueberfaelliges Volumen EUR")

    improving_count: int = Field(..., description="Sich verbessernde Kunden")
    stable_count: int = Field(..., description="Stabile Kunden")
    declining_count: int = Field(..., description="Sich verschlechternde Kunden")


class PaymentBehaviorReportResponse(BaseModel):
    """Kompletter Zahlungsverhaltens-Report."""
    company_id: str = Field(..., description="Firmen-ID")

    total_customers: int = Field(..., description="Gesamtanzahl Kunden")
    analyzed_customers: int = Field(..., description="Analysierte Kunden")

    summary: PaymentBehaviorSummaryResponse = Field(..., description="Zusammenfassung")

    top_payers: List[PaymentMetricsResponse] = Field(..., description="Beste Zahler")
    worst_payers: List[PaymentMetricsResponse] = Field(..., description="Schlechteste Zahler")
    improving_customers: List[PaymentMetricsResponse] = Field(..., description="Sich verbessernde Kunden")
    declining_customers: List[PaymentMetricsResponse] = Field(..., description="Sich verschlechternde Kunden")
    high_risk_customers: List[PaymentMetricsResponse] = Field(..., description="Risiko-Kunden")

    analysis_period_start: str = Field(..., description="Analysezeitraum Start")
    analysis_period_end: str = Field(..., description="Analysezeitraum Ende")

    benchmark_avg_payment_days: float = Field(..., description="Benchmark Zahlungsdauer")
    benchmark_punctuality_rate: float = Field(..., description="Benchmark Puenktlichkeit")

    generated_at: str = Field(..., description="Report-Generierungszeitpunkt")


class CategoryDistributionResponse(BaseModel):
    """Verteilung der Kunden auf Kategorien."""
    excellent: int = Field(0, description="Exzellente Zahler")
    punctual: int = Field(0, description="Puenktliche Zahler")
    delayed: int = Field(0, description="Verspaetete Zahler")
    problematic: int = Field(0, description="Problematische Zahler")
    defaulter: int = Field(0, description="Ausfaeller")


# =============================================================================
# Helper Functions
# =============================================================================

CATEGORY_LABELS = {
    PaymentBehaviorCategory.EXCELLENT: "Exzellent",
    PaymentBehaviorCategory.PUNCTUAL: "Puenktlich",
    PaymentBehaviorCategory.DELAYED: "Verzoegert",
    PaymentBehaviorCategory.PROBLEMATIC: "Problematisch",
    PaymentBehaviorCategory.DEFAULTER: "Zahlungsausfall",
}

TREND_LABELS = {
    PaymentTrend.IMPROVING: "Verbessernd",
    PaymentTrend.STABLE: "Stabil",
    PaymentTrend.DECLINING: "Verschlechternd",
}


def metrics_to_response(metrics) -> PaymentMetricsResponse:
    """Konvertiert PaymentMetrics zu Response."""
    return PaymentMetricsResponse(
        entity_id=str(metrics.entity_id),
        entity_name=metrics.entity_name,
        total_invoices=metrics.total_invoices,
        paid_invoices=metrics.paid_invoices,
        unpaid_invoices=metrics.unpaid_invoices,
        overdue_invoices=metrics.overdue_invoices,
        total_volume=float(metrics.total_volume),
        paid_volume=float(metrics.paid_volume),
        outstanding_volume=float(metrics.outstanding_volume),
        overdue_volume=float(metrics.overdue_volume),
        avg_payment_days=metrics.avg_payment_days,
        min_payment_days=metrics.min_payment_days,
        max_payment_days=metrics.max_payment_days,
        median_payment_days=metrics.median_payment_days,
        punctuality_rate=metrics.punctuality_rate,
        early_payment_rate=metrics.early_payment_rate,
        late_payment_rate=metrics.late_payment_rate,
        default_rate=metrics.default_rate,
        skonto_utilization_rate=metrics.skonto_utilization_rate,
        skonto_saved=float(metrics.skonto_saved),
        behavior_category=metrics.behavior_category.value,
        behavior_category_label=CATEGORY_LABELS.get(metrics.behavior_category, metrics.behavior_category.value),
        payment_trend=metrics.payment_trend.value,
        payment_trend_label=TREND_LABELS.get(metrics.payment_trend, metrics.payment_trend.value),
        payment_score=metrics.payment_score,
        first_invoice_date=metrics.first_invoice_date.isoformat() if metrics.first_invoice_date else None,
        last_invoice_date=metrics.last_invoice_date.isoformat() if metrics.last_invoice_date else None,
        analysis_period_days=metrics.analysis_period_days,
    )


# =============================================================================
# API Endpoints
# =============================================================================

@router.get(
    "/{entity_id}",
    response_model=PaymentMetricsResponse,
    summary="Kunden-Zahlungsverhalten analysieren",
    description="Analysiert das Zahlungsverhalten eines einzelnen Kunden.",
)
async def get_customer_payment_behavior(
    entity_id: UUID,
    period_days: int = Query(365, ge=30, le=730, description="Auswertungszeitraum in Tagen"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Analysiert Zahlungsverhalten eines Kunden.

    - **entity_id**: Kunden-ID
    - **period_days**: Auswertungszeitraum (30-730 Tage)

    Die Analyse umfasst:
    - Puenktlichkeitsrate und Zahlungsdauer
    - Skonto-Nutzung
    - Trend-Entwicklung
    - Risiko-Kategorisierung
    """
    service = get_payment_behavior_report_service()

    metrics = await service.analyze_customer_payment_behavior(
        db=db,
        entity_id=entity_id,
        company_id=current_user.company_id,
        period_days=period_days,
    )

    if not metrics:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Kunde nicht gefunden oder keine Rechnungsdaten vorhanden"
        )

    return metrics_to_response(metrics)


@router.get(
    "",
    response_model=PaymentBehaviorReportResponse,
    summary="Zahlungsverhaltens-Report",
    description="Erstellt einen Report ueber das Zahlungsverhalten aller Kunden.",
)
async def get_payment_behavior_report(
    period_days: int = Query(365, ge=30, le=730, description="Auswertungszeitraum in Tagen"),
    top_n: int = Query(10, ge=1, le=50, description="Anzahl Top/Bottom Kunden"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Erstellt Gesamt-Report ueber Kunden-Zahlungsverhalten.

    Der Report enthaelt:
    - Kategorien-Verteilung (Exzellent/Puenktlich/Verzoegert/Problematisch/Ausfall)
    - Top-Zahler und schlechteste Zahler
    - Trend-Entwicklungen
    - Risiko-Kunden mit hohem ausstehenden Volumen

    Wird fuer:
    - Kreditlimit-Entscheidungen
    - Mahnstrategie-Optimierung
    - Kundensegmentierung
    """
    service = get_payment_behavior_report_service()

    report = await service.generate_payment_behavior_report(
        db=db,
        company_id=current_user.company_id,
        period_days=period_days,
        top_n=top_n,
    )

    summary = PaymentBehaviorSummaryResponse(
        excellent_count=report.summary.excellent_count,
        punctual_count=report.summary.punctual_count,
        delayed_count=report.summary.delayed_count,
        problematic_count=report.summary.problematic_count,
        defaulter_count=report.summary.defaulter_count,
        avg_payment_days_overall=round(report.summary.avg_payment_days_overall, 1),
        avg_punctuality_rate=round(report.summary.avg_punctuality_rate, 3),
        avg_payment_score=round(report.summary.avg_payment_score, 1),
        volume_at_risk=float(report.summary.volume_at_risk),
        overdue_total=float(report.summary.overdue_total),
        improving_count=report.summary.improving_count,
        stable_count=report.summary.stable_count,
        declining_count=report.summary.declining_count,
    )

    return PaymentBehaviorReportResponse(
        company_id=str(report.company_id),
        total_customers=report.total_customers,
        analyzed_customers=report.analyzed_customers,
        summary=summary,
        top_payers=[metrics_to_response(m) for m in report.top_payers],
        worst_payers=[metrics_to_response(m) for m in report.worst_payers],
        improving_customers=[metrics_to_response(m) for m in report.improving_customers],
        declining_customers=[metrics_to_response(m) for m in report.declining_customers],
        high_risk_customers=[metrics_to_response(m) for m in report.high_risk_customers],
        analysis_period_start=report.analysis_period_start.isoformat(),
        analysis_period_end=report.analysis_period_end.isoformat(),
        benchmark_avg_payment_days=report.benchmark_avg_payment_days,
        benchmark_punctuality_rate=report.benchmark_punctuality_rate,
        generated_at=report.generated_at.isoformat(),
    )


@router.get(
    "/ranking/list",
    response_model=List[PaymentMetricsResponse],
    summary="Kunden-Ranking nach Zahlungsverhalten",
    description="Listet Kunden sortiert nach Zahlungsverhalten.",
)
async def get_customer_payment_ranking(
    period_days: int = Query(365, ge=30, le=730, description="Auswertungszeitraum in Tagen"),
    limit: int = Query(50, ge=1, le=200, description="Max. Anzahl Ergebnisse"),
    sort_by: str = Query(
        "payment_score",
        description="Sortierfeld: payment_score, avg_payment_days, punctuality_rate, total_volume, overdue_volume"
    ),
    sort_desc: bool = Query(True, description="Absteigend sortieren"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Ruft Kunden-Ranking nach Zahlungsverhalten ab.

    Sortieroptionen:
    - **payment_score**: Gesamtbewertung (Standard)
    - **avg_payment_days**: Durchschnittliche Zahlungsdauer
    - **punctuality_rate**: Puenktlichkeitsrate
    - **total_volume**: Gesamtvolumen
    - **overdue_volume**: Ueberfaelliges Volumen
    """
    service = get_payment_behavior_report_service()

    valid_sort_fields = {"payment_score", "avg_payment_days", "punctuality_rate", "total_volume", "overdue_volume"}
    if sort_by not in valid_sort_fields:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Ungueltiges Sortierfeld. Erlaubt: {', '.join(valid_sort_fields)}"
        )

    ranking = await service.get_customer_ranking_by_payment(
        db=db,
        company_id=current_user.company_id,
        period_days=period_days,
        limit=limit,
        sort_by=sort_by,
        sort_desc=sort_desc,
    )

    return [metrics_to_response(m) for m in ranking]


@router.get(
    "/categories/distribution",
    response_model=CategoryDistributionResponse,
    summary="Kategorien-Verteilung abrufen",
    description="Zeigt die Verteilung der Kunden auf die Zahlungsverhaltens-Kategorien.",
)
async def get_category_distribution(
    period_days: int = Query(365, ge=30, le=730, description="Auswertungszeitraum in Tagen"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Schnelle Uebersicht ueber Kategorien-Verteilung.

    Kategorien:
    - **Exzellent**: Zahlt vor Faelligkeit, hohe Skonto-Nutzung
    - **Puenktlich**: Zahlt innerhalb der Frist
    - **Verzoegert**: 1-14 Tage verspaetet
    - **Problematisch**: Haeufig stark verzoegert
    - **Zahlungsausfall**: Regelmaessige Ausfaelle (>90 Tage)
    """
    service = get_payment_behavior_report_service()

    report = await service.generate_payment_behavior_report(
        db=db,
        company_id=current_user.company_id,
        period_days=period_days,
        top_n=1,  # Minimale Daten
    )

    return CategoryDistributionResponse(
        excellent=report.summary.excellent_count,
        punctual=report.summary.punctual_count,
        delayed=report.summary.delayed_count,
        problematic=report.summary.problematic_count,
        defaulter=report.summary.defaulter_count,
    )
