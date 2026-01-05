"""
Tests for E-Invoice Generator and Validator Services.

Tests UBL 2.1, XRechnung, ZUGFeRD/CII generation and validation.
"""

import pytest
from datetime import date
from decimal import Decimal

from app.services.einvoice import (
    EInvoiceGeneratorService,
    EInvoiceValidatorService,
    get_einvoice_generator_service,
    get_einvoice_validator_service,
    EInvoiceFormat,
    InvoiceType,
    TaxCategory,
    PaymentMeansCode,
    Address,
    InvoiceData,
    InvoiceParty,
    InvoiceLineItem,
    TaxTotal,
    EInvoiceRequest,
    EInvoiceResponse,
    ValidationResult,
)


# ==================== Fixtures ====================

@pytest.fixture
def sample_address() -> Address:
    """Sample German address."""
    return Address(
        street_name="Musterstrasse",
        building_number="123",
        city="Berlin",
        postal_code="10115",
        country_code="DE",
    )


@pytest.fixture
def sample_seller(sample_address: Address) -> InvoiceParty:
    """Sample seller (Rechnungssteller)."""
    return InvoiceParty(
        name="Muster GmbH",
        address=sample_address,
        vat_id="DE123456789",
        tax_number="12/345/67890",
        contact_name="Max Mustermann",
        email="rechnung@muster.de",
        phone="+49 30 12345678",
        bank_account_iban="DE89370400440532013000",
        bank_account_bic="COBADEFFXXX",
        bank_account_name="Muster GmbH",
    )


@pytest.fixture
def sample_buyer(sample_address: Address) -> InvoiceParty:
    """Sample buyer (Rechnungsempfaenger)."""
    buyer_address = Address(
        street_name="Kundenweg",
        building_number="456",
        city="Hamburg",
        postal_code="20095",
        country_code="DE",
    )
    return InvoiceParty(
        name="Kunde AG",
        address=buyer_address,
        vat_id="DE987654321",
        contact_name="Erika Musterfrau",
        email="einkauf@kunde.de",
    )


@pytest.fixture
def sample_line_items() -> list:
    """Sample invoice line items."""
    return [
        InvoiceLineItem(
            line_id="1",
            description="Beratungsleistung IT-Sicherheit",
            quantity=Decimal("10.00"),
            unit_code="HUR",  # Hours
            unit_price=Decimal("120.00"),
            line_net_amount=Decimal("1200.00"),
            tax_category=TaxCategory.STANDARD,
            tax_percent=Decimal("19.00"),
        ),
        InvoiceLineItem(
            line_id="2",
            description="Softwarelizenz Jahreslizenz",
            quantity=Decimal("1.00"),
            unit_code="C62",  # Units
            unit_price=Decimal("599.00"),
            line_net_amount=Decimal("599.00"),
            tax_category=TaxCategory.STANDARD,
            tax_percent=Decimal("19.00"),
        ),
    ]


@pytest.fixture
def sample_tax_totals() -> list:
    """Sample tax totals."""
    return [
        TaxTotal(
            tax_amount=Decimal("341.81"),
            taxable_amount=Decimal("1799.00"),
            tax_category=TaxCategory.STANDARD,
            tax_percent=Decimal("19.00"),
        ),
    ]


@pytest.fixture
def sample_invoice_data(
    sample_seller: InvoiceParty,
    sample_buyer: InvoiceParty,
    sample_line_items: list,
    sample_tax_totals: list,
) -> InvoiceData:
    """Complete sample invoice data."""
    return InvoiceData(
        invoice_number="RE-2024-001234",
        invoice_type=InvoiceType.INVOICE,
        issue_date=date(2024, 12, 15),
        due_date=date(2025, 1, 15),
        currency_code="EUR",
        seller=sample_seller,
        buyer=sample_buyer,
        line_items=sample_line_items,
        total_net_amount=Decimal("1799.00"),
        total_tax_amount=Decimal("341.81"),
        total_gross_amount=Decimal("2140.81"),
        payable_amount=Decimal("2140.81"),
        tax_totals=sample_tax_totals,
        payment_means_code=PaymentMeansCode.SEPA_CREDIT_TRANSFER,
        note="Bitte ueberweisen Sie den Betrag innerhalb von 30 Tagen.",
    )


@pytest.fixture
def generator_service() -> EInvoiceGeneratorService:
    """Get generator service instance."""
    return get_einvoice_generator_service()


@pytest.fixture
def validator_service() -> EInvoiceValidatorService:
    """Get validator service instance."""
    return get_einvoice_validator_service()


# ==================== Generator Tests ====================

class TestEInvoiceGenerator:
    """Tests for E-Invoice generation."""

    @pytest.mark.asyncio
    async def test_generate_ubl_21(
        self,
        generator_service: EInvoiceGeneratorService,
        sample_invoice_data: InvoiceData,
    ):
        """Test UBL 2.1 invoice generation."""
        request = EInvoiceRequest(
            invoice_data=sample_invoice_data,
            format=EInvoiceFormat.UBL_21,
        )

        result = await generator_service.generate(request)

        assert isinstance(result, EInvoiceResponse)
        assert result.success is True
        assert result.format == EInvoiceFormat.UBL_21
        assert "Invoice" in result.xml_content  # ubl:Invoice or similar
        assert "urn:oasis:names:specification:ubl:schema:xsd:Invoice-2" in result.xml_content
        assert "RE-2024-001234" in result.xml_content
        assert "Muster GmbH" in result.xml_content
        assert "Kunde AG" in result.xml_content
        assert "DE123456789" in result.xml_content

    @pytest.mark.asyncio
    async def test_generate_xrechnung(
        self,
        generator_service: EInvoiceGeneratorService,
        sample_invoice_data: InvoiceData,
    ):
        """Test XRechnung generation with Leitweg-ID."""
        # Add Leitweg-ID (required for XRechnung)
        sample_invoice_data.buyer_reference = "04011000-12345-67"

        request = EInvoiceRequest(
            invoice_data=sample_invoice_data,
            format=EInvoiceFormat.XRECHNUNG_30,
        )

        result = await generator_service.generate(request)

        assert result.success is True
        assert result.format == EInvoiceFormat.XRECHNUNG_30
        assert "xrechnung" in result.xml_content.lower()
        assert "04011000-12345-67" in result.xml_content

    @pytest.mark.asyncio
    async def test_generate_zugferd(
        self,
        generator_service: EInvoiceGeneratorService,
        sample_invoice_data: InvoiceData,
    ):
        """Test ZUGFeRD/CII generation."""
        request = EInvoiceRequest(
            invoice_data=sample_invoice_data,
            format=EInvoiceFormat.ZUGFERD_21,
        )

        result = await generator_service.generate(request)

        assert result.success is True
        assert result.format == EInvoiceFormat.ZUGFERD_21
        assert "CrossIndustryInvoice" in result.xml_content
        assert "urn:un:unece:uncefact" in result.xml_content

    @pytest.mark.asyncio
    async def test_generate_cii(
        self,
        generator_service: EInvoiceGeneratorService,
        sample_invoice_data: InvoiceData,
    ):
        """Test CII D16B generation."""
        request = EInvoiceRequest(
            invoice_data=sample_invoice_data,
            format=EInvoiceFormat.CII_D16B,
        )

        result = await generator_service.generate(request)

        assert result.success is True
        assert result.format == EInvoiceFormat.CII_D16B
        assert "CrossIndustryInvoice" in result.xml_content

    @pytest.mark.asyncio
    async def test_generated_xml_is_parsable(
        self,
        generator_service: EInvoiceGeneratorService,
        sample_invoice_data: InvoiceData,
    ):
        """Test that generated XML is valid and parsable."""
        import xml.etree.ElementTree as ET

        for format_type in [EInvoiceFormat.UBL_21, EInvoiceFormat.ZUGFERD_21]:
            request = EInvoiceRequest(
                invoice_data=sample_invoice_data,
                format=format_type,
            )

            result = await generator_service.generate(request)

            # Should not raise
            root = ET.fromstring(result.xml_content)
            assert root is not None


# ==================== Validator Tests ====================

class TestEInvoiceValidator:
    """Tests for E-Invoice validation."""

    @pytest.mark.asyncio
    async def test_validate_generated_ubl(
        self,
        generator_service: EInvoiceGeneratorService,
        validator_service: EInvoiceValidatorService,
        sample_invoice_data: InvoiceData,
    ):
        """Test validation of generated UBL invoice."""
        # Generate
        request = EInvoiceRequest(
            invoice_data=sample_invoice_data,
            format=EInvoiceFormat.UBL_21,
        )
        generated = await generator_service.generate(request)

        # Validate
        result = await validator_service.validate(generated.xml_content)

        assert isinstance(result, ValidationResult)
        assert result.format_detected == EInvoiceFormat.UBL_21
        assert result.invoice_number == "RE-2024-001234"
        assert result.seller_name == "Muster GmbH"
        assert result.buyer_name == "Kunde AG"

    @pytest.mark.asyncio
    async def test_validate_generated_cii(
        self,
        generator_service: EInvoiceGeneratorService,
        validator_service: EInvoiceValidatorService,
        sample_invoice_data: InvoiceData,
    ):
        """Test validation of generated CII invoice."""
        # Generate
        request = EInvoiceRequest(
            invoice_data=sample_invoice_data,
            format=EInvoiceFormat.ZUGFERD_21,
        )
        generated = await generator_service.generate(request)

        # Validate
        result = await validator_service.validate(generated.xml_content)

        assert result.format_detected in [EInvoiceFormat.ZUGFERD_21, EInvoiceFormat.CII_D16B]
        assert result.invoice_number == "RE-2024-001234"

    @pytest.mark.asyncio
    async def test_detect_format_ubl(
        self,
        generator_service: EInvoiceGeneratorService,
        validator_service: EInvoiceValidatorService,
        sample_invoice_data: InvoiceData,
    ):
        """Test format auto-detection for UBL."""
        request = EInvoiceRequest(
            invoice_data=sample_invoice_data,
            format=EInvoiceFormat.UBL_21,
        )
        generated = await generator_service.generate(request)

        result = await validator_service.validate(generated.xml_content)

        assert result.format_detected == EInvoiceFormat.UBL_21

    @pytest.mark.asyncio
    async def test_detect_format_xrechnung(
        self,
        generator_service: EInvoiceGeneratorService,
        validator_service: EInvoiceValidatorService,
        sample_invoice_data: InvoiceData,
    ):
        """Test format auto-detection for XRechnung."""
        sample_invoice_data.buyer_reference = "04011000-12345-67"

        request = EInvoiceRequest(
            invoice_data=sample_invoice_data,
            format=EInvoiceFormat.XRECHNUNG_30,
        )
        generated = await generator_service.generate(request)

        result = await validator_service.validate(generated.xml_content)

        assert result.format_detected == EInvoiceFormat.XRECHNUNG_30

    @pytest.mark.asyncio
    async def test_validate_invalid_xml(
        self,
        validator_service: EInvoiceValidatorService,
    ):
        """Test validation of invalid XML."""
        invalid_xml = "<not-an-invoice>test</not-an-invoice>"

        result = await validator_service.validate(invalid_xml)

        assert result.is_valid is False
        assert result.format_detected is None
        assert len(result.errors) > 0

    @pytest.mark.asyncio
    async def test_validate_malformed_xml(
        self,
        validator_service: EInvoiceValidatorService,
    ):
        """Test validation of malformed XML."""
        malformed_xml = "<Invoice><unclosed"

        result = await validator_service.validate(malformed_xml)

        assert result.is_valid is False
        assert len(result.errors) > 0


# ==================== Schema Tests ====================

class TestEInvoiceSchemas:
    """Tests for E-Invoice Pydantic schemas."""

    def test_invoice_party_validation(self, sample_address: Address):
        """Test InvoiceParty field validation."""
        # Valid VAT ID
        party = InvoiceParty(
            name="Test GmbH",
            address=sample_address,
            vat_id="DE123456789",
        )
        assert party.vat_id == "DE123456789"

    def test_address_country_code_validation(self):
        """Test Address country code must be 2 letters."""
        # Valid
        address = Address(
            street_name="Test",
            city="Test",
            postal_code="12345",
            country_code="DE",
        )
        assert address.country_code == "DE"

    def test_invoice_line_item_quantity_positive(self):
        """Test line item quantity must be positive."""
        with pytest.raises(ValueError):
            InvoiceLineItem(
                line_id="1",
                description="Test",
                quantity=Decimal("0"),  # Must be > 0
                unit_price=Decimal("100.00"),
                line_net_amount=Decimal("0.00"),
            )

    def test_invoice_data_unique_line_ids(
        self,
        sample_seller: InvoiceParty,
        sample_buyer: InvoiceParty,
    ):
        """Test that line IDs must be unique."""
        duplicate_items = [
            InvoiceLineItem(
                line_id="1",
                description="Item 1",
                quantity=Decimal("1"),
                unit_price=Decimal("100"),
                line_net_amount=Decimal("100"),
            ),
            InvoiceLineItem(
                line_id="1",  # Duplicate ID
                description="Item 2",
                quantity=Decimal("1"),
                unit_price=Decimal("200"),
                line_net_amount=Decimal("200"),
            ),
        ]

        with pytest.raises(ValueError, match="eindeutig"):
            InvoiceData(
                invoice_number="TEST-001",
                issue_date=date.today(),
                seller=sample_seller,
                buyer=sample_buyer,
                line_items=duplicate_items,
                total_net_amount=Decimal("300"),
                total_tax_amount=Decimal("57"),
                total_gross_amount=Decimal("357"),
                payable_amount=Decimal("357"),
            )


# ==================== Integration Tests ====================

class TestEInvoiceRoundTrip:
    """Round-trip tests: generate → validate → verify."""

    @pytest.mark.asyncio
    async def test_roundtrip_all_formats(
        self,
        generator_service: EInvoiceGeneratorService,
        validator_service: EInvoiceValidatorService,
        sample_invoice_data: InvoiceData,
    ):
        """Test generation and validation for all formats."""
        formats_to_test = [
            (EInvoiceFormat.UBL_21, None),
            (EInvoiceFormat.XRECHNUNG_30, "04011000-12345-67"),
            (EInvoiceFormat.ZUGFERD_21, None),
            (EInvoiceFormat.CII_D16B, None),
        ]

        for format_type, leitweg_id in formats_to_test:
            # Add Leitweg-ID for XRechnung
            if leitweg_id:
                sample_invoice_data.buyer_reference = leitweg_id

            request = EInvoiceRequest(
                invoice_data=sample_invoice_data,
                format=format_type,
            )

            # Generate
            generated = await generator_service.generate(request)
            assert generated.success, f"Generation failed for {format_type}: {generated.validation_errors}"

            # Validate
            validated = await validator_service.validate(generated.xml_content)
            assert validated.invoice_number == "RE-2024-001234", f"Invoice number mismatch for {format_type}"

            # Clear Leitweg-ID for next iteration
            sample_invoice_data.buyer_reference = None
