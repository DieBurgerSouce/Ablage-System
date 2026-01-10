"""Add Lexware integration fields to BusinessEntity.

Revision ID: 089_add_lexware_fields
Revises: 088_add_privat_tasks
Create Date: 2026-01-10

Lexware Integration - Kunden/Lieferanten Import:
- lexware_ids: JSON mit Kundennummern/Matchcodes pro Firma
- company_presence: Liste der Firmen wo Entity existiert
- primary_customer_number: Hauptkundennummer fuer Anzeige
- primary_supplier_number: Hauptlieferantennummer fuer Anzeige
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers
revision = '089'
down_revision = '088'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ==================================================
    # BusinessEntity - Lexware Integration Fields
    # ==================================================

    # lexware_ids - Speichert Kundennummern und Matchcodes pro Firma
    # Format: {"folie": {"kd_nr": "12345", "matchcode": "MUELLER", "lief_nr": null}, ...}
    op.add_column(
        'business_entities',
        sa.Column(
            'lexware_ids',
            JSONB,
            nullable=True,
            server_default='{}',
            comment='Lexware IDs per company: {folie: {kd_nr, matchcode, lief_nr}, messer: {...}}'
        )
    )

    # company_presence - In welchen Firmen existiert die Entity
    # Format: ["folie", "messer"] oder ["folie"]
    op.add_column(
        'business_entities',
        sa.Column(
            'company_presence',
            JSONB,
            nullable=True,
            server_default='[]',
            comment='List of company short_names where entity exists'
        )
    )

    # primary_customer_number - Hauptkundennummer fuer Anzeige
    op.add_column(
        'business_entities',
        sa.Column(
            'primary_customer_number',
            sa.String(50),
            nullable=True,
            comment='Primary customer number for display (e.g., 12345)'
        )
    )

    # primary_supplier_number - Hauptlieferantennummer fuer Anzeige
    op.add_column(
        'business_entities',
        sa.Column(
            'primary_supplier_number',
            sa.String(50),
            nullable=True,
            comment='Primary supplier number for display'
        )
    )

    # ==================================================
    # Indexes fuer effiziente Suche
    # ==================================================

    # Index fuer Kundennummer-Suche
    op.create_index(
        'ix_business_entities_primary_customer_number',
        'business_entities',
        ['primary_customer_number']
    )

    # Index fuer Lieferantennummer-Suche
    op.create_index(
        'ix_business_entities_primary_supplier_number',
        'business_entities',
        ['primary_supplier_number']
    )

    # GIN Index fuer JSONB-Suche in lexware_ids
    op.execute("""
        CREATE INDEX ix_business_entities_lexware_ids_gin
        ON business_entities USING GIN (lexware_ids)
    """)

    # GIN Index fuer company_presence Array-Suche
    op.execute("""
        CREATE INDEX ix_business_entities_company_presence_gin
        ON business_entities USING GIN (company_presence)
    """)


def downgrade() -> None:
    # Drop indexes
    op.execute("DROP INDEX IF EXISTS ix_business_entities_company_presence_gin")
    op.execute("DROP INDEX IF EXISTS ix_business_entities_lexware_ids_gin")
    op.drop_index('ix_business_entities_primary_supplier_number', 'business_entities')
    op.drop_index('ix_business_entities_primary_customer_number', 'business_entities')

    # Drop columns
    op.drop_column('business_entities', 'primary_supplier_number')
    op.drop_column('business_entities', 'primary_customer_number')
    op.drop_column('business_entities', 'company_presence')
    op.drop_column('business_entities', 'lexware_ids')
