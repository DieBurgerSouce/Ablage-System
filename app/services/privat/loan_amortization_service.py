# -*- coding: utf-8 -*-
"""
LoanAmortizationService - Kredit-Tilgungsplaene und Analysen.

Berechnet automatisch:
- Tilgungsplan (Annuitaet)
- Voraussichtliches Rueckzahlungsdatum
- Gesamtzinsen
- Zinsersparnis bei Sondertilgung

Enterprise Feature - feinpoliert und durchdacht.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone, date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, List, Optional
from uuid import UUID

import structlog
from prometheus_client import Counter, Histogram
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger(__name__)


# =============================================================================
# Prometheus Metriken
# =============================================================================

LOAN_CALCULATIONS = Counter(
    "loan_calculation_requests_total",
    "Anzahl der Kredit-Berechnungen",
    ["calculation_type"]
)

LOAN_CALCULATION_DURATION = Histogram(
    "loan_calculation_duration_seconds",
    "Dauer der Kredit-Berechnung in Sekunden",
    buckets=[0.01, 0.05, 0.1, 0.5, 1.0, 2.0]
)


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class AmortizationEntry:
    """Einzelner Eintrag im Tilgungsplan."""
    period: int  # Monat/Periode
    date: date
    payment: Decimal  # Gesamtrate
    principal: Decimal  # Tilgungsanteil
    interest: Decimal  # Zinsanteil
    extra_payment: Decimal  # Sondertilgung
    balance: Decimal  # Restschuld nach Zahlung


@dataclass
class AmortizationScheduleResult:
    """Ergebnis der Tilgungsplan-Berechnung."""
    loan_id: UUID
    schedule: List[AmortizationEntry]
    total_payments: Decimal
    total_interest: Decimal
    total_principal: Decimal
    payoff_date: date
    term_months: int
    monthly_payment: Decimal
    effective_rate: Decimal
    calculated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class ExtraPaymentAnalysis:
    """Analyse einer Sondertilgung."""
    loan_id: UUID
    extra_payment_amount: Decimal
    months_saved: int
    interest_saved: Decimal
    new_payoff_date: date
    new_total_interest: Decimal
    original_payoff_date: date
    original_total_interest: Decimal
    calculated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class LoanSummary:
    """Zusammenfassung eines Kredits."""
    loan_id: UUID
    loan_name: str
    principal_amount: Decimal
    current_balance: Decimal
    interest_rate: Decimal
    monthly_payment: Decimal
    remaining_months: int
    projected_payoff_date: date
    total_interest_remaining: Decimal
    progress_percentage: Decimal  # Wie viel bereits getilgt
    calculated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class LoanKPIs:
    """Alle berechneten KPIs fuer einen Kredit."""
    loan_id: UUID
    schedule: Optional[AmortizationScheduleResult] = None
    summary: Optional[LoanSummary] = None
    extra_payment_analysis: Optional[ExtraPaymentAnalysis] = None
    calculated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


# =============================================================================
# Service
# =============================================================================

class LoanAmortizationService:
    """
    Service fuer Kredit-Tilgungsplaene.

    Berechnet:
    - Vollstaendigen Tilgungsplan
    - Restlaufzeit und Auszahlungsdatum
    - Zinsersparnis bei Sondertilgung
    - Effektiven Jahreszins
    """

    def __init__(self) -> None:
        """Initialisiert den Service."""
        pass

    # =========================================================================
    # Tilgungsplan-Berechnung
    # =========================================================================

    async def generate_amortization_schedule(
        self,
        db: AsyncSession,
        loan_id: UUID,
        include_past: bool = False,
    ) -> Optional[AmortizationScheduleResult]:
        """
        Generiert einen vollstaendigen Tilgungsplan.

        Berechnet Annuitaeten-Tilgung mit monatlichen Raten.

        Args:
            db: Datenbank-Session
            loan_id: Kredit-ID
            include_past: Vergangene Perioden einbeziehen

        Returns:
            AmortizationScheduleResult oder None
        """
        from app.db.models import PrivatLoan

        LOAN_CALCULATIONS.labels(calculation_type="amortization_schedule").inc()

        result = await db.execute(
            select(PrivatLoan).where(PrivatLoan.id == loan_id)
        )
        loan = result.scalar_one_or_none()

        if not loan:
            logger.warning("loan_not_found", loan_id=str(loan_id))
            return None

        # Pflichtfelder pruefen
        if not loan.principal_amount or loan.principal_amount <= 0:
            return None
        if not loan.interest_rate:
            return None
        if not loan.monthly_payment or loan.monthly_payment <= 0:
            return None

        # Startwerte
        principal = loan.current_balance or loan.principal_amount
        monthly_rate = loan.interest_rate / 100 / 12
        monthly_payment = loan.monthly_payment
        start_date = loan.balance_date or loan.start_date or date.today()

        # Tilgungsplan generieren
        schedule: List[AmortizationEntry] = []
        balance = principal
        period = 0
        current_date = start_date
        total_interest = Decimal("0")
        total_principal = Decimal("0")
        total_payments = Decimal("0")

        # Maximale Laufzeit (50 Jahre = 600 Monate) als Sicherheit
        max_periods = 600

        while balance > Decimal("0.01") and period < max_periods:
            period += 1

            # Naechsten Monat berechnen
            if period > 1:
                # Zum naechsten Monat
                if current_date.month == 12:
                    current_date = current_date.replace(year=current_date.year + 1, month=1)
                else:
                    current_date = current_date.replace(month=current_date.month + 1)

            # Zinsanteil
            interest = (balance * monthly_rate).quantize(Decimal("0.01"), ROUND_HALF_UP)

            # Tilgungsanteil
            principal_payment = monthly_payment - interest

            # Falls Rate kleiner als Zinsen, nur Zinsen zahlen
            if principal_payment < 0:
                principal_payment = Decimal("0")
                payment = interest
            else:
                payment = monthly_payment

            # Falls Restschuld kleiner als Rate, nur Restschuld zahlen
            if balance < principal_payment:
                principal_payment = balance
                payment = principal_payment + interest

            # Neue Restschuld
            balance = (balance - principal_payment).quantize(Decimal("0.01"), ROUND_HALF_UP)

            # Summen aktualisieren
            total_interest += interest
            total_principal += principal_payment
            total_payments += payment

            schedule.append(AmortizationEntry(
                period=period,
                date=current_date,
                payment=payment,
                principal=principal_payment,
                interest=interest,
                extra_payment=Decimal("0"),
                balance=balance,
            ))

        # Effektiven Jahreszins berechnen (vereinfacht)
        effective_rate = (
            ((total_payments / principal) ** (12 / period) - 1) * 100
            if period > 0 and principal > 0
            else loan.interest_rate
        )

        logger.info(
            "amortization_schedule_generated",
            loan_id=str(loan_id),
            periods=period,
            total_interest=float(total_interest),
            payoff_date=str(current_date),
        )

        return AmortizationScheduleResult(
            loan_id=loan_id,
            schedule=schedule,
            total_payments=total_payments,
            total_interest=total_interest,
            total_principal=total_principal,
            payoff_date=current_date,
            term_months=period,
            monthly_payment=monthly_payment,
            effective_rate=Decimal(str(round(effective_rate, 3))),
        )

    # =========================================================================
    # Sondertilgung-Analyse
    # =========================================================================

    async def analyze_extra_payment(
        self,
        db: AsyncSession,
        loan_id: UUID,
        extra_amount: Decimal,
    ) -> Optional[ExtraPaymentAnalysis]:
        """
        Analysiert die Auswirkung einer Sondertilgung.

        Args:
            db: Datenbank-Session
            loan_id: Kredit-ID
            extra_amount: Hoehe der Sondertilgung

        Returns:
            ExtraPaymentAnalysis oder None
        """
        from app.db.models import PrivatLoan

        LOAN_CALCULATIONS.labels(calculation_type="extra_payment_analysis").inc()

        result = await db.execute(
            select(PrivatLoan).where(PrivatLoan.id == loan_id)
        )
        loan = result.scalar_one_or_none()

        if not loan:
            return None

        if not loan.principal_amount or not loan.interest_rate or not loan.monthly_payment:
            return None

        # Original-Tilgungsplan
        original_schedule = await self.generate_amortization_schedule(db, loan_id)
        if not original_schedule:
            return None

        # Neuen Tilgungsplan mit Sondertilgung berechnen
        principal = (loan.current_balance or loan.principal_amount) - extra_amount
        if principal <= 0:
            # Kredit waere sofort abbezahlt
            return ExtraPaymentAnalysis(
                loan_id=loan_id,
                extra_payment_amount=extra_amount,
                months_saved=original_schedule.term_months,
                interest_saved=original_schedule.total_interest,
                new_payoff_date=date.today(),
                new_total_interest=Decimal("0"),
                original_payoff_date=original_schedule.payoff_date,
                original_total_interest=original_schedule.total_interest,
            )

        monthly_rate = loan.interest_rate / 100 / 12
        monthly_payment = loan.monthly_payment
        start_date = loan.balance_date or loan.start_date or date.today()

        # Neuen Plan berechnen
        balance = principal
        period = 0
        current_date = start_date
        new_total_interest = Decimal("0")
        max_periods = 600

        while balance > Decimal("0.01") and period < max_periods:
            period += 1
            if period > 1:
                if current_date.month == 12:
                    current_date = current_date.replace(year=current_date.year + 1, month=1)
                else:
                    current_date = current_date.replace(month=current_date.month + 1)

            interest = (balance * monthly_rate).quantize(Decimal("0.01"), ROUND_HALF_UP)
            principal_payment = min(monthly_payment - interest, balance)
            if principal_payment < 0:
                principal_payment = Decimal("0")

            balance = (balance - principal_payment).quantize(Decimal("0.01"), ROUND_HALF_UP)
            new_total_interest += interest

        # Ersparnisse berechnen
        months_saved = original_schedule.term_months - period
        interest_saved = original_schedule.total_interest - new_total_interest

        logger.info(
            "extra_payment_analyzed",
            loan_id=str(loan_id),
            extra_amount=float(extra_amount),
            months_saved=months_saved,
            interest_saved=float(interest_saved),
        )

        return ExtraPaymentAnalysis(
            loan_id=loan_id,
            extra_payment_amount=extra_amount,
            months_saved=months_saved,
            interest_saved=interest_saved,
            new_payoff_date=current_date,
            new_total_interest=new_total_interest,
            original_payoff_date=original_schedule.payoff_date,
            original_total_interest=original_schedule.total_interest,
        )

    # =========================================================================
    # Kredit-Zusammenfassung
    # =========================================================================

    async def get_loan_summary(
        self,
        db: AsyncSession,
        loan_id: UUID,
    ) -> Optional[LoanSummary]:
        """
        Erstellt eine Zusammenfassung des Kredits.

        Args:
            db: Datenbank-Session
            loan_id: Kredit-ID

        Returns:
            LoanSummary oder None
        """
        from app.db.models import PrivatLoan

        LOAN_CALCULATIONS.labels(calculation_type="loan_summary").inc()

        result = await db.execute(
            select(PrivatLoan).where(PrivatLoan.id == loan_id)
        )
        loan = result.scalar_one_or_none()

        if not loan:
            return None

        if not loan.principal_amount or not loan.interest_rate or not loan.monthly_payment:
            return None

        # Tilgungsplan fuer Prognose
        schedule = await self.generate_amortization_schedule(db, loan_id)
        if not schedule:
            return None

        # Fortschritt berechnen
        current_balance = loan.current_balance or loan.principal_amount
        progress = ((loan.principal_amount - current_balance) / loan.principal_amount) * 100

        logger.info(
            "loan_summary_calculated",
            loan_id=str(loan_id),
            progress=float(progress),
            remaining_months=schedule.term_months,
        )

        return LoanSummary(
            loan_id=loan_id,
            loan_name=loan.name,
            principal_amount=loan.principal_amount,
            current_balance=current_balance,
            interest_rate=loan.interest_rate,
            monthly_payment=loan.monthly_payment,
            remaining_months=schedule.term_months,
            projected_payoff_date=schedule.payoff_date,
            total_interest_remaining=schedule.total_interest,
            progress_percentage=round(progress, 1),
        )

    # =========================================================================
    # Alle KPIs berechnen
    # =========================================================================

    async def calculate_all_kpis(
        self,
        db: AsyncSession,
        loan_id: UUID,
        extra_payment_amount: Optional[Decimal] = None,
        persist: bool = True,
    ) -> LoanKPIs:
        """
        Berechnet alle KPIs fuer einen Kredit.

        Args:
            db: Datenbank-Session
            loan_id: Kredit-ID
            extra_payment_amount: Optionale Sondertilgung fuer Analyse
            persist: Ob die Werte in der Datenbank gespeichert werden sollen

        Returns:
            LoanKPIs
        """
        schedule = await self.generate_amortization_schedule(db, loan_id)
        summary = await self.get_loan_summary(db, loan_id)

        extra_analysis = None
        if extra_payment_amount and extra_payment_amount > 0:
            extra_analysis = await self.analyze_extra_payment(db, loan_id, extra_payment_amount)

        kpis = LoanKPIs(
            loan_id=loan_id,
            schedule=schedule,
            summary=summary,
            extra_payment_analysis=extra_analysis,
        )

        if persist:
            await self._persist_loan_kpis(db, loan_id, kpis)

        return kpis

    async def _persist_loan_kpis(
        self,
        db: AsyncSession,
        loan_id: UUID,
        kpis: LoanKPIs,
    ) -> None:
        """
        Speichert berechnete KPIs in der Datenbank.

        Args:
            db: Datenbank-Session
            loan_id: Kredit-ID
            kpis: Berechnete KPIs
        """
        from app.db.models import PrivatLoan

        result = await db.execute(
            select(PrivatLoan).where(PrivatLoan.id == loan_id)
        )
        loan = result.scalar_one_or_none()

        if not loan:
            return

        # Tilgungsplan als JSON speichern (nur Zusammenfassung, nicht alle Eintraege)
        if kpis.schedule:
            # Nur wichtige Meilensteine speichern (erstes, letztes, jedes 12. Jahr)
            summary_entries = []
            for entry in kpis.schedule.schedule:
                if entry.period == 1 or entry.period % 12 == 0 or entry.period == len(kpis.schedule.schedule):
                    summary_entries.append({
                        "period": entry.period,
                        "date": str(entry.date),
                        "payment": float(entry.payment),
                        "principal": float(entry.principal),
                        "interest": float(entry.interest),
                        "balance": float(entry.balance),
                    })

            loan.amortization_schedule = {
                "entries": summary_entries,
                "total_payments": float(kpis.schedule.total_payments),
                "total_interest": float(kpis.schedule.total_interest),
                "term_months": kpis.schedule.term_months,
            }
            loan.projected_payoff_date = kpis.schedule.payoff_date
            loan.total_interest_projected = kpis.schedule.total_interest
            loan.effective_annual_rate = kpis.schedule.effective_rate
            loan.remaining_term_months = kpis.schedule.term_months

        # Zinsersparnis bei Sondertilgung
        if kpis.extra_payment_analysis:
            loan.interest_saved_with_extra = kpis.extra_payment_analysis.interest_saved

        # Update calculation timestamp
        loan.last_kpi_calculation = datetime.now(timezone.utc)

        await db.flush()

        logger.info(
            "loan_kpis_persisted",
            loan_id=str(loan_id),
            projected_payoff_date=str(loan.projected_payoff_date) if loan.projected_payoff_date else None,
            total_interest=float(loan.total_interest_projected) if loan.total_interest_projected else None,
        )

    # =========================================================================
    # Batch-Berechnung
    # =========================================================================

    async def recalculate_all_loans(
        self,
        db: AsyncSession,
        space_id: Optional[UUID] = None,
    ) -> Dict[str, Any]:
        """
        Berechnet KPIs fuer alle Kredite (oder alle in einem Space).

        Args:
            db: Datenbank-Session
            space_id: Optional: Nur Kredite in diesem Space

        Returns:
            Statistik-Dictionary
        """
        from app.db.models import PrivatLoan

        LOAN_CALCULATIONS.labels(calculation_type="batch_all").inc()

        query = select(PrivatLoan).where(PrivatLoan.is_active == True)
        if space_id:
            query = query.where(PrivatLoan.space_id == space_id)

        result = await db.execute(query)
        loans = result.scalars().all()

        stats = {
            "total": len(loans),
            "calculated": 0,
            "skipped": 0,
            "errors": [],
        }

        for loan in loans:
            try:
                # Standard-Sondertilgung analysieren wenn erlaubt
                extra_amount = None
                if loan.special_repayment_allowed and loan.special_repayment_limit:
                    extra_amount = loan.special_repayment_limit

                await self.calculate_all_kpis(db, loan.id, extra_amount)
                stats["calculated"] += 1

            except Exception as e:
                stats["skipped"] += 1
                stats["errors"].append(f"{loan.id}: {str(e)}")
                logger.warning(
                    "loan_kpi_calculation_failed",
                    loan_id=str(loan.id),
                    error=str(e),
                )

        logger.info(
            "batch_loan_kpi_calculation_completed",
            total=stats["total"],
            calculated=stats["calculated"],
            skipped=stats["skipped"],
        )

        return stats

    # =========================================================================
    # Hilfsmethoden
    # =========================================================================

    def calculate_monthly_payment(
        self,
        principal: Decimal,
        annual_rate: Decimal,
        months: int,
    ) -> Decimal:
        """
        Berechnet die monatliche Annuitaetenrate.

        Formel: M = P * [r(1+r)^n] / [(1+r)^n - 1]

        Args:
            principal: Kreditsumme
            annual_rate: Jahreszins in Prozent
            months: Laufzeit in Monaten

        Returns:
            Monatliche Rate
        """
        if months <= 0:
            return Decimal("0")

        monthly_rate = annual_rate / 100 / 12

        if monthly_rate == 0:
            return principal / months

        # Annuitaetenformel
        rate_factor = (1 + monthly_rate) ** months
        payment = principal * (monthly_rate * rate_factor) / (rate_factor - 1)

        return payment.quantize(Decimal("0.01"), ROUND_HALF_UP)

    def calculate_loan_term(
        self,
        principal: Decimal,
        annual_rate: Decimal,
        monthly_payment: Decimal,
    ) -> int:
        """
        Berechnet die Laufzeit in Monaten.

        Args:
            principal: Kreditsumme
            annual_rate: Jahreszins in Prozent
            monthly_payment: Monatliche Rate

        Returns:
            Laufzeit in Monaten
        """
        import math

        if monthly_payment <= 0:
            return 0

        monthly_rate = float(annual_rate) / 100 / 12

        if monthly_rate == 0:
            return int(principal / monthly_payment)

        # Formel: n = -ln(1 - (P*r)/M) / ln(1+r)
        try:
            numerator = math.log(1 - (float(principal) * monthly_rate / float(monthly_payment)))
            denominator = math.log(1 + monthly_rate)
            months = -numerator / denominator
            return int(math.ceil(months))
        except (ValueError, ZeroDivisionError):
            return 0


# =============================================================================
# Singleton
# =============================================================================

_loan_amortization_service: Optional[LoanAmortizationService] = None
_service_lock = threading.Lock()


def get_loan_amortization_service() -> LoanAmortizationService:
    """Factory fuer LoanAmortizationService Singleton (Thread-safe)."""
    global _loan_amortization_service
    if _loan_amortization_service is None:
        with _service_lock:
            if _loan_amortization_service is None:
                _loan_amortization_service = LoanAmortizationService()
    return _loan_amortization_service
