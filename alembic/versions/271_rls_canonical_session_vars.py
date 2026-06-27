"""RLS-Konsolidierung: Migration-210-Policies auf kanonische Session-Variablen.

Die von Migration 210 erzeugten FORCE-RLS-Policies nutzten zwei Session-Variablen,
die die Applikation standardmaessig NICHT setzte:
  - tenant_isolation_<t>:  company_id = current_setting('app.current_tenant_id')
  - superuser_bypass_<t>:  current_setting('app.current_user_is_superuser')::boolean

Ein pg_policies-Live-Audit (Stand Head 270) zeigte: nur 5 Tabellen tragen diese
Policies (documents, invoices, approval_requests, document_versions, slack_channels),
und JEDE hat zusaetzlich eine kanonische company_id-Policy (app.current_company_id),
die 89 Policies projektweit verwenden. Die 210-Policies sind damit redundant UND
haengen an nie gesetzten Variablen.

Diese Migration schreibt die 10 Policies (5x tenant_isolation + 5x superuser_bypass)
auf die KANONISCHEN Variablen um:
  - app.current_company_id  (gesetzt in set_rls_company_context / *_sync)
  - app.is_admin            (gesetzt in set_rls_context)
Semantik + Policy-Anzahl bleiben erhalten; nur die Variablenquelle wird konsolidiert.
Danach ist app.current_tenant_id / app.current_user_is_superuser nirgends mehr
referenziert (die app-seitige Zusatz-Setzung dieser Vars wird damit redundant).

Idempotent (to_regclass-Guard + DROP POLICY IF EXISTS). PostgreSQL-only (SQLite/Tests
ueberspringen RLS). Downgrade stellt den 210-Zustand wieder her.

Revision ID: 271
Revises: 270
Create Date: 2026-06-27
"""
from alembic import op

# revision identifiers, used by Alembic.
revision = "271"
down_revision = "270"
branch_labels = None
depends_on = None

# Tabellen mit Migration-210-Policies an current_tenant_id (aus pg_policies-Audit).
_RLS_TABLES = [
    "documents",
    "invoices",
    "approval_requests",
    "document_versions",
    "slack_channels",
]


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    for table in _RLS_TABLES:
        op.execute(
            f"""
            DO $$
            BEGIN
                IF to_regclass('public.{table}') IS NOT NULL THEN
                    -- tenant_isolation: app.current_tenant_id -> app.current_company_id (kanonisch)
                    EXECUTE 'DROP POLICY IF EXISTS tenant_isolation_{table} ON {table}';
                    EXECUTE 'CREATE POLICY tenant_isolation_{table} ON {table} '
                            'USING (company_id = NULLIF(current_setting(''app.current_company_id'', true), '''')::uuid)';
                    -- superuser_bypass: app.current_user_is_superuser -> app.is_admin (kanonisch)
                    EXECUTE 'DROP POLICY IF EXISTS superuser_bypass_{table} ON {table}';
                    EXECUTE 'CREATE POLICY superuser_bypass_{table} ON {table} '
                            'USING (NULLIF(current_setting(''app.is_admin'', true), '''')::boolean IS TRUE)';
                END IF;
            END $$;
            """
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    for table in _RLS_TABLES:
        op.execute(
            f"""
            DO $$
            BEGIN
                IF to_regclass('public.{table}') IS NOT NULL THEN
                    EXECUTE 'DROP POLICY IF EXISTS tenant_isolation_{table} ON {table}';
                    EXECUTE 'CREATE POLICY tenant_isolation_{table} ON {table} '
                            'USING (company_id = current_setting(''app.current_tenant_id'', true)::uuid)';
                    EXECUTE 'DROP POLICY IF EXISTS superuser_bypass_{table} ON {table}';
                    EXECUTE 'CREATE POLICY superuser_bypass_{table} ON {table} '
                            'USING (current_setting(''app.current_user_is_superuser'', true)::boolean = true)';
                END IF;
            END $$;
            """
        )
