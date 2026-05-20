"""Erstelle 32 neue Tabellen fuer das Next-Generation Feature-Release.

Umfasst folgende Feature-Bereiche:
- Proactive Assistant: proactive_hints, hint_rules, hint_statistics
- Smart Dashboard: smart_dashboard_configs, dashboard_kpis, smart_dashboard_widgets,
  smart_dashboard_layouts, document_progress_trackers, batch_progress_trackers
- Approval Workflow Depth: conditional_approval_rules, escalation_rules,
  substitution_rules, approval_sla_metrics
- Automation 2.0: auto_filing_rules, auto_match_results
- KI-Pipeline Intelligence: extraction_confidences, learning_profiles,
  cross_document_matches, document_summaries
- Annotations & German Precision: comment_replies, bounding_box_annotations,
  comment_tasks
- Deutsche Finanz-Features: ust_voranmeldungen, bwa_reports, cashflow_forecasts
- Ad-Hoc Reporting: adhoc_reports, scheduled_reports, adhoc_report_execution_logs
- Ad-Hoc Reporting Extended: ad_hoc_reports, ad_hoc_report_executions,
  ad_hoc_report_shares, ad_hoc_report_schedules

Revision ID: 225_add_next_generation_features
Revises: 224_add_data_quality_history
Create Date: 2026-02-15
"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from alembic import op

revision: str = "225_add_next_generation_features"
down_revision: str = "224_add_data_quality_history"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ==========================================================================
    # Feature #1: Proactive Assistant
    # ==========================================================================

    # ------------------------------------------------------------------
    # Table 1: proactive_hints
    # ------------------------------------------------------------------
    op.create_table(
        "proactive_hints",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("category", sa.String(30), nullable=False, server_default="deadline"),
        sa.Column("priority", sa.String(20), nullable=False, server_default="medium"),
        sa.Column("status", sa.String(20), nullable=False, server_default="new"),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("urgency_score", sa.Float(), server_default="0.5"),
        sa.Column("value_score", sa.Float(), server_default="0.5"),
        sa.Column("combined_score", sa.Float(), server_default="0.25"),
        sa.Column("source_type", sa.String(100), nullable=False),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "source_metadata",
            postgresql.JSONB(),
            server_default="{}",
        ),
        sa.Column("action_url", sa.String(500), nullable=True),
        sa.Column("action_label", sa.String(200), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("dismissed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "category IN ('deadline', 'anomaly', 'optimization')",
            name="ck_proactive_hints_category",
        ),
        sa.CheckConstraint(
            "priority IN ('low', 'medium', 'high', 'critical')",
            name="ck_proactive_hints_priority",
        ),
        sa.CheckConstraint(
            "status IN ('new', 'seen', 'acknowledged', 'dismissed', 'acted_on')",
            name="ck_proactive_hints_status",
        ),
        sa.CheckConstraint(
            "urgency_score >= 0.0 AND urgency_score <= 1.0",
            name="ck_proactive_hints_urgency_range",
        ),
        sa.CheckConstraint(
            "value_score >= 0.0 AND value_score <= 1.0",
            name="ck_proactive_hints_value_range",
        ),
    )

    op.create_index(
        "ix_proactive_hints_company_id",
        "proactive_hints",
        ["company_id"],
    )
    op.create_index(
        "ix_proactive_hints_user_id",
        "proactive_hints",
        ["user_id"],
    )
    op.create_index(
        "ix_proactive_hints_company_status",
        "proactive_hints",
        ["company_id", "status"],
    )
    op.create_index(
        "ix_proactive_hints_company_category_created",
        "proactive_hints",
        ["company_id", "category", "created_at"],
    )
    op.create_index(
        "ix_proactive_hints_expires_at",
        "proactive_hints",
        ["expires_at"],
    )
    op.create_index(
        "ix_proactive_hints_combined_score",
        "proactive_hints",
        ["combined_score"],
    )
    op.create_index(
        "ix_proactive_hints_source",
        "proactive_hints",
        ["source_type", "source_id"],
    )

    # ------------------------------------------------------------------
    # Table 2: hint_rules
    # ------------------------------------------------------------------
    op.create_table(
        "hint_rules",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("category", sa.String(30), nullable=False),
        sa.Column("source_type", sa.String(100), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true"),
        sa.Column(
            "threshold_config",
            postgresql.JSONB(),
            server_default="{}",
        ),
        sa.Column("schedule", sa.String(50), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
        ),
    )

    op.create_index(
        "ix_hint_rules_company_id",
        "hint_rules",
        ["company_id"],
    )
    op.create_index(
        "ix_hint_rules_company_active",
        "hint_rules",
        ["company_id", "is_active"],
    )

    # ------------------------------------------------------------------
    # Table 3: hint_statistics
    # ------------------------------------------------------------------
    op.create_table(
        "hint_statistics",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("total_hints", sa.Integer(), server_default="0"),
        sa.Column(
            "hints_by_category",
            postgresql.JSONB(),
            server_default="{}",
        ),
        sa.Column("action_rate", sa.Float(), server_default="0.0"),
        sa.Column("avg_response_time_hours", sa.Float(), server_default="0.0"),
        sa.Column("estimated_savings", sa.Float(), server_default="0.0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
        ),
    )

    op.create_index(
        "ix_hint_statistics_company_id",
        "hint_statistics",
        ["company_id"],
    )
    op.create_index(
        "ix_hint_statistics_company_period",
        "hint_statistics",
        ["company_id", "period_start", "period_end"],
    )

    # ==========================================================================
    # Feature #2+6: Smart Dashboard
    # ==========================================================================

    # ------------------------------------------------------------------
    # Table 4: smart_dashboard_configs
    # ------------------------------------------------------------------
    op.create_table(
        "smart_dashboard_configs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("active_tab", sa.String(20), nullable=False, server_default="overview"),
        sa.Column(
            "widget_layout",
            postgresql.JSONB(),
            server_default="{}",
        ),
        sa.Column("role_filter", sa.String(50), nullable=True),
        sa.Column("refresh_interval_seconds", sa.Integer(), nullable=False, server_default="30"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "active_tab IN ('overview', 'finance', 'documents', 'workflows', 'system')",
            name="ck_smart_dashboard_active_tab",
        ),
        sa.CheckConstraint(
            "refresh_interval_seconds >= 5 AND refresh_interval_seconds <= 300",
            name="ck_smart_dashboard_refresh_interval",
        ),
    )

    op.create_index(
        "ix_smart_dashboard_configs_company_id",
        "smart_dashboard_configs",
        ["company_id"],
    )
    op.create_index(
        "ix_smart_dashboard_configs_user_id",
        "smart_dashboard_configs",
        ["user_id"],
    )
    op.create_index(
        "ix_smart_dashboard_company_user",
        "smart_dashboard_configs",
        ["company_id", "user_id"],
    )

    # ------------------------------------------------------------------
    # Table 5: dashboard_kpis
    # ------------------------------------------------------------------
    op.create_table(
        "dashboard_kpis",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kpi_key", sa.String(100), nullable=False),
        sa.Column("current_value", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("previous_value", sa.Float(), nullable=True),
        sa.Column("unit", sa.String(20), nullable=False, server_default="count"),
        sa.Column("trend_direction", sa.String(10), nullable=False, server_default="stable"),
        sa.Column(
            "calculated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "kpi_metadata",
            postgresql.JSONB(),
            server_default="{}",
        ),
        sa.CheckConstraint(
            "trend_direction IN ('up', 'down', 'stable')",
            name="ck_dashboard_kpis_trend",
        ),
    )

    op.create_index(
        "ix_dashboard_kpis_company_id",
        "dashboard_kpis",
        ["company_id"],
    )
    op.create_index(
        "ix_dashboard_kpis_kpi_key",
        "dashboard_kpis",
        ["kpi_key"],
    )
    op.create_index(
        "ix_dashboard_kpis_company_key",
        "dashboard_kpis",
        ["company_id", "kpi_key"],
    )
    op.create_index(
        "ix_dashboard_kpis_calculated_at",
        "dashboard_kpis",
        ["calculated_at"],
    )

    # ------------------------------------------------------------------
    # Table 6: smart_dashboard_widgets
    # ------------------------------------------------------------------
    op.create_table(
        "smart_dashboard_widgets",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("tab", sa.String(30), nullable=False),
        sa.Column("widget_type", sa.String(100), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column(
            "config",
            postgresql.JSONB(),
            server_default="{}",
        ),
        sa.Column("position_x", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("position_y", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("position_w", sa.Integer(), nullable=False, server_default="4"),
        sa.Column("position_h", sa.Integer(), nullable=False, server_default="3"),
        sa.Column(
            "min_roles",
            postgresql.JSONB(),
            server_default="[]",
        ),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("refresh_interval_seconds", sa.Integer(), nullable=False, server_default="60"),
        sa.Column("data_source", sa.String(200), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    op.create_index(
        "ix_smart_dashboard_widgets_company_id",
        "smart_dashboard_widgets",
        ["company_id"],
    )
    op.create_index(
        "ix_smart_dashboard_widgets_tab",
        "smart_dashboard_widgets",
        ["tab"],
    )
    op.create_index(
        "ix_smart_widgets_company_tab",
        "smart_dashboard_widgets",
        ["company_id", "tab"],
    )
    op.create_index(
        "ix_smart_widgets_active",
        "smart_dashboard_widgets",
        ["company_id", "is_active"],
    )

    # ------------------------------------------------------------------
    # Table 7: smart_dashboard_layouts
    # ------------------------------------------------------------------
    op.create_table(
        "smart_dashboard_layouts",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("tab", sa.String(30), nullable=False),
        sa.Column(
            "widgets_config",
            postgresql.JSONB(),
            nullable=False,
            server_default="[]",
        ),
        sa.Column("is_custom", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    op.create_index(
        "ix_smart_dashboard_layouts_user_id",
        "smart_dashboard_layouts",
        ["user_id"],
    )
    op.create_index(
        "ix_smart_dashboard_layouts_company_id",
        "smart_dashboard_layouts",
        ["company_id"],
    )
    op.create_index(
        "ix_dashboard_layout_user_company",
        "smart_dashboard_layouts",
        ["user_id", "company_id"],
    )
    op.create_unique_constraint(
        "uq_dashboard_layout_user_tab",
        "smart_dashboard_layouts",
        ["user_id", "company_id", "tab"],
    )

    # ------------------------------------------------------------------
    # Table 8: document_progress_trackers
    # ------------------------------------------------------------------
    op.create_table(
        "document_progress_trackers",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "document_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("current_step", sa.String(100), nullable=False, server_default="hochgeladen"),
        sa.Column(
            "steps_completed",
            postgresql.JSONB(),
            server_default="[]",
        ),
        sa.Column("total_steps", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("progress_percent", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("estimated_completion", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
        ),
    )

    op.create_index(
        "ix_document_progress_trackers_company_id",
        "document_progress_trackers",
        ["company_id"],
    )
    op.create_index(
        "ix_doc_progress_company_step",
        "document_progress_trackers",
        ["company_id", "current_step"],
    )
    op.create_index(
        "ix_doc_progress_started_at",
        "document_progress_trackers",
        ["started_at"],
    )

    # ------------------------------------------------------------------
    # Table 9: batch_progress_trackers
    # ------------------------------------------------------------------
    op.create_table(
        "batch_progress_trackers",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "batch_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("total_documents", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("processed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("current_document_name", sa.String(500), nullable=True),
        sa.Column("progress_percent", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("estimated_remaining_seconds", sa.Integer(), nullable=True),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
        ),
    )

    op.create_index(
        "ix_batch_progress_trackers_company_id",
        "batch_progress_trackers",
        ["company_id"],
    )
    op.create_index(
        "ix_batch_progress_company",
        "batch_progress_trackers",
        ["company_id"],
    )

    # ==========================================================================
    # Feature #3: Approval Workflow Depth
    # ==========================================================================

    # ------------------------------------------------------------------
    # Table 10: conditional_approval_rules
    # ------------------------------------------------------------------
    op.create_table(
        "conditional_approval_rules",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column(
            "conditions",
            postgresql.JSONB(),
            nullable=False,
            server_default="[]",
        ),
        sa.Column(
            "additional_approvers",
            postgresql.JSONB(),
            nullable=False,
            server_default="[]",
        ),
        sa.Column("priority_override", sa.String(50), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    op.create_index(
        "ix_conditional_approval_rules_company_id",
        "conditional_approval_rules",
        ["company_id"],
    )
    op.create_index(
        "ix_conditional_approval_rules_is_active",
        "conditional_approval_rules",
        ["is_active"],
    )
    op.create_index(
        "ix_cond_approval_rules_company_active",
        "conditional_approval_rules",
        ["company_id", "is_active"],
    )

    # ------------------------------------------------------------------
    # Table 11: escalation_rules
    # ------------------------------------------------------------------
    op.create_table(
        "escalation_rules",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("timeout_hours", sa.Integer(), nullable=False, server_default="48"),
        sa.Column(
            "escalation_target_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("escalation_target_role", sa.String(100), nullable=True),
        sa.Column("send_email", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("send_notification", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    op.create_index(
        "ix_escalation_rules_company_id",
        "escalation_rules",
        ["company_id"],
    )
    op.create_index(
        "ix_escalation_rules_is_active",
        "escalation_rules",
        ["is_active"],
    )
    op.create_index(
        "ix_escalation_rules_company_active",
        "escalation_rules",
        ["company_id", "is_active"],
    )

    # ------------------------------------------------------------------
    # Table 12: substitution_rules
    # ------------------------------------------------------------------
    op.create_table(
        "substitution_rules",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "substitute_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reason", sa.String(200), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("auto_activated", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    op.create_index(
        "ix_substitution_rules_company_id",
        "substitution_rules",
        ["company_id"],
    )
    op.create_index(
        "ix_substitution_rules_user_id",
        "substitution_rules",
        ["user_id"],
    )
    op.create_index(
        "ix_substitution_rules_substitute_user_id",
        "substitution_rules",
        ["substitute_user_id"],
    )
    op.create_index(
        "ix_substitution_rules_user",
        "substitution_rules",
        ["user_id", "is_active"],
    )
    op.create_index(
        "ix_substitution_rules_substitute",
        "substitution_rules",
        ["substitute_user_id", "is_active"],
    )
    op.create_index(
        "ix_substitution_rules_period",
        "substitution_rules",
        ["valid_from", "valid_until"],
    )
    op.create_index(
        "ix_substitution_rules_is_active",
        "substitution_rules",
        ["is_active"],
    )

    # ------------------------------------------------------------------
    # Table 13: approval_sla_metrics
    # ------------------------------------------------------------------
    op.create_table(
        "approval_sla_metrics",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "approval_request_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("approval_requests.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("step_number", sa.Integer(), nullable=False),
        sa.Column("assigned_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sla_target_hours", sa.Float(), nullable=False),
        sa.Column("is_breached", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("breached_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    op.create_index(
        "ix_approval_sla_metrics_company_id",
        "approval_sla_metrics",
        ["company_id"],
    )
    op.create_index(
        "ix_approval_sla_metrics_approval_request_id",
        "approval_sla_metrics",
        ["approval_request_id"],
    )
    op.create_index(
        "ix_sla_metrics_request_step",
        "approval_sla_metrics",
        ["approval_request_id", "step_number"],
    )
    op.create_index(
        "ix_sla_metrics_breached",
        "approval_sla_metrics",
        ["company_id", "is_breached"],
    )
    op.create_index(
        "ix_approval_sla_metrics_is_breached",
        "approval_sla_metrics",
        ["is_breached"],
    )

    # ==========================================================================
    # Feature #7: Automation 2.0
    # ==========================================================================

    # ------------------------------------------------------------------
    # Table 14: auto_filing_rules
    # ------------------------------------------------------------------
    op.create_table(
        "auto_filing_rules",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("model_type", sa.String(50), nullable=False, server_default="rule"),
        sa.Column("confidence_threshold", sa.Float(), nullable=False, server_default="0.95"),
        sa.Column("target_folder_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("target_category", sa.String(100), nullable=True),
        sa.Column("training_sample_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("accuracy", sa.Float(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column(
            "config",
            postgresql.JSONB(),
            server_default="{}",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    op.create_index(
        "ix_auto_filing_rules_company_id",
        "auto_filing_rules",
        ["company_id"],
    )
    op.create_index(
        "ix_auto_filing_rules_is_active",
        "auto_filing_rules",
        ["is_active"],
    )
    op.create_index(
        "ix_auto_filing_rules_company_active",
        "auto_filing_rules",
        ["company_id", "is_active"],
    )

    # ------------------------------------------------------------------
    # Table 15: auto_match_results
    # ------------------------------------------------------------------
    op.create_table(
        "auto_match_results",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "document_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "matched_document_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("match_type", sa.String(50), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column(
            "match_details",
            postgresql.JSONB(),
            server_default="{}",
        ),
        sa.Column("is_confirmed", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column(
            "confirmed_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    op.create_index(
        "ix_auto_match_results_company_id",
        "auto_match_results",
        ["company_id"],
    )
    op.create_index(
        "ix_auto_match_results_document_id",
        "auto_match_results",
        ["document_id"],
    )
    op.create_index(
        "ix_auto_match_results_matched_document_id",
        "auto_match_results",
        ["matched_document_id"],
    )
    op.create_index(
        "ix_auto_match_results_match_type",
        "auto_match_results",
        ["match_type"],
    )
    op.create_index(
        "ix_auto_match_document",
        "auto_match_results",
        ["document_id", "match_type"],
    )
    op.create_index(
        "ix_auto_match_matched",
        "auto_match_results",
        ["matched_document_id"],
    )
    op.create_index(
        "ix_auto_match_company_confirmed",
        "auto_match_results",
        ["company_id", "is_confirmed"],
    )

    # ==========================================================================
    # Feature #4: KI-Pipeline Intelligence
    # ==========================================================================

    # ------------------------------------------------------------------
    # Table 16: extraction_confidences
    # ------------------------------------------------------------------
    op.create_table(
        "extraction_confidences",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "document_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("field_name", sa.String(200), nullable=False),
        sa.Column("extracted_value", sa.Text(), nullable=False),
        sa.Column("confidence_score", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("confidence_level", sa.String(20), nullable=False, server_default="low"),
        sa.Column("was_corrected", sa.Boolean(), server_default="false"),
        sa.Column("corrected_value", sa.Text(), nullable=True),
        sa.Column(
            "corrected_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("corrected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("extraction_method", sa.String(50), nullable=False),
        sa.Column(
            "extraction_metadata",
            postgresql.JSONB(),
            server_default="{}",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "confidence_score >= 0.0 AND confidence_score <= 1.0",
            name="ck_extraction_conf_score_range",
        ),
        sa.CheckConstraint(
            "confidence_level IN ('high', 'medium', 'low')",
            name="ck_extraction_conf_level",
        ),
        sa.CheckConstraint(
            "extraction_method IN ('ocr', 'llm', 'regex', 'template')",
            name="ck_extraction_conf_method",
        ),
    )

    op.create_index(
        "ix_extraction_confidences_document_id",
        "extraction_confidences",
        ["document_id"],
    )
    op.create_index(
        "ix_extraction_confidences_company_id",
        "extraction_confidences",
        ["company_id"],
    )
    op.create_index(
        "ix_extraction_conf_doc_field",
        "extraction_confidences",
        ["document_id", "field_name"],
    )
    op.create_index(
        "ix_extraction_conf_company_level",
        "extraction_confidences",
        ["company_id", "confidence_level"],
    )
    op.create_index(
        "ix_extraction_conf_created",
        "extraction_confidences",
        ["created_at"],
    )

    # ------------------------------------------------------------------
    # Table 17: learning_profiles
    # ------------------------------------------------------------------
    op.create_table(
        "learning_profiles",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("profile_type", sa.String(50), nullable=False),
        sa.Column("profile_key", sa.String(200), nullable=False),
        sa.Column("correction_count", sa.Integer(), server_default="0"),
        sa.Column(
            "correction_patterns",
            postgresql.JSONB(),
            server_default="{}",
        ),
        sa.Column(
            "field_overrides",
            postgresql.JSONB(),
            server_default="{}",
        ),
        sa.Column("confidence_boost", sa.Float(), server_default="0.0"),
        sa.Column("last_correction_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "profile_type IN ('supplier', 'document_type')",
            name="ck_learning_prof_type",
        ),
        sa.CheckConstraint(
            "confidence_boost >= 0.0 AND confidence_boost <= 0.5",
            name="ck_learning_prof_boost_range",
        ),
    )

    op.create_index(
        "ix_learning_profiles_company_id",
        "learning_profiles",
        ["company_id"],
    )
    op.create_index(
        "ix_learning_prof_company_type_key",
        "learning_profiles",
        ["company_id", "profile_type", "profile_key"],
    )
    op.create_unique_constraint(
        "uq_learning_profile",
        "learning_profiles",
        ["company_id", "profile_type", "profile_key"],
    )

    # ------------------------------------------------------------------
    # Table 18: cross_document_matches
    # ------------------------------------------------------------------
    op.create_table(
        "cross_document_matches",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "document_a_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "document_b_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("match_type", sa.String(50), nullable=False),
        sa.Column("match_score", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column(
            "field_comparisons",
            postgresql.JSONB(),
            server_default="[]",
        ),
        sa.Column(
            "discrepancies",
            postgresql.JSONB(),
            server_default="[]",
        ),
        sa.Column("status", sa.String(30), nullable=False, server_default="auto_matched"),
        sa.Column(
            "reviewed_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "match_score >= 0.0 AND match_score <= 1.0",
            name="ck_cross_doc_match_score_range",
        ),
        sa.CheckConstraint(
            "match_type IN ('order_invoice', 'delivery_invoice', 'duplicate', 'amendment', 'order_delivery')",
            name="ck_cross_doc_match_type",
        ),
        sa.CheckConstraint(
            "status IN ('auto_matched', 'confirmed', 'rejected', 'review_needed')",
            name="ck_cross_doc_match_status",
        ),
    )

    op.create_index(
        "ix_cross_document_matches_company_id",
        "cross_document_matches",
        ["company_id"],
    )
    op.create_index(
        "ix_cross_document_matches_document_a_id",
        "cross_document_matches",
        ["document_a_id"],
    )
    op.create_index(
        "ix_cross_document_matches_document_b_id",
        "cross_document_matches",
        ["document_b_id"],
    )
    op.create_index(
        "ix_cross_doc_match_company",
        "cross_document_matches",
        ["company_id"],
    )
    op.create_index(
        "ix_cross_doc_match_doc_a",
        "cross_document_matches",
        ["document_a_id"],
    )
    op.create_index(
        "ix_cross_doc_match_doc_b",
        "cross_document_matches",
        ["document_b_id"],
    )
    op.create_index(
        "ix_cross_doc_match_status",
        "cross_document_matches",
        ["company_id", "status"],
    )

    # ------------------------------------------------------------------
    # Table 19: document_summaries
    # ------------------------------------------------------------------
    op.create_table(
        "document_summaries",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "document_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("summary_text", sa.Text(), nullable=False),
        sa.Column("summary_template", sa.String(100), nullable=False, server_default="default"),
        sa.Column(
            "key_facts",
            postgresql.JSONB(),
            server_default="{}",
        ),
        sa.Column(
            "generated_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column("model_used", sa.String(100), nullable=False, server_default="template"),
    )

    op.create_index(
        "ix_document_summaries_company_id",
        "document_summaries",
        ["company_id"],
    )
    op.create_index(
        "ix_doc_summary_company",
        "document_summaries",
        ["company_id"],
    )
    op.create_index(
        "ix_doc_summary_generated",
        "document_summaries",
        ["generated_at"],
    )

    # ==========================================================================
    # Feature #8+10: Annotations & German Precision
    # ==========================================================================

    # ------------------------------------------------------------------
    # Table 20: comment_replies
    # ------------------------------------------------------------------
    op.create_table(
        "comment_replies",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "thread_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("comment_threads.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "parent_reply_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("comment_replies.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column(
            "author_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "mentions",
            postgresql.JSONB(),
            server_default="[]",
        ),
        sa.Column("is_edited", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("edited_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
        ),
    )

    op.create_index(
        "ix_comment_replies_thread_id",
        "comment_replies",
        ["thread_id"],
    )
    op.create_index(
        "ix_comment_replies_parent_reply_id",
        "comment_replies",
        ["parent_reply_id"],
    )
    op.create_index(
        "ix_comment_replies_author_id",
        "comment_replies",
        ["author_id"],
    )
    op.create_index(
        "ix_comment_replies_thread_created",
        "comment_replies",
        ["thread_id", "created_at"],
    )

    # ------------------------------------------------------------------
    # Table 21: bounding_box_annotations
    # ------------------------------------------------------------------
    op.create_table(
        "bounding_box_annotations",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "document_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("page_number", sa.Integer(), nullable=False),
        sa.Column("x", sa.Float(), nullable=False),
        sa.Column("y", sa.Float(), nullable=False),
        sa.Column("width", sa.Float(), nullable=False),
        sa.Column("height", sa.Float(), nullable=False),
        sa.Column("annotation_type", sa.String(30), nullable=False, server_default="bounding_box"),
        sa.Column("label", sa.String(500), nullable=True),
        sa.Column("color", sa.String(20), nullable=False, server_default="'#FFD700'"),
        sa.Column(
            "author_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "thread_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("comment_threads.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
        ),
    )

    op.create_index(
        "ix_bbox_annotations_document_page",
        "bounding_box_annotations",
        ["document_id", "page_number"],
    )
    op.create_index(
        "ix_bbox_annotations_thread_id",
        "bounding_box_annotations",
        ["thread_id"],
    )
    op.create_index(
        "ix_bbox_annotations_author_id",
        "bounding_box_annotations",
        ["author_id"],
    )
    op.create_index(
        "ix_bbox_annotations_document_created",
        "bounding_box_annotations",
        ["document_id", "created_at"],
    )

    # ------------------------------------------------------------------
    # Table 22: comment_tasks
    # ------------------------------------------------------------------
    op.create_table(
        "comment_tasks",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "thread_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("comment_threads.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "assigned_to_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(50), nullable=False, server_default="offen"),
        sa.Column("due_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
        ),
    )

    op.create_index(
        "ix_comment_tasks_thread_id",
        "comment_tasks",
        ["thread_id"],
    )
    op.create_index(
        "ix_comment_tasks_assigned_status",
        "comment_tasks",
        ["assigned_to_user_id", "status"],
    )
    op.create_index(
        "ix_comment_tasks_due_date",
        "comment_tasks",
        ["due_date"],
    )
    op.create_index(
        "ix_comment_tasks_created_by",
        "comment_tasks",
        ["created_by_user_id"],
    )

    # ==========================================================================
    # Feature #11: Deutsche Finanz-Features
    # ==========================================================================

    # ------------------------------------------------------------------
    # Table 23: ust_voranmeldungen
    # ------------------------------------------------------------------
    op.create_table(
        "ust_voranmeldungen",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("period_type", sa.String(20), nullable=False, server_default="monthly"),
        sa.Column("vorsteuer_summe", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("umsatzsteuer_summe", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("zahllast", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("steuerfrei_inland", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("steuerfrei_export", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column(
            "innergemeinschaftliche_lieferungen",
            sa.Float(),
            nullable=False,
            server_default="0.0",
        ),
        sa.Column("vorsteuer_details", postgresql.JSONB(), nullable=True),
        sa.Column("umsatzsteuer_details", postgresql.JSONB(), nullable=True),
        sa.Column("status", sa.String(50), nullable=False, server_default="entwurf"),
        sa.Column("elster_xml", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
        ),
    )

    op.create_index(
        "ix_ust_voranmeldungen_company_id",
        "ust_voranmeldungen",
        ["company_id"],
    )
    op.create_index(
        "ix_ust_va_company_period",
        "ust_voranmeldungen",
        ["company_id", "period_start"],
    )
    op.create_index(
        "ix_ust_va_status",
        "ust_voranmeldungen",
        ["status"],
    )

    # ------------------------------------------------------------------
    # Table 24: bwa_reports
    # ------------------------------------------------------------------
    op.create_table(
        "bwa_reports",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("period_type", sa.String(20), nullable=False, server_default="monthly"),
        sa.Column("skr_schema", sa.String(10), nullable=False, server_default="SKR03"),
        sa.Column("erloese", postgresql.JSONB(), nullable=True),
        sa.Column("materialaufwand", postgresql.JSONB(), nullable=True),
        sa.Column("personalaufwand", postgresql.JSONB(), nullable=True),
        sa.Column("sonstige_aufwendungen", postgresql.JSONB(), nullable=True),
        sa.Column("abschreibungen", postgresql.JSONB(), nullable=True),
        sa.Column("betriebsergebnis", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("finanzergebnis", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("ergebnis_vor_steuern", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("steuern", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("jahresueberschuss", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("vorjahresvergleich", postgresql.JSONB(), nullable=True),
        sa.Column("status", sa.String(50), nullable=False, server_default="entwurf"),
        sa.Column(
            "created_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
        ),
    )

    op.create_index(
        "ix_bwa_reports_company_id",
        "bwa_reports",
        ["company_id"],
    )
    op.create_index(
        "ix_bwa_company_period",
        "bwa_reports",
        ["company_id", "period_start"],
    )
    op.create_index(
        "ix_bwa_status",
        "bwa_reports",
        ["status"],
    )

    # ------------------------------------------------------------------
    # Table 25: cashflow_forecasts
    # ------------------------------------------------------------------
    op.create_table(
        "cashflow_forecasts",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("forecast_date", sa.Date(), nullable=False),
        sa.Column(
            "forecast_generated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("horizon_days", sa.Integer(), nullable=False, server_default="90"),
        sa.Column("predicted_balance", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("confidence_lower", sa.Float(), nullable=True),
        sa.Column("confidence_upper", sa.Float(), nullable=True),
        sa.Column("einnahmen_prognose", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("ausgaben_prognose", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("offene_forderungen", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("offene_verbindlichkeiten", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("saisonaler_faktor", sa.Float(), nullable=True),
        sa.Column(
            "warnung_liquiditaetsengpass",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
        sa.Column("engpass_datum", sa.Date(), nullable=True),
        sa.Column("scenario_type", sa.String(50), nullable=False, server_default="basis"),
        sa.Column("scenario_config", postgresql.JSONB(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
        ),
    )

    op.create_index(
        "ix_cashflow_forecasts_company_id",
        "cashflow_forecasts",
        ["company_id"],
    )
    op.create_index(
        "ix_cashflow_forecast_company_date",
        "cashflow_forecasts",
        ["company_id", "forecast_date"],
    )
    op.create_index(
        "ix_cashflow_forecast_scenario",
        "cashflow_forecasts",
        ["company_id", "scenario_type"],
    )
    op.create_index(
        "ix_cashflow_forecast_engpass",
        "cashflow_forecasts",
        ["warnung_liquiditaetsengpass"],
    )

    # ==========================================================================
    # Feature #12a: Ad-Hoc Reporting
    # ==========================================================================

    # ------------------------------------------------------------------
    # Table 26: adhoc_reports
    # ------------------------------------------------------------------
    op.create_table(
        "adhoc_reports",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(300), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "created_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "data_sources",
            postgresql.JSONB(),
            nullable=False,
            server_default="[]",
        ),
        sa.Column(
            "columns",
            postgresql.JSONB(),
            nullable=False,
            server_default="[]",
        ),
        sa.Column(
            "filters",
            postgresql.JSONB(),
            nullable=False,
            server_default="[]",
        ),
        sa.Column("group_by", postgresql.JSONB(), nullable=True),
        sa.Column("order_by", postgresql.JSONB(), nullable=True),
        sa.Column("limit_rows", sa.Integer(), nullable=True),
        sa.Column("chart_config", postgresql.JSONB(), nullable=True),
        sa.Column("is_template", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("is_shared", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("shared_with_users", postgresql.JSONB(), nullable=True),
        sa.Column("last_executed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("execution_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_index(
        "ix_adhoc_reports_company_id",
        "adhoc_reports",
        ["company_id"],
    )
    op.create_index(
        "ix_adhoc_reports_created_by_user_id",
        "adhoc_reports",
        ["created_by_user_id"],
    )
    op.create_index(
        "ix_adhoc_reports_company_user",
        "adhoc_reports",
        ["company_id", "created_by_user_id"],
    )
    op.create_index(
        "ix_adhoc_reports_is_shared",
        "adhoc_reports",
        ["company_id", "is_shared"],
    )

    # ------------------------------------------------------------------
    # Table 27: scheduled_reports
    # ------------------------------------------------------------------
    op.create_table(
        "scheduled_reports",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "report_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("adhoc_reports.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("frequency", sa.String(20), nullable=False),
        sa.Column("day_of_week", sa.Integer(), nullable=True),
        sa.Column("day_of_month", sa.Integer(), nullable=True),
        sa.Column("time_of_day", sa.String(5), nullable=False, server_default="08:00"),
        sa.Column("export_format", sa.String(10), nullable=False, server_default="excel"),
        sa.Column(
            "recipients",
            postgresql.JSONB(),
            nullable=False,
            server_default="[]",
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("last_sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_send_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    op.create_index(
        "ix_scheduled_reports_report_id",
        "scheduled_reports",
        ["report_id"],
    )
    op.create_index(
        "ix_scheduled_reports_company_id",
        "scheduled_reports",
        ["company_id"],
    )
    op.create_index(
        "ix_scheduled_reports_is_active",
        "scheduled_reports",
        ["is_active"],
    )
    op.create_index(
        "ix_scheduled_reports_next_send_at",
        "scheduled_reports",
        ["next_send_at"],
    )
    op.create_index(
        "ix_scheduled_reports_active_next",
        "scheduled_reports",
        ["is_active", "next_send_at"],
    )

    # ------------------------------------------------------------------
    # Table 28: adhoc_report_execution_logs
    # ------------------------------------------------------------------
    op.create_table(
        "adhoc_report_execution_logs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "report_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("adhoc_reports.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "executed_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("export_format", sa.String(10), nullable=True),
        sa.Column("row_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("execution_time_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("file_path", sa.String(500), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    op.create_index(
        "ix_adhoc_report_execution_logs_report_id",
        "adhoc_report_execution_logs",
        ["report_id"],
    )
    op.create_index(
        "ix_adhoc_report_execution_logs_company_id",
        "adhoc_report_execution_logs",
        ["company_id"],
    )
    op.create_index(
        "ix_adhoc_exec_log_report_date",
        "adhoc_report_execution_logs",
        ["report_id", "created_at"],
    )

    # ==========================================================================
    # Feature #12b: Ad-Hoc Reporting Extended
    # ==========================================================================

    # ------------------------------------------------------------------
    # Table 29: ad_hoc_reports
    # ------------------------------------------------------------------
    op.create_table(
        "ad_hoc_reports",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "created_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(300), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "data_sources",
            postgresql.JSONB(),
            nullable=False,
            server_default="[]",
        ),
        sa.Column(
            "columns",
            postgresql.JSONB(),
            nullable=False,
            server_default="[]",
        ),
        sa.Column(
            "filters",
            postgresql.JSONB(),
            server_default="[]",
        ),
        sa.Column(
            "grouping",
            postgresql.JSONB(),
            server_default="[]",
        ),
        sa.Column(
            "aggregations",
            postgresql.JSONB(),
            server_default="[]",
        ),
        sa.Column("chart_config", postgresql.JSONB(), nullable=True),
        sa.Column("is_public", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("is_template", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("execution_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_executed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
        ),
    )

    op.create_index(
        "ix_ad_hoc_reports_company_id",
        "ad_hoc_reports",
        ["company_id"],
    )
    op.create_index(
        "ix_ad_hoc_reports_created_by",
        "ad_hoc_reports",
        ["created_by"],
    )
    op.create_index(
        "ix_adhoc_reports_company_created",
        "ad_hoc_reports",
        ["company_id", "created_by"],
    )
    op.create_index(
        "ix_adhoc_reports_public",
        "ad_hoc_reports",
        ["company_id", "is_public"],
    )
    op.create_index(
        "ix_adhoc_reports_template",
        "ad_hoc_reports",
        ["is_template"],
    )

    # ------------------------------------------------------------------
    # Table 30: ad_hoc_report_executions
    # ------------------------------------------------------------------
    op.create_table(
        "ad_hoc_report_executions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "report_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("ad_hoc_reports.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "executed_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("row_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("execution_time_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("export_format", sa.String(20), nullable=True),
        sa.Column("export_path", sa.String(500), nullable=True),
        sa.Column("parameters", postgresql.JSONB(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
        ),
    )

    op.create_index(
        "ix_ad_hoc_report_executions_report_id",
        "ad_hoc_report_executions",
        ["report_id"],
    )
    op.create_index(
        "ix_ad_hoc_report_executions_company_id",
        "ad_hoc_report_executions",
        ["company_id"],
    )
    op.create_index(
        "ix_adhoc_exec_report_created",
        "ad_hoc_report_executions",
        ["report_id", "created_at"],
    )
    op.create_index(
        "ix_adhoc_exec_company",
        "ad_hoc_report_executions",
        ["company_id"],
    )

    # ------------------------------------------------------------------
    # Table 31: ad_hoc_report_shares
    # ------------------------------------------------------------------
    op.create_table(
        "ad_hoc_report_shares",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "report_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("ad_hoc_reports.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "shared_with_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("shared_with_role", sa.String(100), nullable=True),
        sa.Column("can_edit", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "shared_with_user_id IS NOT NULL OR shared_with_role IS NOT NULL",
            name="ck_adhoc_share_target",
        ),
    )

    op.create_index(
        "ix_ad_hoc_report_shares_report_id",
        "ad_hoc_report_shares",
        ["report_id"],
    )
    op.create_index(
        "ix_adhoc_share_report",
        "ad_hoc_report_shares",
        ["report_id"],
    )
    op.create_index(
        "ix_adhoc_share_user",
        "ad_hoc_report_shares",
        ["shared_with_user_id"],
    )
    op.create_index(
        "ix_ad_hoc_report_shares_shared_with_user_id",
        "ad_hoc_report_shares",
        ["shared_with_user_id"],
    )

    # ------------------------------------------------------------------
    # Table 32: ad_hoc_report_schedules
    # ------------------------------------------------------------------
    op.create_table(
        "ad_hoc_report_schedules",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "report_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("ad_hoc_reports.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("frequency", sa.String(20), nullable=False),
        sa.Column("day_of_week", sa.Integer(), nullable=True),
        sa.Column("day_of_month", sa.Integer(), nullable=True),
        sa.Column("time_of_day", sa.String(5), nullable=False, server_default="08:00"),
        sa.Column("export_format", sa.String(20), nullable=False, server_default="excel"),
        sa.Column(
            "recipients",
            postgresql.JSONB(),
            nullable=False,
            server_default="[]",
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "frequency IN ('daily', 'weekly', 'monthly', 'quarterly')",
            name="ck_adhoc_schedule_frequency",
        ),
        sa.CheckConstraint(
            "day_of_week IS NULL OR (day_of_week >= 0 AND day_of_week <= 6)",
            name="ck_adhoc_schedule_day_of_week",
        ),
        sa.CheckConstraint(
            "day_of_month IS NULL OR (day_of_month >= 1 AND day_of_month <= 28)",
            name="ck_adhoc_schedule_day_of_month",
        ),
    )

    op.create_index(
        "ix_ad_hoc_report_schedules_report_id",
        "ad_hoc_report_schedules",
        ["report_id"],
    )
    op.create_index(
        "ix_ad_hoc_report_schedules_company_id",
        "ad_hoc_report_schedules",
        ["company_id"],
    )
    op.create_index(
        "ix_adhoc_schedule_active",
        "ad_hoc_report_schedules",
        ["is_active", "next_run_at"],
    )
    op.create_index(
        "ix_adhoc_schedule_report",
        "ad_hoc_report_schedules",
        ["report_id"],
    )


def downgrade() -> None:
    # Drop all tables in REVERSE order (32 -> 1)

    # Feature #12b: Ad-Hoc Reporting Extended
    op.drop_index("ix_adhoc_schedule_report", table_name="ad_hoc_report_schedules")
    op.drop_index("ix_adhoc_schedule_active", table_name="ad_hoc_report_schedules")
    op.drop_index("ix_ad_hoc_report_schedules_company_id", table_name="ad_hoc_report_schedules")
    op.drop_index("ix_ad_hoc_report_schedules_report_id", table_name="ad_hoc_report_schedules")
    op.drop_table("ad_hoc_report_schedules")

    op.drop_index("ix_ad_hoc_report_shares_shared_with_user_id", table_name="ad_hoc_report_shares")
    op.drop_index("ix_adhoc_share_user", table_name="ad_hoc_report_shares")
    op.drop_index("ix_adhoc_share_report", table_name="ad_hoc_report_shares")
    op.drop_index("ix_ad_hoc_report_shares_report_id", table_name="ad_hoc_report_shares")
    op.drop_table("ad_hoc_report_shares")

    op.drop_index("ix_adhoc_exec_company", table_name="ad_hoc_report_executions")
    op.drop_index("ix_adhoc_exec_report_created", table_name="ad_hoc_report_executions")
    op.drop_index("ix_ad_hoc_report_executions_company_id", table_name="ad_hoc_report_executions")
    op.drop_index("ix_ad_hoc_report_executions_report_id", table_name="ad_hoc_report_executions")
    op.drop_table("ad_hoc_report_executions")

    op.drop_index("ix_adhoc_reports_template", table_name="ad_hoc_reports")
    op.drop_index("ix_adhoc_reports_public", table_name="ad_hoc_reports")
    op.drop_index("ix_adhoc_reports_company_created", table_name="ad_hoc_reports")
    op.drop_index("ix_ad_hoc_reports_created_by", table_name="ad_hoc_reports")
    op.drop_index("ix_ad_hoc_reports_company_id", table_name="ad_hoc_reports")
    op.drop_table("ad_hoc_reports")

    # Feature #12a: Ad-Hoc Reporting
    op.drop_index("ix_adhoc_exec_log_report_date", table_name="adhoc_report_execution_logs")
    op.drop_index("ix_adhoc_report_execution_logs_company_id", table_name="adhoc_report_execution_logs")
    op.drop_index("ix_adhoc_report_execution_logs_report_id", table_name="adhoc_report_execution_logs")
    op.drop_table("adhoc_report_execution_logs")

    op.drop_index("ix_scheduled_reports_active_next", table_name="scheduled_reports")
    op.drop_index("ix_scheduled_reports_next_send_at", table_name="scheduled_reports")
    op.drop_index("ix_scheduled_reports_is_active", table_name="scheduled_reports")
    op.drop_index("ix_scheduled_reports_company_id", table_name="scheduled_reports")
    op.drop_index("ix_scheduled_reports_report_id", table_name="scheduled_reports")
    op.drop_table("scheduled_reports")

    op.drop_index("ix_adhoc_reports_is_shared", table_name="adhoc_reports")
    op.drop_index("ix_adhoc_reports_company_user", table_name="adhoc_reports")
    op.drop_index("ix_adhoc_reports_created_by_user_id", table_name="adhoc_reports")
    op.drop_index("ix_adhoc_reports_company_id", table_name="adhoc_reports")
    op.drop_table("adhoc_reports")

    # Feature #11: Deutsche Finanz-Features
    op.drop_index("ix_cashflow_forecast_engpass", table_name="cashflow_forecasts")
    op.drop_index("ix_cashflow_forecast_scenario", table_name="cashflow_forecasts")
    op.drop_index("ix_cashflow_forecast_company_date", table_name="cashflow_forecasts")
    op.drop_index("ix_cashflow_forecasts_company_id", table_name="cashflow_forecasts")
    op.drop_table("cashflow_forecasts")

    op.drop_index("ix_bwa_status", table_name="bwa_reports")
    op.drop_index("ix_bwa_company_period", table_name="bwa_reports")
    op.drop_index("ix_bwa_reports_company_id", table_name="bwa_reports")
    op.drop_table("bwa_reports")

    op.drop_index("ix_ust_va_status", table_name="ust_voranmeldungen")
    op.drop_index("ix_ust_va_company_period", table_name="ust_voranmeldungen")
    op.drop_index("ix_ust_voranmeldungen_company_id", table_name="ust_voranmeldungen")
    op.drop_table("ust_voranmeldungen")

    # Feature #8+10: Annotations & German Precision
    op.drop_index("ix_comment_tasks_created_by", table_name="comment_tasks")
    op.drop_index("ix_comment_tasks_due_date", table_name="comment_tasks")
    op.drop_index("ix_comment_tasks_assigned_status", table_name="comment_tasks")
    op.drop_index("ix_comment_tasks_thread_id", table_name="comment_tasks")
    op.drop_table("comment_tasks")

    op.drop_index("ix_bbox_annotations_document_created", table_name="bounding_box_annotations")
    op.drop_index("ix_bbox_annotations_author_id", table_name="bounding_box_annotations")
    op.drop_index("ix_bbox_annotations_thread_id", table_name="bounding_box_annotations")
    op.drop_index("ix_bbox_annotations_document_page", table_name="bounding_box_annotations")
    op.drop_table("bounding_box_annotations")

    op.drop_index("ix_comment_replies_thread_created", table_name="comment_replies")
    op.drop_index("ix_comment_replies_author_id", table_name="comment_replies")
    op.drop_index("ix_comment_replies_parent_reply_id", table_name="comment_replies")
    op.drop_index("ix_comment_replies_thread_id", table_name="comment_replies")
    op.drop_table("comment_replies")

    # Feature #4: KI-Pipeline Intelligence
    op.drop_index("ix_doc_summary_generated", table_name="document_summaries")
    op.drop_index("ix_doc_summary_company", table_name="document_summaries")
    op.drop_index("ix_document_summaries_company_id", table_name="document_summaries")
    op.drop_table("document_summaries")

    op.drop_index("ix_cross_doc_match_status", table_name="cross_document_matches")
    op.drop_index("ix_cross_doc_match_doc_b", table_name="cross_document_matches")
    op.drop_index("ix_cross_doc_match_doc_a", table_name="cross_document_matches")
    op.drop_index("ix_cross_doc_match_company", table_name="cross_document_matches")
    op.drop_index("ix_cross_document_matches_document_b_id", table_name="cross_document_matches")
    op.drop_index("ix_cross_document_matches_document_a_id", table_name="cross_document_matches")
    op.drop_index("ix_cross_document_matches_company_id", table_name="cross_document_matches")
    op.drop_table("cross_document_matches")

    op.drop_unique_constraint("uq_learning_profile", table_name="learning_profiles")
    op.drop_index("ix_learning_prof_company_type_key", table_name="learning_profiles")
    op.drop_index("ix_learning_profiles_company_id", table_name="learning_profiles")
    op.drop_table("learning_profiles")

    op.drop_index("ix_extraction_conf_created", table_name="extraction_confidences")
    op.drop_index("ix_extraction_conf_company_level", table_name="extraction_confidences")
    op.drop_index("ix_extraction_conf_doc_field", table_name="extraction_confidences")
    op.drop_index("ix_extraction_confidences_company_id", table_name="extraction_confidences")
    op.drop_index("ix_extraction_confidences_document_id", table_name="extraction_confidences")
    op.drop_table("extraction_confidences")

    # Feature #7: Automation 2.0
    op.drop_index("ix_auto_match_company_confirmed", table_name="auto_match_results")
    op.drop_index("ix_auto_match_matched", table_name="auto_match_results")
    op.drop_index("ix_auto_match_document", table_name="auto_match_results")
    op.drop_index("ix_auto_match_results_match_type", table_name="auto_match_results")
    op.drop_index("ix_auto_match_results_matched_document_id", table_name="auto_match_results")
    op.drop_index("ix_auto_match_results_document_id", table_name="auto_match_results")
    op.drop_index("ix_auto_match_results_company_id", table_name="auto_match_results")
    op.drop_table("auto_match_results")

    op.drop_index("ix_auto_filing_rules_company_active", table_name="auto_filing_rules")
    op.drop_index("ix_auto_filing_rules_is_active", table_name="auto_filing_rules")
    op.drop_index("ix_auto_filing_rules_company_id", table_name="auto_filing_rules")
    op.drop_table("auto_filing_rules")

    # Feature #3: Approval Workflow Depth
    op.drop_index("ix_approval_sla_metrics_is_breached", table_name="approval_sla_metrics")
    op.drop_index("ix_sla_metrics_breached", table_name="approval_sla_metrics")
    op.drop_index("ix_sla_metrics_request_step", table_name="approval_sla_metrics")
    op.drop_index("ix_approval_sla_metrics_approval_request_id", table_name="approval_sla_metrics")
    op.drop_index("ix_approval_sla_metrics_company_id", table_name="approval_sla_metrics")
    op.drop_table("approval_sla_metrics")

    op.drop_index("ix_substitution_rules_is_active", table_name="substitution_rules")
    op.drop_index("ix_substitution_rules_period", table_name="substitution_rules")
    op.drop_index("ix_substitution_rules_substitute", table_name="substitution_rules")
    op.drop_index("ix_substitution_rules_user", table_name="substitution_rules")
    op.drop_index("ix_substitution_rules_substitute_user_id", table_name="substitution_rules")
    op.drop_index("ix_substitution_rules_user_id", table_name="substitution_rules")
    op.drop_index("ix_substitution_rules_company_id", table_name="substitution_rules")
    op.drop_table("substitution_rules")

    op.drop_index("ix_escalation_rules_company_active", table_name="escalation_rules")
    op.drop_index("ix_escalation_rules_is_active", table_name="escalation_rules")
    op.drop_index("ix_escalation_rules_company_id", table_name="escalation_rules")
    op.drop_table("escalation_rules")

    op.drop_index("ix_cond_approval_rules_company_active", table_name="conditional_approval_rules")
    op.drop_index("ix_conditional_approval_rules_is_active", table_name="conditional_approval_rules")
    op.drop_index("ix_conditional_approval_rules_company_id", table_name="conditional_approval_rules")
    op.drop_table("conditional_approval_rules")

    # Feature #2+6: Smart Dashboard
    op.drop_index("ix_batch_progress_company", table_name="batch_progress_trackers")
    op.drop_index("ix_batch_progress_trackers_company_id", table_name="batch_progress_trackers")
    op.drop_table("batch_progress_trackers")

    op.drop_index("ix_doc_progress_started_at", table_name="document_progress_trackers")
    op.drop_index("ix_doc_progress_company_step", table_name="document_progress_trackers")
    op.drop_index("ix_document_progress_trackers_company_id", table_name="document_progress_trackers")
    op.drop_table("document_progress_trackers")

    op.drop_unique_constraint("uq_dashboard_layout_user_tab", table_name="smart_dashboard_layouts")
    op.drop_index("ix_dashboard_layout_user_company", table_name="smart_dashboard_layouts")
    op.drop_index("ix_smart_dashboard_layouts_company_id", table_name="smart_dashboard_layouts")
    op.drop_index("ix_smart_dashboard_layouts_user_id", table_name="smart_dashboard_layouts")
    op.drop_table("smart_dashboard_layouts")

    op.drop_index("ix_smart_widgets_active", table_name="smart_dashboard_widgets")
    op.drop_index("ix_smart_widgets_company_tab", table_name="smart_dashboard_widgets")
    op.drop_index("ix_smart_dashboard_widgets_tab", table_name="smart_dashboard_widgets")
    op.drop_index("ix_smart_dashboard_widgets_company_id", table_name="smart_dashboard_widgets")
    op.drop_table("smart_dashboard_widgets")

    op.drop_index("ix_dashboard_kpis_calculated_at", table_name="dashboard_kpis")
    op.drop_index("ix_dashboard_kpis_company_key", table_name="dashboard_kpis")
    op.drop_index("ix_dashboard_kpis_kpi_key", table_name="dashboard_kpis")
    op.drop_index("ix_dashboard_kpis_company_id", table_name="dashboard_kpis")
    op.drop_table("dashboard_kpis")

    op.drop_index("ix_smart_dashboard_company_user", table_name="smart_dashboard_configs")
    op.drop_index("ix_smart_dashboard_configs_user_id", table_name="smart_dashboard_configs")
    op.drop_index("ix_smart_dashboard_configs_company_id", table_name="smart_dashboard_configs")
    op.drop_table("smart_dashboard_configs")

    # Feature #1: Proactive Assistant
    op.drop_index("ix_hint_statistics_company_period", table_name="hint_statistics")
    op.drop_index("ix_hint_statistics_company_id", table_name="hint_statistics")
    op.drop_table("hint_statistics")

    op.drop_index("ix_hint_rules_company_active", table_name="hint_rules")
    op.drop_index("ix_hint_rules_company_id", table_name="hint_rules")
    op.drop_table("hint_rules")

    op.drop_index("ix_proactive_hints_source", table_name="proactive_hints")
    op.drop_index("ix_proactive_hints_combined_score", table_name="proactive_hints")
    op.drop_index("ix_proactive_hints_expires_at", table_name="proactive_hints")
    op.drop_index("ix_proactive_hints_company_category_created", table_name="proactive_hints")
    op.drop_index("ix_proactive_hints_company_status", table_name="proactive_hints")
    op.drop_index("ix_proactive_hints_user_id", table_name="proactive_hints")
    op.drop_index("ix_proactive_hints_company_id", table_name="proactive_hints")
    op.drop_table("proactive_hints")
