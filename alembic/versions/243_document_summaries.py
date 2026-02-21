"""Dokumenten-Zusammenfassungen Spalten.

Revision ID: 243
Revises: 242
Create Date: 2026-02-21

Fuegt Spalten fuer KI-generierte Zusammenfassungen hinzu:
- summary: Zusammenfassung (3-5 Saetze)
- keywords: Extrahierte Schluesselwoerter (JSONB)
- one_liner: Einzeilige Beschreibung
- summary_generated_at: Zeitpunkt der Generierung
- summary_model: Verwendetes LLM-Modell

Phase 2.2: Auto-Zusammenfassungen nach OCR-Verarbeitung.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "243"
down_revision = "242"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Zusammenfassung (3-5 Saetze)
    op.add_column(
        "documents",
        sa.Column(
            "summary",
            sa.Text(),
            nullable=True,
            comment="KI-generierte Zusammenfassung (3-5 Saetze)",
        ),
    )

    # Schluesselwoerter als JSONB-Array
    op.add_column(
        "documents",
        sa.Column(
            "keywords",
            postgresql.JSONB(),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
            comment="Extrahierte Schluesselwoerter",
        ),
    )

    # Einzeilige Beschreibung
    op.add_column(
        "documents",
        sa.Column(
            "one_liner",
            sa.String(500),
            nullable=True,
            comment="Einzeilige Beschreibung",
        ),
    )

    # Zeitpunkt der Summary-Generierung
    op.add_column(
        "documents",
        sa.Column(
            "summary_generated_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )

    # Verwendetes LLM-Modell
    op.add_column(
        "documents",
        sa.Column(
            "summary_model",
            sa.String(100),
            nullable=True,
            comment="LLM-Modell fuer Zusammenfassung",
        ),
    )

    # Partial Index: nur Dokumente mit vorhandener Summary
    op.create_index(
        "ix_documents_summary_generated",
        "documents",
        ["company_id", "summary_generated_at"],
        postgresql_where=sa.text("summary IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_documents_summary_generated", table_name="documents")
    op.drop_column("documents", "summary_model")
    op.drop_column("documents", "summary_generated_at")
    op.drop_column("documents", "one_liner")
    op.drop_column("documents", "keywords")
    op.drop_column("documents", "summary")
