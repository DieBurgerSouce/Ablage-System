# -*- coding: utf-8 -*-
"""Add AI Ethics and Bias Detection tables

Revision ID: 128
Revises: 127
Create Date: 2026-01-28

Tabellen:
- ai_ethics_audits: Einzelne Ethik-Audits von KI-Entscheidungen
- bias_reports: Aggregierte Bias-Berichte nach Kategorie

Features:
- Bias-Detection in Risk-Scoring, Entity-Matching, Klassifikation
- Fairness-Metriken (Disparate Impact, Equal Opportunity)
- Automatische Guardrails gegen unfaire Entscheidungen
- Empfehlungen zur Bias-Reduktion
- Audit-Trail für alle KI-Entscheidungen

Feinpoliert und durchdacht - Deutsche Präzision.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '128'
down_revision = '127'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ==========================================================================
    # AI Ethics Audits - Einzelne KI-Entscheidungen
    # ==========================================================================
    op.create_table(
        'ai_ethics_audits',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),

        # Multi-Tenant
        sa.Column('company_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('companies.id', ondelete='CASCADE'),
                  nullable=False, index=True),

        # Audit-Metadaten
        sa.Column('audit_type', sa.String(50), nullable=False,
                  comment='bias_check, fairness_review, guardrail_check'),
        sa.Column('decision_type', sa.String(100), nullable=True,
                  comment='z.B. risk_scoring, entity_matching, document_classification'),
        sa.Column('decision_id', postgresql.UUID(as_uuid=True), nullable=True,
                  comment='ID der geprüften Entscheidung'),

        # Audit-Ergebnis
        sa.Column('result', sa.String(20), nullable=False,
                  comment='passed, warning, failed'),
        sa.Column('fairness_score', sa.Float, nullable=True,
                  comment='Fairness-Score (0.0 = unfair, 1.0 = fair)'),

        # Details und Empfehlungen (JSONB)
        sa.Column('details', postgresql.JSONB, nullable=False, server_default='{}',
                  comment='Detaillierte Audit-Ergebnisse (z.B. Disparate Impact)'),
        sa.Column('recommendations', postgresql.JSONB, nullable=False,
                  server_default='[]',
                  comment='Array von Empfehlungen zur Bias-Reduktion'),

        # Verantwortlichkeit
        sa.Column('created_by_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('users.id', ondelete='SET NULL'),
                  nullable=True,
                  comment='User der das Audit ausgelöst hat (null = automatisch)'),

        # Timestamps
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.func.now()),
    )

    # Indexes für Queries
    # Note: company_id index already created by index=True on column
    op.create_index('ix_ai_ethics_type',
                    'ai_ethics_audits',
                    ['audit_type', 'decision_type'])
    op.create_index('ix_ai_ethics_created',
                    'ai_ethics_audits',
                    ['created_at'])

    # ==========================================================================
    # Bias Reports - Aggregierte Berichte
    # ==========================================================================
    op.create_table(
        'bias_reports',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),

        # Multi-Tenant
        sa.Column('company_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('companies.id', ondelete='CASCADE'),
                  nullable=False, index=True),

        # Report-Metadaten
        sa.Column('report_type', sa.String(50), nullable=False,
                  comment='risk_scoring, entity_matching, document_classification'),
        sa.Column('overall_fairness', sa.Float, nullable=False,
                  comment='Gesamt-Fairness-Score (0.0 - 1.0)'),

        # Bias-Dimensionen (JSONB)
        sa.Column('dimensions', postgresql.JSONB, nullable=False, server_default='[]',
                  comment='Array von Bias-Dimensionen mit Metriken'),

        # Impact
        sa.Column('affected_entities', sa.Integer, nullable=False, server_default='0',
                  comment='Anzahl betroffener Entities'),

        # Empfehlungen (JSONB)
        sa.Column('recommendations', postgresql.JSONB, nullable=False,
                  server_default='[]',
                  comment='Array von priorisierten Empfehlungen'),

        # Timestamps
        sa.Column('generated_at', sa.DateTime(timezone=True),
                  server_default=sa.func.now(),
                  comment='Zeitpunkt der Report-Generierung'),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True,
                  comment='Ablaufdatum (z.B. nach 30 Tagen)'),
    )

    # Indexes für Queries
    # Note: company_id index already created by index=True on column
    op.create_index('ix_bias_reports_type',
                    'bias_reports',
                    ['report_type'])
    op.create_index('ix_bias_reports_generated',
                    'bias_reports',
                    ['generated_at'])

    # ==========================================================================
    # RLS Policies für Multi-Tenant Isolation
    # ==========================================================================

    # AI Ethics Audits
    op.execute("ALTER TABLE ai_ethics_audits ENABLE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY ai_ethics_audits_company_isolation ON ai_ethics_audits
        FOR ALL
        USING (company_id = current_setting('app.current_company_id', true)::uuid)
    """)

    # Bias Reports
    op.execute("ALTER TABLE bias_reports ENABLE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY bias_reports_company_isolation ON bias_reports
        FOR ALL
        USING (company_id = current_setting('app.current_company_id', true)::uuid)
    """)


def downgrade() -> None:
    # Drop RLS policies
    op.execute("DROP POLICY IF EXISTS bias_reports_company_isolation ON bias_reports")
    op.execute("DROP POLICY IF EXISTS ai_ethics_audits_company_isolation ON ai_ethics_audits")

    # Disable RLS
    op.execute("ALTER TABLE bias_reports DISABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE ai_ethics_audits DISABLE ROW LEVEL SECURITY")

    # Drop tables
    op.drop_table('bias_reports')
    op.drop_table('ai_ethics_audits')
