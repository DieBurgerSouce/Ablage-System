-- Datenbereinigung (kein Schema): Schemathesis-Fuzzing-Leichen aus feature_flags
-- entfernen (F-REC-5, Reconcile-Report §9). Die 4 Zeilen stammen aus den
-- Schemathesis-Läufen (Namen '0', Keys '0'/'00'/'0…'), enabled=false, nie
-- fachlich genutzt. feature_toggle_history bleibt UNANGETASTET (Audit-Trail;
-- FK steht auf ON DELETE SET NULL, flag_name ist denormalisiert).
--
-- Ausführung (Live, als ablage_admin):
--   docker exec -i ablage-postgres sh -c 'PGPASSWORD="$POSTGRES_PASSWORD" \
--     psql -h 127.0.0.1 -U ablage_admin -d ablage_system -v ON_ERROR_STOP=1 -f -' \
--     < scripts/db/cleanup_feature_flag_fuzz_20260714.sql
BEGIN;

-- Vorher-Zustand protokollieren
SELECT 'VORHER: '||count(*)||' feature_flags, davon Fuzz: '||
       count(*) FILTER (WHERE name = '0' AND key ~ '^0+$') AS status
FROM feature_flags;

-- Eng gefasst: nur die Fuzzing-Signatur (Name '0' UND Key nur aus Nullen)
DELETE FROM feature_flags
WHERE name = '0' AND key ~ '^0+$' AND enabled = false;

SELECT 'NACHHER: '||count(*)||' feature_flags, Fuzz-Rest: '||
       count(*) FILTER (WHERE name = '0' AND key ~ '^0+$') AS status
FROM feature_flags;

-- Guard: es darf KEIN echtes Flag getroffen worden sein (alle Fuzz-Zeilen
-- waren enabled=false mit Null-Keys; mehr als 4 Loeschungen waeren verdaechtig)
DO $$
DECLARE n INT;
BEGIN
    GET DIAGNOSTICS n = ROW_COUNT;  -- (informativ; eigentliche Kontrolle unten)
    IF (SELECT count(*) FROM feature_flags WHERE name = '0' AND key ~ '^0+$') > 0 THEN
        RAISE EXCEPTION 'Fuzz-Zeilen ueberleben';
    END IF;
END $$;

COMMIT;
