# -*- coding: utf-8 -*-
"""Tests fuer SmartReconciliationService.

Testet intelligenten Zahlungsabgleich:
- IBAN-Matching
- Referenznummern im Verwendungszweck
- Betrags-Matching (exakt, Skonto, Teilzahlung)
- Namens-Matching (fuzzy)
- Batch-Reconciliation
- Namens-Normalisierung
"""

import pytest
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Optional
from uuid import UUID, uuid4
from unittest.mock import AsyncMock, Mock, MagicMock, patch

from app.services.banking.smart_reconciliation_service import (
    SmartReconciliationService,
    ReconciliationResult,
    ReconciliationMatch,
    ReconciliationStrategy,
    ReconciliationAction,
)


class TestSmartReconciliation:
    """Tests fuer SmartReconciliationService Kernlogik."""

    @pytest.fixture
    def mock_db(self) -> AsyncMock:
        """Mock fuer Datenbank-Session."""
        return AsyncMock()

    @pytest.fixture
    def service(self, mock_db: AsyncMock) -> SmartReconciliationService:
        """Erstellt Service-Instanz."""
        return SmartReconciliationService(mock_db)

    @pytest.mark.asyncio
    async def test_transaction_not_found(self, service: SmartReconciliationService) -> None:
        """Test: Nicht gefundene Transaktion liefert no_match."""
        mock_result = Mock()
        mock_result.scalars.return_value.first.return_value = None
        service.db.execute = AsyncMock(return_value=mock_result)

        result = await service.reconcile(uuid4(), uuid4())

        assert result.action == ReconciliationAction.NO_MATCH
        assert "nicht gefunden" in result.explanation

    @pytest.mark.asyncio
    async def test_negative_amount_skipped(self, service: SmartReconciliationService) -> None:
        """Test: Ausgehende Zahlungen werden nicht abgeglichen."""
        mock_tx = Mock()
        mock_tx.amount = Decimal("-500.00")

        mock_result = Mock()
        mock_result.scalars.return_value.first.return_value = mock_tx
        service.db.execute = AsyncMock(return_value=mock_result)

        result = await service.reconcile(uuid4(), uuid4())

        assert "Zahlungseingänge" in result.explanation or "Zahlungseingaenge" in result.explanation

    @pytest.mark.asyncio
    async def test_no_open_invoices(self, service: SmartReconciliationService) -> None:
        """Test: Keine offenen Rechnungen liefert no_match."""
        mock_tx = Mock()
        mock_tx.amount = Decimal("100.00")

        with patch.object(service, "_get_transaction", return_value=mock_tx):
            with patch.object(service, "_get_open_invoices", return_value=[]):
                result = await service.reconcile(uuid4(), uuid4())

        assert result.action == ReconciliationAction.NO_MATCH
        assert "offenen Rechnungen" in result.explanation

    @pytest.mark.asyncio
    async def test_auto_match_high_confidence(self, service: SmartReconciliationService) -> None:
        """Test: Hohe Konfidenz fuehrt zu automatischem Match."""
        tx_id = uuid4()
        company_id = uuid4()

        mock_tx = Mock()
        mock_tx.amount = Decimal("100.00")
        mock_tx.counterparty_iban = "DE89370400440532013000"
        mock_tx.reference_text = "RE-12345"
        mock_tx.counterparty_name = "Test GmbH"

        mock_invoice = Mock()
        mock_invoice.id = uuid4()
        mock_invoice.invoice_number = "RE-12345"
        mock_invoice.amount = Decimal("100.00")
        mock_invoice.outstanding_amount = Decimal("100.00")
        mock_invoice.entity_id = None
        mock_invoice.skonto_percentage = None
        mock_invoice.skonto_deadline = None

        high_match = ReconciliationMatch(
            invoice_id=mock_invoice.id,
            invoice_number="RE-12345",
            confidence=0.95,
            strategy=ReconciliationStrategy.REFERENCE_IN_TEXT,
            explanation="Rechnungsnummer im Verwendungszweck",
        )

        with patch.object(service, "_get_transaction", return_value=mock_tx):
            with patch.object(service, "_get_open_invoices", return_value=[mock_invoice]):
                with patch.object(service, "_evaluate_match", return_value=high_match):
                    result = await service.reconcile(tx_id, company_id)

        assert result.auto_matched is True
        assert result.action == ReconciliationAction.AUTO_MATCH
        assert result.best_match is not None
        assert result.best_match.confidence >= 0.85

    @pytest.mark.asyncio
    async def test_suggest_medium_confidence(self, service: SmartReconciliationService) -> None:
        """Test: Mittlere Konfidenz fuehrt zu Vorschlag statt Auto-Match."""
        tx_id = uuid4()
        company_id = uuid4()

        mock_tx = Mock()
        mock_tx.amount = Decimal("100.00")
        mock_tx.counterparty_iban = None
        mock_tx.reference_text = ""
        mock_tx.counterparty_name = "Test GmbH"

        mock_invoice = Mock()
        mock_invoice.id = uuid4()
        mock_invoice.invoice_number = "RE-12345"

        # Patch _evaluate_match to return a low-confidence match
        low_match = ReconciliationMatch(
            invoice_id=mock_invoice.id,
            confidence=0.75,
            strategy=ReconciliationStrategy.NAME_FUZZY,
            explanation="Name-Match",
        )

        with patch.object(service, "_get_transaction", return_value=mock_tx):
            with patch.object(service, "_get_open_invoices", return_value=[mock_invoice]):
                with patch.object(service, "_evaluate_match", return_value=low_match):
                    result = await service.reconcile(tx_id, company_id)

        assert result.auto_matched is False
        assert result.action == ReconciliationAction.SUGGEST

    @pytest.mark.asyncio
    async def test_exception_returns_manual_review(self, service: SmartReconciliationService) -> None:
        """Test: Exception fuehrt zu Manual Review."""
        service.db.execute = AsyncMock(side_effect=RuntimeError("DB-Fehler"))

        result = await service.reconcile(uuid4(), uuid4())

        assert result.action == ReconciliationAction.MANUAL_REVIEW
        assert "Fehler" in result.explanation


class TestReferenceMatching:
    """Tests fuer Referenznummern-Matching."""

    @pytest.fixture
    def service(self) -> SmartReconciliationService:
        """Erstellt Service-Instanz."""
        return SmartReconciliationService(AsyncMock())

    def test_exact_reference_match(self, service: SmartReconciliationService) -> None:
        """Test: Exakte Rechnungsnummer im Verwendungszweck gibt 95%."""
        confidence = service._check_reference_match(
            "Zahlung fuer RE-12345 Danke",
            "RE-12345"
        )
        assert confidence == 0.95

    def test_partial_reference_match(self, service: SmartReconciliationService) -> None:
        """Test: Teilweise Uebereinstimmung gibt 80%."""
        confidence = service._check_reference_match(
            "ZAHLUNG 12345 KONTO",
            "RE-12345-2026"
        )
        assert confidence == 0.80

    def test_no_reference_match(self, service: SmartReconciliationService) -> None:
        """Test: Keine Uebereinstimmung gibt 0%."""
        confidence = service._check_reference_match(
            "Allgemeine Zahlung",
            "RE-99999"
        )
        assert confidence == 0.0

    def test_empty_purpose(self, service: SmartReconciliationService) -> None:
        """Test: Leerer Verwendungszweck gibt 0%."""
        confidence = service._check_reference_match("", "RE-12345")
        assert confidence == 0.0

    def test_empty_invoice_number(self, service: SmartReconciliationService) -> None:
        """Test: Leere Rechnungsnummer gibt 0%."""
        confidence = service._check_reference_match("Zahlung RE-12345", "")
        assert confidence == 0.0


class TestAmountMatching:
    """Tests fuer Betrags-Matching."""

    @pytest.fixture
    def service(self) -> SmartReconciliationService:
        """Erstellt Service-Instanz."""
        return SmartReconciliationService(AsyncMock())

    def test_exact_amount_match(self, service: SmartReconciliationService) -> None:
        """Test: Exakter Betrag gibt 90%."""
        mock_tx = Mock()
        mock_tx.amount = Decimal("100.00")

        mock_invoice = Mock()
        mock_invoice.outstanding_amount = Decimal("100.00")
        mock_invoice.amount = Decimal("100.00")
        mock_invoice.skonto_percentage = None
        mock_invoice.skonto_deadline = None

        result = service._check_amount_match(mock_tx, mock_invoice)
        assert result is not None
        assert result[0] == ReconciliationStrategy.AMOUNT_EXACT
        assert result[1] == 0.90

    def test_skonto_amount_match(self, service: SmartReconciliationService) -> None:
        """Test: Skonto-Betrag wird erkannt mit 85%."""
        mock_tx = Mock()
        mock_tx.amount = Decimal("98.00")  # 2% Skonto auf 100

        mock_invoice = Mock()
        mock_invoice.outstanding_amount = Decimal("100.00")
        mock_invoice.amount = Decimal("100.00")
        mock_invoice.skonto_percentage = Decimal("2.0")
        mock_invoice.skonto_deadline = datetime.now(timezone.utc) + timedelta(days=5)

        result = service._check_amount_match(mock_tx, mock_invoice)
        assert result is not None
        assert result[0] == ReconciliationStrategy.AMOUNT_SKONTO
        assert result[1] == 0.85

    def test_partial_payment(self, service: SmartReconciliationService) -> None:
        """Test: Teilzahlung (50%) wird erkannt mit 80%."""
        mock_tx = Mock()
        mock_tx.amount = Decimal("50.00")

        mock_invoice = Mock()
        mock_invoice.outstanding_amount = Decimal("100.00")
        mock_invoice.amount = Decimal("100.00")
        mock_invoice.skonto_percentage = None
        mock_invoice.skonto_deadline = None

        result = service._check_amount_match(mock_tx, mock_invoice)
        assert result is not None
        assert result[0] == ReconciliationStrategy.AMOUNT_PARTIAL
        assert result[1] == 0.80

    def test_zero_invoice_amount(self, service: SmartReconciliationService) -> None:
        """Test: Null-Rechnungsbetrag ergibt keinen Match."""
        mock_tx = Mock()
        mock_tx.amount = Decimal("100.00")

        mock_invoice = Mock()
        mock_invoice.outstanding_amount = Decimal("0")
        mock_invoice.amount = Decimal("0")

        result = service._check_amount_match(mock_tx, mock_invoice)
        assert result is None


class TestNameMatching:
    """Tests fuer Namens-Aehnlichkeit."""

    @pytest.fixture
    def service(self) -> SmartReconciliationService:
        """Erstellt Service-Instanz."""
        return SmartReconciliationService(AsyncMock())

    def test_exact_name_match(self, service: SmartReconciliationService) -> None:
        """Test: Exakt gleicher Name nach Normalisierung."""
        confidence = service._check_name_match("Mueller GmbH", "Mueller GmbH")
        assert confidence == 0.85

    def test_substring_match(self, service: SmartReconciliationService) -> None:
        """Test: Teilstring-Match gibt 75%."""
        confidence = service._check_name_match(
            "Mueller GmbH Berlin",
            "Mueller"
        )
        assert confidence == 0.75

    def test_word_overlap_match(self, service: SmartReconciliationService) -> None:
        """Test: Wort-basierter Match gibt anteiligen Wert."""
        confidence = service._check_name_match(
            "Mueller Technik Berlin",
            "Mueller Technik"
        )
        assert confidence > 0.0

    def test_no_name_match(self, service: SmartReconciliationService) -> None:
        """Test: Komplett unterschiedliche Namen geben 0%."""
        confidence = service._check_name_match(
            "Alpha Consulting",
            "Omega Manufacturing"
        )
        assert confidence == 0.0

    def test_empty_names(self, service: SmartReconciliationService) -> None:
        """Test: Leere Namen geben 0%."""
        assert service._check_name_match("", "Test") == 0.0
        assert service._check_name_match("Test", "") == 0.0


class TestNameNormalization:
    """Tests fuer Namens-Normalisierung."""

    @pytest.fixture
    def service(self) -> SmartReconciliationService:
        """Erstellt Service-Instanz."""
        return SmartReconciliationService(AsyncMock())

    def test_removes_gmbh(self, service: SmartReconciliationService) -> None:
        """Test: GmbH wird entfernt."""
        result = service._normalize_name("Mueller GmbH")
        assert "gmbh" not in result

    def test_removes_ag(self, service: SmartReconciliationService) -> None:
        """Test: AG wird entfernt."""
        result = service._normalize_name("Siemens AG")
        assert "ag" not in result.split()

    def test_lowercase(self, service: SmartReconciliationService) -> None:
        """Test: Alles wird kleingeschrieben."""
        result = service._normalize_name("MUELLER TECHNIK")
        assert result == result.lower()

    def test_removes_special_chars(self, service: SmartReconciliationService) -> None:
        """Test: Sonderzeichen werden entfernt."""
        result = service._normalize_name("Test & Company!")
        assert "&" not in result
        assert "!" not in result


class TestReconciliationMatchToDict:
    """Tests fuer ReconciliationMatch Serialisierung."""

    def test_to_dict(self) -> None:
        """Test: Match wird korrekt zu Dictionary konvertiert."""
        match = ReconciliationMatch(
            invoice_id=uuid4(),
            invoice_number="RE-001",
            entity_name="Test GmbH",
            invoice_amount=Decimal("100.00"),
            transaction_amount=Decimal("100.00"),
            difference=Decimal("0"),
            strategy=ReconciliationStrategy.AMOUNT_EXACT,
            confidence=0.90,
        )
        d = match.to_dict()
        assert d["invoice_number"] == "RE-001"
        assert d["confidence"] == 0.90
        assert d["strategy"] == "amount_exact"


class TestReconciliationResultToDict:
    """Tests fuer ReconciliationResult Serialisierung."""

    def test_to_dict_no_match(self) -> None:
        """Test: Leeres Ergebnis wird korrekt serialisiert."""
        result = ReconciliationResult(
            action=ReconciliationAction.NO_MATCH,
            explanation="Keine passende Rechnung",
        )
        d = result.to_dict()
        assert d["action"] == "no_match"
        assert d["auto_matched"] is False
        assert d["best_match"] is None
