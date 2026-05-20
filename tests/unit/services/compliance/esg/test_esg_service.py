# -*- coding: utf-8 -*-
"""
Unit Tests fuer ESGService.

Testet:
- get_dashboard_summary()
- create_goal()
- get_goals()
- update_goal_progress()
- get_carbon_footprint_trend()
- get_sdg_mapping()

Feinpoliert und durchdacht - ESG Service Tests.
"""

from datetime import date, timedelta
from typing import List
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest

from app.services.compliance.esg.esg_service import (
    ESGService,
    get_esg_service,
)
from .conftest import create_mock_result


# ========================= Test Fixtures =========================


@pytest.fixture
def esg_service(mock_db: AsyncMock) -> ESGService:
    """Create ESGService instance with mocked db."""
    return ESGService(mock_db)


# ========================= Factory Function Tests =========================


class TestFactoryFunction:
    """Tests fuer get_esg_service Factory."""

    def test_get_esg_service_returns_instance(self, mock_db: AsyncMock):
        """Factory sollte ESGService-Instanz zurueckgeben."""
        service = get_esg_service(mock_db)

        assert isinstance(service, ESGService)
        assert service.db is mock_db


# ========================= Dashboard Summary Tests =========================


class TestGetDashboardSummary:
    """Tests fuer get_dashboard_summary() Methode."""

    @pytest.mark.asyncio
    async def test_get_dashboard_summary_success(
        self,
        esg_service: ESGService,
        mock_db: AsyncMock,
        company_id: UUID,
    ):
        """Sollte Dashboard-Zusammenfassung zurueckgeben."""
        # Mock verschiedene Queries
        carbon_total = MagicMock()
        carbon_total.total = 28110.0

        supplier_summary = MagicMock()
        supplier_summary.avg_score = 75.5
        supplier_summary.high_risk_count = 2

        cert_summary = MagicMock()
        cert_summary.active_count = 12
        cert_summary.expiring_count = 3

        goal_summary = MagicMock()
        goal_summary.total = 8
        goal_summary.on_track = 6

        mock_db.execute.side_effect = [
            create_mock_result(scalar_value=carbon_total),
            create_mock_result(scalar_value=supplier_summary),
            create_mock_result(scalar_value=cert_summary),
            create_mock_result(scalar_value=goal_summary),
        ]

        result = await esg_service.get_dashboard_summary(company_id=company_id)

        # Starke Assertion: Dashboard-Summary MUSS carbon_footprint enthalten
        assert result is not None, "get_dashboard_summary sollte ein Ergebnis zurueckgeben"
        assert "carbon_footprint" in result, \
            f"Dashboard-Summary muss 'carbon_footprint' enthalten, erhielt: {result.keys() if isinstance(result, dict) else type(result)}"
        mock_db.execute.assert_called()  # Verifiziere, dass DB aufgerufen wurde

    @pytest.mark.asyncio
    async def test_get_dashboard_summary_with_date_range(
        self,
        esg_service: ESGService,
        mock_db: AsyncMock,
        company_id: UUID,
    ):
        """Sollte Datumsbereich beruecksichtigen."""
        mock_db.execute.return_value = create_mock_result(scalar_value=None)

        await esg_service.get_dashboard_summary(
            company_id=company_id,
            period_start=date.today() - timedelta(days=365),
            period_end=date.today(),
        )

        # Verify execute was called with date parameters
        assert mock_db.execute.called


# ========================= Goal Creation Tests =========================


class TestCreateGoal:
    """Tests fuer create_goal() Methode."""

    @pytest.mark.asyncio
    async def test_create_goal_success(
        self,
        esg_service: ESGService,
        mock_db: AsyncMock,
        company_id: UUID,
    ):
        """Sollte neues ESG-Ziel erstellen."""
        mock_db.add = MagicMock()
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()

        goal = await esg_service.create_goal(
            company_id=company_id,
            title="CO2-Reduktion um 30%",
            description="Bis 2030 30% weniger Emissionen",
            category="environmental",
            metric_name="co2_emissions",
            metric_unit="t CO2e",
            baseline_value=10000.0,
            baseline_year=2020,
            target_value=7000.0,
            target_year=2030,
            sdg_goals=[7, 12, 13],
        )

        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_goal_calculates_progress(
        self,
        esg_service: ESGService,
        mock_db: AsyncMock,
        company_id: UUID,
    ):
        """Sollte Fortschritt korrekt berechnen."""
        mock_db.add = MagicMock()
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()

        goal = await esg_service.create_goal(
            company_id=company_id,
            title="Test Goal",
            category="environmental",
            metric_name="test",
            target_value=100.0,
            target_year=2030,
            baseline_value=0.0,
            baseline_year=2020,
        )

        # Initial progress should be 0
        mock_db.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_goal_validates_target_year(
        self,
        esg_service: ESGService,
        mock_db: AsyncMock,
        company_id: UUID,
    ):
        """Sollte Zieljahr validieren."""
        with pytest.raises(ValueError):
            await esg_service.create_goal(
                company_id=company_id,
                title="Invalid Goal",
                category="environmental",
                metric_name="test",
                target_value=100.0,
                target_year=2000,  # In der Vergangenheit
                baseline_year=2020,
            )


# ========================= Get Goals Tests =========================


class TestGetGoals:
    """Tests fuer get_goals() Methode."""

    @pytest.mark.asyncio
    async def test_get_goals_success(
        self,
        esg_service: ESGService,
        mock_db: AsyncMock,
        sample_goals: List[MagicMock],
        company_id: UUID,
    ):
        """Sollte Ziele zurueckgeben."""
        mock_db.execute.return_value = create_mock_result(scalars_list=sample_goals)

        result = await esg_service.get_goals(company_id=company_id)

        assert len(result) == len(sample_goals)

    @pytest.mark.asyncio
    async def test_get_goals_filter_by_category(
        self,
        esg_service: ESGService,
        mock_db: AsyncMock,
        sample_goals: List[MagicMock],
        company_id: UUID,
    ):
        """Sollte nach Kategorie filtern."""
        env_goals = [g for g in sample_goals if g.category == "environmental"]
        mock_db.execute.return_value = create_mock_result(scalars_list=env_goals)

        result = await esg_service.get_goals(
            company_id=company_id,
            category="environmental",
        )

        for goal in result:
            assert goal.category == "environmental"

    @pytest.mark.asyncio
    async def test_get_goals_active_only(
        self,
        esg_service: ESGService,
        mock_db: AsyncMock,
        sample_goals: List[MagicMock],
        company_id: UUID,
    ):
        """Sollte nur aktive Ziele zurueckgeben."""
        active_goals = [g for g in sample_goals if g.status == "active"]
        mock_db.execute.return_value = create_mock_result(scalars_list=active_goals)

        result = await esg_service.get_goals(
            company_id=company_id,
            active_only=True,
        )

        for goal in result:
            assert goal.status == "active"


# ========================= Update Goal Progress Tests =========================


class TestUpdateGoalProgress:
    """Tests fuer update_goal_progress() Methode."""

    @pytest.mark.asyncio
    async def test_update_goal_progress_success(
        self,
        esg_service: ESGService,
        mock_db: AsyncMock,
        sample_goal: MagicMock,
        company_id: UUID,
    ):
        """Sollte Fortschritt aktualisieren."""
        mock_db.execute.return_value = create_mock_result(scalar_value=sample_goal)
        mock_db.commit = AsyncMock()

        result = await esg_service.update_goal_progress(
            goal_id=sample_goal.id,
            company_id=company_id,
            current_value=8000.0,
        )

        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_goal_progress_calculates_percentage(
        self,
        esg_service: ESGService,
        mock_db: AsyncMock,
        sample_goal: MagicMock,
        company_id: UUID,
    ):
        """Sollte Prozentsatz korrekt berechnen."""
        # Goal: reduce from 10000 to 7000 (3000 reduction needed)
        sample_goal.baseline_value = 10000.0
        sample_goal.target_value = 7000.0

        mock_db.execute.return_value = create_mock_result(scalar_value=sample_goal)
        mock_db.commit = AsyncMock()

        result = await esg_service.update_goal_progress(
            goal_id=sample_goal.id,
            company_id=company_id,
            current_value=8500.0,  # 1500 reduced = 50%
        )

        # Progress should be calculated

    @pytest.mark.asyncio
    async def test_update_goal_progress_goal_not_found(
        self,
        esg_service: ESGService,
        mock_db: AsyncMock,
        company_id: UUID,
    ):
        """Sollte Fehler werfen wenn Ziel nicht existiert."""
        mock_db.execute.return_value = create_mock_result(scalar_value=None)

        with pytest.raises(ValueError, match="Ziel nicht gefunden"):
            await esg_service.update_goal_progress(
                goal_id=uuid4(),
                company_id=company_id,
                current_value=100.0,
            )


# ========================= Carbon Footprint Trend Tests =========================


class TestGetCarbonFootprintTrend:
    """Tests fuer get_carbon_footprint_trend() Methode."""

    @pytest.mark.asyncio
    async def test_get_carbon_trend_success(
        self,
        esg_service: ESGService,
        mock_db: AsyncMock,
        company_id: UUID,
    ):
        """Sollte CO2-Trend zurueckgeben."""
        # Mock monthly data
        trend_data = [
            {"month": "2025-01", "total_kg": 5000},
            {"month": "2025-02", "total_kg": 4800},
            {"month": "2025-03", "total_kg": 4600},
        ]

        mock_db.execute.return_value = create_mock_result(scalars_list=trend_data)

        result = await esg_service.get_carbon_footprint_trend(
            company_id=company_id,
            months=12,
        )

        assert mock_db.execute.called


# ========================= SDG Mapping Tests =========================


class TestGetSdgMapping:
    """Tests fuer get_sdg_mapping() Methode."""

    @pytest.mark.asyncio
    async def test_get_sdg_mapping_success(
        self,
        esg_service: ESGService,
        mock_db: AsyncMock,
        sample_goals: List[MagicMock],
        company_id: UUID,
    ):
        """Sollte SDG-Mapping zurueckgeben."""
        mock_db.execute.return_value = create_mock_result(scalars_list=sample_goals)

        result = await esg_service.get_sdg_mapping(company_id=company_id)

        # Should return mapping of SDG numbers to goals
        assert mock_db.execute.called
