"""Add source field to documents for import analytics

Revision ID: 020
Revises: 019
Create Date: 2025-01-04

Adds source field to track how documents were imported:
- web: Manual upload via web UI
- api: Upload via REST API
- email_import: Imported from email
- folder_watch: Imported from watched folder
- admin: Uploaded by admin
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '020'
down_revision: Union[str, None] = '019b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Add source field to documents table.
    """
    # Add source column with default 'web'
    op.add_column(
        'documents',
        sa.Column('source', sa.String(50), nullable=True, server_default='web')
    )

    # Update existing records to have 'web' as source
    op.execute("UPDATE documents SET source = 'web' WHERE source IS NULL")

    # Make column NOT NULL after backfill
    op.alter_column('documents', 'source', nullable=False)

    # Create index for analytics queries
    op.create_index(
        'ix_documents_source',
        'documents',
        ['source']
    )

    # Create composite index for date-based analytics
    op.create_index(
        'ix_documents_source_upload_date',
        'documents',
        ['source', 'upload_date']
    )


def downgrade() -> None:
    """
    Remove source field from documents table.
    """
    # Drop indexes
    op.drop_index('ix_documents_source_upload_date', table_name='documents')
    op.drop_index('ix_documents_source', table_name='documents')

    # Drop column
    op.drop_column('documents', 'source')
