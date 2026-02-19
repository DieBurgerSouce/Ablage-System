"""Add INSERT-only triggers for GoBD compliance tables.

Revision ID: 151_gobd_immutable
Revises: 150_workflow_sla
Create Date: 2026-02-19

GoBD-Compliance: domain_events und gobd_audit_chain muessen
APPEND-ONLY sein. UPDATE und DELETE werden per Trigger verhindert.

Ausnahme fuer gobd_audit_chain: Verifikations-Felder (is_verified,
last_verified_at, verification_error) duerfen aktualisiert werden.
"""

from alembic import op

revision = '151_gobd_immutable'
down_revision = '150_workflow_sla'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Erstellt INSERT-only Triggers fuer GoBD-Tabellen."""

    # =========================================================================
    # 1. domain_events: Vollstaendig immutable (kein UPDATE, kein DELETE)
    # =========================================================================
    op.execute("""
        CREATE OR REPLACE FUNCTION prevent_domain_event_mutation()
        RETURNS TRIGGER AS $$
        BEGIN
            RAISE EXCEPTION 'domain_events ist APPEND-ONLY: % nicht erlaubt', TG_OP;
        END;
        $$ LANGUAGE plpgsql;
    """)

    op.execute("""
        CREATE TRIGGER trg_domain_events_immutable
        BEFORE UPDATE OR DELETE ON domain_events
        FOR EACH ROW EXECUTE FUNCTION prevent_domain_event_mutation();
    """)

    # =========================================================================
    # 2. gobd_audit_chain: Immutable mit Ausnahme fuer Verifikations-Felder
    # =========================================================================
    op.execute("""
        CREATE OR REPLACE FUNCTION prevent_audit_chain_mutation()
        RETURNS TRIGGER AS $$
        BEGIN
            IF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION 'gobd_audit_chain: DELETE nicht erlaubt';
            END IF;
            IF TG_OP = 'UPDATE' THEN
                -- Nur Verifikations-Felder duerfen aktualisiert werden
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

    op.execute("""
        CREATE TRIGGER trg_audit_chain_immutable
        BEFORE UPDATE OR DELETE ON gobd_audit_chain
        FOR EACH ROW EXECUTE FUNCTION prevent_audit_chain_mutation();
    """)


def downgrade() -> None:
    """Entfernt INSERT-only Triggers."""
    op.execute("DROP TRIGGER IF EXISTS trg_audit_chain_immutable ON gobd_audit_chain;")
    op.execute("DROP FUNCTION IF EXISTS prevent_audit_chain_mutation();")
    op.execute("DROP TRIGGER IF EXISTS trg_domain_events_immutable ON domain_events;")
    op.execute("DROP FUNCTION IF EXISTS prevent_domain_event_mutation();")
