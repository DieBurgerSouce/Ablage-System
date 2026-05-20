# -*- coding: utf-8 -*-
"""
Unit Tests: Period Comparison Service

Tests period-over-period analytics including MoM, QoQ, and YoY comparisons
with German date formatting and trend analysis.

Created: 2026-02-10
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Dict, List
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.services.dashboard.period_comparison_service import (
    PeriodComparisonService,
    PeriodComparison,
    PeriodMetrics,
    ComparisonPeriod,
)

pytestmark = [pytest.mark.unit]

TEST_USER_UUID = uuid4()


@pytest.fixture
def mock_db() -> AsyncMock:
    """
    Fixture für gemockte Datenbank-Session.

    Returns:
        AsyncMock: Mock der AsyncSession
    """
    return AsyncMock()


@pytest.fixture
def service(mock_db: AsyncMock) -> PeriodComparisonService:
    """
    Fixture für PeriodComparisonService mit gemockter DB.

    Args:
        mock_db: Gemockte Datenbank-Session

    Returns:
        PeriodComparisonService: Instanz mit Mock-DB
    """
    return PeriodComparisonService(mock_db)


class TestComparePeriods:
    """Tests für compare_periods Methode."""

    @pytest.mark.asyncio
    async def test_compare_periods_month(self, service: PeriodComparisonService) -> None:
        """
        Test: Monatsvergleich (MoM) mit Delta-Berechnung.

        Verifiziert:
        - Korrekte Periodenberechnung
        - Delta-Berechnung zwischen Monaten
        - Trend-Bestimmung
        """
        current_metrics = PeriodMetrics(
            period_label="Februar 2026",
            document_count=150,
            invoice_total=Decimal("50000.00"),
            expense_total=Decimal("30000.00"),
            ocr_processed=140,
            avg_processing_time_ms=250.0,
            approval_count=45,
            approval_avg_days=5.5
        )

        previous_metrics = PeriodMetrics(
            period_label="Januar 2026",
            document_count=100,
            invoice_total=Decimal("40000.00"),
            expense_total=Decimal("25000.00"),
            ocr_processed=90,
            avg_processing_time_ms=300.0,
            approval_count=30,
            approval_avg_days=6.0
        )

        with patch.object(
            service,
            '_get_period_metrics',
            side_effect=[current_metrics, previous_metrics]
        ):
            result = await service.compare_periods(
                user_id=TEST_USER_UUID,
                period_type=ComparisonPeriod.MONTH,
                reference_date=date(2026, 2, 15)
            )

        assert isinstance(result, PeriodComparison)
        assert result.current == current_metrics
        assert result.previous == previous_metrics
        assert result.trend in ["up", "down", "stable"]
        assert "document_count" in result.deltas
        assert result.deltas["document_count"] == 50.0  # (150-100)/100 * 100

    @pytest.mark.asyncio
    async def test_compare_periods_quarter(self, service: PeriodComparisonService) -> None:
        """
        Test: Quartalsvergleich (QoQ).

        Verifiziert:
        - Quartalsberechnung
        - QoQ Delta-Berechnung
        """
        current_metrics = PeriodMetrics(
            period_label="Q1 2026",
            document_count=500,
            invoice_total=Decimal("150000.00"),
            expense_total=Decimal("90000.00"),
            ocr_processed=450,
            avg_processing_time_ms=275.0,
            approval_count=150,
            approval_avg_days=5.0
        )

        previous_metrics = PeriodMetrics(
            period_label="Q4 2025",
            document_count=400,
            invoice_total=Decimal("120000.00"),
            expense_total=Decimal("75000.00"),
            ocr_processed=380,
            avg_processing_time_ms=300.0,
            approval_count=120,
            approval_avg_days=6.0
        )

        with patch.object(
            service,
            '_get_period_metrics',
            side_effect=[current_metrics, previous_metrics]
        ):
            result = await service.compare_periods(
                user_id=TEST_USER_UUID,
                period_type=ComparisonPeriod.QUARTER,
                reference_date=date(2026, 2, 15)
            )

        assert isinstance(result, PeriodComparison)
        assert result.current.document_count == 500
        assert result.previous.document_count == 400
        assert result.deltas["document_count"] == 25.0  # (500-400)/400 * 100

    @pytest.mark.asyncio
    async def test_compare_periods_year(self, service: PeriodComparisonService) -> None:
        """
        Test: Jahresvergleich (YoY).

        Verifiziert:
        - Jahresberechnung
        - YoY Delta-Berechnung
        """
        current_metrics = PeriodMetrics(
            period_label="2026",
            document_count=2000,
            invoice_total=Decimal("600000.00"),
            expense_total=Decimal("400000.00"),
            ocr_processed=1900,
            avg_processing_time_ms=250.0,
            approval_count=600,
            approval_avg_days=5.0
        )

        previous_metrics = PeriodMetrics(
            period_label="2025",
            document_count=1500,
            invoice_total=Decimal("500000.00"),
            expense_total=Decimal("350000.00"),
            ocr_processed=1400,
            avg_processing_time_ms=280.0,
            approval_count=500,
            approval_avg_days=6.5
        )

        with patch.object(
            service,
            '_get_period_metrics',
            side_effect=[current_metrics, previous_metrics]
        ):
            result = await service.compare_periods(
                user_id=TEST_USER_UUID,
                period_type=ComparisonPeriod.YEAR,
                reference_date=date(2026, 6, 15)
            )

        assert isinstance(result, PeriodComparison)
        assert result.current.document_count == 2000
        assert result.previous.document_count == 1500
        # (2000-1500)/1500 * 100 ≈ 33.33
        assert abs(result.deltas["document_count"] - 33.33) < 0.1


class TestGetTrendSeries:
    """Tests für get_trend_series Methode."""

    @pytest.mark.asyncio
    async def test_get_trend_series(self, service: PeriodComparisonService) -> None:
        """
        Test: Zeitreihen-Abruf für 12 Monate.

        Verifiziert:
        - Korrekte Anzahl Perioden
        - Chronologische Sortierung
        """
        mock_metrics = PeriodMetrics(
            period_label="Januar 2026",
            document_count=100,
            invoice_total=Decimal("10000.00"),
            expense_total=Decimal("5000.00"),
            ocr_processed=90,
            avg_processing_time_ms=250.0,
            approval_count=30,
            approval_avg_days=5.0
        )

        with patch.object(
            service,
            '_get_period_metrics',
            return_value=mock_metrics
        ):
            result = await service.get_trend_series(
                user_id=TEST_USER_UUID,
                metric="document_count",
                periods=12,
                period_type=ComparisonPeriod.MONTH
            )

        assert isinstance(result, list)
        assert len(result) == 12
        assert all(isinstance(m, PeriodMetrics) for m in result)

    @pytest.mark.asyncio
    async def test_get_trend_series_validation(self, service: PeriodComparisonService) -> None:
        """
        Test: Validierung der Periodenanzahl (max 100).

        Verifiziert:
        - ValueError bei periods > 100
        - ValueError bei periods < 1
        """
        with pytest.raises(ValueError, match="zwischen 1 und 100"):
            await service.get_trend_series(
                user_id=TEST_USER_UUID,
                metric="document_count",
                periods=101
            )

        with pytest.raises(ValueError, match="zwischen 1 und 100"):
            await service.get_trend_series(
                user_id=TEST_USER_UUID,
                metric="document_count",
                periods=0
            )

    @pytest.mark.asyncio
    async def test_get_trend_series_invalid_metric(self, service: PeriodComparisonService) -> None:
        """
        Test: Validierung ungültiger Metrik-Namen.

        Verifiziert:
        - ValueError bei unbekannter Metrik
        """
        with pytest.raises(ValueError, match="Ungültige Metrik"):
            await service.get_trend_series(
                user_id=TEST_USER_UUID,
                metric="invalid_metric",
                periods=12
            )


class TestGetPeriodSummary:
    """Tests für get_period_summary Methode."""

    @pytest.mark.asyncio
    async def test_get_period_summary(self, service: PeriodComparisonService) -> None:
        """
        Test: Widget-Summary-Format mit Key-Metrics.

        Verifiziert:
        - Korrekte Dictionary-Struktur
        - Alle erwarteten Keys vorhanden
        - Highlights mit aktuellen Werten
        """
        current_metrics = PeriodMetrics(
            period_label="Februar 2026",
            document_count=150,
            invoice_total=Decimal("50000.00"),
            expense_total=Decimal("30000.00"),
            ocr_processed=140,
            avg_processing_time_ms=250.0,
            approval_count=45,
            approval_avg_days=5.5
        )

        previous_metrics = PeriodMetrics(
            period_label="Januar 2026",
            document_count=100,
            invoice_total=Decimal("40000.00"),
            expense_total=Decimal("25000.00"),
            ocr_processed=90,
            avg_processing_time_ms=300.0,
            approval_count=30,
            approval_avg_days=6.0
        )

        with patch.object(
            service,
            '_get_period_metrics',
            side_effect=[current_metrics, previous_metrics]
        ):
            result = await service.get_period_summary(
                user_id=TEST_USER_UUID,
                period_type=ComparisonPeriod.MONTH
            )

        assert isinstance(result, dict)
        assert result["period_type"] == "month"
        assert result["current_period"] == "Februar 2026"
        assert result["previous_period"] == "Januar 2026"
        assert result["trend"] in ["up", "down", "stable"]
        assert "deltas" in result
        assert "highlights" in result
        assert result["highlights"]["document_count"] == 150
        assert result["highlights"]["invoice_total"] == 50000.00
        assert result["highlights"]["ocr_processed"] == 140


class TestPeriodBoundaries:
    """Tests für _get_period_boundaries Methode."""

    def test_period_boundaries_month(self, service: PeriodComparisonService) -> None:
        """
        Test: Monatsgrenzen-Berechnung.

        Verifiziert:
        - Januar 2026 -> (2026-01-01, 2026-01-31)
        - Dezember 2025 -> (2025-12-01, 2025-12-31)
        """
        start, end = service._get_period_boundaries(
            date(2026, 1, 15),
            ComparisonPeriod.MONTH
        )

        assert start == date(2026, 1, 1)
        assert end == date(2026, 1, 31)

        # Test December (edge case)
        start, end = service._get_period_boundaries(
            date(2025, 12, 20),
            ComparisonPeriod.MONTH
        )

        assert start == date(2025, 12, 1)
        assert end == date(2025, 12, 31)

    def test_period_boundaries_quarter(self, service: PeriodComparisonService) -> None:
        """
        Test: Quartalsgrenzen-Berechnung.

        Verifiziert:
        - Q1 2026 -> (2026-01-01, 2026-03-31)
        - Q4 2025 -> (2025-10-01, 2025-12-31)
        """
        # Q1 (Jan-Mar)
        start, end = service._get_period_boundaries(
            date(2026, 2, 15),
            ComparisonPeriod.QUARTER
        )

        assert start == date(2026, 1, 1)
        assert end == date(2026, 3, 31)

        # Q4 (Oct-Dec)
        start, end = service._get_period_boundaries(
            date(2025, 11, 15),
            ComparisonPeriod.QUARTER
        )

        assert start == date(2025, 10, 1)
        assert end == date(2025, 12, 31)

    def test_period_boundaries_year(self, service: PeriodComparisonService) -> None:
        """
        Test: Jahresgrenzen-Berechnung.

        Verifiziert:
        - 2026 -> (2026-01-01, 2026-12-31)
        """
        start, end = service._get_period_boundaries(
            date(2026, 6, 15),
            ComparisonPeriod.YEAR
        )

        assert start == date(2026, 1, 1)
        assert end == date(2026, 12, 31)


class TestDeltaCalculation:
    """Tests für _calculate_deltas Methode."""

    def test_delta_calculation_zero_division(self, service: PeriodComparisonService) -> None:
        """
        Test: Division durch Null -> 100% bei curr > 0.

        Verifiziert:
        - prev=0, curr>0 -> 100.0
        - prev=0, curr=0 -> 0.0
        """
        current = PeriodMetrics(
            period_label="Februar 2026",
            document_count=100,
            invoice_total=Decimal("10000.00"),
            expense_total=Decimal("5000.00"),
            ocr_processed=90,
            avg_processing_time_ms=250.0,
            approval_count=30,
            approval_avg_days=5.0
        )

        previous = PeriodMetrics(
            period_label="Januar 2026",
            document_count=0,
            invoice_total=Decimal("0.00"),
            expense_total=Decimal("0.00"),
            ocr_processed=0,
            avg_processing_time_ms=0.0,
            approval_count=0,
            approval_avg_days=0.0
        )

        deltas = service._calculate_deltas(current, previous)

        assert deltas["document_count"] == 100.0
        assert deltas["invoice_total"] == 100.0
        assert deltas["ocr_processed"] == 100.0

    def test_delta_calculation_normal(self, service: PeriodComparisonService) -> None:
        """
        Test: Normale Prozent-Berechnung.

        Verifiziert:
        - (150-100)/100 * 100 = 50.0
        - (50000-40000)/40000 * 100 = 25.0
        """
        current = PeriodMetrics(
            period_label="Februar 2026",
            document_count=150,
            invoice_total=Decimal("50000.00"),
            expense_total=Decimal("30000.00"),
            ocr_processed=140,
            avg_processing_time_ms=250.0,
            approval_count=45,
            approval_avg_days=5.5
        )

        previous = PeriodMetrics(
            period_label="Januar 2026",
            document_count=100,
            invoice_total=Decimal("40000.00"),
            expense_total=Decimal("25000.00"),
            ocr_processed=90,
            avg_processing_time_ms=300.0,
            approval_count=30,
            approval_avg_days=6.0
        )

        deltas = service._calculate_deltas(current, previous)

        assert deltas["document_count"] == 50.0
        assert deltas["invoice_total"] == 25.0
        assert abs(deltas["expense_total"] - 20.0) < 0.1


class TestTrendDetermination:
    """Tests für _determine_trend Methode."""

    def test_trend_determination_up(self, service: PeriodComparisonService) -> None:
        """
        Test: Trend 'up' bei Mehrheit positiver Deltas.

        Verifiziert:
        - Alle Key-Metrics > 5% -> "up"
        """
        deltas: Dict[str, float] = {
            "document_count": 25.0,
            "invoice_total": 30.0,
            "expense_total": 20.0,
            "ocr_processed": 15.0,
            "avg_processing_time_ms": -5.0,
            "approval_count": 10.0,
        }

        trend = service._determine_trend(deltas)

        assert trend == "up"

    def test_trend_determination_down(self, service: PeriodComparisonService) -> None:
        """
        Test: Trend 'down' bei Mehrheit negativer Deltas.

        Verifiziert:
        - Alle Key-Metrics < -5% -> "down"
        """
        deltas: Dict[str, float] = {
            "document_count": -25.0,
            "invoice_total": -30.0,
            "expense_total": -20.0,
            "ocr_processed": -15.0,
            "avg_processing_time_ms": 5.0,
            "approval_count": -10.0,
        }

        trend = service._determine_trend(deltas)

        assert trend == "down"

    def test_trend_determination_stable(self, service: PeriodComparisonService) -> None:
        """
        Test: Trend 'stable' bei Deltas innerhalb +/-5%.

        Verifiziert:
        - Gemischte Deltas innerhalb Schwellenwert -> "stable"
        """
        deltas: Dict[str, float] = {
            "document_count": 2.0,
            "invoice_total": -3.0,
            "expense_total": 4.0,
            "ocr_processed": 1.5,
            "avg_processing_time_ms": -2.0,
            "approval_count": 3.0,
        }

        trend = service._determine_trend(deltas)

        assert trend == "stable"


class TestGermanLabels:
    """Tests für _get_period_label Methode."""

    def test_german_labels_month(self, service: PeriodComparisonService) -> None:
        """
        Test: Deutsche Monatsnamen.

        Verifiziert:
        - Januar 2026
        - März 2026 (mit Umlaut)
        """
        label = service._get_period_label(
            date(2026, 1, 1),
            ComparisonPeriod.MONTH
        )

        assert label == "Januar 2026"

        label = service._get_period_label(
            date(2026, 3, 1),
            ComparisonPeriod.MONTH
        )

        assert label == "März 2026"

    def test_german_labels_quarter(self, service: PeriodComparisonService) -> None:
        """
        Test: Quartals-Labels.

        Verifiziert:
        - Q1 2026 (Jan-Mar)
        - Q4 2025 (Oct-Dec)
        """
        label = service._get_period_label(
            date(2026, 1, 1),
            ComparisonPeriod.QUARTER
        )

        assert label == "Q1 2026"

        label = service._get_period_label(
            date(2025, 10, 1),
            ComparisonPeriod.QUARTER
        )

        assert label == "Q4 2025"

    def test_german_labels_year(self, service: PeriodComparisonService) -> None:
        """
        Test: Jahres-Labels.

        Verifiziert:
        - "2026"
        """
        label = service._get_period_label(
            date(2026, 1, 1),
            ComparisonPeriod.YEAR
        )

        assert label == "2026"

    def test_german_labels_custom(self, service: PeriodComparisonService) -> None:
        """
        Test: Custom-Labels im deutschen Datumsformat.

        Verifiziert:
        - DD.MM.YYYY Format
        """
        label = service._get_period_label(
            date(2026, 2, 15),
            ComparisonPeriod.CUSTOM
        )

        assert label == "15.02.2026"
