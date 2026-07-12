-- repair_rls_guc_casts_round2_20260712.sql
--
-- BEFUND (Perception-Audit 2026-07-12, Iteration 03, F-P2-008): /smart-inbox*
-- liefert HTTP 500 ("invalid input syntax for type uuid: ''") sobald ein
-- Nutzer OHNE Company-Kontext zugreift (z. B. Bearer-Login ohne
-- Company-Header — genau der F-31-Live-Sweep-Weg).
--
-- ROOT CAUSE: 4 Alt-Policies (zero_touch_results, nlq_query_logs,
-- smart_inbox_items, user_behavior_logs) nutzen eine ÄLTERE Signatur als die
-- 25 in repair_rls_guc_casts_20260712.sql gefixten:
--     current_setting('app.current_company_id'::text)        -- OHNE ", true"
-- Der dortige Repair-Regex matchte nur die "…, true)"-Form -> diese 4 blieben
-- ungehärtet. Sie sind doppelt fragil:
--   1. GUC nie gesetzt   -> "unrecognized configuration parameter"-Fehler
--   2. GUC = ''          -> ''::uuid -> InvalidTextRepresentationError
--
-- WIRKUNG: Umschreiben auf das kanonische Guard-Muster
--     (NULLIF(current_setting('app.x'::text, true), ''::text))::uuid
-- -> fehlender/leerer Kontext ergibt NULL -> Zeile verweigert
-- (deny-by-default bleibt ERHALTEN, nur der Crash entfällt).
--
-- AUSFUEHRUNG (idempotent, nur Policy-Ausdruecke, keine Datenaenderung):
--   docker exec -i ablage-postgres sh -c \
--     'PGPASSWORD="$POSTGRES_PASSWORD" psql -h 127.0.0.1 -U "$POSTGRES_USER" -d ablage_system' \
--     < scripts/db/repair_rls_guc_casts_round2_20260712.sql
--
-- FOLLOWUP: zusammen mit Runde 1 in eine reguläre Alembic-Migration
-- ueberfuehren (deferred-migration, siehe REPORT.md).

\echo '=== VORHER: Policies mit current_setting OHNE missing_ok ==='
SELECT c.relname AS tabelle, p.polname,
       pg_get_expr(p.polqual, p.polrelid) AS using_expr,
       pg_get_expr(p.polwithcheck, p.polrelid) AS check_expr
FROM pg_policy p JOIN pg_class c ON c.oid = p.polrelid
WHERE coalesce(pg_get_expr(p.polqual, p.polrelid),'') ~ $q$current_setting\('app\.[a-z_]+'::text\)$q$
   OR coalesce(pg_get_expr(p.polwithcheck, p.polrelid),'') ~ $q$current_setting\('app\.[a-z_]+'::text\)$q$
ORDER BY c.relname, p.polname;

DO $$
DECLARE
    r RECORD;
    new_qual TEXT;
    new_check TEXT;
    alter_sql TEXT;
    n_changed INT := 0;
BEGIN
    FOR r IN
        SELECT p.polname,
               c.relname,
               n.nspname,
               pg_get_expr(p.polqual, p.polrelid) AS qual,
               pg_get_expr(p.polwithcheck, p.polrelid) AS chk
        FROM pg_policy p
        JOIN pg_class c ON c.oid = p.polrelid
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE coalesce(pg_get_expr(p.polqual, p.polrelid),'') ~ $q$current_setting\('app\.[a-z_]+'::text\)$q$
           OR coalesce(pg_get_expr(p.polwithcheck, p.polrelid),'') ~ $q$current_setting\('app\.[a-z_]+'::text\)$q$
    LOOP
        -- (current_setting('app.x'::text))::TYP
        --   -> (NULLIF(current_setting('app.x'::text, true), ''::text))::TYP
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
END $$;

\echo '=== NACHHER: verbleibende Policies OHNE missing_ok (muss leer sein) ==='
SELECT c.relname AS tabelle, p.polname
FROM pg_policy p JOIN pg_class c ON c.oid = p.polrelid
WHERE coalesce(pg_get_expr(p.polqual, p.polrelid),'') ~ $q$current_setting\('app\.[a-z_]+'::text\)$q$
   OR coalesce(pg_get_expr(p.polwithcheck, p.polrelid),'') ~ $q$current_setting\('app\.[a-z_]+'::text\)$q$
ORDER BY c.relname, p.polname;
