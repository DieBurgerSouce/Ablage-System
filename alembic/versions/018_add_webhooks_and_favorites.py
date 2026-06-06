"""Add Webhooks and Favorites tables

Revision ID: 018
Revises: 017
Create Date: 2025-11-30

Backend Features:
- Webhook-Subscriptions für Event-Benachrichtigungen
- Webhook-Deliveries für Zustellungs-Tracking
- Document-Favorites für schnellen Dokumentzugriff
"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '018'
down_revision: Union[str, None] = '017'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Erstelle Webhook und Favoriten Tabellen.
    """
    # ==================== WEBHOOK SUBSCRIPTIONS ====================
    op.create_table(
        'webhook_subscriptions',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('url', sa.String(500), nullable=False),
        sa.Column('event_types', postgresql.JSON(), nullable=False),  # Liste der abonnierten Events
        sa.Column('secret', sa.String(100), nullable=False),  # HMAC Signing Secret
        sa.Column('is_active', sa.Boolean(), default=True, nullable=False),
        sa.Column('retry_count', sa.Integer(), default=3, nullable=False),
        sa.Column('timeout_seconds', sa.Integer(), default=30, nullable=False),
        sa.Column('last_triggered_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_success_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_failure_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('failure_count', sa.Integer(), default=0, nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
    )

    # Indexes für webhook_subscriptions
    op.create_index(
        'ix_webhook_subscriptions_user_id',
        'webhook_subscriptions',
        ['user_id']
    )
    op.create_index(
        'ix_webhook_subscriptions_is_active',
        'webhook_subscriptions',
        ['is_active']
    )

    # ==================== WEBHOOK SUBSCRIPTION DELIVERIES ====================
    # HINWEIS (Reconcile 2026-06): Tabelle hiess frueher `webhook_deliveries`,
    # heisst im ORM-Modell aber `webhook_subscription_deliveries`
    # (models_auth_access.py) - die NEUE Event-Platform (Migration 249) belegt den
    # Namen `webhook_deliveries` endpoint-basiert. Ohne diese Umbenennung kollidiert
    # 249 from-scratch ("relation webhook_deliveries already exists"). Hier an das
    # Modell angeglichen (subscription-basiertes Zustellprotokoll).
    op.create_table(
        'webhook_subscription_deliveries',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('subscription_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('webhook_subscriptions.id', ondelete='CASCADE'), nullable=False),
        sa.Column('event_type', sa.String(50), nullable=False),
        sa.Column('event_id', sa.String(50), nullable=False),  # Unique Event ID
        sa.Column('payload', postgresql.JSON(), nullable=False),
        sa.Column('status', sa.String(20), default='pending', nullable=False),  # pending, success, failed
        sa.Column('attempt_count', sa.Integer(), default=0, nullable=False),
        sa.Column('http_status_code', sa.Integer(), nullable=True),
        sa.Column('response_body', sa.Text(), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('duration_ms', sa.Integer(), nullable=True),
        sa.Column('next_retry_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('delivered_at', sa.DateTime(timezone=True), nullable=True),
    )

    # Indexes für webhook_deliveries
    op.create_index(
        'ix_webhook_sub_deliveries_subscription_id',
        'webhook_subscription_deliveries',
        ['subscription_id']
    )
    op.create_index(
        'ix_webhook_sub_deliveries_status',
        'webhook_subscription_deliveries',
        ['status']
    )
    op.create_index(
        'ix_webhook_sub_deliveries_event_id',
        'webhook_subscription_deliveries',
        ['event_id'],
        unique=True
    )
    op.create_index(
        'ix_webhook_sub_deliveries_next_retry_at',
        'webhook_subscription_deliveries',
        ['next_retry_at'],
        postgresql_where=sa.text("status = 'pending' AND next_retry_at IS NOT NULL")
    )

    # ==================== DOCUMENT FAVORITES ====================
    op.create_table(
        'document_favorites',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('document_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('documents.id', ondelete='CASCADE'), nullable=False),
        sa.Column('note', sa.Text(), nullable=True),  # Optionale Notiz
        sa.Column('priority', sa.Integer(), default=0, nullable=False),  # Sortierpriorität
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # Unique-Constraint: Ein Benutzer kann ein Dokument nur einmal favorisieren
    op.create_unique_constraint(
        'uq_document_favorites_user_document',
        'document_favorites',
        ['user_id', 'document_id']
    )

    # Indexes für document_favorites
    op.create_index(
        'ix_document_favorites_user_id',
        'document_favorites',
        ['user_id']
    )
    op.create_index(
        'ix_document_favorites_document_id',
        'document_favorites',
        ['document_id']
    )
    op.create_index(
        'ix_document_favorites_priority',
        'document_favorites',
        ['user_id', 'priority', 'created_at']
    )


def downgrade() -> None:
    """
    Entferne Webhook und Favoriten Tabellen.
    """
    # Document Favorites
    op.drop_index('ix_document_favorites_priority', table_name='document_favorites')
    op.drop_index('ix_document_favorites_document_id', table_name='document_favorites')
    op.drop_index('ix_document_favorites_user_id', table_name='document_favorites')
    op.drop_constraint('uq_document_favorites_user_document', 'document_favorites', type_='unique')
    op.drop_table('document_favorites')

    # Webhook Deliveries
    op.drop_index('ix_webhook_sub_deliveries_next_retry_at', table_name='webhook_subscription_deliveries')
    op.drop_index('ix_webhook_sub_deliveries_event_id', table_name='webhook_subscription_deliveries')
    op.drop_index('ix_webhook_sub_deliveries_status', table_name='webhook_subscription_deliveries')
    op.drop_index('ix_webhook_sub_deliveries_subscription_id', table_name='webhook_subscription_deliveries')
    op.drop_table('webhook_subscription_deliveries')

    # Webhook Subscriptions
    op.drop_index('ix_webhook_subscriptions_is_active', table_name='webhook_subscriptions')
    op.drop_index('ix_webhook_subscriptions_user_id', table_name='webhook_subscriptions')
    op.drop_table('webhook_subscriptions')
