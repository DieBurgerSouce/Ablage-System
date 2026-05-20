"""Add auto-generation columns to supplier_ocr_templates

Revision ID: 218_add_ocr_template_auto_generation
Revises: 217_add_year_end_tables
Create Date: 2026-02-13

Adds columns for automatic OCR template generation:
- is_auto_generated: Boolean flag for auto-generated templates
- source_document_ids: JSONB list of document UUIDs used for generation
- auto_confidence: Float confidence score of the generated template
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '218_add_ocr_template_auto_generation'
down_revision: str = '217_add_year_end_tables'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add auto-generation columns to supplier_ocr_templates."""
    op.add_column('supplier_ocr_templates',
                  sa.Column('is_auto_generated', sa.Boolean(), nullable=True, server_default='false'))
    op.add_column('supplier_ocr_templates',
                  sa.Column('source_document_ids', postgresql.JSONB(), nullable=True))
    op.add_column('supplier_ocr_templates',
                  sa.Column('auto_confidence', sa.Float(), nullable=True))
    op.create_index('ix_ocr_template_auto_generated', 'supplier_ocr_templates', ['is_auto_generated'])


def downgrade() -> None:
    """Remove auto-generation columns from supplier_ocr_templates."""
    op.drop_index('ix_ocr_template_auto_generated', table_name='supplier_ocr_templates')
    op.drop_column('supplier_ocr_templates', 'auto_confidence')
    op.drop_column('supplier_ocr_templates', 'source_document_ids')
    op.drop_column('supplier_ocr_templates', 'is_auto_generated')
