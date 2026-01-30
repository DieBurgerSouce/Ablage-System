"""Add GoBD Compliance Check tracking for Vision 2026.

Revision ID: 137_add_gobd_compliance_checks
Revises: 136_add_document_versioning_signatures
Create Date: 2026-01-28

Vision 2026 Feature: Audit & Compliance Dashboard
- GoBDComplianceCheck: Track compliance status over time
- Automated compliance checking with remediation steps
- Dashboard data for compliance visualization

Extends existing GoBD infrastructure (DocumentArchive, DocumentAccessLog).
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

# revision identifiers, used by Alembic
revision = '137_add_gobd_compliance_checks'
down_revision = '136_add_document_versioning_signatures'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create GoBD compliance check tables."""

    # ============================================================================
    # 1. GoBD COMPLIANCE CHECK TABLE
    # ============================================================================
    op.create_table(
        'gobd_compliance_checks',
        # Primary Key
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),

        # Multi-Tenant
        sa.Column('company_id', UUID(as_uuid=True), sa.ForeignKey('companies.id', ondelete='CASCADE'), nullable=False),

        # Check Type
        sa.Column('check_type', sa.String(50), nullable=False),

        # Status
        sa.Column('status', sa.String(20), nullable=False, server_default='pending'),

        # Timing
        sa.Column('last_checked_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('next_check_at', sa.DateTime(timezone=True), nullable=True),

        # Results
        sa.Column('score', sa.Integer, nullable=True),  # 0-100
        sa.Column('issues_found', sa.Integer, nullable=False, server_default='0'),
        sa.Column('details', JSONB, nullable=False, server_default='{}'),
        sa.Column('affected_documents', JSONB, nullable=False, server_default='[]'),

        # Remediation
        sa.Column('remediation_steps', JSONB, nullable=False, server_default='[]'),
        sa.Column('auto_remediated', sa.Boolean, nullable=False, server_default='false'),
        sa.Column('remediation_notes', sa.Text, nullable=True),

        # Execution
        sa.Column('triggered_by', sa.String(50), nullable=True),  # 'scheduled', 'manual', 'event'
        sa.Column('executed_by_id', UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('execution_duration_ms', sa.Integer, nullable=True),

        # Audit
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()')),

        # Constraints
        sa.CheckConstraint(
            "check_type IN ("
            "'nachvollziehbarkeit', "  # Audit-Trail vorhanden
            "'nachpruefbarkeit', "     # Daten ueberpruefbar
            "'unveraenderbarkeit', "   # Keine Manipulation
            "'vollstaendigkeit', "     # Keine Luecken
            "'ordnung', "              # Systematische Ablage
            "'zeitgerechte_buchung', " # Fristgerecht
            "'aufbewahrung', "         # 10 Jahre
            "'maschinelle_auswertbarkeit', "  # Export moeglich
            "'verfahrensdokumentation', "     # Doku aktuell
            "'datensicherung', "       # Backup vorhanden
            "'zugangskontrolle'"       # Berechtigungen
            ")",
            name='ck_gobd_check_type'
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'running', 'passed', 'failed', 'warning', 'not_applicable')",
            name='ck_gobd_check_status'
        ),
    )

    # Indexes
    op.create_index('ix_gobd_checks_company_id', 'gobd_compliance_checks', ['company_id'])
    op.create_index('ix_gobd_checks_type', 'gobd_compliance_checks', ['check_type'])
    op.create_index('ix_gobd_checks_status', 'gobd_compliance_checks', ['status'])
    op.create_index('ix_gobd_checks_company_type', 'gobd_compliance_checks', ['company_id', 'check_type'])
    op.create_index('ix_gobd_checks_next_check', 'gobd_compliance_checks', ['next_check_at'])
    op.create_index('ix_gobd_checks_last_checked', 'gobd_compliance_checks', ['last_checked_at'])

    # ============================================================================
    # 2. COMPLIANCE CHECK HISTORY (Audit Trail)
    # ============================================================================
    op.create_table(
        'gobd_compliance_history',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),

        # Reference to check
        sa.Column('compliance_check_id', UUID(as_uuid=True), sa.ForeignKey('gobd_compliance_checks.id', ondelete='CASCADE'), nullable=False),
        sa.Column('company_id', UUID(as_uuid=True), sa.ForeignKey('companies.id', ondelete='CASCADE'), nullable=False),

        # Snapshot of check result
        sa.Column('check_type', sa.String(50), nullable=False),
        sa.Column('status', sa.String(20), nullable=False),
        sa.Column('score', sa.Integer, nullable=True),
        sa.Column('issues_found', sa.Integer, nullable=False, server_default='0'),
        sa.Column('details', JSONB, nullable=False, server_default='{}'),

        # Execution
        sa.Column('triggered_by', sa.String(50), nullable=True),
        sa.Column('executed_by_id', UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),

        # Immutable timestamp
        sa.Column('checked_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=False),
    )

    # Indexes
    op.create_index('ix_gobd_history_check_id', 'gobd_compliance_history', ['compliance_check_id'])
    op.create_index('ix_gobd_history_company_id', 'gobd_compliance_history', ['company_id'])
    op.create_index('ix_gobd_history_checked_at', 'gobd_compliance_history', ['checked_at'])
    op.create_index('ix_gobd_history_company_type', 'gobd_compliance_history', ['company_id', 'check_type'])

    # ============================================================================
    # 3. COMPLIANCE REPORT TABLE (for exports)
    # ============================================================================
    op.create_table(
        'gobd_compliance_reports',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),

        # Multi-Tenant
        sa.Column('company_id', UUID(as_uuid=True), sa.ForeignKey('companies.id', ondelete='CASCADE'), nullable=False),

        # Report Details
        sa.Column('report_type', sa.String(50), nullable=False, server_default='full'),
        sa.Column('title', sa.String(255), nullable=False),
        sa.Column('description', sa.Text, nullable=True),

        # Period
        sa.Column('period_start', sa.Date, nullable=True),
        sa.Column('period_end', sa.Date, nullable=True),

        # Content
        sa.Column('summary', JSONB, nullable=False, server_default='{}'),
        sa.Column('check_results', JSONB, nullable=False, server_default='[]'),
        sa.Column('recommendations', JSONB, nullable=False, server_default='[]'),

        # Overall Score
        sa.Column('overall_score', sa.Integer, nullable=True),
        sa.Column('overall_status', sa.String(20), nullable=False, server_default='unknown'),

        # Export
        sa.Column('file_path', sa.String(500), nullable=True),
        sa.Column('file_format', sa.String(20), nullable=True),

        # Generated
        sa.Column('generated_by_id', UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('generated_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()')),

        # Access (for auditors)
        sa.Column('is_exported', sa.Boolean, nullable=False, server_default='false'),
        sa.Column('exported_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('exported_to', sa.String(255), nullable=True),

        # Constraints
        sa.CheckConstraint(
            "report_type IN ('full', 'summary', 'audit', 'quarterly', 'annual', 'custom')",
            name='ck_gobd_report_type'
        ),
    )

    # Indexes
    op.create_index('ix_gobd_reports_company_id', 'gobd_compliance_reports', ['company_id'])
    op.create_index('ix_gobd_reports_generated_at', 'gobd_compliance_reports', ['generated_at'])
    op.create_index('ix_gobd_reports_type', 'gobd_compliance_reports', ['report_type'])


def downgrade() -> None:
    """Remove GoBD compliance check tables."""

    # Drop reports
    op.drop_index('ix_gobd_reports_type', 'gobd_compliance_reports')
    op.drop_index('ix_gobd_reports_generated_at', 'gobd_compliance_reports')
    op.drop_index('ix_gobd_reports_company_id', 'gobd_compliance_reports')
    op.drop_table('gobd_compliance_reports')

    # Drop history
    op.drop_index('ix_gobd_history_company_type', 'gobd_compliance_history')
    op.drop_index('ix_gobd_history_checked_at', 'gobd_compliance_history')
    op.drop_index('ix_gobd_history_company_id', 'gobd_compliance_history')
    op.drop_index('ix_gobd_history_check_id', 'gobd_compliance_history')
    op.drop_table('gobd_compliance_history')

    # Drop checks
    op.drop_index('ix_gobd_checks_last_checked', 'gobd_compliance_checks')
    op.drop_index('ix_gobd_checks_next_check', 'gobd_compliance_checks')
    op.drop_index('ix_gobd_checks_company_type', 'gobd_compliance_checks')
    op.drop_index('ix_gobd_checks_status', 'gobd_compliance_checks')
    op.drop_index('ix_gobd_checks_type', 'gobd_compliance_checks')
    op.drop_index('ix_gobd_checks_company_id', 'gobd_compliance_checks')
    op.drop_table('gobd_compliance_checks')
