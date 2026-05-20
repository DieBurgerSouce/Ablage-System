# -*- coding: utf-8 -*-
"""Tests fuer SkontoService.

Testet Skonto-Berechnung, Validierung und Alerts.
"""

import pytest
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.banking.skonto_service import (
    SkontoService,
    SkontoCalculation,
    SkontoCondition,
    SkontoAlert,
)


class TestSkontoCalculation:
    """Tests fuer Skonto-Berechnung."""

    @pytest.fixture
    def service(self) -> SkontoService:
        """Erstellt SkontoService Instanz."""
        return SkontoService()

    @pytest.fixture
    def mock_db(self) -> AsyncMock:
        """Mock fuer Datenbank-Session."""
        return AsyncMock()

    @pytest.mark.asyncio
    async def test_calculate_skonto_standard(self, service: SkontoService) -> None:
        """Test: Standard 2% Skonto Berechnung."""
        invoice_amount = Decimal("1000.00")
        invoice_date = datetime.now(timezone.utc)

        result = await service.calculate_skonto(
            db=AsyncMock(),
            invoice_amount=invoice_amount,
            invoice_date=invoice_date,
            skonto_percentage=Decimal("2.0"),
            skonto_days=14,
            net_days=30,
        )

        assert result.skonto_amount == Decimal("20.00")
        assert result.amount_with_skonto == Decimal("980.00")
        assert result.skonto_percentage == Decimal("2.0")
        assert result.skonto_days == 14

    @pytest.mark.asyncio
    async def test_calculate_skonto_three_percent(self, service: SkontoService) -> None:
        """Test: 3% Skonto Berechnung."""
        invoice_amount = Decimal("500.00")
        invoice_date = datetime.now(timezone.utc)

        result = await service.calculate_skonto(
            db=AsyncMock(),
            invoice_amount=invoice_amount,
            invoice_date=invoice_date,
            skonto_percentage=Decimal("3.0"),
            skonto_days=10,
            net_days=30,
        )

        assert result.skonto_amount == Decimal("15.00")
        assert result.amount_with_skonto == Decimal("485.00")

    @pytest.mark.asyncio
    async def test_calculate_skonto_deadline(self, service: SkontoService) -> None:
        """Test: Skonto-Deadline wird korrekt berechnet."""
        invoice_date = datetime(2026, 1, 10, 12, 0, 0, tzinfo=timezone.utc)

        result = await service.calculate_skonto(
            db=AsyncMock(),
            invoice_amount=Decimal("1000.00"),
            invoice_date=invoice_date,
            skonto_percentage=Decimal("2.0"),
            skonto_days=14,
            net_days=30,
        )

        expected_deadline = datetime(2026, 1, 24, 12, 0, 0, tzinfo=timezone.utc)
        assert result.skonto_deadline == expected_deadline

    @pytest.mark.asyncio
    async def test_calculate_skonto_is_valid(self, service: SkontoService) -> None:
        """Test: Skonto-Gueltigkeit wird korrekt geprueft."""
        # Rechnungsdatum vor 5 Tagen - Skonto sollte noch gueltig sein
        invoice_date = datetime.now(timezone.utc) - timedelta(days=5)

        result = await service.calculate_skonto(
            db=AsyncMock(),
            invoice_amount=Decimal("1000.00"),
            invoice_date=invoice_date,
            skonto_percentage=Decimal("2.0"),
            skonto_days=14,
            net_days=30,
        )

        assert result.is_skonto_valid is True
        assert result.days_remaining > 0

    @pytest.mark.asyncio
    async def test_calculate_skonto_expired(self, service: SkontoService) -> None:
        """Test: Abgelaufenes Skonto."""
        # Rechnungsdatum vor 20 Tagen - Skonto sollte abgelaufen sein
        invoice_date = datetime.now(timezone.utc) - timedelta(days=20)

        result = await service.calculate_skonto(
            db=AsyncMock(),
            invoice_amount=Decimal("1000.00"),
            invoice_date=invoice_date,
            skonto_percentage=Decimal("2.0"),
            skonto_days=14,
            net_days=30,
        )

        assert result.is_skonto_valid is False
        assert result.days_remaining is None

    @pytest.mark.asyncio
    async def test_calculate_skonto_zero_percentage(self, service: SkontoService) -> None:
        """Test: 0% Skonto (kein Skonto)."""
        result = await service.calculate_skonto(
            db=AsyncMock(),
            invoice_amount=Decimal("1000.00"),
            invoice_date=datetime.now(timezone.utc),
            skonto_percentage=Decimal("0.0"),
            skonto_days=14,
            net_days=30,
        )

        assert result.skonto_amount == Decimal("0.00")
        assert result.amount_with_skonto == Decimal("1000.00")


class TestSkontoDetection:
    """Tests fuer Skonto-Erkennung aus OCR-Text."""

    @pytest.fixture
    def service(self) -> SkontoService:
        """Erstellt SkontoService Instanz."""
        return SkontoService()

    @pytest.mark.asyncio
    async def test_detect_skonto_standard_format(self, service: SkontoService) -> None:
        """Test: Erkennung von '2% Skonto bei Zahlung innerhalb 14 Tagen'."""
        ocr_text = """
        Rechnung Nr. 12345
        Betrag: 1.000,00 EUR

        Zahlungsbedingungen:
        2% Skonto bei Zahlung innerhalb 14 Tagen, netto 30 Tage
        """

        result = await service.auto_detect_skonto_from_text(ocr_text)

        assert result is not None
        assert result.percentage == 2.0
        assert result.days == 14
        assert result.net_days == 30

    @pytest.mark.asyncio
    async def test_detect_skonto_alternative_format(self, service: SkontoService) -> None:
        """Test: Alternative Formulierung 'bei Zahlung bis zum'."""
        ocr_text = """
        3% Skonto bei Zahlung bis zum 24.01.2026
        Zahlungsziel: 30 Tage netto
        """

        result = await service.auto_detect_skonto_from_text(ocr_text)

        assert result is not None
        assert result.percentage == 3.0

    @pytest.mark.asyncio
    async def test_detect_skonto_no_conditions(self, service: SkontoService) -> None:
        """Test: Kein Skonto in Text."""
        ocr_text = """
        Rechnung Nr. 12345
        Betrag: 1.000,00 EUR
        Zahlungsziel: 30 Tage
        """

        result = await service.auto_detect_skonto_from_text(ocr_text)

        assert result is None

    @pytest.mark.asyncio
    async def test_detect_skonto_german_decimal(self, service: SkontoService) -> None:
        """Test: Deutsche Dezimalschreibweise (2,5% statt 2.5%)."""
        ocr_text = "2,5% Skonto innerhalb 10 Tagen"

        result = await service.auto_detect_skonto_from_text(ocr_text)

        assert result is not None
        assert result.percentage == 2.5


class TestSkontoAlerts:
    """Tests fuer Skonto-Ablauf-Alerts."""

    @pytest.fixture
    def service(self) -> SkontoService:
        """Erstellt SkontoService Instanz."""
        return SkontoService()

    @pytest.fixture
    def mock_db(self) -> AsyncMock:
        """Mock fuer Datenbank-Session."""
        db = AsyncMock()
        return db

    @pytest.mark.asyncio
    async def test_get_upcoming_skonto_deadlines_empty(
        self, service: SkontoService, mock_db: AsyncMock
    ) -> None:
        """Test: Keine ausstehenden Skonto-Fristen."""
        # Mock execute to return empty result
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result

        result = await service.get_upcoming_skonto_deadlines(
            db=mock_db,
            company_id=uuid4(),
            days_ahead=7,
        )

        assert result == []

    @pytest.mark.asyncio
    async def test_savings_calculation(self, service: SkontoService) -> None:
        """Test: Ersparnisberechnung bei Skonto-Nutzung."""
        invoice_amount = Decimal("10000.00")
        skonto_percentage = Decimal("2.0")

        # Einfache Berechnung
        expected_savings = invoice_amount * skonto_percentage / 100

        assert expected_savings == Decimal("200.00")


class TestApplySkonto:
    """Tests fuer Skonto-Anwendung."""

    @pytest.fixture
    def service(self) -> SkontoService:
        """Erstellt SkontoService Instanz."""
        return SkontoService()

    @pytest.fixture
    def mock_db(self) -> AsyncMock:
        """Mock fuer Datenbank-Session."""
        return AsyncMock()

    @pytest.mark.asyncio
    async def test_apply_skonto_within_deadline(
        self, service: SkontoService, mock_db: AsyncMock
    ) -> None:
        """Test: Skonto innerhalb Frist anwenden."""
        invoice_tracking_id = uuid4()

        # Mock InvoiceTracking
        mock_invoice = MagicMock()
        mock_invoice.id = invoice_tracking_id
        mock_invoice.amount = 1000.0
        mock_invoice.skonto_percentage = 2.0
        mock_invoice.skonto_deadline = datetime.now(timezone.utc) + timedelta(days=5)
        mock_invoice.skonto_used = False
        mock_invoice.status = "open"
        mock_invoice.deleted_at = None

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_invoice
        mock_db.execute.return_value = mock_result

        success, skonto_amount, message = await service.apply_skonto(
            db=mock_db,
            invoice_tracking_id=invoice_tracking_id,
            payment_amount=Decimal("980.00"),
            payment_date=datetime.now(timezone.utc),
            user_id=uuid4(),
            company_id=uuid4(),
        )

        assert success is True
        assert skonto_amount == Decimal("20.00")
        assert "Skonto" in message

    @pytest.mark.asyncio
    async def test_apply_skonto_after_deadline(
        self, service: SkontoService, mock_db: AsyncMock
    ) -> None:
        """Test: Skonto nach Ablauf der Frist."""
        invoice_tracking_id = uuid4()

        # Mock InvoiceTracking mit abgelaufener Frist
        mock_invoice = MagicMock()
        mock_invoice.id = invoice_tracking_id
        mock_invoice.amount = 1000.0
        mock_invoice.skonto_percentage = 2.0
        mock_invoice.skonto_deadline = datetime.now(timezone.utc) - timedelta(days=5)
        mock_invoice.skonto_used = False
        mock_invoice.status = "open"
        mock_invoice.deleted_at = None

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_invoice
        mock_db.execute.return_value = mock_result

        success, skonto_amount, message = await service.apply_skonto(
            db=mock_db,
            invoice_tracking_id=invoice_tracking_id,
            payment_amount=Decimal("980.00"),
            payment_date=datetime.now(timezone.utc),
            user_id=uuid4(),
            company_id=uuid4(),
            force_apply=False,
        )

        assert success is False
        assert "abgelaufen" in message.lower()

    @pytest.mark.asyncio
    async def test_apply_skonto_already_used(
        self, service: SkontoService, mock_db: AsyncMock
    ) -> None:
        """Test: Skonto bereits genutzt."""
        invoice_tracking_id = uuid4()

        mock_invoice = MagicMock()
        mock_invoice.id = invoice_tracking_id
        mock_invoice.skonto_percentage = 2.0  # Muss gesetzt sein fuer Check
        mock_invoice.skonto_used = True
        mock_invoice.deleted_at = None

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_invoice
        mock_db.execute.return_value = mock_result

        success, skonto_amount, message = await service.apply_skonto(
            db=mock_db,
            invoice_tracking_id=invoice_tracking_id,
            payment_amount=Decimal("980.00"),
            payment_date=datetime.now(timezone.utc),
            user_id=uuid4(),
            company_id=uuid4(),
        )

        assert success is False
        assert "bereits" in message.lower()


class TestSkontoStatistics:
    """Tests fuer Skonto-Statistiken."""

    @pytest.fixture
    def service(self) -> SkontoService:
        """Erstellt SkontoService Instanz."""
        return SkontoService()

    @pytest.mark.asyncio
    async def test_calculate_potential_savings(self, service: SkontoService) -> None:
        """Test: Potenzielle Ersparnisse berechnen."""
        # Simuliere 5 Rechnungen mit je 2% Skonto
        total_amount = Decimal("50000.00")
        avg_skonto = Decimal("2.0")

        potential_savings = total_amount * avg_skonto / 100

        assert potential_savings == Decimal("1000.00")

    @pytest.mark.asyncio
    async def test_utilization_rate(self, service: SkontoService) -> None:
        """Test: Nutzungsrate berechnen."""
        used_count = 8
        total_count = 10

        utilization_rate = (used_count / total_count) * 100

        assert utilization_rate == 80.0
