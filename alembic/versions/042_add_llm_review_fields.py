"""Add LLM Review Pipeline Fields for Phase 6.

Revision ID: 042_add_llm_review_fields
Revises: 041_add_business_profiles
Create Date: 2024-12-16

LLM-basierte Review und Korrektur von OCR-Ergebnissen.

Neue Felder in ocr_training_samples:
- llm_review_status: Status der LLM-Review (pending, reviewed, accepted, rejected, needs_human)
- llm_review_result: JSON mit Ergebnis der LLM-Review (quality_score, issues, recommendation)
- llm_corrected_text: Korrigierter Text vom LLM
- llm_reviewed_at: Timestamp der LLM-Review

Bei rejected/low-quality Samples:
1. LLM prueft semantische Korrektheit
2. LLM korrigiert OCR-typische Fehler
3. LLM bewertet Qualitaet (Score 1-10)
4. LLM entscheidet: accept|reject|needs_human
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "042"
down_revision = "041"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add LLM review pipeline fields to ocr_training_samples."""

    # Check if we're using PostgreSQL
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    # JSON type based on dialect
    if is_postgres:
        json_type = postgresql.JSONB
    else:
        json_type = sa.JSON

    # =========================================================================
    # ADD LLM REVIEW COLUMNS TO OCR_TRAINING_SAMPLES
    # =========================================================================

    # LLM Review Status: pending, reviewed, accepted, rejected, needs_human
    op.add_column(
        "ocr_training_samples",
        sa.Column("llm_review_status", sa.String(20), default="pending")
    )

    # LLM Review Result: {quality_score, issues_found, recommendation, reasoning}
    op.add_column(
        "ocr_training_samples",
        sa.Column("llm_review_result", json_type, nullable=True)
    )

    # Korrigierter Text vom LLM
    op.add_column(
        "ocr_training_samples",
        sa.Column("llm_corrected_text", sa.Text, nullable=True)
    )

    # Timestamp der LLM-Review
    op.add_column(
        "ocr_training_samples",
        sa.Column("llm_reviewed_at", sa.DateTime(timezone=True), nullable=True)
    )

    # =========================================================================
    # ADD INDEX FOR EFFICIENT QUERIES
    # =========================================================================

    op.create_index(
        "ix_ocr_training_samples_llm_review",
        "ocr_training_samples",
        ["llm_review_status"]
    )


def downgrade() -> None:
    """Remove LLM review pipeline fields from ocr_training_samples."""

    # Remove index
    op.drop_index("ix_ocr_training_samples_llm_review", table_name="ocr_training_samples")

    # Remove columns
    op.drop_column("ocr_training_samples", "llm_reviewed_at")
    op.drop_column("ocr_training_samples", "llm_corrected_text")
    op.drop_column("ocr_training_samples", "llm_review_result")
    op.drop_column("ocr_training_samples", "llm_review_status")
