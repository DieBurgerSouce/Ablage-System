"""
Document Template Models

Dokumenten-Vorlagen für wiederkehrende Dokumente mit:
- Variablen-Platzhaltern (Kunde, Datum, Betrag, etc.)
- Ein-Klick Dokumentenerstellung
- Vorlagen-Bibliothek nach Kategorien
- Versionierung von Vorlagen
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.models import Base

if TYPE_CHECKING:
    from app.db.models import Company, User


class TemplateCategory(str, enum.Enum):
    """Kategorien für Dokumentvorlagen."""
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


class TemplateOutputFormat(str, enum.Enum):
    """Ausgabeformate für generierte Dokumente."""
    PDF = "pdf"
    DOCX = "docx"
    HTML = "html"
    MARKDOWN = "markdown"


class VariableType(str, enum.Enum):
    """Typen für Template-Variablen."""
    TEXT = "text"
    NUMBER = "number"
    CURRENCY = "currency"
    DATE = "date"
    DATETIME = "datetime"
    BOOLEAN = "boolean"
    SELECT = "select"
    ENTITY = "entity"  # Referenz auf BusinessEntity
    DOCUMENT = "document"  # Referenz auf anderes Dokument


class DocumentTemplate(Base):
    """
    Dokumentvorlage mit Platzhaltern und Metadaten.

    Unterstützt:
    - Jinja2-Syntax für Platzhalter: {{ variable_name }}
    - Bedingte Bloecke: {% if condition %}...{% endif %}
    - Schleifen: {% for item in items %}...{% endfor %}
    """
    __tablename__ = "document_templates"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("companies.id"),
        nullable=False,
        index=True,
    )

    # Identifikation
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    code: Mapped[str] = mapped_column(String(50), nullable=False)  # Kurzcode wie "INV-STANDARD"
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    category: Mapped[TemplateCategory] = mapped_column(
        Enum(TemplateCategory, name="templatecategory"),
        default=TemplateCategory.OTHER,
    )

    # Vorlage
    content: Mapped[str] = mapped_column(Text, nullable=False)  # Jinja2 Template
    header_content: Mapped[str | None] = mapped_column(Text, nullable=True)  # Optional header
    footer_content: Mapped[str | None] = mapped_column(Text, nullable=True)  # Optional footer

    # Styling
    css_styles: Mapped[str | None] = mapped_column(Text, nullable=True)
    page_size: Mapped[str] = mapped_column(String(20), default="A4")  # A4, Letter, etc.
    orientation: Mapped[str] = mapped_column(String(20), default="portrait")  # portrait, landscape
    margins: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        default=lambda: {"top": 20, "right": 15, "bottom": 20, "left": 15},  # mm
    )

    # Ausgabeformat
    output_format: Mapped[TemplateOutputFormat] = mapped_column(
        Enum(TemplateOutputFormat, name="templateoutputformat"),
        default=TemplateOutputFormat.PDF,
    )

    # Variablen-Definition (Schema)
    variables: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB,
        default=list,
        comment="Schema der Template-Variablen",
    )
    # Format: [{"name": "kunde", "type": "entity", "label": "Kunde", "required": true, "default": null, "options": [...]}]

    # Versionierung
    version: Mapped[int] = mapped_column(Integer, default=1)
    is_latest: Mapped[bool] = mapped_column(Boolean, default=True)
    parent_template_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("document_templates.id"),
        nullable=True,
    )

    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)  # Default für Kategorie

    # Nutzungsstatistik
    usage_count: Mapped[int] = mapped_column(Integer, default=0)
    last_used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Metadaten
    tags: Mapped[list[str]] = mapped_column(JSONB, default=list)
    template_metadata: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)  # Renamed: 'metadata' is reserved in SQLAlchemy

    # Audit
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=True,
    )

    # Relationships
    company: Mapped["Company"] = relationship("Company", back_populates="document_templates")
    created_by: Mapped["User | None"] = relationship("User", foreign_keys=[created_by_id])
    parent_template: Mapped["DocumentTemplate | None"] = relationship(
        "DocumentTemplate",
        remote_side=[id],
        back_populates="child_versions",
    )
    child_versions: Mapped[list["DocumentTemplate"]] = relationship(
        "DocumentTemplate",
        back_populates="parent_template",
    )
    generated_documents: Mapped[list["GeneratedDocument"]] = relationship(
        "GeneratedDocument",
        back_populates="template",
    )

    @hybrid_property
    def variable_names(self) -> list[str]:
        """Liste der Variablen-Namen aus dem Schema."""
        return [v.get("name") for v in self.variables if v.get("name")]

    @hybrid_property
    def required_variables(self) -> list[dict[str, Any]]:
        """Nur erforderliche Variablen."""
        return [v for v in self.variables if v.get("required", False)]

    def __repr__(self) -> str:
        return f"<DocumentTemplate {self.code} v{self.version}>"


class GeneratedDocument(Base):
    """
    Generiertes Dokument aus einer Vorlage.

    Speichert:
    - Die verwendeten Variablen-Werte
    - Referenz zur Vorlage
    - Generiertes Dokument (als Datei oder in Storage)
    """
    __tablename__ = "generated_documents"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("companies.id"),
        nullable=False,
        index=True,
    )
    template_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("document_templates.id"),
        nullable=False,
        index=True,
    )

    # Generierte Datei
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_path: Mapped[str | None] = mapped_column(String(500), nullable=True)  # MinIO path
    file_size: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Verwendete Werte
    variable_values: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        default=dict,
        comment="Verwendete Variablen-Werte bei Generierung",
    )
    # Format: {"kunde": {"id": "...", "name": "..."}, "datum": "2026-01-17", "betrag": 1500.00}

    # Template-Version zum Zeitpunkt der Generierung
    template_version: Mapped[int] = mapped_column(Integer, nullable=False)
    template_snapshot: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="Snapshot des Templates bei Generierung (optional)",
    )

    # Referenzen
    linked_entity_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("business_entities.id"),
        nullable=True,
        index=True,
    )
    linked_document_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id"),
        nullable=True,
        index=True,
    )

    # Status
    is_finalized: Mapped[bool] = mapped_column(Boolean, default=False)  # Unveränderbar
    is_sent: Mapped[bool] = mapped_column(Boolean, default=False)  # Per Email versendet
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sent_to: Mapped[list[str]] = mapped_column(JSONB, default=list)  # Email-Adressen

    # Metadaten
    gen_metadata: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)  # Renamed: 'metadata' is reserved in SQLAlchemy

    # Audit
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=True,
    )

    # Relationships
    company: Mapped["Company"] = relationship("Company")
    template: Mapped["DocumentTemplate"] = relationship(
        "DocumentTemplate",
        back_populates="generated_documents",
    )
    created_by: Mapped["User | None"] = relationship("User", foreign_keys=[created_by_id])

    def __repr__(self) -> str:
        return f"<GeneratedDocument {self.title}>"


class TemplateSnippet(Base):
    """
    Wiederverwendbare Textbausteine für Templates.

    z.B. Standard-Fusszeilen, AGBs, Grussformeln.
    """
    __tablename__ = "template_snippets"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("companies.id"),
        nullable=False,
        index=True,
    )

    # Identifikation
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    code: Mapped[str] = mapped_column(String(50), nullable=False)  # z.B. "AGB-FOOTER"
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    category: Mapped[str] = mapped_column(String(100), default="general")

    # Inhalt
    content: Mapped[str] = mapped_column(Text, nullable=False)

    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Audit
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    def __repr__(self) -> str:
        return f"<TemplateSnippet {self.code}>"
