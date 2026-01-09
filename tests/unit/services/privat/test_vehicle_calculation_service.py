"""
Unit Tests fuer VehicleCalculationService.

Testet:
- Service-Initialisierung
- Dataclass-Strukturen
- Methoden-Existenz
"""

import pytest
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession


class TestVehicleCalculationService:
    """Tests fuer VehicleCalculationService."""

    @pytest.mark.asyncio
    async def test_service_initialization(self) -> None:
        """Testet Service-Initialisierung."""
        from app.services.privat.vehicle_calculation_service import (
            VehicleCalculationService,
        )

        service = VehicleCalculationService()
        assert service is not None

    @pytest.mark.asyncio
    async def test_dataclass_imports(self) -> None:
        """Testet dass alle Datenklassen importierbar sind."""
        from app.services.privat.vehicle_calculation_service import (
            DepreciationResult,
            FuelConsumptionResult,
            ServicePredictionResult,
            TCOResult,
            VehicleCalculationService,
            VehicleKPIs,
        )

        assert VehicleCalculationService is not None
        assert DepreciationResult is not None
        assert TCOResult is not None
        assert FuelConsumptionResult is not None
        assert ServicePredictionResult is not None
        assert VehicleKPIs is not None


class TestDepreciationResultDataClass:
    """Tests fuer DepreciationResult Datenstruktur."""

    @pytest.mark.asyncio
    async def test_depreciation_result_dataclass(self) -> None:
        """Testet DepreciationResult Datenstruktur."""
        from app.services.privat.vehicle_calculation_service import (
            DepreciationResult,
        )

        result = DepreciationResult(
            vehicle_id=uuid4(),
            purchase_price=Decimal("45000.00"),
            current_estimated_value=Decimal("32000.00"),
            total_depreciation=Decimal("13000.00"),
            depreciation_rate=Decimal("28.89"),
            monthly_depreciation=Decimal("241.00"),
            annual_depreciation=Decimal("2892.00"),
            age_months=54,
        )

        assert result.purchase_price == Decimal("45000.00")
        assert result.current_estimated_value == Decimal("32000.00")
        assert result.total_depreciation == Decimal("13000.00")
        assert result.depreciation_rate == Decimal("28.89")
        assert result.monthly_depreciation == Decimal("241.00")
        assert result.age_months == 54


class TestTCOResultDataClass:
    """Tests fuer TCOResult Datenstruktur."""

    @pytest.mark.asyncio
    async def test_tco_result_dataclass(self) -> None:
        """Testet TCOResult Datenstruktur."""
        from app.services.privat.vehicle_calculation_service import (
            TCOResult,
        )

        result = TCOResult(
            vehicle_id=uuid4(),
            tco_total=Decimal("25000.00"),
            tco_per_km=Decimal("0.38"),
            tco_per_month=Decimal("463.00"),
            components={
                "fuel": Decimal("8500.00"),
                "insurance": Decimal("4800.00"),
                "tax": Decimal("1120.00"),
                "maintenance": Decimal("3200.00"),
                "depreciation": Decimal("7380.00"),
            },
            total_km=65000,
            holding_period_months=54,
        )

        assert result.tco_total == Decimal("25000.00")
        assert result.tco_per_km == Decimal("0.38")
        assert result.total_km == 65000
        assert "fuel" in result.components
        assert result.components["fuel"] == Decimal("8500.00")


class TestFuelConsumptionResultDataClass:
    """Tests fuer FuelConsumptionResult Datenstruktur."""

    @pytest.mark.asyncio
    async def test_fuel_consumption_result_dataclass(self) -> None:
        """Testet FuelConsumptionResult Datenstruktur."""
        from app.services.privat.vehicle_calculation_service import (
            FuelConsumptionResult,
        )

        result = FuelConsumptionResult(
            vehicle_id=uuid4(),
            average_consumption=Decimal("6.8"),
            total_fuel_cost=Decimal("2475.00"),
            total_liters=Decimal("1500.00"),
            total_km_tracked=22058,
            cost_per_km=Decimal("0.11"),
            fuel_entries_count=25,
            trend="stable",
        )

        assert result.average_consumption == Decimal("6.8")
        assert result.total_liters == Decimal("1500.00")
        assert result.cost_per_km == Decimal("0.11")
        assert result.trend == "stable"
        assert result.fuel_entries_count == 25


class TestServicePredictionResultDataClass:
    """Tests fuer ServicePredictionResult Datenstruktur."""

    @pytest.mark.asyncio
    async def test_service_prediction_result_dataclass(self) -> None:
        """Testet ServicePredictionResult Datenstruktur."""
        from app.services.privat.vehicle_calculation_service import (
            ServicePredictionResult,
        )

        result = ServicePredictionResult(
            vehicle_id=uuid4(),
            next_service_date=date.today() + timedelta(days=90),
            next_service_km=78000,
            days_until_service=90,
            km_until_service=13000,
            average_daily_km=Decimal("40.0"),
            service_type="scheduled",
        )

        assert result.next_service_km == 78000
        assert result.days_until_service == 90
        assert result.km_until_service == 13000
        assert result.service_type == "scheduled"
        assert result.average_daily_km == Decimal("40.0")


class TestVehicleKPIsDataClass:
    """Tests fuer VehicleKPIs Datenstruktur."""

    @pytest.mark.asyncio
    async def test_vehicle_kpis_dataclass(self) -> None:
        """Testet VehicleKPIs Datenstruktur."""
        from app.services.privat.vehicle_calculation_service import (
            VehicleKPIs,
        )

        kpis = VehicleKPIs(
            vehicle_id=uuid4(),
            depreciation=None,
            tco=None,
            fuel_consumption=None,
            service_prediction=None,
        )

        assert kpis.vehicle_id is not None
        assert kpis.depreciation is None
        assert kpis.tco is None
        assert kpis.fuel_consumption is None
        assert kpis.service_prediction is None
        assert kpis.calculated_at is not None


class TestServiceMethodsExist:
    """Tests dass alle wichtigen Service-Methoden existieren."""

    @pytest.mark.asyncio
    async def test_service_has_calculate_depreciation_method(self) -> None:
        """Testet dass Service calculate_depreciation Methode hat."""
        from app.services.privat.vehicle_calculation_service import (
            VehicleCalculationService,
        )

        service = VehicleCalculationService()

        assert hasattr(service, "calculate_depreciation")
        assert callable(getattr(service, "calculate_depreciation"))

    @pytest.mark.asyncio
    async def test_service_has_calculate_tco_method(self) -> None:
        """Testet dass Service calculate_tco Methode hat."""
        from app.services.privat.vehicle_calculation_service import (
            VehicleCalculationService,
        )

        service = VehicleCalculationService()

        assert hasattr(service, "calculate_tco")
        assert callable(getattr(service, "calculate_tco"))

    @pytest.mark.asyncio
    async def test_service_has_analyze_fuel_consumption_method(self) -> None:
        """Testet dass Service analyze_fuel_consumption Methode hat."""
        from app.services.privat.vehicle_calculation_service import (
            VehicleCalculationService,
        )

        service = VehicleCalculationService()

        assert hasattr(service, "analyze_fuel_consumption")
        assert callable(getattr(service, "analyze_fuel_consumption"))

    @pytest.mark.asyncio
    async def test_service_has_predict_next_service_method(self) -> None:
        """Testet dass Service predict_next_service Methode hat."""
        from app.services.privat.vehicle_calculation_service import (
            VehicleCalculationService,
        )

        service = VehicleCalculationService()

        assert hasattr(service, "predict_next_service")
        assert callable(getattr(service, "predict_next_service"))

    @pytest.mark.asyncio
    async def test_service_has_calculate_all_kpis_method(self) -> None:
        """Testet dass Service calculate_all_kpis Methode hat."""
        from app.services.privat.vehicle_calculation_service import (
            VehicleCalculationService,
        )

        service = VehicleCalculationService()

        assert hasattr(service, "calculate_all_kpis")
        assert callable(getattr(service, "calculate_all_kpis"))

    @pytest.mark.asyncio
    async def test_service_has_recalculate_all_vehicles_method(self) -> None:
        """Testet dass Service recalculate_all_vehicles Methode hat."""
        from app.services.privat.vehicle_calculation_service import (
            VehicleCalculationService,
        )

        service = VehicleCalculationService()

        assert hasattr(service, "recalculate_all_vehicles")
        assert callable(getattr(service, "recalculate_all_vehicles"))


class TestGetServiceFunction:
    """Tests fuer get_vehicle_calculation_service Factory."""

    @pytest.mark.asyncio
    async def test_get_service_function_exists(self) -> None:
        """Testet dass get_vehicle_calculation_service existiert."""
        from app.services.privat.vehicle_calculation_service import (
            get_vehicle_calculation_service,
        )

        assert get_vehicle_calculation_service is not None
        assert callable(get_vehicle_calculation_service)

    @pytest.mark.asyncio
    async def test_get_service_returns_instance(self) -> None:
        """Testet dass get_vehicle_calculation_service eine Instanz zurueckgibt."""
        from app.services.privat.vehicle_calculation_service import (
            VehicleCalculationService,
            get_vehicle_calculation_service,
        )

        service = get_vehicle_calculation_service()

        assert isinstance(service, VehicleCalculationService)
