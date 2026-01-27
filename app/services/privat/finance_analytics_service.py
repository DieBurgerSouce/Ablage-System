"""Finance Analytics Service.

Intelligente Finanz-Analysen fuer das Privat-Modul:
- Monatliche Trends (Einnahmen, Ausgaben, Netto)
- Jahr-zu-Jahr Vergleiche
- Wiederkehrende Zahlungen erkennen
- Cash-Flow Prognosen
"""

import threading
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

import structlog
from sqlalchemy import and_, extract, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    PrivatInsurance,
    PrivatLoan,
    PrivatProperty,
    PrivatSpace,
    PrivatVehicle,
)

logger = structlog.get_logger(__name__)


# ============================================================================
# Data Classes
# ============================================================================


@dataclass
class MonthlyTrend:
    """Monatliche Finanzdaten."""

    year: int
    month: int
    income: Decimal = Decimal("0")
    expenses: Decimal = Decimal("0")
    net: Decimal = Decimal("0")
    income_sources: Dict[str, Decimal] = field(default_factory=dict)
    expense_categories: Dict[str, Decimal] = field(default_factory=dict)


@dataclass
class YoYComparison:
    """Jahr-zu-Jahr Vergleich."""

    current_year: int
    previous_year: int
    current_income: Decimal = Decimal("0")
    previous_income: Decimal = Decimal("0")
    income_change: Decimal = Decimal("0")
    income_change_percent: float = 0.0
    current_expenses: Decimal = Decimal("0")
    previous_expenses: Decimal = Decimal("0")
    expenses_change: Decimal = Decimal("0")
    expenses_change_percent: float = 0.0
    current_net: Decimal = Decimal("0")
    previous_net: Decimal = Decimal("0")
    net_change: Decimal = Decimal("0")


@dataclass
class RecurringPayment:
    """Erkannte wiederkehrende Zahlung."""

    name: str
    expected_amount: Decimal
    frequency: str  # monthly, quarterly, yearly
    expected_day: int
    source_type: str  # insurance, loan, property, vehicle
    source_id: UUID
    confidence: float = 0.0
    is_income: bool = False
    next_occurrence: Optional[date] = None


@dataclass
class CashFlowPrediction:
    """Cash-Flow Vorhersage fuer einen Monat."""

    year: int
    month: int
    predicted_income: Decimal = Decimal("0")
    predicted_expenses: Decimal = Decimal("0")
    predicted_net: Decimal = Decimal("0")
    recurring_income: List[RecurringPayment] = field(default_factory=list)
    recurring_expenses: List[RecurringPayment] = field(default_factory=list)
    confidence: float = 0.0


@dataclass
class FinanceAnalyticsResult:
    """Gesamtergebnis der Finanz-Analyse."""

    space_id: UUID
    analysis_date: date
    monthly_trends: List[MonthlyTrend] = field(default_factory=list)
    yoy_comparisons: List[YoYComparison] = field(default_factory=list)
    recurring_payments: List[RecurringPayment] = field(default_factory=list)
    cash_flow_predictions: List[CashFlowPrediction] = field(default_factory=list)
    total_assets_value: Decimal = Decimal("0")
    total_liabilities: Decimal = Decimal("0")
    net_worth: Decimal = Decimal("0")


# ============================================================================
# Finance Analytics Service
# ============================================================================


class FinanceAnalyticsService:
    """Service fuer intelligente Finanz-Analysen im Privat-Modul.

    Analysiert:
    - Immobilien-Einnahmen (Mieteinnahmen) und -Kosten
    - Versicherungspraemien
    - Kredit-Tilgungen und Zinsen
    - Fahrzeug-Kosten
    """

    def __init__(self) -> None:
        """Initialisiert den Service."""
        pass

    async def get_monthly_trends(
        self,
        db: AsyncSession,
        space_id: UUID,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        months: int = 12,
    ) -> List[MonthlyTrend]:
        """Berechnet monatliche Finanz-Trends.

        Args:
            db: Datenbank-Session
            space_id: ID des PrivatSpace
            start_date: Optionales Startdatum
            end_date: Optionales Enddatum
            months: Anzahl Monate (wenn keine Daten angegeben)

        Returns:
            Liste von MonthlyTrend-Objekten
        """
        if not end_date:
            end_date = date.today()
        if not start_date:
            start_date = end_date - timedelta(days=months * 30)

        logger.info(
            "finance_trends_start",
            space_id=str(space_id),
            start_date=start_date.isoformat(),
            end_date=end_date.isoformat(),
        )

        trends: Dict[Tuple[int, int], MonthlyTrend] = {}

        # Initialisiere alle Monate
        current = start_date.replace(day=1)
        while current <= end_date:
            key = (current.year, current.month)
            trends[key] = MonthlyTrend(year=current.year, month=current.month)
            if current.month == 12:
                current = current.replace(year=current.year + 1, month=1)
            else:
                current = current.replace(month=current.month + 1)

        # Immobilien-Einnahmen (monatliche Miete)
        props = await db.execute(
            select(PrivatProperty).where(
                and_(
                    PrivatProperty.space_id == space_id,
                    PrivatProperty.is_rented == True,
                    PrivatProperty.deleted_at.is_(None),
                )
            )
        )
        for prop in props.scalars():
            if prop.monthly_rent:
                # Miete fuer alle Monate im Zeitraum
                for key in trends.keys():
                    trend = trends[key]
                    rent = Decimal(str(prop.monthly_rent))
                    trend.income += rent
                    if "mieteinnahmen" not in trend.income_sources:
                        trend.income_sources["mieteinnahmen"] = Decimal("0")
                    trend.income_sources["mieteinnahmen"] += rent

        # Versicherungspraemien (Ausgaben)
        insurances = await db.execute(
            select(PrivatInsurance).where(
                and_(
                    PrivatInsurance.space_id == space_id,
                    PrivatInsurance.deleted_at.is_(None),
                )
            )
        )
        for ins in insurances.scalars():
            if ins.premium_amount and ins.payment_interval:
                monthly_premium = self._calculate_monthly_amount(
                    Decimal(str(ins.premium_amount)),
                    ins.payment_interval,
                )
                for key in trends.keys():
                    trend = trends[key]
                    trend.expenses += monthly_premium
                    category = f"versicherung_{ins.insurance_type}"
                    if category not in trend.expense_categories:
                        trend.expense_categories[category] = Decimal("0")
                    trend.expense_categories[category] += monthly_premium

        # Kredit-Raten (Ausgaben)
        loans = await db.execute(
            select(PrivatLoan).where(
                and_(
                    PrivatLoan.space_id == space_id,
                    PrivatLoan.is_active == True,
                    PrivatLoan.deleted_at.is_(None),
                )
            )
        )
        for loan in loans.scalars():
            if loan.monthly_payment:
                monthly = Decimal(str(loan.monthly_payment))
                for key in trends.keys():
                    year, month = key
                    # Pruefen ob Kredit in diesem Monat aktiv
                    month_start = date(year, month, 1)
                    if loan.start_date and month_start < loan.start_date:
                        continue
                    if loan.end_date and month_start > loan.end_date:
                        continue

                    trend = trends[key]
                    trend.expenses += monthly
                    category = f"kredit_{loan.loan_type}"
                    if category not in trend.expense_categories:
                        trend.expense_categories[category] = Decimal("0")
                    trend.expense_categories[category] += monthly

        # Fahrzeug-Kosten (geschaetzt)
        vehicles = await db.execute(
            select(PrivatVehicle).where(
                and_(
                    PrivatVehicle.space_id == space_id,
                    PrivatVehicle.status == "active",
                    PrivatVehicle.deleted_at.is_(None),
                )
            )
        )
        for vehicle in vehicles.scalars():
            # Geschaetzte monatliche Kosten (Steuer/12 + Versicherung/12)
            monthly_cost = Decimal("0")
            if vehicle.annual_tax:
                monthly_cost += Decimal(str(vehicle.annual_tax)) / 12
            if vehicle.insurance_cost:
                monthly_cost += Decimal(str(vehicle.insurance_cost)) / 12

            if monthly_cost > 0:
                for key in trends.keys():
                    trend = trends[key]
                    trend.expenses += monthly_cost
                    if "fahrzeugkosten" not in trend.expense_categories:
                        trend.expense_categories["fahrzeugkosten"] = Decimal("0")
                    trend.expense_categories["fahrzeugkosten"] += monthly_cost

        # Netto berechnen
        for trend in trends.values():
            trend.net = trend.income - trend.expenses

        result = sorted(trends.values(), key=lambda t: (t.year, t.month))

        logger.info(
            "finance_trends_complete",
            space_id=str(space_id),
            months_analyzed=len(result),
        )

        return result

    async def get_yoy_comparison(
        self,
        db: AsyncSession,
        space_id: UUID,
        current_year: Optional[int] = None,
    ) -> List[YoYComparison]:
        """Erstellt Jahr-zu-Jahr Vergleiche.

        Args:
            db: Datenbank-Session
            space_id: ID des PrivatSpace
            current_year: Optionales aktuelles Jahr

        Returns:
            Liste von YoYComparison-Objekten
        """
        if not current_year:
            current_year = date.today().year

        comparisons: List[YoYComparison] = []

        # Vergleich der letzten 3 Jahre
        for year in range(current_year, current_year - 3, -1):
            current_trends = await self.get_monthly_trends(
                db=db,
                space_id=space_id,
                start_date=date(year, 1, 1),
                end_date=date(year, 12, 31),
            )

            previous_trends = await self.get_monthly_trends(
                db=db,
                space_id=space_id,
                start_date=date(year - 1, 1, 1),
                end_date=date(year - 1, 12, 31),
            )

            current_income = sum(t.income for t in current_trends)
            current_expenses = sum(t.expenses for t in current_trends)
            previous_income = sum(t.income for t in previous_trends)
            previous_expenses = sum(t.expenses for t in previous_trends)

            comparison = YoYComparison(
                current_year=year,
                previous_year=year - 1,
                current_income=current_income,
                previous_income=previous_income,
                income_change=current_income - previous_income,
                income_change_percent=(
                    float((current_income - previous_income) / previous_income * 100)
                    if previous_income
                    else 0.0
                ),
                current_expenses=current_expenses,
                previous_expenses=previous_expenses,
                expenses_change=current_expenses - previous_expenses,
                expenses_change_percent=(
                    float((current_expenses - previous_expenses) / previous_expenses * 100)
                    if previous_expenses
                    else 0.0
                ),
                current_net=current_income - current_expenses,
                previous_net=previous_income - previous_expenses,
                net_change=(current_income - current_expenses)
                - (previous_income - previous_expenses),
            )

            comparisons.append(comparison)

        return comparisons

    async def detect_recurring_payments(
        self,
        db: AsyncSession,
        space_id: UUID,
    ) -> List[RecurringPayment]:
        """Erkennt wiederkehrende Zahlungen.

        Args:
            db: Datenbank-Session
            space_id: ID des PrivatSpace

        Returns:
            Liste von RecurringPayment-Objekten
        """
        recurring: List[RecurringPayment] = []
        today = date.today()

        # Mieteinnahmen (monatlich)
        props = await db.execute(
            select(PrivatProperty).where(
                and_(
                    PrivatProperty.space_id == space_id,
                    PrivatProperty.is_rented == True,
                    PrivatProperty.monthly_rent.isnot(None),
                    PrivatProperty.deleted_at.is_(None),
                )
            )
        )
        for prop in props.scalars():
            payment = RecurringPayment(
                name=f"Miete: {prop.address or prop.name}",
                expected_amount=Decimal(str(prop.monthly_rent)),
                frequency="monthly",
                expected_day=1,  # Typischerweise am Monatsanfang
                source_type="property",
                source_id=prop.id,
                confidence=0.95,
                is_income=True,
                next_occurrence=self._next_monthly_occurrence(today, 1),
            )
            recurring.append(payment)

        # Versicherungspraemien
        insurances = await db.execute(
            select(PrivatInsurance).where(
                and_(
                    PrivatInsurance.space_id == space_id,
                    PrivatInsurance.premium_amount.isnot(None),
                    PrivatInsurance.deleted_at.is_(None),
                )
            )
        )
        for ins in insurances.scalars():
            frequency = self._map_payment_interval(ins.payment_interval)
            if frequency:
                payment = RecurringPayment(
                    name=f"Versicherung: {ins.insurance_name or ins.insurance_type}",
                    expected_amount=Decimal(str(ins.premium_amount)),
                    frequency=frequency,
                    expected_day=ins.payment_day or 1,
                    source_type="insurance",
                    source_id=ins.id,
                    confidence=0.9,
                    is_income=False,
                    next_occurrence=self._next_occurrence(today, frequency, ins.payment_day or 1),
                )
                recurring.append(payment)

        # Kreditraten
        loans = await db.execute(
            select(PrivatLoan).where(
                and_(
                    PrivatLoan.space_id == space_id,
                    PrivatLoan.monthly_payment.isnot(None),
                    PrivatLoan.is_active == True,
                    PrivatLoan.deleted_at.is_(None),
                )
            )
        )
        for loan in loans.scalars():
            payment = RecurringPayment(
                name=f"Kredit: {loan.loan_name or loan.loan_type}",
                expected_amount=Decimal(str(loan.monthly_payment)),
                frequency="monthly",
                expected_day=loan.payment_day or 15,
                source_type="loan",
                source_id=loan.id,
                confidence=0.95,
                is_income=False,
                next_occurrence=self._next_monthly_occurrence(
                    today, loan.payment_day or 15
                ),
            )
            recurring.append(payment)

        # Fahrzeug-Kosten (jaehrlich: Steuer, Versicherung)
        vehicles = await db.execute(
            select(PrivatVehicle).where(
                and_(
                    PrivatVehicle.space_id == space_id,
                    PrivatVehicle.status == "active",
                    PrivatVehicle.deleted_at.is_(None),
                )
            )
        )
        for vehicle in vehicles.scalars():
            if vehicle.annual_tax:
                payment = RecurringPayment(
                    name=f"KFZ-Steuer: {vehicle.brand} {vehicle.model}",
                    expected_amount=Decimal(str(vehicle.annual_tax)),
                    frequency="yearly",
                    expected_day=1,  # Januar
                    source_type="vehicle",
                    source_id=vehicle.id,
                    confidence=0.85,
                    is_income=False,
                    next_occurrence=date(today.year + 1, 1, 1)
                    if today.month > 6
                    else date(today.year, 1, 1),
                )
                recurring.append(payment)

        logger.info(
            "recurring_payments_detected",
            space_id=str(space_id),
            total_recurring=len(recurring),
            income_count=len([p for p in recurring if p.is_income]),
            expense_count=len([p for p in recurring if not p.is_income]),
        )

        return recurring

    async def predict_cash_flow(
        self,
        db: AsyncSession,
        space_id: UUID,
        months_ahead: int = 6,
    ) -> List[CashFlowPrediction]:
        """Erstellt Cash-Flow Prognosen.

        Args:
            db: Datenbank-Session
            space_id: ID des PrivatSpace
            months_ahead: Anzahl Monate fuer Prognose

        Returns:
            Liste von CashFlowPrediction-Objekten
        """
        # Wiederkehrende Zahlungen holen
        recurring = await self.detect_recurring_payments(db, space_id)

        predictions: List[CashFlowPrediction] = []
        today = date.today()

        for i in range(months_ahead):
            # Zielmonat berechnen
            target_month = today.month + i
            target_year = today.year
            while target_month > 12:
                target_month -= 12
                target_year += 1

            # Zahlungen fuer diesen Monat filtern
            month_income: List[RecurringPayment] = []
            month_expenses: List[RecurringPayment] = []
            total_income = Decimal("0")
            total_expenses = Decimal("0")

            for payment in recurring:
                if self._is_payment_due(payment, target_year, target_month):
                    if payment.is_income:
                        month_income.append(payment)
                        total_income += payment.expected_amount
                    else:
                        month_expenses.append(payment)
                        total_expenses += payment.expected_amount

            prediction = CashFlowPrediction(
                year=target_year,
                month=target_month,
                predicted_income=total_income,
                predicted_expenses=total_expenses,
                predicted_net=total_income - total_expenses,
                recurring_income=month_income,
                recurring_expenses=month_expenses,
                confidence=0.85 if recurring else 0.3,
            )

            predictions.append(prediction)

        logger.info(
            "cash_flow_predicted",
            space_id=str(space_id),
            months_ahead=months_ahead,
            total_predictions=len(predictions),
        )

        return predictions

    async def get_full_analysis(
        self,
        db: AsyncSession,
        space_id: UUID,
        months_history: int = 12,
        months_forecast: int = 6,
    ) -> FinanceAnalyticsResult:
        """Erstellt vollstaendige Finanz-Analyse.

        Args:
            db: Datenbank-Session
            space_id: ID des PrivatSpace
            months_history: Monate fuer Trend-Analyse
            months_forecast: Monate fuer Cash-Flow Prognose

        Returns:
            FinanceAnalyticsResult mit allen Analysen
        """
        logger.info(
            "full_analysis_start",
            space_id=str(space_id),
            months_history=months_history,
            months_forecast=months_forecast,
        )

        # Alle Analysen parallel ausfuehren
        trends = await self.get_monthly_trends(
            db, space_id, months=months_history
        )
        yoy = await self.get_yoy_comparison(db, space_id)
        recurring = await self.detect_recurring_payments(db, space_id)
        predictions = await self.predict_cash_flow(
            db, space_id, months_ahead=months_forecast
        )

        # Vermoegensberechnung
        total_assets = Decimal("0")
        total_liabilities = Decimal("0")

        # Immobilienwerte
        props = await db.execute(
            select(PrivatProperty).where(
                and_(
                    PrivatProperty.space_id == space_id,
                    PrivatProperty.deleted_at.is_(None),
                )
            )
        )
        for prop in props.scalars():
            if prop.current_value:
                total_assets += Decimal(str(prop.current_value))
            elif prop.purchase_price:
                total_assets += Decimal(str(prop.purchase_price))

        # Fahrzeugwerte
        vehicles = await db.execute(
            select(PrivatVehicle).where(
                and_(
                    PrivatVehicle.space_id == space_id,
                    PrivatVehicle.deleted_at.is_(None),
                )
            )
        )
        for vehicle in vehicles.scalars():
            if vehicle.current_estimated_value:
                total_assets += Decimal(str(vehicle.current_estimated_value))
            elif vehicle.purchase_price:
                # Grobe Schaetzung: 50% nach Kauf
                total_assets += Decimal(str(vehicle.purchase_price)) * Decimal("0.5")

        # Kredite als Verbindlichkeiten
        loans = await db.execute(
            select(PrivatLoan).where(
                and_(
                    PrivatLoan.space_id == space_id,
                    PrivatLoan.is_active == True,
                    PrivatLoan.deleted_at.is_(None),
                )
            )
        )
        for loan in loans.scalars():
            if loan.remaining_amount:
                total_liabilities += Decimal(str(loan.remaining_amount))
            elif loan.loan_amount:
                total_liabilities += Decimal(str(loan.loan_amount))

        result = FinanceAnalyticsResult(
            space_id=space_id,
            analysis_date=date.today(),
            monthly_trends=trends,
            yoy_comparisons=yoy,
            recurring_payments=recurring,
            cash_flow_predictions=predictions,
            total_assets_value=total_assets,
            total_liabilities=total_liabilities,
            net_worth=total_assets - total_liabilities,
        )

        logger.info(
            "full_analysis_complete",
            space_id=str(space_id),
            net_worth=float(result.net_worth),
            recurring_count=len(recurring),
        )

        return result

    # ========================================================================
    # Hilfsmethoden
    # ========================================================================

    def _calculate_monthly_amount(
        self,
        amount: Decimal,
        interval: str,
    ) -> Decimal:
        """Berechnet monatlichen Betrag aus Intervall.

        Args:
            amount: Gesamtbetrag
            interval: Zahlungsintervall

        Returns:
            Monatlicher Betrag
        """
        interval_lower = (interval or "").lower()

        if "monat" in interval_lower or "monthly" in interval_lower:
            return amount
        elif "quartal" in interval_lower or "quarterly" in interval_lower:
            return amount / 3
        elif "halbjaehr" in interval_lower or "semi" in interval_lower:
            return amount / 6
        elif "jaehr" in interval_lower or "yearly" in interval_lower or "annual" in interval_lower:
            return amount / 12
        else:
            return amount  # Default: monatlich

    def _map_payment_interval(self, interval: Optional[str]) -> Optional[str]:
        """Mappt Zahlungsintervall zu Standard-Frequenz.

        Args:
            interval: Roher Intervall-String

        Returns:
            Standard-Frequenz oder None
        """
        if not interval:
            return None

        interval_lower = interval.lower()

        if "monat" in interval_lower or "monthly" in interval_lower:
            return "monthly"
        elif "quartal" in interval_lower or "quarterly" in interval_lower:
            return "quarterly"
        elif "halbjaehr" in interval_lower or "semi" in interval_lower:
            return "half-yearly"
        elif "jaehr" in interval_lower or "yearly" in interval_lower or "annual" in interval_lower:
            return "yearly"

        return "monthly"  # Default

    def _next_monthly_occurrence(self, from_date: date, day: int) -> date:
        """Berechnet naechstes monatliches Vorkommen.

        Args:
            from_date: Ausgangsdatum
            day: Tag des Monats

        Returns:
            Naechstes Vorkommen
        """
        # Versuche im aktuellen Monat
        try:
            target = from_date.replace(day=min(day, 28))
            if target > from_date:
                return target
        except ValueError as e:
            logger.debug("monthly_occurrence_current_month_failed", error_type=type(e).__name__)

        # Naechster Monat
        if from_date.month == 12:
            next_month = from_date.replace(year=from_date.year + 1, month=1, day=1)
        else:
            next_month = from_date.replace(month=from_date.month + 1, day=1)

        try:
            return next_month.replace(day=min(day, 28))
        except ValueError:
            return next_month

    def _next_occurrence(
        self,
        from_date: date,
        frequency: str,
        day: int,
    ) -> date:
        """Berechnet naechstes Vorkommen basierend auf Frequenz.

        Args:
            from_date: Ausgangsdatum
            frequency: Frequenz (monthly, quarterly, yearly)
            day: Tag des Monats/Quartals

        Returns:
            Naechstes Vorkommen
        """
        if frequency == "monthly":
            return self._next_monthly_occurrence(from_date, day)

        elif frequency == "quarterly":
            # Naechster Quartalsmonat (1, 4, 7, 10)
            quarter_months = [1, 4, 7, 10]
            for qm in quarter_months:
                if qm >= from_date.month:
                    try:
                        target = from_date.replace(month=qm, day=min(day, 28))
                        if target > from_date:
                            return target
                    except ValueError as e:
                        logger.debug(
                            "quarterly_date_calculation_failed",
                            error_type=type(e).__name__,
                        )
            # Naechstes Jahr
            return from_date.replace(year=from_date.year + 1, month=1, day=min(day, 28))

        elif frequency == "yearly":
            target = from_date.replace(month=1, day=min(day, 28))
            if target <= from_date:
                target = target.replace(year=target.year + 1)
            return target

        return self._next_monthly_occurrence(from_date, day)

    def _is_payment_due(
        self,
        payment: RecurringPayment,
        year: int,
        month: int,
    ) -> bool:
        """Prueft ob Zahlung in einem Monat faellig ist.

        Args:
            payment: Wiederkehrende Zahlung
            year: Jahr
            month: Monat

        Returns:
            True wenn faellig
        """
        if payment.frequency == "monthly":
            return True

        elif payment.frequency == "quarterly":
            # Quartalsweise: Jan, Apr, Jul, Okt
            return month in [1, 4, 7, 10]

        elif payment.frequency == "half-yearly":
            # Halbjaehrlich: Jan, Jul
            return month in [1, 7]

        elif payment.frequency == "yearly":
            # Jaehrlich: Januar
            return month == 1

        return True


# ============================================================================
# Singleton Pattern
# ============================================================================

_finance_analytics_service: Optional[FinanceAnalyticsService] = None
_finance_analytics_service_lock = threading.Lock()


def get_finance_analytics_service() -> FinanceAnalyticsService:
    """Gibt die Singleton-Instanz des Finance Analytics Service zurueck.

    Returns:
        FinanceAnalyticsService Singleton-Instanz
    """
    global _finance_analytics_service

    if _finance_analytics_service is None:
        with _finance_analytics_service_lock:
            if _finance_analytics_service is None:
                _finance_analytics_service = FinanceAnalyticsService()

    return _finance_analytics_service
