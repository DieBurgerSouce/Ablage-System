"""RLS-GUC-NULLIF-Härtung: Paritäts-Migration der Live-Repairs vom 2026-07-12.

Überführt die beiden auf der Live-DB bereits ausgeführten Repair-Skripte
  - scripts/db/repair_rls_guc_casts_20260712.sql        (Runde 1, 25 Policies)
  - scripts/db/repair_rls_guc_casts_round2_20260712.sql (Runde 2,  4 Policies)
in die Migrationskette, damit eine from-scratch-Datenbank dieselben
gehärteten Policy-Ausdrücke trägt wie Live (F-P1-001/F-P2-008,
Perception-Audit; Paritäts-Beweis: Phoenix-DR-Probe 2026-07).

Muster:  (current_setting('app.x'::text[, true]))::TYP
     ->  (NULLIF(current_setting('app.x'::text, true), ''::text))::TYP
Deny-by-default bleibt erhalten; nur der ''::uuid/boolean-Crash entfällt.

Idempotent: die Regexe matchen nur ungehärtete Signaturen — auf einer bereits
reparierten DB (Live) ist der Lauf ein No-op ("FERTIG: 0 Policies gehaertet").

WICHTIG (alembic/env.py, asyncpg): _split_sql_statements() lässt Strings mit
$$-Blöcken nur dann ungesplittet, wenn außerhalb der $$-Blöcke höchstens ein
Semikolon steht. Deshalb ist jeder DO-Block EIN eigener op.execute-Aufruf;
niemals weitere Statements in denselben String hängen.

Bewusst NICHT Teil dieser Migration (Kontext Phoenix-Probe):
  - repair_legacy_document_status_20260712.sql  (Datenbereinigung, kein Schema)
  - repair_gobd_triggers_20260611.sql           (DDL bereits in Mig 151/234)
  - scripts/db/create_app_role.sql              (opt-in Rollen-Setup, kein Schema)

Downgrade ist bewusst ein No-op: Die Vorher-Ausdrücke sind pro Policy
heterogen und crash-anfällig — ein Rückbau der Härtung ist nie gewollt.

Revision ID: 275
Revises: 274
Create Date: 2026-07-13
"""
from alembic import op

revision = "275"
down_revision = "274"
branch_labels = None
depends_on = None

# Runde 1 — identisch zu repair_rls_guc_casts_20260712.sql (DO-Block, Z.36-86):
# Signatur (current_setting('app.x'::text, true))::boolean|uuid ohne NULLIF.
_ROUND1 = r"""
DO $$
DECLARE
    r RECORD;
    new_qual TEXT;
    new_check TEXT;
    alter_sql TEXT;
    n_changed INT := 0;
BEGIN
    FOR r IN
        SELECT p.polname, c.relname, n.nspname,
               pg_get_expr(p.polqual, p.polrelid) AS qual,
               pg_get_expr(p.polwithcheck, p.polrelid) AS chk
        FROM pg_policy p
        JOIN pg_class c ON c.oid = p.polrelid
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE coalesce(pg_get_expr(p.polqual, p.polrelid),'') ~ '\(current_setting\(''app\.[a-z_]+''::text, true\)\)::(boolean|uuid)'
           OR coalesce(pg_get_expr(p.polwithcheck, p.polrelid),'') ~ '\(current_setting\(''app\.[a-z_]+''::text, true\)\)::(boolean|uuid)'
    LOOP
        new_qual := CASE WHEN r.qual IS NULL THEN NULL ELSE
            regexp_replace(
                r.qual,
                $re$\(current_setting\('(app\.[a-z_]+)'::text, true\)\)::$re$,
                $rp$(NULLIF(current_setting('\1'::text, true), ''::text))::$rp$,
                'g'
            ) END;
        new_check := CASE WHEN r.chk IS NULL THEN NULL ELSE
            regexp_replace(
                r.chk,
                $re$\(current_setting\('(app\.[a-z_]+)'::text, true\)\)::$re$,
                $rp$(NULLIF(current_setting('\1'::text, true), ''::text))::$rp$,
                'g'
            ) END;

        alter_sql := format('ALTER POLICY %I ON %I.%I', r.polname, r.nspname, r.relname);
        IF new_qual IS NOT NULL AND new_qual IS DISTINCT FROM r.qual THEN
            alter_sql := alter_sql || format(' USING (%s)', new_qual);
        END IF;
        IF new_check IS NOT NULL AND new_check IS DISTINCT FROM r.chk THEN
            alter_sql := alter_sql || format(' WITH CHECK (%s)', new_check);
        END IF;

        IF alter_sql LIKE '%USING%' OR alter_sql LIKE '%WITH CHECK%' THEN
            RAISE NOTICE 'HAERTE: %.% (%)', r.relname, r.polname, alter_sql;
            EXECUTE alter_sql;
            n_changed := n_changed + 1;
        END IF;
    END LOOP;
    RAISE NOTICE 'FERTIG: % Policies gehaertet', n_changed;
END $$
"""

# Runde 2 — identisch zu repair_rls_guc_casts_round2_20260712.sql (DO-Block,
# Z.39-92): ältere Signatur OHNE missing_ok: (current_setting('app.x'::text))::TYP
# — doppelt fragil (unrecognized parameter bei nie gesetztem GUC + ''::uuid-Crash).
_ROUND2 = r"""
DO $$
DECLARE
    r RECORD;
    new_qual TEXT;
    new_check TEXT;
    alter_sql TEXT;
    n_changed INT := 0;
BEGIN
    FOR r IN
        SELECT p.polname, c.relname, n.nspname,
               pg_get_expr(p.polqual, p.polrelid) AS qual,
               pg_get_expr(p.polwithcheck, p.polrelid) AS chk
        FROM pg_policy p
        JOIN pg_class c ON c.oid = p.polrelid
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE coalesce(pg_get_expr(p.polqual, p.polrelid),'') ~ $q$current_setting\('app\.[a-z_]+'::text\)$q$
           OR coalesce(pg_get_expr(p.polwithcheck, p.polrelid),'') ~ $q$current_setting\('app\.[a-z_]+'::text\)$q$
    LOOP
        new_qual := CASE WHEN r.qual IS NULL THEN NULL ELSE
            regexp_replace(
                r.qual,
                $re$\(current_setting\('(app\.[a-z_]+)'::text\)\)::$re$,
                $rp$(NULLIF(current_setting('\1'::text, true), ''::text))::$rp$,
                'g'
            )
        END;
        new_check := CASE WHEN r.chk IS NULL THEN NULL ELSE
            regexp_replace(
                r.chk,
                $re$\(current_setting\('(app\.[a-z_]+)'::text\)\)::$re$,
                $rp$(NULLIF(current_setting('\1'::text, true), ''::text))::$rp$,
                'g'
            )
        END;

        alter_sql := format('ALTER POLICY %I ON %I.%I', r.polname, r.nspname, r.relname);
        IF new_qual IS NOT NULL THEN
            alter_sql := alter_sql || format(' USING (%s)', new_qual);
        END IF;
        IF new_check IS NOT NULL THEN
            alter_sql := alter_sql || format(' WITH CHECK (%s)', new_check);
        END IF;

        EXECUTE alter_sql;
        n_changed := n_changed + 1;
        RAISE NOTICE 'gehärtet: %.% (%)', r.relname, r.polname, alter_sql;
    END LOOP;

    RAISE NOTICE 'Policies gehärtet: %', n_changed;
END $$
"""

# Postcondition = exakt die Regexe der Suite
# tests/integration/test_rls_policy_guards.py: nach dieser Migration darf
# KEINE Policy mehr ungeguarded casten. Schlägt sie an, rollt alembic die
# gesamte Migration zurück (Transaktion) — die DB bleibt unverändert.
_POSTCONDITION = r"""
DO $$
DECLARE
    n_offen INT;
BEGIN
    SELECT count(*) INTO n_offen
    FROM pg_policy p
    JOIN pg_class c ON c.oid = p.polrelid
    WHERE coalesce(pg_get_expr(p.polqual, p.polrelid),'') ~ '\(current_setting\(''app\.[a-z_]+''::text, true\)\)::(boolean|uuid)'
       OR coalesce(pg_get_expr(p.polwithcheck, p.polrelid),'') ~ '\(current_setting\(''app\.[a-z_]+''::text, true\)\)::(boolean|uuid)'
       OR coalesce(pg_get_expr(p.polqual, p.polrelid),'') ~ 'current_setting\(''app\.[a-z_]+''::text\)'
       OR coalesce(pg_get_expr(p.polwithcheck, p.polrelid),'') ~ 'current_setting\(''app\.[a-z_]+''::text\)';
    IF n_offen > 0 THEN
        RAISE EXCEPTION 'Migration 275: % Policies weiterhin mit ungeguardetem app.-GUC-Cast', n_offen;
    END IF;
END $$
"""


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        # RLS-Policies existieren nur auf PostgreSQL (SQLite-Test-Runs skippen).
        return
    op.execute(_ROUND1)
    op.execute(_ROUND2)
    op.execute(_POSTCONDITION)


def downgrade() -> None:
    # Bewusst No-op: siehe Docstring — Rückbau der Härtung ist nie gewollt.
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
