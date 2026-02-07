"""Add GL-Posting System.

Revision ID: 206_add_gl_posting_system
Revises: 205_add_retention_enforcement
Create Date: 2026-02-07

Features:
- GL Accounts (Sachkonten SKR03/SKR04)
- Journal Entries (Buchungssaetze)
- Journal Entry Lines (Buchungszeilen)
- Tax Periods (USt-VA Perioden)

GoBD-konform: Keine Loeschungen, nur Stornierungen.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '206_add_gl_posting_system'
down_revision: str = '205_add_retention_enforcement'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add GL-Posting System tables."""

    # =========================================================================
    # GL Accounts Table
    # =========================================================================
    op.create_table(
        'gl_accounts',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('company_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('companies.id', ondelete='CASCADE'), nullable=False),
        sa.Column('account_number', sa.String(5), nullable=False, comment='Kontonummer (z.B. 1200)'),
        sa.Column('account_name', sa.String(100), nullable=False, comment='Kontobezeichnung'),
        sa.Column('account_class', sa.Integer(), nullable=False, comment='Kontenklasse 0-9'),
        sa.Column('is_custom', sa.Boolean(), nullable=False, server_default='false', comment='True = Custom Account'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('default_tax_code', sa.String(10), nullable=True, comment='Standard BU-Schluessel'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
        sa.UniqueConstraint('company_id', 'account_number', name='uq_gl_account_company_number'),
        sa.CheckConstraint('account_class >= 0 AND account_class <= 9', name='ck_gl_account_class_range'),
    )

    op.create_index('ix_gl_accounts_company_id', 'gl_accounts', ['company_id'])
    op.create_index('ix_gl_accounts_company_active', 'gl_accounts', ['company_id', 'is_active'])
    op.create_index('ix_gl_accounts_account_class', 'gl_accounts', ['account_class'])

    # =========================================================================
    # Journal Entries Table
    # =========================================================================
    op.create_table(
        'journal_entries',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('company_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('companies.id', ondelete='CASCADE'), nullable=False),
        sa.Column('document_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('documents.id', ondelete='SET NULL'), nullable=True),
        sa.Column('posting_date', sa.Date(), nullable=False, comment='Buchungsdatum'),
        sa.Column('fiscal_year', sa.Integer(), nullable=False, comment='Geschaeftsjahr'),
        sa.Column('fiscal_period', sa.Integer(), nullable=False, comment='Periode 1-12'),
        sa.Column('entry_number', sa.String(20), nullable=False, comment='Buchungsnummer (JE-2024-00001)'),
        sa.Column('description', sa.String(60), nullable=True, comment='Buchungsbeschreibung'),
        sa.Column('total_amount', sa.Numeric(15, 2), nullable=True, comment='Gesamtbetrag'),
        sa.Column('currency', sa.String(3), nullable=False, server_default='EUR'),
        sa.Column('exchange_rate', sa.Numeric(18, 8), nullable=True, comment='Wechselkurs'),
        sa.Column('status', sa.String(20), nullable=False, server_default='draft'),
        sa.Column('source', sa.String(20), nullable=True, comment='Quelle: manual, auto_booking, import, pipeline'),
        sa.Column('confidence', sa.Numeric(3, 2), nullable=True, comment='Confidence 0.00-1.00'),
        sa.Column('created_by_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('posted_by_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('posted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('reversed_by_entry_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('journal_entries.id', ondelete='SET NULL'), nullable=True),
        sa.Column('metadata_json', postgresql.JSONB(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
        sa.UniqueConstraint('company_id', 'entry_number', name='uq_journal_entry_number'),
        sa.CheckConstraint('fiscal_period >= 1 AND fiscal_period <= 12', name='ck_journal_entry_period_range'),
    )

    op.create_index('ix_journal_entries_company_id', 'journal_entries', ['company_id'])
    op.create_index('ix_journal_entries_company_period', 'journal_entries', ['company_id', 'fiscal_year', 'fiscal_period'])
    op.create_index('ix_journal_entries_posting_date', 'journal_entries', ['posting_date'])
    op.create_index('ix_journal_entries_status', 'journal_entries', ['status'])
    op.create_index('ix_journal_entries_document', 'journal_entries', ['document_id'])

    # =========================================================================
    # Journal Entry Lines Table
    # =========================================================================
    op.create_table(
        'journal_entry_lines',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('entry_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('journal_entries.id', ondelete='CASCADE'), nullable=False),
        sa.Column('line_number', sa.Integer(), nullable=False, comment='Zeilennummer'),
        sa.Column('account_number', sa.String(5), nullable=False, comment='Kontonummer (SKR03/04)'),
        sa.Column('account_name', sa.String(100), nullable=True, comment='Kontobezeichnung'),
        sa.Column('debit_amount', sa.Numeric(15, 2), nullable=False, server_default='0', comment='Soll-Betrag'),
        sa.Column('credit_amount', sa.Numeric(15, 2), nullable=False, server_default='0', comment='Haben-Betrag'),
        sa.Column('tax_code', sa.String(10), nullable=True, comment='DATEV BU-Schluessel'),
        sa.Column('tax_rate', sa.Numeric(5, 2), nullable=True, comment='Steuersatz in Prozent'),
        sa.Column('tax_amount', sa.Numeric(15, 2), nullable=True, comment='Steuerbetrag'),
        sa.Column('cost_center', sa.String(20), nullable=True, comment='Kostenstelle'),
        sa.Column('cost_object', sa.String(20), nullable=True, comment='Kostentraeger'),
        sa.Column('text', sa.String(60), nullable=True, comment='Buchungstext'),
        sa.CheckConstraint('NOT (debit_amount > 0 AND credit_amount > 0)', name='ck_journal_line_not_both_debit_credit'),
    )

    op.create_index('ix_journal_entry_lines_entry', 'journal_entry_lines', ['entry_id', 'line_number'])
    op.create_index('ix_journal_entry_lines_account', 'journal_entry_lines', ['account_number'])
    op.create_index('ix_journal_entry_lines_tax_code', 'journal_entry_lines', ['tax_code'])

    # =========================================================================
    # Tax Periods Table
    # =========================================================================
    op.create_table(
        'tax_periods',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('company_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('companies.id', ondelete='CASCADE'), nullable=False),
        sa.Column('fiscal_year', sa.Integer(), nullable=False),
        sa.Column('period_type', sa.String(20), nullable=False, comment='monthly oder quarterly'),
        sa.Column('period_number', sa.Integer(), nullable=False, comment='Monat 1-12 oder Quartal 1-4'),
        sa.Column('period_start', sa.Date(), nullable=False),
        sa.Column('period_end', sa.Date(), nullable=False),
        sa.Column('status', sa.String(20), nullable=False, server_default='open'),
        sa.Column('total_output_vat', sa.Numeric(15, 2), nullable=False, server_default='0', comment='Umsatzsteuer'),
        sa.Column('total_input_vat', sa.Numeric(15, 2), nullable=False, server_default='0', comment='Vorsteuer'),
        sa.Column('vat_payable', sa.Numeric(15, 2), nullable=False, server_default='0', comment='Zahllast'),
        sa.Column('filed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('elster_transfer_ticket', sa.String(100), nullable=True),
        sa.Column('report_data', postgresql.JSONB(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
        sa.UniqueConstraint('company_id', 'fiscal_year', 'period_type', 'period_number', name='uq_tax_period_company_period'),
    )

    op.create_index('ix_tax_periods_company_id', 'tax_periods', ['company_id'])
    op.create_index('ix_tax_periods_company_year', 'tax_periods', ['company_id', 'fiscal_year'])
    op.create_index('ix_tax_periods_status', 'tax_periods', ['status'])
    op.create_index('ix_tax_periods_period_end', 'tax_periods', ['period_end'])


def downgrade() -> None:
    """Remove GL-Posting System tables."""

    # Drop tables in reverse order (respecting foreign keys)
    op.drop_table('tax_periods')
    op.drop_table('journal_entry_lines')
    op.drop_table('journal_entries')
    op.drop_table('gl_accounts')
