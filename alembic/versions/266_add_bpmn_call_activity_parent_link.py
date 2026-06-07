"""BPMN Call Activity: Eltern-Instanz-Verknuepfung an bpmn_process_instances.

Fuegt zwei Spalten hinzu, damit eine Call Activity eine eigene Sub-Instanz der
aufgerufenen Prozess-Definition starten und nach deren Abschluss die Eltern-
Instanz fortsetzen kann:
- parent_instance_id  -> FK auf bpmn_process_instances.id (self-referential)
- parent_element_id   -> Call-Activity-Element-ID in der Eltern-Instanz

Idempotent (ADD COLUMN IF NOT EXISTS + FK/Index in DO-Bloecken), damit sowohl der
from-scratch-Pfad (Migration 265 create_all hat die Spalten ggf. schon angelegt)
als auch die reale Bestands-DB (Tabelle existiert ohne die Spalten) sauber laufen.

Revision ID: 266
Revises: 265
Create Date: 2026-06-07
"""
from alembic import op

# revision identifiers, used by Alembic.
revision = "266"
down_revision = "265"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Spalten idempotent ergaenzen (Postgres).
    op.execute(
        "ALTER TABLE bpmn_process_instances "
        "ADD COLUMN IF NOT EXISTS parent_instance_id UUID"
    )
    op.execute(
        "ALTER TABLE bpmn_process_instances "
        "ADD COLUMN IF NOT EXISTS parent_element_id VARCHAR(255)"
    )

    # Self-referential FK (ON DELETE SET NULL) nur anlegen, wenn noch nicht vorhanden.
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = 'fk_bpmn_process_instances_parent_instance_id'
            ) THEN
                ALTER TABLE bpmn_process_instances
                ADD CONSTRAINT fk_bpmn_process_instances_parent_instance_id
                FOREIGN KEY (parent_instance_id)
                REFERENCES bpmn_process_instances (id) ON DELETE SET NULL;
            END IF;
        END $$;
        """
    )

    # Index fuer Eltern-Lookups (Rueckkopplung) idempotent.
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_bpmn_process_instances_parent_instance_id "
        "ON bpmn_process_instances (parent_instance_id)"
    )


def downgrade() -> None:
    op.execute(
        "DROP INDEX IF EXISTS ix_bpmn_process_instances_parent_instance_id"
    )
    op.execute(
        "ALTER TABLE bpmn_process_instances "
        "DROP CONSTRAINT IF EXISTS fk_bpmn_process_instances_parent_instance_id"
    )
    op.execute(
        "ALTER TABLE bpmn_process_instances DROP COLUMN IF EXISTS parent_element_id"
    )
    op.execute(
        "ALTER TABLE bpmn_process_instances DROP COLUMN IF EXISTS parent_instance_id"
    )
