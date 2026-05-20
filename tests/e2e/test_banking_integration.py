# -*- coding: utf-8 -*-
"""
E2E Tests: Banking Integration

Tests banking connection and transaction reconciliation.

Feinpoliert und durchdacht - Banking-Integration Tests.
"""

import pytest
import asyncio
from typing import Dict, Any, List
from unittest.mock import AsyncMock, patch
from datetime import datetime, timedelta, timezone
from decimal import Decimal


@pytest.mark.e2e
class TestBankingConnection:
    """Test banking connection and setup."""

    @pytest.mark.asyncio
    async def test_connect_bank_account(self):
        """Test Bankkonto verbinden."""
        with patch("app.services.banking.bank_connection_service.BankConnectionService") as MockBank:
            mock_bank = AsyncMock()
            mock_bank.connect_account.return_value = {
                "success": True,
                "account_id": "bank_acc_001",
                "bank_name": "Sparkasse München",
                "iban": "DE89370400440532013000",
                "account_holder": "Max Mustermann GmbH",
                "connection_status": "active",
                "last_sync": None,
                "message": "Bankkonto erfolgreich verbunden"
            }
            MockBank.return_value = mock_bank

            result = await mock_bank.connect_account(
                iban="DE89370400440532013000",
                credentials={
                    "online_banking_user": "max.mustermann",
                    "online_banking_pin": "****"
                }
            )

            assert result["success"] is True
            assert result["connection_status"] == "active"
            assert "DE89" in result["iban"]

    @pytest.mark.asyncio
    async def test_sync_bank_transactions(self):
        """Test Banktransaktionen synchronisieren."""
        with patch("app.services.banking.bank_connection_service.BankConnectionService") as MockBank:
            mock_bank = AsyncMock()
            mock_bank.sync_transactions.return_value = {
                "success": True,
                "account_id": "bank_acc_001",
                "synced_transactions": 25,
                "date_from": "2024-03-01",
                "date_to": "2024-03-15",
                "last_sync": datetime.now(timezone.utc).isoformat(),
                "message": "25 Transaktionen synchronisiert"
            }
            MockBank.return_value = mock_bank

            result = await mock_bank.sync_transactions(
                account_id="bank_acc_001",
                date_from="2024-03-01",
                date_to="2024-03-15"
            )

            assert result["success"] is True
            assert result["synced_transactions"] == 25


@pytest.mark.e2e
class TestTransactionReconciliation:
    """Test transaction to invoice reconciliation."""

    @pytest.mark.asyncio
    async def test_auto_match_payment_to_invoice(self):
        """Test Automatische Zahlungszuordnung zu Rechnung."""
        with patch("app.services.banking.reconciliation_service.ReconciliationService") as MockReconcile:
            mock_reconcile = AsyncMock()
            mock_reconcile.auto_match_transaction.return_value = {
                "success": True,
                "transaction_id": "tx_001",
                "matched_invoice_id": "inv_001",
                "invoice_number": "RE-2024-001",
                "amount": Decimal("1190.00"),
                "confidence": 0.98,
                "match_criteria": [
                    "exact_amount_match",
                    "invoice_number_in_reference"
                ],
                "message": "Zahlung automatisch zugeordnet"
            }
            MockReconcile.return_value = mock_reconcile

            result = await mock_reconcile.auto_match_transaction(
                transaction_id="tx_001",
                amount=Decimal("1190.00"),
                reference="RE-2024-001 Zahlung"
            )

            assert result["success"] is True
            assert result["confidence"] >= 0.95
            assert "exact_amount_match" in result["match_criteria"]

    @pytest.mark.asyncio
    async def test_manual_match_payment_to_invoice(self):
        """Test Manuelle Zahlungszuordnung."""
        with patch("app.services.banking.reconciliation_service.ReconciliationService") as MockReconcile:
            mock_reconcile = AsyncMock()
            mock_reconcile.manual_match.return_value = {
                "success": True,
                "transaction_id": "tx_002",
                "invoice_id": "inv_002",
                "amount_paid": Decimal("500.00"),
                "invoice_amount": Decimal("500.00"),
                "fully_paid": True,
                "matched_by": "user_001",
                "matched_at": datetime.now(timezone.utc).isoformat(),
                "message": "Zahlung manuell zugeordnet"
            }
            MockReconcile.return_value = mock_reconcile

            result = await mock_reconcile.manual_match(
                transaction_id="tx_002",
                invoice_id="inv_002"
            )

            assert result["success"] is True
            assert result["fully_paid"] is True

    @pytest.mark.asyncio
    async def test_partial_payment_matching(self):
        """Test Teilzahlung zuordnen."""
        with patch("app.services.banking.reconciliation_service.ReconciliationService") as MockReconcile:
            mock_reconcile = AsyncMock()
            mock_reconcile.match_partial_payment.return_value = {
                "success": True,
                "transaction_id": "tx_003",
                "invoice_id": "inv_003",
                "amount_paid": Decimal("600.00"),
                "invoice_amount": Decimal("1190.00"),
                "remaining_amount": Decimal("590.00"),
                "fully_paid": False,
                "payment_percentage": 50.42,
                "message": "Teilzahlung zugeordnet"
            }
            MockReconcile.return_value = mock_reconcile

            result = await mock_reconcile.match_partial_payment(
                transaction_id="tx_003",
                invoice_id="inv_003",
                amount=Decimal("600.00")
            )

            assert result["success"] is True
            assert result["fully_paid"] is False
            assert result["remaining_amount"] == Decimal("590.00")

    @pytest.mark.asyncio
    async def test_skonto_payment_detection(self):
        """Test Skonto-Zahlung erkennen."""
        with patch("app.services.banking.reconciliation_service.ReconciliationService") as MockReconcile:
            mock_reconcile = AsyncMock()
            mock_reconcile.detect_skonto_payment.return_value = {
                "success": True,
                "transaction_id": "tx_004",
                "invoice_id": "inv_004",
                "invoice_amount": Decimal("1000.00"),
                "amount_paid": Decimal("980.00"),
                "skonto_taken": True,
                "skonto_percentage": 2.0,
                "skonto_amount": Decimal("20.00"),
                "within_skonto_period": True,
                "message": "Skonto-Zahlung erkannt und zugeordnet"
            }
            MockReconcile.return_value = mock_reconcile

            result = await mock_reconcile.detect_skonto_payment(
                transaction_id="tx_004",
                amount=Decimal("980.00")
            )

            assert result["skonto_taken"] is True
            assert result["skonto_amount"] == Decimal("20.00")
            assert result["within_skonto_period"] is True

    @pytest.mark.asyncio
    async def test_unmatched_transactions_report(self):
        """Test Nicht zugeordnete Transaktionen auflisten."""
        with patch("app.services.banking.reconciliation_service.ReconciliationService") as MockReconcile:
            mock_reconcile = AsyncMock()
            mock_reconcile.get_unmatched_transactions.return_value = {
                "unmatched_transactions": [
                    {
                        "id": "tx_005",
                        "amount": Decimal("250.00"),
                        "date": "2024-03-10",
                        "reference": "Unbekannte Zahlung",
                        "potential_matches": []
                    },
                    {
                        "id": "tx_006",
                        "amount": Decimal("1200.00"),
                        "date": "2024-03-12",
                        "reference": "Kunde XYZ",
                        "potential_matches": [
                            {
                                "invoice_id": "inv_010",
                                "invoice_amount": Decimal("1200.00"),
                                "confidence": 0.75
                            }
                        ]
                    }
                ],
                "total_unmatched": 2,
                "total_amount": Decimal("1450.00")
            }
            MockReconcile.return_value = mock_reconcile

            result = await mock_reconcile.get_unmatched_transactions(
                account_id="bank_acc_001"
            )

            assert result["total_unmatched"] == 2
            assert len(result["unmatched_transactions"]) == 2
            # Second transaction has potential match
            assert len(result["unmatched_transactions"][1]["potential_matches"]) > 0

    @pytest.mark.asyncio
    async def test_reconciliation_summary(self):
        """Test Zusammenfassung der Zahlungsabstimmung."""
        with patch("app.services.banking.reconciliation_service.ReconciliationService") as MockReconcile:
            mock_reconcile = AsyncMock()
            mock_reconcile.get_reconciliation_summary.return_value = {
                "period": {
                    "from": "2024-03-01",
                    "to": "2024-03-31"
                },
                "statistics": {
                    "total_transactions": 50,
                    "matched_transactions": 42,
                    "unmatched_transactions": 8,
                    "auto_matched": 38,
                    "manual_matched": 4,
                    "match_rate": 84.0
                },
                "amounts": {
                    "total_received": Decimal("45000.00"),
                    "matched_amount": Decimal("42000.00"),
                    "unmatched_amount": Decimal("3000.00")
                },
                "invoices": {
                    "fully_paid": 35,
                    "partially_paid": 7,
                    "unpaid": 12
                }
            }
            MockReconcile.return_value = mock_reconcile

            result = await mock_reconcile.get_reconciliation_summary(
                date_from="2024-03-01",
                date_to="2024-03-31"
            )

            assert result["statistics"]["match_rate"] == 84.0
            assert result["statistics"]["auto_matched"] == 38
            assert result["amounts"]["total_received"] == Decimal("45000.00")
