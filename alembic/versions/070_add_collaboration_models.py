"""Add collaboration models (comments, activities, notifications)

Revision ID: 070_add_collaboration
Revises: 069_add_privat_document_soft_delete_fields
Create Date: 2024-12-31

Adds:
- document_comments: Kommentare zu Dokumenten
- document_activities: Aktivitaetsverlauf
- user_notifications: Benutzer-Benachrichtigungen
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '070_add_collaboration'
down_revision = '069_add_privat_document_soft_delete_fields'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Document Comments
    op.create_table(
        'document_comments',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('document_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('documents.id', ondelete='CASCADE'), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('parent_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('document_comments.id', ondelete='CASCADE'), nullable=True),
        sa.Column('content', sa.Text, nullable=False),
        sa.Column('mentions', postgresql.JSONB, default=list),
        sa.Column('reactions', postgresql.JSONB, default=list),
        sa.Column('is_edited', sa.Boolean, default=False),
        sa.Column('is_deleted', sa.Boolean, default=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
    )

    op.create_index('ix_doc_comment_document', 'document_comments', ['document_id'])
    op.create_index('ix_doc_comment_user', 'document_comments', ['user_id'])
    op.create_index('ix_doc_comment_parent', 'document_comments', ['parent_id'])
    op.create_index('ix_doc_comment_created', 'document_comments', ['created_at'])

    # Document Activities
    op.create_table(
        'document_activities',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('document_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('documents.id', ondelete='CASCADE'), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('activity_type', sa.String(50), nullable=False),
        sa.Column('description', sa.String(500), nullable=False),
        sa.Column('metadata', postgresql.JSONB, default=dict),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_index('ix_doc_activity_document', 'document_activities', ['document_id'])
    op.create_index('ix_doc_activity_user', 'document_activities', ['user_id'])
    op.create_index('ix_doc_activity_type', 'document_activities', ['activity_type'])
    op.create_index('ix_doc_activity_created', 'document_activities', ['created_at'])

    # User Notifications
    op.create_table(
        'user_notifications',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('from_user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('document_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('documents.id', ondelete='CASCADE'), nullable=True),
        sa.Column('notification_type', sa.String(50), nullable=False),
        sa.Column('title', sa.String(200), nullable=False),
        sa.Column('message', sa.Text, nullable=False),
        sa.Column('action_url', sa.String(500), nullable=True),
        sa.Column('is_read', sa.Boolean, default=False),
        sa.Column('read_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_index('ix_notification_user', 'user_notifications', ['user_id'])
    op.create_index('ix_notification_unread', 'user_notifications', ['user_id', 'is_read'])
    op.create_index('ix_notification_created', 'user_notifications', ['created_at'])


def downgrade() -> None:
    # Wichtig: Indices vor Tabellen droppen um DB-Konsistenz zu gewährleisten
    # user_notifications Indices
    op.drop_index('ix_notification_created', table_name='user_notifications')
    op.drop_index('ix_notification_unread', table_name='user_notifications')
    op.drop_index('ix_notification_user', table_name='user_notifications')

    # document_activities Indices
    op.drop_index('ix_doc_activity_created', table_name='document_activities')
    op.drop_index('ix_doc_activity_type', table_name='document_activities')
    op.drop_index('ix_doc_activity_user', table_name='document_activities')
    op.drop_index('ix_doc_activity_document', table_name='document_activities')

    # document_comments Indices
    op.drop_index('ix_doc_comment_created', table_name='document_comments')
    op.drop_index('ix_doc_comment_parent', table_name='document_comments')
    op.drop_index('ix_doc_comment_user', table_name='document_comments')
    op.drop_index('ix_doc_comment_document', table_name='document_comments')

    # Tabellen droppen
    op.drop_table('user_notifications')
    op.drop_table('document_activities')
    op.drop_table('document_comments')
