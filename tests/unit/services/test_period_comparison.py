"""
Unit tests für PeriodComparisonService.

Testet Zeitraum-Vergleiche (MoM, YoY, QoQ) für Dashboard-Metriken.
"""
import pytest
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.dashboard.period_comparison_service import (
    PeriodComparisonService,
    PeriodType,
    ComparisonResult,
    TrendDirection
)


class TestPeriodComparisonService:
    """Tests für PeriodComparisonService."""

    @pytest.fixture
    def mock_db(self) -> AsyncMock:
        """Mock AsyncSession."""
        db = AsyncMock()
        db.execute = AsyncMock()
        db.scalars = AsyncMock()
        return db

    @pytest.fixture
    def service(self, mock_db: AsyncMock) -> PeriodComparisonService:
        """PeriodComparisonService Instanz."""
        return PeriodComparisonService(db=mock_db)

    @pytest.fixture
    def user_id(self) -> str:
        """Test User ID."""
        return "user-123"

    @pytest.fixture
    def current_date(self) -> datetime:
        """Aktuelles Test-Datum."""
        return datetime(2026, 2, 15, 12, 0, 0)

    # -------------------------------------------------------------------------
    # Month-over-Month (MoM) Tests
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_mom_comparison_basic(
        self,
        service: PeriodComparisonService,
        user_id: str,
        current_date: datetime
    ) -> None:
        """MoM-Vergleich mit Basis-Daten."""
        # Arrange
        current_value = Decimal("100.0")
        previous_value = Decimal("80.0")

        with patch.object(
            service,
            "_get_period_value",
            side_effect=[current_value, previous_value]
        ):
            # Act
            result = await service.compare_periods(
                user_id=user_id,
                metric_type="document_count",
                period_type=PeriodType.MONTH_OVER_MONTH,
                reference_date=current_date
            )

        # Assert
        assert result.current_value == current_value
        assert result.previous_value == previous_value
        assert result.delta == Decimal("20.0")
        assert result.delta_percent == Decimal("25.0")  # (20/80)*100
        assert result.trend == TrendDirection.UP
        assert result.current_period_label == "Februar 2026"
        assert result.previous_period_label == "Januar 2026"

    @pytest.mark.asyncio
    async def test_mom_comparison_negative_trend(
        self,
        service: PeriodComparisonService,
        user_id: str,
        current_date: datetime
    ) -> None:
        """MoM-Vergleich mit negativem Trend."""
        # Arrange
        current_value = Decimal("60.0")
        previous_value = Decimal("100.0")

        with patch.object(
            service,
            "_get_period_value",
            side_effect=[current_value, previous_value]
        ):
            # Act
            result = await service.compare_periods(
                user_id=user_id,
                metric_type="document_count",
                period_type=PeriodType.MONTH_OVER_MONTH,
                reference_date=current_date
            )

        # Assert
        assert result.delta == Decimal("-40.0")
        assert result.delta_percent == Decimal("-40.0")  # (-40/100)*100
        assert result.trend == TrendDirection.DOWN

    @pytest.mark.asyncio
    async def test_mom_comparison_stable(
        self,
        service: PeriodComparisonService,
        user_id: str,
        current_date: datetime
    ) -> None:
        """MoM-Vergleich mit stabilem Trend."""
        # Arrange
        current_value = Decimal("100.0")
        previous_value = Decimal("101.0")

        with patch.object(
            service,
            "_get_period_value",
            side_effect=[current_value, previous_value]
        ):
            # Act
            result = await service.compare_periods(
                user_id=user_id,
                metric_type="document_count",
                period_type=PeriodType.MONTH_OVER_MONTH,
                reference_date=current_date
            )

        # Assert
        # Delta < 5% gilt als stabil
        assert result.trend == TrendDirection.STABLE

    @pytest.mark.asyncio
    async def test_mom_division_by_zero(
        self,
        service: PeriodComparisonService,
        user_id: str,
        current_date: datetime
    ) -> None:
        """MoM-Vergleich mit previous_value = 0."""
        # Arrange
        current_value = Decimal("50.0")
        previous_value = Decimal("0.0")

        with patch.object(
            service,
            "_get_period_value",
            side_effect=[current_value, previous_value]
        ):
            # Act
            result = await service.compare_periods(
                user_id=user_id,
                metric_type="document_count",
                period_type=PeriodType.MONTH_OVER_MONTH,
                reference_date=current_date
            )

        # Assert
        assert result.delta == Decimal("50.0")
        assert result.delta_percent is None  # Division by zero
        assert result.trend == TrendDirection.UP

    # -------------------------------------------------------------------------
    # Year-over-Year (YoY) Tests
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_yoy_comparison_basic(
        self,
        service: PeriodComparisonService,
        user_id: str,
        current_date: datetime
    ) -> None:
        """YoY-Vergleich mit Basis-Daten."""
        # Arrange
        current_value = Decimal("500.0")
        previous_value = Decimal("400.0")

        with patch.object(
            service,
            "_get_period_value",
            side_effect=[current_value, previous_value]
        ):
            # Act
            result = await service.compare_periods(
                user_id=user_id,
                metric_type="revenue",
                period_type=PeriodType.YEAR_OVER_YEAR,
                reference_date=current_date
            )

        # Assert
        assert result.current_value == current_value
        assert result.previous_value == previous_value
        assert result.delta == Decimal("100.0")
        assert result.delta_percent == Decimal("25.0")
        assert result.trend == TrendDirection.UP
        assert "2026" in result.current_period_label
        assert "2025" in result.previous_period_label

    # -------------------------------------------------------------------------
    # Quarter-over-Quarter (QoQ) Tests
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_qoq_comparison_basic(
        self,
        service: PeriodComparisonService,
        user_id: str,
        current_date: datetime
    ) -> None:
        """QoQ-Vergleich mit Basis-Daten."""
        # Arrange
        current_value = Decimal("300.0")
        previous_value = Decimal("250.0")

        with patch.object(
            service,
            "_get_period_value",
            side_effect=[current_value, previous_value]
        ):
            # Act
            result = await service.compare_periods(
                user_id=user_id,
                metric_type="document_count",
                period_type=PeriodType.QUARTER_OVER_QUARTER,
                reference_date=current_date
            )

        # Assert
        assert result.delta == Decimal("50.0")
        assert result.delta_percent == Decimal("20.0")
        assert result.trend == TrendDirection.UP
        assert "Q1" in result.current_period_label
        assert "Q4" in result.previous_period_label

    # -------------------------------------------------------------------------
    # Trend Series Tests
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_get_trend_series_12_months(
        self,
        service: PeriodComparisonService,
        user_id: str,
        current_date: datetime
    ) -> None:
        """Trend-Serie für 12 Monate."""
        # Arrange
        monthly_values = [
            Decimal("50.0"),
            Decimal("55.0"),
            Decimal("60.0"),
            Decimal("58.0"),
            Decimal("62.0"),
            Decimal("70.0"),
            Decimal("75.0"),
            Decimal("80.0"),
            Decimal("78.0"),
            Decimal("85.0"),
            Decimal("90.0"),
            Decimal("95.0"),
        ]

        with patch.object(
            service,
            "_get_period_value",
            side_effect=monthly_values
        ):
            # Act
            result = await service.get_trend_series(
                user_id=user_id,
                metric_type="document_count",
                months=12,
                reference_date=current_date
            )

        # Assert
        assert len(result) == 12
        assert all("period_label" in item for item in result)
        assert all("value" in item for item in result)
        assert result[0]["value"] == monthly_values[0]
        assert result[-1]["value"] == monthly_values[-1]

    @pytest.mark.asyncio
    async def test_get_trend_series_german_month_names(
        self,
        service: PeriodComparisonService,
        user_id: str,
        current_date: datetime
    ) -> None:
        """Trend-Serie verwendet deutsche Monatsnamen."""
        # Arrange
        monthly_values = [Decimal("100.0")] * 12

        with patch.object(
            service,
            "_get_period_value",
            side_effect=monthly_values
        ):
            # Act
            result = await service.get_trend_series(
                user_id=user_id,
                metric_type="document_count",
                months=12,
                reference_date=current_date
            )

        # Assert
        # Februar 2026 sollte im letzten Eintrag sein
        assert "Februar" in result[-1]["period_label"] or "Feb" in result[-1]["period_label"]
        # Januar 2026 sollte im vorletzten sein
        assert "Januar" in result[-2]["period_label"] or "Jan" in result[-2]["period_label"]

    # -------------------------------------------------------------------------
    # Empty Data Tests
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_comparison_with_empty_current_period(
        self,
        service: PeriodComparisonService,
        user_id: str,
        current_date: datetime
    ) -> None:
        """Vergleich mit leerem aktuellem Zeitraum."""
        # Arrange
        current_value = Decimal("0.0")
        previous_value = Decimal("100.0")

        with patch.object(
            service,
            "_get_period_value",
            side_effect=[current_value, previous_value]
        ):
            # Act
            result = await service.compare_periods(
                user_id=user_id,
                metric_type="document_count",
                period_type=PeriodType.MONTH_OVER_MONTH,
                reference_date=current_date
            )

        # Assert
        assert result.current_value == Decimal("0.0")
        assert result.delta == Decimal("-100.0")
        assert result.trend == TrendDirection.DOWN

    @pytest.mark.asyncio
    async def test_comparison_with_both_periods_empty(
        self,
        service: PeriodComparisonService,
        user_id: str,
        current_date: datetime
    ) -> None:
        """Vergleich mit beiden Zeiträumen leer."""
        # Arrange
        current_value = Decimal("0.0")
        previous_value = Decimal("0.0")

        with patch.object(
            service,
            "_get_period_value",
            side_effect=[current_value, previous_value]
        ):
            # Act
            result = await service.compare_periods(
                user_id=user_id,
                metric_type="document_count",
                period_type=PeriodType.MONTH_OVER_MONTH,
                reference_date=current_date
            )

        # Assert
        assert result.current_value == Decimal("0.0")
        assert result.previous_value == Decimal("0.0")
        assert result.delta == Decimal("0.0")
        assert result.delta_percent is None
        assert result.trend == TrendDirection.STABLE

    # -------------------------------------------------------------------------
    # User Isolation Tests
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_user_isolation_in_queries(
        self,
        service: PeriodComparisonService,
        mock_db: AsyncMock,
        current_date: datetime
    ) -> None:
        """Queries isolieren korrekt nach user_id."""
        # Arrange
        user_id = "user-123"
        mock_result = MagicMock()
        mock_result.scalar.return_value = Decimal("100.0")
        mock_db.execute.return_value = mock_result

        # Act
        await service._get_period_value(
            user_id=user_id,
            metric_type="document_count",
            start_date=current_date,
            end_date=current_date + timedelta(days=30)
        )

        # Assert
        # Verify user_id is in the query parameters
        call_args = mock_db.execute.call_args
        assert call_args is not None
        # Check that user_id appears in the query or parameters
        query_str = str(call_args[0][0]) if call_args[0] else ""
        assert "user_id" in query_str.lower() or user_id in str(call_args)

    # -------------------------------------------------------------------------
    # Edge Cases
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_comparison_with_very_large_values(
        self,
        service: PeriodComparisonService,
        user_id: str,
        current_date: datetime
    ) -> None:
        """Vergleich mit sehr großen Werten."""
        # Arrange
        current_value = Decimal("999999999.99")
        previous_value = Decimal("500000000.00")

        with patch.object(
            service,
            "_get_period_value",
            side_effect=[current_value, previous_value]
        ):
            # Act
            result = await service.compare_periods(
                user_id=user_id,
                metric_type="revenue",
                period_type=PeriodType.YEAR_OVER_YEAR,
                reference_date=current_date
            )

        # Assert
        assert result.delta > Decimal("0")
        assert result.trend == TrendDirection.UP

    @pytest.mark.asyncio
    async def test_comparison_with_negative_values(
        self,
        service: PeriodComparisonService,
        user_id: str,
        current_date: datetime
    ) -> None:
        """Vergleich mit negativen Werten (z.B. Verluste)."""
        # Arrange
        current_value = Decimal("-50.0")
        previous_value = Decimal("-100.0")

        with patch.object(
            service,
            "_get_period_value",
            side_effect=[current_value, previous_value]
        ):
            # Act
            result = await service.compare_periods(
                user_id=user_id,
                metric_type="profit",
                period_type=PeriodType.MONTH_OVER_MONTH,
                reference_date=current_date
            )

        # Assert
        # -50 ist besser als -100, also UP trend
        assert result.delta == Decimal("50.0")
        assert result.trend == TrendDirection.UP

    @pytest.mark.asyncio
    async def test_trend_series_with_missing_months(
        self,
        service: PeriodComparisonService,
        user_id: str,
        current_date: datetime
    ) -> None:
        """Trend-Serie mit fehlenden Monaten (Nullwerte)."""
        # Arrange
        monthly_values = [
            Decimal("50.0"),
            Decimal("0.0"),  # Fehlender Monat
            Decimal("60.0"),
            Decimal("0.0"),  # Fehlender Monat
            Decimal("70.0"),
        ]

        with patch.object(
            service,
            "_get_period_value",
            side_effect=monthly_values
        ):
            # Act
            result = await service.get_trend_series(
                user_id=user_id,
                metric_type="document_count",
                months=5,
                reference_date=current_date
            )

        # Assert
        assert len(result) == 5
        assert result[1]["value"] == Decimal("0.0")
        assert result[3]["value"] == Decimal("0.0")

    @pytest.mark.asyncio
    async def test_period_labels_cross_year_boundary(
        self,
        service: PeriodComparisonService,
        user_id: str
    ) -> None:
        """Period-Labels über Jahreswechsel hinweg."""
        # Arrange
        reference_date = datetime(2026, 1, 15, 12, 0, 0)  # Januar 2026
        current_value = Decimal("100.0")
        previous_value = Decimal("90.0")

        with patch.object(
            service,
            "_get_period_value",
            side_effect=[current_value, previous_value]
        ):
            # Act
            result = await service.compare_periods(
                user_id=user_id,
                metric_type="document_count",
                period_type=PeriodType.MONTH_OVER_MONTH,
                reference_date=reference_date
            )

        # Assert
        # Januar 2026 vs Dezember 2025
        assert "Januar" in result.current_period_label or "Jan" in result.current_period_label
        assert "2026" in result.current_period_label
        assert "Dezember" in result.previous_period_label or "Dez" in result.previous_period_label
        assert "2025" in result.previous_period_label


class TestComparisonResult:
    """Tests für ComparisonResult Dataclass."""

    def test_comparison_result_initialization(self) -> None:
        """ComparisonResult korrekt initialisiert."""
        result = ComparisonResult(
            current_value=Decimal("100.0"),
            previous_value=Decimal("80.0"),
            delta=Decimal("20.0"),
            delta_percent=Decimal("25.0"),
            trend=TrendDirection.UP,
            current_period_label="Februar 2026",
            previous_period_label="Januar 2026"
        )

        assert result.current_value == Decimal("100.0")
        assert result.trend == TrendDirection.UP

    def test_comparison_result_with_none_delta_percent(self) -> None:
        """ComparisonResult mit None delta_percent."""
        result = ComparisonResult(
            current_value=Decimal("50.0"),
            previous_value=Decimal("0.0"),
            delta=Decimal("50.0"),
            delta_percent=None,
            trend=TrendDirection.UP,
            current_period_label="Februar 2026",
            previous_period_label="Januar 2026"
        )

        assert result.delta_percent is None


class TestTrendDirection:
    """Tests für TrendDirection Enum."""

    def test_trend_direction_values(self) -> None:
        """TrendDirection hat alle erwarteten Werte."""
        assert TrendDirection.UP
        assert TrendDirection.DOWN
        assert TrendDirection.STABLE

    def test_trend_direction_string_representation(self) -> None:
        """TrendDirection String-Repräsentation."""
        assert str(TrendDirection.UP) in ["TrendDirection.UP", "UP"]
        assert str(TrendDirection.DOWN) in ["TrendDirection.DOWN", "DOWN"]
        assert str(TrendDirection.STABLE) in ["TrendDirection.STABLE", "STABLE"]


class TestPeriodType:
    """Tests für PeriodType Enum."""

    def test_period_type_values(self) -> None:
        """PeriodType hat alle erwarteten Werte."""
        assert PeriodType.MONTH_OVER_MONTH
        assert PeriodType.YEAR_OVER_YEAR
        assert PeriodType.QUARTER_OVER_QUARTER

    def test_period_type_string_representation(self) -> None:
        """PeriodType String-Repräsentation."""
        assert "MONTH" in str(PeriodType.MONTH_OVER_MONTH).upper()
        assert "YEAR" in str(PeriodType.YEAR_OVER_YEAR).upper()
        assert "QUARTER" in str(PeriodType.QUARTER_OVER_QUARTER).upper()
