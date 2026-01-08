# -*- coding: utf-8 -*-
"""Add Finance Document History table for audit trail.

Revision ID: 056_add_finance_history
Revises: 055_add_batch_job_cancellation
Create Date: 2024-12-29

This migration adds:
- finance_document_history - Immutable audit log for finance document changes

Enterprise Features:
- Tracks all changes to finance documents
- Supports GDPR compliance requirements
- Immutable (append-only) with database-level protection
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB


# revision identifiers, used by Alembic.
revision = "056"
down_revision = "055"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create finance_document_history table."""

    # =========================================================================
    # 1. Create finance_document_history table (immutable audit log)
    # =========================================================================

    op.create_table(
        'finance_document_history',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),

        # Document reference
        sa.Column('document_id', UUID(as_uuid=True),
                  sa.ForeignKey('documents.id', ondelete='CASCADE'),
                  nullable=False, index=True),

        # User who made the change
        sa.Column('user_id', UUID(as_uuid=True),
                  sa.ForeignKey('users.id', ondelete='SET NULL'),
                  nullable=True, index=True),

        # Action
        sa.Column('action', sa.String(50), nullable=False,
                  comment='created, updated, deleted, restored, category_changed, year_changed, etc.'),

        # Change details
        sa.Column('old_values', JSONB(), server_default='{}',
                  comment='Previous values (for updates)'),
        sa.Column('new_values', JSONB(), server_default='{}',
                  comment='New values (for updates)'),
        sa.Column('changed_fields', JSONB(), server_default='[]',
                  comment='List of changed fields'),

        # Context
        sa.Column('ip_address', sa.String(45), nullable=True,
                  comment='User IP address'),
        sa.Column('user_agent', sa.String(500), nullable=True,
                  comment='Browser/Client info'),

        # Additional metadata
        sa.Column('metadata', JSONB(), server_default='{}',
                  comment='Additional context information'),

        # Human-readable description (in German)
        sa.Column('description', sa.Text(), nullable=True,
                  comment='Human-readable description of the change'),

        # Timestamp (immutable)
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )

    # Indexes for efficient querying
    op.create_index('ix_finance_doc_history_document_id',
                    'finance_document_history', ['document_id'])
    op.create_index('ix_finance_doc_history_user_id',
                    'finance_document_history', ['user_id'])
    op.create_index('ix_finance_doc_history_action',
                    'finance_document_history', ['action'])
    op.create_index('ix_finance_doc_history_created_at',
                    'finance_document_history', ['created_at'])
    op.create_index('ix_finance_doc_history_doc_created',
                    'finance_document_history', ['document_id', 'created_at'])

    # Check constraint for valid actions
    op.create_check_constraint(
        'ck_finance_doc_history_action',
        'finance_document_history',
        "action IN ('created', 'updated', 'deleted', 'restored', "
        "'category_changed', 'year_changed', 'ocr_completed', "
        "'deadline_set', 'deadline_removed', 'bulk_update')"
    )

    # =========================================================================
    # 2. Create trigger to prevent UPDATE/DELETE (immutability)
    # =========================================================================

    # Create immutability trigger function
    op.execute("""
        CREATE OR REPLACE FUNCTION prevent_finance_history_modification()
        RETURNS TRIGGER AS $$
        BEGIN
            RAISE EXCEPTION 'Finance Document History is immutable. UPDATE and DELETE are not allowed.';
            RETURN NULL;
        END;
        $$ LANGUAGE plpgsql;
    """)

    # Apply trigger for UPDATE
    op.execute("""
        CREATE TRIGGER tr_finance_doc_history_no_update
        BEFORE UPDATE ON finance_document_history
        FOR EACH ROW
        EXECUTE FUNCTION prevent_finance_history_modification();
    """)

    # Apply trigger for DELETE
    op.execute("""
        CREATE TRIGGER tr_finance_doc_history_no_delete
        BEFORE DELETE ON finance_document_history
        FOR EACH ROW
        EXECUTE FUNCTION prevent_finance_history_modification();
    """)


def downgrade() -> None:
    """Drop finance_document_history table."""

    # Drop triggers first
    op.execute("DROP TRIGGER IF EXISTS tr_finance_doc_history_no_update ON finance_document_history")
    op.execute("DROP TRIGGER IF EXISTS tr_finance_doc_history_no_delete ON finance_document_history")
    op.execute("DROP FUNCTION IF EXISTS prevent_finance_history_modification()")

    # Drop constraint
    op.drop_constraint('ck_finance_doc_history_action', 'finance_document_history', type_='check')

    # Drop indexes
    op.drop_index('ix_finance_doc_history_doc_created', table_name='finance_document_history')
    op.drop_index('ix_finance_doc_history_created_at', table_name='finance_document_history')
    op.drop_index('ix_finance_doc_history_action', table_name='finance_document_history')
    op.drop_index('ix_finance_doc_history_user_id', table_name='finance_document_history')
    op.drop_index('ix_finance_doc_history_document_id', table_name='finance_document_history')

    # Drop table
    op.drop_table('finance_document_history')
