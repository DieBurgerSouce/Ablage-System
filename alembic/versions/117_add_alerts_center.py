# -*- coding: utf-8 -*-
"""add_alerts_center

Revision ID: 117_alerts_center
Revises: 116_add_saved_filters
Create Date: 2026-01-24

Adds Alert Center tables for centralized alert management:
- alerts: Main alert storage with categories, severity, status
- alert_rules: Auto-alert generation rules
- alert_digest_subscriptions: Email digest configuration per user
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '117_alerts_center'
down_revision = '116_add_saved_filters'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create alerts table
    op.create_table(
        'alerts',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('alert_code', sa.String(50), nullable=False),
        sa.Column('title', sa.String(255), nullable=False),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column('category', sa.String(30), nullable=False, server_default='system'),
        sa.Column('severity', sa.String(20), nullable=False, server_default='medium'),
        sa.Column('status', sa.String(20), nullable=False, server_default='new'),
        sa.Column('source_type', sa.String(50), nullable=True),
        sa.Column('source_id', sa.String(100), nullable=True),
        sa.Column('document_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('entity_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('company_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('assigned_to_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('alert_metadata', postgresql.JSONB(astext_type=sa.Text()), server_default='{}'),
        sa.Column('context', postgresql.JSONB(astext_type=sa.Text()), server_default='{}'),
        sa.Column('available_actions', postgresql.JSONB(astext_type=sa.Text()), server_default='[]'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('acknowledged_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('acknowledged_by_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('resolved_by_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('resolution_note', sa.Text(), nullable=True),
        sa.Column('resolution_action', sa.String(100), nullable=True),
        sa.Column('auto_dismiss_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('is_recurring', sa.Boolean(), server_default='false'),
        sa.Column('recurrence_key', sa.String(255), nullable=True),
        sa.Column('email_sent', sa.Boolean(), server_default='false'),
        sa.Column('email_sent_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('escalation_level', sa.Integer(), server_default='0'),
        sa.Column('escalated_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('escalated_to_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['company_id'], ['companies.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['document_id'], ['documents.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['entity_id'], ['business_entities.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['assigned_to_id'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['acknowledged_by_id'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['resolved_by_id'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['escalated_to_id'], ['users.id'], ondelete='SET NULL'),
        sa.CheckConstraint(
            "severity IN ('info', 'low', 'medium', 'high', 'critical')",
            name='ck_alerts_severity'
        ),
        sa.CheckConstraint(
            "status IN ('new', 'acknowledged', 'in_progress', 'resolved', 'dismissed', 'escalated')",
            name='ck_alerts_status'
        ),
        sa.CheckConstraint(
            "category IN ('fraud', 'risk', 'compliance', 'deadline', 'system', 'security', 'quality', 'workflow')",
            name='ck_alerts_category'
        ),
    )

    # Create indexes for alerts
    op.create_index('ix_alerts_alert_code', 'alerts', ['alert_code'])
    op.create_index('ix_alerts_category', 'alerts', ['category'])
    op.create_index('ix_alerts_severity', 'alerts', ['severity'])
    op.create_index('ix_alerts_status', 'alerts', ['status'])
    op.create_index('ix_alerts_document_id', 'alerts', ['document_id'])
    op.create_index('ix_alerts_entity_id', 'alerts', ['entity_id'])
    op.create_index('ix_alerts_company_id', 'alerts', ['company_id'])
    op.create_index('ix_alerts_assigned_to_id', 'alerts', ['assigned_to_id'])
    op.create_index('ix_alerts_created_at', 'alerts', ['created_at'])
    op.create_index('ix_alerts_recurrence_key', 'alerts', ['recurrence_key'])
    op.create_index('ix_alerts_company_status', 'alerts', ['company_id', 'status'])
    op.create_index('ix_alerts_company_category', 'alerts', ['company_id', 'category'])
    op.create_index('ix_alerts_company_severity', 'alerts', ['company_id', 'severity'])

    # Create alert_rules table
    op.create_table(
        'alert_rules',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('category', sa.String(30), nullable=False),
        sa.Column('severity', sa.String(20), nullable=False),
        sa.Column('alert_code', sa.String(50), nullable=False),
        sa.Column('conditions', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default='{}'),
        sa.Column('actions', postgresql.JSONB(astext_type=sa.Text()), server_default='[]'),
        sa.Column('cooldown_minutes', sa.Integer(), server_default='60'),
        sa.Column('max_alerts_per_day', sa.Integer(), nullable=True),
        sa.Column('company_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('is_active', sa.Boolean(), server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('created_by_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['company_id'], ['companies.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], ondelete='SET NULL'),
    )

    # Create indexes for alert_rules
    op.create_index('ix_alert_rules_company_id', 'alert_rules', ['company_id'])
    op.create_index('ix_alert_rules_company_active', 'alert_rules', ['company_id', 'is_active'])

    # Create alert_digest_subscriptions table
    op.create_table(
        'alert_digest_subscriptions',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('frequency', sa.String(20), server_default='daily'),
        sa.Column('categories', postgresql.JSONB(astext_type=sa.Text()), server_default='[]'),
        sa.Column('min_severity', sa.String(20), server_default='medium'),
        sa.Column('digest_hour', sa.Integer(), server_default='8'),
        sa.Column('digest_day', sa.Integer(), nullable=True),
        sa.Column('is_active', sa.Boolean(), server_default='true'),
        sa.Column('last_sent_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    )

    # Create indexes for alert_digest_subscriptions
    op.create_index('ix_alert_digest_user_id', 'alert_digest_subscriptions', ['user_id'])
    op.create_index('ix_alert_digest_user_active', 'alert_digest_subscriptions', ['user_id', 'is_active'])


def downgrade() -> None:
    # Drop alert_digest_subscriptions
    op.drop_index('ix_alert_digest_user_active', table_name='alert_digest_subscriptions')
    op.drop_index('ix_alert_digest_user_id', table_name='alert_digest_subscriptions')
    op.drop_table('alert_digest_subscriptions')

    # Drop alert_rules
    op.drop_index('ix_alert_rules_company_active', table_name='alert_rules')
    op.drop_index('ix_alert_rules_company_id', table_name='alert_rules')
    op.drop_table('alert_rules')

    # Drop alerts
    op.drop_index('ix_alerts_company_severity', table_name='alerts')
    op.drop_index('ix_alerts_company_category', table_name='alerts')
    op.drop_index('ix_alerts_company_status', table_name='alerts')
    op.drop_index('ix_alerts_recurrence_key', table_name='alerts')
    op.drop_index('ix_alerts_created_at', table_name='alerts')
    op.drop_index('ix_alerts_assigned_to_id', table_name='alerts')
    op.drop_index('ix_alerts_company_id', table_name='alerts')
    op.drop_index('ix_alerts_entity_id', table_name='alerts')
    op.drop_index('ix_alerts_document_id', table_name='alerts')
    op.drop_index('ix_alerts_status', table_name='alerts')
    op.drop_index('ix_alerts_severity', table_name='alerts')
    op.drop_index('ix_alerts_category', table_name='alerts')
    op.drop_index('ix_alerts_alert_code', table_name='alerts')
    op.drop_table('alerts')
