"""Template und Knowledge-Base Modelle - extrahiert aus models.py (Modularisierung Phase 1.1)."""
import uuid
from datetime import datetime
from enum import Enum

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy import Enum as SQLAlchemyEnum
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import backref, relationship

from app.db.models_base import Base, CrossDBJSON, SoftDeleteMixin

# =============================================================================
# Document Template Models
# =============================================================================

class TemplateCategory(str, Enum):
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


class TemplateOutputFormat(str, Enum):
    """Ausgabeformate für generierte Dokumente."""
    PDF = "pdf"
    DOCX = "docx"
    HTML = "html"
    MARKDOWN = "markdown"


class VariableType(str, Enum):
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

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)

    # Identifikation
    name = Column(String(255), nullable=False)
    code = Column(String(50), nullable=False)  # Kurzcode wie "INV-STANDARD"
    description = Column(Text, nullable=True)
    category = Column(SQLAlchemyEnum(TemplateCategory, name="templatecategory"), default=TemplateCategory.OTHER)

    # Vorlage
    content = Column(Text, nullable=False)  # Jinja2 Template
    header_content = Column(Text, nullable=True)  # Optional header
    footer_content = Column(Text, nullable=True)  # Optional footer

    # Styling
    css_styles = Column(Text, nullable=True)
    page_size = Column(String(20), default="A4")  # A4, Letter, etc.
    orientation = Column(String(20), default="portrait")  # portrait, landscape
    margins = Column(CrossDBJSON, default=lambda: {"top": 20, "right": 15, "bottom": 20, "left": 15})  # mm

    # Ausgabeformat
    output_format = Column(SQLAlchemyEnum(TemplateOutputFormat, name="templateoutputformat"), default=TemplateOutputFormat.PDF)

    # Variablen-Definition (Schema)
    variables = Column(CrossDBJSON, default=list, comment="Schema der Template-Variablen")
    # Format: [{"name": "kunde", "type": "entity", "label": "Kunde", "required": true, "default": null, "options": [...]}]

    # Versionierung
    version = Column(Integer, default=1)
    is_latest = Column(Boolean, default=True)
    parent_template_id = Column(UUID(as_uuid=True), ForeignKey("document_templates.id"), nullable=True)

    # Status
    is_active = Column(Boolean, default=True)
    is_default = Column(Boolean, default=False)  # Default für Kategorie

    # Nutzungsstatistik
    usage_count = Column(Integer, default=0)
    last_used_at = Column(DateTime(timezone=True), nullable=True)

    # Metadaten
    tags = Column(CrossDBJSON, default=list)
    template_metadata = Column(CrossDBJSON, default=dict)  # 'metadata' is SQLAlchemy reserved

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    created_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)

    # Relationships
    company = relationship("Company", back_populates="document_templates")
    created_by = relationship("User", foreign_keys=[created_by_id])
    parent_template = relationship(
        "DocumentTemplate",
        remote_side=[id],
        backref=backref("child_versions", lazy="dynamic"),
    )
    generated_documents = relationship("GeneratedDocument", back_populates="template", lazy="dynamic")

    __table_args__ = (
        UniqueConstraint("company_id", "code", "version", name="uq_template_code_version"),
        Index("ix_template_company", "company_id"),
        Index("ix_template_category", "category"),
        Index("ix_template_code", "code"),
        Index("ix_template_is_active", "is_active"),
        Index("ix_template_is_default", "is_default"),
        {"comment": "Dokumentvorlagen mit Jinja2-Syntax (Vorlagen-System)"}
    )

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

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    template_id = Column(UUID(as_uuid=True), ForeignKey("document_templates.id"), nullable=False, index=True)

    # Generierte Datei
    title = Column(String(500), nullable=False)
    filename = Column(String(255), nullable=False)
    storage_path = Column(String(500), nullable=True)  # MinIO path
    file_size = Column(Integer, nullable=True)

    # Verwendete Werte
    variable_values = Column(CrossDBJSON, default=dict, comment="Verwendete Variablen-Werte bei Generierung")
    # Format: {"kunde": {"id": "...", "name": "..."}, "datum": "2026-01-17", "betrag": 1500.00}

    # Template-Version zum Zeitpunkt der Generierung
    template_version = Column(Integer, nullable=False)
    template_snapshot = Column(CrossDBJSON, nullable=True, comment="Snapshot des Templates bei Generierung (optional)")

    # Referenzen
    linked_entity_id = Column(UUID(as_uuid=True), ForeignKey("business_entities.id"), nullable=True, index=True)
    linked_document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id"), nullable=True, index=True)

    # Status
    is_finalized = Column(Boolean, default=False)  # Unveränderbar
    is_sent = Column(Boolean, default=False)  # Per Email versendet
    sent_at = Column(DateTime(timezone=True), nullable=True)
    sent_to = Column(CrossDBJSON, default=list)  # Email-Adressen

    # Metadaten
    gen_doc_metadata = Column(CrossDBJSON, default=dict)  # 'metadata' is SQLAlchemy reserved

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    created_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)

    # Relationships
    company = relationship("Company")
    template = relationship("DocumentTemplate", back_populates="generated_documents")
    created_by = relationship("User", foreign_keys=[created_by_id])

    __table_args__ = (
        Index("ix_generated_company", "company_id"),
        Index("ix_generated_template", "template_id"),
        Index("ix_generated_entity", "linked_entity_id"),
        Index("ix_generated_document", "linked_document_id"),
        Index("ix_generated_created", "created_at"),
        {"comment": "Aus Vorlagen generierte Dokumente (Vorlagen-System)"}
    )

    def __repr__(self) -> str:
        return f"<GeneratedDocument {self.title}>"


class TemplateSnippet(Base):
    """
    Wiederverwendbare Textbausteine für Templates.

    z.B. Standard-Fusszeilen, AGBs, Grussformeln.
    """
    __tablename__ = "template_snippets"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)

    # Identifikation
    name = Column(String(255), nullable=False)
    code = Column(String(50), nullable=False)  # z.B. "AGB-FOOTER"
    description = Column(Text, nullable=True)
    category = Column(String(100), default="general")

    # Inhalt
    content = Column(Text, nullable=False)

    # Status
    is_active = Column(Boolean, default=True)

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("company_id", "code", name="uq_snippet_code"),
        Index("ix_snippet_company", "company_id"),
        Index("ix_snippet_category", "category"),
        Index("ix_snippet_is_active", "is_active"),
        {"comment": "Wiederverwendbare Textbausteine für Templates (Vorlagen-System)"}
    )

    def __repr__(self) -> str:
        return f"<TemplateSnippet {self.code}>"


# =============================================================================
# KNOWLEDGE MANAGEMENT SYSTEM
# =============================================================================


class NoteType(str, Enum):
    """Typen von Knowledge Notes."""

    GENERAL = "general"
    PROCEDURE = "procedure"  # Prozessbeschreibung
    FAQ = "faq"
    TEMPLATE = "template"
    MEETING_NOTES = "meeting_notes"
    DECISION = "decision"
    DOCUMENTATION = "documentation"


class ContentFormat(str, Enum):
    """Format des Note-Inhalts."""

    MARKDOWN = "markdown"
    HTML = "html"
    PLAIN = "plain"


class KnowledgeLinkType(str, Enum):
    """Typen von Knowledge Links."""

    RELATED = "related"  # Allgemein verwandt
    REFERENCES = "references"  # Referenziert
    REPLACES = "replaces"  # Ersetzt
    CONTINUES = "continues"  # Fortsetzung
    CONTRADICTS = "contradicts"  # Widerspricht
    EXPLAINS = "explains"  # Erklärt


class LinkableType(str, Enum):
    """Typen von verlinkbaren Objekten."""

    NOTE = "note"
    DOCUMENT = "document"
    ENTITY = "entity"
    CHECKLIST = "checklist"


class KnowledgeNote(SoftDeleteMixin, Base):
    """
    Wiki-artige Notiz im Knowledge Management System.

    Features:
    - Markdown-Content
    - Hierarchische Struktur (parent_note_id)
    - Polymorph verknüpfbar (Document, Entity, Company)
    - Tags für Kategorisierung
    - Full-Text-Suche (via DB Index)
    """

    __tablename__ = "knowledge_notes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Content
    title = Column(String(500), nullable=False)
    content = Column(Text, nullable=True)
    content_format = Column(String(20), default=ContentFormat.MARKDOWN.value)

    # Kategorisierung
    note_type = Column(String(50), nullable=False, default=NoteType.GENERAL.value)

    # Polymorph Verknüpfungen
    linked_document_id = Column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="SET NULL"),
        nullable=True,
    )
    linked_entity_id = Column(
        UUID(as_uuid=True),
        ForeignKey("business_entities.id", ondelete="SET NULL"),
        nullable=True,
    )
    linked_company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="SET NULL"),
        nullable=True,
    )
    linked_project_id = Column(UUID(as_uuid=True), nullable=True)

    # Hierarchie
    parent_note_id = Column(
        UUID(as_uuid=True),
        ForeignKey("knowledge_notes.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Metadaten
    is_pinned = Column(Boolean, default=False)
    is_template = Column(Boolean, default=False)
    view_count = Column(Integer, default=0)
    tags = Column(CrossDBJSON, default=list)

    # Audit
    created_by_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    updated_by_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    linked_document = relationship("Document", foreign_keys=[linked_document_id])
    linked_entity = relationship("BusinessEntity", foreign_keys=[linked_entity_id])
    linked_company = relationship("Company", foreign_keys=[linked_company_id])
    parent_note = relationship(
        "KnowledgeNote",
        remote_side=[id],
        foreign_keys=[parent_note_id],
        back_populates="child_notes",
    )
    child_notes = relationship(
        "KnowledgeNote",
        back_populates="parent_note",
        foreign_keys=[parent_note_id],
    )
    created_by = relationship("User", foreign_keys=[created_by_id])
    updated_by = relationship("User", foreign_keys=[updated_by_id])
    checklists = relationship(
        "KnowledgeChecklist",
        back_populates="linked_note",
        foreign_keys="KnowledgeChecklist.linked_note_id",
    )

    __table_args__ = (
        Index("ix_knowledge_notes_linked_document_id", "linked_document_id"),
        Index("ix_knowledge_notes_linked_entity_id", "linked_entity_id"),
        Index("ix_knowledge_notes_linked_company_id", "linked_company_id"),
        Index("ix_knowledge_notes_parent_note_id", "parent_note_id"),
        Index("ix_knowledge_notes_note_type", "note_type"),
        Index("ix_knowledge_notes_is_pinned", "is_pinned"),
        Index("ix_knowledge_notes_created_by_id", "created_by_id"),
        Index("ix_knowledge_notes_deleted_at", "deleted_at"),
        {"comment": "Wiki-artige Notizen (Knowledge Management)"}
    )

    def __repr__(self) -> str:
        return f"<KnowledgeNote {self.title[:50]} ({self.id})>"


class KnowledgeChecklist(SoftDeleteMixin, Base):
    """
    Checkliste im Knowledge Management System.

    Features:
    - Titel und Beschreibung
    - Verknüpfbar mit Documents, Entities, Notes
    - Template-Funktion für wiederverwendbare Checklisten
    """

    __tablename__ = "knowledge_checklists"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Content
    title = Column(String(500), nullable=False)
    description = Column(Text, nullable=True)

    # Polymorph Verknüpfungen
    linked_document_id = Column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="SET NULL"),
        nullable=True,
    )
    linked_entity_id = Column(
        UUID(as_uuid=True),
        ForeignKey("business_entities.id", ondelete="SET NULL"),
        nullable=True,
    )
    linked_company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="SET NULL"),
        nullable=True,
    )
    linked_note_id = Column(
        UUID(as_uuid=True),
        ForeignKey("knowledge_notes.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Status
    is_template = Column(Boolean, default=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    # Audit
    created_by_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    items = relationship(
        "KnowledgeChecklistItem",
        back_populates="checklist",
        cascade="all, delete-orphan",
        order_by="KnowledgeChecklistItem.sort_order",
    )
    linked_document = relationship("Document", foreign_keys=[linked_document_id])
    linked_entity = relationship("BusinessEntity", foreign_keys=[linked_entity_id])
    linked_company = relationship("Company", foreign_keys=[linked_company_id])
    linked_note = relationship(
        "KnowledgeNote",
        foreign_keys=[linked_note_id],
        back_populates="checklists",
    )
    created_by = relationship("User", foreign_keys=[created_by_id])

    __table_args__ = (
        Index("ix_knowledge_checklists_linked_document_id", "linked_document_id"),
        Index("ix_knowledge_checklists_linked_entity_id", "linked_entity_id"),
        Index("ix_knowledge_checklists_linked_company_id", "linked_company_id"),
        Index("ix_knowledge_checklists_linked_note_id", "linked_note_id"),
        Index("ix_knowledge_checklists_deleted_at", "deleted_at"),
        {"comment": "Checklisten (Knowledge Management)"}
    )

    @property
    def is_completed(self) -> bool:
        """Prüft ob alle Items abgehakt sind."""
        if not self.items:
            return False
        return all(item.is_completed for item in self.items)

    @property
    def completion_percentage(self) -> float:
        """Berechnet den Fortschritt in Prozent."""
        if not self.items:
            return 0.0
        completed = sum(1 for item in self.items if item.is_completed)
        return (completed / len(self.items)) * 100

    def __repr__(self) -> str:
        return f"<KnowledgeChecklist {self.title[:50]} ({self.id})>"


class KnowledgeChecklistItem(Base):
    """Einzelnes Item in einer Checklist."""

    __tablename__ = "knowledge_checklist_items"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    checklist_id = Column(
        UUID(as_uuid=True),
        ForeignKey("knowledge_checklists.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Content
    text = Column(String(1000), nullable=False)
    description = Column(Text, nullable=True)

    # Status
    is_completed = Column(Boolean, default=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    completed_by_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Sortierung
    sort_order = Column(Integer, default=0)

    # Optional: Deadline
    due_date = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    checklist = relationship("KnowledgeChecklist", back_populates="items")
    completed_by = relationship("User", foreign_keys=[completed_by_id])

    __table_args__ = (
        Index("ix_knowledge_checklist_items_checklist_id", "checklist_id"),
        Index("ix_knowledge_checklist_items_is_completed", "is_completed"),
        Index("ix_knowledge_checklist_items_sort_order", "sort_order"),
        {"comment": "Checklist Items (Knowledge Management)"}
    )

    def __repr__(self) -> str:
        status = "✓" if self.is_completed else "○"
        return f"<KnowledgeChecklistItem {status} {self.text[:30]} ({self.id})>"


class KnowledgeLink(Base):
    """
    Verknüpfung im Knowledge Graph.

    Ermöglicht die Verbindung verschiedener Objekte:
    - Note <-> Note
    - Note <-> Document
    - Note <-> Entity
    - Document <-> Entity
    """

    __tablename__ = "knowledge_links"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Source (polymorph)
    source_type = Column(String(50), nullable=False)
    source_id = Column(UUID(as_uuid=True), nullable=False)

    # Target (polymorph)
    target_type = Column(String(50), nullable=False)
    target_id = Column(UUID(as_uuid=True), nullable=False)

    # Beziehungstyp
    link_type = Column(String(50), nullable=False, default=KnowledgeLinkType.RELATED.value)

    # Metadaten
    description = Column(String(500), nullable=True)
    confidence = Column(Float, nullable=True)  # Für automatisch erstellte Links
    is_bidirectional = Column(Boolean, default=True)

    # Audit
    created_by_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    created_by = relationship("User", foreign_keys=[created_by_id])

    __table_args__ = (
        Index("ix_knowledge_links_source", "source_type", "source_id"),
        Index("ix_knowledge_links_target", "target_type", "target_id"),
        Index("ix_knowledge_links_link_type", "link_type"),
        UniqueConstraint(
            "source_type", "source_id", "target_type", "target_id", "link_type",
            name="uq_knowledge_links_source_target_type",
        ),
        {"comment": "Knowledge Graph Links (Knowledge Management)"}
    )

    def __repr__(self) -> str:
        return f"<KnowledgeLink {self.source_type}:{self.source_id} --[{self.link_type}]--> {self.target_type}:{self.target_id}>"


class KnowledgeTag(Base):
    """Tag für Kategorisierung von Knowledge Items."""

    __tablename__ = "knowledge_tags"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(100), nullable=False, unique=True)
    color = Column(String(7), nullable=True)  # Hex #FF0000
    description = Column(String(500), nullable=True)
    usage_count = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_knowledge_tags_name", "name"),
        Index("ix_knowledge_tags_usage_count", "usage_count"),
        {"comment": "Tags für Knowledge Items (Knowledge Management)"}
    )

    def __repr__(self) -> str:
        return f"<KnowledgeTag {self.name} ({self.usage_count} uses)>"
