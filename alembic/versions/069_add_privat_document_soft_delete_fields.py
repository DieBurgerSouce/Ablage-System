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

revision = "069"
down_revision = "068"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add is_active and deleted_by_id columns to privat_documents.

    IDEMPOTENT: Prueft ob Tabelle/Spalten existieren bevor Aenderungen gemacht werden.
    """
    op.execute("""
        DO $$
        BEGIN
            -- Nur ausfuehren wenn privat_documents Tabelle existiert
            IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'privat_documents') THEN

                -- is_active Spalte hinzufuegen
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'privat_documents' AND column_name = 'is_active'
                ) THEN
                    ALTER TABLE privat_documents ADD COLUMN is_active BOOLEAN NOT NULL DEFAULT true;
                END IF;

                -- deleted_by_id Spalte hinzufuegen
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'privat_documents' AND column_name = 'deleted_by_id'
                ) THEN
                    ALTER TABLE privat_documents ADD COLUMN deleted_by_id UUID;

                    -- Foreign Key nur hinzufuegen wenn Spalte neu erstellt wurde
                    ALTER TABLE privat_documents
                    ADD CONSTRAINT fk_privat_documents_deleted_by_id
                    FOREIGN KEY (deleted_by_id) REFERENCES users(id) ON DELETE SET NULL;
                END IF;

                -- Index erstellen (IF NOT EXISTS ist PostgreSQL 9.5+)
                CREATE INDEX IF NOT EXISTS ix_privat_documents_is_active ON privat_documents(is_active);

            END IF;
        END $$;
    """)


def downgrade() -> None:
    """Remove is_active and deleted_by_id columns from privat_documents.

    IDEMPOTENT: Prueft ob Tabelle/Spalten existieren bevor Aenderungen gemacht werden.
    """
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'privat_documents') THEN
                -- Index droppen
                DROP INDEX IF EXISTS ix_privat_documents_is_active;

                -- Foreign Key Constraint droppen
                IF EXISTS (
                    SELECT 1 FROM information_schema.table_constraints
                    WHERE constraint_name = 'fk_privat_documents_deleted_by_id'
                ) THEN
                    ALTER TABLE privat_documents DROP CONSTRAINT fk_privat_documents_deleted_by_id;
                END IF;

                -- Spalten droppen
                IF EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'privat_documents' AND column_name = 'deleted_by_id'
                ) THEN
                    ALTER TABLE privat_documents DROP COLUMN deleted_by_id;
                END IF;

                IF EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'privat_documents' AND column_name = 'is_active'
                ) THEN
                    ALTER TABLE privat_documents DROP COLUMN is_active;
                END IF;
            END IF;
        END $$;
    """)
