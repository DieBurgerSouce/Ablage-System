-- repair_rls_guc_casts_20260712.sql
--
-- BEFUND (Perception-Audit 2026-07-12, F-P1-001): Nicht-Admin-Upload endet in
-- HTTP 500: "invalid input syntax for type boolean: ''".
--
-- ROOT CAUSE: Nach `SELECT set_config('app.x', ..., true)` (SET LOCAL) und
-- Transaktions-Ende existiert der Custom-GUC auf der gepoolten Verbindung
-- session-seitig mit Leerstring ''. Alt-Policies (vor Migration 273) casten
-- current_setting(...) OHNE NULLIF-Guard direkt nach ::boolean/::uuid ->
-- ''::boolean crasht JEDE Folge-Query auf derselben Verbindung, bis der
-- Kontext neu gesetzt wird. Migration-273-Policies (z.B.
-- superuser_bypass_documents) haben den Guard bereits; dieses Skript zieht
-- alle Alt-Policies auf dasselbe Muster.
--
-- WIRKUNG: (NULLIF(current_setting('app.x'::text, true), ''::text))::TYP
-- -> bei fehlendem/leerem Kontext NULL -> Policy-Ausdruck NULL -> Zeile wird
-- verweigert (deny-by-default bleibt ERHALTEN, nur der Crash entfaellt).
--
-- AUSFUEHRUNG (idempotent, nur Policy-Ausdruecke, keine Datenaenderung):
--   docker exec -i ablage-postgres sh -c \
--     'PGPASSWORD="$POSTGRES_PASSWORD" psql -h 127.0.0.1 -U "$POSTGRES_USER" -d ablage_system' \
--     < scripts/db/repair_rls_guc_casts_20260712.sql
--
-- FOLLOWUP: In eine reguläre Alembic-Migration ueberfuehren (deferred-migration,
-- siehe docs/qa-reports/perception-2026-07/REPORT.md).

\echo '=== VORHER: Policies mit ungeguardeten app.-GUC-Casts ==='
SELECT c.relname AS tabelle, p.polname,
       pg_get_expr(p.polqual, p.polrelid) AS using_expr,
       pg_get_expr(p.polwithcheck, p.polrelid) AS check_expr
FROM pg_policy p JOIN pg_class c ON c.oid = p.polrelid
WHERE coalesce(pg_get_expr(p.polqual, p.polrelid),'') ~ '\(current_setting\(''app\.[a-z_]+''::text, true\)\)::(boolean|uuid)'
   OR coalesce(pg_get_expr(p.polwithcheck, p.polrelid),'') ~ '\(current_setting\(''app\.[a-z_]+''::text, true\)\)::(boolean|uuid)'
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
END $$;

\echo '=== NACHHER: verbleibende ungeguardete Casts (Erwartung: 0 Zeilen) ==='
SELECT c.relname AS tabelle, p.polname
FROM pg_policy p JOIN pg_class c ON c.oid = p.polrelid
WHERE coalesce(pg_get_expr(p.polqual, p.polrelid),'') ~ '\(current_setting\(''app\.[a-z_]+''::text, true\)\)::(boolean|uuid)'
   OR coalesce(pg_get_expr(p.polwithcheck, p.polrelid),'') ~ '\(current_setting\(''app\.[a-z_]+''::text, true\)\)::(boolean|uuid)';

\echo '=== CRASH-REPRO nach Fix als App-Rolle: ''-Zustand darf nicht mehr crashen (Erwartung: 0 sichtbare Zeilen, KEIN Fehler) ==='
-- Als ablage_app (RLS greift; Owner wuerde RLS umgehen). Leerstring-GUCs
-- simulieren den Zustand nach SET LOCAL + COMMIT auf gepoolter Verbindung.
SET ROLE ablage_app;
SELECT set_config('app.is_admin', '', false);
SELECT set_config('app.current_company_id', '', false);
SELECT set_config('app.current_user_id', '', false);
SELECT count(*) AS sichtbare_dokumente_ohne_kontext FROM documents;
SELECT count(*) AS sichtbare_memberships_ohne_kontext FROM user_companies;
RESET ROLE;
