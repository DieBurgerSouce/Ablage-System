"""Add DLP (Data Loss Prevention) tables.

Revision ID: 109_add_dlp_tables
Revises: 108_dashboard_enhancements
Create Date: 2026-01-20

Enterprise Security Feature:
- DLP Policies: Persistierte Policy-Definitionen pro Company
- DLP Audit Logs: Audit-Trail fuer alle DLP-Events
- Multi-Tenant Isolation via company_id

SECURITY:
- Alle Policies sind company-isoliert (Multi-Tenant)
- Audit-Logs sind immutable (keine Updates/Deletes)
- Sensitive Data wird NIEMALS geloggt
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "109_add_dlp_tables"
down_revision = "108_dashboard_enhancements"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ==========================================================================
    # DLP POLICIES TABLE
    # Persistiert DLP-Policies in der Datenbank
    # ==========================================================================
    op.create_table(
        "dlp_policies",
        # Primary Key
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),

        # Policy Identification
        sa.Column("policy_id", sa.String(64), nullable=False, index=True,
                  comment="Human-readable Policy-ID (z.B. 'confidential-docs')"),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, default=True, index=True),

        # Multi-Tenant (KRITISCH!)
        sa.Column("company_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("companies.id", ondelete="CASCADE"),
                  nullable=False, index=True,
                  comment="Mandanten-Zuordnung - PFLICHT fuer Isolation"),

        # Zugriffsbedingungen (JSONB)
        sa.Column("allowed_roles", postgresql.JSONB(),
                  server_default='["admin"]',
                  comment="Rollen die Zugriff haben"),
        sa.Column("blocked_roles", postgresql.JSONB(),
                  server_default='[]',
                  comment="Rollen die explizit blockiert sind"),

        # Zeit-basierte Einschraenkungen
        sa.Column("time_restrictions", postgresql.JSONB(), nullable=True,
                  comment="{'start': '09:00', 'end': '18:00', 'weekdays': [0-6]}"),

        # Dokument-Filter
        sa.Column("document_types", postgresql.JSONB(),
                  server_default='["all"]',
                  comment="Betroffene Dokumenttypen"),
        sa.Column("tags_required", postgresql.JSONB(),
                  server_default='[]',
                  comment="Dokument muss diese Tags haben"),
        sa.Column("tags_blocked", postgresql.JSONB(),
                  server_default='[]',
                  comment="Dokument darf diese Tags nicht haben"),

        # Aktionen
        sa.Column("action", sa.String(20), nullable=False, default="allow"),
        sa.Column("require_watermark", sa.Boolean(), nullable=False, default=False),
        sa.Column("watermark_config", postgresql.JSONB(), nullable=True,
                  comment="Wasserzeichen-Konfiguration"),

        # Benachrichtigungen
        sa.Column("notify_admin", sa.Boolean(), nullable=False, default=False),
        sa.Column("notify_user", sa.Boolean(), nullable=False, default=False),
        sa.Column("log_access", sa.Boolean(), nullable=False, default=True),

        # Prioritaet
        sa.Column("priority", sa.Integer(), nullable=False, default=100, index=True),

        # Audit
        sa.Column("created_by_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.text("CURRENT_TIMESTAMP"),
                  onupdate=sa.text("CURRENT_TIMESTAMP")),

        # Table Comment
        comment="DLP Policies fuer Enterprise Security"
    )

    # Unique Constraint: policy_id pro Company
    op.create_unique_constraint(
        "uq_dlp_policy_company_id",
        "dlp_policies",
        ["company_id", "policy_id"]
    )

    # Composite Indexes
    op.create_index(
        "ix_dlp_policies_company_enabled",
        "dlp_policies",
        ["company_id", "enabled"]
    )
    op.create_index(
        "ix_dlp_policies_company_priority",
        "dlp_policies",
        ["company_id", "priority"]
    )

    # ==========================================================================
    # DLP AUDIT LOGS TABLE
    # Immutable Audit-Trail fuer alle DLP-Events
    # ==========================================================================
    op.create_table(
        "dlp_audit_logs",
        # Primary Key
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),

        # Event-Kontext
        sa.Column("event_type", sa.String(50), nullable=False, index=True,
                  comment="access_check, policy_change, watermark_applied, sensitive_data_found"),
        sa.Column("action_type", sa.String(20), nullable=True,
                  comment="download, view, print, export"),

        # Ergebnis
        sa.Column("result", sa.String(20), nullable=False,
                  comment="allowed, blocked, watermarked, notified"),
        sa.Column("reason", sa.String(500), nullable=True),

        # Betroffene Entities
        sa.Column("user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL"),
                  nullable=True, index=True),
        sa.Column("document_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("documents.id", ondelete="SET NULL"),
                  nullable=True, index=True),
        sa.Column("policy_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("dlp_policies.id", ondelete="SET NULL"),
                  nullable=True),

        # Multi-Tenant (KRITISCH!)
        sa.Column("company_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("companies.id", ondelete="CASCADE"),
                  nullable=False, index=True,
                  comment="Mandanten-Zuordnung - PFLICHT"),

        # Sensitive Data Info (NUR Typen und Counts!)
        sa.Column("sensitive_data_types", postgresql.JSONB(), nullable=True,
                  comment="{'credit_card': 2, 'iban': 1} - NUR Counts!"),

        # Request-Kontext
        sa.Column("ip_address", sa.String(45), nullable=True),
        sa.Column("user_agent", sa.String(255), nullable=True),

        # Metadata
        sa.Column("metadata", postgresql.JSONB(),
                  server_default='{}'),

        # Timestamp (immutable)
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),

        # Table Comment
        comment="DLP Audit-Log fuer Compliance und Forensik"
    )

    # Composite Indexes fuer haeufige Queries
    op.create_index(
        "ix_dlp_audit_company_created",
        "dlp_audit_logs",
        ["company_id", "created_at"]
    )
    op.create_index(
        "ix_dlp_audit_company_event",
        "dlp_audit_logs",
        ["company_id", "event_type"]
    )
    op.create_index(
        "ix_dlp_audit_user_created",
        "dlp_audit_logs",
        ["user_id", "created_at"]
    )

    # ==========================================================================
    # IMMUTABILITY TRIGGER fuer DLP Audit Logs
    # Verhindert UPDATE und DELETE auf Audit-Logs
    # ==========================================================================
    op.execute("""
        CREATE OR REPLACE FUNCTION dlp_audit_immutable()
        RETURNS TRIGGER AS $$
        BEGIN
            IF TG_OP = 'UPDATE' THEN
                RAISE EXCEPTION 'DLP Audit-Logs koennen nicht geaendert werden (Immutable)';
            ELSIF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION 'DLP Audit-Logs koennen nicht geloescht werden (Immutable)';
            END IF;
            RETURN NULL;
        END;
        $$ LANGUAGE plpgsql;
    """)

    op.execute("""
        CREATE TRIGGER dlp_audit_immutable_trigger
        BEFORE UPDATE OR DELETE ON dlp_audit_logs
        FOR EACH ROW
        EXECUTE FUNCTION dlp_audit_immutable();
    """)


def downgrade() -> None:
    # Trigger entfernen
    op.execute("DROP TRIGGER IF EXISTS dlp_audit_immutable_trigger ON dlp_audit_logs;")
    op.execute("DROP FUNCTION IF EXISTS dlp_audit_immutable();")

    # Indexes entfernen
    op.drop_index("ix_dlp_audit_user_created", table_name="dlp_audit_logs")
    op.drop_index("ix_dlp_audit_company_event", table_name="dlp_audit_logs")
    op.drop_index("ix_dlp_audit_company_created", table_name="dlp_audit_logs")
    op.drop_index("ix_dlp_policies_company_priority", table_name="dlp_policies")
    op.drop_index("ix_dlp_policies_company_enabled", table_name="dlp_policies")

    # Constraint entfernen
    op.drop_constraint("uq_dlp_policy_company_id", "dlp_policies", type_="unique")

    # Tabellen entfernen
    op.drop_table("dlp_audit_logs")
    op.drop_table("dlp_policies")
