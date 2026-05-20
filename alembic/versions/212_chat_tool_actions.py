"""chat_tool_actions

Revision ID: 212_chat_tool_actions
Revises: 211_rls_coverage_audit
Create Date: 2026-02-10 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '212_chat_tool_actions'
down_revision: Union[str, None] = '211_rls_coverage_audit'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add chat_tool_actions table for RAG Agent Mode."""

    # Create table
    op.create_table(
        'chat_tool_actions',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('session_id', postgresql.UUID(as_uuid=True), nullable=False,
                  comment='Chat Session in der die Aktion aufgetreten ist'),
        sa.Column('message_id', postgresql.UUID(as_uuid=True), nullable=True,
                  comment='Assistant-Message die die Aktion vorgeschlagen hat'),
        sa.Column('tool_name', sa.String(length=50), nullable=False,
                  comment='Name des aufgerufenen Tools'),
        sa.Column('parameters', postgresql.JSONB(astext_type=sa.Text()), nullable=False,
                  comment='Tool-Parameter als JSON'),
        sa.Column('status', sa.String(length=30), nullable=False,
                  comment='pending_confirmation, confirmed, executed, rejected, failed'),
        sa.Column('result', postgresql.JSONB(astext_type=sa.Text()), nullable=True,
                  comment='Ergebnis nach Ausfuehrung'),
        sa.Column('error_message', sa.Text(), nullable=True,
                  comment='Fehlermeldung bei failed status'),
        sa.Column('requires_confirmation', sa.Boolean(), nullable=False,
                  comment='Muss vom User bestaetigt werden'),
        sa.Column('confirmed_by_id', postgresql.UUID(as_uuid=True), nullable=True,
                  comment='User der die Aktion bestaetigt hat'),
        sa.Column('executed_at', sa.DateTime(timezone=True), nullable=True,
                  comment='Zeitpunkt der Ausfuehrung'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'),
                  nullable=False, comment='Zeitpunkt der Erstellung'),
        sa.ForeignKeyConstraint(['confirmed_by_id'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['message_id'], ['rag_chat_messages.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['session_id'], ['rag_chat_sessions.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        comment='Tool-Aktionen aus dem RAG Chat Agent Mode'
    )

    # Create indexes
    op.create_index('ix_chat_tool_actions_session_id', 'chat_tool_actions', ['session_id'])
    op.create_index('ix_chat_tool_actions_tool_name', 'chat_tool_actions', ['tool_name'])
    op.create_index('ix_chat_tool_actions_status', 'chat_tool_actions', ['status'])
    op.create_index('ix_chat_tool_actions_session_status', 'chat_tool_actions',
                    ['session_id', 'status'])
    op.create_index('ix_chat_tool_actions_created', 'chat_tool_actions', ['created_at'])


def downgrade() -> None:
    """Remove chat_tool_actions table."""

    # Drop indexes
    op.drop_index('ix_chat_tool_actions_created', table_name='chat_tool_actions')
    op.drop_index('ix_chat_tool_actions_session_status', table_name='chat_tool_actions')
    op.drop_index('ix_chat_tool_actions_status', table_name='chat_tool_actions')
    op.drop_index('ix_chat_tool_actions_tool_name', table_name='chat_tool_actions')
    op.drop_index('ix_chat_tool_actions_session_id', table_name='chat_tool_actions')

    # Drop table
    op.drop_table('chat_tool_actions')
