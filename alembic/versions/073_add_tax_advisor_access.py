"""Add Tax Advisor (Steuerberater) Access Support.

Revision ID: 073_add_tax_advisor_access
Revises: 072_add_gobd_archives
Create Date: 2026-01-02

GoBD Phase 4: Steuerberater-Zugang
- Zeitlich begrenzte Zugaenge (access_until)
- Invite-Token fuer einmalige Registrierung
- tax_advisor Rolle mit GoBD-spezifischen Berechtigungen
- Audit-Trail fuer alle Steuerberater-Aktionen

Erfuellt GoBD-Kriterium:
- Prueferzugang: Steuerberater und Pruefungsbetriebe koennen
  temporaer auf archivierte Dokumente zugreifen
"""
from datetime import datetime, timedelta
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
import uuid

revision = '073'
down_revision = '072'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add Tax Advisor access support."""

    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    if is_postgres:
        uuid_type = postgresql.UUID(as_uuid=True)
        jsonb_type = postgresql.JSONB()
    else:
        uuid_type = sa.String(36)
        jsonb_type = sa.JSON()

    # =========================================================================
    # 1. ADD FIELDS TO users TABLE FOR TIME-LIMITED ACCESS
    # =========================================================================
    op.add_column("users", sa.Column(
        "access_until",
        sa.DateTime(timezone=True),
        nullable=True,
        comment="Zeitliche Begrenzung des Zugangs (fuer Steuerberater/Pruefer)"
    ))

    op.add_column("users", sa.Column(
        "invited_by_id",
        uuid_type,
        sa.ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        comment="Benutzer, der diesen Account eingeladen hat"
    ))

    op.add_column("users", sa.Column(
        "invited_at",
        sa.DateTime(timezone=True),
        nullable=True,
        comment="Zeitpunkt der Einladung"
    ))

    op.add_column("users", sa.Column(
        "access_scope",
        jsonb_type if is_postgres else sa.JSON(),
        nullable=True,
        comment="Eingeschraenkter Zugriff (z.B. nur bestimmte Firmen, Zeitraeume)"
    ))

    # Index fuer ablaufende Zugaenge (taeglich pruefen)
    op.create_index(
        "ix_users_access_until",
        "users",
        ["access_until"],
        postgresql_where=sa.text("access_until IS NOT NULL") if is_postgres else None
    )

    # =========================================================================
    # 2. CREATE tax_advisor_invites TABLE
    # =========================================================================
    op.create_table(
        "tax_advisor_invites",
        sa.Column("id", uuid_type, primary_key=True,
                  server_default=sa.text("gen_random_uuid()") if is_postgres else None),

        # Invite-Token (SHA-256 Hash fuer Sicherheit)
        sa.Column("token_hash", sa.String(128), unique=True, nullable=False,
                  comment="SHA-256 Hash des Invite-Tokens"),

        # Referenzen
        sa.Column("company_id", uuid_type, sa.ForeignKey("companies.id", ondelete="CASCADE"),
                  nullable=False, comment="Firma, fuer die der Zugang gilt"),
        sa.Column("invited_by_id", uuid_type, sa.ForeignKey("users.id", ondelete="SET NULL"),
                  nullable=True, comment="Einladender Admin"),

        # Steuerberater-Daten
        sa.Column("email", sa.String(255), nullable=False, comment="E-Mail des Steuerberaters"),
        sa.Column("full_name", sa.String(255), nullable=True, comment="Name des Steuerberaters"),
        sa.Column("tax_firm_name", sa.String(255), nullable=True, comment="Steuerkanzlei"),
        sa.Column("tax_advisor_id", sa.String(50), nullable=True,
                  comment="Steuerberater-ID der Kammer"),

        # Zugangsparameter
        sa.Column("access_duration_days", sa.Integer(), nullable=False, default=30,
                  comment="Zugang in Tagen (Standard: 30)"),
        sa.Column("access_scope", jsonb_type if is_postgres else sa.JSON(), nullable=True,
                  comment="Eingeschraenkter Zugriff (Zeitraum, Dokumenttypen)"),

        # Status
        sa.Column("status", sa.String(20), nullable=False, server_default="pending",
                  comment="pending, accepted, expired, revoked"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False,
                  comment="Ablaufdatum des Invite-Tokens"),

        # Audit
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("accepted_user_id", uuid_type, sa.ForeignKey("users.id", ondelete="SET NULL"),
                  nullable=True, comment="Erstellter Benutzer nach Akzeptierung"),

        comment="GoBD Steuerberater-Einladungen fuer temporaeren Prueferzugang"
    )

    op.create_index("ix_tax_advisor_invites_email", "tax_advisor_invites", ["email"])
    op.create_index("ix_tax_advisor_invites_company", "tax_advisor_invites", ["company_id"])
    op.create_index("ix_tax_advisor_invites_status", "tax_advisor_invites", ["status"])
    op.create_index("ix_tax_advisor_invites_expires", "tax_advisor_invites", ["expires_at"])

    # =========================================================================
    # 3. CREATE tax_advisor ROLE WITH PERMISSIONS
    # =========================================================================
    # Generiere UUIDs
    role_id = str(uuid.uuid4())

    # Berechtigungen fuer Steuerberater
    permissions = [
        # Archive: Nur Lesen, Exportieren, Verifizieren
        ("archive:read", "Archiv lesen", "archive", "read"),
        ("archive:export", "Archiv exportieren", "archive", "export"),
        ("archive:verify", "Archiv-Integritaet pruefen", "archive", "verify"),
        # Dokumente: Nur Lesen
        ("documents:read", "Dokumente lesen", "documents", "read"),
        # Verfahrensdokumentation: Lesen
        ("procedure_docs:read", "Verfahrensdoku lesen", "procedure_docs", "read"),
        # Audit-Logs: Eigene Aktivitaeten lesen
        ("audit_logs:read_own", "Eigene Audit-Logs lesen", "audit_logs", "read_own"),
    ]

    # Erstelle Rolle
    if is_postgres:
        op.execute(f"""
            INSERT INTO roles (id, name, display_name, description, priority, is_system, is_active, color)
            VALUES (
                '{role_id}'::uuid,
                'tax_advisor',
                'Steuerberater',
                'Zeitlich begrenzter Lesezugriff auf GoBD-relevante Dokumente fuer Steuerberater und Pruefungsbetriebe',
                15,
                true,
                true,
                '#059669'
            )
            ON CONFLICT (name) DO UPDATE SET
                display_name = EXCLUDED.display_name,
                description = EXCLUDED.description,
                priority = EXCLUDED.priority,
                color = EXCLUDED.color
        """)

        # Erstelle Berechtigungen und verknuepfe sie mit der Rolle
        for perm_name, perm_desc, resource, action in permissions:
            perm_id = str(uuid.uuid4())
            op.execute(f"""
                INSERT INTO permissions (id, name, description, resource_type, action, is_system)
                VALUES (
                    '{perm_id}'::uuid,
                    '{perm_name}',
                    '{perm_desc}',
                    '{resource}',
                    '{action}',
                    true
                )
                ON CONFLICT (name) DO NOTHING
            """)

            # Verknuepfe Berechtigung mit Rolle
            op.execute(f"""
                INSERT INTO role_permissions (role_id, permission_id)
                SELECT '{role_id}'::uuid, id FROM permissions WHERE name = '{perm_name}'
                ON CONFLICT DO NOTHING
            """)

    # =========================================================================
    # 4. ADD GOBD ACCESS LOG TABLE (Steuerberater-Aktivitaeten)
    # =========================================================================
    op.create_table(
        "tax_advisor_access_logs",
        sa.Column("id", uuid_type, primary_key=True,
                  server_default=sa.text("gen_random_uuid()") if is_postgres else None),

        sa.Column("user_id", uuid_type, sa.ForeignKey("users.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("company_id", uuid_type, sa.ForeignKey("companies.id", ondelete="CASCADE"),
                  nullable=False),

        # Aktion
        sa.Column("action", sa.String(50), nullable=False,
                  comment="document_view, archive_export, integrity_check"),
        sa.Column("resource_type", sa.String(50), nullable=False,
                  comment="document, archive, procedure_doc"),
        sa.Column("resource_id", uuid_type, nullable=True),

        # Details
        sa.Column("details", jsonb_type if is_postgres else sa.JSON(), nullable=True),
        sa.Column("ip_address", sa.String(45), nullable=True),
        sa.Column("user_agent", sa.String(500), nullable=True),

        # Timestamp
        sa.Column("accessed_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),

        comment="GoBD Steuerberater-Zugriffsprotokolle (revisionssicher)"
    )

    op.create_index("ix_tax_advisor_logs_user", "tax_advisor_access_logs", ["user_id"])
    op.create_index("ix_tax_advisor_logs_company", "tax_advisor_access_logs", ["company_id"])
    op.create_index("ix_tax_advisor_logs_accessed", "tax_advisor_access_logs", ["accessed_at"])
    op.create_index("ix_tax_advisor_logs_action", "tax_advisor_access_logs", ["action"])


def downgrade() -> None:
    """Remove Tax Advisor access support."""

    # Drop tables
    op.drop_table("tax_advisor_access_logs")
    op.drop_table("tax_advisor_invites")

    # Remove user columns
    op.drop_index("ix_users_access_until", table_name="users")
    op.drop_column("users", "access_scope")
    op.drop_column("users", "invited_at")
    op.drop_column("users", "invited_by_id")
    op.drop_column("users", "access_until")

    # Note: Role and permissions are kept to preserve audit history
