# -*- coding: utf-8 -*-
"""Add Contract AI tables.

Vision 2.0 Feature: Contract AI - Intelligente Vertragsanalyse
Erstellt Tabellen fuer:
- contracts: Haupttabelle fuer Vertraege
- contract_obligations: Vertragspflichten und -verpflichtungen
- contract_deadlines: Vertragsfristen und wichtige Termine
- contract_comparisons: Vertragsvergleiche zwischen Versionen

Revision ID: 141_add_contracts
Revises: 140_add_project_document_chains
Create Date: 2026-01-29

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '141_add_contracts'
down_revision: Union[str, None] = '140_add_project_document_chains'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create contract-related tables."""

    # ============================================================
    # 1. contracts - Haupttabelle
    # ============================================================
    op.create_table(
        'contracts',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('document_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('contract_number', sa.String(100), nullable=True),
        sa.Column('title', sa.String(500), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('contract_type', sa.String(50), nullable=False, server_default='other'),
        sa.Column('status', sa.String(30), nullable=False, server_default='draft'),
        sa.Column('parties', postgresql.JSONB(astext_type=sa.Text()), nullable=True, server_default='[]'),
        sa.Column('our_role', sa.String(50), nullable=True),
        sa.Column('counterparty_entity_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('effective_date', sa.Date(), nullable=True),
        sa.Column('expiration_date', sa.Date(), nullable=True),
        sa.Column('signed_date', sa.Date(), nullable=True),
        sa.Column('auto_renewal', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('renewal_period_months', sa.Integer(), nullable=True),
        sa.Column('renewal_notice_days', sa.Integer(), nullable=True),
        sa.Column('notice_period_days', sa.Integer(), nullable=True),
        sa.Column('termination_date', sa.Date(), nullable=True),
        sa.Column('termination_reason', sa.Text(), nullable=True),
        sa.Column('total_value', sa.Numeric(15, 2), nullable=True),
        sa.Column('currency', sa.String(3), nullable=False, server_default='EUR'),
        sa.Column('payment_terms', postgresql.JSONB(astext_type=sa.Text()), nullable=True, server_default='{}'),
        sa.Column('clauses', postgresql.JSONB(astext_type=sa.Text()), nullable=True, server_default='{}'),
        sa.Column('signatures', postgresql.JSONB(astext_type=sa.Text()), nullable=True, server_default='[]'),
        sa.Column('risk_score', sa.Integer(), nullable=True),
        sa.Column('risk_factors', postgresql.JSONB(astext_type=sa.Text()), nullable=True, server_default='[]'),
        sa.Column('extraction_confidence', sa.Numeric(5, 4), nullable=True),
        sa.Column('extraction_backend', sa.String(50), nullable=True),
        sa.Column('last_analyzed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('analysis_version', sa.String(20), nullable=True),
        sa.Column('version_number', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('parent_contract_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('company_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('created_by_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('updated_by_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text('now()')),
        sa.Column('tags', postgresql.JSONB(astext_type=sa.Text()), nullable=True, server_default='[]'),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['document_id'], ['documents.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['counterparty_entity_id'], ['business_entities.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['parent_contract_id'], ['contracts.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['company_id'], ['companies.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['updated_by_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.CheckConstraint(
            'risk_score IS NULL OR (risk_score >= 0 AND risk_score <= 100)',
            name='ck_contracts_risk_score',
        ),
    )

    # Contracts indexes
    op.create_index('ix_contracts_document_id', 'contracts', ['document_id'])
    op.create_index('ix_contracts_contract_number', 'contracts', ['contract_number'])
    op.create_index('ix_contracts_contract_type', 'contracts', ['contract_type'])
    op.create_index('ix_contracts_status', 'contracts', ['status'])
    op.create_index('ix_contracts_counterparty', 'contracts', ['counterparty_entity_id'])
    op.create_index('ix_contracts_effective_date', 'contracts', ['effective_date'])
    op.create_index('ix_contracts_expiration_date', 'contracts', ['expiration_date'])
    op.create_index('ix_contracts_company_id', 'contracts', ['company_id'])
    op.create_index('ix_contracts_company_status', 'contracts', ['company_id', 'status'])
    op.create_index('ix_contracts_company_type', 'contracts', ['company_id', 'contract_type'])

    # ============================================================
    # 2. contract_obligations - Vertragspflichten
    # ============================================================
    op.create_table(
        'contract_obligations',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('contract_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('obligation_type', sa.String(30), nullable=False, server_default='other'),
        sa.Column('title', sa.String(255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('responsible_party', sa.String(50), nullable=True),
        sa.Column('assignee_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('due_date', sa.Date(), nullable=True),
        sa.Column('recurring', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('recurrence_pattern', sa.String(20), nullable=True),
        sa.Column('recurrence_end_date', sa.Date(), nullable=True),
        sa.Column('next_occurrence_date', sa.Date(), nullable=True),
        sa.Column('status', sa.String(20), nullable=False, server_default='pending'),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_by_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('reminder_days', sa.Integer(), nullable=False, server_default='7'),
        sa.Column('reminder_sent', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('reminder_sent_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('amount', sa.Numeric(15, 2), nullable=True),
        sa.Column('currency', sa.String(3), nullable=False, server_default='EUR'),
        sa.Column('metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=True, server_default='{}'),
        sa.Column('company_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['contract_id'], ['contracts.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['assignee_id'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['completed_by_id'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['company_id'], ['companies.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )

    # Obligations indexes
    op.create_index('ix_obligations_contract_id', 'contract_obligations', ['contract_id'])
    op.create_index('ix_obligations_due_date', 'contract_obligations', ['due_date'])
    op.create_index('ix_obligations_status', 'contract_obligations', ['status'])
    op.create_index('ix_obligations_next_occurrence', 'contract_obligations', ['next_occurrence_date'])
    op.create_index('ix_obligations_contract_status', 'contract_obligations', ['contract_id', 'status'])
    op.create_index('ix_obligations_company_status', 'contract_obligations', ['company_id', 'status'])

    # ============================================================
    # 3. contract_deadlines - Vertragsfristen
    # ============================================================
    op.create_table(
        'contract_deadlines',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('contract_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('deadline_type', sa.String(50), nullable=False),
        sa.Column('title', sa.String(255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('deadline_date', sa.Date(), nullable=False),
        sa.Column('priority', sa.String(20), nullable=False, server_default='medium'),
        sa.Column('is_completed', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_by_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('action_taken', sa.Text(), nullable=True),
        sa.Column('reminder_days_before', postgresql.JSONB(astext_type=sa.Text()), nullable=True,
                  server_default='[30, 14, 7, 1]'),
        sa.Column('last_reminder_sent', sa.DateTime(timezone=True), nullable=True),
        sa.Column('assignee_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('company_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['contract_id'], ['contracts.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['completed_by_id'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['assignee_id'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['company_id'], ['companies.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )

    # Deadlines indexes
    op.create_index('ix_deadlines_contract_id', 'contract_deadlines', ['contract_id'])
    op.create_index('ix_deadlines_date', 'contract_deadlines', ['deadline_date'])
    op.create_index('ix_deadlines_company_pending', 'contract_deadlines', ['company_id', 'is_completed'])

    # ============================================================
    # 4. contract_comparisons - Vertragsvergleiche
    # ============================================================
    op.create_table(
        'contract_comparisons',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('contract_a_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('contract_b_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('differences', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default='[]'),
        sa.Column('similarity_score', sa.Numeric(5, 4), nullable=True),
        sa.Column('added_clauses', postgresql.JSONB(astext_type=sa.Text()), nullable=True, server_default='[]'),
        sa.Column('removed_clauses', postgresql.JSONB(astext_type=sa.Text()), nullable=True, server_default='[]'),
        sa.Column('modified_clauses', postgresql.JSONB(astext_type=sa.Text()), nullable=True, server_default='[]'),
        sa.Column('risk_impact', sa.Integer(), nullable=True),
        sa.Column('risk_summary', sa.Text(), nullable=True),
        sa.Column('company_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('created_by_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['contract_a_id'], ['contracts.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['contract_b_id'], ['contracts.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['company_id'], ['companies.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )

    # Comparisons indexes
    op.create_index('ix_comparisons_contract_a', 'contract_comparisons', ['contract_a_id'])
    op.create_index('ix_comparisons_contract_b', 'contract_comparisons', ['contract_b_id'])
    op.create_index('ix_comparisons_contracts', 'contract_comparisons', ['contract_a_id', 'contract_b_id'])


def downgrade() -> None:
    """Drop contract-related tables."""

    # Drop in reverse order due to foreign keys
    op.drop_index('ix_comparisons_contracts', table_name='contract_comparisons')
    op.drop_index('ix_comparisons_contract_b', table_name='contract_comparisons')
    op.drop_index('ix_comparisons_contract_a', table_name='contract_comparisons')
    op.drop_table('contract_comparisons')

    op.drop_index('ix_deadlines_company_pending', table_name='contract_deadlines')
    op.drop_index('ix_deadlines_date', table_name='contract_deadlines')
    op.drop_index('ix_deadlines_contract_id', table_name='contract_deadlines')
    op.drop_table('contract_deadlines')

    op.drop_index('ix_obligations_company_status', table_name='contract_obligations')
    op.drop_index('ix_obligations_contract_status', table_name='contract_obligations')
    op.drop_index('ix_obligations_next_occurrence', table_name='contract_obligations')
    op.drop_index('ix_obligations_status', table_name='contract_obligations')
    op.drop_index('ix_obligations_due_date', table_name='contract_obligations')
    op.drop_index('ix_obligations_contract_id', table_name='contract_obligations')
    op.drop_table('contract_obligations')

    op.drop_index('ix_contracts_company_type', table_name='contracts')
    op.drop_index('ix_contracts_company_status', table_name='contracts')
    op.drop_index('ix_contracts_company_id', table_name='contracts')
    op.drop_index('ix_contracts_expiration_date', table_name='contracts')
    op.drop_index('ix_contracts_effective_date', table_name='contracts')
    op.drop_index('ix_contracts_counterparty', table_name='contracts')
    op.drop_index('ix_contracts_status', table_name='contracts')
    op.drop_index('ix_contracts_contract_type', table_name='contracts')
    op.drop_index('ix_contracts_contract_number', table_name='contracts')
    op.drop_index('ix_contracts_document_id', table_name='contracts')
    op.drop_table('contracts')
