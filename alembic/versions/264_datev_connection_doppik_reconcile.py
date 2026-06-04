"""DATEV Doppik-Reconcile Teil 2: datev_connections an das DATEVConnection-Modell
angleichen (Modell nutzt berater_nr/mandant_nr/environment + Zusatzfelder; die
Tabelle hatte beraternummer/mandantennummer/api_environment).

Additiv + alte NOT-NULL relaxiert (Tabelle leer -> kein Backfill/Datenrisiko).
Die alten Spalten + ihre CHECK-Constraints bleiben erhalten; Modell-Inserts lassen
sie NULL (CHECK auf NULL = erfuellt), neue Felder werden gesetzt.

Revision ID: 264
Revises: 263
"""
from alembic import op

revision = "264"
down_revision = "263"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE datev_connections
            ADD COLUMN IF NOT EXISTS created_by_id UUID,
            ADD COLUMN IF NOT EXISTS description TEXT,
            ADD COLUMN IF NOT EXISTS mandant_nr VARCHAR(10),
            ADD COLUMN IF NOT EXISTS berater_nr VARCHAR(10),
            ADD COLUMN IF NOT EXISTS environment VARCHAR(20),
            ADD COLUMN IF NOT EXISTS webhook_url VARCHAR(500),
            ADD COLUMN IF NOT EXISTS auto_kontierung BOOLEAN DEFAULT FALSE,
            ADD COLUMN IF NOT EXISTS auto_beleg_upload BOOLEAN DEFAULT FALSE,
            ADD COLUMN IF NOT EXISTS sync_interval_minutes INTEGER,
            ADD COLUMN IF NOT EXISTS last_buchung_nr INTEGER,
            ADD COLUMN IF NOT EXISTS last_sync_at TIMESTAMPTZ
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='fk_datev_conn_created_by') THEN
                ALTER TABLE datev_connections ADD CONSTRAINT fk_datev_conn_created_by
                    FOREIGN KEY (created_by_id) REFERENCES users(id) ON DELETE SET NULL;
            END IF;
        END $$;
        """
    )
    # Alte (Buchungsstapel-)NOT-NULL relaxieren, da das Modell sie nicht mehr setzt
    op.execute(
        """
        ALTER TABLE datev_connections
            ALTER COLUMN beraternummer DROP NOT NULL,
            ALTER COLUMN mandantennummer DROP NOT NULL,
            ALTER COLUMN api_environment DROP NOT NULL,
            ALTER COLUMN buchungsmodus DROP NOT NULL,
            ALTER COLUMN gobd_enabled DROP NOT NULL,
            ALTER COLUMN festschreibung_automatisch DROP NOT NULL,
            ALTER COLUMN sachkontenlange DROP NOT NULL,
            ALTER COLUMN personenkontenlange DROP NOT NULL,
            ALTER COLUMN enabled_features DROP NOT NULL
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE datev_connections
            ALTER COLUMN beraternummer SET NOT NULL,
            ALTER COLUMN mandantennummer SET NOT NULL,
            ALTER COLUMN api_environment SET NOT NULL,
            ALTER COLUMN buchungsmodus SET NOT NULL,
            ALTER COLUMN gobd_enabled SET NOT NULL,
            ALTER COLUMN festschreibung_automatisch SET NOT NULL,
            ALTER COLUMN sachkontenlange SET NOT NULL,
            ALTER COLUMN personenkontenlange SET NOT NULL,
            ALTER COLUMN enabled_features SET NOT NULL
        """
    )
    op.execute("ALTER TABLE datev_connections DROP CONSTRAINT IF EXISTS fk_datev_conn_created_by")
    op.execute(
        """
        ALTER TABLE datev_connections
            DROP COLUMN IF EXISTS created_by_id,
            DROP COLUMN IF EXISTS description,
            DROP COLUMN IF EXISTS mandant_nr,
            DROP COLUMN IF EXISTS berater_nr,
            DROP COLUMN IF EXISTS environment,
            DROP COLUMN IF EXISTS webhook_url,
            DROP COLUMN IF EXISTS auto_kontierung,
            DROP COLUMN IF EXISTS auto_beleg_upload,
            DROP COLUMN IF EXISTS sync_interval_minutes,
            DROP COLUMN IF EXISTS last_buchung_nr,
            DROP COLUMN IF EXISTS last_sync_at
        """
    )
