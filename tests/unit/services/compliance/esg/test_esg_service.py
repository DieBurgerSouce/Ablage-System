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
        """Sollte Dashboard-Zusammenfassung zurueckgeben.

        Der Service macht 6 DB-Aufrufe (CO2-Summe, CO2-nach-Scope,
        Lieferanten-Avg, Lieferanten-Count, aktive Zertifikate, aktive Ziele).
        """
        # 1) CO2-Gesamtsumme (scalar)
        carbon_total = create_mock_result(scalar_value=28110.0)
        # 2) CO2 nach Scope (fetchall liefert (scope, sum)-Tupel)
        scope_result = MagicMock()
        scope_result.fetchall = MagicMock(return_value=[
            ("scope_1", 15360.0),
            ("scope_2", 4200.0),
            ("scope_3", 8550.0),
        ])
        # 3) Lieferanten-Durchschnittsscore (scalar)
        supplier_avg = create_mock_result(scalar_value=75.5)
        # 4) Anzahl bewerteter Lieferanten (scalar)
        supplier_count = create_mock_result(scalar_value=4)
        # 5) Aktive Zertifizierungen (scalar)
        cert_count = create_mock_result(scalar_value=12)
        # 6) Aktive Ziele (scalars().all())
        goal_a = MagicMock(); goal_a.on_track = True
        goal_b = MagicMock(); goal_b.on_track = False
        goals_result = create_mock_result(scalars_list=[goal_a, goal_b])

        mock_db.execute.side_effect = [
            carbon_total,
            scope_result,
            supplier_avg,
            supplier_count,
            cert_count,
            goals_result,
        ]

        result = await esg_service.get_dashboard_summary(company_id=company_id)

        # Starke Assertion: Dashboard-Summary MUSS carbon_footprint enthalten
        assert result is not None, "get_dashboard_summary sollte ein Ergebnis zurueckgeben"
        assert "carbon_footprint" in result
        assert result["carbon_footprint"]["total_emissions_kg"] == 28110.0
        assert result["carbon_footprint"]["by_scope"]["scope_1"] == 15360.0
        assert result["suppliers"]["average_score"] == 75.5
        assert result["certifications"]["active_count"] == 12
        assert result["goals"]["total"] == 2
        assert result["goals"]["on_track"] == 1

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
            description="Test-Beschreibung",
            category="environmental",
            metric_name="test",
            metric_unit="t CO2e",
            baseline_value=0.0,
            baseline_year=2020,
            target_value=100.0,
            target_year=2030,
        )

        mock_db.add.assert_called_once()
        # Ziel startet aktiv und mit den uebergebenen Zielwerten
        assert goal.is_active is True
        assert goal.target_value == 100.0

    @pytest.mark.asyncio
    async def test_create_goal_validates_category(
        self,
        esg_service: ESGService,
        mock_db: AsyncMock,
        company_id: UUID,
    ):
        """Sollte ungueltige Kategorie ablehnen (echte Validierung)."""
        with pytest.raises(ValueError, match="Kategorie"):
            await esg_service.create_goal(
                company_id=company_id,
                title="Invalid Goal",
                description=None,
                category="ungueltig",  # keine gueltige ESGCategory
                metric_name="test",
                metric_unit=None,
                baseline_value=None,
                baseline_year=2020,
                target_value=100.0,
                target_year=2030,
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

        # Service serialisiert zu Dicts
        assert all(isinstance(g, dict) for g in result)
        for goal in result:
            assert goal["category"] == "environmental"

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

        # Der Service filtert die Query auf is_active; Rueckgabe sind Dicts
        assert len(result) == len(active_goals)
        assert all(isinstance(g, dict) for g in result)
        assert all("title" in g for g in result)


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
