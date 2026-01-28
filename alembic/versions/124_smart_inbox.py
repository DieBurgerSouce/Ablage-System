# -*- coding: utf-8 -*-
"""Smart Inbox - KI-priorisierte Aufgabenliste.

Revision ID: 124
Revises: 123
Create Date: 2026-01-28

This migration adds:
1. smart_inbox_items table for prioritized task management
2. user_behavior_logs table for ML training data
3. Indexes for performance optimization
4. RLS policies for multi-tenant isolation
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "124"
down_revision = "123"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add Smart Inbox tables and indexes."""

    # ==========================================================================
    # 1. CREATE SMART_INBOX_ITEMS TABLE
    # ==========================================================================

    op.create_table(
        "smart_inbox_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_type", sa.String(50), nullable=False),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("category", sa.String(50), nullable=True),
        sa.Column("raw_priority", sa.Float, server_default=sa.text("50.0"), nullable=False),
        sa.Column("ml_priority", sa.Float, server_default=sa.text("50.0"), nullable=False),
        sa.Column("urgency_score", sa.Float, server_default=sa.text("0.0"), nullable=False),
        sa.Column("importance_score", sa.Float, server_default=sa.text("0.0"), nullable=False),
        sa.Column("status", sa.String(20), server_default=sa.text("'pending'"), nullable=False),
        sa.Column("deadline", sa.DateTime(timezone=True), nullable=True),
        sa.Column("snoozed_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("recommended_actions", postgresql.JSONB, server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("completed_action", sa.String(100), nullable=True),
        sa.Column("context_data", postgresql.JSONB, server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_inbox_item_user", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], name="fk_inbox_item_company", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], name="fk_inbox_item_document", ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["entity_id"], ["business_entities.id"], name="fk_inbox_item_entity", ondelete="SET NULL"),
    )

    # ==========================================================================
    # 2. CREATE USER_BEHAVIOR_LOGS TABLE
    # ==========================================================================

    op.create_table(
        "user_behavior_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("inbox_item_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("action", sa.String(50), nullable=False),
        sa.Column("source_type", sa.String(50), nullable=True),
        sa.Column("time_spent_ms", sa.Integer, server_default=sa.text("0"), nullable=False),
        sa.Column("context_page", sa.String(200), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_behavior_log_user", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], name="fk_behavior_log_company", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["inbox_item_id"], ["smart_inbox_items.id"], name="fk_behavior_log_inbox_item", ondelete="CASCADE"),
    )

    # ==========================================================================
    # 3. CREATE INDEXES - SMART_INBOX_ITEMS
    # ==========================================================================

    # Composite index for user queries with status filtering
    op.create_index(
        "ix_smart_inbox_user_status",
        "smart_inbox_items",
        ["user_id", "status"],
    )

    # Composite index for company queries with created_at ordering
    op.create_index(
        "ix_smart_inbox_company_created",
        "smart_inbox_items",
        ["company_id", "created_at"],
    )

    # Partial index for pending items sorted by ML priority
    op.create_index(
        "ix_smart_inbox_pending_priority",
        "smart_inbox_items",
        ["user_id", "ml_priority"],
        postgresql_where=sa.text("status = 'pending'"),
    )

    # Partial index for snoozed items
    op.create_index(
        "ix_smart_inbox_snoozed",
        "smart_inbox_items",
        ["user_id", "snoozed_until"],
        postgresql_where=sa.text("status = 'snoozed'"),
    )

    # Index for deadline-based queries
    op.create_index(
        "ix_smart_inbox_deadline",
        "smart_inbox_items",
        ["user_id", "deadline"],
        postgresql_where=sa.text("deadline IS NOT NULL AND status = 'pending'"),
    )

    # Index for source tracking
    op.create_index(
        "ix_smart_inbox_source",
        "smart_inbox_items",
        ["source_type", "source_id"],
    )

    # ==========================================================================
    # 4. CREATE INDEXES - USER_BEHAVIOR_LOGS
    # ==========================================================================

    # Composite index for user behavior analysis
    op.create_index(
        "ix_behavior_logs_user_created",
        "user_behavior_logs",
        ["user_id", "created_at"],
    )

    # Composite index for company analytics
    op.create_index(
        "ix_behavior_logs_company_created",
        "user_behavior_logs",
        ["company_id", "created_at"],
    )

    # Index for inbox item correlation
    op.create_index(
        "ix_behavior_logs_item",
        "user_behavior_logs",
        ["inbox_item_id"],
    )

    # Index for action-based queries
    op.create_index(
        "ix_behavior_logs_action",
        "user_behavior_logs",
        ["action"],
    )

    # ==========================================================================
    # 5. ENABLE ROW LEVEL SECURITY
    # ==========================================================================

    # Smart Inbox Items RLS
    op.execute("ALTER TABLE smart_inbox_items ENABLE ROW LEVEL SECURITY;")

    op.execute("""
        CREATE POLICY smart_inbox_company_isolation ON smart_inbox_items
            USING (company_id = current_setting('app.current_company_id')::uuid);
    """)

    # User Behavior Logs RLS
    op.execute("ALTER TABLE user_behavior_logs ENABLE ROW LEVEL SECURITY;")

    op.execute("""
        CREATE POLICY behavior_logs_company_isolation ON user_behavior_logs
            USING (company_id = current_setting('app.current_company_id')::uuid);
    """)

    # ==========================================================================
    # 6. UPDATE STATISTICS
    # ==========================================================================

    op.execute("ANALYZE smart_inbox_items;")
    op.execute("ANALYZE user_behavior_logs;")


def downgrade() -> None:
    """Remove Smart Inbox tables and indexes."""

    # Drop RLS policies
    op.execute("DROP POLICY IF EXISTS behavior_logs_company_isolation ON user_behavior_logs;")
    op.execute("DROP POLICY IF EXISTS smart_inbox_company_isolation ON smart_inbox_items;")

    # Drop user_behavior_logs indexes
    op.drop_index("ix_behavior_logs_action", table_name="user_behavior_logs")
    op.drop_index("ix_behavior_logs_item", table_name="user_behavior_logs")
    op.drop_index("ix_behavior_logs_company_created", table_name="user_behavior_logs")
    op.drop_index("ix_behavior_logs_user_created", table_name="user_behavior_logs")

    # Drop smart_inbox_items indexes
    op.drop_index("ix_smart_inbox_source", table_name="smart_inbox_items")
    op.drop_index("ix_smart_inbox_deadline", table_name="smart_inbox_items")
    op.drop_index("ix_smart_inbox_snoozed", table_name="smart_inbox_items")
    op.drop_index("ix_smart_inbox_pending_priority", table_name="smart_inbox_items")
    op.drop_index("ix_smart_inbox_company_created", table_name="smart_inbox_items")
    op.drop_index("ix_smart_inbox_user_status", table_name="smart_inbox_items")

    # Drop tables (user_behavior_logs first due to FK)
    op.drop_table("user_behavior_logs")
    op.drop_table("smart_inbox_items")
