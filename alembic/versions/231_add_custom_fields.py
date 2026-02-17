"""Add custom field definitions table and custom_field_values JSONB column.

Revision ID: 231
Revises: 230
Create Date: 2026-02-16

Creates:
- custom_field_definitions table for field metadata
- custom_field_values JSONB column on documents table
- GIN index on custom_field_values for JSONB search
"""

import uuid

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "231"
down_revision = "230"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Create custom_field_definitions table
    op.create_table(
        "custom_field_definitions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("label", sa.String(200), nullable=False),
        sa.Column("description", sa.String(500), nullable=True),
        sa.Column("field_type", sa.String(20), nullable=False),
        sa.Column("document_type", sa.String(50), nullable=True),
        sa.Column("required", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("default_value", sa.String(500), nullable=True),
        sa.Column("validation_rules", JSONB(), nullable=True),
        sa.Column("dropdown_options", JSONB(), nullable=True),
        sa.Column("lookup_entity", sa.String(100), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_searchable", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("is_filterable", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column(
            "company_id",
            UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "created_by",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        # Constraints
        sa.UniqueConstraint(
            "company_id", "document_type", "name",
            name="uq_custom_field_company_doctype_name",
        ),
    )

    # Indexes
    op.create_index(
        "ix_custom_field_def_company_id",
        "custom_field_definitions",
        ["company_id"],
    )
    op.create_index(
        "ix_custom_field_def_document_type",
        "custom_field_definitions",
        ["document_type"],
    )
    op.create_index(
        "ix_custom_field_def_is_active",
        "custom_field_definitions",
        ["is_active"],
    )
    op.create_index(
        "ix_custom_field_def_company_active",
        "custom_field_definitions",
        ["company_id", "is_active", "document_type"],
    )

    # 2. Add custom_field_values JSONB column to documents table
    op.add_column(
        "documents",
        sa.Column(
            "custom_field_values",
            JSONB(),
            nullable=True,
            server_default=sa.text("'{}'::jsonb"),
            comment="Benutzerdefinierte Feldwerte (JSONB)",
        ),
    )

    # 3. GIN index on custom_field_values for efficient JSONB search
    op.create_index(
        "ix_documents_custom_field_values_gin",
        "documents",
        ["custom_field_values"],
        postgresql_using="gin",
    )


def downgrade() -> None:
    # Remove GIN index
    op.drop_index("ix_documents_custom_field_values_gin", table_name="documents")

    # Remove column
    op.drop_column("documents", "custom_field_values")

    # Drop indexes
    op.drop_index(
        "ix_custom_field_def_company_active",
        table_name="custom_field_definitions",
    )
    op.drop_index(
        "ix_custom_field_def_is_active",
        table_name="custom_field_definitions",
    )
    op.drop_index(
        "ix_custom_field_def_document_type",
        table_name="custom_field_definitions",
    )
    op.drop_index(
        "ix_custom_field_def_company_id",
        table_name="custom_field_definitions",
    )

    # Drop table
    op.drop_table("custom_field_definitions")
