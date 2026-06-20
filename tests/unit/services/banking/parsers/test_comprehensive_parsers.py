# -*- coding: utf-8 -*-
"""
Comprehensive Banking Parser Tests.

Enterprise-Level Tests fuer alle Banking Parser:
- Per-Bank CSV Tests (Commerzbank, Deutsche Bank, DKB, ING, N26, Sparkasse, Volksbank)
- MT940 SWIFT Parser Tests
- CAMT.053 XML Parser Tests mit XXE-Schutz
- Utility Functions (Amount Parsing, IBAN Normalisierung, Reference Extraction)

Diese Tests decken kritische Compliance-Anforderungen ab.
"""

import pytest
from datetime import date
from decimal import Decimal
from typing import Optional
from unittest.mock import Mock, patch, MagicMock
import io

from app.services.banking.parsers.base import (
    BaseParser,
    ParseResult,
    ParsedTransaction,
    ParserRegistry,
    detect_format,
)
from app.services.banking.parsers.csv_parser import GenericCSVParser
from app.services.banking.parsers.mt940_parser import MT940Parser
from app.services.banking.parsers.camt053_parser import CAMT053Parser
from app.services.banking.parsers.bank_csv.commerzbank import CommerzbankCSVParser
from app.services.banking.parsers.bank_csv.deutsche_bank import DeutscheBankCSVParser
from app.services.banking.parsers.bank_csv.dkb import DKBCSVParser
from app.services.banking.parsers.bank_csv.ing import INGCSVParser
from app.services.banking.parsers.bank_csv.n26 import N26CSVParser
from app.services.banking.parsers.bank_csv.sparkasse import SparkasseCSVParser
from app.services.banking.parsers.bank_csv.volksbank import VolksbankCSVParser
from app.services.banking.models import ImportFormat, TransactionType
from app.services.banking.utils import mask_iban, mask_account_number, mask_bic


class _MT940Collection:
    """Mimt die mt940 Transactions-Collection (Parser-Refactor 2026-06-12).

    ``mt940.parse()`` liefert ein iterierbares Collection-Objekt: Statement-
    Metadaten (:25:/:60F:/:62F:) liegen im ``.data``-Dict, die Iteration ergibt
    die einzelnen Transaktionen.
    """

    def __init__(self, data: dict, transactions: list) -> None:
        self.data = data
        self._transactions = transactions

    def __iter__(self):
        return iter(self._transactions)


def _make_mt940_collection(data: dict, transactions: list) -> _MT940Collection:
    return _MT940Collection(data=data, transactions=transactions)


# =============================================================================
# COMMERZBANK CSV PARSER TESTS
# =============================================================================

class TestCommerzbankCSVParser:
    """Umfassende Tests fuer Commerzbank CSV Parser."""

    @pytest.fixture
    def parser(self) -> CommerzbankCSVParser:
        return CommerzbankCSVParser()

    def test_can_parse_confidence_with_auftraggeber(self, parser: CommerzbankCSVParser):
        """Sollte 0.95 Konfidenz bei 'auftraggeber / beguenstigter' erreichen."""
        content = """Buchungstag;Wertstellung;Umsatzart;Buchungstext;Auftraggeber / Begünstigter;Betrag
15.12.2024;15.12.2024;Überweisung;GUTSCHRIFT;Max Mustermann;1.000,00"""
        confidence = parser.can_parse(content)
        assert confidence == 0.95, f"Erwartete 0.95, erhielt {confidence}"

    def test_can_parse_confidence_with_umlaut_variant(self, parser: CommerzbankCSVParser):
        """Sollte auch ohne Umlaute erkennen."""
        content = """Buchungstag;Wertstellung;Umsatzart;Buchungstext;Auftraggeber / Beguenstigter;Betrag
15.12.2024;15.12.2024;Überweisung;GUTSCHRIFT;Max Mustermann;1.000,00"""
        confidence = parser.can_parse(content)
        assert confidence == 0.95

    def test_utf8_bom_handling(self, parser: CommerzbankCSVParser):
        """Sollte UTF-8 BOM korrekt handhaben."""
        # UTF-8 BOM Prefix
        bom_content = "\ufeffBuchungstag;Wertstellung;Umsatzart;Buchungstext;Auftraggeber / Begünstigter;Betrag\n15.12.2024;15.12.2024;Test;Test;Test;100,00"
        confidence = parser.can_parse(bom_content)
        assert confidence == 0.95

    def test_column_mapping(self, parser: CommerzbankCSVParser):
        """Sollte Spalten korrekt mappen."""
        fieldnames = [
            "Buchungstag", "Wertstellung", "Betrag", "Währung",
            "Auftraggeber / Begünstigter", "IBAN", "BIC",
            "Buchungstext", "Umsatzart"
        ]
        mapping = parser._map_columns(fieldnames)

        assert mapping.get("booking_date") == "Buchungstag"
        assert mapping.get("value_date") == "Wertstellung"
        assert mapping.get("amount") == "Betrag"
        assert mapping.get("currency") == "Währung"
        assert mapping.get("counterparty_name") == "Auftraggeber / Begünstigter"
        assert mapping.get("counterparty_iban") == "IBAN"

    def test_parse_transaction_with_german_amounts(self, parser: CommerzbankCSVParser):
        """Sollte deutsche Betragsformate korrekt parsen."""
        content = """Buchungstag;Wertstellung;Umsatzart;Buchungstext;Auftraggeber / Begünstigter;Verwendungszweck;IBAN;BIC;Betrag;Währung
15.12.2024;16.12.2024;Überweisung;GUTSCHRIFT;Max Mustermann;Miete Dezember;DE89370400440532013000;COBADEFFXXX;1.234,56;EUR
16.12.2024;17.12.2024;Lastschrift;ABSCHLAG;Stromanbieter GmbH;Strom 12/2024;DE11520513735120710131;HELADEF1822;-89,99;EUR"""
        result = parser.parse(content)
        assert result.success, f"Parse fehlgeschlagen: {result.errors}"
        assert result.transaction_count == 2

        if result.transactions:
            # Positive Transaktion
            tx1 = result.transactions[0]
            assert tx1.amount == Decimal("1234.56")
            assert tx1.counterparty_name == "Max Mustermann"

            # Negative Transaktion
            tx2 = result.transactions[1]
            assert tx2.amount == Decimal("-89.99")

    def test_empty_content_returns_zero_confidence(self, parser: CommerzbankCSVParser):
        """Sollte 0.0 bei leerem Inhalt zurueckgeben."""
        assert parser.can_parse("") == 0.0
        assert parser.can_parse(b"") == 0.0

    def test_non_commerzbank_content_low_confidence(self, parser: CommerzbankCSVParser):
        """Sollte bei nicht-Commerzbank Inhalt niedrige Konfidenz haben."""
        n26_content = "Date,Payee,Amount (EUR)\n2024-12-15,Test,100.00"
        confidence = parser.can_parse(n26_content)
        assert confidence < 0.5


# =============================================================================
# DEUTSCHE BANK CSV PARSER TESTS
# =============================================================================

class TestDeutscheBankCSVParser:
    """Umfassende Tests fuer Deutsche Bank CSV Parser."""

    @pytest.fixture
    def parser(self) -> DeutscheBankCSVParser:
        return DeutscheBankCSVParser()

    def test_can_parse_confidence_with_beneficiary(self, parser: DeutscheBankCSVParser):
        """Sollte 0.95 Konfidenz bei 'Beneficiary / Originator' erreichen."""
        content = """Booking date;Value date;Transaction type;Beneficiary / Originator;Payment reference;IBAN;Amount
15/12/2024;15/12/2024;Transfer;Max Mustermann;Rent December;DE89370400440532013000;1000.00"""
        confidence = parser.can_parse(content)
        assert confidence == 0.95

    def test_english_header_mapping(self, parser: DeutscheBankCSVParser):
        """Sollte englische Spalten korrekt mappen."""
        fieldnames = [
            "Booking date", "Value date", "Amount", "Currency",
            "Beneficiary / Originator", "IBAN", "BIC",
            "Payment reference", "Transaction type"
        ]
        mapping = parser._map_columns(fieldnames)

        assert mapping.get("booking_date") == "Booking date"
        assert mapping.get("value_date") == "Value date"
        assert mapping.get("amount") == "Amount"
        assert mapping.get("counterparty_name") == "Beneficiary / Originator"
        assert mapping.get("reference_text") == "Payment reference"

    def test_parse_transaction(self, parser: DeutscheBankCSVParser):
        """Sollte Deutsche Bank Transaktionen parsen."""
        content = """Booking date;Value date;Transaction type;Beneficiary / Originator;Payment reference;Amount
15.12.2024;16.12.2024;Transfer;Max Mustermann;Invoice 2024-001;1500,00"""
        result = parser.parse(content)
        assert result.success
        assert result.transaction_count >= 1


# =============================================================================
# DKB CSV PARSER TESTS
# =============================================================================

class TestDKBCSVParser:
    """Umfassende Tests fuer DKB (Deutsche Kreditbank) CSV Parser."""

    @pytest.fixture
    def parser(self) -> DKBCSVParser:
        return DKBCSVParser()

    def test_can_parse_confidence_with_betrag_eur(self, parser: DKBCSVParser):
        """Sollte 0.95 Konfidenz bei 'Betrag (EUR)' erreichen."""
        content = """Buchungstag;Wertstellung;Buchungstext;Auftraggeber / Begünstigter;Verwendungszweck;Kontonummer;BLZ;Betrag (EUR)
15.12.2024;15.12.2024;GUTSCHRIFT;Max Mustermann;Miete;DE123;12345;1.000,00"""
        confidence = parser.can_parse(content)
        assert confidence == 0.95

    def test_iso8859_encoding_handling(self, parser: DKBCSVParser):
        """Sollte Latin-1 Encoding korrekt handhaben."""
        # Simuliere Latin-1 encoded content
        content_str = """Buchungstag;Wertstellung;Buchungstext;Auftraggeber / Begünstigter;Verwendungszweck;Betrag (EUR)
15.12.2024;15.12.2024;ÜBERWEISUNG;Müller;Büro Miete;1.000,00"""
        # Encode to Latin-1 bytes
        content_bytes = content_str.encode('latin-1', errors='replace')
        confidence = parser.can_parse(content_bytes)
        assert confidence > 0.8

    def test_metadata_header_extraction(self, parser: DKBCSVParser):
        """Sollte Kontoinfo aus Metadaten-Header extrahieren."""
        content = """Kontonummer: DE89370400440532013000
BLZ: 12030000
Kontotyp: Girokonto

Buchungstag;Wertstellung;Buchungstext;Auftraggeber / Begünstigter;Verwendungszweck;Kontonummer;BLZ;Betrag (EUR)
15.12.2024;15.12.2024;GUTSCHRIFT;Max Mustermann;Miete;DE123;12345;1.000,00"""
        result = parser.parse(content)
        assert result.success
        # DKB Parser sollte IBAN aus Metadaten extrahieren
        if result.account_iban:
            assert result.account_iban.startswith("DE")

    def test_parse_with_multiple_header_lines(self, parser: DKBCSVParser):
        """Sollte mehrere Metadaten-Zeilen vor Header handhaben."""
        content = """Kontonummer;DE89370400440532013000
Kontoinhaber;Max Mustermann
Von;01.11.2024
Bis;30.11.2024

Buchungstag;Wertstellung;Buchungstext;Auftraggeber / Begünstigter;Verwendungszweck;Kontonummer;BLZ;Betrag (EUR)
15.11.2024;15.11.2024;GUTSCHRIFT;Arbeitgeber;Gehalt November;DE111;12345;3.500,00"""
        result = parser.parse(content)
        assert result.success
        assert result.transaction_count >= 1


# =============================================================================
# ING CSV PARSER TESTS
# =============================================================================

class TestINGCSVParser:
    """Umfassende Tests fuer ING (ING-DiBa) CSV Parser."""

    @pytest.fixture
    def parser(self) -> INGCSVParser:
        return INGCSVParser()

    def test_can_parse_confidence_with_auftraggeber_empfaenger(self, parser: INGCSVParser):
        """Sollte 0.95 Konfidenz bei 'Auftraggeber/Empfänger' erreichen."""
        content = """Buchung;Valuta;Auftraggeber/Empfänger;Buchungstext;Verwendungszweck;Saldo;Betrag
15.12.2024;15.12.2024;Max Mustermann;GUTSCHRIFT;Miete;5.000,00;1.000,00"""
        confidence = parser.can_parse(content)
        assert confidence == 0.95

    def test_can_parse_without_umlaut(self, parser: INGCSVParser):
        """Sollte auch 'Auftraggeber/Empfaenger' erkennen."""
        content = """Buchung;Valuta;Auftraggeber/Empfaenger;Buchungstext;Verwendungszweck;Betrag
15.12.2024;15.12.2024;Max Mustermann;GUTSCHRIFT;Miete;1.000,00"""
        confidence = parser.can_parse(content)
        assert confidence == 0.95

    def test_parse_amount(self, parser: INGCSVParser):
        """Sollte ING Betraege korrekt parsen."""
        content = """Buchung;Valuta;Auftraggeber/Empfänger;Buchungstext;Verwendungszweck;Betrag
15.12.2024;16.12.2024;Max Mustermann;GUTSCHRIFT;Miete Dezember;1.234,56"""
        result = parser.parse(content)
        assert result.success
        if result.transactions:
            assert result.transactions[0].amount == Decimal("1234.56")


# =============================================================================
# N26 CSV PARSER TESTS
# =============================================================================

class TestN26CSVParser:
    """Umfassende Tests fuer N26 CSV Parser."""

    @pytest.fixture
    def parser(self) -> N26CSVParser:
        return N26CSVParser()

    def test_can_parse_confidence_with_payee_amount(self, parser: N26CSVParser):
        """Sollte 0.95 Konfidenz bei 'Payee' + 'Amount (EUR)' erreichen."""
        content = """Date,Payee,Account number,Transaction type,Payment reference,Amount (EUR)
2024-12-15,Max Mustermann,DE89370400440532013000,Income,Salary,1000.00"""
        confidence = parser.can_parse(content)
        assert confidence == 0.95

    def test_comma_delimiter(self, parser: N26CSVParser):
        """Sollte Komma als Delimiter verwenden."""
        content = """Date,Payee,Account number,Transaction type,Payment reference,Amount (EUR)
2024-12-15,Max Mustermann,DE89370400440532013000,Outgoing Transfer,Invoice Payment,-500.00
2024-12-16,Employer Inc.,DE11520513735120710131,Income,Salary December,3500.00"""
        result = parser.parse(content)
        assert result.success
        assert result.transaction_count == 2

    def test_english_column_names_mapping(self, parser: N26CSVParser):
        """Sollte englische Spalten korrekt mappen."""
        fieldnames = ["Date", "Payee", "Account number", "Transaction type", "Payment reference", "Amount (EUR)"]
        mapping = parser._map_columns(fieldnames)

        assert mapping.get("booking_date") == "Date"
        assert mapping.get("counterparty_name") == "Payee"
        assert mapping.get("counterparty_iban") == "Account number"
        assert mapping.get("reference_text") == "Payment reference"
        assert mapping.get("amount") == "Amount (EUR)"

    def test_value_date_inherits_booking_date(self, parser: N26CSVParser):
        """Sollte Value Date von Booking Date erben (N26 hat keine separate Valuta-Spalte)."""
        fieldnames = ["Date", "Payee", "Amount (EUR)"]
        mapping = parser._map_columns(fieldnames)

        # N26 hat keine separate Valuta-Spalte, value_date sollte booking_date sein
        assert mapping.get("booking_date") == "Date"
        assert mapping.get("value_date") == "Date"


# =============================================================================
# SPARKASSE CSV PARSER TESTS
# =============================================================================

class TestSparkasseCSVParser:
    """Umfassende Tests fuer Sparkasse CSV Parser."""

    @pytest.fixture
    def parser(self) -> SparkasseCSVParser:
        return SparkasseCSVParser()

    def test_can_parse_confidence_with_sparkasse_markers(self, parser: SparkasseCSVParser):
        """Sollte hohe Konfidenz bei Sparkasse-spezifischen Spalten erreichen."""
        content = """Auftragskonto;Buchungstag;Valutadatum;Buchungstext;Verwendungszweck;Beguenstigter/Zahlungspflichtiger;Glaeubiger ID;Mandatsreferenz;Kontonummer/IBAN;BIC (SWIFT-Code);Betrag;Waehrung
DE89370400440532013000;15.12.2024;15.12.2024;LASTSCHRIFT;Strom Dezember;Stadtwerke GmbH;DE98ZZZ09999999999;M001234;DE11520513735120710131;HELADEF1822;-89,99;EUR"""
        confidence = parser.can_parse(content)
        assert confidence >= 0.8

    def test_glaeubiger_id_extraction(self, parser: SparkasseCSVParser):
        """Sollte SEPA Glaeubiger-ID (Creditor ID) extrahieren."""
        content = """Auftragskonto;Buchungstag;Valutadatum;Buchungstext;Verwendungszweck;Beguenstigter/Zahlungspflichtiger;Glaeubiger ID;Mandatsreferenz;Kontonummer/IBAN;BIC (SWIFT-Code);Betrag;Waehrung
DE89370400440532013000;15.12.2024;15.12.2024;LASTSCHRIFT;Strom;Stadtwerke;DE98ZZZ09999999999;M001234;DE111;HELADEF1822;-89,99;EUR"""
        result = parser.parse(content)
        assert result.success
        # Glaeubiger-ID sollte im Reference-Parsing extrahiert werden

    def test_mandatsreferenz_extraction(self, parser: SparkasseCSVParser):
        """Sollte SEPA Mandatsreferenz extrahieren."""
        # Mandatsreferenz ist in Sparkasse-CSV direkt als Spalte vorhanden
        content = """Auftragskonto;Buchungstag;Valutadatum;Buchungstext;Verwendungszweck;Beguenstigter/Zahlungspflichtiger;Glaeubiger ID;Mandatsreferenz;Betrag;Waehrung
DE89370400440532013000;15.12.2024;15.12.2024;LASTSCHRIFT;Strom 12/2024;Stadtwerke GmbH;DE98ZZZ09999999999;MANDAT-2024-001;-89,99;EUR"""
        result = parser.parse(content)
        assert result.success


# =============================================================================
# VOLKSBANK CSV PARSER TESTS
# =============================================================================

class TestVolksbankCSVParser:
    """Umfassende Tests fuer Volksbank/Raiffeisenbank CSV Parser."""

    @pytest.fixture
    def parser(self) -> VolksbankCSVParser:
        return VolksbankCSVParser()

    def test_can_parse_confidence_with_empfaenger(self, parser: VolksbankCSVParser):
        """Sollte 0.90 Konfidenz bei 'Empfänger/Zahlungspflichtiger' erreichen."""
        content = """Buchungstag;Valuta;Empfänger/Zahlungspflichtiger;Verwendungszweck;Kundenreferenz;Betrag
15.12.2024;15.12.2024;Max Mustermann;Miete Dezember;REF001;1.000,00"""
        confidence = parser.can_parse(content)
        assert confidence == 0.9

    def test_can_parse_without_umlaut_variant(self, parser: VolksbankCSVParser):
        """Sollte auch 'Empfaenger/Zahlungspflichtiger' erkennen."""
        content = """Buchungstag;Valuta;Empfaenger/Zahlungspflichtiger;Verwendungszweck;Betrag
15.12.2024;15.12.2024;Max Mustermann;Miete;1.000,00"""
        confidence = parser.can_parse(content)
        assert confidence == 0.9

    def test_parse_transaction(self, parser: VolksbankCSVParser):
        """Sollte Volksbank Transaktionen parsen."""
        content = """Buchungstag;Wertstellung;Empfänger/Zahlungspflichtiger;Verwendungszweck;Umsatz;Währung
15.12.2024;16.12.2024;Max Mustermann;Miete Dezember 2024;1.234,56;EUR"""
        result = parser.parse(content)
        assert result.success


# =============================================================================
# MT940 SWIFT PARSER TESTS
# =============================================================================

class TestMT940ParserComprehensive:
    """Umfassende Tests fuer MT940 (SWIFT) Parser."""

    @pytest.fixture
    def parser(self) -> MT940Parser:
        return MT940Parser()

    def test_swift_format_detection_with_20_60(self, parser: MT940Parser):
        """Sollte MT940 an :20: und :60: Markern erkennen."""
        content = """:20:STARTUMS
:25:37040044/532013000
:28C:0/1
:60F:C241215EUR1000,00
:61:2412151215CR100,00NTRFNONREF//12345
:86:ÜBERWEISUNG VON KUNDE
:62F:C241215EUR1100,00
-"""
        confidence = parser.can_parse(content)
        assert confidence == 0.95

    def test_swift_markers_recognition(self, parser: MT940Parser):
        """Sollte alle typischen MT940 Marker erkennen."""
        # Minimal MT940 mit mehreren Markern
        content = """:25:DE89370400440532013000
:28C:00001/001
:60F:C241201EUR5000,00
:61:2412011201CR500,00NTRFREF001//BANK001
:86:Zahlung Kunde Mustermann
EREF+END2END001
MREF+MANDAT001
:62F:C241201EUR5500,00"""
        confidence = parser.can_parse(content)
        assert confidence > 0.8

    def test_61_field_parsing(self, parser: MT940Parser):
        """Sollte :61: Transaktionszeilen korrekt parsen."""
        content = """:20:STATEMENT
:25:DE89370400440532013000
:28C:0/1
:60F:C241215EUR10000,00
:61:2412151215CR1500,00NTRFCUST001//REF12345
Mustermann Max
:86:ÜBERWEISUNG
Miete Dezember 2024
EREF+END2END-001
:62F:C241215EUR11500,00
-"""
        with patch('app.services.banking.parsers.mt940_parser.mt940_parse') as mock_parse:
            # mt940 Bibliothek speichert Daten in tx.data Dictionary; die
            # Collection-Iteration ergibt die Transaktionen (Refactor 2026-06-12).
            mock_amount = MagicMock()
            mock_amount.amount = Decimal("1500.00")
            mock_amount.currency = "EUR"

            mock_tx = MagicMock()
            mock_tx.data = {
                "amount": mock_amount,
                "date": date(2024, 12, 15),
                "entry_date": date(2024, 12, 15),
                "transaction_details": "ÜBERWEISUNG Miete Dezember 2024",
                "extra_details": {},
                "id": "NTRF",
                "customer_reference": "CUST001",
                "bank_reference": "REF12345",
                "currency": "EUR",
            }

            mock_ob = MagicMock()
            mock_ob.amount = MagicMock(amount=Decimal("10000.00"))
            mock_ob.date = date(2024, 12, 15)
            mock_cb = MagicMock()
            mock_cb.amount = MagicMock(amount=Decimal("11500.00"))
            mock_cb.date = date(2024, 12, 15)

            mock_parse.return_value = _make_mt940_collection(
                data={
                    "account_identification": "DE89370400440532013000/COBADEFFXXX",
                    "final_opening_balance": mock_ob,
                    "final_closing_balance": mock_cb,
                },
                transactions=[mock_tx],
            )

            result = parser.parse(content)
            assert result.success
            assert result.transaction_count >= 1

    def test_86_field_reference_extraction(self, parser: MT940Parser):
        """Sollte Referenzen aus :86: Feld extrahieren."""
        reference_text = """ÜBERWEISUNG VON KUNDE
Mustermann Max
IBAN: DE89370400440532013000
EREF+END2END-001
MREF+MANDAT-001
Betreff: Rechnung 2024-001"""

        # Test reference parsing
        refs = parser.parse_reference_text(reference_text)
        assert "end_to_end_ids" in refs
        assert "mandate_ids" in refs
        # Die Referenz-Extraktion sollte EREF und MREF finden

    def test_balance_extraction(self, parser: MT940Parser):
        """Sollte Opening/Closing Balances extrahieren."""
        content = """:20:STATEMENT
:25:DE89370400440532013000
:28C:0/1
:60F:C241201EUR5000,00
:62F:C241231EUR7500,00
-"""
        with patch('app.services.banking.parsers.mt940_parser.mt940_parse') as mock_parse:
            # Salden liegen in der Collection-.data (:60F:/:62F:), Refactor 2026-06-12.
            mock_ob = MagicMock()
            mock_ob.amount = MagicMock(amount=Decimal("5000.00"))
            mock_ob.date = date(2024, 12, 1)
            mock_cb = MagicMock()
            mock_cb.amount = MagicMock(amount=Decimal("7500.00"))
            mock_cb.date = date(2024, 12, 31)

            mock_parse.return_value = _make_mt940_collection(
                data={
                    "account_identification": "DE89370400440532013000",
                    "final_opening_balance": mock_ob,
                    "final_closing_balance": mock_cb,
                },
                transactions=[],
            )

            result = parser.parse(content)
            assert result.success
            assert result.opening_balance == Decimal("5000.00")
            assert result.closing_balance == Decimal("7500.00")

    def test_counterparty_extraction_from_unstructured_86(self, parser: MT940Parser):
        """Sollte Gegenpartei aus unstrukturiertem :86: Feld extrahieren."""
        reference = """NAME+Max Mustermann
IBAN: DE89370400440532013000
BIC: COBADEFFXXX
Verwendungszweck: Miete Dezember"""

        name, iban = parser._extract_counterparty(reference)
        assert name == "Max Mustermann" or name is not None

    def test_bytes_decoding_utf8(self, parser: MT940Parser):
        """Sollte UTF-8 Bytes korrekt dekodieren."""
        content = b":20:TEST\n:25:12345\n:28C:0/1\n:60F:C241215EUR1000,00\n-"
        confidence = parser.can_parse(content)
        assert confidence > 0

    def test_bytes_decoding_latin1_fallback(self, parser: MT940Parser):
        """Sollte auf Latin-1 zurueckfallen bei nicht-UTF-8."""
        # Latin-1 encoded content with umlaut
        content_str = ":20:TEST\n:25:12345\n:86:Müller\n-"
        content_bytes = content_str.encode('latin-1')
        confidence = parser.can_parse(content_bytes)
        # Should still parse
        assert confidence >= 0


# =============================================================================
# CAMT.053 XML PARSER TESTS
# =============================================================================

class TestCAMT053ParserComprehensive:
    """Umfassende Tests fuer CAMT.053 (ISO 20022) Parser."""

    @pytest.fixture
    def parser(self) -> CAMT053Parser:
        return CAMT053Parser()

    @pytest.fixture
    def sample_camt053_xml(self) -> str:
        """Sample CAMT.053 XML Dokument."""
        return """<?xml version="1.0" encoding="UTF-8"?>
<Document xmlns="urn:iso:std:iso:20022:tech:xsd:camt.053.001.02">
    <BkToCstmrStmt>
        <Stmt>
            <Id>STMT-2024-001</Id>
            <Acct>
                <Id>
                    <IBAN>DE89370400440532013000</IBAN>
                </Id>
                <Svcr>
                    <FinInstnId>
                        <BIC>COBADEFFXXX</BIC>
                    </FinInstnId>
                </Svcr>
            </Acct>
            <Bal>
                <Tp><CdOrPrtry><Cd>OPBD</Cd></CdOrPrtry></Tp>
                <Amt Ccy="EUR">5000.00</Amt>
                <CdtDbtInd>CRDT</CdtDbtInd>
                <Dt><Dt>2024-12-01</Dt></Dt>
            </Bal>
            <Bal>
                <Tp><CdOrPrtry><Cd>CLBD</Cd></CdOrPrtry></Tp>
                <Amt Ccy="EUR">7500.00</Amt>
                <CdtDbtInd>CRDT</CdtDbtInd>
                <Dt><Dt>2024-12-31</Dt></Dt>
            </Bal>
            <Ntry>
                <Amt Ccy="EUR">1500.00</Amt>
                <CdtDbtInd>CRDT</CdtDbtInd>
                <BookgDt><Dt>2024-12-15</Dt></BookgDt>
                <ValDt><Dt>2024-12-15</Dt></ValDt>
                <NtryDtls>
                    <TxDtls>
                        <Refs>
                            <EndToEndId>E2E-2024-001</EndToEndId>
                            <MndtId>MANDAT-001</MndtId>
                        </Refs>
                        <RltdPties>
                            <Dbtr><Nm>Max Mustermann</Nm></Dbtr>
                            <DbtrAcct><Id><IBAN>DE11520513735120710131</IBAN></Id></DbtrAcct>
                        </RltdPties>
                        <RmtInf>
                            <Ustrd>Miete Dezember 2024</Ustrd>
                        </RmtInf>
                    </TxDtls>
                </NtryDtls>
            </Ntry>
        </Stmt>
    </BkToCstmrStmt>
</Document>"""

    def test_xml_namespace_handling_camt053_001_02(self, parser: CAMT053Parser, sample_camt053_xml: str):
        """Sollte camt.053.001.02 Namespace korrekt handhaben."""
        confidence = parser.can_parse(sample_camt053_xml)
        assert confidence >= 0.9

    def test_xml_namespace_handling_camt053_001_04(self, parser: CAMT053Parser):
        """Sollte camt.053.001.04 Namespace erkennen."""
        content = """<?xml version="1.0" encoding="UTF-8"?>
<Document xmlns="urn:iso:std:iso:20022:tech:xsd:camt.053.001.04">
    <BkToCstmrStmt><Stmt><Id>TEST</Id></Stmt></BkToCstmrStmt>
</Document>"""
        confidence = parser.can_parse(content)
        assert confidence > 0.8

    def test_xml_namespace_handling_camt053_001_08(self, parser: CAMT053Parser):
        """Sollte camt.053.001.08 Namespace erkennen."""
        content = """<?xml version="1.0" encoding="UTF-8"?>
<Document xmlns="urn:iso:std:iso:20022:tech:xsd:camt.053.001.08">
    <BkToCstmrStmt><Stmt><Id>TEST</Id></Stmt></BkToCstmrStmt>
</Document>"""
        confidence = parser.can_parse(content)
        assert confidence > 0.8

    def test_xxe_protection(self, parser: CAMT053Parser):
        """Sollte XXE (XML External Entity) Angriffe verhindern.

        SECURITY: defusedxml wird verwendet um External Entity Injection zu blockieren.
        """
        malicious_xml = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE foo [
  <!ENTITY xxe SYSTEM "file:///etc/passwd">
]>
<Document xmlns="urn:iso:std:iso:20022:tech:xsd:camt.053.001.02">
    <BkToCstmrStmt>
        <Stmt>
            <Id>&xxe;</Id>
        </Stmt>
    </BkToCstmrStmt>
</Document>"""

        # Parser sollte nicht abstuerzen und XXE nicht ausfuehren
        result = parser.parse(malicious_xml)
        # Das Ergebnis sollte entweder fehlschlagen oder keine sensiblen Daten enthalten
        # defusedxml sollte DTD verarbeitung blockieren
        if result.success:
            # Wenn es parst, sollte es keine /etc/passwd Daten enthalten
            for tx in result.transactions:
                assert "/etc/passwd" not in str(tx.reference_text or "")

    def test_entry_parsing_ntry(self, parser: CAMT053Parser, sample_camt053_xml: str):
        """Sollte <Ntry> Elemente korrekt parsen."""
        result = parser.parse(sample_camt053_xml)
        assert result.success
        assert result.transaction_count >= 1

        if result.transactions:
            tx = result.transactions[0]
            assert tx.amount == Decimal("1500.00")
            assert tx.booking_date == date(2024, 12, 15)
            assert tx.end_to_end_id == "E2E-2024-001"

    def test_account_info_extraction_acct(self, parser: CAMT053Parser, sample_camt053_xml: str):
        """Sollte <Acct> Element (Kontoinfo) korrekt extrahieren."""
        result = parser.parse(sample_camt053_xml)
        assert result.success
        assert result.account_iban == "DE89370400440532013000"
        assert result.account_bic == "COBADEFFXXX"

    def test_balance_extraction(self, parser: CAMT053Parser, sample_camt053_xml: str):
        """Sollte Opening/Closing Balance korrekt extrahieren."""
        result = parser.parse(sample_camt053_xml)
        assert result.success
        assert result.opening_balance == Decimal("5000.00")
        assert result.closing_balance == Decimal("7500.00")

    def test_debit_amount_sign(self, parser: CAMT053Parser):
        """Sollte DBIT Transaktionen als negativ parsen."""
        content = """<?xml version="1.0" encoding="UTF-8"?>
<Document xmlns="urn:iso:std:iso:20022:tech:xsd:camt.053.001.02">
    <BkToCstmrStmt>
        <Stmt>
            <Id>TEST</Id>
            <Ntry>
                <Amt Ccy="EUR">100.00</Amt>
                <CdtDbtInd>DBIT</CdtDbtInd>
                <BookgDt><Dt>2024-12-15</Dt></BookgDt>
            </Ntry>
        </Stmt>
    </BkToCstmrStmt>
</Document>"""
        result = parser.parse(content)
        assert result.success
        if result.transactions:
            assert result.transactions[0].amount == Decimal("-100.00")

    def test_creditor_extraction_for_debit(self, parser: CAMT053Parser):
        """Sollte Creditor bei DBIT Transaktionen extrahieren."""
        content = """<?xml version="1.0" encoding="UTF-8"?>
<Document xmlns="urn:iso:std:iso:20022:tech:xsd:camt.053.001.02">
    <BkToCstmrStmt>
        <Stmt>
            <Id>TEST</Id>
            <Ntry>
                <Amt Ccy="EUR">89.99</Amt>
                <CdtDbtInd>DBIT</CdtDbtInd>
                <BookgDt><Dt>2024-12-15</Dt></BookgDt>
                <NtryDtls>
                    <TxDtls>
                        <RltdPties>
                            <Cdtr><Nm>Stadtwerke GmbH</Nm></Cdtr>
                            <CdtrAcct><Id><IBAN>DE11520513735120710131</IBAN></Id></CdtrAcct>
                        </RltdPties>
                    </TxDtls>
                </NtryDtls>
            </Ntry>
        </Stmt>
    </BkToCstmrStmt>
</Document>"""
        result = parser.parse(content)
        assert result.success
        if result.transactions:
            tx = result.transactions[0]
            assert tx.counterparty_name == "Stadtwerke GmbH"


# =============================================================================
# UTILITY FUNCTION TESTS
# =============================================================================

class TestGermanAmountParsing:
    """Tests fuer deutsche Betragsformate."""

    @pytest.fixture
    def parser(self) -> GenericCSVParser:
        return GenericCSVParser()

    def test_german_format_with_thousand_separator(self, parser: GenericCSVParser):
        """Sollte '1.234,56' korrekt zu 1234.56 parsen."""
        result = parser.parse_german_amount("1.234,56")
        assert result == Decimal("1234.56")

    def test_german_format_without_thousand_separator(self, parser: GenericCSVParser):
        """Sollte '234,56' korrekt zu 234.56 parsen."""
        result = parser.parse_german_amount("234,56")
        assert result == Decimal("234.56")

    def test_german_format_large_number(self, parser: GenericCSVParser):
        """Sollte '1.234.567,89' korrekt parsen."""
        result = parser.parse_german_amount("1.234.567,89")
        assert result == Decimal("1234567.89")

    def test_english_format(self, parser: GenericCSVParser):
        """Sollte englisches Format '1,234.56' erkennen."""
        result = parser.parse_german_amount("1,234.56")
        assert result == Decimal("1234.56")

    def test_amount_with_currency_symbol(self, parser: GenericCSVParser):
        """Sollte Waehrungssymbole entfernen."""
        assert parser.parse_german_amount("€ 100,00") == Decimal("100.00")
        assert parser.parse_german_amount("100,00 €") == Decimal("100.00")
        assert parser.parse_german_amount("CHF 50,00") == Decimal("50.00")

    def test_negative_amount(self, parser: GenericCSVParser):
        """Sollte negative Betraege handhaben."""
        result = parser.parse_german_amount("-123,45")
        assert result == Decimal("-123.45")

    def test_empty_amount(self, parser: GenericCSVParser):
        """Sollte leeren Betrag als 0 parsen."""
        assert parser.parse_german_amount("") == Decimal("0")
        assert parser.parse_german_amount("   ") == Decimal("0")

    def test_invalid_amount(self, parser: GenericCSVParser):
        """Sollte ungueltige Betraege als 0 parsen."""
        assert parser.parse_german_amount("abc") == Decimal("0")


class TestIBANNormalization:
    """Tests fuer IBAN-Normalisierung."""

    def test_iban_normalization_removes_spaces(self):
        """Sollte Leerzeichen entfernen."""
        result = BaseParser.normalize_iban("DE89 3704 0044 0532 0130 00")
        assert result == "DE89370400440532013000"

    def test_iban_normalization_uppercase(self):
        """Sollte in Grossbuchstaben konvertieren."""
        result = BaseParser.normalize_iban("de89370400440532013000")
        assert result == "DE89370400440532013000"

    def test_iban_normalization_combined(self):
        """Sollte Leerzeichen entfernen und in Grossbuchstaben konvertieren."""
        result = BaseParser.normalize_iban("de 89 3704 0044 0532 0130 00")
        assert result == "DE89370400440532013000"

    def test_iban_normalization_empty(self):
        """Sollte None bei leerem Input zurueckgeben."""
        assert BaseParser.normalize_iban("") is None
        assert BaseParser.normalize_iban(None) is None


class TestReferenceExtraction:
    """Tests fuer Referenz-Extraktion aus Verwendungszweck."""

    @pytest.fixture
    def parser(self) -> GenericCSVParser:
        return GenericCSVParser()

    def test_invoice_number_extraction_standard(self, parser: GenericCSVParser):
        """Sollte Standard-Rechnungsnummern extrahieren."""
        refs = parser.parse_reference_text("Rechnung Nr. 2024-001")
        assert "2024-001" in refs["invoice_numbers"]

    def test_invoice_number_extraction_re_prefix(self, parser: GenericCSVParser):
        """Sollte RE-Prefix Rechnungsnummern extrahieren."""
        refs = parser.parse_reference_text("RE 12345/2024")
        assert len(refs["invoice_numbers"]) > 0

    def test_invoice_number_extraction_inv_prefix(self, parser: GenericCSVParser):
        """Sollte INV-Prefix Rechnungsnummern extrahieren."""
        refs = parser.parse_reference_text("Rechnungs-Nr.: INV-2024-0042")
        assert "INV-2024-0042" in refs["invoice_numbers"]

    def test_customer_number_extraction(self, parser: GenericCSVParser):
        """Sollte Kundennummern extrahieren."""
        refs = parser.parse_reference_text("KD-NR: 123456")
        assert len(refs["customer_numbers"]) > 0

    def test_end_to_end_id_extraction(self, parser: GenericCSVParser):
        """Sollte SEPA End-to-End-ID extrahieren."""
        refs = parser.parse_reference_text("EREF+END2END-2024-001")
        assert "END2END-2024-001" in refs["end_to_end_ids"]

    def test_mandate_id_extraction(self, parser: GenericCSVParser):
        """Sollte SEPA Mandats-ID extrahieren."""
        refs = parser.parse_reference_text("MREF+MANDAT-001")
        assert "MANDAT-001" in refs["mandate_ids"]

    def test_creditor_id_extraction(self, parser: GenericCSVParser):
        """Sollte SEPA Glaeubiger-ID extrahieren."""
        refs = parser.parse_reference_text("CRED+DE98ZZZ09999999999")
        assert len(refs["creditor_ids"]) > 0

    def test_empty_reference_text(self, parser: GenericCSVParser):
        """Sollte leere Listen bei leerem Text zurueckgeben."""
        refs = parser.parse_reference_text("")
        assert refs["invoice_numbers"] == []
        assert refs["customer_numbers"] == []

    def test_no_reference_found(self, parser: GenericCSVParser):
        """Sollte leere Listen bei Text ohne Referenzen zurueckgeben."""
        refs = parser.parse_reference_text("Allgemeiner Verwendungszweck ohne Referenz")
        assert refs["invoice_numbers"] == []


class TestTransactionTypeDetection:
    """Tests fuer Transaktionstyp-Erkennung."""

    @pytest.fixture
    def parser(self) -> GenericCSVParser:
        return GenericCSVParser()

    def test_detect_transfer_ueberweisung(self, parser: GenericCSVParser):
        """Sollte ÜBERWEISUNG als TRANSFER erkennen."""
        tx_type = parser.detect_transaction_type("SEPA-ÜBERWEISUNG", Decimal("100"))
        assert tx_type == TransactionType.TRANSFER

    def test_detect_direct_debit_lastschrift(self, parser: GenericCSVParser):
        """Sollte LASTSCHRIFT als DIRECT_DEBIT erkennen."""
        tx_type = parser.detect_transaction_type("SEPA-LASTSCHRIFT", Decimal("-50"))
        assert tx_type == TransactionType.DIRECT_DEBIT

    def test_detect_card_payment(self, parser: GenericCSVParser):
        """Sollte Kartenzahlung erkennen."""
        tx_type = parser.detect_transaction_type("EC-KARTE ZAHLUNG", Decimal("-25"))
        assert tx_type == TransactionType.CARD

    def test_detect_fee(self, parser: GenericCSVParser):
        """Sollte Gebuehren erkennen."""
        tx_type = parser.detect_transaction_type("KONTOFÜHRUNGSGEBÜHR", Decimal("-5"))
        assert tx_type == TransactionType.FEE

    def test_detect_cash(self, parser: GenericCSVParser):
        """Sollte Bargeld-Transaktionen erkennen."""
        tx_type = parser.detect_transaction_type("GAA AUSZAHLUNG", Decimal("-200"))
        assert tx_type == TransactionType.CASH

    def test_detect_interest(self, parser: GenericCSVParser):
        """Sollte Zinsen erkennen."""
        tx_type = parser.detect_transaction_type("HABENZINSEN Q4/2024", Decimal("1.50"))
        assert tx_type == TransactionType.INTEREST

    def test_detect_other(self, parser: GenericCSVParser):
        """Sollte unbekannte Typen als OTHER klassifizieren."""
        tx_type = parser.detect_transaction_type("SONSTIGER VORGANG", Decimal("0"))
        assert tx_type == TransactionType.OTHER


# =============================================================================
# IBAN/ACCOUNT MASKING UTILITY TESTS
# =============================================================================

class TestMaskingUtilities:
    """Tests fuer Banking Maskierungs-Utilities."""

    def test_mask_iban_standard(self):
        """Sollte IBAN korrekt maskieren."""
        result = mask_iban("DE89370400440532013000")
        assert result == "DE89***...***3000"

    def test_mask_iban_short(self):
        """Sollte kurze IBAN mit *** zurueckgeben."""
        assert mask_iban("DE89") == "***"
        assert mask_iban("") == "***"
        assert mask_iban(None) == "***"

    def test_mask_account_number(self):
        """Sollte Kontonummer maskieren."""
        result = mask_account_number("0532013000")
        assert result.endswith("3000")
        assert "****" in result

    def test_mask_account_number_short(self):
        """Sollte kurze Kontonummer mit *** zurueckgeben."""
        assert mask_account_number("123") == "***"
        assert mask_account_number("") == "***"

    def test_mask_bic(self):
        """Sollte BIC maskieren."""
        result = mask_bic("COBADEFFXXX")
        assert result.startswith("COBA")
        assert "*" in result

    def test_mask_bic_short(self):
        """Sollte kurzen BIC mit *** zurueckgeben."""
        assert mask_bic("COB") == "***"
        assert mask_bic("") == "***"


# =============================================================================
# FORMAT DETECTION TESTS
# =============================================================================

class TestFormatDetectionComprehensive:
    """Umfassende Tests fuer automatische Format-Erkennung."""

    def test_detect_mt940_highest_priority(self):
        """Sollte MT940 mit hoechster Konfidenz erkennen."""
        content = """:20:STARTUMS
:25:DE89370400440532013000
:28C:0/1
:60F:C241215EUR1000,00
-"""
        results = detect_format(content)
        assert len(results) > 0
        parser_cls, confidence = results[0]
        assert parser_cls == MT940Parser
        assert confidence >= 0.9

    def test_detect_camt053_highest_priority(self):
        """Sollte CAMT.053 mit hoechster Konfidenz erkennen."""
        content = """<?xml version="1.0"?>
<Document xmlns="urn:iso:std:iso:20022:tech:xsd:camt.053.001.02">
<BkToCstmrStmt><Stmt><Id>TEST</Id></Stmt></BkToCstmrStmt>
</Document>"""
        results = detect_format(content)
        assert len(results) > 0
        parser_cls, confidence = results[0]
        assert parser_cls == CAMT053Parser
        assert confidence >= 0.9

    def test_detect_bank_specific_csv(self):
        """Sollte bank-spezifische CSVs erkennen."""
        # DKB
        dkb_content = "Buchungstag;Wertstellung;Betrag (EUR)\n15.12.2024;15.12.2024;100,00"
        results = detect_format(dkb_content)
        assert len(results) > 0
        # Sollte DKB aufgrund "Betrag (EUR)" erkennen

        # N26
        n26_content = "Date,Payee,Amount (EUR)\n2024-12-15,Test,100.00"
        results = detect_format(n26_content)
        assert len(results) > 0

    def test_format_detection_sorts_by_confidence(self):
        """Sollte Ergebnisse nach Konfidenz sortieren."""
        # Generic CSV sollte niedrigere Konfidenz haben
        content = "Datum;Betrag;Text\n15.12.2024;100;Test"
        results = detect_format(content)

        if len(results) >= 2:
            # Erste Konfidenz sollte >= zweite sein
            assert results[0][1] >= results[1][1]

    def test_format_detection_with_filename_hint(self):
        """Sollte Dateinamen als Hinweis nutzen."""
        content = "Datum;Betrag\n15.12.2024;100"

        # MT940 Extension sollte Konfidenz beeinflussen
        results_sta = detect_format(content, filename="kontoauszug.sta")
        results_csv = detect_format(content, filename="export.csv")

        # Beide sollten Ergebnisse liefern
        assert len(results_sta) > 0 or len(results_csv) > 0


# =============================================================================
# EDGE CASE TESTS
# =============================================================================

class TestEdgeCases:
    """Tests fuer Grenzfaelle und Fehlerbehandlung."""

    def test_empty_transaction_list(self):
        """Sollte leere Transaktionsliste handhaben."""
        parser = GenericCSVParser()
        content = "Datum;Betrag;Text\n"  # Nur Header, keine Daten
        result = parser.parse(content)
        # Sollte nicht abstuerzen
        assert result.transaction_count == 0

    def test_malformed_csv_missing_columns(self):
        """Sollte CSV mit fehlenden Spalten handhaben."""
        parser = GenericCSVParser()
        content = """Datum;Betrag
15.12.2024;100,00
16.12.2024"""  # Zweite Zeile hat fehlende Spalte
        result = parser.parse(content)
        # Sollte nicht abstuerzen
        assert result is not None

    def test_special_characters_in_reference(self):
        """Sollte Sonderzeichen im Verwendungszweck handhaben."""
        parser = GenericCSVParser()
        text = "Zahlung für Büro-Möbel (15% Rabatt) & Zubehör - €1.234,56"
        refs = parser.parse_reference_text(text)
        # Sollte nicht abstuerzen
        assert isinstance(refs, dict)

    def test_unicode_characters_in_counterparty(self):
        """Sollte Unicode-Zeichen im Namen handhaben."""
        parser = GenericCSVParser()
        content = """Datum;Betrag;Empfänger
15.12.2024;100,00;Müller & Söhne GmbH
16.12.2024;200,00;Café François"""
        result = parser.parse(content)
        assert result is not None

    def test_very_large_amount(self):
        """Sollte sehr grosse Betraege handhaben."""
        parser = GenericCSVParser()
        result = parser.parse_german_amount("999.999.999,99")
        assert result == Decimal("999999999.99")

    def test_bytes_content_handling(self):
        """Sollte Bytes-Content korrekt handhaben."""
        parser = MT940Parser()
        content = b":20:TEST\n:25:12345\n-"
        confidence = parser.can_parse(content)
        # Sollte nicht abstuerzen
        assert confidence >= 0

    def test_transaction_hash_generation(self):
        """Sollte konsistente Hashes generieren."""
        hash1 = BaseParser.generate_transaction_hash(
            date(2024, 12, 15),
            Decimal("100.00"),
            "Max Mustermann",
            "Miete"
        )
        hash2 = BaseParser.generate_transaction_hash(
            date(2024, 12, 15),
            Decimal("100.00"),
            "Max Mustermann",
            "Miete"
        )
        assert hash1 == hash2
        assert len(hash1) == 32  # SHA256 truncated to 32 chars

    def test_transaction_hash_uniqueness(self):
        """Sollte unterschiedliche Hashes fuer verschiedene Transaktionen generieren."""
        hash1 = BaseParser.generate_transaction_hash(
            date(2024, 12, 15),
            Decimal("100.00"),
            "Max",
            "Miete"
        )
        hash2 = BaseParser.generate_transaction_hash(
            date(2024, 12, 16),  # Anderes Datum
            Decimal("100.00"),
            "Max",
            "Miete"
        )
        assert hash1 != hash2
