"""Add DataExport table for GDPR Art. 20 - Data Portability.

Revision ID: 012_add_data_export_table
Revises: 011_add_gdpr_deletion_fields
Create Date: 2024-11-30

Implements: GDPR Art. 20 - Right to Data Portability (Recht auf Datenübertragbarkeit)
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


# revision identifiers
revision = '012_add_data_export_table'
down_revision = '011_add_gdpr_deletion_fields'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create data_exports table for GDPR Art. 20."""
    op.create_table(
        'data_exports',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column(
            'user_id',
            UUID(as_uuid=True),
            sa.ForeignKey('users.id', ondelete='CASCADE'),
            nullable=False
        ),
        sa.Column('status', sa.String(50), default='pending', nullable=False),
        sa.Column('format', sa.String(20), default='json', nullable=False),
        sa.Column('file_path', sa.String(500), nullable=True),
        sa.Column('file_size_bytes', sa.Integer, nullable=True),
        sa.Column('error_message', sa.Text, nullable=True),
        sa.Column(
            'requested_at',
            sa.DateTime(timezone=True),
            server_default=sa.func.now()
        ),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('download_count', sa.Integer, default=0),
    )

    # Indexes for efficient queries
    op.create_index(
        'ix_data_exports_user_id',
        'data_exports',
        ['user_id']
    )
    op.create_index(
        'ix_data_exports_status',
        'data_exports',
        ['status']
    )
    op.create_index(
        'ix_data_exports_expires_at',
        'data_exports',
        ['expires_at'],
        postgresql_where=sa.text('expires_at IS NOT NULL')
    )


def downgrade() -> None:
    """Remove data_exports table."""
    op.drop_index('ix_data_exports_expires_at', table_name='data_exports')
    op.drop_index('ix_data_exports_status', table_name='data_exports')
    op.drop_index('ix_data_exports_user_id', table_name='data_exports')
    op.drop_table('data_exports')
