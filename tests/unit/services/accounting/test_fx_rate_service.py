# -*- coding: utf-8 -*-
"""Unit tests fuer FX Rate Service."""

import pytest
from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from app.services.accounting.fx_rate_service import FXRateService, ConversionResult
from app.db.models_fx import ExchangeRate


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

        with patch("app.services.accounting.fx_gain_loss_service.GLPostingService") as mock_gl:
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

        with patch("app.services.accounting.fx_gain_loss_service.GLPostingService") as mock_gl:
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
