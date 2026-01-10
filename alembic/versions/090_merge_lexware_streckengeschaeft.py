"""Merge lexware and streckengeschaeft branches.

Revision ID: 090
Revises: 089, streckengeschaeft_004
Create Date: 2026-01-10

Merges the Lexware integration branch with the Streckengeschäft branch.
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = '090'
down_revision = ('089', 'streckengeschaeft_004')
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Merge-Migration - keine Schemaänderungen erforderlich."""
    pass


def downgrade() -> None:
    """Merge-Migration - keine Schemaänderungen erforderlich."""
    pass
