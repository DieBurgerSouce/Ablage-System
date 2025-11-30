"""Add Audit Log Immutability fields

Revision ID: 017
Revises: 016
Create Date: 2025-11-30

Arbeitspaket 6: Audit Log Immutabilität

Fügt Felder für Blockchain-ähnliche Unveränderlichkeit hinzu:
- sequence_number: Aufsteigende Sequenznummer für Reihenfolge
- integrity_hash: SHA-256 Hash des Eintrags für Tamper-Detection
- previous_hash: Hash des Vorgängers für Verkettung

SECURITY: Diese Migration fügt auch Datenbank-Trigger hinzu um
UPDATE/DELETE-Operationen auf der audit_logs-Tabelle zu verhindern.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '017'
down_revision: Union[str, None] = '016'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Füge Immutabilitäts-Felder und Schutz-Trigger hinzu.
    """
    # Sequenznummer - BigInteger für sehr große Logs
    op.add_column(
        'audit_logs',
        sa.Column('sequence_number', sa.BigInteger(), nullable=True)
    )

    # Integrity-Hash - SHA-256 (64 Hex-Zeichen)
    op.add_column(
        'audit_logs',
        sa.Column('integrity_hash', sa.String(64), nullable=True)
    )

    # Previous-Hash - Verkettung zum Vorgänger
    op.add_column(
        'audit_logs',
        sa.Column('previous_hash', sa.String(64), nullable=True)
    )

    # Unique-Index für Sequenznummer
    op.create_index(
        'ix_audit_logs_sequence_number',
        'audit_logs',
        ['sequence_number'],
        unique=True
    )

    # Index für schnelle Hash-Lookups
    op.create_index(
        'ix_audit_logs_integrity_hash',
        'audit_logs',
        ['integrity_hash']
    )

    # PostgreSQL-spezifische Trigger für Immutabilität
    # Verhindert UPDATE und DELETE auf audit_logs
    op.execute("""
        -- Trigger-Funktion für UPDATE-Verhinderung
        CREATE OR REPLACE FUNCTION audit_logs_prevent_update()
        RETURNS TRIGGER AS $$
        BEGIN
            RAISE EXCEPTION 'UPDATE nicht erlaubt auf audit_logs (Immutabilität)';
            RETURN NULL;
        END;
        $$ LANGUAGE plpgsql;

        -- Trigger-Funktion für DELETE-Verhinderung
        CREATE OR REPLACE FUNCTION audit_logs_prevent_delete()
        RETURNS TRIGGER AS $$
        BEGIN
            RAISE EXCEPTION 'DELETE nicht erlaubt auf audit_logs (Immutabilität)';
            RETURN NULL;
        END;
        $$ LANGUAGE plpgsql;

        -- Trigger erstellen
        DROP TRIGGER IF EXISTS tr_audit_logs_no_update ON audit_logs;
        CREATE TRIGGER tr_audit_logs_no_update
            BEFORE UPDATE ON audit_logs
            FOR EACH ROW
            EXECUTE FUNCTION audit_logs_prevent_update();

        DROP TRIGGER IF EXISTS tr_audit_logs_no_delete ON audit_logs;
        CREATE TRIGGER tr_audit_logs_no_delete
            BEFORE DELETE ON audit_logs
            FOR EACH ROW
            EXECUTE FUNCTION audit_logs_prevent_delete();
    """)


def downgrade() -> None:
    """
    Entferne Immutabilitäts-Features.

    WARNUNG: Downgrade entfernt die Integritätsprüfung!
    """
    # PostgreSQL-Trigger entfernen
    op.execute("""
        DROP TRIGGER IF EXISTS tr_audit_logs_no_update ON audit_logs;
        DROP TRIGGER IF EXISTS tr_audit_logs_no_delete ON audit_logs;
        DROP FUNCTION IF EXISTS audit_logs_prevent_update();
        DROP FUNCTION IF EXISTS audit_logs_prevent_delete();
    """)

    # Indexes entfernen
    op.drop_index('ix_audit_logs_integrity_hash', table_name='audit_logs')
    op.drop_index('ix_audit_logs_sequence_number', table_name='audit_logs')

    # Spalten entfernen
    op.drop_column('audit_logs', 'previous_hash')
    op.drop_column('audit_logs', 'integrity_hash')
    op.drop_column('audit_logs', 'sequence_number')
