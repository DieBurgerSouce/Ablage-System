"""Add missing model fields for GDPR and ProcessingJob

Revision ID: 015
Revises: 014
Create Date: 2025-11-30

Fuegt fehlende Felder hinzu:
- Document.data_category: GDPR Datenkategorie für Aufbewahrungsfristen
- ProcessingJob.progress: Fortschritt 0-100%
- ProcessingJob.message: Status-Nachricht

Diese Felder werden von gdpr_tasks.py und den Schemas erwartet.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '015'
down_revision: Union[str, None] = '014_add_email_verification'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Document.data_category - GDPR Datenkategorie für Retention
    op.add_column(
        'documents',
        sa.Column(
            'data_category',
            sa.String(50),
            nullable=True,
            server_default='document_content',
            comment='GDPR Datenkategorie für Aufbewahrungsfristen'
        )
    )

    # ProcessingJob.progress - Fortschritt 0-100%
    op.add_column(
        'processing_jobs',
        sa.Column(
            'progress',
            sa.Integer(),
            nullable=True,
            server_default='0',
            comment='Fortschritt 0-100%'
        )
    )

    # ProcessingJob.message - Status-Nachricht
    op.add_column(
        'processing_jobs',
        sa.Column(
            'message',
            sa.String(500),
            nullable=True,
            comment='Status-Nachricht'
        )
    )

    # Index für data_category (für Retention-Queries)
    op.create_index(
        'ix_documents_data_category',
        'documents',
        ['data_category']
    )


def downgrade() -> None:
    # Drop index first
    op.drop_index('ix_documents_data_category', table_name='documents')

    # Drop columns in reverse order
    op.drop_column('processing_jobs', 'message')
    op.drop_column('processing_jobs', 'progress')
    op.drop_column('documents', 'data_category')
