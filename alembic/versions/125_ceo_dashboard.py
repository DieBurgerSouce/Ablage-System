# -*- coding: utf-8 -*-
"""Add CEO Dashboard company health snapshots

Revision ID: 125
Revises: 124
Create Date: 2026-01-28

Tabellen:
- company_health_snapshots: Tägliche Gesundheits-Snapshots pro Firma

Features:
- Multi-dimensionale Health Scores (Financial, Operations, Risk, Compliance)
- Historisches Tracking für Trend-Analysen
- Automatische Snapshot-Generierung via Celery
- Metrics-Daten in JSONB für Flexibilität

Feinpoliert und durchdacht - Deutsche Präzision.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '125'
down_revision = '124'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ==========================================================================
    # Company Health Snapshots - CEO Dashboard Datenbasis
    # ==========================================================================
    op.create_table(
        'company_health_snapshots',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),

        # Beziehungen
        sa.Column('company_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('companies.id', ondelete='CASCADE'),
                  nullable=False, index=True),

        # Snapshot-Metadaten
        sa.Column('snapshot_date', sa.Date, nullable=False,
                  comment='Datum des Snapshots (täglich)'),

        # Health Scores (0.0 - 100.0)
        sa.Column('health_score_overall', sa.Float, nullable=True,
                  comment='Gesamt-Score (gewichteter Durchschnitt)'),
        sa.Column('health_score_financial', sa.Float, nullable=True,
                  comment='Finanzielle Gesundheit (Cash Flow, Liquidität)'),
        sa.Column('health_score_operations', sa.Float, nullable=True,
                  comment='Operative Effizienz (Durchlaufzeiten, Fehlerrate)'),
        sa.Column('health_score_risk', sa.Float, nullable=True,
                  comment='Risiko-Score (inverse Skala: 100 = kein Risiko)'),
        sa.Column('health_score_compliance', sa.Float, nullable=True,
                  comment='Compliance-Score (GoBD, DSGVO)'),

        # Document Metrics
        sa.Column('documents_count', sa.Integer, nullable=False, server_default='0',
                  comment='Gesamtanzahl Dokumente'),
        sa.Column('invoices_pending', sa.Integer, nullable=False, server_default='0',
                  comment='Offene Rechnungen'),
        sa.Column('invoices_overdue', sa.Integer, nullable=False, server_default='0',
                  comment='Überfällige Rechnungen'),

        # Financial Metrics
        sa.Column('pending_amount', sa.Numeric(12, 2), nullable=False,
                  server_default='0',
                  comment='Summe offener Beträge'),
        sa.Column('overdue_amount', sa.Numeric(12, 2), nullable=False,
                  server_default='0',
                  comment='Summe überfälliger Beträge'),

        # Automation Metrics
        sa.Column('auto_process_rate', sa.Float, nullable=False, server_default='0',
                  comment='Automatisierungsgrad (0.0 - 1.0)'),

        # Alert Metrics
        sa.Column('active_alerts', sa.Integer, nullable=False, server_default='0',
                  comment='Aktive Alerts'),
        sa.Column('critical_alerts', sa.Integer, nullable=False, server_default='0',
                  comment='Kritische Alerts'),

        # Extended Metrics (JSONB)
        sa.Column('metrics_data', postgresql.JSONB, nullable=False,
                  server_default='{}',
                  comment='Erweiterte Metriken (z.B. OCR-Qualität, User-Aktivität)'),

        # Timestamps
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.func.now()),
    )

    # Unique constraint: Ein Snapshot pro Firma pro Tag
    op.create_index('ix_company_health_unique_snapshot',
                    'company_health_snapshots',
                    ['company_id', 'snapshot_date'],
                    unique=True)

    # Performance-Optimierung für Zeitreihen-Queries
    op.create_index('ix_company_health_company_id',
                    'company_health_snapshots',
                    ['company_id'])
    op.create_index('ix_company_health_date',
                    'company_health_snapshots',
                    ['snapshot_date'])

    # ==========================================================================
    # RLS Policy für Multi-Tenant Isolation
    # ==========================================================================

    op.execute("ALTER TABLE company_health_snapshots ENABLE ROW LEVEL SECURITY")

    op.execute("""
        CREATE POLICY company_health_company_isolation ON company_health_snapshots
        FOR ALL
        USING (company_id = current_setting('app.current_company_id', true)::uuid)
    """)


def downgrade() -> None:
    # Drop RLS policy
    op.execute("DROP POLICY IF EXISTS company_health_company_isolation ON company_health_snapshots")
    op.execute("ALTER TABLE company_health_snapshots DISABLE ROW LEVEL SECURITY")

    # Drop table
    op.drop_table('company_health_snapshots')
