"""Seed default data

Revision ID: 003
Revises: 002
Create Date: 2025-11-26

This migration seeds the database with default tags and configuration.
Moved from infrastructure/postgres/init.sql to ensure proper execution order.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '003'
down_revision: Union[str, None] = '002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Insert default German document tags
    op.execute("""
        INSERT INTO tags (id, name, description, color, created_at) VALUES
            (gen_random_uuid(), 'Rechnung', 'Rechnungen und Quittungen', '#4CAF50', NOW()),
            (gen_random_uuid(), 'Vertrag', 'Verträge und Vereinbarungen', '#2196F3', NOW()),
            (gen_random_uuid(), 'Persönlich', 'Persönliche Dokumente', '#FF9800', NOW()),
            (gen_random_uuid(), 'Geschäftlich', 'Geschäftsdokumente', '#9C27B0', NOW()),
            (gen_random_uuid(), 'Steuer', 'Steuerrelevante Dokumente', '#F44336', NOW()),
            (gen_random_uuid(), 'Archiv', 'Archivierte Dokumente', '#607D8B', NOW()),
            (gen_random_uuid(), 'Brief', 'Briefe und Korrespondenz', '#00BCD4', NOW()),
            (gen_random_uuid(), 'Formular', 'Formulare und Anträge', '#795548', NOW())
        ON CONFLICT (name) DO NOTHING;
    """)


def downgrade() -> None:
    # Remove seeded tags
    op.execute("""
        DELETE FROM tags WHERE name IN (
            'Rechnung', 'Vertrag', 'Persönlich', 'Geschäftlich',
            'Steuer', 'Archiv', 'Brief', 'Formular'
        );
    """)
