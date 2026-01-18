"""Add multi-tenant enhancements for 20+ companies support.

Revision ID: 098_multi_tenant_enhancements
Revises: 097_add_document_templates
Create Date: 2026-01-17

Enhancements for scaling to 20+ companies:
- Index on companies.short_name for fast lookups
- Seed data for legacy companies (folie, messer)
- company_presence already stores short_names as strings
  (no schema change needed - dynamic loading via CompanyService)
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from uuid import uuid4

revision = "098_multi_tenant_enhancements"
down_revision = "097_add_document_templates"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add multi-tenant enhancements."""

    # Check dialect for cross-database compatibility
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    # =========================================================================
    # 1. ADD INDEX ON companies.short_name
    # =========================================================================
    # This index speeds up company lookups by short_name
    # (used extensively in entity_search_service and entities API)
    op.create_index(
        "ix_companies_short_name",
        "companies",
        ["short_name"],
        unique=True,  # short_name should be unique per company
        postgresql_where=sa.text("short_name IS NOT NULL AND deleted_at IS NULL"),
    )

    # =========================================================================
    # 2. SEED DEFAULT COMPANIES (if not exist)
    # =========================================================================
    # Create the legacy companies (folie, messer) for backwards compatibility
    # These are the hardcoded companies that existed before multi-tenant support

    if is_postgres:
        op.execute("""
            INSERT INTO companies (id, name, short_name, display_name, is_active, is_default, created_at, updated_at)
            SELECT
                gen_random_uuid(),
                'Folie GmbH',
                'folie',
                'Folie',
                true,
                true,  -- First company is default
                NOW(),
                NOW()
            WHERE NOT EXISTS (
                SELECT 1 FROM companies WHERE short_name = 'folie'
            );
        """)

        op.execute("""
            INSERT INTO companies (id, name, short_name, display_name, is_active, is_default, created_at, updated_at)
            SELECT
                gen_random_uuid(),
                'Spargelmesser GmbH',
                'messer',
                'Spargelmesser',
                true,
                false,
                NOW(),
                NOW()
            WHERE NOT EXISTS (
                SELECT 1 FROM companies WHERE short_name = 'messer'
            );
        """)

    # =========================================================================
    # 3. ADD GIN INDEX ON business_entities.company_presence
    # =========================================================================
    # This index speeds up JSONB array containment queries like:
    # company_presence @> '["folie"]'

    if is_postgres:
        op.execute("""
            CREATE INDEX IF NOT EXISTS ix_business_entities_company_presence_gin
            ON business_entities USING GIN (company_presence);
        """)

    # =========================================================================
    # 4. ADD GIN INDEX ON business_entities.lexware_ids
    # =========================================================================
    # This index speeds up JSONB key lookups like:
    # lexware_ids->'folie'->>'kd_nr'

    if is_postgres:
        op.execute("""
            CREATE INDEX IF NOT EXISTS ix_business_entities_lexware_ids_gin
            ON business_entities USING GIN (lexware_ids);
        """)


def downgrade() -> None:
    """Remove multi-tenant enhancements."""

    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    # Drop GIN indexes
    if is_postgres:
        op.execute("DROP INDEX IF EXISTS ix_business_entities_lexware_ids_gin")
        op.execute("DROP INDEX IF EXISTS ix_business_entities_company_presence_gin")

    # Drop short_name index
    op.drop_index("ix_companies_short_name", table_name="companies")

    # Note: We do NOT delete the seed companies in downgrade
    # as they may have been used for business data
