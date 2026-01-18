"""Add business contracts tables

Revision ID: 096_add_business_contracts
Revises: 095_add_document_chain_tracking
Create Date: 2026-01-16

Contract Management System:
- business_contracts: Core contract tracking
- contract_milestones: Important dates and events
- contract_renewal_options: Renewal tracking
- contract_amendments: Contract changes
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '096_add_business_contracts'
down_revision = '095_add_document_chain_tracking'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create contract type enum
    contract_type_enum = postgresql.ENUM(
        'service', 'supply', 'framework', 'maintenance', 'license',
        'lease', 'consulting', 'cooperation', 'nda', 'purchase', 'other',
        name='contracttype',
        create_type=False
    )
    contract_type_enum.create(op.get_bind(), checkfirst=True)

    # Create contract status enum
    contract_status_enum = postgresql.ENUM(
        'draft', 'pending_signature', 'active', 'suspended',
        'expiring_soon', 'expired', 'terminated', 'renewed',
        name='contractstatus',
        create_type=False
    )
    contract_status_enum.create(op.get_bind(), checkfirst=True)

    # Create renewal option status enum
    renewal_status_enum = postgresql.ENUM(
        'available', 'pending', 'exercised', 'declined', 'expired',
        name='renewaloptionstatus',
        create_type=False
    )
    renewal_status_enum.create(op.get_bind(), checkfirst=True)

    # Create milestone type enum
    milestone_type_enum = postgresql.ENUM(
        'contract_start', 'contract_end', 'renewal_option', 'notice_deadline',
        'price_adjustment', 'service_level_review', 'deliverable_due',
        'payment_due', 'audit', 'custom',
        name='milestonetype',
        create_type=False
    )
    milestone_type_enum.create(op.get_bind(), checkfirst=True)

    # Create amendment status enum
    amendment_status_enum = postgresql.ENUM(
        'draft', 'pending_approval', 'approved', 'rejected', 'superseded',
        name='amendmentstatus',
        create_type=False
    )
    amendment_status_enum.create(op.get_bind(), checkfirst=True)

    # Create business_contracts table
    op.create_table(
        'business_contracts',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('company_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('companies.id'), nullable=False),

        # Contract identification
        sa.Column('contract_number', sa.String(100), nullable=False),
        sa.Column('title', sa.String(500), nullable=False),
        sa.Column('contract_type', postgresql.ENUM(
            'service', 'supply', 'framework', 'maintenance', 'license',
            'lease', 'consulting', 'cooperation', 'nda', 'purchase', 'other',
            name='contracttype', create_type=False
        ), default='other'),
        sa.Column('description', sa.Text, nullable=True),

        # Contract parties
        sa.Column('party_a_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('business_entities.id'), nullable=True),
        sa.Column('party_a_name', sa.String(255), nullable=True),
        sa.Column('party_a_signatory', sa.String(255), nullable=True),
        sa.Column('party_b_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('business_entities.id'), nullable=True),
        sa.Column('party_b_name', sa.String(255), nullable=True),
        sa.Column('party_b_signatory', sa.String(255), nullable=True),

        # Contract timeline
        sa.Column('contract_date', sa.Date, nullable=True),
        sa.Column('start_date', sa.Date, nullable=False),
        sa.Column('end_date', sa.Date, nullable=True),
        sa.Column('duration_months', sa.Integer, nullable=True),

        # Termination and renewal
        sa.Column('notice_period_days', sa.Integer, default=30),
        sa.Column('notice_deadline', sa.Date, nullable=True),
        sa.Column('auto_renewal', sa.Boolean, default=False),
        sa.Column('renewal_period_months', sa.Integer, nullable=True),
        sa.Column('max_renewals', sa.Integer, nullable=True),
        sa.Column('current_renewal_count', sa.Integer, default=0),

        # Financial terms
        sa.Column('total_value', sa.Numeric(15, 2), nullable=True),
        sa.Column('monthly_value', sa.Numeric(15, 2), nullable=True),
        sa.Column('currency', sa.String(3), default='EUR'),
        sa.Column('payment_terms', sa.String(255), nullable=True),

        # Price adjustments
        sa.Column('price_adjustment_clause', sa.Boolean, default=False),
        sa.Column('price_adjustment_index', sa.String(100), nullable=True),
        sa.Column('price_adjustment_date', sa.Date, nullable=True),
        sa.Column('price_adjustment_percent', sa.Numeric(5, 2), nullable=True),

        # Legal terms
        sa.Column('governing_law', sa.String(100), default='Deutsches Recht'),
        sa.Column('jurisdiction', sa.String(255), nullable=True),
        sa.Column('arbitration_clause', sa.Boolean, default=False),

        # Document reference
        sa.Column('document_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('documents.id'), nullable=True),

        # Status and workflow
        sa.Column('status', postgresql.ENUM(
            'draft', 'pending_signature', 'active', 'suspended',
            'expiring_soon', 'expired', 'terminated', 'renewed',
            name='contractstatus', create_type=False
        ), default='draft'),
        sa.Column('signed_date', sa.Date, nullable=True),
        sa.Column('terminated_date', sa.Date, nullable=True),
        sa.Column('termination_reason', sa.Text, nullable=True),

        # Notifications
        sa.Column('reminder_days', postgresql.JSONB, default=[90, 60, 30, 14, 7]),
        sa.Column('last_reminder_sent', sa.Date, nullable=True),
        sa.Column('notification_emails', postgresql.JSONB, default=[]),

        # Metadata
        sa.Column('tags', postgresql.JSONB, default=[]),
        sa.Column('metadata', postgresql.JSONB, default={}),
        sa.Column('key_contacts', postgresql.JSONB, default=[]),
        sa.Column('notes', sa.Text, nullable=True),

        # Audit
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()')),
        sa.Column('created_by_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=True),
    )

    # Create unique constraint on company + contract_number
    op.create_unique_constraint(
        'uq_contract_number',
        'business_contracts',
        ['company_id', 'contract_number']
    )

    # Create indexes for business_contracts
    op.create_index('ix_contract_company', 'business_contracts', ['company_id'])
    op.create_index('ix_contract_status', 'business_contracts', ['status'])
    op.create_index('ix_contract_end_date', 'business_contracts', ['end_date'])
    op.create_index('ix_contract_notice_deadline', 'business_contracts', ['notice_deadline'])
    op.create_index('ix_contract_party_a', 'business_contracts', ['party_a_id'])
    op.create_index('ix_contract_party_b', 'business_contracts', ['party_b_id'])

    # Create contract_milestones table
    op.create_table(
        'contract_milestones',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('contract_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('business_contracts.id', ondelete='CASCADE'), nullable=False),

        sa.Column('milestone_type', postgresql.ENUM(
            'contract_start', 'contract_end', 'renewal_option', 'notice_deadline',
            'price_adjustment', 'service_level_review', 'deliverable_due',
            'payment_due', 'audit', 'custom',
            name='milestonetype', create_type=False
        ), nullable=False),
        sa.Column('title', sa.String(255), nullable=False),
        sa.Column('description', sa.Text, nullable=True),
        sa.Column('scheduled_date', sa.Date, nullable=False),

        # Completion tracking
        sa.Column('is_completed', sa.Boolean, default=False),
        sa.Column('completed_date', sa.Date, nullable=True),
        sa.Column('completion_notes', sa.Text, nullable=True),

        # Notifications
        sa.Column('reminder_days_before', postgresql.JSONB, default=[14, 7, 1]),
        sa.Column('last_reminder_sent', sa.Date, nullable=True),

        # Linked task
        sa.Column('linked_task_id', postgresql.UUID(as_uuid=True), nullable=True),

        # Audit
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()')),
    )

    # Create indexes for milestones
    op.create_index('ix_milestone_contract', 'contract_milestones', ['contract_id'])
    op.create_index('ix_milestone_scheduled', 'contract_milestones', ['scheduled_date'])
    op.create_index('ix_milestone_type', 'contract_milestones', ['milestone_type'])

    # Create contract_renewal_options table
    op.create_table(
        'contract_renewal_options',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('contract_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('business_contracts.id', ondelete='CASCADE'), nullable=False),

        # Option details
        sa.Column('option_number', sa.Integer, nullable=False),
        sa.Column('renewal_duration_months', sa.Integer, nullable=False),

        # Pricing
        sa.Column('price_adjustment_type', sa.String(50), nullable=True),
        sa.Column('price_adjustment_value', sa.Numeric(10, 2), nullable=True),
        sa.Column('new_monthly_value', sa.Numeric(15, 2), nullable=True),

        # Deadlines
        sa.Column('exercise_deadline', sa.Date, nullable=False),
        sa.Column('renewal_start_date', sa.Date, nullable=False),
        sa.Column('notice_required_days', sa.Integer, default=30),

        # Status
        sa.Column('status', postgresql.ENUM(
            'available', 'pending', 'exercised', 'declined', 'expired',
            name='renewaloptionstatus', create_type=False
        ), default='available'),
        sa.Column('exercised_date', sa.Date, nullable=True),
        sa.Column('exercised_by_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('decision_notes', sa.Text, nullable=True),

        # Audit
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()')),
    )

    # Create unique constraint
    op.create_unique_constraint(
        'uq_contract_renewal_option',
        'contract_renewal_options',
        ['contract_id', 'option_number']
    )

    # Create indexes for renewal options
    op.create_index('ix_renewal_contract', 'contract_renewal_options', ['contract_id'])
    op.create_index('ix_renewal_deadline', 'contract_renewal_options', ['exercise_deadline'])
    op.create_index('ix_renewal_status', 'contract_renewal_options', ['status'])

    # Create contract_amendments table
    op.create_table(
        'contract_amendments',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('contract_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('business_contracts.id', ondelete='CASCADE'), nullable=False),

        # Amendment identification
        sa.Column('amendment_number', sa.Integer, nullable=False),
        sa.Column('title', sa.String(255), nullable=False),
        sa.Column('amendment_date', sa.Date, nullable=False),
        sa.Column('effective_date', sa.Date, nullable=False),

        # Changes
        sa.Column('changes_summary', sa.Text, nullable=False),
        sa.Column('affected_clauses', postgresql.JSONB, default=[]),
        sa.Column('changes_detail', postgresql.JSONB, default={}),

        # Financial impact
        sa.Column('value_change', sa.Numeric(15, 2), nullable=True),
        sa.Column('new_total_value', sa.Numeric(15, 2), nullable=True),

        # Document
        sa.Column('document_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('documents.id'), nullable=True),

        # Status
        sa.Column('status', postgresql.ENUM(
            'draft', 'pending_approval', 'approved', 'rejected', 'superseded',
            name='amendmentstatus', create_type=False
        ), default='draft'),
        sa.Column('approved_by_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('approved_date', sa.Date, nullable=True),

        # Audit
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()')),
        sa.Column('created_by_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=True),
    )

    # Create unique constraint
    op.create_unique_constraint(
        'uq_contract_amendment_number',
        'contract_amendments',
        ['contract_id', 'amendment_number']
    )

    # Create indexes for amendments
    op.create_index('ix_amendment_contract', 'contract_amendments', ['contract_id'])
    op.create_index('ix_amendment_status', 'contract_amendments', ['status'])
    op.create_index('ix_amendment_effective', 'contract_amendments', ['effective_date'])


def downgrade() -> None:
    # Drop tables in reverse order (due to foreign keys)
    op.drop_table('contract_amendments')
    op.drop_table('contract_renewal_options')
    op.drop_table('contract_milestones')
    op.drop_table('business_contracts')

    # Drop enums
    op.execute('DROP TYPE IF EXISTS amendmentstatus')
    op.execute('DROP TYPE IF EXISTS milestonetype')
    op.execute('DROP TYPE IF EXISTS renewaloptionstatus')
    op.execute('DROP TYPE IF EXISTS contractstatus')
    op.execute('DROP TYPE IF EXISTS contracttype')
