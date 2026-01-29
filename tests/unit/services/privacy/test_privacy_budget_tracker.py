# -*- coding: utf-8 -*-
"""
Tests fuer Privacy Budget Tracker.

Testet:
- Budget-Verbrauch
- Budget-Erschoepfung
- Reset-Funktionalitaet
"""

import pytest
from datetime import date, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from app.services.privacy.privacy_budget_tracker import (
    PrivacyBudgetTracker,
    BudgetConfig,
    BudgetStatus,
    BudgetExhaustedError,
    get_budget_tracker,
)


class TestBudgetConfig:
    """Tests fuer Budget-Konfiguration."""

    def test_default_config(self) -> None:
        """Standard-Konfiguration sollte sinnvolle Werte haben."""
        config = BudgetConfig()

        assert config.daily_budget == 10.0
        assert config.min_remaining_warning == 2.0
        assert config.allow_overdraft is False

    def test_custom_config(self) -> None:
        """Benutzerdefinierte Konfiguration sollte funktionieren."""
        config = BudgetConfig(
            daily_budget=20.0,
            allow_overdraft=True,
            overdraft_limit=5.0
        )

        assert config.daily_budget == 20.0
        assert config.allow_overdraft is True
        assert config.overdraft_limit == 5.0


class TestBudgetTrackerInitialization:
    """Tests fuer Tracker-Initialisierung."""

    def test_init_without_redis(self) -> None:
        """Tracker sollte ohne Redis funktionieren."""
        tracker = PrivacyBudgetTracker(redis_client=None)

        assert tracker.redis is None
        assert tracker._local_cache == {}

    def test_init_with_custom_config(self) -> None:
        """Tracker sollte benutzerdefinierte Konfiguration akzeptieren."""
        config = BudgetConfig(daily_budget=5.0)
        tracker = PrivacyBudgetTracker(config=config)

        assert tracker.config.daily_budget == 5.0


class TestBudgetOperations:
    """Tests fuer Budget-Operationen."""

    @pytest.mark.asyncio
    async def test_get_remaining_budget_initial(self) -> None:
        """Initial sollte volles Budget verfuegbar sein."""
        tracker = PrivacyBudgetTracker()
        company_id = uuid4()

        remaining = await tracker.get_remaining_budget(company_id)

        assert remaining == tracker.config.daily_budget

    @pytest.mark.asyncio
    async def test_consume_budget_success(self) -> None:
        """Budget-Verbrauch sollte funktionieren."""
        tracker = PrivacyBudgetTracker()
        company_id = uuid4()

        epsilon = 2.0
        success = await tracker.consume_budget(company_id, epsilon)

        assert success is True
        remaining = await tracker.get_remaining_budget(company_id)
        assert remaining == tracker.config.daily_budget - epsilon

    @pytest.mark.asyncio
    async def test_consume_budget_multiple_times(self) -> None:
        """Mehrfacher Verbrauch sollte korrekt addieren."""
        tracker = PrivacyBudgetTracker()
        company_id = uuid4()

        await tracker.consume_budget(company_id, 1.0)
        await tracker.consume_budget(company_id, 2.0)
        await tracker.consume_budget(company_id, 3.0)

        remaining = await tracker.get_remaining_budget(company_id)
        assert remaining == tracker.config.daily_budget - 6.0

    @pytest.mark.asyncio
    async def test_consume_budget_exhausted(self) -> None:
        """Erschoepftes Budget sollte Fehler werfen."""
        tracker = PrivacyBudgetTracker()
        company_id = uuid4()

        # Verbrauche fast alles
        await tracker.consume_budget(company_id, 9.5)

        # Versuche mehr als verfuegbar
        with pytest.raises(BudgetExhaustedError):
            await tracker.consume_budget(company_id, 1.0)

    @pytest.mark.asyncio
    async def test_consume_budget_invalid_epsilon(self) -> None:
        """Negativer Epsilon sollte Fehler werfen."""
        tracker = PrivacyBudgetTracker()
        company_id = uuid4()

        with pytest.raises(ValueError):
            await tracker.consume_budget(company_id, -1.0)

        with pytest.raises(ValueError):
            await tracker.consume_budget(company_id, 0.0)

    @pytest.mark.asyncio
    async def test_consume_budget_with_overdraft(self) -> None:
        """Overdraft sollte bei Erlaubnis funktionieren."""
        config = BudgetConfig(
            daily_budget=5.0,
            allow_overdraft=True,
            overdraft_limit=2.0
        )
        tracker = PrivacyBudgetTracker(config=config)
        company_id = uuid4()

        # Verbrauche Budget + Overdraft
        await tracker.consume_budget(company_id, 4.0)
        success = await tracker.consume_budget(company_id, 2.5)  # 0.5 Overdraft

        assert success is True

    @pytest.mark.asyncio
    async def test_consume_budget_overdraft_exceeded(self) -> None:
        """Ueberschrittenes Overdraft sollte Fehler werfen."""
        config = BudgetConfig(
            daily_budget=5.0,
            allow_overdraft=True,
            overdraft_limit=1.0
        )
        tracker = PrivacyBudgetTracker(config=config)
        company_id = uuid4()

        await tracker.consume_budget(company_id, 4.5)

        with pytest.raises(BudgetExhaustedError, match="Overdraft-Limit"):
            await tracker.consume_budget(company_id, 3.0)  # Wuerde Limit ueberschreiten


class TestBudgetStatus:
    """Tests fuer Budget-Status."""

    @pytest.mark.asyncio
    async def test_get_status_initial(self) -> None:
        """Initial-Status sollte korrekt sein."""
        tracker = PrivacyBudgetTracker()
        company_id = uuid4()

        status = await tracker.get_status(company_id)

        assert status.company_id == company_id
        assert status.total_budget == tracker.config.daily_budget
        assert status.consumed == 0.0
        assert status.remaining == tracker.config.daily_budget
        assert status.is_exhausted is False
        assert status.queries_count == 0

    @pytest.mark.asyncio
    async def test_get_status_after_consumption(self) -> None:
        """Status sollte nach Verbrauch korrekt sein."""
        tracker = PrivacyBudgetTracker()
        company_id = uuid4()

        await tracker.consume_budget(company_id, 3.0, query_type="count")
        await tracker.consume_budget(company_id, 2.0, query_type="sum")

        status = await tracker.get_status(company_id)

        assert status.consumed == 5.0
        assert status.remaining == 5.0
        assert status.queries_count == 2

    @pytest.mark.asyncio
    async def test_get_status_exhausted(self) -> None:
        """Erschoepfter Status sollte erkannt werden."""
        tracker = PrivacyBudgetTracker()
        company_id = uuid4()

        await tracker.consume_budget(company_id, 10.0)

        status = await tracker.get_status(company_id)

        assert status.is_exhausted is True
        assert status.remaining == 0.0

    def test_status_to_dict(self) -> None:
        """Status sollte zu Dict serialisierbar sein."""
        status = BudgetStatus(
            company_id=uuid4(),
            date=date.today(),
            total_budget=10.0,
            consumed=3.5,
            remaining=6.5,
            is_exhausted=False,
            queries_count=5,
            reset_at=datetime.utcnow()
        )

        d = status.to_dict()

        assert "company_id" in d
        assert "consumed" in d
        assert d["consumed"] == 3.5


class TestBudgetAvailabilityCheck:
    """Tests fuer Budget-Verfuegbarkeitspruefung."""

    @pytest.mark.asyncio
    async def test_check_budget_available_true(self) -> None:
        """Verfuegbarkeitspruefung sollte True zurueckgeben."""
        tracker = PrivacyBudgetTracker()
        company_id = uuid4()

        available = await tracker.check_budget_available(company_id, 5.0)

        assert available is True

    @pytest.mark.asyncio
    async def test_check_budget_available_false(self) -> None:
        """Verfuegbarkeitspruefung sollte False zurueckgeben."""
        tracker = PrivacyBudgetTracker()
        company_id = uuid4()

        await tracker.consume_budget(company_id, 8.0)
        available = await tracker.check_budget_available(company_id, 5.0)

        assert available is False


class TestBudgetReset:
    """Tests fuer Budget-Reset."""

    @pytest.mark.asyncio
    async def test_reset_budget(self) -> None:
        """Reset sollte Budget zuruecksetzen."""
        tracker = PrivacyBudgetTracker()
        company_id = uuid4()

        # Verbrauche etwas
        await tracker.consume_budget(company_id, 5.0)

        # Reset
        await tracker.reset_budget(company_id)

        # Sollte wieder voll sein
        remaining = await tracker.get_remaining_budget(company_id)
        assert remaining == tracker.config.daily_budget


class TestMultipleTenants:
    """Tests fuer Multi-Tenant-Isolation."""

    @pytest.mark.asyncio
    async def test_budget_isolation_between_tenants(self) -> None:
        """Budgets sollten zwischen Tenants isoliert sein."""
        tracker = PrivacyBudgetTracker()
        company_a = uuid4()
        company_b = uuid4()

        # Tenant A verbraucht
        await tracker.consume_budget(company_a, 5.0)

        # Tenant B sollte volles Budget haben
        remaining_b = await tracker.get_remaining_budget(company_b)
        assert remaining_b == tracker.config.daily_budget

        # Tenant A sollte weniger haben
        remaining_a = await tracker.get_remaining_budget(company_a)
        assert remaining_a == 5.0


class TestBudgetHistory:
    """Tests fuer Budget-History."""

    @pytest.mark.asyncio
    async def test_get_history_without_redis(self) -> None:
        """History sollte ohne Redis leere Liste zurueckgeben."""
        tracker = PrivacyBudgetTracker(redis_client=None)
        company_id = uuid4()

        history = await tracker.get_history(company_id)

        assert history == []
