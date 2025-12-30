"""Fix PrivatEmergencyContact relationship column name - SQLAlchemy reserved.

Revision ID: 065_fix_privat_relationship_column
Revises: 064_add_validation_queue_system
Create Date: 2024-12-30

'relationship' ist eine SQLAlchemy ORM-Funktion und darf nicht als
Spaltenname verwendet werden, da es das Symbol ueberschreibt.
Umbenennung zu 'contact_relationship' erforderlich.
"""
from alembic import op

revision = '065_fix_privat_relationship_column'
down_revision = '064_add_validation_queue_system'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Rename relationship -> contact_relationship in privat_emergency_contacts."""
    op.alter_column(
        'privat_emergency_contacts',
        'relationship',
        new_column_name='contact_relationship'
    )


def downgrade() -> None:
    """Revert contact_relationship -> relationship in privat_emergency_contacts."""
    op.alter_column(
        'privat_emergency_contacts',
        'contact_relationship',
        new_column_name='relationship'
    )
