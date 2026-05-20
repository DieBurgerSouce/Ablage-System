# -*- coding: utf-8 -*-
"""Add Communication Hub tables.

Vision 2026+ Feature #1: Kommunikations-Hub (360° Entity View)
Telefon-Notizen und Kommunikations-Zusammenfassungen.

Revision ID: 138_add_communication_hub
Revises: 137_add_gobd_compliance_checks
Create Date: 2026-01-28

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '138_add_communication_hub'
down_revision: Union[str, None] = '137_add_gobd_compliance_checks'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create phone_notes and communication_summaries tables."""

    # Create phone_notes table
    op.create_table(
        'phone_notes',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('entity_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('company_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('call_type', sa.String(20), nullable=False, server_default='phone_call'),
        sa.Column('direction', sa.String(20), nullable=False, server_default='inbound'),
        sa.Column('contact_person', sa.String(255), nullable=True),
        sa.Column('phone_number', sa.String(50), nullable=True),
        sa.Column('duration_minutes', sa.Integer(), nullable=True),
        sa.Column('subject', sa.String(255), nullable=False),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('summary', sa.String(500), nullable=True),
        sa.Column('sentiment', sa.String(20), nullable=True, server_default='neutral'),
        sa.Column('follow_up_required', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('follow_up_date', sa.DateTime(timezone=True), nullable=True),
        sa.Column('follow_up_notes', sa.Text(), nullable=True),
        sa.Column('follow_up_completed', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('follow_up_completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('related_document_ids', postgresql.JSONB(astext_type=sa.Text()), nullable=True, server_default='[]'),
        sa.Column('tags', postgresql.JSONB(astext_type=sa.Text()), nullable=True, server_default='[]'),
        sa.Column('custom_fields', postgresql.JSONB(astext_type=sa.Text()), nullable=True, server_default='{}'),
        sa.Column('call_datetime', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text('now()')),
        sa.Column('created_by_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('assigned_to_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.ForeignKeyConstraint(['company_id'], ['companies.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['entity_id'], ['business_entities.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['assigned_to_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.CheckConstraint(
            "call_type IN ('phone_call', 'email', 'meeting', 'video_call', 'letter', 'fax', 'chat', 'internal_note', 'other')",
            name='ck_phone_notes_call_type'
        ),
        sa.CheckConstraint(
            "direction IN ('inbound', 'outbound', 'internal')",
            name='ck_phone_notes_direction'
        ),
        sa.CheckConstraint(
            "sentiment IS NULL OR sentiment IN ('positive', 'neutral', 'negative', 'escalation')",
            name='ck_phone_notes_sentiment'
        ),
    )

    # Create indexes for phone_notes
    op.create_index('ix_phone_notes_entity_id', 'phone_notes', ['entity_id'])
    op.create_index('ix_phone_notes_company_id', 'phone_notes', ['company_id'])
    op.create_index('ix_phone_notes_entity_company', 'phone_notes', ['entity_id', 'company_id'])
    op.create_index('ix_phone_notes_call_datetime', 'phone_notes', ['call_datetime'])
    op.create_index('ix_phone_notes_follow_up', 'phone_notes', ['follow_up_required', 'follow_up_completed'])
    op.create_index('ix_phone_notes_created_by', 'phone_notes', ['created_by_id'])

    # Create communication_summaries table
    op.create_table(
        'communication_summaries',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('entity_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('company_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('total_communications', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('phone_calls_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('emails_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('meetings_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('other_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('inbound_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('outbound_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('positive_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('neutral_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('negative_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('escalation_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('open_follow_ups', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('overdue_follow_ups', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('last_communication_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_communication_type', sa.String(20), nullable=True),
        sa.Column('last_communication_sentiment', sa.String(20), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['company_id'], ['companies.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['entity_id'], ['business_entities.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('entity_id', name='uq_communication_summaries_entity_id'),
    )

    # Create indexes for communication_summaries
    op.create_index('ix_comm_summary_entity', 'communication_summaries', ['entity_id'])
    op.create_index('ix_comm_summary_company', 'communication_summaries', ['company_id'])


def downgrade() -> None:
    """Drop phone_notes and communication_summaries tables."""
    op.drop_index('ix_comm_summary_company', table_name='communication_summaries')
    op.drop_index('ix_comm_summary_entity', table_name='communication_summaries')
    op.drop_table('communication_summaries')

    op.drop_index('ix_phone_notes_created_by', table_name='phone_notes')
    op.drop_index('ix_phone_notes_follow_up', table_name='phone_notes')
    op.drop_index('ix_phone_notes_call_datetime', table_name='phone_notes')
    op.drop_index('ix_phone_notes_entity_company', table_name='phone_notes')
    op.drop_index('ix_phone_notes_company_id', table_name='phone_notes')
    op.drop_index('ix_phone_notes_entity_id', table_name='phone_notes')
    op.drop_table('phone_notes')
