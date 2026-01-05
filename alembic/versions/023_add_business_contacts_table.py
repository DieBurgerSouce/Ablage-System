"""Add business_contacts table

Revision ID: 023
Revises: 022
Create Date: 2026-01-04 19:10:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '023'
down_revision = '022'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create business_contacts table
    op.create_table(
        'business_contacts',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('name_normalized', sa.String(255), nullable=False),
        sa.Column('contact_type', sa.String(20), server_default='customer'),
        sa.Column('company_form', sa.String(50), nullable=True),

        # Identifikatoren
        sa.Column('tax_id', sa.String(50), nullable=True),
        sa.Column('vat_id', sa.String(30), nullable=True),
        sa.Column('registration_number', sa.String(50), nullable=True),
        sa.Column('customer_number', sa.String(50), nullable=True),
        sa.Column('supplier_number', sa.String(50), nullable=True),

        # Adresse
        sa.Column('street', sa.String(255), nullable=True),
        sa.Column('house_number', sa.String(20), nullable=True),
        sa.Column('address_addition', sa.String(100), nullable=True),
        sa.Column('postal_code', sa.String(10), nullable=True),
        sa.Column('city', sa.String(100), nullable=True),
        sa.Column('country', sa.String(100), server_default='Deutschland'),

        # Kontakt
        sa.Column('email', sa.String(255), nullable=True),
        sa.Column('phone', sa.String(50), nullable=True),
        sa.Column('fax', sa.String(50), nullable=True),
        sa.Column('website', sa.String(255), nullable=True),

        # Bankverbindung
        sa.Column('bank_name', sa.String(255), nullable=True),
        sa.Column('iban', sa.String(34), nullable=True),
        sa.Column('bic', sa.String(11), nullable=True),

        # JSON Felder
        sa.Column('contact_persons', postgresql.JSONB, server_default='[]'),
        sa.Column('tags', postgresql.JSONB, server_default='[]'),
        sa.Column('custom_fields', postgresql.JSONB, server_default='{}'),

        # Foreign Keys
        sa.Column('owner_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('parent_company_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('first_document_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('merged_into_id', postgresql.UUID(as_uuid=True), nullable=True),

        # Automatische Erkennung
        sa.Column('source', sa.String(50), server_default='manual'),
        sa.Column('auto_detected', sa.Boolean, server_default='false'),
        sa.Column('auto_detection_confidence', sa.Float, nullable=True),

        # Metadaten
        sa.Column('notes', sa.Text, nullable=True),

        # Status
        sa.Column('is_active', sa.Boolean, server_default='true'),
        sa.Column('is_verified', sa.Boolean, server_default='false'),

        # Timestamps
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.Column('last_document_date', sa.DateTime(timezone=True), nullable=True),

        # Statistik
        sa.Column('document_count', sa.Integer, server_default='0'),
        sa.Column('total_invoice_amount', sa.Float, server_default='0.0'),
    )

    # Add Foreign Key Constraints
    op.create_foreign_key(
        'business_contacts_owner_id_fkey',
        'business_contacts', 'users',
        ['owner_id'], ['id'],
        ondelete='SET NULL'
    )
    op.create_foreign_key(
        'business_contacts_parent_company_id_fkey',
        'business_contacts', 'business_contacts',
        ['parent_company_id'], ['id'],
        ondelete='SET NULL'
    )
    op.create_foreign_key(
        'business_contacts_first_document_id_fkey',
        'business_contacts', 'documents',
        ['first_document_id'], ['id'],
        ondelete='SET NULL'
    )
    op.create_foreign_key(
        'business_contacts_merged_into_id_fkey',
        'business_contacts', 'business_contacts',
        ['merged_into_id'], ['id'],
        ondelete='SET NULL'
    )

    # Create Indexes
    op.create_index('ix_business_contacts_name_normalized', 'business_contacts', ['name_normalized'])
    op.create_index('ix_business_contacts_contact_type', 'business_contacts', ['contact_type'])
    op.create_index('ix_business_contacts_vat_id', 'business_contacts', ['vat_id'])
    op.create_index('ix_business_contacts_tax_id', 'business_contacts', ['tax_id'])
    op.create_index('ix_business_contacts_postal_code', 'business_contacts', ['postal_code'])
    op.create_index('ix_business_contacts_city', 'business_contacts', ['city'])
    op.create_index('ix_business_contacts_owner_id', 'business_contacts', ['owner_id'])
    op.create_index('ix_business_contacts_is_active', 'business_contacts', ['is_active'])

    # Create document_contacts junction table
    op.create_table(
        'document_contacts',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('document_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('contact_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('role', sa.String(50), nullable=False),
        sa.Column('confidence', sa.Float, server_default='1.0'),
        sa.Column('auto_detected', sa.Boolean, server_default='false'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_foreign_key(
        'document_contacts_document_id_fkey',
        'document_contacts', 'documents',
        ['document_id'], ['id'],
        ondelete='CASCADE'
    )
    op.create_foreign_key(
        'document_contacts_contact_id_fkey',
        'document_contacts', 'business_contacts',
        ['contact_id'], ['id'],
        ondelete='CASCADE'
    )

    op.create_index('ix_document_contacts_document_id', 'document_contacts', ['document_id'])
    op.create_index('ix_document_contacts_contact_id', 'document_contacts', ['contact_id'])
    op.create_index('ix_document_contacts_role', 'document_contacts', ['role'])

    # Create unique constraint for document-contact pairs
    op.create_unique_constraint(
        'uq_document_contact_role',
        'document_contacts',
        ['document_id', 'contact_id', 'role']
    )


def downgrade() -> None:
    op.drop_table('document_contacts')
    op.drop_table('business_contacts')
