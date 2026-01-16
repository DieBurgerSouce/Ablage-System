"""Add entity risk scoring fields.

Revision ID: 092_add_entity_risk_scoring
Revises: 091_add_expense_report_soft_delete
Create Date: 2026-01-16

Adds risk scoring fields to BusinessEntity for payment behavior analysis.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "092_add_entity_risk_scoring"
down_revision = "091_add_expense_report_soft_delete"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add risk scoring columns to business_entities."""
    # Risk Score: 0-100 (higher = riskier)
    op.add_column(
        "business_entities",
        sa.Column(
            "risk_score",
            sa.Float(),
            nullable=True,
            comment="Overall risk score 0-100 (100 = highest risk)"
        )
    )

    # Risk Factors: JSONB with detailed breakdown
    op.add_column(
        "business_entities",
        sa.Column(
            "risk_factors",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=True,
            comment="Risk factor breakdown: {payment_delay, default_rate, ...}"
        )
    )

    # Payment Behavior Score: 0-100 (higher = better payer)
    op.add_column(
        "business_entities",
        sa.Column(
            "payment_behavior_score",
            sa.Float(),
            nullable=True,
            comment="Payment behavior score 0-100 (100 = best payer)"
        )
    )

    # Last risk calculation timestamp
    op.add_column(
        "business_entities",
        sa.Column(
            "risk_calculated_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Timestamp of last risk calculation"
        )
    )

    # Index for filtering by risk
    op.create_index(
        "ix_business_entities_risk_score",
        "business_entities",
        ["risk_score"],
        unique=False
    )


def downgrade() -> None:
    """Remove risk scoring columns from business_entities."""
    op.drop_index("ix_business_entities_risk_score", table_name="business_entities")
    op.drop_column("business_entities", "risk_calculated_at")
    op.drop_column("business_entities", "payment_behavior_score")
    op.drop_column("business_entities", "risk_factors")
    op.drop_column("business_entities", "risk_score")
