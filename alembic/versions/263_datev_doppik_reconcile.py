"""DATEV Doppik-Reconcile: datev_buchungen + datev_kontierung_patterns an die
ORM-Modelle (Doppik: konto_soll/konto_haben/betrag_soll) angleichen.

Hintergrund (KNOWN_ISSUES "Integrationstest-Funde"): Modell und Tabelle waren
divergiert — das Modell nutzt DATEV-Doppik (konto_soll/konto_haben/betrag_soll),
die Tabellen die flache Buchungsstapel-Form (konto/gegenkonto/umsatz/soll_haben),
OHNE Migration. Nutzer-Entscheidung: Doppik (Modell) ist kanonisch.

Diese Migration ist ADDITIV + relaxiert alte NOT-NULL-Spalten (die Tabellen sind
leer -> kein Backfill/Datenrisiko). Die alten flachen Spalten bleiben vorerst
erhalten (nullable), damit nichts hart bricht; ein Cleanup-Drop kann folgen,
sobald alle Write-Pfade auf Doppik umgestellt sind (invoice_mapper etc.).

Revision ID: 263
Revises: 262
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "263"
down_revision = "262"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ---- datev_buchungen: Doppik-Spalten ergaenzen ----
    op.execute(
        """
        ALTER TABLE datev_buchungen
            ADD COLUMN IF NOT EXISTS entity_id UUID,
            ADD COLUMN IF NOT EXISTS buchungsnummer INTEGER,
            ADD COLUMN IF NOT EXISTS buchungsdatum DATE,
            ADD COLUMN IF NOT EXISTS valutadatum DATE,
            ADD COLUMN IF NOT EXISTS betrag_soll DOUBLE PRECISION NOT NULL DEFAULT 0,
            ADD COLUMN IF NOT EXISTS betrag_haben DOUBLE PRECISION NOT NULL DEFAULT 0,
            ADD COLUMN IF NOT EXISTS konto_soll VARCHAR(10) NOT NULL DEFAULT '',
            ADD COLUMN IF NOT EXISTS konto_haben VARCHAR(10) NOT NULL DEFAULT '',
            ADD COLUMN IF NOT EXISTS steuerschluessel VARCHAR(5),
            ADD COLUMN IF NOT EXISTS belegnummer VARCHAR(36),
            ADD COLUMN IF NOT EXISTS gobd_festgeschrieben BOOLEAN DEFAULT FALSE,
            ADD COLUMN IF NOT EXISTS gobd_hash VARCHAR(64),
            ADD COLUMN IF NOT EXISTS festgeschrieben_at TIMESTAMPTZ,
            ADD COLUMN IF NOT EXISTS festgeschrieben_by UUID
        """
    )
    # Server-Defaults wieder entfernen (Modell setzt die Werte explizit)
    op.execute(
        "ALTER TABLE datev_buchungen "
        "ALTER COLUMN betrag_soll DROP DEFAULT, "
        "ALTER COLUMN betrag_haben DROP DEFAULT, "
        "ALTER COLUMN konto_soll DROP DEFAULT, "
        "ALTER COLUMN konto_haben DROP DEFAULT"
    )
    # FK-Constraints fuer die neuen Referenz-Spalten
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='fk_datev_buchungen_entity') THEN
                ALTER TABLE datev_buchungen ADD CONSTRAINT fk_datev_buchungen_entity
                    FOREIGN KEY (entity_id) REFERENCES business_entities(id) ON DELETE SET NULL;
            END IF;
            IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='fk_datev_buchungen_festschr_by') THEN
                ALTER TABLE datev_buchungen ADD CONSTRAINT fk_datev_buchungen_festschr_by
                    FOREIGN KEY (festgeschrieben_by) REFERENCES users(id) ON DELETE SET NULL;
            END IF;
        END $$;
        """
    )
    # Alte flache NOT-NULL-Spalten relaxieren (Modell setzt sie nicht mehr)
    op.execute(
        """
        ALTER TABLE datev_buchungen
            ALTER COLUMN umsatz DROP NOT NULL,
            ALTER COLUMN soll_haben DROP NOT NULL,
            ALTER COLUMN konto DROP NOT NULL,
            ALTER COLUMN gegenkonto DROP NOT NULL,
            ALTER COLUMN buchungs_guid DROP NOT NULL,
            ALTER COLUMN ist_festgeschrieben DROP NOT NULL,
            ALTER COLUMN user_korrektur DROP NOT NULL,
            ALTER COLUMN retry_count DROP NOT NULL
        """
    )

    # ---- datev_kontierung_patterns: Doppik-Spalten ergaenzen ----
    op.execute(
        """
        ALTER TABLE datev_kontierung_patterns
            ADD COLUMN IF NOT EXISTS pattern_type VARCHAR(50) NOT NULL DEFAULT 'keyword',
            ADD COLUMN IF NOT EXISTS keyword_pattern VARCHAR(200),
            ADD COLUMN IF NOT EXISTS amount_min DOUBLE PRECISION,
            ADD COLUMN IF NOT EXISTS amount_max DOUBLE PRECISION,
            ADD COLUMN IF NOT EXISTS konto_soll VARCHAR(10) NOT NULL DEFAULT '',
            ADD COLUMN IF NOT EXISTS konto_haben VARCHAR(10) NOT NULL DEFAULT '',
            ADD COLUMN IF NOT EXISTS steuerschluessel VARCHAR(5),
            ADD COLUMN IF NOT EXISTS confidence DOUBLE PRECISION DEFAULT 0.5
        """
    )
    op.execute(
        "ALTER TABLE datev_kontierung_patterns "
        "ALTER COLUMN pattern_type DROP DEFAULT, "
        "ALTER COLUMN konto_soll DROP DEFAULT, "
        "ALTER COLUMN konto_haben DROP DEFAULT"
    )
    op.execute(
        """
        ALTER TABLE datev_kontierung_patterns
            ALTER COLUMN konto DROP NOT NULL,
            ALTER COLUMN gegenkonto DROP NOT NULL,
            ALTER COLUMN pattern_source DROP NOT NULL,
            ALTER COLUMN priority DROP NOT NULL
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE datev_kontierung_patterns
            ALTER COLUMN konto SET NOT NULL,
            ALTER COLUMN gegenkonto SET NOT NULL,
            ALTER COLUMN pattern_source SET NOT NULL,
            ALTER COLUMN priority SET NOT NULL
        """
    )
    op.execute(
        """
        ALTER TABLE datev_kontierung_patterns
            DROP COLUMN IF EXISTS pattern_type,
            DROP COLUMN IF EXISTS keyword_pattern,
            DROP COLUMN IF EXISTS amount_min,
            DROP COLUMN IF EXISTS amount_max,
            DROP COLUMN IF EXISTS konto_soll,
            DROP COLUMN IF EXISTS konto_haben,
            DROP COLUMN IF EXISTS steuerschluessel,
            DROP COLUMN IF EXISTS confidence
        """
    )
    op.execute("ALTER TABLE datev_buchungen DROP CONSTRAINT IF EXISTS fk_datev_buchungen_entity")
    op.execute("ALTER TABLE datev_buchungen DROP CONSTRAINT IF EXISTS fk_datev_buchungen_festschr_by")
    op.execute(
        """
        ALTER TABLE datev_buchungen
            ALTER COLUMN umsatz SET NOT NULL,
            ALTER COLUMN soll_haben SET NOT NULL,
            ALTER COLUMN konto SET NOT NULL,
            ALTER COLUMN gegenkonto SET NOT NULL,
            ALTER COLUMN buchungs_guid SET NOT NULL,
            ALTER COLUMN ist_festgeschrieben SET NOT NULL,
            ALTER COLUMN user_korrektur SET NOT NULL,
            ALTER COLUMN retry_count SET NOT NULL
        """
    )
    op.execute(
        """
        ALTER TABLE datev_buchungen
            DROP COLUMN IF EXISTS entity_id,
            DROP COLUMN IF EXISTS buchungsnummer,
            DROP COLUMN IF EXISTS buchungsdatum,
            DROP COLUMN IF EXISTS valutadatum,
            DROP COLUMN IF EXISTS betrag_soll,
            DROP COLUMN IF EXISTS betrag_haben,
            DROP COLUMN IF EXISTS konto_soll,
            DROP COLUMN IF EXISTS konto_haben,
            DROP COLUMN IF EXISTS steuerschluessel,
            DROP COLUMN IF EXISTS belegnummer,
            DROP COLUMN IF EXISTS gobd_festgeschrieben,
            DROP COLUMN IF EXISTS gobd_hash,
            DROP COLUMN IF EXISTS festgeschrieben_at,
            DROP COLUMN IF EXISTS festgeschrieben_by
        """
    )
