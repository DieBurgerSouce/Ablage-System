"""Add created_by_id and updated_by_id audit fields to payment_batches and dunning_records.

GoBD Compliance: Nachvollziehbarkeit wer Datensaetze erstellt/bearbeitet hat.

Revision ID: 252
Revises: 251
Create Date: 2026-02-22
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "252"
down_revision = "251"
branch_labels = None
depends_on = None

_UUID = postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    # PaymentBatch
    op.add_column(
        "payment_batches",
        sa.Column("created_by_id", _UUID, nullable=True),
    )
    op.add_column(
        "payment_batches",
        sa.Column("updated_by_id", _UUID, nullable=True),
    )
    op.create_foreign_key(
        "fk_payment_batches_created_by_id",
        "payment_batches", "users", ["created_by_id"], ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_payment_batches_updated_by_id",
        "payment_batches", "users", ["updated_by_id"], ["id"],
        ondelete="SET NULL",
    )

    # DunningRecord
    op.add_column(
        "dunning_records",
        sa.Column("created_by_id", _UUID, nullable=True),
    )
    op.add_column(
        "dunning_records",
        sa.Column("updated_by_id", _UUID, nullable=True),
    )
    op.create_foreign_key(
        "fk_dunning_records_created_by_id",
        "dunning_records", "users", ["created_by_id"], ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_dunning_records_updated_by_id",
        "dunning_records", "users", ["updated_by_id"], ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    # DunningRecord
    op.drop_constraint(
        "fk_dunning_records_updated_by_id", "dunning_records", type_="foreignkey",
    )
    op.drop_constraint(
        "fk_dunning_records_created_by_id", "dunning_records", type_="foreignkey",
    )
    op.drop_column("dunning_records", "updated_by_id")
    op.drop_column("dunning_records", "created_by_id")

    # PaymentBatch
    op.drop_constraint(
        "fk_payment_batches_updated_by_id", "payment_batches", type_="foreignkey",
    )
    op.drop_constraint(
        "fk_payment_batches_created_by_id", "payment_batches", type_="foreignkey",
    )
    op.drop_column("payment_batches", "updated_by_id")
    op.drop_column("payment_batches", "created_by_id")
