# -*- coding: utf-8 -*-
"""Add Supplier OCR Templates tables.

Vision 2026+ Feature #2: Dokumenten-Template-System (Lieferanten-spezifisch)
OCR-Genauigkeit von 95% auf 99%+ fuer wiederkehrende Lieferanten.

Revision ID: 139_add_supplier_ocr_templates
Revises: 138_add_communication_hub
Create Date: 2026-01-28

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '139_add_supplier_ocr_templates'
down_revision: Union[str, None] = '138_add_communication_hub'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create supplier_ocr_templates and related tables."""

    # Create supplier_ocr_templates table
    op.create_table(
        'supplier_ocr_templates',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('entity_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('company_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('document_type', sa.String(50), nullable=False, server_default='invoice_incoming'),
        sa.Column('version', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('matching_strategy', sa.String(30), nullable=False, server_default='combined'),
        sa.Column('logo_fingerprint', sa.String(500), nullable=True),
        sa.Column('layout_fingerprint', sa.String(500), nullable=True),
        sa.Column('text_anchors', postgresql.JSONB(astext_type=sa.Text()), nullable=True, server_default='[]'),
        sa.Column('header_patterns', postgresql.JSONB(astext_type=sa.Text()), nullable=True, server_default='[]'),
        sa.Column('thumbnail_base64', sa.Text(), nullable=True),
        sa.Column('field_definitions', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default='[]'),
        sa.Column('training_document_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('accuracy_score', sa.Float(), nullable=True),
        sa.Column('last_accuracy_test_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('usage_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('successful_extractions', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('failed_extractions', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('average_confidence', sa.Float(), nullable=True),
        sa.Column('last_used_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('is_verified', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('auto_apply', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text('now()')),
        sa.Column('created_by_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('verified_by_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.ForeignKeyConstraint(['company_id'], ['companies.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['entity_id'], ['business_entities.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['verified_by_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )

    # Create indexes for supplier_ocr_templates
    op.create_index('ix_ocr_template_entity_id', 'supplier_ocr_templates', ['entity_id'])
    op.create_index('ix_ocr_template_company_id', 'supplier_ocr_templates', ['company_id'])
    op.create_index('ix_ocr_template_entity_company', 'supplier_ocr_templates', ['entity_id', 'company_id'])
    op.create_index('ix_ocr_template_document_type', 'supplier_ocr_templates', ['document_type'])
    op.create_index('ix_ocr_template_active', 'supplier_ocr_templates', ['is_active', 'auto_apply'])

    # Create ocr_template_samples table
    op.create_table(
        'ocr_template_samples',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('template_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('document_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('company_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('original_extraction', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('corrected_extraction', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('corrected_fields', postgresql.JSONB(astext_type=sa.Text()), nullable=True, server_default='[]'),
        sa.Column('original_confidence', sa.Float(), nullable=True),
        sa.Column('improvement_achieved', sa.Float(), nullable=True),
        sa.Column('is_verified', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('is_used_for_training', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text('now()')),
        sa.Column('corrected_by_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.ForeignKeyConstraint(['company_id'], ['companies.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['document_id'], ['documents.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['template_id'], ['supplier_ocr_templates.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['corrected_by_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )

    # Create indexes for ocr_template_samples
    op.create_index('ix_ocr_sample_template_id', 'ocr_template_samples', ['template_id'])
    op.create_index('ix_ocr_sample_document_id', 'ocr_template_samples', ['document_id'])
    op.create_index('ix_ocr_sample_template_doc', 'ocr_template_samples', ['template_id', 'document_id'])

    # Create ocr_template_match_logs table
    op.create_table(
        'ocr_template_match_logs',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('document_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('company_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('matched_template_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('match_confidence', sa.Float(), nullable=True),
        sa.Column('match_strategy_used', sa.String(30), nullable=True),
        sa.Column('match_details', postgresql.JSONB(astext_type=sa.Text()), nullable=True, server_default='{}'),
        sa.Column('candidates_checked', postgresql.JSONB(astext_type=sa.Text()), nullable=True, server_default='[]'),
        sa.Column('extraction_applied', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('extraction_confidence', sa.Float(), nullable=True),
        sa.Column('fields_extracted', sa.Integer(), nullable=True),
        sa.Column('match_duration_ms', sa.Integer(), nullable=True),
        sa.Column('extraction_duration_ms', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['company_id'], ['companies.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['document_id'], ['documents.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['matched_template_id'], ['supplier_ocr_templates.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )

    # Create indexes for ocr_template_match_logs
    op.create_index('ix_ocr_match_log_document', 'ocr_template_match_logs', ['document_id'])
    op.create_index('ix_ocr_match_log_template', 'ocr_template_match_logs', ['matched_template_id'])
    op.create_index('ix_ocr_match_log_created', 'ocr_template_match_logs', ['created_at'])


def downgrade() -> None:
    """Drop supplier OCR templates tables."""
    op.drop_index('ix_ocr_match_log_created', table_name='ocr_template_match_logs')
    op.drop_index('ix_ocr_match_log_template', table_name='ocr_template_match_logs')
    op.drop_index('ix_ocr_match_log_document', table_name='ocr_template_match_logs')
    op.drop_table('ocr_template_match_logs')

    op.drop_index('ix_ocr_sample_template_doc', table_name='ocr_template_samples')
    op.drop_index('ix_ocr_sample_document_id', table_name='ocr_template_samples')
    op.drop_index('ix_ocr_sample_template_id', table_name='ocr_template_samples')
    op.drop_table('ocr_template_samples')

    op.drop_index('ix_ocr_template_active', table_name='supplier_ocr_templates')
    op.drop_index('ix_ocr_template_document_type', table_name='supplier_ocr_templates')
    op.drop_index('ix_ocr_template_entity_company', table_name='supplier_ocr_templates')
    op.drop_index('ix_ocr_template_company_id', table_name='supplier_ocr_templates')
    op.drop_index('ix_ocr_template_entity_id', table_name='supplier_ocr_templates')
    op.drop_table('supplier_ocr_templates')
