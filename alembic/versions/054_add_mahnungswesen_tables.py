# -*- coding: utf-8 -*-
"""Add Mahnungswesen (Dunning System) tables.

Revision ID: 054_add_mahnungswesen
Revises: 053_add_user_preferences
Create Date: 2024-12-25

This migration adds:
1. mahnung_history - Immutable audit log for dunning actions
2. mahn_tasks - Task management for dunning workflow
3. phone_call_logs - Phone contact documentation
4. dunning_stage_configs - Configurable dunning stages
5. customer_dunning_overrides - Per-customer dunning settings
6. New fields to dunning_records for B2B/B2C and Mahnstopp

BGB §286 Compliance:
- B2B: Basiszins + 9% = 11.27% p.a.
- B2C: Basiszins + 5% = 7.27% p.a.
- EUR 40 Pauschale nach §288 Abs. 5 BGB
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB


# revision identifiers, used by Alembic.
revision = '054_add_mahnungswesen'
down_revision = '053_add_user_preferences'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create Mahnungswesen tables and extend DunningRecord."""

    # =========================================================================
    # 1. Extend dunning_records with new fields
    # =========================================================================

    # B2B/B2C distinction for interest calculation
    op.add_column('dunning_records', sa.Column(
        'is_b2b', sa.Boolean(), nullable=True, server_default='true',
        comment='B2B: +9% Zinsen, B2C: +5% Zinsen'
    ))
    op.add_column('dunning_records', sa.Column(
        'b2b_pauschale_claimed', sa.Boolean(), nullable=True, server_default='false',
        comment='EUR40 Pauschale nach §288 Abs. 5 BGB'
    ))

    # Mahnstopp (for disputes/Reklamationen)
    op.add_column('dunning_records', sa.Column(
        'mahnstopp', sa.Boolean(), nullable=True, server_default='false',
        comment='Stoppt automatische Mahnung'
    ))
    op.add_column('dunning_records', sa.Column(
        'mahnstopp_reason', sa.String(255), nullable=True
    ))
    op.add_column('dunning_records', sa.Column(
        'mahnstopp_until', sa.DateTime(timezone=True), nullable=True
    ))

    # =========================================================================
    # 2. Create mahnung_history table (immutable audit log)
    # =========================================================================

    op.create_table(
        'mahnung_history',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('dunning_record_id', UUID(as_uuid=True),
                  sa.ForeignKey('dunning_records.id', ondelete='CASCADE'),
                  nullable=False, index=True),

        # Action
        sa.Column('action_type', sa.String(50), nullable=False,
                  comment='reminder_sent, escalated, phone_call, payment_received, etc.'),
        sa.Column('mahn_stufe', sa.Integer(), nullable=False,
                  comment='Mahnstufe zum Zeitpunkt der Aktion'),
        sa.Column('action_timestamp', sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),

        # Performer
        sa.Column('performed_by_id', UUID(as_uuid=True),
                  sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),

        # Details
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('outcome', sa.String(50), nullable=True,
                  comment='success, failed, pending, etc.'),
        sa.Column('document_id', UUID(as_uuid=True),
                  sa.ForeignKey('documents.id', ondelete='SET NULL'), nullable=True),

        # Metadata
        sa.Column('metadata', JSONB(), server_default='{}'),
    )

    op.create_index('ix_mahnung_history_action_timestamp', 'mahnung_history', ['action_timestamp'])
    op.create_index('ix_mahnung_history_action_type', 'mahnung_history', ['action_type'])

    # =========================================================================
    # 3. Create mahn_tasks table (task management)
    # =========================================================================

    op.create_table(
        'mahn_tasks',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('dunning_record_id', UUID(as_uuid=True),
                  sa.ForeignKey('dunning_records.id', ondelete='CASCADE'),
                  nullable=False, index=True),

        # Task type
        sa.Column('task_type', sa.String(50), nullable=False,
                  comment='reminder, escalate, phone_call, review, collection'),

        # Assignment
        sa.Column('assigned_user_id', UUID(as_uuid=True),
                  sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),

        # Due date
        sa.Column('due_date', sa.Date(), nullable=False),

        # Status
        sa.Column('status', sa.String(20), nullable=False, server_default='pending',
                  comment='pending, in_progress, completed, snoozed, cancelled'),

        # Snooze (max 3x)
        sa.Column('snoozed_until', sa.Date(), nullable=True),
        sa.Column('snooze_count', sa.Integer(), server_default='0'),
        sa.Column('snooze_reason', sa.String(255), nullable=True),

        # Completion
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_by_id', UUID(as_uuid=True),
                  sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('completion_notes', sa.Text(), nullable=True),

        # Priority (1=highest, 5=lowest)
        sa.Column('priority', sa.Integer(), server_default='3'),

        # Audit
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_index('ix_mahn_tasks_status', 'mahn_tasks', ['status'])
    op.create_index('ix_mahn_tasks_due_date', 'mahn_tasks', ['due_date'])
    op.create_index('ix_mahn_tasks_assigned_user', 'mahn_tasks', ['assigned_user_id'])

    # =========================================================================
    # 4. Create phone_call_logs table
    # =========================================================================

    op.create_table(
        'phone_call_logs',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('dunning_record_id', UUID(as_uuid=True),
                  sa.ForeignKey('dunning_records.id', ondelete='CASCADE'),
                  nullable=False, index=True),

        # Call data
        sa.Column('called_at', sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column('called_by_id', UUID(as_uuid=True),
                  sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),

        # Contact
        sa.Column('contact_name', sa.String(255), nullable=False),
        sa.Column('phone_number', sa.String(50), nullable=True),

        # Outcome
        sa.Column('outcome', sa.String(50), nullable=False,
                  comment='reached, not_reached, voicemail, callback_requested, payment_promised, dispute_raised'),

        # Notes
        sa.Column('notes', sa.Text(), nullable=True),

        # Follow-up
        sa.Column('follow_up_required', sa.Boolean(), server_default='false'),
        sa.Column('follow_up_date', sa.Date(), nullable=True),
        sa.Column('follow_up_notes', sa.String(255), nullable=True),
    )

    op.create_index('ix_phone_call_logs_called_at', 'phone_call_logs', ['called_at'])

    # =========================================================================
    # 5. Create dunning_stage_configs table (admin settings)
    # =========================================================================

    op.create_table(
        'dunning_stage_configs',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', UUID(as_uuid=True),
                  sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),

        # Stage definition
        sa.Column('stage_number', sa.Integer(), nullable=False,
                  comment='1-basiert: 1=erste Stufe'),
        sa.Column('stage_name', sa.String(100), nullable=False,
                  comment='z.B. Zahlungserinnerung, 1. Mahnung'),

        # Trigger
        sa.Column('trigger_days_after_due', sa.Integer(), nullable=False,
                  comment='Tage nach Faelligkeit'),

        # Action
        sa.Column('action_type', sa.String(50), nullable=False,
                  comment='email, letter, phone, escalation'),
        sa.Column('template_id', UUID(as_uuid=True), nullable=True,
                  comment='Template-ID fuer Dokument-Generierung'),

        # Fees
        sa.Column('fee_amount', sa.Numeric(10, 2), server_default='0',
                  comment='Mahngebuehr in EUR'),

        # Status
        sa.Column('is_active', sa.Boolean(), server_default='true'),

        # Sort order (for drag-and-drop reorder)
        sa.Column('sort_order', sa.Integer(), server_default='0'),

        # Audit
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_index('ix_dunning_stage_configs_user_id', 'dunning_stage_configs', ['user_id'])
    op.create_index('ix_dunning_stage_configs_sort_order', 'dunning_stage_configs',
                    ['user_id', 'sort_order'])

    # =========================================================================
    # 6. Create customer_dunning_overrides table
    # =========================================================================

    op.create_table(
        'customer_dunning_overrides',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('business_entity_id', UUID(as_uuid=True),
                  sa.ForeignKey('business_entities.id', ondelete='CASCADE'),
                  nullable=False, unique=True),

        # Payment terms
        sa.Column('custom_payment_terms_days', sa.Integer(), nullable=True,
                  comment='Abweichende Zahlungsfrist'),

        # Dunning settings
        sa.Column('max_mahn_stufe', sa.Integer(), nullable=True,
                  comment='Max. Eskalationsstufe (z.B. 2 = nie Inkasso)'),
        sa.Column('preferred_contact_method', sa.String(50), server_default="'email'",
                  comment='email, phone, letter'),

        # Exclusion
        sa.Column('exclude_from_auto_dunning', sa.Boolean(), server_default='false',
                  comment='Keine automatischen Mahnungen'),
        sa.Column('exclusion_reason', sa.String(255), nullable=True),

        # Notes
        sa.Column('notes', sa.Text(), nullable=True),

        # Audit
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_index('ix_customer_dunning_overrides_entity', 'customer_dunning_overrides',
                    ['business_entity_id'])

    # =========================================================================
    # 7. Create trigger to make mahnung_history immutable (PostgreSQL only)
    # =========================================================================

    # Only create trigger for PostgreSQL
    op.execute("""
        DO $$
        BEGIN
            -- Create function to prevent updates/deletes
            CREATE OR REPLACE FUNCTION prevent_mahnung_history_modification()
            RETURNS TRIGGER AS $func$
            BEGIN
                RAISE EXCEPTION 'mahnung_history ist unveraenderbar - UPDATE und DELETE sind nicht erlaubt';
            END;
            $func$ LANGUAGE plpgsql;

            -- Create trigger for UPDATE
            DROP TRIGGER IF EXISTS tr_mahnung_history_no_update ON mahnung_history;
            CREATE TRIGGER tr_mahnung_history_no_update
                BEFORE UPDATE ON mahnung_history
                FOR EACH ROW
                EXECUTE FUNCTION prevent_mahnung_history_modification();

            -- Create trigger for DELETE
            DROP TRIGGER IF EXISTS tr_mahnung_history_no_delete ON mahnung_history;
            CREATE TRIGGER tr_mahnung_history_no_delete
                BEFORE DELETE ON mahnung_history
                FOR EACH ROW
                EXECUTE FUNCTION prevent_mahnung_history_modification();

            RAISE NOTICE 'mahnung_history immutability triggers created successfully';
        EXCEPTION
            WHEN others THEN
                RAISE NOTICE 'Could not create immutability triggers: %', SQLERRM;
        END $$;
    """)


def downgrade() -> None:
    """Remove Mahnungswesen tables and fields."""

    # Drop triggers first
    op.execute("""
        DO $$
        BEGIN
            DROP TRIGGER IF EXISTS tr_mahnung_history_no_update ON mahnung_history;
            DROP TRIGGER IF EXISTS tr_mahnung_history_no_delete ON mahnung_history;
            DROP FUNCTION IF EXISTS prevent_mahnung_history_modification();
        EXCEPTION
            WHEN others THEN
                RAISE NOTICE 'Could not drop triggers: %', SQLERRM;
        END $$;
    """)

    # Drop tables
    op.drop_table('customer_dunning_overrides')
    op.drop_table('dunning_stage_configs')
    op.drop_table('phone_call_logs')
    op.drop_table('mahn_tasks')
    op.drop_table('mahnung_history')

    # Remove columns from dunning_records
    op.drop_column('dunning_records', 'mahnstopp_until')
    op.drop_column('dunning_records', 'mahnstopp_reason')
    op.drop_column('dunning_records', 'mahnstopp')
    op.drop_column('dunning_records', 'b2b_pauschale_claimed')
    op.drop_column('dunning_records', 'is_b2b')
