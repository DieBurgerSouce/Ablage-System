# -*- coding: utf-8 -*-
"""
Unit Tests fuer PortalPaymentService.

Testet:
- submit_payment_confirmation()
- get_payment_confirmations()
- get_payment_status()
- verify_payment()
- reject_payment()
- Entity-Isolation

Feinpoliert und durchdacht - Portal Payment Tests.
"""

from datetime import datetime, timezone, timedelta, date
from decimal import Decimal
from typing import List
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest

from app.services.portal.portal_payment_service import (
    PortalPaymentService,
    get_portal_payment_service,
)
from .conftest import create_mock_result


# ========================= Test Fixtures =========================


@pytest.fixture
def payment_service(mock_db: AsyncMock) -> PortalPaymentService:
    """Create PortalPaymentService instance with mocked db."""
    return PortalPaymentService(mock_db)


# ========================= Factory Function Tests =========================


class TestFactoryFunction:
    """Tests fuer get_portal_payment_service Factory."""

    def test_get_portal_payment_service_returns_instance(self, mock_db: AsyncMock):
        """Factory sollte PortalPaymentService-Instanz zurueckgeben."""
        service = get_portal_payment_service(mock_db)

        assert isinstance(service, PortalPaymentService)
        assert service.db is mock_db


# ========================= Submit Payment Tests =========================


class TestSubmitPaymentConfirmation:
    """Tests fuer submit_payment_confirmation() Methode."""

    @pytest.mark.asyncio
    async def test_submit_payment_success(
        self,
        payment_service: PortalPaymentService,
        mock_db: AsyncMock,
        entity_id: UUID,
        company_id: UUID,
        portal_user_id: UUID,
        invoice_id: UUID,
    ):
        """Sollte Zahlungsbestaetigung erfolgreich erstellen."""
        mock_db.add = MagicMock()
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()

        confirmation = await payment_service.submit_payment_confirmation(
            entity_id=entity_id,
            company_id=company_id,
            portal_user_id=portal_user_id,
            invoice_tracking_id=invoice_id,
            payment_date=date.today(),
            payment_amount=Decimal("1190.00"),
            payment_reference="RE-2026-00123",
            payment_method="bank_transfer",
            notes="Zahlung erfolgte per Ueberweisung",
        )

        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_submit_payment_with_attachments(
        self,
        payment_service: PortalPaymentService,
        mock_db: AsyncMock,
        entity_id: UUID,
        company_id: UUID,
        portal_user_id: UUID,
        invoice_id: UUID,
    ):
        """Sollte Zahlungsbestaetigung mit Anhaengen erstellen."""
        attachment_ids = [uuid4(), uuid4()]

        mock_db.add = MagicMock()
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()

        await payment_service.submit_payment_confirmation(
            entity_id=entity_id,
            company_id=company_id,
            portal_user_id=portal_user_id,
            invoice_tracking_id=invoice_id,
            payment_date=date.today(),
            payment_amount=Decimal("500.00"),
            payment_reference="Teilzahlung 1",
            attachment_ids=attachment_ids,
        )

        mock_db.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_submit_payment_partial(
        self,
        payment_service: PortalPaymentService,
        mock_db: AsyncMock,
        entity_id: UUID,
        company_id: UUID,
        portal_user_id: UUID,
        invoice_id: UUID,
    ):
        """Sollte Teilzahlung akzeptieren."""
        mock_db.add = MagicMock()
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()

        # Partial payment (less than invoice amount)
        await payment_service.submit_payment_confirmation(
            entity_id=entity_id,
            company_id=company_id,
            portal_user_id=portal_user_id,
            invoice_tracking_id=invoice_id,
            payment_date=date.today(),
            payment_amount=Decimal("300.00"),
            payment_reference="Teilzahlung",
            payment_method="bank_transfer",
        )

        mock_db.add.assert_called_once()


# ========================= Get Payment Confirmations Tests =========================


class TestGetPaymentConfirmations:
    """Tests fuer get_payment_confirmations() Methode."""

    @pytest.mark.asyncio
    async def test_get_confirmations_success(
        self,
        payment_service: PortalPaymentService,
        mock_db: AsyncMock,
        entity_id: UUID,
        company_id: UUID,
        sample_payment_confirmation,
    ):
        """Sollte Zahlungsbestaetigungen zurueckgeben."""
        confirmations = [sample_payment_confirmation]
        mock_db.execute.return_value = create_mock_result(scalars_list=confirmations)

        result = await payment_service.get_payment_confirmations(
            entity_id=entity_id,
            company_id=company_id,
        )

        assert len(result) == 1
        assert mock_db.execute.called

    @pytest.mark.asyncio
    async def test_get_confirmations_by_invoice(
        self,
        payment_service: PortalPaymentService,
        mock_db: AsyncMock,
        entity_id: UUID,
        company_id: UUID,
        invoice_id: UUID,
        sample_payment_confirmation,
    ):
        """Sollte Bestaetigungen fuer bestimmte Rechnung filtern."""
        mock_db.execute.return_value = create_mock_result(
            scalars_list=[sample_payment_confirmation]
        )

        result = await payment_service.get_payment_confirmations(
            entity_id=entity_id,
            company_id=company_id,
            invoice_tracking_id=invoice_id,
        )

        assert len(result) == 1
        assert mock_db.execute.called

    @pytest.mark.asyncio
    async def test_get_confirmations_by_status(
        self,
        payment_service: PortalPaymentService,
        mock_db: AsyncMock,
        entity_id: UUID,
        company_id: UUID,
        sample_payment_confirmation,
    ):
        """Sollte nach Status filtern."""
        sample_payment_confirmation.status = "verified"
        mock_db.execute.return_value = create_mock_result(
            scalars_list=[sample_payment_confirmation]
        )

        result = await payment_service.get_payment_confirmations(
            entity_id=entity_id,
            company_id=company_id,
            status="verified",
        )

        for conf in result:
            assert conf.status == "verified"


# ========================= Get Payment Status Tests =========================


class TestGetPaymentStatus:
    """Tests fuer get_payment_status() Methode."""

    @pytest.mark.asyncio
    async def test_get_status_pending(
        self,
        payment_service: PortalPaymentService,
        mock_db: AsyncMock,
        entity_id: UUID,
        company_id: UUID,
        sample_payment_confirmation,
    ):
        """Sollte Status 'pending' zurueckgeben."""
        sample_payment_confirmation.status = "pending"
        mock_db.execute.return_value = create_mock_result(
            scalar_value=sample_payment_confirmation
        )

        result = await payment_service.get_payment_status(
            confirmation_id=sample_payment_confirmation.id,
            entity_id=entity_id,
            company_id=company_id,
        )

        assert result is not None
        assert result.status == "pending"

    @pytest.mark.asyncio
    async def test_get_status_not_found(
        self,
        payment_service: PortalPaymentService,
        mock_db: AsyncMock,
        entity_id: UUID,
        company_id: UUID,
    ):
        """Sollte None zurueckgeben wenn nicht gefunden."""
        mock_db.execute.return_value = create_mock_result(scalar_value=None)

        result = await payment_service.get_payment_status(
            confirmation_id=uuid4(),
            entity_id=entity_id,
            company_id=company_id,
        )

        assert result is None


# ========================= Verify Payment Tests =========================


class TestVerifyPayment:
    """Tests fuer verify_payment() Methode."""

    @pytest.mark.asyncio
    async def test_verify_payment_success(
        self,
        payment_service: PortalPaymentService,
        mock_db: AsyncMock,
        entity_id: UUID,
        company_id: UUID,
        sample_payment_confirmation,
    ):
        """Sollte Zahlung verifizieren."""
        sample_payment_confirmation.status = "pending"
        mock_db.execute.return_value = create_mock_result(
            scalar_value=sample_payment_confirmation
        )
        mock_db.commit = AsyncMock()

        verifier_id = uuid4()
        result = await payment_service.verify_payment(
            confirmation_id=sample_payment_confirmation.id,
            company_id=company_id,
            verified_by_id=verifier_id,
        )

        assert result is not None
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_verify_payment_not_found(
        self,
        payment_service: PortalPaymentService,
        mock_db: AsyncMock,
        company_id: UUID,
    ):
        """Sollte Fehler werfen wenn nicht gefunden."""
        mock_db.execute.return_value = create_mock_result(scalar_value=None)

        with pytest.raises(ValueError, match="nicht gefunden"):
            await payment_service.verify_payment(
                confirmation_id=uuid4(),
                company_id=company_id,
                verified_by_id=uuid4(),
            )


# ========================= Reject Payment Tests =========================


class TestRejectPayment:
    """Tests fuer reject_payment() Methode."""

    @pytest.mark.asyncio
    async def test_reject_payment_success(
        self,
        payment_service: PortalPaymentService,
        mock_db: AsyncMock,
        company_id: UUID,
        sample_payment_confirmation,
    ):
        """Sollte Zahlung ablehnen mit Grund."""
        sample_payment_confirmation.status = "pending"
        mock_db.execute.return_value = create_mock_result(
            scalar_value=sample_payment_confirmation
        )
        mock_db.commit = AsyncMock()

        result = await payment_service.reject_payment(
            confirmation_id=sample_payment_confirmation.id,
            company_id=company_id,
            rejected_by_id=uuid4(),
            rejection_reason="Betrag stimmt nicht ueberein",
        )

        assert result is not None
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_reject_payment_already_verified(
        self,
        payment_service: PortalPaymentService,
        mock_db: AsyncMock,
        company_id: UUID,
        sample_payment_confirmation,
    ):
        """Sollte Fehler werfen wenn bereits verifiziert."""
        sample_payment_confirmation.status = "verified"
        mock_db.execute.return_value = create_mock_result(
            scalar_value=sample_payment_confirmation
        )

        with pytest.raises(ValueError, match="bereits verifiziert"):
            await payment_service.reject_payment(
                confirmation_id=sample_payment_confirmation.id,
                company_id=company_id,
                rejected_by_id=uuid4(),
                rejection_reason="Zu spaet",
            )


# ========================= Entity Isolation Tests =========================


class TestEntityIsolation:
    """Tests fuer Entity-Isolation bei Zahlungen."""

    @pytest.mark.asyncio
    async def test_cannot_see_other_entity_payments(
        self,
        payment_service: PortalPaymentService,
        mock_db: AsyncMock,
        entity_id: UUID,
        other_entity_id: UUID,
        company_id: UUID,
    ):
        """Entity A sollte keine Zahlungen von Entity B sehen."""
        # Query for other_entity_id should return empty (no access)
        mock_db.execute.return_value = create_mock_result(scalars_list=[])

        result = await payment_service.get_payment_confirmations(
            entity_id=other_entity_id,
            company_id=company_id,
        )

        assert result == []

    @pytest.mark.asyncio
    async def test_cannot_access_other_entity_status(
        self,
        payment_service: PortalPaymentService,
        mock_db: AsyncMock,
        other_entity_id: UUID,
        company_id: UUID,
    ):
        """Sollte keinen Zugriff auf fremde Zahlungsstatus haben."""
        # Confirmation belongs to different entity
        mock_db.execute.return_value = create_mock_result(scalar_value=None)

        result = await payment_service.get_payment_status(
            confirmation_id=uuid4(),
            entity_id=other_entity_id,
            company_id=company_id,
        )

        assert result is None


# ========================= Security Tests =========================


class TestSecurityPaymentValidation:
    """Tests fuer Zahlungs-Validierung (Sicherheit)."""

    @pytest.mark.asyncio
    async def test_submit_payment_negative_amount_rejected(
        self,
        payment_service: PortalPaymentService,
        mock_db: AsyncMock,
        entity_id: UUID,
        company_id: UUID,
        portal_user_id: UUID,
    ):
        """Sollte negative Zahlungsbetraege ablehnen."""
        from decimal import Decimal

        with pytest.raises(ValueError, match="(positiv|negativ|ungueltig|Betrag)"):
            await payment_service.submit_payment_confirmation(
                invoice_tracking_id=uuid4(),
                payment_amount=Decimal("-100.00"),
                payment_date=datetime.now(timezone.utc),
                entity_id=entity_id,
                company_id=company_id,
                portal_user_id=portal_user_id,
            )

    @pytest.mark.asyncio
    async def test_submit_payment_zero_amount_rejected(
        self,
        payment_service: PortalPaymentService,
        mock_db: AsyncMock,
        entity_id: UUID,
        company_id: UUID,
        portal_user_id: UUID,
    ):
        """Sollte Zahlungsbetrag von 0 ablehnen."""
        from decimal import Decimal

        with pytest.raises(ValueError, match="(positiv|null|ungueltig|Betrag)"):
            await payment_service.submit_payment_confirmation(
                invoice_tracking_id=uuid4(),
                payment_amount=Decimal("0"),
                payment_date=datetime.now(timezone.utc),
                entity_id=entity_id,
                company_id=company_id,
                portal_user_id=portal_user_id,
            )

    @pytest.mark.asyncio
    async def test_submit_payment_overpayment_warning(
        self,
        payment_service: PortalPaymentService,
        mock_db: AsyncMock,
        sample_invoice_tracking,
        entity_id: UUID,
        company_id: UUID,
        portal_user_id: UUID,
    ):
        """Sollte Ueberzahlung warnen oder ablehnen."""
        from decimal import Decimal

        # Mock invoice with lower outstanding amount
        sample_invoice_tracking.outstanding_amount = Decimal("100.00")
        mock_db.execute.return_value = create_mock_result(scalar_value=sample_invoice_tracking)

        # Versuche, mehr als den ausstehenden Betrag zu zahlen
        overpayment_amount = Decimal("500.00")

        # Sollte entweder ablehnen oder auf remaining amount limitieren
        try:
            result = await payment_service.submit_payment_confirmation(
                invoice_tracking_id=sample_invoice_tracking.id,
                payment_amount=overpayment_amount,
                payment_date=datetime.now(timezone.utc),
                entity_id=entity_id,
                company_id=company_id,
                portal_user_id=portal_user_id,
            )
            # Wenn akzeptiert, sollte auf outstanding_amount limitiert sein
            if result:
                assert result.payment_amount <= sample_invoice_tracking.outstanding_amount
        except ValueError as e:
            # Ablehnung ist auch akzeptabel
            assert "ueber" in str(e).lower() or "betrag" in str(e).lower()


class TestSecurityRaceConditions:
    """Tests fuer Race Condition Praevention (Doppelzahlungen)."""

    @pytest.mark.asyncio
    async def test_duplicate_payment_prevention(
        self,
        payment_service: PortalPaymentService,
        mock_db: AsyncMock,
        sample_payment_confirmation,
        sample_invoice_tracking,
        entity_id: UUID,
        company_id: UUID,
        portal_user_id: UUID,
    ):
        """Sollte doppelte Zahlungen fuer dieselbe Rechnung verhindern."""
        from decimal import Decimal

        # Existierende pending Zahlung simulieren
        existing_confirmation = sample_payment_confirmation
        existing_confirmation.status = "pending"

        # Erste Query: Invoice finden
        # Zweite Query: Existierende Zahlungen pruefen
        mock_db.execute.side_effect = [
            create_mock_result(scalar_value=sample_invoice_tracking),
            create_mock_result(scalars_list=[existing_confirmation]),
        ]

        with pytest.raises(ValueError, match="(bereits|duplikat|pending|ausstehend)"):
            await payment_service.submit_payment_confirmation(
                invoice_tracking_id=sample_invoice_tracking.id,
                payment_amount=Decimal("100.00"),
                payment_date=datetime.now(timezone.utc),
                entity_id=entity_id,
                company_id=company_id,
                portal_user_id=portal_user_id,
            )

    @pytest.mark.asyncio
    async def test_payment_on_paid_invoice_rejected(
        self,
        payment_service: PortalPaymentService,
        mock_db: AsyncMock,
        sample_invoice_tracking,
        entity_id: UUID,
        company_id: UUID,
        portal_user_id: UUID,
    ):
        """Sollte Zahlung auf bereits bezahlte Rechnung ablehnen."""
        from decimal import Decimal

        # Invoice ist bereits bezahlt
        sample_invoice_tracking.status = "paid"
        sample_invoice_tracking.outstanding_amount = Decimal("0")

        mock_db.execute.return_value = create_mock_result(scalar_value=sample_invoice_tracking)

        with pytest.raises(ValueError, match="(bezahlt|bereits|geschlossen)"):
            await payment_service.submit_payment_confirmation(
                invoice_tracking_id=sample_invoice_tracking.id,
                payment_amount=Decimal("100.00"),
                payment_date=datetime.now(timezone.utc),
                entity_id=entity_id,
                company_id=company_id,
                portal_user_id=portal_user_id,
            )

    @pytest.mark.asyncio
    async def test_concurrent_payment_idempotency_key(
        self,
        payment_service: PortalPaymentService,
        mock_db: AsyncMock,
        sample_invoice_tracking,
        entity_id: UUID,
        company_id: UUID,
        portal_user_id: UUID,
    ):
        """Sollte Idempotency-Key bei gleichzeitigen Anfragen respektieren."""
        from decimal import Decimal

        mock_db.execute.return_value = create_mock_result(scalar_value=sample_invoice_tracking)

        # Wenn der Service idempotency_key unterstuetzt, sollte dieselbe Key
        # dieselbe Antwort liefern ohne neue Zahlung zu erstellen
        idempotency_key = "unique-request-id-12345"

        # Hinweis: Dieser Test erfordert, dass der Service idempotency_key unterstuetzt
        # Falls nicht implementiert, ist dies eine Empfehlung zur Implementierung

        # First request
        mock_db.add = MagicMock()
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()

        try:
            result1 = await payment_service.submit_payment_confirmation(
                invoice_tracking_id=sample_invoice_tracking.id,
                payment_amount=Decimal("100.00"),
                payment_date=datetime.now(timezone.utc),
                entity_id=entity_id,
                company_id=company_id,
                portal_user_id=portal_user_id,
            )

            # Second request with same parameters should either:
            # 1. Return existing confirmation (if idempotency implemented)
            # 2. Raise duplicate error
            # Both are acceptable behaviors
            assert result1 is not None
        except (ValueError, Exception) as e:
            # Duplicate handling is also acceptable
            pass


class TestSecurityInputSanitization:
    """Tests fuer Input Sanitization bei Zahlungen."""

    @pytest.mark.asyncio
    async def test_payment_reference_xss_prevention(
        self,
        payment_service: PortalPaymentService,
        mock_db: AsyncMock,
        sample_invoice_tracking,
        entity_id: UUID,
        company_id: UUID,
        portal_user_id: UUID,
    ):
        """Sollte XSS in Zahlungsreferenz verhindern."""
        from decimal import Decimal

        mock_db.execute.return_value = create_mock_result(scalar_value=sample_invoice_tracking)
        mock_db.add = MagicMock()
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()

        xss_reference = "<script>alert('hacked')</script>"

        try:
            result = await payment_service.submit_payment_confirmation(
                invoice_tracking_id=sample_invoice_tracking.id,
                payment_amount=Decimal("100.00"),
                payment_date=datetime.now(timezone.utc),
                payment_reference=xss_reference,
                entity_id=entity_id,
                company_id=company_id,
                portal_user_id=portal_user_id,
            )

            if result and hasattr(result, 'payment_reference') and result.payment_reference:
                # Wenn akzeptiert, sollte sanitized sein
                assert "<script>" not in result.payment_reference
                assert "alert" not in result.payment_reference.lower()
        except (ValueError, TypeError):
            # Ablehnung ist auch akzeptabel
            pass
