# -*- coding: utf-8 -*-
"""Cash-Flow Forecast Service.

Liefert Daten für das Cash-Flow Forecast Widget:
- 30/60/90 Tage Liquiditaetsprognose
- Einnahmen vs Ausgaben basierend auf offenen Rechnungen
- Skonto-Auswirkungen berücksichtigt
- Confidence-basierte Prognosen

Enterprise Feature: Januar 2026
"""

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal
from enum import Enum
from typing import List, Optional, Dict, Any
from uuid import UUID
import structlog

from sqlalchemy import select, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.datetime_utils import utc_now
from app.services.invoice_direction import is_incoming_invoice, is_outgoing_invoice
from app.db.models import (
    InvoiceTracking,
    BankTransaction,
    Document,
)

logger = structlog.get_logger(__name__)


class ForecastPeriod(str, Enum):
    """Verfügbare Prognose-Zeitraeume."""
    DAYS_30 = "30"
    DAYS_60 = "60"
    DAYS_90 = "90"


@dataclass
class ForecastDataPoint:
    """Einzelner Datenpunkt in der Prognose."""
    date: date
    expected_income: Decimal = Decimal("0.00")
    expected_expenses: Decimal = Decimal("0.00")
    net_flow: Decimal = Decimal("0.00")
    cumulative_balance: Decimal = Decimal("0.00")
    confidence: float = 0.8  # 0-1


@dataclass
class SkontoImpact:
    """Skonto-Auswirkung auf Cash-Flow."""
    invoice_count: int = 0
    potential_savings: Decimal = Decimal("0.00")
    deadline_income_impact: Decimal = Decimal("0.00")
    deadline_expense_impact: Decimal = Decimal("0.00")


@dataclass
class PeriodForecast:
    """Zusammenfassung für einen Prognosezeitraum."""
    period_days: int
    start_date: date
    end_date: date
    total_expected_income: Decimal = Decimal("0.00")
    total_expected_expenses: Decimal = Decimal("0.00")
    net_flow: Decimal = Decimal("0.00")
    ending_balance: Decimal = Decimal("0.00")
    confidence_score: float = 0.0
    income_invoice_count: int = 0
    expense_invoice_count: int = 0


@dataclass
class CashFlowForecastResult:
    """Gesamtergebnis der Cash-Flow Prognose."""
    generated_at: datetime
    current_balance: Decimal
    forecast_30: PeriodForecast
    forecast_60: PeriodForecast
    forecast_90: PeriodForecast
    daily_data: List[ForecastDataPoint] = field(default_factory=list)
    skonto_impact: SkontoImpact = field(default_factory=SkontoImpact)
    risk_warning: Optional[str] = None


class CashFlowForecastService:
    """Service für Cash-Flow Prognosen im Dashboard."""

    # Zahlungswahrscheinlichkeiten basierend auf Zahlungsziel
    PAYMENT_PROBABILITY = {
        "overdue": 0.3,     # Überfällig: 30% Wahrscheinlichkeit
        "due_soon": 0.7,    # Bald fällig: 70%
        "on_time": 0.85,    # Im Rahmen: 85%
        "early": 0.95,      # Früh: 95%
    }

    async def get_forecast(
        self,
        db: AsyncSession,
        user_id: UUID,
        company_id: Optional[UUID] = None,
        starting_balance: Optional[Decimal] = None,
    ) -> CashFlowForecastResult:
        """Erstelle Cash-Flow Prognose für 30/60/90 Tage.

        Args:
            db: Datenbank-Session
            user_id: Benutzer-ID
            company_id: Firmen-ID für Multi-Tenant
            starting_balance: Anfangssaldo (optional)

        Returns:
            CashFlowForecastResult mit allen Prognosen
        """
        generated_at = utc_now()
        today = date.today()

        # 1. Aktuellen Saldo ermitteln
        if starting_balance is None:
            starting_balance = await self._get_current_balance(db, user_id)

        # 2. Offene Rechnungen laden (Einnahmen)
        receivables = await self._get_open_receivables(
            db, user_id, company_id, today, 90
        )

        # 3. Offene Verbindlichkeiten laden (Ausgaben)
        payables = await self._get_open_payables(
            db, user_id, company_id, today, 90
        )

        # 4. Tägliche Datenpunkte berechnen
        daily_data = self._calculate_daily_forecast(
            today, 90, starting_balance, receivables, payables
        )

        # 5. Perioden-Zusammenfassungen erstellen
        forecast_30 = self._summarize_period(daily_data[:30], 30, today, starting_balance)
        forecast_60 = self._summarize_period(daily_data[:60], 60, today, starting_balance)
        forecast_90 = self._summarize_period(daily_data, 90, today, starting_balance)

        # 6. Skonto-Auswirkungen berechnen
        skonto_impact = await self._calculate_skonto_impact(
            db, user_id, company_id, today, 30
        )

        # 7. Risikowarnung generieren
        risk_warning = self._check_liquidity_risk(
            forecast_30, forecast_60, forecast_90, starting_balance
        )

        logger.info(
            "cash_flow_forecast_generated",
            user_id=str(user_id),
            starting_balance=float(starting_balance),
            net_30d=float(forecast_30.net_flow),
            net_60d=float(forecast_60.net_flow),
            net_90d=float(forecast_90.net_flow),
        )

        return CashFlowForecastResult(
            generated_at=generated_at,
            current_balance=starting_balance,
            forecast_30=forecast_30,
            forecast_60=forecast_60,
            forecast_90=forecast_90,
            daily_data=daily_data,
            skonto_impact=skonto_impact,
            risk_warning=risk_warning,
        )

    async def get_chart_data(
        self,
        db: AsyncSession,
        user_id: UUID,
        company_id: Optional[UUID] = None,
        days: int = 30,
        starting_balance: Optional[Decimal] = None,
    ) -> List[Dict[str, Any]]:
        """Liefert Chart-Daten für Frontend-Visualisierung.

        Args:
            db: Datenbank-Session
            user_id: Benutzer-ID
            company_id: Firmen-ID
            days: Anzahl Tage (7, 30, 60, 90)
            starting_balance: Anfangssaldo

        Returns:
            Liste mit täglichen Datenpunkten für Chart
        """
        forecast = await self.get_forecast(
            db, user_id, company_id, starting_balance
        )

        data_points = forecast.daily_data[:days]

        return [
            {
                "date": point.date.isoformat(),
                "income": float(point.expected_income),
                "expenses": float(point.expected_expenses),
                "net": float(point.net_flow),
                "balance": float(point.cumulative_balance),
                "confidence": point.confidence,
            }
            for point in data_points
        ]

    async def _get_current_balance(
        self,
        db: AsyncSession,
        user_id: UUID,
    ) -> Decimal:
        """Ermittle aktuellen Kontostand aus Transaktionen."""
        query = (
            select(func.coalesce(func.sum(BankTransaction.amount), 0))
            .where(
                and_(
                    BankTransaction.user_id == user_id,
                    BankTransaction.is_deleted == False,
                )
            )
        )

        result = await db.execute(query)
        balance = result.scalar() or Decimal("0.00")

        return Decimal(str(balance))

    async def _get_open_receivables(
        self,
        db: AsyncSession,
        user_id: UUID,
        company_id: Optional[UUID],
        from_date: date,
        days_ahead: int,
    ) -> List[Dict[str, Any]]:
        """Lade offene Forderungen (erwartete Einnahmen)."""
        end_date = from_date + timedelta(days=days_ahead)

        query = select(InvoiceTracking).where(
            and_(
                InvoiceTracking.company_id == company_id if company_id else True,
                is_outgoing_invoice(),  # Ausgangsrechnungen (Kunde) = Forderungen
                InvoiceTracking.paid_at.is_(None),  # Noch nicht bezahlt
                or_(
                    InvoiceTracking.due_date.is_(None),
                    InvoiceTracking.due_date <= end_date,
                ),
            )
        )

        result = await db.execute(query)
        invoices = result.scalars().all()

        receivables = []
        for inv in invoices:
            expected_date = inv.due_date or from_date + timedelta(days=14)
            probability = self._calculate_payment_probability(inv, from_date)

            amount = inv.outstanding_amount or inv.amount or Decimal("0.00")

            receivables.append({
                "invoice_id": str(inv.id),
                "expected_date": expected_date,
                "amount": Decimal(str(amount)),
                "probability": probability,
                "has_skonto": inv.skonto_percentage is not None and inv.skonto_percentage > 0,
            })

        return receivables

    async def _get_open_payables(
        self,
        db: AsyncSession,
        user_id: UUID,
        company_id: Optional[UUID],
        from_date: date,
        days_ahead: int,
    ) -> List[Dict[str, Any]]:
        """Lade offene Verbindlichkeiten (erwartete Ausgaben)."""
        end_date = from_date + timedelta(days=days_ahead)

        query = select(InvoiceTracking).where(
            and_(
                InvoiceTracking.company_id == company_id if company_id else True,
                is_incoming_invoice(),  # Eingangsrechnungen (Lieferant) = Verbindlichkeiten
                InvoiceTracking.paid_at.is_(None),  # Noch nicht bezahlt
                or_(
                    InvoiceTracking.due_date.is_(None),
                    InvoiceTracking.due_date <= end_date,
                ),
            )
        )

        result = await db.execute(query)
        invoices = result.scalars().all()

        payables = []
        for inv in invoices:
            expected_date = inv.due_date or from_date + timedelta(days=14)
            probability = 0.9  # Verbindlichkeiten zahlen wir mit hoher Wahrscheinlichkeit

            amount = inv.outstanding_amount or inv.amount or Decimal("0.00")

            payables.append({
                "invoice_id": str(inv.id),
                "expected_date": expected_date,
                "amount": Decimal(str(amount)),
                "probability": probability,
                "has_skonto": inv.skonto_percentage is not None and inv.skonto_percentage > 0,
                "skonto_deadline": inv.skonto_deadline,
            })

        return payables

    def _calculate_payment_probability(
        self,
        invoice: InvoiceTracking,
        reference_date: date,
    ) -> float:
        """Berechne Zahlungswahrscheinlichkeit basierend auf Status."""
        if invoice.due_date is None:
            return self.PAYMENT_PROBABILITY["on_time"]

        days_until_due = (invoice.due_date - reference_date).days

        if days_until_due < 0:
            return self.PAYMENT_PROBABILITY["overdue"]
        elif days_until_due <= 7:
            return self.PAYMENT_PROBABILITY["due_soon"]
        elif days_until_due <= 30:
            return self.PAYMENT_PROBABILITY["on_time"]
        else:
            return self.PAYMENT_PROBABILITY["early"]

    def _calculate_daily_forecast(
        self,
        start_date: date,
        days: int,
        starting_balance: Decimal,
        receivables: List[Dict[str, Any]],
        payables: List[Dict[str, Any]],
    ) -> List[ForecastDataPoint]:
        """Berechne tägliche Prognose-Datenpunkte."""
        daily_data = []
        cumulative = starting_balance

        for day_offset in range(days):
            current_date = start_date + timedelta(days=day_offset)

            # Erwartete Einnahmen an diesem Tag
            day_income = Decimal("0.00")
            income_confidence = 1.0
            income_count = 0

            for rec in receivables:
                if rec["expected_date"] == current_date:
                    weighted_amount = rec["amount"] * Decimal(str(rec["probability"]))
                    day_income += weighted_amount
                    income_confidence *= rec["probability"]
                    income_count += 1

            # Erwartete Ausgaben an diesem Tag
            day_expenses = Decimal("0.00")
            expense_confidence = 1.0

            for pay in payables:
                pay_date = pay.get("skonto_deadline") or pay["expected_date"]
                if pay_date == current_date:
                    weighted_amount = pay["amount"] * Decimal(str(pay["probability"]))
                    day_expenses += weighted_amount
                    expense_confidence *= pay["probability"]

            net_flow = day_income - day_expenses
            cumulative += net_flow

            # Confidence als Durchschnitt
            avg_confidence = (income_confidence + expense_confidence) / 2 if income_count > 0 else 0.8

            daily_data.append(ForecastDataPoint(
                date=current_date,
                expected_income=day_income,
                expected_expenses=day_expenses,
                net_flow=net_flow,
                cumulative_balance=cumulative,
                confidence=min(1.0, avg_confidence),
            ))

        return daily_data

    def _summarize_period(
        self,
        daily_data: List[ForecastDataPoint],
        period_days: int,
        start_date: date,
        starting_balance: Decimal,
    ) -> PeriodForecast:
        """Fasse Periode zusammen."""
        total_income = sum(d.expected_income for d in daily_data)
        total_expenses = sum(d.expected_expenses for d in daily_data)
        net_flow = total_income - total_expenses
        ending_balance = starting_balance + net_flow

        # Confidence als gewichteter Durchschnitt
        if daily_data:
            avg_confidence = sum(d.confidence for d in daily_data) / len(daily_data)
        else:
            avg_confidence = 0.5

        # Rechnungszähler
        income_count = sum(1 for d in daily_data if d.expected_income > 0)
        expense_count = sum(1 for d in daily_data if d.expected_expenses > 0)

        return PeriodForecast(
            period_days=period_days,
            start_date=start_date,
            end_date=start_date + timedelta(days=period_days - 1),
            total_expected_income=total_income,
            total_expected_expenses=total_expenses,
            net_flow=net_flow,
            ending_balance=ending_balance,
            confidence_score=avg_confidence,
            income_invoice_count=income_count,
            expense_invoice_count=expense_count,
        )

    async def _calculate_skonto_impact(
        self,
        db: AsyncSession,
        user_id: UUID,
        company_id: Optional[UUID],
        reference_date: date,
        days_ahead: int,
    ) -> SkontoImpact:
        """Berechne Skonto-Auswirkungen auf Cash-Flow."""
        end_date = reference_date + timedelta(days=days_ahead)

        # Verbindlichkeiten mit Skonto
        query = select(InvoiceTracking).where(
            and_(
                InvoiceTracking.company_id == company_id if company_id else True,
                is_incoming_invoice(),
                InvoiceTracking.paid_at.is_(None),
                InvoiceTracking.skonto_percentage.isnot(None),
                InvoiceTracking.skonto_percentage > 0,
                InvoiceTracking.skonto_deadline.isnot(None),
                InvoiceTracking.skonto_deadline >= reference_date,
                InvoiceTracking.skonto_deadline <= end_date,
            )
        )

        result = await db.execute(query)
        invoices = result.scalars().all()

        total_savings = Decimal("0.00")
        for inv in invoices:
            amount = inv.outstanding_amount or inv.amount or Decimal("0.00")
            skonto_pct = Decimal(str(inv.skonto_percentage or 0)) / 100
            saving = amount * skonto_pct
            total_savings += saving

        return SkontoImpact(
            invoice_count=len(invoices),
            potential_savings=total_savings,
            deadline_expense_impact=-total_savings,  # Weniger Ausgaben
            deadline_income_impact=Decimal("0.00"),
        )

    def _check_liquidity_risk(
        self,
        forecast_30: PeriodForecast,
        forecast_60: PeriodForecast,
        forecast_90: PeriodForecast,
        current_balance: Decimal,
    ) -> Optional[str]:
        """Prüfe auf Liquiditaetsrisiken."""
        # Kritisch: Negativer Saldo erwartet
        if forecast_30.ending_balance < Decimal("-1000"):
            return "Kritisch: Negativer Saldo in den nächsten 30 Tagen erwartet"

        if forecast_60.ending_balance < Decimal("-1000"):
            return "Warnung: Negativer Saldo in den nächsten 60 Tagen möglich"

        # Stark sinkender Trend
        if forecast_90.ending_balance < current_balance * Decimal("0.5"):
            return "Hinweis: Liquiditaet sinkt um mehr als 50% in 90 Tagen"

        return None


# Singleton
_cash_flow_forecast_service: Optional[CashFlowForecastService] = None


def get_cash_flow_forecast_service() -> CashFlowForecastService:
    """Hole CashFlowForecastService Singleton."""
    global _cash_flow_forecast_service
    if _cash_flow_forecast_service is None:
        _cash_flow_forecast_service = CashFlowForecastService()
    return _cash_flow_forecast_service
