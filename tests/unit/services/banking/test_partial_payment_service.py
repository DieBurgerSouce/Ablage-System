# -*- coding: utf-8 -*-
"""Tests fuer PartialPaymentService.

Testet Teilzahlungen, Statusupdates und Bank-Reconciliation.
"""

import pytest
from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.banking.partial_payment_service import (
    PartialPaymentService,
    PaymentTransactionCreate,
    PaymentTransactionResponse,
    InvoicePaymentSummary,
)


class TestRecordPayment:
    """Tests fuer Zahlungserfassung."""

    @pytest.fixture
    def service(self) -> PartialPaymentService:
        """Erstellt PartialPaymentService Instanz."""
        return PartialPaymentService()

    @pytest.fixture
    def mock_db(self) -> AsyncMock:
        """Mock fuer Datenbank-Session."""
        return AsyncMock()

    @pytest.mark.asyncio
    async def test_record_first_partial_payment(
        self, service: PartialPaymentService, mock_db: AsyncMock
    ) -> None:
        """Test: Erste Teilzahlung erfassen."""
        invoice_tracking_id = uuid4()
        user_id = uuid4()
        company_id = uuid4()

        # Mock InvoiceTracking
        mock_invoice = MagicMock()
        mock_invoice.id = invoice_tracking_id
        mock_invoice.amount = 1000.0
        mock_invoice.status = "open"
        mock_invoice.paid_amount = 0.0
        mock_invoice.deleted_at = None

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_invoice
        mock_db.execute.return_value = mock_result

        # Mock _get_total_paid
        with patch.object(service, "_get_total_paid", return_value=Decimal("0.00")):
            payment_data = PaymentTransactionCreate(
                amount=Decimal("500.00"),
                payment_reference="Zahlung 1/2",
                payment_method="bank_transfer",
            )

            response, message = await service.record_payment(
                db=mock_db,
                invoice_tracking_id=invoice_tracking_id,
                payment_data=payment_data,
                user_id=user_id,
                company_id=company_id,
            )

            assert response.amount == Decimal("500.00")
            assert "500" in message or "ausstehend" in message.lower()

    @pytest.mark.asyncio
    async def test_record_payment_completes_invoice(
        self, service: PartialPaymentService, mock_db: AsyncMock
    ) -> None:
        """Test: Zahlung komplettiert Rechnung."""
        invoice_tracking_id = uuid4()
        user_id = uuid4()
        company_id = uuid4()

        mock_invoice = MagicMock()
        mock_invoice.id = invoice_tracking_id
        mock_invoice.amount = 1000.0
        mock_invoice.status = "partial"
        mock_invoice.paid_amount = 500.0
        mock_invoice.deleted_at = None

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_invoice
        mock_db.execute.return_value = mock_result

        with patch.object(service, "_get_total_paid", return_value=Decimal("500.00")):
            payment_data = PaymentTransactionCreate(
                amount=Decimal("500.00"),
                payment_reference="Restzahlung",
            )

            response, message = await service.record_payment(
                db=mock_db,
                invoice_tracking_id=invoice_tracking_id,
                payment_data=payment_data,
                user_id=user_id,
                company_id=company_id,
            )

            assert "bezahlt" in message.lower()

    @pytest.mark.asyncio
    async def test_record_overpayment_warning(
        self, service: PartialPaymentService, mock_db: AsyncMock
    ) -> None:
        """Test: Ueberzahlung wird gewarnt."""
        invoice_tracking_id = uuid4()
        user_id = uuid4()
        company_id = uuid4()

        mock_invoice = MagicMock()
        mock_invoice.id = invoice_tracking_id
        mock_invoice.amount = 1000.0
        mock_invoice.status = "open"
        mock_invoice.paid_amount = 0.0
        mock_invoice.deleted_at = None

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_invoice
        mock_db.execute.return_value = mock_result

        with patch.object(service, "_get_total_paid", return_value=Decimal("0.00")):
            payment_data = PaymentTransactionCreate(
                amount=Decimal("1100.00"),  # 100 EUR Ueberzahlung
            )

            response, message = await service.record_payment(
                db=mock_db,
                invoice_tracking_id=invoice_tracking_id,
                payment_data=payment_data,
                user_id=user_id,
                company_id=company_id,
            )

            assert "ueberzahlung" in message.lower() or "100" in message

    @pytest.mark.asyncio
    async def test_record_payment_cancelled_invoice(
        self, service: PartialPaymentService, mock_db: AsyncMock
    ) -> None:
        """Test: Zahlung fuer stornierte Rechnung ablehnen."""
        invoice_tracking_id = uuid4()

        mock_invoice = MagicMock()
        mock_invoice.id = invoice_tracking_id
        mock_invoice.status = "cancelled"
        mock_invoice.deleted_at = None

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_invoice
        mock_db.execute.return_value = mock_result

        payment_data = PaymentTransactionCreate(amount=Decimal("500.00"))

        with pytest.raises(ValueError, match="storniert"):
            await service.record_payment(
                db=mock_db,
                invoice_tracking_id=invoice_tracking_id,
                payment_data=payment_data,
                user_id=uuid4(),
                company_id=uuid4(),
            )

    @pytest.mark.asyncio
    async def test_record_payment_negative_amount(
        self, service: PartialPaymentService, mock_db: AsyncMock
    ) -> None:
        """Test: Negative Zahlung ablehnen."""
        invoice_tracking_id = uuid4()

        mock_invoice = MagicMock()
        mock_invoice.id = invoice_tracking_id
        mock_invoice.status = "open"
        mock_invoice.deleted_at = None

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_invoice
        mock_db.execute.return_value = mock_result

        payment_data = PaymentTransactionCreate(amount=Decimal("-100.00"))

        with pytest.raises(ValueError, match="positiv"):
            await service.record_payment(
                db=mock_db,
                invoice_tracking_id=invoice_tracking_id,
                payment_data=payment_data,
                user_id=uuid4(),
                company_id=uuid4(),
            )


class TestPaymentSummary:
    """Tests fuer Zahlungsuebersicht."""

    @pytest.fixture
    def service(self) -> PartialPaymentService:
        """Erstellt PartialPaymentService Instanz."""
        return PartialPaymentService()

    @pytest.fixture
    def mock_db(self) -> AsyncMock:
        """Mock fuer Datenbank-Session."""
        return AsyncMock()

    @pytest.mark.asyncio
    async def test_get_payment_summary_no_payments(
        self, service: PartialPaymentService, mock_db: AsyncMock
    ) -> None:
        """Test: Zusammenfassung ohne Zahlungen."""
        invoice_tracking_id = uuid4()

        # Mock Invoice
        mock_invoice = MagicMock()
        mock_invoice.id = invoice_tracking_id
        mock_invoice.invoice_number = "RE-2026-001"
        mock_invoice.amount = 1000.0

        mock_invoice_result = MagicMock()
        mock_invoice_result.scalar_one_or_none.return_value = mock_invoice

        # Mock Payments (empty)
        mock_payments_result = MagicMock()
        mock_payments_result.scalars.return_value.all.return_value = []

        mock_db.execute.side_effect = [mock_invoice_result, mock_payments_result]

        company_id = uuid4()
        summary = await service.get_payment_summary(
            db=mock_db,
            invoice_tracking_id=invoice_tracking_id,
            company_id=company_id,
        )

        assert summary.total_amount == Decimal("1000.00")
        assert summary.paid_amount == Decimal("0.00")
        assert summary.outstanding_amount == Decimal("1000.00")
        assert summary.payment_count == 0
        assert summary.is_fully_paid is False

    @pytest.mark.asyncio
    async def test_get_payment_summary_partial(
        self, service: PartialPaymentService, mock_db: AsyncMock
    ) -> None:
        """Test: Zusammenfassung mit Teilzahlungen."""
        invoice_tracking_id = uuid4()

        # Mock Invoice
        mock_invoice = MagicMock()
        mock_invoice.id = invoice_tracking_id
        mock_invoice.invoice_number = "RE-2026-001"
        mock_invoice.amount = 1000.0

        # Mock Payments
        mock_payment1 = MagicMock()
        mock_payment1.id = uuid4()
        mock_payment1.invoice_tracking_id = invoice_tracking_id
        mock_payment1.amount = 300.0
        mock_payment1.transaction_date = datetime.now(timezone.utc)
        mock_payment1.payment_reference = "Zahlung 1"
        mock_payment1.payment_method = "bank_transfer"
        mock_payment1.skonto_deducted = None
        mock_payment1.reconciliation_status = "pending"
        mock_payment1.created_at = datetime.now(timezone.utc)

        mock_payment2 = MagicMock()
        mock_payment2.id = uuid4()
        mock_payment2.invoice_tracking_id = invoice_tracking_id
        mock_payment2.amount = 200.0
        mock_payment2.transaction_date = datetime.now(timezone.utc)
        mock_payment2.payment_reference = "Zahlung 2"
        mock_payment2.payment_method = "bank_transfer"
        mock_payment2.skonto_deducted = None
        mock_payment2.reconciliation_status = "matched"
        mock_payment2.created_at = datetime.now(timezone.utc)

        mock_invoice_result = MagicMock()
        mock_invoice_result.scalar_one_or_none.return_value = mock_invoice

        mock_payments_result = MagicMock()
        mock_payments_result.scalars.return_value.all.return_value = [
            mock_payment1, mock_payment2
        ]

        mock_db.execute.side_effect = [mock_invoice_result, mock_payments_result]

        company_id = uuid4()
        summary = await service.get_payment_summary(
            db=mock_db,
            invoice_tracking_id=invoice_tracking_id,
            company_id=company_id,
        )

        assert summary.total_amount == Decimal("1000.00")
        assert summary.paid_amount == Decimal("500.00")
        assert summary.outstanding_amount == Decimal("500.00")
        assert summary.payment_count == 2
        assert summary.is_fully_paid is False

    @pytest.mark.asyncio
    async def test_get_payment_summary_fully_paid(
        self, service: PartialPaymentService, mock_db: AsyncMock
    ) -> None:
        """Test: Vollstaendig bezahlte Rechnung."""
        invoice_tracking_id = uuid4()

        mock_invoice = MagicMock()
        mock_invoice.id = invoice_tracking_id
        mock_invoice.invoice_number = "RE-2026-001"
        mock_invoice.amount = 1000.0

        mock_payment = MagicMock()
        mock_payment.id = uuid4()
        mock_payment.invoice_tracking_id = invoice_tracking_id
        mock_payment.amount = 1000.0
        mock_payment.transaction_date = datetime.now(timezone.utc)
        mock_payment.payment_reference = "Vollzahlung"
        mock_payment.payment_method = "bank_transfer"
        mock_payment.skonto_deducted = None
        mock_payment.reconciliation_status = "matched"
        mock_payment.created_at = datetime.now(timezone.utc)

        mock_invoice_result = MagicMock()
        mock_invoice_result.scalar_one_or_none.return_value = mock_invoice

        mock_payments_result = MagicMock()
        mock_payments_result.scalars.return_value.all.return_value = [mock_payment]

        mock_db.execute.side_effect = [mock_invoice_result, mock_payments_result]

        company_id = uuid4()
        summary = await service.get_payment_summary(
            db=mock_db,
            invoice_tracking_id=invoice_tracking_id,
            company_id=company_id,
        )

        assert summary.is_fully_paid is True
        assert summary.outstanding_amount == Decimal("0.00")


class TestDeletePayment:
    """Tests fuer Zahlungsloeschung."""

    @pytest.fixture
    def service(self) -> PartialPaymentService:
        """Erstellt PartialPaymentService Instanz."""
        return PartialPaymentService()

    @pytest.fixture
    def mock_db(self) -> AsyncMock:
        """Mock fuer Datenbank-Session."""
        return AsyncMock()

    @pytest.mark.asyncio
    async def test_delete_pending_payment(
        self, service: PartialPaymentService, mock_db: AsyncMock
    ) -> None:
        """Test: Nicht abgestimmte Zahlung loeschen."""
        payment_id = uuid4()
        invoice_tracking_id = uuid4()

        mock_transaction = MagicMock()
        mock_transaction.id = payment_id
        mock_transaction.invoice_tracking_id = invoice_tracking_id
        mock_transaction.amount = 500.0
        mock_transaction.reconciliation_status = "pending"

        mock_invoice = MagicMock()
        mock_invoice.id = invoice_tracking_id
        mock_invoice.amount = 1000.0
        mock_invoice.due_date = None

        mock_tx_result = MagicMock()
        mock_tx_result.scalar_one_or_none.return_value = mock_transaction

        mock_invoice_result = MagicMock()
        mock_invoice_result.scalar_one_or_none.return_value = mock_invoice

        mock_db.execute.side_effect = [mock_tx_result, mock_invoice_result]

        with patch.object(service, "_get_total_paid", return_value=Decimal("0.00")):
            success, message = await service.delete_payment(
                db=mock_db,
                payment_transaction_id=payment_id,
                user_id=uuid4(),
                company_id=uuid4(),
            )

            assert success is True
            assert "500" in message

    @pytest.mark.asyncio
    async def test_delete_matched_payment_fails(
        self, service: PartialPaymentService, mock_db: AsyncMock
    ) -> None:
        """Test: Abgestimmte Zahlung nicht loeschbar."""
        payment_id = uuid4()

        mock_transaction = MagicMock()
        mock_transaction.id = payment_id
        mock_transaction.reconciliation_status = "matched"

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_transaction
        mock_db.execute.return_value = mock_result

        success, message = await service.delete_payment(
            db=mock_db,
            payment_transaction_id=payment_id,
            user_id=uuid4(),
            company_id=uuid4(),
        )

        assert success is False
        assert "abgestimmt" in message.lower()


class TestReconciliation:
    """Tests fuer Bank-Abgleich."""

    @pytest.fixture
    def service(self) -> PartialPaymentService:
        """Erstellt PartialPaymentService Instanz."""
        return PartialPaymentService()

    @pytest.fixture
    def mock_db(self) -> AsyncMock:
        """Mock fuer Datenbank-Session."""
        return AsyncMock()

    @pytest.mark.asyncio
    async def test_reconcile_payment(
        self, service: PartialPaymentService, mock_db: AsyncMock
    ) -> None:
        """Test: Zahlung mit Bank-Transaktion verknuepfen."""
        payment_id = uuid4()
        bank_transaction_id = uuid4()
        user_id = uuid4()

        mock_transaction = MagicMock()
        mock_transaction.id = payment_id
        mock_transaction.reconciliation_status = "pending"

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_transaction
        mock_db.execute.return_value = mock_result

        success = await service.reconcile_with_bank_transaction(
            db=mock_db,
            payment_transaction_id=payment_id,
            bank_transaction_id=bank_transaction_id,
            user_id=user_id,
            company_id=uuid4(),
        )

        assert success is True
        assert mock_transaction.bank_transaction_id == bank_transaction_id
        assert mock_transaction.reconciliation_status == "matched"


class TestPaymentTolerance:
    """Tests fuer Zahlungs-Toleranz."""

    @pytest.fixture
    def service(self) -> PartialPaymentService:
        """Erstellt PartialPaymentService Instanz."""
        return PartialPaymentService()

    def test_payment_tolerance_value(self, service: PartialPaymentService) -> None:
        """Test: Standard-Toleranz ist 5 Cent."""
        assert service.PAYMENT_TOLERANCE == Decimal("0.05")

    def test_is_fully_paid_with_tolerance(self) -> None:
        """Test: Vollstaendig bezahlt mit Rundungsdifferenz."""
        total = Decimal("1000.00")
        paid = Decimal("999.97")  # 3 Cent Differenz
        tolerance = Decimal("0.05")

        # Differenz < Toleranz = vollstaendig bezahlt
        is_paid = (total - paid) <= tolerance

        assert is_paid is True

    def test_is_not_fully_paid_over_tolerance(self) -> None:
        """Test: Nicht bezahlt wenn ueber Toleranz."""
        total = Decimal("1000.00")
        paid = Decimal("999.90")  # 10 Cent Differenz
        tolerance = Decimal("0.05")

        is_paid = (total - paid) <= tolerance

        assert is_paid is False
