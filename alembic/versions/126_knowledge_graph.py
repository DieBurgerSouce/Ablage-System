# -*- coding: utf-8 -*-
"""Add Knowledge Graph edges table

Revision ID: 126
Revises: 125
Create Date: 2026-01-28

Tabellen:
- graph_edges: Wissensgraph-Kanten für Entity-Beziehungen

Features:
- Polymorphe Beziehungen (Entity, Document, Invoice, BankAccount)
- Typisierte Kanten (ISSUED_TO, CONTAINS, PAID_VIA, etc.)
- Gewichtete Kanten für PageRank und Ähnlichkeitsmetriken
- Properties in JSONB für Flexibilität
- Multi-Tenant Isolation via RLS

Feinpoliert und durchdacht - Deutsche Präzision.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '126'
down_revision = '125'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ==========================================================================
    # Graph Edges - Wissensgraph-Kanten
    # ==========================================================================
    op.create_table(
        'graph_edges',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),

        # Multi-Tenant
        sa.Column('company_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('companies.id', ondelete='CASCADE'),
                  nullable=False, index=True),

        # Source Node (polymorphic)
        sa.Column('source_type', sa.String(50), nullable=False,
                  comment='Entity-Typ: entity, document, invoice, bank_account'),
        sa.Column('source_id', postgresql.UUID(as_uuid=True), nullable=False,
                  comment='UUID des Source-Objekts'),

        # Target Node (polymorphic)
        sa.Column('target_type', sa.String(50), nullable=False,
                  comment='Entity-Typ: entity, document, invoice, bank_account'),
        sa.Column('target_id', postgresql.UUID(as_uuid=True), nullable=False,
                  comment='UUID des Target-Objekts'),

        # Kanten-Typ und Eigenschaften
        sa.Column('edge_type', sa.String(50), nullable=False,
                  comment='ISSUED_TO, CONTAINS, PAID_VIA, BELONGS_TO, LINKED_TO'),
        sa.Column('properties', postgresql.JSONB, nullable=False,
                  server_default='{}',
                  comment='Kanten-Eigenschaften (z.B. confidence, created_by)'),
        sa.Column('weight', sa.Float, nullable=False, server_default='1.0',
                  comment='Gewichtung für Graph-Algorithmen (PageRank, etc.)'),

        # Timestamps
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.func.now()),
    )

    # ==========================================================================
    # Indexes für Graph-Traversierung
    # ==========================================================================

    # Source-basierte Queries (z.B. "Alle ausgehenden Kanten von Entity X")
    op.create_index('ix_graph_edges_source',
                    'graph_edges',
                    ['company_id', 'source_type', 'source_id'])

    # Target-basierte Queries (z.B. "Alle eingehenden Kanten zu Document Y")
    op.create_index('ix_graph_edges_target',
                    'graph_edges',
                    ['company_id', 'target_type', 'target_id'])

    # Edge-Type Filter (z.B. "Alle PAID_VIA Beziehungen")
    op.create_index('ix_graph_edges_type',
                    'graph_edges',
                    ['company_id', 'edge_type'])

    # Unique Constraint: Keine doppelten Kanten zwischen denselben Nodes
    op.create_index('ix_graph_edges_unique',
                    'graph_edges',
                    ['company_id', 'source_type', 'source_id',
                     'target_type', 'target_id', 'edge_type'],
                    unique=True)

    # ==========================================================================
    # RLS Policy für Multi-Tenant Isolation
    # ==========================================================================

    op.execute("ALTER TABLE graph_edges ENABLE ROW LEVEL SECURITY")

    op.execute("""
        CREATE POLICY graph_edges_company_isolation ON graph_edges
        FOR ALL
        USING (company_id = current_setting('app.current_company_id', true)::uuid)
    """)


def downgrade() -> None:
    # Drop RLS policy
    op.execute("DROP POLICY IF EXISTS graph_edges_company_isolation ON graph_edges")
    op.execute("ALTER TABLE graph_edges DISABLE ROW LEVEL SECURITY")

    # Drop table
    op.drop_table('graph_edges')
