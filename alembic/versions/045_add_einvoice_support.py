"""Add E-Invoice support tables and fields

Revision ID: 045_add_einvoice_support
Revises: 044_nullable_chunk_embedding
Create Date: 2025-12-17

Fuegt Unterstuetzung fuer ZUGFeRD und XRechnung hinzu:
- Neue Tabelle einvoice_documents fuer XML-Speicherung und Validierung
- Indizes fuer Leitweg-ID Lookup (B2G)
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB


revision = "045"
down_revision = "044"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Erstelle einvoice_documents Tabelle
    op.create_table(
        'einvoice_documents',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('document_id', UUID(as_uuid=True),
                  sa.ForeignKey('documents.id', ondelete='CASCADE'),
                  nullable=False, unique=True),

        # E-Invoice Format Information
        sa.Column('format', sa.String(50), nullable=False),
        sa.Column('profile', sa.String(50), nullable=True),
        sa.Column('version', sa.String(20), nullable=True),

        # XML Speicherung
        sa.Column('xml_content', sa.Text, nullable=True),
        sa.Column('xml_hash', sa.String(64), nullable=True),

        # Validierung
        sa.Column('is_valid', sa.Boolean, nullable=True),
        sa.Column('validation_timestamp', sa.DateTime(timezone=True), nullable=True),
        sa.Column('validation_errors', JSONB, server_default='[]'),
        sa.Column('validation_warnings', JSONB, server_default='[]'),
        sa.Column('validator_used', sa.String(50), nullable=True),

        # Schema/Schematron separat
        sa.Column('schema_valid', sa.Boolean, nullable=True),
        sa.Column('schematron_valid', sa.Boolean, nullable=True),
        sa.Column('pdf_a_compliant', sa.Boolean, nullable=True),

        # B2G-spezifisch
        sa.Column('leitweg_id', sa.String(100), nullable=True),

        # Generierungsmetadaten
        sa.Column('was_generated', sa.Boolean, server_default='false'),
        sa.Column('was_extracted', sa.Boolean, server_default='false'),
        sa.Column('generation_timestamp', sa.DateTime(timezone=True), nullable=True),
        sa.Column('generated_by_id', UUID(as_uuid=True),
                  sa.ForeignKey('users.id', ondelete='SET NULL'),
                  nullable=True),

        # Originalquelle
        sa.Column('source_filename', sa.String(255), nullable=True),
        sa.Column('extraction_method', sa.String(50), nullable=True),

        # Timestamps
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(timezone=True),
                  server_default=sa.text('NOW()')),
    )

    # Indizes
    op.create_index('ix_einvoice_docs_document_id', 'einvoice_documents', ['document_id'])
    op.create_index('ix_einvoice_docs_format', 'einvoice_documents', ['format'])
    op.create_index('ix_einvoice_docs_leitweg_id', 'einvoice_documents', ['leitweg_id'])
    op.create_index('ix_einvoice_docs_is_valid', 'einvoice_documents', ['is_valid'])
    op.create_index('ix_einvoice_docs_was_generated', 'einvoice_documents', ['was_generated'])


def downgrade() -> None:
    op.drop_table('einvoice_documents')
