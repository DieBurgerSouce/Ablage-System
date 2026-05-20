# -*- coding: utf-8 -*-
"""Tests fuer DunningService (Mahnwesen).

Unit-Tests mit gemockter Datenbankschicht.
"""

import pytest
from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4


class TestDunningServiceImport:
    """Stellt sicher, dass der Dunning-Service importiert werden kann."""

    def test_import_modul(self):
        """dunning_service-Modul laesst sich importieren."""
        import app.services.banking.dunning_service as module
        assert module is not None

    def test_import_service_klasse(self):
        """DunningService kann importiert werden."""
        from app.services.banking.dunning_service import DunningService
        assert DunningService is not None

    def test_import_enums(self):
        """DunningAction und MahnungHistoryAction koennen importiert werden."""
        from app.services.banking.dunning_service import (
            DunningAction,
            MahnungHistoryAction,
        )
        assert DunningAction.FIRST_DUNNING is not None
        assert MahnungHistoryAction.REMINDER_SENT is not None

    def test_import_konstanten(self):
        """BGB-Zinssatz-Konstanten koennen importiert werden."""
        from app.services.banking.dunning_service import (
            BASE_INTEREST_RATE,
            B2B_INTEREST_ADDON,
            B2C_INTEREST_ADDON,
            B2B_PAUSCHALE,
        )
        assert BASE_INTEREST_RATE == Decimal("2.27")
        assert B2B_INTEREST_ADDON == Decimal("9.00")
        assert B2C_INTEREST_ADDON == Decimal("5.00")
        assert B2B_PAUSCHALE == Decimal("40.00")

    def test_import_singleton(self):
        """dunning_service Singleton kann importiert werden."""
        from app.services.banking.dunning_service import dunning_service, DunningService
        assert isinstance(dunning_service, DunningService)


class TestDunningServiceInit:
    """Tests fuer DunningService Initialisierung."""

    def test_instanz_mit_standard_config(self):
        """DunningService mit Standard-Konfiguration instanziierbar."""
        from app.services.banking.dunning_service import DunningService, DunningConfig
        service = DunningService()
        assert service is not None
        assert isinstance(service.config, DunningConfig)

    def test_instanz_mit_eigener_config(self):
        """DunningService mit eigener DunningConfig instanziierbar."""
        from app.services.banking.dunning_service import DunningService, DunningConfig
        config = DunningConfig(reminder_after_days=5, first_dunning_after_days=10)
        service = DunningService(config=config)
        assert service.config.reminder_after_days == 5
        assert service.config.first_dunning_after_days == 10


class TestGetRecommendedAction:
    """Tests fuer _get_recommended_action() (synchrone Logik)."""

    def test_nicht_ueberfaellig_ergibt_reminder(self):
        """Weniger als reminder_after_days Tage => REMINDER."""
        from app.services.banking.dunning_service import DunningService, DunningAction
        from app.services.banking.models import DunningLevel

        service = DunningService()
        # 3 Tage ueberfaellig, Schwelle liegt bei 7
        result = service._get_recommended_action(3, DunningLevel.NOT_STARTED)
        assert result == DunningAction.REMINDER

    def test_ueberfaellig_14_tage_ergibt_first_dunning(self):
        """14 Tage ueberfaellig + NOT_STARTED => FIRST_DUNNING."""
        from app.services.banking.dunning_service import DunningService, DunningAction
        from app.services.banking.models import DunningLevel

        service = DunningService()
        result = service._get_recommended_action(14, DunningLevel.NOT_STARTED)
        assert result == DunningAction.FIRST_DUNNING

    def test_final_reminder_ergibt_collection(self):
        """Bei FINAL_REMINDER-Stufe => COLLECTION."""
        from app.services.banking.dunning_service import DunningService, DunningAction
        from app.services.banking.models import DunningLevel

        service = DunningService()
        result = service._get_recommended_action(60, DunningLevel.FINAL_REMINDER)
        assert result == DunningAction.COLLECTION


class TestCalculateLateInterest:
    """Tests fuer _calculate_late_interest() (synchrone Berechnung)."""

    def test_nicht_ueberfaellig_ergibt_null(self):
        """Wenn due_date >= as_of_date, gibt es keine Verzugszinsen."""
        from app.services.banking.dunning_service import DunningService

        service = DunningService()
        today = date.today()
        result = service._calculate_late_interest(
            principal=Decimal("1000.00"),
            due_date=today,
            as_of_date=today,
        )
        assert result == Decimal("0.00")

    def test_30_tage_ueberfaellig_berechnet_zinsen(self):
        """30 Tage ueberfaellig => positive Verzugszinsen."""
        from app.services.banking.dunning_service import DunningService

        service = DunningService()
        as_of = date.today()
        due = as_of - timedelta(days=30)
        result = service._calculate_late_interest(
            principal=Decimal("1000.00"),
            due_date=due,
            as_of_date=as_of,
        )
        assert result > Decimal("0.00")


class TestGetVerzugszinsenRate:
    """Tests fuer get_verzugszinsen_rate() (synchrone Berechnung)."""

    def test_b2b_rate_ist_hoeher_als_b2c(self):
        """B2B-Verzugszinssatz liegt hoeher als B2C."""
        from app.services.banking.dunning_service import DunningService

        service = DunningService()
        b2b_rate = service.get_verzugszinsen_rate(is_b2b=True)
        b2c_rate = service.get_verzugszinsen_rate(is_b2b=False)
        assert b2b_rate > b2c_rate

    def test_b2b_rate_korrekt(self):
        """B2B: Basiszins (2.27) + 9.00 = 11.27 Prozent."""
        from app.services.banking.dunning_service import DunningService

        service = DunningService()
        rate = service.get_verzugszinsen_rate(is_b2b=True)
        assert rate == Decimal("11.27")

    def test_b2c_rate_korrekt(self):
        """B2C: Basiszins (2.27) + 5.00 = 7.27 Prozent."""
        from app.services.banking.dunning_service import DunningService

        service = DunningService()
        rate = service.get_verzugszinsen_rate(is_b2b=False)
        assert rate == Decimal("7.27")


class TestGetFeeForLevel:
    """Tests fuer _get_fee_for_level()."""

    def test_not_started_hat_keine_gebuehr(self):
        """DunningLevel.NOT_STARTED hat keine Mahngebuehr."""
        from app.services.banking.dunning_service import DunningService
        from app.services.banking.models import DunningLevel

        service = DunningService()
        assert service._get_fee_for_level(DunningLevel.NOT_STARTED) == Decimal("0.00")

    def test_first_reminder_gebuehr(self):
        """FIRST_REMINDER ergibt konfigurierte erste Mahngebuehr."""
        from app.services.banking.dunning_service import DunningService
        from app.services.banking.models import DunningLevel

        service = DunningService()
        assert service._get_fee_for_level(DunningLevel.FIRST_REMINDER) == service.config.first_dunning_fee

    def test_final_reminder_gebuehr(self):
        """FINAL_REMINDER ergibt konfigurierte letzte Mahngebuehr."""
        from app.services.banking.dunning_service import DunningService
        from app.services.banking.models import DunningLevel

        service = DunningService()
        assert service._get_fee_for_level(DunningLevel.FINAL_REMINDER) == service.config.final_dunning_fee
