"""Tests fuer den Loan KPI Service.

Testet die Berechnung aller Kredit-KPIs:
- Tilgungsplan
- Restschuld
- Zinskosten
- Sondertilgungs-Auswirkungen
"""

import pytest
from decimal import Decimal
from datetime import date, timedelta
from uuid import uuid4
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.kpi.loan_kpi_service import (
    LoanKPIService,
    AmortizationSchedule,
    AmortizationEntry,
    ExtraPaymentImpact,
    LoanComparison,
)


class TestAmortizationCalculations:
    """Tests fuer Tilgungsplan-Berechnungen."""

    def setup_method(self) -> None:
        """Setup fuer jeden Test."""
        self.service = LoanKPIService(db=MagicMock())

    def test_monthly_payment_calculation(self) -> None:
        """Monatliche Rate wird korrekt berechnet."""
        principal = Decimal("100000")
        annual_rate = Decimal("5.0")  # 5%
        term_months = 120  # 10 Jahre

        result = self.service._calc_monthly_payment(principal, annual_rate, term_months)

        # Erwartete Rate: ca. 1061€
        assert result > Decimal("1000")
        assert result < Decimal("1100")

    def test_monthly_payment_zero_rate(self) -> None:
        """Monatliche Rate bei 0% Zinsen."""
        principal = Decimal("100000")
        annual_rate = Decimal("0")
        term_months = 100

        result = self.service._calc_monthly_payment(principal, annual_rate, term_months)

        # 100000 / 100 = 1000
        assert result == Decimal("1000.00")

    def test_generate_schedule(self) -> None:
        """Tilgungsplan wird korrekt generiert."""
        schedule = self.service._generate_schedule(
            principal=Decimal("100000"),
            annual_rate=Decimal("5.0"),
            monthly_payment=Decimal("1061"),
            start_date=date.today(),
        )

        assert isinstance(schedule, AmortizationSchedule)
        assert len(schedule.schedule) > 0
        assert schedule.total_interest > Decimal("0")
        assert schedule.remaining_months > 0

    def test_total_interest_calculation(self) -> None:
        """Gesamtzinsen werden korrekt berechnet."""
        schedule = self.service._generate_schedule(
            principal=Decimal("100000"),
            annual_rate=Decimal("5.0"),
            monthly_payment=Decimal("1061"),
            start_date=date.today(),
        )

        # Bei 100k, 5%, ca. 1061€/Monat: ca. 27.000€ Zinsen
        assert schedule.total_interest > Decimal("25000")
        assert schedule.total_interest < Decimal("30000")

    def test_principal_portion_increases_over_time(self) -> None:
        """Tilgungsanteil steigt ueber die Zeit."""
        schedule = self.service._generate_schedule(
            principal=Decimal("100000"),
            annual_rate=Decimal("5.0"),
            monthly_payment=Decimal("1061"),
            start_date=date.today(),
        )

        first_entry = schedule.schedule[0]
        last_entry = schedule.schedule[-1]

        # Tilgungsanteil sollte im letzten Monat hoeher sein
        assert last_entry.principal > first_entry.principal

    def test_interest_portion_decreases_over_time(self) -> None:
        """Zinsanteil sinkt ueber die Zeit."""
        schedule = self.service._generate_schedule(
            principal=Decimal("100000"),
            annual_rate=Decimal("5.0"),
            monthly_payment=Decimal("1061"),
            start_date=date.today(),
        )

        first_entry = schedule.schedule[0]
        last_entry = schedule.schedule[-1]

        # Zinsanteil sollte im letzten Monat niedriger sein
        assert last_entry.interest < first_entry.interest

    def test_final_balance_is_zero(self) -> None:
        """Restschuld am Ende ist 0."""
        schedule = self.service._generate_schedule(
            principal=Decimal("100000"),
            annual_rate=Decimal("5.0"),
            monthly_payment=Decimal("1061"),
            start_date=date.today(),
        )

        last_entry = schedule.schedule[-1]
        assert last_entry.balance == Decimal("0")


class TestExtraPaymentImpact:
    """Tests fuer Sondertilgungs-Auswirkungen."""

    def setup_method(self) -> None:
        self.service = LoanKPIService(db=MagicMock())

    def test_extra_payment_reduces_term(self) -> None:
        """Sondertilgung reduziert Laufzeit."""
        # Standard
        standard = self.service._generate_schedule(
            principal=Decimal("100000"),
            annual_rate=Decimal("5.0"),
            monthly_payment=Decimal("1061"),
            start_date=date.today(),
        )

        # Mit 200€ extra/Monat
        with_extra = self.service._generate_schedule(
            principal=Decimal("100000"),
            annual_rate=Decimal("5.0"),
            monthly_payment=Decimal("1061"),
            start_date=date.today(),
            extra_payment=Decimal("200"),
        )

        # Sollte Laufzeit deutlich reduzieren
        assert with_extra.remaining_months < standard.remaining_months
        months_saved = standard.remaining_months - with_extra.remaining_months
        assert months_saved > 15  # Mindestens 15 Monate gespart

    def test_extra_payment_reduces_interest(self) -> None:
        """Sondertilgung reduziert Gesamtzinsen."""
        # Standard
        standard = self.service._generate_schedule(
            principal=Decimal("100000"),
            annual_rate=Decimal("5.0"),
            monthly_payment=Decimal("1061"),
            start_date=date.today(),
        )

        # Mit 200€ extra/Monat
        with_extra = self.service._generate_schedule(
            principal=Decimal("100000"),
            annual_rate=Decimal("5.0"),
            monthly_payment=Decimal("1061"),
            start_date=date.today(),
            extra_payment=Decimal("200"),
        )

        # Sollte Zinsen deutlich reduzieren
        assert with_extra.total_interest < standard.total_interest
        interest_saved = standard.total_interest - with_extra.total_interest
        assert interest_saved > Decimal("5000")  # Mindestens 5000€ gespart

    @pytest.mark.asyncio
    async def test_calculate_extra_payment_impact(self) -> None:
        """calculate_extra_payment_impact gibt korrekte Werte zurueck."""
        loan_id = uuid4()
        mock_loan = MagicMock()
        mock_loan.principal_amount = Decimal("100000")
        mock_loan.remaining_balance = Decimal("100000")
        mock_loan.interest_rate = Decimal("5.0")
        mock_loan.monthly_payment = Decimal("1061")
        mock_loan.start_date = date.today()

        with patch.object(
            self.service, "_get_loan", return_value=mock_loan
        ):
            result = await self.service.calculate_extra_payment_impact(
                loan_id, Decimal("200")
            )

            assert isinstance(result, ExtraPaymentImpact)
            assert result.extra_monthly == Decimal("200")
            assert result.months_saved > 0
            assert result.interest_saved > Decimal("0")


class TestLoanComparisons:
    """Tests fuer Kredit-Vergleiche."""

    def setup_method(self) -> None:
        self.service = LoanKPIService(db=MagicMock())

    @pytest.mark.asyncio
    async def test_compare_loan_options(self) -> None:
        """Verschiedene Kreditoptionen werden verglichen."""
        principal = Decimal("100000")
        options = [
            {"name": "Kurz/Niedrig", "rate": 4.0, "term_months": 60},
            {"name": "Lang/Hoch", "rate": 5.5, "term_months": 180},
        ]

        result = await self.service.compare_loan_options(principal, options)

        assert len(result) == 2
        assert all(isinstance(r, LoanComparison) for r in result)

        # Kuerzere Laufzeit = hoehere Rate aber weniger Zinsen
        short_option = result[0]
        long_option = result[1]

        assert short_option.monthly_payment > long_option.monthly_payment
        assert short_option.total_interest < long_option.total_interest


class TestRemainingBalance:
    """Tests fuer Restschuld-Berechnungen."""

    def setup_method(self) -> None:
        self.service = LoanKPIService(db=MagicMock())

    @pytest.mark.asyncio
    async def test_remaining_balance_at_start(self) -> None:
        """Restschuld am Start gleich Kreditsumme."""
        loan_id = uuid4()
        mock_loan = MagicMock()
        mock_loan.principal_amount = Decimal("100000")
        mock_loan.interest_rate = Decimal("5.0")
        mock_loan.monthly_payment = Decimal("1061")
        mock_loan.start_date = date.today()

        with patch.object(
            self.service, "_get_loan", return_value=mock_loan
        ):
            result = await self.service.calculate_remaining_balance(
                loan_id, date.today()
            )

            assert result == Decimal("100000")

    @pytest.mark.asyncio
    async def test_remaining_balance_after_one_year(self) -> None:
        """Restschuld nach einem Jahr."""
        loan_id = uuid4()
        start = date.today() - timedelta(days=365)
        mock_loan = MagicMock()
        mock_loan.principal_amount = Decimal("100000")
        mock_loan.interest_rate = Decimal("5.0")
        mock_loan.monthly_payment = Decimal("1061")
        mock_loan.start_date = start

        with patch.object(
            self.service, "_get_loan", return_value=mock_loan
        ):
            result = await self.service.calculate_remaining_balance(
                loan_id, date.today()
            )

            # Nach 1 Jahr: weniger als 100k aber mehr als 90k
            assert result < Decimal("100000")
            assert result > Decimal("90000")


class TestPayoffDate:
    """Tests fuer Tilgungs-Projektionen."""

    def setup_method(self) -> None:
        self.service = LoanKPIService(db=MagicMock())

    @pytest.mark.asyncio
    async def test_payoff_date_calculation(self) -> None:
        """Voraussichtliches Rueckzahlungsdatum."""
        loan_id = uuid4()
        mock_loan = MagicMock()
        mock_loan.principal_amount = Decimal("100000")
        mock_loan.interest_rate = Decimal("5.0")
        mock_loan.monthly_payment = Decimal("1061")
        mock_loan.start_date = date.today()

        with patch.object(
            self.service, "_get_loan", return_value=mock_loan
        ):
            result = await self.service.calculate_payoff_date(loan_id)

            # Sollte ca. 10 Jahre in der Zukunft liegen
            expected = date.today() + timedelta(days=120 * 30)
            assert abs((result - expected).days) < 60


class TestLoanKPIServiceIntegration:
    """Integrationstests fuer den gesamten Service."""

    @pytest.fixture
    def mock_db(self) -> AsyncMock:
        return AsyncMock()

    @pytest.fixture
    def service(self, mock_db: AsyncMock) -> LoanKPIService:
        return LoanKPIService(db=mock_db)

    @pytest.mark.asyncio
    async def test_calculate_amortization_schedule_returns_result(
        self, service: LoanKPIService
    ) -> None:
        """calculate_amortization_schedule gibt AmortizationSchedule zurueck."""
        loan_id = uuid4()
        mock_loan = MagicMock()
        mock_loan.id = loan_id
        mock_loan.principal_amount = Decimal("100000")
        mock_loan.interest_rate = Decimal("5.0")
        mock_loan.monthly_payment = Decimal("1061")
        mock_loan.term_months = 120
        mock_loan.start_date = date.today()

        with patch.object(
            service, "_get_loan", return_value=mock_loan
        ):
            result = await service.calculate_amortization_schedule(loan_id)

            assert isinstance(result, AmortizationSchedule)
            assert len(result.schedule) > 0
            assert all(isinstance(e, AmortizationEntry) for e in result.schedule)
            assert result.total_interest > Decimal("0")
            assert result.payoff_date > date.today()

    @pytest.mark.asyncio
    async def test_calculate_extra_payment_impact_returns_result(
        self, service: LoanKPIService
    ) -> None:
        """calculate_extra_payment_impact gibt ExtraPaymentImpact zurueck."""
        loan_id = uuid4()
        mock_loan = MagicMock()
        mock_loan.id = loan_id
        mock_loan.principal_amount = Decimal("100000")
        mock_loan.remaining_balance = Decimal("100000")
        mock_loan.interest_rate = Decimal("5.0")
        mock_loan.monthly_payment = Decimal("1061")
        mock_loan.term_months = 120
        mock_loan.start_date = date.today()

        extra_monthly = Decimal("200")

        with patch.object(
            service, "_get_loan", return_value=mock_loan
        ):
            result = await service.calculate_extra_payment_impact(loan_id, extra_monthly)

            assert isinstance(result, ExtraPaymentImpact)
            assert result.extra_monthly == extra_monthly
            assert result.months_saved > 0
            assert result.interest_saved > Decimal("0")
            assert result.new_payoff_date < date.today() + timedelta(days=120 * 30)
