"""Add last_reminder_at to DocumentTask.

Revision ID: 102_task_reminder_fields
Revises: 101_gobd_access_log
Create Date: 2026-01-17

Collaboration-Suite Erweiterung:
- Tracking wann zuletzt eine Ueberfaellig-Erinnerung gesendet wurde
- Ermoeglicht cooldown zwischen Erinnerungen
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers
revision = '102_task_reminder_fields'
down_revision = '101_gobd_access_log'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Fuegt last_reminder_at Feld zu document_tasks hinzu (idempotent)."""
    conn = op.get_bind()

    # Check if document_tasks table exists
    table_exists = conn.execute(sa.text("""
        SELECT EXISTS (
            SELECT FROM information_schema.tables
            WHERE table_schema = 'public'
            AND table_name = 'document_tasks'
        )
    """)).scalar()

    if not table_exists:
        # Skip if table doesn't exist yet
        return

    # Check if column already exists
    column_exists = conn.execute(sa.text("""
        SELECT EXISTS (
            SELECT FROM information_schema.columns
            WHERE table_schema = 'public'
            AND table_name = 'document_tasks'
            AND column_name = 'last_reminder_at'
        )
    """)).scalar()

    if column_exists:
        return

    op.add_column(
        'document_tasks',
        sa.Column(
            'last_reminder_at',
            sa.DateTime(timezone=True),
            nullable=True,
            comment='Zeitpunkt der letzten Ueberfaellig-Erinnerung'
        )
    )


def downgrade() -> None:
    """Entfernt last_reminder_at Feld (idempotent)."""
    conn = op.get_bind()

    column_exists = conn.execute(sa.text("""
        SELECT EXISTS (
            SELECT FROM information_schema.columns
            WHERE table_schema = 'public'
            AND table_name = 'document_tasks'
            AND column_name = 'last_reminder_at'
        )
    """)).scalar()

    if column_exists:
        op.drop_column('document_tasks', 'last_reminder_at')
