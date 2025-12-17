# -*- coding: utf-8 -*-
"""
Upgrade DATEV indexes to partial indexes for better performance.

Revision ID: 048_add_datev_indexes
Revises: 047_add_datev_support
Create Date: 2025-12-17

Migration 047 erstellt bereits Standard-Indexes. Diese Migration:
1. Ersetzt Standard-Indexes durch Partial Indexes (nur NOT NULL Werte)
2. Fuegt neuen Composite Index fuer config_id + vendor_name hinzu

Partial Indexes sind kleiner und schneller weil NULL-Werte ausgeschlossen sind.
"""

from alembic import op


# revision identifiers, used by Alembic.
revision = '048_add_datev_indexes'
down_revision = '047_add_datev_support'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Upgrade DATEV vendor mapping indexes to partial indexes."""
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    # Nur fuer PostgreSQL: Standard-Indexes durch Partial Indexes ersetzen
    # Fuer andere Dialekte (SQLite) bleiben die Standard-Indexes erhalten
    if is_postgres:
        # 1. Alte Standard-Indexes aus Migration 047 droppen
        op.drop_index('ix_datev_vendor_mappings_vendor_vat_id', table_name='datev_vendor_mappings')
        op.drop_index('ix_datev_vendor_mappings_vendor_iban', table_name='datev_vendor_mappings')
        op.drop_index('ix_datev_vendor_mappings_business_entity_id', table_name='datev_vendor_mappings')

        # 2. Als Partial Indexes neu erstellen (Performance-Optimierung)
        op.create_index(
            'ix_datev_vendor_mappings_vendor_vat_id',
            'datev_vendor_mappings',
            ['vendor_vat_id'],
            unique=False,
            postgresql_where="vendor_vat_id IS NOT NULL"
        )

        op.create_index(
            'ix_datev_vendor_mappings_vendor_iban',
            'datev_vendor_mappings',
            ['vendor_iban'],
            unique=False,
            postgresql_where="vendor_iban IS NOT NULL"
        )

        op.create_index(
            'ix_datev_vendor_mappings_business_entity_id',
            'datev_vendor_mappings',
            ['business_entity_id'],
            unique=False,
            postgresql_where="business_entity_id IS NOT NULL"
        )

    # 3. Neuer Composite Index (fuer alle Dialekte)
    op.create_index(
        'ix_datev_vendor_mappings_config_vendor_name',
        'datev_vendor_mappings',
        ['config_id', 'vendor_name'],
        unique=False
    )


def downgrade() -> None:
    """Restore original indexes from Migration 047."""
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    # Composite Index droppen (alle Dialekte)
    op.drop_index('ix_datev_vendor_mappings_config_vendor_name', table_name='datev_vendor_mappings')

    if is_postgres:
        # Partial Indexes droppen
        op.drop_index('ix_datev_vendor_mappings_business_entity_id', table_name='datev_vendor_mappings')
        op.drop_index('ix_datev_vendor_mappings_vendor_iban', table_name='datev_vendor_mappings')
        op.drop_index('ix_datev_vendor_mappings_vendor_vat_id', table_name='datev_vendor_mappings')

        # Standard-Indexes (wie in Migration 047) wiederherstellen
        op.create_index('ix_datev_vendor_mappings_vendor_vat_id', 'datev_vendor_mappings', ['vendor_vat_id'])
        op.create_index('ix_datev_vendor_mappings_vendor_iban', 'datev_vendor_mappings', ['vendor_iban'])
        op.create_index('ix_datev_vendor_mappings_business_entity_id', 'datev_vendor_mappings',
                        ['business_entity_id'])
