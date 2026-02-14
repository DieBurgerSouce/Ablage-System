"""Add data quality history table for trend tracking.

Speichert periodische Datenqualitaets-Snapshots pro Company:
- overall_score: Gesamt-Score (0-100)
- issue_counts: Issue-Zaehler pro Kategorie (JSONB)
- issue_details: Vollstaendige Issue-Liste (JSONB)

Revision ID: 224_add_data_quality_history
Revises: 223_add_knowledge_graph_autonomy_comments
Create Date: 2026-02-15
"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from alembic import op

revision: str = "224_add_data_quality_history"
down_revision: str = "223_add_knowledge_graph_autonomy_comments"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "data_quality_history",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("overall_score", sa.Float(), nullable=False),
        sa.Column(
            "issue_counts",
            postgresql.JSONB(),
            nullable=False,
            server_default="{}",
        ),
        sa.Column(
            "issue_details",
            postgresql.JSONB(),
            nullable=False,
            server_default="[]",
        ),
        sa.Column(
            "checked_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
            index=True,
        ),
    )

    # Composite index for efficient trend queries
    op.create_index(
        "ix_dq_history_company_checked",
        "data_quality_history",
        ["company_id", "checked_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_dq_history_company_checked", table_name="data_quality_history")
    op.drop_table("data_quality_history")
