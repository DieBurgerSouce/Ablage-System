-- =============================================================================
-- RLS light (Neuausrichtung Phase 7): App-DB-Rolle "ablage_app" ohne
-- Superuser/BYPASSRLS - damit greifen die vorhandenen RLS-Policies
-- (~92 Policies auf app.current_company_id, Migrationen 210/211/271;
-- FORCE ROW LEVEL SECURITY u. a. auf documents, invoices, approval_requests,
-- document_versions, slack_channels).
--
-- HINTERGRUND: Der heutige App-User (POSTGRES_USER=ablage_admin) ist der
-- Postgres-Superuser des Containers und umgeht RLS vollstaendig. Diese Rolle
-- ist der opt-in-Wechsel auf "App ohne RLS-Bypass" OHNE 269-Tabellen-Vollausbau
-- (6-10 vertrauenswuerdige Buero-User; Privat-Suite ist zusaetzlich zweifach
-- app-seitig geschuetzt: PrivatSpace-ACL + AES-256-GCM).
--
-- AUSFUEHRUNG (als Superuser, Passwort via psql-Variable - NIE inline tippen):
--   docker exec -i -e PGPASSWORD="$DB_PASSWORD" ablage-postgres \
--     psql -U ablage_admin -d ablage_system \
--          -v app_password="$POSTGRES_APP_PASSWORD" \
--          -v owner_role="ablage_admin" \
--          -f - < scripts/db/create_app_role.sql
--
-- AKTIVIERUNG danach (bewusste .env-Entscheidung, siehe .env.example):
--   1. .env: POSTGRES_APP_USER=ablage_app + POSTGRES_APP_PASSWORD=<Passwort>
--   2. docker compose up -d backend worker worker-cpu beat
--      (die DATABASE_URLs in docker-compose.yml sind auf
--       ${POSTGRES_APP_USER:-${POSTGRES_USER:-ablage_admin}} parametrisiert;
--       ohne .env-Eintrag laeuft weiterhin der heutige Superuser - nichts bricht)
--   3. Alembic-Migrationen laufen weiterhin als Superuser (docker/entrypoint
--      nutzt DATABASE_URL des Containers - nach Umstellung Migrationen einmalig
--      pruefen; neue Tabellen erhalten Rechte via ALTER DEFAULT PRIVILEGES unten,
--      solange :owner_role sie anlegt).
--
-- VERIFIKATION (Plan par.8 DoD 8 - "App-Rolle ohne Company-Kontext liest 0 Zeilen"):
--   SET ROLE ablage_app;
--   SELECT count(*) FROM documents;          -- erwartet: 0 Zeilen sichtbar
--   SELECT count(*) FROM invoices;           -- erwartet: 0
--   SELECT count(*) FROM approval_requests;  -- erwartet: 0
--   -- (Policies USING company_id = NULLIF(current_setting('app.current_company_id',
--   --  true), '')::uuid ergeben ohne gesetzten Kontext NULL => keine Zeile passiert.)
--   -- Gegenprobe MIT Kontext (eine echte Company-UUID einsetzen):
--   SET app.current_company_id = '<company-uuid>';
--   SELECT count(*) FROM documents;          -- erwartet: > 0 (Company-Bestand)
--   RESET ROLE;
--
-- HINWEIS psql-Trockenlauf: Docker-Engine war bei Erstellung defekt - das
-- Skript ist syntaktisch sorgfaeltig gebaut (idempotent via \gexec + ALTER),
-- aber noch nicht gegen ein laufendes Postgres ausgefuehrt. Vor der echten
-- Aktivierung einmal gegen die Dev-DB laufen lassen.
-- =============================================================================

\set ON_ERROR_STOP on

-- Default fuer :owner_role, falls nicht per -v uebergeben (Rolle, die die
-- Tabellen besitzt und kuenftige Migrationen ausfuehrt).
\if :{?owner_role}
\else
\set owner_role 'ablage_admin'
\endif

\if :{?app_password}
\else
\echo 'FEHLER: psql-Variable app_password fehlt. Aufruf mit -v app_password="$POSTGRES_APP_PASSWORD" (siehe Kopfkommentar).'
\quit 2
\endif

-- 1) Rolle idempotent anlegen (CREATE nur wenn nicht vorhanden), dann ALTER,
--    damit ein Re-Run Passwort/Attribute deterministisch setzt.
SELECT format(
    'CREATE ROLE ablage_app LOGIN PASSWORD %L NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS NOREPLICATION',
    :'app_password'
)
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ablage_app')
\gexec

ALTER ROLE ablage_app WITH LOGIN PASSWORD :'app_password'
    NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS NOREPLICATION;

COMMENT ON ROLE ablage_app IS
    'Ablage-System App-Rolle ohne RLS-Bypass (RLS light, Neuausrichtung Phase 7). Aktivierung via .env POSTGRES_APP_USER/POSTGRES_APP_PASSWORD.';

-- 2) Verbindungs- und Schema-Rechte (DB-Name dynamisch = aktuelle Datenbank,
--    damit das Skript auch gegen abweichende POSTGRES_DB-Namen laeuft)
SELECT format('GRANT CONNECT ON DATABASE %I TO ablage_app', current_database())
\gexec
GRANT USAGE ON SCHEMA public TO ablage_app;

-- 3) DML auf alle bestehenden Tabellen + Sequenzen (kein DDL, kein TRUNCATE)
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO ablage_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO ablage_app;

-- 4) Zukuenftige Objekte: Migrationen laufen als :owner_role (heute
--    ablage_admin) - deren Neuanlagen sollen automatisch nutzbar sein.
ALTER DEFAULT PRIVILEGES FOR ROLE :"owner_role" IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO ablage_app;
ALTER DEFAULT PRIVILEGES FOR ROLE :"owner_role" IN SCHEMA public
    GRANT USAGE, SELECT ON SEQUENCES TO ablage_app;

-- 5) Sichtbarkeit fuer den Betrieb: kurze Bestandsaufnahme ausgeben
\echo 'Rolle ablage_app angelegt/aktualisiert. RLS-Kontrollwerte:'
SELECT rolname, rolsuper AS superuser, rolbypassrls AS bypassrls
FROM pg_roles WHERE rolname IN ('ablage_app', :'owner_role');

SELECT count(*) AS rls_policies_gesamt FROM pg_policies WHERE schemaname = 'public';

SELECT relname AS force_rls_tabelle
FROM pg_class
WHERE relrowsecurity AND relforcerowsecurity AND relnamespace = 'public'::regnamespace
ORDER BY relname;
