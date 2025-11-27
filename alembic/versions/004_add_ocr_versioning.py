"""Add OCR versioning support

Revision ID: 004
Revises: 003
Create Date: 2025-11-27

Adds document versioning capabilities:
- ocr_result_versions table for storing version history
- Version tracking columns on documents table
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '004'
down_revision: Union[str, None] = '003'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ========== Create ocr_result_versions table ==========
    op.create_table(
        'ocr_result_versions',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('document_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('documents.id', ondelete='CASCADE'), nullable=False),
        sa.Column('ocr_result_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('ocr_results.id', ondelete='SET NULL'), nullable=True),

        # Version metadata
        sa.Column('version_number', sa.Integer(), nullable=False),
        sa.Column('is_current', sa.Boolean(), default=False, nullable=False),
        sa.Column('is_rollback', sa.Boolean(), default=False, nullable=True),
        sa.Column('rollback_from_version', sa.Integer(), nullable=True),

        # OCR data snapshot
        sa.Column('backend', sa.String(50), nullable=False),
        sa.Column('extracted_text', sa.Text(), nullable=True),
        sa.Column('confidence_score', sa.Float(), nullable=True),
        sa.Column('word_count', sa.Integer(), nullable=True),
        sa.Column('char_count', sa.Integer(), nullable=True),

        # German-specific data
        sa.Column('detected_dates', postgresql.JSONB(astext_type=sa.Text()),
                  nullable=True, server_default='[]'),
        sa.Column('detected_amounts', postgresql.JSONB(astext_type=sa.Text()),
                  nullable=True, server_default='[]'),
        sa.Column('detected_ibans', postgresql.JSONB(astext_type=sa.Text()),
                  nullable=True, server_default='[]'),
        sa.Column('detected_vat_ids', postgresql.JSONB(astext_type=sa.Text()),
                  nullable=True, server_default='[]'),
        sa.Column('business_terms', postgresql.JSONB(astext_type=sa.Text()),
                  nullable=True, server_default='[]'),

        # Layout data
        sa.Column('detected_layout', postgresql.JSONB(astext_type=sa.Text()),
                  nullable=True, server_default='{}'),
        sa.Column('bounding_boxes', postgresql.JSONB(astext_type=sa.Text()),
                  nullable=True, server_default='[]'),

        # Processing metadata
        sa.Column('processing_time_ms', sa.Integer(), nullable=True),
        sa.Column('german_validation_score', sa.Float(), nullable=True),
        sa.Column('has_umlauts', sa.Boolean(), default=False, nullable=True),

        # Version metadata
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column('created_by_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('version_note', sa.String(500), nullable=True),
    )

    # Create indexes for efficient queries
    op.create_index('ix_ocr_versions_document_id', 'ocr_result_versions', ['document_id'])
    op.create_index('ix_ocr_versions_version_number', 'ocr_result_versions',
                    ['document_id', 'version_number'])
    op.create_index('ix_ocr_versions_is_current', 'ocr_result_versions',
                    ['document_id', 'is_current'])
    op.create_index('ix_ocr_versions_created_at', 'ocr_result_versions', ['created_at'])

    # ========== Add version tracking columns to documents table ==========
    op.add_column('documents',
                  sa.Column('current_version_number', sa.Integer(), nullable=True, server_default='0'))
    op.add_column('documents',
                  sa.Column('total_versions', sa.Integer(), nullable=True, server_default='0'))


def downgrade() -> None:
    # ========== Remove columns from documents table ==========
    op.drop_column('documents', 'total_versions')
    op.drop_column('documents', 'current_version_number')

    # ========== Drop indexes ==========
    op.drop_index('ix_ocr_versions_created_at', table_name='ocr_result_versions')
    op.drop_index('ix_ocr_versions_is_current', table_name='ocr_result_versions')
    op.drop_index('ix_ocr_versions_version_number', table_name='ocr_result_versions')
    op.drop_index('ix_ocr_versions_document_id', table_name='ocr_result_versions')

    # ========== Drop ocr_result_versions table ==========
    op.drop_table('ocr_result_versions')
