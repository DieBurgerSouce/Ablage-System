"""Add notifications table for user notifications

Revision ID: 021_add_notifications_table
Revises: 020_add_document_source_field
Create Date: 2026-01-04

Implements real-time notification system for:
- System events (document processing complete, errors, etc.)
- User actions (document shared, comments, etc.)
- Admin notifications
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

# revision identifiers
revision = '021'
down_revision = '020'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add notifications table."""
    op.create_table(
        'notifications',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),

        # Notification content
        sa.Column('type', sa.String(50), nullable=False, server_default='info'),
        sa.Column('title', sa.String(255), nullable=False),
        sa.Column('message', sa.Text, nullable=False),

        # Read status
        sa.Column('read', sa.Boolean, nullable=False, server_default='false'),
        sa.Column('read_at', sa.DateTime(timezone=True), nullable=True),

        # Optional reference to related entity
        sa.Column('entity_type', sa.String(50), nullable=True),
        sa.Column('entity_id', UUID(as_uuid=True), nullable=True),

        # Timestamps
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # Create indexes for performance
    op.create_index('ix_notifications_user_id', 'notifications', ['user_id'])
    op.create_index('ix_notifications_read', 'notifications', ['read'])
    op.create_index('ix_notifications_user_unread', 'notifications', ['user_id', 'read'])
    op.create_index('ix_notifications_created_at', 'notifications', ['created_at'])


def downgrade() -> None:
    """Remove notifications table."""
    op.drop_index('ix_notifications_created_at', 'notifications')
    op.drop_index('ix_notifications_user_unread', 'notifications')
    op.drop_index('ix_notifications_read', 'notifications')
    op.drop_index('ix_notifications_user_id', 'notifications')
    op.drop_table('notifications')
