# -*- coding: utf-8 -*-
"""
Unit Tests fuer ZUGFeRD Mapper.

Testet:
- XML -> ExtractedInvoiceData Konvertierung
- ExtractedInvoiceData -> XML Konvertierung
- Verschiedene ZUGFeRD-Profile
- XRechnung-spezifische Felder
"""

from datetime import date
from decimal import Decimal

import pytest

from app.api.schemas.extracted_data import (
    Currency,
    ExtractedAddress,
    ExtractedBankAccount,
    ExtractedInvoiceData,
    ExtractedLineItem,
    TaxBreakdownItem,
)
from app.services.einvoice.mapping.zugferd_mapper import ZUGFeRDMapper


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def mapper() -> ZUGFeRDMapper:
    """Gibt ZUGFeRD Mapper zurueck."""
    return ZUGFeRDMapper()


@pytest.fixture
def sample_invoice() -> ExtractedInvoiceData:
    """Beispiel-Rechnungsdaten fuer Tests."""
    return ExtractedInvoiceData(
        invoice_number="RE-2024-00123",
        invoice_date=date(2024, 12, 17),
        due_date=date(2025, 1, 17),
        sender=ExtractedAddress(
            company="Test GmbH",
            street="Teststrasse 1",
            zip_code="12345",
            city="Berlin",
            country="DE",
        ),
        sender_vat_id="DE123456789",
        sender_bank=ExtractedBankAccount(
            iban="DE89370400440532013000",
            bic="COBADEFFXXX",
            bank_name="Commerzbank",
        ),
        recipient=ExtractedAddress(
            company="Kunde AG",
            street="Kundenweg 42",
            zip_code="54321",
            city="Hamburg",
            country="DE",
        ),
        recipient_vat_id="DE987654321",
        net_amount=Decimal("1000.00"),
        vat_rate=Decimal("19.0"),
        vat_amount=Decimal("190.00"),
        gross_amount=Decimal("1190.00"),
        currency=Currency.EUR,
        line_items=[
            ExtractedLineItem(
                position=1,
                description="Beratungsleistung",
                quantity=Decimal("10"),
                unit="H",
                unit_price=Decimal("100.00"),
                total_price=Decimal("1000.00"),
                vat_rate=Decimal("19.0"),
            ),
        ],
        payment_terms="Zahlbar innerhalb 30 Tagen",
        buyer_reference="04011000-12345-67",  # Leitweg-ID
        invoice_type_code="380",
    )


@pytest.fixture
def sample_zugferd_xml() -> str:
    """Beispiel ZUGFeRD XML fuer Tests."""
    return """<?xml version="1.0" encoding="UTF-8"?>
<rsm:CrossIndustryInvoice
    xmlns:rsm="urn:un:unece:uncefact:data:standard:CrossIndustryInvoice:100"
    xmlns:ram="urn:un:unece:uncefact:data:standard:ReusableAggregateBusinessInformationEntity:100"
    xmlns:udt="urn:un:unece:uncefact:data:standard:UnqualifiedDataType:100"
    xmlns:qdt="urn:un:unece:uncefact:data:standard:QualifiedDataType:100">

    <rsm:ExchangedDocumentContext>
        <ram:GuidelineSpecifiedDocumentContextParameter>
            <ram:ID>urn:cen.eu:en16931:2017</ram:ID>
        </ram:GuidelineSpecifiedDocumentContextParameter>
    </rsm:ExchangedDocumentContext>

    <rsm:ExchangedDocument>
        <ram:ID>RE-2024-00456</ram:ID>
        <ram:TypeCode>380</ram:TypeCode>
        <ram:IssueDateTime>
            <udt:DateTimeString format="102">20241215</udt:DateTimeString>
        </ram:IssueDateTime>
    </rsm:ExchangedDocument>

    <rsm:SupplyChainTradeTransaction>
        <ram:ApplicableHeaderTradeAgreement>
            <ram:BuyerReference>04011000-12345-67</ram:BuyerReference>
            <ram:SellerTradeParty>
                <ram:Name>Lieferant GmbH</ram:Name>
                <ram:PostalTradeAddress>
                    <ram:PostcodeCode>10115</ram:PostcodeCode>
                    <ram:LineOne>Lieferantenstr. 1</ram:LineOne>
                    <ram:CityName>Berlin</ram:CityName>
                    <ram:CountryID>DE</ram:CountryID>
                </ram:PostalTradeAddress>
                <ram:SpecifiedTaxRegistration>
                    <ram:ID schemeID="VA">DE111111111</ram:ID>
                </ram:SpecifiedTaxRegistration>
            </ram:SellerTradeParty>
            <ram:BuyerTradeParty>
                <ram:Name>Kaeufer AG</ram:Name>
                <ram:PostalTradeAddress>
                    <ram:PostcodeCode>20095</ram:PostcodeCode>
                    <ram:LineOne>Kaeuferweg 2</ram:LineOne>
                    <ram:CityName>Hamburg</ram:CityName>
                    <ram:CountryID>DE</ram:CountryID>
                </ram:PostalTradeAddress>
            </ram:BuyerTradeParty>
        </ram:ApplicableHeaderTradeAgreement>

        <ram:ApplicableHeaderTradeDelivery/>

        <ram:ApplicableHeaderTradeSettlement>
            <ram:InvoiceCurrencyCode>EUR</ram:InvoiceCurrencyCode>
            <ram:ApplicableTradeTax>
                <ram:CalculatedAmount>190.00</ram:CalculatedAmount>
                <ram:TypeCode>VAT</ram:TypeCode>
                <ram:BasisAmount>1000.00</ram:BasisAmount>
                <ram:CategoryCode>S</ram:CategoryCode>
                <ram:RateApplicablePercent>19.00</ram:RateApplicablePercent>
            </ram:ApplicableTradeTax>
            <ram:SpecifiedTradeSettlementHeaderMonetarySummation>
                <ram:LineTotalAmount>1000.00</ram:LineTotalAmount>
                <ram:TaxBasisTotalAmount>1000.00</ram:TaxBasisTotalAmount>
                <ram:TaxTotalAmount currencyID="EUR">190.00</ram:TaxTotalAmount>
                <ram:GrandTotalAmount>1190.00</ram:GrandTotalAmount>
                <ram:DuePayableAmount>1190.00</ram:DuePayableAmount>
            </ram:SpecifiedTradeSettlementHeaderMonetarySummation>
        </ram:ApplicableHeaderTradeSettlement>
    </rsm:SupplyChainTradeTransaction>
</rsm:CrossIndustryInvoice>"""


# =============================================================================
# XML -> INVOICE DATA TESTS
# =============================================================================

class TestXmlToInvoiceData:
    """Tests fuer XML -> ExtractedInvoiceData Konvertierung."""

    def test_parse_basic_invoice(
        self, mapper: ZUGFeRDMapper, sample_zugferd_xml: str
    ) -> None:
        """Testet grundlegendes Parsen eines ZUGFeRD XML."""
        invoice_data, metadata = mapper.xml_to_invoice_data(sample_zugferd_xml)

        assert invoice_data.invoice_number == "RE-2024-00456"
        assert invoice_data.invoice_date == date(2024, 12, 15)
        assert invoice_data.buyer_reference == "04011000-12345-67"

    def test_parse_sender_party(
        self, mapper: ZUGFeRDMapper, sample_zugferd_xml: str
    ) -> None:
        """Testet Parsen der Absender-Daten."""
        invoice_data, _ = mapper.xml_to_invoice_data(sample_zugferd_xml)

        assert invoice_data.sender is not None
        assert invoice_data.sender.company == "Lieferant GmbH"
        assert invoice_data.sender.city == "Berlin"
        assert invoice_data.sender.zip_code == "10115"
        assert invoice_data.sender_vat_id == "DE111111111"

    def test_parse_amounts(
        self, mapper: ZUGFeRDMapper, sample_zugferd_xml: str
    ) -> None:
        """Testet Parsen der Betraege."""
        invoice_data, _ = mapper.xml_to_invoice_data(sample_zugferd_xml)

        assert invoice_data.net_amount == Decimal("1000.00")
        assert invoice_data.vat_amount == Decimal("190.00")
        assert invoice_data.gross_amount == Decimal("1190.00")
        assert invoice_data.vat_rate == Decimal("19.00")
        assert invoice_data.currency == Currency.EUR

    def test_parse_tax_breakdown(
        self, mapper: ZUGFeRDMapper, sample_zugferd_xml: str
    ) -> None:
        """Testet Parsen der MwSt-Aufschluesselung."""
        invoice_data, _ = mapper.xml_to_invoice_data(sample_zugferd_xml)

        assert len(invoice_data.tax_breakdown) == 1
        tax = invoice_data.tax_breakdown[0]
        assert tax.tax_category_code == "S"
        assert tax.tax_rate == Decimal("19.00")
        assert tax.taxable_amount == Decimal("1000.00")
        assert tax.tax_amount == Decimal("190.00")

    def test_parse_metadata(
        self, mapper: ZUGFeRDMapper, sample_zugferd_xml: str
    ) -> None:
        """Testet Extrahieren der Metadaten."""
        _, metadata = mapper.xml_to_invoice_data(sample_zugferd_xml)

        assert metadata["format"] == "zugferd"
        assert metadata["profile"] == "EN16931"
        assert "xml_hash" in metadata
        assert len(metadata["xml_hash"]) == 64  # SHA256

    def test_parse_sets_einvoice_fields(
        self, mapper: ZUGFeRDMapper, sample_zugferd_xml: str
    ) -> None:
        """Testet dass E-Invoice Metadaten gesetzt werden."""
        invoice_data, _ = mapper.xml_to_invoice_data(sample_zugferd_xml)

        assert invoice_data.einvoice_format == "zugferd"
        assert invoice_data.einvoice_profile == "EN16931"
        assert invoice_data.einvoice_xml_embedded is True

    def test_parse_invalid_xml_raises_error(self, mapper: ZUGFeRDMapper) -> None:
        """Testet dass ungültiges XML einen Fehler wirft."""
        with pytest.raises(ValueError, match="Ungueltiges XML"):
            mapper.xml_to_invoice_data("<invalid>xml<unclosed")


# =============================================================================
# INVOICE DATA -> XML TESTS
# =============================================================================

class TestInvoiceDataToXml:
    """Tests fuer ExtractedInvoiceData -> XML Konvertierung."""

    def test_generate_basic_xml(
        self, mapper: ZUGFeRDMapper, sample_invoice: ExtractedInvoiceData
    ) -> None:
        """Testet grundlegende XML-Generierung."""
        xml = mapper.invoice_data_to_xml(sample_invoice, "EN16931")

        assert "<?xml version" in xml
        assert "CrossIndustryInvoice" in xml
        assert "RE-2024-00123" in xml  # Rechnungsnummer

    def test_generate_contains_sender(
        self, mapper: ZUGFeRDMapper, sample_invoice: ExtractedInvoiceData
    ) -> None:
        """Testet dass Absender im XML enthalten ist."""
        xml = mapper.invoice_data_to_xml(sample_invoice, "EN16931")

        assert "Test GmbH" in xml
        assert "Berlin" in xml
        assert "DE123456789" in xml  # USt-IdNr

    def test_generate_contains_recipient(
        self, mapper: ZUGFeRDMapper, sample_invoice: ExtractedInvoiceData
    ) -> None:
        """Testet dass Empfaenger im XML enthalten ist."""
        xml = mapper.invoice_data_to_xml(sample_invoice, "EN16931")

        assert "Kunde AG" in xml
        assert "Hamburg" in xml

    def test_generate_contains_amounts(
        self, mapper: ZUGFeRDMapper, sample_invoice: ExtractedInvoiceData
    ) -> None:
        """Testet dass Betraege im XML enthalten sind."""
        xml = mapper.invoice_data_to_xml(sample_invoice, "EN16931")

        assert "1000.00" in xml  # Netto
        assert "190.00" in xml   # MwSt
        assert "1190.00" in xml  # Brutto

    def test_generate_xrechnung_profile(
        self, mapper: ZUGFeRDMapper, sample_invoice: ExtractedInvoiceData
    ) -> None:
        """Testet XRechnung-Profil Generierung."""
        xml = mapper.invoice_data_to_xml(sample_invoice, "XRECHNUNG")

        assert "xrechnung" in xml.lower() or "XRechnung" in xml
        assert "04011000-12345-67" in xml  # Leitweg-ID

    def test_generate_with_line_items(
        self, mapper: ZUGFeRDMapper, sample_invoice: ExtractedInvoiceData
    ) -> None:
        """Testet dass Positionen im XML enthalten sind."""
        xml = mapper.invoice_data_to_xml(sample_invoice, "EN16931")

        assert "Beratungsleistung" in xml
        assert "IncludedSupplyChainTradeLineItem" in xml

    def test_generate_missing_required_field_raises_error(
        self, mapper: ZUGFeRDMapper
    ) -> None:
        """Testet dass fehlende Pflichtfelder einen Fehler werfen."""
        incomplete_invoice = ExtractedInvoiceData()  # Leer

        with pytest.raises(ValueError, match="Rechnungsnummer"):
            mapper.invoice_data_to_xml(incomplete_invoice, "EN16931")

    def test_generate_xrechnung_without_leitweg_raises_error(
        self, mapper: ZUGFeRDMapper
    ) -> None:
        """Testet dass XRechnung ohne Leitweg-ID fehlschlaegt."""
        invoice = ExtractedInvoiceData(
            invoice_number="RE-001",
            invoice_date=date(2024, 12, 17),
            gross_amount=Decimal("100"),
            # buyer_reference fehlt
        )

        with pytest.raises(ValueError, match="Leitweg-ID"):
            mapper.invoice_data_to_xml(invoice, "XRECHNUNG")


# =============================================================================
# ROUNDTRIP TESTS
# =============================================================================

class TestRoundtrip:
    """Tests fuer XML -> InvoiceData -> XML Roundtrip."""

    def test_roundtrip_preserves_data(
        self, mapper: ZUGFeRDMapper, sample_invoice: ExtractedInvoiceData
    ) -> None:
        """Testet dass Daten bei Roundtrip erhalten bleiben."""
        # Generate XML
        xml1 = mapper.invoice_data_to_xml(sample_invoice, "EN16931")

        # Parse back
        parsed, _ = mapper.xml_to_invoice_data(xml1)

        # Check key fields preserved
        assert parsed.invoice_number == sample_invoice.invoice_number
        assert parsed.invoice_date == sample_invoice.invoice_date
        assert parsed.gross_amount == sample_invoice.gross_amount
        assert parsed.currency == sample_invoice.currency

    def test_roundtrip_preserves_parties(
        self, mapper: ZUGFeRDMapper, sample_invoice: ExtractedInvoiceData
    ) -> None:
        """Testet dass Parteien bei Roundtrip erhalten bleiben."""
        xml = mapper.invoice_data_to_xml(sample_invoice, "EN16931")
        parsed, _ = mapper.xml_to_invoice_data(xml)

        assert parsed.sender is not None
        assert parsed.sender.company == sample_invoice.sender.company
        assert parsed.sender.city == sample_invoice.sender.city

        assert parsed.recipient is not None
        assert parsed.recipient.company == sample_invoice.recipient.company


# =============================================================================
# EDGE CASES
# =============================================================================

class TestEdgeCases:
    """Tests fuer Grenzfaelle."""

    def test_parse_xml_bytes(
        self, mapper: ZUGFeRDMapper, sample_zugferd_xml: str
    ) -> None:
        """Testet Parsen von XML als Bytes."""
        xml_bytes = sample_zugferd_xml.encode("utf-8")
        invoice_data, _ = mapper.xml_to_invoice_data(xml_bytes)

        assert invoice_data.invoice_number == "RE-2024-00456"

    def test_parse_empty_optional_fields(self, mapper: ZUGFeRDMapper) -> None:
        """Testet Parsen mit leeren optionalen Feldern."""
        minimal_xml = """<?xml version="1.0" encoding="UTF-8"?>
<rsm:CrossIndustryInvoice
    xmlns:rsm="urn:un:unece:uncefact:data:standard:CrossIndustryInvoice:100"
    xmlns:ram="urn:un:unece:uncefact:data:standard:ReusableAggregateBusinessInformationEntity:100"
    xmlns:udt="urn:un:unece:uncefact:data:standard:UnqualifiedDataType:100">
    <rsm:ExchangedDocumentContext>
        <ram:GuidelineSpecifiedDocumentContextParameter>
            <ram:ID>urn:factur-x.eu:1p0:minimum</ram:ID>
        </ram:GuidelineSpecifiedDocumentContextParameter>
    </rsm:ExchangedDocumentContext>
    <rsm:ExchangedDocument>
        <ram:ID>MIN-001</ram:ID>
        <ram:TypeCode>380</ram:TypeCode>
        <ram:IssueDateTime>
            <udt:DateTimeString format="102">20241217</udt:DateTimeString>
        </ram:IssueDateTime>
    </rsm:ExchangedDocument>
    <rsm:SupplyChainTradeTransaction>
        <ram:ApplicableHeaderTradeAgreement>
            <ram:SellerTradeParty>
                <ram:Name>Minimal GmbH</ram:Name>
            </ram:SellerTradeParty>
            <ram:BuyerTradeParty>
                <ram:Name>Buyer Corp</ram:Name>
            </ram:BuyerTradeParty>
        </ram:ApplicableHeaderTradeAgreement>
        <ram:ApplicableHeaderTradeDelivery/>
        <ram:ApplicableHeaderTradeSettlement>
            <ram:InvoiceCurrencyCode>EUR</ram:InvoiceCurrencyCode>
            <ram:SpecifiedTradeSettlementHeaderMonetarySummation>
                <ram:GrandTotalAmount>100.00</ram:GrandTotalAmount>
            </ram:SpecifiedTradeSettlementHeaderMonetarySummation>
        </ram:ApplicableHeaderTradeSettlement>
    </rsm:SupplyChainTradeTransaction>
</rsm:CrossIndustryInvoice>"""

        invoice_data, metadata = mapper.xml_to_invoice_data(minimal_xml)

        assert invoice_data.invoice_number == "MIN-001"
        assert invoice_data.gross_amount == Decimal("100.00")
        assert invoice_data.sender is not None
        assert invoice_data.sender.company == "Minimal GmbH"
        assert metadata["profile"] == "MINIMUM"

    def test_multiple_tax_rates(self, mapper: ZUGFeRDMapper) -> None:
        """Testet Parsen mehrerer Steuersaetze."""
        multi_tax_xml = """<?xml version="1.0" encoding="UTF-8"?>
<rsm:CrossIndustryInvoice
    xmlns:rsm="urn:un:unece:uncefact:data:standard:CrossIndustryInvoice:100"
    xmlns:ram="urn:un:unece:uncefact:data:standard:ReusableAggregateBusinessInformationEntity:100"
    xmlns:udt="urn:un:unece:uncefact:data:standard:UnqualifiedDataType:100">
    <rsm:ExchangedDocumentContext>
        <ram:GuidelineSpecifiedDocumentContextParameter>
            <ram:ID>urn:cen.eu:en16931:2017</ram:ID>
        </ram:GuidelineSpecifiedDocumentContextParameter>
    </rsm:ExchangedDocumentContext>
    <rsm:ExchangedDocument>
        <ram:ID>MULTI-TAX-001</ram:ID>
        <ram:TypeCode>380</ram:TypeCode>
        <ram:IssueDateTime>
            <udt:DateTimeString format="102">20241217</udt:DateTimeString>
        </ram:IssueDateTime>
    </rsm:ExchangedDocument>
    <rsm:SupplyChainTradeTransaction>
        <ram:ApplicableHeaderTradeAgreement>
            <ram:SellerTradeParty><ram:Name>Multi GmbH</ram:Name></ram:SellerTradeParty>
            <ram:BuyerTradeParty><ram:Name>Buyer Corp</ram:Name></ram:BuyerTradeParty>
        </ram:ApplicableHeaderTradeAgreement>
        <ram:ApplicableHeaderTradeDelivery/>
        <ram:ApplicableHeaderTradeSettlement>
            <ram:InvoiceCurrencyCode>EUR</ram:InvoiceCurrencyCode>
            <ram:ApplicableTradeTax>
                <ram:CalculatedAmount>190.00</ram:CalculatedAmount>
                <ram:TypeCode>VAT</ram:TypeCode>
                <ram:BasisAmount>1000.00</ram:BasisAmount>
                <ram:CategoryCode>S</ram:CategoryCode>
                <ram:RateApplicablePercent>19.00</ram:RateApplicablePercent>
            </ram:ApplicableTradeTax>
            <ram:ApplicableTradeTax>
                <ram:CalculatedAmount>7.00</ram:CalculatedAmount>
                <ram:TypeCode>VAT</ram:TypeCode>
                <ram:BasisAmount>100.00</ram:BasisAmount>
                <ram:CategoryCode>S</ram:CategoryCode>
                <ram:RateApplicablePercent>7.00</ram:RateApplicablePercent>
            </ram:ApplicableTradeTax>
            <ram:SpecifiedTradeSettlementHeaderMonetarySummation>
                <ram:LineTotalAmount>1100.00</ram:LineTotalAmount>
                <ram:TaxTotalAmount currencyID="EUR">197.00</ram:TaxTotalAmount>
                <ram:GrandTotalAmount>1297.00</ram:GrandTotalAmount>
            </ram:SpecifiedTradeSettlementHeaderMonetarySummation>
        </ram:ApplicableHeaderTradeSettlement>
    </rsm:SupplyChainTradeTransaction>
</rsm:CrossIndustryInvoice>"""

        invoice_data, _ = mapper.xml_to_invoice_data(multi_tax_xml)

        assert len(invoice_data.tax_breakdown) == 2
        rates = {t.tax_rate for t in invoice_data.tax_breakdown}
        assert Decimal("19.00") in rates
        assert Decimal("7.00") in rates
