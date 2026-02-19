"""Add unique constraint for event store sequence numbers.

Revision ID: 235
Revises: 234
Create Date: 2026-02-19

Prevents duplicate sequence numbers for the same aggregate,
fixing the race condition in event_store.py.
"""
from alembic import op

revision = "235"
down_revision = "234"
branch_labels = None
depends_on = None


def upgrade() -> None:
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
