"""Add document integrity tables (Hash-Chain, Merkle-Tree)

Revision ID: 215_add_document_integrity_tables
Revises: 214_add_calendar_sync_fields
Create Date: 2026-02-13

Adds tables for document integrity verification:
- document_hashes: SHA-256 hashes per document
- merkle_tree_nodes: Daily Merkle tree nodes
- integrity_reports: Exportable verification reports
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '215_add_document_integrity_tables'
down_revision: str = '214_add_calendar_sync_fields'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create document integrity tables."""

    # Create verification_status enum
    verification_status_enum = postgresql.ENUM(
        'unverified', 'verified', 'tampered',
        name='verification_status',
        create_type=True,
    )
    verification_status_enum.create(op.get_bind(), checkfirst=True)

    # =========================================================================
    # document_hashes
    # =========================================================================
    op.create_table(
        'document_hashes',
        sa.Column('id', sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            'document_id',
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey('documents.id', ondelete='CASCADE'),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            'company_id',
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey('companies.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column('file_hash', sa.String(64), nullable=False),
        sa.Column('hash_algorithm', sa.String(20), nullable=False, server_default='sha-256'),
        sa.Column('file_size_bytes', sa.BigInteger(), nullable=False),
        sa.Column('computed_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('verified_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('verification_status', sa.String(20), nullable=False, server_default='unverified'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    )

    op.create_index('ix_document_hashes_document_id', 'document_hashes', ['document_id'])
    op.create_index('ix_document_hashes_file_hash', 'document_hashes', ['file_hash'])
    op.create_index('ix_document_hashes_company_id', 'document_hashes', ['company_id'])

    # =========================================================================
    # merkle_tree_nodes
    # =========================================================================
    op.create_table(
        'merkle_tree_nodes',
        sa.Column('id', sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            'company_id',
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey('companies.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column('tree_date', sa.Date(), nullable=False),
        sa.Column('node_hash', sa.String(64), nullable=False),
        sa.Column('parent_hash', sa.String(64), nullable=True),
        sa.Column('level', sa.Integer(), nullable=False),
        sa.Column('position', sa.Integer(), nullable=False),
        sa.Column(
            'document_hash_id',
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey('document_hashes.id', ondelete='SET NULL'),
            nullable=True,
        ),
        sa.Column('merkle_root', sa.String(64), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_index('ix_merkle_tree_nodes_tree_date', 'merkle_tree_nodes', ['tree_date'])
    op.create_index('ix_merkle_tree_nodes_company_date', 'merkle_tree_nodes', ['company_id', 'tree_date'])
    op.create_index('ix_merkle_tree_nodes_document_hash_id', 'merkle_tree_nodes', ['document_hash_id'])

    # =========================================================================
    # integrity_reports
    # =========================================================================
    op.create_table(
        'integrity_reports',
        sa.Column('id', sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            'company_id',
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey('companies.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column('report_date', sa.Date(), nullable=False),
        sa.Column('total_documents', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('verified_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('tampered_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('unverified_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('merkle_root', sa.String(64), nullable=False),
        sa.Column('report_data', postgresql.JSONB(), server_default='{}'),
        sa.Column(
            'generated_by',
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey('users.id', ondelete='SET NULL'),
            nullable=True,
        ),
        sa.Column('generated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_index('ix_integrity_reports_company_id', 'integrity_reports', ['company_id'])
    op.create_index('ix_integrity_reports_company_date', 'integrity_reports', ['company_id', 'report_date'])


def downgrade() -> None:
    """Drop document integrity tables."""
    op.drop_table('integrity_reports')
    op.drop_table('merkle_tree_nodes')
    op.drop_table('document_hashes')

    # Drop enum type
    postgresql.ENUM(name='verification_status').drop(op.get_bind(), checkfirst=True)
