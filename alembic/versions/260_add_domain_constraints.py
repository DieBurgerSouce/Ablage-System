"""Add domain-level CHECK constraints for confidence scores, amounts, and rates.

Addresses schema review findings K2/K3:
- Confidence/score fields must be 0.0-1.0
- Amount fields must be non-negative (except transaction amounts which can be negative for debits)
- Interest rates must be 0-100%
- German validation scores must be 0.0-1.0

Revision ID: 260
Revises: 259
Create Date: 2026-03-09
"""
from alembic import op
from sqlalchemy import text

revision = "260"
down_revision = "259"
branch_labels = None
depends_on = None

# (table, constraint_name, expression)
CONSTRAINTS = [
    # === Confidence scores (0.0 - 1.0) ===
    (
        "documents",
        "ck_documents_ocr_confidence_range",
        "ocr_confidence IS NULL OR (ocr_confidence >= 0 AND ocr_confidence <= 1)",
    ),
    (
        "documents",
        "ck_documents_german_validation_score_range",
        "german_validation_score IS NULL OR (german_validation_score >= 0 AND german_validation_score <= 1)",
    ),
    (
        "ocr_results",
        "ck_ocr_results_confidence_range",
        "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
    ),
    # === Banking: non-negative amounts ===
    (
        "payment_orders",
        "ck_payment_orders_amount_positive",
        "amount >= 0",
    ),
    (
        "payment_orders",
        "ck_payment_orders_remaining_positive",
        "remaining_amount IS NULL OR remaining_amount >= 0",
    ),
    # === Dunning: rates and fees ===
    (
        "dunning_records",
        "ck_dunning_records_interest_rate_range",
        "late_interest_rate IS NULL OR (late_interest_rate >= 0 AND late_interest_rate <= 100)",
    ),
    (
        "dunning_records",
        "ck_dunning_records_fee_positive",
        "fee_amount IS NULL OR fee_amount >= 0",
    ),
    (
        "dunning_records",
        "ck_dunning_records_interest_positive",
        "accrued_interest IS NULL OR accrued_interest >= 0",
    ),
    (
        "dunning_records",
        "ck_dunning_records_outstanding_positive",
        "outstanding_amount IS NULL OR outstanding_amount >= 0",
    ),
]


def _table_exists(conn, table_name: str) -> bool:
    result = conn.execute(
        text("SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = :t"),
        {"t": table_name},
    ).fetchone()
    return result is not None


def _constraint_exists(conn, constraint_name: str) -> bool:
    result = conn.execute(
        text("SELECT 1 FROM pg_constraint WHERE conname = :n"),
        {"n": constraint_name},
    ).fetchone()
    return result is not None


def upgrade() -> None:
    conn = op.get_bind()
    for table, name, expr in CONSTRAINTS:
        if _table_exists(conn, table) and not _constraint_exists(conn, name):
            op.execute(
                f"ALTER TABLE {table} ADD CONSTRAINT {name} CHECK ({expr})"
            )


def downgrade() -> None:
    for table, name, _expr in reversed(CONSTRAINTS):
        op.execute(
            f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {name}"
        )
