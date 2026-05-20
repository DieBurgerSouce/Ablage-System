"""Add retention enforcement columns.

Revision ID: 205_add_retention_enforcement
Revises: 204_add_portal_and_esg
Create Date: 2026-02-07

Features:
- Enforcement status tracking
- GDPR conflict resolution
- Post-retention review scheduling
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '205_add_retention_enforcement'
down_revision: str = '204_add_portal_and_esg'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add retention enforcement columns to document_archives."""

    # Add enforcement_status column
    op.add_column(
        'document_archives',
        sa.Column(
            'enforcement_status',
            sa.String(20),
            nullable=False,
            server_default='active',
            comment='Status der Aufbewahrungsfristen-Durchsetzung'
        )
    )

    # Add GDPR conflict resolution tracking
    op.add_column(
        'document_archives',
        sa.Column(
            'gdpr_conflict_resolved_at',
            sa.DateTime(timezone=True),
            nullable=True,
            comment='Zeitpunkt der GDPR-Konflikt-Aufloesung'
        )
    )

    # Add post-retention review scheduling
    op.add_column(
        'document_archives',
        sa.Column(
            'post_retention_review_scheduled',
            sa.Boolean(),
            nullable=False,
            server_default='false',
            comment='Flag ob Post-Retention Review geplant ist'
        )
    )

    op.add_column(
        'document_archives',
        sa.Column(
            'post_retention_review_at',
            sa.DateTime(timezone=True),
            nullable=True,
            comment='Zeitpunkt der geplanten Post-Retention Review'
        )
    )

    # Create indexes for efficient queries
    op.create_index(
        'ix_document_archives_enforcement_status',
        'document_archives',
        ['enforcement_status']
    )

    op.create_index(
        'ix_document_archives_post_retention_review',
        'document_archives',
        ['post_retention_review_scheduled', 'post_retention_review_at']
    )

    op.create_index(
        'ix_document_archives_company_enforcement',
        'document_archives',
        ['company_id', 'enforcement_status', 'retention_expires_at']
    )

    # Update existing records
    # Set enforcement_status based on retention_expires_at
    op.execute("""
        UPDATE document_archives
        SET enforcement_status = CASE
            WHEN retention_expires_at < CURRENT_DATE THEN 'expired'
            ELSE 'active'
        END
    """)


def downgrade() -> None:
    """Remove retention enforcement columns."""

    # Drop indexes
    op.drop_index('ix_document_archives_company_enforcement', table_name='document_archives')
    op.drop_index('ix_document_archives_post_retention_review', table_name='document_archives')
    op.drop_index('ix_document_archives_enforcement_status', table_name='document_archives')

    # Drop columns
    op.drop_column('document_archives', 'post_retention_review_at')
    op.drop_column('document_archives', 'post_retention_review_scheduled')
    op.drop_column('document_archives', 'gdpr_conflict_resolved_at')
    op.drop_column('document_archives', 'enforcement_status')
