# -*- coding: utf-8 -*-
"""Add Process Events table for Process Mining.

Vision 2.0 Feature: Process Mining & Autonome Automatisierung
Erstellt Tabellen fuer:
- process_events: Ereignisse im Dokumenten-Lebenszyklus
- automation_suggestions: Automatisierungsvorschlaege
- process_metrics: Aggregierte Prozess-Metriken

Revision ID: 142_add_process_events
Revises: 141_add_contracts
Create Date: 2026-01-29

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '142_add_process_events'
down_revision: Union[str, None] = '141_add_contracts'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create process mining tables."""

    # ============================================================
    # 1. process_events - Ereignisse im Dokumenten-Lebenszyklus
    # ============================================================
    op.create_table(
        'process_events',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('document_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('entity_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('event_type', sa.String(50), nullable=False),
        sa.Column('event_subtype', sa.String(50), nullable=True),
        sa.Column('actor_type', sa.String(20), nullable=False, server_default='system'),
        sa.Column('actor_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('timestamp', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('duration_ms', sa.Integer(), nullable=True),
        sa.Column('previous_event_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('time_since_previous_ms', sa.Integer(), nullable=True),
        sa.Column('process_instance_id', sa.String(100), nullable=True),
        sa.Column('activity_name', sa.String(100), nullable=True),
        sa.Column('resource', sa.String(100), nullable=True),
        sa.Column('success', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=True, server_default='{}'),
        sa.Column('company_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(['document_id'], ['documents.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['entity_id'], ['business_entities.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['actor_id'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['previous_event_id'], ['process_events.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['company_id'], ['companies.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )

    # Process events indexes
    op.create_index('ix_process_events_document_id', 'process_events', ['document_id'])
    op.create_index('ix_process_events_entity_id', 'process_events', ['entity_id'])
    op.create_index('ix_process_events_event_type', 'process_events', ['event_type'])
    op.create_index('ix_process_events_actor_type', 'process_events', ['actor_type'])
    op.create_index('ix_process_events_timestamp', 'process_events', ['timestamp'])
    op.create_index('ix_process_events_company_id', 'process_events', ['company_id'])
    op.create_index('ix_process_events_process_instance', 'process_events', ['process_instance_id'])
    op.create_index('ix_process_events_activity', 'process_events', ['activity_name'])
    op.create_index('ix_process_events_company_timestamp', 'process_events', ['company_id', 'timestamp'])

    # ============================================================
    # 2. automation_suggestions - Automatisierungsvorschlaege
    # ============================================================
    op.create_table(
        'automation_suggestions',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('suggestion_type', sa.String(50), nullable=False),
        sa.Column('title', sa.String(255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('pattern_description', sa.Text(), nullable=True),
        sa.Column('confidence', sa.Numeric(5, 4), nullable=False),
        sa.Column('potential_savings_hours', sa.Numeric(10, 2), nullable=True),
        sa.Column('potential_savings_cost', sa.Numeric(15, 2), nullable=True),
        sa.Column('affected_steps', postgresql.JSONB(astext_type=sa.Text()), nullable=True, server_default='[]'),
        sa.Column('trigger_conditions', postgresql.JSONB(astext_type=sa.Text()), nullable=True, server_default='{}'),
        sa.Column('suggested_actions', postgresql.JSONB(astext_type=sa.Text()), nullable=True, server_default='[]'),
        sa.Column('sample_documents', postgresql.JSONB(astext_type=sa.Text()), nullable=True, server_default='[]'),
        sa.Column('frequency_per_week', sa.Integer(), nullable=True),
        sa.Column('status', sa.String(30), nullable=False, server_default='pending'),
        sa.Column('activated_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('activated_by_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('rejected_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('rejected_by_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('rejection_reason', sa.Text(), nullable=True),
        sa.Column('automation_rule_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('company_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['activated_by_id'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['rejected_by_id'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['company_id'], ['companies.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )

    # Automation suggestions indexes
    op.create_index('ix_automation_suggestions_type', 'automation_suggestions', ['suggestion_type'])
    op.create_index('ix_automation_suggestions_status', 'automation_suggestions', ['status'])
    op.create_index('ix_automation_suggestions_company', 'automation_suggestions', ['company_id'])
    op.create_index('ix_automation_suggestions_confidence', 'automation_suggestions', ['confidence'])

    # ============================================================
    # 3. process_metrics - Aggregierte Prozess-Metriken (taeglich)
    # ============================================================
    op.create_table(
        'process_metrics',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('metric_date', sa.Date(), nullable=False),
        sa.Column('metric_type', sa.String(50), nullable=False),
        sa.Column('process_name', sa.String(100), nullable=True),
        sa.Column('activity_name', sa.String(100), nullable=True),
        sa.Column('event_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('success_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('failure_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('avg_duration_ms', sa.Integer(), nullable=True),
        sa.Column('min_duration_ms', sa.Integer(), nullable=True),
        sa.Column('max_duration_ms', sa.Integer(), nullable=True),
        sa.Column('p50_duration_ms', sa.Integer(), nullable=True),
        sa.Column('p95_duration_ms', sa.Integer(), nullable=True),
        sa.Column('manual_action_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('automated_action_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('bottleneck_score', sa.Numeric(5, 4), nullable=True),
        sa.Column('metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=True, server_default='{}'),
        sa.Column('company_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['company_id'], ['companies.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('company_id', 'metric_date', 'metric_type', 'process_name', 'activity_name',
                           name='uq_process_metrics'),
    )

    # Process metrics indexes
    op.create_index('ix_process_metrics_date', 'process_metrics', ['metric_date'])
    op.create_index('ix_process_metrics_type', 'process_metrics', ['metric_type'])
    op.create_index('ix_process_metrics_company', 'process_metrics', ['company_id'])
    op.create_index('ix_process_metrics_company_date', 'process_metrics', ['company_id', 'metric_date'])


def downgrade() -> None:
    """Drop process mining tables."""

    op.drop_index('ix_process_metrics_company_date', table_name='process_metrics')
    op.drop_index('ix_process_metrics_company', table_name='process_metrics')
    op.drop_index('ix_process_metrics_type', table_name='process_metrics')
    op.drop_index('ix_process_metrics_date', table_name='process_metrics')
    op.drop_table('process_metrics')

    op.drop_index('ix_automation_suggestions_confidence', table_name='automation_suggestions')
    op.drop_index('ix_automation_suggestions_company', table_name='automation_suggestions')
    op.drop_index('ix_automation_suggestions_status', table_name='automation_suggestions')
    op.drop_index('ix_automation_suggestions_type', table_name='automation_suggestions')
    op.drop_table('automation_suggestions')

    op.drop_index('ix_process_events_company_timestamp', table_name='process_events')
    op.drop_index('ix_process_events_activity', table_name='process_events')
    op.drop_index('ix_process_events_process_instance', table_name='process_events')
    op.drop_index('ix_process_events_company_id', table_name='process_events')
    op.drop_index('ix_process_events_timestamp', table_name='process_events')
    op.drop_index('ix_process_events_actor_type', table_name='process_events')
    op.drop_index('ix_process_events_event_type', table_name='process_events')
    op.drop_index('ix_process_events_entity_id', table_name='process_events')
    op.drop_index('ix_process_events_document_id', table_name='process_events')
    op.drop_table('process_events')
