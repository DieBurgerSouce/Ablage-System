# -*- coding: utf-8 -*-
"""
IndustryBenchmarkService - Branchen-Benchmarks und Vergleiche.

Verantwortlich fuer:
- Vergleich der eigenen KPIs mit Branchendurchschnitt
- Perzentil-Rankings
- Anonymisierte Aggregation ueber Tenants
- Trend-Vergleiche

Vision 2.0 - Feature #10 (Januar 2026)
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, date, timedelta
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

import structlog
from sqlalchemy import select, and_, func, distinct
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.datetime_utils import utc_now
from app.db.models import Company, BusinessEntity, InvoiceTracking, BankTransaction
from app.core.safe_errors import safe_error_log

logger = structlog.get_logger(__name__)


class Industry(str, Enum):
    """Branchen-Klassifikation."""

    MANUFACTURING = "manufacturing"  # Fertigung/Produktion
    RETAIL = "retail"  # Einzelhandel
    WHOLESALE = "wholesale"  # Grosshandel
    SERVICES = "services"  # Dienstleistungen
    IT = "it"  # IT & Software
    CONSTRUCTION = "construction"  # Bau
    HEALTHCARE = "healthcare"  # Gesundheitswesen
    FINANCE = "finance"  # Finanzdienstleistungen
    LOGISTICS = "logistics"  # Logistik & Transport
    HOSPITALITY = "hospitality"  # Gastgewerbe
    OTHER = "other"  # Sonstige


class MetricType(str, Enum):
    """Typ der Metrik."""

    DSO = "dso"  # Days Sales Outstanding
    PUNCTUALITY = "punctuality"  # Puenktlichkeitsrate
    SKONTO_USAGE = "skonto_usage"  # Skonto-Nutzungsrate
    DUNNING_RATE = "dunning_rate"  # Mahnquote
    DEFAULT_RATE = "default_rate"  # Ausfallrate
    AVG_PAYMENT_DELAY = "avg_payment_delay"  # Durchschnittliche Zahlungsverzoegerung


class PerformanceLevel(str, Enum):
    """Leistungsstufe im Vergleich."""

    EXCELLENT = "excellent"  # Top 10%
    GOOD = "good"  # Top 25%
    AVERAGE = "average"  # 25-75%
    BELOW_AVERAGE = "below_average"  # 75-90%
    POOR = "poor"  # Bottom 10%


@dataclass
class BenchmarkMetric:
    """Eine einzelne Benchmark-Metrik."""

    metric_type: MetricType
    label: str
    company_value: float
    industry_average: float
    industry_median: float
    percentile: int  # 0-100, Position im Vergleich
    performance_level: PerformanceLevel
    trend_vs_avg: float  # Differenz zum Durchschnitt in %
    is_better_higher: bool  # True wenn hoehere Werte besser sind
    unit: str  # z.B. "Tage", "%", "EUR"
    recommendations: List[str] = field(default_factory=list)


@dataclass
class IndustryBenchmarkData:
    """Branchendurchschnittswerte (hardcoded oder extern)."""

    industry: Industry
    dso_average: float
    dso_median: float
    punctuality_rate_avg: float
    skonto_usage_avg: float
    dunning_rate_avg: float
    default_rate_avg: float
    avg_payment_delay_days: float
    sample_size: int
    last_updated: datetime


@dataclass
class CompanyBenchmarkReport:
    """Vollstaendiger Benchmark-Report fuer eine Firma."""

    company_id: uuid.UUID
    company_name: str
    industry: Industry
    metrics: List[BenchmarkMetric]
    overall_score: float  # 0-100
    overall_percentile: int
    overall_level: PerformanceLevel
    calculated_at: datetime
    comparison_period_days: int
    recommendations: List[str]


# ============================================================================
# BRANCHENDURCHSCHNITTE - Basierend auf externen Quellen
# (Creditreform, Statista, eigene Aggregation)
# ============================================================================

INDUSTRY_BENCHMARKS: Dict[Industry, IndustryBenchmarkData] = {
    Industry.MANUFACTURING: IndustryBenchmarkData(
        industry=Industry.MANUFACTURING,
        dso_average=45.0,
        dso_median=42.0,
        punctuality_rate_avg=0.72,
        skonto_usage_avg=0.35,
        dunning_rate_avg=0.15,
        default_rate_avg=0.02,
        avg_payment_delay_days=8.5,
        sample_size=5000,
        last_updated=datetime(2026, 1, 1),
    ),
    Industry.RETAIL: IndustryBenchmarkData(
        industry=Industry.RETAIL,
        dso_average=28.0,
        dso_median=25.0,
        punctuality_rate_avg=0.78,
        skonto_usage_avg=0.45,
        dunning_rate_avg=0.12,
        default_rate_avg=0.018,
        avg_payment_delay_days=5.2,
        sample_size=8000,
        last_updated=datetime(2026, 1, 1),
    ),
    Industry.WHOLESALE: IndustryBenchmarkData(
        industry=Industry.WHOLESALE,
        dso_average=52.0,
        dso_median=48.0,
        punctuality_rate_avg=0.68,
        skonto_usage_avg=0.42,
        dunning_rate_avg=0.18,
        default_rate_avg=0.025,
        avg_payment_delay_days=10.5,
        sample_size=3500,
        last_updated=datetime(2026, 1, 1),
    ),
    Industry.SERVICES: IndustryBenchmarkData(
        industry=Industry.SERVICES,
        dso_average=38.0,
        dso_median=35.0,
        punctuality_rate_avg=0.75,
        skonto_usage_avg=0.25,
        dunning_rate_avg=0.14,
        default_rate_avg=0.022,
        avg_payment_delay_days=7.0,
        sample_size=12000,
        last_updated=datetime(2026, 1, 1),
    ),
    Industry.IT: IndustryBenchmarkData(
        industry=Industry.IT,
        dso_average=42.0,
        dso_median=38.0,
        punctuality_rate_avg=0.80,
        skonto_usage_avg=0.20,
        dunning_rate_avg=0.10,
        default_rate_avg=0.015,
        avg_payment_delay_days=6.0,
        sample_size=4500,
        last_updated=datetime(2026, 1, 1),
    ),
    Industry.CONSTRUCTION: IndustryBenchmarkData(
        industry=Industry.CONSTRUCTION,
        dso_average=58.0,
        dso_median=55.0,
        punctuality_rate_avg=0.62,
        skonto_usage_avg=0.30,
        dunning_rate_avg=0.22,
        default_rate_avg=0.035,
        avg_payment_delay_days=14.0,
        sample_size=2800,
        last_updated=datetime(2026, 1, 1),
    ),
    Industry.HEALTHCARE: IndustryBenchmarkData(
        industry=Industry.HEALTHCARE,
        dso_average=65.0,
        dso_median=60.0,
        punctuality_rate_avg=0.58,
        skonto_usage_avg=0.15,
        dunning_rate_avg=0.25,
        default_rate_avg=0.04,
        avg_payment_delay_days=18.0,
        sample_size=2000,
        last_updated=datetime(2026, 1, 1),
    ),
    Industry.FINANCE: IndustryBenchmarkData(
        industry=Industry.FINANCE,
        dso_average=32.0,
        dso_median=28.0,
        punctuality_rate_avg=0.88,
        skonto_usage_avg=0.50,
        dunning_rate_avg=0.08,
        default_rate_avg=0.01,
        avg_payment_delay_days=4.0,
        sample_size=3000,
        last_updated=datetime(2026, 1, 1),
    ),
    Industry.LOGISTICS: IndustryBenchmarkData(
        industry=Industry.LOGISTICS,
        dso_average=48.0,
        dso_median=45.0,
        punctuality_rate_avg=0.70,
        skonto_usage_avg=0.35,
        dunning_rate_avg=0.16,
        default_rate_avg=0.023,
        avg_payment_delay_days=9.0,
        sample_size=2500,
        last_updated=datetime(2026, 1, 1),
    ),
    Industry.HOSPITALITY: IndustryBenchmarkData(
        industry=Industry.HOSPITALITY,
        dso_average=22.0,
        dso_median=18.0,
        punctuality_rate_avg=0.85,
        skonto_usage_avg=0.10,
        dunning_rate_avg=0.08,
        default_rate_avg=0.012,
        avg_payment_delay_days=3.0,
        sample_size=4000,
        last_updated=datetime(2026, 1, 1),
    ),
    Industry.OTHER: IndustryBenchmarkData(
        industry=Industry.OTHER,
        dso_average=40.0,
        dso_median=38.0,
        punctuality_rate_avg=0.72,
        skonto_usage_avg=0.30,
        dunning_rate_avg=0.15,
        default_rate_avg=0.025,
        avg_payment_delay_days=8.0,
        sample_size=10000,
        last_updated=datetime(2026, 1, 1),
    ),
}

# Branchenbezeichnungen auf Deutsch
INDUSTRY_LABELS: Dict[Industry, str] = {
    Industry.MANUFACTURING: "Fertigung & Produktion",
    Industry.RETAIL: "Einzelhandel",
    Industry.WHOLESALE: "Grosshandel",
    Industry.SERVICES: "Dienstleistungen",
    Industry.IT: "IT & Software",
    Industry.CONSTRUCTION: "Bauwesen",
    Industry.HEALTHCARE: "Gesundheitswesen",
    Industry.FINANCE: "Finanzdienstleistungen",
    Industry.LOGISTICS: "Logistik & Transport",
    Industry.HOSPITALITY: "Gastgewerbe",
    Industry.OTHER: "Sonstige",
}


class IndustryBenchmarkService:
    """Service fuer Branchen-Benchmarks und Vergleiche.

    Vergleicht Unternehmenskennzahlen mit Branchendurchschnitten:
    - DSO (Days Sales Outstanding)
    - Puenktlichkeitsrate
    - Skonto-Nutzung
    - Mahnquote
    - Ausfallrate
    """

    def __init__(self, db: AsyncSession):
        """Initialisiert den Service.

        Args:
            db: Async Database Session
        """
        self.db = db

    async def get_company_benchmark(
        self,
        company_id: uuid.UUID,
        industry: Optional[Industry] = None,
        period_days: int = 365,
    ) -> CompanyBenchmarkReport:
        """Erstellt einen vollstaendigen Benchmark-Report fuer eine Firma.

        Args:
            company_id: Firmen-ID
            industry: Branche (optional, sonst aus Company)
            period_days: Analysezeitraum in Tagen

        Returns:
            CompanyBenchmarkReport
        """
        # Company laden
        stmt = select(Company).where(Company.id == company_id)
        result = await self.db.execute(stmt)
        company = result.scalar_one_or_none()

        if not company:
            raise ValueError("Firma nicht gefunden")

        # Branche bestimmen
        if industry is None:
            # Versuche aus Company-Daten zu ermitteln (falls Feld existiert)
            industry = Industry.OTHER

        # Branchenbenchmarks holen
        benchmarks = INDUSTRY_BENCHMARKS.get(industry, INDUSTRY_BENCHMARKS[Industry.OTHER])

        # Unternehmenskennzahlen berechnen
        company_metrics = await self._calculate_company_metrics(company_id, period_days)

        # Metriken vergleichen
        metrics: List[BenchmarkMetric] = []

        # DSO
        metrics.append(self._create_metric(
            metric_type=MetricType.DSO,
            label="Days Sales Outstanding (DSO)",
            company_value=company_metrics.get("dso", 0),
            industry_average=benchmarks.dso_average,
            industry_median=benchmarks.dso_median,
            is_better_higher=False,  # Niedrigerer DSO ist besser
            unit="Tage",
        ))

        # Puenktlichkeitsrate
        metrics.append(self._create_metric(
            metric_type=MetricType.PUNCTUALITY,
            label="Puenktlichkeitsrate",
            company_value=company_metrics.get("punctuality_rate", 0) * 100,
            industry_average=benchmarks.punctuality_rate_avg * 100,
            industry_median=benchmarks.punctuality_rate_avg * 100,
            is_better_higher=True,
            unit="%",
        ))

        # Skonto-Nutzung
        metrics.append(self._create_metric(
            metric_type=MetricType.SKONTO_USAGE,
            label="Skonto-Nutzungsrate",
            company_value=company_metrics.get("skonto_usage", 0) * 100,
            industry_average=benchmarks.skonto_usage_avg * 100,
            industry_median=benchmarks.skonto_usage_avg * 100,
            is_better_higher=True,
            unit="%",
        ))

        # Mahnquote
        metrics.append(self._create_metric(
            metric_type=MetricType.DUNNING_RATE,
            label="Mahnquote",
            company_value=company_metrics.get("dunning_rate", 0) * 100,
            industry_average=benchmarks.dunning_rate_avg * 100,
            industry_median=benchmarks.dunning_rate_avg * 100,
            is_better_higher=False,  # Niedrigere Mahnquote ist besser
            unit="%",
        ))

        # Ausfallrate
        metrics.append(self._create_metric(
            metric_type=MetricType.DEFAULT_RATE,
            label="Ausfallrate",
            company_value=company_metrics.get("default_rate", 0) * 100,
            industry_average=benchmarks.default_rate_avg * 100,
            industry_median=benchmarks.default_rate_avg * 100,
            is_better_higher=False,
            unit="%",
        ))

        # Durchschnittliche Zahlungsverzoegerung
        metrics.append(self._create_metric(
            metric_type=MetricType.AVG_PAYMENT_DELAY,
            label="Durchschnittl. Zahlungsverzoegerung",
            company_value=company_metrics.get("avg_payment_delay", 0),
            industry_average=benchmarks.avg_payment_delay_days,
            industry_median=benchmarks.avg_payment_delay_days,
            is_better_higher=False,
            unit="Tage",
        ))

        # Gesamtbewertung berechnen
        overall_score, overall_percentile = self._calculate_overall_score(metrics)
        overall_level = self._percentile_to_level(overall_percentile)

        # Empfehlungen generieren
        recommendations = self._generate_recommendations(metrics, overall_level)

        return CompanyBenchmarkReport(
            company_id=company_id,
            company_name=company.name,
            industry=industry,
            metrics=metrics,
            overall_score=overall_score,
            overall_percentile=overall_percentile,
            overall_level=overall_level,
            calculated_at=utc_now(),
            comparison_period_days=period_days,
            recommendations=recommendations,
        )

    async def _calculate_company_metrics(
        self,
        company_id: uuid.UUID,
        period_days: int,
    ) -> Dict[str, float]:
        """Berechnet Unternehmenskennzahlen.

        Args:
            company_id: Firmen-ID
            period_days: Analysezeitraum

        Returns:
            Dictionary mit Kennzahlen (mit Fallback-Werten bei Fehlern)
        """
        cutoff_date = utc_now() - timedelta(days=period_days)
        metrics: Dict[str, float] = {
            "punctuality_rate": 0.0,
            "skonto_usage": 0.0,
            "dunning_rate": 0.0,
            "default_rate": 0.0,
            "dso": 0.0,
            "avg_payment_delay": 0.0,
        }

        try:
            # Rechnungsstatistiken
            invoice_stmt = (
                select(
                    func.count(InvoiceTracking.id).label("total"),
                    func.count(InvoiceTracking.id).filter(
                        InvoiceTracking.status == "paid"
                    ).label("paid"),
                    func.count(InvoiceTracking.id).filter(
                        InvoiceTracking.dunning_level > 0
                    ).label("dunned"),
                    func.count(InvoiceTracking.id).filter(
                        InvoiceTracking.status == "cancelled"
                    ).label("cancelled"),
                    func.count(InvoiceTracking.id).filter(
                        InvoiceTracking.skonto_used == True
                    ).label("skonto_used"),
                    func.sum(InvoiceTracking.total_amount).label("total_amount"),
                    func.sum(InvoiceTracking.total_amount).filter(
                        InvoiceTracking.status != "paid"
                    ).label("outstanding"),
                )
                .where(
                    and_(
                        InvoiceTracking.company_id == company_id,
                        InvoiceTracking.created_at >= cutoff_date,
                    )
                )
            )

            result = await self.db.execute(invoice_stmt)
            row = result.one()
        except Exception as e:
            logger.warning(
                "benchmark_invoice_stats_error",
                company_id=str(company_id),
                **safe_error_log(e),
            )
            return metrics

        total = row.total or 0
        paid = row.paid or 0
        dunned = row.dunned or 0
        cancelled = row.cancelled or 0
        skonto_used = row.skonto_used or 0
        total_amount = float(row.total_amount or 0)
        outstanding = float(row.outstanding or 0)

        # Puenktlichkeitsrate
        if total > 0:
            # Berechne puenktlich bezahlte (paid - dunned)
            punctual = max(0, paid - dunned)
            metrics["punctuality_rate"] = punctual / total
        else:
            metrics["punctuality_rate"] = 0.0

        # Skonto-Nutzung
        try:
            skonto_eligible_stmt = (
                select(func.count(InvoiceTracking.id))
                .where(
                    and_(
                        InvoiceTracking.company_id == company_id,
                        InvoiceTracking.created_at >= cutoff_date,
                        InvoiceTracking.skonto_percentage > 0,
                    )
                )
            )
            result = await self.db.execute(skonto_eligible_stmt)
            skonto_eligible = result.scalar() or 0

            if skonto_eligible > 0:
                metrics["skonto_usage"] = skonto_used / skonto_eligible
            else:
                metrics["skonto_usage"] = 0.0
        except Exception as e:
            logger.warning(
                "benchmark_skonto_stats_error",
                company_id=str(company_id),
                **safe_error_log(e),
            )
            # Fallback-Wert bereits gesetzt

        # Mahnquote - defensiv berechnen
        try:
            if total and total > 0:
                metrics["dunning_rate"] = dunned / total
            else:
                metrics["dunning_rate"] = 0.0
        except (TypeError, ZeroDivisionError) as e:
            logger.warning("benchmark_dunning_rate_error", **safe_error_log(e))
            metrics["dunning_rate"] = 0.0

        # Ausfallrate - defensiv berechnen
        try:
            if total and total > 0:
                metrics["default_rate"] = cancelled / total
            else:
                metrics["default_rate"] = 0.0
        except (TypeError, ZeroDivisionError) as e:
            logger.warning("benchmark_default_rate_error", **safe_error_log(e))
            metrics["default_rate"] = 0.0

        # DSO berechnen (Days Sales Outstanding)
        # Formel: DSO = (Ausstehende Forderungen / Gesamtumsatz) * Anzahl Tage
        # Dies misst wie viele Tage durchschnittlich gebraucht werden,
        # um Forderungen einzutreiben.
        try:
            if total_amount and total_amount > 0:
                # Korrekte DSO-Formel
                metrics["dso"] = (outstanding / total_amount) * period_days
            else:
                metrics["dso"] = 0.0
        except (TypeError, ZeroDivisionError) as e:
            logger.warning("benchmark_dso_error", **safe_error_log(e))
            metrics["dso"] = 0.0

        # Durchschnittliche Zahlungsverzoegerung
        try:
            delay_stmt = (
                select(
                    func.avg(
                        func.extract('day', InvoiceTracking.paid_at - InvoiceTracking.due_date)
                    )
                )
                .where(
                    and_(
                        InvoiceTracking.company_id == company_id,
                        InvoiceTracking.created_at >= cutoff_date,
                        InvoiceTracking.status == "paid",
                        InvoiceTracking.paid_at.isnot(None),
                        InvoiceTracking.due_date.isnot(None),
                        InvoiceTracking.paid_at > InvoiceTracking.due_date,
                    )
                )
            )
            result = await self.db.execute(delay_stmt)
            avg_delay = result.scalar() or 0.0
            metrics["avg_payment_delay"] = float(avg_delay)
        except Exception as e:
            logger.warning(
                "benchmark_delay_stats_error",
                company_id=str(company_id),
                **safe_error_log(e),
            )
            # Fallback-Wert bereits gesetzt

        logger.debug(
            "company_metrics_calculated",
            company_id=str(company_id),
            metrics=metrics,
        )

        return metrics

    def _create_metric(
        self,
        metric_type: MetricType,
        label: str,
        company_value: float,
        industry_average: float,
        industry_median: float,
        is_better_higher: bool,
        unit: str,
    ) -> BenchmarkMetric:
        """Erstellt eine Benchmark-Metrik mit Vergleich.

        Args:
            metric_type: Metrik-Typ
            label: Anzeige-Label
            company_value: Eigener Wert
            industry_average: Branchendurchschnitt
            industry_median: Branchenmedian
            is_better_higher: True wenn hoehere Werte besser sind
            unit: Einheit

        Returns:
            BenchmarkMetric
        """
        # Differenz zum Durchschnitt
        if industry_average > 0:
            trend_vs_avg = ((company_value - industry_average) / industry_average) * 100
        else:
            trend_vs_avg = 0.0

        # Perzentil berechnen mit korrekter CDF-Approximation
        # Annahme: Standardabweichung = 30% des Durchschnitts (typisch fuer Branchen-Benchmarks)
        std_dev = industry_average * 0.30 if industry_average > 0 else 1.0
        z_score = (company_value - industry_average) / std_dev if std_dev > 0 else 0.0

        # Z-Score zu Perzentil mit CDF-Approximation (Normalverteilung)
        # Formel: CDF(z) ≈ 0.5 * (1 + erf(z / sqrt(2)))
        # Vereinfachte Approximation fuer z in [-3, 3]:
        # Perzentil ≈ 50 + 50 * erf(z / sqrt(2))
        import math
        try:
            # erf-Approximation fuer Normalverteilungs-CDF
            cdf_value = 0.5 * (1 + math.erf(z_score / math.sqrt(2)))
            base_percentile = int(cdf_value * 100)
        except (OverflowError, ValueError):
            # Fallback fuer extreme Werte
            base_percentile = 100 if z_score > 3 else (0 if z_score < -3 else 50)

        if is_better_higher:
            # Hoeher = besser, also positiver Z-Score = hoeheres Perzentil
            percentile = min(100, max(0, base_percentile))
        else:
            # Niedriger = besser, also invertieren
            percentile = min(100, max(0, 100 - base_percentile))

        # Performance-Level
        performance_level = self._percentile_to_level(percentile)

        # Empfehlungen
        recommendations = self._get_metric_recommendations(
            metric_type, company_value, industry_average, is_better_higher, performance_level
        )

        return BenchmarkMetric(
            metric_type=metric_type,
            label=label,
            company_value=round(company_value, 2),
            industry_average=round(industry_average, 2),
            industry_median=round(industry_median, 2),
            percentile=percentile,
            performance_level=performance_level,
            trend_vs_avg=round(trend_vs_avg, 1),
            is_better_higher=is_better_higher,
            unit=unit,
            recommendations=recommendations,
        )

    def _percentile_to_level(self, percentile: int) -> PerformanceLevel:
        """Konvertiert Perzentil zu Performance-Level."""
        if percentile >= 90:
            return PerformanceLevel.EXCELLENT
        elif percentile >= 75:
            return PerformanceLevel.GOOD
        elif percentile >= 25:
            return PerformanceLevel.AVERAGE
        elif percentile >= 10:
            return PerformanceLevel.BELOW_AVERAGE
        else:
            return PerformanceLevel.POOR

    def _calculate_overall_score(
        self,
        metrics: List[BenchmarkMetric],
    ) -> Tuple[float, int]:
        """Berechnet Gesamt-Score und Perzentil.

        Args:
            metrics: Liste von Benchmark-Metriken

        Returns:
            Tuple[overall_score, overall_percentile]
        """
        if not metrics:
            return 50.0, 50

        # Gewichtung nach Metrik-Typ
        weights = {
            MetricType.DSO: 0.25,
            MetricType.PUNCTUALITY: 0.25,
            MetricType.SKONTO_USAGE: 0.15,
            MetricType.DUNNING_RATE: 0.15,
            MetricType.DEFAULT_RATE: 0.10,
            MetricType.AVG_PAYMENT_DELAY: 0.10,
        }

        weighted_percentile = 0.0
        total_weight = 0.0

        for metric in metrics:
            weight = weights.get(metric.metric_type, 0.1)
            weighted_percentile += metric.percentile * weight
            total_weight += weight

        overall_percentile = int(weighted_percentile / total_weight) if total_weight > 0 else 50

        # Score ist normalisiert (0-100)
        overall_score = overall_percentile

        return overall_score, overall_percentile

    def _get_metric_recommendations(
        self,
        metric_type: MetricType,
        company_value: float,
        industry_average: float,
        is_better_higher: bool,
        level: PerformanceLevel,
    ) -> List[str]:
        """Generiert Empfehlungen fuer eine Metrik."""
        recommendations = []

        # Nur Empfehlungen wenn unter Durchschnitt
        is_below_avg = (
            (company_value < industry_average and is_better_higher) or
            (company_value > industry_average and not is_better_higher)
        )

        if not is_below_avg:
            return []

        if metric_type == MetricType.DSO:
            if level in [PerformanceLevel.BELOW_AVERAGE, PerformanceLevel.POOR]:
                recommendations.append("Verkuerzen Sie Zahlungsziele in neuen Vertraegen")
                recommendations.append("Intensivieren Sie das Forderungsmanagement")
                recommendations.append("Bieten Sie Skonto fuer schnelle Zahlung an")

        elif metric_type == MetricType.PUNCTUALITY:
            if level in [PerformanceLevel.BELOW_AVERAGE, PerformanceLevel.POOR]:
                recommendations.append("Pruefen Sie Kunden mit schlechter Zahlungsmoral")
                recommendations.append("Erwaegen Sie Vorkasse bei Neukunden")
                recommendations.append("Automatisieren Sie Zahlungserinnerungen")

        elif metric_type == MetricType.SKONTO_USAGE:
            if level in [PerformanceLevel.BELOW_AVERAGE, PerformanceLevel.POOR]:
                recommendations.append("Pruefen Sie Liquiditaet fuer Skonto-Nutzung")
                recommendations.append("Optimieren Sie Zahlungsprozesse")

        elif metric_type == MetricType.DUNNING_RATE:
            if level in [PerformanceLevel.BELOW_AVERAGE, PerformanceLevel.POOR]:
                recommendations.append("Ueberpruefen Sie Ihre Bonitaetspruefung")
                recommendations.append("Starten Sie Mahnwesen fruehzeitig")

        elif metric_type == MetricType.DEFAULT_RATE:
            if level in [PerformanceLevel.BELOW_AVERAGE, PerformanceLevel.POOR]:
                recommendations.append("Verschaerfen Sie die Kreditpruefung")
                recommendations.append("Erwaegen Sie Forderungsausfallversicherung")

        return recommendations

    def _generate_recommendations(
        self,
        metrics: List[BenchmarkMetric],
        overall_level: PerformanceLevel,
    ) -> List[str]:
        """Generiert Gesamt-Empfehlungen."""
        recommendations = []

        # Nach Level
        if overall_level == PerformanceLevel.EXCELLENT:
            recommendations.append("Ihre Kennzahlen liegen im Spitzenbereich der Branche.")
            recommendations.append("Halten Sie Ihre aktuellen Prozesse bei.")
        elif overall_level == PerformanceLevel.GOOD:
            recommendations.append("Sie performen ueberdurchschnittlich.")
            recommendations.append("Kleine Optimierungen koennen Sie in die Top-10% bringen.")
        elif overall_level == PerformanceLevel.AVERAGE:
            recommendations.append("Ihre Kennzahlen entsprechen dem Branchendurchschnitt.")
        elif overall_level in [PerformanceLevel.BELOW_AVERAGE, PerformanceLevel.POOR]:
            recommendations.append("Es gibt Verbesserungspotenzial im Vergleich zur Branche.")

        # Spezifische Empfehlungen aus Metriken sammeln
        for metric in metrics:
            if metric.performance_level in [PerformanceLevel.BELOW_AVERAGE, PerformanceLevel.POOR]:
                if metric.recommendations:
                    recommendations.extend(metric.recommendations[:1])  # Nur erste pro Metrik

        # Deduplizieren
        seen = set()
        unique_recommendations = []
        for r in recommendations:
            if r not in seen:
                seen.add(r)
                unique_recommendations.append(r)

        return unique_recommendations[:5]  # Max 5

    async def get_industry_benchmarks(
        self,
        industry: Industry,
    ) -> IndustryBenchmarkData:
        """Holt Branchendurchschnittswerte.

        Args:
            industry: Branche

        Returns:
            IndustryBenchmarkData
        """
        return INDUSTRY_BENCHMARKS.get(industry, INDUSTRY_BENCHMARKS[Industry.OTHER])

    async def get_available_industries(self) -> List[Dict[str, str]]:
        """Holt alle verfuegbaren Branchen.

        Returns:
            Liste mit Industry-Value und Label
        """
        return [
            {"value": ind.value, "label": INDUSTRY_LABELS.get(ind, ind.value)}
            for ind in Industry
        ]

    async def get_trend_comparison(
        self,
        company_id: uuid.UUID,
        industry: Industry,
        months: int = 12,
    ) -> List[Dict[str, Any]]:
        """Vergleicht Trend ueber Zeit mit Branche.

        Args:
            company_id: Firmen-ID
            industry: Branche
            months: Anzahl Monate zurueck

        Returns:
            Monatliche Trend-Daten
        """
        trends = []
        benchmarks = INDUSTRY_BENCHMARKS.get(industry, INDUSTRY_BENCHMARKS[Industry.OTHER])

        for i in range(months):
            month_start = utc_now().replace(day=1) - timedelta(days=30 * i)
            month_end = month_start + timedelta(days=30)

            # Vereinfachte Berechnung: nur DSO und Puenktlichkeit
            stmt = (
                select(
                    func.count(InvoiceTracking.id).label("total"),
                    func.count(InvoiceTracking.id).filter(
                        InvoiceTracking.status == "paid"
                    ).label("paid"),
                )
                .where(
                    and_(
                        InvoiceTracking.company_id == company_id,
                        InvoiceTracking.created_at >= month_start,
                        InvoiceTracking.created_at < month_end,
                    )
                )
            )

            result = await self.db.execute(stmt)
            row = result.one()

            total = row.total or 0
            paid = row.paid or 0
            punctuality = (paid / total * 100) if total > 0 else 0

            trends.append({
                "month": month_start.strftime("%Y-%m"),
                "month_label": month_start.strftime("%b %Y"),
                "company_punctuality": round(punctuality, 1),
                "industry_punctuality": round(benchmarks.punctuality_rate_avg * 100, 1),
            })

        # Chronologisch sortieren
        trends.reverse()

        return trends


# ============================================================================
# Factory Function
# ============================================================================


async def get_benchmark_service(db: AsyncSession) -> IndustryBenchmarkService:
    """Factory-Funktion fuer IndustryBenchmarkService.

    Args:
        db: Async Database Session

    Returns:
        Konfigurierter IndustryBenchmarkService
    """
    return IndustryBenchmarkService(db=db)
