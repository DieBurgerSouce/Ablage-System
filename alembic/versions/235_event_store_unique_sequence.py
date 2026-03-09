"""Add unique constraint for event store sequence numbers.

Revision ID: 235
Revises: 234
Create Date: 2026-02-19

Prevents duplicate sequence numbers for the same aggregate,
fixing the race condition in event_store.py.
"""
from alembic import op
import sqlalchemy as sa

revision = "235"
down_revision = "234"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Idempotent: skip if constraint or backing index already exists
    conn = op.get_bind()
    exists = conn.execute(
        sa.text(
            """SELECT 1 FROM pg_constraint WHERE conname = 'uq_domain_events_aggregate_sequence'
               UNION ALL
               SELECT 1 FROM pg_indexes WHERE indexname = 'uq_domain_events_aggregate_sequence'"""
        )
    ).fetchone()
    if not exists:
        op.create_unique_constraint(
            "uq_domain_events_aggregate_sequence",
            "domain_events",
            ["aggregate_type", "aggregate_id", "sequence_number"],
        )


def downgrade() -> None:
    op.drop_constraint(
        "uq_domain_events_aggregate_sequence",
        "domain_events",
        type_="unique",
    )
