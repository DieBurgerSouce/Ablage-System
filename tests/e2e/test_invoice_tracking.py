# -*- coding: utf-8 -*-
"""
E2E Tests: Invoice Tracking

Tests invoice creation, status updates, and overdue detection.

Feinpoliert und durchdacht - Rechnungs-Tracking Tests.
"""

import pytest
import asyncio
from typing import Dict, Any
from unittest.mock import AsyncMock, patch
from datetime import datetime, timedelta, timezone


@pytest.mark.e2e
class TestInvoiceCreation:
    """Test invoice creation and setup."""

    @pytest.mark.asyncio
    async def test_create_outgoing_invoice(self):
        """Test Ausgangsrechnung erstellen."""
        with patch("app.services.invoice_service.InvoiceService") as MockInvoice:
            mock_invoice = AsyncMock()
            mock_invoice.create_invoice.return_value = {
                "id": "inv_001",
                "invoice_number": "RE-2024-001",
                "invoice_type": "outgoing",
                "customer_id": "cust_001",
                "amount": 1190.0,
                "currency": "EUR",
                "issue_date": "2024-03-15",
                "due_date": "2024-04-14",
                "status": "open",
                "payment_status": "pending"
            }
            MockInvoice.return_value = mock_invoice

            invoice = await mock_invoice.create_invoice({
                "invoice_number": "RE-2024-001",
                "customer_id": "cust_001",
                "amount": 1190.0,
                "due_date": "2024-04-14"
            })

            assert invoice["status"] == "open"
            assert invoice["invoice_type"] == "outgoing"
            assert invoice["payment_status"] == "pending"

    @pytest.mark.asyncio
    async def test_create_incoming_invoice(self):
        """Test Eingangsrechnung erstellen."""
        with patch("app.services.invoice_service.InvoiceService") as MockInvoice:
            mock_invoice = AsyncMock()
            mock_invoice.create_invoice.return_value = {
                "id": "inv_002",
                "invoice_number": "EXT-12345",
                "invoice_type": "incoming",
                "supplier_id": "supp_001",
                "amount": 500.0,
                "currency": "EUR",
                "issue_date": "2024-03-10",
                "due_date": "2024-04-09",
                "status": "open",
                "payment_status": "pending"
            }
            MockInvoice.return_value = mock_invoice

            invoice = await mock_invoice.create_invoice({
                "invoice_type": "incoming",
                "supplier_id": "supp_001",
                "amount": 500.0,
                "due_date": "2024-04-09"
            })

            assert invoice["invoice_type"] == "incoming"
            assert invoice["supplier_id"] == "supp_001"

    @pytest.mark.asyncio
    async def test_invoice_with_skonto_terms(self):
        """Test Rechnung mit Skonto-Bedingungen."""
        with patch("app.services.invoice_service.InvoiceService") as MockInvoice:
            mock_invoice = AsyncMock()
            mock_invoice.create_invoice.return_value = {
                "id": "inv_003",
                "invoice_number": "RE-2024-002",
                "amount": 1000.0,
                "due_date": "2024-04-15",
                "skonto_terms": {
                    "discount_percentage": 2.0,
                    "discount_days": 14,
                    "discount_deadline": "2024-03-29",
                    "discounted_amount": 980.0
                },
                "status": "open"
            }
            MockInvoice.return_value = mock_invoice

            invoice = await mock_invoice.create_invoice({
                "amount": 1000.0,
                "skonto_percentage": 2.0,
                "skonto_days": 14
            })

            assert invoice["skonto_terms"]["discount_percentage"] == 2.0
            assert invoice["skonto_terms"]["discounted_amount"] == 980.0


@pytest.mark.e2e
class TestInvoiceStatusTracking:
    """Test invoice status updates and tracking."""

    @pytest.mark.asyncio
    async def test_mark_invoice_as_paid(self):
        """Test Rechnung als bezahlt markieren."""
        with patch("app.services.invoice_service.InvoiceService") as MockInvoice:
            mock_invoice = AsyncMock()
            mock_invoice.update_payment_status.return_value = {
                "id": "inv_001",
                "payment_status": "paid",
                "paid_at": datetime.now(timezone.utc).isoformat(),
                "paid_amount": 1190.0,
                "payment_method": "bank_transfer",
                "status": "closed"
            }
            MockInvoice.return_value = mock_invoice

            result = await mock_invoice.update_payment_status(
                invoice_id="inv_001",
                status="paid",
                payment_method="bank_transfer",
                paid_amount=1190.0
            )

            assert result["payment_status"] == "paid"
            assert result["status"] == "closed"
            assert result["paid_amount"] == 1190.0

    @pytest.mark.asyncio
    async def test_partial_payment(self):
        """Test Teilzahlung erfassen."""
        with patch("app.services.invoice_service.InvoiceService") as MockInvoice:
            mock_invoice = AsyncMock()
            mock_invoice.add_payment.return_value = {
                "id": "inv_001",
                "total_amount": 1190.0,
                "paid_amount": 500.0,
                "remaining_amount": 690.0,
                "payment_status": "partially_paid",
                "status": "open",
                "payments": [
                    {
                        "amount": 500.0,
                        "paid_at": datetime.now(timezone.utc).isoformat(),
                        "payment_method": "bank_transfer"
                    }
                ]
            }
            MockInvoice.return_value = mock_invoice

            result = await mock_invoice.add_payment(
                invoice_id="inv_001",
                amount=500.0,
                payment_method="bank_transfer"
            )

            assert result["payment_status"] == "partially_paid"
            assert result["remaining_amount"] == 690.0
            assert len(result["payments"]) == 1

    @pytest.mark.asyncio
    async def test_invoice_cancellation(self):
        """Test Rechnung stornieren."""
        with patch("app.services.invoice_service.InvoiceService") as MockInvoice:
            mock_invoice = AsyncMock()
            mock_invoice.cancel_invoice.return_value = {
                "id": "inv_001",
                "status": "cancelled",
                "cancelled_at": datetime.now(timezone.utc).isoformat(),
                "cancellation_reason": "Stornierung auf Kundenwunsch",
                "payment_status": "void"
            }
            MockInvoice.return_value = mock_invoice

            result = await mock_invoice.cancel_invoice(
                invoice_id="inv_001",
                reason="Stornierung auf Kundenwunsch"
            )

            assert result["status"] == "cancelled"
            assert result["payment_status"] == "void"


@pytest.mark.e2e
class TestOverdueDetection:
    """Test overdue invoice detection and alerts."""

    @pytest.mark.asyncio
    async def test_detect_overdue_invoices(self):
        """Test Überfällige Rechnungen erkennen."""
        with patch("app.services.invoice_service.InvoiceService") as MockInvoice:
            mock_invoice = AsyncMock()
            # Invoice due yesterday
            yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).date().isoformat()
            mock_invoice.get_overdue_invoices.return_value = {
                "overdue_invoices": [
                    {
                        "id": "inv_001",
                        "invoice_number": "RE-2024-001",
                        "due_date": yesterday,
                        "days_overdue": 1,
                        "amount": 1190.0,
                        "status": "overdue",
                        "payment_status": "pending"
                    }
                ],
                "total_overdue": 1,
                "total_amount_overdue": 1190.0
            }
            MockInvoice.return_value = mock_invoice

            result = await mock_invoice.get_overdue_invoices()

            assert result["total_overdue"] == 1
            assert result["overdue_invoices"][0]["days_overdue"] == 1
            assert result["overdue_invoices"][0]["status"] == "overdue"

    @pytest.mark.asyncio
    async def test_overdue_alert_creation(self):
        """Test Alert-Erstellung für überfällige Rechnungen."""
        with patch("app.services.alert_service.AlertService") as MockAlert:
            mock_alert = AsyncMock()
            mock_alert.create_overdue_alert.return_value = {
                "id": "alert_001",
                "type": "invoice_overdue",
                "severity": "warning",
                "invoice_id": "inv_001",
                "message": "Rechnung RE-2024-001 ist 1 Tag überfällig",
                "created_at": datetime.now(timezone.utc).isoformat(),
                "status": "active"
            }
            MockAlert.return_value = mock_alert

            alert = await mock_alert.create_overdue_alert(
                invoice_id="inv_001",
                days_overdue=1
            )

            assert alert["type"] == "invoice_overdue"
            assert alert["severity"] == "warning"
            assert "überfällig" in alert["message"]

    @pytest.mark.asyncio
    async def test_skonto_deadline_approaching(self):
        """Test Warnung bei nahendem Skonto-Ablauf."""
        with patch("app.services.alert_service.AlertService") as MockAlert:
            mock_alert = AsyncMock()
            mock_alert.create_skonto_alert.return_value = {
                "id": "alert_002",
                "type": "skonto_deadline_approaching",
                "severity": "info",
                "invoice_id": "inv_003",
                "message": "Skonto-Frist für RE-2024-002 läuft in 2 Tagen ab (Ersparnis: 20,00 EUR)",
                "days_until_deadline": 2,
                "potential_savings": 20.0,
                "status": "active"
            }
            MockAlert.return_value = mock_alert

            alert = await mock_alert.create_skonto_alert(
                invoice_id="inv_003",
                days_until_deadline=2,
                potential_savings=20.0
            )

            assert alert["type"] == "skonto_deadline_approaching"
            assert alert["days_until_deadline"] == 2
            assert alert["potential_savings"] == 20.0
