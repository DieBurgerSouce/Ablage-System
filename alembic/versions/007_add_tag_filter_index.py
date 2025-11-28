"""Add index for tag name filtering

Revision ID: 007
Revises: 006
Create Date: 2025-11-27

Adds index on tags.name column to optimize tag filtering in search queries.
The search service filters by tag name using ANY(:filter_tags), which
benefits from a B-tree index on the name column.
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '007'
down_revision: Union[str, None] = '006'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add index on tags.name for faster filtering."""
    # Index fuer Tag-Namen-Filterung
    # Optimiert WHERE t.name = ANY(:filter_tags) Abfragen
    op.create_index(
        'ix_tags_name',
        'tags',
        ['name'],
        unique=False
    )


def downgrade() -> None:
    """Remove tags.name index."""
    op.drop_index('ix_tags_name', table_name='tags')
