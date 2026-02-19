"""Fix GoBD audit chain trigger conflict between migration 151 and 229.

Revision ID: 234
Revises: 233
Create Date: 2026-02-19

Migration 229 created a blanket immutability trigger (trg_gobd_audit_chain_immutable)
that blocks ALL updates, conflicting with migration 151's nuanced trigger
(trg_audit_chain_immutable) that allows verification field updates.

Fix:
1. Drop migration 229's blanket trigger
2. Replace migration 151's deny-list with allow-list (more secure)
"""
from alembic import op

revision = "234"
down_revision = "233"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Drop migration 229's blanket trigger and function
    op.execute("DROP TRIGGER IF EXISTS trg_gobd_audit_chain_immutable ON gobd_audit_chain;")
    op.execute("DROP FUNCTION IF EXISTS prevent_audit_chain_modification();")

    # 2. Replace migration 151's function with allow-list approach
    op.execute("""
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
    """)


def downgrade() -> None:
    # Restore migration 229's trigger and function
    op.execute("""
        CREATE OR REPLACE FUNCTION prevent_audit_chain_modification()
        RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'GoBD: Audit-Chain-Eintraege duerfen nicht geaendert oder geloescht werden';
        END;
        $$ LANGUAGE plpgsql;
    """)
    op.execute("""
        CREATE TRIGGER trg_gobd_audit_chain_immutable
        BEFORE UPDATE OR DELETE ON gobd_audit_chain
        FOR EACH ROW
        EXECUTE FUNCTION prevent_audit_chain_modification();
    """)

    # Restore migration 151's original deny-list function
    op.execute("""
        CREATE OR REPLACE FUNCTION prevent_audit_chain_mutation()
        RETURNS TRIGGER AS $$
        BEGIN
            IF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION 'gobd_audit_chain: DELETE nicht erlaubt';
            END IF;
            IF TG_OP = 'UPDATE' THEN
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
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)
