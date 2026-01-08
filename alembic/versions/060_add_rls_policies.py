# -*- coding: utf-8 -*-
"""RLS Policies fuer Kasse-Modul Multi-Tenant Isolation.

KRITISCH: Migration 058 aktiviert RLS aber definiert KEINE Policies!
Diese Migration fuegt die fehlenden Policies hinzu.

Revision ID: 060_add_rls_policies
Revises: 059_add_gobd_compliance
Create Date: 2024-12-29

RLS (Row Level Security) stellt sicher, dass:
- Jede Company nur ihre eigenen Daten sieht
- Kein Cross-Tenant Zugriff moeglich ist
- Selbst bei SQL-Injection keine fremden Daten lesbar sind
"""

from alembic import op

# revision identifiers
revision = "060"
down_revision = "059"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add RLS policies for multi-tenant isolation."""

    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    if not is_postgres:
        # SQLite hat kein RLS - skip
        return

    # =========================================================================
    # 1. SESSION VARIABLE HELPER FUNCTION
    # =========================================================================
    # Diese Funktion ermoeglicht sicheren Zugriff auf company_id
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

    # =========================================================================
    # 2. RLS POLICIES FUER CASH_ENTRIES
    # =========================================================================
    op.execute("""
        CREATE POLICY cash_entries_company_isolation ON cash_entries
            FOR ALL
            USING (company_id = get_current_company_id())
            WITH CHECK (company_id = get_current_company_id());
    """)

    # =========================================================================
    # 3. RLS POLICIES FUER CASH_REGISTERS
    # =========================================================================
    op.execute("""
        CREATE POLICY cash_registers_company_isolation ON cash_registers
            FOR ALL
            USING (company_id = get_current_company_id())
            WITH CHECK (company_id = get_current_company_id());
    """)

    # =========================================================================
    # 4. RLS POLICIES FUER CASH_CATEGORIES
    # =========================================================================
    # Kategorien koennen company_id = NULL haben (System-Kategorien)
    op.execute("""
        CREATE POLICY cash_categories_company_isolation ON cash_categories
            FOR ALL
            USING (
                company_id IS NULL  -- System-Kategorien fuer alle sichtbar
                OR company_id = get_current_company_id()
            )
            WITH CHECK (
                company_id IS NULL
                OR company_id = get_current_company_id()
            );
    """)

    # =========================================================================
    # 5. RLS POLICIES FUER CASH_COUNTS
    # =========================================================================
    op.execute("""
        CREATE POLICY cash_counts_company_isolation ON cash_counts
            FOR ALL
            USING (company_id = get_current_company_id())
            WITH CHECK (company_id = get_current_company_id());
    """)

    # =========================================================================
    # 6. RLS POLICIES FUER EXPENSE_REPORTS
    # =========================================================================
    op.execute("""
        CREATE POLICY expense_reports_company_isolation ON expense_reports
            FOR ALL
            USING (company_id = get_current_company_id())
            WITH CHECK (company_id = get_current_company_id());
    """)

    # =========================================================================
    # 7. RLS POLICIES FUER EXPENSE_ITEMS
    # =========================================================================
    # expense_items haben keine eigene company_id, aber gehoeren zu expense_reports
    op.execute("""
        CREATE POLICY expense_items_company_isolation ON expense_items
            FOR ALL
            USING (
                expense_report_id IN (
                    SELECT id FROM expense_reports
                    WHERE company_id = get_current_company_id()
                )
            )
            WITH CHECK (
                expense_report_id IN (
                    SELECT id FROM expense_reports
                    WHERE company_id = get_current_company_id()
                )
            );
    """)

    # =========================================================================
    # 8. BYPASS POLICY FUER SUPERUSER/SERVICE-ACCOUNT
    # =========================================================================
    # Wichtig: Backend-Service braucht Zugriff ohne company_id gesetzt
    # Dies wird durch BYPASSRLS Role oder separate Policy geloest

    # Option A: Service-User Policy (wenn company_id NULL ist = Backend-Zugriff)
    # Wir verwenden hier die sichere Variante: Wenn keine company_id gesetzt,
    # wird nichts zurueckgegeben (ausser bei System-Kategorien)

    # Fuer Backend-Zugriff muss vor Queries:
    # SET app.current_company_id = '<company-uuid>';
    # ausgefuehrt werden (siehe company_context Middleware)


def downgrade() -> None:
    """Remove RLS policies."""

    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    if not is_postgres:
        return

    # Drop policies in reverse order
    op.execute("DROP POLICY IF EXISTS expense_items_company_isolation ON expense_items")
    op.execute("DROP POLICY IF EXISTS expense_reports_company_isolation ON expense_reports")
    op.execute("DROP POLICY IF EXISTS cash_counts_company_isolation ON cash_counts")
    op.execute("DROP POLICY IF EXISTS cash_categories_company_isolation ON cash_categories")
    op.execute("DROP POLICY IF EXISTS cash_registers_company_isolation ON cash_registers")
    op.execute("DROP POLICY IF EXISTS cash_entries_company_isolation ON cash_entries")

    # Drop helper function
    op.execute("DROP FUNCTION IF EXISTS get_current_company_id()")
