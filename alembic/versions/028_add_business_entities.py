"""Add business entities, document groups, and document relationships.

Revision ID: 028_add_business_entities
Revises: 027_add_additional_performance_indexes
Create Date: 2024-12-03

Neue Tabellen:
- business_entities (Kunden/Lieferanten)
- document_groups (Zusammengehoerige Dokumente)
- document_relationships (Beziehungen zwischen Dokumenten)

Document-Erweiterungen:
- business_entity_id (FK -> business_entities)
- group_id (FK -> document_groups)
- page_number_in_group
- is_group_primary
- extracted_data (JSON)
- scan_timestamp
- scan_batch_id
- original_filename_sequence

Diese Migration implementiert das Document Intelligence System fuer:
- Automatische Kunden/Lieferanten-Erkennung (99%+ Praezision)
- Erkennung zusammengehefteter Dokumente
- Dokumentbeziehungen (Verweise, Duplikate, etc.)
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "028"
down_revision = "027"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add business entities, document groups, and relationships."""

    # Check if we're using PostgreSQL
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    # UUID type based on dialect
    if is_postgres:
        uuid_type = postgresql.UUID(as_uuid=True)
        json_type = postgresql.JSONB
    else:
        uuid_type = sa.String(36)
        json_type = sa.JSON

    # =========================================================================
    # 1. CREATE BUSINESS_ENTITIES TABLE
    # =========================================================================
    op.create_table(
        "business_entities",
        sa.Column("id", uuid_type, primary_key=True),

        # Entity identification
        sa.Column("entity_type", sa.String(20), nullable=False, default="supplier"),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("display_name", sa.String(255), nullable=True),
        sa.Column("short_name", sa.String(50), nullable=True),

        # German business identifiers
        sa.Column("vat_id", sa.String(20), unique=True, nullable=True),  # USt-IdNr
        sa.Column("tax_number", sa.String(30), nullable=True),  # Steuernummer
        sa.Column("trade_register", sa.String(50), nullable=True),  # HRB

        # Banking information
        sa.Column("iban", sa.String(34), nullable=True),
        sa.Column("bic", sa.String(11), nullable=True),
        sa.Column("bank_name", sa.String(100), nullable=True),

        # Contact information
        sa.Column("street", sa.String(255), nullable=True),
        sa.Column("street_number", sa.String(20), nullable=True),
        sa.Column("postal_code", sa.String(10), nullable=True),
        sa.Column("city", sa.String(100), nullable=True),
        sa.Column("country", sa.String(2), default="DE"),
        sa.Column("phone", sa.String(30), nullable=True),
        sa.Column("fax", sa.String(30), nullable=True),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("website", sa.String(255), nullable=True),

        # Matching patterns (JSON)
        sa.Column("name_aliases", json_type, nullable=True, default=list),
        sa.Column("address_patterns", json_type, nullable=True, default=list),
        sa.Column("email_domains", json_type, nullable=True, default=list),

        # Statistics
        sa.Column("document_count", sa.Integer, default=0),
        sa.Column("first_document_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_document_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("total_invoice_amount", sa.Float, default=0.0),
        sa.Column("currency", sa.String(3), default="EUR"),

        # Status and confidence
        sa.Column("is_active", sa.Boolean, default=True),
        sa.Column("verified", sa.Boolean, default=False),
        sa.Column("confidence_score", sa.Float, default=0.0),
        sa.Column("auto_detected", sa.Boolean, default=False),

        # Metadata
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("custom_fields", json_type, nullable=True, default=dict),

        # Audit
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.Column("created_by_id", uuid_type, nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),

        # Foreign key
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="SET NULL"),
    )

    # Indexes for business_entities
    op.create_index("ix_business_entities_name", "business_entities", ["name"])
    op.create_index("ix_business_entities_vat_id", "business_entities", ["vat_id"])
    op.create_index("ix_business_entities_iban", "business_entities", ["iban"])
    op.create_index("ix_business_entities_postal_code", "business_entities", ["postal_code"])
    op.create_index("ix_business_entities_entity_type", "business_entities", ["entity_type"])
    op.create_index("ix_business_entities_is_active", "business_entities", ["is_active"])
    op.create_index("ix_business_entities_deleted_at", "business_entities", ["deleted_at"])

    # =========================================================================
    # 2. CREATE DOCUMENT_GROUPS TABLE
    # =========================================================================
    op.create_table(
        "document_groups",
        sa.Column("id", uuid_type, primary_key=True),

        # Group identification
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("group_type", sa.String(30), nullable=False, default="stapled"),

        # Primary document (set after documents table is updated)
        sa.Column("primary_document_id", uuid_type, nullable=True),

        # Detection metadata
        sa.Column("detection_method", sa.String(50), nullable=True),
        sa.Column("detection_confidence", sa.Float, default=0.0),
        sa.Column("detection_details", json_type, nullable=True, default=dict),
        sa.Column("detection_signals", json_type, nullable=True, default=list),

        # Content aggregation
        sa.Column("total_pages", sa.Integer, default=1),
        sa.Column("combined_text", sa.Text, nullable=True),
        sa.Column("combined_text_hash", sa.String(64), nullable=True),

        # Business context
        sa.Column("business_entity_id", uuid_type, nullable=True),
        sa.Column("document_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reference_number", sa.String(100), nullable=True),

        # Extracted data
        sa.Column("extracted_data", json_type, nullable=True, default=dict),

        # User interaction
        sa.Column("user_confirmed", sa.Boolean, default=False),
        sa.Column("user_split", sa.Boolean, default=False),
        sa.Column("confirmation_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("confirmed_by_id", uuid_type, nullable=True),

        # Validation queue
        sa.Column("needs_review", sa.Boolean, default=False),
        sa.Column("review_priority", sa.Integer, default=5),

        # Audit
        sa.Column("owner_id", uuid_type, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),

        # Foreign keys
        sa.ForeignKeyConstraint(["business_entity_id"], ["business_entities.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["confirmed_by_id"], ["users.id"], ondelete="SET NULL"),
    )

    # Indexes for document_groups
    op.create_index("ix_document_groups_group_type", "document_groups", ["group_type"])
    op.create_index("ix_document_groups_detection_confidence", "document_groups", ["detection_confidence"])
    op.create_index("ix_document_groups_business_entity_id", "document_groups", ["business_entity_id"])
    op.create_index("ix_document_groups_owner_id", "document_groups", ["owner_id"])
    op.create_index("ix_document_groups_needs_review", "document_groups", ["needs_review"])
    op.create_index("ix_document_groups_user_confirmed", "document_groups", ["user_confirmed"])
    op.create_index("ix_document_groups_created_at", "document_groups", ["created_at"])
    op.create_index("ix_document_groups_deleted_at", "document_groups", ["deleted_at"])

    # =========================================================================
    # 3. ADD COLUMNS TO DOCUMENTS TABLE
    # =========================================================================

    # Add new columns to documents
    op.add_column("documents", sa.Column("business_entity_id", uuid_type, nullable=True))
    op.add_column("documents", sa.Column("group_id", uuid_type, nullable=True))
    op.add_column("documents", sa.Column("page_number_in_group", sa.Integer, nullable=True))
    op.add_column("documents", sa.Column("is_group_primary", sa.Boolean, default=False))
    op.add_column("documents", sa.Column("extracted_data", json_type, nullable=True))
    op.add_column("documents", sa.Column("scan_timestamp", sa.DateTime(timezone=True), nullable=True))
    op.add_column("documents", sa.Column("scan_batch_id", sa.String(100), nullable=True))
    op.add_column("documents", sa.Column("original_filename_sequence", sa.Integer, nullable=True))

    # Foreign keys for documents
    op.create_foreign_key(
        "fk_documents_business_entity",
        "documents",
        "business_entities",
        ["business_entity_id"],
        ["id"],
        ondelete="SET NULL"
    )
    op.create_foreign_key(
        "fk_documents_group",
        "documents",
        "document_groups",
        ["group_id"],
        ["id"],
        ondelete="SET NULL"
    )

    # Indexes for new document columns
    op.create_index("ix_documents_business_entity_id", "documents", ["business_entity_id"])
    op.create_index("ix_documents_group_id", "documents", ["group_id"])
    op.create_index("ix_documents_scan_batch_id", "documents", ["scan_batch_id"])
    op.create_index("ix_documents_entity_created", "documents", ["business_entity_id", "created_at"])
    op.create_index("ix_documents_group_sequence", "documents", ["group_id", "page_number_in_group"])

    # Now add FK for primary_document_id in document_groups
    op.create_foreign_key(
        "fk_document_groups_primary_document",
        "document_groups",
        "documents",
        ["primary_document_id"],
        ["id"],
        ondelete="SET NULL"
    )

    # =========================================================================
    # 4. CREATE DOCUMENT_RELATIONSHIPS TABLE
    # =========================================================================
    op.create_table(
        "document_relationships",
        sa.Column("id", uuid_type, primary_key=True),

        # Relationship endpoints
        sa.Column("source_document_id", uuid_type, nullable=False),
        sa.Column("target_document_id", uuid_type, nullable=False),

        # Relationship details
        sa.Column("relationship_type", sa.String(30), nullable=False),
        sa.Column("confidence", sa.Float, default=1.0),

        # Ordering
        sa.Column("sequence_number", sa.Integer, nullable=True),

        # Detection metadata
        sa.Column("detected_by", sa.String(50), nullable=True),
        sa.Column("detection_details", json_type, nullable=True, default=dict),

        # User interaction
        sa.Column("user_confirmed", sa.Boolean, default=False),
        sa.Column("user_rejected", sa.Boolean, default=False),

        # Audit
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("created_by_id", uuid_type, nullable=True),

        # Foreign keys
        sa.ForeignKeyConstraint(["source_document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["target_document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="SET NULL"),
    )

    # Indexes for document_relationships
    op.create_index("ix_document_relationships_source", "document_relationships", ["source_document_id"])
    op.create_index("ix_document_relationships_target", "document_relationships", ["target_document_id"])
    op.create_index("ix_document_relationships_type", "document_relationships", ["relationship_type"])
    op.create_index("ix_document_relationships_confidence", "document_relationships", ["confidence"])
    op.create_index(
        "ix_document_relationships_unique",
        "document_relationships",
        ["source_document_id", "target_document_id", "relationship_type"],
        unique=True
    )


def downgrade() -> None:
    """Remove business entities, document groups, and relationships."""

    # =========================================================================
    # 1. DROP DOCUMENT_RELATIONSHIPS TABLE
    # =========================================================================
    op.drop_index("ix_document_relationships_unique", table_name="document_relationships")
    op.drop_index("ix_document_relationships_confidence", table_name="document_relationships")
    op.drop_index("ix_document_relationships_type", table_name="document_relationships")
    op.drop_index("ix_document_relationships_target", table_name="document_relationships")
    op.drop_index("ix_document_relationships_source", table_name="document_relationships")
    op.drop_table("document_relationships")

    # =========================================================================
    # 2. DROP FK FOR PRIMARY_DOCUMENT IN DOCUMENT_GROUPS
    # =========================================================================
    op.drop_constraint("fk_document_groups_primary_document", "document_groups", type_="foreignkey")

    # =========================================================================
    # 3. REMOVE COLUMNS FROM DOCUMENTS TABLE
    # =========================================================================
    op.drop_index("ix_documents_group_sequence", table_name="documents")
    op.drop_index("ix_documents_entity_created", table_name="documents")
    op.drop_index("ix_documents_scan_batch_id", table_name="documents")
    op.drop_index("ix_documents_group_id", table_name="documents")
    op.drop_index("ix_documents_business_entity_id", table_name="documents")

    op.drop_constraint("fk_documents_group", "documents", type_="foreignkey")
    op.drop_constraint("fk_documents_business_entity", "documents", type_="foreignkey")

    op.drop_column("documents", "original_filename_sequence")
    op.drop_column("documents", "scan_batch_id")
    op.drop_column("documents", "scan_timestamp")
    op.drop_column("documents", "extracted_data")
    op.drop_column("documents", "is_group_primary")
    op.drop_column("documents", "page_number_in_group")
    op.drop_column("documents", "group_id")
    op.drop_column("documents", "business_entity_id")

    # =========================================================================
    # 4. DROP DOCUMENT_GROUPS TABLE
    # =========================================================================
    op.drop_index("ix_document_groups_deleted_at", table_name="document_groups")
    op.drop_index("ix_document_groups_created_at", table_name="document_groups")
    op.drop_index("ix_document_groups_user_confirmed", table_name="document_groups")
    op.drop_index("ix_document_groups_needs_review", table_name="document_groups")
    op.drop_index("ix_document_groups_owner_id", table_name="document_groups")
    op.drop_index("ix_document_groups_business_entity_id", table_name="document_groups")
    op.drop_index("ix_document_groups_detection_confidence", table_name="document_groups")
    op.drop_index("ix_document_groups_group_type", table_name="document_groups")
    op.drop_table("document_groups")

    # =========================================================================
    # 5. DROP BUSINESS_ENTITIES TABLE
    # =========================================================================
    op.drop_index("ix_business_entities_deleted_at", table_name="business_entities")
    op.drop_index("ix_business_entities_is_active", table_name="business_entities")
    op.drop_index("ix_business_entities_entity_type", table_name="business_entities")
    op.drop_index("ix_business_entities_postal_code", table_name="business_entities")
    op.drop_index("ix_business_entities_iban", table_name="business_entities")
    op.drop_index("ix_business_entities_vat_id", table_name="business_entities")
    op.drop_index("ix_business_entities_name", table_name="business_entities")
    op.drop_table("business_entities")
