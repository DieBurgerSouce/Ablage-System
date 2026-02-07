# -*- coding: utf-8 -*-
"""add_einvoice_transmission

E-Invoice 2025 Compliance - Transmission Tracking Tables

Revision ID: 148_add_einvoice_transmission
Revises: 147_add_document_lineage
Create Date: 2026-02-02

New Tables:
- einvoice_transmissions: Tracking of e-invoice transmissions (Peppol/Email)
- peppol_participants: Cached Peppol participant registry
- incoming_einvoices: Received e-invoices before processing

Updates:
- einvoice_documents: Add transmissions relationship
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '148_add_einvoice_transmission'
down_revision: Union[str, None] = '147_add_document_lineage'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create E-Invoice 2025 tables."""

    # EInvoice Transmissions Table
    op.create_table(
        'einvoice_transmissions',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('einvoice_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('einvoice_documents.id', ondelete='CASCADE'),
                  nullable=False, index=True),
        sa.Column('channel', sa.String(20), nullable=False),  # peppol, email, portal, manual, api
        sa.Column('status', sa.String(30), nullable=False, default='draft'),

        # Peppol-specific
        sa.Column('peppol_message_id', sa.String(255), nullable=True, unique=True),
        sa.Column('peppol_conversation_id', sa.String(255), nullable=True),
        sa.Column('peppol_endpoint_id', sa.String(100), nullable=True),
        sa.Column('peppol_process_id', sa.String(255), nullable=True),
        sa.Column('peppol_document_type', sa.String(255), nullable=True),

        # Email-specific (fallback)
        sa.Column('email_recipient', sa.String(255), nullable=True),
        sa.Column('email_message_id', sa.String(255), nullable=True),
        sa.Column('email_subject', sa.String(500), nullable=True),

        # Timing
        sa.Column('queued_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('sent_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('delivered_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('acknowledged_at', sa.DateTime(timezone=True), nullable=True),

        # MDN Response
        sa.Column('mdn_received', sa.Boolean, default=False),
        sa.Column('mdn_content', sa.Text, nullable=True),
        sa.Column('business_response', postgresql.JSONB(astext_type=sa.Text()), default=dict),

        # Error handling
        sa.Column('retry_count', sa.Integer, default=0),
        sa.Column('max_retries', sa.Integer, default=3),
        sa.Column('last_error', sa.Text, nullable=True),
        sa.Column('error_code', sa.String(50), nullable=True),
        sa.Column('error_details', postgresql.JSONB(astext_type=sa.Text()), default=dict),

        # Audit
        sa.Column('initiated_by_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('users.id'), nullable=True),
        sa.Column('company_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('companies.id'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    )

    # Indices for einvoice_transmissions
    op.create_index('ix_einvoice_transmissions_status', 'einvoice_transmissions', ['status'])
    op.create_index('ix_einvoice_transmissions_channel', 'einvoice_transmissions', ['channel'])
    op.create_index('ix_einvoice_transmissions_company_status', 'einvoice_transmissions',
                    ['company_id', 'status'])
    op.create_index('ix_einvoice_transmissions_peppol_msg', 'einvoice_transmissions',
                    ['peppol_message_id'])

    # Peppol Participants Table (Cache)
    op.create_table(
        'peppol_participants',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('participant_id', sa.String(100), nullable=False, unique=True),
        sa.Column('scheme_id', sa.String(20), nullable=False, default='0204'),
        sa.Column('endpoint_url', sa.String(500), nullable=True),
        sa.Column('entity_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('entities.id'), nullable=True),
        sa.Column('participant_name', sa.String(500), nullable=True),
        sa.Column('supported_document_types', postgresql.JSONB(astext_type=sa.Text()), default=list),
        sa.Column('capabilities', postgresql.JSONB(astext_type=sa.Text()), default=dict),
        sa.Column('is_active', sa.Boolean, default=True),
        sa.Column('last_verified_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('verification_error', sa.Text, nullable=True),
        sa.Column('company_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('companies.id'), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    )

    # Indices for peppol_participants
    op.create_index('ix_peppol_participants_scheme_id', 'peppol_participants',
                    ['scheme_id', 'participant_id'])
    op.create_index('ix_peppol_participants_entity', 'peppol_participants', ['entity_id'])

    # Incoming E-Invoices Table
    op.create_table(
        'incoming_einvoices',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('channel', sa.String(20), nullable=False),  # peppol, email, portal
        sa.Column('received_at', sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),

        # Peppol-specific
        sa.Column('peppol_message_id', sa.String(255), nullable=True, unique=True),
        sa.Column('peppol_sender_id', sa.String(100), nullable=True),
        sa.Column('peppol_document_type', sa.String(255), nullable=True),

        # Email-specific
        sa.Column('email_sender', sa.String(255), nullable=True),
        sa.Column('email_subject', sa.String(500), nullable=True),
        sa.Column('email_message_id', sa.String(255), nullable=True),

        # Content
        sa.Column('format', sa.String(50), nullable=False),  # xrechnung_cii, xrechnung_ubl, zugferd
        sa.Column('xml_content', sa.Text, nullable=False),
        sa.Column('xml_hash', sa.String(64), nullable=False),
        sa.Column('original_filename', sa.String(255), nullable=True),
        sa.Column('has_pdf_attachment', sa.Boolean, default=False),
        sa.Column('pdf_storage_path', sa.String(500), nullable=True),

        # Extracted Basic Data
        sa.Column('invoice_number', sa.String(100), nullable=True),
        sa.Column('invoice_date', sa.DateTime, nullable=True),
        sa.Column('seller_name', sa.String(255), nullable=True),
        sa.Column('buyer_reference', sa.String(100), nullable=True),
        sa.Column('total_amount', sa.Numeric(12, 2), nullable=True),
        sa.Column('currency', sa.String(3), default='EUR'),

        # Validation
        sa.Column('is_valid', sa.Boolean, nullable=True),
        sa.Column('validation_errors', postgresql.JSONB(astext_type=sa.Text()), default=list),
        sa.Column('validation_warnings', postgresql.JSONB(astext_type=sa.Text()), default=list),

        # Processing
        sa.Column('status', sa.String(30), nullable=False, default='received'),
        sa.Column('processed_at', sa.DateTime(timezone=True), nullable=True),

        # Linking
        sa.Column('document_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('documents.id'), nullable=True),
        sa.Column('entity_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('entities.id'), nullable=True),

        # Audit
        sa.Column('company_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('companies.id'), nullable=False),
        sa.Column('processed_by_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('users.id'), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    )

    # Indices for incoming_einvoices
    op.create_index('ix_incoming_einvoices_status', 'incoming_einvoices', ['status'])
    op.create_index('ix_incoming_einvoices_company_status', 'incoming_einvoices',
                    ['company_id', 'status'])
    op.create_index('ix_incoming_einvoices_invoice_number', 'incoming_einvoices', ['invoice_number'])
    op.create_index('ix_incoming_einvoices_received_at', 'incoming_einvoices', ['received_at'])


def downgrade() -> None:
    """Drop E-Invoice 2025 tables."""

    # Drop indices
    op.drop_index('ix_incoming_einvoices_received_at', table_name='incoming_einvoices')
    op.drop_index('ix_incoming_einvoices_invoice_number', table_name='incoming_einvoices')
    op.drop_index('ix_incoming_einvoices_company_status', table_name='incoming_einvoices')
    op.drop_index('ix_incoming_einvoices_status', table_name='incoming_einvoices')

    op.drop_index('ix_peppol_participants_entity', table_name='peppol_participants')
    op.drop_index('ix_peppol_participants_scheme_id', table_name='peppol_participants')

    op.drop_index('ix_einvoice_transmissions_peppol_msg', table_name='einvoice_transmissions')
    op.drop_index('ix_einvoice_transmissions_company_status', table_name='einvoice_transmissions')
    op.drop_index('ix_einvoice_transmissions_channel', table_name='einvoice_transmissions')
    op.drop_index('ix_einvoice_transmissions_status', table_name='einvoice_transmissions')

    # Drop tables
    op.drop_table('incoming_einvoices')
    op.drop_table('peppol_participants')
    op.drop_table('einvoice_transmissions')
