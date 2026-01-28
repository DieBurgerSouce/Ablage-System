# -*- coding: utf-8 -*-
"""Add External Data Enrichment tables

Revision ID: 130
Revises: 129
Create Date: 2026-01-28

Tabellen:
- external_enrichment_results: Ergebnisse von externen Datenquellen

Features:
- Integration mit Handelsregister, Creditreform, etc.
- Caching von externen API-Calls (TTL-basiert)
- Confidence-Scores für Enrichment-Daten
- Error-Tracking bei API-Fehlern
- Multi-Source Support (verschiedene Provider)
- Status-Tracking (pending, completed, failed, cached)

Feinpoliert und durchdacht - Deutsche Präzision.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '130'
down_revision = '129'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ==========================================================================
    # External Enrichment Results - Externe Datenquellen
    # ==========================================================================
    op.create_table(
        'external_enrichment_results',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),

        # Multi-Tenant
        sa.Column('company_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('companies.id', ondelete='CASCADE'),
                  nullable=False),

        # Entity-Verknüpfung
        sa.Column('entity_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('business_entities.id', ondelete='CASCADE'),
                  nullable=False,
                  comment='Verknüpfter Geschäftspartner'),

        # Datenquelle
        sa.Column('source', sa.String(100), nullable=False,
                  comment='z.B. handelsregister, creditreform, schufa, northdata'),
        sa.Column('source_url', sa.String(500), nullable=True,
                  comment='URL zur Datenquelle (falls vorhanden)'),

        # Daten
        sa.Column('raw_data', postgresql.JSONB, nullable=False,
                  server_default='{}',
                  comment='Raw API Response (für Debugging/Audit)'),
        sa.Column('enriched_data', postgresql.JSONB, nullable=False,
                  server_default='{}',
                  comment='Extrahierte und normalisierte Daten'),

        # Status und Qualität
        sa.Column('status', sa.String(20), nullable=False,
                  server_default='completed',
                  comment='pending, completed, failed, cached'),
        sa.Column('confidence', sa.Float, nullable=False,
                  server_default='0.0',
                  comment='Confidence-Score (0.0 - 1.0)'),
        sa.Column('error_message', sa.Text, nullable=True,
                  comment='Fehlermeldung bei failed Status'),

        # Caching
        sa.Column('cached_until', sa.DateTime(timezone=True), nullable=True,
                  comment='Ablaufdatum des Cache (TTL)'),

        # Timestamps
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.func.now(),
                  comment='Zeitpunkt der Anfrage'),
        sa.Column('updated_at', sa.DateTime(timezone=True),
                  server_default=sa.func.now(),
                  onupdate=sa.func.now(),
                  comment='Zeitpunkt der letzten Aktualisierung'),
    )

    # Performance-Indexes
    op.create_index(
        'ix_enrichment_entity_source',
        'external_enrichment_results',
        ['entity_id', 'source'],
        postgresql_using='btree'
    )
    op.create_index(
        'ix_enrichment_company_created',
        'external_enrichment_results',
        ['company_id', 'created_at'],
        postgresql_using='btree'
    )

    # ==========================================================================
    # RLS Policies für Multi-Tenant Isolation
    # ==========================================================================

    op.execute("ALTER TABLE external_enrichment_results ENABLE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY external_enrichment_results_company_isolation
        ON external_enrichment_results
        FOR ALL
        USING (company_id = current_setting('app.current_company_id', true)::uuid)
    """)


def downgrade() -> None:
    # Drop RLS policy
    op.execute(
        "DROP POLICY IF EXISTS external_enrichment_results_company_isolation "
        "ON external_enrichment_results"
    )

    # Disable RLS
    op.execute("ALTER TABLE external_enrichment_results DISABLE ROW LEVEL SECURITY")

    # Drop table
    op.drop_table('external_enrichment_results')
