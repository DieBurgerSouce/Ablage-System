# -*- coding: utf-8 -*-
"""Zero-Touch OCR migration.

Revision ID: 122
Revises: 121
Create Date: 2026-01-28

This migration adds:
1. zero_touch_results table for automated OCR processing
2. Indexes for performance optimization
3. RLS policy for multi-tenant isolation
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "122"
down_revision = "121"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add zero-touch OCR table and indexes."""

    # ==========================================================================
    # 1. CREATE ZERO_TOUCH_RESULTS TABLE
    # ==========================================================================

    op.create_table(
        "zero_touch_results",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ocr_confidence", sa.Float, nullable=True),
        sa.Column("classification_type", sa.String(50), nullable=True),
        sa.Column("classification_confidence", sa.Float, nullable=True),
        sa.Column("extraction_confidence", sa.Float, nullable=True),
        sa.Column("extracted_fields", postgresql.JSONB, server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("entity_confidence", sa.Float, nullable=True),
        sa.Column("overall_confidence", sa.Float, nullable=True),
        sa.Column("auto_processed", sa.Boolean, default=False, nullable=False, server_default=sa.text("false")),
        sa.Column("requires_review", sa.Boolean, default=True, nullable=False, server_default=sa.text("true")),
        sa.Column("review_completed", sa.Boolean, default=False, nullable=False, server_default=sa.text("false")),
        sa.Column("reviewed_by_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("business_object_type", sa.String(50), nullable=True),
        sa.Column("business_object_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("total_processing_ms", sa.Integer, nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], name="fk_zero_touch_document", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], name="fk_zero_touch_company", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["entity_id"], ["business_entities.id"], name="fk_zero_touch_entity", ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["reviewed_by_id"], ["users.id"], name="fk_zero_touch_reviewer", ondelete="SET NULL"),
    )

    # ==========================================================================
    # 2. CREATE INDEXES
    # ==========================================================================

    # Composite index for company queries with created_at ordering
    op.create_index(
        "ix_zero_touch_company_created",
        "zero_touch_results",
        ["company_id", "created_at"],
    )

    # Unique index on document_id (one-to-one relationship)
    op.create_index(
        "ix_zero_touch_document",
        "zero_touch_results",
        ["document_id"],
        unique=True,
    )

    # Partial index for auto-processed documents
    op.create_index(
        "ix_zero_touch_auto_processed",
        "zero_touch_results",
        ["company_id", "auto_processed"],
        postgresql_where=sa.text("auto_processed = true"),
    )

    # Partial index for documents requiring review
    op.create_index(
        "ix_zero_touch_requires_review",
        "zero_touch_results",
        ["company_id", "requires_review"],
        postgresql_where=sa.text("requires_review = true AND review_completed = false"),
    )

    # ==========================================================================
    # 3. ENABLE ROW LEVEL SECURITY
    # ==========================================================================

    op.execute("ALTER TABLE zero_touch_results ENABLE ROW LEVEL SECURITY;")

    # Create RLS policy for multi-tenant isolation
    op.execute("""
        CREATE POLICY zero_touch_company_isolation ON zero_touch_results
            USING (company_id = current_setting('app.current_company_id')::uuid);
    """)

    # ==========================================================================
    # 4. UPDATE STATISTICS
    # ==========================================================================

    op.execute("ANALYZE zero_touch_results;")


def downgrade() -> None:
    """Remove zero-touch OCR table and indexes."""

    # Drop RLS policy
    op.execute("DROP POLICY IF EXISTS zero_touch_company_isolation ON zero_touch_results;")

    # Drop indexes
    op.drop_index("ix_zero_touch_requires_review", table_name="zero_touch_results")
    op.drop_index("ix_zero_touch_auto_processed", table_name="zero_touch_results")
    op.drop_index("ix_zero_touch_document", table_name="zero_touch_results")
    op.drop_index("ix_zero_touch_company_created", table_name="zero_touch_results")

    # Drop table
    op.drop_table("zero_touch_results")
