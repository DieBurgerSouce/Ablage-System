# -*- coding: utf-8 -*-
"""
Unit tests für PeriodComparisonService.

Testet Zeitraum-Vergleiche (MoM, YoY, QoQ) für Dashboard-Metriken.

Getestet wird der ECHTE Service-Vertrag:
    compare_periods(user_id, period_type: ComparisonPeriod, reference_date)
        -> PeriodComparison(current, previous, deltas, trend)
    get_trend_series(user_id, metric, periods, period_type) -> List[PeriodMetrics]
    _get_period_metrics(user_id, start, end, period_type) -> PeriodMetrics
sowie die reinen Helper-Methoden (Boundaries, Labels, Deltas, Trend).
"""
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import List

import pytest
from unittest.mock import AsyncMock, MagicMock

from app.services.dashboard.period_comparison_service import (
    PeriodComparisonService,
    ComparisonPeriod,
    PeriodType,
    ComparisonResult,
    TrendDirection,
    PeriodMetrics,
    PeriodComparison,
)


def _metrics(
    label: str,
    document_count: int = 0,
    invoice_total: str = "0",
    ocr_processed: int = 0,
) -> PeriodMetrics:
    """Hilfsfunktion: PeriodMetrics mit sinnvollen Defaults."""
    return PeriodMetrics(
        period_label=label,
        document_count=document_count,
        invoice_total=Decimal(invoice_total),
        expense_total=Decimal(invoice_total),
        ocr_processed=ocr_processed,
        avg_processing_time_ms=0.0,
        approval_count=0,
        approval_avg_days=0.0,
    )


class TestPeriodComparisonService:
    """Tests für PeriodComparisonService (echter Vertrag)."""

    @pytest.fixture
    def mock_db(self) -> AsyncMock:
        db = AsyncMock()
        db.execute = AsyncMock()
        return db

    @pytest.fixture
    def service(self, mock_db: AsyncMock) -> PeriodComparisonService:
        return PeriodComparisonService(db=mock_db)

    @pytest.fixture
    def user_id(self) -> uuid.UUID:
        return uuid.uuid4()

    @pytest.fixture
    def current_date(self) -> date:
        return date(2026, 2, 15)

    # -------------------------------------------------------------------------
    # compare_periods – Month-over-Month
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_mom_comparison_basic(
        self, service: PeriodComparisonService, user_id, current_date
    ) -> None:
        """MoM-Vergleich liefert PeriodComparison mit Up-Trend bei Wachstum."""
        service._get_period_metrics = AsyncMock(  # type: ignore[method-assign]
            side_effect=[
                _metrics("Februar 2026", document_count=100, invoice_total="100", ocr_processed=100),
                _metrics("Januar 2026", document_count=80, invoice_total="80", ocr_processed=80),
            ]
        )

        result = await service.compare_periods(
            user_id=user_id,
            period_type=ComparisonPeriod.MONTH,
            reference_date=current_date,
        )

        assert isinstance(result, PeriodComparison)
        assert result.current.document_count == 100
        assert result.previous.document_count == 80
        # (100-80)/80 * 100 = 25%
        assert result.deltas["document_count"] == pytest.approx(25.0)
        assert result.trend == "up"
        assert result.current.period_label == "Februar 2026"
        assert result.previous.period_label == "Januar 2026"

    @pytest.mark.asyncio
    async def test_mom_comparison_negative_trend(
        self, service: PeriodComparisonService, user_id, current_date
    ) -> None:
        """MoM-Vergleich mit Rückgang liefert Down-Trend."""
        service._get_period_metrics = AsyncMock(  # type: ignore[method-assign]
            side_effect=[
                _metrics("Februar 2026", document_count=60, invoice_total="60", ocr_processed=60),
                _metrics("Januar 2026", document_count=100, invoice_total="100", ocr_processed=100),
            ]
        )

        result = await service.compare_periods(
            user_id=user_id,
            period_type=ComparisonPeriod.MONTH,
            reference_date=current_date,
        )

        # (60-100)/100 * 100 = -40%
        assert result.deltas["document_count"] == pytest.approx(-40.0)
        assert result.trend == "down"

    @pytest.mark.asyncio
    async def test_mom_comparison_stable(
        self, service: PeriodComparisonService, user_id, current_date
    ) -> None:
        """MoM-Vergleich mit kleiner Änderung (<5%) gilt als stabil."""
        service._get_period_metrics = AsyncMock(  # type: ignore[method-assign]
            side_effect=[
                _metrics("Februar 2026", document_count=101, invoice_total="101", ocr_processed=101),
                _metrics("Januar 2026", document_count=100, invoice_total="100", ocr_processed=100),
            ]
        )

        result = await service.compare_periods(
            user_id=user_id,
            period_type=ComparisonPeriod.MONTH,
            reference_date=current_date,
        )

        # 1% Veränderung -> stable
        assert result.trend == "stable"

    @pytest.mark.asyncio
    async def test_mom_division_by_zero(
        self, service: PeriodComparisonService, user_id, current_date
    ) -> None:
        """previous = 0 und current > 0 ergibt 100% (kein ZeroDivisionError)."""
        service._get_period_metrics = AsyncMock(  # type: ignore[method-assign]
            side_effect=[
                _metrics("Februar 2026", document_count=50, invoice_total="50", ocr_processed=50),
                _metrics("Januar 2026", document_count=0, invoice_total="0", ocr_processed=0),
            ]
        )

        result = await service.compare_periods(
            user_id=user_id,
            period_type=ComparisonPeriod.MONTH,
            reference_date=current_date,
        )

        assert result.deltas["document_count"] == pytest.approx(100.0)
        assert result.trend == "up"

    # -------------------------------------------------------------------------
    # compare_periods – Year-over-Year
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_yoy_comparison_basic(
        self, service: PeriodComparisonService, user_id, current_date
    ) -> None:
        """YoY-Vergleich liefert Jahres-Labels und Up-Trend."""
        service._get_period_metrics = AsyncMock(  # type: ignore[method-assign]
            side_effect=[
                _metrics("2026", document_count=500, invoice_total="500", ocr_processed=500),
                _metrics("2025", document_count=400, invoice_total="400", ocr_processed=400),
            ]
        )

        result = await service.compare_periods(
            user_id=user_id,
            period_type=ComparisonPeriod.YEAR,
            reference_date=current_date,
        )

        assert result.deltas["document_count"] == pytest.approx(25.0)
        assert result.trend == "up"
        assert "2026" in result.current.period_label
        assert "2025" in result.previous.period_label

    # -------------------------------------------------------------------------
    # compare_periods – Quarter-over-Quarter
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_qoq_comparison_basic(
        self, service: PeriodComparisonService, user_id, current_date
    ) -> None:
        """QoQ-Vergleich liefert Quartals-Labels (Q1 vs Q4)."""
        service._get_period_metrics = AsyncMock(  # type: ignore[method-assign]
            side_effect=[
                _metrics("Q1 2026", document_count=300, invoice_total="300", ocr_processed=300),
                _metrics("Q4 2025", document_count=250, invoice_total="250", ocr_processed=250),
            ]
        )

        result = await service.compare_periods(
            user_id=user_id,
            period_type=ComparisonPeriod.QUARTER,
            reference_date=current_date,
        )

        assert result.deltas["document_count"] == pytest.approx(20.0)
        assert result.trend == "up"
        assert "Q1" in result.current.period_label
        assert "Q4" in result.previous.period_label

    # -------------------------------------------------------------------------
    # get_trend_series
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_get_trend_series_12_months(
        self, service: PeriodComparisonService, user_id
    ) -> None:
        """Trend-Serie liefert 12 chronologisch geordnete PeriodMetrics."""
        monthly = [
            _metrics(f"Monat {i}", document_count=50 + i * 5) for i in range(12)
        ]
        service._get_period_metrics = AsyncMock(side_effect=monthly)  # type: ignore[method-assign]

        result = await service.get_trend_series(
            user_id=user_id,
            metric="document_count",
            periods=12,
            period_type=ComparisonPeriod.MONTH,
        )

        assert len(result) == 12
        assert all(isinstance(item, PeriodMetrics) for item in result)
        assert all(item.period_label for item in result)

    @pytest.mark.asyncio
    async def test_get_trend_series_invalid_metric_raises(
        self, service: PeriodComparisonService, user_id
    ) -> None:
        """Ungültige Metrik wirft ValueError mit deutscher Fehlermeldung."""
        with pytest.raises(ValueError, match="Ungültige Metrik"):
            await service.get_trend_series(
                user_id=user_id,
                metric="erfundene_metrik",
                periods=12,
            )

    @pytest.mark.asyncio
    async def test_get_trend_series_invalid_period_count_raises(
        self, service: PeriodComparisonService, user_id
    ) -> None:
        """Periodenanzahl außerhalb 1-100 wirft ValueError."""
        with pytest.raises(ValueError, match="zwischen 1 und 100"):
            await service.get_trend_series(
                user_id=user_id,
                metric="document_count",
                periods=0,
            )

    # -------------------------------------------------------------------------
    # Empty Data
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_comparison_with_empty_current_period(
        self, service: PeriodComparisonService, user_id, current_date
    ) -> None:
        """Aktueller Zeitraum leer -> Down-Trend (von 100 auf 0)."""
        service._get_period_metrics = AsyncMock(  # type: ignore[method-assign]
            side_effect=[
                _metrics("Februar 2026", document_count=0, invoice_total="0", ocr_processed=0),
                _metrics("Januar 2026", document_count=100, invoice_total="100", ocr_processed=100),
            ]
        )

        result = await service.compare_periods(
            user_id=user_id,
            period_type=ComparisonPeriod.MONTH,
            reference_date=current_date,
        )

        assert result.current.document_count == 0
        assert result.deltas["document_count"] == pytest.approx(-100.0)
        assert result.trend == "down"

    @pytest.mark.asyncio
    async def test_comparison_with_both_periods_empty(
        self, service: PeriodComparisonService, user_id, current_date
    ) -> None:
        """Beide Zeiträume leer -> 0% Delta und stabiler Trend."""
        service._get_period_metrics = AsyncMock(  # type: ignore[method-assign]
            side_effect=[
                _metrics("Februar 2026"),
                _metrics("Januar 2026"),
            ]
        )

        result = await service.compare_periods(
            user_id=user_id,
            period_type=ComparisonPeriod.MONTH,
            reference_date=current_date,
        )

        assert result.current.document_count == 0
        assert result.previous.document_count == 0
        assert result.deltas["document_count"] == pytest.approx(0.0)
        assert result.trend == "stable"

    # -------------------------------------------------------------------------
    # User Isolation (_get_period_metrics filtert nach owner_id)
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_user_isolation_in_queries(
        self, service: PeriodComparisonService, mock_db: AsyncMock, current_date
    ) -> None:
        """_get_period_metrics nutzt user_id im Query (owner_id-Filter)."""
        user_id = uuid.uuid4()

        # Beide execute()-Aufrufe (doc + invoice) liefern ein .one()-Row
        doc_row = MagicMock(total_count=5, ocr_count=3, avg_duration=120.0)
        inv_row = MagicMock(total_invoices=Decimal("99"), paid_count=1, avg_payment_days=2.0)
        doc_result = MagicMock()
        doc_result.one.return_value = doc_row
        inv_result = MagicMock()
        inv_result.one.return_value = inv_row
        mock_db.execute.side_effect = [doc_result, inv_result]

        await service._get_period_metrics(
            user_id=user_id,
            start=date(2026, 2, 1),
            end=date(2026, 2, 28),
            period_type=ComparisonPeriod.MONTH,
        )

        # Beide Queries (Dokumente + Rechnungen) filtern nach owner_id
        assert mock_db.execute.await_count == 2
        doc_query = mock_db.execute.await_args_list[0].args[0]
        compiled = str(doc_query.compile())
        assert "owner_id" in compiled

    # -------------------------------------------------------------------------
    # Helper: Boundaries
    # -------------------------------------------------------------------------

    def test_period_boundaries_month(self, service: PeriodComparisonService) -> None:
        start, end = service._get_period_boundaries(
            date(2026, 2, 15), ComparisonPeriod.MONTH
        )
        assert start == date(2026, 2, 1)
        assert end == date(2026, 2, 28)

    def test_period_boundaries_quarter(self, service: PeriodComparisonService) -> None:
        start, end = service._get_period_boundaries(
            date(2026, 2, 15), ComparisonPeriod.QUARTER
        )
        assert start == date(2026, 1, 1)
        assert end == date(2026, 3, 31)

    def test_period_boundaries_year(self, service: PeriodComparisonService) -> None:
        start, end = service._get_period_boundaries(
            date(2026, 7, 4), ComparisonPeriod.YEAR
        )
        assert start == date(2026, 1, 1)
        assert end == date(2026, 12, 31)

    def test_previous_period_cross_year_boundary(
        self, service: PeriodComparisonService
    ) -> None:
        """Januar -> vorherige Periode ist Dezember des Vorjahres."""
        prev_start, prev_end = service._get_previous_period_boundaries(
            date(2026, 1, 1), ComparisonPeriod.MONTH
        )
        assert prev_start == date(2025, 12, 1)
        assert prev_end == date(2025, 12, 31)

    # -------------------------------------------------------------------------
    # Helper: Labels (deutsche Monatsnamen / Quartale)
    # -------------------------------------------------------------------------

    def test_period_label_german_month(self, service: PeriodComparisonService) -> None:
        label = service._get_period_label(date(2026, 2, 1), ComparisonPeriod.MONTH)
        assert label == "Februar 2026"

    def test_period_label_cross_year_boundary(
        self, service: PeriodComparisonService
    ) -> None:
        """Dezember-Label aus dem Vorjahr korrekt benannt."""
        label = service._get_period_label(date(2025, 12, 1), ComparisonPeriod.MONTH)
        assert "Dezember" in label
        assert "2025" in label

    def test_period_label_quarter(self, service: PeriodComparisonService) -> None:
        label = service._get_period_label(date(2026, 1, 1), ComparisonPeriod.QUARTER)
        assert label == "Q1 2026"

    def test_german_month_name_umlaut(self, service: PeriodComparisonService) -> None:
        """März enthält Umlaut (UTF-8)."""
        assert service._get_german_month_name(3) == "März"


class TestComparisonResult:
    """Tests für ComparisonResult Dataclass."""

    def test_comparison_result_initialization(self) -> None:
        result = ComparisonResult(
            current_value=Decimal("100.0"),
            previous_value=Decimal("80.0"),
            delta=Decimal("20.0"),
            delta_percent=Decimal("25.0"),
            trend=TrendDirection.UP,
            current_period_label="Februar 2026",
            previous_period_label="Januar 2026",
        )
        assert result.current_value == Decimal("100.0")
        assert result.trend == TrendDirection.UP

    def test_comparison_result_with_none_delta_percent(self) -> None:
        result = ComparisonResult(
            current_value=Decimal("50.0"),
            previous_value=Decimal("0.0"),
            delta=Decimal("50.0"),
            delta_percent=None,
            trend=TrendDirection.UP,
            current_period_label="Februar 2026",
            previous_period_label="Januar 2026",
        )
        assert result.delta_percent is None


class TestTrendDirection:
    """Tests für TrendDirection Enum."""

    def test_trend_direction_values(self) -> None:
        assert TrendDirection.UP
        assert TrendDirection.DOWN
        assert TrendDirection.STABLE

    def test_trend_direction_string_values(self) -> None:
        assert TrendDirection.UP.value == "up"
        assert TrendDirection.DOWN.value == "down"
        assert TrendDirection.STABLE.value == "stable"


class TestPeriodType:
    """Tests für PeriodType / ComparisonPeriod Enums."""

    def test_period_type_values(self) -> None:
        assert PeriodType.MONTH_OVER_MONTH
        assert PeriodType.YEAR_OVER_YEAR
        assert PeriodType.QUARTER_OVER_QUARTER

    def test_period_type_string_representation(self) -> None:
        assert "MONTH" in str(PeriodType.MONTH_OVER_MONTH).upper()
        assert "YEAR" in str(PeriodType.YEAR_OVER_YEAR).upper()
        assert "QUARTER" in str(PeriodType.QUARTER_OVER_QUARTER).upper()

    def test_comparison_period_values(self) -> None:
        assert ComparisonPeriod.MONTH.value == "month"
        assert ComparisonPeriod.QUARTER.value == "quarter"
        assert ComparisonPeriod.YEAR.value == "year"
