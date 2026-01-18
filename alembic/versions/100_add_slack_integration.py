"""Add Slack Integration Tables.

Revision ID: 100_slack_integration
Revises: 099_add_knowledge_management
Create Date: 2026-01-17

Slack-Integration fuer Enterprise Notifications:
- slack_channels: Kanal-Konfiguration
- slack_message_logs: Nachrichten-Verlauf
- slack_user_mappings: User-Verknuepfungen
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

# revision identifiers, used by Alembic.
revision = '100_slack_integration'
down_revision = '099_add_knowledge_management'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # =========================================================================
    # SLACK CHANNELS
    # =========================================================================
    op.create_table(
        'slack_channels',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),

        # Kanal-Identifikation
        sa.Column('channel_id', sa.String(50), nullable=False, comment='Slack Channel ID (z.B. C01234567)'),
        sa.Column('channel_name', sa.String(100), nullable=False, comment='Kanal-Name ohne #'),
        sa.Column('channel_type', sa.String(20), server_default='public', comment='Kanal-Typ: public, private, dm'),

        # Multi-Tenant Support
        sa.Column('company_id', UUID(as_uuid=True), sa.ForeignKey('companies.id', ondelete='CASCADE'), nullable=True,
                  comment='Firmen-spezifischer Kanal (NULL = global)'),

        # Routing-Konfiguration
        sa.Column('notification_types', JSONB, server_default='[]', comment='Notification-Typen die an diesen Kanal gehen'),
        sa.Column('min_priority', sa.String(20), server_default='normal', comment='Mindest-Prioritaet: low, normal, high, urgent'),
        sa.Column('is_default', sa.Boolean, server_default='false', comment='Standard-Kanal fuer nicht-routbare Nachrichten'),

        # Formatierung
        sa.Column('include_context', sa.Boolean, server_default='true', comment='Kontext-Details einschliessen'),
        sa.Column('mention_users', JSONB, server_default='[]', comment='Slack User-IDs die bei Nachrichten erwaehnt werden'),
        sa.Column('custom_icon', sa.String(100), nullable=True, comment='Custom Emoji als Icon'),

        # Status
        sa.Column('is_active', sa.Boolean, server_default='true'),
        sa.Column('last_message_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('message_count', sa.Integer, server_default='0'),

        # Audit
        sa.Column('created_by_id', UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),

        comment='Slack-Kanal-Konfiguration fuer Benachrichtigungen'
    )

    # Indexes fuer slack_channels
    op.create_index('ix_slack_channels_company', 'slack_channels', ['company_id'])
    op.create_index('ix_slack_channels_active', 'slack_channels', ['is_active'])
    op.create_index('ix_slack_channels_channel_id', 'slack_channels', ['channel_id'])
    op.create_unique_constraint('uq_slack_channels_channel_company', 'slack_channels', ['channel_id', 'company_id'])

    # =========================================================================
    # SLACK MESSAGE LOGS
    # =========================================================================
    op.create_table(
        'slack_message_logs',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),

        # Kanal-Referenz
        sa.Column('channel_id', UUID(as_uuid=True), sa.ForeignKey('slack_channels.id', ondelete='SET NULL'), nullable=True),
        sa.Column('slack_channel_id', sa.String(50), nullable=False, comment='Slack Channel ID als Backup'),

        # Nachricht
        sa.Column('message_ts', sa.String(50), nullable=True, comment='Slack Message Timestamp/ID'),
        sa.Column('thread_ts', sa.String(50), nullable=True, comment='Thread Timestamp wenn Antwort'),
        sa.Column('notification_type', sa.String(50), nullable=False),
        sa.Column('title', sa.String(255), nullable=False),
        sa.Column('message_preview', sa.String(500), nullable=True, comment='Erste 500 Zeichen'),
        sa.Column('priority', sa.String(20), server_default='normal'),

        # Status
        sa.Column('status', sa.String(20), server_default='pending'),
        sa.Column('error_message', sa.String(500), nullable=True),
        sa.Column('retry_count', sa.Integer, server_default='0'),

        # Referenz zum Ausloesenden Objekt (polymorph)
        sa.Column('reference_type', sa.String(50), nullable=True, comment='document, approval, workflow, etc.'),
        sa.Column('reference_id', UUID(as_uuid=True), nullable=True),

        # Audit
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('sent_at', sa.DateTime(timezone=True), nullable=True),

        comment='Log fuer gesendete Slack-Nachrichten'
    )

    # Indexes fuer slack_message_logs
    op.create_index('ix_slack_messages_channel', 'slack_message_logs', ['channel_id'])
    op.create_index('ix_slack_messages_status', 'slack_message_logs', ['status'])
    op.create_index('ix_slack_messages_created', 'slack_message_logs', ['created_at'])
    op.create_index('ix_slack_messages_notification_type', 'slack_message_logs', ['notification_type'])
    op.create_index('ix_slack_messages_reference', 'slack_message_logs', ['reference_type', 'reference_id'])

    # =========================================================================
    # SLACK USER MAPPINGS
    # =========================================================================
    op.create_table(
        'slack_user_mappings',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),

        # User-Referenzen
        sa.Column('user_id', UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, unique=True),
        sa.Column('slack_user_id', sa.String(50), nullable=False, comment='Slack User ID (z.B. U01234567)'),
        sa.Column('slack_username', sa.String(100), nullable=True, comment='Slack Display Name'),

        # Benachrichtigungs-Praeferenzen
        sa.Column('dm_enabled', sa.Boolean, server_default='false', comment='Direkte Nachrichten erlauben'),
        sa.Column('dm_notification_types', JSONB, server_default='[]', comment='Notification-Typen die als DM gesendet werden'),
        sa.Column('mention_on_approval', sa.Boolean, server_default='true', comment='Bei Freigabe-Anfragen erwaehnen'),
        sa.Column('quiet_hours_start', sa.String(5), nullable=True, comment='Ruhezeit Start (HH:MM)'),
        sa.Column('quiet_hours_end', sa.String(5), nullable=True, comment='Ruhezeit Ende (HH:MM)'),

        # Verifizierung
        sa.Column('is_verified', sa.Boolean, server_default='false', comment='Slack-Account verifiziert'),
        sa.Column('verified_at', sa.DateTime(timezone=True), nullable=True),

        # Audit
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),

        comment='Mapping Ablage-System User <-> Slack User'
    )

    # Indexes fuer slack_user_mappings
    op.create_index('ix_slack_user_mappings_slack_user', 'slack_user_mappings', ['slack_user_id'])
    op.create_unique_constraint('uq_slack_user_mappings_slack_user', 'slack_user_mappings', ['slack_user_id'])


def downgrade() -> None:
    # Drop in reverse order
    op.drop_table('slack_user_mappings')
    op.drop_table('slack_message_logs')
    op.drop_table('slack_channels')
