"""Add company_id to documents table for multi-tenant isolation.

Revision ID: 071_add_company_id_to_documents
Revises: 070_add_collaboration
Create Date: 2026-01-02

Multi-Tenant Erweiterung fuer Documents:
- company_id FK auf companies Tabelle
- Migration bestehender Dokumente zur Default-Company
- Row-Level Security Policy fuer Mandanten-Isolation
- Index fuer Performance bei company-basierten Queries
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "071"
down_revision = "070"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add company_id to documents table with RLS policy."""

    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    if is_postgres:
        uuid_type = postgresql.UUID(as_uuid=True)
    else:
        uuid_type = sa.String(36)

    # =========================================================================
    # 1. ADD company_id COLUMN (nullable first for migration)
    # =========================================================================
    op.add_column(
        "documents",
        sa.Column("company_id", uuid_type, nullable=True)
    )

    # =========================================================================
    # 2. MIGRATE EXISTING DOCUMENTS to Default Company
    # =========================================================================
    if is_postgres:
        # Setze company_id auf die Default-Firma fuer alle existierenden Dokumente
        op.execute("""
            UPDATE documents
            SET company_id = (
                SELECT id FROM companies
                WHERE is_default = true
                LIMIT 1
            )
            WHERE company_id IS NULL
        """)

        # Falls keine Default-Firma existiert, erstelle eine
        op.execute("""
            DO $$
            DECLARE
                default_company_id UUID;
            BEGIN
                -- Pruefe ob Default-Firma existiert
                SELECT id INTO default_company_id
                FROM companies WHERE is_default = true LIMIT 1;

                -- Wenn keine, erstelle Standard-Firma
                IF default_company_id IS NULL THEN
                    INSERT INTO companies (id, name, short_name, is_default, is_active, kontenrahmen)
                    VALUES (gen_random_uuid(), 'Standard-Firma', 'STD', true, true, 'SKR03')
                    RETURNING id INTO default_company_id;
                END IF;

                -- Update alle Dokumente ohne company_id
                UPDATE documents
                SET company_id = default_company_id
                WHERE company_id IS NULL;
            END $$;
        """)
    else:
        # SQLite Fallback - weniger elegant aber funktional
        op.execute("""
            UPDATE documents
            SET company_id = (
                SELECT id FROM companies
                WHERE is_default = 1
                LIMIT 1
            )
            WHERE company_id IS NULL
        """)

    # =========================================================================
    # 3. MAKE company_id NOT NULL after migration
    # =========================================================================
    op.alter_column(
        "documents",
        "company_id",
        nullable=False
    )

    # =========================================================================
    # 4. ADD FOREIGN KEY CONSTRAINT
    # =========================================================================
    op.create_foreign_key(
        "fk_documents_company_id",
        "documents",
        "companies",
        ["company_id"],
        ["id"],
        ondelete="RESTRICT"  # Verhindere Loeschung von Firmen mit Dokumenten
    )

    # =========================================================================
    # 5. CREATE INDEX for company-based queries
    # =========================================================================
    op.create_index(
        "ix_documents_company_id",
        "documents",
        ["company_id"]
    )

    # Composite Index fuer haeufige Queries: company_id + status
    op.create_index(
        "ix_documents_company_status",
        "documents",
        ["company_id", "status"]
    )

    # Composite Index fuer company_id + upload_date (Timeline-Queries)
    op.create_index(
        "ix_documents_company_upload_date",
        "documents",
        ["company_id", "upload_date"]
    )

    # =========================================================================
    # 6. ROW-LEVEL SECURITY POLICY (PostgreSQL only)
    # =========================================================================
    if is_postgres:
        # Enable RLS auf documents (falls noch nicht aktiviert)
        op.execute("""
            DO $$
            BEGIN
                -- Enable RLS if not already enabled
                IF NOT EXISTS (
                    SELECT 1 FROM pg_tables
                    WHERE tablename = 'documents'
                    AND rowsecurity = true
                ) THEN
                    ALTER TABLE documents ENABLE ROW LEVEL SECURITY;
                END IF;
            END $$;
        """)

        # Drop existing policy if exists (idempotent)
        op.execute("""
            DROP POLICY IF EXISTS documents_company_isolation ON documents
        """)

        # Create company isolation policy
        # Dokumente sind nur sichtbar wenn:
        # 1. company_id = current_setting('app.current_company_id')
        # 2. ODER User ist Admin (app.is_admin = true)
        op.execute("""
            CREATE POLICY documents_company_isolation ON documents
            FOR ALL
            USING (
                company_id = NULLIF(current_setting('app.current_company_id', true), '')::uuid
                OR current_setting('app.is_admin', true)::boolean = true
            )
            WITH CHECK (
                company_id = NULLIF(current_setting('app.current_company_id', true), '')::uuid
                OR current_setting('app.is_admin', true)::boolean = true
            )
        """)


def downgrade() -> None:
    """Remove company_id from documents table."""

    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    # Drop RLS policy (PostgreSQL only)
    if is_postgres:
        op.execute("DROP POLICY IF EXISTS documents_company_isolation ON documents")
        # Note: RLS bleibt aktiviert fuer andere Policies

    # Drop indexes
    op.drop_index("ix_documents_company_upload_date", table_name="documents")
    op.drop_index("ix_documents_company_status", table_name="documents")
    op.drop_index("ix_documents_company_id", table_name="documents")

    # Drop foreign key
    op.drop_constraint("fk_documents_company_id", "documents", type_="foreignkey")

    # Drop column
    op.drop_column("documents", "company_id")
