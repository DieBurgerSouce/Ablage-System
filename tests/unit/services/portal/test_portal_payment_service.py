# -*- coding: utf-8 -*-
"""
Unit Tests fuer PortalPaymentService.

Getestet wird der ECHTE Service-Vertrag (app/api/v1/portal/payments.py nutzt ihn):
    submit_payment_confirmation(portal_user, invoice_tracking_id, payment_date,
        payment_amount: str, ...)  -> PortalPaymentConfirmation
    get_payment_confirmations(entity_id, company_id, status?, invoice_tracking_id?,
        limit, offset)             -> tuple[list[dict], int]
    get_payment_confirmation_detail(confirmation_id, entity_id, company_id)
                                   -> Optional[dict]
    cancel_payment_confirmation(confirmation_id, portal_user) -> bool

Die fruehere Testdatei war gegen eine erfundene API geschrieben
(entity_id/company_id/portal_user_id-Kwargs, get_payment_status/verify_payment/
reject_payment) - all das existiert nicht.

Feinpoliert und durchdacht - Portal Payment Tests.
"""

from datetime import datetime, timezone, timedelta, date
from decimal import Decimal
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
        sample_portal_user,
        sample_invoice_tracking,
    ):
        """Sollte Zahlungsbestaetigung erfolgreich erstellen."""
        # Rechnung existiert, gehoert zum Entity, ist offen
        sample_invoice_tracking.status = "open"
        mock_db.execute.return_value = create_mock_result(
            scalar_value=sample_invoice_tracking
        )

        confirmation = await payment_service.submit_payment_confirmation(
            portal_user=sample_portal_user,
            invoice_tracking_id=sample_invoice_tracking.id,
            payment_date=date.today(),
            payment_amount="1190.00",
            payment_reference="RE-2026-00123",
            payment_method="bank_transfer",
            notes="Zahlung erfolgte per Ueberweisung",
        )

        assert confirmation is not None
        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_submit_payment_with_attachments(
        self,
        payment_service: PortalPaymentService,
        mock_db: AsyncMock,
        sample_portal_user,
        sample_invoice_tracking,
    ):
        """Sollte Zahlungsbestaetigung mit Anhaengen erstellen."""
        sample_invoice_tracking.status = "open"
        mock_db.execute.return_value = create_mock_result(
            scalar_value=sample_invoice_tracking
        )
        attachment_ids = [str(uuid4()), str(uuid4())]

        await payment_service.submit_payment_confirmation(
            portal_user=sample_portal_user,
            invoice_tracking_id=sample_invoice_tracking.id,
            payment_date=date.today(),
            payment_amount="500.00",
            payment_reference="Teilzahlung 1",
            attachment_ids=attachment_ids,
        )

        mock_db.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_submit_payment_invoice_not_found(
        self,
        payment_service: PortalPaymentService,
        mock_db: AsyncMock,
        sample_portal_user,
    ):
        """Sollte Fehler werfen wenn Rechnung nicht gefunden / kein Zugriff."""
        mock_db.execute.return_value = create_mock_result(scalar_value=None)

        with pytest.raises(ValueError, match="nicht gefunden oder kein Zugriff"):
            await payment_service.submit_payment_confirmation(
                portal_user=sample_portal_user,
                invoice_tracking_id=uuid4(),
                payment_date=date.today(),
                payment_amount="100.00",
            )

    @pytest.mark.asyncio
    async def test_submit_payment_on_paid_invoice_rejected(
        self,
        payment_service: PortalPaymentService,
        mock_db: AsyncMock,
        sample_portal_user,
        sample_invoice_tracking,
    ):
        """Sollte Zahlung auf bereits bezahlte Rechnung ablehnen."""
        sample_invoice_tracking.status = "paid"
        mock_db.execute.return_value = create_mock_result(
            scalar_value=sample_invoice_tracking
        )

        with pytest.raises(ValueError, match="bereits als bezahlt"):
            await payment_service.submit_payment_confirmation(
                portal_user=sample_portal_user,
                invoice_tracking_id=sample_invoice_tracking.id,
                payment_date=date.today(),
                payment_amount="100.00",
            )


# ========================= Get Payment Confirmations Tests =========================


class TestGetPaymentConfirmations:
    """Tests fuer get_payment_confirmations() Methode (gibt (list[dict], int))."""

    @pytest.mark.asyncio
    async def test_get_confirmations_success(
        self,
        payment_service: PortalPaymentService,
        mock_db: AsyncMock,
        entity_id: UUID,
        company_id: UUID,
        sample_payment_confirmation,
    ):
        """Sollte Liste von Dicts plus Gesamtanzahl zurueckgeben."""
        # 1. execute = count-Query (scalar), 2. execute = Daten (scalars().all())
        mock_db.execute.side_effect = [
            create_mock_result(scalar_value=1),
            create_mock_result(scalars_list=[sample_payment_confirmation]),
        ]

        result, total = await payment_service.get_payment_confirmations(
            entity_id=entity_id,
            company_id=company_id,
        )

        assert isinstance(result, list)
        assert len(result) == 1
        assert total == 1
        assert result[0]["status"] == "pending"
        assert result[0]["payment_amount"] == "1190.00"

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
        mock_db.execute.side_effect = [
            create_mock_result(scalar_value=1),
            create_mock_result(scalars_list=[sample_payment_confirmation]),
        ]

        result, total = await payment_service.get_payment_confirmations(
            entity_id=entity_id,
            company_id=company_id,
            invoice_tracking_id=invoice_id,
        )

        assert len(result) == 1
        assert result[0]["invoice_tracking_id"] == str(invoice_id)

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
        mock_db.execute.side_effect = [
            create_mock_result(scalar_value=1),
            create_mock_result(scalars_list=[sample_payment_confirmation]),
        ]

        result, _ = await payment_service.get_payment_confirmations(
            entity_id=entity_id,
            company_id=company_id,
            status="verified",
        )

        for conf in result:
            assert conf["status"] == "verified"


# ========================= Get Payment Confirmation Detail Tests =========================


class TestGetPaymentConfirmationDetail:
    """Tests fuer get_payment_confirmation_detail() Methode."""

    @pytest.mark.asyncio
    async def test_get_detail_found(
        self,
        payment_service: PortalPaymentService,
        mock_db: AsyncMock,
        entity_id: UUID,
        company_id: UUID,
        sample_payment_confirmation,
        sample_invoice_tracking,
    ):
        """Sollte Detail-Dict zurueckgeben (inkl. Rechnungsdetails)."""
        # 1. execute = Confirmation, 2. execute = zugehoerige Rechnung
        mock_db.execute.side_effect = [
            create_mock_result(scalar_value=sample_payment_confirmation),
            create_mock_result(scalar_value=sample_invoice_tracking),
        ]

        result = await payment_service.get_payment_confirmation_detail(
            confirmation_id=sample_payment_confirmation.id,
            entity_id=entity_id,
            company_id=company_id,
        )

        assert result is not None
        assert result["id"] == str(sample_payment_confirmation.id)
        assert result["invoice_number"] == sample_invoice_tracking.invoice_number
        assert result["status"] == "pending"

    @pytest.mark.asyncio
    async def test_get_detail_not_found(
        self,
        payment_service: PortalPaymentService,
        mock_db: AsyncMock,
        entity_id: UUID,
        company_id: UUID,
    ):
        """Sollte None zurueckgeben wenn nicht gefunden."""
        mock_db.execute.return_value = create_mock_result(scalar_value=None)

        result = await payment_service.get_payment_confirmation_detail(
            confirmation_id=uuid4(),
            entity_id=entity_id,
            company_id=company_id,
        )

        assert result is None


# ========================= Cancel Payment Tests =========================


class TestCancelPaymentConfirmation:
    """Tests fuer cancel_payment_confirmation() Methode."""

    @pytest.mark.asyncio
    async def test_cancel_pending_success(
        self,
        payment_service: PortalPaymentService,
        mock_db: AsyncMock,
        sample_portal_user,
        sample_payment_confirmation,
    ):
        """Sollte ausstehende Zahlungsbestaetigung stornieren (-> True)."""
        sample_payment_confirmation.status = "pending"
        mock_db.execute.return_value = create_mock_result(
            scalar_value=sample_payment_confirmation
        )

        result = await payment_service.cancel_payment_confirmation(
            confirmation_id=sample_payment_confirmation.id,
            portal_user=sample_portal_user,
        )

        assert result is True
        assert sample_payment_confirmation.status == "cancelled"
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_cancel_not_found_returns_false(
        self,
        payment_service: PortalPaymentService,
        mock_db: AsyncMock,
        sample_portal_user,
    ):
        """Sollte False zurueckgeben wenn keine stornierbare Bestaetigung."""
        mock_db.execute.return_value = create_mock_result(scalar_value=None)

        result = await payment_service.cancel_payment_confirmation(
            confirmation_id=uuid4(),
            portal_user=sample_portal_user,
        )

        assert result is False


# ========================= Entity Isolation Tests =========================


class TestEntityIsolation:
    """Tests fuer Entity-Isolation bei Zahlungen.

    Die Isolation ist als WHERE-Filter (entity_id == ..., company_id == ...)
    in jeder Query implementiert; auf Mock-Ebene pruefen wir, dass eine
    fremde Entity ein leeres/None-Ergebnis liefert.
    """

    @pytest.mark.asyncio
    async def test_cannot_see_other_entity_payments(
        self,
        payment_service: PortalPaymentService,
        mock_db: AsyncMock,
        other_entity_id: UUID,
        company_id: UUID,
    ):
        """Entity A sollte keine Zahlungen von Entity B sehen (leere Liste)."""
        mock_db.execute.side_effect = [
            create_mock_result(scalar_value=0),
            create_mock_result(scalars_list=[]),
        ]

        result, total = await payment_service.get_payment_confirmations(
            entity_id=other_entity_id,
            company_id=company_id,
        )

        assert result == []
        assert total == 0

    @pytest.mark.asyncio
    async def test_cannot_access_other_entity_detail(
        self,
        payment_service: PortalPaymentService,
        mock_db: AsyncMock,
        other_entity_id: UUID,
        company_id: UUID,
    ):
        """Sollte keinen Zugriff auf fremde Zahlungsdetails haben (None)."""
        mock_db.execute.return_value = create_mock_result(scalar_value=None)

        result = await payment_service.get_payment_confirmation_detail(
            confirmation_id=uuid4(),
            entity_id=other_entity_id,
            company_id=company_id,
        )

        assert result is None


# ========================= Security / Validation Tests =========================


class TestSecurityPaymentValidation:
    """Tests fuer Zahlungs-Validierung (Sicherheit).

    Betragspruefung wurde im Service ergaenzt (negativ/Null -> ValueError),
    da der API-Layer payment_amount als String ohne gt=0 durchreicht.
    """

    @pytest.mark.asyncio
    async def test_submit_payment_negative_amount_rejected(
        self,
        payment_service: PortalPaymentService,
        mock_db: AsyncMock,
        sample_portal_user,
    ):
        """Sollte negative Zahlungsbetraege ablehnen."""
        with pytest.raises(ValueError, match="positiv"):
            await payment_service.submit_payment_confirmation(
                portal_user=sample_portal_user,
                invoice_tracking_id=uuid4(),
                payment_amount="-100.00",
                payment_date=datetime.now(timezone.utc),
            )
        # Validierung VOR DB-Zugriff -> keine Query
        mock_db.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_submit_payment_zero_amount_rejected(
        self,
        payment_service: PortalPaymentService,
        mock_db: AsyncMock,
        sample_portal_user,
    ):
        """Sollte Zahlungsbetrag von 0 ablehnen."""
        with pytest.raises(ValueError, match="positiv"):
            await payment_service.submit_payment_confirmation(
                portal_user=sample_portal_user,
                invoice_tracking_id=uuid4(),
                payment_amount="0",
                payment_date=datetime.now(timezone.utc),
            )
        mock_db.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_submit_payment_invalid_amount_rejected(
        self,
        payment_service: PortalPaymentService,
        mock_db: AsyncMock,
        sample_portal_user,
    ):
        """Sollte nicht-numerischen Betrag ablehnen."""
        with pytest.raises(ValueError, match="Ungueltiger Zahlungsbetrag"):
            await payment_service.submit_payment_confirmation(
                portal_user=sample_portal_user,
                invoice_tracking_id=uuid4(),
                payment_amount="keine-zahl",
                payment_date=datetime.now(timezone.utc),
            )
        mock_db.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_submit_payment_reference_stored_verbatim(
        self,
        payment_service: PortalPaymentService,
        mock_db: AsyncMock,
        sample_portal_user,
        sample_invoice_tracking,
    ):
        """Zahlungsreferenz wird gespeichert; XSS-Escaping ist Aufgabe der UI.

        Der Service speichert die Referenz unveraendert (kein HTML-Rendering
        im Backend). Wir verifizieren nur, dass kein Crash auftritt und die
        Bestaetigung erstellt wird - die Ausgabe-Kodierung erfolgt im Frontend.
        """
        sample_invoice_tracking.status = "open"
        mock_db.execute.return_value = create_mock_result(
            scalar_value=sample_invoice_tracking
        )

        xss_reference = "<script>alert('x')</script>"
        confirmation = await payment_service.submit_payment_confirmation(
            portal_user=sample_portal_user,
            invoice_tracking_id=sample_invoice_tracking.id,
            payment_amount="100.00",
            payment_date=datetime.now(timezone.utc),
            payment_reference=xss_reference,
        )

        assert confirmation is not None
        mock_db.add.assert_called_once()
