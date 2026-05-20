"""Add PostgreSQL SEQUENCE for Audit Log sequence_number

Revision ID: 019
Revises: 018
Create Date: 2025-11-30

SECURITY FIX: Race Condition in get_next_sequence_number()

Das bisherige MAX(sequence_number) + 1 Verfahren hatte eine Race Condition:
Zwei gleichzeitige INSERTs konnten die gleiche Sequenznummer bekommen.

Diese Migration erstellt eine PostgreSQL SEQUENCE für atomare Sequenznummern.

Feinpoliert und durchdacht - Enterprise-grade Audit Logging.
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '019'
down_revision: Union[str, None] = '018'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Erstelle PostgreSQL SEQUENCE für audit_logs.sequence_number.

    WICHTIG: Nach dieser Migration muss get_next_sequence_number()
    nextval('audit_log_seq') verwenden statt MAX() + 1.
    """
    # PostgreSQL SEQUENCE erstellen
    # Start bei aktuellem Maximum + 1 um Konflikte zu vermeiden
    op.execute("""
        DO $$
        DECLARE
            max_seq BIGINT;
        BEGIN
            -- Hole aktuelles Maximum
            SELECT COALESCE(MAX(sequence_number), 0) + 1 INTO max_seq
            FROM audit_logs;

            -- Erstelle SEQUENCE mit korrektem Startwert
            EXECUTE format('CREATE SEQUENCE IF NOT EXISTS audit_log_seq START WITH %s INCREMENT BY 1 NO CYCLE', max_seq);

            -- Setze DEFAULT auf Spalte (für zukünftige INSERTs)
            -- Dies ist optional da wir nextval() explizit in Python aufrufen
            -- ALTER TABLE audit_logs ALTER COLUMN sequence_number SET DEFAULT nextval('audit_log_seq');

            RAISE NOTICE 'audit_log_seq erstellt mit Startwert %', max_seq;
        END $$;
    """)

    # Zusätzlich: Grant für App-User (falls nötig)
    # op.execute("GRANT USAGE, SELECT ON SEQUENCE audit_log_seq TO ablage_app;")


def downgrade() -> None:
    """
    Entferne PostgreSQL SEQUENCE.

    WARNUNG: Nach Downgrade muss get_next_sequence_number()
    wieder MAX() + 1 verwenden (mit Race Condition).
    """
    op.execute("""
        DROP SEQUENCE IF EXISTS audit_log_seq;
    """)
