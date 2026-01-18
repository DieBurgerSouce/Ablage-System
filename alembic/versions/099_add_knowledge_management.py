"""Add Knowledge Management System.

Revision ID: 099_add_knowledge_management
Revises: 098_multi_tenant_enhancements
Create Date: 2026-01-17

Knowledge Management System mit:
- KnowledgeNote: Wiki-artige Notizen
- KnowledgeChecklist: Checklisten
- KnowledgeLink: Knowledge Graph Verknuepfungen
- KnowledgeTag: Tags fuer Kategorisierung
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "099_add_knowledge_management"
down_revision = "098_multi_tenant_enhancements"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add Knowledge Management tables."""

    # Check dialect for cross-database compatibility
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    if is_postgres:
        uuid_type = postgresql.UUID(as_uuid=True)
        json_type = postgresql.JSONB
    else:
        uuid_type = sa.String(36)
        json_type = sa.JSON

    # =========================================================================
    # 1. KNOWLEDGE_NOTES - Wiki-artige Notizen
    # =========================================================================
    op.create_table(
        "knowledge_notes",
        sa.Column("id", uuid_type, primary_key=True),

        # Content
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("content", sa.Text, nullable=True),  # Markdown content
        sa.Column("content_format", sa.String(20), server_default="markdown"),  # markdown, html, plain

        # Kategorisierung
        sa.Column("note_type", sa.String(50), nullable=False, server_default="general"),
        # Types: general, procedure, faq, template, meeting_notes, decision

        # Verknuepfungen (polymorph)
        sa.Column("linked_document_id", uuid_type, nullable=True),
        sa.Column("linked_entity_id", uuid_type, nullable=True),
        sa.Column("linked_company_id", uuid_type, nullable=True),
        sa.Column("linked_project_id", uuid_type, nullable=True),

        # Hierarchie
        sa.Column("parent_note_id", uuid_type, nullable=True),  # Fuer verschachtelte Wiki-Seiten

        # Metadaten
        sa.Column("is_pinned", sa.Boolean, server_default="false"),
        sa.Column("is_template", sa.Boolean, server_default="false"),
        sa.Column("view_count", sa.Integer, server_default="0"),
        sa.Column("tags", json_type, server_default="[]"),  # ["wichtig", "prozess"]

        # Audit
        sa.Column("created_by_id", uuid_type, nullable=True),
        sa.Column("updated_by_id", uuid_type, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),

        # Foreign Keys
        sa.ForeignKeyConstraint(["linked_document_id"], ["documents.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["linked_entity_id"], ["business_entities.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["linked_company_id"], ["companies.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["parent_note_id"], ["knowledge_notes.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["updated_by_id"], ["users.id"], ondelete="SET NULL"),
    )

    # Indexes
    op.create_index("ix_knowledge_notes_linked_document_id", "knowledge_notes", ["linked_document_id"])
    op.create_index("ix_knowledge_notes_linked_entity_id", "knowledge_notes", ["linked_entity_id"])
    op.create_index("ix_knowledge_notes_linked_company_id", "knowledge_notes", ["linked_company_id"])
    op.create_index("ix_knowledge_notes_parent_note_id", "knowledge_notes", ["parent_note_id"])
    op.create_index("ix_knowledge_notes_note_type", "knowledge_notes", ["note_type"])
    op.create_index("ix_knowledge_notes_is_pinned", "knowledge_notes", ["is_pinned"])
    op.create_index("ix_knowledge_notes_created_by_id", "knowledge_notes", ["created_by_id"])
    op.create_index("ix_knowledge_notes_deleted_at", "knowledge_notes", ["deleted_at"])

    if is_postgres:
        # GIN Index fuer Tag-Suche
        op.execute("""
            CREATE INDEX ix_knowledge_notes_tags_gin ON knowledge_notes USING GIN (tags);
        """)
        # Full-text search auf title und content
        op.execute("""
            CREATE INDEX ix_knowledge_notes_fulltext ON knowledge_notes
            USING GIN (to_tsvector('german', coalesce(title, '') || ' ' || coalesce(content, '')));
        """)

    # =========================================================================
    # 2. KNOWLEDGE_CHECKLISTS - Checklisten
    # =========================================================================
    op.create_table(
        "knowledge_checklists",
        sa.Column("id", uuid_type, primary_key=True),

        # Content
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("description", sa.Text, nullable=True),

        # Verknuepfungen (polymorph)
        sa.Column("linked_document_id", uuid_type, nullable=True),
        sa.Column("linked_entity_id", uuid_type, nullable=True),
        sa.Column("linked_company_id", uuid_type, nullable=True),
        sa.Column("linked_note_id", uuid_type, nullable=True),

        # Status
        sa.Column("is_template", sa.Boolean, server_default="false"),  # Wiederverwendbare Vorlage
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),

        # Audit
        sa.Column("created_by_id", uuid_type, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),

        # Foreign Keys
        sa.ForeignKeyConstraint(["linked_document_id"], ["documents.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["linked_entity_id"], ["business_entities.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["linked_company_id"], ["companies.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["linked_note_id"], ["knowledge_notes.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="SET NULL"),
    )

    # Indexes
    op.create_index("ix_knowledge_checklists_linked_document_id", "knowledge_checklists", ["linked_document_id"])
    op.create_index("ix_knowledge_checklists_linked_entity_id", "knowledge_checklists", ["linked_entity_id"])
    op.create_index("ix_knowledge_checklists_linked_company_id", "knowledge_checklists", ["linked_company_id"])
    op.create_index("ix_knowledge_checklists_linked_note_id", "knowledge_checklists", ["linked_note_id"])
    op.create_index("ix_knowledge_checklists_deleted_at", "knowledge_checklists", ["deleted_at"])

    # =========================================================================
    # 3. KNOWLEDGE_CHECKLIST_ITEMS - Einzelne Checklist-Items
    # =========================================================================
    op.create_table(
        "knowledge_checklist_items",
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column("checklist_id", uuid_type, nullable=False),

        # Content
        sa.Column("text", sa.String(1000), nullable=False),
        sa.Column("description", sa.Text, nullable=True),

        # Status
        sa.Column("is_completed", sa.Boolean, server_default="false"),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_by_id", uuid_type, nullable=True),

        # Sortierung
        sa.Column("sort_order", sa.Integer, server_default="0"),

        # Optional: Deadline
        sa.Column("due_date", sa.DateTime(timezone=True), nullable=True),

        # Foreign Keys
        sa.ForeignKeyConstraint(["checklist_id"], ["knowledge_checklists.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["completed_by_id"], ["users.id"], ondelete="SET NULL"),
    )

    op.create_index("ix_knowledge_checklist_items_checklist_id", "knowledge_checklist_items", ["checklist_id"])
    op.create_index("ix_knowledge_checklist_items_is_completed", "knowledge_checklist_items", ["is_completed"])
    op.create_index("ix_knowledge_checklist_items_sort_order", "knowledge_checklist_items", ["sort_order"])

    # =========================================================================
    # 4. KNOWLEDGE_LINKS - Knowledge Graph Verknuepfungen
    # =========================================================================
    op.create_table(
        "knowledge_links",
        sa.Column("id", uuid_type, primary_key=True),

        # Source (polymorph)
        sa.Column("source_type", sa.String(50), nullable=False),  # note, document, entity, checklist
        sa.Column("source_id", uuid_type, nullable=False),

        # Target (polymorph)
        sa.Column("target_type", sa.String(50), nullable=False),  # note, document, entity, checklist
        sa.Column("target_id", uuid_type, nullable=False),

        # Beziehungstyp
        sa.Column("link_type", sa.String(50), nullable=False, server_default="related"),
        # Types: related, references, replaces, continues, contradicts, explains

        # Metadaten
        sa.Column("description", sa.String(500), nullable=True),
        sa.Column("confidence", sa.Float, nullable=True),  # Fuer automatisch erstellte Links
        sa.Column("is_bidirectional", sa.Boolean, server_default="true"),

        # Audit
        sa.Column("created_by_id", uuid_type, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),

        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("source_type", "source_id", "target_type", "target_id", "link_type",
                           name="uq_knowledge_links_source_target_type"),
    )

    op.create_index("ix_knowledge_links_source", "knowledge_links", ["source_type", "source_id"])
    op.create_index("ix_knowledge_links_target", "knowledge_links", ["target_type", "target_id"])
    op.create_index("ix_knowledge_links_link_type", "knowledge_links", ["link_type"])

    # =========================================================================
    # 5. KNOWLEDGE_TAGS - Tags fuer Kategorisierung (normalisiert)
    # =========================================================================
    op.create_table(
        "knowledge_tags",
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column("name", sa.String(100), nullable=False, unique=True),
        sa.Column("color", sa.String(7), nullable=True),  # Hex color #FF0000
        sa.Column("description", sa.String(500), nullable=True),
        sa.Column("usage_count", sa.Integer, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_index("ix_knowledge_tags_name", "knowledge_tags", ["name"])
    op.create_index("ix_knowledge_tags_usage_count", "knowledge_tags", ["usage_count"])


def downgrade() -> None:
    """Remove Knowledge Management tables."""

    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    # Drop indexes first
    if is_postgres:
        op.execute("DROP INDEX IF EXISTS ix_knowledge_notes_fulltext")
        op.execute("DROP INDEX IF EXISTS ix_knowledge_notes_tags_gin")

    # Drop tables in reverse order
    op.drop_table("knowledge_tags")
    op.drop_table("knowledge_links")
    op.drop_table("knowledge_checklist_items")
    op.drop_table("knowledge_checklists")
    op.drop_table("knowledge_notes")
