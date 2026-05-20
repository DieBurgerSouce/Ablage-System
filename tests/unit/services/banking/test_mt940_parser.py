# -*- coding: utf-8 -*-
"""Tests fuer den MT940-Parser.

Testet:
- MT940-Format-Erkennung
- Parsing von MT940-Statements mit der mt-940 Bibliothek
- Extraktion von Kontoinfo, Salden und Transaktionen
- Gegenpartei-Extraktion aus :86:-Feld
- Fehlerbehandlung bei ungueltigem MT940
"""

import sys
import pytest
from datetime import date
from decimal import Decimal
from typing import Dict, List, Optional
from unittest.mock import Mock, MagicMock, patch

# Mock mt940 module if not installed
if "mt940" not in sys.modules:
    _mock_mt940 = MagicMock()
    _mock_mt940.models = MagicMock()
    sys.modules["mt940"] = _mock_mt940
    sys.modules["mt940.models"] = _mock_mt940.models

from app.services.banking.parsers.mt940_parser import MT940Parser
from app.services.banking.parsers.base import ParseResult, ParsedTransaction
from app.services.banking.models import ImportFormat, TransactionType


class TestMT940ParserCanParse:
    """Tests fuer die MT940-Format-Erkennung."""

    def test_can_parse_strong_mt940_indicators(self) -> None:
        """Hohe Konfidenz bei :20: und :60: Feldern."""
        content = ":20:STARTUMS\n:25:10020030/1234567890\n:28C:1/1\n:60F:C240101EUR1000,00\n"
        confidence = MT940Parser.can_parse(content)
        assert confidence >= 0.9

    def test_can_parse_multiple_markers(self) -> None:
        """Hohe Konfidenz bei mehreren MT940-Markern."""
        content = ":25:DEUTDEDB/1234\n:28C:001\n:60F:C240101EUR500\n:61:2401010101D50,00\n:62F:C240101EUR450\n"
        confidence = MT940Parser.can_parse(content)
        assert confidence >= 0.7

    def test_can_parse_single_marker(self) -> None:
        """Mittlere Konfidenz bei einzelnem MT940-Marker."""
        content = "Some text\n:61:2401010101D50,00NTRFNONREF\nMore text\n"
        confidence = MT940Parser.can_parse(content)
        assert confidence >= 0.4

    def test_can_parse_no_mt940(self) -> None:
        """Keine Erkennung bei normalem Text."""
        content = "Dies ist kein MT940-Format. Nur normaler Text."
        assert MT940Parser.can_parse(content) == 0.0

    def test_can_parse_empty_content(self) -> None:
        """Gibt 0 bei leerem Inhalt zurueck."""
        assert MT940Parser.can_parse("") == 0.0

    def test_can_parse_bytes_content(self) -> None:
        """Erkennt MT940 in Bytes."""
        content = b":20:STARTUMS\n:25:10020030/123\n:60F:C240101EUR1000,00\n"
        confidence = MT940Parser.can_parse(content)
        assert confidence >= 0.9

    def test_can_parse_filename_sta(self) -> None:
        """Erkennt .sta-Dateiendung."""
        content = "Some banking content without MT940 markers"
        confidence = MT940Parser.can_parse(content, filename="kontoauszug.sta")
        assert confidence >= 0.3

    def test_can_parse_filename_mt940(self) -> None:
        """Erkennt .mt940-Dateiendung."""
        content = "Some content"
        confidence = MT940Parser.can_parse(content, filename="export.mt940")
        assert confidence >= 0.3


class TestMT940ParserParse:
    """Tests fuer das MT940-Parsing mit gemockter mt940-Bibliothek."""

    @pytest.fixture
    def parser(self) -> MT940Parser:
        return MT940Parser()

    def test_parse_empty_statements(self, parser: MT940Parser) -> None:
        """Fehler wenn keine Statements gefunden."""
        with patch("app.services.banking.parsers.mt940_parser.mt940_parse", return_value=[]):
            result = parser.parse("some mt940 content")
            assert result.success is False
            assert len(result.errors) > 0

    def test_parse_with_transactions(self, parser: MT940Parser) -> None:
        """Parst Statement mit Transaktionen."""
        # Mock Transaction
        mock_amount = Mock()
        mock_amount.amount = Decimal("-150.50")

        mock_tx = Mock()
        mock_tx.data = {
            "amount": mock_amount,
            "date": date(2024, 3, 15),
            "entry_date": date(2024, 3, 16),
            "transaction_details": "Miete Maerz 2024",
            "extra_details": {
                "name": "Vermieter GmbH",
                "iban": "DE89370400440532013000",
                "bic": "COBADEFFXXX",
            },
            "id": "NTRF",
            "bank_reference": "PRIM001",
            "customer_reference": "CUST001",
            "currency": "EUR",
        }

        # Mock Opening/Closing Balance
        mock_ob_amount = Mock()
        mock_ob_amount.amount = Decimal("5000")
        mock_ob = Mock()
        mock_ob.amount = mock_ob_amount
        mock_ob.date = date(2024, 3, 1)

        mock_cb_amount = Mock()
        mock_cb_amount.amount = Decimal("4849.50")
        mock_cb = Mock()
        mock_cb.amount = mock_cb_amount
        mock_cb.date = date(2024, 3, 31)

        # Mock Statement
        mock_stmt = Mock()
        mock_stmt.account_id = "DE89370400440532013000"
        mock_stmt.bic = "COBADEFFXXX"
        mock_stmt.opening_balance = mock_ob
        mock_stmt.final_closing_balance = mock_cb
        mock_stmt.closing_balance = None
        mock_stmt.transactions = [mock_tx]

        with patch("app.services.banking.parsers.mt940_parser.mt940_parse", return_value=[mock_stmt]):
            result = parser.parse("mt940 content")

        assert result.success is True
        assert result.format == ImportFormat.MT940
        assert result.account_iban == "DE89370400440532013000"
        assert result.account_bic == "COBADEFFXXX"
        assert result.opening_balance == Decimal("5000")
        assert result.closing_balance == Decimal("4849.50")
        assert len(result.transactions) == 1

        tx = result.transactions[0]
        assert tx.amount == Decimal("-150.50")
        assert tx.booking_date == date(2024, 3, 15)
        assert tx.counterparty_name == "Vermieter GmbH"
        assert tx.counterparty_iban == "DE89370400440532013000"
        assert tx.transaction_id == "CUST001"

    def test_parse_account_number_not_iban(self, parser: MT940Parser) -> None:
        """Speichert kurze Account-IDs als account_number, nicht als IBAN."""
        mock_stmt = Mock()
        mock_stmt.account_id = "1234567890"
        mock_stmt.bic = None
        mock_stmt.opening_balance = None
        mock_stmt.final_closing_balance = None
        mock_stmt.closing_balance = None
        mock_stmt.transactions = []

        with patch("app.services.banking.parsers.mt940_parser.mt940_parse", return_value=[mock_stmt]):
            result = parser.parse("mt940 content")

        assert result.account_iban is None
        assert result.account_number == "1234567890"

    def test_parse_exception_handling(self, parser: MT940Parser) -> None:
        """Faengt Exceptions beim Parsing ab."""
        with patch("app.services.banking.parsers.mt940_parser.mt940_parse", side_effect=Exception("Parse-Fehler")):
            result = parser.parse("invalid content")

        assert result.success is False
        assert len(result.errors) > 0

    def test_parse_bytes_content(self, parser: MT940Parser) -> None:
        """Dekodiert Bytes vor dem Parsing."""
        with patch("app.services.banking.parsers.mt940_parser.mt940_parse", return_value=[]) as mock_parse:
            result = parser.parse(b":20:TEST\n:60F:C240101EUR1000\n")
            # Should have tried to decode and pass to mt940_parse
            assert mock_parse.called

    def test_parse_transaction_with_string_extra_details(self, parser: MT940Parser) -> None:
        """Behandelt extra_details als String (nicht Dict)."""
        mock_amount = Mock()
        mock_amount.amount = Decimal("100")

        mock_tx = Mock()
        mock_tx.data = {
            "amount": mock_amount,
            "date": date(2024, 1, 1),
            "entry_date": None,
            "transaction_details": "Zahlung erhalten",
            "extra_details": "Max Mustermann",
            "id": None,
            "guvc": None,
            "bank_reference": None,
            "customer_reference": None,
            "currency": "EUR",
        }

        mock_stmt = Mock()
        mock_stmt.account_id = None
        mock_stmt.bic = None
        mock_stmt.opening_balance = None
        mock_stmt.final_closing_balance = None
        mock_stmt.closing_balance = None
        mock_stmt.transactions = [mock_tx]

        with patch("app.services.banking.parsers.mt940_parser.mt940_parse", return_value=[mock_stmt]):
            result = parser.parse("mt940 content")

        assert result.success is True
        assert len(result.transactions) == 1

    def test_parse_statistics(self, parser: MT940Parser) -> None:
        """Berechnet Gutschriften und Belastungen korrekt."""
        mock_credit = Mock()
        mock_credit.amount = Decimal("500")
        mock_debit = Mock()
        mock_debit.amount = Decimal("-200")

        def make_tx(amount_mock: Mock, tx_date: date) -> Mock:
            tx = Mock()
            tx.data = {
                "amount": amount_mock,
                "date": tx_date,
                "entry_date": None,
                "transaction_details": "Test",
                "extra_details": None,
                "id": None,
                "guvc": None,
                "bank_reference": None,
                "customer_reference": None,
                "currency": "EUR",
            }
            return tx

        mock_stmt = Mock()
        mock_stmt.account_id = None
        mock_stmt.bic = None
        mock_stmt.opening_balance = None
        mock_stmt.final_closing_balance = None
        mock_stmt.closing_balance = None
        mock_stmt.transactions = [
            make_tx(mock_credit, date(2024, 1, 10)),
            make_tx(mock_debit, date(2024, 1, 15)),
        ]

        with patch("app.services.banking.parsers.mt940_parser.mt940_parse", return_value=[mock_stmt]):
            result = parser.parse("mt940 content")

        assert result.success is True
        assert result.total_credits == Decimal("500")
        assert result.total_debits == Decimal("200")


class TestMT940ParserCounterpartyExtraction:
    """Tests fuer die Gegenpartei-Extraktion aus :86:-Feld."""

    @pytest.fixture
    def parser(self) -> MT940Parser:
        return MT940Parser()

    def test_extract_iban_from_reference(self, parser: MT940Parser) -> None:
        """Extrahiert IBAN aus unstrukturiertem Text."""
        name, iban = parser._extract_counterparty(
            "Mueller GmbH DE89370400440532013000 Rechnung 123"
        )
        assert iban == "DE89370400440532013000"

    def test_extract_name_from_name_plus(self, parser: MT940Parser) -> None:
        """Extrahiert Namen aus NAME+ Pattern."""
        name, iban = parser._extract_counterparty("NAME+Mueller GmbH+IBAN+DE89370400440532013000")
        assert name == "Mueller GmbH"

    def test_extract_name_auftraggeber(self, parser: MT940Parser) -> None:
        """Extrahiert Namen aus AUFTRAGGEBER: Pattern."""
        name, iban = parser._extract_counterparty("AUFTRAGGEBER: Schmidt AG\nKREF+12345")
        assert name == "Schmidt AG"

    def test_extract_fallback_first_line(self, parser: MT940Parser) -> None:
        """Nutzt erste Zeile als Fallback-Name."""
        name, iban = parser._extract_counterparty("Stadtwerke Berlin\nStrom Maerz 2024")
        assert name == "Stadtwerke Berlin"

    def test_no_name_for_eref_line(self, parser: MT940Parser) -> None:
        """Erste Zeile wird nicht als Name genutzt wenn sie mit EREF+ beginnt."""
        name, iban = parser._extract_counterparty("EREF+12345678\nZahlung")
        assert name is None or not name.startswith("EREF")

    def test_empty_reference(self, parser: MT940Parser) -> None:
        """Behandelt leeren Referenz-Text."""
        name, iban = parser._extract_counterparty("")
        assert name is None
        assert iban is None
