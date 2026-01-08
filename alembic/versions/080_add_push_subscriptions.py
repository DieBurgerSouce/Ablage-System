"""Add push subscriptions for PWA notifications.

Revision ID: 080_add_push_subscriptions
Revises: 079_add_workflow_automation
Create Date: 2026-01-03

Erstellt Tabellen fuer Web Push Notifications:
- push_subscriptions: Geraete-Subscriptions
- notification_templates: Vordefinierte Benachrichtigungsvorlagen
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

# revision identifiers
revision = '080'
down_revision = '079'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ==================================================
    # Push Subscriptions Table
    # ==================================================
    op.create_table(
        'push_subscriptions',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('user_id', UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),

        # Web Push Subscription data
        sa.Column('endpoint', sa.Text(), nullable=False),
        sa.Column('p256dh_key', sa.Text(), nullable=False),  # Public key
        sa.Column('auth_key', sa.Text(), nullable=False),     # Auth secret
        sa.Column('expiration_time', sa.BigInteger(), nullable=True),

        # Device information
        sa.Column('device_name', sa.String(255), nullable=True),
        sa.Column('device_type', sa.String(50), nullable=True),  # mobile, tablet, desktop
        sa.Column('browser', sa.String(100), nullable=True),
        sa.Column('os', sa.String(100), nullable=True),
        sa.Column('user_agent', sa.Text(), nullable=True),

        # Subscription preferences
        sa.Column('preferences', JSONB, nullable=False, server_default='{}'),
        # Example: {"documents": true, "workflows": true, "system": false}

        # Status
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('last_used_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('error_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('last_error', sa.Text(), nullable=True),

        # Timestamps
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
    )

    # Indexes
    op.create_index('ix_push_subscriptions_user_id', 'push_subscriptions', ['user_id'])
    op.create_index('ix_push_subscriptions_endpoint', 'push_subscriptions', ['endpoint'], unique=True)
    op.create_index('ix_push_subscriptions_is_active', 'push_subscriptions', ['is_active'])
    op.create_index('ix_push_subscriptions_device_type', 'push_subscriptions', ['device_type'])

    # ==================================================
    # Notification Templates Table
    # ==================================================
    op.create_table(
        'notification_templates',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),

        # Template identification
        sa.Column('name', sa.String(100), nullable=False, unique=True),
        sa.Column('category', sa.String(50), nullable=False),  # documents, workflows, system, etc.
        sa.Column('description', sa.Text(), nullable=True),

        # Notification content
        sa.Column('title_template', sa.String(255), nullable=False),
        sa.Column('body_template', sa.Text(), nullable=False),
        sa.Column('icon', sa.String(255), nullable=True),
        sa.Column('badge', sa.String(255), nullable=True),
        sa.Column('image', sa.String(255), nullable=True),

        # Actions (up to 2 buttons)
        sa.Column('actions', JSONB, nullable=True),
        # Example: [{"action": "view", "title": "Anzeigen"}, {"action": "dismiss", "title": "Schliessen"}]

        # Behavior
        sa.Column('tag', sa.String(100), nullable=True),  # Replaces existing with same tag
        sa.Column('require_interaction', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('silent', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('vibrate_pattern', JSONB, nullable=True),  # [200, 100, 200]

        # Default preferences
        sa.Column('default_enabled', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('priority', sa.String(20), nullable=False, server_default="'normal'"),  # low, normal, high

        # Status
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),

        # Timestamps
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
    )

    # Indexes
    op.create_index('ix_notification_templates_name', 'notification_templates', ['name'])
    op.create_index('ix_notification_templates_category', 'notification_templates', ['category'])
    op.create_index('ix_notification_templates_is_active', 'notification_templates', ['is_active'])

    # ==================================================
    # Notification History Table (for tracking sent notifications)
    # ==================================================
    op.create_table(
        'notification_history',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('subscription_id', UUID(as_uuid=True), sa.ForeignKey('push_subscriptions.id', ondelete='CASCADE'), nullable=False),
        sa.Column('template_id', UUID(as_uuid=True), sa.ForeignKey('notification_templates.id', ondelete='SET NULL'), nullable=True),

        # Notification content (snapshot)
        sa.Column('title', sa.String(255), nullable=False),
        sa.Column('body', sa.Text(), nullable=False),
        sa.Column('data', JSONB, nullable=True),

        # Delivery status
        sa.Column('status', sa.String(20), nullable=False, server_default="'pending'"),  # pending, sent, delivered, clicked, failed
        sa.Column('sent_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('delivered_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('clicked_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),

        # Timestamps
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
    )

    # Indexes
    op.create_index('ix_notification_history_subscription_id', 'notification_history', ['subscription_id'])
    op.create_index('ix_notification_history_template_id', 'notification_history', ['template_id'])
    op.create_index('ix_notification_history_status', 'notification_history', ['status'])
    op.create_index('ix_notification_history_created_at', 'notification_history', ['created_at'])

    # ==================================================
    # Seed Default Notification Templates
    # ==================================================
    op.execute("""
        INSERT INTO notification_templates (name, category, title_template, body_template, icon, actions, tag, require_interaction)
        VALUES
            ('document_processed', 'documents', 'Dokument verarbeitet', '{{document_name}} wurde erfolgreich verarbeitet.', '/icons/icon-192x192.png', '[{"action": "view", "title": "Anzeigen"}]', 'document-{{document_id}}', false),
            ('document_error', 'documents', 'Verarbeitungsfehler', 'Bei {{document_name}} ist ein Fehler aufgetreten.', '/icons/icon-192x192.png', '[{"action": "view", "title": "Details"}]', 'error-{{document_id}}', true),
            ('workflow_completed', 'workflows', 'Workflow abgeschlossen', 'Der Workflow "{{workflow_name}}" wurde erfolgreich abgeschlossen.', '/icons/icon-192x192.png', '[{"action": "view", "title": "Anzeigen"}]', 'workflow-{{workflow_id}}', false),
            ('workflow_approval', 'workflows', 'Genehmigung erforderlich', 'Ein Workflow wartet auf Ihre Genehmigung.', '/icons/icon-192x192.png', '[{"action": "approve", "title": "Genehmigen"}, {"action": "reject", "title": "Ablehnen"}]', 'approval-{{workflow_id}}', true),
            ('system_update', 'system', 'System-Update', 'Eine neue Version ist verfuegbar.', '/icons/icon-192x192.png', '[{"action": "update", "title": "Aktualisieren"}]', 'system-update', false),
            ('backup_complete', 'system', 'Backup abgeschlossen', 'Das Backup wurde erfolgreich erstellt.', '/icons/icon-192x192.png', NULL, 'backup', false),
            ('comment_added', 'collaboration', 'Neuer Kommentar', '{{user_name}} hat einen Kommentar hinzugefuegt.', '/icons/icon-192x192.png', '[{"action": "view", "title": "Anzeigen"}]', 'comment-{{document_id}}', false),
            ('share_received', 'collaboration', 'Dokument geteilt', '{{user_name}} hat ein Dokument mit Ihnen geteilt.', '/icons/icon-192x192.png', '[{"action": "view", "title": "Anzeigen"}]', 'share-{{document_id}}', false)
        ON CONFLICT (name) DO NOTHING
    """)


def downgrade() -> None:
    op.drop_table('notification_history')
    op.drop_table('notification_templates')
    op.drop_table('push_subscriptions')
