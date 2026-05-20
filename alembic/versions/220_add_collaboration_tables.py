"""Add collaboration tables (document_mentions, document_activities)

Revision ID: 220_add_collaboration_tables
Revises: 219_add_prediction_feedback_table
Create Date: 2026-02-13

Feature #4: Echtzeit-Kollaboration
- document_mentions: @Mentions in Kommentaren
- document_activities: Activity Feed fuer Dokumente
- Indexes fuer Performance-Optimierung
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '220_add_collaboration_tables'
down_revision: str = '219_add_prediction_feedback_table'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(tablename: str) -> bool:
    conn = op.get_bind()
    result = conn.execute(sa.text(
        "SELECT 1 FROM pg_tables WHERE schemaname='public' AND tablename=:t"
    ), {"t": tablename})
    return result.fetchone() is not None


def upgrade() -> None:
    """Create collaboration tables."""

    if not _table_exists('document_mentions'):
        op.create_table(
            'document_mentions',
            sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column('document_id', postgresql.UUID(as_uuid=True),
                       sa.ForeignKey('documents.id', ondelete='CASCADE'), nullable=False),
            sa.Column('mentioned_user_id', postgresql.UUID(as_uuid=True),
                       sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
            sa.Column('mentioned_by_id', postgresql.UUID(as_uuid=True),
                       sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
            sa.Column('context', sa.Text, nullable=False,
                       comment='Kontext-Text (z.B. Kommentar-Inhalt)'),
            sa.Column('read', sa.Boolean, nullable=False, server_default='false',
                       comment='Wurde die Mention gelesen?'),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False,
                       server_default=sa.func.now()),
        )
        op.create_index('ix_document_mentions_id', 'document_mentions', ['id'])
        op.create_index('ix_document_mentions_document_id', 'document_mentions', ['document_id'])
        op.create_index('ix_document_mentions_mentioned_user_id', 'document_mentions', ['mentioned_user_id'])
        op.create_index('ix_document_mentions_read', 'document_mentions', ['read'])
        op.create_index('ix_document_mentions_created_at', 'document_mentions', ['created_at'])
        op.create_index('ix_document_mentions_user_read', 'document_mentions',
                         ['mentioned_user_id', 'read', 'created_at'])
        op.create_index('ix_document_mentions_document_created', 'document_mentions',
                         ['document_id', 'created_at'])

    if not _table_exists('document_activities'):
        op.create_table(
            'document_activities',
            sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column('document_id', postgresql.UUID(as_uuid=True),
                       sa.ForeignKey('documents.id', ondelete='CASCADE'), nullable=True),
            sa.Column('user_id', postgresql.UUID(as_uuid=True),
                       sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
            sa.Column('action', sa.String(50), nullable=False,
                       comment='Activity Action (viewed, edited, commented, etc.)'),
            sa.Column('details', sa.Text, nullable=False,
                       comment='Deutsche Beschreibung der Aktivitaet'),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False,
                       server_default=sa.func.now()),
        )
        op.create_index('ix_document_activities_id', 'document_activities', ['id'])
        op.create_index('ix_document_activities_document_id', 'document_activities', ['document_id'])
        op.create_index('ix_document_activities_user_id', 'document_activities', ['user_id'])
        op.create_index('ix_document_activities_action', 'document_activities', ['action'])
        op.create_index('ix_document_activities_created_at', 'document_activities', ['created_at'])
        op.create_index('ix_document_activities_document_created', 'document_activities',
                         ['document_id', 'created_at'])
        op.create_index('ix_document_activities_user_created', 'document_activities',
                         ['user_id', 'created_at'])
        op.create_index('ix_document_activities_action_created', 'document_activities',
                         ['action', 'created_at'])


def downgrade() -> None:
    """Drop collaboration tables."""
    op.drop_index('ix_document_activities_action_created', table_name='document_activities')
    op.drop_index('ix_document_activities_user_created', table_name='document_activities')
    op.drop_index('ix_document_activities_document_created', table_name='document_activities')
    op.drop_index('ix_document_activities_created_at', table_name='document_activities')
    op.drop_index('ix_document_activities_action', table_name='document_activities')
    op.drop_index('ix_document_activities_user_id', table_name='document_activities')
    op.drop_index('ix_document_activities_document_id', table_name='document_activities')
    op.drop_index('ix_document_activities_id', table_name='document_activities')
    op.drop_table('document_activities')

    op.drop_index('ix_document_mentions_document_created', table_name='document_mentions')
    op.drop_index('ix_document_mentions_user_read', table_name='document_mentions')
    op.drop_index('ix_document_mentions_created_at', table_name='document_mentions')
    op.drop_index('ix_document_mentions_read', table_name='document_mentions')
    op.drop_index('ix_document_mentions_mentioned_user_id', table_name='document_mentions')
    op.drop_index('ix_document_mentions_document_id', table_name='document_mentions')
    op.drop_index('ix_document_mentions_id', table_name='document_mentions')
    op.drop_table('document_mentions')
