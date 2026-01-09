"""
Unit Tests fuer PropertyCalculationService.

Testet:
- Service-Initialisierung
- Dataclass-Strukturen
- Methoden-Existenz
"""

import pytest
from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession


class TestPropertyCalculationService:
    """Tests fuer PropertyCalculationService."""

    @pytest.mark.asyncio
    async def test_service_initialization(self) -> None:
        """Testet Service-Initialisierung."""
        from app.services.privat.property_calculation_service import (
            PropertyCalculationService,
        )

        service = PropertyCalculationService()
        assert service is not None

    @pytest.mark.asyncio
    async def test_dataclass_imports(self) -> None:
        """Testet dass alle Datenklassen importierbar sind."""
        from app.services.privat.property_calculation_service import (
            CostTrendResult,
            PropertyCalculationService,
            PropertyKPIs,
            RentalYieldResult,
            ROIResult,
        )

        assert PropertyCalculationService is not None
        assert RentalYieldResult is not None
        assert ROIResult is not None
        assert CostTrendResult is not None
        assert PropertyKPIs is not None


class TestRentalYieldResultDataClass:
    """Tests fuer RentalYieldResult Datenstruktur."""

    @pytest.mark.asyncio
    async def test_rental_yield_result_dataclass(self) -> None:
        """Testet RentalYieldResult Datenstruktur."""
        from app.services.privat.property_calculation_service import (
            RentalYieldResult,
        )

        result = RentalYieldResult(
            property_id=uuid4(),
            gross_rental_yield=Decimal("5.5"),
            net_rental_yield=Decimal("4.2"),
            annual_rental_income=Decimal("14400.00"),
            annual_costs=Decimal("3500.00"),
            purchase_price=Decimal("260000.00"),
        )

        assert result.gross_rental_yield == Decimal("5.5")
        assert result.net_rental_yield == Decimal("4.2")
        assert result.annual_rental_income == Decimal("14400.00")
        assert result.annual_costs == Decimal("3500.00")


class TestROIResultDataClass:
    """Tests fuer ROIResult Datenstruktur."""

    @pytest.mark.asyncio
    async def test_roi_result_dataclass(self) -> None:
        """Testet ROIResult Datenstruktur."""
        from app.services.privat.property_calculation_service import (
            ROIResult,
        )

        result = ROIResult(
            property_id=uuid4(),
            total_roi=Decimal("45.5"),
            annual_roi=Decimal("7.58"),
            value_appreciation=Decimal("52000.00"),
            appreciation_rate=Decimal("20.0"),
            total_rental_income=Decimal("86400.00"),
            total_costs=Decimal("24000.00"),
            holding_period_years=Decimal("6"),
        )

        assert result.total_roi == Decimal("45.5")
        assert result.annual_roi == Decimal("7.58")
        assert result.value_appreciation == Decimal("52000.00")
        assert result.holding_period_years == Decimal("6")


class TestCostTrendResultDataClass:
    """Tests fuer CostTrendResult Datenstruktur."""

    @pytest.mark.asyncio
    async def test_cost_trend_result_dataclass(self) -> None:
        """Testet CostTrendResult Datenstruktur."""
        from app.services.privat.property_calculation_service import (
            CostTrendResult,
        )

        result = CostTrendResult(
            property_id=uuid4(),
            monthly_costs=[
                {"month": "2024-01", "amount": Decimal("280.00")},
                {"month": "2024-02", "amount": Decimal("295.00")},
                {"month": "2024-03", "amount": Decimal("275.00")},
            ],
            average_monthly_cost=Decimal("283.33"),
            trend_direction="stable",
            trend_percentage=Decimal("2.5"),
            ytd_total=Decimal("850.00"),
        )

        assert len(result.monthly_costs) == 3
        assert result.average_monthly_cost == Decimal("283.33")
        assert result.trend_direction == "stable"


class TestPropertyKPIsDataClass:
    """Tests fuer PropertyKPIs Datenstruktur."""

    @pytest.mark.asyncio
    async def test_property_kpis_dataclass(self) -> None:
        """Testet PropertyKPIs Datenstruktur."""
        from app.services.privat.property_calculation_service import (
            PropertyKPIs,
        )

        kpis = PropertyKPIs(
            property_id=uuid4(),
            rental_yield=None,
            roi=None,
            cost_trend=None,
        )

        assert kpis.property_id is not None
        assert kpis.rental_yield is None
        assert kpis.roi is None
        assert kpis.cost_trend is None
        assert kpis.calculated_at is not None


class TestServiceMethodsExist:
    """Tests dass alle wichtigen Service-Methoden existieren."""

    @pytest.mark.asyncio
    async def test_service_has_calculate_rental_yield_method(self) -> None:
        """Testet dass Service calculate_rental_yield Methode hat."""
        from app.services.privat.property_calculation_service import (
            PropertyCalculationService,
        )

        service = PropertyCalculationService()

        assert hasattr(service, "calculate_rental_yield")
        assert callable(getattr(service, "calculate_rental_yield"))

    @pytest.mark.asyncio
    async def test_service_has_calculate_roi_method(self) -> None:
        """Testet dass Service calculate_roi Methode hat."""
        from app.services.privat.property_calculation_service import (
            PropertyCalculationService,
        )

        service = PropertyCalculationService()

        assert hasattr(service, "calculate_roi")
        assert callable(getattr(service, "calculate_roi"))

    @pytest.mark.asyncio
    async def test_service_has_get_cost_trend_method(self) -> None:
        """Testet dass Service get_cost_trend Methode hat."""
        from app.services.privat.property_calculation_service import (
            PropertyCalculationService,
        )

        service = PropertyCalculationService()

        assert hasattr(service, "get_cost_trend")
        assert callable(getattr(service, "get_cost_trend"))

    @pytest.mark.asyncio
    async def test_service_has_calculate_all_kpis_method(self) -> None:
        """Testet dass Service calculate_all_kpis Methode hat."""
        from app.services.privat.property_calculation_service import (
            PropertyCalculationService,
        )

        service = PropertyCalculationService()

        assert hasattr(service, "calculate_all_kpis")
        assert callable(getattr(service, "calculate_all_kpis"))

    @pytest.mark.asyncio
    async def test_service_has_recalculate_all_properties_method(self) -> None:
        """Testet dass Service recalculate_all_properties Methode hat."""
        from app.services.privat.property_calculation_service import (
            PropertyCalculationService,
        )

        service = PropertyCalculationService()

        assert hasattr(service, "recalculate_all_properties")
        assert callable(getattr(service, "recalculate_all_properties"))


class TestGetServiceFunction:
    """Tests fuer get_property_calculation_service Factory."""

    @pytest.mark.asyncio
    async def test_get_service_function_exists(self) -> None:
        """Testet dass get_property_calculation_service existiert."""
        from app.services.privat.property_calculation_service import (
            get_property_calculation_service,
        )

        assert get_property_calculation_service is not None
        assert callable(get_property_calculation_service)

    @pytest.mark.asyncio
    async def test_get_service_returns_instance(self) -> None:
        """Testet dass get_property_calculation_service eine Instanz zurueckgibt."""
        from app.services.privat.property_calculation_service import (
            PropertyCalculationService,
            get_property_calculation_service,
        )

        service = get_property_calculation_service()

        assert isinstance(service, PropertyCalculationService)
