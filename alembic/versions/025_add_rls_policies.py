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

HINWEIS: Diese Migration prueft Tabellen- und Spalten-Existenz.
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "025"
down_revision = "024"
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


def policy_exists(conn, policy_name: str, table_name: str) -> bool:
    """Prüft ob eine RLS-Policy existiert."""
    result = conn.execute(sa.text("""
        SELECT EXISTS (
            SELECT FROM pg_policies
            WHERE policyname = :policy_name AND tablename = :table_name
        )
    """), {"policy_name": policy_name, "table_name": table_name})
    return result.scalar()


def upgrade() -> None:
    """Add RLS policies for multi-tenant document isolation."""
    conn = op.get_bind()

    # =========================================================================
    # 1. Enable RLS on documents table
    # =========================================================================
    if table_exists(conn, "documents"):
        op.execute("ALTER TABLE documents ENABLE ROW LEVEL SECURITY")

        # =========================================================================
        # 2. Create policy: Users can only see their own documents
        # =========================================================================
        if not policy_exists(conn, "documents_owner_select", "documents"):
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
        if not policy_exists(conn, "documents_owner_update", "documents"):
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
        if not policy_exists(conn, "documents_owner_delete", "documents"):
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
        if not policy_exists(conn, "documents_insert", "documents"):
            op.execute("""
                CREATE POLICY documents_insert ON documents
                FOR INSERT
                WITH CHECK (true)
            """)

        # =========================================================================
        # 8. Create index for RLS performance (without deleted_at filter if column doesn't exist)
        # =========================================================================
        if column_exists(conn, "documents", "deleted_at"):
            op.execute("""
                CREATE INDEX IF NOT EXISTS idx_documents_owner_id_rls
                ON documents(owner_id)
                WHERE deleted_at IS NULL
            """)
        else:
            op.execute("""
                CREATE INDEX IF NOT EXISTS idx_documents_owner_id_rls
                ON documents(owner_id)
            """)

    # =========================================================================
    # 6. Enable RLS on ocr_results table (linked to documents)
    # =========================================================================
    if table_exists(conn, "ocr_results"):
        op.execute("ALTER TABLE ocr_results ENABLE ROW LEVEL SECURITY")

        if not policy_exists(conn, "ocr_results_via_document", "ocr_results"):
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
    if table_exists(conn, "processing_jobs"):
        op.execute("ALTER TABLE processing_jobs ENABLE ROW LEVEL SECURITY")

        if not policy_exists(conn, "processing_jobs_via_document", "processing_jobs"):
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
