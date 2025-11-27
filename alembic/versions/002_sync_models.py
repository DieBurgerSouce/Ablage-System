"""Sync models with initial schema

Revision ID: 002
Revises: 001
Create Date: 2025-11-26

This migration adds columns that exist in app/db/models.py but were
missing from the initial schema migration.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '002'
down_revision: Union[str, None] = '001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ========== tags table ==========
    # Add description column
    op.add_column('tags', sa.Column('description', sa.String(length=255), nullable=True))

    # ========== ocr_results table ==========
    # Add job_id foreign key
    op.add_column('ocr_results', sa.Column('job_id', postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        'fk_ocr_results_job_id',
        'ocr_results', 'processing_jobs',
        ['job_id'], ['id'],
        ondelete='SET NULL'
    )

    # Add missing columns from models.py
    op.add_column('ocr_results', sa.Column('word_count', sa.Integer(), nullable=True))
    op.add_column('ocr_results', sa.Column('char_count', sa.Integer(), nullable=True))
    op.add_column('ocr_results', sa.Column('page_number', sa.Integer(), nullable=True))
    op.add_column('ocr_results', sa.Column('bounding_boxes', postgresql.JSONB(astext_type=sa.Text()), nullable=True, server_default='[]'))
    op.add_column('ocr_results', sa.Column('detected_layout', postgresql.JSONB(astext_type=sa.Text()), nullable=True, server_default='{}'))
    op.add_column('ocr_results', sa.Column('detected_dates', postgresql.JSONB(astext_type=sa.Text()), nullable=True, server_default='[]'))
    op.add_column('ocr_results', sa.Column('detected_amounts', postgresql.JSONB(astext_type=sa.Text()), nullable=True, server_default='[]'))
    op.add_column('ocr_results', sa.Column('detected_ibans', postgresql.JSONB(astext_type=sa.Text()), nullable=True, server_default='[]'))
    op.add_column('ocr_results', sa.Column('detected_vat_ids', postgresql.JSONB(astext_type=sa.Text()), nullable=True, server_default='[]'))
    op.add_column('ocr_results', sa.Column('business_terms', postgresql.JSONB(astext_type=sa.Text()), nullable=True, server_default='[]'))

    # Add confidence index
    op.create_index('ix_ocr_results_confidence', 'ocr_results', ['confidence_score'], unique=False)

    # ========== api_keys table ==========
    # Add missing columns
    op.add_column('api_keys', sa.Column('description', sa.String(length=255), nullable=True))
    op.add_column('api_keys', sa.Column('permissions', postgresql.JSONB(astext_type=sa.Text()), nullable=True, server_default='[]'))
    op.add_column('api_keys', sa.Column('rate_limit', sa.Integer(), nullable=True, server_default='1000'))

    # Rename last_used_at to last_used to match model
    op.alter_column('api_keys', 'last_used_at', new_column_name='last_used')

    # ========== processing_jobs table ==========
    # Rename result_data to result to match model
    op.alter_column('processing_jobs', 'result_data', new_column_name='result')

    # Add index on created_at
    op.create_index('ix_processing_jobs_created_at', 'processing_jobs', ['created_at'], unique=False)

    # ========== document_tags table ==========
    # Add indexes for join performance
    op.create_index('ix_document_tags_document_id', 'document_tags', ['document_id'], unique=False)
    op.create_index('ix_document_tags_tag_id', 'document_tags', ['tag_id'], unique=False)


def downgrade() -> None:
    # ========== document_tags table ==========
    op.drop_index('ix_document_tags_tag_id', table_name='document_tags')
    op.drop_index('ix_document_tags_document_id', table_name='document_tags')

    # ========== processing_jobs table ==========
    op.drop_index('ix_processing_jobs_created_at', table_name='processing_jobs')
    op.alter_column('processing_jobs', 'result', new_column_name='result_data')

    # ========== api_keys table ==========
    op.alter_column('api_keys', 'last_used', new_column_name='last_used_at')
    op.drop_column('api_keys', 'rate_limit')
    op.drop_column('api_keys', 'permissions')
    op.drop_column('api_keys', 'description')

    # ========== ocr_results table ==========
    op.drop_index('ix_ocr_results_confidence', table_name='ocr_results')
    op.drop_column('ocr_results', 'business_terms')
    op.drop_column('ocr_results', 'detected_vat_ids')
    op.drop_column('ocr_results', 'detected_ibans')
    op.drop_column('ocr_results', 'detected_amounts')
    op.drop_column('ocr_results', 'detected_dates')
    op.drop_column('ocr_results', 'detected_layout')
    op.drop_column('ocr_results', 'bounding_boxes')
    op.drop_column('ocr_results', 'page_number')
    op.drop_column('ocr_results', 'char_count')
    op.drop_column('ocr_results', 'word_count')
    op.drop_constraint('fk_ocr_results_job_id', 'ocr_results', type_='foreignkey')
    op.drop_column('ocr_results', 'job_id')

    # ========== tags table ==========
    op.drop_column('tags', 'description')
