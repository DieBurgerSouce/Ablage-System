"""Add DB-level immutability trigger for GoBD audit chain.

Revision ID: 229
Revises: 228
Create Date: 2026-02-15

Creates a PostgreSQL trigger on gobd_audit_chain that prevents UPDATE and DELETE
operations at the database level. This enforces the GoBD-required append-only
constraint beyond the application-level check in audit_chain_service.py.
"""
from alembic import op

revision = "229"
down_revision = "228"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create trigger function that blocks modifications
    op.execute("""
        CREATE OR REPLACE FUNCTION prevent_audit_chain_modification()
        RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'GoBD: Audit-Chain-Eintraege duerfen nicht geaendert oder geloescht werden';
        END;
        $$ LANGUAGE plpgsql;
    """)

    # Attach trigger to gobd_audit_chain table
    op.execute("""
        CREATE TRIGGER trg_gobd_audit_chain_immutable
        BEFORE UPDATE OR DELETE ON gobd_audit_chain
        FOR EACH ROW
        EXECUTE FUNCTION prevent_audit_chain_modification();
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_gobd_audit_chain_immutable ON gobd_audit_chain;")
    op.execute("DROP FUNCTION IF EXISTS prevent_audit_chain_modification();")
