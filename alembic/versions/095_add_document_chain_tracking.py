"""Add document chain tracking for order workflows.

Revision ID: 095_add_document_chain_tracking
Revises: 094_add_skonto_and_partial_payments
Create Date: 2026-01-16

Features:
- DocumentRelationship Tabelle für Verknüpfungen
- Chain-Identifier für zusammengehörige Dokumente
- Unterstützung für: Angebot → Auftrag → Lieferschein → Rechnung
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "095_add_document_chain_tracking"
down_revision = "094"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create document chain tracking (idempotent)."""
    conn = op.get_bind()

    # 1. Create document_relationships table
    # Check if table exists AND has correct schema (chain_id column)
    table_exists = conn.execute(sa.text("""
        SELECT EXISTS (
            SELECT FROM information_schema.tables
            WHERE table_schema = 'public'
            AND table_name = 'document_relationships'
        )
    """)).scalar()

    has_correct_schema = False
    if table_exists:
        has_correct_schema = conn.execute(sa.text("""
            SELECT EXISTS (
                SELECT FROM information_schema.columns
                WHERE table_schema = 'public'
                AND table_name = 'document_relationships'
                AND column_name = 'chain_id'
            )
        """)).scalar()

        if not has_correct_schema:
            # Table exists but with wrong schema - drop it if empty
            count = conn.execute(sa.text("SELECT COUNT(*) FROM document_relationships")).scalar()
            if count == 0:
                op.drop_table("document_relationships")
                table_exists = False
            else:
                raise RuntimeError("document_relationships table has wrong schema and contains data!")

    if not table_exists:
        op.create_table(
            "document_relationships",
            sa.Column(
                "id",
                postgresql.UUID(as_uuid=True),
                primary_key=True,
                server_default=sa.text("gen_random_uuid()"),
            ),
            sa.Column(
                "source_document_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("documents.id", ondelete="CASCADE"),
                nullable=False,
                index=True,
            ),
            sa.Column(
                "target_document_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("documents.id", ondelete="CASCADE"),
                nullable=False,
                index=True,
            ),
            sa.Column(
                "relationship_type",
                sa.String(50),
                nullable=False,
                comment="quote_to_order, order_to_delivery, delivery_to_invoice, etc."
            ),
            sa.Column(
                "chain_id",
                sa.String(100),
                nullable=True,
                index=True,
            ),
            sa.Column(
                "auto_detected",
                sa.Boolean(),
                default=False,
                nullable=False,
                server_default="false",
            ),
            sa.Column(
                "confidence_score",
                sa.Float(),
                nullable=True,
            ),
            sa.Column(
                "validated",
                sa.Boolean(),
                default=False,
                nullable=False,
                server_default="false",
            ),
            sa.Column(
                "validated_at",
                sa.DateTime(timezone=True),
                nullable=True,
            ),
            sa.Column(
                "validated_by_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("users.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column(
                "notes",
                sa.Text(),
                nullable=True,
            ),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("NOW()"),
            ),
            sa.Column(
                "created_by_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("users.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column(
                "company_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("companies.id", ondelete="RESTRICT"),
                nullable=False,
                index=True,
            ),
        )

    # Create constraints/indexes only if they don't exist
    constraint_exists = conn.execute(sa.text("""
        SELECT EXISTS (
            SELECT FROM pg_constraint
            WHERE conname = 'uq_document_relationships_pair'
        )
    """)).scalar()
    if not constraint_exists:
        op.create_unique_constraint(
            "uq_document_relationships_pair",
            "document_relationships",
            ["source_document_id", "target_document_id", "relationship_type"]
        )

    # Check and create indexes
    idx_chain_exists = conn.execute(sa.text("""
        SELECT EXISTS (
            SELECT FROM pg_indexes
            WHERE indexname = 'ix_document_relationships_chain'
        )
    """)).scalar()
    if not idx_chain_exists:
        op.create_index(
            "ix_document_relationships_chain",
            "document_relationships",
            ["chain_id", "company_id"],
            unique=False,
        )

    idx_type_exists = conn.execute(sa.text("""
        SELECT EXISTS (
            SELECT FROM pg_indexes
            WHERE indexname = 'ix_document_relationships_type'
        )
    """)).scalar()
    if not idx_type_exists:
        op.create_index(
            "ix_document_relationships_type",
            "document_relationships",
            ["relationship_type"],
            unique=False,
        )

    # 2. Add chain-related fields to documents table (idempotent)
    def column_exists(table, column):
        return conn.execute(sa.text(f"""
            SELECT EXISTS (
                SELECT FROM information_schema.columns
                WHERE table_schema = 'public'
                AND table_name = '{table}'
                AND column_name = '{column}'
            )
        """)).scalar()

    if not column_exists("documents", "chain_id"):
        op.add_column(
            "documents",
            sa.Column("chain_id", sa.String(100), nullable=True)
        )
        op.create_index("ix_documents_chain_id", "documents", ["chain_id"])

    if not column_exists("documents", "chain_position"):
        op.add_column(
            "documents",
            sa.Column("chain_position", sa.Integer(), nullable=True)
        )

    if not column_exists("documents", "chain_root_document_id"):
        op.add_column(
            "documents",
            sa.Column(
                "chain_root_document_id",
                postgresql.UUID(as_uuid=True),
                nullable=True
            )
        )
        # Add FK constraint separately
        op.create_foreign_key(
            "fk_documents_chain_root",
            "documents", "documents",
            ["chain_root_document_id"], ["id"],
            ondelete="SET NULL"
        )

    # 3. Create document_chain_discrepancies table IF NOT EXISTS
    discrepancies_exists = conn.execute(sa.text("""
        SELECT EXISTS (
            SELECT FROM information_schema.tables
            WHERE table_schema = 'public'
            AND table_name = 'document_chain_discrepancies'
        )
    """)).scalar()

    if not discrepancies_exists:
        op.create_table(
            "document_chain_discrepancies",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
            sa.Column("chain_id", sa.String(100), nullable=False, index=True),
            sa.Column("source_document_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False),
            sa.Column("target_document_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False),
            sa.Column("discrepancy_type", sa.String(50), nullable=False),
            sa.Column("field_name", sa.String(100), nullable=True),
            sa.Column("expected_value", sa.String(500), nullable=True),
            sa.Column("actual_value", sa.String(500), nullable=True),
            sa.Column("difference_amount", sa.Float(), nullable=True),
            sa.Column("difference_percentage", sa.Float(), nullable=True),
            sa.Column("severity", sa.String(20), nullable=False, server_default="warning"),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("is_resolved", sa.Boolean(), nullable=False, server_default="false"),
            sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("resolved_by_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("resolution_notes", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
            sa.Column("company_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("companies.id", ondelete="RESTRICT"), nullable=False, index=True),
        )

    # Index for unresolved discrepancies (idempotent)
    idx_discrepancies_exists = conn.execute(sa.text("""
        SELECT EXISTS (
            SELECT FROM pg_indexes
            WHERE indexname = 'ix_chain_discrepancies_unresolved'
        )
    """)).scalar()
    if not idx_discrepancies_exists:
        op.create_index(
            "ix_chain_discrepancies_unresolved",
            "document_chain_discrepancies",
            ["company_id", "is_resolved"],
            unique=False,
            postgresql_where=sa.text("is_resolved = false")
        )

    # 4. Create view for complete chains (CREATE OR REPLACE is idempotent)
    op.execute("""
        CREATE OR REPLACE VIEW v_document_chains AS
        SELECT
            d.chain_id,
            d.company_id,
            COUNT(DISTINCT d.id) as document_count,
            MIN(d.created_at) as chain_started_at,
            MAX(d.created_at) as chain_updated_at,
            ARRAY_AGG(DISTINCT d.document_type) as document_types,
            SUM(CASE WHEN d.document_type = 'invoice' THEN 1 ELSE 0 END) as invoice_count,
            SUM(CASE WHEN d.document_type = 'delivery_note' THEN 1 ELSE 0 END) as delivery_note_count,
            SUM(CASE WHEN d.document_type = 'order' THEN 1 ELSE 0 END) as order_count,
            (SELECT COUNT(*) FROM document_chain_discrepancies dcd
             WHERE dcd.chain_id = d.chain_id AND dcd.is_resolved = false) as open_discrepancies
        FROM documents d
        WHERE d.chain_id IS NOT NULL
          AND d.deleted_at IS NULL
        GROUP BY d.chain_id, d.company_id;
    """)


def downgrade() -> None:
    """Remove document chain tracking."""
    # Drop view
    op.execute("DROP VIEW IF EXISTS v_document_chains;")

    # Drop discrepancies table
    op.drop_index("ix_chain_discrepancies_unresolved", table_name="document_chain_discrepancies")
    op.drop_table("document_chain_discrepancies")

    # Drop columns from documents
    op.drop_column("documents", "chain_root_document_id")
    op.drop_column("documents", "chain_position")
    op.drop_column("documents", "chain_id")

    # Drop relationships table
    op.drop_index("ix_document_relationships_type", table_name="document_relationships")
    op.drop_index("ix_document_relationships_chain", table_name="document_relationships")
    op.drop_constraint("uq_document_relationships_pair", "document_relationships", type_="unique")
    op.drop_table("document_relationships")
