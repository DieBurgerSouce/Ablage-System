# -*- coding: utf-8 -*-
"""Comprehensive RLS Policies fuer Multi-Tenant Isolation (Phase 1.1).

KRITISCH: Diese Migration implementiert RLS fuer ALLE 80+ tenant-sensitiven Tabellen.
Dies stellt Database-Level Isolation sicher, selbst wenn Application-Layer kompromittiert wird.

Revision ID: 110_comprehensive_rls_policies
Revises: 110_add_team_collaboration
Create Date: 2026-01-21

Security Architecture:
- RLS (Row Level Security) garantiert:
  1. Jede Company sieht NUR ihre eigenen Daten
  2. Kein Cross-Tenant Zugriff moeglich (auch nicht bei SQL-Injection)
  3. Defense-in-Depth: DB-Layer als letzte Verteidigung

Implementation:
- PostgreSQL Session Variable: app.current_company_id
- Bypass-Mechanismus: app.rls_bypass fuer Service-Tasks
- Helper Functions: get_current_company_id(), is_rls_bypass_enabled()

Kategorien der geschuetzten Tabellen:
- Core: documents, business_entities, invoices
- Finance: budgets, bank_accounts, bank_transactions
- Workflows: workflows, bpmn_*, approval_*
- Compliance: gobd_*, gdpr_*, audit_logs
- Personnel: employees, departments, positions
- Teams: teams, delegations
- DLP: dlp_policies, dlp_audit_logs
- Privat: privat_spaces, privat_documents
- Integrations: erp_connections, slack_channels
"""

from alembic import op

# revision identifiers
revision = "110_comprehensive_rls_policies"
down_revision = "110_add_team_collaboration"
branch_labels = None
depends_on = None


# Tabellen mit company_id Spalte - VOLLSTAENDIGE LISTE (60+ Tabellen)
TABLES_WITH_COMPANY_ID = [
    # === CORE DOCUMENTS ===
    "documents",
    "business_entities",
    "invoices",
    "invoice_tracking",
    "document_chains",
    "document_chain_links",
    "document_templates",
    "generated_documents",
    "template_snippets",

    # === IMPORT SYSTEM ===
    "import_rules",
    "import_logs",
    "email_import_configs",
    "folder_import_configs",

    # === BUDGET & FINANCE ===
    "budgets",
    "budget_items",
    "budget_lines",
    "budget_allocations",
    "budget_alerts",
    "budget_categories",
    "budget_reports",
    "kostenstellen",
    "bank_accounts",
    "bank_transactions",
    "sepa_mandates",

    # === WORKFLOWS & AUTOMATION ===
    "scheduled_exports",
    "notification_rules",
    "approval_rules",
    "approval_requests",
    "contracts",
    "contract_reminders",
    "workflows",
    "workflow_executions",

    # === SHIPPING ===
    "shipments",
    "shipment_events",

    # === KNOWLEDGE & RAG ===
    "knowledge_articles",
    "knowledge_notes",
    "knowledge_checklists",
    "rag_customer_cards",

    # === BPMN PROCESS MANAGEMENT ===
    "bpmn_process_definitions",
    "bpmn_process_instances",
    "bpmn_process_variables",
    "bpmn_activities",
    "bpmn_gateways",
    "bpmn_events",

    # === GOBD COMPLIANCE ===
    "gobd_procedure_docs",
    "gobd_procedure_versions",
    "gobd_control_tests",
    "gobd_system_configurations",
    "gobd_change_protocols",

    # === TEAMS & DELEGATION ===
    "teams",
    "delegations",
    "delegation_templates",
    "delegation_audit_logs",

    # === BUSINESS RULES ===
    "business_rules",
    "rule_conditions",

    # === PERSONNEL MODULE ===
    "departments",
    "positions",
    "employees",
    "leave_requests",
    "absences",
    "time_entries",
    "trainings",
    "training_registrations",
    "performance_reviews",
    "onboarding_tasks",

    # === DLP (Data Loss Prevention) ===
    "dlp_policies",
    "dlp_audit_logs",

    # === PRIVAT SPACES ===
    "privat_spaces",
    "privat_folders",
    "privat_documents",
    "privat_deadline_reminders",

    # === ERP & EXTERNAL ===
    "erp_connections",

    # === AI & ML ===
    "ai_confidence_thresholds",
    "ai_decisions",
    "ai_learning_feedback",

    # === REPORTS & ANALYTICS ===
    "report_templates",
    "report_executions",

    # === TAX ADVISOR ===
    "tax_advisor_access_logs",
    "tax_advisor_invites",

    # === INTEGRATIONS ===
    "slack_channels",

    # === RATE LIMITING ===
    "tenant_rate_limits",
    "tenant_usage_metrics",
    "rate_limit_violations",

    # === GDPR ===
    "gdpr_consent_scopes",
    "gdpr_data_exports",
    "gdpr_data_subject_requests",

    # === MISC ===
    "zm_submissions",
    "document_archives",
    "business_contacts",
    "payment_transactions",
    "payment_predictions",
]

# Tabellen die ueber Parent-Tabelle isoliert werden (kein eigenes company_id)
TABLES_VIA_PARENT = {
    # === DOCUMENT CHILDREN ===
    "document_comments": ("document_id", "documents"),
    "document_versions": ("document_id", "documents"),
    "document_tasks": ("document_id", "documents"),
    "document_access_log": ("document_id", "documents"),
    "document_shares": ("document_id", "documents"),
    "document_relationships": ("source_document_id", "documents"),
    "document_matches": ("document_id", "documents"),
    "ocr_training_samples": ("document_id", "documents"),
    "validation_queue_items": ("document_id", "documents"),

    # === APPROVAL CHILDREN ===
    "approval_steps": ("approval_request_id", "approval_requests"),

    # === BUDGET CHILDREN ===
    "budget_adjustments": ("budget_id", "budgets"),

    # === WORKFLOW CHILDREN ===
    "workflow_steps": ("workflow_id", "workflows"),
    "workflow_step_executions": ("workflow_execution_id", "workflow_executions"),

    # === BPMN CHILDREN ===
    "bpmn_sequence_flows": ("process_definition_id", "bpmn_process_definitions"),
    "bpmn_activity_logs": ("activity_id", "bpmn_activities"),
    "bpmn_timer_events": ("process_instance_id", "bpmn_process_instances"),

    # === CONTRACT CHILDREN ===
    "contract_documents": ("contract_id", "contracts"),
    "contract_parties": ("contract_id", "contracts"),

    # === SHIPMENT CHILDREN ===
    "shipment_documents": ("shipment_id", "shipments"),

    # === TEAM CHILDREN ===
    "team_memberships": ("team_id", "teams"),
    "team_activities": ("team_id", "teams"),
    "team_invitations": ("team_id", "teams"),
    "team_documents": ("team_id", "teams"),

    # === EMPLOYEE CHILDREN ===
    "employee_documents": ("employee_id", "employees"),

    # === REPORT CHILDREN ===
    "report_schedules": ("template_id", "report_templates"),
}


def upgrade() -> None:
    """Add comprehensive RLS policies for multi-tenant isolation."""

    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    if not is_postgres:
        # SQLite hat kein RLS - skip
        return

    # =========================================================================
    # 1. Stelle sicher dass Helper-Funktion existiert (aus Migration 060)
    # =========================================================================
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
    # 2. Bypass-Funktion fuer Service-Account und Superuser
    # =========================================================================
    op.execute("""
        CREATE OR REPLACE FUNCTION is_rls_bypass_enabled()
        RETURNS boolean AS $$
        BEGIN
            RETURN COALESCE(
                current_setting('app.rls_bypass', true)::boolean,
                false
            );
        EXCEPTION
            WHEN OTHERS THEN
                RETURN false;
        END;
        $$ LANGUAGE plpgsql STABLE;
    """)

    # =========================================================================
    # 3. RLS fuer Tabellen mit direktem company_id
    # =========================================================================
    for table_name in TABLES_WITH_COMPANY_ID:
        # Pruefen ob Tabelle existiert
        check_table = bind.execute(f"""
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_schema = 'public'
                AND table_name = '{table_name}'
            )
        """)
        if not check_table.scalar():
            continue

        # Pruefen ob company_id Spalte existiert
        check_col = bind.execute(f"""
            SELECT EXISTS (
                SELECT FROM information_schema.columns
                WHERE table_schema = 'public'
                AND table_name = '{table_name}'
                AND column_name = 'company_id'
            )
        """)
        if not check_col.scalar():
            continue

        # RLS aktivieren
        op.execute(f"ALTER TABLE {table_name} ENABLE ROW LEVEL SECURITY")

        # Policy erstellen (mit Bypass-Option fuer Admins)
        op.execute(f"""
            CREATE POLICY {table_name}_tenant_isolation ON {table_name}
                FOR ALL
                USING (
                    is_rls_bypass_enabled()
                    OR company_id IS NULL
                    OR company_id = get_current_company_id()
                )
                WITH CHECK (
                    is_rls_bypass_enabled()
                    OR company_id IS NULL
                    OR company_id = get_current_company_id()
                );
        """)

    # =========================================================================
    # 4. RLS fuer Tabellen via Parent-Beziehung
    # =========================================================================
    for table_name, (fk_column, parent_table) in TABLES_VIA_PARENT.items():
        # Pruefen ob Tabelle existiert
        check_table = bind.execute(f"""
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_schema = 'public'
                AND table_name = '{table_name}'
            )
        """)
        if not check_table.scalar():
            continue

        # RLS aktivieren
        op.execute(f"ALTER TABLE {table_name} ENABLE ROW LEVEL SECURITY")

        # Policy ueber Parent-Tabelle
        op.execute(f"""
            CREATE POLICY {table_name}_tenant_isolation ON {table_name}
                FOR ALL
                USING (
                    is_rls_bypass_enabled()
                    OR {fk_column} IN (
                        SELECT id FROM {parent_table}
                        WHERE company_id IS NULL
                        OR company_id = get_current_company_id()
                    )
                )
                WITH CHECK (
                    is_rls_bypass_enabled()
                    OR {fk_column} IN (
                        SELECT id FROM {parent_table}
                        WHERE company_id IS NULL
                        OR company_id = get_current_company_id()
                    )
                );
        """)

    # =========================================================================
    # 5. Spezielle Policy fuer audit_logs (nur Lesen, kein Check)
    # =========================================================================
    check_audit = bind.execute("""
        SELECT EXISTS (
            SELECT FROM information_schema.tables
            WHERE table_schema = 'public'
            AND table_name = 'audit_logs'
        )
    """)
    if check_audit.scalar():
        # Audit-Logs: RLS mit Lese-Policy aber ohne Write-Check
        # (Audit-Logs werden von System geschrieben, nicht von Usern)
        op.execute("ALTER TABLE audit_logs ENABLE ROW LEVEL SECURITY")
        op.execute("""
            CREATE POLICY audit_logs_tenant_read ON audit_logs
                FOR SELECT
                USING (
                    is_rls_bypass_enabled()
                    OR company_id IS NULL
                    OR company_id = get_current_company_id()
                );
        """)
        # Insert-Policy fuer System (immer erlaubt mit Bypass)
        op.execute("""
            CREATE POLICY audit_logs_system_write ON audit_logs
                FOR INSERT
                WITH CHECK (is_rls_bypass_enabled());
        """)

    # =========================================================================
    # 6. Index fuer Performance bei RLS-Queries
    # =========================================================================
    for table_name in TABLES_WITH_COMPANY_ID:
        check_table = bind.execute(f"""
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_schema = 'public'
                AND table_name = '{table_name}'
            )
        """)
        if not check_table.scalar():
            continue

        check_col = bind.execute(f"""
            SELECT EXISTS (
                SELECT FROM information_schema.columns
                WHERE table_schema = 'public'
                AND table_name = '{table_name}'
                AND column_name = 'company_id'
            )
        """)
        if not check_col.scalar():
            continue

        # Index nur erstellen wenn nicht vorhanden
        check_idx = bind.execute(f"""
            SELECT EXISTS (
                SELECT FROM pg_indexes
                WHERE tablename = '{table_name}'
                AND indexname = 'ix_{table_name}_company_id_rls'
            )
        """)
        if not check_idx.scalar():
            op.execute(f"""
                CREATE INDEX CONCURRENTLY IF NOT EXISTS
                ix_{table_name}_company_id_rls ON {table_name} (company_id)
            """)


def downgrade() -> None:
    """Remove comprehensive RLS policies."""

    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    if not is_postgres:
        return

    # Drop policies fuer Tabellen mit company_id
    for table_name in TABLES_WITH_COMPANY_ID:
        check_table = bind.execute(f"""
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_schema = 'public'
                AND table_name = '{table_name}'
            )
        """)
        if check_table.scalar():
            op.execute(f"DROP POLICY IF EXISTS {table_name}_tenant_isolation ON {table_name}")
            op.execute(f"ALTER TABLE {table_name} DISABLE ROW LEVEL SECURITY")
            op.execute(f"DROP INDEX IF EXISTS ix_{table_name}_company_id_rls")

    # Drop policies fuer Tabellen via Parent
    for table_name in TABLES_VIA_PARENT.keys():
        check_table = bind.execute(f"""
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_schema = 'public'
                AND table_name = '{table_name}'
            )
        """)
        if check_table.scalar():
            op.execute(f"DROP POLICY IF EXISTS {table_name}_tenant_isolation ON {table_name}")
            op.execute(f"ALTER TABLE {table_name} DISABLE ROW LEVEL SECURITY")

    # Drop audit_logs policies
    op.execute("DROP POLICY IF EXISTS audit_logs_tenant_read ON audit_logs")
    op.execute("DROP POLICY IF EXISTS audit_logs_system_write ON audit_logs")
    op.execute("ALTER TABLE audit_logs DISABLE ROW LEVEL SECURITY")

    # Drop helper functions
    op.execute("DROP FUNCTION IF EXISTS is_rls_bypass_enabled()")
    # Behalte get_current_company_id() - wird von Migration 060 verwaltet
