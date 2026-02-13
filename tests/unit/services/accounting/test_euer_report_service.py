"""
Unit Tests für EUeRReportService

Testet die Generierung von Einnahmen-Überschuss-Rechnung (EÜR) Reports.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
from decimal import Decimal
from datetime import date
from typing import List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.accounting.euer_report_service import (
    EUeRReportService,
    EUeRReport,
    get_euer_report_service
)


@pytest.fixture
def mock_db() -> AsyncSession:
    """Mock AsyncSession für Datenbanktests."""
    db = AsyncMock(spec=AsyncSession)
    db.execute = AsyncMock()
    db.commit = AsyncMock()
    return db


@pytest.fixture
def euer_service(mock_db: AsyncSession) -> EUeRReportService:
    """EUeRReportService Instanz für Tests."""
    return EUeRReportService(db=mock_db)


@pytest.fixture
def company_id() -> uuid4:
    """Test company_id."""
    return uuid4()


@pytest.fixture
def fiscal_year() -> int:
    """Test fiscal year."""
    return 2025


def create_mock_row(account_number: str, total_debit: Decimal, total_credit: Decimal) -> MagicMock:
    """Erstellt eine Mock-Datenbank-Zeile."""
    row = MagicMock()
    row.account_number = account_number
    row.total_debit = total_debit
    row.total_credit = total_credit
    return row


class TestGenerateEuer:
    """Tests für generate_euer Methode."""

    @pytest.mark.asyncio
    async def test_generate_euer_profit(
        self,
        euer_service: EUeRReportService,
        mock_db: AsyncSession,
        company_id: uuid4,
        fiscal_year: int
    ) -> None:
        """Test: Revenue > Expenses = positive profit."""
        # Arrange
        mock_rows = [
            create_mock_row("8000", Decimal("0"), Decimal("50000")),  # Revenue
            create_mock_row("8100", Decimal("0"), Decimal("30000")),  # Revenue
            create_mock_row("3000", Decimal("20000"), Decimal("0")),  # Expense
            create_mock_row("4000", Decimal("15000"), Decimal("0")),  # Expense
        ]
        mock_result = MagicMock()
        mock_result.fetchall.return_value = mock_rows
        mock_db.execute.return_value = mock_result

        # Act
        result = await euer_service.generate_euer(company_id, fiscal_year)

        # Assert
        assert isinstance(result, EUeRReport)
        assert result.company_id == company_id
        assert result.fiscal_year == fiscal_year
        assert result.total_revenue == Decimal("80000")  # 50000 + 30000
        assert result.total_expenses == Decimal("35000")  # 20000 + 15000
        assert result.profit_loss == Decimal("45000")  # 80000 - 35000
        assert result.period_start == date(fiscal_year, 1, 1)
        assert result.period_end == date(fiscal_year, 12, 31)

    @pytest.mark.asyncio
    async def test_generate_euer_loss(
        self,
        euer_service: EUeRReportService,
        mock_db: AsyncSession,
        company_id: uuid4,
        fiscal_year: int
    ) -> None:
        """Test: Revenue < Expenses = negative profit."""
        # Arrange
        mock_rows = [
            create_mock_row("8000", Decimal("0"), Decimal("30000")),  # Revenue
            create_mock_row("3000", Decimal("40000"), Decimal("0")),  # Expense
            create_mock_row("4000", Decimal("25000"), Decimal("0")),  # Expense
        ]
        mock_result = MagicMock()
        mock_result.fetchall.return_value = mock_rows
        mock_db.execute.return_value = mock_result

        # Act
        result = await euer_service.generate_euer(company_id, fiscal_year)

        # Assert
        assert result.total_revenue == Decimal("30000")
        assert result.total_expenses == Decimal("65000")  # 40000 + 25000
        assert result.profit_loss == Decimal("-35000")  # 30000 - 65000

    @pytest.mark.asyncio
    async def test_generate_euer_empty(
        self,
        euer_service: EUeRReportService,
        mock_db: AsyncSession,
        company_id: uuid4,
        fiscal_year: int
    ) -> None:
        """Test: No entries = all zeros."""
        # Arrange
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        mock_db.execute.return_value = mock_result

        # Act
        result = await euer_service.generate_euer(company_id, fiscal_year)

        # Assert
        assert result.company_id == company_id
        assert result.fiscal_year == fiscal_year
        assert result.total_revenue == Decimal("0")
        assert result.total_expenses == Decimal("0")
        assert result.profit_loss == Decimal("0")
        assert result.period_start == date(fiscal_year, 1, 1)
        assert result.period_end == date(fiscal_year, 12, 31)

    @pytest.mark.asyncio
    async def test_generate_euer_period_boundaries(
        self,
        euer_service: EUeRReportService,
        mock_db: AsyncSession,
        company_id: uuid4
    ) -> None:
        """Test: Check period_start/end = Jan 1 / Dec 31."""
        # Arrange
        test_year = 2024
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        mock_db.execute.return_value = mock_result

        # Act
        result = await euer_service.generate_euer(company_id, test_year)

        # Assert
        assert result.period_start == date(2024, 1, 1)
        assert result.period_end == date(2024, 12, 31)

    @pytest.mark.asyncio
    async def test_generate_euer_revenue_accounts_class_8(
        self,
        euer_service: EUeRReportService,
        mock_db: AsyncSession,
        company_id: uuid4,
        fiscal_year: int
    ) -> None:
        """Test: Account 8xxx counted as revenue."""
        # Arrange
        mock_rows = [
            create_mock_row("8000", Decimal("0"), Decimal("10000")),
            create_mock_row("8100", Decimal("0"), Decimal("15000")),
            create_mock_row("8500", Decimal("0"), Decimal("20000")),
            create_mock_row("8999", Decimal("0"), Decimal("5000")),
        ]
        mock_result = MagicMock()
        mock_result.fetchall.return_value = mock_rows
        mock_db.execute.return_value = mock_result

        # Act
        result = await euer_service.generate_euer(company_id, fiscal_year)

        # Assert
        assert result.total_revenue == Decimal("50000")  # All 8xxx accounts
        assert result.total_expenses == Decimal("0")

    @pytest.mark.asyncio
    async def test_generate_euer_expense_accounts_class_3_4(
        self,
        euer_service: EUeRReportService,
        mock_db: AsyncSession,
        company_id: uuid4,
        fiscal_year: int
    ) -> None:
        """Test: Accounts 3xxx/4xxx counted as expense."""
        # Arrange
        mock_rows = [
            create_mock_row("3000", Decimal("10000"), Decimal("0")),
            create_mock_row("3500", Decimal("15000"), Decimal("0")),
            create_mock_row("3999", Decimal("5000"), Decimal("0")),
            create_mock_row("4000", Decimal("12000"), Decimal("0")),
            create_mock_row("4500", Decimal("8000"), Decimal("0")),
            create_mock_row("4999", Decimal("3000"), Decimal("0")),
        ]
        mock_result = MagicMock()
        mock_result.fetchall.return_value = mock_rows
        mock_db.execute.return_value = mock_result

        # Act
        result = await euer_service.generate_euer(company_id, fiscal_year)

        # Assert
        assert result.total_revenue == Decimal("0")
        assert result.total_expenses == Decimal("53000")  # All 3xxx and 4xxx accounts

    @pytest.mark.asyncio
    async def test_generate_euer_ignores_other_accounts(
        self,
        euer_service: EUeRReportService,
        mock_db: AsyncSession,
        company_id: uuid4,
        fiscal_year: int
    ) -> None:
        """Test: Accounts 0xxx, 1xxx, 2xxx not counted."""
        # Arrange
        mock_rows = [
            # These should be counted
            create_mock_row("8000", Decimal("0"), Decimal("50000")),  # Revenue
            create_mock_row("3000", Decimal("20000"), Decimal("0")),  # Expense
            # These should be ignored
            create_mock_row("0000", Decimal("10000"), Decimal("10000")),  # Assets
            create_mock_row("1000", Decimal("15000"), Decimal("5000")),   # Assets
            create_mock_row("2000", Decimal("8000"), Decimal("12000")),   # Liabilities
            create_mock_row("5000", Decimal("5000"), Decimal("5000")),    # Other
            create_mock_row("6000", Decimal("3000"), Decimal("3000")),    # Other
            create_mock_row("7000", Decimal("2000"), Decimal("2000")),    # Other
            create_mock_row("9000", Decimal("1000"), Decimal("1000")),    # Other
        ]
        mock_result = MagicMock()
        mock_result.fetchall.return_value = mock_rows
        mock_db.execute.return_value = mock_result

        # Act
        result = await euer_service.generate_euer(company_id, fiscal_year)

        # Assert
        assert result.total_revenue == Decimal("50000")  # Only 8xxx
        assert result.total_expenses == Decimal("20000")  # Only 3xxx/4xxx
        assert result.profit_loss == Decimal("30000")

    @pytest.mark.asyncio
    async def test_generate_euer_revenue_credit_sided(
        self,
        euer_service: EUeRReportService,
        mock_db: AsyncSession,
        company_id: uuid4,
        fiscal_year: int
    ) -> None:
        """Test: Revenue = credit - debit."""
        # Arrange
        mock_rows = [
            # Revenue account with both debit and credit
            create_mock_row("8000", Decimal("5000"), Decimal("50000")),
            # Should calculate as 50000 - 5000 = 45000
        ]
        mock_result = MagicMock()
        mock_result.fetchall.return_value = mock_rows
        mock_db.execute.return_value = mock_result

        # Act
        result = await euer_service.generate_euer(company_id, fiscal_year)

        # Assert
        assert result.total_revenue == Decimal("45000")  # credit - debit


class TestExportAnlageEuer:
    """Tests für export_anlage_euer Methode."""

    @pytest.mark.asyncio
    async def test_export_anlage_euer_calls_eur_service(
        self,
        euer_service: EUeRReportService,
        mock_db: AsyncSession,
        company_id: uuid4,
        fiscal_year: int
    ) -> None:
        """Test: Delegates to EURService."""
        # Arrange
        mock_eur_data = {
            "betriebseinnahmen": Decimal("100000"),
            "betriebsausgaben": Decimal("60000"),
            "gewinn": Decimal("40000")
        }

        with patch("app.services.accounting.euer_report_service.EURService") as MockEURService:
            mock_eur_instance = AsyncMock()
            mock_eur_instance.generate_anlage_eur.return_value = mock_eur_data
            MockEURService.return_value = mock_eur_instance

            # Act
            result = await euer_service.export_anlage_euer(company_id, fiscal_year)

            # Assert
            MockEURService.assert_called_once_with(mock_db)
            mock_eur_instance.generate_anlage_eur.assert_called_once_with(
                company_id=company_id,
                fiscal_year=fiscal_year
            )
            assert result == mock_eur_data

    @pytest.mark.asyncio
    async def test_export_anlage_euer_returns_dict(
        self,
        euer_service: EUeRReportService,
        mock_db: AsyncSession,
        company_id: uuid4,
        fiscal_year: int
    ) -> None:
        """Test: Returns dict with Anlage data."""
        # Arrange
        mock_eur_data = {
            "betriebseinnahmen": Decimal("80000"),
            "betriebsausgaben": Decimal("50000"),
            "gewinn": Decimal("30000"),
            "steuerpflichtiger_gewinn": Decimal("30000")
        }

        with patch("app.services.accounting.euer_report_service.EURService") as MockEURService:
            mock_eur_instance = AsyncMock()
            mock_eur_instance.generate_anlage_eur.return_value = mock_eur_data
            MockEURService.return_value = mock_eur_instance

            # Act
            result = await euer_service.export_anlage_euer(company_id, fiscal_year)

            # Assert
            assert isinstance(result, dict)
            assert "betriebseinnahmen" in result
            assert "betriebsausgaben" in result
            assert "gewinn" in result
            assert result["gewinn"] == Decimal("30000")

    @pytest.mark.asyncio
    async def test_export_anlage_euer_logs_profit(
        self,
        euer_service: EUeRReportService,
        mock_db: AsyncSession,
        company_id: uuid4,
        fiscal_year: int
    ) -> None:
        """Test: Logs profit_loss."""
        # Arrange
        mock_eur_data = {
            "gewinn": Decimal("25000")
        }

        with patch("app.services.accounting.euer_report_service.EURService") as MockEURService:
            with patch("app.services.accounting.euer_report_service.logger") as mock_logger:
                mock_eur_instance = AsyncMock()
                mock_eur_instance.generate_anlage_eur.return_value = mock_eur_data
                MockEURService.return_value = mock_eur_instance

                # Act
                await euer_service.export_anlage_euer(company_id, fiscal_year)

                # Assert
                # Verify logger was called (implementation-specific)
                assert mock_logger.info.called or mock_logger.debug.called


class TestGetEuerReportService:
    """Tests für get_euer_report_service Factory-Funktion."""

    @pytest.mark.asyncio
    async def test_get_euer_report_service_factory(self, mock_db: AsyncSession) -> None:
        """Test: Creates instance from dependency."""
        # Act
        service = get_euer_report_service(db=mock_db)

        # Assert
        assert isinstance(service, EUeRReportService)
        assert service.db == mock_db
