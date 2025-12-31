"""Add is_active and deleted_by_id fields to privat_documents table.

Revision ID: 069_add_privat_document_soft_delete_fields
Revises: 068_add_personal_permissions
Create Date: 2024-12-30

Diese Migration fuegt fehlende Soft-Delete-Felder zur privat_documents Tabelle hinzu:
- is_active: Boolean fuer aktiven Status (GDPR-konformes Soft-Delete)
- deleted_by_id: UUID Referenz auf User der geloescht hat (Audit-Trail)

SECURITY: Diese Felder sind erforderlich fuer:
- CWE-200 Prevention: Audit-Trail wer was geloescht hat
- GDPR Art. 17: Nachvollziehbare Loeschung mit Recovery-Option
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = '069_add_privat_document_soft_delete_fields'
down_revision = '068_add_personal_permissions'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add is_active and deleted_by_id columns to privat_documents."""
    # Add is_active column with default True
    op.add_column(
        'privat_documents',
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true'))
    )

    # Add deleted_by_id column (nullable, only set when deleted)
    op.add_column(
        'privat_documents',
        sa.Column('deleted_by_id', UUID(as_uuid=True), nullable=True)
    )

    # Add foreign key constraint
    op.create_foreign_key(
        'fk_privat_documents_deleted_by_id',
        'privat_documents',
        'users',
        ['deleted_by_id'],
        ['id'],
        ondelete='SET NULL'
    )

    # Add index for is_active queries (frequently used in filters)
    op.create_index(
        'ix_privat_documents_is_active',
        'privat_documents',
        ['is_active']
    )


def downgrade() -> None:
    """Remove is_active and deleted_by_id columns from privat_documents."""
    # Drop index first
    op.drop_index('ix_privat_documents_is_active', table_name='privat_documents')

    # Drop foreign key constraint
    op.drop_constraint('fk_privat_documents_deleted_by_id', 'privat_documents', type_='foreignkey')

    # Drop columns
    op.drop_column('privat_documents', 'deleted_by_id')
    op.drop_column('privat_documents', 'is_active')
