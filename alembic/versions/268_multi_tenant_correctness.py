"""Multi-Tenant-Korrektheit (Welle 1 / Workstream 1a).

Vier verifizierte Defekte (Stand 2026-06-10):

1. ``business_entities.company_id``: Spalte fehlte in Modell UND DB, obwohl
   ``GET /entities/{id}`` (G5-Fix) und 10+ Services sie referenzieren ->
   AttributeError/500 zur Laufzeit. Nullable: NULL = firmenuebergreifende
   (globale) Entity, gefiltert wird mit ``company_id == X OR company_id IS NULL``.
2. ``user_companies``: Bestands-Korruption (mehrere ``is_current=True`` pro
   User) loeste ``MultipleResultsFound``-500er in ``get_user_current_company``
   und ``get_user_company_id`` aus. Dedupe (neueste Mitgliedschaft gewinnt)
   plus Partial-Unique-Index als dauerhafter Schutz.
3. ``processing_jobs``: Partial-Unique fuer aktive Jobs pro (Dokument, Typ) -
   Grundlage fuer Celery-Idempotenz via ``INSERT .. ON CONFLICT DO NOTHING``.
4. ``bank_accounts.user_id`` DROP NOT NULL: Banking ist seit Migration 232
   company-scoped; ``AccountService.create_account()`` legt Konten ohne
   user_id an - NOT NULL liess jede Konto-Anlage mit NotNullViolation
   scheitern (von den reaktivierten Banking-Multi-Tenant-Tests aufgedeckt).

Idempotent (IF NOT EXISTS / geguardete Updates), additiv. Downgrade entfernt
nur die neuen Indizes; Daten-Bereinigungen und die Spalte bleiben erhalten
(ein Downgrade darf keine Daten verlieren).

Revision ID: 268
Revises: 267
Create Date: 2026-06-10
"""
import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "268"
down_revision = "267"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()

    # --- 1. business_entities.company_id (Spalte + FK + Index) ---------------
    bind.execute(sa.text(
        "ALTER TABLE business_entities ADD COLUMN IF NOT EXISTS company_id UUID"
    ))
    bind.execute(sa.text(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = 'fk_business_entities_company_id'
            ) THEN
                ALTER TABLE business_entities
                    ADD CONSTRAINT fk_business_entities_company_id
                    FOREIGN KEY (company_id) REFERENCES companies(id)
                    ON DELETE CASCADE;
            END IF;
        END $$;
        """
    ))
    bind.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_business_entities_company_id "
        "ON business_entities (company_id)"
    ))

    # --- 2. user_companies: is_current-Dedupe + Partial-Unique ---------------
    # Neueste Mitgliedschaft gewinnt (analog zur defensiven Leselogik).
    bind.execute(sa.text(
        """
        UPDATE user_companies SET is_current = false
        WHERE id IN (
            SELECT id FROM (
                SELECT id, ROW_NUMBER() OVER (
                    PARTITION BY user_id
                    ORDER BY created_at DESC NULLS LAST, id DESC
                ) AS rn
                FROM user_companies
                WHERE is_current = true
            ) ranked
            WHERE ranked.rn > 1
        )
        """
    ))
    bind.execute(sa.text(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_user_companies_one_current "
        "ON user_companies (user_id) WHERE is_current = true"
    ))

    # --- 3. processing_jobs: aktive Duplikate stilllegen + Partial-Unique ----
    bind.execute(sa.text(
        """
        UPDATE processing_jobs SET status = 'cancelled'
        WHERE id IN (
            SELECT id FROM (
                SELECT id, ROW_NUMBER() OVER (
                    PARTITION BY document_id, job_type
                    ORDER BY created_at DESC NULLS LAST, id DESC
                ) AS rn
                FROM processing_jobs
                WHERE status IN ('queued', 'processing')
            ) ranked
            WHERE ranked.rn > 1
        )
        """
    ))
    bind.execute(sa.text(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_processing_jobs_active_per_doc_type "
        "ON processing_jobs (document_id, job_type) "
        "WHERE status IN ('queued', 'processing')"
    ))

    # --- 4. Banking user_id nullable (company-scoped Services) ----------------
    # bank_accounts: AccountService.create_account setzt kein user_id.
    # bank_imports:  ImportService.import_file setzt kein user_id (NOT NULL
    #                maskierte sich als falscher Duplikat-Fehler).
    # dunning_records: DunningService.create_dunning - user_id nur Audit-Kontext.
    bind.execute(sa.text(
        "ALTER TABLE bank_accounts ALTER COLUMN user_id DROP NOT NULL"
    ))
    bind.execute(sa.text(
        "ALTER TABLE bank_imports ALTER COLUMN user_id DROP NOT NULL"
    ))
    bind.execute(sa.text(
        "ALTER TABLE dunning_records ALTER COLUMN user_id DROP NOT NULL"
    ))


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(sa.text(
        "DROP INDEX IF EXISTS uq_processing_jobs_active_per_doc_type"
    ))
    bind.execute(sa.text(
        "DROP INDEX IF EXISTS uq_user_companies_one_current"
    ))
    # business_entities.company_id, die Daten-Bereinigungen und die
    # user_id-Nullability bleiben bewusst erhalten (kein Datenverlust).
