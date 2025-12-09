"""Add deleted_at field to OCRTrainingSample for GDPR compliance.

Enables soft-delete functionality for OCR training samples,
allowing GDPR-compliant data retention and deletion workflows.

Revision ID: 035_add_ocr_training_sample_deleted_at
Revises: 034_add_missing_indexes
Create Date: 2025-12-09
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = "035_add_ocr_training_sample_deleted_at"
down_revision = "034_add_missing_indexes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add deleted_at column and index to ocr_training_samples."""

    # Add deleted_at column for GDPR soft-delete
    op.add_column(
        "ocr_training_samples",
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True)
    )

    # Add index for efficient filtering of non-deleted samples
    op.create_index(
        "ix_ocr_training_samples_deleted_at",
        "ocr_training_samples",
        ["deleted_at"],
        unique=False
    )


def downgrade() -> None:
    """Remove deleted_at column and index from ocr_training_samples."""

    # Drop index first
    op.drop_index("ix_ocr_training_samples_deleted_at", table_name="ocr_training_samples")

    # Drop column
    op.drop_column("ocr_training_samples", "deleted_at")
