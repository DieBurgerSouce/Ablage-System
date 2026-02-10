"""RLS Coverage Audit - Ensure all tenant-scoped tables have RLS policies.

Revision ID: 211_rls_coverage_audit
Revises: 210_add_rls_policies
Create Date: 2026-02-10

Zweck:
------
Diese Migration stellt sicher, dass ALLE Tabellen mit company_id-Spalte
Row-Level Security (RLS) aktiviert haben. Mehrere RLS-Migrationen existieren
(060, 110, 210), aber einige Tabellen koennten uebersehen worden sein.

Diese Migration ist idempotent - sie kann mehrmals ausgefuehrt werden ohne Fehler.

Geschuetzte Tabellen:
--------------------
- invoices: Rechnungen (Ein-/Ausgang)
- bank_transactions: Banktransaktionen
- bank_accounts: Bankkonten (alias: banking_accounts)
- document_chains: Dokumentenketten
- notification_rules: Benachrichtigungsregeln
- approval_workflows: Freigabe-Workflows
- alert_rules: Alarm-Regeln

Sicherheitsstrategie:
--------------------
Die Policies verwenden current_setting('app.current_company_id', true)
analog zu Migration 110. Der zweite Parameter 'true' bedeutet:
- Kein Fehler wenn Variable nicht gesetzt ist (gibt NULL zurueck)
- Ermoeglicht Bypass fuer System-Tasks

"""

from alembic import op
from sqlalchemy import text

# revision identifiers
revision = "211_rls_coverage_audit"
down_revision = "210_add_rls_policies"
branch_labels = None
depends_on = None


# Tabellen die RLS benoetigen (aus Aufgabenstellung)
TABLES_TO_AUDIT = [
    "invoices",
    "bank_transactions",
    "bank_accounts",  # Primaerer Name
    "banking_accounts",  # Alias-Name (moeglicherweise verwendet)
    "document_chains",
    "notification_rules",
    "approval_workflows",
    "alert_rules",
]


def upgrade() -> None:
    """Add or verify RLS policies for all tenant-scoped tables."""

    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    if not is_postgres:
        # SQLite hat kein RLS - skip
        return

    # Stelle sicher dass Helper-Funktion existiert (aus Migration 110)
    # Diese Funktion ist idempotent und wird nicht neu erstellt wenn vorhanden
    op.execute("""
        CREATE OR REPLACE FUNCTION get_current_company_id()
        RETURNS uuid AS $$
        BEGIN
            RETURN NULLIF(current_setting('app.current_company_id', true), '')::uuid;
        EXCEPTION
            WHEN OTHERS THEN
                RETURN NULL;
        END;
        $$ LANGUAGE plpgsql STABLE;
    """)

    # Fuer jede Tabelle: RLS aktivieren und Policy erstellen
    for table_name in TABLES_TO_AUDIT:
        # Pruefen ob Tabelle existiert
        check_table = bind.execute(
            text("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE table_schema = 'public'
                    AND table_name = :tbl
                )
            """),
            {"tbl": table_name},
        )
        if not check_table.scalar():
            # Tabelle existiert nicht - skip
            continue

        # Pruefen ob company_id Spalte existiert
        check_col = bind.execute(
            text("""
                SELECT EXISTS (
                    SELECT FROM information_schema.columns
                    WHERE table_schema = 'public'
                    AND table_name = :tbl
                    AND column_name = 'company_id'
                )
            """),
            {"tbl": table_name},
        )
        if not check_col.scalar():
            # Keine company_id Spalte - skip
            continue

        # =====================================================================
        # RLS aktivieren (idempotent - wirft keinen Fehler wenn bereits aktiv)
        # =====================================================================
        op.execute(f"ALTER TABLE {table_name} ENABLE ROW LEVEL SECURITY")

        # =====================================================================
        # Policy loeschen falls vorhanden (macht Migration idempotent)
        # =====================================================================
        op.execute(f"DROP POLICY IF EXISTS {table_name}_company_isolation ON {table_name}")

        # =====================================================================
        # Neue Isolation-Policy erstellen
        # =====================================================================
        op.execute(f"""
            CREATE POLICY {table_name}_company_isolation ON {table_name}
                FOR ALL
                USING (
                    company_id IS NULL
                    OR company_id = get_current_company_id()
                )
                WITH CHECK (
                    company_id IS NULL
                    OR company_id = get_current_company_id()
                );
        """)

        # =====================================================================
        # Index fuer Performance erstellen (falls nicht vorhanden)
        # =====================================================================
        check_idx = bind.execute(
            text("""
                SELECT EXISTS (
                    SELECT FROM pg_indexes
                    WHERE tablename = :tbl
                    AND indexname = :idx
                )
            """),
            {"tbl": table_name, "idx": f"ix_{table_name}_company_id_rls"},
        )
        if not check_idx.scalar():
            op.execute(f"""
                CREATE INDEX IF NOT EXISTS
                ix_{table_name}_company_id_rls ON {table_name} (company_id)
            """)


def downgrade() -> None:
    """Remove RLS policies created by this migration."""

    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    if not is_postgres:
        return

    # Entferne Policies fuer alle Tabellen
    for table_name in TABLES_TO_AUDIT:
        check_table = bind.execute(
            text("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE table_schema = 'public'
                    AND table_name = :tbl
                )
            """),
            {"tbl": table_name},
        )
        if not check_table.scalar():
            continue

        # Policy loeschen
        op.execute(f"DROP POLICY IF EXISTS {table_name}_company_isolation ON {table_name}")

        # RLS deaktivieren (nur wenn keine anderen Policies existieren)
        check_policies = bind.execute(
            text("""
                SELECT COUNT(*) FROM pg_policies
                WHERE tablename = :tbl
            """),
            {"tbl": table_name},
        )
        if check_policies.scalar() == 0:
            # Keine Policies mehr - RLS deaktivieren
            op.execute(f"ALTER TABLE {table_name} DISABLE ROW LEVEL SECURITY")

        # Index loeschen
        op.execute(f"DROP INDEX IF EXISTS ix_{table_name}_company_id_rls")

    # Behalte get_current_company_id() - wird von anderen Migrationen genutzt
