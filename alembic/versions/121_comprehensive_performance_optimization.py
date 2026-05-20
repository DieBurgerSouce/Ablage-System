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

import logging
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text

logger = logging.getLogger(__name__)


def _columns_exist(bind, table, columns):
    """Check if ALL columns exist on table. Returns False if any missing."""
    for col in columns:
        result = bind.execute(text(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_name = :table AND column_name = :col"
        ), {"table": table, "col": col})
        if not result.fetchone():
            logger.warning(f"Column {table}.{col} does not exist, skipping index")
            return False
    return True


def _table_exists(bind, table):
    """Check if table exists."""
    result = bind.execute(text(
        "SELECT 1 FROM information_schema.tables "
        "WHERE table_name = :table"
    ), {"table": table})
    return result.fetchone() is not None


def _index_exists(bind, index_name):
    """Check if index already exists."""
    result = bind.execute(text(
        "SELECT 1 FROM pg_indexes WHERE indexname = :name"
    ), {"name": index_name})
    return result.fetchone() is not None


# revision identifiers, used by Alembic.
revision = "121"
down_revision = "120_add_ai_conversations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add performance optimizations."""
    bind = op.get_bind()

    # ==========================================================================
    # 1. COMPOSITE INDEXES (with pre-checks for asyncpg compatibility)
    # ==========================================================================

    # Documents: Most common query patterns
    if _columns_exist(bind, "documents", ["company_id", "deleted_at", "created_at"]):
        if not _index_exists(bind, "ix_documents_company_deleted_created"):
            op.create_index(
                "ix_documents_company_deleted_created",
                "documents",
                ["company_id", "deleted_at", "created_at"],
                postgresql_where=sa.text("deleted_at IS NULL"),
            )

    if _columns_exist(bind, "documents", ["company_id", "status", "created_at"]):
        if not _index_exists(bind, "ix_documents_company_status_created"):
            op.create_index(
                "ix_documents_company_status_created",
                "documents",
                ["company_id", "status", "created_at"],
            )

    # folder_id may not exist on documents - skip if missing
    if _columns_exist(bind, "documents", ["company_id", "folder_id", "deleted_at"]):
        if not _index_exists(bind, "ix_documents_company_folder_deleted"):
            op.create_index(
                "ix_documents_company_folder_deleted",
                "documents",
                ["company_id", "folder_id", "deleted_at"],
                postgresql_where=sa.text("deleted_at IS NULL"),
            )

    # Approval Requests: Dashboard and list queries
    if _table_exists(bind, "approval_requests") and _columns_exist(bind, "approval_requests", ["company_id", "status", "due_date"]):
        if not _index_exists(bind, "ix_approval_requests_company_status_due"):
            op.create_index(
                "ix_approval_requests_company_status_due",
                "approval_requests",
                ["company_id", "status", "due_date"],
            )

    if _table_exists(bind, "approval_requests") and _columns_exist(bind, "approval_requests", ["approver_id", "status"]):
        if not _index_exists(bind, "ix_approval_requests_approver_pending"):
            op.create_index(
                "ix_approval_requests_approver_pending",
                "approval_requests",
                ["approver_id", "status"],
                postgresql_where=sa.text("status = 'pending'"),
            )

    # Alerts: Dashboard and auto-dismiss queries
    if _table_exists(bind, "alerts") and _columns_exist(bind, "alerts", ["auto_dismiss_at", "status"]):
        if not _index_exists(bind, "ix_alerts_auto_dismiss"):
            op.create_index(
                "ix_alerts_auto_dismiss",
                "alerts",
                ["auto_dismiss_at", "status"],
                postgresql_where=sa.text("auto_dismiss_at IS NOT NULL AND status = 'new'"),
            )

    if _table_exists(bind, "alerts") and _columns_exist(bind, "alerts", ["company_id", "status", "created_at"]):
        if not _index_exists(bind, "ix_alerts_company_status_created"):
            op.create_index(
                "ix_alerts_company_status_created",
                "alerts",
                ["company_id", "status", "created_at"],
            )

    if _table_exists(bind, "alerts") and _columns_exist(bind, "alerts", ["company_id", "severity", "status"]):
        if not _index_exists(bind, "ix_alerts_company_critical"):
            op.create_index(
                "ix_alerts_company_critical",
                "alerts",
                ["company_id", "severity", "status"],
                postgresql_where=sa.text("severity IN ('high', 'critical') AND status = 'new'"),
            )

    # Invoice Tracking: Payment and dunning queries
    if _table_exists(bind, "invoice_tracking") and _columns_exist(bind, "invoice_tracking", ["company_id", "status", "due_date"]):
        if not _index_exists(bind, "ix_invoice_tracking_company_status_due"):
            op.create_index(
                "ix_invoice_tracking_company_status_due",
                "invoice_tracking",
                ["company_id", "status", "due_date"],
            )

    if _table_exists(bind, "invoice_tracking") and _columns_exist(bind, "invoice_tracking", ["company_id", "dunning_level", "due_date"]):
        if not _index_exists(bind, "ix_invoice_tracking_dunning"):
            op.create_index(
                "ix_invoice_tracking_dunning",
                "invoice_tracking",
                ["company_id", "dunning_level", "due_date"],
                postgresql_where=sa.text("dunning_level > 0"),
            )

    if _table_exists(bind, "invoice_tracking") and _columns_exist(bind, "invoice_tracking", ["entity_id", "invoice_date"]):
        if not _index_exists(bind, "ix_invoice_tracking_entity_date"):
            op.create_index(
                "ix_invoice_tracking_entity_date",
                "invoice_tracking",
                ["entity_id", "invoice_date"],
            )

    # Business Entities: Search and lookup queries
    if _columns_exist(bind, "business_entities", ["company_id", "is_active", "name"]):
        if not _index_exists(bind, "ix_business_entities_company_active"):
            op.create_index(
                "ix_business_entities_company_active",
                "business_entities",
                ["company_id", "is_active", "name"],
                postgresql_where=sa.text("is_active = true"),
            )

    if _columns_exist(bind, "business_entities", ["company_id", "risk_score"]):
        if not _index_exists(bind, "ix_business_entities_high_risk"):
            op.create_index(
                "ix_business_entities_high_risk",
                "business_entities",
                ["company_id", "risk_score"],
                postgresql_where=sa.text("risk_score >= 75"),
            )

    # Document Chains: Chain queries
    if _table_exists(bind, "document_chains") and _columns_exist(bind, "document_chains", ["company_id", "status"]):
        if not _index_exists(bind, "ix_document_chains_company_active"):
            op.create_index(
                "ix_document_chains_company_active",
                "document_chains",
                ["company_id", "status"],
                postgresql_where=sa.text("status != 'completed'"),
            )

    # Import Logs: Recent imports and retries
    if _table_exists(bind, "import_logs") and _columns_exist(bind, "import_logs", ["company_id", "status", "retry_count"]):
        if not _index_exists(bind, "ix_import_logs_retry"):
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
    # 3. STATISTICS UPDATE (only for tables that exist)
    # ==========================================================================

    for tbl in ["documents", "approval_requests", "alerts", "invoice_tracking",
                "business_entities", "document_chains", "import_logs"]:
        if _table_exists(bind, tbl):
            op.execute(f"ANALYZE {tbl}")


def downgrade() -> None:
    """Remove performance optimizations."""
    bind = op.get_bind()

    # Drop RLS helper functions
    op.execute("DROP FUNCTION IF EXISTS get_current_user_id_fast()")
    op.execute("DROP FUNCTION IF EXISTS get_current_company_id_fast()")
    op.execute("DROP FUNCTION IF EXISTS is_rls_bypass_fast()")

    # Drop indexes (only if they exist - some may have been skipped during upgrade)
    indexes_to_drop = [
        ("ix_import_logs_retry", "import_logs"),
        ("ix_document_chains_company_active", "document_chains"),
        ("ix_business_entities_high_risk", "business_entities"),
        ("ix_business_entities_company_active", "business_entities"),
        ("ix_invoice_tracking_entity_date", "invoice_tracking"),
        ("ix_invoice_tracking_dunning", "invoice_tracking"),
        ("ix_invoice_tracking_company_status_due", "invoice_tracking"),
        ("ix_alerts_company_critical", "alerts"),
        ("ix_alerts_company_status_created", "alerts"),
        ("ix_alerts_auto_dismiss", "alerts"),
        ("ix_approval_requests_approver_pending", "approval_requests"),
        ("ix_approval_requests_company_status_due", "approval_requests"),
        ("ix_documents_company_folder_deleted", "documents"),
        ("ix_documents_company_status_created", "documents"),
        ("ix_documents_company_deleted_created", "documents"),
    ]
    for idx_name, tbl_name in indexes_to_drop:
        if _index_exists(bind, idx_name):
            op.drop_index(idx_name, table_name=tbl_name)
