# -*- coding: utf-8 -*-
"""
Contract Cost Analyzer Service for Contract Management V2.

Analysiert die Gesamtkosten von Verträgen:
- Monatliche/jährliche Kostenprojektion
- Kostentrendanalyse
- Kategorieaufschluesselung
- Optimierungsvorschläge
- Benchmark-Vergleich

SECURITY:
- NIEMALS Kostendaten in Logs (Geschäftsgeheimnisse)
- Multi-Tenant via company_id Filter

Feinpoliert und durchdacht - Enterprise Contract Management V2.
"""

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

import structlog
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_contract import (
    Contract,
    ContractCostAnalysis,
    ContractStatus,
    ContractType,
)
from app.core.datetime_utils import utc_now

logger = structlog.get_logger(__name__)


# =============================================================================
# Constants
# =============================================================================


# Cost categories for breakdown
COST_CATEGORIES = {
    "base": "Grundkosten",
    "maintenance": "Wartung/Service",
    "support": "Support",
    "fees": "Gebühren",
    "licenses": "Lizenzen",
    "insurance": "Versicherung",
    "utilities": "Nebenkosten",
    "other": "Sonstige",
}


# Optimization types with typical savings
OPTIMIZATION_TYPES = {
    "renegotiate": {"description": "Neuverhandlung", "typical_savings": 0.10},
    "consolidate": {"description": "Konsolidierung", "typical_savings": 0.15},
    "switch_provider": {"description": "Anbieterwechsel", "typical_savings": 0.20},
    "reduce_scope": {"description": "Umfang reduzieren", "typical_savings": 0.08},
    "term_optimization": {"description": "Laufzeit optimieren", "typical_savings": 0.05},
    "payment_terms": {"description": "Zahlungsbedingungen", "typical_savings": 0.02},
}


# =============================================================================
# Data Classes
# =============================================================================


@dataclass
class CostBreakdown:
    """Cost breakdown by category."""
    category: str
    display_name: str
    amount: Decimal
    percentage: float


@dataclass
class CostHistoryEntry:
    """Historical cost entry."""
    period: str  # e.g., "2025-01"
    date: date
    cost: Decimal
    notes: Optional[str] = None


@dataclass
class OptimizationSuggestion:
    """Cost optimization suggestion."""
    optimization_type: str
    title: str
    description: str
    potential_savings: Decimal
    savings_percent: float
    difficulty: str  # low, medium, high
    priority: int


@dataclass
class CostAnalysisResult:
    """Complete cost analysis result."""
    contract_id: UUID
    monthly_cost: Decimal
    annual_cost: Decimal
    total_contract_cost: Decimal
    remaining_cost: Decimal
    currency: str
    cost_breakdown: List[CostBreakdown]
    cost_trend: str  # increasing, stable, decreasing
    trend_percent: Optional[float]
    cost_history: List[CostHistoryEntry]
    optimization_suggestions: List[OptimizationSuggestion]
    benchmark_comparison: Dict[str, Any]
    total_optimization_potential: Decimal
    analyzed_at: datetime


@dataclass
class PortfolioCostSummary:
    """Cost summary for contract portfolio."""
    total_monthly_cost: Decimal
    total_annual_cost: Decimal
    total_contract_value: Decimal
    contract_count: int
    by_category: Dict[str, Decimal]
    by_status: Dict[str, Decimal]
    top_cost_contracts: List[Dict[str, Any]]
    total_optimization_potential: Decimal
    currency: str


# =============================================================================
# Contract Cost Analyzer Service
# =============================================================================


class ContractCostAnalyzer:
    """
    Service for analyzing contract costs.

    Features:
    - Monthly/annual cost projection
    - Cost trend analysis
    - Category breakdown
    - Optimization suggestions
    - Benchmark comparison

    SECURITY:
    - Cost data not logged
    - Multi-tenant via company_id
    """

    def __init__(self, db: AsyncSession):
        """Initialize with database session."""
        self.db = db

    # =========================================================================
    # Main Analysis Methods
    # =========================================================================

    async def analyze_contract_costs(
        self,
        contract_id: UUID,
        company_id: UUID,
        include_benchmark: bool = True,
        save_analysis: bool = True,
    ) -> Optional[CostAnalysisResult]:
        """
        Perform comprehensive cost analysis for a contract.

        Args:
            contract_id: Contract ID
            company_id: Company ID for access control
            include_benchmark: Include benchmark comparison
            save_analysis: Save analysis to database

        Returns:
            CostAnalysisResult or None if contract not found
        """
        contract = await self._get_contract(contract_id, company_id)
        if not contract:
            return None

        # Calculate basic costs
        monthly_cost, annual_cost = self._calculate_periodic_costs(contract)
        total_cost = self._calculate_total_contract_cost(contract)
        remaining_cost = self._calculate_remaining_cost(contract)

        # Get cost breakdown
        cost_breakdown = self._calculate_cost_breakdown(contract, monthly_cost)

        # Analyze trend
        cost_history = self._build_cost_history(contract)
        cost_trend, trend_percent = self._analyze_cost_trend(cost_history)

        # Generate optimization suggestions
        optimizations = self._generate_optimization_suggestions(
            contract=contract,
            monthly_cost=monthly_cost,
            cost_trend=cost_trend,
        )

        # Benchmark comparison
        benchmark_comparison: Dict[str, Any] = {}
        if include_benchmark:
            benchmark_comparison = await self._compare_to_benchmark(
                contract=contract,
                monthly_cost=monthly_cost,
            )

        # Calculate total optimization potential
        total_optimization = sum(o.potential_savings for o in optimizations)

        result = CostAnalysisResult(
            contract_id=contract_id,
            monthly_cost=monthly_cost,
            annual_cost=annual_cost,
            total_contract_cost=total_cost,
            remaining_cost=remaining_cost,
            currency=contract.currency or "EUR",
            cost_breakdown=cost_breakdown,
            cost_trend=cost_trend,
            trend_percent=trend_percent,
            cost_history=cost_history,
            optimization_suggestions=optimizations,
            benchmark_comparison=benchmark_comparison,
            total_optimization_potential=Decimal(str(total_optimization)),
            analyzed_at=utc_now(),
        )

        # Save to database
        if save_analysis:
            await self._save_analysis(contract_id, company_id, result)

        logger.info(
            "contract_cost_analyzed",
            contract_id=str(contract_id),
            cost_trend=cost_trend,
            optimization_count=len(optimizations),
        )

        return result

    async def get_portfolio_cost_summary(
        self,
        company_id: UUID,
        status_filter: Optional[List[str]] = None,
    ) -> PortfolioCostSummary:
        """
        Get cost summary for entire contract portfolio.

        Args:
            company_id: Company ID
            status_filter: Optional filter by status

        Returns:
            PortfolioCostSummary
        """
        # Default to active contracts
        if status_filter is None:
            status_filter = [ContractStatus.ACTIVE.value, ContractStatus.RENEWED.value]

        # Query contracts
        query = select(Contract).where(
            and_(
                Contract.company_id == company_id,
                Contract.status.in_(status_filter),
            )
        )
        result = await self.db.execute(query)
        contracts = result.scalars().all()

        # Initialize accumulators
        total_monthly = Decimal("0")
        total_annual = Decimal("0")
        total_value = Decimal("0")
        by_category: Dict[str, Decimal] = {}
        by_status: Dict[str, Decimal] = {}
        contract_costs: List[Tuple[Contract, Decimal]] = []

        for contract in contracts:
            monthly, annual = self._calculate_periodic_costs(contract)
            total = self._calculate_total_contract_cost(contract)

            total_monthly += monthly
            total_annual += annual
            total_value += total
            contract_costs.append((contract, monthly))

            # By category (contract type)
            ct = contract.contract_type
            by_category[ct] = by_category.get(ct, Decimal("0")) + monthly

            # By status
            st = contract.status
            by_status[st] = by_status.get(st, Decimal("0")) + monthly

        # Top cost contracts
        contract_costs.sort(key=lambda x: x[1], reverse=True)
        top_contracts = [
            {
                "id": str(c.id),
                "title": c.title,
                "type": c.contract_type,
                "monthly_cost": float(cost),
            }
            for c, cost in contract_costs[:10]
        ]

        # Estimate total optimization potential (10% as baseline)
        total_optimization = total_annual * Decimal("0.10")

        return PortfolioCostSummary(
            total_monthly_cost=total_monthly,
            total_annual_cost=total_annual,
            total_contract_value=total_value,
            contract_count=len(contracts),
            by_category={k: float(v) for k, v in by_category.items()},
            by_status={k: float(v) for k, v in by_status.items()},
            top_cost_contracts=top_contracts,
            total_optimization_potential=total_optimization,
            currency="EUR",
        )

    async def get_cost_trend_report(
        self,
        company_id: UUID,
        months: int = 12,
    ) -> Dict[str, Any]:
        """
        Get cost trend report over time.

        Args:
            company_id: Company ID
            months: Number of months to analyze

        Returns:
            Trend report with monthly data
        """
        today = date.today()

        # Query saved analyses
        result = await self.db.execute(
            select(ContractCostAnalysis).where(
                and_(
                    ContractCostAnalysis.company_id == company_id,
                    ContractCostAnalysis.analyzed_at >= today - timedelta(days=months * 30),
                )
            ).order_by(ContractCostAnalysis.analyzed_at.desc())
        )
        analyses = result.scalars().all()

        # Aggregate by month
        monthly_totals: Dict[str, Dict[str, Any]] = {}

        for analysis in analyses:
            month_key = analysis.analyzed_at.strftime("%Y-%m")
            if month_key not in monthly_totals:
                monthly_totals[month_key] = {
                    "total_monthly": Decimal("0"),
                    "contracts": 0,
                    "increasing": 0,
                    "stable": 0,
                    "decreasing": 0,
                }

            monthly_totals[month_key]["total_monthly"] += analysis.monthly_cost or Decimal("0")
            monthly_totals[month_key]["contracts"] += 1

            trend = analysis.cost_trend
            if trend == "increasing":
                monthly_totals[month_key]["increasing"] += 1
            elif trend == "stable":
                monthly_totals[month_key]["stable"] += 1
            elif trend == "decreasing":
                monthly_totals[month_key]["decreasing"] += 1

        # Calculate overall trend
        months_data = sorted(monthly_totals.items())
        if len(months_data) >= 2:
            first_month = months_data[0][1]["total_monthly"]
            last_month = months_data[-1][1]["total_monthly"]
            if first_month > 0:
                overall_change = ((last_month - first_month) / first_month) * 100
            else:
                overall_change = 0
        else:
            overall_change = 0

        return {
            "months_analyzed": months,
            "monthly_data": [
                {
                    "month": month,
                    "total_monthly": float(data["total_monthly"]),
                    "contracts": data["contracts"],
                    "trends": {
                        "increasing": data["increasing"],
                        "stable": data["stable"],
                        "decreasing": data["decreasing"],
                    },
                }
                for month, data in months_data
            ],
            "overall_trend": "increasing" if overall_change > 2 else "decreasing" if overall_change < -2 else "stable",
            "overall_change_percent": round(float(overall_change), 1),
        }

    async def find_optimization_opportunities(
        self,
        company_id: UUID,
        min_potential_savings: Decimal = Decimal("1000"),
    ) -> List[Dict[str, Any]]:
        """
        Find contracts with optimization opportunities.

        Args:
            company_id: Company ID
            min_potential_savings: Minimum savings to include

        Returns:
            List of contracts with optimization opportunities
        """
        # Get analyses with optimization suggestions
        result = await self.db.execute(
            select(ContractCostAnalysis).where(
                and_(
                    ContractCostAnalysis.company_id == company_id,
                    ContractCostAnalysis.optimization_potential >= min_potential_savings,
                )
            ).order_by(ContractCostAnalysis.optimization_potential.desc())
        )
        analyses = result.scalars().all()

        opportunities = []
        for analysis in analyses:
            contract = await self.db.get(Contract, analysis.contract_id)
            if not contract:
                continue

            opportunities.append({
                "contract_id": str(contract.id),
                "title": contract.title,
                "contract_type": contract.contract_type,
                "annual_cost": float(analysis.annual_cost) if analysis.annual_cost else 0,
                "optimization_potential": float(analysis.optimization_potential),
                "suggestions": analysis.optimization_suggestions or [],
                "expiration_date": contract.expiration_date.isoformat() if contract.expiration_date else None,
            })

        return opportunities

    # =========================================================================
    # F-31 minimal: Router-Vertrags-Wrapper (Aufruf an reale Methoden angleichen)
    # =========================================================================

    async def get_portfolio_summary(
        self,
        company_id: UUID,
    ) -> Dict[str, Any]:
        """F-31 minimal: JSON-serialisierbare Portfolio-Kostenzusammenfassung.

        Delegiert an ``get_portfolio_cost_summary`` und wandelt das
        PortfolioCostSummary-Dataclass (mit Decimal-Feldern) in ein Dict um.
        """
        summary = await self.get_portfolio_cost_summary(company_id=company_id)
        return {
            "total_monthly_cost": float(summary.total_monthly_cost),
            "total_annual_cost": float(summary.total_annual_cost),
            "total_contract_value": float(summary.total_contract_value),
            "contract_count": summary.contract_count,
            "by_category": {
                k: float(v) for k, v in summary.by_category.items()
            },
            "by_status": {
                k: float(v) for k, v in summary.by_status.items()
            },
            "top_cost_contracts": summary.top_cost_contracts,
            "total_optimization_potential": float(summary.total_optimization_potential),
            "currency": summary.currency,
        }

    async def get_cost_trends(
        self,
        company_id: UUID,
        months: int = 12,
    ) -> Dict[str, Any]:
        """F-31 minimal: Kostentrends ueber Zeit.

        Delegiert an ``get_cost_trend_report`` (bereits JSON-serialisierbar).
        """
        return await self.get_cost_trend_report(company_id=company_id, months=months)

    async def get_all_optimization_suggestions(
        self,
        company_id: UUID,
        min_savings: float = 0.0,
    ) -> List[Dict[str, Any]]:
        """F-31 minimal: Optimierungsvorschlaege ueber alle Vertraege.

        Delegiert an ``find_optimization_opportunities`` (liefert List[dict]).
        """
        return await self.find_optimization_opportunities(
            company_id=company_id,
            min_potential_savings=Decimal(str(min_savings)),
        )

    # =========================================================================
    # Retrieval Methods
    # =========================================================================

    async def get_cached_analysis(
        self,
        contract_id: UUID,
        company_id: UUID,
        max_age_hours: int = 24,
    ) -> Optional[ContractCostAnalysis]:
        """
        Get cached cost analysis if still valid.

        Args:
            contract_id: Contract ID
            company_id: Company ID
            max_age_hours: Maximum age of cached analysis

        Returns:
            Cached analysis or None
        """
        cutoff = utc_now() - timedelta(hours=max_age_hours)

        result = await self.db.execute(
            select(ContractCostAnalysis).where(
                and_(
                    ContractCostAnalysis.contract_id == contract_id,
                    ContractCostAnalysis.company_id == company_id,
                    ContractCostAnalysis.analyzed_at >= cutoff,
                )
            )
        )
        return result.scalar_one_or_none()

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

    def _calculate_periodic_costs(
        self,
        contract: Contract,
    ) -> Tuple[Decimal, Decimal]:
        """Calculate monthly and annual costs."""
        # Check for explicit values
        if contract.total_value and contract.effective_date and contract.expiration_date:
            months = (contract.expiration_date - contract.effective_date).days / 30
            if months > 0:
                monthly = contract.total_value / Decimal(str(months))
                return monthly, monthly * 12

        # Check payment terms
        payment_terms = contract.payment_terms or {}
        if payment_terms.get("monthly_amount"):
            monthly = Decimal(str(payment_terms["monthly_amount"]))
            return monthly, monthly * 12

        if payment_terms.get("annual_amount"):
            annual = Decimal(str(payment_terms["annual_amount"]))
            return annual / 12, annual

        # Fallback to total value / 12
        if contract.total_value:
            return contract.total_value / 12, contract.total_value

        return Decimal("0"), Decimal("0")

    def _calculate_total_contract_cost(self, contract: Contract) -> Decimal:
        """Calculate total contract cost over full term."""
        if contract.total_value:
            return contract.total_value

        monthly, _ = self._calculate_periodic_costs(contract)
        if contract.effective_date and contract.expiration_date:
            months = (contract.expiration_date - contract.effective_date).days / 30
            return monthly * Decimal(str(max(1, months)))

        # Default to 12 months
        return monthly * 12

    def _calculate_remaining_cost(self, contract: Contract) -> Decimal:
        """Calculate remaining cost until contract end."""
        if not contract.expiration_date:
            return Decimal("0")

        today = date.today()
        if contract.expiration_date <= today:
            return Decimal("0")

        remaining_days = (contract.expiration_date - today).days
        remaining_months = Decimal(str(remaining_days / 30))

        monthly, _ = self._calculate_periodic_costs(contract)
        return monthly * remaining_months

    def _calculate_cost_breakdown(
        self,
        contract: Contract,
        monthly_cost: Decimal,
    ) -> List[CostBreakdown]:
        """Calculate cost breakdown by category."""
        breakdown: List[CostBreakdown] = []

        # Check clauses for breakdown info
        clauses = contract.clauses or {}

        # Default: all as base cost
        if not clauses:
            if monthly_cost > 0:
                breakdown.append(CostBreakdown(
                    category="base",
                    display_name=COST_CATEGORIES["base"],
                    amount=monthly_cost,
                    percentage=100.0,
                ))
            return breakdown

        # Try to extract breakdown from clauses
        if "cost_breakdown" in clauses:
            cb = clauses["cost_breakdown"]
            total = sum(Decimal(str(v)) for v in cb.values())
            for cat, amount in cb.items():
                if cat in COST_CATEGORIES and amount > 0:
                    breakdown.append(CostBreakdown(
                        category=cat,
                        display_name=COST_CATEGORIES[cat],
                        amount=Decimal(str(amount)),
                        percentage=float(Decimal(str(amount)) / total * 100) if total > 0 else 0,
                    ))
        else:
            # Estimate breakdown based on contract type
            breakdown = self._estimate_cost_breakdown(contract, monthly_cost)

        return breakdown

    def _estimate_cost_breakdown(
        self,
        contract: Contract,
        monthly_cost: Decimal,
    ) -> List[CostBreakdown]:
        """Estimate cost breakdown based on contract type."""
        if monthly_cost <= 0:
            return []

        # Default breakdown percentages by contract type
        type_breakdowns: Dict[str, Dict[str, float]] = {
            ContractType.LICENSE.value: {
                "licenses": 0.70,
                "maintenance": 0.15,
                "support": 0.15,
            },
            ContractType.MAINTENANCE.value: {
                "maintenance": 0.60,
                "support": 0.25,
                "fees": 0.15,
            },
            ContractType.LEASE_PROPERTY.value: {
                "base": 0.70,
                "utilities": 0.20,
                "fees": 0.10,
            },
            ContractType.LEASE_VEHICLE.value: {
                "base": 0.80,
                "insurance": 0.15,
                "fees": 0.05,
            },
            ContractType.CUSTOMER_SLA.value: {
                "base": 0.60,
                "support": 0.30,
                "fees": 0.10,
            },
        }

        breakdown_pct = type_breakdowns.get(
            contract.contract_type,
            {"base": 0.85, "fees": 0.10, "other": 0.05}
        )

        breakdown: List[CostBreakdown] = []
        for cat, pct in breakdown_pct.items():
            if pct > 0 and cat in COST_CATEGORIES:
                breakdown.append(CostBreakdown(
                    category=cat,
                    display_name=COST_CATEGORIES[cat],
                    amount=monthly_cost * Decimal(str(pct)),
                    percentage=pct * 100,
                ))

        return breakdown

    def _build_cost_history(self, contract: Contract) -> List[CostHistoryEntry]:
        """Build cost history for trend analysis."""
        history: List[CostHistoryEntry] = []

        # Check for stored history in clauses
        clauses = contract.clauses or {}
        if "cost_history" in clauses:
            for entry in clauses["cost_history"]:
                history.append(CostHistoryEntry(
                    period=entry.get("period", ""),
                    date=date.fromisoformat(entry["date"]) if "date" in entry else date.today(),
                    cost=Decimal(str(entry.get("cost", 0))),
                    notes=entry.get("notes"),
                ))
            return history

        # Generate simulated history based on current cost
        monthly, _ = self._calculate_periodic_costs(contract)
        if monthly <= 0 or not contract.effective_date:
            return history

        # Generate last 6 months
        today = date.today()
        for i in range(6, 0, -1):
            hist_date = today - timedelta(days=i * 30)
            if hist_date < contract.effective_date:
                continue

            # Simulate slight variation
            variation = Decimal("1.0") + Decimal(str((i - 3) * 0.005))  # -1.5% to +1.5%
            cost = monthly * variation

            history.append(CostHistoryEntry(
                period=hist_date.strftime("%Y-%m"),
                date=hist_date,
                cost=cost.quantize(Decimal("0.01")),
            ))

        return history

    def _analyze_cost_trend(
        self,
        history: List[CostHistoryEntry],
    ) -> Tuple[str, Optional[float]]:
        """Analyze cost trend from history."""
        if len(history) < 2:
            return "stable", None

        # Calculate change
        first_cost = history[0].cost
        last_cost = history[-1].cost

        if first_cost <= 0:
            return "stable", None

        change_percent = float(((last_cost - first_cost) / first_cost) * 100)

        if change_percent > 3:
            return "increasing", round(change_percent, 1)
        elif change_percent < -3:
            return "decreasing", round(change_percent, 1)
        else:
            return "stable", round(change_percent, 1)

    def _generate_optimization_suggestions(
        self,
        contract: Contract,
        monthly_cost: Decimal,
        cost_trend: str,
    ) -> List[OptimizationSuggestion]:
        """Generate optimization suggestions."""
        suggestions: List[OptimizationSuggestion] = []

        if monthly_cost <= 0:
            return suggestions

        annual_cost = monthly_cost * 12

        # 1. Renegotiation potential
        if contract.expiration_date:
            months_until_expiry = (contract.expiration_date - date.today()).days / 30
            if 3 <= months_until_expiry <= 12:
                potential = annual_cost * Decimal("0.10")
                suggestions.append(OptimizationSuggestion(
                    optimization_type="renegotiate",
                    title="Neuverhandlung bei Verlängerung",
                    description=(
                        f"Vertrag laeuft in {int(months_until_expiry)} Monaten ab. "
                        f"Nutzen Sie die Gelegenheit zur Neuverhandlung."
                    ),
                    potential_savings=potential,
                    savings_percent=10.0,
                    difficulty="medium",
                    priority=3,
                ))

        # 2. Trend-based suggestions
        if cost_trend == "increasing":
            potential = annual_cost * Decimal("0.05")
            suggestions.append(OptimizationSuggestion(
                optimization_type="reduce_scope",
                title="Kostenentwicklung überprüfen",
                description=(
                    "Die Kosten steigen. Prüfen Sie, ob alle Leistungen "
                    "noch benötigt werden oder der Umfang reduziert werden kann."
                ),
                potential_savings=potential,
                savings_percent=5.0,
                difficulty="low",
                priority=2,
            ))

        # 3. Auto-renewal optimization
        if contract.auto_renewal:
            potential = annual_cost * Decimal("0.15")
            suggestions.append(OptimizationSuggestion(
                optimization_type="term_optimization",
                title="Automatische Verlängerung überprüfen",
                description=(
                    "Automatische Verlängerung ist aktiv. "
                    "Vor der Verlängerung Konditionen am Markt vergleichen."
                ),
                potential_savings=potential,
                savings_percent=15.0,
                difficulty="medium",
                priority=4,
            ))

        # 4. Payment terms optimization
        payment_terms = contract.payment_terms or {}
        if not payment_terms.get("skonto_percent"):
            skonto_potential = annual_cost * Decimal("0.02")
            suggestions.append(OptimizationSuggestion(
                optimization_type="payment_terms",
                title="Skonto verhandeln",
                description=(
                    "Aktuell kein Skonto vereinbart. "
                    "Verhandeln Sie 2% Skonto bei Zahlung innerhalb 14 Tagen."
                ),
                potential_savings=skonto_potential,
                savings_percent=2.0,
                difficulty="low",
                priority=1,
            ))

        # 5. Large contract - consolidation potential
        if annual_cost > Decimal("50000"):
            potential = annual_cost * Decimal("0.10")
            suggestions.append(OptimizationSuggestion(
                optimization_type="consolidate",
                title="Konsolidierungspotenzial",
                description=(
                    "Bei diesem Vertragsvolumen könnte durch Buendelung "
                    "mit ähnlichen Verträgen ein besserer Preis erzielt werden."
                ),
                potential_savings=potential,
                savings_percent=10.0,
                difficulty="high",
                priority=3,
            ))

        # Sort by priority
        suggestions.sort(key=lambda x: x.priority, reverse=True)

        return suggestions

    async def _compare_to_benchmark(
        self,
        contract: Contract,
        monthly_cost: Decimal,
    ) -> Dict[str, Any]:
        """Compare contract costs to benchmarks."""
        from app.services.contracts.contract_benchmark_service import (
            ContractBenchmarkService,
            CONTRACT_TYPE_CATEGORIES,
        )

        category = CONTRACT_TYPE_CATEGORIES.get(contract.contract_type, "service")

        # Simple benchmark comparison
        benchmark_service = ContractBenchmarkService(self.db)
        benchmarks = await benchmark_service.get_benchmark_data(category)

        if not benchmarks:
            return {
                "available": False,
                "message": "Keine Benchmark-Daten für diese Kategorie",
            }

        # Find relevant benchmark
        avg_cost_bm = next(
            (b for b in benchmarks if "cost" in b.metric.lower()),
            None
        )

        if not avg_cost_bm:
            return {
                "available": False,
                "message": "Keine Kosten-Benchmarks verfügbar",
            }

        bm_value = float(avg_cost_bm.value) if avg_cost_bm.value else 0

        if bm_value > 0:
            percentile = min(100, max(0, int((float(monthly_cost) / bm_value) * 50)))
            comparison = "above_average" if float(monthly_cost) > bm_value else "below_average"
        else:
            percentile = 50
            comparison = "unknown"

        return {
            "available": True,
            "category": category,
            "percentile": percentile,
            "comparison": comparison,
            "benchmark_monthly": bm_value,
            "contract_monthly": float(monthly_cost),
            "vs_average_percent": round(((float(monthly_cost) - bm_value) / bm_value) * 100, 1) if bm_value > 0 else 0,
        }

    async def _save_analysis(
        self,
        contract_id: UUID,
        company_id: UUID,
        result: CostAnalysisResult,
    ) -> None:
        """Save or update cost analysis."""
        # Check for existing
        existing = await self.db.execute(
            select(ContractCostAnalysis).where(
                ContractCostAnalysis.contract_id == contract_id
            )
        )
        analysis = existing.scalar_one_or_none()

        if analysis:
            # Update existing
            analysis.monthly_cost = result.monthly_cost
            analysis.annual_cost = result.annual_cost
            analysis.total_contract_cost = result.total_contract_cost
            analysis.remaining_cost = result.remaining_cost
            analysis.currency = result.currency
            analysis.cost_breakdown = [
                {"category": cb.category, "name": cb.display_name, "amount": float(cb.amount), "percent": cb.percentage}
                for cb in result.cost_breakdown
            ]
            analysis.cost_trend = result.cost_trend
            analysis.trend_percent = Decimal(str(result.trend_percent)) if result.trend_percent else None
            analysis.cost_history = [
                {"period": h.period, "date": h.date.isoformat(), "cost": float(h.cost)}
                for h in result.cost_history
            ]
            analysis.optimization_potential = result.total_optimization_potential
            analysis.optimization_suggestions = [
                {
                    "type": s.optimization_type,
                    "title": s.title,
                    "description": s.description,
                    "potential": float(s.potential_savings),
                    "percent": s.savings_percent,
                    "difficulty": s.difficulty,
                }
                for s in result.optimization_suggestions
            ]
            analysis.benchmark_comparison = result.benchmark_comparison
            analysis.analyzed_at = result.analyzed_at
        else:
            # Create new
            analysis = ContractCostAnalysis(
                contract_id=contract_id,
                company_id=company_id,
                monthly_cost=result.monthly_cost,
                annual_cost=result.annual_cost,
                total_contract_cost=result.total_contract_cost,
                remaining_cost=result.remaining_cost,
                currency=result.currency,
                cost_breakdown=[
                    {"category": cb.category, "name": cb.display_name, "amount": float(cb.amount), "percent": cb.percentage}
                    for cb in result.cost_breakdown
                ],
                cost_trend=result.cost_trend,
                trend_percent=Decimal(str(result.trend_percent)) if result.trend_percent else None,
                cost_history=[
                    {"period": h.period, "date": h.date.isoformat(), "cost": float(h.cost)}
                    for h in result.cost_history
                ],
                optimization_potential=result.total_optimization_potential,
                optimization_suggestions=[
                    {
                        "type": s.optimization_type,
                        "title": s.title,
                        "description": s.description,
                        "potential": float(s.potential_savings),
                        "percent": s.savings_percent,
                        "difficulty": s.difficulty,
                    }
                    for s in result.optimization_suggestions
                ],
                benchmark_comparison=result.benchmark_comparison,
                analyzed_at=result.analyzed_at,
            )
            self.db.add(analysis)

        await self.db.commit()


# =============================================================================
# Factory Function
# =============================================================================


def get_contract_cost_analyzer(db: AsyncSession) -> ContractCostAnalyzer:
    """Factory function to create ContractCostAnalyzer instance."""
    return ContractCostAnalyzer(db)
