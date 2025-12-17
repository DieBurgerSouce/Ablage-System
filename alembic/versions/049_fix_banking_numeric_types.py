# -*- coding: utf-8 -*-
"""
Fix Banking Tables: Float -> Numeric, IBAN Constraint, Cascade.

Revision ID: 049_fix_banking_numeric_types
Revises: 048_add_datev_indexes
Create Date: 2025-12-17

SECURITY FIX: Diese Migration behebt kritische Datenintegritaetsprobleme:

1. Float -> Numeric: Verhindert Rundungsfehler bei Geldbetraegen
   Beispiel: 0.1 + 0.2 != 0.3 bei Float, aber korrekt bei Numeric

2. UNIQUE Constraint auf (user_id, iban): Verhindert doppelte Konten

3. Cascade Fix: CashFlowEntry.bank_account_id nutzt SET NULL statt CASCADE
   um historische Planungsdaten bei Konto-Loeschung zu erhalten
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '049_fix_banking_numeric_types'
down_revision = '048_add_datev_indexes'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Upgrade banking tables with type and constraint fixes."""
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    # =========================================================================
    # 1. Float -> Numeric(15, 2) fuer Geldbetraege
    # =========================================================================

    if is_postgres:
        # BankAccount.current_balance
        op.alter_column(
            'bank_accounts',
            'current_balance',
            type_=sa.Numeric(15, 2),
            existing_type=sa.Float(),
            existing_nullable=True
        )

        # BankTransaction.amount
        op.alter_column(
            'bank_transactions',
            'amount',
            type_=sa.Numeric(15, 2),
            existing_type=sa.Float(),
            existing_nullable=False
        )

        # BankTransaction.allocated_amount
        op.alter_column(
            'bank_transactions',
            'allocated_amount',
            type_=sa.Numeric(15, 2),
            existing_type=sa.Float(),
            existing_nullable=True
        )

        # BankTransaction.remaining_amount
        op.alter_column(
            'bank_transactions',
            'remaining_amount',
            type_=sa.Numeric(15, 2),
            existing_type=sa.Float(),
            existing_nullable=True
        )

        # PaymentBatch.total_amount
        op.alter_column(
            'payment_batches',
            'total_amount',
            type_=sa.Numeric(15, 2),
            existing_type=sa.Float(),
            existing_nullable=True
        )

        # PaymentOrder.amount
        op.alter_column(
            'payment_orders',
            'amount',
            type_=sa.Numeric(15, 2),
            existing_type=sa.Float(),
            existing_nullable=False
        )

        # PaymentOrder.skonto_amount
        op.alter_column(
            'payment_orders',
            'skonto_amount',
            type_=sa.Numeric(15, 2),
            existing_type=sa.Float(),
            existing_nullable=True
        )

        # PaymentOrder.original_amount
        op.alter_column(
            'payment_orders',
            'original_amount',
            type_=sa.Numeric(15, 2),
            existing_type=sa.Float(),
            existing_nullable=True
        )

        # DunningRecord.gross_amount
        op.alter_column(
            'dunning_records',
            'gross_amount',
            type_=sa.Numeric(15, 2),
            existing_type=sa.Float(),
            existing_nullable=True
        )

        # DunningRecord.outstanding_amount
        op.alter_column(
            'dunning_records',
            'outstanding_amount',
            type_=sa.Numeric(15, 2),
            existing_type=sa.Float(),
            existing_nullable=True
        )

        # DunningRecord.reminder_fee
        op.alter_column(
            'dunning_records',
            'reminder_fee',
            type_=sa.Numeric(15, 2),
            existing_type=sa.Float(),
            existing_nullable=True
        )

        # DunningRecord.late_interest_rate (Prozentsatz)
        op.alter_column(
            'dunning_records',
            'late_interest_rate',
            type_=sa.Numeric(7, 4),
            existing_type=sa.Float(),
            existing_nullable=True
        )

        # DunningRecord.accrued_interest
        op.alter_column(
            'dunning_records',
            'accrued_interest',
            type_=sa.Numeric(15, 2),
            existing_type=sa.Float(),
            existing_nullable=True
        )

        # DunningRecord.total_outstanding
        op.alter_column(
            'dunning_records',
            'total_outstanding',
            type_=sa.Numeric(15, 2),
            existing_type=sa.Float(),
            existing_nullable=True
        )

        # CashFlowEntry.expected_amount
        op.alter_column(
            'cash_flow_entries',
            'expected_amount',
            type_=sa.Numeric(15, 2),
            existing_type=sa.Float(),
            existing_nullable=False
        )

        # CashFlowEntry.actual_amount
        op.alter_column(
            'cash_flow_entries',
            'actual_amount',
            type_=sa.Numeric(15, 2),
            existing_type=sa.Float(),
            existing_nullable=True
        )

    # =========================================================================
    # 2. UNIQUE Constraint auf (user_id, iban) in bank_accounts
    # =========================================================================

    # Erstelle unique constraint fuer IBAN pro User
    op.create_unique_constraint(
        'uq_bank_accounts_user_iban',
        'bank_accounts',
        ['user_id', 'iban']
    )

    # Erstelle unique constraint fuer file_hash pro User (Race Condition Prevention)
    op.create_unique_constraint(
        'uq_bank_imports_user_file_hash',
        'bank_imports',
        ['user_id', 'file_hash']
    )

    # =========================================================================
    # 3. Cascade Fix: CashFlowEntry.bank_account_id -> SET NULL
    # =========================================================================

    if is_postgres:
        # Alte FK droppen und mit SET NULL neu erstellen
        op.drop_constraint(
            'cash_flow_entries_bank_account_id_fkey',
            'cash_flow_entries',
            type_='foreignkey'
        )

        op.create_foreign_key(
            'cash_flow_entries_bank_account_id_fkey',
            'cash_flow_entries',
            'bank_accounts',
            ['bank_account_id'],
            ['id'],
            ondelete='SET NULL'
        )


def downgrade() -> None:
    """Revert banking table changes."""
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    # =========================================================================
    # 3. Revert Cascade Fix
    # =========================================================================

    if is_postgres:
        op.drop_constraint(
            'cash_flow_entries_bank_account_id_fkey',
            'cash_flow_entries',
            type_='foreignkey'
        )

        # Achtung: Original war evtl. CASCADE - hier konservativ SET NULL
        op.create_foreign_key(
            'cash_flow_entries_bank_account_id_fkey',
            'cash_flow_entries',
            'bank_accounts',
            ['bank_account_id'],
            ['id'],
            ondelete='SET NULL'
        )

    # =========================================================================
    # 2. Revert UNIQUE Constraints
    # =========================================================================

    op.drop_constraint(
        'uq_bank_imports_user_file_hash',
        'bank_imports',
        type_='unique'
    )

    op.drop_constraint(
        'uq_bank_accounts_user_iban',
        'bank_accounts',
        type_='unique'
    )

    # =========================================================================
    # 1. Revert Numeric -> Float (WARNUNG: Datenverlust moeglich!)
    # =========================================================================

    if is_postgres:
        # Hinweis: Downgrade auf Float kann Praezision verlieren!

        op.alter_column('bank_accounts', 'current_balance',
            type_=sa.Float(), existing_type=sa.Numeric(15, 2))

        op.alter_column('bank_transactions', 'amount',
            type_=sa.Float(), existing_type=sa.Numeric(15, 2))

        op.alter_column('bank_transactions', 'allocated_amount',
            type_=sa.Float(), existing_type=sa.Numeric(15, 2))

        op.alter_column('bank_transactions', 'remaining_amount',
            type_=sa.Float(), existing_type=sa.Numeric(15, 2))

        op.alter_column('payment_batches', 'total_amount',
            type_=sa.Float(), existing_type=sa.Numeric(15, 2))

        op.alter_column('payment_orders', 'amount',
            type_=sa.Float(), existing_type=sa.Numeric(15, 2))

        op.alter_column('payment_orders', 'skonto_amount',
            type_=sa.Float(), existing_type=sa.Numeric(15, 2))

        op.alter_column('payment_orders', 'original_amount',
            type_=sa.Float(), existing_type=sa.Numeric(15, 2))

        op.alter_column('dunning_records', 'gross_amount',
            type_=sa.Float(), existing_type=sa.Numeric(15, 2))

        op.alter_column('dunning_records', 'outstanding_amount',
            type_=sa.Float(), existing_type=sa.Numeric(15, 2))

        op.alter_column('dunning_records', 'reminder_fee',
            type_=sa.Float(), existing_type=sa.Numeric(15, 2))

        op.alter_column('dunning_records', 'late_interest_rate',
            type_=sa.Float(), existing_type=sa.Numeric(7, 4))

        op.alter_column('dunning_records', 'accrued_interest',
            type_=sa.Float(), existing_type=sa.Numeric(15, 2))

        op.alter_column('dunning_records', 'total_outstanding',
            type_=sa.Float(), existing_type=sa.Numeric(15, 2))

        op.alter_column('cash_flow_entries', 'expected_amount',
            type_=sa.Float(), existing_type=sa.Numeric(15, 2))

        op.alter_column('cash_flow_entries', 'actual_amount',
            type_=sa.Float(), existing_type=sa.Numeric(15, 2))
