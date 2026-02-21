"""Optimistic Locking: row_version Spalte fuer Konflikterkennung.

Revision ID: 240
Revises: 239
Create Date: 2026-02-20

Fuegt row_version (Integer, NOT NULL, default=1) zu folgenden Tabellen hinzu:
- documents
- business_entities
- invoice_tracking
- companies

Bestehende Zeilen werden mit row_version=1 initialisiert (server_default).
Bei jedem UPDATE wird row_version inkrementiert. Bei Konflikt gibt die API
HTTP 409 zurueck.

HINWEIS: documents hat bereits current_version_number/total_versions fuer
Content-Versionierung. row_version ist separat fuer Optimistic Locking.
"""
from alembic import op
import sqlalchemy as sa

revision = "240"
down_revision = "239"
branch_labels = None
depends_on = None

# Tabellen die Optimistic Locking erhalten
_TABLES = ["documents", "business_entities", "invoice_tracking", "companies"]


def upgrade() -> None:
    for table in _TABLES:
        # Spalte hinzufuegen mit server_default fuer bestehende Zeilen
        op.add_column(
            table,
            sa.Column(
                "row_version",
                sa.Integer(),
                nullable=False,
                server_default=sa.text("1"),
                comment="Optimistic Locking: Wird bei jedem UPDATE inkrementiert",
            ),
        )

        # Index fuer WHERE-Clause bei optimistic locking UPDATE
        op.create_index(
            f"ix_{table}_row_version",
            table,
            ["row_version"],
        )


def downgrade() -> None:
    for table in reversed(_TABLES):
        op.drop_index(f"ix_{table}_row_version", table_name=table)
        op.drop_column(table, "row_version")
