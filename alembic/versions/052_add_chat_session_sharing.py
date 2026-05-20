"""Add chat session sharing for real-time collaboration

Revision ID: 052_add_chat_session_sharing
Revises: 051_add_attached_document
Create Date: 2024-12-18

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "052"
down_revision = "051"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create rag_chat_session_access table for sharing
    op.create_table(
        'rag_chat_session_access',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            'session_id',
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey('rag_chat_sessions.id', ondelete='CASCADE'),
            nullable=False
        ),
        sa.Column(
            'user_id',
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey('users.id', ondelete='CASCADE'),
            nullable=False
        ),
        sa.Column(
            'granted_by_id',
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey('users.id', ondelete='SET NULL'),
            nullable=True
        ),
        sa.Column(
            'access_level',
            sa.String(20),
            nullable=False,
            server_default='view'
        ),
        sa.Column(
            'granted_at',
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False
        ),
    )

    # Create indexes
    op.create_index(
        'ix_chat_session_access_user_session',
        'rag_chat_session_access',
        ['user_id', 'session_id'],
        unique=True
    )
    op.create_index(
        'ix_chat_session_access_session_id',
        'rag_chat_session_access',
        ['session_id']
    )
    op.create_index(
        'ix_chat_session_access_user_id',
        'rag_chat_session_access',
        ['user_id']
    )


def downgrade() -> None:
    # Drop indexes
    op.drop_index('ix_chat_session_access_user_id', table_name='rag_chat_session_access')
    op.drop_index('ix_chat_session_access_session_id', table_name='rag_chat_session_access')
    op.drop_index('ix_chat_session_access_user_session', table_name='rag_chat_session_access')

    # Drop table
    op.drop_table('rag_chat_session_access')
