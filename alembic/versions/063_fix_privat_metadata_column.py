"""Fix PrivatDocument metadata column name - reserved SQLAlchemy name.

Revision ID: 063_fix_privat_metadata_column
Revises: 062_add_privat_module
Create Date: 2024-12-30

'metadata' ist ein reservierter Name in SQLAlchemy's Declarative API.
Umbenennung zu 'doc_metadata' erforderlich.
"""
from alembic import op

revision = "063"
down_revision = "062"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Rename metadata -> doc_metadata in privat_documents."""
    op.alter_column(
        'privat_documents',
        'metadata',
        new_column_name='doc_metadata'
    )


def downgrade() -> None:
    """Revert doc_metadata -> metadata in privat_documents."""
    op.alter_column(
        'privat_documents',
        'doc_metadata',
        new_column_name='metadata'
    )
