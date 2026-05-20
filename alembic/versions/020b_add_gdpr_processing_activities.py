"""Add GDPR Processing Activities table (Art. 30 DSGVO)

Revision ID: 020_gdpr_processing
Revises: 019_add_audit_log_sequence
Create Date: 2024-12-01

Erstellt Tabelle für Verarbeitungsverzeichnis gemäß Art. 30 DSGVO.
Ersetzt die In-Memory-Speicherung im GDPRComplianceManager.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '020b'
down_revision = '020'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create gdpr_processing_activities table."""

    # Check if we're using PostgreSQL
    bind = op.get_bind()
    is_postgres = bind.dialect.name == 'postgresql'

    # Create table
    op.create_table(
        'gdpr_processing_activities',
        sa.Column('id', sa.UUID() if is_postgres else sa.String(36), primary_key=True),
        sa.Column('activity_id', sa.String(32), unique=True, nullable=False),

        # Document reference
        sa.Column('document_id', sa.UUID() if is_postgres else sa.String(36),
                  sa.ForeignKey('documents.id', ondelete='SET NULL'), nullable=True),

        # Subject (anonymized)
        sa.Column('subject_id', sa.String(64), nullable=True),

        # Processing details (Art. 30 DSGVO Pflichtangaben)
        sa.Column('data_categories', postgresql.JSONB() if is_postgres else sa.JSON(), default=[]),
        sa.Column('processing_purpose', sa.String(100), nullable=False),
        sa.Column('legal_basis', sa.String(255), nullable=False),

        # Retention
        sa.Column('retention_period_days', sa.Integer(), nullable=False),
        sa.Column('retention_expires_at', sa.DateTime(timezone=True), nullable=True),

        # Processing metadata
        sa.Column('processed_by_system', sa.String(100), default='ablage-system-ocr'),
        sa.Column('processing_backend', sa.String(50), nullable=True),

        # Timestamps
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(),
                  onupdate=sa.func.now()),

        # Data transfer (Art. 30(1)(e) DSGVO)
        sa.Column('data_recipients', postgresql.JSONB() if is_postgres else sa.JSON(), default=[]),
        sa.Column('third_country_transfer', sa.Boolean(), default=False),

        # Technical measures (Art. 32 DSGVO)
        sa.Column('encryption_applied', sa.Boolean(), default=True),
        sa.Column('pseudonymization_applied', sa.Boolean(), default=False),
    )

    # Create indexes
    op.create_index('ix_gdpr_processing_activities_activity_id',
                    'gdpr_processing_activities', ['activity_id'])
    op.create_index('ix_gdpr_processing_activities_document_id',
                    'gdpr_processing_activities', ['document_id'])
    op.create_index('ix_gdpr_processing_activities_subject_id',
                    'gdpr_processing_activities', ['subject_id'])
    op.create_index('ix_gdpr_processing_activities_created_at',
                    'gdpr_processing_activities', ['created_at'])
    op.create_index('ix_gdpr_processing_activities_purpose',
                    'gdpr_processing_activities', ['processing_purpose'])
    op.create_index('ix_gdpr_processing_activities_retention',
                    'gdpr_processing_activities', ['retention_expires_at'])


def downgrade() -> None:
    """Drop gdpr_processing_activities table."""

    # Drop indexes
    op.drop_index('ix_gdpr_processing_activities_retention', 'gdpr_processing_activities')
    op.drop_index('ix_gdpr_processing_activities_purpose', 'gdpr_processing_activities')
    op.drop_index('ix_gdpr_processing_activities_created_at', 'gdpr_processing_activities')
    op.drop_index('ix_gdpr_processing_activities_subject_id', 'gdpr_processing_activities')
    op.drop_index('ix_gdpr_processing_activities_document_id', 'gdpr_processing_activities')
    op.drop_index('ix_gdpr_processing_activities_activity_id', 'gdpr_processing_activities')

    # Drop table
    op.drop_table('gdpr_processing_activities')
