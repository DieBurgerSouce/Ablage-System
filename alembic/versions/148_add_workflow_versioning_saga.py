# -*- coding: utf-8 -*-
"""Add Workflow Versioning and Saga Pattern tables.

Revision ID: 148
Revises: 147
Create Date: 2026-02-01

Implementiert:
- WorkflowVersion: Semantische Versionierung von Workflows
- WorkflowABTest: A/B Testing zwischen Versionen
- Saga: Saga-Orchestrierung fuer verteilte Transaktionen
- SagaStep: Einzelne Saga-Schritte mit Compensation
- SagaTransactionLog: Transaktionslog fuer Debugging
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "148"
down_revision = "147"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # =========================================================================
    # WorkflowVersion
    # =========================================================================
    op.create_table(
        "workflow_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "workflow_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workflows.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("version", sa.String(20), nullable=False),
        sa.Column("major", sa.Integer, nullable=False, default=1),
        sa.Column("minor", sa.Integer, nullable=False, default=0),
        sa.Column("patch", sa.Integer, nullable=False, default=0),
        sa.Column("status", sa.String(20), nullable=False, default="draft"),
        sa.Column("is_active", sa.Boolean, nullable=False, default=False),
        sa.Column("is_latest", sa.Boolean, nullable=False, default=True),
        sa.Column("definition", postgresql.JSONB, nullable=False),
        sa.Column("change_description", sa.Text, nullable=False),
        sa.Column("change_type", sa.String(20), nullable=False, default="minor"),
        sa.Column(
            "parent_version_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workflow_versions.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("diff_summary", postgresql.JSONB, nullable=True),
        sa.Column("execution_count", sa.Integer, nullable=False, default=0),
        sa.Column("success_count", sa.Integer, nullable=False, default=0),
        sa.Column("failure_count", sa.Integer, nullable=False, default=0),
        sa.Column("avg_execution_time_ms", sa.Integer, nullable=True),
        sa.Column("ab_test_weight", sa.Integer, nullable=False, default=100),
        sa.Column(
            "created_by_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deprecated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
    )

    # Constraints
    op.create_unique_constraint(
        "uq_workflow_version",
        "workflow_versions",
        ["workflow_id", "version"],
    )
    op.create_check_constraint(
        "ck_major_positive",
        "workflow_versions",
        "major >= 0",
    )
    op.create_check_constraint(
        "ck_minor_positive",
        "workflow_versions",
        "minor >= 0",
    )
    op.create_check_constraint(
        "ck_patch_positive",
        "workflow_versions",
        "patch >= 0",
    )
    op.create_check_constraint(
        "ck_ab_weight_range",
        "workflow_versions",
        "ab_test_weight >= 0 AND ab_test_weight <= 100",
    )

    # Indexes
    op.create_index(
        "ix_workflow_versions_workflow_id",
        "workflow_versions",
        ["workflow_id"],
    )
    op.create_index(
        "ix_workflow_versions_company_id",
        "workflow_versions",
        ["company_id"],
    )
    op.create_index(
        "ix_workflow_versions_status",
        "workflow_versions",
        ["status"],
    )
    op.create_index(
        "ix_workflow_versions_is_active",
        "workflow_versions",
        ["workflow_id", "is_active"],
    )
    op.create_index(
        "ix_workflow_versions_semver",
        "workflow_versions",
        ["workflow_id", "major", "minor", "patch"],
    )

    # =========================================================================
    # WorkflowABTest
    # =========================================================================
    op.create_table(
        "workflow_ab_tests",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "workflow_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workflows.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column(
            "control_version_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workflow_versions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "treatment_version_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workflow_versions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("treatment_percentage", sa.Integer, nullable=False, default=50),
        sa.Column("status", sa.String(20), nullable=False, default="draft"),
        sa.Column("start_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("end_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("control_executions", sa.Integer, nullable=False, default=0),
        sa.Column("control_successes", sa.Integer, nullable=False, default=0),
        sa.Column("control_failures", sa.Integer, nullable=False, default=0),
        sa.Column("control_avg_time_ms", sa.Integer, nullable=True),
        sa.Column("treatment_executions", sa.Integer, nullable=False, default=0),
        sa.Column("treatment_successes", sa.Integer, nullable=False, default=0),
        sa.Column("treatment_failures", sa.Integer, nullable=False, default=0),
        sa.Column("treatment_avg_time_ms", sa.Integer, nullable=True),
        sa.Column("winner", sa.String(20), nullable=True),
        sa.Column("statistical_significance", sa.Float, nullable=True),
        sa.Column("confidence_level", sa.Float, nullable=True),
        sa.Column(
            "created_by_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )

    # Constraints
    op.create_check_constraint(
        "ck_treatment_percentage_range",
        "workflow_ab_tests",
        "treatment_percentage >= 0 AND treatment_percentage <= 100",
    )

    # Indexes
    op.create_index(
        "ix_workflow_ab_tests_workflow_id",
        "workflow_ab_tests",
        ["workflow_id"],
    )
    op.create_index(
        "ix_workflow_ab_tests_company_id",
        "workflow_ab_tests",
        ["company_id"],
    )
    op.create_index(
        "ix_workflow_ab_tests_status",
        "workflow_ab_tests",
        ["status"],
    )
    op.create_index(
        "ix_workflow_ab_tests_dates",
        "workflow_ab_tests",
        ["start_at", "end_at"],
    )

    # =========================================================================
    # Saga
    # =========================================================================
    op.create_table(
        "sagas",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "execution_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workflow_executions.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("status", sa.String(30), nullable=False, default="pending"),
        sa.Column("current_step_index", sa.Integer, nullable=False, default=0),
        sa.Column("total_steps", sa.Integer, nullable=False, default=0),
        sa.Column("checkpoint_data", postgresql.JSONB, nullable=True),
        sa.Column("retry_count", sa.Integer, nullable=False, default=0),
        sa.Column("max_retries", sa.Integer, nullable=False, default=3),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("error_step_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("compensation_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("compensation_completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("steps_compensated", sa.Integer, nullable=False, default=0),
        sa.Column("in_dead_letter_queue", sa.Boolean, nullable=False, default=False),
        sa.Column("dead_letter_reason", sa.Text, nullable=True),
        sa.Column("dead_letter_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "initiated_by_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("context_data", postgresql.JSONB, nullable=False, default={}),
    )

    # Indexes
    op.create_index("ix_sagas_execution_id", "sagas", ["execution_id"])
    op.create_index("ix_sagas_company_id", "sagas", ["company_id"])
    op.create_index("ix_sagas_status", "sagas", ["status"])
    op.create_index("ix_sagas_dead_letter", "sagas", ["in_dead_letter_queue"])
    op.create_index("ix_sagas_created_at", "sagas", ["created_at"])

    # =========================================================================
    # SagaStep
    # =========================================================================
    op.create_table(
        "saga_steps",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "saga_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("sagas.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("step_order", sa.Integer, nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("action_type", sa.String(50), nullable=False),
        sa.Column("action_params", postgresql.JSONB, nullable=False, default={}),
        sa.Column("compensation_type", sa.String(50), nullable=True),
        sa.Column("compensation_params", postgresql.JSONB, nullable=True),
        sa.Column("has_compensation", sa.Boolean, nullable=False, default=True),
        sa.Column("status", sa.String(30), nullable=False, default="pending"),
        sa.Column("retry_count", sa.Integer, nullable=False, default=0),
        sa.Column("max_retries", sa.Integer, nullable=False, default=3),
        sa.Column("retry_delay_seconds", sa.Integer, nullable=False, default=60),
        sa.Column("idempotency_key", sa.String(64), nullable=True, unique=True),
        sa.Column("executed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("compensation_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("compensated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("result_data", postgresql.JSONB, nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("error_details", postgresql.JSONB, nullable=True),
        sa.Column("compensation_error", sa.Text, nullable=True),
        sa.Column("compensation_retry_count", sa.Integer, nullable=False, default=0),
        sa.Column("timeout_seconds", sa.Integer, nullable=False, default=300),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
    )

    # Constraints
    op.create_unique_constraint(
        "uq_saga_step_order",
        "saga_steps",
        ["saga_id", "step_order"],
    )

    # Indexes
    op.create_index("ix_saga_steps_saga_id", "saga_steps", ["saga_id"])
    op.create_index("ix_saga_steps_status", "saga_steps", ["status"])
    op.create_index("ix_saga_steps_idempotency", "saga_steps", ["idempotency_key"])

    # =========================================================================
    # SagaTransactionLog
    # =========================================================================
    op.create_table(
        "saga_transaction_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "saga_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("sagas.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "step_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("saga_steps.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("event_type", sa.String(50), nullable=False),
        sa.Column("previous_state", sa.String(30), nullable=True),
        sa.Column("new_state", sa.String(30), nullable=False),
        sa.Column("event_data", postgresql.JSONB, nullable=False, default={}),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("stack_trace", sa.Text, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    )

    # Indexes
    op.create_index("ix_saga_tx_logs_saga_id", "saga_transaction_logs", ["saga_id"])
    op.create_index("ix_saga_tx_logs_step_id", "saga_transaction_logs", ["step_id"])
    op.create_index("ix_saga_tx_logs_event_type", "saga_transaction_logs", ["event_type"])
    op.create_index("ix_saga_tx_logs_created_at", "saga_transaction_logs", ["created_at"])


def downgrade() -> None:
    # Drop tables in reverse order
    op.drop_table("saga_transaction_logs")
    op.drop_table("saga_steps")
    op.drop_table("sagas")
    op.drop_table("workflow_ab_tests")
    op.drop_table("workflow_versions")
