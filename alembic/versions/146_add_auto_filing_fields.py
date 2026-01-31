"""Add auto-filing fields to BusinessEntity and Company.

Adds:
- default_folder_id to BusinessEntity for auto-filing support
- filing_rules JSONB to Company for custom auto-filing rules

Phase 11.1 & 11.2 of Enterprise Transformation Roadmap.

Revision ID: 146_add_auto_filing_fields
Revises: 145_add_datev_connect
Create Date: 2026-01-31
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB


# revision identifiers, used by Alembic.
revision = "146_add_auto_filing_fields"
down_revision = "145_add_datev_connect"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add auto-filing fields."""

    # =========================================================================
    # Phase 11.1: Add default_folder_id to BusinessEntity
    # =========================================================================
    op.add_column(
        "business_entities",
        sa.Column(
            "default_folder_id",
            UUID(as_uuid=True),
            sa.ForeignKey("folders.id", ondelete="SET NULL"),
            nullable=True,
            comment="Default folder for auto-filing documents from this entity",
        ),
    )

    # Index for efficient folder lookups
    op.create_index(
        "ix_business_entities_default_folder_id",
        "business_entities",
        ["default_folder_id"],
        postgresql_where=sa.text("default_folder_id IS NOT NULL"),
    )

    # =========================================================================
    # Phase 11.2: Add filing_rules JSONB to Company
    # =========================================================================
    op.add_column(
        "companies",
        sa.Column(
            "filing_rules",
            JSONB,
            nullable=True,
            server_default=sa.text("'{}'::jsonb"),
            comment=(
                "Custom auto-filing rules per document type. "
                "Format: {'invoice': {'folder_id': 'uuid', 'folder_name': 'Custom'}, ...}"
            ),
        ),
    )


def downgrade() -> None:
    """Remove auto-filing fields."""

    # Remove filing_rules from companies
    op.drop_column("companies", "filing_rules")

    # Remove default_folder_id index and column from business_entities
    op.drop_index(
        "ix_business_entities_default_folder_id",
        table_name="business_entities",
    )
    op.drop_column("business_entities", "default_folder_id")
