# -*- coding: utf-8 -*-
"""
Tests fuer InkassoService.

Testet:
- Inkasso-Uebergabe (Mock-Modus)
- Fallstatus-Abfrage
- Webhook-Verarbeitung und Signaturpruefung
- Inkasso-Stornierung
- Provider-Auswahl
- Sicherheit: Webhook-Signatur-Manipulation
"""

import hashlib
import hmac
import json
import pytest
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, Mock, patch, PropertyMock
from uuid import UUID, uuid4

from app.services.inkasso_service import (
    InkassoService,
    InkassoProvider,
    CollectionStatus,
    CollectionTransferResult,
    CollectionCaseUpdate,
)


@pytest.fixture
def mock_db() -> AsyncMock:
    """Erstellt eine Mock-Datenbank-Session."""
    return AsyncMock()


@pytest.fixture
def mock_settings():
    """Mock fuer settings ohne echte API-Keys."""
    mock = MagicMock()
    mock.INKASSO_PROVIDER = "mock"
    mock.INKASSO_API_KEY = None
    mock.INKASSO_WEBHOOK_SECRET = "test-webhook-secret-for-tests"
    return mock


@pytest.fixture
def service(mock_db: AsyncMock, mock_settings) -> InkassoService:
    """Erstellt eine InkassoService-Instanz im Mock-Modus."""
    with patch("app.services.inkasso_service.settings", mock_settings):
        svc = InkassoService(mock_db)
    return svc


def _make_mock_invoice(
    invoice_id: UUID = None,
    invoice_number: str = "RE-TEST-001",
    amount: float = 500.00,
) -> Mock:
    """Erzeugt ein Mock-InvoiceTracking."""
    invoice = Mock()
    invoice.id = invoice_id or uuid4()
    invoice.invoice_number = invoice_number
    invoice.amount = amount
    invoice.currency = "EUR"
    invoice.invoice_date = datetime(2026, 1, 1, tzinfo=timezone.utc)
    invoice.due_date = datetime(2026, 1, 30, tzinfo=timezone.utc)
    return invoice


def _make_mock_entity(entity_id: UUID = None) -> Mock:
    """Erzeugt ein Mock-BusinessEntity."""
    entity = Mock()
    entity.id = entity_id or uuid4()
    entity.name = "Test Schuldner GmbH"
    entity.street = "Teststrasse 1"
    entity.postal_code = "00000"
    entity.city = "Teststadt"
    entity.country = "DE"
    entity.email = "test@example.invalid"
    entity.phone = "+49-000-0000000"
    entity.vat_id = "DE000000000"
    return entity


class TestTransferToCollection:
    """Tests fuer transfer_to_collection()."""

    @pytest.mark.asyncio
    async def test_erfolgreiche_mock_uebergabe(
        self, service: InkassoService, mock_db: AsyncMock
    ):
        """Inkasso-Uebergabe im Mock-Modus ist erfolgreich."""
        invoice = _make_mock_invoice()
        entity = _make_mock_entity()
        mock_db.get = AsyncMock(side_effect=[invoice, entity])

        result = await service.transfer_to_collection(
            invoice_id=invoice.id,
            entity_id=entity.id,
            company_id=uuid4(),
            amount=Decimal("500.00"),
        )

        assert result.success is True
        assert result.collection_reference.startswith("INK-")
        assert result.provider == "mock"

    @pytest.mark.asyncio
    async def test_fehlende_rechnung_wirft_fehler(
        self, service: InkassoService, mock_db: AsyncMock
    ):
        """Fehlende Rechnung wirft ValueError."""
        mock_db.get = AsyncMock(side_effect=[None, _make_mock_entity()])

        with pytest.raises(ValueError, match="Rechnung.*nicht gefunden"):
            await service.transfer_to_collection(
                invoice_id=uuid4(),
                entity_id=uuid4(),
                company_id=uuid4(),
                amount=Decimal("500.00"),
            )

    @pytest.mark.asyncio
    async def test_fehlender_geschaeftspartner_wirft_fehler(
        self, service: InkassoService, mock_db: AsyncMock
    ):
        """Fehlender Geschaeftspartner wirft ValueError."""
        mock_db.get = AsyncMock(side_effect=[_make_mock_invoice(), None])

        with pytest.raises(ValueError, match="nicht gefunden"):
            await service.transfer_to_collection(
                invoice_id=uuid4(),
                entity_id=uuid4(),
                company_id=uuid4(),
                amount=Decimal("500.00"),
            )

    @pytest.mark.asyncio
    async def test_uebergabe_aktualisiert_entity_status(
        self, service: InkassoService, mock_db: AsyncMock
    ):
        """Erfolgreiche Uebergabe aktualisiert den Entity-Status."""
        invoice = _make_mock_invoice()
        entity = _make_mock_entity()
        mock_db.get = AsyncMock(side_effect=[invoice, entity])

        await service.transfer_to_collection(
            invoice_id=invoice.id,
            entity_id=entity.id,
            company_id=uuid4(),
            amount=Decimal("500.00"),
        )

        mock_db.execute.assert_called()
        mock_db.commit.assert_called()


class TestGetCaseStatus:
    """Tests fuer get_case_status()."""

    @pytest.mark.asyncio
    async def test_mock_status_abfrage(self, service: InkassoService):
        """Status-Abfrage im Mock-Modus gibt IN_PROGRESS zurueck."""
        result = await service.get_case_status("INK-20260101-ABCD1234")

        assert result.status == CollectionStatus.IN_PROGRESS
        assert result.collection_reference == "INK-20260101-ABCD1234"
        assert result.notes is not None


class TestHandleWebhook:
    """Tests fuer handle_webhook() - Sicherheitskritisch."""

    @pytest.mark.asyncio
    async def test_gueltiger_webhook_wird_verarbeitet(
        self, service: InkassoService
    ):
        """Gueltiger Webhook-Payload wird korrekt verarbeitet."""
        payload = {
            "reference": "INK-20260101-ABCD1234",
            "status": "in_progress",
            "collected_amount": 100.00,
        }

        # Korrekte Signatur generieren
        payload_bytes = json.dumps(payload, sort_keys=True).encode("utf-8")
        signature = hmac.new(
            b"test-webhook-secret-for-tests",
            payload_bytes,
            hashlib.sha256,
        ).hexdigest()

        result = await service.handle_webhook(
            provider=InkassoProvider.EOS,
            payload=payload,
            signature=signature,
        )

        assert result is True

    @pytest.mark.asyncio
    async def test_ungueltige_signatur_wird_abgelehnt(
        self, service: InkassoService
    ):
        """Webhook mit ungueltiger Signatur wird abgelehnt."""
        payload = {"reference": "INK-TEST", "status": "collected"}

        result = await service.handle_webhook(
            provider=InkassoProvider.EOS,
            payload=payload,
            signature="invalid-signature",
        )

        assert result is False

    @pytest.mark.asyncio
    async def test_fehlende_pflichtfelder_wird_abgelehnt(
        self, service: InkassoService
    ):
        """Webhook ohne Pflichtfelder wird abgelehnt."""
        payload = {"irrelevant_field": "test"}

        result = await service.handle_webhook(
            provider=InkassoProvider.EOS,
            payload=payload,
            signature=None,
        )

        assert result is False

    @pytest.mark.asyncio
    async def test_unbekannter_status_wird_als_in_progress_behandelt(
        self, service: InkassoService
    ):
        """Unbekannter Status im Webhook wird als IN_PROGRESS behandelt."""
        payload = {
            "reference": "INK-TEST",
            "status": "unbekannter_status_12345",
        }

        # Keine Signatur-Pruefung (kein Secret match)
        service.webhook_secret = None

        result = await service.handle_webhook(
            provider=InkassoProvider.MOCK,
            payload=payload,
            signature=None,
        )

        assert result is True


class TestCancelCollection:
    """Tests fuer cancel_collection()."""

    @pytest.mark.asyncio
    async def test_mock_stornierung(self, service: InkassoService):
        """Stornierung im Mock-Modus ist erfolgreich."""
        result = await service.cancel_collection(
            collection_reference="INK-20260101-ABCD1234",
            reason="Zahlung erhalten",
        )

        assert result is True


class TestCollectionReference:
    """Tests fuer _generate_collection_reference()."""

    def test_referenz_format(self, service: InkassoService):
        """Collection-Reference hat das korrekte Format INK-YYYYMMDD-XXXXXXXX."""
        ref = service._generate_collection_reference(uuid4())

        assert ref.startswith("INK-")
        parts = ref.split("-")
        assert len(parts) == 3
        assert len(parts[1]) == 8  # YYYYMMDD

    def test_verschiedene_ids_verschiedene_referenzen(self, service: InkassoService):
        """Verschiedene Invoice-IDs erzeugen verschiedene Referenzen."""
        ref1 = service._generate_collection_reference(uuid4())
        ref2 = service._generate_collection_reference(uuid4())

        # Mindestens der ID-Teil sollte unterschiedlich sein
        assert ref1.split("-")[2] != ref2.split("-")[2]


class TestProviderKonfiguration:
    """Tests fuer Provider-Konfigurationen."""

    def test_alle_provider_haben_konfiguration(self):
        """Alle Provider (ausser MOCK) haben eine Konfiguration."""
        for provider in InkassoProvider:
            if provider == InkassoProvider.MOCK:
                continue
            assert provider in InkassoService.PROVIDER_CONFIGS

    def test_mindestbetrag_ist_positiv(self):
        """Mindestforderungsbetrag ist fuer alle Provider positiv."""
        for provider, config in InkassoService.PROVIDER_CONFIGS.items():
            assert config["min_claim_amount"] > 0
