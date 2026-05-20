# -*- coding: utf-8 -*-
"""Natural Language Query 2.0 - Query logging.

Revision ID: 123
Revises: 122
Create Date: 2026-01-28

This migration adds:
1. nlq_query_logs table for Natural Language Query logging
2. Indexes for performance optimization
3. RLS policy for multi-tenant isolation
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "123"
down_revision = "122"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add NLQ query logging table and indexes."""

    # ==========================================================================
    # 1. CREATE NLQ_QUERY_LOGS TABLE
    # ==========================================================================

    op.create_table(
        "nlq_query_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("natural_query", sa.Text, nullable=False),
        sa.Column("generated_sql", sa.Text, nullable=True),
        sa.Column("sanitized_sql", sa.Text, nullable=True),
        sa.Column("query_intent", sa.String(100), nullable=True),
        sa.Column("execution_time_ms", sa.Integer, server_default=sa.text("0"), nullable=False),
        sa.Column("result_count", sa.Integer, server_default=sa.text("0"), nullable=False),
        sa.Column("was_cached", sa.Boolean, server_default=sa.text("false"), nullable=False),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("visualization_type", sa.String(50), nullable=True),
        sa.Column("visualization_config", postgresql.JSONB, server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("feedback_rating", sa.Integer, nullable=True),
        sa.Column("feedback_comment", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_nlq_query_user", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], name="fk_nlq_query_company", ondelete="CASCADE"),
    )

    # ==========================================================================
    # 2. CREATE INDEXES
    # ==========================================================================

    # Composite index for company queries with created_at ordering
    op.create_index(
        "ix_nlq_queries_company_created",
        "nlq_query_logs",
        ["company_id", "created_at"],
    )

    # Composite index for user queries with created_at ordering
    op.create_index(
        "ix_nlq_queries_user_created",
        "nlq_query_logs",
        ["user_id", "created_at"],
    )

    # Index for intent-based filtering
    op.create_index(
        "ix_nlq_queries_intent",
        "nlq_query_logs",
        ["query_intent"],
    )

    # Index for feedback analysis
    op.create_index(
        "ix_nlq_queries_feedback",
        "nlq_query_logs",
        ["feedback_rating"],
        postgresql_where=sa.text("feedback_rating IS NOT NULL"),
    )

    # ==========================================================================
    # 3. ENABLE ROW LEVEL SECURITY
    # ==========================================================================

    op.execute("ALTER TABLE nlq_query_logs ENABLE ROW LEVEL SECURITY;")

    # Create RLS policy for multi-tenant isolation
    op.execute("""
        CREATE POLICY nlq_query_logs_company_isolation ON nlq_query_logs
            USING (company_id = current_setting('app.current_company_id')::uuid);
    """)

    # ==========================================================================
    # 4. UPDATE STATISTICS
    # ==========================================================================

    op.execute("ANALYZE nlq_query_logs;")


def downgrade() -> None:
    """Remove NLQ query logging table and indexes."""

    # Drop RLS policy
    op.execute("DROP POLICY IF EXISTS nlq_query_logs_company_isolation ON nlq_query_logs;")

    # Drop indexes
    op.drop_index("ix_nlq_queries_feedback", table_name="nlq_query_logs")
    op.drop_index("ix_nlq_queries_intent", table_name="nlq_query_logs")
    op.drop_index("ix_nlq_queries_user_created", table_name="nlq_query_logs")
    op.drop_index("ix_nlq_queries_company_created", table_name="nlq_query_logs")

    # Drop table
    op.drop_table("nlq_query_logs")
