"""Add year-end closing (Jahresabschluss) tables

Revision ID: 217_add_year_end_tables
Revises: 216_add_signature_tables
Create Date: 2026-02-13

Adds tables for the Jahresabschluss-Assistent:
- year_end_sessions: Jahresabschluss-Durchlaeufe
- year_end_check_items: Checklisten-Pruefpunkte
- year_end_gaps: Erkannte Luecken und Unstimmigkeiten
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '217_add_year_end_tables'
down_revision: str = '216_add_signature_tables'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create year-end closing tables and enums."""

    # Create enums
    year_end_status = postgresql.ENUM(
        'draft', 'in_progress', 'review', 'completed', 'exported',
        name='year_end_status',
        create_type=True,
    )
    check_item_status = postgresql.ENUM(
        'pending', 'passed', 'warning', 'failed', 'skipped',
        name='check_item_status',
        create_type=True,
    )
    gap_category = postgresql.ENUM(
        'missing_receipt', 'unmatched_transaction', 'missing_invoice',
        'incomplete_data', 'amount_discrepancy',
        name='gap_category',
        create_type=True,
    )

    year_end_status.create(op.get_bind(), checkfirst=True)
    check_item_status.create(op.get_bind(), checkfirst=True)
    gap_category.create(op.get_bind(), checkfirst=True)

    # Create year_end_sessions table
    op.create_table(
        'year_end_sessions',
        sa.Column('id', sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            'company_id',
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey('companies.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column('fiscal_year', sa.Integer(), nullable=False),
        sa.Column(
            'status',
            sa.String(20),
            nullable=False,
            server_default='draft',
        ),
        sa.Column(
            'started_by',
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey('users.id', ondelete='SET NULL'),
            nullable=True,
        ),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('progress_percent', sa.Integer(), server_default='0'),
        sa.Column('total_checks', sa.Integer(), server_default='0'),
        sa.Column('passed_checks', sa.Integer(), server_default='0'),
        sa.Column('warning_checks', sa.Integer(), server_default='0'),
        sa.Column('failed_checks', sa.Integer(), server_default='0'),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('report_generated_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.Column(
            'updated_at',
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    )

    # Create year_end_check_items table
    op.create_table(
        'year_end_check_items',
        sa.Column('id', sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            'session_id',
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey('year_end_sessions.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column(
            'company_id',
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey('companies.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column('category', sa.String(100), nullable=False),
        sa.Column('check_name', sa.String(255), nullable=False),
        sa.Column(
            'status',
            sa.String(20),
            nullable=False,
            server_default='pending',
        ),
        sa.Column('details_json', sa.dialects.postgresql.JSONB(), nullable=True),
        sa.Column('checked_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            'resolved_by',
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey('users.id', ondelete='SET NULL'),
            nullable=True,
        ),
        sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('resolution_notes', sa.Text(), nullable=True),
        sa.Column('sort_order', sa.Integer(), server_default='0'),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.Column(
            'updated_at',
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    )

    # Create year_end_gaps table
    op.create_table(
        'year_end_gaps',
        sa.Column('id', sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            'session_id',
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey('year_end_sessions.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column(
            'company_id',
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey('companies.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column('category', sa.String(30), nullable=False),
        sa.Column('month', sa.Integer(), nullable=True),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('amount', sa.Numeric(12, 2), nullable=True),
        sa.Column(
            'document_id',
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey('documents.id', ondelete='SET NULL'),
            nullable=True,
        ),
        sa.Column('transaction_reference', sa.String(255), nullable=True),
        sa.Column('is_resolved', sa.Boolean(), server_default='false'),
        sa.Column(
            'resolved_by',
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey('users.id', ondelete='SET NULL'),
            nullable=True,
        ),
        sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('resolution_notes', sa.Text(), nullable=True),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.Column(
            'updated_at',
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    )

    # Create indexes
    op.create_index(
        'ix_year_end_sessions_company_year',
        'year_end_sessions',
        ['company_id', 'fiscal_year'],
    )
    op.create_index(
        'ix_year_end_sessions_company_id',
        'year_end_sessions',
        ['company_id'],
    )
    op.create_index(
        'ix_year_end_check_items_session_id',
        'year_end_check_items',
        ['session_id'],
    )
    op.create_index(
        'ix_year_end_gaps_session_id',
        'year_end_gaps',
        ['session_id'],
    )
    op.create_index(
        'ix_year_end_gaps_category',
        'year_end_gaps',
        ['category'],
    )
    op.create_index(
        'ix_year_end_gaps_month',
        'year_end_gaps',
        ['month'],
    )


def downgrade() -> None:
    """Drop year-end closing tables and enums."""

    # Drop indexes
    op.drop_index('ix_year_end_gaps_month', table_name='year_end_gaps')
    op.drop_index('ix_year_end_gaps_category', table_name='year_end_gaps')
    op.drop_index('ix_year_end_gaps_session_id', table_name='year_end_gaps')
    op.drop_index('ix_year_end_check_items_session_id', table_name='year_end_check_items')
    op.drop_index('ix_year_end_sessions_company_id', table_name='year_end_sessions')
    op.drop_index('ix_year_end_sessions_company_year', table_name='year_end_sessions')

    # Drop tables (reverse order)
    op.drop_table('year_end_gaps')
    op.drop_table('year_end_check_items')
    op.drop_table('year_end_sessions')

    # Drop enums
    postgresql.ENUM(name='gap_category').drop(op.get_bind(), checkfirst=True)
    postgresql.ENUM(name='check_item_status').drop(op.get_bind(), checkfirst=True)
    postgresql.ENUM(name='year_end_status').drop(op.get_bind(), checkfirst=True)
