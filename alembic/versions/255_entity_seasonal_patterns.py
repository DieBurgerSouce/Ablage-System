"""Add entity_seasonal_patterns table for seasonal payment pattern persistence.

Revision ID: 255
Revises: 254
Create Date: 2026-02-23
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision = "255"
down_revision = "254"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "entity_seasonal_patterns",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "entity_id",
            UUID(as_uuid=True),
            sa.ForeignKey("business_entities.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "company_id",
            UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("pattern_type", sa.String(50), nullable=False),
        sa.Column("affected_months", sa.JSON(), nullable=False),
        sa.Column(
            "avg_delay_adjustment",
            sa.Float(),
            nullable=False,
            server_default="1.0",
        ),
        sa.Column(
            "confidence",
            sa.Float(),
            nullable=False,
            server_default="0.0",
        ),
        sa.Column(
            "sample_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "last_computed_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_entity_seasonal_patterns_entity_id",
        "entity_seasonal_patterns",
        ["entity_id"],
    )
    op.create_index(
        "ix_entity_seasonal_patterns_company_id",
        "entity_seasonal_patterns",
        ["company_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_entity_seasonal_patterns_company_id",
        table_name="entity_seasonal_patterns",
    )
    op.drop_index(
        "ix_entity_seasonal_patterns_entity_id",
        table_name="entity_seasonal_patterns",
    )
    op.drop_table("entity_seasonal_patterns")
