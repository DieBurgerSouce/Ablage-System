"""Add Kanban workflow system.

Revision ID: 208_add_kanban_workflow
Revises: 207_add_fx_service
Create Date: 2026-02-07

Features:
- Workflow stages (Kanban columns)
- Document workflow items (cards)
- Default document workflow stages
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '208_add_kanban_workflow'
down_revision: str = '207_add_fx_service'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create workflow_stages and document_workflow_items tables."""

    # Create workflow_stages table
    op.create_table(
        'workflow_stages',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('company_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('workflow_type', sa.String(30), nullable=False),
        sa.Column('stage_key', sa.String(50), nullable=False, comment="Eindeutiger Key (z.B. 'eingang', 'pruefung')"),
        sa.Column('stage_name', sa.String(100), nullable=False, comment="Deutsche Anzeige-Bezeichnung"),
        sa.Column('stage_order', sa.Integer(), nullable=False, comment="Reihenfolge der Stage (1, 2, 3, ...)"),
        sa.Column('color', sa.String(20), default="#6B7280", comment="Hex-Farbe fuer UI"),
        sa.Column('icon', sa.String(50), nullable=True, comment="Lucide Icon-Name"),
        sa.Column('is_final', sa.Boolean(), default=False, comment="Ist dies die finale Stage?"),
        sa.Column('auto_transition_after_hours', sa.Integer(), nullable=True, comment="Auto-Weiterleitung nach N Stunden"),
        sa.Column('required_approval', sa.Boolean(), default=False, comment="Freigabe erforderlich?"),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.ForeignKeyConstraint(['company_id'], ['companies.id'], ondelete='CASCADE'),
        sa.UniqueConstraint('company_id', 'workflow_type', 'stage_key', name='uq_workflow_stage'),
    )

    # Create indexes for workflow_stages
    op.create_index('ix_workflow_stages_company_type', 'workflow_stages', ['company_id', 'workflow_type'])
    op.create_index('ix_workflow_stages_order', 'workflow_stages', ['company_id', 'workflow_type', 'stage_order'])

    # Create document_workflow_items table
    op.create_table(
        'document_workflow_items',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('company_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('document_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('workflow_type', sa.String(30), nullable=False),
        sa.Column('current_stage_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('previous_stage_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('entered_stage_at', sa.DateTime(timezone=True), server_default=sa.func.now(), comment="Wann in aktuelle Stage gewechselt"),
        sa.Column('assigned_to', postgresql.UUID(as_uuid=True), nullable=True, comment="Zugewiesener Bearbeiter"),
        sa.Column('priority', sa.String(20), default='normal', comment="Prioritaet (low, normal, high, urgent)"),
        sa.Column('notes', sa.Text(), nullable=True, comment="Notizen zum Workflow-Item"),
        sa.Column('metadata_json', postgresql.JSONB(astext_type=sa.Text()), nullable=True, comment="Zusaetzliche Metadaten"),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.ForeignKeyConstraint(['company_id'], ['companies.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['document_id'], ['documents.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['current_stage_id'], ['workflow_stages.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['previous_stage_id'], ['workflow_stages.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['assigned_to'], ['users.id'], ondelete='SET NULL'),
        sa.UniqueConstraint('company_id', 'document_id', 'workflow_type', name='uq_document_workflow'),
    )

    # Create indexes for document_workflow_items
    op.create_index('ix_workflow_items_stage', 'document_workflow_items', ['current_stage_id'])
    op.create_index('ix_workflow_items_company', 'document_workflow_items', ['company_id', 'workflow_type'])
    op.create_index('ix_workflow_items_document', 'document_workflow_items', ['document_id'])
    op.create_index('ix_workflow_items_assigned', 'document_workflow_items', ['assigned_to'])


def downgrade() -> None:
    """Drop workflow_stages and document_workflow_items tables."""

    # Drop indexes for document_workflow_items
    op.drop_index('ix_workflow_items_assigned', 'document_workflow_items')
    op.drop_index('ix_workflow_items_document', 'document_workflow_items')
    op.drop_index('ix_workflow_items_company', 'document_workflow_items')
    op.drop_index('ix_workflow_items_stage', 'document_workflow_items')

    # Drop document_workflow_items table
    op.drop_table('document_workflow_items')

    # Drop indexes for workflow_stages
    op.drop_index('ix_workflow_stages_order', 'workflow_stages')
    op.drop_index('ix_workflow_stages_company_type', 'workflow_stages')

    # Drop workflow_stages table
    op.drop_table('workflow_stages')
