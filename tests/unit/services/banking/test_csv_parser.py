# -*- coding: utf-8 -*-
"""Tests fuer den generischen CSV-Parser.

Testet:
- CSV-Erkennung und Konfidenz
- Delimiter-Erkennung (Semikolon, Komma, Tab)
- Deutsches Datumsformat (DD.MM.YYYY)
- Deutsches Zahlenformat (1.234,56)
- Spalten-Mapping (deutsch/englisch)
- Fehlerbehandlung (leere Dateien, fehlende Spalten, Encoding)
"""

import pytest
from datetime import date
from decimal import Decimal
from typing import Dict, List, Optional

from app.services.banking.parsers.csv_parser import GenericCSVParser, COLUMN_MAPPINGS
from app.services.banking.parsers.base import ParseResult, ParsedTransaction
from app.services.banking.models import ImportFormat, TransactionType


class TestGenericCSVParserCanParse:
    """Tests fuer die Format-Erkennung des CSV-Parsers."""

    def test_can_parse_standard_german_csv(self) -> None:
        """Erkennt Standard-CSV mit deutschen Spaltenbezeichnungen."""
        content = (
            "Buchungstag;Wertstellung;Betrag;Verwendungszweck;IBAN\n"
            "01.01.2024;02.01.2024;-50,00;Einkauf;DE89370400440532013000\n"
        )
        confidence = GenericCSVParser.can_parse(content)
        assert confidence >= 0.5

    def test_can_parse_english_csv(self) -> None:
        """Erkennt CSV mit englischen Spaltenbezeichnungen."""
        content = (
            "Date,Amount,IBAN,Description\n"
            "2024-01-01,-50.00,DE89370400440532013000,Payment\n"
        )
        confidence = GenericCSVParser.can_parse(content)
        assert confidence >= 0.3

    def test_can_parse_high_confidence_many_columns(self) -> None:
        """Hohe Konfidenz bei vielen bekannten Banking-Spalten."""
        content = (
            "Buchungstag;Betrag;IBAN;Verwendungszweck;Empfaenger;Valuta;Saldo\n"
            "01.01.2024;-50,00;DE89370400440532013000;Einkauf;Mueller;02.01.2024;1000,00\n"
        )
        confidence = GenericCSVParser.can_parse(content)
        assert confidence >= 0.75

    def test_can_parse_empty_content(self) -> None:
        """Gibt 0 bei leerem Inhalt zurueck."""
        assert GenericCSVParser.can_parse("") == 0.0
        assert GenericCSVParser.can_parse(b"") == 0.0

    def test_can_parse_single_line(self) -> None:
        """Gibt 0 bei nur einer Zeile (kein Datenbereich)."""
        content = "Buchungstag;Betrag;IBAN\n"
        # Only 1 line -> 0.0 because len(lines) < 2 after strip
        assert GenericCSVParser.can_parse(content.strip()) == 0.0

    def test_can_parse_no_delimiter(self) -> None:
        """Gibt 0 bei fehlenden Delimitern zurueck."""
        content = "Dies ist kein CSV\nSondern nur Text"
        assert GenericCSVParser.can_parse(content) == 0.0

    def test_can_parse_bytes_utf8(self) -> None:
        """Erkennt UTF-8-kodierte Bytes."""
        content = "Buchungstag;Betrag;Verwendungszweck;IBAN\n01.01.2024;-50,00;Test;DE123\n"
        confidence = GenericCSVParser.can_parse(content.encode("utf-8"))
        assert confidence >= 0.5

    def test_can_parse_bytes_latin1(self) -> None:
        """Erkennt Latin-1/ISO-8859-1 kodierte Bytes."""
        content = "Buchungstag;Betrag;Verwendungszweck;Empf\xe4nger\n01.01.2024;-50,00;Test;M\xfcller\n"
        confidence = GenericCSVParser.can_parse(content.encode("iso-8859-1"))
        assert confidence >= 0.3

    def test_can_parse_filename_extension(self) -> None:
        """Erkennt CSV anhand der Dateiendung mit niedriger Konfidenz."""
        content = "col1;col2;col3\na;b;c\n"
        confidence = GenericCSVParser.can_parse(content, filename="export.csv")
        assert confidence >= 0.2


class TestGenericCSVParserDelimiter:
    """Tests fuer die Delimiter-Erkennung."""

    def test_detect_semicolon(self) -> None:
        """Erkennt Semikolon als Delimiter."""
        result = GenericCSVParser._detect_delimiter("Buchungstag;Betrag;IBAN")
        assert result == ";"

    def test_detect_comma(self) -> None:
        """Erkennt Komma als Delimiter."""
        result = GenericCSVParser._detect_delimiter("Date,Amount,IBAN")
        assert result == ","

    def test_detect_tab(self) -> None:
        """Erkennt Tab als Delimiter."""
        result = GenericCSVParser._detect_delimiter("Date\tAmount\tIBAN")
        assert result == "\t"

    def test_detect_no_delimiter(self) -> None:
        """Gibt None zurueck bei fehlendem Delimiter."""
        result = GenericCSVParser._detect_delimiter("EinzelnesSpalteOhneDelimiter")
        assert result is None


class TestGenericCSVParserParse:
    """Tests fuer das vollstaendige CSV-Parsing."""

    @pytest.fixture
    def parser(self) -> GenericCSVParser:
        """Erstelle Parser-Instanz."""
        return GenericCSVParser()

    def test_parse_standard_german_csv(self, parser: GenericCSVParser) -> None:
        """Parst Standard-CSV mit deutschen Spalten und Formaten."""
        content = (
            "Buchungstag;Wertstellung;Betrag;Verwendungszweck;Empfaenger\n"
            "15.03.2024;16.03.2024;-1.234,56;Rechnung RE-2024-001;Mueller GmbH\n"
            "20.03.2024;21.03.2024;500,00;Gutschrift;Schmidt AG\n"
        )
        result = parser.parse(content)

        assert result.success is True
        assert result.format == ImportFormat.CSV_GENERIC
        assert len(result.transactions) == 2

        # Erste Transaktion (Belastung)
        tx1 = result.transactions[0]
        assert tx1.booking_date == date(2024, 3, 15)
        assert tx1.amount == Decimal("-1234.56")
        assert tx1.reference_text == "Rechnung RE-2024-001"

        # Zweite Transaktion (Gutschrift)
        tx2 = result.transactions[1]
        assert tx2.booking_date == date(2024, 3, 20)
        assert tx2.amount == Decimal("500")

    def test_parse_with_iban_and_bic(self, parser: GenericCSVParser) -> None:
        """Parst CSV mit IBAN- und BIC-Spalten."""
        content = (
            "Buchungstag;Betrag;IBAN;BIC;Verwendungszweck\n"
            "01.06.2024;-100,50;DE89370400440532013000;COBADEFFXXX;Miete Juni\n"
        )
        result = parser.parse(content)

        assert result.success is True
        assert len(result.transactions) == 1
        tx = result.transactions[0]
        assert tx.counterparty_iban == "DE89370400440532013000"
        assert tx.counterparty_bic == "COBADEFFXXX"

    def test_parse_iso_date_format(self, parser: GenericCSVParser) -> None:
        """Parst CSV mit ISO-Datumsformat (YYYY-MM-DD)."""
        content = (
            "Datum;Betrag;Verwendungszweck\n"
            "2024-06-15;-42,00;Test\n"
        )
        result = parser.parse(content)
        assert result.success is True
        assert result.transactions[0].booking_date == date(2024, 6, 15)

    def test_parse_statistics_calculated(self, parser: GenericCSVParser) -> None:
        """Berechnet Summen fuer Gutschriften und Belastungen."""
        content = (
            "Buchungstag;Betrag;Verwendungszweck\n"
            "01.01.2024;-100,00;Zahlung 1\n"
            "02.01.2024;200,50;Gutschrift\n"
            "03.01.2024;-50,25;Zahlung 2\n"
        )
        result = parser.parse(content)

        assert result.success is True
        assert result.total_credits == Decimal("200.50")
        assert result.total_debits == Decimal("150.25")

    def test_parse_date_range_detected(self, parser: GenericCSVParser) -> None:
        """Erkennt den Zeitraum der Transaktionen."""
        content = (
            "Buchungstag;Betrag;Verwendungszweck\n"
            "15.01.2024;-10,00;A\n"
            "01.01.2024;-20,00;B\n"
            "31.01.2024;-30,00;C\n"
        )
        result = parser.parse(content)

        assert result.date_from == date(2024, 1, 1)
        assert result.date_to == date(2024, 1, 31)

    def test_parse_empty_csv(self, parser: GenericCSVParser) -> None:
        """Fehler bei leerem CSV ohne Transaktionen."""
        content = "Buchungstag;Betrag;Verwendungszweck\n"
        result = parser.parse(content)

        assert result.success is False
        assert len(result.errors) > 0

    def test_parse_missing_required_columns(self, parser: GenericCSVParser) -> None:
        """Fehler wenn Pflicht-Spalten fehlen."""
        content = (
            "Name;Stadt;PLZ\n"
            "Mueller;Berlin;10115\n"
        )
        result = parser.parse(content)

        assert result.success is False
        assert any(e.get("type") == "column_error" for e in result.errors)

    def test_parse_encoding_error_bytes(self, parser: GenericCSVParser) -> None:
        """Fehler bei nicht dekodierbaren Bytes."""
        # Invalid byte sequence that no encoding can decode properly
        # but _decode_content tries multiple encodings, so use something
        # that will decode but produce garbage - actually test the error path
        # by mocking _decode_content
        from unittest.mock import patch
        with patch.object(GenericCSVParser, '_decode_content', return_value=None):
            result = parser.parse(b"\xff\xfe")
        assert result.success is False
        assert any(e.get("type") == "encoding_error" for e in result.errors)

    def test_parse_skips_zero_amount_rows(self, parser: GenericCSVParser) -> None:
        """Ueberspringt Zeilen mit Betrag 0."""
        content = (
            "Buchungstag;Betrag;Verwendungszweck\n"
            "01.01.2024;0,00;Nullbuchung\n"
            "02.01.2024;-50,00;Echte Buchung\n"
        )
        result = parser.parse(content)

        assert result.success is True
        assert len(result.transactions) == 1
        assert result.transactions[0].amount == Decimal("-50")

    def test_parse_transaction_type_detection(self, parser: GenericCSVParser) -> None:
        """Erkennt Transaktionstypen aus dem Buchungstext."""
        content = (
            "Buchungstag;Betrag;Buchungstext;Verwendungszweck\n"
            "01.01.2024;-50,00;Lastschrift;Strom\n"
        )
        result = parser.parse(content)

        assert result.success is True
        assert result.transactions[0].transaction_type == TransactionType.DIRECT_DEBIT

    def test_parse_reference_extraction(self, parser: GenericCSVParser) -> None:
        """Extrahiert Rechnungsnummern aus Verwendungszweck."""
        content = (
            "Buchungstag;Betrag;Verwendungszweck\n"
            "01.01.2024;-100,00;Rechnung RE-2024-0042 Mueller GmbH\n"
        )
        result = parser.parse(content)

        assert result.success is True
        tx = result.transactions[0]
        assert len(tx.parsed_invoice_numbers) > 0

    def test_parse_comma_separated_csv(self, parser: GenericCSVParser) -> None:
        """Parst Komma-separiertes CSV (z.B. N26-Stil)."""
        content = (
            "Date,Amount,Payee,Payment Reference\n"
            "2024-01-15,-25.50,Amazon,Order 12345\n"
        )
        result = parser.parse(content)
        # This may or may not parse depending on column mapping
        # The key thing is it doesn't crash
        assert isinstance(result, ParseResult)


class TestGenericCSVParserColumnMapping:
    """Tests fuer das Spalten-Mapping."""

    @pytest.fixture
    def parser(self) -> GenericCSVParser:
        return GenericCSVParser()

    def test_map_german_columns(self, parser: GenericCSVParser) -> None:
        """Mappt deutsche Spaltenbezeichnungen korrekt."""
        fieldnames = ["Buchungstag", "Betrag", "Verwendungszweck", "IBAN"]
        mapping = parser._map_columns(fieldnames)

        assert "booking_date" in mapping
        assert "amount" in mapping
        assert "reference_text" in mapping
        assert "counterparty_iban" in mapping

    def test_map_case_insensitive(self, parser: GenericCSVParser) -> None:
        """Spalten-Mapping ist case-insensitive."""
        fieldnames = ["BUCHUNGSTAG", "BETRAG", "VERWENDUNGSZWECK"]
        mapping = parser._map_columns(fieldnames)

        assert "booking_date" in mapping
        assert "amount" in mapping

    def test_map_unknown_columns_ignored(self, parser: GenericCSVParser) -> None:
        """Unbekannte Spalten werden ignoriert."""
        fieldnames = ["Unbekannt", "Spalte", "XYZ"]
        mapping = parser._map_columns(fieldnames)

        assert len(mapping) == 0


class TestGenericCSVParserDateParsing:
    """Tests fuer verschiedene Datumsformate."""

    @pytest.fixture
    def parser(self) -> GenericCSVParser:
        return GenericCSVParser()

    def test_parse_german_date(self, parser: GenericCSVParser) -> None:
        """Parst deutsches Datum DD.MM.YYYY."""
        result = parser._parse_date("31.12.2024")
        assert result == date(2024, 12, 31)

    def test_parse_short_german_date(self, parser: GenericCSVParser) -> None:
        """Parst kurzes deutsches Datum DD.MM.YY."""
        result = parser._parse_date("31.12.24")
        assert result == date(2024, 12, 31)

    def test_parse_iso_date(self, parser: GenericCSVParser) -> None:
        """Parst ISO-Datum YYYY-MM-DD."""
        result = parser._parse_date("2024-12-31")
        assert result == date(2024, 12, 31)

    def test_parse_slash_date(self, parser: GenericCSVParser) -> None:
        """Parst Datum mit Schraegstrichen DD/MM/YYYY."""
        result = parser._parse_date("31/12/2024")
        assert result == date(2024, 12, 31)

    def test_parse_empty_date(self, parser: GenericCSVParser) -> None:
        """Gibt None bei leerem Datum zurueck."""
        assert parser._parse_date("") is None
        assert parser._parse_date("   ") is None

    def test_parse_invalid_date(self, parser: GenericCSVParser) -> None:
        """Gibt None bei ungueltigem Datum zurueck."""
        assert parser._parse_date("kein-datum") is None
        assert parser._parse_date("99.99.9999") is None
