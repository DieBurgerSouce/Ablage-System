"""Add missing partial indexes and GIN indexes for performance.

- Partial indexes for soft-deleted tables (active-only queries skip deleted rows)
- GIN indexes on high-traffic JSONB columns (document_metadata, custom_field_values)

NOTE: All operations are idempotent - safe to re-run.

Revision ID: 258
Revises: 257
Create Date: 2026-03-09
"""
from alembic import op
from sqlalchemy import text

revision = "258"
down_revision = "257"
branch_labels = None
depends_on = None


def _index_exists(conn, index_name: str) -> bool:
    result = conn.execute(
        text("SELECT 1 FROM pg_indexes WHERE indexname = :n"),
        {"n": index_name},
    ).fetchone()
    return result is not None


def _table_exists(conn, table_name: str) -> bool:
    result = conn.execute(
        text("SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = :t"),
        {"t": table_name},
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

    # === Partial indexes for soft-deleted tables (active records only) ===

    if (_table_exists(conn, "documents")
            and _column_exists(conn, "documents", "deleted_at")
            and not _index_exists(conn, "ix_documents_active")):
        op.execute(
            """CREATE INDEX ix_documents_active
               ON documents (owner_id, created_at DESC)
               WHERE deleted_at IS NULL"""
        )

    if (_table_exists(conn, "bank_accounts")
            and _column_exists(conn, "bank_accounts", "deleted_at")
            and _column_exists(conn, "bank_accounts", "company_id")
            and not _index_exists(conn, "ix_bank_accounts_active")):
        op.execute(
            """CREATE INDEX ix_bank_accounts_active
               ON bank_accounts (company_id, iban)
               WHERE deleted_at IS NULL"""
        )

    if (_table_exists(conn, "saved_filters")
            and _column_exists(conn, "saved_filters", "deleted_at")
            and not _index_exists(conn, "ix_saved_filters_active")):
        op.execute(
            """CREATE INDEX ix_saved_filters_active
               ON saved_filters (user_id, feature)
               WHERE deleted_at IS NULL"""
        )

    # === GIN indexes on high-traffic JSONB columns ===

    if (_table_exists(conn, "documents")
            and _column_exists(conn, "documents", "document_metadata")
            and not _index_exists(conn, "ix_documents_metadata_gin")):
        op.execute(
            """CREATE INDEX ix_documents_metadata_gin
               ON documents USING GIN (document_metadata jsonb_path_ops)
               WHERE document_metadata IS NOT NULL"""
        )

    if (_table_exists(conn, "documents")
            and _column_exists(conn, "documents", "custom_field_values")
            and not _index_exists(conn, "ix_documents_custom_fields_gin")):
        op.execute(
            """CREATE INDEX ix_documents_custom_fields_gin
               ON documents USING GIN (custom_field_values jsonb_path_ops)
               WHERE custom_field_values IS NOT NULL"""
        )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_documents_custom_fields_gin")
    op.execute("DROP INDEX IF EXISTS ix_documents_metadata_gin")
    op.execute("DROP INDEX IF EXISTS ix_saved_filters_active")
    op.execute("DROP INDEX IF EXISTS ix_bank_accounts_active")
    op.execute("DROP INDEX IF EXISTS ix_documents_active")
