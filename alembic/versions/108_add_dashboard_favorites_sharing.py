"""Add dashboard favorites and user-specific sharing.

Revision ID: 108_dashboard_enhancements
Revises: 107_add_gobd_compliance_tables
Create Date: 2026-01-19

Enhances Dashboard-System:
- is_favorite column for quick access to favorite dashboards
- dashboard_shares table for user-specific sharing (beyond role-based)
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "108_dashboard_enhancements"
down_revision = "107_add_gobd_compliance_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ==========================================================================
    # Add is_favorite column to user_dashboards
    # ==========================================================================
    op.add_column(
        "user_dashboards",
        sa.Column("is_favorite", sa.Boolean(), nullable=False, server_default="false"),
    )

    # Index for fast favorite lookups
    op.create_index(
        "ix_user_dashboards_favorite",
        "user_dashboards",
        ["user_id", "is_favorite"],
        postgresql_where=sa.text("is_favorite = true"),
    )

    # ==========================================================================
    # Dashboard Shares - User-specific sharing (beyond role-based)
    # ==========================================================================
    op.create_table(
        "dashboard_shares",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),

        # Foreign Keys
        sa.Column("dashboard_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("user_dashboards.id", ondelete="CASCADE"), nullable=False),
        sa.Column("shared_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("shared_with_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),

        # Permissions
        sa.Column("permission_level", sa.String(20), nullable=False, server_default="view"),  # view, edit

        # Timestamps
        sa.Column("shared_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),  # Optional expiration
    )

    # Indexes
    op.create_index("ix_dashboard_shares_dashboard_id", "dashboard_shares", ["dashboard_id"])
    op.create_index("ix_dashboard_shares_shared_with", "dashboard_shares", ["shared_with_user_id"])

    # Unique constraint: Ein User kann ein Dashboard nicht mehrfach sharen mit demselben User
    op.create_unique_constraint(
        "uq_dashboard_shares_unique",
        "dashboard_shares",
        ["dashboard_id", "shared_with_user_id"]
    )

    # Constraint: User kann Dashboard nicht mit sich selbst teilen
    op.execute("""
        ALTER TABLE dashboard_shares
        ADD CONSTRAINT chk_dashboard_shares_not_self
        CHECK (shared_by_user_id != shared_with_user_id)
    """)


def downgrade() -> None:
    # Drop dashboard_shares table
    op.drop_table("dashboard_shares")

    # Drop favorite index and column
    op.drop_index("ix_user_dashboards_favorite", "user_dashboards")
    op.drop_column("user_dashboards", "is_favorite")
