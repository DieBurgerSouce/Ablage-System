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
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "024_add_missing_constraints"
down_revision = "023_add_performance_indexes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add missing constraints for data integrity."""

    # =========================================================================
    # API_KEYS TABLE CONSTRAINTS
    # =========================================================================

    # 1. UNIQUE Constraint auf token_hash (SECURITY FIX)
    # Verhindert doppelte API-Keys - kritisch fuer Sicherheit
    op.create_unique_constraint(
        "uq_api_keys_token_hash",
        "api_keys",
        ["token_hash"]
    )

    # =========================================================================
    # PROCESSING_JOBS TABLE CONSTRAINTS
    # =========================================================================

    # 2. CHECK Constraint auf priority (0-9)
    op.execute("""
        ALTER TABLE processing_jobs
        ADD CONSTRAINT check_processing_jobs_priority
        CHECK (priority >= 0 AND priority <= 9)
    """)

    # =========================================================================
    # DOCUMENTS TABLE CONSTRAINTS
    # =========================================================================

    # 3. CHECK Constraint auf ocr_confidence (0-1)
    op.execute("""
        ALTER TABLE documents
        ADD CONSTRAINT check_documents_ocr_confidence
        CHECK (ocr_confidence IS NULL OR (ocr_confidence >= 0 AND ocr_confidence <= 1.0))
    """)

    # =========================================================================
    # BATCH_JOBS TABLE CONSTRAINTS
    # =========================================================================

    # 4. CHECK Constraint auf batch_jobs.priority (0-10)
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
    op.drop_constraint("uq_api_keys_token_hash", "api_keys", type_="unique")
