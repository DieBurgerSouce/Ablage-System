"""fix_tunes_migration

Revision ID: 031b_fix_tunes
Revises: 031_add_tunes
Create Date: 2025-12-09 12:00:00.000000

Behebt Probleme in der Tunes-Migration:
- Fügt server_default für id hinzu (gen_random_uuid())
- Erstellt update_updated_at Trigger
- Fügt Index für is_system hinzu
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '031b_fix_tunes'
down_revision = '031_add_tunes'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Erstelle Trigger-Funktion für updated_at (falls nicht existiert)
    op.execute("""
        CREATE OR REPLACE FUNCTION tunes_update_updated_at_column()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = CURRENT_TIMESTAMP;
            RETURN NEW;
        END;
        $$ language 'plpgsql';
    """)

    # Erstelle Trigger auf tunes-Tabelle
    op.execute("""
        DROP TRIGGER IF EXISTS update_tunes_updated_at ON tunes;
        CREATE TRIGGER update_tunes_updated_at
            BEFORE UPDATE ON tunes
            FOR EACH ROW
            EXECUTE FUNCTION tunes_update_updated_at_column();
    """)

    # Ändere id-Column um server_default hinzuzufügen
    op.alter_column(
        'tunes',
        'id',
        server_default=sa.text('gen_random_uuid()')
    )

    # Erstelle zusätzlichen Index für is_system (häufig gefiltert)
    op.create_index(
        'ix_tunes_is_system',
        'tunes',
        ['is_system'],
        unique=False
    )

    # Composite Index für aktive nicht-system Tunes
    op.create_index(
        'ix_tunes_is_active_is_system',
        'tunes',
        ['is_active', 'is_system'],
        unique=False
    )


def downgrade() -> None:
    # Entferne Composite Index
    op.drop_index('ix_tunes_is_active_is_system', table_name='tunes')

    # Entferne is_system Index
    op.drop_index('ix_tunes_is_system', table_name='tunes')

    # Entferne server_default
    op.alter_column(
        'tunes',
        'id',
        server_default=None
    )

    # Entferne Trigger
    op.execute("DROP TRIGGER IF EXISTS update_tunes_updated_at ON tunes;")

    # Entferne Trigger-Funktion
    op.execute("DROP FUNCTION IF EXISTS tunes_update_updated_at_column();")
