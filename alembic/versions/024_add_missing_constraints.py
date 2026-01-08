"""Add missing database constraints for data integrity.

Revision ID: 024_add_missing_constraints
Revises: 023_add_performance_indexes
Create Date: 2024-12-02

SECURITY FIX: Fehlende Constraints hinzufuegen:
- UNIQUE auf api_keys.token_hash (verhindert doppelte API-Keys)
- CHECK auf processing_jobs.priority (0-9 Bereich validieren)
- CHECK auf documents.ocr_confidence (0-1 Bereich validieren)
- CHECK auf batch_jobs.priority (0-10 Bereich validieren)

WICHTIG: Bei bestehenden Daten sollten doppelte token_hash Werte
vor der Migration bereinigt werden!

HINWEIS: Diese Migration prueft Tabellen- und Spalten-Existenz vor Constraint-Erstellung.
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "024"
down_revision = "023b"
branch_labels = None
depends_on = None


def table_exists(conn, table_name: str) -> bool:
    """Prüft ob eine Tabelle existiert."""
    result = conn.execute(sa.text("""
        SELECT EXISTS (
            SELECT FROM information_schema.tables
            WHERE table_name = :table_name
        )
    """), {"table_name": table_name})
    return result.scalar()


def column_exists(conn, table_name: str, column_name: str) -> bool:
    """Prüft ob eine Spalte in einer Tabelle existiert."""
    result = conn.execute(sa.text("""
        SELECT EXISTS (
            SELECT FROM information_schema.columns
            WHERE table_name = :table_name AND column_name = :column_name
        )
    """), {"table_name": table_name, "column_name": column_name})
    return result.scalar()


def constraint_exists(conn, constraint_name: str) -> bool:
    """Prüft ob ein Constraint existiert."""
    result = conn.execute(sa.text("""
        SELECT EXISTS (
            SELECT FROM information_schema.table_constraints
            WHERE constraint_name = :constraint_name
        )
    """), {"constraint_name": constraint_name})
    return result.scalar()


def upgrade() -> None:
    """Add missing constraints for data integrity."""
    conn = op.get_bind()

    # =========================================================================
    # API_KEYS TABLE CONSTRAINTS
    # =========================================================================
    if table_exists(conn, "api_keys") and column_exists(conn, "api_keys", "token_hash"):
        if not constraint_exists(conn, "uq_api_keys_token_hash"):
            op.execute("""
                ALTER TABLE api_keys
                ADD CONSTRAINT uq_api_keys_token_hash UNIQUE (token_hash)
            """)

    # =========================================================================
    # PROCESSING_JOBS TABLE CONSTRAINTS
    # =========================================================================
    if table_exists(conn, "processing_jobs") and column_exists(conn, "processing_jobs", "priority"):
        if not constraint_exists(conn, "check_processing_jobs_priority"):
            op.execute("""
                ALTER TABLE processing_jobs
                ADD CONSTRAINT check_processing_jobs_priority
                CHECK (priority >= 0 AND priority <= 9)
            """)

    # =========================================================================
    # DOCUMENTS TABLE CONSTRAINTS
    # =========================================================================
    if table_exists(conn, "documents") and column_exists(conn, "documents", "ocr_confidence"):
        if not constraint_exists(conn, "check_documents_ocr_confidence"):
            op.execute("""
                ALTER TABLE documents
                ADD CONSTRAINT check_documents_ocr_confidence
                CHECK (ocr_confidence IS NULL OR (ocr_confidence >= 0 AND ocr_confidence <= 1.0))
            """)

    # =========================================================================
    # BATCH_JOBS TABLE CONSTRAINTS
    # =========================================================================
    if table_exists(conn, "batch_jobs") and column_exists(conn, "batch_jobs", "priority"):
        if not constraint_exists(conn, "check_batch_jobs_priority"):
            op.execute("""
                ALTER TABLE batch_jobs
                ADD CONSTRAINT check_batch_jobs_priority
                CHECK (priority >= 0 AND priority <= 10)
            """)


def downgrade() -> None:
    """Remove constraints."""

    # Batch Jobs
    op.execute("ALTER TABLE batch_jobs DROP CONSTRAINT IF EXISTS check_batch_jobs_priority")

    # Documents
    op.execute("ALTER TABLE documents DROP CONSTRAINT IF EXISTS check_documents_ocr_confidence")

    # Processing Jobs
    op.execute("ALTER TABLE processing_jobs DROP CONSTRAINT IF EXISTS check_processing_jobs_priority")

    # API Keys
    op.execute("ALTER TABLE api_keys DROP CONSTRAINT IF EXISTS uq_api_keys_token_hash")
