"""Add RLS policies for multi-tenancy

Revision ID: 210_add_rls_policies
Revises: 209_add_dashboard_shares
Create Date: 2026-02-08

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "210_add_rls_policies"
down_revision = "209_add_dashboard_shares"
branch_labels = None
depends_on = None


def _table_exists(tablename: str) -> bool:
    conn = op.get_bind()
    result = conn.execute(sa.text(
        "SELECT 1 FROM pg_tables WHERE schemaname='public' AND tablename=:t"
    ), {"t": tablename})
    return result.fetchone() is not None


def _column_exists(tablename: str, column: str) -> bool:
    conn = op.get_bind()
    result = conn.execute(sa.text(
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_schema='public' AND table_name=:t AND column_name=:c"
    ), {"t": tablename, "c": column})
    return result.fetchone() is not None


def upgrade() -> None:
    """
    Erstellt die tenant_configs Tabelle und aktiviert Row-Level Security
    auf Schluessel-Tabellen fuer Multi-Tenancy.
    """
    # 1. Erstelle tenant_configs Tabelle
    if not _table_exists("tenant_configs"):
        op.create_table(
            "tenant_configs",
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("features", postgresql.JSONB(astext_type=sa.Text()), nullable=True,
                       comment="Feature-Flags (z.B. {'ocr_enabled': true, 'max_users': 50})"),
            sa.Column("quotas", postgresql.JSONB(astext_type=sa.Text()), nullable=True,
                       comment="Kontingente (z.B. {'documents_per_month': 10000, 'storage_gb': 100})"),
            sa.Column("branding", postgresql.JSONB(astext_type=sa.Text()), nullable=True,
                       comment="Branding-Konfiguration (z.B. {'logo_url': '...', 'primary_color': '#...'})"),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true"),
                       comment="Mandant aktiv (false = deaktiviert, keine Zugriffe)"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                       server_default=sa.text("now()")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(["company_id"], ["companies.id"],
                                     name=op.f("fk_tenant_configs_company_id_companies"),
                                     ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id", name=op.f("pk_tenant_configs")),
            sa.UniqueConstraint("company_id", name=op.f("uq_tenant_configs_company_id")),
        )
        op.create_index(op.f("ix_tenant_configs_company_id"), "tenant_configs",
                         ["company_id"], unique=False)
        op.create_index(op.f("ix_tenant_configs_is_active"), "tenant_configs",
                         ["is_active"], unique=False)

    # 2. Aktiviere Row-Level Security auf Schluessel-Tabellen
    tables_with_rls = [
        "documents",
        "invoices",
        "approval_requests",
        "business_entities",
        "bank_transactions",
        "invoice_positions",
        "banking_accounts",
        "banking_category_rules",
        "banking_reconciliation",
        "banking_skonto_tracking",
        "compliance_audits",
        "custom_fields",
        "custom_tags",
        "dashboard_shares",
        "document_chains",
        "document_chain_links",
        "document_versions",
        "entity_contracts",
        "entity_risk_scores",
        "folder_categories",
        "lexware_customers",
        "lexware_suppliers",
        "notification_rules",
        "saved_searches",
        "slack_channels",
        "slack_integrations",
        "user_company_roles",
    ]

    for table in tables_with_rls:
        # Pruefe ob Tabelle existiert und company_id Spalte hat
        if not _column_exists(table, "company_id"):
            continue

        # Aktiviere RLS
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")

        # Erstelle Policy fuer Mandanten-Isolation (idempotent)
        op.execute(sa.text(f"DROP POLICY IF EXISTS tenant_isolation_{table} ON {table}"))
        op.execute(
            f"""
            CREATE POLICY tenant_isolation_{table} ON {table}
            USING (company_id = current_setting('app.current_tenant_id', true)::uuid)
            """
        )

        # Force RLS auch fuer Table Owner
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")

    # 3. Erstelle Policy fuer Superuser-Bypass
    for table in tables_with_rls:
        if not _column_exists(table, "company_id"):
            continue

        op.execute(sa.text(f"DROP POLICY IF EXISTS superuser_bypass_{table} ON {table}"))
        op.execute(
            f"""
            CREATE POLICY superuser_bypass_{table} ON {table}
            USING (
                current_setting('app.current_user_is_superuser', true)::boolean = true
            )
            """
        )


def downgrade() -> None:
    """
    Entfernt Row-Level Security Policies und die tenant_configs Tabelle.
    """
    tables_with_rls = [
        "documents",
        "invoices",
        "approval_requests",
        "business_entities",
        "bank_transactions",
        "invoice_positions",
        "banking_accounts",
        "banking_category_rules",
        "banking_reconciliation",
        "banking_skonto_tracking",
        "compliance_audits",
        "custom_fields",
        "custom_tags",
        "dashboard_shares",
        "document_chains",
        "document_chain_links",
        "document_versions",
        "entity_contracts",
        "entity_risk_scores",
        "folder_categories",
        "lexware_customers",
        "lexware_suppliers",
        "notification_rules",
        "saved_searches",
        "slack_channels",
        "slack_integrations",
        "user_company_roles",
    ]

    for table in tables_with_rls:
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation_{table} ON {table}")
        op.execute(f"DROP POLICY IF EXISTS superuser_bypass_{table} ON {table}")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")

    op.drop_index(op.f("ix_tenant_configs_is_active"), table_name="tenant_configs")
    op.drop_index(op.f("ix_tenant_configs_company_id"), table_name="tenant_configs")
    op.drop_table("tenant_configs")
