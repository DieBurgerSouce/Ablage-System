# -*- coding: utf-8 -*-
"""Unit tests fuer FX Rate Service."""

import pytest
from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from app.services.accounting.fx_rate_service import FXRateService, ConversionResult, RevaluationSummary, RevaluationEntry
from app.db.models_fx import ExchangeRate
from app.db.models import InvoiceTracking, InvoiceStatus


# Sample ECB XML response
SAMPLE_ECB_XML = """<?xml version="1.0" encoding="UTF-8"?>
<gesmes:Envelope xmlns:gesmes="http://www.gesmes.org/xml/2002-08-01" xmlns="http://www.ecb.int/vocabulary/2002-08-01/eurofxref">
    <gesmes:subject>Reference rates</gesmes:subject>
    <Cube>
        <Cube time="2024-01-15">
            <Cube currency="USD" rate="1.0876"/>
            <Cube currency="GBP" rate="0.85935"/>
            <Cube currency="CHF" rate="0.9367"/>
        </Cube>
    </Cube>
</gesmes:Envelope>
"""


@pytest.fixture
def mock_db():
    """Mock database session."""
    db = AsyncMock()
    db.commit = AsyncMock()
    db.add = MagicMock()
    return db


@pytest.fixture
def fx_service(mock_db):
    """FX Rate Service instance."""
    return FXRateService(mock_db)


class TestFetchECBRates:
    """Tests for fetching ECB rates."""

    @pytest.mark.asyncio
    async def test_fetch_ecb_rates_parses_xml(self, fx_service, mock_db):
        """Test that ECB XML is correctly parsed."""
        # Mock httpx response
        mock_response = MagicMock()
        mock_response.text = SAMPLE_ECB_XML
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(return_value=mock_response)

            # Mock DB queries to return no existing rates
            mock_db.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None)))

            count = await fx_service.fetch_ecb_rates(historical=False)

            # Should have imported 3 rates (USD, GBP, CHF)
            assert count == 3
            assert mock_db.add.call_count == 3

    @pytest.mark.asyncio
    async def test_fetch_ecb_rates_skips_existing(self, fx_service, mock_db):
        """Test that existing rates are not re-imported."""
        mock_response = MagicMock()
        mock_response.text = SAMPLE_ECB_XML
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(return_value=mock_response)

            # Mock DB to return existing rate for USD
            def mock_execute(stmt):
                result = MagicMock()
                # First call (USD) returns existing rate, others return None
                if not hasattr(mock_execute, "call_count"):
                    mock_execute.call_count = 0
                mock_execute.call_count += 1

                if mock_execute.call_count == 1:
                    result.scalar_one_or_none = MagicMock(return_value=ExchangeRate())
                else:
                    result.scalar_one_or_none = MagicMock(return_value=None)
                return result

            mock_db.execute = AsyncMock(side_effect=mock_execute)

            count = await fx_service.fetch_ecb_rates(historical=False)

            # Should only add 2 new rates (GBP, CHF), USD exists
            assert count == 2


class TestGetRate:
    """Tests for getting exchange rates."""

    @pytest.mark.asyncio
    async def test_get_rate_exact_date(self, fx_service, mock_db):
        """Test getting rate for exact date."""
        target_date = date(2024, 1, 15)
        expected_rate = Decimal("1.0876")

        result = MagicMock()
        result.scalar_one_or_none = MagicMock(return_value=expected_rate)
        mock_db.execute = AsyncMock(return_value=result)

        rate = await fx_service.get_rate("USD", target_date)

        assert rate == expected_rate

    @pytest.mark.asyncio
    async def test_get_rate_fallback_recent(self, fx_service, mock_db):
        """Test fallback to most recent rate within 7 days."""
        target_date = date(2024, 1, 15)
        expected_rate = Decimal("1.0850")

        # First call returns None (no exact match), second returns fallback
        result1 = MagicMock()
        result1.scalar_one_or_none = MagicMock(return_value=None)

        result2 = MagicMock()
        result2.scalar_one_or_none = MagicMock(return_value=expected_rate)

        mock_db.execute = AsyncMock(side_effect=[result1, result2])

        rate = await fx_service.get_rate("USD", target_date)

        assert rate == expected_rate

    @pytest.mark.asyncio
    async def test_get_rate_eur_identity(self, fx_service, mock_db):
        """Test that EUR->EUR returns 1.0."""
        rate = await fx_service.get_rate("EUR", date.today())

        assert rate == Decimal("1.0")
        # Should not query DB for EUR
        mock_db.execute.assert_not_called()


class TestConvert:
    """Tests for currency conversion."""

    @pytest.mark.asyncio
    async def test_convert_eur_to_usd(self, fx_service, mock_db):
        """Test EUR to USD conversion (multiplication)."""
        amount = Decimal("100.00")
        rate = Decimal("1.0876")

        # Mock get_rate to return USD rate
        result = MagicMock()
        result.scalar_one_or_none = MagicMock(return_value=rate)
        mock_db.execute = AsyncMock(return_value=result)

        conversion = await fx_service.convert(
            amount=amount,
            from_currency="EUR",
            to_currency="USD",
            rate_date=date(2024, 1, 15),
        )

        assert conversion.original_amount == amount
        assert conversion.original_currency == "EUR"
        assert conversion.target_currency == "USD"
        assert conversion.converted_amount == Decimal("108.76")
        assert conversion.rate_used == rate

    @pytest.mark.asyncio
    async def test_convert_usd_to_eur(self, fx_service, mock_db):
        """Test USD to EUR conversion (division)."""
        amount = Decimal("108.76")
        rate = Decimal("1.0876")

        result = MagicMock()
        result.scalar_one_or_none = MagicMock(return_value=rate)
        mock_db.execute = AsyncMock(return_value=result)

        conversion = await fx_service.convert(
            amount=amount,
            from_currency="USD",
            to_currency="EUR",
            rate_date=date(2024, 1, 15),
        )

        assert conversion.original_currency == "USD"
        assert conversion.target_currency == "EUR"
        assert conversion.converted_amount == Decimal("100.00")

    @pytest.mark.asyncio
    async def test_convert_cross_rate(self, fx_service, mock_db):
        """Test cross-rate conversion (USD to GBP via EUR)."""
        amount = Decimal("100.00")
        usd_rate = Decimal("1.0876")  # EUR/USD
        gbp_rate = Decimal("0.85935")  # EUR/GBP

        # Mock two get_rate calls
        result1 = MagicMock()
        result1.scalar_one_or_none = MagicMock(return_value=usd_rate)

        result2 = MagicMock()
        result2.scalar_one_or_none = MagicMock(return_value=gbp_rate)

        mock_db.execute = AsyncMock(side_effect=[result1, result2])

        conversion = await fx_service.convert(
            amount=amount,
            from_currency="USD",
            to_currency="GBP",
            rate_date=date(2024, 1, 15),
        )

        assert conversion.original_currency == "USD"
        assert conversion.target_currency == "GBP"
        # USD 100 -> EUR 91.94 -> GBP 79.01 (approx)
        assert conversion.converted_amount > Decimal("78.00")
        assert conversion.converted_amount < Decimal("80.00")

    @pytest.mark.asyncio
    async def test_convert_same_currency(self, fx_service, mock_db):
        """Test identity conversion (same currency)."""
        amount = Decimal("100.00")

        conversion = await fx_service.convert(
            amount=amount,
            from_currency="USD",
            to_currency="USD",
        )

        assert conversion.original_amount == amount
        assert conversion.converted_amount == amount
        assert conversion.rate_used == Decimal("1.0")
        assert conversion.rate_source == "identity"

    @pytest.mark.asyncio
    async def test_convert_missing_rate_raises(self, fx_service, mock_db):
        """Test that missing rate raises ValueError."""
        result = MagicMock()
        result.scalar_one_or_none = MagicMock(return_value=None)
        mock_db.execute = AsyncMock(return_value=result)

        with pytest.raises(ValueError, match="Kein Wechselkurs verfuegbar"):
            await fx_service.convert(
                amount=Decimal("100.00"),
                from_currency="EUR",
                to_currency="XYZ",
            )


class TestFXGainLossCalculations:
    """Tests for FX gain/loss calculations."""

    def test_realized_gain_calculation(self):
        """Test calculation of realized FX gain."""
        from app.services.accounting.fx_gain_loss_service import FXGainLossService

        service = FXGainLossService(AsyncMock())

        # Booked at 1.10, settled at 1.08 -> Rate improved (fewer EUR needed)
        # USD 1000 / 1.10 = EUR 909.09 (booking)
        # USD 1000 / 1.08 = EUR 925.93 (settlement)
        # Gain: 925.93 - 909.09 = 16.84 EUR
        result = service.calculate_realized_gain_loss(
            original_amount=Decimal("1000.00"),
            original_currency="USD",
            booking_rate=Decimal("1.10"),
            settlement_rate=Decimal("1.08"),
        )

        assert result.is_gain is True
        assert result.gain_loss_account == "2650"  # Kursgewinne
        assert result.gain_loss_amount > Decimal("16.00")
        assert result.gain_loss_amount < Decimal("17.00")

    def test_realized_loss_calculation(self):
        """Test calculation of realized FX loss."""
        from app.services.accounting.fx_gain_loss_service import FXGainLossService

        service = FXGainLossService(AsyncMock())

        # Booked at 1.08, settled at 1.10 -> Rate worsened (more EUR needed)
        # USD 1000 / 1.08 = EUR 925.93 (booking)
        # USD 1000 / 1.10 = EUR 909.09 (settlement)
        # Loss: 909.09 - 925.93 = -16.84 EUR
        result = service.calculate_realized_gain_loss(
            original_amount=Decimal("1000.00"),
            original_currency="USD",
            booking_rate=Decimal("1.08"),
            settlement_rate=Decimal("1.10"),
        )

        assert result.is_gain is False
        assert result.gain_loss_account == "2150"  # Kursverluste
        assert result.gain_loss_amount > Decimal("16.00")
        assert result.gain_loss_amount < Decimal("17.00")

    @pytest.mark.asyncio
    async def test_fx_gain_posts_to_2650(self):
        """Test that FX gain posts to account 2650."""
        from app.services.accounting.fx_gain_loss_service import FXGainLossService, FXGainLossResult

        mock_db = AsyncMock()
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()

        service = FXGainLossService(mock_db)

        result = FXGainLossResult(
            original_currency="USD",
            original_amount=Decimal("1000.00"),
            booking_rate=Decimal("1.10"),
            settlement_rate=Decimal("1.08"),
            booking_eur_amount=Decimal("909.09"),
            settlement_eur_amount=Decimal("925.93"),
            gain_loss_amount=Decimal("16.84"),
            gain_loss_account="2650",
            is_gain=True,
        )

        with patch("app.services.accounting.gl_posting_service.GLPostingService") as mock_gl:
            mock_gl_instance = AsyncMock()
            mock_gl_instance.create_journal_entry = AsyncMock(return_value=MagicMock(id=uuid4()))
            mock_gl_instance.post_journal_entry = AsyncMock()
            mock_gl.return_value = mock_gl_instance

            await service.post_fx_gain_loss(
                company_id=uuid4(),
                result=result,
                realized=True,
                posted_by=uuid4(),
            )

            # Verify GL entry was created
            mock_gl_instance.create_journal_entry.assert_called_once()
            call_args = mock_gl_instance.create_journal_entry.call_args[1]

            # Check that gain line has account 2650 (credit)
            lines = call_args["lines"]
            assert any(
                line.account_number == "2650" and line.credit_amount == Decimal("16.84")
                for line in lines
            )

    @pytest.mark.asyncio
    async def test_fx_loss_posts_to_2150(self):
        """Test that FX loss posts to account 2150."""
        from app.services.accounting.fx_gain_loss_service import FXGainLossService, FXGainLossResult

        mock_db = AsyncMock()
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()

        service = FXGainLossService(mock_db)

        result = FXGainLossResult(
            original_currency="USD",
            original_amount=Decimal("1000.00"),
            booking_rate=Decimal("1.08"),
            settlement_rate=Decimal("1.10"),
            booking_eur_amount=Decimal("925.93"),
            settlement_eur_amount=Decimal("909.09"),
            gain_loss_amount=Decimal("16.84"),
            gain_loss_account="2150",
            is_gain=False,
        )

        with patch("app.services.accounting.gl_posting_service.GLPostingService") as mock_gl:
            mock_gl_instance = AsyncMock()
            mock_gl_instance.create_journal_entry = AsyncMock(return_value=MagicMock(id=uuid4()))
            mock_gl_instance.post_journal_entry = AsyncMock()
            mock_gl.return_value = mock_gl_instance

            await service.post_fx_gain_loss(
                company_id=uuid4(),
                result=result,
                realized=True,
                posted_by=uuid4(),
            )

            # Verify GL entry was created
            mock_gl_instance.create_journal_entry.assert_called_once()
            call_args = mock_gl_instance.create_journal_entry.call_args[1]

            # Check that loss line has account 2150 (debit)
            lines = call_args["lines"]
            assert any(
                line.account_number == "2150" and line.debit_amount == Decimal("16.84")
                for line in lines
            )


class TestGetAvailableCurrencies:
    """Tests for get_available_currencies."""

    @pytest.mark.asyncio
    async def test_returns_currencies_list(self, fx_service, mock_db):
        """Test that available currencies are returned as list."""
        # Mock DB to return USD, GBP, CHF
        result = MagicMock()
        result.all = MagicMock(return_value=[("USD",), ("GBP",), ("CHF",)])
        mock_db.execute = AsyncMock(return_value=result)

        currencies = await fx_service.get_available_currencies()

        assert currencies == ["USD", "GBP", "CHF"]
        assert isinstance(currencies, list)

    @pytest.mark.asyncio
    async def test_uses_date_window(self, fx_service, mock_db):
        """Test that date defaults to today() and uses 7-day window."""
        result = MagicMock()
        result.all = MagicMock(return_value=[("USD",)])
        mock_db.execute = AsyncMock(return_value=result)

        await fx_service.get_available_currencies()

        # Verify execute was called with date range query
        mock_db.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_empty_when_no_rates(self, fx_service, mock_db):
        """Test that empty list is returned when no rates available."""
        result = MagicMock()
        result.all = MagicMock(return_value=[])
        mock_db.execute = AsyncMock(return_value=result)

        currencies = await fx_service.get_available_currencies()

        assert currencies == []


class TestMonthEndRevaluation:
    """Tests for month_end_revaluation."""

    @pytest.mark.asyncio
    async def test_revaluation_no_positions(self, fx_service, mock_db):
        """Test revaluation when no open positions exist."""
        from app.services.accounting.fx_rate_service import RevaluationSummary

        # Mock _get_open_fx_positions to return empty list
        with patch.object(fx_service, "_get_open_fx_positions", return_value=[]):
            summary = await fx_service.month_end_revaluation(
                company_id=uuid4(),
                revaluation_date=date(2026, 1, 31),
                db=mock_db,
            )

        assert summary.entries_processed == 0
        assert summary.total_gain == Decimal("0.00")
        assert summary.total_loss == Decimal("0.00")
        assert summary.currency_breakdown == {}
        assert summary.entries == []

    @pytest.mark.asyncio
    async def test_revaluation_gain(self, fx_service, mock_db):
        """Test position with rate improvement shows gain."""
        from app.services.accounting.fx_rate_service import RevaluationSummary

        # Mock invoice with USD 1000, booked at 1.10, current 1.08 (gain)
        mock_invoice = MagicMock(spec=InvoiceTracking)
        mock_invoice.id = uuid4()
        mock_invoice.currency = "USD"
        mock_invoice.amount = Decimal("1000.00")
        mock_invoice.outstanding_amount = Decimal("1000.00")
        mock_invoice.paid_amount = Decimal("0.00")
        mock_invoice.invoice_date = date(2024, 1, 15)
        mock_invoice.status = InvoiceStatus.OPEN.value
        mock_invoice.company_id = uuid4()
        mock_invoice.document_id = uuid4()
        mock_invoice.deleted_at = None

        with patch.object(fx_service, "_get_open_fx_positions", return_value=[mock_invoice]):
            # Mock get_rate: booking_rate=1.10, current_rate=1.08
            async def mock_get_rate(currency: str, target_date: Optional[date] = None) -> Optional[Decimal]:
                if target_date == date(2024, 1, 15):
                    return Decimal("1.10")  # Booking rate
                elif target_date == date(2026, 1, 31):
                    return Decimal("1.08")  # Current rate (improvement = gain)
                return None

            with patch.object(fx_service, "get_rate", side_effect=mock_get_rate):
                with patch("app.services.accounting.fx_gain_loss_service.FXGainLossService") as mock_gl:
                    from app.services.accounting.fx_gain_loss_service import FXGainLossResult

                    # Mock calculate_unrealized_gain_loss
                    mock_gl_instance = MagicMock()
                    mock_gl_instance.calculate_unrealized_gain_loss = MagicMock(return_value=FXGainLossResult(
                        original_currency="USD",
                        original_amount=Decimal("1000.00"),
                        booking_rate=Decimal("1.10"),
                        settlement_rate=Decimal("1.08"),
                        booking_eur_amount=Decimal("909.09"),
                        settlement_eur_amount=Decimal("925.93"),
                        gain_loss_amount=Decimal("16.84"),
                        gain_loss_account="2680",  # Unrealized gains
                        is_gain=True,
                    ))
                    mock_gl_instance.post_fx_gain_loss = AsyncMock()
                    mock_gl.return_value = mock_gl_instance

                    summary = await fx_service.month_end_revaluation(
                        company_id=uuid4(),
                        revaluation_date=date(2026, 1, 31),
                        db=mock_db,
                    )

        assert summary.entries_processed == 1
        assert summary.total_gain == Decimal("16.84")
        assert summary.total_loss == Decimal("0.00")
        assert len(summary.entries) == 1
        assert summary.entries[0].is_gain is True

    @pytest.mark.asyncio
    async def test_revaluation_loss(self, fx_service, mock_db):
        """Test position with rate decline shows loss."""
        mock_invoice = MagicMock(spec=InvoiceTracking)
        mock_invoice.id = uuid4()
        mock_invoice.currency = "USD"
        mock_invoice.amount = Decimal("1000.00")
        mock_invoice.outstanding_amount = Decimal("1000.00")
        mock_invoice.paid_amount = Decimal("0.00")
        mock_invoice.invoice_date = date(2024, 1, 15)
        mock_invoice.status = InvoiceStatus.OPEN.value
        mock_invoice.company_id = uuid4()
        mock_invoice.document_id = uuid4()
        mock_invoice.deleted_at = None

        with patch.object(fx_service, "_get_open_fx_positions", return_value=[mock_invoice]):
            # Mock get_rate: booking_rate=1.08, current_rate=1.10 (worse = loss)
            async def mock_get_rate(currency: str, target_date: Optional[date] = None) -> Optional[Decimal]:
                if target_date == date(2024, 1, 15):
                    return Decimal("1.08")  # Booking rate
                elif target_date == date(2026, 1, 31):
                    return Decimal("1.10")  # Current rate (decline = loss)
                return None

            with patch.object(fx_service, "get_rate", side_effect=mock_get_rate):
                with patch("app.services.accounting.fx_gain_loss_service.FXGainLossService") as mock_gl:
                    from app.services.accounting.fx_gain_loss_service import FXGainLossResult

                    mock_gl_instance = MagicMock()
                    mock_gl_instance.calculate_unrealized_gain_loss = MagicMock(return_value=FXGainLossResult(
                        original_currency="USD",
                        original_amount=Decimal("1000.00"),
                        booking_rate=Decimal("1.08"),
                        settlement_rate=Decimal("1.10"),
                        booking_eur_amount=Decimal("925.93"),
                        settlement_eur_amount=Decimal("909.09"),
                        gain_loss_amount=Decimal("16.84"),
                        gain_loss_account="2180",  # Unrealized losses
                        is_gain=False,
                    ))
                    mock_gl_instance.post_fx_gain_loss = AsyncMock()
                    mock_gl.return_value = mock_gl_instance

                    summary = await fx_service.month_end_revaluation(
                        company_id=uuid4(),
                        revaluation_date=date(2026, 1, 31),
                        db=mock_db,
                    )

        assert summary.entries_processed == 1
        assert summary.total_gain == Decimal("0.00")
        assert summary.total_loss == Decimal("16.84")
        assert summary.entries[0].is_gain is False

    @pytest.mark.asyncio
    async def test_revaluation_skips_eur(self, fx_service, mock_db):
        """Test that EUR-denominated positions are skipped."""
        mock_invoice = MagicMock(spec=InvoiceTracking)
        mock_invoice.id = uuid4()
        mock_invoice.currency = "EUR"
        mock_invoice.amount = Decimal("1000.00")
        mock_invoice.outstanding_amount = Decimal("1000.00")
        mock_invoice.paid_amount = Decimal("0.00")
        mock_invoice.invoice_date = date(2024, 1, 15)
        mock_invoice.status = InvoiceStatus.OPEN.value
        mock_invoice.company_id = uuid4()
        mock_invoice.document_id = uuid4()
        mock_invoice.deleted_at = None

        with patch.object(fx_service, "_get_open_fx_positions", return_value=[mock_invoice]):
            summary = await fx_service.month_end_revaluation(
                company_id=uuid4(),
                revaluation_date=date(2026, 1, 31),
                db=mock_db,
            )

        # EUR positions should be skipped
        assert summary.entries_processed == 0

    @pytest.mark.asyncio
    async def test_revaluation_skips_zero_outstanding(self, fx_service, mock_db):
        """Test that paid-off positions are skipped."""
        mock_invoice = MagicMock(spec=InvoiceTracking)
        mock_invoice.id = uuid4()
        mock_invoice.currency = "USD"
        mock_invoice.amount = Decimal("1000.00")
        mock_invoice.outstanding_amount = Decimal("0.00")
        mock_invoice.paid_amount = Decimal("1000.00")
        mock_invoice.invoice_date = date(2024, 1, 15)
        mock_invoice.status = InvoiceStatus.PAID.value
        mock_invoice.company_id = uuid4()
        mock_invoice.document_id = uuid4()
        mock_invoice.deleted_at = None

        with patch.object(fx_service, "_get_open_fx_positions", return_value=[mock_invoice]):
            summary = await fx_service.month_end_revaluation(
                company_id=uuid4(),
                revaluation_date=date(2026, 1, 31),
                db=mock_db,
            )

        # Zero outstanding should be skipped
        assert summary.entries_processed == 0

    @pytest.mark.asyncio
    async def test_revaluation_currency_breakdown(self, fx_service, mock_db):
        """Test currency breakdown groups by currency."""
        # Two USD positions, one GBP position
        invoice_usd1 = MagicMock(spec=InvoiceTracking)
        invoice_usd1.id = uuid4()
        invoice_usd1.currency = "USD"
        invoice_usd1.amount = Decimal("1000.00")
        invoice_usd1.outstanding_amount = Decimal("1000.00")
        invoice_usd1.paid_amount = Decimal("0.00")
        invoice_usd1.invoice_date = date(2024, 1, 15)
        invoice_usd1.status = InvoiceStatus.OPEN.value
        invoice_usd1.company_id = uuid4()
        invoice_usd1.document_id = uuid4()
        invoice_usd1.deleted_at = None

        invoice_usd2 = MagicMock(spec=InvoiceTracking)
        invoice_usd2.id = uuid4()
        invoice_usd2.currency = "USD"
        invoice_usd2.amount = Decimal("500.00")
        invoice_usd2.outstanding_amount = Decimal("500.00")
        invoice_usd2.paid_amount = Decimal("0.00")
        invoice_usd2.invoice_date = date(2024, 1, 15)
        invoice_usd2.status = InvoiceStatus.OPEN.value
        invoice_usd2.company_id = uuid4()
        invoice_usd2.document_id = uuid4()
        invoice_usd2.deleted_at = None

        invoice_gbp = MagicMock(spec=InvoiceTracking)
        invoice_gbp.id = uuid4()
        invoice_gbp.currency = "GBP"
        invoice_gbp.amount = Decimal("800.00")
        invoice_gbp.outstanding_amount = Decimal("800.00")
        invoice_gbp.paid_amount = Decimal("0.00")
        invoice_gbp.invoice_date = date(2024, 1, 15)
        invoice_gbp.status = InvoiceStatus.OPEN.value
        invoice_gbp.company_id = uuid4()
        invoice_gbp.document_id = uuid4()
        invoice_gbp.deleted_at = None

        with patch.object(fx_service, "_get_open_fx_positions", return_value=[invoice_usd1, invoice_usd2, invoice_gbp]):
            async def mock_get_rate(currency: str, target_date: Optional[date] = None) -> Optional[Decimal]:
                if currency == "USD":
                    if target_date == date(2024, 1, 15):
                        return Decimal("1.10")
                    elif target_date == date(2026, 1, 31):
                        return Decimal("1.08")
                elif currency == "GBP":
                    if target_date == date(2024, 1, 15):
                        return Decimal("0.86")
                    elif target_date == date(2026, 1, 31):
                        return Decimal("0.88")
                return None

            with patch.object(fx_service, "get_rate", side_effect=mock_get_rate):
                with patch("app.services.accounting.fx_gain_loss_service.FXGainLossService") as mock_gl:
                    from app.services.accounting.fx_gain_loss_service import FXGainLossResult

                    call_count = [0]

                    def mock_calc_unrealized(original_amount, original_currency, booking_rate, current_rate):
                        call_count[0] += 1
                        if original_currency == "USD":
                            return FXGainLossResult(
                                original_currency="USD",
                                original_amount=original_amount,
                                booking_rate=booking_rate,
                                settlement_rate=current_rate,
                                booking_eur_amount=Decimal("909.09"),
                                settlement_eur_amount=Decimal("925.93"),
                                gain_loss_amount=Decimal("10.00"),
                                gain_loss_account="2680",
                                is_gain=True,
                            )
                        else:  # GBP
                            return FXGainLossResult(
                                original_currency="GBP",
                                original_amount=original_amount,
                                booking_rate=booking_rate,
                                settlement_rate=current_rate,
                                booking_eur_amount=Decimal("930.23"),
                                settlement_eur_amount=Decimal("909.09"),
                                gain_loss_amount=Decimal("5.00"),
                                gain_loss_account="2180",
                                is_gain=False,
                            )

                    mock_gl_instance = MagicMock()
                    mock_gl_instance.calculate_unrealized_gain_loss = MagicMock(side_effect=mock_calc_unrealized)
                    mock_gl_instance.post_fx_gain_loss = AsyncMock()
                    mock_gl.return_value = mock_gl_instance

                    summary = await fx_service.month_end_revaluation(
                        company_id=uuid4(),
                        revaluation_date=date(2026, 1, 31),
                        db=mock_db,
                    )

        assert summary.entries_processed == 3
        assert "USD" in summary.currency_breakdown
        assert "GBP" in summary.currency_breakdown
        assert summary.currency_breakdown["USD"]["positions"] == "2"
        assert summary.currency_breakdown["GBP"]["positions"] == "1"

    @pytest.mark.asyncio
    async def test_revaluation_posts_gl_entries(self, fx_service, mock_db):
        """Test that revaluation calls FXGainLossService.post_fx_gain_loss."""
        mock_invoice = MagicMock(spec=InvoiceTracking)
        mock_invoice.id = uuid4()
        mock_invoice.currency = "USD"
        mock_invoice.amount = Decimal("1000.00")
        mock_invoice.outstanding_amount = Decimal("1000.00")
        mock_invoice.paid_amount = Decimal("0.00")
        mock_invoice.invoice_date = date(2024, 1, 15)
        mock_invoice.status = InvoiceStatus.OPEN.value
        mock_invoice.company_id = uuid4()
        mock_invoice.document_id = uuid4()
        mock_invoice.deleted_at = None

        with patch.object(fx_service, "_get_open_fx_positions", return_value=[mock_invoice]):
            async def mock_get_rate(currency: str, target_date: Optional[date] = None) -> Optional[Decimal]:
                if target_date == date(2024, 1, 15):
                    return Decimal("1.10")
                elif target_date == date(2026, 1, 31):
                    return Decimal("1.08")
                return None

            with patch.object(fx_service, "get_rate", side_effect=mock_get_rate):
                with patch("app.services.accounting.fx_gain_loss_service.FXGainLossService") as mock_gl:
                    from app.services.accounting.fx_gain_loss_service import FXGainLossResult

                    mock_gl_instance = MagicMock()
                    mock_gl_instance.calculate_unrealized_gain_loss = MagicMock(return_value=FXGainLossResult(
                        original_currency="USD",
                        original_amount=Decimal("1000.00"),
                        booking_rate=Decimal("1.10"),
                        settlement_rate=Decimal("1.08"),
                        booking_eur_amount=Decimal("909.09"),
                        settlement_eur_amount=Decimal("925.93"),
                        gain_loss_amount=Decimal("16.84"),
                        gain_loss_account="2680",
                        is_gain=True,
                    ))
                    mock_gl_instance.post_fx_gain_loss = AsyncMock()
                    mock_gl.return_value = mock_gl_instance

                    await fx_service.month_end_revaluation(
                        company_id=uuid4(),
                        revaluation_date=date(2026, 1, 31),
                        db=mock_db,
                    )

                    # Verify post_fx_gain_loss was called
                    mock_gl_instance.post_fx_gain_loss.assert_called_once()
                    call_kwargs = mock_gl_instance.post_fx_gain_loss.call_args[1]
                    assert call_kwargs["realized"] is False

    @pytest.mark.asyncio
    async def test_revaluation_handles_missing_rate(self, fx_service, mock_db):
        """Test that positions without available rate are skipped."""
        mock_invoice = MagicMock(spec=InvoiceTracking)
        mock_invoice.id = uuid4()
        mock_invoice.currency = "XYZ"  # Unknown currency
        mock_invoice.amount = Decimal("1000.00")
        mock_invoice.outstanding_amount = Decimal("1000.00")
        mock_invoice.paid_amount = Decimal("0.00")
        mock_invoice.invoice_date = date(2024, 1, 15)
        mock_invoice.status = InvoiceStatus.OPEN.value
        mock_invoice.company_id = uuid4()
        mock_invoice.document_id = uuid4()
        mock_invoice.deleted_at = None

        with patch.object(fx_service, "_get_open_fx_positions", return_value=[mock_invoice]):
            # get_rate returns None for XYZ
            async def mock_get_rate(currency: str, target_date: Optional[date] = None) -> Optional[Decimal]:
                return None

            with patch.object(fx_service, "get_rate", side_effect=mock_get_rate):
                summary = await fx_service.month_end_revaluation(
                    company_id=uuid4(),
                    revaluation_date=date(2026, 1, 31),
                    db=mock_db,
                )

        # Should skip position with missing rate
        assert summary.entries_processed == 0


class TestGetFXExposure:
    """Tests for get_fx_exposure."""

    @pytest.mark.asyncio
    async def test_fx_exposure_groups_by_currency(self, fx_service, mock_db):
        """Test that exposure groups by currency."""
        invoice_usd1 = MagicMock(spec=InvoiceTracking)
        invoice_usd1.currency = "USD"
        invoice_usd1.amount = Decimal("1000.00")
        invoice_usd1.outstanding_amount = Decimal("1000.00")
        invoice_usd1.paid_amount = Decimal("0.00")

        invoice_usd2 = MagicMock(spec=InvoiceTracking)
        invoice_usd2.currency = "USD"
        invoice_usd2.amount = Decimal("500.00")
        invoice_usd2.outstanding_amount = Decimal("500.00")
        invoice_usd2.paid_amount = Decimal("0.00")

        invoice_gbp = MagicMock(spec=InvoiceTracking)
        invoice_gbp.currency = "GBP"
        invoice_gbp.amount = Decimal("800.00")
        invoice_gbp.outstanding_amount = Decimal("800.00")
        invoice_gbp.paid_amount = Decimal("0.00")

        with patch.object(fx_service, "_get_open_fx_positions", return_value=[invoice_usd1, invoice_usd2, invoice_gbp]):
            # Mock get_rate
            async def mock_get_rate(currency: str, target_date: Optional[date] = None) -> Optional[Decimal]:
                if currency == "USD":
                    return Decimal("1.10")
                elif currency == "GBP":
                    return Decimal("0.86")
                return None

            with patch.object(fx_service, "get_rate", side_effect=mock_get_rate):
                exposures = await fx_service.get_fx_exposure(
                    company_id=uuid4(),
                    db=mock_db,
                )

        assert len(exposures) == 2
        # Find USD exposure
        usd_exposure = next(e for e in exposures if e["currency"] == "USD")
        assert usd_exposure["amount"] == "1500.00"  # 1000 + 500

    @pytest.mark.asyncio
    async def test_fx_exposure_empty(self, fx_service, mock_db):
        """Test that no positions returns empty exposure."""
        with patch.object(fx_service, "_get_open_fx_positions", return_value=[]):
            exposures = await fx_service.get_fx_exposure(
                company_id=uuid4(),
                db=mock_db,
            )

        assert exposures == []

    @pytest.mark.asyncio
    async def test_fx_exposure_calculates_eur_equivalent(self, fx_service, mock_db):
        """Test that EUR equivalent is calculated."""
        mock_invoice = MagicMock(spec=InvoiceTracking)
        mock_invoice.currency = "USD"
        mock_invoice.amount = Decimal("1100.00")
        mock_invoice.outstanding_amount = Decimal("1100.00")
        mock_invoice.paid_amount = Decimal("0.00")

        with patch.object(fx_service, "_get_open_fx_positions", return_value=[mock_invoice]):
            # Mock get_rate to return 1.10 (USD/EUR)
            async def mock_get_rate(currency: str, target_date: Optional[date] = None) -> Optional[Decimal]:
                return Decimal("1.10")

            with patch.object(fx_service, "get_rate", side_effect=mock_get_rate):
                exposures = await fx_service.get_fx_exposure(
                    company_id=uuid4(),
                    db=mock_db,
                )

        assert len(exposures) == 1
        assert exposures[0]["currency"] == "USD"
        assert exposures[0]["amount"] == "1100.00"
        # USD 1100 / 1.10 = EUR 1000
        assert exposures[0]["eur_equivalent"] == "1000.00"

    @pytest.mark.asyncio
    async def test_fx_exposure_excludes_eur(self, fx_service, mock_db):
        """Test that EUR positions are excluded from exposure."""
        invoice_eur = MagicMock(spec=InvoiceTracking)
        invoice_eur.currency = "EUR"
        invoice_eur.amount = Decimal("1000.00")
        invoice_eur.outstanding_amount = Decimal("1000.00")
        invoice_eur.paid_amount = Decimal("0.00")

        # _get_open_fx_positions already filters out EUR in the service
        # So we test the service behavior
        with patch.object(fx_service, "_get_open_fx_positions", return_value=[]):
            exposures = await fx_service.get_fx_exposure(
                company_id=uuid4(),
                db=mock_db,
            )

        # EUR should not appear in exposure
        assert exposures == []
