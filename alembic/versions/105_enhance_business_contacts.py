"""Enhance business_contacts with company_id and document_contact_links.

Revision ID: 105_enhance_business_contacts
Revises: 104_tenant_subscription
Create Date: 2026-01-19

Enhancements:
- Add company_id to business_contacts for multi-tenant support
- Add additional columns to document_contacts
- Add indexes for multi-tenant queries
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '105_enhance_business_contacts'
down_revision = '104_tenant_subscription'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add company_id to business_contacts
    op.add_column(
        'business_contacts',
        sa.Column('company_id', postgresql.UUID(as_uuid=True), nullable=True)
    )
    op.create_foreign_key(
        'business_contacts_company_id_fkey',
        'business_contacts', 'companies',
        ['company_id'], ['id'],
        ondelete='CASCADE'
    )
    op.create_index(
        'ix_business_contacts_company_id',
        'business_contacts',
        ['company_id']
    )
    op.create_index(
        'ix_business_contacts_owner_active',
        'business_contacts',
        ['owner_id', 'is_active']
    )
    op.create_index(
        'ix_business_contacts_company_active',
        'business_contacts',
        ['company_id', 'is_active']
    )

    # Add additional columns to document_contacts
    op.add_column(
        'document_contacts',
        sa.Column('is_auto_detected', sa.Boolean, server_default='false')
    )
    op.add_column(
        'document_contacts',
        sa.Column('detected_at', sa.DateTime(timezone=True), server_default=sa.func.now())
    )
    op.add_column(
        'document_contacts',
        sa.Column('confirmed_by_id', postgresql.UUID(as_uuid=True), nullable=True)
    )
    op.add_column(
        'document_contacts',
        sa.Column('confirmed_at', sa.DateTime(timezone=True), nullable=True)
    )

    op.create_foreign_key(
        'document_contacts_confirmed_by_fkey',
        'document_contacts', 'users',
        ['confirmed_by_id'], ['id'],
        ondelete='SET NULL'
    )


def downgrade() -> None:
    # Remove foreign keys
    op.drop_constraint('document_contacts_confirmed_by_fkey', 'document_contacts', type_='foreignkey')
    op.drop_constraint('business_contacts_company_id_fkey', 'business_contacts', type_='foreignkey')

    # Remove indexes
    op.drop_index('ix_business_contacts_company_active', 'business_contacts')
    op.drop_index('ix_business_contacts_owner_active', 'business_contacts')
    op.drop_index('ix_business_contacts_company_id', 'business_contacts')

    # Remove columns
    op.drop_column('document_contacts', 'confirmed_at')
    op.drop_column('document_contacts', 'confirmed_by_id')
    op.drop_column('document_contacts', 'detected_at')
    op.drop_column('document_contacts', 'is_auto_detected')
    op.drop_column('business_contacts', 'company_id')
