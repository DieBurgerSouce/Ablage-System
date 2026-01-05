"""Add Thumbnail and Preview fields to documents

Revision ID: 019
Revises: 018
Create Date: 2025-01-04

Adds fields for storing thumbnail and preview image keys:
- thumbnail_key: MinIO object key for 200x200 thumbnail
- preview_key: MinIO object key for 800x800 preview
- thumbnail_generated_at: Timestamp when thumbnail was generated
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '019'
down_revision: Union[str, None] = '018'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Add thumbnail fields to documents table.
    """
    # Add thumbnail_key column
    op.add_column(
        'documents',
        sa.Column('thumbnail_key', sa.String(500), nullable=True)
    )

    # Add preview_key column
    op.add_column(
        'documents',
        sa.Column('preview_key', sa.String(500), nullable=True)
    )

    # Add thumbnail_generated_at column
    op.add_column(
        'documents',
        sa.Column('thumbnail_generated_at', sa.DateTime(timezone=True), nullable=True)
    )

    # Create index for quick lookup of documents without thumbnails
    op.create_index(
        'ix_documents_thumbnail_key_null',
        'documents',
        ['id'],
        postgresql_where=sa.text('thumbnail_key IS NULL')
    )


def downgrade() -> None:
    """
    Remove thumbnail fields from documents table.
    """
    # Drop index
    op.drop_index('ix_documents_thumbnail_key_null', table_name='documents')

    # Drop columns
    op.drop_column('documents', 'thumbnail_generated_at')
    op.drop_column('documents', 'preview_key')
    op.drop_column('documents', 'thumbnail_key')
