"""Add Approval System tables for Enterprise workflows.

Revision ID: 086_add_approval_system
Revises: 085_add_portfolio_financial_goals
Create Date: 2026-01-09

Enterprise Features - APPROVAL SYSTEM:
- ApprovalRule: Regeln fuer automatisches Approval-Routing
- ApprovalRequest: Genehmigungsanfragen mit Multi-Step Chain
- ApprovalStep: Einzelne Schritte im Genehmigungsprozess
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

# revision identifiers
revision = '086'
down_revision = '085'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ==================================================
    # ApprovalRule - Regeln fuer automatisches Routing
    # ==================================================
    op.create_table(
        'approval_rules',
        sa.Column('id', UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('gen_random_uuid()')),
        sa.Column('company_id', UUID(as_uuid=True),
                  sa.ForeignKey('companies.id', ondelete='CASCADE'),
                  nullable=False),

        # Regel-Definition
        sa.Column('name', sa.String(200), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('rule_type', sa.String(30), nullable=False,
                  comment='amount_threshold, category, supplier, cost_center, document_type, risk_level, custom'),

        # Entity-Typen
        sa.Column('entity_types', JSONB, nullable=False, server_default='[]',
                  comment='Entity-Typen auf die Regel angewendet wird'),

        # Bedingungen
        sa.Column('conditions', JSONB, nullable=False, server_default='{}',
                  comment='Bedingungen als JSON'),

        # Approval Chain
        sa.Column('approval_chain', JSONB, nullable=False, server_default='[]',
                  comment='Genehmiger-Chain als JSON Array'),

        # Eskalation
        sa.Column('escalation_after_hours', sa.Integer(), nullable=True,
                  comment='Eskalation nach X Stunden'),
        sa.Column('escalation_to_role', sa.String(50), nullable=True,
                  comment='Eskalation an diese Rolle'),

        # SLA
        sa.Column('sla_hours', sa.Integer(), nullable=True, server_default='48',
                  comment='Max. Bearbeitungszeit in Stunden'),

        # Prioritaet
        sa.Column('priority', sa.Integer(), nullable=False, server_default='100',
                  comment='Niedrig = Hoehere Prioritaet'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),

        # Audit
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text('NOW()')),
        sa.Column('created_by_id', UUID(as_uuid=True),
                  sa.ForeignKey('users.id', ondelete='SET NULL'),
                  nullable=True),

        comment='Regeln fuer automatisches Approval-Routing'
    )

    # Indices fuer ApprovalRule
    op.create_index('ix_approval_rules_company_id', 'approval_rules', ['company_id'])
    op.create_index('ix_approval_rules_rule_type', 'approval_rules', ['rule_type'])
    op.create_index('ix_approval_rules_company_active', 'approval_rules',
                    ['company_id', 'is_active'])
    op.create_index('ix_approval_rules_priority', 'approval_rules', ['priority'])

    # ==================================================
    # ApprovalRequest - Genehmigungsanfragen
    # ==================================================
    op.create_table(
        'approval_requests',
        sa.Column('id', UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('gen_random_uuid()')),
        sa.Column('company_id', UUID(as_uuid=True),
                  sa.ForeignKey('companies.id', ondelete='CASCADE'),
                  nullable=False),

        # Entitaet
        sa.Column('entity_type', sa.String(50), nullable=False,
                  comment='invoice, expense, document, purchase_order, contract'),
        sa.Column('entity_id', UUID(as_uuid=True), nullable=False),

        # Verknuepfungen
        sa.Column('workflow_execution_id', UUID(as_uuid=True),
                  sa.ForeignKey('workflow_executions.id', ondelete='SET NULL'),
                  nullable=True),
        sa.Column('triggered_by_rule_id', UUID(as_uuid=True),
                  sa.ForeignKey('approval_rules.id', ondelete='SET NULL'),
                  nullable=True),

        # Anfrage-Details
        sa.Column('title', sa.String(255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('amount', sa.Numeric(14, 2), nullable=True,
                  comment='Betrag falls relevant'),
        sa.Column('currency', sa.String(3), nullable=False, server_default='EUR'),

        # Status
        sa.Column('status', sa.String(20), nullable=False, server_default='pending',
                  comment='pending, approved, rejected, escalated, expired, cancelled'),
        sa.Column('priority', sa.String(20), nullable=False, server_default='normal',
                  comment='low, normal, high, urgent'),

        # Fortschritt
        sa.Column('current_step', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('total_steps', sa.Integer(), nullable=False),
        sa.Column('approval_chain', JSONB, nullable=False, server_default='[]',
                  comment='Kopie der Chain bei Erstellung'),

        # Timing
        sa.Column('due_date', sa.DateTime(timezone=True), nullable=True),
        sa.Column('escalation_date', sa.DateTime(timezone=True), nullable=True),
        sa.Column('is_escalated', sa.Boolean(), nullable=False, server_default='false'),

        # Ergebnis
        sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('resolved_by_id', UUID(as_uuid=True),
                  sa.ForeignKey('users.id', ondelete='SET NULL'),
                  nullable=True),
        sa.Column('resolution_notes', sa.Text(), nullable=True),

        # Ersteller
        sa.Column('requested_by_id', UUID(as_uuid=True),
                  sa.ForeignKey('users.id', ondelete='SET NULL'),
                  nullable=True),

        # Metadata
        sa.Column('metadata', JSONB, nullable=True),

        # Audit
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text('NOW()')),

        comment='Genehmigungsanfragen mit Multi-Step Chain'
    )

    # Indices fuer ApprovalRequest
    op.create_index('ix_approval_requests_company_id', 'approval_requests', ['company_id'])
    op.create_index('ix_approval_requests_entity_type', 'approval_requests', ['entity_type'])
    op.create_index('ix_approval_requests_entity_id', 'approval_requests', ['entity_id'])
    op.create_index('ix_approval_requests_entity', 'approval_requests',
                    ['entity_type', 'entity_id'])
    op.create_index('ix_approval_requests_status', 'approval_requests',
                    ['company_id', 'status'])
    op.create_index('ix_approval_requests_due', 'approval_requests', ['due_date'])
    op.create_index('ix_approval_requests_priority', 'approval_requests', ['priority'])

    # ==================================================
    # ApprovalStep - Einzelne Schritte
    # ==================================================
    op.create_table(
        'approval_steps',
        sa.Column('id', UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('gen_random_uuid()')),
        sa.Column('approval_request_id', UUID(as_uuid=True),
                  sa.ForeignKey('approval_requests.id', ondelete='CASCADE'),
                  nullable=False),

        # Schritt
        sa.Column('step_number', sa.Integer(), nullable=False),

        # Genehmiger
        sa.Column('approver_type', sa.String(20), nullable=False,
                  comment='user, role, group'),
        sa.Column('approver_value', sa.String(255), nullable=False,
                  comment='User-ID, Rollenname, etc.'),
        sa.Column('assigned_user_id', UUID(as_uuid=True),
                  sa.ForeignKey('users.id', ondelete='SET NULL'),
                  nullable=True),

        # Status
        sa.Column('status', sa.String(20), nullable=False, server_default='pending',
                  comment='pending, approved, rejected, escalated, expired, cancelled'),
        sa.Column('is_required', sa.Boolean(), nullable=False, server_default='true'),

        # Entscheidung
        sa.Column('decision', sa.String(20), nullable=True,
                  comment='approved, rejected'),
        sa.Column('decision_date', sa.DateTime(timezone=True), nullable=True),
        sa.Column('decision_by_id', UUID(as_uuid=True),
                  sa.ForeignKey('users.id', ondelete='SET NULL'),
                  nullable=True),
        sa.Column('decision_notes', sa.Text(), nullable=True),

        # Delegation
        sa.Column('delegated_to_id', UUID(as_uuid=True),
                  sa.ForeignKey('users.id', ondelete='SET NULL'),
                  nullable=True),
        sa.Column('delegated_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('delegation_reason', sa.Text(), nullable=True),

        # Erinnerungen
        sa.Column('reminder_sent_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('last_reminder_at', sa.DateTime(timezone=True), nullable=True),

        # Audit
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text('NOW()')),

        comment='Einzelne Schritte im Genehmigungsprozess'
    )

    # Indices fuer ApprovalStep
    op.create_index('ix_approval_steps_request_id', 'approval_steps', ['approval_request_id'])
    op.create_index('ix_approval_steps_request_number', 'approval_steps',
                    ['approval_request_id', 'step_number'])
    op.create_index('ix_approval_steps_assigned', 'approval_steps',
                    ['assigned_user_id', 'status'])
    op.create_index('ix_approval_steps_status', 'approval_steps', ['status'])


def downgrade() -> None:
    # Drop tables in reverse order (dependencies first)
    op.drop_table('approval_steps')
    op.drop_table('approval_requests')
    op.drop_table('approval_rules')
