# -*- coding: utf-8 -*-
"""Add Event Sourcing tables

Revision ID: 129
Revises: 128
Create Date: 2026-01-28

Tabellen:
- domain_events: Event Store für Domain Events (Event Sourcing)
- event_snapshots: Performance-optimierte Snapshots von Aggregate States

Features:
- Complete Event Sourcing Support mit Aggregate-Typen
- Correlation-ID und Causation-ID für Event-Ketten
- Sequence Number für Ordering innerhalb Aggregates
- Snapshot-Support für schnelles Rebuild von Aggregates
- Optimistic Locking via Sequence Numbers
- Multi-Tenant Isolation via RLS

Feinpoliert und durchdacht - Deutsche Präzision.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '129'
down_revision = '128'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ==========================================================================
    # Domain Events - Event Store für Event Sourcing
    # ==========================================================================
    op.create_table(
        'domain_events',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),

        # Multi-Tenant
        sa.Column('company_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('companies.id', ondelete='CASCADE'),
                  nullable=False),

        # Aggregate Identifikation
        sa.Column('aggregate_type', sa.String(50), nullable=False,
                  comment='z.B. Document, Invoice, Entity, BankTransaction'),
        sa.Column('aggregate_id', postgresql.UUID(as_uuid=True), nullable=False,
                  comment='ID des Aggregates (z.B. Document.id)'),
        sa.Column('sequence_number', sa.BigInteger, nullable=False,
                  comment='Sequenznummer innerhalb des Aggregates (für Ordering)'),

        # Event-Metadaten
        sa.Column('event_type', sa.String(100), nullable=False,
                  comment='z.B. DocumentCreated, InvoiceApproved, EntityLinked'),
        sa.Column('event_data', postgresql.JSONB, nullable=False,
                  comment='Event-Payload (alle relevanten Daten)'),
        sa.Column('metadata', postgresql.JSONB, nullable=False,
                  server_default='{}',
                  comment='Zusätzliche Metadaten (IP, User-Agent, etc.)'),

        # Causality Tracking
        sa.Column('correlation_id', postgresql.UUID(as_uuid=True), nullable=True,
                  comment='Correlation-ID für Event-Ketten'),
        sa.Column('causation_id', postgresql.UUID(as_uuid=True), nullable=True,
                  comment='ID des auslösenden Events'),

        # Verantwortlichkeit
        sa.Column('user_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('users.id', ondelete='SET NULL'),
                  nullable=True,
                  comment='User der das Event ausgelöst hat (null = System)'),

        # Timestamp
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.func.now(),
                  comment='Zeitpunkt der Event-Erzeugung'),
    )

    # Unique Constraint: Ein Aggregate darf keine doppelten Sequence Numbers haben
    op.create_index(
        'uq_domain_events_aggregate_sequence',
        'domain_events',
        ['aggregate_type', 'aggregate_id', 'sequence_number'],
        unique=True,
        postgresql_using='btree'
    )

    # Performance-Indexes
    op.create_index(
        'ix_domain_events_aggregate',
        'domain_events',
        ['company_id', 'aggregate_type', 'aggregate_id', 'sequence_number'],
        postgresql_using='btree'
    )
    op.create_index(
        'ix_domain_events_type',
        'domain_events',
        ['company_id', 'event_type'],
        postgresql_using='btree'
    )
    op.create_index(
        'ix_domain_events_correlation',
        'domain_events',
        ['correlation_id'],
        postgresql_using='btree',
        postgresql_where=sa.text('correlation_id IS NOT NULL')
    )

    # ==========================================================================
    # Event Snapshots - Performance-optimierte Snapshots
    # ==========================================================================
    op.create_table(
        'event_snapshots',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),

        # Multi-Tenant
        sa.Column('company_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('companies.id', ondelete='CASCADE'),
                  nullable=False),

        # Aggregate Identifikation
        sa.Column('aggregate_type', sa.String(50), nullable=False,
                  comment='z.B. Document, Invoice, Entity'),
        sa.Column('aggregate_id', postgresql.UUID(as_uuid=True), nullable=False,
                  comment='ID des Aggregates'),
        sa.Column('sequence_number', sa.BigInteger, nullable=False,
                  comment='Sequenznummer bis zu der der Snapshot gültig ist'),

        # Snapshot-Daten
        sa.Column('state', postgresql.JSONB, nullable=False,
                  comment='Vollständiger State des Aggregates'),
        sa.Column('version', sa.Integer, nullable=False, server_default='1',
                  comment='Snapshot-Version (für Schema-Evolution)'),

        # Timestamp
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.func.now(),
                  comment='Zeitpunkt der Snapshot-Erzeugung'),
    )

    # Performance-Index für Snapshot-Queries
    op.create_index(
        'ix_event_snapshots_aggregate',
        'event_snapshots',
        ['company_id', 'aggregate_type', 'aggregate_id'],
        postgresql_using='btree'
    )

    # ==========================================================================
    # RLS Policies für Multi-Tenant Isolation
    # ==========================================================================

    # Domain Events
    op.execute("ALTER TABLE domain_events ENABLE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY domain_events_company_isolation ON domain_events
        FOR ALL
        USING (company_id = current_setting('app.current_company_id', true)::uuid)
    """)

    # Event Snapshots
    op.execute("ALTER TABLE event_snapshots ENABLE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY event_snapshots_company_isolation ON event_snapshots
        FOR ALL
        USING (company_id = current_setting('app.current_company_id', true)::uuid)
    """)


def downgrade() -> None:
    # Drop RLS policies
    op.execute("DROP POLICY IF EXISTS event_snapshots_company_isolation ON event_snapshots")
    op.execute("DROP POLICY IF EXISTS domain_events_company_isolation ON domain_events")

    # Disable RLS
    op.execute("ALTER TABLE event_snapshots DISABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE domain_events DISABLE ROW LEVEL SECURITY")

    # Drop tables
    op.drop_table('event_snapshots')
    op.drop_table('domain_events')
