"""Add batch job cancellation and scheduled exports support.

Revision ID: 055_add_batch_job_cancellation
Revises: 054_add_mahnungswesen_tables
Create Date: 2025-12-29

Adds:
- Cancellation fields to batch_jobs table for Export Improvements Task 3
- ScheduledExport table for Export Improvements Task 4
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '055_add_batch_job_cancellation'
down_revision: Union[str, None] = '054_add_mahnungswesen'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add cancellation fields to rag_batch_jobs and create scheduled_exports table."""

    # ==== Task 3: Batch Job Cancellation ====
    # Note: Using rag_batch_jobs as that's the actual table name in the DB

    # Add is_cancelled column
    op.add_column(
        'rag_batch_jobs',
        sa.Column('is_cancelled', sa.Boolean(), nullable=True, default=False)
    )

    # Add cancelled_at column
    op.add_column(
        'rag_batch_jobs',
        sa.Column('cancelled_at', sa.DateTime(timezone=True), nullable=True)
    )

    # Add cancelled_by_id column with foreign key
    op.add_column(
        'rag_batch_jobs',
        sa.Column('cancelled_by_id', sa.UUID(), nullable=True)
    )

    # Add foreign key constraint
    op.create_foreign_key(
        'fk_rag_batch_jobs_cancelled_by_id',
        'rag_batch_jobs',
        'users',
        ['cancelled_by_id'],
        ['id']
    )

    # Set default value for existing rows
    op.execute("UPDATE rag_batch_jobs SET is_cancelled = FALSE WHERE is_cancelled IS NULL")

    # Make is_cancelled non-nullable after setting defaults
    op.alter_column(
        'rag_batch_jobs',
        'is_cancelled',
        existing_type=sa.Boolean(),
        nullable=False,
        server_default=sa.text('FALSE')
    )

    # ==== Task 4: Scheduled Exports ====

    op.create_table(
        'scheduled_exports',
        sa.Column('id', sa.UUID(), primary_key=True),
        sa.Column('user_id', sa.UUID(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),

        # Schedule (Cron-Format)
        sa.Column('cron_expression', sa.String(100), nullable=False),
        sa.Column('timezone', sa.String(50), server_default='Europe/Berlin'),

        # Export-Konfiguration
        sa.Column('export_type', sa.String(50), nullable=False),
        sa.Column('export_format', sa.String(20), nullable=False),
        sa.Column('filter_config', sa.JSON(), nullable=True),
        sa.Column('include_text', sa.Boolean(), server_default='true'),
        sa.Column('include_metadata', sa.Boolean(), server_default='true'),

        # Status
        sa.Column('is_active', sa.Boolean(), server_default='true'),
        sa.Column('last_run_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('next_run_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_run_status', sa.String(20), nullable=True),
        sa.Column('last_run_job_id', sa.UUID(), sa.ForeignKey('rag_batch_jobs.id'), nullable=True),

        # Notification
        sa.Column('notify_email', sa.Boolean(), server_default='true'),
        sa.Column('notify_on_failure_only', sa.Boolean(), server_default='false'),
        sa.Column('notification_email', sa.String(255), nullable=True),

        # Statistics
        sa.Column('total_runs', sa.Integer(), server_default='0'),
        sa.Column('successful_runs', sa.Integer(), server_default='0'),
        sa.Column('failed_runs', sa.Integer(), server_default='0'),

        # Timestamps
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # Create indexes for scheduled_exports
    op.create_index('ix_scheduled_exports_user_id', 'scheduled_exports', ['user_id'])
    op.create_index('ix_scheduled_exports_is_active', 'scheduled_exports', ['is_active'])
    op.create_index('ix_scheduled_exports_next_run_at', 'scheduled_exports', ['next_run_at'])


def downgrade() -> None:
    """Remove cancellation fields from rag_batch_jobs and drop scheduled_exports table."""

    # ==== Task 4: Drop Scheduled Exports ====

    op.drop_index('ix_scheduled_exports_next_run_at', table_name='scheduled_exports')
    op.drop_index('ix_scheduled_exports_is_active', table_name='scheduled_exports')
    op.drop_index('ix_scheduled_exports_user_id', table_name='scheduled_exports')
    op.drop_table('scheduled_exports')

    # ==== Task 3: Remove Batch Job Cancellation ====

    # Drop foreign key constraint
    op.drop_constraint('fk_rag_batch_jobs_cancelled_by_id', 'rag_batch_jobs', type_='foreignkey')

    # Drop columns
    op.drop_column('rag_batch_jobs', 'cancelled_by_id')
    op.drop_column('rag_batch_jobs', 'cancelled_at')
    op.drop_column('rag_batch_jobs', 'is_cancelled')
