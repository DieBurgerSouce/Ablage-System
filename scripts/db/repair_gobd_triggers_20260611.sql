-- Repair: GoBD-Immutability-Trigger auf der Dev-DB nachziehen (2026-06-11).
--
-- Hintergrund: Die Dev-DB wurde per Stamp/Reconcile auf Revision 268 gebracht,
-- OHNE dass Migration 151_gobd_immutable (Trigger-DDL) je ausgefuehrt wurde.
-- Befund (psql): prevent_audit_chain_mutation/prevent_domain_event_mutation
-- fehlten, 0 Trigger auf domain_events/gobd_audit_chain -> GoBD-Luecke.
--
-- Dieses Skript stellt den kanonischen End-Zustand der Migrations-Kette her:
--   * Migration 151: prevent_domain_event_mutation + trg_domain_events_immutable
--   * Migration 234: Allow-List-Version von prevent_audit_chain_mutation
--   * Migration 151: trg_audit_chain_immutable (nutzt die 234er-Funktion)
-- Idempotent (CREATE OR REPLACE + DROP TRIGGER IF EXISTS).
--
-- Anwendung:
--   docker exec -i ablage-postgres psql -U ablage_admin -d ablage_system \
--     -v ON_ERROR_STOP=1 < scripts/db/repair_gobd_triggers_20260611.sql

BEGIN;

-- 1. domain_events: vollstaendig immutable (Migration 151)
CREATE OR REPLACE FUNCTION prevent_domain_event_mutation()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'domain_events ist APPEND-ONLY: % nicht erlaubt', TG_OP;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_domain_events_immutable ON domain_events;
CREATE TRIGGER trg_domain_events_immutable
BEFORE UPDATE OR DELETE ON domain_events
FOR EACH ROW EXECUTE FUNCTION prevent_domain_event_mutation();

-- 2. gobd_audit_chain: Allow-List-Funktion (Migration 234, ersetzt 151er Deny-List)
CREATE OR REPLACE FUNCTION prevent_audit_chain_mutation()
RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'gobd_audit_chain: DELETE nicht erlaubt (GoBD)';
    END IF;
    IF TG_OP = 'UPDATE' THEN
        -- Allow-List: NUR diese Verifikations-Felder duerfen sich aendern
        IF (NEW.is_verified IS DISTINCT FROM OLD.is_verified)
           OR (NEW.last_verified_at IS DISTINCT FROM OLD.last_verified_at)
           OR (NEW.verification_error IS DISTINCT FROM OLD.verification_error)
        THEN
            -- Sicherstellen dass KEINE anderen Felder geaendert wurden
            IF OLD.content_hash IS DISTINCT FROM NEW.content_hash
               OR OLD.combined_hash IS DISTINCT FROM NEW.combined_hash
               OR OLD.previous_hash IS DISTINCT FROM NEW.previous_hash
               OR OLD.event_type IS DISTINCT FROM NEW.event_type
               OR OLD.event_data::text IS DISTINCT FROM NEW.event_data::text
               OR OLD.sequence_number IS DISTINCT FROM NEW.sequence_number
               OR OLD.document_id IS DISTINCT FROM NEW.document_id
               OR OLD.company_id IS DISTINCT FROM NEW.company_id
               OR OLD.user_id IS DISTINCT FROM NEW.user_id
            THEN
                RAISE EXCEPTION
                    'gobd_audit_chain: Nur Verifikations-Felder (is_verified, last_verified_at, verification_error) duerfen aktualisiert werden';
            END IF;
            -- Nur Verifikationsfelder geaendert -> erlaubt
            RETURN NEW;
        ELSE
            -- Kein Verifikationsfeld geaendert -> jedes UPDATE blockieren
            RAISE EXCEPTION
                'gobd_audit_chain: UPDATE ohne Verifikationsfeld-Aenderung nicht erlaubt (GoBD)';
        END IF;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- 3. Trigger auf gobd_audit_chain (Migration 151; 229er Blanket-Trigger bleibt weg, vgl. 234)
DROP TRIGGER IF EXISTS trg_gobd_audit_chain_immutable ON gobd_audit_chain;
DROP FUNCTION IF EXISTS prevent_audit_chain_modification();
DROP TRIGGER IF EXISTS trg_audit_chain_immutable ON gobd_audit_chain;
CREATE TRIGGER trg_audit_chain_immutable
BEFORE UPDATE OR DELETE ON gobd_audit_chain
FOR EACH ROW EXECUTE FUNCTION prevent_audit_chain_mutation();

COMMIT;
