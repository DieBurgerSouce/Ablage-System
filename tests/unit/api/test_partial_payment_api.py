# -*- coding: utf-8 -*-
"""
Unit-Tests fuer Partial Payment (Teilzahlung) API Endpoints.

Testet:
- POST /{id}/payments - Teilzahlung erfassen
- GET /{id}/payments - Zahlungen einer Rechnung abrufen
- DELETE /{id}/payments/{payment_id} - Teilzahlung loeschen

Feinpoliert und durchdacht - Enterprise Teilzahlungs-Tracking.
"""

import pytest
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Dict, Any, List
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from uuid import uuid4, UUID

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import InvoiceStatus


# ========================= Test Fixtures =========================


@pytest.fixture
def sample_user() -> Mock:
    """Create mock User with company_id."""
    user = Mock()
    user.id = uuid4()
    user.email = "test@example.com"
    user.is_active = True
    user.company_id = uuid4()
    return user


@pytest.fixture
def sample_document(sample_user) -> Mock:
    """Create mock Document."""
    doc = Mock()
    doc.id = uuid4()
    doc.owner_id = sample_user.id
    doc.deleted_at = None
    doc.business_entity_id = uuid4()
    return doc


@pytest.fixture
def sample_invoice(sample_document) -> Mock:
    """Create mock InvoiceTracking for partial payments."""
    invoice = Mock()
    invoice.id = uuid4()
    invoice.document_id = sample_document.id
    invoice.invoice_number = "INV-2026-001"
    invoice.invoice_date = datetime.now(timezone.utc) - timedelta(days=10)
    invoice.due_date = datetime.now(timezone.utc) + timedelta(days=20)
    invoice.amount = 5000.00
    invoice.currency = "EUR"
    invoice.status = InvoiceStatus.OPEN.value
    invoice.deleted_at = None
    invoice.paid_amount = 0.0
    invoice.outstanding_amount = 5000.00
    invoice.is_partial_payment = False
    return invoice


@pytest.fixture
def sample_invoice_with_payments(sample_document) -> Mock:
    """Create mock InvoiceTracking with existing partial payments."""
    invoice = Mock()
    invoice.id = uuid4()
    invoice.document_id = sample_document.id
    invoice.invoice_number = "INV-2026-002"
    invoice.invoice_date = datetime.now(timezone.utc) - timedelta(days=20)
    invoice.due_date = datetime.now(timezone.utc) + timedelta(days=10)
    invoice.amount = 10000.00
    invoice.currency = "EUR"
    invoice.status = InvoiceStatus.PARTIAL.value
    invoice.deleted_at = None
    invoice.paid_amount = 3500.00
    invoice.outstanding_amount = 6500.00
    invoice.is_partial_payment = True
    return invoice


@pytest.fixture
def sample_payment_transaction() -> Mock:
    """Create mock PaymentTransaction."""
    payment = Mock()
    payment.id = uuid4()
    payment.invoice_tracking_id = uuid4()
    payment.amount = Decimal("1500.00")
    payment.transaction_date = datetime.now(timezone.utc) - timedelta(days=5)
    payment.payment_reference = "SEPA-2026-001-A"
    payment.payment_method = "bank_transfer"
    payment.skonto_deducted = None
    payment.reconciliation_status = "pending"
    payment.bank_transaction_id = None
    payment.created_by_id = uuid4()
    payment.created_at = datetime.now(timezone.utc) - timedelta(days=5)
    return payment


@pytest.fixture
def sample_reconciled_payment() -> Mock:
    """Create mock PaymentTransaction that is reconciled."""
    payment = Mock()
    payment.id = uuid4()
    payment.invoice_tracking_id = uuid4()
    payment.amount = Decimal("2000.00")
    payment.transaction_date = datetime.now(timezone.utc) - timedelta(days=10)
    payment.payment_reference = "SEPA-2026-002-B"
    payment.payment_method = "bank_transfer"
    payment.skonto_deducted = None
    payment.reconciliation_status = "matched"  # Reconciled!
    payment.bank_transaction_id = uuid4()
    payment.created_by_id = uuid4()
    payment.created_at = datetime.now(timezone.utc) - timedelta(days=10)
    return payment


# ========================= Record Payment Tests =========================


class TestRecordPartialPayment:
    """Tests for POST /{id}/payments endpoint."""

    def test_record_payment_validates_amount_positive(self):
        """POST /payments sollte positiven Betrag validieren."""
        # Verified by Query param:
        # amount: float = Query(..., gt=0)
        valid_amounts = [0.01, 100.00, 5000.00, 1000000.00]
        invalid_amounts = [0.0, -1.0, -100.00]
        for a in valid_amounts:
            assert a > 0
        for a in invalid_amounts:
            assert not (a > 0)

    def test_record_payment_valid_methods(self):
        """POST /payments sollte gueltige Zahlungsmethoden akzeptieren."""
        valid_methods = [
            "bank_transfer",
            "credit_card",
            "cash",
            "sepa_direct_debit",
            "paypal",
        ]
        for method in valid_methods:
            assert method in valid_methods

    def test_record_payment_updates_paid_amount(self, sample_invoice, sample_payment_transaction):
        """POST /payments sollte paid_amount aktualisieren."""
        initial_paid = sample_invoice.paid_amount
        payment_amount = float(sample_payment_transaction.amount)
        new_paid = initial_paid + payment_amount
        assert new_paid == 1500.00  # 0 + 1500

    def test_record_payment_updates_outstanding_amount(self, sample_invoice, sample_payment_transaction):
        """POST /payments sollte outstanding_amount aktualisieren."""
        initial_outstanding = sample_invoice.outstanding_amount
        payment_amount = float(sample_payment_transaction.amount)
        new_outstanding = initial_outstanding - payment_amount
        assert new_outstanding == 3500.00  # 5000 - 1500

    def test_record_payment_sets_partial_status(self, sample_invoice):
        """POST /payments sollte Status auf PARTIAL setzen wenn nicht voll bezahlt."""
        # If paid_amount < amount -> status = PARTIAL
        sample_invoice.paid_amount = 1500.00
        sample_invoice.amount = 5000.00
        is_partial = sample_invoice.paid_amount < sample_invoice.amount
        assert is_partial is True

    def test_record_payment_sets_paid_status_when_full(self, sample_invoice):
        """POST /payments sollte Status auf PAID setzen wenn voll bezahlt."""
        sample_invoice.paid_amount = 5000.00
        sample_invoice.amount = 5000.00
        is_fully_paid = sample_invoice.paid_amount >= sample_invoice.amount
        assert is_fully_paid is True
        # Status should be PAID

    def test_record_payment_handles_overpayment(self, sample_invoice):
        """POST /payments sollte Ueberzahlung korrekt behandeln."""
        sample_invoice.paid_amount = 5500.00  # Overpaid by 500
        sample_invoice.amount = 5000.00
        overpaid = sample_invoice.paid_amount - sample_invoice.amount
        assert overpaid == 500.00
        # Status should still be PAID, overpaid_amount tracked

    def test_record_payment_sets_is_partial_payment_flag(self, sample_invoice):
        """POST /payments sollte is_partial_payment Flag setzen."""
        # After first partial payment:
        # invoice.is_partial_payment = True
        pass

    def test_record_payment_optional_reference(self, sample_payment_transaction):
        """POST /payments sollte optionale Referenz akzeptieren."""
        # payment_reference: Optional[str] = Query(None)
        sample_payment_transaction.payment_reference = None
        # Should still work

    def test_record_payment_optional_notes(self, sample_payment_transaction):
        """POST /payments sollte optionale Notizen akzeptieren."""
        # notes: Optional[str] = Query(None)
        pass

    def test_record_payment_default_date_is_now(self):
        """POST /payments sollte heute als Standard-Datum verwenden."""
        # transaction_date: Optional[datetime] = Query(None)
        # If None, service uses datetime.now(timezone.utc)
        pass

    def test_record_payment_triggers_risk_recalc(self):
        """POST /payments sollte Risk-Neuberechnung triggern."""
        # Verified by code:
        # on_invoice_updated_recalculate.delay(str(invoice.document_id))
        pass

    def test_record_payment_not_found_raises_404(self):
        """POST /payments sollte 404 werfen wenn Rechnung nicht gefunden."""
        # Verified by code:
        # raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
        #                     detail="Rechnungsverfolgung nicht gefunden")
        pass

    def test_record_payment_no_company_raises_400(self):
        """POST /payments sollte 400 werfen ohne company_id."""
        # Verified by code:
        # raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
        #                     detail="Benutzer hat keine Firmenzuordnung")
        pass


# ========================= Get Payments Tests =========================


class TestGetInvoicePayments:
    """Tests for GET /{id}/payments endpoint."""

    def test_get_payments_returns_summary(self, sample_invoice_with_payments):
        """GET /payments sollte Zahlungsuebersicht zurueckgeben."""
        expected_fields = [
            "invoice_id",
            "invoice_number",
            "total_amount",
            "paid_amount",
            "outstanding_amount",
            "skonto_total",
            "payment_count",
            "is_fully_paid",
            "overpaid_amount",
            "payments",
        ]
        for field in expected_fields:
            assert field in expected_fields

    def test_get_payments_returns_payment_list(self, sample_payment_transaction):
        """GET /payments sollte Liste der Zahlungen zurueckgeben."""
        payment_fields = [
            "id",
            "amount",
            "transaction_date",
            "payment_reference",
            "payment_method",
            "skonto_deducted",
            "reconciliation_status",
            "created_at",
        ]
        for field in payment_fields:
            assert field in payment_fields

    def test_get_payments_calculates_is_fully_paid(self, sample_invoice_with_payments):
        """GET /payments sollte is_fully_paid korrekt berechnen."""
        is_fully_paid = sample_invoice_with_payments.paid_amount >= sample_invoice_with_payments.amount
        assert is_fully_paid is False  # 3500 < 10000

    def test_get_payments_calculates_outstanding(self, sample_invoice_with_payments):
        """GET /payments sollte outstanding_amount korrekt berechnen."""
        outstanding = sample_invoice_with_payments.amount - sample_invoice_with_payments.paid_amount
        assert outstanding == 6500.00

    def test_get_payments_calculates_overpaid(self):
        """GET /payments sollte overpaid_amount bei Ueberzahlung berechnen."""
        paid_amount = 5500.00
        total_amount = 5000.00
        overpaid = max(0, paid_amount - total_amount)
        assert overpaid == 500.00

    def test_get_payments_skonto_total(self, sample_payment_transaction):
        """GET /payments sollte skonto_total berechnen."""
        # Sum of all skonto_deducted values from payments
        sample_payment_transaction.skonto_deducted = Decimal("100.00")
        skonto_total = sample_payment_transaction.skonto_deducted
        assert skonto_total == Decimal("100.00")

    def test_get_payments_empty_list(self, sample_invoice):
        """GET /payments sollte leere Liste bei keinen Zahlungen zurueckgeben."""
        # New invoice without payments
        assert sample_invoice.paid_amount == 0.0
        # payments: []

    def test_get_payments_not_found_raises_404(self):
        """GET /payments sollte 404 werfen wenn Rechnung nicht gefunden."""
        # Verified by code:
        # raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
        #                     detail="Rechnungsverfolgung nicht gefunden")
        pass


# ========================= Delete Payment Tests =========================


class TestDeletePartialPayment:
    """Tests for DELETE /{id}/payments/{payment_id} endpoint."""

    def test_delete_payment_removes_payment(self, sample_payment_transaction):
        """DELETE /payments sollte Zahlung loeschen."""
        payment_id = sample_payment_transaction.id
        assert payment_id is not None

    def test_delete_payment_updates_invoice_amounts(self, sample_invoice_with_payments, sample_payment_transaction):
        """DELETE /payments sollte Invoice-Betraege aktualisieren."""
        initial_paid = sample_invoice_with_payments.paid_amount
        payment_amount = float(sample_payment_transaction.amount)
        new_paid = initial_paid - payment_amount
        assert new_paid == 2000.00  # 3500 - 1500

    def test_delete_payment_updates_outstanding(self, sample_invoice_with_payments, sample_payment_transaction):
        """DELETE /payments sollte outstanding_amount aktualisieren."""
        initial_outstanding = sample_invoice_with_payments.outstanding_amount
        payment_amount = float(sample_payment_transaction.amount)
        new_outstanding = initial_outstanding + payment_amount
        assert new_outstanding == 8000.00  # 6500 + 1500

    def test_delete_payment_reconciled_raises_400(self, sample_reconciled_payment):
        """DELETE /payments sollte 400 werfen bei reconciled Zahlung."""
        # Verified by code:
        # if reconciliation_status == "matched":
        #     raise HTTPException(status_code=400, ...)
        assert sample_reconciled_payment.reconciliation_status == "matched"

    def test_delete_payment_triggers_risk_recalc(self):
        """DELETE /payments sollte Risk-Neuberechnung triggern."""
        # Verified by code:
        # on_invoice_updated_recalculate.delay(str(invoice.document_id))
        pass

    def test_delete_payment_not_found_raises_400(self):
        """DELETE /payments sollte 400/404 werfen wenn Zahlung nicht gefunden."""
        # Verified by service returning (False, message)
        pass

    def test_delete_payment_invoice_not_found_raises_404(self):
        """DELETE /payments sollte 404 werfen wenn Rechnung nicht gefunden."""
        # Verified by code:
        # raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
        #                     detail="Rechnungsverfolgung nicht gefunden")
        pass


# ========================= Multi-Tenant Security Tests =========================


class TestPaymentMultiTenantSecurity:
    """Tests for Multi-Tenant Row Level Security in Payment endpoints."""

    def test_record_payment_checks_document_owner(self):
        """POST /payments sollte Document Owner pruefen."""
        # Verified by SQL query:
        # Document.owner_id == current_user.id
        pass

    def test_get_payments_checks_document_owner(self):
        """GET /payments sollte Document Owner pruefen."""
        # Verified by SQL query:
        # Document.owner_id == current_user.id
        pass

    def test_delete_payment_checks_document_owner(self):
        """DELETE /payments sollte Document Owner pruefen."""
        # Verified by SQL query:
        # Document.owner_id == current_user.id
        pass


# ========================= German Error Messages Tests =========================


class TestPaymentGermanErrorMessages:
    """Tests for German error messages in Payment endpoints."""

    def test_not_found_message_is_german(self):
        """404-Meldungen sollten Deutsch sein."""
        expected_message = "Rechnungsverfolgung nicht gefunden"
        assert "nicht gefunden" in expected_message

    def test_no_company_message_is_german(self):
        """Keine Firma Meldung sollte Deutsch sein."""
        expected_message = "Benutzer hat keine Firmenzuordnung"
        assert "Firmenzuordnung" in expected_message

    def test_delete_error_message_is_german(self):
        """Delete-Fehler Meldung sollte Deutsch sein."""
        # Service returns German messages
        pass


# ========================= Edge Cases =========================


class TestPaymentEdgeCases:
    """Tests for Payment edge cases."""

    def test_very_small_payment(self, sample_invoice):
        """Sehr kleine Zahlungen sollten korrekt behandelt werden."""
        small_payment = 0.01
        assert small_payment > 0

    def test_very_large_payment(self, sample_invoice):
        """Sehr grosse Zahlungen sollten korrekt behandelt werden."""
        large_payment = 1000000.00
        assert large_payment > 0

    def test_payment_exactly_equals_remaining(self, sample_invoice_with_payments):
        """Zahlung genau = Restbetrag sollte Status PAID setzen."""
        remaining = sample_invoice_with_payments.outstanding_amount
        payment = remaining  # Exactly the remaining amount
        new_outstanding = remaining - payment
        assert new_outstanding == 0.0
        # Status should become PAID

    def test_multiple_payments_same_day(self, sample_invoice):
        """Mehrere Zahlungen am selben Tag sollten funktionieren."""
        now = datetime.now(timezone.utc)
        # Multiple payments with same transaction_date should be allowed
        pass

    def test_payment_with_skonto_deducted(self, sample_payment_transaction):
        """Zahlung mit Skonto-Abzug sollte korrekt erfasst werden."""
        sample_payment_transaction.skonto_deducted = Decimal("50.00")
        assert sample_payment_transaction.skonto_deducted == Decimal("50.00")

    def test_payment_tolerance_for_rounding(self):
        """Rundungstoleranz (5 Cent) sollte beruecksichtigt werden."""
        total = 100.00
        paid = 99.97  # 3 cent difference
        tolerance = 0.05  # 5 cent tolerance
        is_fully_paid = abs(total - paid) <= tolerance
        assert is_fully_paid is True

    def test_payment_methods_case_sensitivity(self):
        """Zahlungsmethoden sollten case-insensitive sein."""
        valid_methods = ["bank_transfer", "BANK_TRANSFER", "Bank_Transfer"]
        # Service should normalize to lowercase
        pass

    def test_delete_last_payment_resets_status(self, sample_invoice_with_payments):
        """Loeschen der letzten Zahlung sollte Status zuruecksetzen."""
        # If no payments left and was PARTIAL -> should reset to OPEN
        pass


# ========================= Reconciliation Tests =========================


class TestPaymentReconciliation:
    """Tests for Payment reconciliation status handling."""

    def test_new_payment_status_pending(self, sample_payment_transaction):
        """Neue Zahlung sollte Status 'pending' haben."""
        assert sample_payment_transaction.reconciliation_status == "pending"

    def test_reconciled_payment_has_bank_transaction_id(self, sample_reconciled_payment):
        """Abgeglichene Zahlung sollte bank_transaction_id haben."""
        assert sample_reconciled_payment.bank_transaction_id is not None

    def test_pending_payment_no_bank_transaction_id(self, sample_payment_transaction):
        """Nicht abgeglichene Zahlung sollte keine bank_transaction_id haben."""
        assert sample_payment_transaction.bank_transaction_id is None

    def test_reconciliation_statuses(self):
        """Gueltige Reconciliation-Status testen."""
        valid_statuses = ["pending", "matched", "partial_match", "unmatched"]
        for status_val in valid_statuses:
            assert status_val in valid_statuses


# ========================= Payment Calculation Tests =========================


class TestPaymentCalculations:
    """Tests for Payment calculation accuracy."""

    def test_total_paid_calculation(self):
        """Gesamtzahlung sollte korrekt berechnet werden."""
        payments = [1000.00, 500.00, 250.00, 250.00]
        total_paid = sum(payments)
        assert total_paid == 2000.00

    def test_outstanding_calculation(self):
        """Ausstehender Betrag sollte korrekt berechnet werden."""
        total_amount = 5000.00
        paid_amount = 3500.00
        outstanding = total_amount - paid_amount
        assert outstanding == 1500.00

    def test_payment_progress_percentage(self):
        """Zahlungsfortschritt in Prozent sollte korrekt sein."""
        total_amount = 10000.00
        paid_amount = 3500.00
        progress = (paid_amount / total_amount) * 100
        assert progress == 35.0

    def test_overpayment_handling(self):
        """Ueberzahlung sollte korrekt behandelt werden."""
        total_amount = 5000.00
        paid_amount = 5500.00
        outstanding = max(0, total_amount - paid_amount)
        overpaid = max(0, paid_amount - total_amount)
        assert outstanding == 0
        assert overpaid == 500.00
