"""Drift-Reconcile E4 (Nachzuegler): Render-Normalisierung der letzten 5 Objekte.

Nach dem Live-Lauf von 276-278 verblieben im Katalog-Diff Live<->Frisch exakt
10 Zeilen (= 5 Objekte, je beidseitig): die 4 CHECK-Constraints und der eine
Partial-Index, die Migration 278 auf Live NEU anlegte. PostgreSQL speichert
den geparsten Ausdrucksbaum - dieselbe Quell-DDL ergibt je nach Parse-Vintage
unterschiedliche pg_get_constraintdef/indexdef-Renderings:

  alt (Frisch, via Original-Migrationen):  ANY ((ARRAY['a', 'b'])::text[])
  neu (Live, via 278):                     ANY (ARRAY[('a')::text, ('b')::text])

Semantisch identisch (gleiche Wertelisten, gleiche Logik). Damit kuenftige
Katalog-Diffs OHNE Whitelist-Eintrag auskommen, werden die 5 Objekte hier auf
BEIDEN Seiten unconditional gedroppt und mit identischer DDL neu angelegt -
beide Seiten erhalten dasselbe (aktuelle) Rendering. Betroffene Tabellen
haben 0 Zeilen (live verifiziert 2026-07-14); CHECK-/Index-Validierung ist
trivial. Doppellauf-idempotent (Drop+Recreate konvergiert auf denselben Zustand).

Downgrade = No-op: Es gibt keinen semantischen Vorher-Zustand, nur ein
anderes Rendering desselben Ausdrucks.

Revision ID: 279
Revises: 278
Create Date: 2026-07-14
"""
from alembic import op

revision = "279"
down_revision = "278"
branch_labels = None
depends_on = None

_STATEMENTS = [
    "ALTER TABLE integration_configs DROP CONSTRAINT IF EXISTS ck_integration_configs_last_status",
    "ALTER TABLE integration_configs ADD CONSTRAINT ck_integration_configs_last_status "
    "CHECK (((last_sync_status IS NULL) OR ((last_sync_status)::text = ANY "
    "(ARRAY[('success'::character varying)::text, ('error'::character varying)::text, "
    "('partial'::character varying)::text]))))",
    "ALTER TABLE integration_configs DROP CONSTRAINT IF EXISTS ck_integration_configs_type",
    "ALTER TABLE integration_configs ADD CONSTRAINT ck_integration_configs_type "
    "CHECK (((integration_type)::text = ANY (ARRAY[('datev'::character varying)::text, "
    "('lexware'::character varying)::text, ('banking'::character varying)::text, "
    "('slack'::character varying)::text, ('email'::character varying)::text])))",
    "ALTER TABLE integration_sync_logs DROP CONSTRAINT IF EXISTS ck_sync_logs_status",
    "ALTER TABLE integration_sync_logs ADD CONSTRAINT ck_sync_logs_status "
    "CHECK (((status)::text = ANY (ARRAY[('started'::character varying)::text, "
    "('success'::character varying)::text, ('error'::character varying)::text, "
    "('partial'::character varying)::text])))",
    "ALTER TABLE integration_sync_logs DROP CONSTRAINT IF EXISTS ck_sync_logs_sync_type",
    "ALTER TABLE integration_sync_logs ADD CONSTRAINT ck_sync_logs_sync_type "
    "CHECK (((sync_type)::text = ANY (ARRAY[('full'::character varying)::text, "
    "('incremental'::character varying)::text, ('manual'::character varying)::text])))",
    "DROP INDEX IF EXISTS ix_webhook_deliveries_retry_pending",
    "CREATE INDEX IF NOT EXISTS ix_webhook_deliveries_retry_pending "
    "ON public.webhook_deliveries USING btree (status, next_retry_at) "
    "WHERE (((status)::text = ANY (ARRAY[('pending'::character varying)::text, "
    "('failed'::character varying)::text])) AND (next_retry_at IS NOT NULL))",
]

_POSTCONDITION = """\
DO $$
DECLARE n INT;
BEGIN
    SELECT count(*) INTO n FROM pg_constraint
    WHERE conname IN ('ck_integration_configs_last_status', 'ck_integration_configs_type',
                      'ck_sync_logs_status', 'ck_sync_logs_sync_type');
    IF n <> 4 THEN
        RAISE EXCEPTION 'Migration 279: CHECK-Constraints unvollstaendig (%/4)', n;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_class WHERE relname = 'ix_webhook_deliveries_retry_pending'
                   AND relkind = 'i') THEN
        RAISE EXCEPTION 'Migration 279: ix_webhook_deliveries_retry_pending fehlt';
    END IF;
END $$
"""


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    for stmt in _STATEMENTS:
        op.execute(stmt)
    op.execute(_POSTCONDITION)


def downgrade() -> None:
    # Bewusst No-op: siehe Docstring.
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
