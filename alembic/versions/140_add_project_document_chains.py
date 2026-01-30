# -*- coding: utf-8 -*-
"""Add Project Document Chains table.

Vision 2026+ Feature #3: Projekt-Kontext (Multi-Chain Bundling)
Ermoeglicht die Buendelung mehrerer Document Chains zu einem Projekt.

Revision ID: 140_add_project_document_chains
Revises: 139_add_supplier_ocr_templates
Create Date: 2026-01-28

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '140_add_project_document_chains'
down_revision: Union[str, None] = '139_add_supplier_ocr_templates'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create project_document_chains table."""

    op.create_table(
        'project_document_chains',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('project_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('chain_id', sa.String(100), nullable=False),
        sa.Column('chain_name', sa.String(255), nullable=True),
        sa.Column('chain_description', sa.Text(), nullable=True),
        sa.Column('company_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('chain_status', sa.String(50), nullable=False, server_default='active'),
        sa.Column('expected_document_types', postgresql.JSONB(astext_type=sa.Text()), nullable=True,
                  server_default='["quote", "order", "delivery_note", "invoice"]'),
        sa.Column('completed_document_types', postgresql.JSONB(astext_type=sa.Text()), nullable=True, server_default='[]'),
        sa.Column('progress_percent', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('allocated_budget', sa.Numeric(15, 2), nullable=True),
        sa.Column('actual_cost', sa.Numeric(15, 2), nullable=False, server_default='0'),
        sa.Column('document_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('total_amount', sa.Numeric(15, 2), nullable=True),
        sa.Column('discrepancy_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('has_critical_discrepancy', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('first_document_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('last_document_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('first_document_date', sa.Date(), nullable=True),
        sa.Column('last_document_date', sa.Date(), nullable=True),
        sa.Column('entity_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('primary_reference', sa.String(100), nullable=True),
        sa.Column('order_number', sa.String(100), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=True, server_default='{}'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text('now()')),
        sa.Column('created_by_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.ForeignKeyConstraint(['company_id'], ['companies.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['entity_id'], ['business_entities.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['first_document_id'], ['documents.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['last_document_id'], ['documents.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('project_id', 'chain_id', name='uq_project_chain'),
    )

    # Create indexes
    op.create_index('ix_project_chains_project_id', 'project_document_chains', ['project_id'])
    op.create_index('ix_project_chains_company_id', 'project_document_chains', ['company_id'])
    op.create_index('ix_project_chains_chain_id', 'project_document_chains', ['chain_id'])
    op.create_index('ix_project_chains_entity_id', 'project_document_chains', ['entity_id'])
    op.create_index('ix_project_chains_status', 'project_document_chains', ['chain_status'])


def downgrade() -> None:
    """Drop project_document_chains table."""
    op.drop_index('ix_project_chains_status', table_name='project_document_chains')
    op.drop_index('ix_project_chains_entity_id', table_name='project_document_chains')
    op.drop_index('ix_project_chains_chain_id', table_name='project_document_chains')
    op.drop_index('ix_project_chains_company_id', table_name='project_document_chains')
    op.drop_index('ix_project_chains_project_id', table_name='project_document_chains')
    op.drop_table('project_document_chains')
