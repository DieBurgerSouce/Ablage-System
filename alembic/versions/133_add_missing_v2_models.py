"""Add missing Vision 2.0 models.

Revision ID: 133_add_missing_v2_models
Revises: 132_life_events
Create Date: 2026-01-28

Adds:
- DocumentEntityLink: Verknuepfung Document <-> BusinessEntity
- RiskScoreHistory: Historische Risk-Scores fuer Explainability
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

# revision identifiers, used by Alembic
revision = '133_add_missing_v2_models'
down_revision = '132'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add DocumentEntityLink and RiskScoreHistory tables."""

    # 1. DocumentEntityLink - Verknuepfung Document <-> Entity
    op.create_table(
        'document_entity_links',
        sa.Column('id', UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), primary_key=True),
        sa.Column('document_id', UUID(as_uuid=True), sa.ForeignKey('documents.id', ondelete='CASCADE'), nullable=False),
        sa.Column('entity_id', UUID(as_uuid=True), sa.ForeignKey('business_entities.id', ondelete='CASCADE'), nullable=False),
        sa.Column('company_id', UUID(as_uuid=True), sa.ForeignKey('companies.id', ondelete='CASCADE'), nullable=False),
        sa.Column('link_type', sa.String(50), nullable=True),  # invoice_sender, mentioned, etc.
        sa.Column('confidence', sa.Float, default=1.0),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('created_by_id', UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('metadata', JSONB, default=dict),
    )

    # Indexes for DocumentEntityLink
    op.create_index('ix_doc_entity_links_document_id', 'document_entity_links', ['document_id'])
    op.create_index('ix_doc_entity_links_entity_id', 'document_entity_links', ['entity_id'])
    op.create_index('ix_doc_entity_links_company_id', 'document_entity_links', ['company_id'])
    op.create_index(
        'ix_doc_entity_links_company_type',
        'document_entity_links',
        ['company_id', 'link_type']
    )

    # Unique constraint: Ein Document kann mit einem Entity nur einmal pro Link-Type verknuepft sein
    op.create_unique_constraint(
        'uq_doc_entity_link',
        'document_entity_links',
        ['document_id', 'entity_id', 'link_type']
    )

    # 2. RiskScoreHistory - Historische Risk-Scores
    op.create_table(
        'risk_score_history',
        sa.Column('id', UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), primary_key=True),
        sa.Column('entity_id', UUID(as_uuid=True), sa.ForeignKey('business_entities.id', ondelete='CASCADE'), nullable=False),
        sa.Column('company_id', UUID(as_uuid=True), sa.ForeignKey('companies.id', ondelete='CASCADE'), nullable=False),
        sa.Column('score', sa.Float, nullable=False),
        sa.Column('risk_level', sa.String(20), nullable=True),  # low, medium, high, critical
        sa.Column('factors', JSONB, default=dict),  # {"payment_delay": 25, "default_rate": 15, ...}
        sa.Column('trigger_event', sa.String(100), nullable=True),  # scheduled, invoice_paid, dunning_increased
        sa.Column('calculated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # Indexes for RiskScoreHistory
    op.create_index('ix_risk_score_history_entity_id', 'risk_score_history', ['entity_id'])
    op.create_index('ix_risk_score_history_company_id', 'risk_score_history', ['company_id'])
    op.create_index(
        'ix_risk_score_history_entity_date',
        'risk_score_history',
        ['entity_id', 'calculated_at']
    )
    op.create_index(
        'ix_risk_score_history_company_date',
        'risk_score_history',
        ['company_id', 'calculated_at']
    )


def downgrade() -> None:
    """Remove DocumentEntityLink and RiskScoreHistory tables."""

    # Drop RiskScoreHistory
    op.drop_index('ix_risk_score_history_company_date', 'risk_score_history')
    op.drop_index('ix_risk_score_history_entity_date', 'risk_score_history')
    op.drop_index('ix_risk_score_history_company_id', 'risk_score_history')
    op.drop_index('ix_risk_score_history_entity_id', 'risk_score_history')
    op.drop_table('risk_score_history')

    # Drop DocumentEntityLink
    op.drop_constraint('uq_doc_entity_link', 'document_entity_links', type_='unique')
    op.drop_index('ix_doc_entity_links_company_type', 'document_entity_links')
    op.drop_index('ix_doc_entity_links_company_id', 'document_entity_links')
    op.drop_index('ix_doc_entity_links_entity_id', 'document_entity_links')
    op.drop_index('ix_doc_entity_links_document_id', 'document_entity_links')
    op.drop_table('document_entity_links')
