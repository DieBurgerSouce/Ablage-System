"""Add structured extraction support.

Erweitert Document-Modell fuer strukturierte Datenextraktion:
- Neuer Index auf extracted_data JSONB (GIN)
- Index auf document_type fuer schnelle Filterung
- Neue Dokumenttypen: ORDER, DELIVERY_NOTE

Revision ID: 032_structured_extraction
Revises: 031_add_tunes
Create Date: 2025-01-15

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers
revision = "032_structured_extraction"
down_revision = "031_add_tunes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """
    Upgrade: Strukturierte Extraktion aktivieren.

    Aenderungen:
    1. GIN-Index auf extracted_data JSONB fuer schnelle Suche
    2. Index auf document_type fuer Filterung nach Dokumenttyp
    3. Composite-Index fuer Kombinations-Abfragen
    """
    # 1. GIN-Index auf extracted_data fuer JSONB-Operationen
    # Ermoeglicht schnelle Suche nach z.B. Rechnungsnummer, IBAN, etc.
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_documents_extracted_data_gin
        ON documents USING GIN (extracted_data jsonb_path_ops)
    """)

    # 2. Index auf document_type (falls noch nicht existiert)
    # Ermoeglicht schnelle Filterung nach Dokumenttyp
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_documents_document_type
        ON documents (document_type)
        WHERE document_type IS NOT NULL
    """)

    # 3. Composite-Index fuer haeufige Abfragen: Typ + Datum
    # Note: deleted_at Spalte existiert nicht, daher Index ohne WHERE-Filter
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_documents_type_created
        ON documents (document_type, created_at DESC)
        WHERE document_type IS NOT NULL
    """)

    # 4. Index fuer Suche nach Rechnungsnummer in extracted_data
    # Ermoeglicht: WHERE extracted_data->>'invoice'->>'invoice_number' = 'RE-2024-001'
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_documents_invoice_number
        ON documents ((extracted_data->'invoice'->>'invoice_number'))
        WHERE extracted_data->'invoice'->>'invoice_number' IS NOT NULL
    """)

    # 5. Index fuer Suche nach IBANs in extracted_data
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_documents_ibans
        ON documents USING GIN ((extracted_data->'ibans'))
        WHERE extracted_data->'ibans' IS NOT NULL
    """)

    # 6. Index fuer Klassifizierungskonfidenz
    # Note: CAST statt :: Syntax fuer asyncpg Kompatibilitaet
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_documents_classification_confidence
        ON documents (
            CAST(extracted_data->'classification'->>'confidence' AS FLOAT)
        )
        WHERE extracted_data->'classification'->>'confidence' IS NOT NULL
    """)


def downgrade() -> None:
    """Downgrade: Indizes entfernen."""
    op.execute("DROP INDEX IF EXISTS ix_documents_classification_confidence")
    op.execute("DROP INDEX IF EXISTS ix_documents_ibans")
    op.execute("DROP INDEX IF EXISTS ix_documents_invoice_number")
    op.execute("DROP INDEX IF EXISTS ix_documents_type_created")
    op.execute("DROP INDEX IF EXISTS ix_documents_document_type")
    op.execute("DROP INDEX IF EXISTS ix_documents_extracted_data_gin")
