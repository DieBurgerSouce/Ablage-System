"""Add Project Management Models for Vision 2026.

Revision ID: 135_add_project_management
Revises: 134_add_company_id_to_audit_log
Create Date: 2026-01-28

Vision 2026 Feature: Projekt-/Kostenstellen-Erweiterung
- Project model with company, client, status, budget, dates, team members
- DocumentProjectAssignment for linking documents to projects
- Project-based document organization and tracking

Extends existing Kostenstelle integration.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import UUID, JSONB

# revision identifiers, used by Alembic
revision = '135_add_project_management'
down_revision = '134_add_company_id_to_audit_log'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create project management tables."""

    # ============================================================================
    # 1. PROJECT TABLE
    # ============================================================================
    op.create_table(
        'projects',
        # Primary Key
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),

        # Multi-Tenant
        sa.Column('company_id', UUID(as_uuid=True), sa.ForeignKey('companies.id', ondelete='CASCADE'), nullable=False),

        # Project Identification
        sa.Column('code', sa.String(50), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('description', sa.Text, nullable=True),

        # Client (BusinessEntity)
        sa.Column('client_id', UUID(as_uuid=True), sa.ForeignKey('business_entities.id', ondelete='SET NULL'), nullable=True),

        # Status
        sa.Column('status', sa.String(50), nullable=False, server_default='planning'),

        # Timeline
        sa.Column('start_date', sa.Date, nullable=True),
        sa.Column('end_date', sa.Date, nullable=True),
        sa.Column('actual_start_date', sa.Date, nullable=True),
        sa.Column('actual_end_date', sa.Date, nullable=True),

        # Budget
        sa.Column('budget', sa.Numeric(15, 2), nullable=True),
        sa.Column('budget_spent', sa.Numeric(15, 2), nullable=True, server_default='0'),
        sa.Column('currency', sa.String(3), nullable=False, server_default='EUR'),

        # Kostenstelle Link (FK added conditionally below)
        sa.Column('kostenstelle_id', UUID(as_uuid=True), nullable=True),

        # Manager / Team
        sa.Column('manager_id', UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),

        # Priority & Category
        sa.Column('priority', sa.String(20), nullable=True, server_default='medium'),
        sa.Column('category', sa.String(100), nullable=True),

        # Statistics (cached for performance)
        sa.Column('document_count', sa.Integer, nullable=False, server_default='0'),
        sa.Column('invoice_count', sa.Integer, nullable=False, server_default='0'),
        sa.Column('total_invoiced', sa.Numeric(15, 2), nullable=True, server_default='0'),

        # Metadata
        sa.Column('tags', JSONB, nullable=False, server_default='[]'),
        sa.Column('metadata', JSONB, nullable=False, server_default='{}'),

        # Audit
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()')),
        sa.Column('created_by_id', UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),

        # Constraints
        sa.UniqueConstraint('company_id', 'code', name='uq_project_code_per_company'),
        sa.CheckConstraint("status IN ('planning', 'active', 'on_hold', 'completed', 'cancelled', 'archived')", name='ck_project_status'),
        sa.CheckConstraint("priority IN ('low', 'medium', 'high', 'critical')", name='ck_project_priority'),
    )

    # Indexes for projects
    op.create_index('ix_projects_company_id', 'projects', ['company_id'])
    op.create_index('ix_projects_client_id', 'projects', ['client_id'])
    op.create_index('ix_projects_kostenstelle_id', 'projects', ['kostenstelle_id'])
    op.create_index('ix_projects_manager_id', 'projects', ['manager_id'])
    op.create_index('ix_projects_status', 'projects', ['status'])
    op.create_index('ix_projects_company_status', 'projects', ['company_id', 'status'])
    op.create_index('ix_projects_company_code', 'projects', ['company_id', 'code'])
    op.create_index('ix_projects_end_date', 'projects', ['end_date'])

    # Conditionally add kostenstellen FK (table may not exist yet)
    bind = op.get_bind()
    has_kostenstellen = bind.execute(text(
        "SELECT 1 FROM information_schema.tables WHERE table_name = 'kostenstellen'"
    )).fetchone()
    if has_kostenstellen:
        op.create_foreign_key(
            'fk_projects_kostenstelle',
            'projects', 'kostenstellen',
            ['kostenstelle_id'], ['id'],
            ondelete='SET NULL'
        )

    # ============================================================================
    # 2. PROJECT MEMBER TABLE (Team Members)
    # ============================================================================
    op.create_table(
        'project_members',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),

        # Foreign Keys
        sa.Column('project_id', UUID(as_uuid=True), sa.ForeignKey('projects.id', ondelete='CASCADE'), nullable=False),
        sa.Column('user_id', UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),

        # Role & Permissions
        sa.Column('role', sa.String(50), nullable=False, server_default='member'),
        sa.Column('permissions', JSONB, nullable=False, server_default='[]'),

        # Time-bound (optional)
        sa.Column('valid_from', sa.Date, nullable=True),
        sa.Column('valid_until', sa.Date, nullable=True),

        # Allocation
        sa.Column('allocation_percent', sa.Integer, nullable=True),

        # Status
        sa.Column('is_active', sa.Boolean, nullable=False, server_default='true'),

        # Audit
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()')),

        # Constraints
        sa.UniqueConstraint('project_id', 'user_id', name='uq_project_member'),
        sa.CheckConstraint("role IN ('member', 'lead', 'admin', 'observer', 'external')", name='ck_project_member_role'),
    )

    # Indexes for project_members
    op.create_index('ix_project_members_project_id', 'project_members', ['project_id'])
    op.create_index('ix_project_members_user_id', 'project_members', ['user_id'])
    op.create_index('ix_project_members_active', 'project_members', ['project_id', 'is_active'])

    # ============================================================================
    # 3. DOCUMENT PROJECT ASSIGNMENT TABLE
    # ============================================================================
    op.create_table(
        'document_project_assignments',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),

        # Foreign Keys
        sa.Column('document_id', UUID(as_uuid=True), sa.ForeignKey('documents.id', ondelete='CASCADE'), nullable=False),
        sa.Column('project_id', UUID(as_uuid=True), sa.ForeignKey('projects.id', ondelete='CASCADE'), nullable=False),

        # Multi-Tenant (denormalized for RLS performance)
        sa.Column('company_id', UUID(as_uuid=True), sa.ForeignKey('companies.id', ondelete='CASCADE'), nullable=False),

        # Assignment Type
        sa.Column('assignment_type', sa.String(50), nullable=False, server_default='general'),

        # Assignment Source
        sa.Column('auto_assigned', sa.Boolean, nullable=False, server_default='false'),
        sa.Column('confidence', sa.Float, nullable=True),
        sa.Column('assignment_reason', sa.Text, nullable=True),

        # Assigned By
        sa.Column('assigned_by_id', UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),

        # Audit
        sa.Column('assigned_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()')),

        # Constraints
        sa.UniqueConstraint('document_id', 'project_id', name='uq_document_project'),
        sa.CheckConstraint(
            "assignment_type IN ('invoice', 'contract', 'correspondence', 'deliverable', 'report', 'general')",
            name='ck_assignment_type'
        ),
    )

    # Indexes for document_project_assignments
    op.create_index('ix_doc_project_document_id', 'document_project_assignments', ['document_id'])
    op.create_index('ix_doc_project_project_id', 'document_project_assignments', ['project_id'])
    op.create_index('ix_doc_project_company_id', 'document_project_assignments', ['company_id'])
    op.create_index('ix_doc_project_auto_assigned', 'document_project_assignments', ['auto_assigned'])

    # ============================================================================
    # 4. ADD project_id TO DOCUMENTS TABLE (Direct FK for primary project)
    # ============================================================================
    op.add_column(
        'documents',
        sa.Column('project_id', UUID(as_uuid=True), nullable=True)
    )
    op.create_foreign_key(
        'fk_documents_project',
        'documents',
        'projects',
        ['project_id'],
        ['id'],
        ondelete='SET NULL'
    )
    op.create_index('ix_documents_project_id', 'documents', ['project_id'])

    # ============================================================================
    # 5. ADD project_id TO INVOICE_TRACKING TABLE (for invoice-project linking)
    # ============================================================================
    # Check if invoice_tracking table exists first
    op.add_column(
        'invoice_tracking',
        sa.Column('project_id', UUID(as_uuid=True), nullable=True)
    )
    op.create_foreign_key(
        'fk_invoice_tracking_project',
        'invoice_tracking',
        'projects',
        ['project_id'],
        ['id'],
        ondelete='SET NULL'
    )
    op.create_index('ix_invoice_tracking_project_id', 'invoice_tracking', ['project_id'])


def downgrade() -> None:
    """Remove project management tables."""

    # Remove project_id from invoice_tracking
    op.drop_index('ix_invoice_tracking_project_id', 'invoice_tracking')
    op.drop_constraint('fk_invoice_tracking_project', 'invoice_tracking', type_='foreignkey')
    op.drop_column('invoice_tracking', 'project_id')

    # Remove project_id from documents
    op.drop_index('ix_documents_project_id', 'documents')
    op.drop_constraint('fk_documents_project', 'documents', type_='foreignkey')
    op.drop_column('documents', 'project_id')

    # Drop document_project_assignments
    op.drop_index('ix_doc_project_auto_assigned', 'document_project_assignments')
    op.drop_index('ix_doc_project_company_id', 'document_project_assignments')
    op.drop_index('ix_doc_project_project_id', 'document_project_assignments')
    op.drop_index('ix_doc_project_document_id', 'document_project_assignments')
    op.drop_table('document_project_assignments')

    # Drop project_members
    op.drop_index('ix_project_members_active', 'project_members')
    op.drop_index('ix_project_members_user_id', 'project_members')
    op.drop_index('ix_project_members_project_id', 'project_members')
    op.drop_table('project_members')

    # Drop projects
    op.drop_index('ix_projects_end_date', 'projects')
    op.drop_index('ix_projects_company_code', 'projects')
    op.drop_index('ix_projects_company_status', 'projects')
    op.drop_index('ix_projects_status', 'projects')
    op.drop_index('ix_projects_manager_id', 'projects')
    op.drop_index('ix_projects_kostenstelle_id', 'projects')
    op.drop_index('ix_projects_client_id', 'projects')
    op.drop_index('ix_projects_company_id', 'projects')
    op.drop_table('projects')
