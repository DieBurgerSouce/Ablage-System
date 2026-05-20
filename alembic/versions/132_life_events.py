# -*- coding: utf-8 -*-
"""Add Life Events & Lifecycle Management tables

Revision ID: 132
Revises: 131
Create Date: 2026-01-28

Tabellen:
- life_events: Lebensereignisse und Lifecycle-Management

Features:
- Event Types: birth, marriage, divorce, home_purchase, job_change, retirement, etc.
- Auto-Detection aus Dokumenten (z.B. Geburtsurkunde, Arbeitsvertrag)
- Checklisten für Event-spezifische Aufgaben
- Finanzielle Impact-Analyse (Steuern, Versicherungen, Renten)
- Dokument-Verknüpfung für Nachweise
- Empfehlungen basierend auf Event-Typ
- Status-Tracking (detected, acknowledged, in_progress, completed)

Feinpoliert und durchdacht - Deutsche Präzision.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '132'
down_revision = '131'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ==========================================================================
    # Life Events - Lebensereignisse
    # ==========================================================================
    op.create_table(
        'life_events',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),

        # Verknüpfungen
        sa.Column('user_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('users.id', ondelete='CASCADE'),
                  nullable=False,
                  comment='Benutzer dem das Event zugeordnet ist'),
        sa.Column('company_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('companies.id', ondelete='CASCADE'),
                  nullable=False,
                  comment='Multi-Tenant Company'),

        # Event-Details
        sa.Column('event_type', sa.String(30), nullable=False,
                  comment='birth, marriage, divorce, home_purchase, job_change, '
                          'retirement, inheritance, etc.'),
        sa.Column('status', sa.String(20), nullable=False,
                  server_default='detected',
                  comment='detected, acknowledged, in_progress, completed, cancelled'),

        # Auto-Detection
        sa.Column('detection_source', sa.String(100), nullable=True,
                  comment='Quelle der Detection (z.B. document_classifier, user_input)'),
        sa.Column('detection_confidence', sa.Float, nullable=False,
                  server_default='0.0',
                  comment='Confidence-Score der Auto-Detection (0.0 - 1.0)'),

        # Textuelle Informationen
        sa.Column('title', sa.String(200), nullable=False,
                  comment='Event-Titel (z.B. "Hauskauf in München")'),
        sa.Column('description', sa.Text, nullable=True,
                  comment='Detaillierte Beschreibung'),

        # Event-Datum
        sa.Column('event_date', sa.Date, nullable=True,
                  comment='Datum des Ereignisses (falls bekannt)'),

        # Aufgaben und Empfehlungen
        sa.Column('checklist', postgresql.JSONB, nullable=False,
                  server_default='[]',
                  comment='Array von Checklist-Items: '
                          '[{task, completed, due_date, category}]'),
        sa.Column('recommendations', postgresql.JSONB, nullable=False,
                  server_default='[]',
                  comment='Array von Empfehlungen: '
                          '[{type, title, description, priority, action_url}]'),

        # Finanzielle Auswirkungen
        sa.Column('financial_impact', postgresql.JSONB, nullable=False,
                  server_default='{}',
                  comment='Finanzielle Auswirkungen: '
                          '{tax_implications, insurance_changes, pension_impact, etc.}'),

        # Dokument-Verknüpfungen
        sa.Column('related_document_ids', postgresql.JSONB, nullable=False,
                  server_default='[]',
                  comment='Array von Document-IDs die zu diesem Event gehören'),

        # Timestamps
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.func.now(),
                  comment='Zeitpunkt der Erstellung/Detection'),
        sa.Column('updated_at', sa.DateTime(timezone=True),
                  server_default=sa.func.now(),
                  onupdate=sa.func.now(),
                  comment='Zeitpunkt der letzten Aktualisierung'),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True,
                  comment='Zeitpunkt der Fertigstellung'),
    )

    # Performance-Indexes
    op.create_index(
        'ix_life_events_user_status',
        'life_events',
        ['user_id', 'status'],
        postgresql_using='btree'
    )
    op.create_index(
        'ix_life_events_company_created',
        'life_events',
        ['company_id', 'created_at'],
        postgresql_using='btree'
    )
    op.create_index(
        'ix_life_events_type',
        'life_events',
        ['company_id', 'event_type'],
        postgresql_using='btree'
    )

    # ==========================================================================
    # RLS Policies für Multi-Tenant Isolation
    # ==========================================================================

    op.execute("ALTER TABLE life_events ENABLE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY life_events_company_isolation
        ON life_events
        FOR ALL
        USING (company_id = current_setting('app.current_company_id', true)::uuid)
    """)


def downgrade() -> None:
    # Drop RLS policy
    op.execute("DROP POLICY IF EXISTS life_events_company_isolation ON life_events")

    # Disable RLS
    op.execute("ALTER TABLE life_events DISABLE ROW LEVEL SECURITY")

    # Drop table
    op.drop_table('life_events')
