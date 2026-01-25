# -*- coding: utf-8 -*-
"""Add business rules tables.

Revision ID: 112_add_business_rules
Revises: 111_add_delegation_tables
Create Date: 2026-01-21

Phase 4 der Strategischen Roadmap.

Tables:
- business_rules: Geschaeftsregeln mit Bedingungen und Aktionen
- rule_execution_logs: Audit-Log fuer Regel-Ausfuehrungen
- rule_sets: Gruppierung von Regeln zu Sets
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '112_add_business_rules'
down_revision: str = '111_add_delegation_tables'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ==========================================================================
    # Business Rules Table
    # ==========================================================================
    op.create_table(
        'business_rules',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('gen_random_uuid()')),

        # Identifikation
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('description', sa.Text, nullable=True),
        sa.Column('code', sa.String(50), nullable=True),

        # Multi-Tenant
        sa.Column('company_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('companies.id', ondelete='CASCADE'),
                  nullable=False),

        # Regel-Definition (JSON)
        sa.Column('condition', postgresql.JSONB, nullable=False,
                  comment='Bedingung als JSON-Struktur'),
        sa.Column('actions', postgresql.JSONB, nullable=False,
                  server_default='[]',
                  comment='Aktionen als JSON-Array'),
        sa.Column('else_actions', postgresql.JSONB, nullable=True,
                  comment='Aktionen wenn Regel NICHT matcht'),

        # Konfiguration
        sa.Column('priority', sa.Integer, nullable=False, server_default='50',
                  comment='Ausfuehrungsprioritaet (hoeher = frueher)'),
        sa.Column('category', sa.String(50), nullable=False, server_default='custom',
                  comment='approval, compliance, fraud, workflow, etc.'),
        sa.Column('is_active', sa.Boolean, nullable=False, server_default='true'),
        sa.Column('stop_on_match', sa.Boolean, nullable=False, server_default='false',
                  comment='Weitere Regeln nach Match stoppen'),

        # Anwendungsbereich
        sa.Column('applies_to_document_types', postgresql.JSONB, nullable=True,
                  comment='Nur fuer bestimmte Dokumenttypen'),
        sa.Column('applies_to_sources', postgresql.JSONB, nullable=True,
                  comment='Nur fuer bestimmte Quellen'),

        # Zeitliche Einschraenkung
        sa.Column('valid_from', sa.DateTime(timezone=True), nullable=True),
        sa.Column('valid_until', sa.DateTime(timezone=True), nullable=True),

        # Statistiken
        sa.Column('execution_count', sa.Integer, nullable=False, server_default='0',
                  comment='Wie oft ausgefuehrt'),
        sa.Column('match_count', sa.Integer, nullable=False, server_default='0',
                  comment='Wie oft gematcht'),
        sa.Column('last_executed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_matched_at', sa.DateTime(timezone=True), nullable=True),

        # Audit
        sa.Column('created_by_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('updated_by_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True),
                  server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),

        # Metadata
        sa.Column('metadata_json', postgresql.JSONB, server_default='{}'),
    )

    # Indexes fuer business_rules
    op.create_index('ix_business_rules_company_id', 'business_rules', ['company_id'])
    op.create_index('ix_business_rules_code', 'business_rules', ['code'])
    op.create_index('ix_rule_company_active', 'business_rules', ['company_id', 'is_active'])
    op.create_index('ix_rule_company_category', 'business_rules', ['company_id', 'category'])
    op.create_index('ix_rule_priority', 'business_rules', ['priority'])

    # Unique Constraint
    op.create_unique_constraint(
        'uq_rule_company_code',
        'business_rules',
        ['company_id', 'code']
    )

    # ==========================================================================
    # Rule Execution Logs Table
    # ==========================================================================
    op.create_table(
        'rule_execution_logs',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('gen_random_uuid()')),

        # Regel
        sa.Column('rule_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('business_rules.id', ondelete='CASCADE'),
                  nullable=False),

        # Kontext
        sa.Column('document_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('documents.id', ondelete='SET NULL'),
                  nullable=True),

        # Ergebnis
        sa.Column('matched', sa.Boolean, nullable=False),
        sa.Column('condition_details', postgresql.JSONB, server_default='{}'),
        sa.Column('triggered_actions', postgresql.JSONB, server_default='[]'),
        sa.Column('execution_errors', postgresql.JSONB, server_default='[]'),

        # Kontext-Snapshot (fuer Debugging)
        sa.Column('context_snapshot', postgresql.JSONB, server_default='{}'),

        # Ausfuehrung
        sa.Column('dry_run', sa.Boolean, nullable=False, server_default='false'),
        sa.Column('executed_at', sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column('execution_time_ms', sa.Integer, nullable=True,
                  comment='Ausfuehrungszeit in Millisekunden'),
    )

    # Indexes fuer rule_execution_logs
    op.create_index('ix_rule_execution_logs_rule_id', 'rule_execution_logs', ['rule_id'])
    op.create_index('ix_rule_execution_logs_document_id', 'rule_execution_logs', ['document_id'])
    op.create_index('ix_rule_log_rule_date', 'rule_execution_logs', ['rule_id', 'executed_at'])
    op.create_index('ix_rule_log_document', 'rule_execution_logs', ['document_id', 'executed_at'])
    op.create_index('ix_rule_execution_logs_executed_at', 'rule_execution_logs', ['executed_at'])

    # ==========================================================================
    # Rule Sets Table
    # ==========================================================================
    op.create_table(
        'rule_sets',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('gen_random_uuid()')),

        # Identifikation
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('description', sa.Text, nullable=True),
        sa.Column('version', sa.String(20), nullable=False, server_default='1.0.0'),

        # Multi-Tenant
        sa.Column('company_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('companies.id', ondelete='CASCADE'),
                  nullable=False),

        # Konfiguration
        sa.Column('is_active', sa.Boolean, nullable=False, server_default='true'),
        sa.Column('is_default', sa.Boolean, nullable=False, server_default='false',
                  comment='Standard-Set fuer Company'),

        # Regeln (IDs)
        sa.Column('rule_ids', postgresql.JSONB, nullable=False, server_default='[]',
                  comment='Geordnete Liste der Regel-IDs'),

        # Audit
        sa.Column('created_by_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True),
                  server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
    )

    # Indexes fuer rule_sets
    op.create_index('ix_rule_sets_company_id', 'rule_sets', ['company_id'])
    op.create_index('ix_ruleset_company_active', 'rule_sets', ['company_id', 'is_active'])

    # Unique Constraint
    op.create_unique_constraint(
        'uq_ruleset_company_name_version',
        'rule_sets',
        ['company_id', 'name', 'version']
    )

    # ==========================================================================
    # Enable RLS on all tables
    # ==========================================================================
    op.execute('ALTER TABLE business_rules ENABLE ROW LEVEL SECURITY')
    op.execute('ALTER TABLE rule_execution_logs ENABLE ROW LEVEL SECURITY')
    op.execute('ALTER TABLE rule_sets ENABLE ROW LEVEL SECURITY')

    # RLS Policies fuer business_rules
    op.execute("""
        CREATE POLICY business_rules_tenant_isolation ON business_rules
        FOR ALL
        USING (company_id = COALESCE(
            current_setting('app.current_company_id', true)::uuid,
            company_id
        ))
    """)

    # RLS Policies fuer rule_sets
    op.execute("""
        CREATE POLICY rule_sets_tenant_isolation ON rule_sets
        FOR ALL
        USING (company_id = COALESCE(
            current_setting('app.current_company_id', true)::uuid,
            company_id
        ))
    """)

    # rule_execution_logs benoetigt Join-basierte Policy
    op.execute("""
        CREATE POLICY rule_execution_logs_tenant_isolation ON rule_execution_logs
        FOR ALL
        USING (
            rule_id IN (
                SELECT id FROM business_rules
                WHERE company_id = COALESCE(
                    current_setting('app.current_company_id', true)::uuid,
                    company_id
                )
            )
        )
    """)


def downgrade() -> None:
    # Drop RLS Policies
    op.execute('DROP POLICY IF EXISTS rule_execution_logs_tenant_isolation ON rule_execution_logs')
    op.execute('DROP POLICY IF EXISTS rule_sets_tenant_isolation ON rule_sets')
    op.execute('DROP POLICY IF EXISTS business_rules_tenant_isolation ON business_rules')

    # Disable RLS
    op.execute('ALTER TABLE rule_execution_logs DISABLE ROW LEVEL SECURITY')
    op.execute('ALTER TABLE rule_sets DISABLE ROW LEVEL SECURITY')
    op.execute('ALTER TABLE business_rules DISABLE ROW LEVEL SECURITY')

    # Drop tables in reverse order (due to foreign keys)
    op.drop_table('rule_execution_logs')
    op.drop_table('rule_sets')
    op.drop_table('business_rules')
