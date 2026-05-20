"""
Streckengeschäft - ZM Submissions Table
Add zm_submissions table for tracking Zusammenfassende Meldung status.

Revision ID: streckengeschaeft_004
Create Date: 2026-01-07
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = 'streckengeschaeft_004'
down_revision = '080'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create zm_submissions table for tracking ZM filing status."""

    op.create_table(
        'zm_submissions',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('gen_random_uuid()')),

        # Periode (z.B. "2024-12" für Dezember 2024)
        sa.Column('period', sa.String(7), nullable=False, index=True),

        # User/Company
        sa.Column('user_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('users.id', ondelete='CASCADE'),
                  nullable=False, index=True),
        sa.Column('company_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('companies.id', ondelete='SET NULL'),
                  nullable=True),

        # Status und Submission Details
        sa.Column('status', sa.String(20), nullable=False, default='draft'),
        sa.Column('submitted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('submitted_by', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('users.id'), nullable=True),

        # BZSt-Referenz (nach Einreichung)
        sa.Column('bzst_reference', sa.String(100), nullable=True),
        sa.Column('bzst_response_code', sa.String(20), nullable=True),
        sa.Column('bzst_response_message', sa.Text(), nullable=True),

        # Inhalt der Meldung (Snapshot zum Zeitpunkt der Einreichung)
        sa.Column('total_amount', sa.Numeric(15, 2), nullable=True),
        sa.Column('record_count', sa.Integer(), nullable=True),
        sa.Column('triangular_count', sa.Integer(), nullable=True),
        sa.Column('countries_involved', postgresql.JSONB(), nullable=True),

        # Deadline (25. des Folgemonats)
        sa.Column('deadline', sa.Date(), nullable=False),
        sa.Column('is_late', sa.Boolean(), default=False),

        # Korrektur-Referenz (falls dies eine Korrekturmeldung ist)
        sa.Column('original_submission_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('zm_submissions.id', ondelete='SET NULL'),
                  nullable=True),

        # Timestamps
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.text('NOW()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True),
                  server_default=sa.text('NOW()'), nullable=False),

        # Unique constraint: one submission per user/company per period
        sa.UniqueConstraint('user_id', 'company_id', 'period',
                           name='uq_zm_submission_period'),
    )

    # Create indexes
    # NOTE: ix_zm_submissions_period bereits durch index=True in Column erstellt
    op.create_index('ix_zm_submissions_status', 'zm_submissions', ['status'])
    op.create_index('ix_zm_submissions_deadline', 'zm_submissions', ['deadline', 'is_late'])


def downgrade() -> None:
    """Drop zm_submissions table."""
    op.drop_index('ix_zm_submissions_deadline', table_name='zm_submissions')
    op.drop_index('ix_zm_submissions_status', table_name='zm_submissions')
    # NOTE: ix_zm_submissions_period wird mit Tabelle geloescht (inline index=True)
    op.drop_table('zm_submissions')
