# -*- coding: utf-8 -*-
"""Add active learning queue and metrics tables.

Revision ID: 245
Revises: 244
Create Date: 2026-02-21

Phase 2.4: Active Learning Pipeline
- active_learning_queue: Priorisierte Review-Queue fuer OCR-Korrekturen
- active_learning_metrics: Tagesbasierte Impact-Metriken
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "245"
down_revision = "244"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create active learning tables."""

    # ==========================================================================
    # Table: active_learning_queue
    # ==========================================================================
    op.create_table(
        "active_learning_queue",

        # Primary Key
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),

        # Document Reference
        sa.Column(
            "document_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),

        # Multi-Tenant
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),

        # Scoring
        sa.Column("priority_score", sa.Float, nullable=False),
        sa.Column("uncertainty_score", sa.Float, nullable=False),
        sa.Column("estimated_impact", sa.Float, nullable=False, server_default="0.0"),

        # Queue Context
        sa.Column("queue_reason", sa.String(100), nullable=False),
        sa.Column("ocr_backend", sa.String(50), nullable=True),
        sa.Column("ocr_confidence", sa.Float, nullable=True),
        sa.Column("field_focus", postgresql.JSONB, server_default="[]"),

        # Status & Review
        sa.Column("status", sa.String(20), nullable=False, server_default="queued"),
        sa.Column(
            "reviewed_by_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("correction_data", postgresql.JSONB, nullable=True),
        sa.Column("training_batch_id", postgresql.UUID(as_uuid=True), nullable=True),

        # Timestamps
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),

        comment="Active Learning Queue fuer priorisierte OCR-Korrekturen",
    )

    # Composite index for queue retrieval: company + status + priority DESC
    op.create_index(
        "ix_al_queue_company_status_priority",
        "active_learning_queue",
        ["company_id", "status", sa.text("priority_score DESC")],
    )

    # ==========================================================================
    # Table: active_learning_metrics
    # ==========================================================================
    op.create_table(
        "active_learning_metrics",

        # Primary Key
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),

        # Identifikation
        sa.Column("metric_date", sa.Date, nullable=False),
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),

        # Zaehler
        sa.Column("total_reviewed", sa.Integer, nullable=False, server_default="0"),
        sa.Column("total_corrections", sa.Integer, nullable=False, server_default="0"),
        sa.Column(
            "estimated_errors_prevented",
            sa.Integer,
            nullable=False,
            server_default="0",
        ),

        # Confidence-Tracking
        sa.Column("avg_confidence_before", sa.Float, nullable=True),
        sa.Column("avg_confidence_after", sa.Float, nullable=True),

        # Fehlermuster
        sa.Column("top_error_patterns", postgresql.JSONB, server_default="[]"),

        # Timestamps
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),

        # Unique Constraint
        sa.UniqueConstraint(
            "metric_date",
            "company_id",
            name="uq_al_metrics_date_company",
        ),

        comment="Active Learning Impact-Metriken pro Tag und Company",
    )


def downgrade() -> None:
    """Drop active learning tables."""
    op.drop_table("active_learning_metrics")
    op.drop_index("ix_al_queue_company_status_priority", table_name="active_learning_queue")
    op.drop_table("active_learning_queue")
