"""add_tunes

Revision ID: 031
Revises: 030
Create Date: 2025-12-09 00:05:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
import uuid

# revision identifiers, used by Alembic.
revision = '031_add_tunes'
down_revision = '030_add_bulk_processing'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create tunes table
    tunes_table = op.create_table(
        'tunes',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('description', sa.String(length=500), nullable=True),
        sa.Column('icon', sa.String(length=50), nullable=True),
        sa.Column('color', sa.String(length=50), nullable=True),
        sa.Column('prompt_template', sa.Text(), nullable=True),
        sa.Column('default_backend', sa.String(length=50), nullable=True),
        sa.Column('is_system', sa.Boolean(), nullable=True, default=False),
        sa.Column('is_active', sa.Boolean(), nullable=True, default=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name')
    )

    # Create indexes
    op.create_index('ix_tunes_is_active', 'tunes', ['is_active'], unique=False)
    op.create_index('ix_tunes_name', 'tunes', ['name'], unique=False)

    # Seed default tunes with FIXED UUIDs for idempotency
    # These UUIDs are deterministic so the migration can be safely re-run
    default_tunes = [
        {
            'id': uuid.UUID('a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d'),
            'name': 'Rechnungen & Finanzen',
            'description': 'Optimiert für Rechnungen, Belege und Steuerdokumente.',
            'icon': 'Receipt',
            'color': 'bg-emerald-500',
            'is_system': True,
            'is_active': True
            # created_at and updated_at use server_default
        },
        {
            'id': uuid.UUID('b2c3d4e5-f6a7-4b8c-9d0e-1f2a3b4c5d6e'),
            'name': 'Verträge & Rechtliches',
            'description': 'Erkennt Klauseln, Unterschriften und rechtliche Strukturen.',
            'icon': 'Scale',
            'color': 'bg-blue-500',
            'is_system': True,
            'is_active': True
        },
        {
            'id': uuid.UUID('c3d4e5f6-a7b8-4c9d-0e1f-2a3b4c5d6e7f'),
            'name': 'Allgemeiner Schriftverkehr',
            'description': 'Für Briefe, Notizen und sonstige Korrespondenz.',
            'icon': 'Mail',
            'color': 'bg-amber-500',
            'is_system': True,
            'is_active': True
        },
        {
            'id': uuid.UUID('d4e5f6a7-b8c9-4d0e-1f2a-3b4c5d6e7f8a'),
            'name': 'Technische Dokumentation',
            'description': 'Für Handbücher, Datenblätter und technische Zeichnungen.',
            'icon': 'Wrench',
            'color': 'bg-slate-500',
            'is_system': True,
            'is_active': True
        }
    ]

    op.bulk_insert(tunes_table, default_tunes)


def downgrade() -> None:
    op.drop_index('ix_tunes_name', table_name='tunes')
    op.drop_index('ix_tunes_is_active', table_name='tunes')
    op.drop_table('tunes')
