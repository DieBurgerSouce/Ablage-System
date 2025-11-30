"""Add GDPR deletion fields to User model.

Revision ID: 011_add_gdpr_deletion_fields
Revises: 010_add_2fa_fields
Create Date: 2024-11-30

Implements: GDPR Art. 17 - Right to Erasure (Recht auf Löschung)
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers
revision = '011_add_gdpr_deletion_fields'
down_revision = '010_add_2fa_fields'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add GDPR deletion tracking fields to users table."""
    # Add deletion request tracking fields
    op.add_column(
        'users',
        sa.Column('deletion_requested_at', sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        'users',
        sa.Column('deletion_scheduled_for', sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        'users',
        sa.Column('deletion_reason', sa.String(500), nullable=True)
    )
    op.add_column(
        'users',
        sa.Column('deletion_confirmed', sa.Boolean(), nullable=False, server_default='false')
    )

    # Index for Celery task that searches for due deletions
    # PostgreSQL partial index - only index rows where deletion is scheduled
    op.create_index(
        'ix_users_deletion_scheduled',
        'users',
        ['deletion_scheduled_for'],
        postgresql_where=sa.text('deletion_scheduled_for IS NOT NULL')
    )


def downgrade() -> None:
    """Remove GDPR deletion tracking fields."""
    op.drop_index('ix_users_deletion_scheduled', table_name='users')
    op.drop_column('users', 'deletion_confirmed')
    op.drop_column('users', 'deletion_reason')
    op.drop_column('users', 'deletion_scheduled_for')
    op.drop_column('users', 'deletion_requested_at')
