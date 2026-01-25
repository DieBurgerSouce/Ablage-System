"""Add Delegation tables.

Revision ID: 111_add_delegation_tables
Revises: 110_add_team_collaboration
Create Date: 2026-01-21

Phase 3.2 der Strategischen Roadmap:
- Delegations: Temporaere Rechte-Uebertragung
- DelegationAuditLogs: Nutzungs-Protokollierung
- DelegationTemplates: Wiederverwendbare Vorlagen

Use Cases:
- Urlaubsvertretung
- Krankheitsvertretung
- Projektbasierte Delegation
- Notfall-Zugriff

Multi-Tenant: Alle Tabellen company-isoliert.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "111_add_delegation_tables"
down_revision = "110_add_team_collaboration"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ==========================================================================
    # DELEGATIONS TABLE
    # Haupttabelle fuer temporaere Rechte-Uebertragung
    # ==========================================================================
    op.create_table(
        "delegations",
        # Primary Key
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),

        # Delegator & Delegate
        sa.Column("delegator_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"),
                  nullable=False, index=True,
                  comment="User der seine Rechte delegiert"),
        sa.Column("delegate_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"),
                  nullable=False, index=True,
                  comment="User der die Rechte erhaelt"),

        # Multi-Tenant (KRITISCH!)
        sa.Column("company_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("companies.id", ondelete="CASCADE"),
                  nullable=False, index=True),

        # Delegations-Typ
        sa.Column("delegation_type", sa.String(20), nullable=False, default="partial",
                  comment="full, partial, approval, read_only, emergency"),

        # Berechtigungen (bei PARTIAL)
        sa.Column("permissions", postgresql.JSONB(), nullable=True, default=[],
                  comment="Liste der delegierten Berechtigungen"),
        # Format: ["approvals:*", "documents:read", "documents:comment"]

        # Scope (Einschraenkung auf bestimmte Ressourcen)
        sa.Column("scope", postgresql.JSONB(), nullable=True, default={},
                  comment="Einschraenkung auf bestimmte Ressourcen"),
        # Format: {"folders": ["uuid1", "uuid2"], "tags": ["wichtig"]}

        # Zeitliche Begrenzung
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=False),

        # Status
        sa.Column("status", sa.String(20), nullable=False, default="pending",
                  comment="pending, active, expired, revoked, declined"),

        # Grund & Beschreibung
        sa.Column("reason", sa.String(50), nullable=False, default="other",
                  comment="vacation, illness, parental_leave, business_trip, project, training, other"),
        sa.Column("reason_text", sa.Text(), nullable=True, comment="Freitext-Begruendung"),
        sa.Column("notes", sa.Text(), nullable=True, comment="Interne Notizen"),

        # Bestaetigung
        sa.Column("requires_acceptance", sa.Boolean(), nullable=False, default=True,
                  comment="Muss Delegate bestaetigen?"),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("declined_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decline_reason", sa.Text(), nullable=True),

        # Widerruf
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_by_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL"),
                  nullable=True),
        sa.Column("revoke_reason", sa.Text(), nullable=True),

        # Benachrichtigungen
        sa.Column("notify_on_activation", sa.Boolean(), nullable=False, default=True),
        sa.Column("notify_on_expiry", sa.Boolean(), nullable=False, default=True),
        sa.Column("notify_on_usage", sa.Boolean(), nullable=False, default=False,
                  comment="Bei jeder Nutzung benachrichtigen"),

        # Nutzungsstatistik
        sa.Column("usage_count", sa.Integer(), nullable=False, default=0,
                  comment="Wie oft wurde die Delegation genutzt"),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),

        # Einschraenkungen
        sa.Column("max_approvals", sa.Integer(), nullable=True,
                  comment="Max. Anzahl Genehmigungen (NULL = unbegrenzt)"),
        sa.Column("max_amount", sa.Float(), nullable=True,
                  comment="Max. Betrag pro Genehmigung"),

        # Metadata
        sa.Column("metadata_json", postgresql.JSONB(), nullable=True, default={}),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
    )

    # Indexes fuer Delegations
    op.create_index("ix_delegation_company_status", "delegations", ["company_id", "status"])
    op.create_index("ix_delegation_delegator_active", "delegations", ["delegator_id", "status"])
    op.create_index("ix_delegation_delegate_active", "delegations", ["delegate_id", "status"])
    op.create_index("ix_delegation_validity", "delegations", ["valid_from", "valid_until"])

    # Check Constraints
    op.create_check_constraint(
        "ck_delegation_validity",
        "delegations",
        "valid_until > valid_from"
    )
    op.create_check_constraint(
        "ck_delegation_different_users",
        "delegations",
        "delegator_id != delegate_id"
    )

    # ==========================================================================
    # DELEGATION AUDIT LOGS TABLE
    # Protokollierung jeder Delegations-Nutzung
    # ==========================================================================
    op.create_table(
        "delegation_audit_logs",
        # Primary Key
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),

        # Delegation
        sa.Column("delegation_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("delegations.id", ondelete="CASCADE"),
                  nullable=False, index=True),

        # Aktion
        sa.Column("action", sa.String(100), nullable=False,
                  comment="z.B. approval:execute, document:read"),
        sa.Column("resource_type", sa.String(50), nullable=True,
                  comment="z.B. document, approval, invoice"),
        sa.Column("resource_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("resource_name", sa.String(255), nullable=True),

        # Ergebnis
        sa.Column("success", sa.Boolean(), nullable=False, default=True),
        sa.Column("error_message", sa.Text(), nullable=True),

        # Kontext
        sa.Column("details", postgresql.JSONB(), nullable=True, default={},
                  comment="Zusaetzliche Details wie amount, vendor, etc."),

        # Request-Info
        sa.Column("ip_address", sa.String(45), nullable=True),
        sa.Column("user_agent", sa.String(500), nullable=True),

        # Timestamp
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False, index=True),
    )

    # Indexes fuer Audit Logs
    op.create_index("ix_audit_delegation_created", "delegation_audit_logs",
                    ["delegation_id", "created_at"])
    op.create_index("ix_audit_action", "delegation_audit_logs",
                    ["action", "created_at"])

    # ==========================================================================
    # DELEGATION TEMPLATES TABLE
    # Wiederverwendbare Vorlagen fuer Standard-Delegationen
    # ==========================================================================
    op.create_table(
        "delegation_templates",
        # Primary Key
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),

        # Multi-Tenant
        sa.Column("company_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("companies.id", ondelete="CASCADE"),
                  nullable=False, index=True),

        # Template-Details
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),

        # Delegations-Einstellungen
        sa.Column("delegation_type", sa.String(20), nullable=False),
        sa.Column("permissions", postgresql.JSONB(), nullable=True, default=[]),
        sa.Column("scope", postgresql.JSONB(), nullable=True, default={}),

        # Default-Werte
        sa.Column("default_duration_days", sa.Integer(), nullable=False, default=14),
        sa.Column("requires_acceptance", sa.Boolean(), nullable=False, default=True),
        sa.Column("notify_on_activation", sa.Boolean(), nullable=False, default=True),
        sa.Column("notify_on_usage", sa.Boolean(), nullable=False, default=False),

        # Status
        sa.Column("is_active", sa.Boolean(), nullable=False, default=True),
        sa.Column("is_system", sa.Boolean(), nullable=False, default=False,
                  comment="System-Template (nicht loeschbar)"),

        # Metadata
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
    )

    # Unique Constraint: Template-Name pro Company
    op.create_unique_constraint(
        "uq_delegation_template_name",
        "delegation_templates",
        ["company_id", "name"]
    )

    # ==========================================================================
    # Standard-Templates einfuegen (System-Templates)
    # ==========================================================================
    # Note: Diese werden besser per Seed-Script eingefuegt, nicht in Migration
    # Da company_id bekannt sein muss


def downgrade() -> None:
    # Drop tables in reverse order
    op.drop_table("delegation_templates")
    op.drop_table("delegation_audit_logs")
    op.drop_table("delegations")
