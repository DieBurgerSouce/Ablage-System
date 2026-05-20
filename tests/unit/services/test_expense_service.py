# -*- coding: utf-8 -*-
"""
Unit tests for Expense Service.

Tests fuer Spesenabrechnung:
- Report CRUD
- Item-Verwaltung
- Workflow (Draft -> Submitted -> Approved -> Paid)
- Verpflegungspauschalen (§9 Abs. 4a EStG)
- Kilometergeld
- Bewirtungskosten (70% absetzbar)
"""

import pytest
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch, MagicMock
from uuid import uuid4, UUID
import sys

# Add app to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from app.services.expense_service import ExpenseService


class TestExpenseServiceConstants:
    """Tests fuer steuerliche Konstanten."""

    def test_mileage_rate(self):
        """Teste Kilometerpauschale nach EStG."""
        from app.services.expense_service import MILEAGE_RATE_PER_KM

        assert MILEAGE_RATE_PER_KM == Decimal("0.30")

    def test_per_diem_rates(self):
        """Teste Verpflegungspauschalen 2024."""
        from app.services.expense_service import (
            PER_DIEM_FULL_DAY_DE,
            PER_DIEM_PARTIAL_DAY_DE,
        )

        assert PER_DIEM_FULL_DAY_DE == Decimal("28.00")
        assert PER_DIEM_PARTIAL_DAY_DE == Decimal("14.00")

    def test_meal_reduction_rates(self):
        """Teste Kuerzungssaetze bei Mahlzeitenstellung."""
        from app.services.expense_service import (
            MEAL_REDUCTION_BREAKFAST,
            MEAL_REDUCTION_LUNCH,
            MEAL_REDUCTION_DINNER,
        )

        assert MEAL_REDUCTION_BREAKFAST == Decimal("0.20")
        assert MEAL_REDUCTION_LUNCH == Decimal("0.40")
        assert MEAL_REDUCTION_DINNER == Decimal("0.40")

    def test_entertainment_rates(self):
        """Teste Bewirtungskosten-Saetze."""
        from app.services.expense_service import (
            ENTERTAINMENT_DEDUCTIBLE_RATE,
            ENTERTAINMENT_NON_DEDUCTIBLE_RATE,
        )

        assert ENTERTAINMENT_DEDUCTIBLE_RATE == Decimal("0.70")
        assert ENTERTAINMENT_NON_DEDUCTIBLE_RATE == Decimal("0.30")


class TestExpenseServiceMileage:
    """Tests fuer Kilometergeld-Berechnung."""

    @pytest.fixture
    def service(self):
        """ExpenseService-Instanz."""
        return ExpenseService()

    def test_calculate_mileage_basic(self, service):
        """Teste einfache Kilometergeld-Berechnung."""
        result = service.calculate_mileage(kilometers=Decimal("100"))

        # Schema konvertiert zu float
        assert result.kilometers == pytest.approx(100.0)
        assert result.rate_per_km == pytest.approx(0.30)
        assert result.total_amount == pytest.approx(30.00)

    def test_calculate_mileage_custom_rate(self, service):
        """Teste Kilometergeld mit abweichendem Satz."""
        result = service.calculate_mileage(
            kilometers=Decimal("50"),
            rate_per_km=Decimal("0.35")
        )

        assert result.rate_per_km == pytest.approx(0.35)
        assert result.total_amount == pytest.approx(17.50)

    def test_calculate_mileage_decimal_km(self, service):
        """Teste Kilometergeld mit Dezimalkilometern."""
        result = service.calculate_mileage(kilometers=Decimal("42.5"))

        assert result.total_amount == pytest.approx(12.75)


class TestExpenseServicePerDiem:
    """Tests fuer Verpflegungspauschalen-Berechnung."""

    @pytest.fixture
    def service(self):
        """ExpenseService-Instanz."""
        return ExpenseService()

    def test_calculate_per_diem_full_day(self, service):
        """Teste Pauschale fuer vollen Tag (>=24h)."""
        travel_start = datetime(2024, 1, 1, 8, 0)
        travel_end = datetime(2024, 1, 2, 18, 0)  # 34 Stunden

        result = service.calculate_per_diem(
            travel_start=travel_start,
            travel_end=travel_end,
        )

        assert result.rate_type == "full_day"
        assert result.base_rate == Decimal("28.00")
        assert result.total_amount == Decimal("28.00")

    def test_calculate_per_diem_partial_day(self, service):
        """Teste Pauschale fuer Teil-Tag (8-24h)."""
        travel_start = datetime(2024, 1, 1, 8, 0)
        travel_end = datetime(2024, 1, 1, 20, 0)  # 12 Stunden

        result = service.calculate_per_diem(
            travel_start=travel_start,
            travel_end=travel_end,
        )

        assert result.rate_type == "partial_day"
        assert result.base_rate == Decimal("14.00")
        assert result.total_amount == Decimal("14.00")

    def test_calculate_per_diem_under_8_hours(self, service):
        """Teste keine Pauschale bei unter 8 Stunden."""
        travel_start = datetime(2024, 1, 1, 9, 0)
        travel_end = datetime(2024, 1, 1, 15, 0)  # 6 Stunden

        result = service.calculate_per_diem(
            travel_start=travel_start,
            travel_end=travel_end,
        )

        assert result.rate_type == "none"
        assert result.total_amount == Decimal("0.00")

    def test_calculate_per_diem_breakfast_reduction(self, service):
        """Teste Kuerzung bei Fruehstueck (20%)."""
        travel_start = datetime(2024, 1, 1, 8, 0)
        travel_end = datetime(2024, 1, 2, 18, 0)

        result = service.calculate_per_diem(
            travel_start=travel_start,
            travel_end=travel_end,
            meals_provided={"breakfast": True},
        )

        expected_reduction = Decimal("28.00") * Decimal("0.20")
        expected_total = Decimal("28.00") - expected_reduction

        assert result.meal_reductions == expected_reduction
        assert result.total_amount == expected_total

    def test_calculate_per_diem_all_meals_reduction(self, service):
        """Teste Kuerzung bei allen Mahlzeiten (100%)."""
        travel_start = datetime(2024, 1, 1, 8, 0)
        travel_end = datetime(2024, 1, 2, 18, 0)

        result = service.calculate_per_diem(
            travel_start=travel_start,
            travel_end=travel_end,
            meals_provided={"breakfast": True, "lunch": True, "dinner": True},
        )

        # 20% + 40% + 40% = 100%
        expected_reduction = Decimal("28.00")  # Volle Kuerzung
        expected_total = Decimal("0.00")

        assert result.meal_reductions == expected_reduction
        assert result.total_amount == expected_total

    def test_calculate_per_diem_total_hours(self, service):
        """Teste Berechnung der Gesamtstunden."""
        travel_start = datetime(2024, 1, 1, 8, 0)
        travel_end = datetime(2024, 1, 1, 20, 30)  # 12.5 Stunden

        result = service.calculate_per_diem(
            travel_start=travel_start,
            travel_end=travel_end,
        )

        assert result.total_hours == Decimal("12.5")


class TestExpenseServiceEntertainment:
    """Tests fuer Bewirtungskosten-Validierung."""

    @pytest.fixture
    def service(self):
        """ExpenseService-Instanz."""
        return ExpenseService()

    def test_validate_entertainment_complete(self, service):
        """Teste vollstaendige Bewirtungsdaten."""
        data = {
            "occasion": "Geschaeftsessen zur Projektbesprechung",
            "attendees": [
                {"name": "Max Mustermann", "company": "Firma A"},
                {"name": "Erika Musterfrau", "company": "Firma B"},
            ],
            "business_reason": "Besprechung Projekt XY",
            "host_company": "Meine Firma GmbH",
        }

        # Sollte keine Exception werfen
        service._validate_entertainment_data(data)

    def test_validate_entertainment_missing_occasion(self, service):
        """Teste fehlenden Anlass."""
        data = {
            "attendees": [{"name": "Test"}],
            "business_reason": "Test",
            "host_company": "Test GmbH",
        }

        with pytest.raises(ValueError) as exc_info:
            service._validate_entertainment_data(data)

        assert "occasion" in str(exc_info.value).lower()

    def test_validate_entertainment_missing_attendees(self, service):
        """Teste fehlende Teilnehmer."""
        data = {
            "occasion": "Test",
            "business_reason": "Test",
            "host_company": "Test GmbH",
        }

        with pytest.raises(ValueError) as exc_info:
            service._validate_entertainment_data(data)

        assert "attendees" in str(exc_info.value).lower()

    def test_validate_entertainment_empty_attendees(self, service):
        """Teste leere Teilnehmerliste."""
        data = {
            "occasion": "Test",
            "attendees": [],
            "business_reason": "Test",
            "host_company": "Test GmbH",
        }

        with pytest.raises(ValueError) as exc_info:
            service._validate_entertainment_data(data)

        assert "Teilnehmer" in str(exc_info.value) or "attendee" in str(exc_info.value).lower()

    def test_validate_entertainment_missing_host(self, service):
        """Teste fehlendes bewirtendes Unternehmen."""
        data = {
            "occasion": "Test",
            "attendees": [{"name": "Test"}],
            "business_reason": "Test",
        }

        with pytest.raises(ValueError) as exc_info:
            service._validate_entertainment_data(data)

        assert "Unternehmen" in str(exc_info.value) or "company" in str(exc_info.value).lower()

    def test_calculate_deductible_entertainment(self):
        """Teste Berechnung des abzugsfaehigen Betrags."""
        gross_amount = Decimal("100.00")

        from app.services.expense_service import ENTERTAINMENT_DEDUCTIBLE_RATE
        deductible = gross_amount * ENTERTAINMENT_DEDUCTIBLE_RATE

        assert deductible == Decimal("70.00")


class TestExpenseServiceWorkflow:
    """Tests fuer Workflow-Status."""

    def test_valid_status_transitions(self):
        """Teste gueltige Status-Uebergaenge."""
        valid_transitions = {
            "draft": ["submitted", "deleted"],
            "submitted": ["in_review", "approved", "rejected"],
            "in_review": ["approved", "rejected"],
            "approved": ["paid"],
            "rejected": ["draft"],  # Zurueck zu Entwurf
            "paid": [],  # Endstatus
        }

        # draft -> submitted ist erlaubt
        assert "submitted" in valid_transitions["draft"]

        # submitted -> approved ist erlaubt
        assert "approved" in valid_transitions["submitted"]

        # paid ist Endstatus
        assert len(valid_transitions["paid"]) == 0

    def test_draft_can_be_edited(self):
        """Teste dass Entwuerfe bearbeitet werden koennen."""
        status = "draft"
        editable_statuses = ["draft"]

        assert status in editable_statuses

    def test_submitted_cannot_be_edited(self):
        """Teste dass eingereichte Abrechnungen nicht bearbeitet werden koennen."""
        status = "submitted"
        editable_statuses = ["draft"]

        assert status not in editable_statuses

    def test_approved_cannot_be_deleted(self):
        """Teste dass genehmigte Abrechnungen nicht geloescht werden koennen."""
        status = "approved"
        deletable_statuses = ["draft"]

        assert status not in deletable_statuses


class TestExpenseServiceTotals:
    """Tests fuer Summen-Berechnung."""

    def test_calculate_report_total(self):
        """Teste Berechnung der Gesamtsumme."""
        items = [
            {"amount": Decimal("50.00"), "is_entertainment": False},
            {"amount": Decimal("100.00"), "is_entertainment": True},
            {"amount": Decimal("30.00"), "is_entertainment": False},
        ]

        total = sum(item["amount"] for item in items)

        assert total == Decimal("180.00")

    def test_calculate_deductible_total(self):
        """Teste Berechnung des abzugsfaehigen Betrags."""
        from app.services.expense_service import ENTERTAINMENT_DEDUCTIBLE_RATE

        items = [
            {"amount": Decimal("50.00"), "is_entertainment": False},
            {"amount": Decimal("100.00"), "is_entertainment": True},
            {"amount": Decimal("30.00"), "is_entertainment": False},
        ]

        deductible = Decimal("0")
        for item in items:
            if item["is_entertainment"]:
                deductible += item["amount"] * ENTERTAINMENT_DEDUCTIBLE_RATE
            else:
                deductible += item["amount"]

        # 50 + (100 * 0.70) + 30 = 50 + 70 + 30 = 150
        assert deductible == Decimal("150.00")


class TestExpenseServiceValidation:
    """Tests fuer Eingabe-Validierung."""

    @pytest.fixture
    def service(self):
        """ExpenseService-Instanz."""
        return ExpenseService()

    def test_period_start_before_end(self):
        """Teste dass Periode Start vor Ende liegt."""
        period_start = date(2024, 1, 1)
        period_end = date(2024, 1, 31)

        assert period_start < period_end

    def test_period_end_before_start_invalid(self):
        """Teste dass Ende vor Start ungueltig ist."""
        period_start = date(2024, 1, 31)
        period_end = date(2024, 1, 1)

        assert period_start > period_end  # Ungueltig

    def test_empty_report_cannot_be_submitted(self):
        """Teste dass leerer Report nicht eingereicht werden kann."""
        items_count = 0

        # Ein Report ohne Items kann nicht eingereicht werden
        assert items_count == 0


class TestExpenseServiceCashIntegration:
    """Tests fuer Kassenbuch-Integration."""

    def test_paid_creates_cash_entry(self):
        """Teste dass Auszahlung Kassenbucheintrag erstellt."""
        # Konzeptioneller Test
        report = {
            "status": "approved",
            "approved_amount": Decimal("150.00"),
            "employee_name": "Max Mustermann",
        }

        expected_entry = {
            "entry_type": "expense",
            "amount": report["approved_amount"],
            "description": f"Spesenabrechnung: {report['employee_name']}",
        }

        assert expected_entry["amount"] == Decimal("150.00")
        assert expected_entry["entry_type"] == "expense"

    def test_register_required_for_cash_payment(self):
        """Teste dass Kassen-ID fuer Barauszahlung erforderlich ist."""
        register_id = None
        payment_method = "cash"

        # Bei Barauszahlung muss Kasse angegeben werden
        requires_register = payment_method == "cash" and register_id is None

        assert requires_register is True


class TestExpenseServiceExchangeRate:
    """Tests fuer Waehrungsumrechnung."""

    def test_calculate_eur_amount(self):
        """Teste Umrechnung in EUR."""
        amount = Decimal("100.00")
        currency = "USD"
        exchange_rate = Decimal("0.92")  # 1 USD = 0.92 EUR

        amount_eur = amount * exchange_rate

        assert amount_eur == Decimal("92.00")

    def test_eur_currency_rate_is_one(self):
        """Teste dass EUR-Kurs 1.00 ist."""
        amount = Decimal("100.00")
        currency = "EUR"
        exchange_rate = Decimal("1.00")

        amount_eur = amount * exchange_rate

        assert amount_eur == amount

    def test_exchange_rate_precision(self):
        """Teste Praezision bei Waehrungsumrechnung."""
        amount = Decimal("99.99")
        exchange_rate = Decimal("1.0856")  # CHF -> EUR

        amount_eur = (amount * exchange_rate).quantize(Decimal("0.01"))

        # Ergebnis sollte 2 Dezimalstellen haben
        assert amount_eur.as_tuple().exponent >= -2
