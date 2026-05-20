# -*- coding: utf-8 -*-
"""
Unit Tests fuer SeasonalityDetectionService.

Testet:
- Singleton-Verhalten
- safe_stdev() Helper
- Enums (SeasonType, PatternStrength, CategoryType, AnomalyContext)
- Dataclasses (SeasonalPattern, MonthlyExpectation, SeasonalEvent, etc.)
- KNOWN_PATTERNS und KNOWN_EVENTS
- Pattern Detection
- Seasonal Expectations
- Anomaly Analysis
- Forecasts
- Custom Events
- Statistics

PHASE 0.7 CRITICAL FIX: 80%+ Coverage Ziel
"""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Dict, List
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

from app.services.orchestration.seasonality_detection_service import (
    SeasonalityDetectionService,
    SeasonalPattern,
    MonthlyExpectation,
    SeasonalEvent,
    SeasonalAnomalyAnalysis,
    SeasonalForecast,
    SeasonType,
    PatternStrength,
    CategoryType,
    AnomalyContext,
    KNOWN_PATTERNS,
    KNOWN_EVENTS,
    safe_stdev,
    get_seasonality_detection_service,
)


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def reset_service():
    """Reset Singleton vor und nach jedem Test."""
    SeasonalityDetectionService._instance = None
    yield
    SeasonalityDetectionService._instance = None


@pytest.fixture
def service(reset_service):
    """Frische Service-Instanz fuer jeden Test."""
    return SeasonalityDetectionService()


@pytest.fixture
def sample_user_id():
    """Erzeugt eine Beispiel-User-ID."""
    return uuid4()


@pytest.fixture
def sample_pattern():
    """Erstellt ein Beispiel-Pattern."""
    return SeasonalPattern(
        id=uuid4(),
        category=CategoryType.HEATING,
        season_type=SeasonType.ANNUAL,
        strength=PatternStrength.STRONG,
        peak_months=[1, 2, 11, 12],
        seasonal_factor=2.5,
        typical_min_factor=0.2,
        typical_max_factor=2.5,
        average_amount=Decimal("150"),
        std_deviation=Decimal("50"),
        confidence=0.85,
        description="Heizkosten steigen im Winter",
        data_points=24,
    )


@pytest.fixture
def sample_event():
    """Erstellt ein Beispiel-Event."""
    return SeasonalEvent(
        id=uuid4(),
        name="Geburtstag",
        description="Jaehrlicher Geburtstag",
        typical_month=5,
        typical_day=15,
        categories_affected=[CategoryType.GIFTS, CategoryType.FOOD],
        typical_impact=Decimal("200"),
        impact_range=(Decimal("100"), Decimal("400")),
    )


@pytest.fixture
def sample_historical_data():
    """Erstellt Beispiel-Transaktionsdaten mit saisonalem Muster."""
    data = []
    base_date = date(2024, 1, 1)

    # Heizkosten: hoch im Winter, niedrig im Sommer
    for month in range(1, 13):
        for year_offset in range(2):  # 2 Jahre Daten
            tx_date = date(2023 + year_offset, month, 15)

            # Winter-Monate haben hohe Heizkosten
            if month in [1, 2, 11, 12]:
                amount = 250 + (month % 3) * 20
            elif month in [6, 7, 8]:
                amount = 30
            else:
                amount = 100

            data.append({
                "date": tx_date,
                "category": "heating",
                "amount": amount,
            })

    return data


# =============================================================================
# Singleton Tests
# =============================================================================

class TestSingletonPattern:
    """Tests fuer Singleton-Verhalten."""

    def test_singleton_returns_same_instance(self, reset_service):
        """Singleton gibt immer dieselbe Instanz zurueck."""
        instance1 = SeasonalityDetectionService()
        instance2 = SeasonalityDetectionService()

        assert instance1 is instance2

    def test_factory_returns_same_instance(self, reset_service):
        """Factory-Funktion gibt Singleton zurueck."""
        instance1 = get_seasonality_detection_service()
        instance2 = get_seasonality_detection_service()

        assert instance1 is instance2

    def test_initialization_only_once(self, reset_service):
        """Initialisierung erfolgt nur einmal."""
        instance = SeasonalityDetectionService()
        original_patterns = instance._known_patterns

        instance2 = SeasonalityDetectionService()

        assert instance2._known_patterns is original_patterns


# =============================================================================
# safe_stdev Tests
# =============================================================================

class TestSafeStdev:
    """Tests fuer safe_stdev Helper-Funktion."""

    def test_returns_default_for_empty_list(self):
        """Leere Liste gibt Default zurueck."""
        result = safe_stdev([])
        assert result == 0.0

    def test_returns_default_for_single_element(self):
        """Einzelner Wert gibt Default zurueck."""
        result = safe_stdev([5.0])
        assert result == 0.0

    def test_custom_default_value(self):
        """Benutzerdefinierter Default wird verwendet."""
        result = safe_stdev([], default=99.0)
        assert result == 99.0

    def test_calculates_stdev_for_two_elements(self):
        """Standardabweichung fuer 2 Elemente wird berechnet."""
        result = safe_stdev([10.0, 20.0])
        assert result > 0

    def test_calculates_stdev_for_multiple_elements(self):
        """Standardabweichung fuer mehrere Elemente wird berechnet."""
        result = safe_stdev([1.0, 2.0, 3.0, 4.0, 5.0])
        assert result > 0
        assert result < 2.0  # Bekannte Stdev fuer diese Werte


# =============================================================================
# Enum Tests
# =============================================================================

class TestEnums:
    """Tests fuer Enums."""

    def test_season_type_values(self):
        """SeasonType hat erwartete Werte."""
        assert SeasonType.MONTHLY.value == "monthly"
        assert SeasonType.QUARTERLY.value == "quarterly"
        assert SeasonType.SEMI_ANNUAL.value == "semi_annual"
        assert SeasonType.ANNUAL.value == "annual"
        assert SeasonType.WEEKLY.value == "weekly"
        assert SeasonType.CUSTOM.value == "custom"

    def test_pattern_strength_values(self):
        """PatternStrength hat erwartete Werte."""
        assert PatternStrength.VERY_STRONG.value == "very_strong"
        assert PatternStrength.STRONG.value == "strong"
        assert PatternStrength.MODERATE.value == "moderate"
        assert PatternStrength.WEAK.value == "weak"
        assert PatternStrength.NONE.value == "none"

    def test_category_type_values(self):
        """CategoryType hat erwartete Werte."""
        assert CategoryType.HEATING.value == "heating"
        assert CategoryType.ELECTRICITY.value == "electricity"
        assert CategoryType.VACATION.value == "vacation"
        assert CategoryType.CHRISTMAS.value == "christmas"
        assert CategoryType.INSURANCE.value == "insurance"
        assert CategoryType.TAX.value == "tax"
        assert CategoryType.FOOD.value == "food"
        assert CategoryType.OTHER.value == "other"

    def test_anomaly_context_values(self):
        """AnomalyContext hat erwartete Werte."""
        assert AnomalyContext.EXPECTED_SEASONAL.value == "expected_seasonal"
        assert AnomalyContext.UNEXPECTED_SEASONAL.value == "unexpected_seasonal"
        assert AnomalyContext.EXPECTED_EVENT.value == "expected_event"
        assert AnomalyContext.TRUE_ANOMALY.value == "true_anomaly"


# =============================================================================
# Dataclass Tests
# =============================================================================

class TestSeasonalPattern:
    """Tests fuer SeasonalPattern Dataclass."""

    def test_defaults(self, sample_pattern):
        """SeasonalPattern hat sinnvolle Defaults."""
        pattern = SeasonalPattern(
            id=uuid4(),
            category=CategoryType.HEATING,
            season_type=SeasonType.ANNUAL,
            strength=PatternStrength.MODERATE,
            peak_months=[12],
        )

        assert pattern.seasonal_factor == 1.0
        assert pattern.typical_min_factor == 0.5
        assert pattern.typical_max_factor == 2.0
        assert pattern.confidence == 0.5
        assert pattern.data_points == 0

    def test_all_fields_set(self, sample_pattern):
        """Alle Felder sind korrekt gesetzt."""
        assert sample_pattern.category == CategoryType.HEATING
        assert sample_pattern.strength == PatternStrength.STRONG
        assert sample_pattern.peak_months == [1, 2, 11, 12]
        assert sample_pattern.seasonal_factor == 2.5


class TestMonthlyExpectation:
    """Tests fuer MonthlyExpectation Dataclass."""

    def test_all_fields(self):
        """Alle Felder sind vorhanden."""
        exp = MonthlyExpectation(
            month=12,
            year=2024,
            category=CategoryType.CHRISTMAS,
            expected_amount=Decimal("500"),
            expected_range_min=Decimal("300"),
            expected_range_max=Decimal("800"),
            seasonal_factor=4.0,
            is_peak_season=True,
            expected_events=["Weihnachten"],
            confidence=0.85,
        )

        assert exp.month == 12
        assert exp.is_peak_season is True
        assert "Weihnachten" in exp.expected_events


class TestSeasonalEvent:
    """Tests fuer SeasonalEvent Dataclass."""

    def test_defaults(self):
        """SeasonalEvent hat sinnvolle Defaults."""
        event = SeasonalEvent(
            id=uuid4(),
            name="Test Event",
            description="Beschreibung",
            typical_month=5,
        )

        assert event.flexible_date is True
        assert event.categories_affected == []
        assert event.is_recurring is True

    def test_all_fields_set(self, sample_event):
        """Alle Felder sind korrekt gesetzt."""
        assert sample_event.name == "Geburtstag"
        assert sample_event.typical_month == 5
        assert sample_event.typical_day == 15
        assert CategoryType.GIFTS in sample_event.categories_affected


class TestSeasonalAnomalyAnalysis:
    """Tests fuer SeasonalAnomalyAnalysis Dataclass."""

    def test_all_fields(self):
        """Alle Felder sind vorhanden."""
        analysis = SeasonalAnomalyAnalysis(
            id=uuid4(),
            transaction_date=date(2024, 12, 15),
            category=CategoryType.CHRISTMAS,
            amount=Decimal("800"),
            context=AnomalyContext.EXPECTED_SEASONAL,
            seasonal_pattern=None,
            expected_amount=Decimal("500"),
            expected_range=(Decimal("300"), Decimal("700")),
            deviation_percentage=60.0,
            is_true_anomaly=False,
            confidence=0.85,
            explanation="Im erwarteten Bereich fuer Weihnachten",
            similar_historical=[],
        )

        assert analysis.context == AnomalyContext.EXPECTED_SEASONAL
        assert analysis.is_true_anomaly is False


class TestSeasonalForecast:
    """Tests fuer SeasonalForecast Dataclass."""

    def test_all_fields(self):
        """Alle Felder sind vorhanden."""
        forecast = SeasonalForecast(
            id=uuid4(),
            forecast_date=date.today(),
            horizon_months=12,
            monthly_forecasts={},
            total_expected=Decimal("12000"),
            total_range=(Decimal("10000"), Decimal("14000")),
            high_expense_months=[11, 12],
            peak_categories={12: [CategoryType.CHRISTMAS]},
            overall_confidence=0.7,
        )

        assert forecast.horizon_months == 12
        assert 12 in forecast.high_expense_months


# =============================================================================
# Known Patterns and Events Tests
# =============================================================================

class TestKnownPatterns:
    """Tests fuer KNOWN_PATTERNS."""

    def test_patterns_defined(self):
        """Bekannte Muster sind definiert."""
        assert len(KNOWN_PATTERNS) >= 8

    def test_heating_pattern(self):
        """Heizkosten-Muster ist korrekt definiert."""
        heating = KNOWN_PATTERNS.get(CategoryType.HEATING)

        assert heating is not None
        assert 12 in heating["peak_months"]
        assert 1 in heating["peak_months"]
        assert heating["peak_factor"] > 1.0

    def test_christmas_pattern(self):
        """Weihnachts-Muster ist korrekt definiert."""
        christmas = KNOWN_PATTERNS.get(CategoryType.CHRISTMAS)

        assert christmas is not None
        assert 12 in christmas["peak_months"]
        assert christmas["peak_factor"] >= 4.0

    def test_vacation_pattern(self):
        """Urlaubs-Muster ist korrekt definiert."""
        vacation = KNOWN_PATTERNS.get(CategoryType.VACATION)

        assert vacation is not None
        assert 7 in vacation["peak_months"]
        assert 8 in vacation["peak_months"]


class TestKnownEvents:
    """Tests fuer KNOWN_EVENTS."""

    def test_events_defined(self):
        """Bekannte Events sind definiert."""
        assert len(KNOWN_EVENTS) >= 5

    def test_christmas_event_exists(self):
        """Weihnachten-Event existiert."""
        christmas_events = [e for e in KNOWN_EVENTS if e.name == "Weihnachten"]

        assert len(christmas_events) == 1
        assert christmas_events[0].typical_month == 12

    def test_sommerurlaub_event_exists(self):
        """Sommerurlaub-Event existiert."""
        vacation_events = [e for e in KNOWN_EVENTS if e.name == "Sommerurlaub"]

        assert len(vacation_events) == 1
        assert vacation_events[0].typical_month == 7


# =============================================================================
# Pattern Detection Tests
# =============================================================================

class TestPatternDetection:
    """Tests fuer Pattern-Erkennung."""

    @pytest.mark.asyncio
    async def test_detect_patterns_with_seasonal_data(
        self, service, sample_user_id, sample_historical_data
    ):
        """Saisonale Muster werden erkannt."""
        patterns = await service.detect_patterns(
            user_id=sample_user_id,
            historical_data=sample_historical_data,
            min_data_points=12,
        )

        assert len(patterns) > 0
        heating_patterns = [p for p in patterns if p.category == CategoryType.HEATING]
        assert len(heating_patterns) > 0

    @pytest.mark.asyncio
    async def test_detect_patterns_stores_user_patterns(
        self, service, sample_user_id, sample_historical_data
    ):
        """Erkannte Muster werden gespeichert."""
        await service.detect_patterns(
            user_id=sample_user_id,
            historical_data=sample_historical_data,
        )

        assert sample_user_id in service._user_patterns
        assert len(service._user_patterns[sample_user_id]) > 0

    @pytest.mark.asyncio
    async def test_detect_patterns_skips_insufficient_data(
        self, service, sample_user_id
    ):
        """Kategorien mit wenig Daten werden uebersprungen."""
        sparse_data = [
            {"date": date(2024, 1, 15), "category": "heating", "amount": 100},
            {"date": date(2024, 2, 15), "category": "heating", "amount": 150},
        ]

        patterns = await service.detect_patterns(
            user_id=sample_user_id,
            historical_data=sparse_data,
            min_data_points=12,
        )

        # Sollte leer sein wegen zu wenig Daten
        heating_patterns = [p for p in patterns if p.category == CategoryType.HEATING]
        assert len(heating_patterns) == 0

    @pytest.mark.asyncio
    async def test_detect_patterns_identifies_peak_months(
        self, service, sample_user_id, sample_historical_data
    ):
        """Peak-Monate werden identifiziert."""
        patterns = await service.detect_patterns(
            user_id=sample_user_id,
            historical_data=sample_historical_data,
        )

        heating = next((p for p in patterns if p.category == CategoryType.HEATING), None)
        if heating:
            # Winter-Monate sollten Peak sein
            assert any(m in heating.peak_months for m in [1, 2, 11, 12])

    @pytest.mark.asyncio
    async def test_detect_patterns_calculates_strength(
        self, service, sample_user_id, sample_historical_data
    ):
        """Pattern-Staerke wird berechnet."""
        patterns = await service.detect_patterns(
            user_id=sample_user_id,
            historical_data=sample_historical_data,
        )

        if patterns:
            # Heizkosten sollten starkes Muster haben
            heating = next((p for p in patterns if p.category == CategoryType.HEATING), None)
            if heating:
                assert heating.strength in [
                    PatternStrength.STRONG,
                    PatternStrength.VERY_STRONG,
                    PatternStrength.MODERATE,
                ]

    @pytest.mark.asyncio
    async def test_detect_patterns_unknown_category_maps_to_other(
        self, service, sample_user_id
    ):
        """Unbekannte Kategorien werden zu OTHER gemappt."""
        # Verwende variierende Betraege um ein erkennbares Muster zu erzeugen
        # Hohe Betraege im Winter (Monate 1, 2, 11, 12), niedrig im Sommer
        winter_months = {1, 2, 11, 12}
        data = []
        for year in [2023, 2024]:
            for m in range(1, 13):
                amount = 200 if m in winter_months else 50
                data.append({
                    "date": date(year, m, 15),
                    "category": "unknown_category",
                    "amount": amount
                })

        patterns = await service.detect_patterns(
            user_id=sample_user_id,
            historical_data=data,
            min_data_points=12,
        )

        other_patterns = [p for p in patterns if p.category == CategoryType.OTHER]
        assert len(other_patterns) > 0


# =============================================================================
# Monthly Expectations Tests
# =============================================================================

class TestMonthlyExpectations:
    """Tests fuer monatliche Erwartungen."""

    @pytest.mark.asyncio
    async def test_get_monthly_expectations_with_user_patterns(
        self, service, sample_user_id, sample_historical_data
    ):
        """Monatliche Erwartungen basierend auf User-Patterns."""
        # Erst Patterns lernen
        await service.detect_patterns(
            user_id=sample_user_id,
            historical_data=sample_historical_data,
        )

        expectations = await service.get_monthly_expectations(
            user_id=sample_user_id,
            month=12,
            year=2024,
            categories=[CategoryType.HEATING],
        )

        assert len(expectations) > 0
        heating_exp = next((e for e in expectations if e.category == CategoryType.HEATING), None)
        if heating_exp:
            assert heating_exp.is_peak_season is True

    @pytest.mark.asyncio
    async def test_get_monthly_expectations_uses_known_patterns(
        self, service, sample_user_id
    ):
        """Bekannte Patterns werden verwendet wenn keine User-Daten."""
        expectations = await service.get_monthly_expectations(
            user_id=sample_user_id,
            month=12,
            year=2024,
            categories=[CategoryType.CHRISTMAS],
        )

        christmas_exp = next(
            (e for e in expectations if e.category == CategoryType.CHRISTMAS), None
        )
        # Christmas ist in December Peak
        if christmas_exp:
            assert christmas_exp.is_peak_season is True

    @pytest.mark.asyncio
    async def test_get_monthly_expectations_includes_events(
        self, service, sample_user_id
    ):
        """Events werden in Erwartungen einbezogen."""
        expectations = await service.get_monthly_expectations(
            user_id=sample_user_id,
            month=12,
            year=2024,
        )

        # Weihnachten sollte als Event erscheinen
        christmas_exp = next(
            (e for e in expectations if e.category == CategoryType.CHRISTMAS), None
        )
        if christmas_exp:
            assert "Weihnachten" in christmas_exp.expected_events


# =============================================================================
# Anomaly Analysis Tests
# =============================================================================

class TestAnomalyAnalysis:
    """Tests fuer Anomalie-Analyse mit saisonalem Kontext."""

    @pytest.mark.asyncio
    async def test_analyze_anomaly_expected_seasonal(
        self, service, sample_user_id, sample_historical_data
    ):
        """Saisonal erwartete Ausgaben werden nicht als Anomalie erkannt."""
        await service.detect_patterns(
            user_id=sample_user_id,
            historical_data=sample_historical_data,
        )

        # Hohe Heizkosten im Dezember
        analysis = await service.analyze_anomaly(
            user_id=sample_user_id,
            transaction_date=date(2024, 12, 15),
            category=CategoryType.HEATING,
            amount=Decimal("300"),
        )

        assert analysis.context == AnomalyContext.EXPECTED_SEASONAL
        assert analysis.is_true_anomaly is False

    @pytest.mark.asyncio
    async def test_analyze_anomaly_true_anomaly(
        self, service, sample_user_id, sample_historical_data
    ):
        """Echte Anomalien werden erkannt."""
        await service.detect_patterns(
            user_id=sample_user_id,
            historical_data=sample_historical_data,
        )

        # Sehr hohe Heizkosten im Sommer (Juli)
        analysis = await service.analyze_anomaly(
            user_id=sample_user_id,
            transaction_date=date(2024, 7, 15),
            category=CategoryType.HEATING,
            amount=Decimal("500"),  # Sehr hoch fuer Sommer
            historical_avg=Decimal("100"),
        )

        # Im Sommer sollten hohe Heizkosten ungewoehnlich sein
        assert analysis.is_true_anomaly is True or analysis.context == AnomalyContext.UNEXPECTED_SEASONAL

    @pytest.mark.asyncio
    async def test_analyze_anomaly_expected_event(
        self, service, sample_user_id
    ):
        """Event-basierte Ausgaben werden erkannt."""
        # Hohe Geschenkausgaben im Dezember (Weihnachten)
        analysis = await service.analyze_anomaly(
            user_id=sample_user_id,
            transaction_date=date(2024, 12, 20),
            category=CategoryType.GIFTS,
            amount=Decimal("500"),
            historical_avg=Decimal("50"),
        )

        # Sollte wegen Weihnachten als erwartet gelten
        assert analysis.context in [
            AnomalyContext.EXPECTED_EVENT,
            AnomalyContext.EXPECTED_SEASONAL,
        ] or "Weihnachten" in analysis.explanation

    @pytest.mark.asyncio
    async def test_analyze_anomaly_includes_explanation(
        self, service, sample_user_id
    ):
        """Analyse enthaelt Erklaerung."""
        analysis = await service.analyze_anomaly(
            user_id=sample_user_id,
            transaction_date=date(2024, 6, 15),
            category=CategoryType.FOOD,
            amount=Decimal("200"),
            historical_avg=Decimal("100"),
        )

        assert analysis.explanation != ""
        assert len(analysis.explanation) > 10

    @pytest.mark.asyncio
    async def test_analyze_anomaly_deviation_calculated(
        self, service, sample_user_id
    ):
        """Abweichung wird berechnet."""
        analysis = await service.analyze_anomaly(
            user_id=sample_user_id,
            transaction_date=date(2024, 3, 15),
            category=CategoryType.TAX,
            amount=Decimal("300"),
            historical_avg=Decimal("100"),
        )

        # 300 vs 100 = 200% Abweichung
        assert analysis.deviation_percentage > 0


# =============================================================================
# Forecast Tests
# =============================================================================

class TestForecasts:
    """Tests fuer saisonale Prognosen."""

    @pytest.mark.asyncio
    async def test_generate_forecast(self, service, sample_user_id):
        """Prognose wird generiert."""
        forecast = await service.generate_forecast(
            user_id=sample_user_id,
            horizon_months=12,
        )

        assert forecast is not None
        assert forecast.horizon_months == 12
        assert forecast.total_expected >= Decimal("0")

    @pytest.mark.asyncio
    async def test_generate_forecast_identifies_high_expense_months(
        self, service, sample_user_id, sample_historical_data
    ):
        """Monate mit hohen Ausgaben werden identifiziert."""
        await service.detect_patterns(
            user_id=sample_user_id,
            historical_data=sample_historical_data,
        )

        forecast = await service.generate_forecast(
            user_id=sample_user_id,
            horizon_months=12,
        )

        # high_expense_months sollte existieren
        assert isinstance(forecast.high_expense_months, list)

    @pytest.mark.asyncio
    async def test_generate_forecast_includes_peak_categories(
        self, service, sample_user_id
    ):
        """Peak-Kategorien werden pro Monat identifiziert."""
        forecast = await service.generate_forecast(
            user_id=sample_user_id,
            horizon_months=12,
        )

        assert isinstance(forecast.peak_categories, dict)

    @pytest.mark.asyncio
    async def test_generate_forecast_has_range(
        self, service, sample_user_id
    ):
        """Prognose hat Gesamt-Range."""
        forecast = await service.generate_forecast(
            user_id=sample_user_id,
            horizon_months=6,
        )

        assert forecast.total_range[0] <= forecast.total_expected
        assert forecast.total_range[1] >= forecast.total_expected


# =============================================================================
# Custom Events Tests
# =============================================================================

class TestCustomEvents:
    """Tests fuer benutzerdefinierte Events."""

    @pytest.mark.asyncio
    async def test_add_custom_event(self, service, sample_user_id):
        """Benutzerdefiniertes Event wird hinzugefuegt."""
        event = await service.add_custom_event(
            user_id=sample_user_id,
            name="Hochzeitstag",
            month=6,
            categories=[CategoryType.GIFTS, CategoryType.ENTERTAINMENT],
            typical_impact=Decimal("300"),
            description="Jaehrlicher Hochzeitstag",
        )

        assert event is not None
        assert event.name == "Hochzeitstag"
        assert event.typical_month == 6
        assert CategoryType.GIFTS in event.categories_affected

    @pytest.mark.asyncio
    async def test_add_custom_event_stored(self, service, sample_user_id):
        """Benutzerdefinierte Events werden gespeichert."""
        await service.add_custom_event(
            user_id=sample_user_id,
            name="Geburtstag Kind",
            month=3,
            categories=[CategoryType.GIFTS],
            typical_impact=Decimal("100"),
        )

        assert sample_user_id in service._user_events
        assert len(service._user_events[sample_user_id]) > 0

    @pytest.mark.asyncio
    async def test_get_events_for_month_includes_known(self, service, sample_user_id):
        """get_events_for_month enthaelt bekannte Events."""
        events = await service.get_events_for_month(
            user_id=sample_user_id,
            month=12,
        )

        # Weihnachten sollte dabei sein
        event_names = [e.name for e in events]
        assert "Weihnachten" in event_names

    @pytest.mark.asyncio
    async def test_get_events_for_month_includes_custom(self, service, sample_user_id):
        """get_events_for_month enthaelt benutzerdefinierte Events."""
        await service.add_custom_event(
            user_id=sample_user_id,
            name="Firmenjubilaeum",
            month=9,
            categories=[CategoryType.ENTERTAINMENT],
            typical_impact=Decimal("200"),
        )

        events = await service.get_events_for_month(
            user_id=sample_user_id,
            month=9,
        )

        event_names = [e.name for e in events]
        assert "Firmenjubilaeum" in event_names


# =============================================================================
# Statistics Tests
# =============================================================================

class TestStatistics:
    """Tests fuer Statistiken."""

    @pytest.mark.asyncio
    async def test_get_seasonality_statistics(
        self, service, sample_user_id, sample_historical_data
    ):
        """Statistiken werden berechnet."""
        await service.detect_patterns(
            user_id=sample_user_id,
            historical_data=sample_historical_data,
        )

        stats = await service.get_seasonality_statistics(sample_user_id)

        assert "detected_patterns" in stats
        assert "strong_patterns" in stats
        assert "known_events" in stats
        assert "custom_events" in stats
        assert "average_confidence" in stats

    @pytest.mark.asyncio
    async def test_get_seasonality_statistics_empty_user(self, service):
        """Statistiken fuer unbekannten User sind leer."""
        stats = await service.get_seasonality_statistics(uuid4())

        assert stats["detected_patterns"] == 0
        assert stats["custom_events"] == 0

    @pytest.mark.asyncio
    async def test_statistics_includes_peak_months(
        self, service, sample_user_id, sample_historical_data
    ):
        """Statistiken enthalten identifizierte Peak-Monate."""
        await service.detect_patterns(
            user_id=sample_user_id,
            historical_data=sample_historical_data,
        )

        stats = await service.get_seasonality_statistics(sample_user_id)

        assert "peak_months_identified" in stats
        assert isinstance(stats["peak_months_identified"], list)


# =============================================================================
# Helper Method Tests
# =============================================================================

class TestHelperMethods:
    """Tests fuer Helper-Methoden."""

    def test_month_name_returns_german(self, service):
        """_month_name gibt deutschen Monatsnamen zurueck."""
        assert service._month_name(1) == "Januar"
        assert service._month_name(6) == "Juni"
        assert service._month_name(12) == "Dezember"

    def test_month_name_invalid_returns_string(self, service):
        """Ungueltiger Monat gibt String-Repraesentation zurueck."""
        result = service._month_name(13)
        assert result == "13"

    def test_month_name_all_months(self, service):
        """Alle Monate haben Namen."""
        for month in range(1, 13):
            name = service._month_name(month)
            assert name != str(month)
            assert len(name) > 2


# =============================================================================
# Edge Cases Tests
# =============================================================================

class TestEdgeCases:
    """Tests fuer Randfaelle."""

    @pytest.mark.asyncio
    async def test_empty_historical_data(self, service, sample_user_id):
        """Leere historische Daten verursachen keinen Fehler."""
        patterns = await service.detect_patterns(
            user_id=sample_user_id,
            historical_data=[],
        )

        assert patterns == []

    @pytest.mark.asyncio
    async def test_zero_amount_transactions(self, service, sample_user_id):
        """Transaktionen mit Betrag 0 werden verarbeitet."""
        data = [
            {"date": date(2024, m, 15), "category": "other", "amount": 0}
            for m in range(1, 13)
        ] * 2

        patterns = await service.detect_patterns(
            user_id=sample_user_id,
            historical_data=data,
            min_data_points=12,
        )

        # Sollte keine Patterns erkennen (alle Werte 0)
        assert all(p.strength == PatternStrength.NONE for p in patterns if p.category == CategoryType.OTHER)

    @pytest.mark.asyncio
    async def test_string_date_parsing(self, service, sample_user_id):
        """String-Datumsangaben werden korrekt geparst."""
        data = [
            {"date": "2024-01-15", "category": "heating", "amount": 200},
            {"date": "2024-02-15", "category": "heating", "amount": 250},
        ] * 10

        patterns = await service.detect_patterns(
            user_id=sample_user_id,
            historical_data=data,
            min_data_points=12,
        )

        # Sollte funktionieren ohne Fehler
        assert isinstance(patterns, list)

    @pytest.mark.asyncio
    async def test_datetime_object_handling(self, service, sample_user_id):
        """Datetime-Objekte werden korrekt verarbeitet."""
        data = [
            {
                "date": datetime(2024, m, 15, 12, 0, 0),
                "category": "food",
                "amount": 100 + m * 10
            }
            for m in range(1, 13)
        ] * 2

        patterns = await service.detect_patterns(
            user_id=sample_user_id,
            historical_data=data,
            min_data_points=12,
        )

        assert isinstance(patterns, list)
