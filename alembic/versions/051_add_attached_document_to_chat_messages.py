"""Add attached_document_id to rag_chat_messages

Revision ID: 051_add_attached_document
Revises: 050_add_position_weighted_analytics
Create Date: 2024-12-18

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '051_add_attached_document'
down_revision = '050_add_position_weighted_analytics'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add attached_document_id column to rag_chat_messages
    op.add_column(
        'rag_chat_messages',
        sa.Column(
            'attached_document_id',
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey('documents.id', ondelete='SET NULL'),
            nullable=True
        )
    )

    # Create index for the new foreign key
    op.create_index(
        'ix_rag_chat_messages_attached_document',
        'rag_chat_messages',
        ['attached_document_id']
    )


def downgrade() -> None:
    # Drop index
    op.drop_index('ix_rag_chat_messages_attached_document', table_name='rag_chat_messages')

    # Drop column
    op.drop_column('rag_chat_messages', 'attached_document_id')
