# -*- coding: utf-8 -*-
"""Unit Tests fuer MarginAnalyzerService.

Enterprise Feature: Februar 2026
"""

from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Dict, List
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

import pytest

from app.services.dashboard.margin_analyzer_service import (
    MarginAnalyzerService,
    MarginAnalyzerResult,
    CategoryMargin,
    MarginTrendPoint,
    get_margin_analyzer_service,
)

pytestmark = [pytest.mark.unit]

# Test Constants
TEST_USER_UUID: UUID = UUID("12345678-1234-5678-1234-567812345678")
TEST_COMPANY_UUID: UUID = UUID("87654321-4321-8765-4321-876543218765")


def _make_db_rows(data: List[tuple]) -> AsyncMock:
    """Erstelle Mock DB Result mit Rows."""
    result_mock = AsyncMock()
    result_mock.all.return_value = data
    return result_mock


@pytest.fixture
def service() -> MarginAnalyzerService:
    """MarginAnalyzerService Instanz."""
    return MarginAnalyzerService()


@pytest.fixture
def mock_db() -> AsyncMock:
    """Mock AsyncSession."""
    return AsyncMock()


class TestMarginAnalyzerService:
    """Tests fuer MarginAnalyzerService Core-Funktionen."""

    @pytest.mark.asyncio
    async def test_get_margin_data_success(
        self, service: MarginAnalyzerService, mock_db: AsyncMock
    ) -> None:
        """Test get_margin_data liefert valide Margen-Daten."""
        # Mock category margins
        mock_categories = [
            CategoryMargin(
                category="eingangsrechnung",
                revenue=10000.0,
                costs=7000.0,
                margin=3000.0,
                margin_pct=30.0,
                document_count=5,
            ),
            CategoryMargin(
                category="ausgangsrechnung",
                revenue=15000.0,
                costs=6000.0,
                margin=9000.0,
                margin_pct=60.0,
                document_count=8,
            ),
        ]

        # Mock trend
        mock_trend = [
            MarginTrendPoint(
                period="2026-01",
                revenue=8000.0,
                costs=4800.0,
                margin=3200.0,
                margin_pct=40.0,
            ),
            MarginTrendPoint(
                period="2026-02",
                revenue=17000.0,
                costs=10200.0,
                margin=6800.0,
                margin_pct=40.0,
            ),
        ]

        with patch.object(
            service, "_calculate_category_margins", return_value=mock_categories
        ), patch.object(service, "_calculate_margin_trend", return_value=mock_trend):
            result = await service.get_margin_data(
                mock_db,
                TEST_USER_UUID,
                company_id=TEST_COMPANY_UUID,
                date_from=date(2026, 1, 1),
                date_to=date(2026, 2, 10),
            )

        assert isinstance(result, MarginAnalyzerResult)
        assert result.total_revenue > 0
        assert result.total_costs > 0
        assert result.overall_margin > 0
        assert result.overall_margin_pct > 0
        assert result.total_revenue == 25000.0  # 10000 + 15000
        assert result.total_costs == 13000.0  # 7000 + 6000
        assert result.overall_margin == 12000.0  # 25000 - 13000
        assert result.overall_margin_pct == 48.0  # (12000/25000)*100
        assert len(result.categories) == 2
        assert len(result.trend) == 2

    @pytest.mark.asyncio
    async def test_get_margin_data_empty(
        self, service: MarginAnalyzerService, mock_db: AsyncMock
    ) -> None:
        """Test get_margin_data ohne Dokumente liefert Nullwerte."""
        with patch.object(
            service, "_calculate_category_margins", return_value=[]
        ), patch.object(service, "_calculate_margin_trend", return_value=[]):
            result = await service.get_margin_data(
                mock_db,
                TEST_USER_UUID,
                date_from=date(2026, 1, 1),
                date_to=date(2026, 2, 10),
            )

        assert result.total_revenue == 0.0
        assert result.total_costs == 0.0
        assert result.overall_margin == 0.0
        assert result.overall_margin_pct == 0.0
        assert len(result.categories) == 0
        assert len(result.trend) == 0

    @pytest.mark.asyncio
    async def test_category_margins(
        self, service: MarginAnalyzerService, mock_db: AsyncMock
    ) -> None:
        """Test _calculate_category_margins wendet COST_RATIOS korrekt an."""
        # Mock DB rows: (category, revenue_proxy, doc_count)
        mock_rows = [
            ("eingangsrechnung", 10.0, 5),  # revenue_proxy * 1000 = 10000
            ("ausgangsrechnung", 8.0, 3),  # revenue_proxy * 1000 = 8000
            ("sonstige", 5.0, 2),  # revenue_proxy * 1000 = 5000
        ]

        mock_db.execute.return_value = _make_db_rows(mock_rows)

        categories = await service._calculate_category_margins(
            mock_db, TEST_USER_UUID, date(2026, 1, 1), date(2026, 2, 10)
        )

        assert len(categories) == 3

        # Eingangsrechnung: revenue=10000, costs=10000*0.70=7000
        cat_ein = categories[0]
        assert cat_ein.category == "eingangsrechnung"
        assert cat_ein.revenue == 10000.0
        assert cat_ein.costs == 7000.0  # 0.70 ratio
        assert cat_ein.margin == 3000.0
        assert cat_ein.margin_pct == 30.0
        assert cat_ein.document_count == 5

        # Ausgangsrechnung: revenue=8000, costs=8000*0.40=3200
        cat_aus = categories[1]
        assert cat_aus.category == "ausgangsrechnung"
        assert cat_aus.revenue == 8000.0
        assert cat_aus.costs == 3200.0  # 0.40 ratio
        assert cat_aus.margin == 4800.0
        assert cat_aus.margin_pct == 60.0
        assert cat_aus.document_count == 3

        # Sonstige: revenue=5000, costs=5000*0.60=3000 (default ratio)
        cat_sonstige = categories[2]
        assert cat_sonstige.category == "sonstige"
        assert cat_sonstige.revenue == 5000.0
        assert cat_sonstige.costs == 3000.0  # 0.60 default ratio
        assert cat_sonstige.margin == 2000.0
        assert cat_sonstige.margin_pct == 40.0
        assert cat_sonstige.document_count == 2

    @pytest.mark.asyncio
    async def test_margin_trend_monthly(
        self, service: MarginAnalyzerService, mock_db: AsyncMock
    ) -> None:
        """Test _calculate_margin_trend liefert monatliche Trend-Punkte."""
        # Mock DB rows: (period, revenue_proxy)
        mock_rows = [
            ("2026-01", 10.0),  # revenue = 10000, costs = 6000 (default 0.60)
            ("2026-02", 15.0),  # revenue = 15000, costs = 9000
        ]

        mock_db.execute.return_value = _make_db_rows(mock_rows)

        trend = await service._calculate_margin_trend(
            mock_db, TEST_USER_UUID, date(2026, 1, 1), date(2026, 2, 28)
        )

        assert len(trend) == 2

        # Januar
        jan = trend[0]
        assert jan.period == "2026-01"
        assert jan.revenue == 10000.0
        assert jan.costs == 6000.0  # 10000 * 0.60
        assert jan.margin == 4000.0
        assert jan.margin_pct == 40.0

        # Februar
        feb = trend[1]
        assert feb.period == "2026-02"
        assert feb.revenue == 15000.0
        assert feb.costs == 9000.0  # 15000 * 0.60
        assert feb.margin == 6000.0
        assert feb.margin_pct == 40.0

    @pytest.mark.asyncio
    async def test_comparison_previous_period(
        self, service: MarginAnalyzerService, mock_db: AsyncMock
    ) -> None:
        """Test get_margin_data mit compare_period=previous_period."""
        mock_categories = [
            CategoryMargin(
                category="test",
                revenue=10000.0,
                costs=6000.0,
                margin=4000.0,
                margin_pct=40.0,
                document_count=5,
            )
        ]

        with patch.object(
            service, "_calculate_category_margins", return_value=mock_categories
        ), patch.object(service, "_calculate_margin_trend", return_value=[]):
            result = await service.get_margin_data(
                mock_db,
                TEST_USER_UUID,
                date_from=date(2026, 1, 1),
                date_to=date(2026, 1, 31),
                compare_period="previous_period",
            )

        assert result.comparison is not None
        assert "margin_change_pct" in result.comparison
        assert "previous_from" in result.comparison
        assert "previous_to" in result.comparison
        assert float(result.comparison["margin_change_pct"]) == 1.8
        # Previous period should be 30 days before date_from
        assert result.comparison["previous_from"] == "2025-12-02"
        assert result.comparison["previous_to"] == "2025-12-31"

    @pytest.mark.asyncio
    async def test_comparison_yoy(
        self, service: MarginAnalyzerService, mock_db: AsyncMock
    ) -> None:
        """Test get_margin_data mit compare_period=yoy."""
        mock_categories = [
            CategoryMargin(
                category="test",
                revenue=10000.0,
                costs=6000.0,
                margin=4000.0,
                margin_pct=40.0,
                document_count=5,
            )
        ]

        with patch.object(
            service, "_calculate_category_margins", return_value=mock_categories
        ), patch.object(service, "_calculate_margin_trend", return_value=[]):
            result = await service.get_margin_data(
                mock_db,
                TEST_USER_UUID,
                date_from=date(2026, 1, 1),
                date_to=date(2026, 1, 31),
                compare_period="yoy",
            )

        assert result.comparison is not None
        assert "margin_change_pct" in result.comparison
        assert "previous_from" in result.comparison
        assert "previous_to" in result.comparison
        assert float(result.comparison["margin_change_pct"]) == 3.5
        # YoY comparison should be exactly 1 year before
        assert result.comparison["previous_from"] == "2025-01-01"
        assert result.comparison["previous_to"] == "2025-01-31"

    @pytest.mark.asyncio
    async def test_db_error_resilience(
        self, service: MarginAnalyzerService, mock_db: AsyncMock
    ) -> None:
        """Test get_margin_data liefert Nullwerte bei DB-Fehler."""
        with patch.object(
            service,
            "_calculate_category_margins",
            side_effect=Exception("DB connection error"),
        ):
            result = await service.get_margin_data(
                mock_db,
                TEST_USER_UUID,
                date_from=date(2026, 1, 1),
                date_to=date(2026, 2, 10),
            )

        # Should return zeros on error
        assert result.total_revenue == 0.0
        assert result.total_costs == 0.0
        assert result.overall_margin == 0.0
        assert result.overall_margin_pct == 0.0
        assert len(result.categories) == 0
        assert len(result.trend) == 0


class TestMarginAnalyzerServiceSingleton:
    """Tests fuer MarginAnalyzerService Singleton."""

    def test_singleton_returns_same_instance(self) -> None:
        """Test get_margin_analyzer_service liefert immer dieselbe Instanz."""
        service1 = get_margin_analyzer_service()
        service2 = get_margin_analyzer_service()

        assert service1 is service2
        assert isinstance(service1, MarginAnalyzerService)
