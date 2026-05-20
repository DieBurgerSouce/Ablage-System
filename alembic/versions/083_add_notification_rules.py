"""Add notification_rules table for Rule Engine.

Revision ID: 083_add_notification_rules
Revises: 082_add_enterprise_intelligence_tables
Create Date: 2026-01-09

Enterprise Features:
- Notification Rule Engine mit event-basierten Triggern
- Bedingungs-Matching (conditions als JSONB)
- Multiple Aktionen pro Rule (in_app, push, email, webhook)
- Quiet Hours und Rate Limiting
- Statistik-Tracking (trigger_count, last_triggered)
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

# revision identifiers
revision = '083'
down_revision = '082'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ==================================================
    # Notification Rules - Event-basierte Benachrichtigungsregeln
    # ==================================================

    op.create_table(
        'notification_rules',
        sa.Column('id', UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('gen_random_uuid()')),
        sa.Column('user_id', UUID(as_uuid=True), nullable=False,
                  comment='Benutzer, dem diese Regel gehoert'),

        # Rule identification
        sa.Column('name', sa.String(100), nullable=False,
                  comment='Name der Regel'),
        sa.Column('description', sa.Text(), nullable=True,
                  comment='Optionale Beschreibung'),
        sa.Column('enabled', sa.Boolean(), nullable=False, server_default='true',
                  comment='Ob die Regel aktiv ist'),

        # Event matching
        sa.Column('event_type', sa.String(100), nullable=False,
                  comment='Event-Typ z.B. document.ocr_completed'),
        sa.Column('event_source', sa.String(50), nullable=True,
                  comment='Optional: Quelle filtern (z.B. privat, business)'),

        # Conditions (JSONB fuer komplexe Filter)
        sa.Column('conditions', JSONB, nullable=False, server_default='{}',
                  comment='JSON-Bedingungen mit Operatoren (AND, OR, NOT)'),

        # Actions (JSONB fuer mehrere Aktionen)
        sa.Column('actions', JSONB, nullable=False, server_default='[]',
                  comment='Liste von auszufuehrenden Aktionen'),

        # Scheduling
        sa.Column('quiet_hours_start', sa.Time(), nullable=True,
                  comment='Start der Ruhezeit (z.B. 22:00)'),
        sa.Column('quiet_hours_end', sa.Time(), nullable=True,
                  comment='Ende der Ruhezeit (z.B. 08:00)'),
        sa.Column('timezone', sa.String(50), nullable=False, server_default='Europe/Berlin',
                  comment='Zeitzone fuer Quiet Hours'),

        # Rate limiting
        sa.Column('cooldown_minutes', sa.Integer(), nullable=True, server_default='0',
                  comment='Mindestabstand zwischen Benachrichtigungen'),
        sa.Column('max_per_day', sa.Integer(), nullable=True,
                  comment='Maximale Anzahl pro Tag (NULL = unbegrenzt)'),

        # Priority
        sa.Column('priority', sa.String(20), nullable=False, server_default='normal',
                  comment='Prioritaet: low, normal, high, urgent'),

        # Statistics
        sa.Column('trigger_count', sa.Integer(), nullable=False, server_default='0',
                  comment='Anzahl der Ausloeser'),
        sa.Column('last_triggered_at', sa.DateTime(timezone=True), nullable=True,
                  comment='Zeitpunkt des letzten Triggers'),
        sa.Column('last_matched_event_id', UUID(as_uuid=True), nullable=True,
                  comment='ID des letzten gematchten Events'),

        # Timestamps
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text('NOW()')),

        # Comment
        comment='Benutzerdefinierte Notification-Regeln fuer Events'
    )

    # Foreign key to users
    op.create_foreign_key(
        'fk_notification_rules_user_id',
        'notification_rules', 'users',
        ['user_id'], ['id'],
        ondelete='CASCADE'
    )

    # Indexes
    op.create_index('ix_notification_rules_user_id', 'notification_rules', ['user_id'])
    op.create_index('ix_notification_rules_user_enabled', 'notification_rules', ['user_id', 'enabled'])
    op.create_index('ix_notification_rules_event_type', 'notification_rules', ['event_type'])
    op.create_index('ix_notification_rules_enabled', 'notification_rules', ['enabled'],
                    postgresql_where=sa.text('enabled = true'))

    # GIN index fuer JSONB conditions (fuer schnelle Filterung)
    op.execute(
        "CREATE INDEX ix_notification_rules_conditions_gin ON notification_rules "
        "USING GIN (conditions jsonb_path_ops)"
    )


def downgrade() -> None:
    # Drop indexes
    op.execute("DROP INDEX IF EXISTS ix_notification_rules_conditions_gin")
    op.drop_index('ix_notification_rules_enabled', 'notification_rules')
    op.drop_index('ix_notification_rules_event_type', 'notification_rules')
    op.drop_index('ix_notification_rules_user_enabled', 'notification_rules')
    op.drop_index('ix_notification_rules_user_id', 'notification_rules')

    # Drop foreign key
    op.drop_constraint('fk_notification_rules_user_id', 'notification_rules', type_='foreignkey')

    # Drop table
    op.drop_table('notification_rules')
