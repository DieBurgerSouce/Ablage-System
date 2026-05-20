"""Add DPIA (Data Protection Impact Assessment) tables

Revision ID: 119_add_dpia_tables
Revises: 118_add_inventory_management
Create Date: 2026-01-25

Tabellen:
- dpias: Haupt-DPIA Datenschutz-Folgenabschaetzung
- dpia_processing_operations: Verarbeitungsvorgaenge innerhalb einer DPIA
- dpia_data_subject_groups: Betroffene Personengruppen
- dpia_risks: Risikobewertungen
- dpia_mitigation_measures: Risikominderungsmassnahmen
- dpia_consultations: Datenschutzbeauftragte-Konsultationen
- dpia_audit_log: Audit-Trail fuer DPIA-Aenderungen
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '119_add_dpia_tables'
down_revision = '118_add_inventory_management'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # DPIA Status Enum
    dpia_status_enum = postgresql.ENUM(
        'draft', 'review', 'approved', 'rejected', 'archived',
        name='dpia_status', create_type=False,
    )
    dpia_status_enum.create(op.get_bind(), checkfirst=True)

    # Legal Basis Enum
    legal_basis_enum = postgresql.ENUM(
        'consent', 'contract', 'legal_obligation', 'vital_interests',
        'public_interest', 'legitimate_interest',
        name='legal_basis', create_type=False,
    )
    legal_basis_enum.create(op.get_bind(), checkfirst=True)

    # Measure Type Enum
    measure_type_enum = postgresql.ENUM(
        'technical', 'organizational', 'contractual', 'legal',
        name='measure_type', create_type=False,
    )
    measure_type_enum.create(op.get_bind(), checkfirst=True)

    # Implementation Status Enum
    implementation_status_enum = postgresql.ENUM(
        'planned', 'in_progress', 'implemented',
        name='implementation_status', create_type=False,
    )
    implementation_status_enum.create(op.get_bind(), checkfirst=True)

    # Risk Level Enum
    risk_level_enum = postgresql.ENUM(
        'very_high', 'high', 'medium', 'low', 'minimal',
        name='risk_level', create_type=False,
    )
    risk_level_enum.create(op.get_bind(), checkfirst=True)

    # Main DPIA Table
    op.create_table(
        'dpias',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('title', sa.String(255), nullable=False),
        sa.Column('description', sa.Text, nullable=True),
        sa.Column('version', sa.String(20), nullable=False, server_default='1.0'),
        sa.Column('status', dpia_status_enum, nullable=False),
        sa.Column('controller_name', sa.String(255), nullable=False),
        sa.Column('controller_contact', sa.String(255), nullable=True),
        sa.Column('dpo_name', sa.String(255), nullable=False),
        sa.Column('dpo_contact', sa.String(255), nullable=True),
        sa.Column('assessment_date', sa.DateTime(timezone=True), nullable=True),
        sa.Column('assessor_name', sa.String(255), nullable=True),
        sa.Column('necessity_assessment', sa.Text, nullable=True),
        sa.Column('proportionality_assessment', sa.Text, nullable=True),
        sa.Column('overall_risk_level', risk_level_enum, nullable=True),
        sa.Column('supervisory_authority_consultation', sa.Boolean, server_default='false'),
        sa.Column('supervisory_authority_response', sa.Text, nullable=True),
        sa.Column('company_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('companies.id', ondelete='CASCADE'), nullable=False),
        sa.Column('created_by_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
    )
    op.create_index('ix_dpia_company', 'dpias', ['company_id'])
    op.create_index('ix_dpia_status', 'dpias', ['status'])
    op.create_index('ix_dpia_created_at', 'dpias', ['created_at'])
    op.create_index('ix_dpia_company_status', 'dpias', ['company_id', 'status'])

    # Processing Operations
    op.create_table(
        'dpia_processing_operations',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('dpia_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('dpias.id', ondelete='CASCADE'), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('description', sa.Text, nullable=True),
        sa.Column('purpose', sa.Text, nullable=True),
        sa.Column('legal_basis', legal_basis_enum, nullable=True),
        sa.Column('data_categories', postgresql.JSONB, nullable=True),  # Array of strings
        sa.Column('retention_period', sa.String(255), nullable=True),
        sa.Column('automated_decision_making', sa.Boolean, server_default='false'),
        sa.Column('profiling', sa.Boolean, server_default='false'),
        sa.Column('data_transfer_outside_eu', sa.Boolean, server_default='false'),
        sa.Column('transfer_countries', postgresql.JSONB, nullable=True),  # Array of strings
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('ix_dpia_processing_dpia', 'dpia_processing_operations', ['dpia_id'])

    # Data Subject Groups
    op.create_table(
        'dpia_data_subject_groups',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('dpia_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('dpias.id', ondelete='CASCADE'), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('description', sa.Text, nullable=True),
        sa.Column('estimated_count', sa.Integer, nullable=True),
        sa.Column('includes_vulnerable', sa.Boolean, server_default='false'),
        sa.Column('includes_children', sa.Boolean, server_default='false'),
    )
    op.create_index('ix_dpia_subject_groups_dpia', 'dpia_data_subject_groups', ['dpia_id'])

    # Risks
    op.create_table(
        'dpia_risks',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('dpia_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('dpias.id', ondelete='CASCADE'), nullable=False),
        sa.Column('risk_id', sa.String(50), nullable=True),  # e.g., R1, R2
        sa.Column('description', sa.Text, nullable=False),
        sa.Column('affected_rights', postgresql.JSONB, nullable=True),  # Array of strings
        sa.Column('likelihood', sa.Integer, nullable=True),  # 1-5
        sa.Column('impact', sa.Integer, nullable=True),  # 1-5
        sa.Column('inherent_risk', risk_level_enum, nullable=True),
        sa.Column('residual_risk', risk_level_enum, nullable=True),
        sa.Column('mitigation_measures', postgresql.JSONB, nullable=True),  # Array of measure IDs
        sa.CheckConstraint('likelihood >= 1 AND likelihood <= 5', name='ck_risk_likelihood_range'),
        sa.CheckConstraint('impact >= 1 AND impact <= 5', name='ck_risk_impact_range'),
    )
    op.create_index('ix_dpia_risks_dpia', 'dpia_risks', ['dpia_id'])

    # Mitigation Measures
    op.create_table(
        'dpia_mitigation_measures',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('dpia_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('dpias.id', ondelete='CASCADE'), nullable=False),
        sa.Column('measure_id', sa.String(50), nullable=True),  # e.g., M1, M2
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('description', sa.Text, nullable=True),
        sa.Column('measure_type', measure_type_enum, nullable=True),
        sa.Column('addresses_risks', postgresql.JSONB, nullable=True),  # Array of risk IDs
        sa.Column('implementation_status', implementation_status_enum, nullable=True),
        sa.Column('responsible_person', sa.String(255), nullable=True),
        sa.Column('deadline', sa.DateTime(timezone=True), nullable=True),
        sa.Column('effectiveness', sa.Text, nullable=True),
    )
    op.create_index('ix_dpia_mitigation_dpia', 'dpia_mitigation_measures', ['dpia_id'])

    # DPO Consultations
    op.create_table(
        'dpia_consultations',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('dpia_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('dpias.id', ondelete='CASCADE'), nullable=False, unique=True),
        sa.Column('dpo_name', sa.String(255), nullable=False),
        sa.Column('consultation_date', sa.DateTime(timezone=True), nullable=False),
        sa.Column('opinion', sa.Text, nullable=True),
        sa.Column('recommendations', postgresql.JSONB, nullable=True),  # Array of strings
        sa.Column('approval', sa.Boolean, nullable=False),
        sa.Column('conditions', postgresql.JSONB, nullable=True),  # Array of strings
    )
    op.create_index('ix_dpia_consultations_dpia', 'dpia_consultations', ['dpia_id'])

    # Audit Log
    op.create_table(
        'dpia_audit_log',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('dpia_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('dpias.id', ondelete='CASCADE'), nullable=False),
        sa.Column('action', sa.String(50), nullable=False),
        sa.Column('user_name', sa.String(255), nullable=True),
        sa.Column('details', sa.Text, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('ix_dpia_audit_dpia', 'dpia_audit_log', ['dpia_id'])
    op.create_index('ix_dpia_audit_created_at', 'dpia_audit_log', ['created_at'])


def downgrade() -> None:
    # Drop tables in reverse order
    op.drop_table('dpia_audit_log')
    op.drop_table('dpia_consultations')
    op.drop_table('dpia_mitigation_measures')
    op.drop_table('dpia_risks')
    op.drop_table('dpia_data_subject_groups')
    op.drop_table('dpia_processing_operations')
    op.drop_table('dpias')

    # Drop enums
    op.execute('DROP TYPE IF EXISTS risk_level')
    op.execute('DROP TYPE IF EXISTS implementation_status')
    op.execute('DROP TYPE IF EXISTS measure_type')
    op.execute('DROP TYPE IF EXISTS legal_basis')
    op.execute('DROP TYPE IF EXISTS dpia_status')
