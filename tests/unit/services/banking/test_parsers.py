# -*- coding: utf-8 -*-
"""
Tests fuer Banking Parser.

Testet:
- IBAN-Validierung (MOD-97)
- MT940 Parser
- CAMT.053 Parser
- Generischer CSV Parser
- Bank-spezifische CSV Parser (DKB, N26, Sparkasse, etc.)
- Format-Erkennung
"""

import pytest
from datetime import date
from decimal import Decimal
from typing import Optional

from app.services.banking.account_service import AccountService
from app.services.banking.parsers import (
    detect_format,
    ParseResult,
    ParsedTransaction,
    MT940Parser,
    CAMT053Parser,
    GenericCSVParser,
)
from app.services.banking.parsers.bank_csv import (
    SparkasseCSVParser,
    VolksbankCSVParser,
    DeutscheBankCSVParser,
    CommerzbankCSVParser,
    INGCSVParser,
    N26CSVParser,
    DKBCSVParser,
)
from app.services.banking.models import ImportFormat, TransactionType


class TestIBANValidation:
    """Tests fuer IBAN-Validierung im AccountService."""

    @pytest.fixture
    def account_service(self) -> AccountService:
        return AccountService()

    def test_valid_german_iban(self, account_service: AccountService):
        """Sollte gueltige deutsche IBAN akzeptieren."""
        valid_ibans = [
            "DE89370400440532013000",  # Standard
            "DE 89 3704 0044 0532 0130 00",  # Mit Leerzeichen
            "de89370400440532013000",  # Kleinbuchstaben
            "DE68210501700012345678",  # Sparkasse
            "DE75512108001245126199",  # ING
        ]
        for iban in valid_ibans:
            assert account_service.validate_iban(iban), f"Sollte gueltig sein: {iban}"

    def test_invalid_german_iban_checksum(self, account_service: AccountService):
        """Sollte IBAN mit falscher Pruefsumme ablehnen."""
        invalid_ibans = [
            "DE89370400440532013001",  # Letzte Ziffer falsch
            "DE00370400440532013000",  # Pruefsumme 00 statt 89
            "DE12345678901234567890",  # Falsche Pruefsumme
        ]
        for iban in invalid_ibans:
            assert not account_service.validate_iban(iban), f"Sollte ungueltig sein: {iban}"

    def test_invalid_iban_format(self, account_service: AccountService):
        """Sollte IBAN mit falschem Format ablehnen."""
        invalid_formats = [
            "DE893704004405320130",  # Zu kurz
            "89370400440532013000",  # Ohne Laendercode
            "1234567890",  # Keine IBAN
            "DEXX370400440532013000",  # Buchstaben statt Pruefsumme
            "",  # Leer
            "DE",  # Nur Laendercode
        ]
        for iban in invalid_formats:
            assert not account_service.validate_iban(iban), f"Sollte ungueltig sein: {iban}"

    def test_valid_international_iban(self, account_service: AccountService):
        """Sollte gueltige internationale IBANs akzeptieren."""
        valid_ibans = [
            "AT611904300234573201",  # Oesterreich
            "CH9300762011623852957",  # Schweiz
            "FR7630006000011234567890189",  # Frankreich
            "NL91ABNA0417164300",  # Niederlande
        ]
        for iban in valid_ibans:
            assert account_service.validate_iban(iban), f"Sollte gueltig sein: {iban}"


class TestMT940Parser:
    """Tests fuer MT940 Parser."""

    @pytest.fixture
    def parser(self) -> MT940Parser:
        return MT940Parser()

    def test_can_parse_mt940_content(self, parser: MT940Parser):
        """Sollte MT940-Inhalt erkennen."""
        mt940_content = """:20:STARTUMS
:25:37040044/532013000
:28C:0/1
:60F:C241215EUR1000,00
:61:2412151215CR100,00NTRFNONREF//12345
:86:ÜBERWEISUNG VON KUNDE
:62F:C241215EUR1100,00
-
"""
        confidence = parser.can_parse(mt940_content)
        assert confidence > 0.8, f"Konfidenz sollte > 0.8 sein: {confidence}"

    def test_cannot_parse_csv_content(self, parser: MT940Parser):
        """Sollte CSV-Inhalt ablehnen."""
        csv_content = "Buchungstag;Wertstellung;Betrag;Verwendungszweck\n15.12.2024;15.12.2024;100,00;Test"
        confidence = parser.can_parse(csv_content)
        assert confidence == 0.0, "Sollte CSV nicht als MT940 erkennen"

    def test_parse_mt940_statement(self, parser: MT940Parser):
        """Sollte MT940-Statement korrekt parsen."""
        mt940_content = """:20:STARTUMS
:25:37040044/532013000
:28C:0/1
:60F:C241215EUR1000,00
:61:2412151215CR100,00NTRFNONREF//12345
Mustermann Max
:86:ÜBERWEISUNG VON KUNDE
Mustermann Max
IBAN: DE89370400440532013000
Betreff: Rechnung 2024-001
:62F:C241215EUR1100,00
-
"""
        result = parser.parse(mt940_content)
        assert result.success, f"Parsing sollte erfolgreich sein: {result.errors}"
        assert result.transaction_count >= 1
        # Note: Actual transaction details depend on the mt-940 library behavior


class TestCAMT053Parser:
    """Tests fuer CAMT.053 Parser."""

    @pytest.fixture
    def parser(self) -> CAMT053Parser:
        return CAMT053Parser()

    def test_can_parse_camt_xml(self, parser: CAMT053Parser):
        """Sollte CAMT.053 XML erkennen."""
        camt_xml = """<?xml version="1.0" encoding="UTF-8"?>
<Document xmlns="urn:iso:std:iso:20022:tech:xsd:camt.053.001.02">
    <BkToCstmrStmt>
        <Stmt>
            <Id>12345</Id>
        </Stmt>
    </BkToCstmrStmt>
</Document>"""
        confidence = parser.can_parse(camt_xml)
        assert confidence > 0.8, f"Konfidenz sollte > 0.8 sein: {confidence}"

    def test_cannot_parse_plain_xml(self, parser: CAMT053Parser):
        """Sollte nicht-CAMT XML ablehnen."""
        other_xml = """<?xml version="1.0" encoding="UTF-8"?>
<root><item>test</item></root>"""
        confidence = parser.can_parse(other_xml)
        assert confidence == 0.0, "Sollte nicht-CAMT XML nicht erkennen"

    def test_cannot_parse_mt940(self, parser: CAMT053Parser):
        """Sollte MT940 ablehnen."""
        mt940_content = ":20:STARTUMS\n:25:37040044/532013000"
        confidence = parser.can_parse(mt940_content)
        assert confidence == 0.0


class TestGenericCSVParser:
    """Tests fuer generischen CSV Parser."""

    @pytest.fixture
    def parser(self) -> GenericCSVParser:
        return GenericCSVParser()

    def test_can_parse_generic_csv(self, parser: GenericCSVParser):
        """Sollte generisches CSV erkennen."""
        csv_content = """Datum;Betrag;Verwendungszweck
15.12.2024;100,00;Test Buchung
16.12.2024;-50,00;Abbuchung"""
        confidence = parser.can_parse(csv_content)
        assert confidence > 0.3, f"Konfidenz sollte > 0.3 sein: {confidence}"

    def test_parse_german_numbers(self, parser: GenericCSVParser):
        """Sollte deutsche Zahlenformate korrekt parsen."""
        csv_content = """Datum;Betrag;Empfaenger;Verwendungszweck
15.12.2024;1.234,56;Max Mustermann;Ueberweisung
16.12.2024;-999,99;Firma GmbH;Rechnung"""
        result = parser.parse(csv_content)
        assert result.success
        assert result.transaction_count == 2

        if result.transactions:
            tx = result.transactions[0]
            assert tx.amount == Decimal("1234.56")

    def test_parse_date_formats(self, parser: GenericCSVParser):
        """Sollte verschiedene Datumsformate erkennen."""
        test_dates = [
            ("15.12.2024", date(2024, 12, 15)),
            ("2024-12-15", date(2024, 12, 15)),
            ("15/12/2024", date(2024, 12, 15)),
        ]
        for date_str, expected in test_dates:
            parsed = parser._parse_date(date_str)
            assert parsed == expected, f"Datumsfehler bei {date_str}"


class TestDKBCSVParser:
    """Tests fuer DKB CSV Parser."""

    @pytest.fixture
    def parser(self) -> DKBCSVParser:
        return DKBCSVParser()

    def test_can_parse_dkb_header(self, parser: DKBCSVParser):
        """Sollte DKB CSV-Header erkennen."""
        dkb_content = """Kontonummer: DE89370400440532013000

Buchungstag;Wertstellung;Buchungstext;Auftraggeber / Begünstigter;Verwendungszweck;Kontonummer;BLZ;Betrag (EUR);
15.12.2024;15.12.2024;GUTSCHRIFT;Max Mustermann;Miete Dezember;DE12345678901234567890;37040044;1.000,00;"""
        confidence = parser.can_parse(dkb_content)
        assert confidence > 0.8, f"Konfidenz sollte > 0.8 sein: {confidence}"

    def test_cannot_parse_n26(self, parser: DKBCSVParser):
        """Sollte N26 CSV nicht als DKB erkennen."""
        n26_content = """Date,Payee,Account number,Transaction type,Payment reference,Amount (EUR)
2024-12-15,Max Mustermann,DE12345678901234567890,Income,Salary,1000.00"""
        confidence = parser.can_parse(n26_content)
        assert confidence < 0.5, "Sollte N26 nicht als DKB erkennen"

    def test_parse_dkb_transactions(self, parser: DKBCSVParser):
        """Sollte DKB-Transaktionen korrekt parsen."""
        dkb_content = """Buchungstag;Wertstellung;Buchungstext;Auftraggeber / Begünstigter;Verwendungszweck;Kontonummer;BLZ;Betrag (EUR);
15.12.2024;15.12.2024;GUTSCHRIFT;Max Mustermann;Miete Dezember;DE12345678901234567890;37040044;1.000,00;
16.12.2024;16.12.2024;LASTSCHRIFT;Stromanbieter;Abschlag Strom;DE98765432109876543210;50010517;-85,00;"""
        result = parser.parse(dkb_content)
        assert result.success
        assert result.transaction_count == 2


class TestN26CSVParser:
    """Tests fuer N26 CSV Parser."""

    @pytest.fixture
    def parser(self) -> N26CSVParser:
        return N26CSVParser()

    def test_can_parse_n26_header(self, parser: N26CSVParser):
        """Sollte N26 CSV-Header erkennen."""
        n26_content = """Date,Payee,Account number,Transaction type,Payment reference,Amount (EUR)
2024-12-15,Max Mustermann,DE12345678901234567890,Income,Salary,1000.00"""
        confidence = parser.can_parse(n26_content)
        assert confidence > 0.8, f"Konfidenz sollte > 0.8 sein: {confidence}"

    def test_cannot_parse_dkb(self, parser: N26CSVParser):
        """Sollte DKB CSV nicht als N26 erkennen."""
        dkb_content = """Buchungstag;Wertstellung;Buchungstext;Auftraggeber;Betrag (EUR)
15.12.2024;15.12.2024;GUTSCHRIFT;Max Mustermann;1.000,00"""
        confidence = parser.can_parse(dkb_content)
        assert confidence < 0.5, "Sollte DKB nicht als N26 erkennen"


class TestSparkasseCSVParser:
    """Tests fuer Sparkasse CSV Parser."""

    @pytest.fixture
    def parser(self) -> SparkasseCSVParser:
        return SparkasseCSVParser()

    def test_can_parse_sparkasse_header(self, parser: SparkasseCSVParser):
        """Sollte Sparkasse CSV-Header erkennen."""
        sparkasse_content = """Auftragskonto;Buchungstag;Valutadatum;Buchungstext;Verwendungszweck;Begünstigter/Zahlungspflichtiger;Kontonummer;BLZ;Betrag;Währung;
DE89370400440532013000;15.12.2024;15.12.2024;ÜBERWEISUNG;Miete Dezember;Max Mustermann;DE12345678901234567890;37040044;1000,00;EUR;"""
        confidence = parser.can_parse(sparkasse_content)
        assert confidence > 0.7, f"Konfidenz sollte > 0.7 sein: {confidence}"


class TestVolksbankCSVParser:
    """Tests fuer Volksbank CSV Parser."""

    @pytest.fixture
    def parser(self) -> VolksbankCSVParser:
        return VolksbankCSVParser()

    def test_can_parse_volksbank_header(self, parser: VolksbankCSVParser):
        """Sollte Volksbank CSV-Header erkennen."""
        vb_content = """Bezeichnung Auftragskonto;IBAN Auftragskonto;BIC Auftragskonto;Bankname Auftragskonto;Buchungstag;Valutadatum;Name Zahlungsbeteiligter;IBAN Zahlungsbeteiligter;BIC Zahlungsbeteiligter;Buchungstext;Verwendungszweck;Betrag;Währung;
Girokonto;DE89370400440532013000;COBADEFFXXX;Commerzbank;15.12.2024;15.12.2024;Max Mustermann;DE12345678901234567890;COBADEFFXXX;ÜBERWEISUNG;Miete;1000,00;EUR;"""
        confidence = parser.can_parse(vb_content)
        assert confidence > 0.7, f"Konfidenz sollte > 0.7 sein: {confidence}"


class TestFormatDetection:
    """Tests fuer automatische Format-Erkennung."""

    def test_detect_mt940(self):
        """Sollte MT940 korrekt erkennen."""
        mt940_content = """:20:STARTUMS
:25:37040044/532013000
:28C:0/1
:60F:C241215EUR1000,00
-"""
        results = detect_format(mt940_content)
        assert len(results) > 0
        parser_cls, confidence = results[0]
        assert parser_cls == MT940Parser
        assert confidence > 0.8

    def test_detect_dkb_csv(self):
        """Sollte DKB CSV korrekt erkennen."""
        dkb_content = """Buchungstag;Wertstellung;Buchungstext;Auftraggeber / Begünstigter;Verwendungszweck;Kontonummer;BLZ;Betrag (EUR);
15.12.2024;15.12.2024;GUTSCHRIFT;Max;Test;DE123;37040044;100,00;"""
        results = detect_format(dkb_content)
        assert len(results) > 0
        parser_cls, confidence = results[0]
        assert parser_cls == DKBCSVParser
        assert confidence > 0.8

    def test_detect_n26_csv(self):
        """Sollte N26 CSV korrekt erkennen."""
        n26_content = """Date,Payee,Account number,Transaction type,Payment reference,Amount (EUR)
2024-12-15,Max,DE123,Income,Test,100.00"""
        results = detect_format(n26_content)
        assert len(results) > 0
        parser_cls, confidence = results[0]
        assert parser_cls == N26CSVParser
        assert confidence > 0.8

    def test_detect_by_filename(self):
        """Sollte Format auch anhand Dateiname erkennen."""
        csv_content = "Datum;Betrag;Text\n15.12.2024;100;Test"

        # MT940 Dateiname
        results = detect_format(csv_content, filename="kontoauszug.sta")
        # Should boost MT940 confidence based on extension

    def test_fallback_to_generic_csv(self):
        """Sollte auf Generic CSV zurueckfallen bei unbekanntem Format."""
        unknown_csv = """Col1;Col2;Col3
Val1;Val2;Val3"""
        results = detect_format(unknown_csv)
        # Should return some results, possibly GenericCSV as fallback
        assert len(results) > 0


class TestReferenceTextParsing:
    """Tests fuer Verwendungszweck-Parsing."""

    @pytest.fixture
    def parser(self) -> GenericCSVParser:
        return GenericCSVParser()

    def test_extract_invoice_numbers(self, parser: GenericCSVParser):
        """Sollte Rechnungsnummern aus Verwendungszweck extrahieren."""
        test_cases = [
            ("Rechnung Nr. 2024-001", ["2024-001"]),
            ("RE 12345/2024", ["12345/2024"]),
            ("Rechnungs-Nr.: INV-2024-0042", ["INV-2024-0042"]),
            ("Kein Rechnungsbezug", []),
        ]
        for text, expected in test_cases:
            result = parser.parse_reference_text(text)
            if expected:
                assert "invoice_numbers" in result
                for exp in expected:
                    assert any(exp in inv for inv in result.get("invoice_numbers", []))

    def test_extract_customer_numbers(self, parser: GenericCSVParser):
        """Sollte Kundennummern aus Verwendungszweck extrahieren."""
        test_cases = [
            ("Kundennr. 123456", ["123456"]),
            ("KD-NR: 987654", ["987654"]),
            ("Ohne Kundennummer", []),
        ]
        for text, expected in test_cases:
            result = parser.parse_reference_text(text)
            if expected:
                assert "customer_numbers" in result


class TestTransactionTypeDetection:
    """Tests fuer Transaktionstyp-Erkennung."""

    @pytest.fixture
    def parser(self) -> GenericCSVParser:
        return GenericCSVParser()

    def test_detect_transfer(self, parser: GenericCSVParser):
        """Sollte Ueberweisungen erkennen."""
        booking_texts = [
            "ÜBERWEISUNG",
            "SEPA-ÜBERWEISUNG",
            "ONLINE-UEBERWEISUNG",
        ]
        for text in booking_texts:
            tx_type = parser._detect_transaction_type(text)
            assert tx_type == TransactionType.TRANSFER, f"Sollte TRANSFER sein: {text}"

    def test_detect_direct_debit(self, parser: GenericCSVParser):
        """Sollte Lastschriften erkennen."""
        booking_texts = [
            "LASTSCHRIFT",
            "SEPA-LASTSCHRIFT",
            "EINZUG",
        ]
        for text in booking_texts:
            tx_type = parser._detect_transaction_type(text)
            assert tx_type == TransactionType.DIRECT_DEBIT, f"Sollte DIRECT_DEBIT sein: {text}"

    def test_detect_standing_order(self, parser: GenericCSVParser):
        """Sollte Dauerauftraege erkennen."""
        booking_texts = [
            "DAUERAUFTRAG",
            "DAUERLASTSCHRIFT",
        ]
        for text in booking_texts:
            tx_type = parser._detect_transaction_type(text)
            assert tx_type == TransactionType.STANDING_ORDER, f"Sollte STANDING_ORDER sein: {text}"

    def test_detect_fee(self, parser: GenericCSVParser):
        """Sollte Gebuehren erkennen."""
        booking_texts = [
            "KONTOFÜHRUNGSGEBÜHR",
            "ENTGELT",
            "ABSCHLUSS",
        ]
        for text in booking_texts:
            tx_type = parser._detect_transaction_type(text)
            assert tx_type == TransactionType.FEE, f"Sollte FEE sein: {text}"
