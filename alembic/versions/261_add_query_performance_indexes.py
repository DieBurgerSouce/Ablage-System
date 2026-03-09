"""Add composite and FK indexes for common query patterns.

Addresses schema review findings H3/M4:
- Composite indexes for multi-column queries (company+date, user+action)
- FK indexes on columns that lack them
- Partial indexes for status-filtered queries

NOTE: Uses IF NOT EXISTS and table checks for idempotency.
Does not use CONCURRENTLY (requires autocommit mode not configured in env.py).

Revision ID: 261
Revises: 260
Create Date: 2026-03-09
"""
from alembic import op
from sqlalchemy import text

revision = "261"
down_revision = "260"
branch_labels = None
depends_on = None


def _table_exists(conn, table_name: str) -> bool:
    result = conn.execute(
        text("SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = :t"),
        {"t": table_name},
    ).fetchone()
    return result is not None


def _index_exists(conn, index_name: str) -> bool:
    result = conn.execute(
        text("SELECT 1 FROM pg_indexes WHERE indexname = :n"),
        {"n": index_name},
    ).fetchone()
    return result is not None


def _column_exists(conn, table_name: str, column_name: str) -> bool:
    result = conn.execute(
        text(
            "SELECT 1 FROM information_schema.columns WHERE table_name = :t AND column_name = :c"
        ),
        {"t": table_name, "c": column_name},
    ).fetchone()
    return result is not None


def upgrade() -> None:
    conn = op.get_bind()

    # === Composite indexes for common query patterns ===

    # Documents: company + created_at (tenant-scoped listing)
    if (_table_exists(conn, "documents")
            and _column_exists(conn, "documents", "company_id")
            and not _index_exists(conn, "ix_documents_company_created")):
        op.execute(
            """CREATE INDEX ix_documents_company_created
               ON documents (company_id, created_at DESC)"""
        )

    # Audit logs: time-range + action type (compliance queries)
    if (_table_exists(conn, "audit_logs")
            and not _index_exists(conn, "ix_audit_logs_created_action")):
        op.execute(
            """CREATE INDEX ix_audit_logs_created_action
               ON audit_logs (created_at, action)"""
        )

    # Audit logs: user + action (user activity reports)
    if (_table_exists(conn, "audit_logs")
            and not _index_exists(conn, "ix_audit_logs_user_action")):
        op.execute(
            """CREATE INDEX ix_audit_logs_user_action
               ON audit_logs (user_id, action)"""
        )

    # Bank transactions: company + date (reconciliation queries)
    if (_table_exists(conn, "bank_transactions")
            and _column_exists(conn, "bank_transactions", "company_id")
            and not _index_exists(conn, "ix_bank_transactions_company_date")):
        op.execute(
            """CREATE INDEX ix_bank_transactions_company_date
               ON bank_transactions (company_id, transaction_date DESC)"""
        )

    # === Partial indexes for status-filtered queries ===

    # Processing jobs: only pending/processing (queue polling)
    if (_table_exists(conn, "processing_jobs")
            and not _index_exists(conn, "ix_processing_jobs_pending")):
        op.execute(
            """CREATE INDEX ix_processing_jobs_pending
               ON processing_jobs (document_id, created_at)
               WHERE status IN ('pending', 'queued', 'processing')"""
        )

    # Invoices: only unpaid (dashboard KPIs, overdue checks)
    if (_table_exists(conn, "invoices")
            and not _index_exists(conn, "ix_invoices_unpaid")):
        op.execute(
            """CREATE INDEX ix_invoices_unpaid
               ON invoices (due_date, total_amount)
               WHERE payment_status NOT IN ('paid', 'cancelled')"""
        )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_invoices_unpaid")
    op.execute("DROP INDEX IF EXISTS ix_processing_jobs_pending")
    op.execute("DROP INDEX IF EXISTS ix_bank_transactions_company_date")
    op.execute("DROP INDEX IF EXISTS ix_audit_logs_user_action")
    op.execute("DROP INDEX IF EXISTS ix_audit_logs_created_action")
    op.execute("DROP INDEX IF EXISTS ix_documents_company_created")
