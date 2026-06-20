# -*- coding: utf-8 -*-
"""
Contract Benchmark Service for Contract Management V2.

Vergleicht Verträge mit Marktdurchschnitten:
- Preisvergleich nach Branche/Kategorie
- Laufzeitvergleich
- Risikobewertung im Vergleich zu Standardverträgen
- Verhandlungsvorschläge

SECURITY:
- NIEMALS Vertragswerte in Logs (Geschäftsgeheimnisse)
- Benchmark-Daten sind anonymisiert

Feinpoliert und durchdacht - Enterprise Contract Management V2.
"""

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional
from uuid import UUID

import structlog
from sqlalchemy import and_, select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_contract import (
    Contract,
    ContractBenchmark,
    ContractType,
    ContractStatus,
)

logger = structlog.get_logger(__name__)


# =============================================================================
# Default Benchmark Data (Used if no DB data available)
# =============================================================================


DEFAULT_BENCHMARKS: Dict[str, Dict[str, Dict[str, float]]] = {
    # Software Licenses
    "software_licenses": {
        "avg_monthly_cost_per_user": {"value": 25.0, "min": 5.0, "max": 150.0},
        "avg_term_months": {"value": 12.0, "min": 1.0, "max": 36.0},
        "avg_notice_days": {"value": 30.0, "min": 14.0, "max": 90.0},
        "avg_discount_percent": {"value": 15.0, "min": 0.0, "max": 40.0},
    },
    # Office Lease
    "office_lease": {
        "avg_monthly_cost_per_sqm": {"value": 15.0, "min": 8.0, "max": 35.0},
        "avg_term_months": {"value": 60.0, "min": 12.0, "max": 120.0},
        "avg_notice_days": {"value": 180.0, "min": 90.0, "max": 365.0},
        "avg_price_adjustment_percent": {"value": 2.5, "min": 0.0, "max": 5.0},
    },
    # Maintenance
    "maintenance": {
        "avg_annual_cost_percent": {"value": 18.0, "min": 10.0, "max": 25.0},  # % of asset value
        "avg_term_months": {"value": 12.0, "min": 3.0, "max": 36.0},
        "avg_notice_days": {"value": 30.0, "min": 14.0, "max": 90.0},
        "avg_response_hours": {"value": 24.0, "min": 4.0, "max": 72.0},
    },
    # Consulting
    "consulting": {
        "avg_daily_rate": {"value": 1200.0, "min": 600.0, "max": 2500.0},
        "avg_term_months": {"value": 6.0, "min": 1.0, "max": 24.0},
        "avg_notice_days": {"value": 14.0, "min": 7.0, "max": 30.0},
    },
    # Vehicle Lease
    "vehicle_lease": {
        "avg_monthly_cost": {"value": 450.0, "min": 200.0, "max": 1500.0},
        "avg_term_months": {"value": 36.0, "min": 12.0, "max": 60.0},
        "avg_km_limit_per_year": {"value": 15000.0, "min": 10000.0, "max": 40000.0},
    },
    # Cleaning Services
    "cleaning": {
        "avg_monthly_cost_per_sqm": {"value": 3.5, "min": 1.5, "max": 8.0},
        "avg_term_months": {"value": 12.0, "min": 3.0, "max": 24.0},
        "avg_notice_days": {"value": 30.0, "min": 14.0, "max": 90.0},
    },
    # Insurance
    "insurance": {
        "avg_annual_premium_percent": {"value": 0.5, "min": 0.1, "max": 2.0},  # % of insured value
        "avg_term_months": {"value": 12.0, "min": 12.0, "max": 12.0},
        "avg_notice_days": {"value": 90.0, "min": 30.0, "max": 90.0},
    },
    # Telecom
    "telecom": {
        "avg_monthly_cost_per_user": {"value": 35.0, "min": 15.0, "max": 80.0},
        "avg_term_months": {"value": 24.0, "min": 12.0, "max": 36.0},
        "avg_notice_days": {"value": 30.0, "min": 14.0, "max": 90.0},
    },
    # Service Agreements
    "service": {
        "avg_monthly_cost": {"value": 2500.0, "min": 500.0, "max": 25000.0},
        "avg_term_months": {"value": 12.0, "min": 3.0, "max": 36.0},
        "avg_notice_days": {"value": 30.0, "min": 14.0, "max": 90.0},
        "avg_sla_uptime_percent": {"value": 99.5, "min": 99.0, "max": 99.99},
    },
}


# Contract type to category mapping
CONTRACT_TYPE_CATEGORIES: Dict[str, str] = {
    ContractType.LICENSE.value: "software_licenses",
    ContractType.LEASE_PROPERTY.value: "office_lease",
    ContractType.LEASE_VEHICLE.value: "vehicle_lease",
    ContractType.LEASE_EQUIPMENT.value: "maintenance",
    ContractType.MAINTENANCE.value: "maintenance",
    ContractType.CUSTOMER_SLA.value: "service",
    ContractType.SUPPLIER_FRAMEWORK.value: "service",
    ContractType.SUPPLIER_PURCHASE.value: "service",
    ContractType.NDA.value: "service",
    ContractType.PARTNERSHIP.value: "service",
    ContractType.EMPLOYMENT_PERMANENT.value: "consulting",
    ContractType.EMPLOYMENT_FIXED.value: "consulting",
    ContractType.EMPLOYMENT_FREELANCE.value: "consulting",
    ContractType.OTHER.value: "service",
}


# =============================================================================
# Data Classes
# =============================================================================


@dataclass
class BenchmarkMetric:
    """Single benchmark metric with comparison."""
    metric_name: str
    metric_display_name: str  # German name
    contract_value: Optional[float]
    benchmark_value: float
    min_value: Optional[float]
    max_value: Optional[float]
    percentile: Optional[int] = None  # Where does contract fall (0-100)
    comparison: str = "average"  # below_average, average, above_average
    variance_percent: Optional[float] = None
    recommendation: Optional[str] = None


@dataclass
class BenchmarkResult:
    """Complete benchmark comparison result."""
    contract_id: UUID
    category: str
    metrics: List[BenchmarkMetric]
    overall_rating: str  # good, average, needs_attention
    overall_score: float  # 0-100
    summary: str
    recommendations: List[str]
    potential_savings: Optional[Decimal] = None
    currency: str = "EUR"
    compared_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class NegotiationSuggestion:
    """Suggestion for contract negotiation."""
    category: str
    title: str
    description: str
    potential_impact: str  # low, medium, high
    potential_savings: Optional[Decimal] = None
    priority: int = 0  # 1 = highest


# =============================================================================
# Contract Benchmark Service
# =============================================================================


class ContractBenchmarkService:
    """
    Service for comparing contracts against market benchmarks.

    Features:
    - Price comparison with industry averages
    - Term and condition comparison
    - Risk assessment vs standard contracts
    - Negotiation improvement suggestions

    SECURITY:
    - Contract values are not logged
    - Benchmark data is anonymized
    """

    def __init__(self, db: AsyncSession):
        """Initialize with database session."""
        self.db = db

    # =========================================================================
    # Main Benchmark Methods
    # =========================================================================

    async def get_available_categories(self) -> List[str]:
        """F-31 minimal: Liefert die verfuegbaren Benchmark-Kategorien.

        Basiert auf den hinterlegten DEFAULT_BENCHMARKS-Kategorien.
        """
        return sorted(DEFAULT_BENCHMARKS.keys())

    async def compare_contract_to_benchmark(
        self,
        contract_id: UUID,
        company_id: UUID,
    ) -> Optional[BenchmarkResult]:
        """
        Compare a contract to market benchmarks.

        Args:
            contract_id: Contract ID
            company_id: Company ID for access control

        Returns:
            BenchmarkResult with comparison metrics and recommendations
        """
        # Get contract
        contract = await self._get_contract(contract_id, company_id)
        if not contract:
            return None

        # Determine category
        category = self._get_category_for_contract(contract)

        # Get benchmark data
        benchmarks = await self._get_benchmarks_for_category(category)

        # Compare metrics
        metrics = self._compare_metrics(contract, benchmarks, category)

        # Calculate overall score
        overall_score, overall_rating = self._calculate_overall_score(metrics)

        # Generate recommendations
        recommendations = self._generate_recommendations(contract, metrics, category)

        # Calculate potential savings
        potential_savings = self._calculate_potential_savings(contract, metrics)

        # Generate summary
        summary = self._generate_summary(contract, overall_rating, metrics, category)

        result = BenchmarkResult(
            contract_id=contract_id,
            category=category,
            metrics=metrics,
            overall_rating=overall_rating,
            overall_score=overall_score,
            summary=summary,
            recommendations=recommendations,
            potential_savings=potential_savings,
            currency=contract.currency or "EUR",
        )

        logger.info(
            "contract_benchmark_completed",
            contract_id=str(contract_id),
            category=category,
            overall_rating=overall_rating,
            overall_score=round(overall_score, 1),
            metrics_count=len(metrics),
        )

        return result

    async def get_negotiation_suggestions(
        self,
        contract_id: UUID,
        company_id: UUID,
    ) -> List[NegotiationSuggestion]:
        """
        Get negotiation suggestions for a contract.

        Args:
            contract_id: Contract ID
            company_id: Company ID for access control

        Returns:
            List of prioritized negotiation suggestions
        """
        contract = await self._get_contract(contract_id, company_id)
        if not contract:
            return []

        suggestions: List[NegotiationSuggestion] = []
        category = self._get_category_for_contract(contract)

        # Price-based suggestions
        suggestions.extend(self._get_price_suggestions(contract, category))

        # Term-based suggestions
        suggestions.extend(self._get_term_suggestions(contract, category))

        # Clause-based suggestions
        suggestions.extend(self._get_clause_suggestions(contract))

        # Sort by priority
        suggestions.sort(key=lambda x: x.priority, reverse=True)

        return suggestions

    async def get_benchmark_data(
        self,
        category: str,
        metric: Optional[str] = None,
        region: str = "DACH",
    ) -> List[ContractBenchmark]:
        """
        Get benchmark data for a category.

        Args:
            category: Benchmark category
            metric: Optional specific metric
            region: Region filter

        Returns:
            List of benchmark entries
        """
        today = date.today()
        query = select(ContractBenchmark).where(
            and_(
                ContractBenchmark.category == category,
                ContractBenchmark.region == region,
                ContractBenchmark.valid_from <= today,
                (ContractBenchmark.valid_until.is_(None) | (ContractBenchmark.valid_until >= today)),
            )
        )

        if metric:
            query = query.where(ContractBenchmark.metric == metric)

        query = query.order_by(ContractBenchmark.valid_from.desc())

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def update_benchmark_from_contracts(
        self,
        category: str,
        company_id: Optional[UUID] = None,
    ) -> Dict[str, Any]:
        """
        Update benchmark data based on actual contracts.

        This is used to build internal benchmarks from company contracts.
        Only uses anonymized, aggregated data.

        Args:
            category: Category to update
            company_id: Optional - only use contracts from specific company

        Returns:
            Statistics about the update
        """
        # Get contracts for category
        contract_types = [
            ct for ct, cat in CONTRACT_TYPE_CATEGORIES.items()
            if cat == category
        ]

        if not contract_types:
            return {"error": f"Unbekannte Kategorie: {category}"}

        query = select(Contract).where(
            and_(
                Contract.contract_type.in_(contract_types),
                Contract.status.in_([ContractStatus.ACTIVE.value, ContractStatus.RENEWED.value]),
                Contract.total_value.isnot(None),
            )
        )

        if company_id:
            query = query.where(Contract.company_id == company_id)

        result = await self.db.execute(query)
        contracts = result.scalars().all()

        if len(contracts) < 5:
            return {
                "category": category,
                "sample_size": len(contracts),
                "error": "Zu wenige Verträge für Benchmark (min. 5)",
            }

        # Calculate statistics
        values = [float(c.total_value) for c in contracts if c.total_value]
        terms = [
            (c.expiration_date - c.effective_date).days / 30
            for c in contracts
            if c.effective_date and c.expiration_date
        ]
        notice_days = [c.notice_period_days for c in contracts if c.notice_period_days]

        stats = {
            "category": category,
            "sample_size": len(contracts),
            "metrics_calculated": [],
        }

        # Store/update benchmarks
        today = date.today()

        if values:
            await self._upsert_benchmark(
                category=category,
                metric="avg_total_value",
                values=values,
                valid_from=today,
            )
            stats["metrics_calculated"].append("avg_total_value")

        if terms:
            await self._upsert_benchmark(
                category=category,
                metric="avg_term_months",
                values=terms,
                valid_from=today,
            )
            stats["metrics_calculated"].append("avg_term_months")

        if notice_days:
            await self._upsert_benchmark(
                category=category,
                metric="avg_notice_days",
                values=[float(d) for d in notice_days],
                valid_from=today,
            )
            stats["metrics_calculated"].append("avg_notice_days")

        await self.db.commit()

        logger.info(
            "benchmark_updated_from_contracts",
            category=category,
            sample_size=len(contracts),
            metrics=stats["metrics_calculated"],
        )

        return stats

    # =========================================================================
    # Internal Methods
    # =========================================================================

    async def _get_contract(
        self,
        contract_id: UUID,
        company_id: UUID,
    ) -> Optional[Contract]:
        """Get contract with access control."""
        result = await self.db.execute(
            select(Contract).where(
                and_(
                    Contract.id == contract_id,
                    Contract.company_id == company_id,
                )
            )
        )
        return result.scalar_one_or_none()

    def _get_category_for_contract(self, contract: Contract) -> str:
        """Determine benchmark category for a contract."""
        contract_type = contract.contract_type
        return CONTRACT_TYPE_CATEGORIES.get(contract_type, "service")

    async def _get_benchmarks_for_category(
        self,
        category: str,
    ) -> Dict[str, Dict[str, float]]:
        """Get benchmark data for a category."""
        # Try to get from database first
        db_benchmarks = await self.get_benchmark_data(category)

        if db_benchmarks:
            result: Dict[str, Dict[str, float]] = {}
            for bm in db_benchmarks:
                result[bm.metric] = {
                    "value": float(bm.value) if bm.value else 0,
                    "min": float(bm.min_value) if bm.min_value else 0,
                    "max": float(bm.max_value) if bm.max_value else 0,
                    "p25": float(bm.percentile_25) if bm.percentile_25 else 0,
                    "p50": float(bm.percentile_50) if bm.percentile_50 else 0,
                    "p75": float(bm.percentile_75) if bm.percentile_75 else 0,
                }
            return result

        # Fall back to defaults
        return DEFAULT_BENCHMARKS.get(category, DEFAULT_BENCHMARKS["service"])

    def _compare_metrics(
        self,
        contract: Contract,
        benchmarks: Dict[str, Dict[str, float]],
        category: str,
    ) -> List[BenchmarkMetric]:
        """Compare contract metrics to benchmarks."""
        metrics: List[BenchmarkMetric] = []

        # Compare term length
        if contract.effective_date and contract.expiration_date:
            term_months = (contract.expiration_date - contract.effective_date).days / 30
            term_bm = benchmarks.get("avg_term_months", {})
            if term_bm:
                metric = self._create_metric(
                    metric_name="term_months",
                    display_name="Vertragslaufzeit (Monate)",
                    contract_value=term_months,
                    benchmark=term_bm,
                )
                if term_months > term_bm.get("value", 0) * 1.5:
                    metric.recommendation = "Vertragslaufzeit ist länger als ueblich"
                metrics.append(metric)

        # Compare notice period
        if contract.notice_period_days:
            notice_bm = benchmarks.get("avg_notice_days", {})
            if notice_bm:
                metric = self._create_metric(
                    metric_name="notice_days",
                    display_name="Kündigungsfrist (Tage)",
                    contract_value=float(contract.notice_period_days),
                    benchmark=notice_bm,
                )
                if contract.notice_period_days < notice_bm.get("value", 30):
                    metric.recommendation = "Kündigungsfrist ist kürzer als ueblich (positiv)"
                elif contract.notice_period_days > notice_bm.get("value", 30) * 2:
                    metric.recommendation = "Kündigungsfrist ist deutlich länger als ueblich"
                metrics.append(metric)

        # Compare total value if available
        if contract.total_value:
            value_bm = benchmarks.get("avg_total_value", benchmarks.get("avg_monthly_cost", {}))
            if value_bm:
                metric = self._create_metric(
                    metric_name="total_value",
                    display_name="Vertragswert",
                    contract_value=float(contract.total_value),
                    benchmark=value_bm,
                )
                metrics.append(metric)

        return metrics

    def _create_metric(
        self,
        metric_name: str,
        display_name: str,
        contract_value: Optional[float],
        benchmark: Dict[str, float],
    ) -> BenchmarkMetric:
        """Create a benchmark metric with comparison."""
        bm_value = benchmark.get("value", 0)
        bm_min = benchmark.get("min", 0)
        bm_max = benchmark.get("max", 0)

        # Calculate percentile and comparison
        comparison = "average"
        percentile = 50
        variance_percent = None

        if contract_value is not None and bm_value > 0:
            variance_percent = ((contract_value - bm_value) / bm_value) * 100

            if variance_percent < -20:
                comparison = "below_average"
                percentile = 25
            elif variance_percent > 20:
                comparison = "above_average"
                percentile = 75
            else:
                percentile = 50

            # More precise percentile if min/max available
            if bm_min < bm_max:
                percentile = int(((contract_value - bm_min) / (bm_max - bm_min)) * 100)
                percentile = max(0, min(100, percentile))

        return BenchmarkMetric(
            metric_name=metric_name,
            metric_display_name=display_name,
            contract_value=contract_value,
            benchmark_value=bm_value,
            min_value=bm_min if bm_min else None,
            max_value=bm_max if bm_max else None,
            percentile=percentile,
            comparison=comparison,
            variance_percent=round(variance_percent, 1) if variance_percent else None,
        )

    def _calculate_overall_score(
        self,
        metrics: List[BenchmarkMetric],
    ) -> tuple[float, str]:
        """Calculate overall benchmark score."""
        if not metrics:
            return 50.0, "average"

        # Score based on percentiles (lower is better for cost, higher for favorable terms)
        scores = []
        for metric in metrics:
            if metric.percentile is not None:
                # For cost metrics, lower percentile is better
                if "cost" in metric.metric_name or "value" in metric.metric_name:
                    scores.append(100 - metric.percentile)
                else:
                    scores.append(metric.percentile)

        if not scores:
            return 50.0, "average"

        avg_score = sum(scores) / len(scores)

        if avg_score >= 70:
            rating = "good"
        elif avg_score >= 40:
            rating = "average"
        else:
            rating = "needs_attention"

        return avg_score, rating

    def _generate_recommendations(
        self,
        contract: Contract,
        metrics: List[BenchmarkMetric],
        category: str,
    ) -> List[str]:
        """Generate recommendations based on benchmark comparison."""
        recommendations: List[str] = []

        for metric in metrics:
            if metric.recommendation:
                recommendations.append(metric.recommendation)

            if metric.comparison == "above_average":
                if "cost" in metric.metric_name or "value" in metric.metric_name:
                    recommendations.append(
                        f"{metric.metric_display_name} liegt über dem Durchschnitt. "
                        f"Neuverhandlung empfohlen."
                    )
                elif "term" in metric.metric_name:
                    recommendations.append(
                        f"{metric.metric_display_name} ist länger als ueblich. "
                        f"Kürzere Laufzeit bei Verlängerung verhandeln."
                    )

        # Auto-renewal warning
        if contract.auto_renewal:
            if contract.renewal_notice_days and contract.renewal_notice_days > 60:
                recommendations.append(
                    "Automatische Verlängerung mit langer Kündigungsfrist - "
                    "Erinnerung frühzeitig setzen."
                )

        # Price adjustment warning
        if contract.clauses and contract.clauses.get("price_adjustment"):
            recommendations.append(
                "Preisanpassungsklausel vorhanden - Obergrenze verhandeln."
            )

        return recommendations

    def _calculate_potential_savings(
        self,
        contract: Contract,
        metrics: List[BenchmarkMetric],
    ) -> Optional[Decimal]:
        """Calculate potential savings based on benchmark."""
        if not contract.total_value:
            return None

        # Find value metric
        value_metric = next(
            (m for m in metrics if "value" in m.metric_name or "cost" in m.metric_name),
            None
        )

        if not value_metric or not value_metric.variance_percent:
            return None

        if value_metric.variance_percent > 0:
            # Contract is above average - potential savings
            savings_percent = min(value_metric.variance_percent, 20) / 100
            return Decimal(str(float(contract.total_value) * savings_percent))

        return None

    def _generate_summary(
        self,
        contract: Contract,
        rating: str,
        metrics: List[BenchmarkMetric],
        category: str,
    ) -> str:
        """Generate a summary of the benchmark comparison."""
        rating_text = {
            "good": "gut",
            "average": "durchschnittlich",
            "needs_attention": "verbesserungswuerdig",
        }

        summary = f"Der Vertrag schneidet im Marktvergleich {rating_text.get(rating, 'durchschnittlich')} ab. "

        above_avg = [m for m in metrics if m.comparison == "above_average"]
        below_avg = [m for m in metrics if m.comparison == "below_average"]

        if above_avg:
            names = [m.metric_display_name for m in above_avg[:2]]
            summary += f"Über dem Durchschnitt: {', '.join(names)}. "

        if below_avg:
            names = [m.metric_display_name for m in below_avg[:2]]
            summary += f"Unter dem Durchschnitt: {', '.join(names)}. "

        return summary.strip()

    def _get_price_suggestions(
        self,
        contract: Contract,
        category: str,
    ) -> List[NegotiationSuggestion]:
        """Get price-related negotiation suggestions."""
        suggestions: List[NegotiationSuggestion] = []

        # Volume discount
        if contract.total_value and float(contract.total_value) > 10000:
            suggestions.append(NegotiationSuggestion(
                category="price",
                title="Volumenrabatt",
                description=(
                    "Bei diesem Vertragsvolumen ist ein Mengenrabatt von 5-15% "
                    "branchenueblich. Verhandeln Sie einen Nachlass."
                ),
                potential_impact="medium",
                potential_savings=Decimal(str(float(contract.total_value) * 0.1)),
                priority=3,
            ))

        # Payment terms
        payment_terms = contract.payment_terms or {}
        if not payment_terms.get("skonto_percent"):
            suggestions.append(NegotiationSuggestion(
                category="payment",
                title="Skonto verhandeln",
                description=(
                    "Verhandeln Sie Skonto-Konditionen (z.B. 2% bei Zahlung "
                    "innerhalb 14 Tagen)."
                ),
                potential_impact="low",
                priority=1,
            ))

        return suggestions

    def _get_term_suggestions(
        self,
        contract: Contract,
        category: str,
    ) -> List[NegotiationSuggestion]:
        """Get term-related negotiation suggestions."""
        suggestions: List[NegotiationSuggestion] = []

        # Long term
        if contract.effective_date and contract.expiration_date:
            term_months = (contract.expiration_date - contract.effective_date).days / 30
            if term_months > 24:
                suggestions.append(NegotiationSuggestion(
                    category="term",
                    title="Kürzere Laufzeit",
                    description=(
                        f"Die Laufzeit von {int(term_months)} Monaten ist lang. "
                        f"Bei Verlängerung kürzere Laufzeit oder Sonderkündigungsrecht verhandeln."
                    ),
                    potential_impact="medium",
                    priority=2,
                ))

        # Auto-renewal
        if contract.auto_renewal:
            suggestions.append(NegotiationSuggestion(
                category="term",
                title="Automatische Verlängerung überprüfen",
                description=(
                    "Automatische Verlängerung ist aktiv. Prüfen Sie, ob diese "
                    "gewünscht ist oder ob eine explizite Verlängerung besser waere."
                ),
                potential_impact="medium",
                priority=2,
            ))

        # Notice period
        if contract.notice_period_days and contract.notice_period_days > 90:
            suggestions.append(NegotiationSuggestion(
                category="term",
                title="Kündigungsfrist verkürzen",
                description=(
                    f"Die Kündigungsfrist von {contract.notice_period_days} Tagen ist lang. "
                    f"Verhandeln Sie eine Verkürzung auf 30-60 Tage."
                ),
                potential_impact="high",
                priority=3,
            ))

        return suggestions

    def _get_clause_suggestions(
        self,
        contract: Contract,
    ) -> List[NegotiationSuggestion]:
        """Get clause-related negotiation suggestions."""
        suggestions: List[NegotiationSuggestion] = []

        clauses = contract.clauses or {}

        # Price adjustment clause
        if clauses.get("price_adjustment"):
            suggestions.append(NegotiationSuggestion(
                category="clause",
                title="Preisanpassung begrenzen",
                description=(
                    "Verhandeln Sie eine Obergrenze für Preisanpassungen "
                    "(z.B. max. 5% pro Jahr oder Kopplung an VPI)."
                ),
                potential_impact="high",
                priority=4,
            ))

        # Liability
        if not clauses.get("liability"):
            suggestions.append(NegotiationSuggestion(
                category="clause",
                title="Haftungsbegrenzung vereinbaren",
                description=(
                    "Es fehlt eine explizite Haftungsbegrenzung. "
                    "Fuegen Sie eine angemessene Haftungsobergrenze hinzu."
                ),
                potential_impact="high",
                priority=3,
            ))

        return suggestions

    async def _upsert_benchmark(
        self,
        category: str,
        metric: str,
        values: List[float],
        valid_from: date,
        region: str = "DACH",
    ) -> None:
        """Insert or update a benchmark entry."""
        import statistics

        # Calculate statistics
        avg_value = statistics.mean(values)
        min_value = min(values)
        max_value = max(values)

        p25 = statistics.quantiles(values, n=4)[0] if len(values) >= 4 else min_value
        p50 = statistics.median(values)
        p75 = statistics.quantiles(values, n=4)[2] if len(values) >= 4 else max_value
        std_dev = statistics.stdev(values) if len(values) > 1 else 0

        # Check for existing
        result = await self.db.execute(
            select(ContractBenchmark).where(
                and_(
                    ContractBenchmark.category == category,
                    ContractBenchmark.metric == metric,
                    ContractBenchmark.region == region,
                    ContractBenchmark.valid_from == valid_from,
                )
            )
        )
        existing = result.scalar_one_or_none()

        if existing:
            existing.value = Decimal(str(avg_value))
            existing.min_value = Decimal(str(min_value))
            existing.max_value = Decimal(str(max_value))
            existing.percentile_25 = Decimal(str(p25))
            existing.percentile_50 = Decimal(str(p50))
            existing.percentile_75 = Decimal(str(p75))
            existing.std_deviation = Decimal(str(std_dev))
            existing.sample_size = len(values)
            existing.source = "internal"
        else:
            benchmark = ContractBenchmark(
                category=category,
                metric=metric,
                value=Decimal(str(avg_value)),
                min_value=Decimal(str(min_value)),
                max_value=Decimal(str(max_value)),
                percentile_25=Decimal(str(p25)),
                percentile_50=Decimal(str(p50)),
                percentile_75=Decimal(str(p75)),
                std_deviation=Decimal(str(std_dev)),
                sample_size=len(values),
                region=region,
                valid_from=valid_from,
                source="internal",
            )
            self.db.add(benchmark)


# =============================================================================
# Factory Function
# =============================================================================


def get_contract_benchmark_service(db: AsyncSession) -> ContractBenchmarkService:
    """Factory function to create ContractBenchmarkService instance."""
    return ContractBenchmarkService(db)
