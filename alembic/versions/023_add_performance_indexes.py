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
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "023_add_performance_indexes"
down_revision = "022_add_document_access"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add performance indexes for common query patterns."""

    # =========================================================================
    # DOCUMENTS TABLE INDEXES
    # =========================================================================

    # 1. OCR Backend + Status (Backend-Statistiken)
    op.create_index(
        "ix_documents_backend_status",
        "documents",
        ["ocr_backend_used", "status"],
        if_not_exists=True
    )

    # 2. Updated_at (Kürzlich geänderte Dokumente)
    op.create_index(
        "ix_documents_updated_at",
        "documents",
        ["updated_at"],
        if_not_exists=True
    )

    # 3. Document Type + Status (Dashboard-Filter)
    op.create_index(
        "ix_documents_type_status",
        "documents",
        ["document_type", "status"],
        if_not_exists=True
    )

    # 4. Partial Index für Dokumente mit Embeddings
    # Nur Dokumente mit embedding != NULL werden indexiert
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_documents_with_embedding
        ON documents (owner_id)
        WHERE embedding IS NOT NULL
    """)

    # 5. GIN Index für Full-Text-Search
    # Verwendung des german_text Configs für deutsche Dokumente
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_documents_search_vector_gin
        ON documents USING gin (search_vector)
    """)

    # =========================================================================
    # PROCESSING_JOBS TABLE INDEXES
    # =========================================================================

    # 6. Job-Queue-Priorisierung (Status + Priority DESC + Created)
    op.create_index(
        "ix_processing_jobs_queue",
        "processing_jobs",
        ["status", sa.text("priority DESC"), "created_at"],
        if_not_exists=True
    )

    # =========================================================================
    # OCR_RESULTS TABLE INDEXES
    # =========================================================================

    # 7. OCR-History (Document + Created DESC)
    op.create_index(
        "ix_ocr_results_history",
        "ocr_results",
        ["document_id", sa.text("created_at DESC")],
        if_not_exists=True
    )

    # =========================================================================
    # USERS TABLE INDEXES
    # =========================================================================

    # 8. GDPR Deletion Deadline (User + Scheduled Deletion)
    op.create_index(
        "ix_users_deletion_deadline",
        "users",
        ["id", "deletion_scheduled_for"],
        if_not_exists=True
    )

    # 9. User Tier + Created (Tier-Management)
    op.create_index(
        "ix_users_tier_created",
        "users",
        ["tier", sa.text("created_at DESC")],
        if_not_exists=True
    )

    # 10. Active Users (is_active + last_activity)
    op.create_index(
        "ix_users_active",
        "users",
        ["is_active", sa.text("last_activity_at DESC")],
        if_not_exists=True
    )

    # =========================================================================
    # API_KEYS TABLE INDEXES
    # =========================================================================

    # 11. API-Key Lookups (User + is_active)
    op.create_index(
        "ix_api_keys_user_active",
        "api_keys",
        ["user_id", "is_active"],
        if_not_exists=True
    )

    # =========================================================================
    # BATCH_JOBS TABLE INDEXES
    # =========================================================================

    # 12. Batch-Job Queue (Status + Priority + Created)
    op.create_index(
        "ix_batch_jobs_queue",
        "batch_jobs",
        ["status", sa.text("priority DESC"), "created_at"],
        if_not_exists=True
    )

    # =========================================================================
    # DATA_EXPORTS TABLE INDEXES (falls vorhanden)
    # =========================================================================

    # 13. Export-Request Deadline (GDPR Export)
    # FIX: Corrected table name from data_export_requests to data_exports
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_data_exports_deadline
        ON data_exports (user_id, created_at)
    """)

    # =========================================================================
    # GDPR_DELETION_REQUESTS TABLE INDEXES (falls vorhanden)
    # =========================================================================

    # 14. GDPR Deletion Requests
    # FIX: Corrected column name from scheduled_execution to deletion_scheduled_for
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_gdpr_deletion_requests_deadline
        ON gdpr_deletion_requests (user_id, deletion_scheduled_for)
    """)


def downgrade() -> None:
    """Remove performance indexes."""

    # GDPR tables
    op.execute("DROP INDEX IF EXISTS ix_gdpr_deletion_requests_deadline")
    # FIX: Corrected index name to match renamed index
    op.execute("DROP INDEX IF EXISTS ix_data_exports_deadline")

    # Batch Jobs
    op.drop_index("ix_batch_jobs_queue", table_name="batch_jobs", if_exists=True)

    # API Keys
    op.drop_index("ix_api_keys_user_active", table_name="api_keys", if_exists=True)

    # Users
    op.drop_index("ix_users_active", table_name="users", if_exists=True)
    op.drop_index("ix_users_tier_created", table_name="users", if_exists=True)
    op.drop_index("ix_users_deletion_deadline", table_name="users", if_exists=True)

    # OCR Results
    op.drop_index("ix_ocr_results_history", table_name="ocr_results", if_exists=True)

    # Processing Jobs
    op.drop_index("ix_processing_jobs_queue", table_name="processing_jobs", if_exists=True)

    # Documents
    op.execute("DROP INDEX IF EXISTS ix_documents_search_vector_gin")
    op.execute("DROP INDEX IF EXISTS ix_documents_with_embedding")
    op.drop_index("ix_documents_type_status", table_name="documents", if_exists=True)
    op.drop_index("ix_documents_updated_at", table_name="documents", if_exists=True)
    op.drop_index("ix_documents_backend_status", table_name="documents", if_exists=True)
