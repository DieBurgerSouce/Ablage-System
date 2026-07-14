-- Repair: Legacy-/Invalid-Statuswerte in documents.status (Perception-Audit 2026-07-12, F-P2-006)
--
-- Kontext: documents.status ist varchar (Enum-Abbildung nur ORM-seitig,
-- Richtungsentscheidung varchar<->Enum weiter offen). Ein per SQL geseedetes
-- Test-Artefakt (rls_test.pdf, 2026-07-10) trug status='uploaded' — kein
-- gültiger ProcessingStatus-Wert. Folge: JEDE Dokumentliste der betroffenen
-- Firma crashte beim ORM-Load mit ValueError -> HTTP 500 (durch F-P2-001
-- firmenweite Sicht erstmals für alle Nutzer der Firma sichtbar geworden).
--
-- Mapping: unbekannte/legacy Werte -> 'pending' (hochgeladen, Verarbeitung
-- ausstehend — konservativste Interpretation; ein erneuter OCR-Anstoß ist
-- unschädlich). Idempotent: wiederholte Ausführung ändert nichts mehr.
--
-- Anwendung (Dev-Stack):
--   docker exec ablage-postgres sh -c 'PGPASSWORD="$POSTGRES_PASSWORD" \
--     psql -h 127.0.0.1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
--     -f /dev/stdin' < scripts/db/repair_legacy_document_status_20260712.sql

BEGIN;

-- Vorher-Bild protokollieren
DO $$
DECLARE
    anzahl integer;
BEGIN
    SELECT COUNT(*) INTO anzahl
    FROM documents
    WHERE status NOT IN ('pending', 'queued', 'processing', 'completed', 'failed', 'cancelled');
    RAISE NOTICE 'documents mit invalidem status vor Repair: %', anzahl;
END $$;

UPDATE documents
SET status = 'pending',
    updated_at = NOW()
WHERE status NOT IN ('pending', 'queued', 'processing', 'completed', 'failed', 'cancelled');

-- Nachher-Verifikation: es darf kein invalider Wert übrig sein
DO $$
DECLARE
    anzahl integer;
BEGIN
    SELECT COUNT(*) INTO anzahl
    FROM documents
    WHERE status NOT IN ('pending', 'queued', 'processing', 'completed', 'failed', 'cancelled');
    IF anzahl > 0 THEN
        RAISE EXCEPTION 'Repair unvollständig: % invalide status-Werte übrig', anzahl;
    END IF;
    RAISE NOTICE 'Repair ok: 0 invalide status-Werte übrig';
END $$;

COMMIT;
