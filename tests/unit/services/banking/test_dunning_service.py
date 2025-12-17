# -*- coding: utf-8 -*-
"""
Tests fuer DunningService.

Testet:
- Mahnkonfiguration
- Ueberfaelligkeits-Erkennung
- Gebuehren-Berechnung
- Verzugszinsen
- Empfohlene Aktionen
"""

import pytest
from datetime import datetime, date, timedelta
from decimal import Decimal
from uuid import uuid4

from app.services.banking.dunning_service import (
    DunningService,
    DunningConfig,
    DunningCandidate,
    DunningAction,
)
from app.services.banking.models import DunningLevel


class TestDunningConfig:
    """Tests fuer Mahnkonfiguration."""

    def test_default_config(self):
        """Sollte Standard-Konfiguration haben."""
        config = DunningConfig()

        assert config.reminder_after_days == 7
        assert config.first_dunning_after_days == 14
        assert config.second_dunning_after_days == 28
        assert config.final_dunning_after_days == 42
        assert config.first_dunning_fee == Decimal("5.00")
        assert config.second_dunning_fee == Decimal("10.00")
        assert config.final_dunning_fee == Decimal("15.00")

    def test_custom_config(self):
        """Sollte benutzerdefinierte Konfiguration akzeptieren."""
        config = DunningConfig(
            reminder_after_days=5,
            first_dunning_after_days=10,
            first_dunning_fee=Decimal("10.00"),
        )

        assert config.reminder_after_days == 5
        assert config.first_dunning_after_days == 10
        assert config.first_dunning_fee == Decimal("10.00")


class TestRecommendedAction:
    """Tests fuer empfohlene Mahnaktion."""

    @pytest.fixture
    def service(self) -> DunningService:
        return DunningService()

    def test_reminder_for_early_overdue(self, service: DunningService):
        """Sollte Zahlungserinnerung empfehlen wenn weniger als 14 Tage."""
        action = service._get_recommended_action(
            days_overdue=5,
            current_level=DunningLevel.NOT_STARTED,
        )

        assert action == DunningAction.REMINDER

    def test_first_dunning_recommended(self, service: DunningService):
        """Sollte 1. Mahnung empfehlen ab 14 Tage."""
        action = service._get_recommended_action(
            days_overdue=15,
            current_level=DunningLevel.NOT_STARTED,
        )

        assert action == DunningAction.FIRST_DUNNING

    def test_second_dunning_recommended(self, service: DunningService):
        """Sollte 2. Mahnung empfehlen ab 28 Tage."""
        action = service._get_recommended_action(
            days_overdue=30,
            current_level=DunningLevel.FIRST_REMINDER,
        )

        assert action == DunningAction.SECOND_DUNNING

    def test_final_dunning_recommended(self, service: DunningService):
        """Sollte letzte Mahnung empfehlen ab 42 Tage."""
        action = service._get_recommended_action(
            days_overdue=45,
            current_level=DunningLevel.SECOND_REMINDER,
        )

        assert action == DunningAction.FINAL_DUNNING

    def test_collection_after_final(self, service: DunningService):
        """Sollte Inkasso empfehlen nach letzter Mahnung."""
        action = service._get_recommended_action(
            days_overdue=60,
            current_level=DunningLevel.FINAL_REMINDER,
        )

        assert action == DunningAction.COLLECTION

    def test_no_escalation_before_threshold(self, service: DunningService):
        """Sollte nicht eskalieren wenn Schwelle nicht erreicht."""
        # Erste Mahnung gesendet, aber noch nicht 28 Tage
        action = service._get_recommended_action(
            days_overdue=20,
            current_level=DunningLevel.FIRST_REMINDER,
        )

        assert action == DunningAction.FIRST_DUNNING


class TestFeeCalculation:
    """Tests fuer Gebuehren-Berechnung."""

    @pytest.fixture
    def service(self) -> DunningService:
        return DunningService()

    def test_fee_for_first_dunning(self, service: DunningService):
        """Sollte Gebuehr fuer 1. Mahnung berechnen."""
        fee = service._get_fee_for_level(DunningLevel.FIRST_REMINDER)

        assert fee == Decimal("5.00")

    def test_fee_for_second_dunning(self, service: DunningService):
        """Sollte Gebuehr fuer 2. Mahnung berechnen."""
        fee = service._get_fee_for_level(DunningLevel.SECOND_REMINDER)

        assert fee == Decimal("10.00")

    def test_fee_for_final_dunning(self, service: DunningService):
        """Sollte Gebuehr fuer letzte Mahnung berechnen."""
        fee = service._get_fee_for_level(DunningLevel.FINAL_REMINDER)

        assert fee == Decimal("15.00")

    def test_no_fee_for_not_started(self, service: DunningService):
        """Sollte keine Gebuehr fuer Level NOT_STARTED haben."""
        fee = service._get_fee_for_level(DunningLevel.NOT_STARTED)

        assert fee == Decimal("0.00")

    def test_fee_for_action(self, service: DunningService):
        """Sollte Gebuehr fuer Aktion berechnen."""
        reminder_fee = service._get_fee_for_action(DunningAction.REMINDER)
        first_fee = service._get_fee_for_action(DunningAction.FIRST_DUNNING)

        assert reminder_fee == Decimal("0.00")
        assert first_fee == Decimal("5.00")


class TestLateInterestCalculation:
    """Tests fuer Verzugszinsen-Berechnung."""

    @pytest.fixture
    def service(self) -> DunningService:
        return DunningService()

    def test_no_interest_if_not_overdue(self, service: DunningService):
        """Sollte keine Zinsen berechnen wenn nicht ueberfaellig."""
        today = date.today()
        due_date = today + timedelta(days=5)  # Noch nicht faellig

        interest = service._calculate_late_interest(
            principal=Decimal("1000.00"),
            due_date=due_date,
            as_of_date=today,
        )

        assert interest == Decimal("0.00")

    def test_interest_calculation(self, service: DunningService):
        """Sollte Verzugszinsen korrekt berechnen."""
        today = date.today()
        due_date = today - timedelta(days=30)  # 30 Tage ueberfaellig

        interest = service._calculate_late_interest(
            principal=Decimal("1000.00"),
            due_date=due_date,
            as_of_date=today,
        )

        # Basiszins + 5% = 8.62% p.a.
        # 1000 * 0.0862 / 365 * 30 = ~7.09
        assert interest > Decimal("0.00")
        assert interest < Decimal("10.00")  # Plausibilitaetspruefung

    def test_interest_scales_with_principal(self, service: DunningService):
        """Sollte Zinsen proportional zum Betrag skalieren."""
        today = date.today()
        due_date = today - timedelta(days=60)

        interest_1000 = service._calculate_late_interest(
            principal=Decimal("1000.00"),
            due_date=due_date,
            as_of_date=today,
        )

        interest_2000 = service._calculate_late_interest(
            principal=Decimal("2000.00"),
            due_date=due_date,
            as_of_date=today,
        )

        # Doppelter Betrag = doppelte Zinsen
        assert interest_2000 == interest_1000 * 2

    def test_interest_scales_with_days(self, service: DunningService):
        """Sollte Zinsen proportional zu Tagen skalieren."""
        today = date.today()

        interest_30d = service._calculate_late_interest(
            principal=Decimal("1000.00"),
            due_date=today - timedelta(days=30),
            as_of_date=today,
        )

        interest_60d = service._calculate_late_interest(
            principal=Decimal("1000.00"),
            due_date=today - timedelta(days=60),
            as_of_date=today,
        )

        # Doppelte Zeit = ungefaehr doppelte Zinsen (Rundung beachten)
        assert float(interest_60d) == pytest.approx(float(interest_30d * 2), rel=0.01)


class TestDunningCandidate:
    """Tests fuer DunningCandidate Dataclass."""

    def test_create_candidate(self):
        """Sollte Mahnkandidaten erstellen."""
        today = date.today()
        due_date = today - timedelta(days=20)

        candidate = DunningCandidate(
            document_id=uuid4(),
            invoice_number="RE-2024-001",
            creditor_name="Test GmbH",
            amount=Decimal("500.00"),
            due_date=due_date,
            days_overdue=20,
            current_level=DunningLevel.NOT_STARTED,
            recommended_action=DunningAction.FIRST_DUNNING,
            accumulated_fees=Decimal("0.00"),
            late_interest=Decimal("2.50"),
            total_due=Decimal("507.50"),
        )

        assert candidate.invoice_number == "RE-2024-001"
        assert candidate.days_overdue == 20
        assert candidate.total_due == Decimal("507.50")

    def test_total_due_calculation(self):
        """Sollte Gesamtbetrag korrekt berechnen."""
        candidate = DunningCandidate(
            document_id=uuid4(),
            invoice_number="RE-2024-002",
            creditor_name="Muster AG",
            amount=Decimal("1000.00"),
            due_date=date.today() - timedelta(days=45),
            days_overdue=45,
            current_level=DunningLevel.SECOND_REMINDER,
            recommended_action=DunningAction.FINAL_DUNNING,
            accumulated_fees=Decimal("15.00"),  # 5 + 10
            late_interest=Decimal("10.50"),
            total_due=Decimal("1025.50"),  # 1000 + 15 + 10.50
        )

        expected_total = (
            candidate.amount +
            candidate.accumulated_fees +
            candidate.late_interest
        )

        assert candidate.total_due == expected_total


class TestCustomConfig:
    """Tests mit benutzerdefinierter Konfiguration."""

    def test_custom_fee_structure(self):
        """Sollte benutzerdefinierte Gebuehrenstruktur verwenden."""
        config = DunningConfig(
            first_dunning_fee=Decimal("10.00"),
            second_dunning_fee=Decimal("20.00"),
            final_dunning_fee=Decimal("30.00"),
        )

        service = DunningService(config=config)

        assert service._get_fee_for_level(DunningLevel.FIRST_REMINDER) == Decimal("10.00")
        assert service._get_fee_for_level(DunningLevel.SECOND_REMINDER) == Decimal("20.00")
        assert service._get_fee_for_level(DunningLevel.FINAL_REMINDER) == Decimal("30.00")

    def test_custom_timing(self):
        """Sollte benutzerdefinierte Zeitraeume verwenden."""
        config = DunningConfig(
            reminder_after_days=3,
            first_dunning_after_days=7,
            second_dunning_after_days=14,
            final_dunning_after_days=21,
        )

        service = DunningService(config=config)

        # 8 Tage sollte 1. Mahnung ausloesen (statt Erinnerung)
        action = service._get_recommended_action(
            days_overdue=8,
            current_level=DunningLevel.NOT_STARTED,
        )

        assert action == DunningAction.FIRST_DUNNING

    def test_custom_interest_rate(self):
        """Sollte benutzerdefinierten Zinssatz verwenden."""
        config = DunningConfig(
            late_interest_rate=Decimal("9.00"),  # 9% ueber Basiszins
            base_interest_rate=Decimal("5.00"),  # Hoeherer Basiszins
        )

        service = DunningService(config=config)

        today = date.today()
        interest = service._calculate_late_interest(
            principal=Decimal("1000.00"),
            due_date=today - timedelta(days=365),
            as_of_date=today,
        )

        # 1000 * 14% = 140 (ungefaehr)
        assert interest > Decimal("100.00")
        assert interest < Decimal("200.00")


class TestMinDunningAmount:
    """Tests fuer Mindestbetrag."""

    def test_min_amount_default(self):
        """Sollte Standard-Mindestbetrag haben."""
        config = DunningConfig()

        assert config.min_dunning_amount == Decimal("5.00")

    def test_custom_min_amount(self):
        """Sollte benutzerdefinierten Mindestbetrag verwenden."""
        config = DunningConfig(min_dunning_amount=Decimal("10.00"))

        assert config.min_dunning_amount == Decimal("10.00")
