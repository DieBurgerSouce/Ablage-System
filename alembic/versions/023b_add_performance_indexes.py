"""Add missing performance indexes for common query patterns.

Revision ID: 023_add_performance_indexes
Revises: 022_add_document_access
Create Date: 2024-12-01

Performance-kritische Indexes für:
- Dashboard-Queries (Status, Document-Type)
- User-aktive-Dokumente-Filter (Owner + Deleted)
- Backend-Statistiken (OCR-Backend + Status)
- Job-Queue-Priorisierung
- GDPR-Deadline-Checks
- User-Tier-Management
- API-Key-Lookups
- Full-Text-Search GIN Index

WICHTIG: Bei großen Tabellen in Production sollten diese Indexes
während Off-Peak-Hours mit CONCURRENTLY erstellt werden.

HINWEIS: Diese Migration prüft Tabellen- und Spalten-Existenz vor Index-Erstellung.
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "023b"
down_revision = "023"
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


def upgrade() -> None:
    """Add performance indexes for common query patterns."""
    conn = op.get_bind()

    # =========================================================================
    # DOCUMENTS TABLE INDEXES
    # =========================================================================
    if table_exists(conn, "documents"):
        # 1. OCR Backend + Status (Backend-Statistiken)
        if column_exists(conn, "documents", "ocr_backend_used") and column_exists(conn, "documents", "status"):
            op.execute("""
                CREATE INDEX IF NOT EXISTS ix_documents_backend_status
                ON documents (ocr_backend_used, status)
            """)

        # 2. Updated_at (Kürzlich geänderte Dokumente)
        if column_exists(conn, "documents", "updated_at"):
            op.execute("""
                CREATE INDEX IF NOT EXISTS ix_documents_updated_at
                ON documents (updated_at)
            """)

        # 3. Document Type + Status (Dashboard-Filter)
        if column_exists(conn, "documents", "document_type") and column_exists(conn, "documents", "status"):
            op.execute("""
                CREATE INDEX IF NOT EXISTS ix_documents_type_status
                ON documents (document_type, status)
            """)

        # 4. Partial Index für Dokumente mit Embeddings
        if column_exists(conn, "documents", "embedding"):
            op.execute("""
                CREATE INDEX IF NOT EXISTS ix_documents_with_embedding
                ON documents (owner_id)
                WHERE embedding IS NOT NULL
            """)

        # 5. GIN Index für Full-Text-Search
        if column_exists(conn, "documents", "search_vector"):
            op.execute("""
                CREATE INDEX IF NOT EXISTS ix_documents_search_vector_gin
                ON documents USING gin (search_vector)
            """)

    # =========================================================================
    # PROCESSING_JOBS TABLE INDEXES
    # =========================================================================
    if table_exists(conn, "processing_jobs"):
        if column_exists(conn, "processing_jobs", "status") and \
           column_exists(conn, "processing_jobs", "priority") and \
           column_exists(conn, "processing_jobs", "created_at"):
            op.execute("""
                CREATE INDEX IF NOT EXISTS ix_processing_jobs_queue
                ON processing_jobs (status, priority DESC, created_at)
            """)

    # =========================================================================
    # OCR_RESULTS TABLE INDEXES
    # =========================================================================
    if table_exists(conn, "ocr_results"):
        if column_exists(conn, "ocr_results", "document_id") and \
           column_exists(conn, "ocr_results", "created_at"):
            op.execute("""
                CREATE INDEX IF NOT EXISTS ix_ocr_results_history
                ON ocr_results (document_id, created_at DESC)
            """)

    # =========================================================================
    # USERS TABLE INDEXES
    # =========================================================================
    if table_exists(conn, "users"):
        # 8. GDPR Deletion Deadline (User + Scheduled Deletion)
        if column_exists(conn, "users", "deletion_scheduled_for"):
            op.execute("""
                CREATE INDEX IF NOT EXISTS ix_users_deletion_deadline
                ON users (id, deletion_scheduled_for)
            """)

        # 9. User Tier + Created (Tier-Management)
        if column_exists(conn, "users", "tier") and column_exists(conn, "users", "created_at"):
            op.execute("""
                CREATE INDEX IF NOT EXISTS ix_users_tier_created
                ON users (tier, created_at DESC)
            """)

        # 10. Active Users (is_active + last_activity)
        if column_exists(conn, "users", "is_active") and column_exists(conn, "users", "last_activity_at"):
            op.execute("""
                CREATE INDEX IF NOT EXISTS ix_users_active
                ON users (is_active, last_activity_at DESC)
            """)

    # =========================================================================
    # API_KEYS TABLE INDEXES
    # =========================================================================
    if table_exists(conn, "api_keys"):
        if column_exists(conn, "api_keys", "user_id") and column_exists(conn, "api_keys", "is_active"):
            op.execute("""
                CREATE INDEX IF NOT EXISTS ix_api_keys_user_active
                ON api_keys (user_id, is_active)
            """)

    # =========================================================================
    # BATCH_JOBS TABLE INDEXES
    # =========================================================================
    if table_exists(conn, "batch_jobs"):
        if column_exists(conn, "batch_jobs", "status") and \
           column_exists(conn, "batch_jobs", "priority") and \
           column_exists(conn, "batch_jobs", "created_at"):
            op.execute("""
                CREATE INDEX IF NOT EXISTS ix_batch_jobs_queue
                ON batch_jobs (status, priority DESC, created_at)
            """)

    # =========================================================================
    # DATA_EXPORTS TABLE INDEXES
    # =========================================================================
    if table_exists(conn, "data_exports"):
        if column_exists(conn, "data_exports", "user_id") and column_exists(conn, "data_exports", "created_at"):
            op.execute("""
                CREATE INDEX IF NOT EXISTS ix_data_exports_deadline
                ON data_exports (user_id, created_at)
            """)

    # =========================================================================
    # GDPR_DELETION_REQUESTS TABLE INDEXES
    # =========================================================================
    if table_exists(conn, "gdpr_deletion_requests"):
        if column_exists(conn, "gdpr_deletion_requests", "user_id") and \
           column_exists(conn, "gdpr_deletion_requests", "deletion_scheduled_for"):
            op.execute("""
                CREATE INDEX IF NOT EXISTS ix_gdpr_deletion_requests_deadline
                ON gdpr_deletion_requests (user_id, deletion_scheduled_for)
            """)


def downgrade() -> None:
    """Remove performance indexes."""

    # GDPR tables
    op.execute("DROP INDEX IF EXISTS ix_gdpr_deletion_requests_deadline")
    op.execute("DROP INDEX IF EXISTS ix_data_exports_deadline")

    # Batch Jobs
    op.execute("DROP INDEX IF EXISTS ix_batch_jobs_queue")

    # API Keys
    op.execute("DROP INDEX IF EXISTS ix_api_keys_user_active")

    # Users
    op.execute("DROP INDEX IF EXISTS ix_users_active")
    op.execute("DROP INDEX IF EXISTS ix_users_tier_created")
    op.execute("DROP INDEX IF EXISTS ix_users_deletion_deadline")

    # OCR Results
    op.execute("DROP INDEX IF EXISTS ix_ocr_results_history")

    # Processing Jobs
    op.execute("DROP INDEX IF EXISTS ix_processing_jobs_queue")

    # Documents
    op.execute("DROP INDEX IF EXISTS ix_documents_search_vector_gin")
    op.execute("DROP INDEX IF EXISTS ix_documents_with_embedding")
    op.execute("DROP INDEX IF EXISTS ix_documents_type_status")
    op.execute("DROP INDEX IF EXISTS ix_documents_updated_at")
    op.execute("DROP INDEX IF EXISTS ix_documents_backend_status")
