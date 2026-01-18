"""
Document Template API Schemas

Pydantic Schemas fuer Dokumenten-Vorlagen API.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, ConfigDict


# =============================================================================
# Enums
# =============================================================================

class TemplateCategoryEnum(str, Enum):
    """Kategorien fuer Dokumentvorlagen."""
    INVOICE = "invoice"
    OFFER = "offer"
    CONTRACT = "contract"
    LETTER = "letter"
    REMINDER = "reminder"
    DUNNING = "dunning"
    CONFIRMATION = "confirmation"
    REPORT = "report"
    CERTIFICATE = "certificate"
    OTHER = "other"


class TemplateOutputFormatEnum(str, Enum):
    """Ausgabeformate fuer generierte Dokumente."""
    PDF = "pdf"
    DOCX = "docx"
    HTML = "html"
    MARKDOWN = "markdown"


class VariableTypeEnum(str, Enum):
    """Typen fuer Template-Variablen."""
    TEXT = "text"
    NUMBER = "number"
    CURRENCY = "currency"
    DATE = "date"
    DATETIME = "datetime"
    BOOLEAN = "boolean"
    SELECT = "select"
    ENTITY = "entity"
    DOCUMENT = "document"


# =============================================================================
# Variable Schema
# =============================================================================

class TemplateVariableSchema(BaseModel):
    """Schema fuer eine Template-Variable."""
    name: str = Field(..., min_length=1, max_length=50, pattern=r"^[a-zA-Z_][a-zA-Z0-9_]*$")
    type: VariableTypeEnum
    label: str = Field(..., min_length=1, max_length=100)
    description: str | None = None
    required: bool = False
    default: Any = None
    options: list[str] | None = None  # Fuer SELECT-Typ
    entity_type: str | None = None  # Fuer ENTITY-Typ (z.B. "customer", "supplier")


# =============================================================================
# Template Request Schemas
# =============================================================================

class TemplateCreate(BaseModel):
    """Schema zum Erstellen einer Vorlage."""
    name: str = Field(..., min_length=1, max_length=255)
    code: str = Field(..., min_length=1, max_length=50, pattern=r"^[A-Z0-9_-]+$")
    description: str | None = None
    category: TemplateCategoryEnum = TemplateCategoryEnum.OTHER
    content: str = Field(..., min_length=1)
    header_content: str | None = None
    footer_content: str | None = None
    css_styles: str | None = None
    page_size: str = "A4"
    orientation: str = "portrait"
    margins: dict[str, int] | None = None
    output_format: TemplateOutputFormatEnum = TemplateOutputFormatEnum.PDF
    variables: list[TemplateVariableSchema] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    is_default: bool = False


class TemplateUpdate(BaseModel):
    """Schema zum Aktualisieren einer Vorlage."""
    name: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = None
    category: TemplateCategoryEnum | None = None
    content: str | None = None
    header_content: str | None = None
    footer_content: str | None = None
    css_styles: str | None = None
    page_size: str | None = None
    orientation: str | None = None
    margins: dict[str, int] | None = None
    output_format: TemplateOutputFormatEnum | None = None
    variables: list[TemplateVariableSchema] | None = None
    tags: list[str] | None = None
    is_active: bool | None = None
    is_default: bool | None = None
    create_new_version: bool = False


# =============================================================================
# Template Response Schemas
# =============================================================================

class TemplateResponse(BaseModel):
    """Response-Schema fuer eine Vorlage."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    company_id: UUID
    name: str
    code: str
    description: str | None
    category: TemplateCategoryEnum
    content: str
    header_content: str | None
    footer_content: str | None
    css_styles: str | None
    page_size: str
    orientation: str
    margins: dict[str, Any]
    output_format: TemplateOutputFormatEnum
    variables: list[dict[str, Any]]
    version: int
    is_latest: bool
    is_active: bool
    is_default: bool
    usage_count: int
    last_used_at: datetime | None
    tags: list[str]
    created_at: datetime
    updated_at: datetime
    created_by_id: UUID | None


class TemplateListResponse(BaseModel):
    """Response-Schema fuer Vorlagen-Liste."""
    items: list[TemplateResponse]
    total: int
    offset: int
    limit: int


class TemplateBriefResponse(BaseModel):
    """Kurzform fuer Vorlagen (ohne Content)."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    code: str
    description: str | None
    category: TemplateCategoryEnum
    output_format: TemplateOutputFormatEnum
    version: int
    is_default: bool
    usage_count: int
    variable_count: int = 0


# =============================================================================
# Document Generation Schemas
# =============================================================================

class GenerateDocumentRequest(BaseModel):
    """Request zum Generieren eines Dokuments."""
    template_id: UUID
    title: str = Field(..., min_length=1, max_length=500)
    variables: dict[str, Any] = Field(default_factory=dict)
    linked_entity_id: UUID | None = None
    linked_document_id: UUID | None = None
    save_to_storage: bool = True


class PreviewRequest(BaseModel):
    """Request fuer Template-Vorschau."""
    variables: dict[str, Any] = Field(default_factory=dict)


class GeneratedDocumentResponse(BaseModel):
    """Response-Schema fuer generiertes Dokument."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    company_id: UUID
    template_id: UUID
    title: str
    filename: str
    storage_path: str | None
    file_size: int | None
    variable_values: dict[str, Any]
    template_version: int
    linked_entity_id: UUID | None
    linked_document_id: UUID | None
    is_finalized: bool
    is_sent: bool
    sent_at: datetime | None
    sent_to: list[str]
    created_at: datetime
    created_by_id: UUID | None


class GeneratedDocumentListResponse(BaseModel):
    """Response-Schema fuer Liste generierter Dokumente."""
    items: list[GeneratedDocumentResponse]
    total: int
    offset: int
    limit: int


# =============================================================================
# Snippet Schemas
# =============================================================================

class SnippetCreate(BaseModel):
    """Schema zum Erstellen eines Snippets."""
    name: str = Field(..., min_length=1, max_length=255)
    code: str = Field(..., min_length=1, max_length=50, pattern=r"^[A-Z0-9_-]+$")
    description: str | None = None
    category: str = "general"
    content: str = Field(..., min_length=1)


class SnippetUpdate(BaseModel):
    """Schema zum Aktualisieren eines Snippets."""
    name: str | None = None
    description: str | None = None
    category: str | None = None
    content: str | None = None
    is_active: bool | None = None


class SnippetResponse(BaseModel):
    """Response-Schema fuer ein Snippet."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    company_id: UUID
    name: str
    code: str
    description: str | None
    category: str
    content: str
    is_active: bool
    created_at: datetime
    updated_at: datetime


# =============================================================================
# Category Summary
# =============================================================================

class CategorySummary(BaseModel):
    """Zusammenfassung pro Kategorie."""
    category: TemplateCategoryEnum
    count: int
    default_template_id: UUID | None = None
    default_template_name: str | None = None
