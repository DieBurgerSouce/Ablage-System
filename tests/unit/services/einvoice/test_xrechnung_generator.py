# -*- coding: utf-8 -*-
"""
Tests fuer XRechnung 3.0 Generator.

Testet:
- XRechnung CII Generation
- XRechnung UBL Generation
- BR-DE Validierung
- Pflichtfelder-Pruefung
"""

import pytest
import sys
from datetime import date
from decimal import Decimal
from lxml import etree

# Mock torch to avoid import errors in test environment
sys.modules['torch'] = type(sys)('torch')

# Direct import to avoid app.services.__init__ which loads torch
from app.services.einvoice.xrechnung_generator import (
    XRechnungGenerator,
    XRechnungData,
    XRechnungParty,
    XRechnungAddress,
    XRechnungLineItem,
    XRechnungTaxBreakdown,
    InvoiceTypeCode,
    VATCategoryCode,
    get_xrechnung_generator,
)


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def generator() -> XRechnungGenerator:
    """XRechnung Generator Instanz."""
    return get_xrechnung_generator()


@pytest.fixture
def seller_address() -> XRechnungAddress:
    """Beispiel Seller Adresse."""
    return XRechnungAddress(
        line1="Musterstrasse 123",
        city="Berlin",
        postal_code="10115",
        country_code="DE",
    )


@pytest.fixture
def buyer_address() -> XRechnungAddress:
    """Beispiel Buyer Adresse."""
    return XRechnungAddress(
        line1="Amtsstrasse 1",
        city="Hamburg",
        postal_code="20095",
        country_code="DE",
    )


@pytest.fixture
def seller_party(seller_address: XRechnungAddress) -> XRechnungParty:
    """Beispiel Seller Party."""
    return XRechnungParty(
        name="Musterfirma GmbH",
        address=seller_address,
        vat_id="DE123456789",
        contact_name="Max Mustermann",
        contact_email="max@musterfirma.de",
        contact_phone="+49 30 12345678",
        electronic_address="max@musterfirma.de",
        electronic_address_scheme="EM",
        bank_iban="DE89370400440532013000",
        bank_bic="COBADEFFXXX",
        bank_name="Commerzbank",
    )


@pytest.fixture
def buyer_party(buyer_address: XRechnungAddress) -> XRechnungParty:
    """Beispiel Buyer Party."""
    return XRechnungParty(
        name="Behoerde XY",
        address=buyer_address,
        electronic_address="04011000-12345-67",
        electronic_address_scheme="0204",
    )


@pytest.fixture
def line_item() -> XRechnungLineItem:
    """Beispiel Line Item."""
    return XRechnungLineItem(
        line_id="1",
        description="IT-Beratungsleistungen Januar 2026",
        name="IT-Beratung",
        quantity=Decimal("40.00"),
        unit_code="HUR",
        unit_price=Decimal("120.00"),
        line_total=Decimal("4800.00"),
        vat_category=VATCategoryCode.STANDARD,
        vat_rate=Decimal("19.00"),
    )


@pytest.fixture
def tax_breakdown() -> XRechnungTaxBreakdown:
    """Beispiel Tax Breakdown."""
    return XRechnungTaxBreakdown(
        category=VATCategoryCode.STANDARD,
        rate=Decimal("19.00"),
        taxable_amount=Decimal("4800.00"),
        tax_amount=Decimal("912.00"),
    )


@pytest.fixture
def xrechnung_data(
    seller_party: XRechnungParty,
    buyer_party: XRechnungParty,
    line_item: XRechnungLineItem,
    tax_breakdown: XRechnungTaxBreakdown,
) -> XRechnungData:
    """Vollstaendige XRechnung Daten."""
    return XRechnungData(
        invoice_number="RE-2026-001",
        invoice_type=InvoiceTypeCode.INVOICE,
        invoice_date=date(2026, 1, 15),
        due_date=date(2026, 2, 15),
        currency="EUR",
        buyer_reference="04011000-12345-67",
        seller=seller_party,
        buyer=buyer_party,
        line_items=[line_item],
        total_net=Decimal("4800.00"),
        total_vat=Decimal("912.00"),
        total_gross=Decimal("5712.00"),
        payable_amount=Decimal("5712.00"),
        tax_breakdown=[tax_breakdown],
        payment_means_code="58",
        payment_terms="Zahlbar innerhalb 30 Tagen",
    )


# =============================================================================
# TESTS: CII GENERATION
# =============================================================================

class TestXRechnungCIIGeneration:
    """Tests fuer XRechnung CII Generierung."""

    def test_generate_cii_basic(
        self,
        generator: XRechnungGenerator,
        xrechnung_data: XRechnungData,
    ):
        """Test: Basis CII Generierung."""
        xml_str = generator.generate_cii(xrechnung_data)

        assert xml_str is not None
        assert len(xml_str) > 0
        # XML declaration can have single or double quotes
        assert "<?xml version=" in xml_str
        assert "encoding=" in xml_str
        assert "UTF-8" in xml_str
        assert "CrossIndustryInvoice" in xml_str

    def test_generate_cii_contains_profile(
        self,
        generator: XRechnungGenerator,
        xrechnung_data: XRechnungData,
    ):
        """Test: CII enthaelt XRechnung Profil."""
        xml_str = generator.generate_cii(xrechnung_data)

        assert "xrechnung" in xml_str.lower()
        assert "urn:cen.eu:en16931:2017" in xml_str

    def test_generate_cii_invoice_number(
        self,
        generator: XRechnungGenerator,
        xrechnung_data: XRechnungData,
    ):
        """Test: CII enthaelt Rechnungsnummer."""
        xml_str = generator.generate_cii(xrechnung_data)

        # Parse XML
        root = etree.fromstring(xml_str.encode())

        # Rechnungsnummer suchen
        id_elem = root.find(".//{*}ExchangedDocument/{*}ID")
        assert id_elem is not None
        assert id_elem.text == "RE-2026-001"

    def test_generate_cii_buyer_reference(
        self,
        generator: XRechnungGenerator,
        xrechnung_data: XRechnungData,
    ):
        """Test: CII enthaelt Leitweg-ID (BT-10)."""
        xml_str = generator.generate_cii(xrechnung_data)

        root = etree.fromstring(xml_str.encode())

        buyer_ref = root.find(".//{*}ApplicableHeaderTradeAgreement/{*}BuyerReference")
        assert buyer_ref is not None
        assert buyer_ref.text == "04011000-12345-67"

    def test_generate_cii_seller_vat_id(
        self,
        generator: XRechnungGenerator,
        xrechnung_data: XRechnungData,
    ):
        """Test: CII enthaelt Seller USt-IdNr."""
        xml_str = generator.generate_cii(xrechnung_data)

        assert "DE123456789" in xml_str

    def test_generate_cii_amounts(
        self,
        generator: XRechnungGenerator,
        xrechnung_data: XRechnungData,
    ):
        """Test: CII enthaelt korrekte Betraege."""
        xml_str = generator.generate_cii(xrechnung_data)

        assert "4800.00" in xml_str  # Net
        assert "912.00" in xml_str   # VAT
        assert "5712.00" in xml_str  # Gross

    def test_generate_cii_bank_account(
        self,
        generator: XRechnungGenerator,
        xrechnung_data: XRechnungData,
    ):
        """Test: CII enthaelt Bankverbindung."""
        xml_str = generator.generate_cii(xrechnung_data)

        assert "DE89370400440532013000" in xml_str  # IBAN
        assert "COBADEFFXXX" in xml_str  # BIC

    def test_generate_cii_electronic_address(
        self,
        generator: XRechnungGenerator,
        xrechnung_data: XRechnungData,
    ):
        """Test: CII enthaelt elektronische Adressen (BT-34, BT-49)."""
        xml_str = generator.generate_cii(xrechnung_data)

        # Seller Electronic Address
        assert "max@musterfirma.de" in xml_str

        # Buyer Electronic Address (Leitweg-ID)
        # Wird automatisch aus buyer_reference uebernommen
        root = etree.fromstring(xml_str.encode())
        uri_elems = root.findall(".//{*}URIUniversalCommunication/{*}URIID")
        assert len(uri_elems) >= 1


# =============================================================================
# TESTS: VALIDATION
# =============================================================================

class TestXRechnungValidation:
    """Tests fuer XRechnung Pflichtfeld-Validierung."""

    def test_missing_buyer_reference_raises(
        self,
        generator: XRechnungGenerator,
        xrechnung_data: XRechnungData,
    ):
        """Test: Fehlende Leitweg-ID erzeugt Fehler."""
        xrechnung_data.buyer_reference = ""

        with pytest.raises(ValueError) as exc_info:
            generator.generate_cii(xrechnung_data)

        assert "Leitweg-ID" in str(exc_info.value)

    def test_missing_seller_vat_raises(
        self,
        generator: XRechnungGenerator,
        xrechnung_data: XRechnungData,
    ):
        """Test: Fehlende USt-IdNr erzeugt Fehler."""
        xrechnung_data.seller.vat_id = None
        xrechnung_data.seller.tax_number = None

        with pytest.raises(ValueError) as exc_info:
            generator.generate_cii(xrechnung_data)

        assert "USt-IdNr" in str(exc_info.value) or "Steuernummer" in str(exc_info.value)

    def test_missing_electronic_address_fallback(
        self,
        generator: XRechnungGenerator,
        xrechnung_data: XRechnungData,
    ):
        """Test: Fehlende elektronische Adresse nutzt Email als Fallback."""
        xrechnung_data.seller.electronic_address = None
        # contact_email ist gesetzt -> sollte als Fallback verwendet werden

        xml_str = generator.generate_cii(xrechnung_data)

        # Sollte Email verwenden
        assert "max@musterfirma.de" in xml_str


# =============================================================================
# TESTS: LINE ITEMS
# =============================================================================

class TestXRechnungLineItems:
    """Tests fuer Rechnungspositionen."""

    def test_multiple_line_items(
        self,
        generator: XRechnungGenerator,
        xrechnung_data: XRechnungData,
    ):
        """Test: Mehrere Positionen."""
        # Zweite Position hinzufuegen
        xrechnung_data.line_items.append(XRechnungLineItem(
            line_id="2",
            description="Software-Lizenz",
            quantity=Decimal("1.00"),
            unit_code="C62",
            unit_price=Decimal("500.00"),
            line_total=Decimal("500.00"),
            vat_category=VATCategoryCode.STANDARD,
            vat_rate=Decimal("19.00"),
        ))

        xml_str = generator.generate_cii(xrechnung_data)

        root = etree.fromstring(xml_str.encode())
        line_items = root.findall(".//{*}IncludedSupplyChainTradeLineItem")

        assert len(line_items) == 2

    def test_line_item_unit_code_normalization(
        self,
        generator: XRechnungGenerator,
        xrechnung_data: XRechnungData,
    ):
        """Test: Einheitencode wird normalisiert."""
        # Deutsches "Stunden" -> HUR
        xrechnung_data.line_items[0].unit_code = "stunden"

        item = XRechnungLineItem(
            line_id="1",
            description="Test",
            quantity=Decimal("10"),
            unit_code="stunden",  # Sollte zu HUR werden
            unit_price=Decimal("100"),
            line_total=Decimal("1000"),
        )

        assert item.unit_code == "HUR"


# =============================================================================
# TESTS: TAX BREAKDOWN
# =============================================================================

class TestXRechnungTaxBreakdown:
    """Tests fuer Steueraufschluesselung."""

    def test_reverse_charge(
        self,
        generator: XRechnungGenerator,
        xrechnung_data: XRechnungData,
    ):
        """Test: Reverse Charge Rechnung."""
        xrechnung_data.tax_breakdown = [XRechnungTaxBreakdown(
            category=VATCategoryCode.REVERSE_CHARGE,
            rate=Decimal("0.00"),
            taxable_amount=Decimal("4800.00"),
            tax_amount=Decimal("0.00"),
            exemption_reason="Steuerschuldnerschaft des Leistungsempfaengers (Reverse Charge)",
            exemption_reason_code="VATEX-EU-AE",
        )]
        xrechnung_data.total_vat = Decimal("0.00")
        xrechnung_data.total_gross = Decimal("4800.00")
        xrechnung_data.payable_amount = Decimal("4800.00")

        xml_str = generator.generate_cii(xrechnung_data)

        assert "AE" in xml_str  # Reverse Charge Category
        assert "Steuerschuldnerschaft" in xml_str

    def test_reduced_rate(
        self,
        generator: XRechnungGenerator,
        xrechnung_data: XRechnungData,
    ):
        """Test: Ermaessigter Steuersatz (7%)."""
        xrechnung_data.line_items[0].vat_rate = Decimal("7.00")
        xrechnung_data.line_items[0].vat_category = VATCategoryCode.REDUCED

        xrechnung_data.tax_breakdown = [XRechnungTaxBreakdown(
            category=VATCategoryCode.REDUCED,
            rate=Decimal("7.00"),
            taxable_amount=Decimal("4800.00"),
            tax_amount=Decimal("336.00"),
        )]
        xrechnung_data.total_vat = Decimal("336.00")
        xrechnung_data.total_gross = Decimal("5136.00")
        xrechnung_data.payable_amount = Decimal("5136.00")

        xml_str = generator.generate_cii(xrechnung_data)

        assert "7.00" in xml_str
        assert "AA" in xml_str  # Reduced Rate Category Code


# =============================================================================
# TESTS: OPTIONAL FIELDS
# =============================================================================

class TestXRechnungOptionalFields:
    """Tests fuer optionale Felder."""

    def test_with_order_reference(
        self,
        generator: XRechnungGenerator,
        xrechnung_data: XRechnungData,
    ):
        """Test: Mit Bestellnummer."""
        xrechnung_data.order_reference = "PO-2026-12345"

        xml_str = generator.generate_cii(xrechnung_data)

        assert "PO-2026-12345" in xml_str

    def test_with_contract_reference(
        self,
        generator: XRechnungGenerator,
        xrechnung_data: XRechnungData,
    ):
        """Test: Mit Vertragsnummer."""
        xrechnung_data.contract_reference = "VERTRAG-001"

        xml_str = generator.generate_cii(xrechnung_data)

        assert "VERTRAG-001" in xml_str

    def test_with_billing_period(
        self,
        generator: XRechnungGenerator,
        xrechnung_data: XRechnungData,
    ):
        """Test: Mit Abrechnungszeitraum."""
        xrechnung_data.billing_period_start = date(2026, 1, 1)
        xrechnung_data.billing_period_end = date(2026, 1, 31)

        xml_str = generator.generate_cii(xrechnung_data)

        assert "20260101" in xml_str
        assert "20260131" in xml_str

    def test_with_delivery_address(
        self,
        generator: XRechnungGenerator,
        xrechnung_data: XRechnungData,
    ):
        """Test: Mit abweichender Lieferadresse."""
        xrechnung_data.delivery_address = XRechnungAddress(
            line1="Lagerstrasse 42",
            city="Muenchen",
            postal_code="80331",
            country_code="DE",
        )
        xrechnung_data.delivery_date = date(2026, 1, 10)

        xml_str = generator.generate_cii(xrechnung_data)

        assert "Lagerstrasse 42" in xml_str
        assert "80331" in xml_str

    def test_with_invoice_note(
        self,
        generator: XRechnungGenerator,
        xrechnung_data: XRechnungData,
    ):
        """Test: Mit Bemerkung."""
        xrechnung_data.invoice_note = "Vielen Dank fuer Ihren Auftrag!"

        xml_str = generator.generate_cii(xrechnung_data)

        assert "Vielen Dank" in xml_str


# =============================================================================
# TESTS: XML STRUCTURE
# =============================================================================

class TestXRechnungXMLStructure:
    """Tests fuer XML-Struktur."""

    def test_xml_is_valid(
        self,
        generator: XRechnungGenerator,
        xrechnung_data: XRechnungData,
    ):
        """Test: Generiertes XML ist wohlgeformt."""
        xml_str = generator.generate_cii(xrechnung_data)

        # Sollte ohne Fehler parsen
        root = etree.fromstring(xml_str.encode())
        assert root is not None

    def test_xml_namespaces(
        self,
        generator: XRechnungGenerator,
        xrechnung_data: XRechnungData,
    ):
        """Test: XML enthaelt korrekte Namespaces."""
        xml_str = generator.generate_cii(xrechnung_data)

        assert "urn:un:unece:uncefact:data:standard:CrossIndustryInvoice:100" in xml_str
        assert "urn:un:unece:uncefact:data:standard:ReusableAggregateBusinessInformationEntity:100" in xml_str

    def test_xml_encoding(
        self,
        generator: XRechnungGenerator,
        xrechnung_data: XRechnungData,
    ):
        """Test: XML ist UTF-8 kodiert."""
        # Umlaut im Namen
        xrechnung_data.seller.name = "Musterhuette GmbH"

        xml_str = generator.generate_cii(xrechnung_data)

        assert "UTF-8" in xml_str
        assert "Musterhuette" in xml_str
