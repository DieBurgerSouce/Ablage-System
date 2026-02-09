# -*- coding: utf-8 -*-
"""Unit tests fuer FX Month-End Revaluation (Feature 7).

Tests fuer:
- month_end_revaluation mit mehreren Waehrungen
- month_end_revaluation ohne offene Positionen
- month_end_revaluation mit gemischten Gewinnen/Verlusten
- API-Endpoint Trigger und Response-Format
- Fehlerbehandlung (fehlende Kurse, DB-Fehler)
- FX-Exposure-Berechnung
"""

import pytest
from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock
from uuid import uuid4, UUID

from app.services.accounting.fx_rate_service import (
    FXRateService,
    RevaluationSummary,
    RevaluationEntry,
)
from app.services.accounting.fx_gain_loss_service import (
    FXGainLossService,
    FXGainLossResult,
)
from app.db.models_fx import ExchangeRate, FXGainLossEntry


# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def mock_db():
    """Mock database session."""
    db = AsyncMock()
    db.commit = AsyncMock()
    db.add = MagicMock()
    db.refresh = AsyncMock()
    return db


@pytest.fixture
def fx_service(mock_db):
    """FX Rate Service Instanz."""
    return FXRateService(mock_db)


@pytest.fixture
def company_id():
    """Test-Firmen-ID."""
    return uuid4()


@pytest.fixture
def revaluation_date():
    """Bewertungsstichtag."""
    return date(2026, 1, 31)


def _make_invoice_tracking(
    inv_id: UUID,
    currency: str,
    amount: float,
    outstanding: float,
    invoice_date: datetime,
    status: str = "open",
    paid_amount: float = 0.0,
    company_id: UUID = None,
    document_id: UUID = None,
) -> MagicMock:
    """Erzeugt ein Mock-InvoiceTracking-Objekt."""
    mock = MagicMock()
    mock.id = inv_id
    mock.currency = currency
    mock.amount = amount
    mock.outstanding_amount = outstanding
    mock.paid_amount = paid_amount
    mock.invoice_date = invoice_date
    mock.status = status
    mock.company_id = company_id or uuid4()
    mock.document_id = document_id or uuid4()
    mock.deleted_at = None
    return mock


# =============================================================================
# TESTS: month_end_revaluation
# =============================================================================


class TestMonthEndRevaluation:
    """Tests fuer die Monatsabschluss-Stichtagsbewertung."""

    @pytest.mark.asyncio
    async def test_revaluation_no_open_positions(self, fx_service, mock_db, company_id, revaluation_date):
        """Test: Keine offenen FX-Positionen -> 0 Eintraege."""
        # _get_open_fx_positions returns empty
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute = AsyncMock(return_value=mock_result)

        summary = await fx_service.month_end_revaluation(
            company_id=company_id,
            revaluation_date=revaluation_date,
            db=mock_db,
        )

        assert summary.entries_processed == 0
        assert summary.total_gain == Decimal("0.00")
        assert summary.total_loss == Decimal("0.00")
        assert summary.currency_breakdown == {}
        assert summary.entries == []

    @pytest.mark.asyncio
    async def test_revaluation_single_currency_gain(self, fx_service, mock_db, company_id, revaluation_date):
        """Test: USD-Position mit Kursgewinn."""
        inv = _make_invoice_tracking(
            inv_id=uuid4(),
            currency="USD",
            amount=1000.0,
            outstanding=1000.0,
            invoice_date=datetime(2026, 1, 5, tzinfo=timezone.utc),
            company_id=company_id,
        )

        # Mock _get_open_fx_positions
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [inv]
        mock_db.execute = AsyncMock(return_value=mock_result)

        # Mock get_rate: booking_rate=1.10, current_rate=1.08 (EUR staerker -> Gewinn)
        rate_calls = []

        async def mock_get_rate(currency, target_date=None):
            if currency == "EUR":
                return Decimal("1.0")
            rate_calls.append((currency, target_date))
            if target_date == date(2026, 1, 5):
                return Decimal("1.10")  # Booking rate
            return Decimal("1.08")  # Current rate (Stichtagskurs)

        fx_service.get_rate = mock_get_rate

        # Mock FXGainLossService
        with patch("app.services.accounting.fx_gain_loss_service.FXGainLossService") as mock_gl_cls:
            mock_gl = MagicMock()
            mock_gl.calculate_unrealized_gain_loss.return_value = FXGainLossResult(
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
            mock_gl.post_fx_gain_loss = AsyncMock(return_value=MagicMock())
            mock_gl_cls.return_value = mock_gl

            summary = await fx_service.month_end_revaluation(
                company_id=company_id,
                revaluation_date=revaluation_date,
                db=mock_db,
            )

        assert summary.entries_processed == 1
        assert summary.total_gain == Decimal("16.84")
        assert summary.total_loss == Decimal("0.00")
        assert "USD" in summary.currency_breakdown
        assert summary.currency_breakdown["USD"]["gain"] == "16.84"
        assert summary.entries[0].is_gain is True

    @pytest.mark.asyncio
    async def test_revaluation_single_currency_loss(self, fx_service, mock_db, company_id, revaluation_date):
        """Test: USD-Position mit Kursverlust."""
        inv = _make_invoice_tracking(
            inv_id=uuid4(),
            currency="USD",
            amount=1000.0,
            outstanding=1000.0,
            invoice_date=datetime(2026, 1, 5, tzinfo=timezone.utc),
            company_id=company_id,
        )

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [inv]
        mock_db.execute = AsyncMock(return_value=mock_result)

        async def mock_get_rate(currency, target_date=None):
            if currency == "EUR":
                return Decimal("1.0")
            if target_date == date(2026, 1, 5):
                return Decimal("1.08")  # Booking rate
            return Decimal("1.10")  # Current rate (EUR schwaecher -> Verlust)

        fx_service.get_rate = mock_get_rate

        with patch("app.services.accounting.fx_gain_loss_service.FXGainLossService") as mock_gl_cls:
            mock_gl = MagicMock()
            mock_gl.calculate_unrealized_gain_loss.return_value = FXGainLossResult(
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
            mock_gl.post_fx_gain_loss = AsyncMock(return_value=MagicMock())
            mock_gl_cls.return_value = mock_gl

            summary = await fx_service.month_end_revaluation(
                company_id=company_id,
                revaluation_date=revaluation_date,
                db=mock_db,
            )

        assert summary.entries_processed == 1
        assert summary.total_gain == Decimal("0.00")
        assert summary.total_loss == Decimal("16.84")
        assert summary.currency_breakdown["USD"]["loss"] == "16.84"
        assert summary.entries[0].is_gain is False

    @pytest.mark.asyncio
    async def test_revaluation_multiple_currencies_mixed(
        self, fx_service, mock_db, company_id, revaluation_date
    ):
        """Test: Mehrere Waehrungen mit gemischten Gewinnen und Verlusten."""
        inv_usd = _make_invoice_tracking(
            inv_id=uuid4(),
            currency="USD",
            amount=5000.0,
            outstanding=5000.0,
            invoice_date=datetime(2026, 1, 10, tzinfo=timezone.utc),
            company_id=company_id,
        )
        inv_gbp = _make_invoice_tracking(
            inv_id=uuid4(),
            currency="GBP",
            amount=3000.0,
            outstanding=3000.0,
            invoice_date=datetime(2026, 1, 12, tzinfo=timezone.utc),
            company_id=company_id,
        )
        inv_chf = _make_invoice_tracking(
            inv_id=uuid4(),
            currency="CHF",
            amount=2000.0,
            outstanding=2000.0,
            invoice_date=datetime(2026, 1, 15, tzinfo=timezone.utc),
            company_id=company_id,
        )

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [inv_usd, inv_gbp, inv_chf]
        mock_db.execute = AsyncMock(return_value=mock_result)

        # Rates: USD gain, GBP loss, CHF gain
        rate_map = {
            ("USD", date(2026, 1, 10)): Decimal("1.10"),
            ("USD", revaluation_date): Decimal("1.08"),
            ("GBP", date(2026, 1, 12)): Decimal("0.85"),
            ("GBP", revaluation_date): Decimal("0.87"),
            ("CHF", date(2026, 1, 15)): Decimal("0.96"),
            ("CHF", revaluation_date): Decimal("0.94"),
        }

        async def mock_get_rate(currency, target_date=None):
            if currency == "EUR":
                return Decimal("1.0")
            return rate_map.get((currency, target_date))

        fx_service.get_rate = mock_get_rate

        gl_results = [
            # USD: Gain (rate dropped, fewer EUR needed)
            FXGainLossResult(
                original_currency="USD",
                original_amount=Decimal("5000.00"),
                booking_rate=Decimal("1.10"),
                settlement_rate=Decimal("1.08"),
                booking_eur_amount=Decimal("4545.45"),
                settlement_eur_amount=Decimal("4629.63"),
                gain_loss_amount=Decimal("84.18"),
                gain_loss_account="2650",
                is_gain=True,
            ),
            # GBP: Loss (rate rose, more EUR needed)
            FXGainLossResult(
                original_currency="GBP",
                original_amount=Decimal("3000.00"),
                booking_rate=Decimal("0.85"),
                settlement_rate=Decimal("0.87"),
                booking_eur_amount=Decimal("3529.41"),
                settlement_eur_amount=Decimal("3448.28"),
                gain_loss_amount=Decimal("81.13"),
                gain_loss_account="2150",
                is_gain=False,
            ),
            # CHF: Gain (rate dropped)
            FXGainLossResult(
                original_currency="CHF",
                original_amount=Decimal("2000.00"),
                booking_rate=Decimal("0.96"),
                settlement_rate=Decimal("0.94"),
                booking_eur_amount=Decimal("2083.33"),
                settlement_eur_amount=Decimal("2127.66"),
                gain_loss_amount=Decimal("44.33"),
                gain_loss_account="2650",
                is_gain=True,
            ),
        ]

        call_count = [0]

        with patch("app.services.accounting.fx_gain_loss_service.FXGainLossService") as mock_gl_cls:
            mock_gl = MagicMock()

            def side_effect_calc(*args, **kwargs):
                idx = call_count[0]
                call_count[0] += 1
                return gl_results[idx]

            mock_gl.calculate_unrealized_gain_loss.side_effect = side_effect_calc
            mock_gl.post_fx_gain_loss = AsyncMock(return_value=MagicMock())
            mock_gl_cls.return_value = mock_gl

            summary = await fx_service.month_end_revaluation(
                company_id=company_id,
                revaluation_date=revaluation_date,
                db=mock_db,
            )

        assert summary.entries_processed == 3
        # Gains: 84.18 + 44.33 = 128.51
        assert summary.total_gain == Decimal("128.51")
        # Loss: 81.13
        assert summary.total_loss == Decimal("81.13")
        assert len(summary.currency_breakdown) == 3
        assert "USD" in summary.currency_breakdown
        assert "GBP" in summary.currency_breakdown
        assert "CHF" in summary.currency_breakdown

    @pytest.mark.asyncio
    async def test_revaluation_skips_eur_positions(self, fx_service, mock_db, company_id, revaluation_date):
        """Test: EUR-Positionen werden uebersprungen."""
        inv_eur = _make_invoice_tracking(
            inv_id=uuid4(),
            currency="EUR",
            amount=5000.0,
            outstanding=5000.0,
            invoice_date=datetime(2026, 1, 10, tzinfo=timezone.utc),
            company_id=company_id,
        )

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [inv_eur]
        mock_db.execute = AsyncMock(return_value=mock_result)

        summary = await fx_service.month_end_revaluation(
            company_id=company_id,
            revaluation_date=revaluation_date,
            db=mock_db,
        )

        assert summary.entries_processed == 0

    @pytest.mark.asyncio
    async def test_revaluation_skips_zero_outstanding(self, fx_service, mock_db, company_id, revaluation_date):
        """Test: Positionen ohne ausstehenden Betrag werden uebersprungen.

        outstanding_amount=None + paid_amount=amount -> outstanding = 0 -> skip.
        """
        inv = _make_invoice_tracking(
            inv_id=uuid4(),
            currency="USD",
            amount=1000.0,
            outstanding=1000.0,  # will be overridden below
            paid_amount=1000.0,
            invoice_date=datetime(2026, 1, 5, tzinfo=timezone.utc),
            company_id=company_id,
        )
        inv.outstanding_amount = None  # Triggers fallback: amount - paid = 0

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [inv]
        mock_db.execute = AsyncMock(return_value=mock_result)

        summary = await fx_service.month_end_revaluation(
            company_id=company_id,
            revaluation_date=revaluation_date,
            db=mock_db,
        )

        assert summary.entries_processed == 0

    @pytest.mark.asyncio
    async def test_revaluation_missing_booking_rate_skips(
        self, fx_service, mock_db, company_id, revaluation_date
    ):
        """Test: Fehlender Buchungskurs -> Position wird uebersprungen."""
        inv = _make_invoice_tracking(
            inv_id=uuid4(),
            currency="XYZ",
            amount=1000.0,
            outstanding=1000.0,
            invoice_date=datetime(2026, 1, 5, tzinfo=timezone.utc),
            company_id=company_id,
        )

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [inv]
        mock_db.execute = AsyncMock(return_value=mock_result)

        # Kein Kurs fuer XYZ
        async def mock_get_rate(currency, target_date=None):
            return None

        fx_service.get_rate = mock_get_rate

        summary = await fx_service.month_end_revaluation(
            company_id=company_id,
            revaluation_date=revaluation_date,
            db=mock_db,
        )

        assert summary.entries_processed == 0

    @pytest.mark.asyncio
    async def test_revaluation_missing_current_rate_skips(
        self, fx_service, mock_db, company_id, revaluation_date
    ):
        """Test: Fehlender Stichtagskurs -> Position wird uebersprungen."""
        inv = _make_invoice_tracking(
            inv_id=uuid4(),
            currency="USD",
            amount=1000.0,
            outstanding=1000.0,
            invoice_date=datetime(2026, 1, 5, tzinfo=timezone.utc),
            company_id=company_id,
        )

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [inv]
        mock_db.execute = AsyncMock(return_value=mock_result)

        async def mock_get_rate(currency, target_date=None):
            if target_date == date(2026, 1, 5):
                return Decimal("1.10")  # Booking rate exists
            return None  # No current rate

        fx_service.get_rate = mock_get_rate

        summary = await fx_service.month_end_revaluation(
            company_id=company_id,
            revaluation_date=revaluation_date,
            db=mock_db,
        )

        assert summary.entries_processed == 0

    @pytest.mark.asyncio
    async def test_revaluation_zero_difference_skipped(
        self, fx_service, mock_db, company_id, revaluation_date
    ):
        """Test: Keine Kursdifferenz -> wird nicht gebucht."""
        inv = _make_invoice_tracking(
            inv_id=uuid4(),
            currency="USD",
            amount=1000.0,
            outstanding=1000.0,
            invoice_date=datetime(2026, 1, 5, tzinfo=timezone.utc),
            company_id=company_id,
        )

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [inv]
        mock_db.execute = AsyncMock(return_value=mock_result)

        # Gleicher Kurs bei Buchung und Stichtag
        async def mock_get_rate(currency, target_date=None):
            return Decimal("1.10")

        fx_service.get_rate = mock_get_rate

        with patch("app.services.accounting.fx_gain_loss_service.FXGainLossService") as mock_gl_cls:
            mock_gl = MagicMock()
            mock_gl.calculate_unrealized_gain_loss.return_value = FXGainLossResult(
                original_currency="USD",
                original_amount=Decimal("1000.00"),
                booking_rate=Decimal("1.10"),
                settlement_rate=Decimal("1.10"),
                booking_eur_amount=Decimal("909.09"),
                settlement_eur_amount=Decimal("909.09"),
                gain_loss_amount=Decimal("0.00"),
                gain_loss_account="2650",
                is_gain=True,
            )
            mock_gl_cls.return_value = mock_gl

            summary = await fx_service.month_end_revaluation(
                company_id=company_id,
                revaluation_date=revaluation_date,
                db=mock_db,
            )

        assert summary.entries_processed == 0

    @pytest.mark.asyncio
    async def test_revaluation_partial_payment_uses_outstanding(
        self, fx_service, mock_db, company_id, revaluation_date
    ):
        """Test: Teilzahlung -> nur ausstehender Betrag wird bewertet."""
        inv = _make_invoice_tracking(
            inv_id=uuid4(),
            currency="USD",
            amount=1000.0,
            outstanding=600.0,  # 400 already paid
            paid_amount=400.0,
            invoice_date=datetime(2026, 1, 5, tzinfo=timezone.utc),
            company_id=company_id,
        )

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [inv]
        mock_db.execute = AsyncMock(return_value=mock_result)

        async def mock_get_rate(currency, target_date=None):
            if target_date == date(2026, 1, 5):
                return Decimal("1.10")
            return Decimal("1.08")

        fx_service.get_rate = mock_get_rate

        with patch("app.services.accounting.fx_gain_loss_service.FXGainLossService") as mock_gl_cls:
            mock_gl = MagicMock()
            mock_gl.calculate_unrealized_gain_loss.return_value = FXGainLossResult(
                original_currency="USD",
                original_amount=Decimal("600.00"),
                booking_rate=Decimal("1.10"),
                settlement_rate=Decimal("1.08"),
                booking_eur_amount=Decimal("545.45"),
                settlement_eur_amount=Decimal("555.56"),
                gain_loss_amount=Decimal("10.11"),
                gain_loss_account="2650",
                is_gain=True,
            )
            mock_gl.post_fx_gain_loss = AsyncMock(return_value=MagicMock())
            mock_gl_cls.return_value = mock_gl

            summary = await fx_service.month_end_revaluation(
                company_id=company_id,
                revaluation_date=revaluation_date,
                db=mock_db,
            )

        # Verify outstanding amount (600) was used, not total (1000)
        mock_gl.calculate_unrealized_gain_loss.assert_called_once()
        call_kwargs = mock_gl.calculate_unrealized_gain_loss.call_args[1]
        assert call_kwargs["original_amount"] == Decimal("600.0")
        assert summary.entries_processed == 1

    @pytest.mark.asyncio
    async def test_revaluation_posts_as_unrealized(
        self, fx_service, mock_db, company_id, revaluation_date
    ):
        """Test: GL-Buchungen werden als 'unrealisiert' gepostet."""
        inv = _make_invoice_tracking(
            inv_id=uuid4(),
            currency="USD",
            amount=1000.0,
            outstanding=1000.0,
            invoice_date=datetime(2026, 1, 5, tzinfo=timezone.utc),
            company_id=company_id,
        )

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [inv]
        mock_db.execute = AsyncMock(return_value=mock_result)

        async def mock_get_rate(currency, target_date=None):
            if target_date == date(2026, 1, 5):
                return Decimal("1.10")
            return Decimal("1.08")

        fx_service.get_rate = mock_get_rate

        with patch("app.services.accounting.fx_gain_loss_service.FXGainLossService") as mock_gl_cls:
            mock_gl = MagicMock()
            mock_gl.calculate_unrealized_gain_loss.return_value = FXGainLossResult(
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
            mock_gl.post_fx_gain_loss = AsyncMock(return_value=MagicMock())
            mock_gl_cls.return_value = mock_gl

            await fx_service.month_end_revaluation(
                company_id=company_id,
                revaluation_date=revaluation_date,
                db=mock_db,
            )

            # Verify realized=False
            mock_gl.post_fx_gain_loss.assert_called_once()
            call_kwargs = mock_gl.post_fx_gain_loss.call_args[1]
            assert call_kwargs["realized"] is False


# =============================================================================
# TESTS: get_fx_exposure
# =============================================================================


class TestFXExposure:
    """Tests fuer FX-Exposure-Berechnung."""

    @pytest.mark.asyncio
    async def test_exposure_empty(self, fx_service, mock_db, company_id):
        """Test: Keine offenen FX-Positionen."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute = AsyncMock(return_value=mock_result)

        exposures = await fx_service.get_fx_exposure(
            company_id=company_id,
            db=mock_db,
        )

        assert exposures == []

    @pytest.mark.asyncio
    async def test_exposure_multiple_currencies(self, fx_service, mock_db, company_id):
        """Test: Mehrere Waehrungen aggregiert."""
        inv1 = _make_invoice_tracking(
            inv_id=uuid4(),
            currency="USD",
            amount=1000.0,
            outstanding=1000.0,
            invoice_date=datetime(2026, 1, 5, tzinfo=timezone.utc),
        )
        inv2 = _make_invoice_tracking(
            inv_id=uuid4(),
            currency="USD",
            amount=2000.0,
            outstanding=2000.0,
            invoice_date=datetime(2026, 1, 10, tzinfo=timezone.utc),
        )
        inv3 = _make_invoice_tracking(
            inv_id=uuid4(),
            currency="GBP",
            amount=5000.0,
            outstanding=5000.0,
            invoice_date=datetime(2026, 1, 12, tzinfo=timezone.utc),
        )

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [inv1, inv2, inv3]
        mock_db.execute = AsyncMock(return_value=mock_result)

        async def mock_get_rate(currency, target_date=None):
            rates = {"USD": Decimal("1.10"), "GBP": Decimal("0.86")}
            return rates.get(currency)

        fx_service.get_rate = mock_get_rate

        exposures = await fx_service.get_fx_exposure(
            company_id=company_id,
            db=mock_db,
        )

        assert len(exposures) == 2
        # Sorted alphabetically: GBP, USD
        assert exposures[0]["currency"] == "GBP"
        assert exposures[0]["amount"] == "5000.00"
        # GBP 5000 / 0.86 = EUR 5813.95
        assert Decimal(exposures[0]["eur_equivalent"]) > Decimal("5800")

        assert exposures[1]["currency"] == "USD"
        assert exposures[1]["amount"] == "3000.00"  # 1000 + 2000
        # USD 3000 / 1.10 = EUR 2727.27
        assert Decimal(exposures[1]["eur_equivalent"]) > Decimal("2700")


# =============================================================================
# TESTS: API Endpoint Response Format
# =============================================================================


class TestRevaluationAPISchemas:
    """Tests fuer API Schema Validierung."""

    def test_revaluation_summary_serialization(self):
        """Test: RevaluationSummary wird korrekt serialisiert."""
        summary = RevaluationSummary(
            entries_processed=3,
            total_gain=Decimal("128.51"),
            total_loss=Decimal("81.13"),
            currency_breakdown={
                "USD": {"gain": "84.18", "loss": "0.00", "positions": "1"},
                "GBP": {"gain": "0.00", "loss": "81.13", "positions": "1"},
                "CHF": {"gain": "44.33", "loss": "0.00", "positions": "1"},
            },
            entries=[],
        )

        assert summary.entries_processed == 3
        assert isinstance(summary.total_gain, Decimal)
        assert isinstance(summary.total_loss, Decimal)
        assert len(summary.currency_breakdown) == 3

    def test_revaluation_entry_fields(self):
        """Test: RevaluationEntry hat alle benoetigten Felder."""
        entry = RevaluationEntry(
            invoice_tracking_id=uuid4(),
            currency="USD",
            original_amount=Decimal("1000.00"),
            outstanding_amount=Decimal("600.00"),
            booking_rate=Decimal("1.10"),
            current_rate=Decimal("1.08"),
            gain_loss_eur=Decimal("10.11"),
            is_gain=True,
        )

        assert entry.currency == "USD"
        assert entry.outstanding_amount == Decimal("600.00")
        assert entry.gain_loss_eur == Decimal("10.11")
        assert entry.is_gain is True


# =============================================================================
# TESTS: Celery Task
# =============================================================================


class TestFXRevaluationCeleryTask:
    """Tests fuer die Celery Task Integration."""

    @pytest.mark.asyncio
    async def test_month_end_revaluation_task_exists(self):
        """Test: Celery Task ist registriert."""
        from app.workers.tasks.fx_rate_tasks import month_end_revaluation
        assert month_end_revaluation is not None
        assert month_end_revaluation.name == "app.workers.tasks.fx_rate_tasks.month_end_revaluation"

    @pytest.mark.asyncio
    async def test_run_all_task_exists(self):
        """Test: Batch-Celery Task ist registriert."""
        from app.workers.tasks.fx_rate_tasks import run_month_end_fx_revaluation_all
        assert run_month_end_fx_revaluation_all is not None
        assert (
            run_month_end_fx_revaluation_all.name
            == "app.workers.tasks.fx_rate_tasks.run_month_end_fx_revaluation_all"
        )


# =============================================================================
# TESTS: Error Handling
# =============================================================================


class TestRevaluationErrorHandling:
    """Tests fuer Fehlerbehandlung."""

    @pytest.mark.asyncio
    async def test_revaluation_db_error_propagates(self, fx_service, mock_db, company_id, revaluation_date):
        """Test: DB-Fehler werden weitergegeben."""
        mock_db.execute = AsyncMock(side_effect=Exception("DB Connection Lost"))

        with pytest.raises(Exception, match="DB Connection Lost"):
            await fx_service.month_end_revaluation(
                company_id=company_id,
                revaluation_date=revaluation_date,
                db=mock_db,
            )

    @pytest.mark.asyncio
    async def test_revaluation_gl_posting_error_propagates(
        self, fx_service, mock_db, company_id, revaluation_date
    ):
        """Test: GL-Buchungsfehler werden weitergegeben."""
        inv = _make_invoice_tracking(
            inv_id=uuid4(),
            currency="USD",
            amount=1000.0,
            outstanding=1000.0,
            invoice_date=datetime(2026, 1, 5, tzinfo=timezone.utc),
            company_id=company_id,
        )

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [inv]
        mock_db.execute = AsyncMock(return_value=mock_result)

        async def mock_get_rate(currency, target_date=None):
            if target_date == date(2026, 1, 5):
                return Decimal("1.10")
            return Decimal("1.08")

        fx_service.get_rate = mock_get_rate

        with patch("app.services.accounting.fx_gain_loss_service.FXGainLossService") as mock_gl_cls:
            mock_gl = MagicMock()
            mock_gl.calculate_unrealized_gain_loss.return_value = FXGainLossResult(
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
            mock_gl.post_fx_gain_loss = AsyncMock(
                side_effect=Exception("GL Posting fehlgeschlagen")
            )
            mock_gl_cls.return_value = mock_gl

            with pytest.raises(Exception, match="GL Posting fehlgeschlagen"):
                await fx_service.month_end_revaluation(
                    company_id=company_id,
                    revaluation_date=revaluation_date,
                    db=mock_db,
                )

    @pytest.mark.asyncio
    async def test_revaluation_outstanding_amount_fallback(
        self, fx_service, mock_db, company_id, revaluation_date
    ):
        """Test: Wenn outstanding_amount None ist, wird amount - paid_amount berechnet."""
        inv = _make_invoice_tracking(
            inv_id=uuid4(),
            currency="USD",
            amount=1000.0,
            outstanding=None,  # type: ignore[arg-type] - simulating None
            paid_amount=300.0,
            invoice_date=datetime(2026, 1, 5, tzinfo=timezone.utc),
            company_id=company_id,
        )
        inv.outstanding_amount = None  # Override the mock

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [inv]
        mock_db.execute = AsyncMock(return_value=mock_result)

        async def mock_get_rate(currency, target_date=None):
            if target_date == date(2026, 1, 5):
                return Decimal("1.10")
            return Decimal("1.08")

        fx_service.get_rate = mock_get_rate

        with patch("app.services.accounting.fx_gain_loss_service.FXGainLossService") as mock_gl_cls:
            mock_gl = MagicMock()
            mock_gl.calculate_unrealized_gain_loss.return_value = FXGainLossResult(
                original_currency="USD",
                original_amount=Decimal("700.00"),
                booking_rate=Decimal("1.10"),
                settlement_rate=Decimal("1.08"),
                booking_eur_amount=Decimal("636.36"),
                settlement_eur_amount=Decimal("648.15"),
                gain_loss_amount=Decimal("11.79"),
                gain_loss_account="2650",
                is_gain=True,
            )
            mock_gl.post_fx_gain_loss = AsyncMock(return_value=MagicMock())
            mock_gl_cls.return_value = mock_gl

            summary = await fx_service.month_end_revaluation(
                company_id=company_id,
                revaluation_date=revaluation_date,
                db=mock_db,
            )

        # Verify: 1000 - 300 = 700 was used
        call_kwargs = mock_gl.calculate_unrealized_gain_loss.call_args[1]
        assert call_kwargs["original_amount"] == Decimal("700.0")
        assert summary.entries_processed == 1
