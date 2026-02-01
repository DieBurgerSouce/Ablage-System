"""Add Odoo webhook and extended sync tracking tables.

Revision ID: 201_add_odoo_webhooks
Revises: 200_add_fraud_detection_tables
Create Date: 2026-02-01

Phase 6: Odoo Integration Deepening
- Webhook event tracking for idempotency
- Extended sync status per data type
- AI feedback tracking for push operations
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

# revision identifiers, used by Alembic.
revision = '201_add_odoo_webhooks'
down_revision = '200_add_fraud_detection_tables'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create Odoo webhook and extended sync tables."""

    # ==========================================================================
    # Table: odoo_webhook_events - Webhook idempotency tracking
    # ==========================================================================
    op.create_table(
        'odoo_webhook_events',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('connection_id', UUID(as_uuid=True), sa.ForeignKey('erp_connections.id', ondelete='CASCADE'), nullable=False, index=True),

        # Event identification (for idempotency)
        sa.Column('event_id', sa.String(255), nullable=False, index=True, comment='Odoo webhook event ID'),
        sa.Column('event_type', sa.String(100), nullable=False, index=True, comment='customer, supplier, invoice, payment, product, etc.'),
        sa.Column('action', sa.String(50), nullable=False, comment='create, update, delete'),

        # Payload tracking
        sa.Column('payload_hash', sa.String(64), nullable=False, comment='SHA-256 hash of payload'),
        sa.Column('payload_preview', JSONB, nullable=True, comment='Sanitized preview (no PII)'),
        sa.Column('odoo_record_id', sa.String(100), nullable=True, index=True, comment='ID of record in Odoo'),

        # Processing status
        sa.Column('status', sa.String(30), nullable=False, default='pending', index=True),
        sa.Column('processed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('processing_attempts', sa.Integer, nullable=False, default=0),
        sa.Column('last_attempt_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('error_message', sa.Text, nullable=True),

        # Task tracking
        sa.Column('task_id', sa.String(100), nullable=True, comment='Celery task ID'),

        # Timestamps
        sa.Column('received_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False, index=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),

        sa.UniqueConstraint('connection_id', 'event_id', name='uq_odoo_webhook_event_id'),
        comment='Odoo webhook events for idempotent processing'
    )

    # ==========================================================================
    # Table: odoo_sync_status - Extended sync status per data type
    # ==========================================================================
    op.create_table(
        'odoo_sync_status',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('connection_id', UUID(as_uuid=True), sa.ForeignKey('erp_connections.id', ondelete='CASCADE'), nullable=False),

        # Data type identification
        sa.Column('data_type', sa.String(50), nullable=False, comment='projects, timesheet, inventory, products, etc.'),

        # Sync state
        sa.Column('last_sync_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_successful_sync_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_sync_cursor', sa.String(255), nullable=True, comment='Cursor/offset for incremental sync'),
        sa.Column('sync_state', JSONB, nullable=True, comment='Additional state data'),

        # Statistics
        sa.Column('total_records_synced', sa.BigInteger, nullable=False, default=0),
        sa.Column('records_synced_today', sa.Integer, nullable=False, default=0),
        sa.Column('last_record_count', sa.Integer, nullable=True),

        # Error tracking
        sa.Column('consecutive_failures', sa.Integer, nullable=False, default=0),
        sa.Column('last_error', sa.Text, nullable=True),
        sa.Column('is_paused', sa.Boolean, nullable=False, default=False, comment='Paused due to errors'),

        # Timestamps
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),

        sa.UniqueConstraint('connection_id', 'data_type', name='uq_odoo_sync_status_type'),
        comment='Extended sync status per data type for Odoo'
    )

    # ==========================================================================
    # Table: odoo_ai_feedback - AI feedback pushed to Odoo
    # ==========================================================================
    op.create_table(
        'odoo_ai_feedback',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('connection_id', UUID(as_uuid=True), sa.ForeignKey('erp_connections.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('entity_id', UUID(as_uuid=True), sa.ForeignKey('business_entities.id', ondelete='CASCADE'), nullable=False, index=True),

        # Feedback type and data
        sa.Column('feedback_type', sa.String(50), nullable=False, index=True, comment='risk_score, payment_suggestion, skonto_prediction'),
        sa.Column('feedback_data', JSONB, nullable=False, comment='The feedback data (sanitized)'),
        sa.Column('odoo_field', sa.String(100), nullable=True, comment='Target field in Odoo'),

        # Push status
        sa.Column('status', sa.String(30), nullable=False, default='pending', index=True),
        sa.Column('pushed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('push_attempts', sa.Integer, nullable=False, default=0),
        sa.Column('last_attempt_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('error_message', sa.Text, nullable=True),

        # Odoo response
        sa.Column('odoo_record_id', sa.String(100), nullable=True, comment='ID of updated record in Odoo'),
        sa.Column('odoo_response', JSONB, nullable=True, comment='Sanitized response'),

        # Timestamps
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False, index=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),

        comment='AI feedback pushed to Odoo (risk scores, suggestions)'
    )

    # ==========================================================================
    # Indexes
    # ==========================================================================
    op.create_index(
        'ix_odoo_webhook_events_status_received',
        'odoo_webhook_events',
        ['status', 'received_at']
    )
    op.create_index(
        'ix_odoo_ai_feedback_status_created',
        'odoo_ai_feedback',
        ['status', 'created_at']
    )
    op.create_index(
        'ix_odoo_sync_status_connection',
        'odoo_sync_status',
        ['connection_id']
    )


def downgrade() -> None:
    """Drop Odoo webhook and extended sync tables."""
    op.drop_index('ix_odoo_sync_status_connection', table_name='odoo_sync_status')
    op.drop_index('ix_odoo_ai_feedback_status_created', table_name='odoo_ai_feedback')
    op.drop_index('ix_odoo_webhook_events_status_received', table_name='odoo_webhook_events')

    op.drop_table('odoo_ai_feedback')
    op.drop_table('odoo_sync_status')
    op.drop_table('odoo_webhook_events')
