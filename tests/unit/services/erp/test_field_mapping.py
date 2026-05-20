"""Tests for ERP Field Mapping Service.

Testet Feld-Transformatoren und Entity-Mappings.
"""

import pytest
from datetime import datetime, date
from decimal import Decimal

from app.services.erp.field_mapping import (
    PassthroughTransformer,
    DateTransformer,
    CurrencyTransformer,
    BooleanTransformer,
    LookupTransformer,
    StringNormalizer,
    AddressTransformer,
    get_transformer,
    FieldMappingConfig,
    EntityMappingService,
    get_mapping_service,
)


# =============================================================================
# Transformer Tests
# =============================================================================


class TestPassthroughTransformer:
    """Tests for PassthroughTransformer."""

    def test_to_erp_returns_same_value(self):
        """Test that value passes through unchanged."""
        transformer = PassthroughTransformer()

        assert transformer.to_erp("test") == "test"
        assert transformer.to_erp(123) == 123
        assert transformer.to_erp(None) is None

    def test_from_erp_returns_same_value(self):
        """Test that value passes through unchanged."""
        transformer = PassthroughTransformer()

        assert transformer.from_erp("test") == "test"
        assert transformer.from_erp(123) == 123


class TestDateTransformer:
    """Tests for DateTransformer."""

    def test_to_erp_datetime(self):
        """Test datetime to ERP format."""
        transformer = DateTransformer()
        dt = datetime(2024, 1, 15, 10, 30, 45)

        result = transformer.to_erp(dt)

        assert result == "2024-01-15 10:30:45"

    def test_to_erp_date(self):
        """Test date to ERP format."""
        transformer = DateTransformer()
        d = date(2024, 1, 15)

        result = transformer.to_erp(d)

        assert result == "2024-01-15"

    def test_to_erp_none(self):
        """Test None handling."""
        transformer = DateTransformer()

        assert transformer.to_erp(None) is None

    def test_from_erp_string_datetime(self):
        """Test parsing datetime string from ERP."""
        transformer = DateTransformer()

        result = transformer.from_erp("2024-01-15 10:30:45")

        assert isinstance(result, datetime)
        assert result.year == 2024
        assert result.month == 1
        assert result.day == 15
        assert result.hour == 10

    def test_from_erp_string_date(self):
        """Test parsing date string from ERP."""
        transformer = DateTransformer()

        result = transformer.from_erp("2024-01-15")

        assert isinstance(result, datetime)
        assert result.year == 2024
        assert result.month == 1
        assert result.day == 15

    def test_from_erp_none(self):
        """Test None handling."""
        transformer = DateTransformer()

        assert transformer.from_erp(None) is None
        assert transformer.from_erp(False) is None  # Odoo style


class TestCurrencyTransformer:
    """Tests for CurrencyTransformer."""

    def test_to_erp_decimal(self):
        """Test Decimal to float."""
        transformer = CurrencyTransformer()

        result = transformer.to_erp(Decimal("123.45"))

        assert result == 123.45
        assert isinstance(result, float)

    def test_to_erp_int(self):
        """Test int to float."""
        transformer = CurrencyTransformer()

        result = transformer.to_erp(100)

        assert result == 100.0
        assert isinstance(result, float)

    def test_to_erp_string(self):
        """Test string with comma to float."""
        transformer = CurrencyTransformer()

        result = transformer.to_erp("123,45")

        assert result == 123.45

    def test_from_erp_float(self):
        """Test float to Decimal."""
        transformer = CurrencyTransformer()

        result = transformer.from_erp(123.45)

        assert isinstance(result, Decimal)
        assert result == Decimal("123.45")

    def test_from_erp_none(self):
        """Test None handling."""
        transformer = CurrencyTransformer()

        assert transformer.from_erp(None) is None
        assert transformer.from_erp(False) is None


class TestBooleanTransformer:
    """Tests for BooleanTransformer."""

    def test_to_erp_true(self):
        """Test True value."""
        transformer = BooleanTransformer()

        assert transformer.to_erp(True) is True
        assert transformer.to_erp(1) is True
        assert transformer.to_erp("yes") is True

    def test_to_erp_false(self):
        """Test False value."""
        transformer = BooleanTransformer()

        assert transformer.to_erp(False) is False
        assert transformer.to_erp(None) is False
        assert transformer.to_erp(0) is False

    def test_from_erp_odoo_false(self):
        """Test Odoo False (None equivalent)."""
        transformer = BooleanTransformer()

        assert transformer.from_erp(False) is False
        assert transformer.from_erp(None) is False


class TestLookupTransformer:
    """Tests for LookupTransformer."""

    def test_to_erp_with_lookup(self):
        """Test lookup table conversion."""
        transformer = LookupTransformer()
        config = {"lookup_table": {"local-1": 123}}

        result = transformer.to_erp("local-1", config)

        assert result == 123

    def test_to_erp_int_passthrough(self):
        """Test int passes through as-is."""
        transformer = LookupTransformer()

        result = transformer.to_erp(456)

        assert result == 456

    def test_from_erp_many2one(self):
        """Test Odoo many2one [id, name] format."""
        transformer = LookupTransformer()

        result = transformer.from_erp([123, "Germany"])

        assert result == "123"

    def test_from_erp_with_reverse_lookup(self):
        """Test reverse lookup."""
        transformer = LookupTransformer()
        config = {"reverse_lookup": {123: "DE"}}

        result = transformer.from_erp(123, config)

        assert result == "DE"


class TestStringNormalizer:
    """Tests for StringNormalizer."""

    def test_to_erp_trim(self):
        """Test string trimming."""
        transformer = StringNormalizer()

        result = transformer.to_erp("  test  ")

        assert result == "test"

    def test_to_erp_none(self):
        """Test None to empty string."""
        transformer = StringNormalizer()

        assert transformer.to_erp(None) == ""
        assert transformer.to_erp(False) == ""  # Odoo style

    def test_to_erp_max_length(self):
        """Test max length truncation."""
        transformer = StringNormalizer()
        config = {"max_length": 5}

        result = transformer.to_erp("hello world", config)

        assert result == "hello"
        assert len(result) == 5

    def test_from_erp_empty_to_none(self):
        """Test empty string to None."""
        transformer = StringNormalizer()

        assert transformer.from_erp("") is None
        assert transformer.from_erp("  ") is None


class TestAddressTransformer:
    """Tests for AddressTransformer."""

    def test_to_erp(self):
        """Test address dict to flat fields."""
        transformer = AddressTransformer()
        address = {
            "street": "Main Street 1",
            "street2": "Apt 5",
            "city": "Berlin",
            "zip": "12345",
        }

        result = transformer.to_erp(address)

        assert result["street"] == "Main Street 1"
        assert result["street2"] == "Apt 5"
        assert result["city"] == "Berlin"
        assert result["zip"] == "12345"

    def test_from_erp(self):
        """Test flat fields to address dict."""
        transformer = AddressTransformer()
        flat = {
            "street": "Main Street 1",
            "city": "Berlin",
            "zip": "12345",
        }

        result = transformer.from_erp(flat)

        assert result["street"] == "Main Street 1"
        assert result["city"] == "Berlin"
        assert result["zip"] == "12345"


# =============================================================================
# Transformer Registry Tests
# =============================================================================


class TestTransformerRegistry:
    """Tests for transformer registry."""

    def test_get_passthrough(self):
        """Test getting passthrough transformer."""
        transformer = get_transformer("passthrough")
        assert isinstance(transformer, PassthroughTransformer)

    def test_get_date(self):
        """Test getting date transformer."""
        transformer = get_transformer("date")
        assert isinstance(transformer, DateTransformer)

    def test_get_unknown_returns_passthrough(self):
        """Test unknown name returns passthrough."""
        transformer = get_transformer("unknown")
        assert isinstance(transformer, PassthroughTransformer)


# =============================================================================
# FieldMappingConfig Tests
# =============================================================================


class TestFieldMappingConfig:
    """Tests for FieldMappingConfig."""

    def test_creation(self):
        """Test config creation."""
        config = FieldMappingConfig(
            local_field="name",
            remote_field="display_name",
            transformer="string",
            required=True,
        )

        assert config.local_field == "name"
        assert config.remote_field == "display_name"
        assert config.required is True

    def test_to_erp(self):
        """Test to_erp transformation."""
        config = FieldMappingConfig(
            local_field="amount",
            remote_field="total",
            transformer="currency",
        )

        result = config.to_erp(Decimal("123.45"))

        assert result == 123.45

    def test_from_erp(self):
        """Test from_erp transformation."""
        config = FieldMappingConfig(
            local_field="amount",
            remote_field="total",
            transformer="currency",
        )

        result = config.from_erp(123.45)

        assert isinstance(result, Decimal)

    def test_default_value(self):
        """Test default value application."""
        config = FieldMappingConfig(
            local_field="status",
            remote_field="state",
            transformer="string",
            default_value="draft",
        )

        result = config.to_erp(None)
        assert result == "draft"


# =============================================================================
# EntityMappingService Tests
# =============================================================================


class TestEntityMappingService:
    """Tests for EntityMappingService."""

    def test_default_mappings_loaded(self):
        """Test that default mappings are loaded."""
        service = EntityMappingService()

        customer_mappings = service.get_mappings("customer")

        assert len(customer_mappings) > 0
        field_names = [m.local_field for m in customer_mappings]
        assert "name" in field_names
        assert "email" in field_names

    def test_to_erp_customer(self):
        """Test customer transformation to ERP."""
        service = EntityMappingService()
        local_data = {
            "name": "Test Customer",
            "email": "test@example.com",
            "phone": "+49123456789",
            "address": {
                "street": "Main Street 1",
                "city": "Berlin",
            },
        }

        result = service.to_erp("customer", local_data)

        assert result["name"] == "Test Customer"
        assert result["email"] == "test@example.com"
        assert result["phone"] == "+49123456789"
        assert result["street"] == "Main Street 1"
        assert result["city"] == "Berlin"

    def test_from_erp_customer(self):
        """Test customer transformation from ERP."""
        service = EntityMappingService()
        erp_data = {
            "name": "Test Customer",
            "email": "test@example.com",
            "phone": "+49123456789",
            "street": "Main Street 1",
            "city": "Berlin",
            "write_date": "2024-01-15 10:30:00",
        }

        result = service.from_erp("customer", erp_data)

        assert result["name"] == "Test Customer"
        assert result["email"] == "test@example.com"
        assert "address" in result
        assert result["address"]["street"] == "Main Street 1"
        assert isinstance(result.get("updated_at"), datetime)

    def test_custom_mappings(self):
        """Test applying custom mappings."""
        custom = {
            "customer": [
                {"local_field": "custom_field", "remote_field": "x_custom", "transformer": "string"},
            ],
        }
        service = EntityMappingService(custom_mappings=custom)

        mappings = service.get_mappings("customer")
        field_names = [m.local_field for m in mappings]

        assert "custom_field" in field_names

    def test_invoice_mappings(self):
        """Test invoice default mappings."""
        service = EntityMappingService()

        mappings = service.get_mappings("invoice")
        field_names = [m.local_field for m in mappings]

        assert "number" in field_names
        assert "invoice_date" in field_names
        assert "total_amount" in field_names


# =============================================================================
# Singleton Tests
# =============================================================================


class TestMappingServiceSingleton:
    """Tests for mapping service singleton."""

    def test_singleton(self):
        """Test that get_mapping_service returns same instance."""
        # Reset singleton
        import app.services.erp.field_mapping as fm
        fm._mapping_service = None

        service1 = get_mapping_service()
        service2 = get_mapping_service()

        assert service1 is service2

    def test_custom_mappings_create_new(self):
        """Test that custom mappings create new instance."""
        import app.services.erp.field_mapping as fm
        fm._mapping_service = None

        service1 = get_mapping_service()
        service2 = get_mapping_service({"customer": []})

        # New instance created
        assert service2 is not service1
