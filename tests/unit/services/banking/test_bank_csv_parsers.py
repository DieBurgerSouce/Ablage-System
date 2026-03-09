# -*- coding: utf-8 -*-
"""Tests fuer die bank-spezifischen CSV-Parser.

Testet alle 7 Bank-Parser:
- Sparkasse
- Commerzbank
- DKB (Deutsche Kreditbank)
- ING (ING-DiBa)
- Deutsche Bank
- N26
- Volksbank/Raiffeisenbank

Jeder Parser wird getestet auf:
- Format-Erkennung (can_parse)
- Spalten-Mapping (_map_columns)
- Vollstaendiges Parsing
- Bank-spezifische Besonderheiten
"""

import pytest
from datetime import date
from decimal import Decimal
from typing import Dict, List, Optional

from app.services.banking.parsers.bank_csv.sparkasse import SparkasseCSVParser
from app.services.banking.parsers.bank_csv.commerzbank import CommerzbankCSVParser
from app.services.banking.parsers.bank_csv.dkb import DKBCSVParser
from app.services.banking.parsers.bank_csv.ing import INGCSVParser
from app.services.banking.parsers.bank_csv.deutsche_bank import DeutscheBankCSVParser
from app.services.banking.parsers.bank_csv.n26 import N26CSVParser
from app.services.banking.parsers.bank_csv.volksbank import VolksbankCSVParser
from app.services.banking.parsers.base import ParseResult
from app.services.banking.models import ImportFormat, TransactionType


# =============================================================================
# Sparkasse
# =============================================================================

class TestSparkasseCSVParser:
    """Tests fuer den Sparkasse CSV-Parser."""

    SPARKASSE_HEADER = (
        '"Auftragskonto";"Buchungstag";"Valutadatum";"Buchungstext";'
        '"Verwendungszweck";"Glaeubiger ID";"Mandatsreferenz";'
        '"Kundenreferenz (End-to-End)";"Sammlerreferenz";'
        '"Lastschrift Ursprungsbetrag";"Auslagenersatz Ruecklastschrift";'
        '"Beg\u00fcnstigter/Zahlungspflichtiger";"Kontonummer/IBAN";'
        '"BIC (SWIFT-Code)";"Betrag";"W\u00e4hrung";"Info"'
    )

    SPARKASSE_ROW = (
        '"DE89370400440532013000";"15.03.2024";"16.03.2024";"Lastschrift";'
        '"Strom Maerz 2024";"DE98ZZZ09999999999";"MNDT-2024-001";'
        '"E2E-2024-001";"";"";"";"Stadtwerke Berlin";"DE02100500000024290661";'
        '"BELADEBEXXX";"-149,50";"EUR";"Umsatz gebucht"'
    )

    @pytest.fixture
    def parser(self) -> SparkasseCSVParser:
        return SparkasseCSVParser()

    def test_can_parse_sparkasse_header(self) -> None:
        """Erkennt Sparkasse-Format anhand der Spaltenbezeichnungen."""
        content = self.SPARKASSE_HEADER + "\n" + self.SPARKASSE_ROW + "\n"
        confidence = SparkasseCSVParser.can_parse(content)
        assert confidence >= 0.8

    def test_can_parse_no_sparkasse(self) -> None:
        """Erkennt Nicht-Sparkasse-Format."""
        content = "Date,Amount,Payee\n2024-01-01,-50.00,Test\n"
        assert SparkasseCSVParser.can_parse(content) == 0.0

    def test_can_parse_empty(self) -> None:
        """Gibt 0 bei leerem Inhalt zurueck."""
        assert SparkasseCSVParser.can_parse("") == 0.0

    def test_map_columns(self, parser: SparkasseCSVParser) -> None:
        """Mappt Sparkasse-spezifische Spalten korrekt."""
        fieldnames = [
            "Buchungstag", "Valutadatum", "Betrag", "W\u00e4hrung",
            "Beg\u00fcnstigter/Zahlungspflichtiger", "Kontonummer/IBAN",
            "BIC (SWIFT-Code)", "Verwendungszweck", "Buchungstext",
        ]
        mapping = parser._map_columns(fieldnames)

        assert mapping.get("booking_date") == "Buchungstag"
        assert mapping.get("value_date") == "Valutadatum"
        assert mapping.get("amount") == "Betrag"
        assert mapping.get("reference_text") == "Verwendungszweck"
        assert mapping.get("booking_text") == "Buchungstext"

    def test_parse_full_sparkasse_csv(self, parser: SparkasseCSVParser) -> None:
        """Parst vollstaendiges Sparkasse-CSV."""
        content = self.SPARKASSE_HEADER + "\n" + self.SPARKASSE_ROW + "\n"
        result = parser.parse(content)

        assert result.success is True
        assert len(result.transactions) == 1
        tx = result.transactions[0]
        assert tx.booking_date == date(2024, 3, 15)
        assert tx.amount == Decimal("-149.50")

    def test_parse_sparkasse_format_metadata(self, parser: SparkasseCSVParser) -> None:
        """Setzt korrektes Format und Variante."""
        assert parser.FORMAT == ImportFormat.CSV_SPARKASSE
        assert parser.FORMAT_VARIANT == "sparkasse"


# =============================================================================
# Commerzbank
# =============================================================================

class TestCommerzbankCSVParser:
    """Tests fuer den Commerzbank CSV-Parser."""

    COBA_HEADER = "Buchungstag;Wertstellung;Umsatzart;Buchungstext;Betrag;W\u00e4hrung;Auftraggeber / Beg\u00fcnstigter;IBAN;BIC"
    COBA_ROW = "15.03.2024;16.03.2024;Lastschrift;Strom;-149,50;EUR;Stadtwerke Berlin;DE02100500000024290661;BELADEBEXXX"

    @pytest.fixture
    def parser(self) -> CommerzbankCSVParser:
        return CommerzbankCSVParser()

    def test_can_parse_coba_header(self) -> None:
        """Erkennt Commerzbank-Format (Auftraggeber / Beg\u00fcnstigter)."""
        content = self.COBA_HEADER + "\n" + self.COBA_ROW + "\n"
        confidence = CommerzbankCSVParser.can_parse(content)
        assert confidence >= 0.85

    def test_can_parse_no_coba(self) -> None:
        """Erkennt Nicht-Commerzbank-Format."""
        content = "Datum;Betrag;Name\n01.01.2024;-50;Test\n"
        assert CommerzbankCSVParser.can_parse(content) == 0.0

    def test_can_parse_empty(self) -> None:
        """Gibt 0 bei leerem Inhalt zurueck."""
        assert CommerzbankCSVParser.can_parse("") == 0.0

    def test_can_parse_bom(self) -> None:
        """Erkennt Commerzbank-CSV mit UTF-8 BOM."""
        content = "\ufeff" + self.COBA_HEADER + "\n" + self.COBA_ROW + "\n"
        confidence = CommerzbankCSVParser.can_parse(content)
        assert confidence >= 0.85

    def test_map_columns(self, parser: CommerzbankCSVParser) -> None:
        """Mappt Commerzbank-spezifische Spalten korrekt."""
        fieldnames = [
            "Buchungstag", "Wertstellung", "Umsatzart", "Buchungstext",
            "Betrag", "W\u00e4hrung", "Auftraggeber / Beg\u00fcnstigter", "IBAN", "BIC",
        ]
        mapping = parser._map_columns(fieldnames)

        assert mapping.get("booking_date") == "Buchungstag"
        assert mapping.get("value_date") == "Wertstellung"
        assert mapping.get("amount") == "Betrag"
        assert mapping.get("booking_text") == "Umsatzart"
        assert mapping.get("reference_text") == "Buchungstext"

    def test_parse_full_coba_csv(self, parser: CommerzbankCSVParser) -> None:
        """Parst vollstaendiges Commerzbank-CSV."""
        content = self.COBA_HEADER + "\n" + self.COBA_ROW + "\n"
        result = parser.parse(content)

        assert result.success is True
        assert len(result.transactions) == 1
        tx = result.transactions[0]
        assert tx.amount == Decimal("-149.50")

    def test_parse_coba_format_metadata(self, parser: CommerzbankCSVParser) -> None:
        """Setzt korrektes Format und Variante."""
        assert parser.FORMAT == ImportFormat.CSV_COMMERZBANK
        assert parser.FORMAT_VARIANT == "commerzbank"


# =============================================================================
# DKB
# =============================================================================

class TestDKBCSVParser:
    """Tests fuer den DKB CSV-Parser."""

    DKB_META = (
        '"Kontonummer:";"DE89370400440532013000 / Girokonto"\n'
        '"Von:";"01.01.2024"\n'
        '"Bis:";"31.03.2024"\n'
        '"Kontostand vom 31.03.2024:";"4.850,50 EUR"\n'
        '\n'
    )
    DKB_HEADER = '"Buchungstag";"Wertstellung";"Buchungstext";"Auftraggeber / Beg\u00fcnstigter";"Verwendungszweck";"Kontonummer";"BLZ";"Betrag (EUR)";"Gl\u00e4ubiger-ID";"Mandatsreferenz";"Kundenreferenz"'
    DKB_ROW = '"15.03.2024";"16.03.2024";"Lastschrift";"Stadtwerke Berlin";"Strom Maerz 2024";"DE02100500000024290661";"10050000";"-149,50";"DE98ZZZ09999999999";"MNDT-001";"E2E-001"'

    @pytest.fixture
    def parser(self) -> DKBCSVParser:
        return DKBCSVParser()

    def test_can_parse_dkb_header(self) -> None:
        """Erkennt DKB-Format anhand 'Betrag (EUR)' Spalte."""
        content = self.DKB_META + self.DKB_HEADER + "\n" + self.DKB_ROW + "\n"
        confidence = DKBCSVParser.can_parse(content)
        assert confidence >= 0.7

    def test_can_parse_betrag_eur_column(self) -> None:
        """Hohe Konfidenz bei 'Betrag (EUR)' Spalte."""
        content = self.DKB_HEADER + "\n" + self.DKB_ROW + "\n"
        confidence = DKBCSVParser.can_parse(content)
        assert confidence >= 0.85

    def test_can_parse_no_dkb(self) -> None:
        """Erkennt Nicht-DKB-Format."""
        content = "Date,Amount,Payee\n2024-01-01,-50.00,Test\n"
        assert DKBCSVParser.can_parse(content) == 0.0

    def test_can_parse_empty(self) -> None:
        """Gibt 0 bei leerem Inhalt zurueck."""
        assert DKBCSVParser.can_parse("") == 0.0

    def test_parse_with_metadata_header(self, parser: DKBCSVParser) -> None:
        """Parst DKB-CSV mit Metadaten vor dem eigentlichen Header."""
        content = self.DKB_META + self.DKB_HEADER + "\n" + self.DKB_ROW + "\n"
        result = parser.parse(content)

        assert result.success is True
        assert result.format == ImportFormat.CSV_DKB
        assert result.format_variant == "dkb"
        assert len(result.transactions) == 1

    def test_parse_iban_from_metadata(self, parser: DKBCSVParser) -> None:
        """Extrahiert IBAN aus den Metadaten."""
        content = self.DKB_META + self.DKB_HEADER + "\n" + self.DKB_ROW + "\n"
        result = parser.parse(content)

        assert result.account_iban == "DE89370400440532013000"

    def test_parse_encoding_error(self, parser: DKBCSVParser) -> None:
        """Fehler bei nicht dekodierbarem Inhalt."""
        from unittest.mock import patch
        with patch.object(DKBCSVParser, '_decode_content', return_value=None):
            result = parser.parse(b"\xff\xfe")
        assert result.success is False

    def test_map_columns(self, parser: DKBCSVParser) -> None:
        """Mappt DKB-spezifische Spalten korrekt."""
        fieldnames = [
            "Buchungstag", "Wertstellung", "Buchungstext",
            "Auftraggeber / Beg\u00fcnstigter", "Verwendungszweck",
            "Kontonummer", "BLZ", "Betrag (EUR)",
        ]
        mapping = parser._map_columns(fieldnames)

        assert mapping.get("booking_date") == "Buchungstag"
        assert mapping.get("value_date") == "Wertstellung"
        assert mapping.get("amount") == "Betrag (EUR)"
        assert mapping.get("reference_text") == "Verwendungszweck"
        assert mapping.get("booking_text") == "Buchungstext"

    def test_parse_dkb_format_metadata(self, parser: DKBCSVParser) -> None:
        """Setzt korrektes Format und Variante."""
        assert parser.FORMAT == ImportFormat.CSV_DKB
        assert parser.FORMAT_VARIANT == "dkb"


# =============================================================================
# ING
# =============================================================================

class TestINGCSVParser:
    """Tests fuer den ING CSV-Parser."""

    ING_HEADER = "Buchung;Valuta;Auftraggeber/Empf\u00e4nger;Buchungstext;Verwendungszweck;Betrag;W\u00e4hrung;Saldo"
    ING_ROW = "15.03.2024;16.03.2024;Stadtwerke Berlin;Lastschrift;Strom Maerz 2024;-149,50;EUR;4.850,50"

    @pytest.fixture
    def parser(self) -> INGCSVParser:
        return INGCSVParser()

    def test_can_parse_ing_header(self) -> None:
        """Erkennt ING-Format anhand 'Auftraggeber/Empfaenger'."""
        content = self.ING_HEADER + "\n" + self.ING_ROW + "\n"
        confidence = INGCSVParser.can_parse(content)
        assert confidence >= 0.85

    def test_can_parse_no_ing(self) -> None:
        """Erkennt Nicht-ING-Format."""
        content = "Date,Amount,Payee\n2024-01-01,-50.00,Test\n"
        assert INGCSVParser.can_parse(content) == 0.0

    def test_can_parse_empty(self) -> None:
        """Gibt 0 bei leerem Inhalt zurueck."""
        assert INGCSVParser.can_parse("") == 0.0

    def test_map_columns(self, parser: INGCSVParser) -> None:
        """Mappt ING-spezifische Spalten korrekt."""
        fieldnames = [
            "Buchung", "Valuta", "Auftraggeber/Empf\u00e4nger",
            "Buchungstext", "Verwendungszweck", "Betrag", "W\u00e4hrung", "Saldo",
        ]
        mapping = parser._map_columns(fieldnames)

        assert mapping.get("booking_date") == "Buchung"
        assert mapping.get("value_date") == "Valuta"
        assert mapping.get("amount") == "Betrag"
        assert mapping.get("reference_text") == "Verwendungszweck"
        assert mapping.get("booking_text") == "Buchungstext"

    def test_parse_full_ing_csv(self, parser: INGCSVParser) -> None:
        """Parst vollstaendiges ING-CSV."""
        content = self.ING_HEADER + "\n" + self.ING_ROW + "\n"
        result = parser.parse(content)

        assert result.success is True
        assert len(result.transactions) == 1
        tx = result.transactions[0]
        assert tx.amount == Decimal("-149.50")
        assert tx.booking_date == date(2024, 3, 15)

    def test_parse_ing_format_metadata(self, parser: INGCSVParser) -> None:
        """Setzt korrektes Format und Variante."""
        assert parser.FORMAT == ImportFormat.CSV_ING
        assert parser.FORMAT_VARIANT == "ing"


# =============================================================================
# Deutsche Bank
# =============================================================================

class TestDeutscheBankCSVParser:
    """Tests fuer den Deutsche Bank CSV-Parser."""

    DB_HEADER = "Booking date;Value date;Transaction Type;Beneficiary / Originator;Payment Reference;IBAN;BIC;Amount;Currency"
    DB_ROW = "15.03.2024;16.03.2024;Direct Debit;Stadtwerke Berlin;Strom Maerz 2024;DE02100500000024290661;BELADEBEXXX;-149,50;EUR"

    @pytest.fixture
    def parser(self) -> DeutscheBankCSVParser:
        return DeutscheBankCSVParser()

    def test_can_parse_db_header(self) -> None:
        """Erkennt Deutsche Bank-Format anhand 'Beneficiary / Originator'."""
        content = self.DB_HEADER + "\n" + self.DB_ROW + "\n"
        confidence = DeutscheBankCSVParser.can_parse(content)
        assert confidence >= 0.9

    def test_can_parse_no_db(self) -> None:
        """Erkennt Nicht-Deutsche Bank-Format."""
        content = "Buchungstag;Betrag;Name\n01.01.2024;-50;Test\n"
        assert DeutscheBankCSVParser.can_parse(content) == 0.0

    def test_can_parse_empty(self) -> None:
        """Gibt 0 bei leerem Inhalt zurueck."""
        assert DeutscheBankCSVParser.can_parse("") == 0.0

    def test_map_columns(self, parser: DeutscheBankCSVParser) -> None:
        """Mappt Deutsche Bank-spezifische (englische) Spalten korrekt."""
        fieldnames = [
            "Booking date", "Value date", "Transaction Type",
            "Beneficiary / Originator", "Payment Reference",
            "IBAN", "BIC", "Amount", "Currency",
        ]
        mapping = parser._map_columns(fieldnames)

        assert mapping.get("booking_date") == "Booking date"
        assert mapping.get("value_date") == "Value date"
        assert mapping.get("amount") == "Amount"
        assert mapping.get("counterparty_name") == "Beneficiary / Originator"
        assert mapping.get("reference_text") == "Payment Reference"
        assert mapping.get("booking_text") == "Transaction Type"

    def test_parse_full_db_csv(self, parser: DeutscheBankCSVParser) -> None:
        """Parst vollstaendiges Deutsche Bank-CSV."""
        content = self.DB_HEADER + "\n" + self.DB_ROW + "\n"
        result = parser.parse(content)

        assert result.success is True
        assert len(result.transactions) == 1
        tx = result.transactions[0]
        assert tx.amount == Decimal("-149.50")
        assert tx.counterparty_name == "Stadtwerke Berlin"

    def test_parse_db_format_metadata(self, parser: DeutscheBankCSVParser) -> None:
        """Setzt korrektes Format und Variante."""
        assert parser.FORMAT == ImportFormat.CSV_DEUTSCHE_BANK
        assert parser.FORMAT_VARIANT == "deutsche_bank"


# =============================================================================
# N26
# =============================================================================

class TestN26CSVParser:
    """Tests fuer den N26 CSV-Parser."""

    N26_HEADER = "Date,Payee,Account number,Transaction type,Payment reference,Amount (EUR)"
    N26_ROW = "2024-03-15,Stadtwerke Berlin,DE02100500000024290661,Direct Debit,Strom Maerz 2024,-149.50"

    @pytest.fixture
    def parser(self) -> N26CSVParser:
        return N26CSVParser()

    def test_can_parse_n26_header(self) -> None:
        """Erkennt N26-Format anhand 'Payee' + 'Amount (EUR)'."""
        content = self.N26_HEADER + "\n" + self.N26_ROW + "\n"
        confidence = N26CSVParser.can_parse(content)
        assert confidence >= 0.9

    def test_can_parse_no_n26(self) -> None:
        """Erkennt Nicht-N26-Format."""
        content = "Buchungstag;Betrag;Name\n01.01.2024;-50;Test\n"
        assert N26CSVParser.can_parse(content) == 0.0

    def test_can_parse_empty(self) -> None:
        """Gibt 0 bei leerem Inhalt zurueck."""
        assert N26CSVParser.can_parse("") == 0.0

    def test_map_columns(self, parser: N26CSVParser) -> None:
        """Mappt N26-spezifische (englische) Spalten korrekt."""
        fieldnames = [
            "Date", "Payee", "Account number", "Transaction type",
            "Payment reference", "Amount (EUR)",
        ]
        mapping = parser._map_columns(fieldnames)

        assert mapping.get("booking_date") == "Date"
        assert mapping.get("counterparty_name") == "Payee"
        assert mapping.get("counterparty_iban") == "Account number"
        assert mapping.get("amount") == "Amount (EUR)"
        assert mapping.get("reference_text") == "Payment reference"
        assert mapping.get("booking_text") == "Transaction type"

    def test_map_columns_value_date_fallback(self, parser: N26CSVParser) -> None:
        """N26 setzt value_date = booking_date (keine separate Spalte)."""
        fieldnames = ["Date", "Amount (EUR)", "Payee"]
        mapping = parser._map_columns(fieldnames)

        assert mapping.get("value_date") == "Date"

    def test_parse_full_n26_csv(self, parser: N26CSVParser) -> None:
        """Parst vollstaendiges N26-CSV (Komma-separiert, englische Spaltennamen)."""
        content = self.N26_HEADER + "\n" + self.N26_ROW + "\n"
        result = parser.parse(content)

        assert result.success is True
        assert len(result.transactions) == 1
        tx = result.transactions[0]
        assert tx.amount == Decimal("-149.50")
        assert tx.booking_date == date(2024, 3, 15)
        assert tx.counterparty_name == "Stadtwerke Berlin"

    def test_parse_n26_format_metadata(self, parser: N26CSVParser) -> None:
        """Setzt korrektes Format und Variante."""
        assert parser.FORMAT == ImportFormat.CSV_N26
        assert parser.FORMAT_VARIANT == "n26"


# =============================================================================
# Volksbank
# =============================================================================

class TestVolksbankCSVParser:
    """Tests fuer den Volksbank/Raiffeisenbank CSV-Parser."""

    VR_HEADER = "Buchungstag;Valuta;Empf\u00e4nger/Zahlungspflichtiger;IBAN;BIC;Buchungstext;Verwendungszweck;Kundenreferenz;Betrag;W\u00e4hrung"
    VR_ROW = "15.03.2024;16.03.2024;Stadtwerke Berlin;DE02100500000024290661;BELADEBEXXX;Lastschrift;Strom Maerz 2024;E2E-001;-149,50;EUR"

    @pytest.fixture
    def parser(self) -> VolksbankCSVParser:
        return VolksbankCSVParser()

    def test_can_parse_vr_header(self) -> None:
        """Erkennt Volksbank-Format anhand 'Empfaenger/Zahlungspflichtiger'."""
        content = self.VR_HEADER + "\n" + self.VR_ROW + "\n"
        confidence = VolksbankCSVParser.can_parse(content)
        assert confidence >= 0.85

    def test_can_parse_no_vr(self) -> None:
        """Erkennt Nicht-Volksbank-Format."""
        content = "Date,Amount,Payee\n2024-01-01,-50.00,Test\n"
        assert VolksbankCSVParser.can_parse(content) == 0.0

    def test_can_parse_empty(self) -> None:
        """Gibt 0 bei leerem Inhalt zurueck."""
        assert VolksbankCSVParser.can_parse("") == 0.0

    def test_map_columns(self, parser: VolksbankCSVParser) -> None:
        """Mappt Volksbank-spezifische Spalten korrekt."""
        fieldnames = [
            "Buchungstag", "Valuta", "Empf\u00e4nger/Zahlungspflichtiger",
            "IBAN", "BIC", "Buchungstext", "Verwendungszweck",
            "Kundenreferenz", "Betrag", "W\u00e4hrung",
        ]
        mapping = parser._map_columns(fieldnames)

        assert mapping.get("booking_date") == "Buchungstag"
        assert mapping.get("value_date") == "Valuta"
        assert mapping.get("amount") == "Betrag"
        assert mapping.get("counterparty_name") == "Empf\u00e4nger/Zahlungspflichtiger"
        assert mapping.get("counterparty_iban") == "IBAN"
        assert mapping.get("counterparty_bic") == "BIC"
        assert mapping.get("reference_text") == "Verwendungszweck"

    def test_parse_full_vr_csv(self, parser: VolksbankCSVParser) -> None:
        """Parst vollstaendiges Volksbank-CSV."""
        content = self.VR_HEADER + "\n" + self.VR_ROW + "\n"
        result = parser.parse(content)

        assert result.success is True
        assert len(result.transactions) == 1
        tx = result.transactions[0]
        assert tx.amount == Decimal("-149.50")
        assert tx.booking_date == date(2024, 3, 15)
        assert tx.counterparty_name == "Stadtwerke Berlin"
        assert tx.counterparty_iban == "DE02100500000024290661"

    def test_parse_vr_format_metadata(self, parser: VolksbankCSVParser) -> None:
        """Setzt korrektes Format und Variante."""
        assert parser.FORMAT == ImportFormat.CSV_VOLKSBANK
        assert parser.FORMAT_VARIANT == "volksbank"


# =============================================================================
# Uebergreifende Tests
# =============================================================================

class TestBankCSVParsersCommon:
    """Uebergreifende Tests fuer alle Bank-Parser."""

    ALL_PARSERS = [
        SparkasseCSVParser,
        CommerzbankCSVParser,
        DKBCSVParser,
        INGCSVParser,
        DeutscheBankCSVParser,
        N26CSVParser,
        VolksbankCSVParser,
    ]

    def test_all_parsers_have_format(self) -> None:
        """Jeder Parser hat ein eindeutiges FORMAT gesetzt."""
        formats = set()
        for parser_cls in self.ALL_PARSERS:
            assert parser_cls.FORMAT is not None
            assert parser_cls.FORMAT not in formats, f"Doppeltes FORMAT: {parser_cls.FORMAT}"
            formats.add(parser_cls.FORMAT)

    def test_all_parsers_have_variant(self) -> None:
        """Jeder Parser hat eine FORMAT_VARIANT gesetzt."""
        for parser_cls in self.ALL_PARSERS:
            assert parser_cls.FORMAT_VARIANT is not None

    def test_all_parsers_can_parse_empty(self) -> None:
        """Kein Parser erkennt leeren Inhalt."""
        for parser_cls in self.ALL_PARSERS:
            assert parser_cls.can_parse("") == 0.0
            assert parser_cls.can_parse(b"") == 0.0

    def test_all_parsers_inherit_from_generic(self) -> None:
        """Alle Bank-Parser erben von GenericCSVParser."""
        from app.services.banking.parsers.csv_parser import GenericCSVParser
        for parser_cls in self.ALL_PARSERS:
            assert issubclass(parser_cls, GenericCSVParser)

    def test_german_amount_parsing(self) -> None:
        """Alle Parser erben korrektes deutsches Betrag-Parsing."""
        parser = SparkasseCSVParser()

        # Deutsches Format: 1.234,56
        assert parser.parse_german_amount("1.234,56") == Decimal("1234.56")
        assert parser.parse_german_amount("-1.234,56") == Decimal("-1234.56")

        # Nur Komma
        assert parser.parse_german_amount("42,50") == Decimal("42.50")
        assert parser.parse_german_amount("-42,50") == Decimal("-42.50")

        # Waehrungssymbol
        assert parser.parse_german_amount("1.234,56 \u20ac") == Decimal("1234.56")

        # Englisches Format
        assert parser.parse_german_amount("1,234.56") == Decimal("1234.56")

        # Leerer String
        assert parser.parse_german_amount("") == Decimal("0")

    def test_iban_normalization(self) -> None:
        """IBAN-Normalisierung entfernt Leerzeichen und konvertiert zu Grossbuchstaben."""
        parser = SparkasseCSVParser()

        assert parser.normalize_iban("DE89 3704 0044 0532 0130 00") == "DE89370400440532013000"
        assert parser.normalize_iban("de89370400440532013000") == "DE89370400440532013000"
        assert parser.normalize_iban("") is None
        assert parser.normalize_iban(None) is None

    def test_transaction_type_detection(self) -> None:
        """Erkennt verschiedene Transaktionstypen."""
        parser = SparkasseCSVParser()

        assert parser.detect_transaction_type("Lastschrift", Decimal("-50")) == TransactionType.DIRECT_DEBIT
        assert parser.detect_transaction_type("VISA Kartenzahlung", Decimal("-20")) == TransactionType.CARD
        assert parser.detect_transaction_type("Geldautomat Auszahlung", Decimal("-100")) == TransactionType.CASH
        assert parser.detect_transaction_type("Kontof\u00fchrungsgeb\u00fchr", Decimal("-5")) == TransactionType.FEE
        assert parser.detect_transaction_type("Habenzinsen", Decimal("1.5")) == TransactionType.INTEREST
        assert parser.detect_transaction_type("", Decimal("0")) == TransactionType.OTHER
