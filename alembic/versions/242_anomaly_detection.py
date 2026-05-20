"""Anomalie-Erkennung Tabellen.

Revision ID: 242
Revises: 241
Create Date: 2026-02-21

Erstellt die Infrastruktur fuer Hybrid-Anomalie-Erkennung:
- anomaly_rules: Konfigurierbare Pruefregeln pro Mandant
- anomalies: Erkannte Anomalien mit Score und Status-Tracking

Phase 2.3 der Feature-Roadmap.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "242"
down_revision = "241"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # anomaly_rules
    op.create_table(
        "anomaly_rules",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("rule_type", sa.String(50), nullable=False),
        sa.Column(
            "config",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "severity",
            sa.String(20),
            nullable=False,
            server_default="warning",
        ),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=False,
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
        ),
        # Constraints
        sa.CheckConstraint(
            "rule_type IN ('duplicate_invoice', 'amount_outlier', 'supplier_change', "
            "'missing_chain_doc', 'unusual_frequency', 'amount_threshold')",
            name="ck_anomaly_rules_rule_type",
        ),
        sa.CheckConstraint(
            "severity IN ('info', 'warning', 'critical')",
            name="ck_anomaly_rules_severity",
        ),
    )

    op.create_index(
        "ix_anomaly_rules_company_id",
        "anomaly_rules",
        ["company_id"],
    )
    op.create_index(
        "ix_anomaly_rules_rule_type",
        "anomaly_rules",
        ["rule_type"],
    )
    op.create_index(
        "ix_anomaly_rules_company_active",
        "anomaly_rules",
        ["company_id", "is_active"],
    )

    # anomalies
    op.create_table(
        "anomalies",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "rule_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("anomaly_rules.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("anomaly_type", sa.String(50), nullable=False),
        sa.Column("severity", sa.String(20), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("source_table", sa.String(100), nullable=False),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "related_ids",
            postgresql.JSONB(),
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("score", sa.Float(), server_default=sa.text("0.0")),
        sa.Column(
            "details",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default="open",
        ),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "resolved_by_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("resolution_note", sa.Text(), nullable=True),
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        # Constraints
        sa.CheckConstraint(
            "score >= 0 AND score <= 1",
            name="ck_anomalies_score_range",
        ),
        sa.CheckConstraint(
            "severity IN ('info', 'warning', 'critical')",
            name="ck_anomalies_severity",
        ),
        sa.CheckConstraint(
            "status IN ('open', 'investigating', 'resolved', 'false_positive')",
            name="ck_anomalies_status",
        ),
    )

    op.create_index(
        "ix_anomalies_company_id",
        "anomalies",
        ["company_id"],
    )
    op.create_index(
        "ix_anomalies_rule_id",
        "anomalies",
        ["rule_id"],
    )
    op.create_index(
        "ix_anomalies_anomaly_type",
        "anomalies",
        ["anomaly_type"],
    )
    op.create_index(
        "ix_anomalies_company_status_created",
        "anomalies",
        ["company_id", "status", "created_at"],
    )
    op.create_index(
        "ix_anomalies_type_status",
        "anomalies",
        ["anomaly_type", "status"],
    )


def downgrade() -> None:
    op.drop_table("anomalies")
    op.drop_table("anomaly_rules")
