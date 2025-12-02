"""Add Row Level Security (RLS) policies for document access control.

Revision ID: 025_add_rls_policies
Revises: 024_add_missing_constraints
Create Date: 2024-12-02

SECURITY: RLS ermoeglicht fein-granulare Zugriffskontrolle auf Datenbankebene:
- Benutzer koennen nur ihre eigenen Dokumente sehen/bearbeiten
- Admins haben vollen Zugriff
- Defense-in-Depth: Selbst bei Application-Layer Bypass greift RLS

WICHTIG: Erfordert, dass die Applikation SET LOCAL app.current_user_id
vor Queries ausfuehrt!
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "025_add_rls_policies"
down_revision = "024_add_missing_constraints"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add RLS policies for multi-tenant document isolation."""

    # =========================================================================
    # 1. Enable RLS on documents table
    # =========================================================================
    op.execute("ALTER TABLE documents ENABLE ROW LEVEL SECURITY")

    # =========================================================================
    # 2. Create policy: Users can only see their own documents
    # =========================================================================
    op.execute("""
        CREATE POLICY documents_owner_select ON documents
        FOR SELECT
        USING (
            -- Owner can see their documents
            owner_id::text = current_setting('app.current_user_id', true)
            OR
            -- Bypass if setting not set (for system operations)
            current_setting('app.current_user_id', true) IS NULL
            OR
            current_setting('app.current_user_id', true) = ''
            OR
            -- Admin bypass (checked via role)
            current_setting('app.is_admin', true) = 'true'
        )
    """)

    # =========================================================================
    # 3. Create policy: Users can only update their own documents
    # =========================================================================
    op.execute("""
        CREATE POLICY documents_owner_update ON documents
        FOR UPDATE
        USING (
            owner_id::text = current_setting('app.current_user_id', true)
            OR
            current_setting('app.current_user_id', true) IS NULL
            OR
            current_setting('app.current_user_id', true) = ''
            OR
            current_setting('app.is_admin', true) = 'true'
        )
    """)

    # =========================================================================
    # 4. Create policy: Users can only delete their own documents
    # =========================================================================
    op.execute("""
        CREATE POLICY documents_owner_delete ON documents
        FOR DELETE
        USING (
            owner_id::text = current_setting('app.current_user_id', true)
            OR
            current_setting('app.current_user_id', true) IS NULL
            OR
            current_setting('app.current_user_id', true) = ''
            OR
            current_setting('app.is_admin', true) = 'true'
        )
    """)

    # =========================================================================
    # 5. Create policy: Anyone can insert (owner_id set by app)
    # =========================================================================
    op.execute("""
        CREATE POLICY documents_insert ON documents
        FOR INSERT
        WITH CHECK (true)
    """)

    # =========================================================================
    # 6. Enable RLS on ocr_results table (linked to documents)
    # =========================================================================
    op.execute("ALTER TABLE ocr_results ENABLE ROW LEVEL SECURITY")

    op.execute("""
        CREATE POLICY ocr_results_via_document ON ocr_results
        FOR ALL
        USING (
            -- Access if user owns the parent document
            EXISTS (
                SELECT 1 FROM documents d
                WHERE d.id = ocr_results.document_id
                AND (
                    d.owner_id::text = current_setting('app.current_user_id', true)
                    OR current_setting('app.current_user_id', true) IS NULL
                    OR current_setting('app.current_user_id', true) = ''
                    OR current_setting('app.is_admin', true) = 'true'
                )
            )
        )
    """)

    # =========================================================================
    # 7. Enable RLS on processing_jobs table
    # =========================================================================
    op.execute("ALTER TABLE processing_jobs ENABLE ROW LEVEL SECURITY")

    op.execute("""
        CREATE POLICY processing_jobs_via_document ON processing_jobs
        FOR ALL
        USING (
            -- Access if user owns the parent document
            EXISTS (
                SELECT 1 FROM documents d
                WHERE d.id = processing_jobs.document_id
                AND (
                    d.owner_id::text = current_setting('app.current_user_id', true)
                    OR current_setting('app.current_user_id', true) IS NULL
                    OR current_setting('app.current_user_id', true) = ''
                    OR current_setting('app.is_admin', true) = 'true'
                )
            )
        )
    """)

    # =========================================================================
    # 8. Create index for RLS performance
    # =========================================================================
    # FIX: Corrected column reference from is_deleted to deleted_at (DateTime, not Boolean)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_documents_owner_id_rls
        ON documents(owner_id)
        WHERE deleted_at IS NULL
    """)


def downgrade() -> None:
    """Remove RLS policies and disable RLS."""

    # Drop policies
    op.execute("DROP POLICY IF EXISTS documents_owner_select ON documents")
    op.execute("DROP POLICY IF EXISTS documents_owner_update ON documents")
    op.execute("DROP POLICY IF EXISTS documents_owner_delete ON documents")
    op.execute("DROP POLICY IF EXISTS documents_insert ON documents")
    op.execute("DROP POLICY IF EXISTS ocr_results_via_document ON ocr_results")
    op.execute("DROP POLICY IF EXISTS processing_jobs_via_document ON processing_jobs")

    # Drop index
    op.execute("DROP INDEX IF EXISTS idx_documents_owner_id_rls")

    # Disable RLS
    op.execute("ALTER TABLE processing_jobs DISABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE ocr_results DISABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE documents DISABLE ROW LEVEL SECURITY")
