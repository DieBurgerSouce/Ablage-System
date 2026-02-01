# -*- coding: utf-8 -*-
"""Add document lineage tracking tables.

Revision ID: 147_add_document_lineage
Revises: 146_add_auto_filing_fields
Create Date: 2026-02-01

Phase 1.3: Document Lineage Timeline
- document_lineage_events: Alle Ereignisse in der Verarbeitungskette
- document_lineage_summaries: Cache fuer schnelle Abfragen
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '147_add_document_lineage'
down_revision = '146_add_auto_filing_fields'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create document lineage tables."""

    # ==========================================================================
    # Table: document_lineage_events
    # ==========================================================================
    op.create_table(
        'document_lineage_events',

        # Primary Key
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('gen_random_uuid()')),

        # Document Reference
        sa.Column('document_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('documents.id', ondelete='CASCADE'),
                  nullable=False, index=True),

        # Event Type
        sa.Column('event_type', sa.String(50), nullable=False, index=True),

        # Event Data (JSONB)
        sa.Column('event_data', postgresql.JSONB, server_default='{}'),

        # Processing Duration (milliseconds)
        sa.Column('duration_ms', sa.Integer, nullable=True),

        # Confidence Score (0.0 - 1.0)
        sa.Column('confidence', sa.Float, nullable=True),

        # User who triggered the event (optional)
        sa.Column('user_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('users.id', ondelete='SET NULL'),
                  nullable=True, index=True),

        # Multi-Tenant Support
        sa.Column('company_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('companies.id', ondelete='CASCADE'),
                  nullable=False, index=True),

        # Source Service
        sa.Column('source_service', sa.String(100), nullable=True),

        # Correlation ID for related events
        sa.Column('correlation_id', postgresql.UUID(as_uuid=True),
                  nullable=True, index=True),

        # Timestamp
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.func.now(), index=True),
    )

    # Composite Indexes for common queries
    op.create_index(
        'ix_lineage_document_created',
        'document_lineage_events',
        ['document_id', 'created_at']
    )

    op.create_index(
        'ix_lineage_document_type',
        'document_lineage_events',
        ['document_id', 'event_type']
    )

    op.create_index(
        'ix_lineage_company_created',
        'document_lineage_events',
        ['company_id', 'created_at']
    )

    # Check constraint for event types
    op.create_check_constraint(
        'ck_lineage_event_type',
        'document_lineage_events',
        "event_type IN ('import', 'ocr_start', 'ocr_complete', 'ocr_failed', "
        "'classification', 'extraction', 'entity_link', 'entity_unlink', "
        "'modification', 'metadata_update', 'tag_change', 'approval', "
        "'rejection', 'escalation', 'export', 'archive', 'restore', "
        "'soft_delete', 'hard_delete')"
    )

    # ==========================================================================
    # Table: document_lineage_summaries
    # ==========================================================================
    op.create_table(
        'document_lineage_summaries',

        # Primary Key
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('gen_random_uuid()')),

        # Document Reference (1:1)
        sa.Column('document_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('documents.id', ondelete='CASCADE'),
                  nullable=False, unique=True, index=True),

        # Import Information
        sa.Column('import_source_type', sa.String(50), nullable=True),
        sa.Column('import_source_details', postgresql.JSONB, server_default='{}'),
        sa.Column('imported_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('imported_by_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('users.id', ondelete='SET NULL'),
                  nullable=True),

        # OCR Information
        sa.Column('ocr_backend', sa.String(50), nullable=True),
        sa.Column('ocr_duration_ms', sa.Integer, nullable=True),
        sa.Column('ocr_confidence', sa.Float, nullable=True),
        sa.Column('ocr_completed_at', sa.DateTime(timezone=True), nullable=True),

        # Classification
        sa.Column('classification_confidence', sa.Float, nullable=True),
        sa.Column('classified_at', sa.DateTime(timezone=True), nullable=True),

        # Entity Linking
        sa.Column('current_entity_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('business_entities.id', ondelete='SET NULL'),
                  nullable=True),
        sa.Column('entity_link_confidence', sa.Float, nullable=True),
        sa.Column('entity_linked_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('entity_link_count', sa.Integer, server_default='0'),

        # Modification Statistics
        sa.Column('modification_count', sa.Integer, server_default='0'),
        sa.Column('last_modified_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_modified_by_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('users.id', ondelete='SET NULL'),
                  nullable=True),

        # Total Processing Duration
        sa.Column('total_processing_duration_ms', sa.Integer, server_default='0'),

        # Event Count
        sa.Column('total_event_count', sa.Integer, server_default='0'),

        # Workflow Status
        sa.Column('approval_count', sa.Integer, server_default='0'),
        sa.Column('rejection_count', sa.Integer, server_default='0'),

        # Export Statistics
        sa.Column('export_count', sa.Integer, server_default='0'),
        sa.Column('last_exported_at', sa.DateTime(timezone=True), nullable=True),

        # Multi-Tenant
        sa.Column('company_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('companies.id', ondelete='CASCADE'),
                  nullable=False, index=True),

        # Timestamps
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True),
                  server_default=sa.func.now(),
                  onupdate=sa.func.now()),
    )

    # Index for company queries
    op.create_index(
        'ix_lineage_summary_company',
        'document_lineage_summaries',
        ['company_id']
    )

    # ==========================================================================
    # Add RLS Policies (Row Level Security)
    # ==========================================================================

    # Enable RLS
    op.execute("""
        ALTER TABLE document_lineage_events ENABLE ROW LEVEL SECURITY;
        ALTER TABLE document_lineage_summaries ENABLE ROW LEVEL SECURITY;
    """)

    # Create RLS policies for document_lineage_events
    op.execute("""
        CREATE POLICY lineage_events_company_isolation
        ON document_lineage_events
        FOR ALL
        USING (
            company_id::text = current_setting('app.current_company_id', true)
            OR current_setting('app.is_admin', true) = 'true'
        );
    """)

    # Create RLS policies for document_lineage_summaries
    op.execute("""
        CREATE POLICY lineage_summaries_company_isolation
        ON document_lineage_summaries
        FOR ALL
        USING (
            company_id::text = current_setting('app.current_company_id', true)
            OR current_setting('app.is_admin', true) = 'true'
        );
    """)


def downgrade() -> None:
    """Drop document lineage tables."""

    # Drop RLS policies
    op.execute("""
        DROP POLICY IF EXISTS lineage_events_company_isolation ON document_lineage_events;
        DROP POLICY IF EXISTS lineage_summaries_company_isolation ON document_lineage_summaries;
    """)

    # Drop indexes
    op.drop_index('ix_lineage_summary_company', table_name='document_lineage_summaries')
    op.drop_index('ix_lineage_company_created', table_name='document_lineage_events')
    op.drop_index('ix_lineage_document_type', table_name='document_lineage_events')
    op.drop_index('ix_lineage_document_created', table_name='document_lineage_events')

    # Drop tables
    op.drop_table('document_lineage_summaries')
    op.drop_table('document_lineage_events')
