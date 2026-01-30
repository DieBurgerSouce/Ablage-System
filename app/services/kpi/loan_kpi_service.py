"""Loan KPI Service fuer Kredit-Berechnungen.

Berechnet alle Kredit-bezogenen KPIs:
- Tilgungsplan (Amortization Schedule)
- Restschuld-Prognose
- Sondertilgungs-Auswirkungen
- Zinsbelastung

Enterprise Features:
- Multi-Tenant Security via space_id
- Echte DB-Integration mit SQLAlchemy
- KPI-Persistenz in DB
- Structured Logging
"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional
from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import PrivatLoan
from app.core.safe_errors import safe_error_log

logger = structlog.get_logger(__name__)


# Type alias fuer Loan-Optionen (vermeidet Any)
@dataclass
class LoanOption:
    """Eine Kreditoption fuer Vergleich."""

    name: str
    rate: Decimal
    term_months: int


@dataclass
class AmortizationEntry:
    """Ein Eintrag im Tilgungsplan."""

    month: int
    payment: Decimal
    principal: Decimal
    interest: Decimal
    balance: Decimal


@dataclass
class AmortizationSchedule:
    """Vollstaendiger Tilgungsplan."""

    schedule: list[AmortizationEntry]
    total_interest: Decimal
    total_payments: Decimal
    payoff_date: date
    remaining_months: int


@dataclass
class ExtraPaymentImpact:
    """Auswirkung einer Sondertilgung."""

    extra_monthly: Decimal
    months_saved: int
    interest_saved: Decimal
    new_payoff_date: date


@dataclass
class LoanComparison:
    """Vergleich verschiedener Kreditoptionen."""

    option_name: str
    monthly_payment: Decimal
    total_interest: Decimal
    payoff_months: int
    total_cost: Decimal


class LoanKPIService:
    """Service fuer Kredit-KPI-Berechnungen.

    Berechnet Tilgungsplaene, Restschuld-Prognosen und
    analysiert Auswirkungen von Sondertilgungen.
    """

    def __init__(self, db: AsyncSession) -> None:
        """Initialisiert den Service.

        Args:
            db: Async Database Session
        """
        self.db = db

    async def calculate_amortization_schedule(
        self,
        loan_id: UUID,
        space_id: UUID,
        persist: bool = True,
    ) -> AmortizationSchedule:
        """Berechnet den vollstaendigen Tilgungsplan.

        Args:
            loan_id: UUID des Kredits
            space_id: UUID des Space (Multi-Tenant Security!)
            persist: Ob KPIs in DB persistiert werden sollen

        Returns:
            AmortizationSchedule mit monatlichen Zahlungen

        Raises:
            ValueError: Wenn Kredit nicht gefunden oder Zugriff verweigert
        """
        logger.info(
            "loan_amortization_calculation_started",
            loan_id=str(loan_id),
            space_id=str(space_id),
        )

        loan = await self._get_loan(loan_id, space_id)

        # Validierung der benoetigten Felder
        if not loan.principal_amount or loan.principal_amount <= 0:
            raise ValueError(f"Kredit {loan_id} hat keine gueltige Kreditsumme")
        if not loan.monthly_payment or loan.monthly_payment <= 0:
            raise ValueError(f"Kredit {loan_id} hat keine gueltige monatliche Rate")

        # Verwende aktuellen Saldo wenn vorhanden, sonst Ursprungssumme
        principal = Decimal(str(loan.current_balance or loan.principal_amount))
        annual_rate = Decimal(str(loan.interest_rate or 0))
        monthly_payment = Decimal(str(loan.monthly_payment))
        start_date = loan.start_date or date.today()

        result = self._generate_schedule(
            principal=principal,
            annual_rate=annual_rate,
            monthly_payment=monthly_payment,
            start_date=start_date,
        )

        if persist:
            await self._persist_amortization(loan, result)

        logger.info(
            "loan_amortization_calculation_completed",
            loan_id=str(loan_id),
            remaining_months=result.remaining_months,
            total_interest=str(result.total_interest),
        )

        return result

    def _generate_schedule(
        self,
        principal: Decimal,
        annual_rate: Decimal,
        monthly_payment: Decimal,
        start_date: date,
        extra_payment: Decimal = Decimal("0"),
    ) -> AmortizationSchedule:
        """Generiert einen Tilgungsplan.

        Args:
            principal: Kreditsumme
            annual_rate: Jaehrlicher Zinssatz in Prozent
            monthly_payment: Monatliche Rate
            start_date: Startdatum
            extra_payment: Optionale monatliche Sondertilgung

        Returns:
            AmortizationSchedule
        """
        schedule: list[AmortizationEntry] = []
        balance = principal
        monthly_rate = annual_rate / 12 / 100
        total_payment = monthly_payment + extra_payment

        month = 0
        total_interest = Decimal("0")
        total_payments = Decimal("0")

        while balance > 0 and month < 600:  # Max 50 Jahre
            month += 1
            interest = (balance * monthly_rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            principal_payment = min(total_payment - interest, balance)
            balance = max(balance - principal_payment, Decimal("0"))

            total_interest += interest
            total_payments += total_payment

            schedule.append(AmortizationEntry(
                month=month,
                payment=total_payment,
                principal=principal_payment,
                interest=interest,
                balance=balance,
            ))

        payoff_date = start_date + timedelta(days=month * 30)

        return AmortizationSchedule(
            schedule=schedule,
            total_interest=total_interest,
            total_payments=total_payments,
            payoff_date=payoff_date,
            remaining_months=month,
        )

    async def calculate_extra_payment_impact(
        self,
        loan_id: UUID,
        space_id: UUID,
        extra_monthly: Decimal,
        persist: bool = True,
    ) -> ExtraPaymentImpact:
        """Berechnet die Auswirkung einer Sondertilgung.

        Args:
            loan_id: UUID des Kredits
            space_id: UUID des Space (Multi-Tenant Security!)
            extra_monthly: Monatliche Sondertilgung
            persist: Ob Ersparnis in DB persistiert werden soll

        Returns:
            ExtraPaymentImpact mit Ersparnis-Details

        Raises:
            ValueError: Wenn Kredit nicht gefunden oder Zugriff verweigert
        """
        logger.info(
            "loan_extra_payment_impact_started",
            loan_id=str(loan_id),
            space_id=str(space_id),
            extra_monthly=str(extra_monthly),
        )

        loan = await self._get_loan(loan_id, space_id)

        # Validierung
        if not loan.principal_amount or loan.principal_amount <= 0:
            raise ValueError(f"Kredit {loan_id} hat keine gueltige Kreditsumme")
        if not loan.monthly_payment or loan.monthly_payment <= 0:
            raise ValueError(f"Kredit {loan_id} hat keine gueltige monatliche Rate")

        principal = Decimal(str(loan.current_balance or loan.principal_amount))
        annual_rate = Decimal(str(loan.interest_rate or 0))
        monthly_payment = Decimal(str(loan.monthly_payment))

        # Standard-Tilgung
        standard = self._generate_schedule(
            principal=principal,
            annual_rate=annual_rate,
            monthly_payment=monthly_payment,
            start_date=date.today(),
        )

        # Mit Sondertilgung
        with_extra = self._generate_schedule(
            principal=principal,
            annual_rate=annual_rate,
            monthly_payment=monthly_payment,
            start_date=date.today(),
            extra_payment=extra_monthly,
        )

        result = ExtraPaymentImpact(
            extra_monthly=extra_monthly,
            months_saved=standard.remaining_months - with_extra.remaining_months,
            interest_saved=standard.total_interest - with_extra.total_interest,
            new_payoff_date=with_extra.payoff_date,
        )

        if persist:
            await self._persist_extra_payment_impact(loan, result)

        logger.info(
            "loan_extra_payment_impact_completed",
            loan_id=str(loan_id),
            months_saved=result.months_saved,
            interest_saved=str(result.interest_saved),
        )

        return result

    async def calculate_remaining_balance(
        self,
        loan_id: UUID,
        space_id: UUID,
        at_date: date,
    ) -> Decimal:
        """Berechnet die Restschuld zu einem bestimmten Datum.

        Args:
            loan_id: UUID des Kredits
            space_id: UUID des Space (Multi-Tenant Security!)
            at_date: Stichtag

        Returns:
            Restschuld zum Stichtag

        Raises:
            ValueError: Wenn Kredit nicht gefunden oder Zugriff verweigert
        """
        loan = await self._get_loan(loan_id, space_id)

        if not loan.principal_amount or loan.principal_amount <= 0:
            return Decimal("0")
        if not loan.monthly_payment or loan.monthly_payment <= 0:
            return Decimal(str(loan.principal_amount))

        principal = Decimal(str(loan.principal_amount))
        annual_rate = Decimal(str(loan.interest_rate or 0))
        monthly_payment = Decimal(str(loan.monthly_payment))
        start_date = loan.start_date or date.today()

        schedule = self._generate_schedule(
            principal=principal,
            annual_rate=annual_rate,
            monthly_payment=monthly_payment,
            start_date=start_date,
        )

        # Finde den Monat zum Stichtag
        months_from_start = ((at_date.year - start_date.year) * 12 +
                            (at_date.month - start_date.month))

        if months_from_start <= 0:
            return principal

        if months_from_start >= len(schedule.schedule):
            return Decimal("0")

        return schedule.schedule[months_from_start - 1].balance

    async def calculate_payoff_date(
        self,
        loan_id: UUID,
        space_id: UUID,
    ) -> date:
        """Berechnet das voraussichtliche Tilgungsdatum.

        Args:
            loan_id: UUID des Kredits
            space_id: UUID des Space (Multi-Tenant Security!)

        Returns:
            Voraussichtliches Enddatum

        Raises:
            ValueError: Wenn Kredit nicht gefunden oder Zugriff verweigert
        """
        schedule = await self.calculate_amortization_schedule(
            loan_id, space_id, persist=False
        )
        return schedule.payoff_date

    def compare_loan_options(
        self,
        principal: Decimal,
        options: list[LoanOption],
    ) -> list[LoanComparison]:
        """Vergleicht verschiedene Kreditoptionen.

        Args:
            principal: Kreditsumme
            options: Liste von LoanOption Objekten

        Returns:
            Liste von LoanComparison Ergebnissen
        """
        results: list[LoanComparison] = []

        for opt in options:
            annual_rate = opt.rate
            term_months = opt.term_months
            name = opt.name or f"{annual_rate}% / {term_months}M"

            # Monatliche Rate berechnen (Annuitaet)
            monthly_rate = annual_rate / 12 / 100
            if monthly_rate > 0:
                monthly_payment = principal * (
                    monthly_rate * (1 + monthly_rate) ** term_months
                ) / ((1 + monthly_rate) ** term_months - 1)
            else:
                monthly_payment = principal / Decimal(str(term_months))

            monthly_payment = monthly_payment.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

            schedule = self._generate_schedule(
                principal=principal,
                annual_rate=annual_rate,
                monthly_payment=monthly_payment,
                start_date=date.today(),
            )

            results.append(LoanComparison(
                option_name=name,
                monthly_payment=monthly_payment,
                total_interest=schedule.total_interest,
                payoff_months=schedule.remaining_months,
                total_cost=schedule.total_payments,
            ))

        return results

    def _calc_monthly_payment(
        self,
        principal: Decimal,
        annual_rate: Decimal,
        term_months: int
    ) -> Decimal:
        """Berechnet die monatliche Annuitaet.

        Formel: P * (r * (1+r)^n) / ((1+r)^n - 1)
        """
        monthly_rate = annual_rate / 12 / 100

        if monthly_rate == 0:
            return (principal / Decimal(str(term_months))).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )

        numerator = principal * monthly_rate * (1 + monthly_rate) ** term_months
        denominator = (1 + monthly_rate) ** term_months - 1

        return (numerator / denominator).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    async def _get_loan(self, loan_id: UUID, space_id: UUID) -> PrivatLoan:
        """Laedt Kredit aus der Datenbank mit Multi-Tenant Security.

        Args:
            loan_id: UUID des Kredits
            space_id: UUID des Space (Multi-Tenant Security!)

        Returns:
            PrivatLoan Objekt

        Raises:
            ValueError: Wenn Kredit nicht gefunden oder Zugriff verweigert
        """
        stmt = (
            select(PrivatLoan)
            .where(
                PrivatLoan.id == loan_id,
                PrivatLoan.space_id == space_id,  # Multi-Tenant Security!
                PrivatLoan.is_active.is_(True),
            )
        )

        result = await self.db.execute(stmt)
        loan = result.scalar_one_or_none()

        if not loan:
            logger.warning(
                "loan_not_found_or_access_denied",
                loan_id=str(loan_id),
                space_id=str(space_id),
            )
            raise ValueError(
                f"Kredit {loan_id} nicht gefunden oder Zugriff verweigert"
            )

        return loan

    async def _get_all_loans(self, space_id: UUID) -> list[PrivatLoan]:
        """Laedt alle aktiven Kredite eines Space.

        Args:
            space_id: UUID des Space (Multi-Tenant Security!)

        Returns:
            Liste von PrivatLoan Objekten
        """
        stmt = (
            select(PrivatLoan)
            .where(
                PrivatLoan.space_id == space_id,  # Multi-Tenant Security!
                PrivatLoan.is_active.is_(True),
            )
            .order_by(PrivatLoan.start_date.desc())
        )

        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def _persist_amortization(
        self,
        loan: PrivatLoan,
        schedule: AmortizationSchedule,
    ) -> None:
        """Persistiert Tilgungsplan-KPIs in der Datenbank.

        Args:
            loan: PrivatLoan Objekt
            schedule: Berechneter Tilgungsplan
        """
        # Konvertiere Schedule zu JSON-faehigem Format
        schedule_json = [
            {
                "month": entry.month,
                "payment": str(entry.payment),
                "principal": str(entry.principal),
                "interest": str(entry.interest),
                "balance": str(entry.balance),
            }
            for entry in schedule.schedule[:60]  # Maximal 5 Jahre voraus speichern
        ]

        loan.amortization_schedule = schedule_json
        loan.projected_payoff_date = schedule.payoff_date
        loan.total_interest_projected = schedule.total_interest
        loan.remaining_term_months = schedule.remaining_months
        loan.last_kpi_calculation = datetime.now(timezone.utc)

        await self.db.commit()

        logger.debug(
            "loan_amortization_persisted",
            loan_id=str(loan.id),
            remaining_months=schedule.remaining_months,
        )

    async def _persist_extra_payment_impact(
        self,
        loan: PrivatLoan,
        impact: ExtraPaymentImpact,
    ) -> None:
        """Persistiert Sondertilgungs-Ersparnis in der Datenbank.

        Args:
            loan: PrivatLoan Objekt
            impact: Berechnete Auswirkung
        """
        loan.interest_saved_with_extra = impact.interest_saved
        loan.last_kpi_calculation = datetime.now(timezone.utc)

        await self.db.commit()

        logger.debug(
            "loan_extra_payment_impact_persisted",
            loan_id=str(loan.id),
            interest_saved=str(impact.interest_saved),
        )

    async def calculate_all_loan_kpis_for_space(
        self,
        space_id: UUID,
        persist: bool = True,
    ) -> dict[UUID, AmortizationSchedule]:
        """Berechnet KPIs fuer alle Kredite eines Space.

        Batch-Methode fuer Celery Tasks.

        Args:
            space_id: UUID des Space
            persist: Ob KPIs persistiert werden sollen

        Returns:
            Dict von loan_id -> AmortizationSchedule
        """
        logger.info(
            "batch_loan_kpi_calculation_started",
            space_id=str(space_id),
        )

        loans = await self._get_all_loans(space_id)

        results: dict[UUID, AmortizationSchedule] = {}
        success_count = 0
        error_count = 0

        for loan in loans:
            try:
                schedule = await self.calculate_amortization_schedule(
                    loan_id=loan.id,
                    space_id=space_id,
                    persist=persist,
                )
                results[loan.id] = schedule
                success_count += 1
            except Exception as e:
                logger.error(
                    "loan_kpi_calculation_failed",
                    loan_id=str(loan.id),
                    **safe_error_log(e),
                )
                error_count += 1

        logger.info(
            "batch_loan_kpi_calculation_completed",
            space_id=str(space_id),
            total=len(loans),
            success=success_count,
            errors=error_count,
        )

        return results

    def _calc_effective_annual_rate(
        self,
        nominal_rate: Decimal,
        periods_per_year: int = 12,
    ) -> Decimal:
        """Berechnet den effektiven Jahreszins.

        Formel: (1 + nominal_rate/n)^n - 1

        Args:
            nominal_rate: Nominaler Jahreszins in Prozent
            periods_per_year: Anzahl der Zinsperioden pro Jahr

        Returns:
            Effektiver Jahreszins in Prozent
        """
        if nominal_rate <= 0:
            return Decimal("0")

        rate = nominal_rate / 100
        effective = ((1 + rate / periods_per_year) ** periods_per_year) - 1
        return (Decimal(str(effective)) * 100).quantize(
            Decimal("0.001"), rounding=ROUND_HALF_UP
        )
