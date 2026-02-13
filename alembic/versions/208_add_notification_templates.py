"""Add notification templates

Revision ID: 208_add_notification_templates
Revises: 207_add_saved_searches
Create Date: 2026-02-08

Fuegt die notification_templates Tabelle fuer das Template-Engine-System hinzu.
Ermoeglicht wiederverwendbare Benachrichtigungsvorlagen mit Jinja2-Templates.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "208_add_notification_templates"
down_revision = "208_add_kanban_workflow"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Erstellt notification_templates Tabelle."""
    conn = op.get_bind()
    result = conn.execute(sa.text(
        "SELECT 1 FROM pg_tables WHERE schemaname='public' AND tablename='notification_message_templates'"
    ))
    if result.fetchone():
        return  # Tabelle existiert bereits

    # Tabelle erstellen
    op.create_table(
        "notification_message_templates",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
        ),
        sa.Column(
            "name",
            sa.String(200),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            "category",
            sa.String(50),
            nullable=False,
        ),
        sa.Column(
            "subject_template",
            sa.Text(),
            nullable=False,
        ),
        sa.Column(
            "body_template",
            sa.Text(),
            nullable=False,
        ),
        sa.Column(
            "variables",
            postgresql.JSONB(),
            nullable=True,
            comment="JSON mit required/optional Variablen",
        ),
        sa.Column(
            "channels",
            postgresql.JSONB(),
            nullable=True,
            comment="JSON-Array mit unterstuetzten Notification-Channels",
        ),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column(
            "created_by_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )

    # Indizes erstellen
    op.create_index(
        "ix_notification_msg_tpl_name",
        "notification_message_templates",
        ["name"],
        unique=True,
    )
    op.create_index(
        "ix_notification_msg_tpl_category",
        "notification_message_templates",
        ["category"],
    )
    op.create_index(
        "ix_notification_msg_tpl_is_active",
        "notification_message_templates",
        ["is_active"],
    )
    op.create_index(
        "ix_notification_msg_tpl_category_active",
        "notification_message_templates",
        ["category", "is_active"],
    )


def downgrade() -> None:
    """Loescht notification_templates Tabelle."""
    # Indizes loeschen (werden automatisch mit Tabelle geloescht)
    # Tabelle loeschen
    op.drop_table("notification_message_templates")
