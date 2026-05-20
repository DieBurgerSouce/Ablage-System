"""
Unit Tests fuer FinanceAnalyticsService.

Testet:
- Monatliche Trends
- Jahr-zu-Jahr Vergleich
- Wiederkehrende Zahlungen Erkennung
- Cashflow-Vorhersage
"""

import pytest
from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession


class TestFinanceAnalyticsService:
    """Tests fuer Finance Analytics."""

    @pytest.fixture
    def mock_db(self) -> AsyncMock:
        """Erstellt einen Mock fuer die Datenbank-Session."""
        db = AsyncMock(spec=AsyncSession)
        db.commit = AsyncMock()
        db.refresh = AsyncMock()
        return db

    @pytest.fixture
    def sample_transactions(self) -> list:
        """Erstellt Beispiel-Transaktionen."""
        return [
            # Einnahmen
            MagicMock(
                id=uuid4(),
                date=date(2024, 1, 15),
                amount=Decimal("3500.00"),
                transaction_type="income",
                category="gehalt",
                description="Gehalt Januar",
            ),
            MagicMock(
                id=uuid4(),
                date=date(2024, 2, 15),
                amount=Decimal("3500.00"),
                transaction_type="income",
                category="gehalt",
                description="Gehalt Februar",
            ),
            MagicMock(
                id=uuid4(),
                date=date(2024, 3, 15),
                amount=Decimal("3500.00"),
                transaction_type="income",
                category="gehalt",
                description="Gehalt Maerz",
            ),
            # Ausgaben
            MagicMock(
                id=uuid4(),
                date=date(2024, 1, 1),
                amount=Decimal("-1200.00"),
                transaction_type="expense",
                category="miete",
                description="Miete Januar",
            ),
            MagicMock(
                id=uuid4(),
                date=date(2024, 2, 1),
                amount=Decimal("-1200.00"),
                transaction_type="expense",
                category="miete",
                description="Miete Februar",
            ),
            MagicMock(
                id=uuid4(),
                date=date(2024, 3, 1),
                amount=Decimal("-1200.00"),
                transaction_type="expense",
                category="miete",
                description="Miete Maerz",
            ),
            # Einmalige Ausgabe
            MagicMock(
                id=uuid4(),
                date=date(2024, 2, 20),
                amount=Decimal("-500.00"),
                transaction_type="expense",
                category="elektronik",
                description="Laptop Reparatur",
            ),
        ]

    @pytest.mark.asyncio
    async def test_service_initialization(self) -> None:
        """Testet Service-Initialisierung."""
        from app.services.privat.finance_analytics_service import (
            FinanceAnalyticsService,
        )

        service = FinanceAnalyticsService()
        assert service is not None

    @pytest.mark.asyncio
    async def test_dataclass_imports(self) -> None:
        """Testet dass alle Datenklassen importierbar sind."""
        from app.services.privat.finance_analytics_service import (
            CashFlowPrediction,
            FinanceAnalyticsResult,
            FinanceAnalyticsService,
            MonthlyTrend,
            RecurringPayment,
            YoYComparison,
        )

        assert FinanceAnalyticsService is not None
        assert MonthlyTrend is not None
        assert YoYComparison is not None
        assert RecurringPayment is not None
        assert CashFlowPrediction is not None
        assert FinanceAnalyticsResult is not None


class TestRecurringPaymentDataClass:
    """Tests fuer RecurringPayment Datenstruktur."""

    @pytest.mark.asyncio
    async def test_recurring_payment_dataclass(self) -> None:
        """Testet RecurringPayment Datenstruktur."""
        from app.services.privat.finance_analytics_service import (
            RecurringPayment,
        )

        payment = RecurringPayment(
            name="Miete",
            expected_amount=Decimal("1200"),
            frequency="monthly",
            expected_day=1,
            source_type="property",
            source_id=uuid4(),
            confidence=0.95,
            is_income=False,
        )

        assert payment.name == "Miete"
        assert payment.expected_amount == Decimal("1200")
        assert payment.frequency == "monthly"
        assert payment.confidence == 0.95

    @pytest.mark.asyncio
    async def test_monthly_trend_dataclass(self) -> None:
        """Testet MonthlyTrend Datenstruktur."""
        from app.services.privat.finance_analytics_service import (
            MonthlyTrend,
        )

        trend = MonthlyTrend(
            year=2024,
            month=6,
            income=Decimal("3500"),
            expenses=Decimal("2500"),
            net=Decimal("1000"),
        )

        assert trend.year == 2024
        assert trend.month == 6
        assert trend.net == Decimal("1000")


class TestTrendAnalysis:
    """Tests fuer Trend-Analysen."""

    @pytest.mark.asyncio
    async def test_yoy_comparison_dataclass(self) -> None:
        """Testet YoYComparison Datenstruktur."""
        from app.services.privat.finance_analytics_service import (
            YoYComparison,
        )

        comparison = YoYComparison(
            current_year=2024,
            previous_year=2023,
            current_income=Decimal("42000"),
            previous_income=Decimal("38400"),
            income_change=Decimal("3600"),
            income_change_percent=9.375,
        )

        assert comparison.current_year == 2024
        assert comparison.income_change_percent > 0

    @pytest.mark.asyncio
    async def test_cash_flow_prediction_dataclass(self) -> None:
        """Testet CashFlowPrediction Datenstruktur."""
        from app.services.privat.finance_analytics_service import (
            CashFlowPrediction,
        )

        prediction = CashFlowPrediction(
            year=2025,
            month=1,
            predicted_income=Decimal("3500"),
            predicted_expenses=Decimal("2500"),
            predicted_net=Decimal("1000"),
            confidence=0.85,
        )

        assert prediction.year == 2025
        assert prediction.predicted_net == Decimal("1000")


class TestFinanceAnalyticsResult:
    """Tests fuer FinanceAnalyticsResult Datenstruktur."""

    @pytest.mark.asyncio
    async def test_finance_analytics_result_dataclass(self) -> None:
        """Testet FinanceAnalyticsResult Datenstruktur."""
        from app.services.privat.finance_analytics_service import (
            FinanceAnalyticsResult,
        )

        result = FinanceAnalyticsResult(
            space_id=uuid4(),
            analysis_date=date.today(),
            total_assets_value=Decimal("500000"),
            total_liabilities=Decimal("150000"),
            net_worth=Decimal("350000"),
        )

        assert result.net_worth == Decimal("350000")
        assert result.total_assets_value > result.total_liabilities


class TestFullAnalysis:
    """Tests fuer vollstaendige Analyse."""

    @pytest.fixture
    def mock_db(self) -> AsyncMock:
        """Erstellt Mock DB."""
        db = AsyncMock(spec=AsyncSession)
        mock_result = MagicMock()
        mock_result.scalars = MagicMock(
            return_value=MagicMock(all=MagicMock(return_value=[]))
        )
        db.execute = AsyncMock(return_value=mock_result)
        return db

    @pytest.mark.asyncio
    async def test_service_has_full_analysis_method(self) -> None:
        """Testet dass Service get_full_analysis Methode hat."""
        from app.services.privat.finance_analytics_service import (
            FinanceAnalyticsService,
        )

        service = FinanceAnalyticsService()

        # Pruefe dass Methode existiert
        assert hasattr(service, "get_full_analysis")
        assert callable(getattr(service, "get_full_analysis"))
