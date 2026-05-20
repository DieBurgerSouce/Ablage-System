"""Add Portal and ESG models (Phase 5.2 & 7.4).

Revision ID: 204_add_portal_and_esg
Revises: 203_add_psd2_banking_integration
Create Date: 2026-02-02

Features:
- Kundenportal (Self-Service)
- ESG-Reporting (Environmental, Social, Governance)
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '204_add_portal_and_esg'
down_revision: str = '203_add_psd2_banking_integration'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ==================== PORTAL TABLES ====================

    # Portal Users (Kunden-Accounts)
    op.create_table(
        'portal_users',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('entity_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('business_entities.id', ondelete='CASCADE'), nullable=False),
        sa.Column('company_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('companies.id', ondelete='CASCADE'), nullable=False),
        sa.Column('email', sa.String(255), nullable=False),
        sa.Column('hashed_password', sa.String(255), nullable=False),
        sa.Column('first_name', sa.String(100)),
        sa.Column('last_name', sa.String(100)),
        sa.Column('phone', sa.String(50)),
        sa.Column('position', sa.String(100)),
        sa.Column('status', sa.String(20), nullable=False, server_default='pending'),
        sa.Column('can_view_invoices', sa.Boolean(), server_default='true'),
        sa.Column('can_confirm_payments', sa.Boolean(), server_default='true'),
        sa.Column('can_submit_complaints', sa.Boolean(), server_default='true'),
        sa.Column('can_upload_documents', sa.Boolean(), server_default='true'),
        sa.Column('can_view_all_entity_data', sa.Boolean(), server_default='false'),
        sa.Column('invitation_token', sa.String(255), unique=True),
        sa.Column('invitation_sent_at', sa.DateTime(timezone=True)),
        sa.Column('invitation_expires_at', sa.DateTime(timezone=True)),
        sa.Column('invited_by_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='SET NULL')),
        sa.Column('password_changed_at', sa.DateTime(timezone=True)),
        sa.Column('failed_login_attempts', sa.Integer(), server_default='0'),
        sa.Column('locked_until', sa.DateTime(timezone=True)),
        sa.Column('last_login_at', sa.DateTime(timezone=True)),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.UniqueConstraint('company_id', 'email', name='uq_portal_users_company_email'),
    )
    op.create_index('ix_portal_users_entity_id', 'portal_users', ['entity_id'])
    op.create_index('ix_portal_users_company_id', 'portal_users', ['company_id'])
    op.create_index('ix_portal_users_email', 'portal_users', ['email'])
    op.create_index('ix_portal_users_entity_status', 'portal_users', ['entity_id', 'status'])

    # Portal Sessions
    op.create_table(
        'portal_sessions',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('portal_user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('portal_users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('session_token_hash', sa.String(255), nullable=False),
        sa.Column('refresh_token_hash', sa.String(255)),
        sa.Column('user_agent', sa.String(500)),
        sa.Column('ip_address', sa.String(45)),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('refresh_expires_at', sa.DateTime(timezone=True)),
        sa.Column('last_activity_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('revoked_at', sa.DateTime(timezone=True)),
        sa.Column('revoked_reason', sa.String(100)),
    )
    op.create_index('ix_portal_sessions_portal_user_id', 'portal_sessions', ['portal_user_id'])
    op.create_index('ix_portal_sessions_token_hash', 'portal_sessions', ['session_token_hash'])
    op.create_index('ix_portal_sessions_user_active', 'portal_sessions', ['portal_user_id', 'expires_at'])

    # Portal Complaints (Reklamationen)
    op.create_table(
        'portal_complaints',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('company_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('companies.id', ondelete='CASCADE'), nullable=False),
        sa.Column('entity_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('business_entities.id', ondelete='CASCADE'), nullable=False),
        sa.Column('submitted_by_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('portal_users.id', ondelete='SET NULL')),
        sa.Column('document_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('documents.id', ondelete='SET NULL')),
        sa.Column('invoice_tracking_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('invoice_tracking.id', ondelete='SET NULL')),
        sa.Column('reference_number', sa.String(50), unique=True, nullable=False),
        sa.Column('complaint_type', sa.String(30), nullable=False),
        sa.Column('subject', sa.String(255), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('status', sa.String(20), nullable=False, server_default='new'),
        sa.Column('priority', sa.String(20), server_default='normal'),
        sa.Column('assigned_to_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='SET NULL')),
        sa.Column('internal_notes', sa.Text()),
        sa.Column('resolution', sa.Text()),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('first_response_at', sa.DateTime(timezone=True)),
        sa.Column('resolved_at', sa.DateTime(timezone=True)),
        sa.Column('closed_at', sa.DateTime(timezone=True)),
        sa.Column('metadata', postgresql.JSONB(), server_default='{}'),
    )
    op.create_index('ix_portal_complaints_company_id', 'portal_complaints', ['company_id'])
    op.create_index('ix_portal_complaints_entity_id', 'portal_complaints', ['entity_id'])
    op.create_index('ix_portal_complaints_status', 'portal_complaints', ['company_id', 'status'])
    op.create_index('ix_portal_complaints_entity_status', 'portal_complaints', ['entity_id', 'status'])

    # Portal Messages
    op.create_table(
        'portal_messages',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('company_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('companies.id', ondelete='CASCADE'), nullable=False),
        sa.Column('entity_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('business_entities.id', ondelete='CASCADE'), nullable=False),
        sa.Column('complaint_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('portal_complaints.id', ondelete='CASCADE')),
        sa.Column('portal_user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('portal_users.id', ondelete='SET NULL')),
        sa.Column('internal_user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='SET NULL')),
        sa.Column('direction', sa.String(20), nullable=False),
        sa.Column('subject', sa.String(255)),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('attachments', postgresql.JSONB(), server_default='[]'),
        sa.Column('is_read', sa.Boolean(), server_default='false'),
        sa.Column('read_at', sa.DateTime(timezone=True)),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
    )
    op.create_index('ix_portal_messages_company_id', 'portal_messages', ['company_id'])
    op.create_index('ix_portal_messages_entity_id', 'portal_messages', ['entity_id'])
    op.create_index('ix_portal_messages_conversation', 'portal_messages', ['entity_id', 'created_at'])
    op.create_index('ix_portal_messages_unread', 'portal_messages', ['entity_id', 'is_read'])

    # Portal Documents
    op.create_table(
        'portal_documents',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('company_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('companies.id', ondelete='CASCADE'), nullable=False),
        sa.Column('entity_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('business_entities.id', ondelete='CASCADE'), nullable=False),
        sa.Column('uploaded_by_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('portal_users.id', ondelete='SET NULL')),
        sa.Column('complaint_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('portal_complaints.id', ondelete='SET NULL')),
        sa.Column('message_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('portal_messages.id', ondelete='SET NULL')),
        sa.Column('document_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('documents.id', ondelete='SET NULL')),
        sa.Column('original_filename', sa.String(255), nullable=False),
        sa.Column('file_size', sa.Integer()),
        sa.Column('mime_type', sa.String(100)),
        sa.Column('storage_path', sa.String(500)),
        sa.Column('description', sa.Text()),
        sa.Column('document_type', sa.String(50)),
        sa.Column('processing_status', sa.String(20), server_default='pending'),
        sa.Column('processed_at', sa.DateTime(timezone=True)),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
    )
    op.create_index('ix_portal_documents_entity_id', 'portal_documents', ['entity_id'])
    op.create_index('ix_portal_documents_entity_created', 'portal_documents', ['entity_id', 'created_at'])

    # Portal Payment Confirmations
    op.create_table(
        'portal_payment_confirmations',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('company_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('companies.id', ondelete='CASCADE'), nullable=False),
        sa.Column('entity_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('business_entities.id', ondelete='CASCADE'), nullable=False),
        sa.Column('portal_user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('portal_users.id', ondelete='SET NULL')),
        sa.Column('invoice_tracking_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('invoice_tracking.id', ondelete='CASCADE'), nullable=False),
        sa.Column('payment_date', sa.DateTime(timezone=True), nullable=False),
        sa.Column('payment_amount', sa.String(50), nullable=False),
        sa.Column('payment_reference', sa.String(255)),
        sa.Column('payment_method', sa.String(50)),
        sa.Column('attachment_ids', postgresql.JSONB(), server_default='[]'),
        sa.Column('status', sa.String(20), server_default='pending'),
        sa.Column('verified_at', sa.DateTime(timezone=True)),
        sa.Column('verified_by_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='SET NULL')),
        sa.Column('rejection_reason', sa.Text()),
        sa.Column('notes', sa.Text()),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
    )
    op.create_index('ix_portal_payment_confirmations_invoice', 'portal_payment_confirmations', ['invoice_tracking_id'])
    op.create_index('ix_portal_payment_confirmations_status', 'portal_payment_confirmations', ['company_id', 'status'])

    # ==================== ESG TABLES ====================

    # ESG Carbon Footprint
    op.create_table(
        'esg_carbon_footprint',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('company_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('companies.id', ondelete='CASCADE'), nullable=False),
        sa.Column('period_start', sa.Date(), nullable=False),
        sa.Column('period_end', sa.Date(), nullable=False),
        sa.Column('scope', sa.String(20), nullable=False),
        sa.Column('source_category', sa.String(100), nullable=False),
        sa.Column('source_description', sa.String(255)),
        sa.Column('consumption_value', sa.Float(), nullable=False),
        sa.Column('consumption_unit', sa.String(50), nullable=False),
        sa.Column('co2_equivalent_kg', sa.Float(), nullable=False),
        sa.Column('emission_factor', sa.Float()),
        sa.Column('emission_factor_source', sa.String(255)),
        sa.Column('document_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('documents.id', ondelete='SET NULL')),
        sa.Column('calculation_method', sa.String(100)),
        sa.Column('data_quality', sa.String(20)),
        sa.Column('recorded_by_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='SET NULL')),
        sa.Column('verified', sa.Boolean(), server_default='false'),
        sa.Column('verified_at', sa.DateTime(timezone=True)),
        sa.Column('verified_by_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='SET NULL')),
        sa.Column('notes', sa.Text()),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
    )
    op.create_index('ix_esg_carbon_footprint_company_id', 'esg_carbon_footprint', ['company_id'])
    op.create_index('ix_esg_carbon_footprint_period', 'esg_carbon_footprint', ['company_id', 'period_start', 'period_end'])
    op.create_index('ix_esg_carbon_footprint_scope', 'esg_carbon_footprint', ['company_id', 'scope'])

    # ESG Supplier Ratings
    op.create_table(
        'esg_supplier_ratings',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('company_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('companies.id', ondelete='CASCADE'), nullable=False),
        sa.Column('entity_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('business_entities.id', ondelete='CASCADE'), nullable=False),
        sa.Column('rating_date', sa.Date(), nullable=False),
        sa.Column('valid_until', sa.Date()),
        sa.Column('overall_score', sa.Float(), nullable=False),
        sa.Column('environmental_score', sa.Float()),
        sa.Column('social_score', sa.Float()),
        sa.Column('governance_score', sa.Float()),
        sa.Column('environmental_details', postgresql.JSONB(), server_default='{}'),
        sa.Column('social_details', postgresql.JSONB(), server_default='{}'),
        sa.Column('governance_details', postgresql.JSONB(), server_default='{}'),
        sa.Column('risk_level', sa.String(20)),
        sa.Column('risk_factors', postgresql.JSONB(), server_default='[]'),
        sa.Column('certifications', postgresql.JSONB(), server_default='[]'),
        sa.Column('improvement_areas', postgresql.JSONB(), server_default='[]'),
        sa.Column('action_plan', sa.Text()),
        sa.Column('assessed_by_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='SET NULL')),
        sa.Column('assessment_method', sa.String(100)),
        sa.Column('notes', sa.Text()),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
    )
    op.create_index('ix_esg_supplier_ratings_company_id', 'esg_supplier_ratings', ['company_id'])
    op.create_index('ix_esg_supplier_ratings_entity', 'esg_supplier_ratings', ['entity_id', 'rating_date'])
    op.create_index('ix_esg_supplier_ratings_score', 'esg_supplier_ratings', ['company_id', 'overall_score'])

    # ESG Certifications
    op.create_table(
        'esg_certifications',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('company_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('companies.id', ondelete='CASCADE'), nullable=False),
        sa.Column('certification_type', sa.String(100), nullable=False),
        sa.Column('certification_name', sa.String(255), nullable=False),
        sa.Column('certification_body', sa.String(255)),
        sa.Column('certificate_number', sa.String(100)),
        sa.Column('category', sa.String(20), nullable=False),
        sa.Column('issue_date', sa.Date(), nullable=False),
        sa.Column('expiry_date', sa.Date()),
        sa.Column('status', sa.String(20), nullable=False, server_default='active'),
        sa.Column('scope_description', sa.Text()),
        sa.Column('applicable_sites', postgresql.JSONB(), server_default='[]'),
        sa.Column('document_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('documents.id', ondelete='SET NULL')),
        sa.Column('last_audit_date', sa.Date()),
        sa.Column('next_audit_date', sa.Date()),
        sa.Column('audit_findings', postgresql.JSONB(), server_default='[]'),
        sa.Column('reminder_days_before', sa.Integer(), server_default='90'),
        sa.Column('reminder_sent_at', sa.DateTime(timezone=True)),
        sa.Column('notes', sa.Text()),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
    )
    op.create_index('ix_esg_certifications_company_id', 'esg_certifications', ['company_id'])
    op.create_index('ix_esg_certifications_type', 'esg_certifications', ['company_id', 'certification_type'])
    op.create_index('ix_esg_certifications_expiry', 'esg_certifications', ['company_id', 'expiry_date'])
    op.create_index('ix_esg_certifications_status', 'esg_certifications', ['company_id', 'status'])

    # ESG Reports
    op.create_table(
        'esg_reports',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('company_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('companies.id', ondelete='CASCADE'), nullable=False),
        sa.Column('title', sa.String(255), nullable=False),
        sa.Column('report_type', sa.String(50), nullable=False),
        sa.Column('reporting_standard', sa.String(100)),
        sa.Column('period_start', sa.Date(), nullable=False),
        sa.Column('period_end', sa.Date(), nullable=False),
        sa.Column('fiscal_year', sa.Integer()),
        sa.Column('status', sa.String(20), nullable=False, server_default='draft'),
        sa.Column('summary', sa.Text()),
        sa.Column('content_json', postgresql.JSONB(), server_default='{}'),
        sa.Column('metrics_summary', postgresql.JSONB(), server_default='{}'),
        sa.Column('document_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('documents.id', ondelete='SET NULL')),
        sa.Column('pdf_path', sa.String(500)),
        sa.Column('created_by_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='SET NULL')),
        sa.Column('approved_by_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='SET NULL')),
        sa.Column('approved_at', sa.DateTime(timezone=True)),
        sa.Column('published_at', sa.DateTime(timezone=True)),
        sa.Column('notes', sa.Text()),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
    )
    op.create_index('ix_esg_reports_company_id', 'esg_reports', ['company_id'])
    op.create_index('ix_esg_reports_period', 'esg_reports', ['company_id', 'period_start', 'period_end'])
    op.create_index('ix_esg_reports_status', 'esg_reports', ['company_id', 'status'])
    op.create_index('ix_esg_reports_type', 'esg_reports', ['company_id', 'report_type'])

    # ESG Goals
    op.create_table(
        'esg_goals',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('company_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('companies.id', ondelete='CASCADE'), nullable=False),
        sa.Column('title', sa.String(255), nullable=False),
        sa.Column('description', sa.Text()),
        sa.Column('category', sa.String(20), nullable=False),
        sa.Column('metric_name', sa.String(100), nullable=False),
        sa.Column('metric_unit', sa.String(50)),
        sa.Column('baseline_value', sa.Float()),
        sa.Column('baseline_year', sa.Integer()),
        sa.Column('target_value', sa.Float(), nullable=False),
        sa.Column('target_year', sa.Integer(), nullable=False),
        sa.Column('current_value', sa.Float()),
        sa.Column('current_value_date', sa.Date()),
        sa.Column('progress_percentage', sa.Float()),
        sa.Column('on_track', sa.Boolean()),
        sa.Column('sdg_goals', postgresql.JSONB(), server_default='[]'),
        sa.Column('is_active', sa.Boolean(), server_default='true'),
        sa.Column('notes', sa.Text()),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
    )
    op.create_index('ix_esg_goals_company_id', 'esg_goals', ['company_id'])
    op.create_index('ix_esg_goals_category', 'esg_goals', ['company_id', 'category'])
    op.create_index('ix_esg_goals_active', 'esg_goals', ['company_id', 'is_active'])


def downgrade() -> None:
    # ESG Tables
    op.drop_index('ix_esg_goals_active', table_name='esg_goals')
    op.drop_index('ix_esg_goals_category', table_name='esg_goals')
    op.drop_index('ix_esg_goals_company_id', table_name='esg_goals')
    op.drop_table('esg_goals')

    op.drop_index('ix_esg_reports_type', table_name='esg_reports')
    op.drop_index('ix_esg_reports_status', table_name='esg_reports')
    op.drop_index('ix_esg_reports_period', table_name='esg_reports')
    op.drop_index('ix_esg_reports_company_id', table_name='esg_reports')
    op.drop_table('esg_reports')

    op.drop_index('ix_esg_certifications_status', table_name='esg_certifications')
    op.drop_index('ix_esg_certifications_expiry', table_name='esg_certifications')
    op.drop_index('ix_esg_certifications_type', table_name='esg_certifications')
    op.drop_index('ix_esg_certifications_company_id', table_name='esg_certifications')
    op.drop_table('esg_certifications')

    op.drop_index('ix_esg_supplier_ratings_score', table_name='esg_supplier_ratings')
    op.drop_index('ix_esg_supplier_ratings_entity', table_name='esg_supplier_ratings')
    op.drop_index('ix_esg_supplier_ratings_company_id', table_name='esg_supplier_ratings')
    op.drop_table('esg_supplier_ratings')

    op.drop_index('ix_esg_carbon_footprint_scope', table_name='esg_carbon_footprint')
    op.drop_index('ix_esg_carbon_footprint_period', table_name='esg_carbon_footprint')
    op.drop_index('ix_esg_carbon_footprint_company_id', table_name='esg_carbon_footprint')
    op.drop_table('esg_carbon_footprint')

    # Portal Tables
    op.drop_index('ix_portal_payment_confirmations_status', table_name='portal_payment_confirmations')
    op.drop_index('ix_portal_payment_confirmations_invoice', table_name='portal_payment_confirmations')
    op.drop_table('portal_payment_confirmations')

    op.drop_index('ix_portal_documents_entity_created', table_name='portal_documents')
    op.drop_index('ix_portal_documents_entity_id', table_name='portal_documents')
    op.drop_table('portal_documents')

    op.drop_index('ix_portal_messages_unread', table_name='portal_messages')
    op.drop_index('ix_portal_messages_conversation', table_name='portal_messages')
    op.drop_index('ix_portal_messages_entity_id', table_name='portal_messages')
    op.drop_index('ix_portal_messages_company_id', table_name='portal_messages')
    op.drop_table('portal_messages')

    op.drop_index('ix_portal_complaints_entity_status', table_name='portal_complaints')
    op.drop_index('ix_portal_complaints_status', table_name='portal_complaints')
    op.drop_index('ix_portal_complaints_entity_id', table_name='portal_complaints')
    op.drop_index('ix_portal_complaints_company_id', table_name='portal_complaints')
    op.drop_table('portal_complaints')

    op.drop_index('ix_portal_sessions_user_active', table_name='portal_sessions')
    op.drop_index('ix_portal_sessions_token_hash', table_name='portal_sessions')
    op.drop_index('ix_portal_sessions_portal_user_id', table_name='portal_sessions')
    op.drop_table('portal_sessions')

    op.drop_index('ix_portal_users_entity_status', table_name='portal_users')
    op.drop_index('ix_portal_users_email', table_name='portal_users')
    op.drop_index('ix_portal_users_company_id', table_name='portal_users')
    op.drop_index('ix_portal_users_entity_id', table_name='portal_users')
    op.drop_table('portal_users')
