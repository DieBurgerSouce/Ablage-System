# -*- coding: utf-8 -*-
"""OCR Correction Feedback fuer ML Persistence (Phase 1.3).

Diese Migration erstellt Tabellen für persistente OCR-Korrekturen:
- ocr_correction_feedbacks: Einzelne Korrekturen von Usern
- ocr_backend_performance: Aggregierte Performance-Metriken

Vorteile gegenüber Redis-Only:
- Keine 30-Tage TTL Begrenzung
- SQL-Abfragen für komplexe Analysen
- ML-Training auf historischen Daten
- RLS für Multi-Tenancy

Revision ID: 115
Revises: 114
Create Date: 2026-01-23
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from alembic import op

# revision identifiers
revision = "115"
down_revision = "114"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create OCR feedback tables."""

    # OCR Correction Feedbacks - Einzelne Korrekturen
    op.create_table(
        "ocr_correction_feedbacks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "document_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
        sa.Column("backend", sa.String(50), nullable=False, index=True),
        sa.Column("backend_version", sa.String(50), nullable=True),
        sa.Column("field_name", sa.String(100), nullable=False, index=True),
        sa.Column("original_value", sa.Text, nullable=False),
        sa.Column("corrected_value", sa.Text, nullable=False),
        sa.Column("correction_type", sa.String(20), nullable=False, default="text"),
        sa.Column("confidence_before", sa.Float, nullable=True),
        sa.Column("confidence_after", sa.Float, nullable=True),
        sa.Column("document_type", sa.String(50), nullable=True, index=True),
        sa.Column("error_category", sa.String(50), nullable=True),
        sa.Column("edit_distance", sa.Integer, nullable=True),
        sa.Column("status", sa.String(20), nullable=False, default="pending"),
        sa.Column("processed_at", sa.DateTime, nullable=True),
        sa.Column("verification_source", sa.String(50), nullable=True),
        sa.Column("metadata", postgresql.JSONB, nullable=True, default={}),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, nullable=True, onupdate=sa.func.now()),
        sa.UniqueConstraint(
            "document_id", "field_name", "user_id",
            name="uq_ocr_feedback_doc_field_user"
        ),
        comment="OCR-Korrekturen für Self-Learning und Confidence-Kalibrierung",
    )

    # Composite Indexes für häufige Queries
    op.create_index(
        "ix_ocr_feedback_backend_field",
        "ocr_correction_feedbacks",
        ["backend", "field_name", "status"],
    )
    op.create_index(
        "ix_ocr_feedback_company_backend",
        "ocr_correction_feedbacks",
        ["company_id", "backend", "created_at"],
    )
    op.create_index(
        "ix_ocr_feedback_doctype_field",
        "ocr_correction_feedbacks",
        ["document_type", "field_name", "status"],
    )

    # OCR Backend Performance - Aggregierte Metriken
    op.create_table(
        "ocr_backend_performance",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("backend", sa.String(50), nullable=False, index=True),
        sa.Column("field_name", sa.String(100), nullable=False, index=True),
        sa.Column("document_type", sa.String(50), nullable=True, index=True),
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=True,
            index=True,
        ),
        sa.Column("total_corrections", sa.Integer, nullable=False, default=0),
        sa.Column("total_documents", sa.Integer, nullable=False, default=0),
        sa.Column("correction_rate", sa.Float, nullable=False, default=0.0),
        sa.Column("avg_confidence_before", sa.Float, nullable=True),
        sa.Column("avg_confidence_adjustment", sa.Float, nullable=True),
        sa.Column("umlaut_error_rate", sa.Float, nullable=True),
        sa.Column("digit_error_rate", sa.Float, nullable=True),
        sa.Column("period_start", sa.DateTime, nullable=False),
        sa.Column("period_end", sa.DateTime, nullable=False),
        sa.Column("calculated_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint(
            "backend", "field_name", "document_type", "company_id", "period_start",
            name="uq_backend_performance_period"
        ),
        comment="Aggregierte OCR-Backend Performance für Confidence-Tuning",
    )

    op.create_index(
        "ix_backend_perf_lookup",
        "ocr_backend_performance",
        ["backend", "field_name", "calculated_at"],
    )

    # RLS für Multi-Tenancy (falls PostgreSQL)
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        # RLS für ocr_correction_feedbacks
        op.execute("ALTER TABLE ocr_correction_feedbacks ENABLE ROW LEVEL SECURITY")
        op.execute("""
            CREATE POLICY ocr_feedback_tenant_isolation ON ocr_correction_feedbacks
                FOR ALL
                USING (
                    is_rls_bypass_enabled()
                    OR company_id = get_current_company_id()
                )
                WITH CHECK (
                    is_rls_bypass_enabled()
                    OR company_id = get_current_company_id()
                );
        """)

        # RLS für ocr_backend_performance (nullable company_id)
        op.execute("ALTER TABLE ocr_backend_performance ENABLE ROW LEVEL SECURITY")
        op.execute("""
            CREATE POLICY backend_perf_tenant_isolation ON ocr_backend_performance
                FOR ALL
                USING (
                    is_rls_bypass_enabled()
                    OR company_id IS NULL
                    OR company_id = get_current_company_id()
                )
                WITH CHECK (
                    is_rls_bypass_enabled()
                    OR company_id IS NULL
                    OR company_id = get_current_company_id()
                );
        """)


def downgrade() -> None:
    """Drop OCR feedback tables."""

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        # Drop RLS policies
        op.execute("DROP POLICY IF EXISTS backend_perf_tenant_isolation ON ocr_backend_performance")
        op.execute("DROP POLICY IF EXISTS ocr_feedback_tenant_isolation ON ocr_correction_feedbacks")
        op.execute("ALTER TABLE ocr_backend_performance DISABLE ROW LEVEL SECURITY")
        op.execute("ALTER TABLE ocr_correction_feedbacks DISABLE ROW LEVEL SECURITY")

    # Drop indexes
    op.drop_index("ix_backend_perf_lookup", table_name="ocr_backend_performance")
    op.drop_index("ix_ocr_feedback_doctype_field", table_name="ocr_correction_feedbacks")
    op.drop_index("ix_ocr_feedback_company_backend", table_name="ocr_correction_feedbacks")
    op.drop_index("ix_ocr_feedback_backend_field", table_name="ocr_correction_feedbacks")

    # Drop tables
    op.drop_table("ocr_backend_performance")
    op.drop_table("ocr_correction_feedbacks")
