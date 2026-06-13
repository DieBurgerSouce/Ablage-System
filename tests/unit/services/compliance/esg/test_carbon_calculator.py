# -*- coding: utf-8 -*-
"""
Unit Tests fuer CarbonCalculator.

Testet gegen den ECHTEN Vertrag von
app.services.compliance.esg.carbon_calculator:
- get_emission_factors()  (deutsche Schluessel: strom_de_kwh, erdgas_m3, ...)
- calculate_emissions()  (statisch, ValueError bei unbekannter Quelle)
- record_emissions()
- get_emissions()  (gibt (List[dict], int) zurueck)
- get_emissions_summary()  (total_co2_kg, by_scope, top_categories)
- verify_entry()

Feinpoliert und durchdacht - Carbon Calculator Tests.
"""

from datetime import date, timedelta
from typing import List
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest

from app.services.compliance.esg.carbon_calculator import (
    CarbonCalculator,
    get_carbon_calculator,
    EMISSION_FACTORS,
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
        """Sollte Stromverbrauch-Faktor (strom_de_kwh) enthalten."""
        factors = CarbonCalculator.get_emission_factors()

        assert "strom_de_kwh" in factors
        assert "factor" in factors["strom_de_kwh"]
        assert "unit" in factors["strom_de_kwh"]
        assert "scope" in factors["strom_de_kwh"]
        assert factors["strom_de_kwh"]["scope"] == "scope_2"

    def test_emission_factors_has_all_scopes(self):
        """Sollte Faktoren fuer alle drei Scopes enthalten."""
        factors = CarbonCalculator.get_emission_factors()

        scopes = {data.get("scope") for data in factors.values()}

        assert "scope_1" in scopes
        assert "scope_2" in scopes
        assert "scope_3" in scopes


# ========================= Calculate Emissions Tests =========================


class TestCalculateEmissions:
    """Tests fuer calculate_emissions() statische Methode."""

    def test_calculate_emissions_electricity(self):
        """Sollte CO2 fuer Stromverbrauch korrekt berechnen."""
        result = CarbonCalculator.calculate_emissions(
            source_category="strom_de_kwh",
            consumption_value=10000,  # 10.000 kWh
        )

        # 10000 kWh * 0.420 = 4200 kg CO2e
        assert result["co2_equivalent_kg"] == pytest.approx(4200.0)
        assert result["emission_factor"] == 0.420
        assert result["scope"] == "scope_2"

    def test_calculate_emissions_with_custom_factor(self):
        """Sollte Custom Emission Factor verwenden."""
        custom_factor = 0.5
        result = CarbonCalculator.calculate_emissions(
            source_category="strom_de_kwh",
            consumption_value=1000,
            custom_factor=custom_factor,
        )

        assert result["co2_equivalent_kg"] == 500.0  # 1000 * 0.5
        assert result["emission_factor"] == custom_factor
        assert result["emission_factor_source"] == "Benutzerdefiniert"

    def test_calculate_emissions_invalid_category(self):
        """Sollte ValueError fuer unbekannte Quelle werfen (deutscher Text)."""
        with pytest.raises(ValueError, match="Unbekannte Emissionsquelle"):
            CarbonCalculator.calculate_emissions(
                source_category="unknown_category",
                consumption_value=1000,
            )

    @pytest.mark.parametrize("category,scope", [
        ("erdgas_m3", "scope_1"),
        ("diesel_l", "scope_1"),
        ("benzin_l", "scope_1"),
        ("strom_de_kwh", "scope_2"),
        ("fernwaerme_kwh", "scope_2"),
        ("flug_kurz_km", "scope_3"),
        ("pkw_km", "scope_3"),
        ("abfall_kg", "scope_3"),
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
        """Sollte Emission erfassen, Scope ableiten und speichern."""
        mock_db.add = MagicMock()
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()

        entry = await calculator.record_emissions(
            company_id=company_id,
            period_start=date.today() - timedelta(days=30),
            period_end=date.today(),
            source_category="strom_de_kwh",
            consumption_value=10000,
            consumption_unit="kWh",
            recorded_by_id=user_id,
        )

        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()
        # Scope_2 fuer Strom abgeleitet, CO2 berechnet
        assert entry.scope == "scope_2"
        assert entry.co2_equivalent_kg == pytest.approx(4200.0)

    @pytest.mark.asyncio
    async def test_record_emissions_with_custom_factor(
        self,
        calculator: CarbonCalculator,
        mock_db: AsyncMock,
        company_id: UUID,
        user_id: UUID,
    ):
        """Sollte Custom Factor verwenden und Scope_3 als Fallback setzen."""
        mock_db.add = MagicMock()
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()
        custom_factor = 0.35

        entry = await calculator.record_emissions(
            company_id=company_id,
            period_start=date.today() - timedelta(days=30),
            period_end=date.today(),
            source_category="eigene_quelle",  # nicht in EMISSION_FACTORS
            consumption_value=1000,
            consumption_unit="kWh",
            custom_factor=custom_factor,
            custom_factor_source="Eigene Messung",
            recorded_by_id=user_id,
        )

        mock_db.add.assert_called_once()
        assert entry.emission_factor == custom_factor
        assert entry.co2_equivalent_kg == pytest.approx(350.0)
        # Unbekannte Quelle + Custom -> Scope_3 Fallback
        assert entry.scope == "scope_3"


# ========================= Get Emissions Tests =========================


class TestGetEmissions:
    """Tests fuer get_emissions() (gibt (List[dict], int) zurueck)."""

    @pytest.mark.asyncio
    async def test_get_emissions_success(
        self,
        calculator: CarbonCalculator,
        mock_db: AsyncMock,
        sample_emissions: List[MagicMock],
        company_id: UUID,
    ):
        """Sollte Emissionen als Dict-Liste mit Gesamtanzahl liefern."""
        count_result = create_mock_result(scalar_value=5)
        list_result = create_mock_result(scalars_list=sample_emissions)
        mock_db.execute.side_effect = [count_result, list_result]

        entries, total = await calculator.get_emissions(company_id=company_id)

        assert total == 5
        assert len(entries) == 5
        assert all(isinstance(e, dict) for e in entries)
        assert "co2_equivalent_kg" in entries[0]

    @pytest.mark.asyncio
    async def test_get_emissions_filter_by_scope(
        self,
        calculator: CarbonCalculator,
        mock_db: AsyncMock,
        company_id: UUID,
    ):
        """Sollte nach Scope filtern und Dicts liefern."""
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
            assert entry["scope"] == "scope_1"

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
        """Sollte nur verifizierte Emissionen liefern."""
        verified_emissions = [
            e for e in generate_emissions_by_scope(company_id, "scope_1", 3) if e.verified
        ]

        count_result = create_mock_result(scalar_value=len(verified_emissions))
        list_result = create_mock_result(scalars_list=verified_emissions)
        mock_db.execute.side_effect = [count_result, list_result]

        entries, total = await calculator.get_emissions(
            company_id=company_id,
            verified_only=True,
        )

        for entry in entries:
            assert entry["verified"] is True


# ========================= Emissions Summary Tests =========================


class TestGetEmissionsSummary:
    """Tests fuer get_emissions_summary() Methode (echte Rueckgabe-Struktur)."""

    @pytest.mark.asyncio
    async def test_get_emissions_summary_success(
        self,
        calculator: CarbonCalculator,
        mock_db: AsyncMock,
        company_id: UUID,
    ):
        """Sollte total_co2_kg, by_scope und top_categories aggregieren."""
        # 1. Aufruf: total sum (scalar)
        total_result = create_mock_result(scalar_value=28110.0)
        # 2. Aufruf: by_scope (fetchall liefert (scope, sum)-Tupel)
        scope_result = MagicMock()
        scope_result.fetchall = MagicMock(return_value=[
            ("scope_1", 15360.0),
            ("scope_2", 4200.0),
            ("scope_3", 8550.0),
        ])
        # 3. Aufruf: top_categories (fetchall liefert (category, sum)-Tupel)
        category_result = MagicMock()
        category_result.fetchall = MagicMock(return_value=[
            ("erdgas_m3", 10000.0),
            ("abfall_kg", 8550.0),
            ("strom_de_kwh", 4200.0),
        ])
        mock_db.execute.side_effect = [total_result, scope_result, category_result]

        result = await calculator.get_emissions_summary(
            company_id=company_id,
            period_start=date.today() - timedelta(days=365),
            period_end=date.today(),
        )

        assert result["total_co2_kg"] == 28110.0
        assert result["total_co2_tons"] == pytest.approx(28.11)
        assert result["by_scope"]["scope_1"] == 15360.0
        assert result["by_scope"]["scope_2"] == 4200.0
        assert result["by_scope"]["scope_3"] == 8550.0
        assert len(result["top_categories"]) == 3
        assert result["top_categories"][0]["category"] == "erdgas_m3"

    @pytest.mark.asyncio
    async def test_get_emissions_summary_empty(
        self,
        calculator: CarbonCalculator,
        mock_db: AsyncMock,
        company_id: UUID,
    ):
        """Sollte 0-Werte liefern wenn keine Emissionen erfasst sind."""
        total_result = create_mock_result(scalar_value=None)
        scope_result = MagicMock()
        scope_result.fetchall = MagicMock(return_value=[])
        category_result = MagicMock()
        category_result.fetchall = MagicMock(return_value=[])
        mock_db.execute.side_effect = [total_result, scope_result, category_result]

        result = await calculator.get_emissions_summary(
            company_id=company_id,
            period_start=date.today() - timedelta(days=30),
            period_end=date.today(),
        )

        assert result["total_co2_kg"] == 0.0
        assert result["by_scope"]["scope_1"] == 0
        assert result["top_categories"] == []


# ========================= Verify Entry Tests =========================


class TestVerifyEntry:
    """Tests fuer verify_entry() Methode."""

    @pytest.mark.asyncio
    async def test_verify_entry_success(
        self,
        calculator: CarbonCalculator,
        mock_db: AsyncMock,
        sample_emission,
        company_id: UUID,
        user_id: UUID,
    ):
        """Sollte Eintrag als verifiziert markieren."""
        mock_db.execute.return_value = create_mock_result(scalar_value=sample_emission)
        mock_db.commit = AsyncMock()

        result = await calculator.verify_entry(
            entry_id=sample_emission.id,
            company_id=company_id,
            verified_by_id=user_id,
        )

        assert result is True
        assert sample_emission.verified is True
        assert sample_emission.verified_by_id == user_id
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_verify_entry_not_found(
        self,
        calculator: CarbonCalculator,
        mock_db: AsyncMock,
        company_id: UUID,
        user_id: UUID,
    ):
        """Sollte False zurueckgeben wenn Eintrag nicht existiert."""
        mock_db.execute.return_value = create_mock_result(scalar_value=None)

        result = await calculator.verify_entry(
            entry_id=uuid4(),
            company_id=company_id,
            verified_by_id=user_id,
        )

        assert result is False
