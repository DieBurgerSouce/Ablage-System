# -*- coding: utf-8 -*-
"""Add fraud detection tables for CEO fraud, IBAN manipulation, and duplicate payments.

Revision ID: 200_add_fraud_detection_tables
Revises: 199
Create Date: 2026-02-01

Tables:
- iban_baselines: Tracks IBAN history per entity for manipulation detection
- fraud_scan_results: Stores scan results with risk scores and indicators
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB


# revision identifiers, used by Alembic.
revision: str = '200_add_fraud_detection_tables'
down_revision: Union[str, None] = '150_workflow_sla'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create fraud detection tables."""

    # Table: iban_baselines
    # Tracks IBAN history per entity for IBAN manipulation detection
    op.create_table(
        'iban_baselines',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('entity_id', UUID(as_uuid=True), sa.ForeignKey('business_entities.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('company_id', UUID(as_uuid=True), sa.ForeignKey('companies.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('iban', sa.String(34), nullable=False),
        sa.Column('bic', sa.String(11), nullable=True),
        sa.Column('bank_name', sa.String(255), nullable=True),
        sa.Column('first_seen_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('last_used_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('last_verified_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('is_verified', sa.Boolean, default=False, nullable=False),
        sa.Column('is_active', sa.Boolean, default=True, nullable=False),
        sa.Column('verification_method', sa.String(50), nullable=True),  # manual, bank_statement, api
        sa.Column('verified_by_id', UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('notes', sa.Text, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
        # Unique constraint: One IBAN per entity (but can have multiple IBANs per entity)
        sa.Index('ix_iban_baselines_entity_iban', 'entity_id', 'iban', unique=True),
        sa.Index('ix_iban_baselines_company_entity', 'company_id', 'entity_id'),
    )

    # Table: fraud_scan_results
    # Stores fraud scan results with risk scores and detailed indicators
    op.create_table(
        'fraud_scan_results',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('company_id', UUID(as_uuid=True), sa.ForeignKey('companies.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('document_id', UUID(as_uuid=True), sa.ForeignKey('documents.id', ondelete='CASCADE'), nullable=True, index=True),
        sa.Column('entity_id', UUID(as_uuid=True), sa.ForeignKey('business_entities.id', ondelete='SET NULL'), nullable=True, index=True),
        sa.Column('invoice_id', UUID(as_uuid=True), sa.ForeignKey('invoice_tracking.id', ondelete='SET NULL'), nullable=True, index=True),
        # Scan metadata
        sa.Column('scan_type', sa.String(50), nullable=False, index=True),  # ceo_fraud, duplicate_payment, iban_manipulation, internal_irregularity
        sa.Column('scan_source', sa.String(50), nullable=False),  # automated, manual, ocr_trigger
        # Risk assessment
        sa.Column('risk_score', sa.Float, nullable=False),  # 0.0 - 1.0
        sa.Column('risk_level', sa.String(20), nullable=False),  # low, medium, high, critical
        sa.Column('confidence', sa.Float, nullable=False),  # 0.0 - 1.0
        # Detailed indicators (JSONB for flexibility)
        sa.Column('indicators', JSONB, default=dict, nullable=False),
        sa.Column('explanation', JSONB, default=dict, nullable=False),
        # ML model info
        sa.Column('model_version', sa.String(50), nullable=True),
        sa.Column('features_used', JSONB, default=list, nullable=True),
        # Status
        sa.Column('status', sa.String(30), default='pending', nullable=False),  # pending, reviewed, false_positive, confirmed
        sa.Column('reviewed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('reviewed_by_id', UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('review_notes', sa.Text, nullable=True),
        # Alert linkage
        sa.Column('alert_id', UUID(as_uuid=True), sa.ForeignKey('alerts.id', ondelete='SET NULL'), nullable=True, index=True),
        # Timestamps
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), index=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
        # Indexes for common queries
        sa.Index('ix_fraud_scan_results_company_type', 'company_id', 'scan_type'),
        sa.Index('ix_fraud_scan_results_company_risk', 'company_id', 'risk_level'),
        sa.Index('ix_fraud_scan_results_company_status', 'company_id', 'status'),
        sa.Index('ix_fraud_scan_results_created_at', 'created_at'),
        # Check constraints
        sa.CheckConstraint('risk_score >= 0 AND risk_score <= 1', name='ck_fraud_scan_results_risk_score'),
        sa.CheckConstraint('confidence >= 0 AND confidence <= 1', name='ck_fraud_scan_results_confidence'),
        sa.CheckConstraint("risk_level IN ('low', 'medium', 'high', 'critical')", name='ck_fraud_scan_results_risk_level'),
        sa.CheckConstraint("scan_type IN ('ceo_fraud', 'duplicate_payment', 'iban_manipulation', 'internal_irregularity', 'general')", name='ck_fraud_scan_results_scan_type'),
        sa.CheckConstraint("status IN ('pending', 'reviewed', 'false_positive', 'confirmed', 'investigating')", name='ck_fraud_scan_results_status'),
    )

    # Table: iban_change_requests
    # Workflow for IBAN change verification
    op.create_table(
        'iban_change_requests',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('company_id', UUID(as_uuid=True), sa.ForeignKey('companies.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('entity_id', UUID(as_uuid=True), sa.ForeignKey('business_entities.id', ondelete='CASCADE'), nullable=False, index=True),
        # IBAN change details
        sa.Column('old_iban', sa.String(34), nullable=True),
        sa.Column('new_iban', sa.String(34), nullable=False),
        sa.Column('new_bic', sa.String(11), nullable=True),
        sa.Column('new_bank_name', sa.String(255), nullable=True),
        # Request metadata
        sa.Column('source_document_id', UUID(as_uuid=True), sa.ForeignKey('documents.id', ondelete='SET NULL'), nullable=True),
        sa.Column('detection_method', sa.String(50), nullable=False),  # ocr, manual_entry, import
        sa.Column('detected_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        # Risk assessment
        sa.Column('risk_score', sa.Float, nullable=True),
        sa.Column('risk_indicators', JSONB, default=dict, nullable=True),
        # Verification workflow
        sa.Column('status', sa.String(30), default='pending', nullable=False),  # pending, approved, rejected, expired
        sa.Column('verification_required', sa.Boolean, default=True, nullable=False),
        sa.Column('verification_deadline', sa.DateTime(timezone=True), nullable=True),
        sa.Column('verification_method', sa.String(50), nullable=True),  # callback, document, bank_statement
        sa.Column('verified_by_id', UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('verified_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('rejection_reason', sa.Text, nullable=True),
        # Timestamps
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
        # Indexes
        sa.Index('ix_iban_change_requests_company_status', 'company_id', 'status'),
        sa.Index('ix_iban_change_requests_entity', 'entity_id'),
        # Check constraints
        sa.CheckConstraint("status IN ('pending', 'approved', 'rejected', 'expired')", name='ck_iban_change_requests_status'),
    )


def downgrade() -> None:
    """Drop fraud detection tables."""
    op.drop_table('iban_change_requests')
    op.drop_table('fraud_scan_results')
    op.drop_table('iban_baselines')
