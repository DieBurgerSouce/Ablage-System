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
    # Soft-delete Spalte zur companies-Tabelle hinzufuegen
    op.add_column(
        "companies",
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_companies_deleted_at", "companies", ["deleted_at"])

    # CASCADE zu RESTRICT aendern auf allen bekannten Tabellen
    for table_name in TABLES_WITH_COMPANY_FK:
        constraint_name = f"fk_{table_name}_company_id"
        try:
            op.drop_constraint(constraint_name, table_name, type_="foreignkey")
        except Exception:
            # Constraint-Name kann abweichen - PostgreSQL-Standard-Muster versuchen
            try:
                op.drop_constraint(
                    f"{table_name}_company_id_fkey", table_name, type_="foreignkey"
                )
            except Exception:
                # Constraint existiert nicht oder hat anderen Namen - ueberspringen
                continue

        op.create_foreign_key(
            f"{table_name}_company_id_fkey",
            table_name,
            "companies",
            ["company_id"],
            ["id"],
            ondelete="RESTRICT",
        )


def downgrade() -> None:
    # RESTRICT zurueck zu CASCADE aendern
    for table_name in TABLES_WITH_COMPANY_FK:
        try:
            op.drop_constraint(
                f"{table_name}_company_id_fkey", table_name, type_="foreignkey"
            )
        except Exception:
            continue

        op.create_foreign_key(
            f"{table_name}_company_id_fkey",
            table_name,
            "companies",
            ["company_id"],
            ["id"],
            ondelete="CASCADE",
        )

    op.drop_index("ix_companies_deleted_at", "companies")
    op.drop_column("companies", "deleted_at")
