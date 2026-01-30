# -*- coding: utf-8 -*-
"""Unit tests for IndustryBenchmarkService.

Tests:
- Branchendaten
- Metrik-Berechnung
- Perzentil-Berechnung
- Performance-Level
"""

import pytest
import uuid
from datetime import datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.analytics.industry_benchmark_service import (
    IndustryBenchmarkService,
    Industry,
    MetricType,
    PerformanceLevel,
    BenchmarkMetric,
    IndustryBenchmarkData,
    INDUSTRY_BENCHMARKS,
    INDUSTRY_LABELS,
    get_benchmark_service,
)


class TestIndustryBenchmarkService:
    """Tests fuer IndustryBenchmarkService."""

    @pytest.fixture
    def mock_db(self):
        """Mock Database Session."""
        return AsyncMock()

    @pytest.fixture
    def service(self, mock_db):
        """Service-Instanz."""
        return IndustryBenchmarkService(mock_db)

    @pytest.fixture
    def sample_company_id(self):
        """Beispiel Company-ID."""
        return uuid.uuid4()

    # ========================================================================
    # INDUSTRY BENCHMARKS DATA TESTS
    # ========================================================================

    def test_all_industries_have_benchmarks(self):
        """Alle Branchen sollten Benchmark-Daten haben."""
        for industry in Industry:
            assert industry in INDUSTRY_BENCHMARKS, f"Fehlende Benchmarks fuer {industry}"

    def test_all_industries_have_labels(self):
        """Alle Branchen sollten deutsche Labels haben."""
        for industry in Industry:
            assert industry in INDUSTRY_LABELS, f"Fehlender Label fuer {industry}"
            assert len(INDUSTRY_LABELS[industry]) > 0

    def test_benchmark_data_valid_ranges(self):
        """Benchmark-Werte sollten in sinnvollen Bereichen liegen."""
        for industry, data in INDUSTRY_BENCHMARKS.items():
            # DSO: 0-120 Tage
            assert 0 < data.dso_average < 120, f"DSO fuer {industry} ausserhalb Bereich"
            assert 0 < data.dso_median < 120

            # Raten: 0-1
            assert 0 <= data.punctuality_rate_avg <= 1
            assert 0 <= data.skonto_usage_avg <= 1
            assert 0 <= data.dunning_rate_avg <= 1
            assert 0 <= data.default_rate_avg <= 1

            # Stichprobengroesse: positiv
            assert data.sample_size > 0

    def test_benchmark_data_has_timestamp(self):
        """Benchmark-Daten sollten Timestamp haben."""
        for industry, data in INDUSTRY_BENCHMARKS.items():
            assert data.last_updated is not None
            assert isinstance(data.last_updated, datetime)

    # ========================================================================
    # GET INDUSTRY BENCHMARKS TESTS
    # ========================================================================

    @pytest.mark.asyncio
    async def test_get_industry_benchmarks_manufacturing(self, service):
        """Holen von Fertigungs-Benchmarks."""
        data = await service.get_industry_benchmarks(Industry.MANUFACTURING)

        assert data.industry == Industry.MANUFACTURING
        assert data.dso_average == 45.0
        assert data.punctuality_rate_avg == 0.72

    @pytest.mark.asyncio
    async def test_get_industry_benchmarks_retail(self, service):
        """Holen von Einzelhandel-Benchmarks."""
        data = await service.get_industry_benchmarks(Industry.RETAIL)

        assert data.industry == Industry.RETAIL
        assert data.dso_average == 28.0
        # Retail hat typischerweise bessere Werte
        assert data.punctuality_rate_avg > 0.7

    @pytest.mark.asyncio
    async def test_get_available_industries(self, service):
        """Liste aller Branchen."""
        industries = await service.get_available_industries()

        assert len(industries) == len(Industry)

        # Jede Branche sollte value und label haben
        for ind in industries:
            assert "value" in ind
            assert "label" in ind
            assert len(ind["label"]) > 0

    # ========================================================================
    # METRIC CREATION TESTS
    # ========================================================================

    def test_create_metric_better_lower(self, service):
        """Metrik-Erstellung: niedriger ist besser (z.B. DSO)."""
        metric = service._create_metric(
            metric_type=MetricType.DSO,
            label="DSO",
            company_value=30.0,  # Besser als Durchschnitt
            industry_average=45.0,
            industry_median=42.0,
            is_better_higher=False,
            unit="Tage",
        )

        assert metric.company_value == 30.0
        assert metric.industry_average == 45.0
        assert metric.percentile > 50  # Besser als Durchschnitt = hoeheres Perzentil
        assert metric.trend_vs_avg < 0  # Unter Durchschnitt (bei niedriger=besser)

    def test_create_metric_better_higher(self, service):
        """Metrik-Erstellung: hoeher ist besser (z.B. Puenktlichkeit)."""
        metric = service._create_metric(
            metric_type=MetricType.PUNCTUALITY,
            label="Puenktlichkeit",
            company_value=85.0,  # Besser als Durchschnitt
            industry_average=72.0,
            industry_median=70.0,
            is_better_higher=True,
            unit="%",
        )

        assert metric.company_value == 85.0
        assert metric.percentile > 50  # Besser als Durchschnitt
        assert metric.trend_vs_avg > 0  # Ueber Durchschnitt

    def test_create_metric_performance_level(self, service):
        """Performance-Level Zuweisung."""
        # Exzellent (weit besser als Durchschnitt)
        excellent_metric = service._create_metric(
            metric_type=MetricType.DSO,
            label="DSO",
            company_value=20.0,
            industry_average=45.0,
            industry_median=42.0,
            is_better_higher=False,
            unit="Tage",
        )

        assert excellent_metric.performance_level in [
            PerformanceLevel.EXCELLENT,
            PerformanceLevel.GOOD,
        ]

        # Schlecht (weit schlechter als Durchschnitt)
        poor_metric = service._create_metric(
            metric_type=MetricType.DSO,
            label="DSO",
            company_value=80.0,
            industry_average=45.0,
            industry_median=42.0,
            is_better_higher=False,
            unit="Tage",
        )

        assert poor_metric.performance_level in [
            PerformanceLevel.BELOW_AVERAGE,
            PerformanceLevel.POOR,
        ]

    # ========================================================================
    # PERCENTILE CALCULATION TESTS
    # ========================================================================

    def test_percentile_to_level_excellent(self, service):
        """Perzentil 90+ = Excellent."""
        assert service._percentile_to_level(95) == PerformanceLevel.EXCELLENT
        assert service._percentile_to_level(90) == PerformanceLevel.EXCELLENT

    def test_percentile_to_level_good(self, service):
        """Perzentil 75-89 = Good."""
        assert service._percentile_to_level(85) == PerformanceLevel.GOOD
        assert service._percentile_to_level(75) == PerformanceLevel.GOOD

    def test_percentile_to_level_average(self, service):
        """Perzentil 25-74 = Average."""
        assert service._percentile_to_level(50) == PerformanceLevel.AVERAGE
        assert service._percentile_to_level(25) == PerformanceLevel.AVERAGE

    def test_percentile_to_level_below_average(self, service):
        """Perzentil 10-24 = Below Average."""
        assert service._percentile_to_level(20) == PerformanceLevel.BELOW_AVERAGE
        assert service._percentile_to_level(10) == PerformanceLevel.BELOW_AVERAGE

    def test_percentile_to_level_poor(self, service):
        """Perzentil <10 = Poor."""
        assert service._percentile_to_level(5) == PerformanceLevel.POOR
        assert service._percentile_to_level(1) == PerformanceLevel.POOR

    # ========================================================================
    # OVERALL SCORE CALCULATION TESTS
    # ========================================================================

    def test_calculate_overall_score_empty(self, service):
        """Leere Metriken-Liste."""
        score, percentile = service._calculate_overall_score([])

        assert score == 50.0
        assert percentile == 50

    def test_calculate_overall_score_weighted(self, service):
        """Gewichtete Gesamt-Score Berechnung."""
        metrics = [
            BenchmarkMetric(
                metric_type=MetricType.DSO,
                label="DSO",
                company_value=30.0,
                industry_average=45.0,
                industry_median=42.0,
                percentile=80,
                performance_level=PerformanceLevel.GOOD,
                trend_vs_avg=-33.0,
                is_better_higher=False,
                unit="Tage",
            ),
            BenchmarkMetric(
                metric_type=MetricType.PUNCTUALITY,
                label="Puenktlichkeit",
                company_value=85.0,
                industry_average=72.0,
                industry_median=70.0,
                percentile=75,
                performance_level=PerformanceLevel.GOOD,
                trend_vs_avg=18.0,
                is_better_higher=True,
                unit="%",
            ),
        ]

        score, percentile = service._calculate_overall_score(metrics)

        # Score sollte zwischen den beiden Perzentilen liegen
        assert 70 <= percentile <= 85
        assert score == percentile  # In dieser Implementierung identisch

    # ========================================================================
    # RECOMMENDATIONS TESTS
    # ========================================================================

    def test_get_metric_recommendations_dso_poor(self, service):
        """DSO-Empfehlungen bei schlechter Performance."""
        recs = service._get_metric_recommendations(
            metric_type=MetricType.DSO,
            company_value=70.0,
            industry_average=45.0,
            is_better_higher=False,
            level=PerformanceLevel.POOR,
        )

        assert len(recs) > 0
        # Sollte konkrete Handlungsempfehlungen enthalten
        assert any("Zahlungsziele" in r for r in recs)

    def test_get_metric_recommendations_punctuality_poor(self, service):
        """Puenktlichkeits-Empfehlungen bei schlechter Performance."""
        recs = service._get_metric_recommendations(
            metric_type=MetricType.PUNCTUALITY,
            company_value=50.0,
            industry_average=72.0,
            is_better_higher=True,
            level=PerformanceLevel.POOR,
        )

        assert len(recs) > 0

    def test_get_metric_recommendations_good_performance(self, service):
        """Keine Empfehlungen bei guter Performance."""
        recs = service._get_metric_recommendations(
            metric_type=MetricType.DSO,
            company_value=30.0,
            industry_average=45.0,
            is_better_higher=False,
            level=PerformanceLevel.GOOD,
        )

        # Bei guter Performance keine Empfehlungen
        assert len(recs) == 0

    def test_generate_recommendations_excellent(self, service):
        """Gesamt-Empfehlungen bei hervorragender Performance."""
        metrics = [
            BenchmarkMetric(
                metric_type=MetricType.DSO,
                label="DSO",
                company_value=20.0,
                industry_average=45.0,
                industry_median=42.0,
                percentile=95,
                performance_level=PerformanceLevel.EXCELLENT,
                trend_vs_avg=-55.0,
                is_better_higher=False,
                unit="Tage",
            ),
        ]

        recs = service._generate_recommendations(metrics, PerformanceLevel.EXCELLENT)

        assert len(recs) > 0
        assert any("Spitzenbereich" in r for r in recs)

    def test_generate_recommendations_poor(self, service):
        """Gesamt-Empfehlungen bei schlechter Performance."""
        metrics = [
            BenchmarkMetric(
                metric_type=MetricType.DSO,
                label="DSO",
                company_value=80.0,
                industry_average=45.0,
                industry_median=42.0,
                percentile=10,
                performance_level=PerformanceLevel.POOR,
                trend_vs_avg=78.0,
                is_better_higher=False,
                unit="Tage",
                recommendations=["Verkuerzen Sie Zahlungsziele"],
            ),
        ]

        recs = service._generate_recommendations(metrics, PerformanceLevel.POOR)

        assert len(recs) > 0
        assert any("Verbesserungspotenzial" in r for r in recs)

    # ========================================================================
    # FACTORY FUNCTION TEST
    # ========================================================================

    @pytest.mark.asyncio
    async def test_get_benchmark_service(self, mock_db):
        """Factory-Funktion sollte Service erstellen."""
        service = await get_benchmark_service(mock_db)

        assert isinstance(service, IndustryBenchmarkService)


class TestIndustryEnum:
    """Tests fuer Industry Enum."""

    def test_industry_values(self):
        """Industry-Werte sollten gueltige Strings sein."""
        for industry in Industry:
            assert isinstance(industry.value, str)
            assert len(industry.value) > 0
            # Sollte lowercase sein
            assert industry.value == industry.value.lower()

    def test_industry_from_string(self):
        """Industry aus String erstellen."""
        assert Industry("manufacturing") == Industry.MANUFACTURING
        assert Industry("retail") == Industry.RETAIL
        assert Industry("other") == Industry.OTHER

    def test_industry_from_invalid_string(self):
        """Ungueltige Industry-Strings."""
        with pytest.raises(ValueError):
            Industry("invalid_industry")


class TestMetricType:
    """Tests fuer MetricType Enum."""

    def test_all_metric_types(self):
        """Alle Metrik-Typen sollten vorhanden sein."""
        expected_types = ["dso", "punctuality", "skonto_usage", "dunning_rate", "default_rate", "avg_payment_delay"]

        for expected in expected_types:
            assert expected in [m.value for m in MetricType]

    def test_metric_type_count(self):
        """Anzahl der Metrik-Typen."""
        assert len(MetricType) == 6


class TestPerformanceLevel:
    """Tests fuer PerformanceLevel Enum."""

    def test_all_levels(self):
        """Alle Performance-Level sollten vorhanden sein."""
        expected = ["excellent", "good", "average", "below_average", "poor"]

        for exp in expected:
            assert exp in [l.value for l in PerformanceLevel]

    def test_level_ordering(self):
        """Performance-Level sollten logisch geordnet sein."""
        levels = list(PerformanceLevel)
        assert levels[0] == PerformanceLevel.EXCELLENT
        assert levels[-1] == PerformanceLevel.POOR
