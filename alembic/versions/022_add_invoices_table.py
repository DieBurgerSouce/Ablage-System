"""Add invoices table for financial tracking

Revision ID: 022_add_invoices_table
Revises: 021_add_notifications_table
Create Date: 2026-01-04

Implements financial tracking system for:
- Invoice management
- Payment status tracking
- Financial aggregations and reporting
- Deadline monitoring

NOTE: company_id column added without FK constraint here because
companies table is created later in migration 057. FK constraint
is added in a later migration after companies table exists.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
from decimal import Decimal

# revision identifiers
revision = '022'
down_revision = '021b'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add invoices table."""
    op.create_table(
        'invoices',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('document_id', UUID(as_uuid=True), sa.ForeignKey('documents.id', ondelete='CASCADE'), nullable=False, unique=True),
        # NOTE: company_id ohne FK weil companies Tabelle erst in Migration 057 erstellt wird
        sa.Column('company_id', UUID(as_uuid=True), nullable=True),

        # Invoice details
        sa.Column('invoice_number', sa.String(100), nullable=False, unique=True),
        sa.Column('invoice_date', sa.Date, nullable=False),
        sa.Column('due_date', sa.Date, nullable=False),

        # Amounts
        sa.Column('subtotal', sa.Numeric(12, 2), nullable=False),
        sa.Column('tax_amount', sa.Numeric(12, 2), server_default='0'),
        sa.Column('total_amount', sa.Numeric(12, 2), nullable=False),
        sa.Column('currency', sa.String(3), server_default='EUR', nullable=False),

        # Payment status
        sa.Column('status', sa.String(20), server_default='pending', nullable=False),
        sa.Column('payment_date', sa.Date, nullable=True),

        # Metadata
        sa.Column('notes', sa.Text, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    )

    # Create indexes for performance
    op.create_index('ix_invoices_invoice_number', 'invoices', ['invoice_number'])
    op.create_index('ix_invoices_status', 'invoices', ['status'])
    op.create_index('ix_invoices_due_date', 'invoices', ['due_date'])
    op.create_index('ix_invoices_company_date', 'invoices', ['company_id', 'invoice_date'])


def downgrade() -> None:
    """Remove invoices table."""
    op.drop_index('ix_invoices_company_date', 'invoices')
    op.drop_index('ix_invoices_due_date', 'invoices')
    op.drop_index('ix_invoices_status', 'invoices')
    op.drop_index('ix_invoices_invoice_number', 'invoices')
    op.drop_table('invoices')
