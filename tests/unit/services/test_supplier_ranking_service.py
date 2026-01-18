# -*- coding: utf-8 -*-
"""Unit tests for Supplier Ranking Service.

Tests:
- Ranking categories and tiers
- Score calculation
- Category score computation
- Trend detection
- Report generation (mocked dependencies)
"""

from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.supplier_ranking_service import (
    SupplierRankingService,
    SupplierRankingCategory,
    SupplierTier,
    SupplierScore,
    SupplierRanking,
    SupplierRankingReport,
    get_supplier_ranking_service,
)


@pytest.fixture
def ranking_service() -> SupplierRankingService:
    """Create SupplierRankingService instance."""
    return SupplierRankingService()


@pytest.fixture
def company_id():
    """Test company ID."""
    return uuid4()


@pytest.fixture
def entity_id():
    """Test entity/supplier ID."""
    return uuid4()


class TestSupplierRankingCategoryEnum:
    """Tests for SupplierRankingCategory enum."""

    def test_all_categories_exist(self):
        """Test all expected categories are defined."""
        expected = ["punctuality", "price", "reliability", "communication", "payment_terms"]
        for category in expected:
            assert SupplierRankingCategory(category) is not None

    def test_category_values(self):
        """Test category string values."""
        assert SupplierRankingCategory.PUNCTUALITY.value == "punctuality"
        assert SupplierRankingCategory.PRICE.value == "price"
        assert SupplierRankingCategory.RELIABILITY.value == "reliability"
        assert SupplierRankingCategory.COMMUNICATION.value == "communication"
        assert SupplierRankingCategory.PAYMENT_TERMS.value == "payment_terms"


class TestSupplierTierEnum:
    """Tests for SupplierTier enum."""

    def test_all_tiers_exist(self):
        """Test all expected tiers are defined."""
        expected = ["platinum", "gold", "silver", "bronze", "critical"]
        for tier in expected:
            assert SupplierTier(tier) is not None

    def test_tier_values(self):
        """Test tier string values."""
        assert SupplierTier.PLATINUM.value == "platinum"
        assert SupplierTier.GOLD.value == "gold"
        assert SupplierTier.SILVER.value == "silver"
        assert SupplierTier.BRONZE.value == "bronze"
        assert SupplierTier.CRITICAL.value == "critical"


class TestCategoryWeights:
    """Tests for category weights configuration."""

    def test_weights_sum_to_one(self, ranking_service):
        """Category weights should sum to 1.0."""
        total = sum(ranking_service.CATEGORY_WEIGHTS.values())
        assert abs(total - 1.0) < 0.001

    def test_all_categories_have_weights(self, ranking_service):
        """All categories should have a weight defined."""
        for category in SupplierRankingCategory:
            assert category in ranking_service.CATEGORY_WEIGHTS

    def test_punctuality_has_highest_weight(self, ranking_service):
        """Punctuality should have highest weight."""
        punctuality_weight = ranking_service.CATEGORY_WEIGHTS[SupplierRankingCategory.PUNCTUALITY]
        for category, weight in ranking_service.CATEGORY_WEIGHTS.items():
            if category != SupplierRankingCategory.PUNCTUALITY:
                assert punctuality_weight >= weight


class TestSupplierScoreDataclass:
    """Tests for SupplierScore dataclass."""

    def test_category_score_creation(self):
        """Test SupplierScore can be created."""
        score = SupplierScore(
            category=SupplierRankingCategory.PUNCTUALITY,
            score=85.0,
            weight=0.30,
            data_points=15,
            trend="up",
            details={"on_time_deliveries": 12, "total_deliveries": 15},
        )
        assert score.category == SupplierRankingCategory.PUNCTUALITY
        assert score.score == 85.0
        assert score.weight == 0.30
        assert score.data_points == 15
        assert score.trend == "up"
        assert score.details["on_time_deliveries"] == 12

    def test_category_score_with_defaults(self):
        """Test SupplierScore with default values."""
        score = SupplierScore(
            category=SupplierRankingCategory.PRICE,
            score=70.0,
            weight=0.25,
            data_points=10,
            trend="stable",
        )
        assert score.details == {}


class TestSupplierRankingDataclass:
    """Tests for SupplierRanking dataclass."""

    def test_supplier_ranking_creation(self, entity_id):
        """Test SupplierRanking can be created."""
        category_scores = [
            SupplierScore(
                category=SupplierRankingCategory.PUNCTUALITY,
                score=90.0,
                weight=0.30,
                data_points=20,
                trend="up",
            )
        ]

        ranking = SupplierRanking(
            entity_id=entity_id,
            entity_name="Test Lieferant GmbH",
            overall_score=85.0,
            tier=SupplierTier.GOLD,
            category_scores=category_scores,
            total_orders=50,
            total_volume=Decimal("100000.00"),
            first_order_date=date(2024, 1, 1),
            last_order_date=date(2026, 1, 15),
            avg_order_value=Decimal("2000.00"),
            score_trend="improving",
            previous_score=78.0,
        )

        assert ranking.entity_id == entity_id
        assert ranking.entity_name == "Test Lieferant GmbH"
        assert ranking.overall_score == 85.0
        assert ranking.tier == SupplierTier.GOLD
        assert len(ranking.category_scores) == 1
        assert ranking.total_orders == 50
        assert ranking.total_volume == Decimal("100000.00")
        assert ranking.score_trend == "improving"

    def test_supplier_ranking_with_defaults(self, entity_id):
        """Test SupplierRanking default values."""
        ranking = SupplierRanking(
            entity_id=entity_id,
            entity_name="Test Supplier",
            overall_score=75.0,
            tier=SupplierTier.SILVER,
            category_scores=[],
            total_orders=10,
            total_volume=Decimal("10000.00"),
            first_order_date=None,
            last_order_date=None,
            avg_order_value=Decimal("1000.00"),
            score_trend="stable",
            previous_score=None,
        )

        assert ranking.first_order_date is None
        assert ranking.last_order_date is None
        assert ranking.previous_score is None
        assert ranking.recommendations == []


class TestTierDetermination:
    """Tests for tier determination logic."""

    def test_platinum_tier_threshold(self, ranking_service):
        """Scores >= 90 should be platinum."""
        tier = ranking_service._determine_tier(90.0)
        assert tier == SupplierTier.PLATINUM
        tier = ranking_service._determine_tier(95.0)
        assert tier == SupplierTier.PLATINUM
        tier = ranking_service._determine_tier(100.0)
        assert tier == SupplierTier.PLATINUM

    def test_gold_tier_threshold(self, ranking_service):
        """Scores 75-89 should be gold."""
        tier = ranking_service._determine_tier(75.0)
        assert tier == SupplierTier.GOLD
        tier = ranking_service._determine_tier(85.0)
        assert tier == SupplierTier.GOLD
        tier = ranking_service._determine_tier(89.9)
        assert tier == SupplierTier.GOLD

    def test_silver_tier_threshold(self, ranking_service):
        """Scores 60-74 should be silver."""
        tier = ranking_service._determine_tier(60.0)
        assert tier == SupplierTier.SILVER
        tier = ranking_service._determine_tier(70.0)
        assert tier == SupplierTier.SILVER
        tier = ranking_service._determine_tier(74.9)
        assert tier == SupplierTier.SILVER

    def test_bronze_tier_threshold(self, ranking_service):
        """Scores 40-59 should be bronze."""
        tier = ranking_service._determine_tier(40.0)
        assert tier == SupplierTier.BRONZE
        tier = ranking_service._determine_tier(50.0)
        assert tier == SupplierTier.BRONZE
        tier = ranking_service._determine_tier(59.9)
        assert tier == SupplierTier.BRONZE

    def test_critical_tier_threshold(self, ranking_service):
        """Scores < 40 should be critical."""
        tier = ranking_service._determine_tier(39.9)
        assert tier == SupplierTier.CRITICAL
        tier = ranking_service._determine_tier(20.0)
        assert tier == SupplierTier.CRITICAL
        tier = ranking_service._determine_tier(0.0)
        assert tier == SupplierTier.CRITICAL


class TestScoreTrendCalculation:
    """Tests for score trend calculation."""

    def test_improving_trend(self, ranking_service):
        """Significant score increase should be improving."""
        trend = ranking_service._calculate_score_trend(70.0, 80.0)
        assert trend == "improving"

    def test_declining_trend(self, ranking_service):
        """Significant score decrease should be declining."""
        trend = ranking_service._calculate_score_trend(80.0, 70.0)
        assert trend == "declining"

    def test_stable_trend(self, ranking_service):
        """Small changes should be stable."""
        trend = ranking_service._calculate_score_trend(75.0, 77.0)
        assert trend == "stable"
        trend = ranking_service._calculate_score_trend(75.0, 73.0)
        assert trend == "stable"

    def test_no_previous_score(self, ranking_service):
        """No previous score should be stable."""
        trend = ranking_service._calculate_score_trend(None, 80.0)
        assert trend == "stable"


class TestOverallScoreCalculation:
    """Tests for overall score calculation."""

    def test_weighted_score_calculation(self, ranking_service):
        """Test weighted average calculation."""
        category_scores = [
            SupplierScore(
                category=SupplierRankingCategory.PUNCTUALITY,
                score=100.0,
                weight=0.30,
                data_points=10,
                trend="stable",
            ),
            SupplierScore(
                category=SupplierRankingCategory.PRICE,
                score=80.0,
                weight=0.25,
                data_points=10,
                trend="stable",
            ),
            SupplierScore(
                category=SupplierRankingCategory.RELIABILITY,
                score=90.0,
                weight=0.25,
                data_points=10,
                trend="stable",
            ),
            SupplierScore(
                category=SupplierRankingCategory.COMMUNICATION,
                score=70.0,
                weight=0.10,
                data_points=10,
                trend="stable",
            ),
            SupplierScore(
                category=SupplierRankingCategory.PAYMENT_TERMS,
                score=85.0,
                weight=0.10,
                data_points=10,
                trend="stable",
            ),
        ]

        overall = ranking_service._calculate_overall_score(category_scores)
        # Expected: 100*0.3 + 80*0.25 + 90*0.25 + 70*0.1 + 85*0.1 = 30 + 20 + 22.5 + 7 + 8.5 = 88.0
        assert abs(overall - 88.0) < 0.1

    def test_empty_category_scores(self, ranking_service):
        """Empty category scores should return 0."""
        overall = ranking_service._calculate_overall_score([])
        assert overall == 0.0


class TestRecommendationsGeneration:
    """Tests for recommendation generation."""

    def test_platinum_recommendations(self, ranking_service):
        """Platinum suppliers should have positive recommendations."""
        # Create mock invoices list with enough items
        mock_invoices = [MagicMock() for _ in range(50)]
        recommendations = ranking_service._generate_recommendations(
            [], SupplierTier.PLATINUM, mock_invoices
        )
        assert len(recommendations) > 0
        assert any("Top-Lieferant" in r or "strategisch" in r.lower() for r in recommendations)

    def test_critical_recommendations(self, ranking_service):
        """Critical suppliers should have warning recommendations."""
        mock_invoices = [MagicMock() for _ in range(50)]
        recommendations = ranking_service._generate_recommendations(
            [], SupplierTier.CRITICAL, mock_invoices
        )
        assert len(recommendations) > 0
        assert any("Alternative" in r or "kritisch" in r.lower() for r in recommendations)

    def test_low_data_recommendations(self, ranking_service):
        """Low data points should trigger data collection recommendation."""
        # Only 2 invoices - should trigger "wenig Daten" recommendation
        mock_invoices = [MagicMock() for _ in range(2)]
        recommendations = ranking_service._generate_recommendations(
            [], SupplierTier.SILVER, mock_invoices
        )
        assert any("Daten" in r or "daten" in r.lower() for r in recommendations)


class TestSingletonPattern:
    """Tests for singleton pattern."""

    def test_singleton_returns_same_instance(self):
        """get_supplier_ranking_service should return same instance."""
        service1 = get_supplier_ranking_service()
        service2 = get_supplier_ranking_service()
        assert service1 is service2

    def test_singleton_is_correct_type(self):
        """Singleton should be SupplierRankingService instance."""
        service = get_supplier_ranking_service()
        assert isinstance(service, SupplierRankingService)


class TestSupplierRankingReportDataclass:
    """Tests for SupplierRankingReport dataclass."""

    def test_report_creation(self, company_id):
        """Test SupplierRankingReport can be created."""
        report = SupplierRankingReport(
            company_id=company_id,
            total_suppliers=100,
            ranked_suppliers=95,
            tier_distribution={
                "platinum": 10,
                "gold": 25,
                "silver": 35,
                "bronze": 20,
                "critical": 5,
            },
            top_suppliers=[],
            critical_suppliers=[],
            improving_suppliers=[],
            declining_suppliers=[],
            avg_overall_score=72.5,
            avg_punctuality=75.0,
            avg_reliability=70.0,
            analysis_period_start=date(2025, 1, 1),
            analysis_period_end=date(2026, 1, 1),
        )

        assert report.company_id == company_id
        assert report.total_suppliers == 100
        assert report.ranked_suppliers == 95
        assert report.tier_distribution["platinum"] == 10
        assert report.avg_overall_score == 72.5

    def test_report_with_defaults(self, company_id):
        """Test SupplierRankingReport default values."""
        report = SupplierRankingReport(
            company_id=company_id,
            total_suppliers=10,
            ranked_suppliers=10,
            tier_distribution={},
            top_suppliers=[],
            critical_suppliers=[],
            improving_suppliers=[],
            declining_suppliers=[],
            avg_overall_score=50.0,
            avg_punctuality=50.0,
            avg_reliability=50.0,
            analysis_period_start=date(2025, 1, 1),
            analysis_period_end=date(2026, 1, 1),
        )

        assert report.generated_at is not None


class TestCategoryTrendDetection:
    """Tests for category trend detection."""

    def test_trend_up_detection(self, ranking_service):
        """Test upward trend detection."""
        # Scores improving over time
        scores = [60.0, 65.0, 70.0, 75.0, 80.0]
        trend = ranking_service._detect_category_trend(scores)
        assert trend == "up"

    def test_trend_down_detection(self, ranking_service):
        """Test downward trend detection."""
        # Scores declining over time
        scores = [80.0, 75.0, 70.0, 65.0, 60.0]
        trend = ranking_service._detect_category_trend(scores)
        assert trend == "down"

    def test_trend_stable_detection(self, ranking_service):
        """Test stable trend detection."""
        # Scores relatively stable
        scores = [70.0, 72.0, 68.0, 71.0, 70.0]
        trend = ranking_service._detect_category_trend(scores)
        assert trend == "stable"

    def test_empty_scores(self, ranking_service):
        """Empty scores should return stable."""
        trend = ranking_service._detect_category_trend([])
        assert trend == "stable"

    def test_single_score(self, ranking_service):
        """Single score should return stable."""
        trend = ranking_service._detect_category_trend([75.0])
        assert trend == "stable"
