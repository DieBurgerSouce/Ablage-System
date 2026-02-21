# -*- coding: utf-8 -*-
"""Add feature_toggle_history table for audit trail.

Revision ID: 250
Revises: 249
Create Date: 2026-02-21

Phase 7.1: Feature Toggle Admin UI API
- feature_toggle_history: Vollstaendiger Audit-Trail fuer Feature-Flag Aenderungen
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "250"
down_revision = "249"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "feature_toggle_history",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        # Soft reference to feature_flags – nullable so history survives flag deletion
        sa.Column(
            "feature_flag_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("feature_flags.id", ondelete="SET NULL"),
            nullable=True,
        ),
        # Denormalised name so records are readable even after flag deletion
        sa.Column("flag_name", sa.String(100), nullable=False),
        # Action that was taken
        sa.Column("action", sa.String(50), nullable=False),  # enabled, disabled, rollout_changed, config_changed
        # Before / after snapshots stored as JSONB for full auditability
        sa.Column("old_value", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("new_value", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        # Who made the change
        sa.Column(
            "changed_by_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        # Optional free-text reason supplied by the operator
        sa.Column("reason", sa.Text(), nullable=True),
        # Immutable timestamp – always stored with timezone
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )

    # Index: look up all history for a specific flag by name
    op.create_index(
        "ix_feature_toggle_history_flag_name",
        "feature_toggle_history",
        ["flag_name"],
    )

    # Index: filter history by the user who made the change
    op.create_index(
        "ix_feature_toggle_history_changed_by_id",
        "feature_toggle_history",
        ["changed_by_id"],
    )

    # Index: time-ordered queries (most recent first / date range scans)
    op.create_index(
        "ix_feature_toggle_history_created_at",
        "feature_toggle_history",
        ["created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_feature_toggle_history_created_at", table_name="feature_toggle_history")
    op.drop_index("ix_feature_toggle_history_changed_by_id", table_name="feature_toggle_history")
    op.drop_index("ix_feature_toggle_history_flag_name", table_name="feature_toggle_history")
    op.drop_table("feature_toggle_history")
