"""Add invoice tracking table for risk scoring.

Revision ID: 093_add_invoice_tracking
Revises: 092_add_entity_risk_scoring
Create Date: 2026-01-16

Creates invoice_tracking table to track payment information for risk scoring.
Links documents (invoices) with payment status and dunning information.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "093"
down_revision = "092"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create invoice_tracking table."""
    op.create_table(
        "invoice_tracking",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        # Document reference
        sa.Column(
            "document_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        # Invoice identification
        sa.Column("invoice_number", sa.String(100), nullable=True),
        sa.Column("invoice_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("due_date", sa.DateTime(timezone=True), nullable=True),
        # Amount information
        sa.Column("amount", sa.Float(), default=0.0),
        sa.Column("currency", sa.String(3), default="EUR"),
        # Payment status
        sa.Column(
            "status",
            sa.String(20),
            default="open",
            nullable=False,
            comment="Status: open, sent, paid, overdue, dunning, cancelled, partial",
        ),
        # Payment tracking
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("paid_amount", sa.Float(), nullable=True),
        # Dunning tracking
        sa.Column("dunning_level", sa.Integer(), default=0),
        sa.Column("last_dunning_at", sa.DateTime(timezone=True), nullable=True),
        # Audit fields
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )

    # Create indexes for common queries
    op.create_index(
        "ix_invoice_tracking_status",
        "invoice_tracking",
        ["status"],
        unique=False,
    )
    op.create_index(
        "ix_invoice_tracking_due_date",
        "invoice_tracking",
        ["due_date"],
        unique=False,
    )
    op.create_index(
        "ix_invoice_tracking_invoice_number",
        "invoice_tracking",
        ["invoice_number"],
        unique=False,
    )

    # Composite index for entity risk queries
    # (document_id + status for filtering invoices by entity and status)
    op.create_index(
        "ix_invoice_tracking_document_status",
        "invoice_tracking",
        ["document_id", "status"],
        unique=False,
    )


def downgrade() -> None:
    """Drop invoice_tracking table."""
    op.drop_index("ix_invoice_tracking_document_status", table_name="invoice_tracking")
    op.drop_index("ix_invoice_tracking_invoice_number", table_name="invoice_tracking")
    op.drop_index("ix_invoice_tracking_due_date", table_name="invoice_tracking")
    op.drop_index("ix_invoice_tracking_status", table_name="invoice_tracking")
    op.drop_table("invoice_tracking")
