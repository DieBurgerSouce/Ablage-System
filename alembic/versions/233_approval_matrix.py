"""Approval Matrix Models.

Revision ID: 233
Revises: 232
Create Date: 2026-02-16

Adds:
- approval_chain_templates: Wiederverwendbare Genehmigungsketten
- approval_matrices: Betrags-/Abteilungsbasierte Matrix
- approval_audit_logs: Unveraenderliches Audit-Protokoll
- approval_groups: Gruppenbasierte Genehmigungen
- approval_group_members: Gruppenmitgliedschaften
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = "233"
down_revision = "232"
branch_labels = None
depends_on = None

def upgrade() -> None:
    # Create approval_chain_templates first (referenced by approval_matrices)
    op.create_table(
        "approval_chain_templates",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", UUID(as_uuid=True), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("steps_config", JSONB, nullable=False, server_default="[]"),
        sa.Column("is_default", sa.Boolean, default=False),
        sa.Column("is_active", sa.Boolean, default=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("created_by_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.UniqueConstraint("company_id", "name", name="uq_chain_template_company_name"),
    )

    # Create approval_matrices
    op.create_table(
        "approval_matrices",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", UUID(as_uuid=True), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("department", sa.String(100), nullable=False),
        sa.Column("document_type", sa.String(50), nullable=True),
        sa.Column("amount_min", sa.Numeric(15, 2), nullable=False, server_default="0"),
        sa.Column("amount_max", sa.Numeric(15, 2), nullable=True),
        sa.Column("chain_template_id", UUID(as_uuid=True), sa.ForeignKey("approval_chain_templates.id", ondelete="SET NULL"), nullable=True),
        sa.Column("four_eyes_required", sa.Boolean, default=False),
        sa.Column("min_approvers", sa.Integer, default=1),
        sa.Column("priority", sa.Integer, default=0),
        sa.Column("is_active", sa.Boolean, default=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("created_by_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
    )
    op.create_index("ix_approval_matrices_company_dept", "approval_matrices", ["company_id", "department"])
    op.create_index("ix_approval_matrices_company_amount", "approval_matrices", ["company_id", "amount_min", "amount_max"])

    # Create approval_audit_logs
    op.create_table(
        "approval_audit_logs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", UUID(as_uuid=True), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("request_id", UUID(as_uuid=True), sa.ForeignKey("approval_requests.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("step_id", UUID(as_uuid=True), sa.ForeignKey("approval_steps.id", ondelete="SET NULL"), nullable=True),
        sa.Column("actor_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("action_type", sa.String(50), nullable=False),
        sa.Column("old_status", sa.String(50), nullable=True),
        sa.Column("new_status", sa.String(50), nullable=False),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("metadata_json", JSONB, nullable=True),
        sa.Column("ip_address", sa.String(45), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_audit_log_request_created", "approval_audit_logs", ["request_id", "created_at"])
    op.create_index("ix_audit_log_company_created", "approval_audit_logs", ["company_id", "created_at"])

    # Create approval_groups
    op.create_table(
        "approval_groups",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", UUID(as_uuid=True), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("decision_mode", sa.String(50), default="any"),
        sa.Column("is_active", sa.Boolean, default=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("company_id", "name", name="uq_approval_group_company_name"),
    )

    # Create approval_group_members
    op.create_table(
        "approval_group_members",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("group_id", UUID(as_uuid=True), sa.ForeignKey("approval_groups.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("can_approve", sa.Boolean, default=True),
        sa.Column("can_reject", sa.Boolean, default=True),
        sa.Column("is_backup", sa.Boolean, default=False),
        sa.Column("added_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("added_by_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.UniqueConstraint("group_id", "user_id", name="uq_group_member"),
    )

def downgrade() -> None:
    op.drop_table("approval_group_members")
    op.drop_table("approval_groups")
    op.drop_index("ix_audit_log_company_created", table_name="approval_audit_logs")
    op.drop_index("ix_audit_log_request_created", table_name="approval_audit_logs")
    op.drop_table("approval_audit_logs")
    op.drop_index("ix_approval_matrices_company_amount", table_name="approval_matrices")
    op.drop_index("ix_approval_matrices_company_dept", table_name="approval_matrices")
    op.drop_table("approval_matrices")
    op.drop_table("approval_chain_templates")
