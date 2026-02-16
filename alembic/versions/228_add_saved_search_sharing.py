"""Add team sharing to saved searches.

Revision ID: 228
Revises: 227
Create Date: 2026-02-15

Adds is_shared and company_id columns for team-wide search sharing (Gap C).
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "228"
down_revision = "227"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "saved_searches",
        sa.Column(
            "is_shared",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
            comment="Mit Team geteilt",
        ),
    )
    op.add_column(
        "saved_searches",
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
            comment="Firma fuer Team-Sharing",
        ),
    )
    op.create_foreign_key(
        "fk_saved_searches_company_id",
        "saved_searches",
        "companies",
        ["company_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_saved_searches_company_id",
        "saved_searches",
        ["company_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_saved_searches_company_id", table_name="saved_searches")
    op.drop_constraint("fk_saved_searches_company_id", "saved_searches", type_="foreignkey")
    op.drop_column("saved_searches", "company_id")
    op.drop_column("saved_searches", "is_shared")
