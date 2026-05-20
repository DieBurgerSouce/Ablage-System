# -*- coding: utf-8 -*-
"""Tests fuer AutoReconciliationService.

Testet automatischen Transaktionsabgleich mit Rechnungen:
- Verschiedene Matching-Strategien
- Konfidenz-Schwellen
- Teilzahlungen
- Manuelle Zuordnung
- Batch-Verarbeitung
"""

import pytest
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import List
from uuid import UUID, uuid4
from unittest.mock import AsyncMock, Mock, MagicMock, patch

from app.services.banking.auto_reconciliation_service import (
    AutoReconciliationService,
    ReconciliationConfig,
    ReconciliationResult,
    BatchReconciliationResult,
    MatchCandidate,
)
from app.db.models_banking_connection import ReconciliationMatchType


class TestAutoReconciliationService:
    """Tests fuer AutoReconciliationService Initialisierung und Konfiguration."""

    def test_default_config(self) -> None:
        """Test: Service wird mit Standard-Konfiguration erstellt."""
        service = AutoReconciliationService()
        assert service.config.auto_reconcile_threshold == 0.90
        assert service.config.suggestion_threshold == 0.50
        assert service.config.max_suggestions == 5

    def test_custom_config(self) -> None:
        """Test: Service akzeptiert benutzerdefinierte Konfiguration."""
        config = ReconciliationConfig(
            auto_reconcile_threshold=0.80,
            suggestion_threshold=0.40,
            max_suggestions=10,
        )
        service = AutoReconciliationService(config=config)
        assert service.config.auto_reconcile_threshold == 0.80
        assert service.config.max_suggestions == 10


class TestReconcileTransaction:
    """Tests fuer reconcile_transaction Methode."""

    @pytest.fixture
    def service(self) -> AutoReconciliationService:
        """Erstellt Service-Instanz."""
        return AutoReconciliationService()

    @pytest.fixture
    def mock_db(self) -> AsyncMock:
        """Mock fuer Datenbank-Session."""
        return AsyncMock()

    @pytest.mark.asyncio
    async def test_transaction_not_found(self, service: AutoReconciliationService, mock_db: AsyncMock) -> None:
        """Test: Transaktion nicht gefunden liefert Fehler."""
        tx_id = uuid4()
        company_id = uuid4()

        # _get_transaction_with_account returns None
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        result = await service.reconcile_transaction(mock_db, tx_id, company_id)

        assert result.success is False
        assert result.error_message == "Transaktion nicht gefunden"
        assert result.transaction_id == tx_id

    @pytest.mark.asyncio
    async def test_already_reconciled_transaction(self, service: AutoReconciliationService, mock_db: AsyncMock) -> None:
        """Test: Bereits abgeglichene Transaktion wird uebersprungen."""
        tx_id = uuid4()
        company_id = uuid4()
        invoice_id = uuid4()

        mock_tx = Mock()
        mock_tx.reconciliation_status = "matched"
        mock_tx.reconciliation_match_type = "auto_exact"
        mock_tx.reconciliation_confidence = 0.99
        mock_tx.matched_invoice_id = invoice_id

        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = mock_tx
        mock_db.execute.return_value = mock_result

        result = await service.reconcile_transaction(mock_db, tx_id, company_id)

        assert result.success is True
        assert result.matched is True
        assert result.invoice_id == invoice_id
        assert result.confidence == 0.99

    @pytest.mark.asyncio
    async def test_negative_amount_skipped(self, service: AutoReconciliationService, mock_db: AsyncMock) -> None:
        """Test: Ausgehende Zahlungen (negativ) werden nicht abgeglichen."""
        tx_id = uuid4()
        company_id = uuid4()

        mock_tx = Mock()
        mock_tx.reconciliation_status = "pending"
        mock_tx.amount = Decimal("-100.00")

        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = mock_tx
        mock_db.execute.return_value = mock_result

        result = await service.reconcile_transaction(mock_db, tx_id, company_id)

        assert result.success is True
        assert result.matched is False
        assert "eingehende" in result.error_message

    @pytest.mark.asyncio
    async def test_no_candidates_found(self, service: AutoReconciliationService, mock_db: AsyncMock) -> None:
        """Test: Keine Kandidaten gefunden ergibt unmatched."""
        tx_id = uuid4()
        company_id = uuid4()

        mock_tx = Mock()
        mock_tx.reconciliation_status = "pending"
        mock_tx.amount = Decimal("100.00")
        mock_tx.counterparty_iban = None
        mock_tx.reference_text = None
        mock_tx.counterparty_name = None

        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = mock_tx
        mock_db.execute.return_value = mock_result

        result = await service.reconcile_transaction(mock_db, tx_id, company_id)

        assert result.success is True
        assert result.matched is False

    @pytest.mark.asyncio
    async def test_high_confidence_auto_apply(self, service: AutoReconciliationService) -> None:
        """Test: Hohe Konfidenz fuehrt zu automatischer Zuordnung."""
        tx_id = uuid4()
        company_id = uuid4()
        invoice_id = uuid4()
        mock_db = AsyncMock()

        mock_tx = Mock()
        mock_tx.reconciliation_status = "pending"
        mock_tx.amount = Decimal("1000.00")
        mock_tx.counterparty_iban = "DE89370400440532013000"
        mock_tx.reference_text = None
        mock_tx.counterparty_name = None

        # Mock _get_transaction_with_account
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = mock_tx
        mock_db.execute.return_value = mock_result

        # Patch _find_candidates to return a high-confidence match
        candidate = MatchCandidate(
            invoice_id=invoice_id,
            invoice_number="RE-2026-001",
            invoice_date=date.today(),
            due_date=date.today(),
            invoice_amount=Decimal("1000.00"),
            outstanding_amount=Decimal("1000.00"),
            currency="EUR",
            entity_id=uuid4(),
            entity_name="Test GmbH",
            entity_iban="DE89370400440532013000",
            confidence=0.99,
            match_type=ReconciliationMatchType.AUTO_EXACT,
        )

        with patch.object(service, "_find_candidates", return_value=[candidate]):
            with patch.object(service, "_apply_match", new_callable=AsyncMock):
                result = await service.reconcile_transaction(mock_db, tx_id, company_id, auto_apply=True)

        assert result.success is True
        assert result.matched is True
        assert result.confidence == 0.99
        assert result.invoice_id == invoice_id

    @pytest.mark.asyncio
    async def test_low_confidence_returns_suggestions(self, service: AutoReconciliationService) -> None:
        """Test: Niedrige Konfidenz liefert Vorschlaege statt Auto-Match."""
        tx_id = uuid4()
        company_id = uuid4()
        mock_db = AsyncMock()

        mock_tx = Mock()
        mock_tx.reconciliation_status = "pending"
        mock_tx.amount = Decimal("500.00")
        mock_tx.counterparty_iban = None
        mock_tx.reference_text = None
        mock_tx.counterparty_name = "Test AG"

        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = mock_tx
        mock_db.execute.return_value = mock_result

        candidate = MatchCandidate(
            invoice_id=uuid4(),
            invoice_number="RE-2026-002",
            invoice_date=date.today(),
            due_date=date.today(),
            invoice_amount=Decimal("500.00"),
            outstanding_amount=Decimal("500.00"),
            currency="EUR",
            entity_id=None,
            entity_name=None,
            entity_iban=None,
            confidence=0.70,
            match_type=ReconciliationMatchType.AUTO_FUZZY,
        )

        with patch.object(service, "_find_candidates", return_value=[candidate]):
            result = await service.reconcile_transaction(mock_db, tx_id, company_id, auto_apply=True)

        assert result.success is True
        assert result.matched is False
        assert len(result.suggestions) == 1
        assert result.suggestions[0].confidence == 0.70

    @pytest.mark.asyncio
    async def test_exception_returns_error(self, service: AutoReconciliationService) -> None:
        """Test: Exception wird abgefangen und als Fehler zurueckgegeben."""
        tx_id = uuid4()
        company_id = uuid4()
        mock_db = AsyncMock()

        mock_tx = Mock()
        mock_tx.reconciliation_status = "pending"
        mock_tx.amount = Decimal("100.00")
        mock_tx.counterparty_iban = "DE89370400440532013000"
        mock_tx.reference_text = None
        mock_tx.counterparty_name = None

        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = mock_tx
        mock_db.execute.return_value = mock_result

        with patch.object(service, "_find_candidates", side_effect=RuntimeError("DB-Fehler")):
            result = await service.reconcile_transaction(mock_db, tx_id, company_id)

        assert result.success is False
        assert result.error_message is not None


class TestManualMatch:
    """Tests fuer manuelle Zuordnung."""

    @pytest.fixture
    def service(self) -> AutoReconciliationService:
        """Erstellt Service-Instanz."""
        return AutoReconciliationService()

    @pytest.mark.asyncio
    async def test_manual_match_success(self, service: AutoReconciliationService) -> None:
        """Test: Erfolgreiche manuelle Zuordnung."""
        tx_id = uuid4()
        invoice_id = uuid4()
        company_id = uuid4()
        user_id = uuid4()
        mock_db = AsyncMock()

        mock_tx = Mock()
        mock_tx.amount = Decimal("500.00")

        mock_invoice = Mock()
        mock_invoice.company_id = company_id
        mock_invoice.outstanding_amount = 500.00

        # _get_transaction_with_account
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = mock_tx
        mock_db.execute.return_value = mock_result

        mock_db.get = AsyncMock(return_value=mock_invoice)

        result = await service.manual_match(mock_db, tx_id, invoice_id, company_id, user_id)

        assert result.success is True
        assert result.matched is True
        assert result.match_type == ReconciliationMatchType.MANUAL
        assert result.confidence == 1.0

    @pytest.mark.asyncio
    async def test_manual_match_invoice_not_found(self, service: AutoReconciliationService) -> None:
        """Test: Manuelle Zuordnung mit fehlender Rechnung schlaegt fehl."""
        tx_id = uuid4()
        invoice_id = uuid4()
        company_id = uuid4()
        user_id = uuid4()
        mock_db = AsyncMock()

        mock_tx = Mock()
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = mock_tx
        mock_db.execute.return_value = mock_result

        mock_db.get = AsyncMock(return_value=None)

        result = await service.manual_match(mock_db, tx_id, invoice_id, company_id, user_id)

        assert result.success is False
        assert "Rechnung" in result.error_message


class TestSplitTransaction:
    """Tests fuer Transaktions-Aufteilung."""

    @pytest.fixture
    def service(self) -> AutoReconciliationService:
        """Erstellt Service-Instanz."""
        return AutoReconciliationService()

    @pytest.mark.asyncio
    async def test_split_amount_mismatch(self, service: AutoReconciliationService) -> None:
        """Test: Abweichende Summe bei Aufteilung wird abgelehnt."""
        tx_id = uuid4()
        company_id = uuid4()
        user_id = uuid4()
        mock_db = AsyncMock()

        mock_tx = Mock()
        mock_tx.amount = Decimal("1000.00")
        mock_tx.currency = "EUR"

        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = mock_tx
        mock_db.execute.return_value = mock_result

        allocations = [
            {"invoice_id": str(uuid4()), "amount": "300.00"},
            {"invoice_id": str(uuid4()), "amount": "300.00"},
        ]

        result = await service.split_transaction(mock_db, tx_id, company_id, user_id, allocations)

        assert result.success is False
        assert "Summe" in result.error_message


class TestHelperMethods:
    """Tests fuer Hilfs-Methoden."""

    def test_extract_invoice_numbers_re_format(self) -> None:
        """Test: Rechnungsnummern im RE-Format werden extrahiert."""
        service = AutoReconciliationService()
        numbers = service._extract_invoice_numbers("Zahlung RE-20240123 und RE20249999")
        assert "20240123" in numbers or "20249999" in numbers

    def test_extract_invoice_numbers_rechnung_format(self) -> None:
        """Test: Rechnungsnummern im Rechnung-Nr Format werden extrahiert."""
        service = AutoReconciliationService()
        numbers = service._extract_invoice_numbers("Rechnung Nr. 123456")
        assert "123456" in numbers

    def test_extract_invoice_numbers_no_match(self) -> None:
        """Test: Text ohne Rechnungsnummer liefert leere Liste."""
        service = AutoReconciliationService()
        numbers = service._extract_invoice_numbers("Allgemeine Zahlung ohne Referenz")
        assert len(numbers) == 0

    def test_extract_customer_numbers(self) -> None:
        """Test: Kundennummern werden korrekt extrahiert."""
        service = AutoReconciliationService()
        numbers = service._extract_customer_numbers("KD-NR 12345 Kundennummer: 67890")
        assert "12345" in numbers or "67890" in numbers

    def test_calculate_name_similarity_identical(self) -> None:
        """Test: Identische Namen ergeben Aehnlichkeit 1.0."""
        service = AutoReconciliationService()
        similarity = service._calculate_name_similarity("mueller gmbh", "mueller gmbh")
        assert similarity == 1.0

    def test_calculate_name_similarity_partial(self) -> None:
        """Test: Teilweise uebereinstimmende Namen ergeben Wert > 0."""
        service = AutoReconciliationService()
        similarity = service._calculate_name_similarity("mueller gmbh berlin", "mueller gmbh")
        assert similarity > 0.0
        assert similarity < 1.0

    def test_calculate_name_similarity_empty(self) -> None:
        """Test: Leere Namen ergeben 0.0."""
        service = AutoReconciliationService()
        assert service._calculate_name_similarity("", "test") == 0.0
        assert service._calculate_name_similarity("test", "") == 0.0
