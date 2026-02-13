"""Merge saved_searches and collaboration heads.

Revision ID: 221_merge_heads
Revises: 207_add_saved_searches, 220_add_collaboration_tables
Create Date: 2026-02-13
"""

from typing import Sequence, Union

from alembic import op

revision: str = "221_merge_heads"
down_revision: Union[str, Sequence[str]] = (
    "207_add_saved_searches",
    "220_add_collaboration_tables",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
