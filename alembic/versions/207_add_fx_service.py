# -*- coding: utf-8 -*-
"""add_fx_service

Revision ID: 207_add_fx_service
Revises: 206_add_gl_posting_system
Create Date: 2026-02-07 23:22:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '207_add_fx_service'
down_revision: Union[str, None] = '206_add_gl_posting_system'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create exchange_rates table
    op.create_table(
        'exchange_rates',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('base_currency', sa.String(length=3), nullable=False, server_default='EUR'),
        sa.Column('target_currency', sa.String(length=3), nullable=False),
        sa.Column('rate', sa.Numeric(precision=18, scale=8), nullable=False),
        sa.Column('rate_date', sa.Date(), nullable=False),
        sa.Column('source', sa.String(length=20), nullable=False, server_default='ecb'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('base_currency', 'target_currency', 'rate_date', 'source', name='uq_exchange_rate')
    )
    op.create_index('ix_exchange_rates_lookup', 'exchange_rates', ['base_currency', 'target_currency', 'rate_date'])

    # Create fx_gain_loss_entries table
    op.create_table(
        'fx_gain_loss_entries',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('company_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('journal_entry_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('original_currency', sa.String(length=3), nullable=False),
        sa.Column('original_amount', sa.Numeric(precision=15, scale=2), nullable=False),
        sa.Column('booking_rate', sa.Numeric(precision=18, scale=8), nullable=False),
        sa.Column('settlement_rate', sa.Numeric(precision=18, scale=8), nullable=False),
        sa.Column('gain_loss_amount', sa.Numeric(precision=15, scale=2), nullable=False),
        sa.Column('gain_loss_account', sa.String(length=5), nullable=False),
        sa.Column('realized', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('reference_document_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['company_id'], ['companies.id'], ),
        sa.ForeignKeyConstraint(['journal_entry_id'], ['journal_entries.id'], ),
        sa.ForeignKeyConstraint(['reference_document_id'], ['documents.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_fx_gain_loss_company', 'fx_gain_loss_entries', ['company_id'])
    op.create_index('ix_fx_gain_loss_journal', 'fx_gain_loss_entries', ['journal_entry_id'])


def downgrade() -> None:
    op.drop_index('ix_fx_gain_loss_journal', table_name='fx_gain_loss_entries')
    op.drop_index('ix_fx_gain_loss_company', table_name='fx_gain_loss_entries')
    op.drop_table('fx_gain_loss_entries')

    op.drop_index('ix_exchange_rates_lookup', table_name='exchange_rates')
    op.drop_table('exchange_rates')
