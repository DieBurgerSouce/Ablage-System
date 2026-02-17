# -*- coding: utf-8 -*-
"""
Pydantic-Modelle fuer Custom Fields API Endpoints.

Definiert Request/Response Schemas fuer:
- /api/v1/custom-fields/definitions (CRUD)
- /api/v1/documents/{id}/custom-fields (Werte setzen/lesen)
"""

import re
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Union
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


# =============================================================================
# ENUMS
# =============================================================================

class FieldTypeEnum(str, Enum):
    """Verfuegbare Feldtypen."""
    TEXT = "text"
    NUMBER = "number"
    DATE = "date"
    BOOLEAN = "boolean"
    DROPDOWN = "dropdown"
    MULTI_SELECT = "multi_select"
    LOOKUP = "lookup"


# =============================================================================
# FIELD NAME VALIDATION (CWE-89 Prevention)
# =============================================================================

# Whitelist-Pattern fuer Feldnamen: snake_case, 2-64 Zeichen
FIELD_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_]{1,63}$")


def validate_field_name(name: str) -> str:
    """Validiert einen Feldnamen gegen die Whitelist.

    Verhindert SQL-Injection ueber JSONB-Schluessel (CWE-89).

    Args:
        name: Zu pruefender Feldname

    Returns:
        Validierter Feldname

    Raises:
        ValueError: Bei ungueltigem Format
    """
    if not FIELD_NAME_PATTERN.match(name):
        raise ValueError(
            f"Feldname '{name}' ist ungueltig. "
            "Erlaubt: Kleinbuchstaben, Ziffern, Unterstriche. "
            "Muss mit Buchstabe beginnen, 2-64 Zeichen."
        )
    return name


# =============================================================================
# VALIDATION RULES
# =============================================================================

class ValidationRules(BaseModel):
    """Validierungsregeln fuer ein benutzerdefiniertes Feld."""
    min_value: Optional[float] = Field(None, description="Minimalwert (Zahl)")
    max_value: Optional[float] = Field(None, description="Maximalwert (Zahl)")
    min_length: Optional[int] = Field(None, ge=0, description="Minimale Textlaenge")
    max_length: Optional[int] = Field(None, ge=1, description="Maximale Textlaenge")
    pattern: Optional[str] = Field(None, description="Regex-Pattern fuer Text")

    model_config = ConfigDict(extra="forbid")


class DropdownOption(BaseModel):
    """Einzelne Option fuer Dropdown/Multi-Select Felder."""
    value: str = Field(..., min_length=1, max_length=200, description="Technischer Wert")
    label: str = Field(..., min_length=1, max_length=200, description="Anzeige-Label (deutsch)")


# =============================================================================
# CREATE / UPDATE
# =============================================================================

class CustomFieldDefinitionCreate(BaseModel):
    """Request-Schema zum Erstellen einer Felddefinition."""
    name: str = Field(
        ...,
        min_length=2,
        max_length=64,
        description="Interner Feldname (snake_case)",
        examples=["lieferanten_nr"],
    )
    label: str = Field(
        ...,
        min_length=1,
        max_length=200,
        description="Anzeige-Label (deutsch)",
        examples=["Lieferanten-Nr."],
    )
    description: Optional[str] = Field(
        None,
        max_length=500,
        description="Optionale Beschreibung",
    )
    field_type: FieldTypeEnum = Field(
        ...,
        description="Feldtyp",
    )
    document_type: Optional[str] = Field(
        None,
        max_length=50,
        description="Dokumenttyp-Filter (None = alle)",
    )
    required: bool = Field(False, description="Pflichtfeld")
    default_value: Optional[str] = Field(
        None,
        max_length=500,
        description="Standardwert",
    )
    validation_rules: Optional[ValidationRules] = Field(
        None,
        description="Validierungsregeln",
    )
    dropdown_options: Optional[List[DropdownOption]] = Field(
        None,
        description="Optionen fuer Dropdown/Multi-Select",
    )
    lookup_entity: Optional[str] = Field(
        None,
        max_length=100,
        description="Lookup-Zielentitaet",
    )
    sort_order: int = Field(0, ge=0, description="Sortierreihenfolge")
    is_searchable: bool = Field(True, description="In Suche einschliessen")
    is_filterable: bool = Field(True, description="Als Filter anbieten")

    @field_validator("name")
    @classmethod
    def check_name_format(cls, v: str) -> str:
        return validate_field_name(v)

    @field_validator("dropdown_options")
    @classmethod
    def check_dropdown_options(
        cls, v: Optional[List[DropdownOption]], info: object
    ) -> Optional[List[DropdownOption]]:
        """Dropdown/Multi-Select Felder muessen Optionen haben."""
        # info.data may not have field_type yet during partial validation
        return v

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "name": "lieferanten_nr",
                "label": "Lieferanten-Nr.",
                "field_type": "text",
                "document_type": "invoice",
                "required": False,
                "is_searchable": True,
                "is_filterable": True,
            }
        }
    )


class CustomFieldDefinitionUpdate(BaseModel):
    """Request-Schema zum Aktualisieren einer Felddefinition."""
    label: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=500)
    required: Optional[bool] = None
    default_value: Optional[str] = Field(None, max_length=500)
    validation_rules: Optional[ValidationRules] = None
    dropdown_options: Optional[List[DropdownOption]] = None
    sort_order: Optional[int] = Field(None, ge=0)
    is_searchable: Optional[bool] = None
    is_filterable: Optional[bool] = None
    is_active: Optional[bool] = None

    model_config = ConfigDict(extra="forbid")


# =============================================================================
# RESPONSE
# =============================================================================

class CustomFieldDefinitionResponse(BaseModel):
    """Response-Schema fuer eine Felddefinition."""
    id: UUID
    name: str
    label: str
    description: Optional[str] = None
    field_type: FieldTypeEnum
    document_type: Optional[str] = None
    required: bool
    default_value: Optional[str] = None
    validation_rules: Optional[Dict[str, Union[float, int, str, None]]] = None
    dropdown_options: Optional[List[Dict[str, str]]] = None
    lookup_entity: Optional[str] = None
    sort_order: int
    is_searchable: bool
    is_filterable: bool
    company_id: UUID
    created_by: Optional[UUID] = None
    is_active: bool
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class CustomFieldDefinitionListResponse(BaseModel):
    """Response-Schema fuer eine Liste von Felddefinitionen."""
    items: List[CustomFieldDefinitionResponse]
    total: int


# =============================================================================
# FIELD VALUES (auf Dokumenten)
# =============================================================================

class CustomFieldValueSet(BaseModel):
    """Request-Schema zum Setzen von benutzerdefinierten Feldwerten auf einem Dokument."""
    values: Dict[str, Union[str, int, float, bool, List[str], None]] = Field(
        ...,
        description="Feld-Werte: {feldname: wert}",
    )

    @field_validator("values")
    @classmethod
    def check_field_names(
        cls, v: Dict[str, Union[str, int, float, bool, List[str], None]]
    ) -> Dict[str, Union[str, int, float, bool, List[str], None]]:
        """Alle Feldnamen muessen dem Whitelist-Pattern entsprechen (CWE-89)."""
        for key in v:
            validate_field_name(key)
        return v


class CustomFieldValueResponse(BaseModel):
    """Response-Schema fuer benutzerdefinierte Feldwerte eines Dokuments."""
    document_id: UUID
    values: Dict[str, Union[str, int, float, bool, List[str], None]]


# =============================================================================
# EXPORT
# =============================================================================

__all__ = [
    "FieldTypeEnum",
    "ValidationRules",
    "DropdownOption",
    "CustomFieldDefinitionCreate",
    "CustomFieldDefinitionUpdate",
    "CustomFieldDefinitionResponse",
    "CustomFieldDefinitionListResponse",
    "CustomFieldValueSet",
    "CustomFieldValueResponse",
    "validate_field_name",
    "FIELD_NAME_PATTERN",
]
