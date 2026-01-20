"""Add BPMN 2.0 Process Engine tables.

Revision ID: 106_add_bpmn_process_engine
Revises: 105_enhance_business_contacts
Create Date: 2026-01-19

Enterprise-Grade BPMN Process Engine mit:
- Process Definitions (Versionierung, BPMN XML)
- Process Instances (Laufende Workflows)
- Process Tasks (User Tasks, Service Tasks)
- Timer Jobs (Celery Integration)
- Process History (Audit Trail)
- Variable History (Debugging)
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "106_add_bpmn_process_engine"
down_revision = "105_enhance_business_contacts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ==========================================================================
    # Process Definitions
    # ==========================================================================
    op.create_table(
        "bpmn_process_definitions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("key", sa.String(255), nullable=False, index=True,
                  comment="Eindeutiger Prozess-Key"),
        sa.Column("name", sa.String(255), nullable=False,
                  comment="Anzeigename"),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, default=1),
        sa.Column("is_active", sa.Boolean(), nullable=False, default=True),
        sa.Column("bpmn_xml", sa.Text(), nullable=True,
                  comment="BPMN 2.0 XML"),
        sa.Column("process_data", postgresql.JSONB(), nullable=False,
                  server_default="{}",
                  comment="Parsed BPMN als JSONB"),
        sa.Column("category", sa.String(100), nullable=True, index=True),
        sa.Column("tags", postgresql.JSONB(), nullable=True,
                  server_default="[]"),
        sa.Column("deployed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deployed_by_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL"),
                  nullable=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("companies.id", ondelete="CASCADE"),
                  nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.UniqueConstraint("company_id", "key", "version",
                           name="uq_process_def_company_key_version"),
    )

    op.create_index(
        "ix_process_def_active",
        "bpmn_process_definitions",
        ["company_id", "key", "is_active"]
    )

    # ==========================================================================
    # Process Instances
    # ==========================================================================
    op.create_table(
        "bpmn_process_instances",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("definition_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("bpmn_process_definitions.id",
                                ondelete="RESTRICT"),
                  nullable=False, index=True),
        sa.Column("business_key", sa.String(255), nullable=True, index=True,
                  comment="Externer Schluessel"),
        sa.Column("status", sa.String(50), nullable=False, default="created",
                  index=True),
        sa.Column("variables", postgresql.JSONB(), nullable=False,
                  server_default="{}"),
        sa.Column("current_elements", postgresql.JSONB(), nullable=False,
                  server_default="[]"),
        sa.Column("started_by_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL"),
                  nullable=True, index=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("companies.id", ondelete="CASCADE"),
                  nullable=False, index=True),
        sa.Column("document_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("documents.id", ondelete="SET NULL"),
                  nullable=True, index=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), onupdate=sa.func.now()),
    )

    op.create_index(
        "ix_process_instance_status",
        "bpmn_process_instances",
        ["company_id", "status"]
    )

    op.create_index(
        "ix_process_instance_business_key",
        "bpmn_process_instances",
        ["company_id", "business_key"]
    )

    # ==========================================================================
    # Process Tasks
    # ==========================================================================
    op.create_table(
        "bpmn_process_tasks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("instance_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("bpmn_process_instances.id",
                                ondelete="CASCADE"),
                  nullable=False, index=True),
        sa.Column("element_id", sa.String(255), nullable=False),
        sa.Column("element_name", sa.String(255), nullable=True),
        sa.Column("task_type", sa.String(50), nullable=False,
                  default="user_task"),
        sa.Column("status", sa.String(50), nullable=False, default="pending",
                  index=True),
        sa.Column("assignee_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL"),
                  nullable=True, index=True),
        sa.Column("assignee_group", sa.String(255), nullable=True, index=True),
        sa.Column("delegated_from_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL"),
                  nullable=True),
        sa.Column("priority", sa.Integer(), nullable=False, default=50),
        sa.Column("due_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("follow_up_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("escalation_level", sa.Integer(), nullable=False, default=0),
        sa.Column("escalated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("form_key", sa.String(255), nullable=True),
        sa.Column("task_variables", postgresql.JSONB(), nullable=False,
                  server_default="{}"),
        sa.Column("company_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("companies.id", ondelete="CASCADE"),
                  nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now()),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), onupdate=sa.func.now()),
    )

    op.create_index(
        "ix_process_task_assignee",
        "bpmn_process_tasks",
        ["company_id", "assignee_id", "status"]
    )

    op.create_index(
        "ix_process_task_group",
        "bpmn_process_tasks",
        ["company_id", "assignee_group", "status"]
    )

    op.create_index(
        "ix_process_task_due",
        "bpmn_process_tasks",
        ["company_id", "due_date", "status"]
    )

    # ==========================================================================
    # Process History (Audit Trail)
    # ==========================================================================
    op.create_table(
        "bpmn_process_history",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("instance_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("bpmn_process_instances.id",
                                ondelete="CASCADE"),
                  nullable=False, index=True),
        sa.Column("task_id", postgresql.UUID(as_uuid=True), nullable=True,
                  index=True),
        sa.Column("event_type", sa.String(100), nullable=False, index=True),
        sa.Column("element_id", sa.String(255), nullable=True),
        sa.Column("element_type", sa.String(50), nullable=True),
        sa.Column("old_value", postgresql.JSONB(), nullable=True),
        sa.Column("new_value", postgresql.JSONB(), nullable=True),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL"),
                  nullable=True),
        sa.Column("actor_type", sa.String(50), nullable=False, default="user"),
        sa.Column("company_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("companies.id", ondelete="CASCADE"),
                  nullable=False, index=True),
        sa.Column("timestamp", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), index=True),
    )

    op.create_index(
        "ix_process_history_time",
        "bpmn_process_history",
        ["company_id", "instance_id", "timestamp"]
    )

    # ==========================================================================
    # Timer Jobs (Celery Integration)
    # ==========================================================================
    op.create_table(
        "bpmn_timer_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("instance_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("bpmn_process_instances.id",
                                ondelete="CASCADE"),
                  nullable=False, index=True),
        sa.Column("task_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("element_id", sa.String(255), nullable=False),
        sa.Column("timer_type", sa.String(50), nullable=False),
        sa.Column("timer_value", sa.String(255), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False,
                  index=True),
        sa.Column("repeat_count", sa.Integer(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, default=True),
        sa.Column("last_executed_at", sa.DateTime(timezone=True),
                  nullable=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("companies.id", ondelete="CASCADE"),
                  nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now()),
    )

    op.create_index(
        "ix_timer_job_due",
        "bpmn_timer_jobs",
        ["company_id", "due_at", "is_active"]
    )

    # ==========================================================================
    # Variable History (Debugging)
    # ==========================================================================
    op.create_table(
        "bpmn_variable_history",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("instance_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("bpmn_process_instances.id",
                                ondelete="CASCADE"),
                  nullable=False, index=True),
        sa.Column("variable_name", sa.String(255), nullable=False),
        sa.Column("old_value", postgresql.JSONB(), nullable=True),
        sa.Column("new_value", postgresql.JSONB(), nullable=True),
        sa.Column("element_id", sa.String(255), nullable=True),
        sa.Column("changed_by_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL"),
                  nullable=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("companies.id", ondelete="CASCADE"),
                  nullable=False, index=True),
        sa.Column("timestamp", sa.DateTime(timezone=True),
                  server_default=sa.func.now()),
    )

    op.create_index(
        "ix_var_history_instance",
        "bpmn_variable_history",
        ["instance_id", "variable_name", "timestamp"]
    )


def downgrade() -> None:
    op.drop_table("bpmn_variable_history")
    op.drop_table("bpmn_timer_jobs")
    op.drop_table("bpmn_process_history")
    op.drop_table("bpmn_process_tasks")
    op.drop_table("bpmn_process_instances")
    op.drop_table("bpmn_process_definitions")
