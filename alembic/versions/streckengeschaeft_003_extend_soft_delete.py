"""
Streckengeschaeft - Extend Soft Delete to Child Tables

Adds soft-delete columns to child tables:
- drop_shipment_positions
- transaction_parties
- proof_documents

This ensures GDPR/GoBD compliant data retention where child records
are also soft-deleted rather than cascade deleted.

Revision ID: streckengeschaeft_003
Create Date: 2024-12-29
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = 'streckengeschaeft_003'
down_revision = 'streckengeschaeft_001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add soft-delete columns to child tables."""

    # Add soft-delete columns to drop_shipment_positions
    op.add_column(
        'drop_shipment_positions',
        sa.Column('is_deleted', sa.Boolean(), server_default='false', nullable=False)
    )
    op.add_column(
        'drop_shipment_positions',
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        'drop_shipment_positions',
        sa.Column('deleted_by', postgresql.UUID(as_uuid=True), nullable=True)
    )

    # Add soft-delete columns to transaction_parties
    op.add_column(
        'transaction_parties',
        sa.Column('is_deleted', sa.Boolean(), server_default='false', nullable=False)
    )
    op.add_column(
        'transaction_parties',
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        'transaction_parties',
        sa.Column('deleted_by', postgresql.UUID(as_uuid=True), nullable=True)
    )

    # Add soft-delete columns to proof_documents
    op.add_column(
        'proof_documents',
        sa.Column('is_deleted', sa.Boolean(), server_default='false', nullable=False)
    )
    op.add_column(
        'proof_documents',
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        'proof_documents',
        sa.Column('deleted_by', postgresql.UUID(as_uuid=True), nullable=True)
    )

    # Add indexes for soft-delete filtering
    op.create_index(
        'ix_positions_not_deleted',
        'drop_shipment_positions',
        ['is_deleted'],
        postgresql_where=sa.text("is_deleted = false")
    )
    op.create_index(
        'ix_parties_not_deleted',
        'transaction_parties',
        ['is_deleted'],
        postgresql_where=sa.text("is_deleted = false")
    )
    op.create_index(
        'ix_proofs_not_deleted',
        'proof_documents',
        ['is_deleted'],
        postgresql_where=sa.text("is_deleted = false")
    )


def downgrade() -> None:
    """Remove soft-delete columns from child tables."""

    # Drop indexes
    op.drop_index('ix_proofs_not_deleted', 'proof_documents')
    op.drop_index('ix_parties_not_deleted', 'transaction_parties')
    op.drop_index('ix_positions_not_deleted', 'drop_shipment_positions')

    # Drop columns from proof_documents
    op.drop_column('proof_documents', 'deleted_by')
    op.drop_column('proof_documents', 'deleted_at')
    op.drop_column('proof_documents', 'is_deleted')

    # Drop columns from transaction_parties
    op.drop_column('transaction_parties', 'deleted_by')
    op.drop_column('transaction_parties', 'deleted_at')
    op.drop_column('transaction_parties', 'is_deleted')

    # Drop columns from drop_shipment_positions
    op.drop_column('drop_shipment_positions', 'deleted_by')
    op.drop_column('drop_shipment_positions', 'deleted_at')
    op.drop_column('drop_shipment_positions', 'is_deleted')
