# -*- coding: utf-8 -*-
"""
LoanScenarioService - What-If Analysen fuer Kredite.

Ermoeglicht Simulationen:
1. Sondertilgung: Was passiert bei Extra-Zahlungen?
2. Umschuldung: Lohnt sich ein neuer Kredit?
3. Ratenänderung: Auswirkung auf Laufzeit/Zinsen
4. Tilgungssatzänderung: Effekt verschiedener Tilgungssätze

Enterprise Feature - KEINE externen APIs, alles lokal berechnet.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone, date, timedelta
from decimal import Decimal, ROUND_HALF_UP, ROUND_CEILING
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID
import math

import structlog
from prometheus_client import Counter, Histogram
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger(__name__)


# =============================================================================
# Prometheus Metriken
# =============================================================================

LOAN_SCENARIO_CALCULATIONS = Counter(
    "loan_scenario_calculations_total",
    "Anzahl der Kredit-Szenarien Berechnungen",
    ["scenario_type"]
)

LOAN_SCENARIO_DURATION = Histogram(
    "loan_scenario_duration_seconds",
    "Dauer der Kredit-Szenarien Berechnung",
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0]
)


# =============================================================================
# Konstanten
# =============================================================================

# Typische Vorfaelligkeitsentschaedigungsregelung (vereinfacht)
PREPAYMENT_PENALTY_RATE = Decimal("0.01")  # 1% des Restbetrags
PREPAYMENT_PENALTY_MAX_MONTHS = 6  # oder 6 Monats-Zinsen

# Umschuldungskosten (geschaetzt)
REFINANCING_COSTS = {
    "notar": Decimal("0.015"),           # 1.5% vom Kreditbetrag
    "grundbuch": Decimal("0.005"),       # 0.5% vom Kreditbetrag
    "bearbeitungsgebuehr": Decimal("0"),  # seit 2014 nicht mehr erlaubt
}


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class AmortizationEntry:
    """Ein Eintrag im Tilgungsplan."""
    month: int
    date: date
    opening_balance: Decimal
    payment: Decimal
    principal: Decimal
    interest: Decimal
    closing_balance: Decimal
    extra_payment: Decimal = Decimal("0")


@dataclass
class ExtraPaymentScenario:
    """Ergebnis einer Sondertilgungs-Simulation."""
    loan_id: UUID
    loan_name: str

    # Ausgangssituation
    original_remaining_balance: Decimal
    original_monthly_payment: Decimal
    original_interest_rate: Decimal
    original_remaining_months: int
    original_total_interest: Decimal

    # Nach Sondertilgung
    extra_payment_amount: Decimal
    new_remaining_balance: Decimal
    new_remaining_months: int
    new_total_interest: Decimal

    # Einsparungen
    months_saved: int
    interest_saved: Decimal
    new_payoff_date: date

    # Tilgungsplan (optional, kann gross sein)
    amortization_schedule: Optional[List[AmortizationEntry]] = None


@dataclass
class RefinancingScenario:
    """Ergebnis einer Umschuldungs-Simulation."""
    loan_id: UUID
    loan_name: str

    # Aktueller Kredit
    current_balance: Decimal
    current_interest_rate: Decimal
    current_monthly_payment: Decimal
    current_remaining_months: int
    current_total_remaining_interest: Decimal

    # Neuer Kredit
    new_interest_rate: Decimal
    new_monthly_payment: Decimal
    new_remaining_months: int
    new_total_interest: Decimal

    # Kosten
    prepayment_penalty: Decimal
    refinancing_costs: Decimal
    total_upfront_costs: Decimal

    # Vergleich
    interest_savings: Decimal
    net_savings: Decimal  # Ersparnis minus Kosten
    break_even_months: Optional[int]  # Wann rechnet sich die Umschuldung

    # Bewertung
    is_recommended: bool
    recommendation_reason: str


@dataclass
class PaymentChangeScenario:
    """Ergebnis einer Ratenänderungs-Simulation."""
    loan_id: UUID
    loan_name: str

    # Ausgangssituation
    original_payment: Decimal
    original_remaining_months: int
    original_total_interest: Decimal

    # Neues Szenario
    new_payment: Decimal
    new_remaining_months: int
    new_total_interest: Decimal

    # Differenz
    payment_change: Decimal
    months_change: int
    interest_change: Decimal

    # Warnung bei zu niedriger Rate
    is_viable: bool
    warning_message: Optional[str]


@dataclass
class LoanComparison:
    """Vergleich mehrerer Kredit-Szenarien."""
    loan_id: UUID
    loan_name: str

    scenarios: List[Dict[str, Any]]

    best_scenario: str
    best_scenario_reason: str


@dataclass
class TilgungsPlanResponse:
    """Vollstaendiger Tilgungsplan."""
    loan_id: UUID
    loan_name: str

    # Kredit-Details
    principal: Decimal
    interest_rate: Decimal
    monthly_payment: Decimal
    start_date: date

    # Berechnet
    total_months: int
    total_interest: Decimal
    total_payments: Decimal
    payoff_date: date

    # Plan
    schedule: List[AmortizationEntry]


# =============================================================================
# Singleton Service
# =============================================================================

class LoanScenarioService:
    """
    Singleton Service fuer Kredit-Szenarien und What-If Analysen.

    Ermoeglicht:
    - Sondertilgungs-Simulationen
    - Umschuldungs-Analysen
    - Ratenänderungs-Szenarien
    - Vollstaendige Tilgungsplaene
    """

    _instance: Optional["LoanScenarioService"] = None
    _lock = threading.Lock()

    def __new__(cls) -> "LoanScenarioService":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        if self._initialized:
            return
        self._initialized = True
        logger.info("loan_scenario_service_initialized")

    # =========================================================================
    # Sondertilgung Simulation
    # =========================================================================

    async def simulate_extra_payment(
        self,
        db: AsyncSession,
        loan_id: UUID,
        extra_payment_amount: Decimal,
        include_amortization: bool = False,
    ) -> Optional[ExtraPaymentScenario]:
        """Simuliert eine einmalige Sondertilgung."""
        from app.db.models import PrivatLoan

        LOAN_SCENARIO_CALCULATIONS.labels(scenario_type="extra_payment").inc()

        result = await db.execute(
            select(PrivatLoan).where(PrivatLoan.id == loan_id)
        )
        loan = result.scalar_one_or_none()

        if not loan:
            logger.warning("loan_not_found_for_scenario", loan_id=str(loan_id))
            return None

        # Aktuelle Werte
        remaining_balance = loan.remaining_balance or Decimal("0")
        monthly_payment = loan.monthly_payment or Decimal("0")
        interest_rate = loan.interest_rate or Decimal("0")

        if remaining_balance <= 0 or monthly_payment <= 0:
            return None

        # Monatlicher Zinssatz
        monthly_rate = interest_rate / Decimal("100") / Decimal("12")

        # Original-Restlaufzeit berechnen
        original_months = self._calculate_remaining_months(
            remaining_balance, monthly_payment, monthly_rate
        )
        original_total_interest = self._calculate_total_interest(
            remaining_balance, monthly_payment, monthly_rate, original_months
        )

        # Nach Sondertilgung
        new_balance = max(Decimal("0"), remaining_balance - extra_payment_amount)

        if new_balance <= 0:
            # Kredit komplett abbezahlt
            return ExtraPaymentScenario(
                loan_id=loan_id,
                loan_name=loan.name,
                original_remaining_balance=remaining_balance,
                original_monthly_payment=monthly_payment,
                original_interest_rate=interest_rate,
                original_remaining_months=original_months,
                original_total_interest=original_total_interest,
                extra_payment_amount=extra_payment_amount,
                new_remaining_balance=Decimal("0"),
                new_remaining_months=0,
                new_total_interest=Decimal("0"),
                months_saved=original_months,
                interest_saved=original_total_interest,
                new_payoff_date=date.today(),
            )

        # Neue Restlaufzeit berechnen (gleiche Rate)
        new_months = self._calculate_remaining_months(
            new_balance, monthly_payment, monthly_rate
        )
        new_total_interest = self._calculate_total_interest(
            new_balance, monthly_payment, monthly_rate, new_months
        )

        # Einsparungen
        months_saved = original_months - new_months
        interest_saved = original_total_interest - new_total_interest

        # Neues Enddatum
        new_payoff_date = date.today() + timedelta(days=new_months * 30)

        # Tilgungsplan (optional)
        amortization = None
        if include_amortization:
            amortization = self._generate_amortization_schedule(
                new_balance, monthly_payment, monthly_rate, date.today()
            )

        logger.info(
            "extra_payment_simulated",
            loan_id=str(loan_id),
            extra_payment=str(extra_payment_amount),
            months_saved=months_saved,
            interest_saved=str(interest_saved),
        )

        return ExtraPaymentScenario(
            loan_id=loan_id,
            loan_name=loan.name,
            original_remaining_balance=remaining_balance,
            original_monthly_payment=monthly_payment,
            original_interest_rate=interest_rate,
            original_remaining_months=original_months,
            original_total_interest=original_total_interest,
            extra_payment_amount=extra_payment_amount,
            new_remaining_balance=new_balance,
            new_remaining_months=new_months,
            new_total_interest=new_total_interest,
            months_saved=months_saved,
            interest_saved=interest_saved,
            new_payoff_date=new_payoff_date,
            amortization_schedule=amortization,
        )

    # =========================================================================
    # Umschuldung Simulation
    # =========================================================================

    async def simulate_refinancing(
        self,
        db: AsyncSession,
        loan_id: UUID,
        new_interest_rate: Decimal,
        new_loan_term_months: Optional[int] = None,
    ) -> Optional[RefinancingScenario]:
        """Simuliert eine Umschuldung zu einem neuen Zinssatz."""
        from app.db.models import PrivatLoan

        LOAN_SCENARIO_CALCULATIONS.labels(scenario_type="refinancing").inc()

        result = await db.execute(
            select(PrivatLoan).where(PrivatLoan.id == loan_id)
        )
        loan = result.scalar_one_or_none()

        if not loan:
            logger.warning("loan_not_found_for_refinancing", loan_id=str(loan_id))
            return None

        # Aktuelle Werte
        current_balance = loan.remaining_balance or Decimal("0")
        current_rate = loan.interest_rate or Decimal("0")
        current_payment = loan.monthly_payment or Decimal("0")

        if current_balance <= 0 or current_payment <= 0:
            return None

        # Monatliche Zinssaetze
        current_monthly_rate = current_rate / Decimal("100") / Decimal("12")
        new_monthly_rate = new_interest_rate / Decimal("100") / Decimal("12")

        # Aktuelle Restlaufzeit und Zinsen
        current_remaining_months = self._calculate_remaining_months(
            current_balance, current_payment, current_monthly_rate
        )
        current_total_interest = self._calculate_total_interest(
            current_balance, current_payment, current_monthly_rate, current_remaining_months
        )

        # Neue Laufzeit (Standard: gleiche Laufzeit wie aktuell)
        new_term = new_loan_term_months or current_remaining_months

        # Neue monatliche Rate berechnen
        new_payment = self._calculate_monthly_payment(
            current_balance, new_monthly_rate, new_term
        )

        # Neue Gesamtzinsen
        new_total_interest = self._calculate_total_interest(
            current_balance, new_payment, new_monthly_rate, new_term
        )

        # Vorfaelligkeitsentschaedigung berechnen
        prepayment_penalty = self._calculate_prepayment_penalty(
            current_balance, current_monthly_rate
        )

        # Umschuldungskosten
        refinancing_costs = (
            current_balance * REFINANCING_COSTS["notar"] +
            current_balance * REFINANCING_COSTS["grundbuch"]
        )

        total_upfront_costs = prepayment_penalty + refinancing_costs

        # Vergleich
        interest_savings = current_total_interest - new_total_interest
        net_savings = interest_savings - total_upfront_costs

        # Break-Even berechnen
        monthly_savings = current_payment - new_payment
        break_even_months: Optional[int] = None
        if monthly_savings > 0:
            break_even_months = int(
                (total_upfront_costs / monthly_savings).quantize(Decimal("1"), rounding=ROUND_CEILING)
            )

        # Empfehlung
        is_recommended = net_savings > Decimal("1000") and (break_even_months is None or break_even_months <= 24)

        if net_savings <= 0:
            recommendation_reason = "Die Umschuldung lohnt sich nicht - Kosten uebersteigen die Ersparnis."
        elif break_even_months and break_even_months > 36:
            recommendation_reason = f"Break-Even erst nach {break_even_months} Monaten - pruefe Alternative."
            is_recommended = False
        elif is_recommended:
            recommendation_reason = f"Empfohlen! Netto-Ersparnis von {net_savings} EUR nach Kosten."
        else:
            recommendation_reason = "Geringe Ersparnis - individuelle Abwaegung erforderlich."

        logger.info(
            "refinancing_simulated",
            loan_id=str(loan_id),
            current_rate=str(current_rate),
            new_rate=str(new_interest_rate),
            net_savings=str(net_savings),
            is_recommended=is_recommended,
        )

        return RefinancingScenario(
            loan_id=loan_id,
            loan_name=loan.name,
            current_balance=current_balance,
            current_interest_rate=current_rate,
            current_monthly_payment=current_payment,
            current_remaining_months=current_remaining_months,
            current_total_remaining_interest=current_total_interest,
            new_interest_rate=new_interest_rate,
            new_monthly_payment=new_payment,
            new_remaining_months=new_term,
            new_total_interest=new_total_interest,
            prepayment_penalty=prepayment_penalty,
            refinancing_costs=refinancing_costs,
            total_upfront_costs=total_upfront_costs,
            interest_savings=interest_savings,
            net_savings=net_savings,
            break_even_months=break_even_months,
            is_recommended=is_recommended,
            recommendation_reason=recommendation_reason,
        )

    # =========================================================================
    # Ratenänderung Simulation
    # =========================================================================

    async def simulate_payment_change(
        self,
        db: AsyncSession,
        loan_id: UUID,
        new_monthly_payment: Decimal,
    ) -> Optional[PaymentChangeScenario]:
        """Simuliert eine Aenderung der monatlichen Rate."""
        from app.db.models import PrivatLoan

        LOAN_SCENARIO_CALCULATIONS.labels(scenario_type="payment_change").inc()

        result = await db.execute(
            select(PrivatLoan).where(PrivatLoan.id == loan_id)
        )
        loan = result.scalar_one_or_none()

        if not loan:
            return None

        remaining_balance = loan.remaining_balance or Decimal("0")
        current_payment = loan.monthly_payment or Decimal("0")
        interest_rate = loan.interest_rate or Decimal("0")

        if remaining_balance <= 0:
            return None

        monthly_rate = interest_rate / Decimal("100") / Decimal("12")

        # Minimum-Rate (nur Zinsen)
        minimum_payment = remaining_balance * monthly_rate

        is_viable = True
        warning_message: Optional[str] = None

        if new_monthly_payment <= minimum_payment:
            is_viable = False
            warning_message = (
                f"Die neue Rate ({new_monthly_payment} EUR) ist zu niedrig. "
                f"Mindestens {minimum_payment.quantize(Decimal('0.01'))} EUR sind noetig um die Zinsen zu decken."
            )

        # Original
        original_months = self._calculate_remaining_months(
            remaining_balance, current_payment, monthly_rate
        )
        original_interest = self._calculate_total_interest(
            remaining_balance, current_payment, monthly_rate, original_months
        )

        # Neu
        if is_viable:
            new_months = self._calculate_remaining_months(
                remaining_balance, new_monthly_payment, monthly_rate
            )
            new_interest = self._calculate_total_interest(
                remaining_balance, new_monthly_payment, monthly_rate, new_months
            )
        else:
            new_months = 9999  # "unendlich"
            new_interest = Decimal("0")

        return PaymentChangeScenario(
            loan_id=loan_id,
            loan_name=loan.name,
            original_payment=current_payment,
            original_remaining_months=original_months,
            original_total_interest=original_interest,
            new_payment=new_monthly_payment,
            new_remaining_months=new_months,
            new_total_interest=new_interest,
            payment_change=new_monthly_payment - current_payment,
            months_change=new_months - original_months,
            interest_change=new_interest - original_interest,
            is_viable=is_viable,
            warning_message=warning_message,
        )

    # =========================================================================
    # Vollstaendiger Tilgungsplan
    # =========================================================================

    async def generate_full_amortization(
        self,
        db: AsyncSession,
        loan_id: UUID,
    ) -> Optional[TilgungsPlanResponse]:
        """Generiert einen vollstaendigen Tilgungsplan."""
        from app.db.models import PrivatLoan

        LOAN_SCENARIO_CALCULATIONS.labels(scenario_type="amortization").inc()

        result = await db.execute(
            select(PrivatLoan).where(PrivatLoan.id == loan_id)
        )
        loan = result.scalar_one_or_none()

        if not loan:
            return None

        principal = loan.original_amount or loan.remaining_balance or Decimal("0")
        remaining = loan.remaining_balance or Decimal("0")
        payment = loan.monthly_payment or Decimal("0")
        rate = loan.interest_rate or Decimal("0")
        start = loan.start_date or date.today()

        if principal <= 0 or payment <= 0:
            return None

        monthly_rate = rate / Decimal("100") / Decimal("12")

        # Tilgungsplan generieren
        schedule = self._generate_amortization_schedule(
            remaining, payment, monthly_rate, date.today()
        )

        total_months = len(schedule)
        total_interest = sum(entry.interest for entry in schedule)
        total_payments = sum(entry.payment for entry in schedule)
        payoff_date = schedule[-1].date if schedule else date.today()

        return TilgungsPlanResponse(
            loan_id=loan_id,
            loan_name=loan.name,
            principal=principal,
            interest_rate=rate,
            monthly_payment=payment,
            start_date=start,
            total_months=total_months,
            total_interest=total_interest,
            total_payments=total_payments,
            payoff_date=payoff_date,
            schedule=schedule,
        )

    # =========================================================================
    # Mehrere Szenarien vergleichen
    # =========================================================================

    async def compare_scenarios(
        self,
        db: AsyncSession,
        loan_id: UUID,
        extra_payments: List[Decimal] = None,
        new_rates: List[Decimal] = None,
    ) -> Optional[LoanComparison]:
        """Vergleicht mehrere Szenarien fuer einen Kredit."""
        from app.db.models import PrivatLoan

        LOAN_SCENARIO_CALCULATIONS.labels(scenario_type="comparison").inc()

        result = await db.execute(
            select(PrivatLoan).where(PrivatLoan.id == loan_id)
        )
        loan = result.scalar_one_or_none()

        if not loan:
            return None

        extra_payments = extra_payments or []
        new_rates = new_rates or []

        scenarios: List[Dict[str, Any]] = []
        best_net_savings = Decimal("-999999999")
        best_scenario = "baseline"
        best_reason = "Keine bessere Option gefunden"

        # Baseline (aktueller Stand)
        remaining = loan.remaining_balance or Decimal("0")
        payment = loan.monthly_payment or Decimal("0")
        rate = loan.interest_rate or Decimal("0")
        monthly_rate = rate / Decimal("100") / Decimal("12")

        baseline_months = self._calculate_remaining_months(remaining, payment, monthly_rate)
        baseline_interest = self._calculate_total_interest(remaining, payment, monthly_rate, baseline_months)

        scenarios.append({
            "name": "baseline",
            "description": "Aktueller Stand ohne Aenderung",
            "remaining_months": baseline_months,
            "total_interest": str(baseline_interest),
            "net_savings": "0",
        })

        # Extra-Payment Szenarien
        for extra in extra_payments:
            scenario = await self.simulate_extra_payment(db, loan_id, extra)
            if scenario:
                net_savings = scenario.interest_saved
                scenarios.append({
                    "name": f"extra_payment_{extra}",
                    "description": f"Sondertilgung von {extra} EUR",
                    "remaining_months": scenario.new_remaining_months,
                    "total_interest": str(scenario.new_total_interest),
                    "net_savings": str(net_savings),
                    "extra_payment": str(extra),
                })

                if net_savings > best_net_savings:
                    best_net_savings = net_savings
                    best_scenario = f"Sondertilgung {extra} EUR"
                    best_reason = f"Spart {net_savings} EUR Zinsen und verkuerzt um {scenario.months_saved} Monate"

        # Refinancing Szenarien
        for new_rate in new_rates:
            scenario = await self.simulate_refinancing(db, loan_id, new_rate)
            if scenario:
                scenarios.append({
                    "name": f"refinancing_{new_rate}",
                    "description": f"Umschuldung auf {new_rate}%",
                    "remaining_months": scenario.new_remaining_months,
                    "total_interest": str(scenario.new_total_interest),
                    "net_savings": str(scenario.net_savings),
                    "new_rate": str(new_rate),
                    "upfront_costs": str(scenario.total_upfront_costs),
                })

                if scenario.net_savings > best_net_savings:
                    best_net_savings = scenario.net_savings
                    best_scenario = f"Umschuldung auf {new_rate}%"
                    best_reason = scenario.recommendation_reason

        return LoanComparison(
            loan_id=loan_id,
            loan_name=loan.name,
            scenarios=scenarios,
            best_scenario=best_scenario,
            best_scenario_reason=best_reason,
        )

    # =========================================================================
    # Hilfsmethoden
    # =========================================================================

    def _calculate_remaining_months(
        self,
        balance: Decimal,
        payment: Decimal,
        monthly_rate: Decimal,
    ) -> int:
        """Berechnet die Restlaufzeit in Monaten."""
        if payment <= 0 or balance <= 0:
            return 0

        if monthly_rate <= 0:
            # Zinslos
            return int((balance / payment).quantize(Decimal("1"), rounding=ROUND_CEILING))

        # Formel: n = -log(1 - r*P/M) / log(1 + r)
        # P = Principal, M = Monthly Payment, r = monthly rate
        try:
            rate_float = float(monthly_rate)
            balance_float = float(balance)
            payment_float = float(payment)

            # Pruefe ob Rate ueberhaupt tilgt
            if payment_float <= balance_float * rate_float:
                return 9999  # "unendlich"

            n = -math.log(1 - rate_float * balance_float / payment_float) / math.log(1 + rate_float)
            return int(math.ceil(n))
        except (ValueError, ZeroDivisionError):
            return 9999

    def _calculate_total_interest(
        self,
        balance: Decimal,
        payment: Decimal,
        monthly_rate: Decimal,
        months: int,
    ) -> Decimal:
        """Berechnet die Gesamtzinsen ueber die Laufzeit."""
        if months <= 0 or months >= 9999:
            return Decimal("0")

        total_paid = payment * months

        # Letzte Zahlung kann kleiner sein
        # Vereinfacht: Total Interest = Total Payments - Principal
        total_interest = total_paid - balance

        # Falls negativ (durch Rundung), auf 0 setzen
        return max(Decimal("0"), total_interest.quantize(Decimal("0.01")))

    def _calculate_monthly_payment(
        self,
        principal: Decimal,
        monthly_rate: Decimal,
        term_months: int,
    ) -> Decimal:
        """Berechnet die monatliche Rate fuer einen Kredit."""
        if term_months <= 0 or principal <= 0:
            return Decimal("0")

        if monthly_rate <= 0:
            # Zinslos
            return (principal / term_months).quantize(Decimal("0.01"))

        # Formel: M = P * [r(1+r)^n] / [(1+r)^n - 1]
        try:
            r = float(monthly_rate)
            n = term_months
            p = float(principal)

            payment = p * (r * (1 + r) ** n) / ((1 + r) ** n - 1)
            return Decimal(str(payment)).quantize(Decimal("0.01"))
        except (ValueError, ZeroDivisionError, OverflowError):
            return Decimal("0")

    def _calculate_prepayment_penalty(
        self,
        remaining_balance: Decimal,
        monthly_rate: Decimal,
    ) -> Decimal:
        """Berechnet die geschaetzte Vorfaelligkeitsentschaedigung."""
        # Methode 1: 1% vom Restbetrag
        penalty_percentage = remaining_balance * PREPAYMENT_PENALTY_RATE

        # Methode 2: 6 Monatszinsen
        penalty_months = remaining_balance * monthly_rate * PREPAYMENT_PENALTY_MAX_MONTHS

        # Nehme das Minimum (wie rechtlich vorgesehen)
        penalty = min(penalty_percentage, penalty_months)

        return penalty.quantize(Decimal("0.01"))

    def _generate_amortization_schedule(
        self,
        principal: Decimal,
        payment: Decimal,
        monthly_rate: Decimal,
        start_date: date,
    ) -> List[AmortizationEntry]:
        """Generiert einen detaillierten Tilgungsplan."""
        schedule: List[AmortizationEntry] = []
        balance = principal
        current_date = start_date

        month = 0
        max_months = 600  # 50 Jahre Maximum

        while balance > Decimal("0.01") and month < max_months:
            month += 1
            current_date = current_date + timedelta(days=30)

            interest = (balance * monthly_rate).quantize(Decimal("0.01"))
            principal_part = payment - interest

            # Letzte Zahlung anpassen
            if principal_part > balance:
                principal_part = balance
                actual_payment = principal_part + interest
            else:
                actual_payment = payment

            new_balance = balance - principal_part

            entry = AmortizationEntry(
                month=month,
                date=current_date,
                opening_balance=balance,
                payment=actual_payment,
                principal=principal_part,
                interest=interest,
                closing_balance=max(Decimal("0"), new_balance),
            )
            schedule.append(entry)

            balance = new_balance

        return schedule


# =============================================================================
# Singleton-Instanz
# =============================================================================

def get_loan_scenario_service() -> LoanScenarioService:
    """Gibt die Singleton-Instanz des Loan Scenario Service zurueck."""
    return LoanScenarioService()
