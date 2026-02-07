# -*- coding: utf-8 -*-
"""
Add Contract Management V2 Enhancements tables.

- ContractClause: Extracted contract clauses
- ContractBenchmark: Market benchmark data
- ContractCancellation: Cancellation requests and tracking
- ContractCostAnalysis: Cost analysis records

Revision ID: 203_add_contract_v2_enhancements
Revises: 202_add_autonomous_trust_system
Create Date: 2026-02-02

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB


# revision identifiers
revision = '203_add_contract_v2_enhancements'
down_revision = '202_add_autonomous_trust_system'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add Contract Management V2 tables."""

    # ==========================================================================
    # ContractClause - Extracted clauses from contracts
    # ==========================================================================
    op.create_table(
        'contract_clauses',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('contract_id', UUID(as_uuid=True), sa.ForeignKey('contracts.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('company_id', UUID(as_uuid=True), sa.ForeignKey('companies.id', ondelete='CASCADE'), nullable=False, index=True),

        # Clause identification
        sa.Column('clause_type', sa.String(50), nullable=False, index=True),
        # Types: price_adjustment, minimum_term, auto_renewal, penalty, termination_condition,
        #        liability, confidentiality, warranty, jurisdiction, payment_terms, etc.

        # Original text
        sa.Column('clause_text', sa.Text, nullable=False),
        sa.Column('clause_text_hash', sa.String(64), nullable=True),  # SHA-256 for dedup

        # Extraction metadata
        sa.Column('confidence', sa.Numeric(5, 4), nullable=False, default=0.0),
        sa.Column('extraction_method', sa.String(50), nullable=True),  # nlp, regex, manual
        sa.Column('source_page', sa.Integer, nullable=True),
        sa.Column('source_position', JSONB, nullable=True),  # {"start": 100, "end": 500}

        # Structured extracted values (clause-type specific)
        sa.Column('extracted_value', JSONB, nullable=True),
        # Examples:
        # price_adjustment: {"type": "index", "index_name": "VPI", "interval": "annual", "cap_percent": 5}
        # minimum_term: {"months": 24, "start_date": "2026-01-01"}
        # auto_renewal: {"enabled": true, "period_months": 12, "notice_days": 90}
        # penalty: {"type": "late_delivery", "percent": 0.5, "max_percent": 5}
        # termination_condition: {"type": "breach", "cure_period_days": 30}

        # Status
        sa.Column('is_active', sa.Boolean, default=True, nullable=False),
        sa.Column('is_verified', sa.Boolean, default=False, nullable=False),
        sa.Column('verified_by_id', UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('verified_at', sa.DateTime(timezone=True), nullable=True),

        # Risk assessment
        sa.Column('risk_level', sa.String(20), nullable=True),  # low, medium, high, critical
        sa.Column('risk_notes', sa.Text, nullable=True),

        # Timestamps
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
    )

    # Indexes for contract_clauses
    op.create_index('ix_contract_clauses_contract_type', 'contract_clauses', ['contract_id', 'clause_type'])
    op.create_index('ix_contract_clauses_company_type', 'contract_clauses', ['company_id', 'clause_type'])
    op.create_index('ix_contract_clauses_text_hash', 'contract_clauses', ['clause_text_hash'])

    # ==========================================================================
    # ContractBenchmark - Market benchmark data for comparison
    # ==========================================================================
    op.create_table(
        'contract_benchmarks',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),

        # Category and metric
        sa.Column('category', sa.String(100), nullable=False, index=True),
        # Categories: software_licenses, office_lease, vehicle_lease, maintenance,
        #             consulting, cleaning, security, telecom, insurance, etc.

        sa.Column('metric', sa.String(100), nullable=False, index=True),
        # Metrics: avg_monthly_cost, avg_term_months, avg_notice_days,
        #          avg_discount_percent, avg_price_adjustment_percent, etc.

        # Value and statistics
        sa.Column('value', sa.Numeric(15, 4), nullable=False),
        sa.Column('min_value', sa.Numeric(15, 4), nullable=True),
        sa.Column('max_value', sa.Numeric(15, 4), nullable=True),
        sa.Column('percentile_25', sa.Numeric(15, 4), nullable=True),
        sa.Column('percentile_50', sa.Numeric(15, 4), nullable=True),
        sa.Column('percentile_75', sa.Numeric(15, 4), nullable=True),
        sa.Column('std_deviation', sa.Numeric(15, 4), nullable=True),

        # Sample and validity
        sa.Column('sample_size', sa.Integer, nullable=False, default=0),
        sa.Column('region', sa.String(50), default='DACH', nullable=False),  # DACH, EU, global
        sa.Column('industry', sa.String(100), nullable=True),  # Optional industry filter
        sa.Column('valid_from', sa.Date, nullable=False),
        sa.Column('valid_until', sa.Date, nullable=True),

        # Source
        sa.Column('source', sa.String(255), nullable=True),  # Internal, MarktMonitor, etc.
        sa.Column('source_url', sa.String(500), nullable=True),

        # Metadata
        sa.Column('notes', sa.Text, nullable=True),
        sa.Column('metadata', JSONB, nullable=True),

        # Timestamps
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
    )

    # Indexes for contract_benchmarks
    op.create_index('ix_benchmarks_category_metric', 'contract_benchmarks', ['category', 'metric'])
    op.create_index('ix_benchmarks_region_industry', 'contract_benchmarks', ['region', 'industry'])
    op.create_index('ix_benchmarks_valid_from', 'contract_benchmarks', ['valid_from'])

    # Unique constraint for benchmark data points
    op.create_unique_constraint(
        'uq_benchmark_category_metric_region_industry_valid',
        'contract_benchmarks',
        ['category', 'metric', 'region', 'industry', 'valid_from']
    )

    # ==========================================================================
    # ContractCancellation - Cancellation requests and tracking
    # ==========================================================================
    op.create_table(
        'contract_cancellations',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('contract_id', UUID(as_uuid=True), sa.ForeignKey('contracts.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('company_id', UUID(as_uuid=True), sa.ForeignKey('companies.id', ondelete='CASCADE'), nullable=False, index=True),

        # Cancellation details
        sa.Column('cancellation_type', sa.String(50), nullable=False),
        # Types: ordinary (ordentlich), extraordinary (ausserordentlich), mutual (einvernehmlich)

        sa.Column('reason', sa.Text, nullable=True),
        sa.Column('reason_code', sa.String(50), nullable=True),
        # Codes: non_renewal, cost_reduction, service_issue, contract_breach, other

        # Dates
        sa.Column('requested_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('effective_date', sa.Date, nullable=False),
        sa.Column('latest_send_date', sa.Date, nullable=False),  # Must be sent before this date
        sa.Column('scheduled_send_date', sa.Date, nullable=True),  # When to auto-send

        # Letter content
        sa.Column('letter_template', sa.String(100), nullable=True),  # Template used
        sa.Column('letter_content', sa.Text, nullable=True),  # Generated letter
        sa.Column('letter_language', sa.String(10), default='de', nullable=False),
        sa.Column('recipient_name', sa.String(255), nullable=True),
        sa.Column('recipient_address', sa.Text, nullable=True),
        sa.Column('recipient_email', sa.String(255), nullable=True),

        # Sending
        sa.Column('send_method', sa.String(50), nullable=True),
        # Methods: email, post, fax, portal, manual

        sa.Column('sent_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('sent_by_id', UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('sent_reference', sa.String(255), nullable=True),  # Post tracking, email message ID

        # Acknowledgment
        sa.Column('acknowledgment_received', sa.Boolean, default=False, nullable=False),
        sa.Column('acknowledgment_date', sa.DateTime(timezone=True), nullable=True),
        sa.Column('acknowledgment_reference', sa.String(255), nullable=True),
        sa.Column('acknowledgment_document_id', UUID(as_uuid=True), sa.ForeignKey('documents.id', ondelete='SET NULL'), nullable=True),

        # Status
        sa.Column('status', sa.String(30), nullable=False, default='draft'),
        # Status: draft, pending, scheduled, sent, acknowledged, rejected, completed, cancelled

        # Workflow
        sa.Column('requested_by_id', UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('approved_by_id', UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('approved_at', sa.DateTime(timezone=True), nullable=True),

        # Metadata
        sa.Column('metadata', JSONB, nullable=True),
        sa.Column('notes', sa.Text, nullable=True),

        # Timestamps
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
    )

    # Indexes for contract_cancellations
    op.create_index('ix_cancellations_contract', 'contract_cancellations', ['contract_id'])
    op.create_index('ix_cancellations_company_status', 'contract_cancellations', ['company_id', 'status'])
    op.create_index('ix_cancellations_effective_date', 'contract_cancellations', ['effective_date'])
    op.create_index('ix_cancellations_scheduled_send', 'contract_cancellations', ['scheduled_send_date', 'status'])

    # ==========================================================================
    # ContractCostAnalysis - Cost analysis cache
    # ==========================================================================
    op.create_table(
        'contract_cost_analyses',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('contract_id', UUID(as_uuid=True), sa.ForeignKey('contracts.id', ondelete='CASCADE'), nullable=False, unique=True),
        sa.Column('company_id', UUID(as_uuid=True), sa.ForeignKey('companies.id', ondelete='CASCADE'), nullable=False, index=True),

        # Cost projections
        sa.Column('monthly_cost', sa.Numeric(15, 2), nullable=True),
        sa.Column('annual_cost', sa.Numeric(15, 2), nullable=True),
        sa.Column('total_contract_cost', sa.Numeric(15, 2), nullable=True),
        sa.Column('remaining_cost', sa.Numeric(15, 2), nullable=True),
        sa.Column('currency', sa.String(3), default='EUR', nullable=False),

        # Cost breakdown by category
        sa.Column('cost_breakdown', JSONB, nullable=True),
        # Example: {"base": 1000, "maintenance": 200, "support": 100, "fees": 50}

        # Trend analysis
        sa.Column('cost_trend', sa.String(20), nullable=True),  # increasing, stable, decreasing
        sa.Column('trend_percent', sa.Numeric(5, 2), nullable=True),
        sa.Column('cost_history', JSONB, nullable=True),
        # Example: [{"date": "2025-01", "cost": 1000}, {"date": "2025-06", "cost": 1050}]

        # Optimization
        sa.Column('optimization_potential', sa.Numeric(15, 2), nullable=True),
        sa.Column('optimization_suggestions', JSONB, nullable=True),
        # Example: [{"type": "renegotiate", "potential": 500, "description": "..."}]

        # Benchmark comparison
        sa.Column('benchmark_comparison', JSONB, nullable=True),
        # Example: {"percentile": 75, "vs_average": 1.15, "recommendation": "above_average"}

        # Analysis metadata
        sa.Column('analyzed_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('analysis_version', sa.String(20), nullable=True),

        # Timestamps
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
    )

    # Indexes
    op.create_index('ix_cost_analyses_company', 'contract_cost_analyses', ['company_id'])
    op.create_index('ix_cost_analyses_trend', 'contract_cost_analyses', ['cost_trend'])


def downgrade() -> None:
    """Remove Contract Management V2 tables."""
    op.drop_table('contract_cost_analyses')
    op.drop_table('contract_cancellations')
    op.drop_table('contract_benchmarks')
    op.drop_table('contract_clauses')
