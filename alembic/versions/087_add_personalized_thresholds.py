# -*- coding: utf-8 -*-
"""Add personalized thresholds tables.

Revision ID: 087_add_personalized_thresholds
Revises: 086_add_approval_system
Create Date: 2026-01-09

PHASE 0 CRITICAL: Persisting user-specific thresholds to database.
Previously all thresholds were stored in-memory only, which meant:
- Data loss on restart
- No persistence across sessions
- No history tracking
- No multi-instance support

This migration adds:
- privat_user_thresholds: Personalized threshold values per user
- privat_user_profiles: User profiles for threshold calculation
- privat_threshold_adjustments: Audit log of threshold changes
- privat_threshold_recommendations: AI-generated recommendations
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

# revision identifiers, used by Alembic.
revision = "087"
down_revision = "086"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # User Profiles Table
    op.create_table(
        "privat_user_profiles",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True),
        # Profession and Risk
        sa.Column("profession_type", sa.String(50), nullable=False, default="employee"),
        sa.Column("risk_tolerance", sa.String(50), nullable=False, default="moderate"),
        sa.Column("income_stability", sa.Numeric(3, 2), nullable=False, default=0.7),  # 0-1
        # Demographics
        sa.Column("age_group", sa.String(20), nullable=True),  # "18-30", "31-45", etc.
        sa.Column("household_size", sa.Integer, nullable=False, default=2),
        # Financial Situation
        sa.Column("has_dependents", sa.Boolean, nullable=False, default=False),
        sa.Column("is_homeowner", sa.Boolean, nullable=False, default=False),
        sa.Column("has_pension_plan", sa.Boolean, nullable=False, default=True),
        # Preferences
        sa.Column("prefers_aggressive_alerts", sa.Boolean, nullable=False, default=False),
        sa.Column("prefers_conservative_targets", sa.Boolean, nullable=False, default=True),
        # Learning data
        sa.Column("feedback_history", JSONB, nullable=True, default={}),
        # Timestamps
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
    )
    op.create_index("idx_user_profiles_user_id", "privat_user_profiles", ["user_id"])

    # User Thresholds Table
    op.create_table(
        "privat_user_thresholds",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        # Threshold identification
        sa.Column("threshold_type", sa.String(50), nullable=False),  # e.g., "dti_warning", "emergency_fund_min"
        # Values
        sa.Column("default_value", sa.Numeric(10, 4), nullable=False),
        sa.Column("current_value", sa.Numeric(10, 4), nullable=False),
        # Adjustment tracking
        sa.Column("adjustment_source", sa.String(50), nullable=False),  # system_default, user_preference, learned_behavior, etc.
        sa.Column("adjustment_reason", sa.Text, nullable=True),
        # Confidence and Effectiveness
        sa.Column("confidence", sa.Numeric(3, 2), nullable=False, default=0.7),  # 0-1
        sa.Column("times_triggered", sa.Integer, nullable=False, default=0),
        sa.Column("times_acted_on", sa.Integer, nullable=False, default=0),
        sa.Column("effectiveness_score", sa.Numeric(3, 2), nullable=False, default=1.0),  # 0-1
        # Timestamps
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        # Unique constraint: one threshold type per user
        sa.UniqueConstraint("user_id", "threshold_type", name="uq_user_threshold_type"),
    )
    op.create_index("idx_user_thresholds_user_id", "privat_user_thresholds", ["user_id"])
    op.create_index("idx_user_thresholds_type", "privat_user_thresholds", ["threshold_type"])
    op.create_index("idx_user_thresholds_user_type", "privat_user_thresholds", ["user_id", "threshold_type"])

    # Threshold Adjustments (Audit Log)
    op.create_table(
        "privat_threshold_adjustments",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("threshold_type", sa.String(50), nullable=False),
        # Values
        sa.Column("previous_value", sa.Numeric(10, 4), nullable=False),
        sa.Column("new_value", sa.Numeric(10, 4), nullable=False),
        # Adjustment details
        sa.Column("adjustment_source", sa.String(50), nullable=False),
        sa.Column("reason", sa.Text, nullable=True),
        sa.Column("confidence", sa.Numeric(3, 2), nullable=False, default=0.7),
        # Rollback support
        sa.Column("can_rollback", sa.Boolean, nullable=False, default=True),
        sa.Column("rolled_back", sa.Boolean, nullable=False, default=False),
        sa.Column("rolled_back_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rolled_back_by", UUID(as_uuid=True), nullable=True),
        # Timestamp
        sa.Column("applied_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
    )
    op.create_index("idx_threshold_adjustments_user", "privat_threshold_adjustments", ["user_id"])
    op.create_index("idx_threshold_adjustments_type", "privat_threshold_adjustments", ["threshold_type"])
    op.create_index("idx_threshold_adjustments_applied", "privat_threshold_adjustments", ["applied_at"])

    # Threshold Recommendations
    op.create_table(
        "privat_threshold_recommendations",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("threshold_type", sa.String(50), nullable=False),
        # Values
        sa.Column("current_value", sa.Numeric(10, 4), nullable=False),
        sa.Column("recommended_value", sa.Numeric(10, 4), nullable=False),
        # Recommendation details
        sa.Column("reason", sa.Text, nullable=False),
        sa.Column("confidence", sa.Numeric(3, 2), nullable=False, default=0.7),
        sa.Column("potential_impact", sa.Text, nullable=True),
        # Status
        sa.Column("accepted", sa.Boolean, nullable=True),  # null = pending
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        # Validity
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("idx_threshold_recommendations_user", "privat_threshold_recommendations", ["user_id"])
    op.create_index("idx_threshold_recommendations_pending", "privat_threshold_recommendations",
                    ["user_id", "accepted"], postgresql_where=sa.text("accepted IS NULL"))

    # Add trigger for updated_at
    op.execute("""
        CREATE OR REPLACE FUNCTION update_privat_threshold_updated_at()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = NOW();
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)

    op.execute("""
        CREATE TRIGGER trigger_update_privat_user_profiles_updated_at
        BEFORE UPDATE ON privat_user_profiles
        FOR EACH ROW EXECUTE FUNCTION update_privat_threshold_updated_at();
    """)

    op.execute("""
        CREATE TRIGGER trigger_update_privat_user_thresholds_updated_at
        BEFORE UPDATE ON privat_user_thresholds
        FOR EACH ROW EXECUTE FUNCTION update_privat_threshold_updated_at();
    """)


def downgrade() -> None:
    # Drop triggers
    op.execute("DROP TRIGGER IF EXISTS trigger_update_privat_user_thresholds_updated_at ON privat_user_thresholds")
    op.execute("DROP TRIGGER IF EXISTS trigger_update_privat_user_profiles_updated_at ON privat_user_profiles")
    op.execute("DROP FUNCTION IF EXISTS update_privat_threshold_updated_at()")

    # Drop tables in reverse order
    op.drop_table("privat_threshold_recommendations")
    op.drop_table("privat_threshold_adjustments")
    op.drop_table("privat_user_thresholds")
    op.drop_table("privat_user_profiles")
