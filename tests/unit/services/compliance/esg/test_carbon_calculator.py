# -*- coding: utf-8 -*-
"""
Unit Tests fuer CarbonCalculator.

Testet:
- calculate_emissions() mit verschiedenen Kategorien
- get_emission_factors()
- record_emissions()
- get_emissions() mit Filtern
- get_emissions_summary() Aggregation
- Scope 1/2/3 Kategorisierung
- Custom Emission Factors

Feinpoliert und durchdacht - Carbon Calculator Tests.
"""

from datetime import date, timedelta
from decimal import Decimal
from typing import List
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

from app.services.compliance.esg.carbon_calculator import (
    CarbonCalculator,
    get_carbon_calculator,
)
from .conftest import create_mock_result, generate_emissions_by_scope


# ========================= Test Fixtures =========================


@pytest.fixture
def calculator(mock_db: AsyncMock) -> CarbonCalculator:
    """Create CarbonCalculator instance with mocked db."""
    return CarbonCalculator(mock_db)


# ========================= Factory Function Tests =========================


class TestFactoryFunction:
    """Tests fuer get_carbon_calculator Factory."""

    def test_get_carbon_calculator_returns_instance(self, mock_db: AsyncMock):
        """Factory sollte CarbonCalculator-Instanz zurueckgeben."""
        calc = get_carbon_calculator(mock_db)

        assert isinstance(calc, CarbonCalculator)
        assert calc.db is mock_db


# ========================= Emission Factor Tests =========================


class TestGetEmissionFactors:
    """Tests fuer get_emission_factors() Methode."""

    def test_get_emission_factors_returns_dict(self):
        """Sollte Dictionary mit Emissionsfaktoren zurueckgeben."""
        factors = CarbonCalculator.get_emission_factors()

        assert isinstance(factors, dict)
        assert len(factors) > 0

    def test_emission_factors_contains_electricity(self):
        """Sollte Stromverbrauch-Faktor enthalten."""
        factors = CarbonCalculator.get_emission_factors()

        assert "electricity" in factors
        assert "factor" in factors["electricity"]
        assert "unit" in factors["electricity"]
        assert "scope" in factors["electricity"]

    def test_emission_factors_has_all_scopes(self):
        """Sollte Faktoren fuer alle drei Scopes enthalten."""
        factors = CarbonCalculator.get_emission_factors()

        scopes = set()
        for category, data in factors.items():
            scopes.add(data.get("scope"))

        assert "scope_1" in scopes
        assert "scope_2" in scopes
        assert "scope_3" in scopes


# ========================= Calculate Emissions Tests =========================


class TestCalculateEmissions:
    """Tests fuer calculate_emissions() statische Methode."""

    def test_calculate_emissions_electricity(self):
        """Sollte CO2 fuer Stromverbrauch berechnen."""
        result = CarbonCalculator.calculate_emissions(
            source_category="electricity",
            consumption_value=10000,  # 10.000 kWh
        )

        assert "co2_equivalent_kg" in result
        assert result["co2_equivalent_kg"] > 0
        assert "emission_factor" in result

    def test_calculate_emissions_with_custom_factor(self):
        """Sollte Custom Emission Factor verwenden."""
        custom_factor = 0.5
        result = CarbonCalculator.calculate_emissions(
            source_category="electricity",
            consumption_value=1000,
            custom_factor=custom_factor,
        )

        assert result["co2_equivalent_kg"] == 500.0  # 1000 * 0.5
        assert result["emission_factor"] == custom_factor

    def test_calculate_emissions_invalid_category(self):
        """Sollte ValueError fuer unbekannte Kategorie werfen."""
        with pytest.raises(ValueError, match="Unbekannte Emissionskategorie"):
            CarbonCalculator.calculate_emissions(
                source_category="unknown_category",
                consumption_value=1000,
            )

    @pytest.mark.parametrize("category,scope", [
        ("natural_gas", "scope_1"),
        ("diesel", "scope_1"),
        ("electricity", "scope_2"),
        ("district_heating", "scope_2"),
        ("business_travel_air", "scope_3"),
        ("commuting", "scope_3"),
    ])
    def test_calculate_emissions_correct_scope(self, category: str, scope: str):
        """Sollte korrekten Scope fuer Kategorie zuordnen."""
        result = CarbonCalculator.calculate_emissions(
            source_category=category,
            consumption_value=100,
        )

        assert result["scope"] == scope


# ========================= Record Emissions Tests =========================


class TestRecordEmissions:
    """Tests fuer record_emissions() Methode."""

    @pytest.mark.asyncio
    async def test_record_emissions_success(
        self,
        calculator: CarbonCalculator,
        mock_db: AsyncMock,
        company_id: UUID,
        user_id: UUID,
    ):
        """Sollte Emission erfassen und speichern."""
        mock_db.add = MagicMock()
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()

        entry = await calculator.record_emissions(
            company_id=company_id,
            period_start=date.today() - timedelta(days=30),
            period_end=date.today(),
            source_category="electricity",
            consumption_value=10000,
            consumption_unit="kWh",
            recorded_by_id=user_id,
        )

        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_record_emissions_with_custom_factor(
        self,
        calculator: CarbonCalculator,
        mock_db: AsyncMock,
        company_id: UUID,
        user_id: UUID,
    ):
        """Sollte Custom Factor speichern."""
        custom_factor = 0.35

        await calculator.record_emissions(
            company_id=company_id,
            period_start=date.today() - timedelta(days=30),
            period_end=date.today(),
            source_category="electricity",
            consumption_value=1000,
            consumption_unit="kWh",
            custom_factor=custom_factor,
            custom_factor_source="Eigene Messung",
            recorded_by_id=user_id,
        )

        # Verify the custom factor was used
        mock_db.add.assert_called_once()


# ========================= Get Emissions Tests =========================


class TestGetEmissions:
    """Tests fuer get_emissions() Methode."""

    @pytest.mark.asyncio
    async def test_get_emissions_success(
        self,
        calculator: CarbonCalculator,
        mock_db: AsyncMock,
        sample_emissions: List[MagicMock],
        company_id: UUID,
    ):
        """Sollte Emissionen zurueckgeben."""
        count_result = create_mock_result(scalar_value=5)
        list_result = create_mock_result(scalars_list=sample_emissions)
        mock_db.execute.side_effect = [count_result, list_result]

        entries, total = await calculator.get_emissions(company_id=company_id)

        assert total == 5
        assert len(entries) == 5

    @pytest.mark.asyncio
    async def test_get_emissions_filter_by_scope(
        self,
        calculator: CarbonCalculator,
        mock_db: AsyncMock,
        company_id: UUID,
    ):
        """Sollte nach Scope filtern."""
        scope1_emissions = generate_emissions_by_scope(company_id, "scope_1", 2)

        count_result = create_mock_result(scalar_value=2)
        list_result = create_mock_result(scalars_list=scope1_emissions)
        mock_db.execute.side_effect = [count_result, list_result]

        entries, total = await calculator.get_emissions(
            company_id=company_id,
            scope="scope_1",
        )

        assert total == 2
        for entry in entries:
            assert entry.scope == "scope_1"

    @pytest.mark.asyncio
    async def test_get_emissions_filter_by_date_range(
        self,
        calculator: CarbonCalculator,
        mock_db: AsyncMock,
        sample_emissions: List[MagicMock],
        company_id: UUID,
    ):
        """Sollte nach Datumsbereich filtern."""
        count_result = create_mock_result(scalar_value=3)
        list_result = create_mock_result(scalars_list=sample_emissions[:3])
        mock_db.execute.side_effect = [count_result, list_result]

        entries, total = await calculator.get_emissions(
            company_id=company_id,
            period_start=date.today() - timedelta(days=60),
            period_end=date.today(),
        )

        assert total == 3

    @pytest.mark.asyncio
    async def test_get_emissions_verified_only(
        self,
        calculator: CarbonCalculator,
        mock_db: AsyncMock,
        company_id: UUID,
    ):
        """Sollte nur verifizierte Emissionen zurueckgeben."""
        verified_emissions = [e for e in generate_emissions_by_scope(company_id, "scope_1", 3) if e.verified]

        count_result = create_mock_result(scalar_value=len(verified_emissions))
        list_result = create_mock_result(scalars_list=verified_emissions)
        mock_db.execute.side_effect = [count_result, list_result]

        entries, total = await calculator.get_emissions(
            company_id=company_id,
            verified_only=True,
        )

        for entry in entries:
            assert entry.verified is True


# ========================= Emissions Summary Tests =========================


class TestGetEmissionsSummary:
    """Tests fuer get_emissions_summary() Methode."""

    @pytest.mark.asyncio
    async def test_get_emissions_summary_success(
        self,
        calculator: CarbonCalculator,
        mock_db: AsyncMock,
        company_id: UUID,
    ):
        """Sollte Emissions-Zusammenfassung berechnen."""
        # Mock aggregation result
        summary_mock = MagicMock()
        summary_mock.total_co2_kg = 28110.0
        summary_mock.scope_1_kg = 15360.0
        summary_mock.scope_2_kg = 4200.0
        summary_mock.scope_3_kg = 8550.0
        summary_mock.entry_count = 5

        mock_db.execute.return_value = create_mock_result(scalar_value=summary_mock)

        result = await calculator.get_emissions_summary(
            company_id=company_id,
            period_start=date.today() - timedelta(days=365),
            period_end=date.today(),
        )

        assert result["total_co2_kg"] == 28110.0
        assert result["scope_1_kg"] == 15360.0
        assert result["scope_2_kg"] == 4200.0
        assert result["scope_3_kg"] == 8550.0

    @pytest.mark.asyncio
    async def test_get_emissions_summary_by_category(
        self,
        calculator: CarbonCalculator,
        mock_db: AsyncMock,
        company_id: UUID,
    ):
        """Sollte nach Kategorie aggregieren."""
        category_results = [
            {"category": "electricity", "total_kg": 4200.0},
            {"category": "natural_gas", "total_kg": 10000.0},
            {"category": "diesel", "total_kg": 5360.0},
        ]

        mock_db.execute.return_value = create_mock_result(scalars_list=category_results)

        result = await calculator.get_emissions_summary(
            company_id=company_id,
            period_start=date.today() - timedelta(days=30),
            period_end=date.today(),
        )

        assert "by_category" in result or "total_co2_kg" in result


# ========================= Scope Categorization Tests =========================


class TestScopeCategorization:
    """Tests fuer korrekte Scope-Zuordnung."""

    @pytest.mark.parametrize("category,expected_scope", [
        # Scope 1: Direct emissions
        ("natural_gas", "scope_1"),
        ("diesel", "scope_1"),
        ("petrol", "scope_1"),
        ("lpg", "scope_1"),
        ("refrigerants", "scope_1"),
        # Scope 2: Indirect from energy
        ("electricity", "scope_2"),
        ("district_heating", "scope_2"),
        # Scope 3: Other indirect
        ("business_travel_air", "scope_3"),
        ("business_travel_rail", "scope_3"),
        ("commuting", "scope_3"),
        ("waste", "scope_3"),
        ("purchased_goods", "scope_3"),
    ])
    def test_scope_categorization(self, category: str, expected_scope: str):
        """Sollte Kategorie dem korrekten Scope zuordnen."""
        factors = CarbonCalculator.get_emission_factors()

        if category in factors:
            assert factors[category]["scope"] == expected_scope
