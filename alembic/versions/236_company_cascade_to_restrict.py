"""Change company foreign keys from CASCADE to RESTRICT for safety.

Revision ID: 236
Revises: 235
Create Date: 2026-02-19

Verhindert versehentliches Loeschen aller Mandanten-Daten via CASCADE.
Fuegt soft-delete Spalte zur companies-Tabelle hinzu.
"""
from alembic import op
import sqlalchemy as sa

revision = "236"
down_revision = "235"
branch_labels = None
depends_on = None


# Tabellen mit company_id FK und CASCADE - werden explizit behandelt
TABLES_WITH_COMPANY_FK = [
    "documents",
    "folders",
    "business_entities",
    "invoices",
    "domain_events",
    "gobd_audit_chain",
    "document_archives",
    "bank_accounts",
    "bank_transactions",
    "approval_chains",
    "approval_chain_templates",
    "contracts",
    "alerts",
    "workflows",
    "tags",
    "categories",
]


def upgrade() -> None:
    # Soft-delete Spalte zur companies-Tabelle hinzufuegen.
    # HINWEIS (Reconcile 2026-06): companies.deleted_at + ix_companies_deleted_at
    # werden bereits in Migration 057 (companies-CREATE, Zeile 90/98) angelegt.
    # Historisch ergaenzte DIESE Migration die Spalte; 057 wurde spaeter
    # angeglichen -> beide legen sie an. Idempotent absichern, damit from-scratch
    # (057 hat sie bereits) nicht mit "column already exists" bricht.
    op.execute(
        "ALTER TABLE companies ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_companies_deleted_at "
        "ON companies (deleted_at)"
    )

    # CASCADE zu RESTRICT aendern auf allen bekannten Tabellen.
    # HINWEIS (Reconcile 2026-06): Das frueher hier genutzte try/except um
    # op.drop_constraint funktioniert in PostgreSQL NICHT - ein fehlschlagendes
    # Statement bricht die GANZE Transaktion ab ("current transaction is
    # aborted"), das except kann nicht sauber fortsetzen. Stattdessen vorab
    # pruefen, ob ueberhaupt ein company_id-FK existiert (Name variiert:
    # fk_<t>_company_id ODER <t>_company_id_fkey), und nur dann idempotent
    # ersetzen. Tabellen ohne company_id-FK werden - wie zuvor beabsichtigt -
    # uebersprungen (kein company_id-Spalten-Zwang).
    bind = op.get_bind()
    for table_name in TABLES_WITH_COMPANY_FK:
        existing = bind.execute(
            sa.text(
                "SELECT con.conname FROM pg_constraint con "
                "JOIN pg_class rel ON rel.oid = con.conrelid "
                "WHERE rel.relname = :t AND con.contype = 'f' "
                "AND con.conname IN (:n1, :n2)"
            ),
            {
                "t": table_name,
                "n1": f"fk_{table_name}_company_id",
                "n2": f"{table_name}_company_id_fkey",
            },
        ).scalar()
        if not existing:
            continue
        op.execute(f'ALTER TABLE {table_name} DROP CONSTRAINT IF EXISTS "{existing}"')
        op.create_foreign_key(
            f"{table_name}_company_id_fkey",
            table_name,
            "companies",
            ["company_id"],
            ["id"],
            ondelete="RESTRICT",
        )


def downgrade() -> None:
    # RESTRICT zurueck zu CASCADE aendern (idempotent, ohne transaktions-
    # abbrechendes try/except - siehe upgrade).
    bind = op.get_bind()
    for table_name in TABLES_WITH_COMPANY_FK:
        existing = bind.execute(
            sa.text(
                "SELECT 1 FROM pg_constraint con "
                "JOIN pg_class rel ON rel.oid = con.conrelid "
                "WHERE rel.relname = :t AND con.contype = 'f' "
                "AND con.conname = :n"
            ),
            {"t": table_name, "n": f"{table_name}_company_id_fkey"},
        ).scalar()
        if not existing:
            continue
        op.execute(
            f'ALTER TABLE {table_name} DROP CONSTRAINT IF EXISTS "{table_name}_company_id_fkey"'
        )
        op.create_foreign_key(
            f"{table_name}_company_id_fkey",
            table_name,
            "companies",
            ["company_id"],
            ["id"],
            ondelete="CASCADE",
        )

    # deleted_at/Index gehoeren kanonisch zu Migration 057; idempotent droppen.
    op.execute("DROP INDEX IF EXISTS ix_companies_deleted_at")
    op.execute("ALTER TABLE companies DROP COLUMN IF EXISTS deleted_at")
