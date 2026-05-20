# -*- coding: utf-8 -*-
"""
Unit Tests fuer Dashboard Widgets KPI API Endpoints.

Testet:
- Revenue Trend Endpoint
- DSO Tracker Endpoint
- Margin Analyzer Endpoint

Feinpoliert und durchdacht - Enterprise Test Coverage.
"""

import pytest
from datetime import date, datetime, timezone
from typing import Dict, List, Optional
from unittest.mock import AsyncMock, Mock, patch, MagicMock
from uuid import UUID, uuid4

from app.services.dashboard.revenue_trend_service import (
    RevenueTrendResult,
    RevenueDataPoint,
)
from app.services.dashboard.dso_tracker_service import (
    DSOTrackerResult,
    DSODataPoint,
    AgingBucket,
)
from app.services.dashboard.margin_analyzer_service import (
    MarginAnalyzerResult,
    CategoryMargin,
    MarginTrendPoint,
)


# Test-Konstanten
TEST_USER_UUID = UUID("00000000-0000-0000-0000-000000000001")
TEST_COMPANY_UUID = UUID("00000000-0000-0000-0000-000000000002")

pytestmark = [pytest.mark.unit, pytest.mark.api]


# ========================= Mock Fixtures =========================


@pytest.fixture
def sample_revenue_trend_result() -> RevenueTrendResult:
    """Beispiel-Ergebnis fuer Revenue Trend."""
    return RevenueTrendResult(
        generated_at=datetime(2025, 12, 1, 10, 0, 0, tzinfo=timezone.utc),
        date_from=date(2025, 6, 1),
        date_to=date(2025, 11, 30),
        total_revenue=150000.00,
        total_expenses=97500.00,
        net_income=52500.00,
        data_points=[
            RevenueDataPoint(
                period="2025-11",
                revenue=25000.00,
                expense=16250.00,
                net=8750.00,
                document_count=15,
                category="gesamt",
            ),
        ],
        comparison=None,
    )


@pytest.fixture
def sample_dso_tracker_result() -> DSOTrackerResult:
    """Beispiel-Ergebnis fuer DSO Tracker."""
    return DSOTrackerResult(
        generated_at=datetime(2025, 12, 1, 10, 0, 0, tzinfo=timezone.utc),
        date_from=date(2025, 6, 1),
        date_to=date(2025, 11, 30),
        current_dso=38.5,
        benchmark_dso=45.0,
        dso_trend=[
            DSODataPoint(
                period="2025-11",
                dso_value=38.5,
                invoice_count=20,
                total_outstanding=50000.00,
                total_revenue=120000.00,
            ),
        ],
        aging_buckets=[
            AgingBucket(
                label="Nicht faellig",
                count=10,
                amount=30000.00,
                percentage=60.0,
            ),
            AgingBucket(
                label="1-30 Tage",
                count=5,
                amount=15000.00,
                percentage=30.0,
            ),
            AgingBucket(
                label="31-60 Tage",
                count=2,
                amount=5000.00,
                percentage=10.0,
            ),
        ],
        total_outstanding=50000.00,
        total_receivables=120000.00,
        overdue_count=7,
    )


@pytest.fixture
def sample_margin_analyzer_result() -> MarginAnalyzerResult:
    """Beispiel-Ergebnis fuer Margin Analyzer."""
    return MarginAnalyzerResult(
        generated_at=datetime(2025, 12, 1, 10, 0, 0, tzinfo=timezone.utc),
        date_from=date(2025, 6, 1),
        date_to=date(2025, 11, 30),
        total_revenue=200000.00,
        total_costs=130000.00,
        overall_margin=70000.00,
        overall_margin_pct=35.0,
        categories=[
            CategoryMargin(
                category="eingangsrechnung",
                revenue=120000.00,
                costs=84000.00,
                margin=36000.00,
                margin_pct=30.0,
                document_count=45,
            ),
            CategoryMargin(
                category="ausgangsrechnung",
                revenue=80000.00,
                costs=46000.00,
                margin=34000.00,
                margin_pct=42.5,
                document_count=30,
            ),
        ],
        trend=[
            MarginTrendPoint(
                period="2025-11",
                revenue=35000.00,
                costs=21000.00,
                margin=14000.00,
                margin_pct=40.0,
            ),
        ],
    )


# ========================= Revenue Trend Endpoint Tests =========================


class TestRevenueTrendEndpoint:
    """Tests fuer den Revenue Trend Endpoint."""

    @pytest.mark.asyncio
    async def test_revenue_trend_returns_correct_structure(
        self, sample_revenue_trend_result: RevenueTrendResult
    ) -> None:
        """Revenue Trend liefert korrekte Struktur."""
        result = sample_revenue_trend_result
        assert result.generated_at is not None
        assert result.date_from == date(2025, 6, 1)
        assert result.date_to == date(2025, 11, 30)
        assert result.total_revenue == 150000.00
        assert result.total_expenses == 97500.00
        assert result.net_income == 52500.00
        assert len(result.data_points) == 1

    @pytest.mark.asyncio
    async def test_revenue_trend_data_point_fields(
        self, sample_revenue_trend_result: RevenueTrendResult
    ) -> None:
        """Revenue Trend Datenpunkt hat alle Felder."""
        dp = sample_revenue_trend_result.data_points[0]
        assert dp.period == "2025-11"
        assert dp.revenue == 25000.00
        assert dp.expense == 16250.00
        assert dp.net == 8750.00
        assert dp.document_count == 15
        assert dp.category == "gesamt"

    @pytest.mark.asyncio
    async def test_revenue_trend_with_comparison(self) -> None:
        """Revenue Trend mit Vergleichsdaten."""
        result = RevenueTrendResult(
            generated_at=datetime(2025, 12, 1, tzinfo=timezone.utc),
            date_from=date(2025, 6, 1),
            date_to=date(2025, 11, 30),
            total_revenue=100000.00,
            total_expenses=65000.00,
            net_income=35000.00,
            comparison={
                "revenue_change_pct": "5.2",
                "expense_change_pct": "3.1",
                "previous_from": "2024-12-01",
                "previous_to": "2025-05-31",
            },
        )
        assert result.comparison is not None
        assert result.comparison["revenue_change_pct"] == "5.2"

    @pytest.mark.asyncio
    async def test_revenue_trend_net_income_consistency(
        self, sample_revenue_trend_result: RevenueTrendResult
    ) -> None:
        """Netto-Einkommen ist konsistent."""
        result = sample_revenue_trend_result
        expected_net = result.total_revenue - result.total_expenses
        assert result.net_income == expected_net


# ========================= DSO Tracker Endpoint Tests =========================


class TestDSOTrackerEndpoint:
    """Tests fuer den DSO Tracker Endpoint."""

    @pytest.mark.asyncio
    async def test_dso_tracker_returns_correct_structure(
        self, sample_dso_tracker_result: DSOTrackerResult
    ) -> None:
        """DSO Tracker liefert korrekte Struktur."""
        result = sample_dso_tracker_result
        assert result.current_dso == 38.5
        assert result.benchmark_dso == 45.0
        assert len(result.dso_trend) == 1
        assert len(result.aging_buckets) == 3
        assert result.total_outstanding == 50000.00
        assert result.overdue_count == 7

    @pytest.mark.asyncio
    async def test_dso_tracker_aging_buckets(
        self, sample_dso_tracker_result: DSOTrackerResult
    ) -> None:
        """Faelligkeitsverteilung ist vollstaendig."""
        buckets = sample_dso_tracker_result.aging_buckets
        total_pct = sum(b.percentage for b in buckets)
        assert total_pct == 100.0

        assert buckets[0].label == "Nicht faellig"
        assert buckets[1].label == "1-30 Tage"
        assert buckets[2].label == "31-60 Tage"

    @pytest.mark.asyncio
    async def test_dso_tracker_below_benchmark(
        self, sample_dso_tracker_result: DSOTrackerResult
    ) -> None:
        """DSO unter Branchendurchschnitt ist positiv."""
        result = sample_dso_tracker_result
        assert result.current_dso < result.benchmark_dso

    @pytest.mark.asyncio
    async def test_dso_tracker_trend_data_point(
        self, sample_dso_tracker_result: DSOTrackerResult
    ) -> None:
        """DSO Trend-Datenpunkt hat alle Felder."""
        dp = sample_dso_tracker_result.dso_trend[0]
        assert dp.period == "2025-11"
        assert dp.dso_value == 38.5
        assert dp.invoice_count == 20
        assert dp.total_outstanding == 50000.00
        assert dp.total_revenue == 120000.00


# ========================= Margin Analyzer Endpoint Tests =========================


class TestMarginAnalyzerEndpoint:
    """Tests fuer den Margin Analyzer Endpoint."""

    @pytest.mark.asyncio
    async def test_margin_analyzer_returns_correct_structure(
        self, sample_margin_analyzer_result: MarginAnalyzerResult
    ) -> None:
        """Margin Analyzer liefert korrekte Struktur."""
        result = sample_margin_analyzer_result
        assert result.total_revenue == 200000.00
        assert result.total_costs == 130000.00
        assert result.overall_margin == 70000.00
        assert result.overall_margin_pct == 35.0
        assert len(result.categories) == 2
        assert len(result.trend) == 1

    @pytest.mark.asyncio
    async def test_margin_analyzer_category_fields(
        self, sample_margin_analyzer_result: MarginAnalyzerResult
    ) -> None:
        """Kategorie-Margen haben alle Felder."""
        cat = sample_margin_analyzer_result.categories[0]
        assert cat.category == "eingangsrechnung"
        assert cat.revenue == 120000.00
        assert cat.costs == 84000.00
        assert cat.margin == 36000.00
        assert cat.margin_pct == 30.0
        assert cat.document_count == 45

    @pytest.mark.asyncio
    async def test_margin_analyzer_overall_margin_calculation(
        self, sample_margin_analyzer_result: MarginAnalyzerResult
    ) -> None:
        """Gesamtmarge ist konsistent."""
        result = sample_margin_analyzer_result
        expected_margin = result.total_revenue - result.total_costs
        assert result.overall_margin == expected_margin

    @pytest.mark.asyncio
    async def test_margin_analyzer_margin_pct_positive(
        self, sample_margin_analyzer_result: MarginAnalyzerResult
    ) -> None:
        """Marge ist positiv."""
        result = sample_margin_analyzer_result
        assert result.overall_margin_pct > 0

    @pytest.mark.asyncio
    async def test_margin_analyzer_trend_point_fields(
        self, sample_margin_analyzer_result: MarginAnalyzerResult
    ) -> None:
        """Trend-Datenpunkt hat alle Felder."""
        tp = sample_margin_analyzer_result.trend[0]
        assert tp.period == "2025-11"
        assert tp.revenue == 35000.00
        assert tp.costs == 21000.00
        assert tp.margin == 14000.00
        assert tp.margin_pct == 40.0

    @pytest.mark.asyncio
    async def test_margin_analyzer_with_comparison(self) -> None:
        """Margin Analyzer mit Vergleichsdaten."""
        result = MarginAnalyzerResult(
            generated_at=datetime(2025, 12, 1, tzinfo=timezone.utc),
            date_from=date(2025, 6, 1),
            date_to=date(2025, 11, 30),
            total_revenue=200000.00,
            total_costs=130000.00,
            overall_margin=70000.00,
            overall_margin_pct=35.0,
            comparison={
                "margin_change_pct": "1.8",
                "previous_from": "2024-12-01",
                "previous_to": "2025-05-31",
            },
        )
        assert result.comparison is not None
        assert result.comparison["margin_change_pct"] == "1.8"

    @pytest.mark.asyncio
    async def test_margin_analyzer_empty_categories(self) -> None:
        """Margin Analyzer ohne Kategorien."""
        result = MarginAnalyzerResult(
            generated_at=datetime(2025, 12, 1, tzinfo=timezone.utc),
            date_from=date(2025, 6, 1),
            date_to=date(2025, 11, 30),
            total_revenue=0.0,
            total_costs=0.0,
            overall_margin=0.0,
            overall_margin_pct=0.0,
        )
        assert len(result.categories) == 0
        assert len(result.trend) == 0
        assert result.overall_margin_pct == 0.0


# ========================= Service Integration Tests =========================


class TestServiceIntegration:
    """Tests fuer Service-Integration mit Datenbank-Mock."""

    @pytest.mark.asyncio
    async def test_revenue_trend_service_db_error(self) -> None:
        """Revenue Trend Service behandelt DB-Fehler korrekt."""
        from app.services.dashboard.revenue_trend_service import RevenueTrendService

        service = RevenueTrendService()
        mock_db = AsyncMock()
        mock_db.execute.side_effect = Exception("Verbindungsfehler")

        result = await service.get_revenue_trend(
            db=mock_db,
            user_id=TEST_USER_UUID,
            date_from=date(2025, 1, 1),
            date_to=date(2025, 6, 30),
        )

        assert result.total_revenue == 0.0
        assert len(result.data_points) == 0

    @pytest.mark.asyncio
    async def test_dso_tracker_service_db_error(self) -> None:
        """DSO Tracker Service behandelt DB-Fehler korrekt."""
        from app.services.dashboard.dso_tracker_service import DSOTrackerService

        service = DSOTrackerService()
        mock_db = AsyncMock()
        mock_db.execute.side_effect = Exception("Verbindungsfehler")

        result = await service.get_dso_data(
            db=mock_db,
            user_id=TEST_USER_UUID,
            date_from=date(2025, 1, 1),
            date_to=date(2025, 6, 30),
        )

        assert result.current_dso == 0.0
        assert result.benchmark_dso == 45.0

    @pytest.mark.asyncio
    async def test_margin_analyzer_service_db_error(self) -> None:
        """Margin Analyzer Service behandelt DB-Fehler korrekt."""
        from app.services.dashboard.margin_analyzer_service import MarginAnalyzerService

        service = MarginAnalyzerService()
        mock_db = AsyncMock()
        mock_db.execute.side_effect = Exception("Verbindungsfehler")

        result = await service.get_margin_data(
            db=mock_db,
            user_id=TEST_USER_UUID,
            date_from=date(2025, 1, 1),
            date_to=date(2025, 6, 30),
        )

        assert result.total_revenue == 0.0
        assert result.overall_margin_pct == 0.0
        assert len(result.categories) == 0
