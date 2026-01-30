"""Add insights and autonomy tables

Vision 2.0 Phase 2+3: KI-Intelligenz und Autonomie-Framework

Neue Tabellen:
- cashflow_predictions: Cashflow-Prognosen
- fraud_alerts: Betrugs-Warnungen
- skonto_recommendations: Skonto-Empfehlungen
- proactive_insights: Generische proaktive Insights
- autonomy_settings: Autonomie-Einstellungen pro Company
- pending_actions: Genehmigungs-Warteschlange
- autonomy_decision_logs: Entscheidungs-Protokoll
- autonomy_metrics: Aggregierte Metriken

Revision ID: 144_insights_autonomy
Revises: 143_add_consent_management
Create Date: 2026-01-30

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "144_insights_autonomy"
down_revision: Union[str, None] = "143_consent_management"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ==========================================================================
    # CASHFLOW PREDICTIONS
    # ==========================================================================
    op.create_table(
        "cashflow_predictions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("prediction_date", sa.Date(), nullable=False),
        sa.Column("scenario_type", sa.String(30), nullable=False, server_default="baseline"),
        sa.Column("predicted_inflow", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("predicted_outflow", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("predicted_balance", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("confidence_low", sa.Float(), nullable=True),
        sa.Column("confidence_high", sa.Float(), nullable=True),
        sa.Column("confidence_level", sa.Float(), nullable=True, server_default="0.95"),
        sa.Column("model_version", sa.String(50), nullable=True),
        sa.Column("features_used", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("accuracy_metrics", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("inflow_breakdown", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("outflow_breakdown", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "scenario_type IN ('baseline', 'optimistic', 'pessimistic', 'custom')",
            name="ck_cashflow_scenario_type"
        ),
        comment="Cashflow-Prognosen fuer Liquiditaetsplanung"
    )
    op.create_index(
        "ix_cashflow_pred_company_date",
        "cashflow_predictions",
        ["company_id", "prediction_date", "scenario_type"],
        unique=True
    )
    op.create_index("ix_cashflow_pred_date_range", "cashflow_predictions", ["prediction_date"])

    # ==========================================================================
    # FRAUD ALERTS
    # ==========================================================================
    op.create_table(
        "fraud_alerts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("alert_type", sa.String(50), nullable=False),
        sa.Column("severity", sa.String(20), nullable=False, server_default="medium"),
        sa.Column("status", sa.String(30), nullable=False, server_default="open"),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("risk_score", sa.Float(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("invoice_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("evidence", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("anomaly_details", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("similar_cases", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("recommended_actions", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("assigned_to_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("investigation_notes", sa.Text(), nullable=True),
        sa.Column("resolution_notes", sa.Text(), nullable=True),
        sa.Column("detected_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_by_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["entity_id"], ["business_entities.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["assigned_to_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["resolved_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "severity IN ('info', 'low', 'medium', 'high', 'critical')",
            name="ck_fraud_alert_severity"
        ),
        sa.CheckConstraint(
            "status IN ('open', 'investigating', 'confirmed', 'false_positive', 'resolved')",
            name="ck_fraud_alert_status"
        ),
        comment="Betrugs-Warnungen aus Anomalieerkennung"
    )
    op.create_index("ix_fraud_alert_company_id", "fraud_alerts", ["company_id"])
    op.create_index("ix_fraud_alert_company_status", "fraud_alerts", ["company_id", "status"])
    op.create_index("ix_fraud_alert_type_severity", "fraud_alerts", ["alert_type", "severity"])
    op.create_index("ix_fraud_alert_detected", "fraud_alerts", ["detected_at"])
    op.create_index("ix_fraud_alert_document_id", "fraud_alerts", ["document_id"])
    op.create_index("ix_fraud_alert_entity_id", "fraud_alerts", ["entity_id"])

    # ==========================================================================
    # SKONTO RECOMMENDATIONS
    # ==========================================================================
    op.create_table(
        "skonto_recommendations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("invoice_tracking_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("recommendation", sa.String(50), nullable=False),
        sa.Column("priority", sa.String(20), nullable=False, server_default="medium"),
        sa.Column("invoice_amount", sa.Float(), nullable=False),
        sa.Column("skonto_percentage", sa.Float(), nullable=False),
        sa.Column("skonto_amount", sa.Float(), nullable=False),
        sa.Column("skonto_deadline", sa.Date(), nullable=False),
        sa.Column("days_until_deadline", sa.Integer(), nullable=False),
        sa.Column("annualized_return", sa.Float(), nullable=True),
        sa.Column("opportunity_cost", sa.Float(), nullable=True),
        sa.Column("liquidity_impact", sa.Float(), nullable=True),
        sa.Column("cash_available", sa.Float(), nullable=True),
        sa.Column("liquidity_buffer_after", sa.Float(), nullable=True),
        sa.Column("reasoning", sa.Text(), nullable=True),
        sa.Column("factors", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("status", sa.String(30), nullable=False, server_default="new"),
        sa.Column("acted_upon", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("action_taken", sa.String(50), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("acted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["entity_id"], ["business_entities.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "status IN ('new', 'acknowledged', 'acted_upon', 'dismissed', 'expired')",
            name="ck_skonto_rec_status"
        ),
        sa.CheckConstraint(
            "priority IN ('high', 'medium', 'low')",
            name="ck_skonto_rec_priority"
        ),
        comment="Skonto-Optimierungsempfehlungen"
    )
    op.create_index("ix_skonto_rec_company_id", "skonto_recommendations", ["company_id"])
    op.create_index("ix_skonto_rec_company_status", "skonto_recommendations", ["company_id", "status"])
    op.create_index("ix_skonto_rec_deadline", "skonto_recommendations", ["skonto_deadline"])
    op.create_index("ix_skonto_rec_priority", "skonto_recommendations", ["priority"])
    op.create_index("ix_skonto_rec_invoice", "skonto_recommendations", ["invoice_tracking_id"])

    # ==========================================================================
    # PROACTIVE INSIGHTS
    # ==========================================================================
    op.create_table(
        "proactive_insights",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("category", sa.String(30), nullable=False),
        sa.Column("insight_type", sa.String(50), nullable=False),
        sa.Column("severity", sa.String(20), nullable=False, server_default="info"),
        sa.Column("status", sa.String(30), nullable=False, server_default="new"),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("summary", sa.String(500), nullable=False),
        sa.Column("details", sa.Text(), nullable=True),
        sa.Column("icon", sa.String(50), nullable=True),
        sa.Column("context_data", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("related_entities", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("metrics", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("suggested_actions", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("action_url", sa.String(255), nullable=True),
        sa.Column("valid_from", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("recurrence_key", sa.String(255), nullable=True),
        sa.Column("viewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("dismissed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("acted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "category IN ('cashflow', 'fraud', 'skonto', 'risk', 'payment', 'supplier', 'seasonal')",
            name="ck_insight_category"
        ),
        sa.CheckConstraint(
            "severity IN ('info', 'low', 'medium', 'high', 'critical')",
            name="ck_insight_severity"
        ),
        sa.CheckConstraint(
            "status IN ('new', 'acknowledged', 'acted_upon', 'dismissed', 'expired')",
            name="ck_insight_status"
        ),
        comment="Proaktive Insights fuer Benutzer"
    )
    op.create_index("ix_proactive_insight_company_id", "proactive_insights", ["company_id"])
    op.create_index("ix_proactive_insight_user_id", "proactive_insights", ["user_id"])
    op.create_index("ix_insight_company_status", "proactive_insights", ["company_id", "status"])
    op.create_index("ix_insight_category_type", "proactive_insights", ["category", "insight_type"])
    op.create_index("ix_insight_valid_range", "proactive_insights", ["valid_from", "valid_until"])
    op.create_index("ix_insight_recurrence", "proactive_insights", ["recurrence_key"])

    # ==========================================================================
    # AUTONOMY SETTINGS
    # ==========================================================================
    op.create_table(
        "autonomy_settings",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("autonomy_level", sa.String(30), nullable=False, server_default="conservative"),
        sa.Column("category_overrides", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("low_confidence_threshold", sa.Float(), nullable=False, server_default="0.80"),
        sa.Column("high_confidence_threshold", sa.Float(), nullable=False, server_default="0.95"),
        sa.Column("default_timeout_hours", sa.Integer(), nullable=False, server_default="24"),
        sa.Column("auto_approve_on_timeout", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("notify_on_auto_execute", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("notify_channels", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("require_dual_approval", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("dual_approval_categories", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("daily_auto_execute_limit", sa.Integer(), nullable=True),
        sa.Column("max_single_action_value", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.Column("updated_by_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["updated_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("company_id"),
        sa.CheckConstraint(
            "autonomy_level IN ('conservative', 'smart_hybrid', 'progressive', 'zero_touch')",
            name="ck_autonomy_level"
        ),
        sa.CheckConstraint(
            "low_confidence_threshold >= 0.0 AND low_confidence_threshold <= 1.0",
            name="ck_low_threshold_range"
        ),
        sa.CheckConstraint(
            "high_confidence_threshold >= 0.0 AND high_confidence_threshold <= 1.0",
            name="ck_high_threshold_range"
        ),
        sa.CheckConstraint(
            "low_confidence_threshold < high_confidence_threshold",
            name="ck_threshold_order"
        ),
        comment="Autonomie-Einstellungen pro Company"
    )
    op.create_index("ix_autonomy_settings_company_id", "autonomy_settings", ["company_id"])

    # ==========================================================================
    # PENDING ACTIONS
    # ==========================================================================
    op.create_table(
        "pending_actions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("action_type", sa.String(100), nullable=False),
        sa.Column("action_category", sa.String(30), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("detailed_description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(30), nullable=False, server_default="pending"),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("routing_decision", sa.String(30), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("parameters", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("affected_entities", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("estimated_impact", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("source_type", sa.String(50), nullable=True),
        sa.Column("source_id", sa.String(100), nullable=True),
        sa.Column("approved_by_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column("requires_dual_approval", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("second_approver_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("second_approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("executed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("execution_result", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("execution_error", sa.Text(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="50"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["approved_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["second_approver_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "status IN ('pending', 'approved', 'rejected', 'expired', 'auto_approved', 'cancelled')",
            name="ck_pending_action_status"
        ),
        sa.CheckConstraint(
            "action_category IN ('routine', 'read_only', 'modification', 'notification', 'financial', 'deletion', 'external', 'legal', 'compliance')",
            name="ck_pending_action_category"
        ),
        sa.CheckConstraint(
            "priority >= 0 AND priority <= 100",
            name="ck_pending_priority_range"
        ),
        sa.CheckConstraint(
            "confidence >= 0.0 AND confidence <= 1.0",
            name="ck_pending_confidence_range"
        ),
        comment="Ausstehende Aktionen fuer Genehmigung"
    )
    op.create_index("ix_pending_action_company_id", "pending_actions", ["company_id"])
    op.create_index("ix_pending_company_status", "pending_actions", ["company_id", "status"])
    op.create_index("ix_pending_expires", "pending_actions", ["expires_at"])
    op.create_index("ix_pending_priority", "pending_actions", ["priority"])
    op.create_index("ix_pending_category", "pending_actions", ["action_category"])
    op.create_index("ix_pending_action_type", "pending_actions", ["action_type"])

    # ==========================================================================
    # AUTONOMY DECISION LOGS
    # ==========================================================================
    op.create_table(
        "autonomy_decision_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("action_type", sa.String(100), nullable=False),
        sa.Column("action_category", sa.String(30), nullable=False),
        sa.Column("action_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("routing_decision", sa.String(30), nullable=False),
        sa.Column("was_auto_executed", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("confidence_score", sa.Float(), nullable=False),
        sa.Column("autonomy_level", sa.String(30), nullable=False),
        sa.Column("category_override_applied", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("low_threshold_used", sa.Float(), nullable=False),
        sa.Column("high_threshold_used", sa.Float(), nullable=False),
        sa.Column("decision_reason", sa.Text(), nullable=True),
        sa.Column("decision_factors", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("outcome", sa.String(30), nullable=True),
        sa.Column("outcome_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("user_feedback", sa.String(30), nullable=True),
        sa.Column("decision_time_ms", sa.Integer(), nullable=True),
        sa.Column("execution_time_ms", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "routing_decision IN ('auto_execute', 'suggest_and_confirm', 'manual_review')",
            name="ck_decision_routing"
        ),
        comment="Protokoll der Autonomie-Entscheidungen"
    )
    op.create_index("ix_decision_log_company_id", "autonomy_decision_logs", ["company_id"])
    op.create_index("ix_decision_log_company_date", "autonomy_decision_logs", ["company_id", "created_at"])
    op.create_index("ix_decision_log_action_type", "autonomy_decision_logs", ["action_type", "created_at"])
    op.create_index("ix_decision_log_routing", "autonomy_decision_logs", ["routing_decision", "created_at"])
    op.create_index("ix_decision_log_outcome", "autonomy_decision_logs", ["outcome"])
    op.create_index("ix_decision_log_action_id", "autonomy_decision_logs", ["action_id"])

    # ==========================================================================
    # AUTONOMY METRICS
    # ==========================================================================
    op.create_table(
        "autonomy_metrics",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("total_actions", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("auto_executed_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("suggested_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("manual_review_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("approved_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rejected_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("expired_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("avg_confidence", sa.Float(), nullable=True),
        sa.Column("avg_decision_time_ms", sa.Float(), nullable=True),
        sa.Column("avg_approval_time_min", sa.Float(), nullable=True),
        sa.Column("auto_execute_success_rate", sa.Float(), nullable=True),
        sa.Column("false_positive_rate", sa.Float(), nullable=True),
        sa.Column("by_category", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("by_action_type", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        comment="Aggregierte Autonomie-Metriken"
    )
    op.create_index("ix_autonomy_metrics_company_id", "autonomy_metrics", ["company_id"])
    op.create_index(
        "ix_autonomy_metrics_company_date",
        "autonomy_metrics",
        ["company_id", "date"],
        unique=True
    )


def downgrade() -> None:
    # Drop tables in reverse order
    op.drop_table("autonomy_metrics")
    op.drop_table("autonomy_decision_logs")
    op.drop_table("pending_actions")
    op.drop_table("autonomy_settings")
    op.drop_table("proactive_insights")
    op.drop_table("skonto_recommendations")
    op.drop_table("fraud_alerts")
    op.drop_table("cashflow_predictions")
