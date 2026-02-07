"""Add inventory management tables

Revision ID: 118_add_inventory_management
Revises: 117_alerts_center
Create Date: 2026-01-24

Tabellen:
- warehouses: Lager/Lagerorte
- inventory_items: Artikel-Stammdaten
- stock_levels: Aktuelle Bestaende pro Artikel/Lager
- inventory_movements: Historische Warenbewegungen
- goods_receipts: Wareneingaenge aus Lieferscheinen
- goods_receipt_lines: Zeilen im Wareneingang
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '118_add_inventory_management'
down_revision = '117_alerts_center'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Warehouses (Lager)
    op.create_table(
        'warehouses',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('company_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('companies.id', ondelete='CASCADE'), nullable=False),
        sa.Column('code', sa.String(20), nullable=False),
        sa.Column('name', sa.String(200), nullable=False),
        sa.Column('description', sa.Text, nullable=True),
        sa.Column('address_line1', sa.String(200), nullable=True),
        sa.Column('address_line2', sa.String(200), nullable=True),
        sa.Column('postal_code', sa.String(20), nullable=True),
        sa.Column('city', sa.String(100), nullable=True),
        sa.Column('country', sa.String(2), server_default='DE'),
        sa.Column('is_active', sa.Boolean, server_default='true'),
        sa.Column('is_default', sa.Boolean, server_default='false'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.UniqueConstraint('company_id', 'code', name='uq_warehouse_company_code'),
    )
    op.create_index('ix_warehouse_company_active', 'warehouses', ['company_id', 'is_active'])

    # Inventory Items (Artikel)
    op.create_table(
        'inventory_items',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('company_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('companies.id', ondelete='CASCADE'), nullable=False),
        sa.Column('item_number', sa.String(50), nullable=False),
        sa.Column('ean', sa.String(13), nullable=True),
        sa.Column('manufacturer_part_number', sa.String(50), nullable=True),
        sa.Column('name', sa.String(200), nullable=False),
        sa.Column('description', sa.Text, nullable=True),
        sa.Column('category', sa.String(100), nullable=True),
        sa.Column('unit', sa.String(20), server_default='Stueck'),
        sa.Column('purchase_price', sa.Numeric(12, 2), nullable=True),
        sa.Column('sales_price', sa.Numeric(12, 2), nullable=True),
        sa.Column('currency', sa.String(3), server_default='EUR'),
        sa.Column('min_stock_level', sa.Numeric(12, 3), nullable=True),
        sa.Column('reorder_point', sa.Numeric(12, 3), nullable=True),
        sa.Column('reorder_quantity', sa.Numeric(12, 3), nullable=True),
        sa.Column('default_supplier_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('business_entities.id'), nullable=True),
        sa.Column('is_active', sa.Boolean, server_default='true'),
        sa.Column('attributes', postgresql.JSONB, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.UniqueConstraint('company_id', 'item_number', name='uq_item_company_number'),
    )
    op.create_index('ix_item_company_active', 'inventory_items', ['company_id', 'is_active'])
    op.create_index('ix_item_ean', 'inventory_items', ['ean'])
    op.create_index('ix_item_category', 'inventory_items', ['company_id', 'category'])

    # Stock Levels (Bestaende)
    op.create_table(
        'stock_levels',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('company_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('companies.id', ondelete='CASCADE'), nullable=False),
        sa.Column('item_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('inventory_items.id', ondelete='CASCADE'), nullable=False),
        sa.Column('warehouse_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('warehouses.id', ondelete='CASCADE'), nullable=False),
        sa.Column('quantity_on_hand', sa.Numeric(12, 3), server_default='0'),
        sa.Column('quantity_reserved', sa.Numeric(12, 3), server_default='0'),
        sa.Column('quantity_on_order', sa.Numeric(12, 3), server_default='0'),
        sa.Column('last_count_date', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_count_quantity', sa.Numeric(12, 3), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.UniqueConstraint('item_id', 'warehouse_id', name='uq_stock_item_warehouse'),
        sa.CheckConstraint('quantity_on_hand >= 0', name='ck_stock_quantity_positive'),
    )
    op.create_index('ix_stock_company', 'stock_levels', ['company_id'])
    op.create_index('ix_stock_warehouse', 'stock_levels', ['warehouse_id'])

    # Movement Type Enum
    movement_type_enum = postgresql.ENUM(
        'goods_receipt', 'goods_issue', 'transfer',
        'adjustment_plus', 'adjustment_minus',
        'return_inbound', 'return_outbound', 'scrapping',
        name='movement_type',
        create_type=False,
    )
    movement_type_enum.create(op.get_bind(), checkfirst=True)

    # Movement Status Enum
    movement_status_enum = postgresql.ENUM(
        'pending', 'confirmed', 'cancelled',
        name='movement_status',
        create_type=False,
    )
    movement_status_enum.create(op.get_bind(), checkfirst=True)

    # Inventory Movements (Warenbewegungen)
    op.create_table(
        'inventory_movements',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('company_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('companies.id', ondelete='CASCADE'), nullable=False),
        sa.Column('item_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('inventory_items.id', ondelete='CASCADE'), nullable=False),
        sa.Column('warehouse_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('warehouses.id', ondelete='CASCADE'), nullable=False),
        sa.Column('target_warehouse_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('warehouses.id'), nullable=True),
        sa.Column('movement_type', movement_type_enum, nullable=False),
        sa.Column('status', movement_status_enum, server_default='confirmed'),
        sa.Column('quantity', sa.Numeric(12, 3), nullable=False),
        sa.Column('unit_price', sa.Numeric(12, 2), nullable=True),
        sa.Column('total_value', sa.Numeric(12, 2), nullable=True),
        sa.Column('currency', sa.String(3), server_default='EUR'),
        sa.Column('document_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('documents.id'), nullable=True),
        sa.Column('reference_number', sa.String(100), nullable=True),
        sa.Column('entity_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('business_entities.id'), nullable=True),
        sa.Column('notes', sa.Text, nullable=True),
        sa.Column('created_by', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('movement_date', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('ix_movement_company_date', 'inventory_movements', ['company_id', 'movement_date'])
    op.create_index('ix_movement_item', 'inventory_movements', ['item_id'])
    op.create_index('ix_movement_document', 'inventory_movements', ['document_id'])
    op.create_index('ix_movement_type', 'inventory_movements', ['movement_type'])

    # Goods Receipts (Wareneingaenge)
    op.create_table(
        'goods_receipts',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('company_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('companies.id', ondelete='CASCADE'), nullable=False),
        sa.Column('delivery_note_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('documents.id', ondelete='CASCADE'), nullable=False),
        sa.Column('warehouse_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('warehouses.id'), nullable=False),
        sa.Column('supplier_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('business_entities.id'), nullable=True),
        sa.Column('delivery_note_number', sa.String(100), nullable=True),
        sa.Column('purchase_order_number', sa.String(100), nullable=True),
        sa.Column('receipt_date', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('is_processed', sa.Boolean, server_default='false'),
        sa.Column('processed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('notes', sa.Text, nullable=True),
        sa.Column('created_by', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.UniqueConstraint('delivery_note_id', name='uq_goods_receipt_delivery_note'),
    )
    op.create_index('ix_goods_receipt_company', 'goods_receipts', ['company_id'])
    op.create_index('ix_goods_receipt_supplier', 'goods_receipts', ['supplier_id'])
    op.create_index('ix_goods_receipt_date', 'goods_receipts', ['receipt_date'])

    # Goods Receipt Lines (Wareneingangszeilen)
    op.create_table(
        'goods_receipt_lines',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('goods_receipt_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('goods_receipts.id', ondelete='CASCADE'), nullable=False),
        sa.Column('item_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('inventory_items.id'), nullable=True),
        sa.Column('line_number', sa.Integer, nullable=False),
        sa.Column('item_number_extracted', sa.String(50), nullable=True),
        sa.Column('description', sa.String(500), nullable=True),
        sa.Column('quantity_expected', sa.Numeric(12, 3), nullable=True),
        sa.Column('quantity_received', sa.Numeric(12, 3), nullable=False),
        sa.Column('unit', sa.String(20), server_default='Stueck'),
        sa.Column('movement_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('inventory_movements.id'), nullable=True),
        sa.Column('is_matched', sa.Boolean, server_default='false'),
        sa.Column('match_confidence', sa.Numeric(5, 2), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint('goods_receipt_id', 'line_number', name='uq_receipt_line_number'),
    )
    op.create_index('ix_goods_receipt_line_item', 'goods_receipt_lines', ['item_id'])


def downgrade() -> None:
    # Drop tables in reverse order
    op.drop_table('goods_receipt_lines')
    op.drop_table('goods_receipts')
    op.drop_table('inventory_movements')
    op.drop_table('stock_levels')
    op.drop_table('inventory_items')
    op.drop_table('warehouses')

    # Drop enums
    op.execute('DROP TYPE IF EXISTS movement_status')
    op.execute('DROP TYPE IF EXISTS movement_type')
