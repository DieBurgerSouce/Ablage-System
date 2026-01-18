"""
Tests for E-Invoice Validator Service and Models.

Tests validation service and Pydantic models for e-invoice data.
"""

import pytest
from datetime import date, datetime, timezone
from decimal import Decimal

from app.services.einvoice import (
    EInvoiceValidatorService,
    ValidationResult,
    ValidationMessage,
    ValidationSeverity,
    ValidatorType,
    get_validator_service,
)
from app.services.einvoice.einvoice_models import (
    EInvoiceFormat,
    InvoiceType,
    TaxCategory,
    PaymentMeansCode,
    Address,
    InvoiceData,
    InvoiceParty,
    InvoiceLineItem,
    TaxTotal,
    PaymentTerms,
)


# ==================== Model Tests ====================

class TestEInvoiceModels:
    """Tests for E-Invoice Pydantic models."""

    def test_einvoice_format_enum(self) -> None:
        """Test EInvoiceFormat enum values."""
        assert EInvoiceFormat.UBL_21 == "ubl_2.1"
        assert EInvoiceFormat.ZUGFERD_21 == "zugferd_2.1"
        assert EInvoiceFormat.XRECHNUNG_30 == "xrechnung_3.0"
        assert EInvoiceFormat.CII_D16B == "cii_d16b"

    def test_invoice_type_enum(self) -> None:
        """Test InvoiceType enum values."""
        assert InvoiceType.INVOICE == "380"
        assert InvoiceType.CREDIT_NOTE == "381"
        assert InvoiceType.CORRECTED_INVOICE == "384"

    def test_tax_category_enum(self) -> None:
        """Test TaxCategory enum values."""
        assert TaxCategory.STANDARD == "S"
        assert TaxCategory.REDUCED == "AA"
        assert TaxCategory.ZERO_RATED == "Z"
        assert TaxCategory.EXEMPT == "E"

    def test_payment_means_code_enum(self) -> None:
        """Test PaymentMeansCode enum values."""
        assert PaymentMeansCode.SEPA_CREDIT_TRANSFER == "58"
        assert PaymentMeansCode.SEPA_DIRECT_DEBIT == "59"
        assert PaymentMeansCode.CREDIT_TRANSFER == "30"


class TestAddressModel:
    """Tests for Address model."""

    def test_address_creation_minimal(self) -> None:
        """Test Address with required fields only."""
        address = Address(
            street_name="Musterstrasse",
            city="Berlin",
            postal_code="10115",
        )
        assert address.street_name == "Musterstrasse"
        assert address.city == "Berlin"
        assert address.postal_code == "10115"
        assert address.country_code == "DE"  # Default

    def test_address_creation_full(self) -> None:
        """Test Address with all fields."""
        address = Address(
            street_name="Musterstrasse",
            building_number="123",
            additional_street="Hinterhaus",
            city="Berlin",
            postal_code="10115",
            country_code="AT",
            country_subdivision="Wien",
        )
        assert address.building_number == "123"
        assert address.country_code == "AT"

    def test_address_country_code_validation(self) -> None:
        """Test country code must be 2 uppercase letters."""
        # Valid
        address = Address(
            street_name="Test",
            city="Test",
            postal_code="12345",
            country_code="DE",
        )
        assert address.country_code == "DE"


class TestInvoicePartyModel:
    """Tests for InvoiceParty model."""

    @pytest.fixture
    def sample_address(self) -> Address:
        """Sample address fixture."""
        return Address(
            street_name="Musterstrasse",
            building_number="123",
            city="Berlin",
            postal_code="10115",
            country_code="DE",
        )

    def test_invoice_party_minimal(self, sample_address: Address) -> None:
        """Test InvoiceParty with minimal fields."""
        party = InvoiceParty(
            name="Muster GmbH",
            address=sample_address,
        )
        assert party.name == "Muster GmbH"
        assert party.address.city == "Berlin"

    def test_invoice_party_with_vat_id(self, sample_address: Address) -> None:
        """Test InvoiceParty with VAT ID."""
        party = InvoiceParty(
            name="Muster GmbH",
            address=sample_address,
            vat_id="DE123456789",
        )
        assert party.vat_id == "DE123456789"

    def test_invoice_party_with_bank_details(self, sample_address: Address) -> None:
        """Test InvoiceParty with bank details."""
        party = InvoiceParty(
            name="Muster GmbH",
            address=sample_address,
            bank_account_iban="DE89370400440532013000",
            bank_account_bic="COBADEFFXXX",
            bank_account_name="Muster GmbH",
        )
        assert party.bank_account_iban == "DE89370400440532013000"


class TestInvoiceLineItemModel:
    """Tests for InvoiceLineItem model."""

    def test_line_item_creation(self) -> None:
        """Test InvoiceLineItem creation."""
        item = InvoiceLineItem(
            line_id="1",
            description="Beratungsleistung",
            quantity=Decimal("10.00"),
            unit_price=Decimal("120.00"),
            line_net_amount=Decimal("1200.00"),
        )
        assert item.line_id == "1"
        assert item.quantity == Decimal("10.00")
        assert item.line_net_amount == Decimal("1200.00")

    def test_line_item_with_tax(self) -> None:
        """Test InvoiceLineItem with tax details."""
        item = InvoiceLineItem(
            line_id="1",
            description="Test",
            quantity=Decimal("1"),
            unit_price=Decimal("100"),
            line_net_amount=Decimal("100"),
            tax_category=TaxCategory.STANDARD,
            tax_percent=Decimal("19.00"),
        )
        assert item.tax_category == TaxCategory.STANDARD
        assert item.tax_percent == Decimal("19.00")

    def test_line_item_quantity_must_be_positive(self) -> None:
        """Test line item quantity validation."""
        with pytest.raises(ValueError):
            InvoiceLineItem(
                line_id="1",
                description="Test",
                quantity=Decimal("0"),  # Must be > 0
                unit_price=Decimal("100.00"),
                line_net_amount=Decimal("0.00"),
            )


class TestTaxTotalModel:
    """Tests for TaxTotal model."""

    def test_tax_total_creation(self) -> None:
        """Test TaxTotal creation."""
        tax = TaxTotal(
            tax_amount=Decimal("19.00"),
            taxable_amount=Decimal("100.00"),
            tax_percent=Decimal("19.00"),
        )
        assert tax.tax_amount == Decimal("19.00")
        assert tax.taxable_amount == Decimal("100.00")


class TestInvoiceDataModel:
    """Tests for complete InvoiceData model."""

    @pytest.fixture
    def sample_address(self) -> Address:
        """Sample address fixture."""
        return Address(
            street_name="Musterstrasse",
            city="Berlin",
            postal_code="10115",
        )

    @pytest.fixture
    def sample_seller(self, sample_address: Address) -> InvoiceParty:
        """Sample seller fixture."""
        return InvoiceParty(
            name="Muster GmbH",
            address=sample_address,
            vat_id="DE123456789",
        )

    @pytest.fixture
    def sample_buyer(self, sample_address: Address) -> InvoiceParty:
        """Sample buyer fixture."""
        return InvoiceParty(
            name="Kunde AG",
            address=sample_address,
        )

    @pytest.fixture
    def sample_line_item(self) -> InvoiceLineItem:
        """Sample line item fixture."""
        return InvoiceLineItem(
            line_id="1",
            description="Beratung",
            quantity=Decimal("1"),
            unit_price=Decimal("100"),
            line_net_amount=Decimal("100"),
        )

    def test_invoice_data_creation(
        self,
        sample_seller: InvoiceParty,
        sample_buyer: InvoiceParty,
        sample_line_item: InvoiceLineItem,
    ) -> None:
        """Test InvoiceData creation."""
        invoice = InvoiceData(
            invoice_number="RE-2024-001",
            issue_date=date(2024, 1, 15),
            seller=sample_seller,
            buyer=sample_buyer,
            line_items=[sample_line_item],
            total_net_amount=Decimal("100.00"),
            total_tax_amount=Decimal("19.00"),
            total_gross_amount=Decimal("119.00"),
            payable_amount=Decimal("119.00"),
        )
        assert invoice.invoice_number == "RE-2024-001"
        assert invoice.seller.name == "Muster GmbH"
        assert len(invoice.line_items) == 1

    def test_invoice_data_unique_line_ids(
        self,
        sample_seller: InvoiceParty,
        sample_buyer: InvoiceParty,
    ) -> None:
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


# ==================== Validator Tests ====================

class TestValidationResult:
    """Tests for ValidationResult dataclass."""

    def test_validation_result_creation(self) -> None:
        """Test ValidationResult creation."""
        result = ValidationResult(
            valid=True,
            validated_at=datetime.now(timezone.utc),
            validator_used="test",
        )
        assert result.valid is True
        assert result.error_count == 0

    def test_validation_result_add_error(self) -> None:
        """Test adding error to ValidationResult."""
        result = ValidationResult(
            valid=True,
            validated_at=datetime.now(timezone.utc),
            validator_used="test",
        )
        result.add_error(
            code="ERR-001",
            location="/Invoice/ID",
            message="ID ist erforderlich",
        )
        assert result.valid is False
        assert result.error_count == 1
        assert len(result.messages) == 1
        assert result.messages[0].severity == ValidationSeverity.ERROR

    def test_validation_result_add_warning(self) -> None:
        """Test adding warning to ValidationResult."""
        result = ValidationResult(
            valid=True,
            validated_at=datetime.now(timezone.utc),
            validator_used="test",
        )
        result.add_warning(
            code="WARN-001",
            location="/Invoice/Note",
            message="Note ist empfohlen",
        )
        assert result.valid is True  # Warnings don't invalidate
        assert result.warning_count == 1


class TestValidationMessage:
    """Tests for ValidationMessage dataclass."""

    def test_validation_message_creation(self) -> None:
        """Test ValidationMessage creation."""
        msg = ValidationMessage(
            code="BR-DE-01",
            severity=ValidationSeverity.ERROR,
            location="/Invoice/AccountingSupplierParty",
            message="Leitweg-ID fehlt",
            rule_id="BR-DE-01",
        )
        assert msg.code == "BR-DE-01"
        assert msg.severity == ValidationSeverity.ERROR


class TestValidatorService:
    """Tests for EInvoiceValidatorService."""

    @pytest.fixture
    def validator_service(self) -> EInvoiceValidatorService:
        """Get validator service instance."""
        return get_validator_service()

    def test_validator_service_creation(
        self, validator_service: EInvoiceValidatorService
    ) -> None:
        """Test validator service can be created."""
        assert validator_service is not None

    def test_get_validator_service_returns_instance(self) -> None:
        """Test get_validator_service returns an instance."""
        service = get_validator_service()
        assert isinstance(service, EInvoiceValidatorService)

    def test_validator_type_enum(self) -> None:
        """Test ValidatorType enum values."""
        assert ValidatorType.AUTO == "auto"
        assert ValidatorType.FACTURX == "facturx"
        assert ValidatorType.KOSIT == "kosit"
