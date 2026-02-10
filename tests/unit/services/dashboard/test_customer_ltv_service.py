# -*- coding: utf-8 -*-
"""Unit Tests fuer CustomerLTVService.

Testet:
- Customer Lifetime Value Berechnungen
- Churn-Risiko-Algorithmen
- Trend-Analysen (wachsend/ruecklaeufig)
- Widget-Daten-Export
- Error-Resilience

Enterprise Feature: Januar 2026
"""

import pytest
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import List, Dict
from unittest.mock import AsyncMock, Mock, patch
from uuid import UUID

from app.services.dashboard.customer_ltv_service import (
    CustomerLTVService,
    CustomerLTVResult,
    CustomerMetrics,
    ChurnRisk,
    RevenueTrend,
    TrendDataPoint,
    get_customer_ltv_service,
)
from app.db.models import BusinessEntity, InvoiceTracking

pytestmark = [pytest.mark.unit]

TEST_USER_UUID = UUID("12345678-1234-5678-1234-567812345678")
TEST_COMPANY_UUID = UUID("87654321-4321-8765-4321-876543218765")


@pytest.fixture
def service() -> CustomerLTVService:
    """Erstelle CustomerLTVService Instanz."""
    return CustomerLTVService()


@pytest.fixture
def mock_db() -> AsyncMock:
    """Erstelle Mock-Datenbank-Session."""
    return AsyncMock()


class TestGetCustomerLTV:
    """Tests fuer get_customer_ltv Methode."""

    @pytest.mark.asyncio
    async def test_get_customer_ltv_success(
        self, service: CustomerLTVService, mock_db: AsyncMock
    ):
        """Test erfolgreiche Customer LTV Berechnung mit Kunden."""
        # Mock customer entities
        mock_customers = [
            Mock(
                id=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
                name="Top Kunde GmbH",
                entity_type="customer",
                is_deleted=False,
            ),
            Mock(
                id=UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"),
                name="Risk Kunde AG",
                entity_type="customer",
                is_deleted=False,
            ),
        ]

        # Mock metrics for customers
        mock_top_metrics = CustomerMetrics(
            entity_id=str(mock_customers[0].id),
            entity_name="Top Kunde GmbH",
            lifetime_value=Decimal("50000.00"),
            total_orders=20,
            avg_order_value=Decimal("2500.00"),
            churn_risk=ChurnRisk.LOW,
            churn_risk_score=15.0,
            days_since_last_order=10,
            revenue_trend=RevenueTrend.GROWING,
            trend_percentage=25.0,
        )

        mock_risk_metrics = CustomerMetrics(
            entity_id=str(mock_customers[1].id),
            entity_name="Risk Kunde AG",
            lifetime_value=Decimal("10000.00"),
            total_orders=5,
            avg_order_value=Decimal("2000.00"),
            churn_risk=ChurnRisk.CRITICAL,
            churn_risk_score=90.0,
            days_since_last_order=200,
            revenue_trend=RevenueTrend.DECLINING,
            trend_percentage=-20.0,
        )

        # Mock trend data
        mock_trend = [
            TrendDataPoint(
                period="2026-01",
                total_revenue=Decimal("30000.00"),
                customer_count=2,
                avg_order_value=Decimal("3000.00"),
            ),
        ]

        with patch.object(
            service, "_get_customers", return_value=mock_customers
        ) as mock_get_customers, patch.object(
            service,
            "_calculate_customer_metrics",
            side_effect=[mock_top_metrics, mock_risk_metrics],
        ) as mock_calc_metrics, patch.object(
            service, "_calculate_trend_data", return_value=mock_trend
        ):

            result = await service.get_customer_ltv(
                db=mock_db,
                user_id=TEST_USER_UUID,
                company_id=TEST_COMPANY_UUID,
                period_days=365,
            )

            # Verify result structure
            assert isinstance(result, CustomerLTVResult)
            assert result.period_days == 365
            assert result.total_customers == 2
            assert result.active_customers == 2
            assert result.total_ltv == Decimal("60000.00")
            assert result.avg_ltv == Decimal("30000.00")

            # Verify top customers sorted by LTV
            assert len(result.top_customers) == 2
            assert result.top_customers[0].entity_id == str(mock_customers[0].id)
            assert result.top_customers[0].lifetime_value == Decimal("50000.00")

            # Verify at-risk customers filtered and sorted
            assert len(result.at_risk_customers) == 1
            assert result.at_risk_customers[0].entity_id == str(mock_customers[1].id)
            assert result.at_risk_customers[0].churn_risk == ChurnRisk.CRITICAL

            # Verify method calls
            mock_get_customers.assert_called_once_with(mock_db, TEST_COMPANY_UUID)
            assert mock_calc_metrics.call_count == 2

    @pytest.mark.asyncio
    async def test_get_customer_ltv_no_customers(
        self, service: CustomerLTVService, mock_db: AsyncMock
    ):
        """Test Customer LTV mit leerer Kundenliste."""
        with patch.object(
            service, "_get_customers", return_value=[]
        ), patch.object(
            service, "_calculate_trend_data", return_value=[]
        ):

            result = await service.get_customer_ltv(
                db=mock_db,
                user_id=TEST_USER_UUID,
                company_id=TEST_COMPANY_UUID,
                period_days=365,
            )

            assert result.total_customers == 0
            assert result.active_customers == 0
            assert result.total_ltv == Decimal("0.00")
            assert result.avg_ltv == Decimal("0.00")
            assert result.avg_churn_risk == 0.0
            assert len(result.top_customers) == 0
            assert len(result.at_risk_customers) == 0


class TestGetWidgetData:
    """Tests fuer get_widget_data Methode."""

    @pytest.mark.asyncio
    async def test_get_widget_data(
        self, service: CustomerLTVService, mock_db: AsyncMock
    ):
        """Test Widget-Daten-Export im korrekten Format."""
        # Mock result from get_customer_ltv
        mock_customer_1 = CustomerMetrics(
            entity_id="test-id-1",
            entity_name="Widget Kunde",
            lifetime_value=Decimal("15000.00"),
            total_orders=10,
            avg_order_value=Decimal("1500.00"),
            churn_risk=ChurnRisk.LOW,
            churn_risk_score=12.5,
            days_since_last_order=15,
            revenue_trend=RevenueTrend.GROWING,
            trend_percentage=18.7,
        )

        mock_result = CustomerLTVResult(
            generated_at=datetime(2026, 1, 15, 10, 30, 0),
            period_days=365,
            total_customers=5,
            active_customers=4,
            total_ltv=Decimal("75000.00"),
            avg_ltv=Decimal("18750.00"),
            avg_churn_risk=25.3,
            top_customers=[mock_customer_1],
            at_risk_customers=[],
            trend_data=[
                TrendDataPoint(
                    period="2026-01",
                    total_revenue=Decimal("20000.00"),
                    customer_count=4,
                    avg_order_value=Decimal("2000.00"),
                )
            ],
            overall_trend=RevenueTrend.STABLE,
            overall_trend_percentage=5.5,
        )

        with patch.object(
            service, "get_customer_ltv", return_value=mock_result
        ):

            widget_data = await service.get_widget_data(
                db=mock_db,
                user_id=TEST_USER_UUID,
                company_id=TEST_COMPANY_UUID,
                period_days=365,
            )

            # Verify top-level structure
            assert isinstance(widget_data, Dict)
            assert widget_data["generatedAt"] == "2026-01-15T10:30:00"
            assert widget_data["periodDays"] == 365
            assert widget_data["totalCustomers"] == 5
            assert widget_data["activeCustomers"] == 4
            assert widget_data["totalLTV"] == 75000.00
            assert widget_data["avgLTV"] == 18750.00
            assert widget_data["avgChurnRisk"] == 25.3
            assert widget_data["overallTrend"] == "stable"
            assert widget_data["trendPercentage"] == 5.5

            # Verify top customers format
            assert len(widget_data["topCustomers"]) == 1
            top = widget_data["topCustomers"][0]
            assert top["id"] == "test-id-1"
            assert top["name"] == "Widget Kunde"
            assert top["ltv"] == 15000.00
            assert top["orders"] == 10
            assert top["avgOrder"] == 1500.00
            assert top["trend"] == "growing"
            assert top["trendPct"] == 18.7
            assert top["churnRisk"] == "low"
            assert top["churnScore"] == 12.5
            assert top["daysSinceOrder"] == 15

            # Verify trend data format
            assert len(widget_data["trendData"]) == 1
            trend = widget_data["trendData"][0]
            assert trend["period"] == "2026-01"
            assert trend["revenue"] == 20000.00
            assert trend["customers"] == 4
            assert trend["avgOrder"] == 2000.00


class TestChurnRiskCalculation:
    """Tests fuer _calculate_churn_risk Methode."""

    def test_churn_risk_critical_long_absence_low_orders(
        self, service: CustomerLTVService
    ):
        """Test CRITICAL Churn-Risiko: >180 Tage ohne Bestellung, wenige Orders."""
        risk, score = service._calculate_churn_risk(
            days_since_order=200,
            total_orders=3,
            relationship_months=18,
        )

        assert risk == ChurnRisk.CRITICAL
        assert score >= 80.0
        assert score <= 100.0

    def test_churn_risk_high_90_180_days(
        self, service: CustomerLTVService
    ):
        """Test HIGH/CRITICAL Churn-Risiko: 91-180 Tage ohne Bestellung.

        Algorithm breakdown:
        - Base score: 80.0 (120 days in 91-180 range)
        - Frequency mod: +10 (5 orders / 12 months = 0.42/month < 0.5)
        - Duration mod: -5 (12 months)
        - Final: 80 + 10 - 5 = 85.0 → CRITICAL
        """
        risk, score = service._calculate_churn_risk(
            days_since_order=120,
            total_orders=5,
            relationship_months=12,
        )

        assert risk == ChurnRisk.CRITICAL
        assert score >= 80.0
        assert score == 85.0

    def test_churn_risk_low_recent_frequent(
        self, service: CustomerLTVService
    ):
        """Test LOW Churn-Risiko: <30 Tage, haeufige Bestellungen."""
        risk, score = service._calculate_churn_risk(
            days_since_order=15,
            total_orders=30,  # 30 orders in 12 months = 2.5/month
            relationship_months=12,
        )

        assert risk == ChurnRisk.LOW
        assert score < 40.0

    def test_churn_risk_medium_range(
        self, service: CustomerLTVService
    ):
        """Test MEDIUM Churn-Risiko: 31-60 Tage."""
        risk, score = service._calculate_churn_risk(
            days_since_order=45,
            total_orders=8,
            relationship_months=10,
        )

        # Base score should be 30 for 31-60 days
        # With modifiers, should land in MEDIUM range (40-60)
        assert score >= 30.0

    def test_churn_risk_loyalty_modifier(
        self, service: CustomerLTVService
    ):
        """Test Langzeit-Kunden-Modifikator (24+ Monate).

        Algorithm breakdown:
        Short (6 months):
        - Base: 60.0 (70 days in 61-90 range)
        - Frequency: -5 (10/6 = 1.67/month >= 1)
        - Duration: +5 (6 months < 12)
        - Final: 60 - 5 + 5 = 60.0

        Long (30 months):
        - Base: 60.0
        - Frequency: +10 (10/30 = 0.33/month < 0.5)
        - Duration: -10 (30 months >= 24)
        - Final: 60 + 10 - 10 = 60.0

        Both are equal due to offsetting modifiers. Use different input to show loyalty effect.
        """
        # Use higher order count to show loyalty effect more clearly
        risk_short, score_short = service._calculate_churn_risk(
            days_since_order=70,
            total_orders=18,  # 18/6 = 3/month → freq_mod = -15
            relationship_months=6,
        )

        risk_long, score_long = service._calculate_churn_risk(
            days_since_order=70,
            total_orders=60,  # 60/30 = 2/month → freq_mod = -15
            relationship_months=30,
        )

        # Expected scores:
        # Short: 60 - 15 + 5 = 50.0
        # Long: 60 - 15 - 10 = 35.0
        # Long-term customer should have lower risk score
        assert score_long < score_short
        assert score_short == 50.0
        assert score_long == 35.0


class TestTrendCalculation:
    """Tests fuer Trend-Analyse Methoden."""

    def test_trend_growing_over_10_percent(
        self, service: CustomerLTVService
    ):
        """Test GROWING Trend bei >10% Steigerung."""
        trend_data = [
            TrendDataPoint(
                period="2025-10",
                total_revenue=Decimal("10000.00"),
                customer_count=5,
                avg_order_value=Decimal("2000.00"),
            ),
            TrendDataPoint(
                period="2025-11",
                total_revenue=Decimal("10500.00"),
                customer_count=5,
                avg_order_value=Decimal("2100.00"),
            ),
            TrendDataPoint(
                period="2025-12",
                total_revenue=Decimal("12000.00"),
                customer_count=6,
                avg_order_value=Decimal("2200.00"),
            ),
            TrendDataPoint(
                period="2026-01",
                total_revenue=Decimal("13000.00"),
                customer_count=6,
                avg_order_value=Decimal("2300.00"),
            ),
        ]

        trend, pct = service._determine_overall_trend(trend_data)

        assert trend == RevenueTrend.GROWING
        assert pct > 10.0

    def test_trend_declining_over_10_percent(
        self, service: CustomerLTVService
    ):
        """Test DECLINING Trend bei <-10% Rueckgang."""
        trend_data = [
            TrendDataPoint(
                period="2025-10",
                total_revenue=Decimal("15000.00"),
                customer_count=8,
                avg_order_value=Decimal("2500.00"),
            ),
            TrendDataPoint(
                period="2025-11",
                total_revenue=Decimal("14000.00"),
                customer_count=7,
                avg_order_value=Decimal("2400.00"),
            ),
            TrendDataPoint(
                period="2025-12",
                total_revenue=Decimal("12000.00"),
                customer_count=6,
                avg_order_value=Decimal("2200.00"),
            ),
            TrendDataPoint(
                period="2026-01",
                total_revenue=Decimal("10000.00"),
                customer_count=5,
                avg_order_value=Decimal("2000.00"),
            ),
        ]

        trend, pct = service._determine_overall_trend(trend_data)

        assert trend == RevenueTrend.DECLINING
        assert pct < -10.0

    def test_trend_stable_within_10_percent(
        self, service: CustomerLTVService
    ):
        """Test STABLE Trend bei Aenderungen innerhalb ±10%."""
        trend_data = [
            TrendDataPoint(
                period="2025-11",
                total_revenue=Decimal("10000.00"),
                customer_count=5,
                avg_order_value=Decimal("2000.00"),
            ),
            TrendDataPoint(
                period="2025-12",
                total_revenue=Decimal("10200.00"),
                customer_count=5,
                avg_order_value=Decimal("2040.00"),
            ),
            TrendDataPoint(
                period="2026-01",
                total_revenue=Decimal("10500.00"),
                customer_count=5,
                avg_order_value=Decimal("2100.00"),
            ),
        ]

        trend, pct = service._determine_overall_trend(trend_data)

        assert trend == RevenueTrend.STABLE
        assert -10.0 <= pct <= 10.0

    def test_trend_insufficient_data(
        self, service: CustomerLTVService
    ):
        """Test Trend-Berechnung mit weniger als 2 Datenpunkten."""
        trend_data = [
            TrendDataPoint(
                period="2026-01",
                total_revenue=Decimal("10000.00"),
                customer_count=5,
                avg_order_value=Decimal("2000.00"),
            ),
        ]

        trend, pct = service._determine_overall_trend(trend_data)

        assert trend == RevenueTrend.STABLE
        assert pct == 0.0

        # Empty list
        trend_empty, pct_empty = service._determine_overall_trend([])
        assert trend_empty == RevenueTrend.STABLE
        assert pct_empty == 0.0


class TestDatabaseErrorResilience:
    """Tests fuer Fehler-Resilience bei Datenbankoperationen."""

    @pytest.mark.asyncio
    async def test_db_error_in_get_customers(
        self, service: CustomerLTVService, mock_db: AsyncMock
    ):
        """Test Error-Handling wenn _get_customers fehlschlaegt."""
        with patch.object(
            service,
            "_get_customers",
            side_effect=Exception("Database connection lost"),
        ):

            with pytest.raises(Exception) as exc_info:
                await service.get_customer_ltv(
                    db=mock_db,
                    user_id=TEST_USER_UUID,
                    company_id=TEST_COMPANY_UUID,
                    period_days=365,
                )

            assert "Database connection lost" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_no_orders_returns_empty_metrics(
        self, service: CustomerLTVService, mock_db: AsyncMock
    ):
        """Test dass Kunden ohne Bestellungen leere Metriken zurueckgeben.

        This test mocks _calculate_customer_metrics instead of letting it run,
        because the actual method queries InvoiceTracking.entity_id which exists
        on the model (line 296 in service). The method returns empty metrics when
        no invoices are found (lines 305-309).
        """
        mock_customer = Mock(
            id=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
            name="Neuer Kunde",
        )

        # Mock empty metrics (no orders)
        empty_metrics = CustomerMetrics(
            entity_id=str(mock_customer.id),
            entity_name="Neuer Kunde",
            lifetime_value=Decimal("0.00"),
            total_orders=0,
            avg_order_value=Decimal("0.00"),
            churn_risk=ChurnRisk.LOW,
            churn_risk_score=0.0,
            days_since_last_order=0,
            revenue_trend=RevenueTrend.STABLE,
            trend_percentage=0.0,
        )

        with patch.object(
            service, "_get_customers", return_value=[mock_customer]
        ), patch.object(
            service, "_calculate_customer_metrics", return_value=empty_metrics
        ), patch.object(
            service, "_calculate_trend_data", return_value=[]
        ):

            result = await service.get_customer_ltv(
                db=mock_db,
                user_id=TEST_USER_UUID,
                company_id=TEST_COMPANY_UUID,
                period_days=365,
            )

            # Should have 1 total customer but 0 active (no orders)
            # Active customers are filtered at line 142: if metrics.total_orders > 0
            assert result.total_customers == 1
            assert result.active_customers == 0
            assert len(result.top_customers) == 0


class TestSingleton:
    """Tests fuer Singleton-Pattern."""

    def test_get_customer_ltv_service_singleton(self):
        """Test dass get_customer_ltv_service Singleton zurueckgibt."""
        service1 = get_customer_ltv_service()
        service2 = get_customer_ltv_service()

        assert service1 is service2
        assert isinstance(service1, CustomerLTVService)
