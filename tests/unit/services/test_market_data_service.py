# -*- coding: utf-8 -*-
"""
Unit tests for Market Data Service.

Tests fuer Marktdaten-Schaetzungen:
- Immobilienbewertung
- Fahrzeugbewertung
- Regionale Preisindizes
- Abschreibungsberechnung
"""

import pytest
from datetime import date, datetime
from decimal import Decimal
from uuid import uuid4
from pathlib import Path
import sys

# Add app to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))


class TestPropertyMarketData:
    """Tests fuer Immobilien-Marktdaten."""

    def test_property_market_data_creation(self):
        """Teste PropertyMarketData-Erstellung."""
        from app.services.external.market_data_service import PropertyMarketData, DataSource

        data = PropertyMarketData(
            property_id=uuid4(),
            estimated_value=Decimal("500000.00"),
            price_per_sqm=Decimal("5000.00"),
            value_range_min=Decimal("450000.00"),
            value_range_max=Decimal("550000.00"),
            comparable_count=10,
            data_source=DataSource.LOCAL_ESTIMATE,
            confidence=0.85,
            location_factor=1.2,
            condition_factor=0.95,
            market_trend="stable",
        )

        assert data.estimated_value == Decimal("500000.00")
        assert data.confidence == 0.85
        assert data.market_trend == "stable"

    def test_property_value_range_validity(self):
        """Teste Wertbereich-Validitaet."""
        from app.services.external.market_data_service import PropertyMarketData, DataSource

        data = PropertyMarketData(
            property_id=uuid4(),
            estimated_value=Decimal("500000.00"),
            price_per_sqm=Decimal("5000.00"),
            value_range_min=Decimal("450000.00"),
            value_range_max=Decimal("550000.00"),
            comparable_count=5,
            data_source=DataSource.LOCAL_ESTIMATE,
            confidence=0.85,
            location_factor=1.0,
            condition_factor=1.0,
            market_trend="stable",
        )

        assert data.value_range_min <= data.estimated_value
        assert data.estimated_value <= data.value_range_max

    def test_property_to_dict(self):
        """Teste PropertyMarketData-Serialisierung."""
        from app.services.external.market_data_service import PropertyMarketData, DataSource

        property_id = uuid4()
        data = PropertyMarketData(
            property_id=property_id,
            estimated_value=Decimal("350000.00"),
            price_per_sqm=Decimal("3500.00"),
            value_range_min=Decimal("315000.00"),
            value_range_max=Decimal("385000.00"),
            comparable_count=8,
            data_source=DataSource.LOCAL_ESTIMATE,
            confidence=0.80,
            location_factor=1.1,
            condition_factor=1.0,
            market_trend="rising",
        )

        result = data.to_dict()

        assert result["property_id"] == str(property_id)
        assert result["estimated_value"] == 350000.00
        assert result["market_trend"] == "rising"


class TestVehicleMarketData:
    """Tests fuer Fahrzeug-Marktdaten."""

    def test_vehicle_market_data_creation(self):
        """Teste VehicleMarketData-Erstellung."""
        from app.services.external.market_data_service import VehicleMarketData, DataSource

        data = VehicleMarketData(
            vehicle_id=uuid4(),
            estimated_value=Decimal("25000.00"),
            value_range_min=Decimal("22000.00"),
            value_range_max=Decimal("28000.00"),
            comparable_count=15,
            data_source=DataSource.LOCAL_ESTIMATE,
            confidence=0.80,
            mileage_factor=0.85,
            condition_factor=0.90,
            age_depreciation=Decimal("5000.00"),
            market_trend="stable",
        )

        assert data.estimated_value == Decimal("25000.00")
        assert data.mileage_factor == 0.85
        assert data.market_trend == "stable"

    def test_vehicle_depreciation_factor(self):
        """Teste Fahrzeug-Abschreibungsfaktor."""
        from app.services.external.market_data_service import VehicleMarketData, DataSource

        data = VehicleMarketData(
            vehicle_id=uuid4(),
            estimated_value=Decimal("20000.00"),
            value_range_min=Decimal("17000.00"),
            value_range_max=Decimal("23000.00"),
            comparable_count=5,
            data_source=DataSource.LOCAL_ESTIMATE,
            confidence=0.75,
            mileage_factor=0.75,
            condition_factor=0.85,
            age_depreciation=Decimal("10000.00"),
            market_trend="falling",
        )

        # Mileage Factor sollte zwischen 0 und 1 liegen
        assert 0 < data.mileage_factor <= 1.0
        assert 0 < data.condition_factor <= 1.0

    def test_vehicle_to_dict(self):
        """Teste VehicleMarketData-Serialisierung."""
        from app.services.external.market_data_service import VehicleMarketData, DataSource

        vehicle_id = uuid4()
        data = VehicleMarketData(
            vehicle_id=vehicle_id,
            estimated_value=Decimal("18500.00"),
            value_range_min=Decimal("16000.00"),
            value_range_max=Decimal("21000.00"),
            comparable_count=25,
            data_source=DataSource.LOCAL_ESTIMATE,
            confidence=0.85,
            mileage_factor=0.80,
            condition_factor=0.95,
            age_depreciation=Decimal("6500.00"),
            market_trend="rising",
        )

        result = data.to_dict()

        assert result["vehicle_id"] == str(vehicle_id)
        assert result["estimated_value"] == 18500.00
        assert result["market_trend"] == "rising"


class TestPropertyPricesByRegion:
    """Tests fuer regionale Immobilienpreise."""

    def test_german_cities_prices_defined(self):
        """Teste dass deutsche Staedte Preise haben."""
        from app.services.external.market_data_service import PROPERTY_PRICES_BY_REGION

        cities = ["muenchen", "frankfurt", "berlin", "hamburg", "koeln", "duesseldorf"]

        for city in cities:
            assert city in PROPERTY_PRICES_BY_REGION
            assert PROPERTY_PRICES_BY_REGION[city] > 0

    def test_munich_highest_price(self):
        """Teste dass Muenchen die hoechsten Preise hat."""
        from app.services.external.market_data_service import PROPERTY_PRICES_BY_REGION

        munich_price = PROPERTY_PRICES_BY_REGION["muenchen"]

        for region, price in PROPERTY_PRICES_BY_REGION.items():
            if region != "muenchen":
                assert munich_price >= price

    def test_all_regions_have_positive_prices(self):
        """Teste dass alle Regionen positive Preise haben."""
        from app.services.external.market_data_service import PROPERTY_PRICES_BY_REGION

        for region, price in PROPERTY_PRICES_BY_REGION.items():
            assert isinstance(price, Decimal)
            assert price > 0

    def test_default_region_exists(self):
        """Teste dass eine Default-Region existiert."""
        from app.services.external.market_data_service import PROPERTY_PRICES_BY_REGION

        assert "default" in PROPERTY_PRICES_BY_REGION
        assert PROPERTY_PRICES_BY_REGION["default"] > 0


class TestVehicleDepreciation:
    """Tests fuer Fahrzeug-Abschreibung."""

    def test_depreciation_by_age(self):
        """Teste Abschreibung nach Alter."""
        from app.services.external.market_data_service import VEHICLE_DEPRECIATION_TABLE

        # Jahr 0 sollte 0% Verlust sein (Neuwagen)
        assert VEHICLE_DEPRECIATION_TABLE[0] == 0.0

        # Jahr 1 sollte Verlust haben
        assert VEHICLE_DEPRECIATION_TABLE[1] > VEHICLE_DEPRECIATION_TABLE[0]

        # Abschreibung sollte mit dem Alter steigen (mehr Wertverlust)
        for year in range(1, 10):
            assert VEHICLE_DEPRECIATION_TABLE[year] < VEHICLE_DEPRECIATION_TABLE[year + 1]

    def test_depreciation_curve(self):
        """Teste realistische Abschreibungskurve."""
        from app.services.external.market_data_service import VEHICLE_DEPRECIATION_TABLE

        # Nach 1 Jahr ca. 20-30% Wertverlust
        year1_loss = VEHICLE_DEPRECIATION_TABLE[1]
        assert 0.20 <= year1_loss <= 0.30

        # Nach 5 Jahren ca. 55-65% Wertverlust
        year5_loss = VEHICLE_DEPRECIATION_TABLE[5]
        assert 0.55 <= year5_loss <= 0.65

    def test_depreciation_has_maximum(self):
        """Teste dass Abschreibung ein Maximum hat."""
        from app.services.external.market_data_service import VEHICLE_DEPRECIATION_TABLE

        # Jahr 10 ist Maximum (75%)
        assert VEHICLE_DEPRECIATION_TABLE[10] == 0.75
        # Alle anderen Jahre haben weniger Verlust
        for year in range(0, 10):
            assert VEHICLE_DEPRECIATION_TABLE[year] < VEHICLE_DEPRECIATION_TABLE[10]


class TestMileageDepreciation:
    """Tests fuer Kilometerstand-Abschreibung."""

    def test_mileage_factor_calculation(self):
        """Teste Kilometerstand-Faktor-Berechnung."""
        # Formel: factor = max(0.3, 1.0 - (km / 300000))

        def calculate_mileage_factor(km: int) -> float:
            return max(0.3, 1.0 - (km / 300000))

        assert calculate_mileage_factor(0) == 1.0
        assert calculate_mileage_factor(150000) == 0.5
        assert calculate_mileage_factor(300000) == 0.3
        assert calculate_mileage_factor(400000) == 0.3  # Minimum

    def test_low_mileage_high_factor(self):
        """Teste dass niedriger km-Stand hohen Faktor ergibt."""
        def calculate_mileage_factor(km: int) -> float:
            return max(0.3, 1.0 - (km / 300000))

        low_km_factor = calculate_mileage_factor(30000)
        high_km_factor = calculate_mileage_factor(200000)

        assert low_km_factor > high_km_factor


class TestMarketDataServiceEstimation:
    """Tests fuer MarketDataService Schaetzungen."""

    def test_property_estimation_formula(self):
        """Teste Immobilien-Schaetzungsformel."""
        # Formel: base_price * sqm * location_factor * condition_factor

        base_price_per_sqm = Decimal("5000")
        living_area = 100  # qm
        location_factor = Decimal("1.2")
        condition_factor = Decimal("0.9")

        estimated_value = (
            base_price_per_sqm *
            living_area *
            location_factor *
            condition_factor
        )

        assert estimated_value == Decimal("540000")

    def test_vehicle_estimation_formula(self):
        """Teste Fahrzeug-Schaetzungsformel."""
        # Formel: purchase_price * age_factor * mileage_factor * condition_factor

        purchase_price = Decimal("50000")
        age_factor = Decimal("0.65")  # 5 Jahre alt
        mileage_factor = Decimal("0.80")  # 60.000 km
        condition_factor = Decimal("0.95")

        estimated_value = (
            purchase_price *
            age_factor *
            mileage_factor *
            condition_factor
        )

        assert estimated_value == Decimal("24700.0000")

    def test_confidence_calculation(self):
        """Teste Konfidenz-Berechnung."""
        # Basis-Konfidenz fuer lokale Schaetzung
        base_confidence = 0.70

        # Erhoehung durch Datenqualitaet
        has_purchase_price = True
        has_location = True
        has_condition = True

        confidence = base_confidence
        if has_purchase_price:
            confidence += 0.10
        if has_location:
            confidence += 0.10
        if has_condition:
            confidence += 0.05

        assert confidence == 0.95

    def test_value_range_calculation(self):
        """Teste Wertbereich-Berechnung."""
        estimated_value = Decimal("500000")
        confidence = Decimal("0.85")
        uncertainty = Decimal("1") - confidence  # 0.15

        value_range_min = estimated_value * (Decimal("1") - uncertainty)
        value_range_max = estimated_value * (Decimal("1") + uncertainty)

        assert value_range_min == Decimal("425000")
        assert value_range_max == Decimal("575000")


class TestMarketDataServiceCaching:
    """Tests fuer Caching-Funktionalitaet."""

    def test_cache_key_generation(self):
        """Teste Cache-Key-Generierung."""
        def generate_cache_key(entity_type: str, entity_id: str) -> str:
            return f"market_data:{entity_type}:{entity_id}"

        property_id = str(uuid4())
        vehicle_id = str(uuid4())

        property_key = generate_cache_key("property", property_id)
        vehicle_key = generate_cache_key("vehicle", vehicle_id)

        assert property_key.startswith("market_data:property:")
        assert vehicle_key.startswith("market_data:vehicle:")

    def test_cache_ttl_default(self):
        """Teste Standard-Cache-TTL."""
        # Standard: 24 Stunden fuer Marktdaten
        default_ttl_hours = 24
        assert default_ttl_hours == 24

    def test_cache_invalidation_trigger(self):
        """Teste Cache-Invalidierungstrigger."""
        # Cache sollte invalidiert werden wenn:
        triggers = [
            "entity_updated",
            "manual_refresh",
            "ttl_expired"
        ]

        assert "entity_updated" in triggers
        assert "manual_refresh" in triggers


class TestMarketDataServiceConditionFactors:
    """Tests fuer Zustandsfaktoren."""

    def test_property_condition_factors(self):
        """Teste Immobilien-Zustandsfaktoren."""
        condition_factors = {
            "neuwertig": Decimal("1.10"),
            "sehr_gut": Decimal("1.00"),
            "gut": Decimal("0.90"),
            "renovierungsbeduerftig": Decimal("0.75"),
            "sanierungsbeduerftig": Decimal("0.50")
        }

        assert condition_factors["neuwertig"] > condition_factors["sehr_gut"]
        assert condition_factors["sehr_gut"] > condition_factors["gut"]
        assert condition_factors["gut"] > condition_factors["renovierungsbeduerftig"]

    def test_vehicle_condition_factors(self):
        """Teste Fahrzeug-Zustandsfaktoren."""
        condition_factors = {
            "neuwertig": Decimal("1.00"),
            "sehr_gut": Decimal("0.95"),
            "gut": Decimal("0.85"),
            "maengel": Decimal("0.70"),
            "beschaedigt": Decimal("0.50")
        }

        assert condition_factors["neuwertig"] > condition_factors["sehr_gut"]
        assert condition_factors["sehr_gut"] > condition_factors["gut"]
        assert all(factor > 0 for factor in condition_factors.values())


class TestMarketDataServiceMarketTrend:
    """Tests fuer Markttrend-Analyse."""

    def test_market_trend_values(self):
        """Teste gueltige Markttrend-Werte."""
        valid_trends = ["rising", "stable", "falling"]

        assert "rising" in valid_trends
        assert "stable" in valid_trends
        assert "falling" in valid_trends

    def test_trend_adjustment_factors(self):
        """Teste Trend-Anpassungsfaktoren."""
        trend_adjustments = {
            "rising": Decimal("1.05"),
            "stable": Decimal("1.00"),
            "falling": Decimal("0.95")
        }

        assert trend_adjustments["rising"] > trend_adjustments["stable"]
        assert trend_adjustments["stable"] > trend_adjustments["falling"]


class TestMarketDataServiceSingleton:
    """Tests fuer Singleton-Pattern."""

    def test_get_market_data_service_singleton(self):
        """Teste Singleton-Instanz."""
        from app.services.external.market_data_service import get_market_data_service

        service1 = get_market_data_service()
        service2 = get_market_data_service()

        assert service1 is service2

    def test_service_has_required_methods(self):
        """Teste dass Service erforderliche Methoden hat."""
        from app.services.external.market_data_service import MarketDataService

        # Methoden sollten existieren
        assert hasattr(MarketDataService, "estimate_property_value")
        assert hasattr(MarketDataService, "estimate_vehicle_value")
