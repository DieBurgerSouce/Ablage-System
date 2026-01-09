"""
Unit-Tests fuer LoanScenarioService

Testet:
- Service-Initialisierung
- Dataclass-Strukturen
- Hilfsmethoden (synchron)
- Methoden-Existenz
"""

import pytest
from datetime import date, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from app.services.privat.loan_scenario_service import (
    LoanScenarioService,
    get_loan_scenario_service,
    AmortizationEntry,
    ExtraPaymentScenario,
    RefinancingScenario,
    PaymentChangeScenario,
    LoanComparison,
    TilgungsPlanResponse,
)


class TestLoanScenarioServiceInit:
    """Tests fuer Service-Initialisierung."""

    def test_service_initialization(self) -> None:
        """Testet Service-Initialisierung."""
        service = LoanScenarioService()
        assert service is not None

    def test_singleton_pattern(self) -> None:
        """Testet dass Service ein Singleton ist."""
        service1 = LoanScenarioService()
        service2 = LoanScenarioService()
        assert service1 is service2


class TestAmortizationEntryDataClass:
    """Tests fuer AmortizationEntry Datenstruktur."""

    def test_amortization_entry_creation(self) -> None:
        """Testet AmortizationEntry Erstellung."""
        entry = AmortizationEntry(
            month=1,
            date=date.today(),
            opening_balance=Decimal("100000"),
            payment=Decimal("1000"),
            principal=Decimal("500"),
            interest=Decimal("500"),
            closing_balance=Decimal("99500"),
        )

        assert entry.month == 1
        assert entry.payment == Decimal("1000")
        assert entry.extra_payment == Decimal("0")  # Default


class TestExtraPaymentScenarioDataClass:
    """Tests fuer ExtraPaymentScenario Datenstruktur."""

    def test_extra_payment_scenario_creation(self) -> None:
        """Testet ExtraPaymentScenario Erstellung."""
        loan_id = uuid4()
        scenario = ExtraPaymentScenario(
            loan_id=loan_id,
            loan_name="Test Kredit",
            original_remaining_balance=Decimal("200000"),
            original_monthly_payment=Decimal("1200"),
            original_interest_rate=Decimal("3.5"),
            original_remaining_months=180,
            original_total_interest=Decimal("50000"),
            extra_payment_amount=Decimal("10000"),
            new_remaining_balance=Decimal("190000"),
            new_remaining_months=165,
            new_total_interest=Decimal("42000"),
            months_saved=15,
            interest_saved=Decimal("8000"),
            new_payoff_date=date.today() + timedelta(days=165 * 30),
        )

        assert scenario.loan_id == loan_id
        assert scenario.months_saved == 15
        assert scenario.interest_saved == Decimal("8000")


class TestRefinancingScenarioDataClass:
    """Tests fuer RefinancingScenario Datenstruktur."""

    def test_refinancing_scenario_creation(self) -> None:
        """Testet RefinancingScenario Erstellung."""
        loan_id = uuid4()
        scenario = RefinancingScenario(
            loan_id=loan_id,
            loan_name="Test Kredit",
            current_balance=Decimal("150000"),
            current_interest_rate=Decimal("4.5"),
            current_monthly_payment=Decimal("1500"),
            current_remaining_months=120,
            current_total_remaining_interest=Decimal("30000"),
            new_interest_rate=Decimal("2.5"),
            new_monthly_payment=Decimal("1350"),
            new_remaining_months=120,
            new_total_interest=Decimal("12000"),
            prepayment_penalty=Decimal("2000"),
            refinancing_costs=Decimal("3000"),
            total_upfront_costs=Decimal("5000"),
            interest_savings=Decimal("18000"),
            net_savings=Decimal("13000"),
            break_even_months=34,
            is_recommended=True,
            recommendation_reason="Empfohlen! Netto-Ersparnis von 13000 EUR.",
        )

        assert scenario.is_recommended is True
        assert scenario.net_savings == Decimal("13000")


class TestPaymentChangeScenarioDataClass:
    """Tests fuer PaymentChangeScenario Datenstruktur."""

    def test_payment_change_scenario_creation(self) -> None:
        """Testet PaymentChangeScenario Erstellung."""
        loan_id = uuid4()
        scenario = PaymentChangeScenario(
            loan_id=loan_id,
            loan_name="Test Kredit",
            original_payment=Decimal("1000"),
            original_remaining_months=120,
            original_total_interest=Decimal("20000"),
            new_payment=Decimal("1200"),
            new_remaining_months=95,
            new_total_interest=Decimal("14000"),
            payment_change=Decimal("200"),
            months_change=-25,
            interest_change=Decimal("-6000"),
            is_viable=True,
            warning_message=None,
        )

        assert scenario.is_viable is True
        assert scenario.months_change == -25


class TestTilgungsPlanResponseDataClass:
    """Tests fuer TilgungsPlanResponse Datenstruktur."""

    def test_tilgungsplan_response_creation(self) -> None:
        """Testet TilgungsPlanResponse Erstellung."""
        loan_id = uuid4()
        schedule = [
            AmortizationEntry(
                month=i,
                date=date.today() + timedelta(days=i * 30),
                opening_balance=Decimal(str(100000 - i * 1000)),
                payment=Decimal("1200"),
                principal=Decimal("1000"),
                interest=Decimal("200"),
                closing_balance=Decimal(str(99000 - i * 1000)),
            )
            for i in range(1, 4)
        ]

        response = TilgungsPlanResponse(
            loan_id=loan_id,
            loan_name="Test Kredit",
            principal=Decimal("100000"),
            interest_rate=Decimal("3.5"),
            monthly_payment=Decimal("1200"),
            start_date=date.today(),
            total_months=100,
            total_interest=Decimal("20000"),
            total_payments=Decimal("120000"),
            payoff_date=date.today() + timedelta(days=100 * 30),
            schedule=schedule,
        )

        assert response.total_months == 100
        assert len(response.schedule) == 3


class TestHelperMethods:
    """Tests fuer synchrone Hilfsmethoden."""

    @pytest.fixture
    def service(self) -> LoanScenarioService:
        return LoanScenarioService()

    def test_calculate_remaining_months_basic(self, service: LoanScenarioService) -> None:
        """Testet Restlaufzeit-Berechnung."""
        months = service._calculate_remaining_months(
            balance=Decimal("100000"),
            payment=Decimal("1000"),
            monthly_rate=Decimal("0.003"),  # ca. 3.6% p.a.
        )

        # Bei ca. 3.6% Zinsen und 1000 EUR Rate sollte Laufzeit ~115 Monate sein
        assert 100 < months < 130

    def test_calculate_remaining_months_zero_rate(self, service: LoanScenarioService) -> None:
        """Testet Restlaufzeit-Berechnung ohne Zinsen."""
        months = service._calculate_remaining_months(
            balance=Decimal("100000"),
            payment=Decimal("1000"),
            monthly_rate=Decimal("0"),
        )

        # Ohne Zinsen: 100000 / 1000 = 100 Monate
        assert months == 100

    def test_calculate_remaining_months_too_low_payment(self, service: LoanScenarioService) -> None:
        """Testet wenn Rate die Zinsen nicht deckt."""
        months = service._calculate_remaining_months(
            balance=Decimal("100000"),
            payment=Decimal("100"),  # Zu wenig, deckt nicht mal Zinsen
            monthly_rate=Decimal("0.005"),  # 6% p.a. = 500 EUR Zinsen/Monat
        )

        # Sollte "unendlich" (9999) zurueckgeben
        assert months == 9999

    def test_calculate_total_interest(self, service: LoanScenarioService) -> None:
        """Testet Gesamtzins-Berechnung."""
        interest = service._calculate_total_interest(
            balance=Decimal("100000"),
            payment=Decimal("1000"),
            monthly_rate=Decimal("0.003"),
            months=115,
        )

        # Total interest = 115 * 1000 - 100000 = 15000
        assert interest > Decimal("0")
        assert interest == Decimal("15000.00")

    def test_calculate_monthly_payment(self, service: LoanScenarioService) -> None:
        """Testet monatliche Rate-Berechnung."""
        payment = service._calculate_monthly_payment(
            principal=Decimal("100000"),
            monthly_rate=Decimal("0.003"),
            term_months=120,
        )

        # Sollte ca. 960-1000 EUR sein
        assert Decimal("900") < payment < Decimal("1100")

    def test_calculate_monthly_payment_zero_rate(self, service: LoanScenarioService) -> None:
        """Testet monatliche Rate ohne Zinsen."""
        payment = service._calculate_monthly_payment(
            principal=Decimal("100000"),
            monthly_rate=Decimal("0"),
            term_months=100,
        )

        # Ohne Zinsen: 100000 / 100 = 1000
        assert payment == Decimal("1000.00")

    def test_calculate_prepayment_penalty(self, service: LoanScenarioService) -> None:
        """Testet Vorfaelligkeitsentschaedigung-Berechnung."""
        penalty = service._calculate_prepayment_penalty(
            remaining_balance=Decimal("100000"),
            monthly_rate=Decimal("0.003"),  # 3.6% p.a.
        )

        # Min(1% * 100000, 6 * 0.003 * 100000) = Min(1000, 1800) = 1000
        assert penalty == Decimal("1000.00")

    def test_generate_amortization_schedule(self, service: LoanScenarioService) -> None:
        """Testet Tilgungsplan-Generierung."""
        schedule = service._generate_amortization_schedule(
            principal=Decimal("10000"),
            payment=Decimal("1000"),
            monthly_rate=Decimal("0.005"),
            start_date=date.today(),
        )

        # Sollte ca. 10-11 Eintraege haben
        assert len(schedule) > 0
        assert len(schedule) <= 15

        # Erste Zahlung
        first = schedule[0]
        assert first.month == 1
        assert first.opening_balance == Decimal("10000")

        # Letzte Zahlung sollte nahe 0 sein
        last = schedule[-1]
        assert last.closing_balance <= Decimal("1")

        # Zahlungen sollten absteigend sein (Restschuld)
        for i in range(1, len(schedule)):
            assert schedule[i].opening_balance < schedule[i - 1].opening_balance


class TestServiceMethodsExist:
    """Tests dass alle wichtigen Service-Methoden existieren."""

    @pytest.fixture
    def service(self) -> LoanScenarioService:
        return LoanScenarioService()

    def test_service_has_simulate_extra_payment_method(self, service: LoanScenarioService) -> None:
        """Testet dass Service simulate_extra_payment Methode hat."""
        assert hasattr(service, "simulate_extra_payment")
        assert callable(getattr(service, "simulate_extra_payment"))

    def test_service_has_simulate_refinancing_method(self, service: LoanScenarioService) -> None:
        """Testet dass Service simulate_refinancing Methode hat."""
        assert hasattr(service, "simulate_refinancing")
        assert callable(getattr(service, "simulate_refinancing"))

    def test_service_has_simulate_payment_change_method(self, service: LoanScenarioService) -> None:
        """Testet dass Service simulate_payment_change Methode hat."""
        assert hasattr(service, "simulate_payment_change")
        assert callable(getattr(service, "simulate_payment_change"))

    def test_service_has_generate_full_amortization_method(self, service: LoanScenarioService) -> None:
        """Testet dass Service generate_full_amortization Methode hat."""
        assert hasattr(service, "generate_full_amortization")
        assert callable(getattr(service, "generate_full_amortization"))

    def test_service_has_compare_scenarios_method(self, service: LoanScenarioService) -> None:
        """Testet dass Service compare_scenarios Methode hat."""
        assert hasattr(service, "compare_scenarios")
        assert callable(getattr(service, "compare_scenarios"))


class TestHelperMethodsExist:
    """Tests dass alle Hilfsmethoden existieren."""

    @pytest.fixture
    def service(self) -> LoanScenarioService:
        return LoanScenarioService()

    def test_service_has_calculate_remaining_months_method(self, service: LoanScenarioService) -> None:
        """Testet dass Service _calculate_remaining_months Methode hat."""
        assert hasattr(service, "_calculate_remaining_months")
        assert callable(getattr(service, "_calculate_remaining_months"))

    def test_service_has_calculate_total_interest_method(self, service: LoanScenarioService) -> None:
        """Testet dass Service _calculate_total_interest Methode hat."""
        assert hasattr(service, "_calculate_total_interest")
        assert callable(getattr(service, "_calculate_total_interest"))

    def test_service_has_calculate_monthly_payment_method(self, service: LoanScenarioService) -> None:
        """Testet dass Service _calculate_monthly_payment Methode hat."""
        assert hasattr(service, "_calculate_monthly_payment")
        assert callable(getattr(service, "_calculate_monthly_payment"))

    def test_service_has_calculate_prepayment_penalty_method(self, service: LoanScenarioService) -> None:
        """Testet dass Service _calculate_prepayment_penalty Methode hat."""
        assert hasattr(service, "_calculate_prepayment_penalty")
        assert callable(getattr(service, "_calculate_prepayment_penalty"))

    def test_service_has_generate_amortization_schedule_method(self, service: LoanScenarioService) -> None:
        """Testet dass Service _generate_amortization_schedule Methode hat."""
        assert hasattr(service, "_generate_amortization_schedule")
        assert callable(getattr(service, "_generate_amortization_schedule"))


class TestGetServiceFunction:
    """Tests fuer get_loan_scenario_service Factory."""

    def test_get_service_function_exists(self) -> None:
        """Testet dass get_loan_scenario_service existiert."""
        assert get_loan_scenario_service is not None
        assert callable(get_loan_scenario_service)

    def test_get_service_returns_instance(self) -> None:
        """Testet dass get_loan_scenario_service eine Instanz zurueckgibt."""
        service = get_loan_scenario_service()
        assert isinstance(service, LoanScenarioService)
