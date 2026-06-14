# -*- coding: utf-8 -*-
"""
Unit-Tests fuer DSO Tracker Service.

Testet:
- DSO-Berechnung (Days Sales Outstanding)
- 6-Monats-Trend
- Faelligkeitsverteilung (Aging Buckets)
- Periodenvergleich (previous_period, yoy)
- Ausstehende Forderungen
- Fehlerbehandlung

Feinpoliert und durchdacht - DSO Tracker Service Tests.
"""

import pytest
from datetime import date, datetime, timezone
from typing import List, Dict
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

from app.services.dashboard.dso_tracker_service import (
    DSOTrackerService,
    DSOTrackerResult,
    DSODataPoint,
    AgingBucket,
    get_dso_tracker_service,
)


# Test-Konstanten
TEST_USER_UUID = UUID("00000000-0000-0000-0000-000000000001")
TEST_COMPANY_UUID = UUID("00000000-0000-0000-0000-000000000002")

pytestmark = [pytest.mark.unit]


# ========================= Fixtures =========================


@pytest.fixture
def service() -> DSOTrackerService:
    """Erstelle DSOTrackerService-Instanz."""
    return DSOTrackerService()


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


def _make_db_scalar(value: float) -> MagicMock:
    """Erstelle Mock-Ergebnis mit Skalar-Wert."""
    mock_result = MagicMock()
    mock_result.scalar.return_value = value
    return mock_result


def _make_db_one_or_none(data: tuple) -> MagicMock:
    """Erstelle Mock-Ergebnis mit single row."""
    mock_result = MagicMock()
    mock_result.one_or_none.return_value = data
    return mock_result


# ========================= Service Tests =========================


class TestDSOTrackerService:
    """Tests fuer DSOTrackerService."""

    @pytest.mark.asyncio
    async def test_get_dso_data_success(
        self, service: DSOTrackerService, mock_db: AsyncMock
    ) -> None:
        """DSO-Daten erfolgreich abrufen mit allen Metriken."""
        # Mock alle 4 privaten Methoden
        with patch.object(
            DSOTrackerService, '_calculate_current_dso', return_value=42.5
        ), patch.object(
            DSOTrackerService, '_calculate_dso_trend', return_value=[
                DSODataPoint(
                    period="2025-07",
                    dso_value=45.2,
                    invoice_count=10,
                    total_outstanding=5000.0,
                    total_revenue=12000.0,
                ),
                DSODataPoint(
                    period="2025-08",
                    dso_value=40.1,
                    invoice_count=12,
                    total_outstanding=4800.0,
                    total_revenue=15000.0,
                ),
            ]
        ), patch.object(
            DSOTrackerService, '_calculate_aging_buckets', return_value=[
                AgingBucket(label="Nicht faellig", count=5, amount=2000.0, percentage=40.0),
                AgingBucket(label="1-30 Tage", count=3, amount=1500.0, percentage=30.0),
                AgingBucket(label="31-60 Tage", count=2, amount=1000.0, percentage=20.0),
            ]
        ), patch.object(
            DSOTrackerService, '_get_outstanding_stats', return_value={
                "total_outstanding": 5000.0,
                "total_receivables": 8000.0,
                "overdue_count": 3,
            }
        ):
            result = await service.get_dso_data(
                db=mock_db,
                user_id=TEST_USER_UUID,
                date_from=date(2025, 7, 1),
                date_to=date(2025, 8, 31),
            )

        assert isinstance(result, DSOTrackerResult)
        assert result.current_dso == 42.5
        assert result.benchmark_dso == 45.0
        assert len(result.dso_trend) == 2
        assert len(result.aging_buckets) == 3
        assert result.total_outstanding == 5000.0
        assert result.total_receivables == 8000.0
        assert result.overdue_count == 3
        assert result.comparison is None

    @pytest.mark.asyncio
    async def test_get_dso_data_empty(
        self, service: DSOTrackerService, mock_db: AsyncMock
    ) -> None:
        """DSO-Daten ohne Ergebnisse."""
        # Mock alle 4 privaten Methoden mit leeren Ergebnissen
        with patch.object(
            DSOTrackerService, '_calculate_current_dso', return_value=0.0
        ), patch.object(
            DSOTrackerService, '_calculate_dso_trend', return_value=[]
        ), patch.object(
            DSOTrackerService, '_calculate_aging_buckets', return_value=[]
        ), patch.object(
            DSOTrackerService, '_get_outstanding_stats', return_value={
                "total_outstanding": 0.0,
                "total_receivables": 0.0,
                "overdue_count": 0,
            }
        ):
            result = await service.get_dso_data(
                db=mock_db,
                user_id=TEST_USER_UUID,
                date_from=date(2025, 1, 1),
                date_to=date(2025, 6, 30),
            )

        assert isinstance(result, DSOTrackerResult)
        assert result.current_dso == 0.0
        assert len(result.dso_trend) == 0
        assert len(result.aging_buckets) == 0
        assert result.total_outstanding == 0.0
        assert result.total_receivables == 0.0
        assert result.overdue_count == 0

    @pytest.mark.asyncio
    async def test_get_dso_data_with_company_filter(
        self, service: DSOTrackerService, mock_db: AsyncMock
    ) -> None:
        """DSO-Daten mit Company-Filter."""
        with patch.object(
            DSOTrackerService, '_calculate_current_dso', return_value=38.5
        ), patch.object(
            DSOTrackerService, '_calculate_dso_trend', return_value=[]
        ), patch.object(
            DSOTrackerService, '_calculate_aging_buckets', return_value=[]
        ), patch.object(
            DSOTrackerService, '_get_outstanding_stats', return_value={
                "total_outstanding": 1000.0,
                "total_receivables": 2000.0,
                "overdue_count": 1,
            }
        ):
            result = await service.get_dso_data(
                db=mock_db,
                user_id=TEST_USER_UUID,
                company_id=TEST_COMPANY_UUID,
            )

        assert isinstance(result, DSOTrackerResult)
        assert result.current_dso == 38.5

    @pytest.mark.asyncio
    async def test_get_dso_data_with_comparison_previous(
        self, service: DSOTrackerService, mock_db: AsyncMock
    ) -> None:
        """DSO-Daten mit Vorperioden-Vergleich."""
        with patch.object(
            DSOTrackerService, '_calculate_current_dso', return_value=42.0
        ), patch.object(
            DSOTrackerService, '_calculate_dso_trend', return_value=[]
        ), patch.object(
            DSOTrackerService, '_calculate_aging_buckets', return_value=[]
        ), patch.object(
            DSOTrackerService, '_get_outstanding_stats', return_value={
                "total_outstanding": 0.0,
                "total_receivables": 0.0,
                "overdue_count": 0,
            }
        ):
            result = await service.get_dso_data(
                db=mock_db,
                user_id=TEST_USER_UUID,
                date_from=date(2025, 10, 1),
                date_to=date(2025, 10, 31),
                compare_period="previous_period",
            )

        assert result.comparison is not None
        assert "dso_change_days" in result.comparison
        assert "previous_from" in result.comparison
        assert "previous_to" in result.comparison
        # Vorperiode ist 1 Monat zurueck
        assert result.comparison["previous_from"] == "2025-09-01"
        assert result.comparison["previous_to"] == "2025-09-30"

    @pytest.mark.asyncio
    async def test_get_dso_data_with_comparison_yoy(
        self, service: DSOTrackerService, mock_db: AsyncMock
    ) -> None:
        """DSO-Daten mit Year-over-Year Vergleich."""
        with patch.object(
            DSOTrackerService, '_calculate_current_dso', return_value=44.5
        ), patch.object(
            DSOTrackerService, '_calculate_dso_trend', return_value=[]
        ), patch.object(
            DSOTrackerService, '_calculate_aging_buckets', return_value=[]
        ), patch.object(
            DSOTrackerService, '_get_outstanding_stats', return_value={
                "total_outstanding": 0.0,
                "total_receivables": 0.0,
                "overdue_count": 0,
            }
        ):
            result = await service.get_dso_data(
                db=mock_db,
                user_id=TEST_USER_UUID,
                date_from=date(2025, 10, 1),
                date_to=date(2025, 10, 31),
                compare_period="yoy",
            )

        assert result.comparison is not None
        assert "dso_change_days" in result.comparison
        assert "previous_from" in result.comparison
        assert "previous_to" in result.comparison
        # Vorjahresperiode
        assert result.comparison["previous_from"] == "2024-10-01"
        assert result.comparison["previous_to"] == "2024-10-31"

    @pytest.mark.asyncio
    async def test_aging_buckets_calculation(
        self, service: DSOTrackerService, mock_db: AsyncMock
    ) -> None:
        """Faelligkeitsverteilung korrekt berechnen."""
        # Mock db.execute fuer aging buckets query
        rows = [
            ("nicht_fällig", 5, 2500.0),
            ("1_30_tage", 3, 1500.0),
            ("31_60_tage", 2, 1000.0),
            ("61_90_tage", 1, 500.0),
            ("über_90_tage", 1, 500.0),
        ]
        mock_db.execute.return_value = _make_db_rows(rows)

        result = await service._calculate_aging_buckets(
            db=mock_db,
            company_id=None,
            reference_date=date(2025, 10, 1),
        )

        assert len(result) == 5
        assert result[0].label == "Nicht fällig"
        assert result[0].count == 5
        assert result[0].amount == 2500.0
        assert result[0].percentage == pytest.approx(41.7, rel=0.1)

        assert result[1].label == "1-30 Tage"
        assert result[1].count == 3
        assert result[1].amount == 1500.0
        assert result[1].percentage == 25.0

        assert result[4].label == "Über 90 Tage"
        assert result[4].count == 1
        assert result[4].amount == 500.0
        assert result[4].percentage == pytest.approx(8.3, rel=0.1)

    @pytest.mark.asyncio
    async def test_outstanding_stats(
        self, service: DSOTrackerService, mock_db: AsyncMock
    ) -> None:
        """Ausstehende Forderungen Statistiken."""
        # Mock db.execute fuer outstanding stats query
        row = (5000.0, 8000.0, 3)
        mock_db.execute.return_value = _make_db_one_or_none(row)

        result = await service._get_outstanding_stats(
            db=mock_db,
            company_id=None,
            reference_date=date(2025, 10, 1),
        )

        assert result["total_outstanding"] == 5000.0
        assert result["total_receivables"] == 8000.0
        assert result["overdue_count"] == 3

    @pytest.mark.asyncio
    async def test_get_dso_data_db_error(
        self, service: DSOTrackerService, mock_db: AsyncMock
    ) -> None:
        """Fehlerbehandlung bei Datenbankfehler."""
        # _calculate_current_dso wirft Exception
        with patch.object(
            DSOTrackerService, '_calculate_current_dso',
            side_effect=Exception("Datenbankfehler")
        ):
            result = await service.get_dso_data(
                db=mock_db,
                user_id=TEST_USER_UUID,
                date_from=date(2025, 1, 1),
                date_to=date(2025, 6, 30),
            )

        assert isinstance(result, DSOTrackerResult)
        assert result.current_dso == 0.0
        assert len(result.dso_trend) == 0
        assert len(result.aging_buckets) == 0
        assert result.total_outstanding == 0.0
        assert result.total_receivables == 0.0
        assert result.overdue_count == 0

    @pytest.mark.asyncio
    async def test_calculate_current_dso_with_revenue(
        self, service: DSOTrackerService, mock_db: AsyncMock
    ) -> None:
        """DSO-Berechnung mit Umsatz."""
        # Mock 2 queries: total_revenue, total_outstanding
        mock_db.execute.side_effect = [
            _make_db_scalar(10000.0),  # total_revenue
            _make_db_scalar(3000.0),   # total_outstanding
        ]

        result = await service._calculate_current_dso(
            db=mock_db,
            company_id=None,
            reference_date=date(2025, 10, 1),
        )

        # DSO = (3000 / 10000) * 90 = 27.0
        assert result == 27.0

    @pytest.mark.asyncio
    async def test_calculate_current_dso_no_revenue(
        self, service: DSOTrackerService, mock_db: AsyncMock
    ) -> None:
        """DSO-Berechnung ohne Umsatz."""
        # Mock 2 queries: total_revenue = 0
        mock_db.execute.side_effect = [
            _make_db_scalar(0.0),  # total_revenue
            _make_db_scalar(0.0),  # total_outstanding
        ]

        result = await service._calculate_current_dso(
            db=mock_db,
            company_id=None,
            reference_date=date(2025, 10, 1),
        )

        # DSO = 0 wenn kein Umsatz
        assert result == 0.0

    @pytest.mark.asyncio
    async def test_calculate_dso_trend_with_data(
        self, service: DSOTrackerService, mock_db: AsyncMock
    ) -> None:
        """DSO-Trend mit Daten."""
        rows = [
            ("2025-07", 10, 12000.0, 3600.0),
            ("2025-08", 12, 15000.0, 3000.0),
            ("2025-09", 8, 10000.0, 2000.0),
        ]
        mock_db.execute.return_value = _make_db_rows(rows)

        result = await service._calculate_dso_trend(
            db=mock_db,
            company_id=None,
            date_from=date(2025, 7, 1),
            date_to=date(2025, 9, 30),
        )

        assert len(result) == 3
        assert result[0].period == "2025-07"
        assert result[0].invoice_count == 10
        assert result[0].total_revenue == 12000.0
        assert result[0].total_outstanding == 3600.0
        # DSO = (3600 / 12000) * 30 = 9.0
        assert result[0].dso_value == 9.0

        assert result[1].period == "2025-08"
        # DSO = (3000 / 15000) * 30 = 6.0
        assert result[1].dso_value == 6.0

    @pytest.mark.asyncio
    async def test_calculate_dso_trend_zero_revenue(
        self, service: DSOTrackerService, mock_db: AsyncMock
    ) -> None:
        """DSO-Trend mit Nullumsatz in einem Monat."""
        rows = [
            ("2025-07", 0, 0.0, 0.0),
        ]
        mock_db.execute.return_value = _make_db_rows(rows)

        result = await service._calculate_dso_trend(
            db=mock_db,
            company_id=None,
            date_from=date(2025, 7, 1),
            date_to=date(2025, 7, 31),
        )

        assert len(result) == 1
        assert result[0].dso_value == 0.0

    @pytest.mark.asyncio
    async def test_build_comparison_unknown_period(
        self, service: DSOTrackerService
    ) -> None:
        """Unbekannter Vergleichszeitraum liefert None."""
        result = service._build_comparison(
            compare_period="unknown",
            date_from=date(2025, 10, 1),
            date_to=date(2025, 10, 31),
            current_dso=42.0,
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_build_comparison_none_period(
        self, service: DSOTrackerService
    ) -> None:
        """Kein Vergleichszeitraum liefert None."""
        result = service._build_comparison(
            compare_period=None,
            date_from=date(2025, 10, 1),
            date_to=date(2025, 10, 31),
            current_dso=42.0,
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_get_outstanding_stats_none_result(
        self, service: DSOTrackerService, mock_db: AsyncMock
    ) -> None:
        """Ausstehende Statistiken bei None-Ergebnis."""
        mock_db.execute.return_value = _make_db_one_or_none(None)

        result = await service._get_outstanding_stats(
            db=mock_db,
            company_id=None,
            reference_date=date(2025, 10, 1),
        )

        assert result["total_outstanding"] == 0.0
        assert result["total_receivables"] == 0.0
        assert result["overdue_count"] == 0


# ========================= Singleton Tests =========================


class TestDSOTrackerServiceSingleton:
    """Tests fuer Singleton-Pattern."""

    def test_get_dso_tracker_service_returns_instance(self) -> None:
        """Singleton liefert Instanz."""
        service = get_dso_tracker_service()
        assert isinstance(service, DSOTrackerService)

    def test_get_dso_tracker_service_returns_same_instance(self) -> None:
        """Singleton liefert gleiche Instanz."""
        service1 = get_dso_tracker_service()
        service2 = get_dso_tracker_service()
        assert service1 is service2
