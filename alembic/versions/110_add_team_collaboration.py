"""Add Team & Collaboration tables.

Revision ID: 110_add_team_collaboration
Revises: 109_add_dlp_tables
Create Date: 2026-01-21

Phase 3.1 der Strategischen Roadmap:
- Teams: Matrix-Team-Struktur (Departments, Projects)
- TeamMemberships: Mitgliedschaften mit Rollen
- TeamActivities: Aktivitaets-Tracking
- TeamInvitations: Einladungssystem
- TeamDocuments: Team-Dokument-Freigaben

Multi-Tenant: Alle Tabellen company-isoliert.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "110_add_team_collaboration"
down_revision = "109_add_dlp_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ==========================================================================
    # TEAMS TABLE
    # Matrix-Team-Struktur mit Hierarchie
    # ==========================================================================
    op.create_table(
        "teams",
        # Primary Key
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),

        # Identifikation
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("code", sa.String(50), nullable=True, index=True,
                  comment="Kurzcode (z.B. DEV, SALES)"),
        sa.Column("description", sa.Text(), nullable=True),

        # Team-Typ
        sa.Column("team_type", sa.String(50), nullable=False, default="department",
                  comment="department, project, working_group, committee, virtual"),

        # Hierarchie
        sa.Column("parent_team_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("teams.id", ondelete="SET NULL"),
                  nullable=True, index=True),
        sa.Column("level", sa.Integer(), nullable=False, default=0,
                  comment="Hierarchie-Ebene (0 = Root)"),
        sa.Column("path", sa.String(500), nullable=True,
                  comment="Materialized Path fuer schnelle Hierarchie-Queries"),

        # Multi-Tenant (KRITISCH!)
        sa.Column("company_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("companies.id", ondelete="CASCADE"),
                  nullable=False, index=True),

        # Status & Sichtbarkeit
        sa.Column("status", sa.String(20), nullable=False, default="active",
                  comment="active, inactive, archived, pending"),
        sa.Column("visibility", sa.String(20), nullable=False, default="company",
                  comment="public, private, company"),

        # Zeitliche Begrenzung (fuer Projektteams)
        sa.Column("start_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("end_date", sa.DateTime(timezone=True), nullable=True),

        # Einstellungen
        sa.Column("settings", postgresql.JSONB(), nullable=True, default={}),
        sa.Column("default_permissions", postgresql.JSONB(), nullable=True, default=[]),
        sa.Column("tags", postgresql.JSONB(), nullable=True, default=[]),

        # Kontaktinformationen
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("slack_channel", sa.String(100), nullable=True),
        sa.Column("external_id", sa.String(100), nullable=True),

        # Statistiken (cached)
        sa.Column("member_count", sa.Integer(), nullable=False, default=0),
        sa.Column("active_member_count", sa.Integer(), nullable=False, default=0),

        # Verantwortung
        sa.Column("created_by_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL"),
                  nullable=True),

        # Metadata
        sa.Column("metadata_json", postgresql.JSONB(), nullable=True, default={}),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
    )

    # Indexes fuer Teams
    op.create_index("ix_team_company_status", "teams", ["company_id", "status"])
    op.create_index("ix_team_company_type", "teams", ["company_id", "team_type"])
    op.create_index("ix_team_path", "teams", ["path"])

    # Unique Constraint: Code pro Company
    op.create_unique_constraint(
        "uq_team_company_code",
        "teams",
        ["company_id", "code"]
    )

    # ==========================================================================
    # TEAM MEMBERSHIPS TABLE
    # Mitgliedschaften mit Rollen und zeitlicher Begrenzung
    # ==========================================================================
    op.create_table(
        "team_memberships",
        # Primary Key
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),

        # Zuordnung
        sa.Column("team_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("teams.id", ondelete="CASCADE"),
                  nullable=False, index=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"),
                  nullable=False, index=True),

        # Rolle
        sa.Column("role", sa.String(20), nullable=False, default="member",
                  comment="member, lead, admin, deputy, observer"),

        # Zeitliche Begrenzung
        sa.Column("valid_from", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=True,
                  comment="NULL = unbegrenzt"),

        # Status
        sa.Column("is_active", sa.Boolean(), nullable=False, default=True),
        sa.Column("is_primary", sa.Boolean(), nullable=False, default=False,
                  comment="Hauptteam des Users"),

        # Zusaetzliche Berechtigungen
        sa.Column("additional_permissions", postgresql.JSONB(), nullable=True, default=[]),

        # Mitgliedschafts-Details
        sa.Column("title", sa.String(100), nullable=True,
                  comment="Funktion/Titel im Team"),
        sa.Column("department", sa.String(100), nullable=True,
                  comment="Herkunfts-Abteilung (bei Projektteams)"),
        sa.Column("allocation_percent", sa.Integer(), nullable=False, default=100,
                  comment="Prozentuale Zuordnung zum Team"),

        # Einladung/Beitritt
        sa.Column("invited_by_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL"),
                  nullable=True),
        sa.Column("invitation_status", sa.String(20), default="accepted"),
        sa.Column("invitation_sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("joined_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()")),

        # Benachrichtigungen
        sa.Column("notification_preferences", postgresql.JSONB(), nullable=True, default={}),

        # Audit
        sa.Column("reason", sa.Text(), nullable=True,
                  comment="Grund fuer Mitgliedschaft"),

        # Metadata
        sa.Column("metadata_json", postgresql.JSONB(), nullable=True, default={}),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("left_at", sa.DateTime(timezone=True), nullable=True,
                  comment="Wann Team verlassen"),
    )

    # Indexes fuer TeamMemberships
    op.create_index("ix_membership_user_active", "team_memberships",
                    ["user_id", "is_active"])
    op.create_index("ix_membership_team_role", "team_memberships",
                    ["team_id", "role"])
    op.create_index("ix_membership_valid", "team_memberships",
                    ["valid_from", "valid_until"])

    # Unique Constraint: Ein User pro Team
    op.create_unique_constraint(
        "uq_membership_team_user",
        "team_memberships",
        ["team_id", "user_id"]
    )

    # ==========================================================================
    # TEAM ACTIVITIES TABLE
    # Aktivitaets-Log fuer Activity Feed
    # ==========================================================================
    op.create_table(
        "team_activities",
        # Primary Key
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),

        # Team-Zuordnung
        sa.Column("team_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("teams.id", ondelete="CASCADE"),
                  nullable=False, index=True),

        # Aktivitaets-Typ
        sa.Column("activity_type", sa.String(50), nullable=False,
                  comment="member_joined, member_left, document_shared, etc."),

        # Actor (wer hat die Aktion ausgefuehrt)
        sa.Column("actor_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL"),
                  nullable=True, index=True),

        # Target
        sa.Column("target_user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL"),
                  nullable=True),
        sa.Column("target_document_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("documents.id", ondelete="SET NULL"),
                  nullable=True),
        sa.Column("target_entity_type", sa.String(50), nullable=True),
        sa.Column("target_entity_id", postgresql.UUID(as_uuid=True), nullable=True),

        # Beschreibung
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),

        # Details (strukturiert)
        sa.Column("details", postgresql.JSONB(), nullable=True, default={}),

        # Sichtbarkeit
        sa.Column("is_public", sa.Boolean(), nullable=False, default=True),
        sa.Column("visibility", sa.String(20), nullable=False, default="company"),

        # Mentions
        sa.Column("mentioned_user_ids", postgresql.JSONB(), nullable=True, default=[]),

        # Metadata
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False, index=True),
        sa.Column("ip_address", sa.String(45), nullable=True),
        sa.Column("user_agent", sa.String(500), nullable=True),
    )

    # Indexes fuer TeamActivities
    op.create_index("ix_activity_team_created", "team_activities",
                    ["team_id", "created_at"])
    op.create_index("ix_activity_actor_created", "team_activities",
                    ["actor_id", "created_at"])
    op.create_index("ix_activity_type_created", "team_activities",
                    ["activity_type", "created_at"])

    # ==========================================================================
    # TEAM INVITATIONS TABLE
    # Einladungen zu Teams
    # ==========================================================================
    op.create_table(
        "team_invitations",
        # Primary Key
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),

        # Team-Zuordnung
        sa.Column("team_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("teams.id", ondelete="CASCADE"),
                  nullable=False, index=True),

        # Einladender
        sa.Column("invited_by_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL"),
                  nullable=True),

        # Eingeladener
        sa.Column("user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL"),
                  nullable=True, index=True),
        sa.Column("email", sa.String(255), nullable=True, index=True,
                  comment="Fuer externe Einladungen"),

        # Geplante Rolle
        sa.Column("role", sa.String(20), nullable=False, default="member"),

        # Status
        sa.Column("status", sa.String(20), nullable=False, default="pending",
                  comment="pending, accepted, declined, expired, cancelled"),

        # Token fuer Einladungs-Link
        sa.Column("token", sa.String(100), unique=True, nullable=False, index=True),

        # Zeitliche Begrenzung
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),

        # Nachricht
        sa.Column("personal_message", sa.Text(), nullable=True),

        # Response
        sa.Column("responded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decline_reason", sa.Text(), nullable=True),

        # Metadata
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
    )

    # Indexes fuer TeamInvitations
    op.create_index("ix_invitation_team_status", "team_invitations",
                    ["team_id", "status"])

    # ==========================================================================
    # TEAM DOCUMENTS TABLE
    # Team-Dokument-Freigaben
    # ==========================================================================
    op.create_table(
        "team_documents",
        # Primary Key
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),

        # Zuordnung
        sa.Column("team_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("teams.id", ondelete="CASCADE"),
                  nullable=False, index=True),
        sa.Column("document_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("documents.id", ondelete="CASCADE"),
                  nullable=False, index=True),

        # Wer hat geteilt
        sa.Column("shared_by_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL"),
                  nullable=True),

        # Berechtigung
        sa.Column("permission", sa.String(20), nullable=False, default="read",
                  comment="read, comment, edit, full"),

        # Zeitliche Begrenzung
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=True),

        # Notiz
        sa.Column("note", sa.Text(), nullable=True),

        # Metadata
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
    )

    # Unique Constraint: Ein Dokument pro Team
    op.create_unique_constraint(
        "uq_team_document",
        "team_documents",
        ["team_id", "document_id"]
    )

    op.create_index("ix_team_doc_document", "team_documents", ["document_id"])


def downgrade() -> None:
    # Drop tables in reverse order
    op.drop_table("team_documents")
    op.drop_table("team_invitations")
    op.drop_table("team_activities")
    op.drop_table("team_memberships")
    op.drop_table("teams")
