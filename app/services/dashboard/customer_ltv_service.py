# -*- coding: utf-8 -*-
"""Customer Lifetime Value Service.

Liefert Daten für das Customer LTV Widget:
- Kumulativer Umsatz pro Kunde
- Trend-Analyse (wachsend/rücklaeufig)
- Churn-Risiko-Indikator
- Top-Kunden-Ranking

Enterprise Feature: Januar 2026
"""

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal
from enum import Enum
from typing import List, Optional, Dict, Any
from uuid import UUID
import structlog

from sqlalchemy import select, func, and_, or_, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.datetime_utils import utc_now
from app.db.models import (
    BusinessEntity,
    InvoiceTracking,
    Document,
)

logger = structlog.get_logger(__name__)


class ChurnRisk(str, Enum):
    """Churn-Risiko-Stufen."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class RevenueTrend(str, Enum):
    """Umsatz-Trend."""
    GROWING = "growing"
    STABLE = "stable"
    DECLINING = "declining"


@dataclass
class CustomerMetrics:
    """Metriken für einen einzelnen Kunden."""
    entity_id: str
    entity_name: str
    lifetime_value: Decimal = Decimal("0.00")
    total_orders: int = 0
    first_order_date: Optional[date] = None
    last_order_date: Optional[date] = None
    avg_order_value: Decimal = Decimal("0.00")
    relationship_months: int = 0
    monthly_revenue_avg: Decimal = Decimal("0.00")
    revenue_trend: RevenueTrend = RevenueTrend.STABLE
    trend_percentage: float = 0.0
    churn_risk: ChurnRisk = ChurnRisk.LOW
    churn_risk_score: float = 0.0  # 0-100
    days_since_last_order: int = 0


@dataclass
class TrendDataPoint:
    """Datenpunkt für Trend-Analyse."""
    period: str  # YYYY-MM
    total_revenue: Decimal
    customer_count: int
    avg_order_value: Decimal


@dataclass
class CustomerLTVResult:
    """Gesamtergebnis der Customer LTV Analyse."""
    generated_at: datetime
    period_days: int

    # Aggregierte Metriken
    total_customers: int = 0
    active_customers: int = 0
    total_ltv: Decimal = Decimal("0.00")
    avg_ltv: Decimal = Decimal("0.00")
    avg_churn_risk: float = 0.0

    # Top Kunden
    top_customers: List[CustomerMetrics] = field(default_factory=list)

    # Risiko-Kunden (hohe Churn-Wahrscheinlichkeit)
    at_risk_customers: List[CustomerMetrics] = field(default_factory=list)

    # Trend-Daten
    trend_data: List[TrendDataPoint] = field(default_factory=list)
    overall_trend: RevenueTrend = RevenueTrend.STABLE
    overall_trend_percentage: float = 0.0


class CustomerLTVService:
    """Service für Customer Lifetime Value Metriken."""

    # Churn-Risiko Schwellenwerte (Tage ohne Bestellung)
    CHURN_LOW = 30
    CHURN_MEDIUM = 60
    CHURN_HIGH = 90
    CHURN_CRITICAL = 180

    async def get_customer_ltv(
        self,
        db: AsyncSession,
        user_id: UUID,
        company_id: Optional[UUID] = None,
        period_days: int = 365,
    ) -> CustomerLTVResult:
        """Hole Customer LTV Metriken.

        Args:
            db: Datenbank-Session
            user_id: Benutzer-ID
            company_id: Firmen-ID
            period_days: Auswertungszeitraum

        Returns:
            CustomerLTVResult mit allen Metriken
        """
        generated_at = utc_now()
        today = date.today()
        cutoff_date = today - timedelta(days=period_days)

        # 1. Alle Kunden laden
        customers = await self._get_customers(db, company_id)

        # 2. LTV pro Kunde berechnen
        customer_metrics = []
        for customer in customers:
            metrics = await self._calculate_customer_metrics(
                db, customer, cutoff_date, today, company_id
            )
            if metrics.total_orders > 0:
                customer_metrics.append(metrics)

        # 3. Top Kunden nach LTV
        sorted_by_ltv = sorted(
            customer_metrics,
            key=lambda c: c.lifetime_value,
            reverse=True,
        )
        top_customers = sorted_by_ltv[:10]

        # 4. Risiko-Kunden (hoher Churn-Score)
        at_risk = [
            c for c in customer_metrics
            if c.churn_risk in [ChurnRisk.HIGH, ChurnRisk.CRITICAL]
        ]
        at_risk_sorted = sorted(
            at_risk,
            key=lambda c: c.churn_risk_score,
            reverse=True,
        )[:5]

        # 5. Aggregierte Metriken
        total_ltv = sum(c.lifetime_value for c in customer_metrics)
        avg_ltv = total_ltv / len(customer_metrics) if customer_metrics else Decimal("0.00")
        avg_churn = (
            sum(c.churn_risk_score for c in customer_metrics) / len(customer_metrics)
            if customer_metrics else 0.0
        )

        # 6. Trend-Daten berechnen
        trend_data = await self._calculate_trend_data(
            db, company_id, period_days
        )

        # 7. Gesamt-Trend bestimmen
        overall_trend, trend_pct = self._determine_overall_trend(trend_data)

        logger.info(
            "customer_ltv_calculated",
            user_id=str(user_id),
            period_days=period_days,
            active_customers=len(customer_metrics),
            total_ltv=float(total_ltv),
            avg_churn_risk=avg_churn,
        )

        return CustomerLTVResult(
            generated_at=generated_at,
            period_days=period_days,
            total_customers=len(customers),
            active_customers=len(customer_metrics),
            total_ltv=total_ltv,
            avg_ltv=avg_ltv,
            avg_churn_risk=avg_churn,
            top_customers=top_customers,
            at_risk_customers=at_risk_sorted,
            trend_data=trend_data,
            overall_trend=overall_trend,
            overall_trend_percentage=trend_pct,
        )

    async def get_widget_data(
        self,
        db: AsyncSession,
        user_id: UUID,
        company_id: Optional[UUID] = None,
        period_days: int = 365,
    ) -> Dict[str, Any]:
        """Liefert Widget-Daten für Frontend.

        Returns:
            Dict mit Metriken für Widget-Anzeige
        """
        result = await self.get_customer_ltv(
            db, user_id, company_id, period_days
        )

        return {
            "generatedAt": result.generated_at.isoformat(),
            "periodDays": result.period_days,
            "totalCustomers": result.total_customers,
            "activeCustomers": result.active_customers,
            "totalLTV": float(result.total_ltv),
            "avgLTV": float(result.avg_ltv),
            "avgChurnRisk": round(result.avg_churn_risk, 1),
            "overallTrend": result.overall_trend.value,
            "trendPercentage": round(result.overall_trend_percentage, 1),
            "topCustomers": [
                {
                    "id": c.entity_id,
                    "name": c.entity_name,
                    "ltv": float(c.lifetime_value),
                    "orders": c.total_orders,
                    "avgOrder": float(c.avg_order_value),
                    "trend": c.revenue_trend.value,
                    "trendPct": round(c.trend_percentage, 1),
                    "churnRisk": c.churn_risk.value,
                    "churnScore": round(c.churn_risk_score, 1),
                    "daysSinceOrder": c.days_since_last_order,
                }
                for c in result.top_customers[:5]  # Top 5 für Widget
            ],
            "atRiskCustomers": [
                {
                    "id": c.entity_id,
                    "name": c.entity_name,
                    "ltv": float(c.lifetime_value),
                    "churnRisk": c.churn_risk.value,
                    "churnScore": round(c.churn_risk_score, 1),
                    "daysSinceOrder": c.days_since_last_order,
                }
                for c in result.at_risk_customers
            ],
            "trendData": [
                {
                    "period": t.period,
                    "revenue": float(t.total_revenue),
                    "customers": t.customer_count,
                    "avgOrder": float(t.avg_order_value),
                }
                for t in result.trend_data
            ],
        }

    async def _get_customers(
        self,
        db: AsyncSession,
        company_id: Optional[UUID],
    ) -> List[BusinessEntity]:
        """Lade alle Kunden-Entities."""
        query = select(BusinessEntity).where(
            and_(
                BusinessEntity.company_id == company_id if company_id else True,
                BusinessEntity.entity_type == "customer",
                BusinessEntity.is_deleted == False,
            )
        )

        result = await db.execute(query)
        return list(result.scalars().all())

    async def _calculate_customer_metrics(
        self,
        db: AsyncSession,
        customer: BusinessEntity,
        cutoff_date: date,
        today: date,
        company_id: Optional[UUID],
    ) -> CustomerMetrics:
        """Berechne Metriken für einen Kunden."""
        # Hole alle ausgehenden Rechnungen (Umsatz)
        query = select(InvoiceTracking).where(
            and_(
                InvoiceTracking.entity_id == customer.id,
                InvoiceTracking.company_id == company_id if company_id else True,
                InvoiceTracking.is_incoming == False,  # Ausgehende = Umsatz
            )
        )

        result = await db.execute(query)
        invoices = list(result.scalars().all())

        if not invoices:
            return CustomerMetrics(
                entity_id=str(customer.id),
                entity_name=customer.name or "Unbekannt",
            )

        # LTV = Summe aller Rechnungen
        lifetime_value = sum(
            Decimal(str(inv.total_amount or 0)) for inv in invoices
        )

        # Bestelldaten
        sorted_invoices = sorted(
            invoices,
            key=lambda i: i.created_at or datetime.min
        )
        first_order = sorted_invoices[0].created_at.date() if sorted_invoices[0].created_at else None
        last_order = sorted_invoices[-1].created_at.date() if sorted_invoices[-1].created_at else None

        # Durchschnittlicher Bestellwert
        avg_order = lifetime_value / len(invoices) if invoices else Decimal("0.00")

        # Beziehungsdauer in Monaten
        if first_order:
            relationship_months = max(1, (today - first_order).days // 30)
        else:
            relationship_months = 1

        # Monatlicher Durchschnittsumsatz
        monthly_avg = lifetime_value / Decimal(str(relationship_months))

        # Tage seit letzter Bestellung
        days_since = (today - last_order).days if last_order else 999

        # Churn-Risiko berechnen
        churn_risk, churn_score = self._calculate_churn_risk(
            days_since, len(invoices), relationship_months
        )

        # Trend berechnen (letzte 3 Monate vs vorherige 3 Monate)
        trend, trend_pct = self._calculate_customer_trend(
            invoices, today
        )

        return CustomerMetrics(
            entity_id=str(customer.id),
            entity_name=customer.name or "Unbekannt",
            lifetime_value=lifetime_value,
            total_orders=len(invoices),
            first_order_date=first_order,
            last_order_date=last_order,
            avg_order_value=avg_order,
            relationship_months=relationship_months,
            monthly_revenue_avg=monthly_avg,
            revenue_trend=trend,
            trend_percentage=trend_pct,
            churn_risk=churn_risk,
            churn_risk_score=churn_score,
            days_since_last_order=days_since,
        )

    def _calculate_churn_risk(
        self,
        days_since_order: int,
        total_orders: int,
        relationship_months: int,
    ) -> tuple[ChurnRisk, float]:
        """Berechne Churn-Risiko basierend auf mehreren Faktoren."""
        # Basis-Score: Tage seit letzter Bestellung
        if days_since_order <= self.CHURN_LOW:
            base_score = 10.0
        elif days_since_order <= self.CHURN_MEDIUM:
            base_score = 30.0
        elif days_since_order <= self.CHURN_HIGH:
            base_score = 60.0
        elif days_since_order <= self.CHURN_CRITICAL:
            base_score = 80.0
        else:
            base_score = 95.0

        # Modifikator: Bestellhäufigkeit
        avg_orders_per_month = total_orders / max(1, relationship_months)
        if avg_orders_per_month >= 2:
            frequency_mod = -15  # Häufige Besteller = weniger Risiko
        elif avg_orders_per_month >= 1:
            frequency_mod = -5
        elif avg_orders_per_month >= 0.5:
            frequency_mod = 0
        else:
            frequency_mod = 10  # Seltene Besteller = mehr Risiko

        # Modifikator: Beziehungsdauer
        if relationship_months >= 24:
            duration_mod = -10  # Langzeit-Kunden = weniger Risiko
        elif relationship_months >= 12:
            duration_mod = -5
        else:
            duration_mod = 5

        # Finaler Score (0-100)
        final_score = max(0, min(100, base_score + frequency_mod + duration_mod))

        # Risiko-Stufe ableiten
        if final_score >= 80:
            risk = ChurnRisk.CRITICAL
        elif final_score >= 60:
            risk = ChurnRisk.HIGH
        elif final_score >= 40:
            risk = ChurnRisk.MEDIUM
        else:
            risk = ChurnRisk.LOW

        return risk, final_score

    def _calculate_customer_trend(
        self,
        invoices: List[InvoiceTracking],
        today: date,
    ) -> tuple[RevenueTrend, float]:
        """Berechne Umsatz-Trend für einen Kunden."""
        if len(invoices) < 2:
            return RevenueTrend.STABLE, 0.0

        three_months_ago = today - timedelta(days=90)
        six_months_ago = today - timedelta(days=180)

        # Letzte 3 Monate
        recent = [
            inv for inv in invoices
            if inv.created_at and inv.created_at.date() >= three_months_ago
        ]
        recent_revenue = sum(
            float(inv.total_amount or 0) for inv in recent
        )

        # Vorherige 3 Monate
        previous = [
            inv for inv in invoices
            if inv.created_at and six_months_ago <= inv.created_at.date() < three_months_ago
        ]
        previous_revenue = sum(
            float(inv.total_amount or 0) for inv in previous
        )

        if previous_revenue > 0:
            change_pct = ((recent_revenue - previous_revenue) / previous_revenue) * 100
        elif recent_revenue > 0:
            change_pct = 100.0  # Neuer Kunde = wachsend
        else:
            change_pct = 0.0

        if change_pct > 10:
            trend = RevenueTrend.GROWING
        elif change_pct < -10:
            trend = RevenueTrend.DECLINING
        else:
            trend = RevenueTrend.STABLE

        return trend, change_pct

    async def _calculate_trend_data(
        self,
        db: AsyncSession,
        company_id: Optional[UUID],
        period_days: int,
    ) -> List[TrendDataPoint]:
        """Berechne monatliche Trend-Daten."""
        cutoff_date = date.today() - timedelta(days=period_days)

        query = select(
            func.date_trunc("month", InvoiceTracking.created_at).label("month"),
            func.sum(InvoiceTracking.total_amount).label("total_revenue"),
            func.count(func.distinct(InvoiceTracking.entity_id)).label("customer_count"),
            func.avg(InvoiceTracking.total_amount).label("avg_order"),
        ).where(
            and_(
                InvoiceTracking.company_id == company_id if company_id else True,
                InvoiceTracking.is_incoming == False,  # Ausgehende = Umsatz
                InvoiceTracking.created_at >= cutoff_date,
                InvoiceTracking.total_amount.isnot(None),
            )
        ).group_by(
            func.date_trunc("month", InvoiceTracking.created_at)
        ).order_by(
            func.date_trunc("month", InvoiceTracking.created_at)
        )

        result = await db.execute(query)
        rows = result.fetchall()

        return [
            TrendDataPoint(
                period=row.month.strftime("%Y-%m") if row.month else "Unknown",
                total_revenue=Decimal(str(row.total_revenue or 0)),
                customer_count=row.customer_count or 0,
                avg_order_value=Decimal(str(row.avg_order or 0)),
            )
            for row in rows
        ]

    def _determine_overall_trend(
        self,
        trend_data: List[TrendDataPoint],
    ) -> tuple[RevenueTrend, float]:
        """Bestimme Gesamt-Trend aus monatlichen Daten."""
        if len(trend_data) < 2:
            return RevenueTrend.STABLE, 0.0

        # Letzte 3 Monate vs erste 3 Monate
        if len(trend_data) >= 6:
            recent = trend_data[-3:]
            earlier = trend_data[:3]
        else:
            mid = len(trend_data) // 2
            recent = trend_data[mid:]
            earlier = trend_data[:mid]

        recent_avg = sum(float(t.total_revenue) for t in recent) / len(recent) if recent else 0
        earlier_avg = sum(float(t.total_revenue) for t in earlier) / len(earlier) if earlier else 0

        if earlier_avg > 0:
            change_pct = ((recent_avg - earlier_avg) / earlier_avg) * 100
        elif recent_avg > 0:
            change_pct = 100.0
        else:
            change_pct = 0.0

        if change_pct > 10:
            trend = RevenueTrend.GROWING
        elif change_pct < -10:
            trend = RevenueTrend.DECLINING
        else:
            trend = RevenueTrend.STABLE

        return trend, change_pct


# Singleton
_customer_ltv_service: Optional[CustomerLTVService] = None


def get_customer_ltv_service() -> CustomerLTVService:
    """Hole CustomerLTVService Singleton."""
    global _customer_ltv_service
    if _customer_ltv_service is None:
        _customer_ltv_service = CustomerLTVService()
    return _customer_ltv_service
