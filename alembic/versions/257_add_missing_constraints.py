"""Add missing CHECK constraints for data integrity.

- Chain integrity: chain_position requires chain_root_document_id and vice versa
- BatchJob progress must be 0-100
- ProcessingJob priority must be 1-10
- EInvoice: was_generated and was_extracted are mutually exclusive
- CompanySettings: enforce singleton (max 1 row)
- document_tags: unique constraint to prevent duplicate tag assignments

Revision ID: 257
Revises: 256
Create Date: 2026-03-09
"""
from alembic import op
from sqlalchemy import text

revision = "257"
down_revision = "256"
branch_labels = None
depends_on = None


def _table_exists(conn, table_name: str) -> bool:
    """Check if a table exists in the public schema."""
    result = conn.execute(
        text("SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = :t"),
        {"t": table_name},
    ).fetchone()
    return result is not None


def _constraint_exists(conn, constraint_name: str) -> bool:
    """Check if a constraint or index with this name exists."""
    result = conn.execute(
        text(
            """SELECT 1 FROM pg_constraint WHERE conname = :n
               UNION ALL
               SELECT 1 FROM pg_indexes WHERE indexname = :n"""
        ),
        {"n": constraint_name},
    ).fetchone()
    return result is not None


def upgrade() -> None:
    conn = op.get_bind()

    # Chain integrity: chain_position and chain_root_document_id must both be set or both NULL
    if _table_exists(conn, "documents") and not _constraint_exists(conn, "ck_documents_chain_integrity"):
        op.execute(
            """ALTER TABLE documents ADD CONSTRAINT ck_documents_chain_integrity
               CHECK ((chain_root_document_id IS NULL) = (chain_position IS NULL))"""
        )

    # BatchJob progress must be 0-100
    if _table_exists(conn, "batch_jobs") and not _constraint_exists(conn, "ck_batch_jobs_progress"):
        op.execute(
            """ALTER TABLE batch_jobs ADD CONSTRAINT ck_batch_jobs_progress
               CHECK (progress >= 0 AND progress <= 100)"""
        )

    # ProcessingJob priority must be 1-10
    if _table_exists(conn, "processing_jobs") and not _constraint_exists(conn, "ck_processing_jobs_priority"):
        op.execute(
            """ALTER TABLE processing_jobs ADD CONSTRAINT ck_processing_jobs_priority
               CHECK (priority >= 1 AND priority <= 10)"""
        )

    # EInvoice: was_generated and was_extracted are mutually exclusive
    if _table_exists(conn, "einvoice_documents") and not _constraint_exists(conn, "ck_einvoice_source_exclusive"):
        op.execute(
            """ALTER TABLE einvoice_documents ADD CONSTRAINT ck_einvoice_source_exclusive
               CHECK (NOT (was_generated = true AND was_extracted = true))"""
        )

    # CompanySettings: enforce singleton (max 1 row via unique on a constant expression)
    if _table_exists(conn, "company_settings") and not _constraint_exists(conn, "ix_company_settings_singleton"):
        op.execute(
            """CREATE UNIQUE INDEX ix_company_settings_singleton
               ON company_settings ((true))"""
        )

    # document_tags: prevent duplicate tag assignments
    if _table_exists(conn, "document_tags") and not _constraint_exists(conn, "ix_document_tags_unique"):
        op.execute(
            """CREATE UNIQUE INDEX ix_document_tags_unique
               ON document_tags (document_id, tag_id)"""
        )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_document_tags_unique")
    op.execute("DROP INDEX IF EXISTS ix_company_settings_singleton")
    op.execute("ALTER TABLE einvoice_documents DROP CONSTRAINT IF EXISTS ck_einvoice_source_exclusive")
    op.execute("ALTER TABLE processing_jobs DROP CONSTRAINT IF EXISTS ck_processing_jobs_priority")
    op.execute("ALTER TABLE batch_jobs DROP CONSTRAINT IF EXISTS ck_batch_jobs_progress")
    op.execute("ALTER TABLE documents DROP CONSTRAINT IF EXISTS ck_documents_chain_integrity")
