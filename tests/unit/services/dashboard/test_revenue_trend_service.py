# -*- coding: utf-8 -*-
"""
Unit-Tests fuer Revenue Trend Service.

Testet:
- Umsatz-Trend-Berechnung
- Periodenvergleich (previous_period, yoy)
- Standard-Datumsbereich
- Fehlerbehandlung
- Leere Ergebnisse

Feinpoliert und durchdacht - Revenue Trend Service Tests.
"""

import pytest
from datetime import date, datetime, timezone
from typing import List, Optional
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

from app.services.dashboard.revenue_trend_service import (
    RevenueTrendService,
    RevenueTrendResult,
    RevenueDataPoint,
    get_revenue_trend_service,
)


# Test-Konstanten
TEST_USER_UUID = UUID("00000000-0000-0000-0000-000000000001")
TEST_COMPANY_UUID = UUID("00000000-0000-0000-0000-000000000002")

pytestmark = [pytest.mark.unit]


# ========================= Fixtures =========================


@pytest.fixture
def service() -> RevenueTrendService:
    """Erstelle RevenueTrendService-Instanz."""
    return RevenueTrendService()


@pytest.fixture
def mock_db() -> AsyncMock:
    """Erstelle Mock-Datenbank-Session."""
    db = AsyncMock()
    return db


def _make_db_rows(data: List[tuple]) -> MagicMock:
    """Erstelle Mock-Ergebnis mit Zeilen."""
    mock_result = MagicMock()
    mock_result.all.return_value = data
    return mock_result


# ========================= Service Tests =========================


class TestRevenueTrendService:
    """Tests fuer RevenueTrendService."""

    @pytest.mark.asyncio
    async def test_get_revenue_trend_with_data(
        self, service: RevenueTrendService, mock_db: AsyncMock
    ) -> None:
        """Umsatz-Trend mit vorhandenen Daten."""
        rows = [
            ("2025-07", 0.85, 12),
            ("2025-08", 0.92, 15),
            ("2025-09", 0.78, 10),
        ]
        mock_db.execute.return_value = _make_db_rows(rows)

        result = await service.get_revenue_trend(
            db=mock_db,
            user_id=TEST_USER_UUID,
            date_from=date(2025, 7, 1),
            date_to=date(2025, 9, 30),
        )

        assert isinstance(result, RevenueTrendResult)
        assert len(result.data_points) == 3
        assert result.total_revenue > 0
        assert result.total_expenses > 0
        assert result.net_income > 0
        assert result.comparison is None

    @pytest.mark.asyncio
    async def test_get_revenue_trend_empty_data(
        self, service: RevenueTrendService, mock_db: AsyncMock
    ) -> None:
        """Umsatz-Trend ohne Daten."""
        mock_db.execute.return_value = _make_db_rows([])

        result = await service.get_revenue_trend(
            db=mock_db,
            user_id=TEST_USER_UUID,
            date_from=date(2025, 1, 1),
            date_to=date(2025, 6, 30),
        )

        assert isinstance(result, RevenueTrendResult)
        assert len(result.data_points) == 0
        assert result.total_revenue == 0.0
        assert result.total_expenses == 0.0
        assert result.net_income == 0.0

    @pytest.mark.asyncio
    async def test_get_revenue_trend_default_dates(
        self, service: RevenueTrendService, mock_db: AsyncMock
    ) -> None:
        """Umsatz-Trend mit Standard-Datumsbereich."""
        mock_db.execute.return_value = _make_db_rows([])

        result = await service.get_revenue_trend(
            db=mock_db,
            user_id=TEST_USER_UUID,
        )

        assert isinstance(result, RevenueTrendResult)
        assert result.date_from is not None
        assert result.date_to is not None
        assert result.date_from < result.date_to

    @pytest.mark.asyncio
    async def test_get_revenue_trend_previous_period_comparison(
        self, service: RevenueTrendService, mock_db: AsyncMock
    ) -> None:
        """Umsatz-Trend mit Vorperioden-Vergleich."""
        rows = [("2025-10", 0.90, 8)]
        mock_db.execute.return_value = _make_db_rows(rows)

        result = await service.get_revenue_trend(
            db=mock_db,
            user_id=TEST_USER_UUID,
            date_from=date(2025, 10, 1),
            date_to=date(2025, 10, 31),
            compare_period="previous_period",
        )

        assert result.comparison is not None
        assert "revenue_change_pct" in result.comparison
        assert "expense_change_pct" in result.comparison
        assert "previous_from" in result.comparison
        assert "previous_to" in result.comparison

    @pytest.mark.asyncio
    async def test_get_revenue_trend_yoy_comparison(
        self, service: RevenueTrendService, mock_db: AsyncMock
    ) -> None:
        """Umsatz-Trend mit Year-over-Year Vergleich."""
        rows = [("2025-10", 0.90, 8)]
        mock_db.execute.return_value = _make_db_rows(rows)

        result = await service.get_revenue_trend(
            db=mock_db,
            user_id=TEST_USER_UUID,
            date_from=date(2025, 10, 1),
            date_to=date(2025, 10, 31),
            compare_period="yoy",
        )

        assert result.comparison is not None
        assert "revenue_change_pct" in result.comparison
        assert "previous_from" in result.comparison

    @pytest.mark.asyncio
    async def test_get_revenue_trend_with_company_id(
        self, service: RevenueTrendService, mock_db: AsyncMock
    ) -> None:
        """Umsatz-Trend mit Company-Filter."""
        mock_db.execute.return_value = _make_db_rows([])

        result = await service.get_revenue_trend(
            db=mock_db,
            user_id=TEST_USER_UUID,
            company_id=TEST_COMPANY_UUID,
        )

        assert isinstance(result, RevenueTrendResult)
        mock_db.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_revenue_trend_data_point_structure(
        self, service: RevenueTrendService, mock_db: AsyncMock
    ) -> None:
        """Datenpunkt-Struktur pruefen."""
        rows = [("2025-11", 0.95, 20)]
        mock_db.execute.return_value = _make_db_rows(rows)

        result = await service.get_revenue_trend(
            db=mock_db,
            user_id=TEST_USER_UUID,
            date_from=date(2025, 11, 1),
            date_to=date(2025, 11, 30),
        )

        assert len(result.data_points) == 1
        dp = result.data_points[0]
        assert dp.period == "2025-11"
        assert dp.revenue > 0
        assert dp.expense > 0
        assert dp.net == dp.revenue - dp.expense
        assert dp.document_count == 20
        assert dp.category == "gesamt"

    @pytest.mark.asyncio
    async def test_get_revenue_trend_error_handling(
        self, service: RevenueTrendService, mock_db: AsyncMock
    ) -> None:
        """Fehlerbehandlung bei Datenbankfehler."""
        mock_db.execute.side_effect = Exception("Datenbankfehler")

        result = await service.get_revenue_trend(
            db=mock_db,
            user_id=TEST_USER_UUID,
            date_from=date(2025, 1, 1),
            date_to=date(2025, 6, 30),
        )

        assert isinstance(result, RevenueTrendResult)
        assert result.total_revenue == 0.0
        assert result.total_expenses == 0.0
        assert result.net_income == 0.0
        assert len(result.data_points) == 0

    @pytest.mark.asyncio
    async def test_get_revenue_trend_net_calculation(
        self, service: RevenueTrendService, mock_db: AsyncMock
    ) -> None:
        """Netto-Berechnung korrekt."""
        rows = [("2025-12", 1.0, 5)]
        mock_db.execute.return_value = _make_db_rows(rows)

        result = await service.get_revenue_trend(
            db=mock_db,
            user_id=TEST_USER_UUID,
            date_from=date(2025, 12, 1),
            date_to=date(2025, 12, 31),
        )

        assert result.net_income == round(
            result.total_revenue - result.total_expenses, 2
        )

    @pytest.mark.asyncio
    async def test_get_revenue_trend_unknown_compare_period(
        self, service: RevenueTrendService, mock_db: AsyncMock
    ) -> None:
        """Unbekannter Vergleichszeitraum liefert None."""
        mock_db.execute.return_value = _make_db_rows([])

        result = await service.get_revenue_trend(
            db=mock_db,
            user_id=TEST_USER_UUID,
            compare_period="unknown",
        )

        assert result.comparison is None


# ========================= Singleton Tests =========================


class TestRevenueTrendServiceSingleton:
    """Tests fuer Singleton-Pattern."""

    def test_get_revenue_trend_service_returns_instance(self) -> None:
        """Singleton liefert Instanz."""
        service = get_revenue_trend_service()
        assert isinstance(service, RevenueTrendService)

    def test_get_revenue_trend_service_returns_same_instance(self) -> None:
        """Singleton liefert gleiche Instanz."""
        service1 = get_revenue_trend_service()
        service2 = get_revenue_trend_service()
        assert service1 is service2
