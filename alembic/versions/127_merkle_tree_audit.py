# -*- coding: utf-8 -*-
"""Add Merkle Tree audit logging

Revision ID: 127
Revises: 126
Create Date: 2026-01-28

Tabellen:
- merkle_tree_nodes: Merkle Tree Knoten für Audit-Log-Integrität

Features:
- Kryptographische Audit-Log-Verifizierung via Merkle Tree
- Monatliche Wurzel-Hashes für GoBD-Compliance
- Effiziente Verifizierung einzelner Einträge (O(log n))
- Tree-basierte Struktur (Level 0 = Root)
- SHA-256 Hash-Werte für maximale Sicherheit

Feinpoliert und durchdacht - Deutsche Präzision.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '127'
down_revision = '126'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ==========================================================================
    # Merkle Tree Nodes - Kryptographische Audit-Integrität
    # ==========================================================================
    op.create_table(
        'merkle_tree_nodes',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),

        # Multi-Tenant
        sa.Column('company_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('companies.id', ondelete='CASCADE'),
                  nullable=False, index=True),

        # Tree Identification
        sa.Column('tree_id', sa.String(100), nullable=False,
                  comment='Tree-Identifier (z.B. "audit_2026_01" für Januar 2026)'),

        # Tree Structure
        sa.Column('level', sa.Integer, nullable=False,
                  comment='Baum-Ebene (0 = Root, höhere Werte = Blätter)'),
        sa.Column('position', sa.Integer, nullable=False,
                  comment='Position in der Ebene (0-based index)'),

        # Cryptographic Hashes (SHA-256)
        sa.Column('hash_value', sa.String(64), nullable=False,
                  comment='SHA-256 Hash dieses Knotens (hex-encoded)'),
        sa.Column('left_child_hash', sa.String(64), nullable=True,
                  comment='Hash des linken Kindknotens (null bei Blättern)'),
        sa.Column('right_child_hash', sa.String(64), nullable=True,
                  comment='Hash des rechten Kindknotens (null bei Blättern)'),

        # Metadata
        sa.Column('entry_count', sa.Integer, nullable=False, server_default='0',
                  comment='Anzahl Audit-Einträge in diesem Teilbaum'),

        # Timestamps
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.func.now()),
    )

    # ==========================================================================
    # Indexes für Tree-Navigation und Verifikation
    # ==========================================================================

    # Unique constraint: Ein Knoten pro Position im Tree
    op.create_index('ix_merkle_tree_id',
                    'merkle_tree_nodes',
                    ['company_id', 'tree_id', 'level', 'position'],
                    unique=True)

    # Root-Knoten-Lookup (für Verifikation)
    op.create_index('ix_merkle_root',
                    'merkle_tree_nodes',
                    ['company_id', 'tree_id'],
                    postgresql_where=sa.text('level = 0'))

    # ==========================================================================
    # RLS Policy für Multi-Tenant Isolation
    # ==========================================================================

    op.execute("ALTER TABLE merkle_tree_nodes ENABLE ROW LEVEL SECURITY")

    op.execute("""
        CREATE POLICY merkle_tree_company_isolation ON merkle_tree_nodes
        FOR ALL
        USING (company_id = current_setting('app.current_company_id', true)::uuid)
    """)


def downgrade() -> None:
    # Drop RLS policy
    op.execute("DROP POLICY IF EXISTS merkle_tree_company_isolation ON merkle_tree_nodes")
    op.execute("ALTER TABLE merkle_tree_nodes DISABLE ROW LEVEL SECURITY")

    # Drop table
    op.drop_table('merkle_tree_nodes')
