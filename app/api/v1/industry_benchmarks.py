# -*- coding: utf-8 -*-
"""Industry Benchmarks API - Branchen-Vergleiche und KPIs.

Stellt Endpoints bereit fuer:
- Vergleich der eigenen KPIs mit Branchendurchschnitt
- Perzentil-Rankings
- Trend-Vergleiche ueber Zeit

Vision 2.0 - Feature #10 (Januar 2026)
"""

from typing import Optional, List, Dict, Any
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Path
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.db.models import User
from app.api.dependencies import get_current_active_user
from app.services.analytics.industry_benchmark_service import (
    IndustryBenchmarkService,
    get_benchmark_service,
    Industry,
    MetricType,
    PerformanceLevel,
    BenchmarkMetric,
    CompanyBenchmarkReport,
    IndustryBenchmarkData,
    INDUSTRY_LABELS,
)

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/benchmarks", tags=["industry-benchmarks"])


# ==================== Schemas ====================


class MetricResponse(BaseModel):
    """Benchmark-Metrik Antwort."""

    metric_type: str = Field(..., description="Metrik-Typ")
    label: str = Field(..., description="Anzeige-Label auf Deutsch")
    company_value: float = Field(..., description="Eigener Wert")
    industry_average: float = Field(..., description="Branchendurchschnitt")
    industry_median: float = Field(..., description="Branchenmedian")
    percentile: int = Field(..., description="Perzentil (0-100)")
    performance_level: str = Field(..., description="Leistungsstufe")
    trend_vs_avg: float = Field(..., description="Abweichung vom Durchschnitt in %")
    is_better_higher: bool = Field(..., description="True wenn hoehere Werte besser")
    unit: str = Field(..., description="Einheit")
    recommendations: List[str] = Field(default_factory=list, description="Empfehlungen")


class BenchmarkReportResponse(BaseModel):
    """Vollstaendiger Benchmark-Report."""

    company_id: str = Field(..., description="Firmen-ID")
    company_name: str = Field(..., description="Firmenname")
    industry: str = Field(..., description="Branche")
    industry_label: str = Field(..., description="Branchenbezeichnung auf Deutsch")
    metrics: List[MetricResponse] = Field(..., description="Einzelne Metriken")
    overall_score: float = Field(..., description="Gesamt-Score (0-100)")
    overall_percentile: int = Field(..., description="Gesamt-Perzentil")
    overall_level: str = Field(..., description="Gesamt-Leistungsstufe")
    calculated_at: str = Field(..., description="Berechnungszeitpunkt (ISO)")
    comparison_period_days: int = Field(..., description="Vergleichszeitraum in Tagen")
    recommendations: List[str] = Field(..., description="Gesamt-Empfehlungen")


class IndustryDataResponse(BaseModel):
    """Branchendurchschnittswerte."""

    industry: str = Field(..., description="Branchen-Code")
    industry_label: str = Field(..., description="Branchenbezeichnung")
    dso_average: float = Field(..., description="Durchschnittlicher DSO")
    dso_median: float = Field(..., description="Median DSO")
    punctuality_rate_avg: float = Field(..., description="Durchschnittl. Puenktlichkeit (%)")
    skonto_usage_avg: float = Field(..., description="Durchschnittl. Skonto-Nutzung (%)")
    dunning_rate_avg: float = Field(..., description="Durchschnittl. Mahnquote (%)")
    default_rate_avg: float = Field(..., description="Durchschnittl. Ausfallrate (%)")
    avg_payment_delay_days: float = Field(..., description="Durchschnittl. Zahlungsverzoegerung")
    sample_size: int = Field(..., description="Stichprobengroesse")
    last_updated: str = Field(..., description="Letzte Aktualisierung (ISO)")


class IndustryListResponse(BaseModel):
    """Liste verfuegbarer Branchen."""

    industries: List[Dict[str, str]]


class TrendDataPoint(BaseModel):
    """Ein Trend-Datenpunkt."""

    month: str = Field(..., description="Monat (YYYY-MM)")
    month_label: str = Field(..., description="Monat (z.B. Jan 2026)")
    company_punctuality: float = Field(..., description="Eigene Puenktlichkeitsrate (%)")
    industry_punctuality: float = Field(..., description="Branchen-Puenktlichkeitsrate (%)")


class TrendResponse(BaseModel):
    """Trend-Vergleich Antwort."""

    company_id: str
    industry: str
    industry_label: str
    months: int
    data: List[TrendDataPoint]


# ==================== Helper Functions ====================


def _metric_to_response(metric: BenchmarkMetric) -> MetricResponse:
    """Konvertiert BenchmarkMetric zu Response."""
    return MetricResponse(
        metric_type=metric.metric_type.value,
        label=metric.label,
        company_value=metric.company_value,
        industry_average=metric.industry_average,
        industry_median=metric.industry_median,
        percentile=metric.percentile,
        performance_level=metric.performance_level.value,
        trend_vs_avg=metric.trend_vs_avg,
        is_better_higher=metric.is_better_higher,
        unit=metric.unit,
        recommendations=metric.recommendations,
    )


def _report_to_response(report: CompanyBenchmarkReport) -> BenchmarkReportResponse:
    """Konvertiert CompanyBenchmarkReport zu Response."""
    return BenchmarkReportResponse(
        company_id=str(report.company_id),
        company_name=report.company_name,
        industry=report.industry.value,
        industry_label=INDUSTRY_LABELS.get(report.industry, report.industry.value),
        metrics=[_metric_to_response(m) for m in report.metrics],
        overall_score=report.overall_score,
        overall_percentile=report.overall_percentile,
        overall_level=report.overall_level.value,
        calculated_at=report.calculated_at.isoformat(),
        comparison_period_days=report.comparison_period_days,
        recommendations=report.recommendations,
    )


def _benchmark_data_to_response(data: IndustryBenchmarkData) -> IndustryDataResponse:
    """Konvertiert IndustryBenchmarkData zu Response."""
    return IndustryDataResponse(
        industry=data.industry.value,
        industry_label=INDUSTRY_LABELS.get(data.industry, data.industry.value),
        dso_average=data.dso_average,
        dso_median=data.dso_median,
        punctuality_rate_avg=round(data.punctuality_rate_avg * 100, 1),
        skonto_usage_avg=round(data.skonto_usage_avg * 100, 1),
        dunning_rate_avg=round(data.dunning_rate_avg * 100, 1),
        default_rate_avg=round(data.default_rate_avg * 100, 1),
        avg_payment_delay_days=data.avg_payment_delay_days,
        sample_size=data.sample_size,
        last_updated=data.last_updated.isoformat(),
    )


# ==================== Endpoints ====================


@router.get(
    "/company",
    response_model=BenchmarkReportResponse,
    summary="Eigene KPIs vs Branche",
    description="Vergleicht die eigenen Unternehmenskennzahlen mit dem Branchendurchschnitt.",
)
async def get_company_benchmark(
    industry: Optional[str] = Query(
        None,
        description="Branche (z.B. 'manufacturing', 'retail'). Wenn nicht angegeben: 'other'"
    ),
    period_days: int = Query(365, ge=30, le=730, description="Vergleichszeitraum in Tagen"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> BenchmarkReportResponse:
    """Erstellt Benchmark-Report fuer die eigene Firma."""
    if not current_user.default_company_id:
        raise HTTPException(
            status_code=400,
            detail="Keine Firma zugeordnet.",
        )

    # Branche validieren
    industry_enum = None
    if industry:
        try:
            industry_enum = Industry(industry)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Unbekannte Branche: {industry}. Verfuegbar: {[i.value for i in Industry]}",
            )

    service = await get_benchmark_service(db)

    report = await service.get_company_benchmark(
        company_id=current_user.default_company_id,
        industry=industry_enum,
        period_days=period_days,
    )

    return _report_to_response(report)


@router.get(
    "/industry/{industry}",
    response_model=IndustryDataResponse,
    summary="Branchendurchschnitt abrufen",
    description="Holt die Durchschnittswerte einer Branche.",
)
async def get_industry_benchmarks(
    industry: str = Path(..., description="Branche"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> IndustryDataResponse:
    """Holt Branchendurchschnittswerte."""
    try:
        industry_enum = Industry(industry)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Unbekannte Branche: {industry}",
        )

    service = await get_benchmark_service(db)
    data = await service.get_industry_benchmarks(industry_enum)

    return _benchmark_data_to_response(data)


@router.get(
    "/industries",
    response_model=IndustryListResponse,
    summary="Verfuegbare Branchen",
    description="Listet alle verfuegbaren Branchen mit deutschen Labels.",
)
async def list_industries(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> IndustryListResponse:
    """Listet alle verfuegbaren Branchen."""
    service = await get_benchmark_service(db)
    industries = await service.get_available_industries()

    return IndustryListResponse(industries=industries)


@router.get(
    "/percentile",
    response_model=Dict[str, Any],
    summary="Perzentil-Ranking",
    description="Zeigt das Perzentil-Ranking der Firma im Branchenvergleich.",
)
async def get_percentile_ranking(
    industry: Optional[str] = Query(None, description="Branche"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Dict[str, Any]:
    """Holt Perzentil-Ranking."""
    if not current_user.default_company_id:
        raise HTTPException(status_code=400, detail="Keine Firma zugeordnet.")

    industry_enum = None
    if industry:
        try:
            industry_enum = Industry(industry)
        except ValueError:
            industry_enum = Industry.OTHER

    service = await get_benchmark_service(db)
    report = await service.get_company_benchmark(
        company_id=current_user.default_company_id,
        industry=industry_enum,
    )

    # Perzentile extrahieren
    metric_percentiles = {
        m.metric_type.value: {
            "percentile": m.percentile,
            "level": m.performance_level.value,
            "label": m.label,
        }
        for m in report.metrics
    }

    return {
        "company_id": str(report.company_id),
        "industry": report.industry.value,
        "overall_percentile": report.overall_percentile,
        "overall_level": report.overall_level.value,
        "metric_percentiles": metric_percentiles,
        "interpretation": _interpret_percentile(report.overall_percentile),
    }


def _interpret_percentile(percentile: int) -> str:
    """Interpretiert das Perzentil auf Deutsch."""
    if percentile >= 90:
        return "Sie gehoeren zu den Top 10% Ihrer Branche. Hervorragend!"
    elif percentile >= 75:
        return "Sie performen besser als 75% der Branche. Sehr gut!"
    elif percentile >= 50:
        return "Sie liegen im oberen Mittelfeld der Branche."
    elif percentile >= 25:
        return "Sie liegen im unteren Mittelfeld. Es gibt Optimierungspotenzial."
    else:
        return "Sie liegen unter dem Branchendurchschnitt. Handlungsbedarf vorhanden."


@router.get(
    "/trends",
    response_model=TrendResponse,
    summary="Trend-Vergleich",
    description="Vergleicht den monatlichen Trend mit der Branche.",
)
async def get_trends(
    industry: Optional[str] = Query(None, description="Branche"),
    months: int = Query(12, ge=3, le=24, description="Anzahl Monate"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> TrendResponse:
    """Holt Trend-Vergleich."""
    if not current_user.default_company_id:
        raise HTTPException(status_code=400, detail="Keine Firma zugeordnet.")

    industry_enum = Industry.OTHER
    if industry:
        try:
            industry_enum = Industry(industry)
        except ValueError:
            pass

    service = await get_benchmark_service(db)
    trend_data = await service.get_trend_comparison(
        company_id=current_user.default_company_id,
        industry=industry_enum,
        months=months,
    )

    return TrendResponse(
        company_id=str(current_user.default_company_id),
        industry=industry_enum.value,
        industry_label=INDUSTRY_LABELS.get(industry_enum, industry_enum.value),
        months=months,
        data=[TrendDataPoint(**d) for d in trend_data],
    )


@router.get(
    "/summary",
    response_model=Dict[str, Any],
    summary="Benchmark-Zusammenfassung",
    description="Kompakte Zusammenfassung der wichtigsten Benchmark-KPIs.",
)
async def get_benchmark_summary(
    industry: Optional[str] = Query(None, description="Branche"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Dict[str, Any]:
    """Holt kompakte Benchmark-Zusammenfassung."""
    if not current_user.default_company_id:
        raise HTTPException(status_code=400, detail="Keine Firma zugeordnet.")

    industry_enum = Industry.OTHER
    if industry:
        try:
            industry_enum = Industry(industry)
        except ValueError:
            pass

    service = await get_benchmark_service(db)
    report = await service.get_company_benchmark(
        company_id=current_user.default_company_id,
        industry=industry_enum,
    )

    # Finde beste und schlechteste Metrik
    best_metric = max(report.metrics, key=lambda m: m.percentile)
    worst_metric = min(report.metrics, key=lambda m: m.percentile)

    return {
        "overall": {
            "score": report.overall_score,
            "percentile": report.overall_percentile,
            "level": report.overall_level.value,
            "level_label": _level_to_label(report.overall_level),
        },
        "industry": {
            "code": report.industry.value,
            "label": INDUSTRY_LABELS.get(report.industry, report.industry.value),
        },
        "best_metric": {
            "type": best_metric.metric_type.value,
            "label": best_metric.label,
            "percentile": best_metric.percentile,
            "trend": f"{best_metric.trend_vs_avg:+.1f}% vs Branche",
        },
        "worst_metric": {
            "type": worst_metric.metric_type.value,
            "label": worst_metric.label,
            "percentile": worst_metric.percentile,
            "trend": f"{worst_metric.trend_vs_avg:+.1f}% vs Branche",
        },
        "top_recommendations": report.recommendations[:3],
    }


def _level_to_label(level: PerformanceLevel) -> str:
    """Konvertiert Level zu deutschem Label."""
    labels = {
        PerformanceLevel.EXCELLENT: "Hervorragend",
        PerformanceLevel.GOOD: "Gut",
        PerformanceLevel.AVERAGE: "Durchschnittlich",
        PerformanceLevel.BELOW_AVERAGE: "Unterdurchschnittlich",
        PerformanceLevel.POOR: "Verbesserungswuerdig",
    }
    return labels.get(level, "Unbekannt")
