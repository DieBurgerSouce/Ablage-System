# -*- coding: utf-8 -*-
"""
InsightGeneratorService - Generiert proaktive Insights und Erklärungen.

Verantwortlich für:
- Proaktive Warnungen und Hinweise
- Cash-Flow-Analyse
- Anomalie-Erkennung
- Trend-Analysen
- Natürlichsprachliche Erklärungen

Vision 2.0 - Phase 1 (Januar 2026)
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import datetime, date, timedelta
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

import structlog
from sqlalchemy import select, and_, func, case, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.datetime_utils import utc_now
from app.db.models import Document, BusinessEntity, InvoiceTracking, BankTransaction

logger = structlog.get_logger(__name__)


class InsightCategory(str, Enum):
    """Kategorie eines Insights."""

    CASH_FLOW = "cash_flow"
    OVERDUE = "overdue"
    ANOMALY = "anomaly"
    TREND = "trend"
    OPPORTUNITY = "opportunity"
    RISK = "risk"
    COMPLIANCE = "compliance"
    OPTIMIZATION = "optimization"


class InsightSeverity(str, Enum):
    """Schweregrad eines Insights."""

    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"
    SUCCESS = "success"


@dataclass
class Insight:
    """Ein generiertes Insight."""

    id: uuid.UUID
    category: InsightCategory
    severity: InsightSeverity
    title: str
    summary: str
    details: str
    recommendations: List[str] = field(default_factory=list)
    affected_entities: List[uuid.UUID] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=utc_now)
    expires_at: Optional[datetime] = None
    action_url: Optional[str] = None


@dataclass
class InsightContext:
    """Kontext für Insight-Generierung."""

    company_id: uuid.UUID
    user_id: uuid.UUID
    date_from: Optional[date] = None
    date_to: Optional[date] = None
    include_predictions: bool = True


class InsightGeneratorService:
    """Service für proaktive Insight-Generierung.

    Analysiert Geschäftsdaten und generiert:
    - Warnungen bei Risiken
    - Optimierungsvorschläge
    - Trend-Analysen
    - Compliance-Hinweise
    """

    # Schwellwerte
    OVERDUE_THRESHOLD_DAYS = 30
    HIGH_AMOUNT_MULTIPLIER = 3.0
    LOW_CASH_FLOW_THRESHOLD = 5000
    SKONTO_WARNING_DAYS = 3

    def __init__(self, db: AsyncSession):
        """Initialisiert den Service.

        Args:
            db: Async Database Session
        """
        self.db = db

    async def generate_all_insights(
        self,
        context: InsightContext,
    ) -> List[Insight]:
        """Generiert alle relevanten Insights.

        Args:
            context: Generierungskontext

        Returns:
            Liste von Insights
        """
        insights: List[Insight] = []

        # Parallel Insights generieren
        tasks = [
            self._generate_overdue_insights(context),
            self._generate_cash_flow_insights(context),
            self._generate_skonto_insights(context),
            self._generate_anomaly_insights(context),
            self._generate_trend_insights(context),
            self._generate_risk_insights(context),
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        for result in results:
            if isinstance(result, Exception):
                logger.error("insight_generation_error", error=str(result))
            elif result:
                insights.extend(result)

        # Nach Severity sortieren
        severity_order = {
            InsightSeverity.CRITICAL: 0,
            InsightSeverity.WARNING: 1,
            InsightSeverity.INFO: 2,
            InsightSeverity.SUCCESS: 3,
        }
        insights.sort(key=lambda x: severity_order.get(x.severity, 99))

        logger.info(
            "insights_generated",
            company_id=str(context.company_id),
            count=len(insights),
        )

        return insights

    # ========================================================================
    # Overdue Insights
    # ========================================================================

    async def _generate_overdue_insights(
        self,
        context: InsightContext,
    ) -> List[Insight]:
        """Generiert Insights zu überfälligen Posten."""
        insights: List[Insight] = []

        # Überfällige Ausgangsrechnungen (Forderungen)
        receivables_stmt = (
            select(
                func.count(InvoiceTracking.id),
                func.sum(InvoiceTracking.total_amount),
                func.avg(
                    func.extract('day', utc_now() - InvoiceTracking.due_date)
                ),
            )
            .where(
                and_(
                    InvoiceTracking.company_id == context.company_id,
                    InvoiceTracking.invoice_type == "outgoing",
                    InvoiceTracking.status.in_(["pending", "open"]),
                    InvoiceTracking.due_date < date.today(),
                )
            )
        )
        result = await self.db.execute(receivables_stmt)
        row = result.one()
        overdue_count, overdue_amount, avg_days = row

        if overdue_count and overdue_count > 0:
            overdue_amount = overdue_amount or Decimal("0")
            avg_days = avg_days or 0

            severity = InsightSeverity.WARNING
            if overdue_amount > Decimal("10000") or avg_days > 30:
                severity = InsightSeverity.CRITICAL

            insights.append(Insight(
                id=uuid.uuid4(),
                category=InsightCategory.OVERDUE,
                severity=severity,
                title=f"{overdue_count} überfällige Forderungen",
                summary=f"Offene Forderungen: {float(overdue_amount):,.2f} EUR",
                details=f"""
Es gibt **{overdue_count} überfällige Ausgangsrechnungen** mit einem Gesamtbetrag von **{float(overdue_amount):,.2f} EUR**.

Die durchschnittliche Überfälligkeit beträgt **{int(avg_days)} Tage**.

Dies beeinträchtigt Ihre Liquidität und erhöht das Ausfallrisiko.
                """.strip(),
                recommendations=[
                    "Starten Sie einen Mahnlauf für Rechnungen >30 Tage überfällig",
                    "Prüfen Sie Zahlungsvereinbarungen mit säumigen Kunden",
                    "Erwägen Sie Skonto-Angebote für schnelle Zahlung",
                ],
                metrics={
                    "overdue_count": overdue_count,
                    "overdue_amount": float(overdue_amount),
                    "avg_days_overdue": int(avg_days),
                },
                action_url="/banking/dunning",
            ))

        # Überfällige Eingangsrechnungen (Verbindlichkeiten)
        payables_stmt = (
            select(
                func.count(InvoiceTracking.id),
                func.sum(InvoiceTracking.total_amount),
            )
            .where(
                and_(
                    InvoiceTracking.company_id == context.company_id,
                    InvoiceTracking.invoice_type == "incoming",
                    InvoiceTracking.status.in_(["pending", "open"]),
                    InvoiceTracking.due_date < date.today(),
                )
            )
        )
        result = await self.db.execute(payables_stmt)
        row = result.one()
        payable_count, payable_amount = row

        if payable_count and payable_count > 0:
            payable_amount = payable_amount or Decimal("0")

            insights.append(Insight(
                id=uuid.uuid4(),
                category=InsightCategory.OVERDUE,
                severity=InsightSeverity.WARNING,
                title=f"{payable_count} überfällige Verbindlichkeiten",
                summary=f"Offene Verbindlichkeiten: {float(payable_amount):,.2f} EUR",
                details=f"""
Sie haben **{payable_count} überfällige Eingangsrechnungen** offen mit einem Gesamtbetrag von **{float(payable_amount):,.2f} EUR**.

Überfällige Verbindlichkeiten können zu:
- Mahngebühren führen
- Lieferantenbeziehungen belasten
- Kreditwürdigkeit beeinträchtigen
                """.strip(),
                recommendations=[
                    "Priorisieren Sie Zahlungen nach Fälligkeit",
                    "Kontaktieren Sie Lieferanten für Zahlungsaufschub",
                    "Prüfen Sie Liquiditätsreserven",
                ],
                metrics={
                    "payable_count": payable_count,
                    "payable_amount": float(payable_amount),
                },
                action_url="/banking/payments",
            ))

        return insights

    # ========================================================================
    # Cash Flow Insights
    # ========================================================================

    async def _generate_cash_flow_insights(
        self,
        context: InsightContext,
    ) -> List[Insight]:
        """Generiert Cash-Flow-Insights."""
        insights: List[Insight] = []

        # Aktueller Monat
        month_start = date.today().replace(day=1)

        # Einnahmen (bezahlte Ausgangsrechnungen)
        income_stmt = (
            select(func.sum(InvoiceTracking.total_amount))
            .where(
                and_(
                    InvoiceTracking.company_id == context.company_id,
                    InvoiceTracking.invoice_type == "outgoing",
                    InvoiceTracking.status == "paid",
                    InvoiceTracking.paid_at >= month_start,
                )
            )
        )
        result = await self.db.execute(income_stmt)
        income = result.scalar() or Decimal("0")

        # Ausgaben (bezahlte Eingangsrechnungen)
        expense_stmt = (
            select(func.sum(InvoiceTracking.total_amount))
            .where(
                and_(
                    InvoiceTracking.company_id == context.company_id,
                    InvoiceTracking.invoice_type == "incoming",
                    InvoiceTracking.status == "paid",
                    InvoiceTracking.paid_at >= month_start,
                )
            )
        )
        result = await self.db.execute(expense_stmt)
        expenses = result.scalar() or Decimal("0")

        net_flow = income - expenses

        # Vormonat zum Vergleich
        last_month_start = (month_start - timedelta(days=1)).replace(day=1)
        last_month_end = month_start - timedelta(days=1)

        prev_income_stmt = (
            select(func.sum(InvoiceTracking.total_amount))
            .where(
                and_(
                    InvoiceTracking.company_id == context.company_id,
                    InvoiceTracking.invoice_type == "outgoing",
                    InvoiceTracking.status == "paid",
                    InvoiceTracking.paid_at >= last_month_start,
                    InvoiceTracking.paid_at <= last_month_end,
                )
            )
        )
        result = await self.db.execute(prev_income_stmt)
        prev_income = result.scalar() or Decimal("1")  # Avoid division by zero

        # Veränderung berechnen
        if prev_income > 0:
            income_change = ((income - prev_income) / prev_income) * 100
        else:
            income_change = 0

        # Insight erstellen
        if net_flow < 0:
            severity = InsightSeverity.CRITICAL if abs(net_flow) > self.LOW_CASH_FLOW_THRESHOLD else InsightSeverity.WARNING
            title = "Negativer Cash Flow"
            summary = f"Netto: {float(net_flow):+,.2f} EUR diesen Monat"
        elif net_flow < self.LOW_CASH_FLOW_THRESHOLD:
            severity = InsightSeverity.WARNING
            title = "Niedriger Cash Flow"
            summary = f"Netto: {float(net_flow):+,.2f} EUR diesen Monat"
        else:
            severity = InsightSeverity.SUCCESS
            title = "Positiver Cash Flow"
            summary = f"Netto: {float(net_flow):+,.2f} EUR diesen Monat"

        insights.append(Insight(
            id=uuid.uuid4(),
            category=InsightCategory.CASH_FLOW,
            severity=severity,
            title=title,
            summary=summary,
            details=f"""
**Cash Flow Analyse - {month_start.strftime('%B %Y')}**

| Kennzahl | Betrag |
|----------|--------|
| Einnahmen | {float(income):,.2f} EUR |
| Ausgaben | {float(expenses):,.2f} EUR |
| **Netto** | **{float(net_flow):+,.2f} EUR** |

Veränderung zum Vormonat: {income_change:+.1f}%
            """.strip(),
            recommendations=self._get_cash_flow_recommendations(net_flow, income_change),
            metrics={
                "income": float(income),
                "expenses": float(expenses),
                "net_flow": float(net_flow),
                "income_change_pct": round(float(income_change), 1),
            },
            action_url="/dashboard/cashflow",
        ))

        return insights

    def _get_cash_flow_recommendations(
        self,
        net_flow: Decimal,
        income_change: float,
    ) -> List[str]:
        """Generiert Cash-Flow-Empfehlungen."""
        recommendations = []

        if net_flow < 0:
            recommendations.append("Prüfen Sie offene Forderungen und starten Sie Mahnlauf")
            recommendations.append("Verschieben Sie nicht dringende Ausgaben")
            recommendations.append("Verhandeln Sie längere Zahlungsziele mit Lieferanten")

        if income_change < -10:
            recommendations.append("Analysieren Sie Umsatzrückgang - Kundenschwund?")
            recommendations.append("Prüfen Sie Preisgestaltung und Konditionen")

        if net_flow > 0 and net_flow < Decimal("5000"):
            recommendations.append("Bauen Sie Liquiditätsreserve auf")
            recommendations.append("Prüfen Sie Skonto-Nutzung bei Lieferanten")

        if not recommendations:
            recommendations.append("Aktuelle Cash-Flow-Position ist stabil")
            recommendations.append("Erwägen Sie Investitionen oder Rücklagen")

        return recommendations

    # ========================================================================
    # Skonto Insights
    # ========================================================================

    async def _generate_skonto_insights(
        self,
        context: InsightContext,
    ) -> List[Insight]:
        """Generiert Skonto-Insights."""
        insights: List[Insight] = []

        # Rechnungen mit ablaufendem Skonto
        skonto_deadline = date.today() + timedelta(days=self.SKONTO_WARNING_DAYS)

        stmt = (
            select(
                func.count(InvoiceTracking.id),
                func.sum(InvoiceTracking.skonto_amount),
            )
            .where(
                and_(
                    InvoiceTracking.company_id == context.company_id,
                    InvoiceTracking.invoice_type == "incoming",
                    InvoiceTracking.status.in_(["pending", "open"]),
                    InvoiceTracking.skonto_deadline.isnot(None),
                    InvoiceTracking.skonto_deadline <= skonto_deadline,
                    InvoiceTracking.skonto_deadline >= date.today(),
                    InvoiceTracking.skonto_used == False,
                )
            )
        )
        result = await self.db.execute(stmt)
        row = result.one()
        skonto_count, skonto_savings = row

        if skonto_count and skonto_count > 0:
            skonto_savings = skonto_savings or Decimal("0")

            insights.append(Insight(
                id=uuid.uuid4(),
                category=InsightCategory.OPPORTUNITY,
                severity=InsightSeverity.WARNING,
                title=f"{skonto_count} Skonto-Fristen laufen ab",
                summary=f"Mögliche Ersparnis: {float(skonto_savings):,.2f} EUR",
                details=f"""
**{skonto_count} Rechnungen** haben Skonto-Fristen, die in den nächsten **{self.SKONTO_WARNING_DAYS} Tagen** ablaufen.

Potenzielle Ersparnis bei Zahlung: **{float(skonto_savings):,.2f} EUR**

Skonto-Nutzung ist eine der einfachsten Möglichkeiten, Kosten zu reduzieren.
                """.strip(),
                recommendations=[
                    "Priorisieren Sie diese Zahlungen",
                    f"Zahlen Sie vor Ablauf der {self.SKONTO_WARNING_DAYS}-Tage-Frist",
                    "Prüfen Sie Liquidität für vorzeitige Zahlung",
                ],
                metrics={
                    "expiring_count": skonto_count,
                    "potential_savings": float(skonto_savings),
                },
                action_url="/banking/skonto",
            ))

        # Verpasste Skonti im letzten Monat
        month_start = date.today().replace(day=1)

        missed_stmt = (
            select(func.sum(InvoiceTracking.skonto_amount))
            .where(
                and_(
                    InvoiceTracking.company_id == context.company_id,
                    InvoiceTracking.invoice_type == "incoming",
                    InvoiceTracking.skonto_deadline < date.today(),
                    InvoiceTracking.skonto_deadline >= month_start,
                    InvoiceTracking.skonto_used == False,
                    InvoiceTracking.status == "paid",
                )
            )
        )
        result = await self.db.execute(missed_stmt)
        missed_savings = result.scalar() or Decimal("0")

        if missed_savings > Decimal("100"):
            insights.append(Insight(
                id=uuid.uuid4(),
                category=InsightCategory.OPTIMIZATION,
                severity=InsightSeverity.INFO,
                title="Verpasste Skonto-Ersparnis",
                summary=f"{float(missed_savings):,.2f} EUR diesen Monat",
                details=f"""
Diesen Monat wurden **{float(missed_savings):,.2f} EUR** an Skonto-Ersparnissen nicht genutzt.

Optimieren Sie Ihre Zahlungsprozesse, um zukünftig Skonto-Fristen einzuhalten.
                """.strip(),
                recommendations=[
                    "Automatische Skonto-Erinnerungen aktivieren",
                    "Zahlungslauf-Planung optimieren",
                    "Priorisierung nach Skonto-Höhe einführen",
                ],
                metrics={
                    "missed_savings": float(missed_savings),
                },
                action_url="/banking/skonto/missed",
            ))

        return insights

    # ========================================================================
    # Anomaly Insights
    # ========================================================================

    async def _generate_anomaly_insights(
        self,
        context: InsightContext,
    ) -> List[Insight]:
        """Generiert Anomalie-Insights."""
        insights: List[Insight] = []

        # Durchschnittlichen Rechnungsbetrag berechnen
        avg_stmt = (
            select(func.avg(InvoiceTracking.total_amount))
            .where(
                and_(
                    InvoiceTracking.company_id == context.company_id,
                    InvoiceTracking.created_at >= date.today() - timedelta(days=90),
                )
            )
        )
        result = await self.db.execute(avg_stmt)
        avg_amount = result.scalar() or Decimal("1000")

        threshold = avg_amount * Decimal(str(self.HIGH_AMOUNT_MULTIPLIER))

        # Ungewöhnlich hohe Rechnungen in letzten 7 Tagen
        high_stmt = (
            select(InvoiceTracking)
            .where(
                and_(
                    InvoiceTracking.company_id == context.company_id,
                    InvoiceTracking.total_amount > threshold,
                    InvoiceTracking.created_at >= date.today() - timedelta(days=7),
                )
            )
            .order_by(InvoiceTracking.total_amount.desc())
            .limit(5)
        )
        result = await self.db.execute(high_stmt)
        high_invoices = result.scalars().all()

        if high_invoices:
            total_high = sum(i.total_amount for i in high_invoices)

            insights.append(Insight(
                id=uuid.uuid4(),
                category=InsightCategory.ANOMALY,
                severity=InsightSeverity.WARNING,
                title=f"{len(high_invoices)} ungewöhnlich hohe Rechnungen",
                summary=f"Beträge über {float(threshold):,.0f} EUR (3x Durchschnitt)",
                details=f"""
**{len(high_invoices)} Rechnungen** in den letzten 7 Tagen überschreiten den 3-fachen Durchschnittsbetrag von {float(avg_amount):,.2f} EUR.

Gesamtbetrag: **{float(total_high):,.2f} EUR**

Diese sollten manuell auf Korrektheit geprüft werden.
                """.strip(),
                recommendations=[
                    "Prüfen Sie diese Rechnungen manuell",
                    "Vergleichen Sie mit Bestellungen/Verträgen",
                    "Bei Eingangsrechnungen: Lieferantenrückfrage",
                ],
                affected_entities=[i.id for i in high_invoices],
                metrics={
                    "high_count": len(high_invoices),
                    "average_amount": float(avg_amount),
                    "threshold": float(threshold),
                    "total_high_amount": float(total_high),
                },
                action_url="/documents/review",
            ))

        # Doppelte Rechnungsnummern prüfen
        duplicate_stmt = (
            select(
                InvoiceTracking.invoice_number,
                func.count(InvoiceTracking.id).label("cnt"),
            )
            .where(
                and_(
                    InvoiceTracking.company_id == context.company_id,
                    InvoiceTracking.invoice_number.isnot(None),
                    InvoiceTracking.created_at >= date.today() - timedelta(days=30),
                )
            )
            .group_by(InvoiceTracking.invoice_number)
            .having(func.count(InvoiceTracking.id) > 1)
        )
        result = await self.db.execute(duplicate_stmt)
        duplicates = result.all()

        if duplicates:
            insights.append(Insight(
                id=uuid.uuid4(),
                category=InsightCategory.ANOMALY,
                severity=InsightSeverity.CRITICAL,
                title=f"{len(duplicates)} mögliche Duplikat-Rechnungen",
                summary="Gleiche Rechnungsnummern erkannt",
                details=f"""
**{len(duplicates)} Rechnungsnummern** kommen mehrfach vor:

{chr(10).join(f'- {d[0]}: {d[1]}x vorhanden' for d in duplicates[:5])}

Dies könnte auf:
- Doppelte Erfassung hindeuten
- Betrugsverdacht sein
- Systemfehler bedeuten
                """.strip(),
                recommendations=[
                    "Prüfen Sie diese Rechnungen sofort",
                    "Vergleichen Sie mit Originaldokumenten",
                    "Kontaktieren Sie Lieferanten bei Unklarheit",
                ],
                metrics={
                    "duplicate_numbers": len(duplicates),
                },
                action_url="/admin/fraud",
            ))

        return insights

    # ========================================================================
    # Trend Insights
    # ========================================================================

    async def _generate_trend_insights(
        self,
        context: InsightContext,
    ) -> List[Insight]:
        """Generiert Trend-Insights."""
        insights: List[Insight] = []

        # Monatliche Umsätze der letzten 6 Monate
        stmt = (
            select(
                func.date_trunc('month', InvoiceTracking.created_at).label('month'),
                func.sum(InvoiceTracking.total_amount).label('total'),
            )
            .where(
                and_(
                    InvoiceTracking.company_id == context.company_id,
                    InvoiceTracking.invoice_type == "outgoing",
                    InvoiceTracking.created_at >= date.today() - timedelta(days=180),
                )
            )
            .group_by('month')
            .order_by('month')
        )
        result = await self.db.execute(stmt)
        monthly_data = result.all()

        if len(monthly_data) >= 3:
            # Trend berechnen (einfache lineare Regression)
            values = [float(m.total or 0) for m in monthly_data]

            # Durchschnittliche Veränderung
            if len(values) >= 2:
                changes = [values[i] - values[i-1] for i in range(1, len(values))]
                avg_change = sum(changes) / len(changes)
                last_value = values[-1]
                predicted_next = last_value + avg_change

                if avg_change < 0:
                    trend = "fallend"
                    severity = InsightSeverity.WARNING
                else:
                    trend = "steigend"
                    severity = InsightSeverity.SUCCESS

                pct_change = (avg_change / (sum(values) / len(values))) * 100 if sum(values) > 0 else 0

                insights.append(Insight(
                    id=uuid.uuid4(),
                    category=InsightCategory.TREND,
                    severity=severity,
                    title=f"Umsatztrend: {trend}",
                    summary=f"Durchschnittliche monatliche Veränderung: {pct_change:+.1f}%",
                    details=f"""
**6-Monats-Umsatztrend**: {trend.upper()}

| Monat | Umsatz |
|-------|--------|
{chr(10).join(f'| {m.month.strftime("%b %Y") if m.month else "N/A"} | {float(m.total or 0):,.0f} EUR |' for m in monthly_data[-4:])}

**Prognose nächster Monat**: ~{predicted_next:,.0f} EUR

_Basierend auf linearer Trendfortschreibung_
                    """.strip(),
                    recommendations=self._get_trend_recommendations(avg_change, pct_change),
                    metrics={
                        "trend_direction": trend,
                        "avg_monthly_change": avg_change,
                        "pct_change": round(pct_change, 1),
                        "predicted_next": predicted_next,
                    },
                    action_url="/dashboard/analytics",
                ))

        return insights

    def _get_trend_recommendations(
        self,
        avg_change: float,
        pct_change: float,
    ) -> List[str]:
        """Generiert Trend-basierte Empfehlungen."""
        recommendations = []

        if pct_change < -10:
            recommendations.append("Analysieren Sie Ursachen für Umsatzrückgang")
            recommendations.append("Prüfen Sie Kundenabwanderung")
            recommendations.append("Erwägen Sie Marketing-Maßnahmen")
        elif pct_change < 0:
            recommendations.append("Beobachten Sie den Trend weiter")
            recommendations.append("Prüfen Sie saisonale Effekte")
        elif pct_change > 10:
            recommendations.append("Stellen Sie Kapazitäten sicher")
            recommendations.append("Prüfen Sie Liquiditätsbedarf für Wachstum")
        else:
            recommendations.append("Stabiler Trend - weiter beobachten")

        return recommendations

    # ========================================================================
    # Risk Insights
    # ========================================================================

    async def _generate_risk_insights(
        self,
        context: InsightContext,
    ) -> List[Insight]:
        """Generiert Risiko-Insights."""
        insights: List[Insight] = []

        # Kunden mit hohem Ausfallrisiko
        high_risk_stmt = (
            select(BusinessEntity)
            .where(
                and_(
                    BusinessEntity.company_id == context.company_id,
                    BusinessEntity.risk_score >= 75,
                )
            )
            .order_by(BusinessEntity.risk_score.desc())
            .limit(5)
        )
        result = await self.db.execute(high_risk_stmt)
        high_risk_entities = result.scalars().all()

        if high_risk_entities:
            # Offene Beträge dieser Kunden
            entity_ids = [e.id for e in high_risk_entities]

            open_stmt = (
                select(func.sum(InvoiceTracking.total_amount))
                .where(
                    and_(
                        InvoiceTracking.company_id == context.company_id,
                        InvoiceTracking.business_entity_id.in_(entity_ids),
                        InvoiceTracking.status.in_(["pending", "open"]),
                    )
                )
            )
            result = await self.db.execute(open_stmt)
            at_risk_amount = result.scalar() or Decimal("0")

            insights.append(Insight(
                id=uuid.uuid4(),
                category=InsightCategory.RISK,
                severity=InsightSeverity.CRITICAL if at_risk_amount > Decimal("10000") else InsightSeverity.WARNING,
                title=f"{len(high_risk_entities)} High-Risk Geschäftspartner",
                summary=f"Gefährdetes Volumen: {float(at_risk_amount):,.2f} EUR",
                details=f"""
**{len(high_risk_entities)} Geschäftspartner** haben einen Risiko-Score von 75 oder höher.

Offene Forderungen bei diesen Partnern: **{float(at_risk_amount):,.2f} EUR**

Diese Kunden haben ein erhöhtes Ausfallrisiko basierend auf:
- Zahlungshistorie
- Überfälligkeitsquote
- Mahnhäufigkeit
                """.strip(),
                recommendations=[
                    "Reduzieren Sie Kreditlinien",
                    "Fordern Sie Vorauszahlung bei neuen Aufträgen",
                    "Intensivieren Sie das Forderungsmanagement",
                ],
                affected_entities=entity_ids,
                metrics={
                    "high_risk_count": len(high_risk_entities),
                    "at_risk_amount": float(at_risk_amount),
                },
                action_url="/entities/risk",
            ))

        # Konzentrationsrisiko
        concentration_stmt = (
            select(
                InvoiceTracking.business_entity_id,
                func.sum(InvoiceTracking.total_amount).label('total'),
            )
            .where(
                and_(
                    InvoiceTracking.company_id == context.company_id,
                    InvoiceTracking.invoice_type == "outgoing",
                    InvoiceTracking.created_at >= date.today() - timedelta(days=365),
                )
            )
            .group_by(InvoiceTracking.business_entity_id)
            .order_by(func.sum(InvoiceTracking.total_amount).desc())
            .limit(5)
        )
        result = await self.db.execute(concentration_stmt)
        top_customers = result.all()

        if top_customers:
            total_revenue = sum(c.total or Decimal("0") for c in top_customers)

            all_revenue_stmt = (
                select(func.sum(InvoiceTracking.total_amount))
                .where(
                    and_(
                        InvoiceTracking.company_id == context.company_id,
                        InvoiceTracking.invoice_type == "outgoing",
                        InvoiceTracking.created_at >= date.today() - timedelta(days=365),
                    )
                )
            )
            result = await self.db.execute(all_revenue_stmt)
            all_revenue = result.scalar() or Decimal("1")

            concentration_pct = (total_revenue / all_revenue) * 100 if all_revenue > 0 else 0

            if concentration_pct > 50:
                insights.append(Insight(
                    id=uuid.uuid4(),
                    category=InsightCategory.RISK,
                    severity=InsightSeverity.WARNING,
                    title="Hohe Kundenkonzentration",
                    summary=f"Top-5 Kunden: {float(concentration_pct):.1f}% des Umsatzes",
                    details=f"""
Die **Top 5 Kunden** machen **{float(concentration_pct):.1f}%** Ihres Jahresumsatzes aus.

Dies bedeutet erhöhtes Risiko bei Kundenausfall.

Diversifizierung der Kundenbasis wird empfohlen.
                    """.strip(),
                    recommendations=[
                        "Akquirieren Sie neue Kunden",
                        "Bauen Sie Beziehungen zu kleineren Kunden aus",
                        "Prüfen Sie Abhängigkeiten kritisch",
                    ],
                    metrics={
                        "top5_concentration": float(concentration_pct),
                    },
                    action_url="/analytics/customers",
                ))

        return insights


# ============================================================================
# Factory Function
# ============================================================================


async def get_insight_generator_service(db: AsyncSession) -> InsightGeneratorService:
    """Factory-Funktion für InsightGeneratorService.

    Args:
        db: Async Database Session

    Returns:
        Konfigurierter InsightGeneratorService
    """
    return InsightGeneratorService(db=db)
