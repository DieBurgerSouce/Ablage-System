"""Add soft-delete columns to expense_reports.

Revision ID: 091
Revises: 090
Create Date: 2026-01-11

Adds deleted_at and deleted_by_id columns to expense_reports table
for soft-delete functionality.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = '091'
down_revision = '090'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add soft-delete columns to expense_reports."""
    # Add deleted_at column
    op.add_column(
        'expense_reports',
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True)
    )

    # Add deleted_by_id column
    op.add_column(
        'expense_reports',
        sa.Column(
            'deleted_by_id',
            postgresql.UUID(as_uuid=True),
            nullable=True
        )
    )

    # Add foreign key constraint for deleted_by_id
    op.create_foreign_key(
        'fk_expense_reports_deleted_by_id_users',
        'expense_reports',
        'users',
        ['deleted_by_id'],
        ['id'],
        ondelete='SET NULL'
    )

    # Add index for soft-delete queries
    op.create_index(
        'ix_expense_reports_deleted_at',
        'expense_reports',
        ['deleted_at'],
        postgresql_where=sa.text('deleted_at IS NULL')
    )


def downgrade() -> None:
    """Remove soft-delete columns from expense_reports."""
    op.drop_index('ix_expense_reports_deleted_at', table_name='expense_reports')
    op.drop_constraint(
        'fk_expense_reports_deleted_by_id_users',
        'expense_reports',
        type_='foreignkey'
    )
    op.drop_column('expense_reports', 'deleted_by_id')
    op.drop_column('expense_reports', 'deleted_at')
