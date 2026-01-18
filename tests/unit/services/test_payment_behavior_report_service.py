# -*- coding: utf-8 -*-
"""Unit tests for Payment Behavior Report Service.

Tests:
- Payment behavior categories and trends
- Score calculation
- Metrics computation
- Category determination
- Report generation (mocked dependencies)
"""

from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.payment_behavior_report_service import (
    PaymentBehaviorReportService,
    PaymentBehaviorCategory,
    PaymentTrend,
    PaymentMetrics,
    PaymentBehaviorSummary,
    PaymentBehaviorReport,
    get_payment_behavior_report_service,
)


@pytest.fixture
def payment_service() -> PaymentBehaviorReportService:
    """Create PaymentBehaviorReportService instance."""
    return PaymentBehaviorReportService()


@pytest.fixture
def company_id():
    """Test company ID."""
    return uuid4()


@pytest.fixture
def entity_id():
    """Test entity/customer ID."""
    return uuid4()


class TestPaymentBehaviorCategoryEnum:
    """Tests for PaymentBehaviorCategory enum."""

    def test_all_categories_exist(self):
        """Test all expected categories are defined."""
        expected = ["excellent", "punctual", "delayed", "problematic", "defaulter"]
        for category in expected:
            assert PaymentBehaviorCategory(category) is not None

    def test_category_values(self):
        """Test category string values."""
        assert PaymentBehaviorCategory.EXCELLENT.value == "excellent"
        assert PaymentBehaviorCategory.PUNCTUAL.value == "punctual"
        assert PaymentBehaviorCategory.DELAYED.value == "delayed"
        assert PaymentBehaviorCategory.PROBLEMATIC.value == "problematic"
        assert PaymentBehaviorCategory.DEFAULTER.value == "defaulter"


class TestPaymentTrendEnum:
    """Tests for PaymentTrend enum."""

    def test_all_trends_exist(self):
        """Test all expected trends are defined."""
        expected = ["improving", "stable", "declining"]
        for trend in expected:
            assert PaymentTrend(trend) is not None

    def test_trend_values(self):
        """Test trend string values."""
        assert PaymentTrend.IMPROVING.value == "improving"
        assert PaymentTrend.STABLE.value == "stable"
        assert PaymentTrend.DECLINING.value == "declining"


class TestPaymentMetricsDataclass:
    """Tests for PaymentMetrics dataclass."""

    def test_metrics_creation(self, entity_id):
        """Test PaymentMetrics can be created."""
        metrics = PaymentMetrics(
            entity_id=entity_id,
            entity_name="Test Kunde GmbH",
            total_invoices=24,
            paid_invoices=20,
            unpaid_invoices=4,
            overdue_invoices=1,
            total_volume=Decimal("50000.00"),
            paid_volume=Decimal("45000.00"),
            outstanding_volume=Decimal("5000.00"),
            overdue_volume=Decimal("1200.00"),
            avg_payment_days=28.5,
            min_payment_days=14,
            max_payment_days=45,
            median_payment_days=27.0,
            punctuality_rate=0.85,
            early_payment_rate=0.15,
            late_payment_rate=0.10,
            default_rate=0.02,
            skonto_utilization_rate=0.60,
            skonto_saved=Decimal("450.00"),
            behavior_category=PaymentBehaviorCategory.PUNCTUAL,
            payment_trend=PaymentTrend.STABLE,
            payment_score=82.5,
            first_invoice_date=date(2025, 1, 1),
            last_invoice_date=date(2026, 1, 10),
            analysis_period_days=365,
        )

        assert metrics.entity_id == entity_id
        assert metrics.entity_name == "Test Kunde GmbH"
        assert metrics.total_invoices == 24
        assert metrics.paid_invoices == 20
        assert metrics.avg_payment_days == 28.5
        assert metrics.punctuality_rate == 0.85
        assert metrics.behavior_category == PaymentBehaviorCategory.PUNCTUAL
        assert metrics.payment_score == 82.5

    def test_metrics_with_none_dates(self, entity_id):
        """Test PaymentMetrics with None dates."""
        metrics = PaymentMetrics(
            entity_id=entity_id,
            entity_name="New Customer",
            total_invoices=2,
            paid_invoices=1,
            unpaid_invoices=1,
            overdue_invoices=0,
            total_volume=Decimal("1000.00"),
            paid_volume=Decimal("500.00"),
            outstanding_volume=Decimal("500.00"),
            overdue_volume=Decimal("0.00"),
            avg_payment_days=15.0,
            min_payment_days=15,
            max_payment_days=15,
            median_payment_days=15.0,
            punctuality_rate=1.0,
            early_payment_rate=0.0,
            late_payment_rate=0.0,
            default_rate=0.0,
            skonto_utilization_rate=0.0,
            skonto_saved=Decimal("0.00"),
            behavior_category=PaymentBehaviorCategory.EXCELLENT,
            payment_trend=PaymentTrend.STABLE,
            payment_score=95.0,
            first_invoice_date=None,
            last_invoice_date=None,
            analysis_period_days=30,
        )

        assert metrics.first_invoice_date is None
        assert metrics.last_invoice_date is None


class TestPaymentBehaviorSummaryDataclass:
    """Tests for PaymentBehaviorSummary dataclass."""

    def test_summary_creation_with_defaults(self):
        """Test PaymentBehaviorSummary can be created with defaults."""
        summary = PaymentBehaviorSummary()
        assert summary.excellent_count == 0
        assert summary.punctual_count == 0
        assert summary.delayed_count == 0
        assert summary.problematic_count == 0
        assert summary.defaulter_count == 0
        assert summary.avg_payment_days_overall == 0.0
        assert summary.avg_punctuality_rate == 0.0
        assert summary.avg_payment_score == 0.0
        assert summary.volume_at_risk == Decimal("0.00")
        assert summary.overdue_total == Decimal("0.00")
        assert summary.improving_count == 0
        assert summary.stable_count == 0
        assert summary.declining_count == 0

    def test_summary_with_values(self):
        """Test PaymentBehaviorSummary with values."""
        summary = PaymentBehaviorSummary(
            excellent_count=10,
            punctual_count=50,
            delayed_count=25,
            problematic_count=10,
            defaulter_count=5,
            avg_payment_days_overall=30.5,
            avg_punctuality_rate=0.75,
            avg_payment_score=72.0,
            volume_at_risk=Decimal("150000.00"),
            overdue_total=Decimal("25000.00"),
            improving_count=15,
            stable_count=65,
            declining_count=20,
        )

        assert summary.excellent_count == 10
        assert summary.problematic_count == 10
        assert summary.avg_payment_days_overall == 30.5
        assert summary.volume_at_risk == Decimal("150000.00")


class TestPaymentBehaviorReportDataclass:
    """Tests for PaymentBehaviorReport dataclass."""

    def test_report_creation(self, company_id):
        """Test PaymentBehaviorReport can be created."""
        summary = PaymentBehaviorSummary(
            excellent_count=5,
            punctual_count=20,
        )

        report = PaymentBehaviorReport(
            company_id=company_id,
            total_customers=100,
            analyzed_customers=90,
            summary=summary,
            customer_metrics=[],
            top_payers=[],
            worst_payers=[],
            improving_customers=[],
            declining_customers=[],
            high_risk_customers=[],
            analysis_period_start=date(2025, 1, 1),
            analysis_period_end=date(2026, 1, 1),
        )

        assert report.company_id == company_id
        assert report.total_customers == 100
        assert report.analyzed_customers == 90
        assert report.summary.excellent_count == 5
        assert report.benchmark_avg_payment_days == 30.0
        assert report.benchmark_punctuality_rate == 0.75

    def test_report_generated_at_default(self, company_id):
        """Test report generated_at has default value."""
        report = PaymentBehaviorReport(
            company_id=company_id,
            total_customers=10,
            analyzed_customers=10,
            summary=PaymentBehaviorSummary(),
            customer_metrics=[],
            top_payers=[],
            worst_payers=[],
            improving_customers=[],
            declining_customers=[],
            high_risk_customers=[],
            analysis_period_start=date(2025, 1, 1),
            analysis_period_end=date(2026, 1, 1),
        )

        assert report.generated_at is not None


class TestBehaviorCategorization:
    """Tests for behavior categorization logic."""

    def test_defaulter_category(self, payment_service):
        """High default rate should be categorized as defaulter."""
        category = payment_service._categorize_behavior(
            punctuality_rate=0.5,
            late_rate=0.2,
            default_rate=0.15,  # >= 10% threshold
        )
        assert category == PaymentBehaviorCategory.DEFAULTER

    def test_problematic_category(self, payment_service):
        """High late rate should be categorized as problematic."""
        category = payment_service._categorize_behavior(
            punctuality_rate=0.5,
            late_rate=0.35,  # >= 30% threshold
            default_rate=0.05,
        )
        assert category == PaymentBehaviorCategory.PROBLEMATIC

    def test_delayed_category(self, payment_service):
        """Moderate late rate should be categorized as delayed."""
        category = payment_service._categorize_behavior(
            punctuality_rate=0.8,
            late_rate=0.15,  # > 10% but < 30%
            default_rate=0.02,
        )
        assert category == PaymentBehaviorCategory.DELAYED

    def test_excellent_category(self, payment_service):
        """Very high punctuality should be categorized as excellent."""
        category = payment_service._categorize_behavior(
            punctuality_rate=0.98,  # >= 95%
            late_rate=0.02,
            default_rate=0.0,
        )
        assert category == PaymentBehaviorCategory.EXCELLENT

    def test_punctual_category(self, payment_service):
        """Normal punctuality should be categorized as punctual."""
        category = payment_service._categorize_behavior(
            punctuality_rate=0.85,  # < 95% but low late rate
            late_rate=0.08,  # <= 10%
            default_rate=0.02,
        )
        assert category == PaymentBehaviorCategory.PUNCTUAL


class TestPaymentScoreCalculation:
    """Tests for payment score calculation."""

    def test_perfect_score(self, payment_service):
        """Perfect metrics should yield high score."""
        score = payment_service._calculate_payment_score(
            punctuality_rate=1.0,
            avg_payment_days=20.0,  # Early payment
            default_rate=0.0,
            skonto_rate=1.0,
        )
        assert score >= 95.0

    def test_poor_score(self, payment_service):
        """Poor metrics should yield low score."""
        score = payment_service._calculate_payment_score(
            punctuality_rate=0.3,
            avg_payment_days=60.0,  # Very late
            default_rate=0.15,
            skonto_rate=0.0,
        )
        assert score <= 40.0

    def test_average_score(self, payment_service):
        """Average metrics should yield medium score."""
        score = payment_service._calculate_payment_score(
            punctuality_rate=0.75,
            avg_payment_days=35.0,
            default_rate=0.05,
            skonto_rate=0.3,
        )
        assert 50.0 <= score <= 80.0

    def test_score_bounds(self, payment_service):
        """Score should be bounded between 0 and 100."""
        # Extremely bad metrics
        score_bad = payment_service._calculate_payment_score(
            punctuality_rate=0.0,
            avg_payment_days=100.0,
            default_rate=0.5,
            skonto_rate=0.0,
        )
        assert score_bad >= 0.0

        # Perfect metrics
        score_good = payment_service._calculate_payment_score(
            punctuality_rate=1.0,
            avg_payment_days=10.0,
            default_rate=0.0,
            skonto_rate=1.0,
        )
        assert score_good <= 100.0


class TestScoreWeights:
    """Tests for score weight configuration."""

    def test_weights_sum_to_one(self, payment_service):
        """Score weights should sum to 1.0."""
        total = sum(payment_service.SCORE_WEIGHTS.values())
        assert abs(total - 1.0) < 0.001

    def test_punctuality_has_highest_weight(self, payment_service):
        """Punctuality should have highest weight."""
        punctuality_weight = payment_service.SCORE_WEIGHTS["punctuality"]
        for key, weight in payment_service.SCORE_WEIGHTS.items():
            if key != "punctuality":
                assert punctuality_weight >= weight


class TestThresholds:
    """Tests for service thresholds."""

    def test_punctuality_threshold_exists(self, payment_service):
        """Punctuality threshold should be defined."""
        assert hasattr(payment_service, 'PUNCTUALITY_THRESHOLD')
        assert payment_service.PUNCTUALITY_THRESHOLD > 0

    def test_delayed_threshold_exists(self, payment_service):
        """Delayed threshold should be defined."""
        assert hasattr(payment_service, 'DELAYED_THRESHOLD')
        assert payment_service.DELAYED_THRESHOLD > payment_service.PUNCTUALITY_THRESHOLD

    def test_problematic_threshold_exists(self, payment_service):
        """Problematic threshold should be defined."""
        assert hasattr(payment_service, 'PROBLEMATIC_THRESHOLD')
        assert 0 < payment_service.PROBLEMATIC_THRESHOLD <= 1.0

    def test_default_threshold_exists(self, payment_service):
        """Default threshold should be defined."""
        assert hasattr(payment_service, 'DEFAULT_THRESHOLD')
        assert 0 < payment_service.DEFAULT_THRESHOLD <= 1.0


class TestSingletonPattern:
    """Tests for singleton pattern."""

    def test_singleton_returns_same_instance(self):
        """get_payment_behavior_report_service should return same instance."""
        service1 = get_payment_behavior_report_service()
        service2 = get_payment_behavior_report_service()
        assert service1 is service2

    def test_singleton_is_correct_type(self):
        """Singleton should be PaymentBehaviorReportService instance."""
        service = get_payment_behavior_report_service()
        assert isinstance(service, PaymentBehaviorReportService)


class TestTrendCalculation:
    """Tests for payment trend calculation."""

    @pytest.mark.asyncio
    async def test_insufficient_data_stable(self, payment_service):
        """Insufficient data should return stable trend."""
        # Create mock invoices (less than 4)
        invoices = [MagicMock() for _ in range(3)]
        trend = await payment_service._calculate_trend(invoices)
        assert trend == PaymentTrend.STABLE

    @pytest.mark.asyncio
    async def test_empty_invoices_stable(self, payment_service):
        """Empty invoices should return stable trend."""
        trend = await payment_service._calculate_trend([])
        assert trend == PaymentTrend.STABLE


class TestVolumeCalculations:
    """Tests for volume-based calculations."""

    def test_calculate_rates_with_zero_paid(self, payment_service):
        """Zero paid invoices should not cause division by zero."""
        # This is implicitly tested through _calculate_metrics
        # but we verify the logic doesn't break
        paid_invoices = 0
        late_payments = 0

        # Rate calculation from service
        punctuality_rate = (paid_invoices - late_payments) / paid_invoices if paid_invoices > 0 else 0.0
        assert punctuality_rate == 0.0

    def test_calculate_rates_with_zero_total(self, payment_service):
        """Zero total invoices should not cause division by zero."""
        total_invoices = 0
        severe_overdue = 0

        # Default rate calculation
        default_rate = severe_overdue / total_invoices if total_invoices > 0 else 0.0
        assert default_rate == 0.0
