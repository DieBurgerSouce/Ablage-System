"""Add tenant subscription and rate limit system.

Revision ID: 104_tenant_subscription
Revises: 103_enhance_document_comments
Create Date: 2026-01-19

Multi-Tenant Hardening:
- Subscription Tiers (Free, Basic, Professional, Enterprise)
- Tenant-spezifische Rate Limits
- Usage Tracking und Metriken
- Billing-Vorbereitung
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '104_tenant_subscription'
down_revision = '103_enhance_document_comments'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ==========================================
    # 1. Subscription Tier Enum
    # ==========================================
    subscription_tier_enum = postgresql.ENUM(
        'free', 'basic', 'professional', 'enterprise',
        name='subscription_tier',
        create_type=False
    )
    subscription_tier_enum.create(op.get_bind(), checkfirst=True)

    # ==========================================
    # 2. Subscription-Felder zur Company-Tabelle
    # ==========================================
    op.add_column(
        'companies',
        sa.Column(
            'subscription_tier',
            sa.String(50),
            nullable=False,
            server_default='free',
            comment='Abonnement-Stufe: free, basic, professional, enterprise'
        )
    )
    op.add_column(
        'companies',
        sa.Column(
            'subscription_started_at',
            sa.DateTime(timezone=True),
            nullable=True,
            comment='Beginn des aktuellen Abonnements'
        )
    )
    op.add_column(
        'companies',
        sa.Column(
            'subscription_expires_at',
            sa.DateTime(timezone=True),
            nullable=True,
            comment='Ablaufdatum des Abonnements (null = unbegrenzt)'
        )
    )
    op.add_column(
        'companies',
        sa.Column(
            'billing_email',
            sa.String(255),
            nullable=True,
            comment='E-Mail fuer Rechnungen'
        )
    )
    op.add_column(
        'companies',
        sa.Column(
            'billing_address',
            postgresql.JSONB,
            nullable=True,
            server_default='{}',
            comment='Rechnungsadresse als JSON'
        )
    )
    op.add_column(
        'companies',
        sa.Column(
            'payment_method',
            sa.String(50),
            nullable=True,
            comment='Zahlungsmethode: invoice, sepa, card'
        )
    )
    op.add_column(
        'companies',
        sa.Column(
            'max_users',
            sa.Integer,
            nullable=False,
            server_default='5',
            comment='Maximale Anzahl Benutzer'
        )
    )
    op.add_column(
        'companies',
        sa.Column(
            'max_documents_per_month',
            sa.Integer,
            nullable=False,
            server_default='100',
            comment='Maximale Dokumente pro Monat'
        )
    )
    op.add_column(
        'companies',
        sa.Column(
            'max_storage_gb',
            sa.Integer,
            nullable=False,
            server_default='5',
            comment='Maximaler Speicher in GB'
        )
    )
    op.add_column(
        'companies',
        sa.Column(
            'features_enabled',
            postgresql.JSONB,
            nullable=False,
            server_default='["ocr", "search", "export"]',
            comment='Aktivierte Features als JSON-Array'
        )
    )

    # Indexes fuer Subscription-Queries
    op.create_index(
        'ix_companies_subscription_tier',
        'companies',
        ['subscription_tier']
    )
    op.create_index(
        'ix_companies_subscription_expires',
        'companies',
        ['subscription_expires_at']
    )

    # ==========================================
    # 3. Tenant Rate Limit Configurations
    # ==========================================
    op.create_table(
        'tenant_rate_limits',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('company_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('companies.id', ondelete='CASCADE'), nullable=False),

        # Endpoint-spezifische Limits
        sa.Column('endpoint_pattern', sa.String(255), nullable=False, comment='Endpoint-Pattern (z.B. /api/v1/documents/*)'),
        sa.Column('requests_per_minute', sa.Integer, nullable=False, default=100),
        sa.Column('requests_per_hour', sa.Integer, nullable=False, default=1000),
        sa.Column('requests_per_day', sa.Integer, nullable=False, default=10000),

        # Burst-Limits
        sa.Column('burst_limit', sa.Integer, nullable=False, default=50, comment='Max Requests in 1 Sekunde'),

        # Spezielle Limits
        sa.Column('ocr_requests_per_hour', sa.Integer, nullable=True, comment='OCR-spezifisches Limit'),
        sa.Column('batch_requests_per_hour', sa.Integer, nullable=True, comment='Batch-Operations Limit'),
        sa.Column('export_requests_per_day', sa.Integer, nullable=True, comment='Export-Limit pro Tag'),

        # Flags
        sa.Column('is_custom', sa.Boolean, nullable=False, default=False, comment='True wenn manuell angepasst'),
        sa.Column('is_active', sa.Boolean, nullable=False, default=True),

        # Audit
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.Column('created_by_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),

        # Constraints
        sa.UniqueConstraint('company_id', 'endpoint_pattern', name='uq_tenant_rate_limits_company_endpoint'),
    )

    op.create_index('ix_tenant_rate_limits_company', 'tenant_rate_limits', ['company_id'])
    op.create_index('ix_tenant_rate_limits_endpoint', 'tenant_rate_limits', ['endpoint_pattern'])

    # ==========================================
    # 4. Tenant Usage Metrics (fuer Dashboard)
    # ==========================================
    op.create_table(
        'tenant_usage_metrics',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('company_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('companies.id', ondelete='CASCADE'), nullable=False),

        # Zeitraum
        sa.Column('period_type', sa.String(20), nullable=False, comment='hourly, daily, monthly'),
        sa.Column('period_start', sa.DateTime(timezone=True), nullable=False),
        sa.Column('period_end', sa.DateTime(timezone=True), nullable=False),

        # API Metriken
        sa.Column('total_requests', sa.BigInteger, nullable=False, default=0),
        sa.Column('rate_limited_requests', sa.BigInteger, nullable=False, default=0),
        sa.Column('failed_requests', sa.BigInteger, nullable=False, default=0),
        sa.Column('avg_response_time_ms', sa.Float, nullable=True),
        sa.Column('p95_response_time_ms', sa.Float, nullable=True),
        sa.Column('p99_response_time_ms', sa.Float, nullable=True),

        # OCR Metriken
        sa.Column('documents_processed', sa.Integer, nullable=False, default=0),
        sa.Column('pages_processed', sa.Integer, nullable=False, default=0),
        sa.Column('ocr_processing_time_ms', sa.BigInteger, nullable=False, default=0),

        # Storage Metriken
        sa.Column('storage_used_bytes', sa.BigInteger, nullable=False, default=0),
        sa.Column('documents_stored', sa.Integer, nullable=False, default=0),

        # User Metriken
        sa.Column('active_users', sa.Integer, nullable=False, default=0),
        sa.Column('unique_sessions', sa.Integer, nullable=False, default=0),

        # Endpoint-Breakdown
        sa.Column('endpoint_breakdown', postgresql.JSONB, nullable=True, comment='Requests pro Endpoint'),

        # Audit
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),

        # Constraints
        sa.UniqueConstraint('company_id', 'period_type', 'period_start', name='uq_tenant_metrics_period'),
    )

    op.create_index('ix_tenant_metrics_company', 'tenant_usage_metrics', ['company_id'])
    op.create_index('ix_tenant_metrics_period', 'tenant_usage_metrics', ['period_type', 'period_start'])
    op.create_index('ix_tenant_metrics_company_period', 'tenant_usage_metrics', ['company_id', 'period_type', 'period_start'])

    # ==========================================
    # 5. Rate Limit Violations Log
    # ==========================================
    op.create_table(
        'rate_limit_violations',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('company_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('companies.id', ondelete='CASCADE'), nullable=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),

        # Violation Details
        sa.Column('endpoint', sa.String(255), nullable=False),
        sa.Column('method', sa.String(10), nullable=False),
        sa.Column('ip_address', sa.String(45), nullable=False),
        sa.Column('user_agent', sa.String(500), nullable=True),

        # Limit Info
        sa.Column('limit_type', sa.String(50), nullable=False, comment='minute, hour, day, burst'),
        sa.Column('limit_value', sa.Integer, nullable=False),
        sa.Column('current_count', sa.Integer, nullable=False),
        sa.Column('retry_after_seconds', sa.Integer, nullable=True),

        # Timestamp
        sa.Column('occurred_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_index('ix_rate_violations_company', 'rate_limit_violations', ['company_id'])
    op.create_index('ix_rate_violations_user', 'rate_limit_violations', ['user_id'])
    op.create_index('ix_rate_violations_time', 'rate_limit_violations', ['occurred_at'])
    op.create_index('ix_rate_violations_endpoint', 'rate_limit_violations', ['endpoint'])

    # ==========================================
    # 6. Subscription Tier Defaults
    # ==========================================
    op.create_table(
        'subscription_tier_defaults',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('tier', sa.String(50), nullable=False, unique=True),

        # Limits
        sa.Column('max_users', sa.Integer, nullable=False),
        sa.Column('max_documents_per_month', sa.Integer, nullable=False),
        sa.Column('max_storage_gb', sa.Integer, nullable=False),

        # Rate Limits
        sa.Column('requests_per_minute', sa.Integer, nullable=False),
        sa.Column('requests_per_hour', sa.Integer, nullable=False),
        sa.Column('requests_per_day', sa.Integer, nullable=False),
        sa.Column('ocr_requests_per_hour', sa.Integer, nullable=False),
        sa.Column('batch_requests_per_hour', sa.Integer, nullable=False),

        # Features
        sa.Column('features_enabled', postgresql.JSONB, nullable=False),

        # Pricing (fuer Billing-Vorbereitung)
        sa.Column('price_monthly_eur', sa.Numeric(10, 2), nullable=True),
        sa.Column('price_yearly_eur', sa.Numeric(10, 2), nullable=True),

        # Audit
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
    )

    # Seed Default Tiers
    op.execute("""
        INSERT INTO subscription_tier_defaults
        (id, tier, max_users, max_documents_per_month, max_storage_gb,
         requests_per_minute, requests_per_hour, requests_per_day,
         ocr_requests_per_hour, batch_requests_per_hour, features_enabled,
         price_monthly_eur, price_yearly_eur)
        VALUES
        (gen_random_uuid(), 'free', 3, 50, 1,
         30, 300, 1000, 10, 2,
         '["ocr", "search", "export_csv"]',
         0, 0),
        (gen_random_uuid(), 'basic', 10, 500, 10,
         60, 600, 5000, 50, 10,
         '["ocr", "search", "export_csv", "export_pdf", "api_access"]',
         29.99, 299.99),
        (gen_random_uuid(), 'professional', 50, 5000, 100,
         120, 1200, 20000, 200, 50,
         '["ocr", "search", "export_csv", "export_pdf", "api_access", "advanced_analytics", "workflow", "integrations"]',
         99.99, 999.99),
        (gen_random_uuid(), 'enterprise', 999, 999999, 9999,
         1000, 10000, 100000, 1000, 500,
         '["ocr", "search", "export_csv", "export_pdf", "api_access", "advanced_analytics", "workflow", "integrations", "sso", "audit_log", "custom_branding", "priority_support", "dedicated_resources"]',
         NULL, NULL)
    """)


def downgrade() -> None:
    # Drop tables
    op.drop_table('subscription_tier_defaults')
    op.drop_table('rate_limit_violations')
    op.drop_table('tenant_usage_metrics')
    op.drop_table('tenant_rate_limits')

    # Drop indexes
    op.drop_index('ix_companies_subscription_tier', 'companies')
    op.drop_index('ix_companies_subscription_expires', 'companies')

    # Drop columns from companies
    op.drop_column('companies', 'features_enabled')
    op.drop_column('companies', 'max_storage_gb')
    op.drop_column('companies', 'max_documents_per_month')
    op.drop_column('companies', 'max_users')
    op.drop_column('companies', 'payment_method')
    op.drop_column('companies', 'billing_address')
    op.drop_column('companies', 'billing_email')
    op.drop_column('companies', 'subscription_expires_at')
    op.drop_column('companies', 'subscription_started_at')
    op.drop_column('companies', 'subscription_tier')

    # Drop enum
    postgresql.ENUM(name='subscription_tier').drop(op.get_bind(), checkfirst=True)
