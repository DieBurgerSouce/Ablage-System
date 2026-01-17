# -*- coding: utf-8 -*-
"""
Tests fuer TransactionService.

Testet:
- Transaktionen auflisten und filtern
- Transaktionsdetails abrufen
- Transaktionen aktualisieren
- Reconciliation-Status setzen
- Statistiken berechnen
"""

import pytest
from datetime import datetime, date, timedelta
from decimal import Decimal
from typing import List
from uuid import uuid4
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.banking.transaction_service import TransactionService
from app.services.banking.models import (
    TransactionType,
    ReconciliationStatus,
    TransactionFilter,
    TransactionStats,
    BankTransactionResponse,
)


class TestTransactionServiceFiltering:
    """Tests fuer Transaktions-Filterung."""

    @pytest.fixture
    def service(self) -> TransactionService:
        return TransactionService()

    @pytest.fixture
    def mock_db(self):
        """Mockt AsyncSession."""
        db = AsyncMock()
        db.execute = AsyncMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock()
        return db

    def test_build_filter_date_range(self, service: TransactionService):
        """Sollte Datumsbereich-Filter erstellen."""
        filters = TransactionFilter(
            date_from=date(2024, 1, 1),
            date_to=date(2024, 12, 31),
        )
        assert filters.date_from == date(2024, 1, 1)
        assert filters.date_to == date(2024, 12, 31)

    def test_build_filter_amount_range(self, service: TransactionService):
        """Sollte Betragsbereich-Filter erstellen."""
        filters = TransactionFilter(
            amount_min=Decimal("100.00"),
            amount_max=Decimal("1000.00"),
        )
        assert filters.amount_min == Decimal("100.00")
        assert filters.amount_max == Decimal("1000.00")

    def test_build_filter_transaction_type(self, service: TransactionService):
        """Sollte Transaktionstyp-Filter erstellen."""
        filters = TransactionFilter(
            transaction_type=TransactionType.TRANSFER,
        )
        assert filters.transaction_type == TransactionType.TRANSFER

    def test_build_filter_reconciliation_status(self, service: TransactionService):
        """Sollte Reconciliation-Status-Filter erstellen."""
        filters = TransactionFilter(
            reconciliation_status=ReconciliationStatus.UNMATCHED,
        )
        assert filters.reconciliation_status == ReconciliationStatus.UNMATCHED

    def test_build_filter_search_text(self, service: TransactionService):
        """Sollte Suchtext-Filter erstellen."""
        filters = TransactionFilter(
            search_text="Miete",
        )
        assert filters.search_text == "Miete"

    def test_build_filter_combined(self, service: TransactionService):
        """Sollte kombinierte Filter erstellen."""
        filters = TransactionFilter(
            date_from=date(2024, 1, 1),
            amount_min=Decimal("50.00"),
            transaction_type=TransactionType.DIRECT_DEBIT,
            reconciliation_status=ReconciliationStatus.MATCHED,
            search_text="Strom",
        )
        assert filters.date_from == date(2024, 1, 1)
        assert filters.amount_min == Decimal("50.00")
        assert filters.transaction_type == TransactionType.DIRECT_DEBIT
        assert filters.reconciliation_status == ReconciliationStatus.MATCHED
        assert filters.search_text == "Strom"


class TestTransactionServiceResponseConversion:
    """Tests fuer Response-Konvertierung."""

    @pytest.fixture
    def service(self) -> TransactionService:
        return TransactionService()

    def test_to_response_basic_fields(self, service: TransactionService):
        """Sollte alle Basis-Felder korrekt konvertieren."""
        mock_tx = MagicMock()
        mock_tx.id = uuid4()
        mock_tx.bank_account_id = uuid4()
        mock_tx.import_id = uuid4()
        mock_tx.transaction_id = "TX123456"
        mock_tx.booking_date = date(2024, 12, 15)
        mock_tx.value_date = date(2024, 12, 15)
        mock_tx.amount = Decimal("1234.56")
        mock_tx.currency = "EUR"
        mock_tx.counterparty_name = "Max Mustermann"
        mock_tx.counterparty_iban = "DE89370400440532013000"
        mock_tx.counterparty_bic = "COBADEFFXXX"
        mock_tx.reference_text = "Miete Dezember"
        mock_tx.end_to_end_id = "E2E123456"
        mock_tx.mandate_id = "MANDATE123"
        mock_tx.creditor_id = "DE98ZZZ09999999999"
        mock_tx.transaction_type = "transfer"
        mock_tx.booking_text = "ÜBERWEISUNG"
        mock_tx.reconciliation_status = "unmatched"
        mock_tx.matched_document_id = None
        mock_tx.match_confidence = None
        mock_tx.matched_at = None
        mock_tx.notes = "Test-Notiz"
        mock_tx.tags = ["miete", "dezember"]
        mock_tx.category = "wohnen"
        mock_tx.parsed_invoice_numbers = []
        mock_tx.parsed_customer_numbers = []
        mock_tx.parsed_references = []
        mock_tx.created_at = datetime.now()
        mock_tx.updated_at = datetime.now()
        # Zusaetzliche Felder fuer BankTransactionResponse
        mock_tx.matched_invoice_number = None
        mock_tx.match_method = None
        mock_tx.is_partial_payment = False
        mock_tx.allocated_amount = None
        mock_tx.remaining_amount = None
        mock_tx.imported_at = datetime.now()

        response = service._to_response(mock_tx)

        assert response.id == mock_tx.id
        assert response.bank_account_id == mock_tx.bank_account_id
        assert response.amount == Decimal("1234.56")
        assert response.counterparty_name == "Max Mustermann"
        assert response.transaction_type == TransactionType.TRANSFER
        assert response.reconciliation_status == ReconciliationStatus.UNMATCHED
        # notes und tags sind nicht im Response-Schema exponiert

    def test_to_response_default_values(self, service: TransactionService):
        """Sollte Standardwerte fuer fehlende Felder setzen."""
        mock_tx = MagicMock()
        mock_tx.id = uuid4()
        mock_tx.bank_account_id = uuid4()
        mock_tx.import_id = None
        mock_tx.transaction_id = None
        mock_tx.booking_date = date(2024, 12, 15)
        # value_date muss gesetzt sein (Pflichtfeld im Schema)
        mock_tx.value_date = date(2024, 12, 15)
        mock_tx.amount = Decimal("100.00")
        mock_tx.currency = None
        mock_tx.counterparty_name = None
        mock_tx.counterparty_iban = None
        mock_tx.counterparty_bic = None
        mock_tx.reference_text = None
        mock_tx.end_to_end_id = None
        mock_tx.mandate_id = None
        mock_tx.creditor_id = None
        mock_tx.transaction_type = None
        mock_tx.booking_text = None
        mock_tx.reconciliation_status = None
        mock_tx.matched_document_id = None
        mock_tx.match_confidence = None
        mock_tx.matched_at = None
        mock_tx.notes = None
        mock_tx.tags = None
        mock_tx.category = None
        mock_tx.parsed_invoice_numbers = None
        mock_tx.parsed_customer_numbers = None
        mock_tx.parsed_references = None
        mock_tx.created_at = datetime.now()
        mock_tx.updated_at = None
        # Zusaetzliche Pflichtfelder fuer BankTransactionResponse
        mock_tx.matched_invoice_number = None
        mock_tx.match_method = None
        mock_tx.is_partial_payment = False
        mock_tx.allocated_amount = None
        mock_tx.remaining_amount = None
        mock_tx.imported_at = datetime.now()

        response = service._to_response(mock_tx)

        assert response.currency == "EUR"
        assert response.transaction_type is None
        assert response.reconciliation_status == ReconciliationStatus.UNMATCHED
        # tags ist nicht im Response-Schema exponiert


class TestTransactionServiceWithMockedDB:
    """Tests mit gemockter Datenbank."""

    @pytest.fixture
    def service(self) -> TransactionService:
        return TransactionService()

    @pytest.fixture
    def mock_db(self):
        """Mockt AsyncSession."""
        db = AsyncMock()
        db.execute = AsyncMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock()
        db.get = AsyncMock()
        return db

    @pytest.mark.asyncio
    async def test_get_transaction_returns_none_for_other_user(
        self, service: TransactionService, mock_db
    ):
        """Sollte None zurueckgeben wenn Transaktion anderem User gehoert."""
        user_id = uuid4()
        transaction_id = uuid4()

        # Mock: Keine Transaktion gefunden
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        result = await service.get_transaction(mock_db, user_id, transaction_id)

        assert result is None

    @pytest.mark.asyncio
    async def test_update_transaction_returns_none_for_missing(
        self, service: TransactionService, mock_db
    ):
        """Sollte None zurueckgeben wenn Transaktion nicht existiert."""
        user_id = uuid4()
        transaction_id = uuid4()

        # Mock: Keine Transaktion gefunden
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        result = await service.update_transaction(
            mock_db, user_id, transaction_id, notes="Test"
        )

        assert result is None


class TestTransactionStats:
    """Tests fuer Transaktions-Statistiken."""

    def test_stats_model_creation(self):
        """Sollte TransactionStats korrekt erstellen."""
        stats = TransactionStats(
            total_count=100,
            total_credits=Decimal("50000.00"),
            total_debits=Decimal("30000.00"),
            unmatched_count=25,
            matched_count=70,
            partially_matched_count=5,
            match_rate=70.0,
        )

        assert stats.total_count == 100
        assert stats.total_credits == Decimal("50000.00")
        assert stats.total_debits == Decimal("30000.00")
        assert stats.unmatched_count == 25
        assert stats.matched_count == 70
        assert stats.match_rate == 70.0

    def test_stats_net_calculation(self):
        """Sollte Netto-Betrag korrekt berechnen."""
        stats = TransactionStats(
            total_count=10,
            total_credits=Decimal("1000.00"),
            total_debits=Decimal("750.00"),
            unmatched_count=2,
            matched_count=8,
            partially_matched_count=0,
            match_rate=80.0,
        )

        net = stats.total_credits - stats.total_debits
        assert net == Decimal("250.00")


class TestReconciliationStatus:
    """Tests fuer Reconciliation-Status-Handling."""

    @pytest.fixture
    def service(self) -> TransactionService:
        return TransactionService()

    @pytest.fixture
    def mock_db(self):
        """Mockt AsyncSession."""
        db = AsyncMock()
        db.execute = AsyncMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock()
        return db

    @pytest.mark.asyncio
    async def test_set_reconciliation_status_matched(
        self, service: TransactionService, mock_db
    ):
        """Sollte MATCHED-Status korrekt setzen."""
        user_id = uuid4()
        transaction_id = uuid4()
        document_id = uuid4()

        # Mock Transaktion
        mock_tx = MagicMock()
        mock_tx.id = transaction_id
        mock_tx.bank_account_id = uuid4()
        mock_tx.import_id = None
        mock_tx.transaction_id = "TX123"
        mock_tx.booking_date = date(2024, 12, 15)
        mock_tx.value_date = date(2024, 12, 15)  # Pflichtfeld
        mock_tx.amount = Decimal("100.00")
        mock_tx.currency = "EUR"
        mock_tx.counterparty_name = "Test"
        mock_tx.counterparty_iban = None
        mock_tx.counterparty_bic = None
        mock_tx.reference_text = "Test"
        mock_tx.end_to_end_id = None
        mock_tx.mandate_id = None
        mock_tx.creditor_id = None
        mock_tx.transaction_type = None
        mock_tx.booking_text = None
        mock_tx.reconciliation_status = "unmatched"
        mock_tx.matched_document_id = None
        mock_tx.match_confidence = None
        mock_tx.matched_at = None
        mock_tx.notes = None
        mock_tx.tags = None
        mock_tx.category = None
        mock_tx.parsed_invoice_numbers = []
        mock_tx.parsed_customer_numbers = []
        mock_tx.parsed_references = []
        mock_tx.created_at = datetime.now()
        mock_tx.updated_at = None
        # Zusaetzliche Pflichtfelder fuer BankTransactionResponse
        mock_tx.matched_invoice_number = None
        mock_tx.match_method = None
        mock_tx.is_partial_payment = False
        mock_tx.allocated_amount = None
        mock_tx.remaining_amount = None
        mock_tx.imported_at = datetime.now()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_tx
        mock_db.execute.return_value = mock_result

        result = await service.set_reconciliation_status(
            mock_db,
            user_id,
            transaction_id,
            status=ReconciliationStatus.MATCHED,
            matched_document_id=document_id,
            match_confidence=0.95,
        )

        # Verify status was updated
        assert mock_tx.reconciliation_status == ReconciliationStatus.MATCHED.value
        assert mock_tx.matched_document_id == document_id
        assert mock_tx.match_confidence == 0.95
        assert mock_tx.matched_at is not None
        mock_db.commit.assert_called_once()


class TestTransactionFilter:
    """Tests fuer TransactionFilter Model."""

    def test_filter_empty(self):
        """Sollte leeren Filter erstellen."""
        filters = TransactionFilter()
        assert filters.date_from is None
        assert filters.date_to is None
        assert filters.amount_min is None
        assert filters.amount_max is None
        assert filters.transaction_type is None
        assert filters.reconciliation_status is None
        assert filters.search_text is None

    def test_filter_with_all_fields(self):
        """Sollte Filter mit allen Feldern erstellen."""
        filters = TransactionFilter(
            date_from=date(2024, 1, 1),
            date_to=date(2024, 12, 31),
            amount_min=Decimal("10.00"),
            amount_max=Decimal("1000.00"),
            transaction_type=TransactionType.TRANSFER,
            reconciliation_status=ReconciliationStatus.UNMATCHED,
            search_text="Test",
            counterparty_name="Max Mustermann",
            counterparty_iban="DE89370400440532013000",
        )

        assert filters.date_from == date(2024, 1, 1)
        assert filters.date_to == date(2024, 12, 31)
        assert filters.amount_min == Decimal("10.00")
        assert filters.amount_max == Decimal("1000.00")
        assert filters.transaction_type == TransactionType.TRANSFER
        assert filters.reconciliation_status == ReconciliationStatus.UNMATCHED
        assert filters.search_text == "Test"
        assert filters.counterparty_name == "Max Mustermann"
        assert filters.counterparty_iban == "DE89370400440532013000"
