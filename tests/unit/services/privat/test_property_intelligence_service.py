"""
Unit-Tests fuer PropertyCalculationService

Testet:
- Mietrendite-Berechnung (Brutto/Netto)
- ROI-Berechnung (Gesamt/Jaehrlich)
- Nebenkosten-Trend-Analyse
- Batch-KPI-Berechnung
"""

import pytest
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from app.services.privat.property_calculation_service import (
    PropertyCalculationService,
    RentalYieldResult,
    ROIResult,
    CostTrendResult,
    PropertyKPIs,
)


class TestRentalYieldCalculation:
    """Tests fuer Mietrendite-Berechnung."""

    @pytest.fixture
    def service(self) -> PropertyCalculationService:
        """Erstellt eine Service-Instanz."""
        return PropertyCalculationService()

    @pytest.mark.asyncio
    async def test_calculate_rental_yield_basic(self, service: PropertyCalculationService):
        """Grundlegende Bruttomietrendite-Berechnung."""
        # Mock Property mit Mietern
        property_mock = MagicMock()
        property_mock.id = uuid4()
        property_mock.purchase_price = Decimal("300000")
        property_mock.purchase_date = date.today() - timedelta(days=365)

        # Mock Mieter
        tenant_mock = MagicMock()
        tenant_mock.is_active = True
        tenant_mock.monthly_rent = Decimal("1200")
        property_mock.tenants = [tenant_mock]

        # Mock DB
        db_mock = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = property_mock
        db_mock.execute.return_value = result_mock

        # Service call patchen
        with patch.object(service, '_calculate_annual_costs', return_value=Decimal("0")):
            result = await service.calculate_rental_yield(db_mock, property_mock.id)

        assert result is not None
        # Bruttomietrendite: (1200 * 12) / 300000 * 100 = 4.8%
        assert result.gross_rental_yield == pytest.approx(Decimal("4.8"), rel=0.01)
        assert result.annual_rental_income == Decimal("14400")

    @pytest.mark.asyncio
    async def test_calculate_rental_yield_no_purchase_price(self, service: PropertyCalculationService):
        """Ohne Kaufpreis keine Berechnung moeglich."""
        property_mock = MagicMock()
        property_mock.id = uuid4()
        property_mock.purchase_price = None  # Kein Kaufpreis
        property_mock.tenants = []

        db_mock = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = property_mock
        db_mock.execute.return_value = result_mock

        result = await service.calculate_rental_yield(db_mock, property_mock.id)

        assert result is None

    @pytest.mark.asyncio
    async def test_calculate_rental_yield_multiple_tenants(self, service: PropertyCalculationService):
        """Mehrere Mieter werden korrekt summiert."""
        property_mock = MagicMock()
        property_mock.id = uuid4()
        property_mock.purchase_price = Decimal("500000")

        # Zwei aktive Mieter
        tenant1 = MagicMock()
        tenant1.is_active = True
        tenant1.monthly_rent = Decimal("800")

        tenant2 = MagicMock()
        tenant2.is_active = True
        tenant2.monthly_rent = Decimal("950")

        # Ein inaktiver Mieter (sollte ignoriert werden)
        tenant3 = MagicMock()
        tenant3.is_active = False
        tenant3.monthly_rent = Decimal("1000")

        property_mock.tenants = [tenant1, tenant2, tenant3]

        db_mock = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = property_mock
        db_mock.execute.return_value = result_mock

        with patch.object(service, '_calculate_annual_costs', return_value=Decimal("0")):
            result = await service.calculate_rental_yield(db_mock, property_mock.id)

        assert result is not None
        # (800 + 950) * 12 = 21000 jaehrlich
        assert result.annual_rental_income == Decimal("21000")
        # 21000 / 500000 * 100 = 4.2%
        assert result.gross_rental_yield == pytest.approx(Decimal("4.2"), rel=0.01)


class TestROICalculation:
    """Tests fuer ROI-Berechnung."""

    @pytest.fixture
    def service(self) -> PropertyCalculationService:
        return PropertyCalculationService()

    @pytest.mark.asyncio
    async def test_calculate_roi_basic(self, service: PropertyCalculationService):
        """Grundlegende ROI-Berechnung."""
        property_mock = MagicMock()
        property_mock.id = uuid4()
        property_mock.purchase_price = Decimal("400000")
        property_mock.purchase_date = date.today() - timedelta(days=730)  # 2 Jahre
        property_mock.current_value = Decimal("450000")  # +50000 Wertsteigerung
        property_mock.notary_costs = Decimal("5000")
        property_mock.land_transfer_tax = Decimal("14000")

        tenant_mock = MagicMock()
        tenant_mock.is_active = True
        tenant_mock.monthly_rent = Decimal("1500")
        property_mock.tenants = [tenant_mock]

        db_mock = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = property_mock
        db_mock.execute.return_value = result_mock

        with patch.object(service, '_calculate_total_costs', return_value=Decimal("5000")):
            result = await service.calculate_roi(db_mock, property_mock.id)

        assert result is not None
        assert result.value_appreciation == Decimal("50000")
        # Wertsteigerungsrate: 50000 / 400000 * 100 = 12.5%
        assert result.appreciation_rate == pytest.approx(Decimal("12.5"), rel=0.01)
        assert result.holding_period_years > Decimal("1.9")

    @pytest.mark.asyncio
    async def test_calculate_roi_no_purchase_date(self, service: PropertyCalculationService):
        """Ohne Kaufdatum keine ROI-Berechnung."""
        property_mock = MagicMock()
        property_mock.id = uuid4()
        property_mock.purchase_price = Decimal("300000")
        property_mock.purchase_date = None
        property_mock.tenants = []

        db_mock = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = property_mock
        db_mock.execute.return_value = result_mock

        result = await service.calculate_roi(db_mock, property_mock.id)

        assert result is None


class TestCostTrendAnalysis:
    """Tests fuer Nebenkosten-Trend-Analyse (Methoden-Existenz)."""

    @pytest.fixture
    def service(self) -> PropertyCalculationService:
        return PropertyCalculationService()

    def test_service_has_get_cost_trend_method(self, service: PropertyCalculationService):
        """Service hat get_cost_trend Methode."""
        assert hasattr(service, "get_cost_trend")
        assert callable(getattr(service, "get_cost_trend"))


class TestPropertyKPIsBatch:
    """Tests fuer Batch-KPI-Berechnung (Methoden-Existenz)."""

    @pytest.fixture
    def service(self) -> PropertyCalculationService:
        return PropertyCalculationService()

    def test_service_has_calculate_all_kpis_method(self, service: PropertyCalculationService):
        """Service hat calculate_all_kpis Methode."""
        assert hasattr(service, "calculate_all_kpis")
        assert callable(getattr(service, "calculate_all_kpis"))

    def test_service_has_recalculate_all_properties_method(self, service: PropertyCalculationService):
        """Service hat recalculate_all_properties Methode."""
        assert hasattr(service, "recalculate_all_properties")
        assert callable(getattr(service, "recalculate_all_properties"))


class TestRentalYieldResult:
    """Tests fuer RentalYieldResult Dataclass."""

    def test_rental_yield_result_creation(self):
        """RentalYieldResult kann erstellt werden."""
        result = RentalYieldResult(
            property_id=uuid4(),
            gross_rental_yield=Decimal("4.5"),
            net_rental_yield=Decimal("3.8"),
            annual_rental_income=Decimal("13500"),
            annual_costs=Decimal("2100"),
            purchase_price=Decimal("300000"),
        )

        assert result.gross_rental_yield == Decimal("4.5")
        assert result.net_rental_yield == Decimal("3.8")
        assert result.calculated_at is not None


class TestROIResult:
    """Tests fuer ROIResult Dataclass."""

    def test_roi_result_creation(self):
        """ROIResult kann erstellt werden."""
        result = ROIResult(
            property_id=uuid4(),
            total_roi=Decimal("25.5"),
            annual_roi=Decimal("8.5"),
            value_appreciation=Decimal("50000"),
            appreciation_rate=Decimal("12.5"),
            total_rental_income=Decimal("36000"),
            total_costs=Decimal("10000"),
            holding_period_years=Decimal("3.0"),
        )

        assert result.total_roi == Decimal("25.5")
        assert result.annual_roi == Decimal("8.5")


class TestCostTrendResult:
    """Tests fuer CostTrendResult Dataclass."""

    def test_cost_trend_result_creation(self):
        """CostTrendResult kann erstellt werden."""
        result = CostTrendResult(
            property_id=uuid4(),
            monthly_costs=[
                {"month": "2024-01", "amount": 150.0},
                {"month": "2024-02", "amount": 155.0},
            ],
            average_monthly_cost=Decimal("152.5"),
            trend_direction="increasing",
            trend_percentage=Decimal("3.3"),
            ytd_total=Decimal("305.0"),
        )

        assert result.trend_direction == "increasing"
        assert len(result.monthly_costs) == 2
