# -*- coding: utf-8 -*-
"""Add Saved Filters for Server-side Filter Persistence and Sharing.

PHASE 4.5: Frontend UX Enhancement - Saved Filters + Sharing

Neue Tabellen:
- saved_filters: Gespeicherte Filter pro User/Company mit Sharing-Option

Features:
- Server-seitige Persistenz statt LocalStorage
- Sharing von Filtern innerhalb einer Company
- Feature-spezifische Filter (documents, invoices, entities, etc.)
- JSONB fuer flexible Filter-Konfiguration

Revision ID: 116_add_saved_filters
Revises: 115_ocr_correction_feedback
Create Date: 2026-01-23
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "116_add_saved_filters"
down_revision: Union[str, None] = "115"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ==========================================================================
    # SAVED FILTERS TABLE
    # ==========================================================================
    op.create_table(
        "saved_filters",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),

        # Feature this filter applies to (documents, invoices, entities, transactions, etc.)
        sa.Column("feature", sa.String(100), nullable=False),

        # JSONB for flexible filter configuration
        sa.Column("filter_config", postgresql.JSONB, nullable=False, server_default="{}"),

        # Sharing options
        sa.Column("is_shared", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("is_default", sa.Boolean, nullable=False, server_default="false"),

        # Usage tracking
        sa.Column("use_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),

        # Soft delete support
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),

        # Timestamps
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), onupdate=sa.text("CURRENT_TIMESTAMP"), nullable=False),
    )

    # Indexes for efficient querying
    op.create_index("ix_saved_filters_user_id", "saved_filters", ["user_id"])
    op.create_index("ix_saved_filters_company_id", "saved_filters", ["company_id"])
    op.create_index("ix_saved_filters_feature", "saved_filters", ["feature"])
    op.create_index("ix_saved_filters_is_shared", "saved_filters", ["is_shared"])
    op.create_index("ix_saved_filters_deleted_at", "saved_filters", ["deleted_at"])

    # Composite index for common queries (user's filters for a feature)
    op.create_index(
        "ix_saved_filters_user_feature",
        "saved_filters",
        ["user_id", "feature", "deleted_at"]
    )

    # Composite index for shared filters within a company
    op.create_index(
        "ix_saved_filters_company_shared",
        "saved_filters",
        ["company_id", "feature", "is_shared", "deleted_at"]
    )

    # ==========================================================================
    # RLS POLICY for Multi-Tenant Isolation
    # ==========================================================================
    op.execute("ALTER TABLE saved_filters ENABLE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY saved_filters_select_policy ON saved_filters
            FOR SELECT
            USING (
                deleted_at IS NULL AND (
                    user_id = current_setting('app.user_id', true)::uuid
                    OR (is_shared = true AND company_id = current_setting('app.company_id', true)::uuid)
                )
            )
    """)
    op.execute("""
        CREATE POLICY saved_filters_insert_policy ON saved_filters
            FOR INSERT
            WITH CHECK (
                user_id = current_setting('app.user_id', true)::uuid
                AND company_id = current_setting('app.company_id', true)::uuid
            )
    """)
    op.execute("""
        CREATE POLICY saved_filters_update_policy ON saved_filters
            FOR UPDATE
            USING (user_id = current_setting('app.user_id', true)::uuid)
            WITH CHECK (user_id = current_setting('app.user_id', true)::uuid)
    """)
    op.execute("""
        CREATE POLICY saved_filters_delete_policy ON saved_filters
            FOR DELETE
            USING (user_id = current_setting('app.user_id', true)::uuid)
    """)


def downgrade() -> None:
    # Drop RLS policies first
    op.execute("DROP POLICY IF EXISTS saved_filters_delete_policy ON saved_filters")
    op.execute("DROP POLICY IF EXISTS saved_filters_update_policy ON saved_filters")
    op.execute("DROP POLICY IF EXISTS saved_filters_insert_policy ON saved_filters")
    op.execute("DROP POLICY IF EXISTS saved_filters_select_policy ON saved_filters")
    op.execute("ALTER TABLE saved_filters DISABLE ROW LEVEL SECURITY")

    # Drop indexes
    op.drop_index("ix_saved_filters_company_shared", table_name="saved_filters")
    op.drop_index("ix_saved_filters_user_feature", table_name="saved_filters")
    op.drop_index("ix_saved_filters_deleted_at", table_name="saved_filters")
    op.drop_index("ix_saved_filters_is_shared", table_name="saved_filters")
    op.drop_index("ix_saved_filters_feature", table_name="saved_filters")
    op.drop_index("ix_saved_filters_company_id", table_name="saved_filters")
    op.drop_index("ix_saved_filters_user_id", table_name="saved_filters")

    # Drop table
    op.drop_table("saved_filters")
