# -*- coding: utf-8 -*-
"""Comprehensive performance optimization migration.

Revision ID: 121
Revises: 120
Create Date: 2026-01-26

This migration adds:
1. Composite indexes for frequently queried columns
2. Optimized RLS helper functions (avoid text casts)
3. Partial indexes for common filter patterns
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "121"
down_revision = "120_add_ai_conversations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add performance optimizations."""

    # ==========================================================================
    # 1. COMPOSITE INDEXES
    # ==========================================================================

    # Documents: Most common query patterns
    # Query: WHERE company_id = ? AND deleted_at IS NULL ORDER BY created_at DESC
    op.create_index(
        "ix_documents_company_deleted_created",
        "documents",
        ["company_id", "deleted_at", "created_at"],
        postgresql_where=sa.text("deleted_at IS NULL"),
    )

    # Query: WHERE company_id = ? AND status = ? ORDER BY created_at DESC
    op.create_index(
        "ix_documents_company_status_created",
        "documents",
        ["company_id", "status", "created_at"],
    )

    # Query: WHERE company_id = ? AND folder_id = ? AND deleted_at IS NULL
    op.create_index(
        "ix_documents_company_folder_deleted",
        "documents",
        ["company_id", "folder_id", "deleted_at"],
        postgresql_where=sa.text("deleted_at IS NULL"),
    )

    # Approval Requests: Dashboard and list queries
    # Query: WHERE company_id = ? AND status = ? ORDER BY due_date ASC
    op.create_index(
        "ix_approval_requests_company_status_due",
        "approval_requests",
        ["company_id", "status", "due_date"],
    )

    # Query: WHERE approver_id = ? AND status = 'pending'
    op.create_index(
        "ix_approval_requests_approver_pending",
        "approval_requests",
        ["approver_id", "status"],
        postgresql_where=sa.text("status = 'pending'"),
    )

    # Alerts: Dashboard and auto-dismiss queries
    # Query: WHERE auto_dismiss_at < NOW() AND status = 'new'
    op.create_index(
        "ix_alerts_auto_dismiss",
        "alerts",
        ["auto_dismiss_at", "status"],
        postgresql_where=sa.text("auto_dismiss_at IS NOT NULL AND status = 'new'"),
    )

    # Query: WHERE company_id = ? AND status = 'new' ORDER BY created_at DESC
    op.create_index(
        "ix_alerts_company_status_created",
        "alerts",
        ["company_id", "status", "created_at"],
    )

    # Query: WHERE company_id = ? AND severity IN ('high', 'critical') AND status = 'new'
    op.create_index(
        "ix_alerts_company_critical",
        "alerts",
        ["company_id", "severity", "status"],
        postgresql_where=sa.text("severity IN ('high', 'critical') AND status = 'new'"),
    )

    # Invoice Tracking: Payment and dunning queries
    # Query: WHERE company_id = ? AND status = ? ORDER BY due_date ASC
    op.create_index(
        "ix_invoice_tracking_company_status_due",
        "invoice_tracking",
        ["company_id", "status", "due_date"],
    )

    # Query: WHERE company_id = ? AND dunning_level > 0 ORDER BY due_date
    op.create_index(
        "ix_invoice_tracking_dunning",
        "invoice_tracking",
        ["company_id", "dunning_level", "due_date"],
        postgresql_where=sa.text("dunning_level > 0"),
    )

    # Query: WHERE entity_id = ? ORDER BY invoice_date DESC
    op.create_index(
        "ix_invoice_tracking_entity_date",
        "invoice_tracking",
        ["entity_id", "invoice_date"],
    )

    # Business Entities: Search and lookup queries
    # Query: WHERE company_id = ? AND is_active = true ORDER BY name
    op.create_index(
        "ix_business_entities_company_active",
        "business_entities",
        ["company_id", "is_active", "name"],
        postgresql_where=sa.text("is_active = true"),
    )

    # Query: WHERE company_id = ? AND risk_score >= 75
    op.create_index(
        "ix_business_entities_high_risk",
        "business_entities",
        ["company_id", "risk_score"],
        postgresql_where=sa.text("risk_score >= 75"),
    )

    # Document Chains: Chain queries
    # Query: WHERE company_id = ? AND status != 'completed'
    op.create_index(
        "ix_document_chains_company_active",
        "document_chains",
        ["company_id", "status"],
        postgresql_where=sa.text("status != 'completed'"),
    )

    # Import Logs: Recent imports and retries
    # Query: WHERE company_id = ? AND status = 'failed' AND retry_count < 3
    op.create_index(
        "ix_import_logs_retry",
        "import_logs",
        ["company_id", "status", "retry_count"],
        postgresql_where=sa.text("status = 'failed' AND retry_count < 3"),
    )

    # ==========================================================================
    # 2. RLS HELPER FUNCTIONS (Optimized - no text casts)
    # ==========================================================================

    # Create optimized RLS helper functions that return UUID directly
    op.execute("""
        CREATE OR REPLACE FUNCTION get_current_user_id_fast()
        RETURNS uuid
        LANGUAGE sql
        STABLE
        PARALLEL SAFE
        AS $$
            SELECT NULLIF(current_setting('app.current_user_id', true), '')::uuid
        $$;
    """)

    op.execute("""
        CREATE OR REPLACE FUNCTION get_current_company_id_fast()
        RETURNS uuid
        LANGUAGE sql
        STABLE
        PARALLEL SAFE
        AS $$
            SELECT NULLIF(current_setting('app.current_company_id', true), '')::uuid
        $$;
    """)

    op.execute("""
        CREATE OR REPLACE FUNCTION is_rls_bypass_fast()
        RETURNS boolean
        LANGUAGE sql
        STABLE
        PARALLEL SAFE
        AS $$
            SELECT COALESCE(current_setting('app.bypass_rls', true), 'false')::boolean
        $$;
    """)

    # ==========================================================================
    # 3. STATISTICS UPDATE
    # ==========================================================================

    # Update statistics for query planner optimization
    op.execute("ANALYZE documents;")
    op.execute("ANALYZE approval_requests;")
    op.execute("ANALYZE alerts;")
    op.execute("ANALYZE invoice_tracking;")
    op.execute("ANALYZE business_entities;")
    op.execute("ANALYZE document_chains;")
    op.execute("ANALYZE import_logs;")


def downgrade() -> None:
    """Remove performance optimizations."""

    # Drop RLS helper functions
    op.execute("DROP FUNCTION IF EXISTS get_current_user_id_fast();")
    op.execute("DROP FUNCTION IF EXISTS get_current_company_id_fast();")
    op.execute("DROP FUNCTION IF EXISTS is_rls_bypass_fast();")

    # Drop indexes (in reverse order)
    op.drop_index("ix_import_logs_retry", table_name="import_logs")
    op.drop_index("ix_document_chains_company_active", table_name="document_chains")
    op.drop_index("ix_business_entities_high_risk", table_name="business_entities")
    op.drop_index("ix_business_entities_company_active", table_name="business_entities")
    op.drop_index("ix_invoice_tracking_entity_date", table_name="invoice_tracking")
    op.drop_index("ix_invoice_tracking_dunning", table_name="invoice_tracking")
    op.drop_index("ix_invoice_tracking_company_status_due", table_name="invoice_tracking")
    op.drop_index("ix_alerts_company_critical", table_name="alerts")
    op.drop_index("ix_alerts_company_status_created", table_name="alerts")
    op.drop_index("ix_alerts_auto_dismiss", table_name="alerts")
    op.drop_index("ix_approval_requests_approver_pending", table_name="approval_requests")
    op.drop_index("ix_approval_requests_company_status_due", table_name="approval_requests")
    op.drop_index("ix_documents_company_folder_deleted", table_name="documents")
    op.drop_index("ix_documents_company_status_created", table_name="documents")
    op.drop_index("ix_documents_company_deleted_created", table_name="documents")
