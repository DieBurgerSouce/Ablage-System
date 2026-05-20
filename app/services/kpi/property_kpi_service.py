"""Property KPI Service für Immobilien-Berechnungen.

Berechnet alle Immobilien-bezogenen KPIs:
- Bruttomietrendite
- Nettomietrendite
- ROI (Return on Investment)
- Cash-on-Cash Return
- Wertzuwachs
- DSCR (Debt Service Coverage Ratio)
- LTV (Loan-to-Value)

Enterprise-Features:
- Multi-Tenant Isolation via space_id
- Echte DB-Integration mit SQLAlchemy
- Automatisches Speichern der berechneten KPIs
"""

from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional
from uuid import UUID

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import PrivatProperty, PrivatRentalIncome, PrivatUtilityStatement, PrivatLoan
from app.core.safe_errors import safe_error_log

logger = structlog.get_logger(__name__)


@dataclass
class PropertyKPIResult:
    """Ergebnis der Property-KPI-Berechnung."""

    # Rendite-KPIs
    gross_yield: Decimal
    net_yield: Decimal

    # ROI-KPIs
    total_roi: Decimal
    annual_roi: Decimal
    cash_on_cash_return: Decimal

    # Wert-KPIs
    value_appreciation: Decimal
    value_appreciation_rate: Decimal

    # Finanzierungs-KPIs
    ltv_ratio: Decimal
    debt_service_coverage: Decimal

    # Kosten-KPIs
    expense_ratio: Decimal
    maintenance_reserve: Decimal


class PropertyKPIService:
    """Service für Immobilien-KPI-Berechnungen.

    Berechnet automatisch alle relevanten KPIs für Immobilien
    basierend auf Kaufpreis, aktuellem Wert, Mieteinnahmen und Kosten.

    WICHTIG: Multi-Tenant Isolation
    - Alle Abfragen filtern nach space_id
    - space_id MUSS bei calculate_all_kpis übergeben werden
    """

    def __init__(self, db: AsyncSession) -> None:
        """Initialisiert den Service.

        Args:
            db: Async Database Session
        """
        self.db = db

    async def calculate_all_kpis(
        self,
        property_id: UUID,
        space_id: UUID,
        persist: bool = True
    ) -> PropertyKPIResult:
        """Berechnet alle KPIs für eine Immobilie.

        Args:
            property_id: UUID der Immobilie
            space_id: UUID des Space (Multi-Tenant Isolation!)
            persist: Ob die KPIs in der DB gespeichert werden sollen

        Returns:
            PropertyKPIResult mit allen berechneten KPIs

        Raises:
            ValueError: Wenn Property nicht existiert oder nicht zum Space gehoert
        """
        property_data = await self._get_property(property_id, space_id)
        rental_income = await self._get_rental_income(property_id, space_id)
        expenses = await self._get_expenses(property_id, space_id)

        # Berechne alle KPIs
        current_value = property_data.current_value or Decimal("0")
        purchase_price = property_data.purchase_price or Decimal("0")

        result = PropertyKPIResult(
            gross_yield=self._calc_gross_yield(rental_income, current_value),
            net_yield=self._calc_net_yield(rental_income, expenses, current_value),
            total_roi=self._calc_total_roi(property_data),
            annual_roi=self._calc_annual_roi(property_data),
            cash_on_cash_return=self._calc_cash_on_cash(property_data, rental_income, expenses),
            value_appreciation=current_value - purchase_price,
            value_appreciation_rate=self._calc_appreciation_rate(property_data),
            ltv_ratio=self._calc_ltv_ratio(property_data),
            debt_service_coverage=self._calc_dscr(rental_income, property_data),
            expense_ratio=self._calc_expense_ratio(expenses, rental_income),
            maintenance_reserve=self._calc_maintenance_reserve(property_data),
        )

        # Persistiere KPIs in der DB wenn gewünscht
        if persist:
            await self._persist_kpis(property_data, result)

        logger.info(
            "property_kpis_calculated",
            property_id=str(property_id),
            space_id=str(space_id),
            gross_yield=float(result.gross_yield),
            net_yield=float(result.net_yield),
            persisted=persist
        )

        return result

    async def _persist_kpis(
        self,
        property_data: PrivatProperty,
        result: PropertyKPIResult
    ) -> None:
        """Speichert berechnete KPIs in der Datenbank.

        Args:
            property_data: Die Property-Entität
            result: Die berechneten KPIs
        """
        property_data.calculated_yield = result.gross_yield
        property_data.calculated_net_yield = result.net_yield
        property_data.value_appreciation = result.value_appreciation
        property_data.value_appreciation_rate = result.value_appreciation_rate
        property_data.calculated_roi = result.total_roi
        property_data.annual_roi = result.annual_roi
        property_data.last_kpi_calculation = datetime.now(timezone.utc)

        await self.db.commit()

    def _calc_gross_yield(self, monthly_income: Decimal, property_value: Decimal) -> Decimal:
        """Berechnet die Bruttomietrendite.

        Formel: (Jahresmiete / Immobilienwert) * 100

        Args:
            monthly_income: Monatliche Mieteinnahmen
            property_value: Aktueller Immobilienwert

        Returns:
            Bruttomietrendite in Prozent
        """
        if property_value <= 0:
            return Decimal("0")
        annual_income = monthly_income * 12
        result = (annual_income / property_value) * 100
        return result.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    def _calc_net_yield(
        self,
        monthly_income: Decimal,
        monthly_expenses: Decimal,
        property_value: Decimal
    ) -> Decimal:
        """Berechnet die Nettomietrendite.

        Formel: ((Jahresmiete - Jahreskosten) / Immobilienwert) * 100

        Args:
            monthly_income: Monatliche Mieteinnahmen
            monthly_expenses: Monatliche Kosten
            property_value: Aktueller Immobilienwert

        Returns:
            Nettomietrendite in Prozent
        """
        if property_value <= 0:
            return Decimal("0")
        annual_net = (monthly_income - monthly_expenses) * 12
        result = (annual_net / property_value) * 100
        return result.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    def _calc_total_roi(self, property_data: PrivatProperty) -> Decimal:
        """Berechnet den Gesamt-ROI seit Kauf.

        ROI = (Aktueller Wert - Kaufpreis + Mieteinnahmen - Kosten) / Kaufpreis * 100
        """
        purchase_price = property_data.purchase_price or Decimal("0")
        current_value = property_data.current_value or Decimal("0")

        if purchase_price <= 0:
            return Decimal("0")

        gain = current_value - purchase_price
        result = (gain / purchase_price) * 100
        return result.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    def _calc_annual_roi(self, property_data: PrivatProperty) -> Decimal:
        """Berechnet den annualisierten ROI.

        Teilt den Gesamt-ROI durch die Anzahl der Jahre seit Kauf.
        """
        purchase_price = property_data.purchase_price or Decimal("0")
        if purchase_price <= 0:
            return Decimal("0")

        total_roi = self._calc_total_roi(property_data)
        purchase_date = property_data.purchase_date
        if not purchase_date:
            return total_roi

        years = self._calc_years_owned(purchase_date)

        if years <= 0:
            return total_roi

        return (total_roi / Decimal(str(years))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    def _calc_cash_on_cash(
        self,
        property_data: PrivatProperty,
        monthly_income: Decimal,
        monthly_expenses: Decimal
    ) -> Decimal:
        """Berechnet den Cash-on-Cash Return.

        Cash-on-Cash = Jährlicher Cashflow / Eingesetztes Eigenkapital * 100
        """
        purchase_price = property_data.purchase_price or Decimal("0")

        # Hole Kreditbetrag aus verknüpftem Loan falls vorhanden
        loan_amount = Decimal("0")
        monthly_payment = Decimal("0")
        if property_data.loan:
            loan_amount = property_data.loan.principal_amount or Decimal("0")
            monthly_payment = property_data.loan.monthly_payment or Decimal("0")

        equity = purchase_price - loan_amount
        if equity <= 0:
            return Decimal("0")

        annual_cashflow = (monthly_income - monthly_expenses) * 12

        # Kreditzahlung abziehen falls vorhanden
        annual_cashflow -= monthly_payment * 12

        result = (annual_cashflow / equity) * 100
        return result.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    def _calc_appreciation_rate(self, property_data: PrivatProperty) -> Decimal:
        """Berechnet die jährliche Wertsteigerungsrate."""
        purchase_price = property_data.purchase_price or Decimal("0")
        current_value = property_data.current_value or Decimal("0")

        if purchase_price <= 0:
            return Decimal("0")

        purchase_date = property_data.purchase_date
        if not purchase_date:
            return Decimal("0")

        years = self._calc_years_owned(purchase_date)
        if years <= 0:
            return Decimal("0")

        appreciation = current_value - purchase_price
        annual_rate = (appreciation / purchase_price / Decimal(str(years))) * 100
        return annual_rate.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    def _calc_ltv_ratio(self, property_data: PrivatProperty) -> Decimal:
        """Berechnet das Loan-to-Value Verhältnis.

        LTV = Restschuld / Aktueller Wert * 100
        """
        current_value = property_data.current_value or Decimal("0")
        if current_value <= 0:
            return Decimal("100")  # Maximales Risiko

        # Hole Restschuld aus verknüpftem Loan
        remaining_loan = Decimal("0")
        if property_data.loan:
            remaining_loan = property_data.loan.current_balance or Decimal("0")

        result = (remaining_loan / current_value) * 100
        return result.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    def _calc_dscr(self, monthly_income: Decimal, property_data: PrivatProperty) -> Decimal:
        """Berechnet die Debt Service Coverage Ratio.

        DSCR = NOI / Jährlicher Schuldendienst
        Ein Wert > 1.25 wird als gesund angesehen.
        """
        # Hole monatliche Zahlung aus verknüpftem Loan
        monthly_payment = Decimal("0")
        if property_data.loan:
            monthly_payment = property_data.loan.monthly_payment or Decimal("0")

        if monthly_payment <= 0:
            return Decimal("999.00")  # Keine Schulden = perfekt

        annual_noi = monthly_income * 12
        annual_debt_service = monthly_payment * 12

        result = annual_noi / annual_debt_service
        return result.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    def _calc_expense_ratio(self, monthly_expenses: Decimal, monthly_income: Decimal) -> Decimal:
        """Berechnet das Kosten-zu-Einnahmen-Verhältnis."""
        if monthly_income <= 0:
            return Decimal("100")

        result = (monthly_expenses / monthly_income) * 100
        return result.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    def _calc_maintenance_reserve(self, property_data: PrivatProperty) -> Decimal:
        """Empfohlene Instandhaltungsrücklage pro Jahr.

        Typisch: 1-2% des Immobilienwerts pro Jahr
        """
        current_value = property_data.current_value or Decimal("0")
        rate = Decimal("0.015")  # 1.5%
        return (current_value * rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    def _calc_years_owned(self, purchase_date: date) -> float:
        """Berechnet die Anzahl Jahre seit Kauf."""
        today = date.today()
        delta = today - purchase_date
        return delta.days / 365.25

    async def _get_property(self, property_id: UUID, space_id: UUID) -> PrivatProperty:
        """Laedt Property aus der Datenbank mit Multi-Tenant-Prüfung.

        Args:
            property_id: UUID der Immobilie
            space_id: UUID des Space (Multi-Tenant Isolation!)

        Returns:
            PrivatProperty Entität

        Raises:
            ValueError: Wenn Property nicht existiert oder nicht zum Space gehoert
        """
        stmt = (
            select(PrivatProperty)
            .options(selectinload(PrivatProperty.loan))  # Eager load loan
            .where(
                PrivatProperty.id == property_id,
                PrivatProperty.space_id == space_id,  # Multi-Tenant Security!
                PrivatProperty.deleted_at.is_(None)
            )
        )
        result = await self.db.execute(stmt)
        property_data = result.scalar_one_or_none()

        if not property_data:
            logger.warning(
                "property_not_found_or_access_denied",
                property_id=str(property_id),
                space_id=str(space_id)
            )
            raise ValueError(
                f"Immobilie {property_id} nicht gefunden oder Zugriff verweigert"
            )

        return property_data

    async def _get_rental_income(self, property_id: UUID, space_id: UUID) -> Decimal:
        """Berechnet durchschnittliche monatliche Mieteinnahmen der letzten 12 Monate.

        Args:
            property_id: UUID der Immobilie
            space_id: UUID des Space (für Audit-Log)

        Returns:
            Durchschnittliche monatliche Mieteinnahmen als Decimal
        """
        # Berechne Durchschnitt der letzten 12 Monate
        twelve_months_ago = date.today().replace(
            year=date.today().year - 1
        )

        stmt = (
            select(func.coalesce(func.avg(PrivatRentalIncome.amount), 0))
            .join(PrivatProperty, PrivatRentalIncome.property_id == PrivatProperty.id)
            .where(
                PrivatRentalIncome.property_id == property_id,
                PrivatProperty.space_id == space_id,  # Multi-Tenant Join-Prüfung
                PrivatRentalIncome.payment_date >= twelve_months_ago,
                PrivatRentalIncome.payment_type == "rent"
            )
        )
        result = await self.db.execute(stmt)
        avg_income = result.scalar() or Decimal("0")

        return Decimal(str(avg_income)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    async def _get_expenses(self, property_id: UUID, space_id: UUID) -> Decimal:
        """Berechnet durchschnittliche monatliche Kosten (Nebenkosten).

        Verwendet die letzten Nebenkostenabrechnungen um durchschnittliche
        monatliche Kosten zu berechnen.

        Args:
            property_id: UUID der Immobilie
            space_id: UUID des Space (für Audit-Log)

        Returns:
            Durchschnittliche monatliche Kosten als Decimal
        """
        # Hole letzte Nebenkostenabrechnung
        stmt = (
            select(PrivatUtilityStatement)
            .join(PrivatProperty, PrivatUtilityStatement.property_id == PrivatProperty.id)
            .where(
                PrivatUtilityStatement.property_id == property_id,
                PrivatProperty.space_id == space_id  # Multi-Tenant Join-Prüfung
            )
            .order_by(PrivatUtilityStatement.period_end.desc())
            .limit(1)
        )
        result = await self.db.execute(stmt)
        last_statement = result.scalar_one_or_none()

        if not last_statement:
            return Decimal("0")

        # Berechne Monate im Abrechnungszeitraum
        period_months = (
            (last_statement.period_end.year - last_statement.period_start.year) * 12 +
            (last_statement.period_end.month - last_statement.period_start.month) + 1
        )

        if period_months <= 0:
            period_months = 12  # Fallback auf 1 Jahr

        monthly_costs = last_statement.total_costs / period_months
        return monthly_costs.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    async def calculate_all_properties_for_space(
        self,
        space_id: UUID,
        persist: bool = True
    ) -> dict[UUID, PropertyKPIResult]:
        """Berechnet KPIs für alle Properties eines Space.

        Args:
            space_id: UUID des Space
            persist: Ob die KPIs in der DB gespeichert werden sollen

        Returns:
            Dict mit Property-IDs als Keys und KPI-Results als Values
        """
        stmt = (
            select(PrivatProperty.id)
            .where(
                PrivatProperty.space_id == space_id,
                PrivatProperty.deleted_at.is_(None),
                PrivatProperty.is_active.is_(True)
            )
        )
        result = await self.db.execute(stmt)
        property_ids = [row[0] for row in result.all()]

        results: dict[UUID, PropertyKPIResult] = {}
        for property_id in property_ids:
            try:
                kpi_result = await self.calculate_all_kpis(
                    property_id=property_id,
                    space_id=space_id,
                    persist=persist
                )
                results[property_id] = kpi_result
            except ValueError as e:
                logger.warning(
                    "property_kpi_calculation_failed",
                    property_id=str(property_id),
                    **safe_error_log(e)
                )
                continue

        logger.info(
            "space_property_kpis_calculated",
            space_id=str(space_id),
            total_properties=len(property_ids),
            successful=len(results)
        )

        return results
