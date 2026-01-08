# -*- coding: utf-8 -*-
"""Add Workflow-Automation tables.

Revision ID: 079_add_workflow_automation
Revises: 078_add_report_builder
Create Date: 2026-01-03

Workflow-Automation-Infrastruktur:
- workflows: Workflow-Definitionen mit Trigger-Config und ReactFlow-Nodes
- workflow_steps: Einzelne Schritte pro Workflow (Condition, Action, Branch, etc.)
- workflow_executions: Ausfuehrungs-Historie
- workflow_step_executions: Schritt-Level Audit Trail
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "079"
down_revision = "078"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add Workflow-Automation tables."""

    # Check dialect
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    if is_postgres:
        uuid_type = postgresql.UUID(as_uuid=True)
        json_type = postgresql.JSONB
        uuid_default = sa.text("gen_random_uuid()")
    else:
        uuid_type = sa.String(36)
        json_type = sa.JSON
        uuid_default = None

    # =========================================================================
    # 1. WORKFLOWS - Workflow-Definitionen
    # =========================================================================
    op.create_table(
        "workflows",
        sa.Column("id", uuid_type, primary_key=True, server_default=uuid_default),
        sa.Column("user_id", uuid_type, nullable=False),
        sa.Column("company_id", uuid_type, nullable=True),  # Optional: Multi-Tenant

        # Basis-Informationen
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("is_active", sa.Boolean, default=True, nullable=False),

        # Template-Funktion
        sa.Column("is_template", sa.Boolean, default=False, nullable=False),
        sa.Column("template_category", sa.String(50), nullable=True),
        # Categories: document, finance, notification, reporting, approval

        # Trigger-Konfiguration
        sa.Column("trigger_type", sa.String(30), nullable=False),
        # Types: document_event, schedule, condition, manual, webhook
        sa.Column("trigger_config", json_type, nullable=False, server_default="{}"),
        # document_event: {"events": ["created", "processed"], "folder_ids": [], "document_types": []}
        # schedule: {"cron": "0 9 * * *", "timezone": "Europe/Berlin"}
        # condition: {"field": "status", "operator": "equals", "value": "processed"}
        # webhook: {"secret": "...", "path": "/trigger/workflow-name"}

        # ReactFlow Graph Definition
        sa.Column("nodes", json_type, nullable=False, server_default="[]"),
        sa.Column("edges", json_type, nullable=False, server_default="[]"),
        sa.Column("variables", json_type, nullable=True),  # Workflow-Variablen

        # Webhook-Trigger Secret (nur fuer trigger_type=webhook)
        sa.Column("webhook_secret", sa.String(64), nullable=True),
        sa.Column("webhook_path", sa.String(100), nullable=True),

        # Ausfuehrungs-Einstellungen
        sa.Column("max_concurrent_executions", sa.Integer, default=10, nullable=False),
        sa.Column("timeout_seconds", sa.Integer, default=3600, nullable=False),
        sa.Column("retry_config", json_type, nullable=True),
        # retry_config: {"max_retries": 3, "backoff_seconds": 60}
        sa.Column("error_handling", sa.String(20), default="stop", nullable=False),
        # Error handling: stop, continue, rollback
        sa.Column("enable_audit_log", sa.Boolean, default=True, nullable=False),

        # Statistiken
        sa.Column("execution_count", sa.Integer, default=0, nullable=False),
        sa.Column("success_count", sa.Integer, default=0, nullable=False),
        sa.Column("failure_count", sa.Integer, default=0, nullable=False),
        sa.Column("last_executed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("avg_execution_time_ms", sa.Integer, nullable=True),

        # Naechste geplante Ausfuehrung (nur fuer trigger_type=schedule)
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=True),

        # Audit
        sa.Column("created_by_id", uuid_type, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),

        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="SET NULL"),
    )

    op.create_index("ix_workflows_user_id", "workflows", ["user_id"])
    op.create_index("ix_workflows_company_id", "workflows", ["company_id"])
    op.create_index("ix_workflows_is_active", "workflows", ["is_active"])
    op.create_index("ix_workflows_trigger_type", "workflows", ["trigger_type"])
    op.create_index("ix_workflows_is_template", "workflows", ["is_template"])
    op.create_index("ix_workflows_template_category", "workflows", ["template_category"])
    op.create_index("ix_workflows_next_run_at", "workflows", ["next_run_at"])
    op.create_index(
        "ix_workflows_webhook_path",
        "workflows",
        ["webhook_path"],
        unique=True,
        postgresql_where=sa.text("webhook_path IS NOT NULL") if is_postgres else None,
    )

    # =========================================================================
    # 2. WORKFLOW_STEPS - Einzelne Schritte pro Workflow
    # =========================================================================
    op.create_table(
        "workflow_steps",
        sa.Column("id", uuid_type, primary_key=True, server_default=uuid_default),
        sa.Column("workflow_id", uuid_type, nullable=False),

        # Basis-Informationen
        sa.Column("step_order", sa.Integer, nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=True),

        # Step-Typ
        sa.Column("step_type", sa.String(30), nullable=False),
        # Types: condition, action, branch, delay, parallel, loop

        # Step-Konfiguration (JSONB)
        sa.Column("config", json_type, nullable=False, server_default="{}"),
        # condition: Wiederverwendet ImportRule Format
        # action: {"action_type": "move_folder", "params": {"folder_id": "..."}}
        # branch: {"true_step_id": "...", "false_step_id": "..."}
        # delay: {"delay_seconds": 300, "delay_until": "next_business_day"}
        # parallel: {"parallel_step_ids": ["...", "..."]}

        # Retry/Error Handling
        sa.Column("retry_on_failure", sa.Boolean, default=True, nullable=False),
        sa.Column("max_retries", sa.Integer, default=3, nullable=False),
        sa.Column("retry_backoff_seconds", sa.Integer, default=60, nullable=False),
        sa.Column("continue_on_error", sa.Boolean, default=False, nullable=False),
        sa.Column("fallback_step_id", uuid_type, nullable=True),

        # ReactFlow Position
        sa.Column("position_x", sa.Float, nullable=True),
        sa.Column("position_y", sa.Float, nullable=True),
        sa.Column("node_data", json_type, nullable=True),  # Zusaetzliche ReactFlow Daten

        # Audit
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),

        sa.ForeignKeyConstraint(["workflow_id"], ["workflows.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["fallback_step_id"], ["workflow_steps.id"], ondelete="SET NULL"),
    )

    op.create_index("ix_workflow_steps_workflow_id", "workflow_steps", ["workflow_id"])
    op.create_index("ix_workflow_steps_step_type", "workflow_steps", ["step_type"])
    op.create_index("ix_workflow_steps_step_order", "workflow_steps", ["workflow_id", "step_order"])

    # =========================================================================
    # 3. WORKFLOW_EXECUTIONS - Ausfuehrungs-Historie
    # =========================================================================
    op.create_table(
        "workflow_executions",
        sa.Column("id", uuid_type, primary_key=True, server_default=uuid_default),
        sa.Column("workflow_id", uuid_type, nullable=False),
        sa.Column("company_id", uuid_type, nullable=True),

        # Wer hat ausgeloest
        sa.Column("triggered_by_id", uuid_type, nullable=True),  # NULL = automatisch

        # Trigger-Kontext
        sa.Column("trigger_type", sa.String(30), nullable=False),
        sa.Column("trigger_source", sa.String(255), nullable=True),
        # Beispiel: "document:abc123", "schedule:daily_9am", "webhook:external_system"
        sa.Column("trigger_data", json_type, nullable=True),  # Kontext-Daten
        sa.Column("document_id", uuid_type, nullable=True),  # Optional: Ausloesendes Dokument

        # Ausfuehrungs-Status
        sa.Column("status", sa.String(20), nullable=False, default="pending"),
        # Status: pending, running, completed, failed, cancelled, paused
        sa.Column("current_step_id", uuid_type, nullable=True),
        sa.Column("progress_percent", sa.Integer, default=0, nullable=False),

        # Ergebnisse
        sa.Column("result", json_type, nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("error_code", sa.String(50), nullable=True),
        sa.Column("error_step_id", uuid_type, nullable=True),

        # Timing
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.Integer, nullable=True),

        # Celery-Integration
        sa.Column("celery_task_id", sa.String(100), nullable=True),
        sa.Column("retry_count", sa.Integer, default=0, nullable=False),

        # Runtime-Variablen
        sa.Column("variables", json_type, nullable=True),

        # Audit
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),

        sa.ForeignKeyConstraint(["workflow_id"], ["workflows.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["triggered_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["current_step_id"], ["workflow_steps.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["error_step_id"], ["workflow_steps.id"], ondelete="SET NULL"),
    )

    op.create_index("ix_workflow_executions_workflow_id", "workflow_executions", ["workflow_id"])
    op.create_index("ix_workflow_executions_status", "workflow_executions", ["status"])
    op.create_index("ix_workflow_executions_document_id", "workflow_executions", ["document_id"])
    op.create_index("ix_workflow_executions_started_at", "workflow_executions", ["started_at"])
    op.create_index("ix_workflow_executions_trigger_type", "workflow_executions", ["trigger_type"])
    op.create_index("ix_workflow_executions_company_id", "workflow_executions", ["company_id"])
    op.create_index(
        "ix_workflow_executions_running",
        "workflow_executions",
        ["workflow_id", "status"],
        postgresql_where=sa.text("status = 'running'") if is_postgres else None,
    )

    # =========================================================================
    # 4. WORKFLOW_STEP_EXECUTIONS - Schritt-Level Audit Trail
    # =========================================================================
    op.create_table(
        "workflow_step_executions",
        sa.Column("id", uuid_type, primary_key=True, server_default=uuid_default),
        sa.Column("workflow_execution_id", uuid_type, nullable=False),
        sa.Column("workflow_step_id", uuid_type, nullable=False),

        # Ausfuehrungs-Reihenfolge
        sa.Column("execution_order", sa.Integer, nullable=False),

        # Status
        sa.Column("status", sa.String(20), nullable=False, default="pending"),
        # Status: pending, running, completed, failed, skipped

        # Input/Output
        sa.Column("input_data", json_type, nullable=True),
        sa.Column("output_data", json_type, nullable=True),

        # Fehler-Details
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("error_code", sa.String(50), nullable=True),
        sa.Column("error_details", json_type, nullable=True),

        # Timing
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.Integer, nullable=True),

        # Retry-Info
        sa.Column("retry_attempt", sa.Integer, default=0, nullable=False),
        sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True),

        # Branch-Entscheidung (fuer branch-Steps)
        sa.Column("branch_result", sa.Boolean, nullable=True),
        sa.Column("branch_reason", sa.Text, nullable=True),

        # Audit
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),

        sa.ForeignKeyConstraint(["workflow_execution_id"], ["workflow_executions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workflow_step_id"], ["workflow_steps.id"], ondelete="CASCADE"),
    )

    op.create_index("ix_workflow_step_execs_execution_id", "workflow_step_executions", ["workflow_execution_id"])
    op.create_index("ix_workflow_step_execs_step_id", "workflow_step_executions", ["workflow_step_id"])
    op.create_index("ix_workflow_step_execs_status", "workflow_step_executions", ["status"])
    op.create_index("ix_workflow_step_execs_order", "workflow_step_executions", ["workflow_execution_id", "execution_order"])

    # =========================================================================
    # 5. DEFAULT WORKFLOW TEMPLATES - Prebuilt Templates
    # =========================================================================
    if is_postgres:
        # Erstelle System-User-Referenz (falls nicht existiert)
        # Templates sind oeffentlich und nicht an einen User gebunden
        op.execute("""
            INSERT INTO workflows (
                id, user_id, name, description, is_active, is_template, template_category,
                trigger_type, trigger_config, nodes, edges, max_concurrent_executions, timeout_seconds
            )
            SELECT
                gen_random_uuid(),
                (SELECT id FROM users LIMIT 1),  -- Erster Admin als Owner
                'Auto-Kategorisierung',
                'Kategorisiert neue Dokumente automatisch mit KI und benachrichtigt bei niedriger Konfidenz',
                false,  -- Templates sind inaktiv bis instanziiert
                true,   -- Ist Template
                'document',
                'document_event',
                '{"events": ["processed"], "document_types": []}'::jsonb,
                '[
                    {"id": "trigger-1", "type": "trigger", "position": {"x": 100, "y": 100}, "data": {"label": "Dokument verarbeitet"}},
                    {"id": "action-1", "type": "action", "position": {"x": 100, "y": 200}, "data": {"action_type": "ai_categorization"}},
                    {"id": "branch-1", "type": "branch", "position": {"x": 100, "y": 300}, "data": {"condition": {"field": "ai_confidence", "operator": "less_than", "value": 0.8}}},
                    {"id": "action-2", "type": "action", "position": {"x": 200, "y": 400}, "data": {"action_type": "send_notification", "params": {"type": "warning", "title": "Manuelle Kategorisierung erforderlich"}}}
                ]'::jsonb,
                '[
                    {"id": "e1", "source": "trigger-1", "target": "action-1"},
                    {"id": "e2", "source": "action-1", "target": "branch-1"},
                    {"id": "e3", "source": "branch-1", "target": "action-2", "sourceHandle": "true"}
                ]'::jsonb,
                10,
                3600
            WHERE EXISTS (SELECT 1 FROM users LIMIT 1)
            ON CONFLICT DO NOTHING;
        """)

        op.execute("""
            INSERT INTO workflows (
                id, user_id, name, description, is_active, is_template, template_category,
                trigger_type, trigger_config, nodes, edges, max_concurrent_executions, timeout_seconds
            )
            SELECT
                gen_random_uuid(),
                (SELECT id FROM users LIMIT 1),
                'Rechnungsverarbeitung',
                'OCR mit DeepSeek Backend, Extraktion, Pruefung bei hohen Betraegen',
                false,
                true,
                'finance',
                'condition',
                '{"field": "document_type", "operator": "equals", "value": "invoice"}'::jsonb,
                '[
                    {"id": "trigger-1", "type": "trigger", "position": {"x": 100, "y": 100}, "data": {"label": "Rechnung erkannt"}},
                    {"id": "action-1", "type": "action", "position": {"x": 100, "y": 200}, "data": {"action_type": "start_ocr", "params": {"backend": "deepseek"}}},
                    {"id": "action-2", "type": "action", "position": {"x": 100, "y": 300}, "data": {"action_type": "extract_invoice_data"}},
                    {"id": "branch-1", "type": "branch", "position": {"x": 100, "y": 400}, "data": {"condition": {"field": "total_gross", "operator": "greater_than", "value": 5000}}},
                    {"id": "action-3", "type": "action", "position": {"x": 200, "y": 500}, "data": {"action_type": "send_notification", "params": {"type": "info", "title": "Grosse Rechnung zur Pruefung"}}}
                ]'::jsonb,
                '[
                    {"id": "e1", "source": "trigger-1", "target": "action-1"},
                    {"id": "e2", "source": "action-1", "target": "action-2"},
                    {"id": "e3", "source": "action-2", "target": "branch-1"},
                    {"id": "e4", "source": "branch-1", "target": "action-3", "sourceHandle": "true"}
                ]'::jsonb,
                10,
                7200
            WHERE EXISTS (SELECT 1 FROM users LIMIT 1)
            ON CONFLICT DO NOTHING;
        """)

        op.execute("""
            INSERT INTO workflows (
                id, user_id, name, description, is_active, is_template, template_category,
                trigger_type, trigger_config, nodes, edges, max_concurrent_executions, timeout_seconds
            )
            SELECT
                gen_random_uuid(),
                (SELECT id FROM users LIMIT 1),
                'Woechentlicher Dokumentbericht',
                'Generiert jeden Montag um 09:00 einen Wochenbericht und sendet ihn per E-Mail',
                false,
                true,
                'reporting',
                'schedule',
                '{"cron": "0 9 * * 1", "timezone": "Europe/Berlin"}'::jsonb,
                '[
                    {"id": "trigger-1", "type": "trigger", "position": {"x": 100, "y": 100}, "data": {"label": "Montag 09:00"}},
                    {"id": "action-1", "type": "action", "position": {"x": 100, "y": 200}, "data": {"action_type": "generate_report", "params": {"report_type": "weekly_document_summary", "format": "pdf"}}},
                    {"id": "action-2", "type": "action", "position": {"x": 100, "y": 300}, "data": {"action_type": "send_email", "params": {"to_variable": "report_recipients", "subject": "Woechentlicher Dokumentbericht"}}}
                ]'::jsonb,
                '[
                    {"id": "e1", "source": "trigger-1", "target": "action-1"},
                    {"id": "e2", "source": "action-1", "target": "action-2"}
                ]'::jsonb,
                1,
                1800
            WHERE EXISTS (SELECT 1 FROM users LIMIT 1)
            ON CONFLICT DO NOTHING;
        """)

        op.execute("""
            INSERT INTO workflows (
                id, user_id, name, description, is_active, is_template, template_category,
                trigger_type, trigger_config, nodes, edges, max_concurrent_executions, timeout_seconds
            )
            SELECT
                gen_random_uuid(),
                (SELECT id FROM users LIMIT 1),
                'Duplikat-Erkennung',
                'Prueft neue Dokumente auf Duplikate und archiviert diese automatisch',
                false,
                true,
                'document',
                'document_event',
                '{"events": ["created"], "document_types": []}'::jsonb,
                '[
                    {"id": "trigger-1", "type": "trigger", "position": {"x": 100, "y": 100}, "data": {"label": "Dokument erstellt"}},
                    {"id": "action-1", "type": "action", "position": {"x": 100, "y": 200}, "data": {"action_type": "check_duplicate"}},
                    {"id": "branch-1", "type": "branch", "position": {"x": 100, "y": 300}, "data": {"condition": {"field": "is_duplicate", "operator": "equals", "value": true}}},
                    {"id": "action-2", "type": "action", "position": {"x": 200, "y": 400}, "data": {"action_type": "move_folder", "params": {"folder_name": "Duplikate"}}},
                    {"id": "action-3", "type": "action", "position": {"x": 200, "y": 500}, "data": {"action_type": "send_notification", "params": {"type": "warning", "title": "Duplikat gefunden"}}}
                ]'::jsonb,
                '[
                    {"id": "e1", "source": "trigger-1", "target": "action-1"},
                    {"id": "e2", "source": "action-1", "target": "branch-1"},
                    {"id": "e3", "source": "branch-1", "target": "action-2", "sourceHandle": "true"},
                    {"id": "e4", "source": "action-2", "target": "action-3"}
                ]'::jsonb,
                10,
                1800
            WHERE EXISTS (SELECT 1 FROM users LIMIT 1)
            ON CONFLICT DO NOTHING;
        """)

        op.execute("""
            INSERT INTO workflows (
                id, user_id, name, description, is_active, is_template, template_category,
                trigger_type, trigger_config, nodes, edges, max_concurrent_executions, timeout_seconds
            )
            SELECT
                gen_random_uuid(),
                (SELECT id FROM users LIMIT 1),
                'Genehmigungsworkflow',
                'Weist Dokumente einem Benutzer zur Genehmigung zu und wartet auf Rueckmeldung',
                false,
                true,
                'approval',
                'document_event',
                '{"events": ["processed"], "document_types": ["contract", "invoice"]}'::jsonb,
                '[
                    {"id": "trigger-1", "type": "trigger", "position": {"x": 100, "y": 100}, "data": {"label": "Dokument verarbeitet"}},
                    {"id": "branch-1", "type": "branch", "position": {"x": 100, "y": 200}, "data": {"condition": {"field": "total_gross", "operator": "greater_than", "value": 1000}}},
                    {"id": "action-1", "type": "action", "position": {"x": 200, "y": 300}, "data": {"action_type": "assign_user", "params": {"user_variable": "approver_id"}}},
                    {"id": "action-2", "type": "action", "position": {"x": 200, "y": 400}, "data": {"action_type": "send_notification", "params": {"type": "info", "title": "Dokument zur Genehmigung", "to_variable": "approver_id"}}},
                    {"id": "action-3", "type": "action", "position": {"x": 200, "y": 500}, "data": {"action_type": "update_status", "params": {"status": "pending_approval"}}}
                ]'::jsonb,
                '[
                    {"id": "e1", "source": "trigger-1", "target": "branch-1"},
                    {"id": "e2", "source": "branch-1", "target": "action-1", "sourceHandle": "true"},
                    {"id": "e3", "source": "action-1", "target": "action-2"},
                    {"id": "e4", "source": "action-2", "target": "action-3"}
                ]'::jsonb,
                10,
                86400
            WHERE EXISTS (SELECT 1 FROM users LIMIT 1)
            ON CONFLICT DO NOTHING;
        """)


def downgrade() -> None:
    """Remove Workflow-Automation tables."""
    op.drop_table("workflow_step_executions")
    op.drop_table("workflow_executions")
    op.drop_table("workflow_steps")
    op.drop_table("workflows")
