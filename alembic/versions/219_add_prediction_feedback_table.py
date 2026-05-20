"""Add prediction_feedbacks table

Revision ID: 219_add_prediction_feedback_table
Revises: 218_add_ocr_template_auto_generation
Create Date: 2026-02-13

Persistiert ML-Vorhersage-Feedback fuer Retraining:
- prediction_feedbacks Tabelle
- Indexes fuer Entity+Type+Created und Company+Status
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '219_add_prediction_feedback_table'
down_revision: str = '218_add_ocr_template_auto_generation'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create prediction_feedbacks table."""
    op.create_table(
        'prediction_feedbacks',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            'entity_id',
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey('business_entities.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column(
            'company_id',
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey('companies.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column('prediction_id', sa.String(100), unique=True, nullable=False),
        sa.Column('prediction_type', sa.String(50), nullable=False),
        sa.Column('predicted_value', sa.Float, nullable=False),
        sa.Column('actual_value', sa.Float, nullable=False),
        sa.Column('was_accurate', sa.Boolean, nullable=False),
        sa.Column('status', sa.String(20), nullable=False, server_default='pending'),
        sa.Column('processed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('extra_data', postgresql.JSONB, nullable=True),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    op.create_index(
        'ix_prediction_feedbacks_entity_type_created',
        'prediction_feedbacks',
        ['entity_id', 'prediction_type', 'created_at'],
    )
    op.create_index(
        'ix_prediction_feedbacks_company_status',
        'prediction_feedbacks',
        ['company_id', 'status'],
    )
    op.create_index(
        'ix_prediction_feedbacks_prediction_type',
        'prediction_feedbacks',
        ['prediction_type'],
    )
    op.create_index(
        'ix_prediction_feedbacks_was_accurate',
        'prediction_feedbacks',
        ['was_accurate'],
    )


def downgrade() -> None:
    """Drop prediction_feedbacks table."""
    op.drop_index('ix_prediction_feedbacks_was_accurate', table_name='prediction_feedbacks')
    op.drop_index('ix_prediction_feedbacks_prediction_type', table_name='prediction_feedbacks')
    op.drop_index('ix_prediction_feedbacks_company_status', table_name='prediction_feedbacks')
    op.drop_index('ix_prediction_feedbacks_entity_type_created', table_name='prediction_feedbacks')
    op.drop_table('prediction_feedbacks')
