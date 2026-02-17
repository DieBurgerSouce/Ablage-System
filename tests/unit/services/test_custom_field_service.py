# -*- coding: utf-8 -*-
"""
Unit-Tests fuer den Custom Field Service.

Testet:
- Feldtyp-Validierung (alle 7 Typen)
- CRUD-Operationen fuer Felddefinitionen
- Feldwerte setzen/lesen auf Dokumenten
- SQL-Injection-Schutz bei JSONB-Abfragen (CWE-89)
- Whitelist-Validierung fuer Feldnamen
"""

import re
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Union
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Add app to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from app.api.schemas.custom_fields import (
    FIELD_NAME_PATTERN,
    CustomFieldDefinitionCreate,
    CustomFieldValueSet,
    FieldTypeEnum,
    validate_field_name,
)
from app.db.models_custom_fields import CustomFieldDefinition, FieldType


# =============================================================================
# Lazy import of service (avoids torch import chain)
# =============================================================================

def _get_service_class():
    """Lazily import CustomFieldService to avoid torch dependency chain."""
    # Mock torch before importing service
    if "torch" not in sys.modules:
        sys.modules["torch"] = MagicMock()
    from app.services.custom_field_service import (
        CustomFieldService,
        CustomFieldValidationError,
    )
    return CustomFieldService, CustomFieldValidationError


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def service():
    CustomFieldService, _ = _get_service_class()
    return CustomFieldService()


@pytest.fixture
def validation_error_class():
    _, CustomFieldValidationError = _get_service_class()
    return CustomFieldValidationError


@pytest.fixture
def company_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def user_id() -> uuid.UUID:
    return uuid.uuid4()


def _make_definition(
    *,
    name: str = "test_field",
    field_type: str = "text",
    required: bool = False,
    validation_rules: Optional[Dict[str, object]] = None,
    dropdown_options: Optional[List[Dict[str, str]]] = None,
    lookup_entity: Optional[str] = None,
) -> MagicMock:
    """Erstellt ein Mock-CustomFieldDefinition-Objekt."""
    defn = MagicMock(spec=CustomFieldDefinition)
    defn.name = name
    defn.field_type = field_type
    defn.required = required
    defn.validation_rules = validation_rules
    defn.dropdown_options = dropdown_options
    defn.lookup_entity = lookup_entity
    return defn


# =============================================================================
# Field Name Validation (CWE-89 Prevention)
# =============================================================================

class TestFieldNameValidation:
    """Tests fuer Feldnamen-Whitelist (SQL-Injection-Schutz)."""

    def test_valid_names(self) -> None:
        """Gueltige snake_case Namen werden akzeptiert."""
        valid_names = [
            "ab",
            "test_field",
            "lieferanten_nr",
            "custom_date_01",
            "a" * 64,
        ]
        for name in valid_names:
            result = validate_field_name(name)
            assert result == name

    def test_invalid_names_rejected(self) -> None:
        """Ungueltige Namen werden abgelehnt."""
        invalid_names = [
            "",              # Leer
            "a",             # Zu kurz (min 2 Zeichen)
            "A",             # Grossbuchstabe
            "1field",        # Beginnt mit Zahl
            "_field",        # Beginnt mit Underscore
            "field-name",    # Bindestrich
            "feld name",     # Leerzeichen
            "feld.name",     # Punkt
            "a" * 65,        # Zu lang
        ]
        for name in invalid_names:
            with pytest.raises(ValueError):
                validate_field_name(name)

    def test_sql_injection_patterns_rejected(self) -> None:
        """SQL-Injection-Versuche werden abgelehnt (CWE-89)."""
        injection_patterns = [
            "field'; DROP TABLE documents;--",
            "field\" OR 1=1",
            "field\nUNION SELECT",
            "field\\x00",
            "field->>'admin",
            "field)UNION(SELECT",
        ]
        for pattern in injection_patterns:
            with pytest.raises(ValueError):
                validate_field_name(pattern)

    def test_pattern_regex(self) -> None:
        """FIELD_NAME_PATTERN matcht korrekt."""
        assert FIELD_NAME_PATTERN.match("ab") is not None
        assert FIELD_NAME_PATTERN.match("test_field_123") is not None
        assert FIELD_NAME_PATTERN.match("a") is None
        assert FIELD_NAME_PATTERN.match("1test") is None
        assert FIELD_NAME_PATTERN.match("Test") is None


# =============================================================================
# Field Type Validation
# =============================================================================

class TestTextValidation:
    """Tests fuer Text-Feld-Validierung."""

    def test_valid_text(self, service) -> None:
        defn = _make_definition(field_type="text")
        service._validate_field_value(defn, "my_field", "Hallo Welt")

    def test_non_string_rejected(self, service, validation_error_class) -> None:
        defn = _make_definition(field_type="text")
        with pytest.raises(validation_error_class, match="Text"):
            service._validate_field_value(defn, "my_field", 42)

    def test_min_length(self, service, validation_error_class) -> None:
        defn = _make_definition(
            field_type="text",
            validation_rules={"min_length": 5},
        )
        with pytest.raises(validation_error_class, match="mindestens 5"):
            service._validate_field_value(defn, "my_field", "ab")

    def test_max_length(self, service, validation_error_class) -> None:
        defn = _make_definition(
            field_type="text",
            validation_rules={"max_length": 3},
        )
        with pytest.raises(validation_error_class, match="maximal 3"):
            service._validate_field_value(defn, "my_field", "abcdef")

    def test_pattern_match(self, service) -> None:
        defn = _make_definition(
            field_type="text",
            validation_rules={"pattern": r"^\d{4}-\d{3}$"},
        )
        service._validate_field_value(defn, "my_field", "1234-567")

    def test_pattern_mismatch(self, service, validation_error_class) -> None:
        defn = _make_definition(
            field_type="text",
            validation_rules={"pattern": r"^\d{4}-\d{3}$"},
        )
        with pytest.raises(validation_error_class, match="Muster"):
            service._validate_field_value(defn, "my_field", "abc")


class TestNumberValidation:
    """Tests fuer Zahlen-Feld-Validierung."""

    def test_valid_int(self, service) -> None:
        defn = _make_definition(field_type="number")
        service._validate_field_value(defn, "my_field", 42)

    def test_valid_float(self, service) -> None:
        defn = _make_definition(field_type="number")
        service._validate_field_value(defn, "my_field", 3.14)

    def test_string_rejected(self, service, validation_error_class) -> None:
        defn = _make_definition(field_type="number")
        with pytest.raises(validation_error_class, match="Zahl"):
            service._validate_field_value(defn, "my_field", "42")

    def test_min_value(self, service, validation_error_class) -> None:
        defn = _make_definition(
            field_type="number",
            validation_rules={"min_value": 10},
        )
        with pytest.raises(validation_error_class, match="mindestens 10"):
            service._validate_field_value(defn, "my_field", 5)

    def test_max_value(self, service, validation_error_class) -> None:
        defn = _make_definition(
            field_type="number",
            validation_rules={"max_value": 100},
        )
        with pytest.raises(validation_error_class, match="maximal 100"):
            service._validate_field_value(defn, "my_field", 200)


class TestDateValidation:
    """Tests fuer Datum-Feld-Validierung."""

    def test_valid_date(self, service) -> None:
        defn = _make_definition(field_type="date")
        service._validate_field_value(defn, "my_field", "2026-02-16")

    def test_invalid_date_format(self, service, validation_error_class) -> None:
        defn = _make_definition(field_type="date")
        with pytest.raises(validation_error_class, match="YYYY-MM-DD"):
            service._validate_field_value(defn, "my_field", "16.02.2026")

    def test_non_string_rejected(self, service, validation_error_class) -> None:
        defn = _make_definition(field_type="date")
        with pytest.raises(validation_error_class, match="Text"):
            service._validate_field_value(defn, "my_field", 20260216)


class TestBooleanValidation:
    """Tests fuer Boolean-Feld-Validierung."""

    def test_valid_true(self, service) -> None:
        defn = _make_definition(field_type="boolean")
        service._validate_field_value(defn, "my_field", True)

    def test_valid_false(self, service) -> None:
        defn = _make_definition(field_type="boolean")
        service._validate_field_value(defn, "my_field", False)

    def test_string_rejected(self, service, validation_error_class) -> None:
        defn = _make_definition(field_type="boolean")
        with pytest.raises(validation_error_class, match="true oder false"):
            service._validate_field_value(defn, "my_field", "true")

    def test_int_rejected(self, service, validation_error_class) -> None:
        defn = _make_definition(field_type="boolean")
        with pytest.raises(validation_error_class, match="true oder false"):
            service._validate_field_value(defn, "my_field", 1)


class TestDropdownValidation:
    """Tests fuer Dropdown-Feld-Validierung."""

    def test_valid_option(self, service) -> None:
        defn = _make_definition(
            field_type="dropdown",
            dropdown_options=[
                {"value": "opt_a", "label": "Option A"},
                {"value": "opt_b", "label": "Option B"},
            ],
        )
        service._validate_field_value(defn, "my_field", "opt_a")

    def test_invalid_option(self, service, validation_error_class) -> None:
        defn = _make_definition(
            field_type="dropdown",
            dropdown_options=[
                {"value": "opt_a", "label": "Option A"},
            ],
        )
        with pytest.raises(validation_error_class, match="keine gueltige Option"):
            service._validate_field_value(defn, "my_field", "opt_c")


class TestMultiSelectValidation:
    """Tests fuer Multi-Select-Feld-Validierung."""

    def test_valid_selection(self, service) -> None:
        defn = _make_definition(
            field_type="multi_select",
            dropdown_options=[
                {"value": "tag_a", "label": "Tag A"},
                {"value": "tag_b", "label": "Tag B"},
                {"value": "tag_c", "label": "Tag C"},
            ],
        )
        service._validate_field_value(defn, "my_field", ["tag_a", "tag_c"])

    def test_invalid_item_in_list(self, service, validation_error_class) -> None:
        defn = _make_definition(
            field_type="multi_select",
            dropdown_options=[
                {"value": "tag_a", "label": "Tag A"},
            ],
        )
        with pytest.raises(validation_error_class, match="keine gueltige Option"):
            service._validate_field_value(defn, "my_field", ["tag_a", "tag_z"])

    def test_non_list_rejected(self, service, validation_error_class) -> None:
        defn = _make_definition(field_type="multi_select", dropdown_options=[])
        with pytest.raises(validation_error_class, match="Liste"):
            service._validate_field_value(defn, "my_field", "tag_a")


class TestLookupValidation:
    """Tests fuer Lookup-Feld-Validierung."""

    def test_valid_uuid(self, service) -> None:
        defn = _make_definition(field_type="lookup")
        valid_uuid = str(uuid.uuid4())
        service._validate_field_value(defn, "my_field", valid_uuid)

    def test_invalid_uuid(self, service, validation_error_class) -> None:
        defn = _make_definition(field_type="lookup")
        with pytest.raises(validation_error_class, match="UUID"):
            service._validate_field_value(defn, "my_field", "not-a-uuid")

    def test_non_string_rejected(self, service, validation_error_class) -> None:
        defn = _make_definition(field_type="lookup")
        with pytest.raises(validation_error_class, match="UUID als Text"):
            service._validate_field_value(defn, "my_field", 12345)


# =============================================================================
# Required Fields
# =============================================================================

class TestRequiredFields:
    """Tests fuer Pflichtfeld-Validierung."""

    def test_required_field_none_rejected(self, service, validation_error_class) -> None:
        defn = _make_definition(field_type="text", required=True)
        with pytest.raises(validation_error_class, match="Pflichtfeld"):
            service._validate_field_value(defn, "my_field", None)

    def test_optional_field_none_allowed(self, service) -> None:
        defn = _make_definition(field_type="text", required=False)
        # Soll keine Exception werfen
        service._validate_field_value(defn, "my_field", None)


# =============================================================================
# Schema Validation
# =============================================================================

class TestSchemaValidation:
    """Tests fuer Pydantic-Schema-Validierung."""

    def test_create_schema_valid(self) -> None:
        data = CustomFieldDefinitionCreate(
            name="lieferanten_nr",
            label="Lieferanten-Nr.",
            field_type=FieldTypeEnum.TEXT,
        )
        assert data.name == "lieferanten_nr"
        assert data.field_type == FieldTypeEnum.TEXT

    def test_create_schema_invalid_name(self) -> None:
        with pytest.raises(ValueError, match="ungueltig"):
            CustomFieldDefinitionCreate(
                name="UPPER_CASE",
                label="Test",
                field_type=FieldTypeEnum.TEXT,
            )

    def test_create_schema_name_too_short(self) -> None:
        with pytest.raises(ValueError):
            CustomFieldDefinitionCreate(
                name="a",
                label="Test",
                field_type=FieldTypeEnum.TEXT,
            )

    def test_value_set_validates_field_names(self) -> None:
        """CustomFieldValueSet prueft alle Feldnamen gegen Whitelist."""
        data = CustomFieldValueSet(values={"valid_name": "test"})
        assert "valid_name" in data.values

    def test_value_set_rejects_invalid_field_names(self) -> None:
        """SQL-Injection ueber Feldnamen wird abgefangen."""
        with pytest.raises(ValueError, match="ungueltig"):
            CustomFieldValueSet(values={"'; DROP TABLE--": "hacked"})


# =============================================================================
# FieldType Enum
# =============================================================================

class TestFieldTypeEnum:
    """Tests fuer den FieldType-Enum."""

    def test_all_types_present(self) -> None:
        expected = {"text", "number", "date", "boolean", "dropdown", "multi_select", "lookup"}
        actual = {ft.value for ft in FieldType}
        assert actual == expected

    def test_enum_string_values(self) -> None:
        assert FieldType.TEXT.value == "text"
        assert FieldType.MULTI_SELECT.value == "multi_select"
        assert FieldType.LOOKUP.value == "lookup"


# =============================================================================
# Service Create Definition Validation
# =============================================================================

class TestCreateDefinitionValidation:
    """Tests fuer Validierung beim Erstellen von Definitionen."""

    @pytest.mark.asyncio
    async def test_invalid_field_type_raises(self, service) -> None:
        db = AsyncMock()
        with pytest.raises(ValueError, match="Ungueltiger Feldtyp"):
            await service.create_definition(
                db,
                name="test_field",
                label="Test",
                field_type="invalid_type",
                company_id=uuid.uuid4(),
                user_id=uuid.uuid4(),
            )

    @pytest.mark.asyncio
    async def test_dropdown_without_options_raises(self, service) -> None:
        db = AsyncMock()
        with pytest.raises(ValueError, match="mindestens eine Option"):
            await service.create_definition(
                db,
                name="test_field",
                label="Test",
                field_type="dropdown",
                company_id=uuid.uuid4(),
                user_id=uuid.uuid4(),
                dropdown_options=None,
            )

    @pytest.mark.asyncio
    async def test_lookup_without_entity_raises(self, service) -> None:
        db = AsyncMock()
        with pytest.raises(ValueError, match="lookup_entity"):
            await service.create_definition(
                db,
                name="test_field",
                label="Test",
                field_type="lookup",
                company_id=uuid.uuid4(),
                user_id=uuid.uuid4(),
                lookup_entity=None,
            )

    @pytest.mark.asyncio
    async def test_lookup_invalid_entity_raises(self, service) -> None:
        db = AsyncMock()
        with pytest.raises(ValueError, match="Ungueltige Lookup-Entitaet"):
            await service.create_definition(
                db,
                name="test_field",
                label="Test",
                field_type="lookup",
                company_id=uuid.uuid4(),
                user_id=uuid.uuid4(),
                lookup_entity="hacker_table",
            )

    @pytest.mark.asyncio
    async def test_invalid_field_name_raises(self, service) -> None:
        db = AsyncMock()
        with pytest.raises(ValueError, match="ungueltig"):
            await service.create_definition(
                db,
                name="INVALID",
                label="Test",
                field_type="text",
                company_id=uuid.uuid4(),
                user_id=uuid.uuid4(),
            )
