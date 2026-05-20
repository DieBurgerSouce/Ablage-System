# -*- coding: utf-8 -*-
"""Tests fuer den CAMT.053-Parser.

Testet:
- CAMT.053-Format-Erkennung
- XML-Parsing mit defusedxml (Sicherheit gegen XXE)
- Namespace-Erkennung (v02, v04, v08)
- Kontoinfo-, Saldo- und Transaktionsextraktion
- Gutschrift/Belastung-Vorzeichen (CRDT/DBIT)
- Fehlerbehandlung bei ungueltigem XML
"""

import pytest
from datetime import date
from decimal import Decimal
from typing import Dict, List, Optional
from unittest.mock import Mock, patch

from app.services.banking.parsers.camt053_parser import CAMT053Parser, CAMT_NS
from app.services.banking.parsers.base import ParseResult, ParsedTransaction
from app.services.banking.models import ImportFormat, TransactionType


# Minimales CAMT.053 XML fuer Tests
MINIMAL_CAMT053 = """<?xml version="1.0" encoding="UTF-8"?>
<Document xmlns="urn:iso:std:iso:20022:tech:xsd:camt.053.001.02">
  <BkToCstmrStmt>
    <Stmt>
      <Acct>
        <Id><IBAN>DE89370400440532013000</IBAN></Id>
        <Svcr><FinInstnId><BIC>COBADEFFXXX</BIC></FinInstnId></Svcr>
      </Acct>
      <Bal>
        <Tp><CdOrPrtry><Cd>OPBD</Cd></CdOrPrtry></Tp>
        <Amt Ccy="EUR">5000.00</Amt>
        <CdtDbtInd>CRDT</CdtDbtInd>
        <Dt><Dt>2024-03-01</Dt></Dt>
      </Bal>
      <Bal>
        <Tp><CdOrPrtry><Cd>CLBD</Cd></CdOrPrtry></Tp>
        <Amt Ccy="EUR">4850.50</Amt>
        <CdtDbtInd>CRDT</CdtDbtInd>
        <Dt><Dt>2024-03-31</Dt></Dt>
      </Bal>
      <Ntry>
        <Amt Ccy="EUR">149.50</Amt>
        <CdtDbtInd>DBIT</CdtDbtInd>
        <BookgDt><Dt>2024-03-15</Dt></BookgDt>
        <ValDt><Dt>2024-03-16</Dt></ValDt>
        <AcctSvcrRef>REF001</AcctSvcrRef>
        <AddtlNtryInf>Lastschrift</AddtlNtryInf>
        <NtryDtls>
          <TxDtls>
            <Refs>
              <EndToEndId>E2E-2024-001</EndToEndId>
              <MndtId>MNDT-001</MndtId>
            </Refs>
            <RltdPties>
              <Cdtr><Nm>Stadtwerke Berlin</Nm></Cdtr>
              <CdtrAcct><Id><IBAN>DE02100500000024290661</IBAN></Id></CdtrAcct>
            </RltdPties>
            <RltdAgts>
              <CdtrAgt><FinInstnId><BIC>BELADEBEXXX</BIC></FinInstnId></CdtrAgt>
            </RltdAgts>
            <RmtInf>
              <Ustrd>Strom Maerz 2024 Rechnung RE-2024-0815</Ustrd>
            </RmtInf>
          </TxDtls>
        </NtryDtls>
      </Ntry>
    </Stmt>
  </BkToCstmrStmt>
</Document>"""

CAMT053_CREDIT = """<?xml version="1.0" encoding="UTF-8"?>
<Document xmlns="urn:iso:std:iso:20022:tech:xsd:camt.053.001.02">
  <BkToCstmrStmt>
    <Stmt>
      <Acct><Id><IBAN>DE89370400440532013000</IBAN></Id></Acct>
      <Ntry>
        <Amt Ccy="EUR">500.00</Amt>
        <CdtDbtInd>CRDT</CdtDbtInd>
        <BookgDt><Dt>2024-06-01</Dt></BookgDt>
        <ValDt><Dt>2024-06-01</Dt></ValDt>
        <NtryDtls>
          <TxDtls>
            <RltdPties>
              <Dbtr><Nm>Kunde AG</Nm></Dbtr>
              <DbtrAcct><Id><IBAN>DE27100777770209299700</IBAN></Id></DbtrAcct>
            </RltdPties>
            <RmtInf>
              <Ustrd>Zahlung Rechnung INV-2024-100</Ustrd>
            </RmtInf>
          </TxDtls>
        </NtryDtls>
      </Ntry>
    </Stmt>
  </BkToCstmrStmt>
</Document>"""


class TestCAMT053ParserCanParse:
    """Tests fuer die CAMT.053-Format-Erkennung."""

    def test_can_parse_camt053_namespace(self) -> None:
        """Hohe Konfidenz bei camt.053-Namespace."""
        confidence = CAMT053Parser.can_parse(MINIMAL_CAMT053)
        assert confidence >= 0.9

    def test_can_parse_iso20022_indicators(self) -> None:
        """Erkennt ISO-20022-Indikatoren."""
        content = '<?xml version="1.0"?><Document xmlns="urn:iso:std:iso:20022:tech:xsd:camt.053.001.04"><BkToCstmrStmt/></Document>'
        confidence = CAMT053Parser.can_parse(content)
        assert confidence >= 0.9

    def test_can_parse_xml_with_bank_elements(self) -> None:
        """Mittlere Konfidenz bei XML mit Banking-Elementen."""
        content = '<?xml version="1.0"?><root><Stmt><Ntry><Acct/><Bal/><TxDtls/></Ntry></Stmt></root>'
        confidence = CAMT053Parser.can_parse(content)
        assert confidence >= 0.5

    def test_can_parse_empty_content(self) -> None:
        """Gibt 0 bei leerem Inhalt zurueck."""
        assert CAMT053Parser.can_parse("") == 0.0

    def test_can_parse_non_xml(self) -> None:
        """Gibt 0 bei Nicht-XML-Inhalt zurueck."""
        assert CAMT053Parser.can_parse("Dies ist kein XML.") == 0.0

    def test_can_parse_bytes(self) -> None:
        """Erkennt CAMT.053 in Bytes."""
        confidence = CAMT053Parser.can_parse(MINIMAL_CAMT053.encode("utf-8"))
        assert confidence >= 0.9

    def test_can_parse_filename_camt(self) -> None:
        """Erkennt .camt053-Dateiendung."""
        content = '<?xml version="1.0"?><root/>'
        confidence = CAMT053Parser.can_parse(content, filename="auszug.camt053")
        assert confidence >= 0.4

    def test_can_parse_filename_xml_no_camt(self) -> None:
        """Niedrige Konfidenz bei .xml ohne CAMT-Marker."""
        content = '<?xml version="1.0"?><root><data/></root>'
        confidence = CAMT053Parser.can_parse(content, filename="data.xml")
        # No CAMT markers, just XML extension -> may return 0
        assert confidence <= 0.4


class TestCAMT053ParserParse:
    """Tests fuer das CAMT.053-Parsing."""

    @pytest.fixture
    def parser(self) -> CAMT053Parser:
        return CAMT053Parser()

    def test_parse_full_statement(self, parser: CAMT053Parser) -> None:
        """Parst vollstaendiges CAMT.053-Statement."""
        result = parser.parse(MINIMAL_CAMT053)

        assert result.success is True
        assert result.format == ImportFormat.CAMT053
        assert result.account_iban == "DE89370400440532013000"
        assert result.account_bic == "COBADEFFXXX"

    def test_parse_opening_balance(self, parser: CAMT053Parser) -> None:
        """Extrahiert Anfangssaldo korrekt."""
        result = parser.parse(MINIMAL_CAMT053)

        assert result.opening_balance == Decimal("5000.00")
        assert result.date_from is not None

    def test_parse_closing_balance(self, parser: CAMT053Parser) -> None:
        """Extrahiert Endsaldo korrekt."""
        result = parser.parse(MINIMAL_CAMT053)

        assert result.closing_balance == Decimal("4850.50")
        assert result.balance_date == date(2024, 3, 31)

    def test_parse_debit_transaction(self, parser: CAMT053Parser) -> None:
        """Parst Belastung mit negativem Vorzeichen."""
        result = parser.parse(MINIMAL_CAMT053)

        assert len(result.transactions) == 1
        tx = result.transactions[0]

        assert tx.amount == Decimal("-149.50")
        assert tx.booking_date == date(2024, 3, 15)
        assert tx.value_date == date(2024, 3, 16)
        assert tx.counterparty_name == "Stadtwerke Berlin"
        assert tx.counterparty_iban == "DE02100500000024290661"
        assert tx.counterparty_bic == "BELADEBEXXX"
        assert tx.end_to_end_id == "E2E-2024-001"
        assert tx.mandate_id == "MNDT-001"
        assert tx.transaction_id == "REF001"

    def test_parse_credit_transaction(self, parser: CAMT053Parser) -> None:
        """Parst Gutschrift mit positivem Vorzeichen."""
        result = parser.parse(CAMT053_CREDIT)

        assert result.success is True
        assert len(result.transactions) == 1
        tx = result.transactions[0]

        assert tx.amount == Decimal("500.00")
        assert tx.counterparty_name == "Kunde AG"
        assert tx.counterparty_iban == "DE27100777770209299700"

    def test_parse_reference_text(self, parser: CAMT053Parser) -> None:
        """Extrahiert Verwendungszweck."""
        result = parser.parse(MINIMAL_CAMT053)

        tx = result.transactions[0]
        assert "Strom Maerz 2024" in tx.reference_text

    def test_parse_statistics(self, parser: CAMT053Parser) -> None:
        """Berechnet Statistiken korrekt."""
        result = parser.parse(MINIMAL_CAMT053)

        assert result.total_debits == Decimal("149.50")
        assert result.total_credits == Decimal("0")

    def test_parse_invalid_xml(self, parser: CAMT053Parser) -> None:
        """Fehler bei ungueltigem XML."""
        result = parser.parse("<invalid>xml without closing")

        assert result.success is False
        assert len(result.errors) > 0

    def test_parse_xml_without_namespace(self, parser: CAMT053Parser) -> None:
        """Behandelt XML ohne erkennbaren CAMT-Namespace."""
        content = '<?xml version="1.0"?><Root><Data>Test</Data></Root>'
        result = parser.parse(content)

        # No Stmt elements found -> error
        assert result.success is False

    def test_parse_bytes_content(self, parser: CAMT053Parser) -> None:
        """Dekodiert Bytes vor dem Parsing."""
        result = parser.parse(MINIMAL_CAMT053.encode("utf-8"))
        assert result.success is True

    def test_parse_transaction_type_detection(self, parser: CAMT053Parser) -> None:
        """Erkennt Transaktionstyp aus Buchungstext."""
        result = parser.parse(MINIMAL_CAMT053)

        tx = result.transactions[0]
        # AddtlNtryInf contains "Lastschrift"
        assert tx.transaction_type == TransactionType.DIRECT_DEBIT


class TestCAMT053ParserNamespace:
    """Tests fuer die Namespace-Erkennung."""

    @pytest.fixture
    def parser(self) -> CAMT053Parser:
        return CAMT053Parser()

    def test_detect_namespace_v02(self, parser: CAMT053Parser) -> None:
        """Erkennt Version 02 Namespace."""
        from defusedxml.ElementTree import fromstring
        root = fromstring(MINIMAL_CAMT053)
        ns = parser._detect_namespace(root)
        assert ns == "urn:iso:std:iso:20022:tech:xsd:camt.053.001.02"

    def test_detect_namespace_no_namespace(self, parser: CAMT053Parser) -> None:
        """Erkennt XML ohne Namespace wenn Stmt vorhanden."""
        from defusedxml.ElementTree import fromstring
        content = "<Root><Stmt><Ntry/></Stmt></Root>"
        root = fromstring(content)
        ns = parser._detect_namespace(root)
        assert ns == ""

    def test_detect_namespace_unknown(self, parser: CAMT053Parser) -> None:
        """Gibt None bei unbekanntem Namespace ohne Stmt."""
        from defusedxml.ElementTree import fromstring
        content = "<Root><Data/></Root>"
        root = fromstring(content)
        ns = parser._detect_namespace(root)
        assert ns is None
