"""Add workflow SLA monitoring and parallel approvals.

Revision ID: 150_workflow_sla
Revises: 149
Create Date: 2026-02-01

Phase 4: Workflow Extensions mit:
- SLA Tracking (workflow_sla Tabelle)
- Parallel Approvals (parallel_approvals Tabelle)
- Indexes fuer Performance
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = '150_workflow_sla'
down_revision = '148'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create workflow SLA monitoring and parallel approvals tables."""

    # ==========================================================================
    # Workflow SLA Table
    # ==========================================================================

    op.create_table(
        'workflow_sla',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('gen_random_uuid()')),

        # Referenzen
        sa.Column('instance_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('bpmn_process_instances.id', ondelete='CASCADE'),
                  nullable=False, index=True),
        sa.Column('definition_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('bpmn_process_definitions.id', ondelete='CASCADE'),
                  nullable=False, index=True),

        # SLA Konfiguration
        sa.Column('max_duration_hours', sa.Integer, nullable=False),
        sa.Column('start_time', sa.DateTime(timezone=True), nullable=False),
        sa.Column('deadline', sa.DateTime(timezone=True), nullable=False),

        # Status
        sa.Column('status', sa.String(30), nullable=False, default='on_track',
                  comment='on_track, warning, at_risk, critical, breached'),
        sa.Column('current_alert_level', sa.String(30), nullable=True,
                  comment='info_50, warning_75, high_90, critical_100'),

        # Alerts
        sa.Column('alerts_sent', postgresql.JSONB, nullable=False,
                  server_default='[]',
                  comment='Liste der gesendeten Alert-Typen'),

        # Completion
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('was_on_time', sa.Boolean, nullable=True),
        sa.Column('actual_duration_hours', sa.Float, nullable=True),
        sa.Column('breach_by_hours', sa.Float, nullable=True),

        # Escalation
        sa.Column('escalated', sa.Boolean, nullable=False, default=False),
        sa.Column('escalated_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('escalation_user_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('users.id', ondelete='SET NULL'),
                  nullable=True),

        # Multi-Tenant
        sa.Column('company_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('companies.id', ondelete='CASCADE'),
                  nullable=False, index=True),

        # Timestamps
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True),
                  server_default=sa.func.now(), onupdate=sa.func.now()),

        # Constraints
        sa.CheckConstraint(
            "status IN ('on_track', 'warning', 'at_risk', 'critical', 'breached')",
            name='ck_workflow_sla_status'
        ),
    )

    # Indexes fuer workflow_sla
    op.create_index(
        'ix_workflow_sla_company_status',
        'workflow_sla',
        ['company_id', 'status']
    )
    op.create_index(
        'ix_workflow_sla_deadline',
        'workflow_sla',
        ['deadline']
    )
    op.create_index(
        'ix_workflow_sla_instance_active',
        'workflow_sla',
        ['instance_id'],
        postgresql_where=sa.text("completed_at IS NULL")
    )

    # ==========================================================================
    # Parallel Approvals Table
    # ==========================================================================

    op.create_table(
        'parallel_approvals',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('gen_random_uuid()')),

        # Referenz zur Workflow-Instanz
        sa.Column('instance_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('bpmn_process_instances.id', ondelete='CASCADE'),
                  nullable=False, index=True),

        # Identifikation
        sa.Column('approval_key', sa.String(100), nullable=False,
                  comment='Eindeutiger Key fuer diese Genehmigung'),
        sa.Column('element_id', sa.String(255), nullable=False,
                  comment='BPMN Element-ID'),

        # Konfiguration
        sa.Column('title', sa.String(255), nullable=False),
        sa.Column('description', sa.Text, nullable=True),
        sa.Column('consensus_type', sa.String(30), nullable=False, default='all',
                  comment='all, majority, any, unanimous, quorum'),
        sa.Column('quorum_count', sa.Integer, nullable=True,
                  comment='Mindestanzahl bei quorum-Typ'),

        # Genehmiger und Votes
        sa.Column('approvers', postgresql.JSONB, nullable=False,
                  comment='Liste der Genehmiger-User-IDs'),
        sa.Column('votes', postgresql.JSONB, nullable=False, server_default='{}',
                  comment='Dict: user_id -> {decision, comment, voted_at}'),

        # Status
        sa.Column('status', sa.String(30), nullable=False, default='pending',
                  comment='pending, approved, rejected, cancelled, expired'),
        sa.Column('final_decision', sa.String(30), nullable=True,
                  comment='approved, rejected'),

        # Timing
        sa.Column('due_date', sa.DateTime(timezone=True), nullable=True),
        sa.Column('consensus_reached_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('cancelled_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('cancellation_reason', sa.Text, nullable=True),

        # Initiator
        sa.Column('created_by_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('users.id', ondelete='SET NULL'),
                  nullable=True),

        # Multi-Tenant
        sa.Column('company_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('companies.id', ondelete='CASCADE'),
                  nullable=False, index=True),

        # Timestamps
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True),
                  server_default=sa.func.now(), onupdate=sa.func.now()),

        # Constraints
        sa.CheckConstraint(
            "consensus_type IN ('all', 'majority', 'any', 'unanimous', 'quorum')",
            name='ck_parallel_approvals_consensus_type'
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'approved', 'rejected', 'cancelled', 'expired')",
            name='ck_parallel_approvals_status'
        ),
        sa.UniqueConstraint('instance_id', 'approval_key',
                            name='uq_parallel_approval_instance_key'),
    )

    # Indexes fuer parallel_approvals
    op.create_index(
        'ix_parallel_approvals_company_status',
        'parallel_approvals',
        ['company_id', 'status']
    )
    op.create_index(
        'ix_parallel_approvals_due_date',
        'parallel_approvals',
        ['due_date'],
        postgresql_where=sa.text("status = 'pending'")
    )

    # GIN Index fuer JSONB approvers Suche
    op.execute("""
        CREATE INDEX ix_parallel_approvals_approvers
        ON parallel_approvals
        USING GIN (approvers jsonb_path_ops)
    """)

    # ==========================================================================
    # SLA Definition Table (fuer persistente SLA-Konfigurationen)
    # ==========================================================================

    op.create_table(
        'workflow_sla_definitions',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('gen_random_uuid()')),

        # Workflow-Typ
        sa.Column('workflow_key', sa.String(255), nullable=False),
        sa.Column('workflow_name', sa.String(255), nullable=True),

        # SLA Konfiguration
        sa.Column('max_duration_hours', sa.Integer, nullable=False),
        sa.Column('description', sa.Text, nullable=True),

        # Escalation
        sa.Column('escalation_user_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('users.id', ondelete='SET NULL'),
                  nullable=True),
        sa.Column('escalation_role', sa.String(100), nullable=True),

        # Alert Thresholds (optional custom)
        sa.Column('alert_thresholds', postgresql.JSONB, nullable=True,
                  comment='Custom alert thresholds: [{percent, level, severity}]'),

        # Status
        sa.Column('is_active', sa.Boolean, nullable=False, default=True),

        # Multi-Tenant
        sa.Column('company_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('companies.id', ondelete='CASCADE'),
                  nullable=False, index=True),

        # Timestamps
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True),
                  server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.Column('created_by_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('users.id', ondelete='SET NULL'),
                  nullable=True),

        # Unique per Company
        sa.UniqueConstraint('company_id', 'workflow_key',
                            name='uq_sla_definition_company_workflow'),
    )

    op.create_index(
        'ix_sla_definitions_company_active',
        'workflow_sla_definitions',
        ['company_id', 'is_active']
    )

    # ==========================================================================
    # Workflow Analytics View (fuer schnelle Dashboards)
    # ==========================================================================

    op.execute("""
        CREATE OR REPLACE VIEW v_workflow_sla_summary AS
        SELECT
            ws.company_id,
            pd.key as workflow_key,
            pd.name as workflow_name,
            COUNT(*) as total_instances,
            COUNT(*) FILTER (WHERE ws.was_on_time = true) as on_time_count,
            COUNT(*) FILTER (WHERE ws.was_on_time = false) as breached_count,
            COUNT(*) FILTER (WHERE ws.completed_at IS NULL) as active_count,
            ROUND(
                COUNT(*) FILTER (WHERE ws.was_on_time = true)::numeric /
                NULLIF(COUNT(*) FILTER (WHERE ws.completed_at IS NOT NULL), 0) * 100,
                2
            ) as compliance_rate,
            ROUND(AVG(ws.actual_duration_hours)::numeric, 2) as avg_duration_hours,
            ROUND(AVG(ws.breach_by_hours) FILTER (WHERE ws.was_on_time = false)::numeric, 2) as avg_breach_hours
        FROM workflow_sla ws
        JOIN bpmn_process_instances pi ON ws.instance_id = pi.id
        JOIN bpmn_process_definitions pd ON pi.definition_id = pd.id
        GROUP BY ws.company_id, pd.key, pd.name
    """)


def downgrade() -> None:
    """Remove workflow SLA monitoring and parallel approvals tables."""

    # Drop view
    op.execute("DROP VIEW IF EXISTS v_workflow_sla_summary")

    # Drop tables in reverse order
    op.drop_table('workflow_sla_definitions')
    op.drop_table('parallel_approvals')
    op.drop_table('workflow_sla')
