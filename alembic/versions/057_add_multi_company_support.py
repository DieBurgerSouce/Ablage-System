"""Add multi-company support for Kasse module.

Revision ID: 057_add_multi_company_support
Revises: 056_add_finance_document_history
Create Date: 2024-12-29

Multi-Company-Architektur fuer Kasse-Modul:
- companies: Firmen/Mandanten (ersetzt CompanySettings-Singleton)
- user_companies: User-Firma Zuordnung mit granularen Berechtigungen
- Row-Level Security (RLS) fuer Multi-Tenant-Isolation
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "057"
down_revision = "056"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add multi-company support tables."""

    # Check dialect for cross-database compatibility
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    if is_postgres:
        uuid_type = postgresql.UUID(as_uuid=True)
        json_type = postgresql.JSONB
    else:
        uuid_type = sa.String(36)
        json_type = sa.JSON

    # =========================================================================
    # 1. COMPANIES - Firmen/Mandanten
    # =========================================================================
    op.create_table(
        "companies",
        sa.Column("id", uuid_type, primary_key=True),

        # Identifikation
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("short_name", sa.String(50), nullable=True),
        sa.Column("display_name", sa.String(255), nullable=True),

        # Rechtsform & Register
        sa.Column("legal_form", sa.String(50), nullable=True),
        sa.Column("commercial_register", sa.String(100), nullable=True),
        sa.Column("court", sa.String(100), nullable=True),

        # Steuer
        sa.Column("vat_id", sa.String(20), unique=True, nullable=True),
        sa.Column("tax_number", sa.String(50), nullable=True),

        # Adresse
        sa.Column("street", sa.String(255), nullable=True),
        sa.Column("street_number", sa.String(20), nullable=True),
        sa.Column("postal_code", sa.String(10), nullable=True),
        sa.Column("city", sa.String(100), nullable=True),
        sa.Column("country", sa.String(2), server_default="DE"),

        # Kontakt
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("phone", sa.String(50), nullable=True),
        sa.Column("website", sa.String(255), nullable=True),

        # Banking (Hauptkonto)
        sa.Column("iban", sa.String(34), nullable=True),
        sa.Column("bic", sa.String(11), nullable=True),
        sa.Column("bank_name", sa.String(100), nullable=True),

        # Alternative Namen fuer OCR-Erkennung
        sa.Column("alternative_names", json_type, server_default="[]"),

        # Einstellungen
        sa.Column("default_currency", sa.String(3), server_default="EUR"),
        sa.Column("fiscal_year_start", sa.Integer, server_default="1"),
        sa.Column("kontenrahmen", sa.String(10), server_default="SKR03"),

        # Status
        sa.Column("is_active", sa.Boolean, server_default="true"),
        sa.Column("is_default", sa.Boolean, server_default="false"),

        # Audit
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.Column("created_by_id", uuid_type, nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),

        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="SET NULL"),
    )

    op.create_index("ix_companies_vat_id", "companies", ["vat_id"])
    op.create_index("ix_companies_is_active", "companies", ["is_active"])
    op.create_index("ix_companies_is_default", "companies", ["is_default"])
    op.create_index("ix_companies_deleted_at", "companies", ["deleted_at"])
    op.create_index("ix_companies_name", "companies", ["name"])

    # =========================================================================
    # 2. USER_COMPANIES - User-Firma Zuordnung
    # =========================================================================
    op.create_table(
        "user_companies",
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column("user_id", uuid_type, nullable=False),
        sa.Column("company_id", uuid_type, nullable=False),

        # Rolle
        sa.Column("role", sa.String(50), server_default="member"),

        # Granulare Berechtigungen fuer Kasse-Modul
        sa.Column("can_manage_cash", sa.Boolean, server_default="false"),
        sa.Column("can_approve_expenses", sa.Boolean, server_default="false"),
        sa.Column("can_export_datev", sa.Boolean, server_default="false"),
        sa.Column("can_manage_settings", sa.Boolean, server_default="false"),

        # Aktive Firma fuer Session
        sa.Column("is_current", sa.Boolean, server_default="false"),

        # Audit
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),

        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("user_id", "company_id", name="uq_user_companies_user_company"),
    )

    op.create_index("ix_user_companies_user_id", "user_companies", ["user_id"])
    op.create_index("ix_user_companies_company_id", "user_companies", ["company_id"])
    op.create_index("ix_user_companies_is_current", "user_companies", ["is_current"])
    op.create_index("ix_user_companies_role", "user_companies", ["role"])

    # =========================================================================
    # 3. MIGRATION: CompanySettings -> Company (falls vorhanden)
    # =========================================================================
    # Pruefe ob company_settings existiert und migriere Daten
    if is_postgres:
        op.execute("""
            DO $$
            BEGIN
                IF EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'company_settings') THEN
                    INSERT INTO companies (
                        id, name, vat_id, tax_number, street, postal_code,
                        city, country, email, phone, website, iban, bic,
                        commercial_register, court, alternative_names, is_default
                    )
                    SELECT
                        gen_random_uuid(),
                        COALESCE(company_name, 'Meine Firma'),
                        vat_id, tax_number, street, postal_code,
                        city,
                        CASE
                            WHEN country IS NULL THEN 'DE'
                            WHEN country IN ('Deutschland', 'Germany', 'DE') THEN 'DE'
                            WHEN country IN ('Oesterreich', 'Austria', 'AT') THEN 'AT'
                            WHEN country IN ('Schweiz', 'Switzerland', 'CH') THEN 'CH'
                            WHEN LENGTH(country) = 2 THEN country
                            ELSE 'DE'
                        END,
                        email, phone, website,
                        iban, bic, commercial_register, court,
                        COALESCE(alternative_names, '[]'::jsonb), true
                    FROM company_settings
                    LIMIT 1;
                END IF;
            END $$;
        """)

    # =========================================================================
    # 4. ROW-LEVEL SECURITY (PostgreSQL only)
    # =========================================================================
    if is_postgres:
        # Enable RLS auf companies
        op.execute("ALTER TABLE companies ENABLE ROW LEVEL SECURITY")

        # Enable RLS auf user_companies
        op.execute("ALTER TABLE user_companies ENABLE ROW LEVEL SECURITY")

        # Policy fuer companies: User sieht nur Firmen, denen er zugeordnet ist
        op.execute("""
            CREATE POLICY company_access_policy ON companies
            FOR ALL
            USING (
                id IN (
                    SELECT company_id FROM user_companies
                    WHERE user_id = current_setting('app.current_user_id', true)::uuid
                )
                OR current_setting('app.is_admin', true)::boolean = true
            )
        """)

        # Policy fuer user_companies: User sieht nur eigene Zuordnungen
        op.execute("""
            CREATE POLICY user_company_access_policy ON user_companies
            FOR ALL
            USING (
                user_id = current_setting('app.current_user_id', true)::uuid
                OR current_setting('app.is_admin', true)::boolean = true
            )
        """)

    # =========================================================================
    # 5. ADD FK CONSTRAINT TO INVOICES TABLE (if exists)
    # =========================================================================
    # invoices.company_id wurde in Migration 022 ohne FK erstellt
    # Jetzt koennen wir die FK Constraint hinzufuegen
    if is_postgres:
        op.execute("""
            DO $$
            BEGIN
                IF EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'invoices') THEN
                    IF NOT EXISTS (
                        SELECT FROM information_schema.table_constraints
                        WHERE constraint_name = 'fk_invoices_company_id'
                        AND table_name = 'invoices'
                    ) THEN
                        ALTER TABLE invoices
                        ADD CONSTRAINT fk_invoices_company_id
                        FOREIGN KEY (company_id) REFERENCES companies(id);
                    END IF;
                END IF;
            END $$;
        """)


def downgrade() -> None:
    """Remove multi-company support tables."""

    # Check dialect
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    # Drop FK constraint from invoices (if exists)
    if is_postgres:
        op.execute("""
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT FROM information_schema.table_constraints
                    WHERE constraint_name = 'fk_invoices_company_id'
                    AND table_name = 'invoices'
                ) THEN
                    ALTER TABLE invoices DROP CONSTRAINT fk_invoices_company_id;
                END IF;
            END $$;
        """)

    # Drop RLS policies (PostgreSQL only)
    if is_postgres:
        op.execute("DROP POLICY IF EXISTS user_company_access_policy ON user_companies")
        op.execute("DROP POLICY IF EXISTS company_access_policy ON companies")
        op.execute("ALTER TABLE user_companies DISABLE ROW LEVEL SECURITY")
        op.execute("ALTER TABLE companies DISABLE ROW LEVEL SECURITY")

    # Drop user_companies
    op.drop_index("ix_user_companies_role", table_name="user_companies")
    op.drop_index("ix_user_companies_is_current", table_name="user_companies")
    op.drop_index("ix_user_companies_company_id", table_name="user_companies")
    op.drop_index("ix_user_companies_user_id", table_name="user_companies")
    op.drop_table("user_companies")

    # Drop companies
    op.drop_index("ix_companies_name", table_name="companies")
    op.drop_index("ix_companies_deleted_at", table_name="companies")
    op.drop_index("ix_companies_is_default", table_name="companies")
    op.drop_index("ix_companies_is_active", table_name="companies")
    op.drop_index("ix_companies_vat_id", table_name="companies")
    op.drop_table("companies")
