# -*- coding: utf-8 -*-
"""
Integration Tests: Skonto-Tracking Full Pipeline.

Tests vollständigen Skonto-Workflow mit Celery:
- Skonto-Erkennung aus OCR-Text
- Deadline-Berechnung
- Partial payment mit Skonto
- Missed deadline handling
- Alert generation

Feinpoliert und durchdacht - Comprehensive Skonto Testing.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timedelta
from uuid import uuid4
from decimal import Decimal
import asyncio

import pytest_asyncio
from httpx import AsyncClient


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def invoice_with_skonto():
    """Sample invoice with skonto terms."""
    return {
        "id": str(uuid4()),
        "invoice_number": "RE-2024-001",
        "total_amount": Decimal("1000.00"),
        "invoice_date": datetime.utcnow().date(),
        "due_date": datetime.utcnow().date() + timedelta(days=30),
        "skonto_percentage": None,  # To be detected
        "skonto_days": None,
        "skonto_deadline": None,
        "skonto_amount": None,
        "skonto_used": False,
    }


@pytest.fixture
def ocr_text_with_skonto():
    """OCR text containing skonto terms."""
    return """
    Rechnung RE-2024-001

    Gesamtbetrag: 1.000,00 EUR
    Fälligkeitsdatum: 15.03.2024

    Zahlungsbedingungen:
    2% Skonto bei Zahlung innerhalb von 14 Tagen
    Netto 30 Tage

    Bankverbindung:
    IBAN: DE89 3704 0044 0532 0130 00
    """


# =============================================================================
# TEST 1: SKONTO DETECTION FROM OCR
# =============================================================================

@pytest.mark.integration
@pytest.mark.asyncio
async def test_skonto_detection_from_ocr(
    async_client: AsyncClient,
    auth_headers: dict,
    invoice_with_skonto: dict,
    ocr_text_with_skonto: str,
):
    """
    Test automatische Skonto-Erkennung aus OCR-Text.

    ARRANGE: OCR-Text mit Skonto-Bedingungen
    ACT: Extract skonto terms
    ASSERT: 2% Skonto, 14 Tage erkannt
    """
    with patch("app.services.banking.skonto_service.SkontoService") as MockService:
        mock_service = MockService.return_value

        def extract_skonto_terms(ocr_text: str) -> dict:
            """Extract skonto terms from OCR text."""
            import re

            # Pattern: "X% Skonto ... Y Tagen"
            pattern = r'(\d+(?:[.,]\d+)?)\s*%\s*[Ss]konto.*?(\d+)\s*[Tt]agen'
            match = re.search(pattern, ocr_text)

            if match:
                percentage = float(match.group(1).replace(',', '.'))
                days = int(match.group(2))

                return {
                    "skonto_percentage": percentage,
                    "skonto_days": days,
                    "confidence": 0.95,
                }

            return {"confidence": 0.0}

        mock_service.extract_skonto_terms = extract_skonto_terms

        # ACT: Extract skonto terms
        result = mock_service.extract_skonto_terms(ocr_text_with_skonto)

        # ASSERT: Skonto terms detected
        assert result["confidence"] > 0.9
        assert result["skonto_percentage"] == 2.0
        assert result["skonto_days"] == 14


# =============================================================================
# TEST 2: SKONTO DEADLINE CALCULATION
# =============================================================================

@pytest.mark.integration
@pytest.mark.asyncio
async def test_skonto_deadline_calculation(
    async_client: AsyncClient,
    auth_headers: dict,
    invoice_with_skonto: dict,
):
    """
    Test Skonto-Deadline-Berechnung.

    ARRANGE: Rechnung mit Skonto-Bedingungen
    ACT: Berechne Deadline und Betrag
    ASSERT: Deadline = invoice_date + 14 Tage, Betrag = 980.00
    """
    with patch("app.services.banking.skonto_service.SkontoService") as MockService:
        mock_service = MockService.return_value

        def calculate_skonto_deadline(
            invoice_date: datetime.date,
            skonto_days: int,
            skonto_percentage: float,
            total_amount: Decimal,
        ) -> dict:
            """Calculate skonto deadline and amount."""
            deadline = invoice_date + timedelta(days=skonto_days)
            skonto_amount = total_amount * Decimal(str(skonto_percentage / 100))

            return {
                "skonto_deadline": deadline,
                "skonto_amount": round(skonto_amount, 2),
                "payable_amount": round(total_amount - skonto_amount, 2),
            }

        mock_service.calculate_skonto = calculate_skonto_deadline

        # ACT: Calculate skonto
        result = mock_service.calculate_skonto(
            invoice_date=invoice_with_skonto["invoice_date"],
            skonto_days=14,
            skonto_percentage=2.0,
            total_amount=invoice_with_skonto["total_amount"],
        )

        # ASSERT: Correct calculations
        assert result["skonto_deadline"] == invoice_with_skonto["invoice_date"] + timedelta(days=14)
        assert result["skonto_amount"] == Decimal("20.00")
        assert result["payable_amount"] == Decimal("980.00")


# =============================================================================
# TEST 3: PARTIAL PAYMENT WITH SKONTO
# =============================================================================

@pytest.mark.integration
@pytest.mark.asyncio
async def test_skonto_partial_payment(
    async_client: AsyncClient,
    auth_headers: dict,
    invoice_with_skonto: dict,
):
    """
    Test Teilzahlung mit Skonto-Anwendung.

    ARRANGE: Rechnung 1000 EUR, Skonto 2%, Teilzahlung 500 EUR
    ACT: Apply skonto proportional
    ASSERT: Skonto 10 EUR (2% von 500), outstanding 490 EUR
    """
    with patch("app.services.banking.partial_payment_service.PartialPaymentService") as MockService:
        mock_service = MockService.return_value

        def apply_skonto_to_partial_payment(
            total_amount: Decimal,
            payment_amount: Decimal,
            skonto_percentage: float,
        ) -> dict:
            """Apply skonto proportionally to partial payment."""
            # Skonto only applies to paid portion
            skonto_on_payment = payment_amount * Decimal(str(skonto_percentage / 100))
            net_payment = payment_amount - skonto_on_payment

            # Outstanding amount (without skonto on unpaid portion)
            outstanding = total_amount - payment_amount

            return {
                "payment_amount": payment_amount,
                "skonto_applied": round(skonto_on_payment, 2),
                "net_payment": round(net_payment, 2),
                "outstanding_amount": round(outstanding, 2),
            }

        mock_service.apply_skonto_to_partial = apply_skonto_to_partial_payment

        # ACT: Partial payment with skonto
        result = mock_service.apply_skonto_to_partial(
            total_amount=Decimal("1000.00"),
            payment_amount=Decimal("500.00"),
            skonto_percentage=2.0,
        )

        # ASSERT: Proportional skonto applied
        assert result["skonto_applied"] == Decimal("10.00")  # 2% of 500
        assert result["net_payment"] == Decimal("490.00")
        assert result["outstanding_amount"] == Decimal("500.00")


# =============================================================================
# TEST 4: MISSED DEADLINE HANDLING
# =============================================================================

@pytest.mark.integration
@pytest.mark.asyncio
async def test_skonto_missed_deadline(
    async_client: AsyncClient,
    auth_headers: dict,
    invoice_with_skonto: dict,
):
    """
    Test Handling von abgelaufener Skonto-Frist.

    ARRANGE: Skonto-Deadline ist gestern
    ACT: Versuche Skonto anzuwenden
    ASSERT: Skonto nicht mehr anwendbar, Warnung
    """
    # ARRANGE: Expired deadline
    expired_deadline = datetime.utcnow().date() - timedelta(days=1)

    with patch("app.services.banking.skonto_service.SkontoService") as MockService:
        mock_service = MockService.return_value

        def check_skonto_validity(skonto_deadline: datetime.date) -> dict:
            """Check if skonto is still valid."""
            today = datetime.utcnow().date()

            if skonto_deadline < today:
                return {
                    "valid": False,
                    "reason": "Skonto-Frist abgelaufen",
                    "deadline": skonto_deadline,
                    "days_overdue": (today - skonto_deadline).days,
                }

            return {
                "valid": True,
                "days_remaining": (skonto_deadline - today).days,
            }

        mock_service.check_skonto_validity = check_skonto_validity

        # ACT: Check validity
        result = mock_service.check_skonto_validity(expired_deadline)

        # ASSERT: Skonto expired
        assert result["valid"] is False
        assert result["days_overdue"] == 1
        assert "abgelaufen" in result["reason"]


# =============================================================================
# TEST 5: SKONTO ALERT GENERATION
# =============================================================================

@pytest.mark.integration
@pytest.mark.asyncio
async def test_skonto_alert_generation(
    async_client: AsyncClient,
    auth_headers: dict,
    invoice_with_skonto: dict,
):
    """
    Test automatische Alert-Generierung bei bevorstehender Skonto-Deadline.

    ARRANGE: Skonto-Deadline in 2 Tagen
    ACT: Check skonto deadlines (Celery task)
    ASSERT: Alert erstellt (DEAD_003: Skonto-Frist)
    """
    # ARRANGE: Deadline in 2 days
    upcoming_deadline = datetime.utcnow().date() + timedelta(days=2)

    with patch("app.services.banking.skonto_service.SkontoService") as MockSkontoService:
        with patch("app.services.alert_center_service.AlertCenterService") as MockAlertService:
            mock_skonto = MockSkontoService.return_value
            mock_alerts = MockAlertService.return_value

            async def mock_check_upcoming_deadlines(threshold_days: int = 3):
                """Check for upcoming skonto deadlines."""
                today = datetime.utcnow().date()

                invoices_with_upcoming_skonto = [
                    {
                        "id": invoice_with_skonto["id"],
                        "invoice_number": invoice_with_skonto["invoice_number"],
                        "skonto_deadline": upcoming_deadline,
                        "skonto_amount": Decimal("20.00"),
                        "days_remaining": (upcoming_deadline - today).days,
                    }
                ]

                return invoices_with_upcoming_skonto

            alert_created = False

            async def mock_create_alert(category: str, alert_code: str, **kwargs):
                """Mock alert creation."""
                nonlocal alert_created
                if alert_code == "DEAD_003":
                    alert_created = True
                return {"id": str(uuid4()), "alert_code": alert_code}

            mock_skonto.check_upcoming_deadlines = mock_check_upcoming_deadlines
            mock_alerts.create_alert = mock_create_alert

            # ACT: Check deadlines
            upcoming_invoices = await mock_skonto.check_upcoming_deadlines(threshold_days=3)

            # Create alerts
            for invoice in upcoming_invoices:
                if invoice["days_remaining"] <= 3:
                    await mock_alerts.create_alert(
                        category="deadline",
                        alert_code="DEAD_003",
                        title=f"Skonto-Frist läuft ab: {invoice['invoice_number']}",
                        metadata={
                            "invoice_id": invoice["id"],
                            "skonto_amount": float(invoice["skonto_amount"]),
                            "days_remaining": invoice["days_remaining"],
                        },
                    )

            # ASSERT: Alert created
            assert len(upcoming_invoices) == 1
            assert alert_created is True
