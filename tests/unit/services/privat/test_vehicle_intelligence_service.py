"""
Unit-Tests fuer VehicleIntelligenceService

Testet:
- Service-Initialisierung
- Dataclass-Strukturen
- Hilfsmethoden (synchron)
- Fahrzeugklassen-Bestimmung
- Depreciation-Interpolation
- Methoden-Existenz
"""

import pytest
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from app.services.privat.vehicle_intelligence_service import (
    VehicleIntelligenceService,
    get_vehicle_intelligence_service,
    VehicleDepreciation,
    VehicleTCO,
    FuelAnalysis,
    ServicePrediction,
    VehicleAnalytics,
    DEPRECIATION_CURVES,
    MAKE_TO_CLASS,
    FUEL_COSTS,
    SERVICE_INTERVALS,
)


class TestVehicleIntelligenceServiceInit:
    """Tests fuer Service-Initialisierung."""

    def test_service_initialization(self) -> None:
        """Testet Service-Initialisierung."""
        service = VehicleIntelligenceService()
        assert service is not None


class TestVehicleDepreciationDataClass:
    """Tests fuer VehicleDepreciation Datenstruktur."""

    def test_vehicle_depreciation_creation(self) -> None:
        """Testet VehicleDepreciation Erstellung."""
        vehicle_id = uuid4()
        depreciation = VehicleDepreciation(
            vehicle_id=vehicle_id,
            purchase_price=Decimal("50000"),
            current_estimated_value=Decimal("35000"),
            depreciation_absolute=Decimal("15000"),
            depreciation_percent=Decimal("30"),
            monthly_depreciation=Decimal("500"),
            vehicle_class="premium",
            age_years=Decimal("2.5"),
        )

        assert depreciation.vehicle_id == vehicle_id
        assert depreciation.depreciation_percent == Decimal("30")
        assert depreciation.mileage_factor == Decimal("1.0")  # Default


class TestVehicleTCODataClass:
    """Tests fuer VehicleTCO Datenstruktur."""

    def test_vehicle_tco_creation(self) -> None:
        """Testet VehicleTCO Erstellung."""
        vehicle_id = uuid4()
        tco = VehicleTCO(
            vehicle_id=vehicle_id,
            purchase_price=Decimal("45000"),
            current_value=Decimal("32000"),
            depreciation_total=Decimal("13000"),
            fuel_costs_annual=Decimal("2400"),
            insurance_annual=Decimal("800"),
            tax_annual=Decimal("180"),
            maintenance_annual=Decimal("450"),
            repairs_annual=Decimal("300"),
            total_annual_costs=Decimal("4130"),
            cost_per_km=Decimal("0.35"),
            cost_per_month=Decimal("344.17"),
        )

        assert tco.vehicle_id == vehicle_id
        assert tco.total_annual_costs == Decimal("4130")


class TestFuelAnalysisDataClass:
    """Tests fuer FuelAnalysis Datenstruktur."""

    def test_fuel_analysis_creation(self) -> None:
        """Testet FuelAnalysis Erstellung."""
        vehicle_id = uuid4()
        analysis = FuelAnalysis(
            vehicle_id=vehicle_id,
            average_consumption=Decimal("7.5"),
            average_cost_per_100km=Decimal("13.13"),
            average_cost_per_fill=Decimal("75.00"),
            consumption_trend="stable",
            trend_percent=Decimal("0"),
            total_fuel_cost_ytd=Decimal("1500"),
            total_km_ytd=12000,
            fill_count_ytd=20,
        )

        assert analysis.average_consumption == Decimal("7.5")
        assert analysis.consumption_trend == "stable"


class TestServicePredictionDataClass:
    """Tests fuer ServicePrediction Datenstruktur."""

    def test_service_prediction_creation(self) -> None:
        """Testet ServicePrediction Erstellung."""
        vehicle_id = uuid4()
        prediction = ServicePrediction(
            vehicle_id=vehicle_id,
            next_service_km=60000,
            next_service_date=date.today() + timedelta(days=60),
            km_until_service=3000,
            days_until_service=60,
            tuev_due=date.today() + timedelta(days=180),
            days_until_tuev=180,
            estimated_service_cost=Decimal("400"),
            recommendations=["Service-Termin vereinbaren"],
        )

        assert prediction.next_service_km == 60000
        assert prediction.days_until_service == 60


class TestVehicleAnalyticsDataClass:
    """Tests fuer VehicleAnalytics Datenstruktur."""

    def test_vehicle_analytics_creation(self) -> None:
        """Testet VehicleAnalytics Erstellung."""
        vehicle_id = uuid4()
        analytics = VehicleAnalytics(
            vehicle_id=vehicle_id,
            health_score=Decimal("75"),
            recommendations=["Service faellig", "TUeV pruefen"],
            optimal_sell_date=date.today() + timedelta(days=365),
            optimal_sell_reason="Fahrzeug ueber 6 Jahre",
        )

        assert analytics.health_score == Decimal("75")
        assert len(analytics.recommendations) == 2


class TestDepreciationCurves:
    """Tests fuer Depreciation-Kurven Konstanten."""

    def test_depreciation_curves_exist(self) -> None:
        """Testet dass Depreciation-Kurven existieren."""
        assert "premium" in DEPRECIATION_CURVES
        assert "volume" in DEPRECIATION_CURVES
        assert "budget" in DEPRECIATION_CURVES
        assert "electric" in DEPRECIATION_CURVES
        assert "classic" in DEPRECIATION_CURVES

    def test_depreciation_curve_year_0_is_100_percent(self) -> None:
        """Jahr 0 sollte 100% Wert haben."""
        for curve_name, curve in DEPRECIATION_CURVES.items():
            assert curve[0] == 1.0, f"{curve_name} sollte bei Jahr 0 Faktor 1.0 haben"

    def test_depreciation_curve_decreasing(self) -> None:
        """Wertverlust-Kurven sollten abnehmend sein (ausser Classic)."""
        for curve_name in ["premium", "volume", "budget", "electric"]:
            curve = DEPRECIATION_CURVES[curve_name]
            years = sorted(curve.keys())
            for i in range(1, len(years)):
                assert curve[years[i]] <= curve[years[i - 1]], \
                    f"{curve_name}: Jahr {years[i]} sollte <= Jahr {years[i-1]} sein"


class TestMakeToClassMapping:
    """Tests fuer Marken-zu-Klasse Mapping."""

    def test_premium_brands(self) -> None:
        """Premium-Marken sind korrekt zugeordnet."""
        premium_brands = ["mercedes", "mercedes-benz", "bmw", "audi", "porsche"]
        for brand in premium_brands:
            assert MAKE_TO_CLASS.get(brand) == "premium", f"{brand} sollte premium sein"

    def test_volume_brands(self) -> None:
        """Volumen-Marken sind korrekt zugeordnet."""
        volume_brands = ["volkswagen", "vw", "ford", "opel", "skoda", "toyota"]
        for brand in volume_brands:
            assert MAKE_TO_CLASS.get(brand) == "volume", f"{brand} sollte volume sein"

    def test_budget_brands(self) -> None:
        """Budget-Marken sind korrekt zugeordnet."""
        budget_brands = ["dacia", "fiat", "hyundai", "kia"]
        for brand in budget_brands:
            assert MAKE_TO_CLASS.get(brand) == "budget", f"{brand} sollte budget sein"


class TestFuelCosts:
    """Tests fuer Kraftstoffkosten-Konstanten."""

    def test_fuel_costs_exist(self) -> None:
        """Testet dass Kraftstoffkosten existieren."""
        assert "benzin" in FUEL_COSTS
        assert "diesel" in FUEL_COSTS
        assert "elektro" in FUEL_COSTS

    def test_elektro_cheaper_per_kwh(self) -> None:
        """Strom sollte pro kWh guenstiger sein als Benzin pro Liter."""
        assert FUEL_COSTS["elektro"] < FUEL_COSTS["benzin"]


class TestServiceIntervals:
    """Tests fuer Service-Intervall-Konstanten."""

    def test_service_intervals_exist(self) -> None:
        """Testet dass Service-Intervalle existieren."""
        assert "benzin" in SERVICE_INTERVALS
        assert "diesel" in SERVICE_INTERVALS
        assert "elektro" in SERVICE_INTERVALS

    def test_elektro_longer_interval(self) -> None:
        """Elektro-Fahrzeuge haben laengere Service-Intervalle."""
        assert SERVICE_INTERVALS["elektro"] > SERVICE_INTERVALS["benzin"]


class TestGetVehicleClass:
    """Tests fuer _get_vehicle_class Methode."""

    @pytest.fixture
    def service(self) -> VehicleIntelligenceService:
        return VehicleIntelligenceService()

    def test_get_vehicle_class_premium(self, service: VehicleIntelligenceService) -> None:
        """Premium-Marken werden erkannt."""
        assert service._get_vehicle_class("BMW", None) == "premium"
        assert service._get_vehicle_class("Mercedes", None) == "premium"
        assert service._get_vehicle_class("AUDI", None) == "premium"

    def test_get_vehicle_class_volume(self, service: VehicleIntelligenceService) -> None:
        """Volumen-Marken werden erkannt."""
        assert service._get_vehicle_class("VW", None) == "volume"
        assert service._get_vehicle_class("Ford", None) == "volume"
        assert service._get_vehicle_class("Toyota", None) == "volume"

    def test_get_vehicle_class_budget(self, service: VehicleIntelligenceService) -> None:
        """Budget-Marken werden erkannt."""
        assert service._get_vehicle_class("Dacia", None) == "budget"
        assert service._get_vehicle_class("FIAT", None) == "budget"

    def test_get_vehicle_class_electric_override(self, service: VehicleIntelligenceService) -> None:
        """Elektro-Kraftstoff ueberschreibt Markenklasse."""
        assert service._get_vehicle_class("BMW", "Elektro") == "electric"
        assert service._get_vehicle_class("Mercedes", "elektro") == "electric"

    def test_get_vehicle_class_default(self, service: VehicleIntelligenceService) -> None:
        """Unbekannte Marken bekommen Default-Klasse."""
        assert service._get_vehicle_class("UnbekannteMarke", None) == "volume"
        assert service._get_vehicle_class(None, None) == "volume"


class TestInterpolateDepreciation:
    """Tests fuer _interpolate_depreciation Methode."""

    @pytest.fixture
    def service(self) -> VehicleIntelligenceService:
        return VehicleIntelligenceService()

    def test_interpolate_year_0(self, service: VehicleIntelligenceService) -> None:
        """Jahr 0 gibt 1.0 zurueck."""
        curve = DEPRECIATION_CURVES["volume"]
        factor = service._interpolate_depreciation(curve, 0.0)
        assert factor == 1.0

    def test_interpolate_exact_year(self, service: VehicleIntelligenceService) -> None:
        """Exakte Jahre geben den Kurven-Wert zurueck."""
        curve = DEPRECIATION_CURVES["volume"]
        factor = service._interpolate_depreciation(curve, 1.0)
        assert factor == curve[1]

    def test_interpolate_between_years(self, service: VehicleIntelligenceService) -> None:
        """Zwischen-Jahre: Implementation nutzt int() fuer Jahr-Lookup."""
        curve = DEPRECIATION_CURVES["volume"]
        factor = service._interpolate_depreciation(curve, 1.5)

        # Die Implementation nutzt int(age_years) fuer exakten Treffer
        # 1.5 -> int(1.5) = 1 -> curve[1] = 0.72
        assert factor == curve[1]

    def test_interpolate_negative_years(self, service: VehicleIntelligenceService) -> None:
        """Negative Jahre geben 1.0 zurueck."""
        curve = DEPRECIATION_CURVES["volume"]
        factor = service._interpolate_depreciation(curve, -1.0)
        assert factor == 1.0


class TestServiceMethodsExist:
    """Tests dass alle wichtigen Service-Methoden existieren."""

    @pytest.fixture
    def service(self) -> VehicleIntelligenceService:
        return VehicleIntelligenceService()

    def test_service_has_calculate_depreciation_method(self, service: VehicleIntelligenceService) -> None:
        """Testet dass Service calculate_depreciation Methode hat."""
        assert hasattr(service, "calculate_depreciation")
        assert callable(getattr(service, "calculate_depreciation"))

    def test_service_has_calculate_tco_method(self, service: VehicleIntelligenceService) -> None:
        """Testet dass Service calculate_tco Methode hat."""
        assert hasattr(service, "calculate_tco")
        assert callable(getattr(service, "calculate_tco"))

    def test_service_has_analyze_fuel_consumption_method(self, service: VehicleIntelligenceService) -> None:
        """Testet dass Service analyze_fuel_consumption Methode hat."""
        assert hasattr(service, "analyze_fuel_consumption")
        assert callable(getattr(service, "analyze_fuel_consumption"))

    def test_service_has_predict_service_method(self, service: VehicleIntelligenceService) -> None:
        """Testet dass Service predict_service Methode hat."""
        assert hasattr(service, "predict_service")
        assert callable(getattr(service, "predict_service"))

    def test_service_has_get_full_analytics_method(self, service: VehicleIntelligenceService) -> None:
        """Testet dass Service get_full_analytics Methode hat."""
        assert hasattr(service, "get_full_analytics")
        assert callable(getattr(service, "get_full_analytics"))

    def test_service_has_recalculate_all_vehicles_method(self, service: VehicleIntelligenceService) -> None:
        """Testet dass Service recalculate_all_vehicles Methode hat."""
        assert hasattr(service, "recalculate_all_vehicles")
        assert callable(getattr(service, "recalculate_all_vehicles"))


class TestHelperMethodsExist:
    """Tests dass alle Hilfsmethoden existieren."""

    @pytest.fixture
    def service(self) -> VehicleIntelligenceService:
        return VehicleIntelligenceService()

    def test_service_has_get_vehicle_class_method(self, service: VehicleIntelligenceService) -> None:
        """Testet dass Service _get_vehicle_class Methode hat."""
        assert hasattr(service, "_get_vehicle_class")
        assert callable(getattr(service, "_get_vehicle_class"))

    def test_service_has_interpolate_depreciation_method(self, service: VehicleIntelligenceService) -> None:
        """Testet dass Service _interpolate_depreciation Methode hat."""
        assert hasattr(service, "_interpolate_depreciation")
        assert callable(getattr(service, "_interpolate_depreciation"))

    def test_service_has_calculate_optimal_sell_method(self, service: VehicleIntelligenceService) -> None:
        """Testet dass Service _calculate_optimal_sell Methode hat."""
        assert hasattr(service, "_calculate_optimal_sell")
        assert callable(getattr(service, "_calculate_optimal_sell"))

    def test_service_has_calculate_health_score_method(self, service: VehicleIntelligenceService) -> None:
        """Testet dass Service _calculate_health_score Methode hat."""
        assert hasattr(service, "_calculate_health_score")
        assert callable(getattr(service, "_calculate_health_score"))


class TestHealthScoreCalculation:
    """Tests fuer _calculate_health_score Methode."""

    @pytest.fixture
    def service(self) -> VehicleIntelligenceService:
        return VehicleIntelligenceService()

    def test_health_score_base(self, service: VehicleIntelligenceService) -> None:
        """Basis-Score ohne Daten ist 70."""
        vehicle_id = uuid4()
        analytics = VehicleAnalytics(vehicle_id=vehicle_id)
        score = service._calculate_health_score(analytics)

        # Basis-Score ist 70
        assert score == Decimal("70.00")

    def test_health_score_good_depreciation(self, service: VehicleIntelligenceService) -> None:
        """Niedriger Wertverlust erhoeht Score."""
        vehicle_id = uuid4()
        analytics = VehicleAnalytics(
            vehicle_id=vehicle_id,
            depreciation=VehicleDepreciation(
                vehicle_id=vehicle_id,
                purchase_price=Decimal("50000"),
                current_estimated_value=Decimal("45000"),
                depreciation_absolute=Decimal("5000"),
                depreciation_percent=Decimal("10"),  # < 20%
                monthly_depreciation=Decimal("200"),
                vehicle_class="premium",
                age_years=Decimal("1"),
            ),
        )
        score = service._calculate_health_score(analytics)

        # Sollte ueber Basis (70) liegen
        assert score > Decimal("70")

    def test_health_score_bounded(self, service: VehicleIntelligenceService) -> None:
        """Score bleibt im Bereich 0-100."""
        vehicle_id = uuid4()
        analytics = VehicleAnalytics(
            vehicle_id=vehicle_id,
            depreciation=VehicleDepreciation(
                vehicle_id=vehicle_id,
                purchase_price=Decimal("50000"),
                current_estimated_value=Decimal("40000"),
                depreciation_absolute=Decimal("10000"),
                depreciation_percent=Decimal("20"),
                monthly_depreciation=Decimal("300"),
                vehicle_class="volume",
                age_years=Decimal("3"),
            ),
            tco=VehicleTCO(
                vehicle_id=vehicle_id,
                cost_per_km=Decimal("0.25"),  # Gut
            ),
            fuel_analysis=FuelAnalysis(
                vehicle_id=vehicle_id,
                average_consumption=Decimal("6.5"),
                average_cost_per_100km=Decimal("11.50"),
                average_cost_per_fill=Decimal("65"),
                consumption_trend="improving",
                trend_percent=Decimal("5"),
            ),
        )
        score = service._calculate_health_score(analytics)

        assert Decimal("0") <= score <= Decimal("100")


class TestOptimalSellCalculation:
    """Tests fuer _calculate_optimal_sell Methode."""

    @pytest.fixture
    def service(self) -> VehicleIntelligenceService:
        return VehicleIntelligenceService()

    def test_optimal_sell_no_data(self, service: VehicleIntelligenceService) -> None:
        """Ohne Daten kein Verkaufsdatum."""
        sell_date, reason = service._calculate_optimal_sell(None, None)
        assert sell_date is None
        assert reason == ""

    def test_optimal_sell_premium_over_4_years(self, service: VehicleIntelligenceService) -> None:
        """Premium nach 4+ Jahren: Empfehlung."""
        vehicle_id = uuid4()
        depreciation = VehicleDepreciation(
            vehicle_id=vehicle_id,
            purchase_price=Decimal("60000"),
            current_estimated_value=Decimal("35000"),
            depreciation_absolute=Decimal("25000"),
            depreciation_percent=Decimal("42"),
            monthly_depreciation=Decimal("400"),
            vehicle_class="premium",
            age_years=Decimal("4.5"),
        )
        tco = VehicleTCO(
            vehicle_id=vehicle_id,
            cost_per_month=Decimal("350"),
        )

        sell_date, reason = service._calculate_optimal_sell(depreciation, tco)

        assert sell_date is not None
        assert "Premium" in reason or "4 Jahre" in reason


class TestGetServiceFunction:
    """Tests fuer get_vehicle_intelligence_service Factory."""

    def test_get_service_function_exists(self) -> None:
        """Testet dass get_vehicle_intelligence_service existiert."""
        assert get_vehicle_intelligence_service is not None
        assert callable(get_vehicle_intelligence_service)

    def test_get_service_returns_instance(self) -> None:
        """Testet dass get_vehicle_intelligence_service eine Instanz zurueckgibt."""
        service = get_vehicle_intelligence_service()
        assert isinstance(service, VehicleIntelligenceService)

    def test_get_service_singleton(self) -> None:
        """Testet dass get_vehicle_intelligence_service Singleton ist."""
        service1 = get_vehicle_intelligence_service()
        service2 = get_vehicle_intelligence_service()
        assert service1 is service2
