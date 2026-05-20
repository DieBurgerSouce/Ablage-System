"""Add SHA-256 hash chain columns to domain_events.

Revision ID: 254
Revises: 253
Create Date: 2026-02-23
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "254"
down_revision = "253"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("domain_events", sa.Column("event_hash", sa.String(64), nullable=True))
    op.add_column("domain_events", sa.Column("previous_hash", sa.String(64), nullable=True))
    op.add_column("domain_events", sa.Column("chain_hash", sa.String(64), nullable=True))
    op.create_index("ix_domain_events_chain_hash", "domain_events", ["chain_hash"])


def downgrade() -> None:
    op.drop_index("ix_domain_events_chain_hash", table_name="domain_events")
    op.drop_column("domain_events", "chain_hash")
    op.drop_column("domain_events", "previous_hash")
    op.drop_column("domain_events", "event_hash")
